"""Persistent Playwright browser driver with strict thread affinity."""

from __future__ import annotations

import asyncio
import collections
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
_MAX_LOGICAL_PAGES = 8
_PROFILE_NAME = "cortex-bridge-ui"
_IDLE_SHUTDOWN_SECONDS = 0.5


def _driver_error(message: str, exc: BaseException | None = None) -> Exception:
    from transport.chatgpt_web.adapter import DriverError

    error = DriverError(message)
    if exc is not None:
        error.__cause__ = exc
    return error


def _settle(
    future: concurrent.futures.Future[Any],
    *,
    result: Any = None,
    error: BaseException | None = None,
) -> None:
    """Settle a cross-thread future without letting cancellation kill the worker."""
    if future.done() or future.cancelled():
        return
    try:
        if error is None:
            future.set_result(result)
        else:
            future.set_exception(error)
    except concurrent.futures.InvalidStateError:
        pass


@dataclass
class _WorkerCall:
    action: str
    session: str | None
    callback: Callable[[BrowserContext, Page], Any] | None
    future: concurrent.futures.Future[Any]


class _PlaywrightRuntime:
    """One authenticated persistent context shared by bounded logical pages."""

    def __init__(self, profile_root: Path, headless: bool):
        self.profile_root = profile_root
        self.profile_path = profile_root / _PROFILE_NAME
        self.headless = headless
        self._calls: queue.Queue[_WorkerCall] = queue.Queue()
        self._startup: concurrent.futures.Future[None] = concurrent.futures.Future()
        self._state_lock = threading.Lock()
        self._clients: collections.Counter[str] = collections.Counter()
        self._thread: threading.Thread | None = None
        self._accepting = True
        self._dead = False
        self._logical_pages = 0
        self._idle_timer: threading.Timer | None = None

    @property
    def live(self) -> bool:
        with self._state_lock:
            return self._accepting and not self._dead

    @property
    def started(self) -> bool:
        with self._state_lock:
            return self._thread is not None

    @property
    def logical_pages(self) -> int:
        with self._state_lock:
            return self._logical_pages

    def register(self, session: str) -> None:
        with self._state_lock:
            if not self._accepting or self._dead:
                raise RuntimeError("playwright runtime is unavailable")
            if self._idle_timer is not None:
                self._idle_timer.cancel()
                self._idle_timer = None
            self._clients[session] += 1

    def _start_locked(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._worker,
            name="cortex-playwright-runtime",
            daemon=True,
        )
        self._thread.start()

    def submit(
        self,
        session: str,
        callback: Callable[[BrowserContext, Page], Any],
    ) -> tuple[concurrent.futures.Future[None], concurrent.futures.Future[Any]]:
        future: concurrent.futures.Future[Any] = concurrent.futures.Future()
        with self._state_lock:
            if not self._accepting or self._dead or not self._clients.get(session):
                raise RuntimeError("browser driver is closed")
            self._start_locked()
            self._calls.put(_WorkerCall("call", session, callback, future))
        return self._startup, future

    def release(
        self, session: str
    ) -> tuple[concurrent.futures.Future[None], threading.Thread | None]:
        future: concurrent.futures.Future[None] = concurrent.futures.Future()
        with self._state_lock:
            count = self._clients.get(session, 0)
            if count > 1:
                self._clients[session] -= 1
                _settle(future)
                return future, self._thread
            if count == 1:
                del self._clients[session]
            thread = self._thread
            if thread is None:
                if not self._clients:
                    self._accepting = False
                    self._dead = True
                _settle(future)
                return future, thread
            if self._clients:
                self._calls.put(_WorkerCall("close_page", session, None, future))
            else:
                # Release the page immediately, but keep the authenticated
                # context warm for a short terminal-session handoff window.
                self._calls.put(_WorkerCall("close_page", session, None, future))
                self._idle_timer = threading.Timer(
                    _IDLE_SHUTDOWN_SECONDS, self._shutdown_if_idle
                )
                self._idle_timer.daemon = True
                self._idle_timer.start()
        return future, thread

    def _shutdown_if_idle(self) -> None:
        future: concurrent.futures.Future[None] = concurrent.futures.Future()
        with self._state_lock:
            self._idle_timer = None
            if self._clients or self._dead or not self._accepting:
                return
            # Admission and the terminal sentinel share this lock. No call can
            # ever be queued behind shutdown.
            self._accepting = False
            self._calls.put(_WorkerCall("shutdown", None, None, future))

    def _set_logical_pages(self, count: int) -> None:
        with self._state_lock:
            self._logical_pages = count

    def _mark_dead(self) -> None:
        with self._state_lock:
            if self._idle_timer is not None:
                self._idle_timer.cancel()
                self._idle_timer = None
            self._accepting = False
            self._dead = True
            self._logical_pages = 0

    def _worker(self) -> None:
        playwright: Playwright | None = None
        context: BrowserContext | None = None
        pages: collections.OrderedDict[str, Page] = collections.OrderedDict()
        terminal_error: BaseException | None = None

        def close_context() -> BaseException | None:
            nonlocal context, playwright
            error: BaseException | None = None
            if context is not None:
                try:
                    context.close()
                except BaseException as exc:
                    error = exc
                context = None
            if playwright is not None:
                try:
                    playwright.stop()
                except BaseException as exc:
                    error = error or exc
                playwright = None
            pages.clear()
            self._set_logical_pages(0)
            return error

        def page_for(session: str) -> Page:
            page = pages.get(session)
            if page is not None and not page.is_closed():
                pages.move_to_end(session)
                return page
            pages.pop(session, None)
            assert context is not None
            if not pages:
                candidates = [candidate for candidate in context.pages if not candidate.is_closed()]
                page = candidates[-1] if candidates else context.new_page()
            else:
                while len(pages) >= _MAX_LOGICAL_PAGES:
                    _old_session, old_page = pages.popitem(last=False)
                    try:
                        old_page.close()
                    except BaseException:
                        pass
                page = context.new_page()
            pages[session] = page
            self._set_logical_pages(len(pages))
            return page

        try:
            self.profile_path.mkdir(parents=True, exist_ok=True)
            playwright = sync_playwright().start()
            context = playwright.chromium.launch_persistent_context(
                str(self.profile_path),
                headless=self.headless,
            )
            _settle(self._startup)
            while True:
                call = self._calls.get()
                if call.action == "shutdown":
                    error = close_context()
                    if error is None:
                        _settle(call.future)
                    else:
                        _settle(call.future, error=error)
                    return
                if call.action == "close_page":
                    page = pages.pop(str(call.session), None)
                    try:
                        if page is not None and not page.is_closed():
                            page.close()
                    except BaseException as exc:
                        _settle(call.future, error=exc)
                    else:
                        self._set_logical_pages(len(pages))
                        _settle(call.future)
                    continue
                try:
                    assert call.session is not None and call.callback is not None
                    result = call.callback(context, page_for(call.session))
                except BaseException as exc:
                    _settle(call.future, error=exc)
                else:
                    _settle(call.future, result=result)
        except BaseException as exc:
            terminal_error = exc
            _settle(self._startup, error=exc)
        finally:
            terminal_error = terminal_error or close_context()
            self._mark_dead()
            failure = terminal_error or RuntimeError("playwright runtime stopped")
            while True:
                try:
                    pending = self._calls.get_nowait()
                except queue.Empty:
                    break
                _settle(pending.future, error=failure)
            _discard_runtime(self)


