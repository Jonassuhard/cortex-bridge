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
STREAM_TIMEOUT = "STREAM_TIMEOUT"

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
        self._pending_new_chat = False

    # -- pause/resume (§5: pause safely on any blocker) ------------------------------

    def pause(self, reason: str) -> None:
        self.paused = True
        self.pause_reason = reason

    def resume(self) -> None:
        self.paused = False
        self.pause_reason = None

    # -- §8 conversation selection + lock ----------------------------------------------

    async def list_conversations(self) -> list[dict]:
        """Candidate conversations (title + /c/<uuid> identity) for the user
        to pick from. Sidebar DOM on real ChatGPT; registry on the fixture."""
        return await self.driver.list_conversations()

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

    async def start_new_conversation(self, url: str) -> None:
        """§8 brand-new chat case: navigate to a fresh chat surface. The
        /c/<id> identity only exists after the first send; the lock is
        captured by send_message → _capture_new_lock()."""
        await self.driver.navigate(url)
        state = await self._state()
        if state.get("conversation_id"):
            # The URL already is a conversation — lock it normally.
            await self.select_conversation(url)
            return
        self._pending_new_chat = True
        self._baseline = set()

    async def _capture_new_lock(self, original_url: str) -> None:
        """Poll until the backend assigns a /c/<id> URL, then lock it.

        Right after the first send, ChatGPT shows a transient
        /c/WEB:<uuid> URL that the SPA later rewrites to the canonical
        /c/<uuid>. Locking the transient identity breaks re-attach on
        resume (the canonical page never matches "WEB"), so keep polling
        for the canonical form until the deadline."""
        deadline = time.monotonic() + min(30.0, self.max_wait)
        transient: ConversationLock | None = None
        while time.monotonic() < deadline:
            state = await self._state()
            identity = state.get("conversation_id")
            if identity:
                lock = ConversationLock(
                    state.get("url", original_url), identity, state.get("title"), time.time()
                )
                if ":" not in state.get("url", "").rsplit("/c/", 1)[-1]:
                    self.lock = lock
                    self._pending_new_chat = False
                    return
                transient = lock  # transient WEB:<uuid> — wait for canonical
            await asyncio.sleep(self.poll_interval)
        if transient is not None:
            # Deadline hit with only the transient URL: lock it rather than
            # losing the conversation; re-attach may need human resolution.
            self.lock = transient
            self._pending_new_chat = False
            return
        self.delivery_uncertain = True
        self.pause(DELIVERY_UNCERTAIN)
        raise TransportError(
            DELIVERY_UNCERTAIN, "message sent but no /c/<id> URL appeared — cannot lock"
        )

    async def verify_lock(self) -> None:
        """Verify before every message: current conversation == locked one."""
        if self._pending_new_chat:
            return  # identity does not exist yet; captured after first send
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
        # Never type into the composer while ChatGPT is still streaming:
        # the send button is disabled and the draft can be lost on re-render.
        deadline = time.monotonic() + min(60.0, self.max_wait)
        while state.get("streaming") and time.monotonic() < deadline:
            await asyncio.sleep(self.poll_interval)
            state = await self._state()
        if state.get("streaming"):
            raise TransportError(STREAM_TIMEOUT, "still streaming before send")
        self._baseline = {m["id"] for m in state.get("messages", []) if m["role"] == "assistant"}
        try:
            await self.driver.send_message(text)
        except DriverError as exc:
            self.delivery_uncertain = True
            self.pause(DELIVERY_UNCERTAIN)
            raise TransportError(DELIVERY_UNCERTAIN, f"send may have failed: {exc}") from exc
        # The SPA takes a moment to render the sent user message — poll for it.
        first_line = text.split("\n", 1)[0][:80]
        sent: list[dict] = []
        after: dict = {}
        deadline = time.monotonic() + min(30.0, self.max_wait)
        while time.monotonic() < deadline:
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
                if m["role"] == "user" and first_line in m.get("text", "")
            ]
            if sent:
                break
            await asyncio.sleep(0.5)
        if not sent:
            self.delivery_uncertain = True
            self.pause(DELIVERY_UNCERTAIN)
            raise TransportError(DELIVERY_UNCERTAIN, "user message not visible after send")
        if self._pending_new_chat:
            await self._capture_new_lock(after.get("url", ""))
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

    async def list_conversations(self) -> list[dict]:
        return await asyncio.to_thread(self._get, f"{self.base_url}/__conversations")

    async def close_tab(self) -> None:
        pass  # fixture tab closure is test-controlled via FixtureServer.close_tab()


