"""Persistent Playwright browser driver with strict thread affinity."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import queue
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright


_SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass
class _WorkerCall:
    callback: Callable[[BrowserContext, Page | None], Any] | None
    future: concurrent.futures.Future[Any]


class PlaywrightBrowserDriver:
    """One persistent Chromium context owned by one dedicated worker thread."""

    driver_name = "playwright"

    def __init__(
        self,
        session: str,
        profile_root: Path,
        *,
        headless: bool | None = None,
    ):
        if not _SESSION_RE.fullmatch(session):
            raise ValueError("session must be a safe browser-profile name")
        self.session = session
        self.profile_root = Path(profile_root).expanduser().resolve()
        self.profile_path = self.profile_root / session
        self.headless = (
            os.environ.get("CORTEX_PLAYWRIGHT_HEADLESS") == "1"
            if headless is None
            else bool(headless)
        )
        self.target_url: str | None = None
        self._calls: queue.Queue[_WorkerCall] = queue.Queue()
        self._startup: concurrent.futures.Future[None] = concurrent.futures.Future()
        self._close_future: concurrent.futures.Future[None] | None = None
        self._state_lock = threading.Lock()
        self._closed = False
        self._thread: threading.Thread | None = None

    @property
    def closed(self) -> bool:
        with self._state_lock:
            return self._closed

    @property
    def started(self) -> bool:
        with self._state_lock:
            return self._thread is not None

    def _ensure_started(self) -> None:
        with self._state_lock:
            if self._closed:
                raise RuntimeError("browser driver is closed")
            if self._thread is not None:
                return
            self._thread = threading.Thread(
                target=self._worker,
                name=f"cortex-playwright-{self.session}",
                daemon=True,
            )
            self._thread.start()

    def _worker(self) -> None:
        playwright: Playwright | None = None
        context: BrowserContext | None = None
        try:
            self.profile_path.mkdir(parents=True, exist_ok=True)
            playwright = sync_playwright().start()
            context = playwright.chromium.launch_persistent_context(
                str(self.profile_path),
                headless=self.headless,
            )
            self._startup.set_result(None)
            while True:
                call = self._calls.get()
                if call.callback is None:
                    try:
                        context.close()
                        context = None
                        playwright.stop()
                        playwright = None
                    except BaseException as exc:
                        call.future.set_exception(exc)
                    else:
                        call.future.set_result(None)
                    return
                try:
                    pages = context.pages
                    page = pages[-1] if pages else None
                    call.future.set_result(call.callback(context, page))
                except BaseException as exc:
                    call.future.set_exception(exc)
        except BaseException as exc:
            if not self._startup.done():
                self._startup.set_exception(exc)
            while True:
                try:
                    pending = self._calls.get_nowait()
                except queue.Empty:
                    break
                if not pending.future.done():
                    pending.future.set_exception(exc)
        finally:
            if context is not None:
                try:
                    context.close()
                except BaseException:
                    pass
            if playwright is not None:
                try:
                    playwright.stop()
                except BaseException:
                    pass

    async def _call(self, callback: Callable[[BrowserContext, Page | None], Any]) -> Any:
        if self.closed:
            raise RuntimeError("browser driver is closed")
        self._ensure_started()
        await asyncio.wrap_future(self._startup)
        future: concurrent.futures.Future[Any] = concurrent.futures.Future()
        self._calls.put(_WorkerCall(callback, future))
        return await asyncio.wrap_future(future)

    @staticmethod
    def _page(context: BrowserContext, page: Page | None) -> Page:
        if page is None or page.is_closed():
            return context.new_page()
        return page

    async def navigate(self, url: str) -> None:
        def navigate(context: BrowserContext, page: Page | None) -> None:
            self._page(context, page).goto(url, wait_until="domcontentloaded")

        await self._call(navigate)
        self.target_url = url

    async def evaluate(self, code: str, timeout: float = 30) -> Any:
        del timeout  # Playwright awaits returned promises; action timeouts remain context defaults.
        return await self._call(
            lambda context, page: self._page(context, page).evaluate(code)
        )

    async def list_tabs(self) -> list[dict[str, Any]]:
        def tabs(context: BrowserContext, _page: Page | None) -> list[dict[str, Any]]:
            result = []
            for index, tab in enumerate(context.pages):
                if tab.is_closed():
                    continue
                result.append({
                    "id": str(index),
                    "url": tab.url,
                    "title": tab.title(),
                    "active": index == len(context.pages) - 1,
                })
            return result

        return await self._call(tabs)

    async def upload_files(self, selector: str, paths: list[str]) -> None:
        await self._call(
            lambda context, page: self._page(context, page)
            .locator(selector)
            .set_input_files(paths)
        )

    async def take_screenshot(self, path: str) -> dict[str, Any]:
        destination = Path(path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        await self._call(
            lambda context, page: self._page(context, page).screenshot(path=str(destination))
        )
        return {"path": str(destination), "driver": self.driver_name}

    async def health(self) -> dict[str, Any]:
        if not self.started:
            return {
                "connected": False,
                "tabs": 0,
                "driver": self.driver_name,
                "session": self.session,
                "error": "browser profile has not been opened",
            }
        try:
            tabs = await self.list_tabs()
            return {
                "connected": True,
                "tabs": len(tabs),
                "driver": self.driver_name,
                "session": self.session,
            }
        except Exception as exc:
            return {
                "connected": False,
                "tabs": 0,
                "driver": self.driver_name,
                "session": self.session,
                "error": str(exc),
            }

    async def open_login(self) -> dict[str, Any]:
        await self.navigate("https://chatgpt.com/")
        return await self.health()

    @staticmethod
    def _decode_json(raw: Any, label: str) -> dict[str, Any]:
        try:
            return json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            from transport.chatgpt_web.adapter import DriverError

            raise DriverError(f"cannot parse {label}: {exc}") from exc

    async def spa_navigate(self, url: str) -> bool:
        from transport.chatgpt_web.adapter import _SPA_NAV_JS

        result = self._decode_json(
            await self.evaluate(f"{_SPA_NAV_JS}({json.dumps(url)})"),
            "SPA navigation result",
        )
        if result.get("ok"):
            self.target_url = url
            return True
        return False

    async def get_state(self) -> dict[str, Any]:
        from transport.chatgpt_web.adapter import _STATE_JS

        return self._decode_json(await self.evaluate(_STATE_JS), "page state")

    async def get_light_state(self) -> dict[str, Any]:
        from transport.chatgpt_web.adapter import _LIGHT_STATE_JS

        return self._decode_json(await self.evaluate(_LIGHT_STATE_JS), "light page state")

    async def send_message(self, text: str) -> None:
        from transport.chatgpt_web.adapter import DriverError, _SEND_JS

        result = self._decode_json(
            await self.evaluate(f"{_SEND_JS}({json.dumps(text)})", timeout=60),
            "send result",
        )
        if not result.get("ok"):
            raise DriverError(f"send failed: {result.get('error', 'unknown')}")

    async def press_stop(self) -> None:
        await self.evaluate(
            """(() => {
              for (const selector of ['[data-testid="stop-button"]',
                'button[aria-label*="Stop"]', 'button[aria-label*="Arr"]']) {
                const button = document.querySelector(selector);
                if (button) { button.click(); return true; }
              }
              return false;
            })()"""
        )

    def capabilities(self) -> dict[str, Any]:
        from transport.chatgpt_web.adapter import MAX_FILE_BYTES, MAX_IMAGE_BYTES

        return {
            "send_text": True,
            "upload_file": True,
            "upload_image": True,
            "take_screenshot": True,
            "limits": {"file_bytes": MAX_FILE_BYTES, "image_bytes": MAX_IMAGE_BYTES},
        }

    async def await_attachment(self) -> dict[str, Any]:
        from transport.chatgpt_web.adapter import _ATTACHMENT_WAIT_JS

        return self._decode_json(
            await self.evaluate(_ATTACHMENT_WAIT_JS, timeout=70),
            "attachment state",
        )

    async def send_bare(self) -> dict[str, Any]:
        from transport.chatgpt_web.adapter import _SEND_BARE_JS

        return self._decode_json(
            await self.evaluate(_SEND_BARE_JS),
            "bare-send result",
        )

    async def probe(self) -> dict[str, Any]:
        from transport.chatgpt_web.adapter import _PROBE_JS, _summarize_probe

        return _summarize_probe(
            self._decode_json(await self.evaluate(_PROBE_JS), "probe result")
        )

    async def list_conversations(self) -> list[dict[str, Any]]:
        from transport.chatgpt_web.adapter import _CONVERSATIONS_JS

        tabs = await self.list_tabs()
        if not tabs or tabs[-1]["url"] == "about:blank":
            await self.navigate("https://chatgpt.com/")
        raw = await self.evaluate(_CONVERSATIONS_JS)
        try:
            return json.loads(raw) if isinstance(raw, str) else list(raw or [])
        except (json.JSONDecodeError, TypeError) as exc:
            from transport.chatgpt_web.adapter import DriverError

            raise DriverError(f"cannot parse conversation list: {exc}") from exc

    async def list_models(self) -> dict[str, Any]:
        from transport.chatgpt_web.adapter import _MODELS_JS

        return self._decode_json(await self.evaluate(_MODELS_JS), "model list")

    async def select_model(self, label: str) -> str:
        from transport.chatgpt_web.adapter import DriverError, _SELECT_MODEL_JS

        result = self._decode_json(
            await self.evaluate(
                f"{_SELECT_MODEL_JS}({json.dumps(label)})",
                timeout=40,
            ),
            "model selection",
        )
        if not result.get("ok"):
            raise DriverError(f"model selection failed: {result.get('error', 'unknown')}")
        return str(result.get("selected") or label)

    async def close_tab(self) -> None:
        def close_page(_context: BrowserContext, page: Page | None) -> None:
            if page is not None and not page.is_closed():
                page.close()

        await self._call(close_page)
        self.target_url = None

    async def close(self) -> None:
        with self._state_lock:
            if self._close_future is None:
                self._closed = True
                self._close_future = concurrent.futures.Future()
                owner = True
            else:
                owner = False
            close_future = self._close_future
            thread = self._thread
        if owner:
            if thread is None:
                if not close_future.done():
                    close_future.set_result(None)
            else:
                try:
                    await asyncio.wrap_future(self._startup)
                except BaseException:
                    if not close_future.done():
                        close_future.set_result(None)
                else:
                    self._calls.put(_WorkerCall(None, close_future))
        await asyncio.wrap_future(close_future)
        if thread is not None:
            await asyncio.to_thread(thread.join, 5)
