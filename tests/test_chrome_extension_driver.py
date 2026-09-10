from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parent.parent
CONSOLE = ROOT / "console"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(CONSOLE) not in sys.path:
    sys.path.insert(0, str(CONSOLE))

from transport.browser import create_browser_driver, load_browser_settings  # noqa: E402
import transport.browser_chrome_extension as chrome_extension_driver  # noqa: E402
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
        self.native_calls: list[tuple[str, str, str]] = []

        async def activate(url: str, name: str, expected_text_hash: str) -> None:
            self.assertRegex(expected_text_hash, r"\A[0-9a-f]{64}\Z")
            self.native_calls.append((url, name, expected_text_hash))

        self.driver = ChromeExtensionBrowserDriver(
            session="session-a",
            manager=self.manager,
            allowed_root=self.root,
            native_activator=activate,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_attachment_name_matching_is_raw_case_sensitive_and_ascii_strict(self) -> None:
        matches = chrome_extension_driver._attachment_name_matches

        for actual in (
            "report.txt",
            "report (1).txt",
            "report(23).txt",
            "report (20260824-015544).txt",
        ):
            with self.subTest(accepted=actual):
                self.assertTrue(matches(actual, "report.txt"))

        for actual, expected in (
            ("Report.txt", "report.txt"),
            ("REPORT (1).txt", "report.txt"),
            ("cafe\N{COMBINING ACUTE ACCENT}.txt", "caf\N{LATIN SMALL LETTER E WITH ACUTE}.txt"),
            ("report (\N{ARABIC-INDIC DIGIT ONE}).txt", "report.txt"),
            ("report (\N{FULLWIDTH DIGIT ONE}).txt", "report.txt"),
            ("report (20260824-0155440).txt", "report.txt"),
            ("report (20260824-01554a).txt", "report.txt"),
            ("report (1).txt.bak", "report.txt"),
            ("report (1) copy.txt", "report.txt"),
        ):
            with self.subTest(rejected=actual):
                self.assertFalse(matches(actual, expected))

    async def test_first_navigation_gets_a_bounded_30s_budget_behind_serialized_allocation(self) -> None:
        # Regression: two writers opening their dedicated tabs concurrently
        # serialize on the extension's tab-allocation lock; the queued
        # writer's 10 s deadline expired while it was still waiting, killing
        # a healthy open (real-Chrome QA 2026-08-14, SELECTION_FAILED with
        # EXTENSION_TIMEOUT). The initial open gets 30 s; switches keep 10 s.
        self.manager.responses["navigate"] = {
            "tab_id": 42,
            "url": "https://chatgpt.com/",
        }
        self.manager.responses["get_state"] = {
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
        await self.driver.navigate("https://chatgpt.com/")
        first = [call for call in self.manager.calls if call[1] == "navigate"]
        self.assertGreater(first[0][3], 29)
        self.assertLessEqual(first[0][3], 30)

        self.manager.responses["navigate"] = {
            "tab_id": 42,
            "url": "https://chatgpt.com/c/abc",
        }
        self.manager.responses["get_state"] = {
            "url": "https://chatgpt.com/c/abc",
            "conversation_id": "abc",
            "title": "Test",
            "blocker": None,
            "composer_present": True,
            "send_button_present": True,
            "stop_button_present": False,
            "streaming": False,
            "messages": [],
        }
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

    async def test_open_login_returns_a_ui_blocker_without_waiting_for_composer_timeout(self) -> None:
        self.manager.responses["probe"] = {
            "ok": False,
            "url": "https://chatgpt.com/?no_universal_links=1#settings",
            "blocker": "ui_blocker",
            "composer_present": True,
            "failures": ["ui_blocker"],
        }

        result = await self.driver.open_login()

        self.assertEqual(result["probe"]["blocker"], "ui_blocker")
        self.assertEqual(
            [call[1] for call in self.manager.calls],
            ["open_chatgpt", "probe"],
        )

    async def test_open_login_uses_one_eight_second_budget_and_reports_an_open_loading_tab(self) -> None:
        from console.chrome_extension import BridgeProtocolError
        from console.onboarding import open_connection_with_driver

        now = [100.0]

        class BudgetManager(FakeManager):
            async def command(
                self,
                session: str,
                action: str,
                payload: dict,
                timeout: float,
            ):
                self.calls.append((session, action, payload, timeout))
                if action == "open_chatgpt":
                    now[0] += 3.0
                    return self.responses[action]
                if action == "probe":
                    now[0] += timeout
                    raise BridgeProtocolError(
                        "EXTENSION_TIMEOUT",
                        "Chrome extension did not answer before the shared deadline",
                    )
                return self.responses[action]

        manager = BudgetManager()
        driver = ChromeExtensionBrowserDriver(
            session="budgeted-open",
            manager=manager,
            allowed_root=self.root,
            retry_sleep=lambda _delay: None,
            monotonic=lambda: now[0],
        )

        result = await open_connection_with_driver(driver)

        open_call, probe_call = manager.calls
        self.assertEqual([open_call[1], probe_call[1]], ["open_chatgpt", "probe"])
        self.assertGreater(open_call[3], 7.9)
        self.assertLessEqual(open_call[3], 8.0)
        self.assertGreater(probe_call[3], 4.9)
        self.assertLessEqual(probe_call[3], 5.0)
        self.assertAlmostEqual(now[0], 108.0, places=6)
        self.assertEqual(result["code"], "CHATGPT_LOADING")
        self.assertEqual(result["state"], "checking")
        self.assertEqual(result["url"], "https://chatgpt.com/")

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

    async def test_attachment_only_send_retains_and_passes_the_confirmed_filename(self) -> None:
        staged = self.root / "cortex-attachment-1234-report.txt"
        staged.write_text("synthetic", encoding="utf-8")
        self.manager.responses["send_bare"] = {
            "ok": True,
            "native_activation": True,
            "url": "https://chatgpt.com/c/abc",
            "attachment_name": "report.txt",
            "before_user_message_ids": [],
        }
        self.manager.responses["get_state"] = {
            "url": "https://chatgpt.com/c/abc",
            "messages": [
                {
                    "id": "bare-after",
                    "role": "user",
                    "text": "",
                    "attachments": [{"name": "report.txt"}],
                }
            ],
        }

        await self.driver.upload_files_named(
            "form input[type=file]",
            [str(staged)],
            "report.txt",
        )
        await self.driver.await_attachment()
        await self.driver.send_bare()

        bare = next(call for call in self.manager.calls if call[1] == "send_bare")
        self.assertEqual(
            bare[2],
            {"name": "report.txt", "native_activation": True},
        )

    async def test_text_attachment_send_passes_and_consumes_the_confirmed_filename(self) -> None:
        staged = self.root / "cortex-attachment-1234-report.txt"
        staged.write_text("synthetic", encoding="utf-8")
        self.manager.responses["send_text"] = [
            {
                "ok": True,
                "native_activation": True,
                "url": "https://chatgpt.com/c/abc",
                "attachment_name": "report.txt",
                "before_user_message_ids": [],
            },
            {"ok": True},
        ]
        self.manager.responses["get_state"] = {
            "url": "https://chatgpt.com/c/abc",
            "messages": [
                {
                    "id": "text-after",
                    "role": "user",
                    "text": "Inspect the synthetic report.",
                    "attachments": [{"name": "report (1).txt"}],
                }
            ],
        }

        await self.driver.upload_files_named(
            "form input[type=file]",
            [str(staged)],
            "report.txt",
        )
        await self.driver.await_attachment()
        await self.driver.send_message("Inspect the synthetic report.")
        await self.driver.send_message("Next plain message.")

        sends = [call for call in self.manager.calls if call[1] == "send_text"]
        self.assertEqual(
            sends[0][2],
            {
                "text": "Inspect the synthetic report.",
                "name": "report.txt",
                "native_activation": True,
            },
        )
        self.assertEqual(sends[1][2], {"text": "Next plain message."})

    async def test_text_attachment_native_activation_receives_only_normalized_text_hash(self) -> None:
        native_calls: list[tuple[str, str, str]] = []

        async def activate(url: str, name: str, expected_text_hash: str) -> None:
            self.assertRegex(expected_text_hash, r"\A[0-9a-f]{64}\Z")
            native_calls.append((url, name, expected_text_hash))

        driver = ChromeExtensionBrowserDriver(
            session="session-native",
            manager=self.manager,
            allowed_root=self.root,
            native_activator=activate,
            retry_sleep=lambda _delay: None,
        )
        staged = self.root / "cortex-attachment-native-report.txt"
        staged.write_text("synthetic", encoding="utf-8")
        self.manager.responses["send_text"] = {
            "ok": True,
            "native_activation": True,
            "url": "https://chatgpt.com/c/native-proof",
            "attachment_name": "report (2024).txt",
            "before_user_message_ids": ["before"],
        }
        self.manager.responses["get_state"] = {
            "url": "https://chatgpt.com/c/native-proof",
            "messages": [
                {
                    "id": "after",
                    "role": "user",
                    "text": "Inspect the synthetic report.",
                    "attachments": [{"name": "report (2024) (20260824-015544).txt"}],
                }
            ],
        }

        await driver.upload_files_named(
            "form input[type=file]",
            [str(staged)],
            "report (2024).txt",
        )
        await driver.await_attachment()
        raw_prompt = "  Inspect the\n synthetic\t report.  "
        await driver.send_message(raw_prompt)

        self.assertEqual(
            native_calls,
            [(
                "https://chatgpt.com/c/native-proof",
                "report (2024).txt",
                "80403fbe9ccdf863efde0979eaa1831ee1a4495302eb4278478b39ce11b55e01",
            )],
        )
        self.assertNotIn(raw_prompt, repr(native_calls))
        send = next(call for call in self.manager.calls if call[1] == "send_text")
        self.assertEqual(
            send[2],
            {
                "text": raw_prompt,
                "name": "report (2024).txt",
                "native_activation": True,
            },
        )

    async def test_native_helper_process_receives_hash_without_prompt_in_stdin_argv_or_logs(self) -> None:
        secret_prompt = "  Private Cortex\n prompt\tthat must not reach AX.  "
        expected_hash = (
            "ec23e1b783c42568359b184a299383cc88d59b4d0daafad70e5c01793a97ee1b"
        )
        captured: dict[str, object] = {}
        driver = ChromeExtensionBrowserDriver(
            session="session-native-process",
            manager=self.manager,
            allowed_root=self.root,
            retry_sleep=lambda _delay: None,
        )
        staged = self.root / "cortex-attachment-native-private.txt"
        staged.write_text("synthetic", encoding="utf-8")
        self.manager.responses["send_text"] = {
            "ok": True,
            "native_activation": True,
            "url": "https://chatgpt.com/c/native-proof",
            "attachment_name": "report.txt",
            "before_user_message_ids": [],
        }
        self.manager.responses["get_state"] = {
            "url": "https://chatgpt.com/c/native-proof",
            "messages": [
                {
                    "id": "after-private",
                    "role": "user",
                    "text": "Private Cortex prompt that must not reach AX.",
                    "attachments": [{"name": "report.txt"}],
                }
            ],
        }
        await driver.upload_files_named(
            "form input[type=file]",
            [str(staged)],
            "report.txt",
        )
        await driver.await_attachment()

        class FakeProcess:
            returncode = 0

            async def communicate(self, request: bytes | None = None):
                captured["stdin"] = request
                return b"PRESS_STARTED\n", b""

        async def launch(*argv, **kwargs):
            captured["argv"] = argv
            captured["launch_kwargs"] = kwargs
            return FakeProcess()

        records: list[logging.LogRecord] = []

        class CaptureHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = CaptureHandler()
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        try:
            with (
                patch.object(
                    chrome_extension_driver,
                    "_compile_macos_ax_helper",
                    AsyncMock(return_value=Path("/tmp/cortex-macos-ax-send")),
                ),
                patch.object(
                    chrome_extension_driver.asyncio,
                    "create_subprocess_exec",
                    side_effect=launch,
                ),
            ):
                await driver.send_message(secret_prompt)
        finally:
            root_logger.removeHandler(handler)

        request_text = bytes(captured["stdin"]).decode("utf-8")
        self.assertEqual(
            json.loads(request_text),
            {
                "expected_url": "https://chatgpt.com/c/native-proof",
                "expected_file_name": "report.txt",
                "expected_text_sha256": expected_hash,
            },
        )
        self.assertNotIn("expected_text\"", request_text)
        self.assertNotIn(secret_prompt, request_text)
        self.assertNotIn(secret_prompt, repr(captured["argv"]))
        self.assertNotIn(
            secret_prompt,
            "\n".join(record.getMessage() for record in records),
        )

    async def test_native_helper_rejects_a_non_sha256_value_before_starting(self) -> None:
        compile_helper = AsyncMock(return_value=Path("/tmp/cortex-macos-ax-send"))
        with patch.object(
            chrome_extension_driver,
            "_compile_macos_ax_helper",
            compile_helper,
        ):
            with self.assertRaises(DriverError) as caught:
                await chrome_extension_driver.activate_macos_ax_send(
                    "https://chatgpt.com/c/native-proof",
                    "report.txt",
                    "raw prompt accidentally passed here",
                )

        self.assertEqual(getattr(caught.exception, "code", None), "SEND_REJECTED")
        compile_helper.assert_not_awaited()

    async def test_native_helper_unexpected_exit_is_delivery_uncertain(self) -> None:
        class FakeProcess:
            returncode = -9

            async def communicate(self, request: bytes | None = None):
                return b"", b"terminated"

        with (
            patch.object(
                chrome_extension_driver,
                "_compile_macos_ax_helper",
                AsyncMock(return_value=Path("/tmp/cortex-macos-ax-send")),
            ),
            patch.object(
                chrome_extension_driver.asyncio,
                "create_subprocess_exec",
                AsyncMock(return_value=FakeProcess()),
            ),
        ):
            with self.assertRaises(DriverError) as caught:
                await chrome_extension_driver.activate_macos_ax_send(
                    "https://chatgpt.com/c/native-proof",
                    "report.txt",
                    "0" * 64,
                )

        self.assertEqual(
            getattr(caught.exception, "code", None),
            "DELIVERY_UNCERTAIN",
        )

    async def test_cancelling_started_native_helper_kills_and_reaps_it_as_uncertain(self) -> None:
        started = asyncio.Event()

        class FakeProcess:
            returncode = None

            def __init__(self):
                self.killed = False
                self.communicate_calls = 0

            async def communicate(self, request: bytes | None = None):
                self.communicate_calls += 1
                if self.communicate_calls == 1:
                    self.request = request
                    started.set()
                    await asyncio.Event().wait()
                self.returncode = -9
                return b"", b"cancelled"

            def kill(self):
                self.killed = True
                self.returncode = -9

        process = FakeProcess()
        with (
            patch.object(
                chrome_extension_driver,
                "_compile_macos_ax_helper",
                AsyncMock(return_value=Path("/tmp/cortex-macos-ax-send")),
            ),
            patch.object(
                chrome_extension_driver.asyncio,
                "create_subprocess_exec",
                AsyncMock(return_value=process),
            ),
        ):
            task = asyncio.create_task(
                chrome_extension_driver.activate_macos_ax_send(
                    "https://chatgpt.com/c/native-proof",
                    "report.txt",
                    "0" * 64,
                )
            )
            await started.wait()
            task.cancel()
            with self.assertRaises(DriverError) as caught:
                await task

        self.assertEqual(getattr(caught.exception, "code", None), "DELIVERY_UNCERTAIN")
        self.assertTrue(process.killed)
        self.assertEqual(process.communicate_calls, 2)

    async def test_cancelling_native_helper_compilation_kills_and_reaps_compiler(self) -> None:
        started = asyncio.Event()

        class FakeCompiler:
            returncode = None

            def __init__(self):
                self.killed = False
                self.communicate_calls = 0

            async def communicate(self):
                self.communicate_calls += 1
                if self.communicate_calls == 1:
                    started.set()
                    await asyncio.Event().wait()
                self.returncode = -9
                return b"", b"cancelled"

            def kill(self):
                self.killed = True
                self.returncode = -9

        process = FakeCompiler()
        with tempfile.TemporaryDirectory() as home:
            with (
                patch.dict(os.environ, {"CORTEX_HOME": home}, clear=False),
                patch.object(chrome_extension_driver.sys, "platform", "darwin"),
                patch.object(
                    chrome_extension_driver.shutil,
                    "which",
                    return_value="/usr/bin/swiftc",
                ),
                patch.object(
                    chrome_extension_driver.asyncio,
                    "create_subprocess_exec",
                    AsyncMock(return_value=process),
                ),
            ):
                task = asyncio.create_task(chrome_extension_driver._compile_macos_ax_helper())
                await started.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                temporary_files = list((Path(home) / "bin").glob(".*.tmp"))

        self.assertTrue(process.killed)
        self.assertEqual(process.communicate_calls, 2)
        self.assertEqual(temporary_files, [])

    async def test_native_helper_timeout_configuration_failure_is_rejected(self) -> None:
        class FakeProcess:
            returncode = 10

            async def communicate(self, request: bytes | None = None):
                return b"", b"timeout setup failed"

        with (
            patch.object(
                chrome_extension_driver,
                "_compile_macos_ax_helper",
                AsyncMock(return_value=Path("/tmp/cortex-macos-ax-send")),
            ),
            patch.object(
                chrome_extension_driver.asyncio,
                "create_subprocess_exec",
                AsyncMock(return_value=FakeProcess()),
            ),
        ):
            with self.assertRaises(DriverError) as caught:
                await chrome_extension_driver.activate_macos_ax_send(
                    "https://chatgpt.com/c/native-proof",
                    "report.txt",
                    "0" * 64,
                )

        self.assertEqual(getattr(caught.exception, "code", None), "SEND_REJECTED")

    async def test_text_attachment_send_consumes_the_filename_after_uncertainty(self) -> None:
        from console.chrome_extension import BridgeProtocolError

        staged = self.root / "cortex-attachment-1234-report.txt"
        staged.write_text("synthetic", encoding="utf-8")
        await self.driver.upload_files_named(
            "form input[type=file]",
            [str(staged)],
            "report.txt",
        )
        await self.driver.await_attachment()
        self.manager.responses["send_text"] = [
            BridgeProtocolError(
                "DELIVERY_UNCERTAIN",
                "trusted click started without delivery proof",
            ),
            {"ok": True},
        ]

        with self.assertRaises(DriverError):
            await self.driver.send_message("Inspect the synthetic report.")
        await self.driver.send_message("Next plain message.")

        sends = [call for call in self.manager.calls if call[1] == "send_text"]
        self.assertEqual(
            sends[0][2],
            {
                "text": "Inspect the synthetic report.",
                "name": "report.txt",
                "native_activation": True,
            },
        )
        self.assertEqual(sends[1][2], {"text": "Next plain message."})

    async def test_attachment_only_send_refuses_an_unconfirmed_filename(self) -> None:
        staged = self.root / "cortex-attachment-1234-report.txt"
        staged.write_text("synthetic", encoding="utf-8")
        self.manager.responses["await_attachment"] = {
            "ok": False,
            "error": "Attachment did not become ready",
        }

        await self.driver.upload_files_named(
            "form input[type=file]",
            [str(staged)],
            "report.txt",
        )
        await self.driver.await_attachment()

        with self.assertRaisesRegex(DriverError, "no confirmed attachment"):
            await self.driver.send_bare()
        self.assertNotIn(
            "send_bare",
            [action for _, action, _, _ in self.manager.calls],
        )

    async def test_failed_attachment_readiness_never_returns_the_dirty_writer_to_pool(self) -> None:
        staged = self.root / "dirty-upload.txt"
        staged.write_text("synthetic", encoding="utf-8")
        self.manager.responses["await_attachment"] = {
            "ok": False,
            "error": "Attachment did not become ready",
        }

        await self.driver.upload_files_named(
            "form input[type=file]",
            [str(staged)],
            "dirty-upload.txt",
        )
        await self.driver.await_attachment()
        await self.driver.close()

        release = [
            call for call in self.manager.calls if call[1] == "release_session"
        ][-1]
        self.assertEqual(release[2], {"reusable": False})

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
        self.driver.target_url = "https://chatgpt.com/c/screenshot-proof"

        result = await self.driver.take_screenshot(str(destination))

        self.assertEqual(destination.read_bytes(), PNG)
        self.assertEqual(result["path"], str(destination))
        self.assertEqual(result["tab_id"], 42)
        self.assertFalse(destination.with_suffix(".tmp").exists())
        capture = [call for call in self.manager.calls if call[1] == "capture_screenshot"]
        self.assertEqual(
            capture[-1][2],
            {"expected_url": "https://chatgpt.com/c/screenshot-proof"},
        )

    async def test_screenshot_refuses_without_a_selected_target(self) -> None:
        destination = self.root / "captures" / "unbound.png"

        with self.assertRaisesRegex(DriverError, "selected ChatGPT target"):
            await self.driver.take_screenshot(str(destination))

        self.assertFalse(destination.exists())
        self.assertNotIn(
            "capture_screenshot",
            [action for _, action, _, _ in self.manager.calls],
        )

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
        release = next(call for call in self.manager.calls if call[1] == "release_session")
        self.assertEqual(release[2], {"reusable": True})

    async def test_failed_native_activation_never_returns_the_dirty_writer_to_pool(self) -> None:
        async def reject(_url: str, _name: str, expected_text_hash: str) -> None:
            self.assertRegex(expected_text_hash, r"\A[0-9a-f]{64}\Z")
            raise DriverError("native activation rejected")

        driver = ChromeExtensionBrowserDriver(
            session="cortex-conv-dirty",
            manager=self.manager,
            allowed_root=self.root,
            native_activator=reject,
        )
        staged = self.root / "dirty-report.txt"
        staged.write_text("synthetic", encoding="utf-8")
        self.manager.responses["send_text"] = {
            "ok": True,
            "native_activation": True,
            "url": "https://chatgpt.com/c/dirty",
            "attachment_name": "dirty-report.txt",
            "before_user_message_ids": [],
        }
        await driver.upload_files_named(
            "form input[type=file]",
            [str(staged)],
            "dirty-report.txt",
        )
        await driver.await_attachment()

        with self.assertRaises(DriverError):
            await driver.send_message("Do not reuse this draft.")
        await driver.close()

        release = [call for call in self.manager.calls if call[1] == "release_session"][-1]
        self.assertEqual(release[2], {"reusable": False})

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
    def test_native_helper_skips_readable_unlabelled_buttons_without_failing_open(self) -> None:
        source = (ROOT / "transport" / "macos_ax_send.swift").read_text(
            encoding="utf-8"
        )

        self.assertIn("private enum ControlLabelRead", source)
        self.assertIn("case label(String)", source)
        self.assertIn("case empty", source)
        self.assertIn("case unreadable", source)
        self.assertIn("case .empty:", source)
        self.assertIn("case .unreadable:", source)
        self.assertIn("case let .label(value):", source)
        self.assertNotIn("return label.isEmpty ? nil : label", source)
        self.assertNotIn("if rawText.isEmpty { continue }", source)

    def test_native_helper_rejects_an_unreadable_common_ancestor_role(self) -> None:
        source = (ROOT / "transport" / "macos_ax_send.swift").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "private func stringAttribute(_ element: AXUIElement, "
            "_ name: CFString) -> String?",
            source,
        )
        self.assertIn("guard let commonAncestorRole = stringAttribute(", source)
        self.assertNotIn('(attribute(element, name) as? String) ?? ""', source)

    def test_native_helper_accepts_a_named_image_attachment_group(self) -> None:
        source = (ROOT / "transport" / "macos_ax_send.swift").read_text(
            encoding="utf-8"
        )

        self.assertIn("private func visibleEnabledElement(", source)
        self.assertIn("var attachmentGroups: [AXUIElement] = []", source)
        self.assertIn('if role == (kAXGroupRole as String)', source)
        self.assertIn(
            "attachmentButtons.isEmpty ? attachmentGroups : attachmentButtons",
            source,
        )

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
