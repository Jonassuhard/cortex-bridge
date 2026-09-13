"""Conversation-first ChatGPT transport API for the Cortex Bridge UI.

This router does not use the OpenAI API. It controls the user's already signed-in
ChatGPT Chrome surface through the existing WebBridge driver, confirms delivery,
mirrors the visible assistant response, and exposes an SSE stream to the local UI.

The autonomous mission runner remains separate: these routes provide the normal
conversation experience while /api/missions drives the ChatGPT ↔ local executor loop.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

import missions as missions_api
import write_slots
import attachments
from transport.chatgpt_web.adapter import (
    CONVERSATION_MISMATCH,
    GENERATION_CANCELLED,
    TAB_CLOSED,
    ChatGPTWebTransport,
    TransportError,
)
from transport.browser import create_transport
from cortex_paths import build_paths

router = APIRouter(prefix="/api")
RUNTIME_PATHS = build_paths()
DATA_DIR = RUNTIME_PATHS.home
CHAT_RUNS_FILE = RUNTIME_PATHS.chat_runs


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _monotonic_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _validate_chatgpt_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.netloc not in {"chatgpt.com", "www.chatgpt.com"}:
        raise HTTPException(status_code=422, detail="conversation URL must be an https://chatgpt.com URL")
    if parsed.path != "/" and not parsed.path.startswith("/c/"):
        raise HTTPException(status_code=422, detail="unsupported ChatGPT conversation URL")
    return url.strip()


@dataclass
class ChatRunRuntime:
    id: str
    conversation_url: str
    text: str
    new_conversation: bool
    state: str = "QUEUED"
    canonical_url: str | None = None
    response_text: str = ""
    attachment_path: str | None = None
    attachment_image: bool = False
    attachment_name: str | None = None
    attachment_token: str | None = None
    attachment_owner: str | None = None
    attachment_mime: str | None = None
    attachment_kind: str | None = None
    attachment_size_bytes: int | None = None
    created_at: str = field(default_factory=_now)
    delivered_at: str | None = None
    first_response_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    error_details: dict[str, Any] | None = None
    latency: dict[str, int | None] = field(default_factory=lambda: {
        "delivery_ms": None,
        "first_response_ms": None,
        "total_ms": None,
    })
    events: list[dict[str, Any]] = field(default_factory=list)
    event_seq: int = 0
    cancelled: bool = False
    conversation_key: str | None = None
    session_id: str | None = None
    lease: Any | None = None
    transport: ChatGPTWebTransport | None = None
    task: asyncio.Task | None = None

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "state": self.state,
            "conversation_url": self.conversation_url,
            "canonical_url": self.canonical_url,
            "text": self.text,
            "response_text": self.response_text,
            "attachment_name": self.attachment_name,
            "created_at": self.created_at,
            "delivered_at": self.delivered_at,
            "first_response_at": self.first_response_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "error_details": self.error_details,
            "latency": self.latency,
        }

    def persisted(self) -> dict[str, Any]:
        payload = self.public()
        payload.update({
            "new_conversation": self.new_conversation,
            "conversation_key": self.conversation_key,
            "session_id": self.session_id,
            "attachment_path": self.attachment_path,
            "attachment_image": self.attachment_image,
            "attachment_name": self.attachment_name,
            "attachment_token": self.attachment_token,
            "attachment_owner": self.attachment_owner,
            "attachment_mime": self.attachment_mime,
            "attachment_kind": self.attachment_kind,
            "attachment_size_bytes": self.attachment_size_bytes,
        })
        return payload


class ChatSendIn(BaseModel):
    conversation_url: str
    text: str
    new_conversation: bool = False


class AttachmentUploadIn(BaseModel):
    name: str | None = None
    data_b64: str | None = None
    path: str | None = None


class ChatSendAttachmentIn(BaseModel):
    conversation_url: str
    text: str = ""
    path: str | None = None
    data_b64: str | None = None
    image: bool = False
    name: str | None = None
    new_conversation: bool = False


class ChatScreenshotIn(BaseModel):
    conversation_url: str
    text: str = ""
    new_conversation: bool = False


class ContextApprovalItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["file", "screenshot", "link"]
    reason: str
    path: str | None = None
    target: str | None = None
    url: str | None = None


class ContextApprovalIn(BaseModel):
    conversation_url: str
    workspace: str
    request_id: str
    item_id: str
    item: ContextApprovalItemIn
    text: str = ""
    new_conversation: bool = False


class ChatCancelIn(BaseModel):
    reason: str = "USER_CANCEL"


# Read-only browsing always uses a session outside the bounded writer registry.
READ_ONLY_SESSION_ID = "cortex-view-read-only"
SCREENSHOT_SESSION_ID = "cortex-capture-read-only"
ui_transport_factory = create_transport

_runs: dict[str, ChatRunRuntime] = {}
_view_transport: ChatGPTWebTransport | None = None
_view_url: str | None = None
_view_mutex = asyncio.Lock()
_view_operation_mutex: asyncio.Lock | None = None
_view_operation_loop: asyncio.AbstractEventLoop | None = None
_context_approval_registry: dict[tuple[str, str, str, str], dict[str, Any]] = {}
# Requests are populated only from assistant messages observed through the
# server-side ChatGPT transport.  The client may approve an observed item, but
# it cannot mint a request/item identity by posting directly to the endpoint.
_observed_context_registry: dict[tuple[str, str, str], dict[str, Any]] = {}
_context_approval_mutex: asyncio.Lock | None = None
_context_approval_loop: asyncio.AbstractEventLoop | None = None

_CONTEXT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CONTEXT_REQUEST_FENCE_RE = re.compile(
    r"```cortex-context-request(?:\.v1)?[ \t]*\r?\n([\s\S]*?)```",
    re.IGNORECASE,
)
_CONTEXT_PROTOCOL = "cortex-context-request.v1"
_CONTEXT_MAX_ITEMS = 10
_CONTEXT_MAX_REASON_CHARS = 500
_CONTEXT_MAX_SUMMARY_CHARS = 600


def _context_conversation_key(url: str) -> str:
    """Use one stable identity for ChatGPT URLs with/without a trailing slash."""
    return url.rstrip("/")


def _view_operation_lock() -> asyncio.Lock:
    """Return the shared read-surface lock for the current event loop."""
    global _view_operation_mutex, _view_operation_loop
    loop = asyncio.get_running_loop()
    if _view_operation_mutex is None or _view_operation_loop is not loop:
        _view_operation_mutex = asyncio.Lock()
        _view_operation_loop = loop
    return _view_operation_mutex


def _context_approval_lock() -> asyncio.Lock:
    """Return the idempotency lock for the current event loop."""
    global _context_approval_mutex, _context_approval_loop
    loop = asyncio.get_running_loop()
    if _context_approval_mutex is None or _context_approval_loop is not loop:
        _context_approval_mutex = asyncio.Lock()
        _context_approval_loop = loop
    return _context_approval_mutex


def _validate_context_identity(value: str, field: str) -> str:
    if not isinstance(value, str) or not _CONTEXT_ID_RE.fullmatch(value):
        raise HTTPException(
            status_code=422,
            detail=f"{field} must be a bounded token (letters, numbers, '.', '_' ':' or '-')",
        )
    return value


def _authorized_context_workspace() -> Path:
    """Return the canonical workspace selected in the persisted settings.

    Context approvals must be rooted at the server-selected workspace, not at
    an arbitrary path supplied by a browser client.  Missing or invalid
    settings fail closed.
    """
    default = Path.home() / "cortex-workspaces"
    try:
        raw = json.loads(RUNTIME_PATHS.settings.read_text(encoding="utf-8"))
        configured = raw.get("default_workspace") if isinstance(raw, dict) else None
        if isinstance(configured, str) and configured.strip():
            default = Path(configured).expanduser()
    except (OSError, json.JSONDecodeError):
        pass
    try:
        root = default.resolve(strict=True)
    except (OSError, RuntimeError):
        raise HTTPException(status_code=503, detail="authorized workspace is unavailable")
    if not root.is_dir():
        raise HTTPException(status_code=503, detail="authorized workspace is not a directory")
    return root


def _context_item_payload(item: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize one assistant-proposed context item for provenance checks."""
    if not isinstance(item, dict):
        return None
    item_id = item.get("id")
    reason = item.get("reason")
    kind = item.get("kind")
    if (
        not isinstance(item_id, str)
        or not _CONTEXT_ID_RE.fullmatch(item_id.strip())
        or not isinstance(reason, str)
        or not reason.strip()
        or len(reason.strip()) > _CONTEXT_MAX_REASON_CHARS
        or kind not in {"file", "screenshot", "link"}
    ):
        return None
    result: dict[str, Any] = {
        "id": item_id.strip(),
        "kind": kind,
        "reason": reason.strip(),
    }
    if kind == "file":
        path = item.get("path")
        if not isinstance(path, str) or not path.strip():
            return None
        candidate = Path(path.strip())
        if candidate.is_absolute() or "\x00" in path or ".." in candidate.parts:
            return None
        result["path"] = path.strip()
    elif kind == "screenshot":
        target = item.get("target")
        if not isinstance(target, str) or target.strip() not in {
            "current_chatgpt",
            "current_conversation",
        }:
            return None
        result["target"] = target.strip()
    else:
        target = item.get("url")
        if not isinstance(target, str) or not re.match(r"^https?://[^\s]+$", target.strip(), re.IGNORECASE):
            return None
        result["url"] = target.strip()
    return result


