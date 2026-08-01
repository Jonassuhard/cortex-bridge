from __future__ import annotations

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

from console.chrome_extension import BridgeProtocolError  # noqa: E402
from transport.browser_chrome_extension import ChromeExtensionBrowserDriver  # noqa: E402
from transport.chatgpt_web.adapter import (  # noqa: E402
    ChatGPTWebTransport,
    ConversationLock,
    DriverError,
)


class FlakyReadManager:
    def __init__(self) -> None:
        self.calls = 0

    async def command(
        self,
        session: str,
        action: str,
        payload: dict,
        timeout: float,
    ) -> dict:
        del session, payload, timeout
        self.calls += 1
        if action == "get_state" and self.calls < 3:
            raise BridgeProtocolError(
                "TAB_UNAVAILABLE",
                "The ChatGPT content script is not available yet",
            )
        return {
            "url": "https://chatgpt.com/",
            "conversation_id": None,
            "title": "ChatGPT",
            "blocker": None,
            "composer_present": True,
            "send_button_present": True,
            "stop_button_present": False,
            "streaming": False,
            "messages": [],
        }


class UnboundWriterManager:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def command(
        self,
        session: str,
        action: str,
        payload: dict,
        timeout: float,
    ) -> dict:
        del session, timeout
        self.actions.append(action)
        if action == "spa_navigate":
            raise BridgeProtocolError(
                "TAB_UNAVAILABLE",
                "No ChatGPT tab is bound to this Cortex session",
            )
        if action == "navigate":
            return {"tab_id": 42, "window_id": 7, "url": payload["url"]}
        if action == "get_state":
            return {
                "url": payload.get("url", "https://chatgpt.com/c/cortex-regression"),
                "conversation_id": "cortex-regression",
                "title": "Cortex regression",
                "blocker": None,
                "composer_present": True,
                "send_button_present": False,
                "stop_button_present": False,
                "streaming": False,
                "messages": [],
            }
        raise AssertionError(f"unexpected action: {action}")


class UnavailableSendManager:
    def __init__(self) -> None:
        self.calls = 0

    async def command(
        self,
        session: str,
        action: str,
        payload: dict,
        timeout: float,
    ) -> dict:
        del session, payload, timeout
        self.calls += 1
        if action != "send_text":
            raise AssertionError(f"unexpected action: {action}")
        raise BridgeProtocolError(
            "TAB_UNAVAILABLE",
            "The ChatGPT content script is not available yet",
        )


class LoadingComposerManager:
    def __init__(self) -> None:
        self.actions: list[str] = []
        self.state_reads = 0

    async def command(
        self,
        session: str,
        action: str,
        payload: dict,
        timeout: float,
    ) -> dict:
        del session, timeout
        self.actions.append(action)
        if action == "navigate":
            return {"tab_id": 42, "window_id": 7, "url": payload["url"]}
        if action == "get_state":
            self.state_reads += 1
            return {
                "url": "https://chatgpt.com/",
                "conversation_id": None,
                "title": "ChatGPT",
                "blocker": None,
                "composer_present": self.state_reads >= 3,
                "send_button_present": False,
                "stop_button_present": False,
                "streaming": False,
                "messages": [],
            }
        raise AssertionError(f"unexpected action: {action}")


class ClosedSelectionManager:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def command(
        self,
        session: str,
        action: str,
        payload: dict,
        timeout: float,
    ) -> dict:
        del session, timeout
        self.actions.append(action)
        if action == "spa_navigate":
            raise BridgeProtocolError("TAB_CLOSED", "The bound tab was closed")
        if action == "navigate":
            return {"tab_id": 43, "window_id": 7, "url": payload["url"]}
        if action == "get_state":
            return {
                "url": "https://chatgpt.com/c/recovered-view",
                "conversation_id": "recovered-view",
                "title": "Recovered view",
                "blocker": None,
                "composer_present": True,
                "send_button_present": False,
                "stop_button_present": False,
                "streaming": False,
                "messages": [],
            }
        raise AssertionError(f"unexpected action: {action}")


