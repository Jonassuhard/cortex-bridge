"""Mission loop driver (mission spec §12 canonical loop) + mock orchestrator.

`MissionLoop` runs the canonical loop against ANY orchestrator client:

    async def next_decision(message: str | None) -> MockReply-like
        # message is the orchestrator contract (first call) or a rendered
        # ```cortex-report fence (subsequent calls); returns the assistant
        # message (text + stable message identity).

Wiring per cycle:

    receive assistant message
    → duplicate-fingerprint check (never process the same response twice)
    → extract exactly one ```cortex-decision block
    → strict cortex.v1 validation + mission-state checks (§10/§14)
    → REPETITION_LOOP detection
    → policy evaluation (§16) + approval callback hook
    → structured tool dispatch (executor/tools.py, §15)
    → deterministic result validation
    → cortex.v1 report build (§11) + idempotent send-record
    → persist every artifact in SQLite (§18)
    → feed the report back to the orchestrator
    → budgets enforced per cycle (§14)

`MockOrchestrator` implements the client interface with scripted decisions
for tests and local development.
"""

from __future__ import annotations

import inspect
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from executor.policy import PolicyDecision, PolicyEngine
from executor.tools import ToolDenied, ToolError, ToolExecutor

from . import protocol
from .protocol import DecisionError
from .state import (
    ITERATION_BUDGET_EXCEEDED,
    BudgetExceeded,
    Budgets,
    DuplicateReport,
    DuplicateResponse,
    StateMachine,
)
from .store import Store, StoreError, TERMINAL_STATES

DUPLICATE_RESPONSE_IGNORED = "DUPLICATE_RESPONSE_IGNORED"
PROTOCOL_VIOLATION = "PROTOCOL_VIOLATION"
PROTOCOL_VIOLATIONS_EXCEEDED = "PROTOCOL_VIOLATIONS_EXCEEDED"
APPROVAL_DENIED = "APPROVAL_DENIED"
REPORT_RESEND_IGNORED = "REPORT_RESEND_IGNORED"

MAX_CONSECUTIVE_PROTOCOL_VIOLATIONS = 3
MAX_CYCLES = 200  # absolute safety bound independent of §14 budgets

STALLED_STATES = ("PAUSED", "PAUSED_RECOVERY_REQUIRED")


def contract_message(objective: str, mission_id: str, workspace: str) -> str:
    """The §9 orchestrator contract sent as the first transport message."""
    return (
        "You are the cloud orchestrator for Cortex Bridge.\n\n"
        "You analyze the global objective.\n"
        "You produce one bounded local action per iteration.\n"
        "You do not directly claim that local work happened.\n"
        "You wait for the validated execution report.\n"
        "You adapt the next action based on the report.\n"
        "You terminate only when all global acceptance criteria are satisfied.\n\n"
        f"Mission ID: {mission_id}\n"
        f"Workspace: {workspace}\n\n"
        f"Objective:\n{objective}\n\n"
        "Answer with exactly one fenced block and no other structured payload:\n"
        "```cortex-decision\n{...valid cortex.v1 JSON...}\n```"
    )


@dataclass
class MockReply:
    """One assistant message: raw text plus a stable message identity."""

    text: str
    message_id: str