def _context_payload_candidates(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Read valid proposal payloads from one assistant message only."""
    if message.get("role") != "assistant":
        return []
    candidates: list[str] = []
    text = message.get("text")
    if isinstance(text, str):
        candidates.extend(match.group(1).strip() for match in _CONTEXT_REQUEST_FENCE_RE.finditer(text))
    for block in message.get("code_blocks") or []:
        if not isinstance(block, dict):
            continue
        lang = str(block.get("lang") or "").strip().lower()
        if lang in {"cortex-context-request", _CONTEXT_PROTOCOL} and isinstance(block.get("text"), str):
            candidates.append(str(block["text"]).strip())
    # Duplicate serialization (text + code_blocks) is ambiguous and must not
    # register a request that cannot be tied to one exact representation.
    if len(candidates) != 1 or not candidates[0]:
        return []
    try:
        payload = json.loads(candidates[0])
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict) or payload.get("protocol") != _CONTEXT_PROTOCOL:
        return []
    request_id = payload.get("requestId")
    summary = payload.get("summary")
    items = payload.get("items")
    if (
        not isinstance(request_id, str)
        or not _CONTEXT_ID_RE.fullmatch(request_id.strip())
        or not isinstance(summary, str)
        or not summary.strip()
        or len(summary.strip()) > _CONTEXT_MAX_SUMMARY_CHARS
        or not isinstance(items, list)
        or not 0 < len(items) <= _CONTEXT_MAX_ITEMS
    ):
        return []
    normalized = [_context_item_payload(item) for item in items]
    if any(item is None for item in normalized):
        return []
    item_values = [item for item in normalized if item is not None]
    if len({item["id"] for item in item_values}) != len(item_values):
        return []
    return [{"request_id": request_id.strip(), "item": item} for item in item_values]


def _register_observed_context_requests(
    conversation_url: str,
    messages: list[dict[str, Any]],
    *,
    workspace: Path | None = None,
) -> None:
    """Record assistant proposals observed by the trusted read transport."""
    candidates_by_message = [
        (message, _context_payload_candidates(message)) for message in messages
    ]
    if not any(candidates for _, candidates in candidates_by_message):
        return
    try:
        root = (workspace or _authorized_context_workspace()).resolve(strict=True)
    except HTTPException:
        # Preserve the visible ChatGPT response, but do not create an approval
        # record when the authorized workspace cannot be resolved.
        return
    for message, candidates in candidates_by_message:
        for candidate in candidates:
            key = (
                _context_conversation_key(conversation_url),
                candidate["request_id"],
                candidate["item"]["id"],
            )
            _observed_context_registry[key] = {
                "workspace": str(root),
                "item": candidate["item"],
                "message_id": message.get("id"),
            }


def _make_transport(session_id: str) -> ChatGPTWebTransport:
    """Keep zero-argument fixture factories compatible at the API boundary."""
    try:
        return ui_transport_factory(session_id)
    except TypeError:
        return ui_transport_factory()


def _persist_runs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    runs = list(_runs.values())
    terminal_states = {"COMPLETED", "FAILED", "CANCELLED"}
    retained_ids = {
        run.id for run in runs if run.state not in terminal_states
    }
    retained_ids.update(
        run.id for run in [r for r in runs if r.state in terminal_states][-100:]
    )
    payload = [run.persisted() for run in runs if run.id in retained_ids]
    tmp = CHAT_RUNS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CHAT_RUNS_FILE)


def _load_persisted_runs() -> None:
    """Restore history and reserve leases for interrupted chat writers."""
    try:
        payload = json.loads(CHAT_RUNS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, list):
        return
    for item in payload:
        if not isinstance(item, dict) or not item.get("id") or not item.get("conversation_url"):
            continue
        run = ChatRunRuntime(
            id=str(item["id"]),
            conversation_url=str(item["conversation_url"]),
            text=str(item.get("text") or ""),
            new_conversation=bool(item.get("new_conversation")),
            state=str(item.get("state") or "FAILED"),
            canonical_url=item.get("canonical_url"),
            response_text=str(item.get("response_text") or ""),
            attachment_path=item.get("attachment_path"),
            attachment_image=bool(item.get("attachment_image")),
            attachment_name=item.get("attachment_name"),
            attachment_token=item.get("attachment_token"),
            attachment_owner=item.get("attachment_owner"),
            attachment_mime=item.get("attachment_mime"),
            attachment_kind=item.get("attachment_kind"),
            attachment_size_bytes=item.get("attachment_size_bytes"),
            created_at=str(item.get("created_at") or _now()),
            delivered_at=item.get("delivered_at"),
            first_response_at=item.get("first_response_at"),
            completed_at=item.get("completed_at"),
            error=item.get("error"),
            error_details=item.get("error_details"),
            latency=dict(item.get("latency") or {
                "delivery_ms": None,
                "first_response_ms": None,
                "total_ms": None,
            }),
            conversation_key=item.get("conversation_key"),
            session_id=item.get("session_id"),
        )
        if (
            run.state not in {"COMPLETED", "FAILED", "CANCELLED"}
            and run.conversation_key
            and run.session_id
        ):
            try:
                run.lease = write_slots.restore_writer(
                    run.conversation_key,
                    run.session_id,
                    run.canonical_url or run.conversation_url,
                )
            except (
                ValueError,
                write_slots.SessionCapacityError,
                write_slots.SessionRekeyError,
            ):
                run.state = "FAILED"
                run.error = "SESSION_RESTORE_FAILED: persisted writer capacity is inconsistent"
        _runs[run.id] = run
    terminal_states = {"COMPLETED", "FAILED", "CANCELLED"}
    preserve: set[str] = set()
    for run in _runs.values():
        if run.state in terminal_states or not run.attachment_path:
            continue
        descriptor = {
            "token": run.attachment_token,
            "owner": run.attachment_owner,
            "name": run.attachment_name,
            "path": run.attachment_path,
            "size_bytes": run.attachment_size_bytes,
            "mime": run.attachment_mime,
            "kind": run.attachment_kind,
        }
        try:
            attachments.restore_descriptor(descriptor)
            preserve.add(run.attachment_path)
        except ValueError as exc:
            run.state = "FAILED"
            run.error = f"ATTACHMENT_RESTORE_FAILED: {exc}"
    attachments.cleanup_abandoned(preserve)


_load_persisted_runs()


def _emit(run: ChatRunRuntime, event_type: str, payload: dict[str, Any]) -> None:
    run.event_seq += 1
    run.events.append({
        "seq": run.event_seq,
        "ts": _now(),
        "type": event_type,
        "payload": payload,
    })
    # Keep memory bounded while preserving enough replay for reconnects.
    if len(run.events) > 500:
        run.events[:] = run.events[-500:]
    _persist_runs()


def _set_state(run: ChatRunRuntime, state: str) -> None:
    if run.state == state:
        return
    run.state = state
    _emit(run, "status", {"state": state})


async def _ensure_view_transport(
    url: str,
    *,
    force_recreate: bool = False,
) -> ChatGPTWebTransport:
    global _view_transport, _view_url
    async with _view_mutex:
        if (
            not force_recreate
            and _view_transport is not None
            and _view_url == url
        ):
            return _view_transport
        previous = _view_transport
        transport = _make_transport(READ_ONLY_SESSION_ID)
        if url.rstrip("/") == "https://chatgpt.com":
            await transport.start_new_conversation(url)
        else:
            await transport.select_conversation(url)
        _view_transport = transport
        _view_url = url
        if previous is not None and previous is not transport:
            await previous.close()
        return transport


async def _run_chat(run: ChatRunRuntime) -> None:
    started = time.monotonic()
    transport: ChatGPTWebTransport | None = None
    try:
        if run.lease is None:
            raise RuntimeError("chat writer started without a conversation lease")
        transport = _make_transport(run.lease.session_id)
        run.transport = transport
        if run.cancelled:
            raise TransportError(GENERATION_CANCELLED, "cancelled before send")
        _set_state(run, "SELECTING_CONVERSATION")
        if run.new_conversation or run.conversation_url.rstrip("/") == "https://chatgpt.com":
            await transport.start_new_conversation(run.conversation_url)
        else:
            await transport.select_conversation(run.conversation_url)

        if run.cancelled:
            raise TransportError(GENERATION_CANCELLED, "cancelled before delivery")
        _set_state(run, "SENDING_TO_CHATGPT")
        if run.attachment_path:
            import os
            from urllib.parse import quote

            raw_url = None
            if run.attachment_token:
                port = os.environ.get("PORT", "8420")
                raw_url = (
                    "http://127.0.0.1:"
                    f"{port}/api/chat/attachments/raw?token={quote(run.attachment_token)}"
                )
            await transport.send_with_attachment(
                run.text,
                run.attachment_path,
                image=run.attachment_image,
                raw_url=raw_url,
                mime=run.attachment_mime,
                name=run.attachment_name,
            )
        else:
            await transport.send_message(run.text)
        run.delivered_at = _now()
        run.latency["delivery_ms"] = _monotonic_ms(started)
        run.canonical_url = transport.lock.url if transport.lock else run.conversation_url
        if (
            run.conversation_key
            and run.conversation_key.startswith("provisional:")
            and run.canonical_url
            and "/c/" in run.canonical_url
        ):
            run.lease = await write_slots.rekey(run.conversation_key, run.canonical_url)
            run.conversation_key = run.lease.conversation_key
        _set_state(run, "VISIBLE_IN_CHATGPT")
        _emit(run, "delivery", {
            "delivered_at": run.delivered_at,
            "canonical_url": run.canonical_url,
            "latency_ms": run.latency["delivery_ms"],
        })
        _set_state(run, "WAITING_FOR_CHATGPT")

        last_visible = ""
        last_streaming: bool | None = None

        async def on_update(update: dict[str, Any]) -> None:
            nonlocal last_streaming, last_visible
            if run.cancelled:
                await transport.cancel_generation()
                return
            text = str(update.get("text") or "")
            streaming = bool(update.get("streaming"))
            if text and run.first_response_at is None:
                run.first_response_at = _now()
                run.latency["first_response_ms"] = _monotonic_ms(started)
            if text != last_visible or streaming != last_streaming:
                last_visible = text
                last_streaming = streaming
                run.response_text = text
                _set_state(
                    run,
                    "CHATGPT_STREAMING" if streaming else "WAITING_FOR_CHATGPT",
                )
                _emit(run, "stream", {
                    "text": text,
                    "streaming": streaming,
                    "first_response_at": run.first_response_at,
                    "code_blocks": update.get("code_blocks", []),
                    "images": update.get("images", []),
                })
                if not streaming:
                    _register_observed_context_requests(
                        run.canonical_url or run.conversation_url,
                        [{
                            "id": update.get("id"),
                            "role": "assistant",
                            "text": text,
                            "code_blocks": update.get("code_blocks", []),
                        }],
                    )

        final = await transport.stream_response(on_update)
        if run.cancelled:
            raise TransportError(GENERATION_CANCELLED, "cancelled during response")
        run.response_text = str(final.get("text") or "")
        _register_observed_context_requests(
            run.canonical_url or run.conversation_url,
            [{
                "id": final.get("id"),
                "role": "assistant",
                "text": run.response_text,
                "code_blocks": final.get("code_blocks", []),
            }],
        )
        run.completed_at = _now()
        run.latency["total_ms"] = _monotonic_ms(started)
        _set_state(run, "COMPLETED")
        _emit(run, "complete", {
            "text": run.response_text,
            "completed_at": run.completed_at,
            "canonical_url": run.canonical_url,
            "latency": run.latency,
            "code_blocks": final.get("code_blocks", []),
            "images": final.get("images", []),
        })
    except asyncio.CancelledError:
        run.cancelled = True
        run.error = "GENERATION_CANCELLED: chat task cancelled"
        run.completed_at = _now()
        run.latency["total_ms"] = _monotonic_ms(started)
        _set_state(run, "CANCELLED")
        _emit(run, "cancelled", {"error": run.error})
    except TransportError as exc:
        run.error = f"{exc.code}: {exc.message}"
        run.error_details = exc.details or None
        run.completed_at = _now()
        run.latency["total_ms"] = _monotonic_ms(started)
        if exc.code == GENERATION_CANCELLED or run.cancelled:
            _set_state(run, "CANCELLED")
            _emit(run, "cancelled", {"error": run.error})
        else:
            _set_state(run, "FAILED")
            _emit(
                run,
                "error",
                {"error": run.error, "code": exc.code, "details": exc.details},
            )
    except Exception as exc:  # never leave a UI chat stuck forever
        run.error = f"CHAT_RUN_CRASHED: {exc}"
        run.completed_at = _now()
        run.latency["total_ms"] = _monotonic_ms(started)
        _set_state(run, "FAILED")
        _emit(run, "error", {"error": run.error, "code": "CHAT_RUN_CRASHED"})
    finally:
        if transport is not None:
            try:
                await transport.close()
            except Exception:
                pass
        if run.attachment_path:
            try:
                attachments.release_owned(
                    run.attachment_path,
                    token=run.attachment_token,
                )
            except Exception:
                pass
        if run.lease is not None:
            await run.lease.release()
        _persist_runs()


@router.get("/conversations/snapshot")
async def conversation_snapshot(url: str = Query(..., min_length=1), light: int = 0) -> dict[str, Any]:
    """Read one selected conversation through a dedicated read-only UI session.

    light=1 returns identity/count/streaming only (P0c) — the UI polls this
    cheaply and fetches the full snapshot only when the signature changes."""
    clean_url = _validate_chatgpt_url(url)

    async def read_snapshot(transport: ChatGPTWebTransport) -> dict[str, Any]:
        if light:
            light_state = await transport._light_state()
            return {
                "url": light_state.get("url", clean_url),
                "conversation_id": light_state.get("conversation_id"),
                "title": light_state.get("title") or "ChatGPT",
                "streaming": bool(light_state.get("streaming")),
                "composer_present": bool(light_state.get("composer_present")),
                "message_count": light_state.get("message_count", 0),
                "first_id": light_state.get("first_id"),
                "last_id": light_state.get("last_id"),
                "light": True,
            }
        state = await transport.snapshot(
            verify_lock=clean_url.rstrip("/") != "https://chatgpt.com"
        )
        _register_observed_context_requests(clean_url, state.get("messages") or [])
        # Do not expose protocol reconstruction or any browser-level secret.
        return {
            "url": state.get("url", clean_url),
            "conversation_id": state.get("conversation_id"),
            "title": state.get("title") or "ChatGPT",
            "blocker": state.get("blocker"),
            "composer_present": bool(state.get("composer_present")),
            "send_button_present": bool(state.get("send_button_present")),
            "stop_button_present": bool(state.get("stop_button_present")),
            "streaming": bool(state.get("streaming")),
            "model_label": state.get("model_label"),
            "messages": state.get("messages", []),
        }

    try:
        async with _view_operation_lock():
            transport = await _ensure_view_transport(clean_url)
            try:
                return await read_snapshot(transport)
            except TransportError as exc:
                if exc.code not in {TAB_CLOSED, CONVERSATION_MISMATCH}:
                    raise
                recovered = await _ensure_view_transport(
                    clean_url,
                    force_recreate=True,
                )
                return await read_snapshot(recovered)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"cannot read conversation: {exc}")


@router.post("/chat/send", status_code=202)
async def send_chat(body: ChatSendIn) -> dict[str, Any]:
    if missions_api._global_stop:
        raise HTTPException(status_code=409, detail="STOP EVERYTHING is active; reset it first")
    if not missions_api.optin_accepted():
        raise HTTPException(status_code=403, detail="Experimental ChatGPT Web Transport is not enabled")
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="message text must not be empty")
    url = _validate_chatgpt_url(body.conversation_url)
    missions_api.get_store()  # restore durable mission leases before capacity admission
    conversation_key = (
        write_slots.new_conversation_key()
        if body.new_conversation or url.rstrip("/") == "https://chatgpt.com"
        else url
    )
    try:
        lease = await write_slots.acquire_writer(conversation_key)
    except write_slots.SessionCapacityError:
        raise HTTPException(status_code=409, detail=write_slots.REFUSAL_MESSAGE)
    run = ChatRunRuntime(
        id=uuid.uuid4().hex,
        conversation_url=url,
        text=text,
        new_conversation=body.new_conversation,
        conversation_key=conversation_key,
        session_id=lease.session_id,
        lease=lease,
    )
    try:
        _runs[run.id] = run
        _emit(run, "status", {"state": run.state})
        payload = run.public()
        run.task = asyncio.create_task(_run_chat(run))
        return payload
    except BaseException:
        _runs.pop(run.id, None)
        await lease.release()
        raise


def list_active_runs() -> list[ChatRunRuntime]:
    """Non-terminal chat runs — used by the two-write-conversation guard."""
    return [run for run in _runs.values() if run.state not in {"COMPLETED", "FAILED", "CANCELLED"}]


async def _start_attachment_run(
    *,
    url: str,
    text: str,
    path: str,
    image: bool,
    name: str | None,
    new_conversation: bool,
    token: str | None = None,
    owner: str | None = None,
    mime: str | None = None,
    kind: str | None = None,
    size_bytes: int | None = None,
) -> dict[str, Any]:
    missions_api.get_store()  # restore durable mission leases before capacity admission
    conversation_key = (
        write_slots.new_conversation_key()
        if new_conversation or url.rstrip("/") == "https://chatgpt.com"
        else url
    )
    try:
        lease = await write_slots.acquire_writer(conversation_key)
    except write_slots.SessionCapacityError:
        raise HTTPException(status_code=409, detail=write_slots.REFUSAL_MESSAGE)
    run = ChatRunRuntime(
        id=uuid.uuid4().hex,
        conversation_url=url,
        text=text,
        new_conversation=new_conversation,
        attachment_path=path,
        attachment_image=image,
        attachment_name=name,
        attachment_token=token,
        attachment_owner=owner,
        attachment_mime=mime,
        attachment_kind=kind,
        attachment_size_bytes=size_bytes,
        conversation_key=conversation_key,
        session_id=lease.session_id,
        lease=lease,
    )
    try:
        _runs[run.id] = run
        _emit(run, "status", {"state": run.state})
        payload = run.public()
        run.task = asyncio.create_task(_run_chat(run))
        return payload
    except BaseException:
        _runs.pop(run.id, None)
        await lease.release()
        raise


@router.post("/chat/attachments", status_code=201)
async def upload_attachment(body: AttachmentUploadIn) -> dict[str, Any]:
    """Validate + store an attachment (P3). Two modes: base64 from the
    browser picker, or a direct local path. Official ChatGPT limits are
    pre-checked; the error is precise and in French."""
    try:
        if body.path:
            return attachments.stage_path(body.path)
        if body.name and body.data_b64:
            return attachments.store_upload(body.name, body.data_b64)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    raise HTTPException(status_code=422, detail="fournis soit path, soit name + data_b64")


@router.get("/chat/attachments/raw")
async def attachment_raw(token: str = Query(..., min_length=1)) -> Any:
    """Serve registered attachment bytes for the fetch-injection fallback.

    Only paths that passed validate_size this session are served (registry),
    with permissive CORS so the chatgpt.com page can fetch from loopback."""
    from fastapi.responses import FileResponse

    descriptor = attachments.resolve_token(token)
    if descriptor is None:
        raise HTTPException(status_code=404, detail="attachment token unknown or expired")
    return FileResponse(
        descriptor["path"],
        filename=descriptor["name"],
        headers={
            "Access-Control-Allow-Origin": "https://chatgpt.com",
            "Cache-Control": "no-store",
        },
    )


@router.post("/chat/send-with-attachment", status_code=202)
async def send_with_attachment(body: ChatSendAttachmentIn) -> dict[str, Any]:
    if missions_api._global_stop:
        raise HTTPException(status_code=409, detail="STOP EVERYTHING is active; reset it first")
    if not missions_api.optin_accepted():
        raise HTTPException(status_code=403, detail="Experimental ChatGPT Web Transport is not enabled")
    url = _validate_chatgpt_url(body.conversation_url)
    try:
        if body.path and body.data_b64 is not None:
            raise ValueError("fournis soit path, soit name + data_b64, pas les deux")
        if body.data_b64 is not None and body.name:
            descriptor = attachments.store_upload(body.name, body.data_b64)
        elif body.path:
            descriptor = attachments.stage_path(body.path)
        else:
            raise ValueError("fournis soit path, soit name + data_b64")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    try:
        return await _start_attachment_run(
            url=url,
            text=body.text,
            path=descriptor["path"],
            image=body.image or descriptor["kind"] == "image",
            name=descriptor["name"],
            new_conversation=body.new_conversation,
            token=descriptor["token"],
            owner=descriptor["owner"],
            mime=descriptor["mime"],
            kind=descriptor["kind"],
            size_bytes=descriptor["size_bytes"],
        )
    except BaseException:
        try:
            attachments.release_owned(
                descriptor["path"],
                token=descriptor["token"],
            )
        except Exception:
            pass
        raise


def _workspace_context_file(workspace: str, relative_path: str | None) -> Path:
    """Resolve a context proposal without allowing an escape from workspace."""
    if not isinstance(workspace, str) or not workspace.strip():
        raise HTTPException(status_code=422, detail="workspace must not be empty")
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise HTTPException(status_code=422, detail="context file path is required")
    candidate_input = Path(relative_path.strip())
    if candidate_input.is_absolute() or "\x00" in relative_path or ".." in candidate_input.parts:
        raise HTTPException(status_code=422, detail="context file path must stay relative to workspace")
    try:
        root = Path(workspace).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        raise HTTPException(status_code=422, detail="workspace does not exist")
    if not root.is_dir():
        raise HTTPException(status_code=422, detail="workspace must be a directory")
    try:
        resolved = (root / candidate_input).resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        raise HTTPException(status_code=422, detail="context file path escapes workspace")
    if not resolved.is_file():
        raise HTTPException(status_code=422, detail="context file must be a regular file")
    return resolved


@router.post("/chat/approve-context", status_code=202)
async def approve_context(body: ContextApprovalIn) -> dict[str, Any]:
    """Send one user-approved context item to the selected ChatGPT conversation.

    The endpoint is intentionally separate from the marker parser: seeing a
    request in an assistant message never sends anything. A caller must make
    this explicit approval request for each item.
    """
    request_id = _validate_context_identity(body.request_id, "context request_id")
    item_id = _validate_context_identity(body.item_id, "context item_id")
    if body.item.id != item_id:
        raise HTTPException(status_code=422, detail="context item_id does not match item.id")
    reason = body.item.reason.strip()
    if not reason or len(reason) > 500:
        raise HTTPException(status_code=422, detail="context reason must be 1–500 characters")
    url = _validate_chatgpt_url(body.conversation_url)
    try:
        requested_workspace = Path(body.workspace).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        raise HTTPException(status_code=422, detail="workspace does not exist")
    if not requested_workspace.is_dir():
        raise HTTPException(status_code=422, detail="workspace must be a directory")
    validated_file_path: Path | None = None
    validated_link: str | None = None
    if body.item.kind == "file":
        # Keep malformed/traversal input a local 422 even when the caller has
        # not yet presented a server-observed request identity.
        validated_file_path = _workspace_context_file(body.workspace, body.item.path)
    elif body.item.kind == "link":
        validated_link = (body.item.url or "").strip()
        if not re.match(r"^https?://[^\s]+$", validated_link, re.IGNORECASE):
            raise HTTPException(status_code=422, detail="context link must use http(s)")
    else:
        target = (body.item.target or "").strip()
        if target not in {"current_chatgpt", "current_conversation"}:
            raise HTTPException(status_code=422, detail="unsupported screenshot target")
    observed = _observed_context_registry.get(
        (_context_conversation_key(url), request_id, item_id)
    )
    if observed is None:
        raise HTTPException(
            status_code=409,
            detail="context request was not observed in the selected ChatGPT conversation",
        )
    if requested_workspace != Path(str(observed["workspace"])):
        raise HTTPException(
            status_code=409,
            detail="context approval workspace does not match the authorized workspace",
        )
    observed_item = observed.get("item")
    submitted_item = body.item.model_dump(exclude_none=True)
    if not isinstance(observed_item, dict) or any(
        observed_item.get(key) != submitted_item.get(key)
        for key in ("id", "kind", "reason", "path", "target", "url")
        if observed_item.get(key) is not None or submitted_item.get(key) is not None
    ):
        raise HTTPException(
            status_code=409,
            detail="context approval item does not match the observed ChatGPT request",
        )
    context_note = body.text.strip()
    note = f"Contexte autorisé par l'utilisateur ({reason})"
    if context_note:
        note = f"{context_note}\n{note}"
    workspace_key = str(requested_workspace)
    approval_key = (url, workspace_key, request_id, item_id)

    async with _context_approval_lock():
        previous = _context_approval_registry.get(approval_key)
        if previous is not None:
            duplicate = dict(previous)
            duplicate["idempotent"] = True
            return duplicate

        if body.item.kind == "file":
            path = validated_file_path
            if path is None:  # defensive; the branch above always initializes it
                raise HTTPException(status_code=422, detail="context file path is required")
            result = await send_with_attachment(ChatSendAttachmentIn(
                conversation_url=url,
                text=note,
                path=str(path),
                image=False,
                name=path.name,
                new_conversation=body.new_conversation,
            ))
        elif body.item.kind == "link":
            target = validated_link
            if target is None:  # defensive; the branch above always initializes it
                raise HTTPException(status_code=422, detail="context link must use http(s)")
            result = await send_chat(ChatSendIn(
                conversation_url=url,
                text=f"{note}\nLien demandé : {target}",
                new_conversation=body.new_conversation,
            ))
        else:
            result = await send_screenshot(ChatScreenshotIn(
                conversation_url=url,
                text=note,
                new_conversation=body.new_conversation,
            ))

        response = dict(result) if isinstance(result, dict) else {"result": result}
        response.update({
            "context_request_id": request_id,
            "context_item_id": item_id,
            "idempotent": False,
        })
        _context_approval_registry[approval_key] = dict(response)
        return response


@router.post("/chat/send-screenshot", status_code=202)
async def send_screenshot(body: ChatScreenshotIn) -> dict[str, Any]:
    """Select the requested target, validate its driver capture, then send."""
    if missions_api._global_stop:
        raise HTTPException(status_code=409, detail="STOP EVERYTHING is active; reset it first")
    if not missions_api.optin_accepted():
        raise HTTPException(status_code=403, detail="Experimental ChatGPT Web Transport is not enabled")
    url = _validate_chatgpt_url(body.conversation_url)
    transport: ChatGPTWebTransport | None = None
    target: Path | None = None
    descriptor: dict[str, Any] | None = None
    try:
        # Read-only browser sessions share one physical Chrome tab. Keep route
        # selection and pixel capture in the same operation lock used by
        # conversation snapshots, otherwise a concurrent view can retarget the
        # tab between these two steps and leak another conversation's pixels.
        async with _view_operation_lock():
            transport = _make_transport(SCREENSHOT_SESSION_ID)
            try:
                shooter = getattr(transport.driver, "take_screenshot", None)
                if shooter is None:
                    raise HTTPException(status_code=422, detail="ce transport ne sait pas capturer d'écran")
                try:
                    if url.rstrip("/") == "https://chatgpt.com":
                        await transport.start_new_conversation(url)
                    else:
                        await transport.select_conversation(url)
                except Exception as exc:
                    raise HTTPException(status_code=503, detail=f"conversation cible introuvable: {exc}")
                attachments.ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
                target = attachments.ATTACHMENTS_DIR / f"cortex-screenshot-{uuid.uuid4().hex[:8]}.png"
                try:
                    result = await shooter(str(target))
                    if not isinstance(result, dict) or not result.get("path"):
                        raise ValueError("le pilote n'a pas confirmé le chemin de capture")
                    descriptor = attachments.describe_screenshot(
                        str(result["path"]),
                        expected_path=str(target),
                    )
                except Exception as exc:
                    target.unlink(missing_ok=True)
                    raise HTTPException(status_code=503, detail=f"capture impossible: {exc}")
            finally:
                closer = getattr(transport, "close", None)
                if callable(closer):
                    try:
                        await closer()
                    except Exception:
                        pass
    except BaseException:
        if descriptor is not None:
            try:
                attachments.release_owned(
                    descriptor["path"],
                    token=descriptor["token"],
                )
            except Exception:
                pass
        elif target is not None:
            target.unlink(missing_ok=True)
        raise
    if descriptor is None:  # pragma: no cover - defensive
        raise HTTPException(status_code=503, detail="capture impossible: descripteur absent")
    try:
        return await _start_attachment_run(
            url=url,
            text=body.text,
            path=descriptor["path"],
            image=True,
            name=descriptor["name"],
            new_conversation=body.new_conversation,
            token=descriptor["token"],
            owner=descriptor["owner"],
            mime=descriptor["mime"],
            kind=descriptor["kind"],
            size_bytes=descriptor["size_bytes"],
        )
    except BaseException:
        try:
            attachments.release_owned(
                descriptor["path"],
                token=descriptor["token"],
            )
        except Exception:
            pass
        raise


@router.get("/transport/capabilities")
async def transport_capabilities() -> dict[str, Any]:
    """What the active transport can do (P3) — the UI adapts from this."""
    from transport.chatgpt_web import adapter as adapter_mod

    transport = _make_transport(READ_ONLY_SESSION_ID)
    caps_fn = getattr(transport.driver, "capabilities", None)
    caps = dict(caps_fn()) if caps_fn else {"send_text": True, "upload_file": False, "upload_image": False, "take_screenshot": False}
    driver_limits = caps.get("limits") if isinstance(caps.get("limits"), dict) else {}

    def bounded_limit(value: Any, intake_limit: int) -> int:
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return min(value, intake_limit)
        return intake_limit

    caps["limits"] = {
        "file_bytes": bounded_limit(
            driver_limits.get("file_bytes"), adapter_mod.MAX_FILE_BYTES
        ),
        "image_bytes": bounded_limit(
            driver_limits.get("image_bytes"), adapter_mod.MAX_IMAGE_BYTES
        ),
    }
    return caps


@router.get("/chat/runs")
async def list_chat_runs() -> list[dict[str, Any]]:
    return [run.public() for run in reversed(list(_runs.values()))]


@router.get("/chat/runs/{run_id}")
async def get_chat_run(run_id: str) -> dict[str, Any]:
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="chat run not found")
    return run.public()


@router.get("/chat/runs/{run_id}/events")
async def chat_run_events(run_id: str) -> StreamingResponse:
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="chat run not found")

    async def stream():
        sent = 0
        idle_ticks = 0
        while True:
            while sent < len(run.events):
                event = run.events[sent]
                sent += 1
                yield f"id: {event['seq']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                idle_ticks = 0
            if run.state in {"COMPLETED", "FAILED", "CANCELLED"} and sent >= len(run.events):
                return
            idle_ticks += 1
            if idle_ticks >= 30:
                yield ": heartbeat\n\n"
                idle_ticks = 0
            await asyncio.sleep(0.25)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/runs/{run_id}/cancel")
async def cancel_chat_run(run_id: str, body: ChatCancelIn | None = None) -> dict[str, Any]:
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="chat run not found")
    if run.state in {"COMPLETED", "FAILED", "CANCELLED"}:
        if run.lease is not None:
            await run.lease.release()
        return run.public()
    run.cancelled = True
    if run.transport is not None:
        await run.transport.cancel_generation()
    if run.task is not None and not run.task.done():
        run.task.cancel()
    _set_state(run, "CANCELLED")
    _emit(run, "cancelled", {"reason": body.reason if body else "USER_CANCEL"})
    if run.task is not None:
        await asyncio.gather(run.task, return_exceptions=True)
    elif run.lease is not None:
        await run.lease.release()
    return run.public()
