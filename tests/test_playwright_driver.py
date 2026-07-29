"""Playwright browser-driver contract tests.

Every browser interaction stays on a loopback fixture page.
"""

from __future__ import annotations

import asyncio
import http.server
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import transport.browser_playwright.driver as playwright_driver_module
from transport.browser import BrowserDriver, create_browser_driver
from transport.browser_playwright import PlaywrightBrowserDriver
from transport.chatgpt_web.adapter import (
    ChatGPTWebTransport,
    ConversationLock,
    DELIVERY_UNCERTAIN,
    DriverError,
    TransportError,
    WebBridgeDriver,
)


_FIXTURE_HTML = b"""<!doctype html>
<html>
  <head><title>Cortex Playwright Fixture</title></head>
  <body>
    <main id="messages">
      <article data-message-author-role="assistant" data-message-id="initial">ready</article>
    </main>
    <form>
      <div id="prompt-textarea" role="textbox" contenteditable="true"></div>
      <input id="upload" type="file">
      <button data-testid="send-button" type="button">Send</button>
    </form>
    <output id="uploaded"></output>
    <script>
      document.querySelector("#upload").addEventListener("change", (event) => {
        document.querySelector("#uploaded").textContent =
          event.target.files[0]?.name || "";
      });
      document.querySelector("[data-testid=send-button]").addEventListener("click", () => {
        const composer = document.querySelector("#prompt-textarea");
        const text = composer.innerText;
        const message = document.createElement("article");
        message.dataset.messageAuthorRole = "user";
        message.dataset.messageId = `user-${Date.now()}`;
        message.textContent = text;
        document.querySelector("#messages").appendChild(message);
        composer.innerText = "";
        if (window.breakAfterClick) {
          Object.defineProperty(composer, "innerText", {
            configurable: true,
            get() { throw new Error("post-click state unreadable"); },
          });
        }
      });
    </script>
  </body>
</html>
"""


class _FixtureHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(_FIXTURE_HTML)))
        self.end_headers()
        self.wfile.write(_FIXTURE_HTML)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class _BrokenPlaywright:
    def start(self) -> None:
        raise RuntimeError("browser executable missing")


class PlaywrightDriverTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/fixture"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    async def asyncSetUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.profile_root = Path(self.tempdir.name) / "profiles"
        self.drivers: list[PlaywrightBrowserDriver] = []

    async def asyncTearDown(self) -> None:
        for driver in reversed(self.drivers):
            await asyncio.wait_for(driver.close(), timeout=0.5)
        for runtime in {driver._runtime for driver in self.drivers}:
            thread = runtime._thread
            if thread is not None:
                # join() returns as soon as the condition is met. The bound
                # covers the 0.5 s warm-handoff window plus Chromium teardown.
                await asyncio.to_thread(thread.join, 5)
                self.assertFalse(thread.is_alive())
        self.tempdir.cleanup()

    def driver(self, session: str) -> PlaywrightBrowserDriver:
        driver = PlaywrightBrowserDriver(
            session=session,
            profile_root=self.profile_root,
            headless=True,
        )
        self.drivers.append(driver)
        return driver

    async def wait_for_worker_exit(self, driver: PlaywrightBrowserDriver) -> None:
        thread = driver._runtime._thread
        self.assertIsNotNone(thread)
        await asyncio.to_thread(thread.join, 0.5)
        self.assertFalse(thread.is_alive())

    async def test_navigation_evaluation_upload_screenshot_tabs_and_health(self) -> None:
        driver = self.driver("contract-a")
        self.assertIsInstance(driver, BrowserDriver)

        await driver.navigate(self.url)
        self.assertEqual(await driver.evaluate("document.title"), "Cortex Playwright Fixture")

        upload = Path(self.tempdir.name) / "proof.txt"
        upload.write_text("fixture", encoding="utf-8")
        await driver.upload_files("#upload", [str(upload)])
        self.assertEqual(await driver.evaluate("document.querySelector('#uploaded').textContent"), "proof.txt")

        screenshot = Path(self.tempdir.name) / "proof.png"
        result = await driver.take_screenshot(str(screenshot))
        self.assertEqual(Path(result["path"]).resolve(), screenshot.resolve())
        self.assertGreater(screenshot.stat().st_size, 0)

        tabs = await driver.list_tabs()
        self.assertEqual(len(tabs), 1)
        self.assertEqual(tabs[0]["url"], self.url)
        health = await driver.health()
        self.assertEqual(health["driver"], "playwright")
        self.assertEqual(health["session"], "contract-a")
        self.assertTrue(health["connected"])
        self.assertEqual(health["tabs"], 1)
        self.assertEqual(driver.profile_path.name, "cortex-bridge-ui")

    async def test_health_does_not_launch_profile_before_explicit_browser_use(self) -> None:
        driver = self.driver("diagnostic-only")
        health = await driver.health()
        self.assertFalse(health["connected"])
        self.assertFalse(driver.started)
        self.assertEqual(health["driver"], "playwright")

    async def test_authenticated_profile_is_shared_while_logical_pages_are_isolated(self) -> None:
        login = self.driver("cortex-bridge-ui")
        writer = self.driver("cortex-conv-a")
        reader = self.driver("cortex-view-read-only")
        await login.navigate(f"{self.url}?page=login")
        await login.evaluate("document.cookie = 'cortex_auth=ready; path=/'")
        await writer.navigate(f"{self.url}?page=writer")
        await reader.navigate(f"{self.url}?page=reader")

        self.assertIn("cortex_auth=ready", await writer.evaluate("document.cookie"))
        self.assertIn("cortex_auth=ready", await reader.evaluate("document.cookie"))
        await writer.evaluate("window.logicalMarker = 'writer'")
        self.assertIsNone(await reader.evaluate("window.logicalMarker || null"))
        self.assertEqual(login.profile_path, writer.profile_path)
        self.assertEqual(writer.profile_path, reader.profile_path)
        self.assertEqual(len(list(self.profile_root.iterdir())), 1)

    async def test_terminal_sessions_do_not_create_unbounded_profiles_or_pages(self) -> None:
        for index in range(20):
            driver = self.driver(f"cortex-conv-{index}")
            await driver.navigate(f"{self.url}?session={index}")
            await driver.close()
        survivor = self.driver("cortex-view-read-only")
        await survivor.navigate(self.url)
        health = await survivor.health()
        self.assertLessEqual(health["logical_sessions"], 8)
        self.assertEqual(len(list(self.profile_root.iterdir())), 1)

    async def test_requests_are_serialized_on_worker_and_close_is_event_loop_safe(self) -> None:
        driver = self.driver("serialized")
        await driver.navigate(self.url)
        values = await asyncio.gather(*[
            driver.evaluate("window.counter = (window.counter || 0) + 1")
            for _ in range(12)
        ])
        self.assertEqual(sorted(values), list(range(1, 13)))

        slow = asyncio.create_task(driver.evaluate(
            "new Promise(resolve => setTimeout(() => resolve('done'), 250))"
        ))
        await asyncio.sleep(0.01)
        closing = asyncio.create_task(driver.close())
        await asyncio.sleep(0.05)
        self.assertFalse(closing.done(), "close blocked instead of awaiting the worker asynchronously")
        self.assertEqual(await slow, "done")
        await closing
        await driver.close()  # idempotent

    async def test_cancelled_request_does_not_kill_worker(self) -> None:
        driver = self.driver("cancel-safe")
        await driver.navigate(self.url)
        pending = asyncio.create_task(driver.evaluate(
            "new Promise(resolve => setTimeout(() => resolve('late'), 150))"
        ))
        await asyncio.sleep(0.02)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        await asyncio.sleep(0.2)
        self.assertEqual(await driver.evaluate("6 * 7"), 42)

    async def test_close_admission_race_never_leaves_waiter_behind_sentinel(self) -> None:
        driver = self.driver("close-race")
        await driver.navigate(self.url)
        calls = [
            asyncio.create_task(driver.evaluate(f"{index}"))
            for index in range(100)
        ]
        closing = asyncio.create_task(driver.close())
        results = await asyncio.wait_for(
            asyncio.gather(*calls, closing, return_exceptions=True),
            timeout=3,
        )
        self.assertEqual(len(results), 101)
        self.assertTrue(all(task.done() for task in calls))

    async def test_evaluate_timeout_is_bounded_and_page_recovers(self) -> None:
        driver = self.driver("timeout-safe")
        await driver.navigate(self.url)
        started = time.monotonic()
        with self.assertRaisesRegex(DriverError, "timed out"):
            await driver.evaluate("new Promise(() => {})", timeout=0.15)
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(await driver.evaluate("21 * 2"), 42)

    async def test_playwright_errors_are_normalized_for_adapter_fallbacks(self) -> None:
        driver = self.driver("normalized-errors")
        await driver.navigate(self.url)
        missing = Path(self.tempdir.name) / "missing.txt"
        with self.assertRaises(DriverError):
            await driver.upload_files("#upload", [str(missing)])

    async def test_post_click_playwright_failure_becomes_delivery_uncertain(self) -> None:
        driver = self.driver("post-click")
        transport = ChatGPTWebTransport(
            driver,
            stability_interval=0.01,
            poll_interval=0.01,
            max_wait=1,
        )
        await transport.recover_selection_with_reload(
            f"http://127.0.0.1:{self.server.server_port}/c/post-click"
        )
        await driver.evaluate("window.breakAfterClick = true")
        with self.assertRaises(TransportError) as raised:
            await transport.send_message("message after click must not retry")
        self.assertEqual(raised.exception.code, DELIVERY_UNCERTAIN)
        self.assertTrue(transport.delivery_uncertain)

    async def test_chatgpt_transport_flow_uses_playwright_contract(self) -> None:
        driver = self.driver("playwright-flow")
        transport = ChatGPTWebTransport(
            driver,
            stability_interval=0.01,
            poll_interval=0.01,
            max_wait=2,
        )
        await transport.recover_selection_with_reload(
            f"http://127.0.0.1:{self.server.server_port}/c/playwright-flow"
        )
        sent = await transport.send_message("meaningful playwright flow")
        self.assertEqual(sent["role"], "user")
        self.assertIn("meaningful playwright flow", sent["text"])

    async def test_startup_failure_is_evicted_and_factory_recovers(self) -> None:
        settings = {
            "browser_transport": "playwright",
            "browser_profile_root": str(self.profile_root),
        }
        with mock.patch.object(
            playwright_driver_module,
            "sync_playwright",
            return_value=_BrokenPlaywright(),
        ):
            broken = create_browser_driver(
                session="startup-recovery",
                settings=settings,
                headless=True,
            )
            with self.assertRaises(DriverError):
                await broken.navigate(self.url)
        recovered = create_browser_driver(
            session="startup-recovery",
            settings=settings,
            headless=True,
        )
        self.assertIsNot(recovered, broken)
        self.drivers.append(recovered)
        await recovered.navigate(self.url)
        self.assertEqual(await recovered.evaluate("document.title"), "Cortex Playwright Fixture")

    async def test_close_completes_after_startup_worker_has_failed(self) -> None:
        driver = PlaywrightBrowserDriver(
            session="startup-close",
            profile_root=self.profile_root,
            headless=True,
        )
        with mock.patch.object(
            playwright_driver_module,
            "sync_playwright",
            return_value=_BrokenPlaywright(),
        ):
            with self.assertRaisesRegex(DriverError, "browser executable missing"):
                await driver.navigate(self.url)
        await self.wait_for_worker_exit(driver)

        await asyncio.wait_for(driver.close(), timeout=0.5)
        self.assertTrue(driver.closed)

    async def test_registered_startup_failure_is_not_masked_by_teardown_hang(self) -> None:
        driver = self.driver("startup-teardown")
        with mock.patch.object(
            playwright_driver_module,
            "sync_playwright",
            return_value=_BrokenPlaywright(),
        ):
            with self.assertRaisesRegex(DriverError, "browser executable missing"):
                await driver.navigate(self.url)
        await self.wait_for_worker_exit(driver)

    async def test_thread_start_failure_does_not_leave_close_pending(self) -> None:
        driver = PlaywrightBrowserDriver(
            session="thread-start-close",
            profile_root=self.profile_root,
            headless=True,
        )
        with mock.patch.object(
            playwright_driver_module.threading.Thread,
            "start",
            side_effect=RuntimeError("worker thread refused to start"),
        ):
            with self.assertRaisesRegex(DriverError, "worker thread refused to start"):
                await driver.navigate(self.url)

        await asyncio.wait_for(driver.close(), timeout=0.5)
        self.assertFalse(driver.live)

    async def test_idle_timer_start_failure_falls_back_to_worker_shutdown(self) -> None:
        driver = PlaywrightBrowserDriver(
            session="timer-start-close",
            profile_root=self.profile_root,
            headless=True,
        )
        await driver.navigate(self.url)
        thread = driver._runtime._thread
        self.assertIsNotNone(thread)

        with mock.patch.object(
            playwright_driver_module.threading.Timer,
            "start",
            side_effect=RuntimeError("idle timer refused to start"),
        ):
            await asyncio.wait_for(driver.close(), timeout=0.5)

        await asyncio.to_thread(thread.join, 1)
        self.assertFalse(thread.is_alive())
        self.assertFalse(driver.live)

    async def test_registration_claim_is_atomic_with_idle_shutdown(self) -> None:
        seed = self.driver("handoff-seed")
        await seed.navigate(self.url)
        await seed.close()
        original_shared_runtime = playwright_driver_module._shared_runtime

        def run_idle_callback_after_selection(*args, **kwargs):
            runtime = original_shared_runtime(*args, **kwargs)
            runtime._shutdown_if_idle()
            return runtime

        with mock.patch.object(
            playwright_driver_module,
            "_shared_runtime",
            side_effect=run_idle_callback_after_selection,
        ):
            handoff = PlaywrightBrowserDriver(
                session="handoff-successor",
                profile_root=self.profile_root,
                headless=True,
            )
        self.drivers.append(handoff)

        await handoff.navigate(self.url)
        self.assertTrue(handoff.live)

    async def test_factory_selects_exact_backend_and_reuses_live_playwright_session(self) -> None:
        first = create_browser_driver(
            session="factory",
            settings={
                "browser_transport": "playwright",
                "browser_profile_root": str(self.profile_root),
            },
            headless=True,
        )
        second = create_browser_driver(
            session="factory",
            settings={
                "browser_transport": "playwright",
                "browser_profile_root": str(self.profile_root),
            },
            headless=True,
        )
        self.assertIs(first, second)
        self.drivers.append(first)
        await first.navigate(self.url)

        compatibility = create_browser_driver(
            session="compat",
            settings={"browser_transport": "webbridge"},
        )
        self.assertEqual(compatibility.driver_name, "webbridge")
        with self.assertRaisesRegex(ValueError, "browser_transport"):
            create_browser_driver(
                session="invalid",
                settings={"browser_transport": "selenium"},
            )