class MockOrchestrator:
    """Scripted orchestrator implementing the client interface.

    Script items:
    * dict  — merged over a valid cortex.v1 decision template; iteration is
      auto-filled from the count of dict items emitted (1-based);
    * str   — returned verbatim as the assistant message;
    * MockReply — verbatim text with an explicit message identity;
    * MockOrchestrator.DUPLICATE_PREVIOUS — re-emit the previous reply
      (same text AND same message identity) to simulate a transport-level
      duplicate (e.g. browser refresh re-extraction).

    ``on_message(message, orchestrator)`` is called on every received
    transport message (contract or report) — used by tests to pause/cancel.
    """

    DUPLICATE_PREVIOUS = "DUPLICATE_PREVIOUS"

    def __init__(
        self,
        mission_id: str,
        script: list,
        *,
        conversation_identity: str = "mock-conversation",
        on_message: Callable[[str | None, "MockOrchestrator"], None] | None = None,
    ):
        self.mission_id = mission_id
        self.script = list(script)
        self.conversation_identity = conversation_identity
        self.on_message = on_message
        self.received: list[str | None] = []
        self.sent: list[MockReply] = []
        self._index = 0
        self._decision_count = 0

    async def next_decision(self, message: str | None) -> MockReply:
        self.received.append(message)
        if self.on_message is not None:
            self.on_message(message, self)
        if self._index >= len(self.script):
            raise RuntimeError("mock orchestrator script exhausted")
        item = self.script[self._index]
        self._index += 1
        if item == self.DUPLICATE_PREVIOUS:
            if not self.sent:
                raise RuntimeError("DUPLICATE_PREVIOUS with no previous reply")
            reply = self.sent[-1]
        elif isinstance(item, MockReply):
            reply = item
        elif isinstance(item, str):
            reply = MockReply(item, f"mock-msg-{self._index}")
        elif isinstance(item, dict):
            self._decision_count += 1
            decision = {
                "protocol": "cortex.v1",
                "missionId": self.mission_id,
                "actionId": str(uuid.uuid4()),
                "iteration": self._decision_count,
                "state": "EXECUTE",
                "summary": "mock decision",
                "action": None,
                "acceptanceCriteria": ["mock criterion"],
                "requiresApproval": False,
                "terminal": False,
            }
            decision.update(item)
            body = json.dumps(decision, indent=2)
            reply = MockReply(
                f"```cortex-decision\n{body}\n```", f"mock-msg-{self._index}"
            )
        else:
            raise TypeError(f"unsupported script item: {item!r}")
        self.sent.append(reply)
        return reply


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