# §6 warning shown before the experimental transport may be enabled.
EXPERIMENTAL_TRANSPORT_WARNING = (
    "This mode automates the ChatGPT web interface.\n"
    "It is experimental and may stop working when the interface changes.\n"
    "Use it at your own discretion.\n"
    "No CAPTCHA, authentication or anti-bot bypass is implemented."
)

# ---------------------------------------------------------------------------
# Live-validated JS DOM contract (see docs/phase5-dom-contract.md, 2026-07-24)
# ---------------------------------------------------------------------------

_STATE_JS = r"""
(() => {
  const q = (sel) => document.querySelector(sel);
  const text = document.body ? document.body.innerText.slice(0, 8000) : '';
  const composer = q('#prompt-textarea');
  // Blockers (conservative; see docs/phase5-dom-contract.md §f):
  let blocker = null;
  if (!composer && /log in|sign up|se connecter|inscrivez-vous/i.test(text)) blocker = 'login';
  if (/verify you are human|v\u00e9rifiez que vous \u00eates humain|cf-chl|challenge-platform/i.test(text)
      || q('#cf-chl-widget, .cf-turnstile')) blocker = 'captcha';
  if (/rate limit|too many requests|limite de requ\u00eates/i.test(text)) blocker = 'rate_limit';
  const convMatch = location.pathname.match(/\/c\/([A-Za-z0-9-]+)/);
  // Code blocks are CodeMirror viewers (pre.cm-content); NO language label
  // exists in the header on this build -> cortex-decision is content-sniffed.
  const sniffLang = (t) => {
    try { const j = JSON.parse(t); if (j && j.protocol === 'cortex.v1') return 'cortex-decision'; }
    catch (e) {}
    return '';
  };
  const messages = Array.from(document.querySelectorAll('[data-message-author-role]')).map((el, i) => {
    const blocks = Array.from(el.querySelectorAll('pre.cm-content')).map((pre) => {
      const t = pre.textContent || '';
      return { lang: sniffLang(t), text: t };
    });
    return {
      id: el.getAttribute('data-message-id') || ('idx-' + i),
      role: el.getAttribute('data-message-author-role'),
      text: el.textContent || '',
      code_blocks: blocks,
    };
  });
  const stop = q('[data-testid="stop-button"], button[aria-label*="Stop"], button[aria-label*="Arr"]');
  const streaming = !!stop || !!q('.result-streaming');
  return JSON.stringify({
    url: location.href,
    conversation_id: convMatch ? convMatch[1] : null,
    title: document.title,
    blocker: blocker,
    composer_present: !!composer,
    send_button_present: !!composer,
    stop_button_present: !!stop,
    streaming: streaming,
    messages: messages,
  });
})()
"""

_CONVERSATIONS_JS = r"""
(() => JSON.stringify(
  Array.from(document.querySelectorAll('nav a[href^="/c/"], aside a[href^="/c/"]')).map((a) => ({
    url: 'https://chatgpt.com' + a.getAttribute('href'),
    identity: (a.getAttribute('href').match(/\/c\/([A-Za-z0-9-]+)/) || [])[1],
    title: (a.textContent || '').trim(),
  })).filter((c) => c.identity)
))()
"""

# Phase 7 executes this; Phase 5 ships it unexecuted by design.
# Verified against real chatgpt.com (2026-07-24, FR UI):
#  - ProseMirror ignores `textContent =`; `document.execCommand('insertText')`
#    is the only injection that updates React state and arms the send button.
#  - The send button only exists once text is present: poll for it (long
#    contracts take several seconds to arm it — allow 10s).
#  - Its aria-label is "Envoyer le prompt" / "Send prompt" (testid send-button).
#  - Idempotent: if the composer already holds this exact text (recovery after
#    a failed send), skip the insert and just click send.
_SEND_JS = r"""
(async (text) => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  // The SPA may still be rendering when we land — wait for the composer.
  let composer = null;
  for (let i = 0; i < 50 && !composer; i++) {
    composer = document.querySelector('#prompt-textarea');
    if (!composer) await sleep(200);
  }
  if (!composer) return JSON.stringify({ ok: false, error: 'composer not found' });
  const current = (composer.innerText || '').replace(/\s+/g, ' ').trim();
  const wanted = text.replace(/\s+/g, ' ').trim();
  if (!current.startsWith(wanted.slice(0, 200))) {
    composer.focus();
    if (!document.execCommand('insertText', false, text)) {
      return JSON.stringify({ ok: false, error: 'insertText rejected' });
    }
  }
  const form = composer.closest('form') || document;
  const findSend = () => form.querySelector('button[data-testid="send-button"]:not([disabled])')
    || Array.from(form.querySelectorAll('button[aria-label]')).find((b) =>
        !b.disabled && /envoyer le (prompt|message)|send (prompt|message)/i.test(b.getAttribute('aria-label') || ''))
    || Array.from(form.querySelectorAll('button.composer-submit-button-color')).find((b) => !b.disabled);
  let btn = null;
  for (let i = 0; i < 50 && !btn; i++) { btn = findSend(); if (!btn) await sleep(200); }
  if (!btn) return JSON.stringify({ ok: false, error: 'send button not found' });
  btn.click();
  // Proof of send: the composer empties once the message is accepted.
  for (let i = 0; i < 25; i++) {
    await sleep(200);
    if (!(composer.innerText || '').trim()) return JSON.stringify({ ok: true });
  }
  return JSON.stringify({ ok: false, error: 'composer not cleared after click' });
})
"""