class _AttachmentFallbackDriver:
    """Real adapter double with no private ``_command`` escape hatch."""

    def __init__(self) -> None:
        self.evaluate_calls = 0
        self.url = "http://127.0.0.1/c/local-fixture"

    async def get_state(self) -> dict:
        return {
            "url": self.url,
            "conversation_id": "local-fixture",
            "title": "Fixture",
            "blocker": None,
            "messages": [],
        }

    async def upload_files(self, _selector: str, _paths: list[str]) -> None:
        raise DriverError("primary upload rejected")

    async def evaluate(self, _code: str, timeout: float = 30) -> dict:
        self.evaluate_calls += 1
        self.code = _code
        self.timeout = timeout
        return {"ok": True}

    async def await_attachment(self) -> dict:
        return {"ok": True, "label": "proof.txt"}

    async def send_bare(self) -> dict:
        return {"ok": True}


class AdapterPublicDriverContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_attachment_fallback_uses_public_evaluate_contract(self) -> None:
        driver = _AttachmentFallbackDriver()
        transport = ChatGPTWebTransport(driver)
        transport.lock = ConversationLock(
            driver.url,
            "local-fixture",
            "Fixture",
            0,
        )
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "proof.txt"
            path.write_text("fixture", encoding="utf-8")
            result = await transport.send_with_attachment(None, str(path), image=False)
        self.assertTrue(result["sent"])
        self.assertEqual(driver.evaluate_calls, 1)
        self.assertEqual(driver.timeout, 90)

    async def test_attachment_fallback_uses_validated_mime_and_name(self) -> None:
        driver = _AttachmentFallbackDriver()
        transport = ChatGPTWebTransport(driver)
        transport.lock = ConversationLock(driver.url, "local-fixture", "Fixture", 0)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "misleading.bin"
            path.write_bytes(b"fixture")
            await transport.send_with_attachment(
                None,
                str(path),
                image=True,
                mime="image/png",
                name="validated.png",
            )
        self.assertIn("image/png", driver.code)
        self.assertIn("validated.png", driver.code)


