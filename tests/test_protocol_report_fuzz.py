"""Protocol report + decision identity fuzzing (cortex.v1 §10/§11).

Covers report construction/rendering validation and the canonical
decision_action_key used for loop detection.
"""

from __future__ import annotations

import json
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestration import protocol  # noqa: E402
from orchestration.protocol import DecisionError  # noqa: E402

MISSION_ID = str(uuid.uuid4())


def make_decision(**overrides) -> dict:
    """Build a valid EXECUTE decision. Pass tool/arguments for the action."""
    tool = overrides.pop("tool", "read_file")
    arguments = overrides.pop("arguments", {"path": "x.txt"})
    if "action_id" in overrides:
        overrides["actionId"] = overrides.pop("action_id")
    action = None
    if tool is not None:
        action = {"tool": tool, "arguments": arguments}
    data = {
        "protocol": "cortex.v1",
        "missionId": MISSION_ID,
        "actionId": str(uuid.uuid4()),
        "iteration": 1,
        "state": "EXECUTE",
        "summary": "test",
        "action": action,
        "acceptanceCriteria": ["returned"],
        "requiresApproval": False,
        "terminal": False,
    }
    data.update(overrides)
    return data


class DecisionActionKeyTest(unittest.TestCase):
    """Canonical identity for loop detection (§14)."""

    def test_same_action_different_arg_order_is_same_key(self):
        a = {"state": "EXECUTE", "action": {
            "tool": "write_file",
            "arguments": {"path": "x.txt", "content": "y"},
        }}
        b = {"state": "EXECUTE", "action": {
            "tool": "write_file",
            "arguments": {"content": "y", "path": "x.txt"},
        }}
        self.assertEqual(
            protocol.decision_action_key(a),
            protocol.decision_action_key(b),
        )

    def test_different_tool_is_different_key(self):
        a = {"state": "EXECUTE", "action": {"tool": "read_file", "arguments": {"path": "x"}}}
        b = {"state": "EXECUTE", "action": {"tool": "write_file", "arguments": {"path": "x", "content": "y"}}}
        self.assertNotEqual(
            protocol.decision_action_key(a),
            protocol.decision_action_key(b),
        )

    def test_different_state_is_different_key(self):
        a = {"state": "EXECUTE", "action": {"tool": "read_file", "arguments": {"path": "x"}}}
        b = {"state": "COMPLETE", "action": {"tool": "read_file", "arguments": {"path": "x"}}}
        self.assertNotEqual(
            protocol.decision_action_key(a),
            protocol.decision_action_key(b),
        )

    def test_missing_action_is_handled(self):
        """Decision with no action (BLOCKED/COMPLETE) yields a stable key."""
        key = protocol.decision_action_key({"state": "COMPLETE"})
        self.assertIn("COMPLETE", key)


class BuildReportTest(unittest.TestCase):
    """§11 report construction validation."""

    def test_invalid_status_raises(self):
        with self.assertRaises(ValueError):
            protocol.build_report(
                mission_id=MISSION_ID,
                action_id=str(uuid.uuid4()),
                iteration=1,
                status="NOPE",
                summary="x",
                tool=None,
            )

    def test_all_valid_statuses_accepted(self):
        for status in ("SUCCEEDED", "FAILED", "BLOCKED", "DENIED", "CANCELLED"):
            with self.subTest(status=status):
                report = protocol.build_report(
                    mission_id=MISSION_ID,
                    action_id=str(uuid.uuid4()),
                    iteration=1,
                    status=status,
                    summary="ok",
                    tool="read_file",
                )
                self.assertEqual(report["status"], status)
                self.assertEqual(report["protocol"], "cortex.v1")

    def test_default_validation_derives_from_status(self):
        ok = protocol.build_report(
            mission_id=MISSION_ID,
            action_id=str(uuid.uuid4()),
            iteration=1,
            status="SUCCEEDED",
            summary="x",
            tool=None,
        )
        self.assertTrue(ok["validation"]["passed"])
        failed = protocol.build_report(
            mission_id=MISSION_ID,
            action_id=str(uuid.uuid4()),
            iteration=1,
            status="FAILED",
            summary="x",
            tool=None,
        )
        self.assertFalse(failed["validation"]["passed"])

    def test_tool_result_is_merged_into_tool_result(self):
        report = protocol.build_report(
            mission_id=MISSION_ID,
            action_id=str(uuid.uuid4()),
            iteration=1,
            status="SUCCEEDED",
            summary="x",
            tool="run_process",
            tool_result={"exitCode": 0, "stdout": "done\n", "stderr": ""},
        )
        self.assertEqual(report["toolResult"]["exitCode"], 0)
        self.assertIn("done", report["toolResult"]["stdout"])