class DelayedBackgroundPaintDriver:
    requires_content_stability = True

    def __init__(self) -> None:
        self.reads = 0
        self.focused = False

    async def get_state(self) -> dict:
        self.reads += 1
        streaming = self.reads <= 2
        text = "CB-QA-A-1\nCB-QA-A-END" if self.focused else "CB"
        return {
            "url": "https://chatgpt.com/c/background-tab",
            "conversation_id": "background-tab",
            "title": "Background tab",
            "blocker": None,
            "composer_present": True,
            "send_button_present": False,
            "stop_button_present": streaming,
            "streaming": streaming,
            "messages": [
                {
                    "id": "assistant-background",
                    "role": "assistant",
                    "text": text,
                    "code_blocks": [],
                }
            ],
        }

    async def focus_tab(self) -> None:
        self.focused = True


class ChromeExtensionReadinessRegressionTest(unittest.IsolatedAsyncioTestCase):
    async def test_read_waits_for_content_script_after_navigation(self) -> None:
        manager = FlakyReadManager()
        with tempfile.TemporaryDirectory() as temporary:
            driver = ChromeExtensionBrowserDriver(
                session="cortex-conv-regression",
                manager=manager,
                allowed_root=temporary,
                retry_sleep=lambda _: None,
            )

            state = await driver.get_state()

        self.assertTrue(state["composer_present"])
        self.assertEqual(manager.calls, 3)

    async def test_existing_conversation_creates_a_dedicated_writer_tab(self) -> None:
        manager = UnboundWriterManager()
        url = "https://chatgpt.com/c/cortex-regression"
        with tempfile.TemporaryDirectory() as temporary:
            driver = ChromeExtensionBrowserDriver(
                session="cortex-conv-regression",
                manager=manager,
                allowed_root=temporary,
            )

            handled = await driver.spa_navigate(url)

        self.assertTrue(handled)
        self.assertEqual(driver.target_url, url)
        self.assertEqual(manager.actions, ["spa_navigate", "navigate", "get_state"])

    async def test_mutating_send_is_never_retried_automatically(self) -> None:
        manager = UnavailableSendManager()
        with tempfile.TemporaryDirectory() as temporary:
            driver = ChromeExtensionBrowserDriver(
                session="cortex-conv-regression",
                manager=manager,
                allowed_root=temporary,
            )

            with self.assertRaisesRegex(DriverError, "TAB_UNAVAILABLE"):
                await driver.send_message("must be attempted exactly once")

        self.assertEqual(manager.calls, 1)

    async def test_navigation_waits_for_a_ready_composer_before_returning(self) -> None:
        manager = LoadingComposerManager()
        with tempfile.TemporaryDirectory() as temporary:
            driver = ChromeExtensionBrowserDriver(
                session="cortex-conv-regression",
                manager=manager,
                allowed_root=temporary,
                retry_sleep=lambda _: None,
            )

            await driver.navigate("https://chatgpt.com/")

        self.assertEqual(manager.actions, ["navigate", "get_state", "get_state", "get_state"])

    async def test_closed_selection_tab_is_recreated_before_any_write(self) -> None:
        manager = ClosedSelectionManager()
        with tempfile.TemporaryDirectory() as temporary:
            driver = ChromeExtensionBrowserDriver(
                session="cortex-view-read-only",
                manager=manager,
                allowed_root=temporary,
            )

            handled = await driver.spa_navigate(
                "https://chatgpt.com/c/recovered-view"
            )

        self.assertTrue(handled)
        self.assertEqual(manager.actions, ["spa_navigate", "navigate", "get_state"])

    async def test_response_waits_for_the_final_background_tab_paint(self) -> None:
        driver = DelayedBackgroundPaintDriver()
        transport = ChatGPTWebTransport(
            driver,
            stability_interval=0.02,
            post_stream_stability_interval=0.12,
            poll_interval=0.01,
            max_wait=1,
        )
        transport.lock = ConversationLock(
            "https://chatgpt.com/c/background-tab",
            "background-tab",
            "Background tab",
            1.0,
        )

        response = await transport.await_response()

        self.assertEqual(response["text"], "CB-QA-A-1\nCB-QA-A-END")
        self.assertTrue(driver.focused)


if __name__ == "__main__":
    unittest.main()
