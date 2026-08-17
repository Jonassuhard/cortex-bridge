"""Required unit tests (mission spec §20) against protocol / state / store.

Runs with stdlib unittest:
    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestration import protocol  # noqa: E402
from orchestration.protocol import DecisionError  # noqa: E402
from orchestration.state import (  # noqa: E402
    BudgetExceeded,
    Budgets,
    DuplicateReport,
    DuplicateResponse,
    StateMachine,
)
from orchestration.store import InvalidTransition, Store  # noqa: E402
from executor.tools import ToolDenied, ToolExecutor  # noqa: E402

MISSION_ID = str(uuid.uuid4())


def make_decision(
    *,
    mission_id: str = MISSION_ID,
    action_id: str | None = None,
    iteration: int = 1,
    state: str = "EXECUTE",
    tool: str | None = "read_file",
    arguments: dict | None = None,
    criteria: list[str] | None = None,
    requires_approval: bool = False,
    terminal: bool = False,
) -> dict:
    action = None
    if tool is not None:
        action = {"tool": tool, "arguments": arguments if arguments is not None else {"path": "x.txt"}}
    if criteria is None:
        criteria = ["The requested information is returned."]
    return {
        "protocol": "cortex.v1",
        "missionId": mission_id,
        "actionId": action_id or str(uuid.uuid4()),
        "iteration": iteration,
        "state": state,
        "summary": "test decision",
        "action": action,
        "acceptanceCriteria": criteria,
        "requiresApproval": requires_approval,
        "terminal": terminal,
    }


class ProtocolTestCase(unittest.TestCase):
    """§20 tests 1-12: strict cortex.v1 decision validation + extraction."""

    # 1. valid cortex.v1 decision
    def test_01_valid_decision(self):
        d = make_decision()
        out = protocol.validate_decision(
            d, expected_mission_id=MISSION_ID, expected_iteration=1
        )
        self.assertEqual(out["state"], "EXECUTE")
        self.assertEqual(out["action"]["tool"], "read_file")

    # 2. invalid protocol
    def test_02_invalid_protocol(self):
        d = make_decision()
        d["protocol"] = "cortex.v2"
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(d, expected_mission_id=MISSION_ID, expected_iteration=1)
        self.assertEqual(cm.exception.code, "INVALID_PROTOCOL")

    # 3. wrong mission ID
    def test_03_wrong_mission_id(self):
        d = make_decision()
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(
                d, expected_mission_id=str(uuid.uuid4()), expected_iteration=1
            )
        self.assertEqual(cm.exception.code, "WRONG_MISSION_ID")

    # 4. repeated action ID
    def test_04_repeated_action_id(self):
        action_id = str(uuid.uuid4())
        d = make_decision(action_id=action_id)
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(
                d,
                expected_mission_id=MISSION_ID,
                expected_iteration=1,
                seen_action_ids=[action_id],
            )
        self.assertEqual(cm.exception.code, "REPEATED_ACTION_ID")

    # 5. incorrect iteration
    def test_05_incorrect_iteration(self):
        d = make_decision(iteration=7)
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(d, expected_mission_id=MISSION_ID, expected_iteration=1)
        self.assertEqual(cm.exception.code, "WRONG_ITERATION")

    # 6. unknown state
    def test_06_unknown_state(self):
        d = make_decision(state="YOLO")
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(d, expected_mission_id=MISSION_ID, expected_iteration=1)
        self.assertEqual(cm.exception.code, "UNKNOWN_STATE")

    # 7. unknown tool
    def test_07_unknown_tool(self):
        d = make_decision(tool="delete_everything")
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(d, expected_mission_id=MISSION_ID, expected_iteration=1)
        self.assertEqual(cm.exception.code, "UNKNOWN_TOOL")

    # 8. unknown field
    def test_08_unknown_field(self):
        d = make_decision()
        d["extra"] = True
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(d, expected_mission_id=MISSION_ID, expected_iteration=1)
        self.assertEqual(cm.exception.code, "UNKNOWN_FIELD")

    # 9. malformed arguments
    def test_09_malformed_arguments(self):
        d = make_decision(arguments={"path": 123})
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(d, expected_mission_id=MISSION_ID, expected_iteration=1)
        self.assertEqual(cm.exception.code, "MALFORMED_ARGUMENTS")
        d2 = make_decision(arguments={})  # read_file requires path
        with self.assertRaises(DecisionError) as cm2:
            protocol.validate_decision(d2, expected_mission_id=MISSION_ID, expected_iteration=1)
        self.assertEqual(cm2.exception.code, "MALFORMED_ARGUMENTS")

    # 10. missing acceptance criteria
    def test_10_missing_acceptance_criteria(self):
        d = make_decision()
        del d["acceptanceCriteria"]
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(d, expected_mission_id=MISSION_ID, expected_iteration=1)
        self.assertEqual(cm.exception.code, "MISSING_ACCEPTANCE_CRITERIA")
        d2 = make_decision(criteria=[])  # EXECUTE with empty criteria
        with self.assertRaises(DecisionError) as cm2:
            protocol.validate_decision(d2, expected_mission_id=MISSION_ID, expected_iteration=1)
        self.assertEqual(cm2.exception.code, "MISSING_ACCEPTANCE_CRITERIA")

    # 11. absolute path rejected
    def test_11_absolute_path_rejected(self):
        d = make_decision(tool="write_file", arguments={"path": "/etc/passwd", "content": "x"})
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(d, expected_mission_id=MISSION_ID, expected_iteration=1)
        self.assertEqual(cm.exception.code, "ABSOLUTE_PATH")

    # 12. ../ traversal rejected
    def test_12_parent_traversal_rejected(self):
        d = make_decision(arguments={"path": "../outside.txt"})
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(d, expected_mission_id=MISSION_ID, expected_iteration=1)
        self.assertEqual(cm.exception.code, "PATH_TRAVERSAL")

    def test_run_tests_requires_structured_argv(self):
        malformed = make_decision(tool="run_tests", arguments={"command": "python3 -m unittest"})
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(
                malformed, expected_mission_id=MISSION_ID, expected_iteration=1
            )
        self.assertEqual(cm.exception.code, "MALFORMED_ARGUMENTS")
        valid = make_decision(tool="run_tests", arguments={"argv": ["python3", "-m", "unittest"]})
        protocol.validate_decision(valid, expected_mission_id=MISSION_ID, expected_iteration=1)

    # extraction helper (§9): exactly one fenced block, other JSON ignored
    def test_extract_decision_block(self):
        decision = make_decision()
        message = (
            "Here is some prose with decoy JSON: {\"foo\": 1}\n"
            "```json\n{\"decoy\": true}\n```\n"
            "```cortex-decision\n" + json.dumps(decision) + "\n```\n"
            "trailing text"
        )
        extracted = protocol.extract_decision_block(message)
        self.assertEqual(extracted["actionId"], decision["actionId"])

    def test_extract_rejects_zero_and_multiple_blocks(self):
        with self.assertRaises(DecisionError) as cm:
            protocol.extract_decision_block("no block here, only {\"json\": true}")
        self.assertEqual(cm.exception.code, "NO_DECISION_BLOCK")
        block = "```cortex-decision\n{}\n```"
        with self.assertRaises(DecisionError) as cm2:
            protocol.extract_decision_block(block + "\n" + block)
        self.assertEqual(cm2.exception.code, "MULTIPLE_DECISION_BLOCKS")

    # Live ChatGPT DOM extraction drops code fences: accept the whole-message
    # bare form, keep rejecting embedded or ambiguous blocks.
    def test_extract_accepts_dom_stripped_bare_block(self):
        decision = make_decision()
        message = "cortex-decision\n" + json.dumps(decision, indent=2)
        extracted = protocol.extract_decision_block(message)
        self.assertEqual(extracted["actionId"], decision["actionId"])

    def test_extract_accepts_bare_block_with_trailing_fence_remnant(self):
        decision = make_decision()
        message = "cortex-decision\n" + json.dumps(decision) + "\n```"
        extracted = protocol.extract_decision_block(message)
        self.assertEqual(extracted["actionId"], decision["actionId"])

    def test_extract_rejects_bare_block_with_surrounding_prose(self):
        decision = make_decision()
        bare = "cortex-decision\n" + json.dumps(decision)
        with self.assertRaises(DecisionError) as cm:
            protocol.extract_decision_block("Let me explain.\n" + bare)
        self.assertEqual(cm.exception.code, "NO_DECISION_BLOCK")
        with self.assertRaises(DecisionError) as cm2:
            protocol.extract_decision_block(bare + "\n" + bare)
        self.assertEqual(cm2.exception.code, "NO_DECISION_BLOCK")


    # terminal COMPLETE without validation instructions (§10)
    def test_complete_without_validation_instructions(self):
        d = make_decision(state="COMPLETE", tool=None, criteria=[], terminal=True)
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(d, expected_mission_id=MISSION_ID, expected_iteration=1)
        self.assertEqual(cm.exception.code, "COMPLETE_WITHOUT_VALIDATION")
        ok = make_decision(state="COMPLETE", tool=None, criteria=["scan.py exists"], terminal=True)
        protocol.validate_decision(ok, expected_mission_id=MISSION_ID, expected_iteration=1)


class SymlinkEscapeTestCase(unittest.TestCase):
    """§20 test 13: symlink escape rejected (runtime complement to §10)."""

    def test_13_symlink_escape_rejected(self):
        import asyncio

        with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as outside:
            secret = Path(outside) / "secret.txt"
            secret.write_text("TOP SECRET", encoding="utf-8")
            link = Path(ws) / "link.txt"
            try:
                link.symlink_to(secret)
            except OSError as exc:  # pragma: no cover - platform without symlinks
                self.skipTest(f"symlinks unavailable: {exc}")
            executor = ToolExecutor(ws)
            with self.assertRaises(ToolDenied) as cm:
                asyncio.run(executor.read_file("link.txt"))
            self.assertEqual(cm.exception.code, "SYMLINK_ESCAPE")


class StateStoreTestCase(unittest.TestCase):
    """§20 tests 14-20: duplicates, loop protection, budgets, restart."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "cortex.db"
        self.store = Store(self.db_path)
        self.addCleanup(self.store.close)
        self.mission_id = str(uuid.uuid4())
        self.store.create_mission(self.mission_id, "test mission", self.tmp.name)
        self.sm = StateMachine(self.store, self.mission_id)
        # Drive the mission into the canonical waiting state.
        self.sm.transition("INITIALIZING_MISSION")
        self.sm.transition("SENDING_OBJECTIVE")
        self.sm.transition("WAITING_FOR_CHATGPT")

    def _decision(self, *, iteration=1, tool="read_file", arguments=None):
        return make_decision(
            mission_id=self.mission_id,
            iteration=iteration,
            tool=tool,
            arguments=arguments if arguments is not None else {"path": "x.txt"},
        )

    # 14. duplicate response rejected (§14 fingerprints)
    def test_14_duplicate_response_rejected(self):
        kwargs = dict(
            conversation_identity="conv-1",
            message_identity="msg-1",
            content="  normalized\r\n  content  ",
        )
        self.sm.register_response(**kwargs)
        with self.assertRaises(DuplicateResponse):
            self.sm.register_response(**kwargs)

    # 15. duplicate report send rejected (§14 idempotency keys)
    def test_15_duplicate_report_send_rejected(self):
        report = protocol.build_report(
            mission_id=self.mission_id,
            action_id=str(uuid.uuid4()),
            iteration=1,
            status="SUCCEEDED",
            summary="done",
            tool="read_file",
        )
        self.sm.send_report_once(report)
        with self.assertRaises(DuplicateReport):
            self.sm.send_report_once(report)

    # 16. repeated action loop detected (3 identical failing decisions)
    def test_16_repetition_loop_detected(self):
        for i in range(2):
            d = self._decision()
            self.sm.process_decision(d)
            self.sm.note_decision_result(d, success=False)
        with self.assertRaises(BudgetExceeded) as cm:
            self.sm.process_decision(self._decision())
        self.assertEqual(cm.exception.reason, "REPETITION_LOOP")
        self.assertEqual(self.sm.state, "PAUSED")
        self.assertEqual(self.sm.pause_reason, "REPETITION_LOOP")

    # 17. iteration limit enforced (§14: 25 default)
    def test_17_iteration_limit_enforced(self):
        sm = StateMachine(self.store, self.mission_id, budgets=Budgets(max_iterations=2))
        sm.advance_iteration()
        sm.advance_iteration()
        with self.assertRaises(BudgetExceeded) as cm:
            sm.advance_iteration()
        self.assertEqual(cm.exception.reason, "ITERATION_BUDGET_EXCEEDED")
        self.assertEqual(sm.state, "FAILED")

    # 18. mission timeout enforced (§14: 60 min default)
    def test_18_mission_timeout_enforced(self):
        t0 = self.store.get_mission(self.mission_id)["started_at"]
        clock = lambda: t0 + 3700  # noqa: E731 - 61+ minutes later
        sm = StateMachine(self.store, self.mission_id, clock=clock)
        with self.assertRaises(BudgetExceeded) as cm:
            sm.check_duration_budget()
        self.assertEqual(cm.exception.reason, "MISSION_TIMEOUT")
        self.assertEqual(sm.state, "FAILED")
        self.assertFalse(sm.can_continue())

    # 19. cancellation stops continuation
    def test_19_cancellation_stops_continuation(self):
        self.sm.cancel()
        self.assertEqual(self.sm.state, "CANCELLED")
        self.assertFalse(self.sm.can_continue())
        with self.assertRaises(InvalidTransition):
            self.sm.transition("WAITING_FOR_CHATGPT")
        with self.assertRaises(InvalidTransition):
            self.sm.resume("WAITING_FOR_CHATGPT")

    # 20. server restart sets mission to paused (§18)
    def test_20_restart_sets_paused(self):
        self.store.close()
        store2 = Store(self.db_path)
        self.addCleanup(store2.close)
        mission = store2.get_mission(self.mission_id)
        self.assertEqual(mission["state"], "PAUSED_RECOVERY_REQUIRED")
        self.assertEqual(mission["pause_reason"], "SERVER_RESTART")
        # Never auto-resumed — but an explicit user resume is possible.
        sm2 = StateMachine(store2, self.mission_id)
        self.assertFalse(sm2.can_continue())
        sm2.resume("WAITING_FOR_CHATGPT")
        self.assertEqual(sm2.state, "WAITING_FOR_CHATGPT")


