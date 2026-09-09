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
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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


class ChatCancelIn(BaseModel):
    reason: str = "USER_CANCEL"


# Read-only browsing always uses a session outside the bounded writer registry.
READ_ONLY_SESSION_ID = "cortex-view-read-only"
SCREENSHOT_SESSION_ID = "cortex-capture-read-only"
TRANSPORT_SNAPSHOT_BUDGET_SECONDS = 8.0
SNAPSHOT_ACQUISITION_TIMEOUT = "SNAPSHOT_ACQUISITION_TIMEOUT"
# Reserve a small local release window inside the one route budget.  This is
# an engineering allowance for the extension's session-map ACK, not a latency
# guarantee; selection retains 7.9 seconds of the 8 second acquisition budget.
SNAPSHOT_CANDIDATE_CLEANUP_RESERVE_SECONDS = 0.1
ui_transport_factory = create_transport


@dataclass
class _UnpublishedViewCandidate:
    """Own a reader until it is either released or safely published."""

    transport: Any
    cleanup_state: str = "owned"

_runs: dict[str, ChatRunRuntime] = {}
_view_transport: ChatGPTWebTransport | None = None
_view_url: str | None = None
_view_cleanup_candidate: _UnpublishedViewCandidate | None = None
_view_mutex = asyncio.Lock()
_view_operation_mutex: asyncio.Lock | None = None
_view_operation_loop: asyncio.AbstractEventLoop | None = None


def _view_operation_lock() -> asyncio.Lock:
    """Return the shared read-surface lock for the current event loop."""
    global _view_operation_mutex, _view_operation_loop
    loop = asyncio.get_running_loop()
    if _view_operation_mutex is None or _view_operation_loop is not loop:
        _view_operation_mutex = asyncio.Lock()
        _view_operation_loop = loop
    return _view_operation_mutex


def _snapshot_remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TransportError(
            SNAPSHOT_ACQUISITION_TIMEOUT,
            "conversation snapshot acquisition exceeded its 8 second budget",
            details={"retryable": True},
        )
    return remaining


async def _await_snapshot_stage(awaitable, deadline: float):
    """Await one read-only stage without allowing it to reset the route budget."""
    try:
        remaining = _snapshot_remaining(deadline)
    except BaseException:
        # A coroutine may have been constructed by a caller immediately before
        # discovering that the absolute budget elapsed.  Dispose of that
        # unopened coroutine rather than warning or accidentally running it.
        dispose = getattr(awaitable, "close", None)
        if dispose is not None:
            dispose()
        raise
    try:
        result = await asyncio.wait_for(awaitable, timeout=remaining)
    except asyncio.TimeoutError as exc:
        raise TransportError(
            SNAPSHOT_ACQUISITION_TIMEOUT,
            "conversation snapshot acquisition exceeded its 8 second budget",
            details={"retryable": True},
        ) from exc
    except TransportError as exc:
        if time.monotonic() >= deadline:
            raise TransportError(
                SNAPSHOT_ACQUISITION_TIMEOUT,
                "conversation snapshot acquisition exceeded its 8 second budget",
                details={"retryable": True},
            ) from exc
        raise
    _snapshot_remaining(deadline)
    return result


async def _select_view_conversation(
    transport: ChatGPTWebTransport,
    url: str,
    deadline: float,
) -> None:
    if isinstance(transport, ChatGPTWebTransport):
        if url.rstrip("/") == "https://chatgpt.com":
            await _await_snapshot_stage(
                transport.start_new_conversation(url, deadline=deadline),
                deadline,
            )
        else:
            await _await_snapshot_stage(
                transport.select_conversation(url, deadline=deadline),
                deadline,
            )
        return
    if url.rstrip("/") == "https://chatgpt.com":
        await _await_snapshot_stage(transport.start_new_conversation(url), deadline)
    else:
        await _await_snapshot_stage(transport.select_conversation(url), deadline)


def _candidate_selection_deadline(deadline: float) -> float:
    """Keep a small portion of the original deadline for candidate release."""
    selection_deadline = deadline - SNAPSHOT_CANDIDATE_CLEANUP_RESERVE_SECONDS
    if selection_deadline <= time.monotonic():
        _snapshot_remaining(deadline)
        raise TransportError(
            SNAPSHOT_ACQUISITION_TIMEOUT,
            "conversation snapshot acquisition has no time left to release a candidate",
            details={"retryable": True},
        )
    return selection_deadline


async def _close_unpublished_view_candidate(
    candidate: _UnpublishedViewCandidate,
    deadline: float,
) -> None:
    """Release the owned candidate inside the route deadline, or retain it."""
    candidate.cleanup_state = "closing"
    try:
        if isinstance(candidate.transport, ChatGPTWebTransport):
            await _await_snapshot_stage(
                candidate.transport.close(deadline=deadline),
                deadline,
            )
        else:
            await _await_snapshot_stage(candidate.transport.close(), deadline)
    except BaseException:
        candidate.cleanup_state = "cleanup_pending"
        raise
    candidate.cleanup_state = "closed"


