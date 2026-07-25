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
    GENERATION_CANCELLED,
    ChatGPTWebTransport,
    TransportError,
    WebBridgeDriver,
)

router = APIRouter(prefix="/api")
DATA_DIR = Path(__file__).resolve().parent / "data"
CHAT_RUNS_FILE = DATA_DIR / "chat-runs.json"


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
    created_at: str = field(default_factory=_now)
    delivered_at: str | None = None
    first_response_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    latency: dict[str, int | None] = field(default_factory=lambda: {
        "delivery_ms": None,
        "first_response_ms": None,
        "total_ms": None,
    })
    events: list[dict[str, Any]] = field(default_factory=list)
    event_seq: int = 0
    cancelled: bool = False
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
            "latency": self.latency,
        }


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
    path: str
    image: bool = False
    name: str | None = None
    new_conversation: bool = False


class ChatScreenshotIn(BaseModel):
    conversation_url: str
    text: str = ""
    new_conversation: bool = False


class ChatCancelIn(BaseModel):
    reason: str = "USER_CANCEL"


# A dedicated WebBridge session prevents UI browsing from moving the mission runner tab.
ui_transport_factory = lambda: ChatGPTWebTransport(  # noqa: E731
    WebBridgeDriver(session="cortex-bridge-ui")
)

_runs: dict[str, ChatRunRuntime] = {}
_view_transport: ChatGPTWebTransport | None = None
_view_url: str | None = None
_view_mutex = asyncio.Lock()


def _persist_runs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = [run.public() for run in list(_runs.values())[-100:]]
    tmp = CHAT_RUNS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CHAT_RUNS_FILE)


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


async def _ensure_view_transport(url: str) -> ChatGPTWebTransport:
    global _view_transport, _view_url
    async with _view_mutex:
        if _view_transport is not None and _view_url == url:
            return _view_transport
        transport = ui_transport_factory()
        if url.rstrip("/") == "https://chatgpt.com":
            await transport.start_new_conversation(url)
        else:
            await transport.select_conversation(url)
        _view_transport = transport
        _view_url = url
        return transport