class StoreSchemaTestCase(unittest.TestCase):
    """§18: all 11 required tables exist; report builder (§11) shape."""

    def test_eleven_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "cortex.db")
            self.addCleanup(store.close)
            expected = {
                "missions",
                "conversation_bindings",
                "iterations",
                "chatgpt_messages",
                "orchestrator_decisions",
                "policy_decisions",
                "approvals",
                "tool_executions",
                "validation_results",
                "transport_events",
                "artifacts",
            }
            self.assertEqual(set(store.table_names()), expected)

    def test_report_builder_and_render(self):
        report = protocol.build_report(
            mission_id=MISSION_ID,
            action_id=str(uuid.uuid4()),
            iteration=1,
            status="SUCCEEDED",
            summary="package.json was read successfully.",
            tool="read_file",
            validation={"passed": True, "checks": [{"name": "file_read", "passed": True, "evidence": "captured"}]},
        )
        self.assertEqual(report["protocol"], "cortex.v1")
        self.assertEqual(report["toolResult"]["exitCode"], 0)
        message = protocol.render_report_message(report)
        self.assertTrue(message.startswith("```cortex-report\n"))
        self.assertTrue(message.endswith("\n```"))
        parsed = json.loads(message[len("```cortex-report\n"):-len("\n```")])
        self.assertEqual(parsed, report)
        with self.assertRaises(ValueError):
            protocol.build_report(
                mission_id=MISSION_ID,
                action_id=str(uuid.uuid4()),
                iteration=1,
                status="MAYBE",
                summary="x",
                tool=None,
            )


if __name__ == "__main__":
    unittest.main()