class _CountingWebBridgeDriver(WebBridgeDriver):
    def __init__(self) -> None:
        super().__init__()
        self.close_calls = 0

    async def close_tab(self) -> None:
        self.close_calls += 1


class WebBridgeLifecycleCompatibilityTest(unittest.IsolatedAsyncioTestCase):
    async def test_close_is_idempotent(self) -> None:
        driver = _CountingWebBridgeDriver()
        await driver.close()
        await driver.close()
        self.assertEqual(driver.close_calls, 1)

    async def test_concurrent_close_is_idempotent(self) -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        class ConcurrentDriver(_CountingWebBridgeDriver):
            async def close_tab(inner_self) -> None:
                inner_self.close_calls += 1
                entered.set()
                await release.wait()

        driver = ConcurrentDriver()
        first = asyncio.create_task(driver.close())
        await entered.wait()
        second = asyncio.create_task(driver.close())
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(first, second)
        self.assertEqual(driver.close_calls, 1)


class _WebBridgeContractDaemon:
    def __init__(self) -> None:
        self.url = ""
        self.messages = [{
            "id": "initial",
            "role": "assistant",
            "text": "ready",
            "code_blocks": [],
        }]
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                action = payload["action"]
                args = payload.get("args") or {}
                if action == "navigate":
                    owner.url = args["url"]
                    data: object = {}
                elif action == "list_tabs":
                    data = {"tabs": [{"url": owner.url}] if owner.url else []}
                elif action == "close_tab":
                    owner.url = ""
                    data = {}
                else:
                    code = str(args.get("code") or "")
                    if "not_in_sidebar" in code:
                        match = code.rsplit("(", 1)[-1].rsplit(")", 1)[0]
                        owner.url = json.loads(match)
                        data = {"value": json.dumps({"ok": True, "clicked": True})}
                    elif "composer not cleared after click" in code:
                        match = code.rsplit("(", 1)[-1].rsplit(")", 1)[0]
                        text = json.loads(match)
                        owner.messages.append({
                            "id": f"user-{len(owner.messages)}",
                            "role": "user",
                            "text": text,
                            "code_blocks": [],
                        })
                        data = {"value": json.dumps({"ok": True})}
                    elif "message_count:" in code:
                        data = {"value": json.dumps({
                            "url": owner.url,
                            "conversation_id": "webbridge-flow",
                            "title": "WebBridge fixture",
                            "message_count": len(owner.messages),
                            "first_id": owner.messages[0]["id"],
                            "last_id": owner.messages[-1]["id"],
                            "streaming": False,
                            "composer_present": True,
                        })}
                    else:
                        data = {"value": json.dumps({
                            "url": owner.url,
                            "conversation_id": "webbridge-flow",
                            "title": "WebBridge fixture",
                            "blocker": None,
                            "composer_present": True,
                            "send_button_present": True,
                            "stop_button_present": False,
                            "streaming": False,
                            "messages": owner.messages,
                        })}
                body = json.dumps({"ok": True, "data": data}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> "_WebBridgeContractDaemon":
        self.thread.start()
        return self

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class WebBridgeAdapterContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_chatgpt_transport_flow_uses_webbridge_contract(self) -> None:
        daemon = _WebBridgeContractDaemon().start()
        self.addAsyncCleanup(asyncio.to_thread, daemon.close)
        driver = WebBridgeDriver(daemon=daemon.endpoint, session="webbridge-flow")
        transport = ChatGPTWebTransport(
            driver,
            stability_interval=0.01,
            poll_interval=0.01,
            max_wait=2,
        )
        url = f"{daemon.endpoint}/c/webbridge-flow"
        await transport.select_conversation(url)
        sent = await transport.send_message("meaningful webbridge flow")
        self.assertEqual(sent["role"], "user")
        self.assertIn("meaningful webbridge flow", sent["text"])


if __name__ == "__main__":
    unittest.main()
