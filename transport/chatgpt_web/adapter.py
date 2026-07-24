"""ChatGPT web transport adapter (mission spec §7.1 / §8 / §13).

Driver abstraction — the adapter logic (conversation locking, multi-signal
completion detection, latest-response extraction, blocker detection,
duplicate protection, delivery-uncertainty handling) is IDENTICAL in both
modes:

* ``LocalFixtureDriver`` — drives the §22 local fixture over HTTP;
* ``WebBridgeDriver`` — drives real Chrome through the local WebBridge
  daemon (http://127.0.0.1:10086, POST /command). Used in Phase 5 against
  real ChatGPT; untested here by design.

DOM contract (identical for both drivers):

    PageState {
      url, conversation_id, title,
      blocker: None | "login" | "captcha" | "rate_limit",
      composer_present, send_button_present,
      stop_button_present, streaming,
      messages: [{id, role, text, code_blocks: [{lang, text}]}]
    }

Because rendered ChatGPT messages preserve code-fence CONTENT verbatim but
not the fence markers, ``protocol_text()`` reconstructs synthetic
```cortex-decision fences from code_blocks for the Phase 3 loop.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from orchestration import protocol

# -- error taxonomy (§5/§8/§13: pause safely, never bypass) ---------------------

CONVERSATION_MISMATCH = "CONVERSATION_MISMATCH"
CHATGPT_RESPONSE_TIMEOUT = "CHATGPT_RESPONSE_TIMEOUT"
TAB_CLOSED = "TAB_CLOSED"
LOGIN_REQUIRED = "LOGIN_REQUIRED"
CAPTCHA = "CAPTCHA"
RATE_LIMIT = "RATE_LIMIT"
DELIVERY_UNCERTAIN = "DELIVERY_UNCERTAIN"
TRANSPORT_PAUSED = "TRANSPORT_PAUSED"
DUPLICATE_EXTRACTION = "DUPLICATE_EXTRACTION"
NO_CONVERSATION = "NO_CONVERSATION"
GENERATION_CANCELLED = "GENERATION_CANCELLED"
STATE_UNREADABLE = "STATE_UNREADABLE"
SEND_REJECTED = "SEND_REJECTED"

BLOCKER_CODES = {"login": LOGIN_REQUIRED, "captcha": CAPTCHA, "rate_limit": RATE_LIMIT}

DEFAULT_STABILITY_INTERVAL = 2.0  # §13: message stable for 2 seconds
DEFAULT_MAX_WAIT = 300.0  # §13: 5 minutes per ChatGPT response
DEFAULT_POLL_INTERVAL = 0.5


class TransportError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class ConversationMismatch(TransportError):
    def __init__(self, message: str):
        super().__init__(CONVERSATION_MISMATCH, message)


class BlockerDetected(TransportError):
    """Login / CAPTCHA / rate-limit — pause safely, request human help."""

    def __init__(self, kind: str):
        super().__init__(BLOCKER_CODES.get(kind, kind.upper()), f"blocker detected: {kind}")
        self.kind = kind


class DriverError(Exception):
    """A driver-level failure (page unreadable, daemon down, send rejected)."""


class TabClosedError(DriverError):
    pass


@dataclass
class ConversationLock:
    """§8: one locked conversation — never guessed, never silently switched."""

    url: str
    identity: str
    title: str | None
    selected_at: float

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "identity": self.identity,
            "title": self.title,
            "selected_at": self.selected_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationLock":
        return cls(data["url"], data["identity"], data.get("title"), data["selected_at"])


def protocol_text(message: dict) -> str:
    """Reconstruct synthetic fenced text for the cortex.v1 extractor.

    Rendered messages lose fence markers; the code content survives in
    code_blocks. Rebuild ```lang fences so protocol.extract_decision_block
    sees exactly the blocks the orchestrator emitted.
    """
    blocks = message.get("code_blocks") or []
    if not blocks:
        return message.get("text", "")
    return "\n".join(f"```{b.get('lang', '')}\n{b.get('text', '')}\n```" for b in blocks)


class ChatGPTWebTransport:
    """§7.1 transport: select/lock one conversation, send, await, extract."""

    def __init__(
        self,
        driver,
        *,
        stability_interval: float = DEFAULT_STABILITY_INTERVAL,
        max_wait: float = DEFAULT_MAX_WAIT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ):
        self.driver = driver
        self.stability_interval = stability_interval
        self.max_wait = max_wait
        self.poll_interval = poll_interval
        self.lock: ConversationLock | None = None
        self.paused = False
        self.pause_reason: str | None = None
        self.delivery_uncertain = False
        self.streaming_observed = False
        self._extracted_ids: set[str] = set()
        self._baseline: set[str] = set()
        self._cancel_requested = False

    # -- pause/resume (§5: pause safely on any blocker) ------------------------------

    def pause(self, reason: str) -> None:
        self.paused = True
        self.pause_reason = reason

    def resume(self) -> None:
        self.paused = False
        self.pause_reason = None

    # -- §8 conversation selection + lock ----------------------------------------------

    async def select_conversation(self, url: str) -> ConversationLock:
        """Navigate to a user-chosen conversation and lock the mission to it."""
        await self.driver.navigate(url)
        state = await self._state()
        identity = state.get("conversation_id")
        if not identity:
            raise TransportError(NO_CONVERSATION, f"no conversation at {url}")
        self.lock = ConversationLock(url, identity, state.get("title"), time.time())
        self._baseline = {m["id"] for m in state.get("messages", []) if m["role"] == "assistant"}
        return self.lock

    async def attach(self, lock: ConversationLock) -> None:
        """Re-attach to a previously locked conversation (e.g. after a
        browser restart). Identity must match — never falls back to whatever
        tab happens to be focused (§8)."""
        await self.driver.navigate(lock.url)
        state = await self._state()
        if state.get("conversation_id") != lock.identity:
            self.pause(CONVERSATION_MISMATCH)
            raise ConversationMismatch(
                f"locked conversation {lock.identity} not found at {lock.url}"
            )
        self.lock = lock
        self._baseline = {m["id"] for m in state.get("messages", []) if m["role"] == "assistant"}

    async def verify_lock(self) -> None:
        """Verify before every message: current conversation == locked one."""
        if self.lock is None:
            raise TransportError(NO_CONVERSATION, "no conversation selected")
        state = await self._state()
        if state.get("conversation_id") != self.lock.identity:
            self.pause(CONVERSATION_MISMATCH)
            raise ConversationMismatch(
                f"page shows {state.get('conversation_id')!r}, locked to {self.lock.identity!r}"
            )

    # -- internal state access with blocker/tab handling --------------------------------

    async def _state(self) -> dict:
        try:
            state = await self.driver.get_state()
        except TabClosedError as exc:
            self.pause(TAB_CLOSED)
            raise TransportError(TAB_CLOSED, "browser tab was closed") from exc
        blocker = state.get("blocker")
        if blocker:
            self.pause(BLOCKER_CODES.get(blocker, blocker.upper()))
            raise BlockerDetected(blocker)
        return state

    # -- sending (§7.1) ----------------------------------------------------------------------

    async def send_message(self, text: str) -> dict:
        """Send one user message into the locked conversation.

        Never resends automatically; uncertain delivery must be resolved by
        the human (resolve_delivery) before any further send (§13/§22.19).
        """
        if self.delivery_uncertain:
            raise TransportError(
                DELIVERY_UNCERTAIN,
                "previous delivery is uncertain; refusing to resend — resolve first",
            )
        if self.paused:
            raise TransportError(
                TRANSPORT_PAUSED, f"transport paused ({self.pause_reason}); resume first"
            )
        await self.verify_lock()
        state = await self._state()
        self._baseline = {m["id"] for m in state.get("messages", []) if m["role"] == "assistant"}
        try:
            await self.driver.send_message(text)
        except DriverError as exc:
            self.delivery_uncertain = True
            self.pause(DELIVERY_UNCERTAIN)
            raise TransportError(DELIVERY_UNCERTAIN, f"send may have failed: {exc}") from exc
        try:
            after = await self._state()
        except (TransportError, DriverError) as exc:
            self.delivery_uncertain = True
            self.pause(DELIVERY_UNCERTAIN)
            raise TransportError(
                DELIVERY_UNCERTAIN, f"cannot confirm delivery: {exc}"
            ) from exc
        sent = [
            m
            for m in after.get("messages", [])
            if m["role"] == "user" and text.split("\n", 1)[0][:80] in m.get("text", "")
        ]
        if not sent:
            self.delivery_uncertain = True
            self.pause(DELIVERY_UNCERTAIN)
            raise TransportError(DELIVERY_UNCERTAIN, "user message not visible after send")
        self._cancel_requested = False
        self.streaming_observed = False
        return sent[-1]

    async def resolve_delivery(self) -> None:
        """Human confirmed the page state; clear delivery uncertainty."""
        await self._state()  # raises if still unreadable / blocked
        self.delivery_uncertain = False
        self.resume()

    # -- §13 response-completion detection (multi-signal) --------------------------------------

    async def await_response(self) -> dict:
        """Wait for the next assistant response and extract it once.

        Completion requires ALL of: stop button gone, no streaming indicator,
        latest new assistant message unchanged for the stability interval.
        On timeout: pause safely with CHATGPT_RESPONSE_TIMEOUT; never resend
        automatically.
        """
        if self.paused:
            raise TransportError(
                TRANSPORT_PAUSED, f"transport paused ({self.pause_reason}); resume first"
            )
        deadline = time.monotonic() + self.max_wait
        last_text: str | None = None
        stable_since: float | None = None
        while time.monotonic() < deadline:
            if self._cancel_requested:
                self._cancel_requested = False
                raise TransportError(GENERATION_CANCELLED, "generation cancelled by user")
            state = await self._state()
            if state.get("stop_button_present") or state.get("streaming"):
                self.streaming_observed = True
                stable_since = None
            new_msgs = [
                m
                for m in state.get("messages", [])
                if m["role"] == "assistant" and m["id"] not in self._baseline
            ]
            if new_msgs:
                latest = new_msgs[-1]
                if not state.get("stop_button_present") and not state.get("streaming"):
                    now = time.monotonic()
                    if latest.get("text") == last_text:
                        stable_since = stable_since if stable_since is not None else now
                        if now - stable_since >= self.stability_interval:
                            if latest["id"] in self._extracted_ids:
                                raise TransportError(
                                    DUPLICATE_EXTRACTION,
                                    f"message {latest['id']} was already extracted",
                                )
                            self._extracted_ids.add(latest["id"])
                            return {
                                "id": latest["id"],
                                "role": "assistant",
                                "text": latest.get("text", ""),
                                "protocol_text": protocol_text(latest),
                            }
                    else:
                        last_text = latest.get("text")
                        stable_since = None
            await asyncio.sleep(self.poll_interval)
        self.pause(CHATGPT_RESPONSE_TIMEOUT)
        raise TransportError(
            CHATGPT_RESPONSE_TIMEOUT,
            f"no completed response within {self.max_wait}s; mission paused",
        )

    async def cancel_generation(self) -> None:
        """Cancel the in-flight generation (§17 cancel during generation)."""
        self._cancel_requested = True
        try:
            await self.driver.press_stop()
        except DriverError:
            pass  # already stopped — cancellation still honored

    # -- §17 manual fallback ----------------------------------------------------------------------

    def manual_fallback_payload(self, report: dict | None = None, note: str | None = None) -> str:
        """Payload the user can paste manually when the transport is down."""
        parts = ["[Cortex Bridge — manual fallback payload]"]
        if note:
            parts.append(note)
        if report is not None:
            parts.append(protocol.render_report_message(report))
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------


class LocalFixtureDriver:
    """Drives the §22 local fixture over HTTP (mirrors WebBridge semantics:
    navigating makes a conversation the 'current tab')."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def _fetch(url: str) -> None:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                resp.read()
        except urllib.error.HTTPError as exc:
            raise DriverError(f"GET {url} -> {exc.code}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise DriverError(f"GET {url} failed: {exc}") from exc

    @staticmethod
    def _get(url: str) -> dict:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise DriverError(f"GET {url} -> {exc.code}") from exc
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise DriverError(f"GET {url} failed: {exc}") from exc

    @staticmethod
    def _post(url: str, payload: dict) -> dict:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            raise DriverError(f"POST {url} -> {exc.code} {detail}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise DriverError(f"POST {url} failed: {exc}") from exc

    async def navigate(self, url: str) -> None:
        await asyncio.to_thread(self._fetch, url)

    async def get_state(self) -> dict:
        state = await asyncio.to_thread(self._get, f"{self.base_url}/__state")
        if state.get("tab_closed"):
            raise TabClosedError("tab closed")
        return state

    async def send_message(self, text: str) -> None:
        await asyncio.to_thread(self._post, f"{self.base_url}/__send", {"text": text})

    async def press_stop(self) -> None:
        await asyncio.to_thread(self._post, f"{self.base_url}/__stop", {})

    async def close_tab(self) -> None:
        pass  # fixture tab closure is test-controlled via FixtureServer.close_tab()


_STATE_JS = r"""
(() => {
  const q = (sel) => document.querySelector(sel);
  const all = (sel) => Array.from(document.querySelectorAll(sel));
  const text = document.body ? document.body.innerText : '';
  let blocker = null;
  if (!q('#prompt-textarea') && /log in|sign up/i.test(text)) blocker = 'login';
  if (/verify you are human|cf-chl|cloudflare/i.test(text)) blocker = 'captcha';
  if (/rate limit|too many requests/i.test(text)) blocker = 'rate_limit';
  const convMatch = location.pathname.match(/\/c\/([A-Za-z0-9-]+)/);
  const messages = all('[data-message-author-role]').map((el, i) => {
    const blocks = Array.from(el.querySelectorAll('pre')).map((pre) => {
      const header = pre.closest('[class*="code-block"]')?.querySelector('span, div');
      const code = pre.querySelector('code');
      const langClass = code ? (code.className.match(/language-([A-Za-z0-9_.+-]*)/) || [])[1] : '';
      return { lang: langClass || (header ? header.textContent.trim().toLowerCase() : ''), text: pre.textContent };
    });
    return {
      id: el.getAttribute('data-message-id') || ('idx-' + i),
      role: el.getAttribute('data-message-author-role'),
      text: el.textContent,
      code_blocks: blocks,
    };
  });
  const stop = q('button[aria-label*="Stop"], [data-testid="stop-button"]');
  return JSON.stringify({
    url: location.href,
    conversation_id: convMatch ? convMatch[1] : null,
    title: document.title,
    blocker: blocker,
    composer_present: !!q('#prompt-textarea'),
    send_button_present: !!q('button[data-testid="send-button"], #prompt-textarea'),
    stop_button_present: !!stop,
    streaming: !!stop || !!q('.result-streaming'),
    messages: messages,
  });
})()
"""


class WebBridgeDriver:
    """Drives the user's Chrome through the local WebBridge daemon.

    Phase 5 uses this against real chatgpt.com. Loopback only; the daemon
    holds the actual browser session. NOT exercised by fixture tests.
    """

    def __init__(self, daemon: str = "http://127.0.0.1:10086", session: str = "cortex-bridge"):
        self.daemon = daemon.rstrip("/")
        self.session = session

    def _command(self, action: str, args: dict | None = None) -> Any:
        payload = {"action": action, "args": args or {}, "session": self.session}
        req = urllib.request.Request(
            f"{self.daemon}/command",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise DriverError(f"webbridge {action} failed: {exc}") from exc
        if isinstance(data, dict) and data.get("ok") is False:
            raise DriverError(f"webbridge {action} rejected: {data.get('error')}")
        return data.get("result", data)

    async def navigate(self, url: str) -> None:
        await asyncio.to_thread(self._command, "navigate", {"url": url, "newTab": False})

    async def get_state(self) -> dict:
        raw = await asyncio.to_thread(self._command, "evaluate", {"code": _STATE_JS})
        if isinstance(raw, dict) and "value" in raw:
            raw = raw["value"]
        try:
            return json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise DriverError(f"cannot parse page state: {exc}") from exc

    async def send_message(self, text: str) -> None:
        await asyncio.to_thread(
            self._command, "fill", {"selector": "#prompt-textarea", "value": text}
        )
        await asyncio.to_thread(
            self._command,
            "evaluate",
            {
                "code": "document.querySelector('button[data-testid=\"send-button\"]')?.click()"
                " ?? document.querySelector('#prompt-textarea')?.dispatchEvent("
                "new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}))"
            },
        )

    async def press_stop(self) -> None:
        await asyncio.to_thread(
            self._command,
            "evaluate",
            {"code": "document.querySelector('button[aria-label*=\"Stop\"]')?.click()"},
        )

    async def close_tab(self) -> None:
        await asyncio.to_thread(self._command, "close_tab", {})
