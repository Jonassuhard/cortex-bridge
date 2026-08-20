from __future__ import annotations

import base64
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONSOLE = ROOT / "console"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(CONSOLE) not in sys.path:
    sys.path.insert(0, str(CONSOLE))

from transport.browser import create_browser_driver, load_browser_settings  # noqa: E402
from transport.browser_chrome_extension import (  # noqa: E402
    ChromeExtensionBrowserDriver,
    EXTENSION_FILE_LIMIT_BYTES,
)
from transport.chatgpt_web.adapter import (  # noqa: E402
    ChatGPTWebTransport,
    ConversationLock,
    DriverError,
    TabClosedError,
    TransportError,
)


PNG = b"\x89PNG\r\n\x1a\n" + b"cortex-test-png"


class FakeManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict, float]] = []
        self.responses: dict[str, object] = {
            "open_chatgpt": {
                "tab_id": 42,
                "window_id": 7,
                "url": "https://chatgpt.com/",
            },
            "list_tabs": {
                "tabs": [
                    {
                        "session": "session-a",
                        "tab_id": 42,
                        "window_id": 7,
                        "url": "https://chatgpt.com/",
                        "active": True,
                    }
                ]
            },
            "probe": {
                "ok": True,
                "url": "https://chatgpt.com/",
                "title": "ChatGPT",
                "composer_present": True,
                "failures": [],
                "warnings": [],
            },
            "get_state": {
                "url": "https://chatgpt.com/c/abc",
                "conversation_id": "abc",
                "title": "Test",
                "blocker": None,
                "composer_present": True,
                "send_button_present": True,
                "stop_button_present": False,
                "streaming": False,
                "messages": [],
            },
            "get_light_state": {
                "url": "https://chatgpt.com/c/abc",
                "conversation_id": "abc",
                "title": "Test",
                "message_count": 0,
                "first_id": None,
                "last_id": None,
                "streaming": False,
                "composer_present": True,
            },
            "spa_navigate": {"handled": True},
            "list_conversations": [],
            "send_text": {"ok": True},
            "press_stop": {"stopped": True},
            "attachment_begin": {"accepted": True},
            "attachment_chunk": {"accepted": True},
            "attachment_commit": {"attached": True},
            "await_attachment": {"ok": True},
            "send_bare": {"ok": True},
            "capture_screenshot": {
                "data_url": "data:image/png;base64," + base64.b64encode(PNG).decode("ascii"),
                "tab_id": 42,
            },
            "list_models": {"selected": "GPT-5", "models": ["GPT-5"]},
            "select_model": {"selected": "GPT-5"},
            "release_session": {"released": True, "tab_id": 42},
            "close_tab": {"closed": True},
            "navigate": {"tab_id": 42, "url": "https://chatgpt.com/c/abc"},
        }
        self.status = {
            "state": "paired",
            "extension_connected": True,
            "paired": True,
            "pending_commands": 0,
        }

    def public_status(self) -> dict:
        return dict(self.status)

    async def command(self, session: str, action: str, payload: dict, timeout: float):
        self.calls.append((session, action, payload, timeout))
        response = self.responses[action]
        if isinstance(response, list):
            response = response.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class ChromeExtensionDriverContractTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.manager = FakeManager()
        self.driver = ChromeExtensionBrowserDriver(
            session="session-a",
            manager=self.manager,
            allowed_root=self.root,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def test_first_navigation_gets_a_bounded_30s_budget_behind_serialized_allocation(self) -> None:
        # Regression: two writers opening their dedicated tabs concurrently
        # serialize on the extension's tab-allocation lock; the queued
        # writer's 10 s deadline expired while it was still waiting, killing
        # a healthy open (real-Chrome QA 2026-08-14, SELECTION_FAILED with
        # EXTENSION_TIMEOUT). The initial open gets 30 s; switches keep 10 s.
        await self.driver.navigate("https://chatgpt.com/")
        first = [call for call in self.manager.calls if call[1] == "navigate"]
        self.assertGreater(first[0][3], 29)
        self.assertLessEqual(first[0][3], 30)

        await self.driver.navigate("https://chatgpt.com/c/abc")
        later = [call for call in self.manager.calls if call[1] == "navigate"]
        self.assertGreater(later[-1][3], 9)
        self.assertLessEqual(later[-1][3], 10)

    async def test_health_is_true_only_for_a_paired_extension(self) -> None:
        health = await self.driver.health()
        self.assertTrue(health["connected"])
        self.assertEqual(health["driver"], "chrome_extension")
        self.assertEqual(health["tabs"], 1)

        self.manager.status.update(
            state="disconnected", extension_connected=False, paired=False
        )
        disconnected = await self.driver.health()
        self.assertFalse(disconnected["connected"])
        self.assertEqual(disconnected["tabs"], 0)

    async def test_open_login_opens_and_probes_the_bound_tab(self) -> None:
        result = await self.driver.open_login()

        self.assertEqual(result["driver"], "chrome_extension")
        self.assertTrue(result["connected"])
        self.assertTrue(result["probe"]["composer_present"])
        self.assertEqual(
            [call[1] for call in self.manager.calls],
            ["open_chatgpt", "probe"],
        )

    async def test_open_login_waits_until_the_reloaded_chatgpt_composer_is_ready(self) -> None:
        self.manager.responses["probe"] = [
            {
                "ok": False,
                "url": "https://chatgpt.com/",
                "composer_present": False,
                "blocker": None,
                "failures": ["composer"],
            },
            {
                "ok": True,
                "url": "https://chatgpt.com/",
                "composer_present": True,
                "blocker": None,
                "failures": [],
            },
        ]

        result = await self.driver.open_login()

        self.assertTrue(result["probe"]["composer_present"])
        self.assertEqual(
            [call[1] for call in self.manager.calls],
            ["open_chatgpt", "probe", "probe"],
        )

    async def test_structured_state_navigation_and_send_contract(self) -> None:
        await self.driver.navigate("https://chatgpt.com/c/abc")
        self.assertTrue(await self.driver.spa_navigate("https://chatgpt.com/c/abc"))
        self.assertEqual((await self.driver.get_state())["conversation_id"], "abc")
        self.assertEqual((await self.driver.get_light_state())["message_count"], 0)
        await self.driver.send_message("hello")
        await self.driver.press_stop()

        calls = {action: payload for _, action, payload, _ in self.manager.calls}
        self.assertEqual(calls["navigate"], {"url": "https://chatgpt.com/c/abc"})
        self.assertEqual(calls["send_text"], {"text": "hello"})

    async def test_spa_navigation_falls_back_to_full_navigation_when_target_is_absent(self) -> None:
        self.manager.responses["spa_navigate"] = {"handled": False}
        self.manager.responses["navigate"] = {
            "tab_id": 42,
            "url": "https://chatgpt.com/c/target",
        }

        handled = await self.driver.spa_navigate("https://chatgpt.com/c/target")

        self.assertTrue(handled)
        self.assertTrue(self.driver.selection_used_full_navigation)
        self.assertEqual(self.driver.target_url, "https://chatgpt.com/c/target")
        self.assertEqual(
            [call[1] for call in self.manager.calls],
            ["spa_navigate", "navigate"],
        )

    async def test_send_waits_for_a_proven_missing_content_script_before_delivery(self) -> None:
        from console.chrome_extension import BridgeProtocolError

        self.manager.responses["send_text"] = [
            BridgeProtocolError(
                "TAB_UNAVAILABLE",
                "The ChatGPT content script is not available yet",
            ),
            {"ok": True},
        ]
        driver = ChromeExtensionBrowserDriver(
            session="session-a",
            manager=self.manager,
            allowed_root=self.root,
            retry_sleep=lambda _delay: None,
        )

        await driver.send_message("CORTEX-CONTENT-SCRIPT-READY")

        sends = [call for call in self.manager.calls if call[1] == "send_text"]
        self.assertEqual(len(sends), 2)

    async def test_send_waits_for_a_transient_pre_delivery_composer(self) -> None:
        from console.chrome_extension import BridgeProtocolError

        self.manager.responses["send_text"] = [
            BridgeProtocolError(
                "PRE_DELIVERY_NOT_READY",
                "COMPOSER_MISSING: ChatGPT composer not found",
            ),
            {"ok": True},
        ]
        driver = ChromeExtensionBrowserDriver(
            session="session-a",
            manager=self.manager,
            allowed_root=self.root,
            retry_sleep=lambda _delay: None,
        )

        await driver.send_message("CORTEX-COMPOSER-READY")

        sends = [call for call in self.manager.calls if call[1] == "send_text"]
        self.assertEqual(len(sends), 2)

    async def test_send_never_retries_an_ambiguous_tab_error(self) -> None:
        from console.chrome_extension import BridgeProtocolError

        self.manager.responses["send_text"] = BridgeProtocolError(
            "TAB_UNAVAILABLE",
            "The bound tab is not ChatGPT",
        )
        driver = ChromeExtensionBrowserDriver(
            session="session-a",
            manager=self.manager,
            allowed_root=self.root,
            retry_sleep=lambda _delay: None,
        )

        with self.assertRaises(DriverError):
            await driver.send_message("CORTEX-DO-NOT-RETRY")

        sends = [call for call in self.manager.calls if call[1] == "send_text"]
        self.assertEqual(len(sends), 1)

    async def test_raw_javascript_evaluation_is_never_available(self) -> None:
        with self.assertRaisesRegex(DriverError, "raw evaluation is unavailable"):
            await self.driver.evaluate("document.cookie")
        self.assertEqual(self.manager.calls, [])

    async def test_upload_uses_bounded_chunks_and_never_sends_a_path(self) -> None:
        staged = self.root / "small.txt"
        staged.write_bytes(b"a" * 600_000)

        await self.driver.upload_files("form input[type=file]", [str(staged)])
        await self.driver.await_attachment()

        actions = [call[1] for call in self.manager.calls]
        self.assertEqual(actions[0], "attachment_begin")
        self.assertEqual(actions[-1], "await_attachment")
        self.assertGreater(actions.count("attachment_chunk"), 1)
        self.assertEqual(self.manager.calls[-1][2], {"name": "small.txt"})
        wire = repr(self.manager.calls)
        self.assertNotIn(str(staged), wire)

    async def test_named_upload_keeps_the_user_filename_off_the_staging_prefix(self) -> None:
        staged = self.root / "cortex-attachment-1234-report.txt"
        staged.write_text("synthetic", encoding="utf-8")

        await self.driver.upload_files_named(
            "form input[type=file]",
            [str(staged)],
            "report.txt",
        )
        await self.driver.await_attachment()

        begin = next(call for call in self.manager.calls if call[1] == "attachment_begin")
        self.assertEqual(begin[2]["name"], "report.txt")
        self.assertEqual(self.manager.calls[-1][2], {"name": "report.txt"})

    async def test_upload_rejects_outside_and_oversized_files_before_sending(self) -> None:
        outside = Path(self.tmp.name).parent / "outside-cortex.txt"
        outside.write_text("private", encoding="utf-8")
        try:
            with self.assertRaisesRegex(DriverError, "managed staging directory"):
                await self.driver.upload_files("form input[type=file]", [str(outside)])
        finally:
            outside.unlink(missing_ok=True)

        oversized = self.root / "large.bin"
        with oversized.open("wb") as handle:
            handle.truncate(EXTENSION_FILE_LIMIT_BYTES + 1)
        with self.assertRaisesRegex(DriverError, "25 MiB"):
            await self.driver.upload_files("form input[type=file]", [str(oversized)])
        self.assertEqual(self.manager.calls, [])

    async def test_screenshot_is_validated_and_written_atomically_under_cortex_home(self) -> None:
        destination = self.root / "captures" / "chatgpt.png"

        result = await self.driver.take_screenshot(str(destination))

        self.assertEqual(destination.read_bytes(), PNG)
        self.assertEqual(result["path"], str(destination))
        self.assertEqual(result["tab_id"], 42)
        self.assertFalse(destination.with_suffix(".tmp").exists())

    async def test_tab_closed_error_uses_the_adapter_taxonomy(self) -> None:
        from console.chrome_extension import BridgeProtocolError

        self.manager.responses["probe"] = BridgeProtocolError(
            "TAB_CLOSED", "The bound tab was closed"
        )

        with self.assertRaises(TabClosedError):
            await self.driver.probe()

    async def test_logical_close_releases_binding_without_closing_users_tab(self) -> None:
        await self.driver.close()
        await self.driver.close()

        actions = [call[1] for call in self.manager.calls]
        self.assertEqual(actions.count("release_session"), 1)
        self.assertNotIn("close_tab", [call[1] for call in self.manager.calls])

    async def test_structured_upload_failure_never_falls_back_to_raw_evaluation(self) -> None:
        from console.chrome_extension import BridgeProtocolError

        staged = self.root / "rejected.txt"
        staged.write_text("safe fixture", encoding="utf-8")
        self.manager.responses["attachment_begin"] = BridgeProtocolError(
            "ATTACHMENT_REJECTED", "Chrome rejected this attachment"
        )
        transport = ChatGPTWebTransport(self.driver)
        transport.lock = ConversationLock(
            "https://chatgpt.com/c/abc", "abc", "Test", 1.0
        )

        with self.assertRaises(TransportError) as caught:
            await transport.send_with_attachment(
                "describe this file",
                str(staged),
                image=False,
            )

        self.assertEqual(caught.exception.code, "ATTACHMENT_FAILED")
        self.assertNotIn("raw evaluation", str(caught.exception))


class ChromeExtensionFactoryTest(unittest.TestCase):
    def test_chrome_extension_is_the_default_product_transport(self) -> None:
        self.assertEqual(load_browser_settings({})["browser_transport"], "chrome_extension")
        driver = create_browser_driver(
            "factory",
            settings={"browser_transport": "chrome_extension"},
        )
        self.assertEqual(driver.driver_name, "chrome_extension")

    def test_chrome_extension_factory_replaces_a_closed_cached_session(self) -> None:
        first = create_browser_driver(
            "factory-recreate-closed",
            settings={"browser_transport": "chrome_extension"},
        )
        first._closed = True

        second = create_browser_driver(
            "factory-recreate-closed",
            settings={"browser_transport": "chrome_extension"},
        )

        self.assertIsNot(first, second)
        self.assertTrue(second.live)

    def test_legacy_development_transports_remain_explicit(self) -> None:
        for name in ("playwright", "webbridge"):
            self.assertEqual(
                load_browser_settings({"browser_transport": name})["browser_transport"],
                name,
            )


if __name__ == "__main__":
    unittest.main()