async def _run_chat(run: ChatRunRuntime) -> None:
    started = time.monotonic()
    transport = ui_transport_factory()
    run.transport = transport
    try:
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

            port = os.environ.get("PORT", "8420")
            raw_url = f"http://127.0.0.1:{port}/api/chat/attachments/raw?path={quote(run.attachment_path)}"
            await transport.send_with_attachment(
                run.text, run.attachment_path, image=run.attachment_image, raw_url=raw_url
            )
        else:
            await transport.send_message(run.text)
        run.delivered_at = _now()
        run.latency["delivery_ms"] = _monotonic_ms(started)
        run.canonical_url = transport.lock.url if transport.lock else run.conversation_url
        _set_state(run, "VISIBLE_IN_CHATGPT")
        _emit(run, "delivery", {
            "delivered_at": run.delivered_at,
            "canonical_url": run.canonical_url,
            "latency_ms": run.latency["delivery_ms"],
        })
        _set_state(run, "WAITING_FOR_CHATGPT")

        last_visible = ""

        async def on_update(update: dict[str, Any]) -> None:
            nonlocal last_visible
            if run.cancelled:
                await transport.cancel_generation()
                return
            text = str(update.get("text") or "")
            if text and run.first_response_at is None:
                run.first_response_at = _now()
                run.latency["first_response_ms"] = _monotonic_ms(started)
            if text != last_visible or update.get("streaming"):
                last_visible = text
                run.response_text = text
                _set_state(run, "CHATGPT_STREAMING")
                _emit(run, "stream", {
                    "text": text,
                    "streaming": bool(update.get("streaming")),
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
        run.completed_at = _now()
        run.latency["total_ms"] = _monotonic_ms(started)
        if exc.code == GENERATION_CANCELLED or run.cancelled:
            _set_state(run, "CANCELLED")
            _emit(run, "cancelled", {"error": run.error})
        else:
            _set_state(run, "FAILED")
            _emit(run, "error", {"error": run.error, "code": exc.code})
    except Exception as exc:  # never leave a UI chat stuck forever
        run.error = f"CHAT_RUN_CRASHED: {exc}"
        run.completed_at = _now()
        run.latency["total_ms"] = _monotonic_ms(started)
        _set_state(run, "FAILED")
        _emit(run, "error", {"error": run.error, "code": "CHAT_RUN_CRASHED"})
    finally:
        _persist_runs()


@router.get("/conversations/snapshot")
async def conversation_snapshot(url: str = Query(..., min_length=1), light: int = 0) -> dict[str, Any]:
    """Read one selected conversation through a dedicated read-only UI session.

    light=1 returns identity/count/streaming only (P0c) — the UI polls this
    cheaply and fetches the full snapshot only when the signature changes."""
    clean_url = _validate_chatgpt_url(url)
    try:
        transport = await _ensure_view_transport(clean_url)
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
        state = await transport.snapshot(verify_lock=clean_url.rstrip("/") != "https://chatgpt.com")
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
    # P2b: at most two WRITE conversations at once (reading is unlimited).
    allowed, _active = write_slots.write_slot_available(url)
    if not allowed:
        raise HTTPException(status_code=409, detail=write_slots.REFUSAL_MESSAGE)
    run = ChatRunRuntime(
        id=uuid.uuid4().hex,
        conversation_url=url,
        text=text,
        new_conversation=body.new_conversation,
    )
    _runs[run.id] = run
    _emit(run, "status", {"state": run.state})
    run.task = asyncio.create_task(_run_chat(run))
    return run.public()


def list_active_runs() -> list[ChatRunRuntime]:
    """Non-terminal chat runs — used by the two-write-conversation guard."""
    return [run for run in _runs.values() if run.state not in {"COMPLETED", "FAILED", "CANCELLED"}]


def _start_attachment_run(
    *, url: str, text: str, path: str, image: bool, name: str | None, new_conversation: bool
) -> dict[str, Any]:
    allowed, _active = write_slots.write_slot_available(url)
    if not allowed:
        raise HTTPException(status_code=409, detail=write_slots.REFUSAL_MESSAGE)
    run = ChatRunRuntime(
        id=uuid.uuid4().hex,
        conversation_url=url,
        text=text,
        new_conversation=new_conversation,
        attachment_path=path,
        attachment_image=image,
        attachment_name=name,
    )
    _runs[run.id] = run
    _emit(run, "status", {"state": run.state})
    run.task = asyncio.create_task(_run_chat(run))
    return run.public()


@router.post("/chat/attachments", status_code=201)
async def upload_attachment(body: AttachmentUploadIn) -> dict[str, Any]:
    """Validate + store an attachment (P3). Two modes: base64 from the
    browser picker, or a direct local path. Official ChatGPT limits are
    pre-checked; the error is precise and in French."""
    try:
        if body.path:
            return attachments.describe_path(body.path)
        if body.name and body.data_b64:
            return attachments.store_upload(body.name, body.data_b64)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    raise HTTPException(status_code=422, detail="fournis soit path, soit name + data_b64")


@router.get("/chat/attachments/raw")
async def attachment_raw(path: str = Query(..., min_length=1)) -> Any:
    """Serve registered attachment bytes for the fetch-injection fallback.

    Only paths that passed validate_size this session are served (registry),
    with permissive CORS so the chatgpt.com page can fetch from loopback."""
    from fastapi.responses import FileResponse

    name = attachments.allowed_name(path)
    if name is None:
        raise HTTPException(status_code=404, detail="attachment not registered")
    return FileResponse(
        path,
        filename=name,
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"},
    )


@router.post("/chat/send-with-attachment", status_code=202)
async def send_with_attachment(body: ChatSendAttachmentIn) -> dict[str, Any]:
    if missions_api._global_stop:
        raise HTTPException(status_code=409, detail="STOP EVERYTHING is active; reset it first")
    if not missions_api.optin_accepted():
        raise HTTPException(status_code=403, detail="Experimental ChatGPT Web Transport is not enabled")
    url = _validate_chatgpt_url(body.conversation_url)
    try:
        descriptor = attachments.describe_path(body.path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _start_attachment_run(
        url=url,
        text=body.text,
        path=descriptor["path"],
        image=body.image or descriptor["kind"] == "image",
        name=body.name or descriptor["name"],
        new_conversation=body.new_conversation,
    )


@router.post("/chat/send-screenshot", status_code=202)
async def send_screenshot(body: ChatScreenshotIn) -> dict[str, Any]:
    """Capture the current ChatGPT tab and send it as an image (P3)."""
    if missions_api._global_stop:
        raise HTTPException(status_code=409, detail="STOP EVERYTHING is active; reset it first")
    if not missions_api.optin_accepted():
        raise HTTPException(status_code=403, detail="Experimental ChatGPT Web Transport is not enabled")
    url = _validate_chatgpt_url(body.conversation_url)
    transport = ui_transport_factory()
    shooter = getattr(transport.driver, "take_screenshot", None)
    if shooter is None:
        raise HTTPException(status_code=422, detail="ce transport ne sait pas capturer d'écran")
    attachments.ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    target = attachments.ATTACHMENTS_DIR / f"screenshot-{uuid.uuid4().hex[:8]}.png"
    try:
        await shooter(str(target))
        descriptor = attachments.describe_path(str(target))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"capture impossible: {exc}")
    return _start_attachment_run(
        url=url,
        text=body.text,
        path=descriptor["path"],
        image=True,
        name=descriptor["name"],
        new_conversation=body.new_conversation,
    )


@router.get("/transport/capabilities")
async def transport_capabilities() -> dict[str, Any]:
    """What the active transport can do (P3) — the UI adapts from this."""
    from transport.chatgpt_web import adapter as adapter_mod

    transport = ui_transport_factory()
    caps_fn = getattr(transport.driver, "capabilities", None)
    caps = caps_fn() if caps_fn else {"send_text": True, "upload_file": False, "upload_image": False, "take_screenshot": False}
    caps.setdefault("limits", {"file_bytes": adapter_mod.MAX_FILE_BYTES, "image_bytes": adapter_mod.MAX_IMAGE_BYTES})
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
        return run.public()
    run.cancelled = True
    if run.transport is not None:
        await run.transport.cancel_generation()
    if run.task is not None and not run.task.done():
        run.task.cancel()
    _set_state(run, "CANCELLED")
    _emit(run, "cancelled", {"reason": body.reason if body else "USER_CANCEL"})
    return run.public()
