"""P2b — two-write-conversation guard (write_slots).

Pure-logic tests over console/write_slots.py: no network, no browser, no DB.
The guard must refuse a THIRD distinct write conversation while allowing
re-sends into an already-active one, and free slots when runs terminate.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "console"))

import chat as chat_api  # noqa: E402
import missions as missions_api  # noqa: E402
import write_slots  # noqa: E402
from conversation_sessions import ConversationSessionRegistry  # noqa: E402

CONV_A = "https://chatgpt.com/c/aaa-111"
CONV_B = "https://chatgpt.com/c/bbb-222"
CONV_C = "https://chatgpt.com/c/ccc-333"


def _fake_run(run_id: str, url: str, state: str) -> chat_api.ChatRunRuntime:
    run = chat_api.ChatRunRuntime(id=run_id, conversation_url=url, text="x", new_conversation=False)
    run.state = state
    return run


class WriteSlotsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_runs = dict(chat_api._runs)
        self._saved_urls = dict(missions_api._mission_write_urls)
        self._saved_registry = write_slots._registry
        write_slots._registry = ConversationSessionRegistry(capacity=2)
        chat_api._runs.clear()
        missions_api._mission_write_urls.clear()

    def tearDown(self) -> None:
        chat_api._runs.clear()
        chat_api._runs.update(self._saved_runs)
        missions_api._mission_write_urls.clear()
        missions_api._mission_write_urls.update(self._saved_urls)
        write_slots._registry = self._saved_registry

    def test_no_active_run_means_free_slot(self) -> None:
        ok, active = write_slots.write_slot_available(CONV_A)
        self.assertTrue(ok)
        self.assertEqual(active, set())

    def test_two_active_conversations_refuse_a_third(self) -> None:
        chat_api._runs["r1"] = _fake_run("r1", CONV_A, "WAITING_FOR_CHATGPT")
        chat_api._runs["r2"] = _fake_run("r2", CONV_B, "CHATGPT_STREAMING")
        ok, active = write_slots.write_slot_available(CONV_C)
        self.assertFalse(ok)
        self.assertEqual(active, {CONV_A, CONV_B})

    def test_resend_into_an_active_conversation_is_allowed(self) -> None:
        chat_api._runs["r1"] = _fake_run("r1", CONV_A, "WAITING_FOR_CHATGPT")
        chat_api._runs["r2"] = _fake_run("r2", CONV_B, "CHATGPT_STREAMING")
        ok, _ = write_slots.write_slot_available(CONV_A)
        self.assertTrue(ok)

    def test_terminal_runs_free_their_slot(self) -> None:
        chat_api._runs["r1"] = _fake_run("r1", CONV_A, "COMPLETED")
        chat_api._runs["r2"] = _fake_run("r2", CONV_B, "FAILED")
        ok, active = write_slots.write_slot_available(CONV_C)
        self.assertTrue(ok)
        self.assertEqual(active, set())

    def test_mission_conversations_count_toward_the_limit(self) -> None:
        chat_api._runs["r1"] = _fake_run("r1", CONV_A, "WAITING_FOR_CHATGPT")
        missions_api._mission_write_urls["m1"] = CONV_B
        original_rows = missions_api.get_store

        class _Store:
            def rows(self, table: str, order_by: str = "") -> list[dict]:
                return [{"id": "m1", "state": "WAITING_FOR_CHATGPT"}]

        missions_api.get_store = lambda: _Store()  # type: ignore[assignment]
        try:
            ok, active = write_slots.write_slot_available(CONV_C)
            self.assertFalse(ok)
            self.assertEqual(active, {CONV_A, CONV_B})
        finally:
            missions_api.get_store = original_rows  # type: ignore[assignment]

    def test_refusal_message_is_french_and_mentions_draft(self) -> None:
        self.assertIn("deux conversations", write_slots.REFUSAL_MESSAGE)
        self.assertIn("brouillon est conservé", write_slots.REFUSAL_MESSAGE)

    def test_durable_registry_wrappers_are_available(self) -> None:
        missing = [
            name
            for name in (
                "acquire_writer",
                "rekey",
                "release_writer",
                "restore_writer",
                "new_conversation_key",
            )
            if not hasattr(write_slots, name)
        ]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
