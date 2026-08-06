"""Secure loopback channel for the Cortex Bridge Chrome extension.

The extension connects out to this process.  A browser page can authorize that
connection with a short-lived, single-use token, after which the backend may
send only the structured commands declared in ``ALLOWED_ACTIONS``.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


PAIRING_TTL_SECONDS = 60
DEFAULT_COMMAND_TIMEOUT_SECONDS = 10.0
MAX_MESSAGE_BYTES = 2 * 1024 * 1024
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})
EXTENSION_PROTOCOL_VERSION = 2

ALLOWED_ACTIONS = frozenset(
    {
        "open_chatgpt",
        "release_session",
        "focus_tab",
        "navigate",
        "list_tabs",
        "close_tab",
        "probe",
        "get_state",
        "get_light_state",
        "spa_navigate",
        "list_conversations",
        "send_text",
        "press_stop",
        "attachment_begin",
        "attachment_chunk",
        "attachment_commit",
        "await_attachment",
        "send_bare",
        "capture_screenshot",
        "list_models",
        "select_model",
    }
)


class JsonConnection(Protocol):
    async def send_json(self, payload: dict[str, Any]) -> None: ...


class BridgeProtocolError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PairingTicket:
    value: str
    expires_at: float
    expires_in_seconds: int = PAIRING_TTL_SECONDS


class ChromeExtensionManager:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        token_factory: Callable[[int], str] = secrets.token_urlsafe,
    ) -> None:
        self._clock = clock
        self._token_factory = token_factory
        self._tickets: dict[str, PairingTicket] = {}
        self._connection: JsonConnection | None = None
        self._extension_seen = False
        self._paired_at: float | None = None
        self._pending: dict[str, asyncio.Future[Any]] = {}
        self._last_seen_at: float | None = None
        self._send_lock = asyncio.Lock()
        self._extension_protocol_version: int | None = None
        self._protocol_compatible: bool | None = None

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def _remove_expired_tickets(self) -> None:
        now = self._clock()
        for value, ticket in list(self._tickets.items()):
            if ticket.expires_at < now:
                self._tickets.pop(value, None)

    def issue_pairing_token(self) -> PairingTicket:
        self._remove_expired_tickets()
        value = self._token_factory(32)
        ticket = PairingTicket(
            value=value,
            expires_at=self._clock() + PAIRING_TTL_SECONDS,
        )
        self._tickets[value] = ticket
        return ticket

    def issue_pairing_response(self) -> dict[str, Any]:
        ticket = self.issue_pairing_token()
        return {
            "token": ticket.value,
            "expires_in_seconds": ticket.expires_in_seconds,
        }

    def note_connection(self) -> None:
        self._extension_seen = True
        self._last_seen_at = self._clock()

    def consume_pairing_token(
        self,
        value: str,
        connection: JsonConnection,
    ) -> bool:
        self._remove_expired_tickets()
        ticket = self._tickets.pop(value, None)
        if ticket is None or ticket.expires_at < self._clock():
            return False
        previous = self._connection
        if previous is not None and previous is not connection:
            self.disconnect(previous)
        self._connection = connection
        self._extension_seen = True
        self._paired_at = self._clock()
        self._last_seen_at = self._paired_at
        return True

    def consume_pairing_message(
        self,
        message: dict[str, Any],
        connection: JsonConnection,
    ) -> tuple[bool, str]:
        raw_version = message.get("protocol_version")
        version = (
            raw_version
            if isinstance(raw_version, int) and not isinstance(raw_version, bool)
            else None
        )
        self._extension_seen = True
        self._last_seen_at = self._clock()
        protocol_compatible = version == EXTENSION_PROTOCOL_VERSION
        active_connection = self._connection
        if active_connection is None or active_connection is connection:
            self._extension_protocol_version = version
            self._protocol_compatible = protocol_compatible
        if not protocol_compatible:
            return False, "EXTENSION_PROTOCOL_MISMATCH"
        paired = self.consume_pairing_token(
            str(message.get("token") or ""),
            connection,
        )
        if paired:
            self._extension_protocol_version = version
            self._protocol_compatible = True
        return paired, "PAIRED" if paired else "PAIRING_REJECTED"

    def public_status(self) -> dict[str, Any]:
        self._remove_expired_tickets()
        if self._connection is not None:
            state = "paired"
        elif self._protocol_compatible is False:
            state = "extension_outdated"
        elif self._tickets:
            state = "awaiting_extension"
        elif self._extension_seen:
            state = "extension_detected"
        else:
            state = "disconnected"
        return {
            "state": state,
            "extension_connected": self._connection is not None,
            "paired": self._connection is not None,
            "pending_commands": len(self._pending),
            "protocol_compatible": self._protocol_compatible,
            "extension_protocol_version": self._extension_protocol_version,
            "required_protocol_version": EXTENSION_PROTOCOL_VERSION,
        }

    async def command(
        self,
        session: str,
        action: str,
        payload: dict[str, Any],
        timeout: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    ) -> Any:
        if action not in ALLOWED_ACTIONS:
            raise BridgeProtocolError(
                "COMMAND_NOT_ALLOWED",
                f"Chrome extension command is not allowed: {action}",
            )
        connection = self._connection
        if connection is None:
            raise BridgeProtocolError(
                "EXTENSION_UNPAIRED",
                "Chrome extension is not paired",
            )
        if timeout <= 0:
            raise BridgeProtocolError(
                "EXTENSION_TIMEOUT",
                "Chrome extension command timeout must be positive",
            )
        envelope = {
            "type": "command",
            "request_id": uuid.uuid4().hex,
            "session": session,
            "action": action,
            "payload": payload,
        }
        encoded = json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise BridgeProtocolError(
                "PAYLOAD_TOO_LARGE",
                "Chrome extension command exceeds the local message limit",
            )
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._pending[envelope["request_id"]] = future
        try:
            async with asyncio.timeout(timeout):
                async with self._send_lock:
                    if connection is not self._connection:
                        raise BridgeProtocolError(
                            "EXTENSION_DISCONNECTED",
                            "Chrome extension disconnected before sending a command",
                        )
                    await connection.send_json(envelope)
                return await future
        except asyncio.TimeoutError as exc:
            raise BridgeProtocolError(
                "EXTENSION_TIMEOUT",
                f"Chrome extension did not answer within {timeout:g} seconds",
            ) from exc
        except BridgeProtocolError:
            raise
        except Exception as exc:
            self.disconnect(connection)
            raise BridgeProtocolError(
                "EXTENSION_DISCONNECTED",
                "Chrome extension disconnected while sending a command",
            ) from exc
        finally:
            self._pending.pop(envelope["request_id"], None)

    def receive_result(
        self,
        connection: JsonConnection,
        message: dict[str, Any],
    ) -> bool:
        if connection is not self._connection:
            return False
        request_id = str(message.get("request_id") or "")
        future = self._pending.get(request_id)
        if future is None or future.done():
            return False
        self._last_seen_at = self._clock()
        if message.get("ok") is True:
            future.set_result(message.get("result"))
            return True
        raw_error = message.get("error")
        error = raw_error if isinstance(raw_error, dict) else {}
        future.set_exception(
            BridgeProtocolError(
                str(error.get("code") or "EXTENSION_COMMAND_FAILED"),
                str(error.get("message") or "Chrome extension command failed"),
            )
        )
        return True

    def disconnect(self, connection: JsonConnection) -> None:
        if connection is not self._connection:
            return
        self._connection = None
        self._extension_seen = False
        self._paired_at = None
        self._extension_protocol_version = None
        self._protocol_compatible = None
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(
                    BridgeProtocolError(
                        "EXTENSION_DISCONNECTED",
                        "Chrome extension disconnected",
                    )
                )

    async def handle_socket(self, websocket: WebSocket) -> None:
        client_host = websocket.client.host if websocket.client else ""
        origin = websocket.headers.get("origin", "")
        if client_host not in LOOPBACK_HOSTS or not origin.startswith("chrome-extension://"):
            await websocket.close(code=1008, reason="Cortex Bridge accepts local extensions only")
            return
        await websocket.accept()
        self.note_connection()
        try:
            while True:
                raw = await websocket.receive_text()
                if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
                    await websocket.close(code=1009, reason="message too large")
                    return
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json(
                        {"type": "protocol.error", "code": "INVALID_JSON"}
                    )
                    continue
                message_type = message.get("type")
                if message_type == "pair":
                    paired, code = self.consume_pairing_message(message, websocket)
                    await websocket.send_json(
                        {
                            "type": "pair.result",
                            "ok": paired,
                            "code": code,
                        }
                    )
                elif message_type == "bridge.heartbeat":
                    self._last_seen_at = self._clock()
                    await websocket.send_json({"type": "bridge.heartbeat.ack"})
                elif message_type == "command.result":
                    self.receive_result(websocket, message)
                else:
                    await websocket.send_json(
                        {"type": "protocol.error", "code": "MESSAGE_NOT_ALLOWED"}
                    )
        except WebSocketDisconnect:
            pass
        finally:
            self.disconnect(websocket)


chrome_extension_manager = ChromeExtensionManager()
router = APIRouter(prefix="/api")


@router.websocket("/chrome-extension/ws")
async def extension_socket(websocket: WebSocket) -> None:
    await chrome_extension_manager.handle_socket(websocket)


@router.post("/chrome-extension/pairing")
async def create_pairing() -> dict[str, Any]:
    return chrome_extension_manager.issue_pairing_response()


@router.get("/chrome-extension/status")
async def extension_status() -> dict[str, Any]:
    return chrome_extension_manager.public_status()
