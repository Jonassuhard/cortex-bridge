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
import collections
import inspect
import json
import time
import urllib.error
import urllib.parse
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
SELECTION_TIMEOUT = "SELECTION_TIMEOUT"
SELECTION_FAILED = "SELECTION_FAILED"
SELECTION_SUPERSEDED = "SELECTION_SUPERSEDED"

DEFAULT_SELECTION_BUDGET = 10.0
MAX_CONVERSATIONS = 50

BLOCKER_CODES = {"login": LOGIN_REQUIRED, "captcha": CAPTCHA, "rate_limit": RATE_LIMIT}

DEFAULT_STABILITY_INTERVAL = 2.0  # §13: message stable for 2 seconds
DEFAULT_POST_STREAM_STABILITY_INTERVAL = 5.0
DEFAULT_MAX_WAIT = 300.0  # §13: 5 minutes per ChatGPT response
DEFAULT_POLL_INTERVAL = 0.5
# Thinking models render an EMPTY assistant shell while reasoning, with a
# paint gap between "stop button gone" and the code block being painted.
# An empty assistant message is never final within this grace window; only
# after this many seconds of continuous emptiness is it accepted as a
# genuinely empty reply (which the loop then handles as a violation).
# 120 s: measured live 2026-07-25 — a thinking model painted a trivial
# answer ~50 s after the stop button vanished; 45 s was too short.
DEFAULT_EMPTY_REPLY_GRACE = 120.0

# -- attachments (P3) -------------------------------------------------------------
# Official ChatGPT limits (help.openai.com file-uploads FAQ, 2026-07):
# 512 MB per file, 20 MB per image. Local pre-check; ChatGPT has final say.
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}

# Wait for an attachment chip to appear in/above the composer after an
# upload, and for its progress indicator to disappear. Heuristic by design —
# ChatGPT does not expose a stable testid for this yet.
_ATTACHMENT_WAIT_JS = r"""
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const chipSelectors = [
    '[data-testid*="attachment"]', '[data-testid*="file-chip"]',
    'form img', 'form [role="img"]', '[class*="attachment"]', '[class*="file-chip"]',
  ];
  const progressSelectors = ['[role="progressbar"]', '[class*="progress"]', '[class*="uploading"]'];
  const findChip = () => {
    for (const sel of chipSelectors) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  };
  for (let i = 0; i < 120; i++) {
    const chip = findChip();
    const uploading = progressSelectors.some((sel) => !!document.querySelector(sel));
    if (chip && !uploading) {
      return JSON.stringify({ ok: true, label: (chip.getAttribute('alt') || chip.getAttribute('aria-label') || chip.textContent || '').trim().slice(0, 80) });
    }
    await sleep(500);
  }
  return JSON.stringify({ ok: false, error: 'attachment chip never appeared (60s)' });
})()
"""

# Attach via base64 injection (P3 primary path): the adapter reads the local
# file itself and the page rebuilds a File via DataTransfer — no CDP (the
# extension rejects setFileInputFiles with "Not allowed") and no fetch
# (Chrome Private Network Access blocks HTTPS→loopback fetches). Capped at
# INJECT_MAX_BYTES; larger files need the fetch path.
_ATTACH_B64_JS = r"""
(async (b64, name, mime) => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  try {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const file = new File([bytes], name, { type: mime || 'application/octet-stream' });
    const dt = new DataTransfer();
    dt.items.add(file);
    const input = document.querySelector('form input[type="file"]') || document.querySelector('input[type="file"]');
    if (!input) return JSON.stringify({ ok: false, error: 'file input not found' });
    input.files = dt.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
    await sleep(400);
    return JSON.stringify({ ok: true });
  } catch (e) {
    return JSON.stringify({ ok: false, error: String(e) });
  }
})
"""
INJECT_MAX_BYTES = 10 * 1024 * 1024  # keep evaluate payloads sane (~13 MB b64)

# Attach via fetch + DataTransfer (P3 fallback): Chrome's CDP setFileInputFiles
# is rejected by the WebBridge extension ("Not allowed"), so the page itself
# fetches the bytes from the loopback console and assigns input.files — the
# classic DataTransfer trick, no CDP involved.
_ATTACH_FETCH_JS = r"""
(async (rawUrl, name, mime) => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  try {
    const resp = await fetch(rawUrl);
    if (!resp.ok) return JSON.stringify({ ok: false, error: 'fetch failed: ' + resp.status });
    const buf = await resp.arrayBuffer();
    const file = new File([buf], name, { type: mime || 'application/octet-stream' });
    const dt = new DataTransfer();
    dt.items.add(file);
    const input = document.querySelector('form input[type="file"]') || document.querySelector('input[type="file"]');
    if (!input) return JSON.stringify({ ok: false, error: 'file input not found' });
    input.files = dt.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
    await sleep(400);
    return JSON.stringify({ ok: true });
  } catch (e) {
    return JSON.stringify({ ok: false, error: String(e) });
  }
})
"""

# Send with NO text: attachment-only message — click the armed send button.
_SEND_BARE_JS = r"""
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const findSend = () => document.querySelector('[data-testid="send-button"]')
    || Array.from(document.querySelectorAll('button')).find((b) => /envoyer|send/i.test(b.getAttribute('aria-label') || ''));
  let btn = null;
  for (let i = 0; i < 20 && !btn; i++) { btn = findSend(); if (!btn) await sleep(250); }
  if (!btn) return JSON.stringify({ ok: false, error: 'send button not found' });
  if (btn.disabled) return JSON.stringify({ ok: false, error: 'send button disabled' });
  btn.click();
  await sleep(300);
  return JSON.stringify({ ok: true });
})()
"""

# -- performance instrumentation (P0) -------------------------------------------
# Every WebBridge daemon call is timed into a ring buffer so the console can
# show where latency actually goes (navigate vs evaluate vs send) instead of
# guessing. Loopback-only data; nothing leaves the machine.
_PERF_LOG: "collections.deque[dict]" = collections.deque(maxlen=500)


def _record_perf(session: str, action: str, started: float, ok: bool) -> None:
    _PERF_LOG.append(
        {
            "ts": time.time(),
            "session": session,
            "action": action,
            "ms": round((time.monotonic() - started) * 1000, 1),
            "ok": ok,
        }
    )


def perf_stats(limit: int = 200) -> dict:
    """Recent WebBridge call timings + per-action aggregates (avg / p95 / max)."""
    entries = list(_PERF_LOG)[-limit:]
    by_action: dict[str, list[float]] = {}
    for e in entries:
        by_action.setdefault(e["action"], []).append(e["ms"])
    aggregates = {}
    for action, samples in sorted(by_action.items()):
        samples.sort()
        p95 = samples[min(len(samples) - 1, int(len(samples) * 0.95))]
        aggregates[action] = {
            "count": len(samples),
            "avg_ms": round(sum(samples) / len(samples), 1),
            "p95_ms": round(p95, 1),
            "max_ms": round(samples[-1], 1),
        }
    return {"recent": entries[-50:], "by_action": aggregates}


