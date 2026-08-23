"""DOM-breakage resilience — the differentiating README claim.

When ChatGPT changes its DOM (composer gone, send button gone, sidebar
restructured), Cortex Bridge must:

1. report the breakage truthfully (never launder a broken probe into ok),
2. fail closed with a machine-readable code (never resend, never guess),
3. never substitute another browser, profile or transport silently.

The happy-path contract lives in tests/test_chrome_extension_driver.py; this
file pins the broken-DOM side of the same contract.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONSOLE = ROOT / "console"
for path in (str(ROOT), str(CONSOLE)):
    if path not in sys.path:
        sys.path.insert(0, path)

from transport.browser import create_browser_driver, load_browser_settings  # noqa: E402
from transport.browser_chrome_extension import ChromeExtensionBrowserDriver  # noqa: E402
from transport.chatgpt_web.adapter import DriverError  # noqa: E402


class BrokenDomManager:
    """Extension-side manager simulating a ChatGPT DOM update."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict, float]] = []
        self.status = {"state": "paired", "paired": True}
        self.probe_payload = {
            "ok": False,
            "url": "https://chatgpt.com/c/abc",
            "title": "ChatGPT",
            "composer_present": False,
            "failures": ["composer_missing", "send_button_missing"],
            "warnings": [],
        }
        self.send_error = DriverError("COMPOSER_MISSING: composer selector not found")
        self.send_error.code = "COMPOSER_MISSING"

    def public_status(self) -> dict:
        return dict(self.status)

    async def command(self, session: str, action: str, payload: dict, timeout: float):
        self.calls.append((session, action, payload, timeout))
        if action == "probe":
            return dict(self.probe_payload)
        if action == "send_text":
            raise self.send_error
        if action == "list_tabs":
            return {"tabs": []}
        raise AssertionError(f"unexpected action {action}")


class DomBreakageResilienceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.manager = BrokenDomManager()
        self.driver = ChromeExtensionBrowserDriver(
            session="session-dom-break",
            manager=self.manager,
            allowed_root=Path(self.tmp.name),
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def test_probe_surfaces_broken_dom_truthfully(self) -> None:
        """A broken DOM is reported as broken — never laundered into ok."""
        result = await self.driver.probe()
        self.assertFalse(result["ok"])
        self.assertFalse(result["composer_present"])
        self.assertIn("composer_missing", result["failures"])

    async def test_send_fails_closed_with_machine_code_and_no_retry(self) -> None:
        """Composer missing → one attempt, structured code, no silent resend."""
        with self.assertRaises(DriverError) as cm:
            await self.driver.send_message("hello")
        self.assertEqual(cm.exception.code, "COMPOSER_MISSING")
        sends = [c for c in self.manager.calls if c[1] == "send_text"]
        self.assertEqual(len(sends), 1, "a broken DOM must never trigger a resend")

    async def test_health_reports_disconnected_when_extension_unpaired(self) -> None:
        self.manager.status = {"state": "disconnected", "paired": False}
        health = await self.driver.health()
        self.assertFalse(health["connected"])
        self.assertEqual(health["driver"], "chrome_extension")

    def test_factory_never_substitutes_another_transport(self) -> None:
        """Broken DOM changes nothing to transport selection: no fallback."""
        driver = create_browser_driver(
            "dom-break-factory",
            settings={"browser_transport": "chrome_extension"},
        )
        self.assertEqual(driver.driver_name, "chrome_extension")
        self.assertIsInstance(driver, ChromeExtensionBrowserDriver)
        # An unknown transport name is rejected, never silently substituted.
        with self.assertRaises(ValueError):
            load_browser_settings({"browser_transport": "auto-fallback-please"})

    async def test_raw_evaluation_stays_unavailable_when_dom_breaks(self) -> None:
        """No escape hatch: raw JS evaluation cannot replace a broken selector."""
        self.assertFalse(self.driver.supports_raw_evaluation)
        with self.assertRaises(DriverError):
            await self.driver.evaluate("document.querySelector('#prompt-textarea')")


if __name__ == "__main__":
    unittest.main()
