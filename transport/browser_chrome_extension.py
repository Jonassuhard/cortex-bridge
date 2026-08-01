"""BrowserDriver implementation backed by the paired Chrome extension."""

from __future__ import annotations

import asyncio
import base64
import mimetypes
import os
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

try:
    from chrome_extension import (
        BridgeProtocolError,
        ChromeExtensionManager,
        chrome_extension_manager,
    )
    from cortex_paths import build_paths
except ModuleNotFoundError:
    from console.chrome_extension import (
        BridgeProtocolError,
        ChromeExtensionManager,
        chrome_extension_manager,
    )
    from console.cortex_paths import build_paths

from transport.chatgpt_web.adapter import DriverError, TabClosedError


RUNTIME_PATHS = build_paths()
EXTENSION_FILE_LIMIT_BYTES = 25 * 1024 * 1024
TRANSFER_CHUNK_CHARACTERS = 256 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CONTENT_SCRIPT_RETRY_DELAY_SECONDS = 0.25
CONTENT_SCRIPT_READ_ACTIONS = frozenset(
    {
        "probe",
        "get_state",
        "get_light_state",
        "list_conversations",
        "list_models",
    }
)


class ChromeExtensionBrowserDriver:
    driver_name = "chrome_extension"
    supports_raw_evaluation = False
    requires_content_stability = True

    def __init__(
        self,
        *,
        session: str,
        manager: ChromeExtensionManager = chrome_extension_manager,
        allowed_root: str | Path | None = None,
        retry_sleep: Callable[[float], Awaitable[None] | None] = asyncio.sleep,
    ) -> None:
        self.session = session
        self.manager = manager
        self.allowed_root = Path(allowed_root or RUNTIME_PATHS.home).expanduser().resolve()
        self._retry_sleep = retry_sleep
        self.target_url: str | None = None
        self._closed = False

    async def _command(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float = 10.0,
    ) -> Any:
        if self._closed and action != "list_tabs":
            raise TabClosedError("Chrome extension driver session is closed")
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DriverError(
                    f"TAB_UNAVAILABLE: ChatGPT did not become ready within {timeout:g} seconds"
                )
            try:
                return await self.manager.command(
                    self.session,
                    action,
                    payload or {},
                    remaining,
                )
            except Exception as exc:
                code = getattr(exc, "code", None)
                if code == "TAB_CLOSED":
                    raise TabClosedError(str(exc)) from exc
                if (
                    code == "TAB_UNAVAILABLE"
                    and action in CONTENT_SCRIPT_READ_ACTIONS
                    and remaining > CONTENT_SCRIPT_RETRY_DELAY_SECONDS
                ):
                    pending_sleep = self._retry_sleep(
                        min(CONTENT_SCRIPT_RETRY_DELAY_SECONDS, remaining)
                    )
                    if pending_sleep is not None:
                        await pending_sleep
                    continue
                if code:
                    error = DriverError(f"{code}: {exc}")
                    error.code = code
                    raise error from exc
                raise

    async def navigate(self, url: str) -> None:
        result = await self._command("navigate", {"url": url}, timeout=10)
        self.target_url = str((result or {}).get("url") or url)
        await self._wait_until_page_ready(timeout=10)

    async def _wait_until_page_ready(self, *, timeout: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DriverError(
                    f"TAB_UNAVAILABLE: ChatGPT composer did not become ready within {timeout:g} seconds"
                )
            state = await self._command("get_state", timeout=remaining)
            if not isinstance(state, dict):
                raise DriverError("Chrome extension returned an invalid page state")
            if state.get("composer_present") or state.get("blocker"):
                return state
            pending_sleep = self._retry_sleep(
                min(CONTENT_SCRIPT_RETRY_DELAY_SECONDS, remaining)
            )
            if pending_sleep is not None:
                await pending_sleep

    async def evaluate(self, code: str, timeout: float = 30) -> Any:
        del code, timeout
        raise DriverError(
            "raw evaluation is unavailable on the Chrome extension transport"
        )

    async def list_tabs(self) -> list[dict[str, Any]]:
        result = await self._command("list_tabs", timeout=5)
        if isinstance(result, dict):
            return list(result.get("tabs") or [])
        return list(result or [])

    async def spa_navigate(self, url: str) -> bool:
        try:
            result = await self._command("spa_navigate", {"url": url}, timeout=10)
        except TabClosedError:
            # Selection is read-only at this point. Recreate the dedicated
            # tab before any user message is attempted.
            await self.navigate(url)
            return True
        except DriverError as exc:
            if getattr(exc, "code", None) != "TAB_UNAVAILABLE":
                raise
            # A fresh writer session has no tab yet. Full navigation safely
            # creates its dedicated tab; no user message is involved.
            await self.navigate(url)
            return True
        handled = bool((result or {}).get("handled"))
        if handled:
            self.target_url = url
        return handled

    async def get_state(self) -> dict[str, Any]:
        result = await self._command("get_state", timeout=10)
        if not isinstance(result, dict):
            raise DriverError("Chrome extension returned an invalid page state")
        return result

    async def get_light_state(self) -> dict[str, Any]:
        result = await self._command("get_light_state", timeout=5)
        if not isinstance(result, dict):
            raise DriverError("Chrome extension returned an invalid light state")
        return result

    async def send_message(self, text: str) -> None:
        result = await self._command("send_text", {"text": text}, timeout=60)
        if isinstance(result, dict) and result.get("ok") is False:
            raise DriverError(str(result.get("error") or "ChatGPT send was rejected"))

    async def press_stop(self) -> None:
        await self._command("press_stop", timeout=10)

    async def focus_tab(self) -> None:
        await self._command("focus_tab", timeout=10)

    async def list_conversations(self) -> list[dict[str, Any]]:
        result = await self._command("list_conversations", timeout=10)
        if isinstance(result, dict):
            rows = result.get("conversations") or []
        else:
            rows = result or []
        return list(rows)[:50]

    async def probe(self) -> dict[str, Any]:
        result = await self._command("probe", timeout=10)
        if not isinstance(result, dict):
            raise DriverError("Chrome extension returned an invalid probe")
        return result

    def capabilities(self) -> dict[str, Any]:
        return {
            "send_text": True,
            "upload_file": True,
            "upload_image": True,
            "take_screenshot": True,
            "limits": {
                "file_bytes": EXTENSION_FILE_LIMIT_BYTES,
                "image_bytes": EXTENSION_FILE_LIMIT_BYTES,
            },
        }

    def _managed_file(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute() or candidate.is_symlink():
            raise DriverError("attachment must be inside the managed staging directory")
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.allowed_root)
        except ValueError as exc:
            raise DriverError(
                "attachment must be inside the managed staging directory"
            ) from exc
        if not resolved.is_file():
            raise DriverError("staged attachment does not exist")
        return resolved

    async def upload_files(self, selector: str, paths: list[str]) -> None:
        del selector
        if len(paths) != 1:
            raise DriverError("the Chrome extension accepts one attachment at a time")
        path = self._managed_file(paths[0])
        size = path.stat().st_size
        if size > EXTENSION_FILE_LIMIT_BYTES:
            raise DriverError("attachment exceeds the 25 MiB Chrome bridge limit")
        transfer_id = uuid.uuid4().hex
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        await self._command(
            "attachment_begin",
            {
                "transfer_id": transfer_id,
                "name": path.name,
                "mime": mime,
                "size": size,
            },
            timeout=10,
        )
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        for offset in range(0, len(encoded), TRANSFER_CHUNK_CHARACTERS):
            await self._command(
                "attachment_chunk",
                {
                    "transfer_id": transfer_id,
                    "index": offset // TRANSFER_CHUNK_CHARACTERS,
                    "data": encoded[offset : offset + TRANSFER_CHUNK_CHARACTERS],
                },
                timeout=10,
            )
        await self._command(
            "attachment_commit",
            {"transfer_id": transfer_id},
            timeout=30,
        )

    async def await_attachment(self) -> dict[str, Any]:
        result = await self._command("await_attachment", timeout=70)
        return dict(result or {})

    async def send_bare(self) -> dict[str, Any]:
        result = await self._command("send_bare", timeout=30)
        return dict(result or {})

    def _managed_destination(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            raise DriverError("screenshot path must be absolute")
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.allowed_root)
        except ValueError as exc:
            raise DriverError("screenshot path must remain inside CORTEX_HOME") from exc
        current = resolved.parent
        while current != self.allowed_root:
            if current.is_symlink():
                raise DriverError("screenshot path must not contain symlinks")
            current = current.parent
        return resolved

    async def take_screenshot(self, path: str) -> dict[str, Any]:
        destination = self._managed_destination(path)
        result = await self._command("capture_screenshot", timeout=30)
        data_url = str((result or {}).get("data_url") or "")
        prefix = "data:image/png;base64,"
        if not data_url.startswith(prefix):
            raise DriverError("Chrome extension returned an invalid screenshot")
        try:
            data = base64.b64decode(data_url[len(prefix) :], validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise DriverError("Chrome extension returned invalid PNG data") from exc
        if not data.startswith(PNG_SIGNATURE):
            raise DriverError("Chrome extension screenshot is not a PNG")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, destination)
        return {
            "path": str(destination),
            "bytes": len(data),
            "tab_id": (result or {}).get("tab_id"),
        }

    async def health(self) -> dict[str, Any]:
        status = self.manager.public_status()
        if not status.get("paired"):
            return {
                "connected": False,
                "tabs": 0,
                "driver": self.driver_name,
                "session": self.session,
                "state": status.get("state", "disconnected"),
            }
        try:
            tabs = await self.list_tabs()
        except DriverError as exc:
            return {
                "connected": False,
                "tabs": 0,
                "driver": self.driver_name,
                "session": self.session,
                "state": "disconnected",
                "error": str(exc),
            }
        return {
            "connected": True,
            "tabs": len(tabs),
            "driver": self.driver_name,
            "session": self.session,
            "state": "paired",
        }

    async def list_models(self) -> dict[str, Any]:
        result = await self._command("list_models", timeout=30)
        if not isinstance(result, dict):
            raise DriverError("Chrome extension returned an invalid model list")
        return {
            "current": result.get("selected") or result.get("current"),
            "models": list(result.get("models") or []),
        }

    async def select_model(self, label: str) -> str:
        result = await self._command("select_model", {"label": label}, timeout=40)
        return str((result or {}).get("selected") or label)

    async def close_tab(self) -> None:
        await self._command("close_tab", timeout=10)
        self.target_url = None

    async def close(self) -> None:
        # Closing a logical Cortex transport must never close or poison the
        # person's real Chrome tab. ``close_tab`` remains an explicit action.
        return None

    async def open_login(self) -> dict[str, Any]:
        opened = await self._command("open_chatgpt", timeout=10)
        self.target_url = str((opened or {}).get("url") or "https://chatgpt.com/")
        deadline = time.monotonic() + 10
        last_error: DriverError | None = None
        while time.monotonic() < deadline:
            try:
                probe = await self.probe()
                return {
                    "connected": True,
                    "tabs": 1,
                    "driver": self.driver_name,
                    "session": self.session,
                    "tab_id": (opened or {}).get("tab_id"),
                    "window_id": (opened or {}).get("window_id"),
                    "url": (opened or {}).get("url"),
                    "probe": probe,
                }
            except DriverError as exc:
                last_error = exc
                await asyncio.sleep(0.25)
        raise last_error or DriverError("ChatGPT did not become ready within 10 seconds")