class TransportError(Exception):
    def __init__(self, code: str, message: str, *, details: dict | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = dict(details or {})


class SelectionTimeoutError(TransportError):
    def __init__(self, message: str):
        super().__init__(
            SELECTION_TIMEOUT,
            message,
            details={"reload_required": True},
        )


def _clean_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _conversation_identity(item: dict) -> str | None:
    identity = _clean_text(item.get("identity"))
    if identity:
        return identity
    url = _clean_text(item.get("url"))
    if not url or "/c/" not in url:
        return None
    identity = url.rsplit("/c/", 1)[-1].split("?", 1)[0].split("#", 1)[0].strip("/")
    return identity or None


def normalize_conversations(
    items: list[dict] | None,
    limit: int = MAX_CONVERSATIONS,
) -> list[dict]:
    """Return stable, truthful, deduplicated conversation metadata."""
    normalized: list[dict] = []
    seen: set[str] = set()
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        identity = _conversation_identity(raw)
        if not identity or identity in seen:
            continue
        seen.add(identity)
        project_id = _clean_text(raw.get("project_id"))
        project_title = _clean_text(raw.get("project_title"))
        message_count = raw.get("message_count")
        if isinstance(message_count, bool) or not isinstance(message_count, int) or message_count < 0:
            message_count = None
        updated_at = _clean_text(raw.get("updated_at")) or _clean_text(raw.get("timestamp"))
        url = _clean_text(raw.get("url")) or f"https://chatgpt.com/c/{identity}"
        normalized.append({
            "identity": identity,
            "url": url,
            "title": _clean_text(raw.get("title")) or "Conversation",
            "pinned": bool(raw.get("pinned")),
            "project": bool(project_id or project_title),
            "project_id": project_id,
            "project_title": project_title,
            "updated_at": updated_at,
            "timestamp": updated_at,
            "preview": _clean_text(raw.get("preview")),
            "message_count": message_count,
            "unread": raw.get("unread") if isinstance(raw.get("unread"), int) else 0,
            "archived": bool(raw.get("archived")),
            "status": _clean_text(raw.get("status")) or "idle",
        })
        if len(normalized) >= max(0, limit):
            break
    return normalized


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
    visible_lines = [
        line.strip()
        for line in str(message.get("text", "")).splitlines()
        if line.strip()
    ]
    visible_protocol_label = (
        visible_lines[0]
        if len(blocks) == 1
        and visible_lines
        and visible_lines[0] in {"cortex-decision", "cortex-report"}
        else ""
    )
    rebuilt = []
    for block in blocks:
        language = str(block.get("lang") or "").strip() or visible_protocol_label
        rebuilt.append(f"```{language}\n{block.get('text', '')}\n```")
    return "\n".join(rebuilt)


class ChatGPTWebTransport:
    """§7.1 transport: select/lock one conversation, send, await, extract."""

    def __init__(
        self,
        driver,
        *,
        stability_interval: float = DEFAULT_STABILITY_INTERVAL,
        max_wait: float = DEFAULT_MAX_WAIT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        empty_reply_grace: float = DEFAULT_EMPTY_REPLY_GRACE,
        selection_budget: float = DEFAULT_SELECTION_BUDGET,
        post_stream_stability_interval: float = DEFAULT_POST_STREAM_STABILITY_INTERVAL,
    ):
        self.driver = driver
        self.stability_interval = stability_interval
        self.post_stream_stability_interval = post_stream_stability_interval
        self.max_wait = max_wait
        self.poll_interval = poll_interval
        self.empty_reply_grace = empty_reply_grace
        self.selection_budget = selection_budget
        self.lock: ConversationLock | None = None
        self.paused = False
        self.pause_reason: str | None = None
        self.delivery_uncertain = False
        self.streaming_observed = False
        self._extracted_ids: set[str] = set()
        self._baseline: set[str] = set()
        self._cancel_requested = False
        self._pending_new_chat = False
        self._selection_generation = 0

    async def close(self) -> None:
        """Release the logical browser page owned by this transport."""
        closer = getattr(self.driver, "close", None)
        if closer is not None:
            await closer()

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
        return normalize_conversations(await self.driver.list_conversations())

    async def probe(self) -> dict:
        """Read-only DOM health check: which adaptive selector currently
        matches each role, plus diagnostics. Fixture drivers have no DOM,
        so probing is only available on the live WebBridge driver."""
        probe = getattr(self.driver, "probe", None)
        if probe is None:
            return {"ok": False, "error": "driver does not support probing",
                    "failures": ["unsupported-driver"], "warnings": []}
        return await probe()

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SelectionTimeoutError("conversation selection exceeded its absolute budget")
        return remaining

    async def _selection_await(self, awaitable, deadline: float):
        try:
            return await asyncio.wait_for(awaitable, timeout=self._remaining(deadline))
        except asyncio.TimeoutError as exc:
            raise SelectionTimeoutError(
                "conversation selection exceeded its absolute budget"
            ) from exc

    def _assert_current_selection(self, generation: int) -> None:
        if generation != self._selection_generation:
            raise TransportError(
                SELECTION_SUPERSEDED,
                "a newer conversation selection superseded this one",
                details={"reload_required": False},
            )

    async def _await_conversation(
        self,
        want_identity: str | None,
        timeout: float = 25.0,
        *,
        deadline: float | None = None,
    ) -> dict:
        """Poll until the SPA actually shows the requested conversation.

        Navigation resolves before chatgpt.com finishes its client-side
        route change — a single immediate state read can still show the
        PREVIOUS conversation and cause a false CONVERSATION_MISMATCH."""
        poll_deadline = deadline if deadline is not None else time.monotonic() + timeout
        state: dict = {}
        while time.monotonic() < poll_deadline:
            state = await self._state(deadline=deadline)
            identity = state.get("conversation_id")
            if want_identity is None:
                if identity:
                    return state
            elif identity == want_identity:
                return state
            if deadline is not None:
                await self._selection_await(
                    asyncio.sleep(min(self.poll_interval, self._remaining(deadline))),
                    deadline,
                )
            else:
                await asyncio.sleep(self.poll_interval)
        return state

    async def select_conversation(
        self,
        url: str,
        *,
        budget: float | None = None,
        _force_reload: bool = False,
    ) -> ConversationLock:
        """Navigate to a user-chosen conversation and lock the mission to it.

        P0: prefer an in-app SPA switch (sidebar link click, no page reload)
        when the driver supports it; fall back to full navigation."""
        selection_budget = self.selection_budget if budget is None else budget
        if selection_budget <= 0:
            raise SelectionTimeoutError("conversation selection budget must be positive")
        deadline = time.monotonic() + selection_budget
        self._selection_generation += 1
        generation = self._selection_generation
        want = url.rsplit("/c/", 1)[-1] if "/c/" in url else None
        if hasattr(self.driver, "selection_used_full_navigation"):
            self.driver.selection_used_full_navigation = False
        spa_nav = getattr(self.driver, "spa_navigate", None)
        spa_done = False
        if want and spa_nav is not None and not _force_reload:
            try:
                spa_done = bool(await self._selection_await(spa_nav(url), deadline))
            except SelectionTimeoutError:
                raise
            except Exception as exc:
                raise TransportError(
                    SELECTION_FAILED,
                    f"in-app conversation selection failed: {exc}",
                    details={"reload_required": True},
                ) from exc
            if not spa_done:
                raise TransportError(
                    SELECTION_FAILED,
                    "in-app conversation selection failed",
                    details={"reload_required": True},
                )
        self._assert_current_selection(generation)
        if not spa_done:
            await self._selection_await(self.driver.navigate(url), deadline)
        self._assert_current_selection(generation)
        state = await self._await_conversation(want, deadline=deadline)
        self._assert_current_selection(generation)
        # A hard navigation can expose the final /c/<id> URL before React has
        # mounted the composer. Identity alone is therefore insufficient for
        # a writer session: wait inside the same absolute selection budget so
        # the following send cannot race into COMPOSER_MISSING. This is a
        # readiness poll, not the heavier SPA content-stability loop below.
        if (
            want
            and state.get("conversation_id") == want
            and getattr(self.driver, "selection_used_full_navigation", False)
            and not state.get("composer_present")
            and not state.get("blocker")
        ):
            while not state.get("composer_present"):
                await self._selection_await(
                    asyncio.sleep(min(self.poll_interval, self._remaining(deadline))),
                    deadline,
                )
                state = await self._state(deadline=deadline)
                self._assert_current_selection(generation)
                if state.get("conversation_id") != want:
                    continue
        # SPA route change updates the URL BEFORE the message DOM is replaced:
        # identity already matches while the old conversation's messages are
        # still painted, and a stable empty skeleton appears while the new one
        # loads (both observed live 2026-07-25). An existing /c/ conversation
        # always has >= 1 message, so require: identity match AND messages
        # present AND two identical consecutive LIGHT reads — before locking.
        if (
            want
            and state.get("conversation_id") == want
            and getattr(self.driver, "requires_content_stability", True)
            and not getattr(self.driver, "selection_used_full_navigation", False)
        ):
            def _sig(s: dict) -> tuple:
                return (
                    s.get("conversation_id"),
                    s.get("title"),
                    s.get("message_count"),
                    s.get("first_id"),
                )

            stable_deadline = min(deadline, time.monotonic() + 3.0)
            loaded_since: float | None = None
            previous = _sig(await self._light_state(deadline=deadline))
            while time.monotonic() < stable_deadline:
                await self._selection_await(asyncio.sleep(0.4), deadline)
                light = await self._light_state(deadline=deadline)
                current = _sig(light)
                loaded = (
                    current[0] == want
                    and (current[2] or 0) > 0
                    and current[1] not in (None, "", "ChatGPT")
                )
                if loaded and current == previous:
                    break  # two identical light reads — content settled
                if loaded and loaded_since is None:
                    loaded_since = time.monotonic()
                if loaded_since is not None and time.monotonic() - loaded_since > 1.2:
                    break  # clearly loaded; virtualized threads never fully stabilize
                previous = current
            state = await self._state(deadline=deadline)
        self._remaining(deadline)
        self._assert_current_selection(generation)
        identity = state.get("conversation_id")
        if not identity:
            raise TransportError(NO_CONVERSATION, f"no conversation at {url}")
        self.lock = ConversationLock(url, identity, state.get("title"), time.time())
        self._baseline = {m["id"] for m in state.get("messages", []) if m["role"] == "assistant"}
        return self.lock

    async def recover_selection_with_reload(
        self,
        url: str,
        *,
        budget: float | None = None,
    ) -> ConversationLock:
        """Explicit operator-approved recovery path using full navigation."""
        return await self.select_conversation(
            url,
            budget=self.selection_budget if budget is None else budget,
            _force_reload=True,
        )

    async def attach(self, lock: ConversationLock) -> None:
        """Re-attach to a previously locked conversation (e.g. after a
        browser restart). Identity must match — never falls back to whatever
        tab happens to be focused (§8)."""
        await self.driver.navigate(lock.url)
        state = await self._await_conversation(lock.identity)
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
        try:
            await self.driver.navigate(url)
        except TabClosedError as exc:
            raise TransportError(
                TAB_CLOSED,
                "new conversation tab closed before delivery",
                details={"reload_required": True},
            ) from exc
        except DriverError as exc:
            driver_code = getattr(exc, "code", None)
            details = {"reload_required": True}
            if driver_code:
                details["driver_code"] = driver_code
            raise TransportError(
                SELECTION_FAILED,
                f"new conversation navigation failed: {exc}",
                details=details,
            ) from exc
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
        # Short grace poll: SPA re-renders can briefly report the previous
        # route; a real mismatch (user switched chats) persists.
        state = await self._await_conversation(self.lock.identity, timeout=8.0)
        if state.get("conversation_id") != self.lock.identity:
            self.pause(CONVERSATION_MISMATCH)
            raise ConversationMismatch(
                f"page shows {state.get('conversation_id')!r}, locked to {self.lock.identity!r}"
            )

    # -- internal state access with blocker/tab handling --------------------------------

    async def _state(self, *, deadline: float | None = None) -> dict:
        try:
            if deadline is None:
                state = await self.driver.get_state()
            else:
                state = await self._selection_await(self.driver.get_state(), deadline)
        except TabClosedError as exc:
            self.pause(TAB_CLOSED)
            raise TransportError(TAB_CLOSED, "browser tab was closed") from exc
        except DriverError as exc:
            driver_code = getattr(exc, "code", None)
            raise TransportError(
                STATE_UNREADABLE,
                str(exc),
                details={"driver_code": driver_code} if driver_code else None,
            ) from exc
        blocker = state.get("blocker")
        if blocker:
            self.pause(BLOCKER_CODES.get(blocker, blocker.upper()))
            raise BlockerDetected(blocker)
        return state

    async def _light_state(self, *, deadline: float | None = None) -> dict:
        """Cheap poll read when the driver supports it (P0c); fixture drivers
        fall back to a full state mapped onto the light shape."""
        getter = getattr(self.driver, "get_light_state", None)
        if getter is not None:
            try:
                if deadline is None:
                    return await getter()
                return await self._selection_await(getter(), deadline)
            except TabClosedError as exc:
                self.pause(TAB_CLOSED)
                raise TransportError(TAB_CLOSED, "browser tab was closed") from exc
        s = await self._state(deadline=deadline)
        msgs = s.get("messages") or []
        return {
            "url": s.get("url"),
            "conversation_id": s.get("conversation_id"),
            "title": s.get("title"),
            "message_count": len(msgs),
            "first_id": msgs[0].get("id") if msgs else None,
            "last_id": msgs[-1].get("id") if msgs else None,
            "streaming": bool(s.get("streaming")),
            "composer_present": bool(s.get("composer_present")),
        }

    # -- sending (§7.1) ----------------------------------------------------------------------

    async def send_with_attachment(
        self,
        text: str | None,
        path: str,
        *,
        image: bool,
        raw_url: str | None = None,
        mime: str | None = None,
        name: str | None = None,
    ) -> dict:
        """Attach a local file/image to the composer, then send (P3).

        Flow: verify lock → attach (CDP upload first, fetch+DataTransfer
        fallback through raw_url) → wait for the attachment chip → send with
        text, or bare-send for an attachment-only message."""
        if self.delivery_uncertain:
            raise TransportError(
                DELIVERY_UNCERTAIN,
                "previous delivery is uncertain; refusing to resend — resolve first",
            )
        if self.paused:
            raise TransportError(
                TRANSPORT_PAUSED, f"transport paused ({self.pause_reason}); resume first"
            )
        uploader = getattr(self.driver, "upload_files", None)
        if uploader is None:
            raise TransportError("ATTACHMENTS_UNSUPPORTED", "this driver cannot upload files")
        await self.verify_lock()
        # The composer form input accepts everything (images included). The
        # standalone image/* inputs belong to other features and CDP rejects
        # them with "Not allowed" (verified live 2026-07-25).
        selector = 'form input[type="file"]'
        attached = False
        try:
            named_uploader = getattr(self.driver, "upload_files_named", None)
            if name and callable(named_uploader):
                await named_uploader(selector, [path], name)
            else:
                await uploader(selector, [path])
            attached = True
        except DriverError as cdp_exc:
            if getattr(self.driver, "supports_raw_evaluation", True) is False:
                raise TransportError(
                    "ATTACHMENT_FAILED",
                    f"structured upload rejected: {cdp_exc}",
                ) from cdp_exc
            # Primary fallback: base64 injection — no CDP, no network.
            import base64
            import mimetypes
            import os
            effective_mime = mime or mimetypes.guess_type(path)[0] or "application/octet-stream"
            effective_name = name or os.path.basename(path)
            size = os.path.getsize(path)
            if size <= INJECT_MAX_BYTES:
                with open(path, "rb") as fh:
                    b64 = base64.b64encode(fh.read()).decode("ascii")
                code = f"{_ATTACH_B64_JS}({json.dumps(b64)}, {json.dumps(effective_name)}, {json.dumps(effective_mime)})"
            elif raw_url:
                code = f"{_ATTACH_FETCH_JS}({json.dumps(raw_url)}, {json.dumps(effective_name)}, {json.dumps(effective_mime)})"
            else:
                raise TransportError("ATTACHMENT_FAILED", f"upload rejected: {cdp_exc}") from cdp_exc
            raw = await self.driver.evaluate(code, timeout=90)
            if isinstance(raw, dict) and "value" in raw:
                raw = raw["value"]
            result = json.loads(raw) if isinstance(raw, str) else (raw or {})
            if not result.get("ok"):
                raise TransportError(
                    "ATTACHMENT_FAILED",
                    f"CDP rejected ({cdp_exc}); injection failed: {result.get('error')}",
                )
            attached = True
        if not attached:  # pragma: no cover - defensive
            raise TransportError("ATTACHMENT_FAILED", "attachment could not be staged")
        chip = await self.driver.await_attachment()
        if not chip.get("ok"):
            raise TransportError("ATTACHMENT_FAILED", chip.get("error", "attachment never appeared"))
        if text and text.strip():
            return await self.send_message(text)
        result = await self.driver.send_bare()
        if not result.get("ok"):
            self.delivery_uncertain = True
            self.pause(DELIVERY_UNCERTAIN)
            raise TransportError(DELIVERY_UNCERTAIN, f"bare send failed: {result.get('error')}")
        return {"sent": True, "attachment": chip.get("label")}

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
        user_ids_before = {m["id"] for m in state.get("messages", []) if m["role"] == "user"}
        try:
            await self.driver.send_message(text)
        except DriverError as exc:
            self.delivery_uncertain = True
            self.pause(DELIVERY_UNCERTAIN)
            raise TransportError(DELIVERY_UNCERTAIN, f"send may have failed: {exc}") from exc
        # The SPA takes a moment to render the sent user message — poll for it.
        # Marker: first substantial content line. ChatGPT's markdown consumes
        # the leading ``` fence AND its language label, so neither can serve
        # as the marker; the JSON body stays visible inside the code block.
        marker = ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("```") or len(stripped) < 8:
                continue
            marker = stripped[:60]
            break
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
                if m["role"] == "user"
                and m["id"] not in user_ids_before
                and marker in (
                    m.get("text", "")
                    + " ".join(b.get("text", "") for b in m.get("code_blocks", []))
                )
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

    async def snapshot(self, *, verify_lock: bool = True) -> dict:
        """Return the current sanitized page state for the locked conversation.

        This is the read-only surface used by the localhost conversation client.
        It deliberately goes through the same blocker detection as mission traffic.
        """
        if verify_lock and not self._pending_new_chat:
            await self.verify_lock()
        return await self._state()

    async def stream_response(self, on_update=None) -> dict:
        """Wait for the next assistant response and optionally mirror visible text.

        ``on_update`` receives a dictionary whenever the latest visible assistant
        content or streaming state changes. It may be synchronous or async. The
        completion rules stay identical to :meth:`await_response`.

        Completion requires ALL of: stop button gone, no streaming indicator,
        latest new assistant content (text AND code blocks) unchanged for the
        stability interval, and — outside the empty-reply grace window — a
        non-empty message (thinking models paint an empty shell first).
        On timeout: pause safely with CHATGPT_RESPONSE_TIMEOUT; never resend
        automatically.
        """
        if self.paused:
            raise TransportError(
                TRANSPORT_PAUSED, f"transport paused ({self.pause_reason}); resume first"
            )
        deadline = time.monotonic() + self.max_wait
        last_sig: str | None = None
        last_emit: tuple | None = None
        stable_since: float | None = None
        empty_since: float | None = None
        final_paint_requested = False

        async def emit(payload: dict) -> None:
            if on_update is None:
                return
            result = on_update(payload)
            if inspect.isawaitable(result):
                await result

        while time.monotonic() < deadline:
            if self._cancel_requested:
                self._cancel_requested = False
                raise TransportError(GENERATION_CANCELLED, "generation cancelled by user")
            state = await self._state()
            # Fast mismatch detection: a human (or another tab action) may
            # yank the page away while we wait — fail in seconds, not after
            # the full response timeout.
            if (
                self.lock is not None
                and not self._pending_new_chat
                and state.get("conversation_id") != self.lock.identity
            ):
                self.pause(CONVERSATION_MISMATCH)
                raise ConversationMismatch(
                    f"page shows {state.get('conversation_id')!r}, locked to {self.lock.identity!r}"
                )
            is_streaming = bool(state.get("stop_button_present") or state.get("streaming"))
            if is_streaming:
                self.streaming_observed = True
                stable_since = None
                empty_since = None
            elif (
                self.streaming_observed
                and not final_paint_requested
                and getattr(self.driver, "requires_content_stability", True)
            ):
                focus_tab = getattr(self.driver, "focus_tab", None)
                if focus_tab is not None:
                    await focus_tab()
                    final_paint_requested = True
                    last_sig = None
                    stable_since = None
                    await asyncio.sleep(self.poll_interval)
                    continue
            new_msgs = [
                m
                for m in state.get("messages", [])
                if m["role"] == "assistant" and m["id"] not in self._baseline
            ]
            if new_msgs:
                latest = new_msgs[-1]
                emit_key = (latest.get("id"), latest.get("text", ""), is_streaming)
                if emit_key != last_emit:
                    await emit({
                        "id": latest.get("id"),
                        "role": "assistant",
                        "text": latest.get("text", ""),
                        "code_blocks": latest.get("code_blocks", []),
                        "images": latest.get("images", []),
                        "streaming": is_streaming,
                    })
                    last_emit = emit_key
                if not is_streaming:
                    now = time.monotonic()
                    # Stability signature: visible text + code block contents
                    # (thinking models stream into the CodeMirror block after
                    # the prose, and the prose can be empty throughout).
                    sig = (latest.get("text") or "") + "\x00" + "\x00".join(
                        (b.get("text") or "") for b in (latest.get("code_blocks") or [])
                    )
                    if not sig.strip("\x00"):
                        # Empty assistant shell: never final within the grace
                        # window — the model is very likely still reasoning or
                        # the renderer has not painted the code block yet.
                        empty_since = empty_since if empty_since is not None else now
                        if now - empty_since < self.empty_reply_grace:
                            last_sig = None
                            stable_since = None
                            await asyncio.sleep(self.poll_interval)
                            continue
                        # else: genuinely empty reply — fall through so the
                        # loop can record its usual protocol violation.
                    else:
                        empty_since = None
                    if sig == last_sig:
                        stable_since = stable_since if stable_since is not None else now
                        required_stability = (
                            self.post_stream_stability_interval
                            if (
                                self.streaming_observed
                                and getattr(self.driver, "requires_content_stability", True)
                            )
                            else self.stability_interval
                        )
                        if now - stable_since >= required_stability:
                            if latest["id"] in self._extracted_ids:
                                raise TransportError(
                                    DUPLICATE_EXTRACTION,
                                    f"message {latest['id']} was already extracted",
                                )
                            self._extracted_ids.add(latest["id"])
                            final = {
                                "id": latest["id"],
                                "role": "assistant",
                                "text": latest.get("text", ""),
                                "protocol_text": protocol_text(latest),
                                "code_blocks": latest.get("code_blocks", []),
                                "images": latest.get("images", []),
                            }
                            await emit({**final, "streaming": False, "stable": True})
                            return final
                    else:
                        last_sig = sig
                        stable_since = None
            await asyncio.sleep(self.poll_interval)
        self.pause(CHATGPT_RESPONSE_TIMEOUT)
        raise TransportError(
            CHATGPT_RESPONSE_TIMEOUT,
            f"no completed response within {self.max_wait}s; mission paused",
        )

    async def await_response(self) -> dict:
        """Wait for the next stable assistant response without a streaming callback."""
        return await self.stream_response()

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

    requires_content_stability = False

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def _fetch(url: str) -> None:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                resp.read()
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise DriverError(f"GET {url} -> {code}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise DriverError(f"GET {url} failed: {exc}") from exc

    @staticmethod
    def _get(url: str) -> dict:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise DriverError(f"GET {url} -> {code}") from exc
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
            code = exc.code
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:200]
            finally:
                exc.close()
            raise DriverError(f"POST {url} -> {code} {detail}") from exc
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

# Adaptive selector candidates, tried in order; the first match wins and is
# reported back (state["selectors"]) so the console/probe can show which
# selector the live UI currently honors. Fallbacks exist so a ChatGPT UI
# refresh degrades gracefully instead of breaking silently.
_STATE_JS = r"""
(() => {
  const q = (sel) => { try { return document.querySelector(sel); } catch (e) { return null; } };
  const qAll = (sel) => { try { return Array.from(document.querySelectorAll(sel)); } catch (e) { return []; } };
  const COMPOSER_CANDIDATES = ['#prompt-textarea', 'div[contenteditable="true"][role="textbox"]', 'div[contenteditable="true"]', 'form textarea'];
  const MESSAGE_CANDIDATES = ['[data-message-author-role]', 'article[data-testid^="conversation-turn"]', 'main article'];
  const STOP_CANDIDATES = ['[data-testid="stop-button"]', 'button[aria-label*="Stop"]', 'button[aria-label*="Arr"]'];
  const first = (cands) => { for (const c of cands) { if (q(c)) return c; } return null; };
  const text = document.body ? document.body.innerText.slice(0, 8000) : '';
  const composerSel = first(COMPOSER_CANDIDATES);
  const composer = composerSel ? q(composerSel) : null;
  const isLoginControl = (el) => {
    const testid = (el.getAttribute('data-testid') || '').trim();
    const label = ((el.getAttribute('aria-label') || '') + ' ' + (el.textContent || ''))
      .replace(/\s+/g, ' ').trim();
    return /(^|[-_])(login|sign[-_]?up)([-_]|$)/i.test(testid)
      || /^(login|log in|sign up|se connecter|connexion|s['’]inscrire|créer un compte)$/i.test(label);
  };
  const loginControl = qAll('a, button').find(isLoginControl);
  // Blockers (conservative; see docs/phase5-dom-contract.md §f):
  let blocker = null;
  if (loginControl || (!composer && /log in|sign up|se connecter|inscrivez-vous/i.test(text))) blocker = 'login';
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
  const messageSel = first(MESSAGE_CANDIDATES);
  const messages = (messageSel ? qAll(messageSel) : []).map((el, i) => {
    const blocks = Array.from(el.querySelectorAll('pre.cm-content')).map((pre) => {
      const t = pre.textContent || '';
      return { lang: sniffLang(t), text: t };
    });
    const images = Array.from(el.querySelectorAll('img')).map((img) => ({
      src: img.currentSrc || img.src || '',
      alt: img.alt || '',
    })).filter((img) => img.src && !img.src.startsWith('data:image/svg'));
    const timeEl = el.querySelector('time');
    return {
      id: el.getAttribute('data-message-id') || ('idx-' + i),
      role: el.getAttribute('data-message-author-role') || null,
      text: el.textContent || '',
      code_blocks: blocks,
      images: images,
      created_at: timeEl ? (timeEl.getAttribute('datetime') || timeEl.textContent || '').trim() : null,
    };
  });
  const stopSel = first(STOP_CANDIDATES);
  const stop = stopSel ? q(stopSel) : null;
  const streaming = !!stop || !!q('.result-streaming');
  const modelButton = q('[data-testid="model-switcher-dropdown-button"]')
    || Array.from(document.querySelectorAll('button')).find((b) => /GPT|ChatGPT|mod[eè]le|model/i.test((b.textContent || '') + ' ' + (b.getAttribute('aria-label') || '')));
  return JSON.stringify({
    url: location.href,
    conversation_id: convMatch ? convMatch[1] : null,
    title: document.title,
    blocker: blocker,
    composer_present: !!composer,
    send_button_present: !!composer,
    stop_button_present: !!stop,
    streaming: streaming,
    model_label: modelButton ? (modelButton.textContent || modelButton.getAttribute('aria-label') || '').trim() : null,
    messages: messages,
    selectors: { composer: composerSel, messages: messageSel, stop: stopSel },
  });
})()
"""

_CONVERSATIONS_JS = r"""
(async () => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const normalize = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const collect = (seen) => {
    for (const a of document.querySelectorAll('nav a[href^="/c/"], aside a[href^="/c/"]')) {
      const href = a.getAttribute('href') || '';
      const match = href.match(/\/c\/([A-Za-z0-9-]+)/);
      if (!match) continue;
      const row = a.closest('li, [data-testid*="conversation"], [class*="group"]') || a.parentElement || a;
      const lines = (a.innerText || a.textContent || '').split(/\n+/).map(normalize).filter(Boolean);
      const title = normalize(a.getAttribute('title')) || lines[0] || 'Conversation';
      const timeEl = row.querySelector ? row.querySelector('time') : null;
      const timestamp = timeEl ? normalize(timeEl.getAttribute('datetime') || timeEl.textContent) : '';
      const preview = lines.find((line, index) => index > 0 && line !== timestamp && line !== title) || title;
      const labels = normalize((row.getAttribute && row.getAttribute('aria-label')) || '') + ' ' + normalize(row.textContent);
      const numericBadge = row.querySelector ? Array.from(row.querySelectorAll('[aria-label], [data-testid], span')).find((el) => {
        const value = normalize(el.textContent);
        return /^\d+$/.test(value) && /unread|non lu|new|nouveau/i.test((el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('data-testid') || ''));
      }) : null;
      const unread = numericBadge ? Number(normalize(numericBadge.textContent)) : (/unread|non lu/i.test(labels) ? 1 : 0);
      const pinned = /pinned|épingl|epingle/i.test(labels);
      // Best-effort project detection: a chat nested inside a folder row
      // (li > ul > chat link) belongs to a ChatGPT project; top-level links
      // (Recents/Pinned sections) are plain chats.
      const parentUl = a.closest('ul');
      const project = !!(parentUl && parentUl.closest('li'));
      const current = location.pathname === href || a.getAttribute('aria-current') === 'page';
      seen.set(match[1], {
        url: 'https://chatgpt.com' + href,
        identity: match[1],
        title,
        preview,
        timestamp,
        unread,
        pinned,
        project,
        status: current ? 'idle' : undefined,
      });
    }
  };
  const seen = new Map();
  const links = Array.from(document.querySelectorAll('nav a[href^="/c/"], aside a[href^="/c/"]'));
  let container = links[0]?.closest('[class*="overflow"], nav, aside') || null;
  collect(seen);
  let unchanged = 0;
  let previous = seen.size;
  for (let i = 0; i < 40 && container; i++) {
    const before = container.scrollTop;
    container.scrollTop = Math.min(container.scrollHeight, container.scrollTop + Math.max(320, container.clientHeight * .8));
    await sleep(160);
    collect(seen);
    if (seen.size === previous && container.scrollTop === before) unchanged += 1;
    else unchanged = 0;
    previous = seen.size;
    if (unchanged >= 3 || container.scrollTop + container.clientHeight >= container.scrollHeight - 4) break;
  }
  if (container) container.scrollTop = 0;
  // Sidebar order is recency order: keep the 50 most recent conversations.
  return JSON.stringify(Array.from(seen.values()).slice(0, 50));
})()
"""

# Light state (P0c): identity + counts + edge ids WITHOUT serializing message
# text. ~10x cheaper than _STATE_JS on long conversations; used for polling,
# lock verification and switch stability. Full reads stay for extraction.
_LIGHT_STATE_JS = r"""
(() => {
  const msgs = document.querySelectorAll('[data-message-author-role]');
  const first = msgs[0] || null;
  const last = msgs[msgs.length - 1] || null;
  const stopBtn = document.querySelector('[data-testid="stop-button"]')
    || Array.from(document.querySelectorAll('button')).find((b) => /stop|arrêter|arreter/i.test(b.getAttribute('aria-label') || ''));
  return JSON.stringify({
    url: location.href,
    conversation_id: (location.pathname.match(/\/c\/([^/?#]+)/) || [null, null])[1],
    title: document.title,
    message_count: msgs.length,
    first_id: first ? first.getAttribute('data-message-id') : null,
    last_id: last ? last.getAttribute('data-message-id') : null,
    streaming: !!stopBtn,
    composer_present: !!document.querySelector('#prompt-textarea, [contenteditable="true"]'),
  });
})()
"""

# In-app conversation switch (P0): clicking the sidebar link triggers the
# chatgpt.com SPA router — NO full page reload (2-10x faster than navigate).
# Falls back to a real navigation when the link is not rendered.
_SPA_NAV_JS = r"""
(async (targetUrl) => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const realClick = (el) => {
    const r = el.getBoundingClientRect();
    const opts = { bubbles: true, cancelable: true, clientX: r.x + r.width / 2, clientY: r.y + r.height / 2, button: 0, pointerType: 'mouse' };
    el.dispatchEvent(new PointerEvent('pointerdown', opts));
    el.dispatchEvent(new MouseEvent('mousedown', opts));
    el.dispatchEvent(new PointerEvent('pointerup', opts));
    el.dispatchEvent(new MouseEvent('mouseup', opts));
    el.dispatchEvent(new MouseEvent('click', opts));
  };
  const want = (targetUrl.split('/c/')[1] || '').split(/[?#]/)[0];
  if (!want || !/chatgpt\.com$/.test(location.hostname)) {
    return JSON.stringify({ ok: false, reason: 'no_app' });
  }
  const findLink = () => {
    const links = Array.from(document.querySelectorAll('nav a[href^="/c/"], aside a[href^="/c/"]'));
    return links.find((a) => (a.getAttribute('href') || '').includes('/c/' + want));
  };
  let link = findLink();
  // The sidebar renders lazily — scroll to load older entries before giving up.
  const first = document.querySelector('nav a[href^="/c/"], aside a[href^="/c/"]');
  const container = first ? (first.closest('[class*="overflow"]') || first.closest('nav') || first.closest('aside')) : null;
  for (let i = 0; i < 12 && !link && container; i++) {
    container.scrollTop = Math.min(container.scrollHeight, container.scrollTop + Math.max(320, container.clientHeight * .8));
    await sleep(150);
    link = findLink();
  }
  if (!link) return JSON.stringify({ ok: false, reason: 'not_in_sidebar' });
  realClick(link);
  await sleep(250);
  return JSON.stringify({ ok: true, clicked: true });
})
"""

# Verified against real chatgpt.com (2026-07-25, FR UI, Radix composer pill):
#  - The switcher is a `button.__composer-pill` whose text is the current model
#    ("Pro", "Instantanée") — no data-testid, no "GPT" in the label.
#  - Radix menus ignore plain `.click()`: a pointerdown/mousedown/pointerup/
#    mouseup/click sequence is required to open them.
#  - Open menu items carry role menuitem / menuitemradio / option.
#  - After a fresh navigate the pill renders late: poll for it (like _SEND_JS
#    polls for the composer) instead of failing immediately.
_MODELS_JS = r"""
(async () => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const realClick = (el) => {
    const r = el.getBoundingClientRect();
    const opts = { bubbles: true, cancelable: true, clientX: r.x + r.width / 2, clientY: r.y + r.height / 2, button: 0, pointerType: 'mouse' };
    el.dispatchEvent(new PointerEvent('pointerdown', opts));
    el.dispatchEvent(new MouseEvent('mousedown', opts));
    el.dispatchEvent(new PointerEvent('pointerup', opts));
    el.dispatchEvent(new MouseEvent('mouseup', opts));
    el.dispatchEvent(new MouseEvent('click', opts));
  };
  const findSwitcher = () => {
    const buttons = Array.from(document.querySelectorAll('button'));
    return document.querySelector('[data-testid="model-switcher-dropdown-button"]')
      || buttons.find((b) => (b.className || '').includes('__composer-pill') && (b.textContent || '').trim())
      || buttons.find((b) => /model|modèle|GPT|ChatGPT/i.test((b.getAttribute('aria-label') || '') + ' ' + (b.textContent || '')));
  };
  let switcher = null;
  for (let i = 0; i < 50 && !switcher; i++) {
    switcher = findSwitcher();
    if (!switcher) await sleep(200);
  }
  if (!switcher) return JSON.stringify({ current: null, models: [], error: 'model switcher not found' });
  const current = (switcher.textContent || switcher.getAttribute('aria-label') || '').trim();
  realClick(switcher);
  await sleep(450);
  const candidates = Array.from(document.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="option"], [data-testid*="model"], [data-radix-collection-item]'));
  const labels = [];
  for (const el of candidates) {
    const text = (el.textContent || '').replace(/\s+/g, ' ').trim();
    if (!text || text.length > 120) continue;
    if (/model|GPT|ChatGPT|o\d|mini|pro|thinking|instant|sol|moyenne|élev/i.test(text)) labels.push(text);
  }
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  return JSON.stringify({ current, models: Array.from(new Set(labels)).slice(0, 30), error: null });
})()
"""

_SELECT_MODEL_JS = r"""
(async (label) => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const realClick = (el) => {
    const r = el.getBoundingClientRect();
    const opts = { bubbles: true, cancelable: true, clientX: r.x + r.width / 2, clientY: r.y + r.height / 2, button: 0, pointerType: 'mouse' };
    el.dispatchEvent(new PointerEvent('pointerdown', opts));
    el.dispatchEvent(new MouseEvent('mousedown', opts));
    el.dispatchEvent(new PointerEvent('pointerup', opts));
    el.dispatchEvent(new MouseEvent('mouseup', opts));
    el.dispatchEvent(new MouseEvent('click', opts));
  };
  const findSwitcher = () => {
    const buttons = Array.from(document.querySelectorAll('button'));
    return document.querySelector('[data-testid="model-switcher-dropdown-button"]')
      || buttons.find((b) => (b.className || '').includes('__composer-pill') && (b.textContent || '').trim())
      || buttons.find((b) => /model|modèle|GPT|ChatGPT/i.test((b.getAttribute('aria-label') || '') + ' ' + (b.textContent || '')));
  };
  let switcher = null;
  for (let i = 0; i < 50 && !switcher; i++) {
    switcher = findSwitcher();
    if (!switcher) await sleep(200);
  }
  if (!switcher) return JSON.stringify({ ok: false, error: 'model switcher not found' });
  realClick(switcher);
  await sleep(450);
  const candidates = Array.from(document.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="option"], [data-testid*="model"], [data-radix-collection-item]'));
  const normalized = label.replace(/\s+/g, ' ').trim().toLowerCase();
  const target = candidates.find((el) => (el.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase() === normalized)
    || candidates.find((el) => (el.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase().includes(normalized));
  if (!target) {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    return JSON.stringify({ ok: false, error: 'requested model not visible' });
  }
  realClick(target);
  await sleep(800);
  // React re-renders the pill after selection: the old `switcher` reference is
  // detached and still shows the previous label. Re-query the live switcher.
  const after = findSwitcher();
  const visible = ((after && (after.textContent || after.getAttribute('aria-label'))) || '').replace(/\s+/g, ' ').trim();
  const ok = visible.toLowerCase().includes(normalized) || normalized.includes(visible.toLowerCase());
  return JSON.stringify({ ok, selected: visible, error: ok ? null : 'selection could not be confirmed' });
})
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
  // Adaptive composer candidates (same list as _STATE_JS): first match wins.
  const COMPOSER_CANDIDATES = ['#prompt-textarea', 'div[contenteditable="true"][role="textbox"]', 'div[contenteditable="true"]', 'form textarea'];
  const findComposer = () => {
    for (const c of COMPOSER_CANDIDATES) {
      try { const el = document.querySelector(c); if (el) return el; } catch (e) {}
    }
    return null;
  };
  // The SPA may still be rendering when we land — wait for the composer.
  let composer = null;
  for (let i = 0; i < 50 && !composer; i++) {
    composer = findComposer();
    if (!composer) await sleep(200);
  }
  if (!composer) return JSON.stringify({ ok: false, error: 'composer not found' });
  const isTextarea = composer.tagName === 'TEXTAREA' || composer.tagName === 'INPUT';
  const readComposer = () => (isTextarea ? composer.value : composer.innerText) || '';
  const current = readComposer().replace(/\s+/g, ' ').trim();
  const wanted = text.replace(/\s+/g, ' ').trim();
  if (!current.startsWith(wanted.slice(0, 200))) {
    composer.focus();
    if (isTextarea) {
      composer.value = text;
      composer.dispatchEvent(new Event('input', { bubbles: true }));
    } else if (!document.execCommand('insertText', false, text)) {
      return JSON.stringify({ ok: false, error: 'insertText rejected' });
    }
  }
  const form = composer.closest('form') || document;
  // Only real send controls: testid send-button, a send aria-label, or the
  // form's submit button. NB: .composer-submit-button-color also matches the
  // VOICE-mode button ("Démarrer le mode vocal") while React has not armed
  // the send button yet — never fall back to it.
  const findSend = () => form.querySelector('button[data-testid="send-button"]:not([disabled])')
    || Array.from(form.querySelectorAll('button[aria-label]')).find((b) =>
        !b.disabled && /envoyer le (prompt|message)|send (prompt|message)/i.test(b.getAttribute('aria-label') || ''))
    || form.querySelector('button[type="submit"]:not([disabled])');
  let btn = null;
  for (let i = 0; i < 50 && !btn; i++) { btn = findSend(); if (!btn) await sleep(200); }
  if (!btn) return JSON.stringify({ ok: false, error: 'send button not found' });
  btn.click();
  // Proof of send: the composer empties once the message is accepted.
  for (let i = 0; i < 25; i++) {
    await sleep(200);
    if (!readComposer().trim()) return JSON.stringify({ ok: true });
  }
  return JSON.stringify({ ok: false, error: 'composer not cleared after click' });
})
"""

# Read-only DOM health probe: tests every selector role and reports which
# candidate currently matches, plus diagnostics for debugging UI changes.
# No clicks, no typing — safe to run anytime (used by /api/transport/probe
# and the daily health-check automation).
_PROBE_JS = r"""
(() => {
  const q = (sel) => { try { return document.querySelector(sel); } catch (e) { return null; } };
  const qCount = (sel) => { try { return document.querySelectorAll(sel).length; } catch (e) { return 0; } };
  const CANDIDATES = {
    composer: ['#prompt-textarea', 'div[contenteditable="true"][role="textbox"]', 'div[contenteditable="true"]', 'form textarea'],
    messages: ['[data-message-author-role]', 'article[data-testid^="conversation-turn"]', 'main article'],
    send: ['button[data-testid="send-button"]', 'form button[type="submit"]'],
    stop: ['[data-testid="stop-button"]', 'button[aria-label*="Stop"]', 'button[aria-label*="Arr"]'],
  };
  const probeRole = (cands) => {
    for (const c of cands) { if (q(c)) return { ok: true, selector: c, count: qCount(c) }; }
    return { ok: false, selector: null, count: 0 };
  };
  const roles = {};
  for (const [name, cands] of Object.entries(CANDIDATES)) roles[name] = probeRole(cands);
  // The send button only exists while the composer holds text, so also check
  // for a send aria-label anywhere (voice-mode button excluded by the regex).
  const sendAria = Array.from(document.querySelectorAll('button[aria-label]')).find((b) =>
    /envoyer le (prompt|message)|send (prompt|message)/i.test(b.getAttribute('aria-label') || ''));
  if (!roles.send.ok && sendAria) roles.send = { ok: true, selector: 'aria:' + (sendAria.getAttribute('aria-label') || ''), count: 1 };
  const buttons = Array.from(document.querySelectorAll('form button, main button')).slice(0, 30).map((b) => ({
    testid: b.getAttribute('data-testid'),
    aria: b.getAttribute('aria-label'),
    type: b.getAttribute('type'),
    disabled: !!b.disabled,
  }));
  const controls = Array.from(document.querySelectorAll('a, button'));
  const isLoginControl = (el) => {
    const testid = (el.getAttribute('data-testid') || '').trim();
    const label = ((el.getAttribute('aria-label') || '') + ' ' + (el.textContent || ''))
      .replace(/\s+/g, ' ').trim();
    return /(^|[-_])(login|sign[-_]?up)([-_]|$)/i.test(testid)
      || /^(login|log in|sign up|se connecter|connexion|s['’]inscrire|créer un compte)$/i.test(label);
  };
  const loginControls = controls.filter(isLoginControl).length;
  const accountControls = controls.filter((el) =>
    /profile|profil|account|compte/i.test(
      [el.getAttribute('data-testid') || '', el.getAttribute('aria-label') || ''].join(' ')
    )
  ).length;
  return JSON.stringify({
    url: location.href,
    title: document.title,
    roles: roles,
    diagnostics: {
      buttons: buttons,
      contenteditables: qCount('[contenteditable="true"]'),
      textareas: qCount('textarea'),
      message_nodes: qCount('[data-message-author-role]'),
      conversation_links: qCount('a[href^="/c/"]'),
      sidebar_conversation_links: qCount('nav a[href^="/c/"], aside a[href^="/c/"]'),
      login_controls: loginControls,
      account_controls: accountControls,
    },
  });
})()
"""


def _summarize_probe(result: dict) -> dict:
    """Add the top-level ok/failures/warnings summary to a raw probe payload.

    The transport is considered healthy when the composer resolves. Message
    nodes are also required inside an existing ``/c/`` conversation, but not
    on the valid ChatGPT home/new-chat page. Send/stop buttons are contextual
    and therefore remain warnings.
    """
    roles = result.get("roles") or {}
    parsed_url = urllib.parse.urlparse(str(result.get("url") or ""))
    on_chatgpt_home = (
        (parsed_url.hostname or "").lower() in {"chatgpt.com", "www.chatgpt.com"}
        and parsed_url.path in {"", "/"}
    )
    failures = []
    if not (roles.get("composer") or {}).get("ok"):
        failures.append("composer")
    if not on_chatgpt_home and not (roles.get("messages") or {}).get("ok"):
        failures.append("messages")
    warnings = [name for name in ("send", "stop") if not (roles.get(name) or {}).get("ok")]
    if on_chatgpt_home and not (roles.get("messages") or {}).get("ok"):
        warnings.insert(0, "messages")
    if int((result.get("diagnostics") or {}).get("login_controls") or 0) > 0:
        result["blocker"] = "login"
        failures.append("login")
    result["failures"] = failures
    result["warnings"] = warnings
    result["ok"] = not failures
    return result


class WebBridgeDriver:
    """Drives the user's Chrome through the local WebBridge daemon.

    Phase 5 uses this against real chatgpt.com. Loopback only; the daemon
    holds the actual browser session. NOT exercised by fixture tests.
    """

    def __init__(self, daemon: str = "http://127.0.0.1:10086", session: str = "cortex-bridge"):
        self.driver_name = "webbridge"
        self.daemon = daemon.rstrip("/")
        self.session = session
        self.target_url: str | None = None
        self._closed = False
        self._close_lock = asyncio.Lock()

    def _command(self, action: str, args: dict | None = None, timeout: float = 30) -> Any:
        payload = {"action": action, "args": args or {}, "session": self.session}
        req = urllib.request.Request(
            f"{self.daemon}/command",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        ok = False
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            _record_perf(self.session, action, started, False)
            raise DriverError(f"webbridge {action} failed: {exc}") from exc
        if isinstance(data, dict) and data.get("ok") is False:
            _record_perf(self.session, action, started, False)
            raise DriverError(f"webbridge {action} rejected: {data.get('error')}")
        ok = True
        _record_perf(self.session, action, started, ok)
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
                self.target_url = url
                return
            except DriverError as exc:
                last = exc
                await asyncio.sleep(1.5)
        raise last  # type: ignore[misc]

    async def evaluate(self, code: str, timeout: float = 30) -> Any:
        raw = await asyncio.to_thread(
            self._command, "evaluate", {"code": code}, timeout
        )
        if isinstance(raw, dict) and "value" in raw:
            return raw["value"]
        return raw

    async def list_tabs(self) -> list[dict]:
        raw = await asyncio.to_thread(self._command, "list_tabs", {}, 5)
        if isinstance(raw, dict):
            return list(raw.get("tabs", []))
        return list(raw or [])

    async def spa_navigate(self, url: str) -> bool:
        """Client-side conversation switch via the sidebar link (no reload).

        Returns True when the SPA router handled the switch; False means the
        caller must fall back to a full `navigate`."""
        code = f"{_SPA_NAV_JS}({json.dumps(url)})"
        try:
            raw = await asyncio.to_thread(self._command, "evaluate", {"code": code}, 30)
        except DriverError:
            return False
        if isinstance(raw, dict) and "value" in raw:
            raw = raw["value"]
        try:
            result = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except json.JSONDecodeError:
            return False
        handled = bool(result.get("ok"))
        if handled:
            self.target_url = url
        return handled

    async def get_state(self) -> dict:
        raw = await asyncio.to_thread(self._command, "evaluate", {"code": _STATE_JS})
        if isinstance(raw, dict) and "value" in raw:
            raw = raw["value"]
        try:
            return json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise DriverError(f"cannot parse page state: {exc}") from exc

    async def get_light_state(self) -> dict:
        """Cheap identity/count read (P0c) — no message text serialized."""
        raw = await asyncio.to_thread(self._command, "evaluate", {"code": _LIGHT_STATE_JS})
        if isinstance(raw, dict) and "value" in raw:
            raw = raw["value"]
        try:
            return json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise DriverError(f"cannot parse light page state: {exc}") from exc

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
                "code": "(() => { for (const c of ['[data-testid=\"stop-button\"]',"
                " 'button[aria-label*=\"Stop\"]', 'button[aria-label*=\"Arr\"]']) {"
                " try { const el = document.querySelector(c); if (el) { el.click(); return; } }"
                " catch (e) {} } })()"
            },
        )

    def capabilities(self) -> dict:
        """What this driver can do (P3) — the UI adapts from this, never hardcodes."""
        return {
            "send_text": True,
            "upload_file": True,
            "upload_image": True,
            "take_screenshot": True,
            "limits": {"file_bytes": MAX_FILE_BYTES, "image_bytes": MAX_IMAGE_BYTES},
        }

    async def upload_files(self, selector: str, paths: list[str]) -> None:
        """Attach local files to the composer via the daemon upload action."""
        await asyncio.to_thread(
            self._command, "upload", {"selector": selector, "files": paths}, 60
        )

    async def await_attachment(self) -> dict:
        raw = await asyncio.to_thread(self._command, "evaluate", {"code": _ATTACHMENT_WAIT_JS}, 70)
        if isinstance(raw, dict) and "value" in raw:
            raw = raw["value"]
        try:
            return json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        except json.JSONDecodeError as exc:
            raise DriverError(f"cannot parse attachment state: {exc}") from exc

    async def send_bare(self) -> dict:
        raw = await asyncio.to_thread(self._command, "evaluate", {"code": _SEND_BARE_JS}, 30)
        if isinstance(raw, dict) and "value" in raw:
            raw = raw["value"]
        try:
            return json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        except json.JSONDecodeError as exc:
            raise DriverError(f"cannot parse bare-send result: {exc}") from exc

    async def take_screenshot(self, path: str) -> dict:
        """Capture the current tab (P3) — returns the daemon screenshot payload."""
        return await asyncio.to_thread(self._command, "screenshot", {"path": path}, 30)

    async def probe(self) -> dict:
        """Read-only DOM health check on the current tab (see _PROBE_JS)."""
        raw = await asyncio.to_thread(self._command, "evaluate", {"code": _PROBE_JS})
        if isinstance(raw, dict) and "value" in raw:
            raw = raw["value"]
        try:
            result = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        except (json.JSONDecodeError, TypeError) as exc:
            raise DriverError(f"cannot parse probe result: {exc}") from exc
        return _summarize_probe(result)

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

    async def health(self) -> dict:
        try:
            tabs = await self.list_tabs()
            return {
                "connected": True,
                "tabs": len(tabs),
                "driver": self.driver_name,
                "session": self.session,
            }
        except DriverError as exc:
            return {
                "connected": False,
                "tabs": 0,
                "driver": self.driver_name,
                "session": self.session,
                "error": str(exc),
            }

    async def list_models(self) -> dict:
        raw = await asyncio.to_thread(self._command, "evaluate", {"code": _MODELS_JS}, 30)
        if isinstance(raw, dict) and "value" in raw:
            raw = raw["value"]
        try:
            return json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        except (json.JSONDecodeError, TypeError) as exc:
            raise DriverError(f"cannot parse model list: {exc}") from exc

    async def select_model(self, label: str) -> str:
        code = f"{_SELECT_MODEL_JS}({json.dumps(label)})"
        raw = await asyncio.to_thread(self._command, "evaluate", {"code": code}, 40)
        if isinstance(raw, dict) and "value" in raw:
            raw = raw["value"]
        result = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        if not result.get("ok"):
            raise DriverError(f"model selection failed: {result.get('error', 'unknown')}")
        return str(result.get("selected") or label)

    async def close_tab(self) -> None:
        await asyncio.to_thread(self._command, "close_tab", {})
        self.target_url = None

    async def close(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            await self.close_tab()
            self._closed = True

    async def open_login(self) -> dict:
        await self.navigate("https://chatgpt.com/")
        return await self.health()
