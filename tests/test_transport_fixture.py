"""Phase 4 — required browser transport fixture tests (mission spec §22).

All 20 tests run against the local fixture server (never real ChatGPT,
never the WebBridge daemon, never the console on 8420). stdlib unittest:
    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestration import protocol  # noqa: E402
from transport.chatgpt_web.adapter import (  # noqa: E402
    CHATGPT_RESPONSE_TIMEOUT,
    CONVERSATION_MISMATCH,
    DELIVERY_UNCERTAIN,
    GENERATION_CANCELLED,
    DUPLICATE_EXTRACTION,
    TAB_CLOSED,
    TRANSPORT_PAUSED,
    BlockerDetected,
    ChatGPTWebTransport,
    ConversationLock,
    LocalFixtureDriver,
    TransportError,
)
from transport.chatgpt_web.fixture import FixtureServer  # noqa: E402


class FixtureTransportTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.server = FixtureServer().start()
        self.addCleanup(self.server.stop)
        self.driver = LocalFixtureDriver(self.server.base_url)
        self.transport = self._make_transport(self.driver)

    def _make_transport(self, driver, **overrides):
        params = {"stability_interval": 0.15, "poll_interval": 0.03, "max_wait": 5.0}
        params.update(overrides)
        return ChatGPTWebTransport(driver, **params)

    @property
    def conv_url(self):
        return f"{self.server.base_url}/c/conv-1"

    async def _select(self):
        return await self.transport.select_conversation(self.conv_url)

    def _user_messages(self, cid="conv-1"):
        return [m for m in self.server.conversation(cid).messages if m["role"] == "user"]

    # 1. conversation selection
    async def test_01_conversation_selection(self):
        lock = await self._select()
        self.assertEqual(lock.identity, "conv-1")
        self.assertEqual(lock.url, self.conv_url)
        self.assertEqual(lock.title, "Fixture conversation conv-1")
        self.assertGreater(lock.selected_at, 0)

    # 2. conversation lock
    async def test_02_conversation_lock(self):
        lock = await self._select()
        await self.transport.verify_lock()  # does not raise
        restored = ConversationLock.from_dict(lock.to_dict())
        self.assertEqual(restored.identity, lock.identity)
        self.assertEqual(restored.url, lock.url)

    # 3. sending a user message
    async def test_03_sending_user_message(self):
        self.server.queue_replies(["acknowledged"], "conv-1")
        await self._select()
        sent = await self.transport.send_message("Hello from Cortex Bridge")
        self.assertEqual(sent["role"], "user")
        state = await self.driver.get_state()
        self.assertTrue(
            any(m["role"] == "user" and "Hello from Cortex Bridge" in m["text"] for m in state["messages"])
        )

    # 4. detecting streaming start
    async def test_04_detect_streaming_start(self):
        self.server.set_streaming(8, 0.15, "conv-1")
        self.server.queue_replies(["streaming reply body " * 10], "conv-1")
        await self._select()
        await self.transport.send_message("go")
        task = asyncio.create_task(self.transport.await_response())
        observed = False
        for _ in range(40):
            if self.transport.streaming_observed:
                observed = True
                break
            await asyncio.sleep(0.03)
        msg = await task
        self.assertTrue(observed, "streaming signals were never observed")
        self.assertIn("streaming reply body", msg["text"])

    # 5. detecting stable completion
    async def test_05_detect_stable_completion(self):
        self.server.queue_replies(["final answer 42"], "conv-1")
        await self._select()
        await self.transport.send_message("go")
        msg = await self.transport.await_response()
        self.assertEqual(msg["text"], "final answer 42")
        state = await self.driver.get_state()
        self.assertFalse(state["stop_button_present"])
        self.assertFalse(state["streaming"])

    # 6. extracting latest response (fenced block survives verbatim)
    async def test_06_extract_latest_response(self):
        decision = {
            "protocol": "cortex.v1",
            "missionId": str(uuid.uuid4()),
            "actionId": str(uuid.uuid4()),
            "iteration": 1,
            "state": "BLOCKED",
            "summary": "echo with \"quotes\" and __markdown__ traps",
            "action": None,
            "acceptanceCriteria": [],
            "requiresApproval": False,
            "terminal": True,
        }
        reply = "Decision:\n```cortex-decision\n" + json.dumps(decision, indent=2) + "\n```"
        self.server.queue_replies([reply], "conv-1")
        await self._select()
        await self.transport.send_message("go")
        msg = await self.transport.await_response()
        extracted = protocol.extract_decision_block(msg["protocol_text"])
        self.assertEqual(extracted, decision)

    # 7. ignoring older messages
    async def test_07_ignoring_older_messages(self):
        self.server.conversation("conv-1").add_message("assistant", "OLD ANSWER")
        self.server.queue_replies(["NEW ANSWER"], "conv-1")
        await self._select()
        await self.transport.send_message("next")
        msg = await self.transport.await_response()
        self.assertEqual(msg["text"], "NEW ANSWER")

    # 8. refusing a different conversation
    async def test_08_refusing_different_conversation(self):
        await self._select()
        # Simulate the user switching Chrome to another conversation.
        await self.driver.navigate(f"{self.server.base_url}/c/conv-b")
        with self.assertRaises(TransportError) as cm:
            await self.transport.send_message("must not be sent")
        self.assertEqual(cm.exception.code, CONVERSATION_MISMATCH)
        self.assertEqual(self.transport.pause_reason, CONVERSATION_MISMATCH)
        self.assertEqual(self._user_messages("conv-b"), [])

    # 9. avoiding duplicate extraction
    async def test_09_avoiding_duplicate_extraction(self):
        self.server.queue_replies(["only once"], "conv-1")
        await self._select()
        await self.transport.send_message("go")
        msg = await self.transport.await_response()
        self.assertEqual(msg["text"], "only once")
        with self.assertRaises(TransportError) as cm:
            await self.transport.await_response()
        self.assertEqual(cm.exception.code, DUPLICATE_EXTRACTION)

    # 10. handling DOM mutation
    async def test_10_handling_dom_mutation(self):
        full = "mutating content " * 20
        self.server.set_streaming(8, 0.1, "conv-1")
        self.server.queue_replies([full], "conv-1")
        await self._select()
        await self.transport.send_message("go")

        async def poll_states():
            seen = set()
            for _ in range(25):
                state = await self.driver.get_state()
                if state["messages"]:
                    seen.add(state["messages"][-1]["text"])
                await asyncio.sleep(0.04)
            return seen

        msg, seen = await asyncio.gather(
            asyncio.create_task(self.transport.await_response()),
            asyncio.create_task(poll_states()),
        )
        self.assertGreaterEqual(len(seen), 2, "no DOM mutation observed while streaming")
        self.assertEqual(msg["text"], full)

    # 11. response timeout → pause, no automatic resend
    async def test_11_response_timeout(self):
        transport = self._make_transport(self.driver, max_wait=0.5)
        await transport.select_conversation(self.conv_url)
        await transport.send_message("go")
        with self.assertRaises(TransportError) as cm:
            await transport.await_response()
        self.assertEqual(cm.exception.code, CHATGPT_RESPONSE_TIMEOUT)
        self.assertTrue(transport.paused)
        self.assertEqual(transport.pause_reason, CHATGPT_RESPONSE_TIMEOUT)
        self.assertEqual(len(self._user_messages()), 1)  # never resent

    # 12. login state detection
    async def test_12_login_state_detection(self):
        await self._select()
        self.server.set_mode("login", "conv-1")
        with self.assertRaises(BlockerDetected) as cm:
            await self.transport.verify_lock()
        self.assertEqual(cm.exception.kind, "login")
        self.assertTrue(self.transport.paused)

    # 13. CAPTCHA state detection
    async def test_13_captcha_state_detection(self):
        await self._select()
        self.server.set_mode("captcha", "conv-1")
        with self.assertRaises(BlockerDetected) as cm:
            await self.transport.send_message("blocked")
        self.assertEqual(cm.exception.kind, "captcha")
        self.assertEqual(self._user_messages(), [])

    # 14. rate-limit detection
    async def test_14_rate_limit_detection(self):
        await self._select()
        self.server.set_mode("rate_limit", "conv-1")
        with self.assertRaises(BlockerDetected) as cm:
            await self.transport.verify_lock()
        self.assertEqual(cm.exception.kind, "rate_limit")
        self.assertTrue(self.transport.paused)

    # 15. browser tab closure
    async def test_15_browser_tab_closure(self):
        await self._select()
        self.server.close_tab()
        with self.assertRaises(TransportError) as cm:
            await self.transport.send_message("anyone there?")
        self.assertEqual(cm.exception.code, TAB_CLOSED)
        self.assertTrue(self.transport.paused)

    # 16. browser restart → re-attach to the locked conversation
    async def test_16_browser_restart_reattach(self):
        lock = await self._select()
        # Simulate a browser restart: brand-new driver, adapter re-attaches.
        driver2 = LocalFixtureDriver(self.server.base_url)
        transport2 = self._make_transport(driver2)
        await transport2.attach(lock)
        self.assertEqual(transport2.lock.identity, "conv-1")
        self.server.queue_replies(["after restart"], "conv-1")
        await transport2.send_message("continue")
        msg = await transport2.await_response()
        self.assertEqual(msg["text"], "after restart")
        # A mismatched identity is refused — never falls back to focused tab.
        bad_lock = ConversationLock(self.conv_url, "conv-other", None, lock.selected_at)
        transport3 = self._make_transport(LocalFixtureDriver(self.server.base_url))
        with self.assertRaises(TransportError) as cm:
            await transport3.attach(bad_lock)
        self.assertEqual(cm.exception.code, CONVERSATION_MISMATCH)

    # 17. pause before sending
    async def test_17_pause_before_sending(self):
        self.server.queue_replies(["resumed reply"], "conv-1")
        await self._select()
        self.transport.pause("USER_PAUSE")
        with self.assertRaises(TransportError) as cm:
            await self.transport.send_message("refused while paused")
        self.assertEqual(cm.exception.code, TRANSPORT_PAUSED)
        self.assertEqual(self._user_messages(), [])
        self.transport.resume()
        await self.transport.send_message("allowed after resume")
        msg = await self.transport.await_response()
        self.assertEqual(msg["text"], "resumed reply")

    # 18. cancel during generation
    async def test_18_cancel_during_generation(self):
        full = "long generation " * 30
        self.server.set_streaming(10, 0.15, "conv-1")
        self.server.queue_replies([full], "conv-1")
        await self._select()
        await self.transport.send_message("go")
        task = asyncio.create_task(self.transport.await_response())
        for _ in range(50):
            if self.transport.streaming_observed:
                break
            await asyncio.sleep(0.03)
        self.assertTrue(self.transport.streaming_observed)
        await self.transport.cancel_generation()
        with self.assertRaises(TransportError) as cm:
            await task
        self.assertEqual(cm.exception.code, GENERATION_CANCELLED)
        state = await self.driver.get_state()
        partial = state["messages"][-1]["text"]
        self.assertLess(len(partial), len(full))  # partial text was never extracted

    # 19. no resend after uncertain delivery
    async def test_19_no_resend_after_uncertain_delivery(self):
        self.server.queue_replies(["eventual reply"], "conv-1")
        await self._select()
        self.server.fail_next(skip=2)  # 3rd state read (post-send confirmation) fails
        with self.assertRaises(TransportError) as cm:
            await self.transport.send_message("delivered exactly once")
        self.assertEqual(cm.exception.code, DELIVERY_UNCERTAIN)
        self.assertTrue(self.transport.delivery_uncertain)
        # Refusing to resend while uncertain:
        with self.assertRaises(TransportError) as cm2:
            await self.transport.send_message("delivered exactly once")
        self.assertEqual(cm2.exception.code, DELIVERY_UNCERTAIN)
        self.assertEqual(len(self._user_messages()), 1)  # exactly one copy
        # Human resolves after inspecting the page; the mission continues.
        await self.transport.resolve_delivery()
        msg = await self.transport.await_response()
        self.assertEqual(msg["text"], "eventual reply")

    # 20. manual fallback generation
    async def test_20_manual_fallback_generation(self):
        mission_id = str(uuid.uuid4())
        report = protocol.build_report(
            mission_id=mission_id,
            action_id=str(uuid.uuid4()),
            iteration=1,
            status="SUCCEEDED",
            summary="manual mode evidence",
            tool="read_file",
        )
        payload = self.transport.manual_fallback_payload(
            report, note="Transport unavailable — paste this manually."
        )
        self.assertIn("manual fallback", payload)
        self.assertIn("Transport unavailable", payload)
        self.assertIn("```cortex-report", payload)
        self.assertIn(mission_id, payload)


class _DeadlineDriver:
    requires_content_stability = True

    def __init__(self, *, spa_delay=0.0, state_delay=0.0, light_delay=0.0):
        self.spa_delay = spa_delay
        self.state_delay = state_delay
        self.light_delay = light_delay
        self.current = "conv-a"

    async def spa_navigate(self, url):
        await asyncio.sleep(self.spa_delay)
        self.current = url.rsplit("/c/", 1)[-1]
        return True

    async def navigate(self, url):
        self.current = url.rsplit("/c/", 1)[-1]

    def _state_payload(self):
        return {
            "url": f"https://chatgpt.com/c/{self.current}",
            "conversation_id": self.current,
            "title": f"Conversation {self.current}",
            "blocker": None,
            "messages": [{"id": f"m-{self.current}", "role": "assistant", "text": "ok"}],
            "streaming": False,
        }

    async def get_state(self):
        await asyncio.sleep(self.state_delay)
        return self._state_payload()

    async def get_light_state(self):
        await asyncio.sleep(self.light_delay)
        state = self._state_payload()
        return {
            "conversation_id": state["conversation_id"],
            "title": state["title"],
            "message_count": 1,
            "first_id": state["messages"][0]["id"],
        }


class SelectionDeadlineTest(unittest.IsolatedAsyncioTestCase):
    def _transport(self, driver, budget=0.08):
        return ChatGPTWebTransport(
            driver,
            selection_budget=budget,
            poll_interval=0.005,
            stability_interval=0.005,
        )

    async def _assert_bounded(self, driver):
        from transport.chatgpt_web.adapter import SELECTION_TIMEOUT

        started = time.monotonic()
        with self.assertRaises(TransportError) as raised:
            await self._transport(driver).select_conversation(
                "https://chatgpt.com/c/conv-a"
            )
        self.assertEqual(raised.exception.code, SELECTION_TIMEOUT)
        self.assertTrue(raised.exception.details["reload_required"])
        self.assertLess(time.monotonic() - started, 0.35)

    async def test_spa_navigate_shares_the_absolute_deadline(self):
        await self._assert_bounded(_DeadlineDriver(spa_delay=1.0))

    async def test_get_state_shares_the_absolute_deadline(self):
        await self._assert_bounded(_DeadlineDriver(state_delay=1.0))

    async def test_get_light_state_shares_the_absolute_deadline(self):
        await self._assert_bounded(_DeadlineDriver(light_delay=1.0))

    async def test_late_selection_a_cannot_replace_completed_selection_b(self):
        from transport.chatgpt_web.adapter import SELECTION_SUPERSEDED

        driver = _DeadlineDriver()
        driver.requires_content_stability = False
        transport = self._transport(driver, budget=1.0)

        async def gated_spa(url):
            if url.endswith("conv-a"):
                await asyncio.sleep(0.08)
            driver.current = url.rsplit("/c/", 1)[-1]
            return True

        driver.spa_navigate = gated_spa
        task_a = asyncio.create_task(
            transport.select_conversation("https://chatgpt.com/c/conv-a")
        )
        await asyncio.sleep(0.01)
        lock_b = await transport.select_conversation("https://chatgpt.com/c/conv-b")
        with self.assertRaises(TransportError) as raised:
            await task_a
        self.assertEqual(raised.exception.code, SELECTION_SUPERSEDED)
        self.assertEqual(lock_b.identity, "conv-b")
        self.assertEqual(transport.lock.identity, "conv-b")

    async def test_fixture_driver_skips_live_content_stability_wait(self):
        self.assertFalse(LocalFixtureDriver.requires_content_stability)
        server = FixtureServer().start()
        self.addCleanup(server.stop)
        transport = self._transport(LocalFixtureDriver(server.base_url), budget=1.0)
        started = time.monotonic()
        lock = await transport.select_conversation(f"{server.base_url}/c/fast-fixture")
        self.assertEqual(lock.identity, "fast-fixture")
        self.assertLess(time.monotonic() - started, 0.30)


class ConversationNormalizationTest(unittest.TestCase):
    def test_deduplicates_before_hard_limit_and_keeps_stable_order(self):
        from transport.chatgpt_web.adapter import normalize_conversations

        items = []
        for index in range(55):
            items.append({
                "identity": f"conv-{index}",
                "url": f"https://chatgpt.com/c/conv-{index}",
                "title": f"Conversation {index}",
                "message_count": index,
            })
            if index == 0:
                items.append(dict(items[-1], title="duplicate must lose"))
        normalized = normalize_conversations(items)
        self.assertEqual(len(normalized), 50)
        self.assertEqual(normalized[0]["title"], "Conversation 0")
        self.assertEqual(normalized[-1]["identity"], "conv-49")

    def test_unknown_metadata_is_not_fabricated(self):
        from transport.chatgpt_web.adapter import normalize_conversations

        [item] = normalize_conversations([{
            "identity": "conv-1",
            "url": "https://chatgpt.com/c/conv-1",
            "title": "One",
            "project": True,
            "message_count": "12",
        }])
        self.assertFalse(item["project"])
        self.assertIsNone(item["project_id"])
        self.assertIsNone(item["project_title"])
        self.assertIsNone(item["message_count"])


class FixtureConversationMetadataTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.server = FixtureServer().start()
        self.addCleanup(self.server.stop)
        self.transport = ChatGPTWebTransport(
            LocalFixtureDriver(self.server.base_url),
            stability_interval=0.15,
            poll_interval=0.03,
            max_wait=5.0,
        )

    async def test_fixture_metadata_updates_are_truthful(self):
        conversation = self.server.conversation("metadata")
        conversation.add_message("user", "first")
        self.server.set_metadata(
            "metadata",
            title="Titre réel",
            pinned=True,
            project_id="project-1",
            project_title="Projet réel",
            preview="first",
            updated_at="2026-07-29T10:00:00+00:00",
        )
        listed = await self.transport.list_conversations()
        item = next(entry for entry in listed if entry["identity"] == "metadata")
        self.assertEqual(item["title"], "Titre réel")
        self.assertTrue(item["pinned"])
        self.assertEqual(item["project_id"], "project-1")
        self.assertEqual(item["project_title"], "Projet réel")
        self.assertEqual(item["preview"], "first")
        self.assertEqual(item["message_count"], 1)

    async def test_fixture_deletion_disappears_from_fresh_list(self):
        self.server.conversation("deleted")
        before = await self.transport.list_conversations()
        self.assertIn("deleted", {item["identity"] for item in before})
        self.server.delete_conversation("deleted")
        after = await self.transport.list_conversations()
        self.assertNotIn("deleted", {item["identity"] for item in after})


if __name__ == "__main__":
    unittest.main()