class WebBridgeDriver:
    """Drives the user's Chrome through the local WebBridge daemon.

    Phase 5 uses this against real chatgpt.com. Loopback only; the daemon
    holds the actual browser session. NOT exercised by fixture tests.
    """

    def __init__(self, daemon: str = "http://127.0.0.1:10086", session: str = "cortex-bridge"):
        self.daemon = daemon.rstrip("/")
        self.session = session

    def _command(self, action: str, args: dict | None = None, timeout: float = 30) -> Any:
        payload = {"action": action, "args": args or {}, "session": self.session}
        req = urllib.request.Request(
            f"{self.daemon}/command",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise DriverError(f"webbridge {action} failed: {exc}") from exc
        if isinstance(data, dict) and data.get("ok") is False:
            raise DriverError(f"webbridge {action} rejected: {data.get('error')}")
        # Daemon envelope is {"ok": true, "data": <payload>}.
        if isinstance(data, dict):
            return data.get("data", data.get("result", data))
        return data

    async def navigate(self, url: str) -> None:
        # chatgpt.com can be slow to load; allow a long timeout and retry once.
        last: DriverError | None = None
        for _ in range(2):
            try:
                await asyncio.to_thread(
                    self._command, "navigate", {"url": url, "newTab": False}, 90
                )
                return
            except DriverError as exc:
                last = exc
                await asyncio.sleep(1.5)
        raise last  # type: ignore[misc]

    async def get_state(self) -> dict:
        raw = await asyncio.to_thread(self._command, "evaluate", {"code": _STATE_JS})
        if isinstance(raw, dict) and "value" in raw:
            raw = raw["value"]
        try:
            return json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise DriverError(f"cannot parse page state: {exc}") from exc

    async def send_message(self, text: str) -> None:
        code = f"{_SEND_JS}({json.dumps(text)})"
        raw = await asyncio.to_thread(self._command, "evaluate", {"code": code}, 60)
        if isinstance(raw, dict) and "value" in raw:
            raw = raw["value"]
        result = json.loads(raw) if isinstance(raw, str) else (raw or {})
        if not result.get("ok"):
            raise DriverError(f"send failed: {result.get('error', 'unknown')}")

    async def press_stop(self) -> None:
        await asyncio.to_thread(
            self._command,
            "evaluate",
            {
                "code": "(document.querySelector('[data-testid=\"stop-button\"]')"
                " || document.querySelector('button[aria-label*=\"Stop\"]')"
                " || document.querySelector('button[aria-label*=\"Arr\"]'))?.click()"
            },
        )

    async def list_conversations(self) -> list[dict]:
        """§8 candidates from the sidebar DOM of an open chatgpt.com tab."""
        # The session may have no tab yet — open chatgpt.com first.
        try:
            tabs = await asyncio.to_thread(self._command, "list_tabs", {})
            tab_list = tabs.get("tabs", []) if isinstance(tabs, dict) else []
        except DriverError:
            tab_list = []
        if not tab_list:
            await asyncio.to_thread(
                self._command, "navigate",
                {"url": "https://chatgpt.com/", "newTab": True,
                 "group_title": "Cortex Bridge"},
            )
            await asyncio.sleep(3)  # let the app shell render the sidebar
        raw = await asyncio.to_thread(self._command, "evaluate", {"code": _CONVERSATIONS_JS})
        if isinstance(raw, dict) and "value" in raw:
            raw = raw["value"]
        try:
            return json.loads(raw) if isinstance(raw, str) else list(raw or [])
        except (json.JSONDecodeError, TypeError) as exc:
            raise DriverError(f"cannot parse conversation list: {exc}") from exc

    async def close_tab(self) -> None:
        await asyncio.to_thread(self._command, "close_tab", {})