class MissionLoop:
    """Drives one mission through the §12 canonical loop."""

    def __init__(
        self,
        *,
        store: Store,
        mission_id: str,
        orchestrator,
        tools: ToolExecutor,
        policy: PolicyEngine | None = None,
        approval_callback: Callable[[dict, PolicyDecision], Any] | None = None,
        action_validator: Callable[[dict, dict | None, ToolError | None], Any] | None = None,
        final_validator: Callable[[dict, ToolExecutor], Any] | None = None,
        budgets: Budgets | None = None,
        clock: Callable[[], float] = time.time,
        conversation: dict | None = None,
    ):
        self.store = store
        self.budgets = budgets or Budgets()
        self.sm = StateMachine(store, mission_id, budgets=self.budgets, clock=clock)
        self.mission_id = mission_id
        self.orchestrator = orchestrator
        self.tools = tools
        self.policy = policy or PolicyEngine(tools.workspace)
        self.approval_callback = approval_callback
        self.action_validator = action_validator
        self.final_validator = final_validator
        self.conversation = conversation
        self._pending: str | None = contract_message(
            store.get_mission(mission_id)["objective"], mission_id, str(tools.workspace)
        )
        self._stashed: MockReply | None = None
        self._protocol_violations = 0

    # -- lifecycle ------------------------------------------------------------

    async def start(self) -> dict:
        """Drive a fresh mission to WAITING_FOR_CHATGPT (idempotent)."""
        mission = self.sm.mission()
        if mission["state"] == "IDLE":
            self.sm.transition("INITIALIZING_MISSION")
            mission = self.sm.mission()
        if self.conversation and self.store.count("conversation_bindings", self.mission_id) == 0:
            self.store.bind_conversation(
                str(uuid.uuid4()),
                self.mission_id,
                self.conversation.get("url", "mock://conversation"),
                self.conversation.get("title"),
                self.conversation.get("target_id"),
            )
        if mission["state"] == "INITIALIZING_MISSION":
            self.sm.transition("SENDING_OBJECTIVE")
            mission = self.sm.mission()
        if mission["state"] == "SENDING_OBJECTIVE":
            self.sm.transition("WAITING_FOR_CHATGPT")
        return self.sm.mission()

    async def run(self, max_cycles: int = MAX_CYCLES) -> dict:
        """Run until terminal, paused, budget-exhausted, or max_cycles."""
        await self.start()
        for _ in range(max_cycles):
            mission = self.sm.mission()
            if mission["state"] in TERMINAL_STATES or mission["state"] in STALLED_STATES:
                return mission
            try:
                self.sm.check_duration_budget()
            except BudgetExceeded:
                return self.sm.mission()
            if self.sm.expected_iteration > self.budgets.max_iterations:
                self.sm.transition("FAILED", pause_reason=ITERATION_BUDGET_EXCEEDED)
                return self.sm.mission()

            if self._stashed is not None:
                reply, self._stashed = self._stashed, None
            else:
                reply = await self.orchestrator.next_decision(self._pending)

            mission = self.sm.mission()
            if mission["state"] in TERMINAL_STATES:
                return mission
            if mission["state"] in STALLED_STATES:
                # Paused/cancelled externally while waiting (e.g. user pause):
                # stash the unprocessed reply so an explicit resume continues
                # exactly where the loop stopped.
                self._stashed = reply
                return mission

            self.sm.transition("PARSING_DECISION")
            try:
                outcome = await self._handle_reply(reply)
            except BudgetExceeded:
                return self.sm.mission()
            if outcome == "stop":
                return self.sm.mission()
            if self.sm.state == "REPLANNING":
                self.sm.transition("WAITING_FOR_CHATGPT")
        raise RuntimeError(f"loop exceeded safety bound of {max_cycles} cycles")

    # -- per-cycle handling -----------------------------------------------------

    async def _handle_reply(self, reply: MockReply) -> str:
        text, message_id = reply.text, reply.message_id
        conversation_identity = getattr(
            self.orchestrator, "conversation_identity", "unknown-conversation"
        )

        # Extract first so the §14 fingerprint uses the embedded iteration —
        # a re-delivered response is caught even after the mission advanced.
        parsed: dict | None = None
        extraction_error: DecisionError | None = None
        embedded_iteration: int | None = None
        try:
            parsed = protocol.extract_decision_block(text)
            it = parsed.get("iteration")
            if isinstance(it, int) and not isinstance(it, bool):
                embedded_iteration = it
        except DecisionError as exc:
            extraction_error = exc

        try:
            self.sm.register_response(
                conversation_identity=conversation_identity,
                message_identity=message_id,
                content=text,
                iteration=embedded_iteration,
            )
        except DuplicateResponse:
            self.store.record_transport_event(
                str(uuid.uuid4()),
                self.mission_id,
                DUPLICATE_RESPONSE_IGNORED,
                {"message_id": message_id},
            )
            self.sm.transition("REPLANNING")
            return "continue"  # pending unchanged: ask the orchestrator again

        if extraction_error is not None:
            self._record_protocol_violation(extraction_error, text, None)
            return "continue" if self.sm.state not in TERMINAL_STATES else "stop"

        try:
            decision = self.sm.process_decision(parsed)
        except DecisionError as exc:
            self._record_protocol_violation(exc, text, parsed)
            return "continue" if self.sm.state not in TERMINAL_STATES else "stop"
        except BudgetExceeded:
            raise  # REPETITION_LOOP pause already applied by the state machine

        self._protocol_violations = 0
        state = decision["state"]
        if state == "BLOCKED":
            self.sm.transition("BLOCKED")
            return "stop"
        if state == "COMPLETE":
            return await self._handle_complete(decision)
        return await self._handle_action(decision)

    # -- protocol violations -------------------------------------------------------

    def _record_protocol_violation(
        self, error: DecisionError, text: str, parsed: dict | None
    ) -> None:
        self._protocol_violations += 1
        action_id = str(uuid.uuid4())
        if parsed and isinstance(parsed.get("actionId"), str):
            try:
                uuid.UUID(parsed["actionId"])
                action_id = parsed["actionId"]
            except ValueError:
                pass
        try:
            self.store.record_decision(
                str(uuid.uuid4()),
                self.mission_id,
                action_id,
                (parsed or {}).get("iteration") or self.sm.expected_iteration,
                parsed if parsed is not None else {"raw": text[:2000]},
                valid=False,
                error=f"{error.code}: {error.message}",
            )
        except StoreError:
            pass  # e.g. action_id already recorded — the violation is still reported
        self.store.record_transport_event(
            str(uuid.uuid4()),
            self.mission_id,
            PROTOCOL_VIOLATION,
            {"code": error.code, "message": error.message},
        )
        report = protocol.build_report(
            mission_id=self.mission_id,
            action_id=action_id,
            iteration=(parsed or {}).get("iteration") or self.sm.expected_iteration,
            status="FAILED",
            summary=f"protocol violation: {error.code}: {error.message}",
            tool=None,
            validation={
                "passed": False,
                "checks": [
                    {
                        "name": "protocol_validation",
                        "passed": False,
                        "evidence": f"{error.code}: {error.message}",
                    }
                ],
            },
            blockers=[error.code],
        )
        self._pending = protocol.render_report_message(report)
        if self._protocol_violations >= MAX_CONSECUTIVE_PROTOCOL_VIOLATIONS:
            self.sm.transition("FAILED", pause_reason=PROTOCOL_VIOLATIONS_EXCEEDED)
            return
        self.sm.transition("REPLANNING")

    # -- EXECUTE / REQUEST_CONTEXT ----------------------------------------------------

    async def _handle_action(self, decision: dict) -> str:
        tool = decision["action"]["tool"]
        arguments = decision["action"].get("arguments", {})
        action_id = decision["actionId"]

        policy_decision = self.policy.evaluate(tool, arguments)
        self.store.record_policy_decision(
            str(uuid.uuid4()),
            self.mission_id,
            action_id,
            tool,
            allowed=policy_decision.allowed,
            requires_approval=policy_decision.requires_approval,
            reason=policy_decision.reason,
        )
        if not policy_decision.allowed:
            report = protocol.build_report(
                mission_id=self.mission_id,
                action_id=action_id,
                iteration=decision["iteration"],
                status="DENIED",
                summary=f"policy denied {tool}: {policy_decision.reason}",
                tool=tool,
                tool_result={"exitCode": 1, "stderr": policy_decision.reason},
                validation={
                    "passed": False,
                    "checks": [
                        {
                            "name": "policy",
                            "passed": False,
                            "evidence": policy_decision.reason,
                        }
                    ],
                },
                blockers=[policy_decision.denial_code or "POLICY_DENIED"],
            )
            return self._finalize_cycle(decision, report, success=False)

        if policy_decision.requires_approval:
            self.sm.transition("WAITING_FOR_APPROVAL")
            scope = None
            if self.approval_callback is not None:
                scope = await _maybe_await(
                    self.approval_callback(decision, policy_decision)
                )
            self.store.record_approval(
                str(uuid.uuid4()),
                self.mission_id,
                action_id,
                tool,
                scope if isinstance(scope, str) else "denied",
                bool(scope),
            )
            if not scope:
                report = protocol.build_report(
                    mission_id=self.mission_id,
                    action_id=action_id,
                    iteration=decision["iteration"],
                    status="DENIED",
                    summary=f"approval denied for {tool}",
                    tool=tool,
                    tool_result={"exitCode": 1, "stderr": APPROVAL_DENIED},
                    validation={
                        "passed": False,
                        "checks": [
                            {"name": "approval", "passed": False, "evidence": APPROVAL_DENIED}
                        ],
                    },
                    blockers=[APPROVAL_DENIED],
                )
                return self._finalize_cycle(decision, report, success=False)

        self.sm.transition("EXECUTING_LOCAL_ACTION")
        started = time.time()
        result: dict | None = None
        tool_error: ToolError | None = None
        try:
            result = await getattr(self.tools, tool)(**arguments)
        except (ToolDenied, ToolError) as exc:
            tool_error = exc
        finished = time.time()
        self.store.record_tool_execution(
            str(uuid.uuid4()),
            self.mission_id,
            action_id,
            tool,
            arguments,
            result if result is not None else {"error": f"{tool_error.code}: {tool_error.message}"},
            (result or {}).get("exitCode", 1 if tool_error else 0),
            started,
            finished,
        )

        self.sm.transition("VALIDATING_ACTION")
        validation = await self._validate_action(decision, result, tool_error)
        self.store.record_validation(
            str(uuid.uuid4()), self.mission_id, action_id, validation["passed"], validation["checks"]
        )

        for artifact_path in self._artifacts_of(result):
            self.store.record_artifact(
                str(uuid.uuid4()),
                self.mission_id,
                action_id,
                artifact_path,
                artifact_path,
                None,
            )

        if tool_error is not None:
            denied = isinstance(tool_error, ToolDenied)
            report = protocol.build_report(
                mission_id=self.mission_id,
                action_id=action_id,
                iteration=decision["iteration"],
                status="DENIED" if denied else "FAILED",
                summary=f"{tool} failed: {tool_error.code}: {tool_error.message}",
                tool=tool,
                tool_result={
                    "exitCode": 1,
                    "stderr": f"{tool_error.code}: {tool_error.message}",
                },
                validation=validation,
                blockers=[tool_error.code],
            )
            return self._finalize_cycle(decision, report, success=False)

        summary = f"{tool} executed successfully."
        report = protocol.build_report(
            mission_id=self.mission_id,
            action_id=action_id,
            iteration=decision["iteration"],
            status="SUCCEEDED" if validation["passed"] else "FAILED",
            summary=summary if validation["passed"] else f"{tool} executed but validation failed.",
            tool=tool,
            tool_result=self._tool_result_view(tool, result),
            files_changed=list((result or {}).get("filesChanged", [])),
            validation=validation,
        )
        return self._finalize_cycle(decision, report, success=validation["passed"])

    async def _validate_action(
        self, decision: dict, result: dict | None, tool_error: ToolError | None
    ) -> dict:
        if self.action_validator is not None:
            outcome = await _maybe_await(
                self.action_validator(decision, result, tool_error)
            )
            if outcome is not None:
                return outcome
        ok = tool_error is None
        return {
            "passed": ok,
            "checks": [
                {
                    "name": "tool_execution",
                    "passed": ok,
                    "evidence": (
                        f"{decision['action']['tool']} completed without tool error"
                        if ok
                        else f"{tool_error.code}: {tool_error.message}"
                    ),
                }
            ],
        }

    @staticmethod
    def _tool_result_view(tool: str, result: dict | None) -> dict:
        result = result or {}
        if "exitCode" in result:
            return {
                "exitCode": result.get("exitCode", 0),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
            }
        return {
            "exitCode": 0,
            "stdout": json.dumps(result, sort_keys=True)[:4000],
            "stderr": "",
        }

    @staticmethod
    def _artifacts_of(result: dict | None) -> list[str]:
        if not result:
            return []
        artifacts = []
        if result.get("backup"):
            artifacts.append(result["backup"])
        return artifacts

    # -- COMPLETE -----------------------------------------------------------------------

    async def _handle_complete(self, decision: dict) -> str:
        self.sm.transition("FINAL_VALIDATION")
        if self.final_validator is not None:
            validation = await _maybe_await(self.final_validator(decision, self.tools))
        else:
            validation = {
                "passed": True,
                "checks": [
                    {
                        "name": "final_validation",
                        "passed": True,
                        "evidence": "no deterministic final validator configured",
                    }
                ],
            }
        self.store.record_validation(
            str(uuid.uuid4()),
            self.mission_id,
            decision["actionId"],
            validation["passed"],
            validation["checks"],
        )
        if validation["passed"]:
            self.sm.transition("COMPLETED")
            return "stop"
        report = protocol.build_report(
            mission_id=self.mission_id,
            action_id=decision["actionId"],
            iteration=decision["iteration"],
            status="FAILED",
            summary="final validation failed; mission continues within budget.",
            tool=None,
            tool_result={"exitCode": 1, "stderr": "final validation failed"},
            validation=validation,
        )
        return self._finalize_cycle(decision, report, success=False)

    # -- report + replan ------------------------------------------------------------------

    def _finalize_cycle(self, decision: dict, report: dict, *, success: bool) -> str:
        try:
            self.sm.send_report_once(report)
        except DuplicateReport:
            # §14: never send the same report twice — keep the loop consistent.
            self.store.record_transport_event(
                str(uuid.uuid4()),
                self.mission_id,
                REPORT_RESEND_IGNORED,
                {"action_id": report["actionId"], "iteration": report["iteration"]},
            )
        self.sm.note_decision_result(decision, success=success)
        self.sm.transition("SENDING_REPORT")
        self._pending = protocol.render_report_message(report)
        self.store.record_iteration(
            self.mission_id,
            decision["iteration"],
            decision["actionId"],
            "SENDING_REPORT",
            finished_at=time.time(),
        )
        self.sm.transition("REPLANNING")
        self.sm.advance_iteration()  # raises BudgetExceeded past the §14 cap
        return "continue"
