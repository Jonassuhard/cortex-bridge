"""Playwright browser-driver contract tests.

Every browser interaction stays on a loopback fixture page.
"""

from __future__ import annotations

import asyncio
import http.server
import json
import tempfile
import threading
import unittest
from pathlib import Path

from transport.browser import BrowserDriver, create_browser_driver
from transport.browser_playwright import PlaywrightBrowserDriver
from transport.chatgpt_web.adapter import (
    ChatGPTWebTransport,
    ConversationLock,
    DriverError,
    WebBridgeDriver,
)


_FIXTURE_HTML = b"""<!doctype html>
<html>
  <head><title>Cortex Playwright Fixture</title></head>
  <body>
    <input id="upload" type="file">
    <output id="uploaded"></output>
    <script>
      document.querySelector("#upload").addEventListener("change", (event) => {
        document.querySelector("#uploaded").textContent =
          event.target.files[0]?.name || "";
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
            await driver.close()
        self.tempdir.cleanup()

    def driver(self, session: str) -> PlaywrightBrowserDriver:
        driver = PlaywrightBrowserDriver(
            session=session,
            profile_root=self.profile_root,
            headless=True,
        )
        self.drivers.append(driver)
        return driver

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
        self.assertEqual(
            driver.profile_path.resolve(),
            (self.profile_root / "contract-a").resolve(),
        )

    async def test_health_does_not_launch_profile_before_explicit_browser_use(self) -> None:
        driver = self.driver("diagnostic-only")
        health = await driver.health()
        self.assertFalse(health["connected"])
        self.assertFalse(driver.started)
        self.assertEqual(health["driver"], "playwright")

    async def test_profiles_are_isolated_and_same_session_reopens_after_close(self) -> None:
        first = self.driver("persistent-a")
        second = self.driver("persistent-b")
        await asyncio.gather(first.navigate(self.url), second.navigate(self.url))
        await first.evaluate("localStorage.setItem('owner', 'A')")
        self.assertIsNone(await second.evaluate("localStorage.getItem('owner')"))
        await first.close()
        await second.close()

        reopened = self.driver("persistent-a")
        await reopened.navigate(self.url)
        self.assertEqual(await reopened.evaluate("localStorage.getItem('owner')"), "A")

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


if __name__ == "__main__":
    unittest.main()
