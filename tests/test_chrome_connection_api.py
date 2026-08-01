from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONSOLE = ROOT / "console"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(CONSOLE) not in sys.path:
    sys.path.insert(0, str(CONSOLE))

import onboarding  # noqa: E402


class ChromeConnectionResultTest(unittest.TestCase):
    def test_connected_requires_a_real_composer_and_successful_probe(self) -> None:
        result = onboarding.connection_result_from_probe(
            {
                "ok": True,
                "url": "https://chatgpt.com/c/abc",
                "composer_present": True,
                "failures": [],
            },
            opened={"tab_id": 42, "window_id": 7},
        )

        self.assertEqual(result["code"], "CONNECTED")
        self.assertEqual(result["state"], "connected")
        self.assertEqual(result["title"], "ChatGPT connecté")
        self.assertFalse(result["recoverable"])
        self.assertEqual(result["tab_id"], 42)

    def test_login_page_has_retry_and_close_copy(self) -> None:
        result = onboarding.connection_result_from_probe(
            {
                "ok": False,
                "url": "https://chatgpt.com/auth/login",
                "blocker": "login",
                "composer_present": False,
                "failures": ["login"],
            }
        )

        self.assertEqual(result["code"], "LOGIN_REQUIRED")
        self.assertEqual(result["state"], "manual_action")
        self.assertEqual(result["title"], "Connexion à ChatGPT requise")
        self.assertIn("Connecte-toi dans l’onglet ChatGPT", result["message"])
        self.assertTrue(result["recoverable"])

    def test_captcha_is_never_presented_as_a_connection_failure(self) -> None:
        result = onboarding.connection_result_from_probe(
            {
                "ok": False,
                "url": "https://chatgpt.com/",
                "blocker": "captcha",
                "composer_present": False,
                "failures": ["captcha"],
            }
        )

        self.assertEqual(result["code"], "CAPTCHA")
        self.assertEqual(result["title"], "Vérification requise")
        self.assertIn("termine la vérification", result["message"])
        self.assertNotIn("contour", result["message"].lower())

    def test_missing_composer_is_loading_not_connected(self) -> None:
        result = onboarding.connection_result_from_probe(
            {
                "ok": False,
                "url": "https://chatgpt.com/",
                "blocker": None,
                "composer_present": False,
                "failures": ["composer-missing"],
            }
        )

        self.assertEqual(result["code"], "CHATGPT_LOADING")
        self.assertEqual(result["state"], "checking")
        self.assertTrue(result["recoverable"])

    def test_extension_missing_has_install_copy(self) -> None:
        result = onboarding.connection_result_from_bridge_status(
            {"state": "disconnected", "paired": False}
        )

        self.assertEqual(result["code"], "EXTENSION_MISSING")
        self.assertEqual(result["title"], "Extension Chrome introuvable")
        self.assertIn("Installe ou active", result["message"])
        self.assertTrue(result["recoverable"])

    def test_detected_but_unpaired_extension_is_distinct(self) -> None:
        result = onboarding.connection_result_from_bridge_status(
            {"state": "extension_detected", "paired": False}
        )

        self.assertEqual(result["code"], "EXTENSION_UNPAIRED")
        self.assertEqual(result["state"], "checking")


class FakeChromeDriver:
    driver_name = "chrome_extension"

    def __init__(self, probe: dict) -> None:
        self.probe_payload = probe
        self.open_calls = 0
        self.probe_calls = 0

    async def open_login(self) -> dict:
        self.open_calls += 1
        return {
            "driver": self.driver_name,
            "connected": True,
            "tab_id": 42,
            "window_id": 7,
            "url": "https://chatgpt.com/",
            "probe": self.probe_payload,
        }

    async def probe(self) -> dict:
        self.probe_calls += 1
        return self.probe_payload


class ChromeConnectionActionTest(unittest.IsolatedAsyncioTestCase):
    async def test_open_maps_the_driver_probe(self) -> None:
        driver = FakeChromeDriver(
            {
                "ok": False,
                "url": "https://chatgpt.com/auth/login",
                "blocker": "login",
                "composer_present": False,
                "failures": ["login"],
            }
        )

        result = await onboarding.open_connection_with_driver(driver)

        self.assertEqual(result["code"], "LOGIN_REQUIRED")
        self.assertEqual(driver.open_calls, 1)

    async def test_retry_only_probes_the_existing_tab(self) -> None:
        driver = FakeChromeDriver(
            {
                "ok": True,
                "url": "https://chatgpt.com/c/abc",
                "composer_present": True,
                "failures": [],
            }
        )

        result = await onboarding.retry_connection_with_driver(driver)

        self.assertEqual(result["code"], "CONNECTED")
        self.assertEqual(driver.open_calls, 0)
        self.assertEqual(driver.probe_calls, 1)


if __name__ == "__main__":
    unittest.main()
