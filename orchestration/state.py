"""Mission state machine + duplicate/loop protection (mission spec §12, §14).

Wraps Store with:

* §12 state transitions (via Store.transition / Store.resume);
* §14 budgets: 25 iterations, 60 minutes, 2 local failures per logical
  action, 2 transport retries, 1 fallback attempt;
* repeated-identical-decision detection → PAUSED with REPETITION_LOOP;
* response fingerprints — never process the same assistant response twice;
* report idempotency keys — never send the same report twice.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from . import protocol
from .store import Store, StoreError, TERMINAL_STATES

PAUSED = "PAUSED"
REPETITION_LOOP = "REPETITION_LOOP"
LOCAL_FAILURE_BUDGET_EXCEEDED = "LOCAL_FAILURE_BUDGET_EXCEEDED"
ITERATION_BUDGET_EXCEEDED = "ITERATION_BUDGET_EXCEEDED"
MISSION_TIMEOUT = "MISSION_TIMEOUT"


class DuplicateResponse(StoreError):
    """The same assistant response was presented for processing twice."""


class DuplicateReport(StoreError):
    """The same report was about to be sent twice."""


class BudgetExceeded(StoreError):
    """A §14 budget was exhausted; the mission has been failed/paused."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class Budgets:
    max_iterations: int = 25
    max_duration_seconds: int = 3600
    max_local_failures_per_action: int = 2
    max_transport_retries: int = 2
    max_fallback_attempts: int = 1
    repetition_threshold: int = 3


