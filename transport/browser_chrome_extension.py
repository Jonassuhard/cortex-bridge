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
CONTENT_SCRIPT_RECOVERY_FAILURES = 3
CONTENT_SCRIPT_WRITE_READY_TIMEOUT_SECONDS = 10.0
CONTENT_SCRIPT_NOT_READY_MESSAGE = "The ChatGPT content script is not available yet"
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
        self.selection_used_full_navigation = False
        self._closed = False
        self._pending_attachment_name: str | None = None

    @property
    def live(self) -> bool:
        return not self._closed

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
        unavailable_failures = 0
        recovery_attempted = False
        write_ready_deadline: float | None = None
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
                recoverable_read = (
                    action in CONTENT_SCRIPT_READ_ACTIONS
                    and bool(self.target_url)
                    and not recovery_attempted
                )
                if code == "TAB_CLOSED" and recoverable_read:
                    await self._recover_read_session(deadline)
                    recovery_attempted = True
                    continue
                if code == "TAB_CLOSED":
                    raise TabClosedError(str(exc)) from exc
                safe_pre_delivery_wait = (
                    action == "send_text"
                    and (
                        code == "PRE_DELIVERY_NOT_READY"
                        or (
                            code == "TAB_UNAVAILABLE"
                            and str(exc) == CONTENT_SCRIPT_NOT_READY_MESSAGE
                        )
                    )
                )
                if safe_pre_delivery_wait:
                    now = time.monotonic()
                    if write_ready_deadline is None:
                        write_ready_deadline = min(
                            deadline,
                            now + CONTENT_SCRIPT_WRITE_READY_TIMEOUT_SECONDS,
                        )
                    if now < write_ready_deadline:
                        pending_sleep = self._retry_sleep(
                            min(
                                CONTENT_SCRIPT_RETRY_DELAY_SECONDS,
                                write_ready_deadline - now,
                            )
                        )
                        if pending_sleep is not None:
                            await pending_sleep
                        continue
                if (
                    code == "TAB_UNAVAILABLE"
                    and action in CONTENT_SCRIPT_READ_ACTIONS
                    and remaining > CONTENT_SCRIPT_RETRY_DELAY_SECONDS
                ):
                    unavailable_failures += 1
                    if (
                        recoverable_read
                        and unavailable_failures >= CONTENT_SCRIPT_RECOVERY_FAILURES
                    ):
                        await self._recover_read_session(deadline)
                        recovery_attempted = True
                        continue
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

    async def _recover_read_session(self, deadline: float) -> None:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not self.target_url:
            raise DriverError("TAB_UNAVAILABLE: no time or canonical URL for recovery")
        try:
            await self.manager.command(
                self.session,
                "navigate",
                {"url": self.target_url},
                remaining,
            )
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code:
                error = DriverError(f"{code}: {exc}")
                error.code = code
                raise error from exc
            raise

    async def navigate(self, url: str) -> None:
        self.selection_used_full_navigation = True
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
        self.selection_used_full_navigation = False
        try:
            result = await self._command("spa_navigate", {"url": url}, timeout=10)
        except TabClosedError:
            # Selection is read-only at this point. Recreate the dedicated
            # tab before any user message is attempted. Do not wait for the
            # composer here: the adapter's identity poll is the authoritative
            # readiness check and shares the same absolute 10 s budget.
            result = await self._command("navigate", {"url": url}, timeout=10)
            self.target_url = str((result or {}).get("url") or url)
            self.selection_used_full_navigation = True
            return True
        except DriverError as exc:
            if getattr(exc, "code", None) != "TAB_UNAVAILABLE":
                raise
            # A fresh writer session has no tab yet. Full navigation safely
            # creates its dedicated tab; no user message is involved. The
            # adapter immediately polls the exact conversation identity, so a
            # second composer-readiness loop here only burns the same budget.
            result = await self._command("navigate", {"url": url}, timeout=10)
            self.target_url = str((result or {}).get("url") or url)
            self.selection_used_full_navigation = True
            return True
        handled = bool((result or {}).get("handled"))
        if handled:
            self.target_url = url
            return True
        # A new Cortex-owned writer tab may not have the target conversation
        # in its currently rendered sidebar. Direct navigation is still safe:
        # no user message has been prepared or activated at this point.
        result = await self._command("navigate", {"url": url}, timeout=10)
        self.target_url = str((result or {}).get("url") or url)
        self.selection_used_full_navigation = True
        return True

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
        await self.upload_files_named(selector, paths, None)

    async def upload_files_named(
        self,
        selector: str,
        paths: list[str],
        name: str | None,
    ) -> None:
        del selector
        if len(paths) != 1:
            raise DriverError("the Chrome extension accepts one attachment at a time")
        path = self._managed_file(paths[0])
        display_name = str(name or path.name).strip()
        if not display_name or Path(display_name).name != display_name:
            raise DriverError("attachment display name must be a plain filename")
        size = path.stat().st_size
        if size > EXTENSION_FILE_LIMIT_BYTES:
            raise DriverError("attachment exceeds the 25 MiB Chrome bridge limit")
        transfer_id = uuid.uuid4().hex
        mime = mimetypes.guess_type(display_name)[0] or "application/octet-stream"
        await self._command(
            "attachment_begin",
            {
                "transfer_id": transfer_id,
                "name": display_name,
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
        self._pending_attachment_name = display_name

    async def await_attachment(self) -> dict[str, Any]:
        result = await self._command(
            "await_attachment",
            {"name": self._pending_attachment_name} if self._pending_attachment_name else {},
            timeout=70,
        )
        if isinstance(result, dict) and result.get("ok"):
            self._pending_attachment_name = None
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
        if self._closed:
            return
        try:
            # Release only Cortex's logical binding. The Chrome tab remains
            # open and can be reused by the next writer session; close_tab is
            # still reserved for an explicit user action.
            await self._command("release_session", timeout=5)
        finally:
            self._closed = True
            self.target_url = None

    async def open_login(self) -> dict[str, Any]:
        opened = await self._command("open_chatgpt", timeout=10)
        self.target_url = str((opened or {}).get("url") or "https://chatgpt.com/")
        deadline = time.monotonic() + 10
        last_error: DriverError | None = None
        last_probe: dict[str, Any] | None = None

        def connection_payload(probe: dict[str, Any]) -> dict[str, Any]:
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

        while time.monotonic() < deadline:
            try:
                probe = await self.probe()
                last_probe = probe
                blocker = str(probe.get("blocker") or "").lower()
                failures = {
                    str(value).lower() for value in probe.get("failures") or []
                }
                if (
                    probe.get("ok") is True
                    and probe.get("composer_present") is True
                ) or blocker in {"login", "captcha", "rate_limit"} or failures.intersection(
                    {"login", "captcha", "rate_limit"}
                ):
                    return connection_payload(probe)
            except DriverError as exc:
                last_error = exc
            await asyncio.sleep(0.25)
        if last_probe is not None:
            return connection_payload(last_probe)
        raise last_error or DriverError("ChatGPT did not become ready within 10 seconds")
