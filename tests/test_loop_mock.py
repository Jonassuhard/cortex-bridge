"""Phase 3 — mock orchestration loop tests (mission spec §12/§14/§19).

End-to-end: MissionLoop + MockOrchestrator + real protocol validation, real
state machine, real policy engine, real tools, real SQLite. stdlib unittest:
    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from executor.tools import ToolExecutor  # noqa: E402
from executor.policy import PolicyEngine  # noqa: E402
from orchestration.loop import (  # noqa: E402
    DUPLICATE_RESPONSE_IGNORED,
    MissionLoop,
    MockOrchestrator,
    MockReply,
    default_trace_validator,
)
from orchestration.state import (  # noqa: E402
    Budgets,
    ITERATION_BUDGET_EXCEEDED,
    REPETITION_LOOP,
)
from orchestration.store import Store  # noqa: E402


def execute(tool, arguments, **extra):
    d = {
        "state": "EXECUTE",
        "action": {"tool": tool, "arguments": arguments},
        "acceptanceCriteria": ["action verified"],
    }
    d.update(extra)
    return d


def complete(criteria=None):
    return {
        "state": "COMPLETE",
        "action": None,
        "terminal": True,
        "acceptanceCriteria": criteria or ["mission satisfied"],
    }


def blocked(summary="cannot proceed"):
    return {
        "state": "BLOCKED",
        "action": None,
        "terminal": True,
        "acceptanceCriteria": [],
        "summary": summary,
    }


def reports_received(mock) -> list[dict]:
    out = []
    for message in mock.received:
        if message and message.startswith("```cortex-report"):
            body = message[len("```cortex-report\n"):].rsplit("\n```", 1)[0]
            out.append(json.loads(body))
    return out


class LoopTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = Path(self._tmp.name)
        self.store = Store(self.ws / "cortex.db")
        self.addCleanup(self.store.close)
        self.mission_id = str(uuid.uuid4())
        self.store.create_mission(self.mission_id, "test objective", str(self.ws))
        self.tools = ToolExecutor(self.ws)

    def make_loop(self, script, **kwargs):
        mock = MockOrchestrator(self.mission_id, script, on_message=kwargs.pop("on_message", None))
        kwargs.setdefault("approval_callback", lambda decision, policy: "once")
        loop = MissionLoop(
            store=self.store,
            mission_id=self.mission_id,
            orchestrator=mock,
            tools=self.tools,
            **kwargs,
        )
        return loop, mock

    async def test_process_exit_nonzero_is_failed(self):
        (self.ws / "fail.py").write_text(
            "import sys\nsys.exit(3)\n", encoding="utf-8"
        )
        loop, mock = self.make_loop(
            [
                execute("run_process", {"argv": ["python3", "fail.py"]}),
                blocked("stop after the failed command"),
            ], policy=PolicyEngine(self.ws, allow_processes=True)
        )

        await loop.run()

        report = reports_received(mock)[0]
        self.assertEqual(report["status"], "FAILED")
        self.assertFalse(report["validation"]["passed"])
        self.assertEqual(report["toolResult"]["exitCode"], 3)
        self.assertTrue(
            any(check["name"] == "process_exit_code" for check in report["validation"]["checks"])
        )

    async def test_process_timeout_is_failed(self):
        (self.ws / "slow.py").write_text("import time\ntime.sleep(2)\n", encoding="utf-8")
        loop, mock = self.make_loop(
            [
                execute(
                    "run_process",
                    {
                        "argv": ["python3", "slow.py"],
                        "timeoutSeconds": 1,
                    },
                ),
                blocked("stop after the timed out command"),
            ], policy=PolicyEngine(self.ws, allow_processes=True)
        )

        await loop.run()

        report = reports_received(mock)[0]
        self.assertEqual(report["status"], "FAILED")
        self.assertFalse(report["validation"]["passed"])
        self.assertTrue(
            any(check["name"] == "process_timeout" for check in report["validation"]["checks"])
        )

    async def test_truncated_process_output_is_failed(self):
        (self.ws / "large_output.py").write_text("print('x' * 20000)\n", encoding="utf-8")
        loop, mock = self.make_loop(
            [
                execute(
                    "run_process",
                    {"argv": ["python3", "large_output.py"]},
                ),
                blocked("stop after the truncated command"),
            ], policy=PolicyEngine(self.ws, allow_processes=True)
        )

        await loop.run()

        report = reports_received(mock)[0]
        self.assertEqual(report["status"], "FAILED")
        self.assertFalse(report["validation"]["passed"])
        self.assertTrue(
            any(
                check["name"] == "process_output_complete"
                and check["passed"] is False
                for check in report["validation"]["checks"]
            )
        )

    async def test_default_trace_rejects_empty_complete(self):
        loop, mock = self.make_loop([complete(), blocked("no execution evidence")])

        mission = await loop.run()

        self.assertEqual(mission["state"], "BLOCKED")
        validations = self.store.rows("validation_results", self.mission_id, order_by="rowid")
        self.assertEqual(validations[0]["passed"], 0)
        checks = json.loads(validations[0]["checks_json"])
        self.assertEqual(checks[-1]["validator"], "execution-trace-v1")

    async def test_default_trace_allows_completion_after_policy_denial_is_remediated(
        self,
    ):
        loop, mock = self.make_loop(
            [
                execute(
                    "run_process",
                    {"argv": ["python3", "-c", "print('denied')"]},
                ),
                execute(
                    "write_file",
                    {
                        "path": "verify.py",
                        "content": "print('validated')\n",
                    },
                ),
                execute(
                    "run_process",
                    {"argv": ["python3", "verify.py"]},
                ),
                complete(),
                blocked("completion should not need this fallback"),
            ],
            policy=PolicyEngine(self.ws, allow_processes=True),
        )

        mission = await loop.run()

        self.assertEqual(mission["state"], "COMPLETED")
        reports = reports_received(mock)
        self.assertEqual(reports[0]["status"], "DENIED")
        self.assertEqual(reports[1]["status"], "SUCCEEDED")
        self.assertEqual(reports[2]["status"], "SUCCEEDED")
        final_validations = self.store.rows(
            "validation_results", self.mission_id, order_by="rowid"
        )[-3:]
        self.assertTrue(all(row["passed"] == 1 for row in final_validations))

    async def test_final_validator_exception_fails_terminally(self):
        def exploding_validator(decision, tools):
            raise RuntimeError("validator crash")

        loop, _ = self.make_loop([complete()], final_validator=exploding_validator)

        mission = await loop.run()

        self.assertEqual(mission["state"], "FAILED")
        validations = self.store.rows("validation_results", self.mission_id, order_by="rowid")
        self.assertEqual(validations[0]["passed"], 0)

    async def test_malformed_final_validator_output_fails_terminally(self):
        def malformed_validator(decision, tools):
            return {"passed": True, "checks": "not a list"}

        loop, _ = self.make_loop([complete()], final_validator=malformed_validator)

        mission = await loop.run()

        self.assertEqual(mission["state"], "FAILED")
        validations = self.store.rows("validation_results", self.mission_id, order_by="rowid")
        self.assertEqual(validations[0]["passed"], 0)

    async def test_named_final_validator_records_identity_and_evidence(self):
        def evidence_validator(decision, tools):
            return {
                "passed": True,
                "checks": [
                    {
                        "name": "workspace_evidence",
                        "passed": True,
                        "evidence": "validated locally",
                    }
                ],
            }

        loop, _ = self.make_loop([complete()], final_validator=evidence_validator)

        mission = await loop.run()

        self.assertEqual(mission["state"], "COMPLETED")
        validations = self.store.rows("validation_results", self.mission_id, order_by="rowid")
        checks = json.loads(validations[0]["checks_json"])
        self.assertEqual(checks[0]["evidence"], "validated locally")
        self.assertEqual(checks[-1]["validator"], "evidence_validator")

    async def test_final_validator_empty_checks_fails_terminally(self):
        def empty_checks_validator(decision, tools):
            return {"passed": True, "checks": []}

        loop, _ = self.make_loop([complete()], final_validator=empty_checks_validator)

        mission = await loop.run()

        self.assertEqual(mission["state"], "FAILED")
        validations = self.store.rows("validation_results", self.mission_id, order_by="rowid")
        self.assertEqual(validations[0]["passed"], 0)

    async def test_final_validator_empty_evidence_fails_terminally(self):
        def empty_evidence_validator(decision, tools):
            return {
                "passed": True,
                "checks": [{"name": "proof", "passed": True, "evidence": ""}],
            }

        loop, _ = self.make_loop([complete()], final_validator=empty_evidence_validator)

        mission = await loop.run()

        self.assertEqual(mission["state"], "FAILED")
        validations = self.store.rows("validation_results", self.mission_id, order_by="rowid")
        self.assertEqual(validations[0]["passed"], 0)

    async def test_final_validator_failed_check_cannot_claim_success(self):
        def contradictory_validator(decision, tools):
            return {
                "passed": True,
                "checks": [{"name": "proof", "passed": False, "evidence": "missing"}],
            }

        loop, _ = self.make_loop([complete()], final_validator=contradictory_validator)

        mission = await loop.run()

        self.assertEqual(mission["state"], "FAILED")
        validations = self.store.rows("validation_results", self.mission_id, order_by="rowid")
        self.assertEqual(validations[0]["passed"], 0)

    async def test_default_trace_rejects_approval_denied_action(self):
        loop, _ = self.make_loop(
            [
                execute("write_file", {"path": "denied.txt", "content": "no"}),
                execute("list_directory", {"path": "."}),
                complete(),
                blocked("approval denial remains unresolved"),
            ],
            approval_callback=lambda decision, policy: None,
        )

        mission = await loop.run()

        self.assertEqual(mission["state"], "BLOCKED")
        validations = self.store.rows("validation_results", self.mission_id, order_by="rowid")
        self.assertEqual(validations[-1]["passed"], 0)

    async def test_default_trace_rejects_nonzero_process_before_complete(self):
        (self.ws / "fail.py").write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
        loop, _ = self.make_loop(
            [
                execute("run_process", {"argv": ["python3", "fail.py"]}),
                complete(),
                blocked("failed process remains unresolved"),
            ], policy=PolicyEngine(self.ws, allow_processes=True)
        )

        mission = await loop.run()

        self.assertEqual(mission["state"], "BLOCKED")
        validations = self.store.rows("validation_results", self.mission_id, order_by="rowid")
        self.assertEqual(validations[-1]["passed"], 0)

    async def test_default_trace_rejects_timed_out_process_before_complete(self):
        (self.ws / "slow.py").write_text("import time\ntime.sleep(2)\n", encoding="utf-8")
        loop, _ = self.make_loop(
            [
                execute(
                    "run_process",
                    {
                        "argv": ["python3", "slow.py"],
                        "timeoutSeconds": 1,
                    },
                ),
                complete(),
                blocked("timed out process remains unresolved"),
            ], policy=PolicyEngine(self.ws, allow_processes=True)
        )

        mission = await loop.run()

        self.assertEqual(mission["state"], "BLOCKED")
        validations = self.store.rows("validation_results", self.mission_id, order_by="rowid")
        self.assertEqual(validations[-1]["passed"], 0)

    def test_default_trace_rejects_missing_or_outside_changed_file(self):
        for changed_path in ("missing.txt", "../outside.txt"):
            trace_mission_id = str(uuid.uuid4())
            self.store.create_mission(trace_mission_id, "trace check", str(self.ws))
            action_id = str(uuid.uuid4())
            self.store.record_tool_execution(
                str(uuid.uuid4()),
                trace_mission_id,
                action_id,
                "write_file",
                {"path": changed_path},
                {"filesChanged": [changed_path]},
                0,
                0,
                0,
            )
            self.store.record_validation(
                str(uuid.uuid4()), trace_mission_id, action_id, True, []
            )

            validation = default_trace_validator({}, self.tools, self.store, trace_mission_id)

            self.assertFalse(validation["passed"])
            self.assertFalse(
                next(check["passed"] for check in validation["checks"] if check["name"] == "changed_files_present")
            )

    # 1. Multi-iteration repair mission end-to-end → COMPLETED, evidence persisted
    async def test_01_multi_iteration_repair_completes(self):
        (self.ws / "broken.py").write_text("print('BROKEN')\n", encoding="utf-8")
        script = [
            execute("read_file", {"path": "broken.py"}),
            execute(
                "apply_patch",
                {
                    "path": "broken.py",
                    "replacements": [{"old": "print('BROKEN')", "new": "print('CORTEX_REPAIR_OK')"}],
                },
            ),
            execute("run_process", {"argv": ["python3", "broken.py"]}),
            complete(["broken.py prints CORTEX_REPAIR_OK"]),
        ]

        def final_validator(decision, tools):
            ok = "CORTEX_REPAIR_OK" in (self.ws / "broken.py").read_text(encoding="utf-8")
            return {
                "passed": ok,
                "checks": [{"name": "script_fixed", "passed": ok, "evidence": "content check"}],
            }

        loop, mock = self.make_loop(
            script,
            final_validator=final_validator,
            policy=PolicyEngine(self.ws, allow_processes=True),
        )
        mission = await loop.run()

        self.assertEqual(mission["state"], "COMPLETED")
        # tool executions: read_file + apply_patch + run_process
        executions = self.store.rows("tool_executions", self.mission_id, order_by="rowid")
        self.assertEqual(len(executions), 3)
        self.assertEqual(
            [json.loads(e["arguments_json"]).get("path", e["tool"]) for e in executions],
            ["broken.py", "broken.py", "run_process"],
        )
        # run_process result captured exit code 0 and the repaired output
        run_result = json.loads(executions[2]["result_json"])
        self.assertEqual(run_result["exitCode"], 0)
        self.assertIn("CORTEX_REPAIR_OK", run_result["stdout"])
        # all 4 decisions recorded as valid
        decisions = self.store.rows("orchestrator_decisions", self.mission_id, order_by="rowid")
        self.assertEqual(len(decisions), 4)
        self.assertTrue(all(d["valid"] == 1 for d in decisions))
        # reports fed back to the orchestrator: 3 (COMPLETE sends none)
        reports = reports_received(mock)
        self.assertEqual(len(reports), 3)
        self.assertTrue(all(r["status"] == "SUCCEEDED" for r in reports))
        self.assertEqual(reports[2]["toolResult"]["exitCode"], 0)
        # policy + approvals: apply_patch and run_process required approval
        self.assertEqual(self.store.count("policy_decisions", self.mission_id), 3)
        approvals = self.store.rows("approvals", self.mission_id)
        self.assertEqual(len(approvals), 2)
        self.assertTrue(all(a["approved"] == 1 for a in approvals))
        # validation results: 3 action validations + 1 final validation
        self.assertEqual(self.store.count("validation_results", self.mission_id), 4)
        # patch backup persisted as an artifact; iterations recorded
        self.assertEqual(self.store.count("artifacts", self.mission_id), 1)
        self.assertEqual(self.store.count("iterations", self.mission_id), 3)
        # fingerprinted messages: all 4 assistant replies recorded once
        self.assertEqual(self.store.count("chatgpt_messages", self.mission_id), 4)
        self.assertEqual(self.store.count("transport_events", self.mission_id), 3)

    # 2. Final validation failure → failed-validation report back, continue in budget
    async def test_02_final_validation_failure_continues(self):
        calls = {"n": 0}

        def flaky_validator(decision, tools):
            calls["n"] += 1
            ok = calls["n"] >= 2
            return {
                "passed": ok,
                "checks": [
                    {
                        "name": "flaky",
                        "passed": ok,
                        "evidence": f"attempt {calls['n']}",
                    }
                ],
            }

        loop, mock = self.make_loop([complete(), complete()], final_validator=flaky_validator)
        mission = await loop.run()

        self.assertEqual(mission["state"], "COMPLETED")
        validations = self.store.rows("validation_results", self.mission_id, order_by="rowid")
        self.assertEqual(len(validations), 2)
        self.assertEqual(validations[0]["passed"], 0)
        self.assertEqual(validations[1]["passed"], 1)
        reports = reports_received(mock)
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["status"], "FAILED")
        self.assertIn("final validation failed", reports[0]["summary"])
        self.assertEqual(self.store.get_mission(self.mission_id)["iteration"], 1)

    # 3. BLOCKED decision → mission BLOCKED, no tool executed
    async def test_03_blocked_decision(self):
        loop, mock = self.make_loop([blocked()])
        mission = await loop.run()
        self.assertEqual(mission["state"], "BLOCKED")
        self.assertEqual(self.store.count("tool_executions", self.mission_id), 0)
        self.assertEqual(len(mock.received), 1)  # contract only; no report sent
        decisions = self.store.rows("orchestrator_decisions", self.mission_id, order_by="rowid")
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["valid"], 1)

    # 4. Pause then explicit resume → continues; cancel → CANCELLED, nothing further
    async def test_04_pause_resume_then_cancel(self):
        (self.ws / "x.txt").write_text("x", encoding="utf-8")
        (self.ws / "y.txt").write_text("y", encoding="utf-8")
        script = [
            execute("read_file", {"path": "x.txt"}),
            execute("read_file", {"path": "y.txt"}),
            complete(),
        ]
        mock = MockOrchestrator(self.mission_id, script)
        loop = MissionLoop(
            store=self.store,
            mission_id=self.mission_id,
            orchestrator=mock,
            tools=self.tools,
            approval_callback=lambda d, p: "once",
        )
        paused = {"done": False}

        def pause_hook(message, orch):
            if message and message.startswith("```cortex-report") and not paused["done"]:
                paused["done"] = True
                loop.sm.transition("PAUSED")

        mock.on_message = pause_hook
        mission = await loop.run()
        self.assertEqual(mission["state"], "PAUSED")
        self.assertEqual(self.store.count("tool_executions", self.mission_id), 1)
        self.assertEqual(len(mock.received), 2)  # contract + one report

        # Explicit resume — the stashed decision is then processed.
        loop.sm.resume("WAITING_FOR_CHATGPT")
        mission = await loop.run()
        self.assertEqual(mission["state"], "COMPLETED")
        self.assertEqual(self.store.count("tool_executions", self.mission_id), 2)

        # Cancellation variant on a fresh mission.
        store2 = Store(self.ws / "cortex2.db")
        self.addCleanup(store2.close)
        mission2 = str(uuid.uuid4())
        store2.create_mission(mission2, "cancel me", str(self.ws))
        mock2 = MockOrchestrator(mission2, script)
        loop2 = MissionLoop(
            store=store2,
            mission_id=mission2,
            orchestrator=mock2,
            tools=self.tools,
            approval_callback=lambda d, p: "once",
        )
        cancelled = {"done": False}

        def cancel_hook(message, orch):
            if message and message.startswith("```cortex-report") and not cancelled["done"]:
                cancelled["done"] = True
                loop2.sm.cancel()

        mock2.on_message = cancel_hook
        mission = await loop2.run()
        self.assertEqual(mission["state"], "CANCELLED")
        self.assertEqual(store2.count("tool_executions", mission2), 1)
        # A cancelled mission never continues.
        mission = await loop2.run()
        self.assertEqual(mission["state"], "CANCELLED")
        self.assertEqual(store2.count("tool_executions", mission2), 1)
        self.assertEqual(len(mock2.received), 2)

    # 5. Duplicate assistant response (same fingerprint) rejected, processed once
    async def test_05_duplicate_response_rejected(self):
        (self.ws / "x.txt").write_text("x", encoding="utf-8")
        script = [
            execute("read_file", {"path": "x.txt"}),
            MockOrchestrator.DUPLICATE_PREVIOUS,
            blocked(),
        ]
        loop, mock = self.make_loop(script)
        mission = await loop.run()

        self.assertEqual(mission["state"], "BLOCKED")
        self.assertEqual(self.store.count("tool_executions", self.mission_id), 1)
        self.assertEqual(self.store.count("chatgpt_messages", self.mission_id), 2)
        events = self.store.rows("transport_events", self.mission_id)
        self.assertTrue(any(e["event_type"] == DUPLICATE_RESPONSE_IGNORED for e in events))

    # 6. Same failing decision repeated 3× → REPETITION_LOOP pause
    async def test_06_repetition_loop_pause(self):
        failing = execute("read_file", {"path": "missing.txt"})
        loop, mock = self.make_loop([dict(failing), dict(failing), dict(failing)])
        mission = await loop.run()

        self.assertEqual(mission["state"], "PAUSED")
        self.assertEqual(mission["pause_reason"], REPETITION_LOOP)
        self.assertEqual(self.store.count("tool_executions", self.mission_id), 2)
        decisions = self.store.rows("orchestrator_decisions", self.mission_id, order_by="rowid")
        self.assertEqual(len(decisions), 3)

    # 7. Iteration budget exhaustion → FAILED with the right reason
    async def test_07_iteration_budget_exhaustion(self):
        for name in ("x1.txt", "x2.txt", "x3.txt"):
            (self.ws / name).write_text(name, encoding="utf-8")
        script = [
            execute("read_file", {"path": "x1.txt"}),
            execute("read_file", {"path": "x2.txt"}),
            execute("read_file", {"path": "x3.txt"}),
        ]
        loop, mock = self.make_loop(script, budgets=Budgets(max_iterations=2))
        mission = await loop.run()

        self.assertEqual(mission["state"], "FAILED")
        self.assertEqual(mission["pause_reason"], ITERATION_BUDGET_EXCEEDED)
        self.assertEqual(self.store.count("tool_executions", self.mission_id), 2)
        self.assertEqual(len(mock.received), 2)  # contract + 1 report; budget stops further sends

    # 8. Restart recovery → PAUSED_RECOVERY_REQUIRED; loop refuses until resume
    async def test_08_restart_recovery_requires_explicit_resume(self):
        (self.ws / "x.txt").write_text("x", encoding="utf-8")
        mock = MockOrchestrator(self.mission_id, [execute("read_file", {"path": "x.txt"}), complete()])
        loop = MissionLoop(
            store=self.store,
            mission_id=self.mission_id,
            orchestrator=mock,
            tools=self.tools,
        )
        await loop.start()
        self.assertEqual(self.store.get_mission(self.mission_id)["state"], "WAITING_FOR_CHATGPT")
        # Simulate a server crash: close the store mid-running-mission.
        self.store.close()

        store2 = Store(self.ws / "cortex.db")
        self.addCleanup(store2.close)
        recovered = store2.get_mission(self.mission_id)
        self.assertEqual(recovered["state"], "PAUSED_RECOVERY_REQUIRED")
        self.assertEqual(recovered["pause_reason"], "SERVER_RESTART")

        loop2 = MissionLoop(
            store=store2,
            mission_id=self.mission_id,
            orchestrator=mock,
            tools=self.tools,
            approval_callback=lambda d, p: "once",
        )
        mission = await loop2.run()
        # The loop refuses to continue a recovered mission without resume.
        self.assertEqual(mission["state"], "PAUSED_RECOVERY_REQUIRED")
        self.assertEqual(mock.received, [])
        self.assertEqual(store2.count("tool_executions", self.mission_id), 0)

        # Explicit user resume → the mission proceeds to completion.
        loop2.sm.resume("WAITING_FOR_CHATGPT")
        mission = await loop2.run()
        self.assertEqual(mission["state"], "COMPLETED")
        self.assertEqual(store2.count("tool_executions", self.mission_id), 1)

    # 9. Protocol violations → rejected with the right error, no tool executed
    async def test_09_protocol_violations_rejected(self):
        script = [
            MockReply(
                "Sure! Here is the result: {\"files\": 3}\n```json\n{\"decoy\": true}\n```",
                "bad-1",
            ),
            MockReply(
                "```cortex-decision\n{}\n```\nsome text\n```cortex-decision\n{}\n```",
                "bad-2",
            ),
            blocked(),
        ]
        loop, mock = self.make_loop(script)
        mission = await loop.run()

        self.assertEqual(mission["state"], "BLOCKED")
        self.assertEqual(self.store.count("tool_executions", self.mission_id), 0)
        decisions = self.store.rows("orchestrator_decisions", self.mission_id, order_by="rowid")
        invalid = [d for d in decisions if d["valid"] == 0]
        self.assertEqual(len(invalid), 2)
        self.assertIn("NO_DECISION_BLOCK", invalid[0]["error"])
        self.assertIn("MULTIPLE_DECISION_BLOCKS", invalid[1]["error"])
        # The orchestrator was told about each violation via the report channel.
        self.assertIn("NO_DECISION_BLOCK", mock.received[1])
        self.assertIn("MULTIPLE_DECISION_BLOCKS", mock.received[2])
        events = self.store.rows("transport_events", self.mission_id)
        self.assertEqual(sum(1 for e in events if e["event_type"] == "PROTOCOL_VIOLATION"), 2)

    async def test_truncated_decision_can_resynchronize_one_iteration_forward(self):
        malformed = MockReply(
            "```cortex-decision\n"
            + json.dumps(
                {
                    "protocol": "cortex.v1",
                    "missionId": self.mission_id,
                    "actionId": str(uuid.uuid4()),
                    "iteration": 1,
                    "state": "EXECUTE",
                }
            )[:-1]
            + "\n```",
            "truncated-decision-1",
        )
        loop, _mock = self.make_loop(
            [
                malformed,
                execute(
                    "write_file",
                    {"path": "recovered.txt", "content": "RECOVERED"},
                    iteration=2,
                ),
                {**complete(), "iteration": 3},
            ]
        )

        mission = await loop.run()

        self.assertEqual(mission["state"], "COMPLETED")
        self.assertEqual((self.ws / "recovered.txt").read_text(), "RECOVERED")
        self.assertEqual(self.store.count("tool_executions", self.mission_id), 1)
        events = self.store.rows("transport_events", self.mission_id)
        self.assertEqual(
            sum(1 for event in events if event["event_type"] == "PROTOCOL_RESYNCHRONIZED"),
            1,
        )

    async def test_truncated_decision_does_not_allow_an_arbitrary_forward_jump(self):
        malformed = MockReply(
            "```cortex-decision\n{\"protocol\":\"cortex.v1\"\n```",
            "truncated-decision-jump",
        )
        loop, _mock = self.make_loop(
            [
                malformed,
                execute(
                    "write_file",
                    {"path": "must-not-exist.txt", "content": "NO"},
                    iteration=3,
                ),
                {**blocked(), "iteration": 3},
            ]
        )

        mission = await loop.run()

        self.assertEqual(mission["state"], "FAILED")
        self.assertEqual(mission["pause_reason"], "PROTOCOL_VIOLATIONS_EXCEEDED")
        self.assertFalse((self.ws / "must-not-exist.txt").exists())
        self.assertEqual(self.store.count("tool_executions", self.mission_id), 0)


if __name__ == "__main__":
    unittest.main()