def response_fingerprint(
    *,
    conversation_identity: str,
    message_identity: str,
    content: str,
    mission_id: str,
    iteration: int,
) -> str:
    """Stable §14 fingerprint of an assistant response."""
    normalized = " ".join(content.split())
    material = "\x1f".join(
        [conversation_identity, message_identity, normalized, mission_id, str(iteration)]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def report_idempotency_key(*, mission_id: str, action_id: str, iteration: int) -> str:
    """One report per (mission, action, iteration) — deterministic key."""
    material = f"cortex-report\x1f{mission_id}\x1f{action_id}\x1f{iteration}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def action_failure_key(tool: str, arguments: dict) -> str:
    """Identity of a logical local action for the §14 failure budget."""
    import json

    canonical = json.dumps(arguments or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{tool}|{canonical}".encode("utf-8")).hexdigest()


class StateMachine:
    """Per-mission state machine bound to a Store."""

    def __init__(
        self,
        store: Store,
        mission_id: str,
        *,
        budgets: Budgets | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.store = store
        self.mission_id = mission_id
        self.budgets = budgets or Budgets()
        self.clock = clock

    # -- mission row helpers ----------------------------------------------------

    def mission(self) -> dict:
        return self.store.get_mission(self.mission_id)

    @property
    def state(self) -> str:
        return self.mission()["state"]

    @property
    def pause_reason(self) -> str | None:
        return self.mission()["pause_reason"]

    @property
    def expected_iteration(self) -> int:
        """The iteration number the next decision must carry (1-based)."""
        return int(self.mission()["iteration"]) + 1

    # -- transitions --------------------------------------------------------------

    def transition(self, new_state: str, *, pause_reason: str | None = None) -> str:
        return self.store.transition(self.mission_id, new_state, pause_reason=pause_reason)

    def resume(self, target_state: str) -> str:
        return self.store.resume(self.mission_id, target_state)

    def cancel(self) -> str:
        return self.transition("CANCELLED")

    def can_continue(self) -> bool:
        mission = self.mission()
        if mission["state"] in TERMINAL_STATES or mission["state"] in ("PAUSED", "PAUSED_RECOVERY_REQUIRED"):
            return False
        try:
            self.check_duration_budget()
        except BudgetExceeded:
            return False
        return True

    # -- budgets (§14) -------------------------------------------------------------

    def check_duration_budget(self) -> None:
        mission = self.mission()
        started = mission["started_at"] or mission["created_at"]
        if self.clock() - started > self.budgets.max_duration_seconds:
            self._fail(MISSION_TIMEOUT)
            raise BudgetExceeded(MISSION_TIMEOUT)

    def advance_iteration(self) -> int:
        """Advance after an iteration completed; enforces the 25-iteration cap."""
        mission = self.mission()
        next_iteration = int(mission["iteration"]) + 1
        if next_iteration > self.budgets.max_iterations:
            self._fail(ITERATION_BUDGET_EXCEEDED)
            raise BudgetExceeded(ITERATION_BUDGET_EXCEEDED)
        self.store.set_iteration(self.mission_id, next_iteration)
        return next_iteration

    def note_action_result(self, tool: str, arguments: dict, *, success: bool) -> None:
        """Record the outcome of a logical local action (§14 failure budget)."""
        key = action_failure_key(tool, arguments)
        counts = self.mission()["failure_counts"]
        entry = counts.setdefault(key, {"failures": 0})
        if not success:
            entry["failures"] += 1
            self.store.set_failure_counts(self.mission_id, counts)
            if entry["failures"] > self.budgets.max_local_failures_per_action:
                self._fail(LOCAL_FAILURE_BUDGET_EXCEEDED)
                raise BudgetExceeded(LOCAL_FAILURE_BUDGET_EXCEEDED)
        else:
            self.store.set_failure_counts(self.mission_id, counts)

    # -- duplicate response protection (§14) ----------------------------------------

    def register_response(
        self,
        *,
        conversation_identity: str,
        message_identity: str,
        content: str,
        iteration: int | None = None,
    ) -> str:
        """Fingerprint + record an assistant response. Rejects duplicates.

        ``iteration`` defaults to the current expected iteration; callers that
        already parsed the decision should pass its embedded iteration so a
        re-delivered response is caught even after the mission advanced.
        """
        fingerprint = response_fingerprint(
            conversation_identity=conversation_identity,
            message_identity=message_identity,
            content=content,
            mission_id=self.mission_id,
            iteration=iteration if iteration is not None else self.expected_iteration,
        )
        if self.store.has_fingerprint(fingerprint):
            raise DuplicateResponse("response already processed (fingerprint seen)")
        self.store.record_message(
            str(uuid.uuid4()), self.mission_id, "assistant", fingerprint, content
        )
        return fingerprint

    # -- decision intake (§10 + §14) ---------------------------------------------------

    def process_decision(self, decision: dict) -> dict:
        """Validate a parsed decision against mission state; record it.

        Enforces mission id / action id / iteration checks and detects
        repeated identical decisions (REPETITION_LOOP after the threshold).
        """
        seen = self.store.seen_action_ids(self.mission_id)
        validated = protocol.validate_decision(
            decision,
            expected_mission_id=self.mission_id,
            expected_iteration=self.expected_iteration,
            seen_action_ids=seen,
        )
        self.store.record_decision(
            str(uuid.uuid4()),
            self.mission_id,
            validated["actionId"],
            validated["iteration"],
            validated,
            valid=True,
        )
        self._track_repetition(validated)
        return validated

    def _track_repetition(self, decision: dict) -> None:
        key = protocol.decision_action_key(decision)
        counts = self.mission()["failure_counts"]
        entry = counts.setdefault(f"decision:{key}", {"emissions": 0, "failures": 0})
        entry["emissions"] += 1
        self.store.set_failure_counts(self.mission_id, counts)
        if (
            entry["emissions"] >= self.budgets.repetition_threshold
            and entry["failures"] >= self.budgets.repetition_threshold - 1
        ):
            self.transition(PAUSED, pause_reason=REPETITION_LOOP)
            raise BudgetExceeded(REPETITION_LOOP)

    def note_decision_result(self, decision: dict, *, success: bool) -> None:
        """Record whether the action of a decision succeeded (loop detection)."""
        key = protocol.decision_action_key(decision)
        counts = self.mission()["failure_counts"]
        entry = counts.setdefault(f"decision:{key}", {"emissions": 0, "failures": 0})
        if not success:
            entry["failures"] += 1
        self.store.set_failure_counts(self.mission_id, counts)

    # -- report idempotency (§14) -------------------------------------------------------

    def send_report_once(self, report: dict) -> str:
        """Record that a report was sent; raises DuplicateReport on resend."""
        key = report_idempotency_key(
            mission_id=self.mission_id,
            action_id=report["actionId"],
            iteration=report["iteration"],
        )
        if self.store.has_report_key(key):
            raise DuplicateReport("report already sent for this action/iteration")
        ok = self.store.record_report_send(
            str(uuid.uuid4()), self.mission_id, key,
            detail={"status": report.get("status"), "report": report},
        )
        if not ok:
            raise DuplicateReport("report already sent for this action/iteration")
        return key

    # -- internal -------------------------------------------------------------------------

    def _fail(self, reason: str) -> None:
        """Best-effort transition to FAILED; ignore if already terminal."""
        try:
            self.store.transition(self.mission_id, "FAILED", pause_reason=reason)
        except StoreError:
            pass