async def _reconcile_view_cleanup_candidate(deadline: float) -> None:
    """Do not create another reader until the prior candidate is confirmed closed."""
    global _view_cleanup_candidate
    candidate = _view_cleanup_candidate
    if candidate is None:
        return
    try:
        await _close_unpublished_view_candidate(candidate, deadline)
    except asyncio.CancelledError:
        raise
    except BaseException as exc:
        raise TransportError(
            SNAPSHOT_ACQUISITION_TIMEOUT,
            "conversation snapshot candidate cleanup pending; retry required",
            details={"retryable": True, "cleanup_state": candidate.cleanup_state},
        ) from exc
    _view_cleanup_candidate = None


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
    deadline: float | None = None,
) -> ChatGPTWebTransport:
    global _view_cleanup_candidate, _view_transport, _view_url
    if deadline is None:
        deadline = time.monotonic() + TRANSPORT_SNAPSHOT_BUDGET_SECONDS
    await _await_snapshot_stage(_view_mutex.acquire(), deadline)
    try:
        await _reconcile_view_cleanup_candidate(deadline)
        if (
            not force_recreate
            and _view_transport is not None
            and _view_url == url
        ):
            return _view_transport
        previous = _view_transport
        selection_deadline = _candidate_selection_deadline(deadline)
        if previous is not None:
            # The transport factory may wrap its cached live driver again for
            # this constant session ID. Release the published generation before
            # asking the factory for its successor, otherwise closing the old
            # wrapper can close the newly published reader as well.
            previous_cleanup = _UnpublishedViewCandidate(
                previous,
                cleanup_state="published",
            )
            _view_transport = None
            _view_url = None
            try:
                await _close_unpublished_view_candidate(
                    previous_cleanup,
                    selection_deadline,
                )
            except asyncio.CancelledError:
                _view_cleanup_candidate = previous_cleanup
                raise
            except BaseException as cleanup_error:
                _view_cleanup_candidate = previous_cleanup
                raise TransportError(
                    SNAPSHOT_ACQUISITION_TIMEOUT,
                    "conversation snapshot candidate cleanup pending; retry required",
                    details={
                        "retryable": True,
                        "cleanup_state": previous_cleanup.cleanup_state,
                    },
                ) from cleanup_error
            _snapshot_remaining(selection_deadline)
        candidate = _UnpublishedViewCandidate(
            _make_transport(READ_ONLY_SESSION_ID)
        )
        try:
            await _select_view_conversation(
                candidate.transport,
                url,
                selection_deadline,
            )
        except BaseException as selection_error:
            # A candidate is never published after a failed or cancelled
            # selection.  If its release cannot be confirmed, retain the one
            # owner so the next request reconciles it before creating another.
            try:
                await _close_unpublished_view_candidate(candidate, deadline)
            except asyncio.CancelledError:
                _view_cleanup_candidate = candidate
                raise
            except BaseException as cleanup_error:
                _view_cleanup_candidate = candidate
                if isinstance(selection_error, asyncio.CancelledError):
                    raise selection_error
                raise TransportError(
                    SNAPSHOT_ACQUISITION_TIMEOUT,
                    "conversation snapshot candidate cleanup pending; retry required",
                    details={
                        "retryable": True,
                        "cleanup_state": candidate.cleanup_state,
                    },
                ) from cleanup_error
            raise
        if candidate.cleanup_state != "owned":
            raise RuntimeError("cannot publish a released view candidate")
        _view_transport = candidate.transport
        _view_url = url
        candidate.cleanup_state = "published"
        return candidate.transport
    finally:
        _view_mutex.release()


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

        final = await transport.stream_response(on_update)
        if run.cancelled:
            raise TransportError(GENERATION_CANCELLED, "cancelled during response")
        run.response_text = str(final.get("text") or "")
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
    deadline = time.monotonic() + TRANSPORT_SNAPSHOT_BUDGET_SECONDS

    async def read_snapshot(transport: ChatGPTWebTransport) -> dict[str, Any]:
        if light:
            if isinstance(transport, ChatGPTWebTransport):
                light_state = await _await_snapshot_stage(
                    transport._light_state(deadline=deadline),
                    deadline,
                )
            else:
                light_state = await _await_snapshot_stage(transport._light_state(), deadline)
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
        if isinstance(transport, ChatGPTWebTransport):
            state = await _await_snapshot_stage(
                transport.snapshot(
                    verify_lock=clean_url.rstrip("/") != "https://chatgpt.com",
                    deadline=deadline,
                ),
                deadline,
            )
        else:
            state = await _await_snapshot_stage(
                transport.snapshot(
                    verify_lock=clean_url.rstrip("/") != "https://chatgpt.com"
                ),
                deadline,
            )
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
        operation_lock = _view_operation_lock()
        await _await_snapshot_stage(operation_lock.acquire(), deadline)
        try:
            transport = await _ensure_view_transport(clean_url, deadline=deadline)
            try:
                return await read_snapshot(transport)
            except TransportError as exc:
                if exc.code == SNAPSHOT_ACQUISITION_TIMEOUT:
                    raise
                if exc.code not in {TAB_CLOSED, CONVERSATION_MISMATCH}:
                    raise
                recovered = await _ensure_view_transport(
                    clean_url,
                    force_recreate=True,
                    deadline=deadline,
                )
                return await read_snapshot(recovered)
        finally:
            operation_lock.release()
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
