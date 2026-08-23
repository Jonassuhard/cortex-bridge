"""Rate-limit resilience — writer-slot retention.

When ChatGPT answers with a usage/rate limit, the transport pauses the run
but the run is NOT terminal. The two-write-conversation guard must therefore
keep the slot occupied: a third conversation stays refused (409 semantics),
the rate-limited conversation keeps its own slot, and finishing the run
frees the slot again.

Transport-level detection is covered by
tests/test_transport_fixture.py::test_14_rate_limit_detection; this file
pins the slot-retention contract the UI relies on while paused.
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


class RateLimitSlotRetentionTest(unittest.TestCase):
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

    def test_rate_limited_run_keeps_its_slot(self) -> None:
        """A paused (non-terminal) rate-limited run still owns its writer slot."""
        chat_api._runs["r1"] = _fake_run("r1", CONV_A, "PAUSED")
        chat_api._runs["r2"] = _fake_run("r2", CONV_B, "CHATGPT_STREAMING")

        ok, active = write_slots.write_slot_available(CONV_A)
        self.assertTrue(ok, "the rate-limited conversation must keep its own slot")
        self.assertEqual(active, {CONV_A, CONV_B})

    def test_third_conversation_still_refused_while_rate_limited(self) -> None:
        """Rate limiting must not free capacity silently: a third write is refused."""
        chat_api._runs["r1"] = _fake_run("r1", CONV_A, "PAUSED")
        chat_api._runs["r2"] = _fake_run("r2", CONV_B, "WAITING_FOR_CHATGPT")

        ok, active = write_slots.write_slot_available(CONV_C)
        self.assertFalse(ok)
        self.assertEqual(active, {CONV_A, CONV_B})

    def test_finishing_a_rate_limited_run_frees_the_slot(self) -> None:
        """Once the paused run reaches a terminal state, capacity returns."""
        run = _fake_run("r1", CONV_A, "PAUSED")
        chat_api._runs["r1"] = run
        chat_api._runs["r2"] = _fake_run("r2", CONV_B, "CHATGPT_STREAMING")

        for terminal in ("COMPLETED", "FAILED", "CANCELLED"):
            run.state = "PAUSED"
            ok, _ = write_slots.write_slot_available(CONV_C)
            self.assertFalse(ok, "precondition: paused run holds the slot")
            run.state = terminal
            ok, active = write_slots.write_slot_available(CONV_C)
            self.assertTrue(ok, f"terminal state {terminal} must free the slot")
            self.assertEqual(active, {CONV_B})