class RenderReportMessageTest(unittest.TestCase):
    """§11 render: exactly one fence, rejects unknown fields."""

    def test_valid_report_renders_one_fence(self):
        report = protocol.build_report(
            mission_id=MISSION_ID,
            action_id=str(uuid.uuid4()),
            iteration=1,
            status="SUCCEEDED",
            summary="done",
            tool="read_file",
        )
        message = protocol.render_report_message(report)
        self.assertTrue(message.startswith("```cortex-report\n"))
        self.assertTrue(message.endswith("\n```"))
        # exactly one opening fence
        self.assertEqual(message.count("```cortex-report"), 1)

    def test_unknown_field_is_rejected(self):
        report = protocol.build_report(
            mission_id=MISSION_ID,
            action_id=str(uuid.uuid4()),
            iteration=1,
            status="SUCCEEDED",
            summary="done",
            tool="read_file",
        )
        report["leaked_secret"] = "hunter2"
        with self.assertRaises(ValueError):
            protocol.render_report_message(report)

    def test_rendered_body_round_trips_to_json(self):
        report = protocol.build_report(
            mission_id=MISSION_ID,
            action_id=str(uuid.uuid4()),
            iteration=3,
            status="SUCCEEDED",
            summary="done",
            tool="write_file",
            files_changed=["a.txt"],
        )
        message = protocol.render_report_message(report)
        body = message[len("```cortex-report\n"):-len("\n```")]
        parsed = json.loads(body)
        self.assertEqual(parsed["iteration"], 3)
        self.assertEqual(parsed["filesChanged"], ["a.txt"])


class ValidateDecisionEdgeCaseTest(unittest.TestCase):
    """Extra validate_decision edges not covered by the §20 suite."""

    def test_bool_iteration_is_rejected_as_not_int(self):
        d = make_decision(iteration=True)
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(
                d, expected_mission_id=MISSION_ID, expected_iteration=1
            )
        self.assertEqual(cm.exception.code, "WRONG_ITERATION")

    def test_float_iteration_is_rejected(self):
        d = make_decision(iteration=1.0)
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(
                d, expected_mission_id=MISSION_ID, expected_iteration=1
            )
        self.assertEqual(cm.exception.code, "WRONG_ITERATION")

    def test_timeout_seconds_out_of_bounds_is_rejected(self):
        for bad in (0, -1, 601, 10000):
            with self.subTest(bad=bad):
                d = make_decision(
                    tool="run_process",
                    arguments={
                        "argv": ["python3", "x.py"],
                        "timeoutSeconds": bad,
                    },
                )
                with self.assertRaises(DecisionError) as cm:
                    protocol.validate_decision(
                        d, expected_mission_id=MISSION_ID, expected_iteration=1
                    )
                self.assertEqual(cm.exception.code, "MALFORMED_ARGUMENTS")

    def test_request_context_with_write_tool_is_rejected(self):
        d = make_decision(
            state="REQUEST_CONTEXT",
            tool="write_file",
            arguments={"path": "x.txt", "content": "y"},
        )
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(
                d, expected_mission_id=MISSION_ID, expected_iteration=1
            )
        self.assertEqual(cm.exception.code, "UNKNOWN_TOOL")

    def test_request_context_with_read_tool_is_allowed(self):
        d = make_decision(
            state="REQUEST_CONTEXT",
            tool="read_file",
            arguments={"path": "x.txt"},
        )
        protocol.validate_decision(
            d, expected_mission_id=MISSION_ID, expected_iteration=1
        )

    def test_apply_patch_replacement_must_have_exactly_old_new(self):
        d = make_decision(
            tool="apply_patch",
            arguments={
                "path": "x.txt",
                "replacements": [{"old": "a", "new": "b", "extra": "no"}],
            },
        )
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(
                d, expected_mission_id=MISSION_ID, expected_iteration=1
            )
        self.assertEqual(cm.exception.code, "MALFORMED_ARGUMENTS")

    def test_apply_patch_empty_old_is_rejected(self):
        d = make_decision(
            tool="apply_patch",
            arguments={"path": "x.txt", "replacements": [{"old": "", "new": "b"}]},
        )
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(
                d, expected_mission_id=MISSION_ID, expected_iteration=1
            )
        self.assertEqual(cm.exception.code, "MALFORMED_ARGUMENTS")

    def test_action_with_extra_key_is_rejected(self):
        d = make_decision()
        d["action"]["extra"] = "no"
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(
                d, expected_mission_id=MISSION_ID, expected_iteration=1
            )
        self.assertEqual(cm.exception.code, "UNKNOWN_FIELD")

    def test_action_id_must_be_uuid(self):
        d = make_decision(action_id="not-a-uuid")
        with self.assertRaises(DecisionError) as cm:
            protocol.validate_decision(
                d, expected_mission_id=MISSION_ID, expected_iteration=1
            )
        self.assertEqual(cm.exception.code, "MALFORMED_ARGUMENTS")


if __name__ == "__main__":
    unittest.main()