_RUNTIMES: dict[tuple[str, bool], _PlaywrightRuntime] = {}
_RUNTIMES_LOCK = threading.Lock()


def _discard_runtime(runtime: _PlaywrightRuntime) -> None:
    key = (str(runtime.profile_root), runtime.headless)
    with _RUNTIMES_LOCK:
        if _RUNTIMES.get(key) is runtime:
            _RUNTIMES.pop(key, None)


def _shared_runtime(profile_root: Path, headless: bool) -> _PlaywrightRuntime:
    key = (str(profile_root), headless)
    with _RUNTIMES_LOCK:
        runtime = _RUNTIMES.get(key)
        if runtime is None or not runtime.live:
            runtime = _PlaywrightRuntime(profile_root, headless)
            _RUNTIMES[key] = runtime
        return runtime


class PlaywrightBrowserDriver:
    """Logical browser session backed by one shared authenticated context."""

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
        self.headless = (
            os.environ.get("CORTEX_PLAYWRIGHT_HEADLESS") == "1"
            if headless is None
            else bool(headless)
        )
        self._runtime = _shared_runtime(self.profile_root, self.headless)
        self._runtime.register(session)
        self.profile_path = self._runtime.profile_path
        self.target_url: str | None = None
        self._state_lock = threading.Lock()
        self._closed = False
        self._used = False
        self._close_future: concurrent.futures.Future[None] | None = None
        self._close_thread: threading.Thread | None = None

    @property
    def closed(self) -> bool:
        with self._state_lock:
            return self._closed

    @property
    def live(self) -> bool:
        return not self.closed and self._runtime.live

    @property
    def started(self) -> bool:
        with self._state_lock:
            return self._used

    async def _await_future(
        self,
        future: concurrent.futures.Future[Any],
        operation: str,
    ) -> Any:
        try:
            return await asyncio.shield(asyncio.wrap_future(future))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            from transport.chatgpt_web.adapter import DriverError

            if isinstance(exc, DriverError):
                raise
            raise _driver_error(f"playwright {operation} failed: {exc}", exc)

    async def _call(
        self,
        callback: Callable[[BrowserContext, Page], Any],
        *,
        operation: str = "operation",
    ) -> Any:
        try:
            startup, future = self._runtime.submit(self.session, callback)
        except Exception as exc:
            raise _driver_error(f"playwright {operation} failed: {exc}", exc)
        with self._state_lock:
            self._used = True
        await self._await_future(startup, "startup")
        return await self._await_future(future, operation)

    async def navigate(self, url: str) -> None:
        await self._call(
            lambda _context, page: page.goto(url, wait_until="domcontentloaded"),
            operation="navigate",
        )
        self.target_url = url

    async def evaluate(self, code: str, timeout: float = 30) -> Any:
        if timeout <= 0:
            raise _driver_error("playwright evaluate timed out: timeout must be positive")
        timeout_ms = max(1, int(timeout * 1000))
        wrapper = """async ([source, timeoutMs]) => {
          let timer;
          try {
            return await Promise.race([
              (0, eval)(source),
              new Promise((_, reject) => {
                timer = setTimeout(
                  () => reject(new Error(`CORTEX_EVALUATE_TIMEOUT:${timeoutMs}`)),
                  timeoutMs
                );
              }),
            ]);
          } finally {
            clearTimeout(timer);
          }
        }"""
        try:
            return await self._call(
                lambda _context, page: page.evaluate(wrapper, [code, timeout_ms]),
                operation="evaluate",
            )
        except Exception as exc:
            if "CORTEX_EVALUATE_TIMEOUT" in str(exc):
                raise _driver_error(
                    f"playwright evaluate timed out after {timeout:.3g}s", exc
                )
            raise

    async def list_tabs(self) -> list[dict[str, Any]]:
        def tabs(_context: BrowserContext, page: Page) -> list[dict[str, Any]]:
            if page.is_closed():
                return []
            return [{
                "id": self.session,
                "url": page.url,
                "title": page.title(),
                "active": True,
            }]

        return await self._call(tabs, operation="list tabs")

    async def upload_files(self, selector: str, paths: list[str]) -> None:
        await self._call(
            lambda _context, page: page.locator(selector).set_input_files(paths),
            operation="upload files",
        )

    async def take_screenshot(self, path: str) -> dict[str, Any]:
        destination = Path(path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        await self._call(
            lambda _context, page: page.screenshot(path=str(destination)),
            operation="screenshot",
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
                "logical_sessions": self._runtime.logical_pages,
                "profile_path": str(self.profile_path),
            }
        except Exception as exc:
            return {
                "connected": False,
                "tabs": 0,
                "driver": self.driver_name,
                "session": self.session,
                "logical_sessions": self._runtime.logical_pages,
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
            raise _driver_error(f"cannot parse {label}: {exc}", exc)

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
            raise _driver_error(f"cannot parse conversation list: {exc}", exc)

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
        await self._call(
            lambda _context, page: page.close() if not page.is_closed() else None,
            operation="close tab",
        )
        self.target_url = None

    async def close(self) -> None:
        with self._state_lock:
            if self._close_future is None:
                self._closed = True
                self._close_future, self._close_thread = self._runtime.release(self.session)
            close_future = self._close_future
            thread = self._close_thread
        try:
            await self._await_future(close_future, "close")
        except Exception:
            # Startup already reports the actionable failure. Closing a
            # poisoned runtime remains best-effort and idempotent.
            pass
        if thread is not None and not thread.is_alive():
            await asyncio.to_thread(thread.join, 0)
