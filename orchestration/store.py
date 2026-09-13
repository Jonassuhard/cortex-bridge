"""SQLite persistence for Cortex Bridge (mission spec §18).

Eleven tables: missions, conversation_bindings, iterations, chatgpt_messages,
orchestrator_decisions, policy_decisions, approvals, tool_executions,
validation_results, transport_events, artifacts.

Every state transition is persisted transactionally. On open, any mission
left in a running state is set to PAUSED_RECOVERY_REQUIRED and is never
auto-resumed.
"""

from __future__ import annotations

import json
import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "console" / "data" / "cortex.db"

# §12 states plus the §18 recovery state.
ALL_STATES = (
    "IDLE",
    "SELECTING_CONVERSATION",
    "INITIALIZING_MISSION",
    "SENDING_OBJECTIVE",
    "WAITING_FOR_CHATGPT",
    "PARSING_DECISION",
    "WAITING_FOR_APPROVAL",
    "EXECUTING_LOCAL_ACTION",
    "VALIDATING_ACTION",
    "SENDING_REPORT",
    "REPLANNING",
    "FINAL_VALIDATION",
    "COMPLETED",
    "BLOCKED",
    "FAILED",
    "PAUSED",
    "CANCELLED",
    "TRANSPORT_ERROR",
    "PAUSED_RECOVERY_REQUIRED",
)

RUNNING_STATES = frozenset(
    {
        "INITIALIZING_MISSION",
        "SENDING_OBJECTIVE",
        "WAITING_FOR_CHATGPT",
        "PARSING_DECISION",
        "WAITING_FOR_APPROVAL",
        "EXECUTING_LOCAL_ACTION",
        "VALIDATING_ACTION",
        "SENDING_REPORT",
        "REPLANNING",
        "FINAL_VALIDATION",
        "TRANSPORT_ERROR",
    }
)

TERMINAL_STATES = frozenset({"COMPLETED", "BLOCKED", "FAILED", "CANCELLED"})

# Allowed forward transitions. Resume from PAUSED / PAUSED_RECOVERY_REQUIRED
# is handled separately (explicit user-driven target state).
TRANSITIONS: dict[str, frozenset[str]] = {
    "IDLE": frozenset(
        {"SELECTING_CONVERSATION", "INITIALIZING_MISSION", "PAUSED", "CANCELLED"}
    ),
    "SELECTING_CONVERSATION": frozenset({"INITIALIZING_MISSION", "PAUSED", "CANCELLED"}),
    "INITIALIZING_MISSION": frozenset(
        {"SENDING_OBJECTIVE", "FAILED", "PAUSED", "CANCELLED"}
    ),
    "SENDING_OBJECTIVE": frozenset({"WAITING_FOR_CHATGPT", "TRANSPORT_ERROR", "CANCELLED"}),
    "WAITING_FOR_CHATGPT": frozenset(
        {"PARSING_DECISION", "PAUSED", "CANCELLED", "TRANSPORT_ERROR"}
    ),
    "PARSING_DECISION": frozenset(
        {
            "WAITING_FOR_APPROVAL",
            "EXECUTING_LOCAL_ACTION",
            "FINAL_VALIDATION",
            "SENDING_REPORT",
            "REPLANNING",
            "BLOCKED",
            "FAILED",
            "PAUSED",
            "CANCELLED",
        }
    ),
    "WAITING_FOR_APPROVAL": frozenset(
        {"EXECUTING_LOCAL_ACTION", "SENDING_REPORT", "PAUSED", "CANCELLED", "BLOCKED"}
    ),
    "EXECUTING_LOCAL_ACTION": frozenset(
        {"VALIDATING_ACTION", "FAILED", "PAUSED", "CANCELLED"}
    ),
    "VALIDATING_ACTION": frozenset({"SENDING_REPORT", "FAILED"}),
    "SENDING_REPORT": frozenset({"REPLANNING", "TRANSPORT_ERROR", "PAUSED", "CANCELLED"}),
    "REPLANNING": frozenset({"WAITING_FOR_CHATGPT", "PAUSED", "CANCELLED", "FAILED"}),
    "FINAL_VALIDATION": frozenset({"COMPLETED", "SENDING_REPORT", "FAILED"}),
    "TRANSPORT_ERROR": frozenset(
        {"WAITING_FOR_CHATGPT", "SENDING_OBJECTIVE", "SENDING_REPORT", "PAUSED", "FAILED", "CANCELLED"}
    ),
    "PAUSED": frozenset({"CANCELLED"}),
    "PAUSED_RECOVERY_REQUIRED": frozenset({"CANCELLED"}),
    "COMPLETED": frozenset(),
    "BLOCKED": frozenset(),
    "FAILED": frozenset(),
    "CANCELLED": frozenset(),
}

RESUMABLE_FROM = frozenset({"PAUSED", "PAUSED_RECOVERY_REQUIRED"})

# Budget exhaustion / user cancellation may fail or cancel a mission from any
# running state.
for _state in list(TRANSITIONS):
    if _state in RUNNING_STATES:
        TRANSITIONS[_state] = TRANSITIONS[_state] | {"FAILED", "CANCELLED"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS missions (
    id TEXT PRIMARY KEY,
    objective TEXT NOT NULL,
    workspace TEXT NOT NULL,
    state TEXT NOT NULL,
    pause_reason TEXT,
    paused_from_state TEXT,
    iteration INTEGER NOT NULL DEFAULT 0,
    max_iterations INTEGER NOT NULL DEFAULT 25,
    max_duration_seconds INTEGER NOT NULL DEFAULT 3600,
    failure_counts TEXT NOT NULL DEFAULT '{}',
    executor_kind TEXT NOT NULL DEFAULT 'unavailable',
    executor_model_used TEXT,
    runtime_mode TEXT NOT NULL DEFAULT 'live',
    release_eligible INTEGER NOT NULL DEFAULT 0,
    runtime_observed_at REAL,
    created_at REAL NOT NULL,
    started_at REAL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS conversation_bindings (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    conversation_url TEXT NOT NULL,
    conversation_title TEXT,
    browser_target_id TEXT,
    session_id TEXT,
    conversation_target TEXT,
    selected_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS iterations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    iteration INTEGER NOT NULL,
    action_id TEXT,
    state TEXT NOT NULL,
    started_at REAL NOT NULL,
    finished_at REAL
);
CREATE TABLE IF NOT EXISTS chatgpt_messages (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    role TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    content TEXT NOT NULL,
    received_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS orchestrator_decisions (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    action_id TEXT NOT NULL,
    iteration INTEGER NOT NULL,
    decision_json TEXT NOT NULL,
    valid INTEGER NOT NULL,
    error TEXT,
    received_at REAL NOT NULL,
    UNIQUE (mission_id, action_id)
);
CREATE TABLE IF NOT EXISTS policy_decisions (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    action_id TEXT,
    tool TEXT NOT NULL,
    allowed INTEGER NOT NULL,
    requires_approval INTEGER NOT NULL,
    reason TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    action_id TEXT,
    tool TEXT NOT NULL,
    scope TEXT NOT NULL,
    approved INTEGER NOT NULL,
    decided_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tool_executions (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    action_id TEXT,
    tool TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    result_json TEXT,
    exit_code INTEGER,
    started_at REAL NOT NULL,
    finished_at REAL
);
CREATE TABLE IF NOT EXISTS validation_results (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    action_id TEXT,
    passed INTEGER NOT NULL,
    checks_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS transport_events (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    event_type TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    idempotency_key TEXT UNIQUE,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(id),
    action_id TEXT,
    name TEXT NOT NULL,
    path TEXT,
    sha256 TEXT,
    created_at REAL NOT NULL
);
"""


class StoreError(Exception):
    pass


class InvalidTransition(StoreError):
    pass


class DuplicateRecord(StoreError):
    pass


class Store:
    """SQLite-backed persistence. One Store per process is expected."""

    def __init__(self, path: str | Path | None = None, *, recover_interrupted: bool = True):
        self.path = Path(path) if path else DEFAULT_DB_PATH
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._migrate_conversation_bindings()
        self._migrate_mission_runtime_truth()
        # Only the runtime owner performs startup recovery. Short-lived journal
        # clients must not pause missions owned by an already-running process.
        if recover_interrupted:
            self._recover_interrupted_missions()
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        self._conn.close()
        self._closed = True

    def _migrate_conversation_bindings(self) -> None:
        """Add v0.5 lease fields without invalidating an existing evidence DB."""
        columns = {
            row["name"]
            for row in self._conn.execute(
                "PRAGMA table_info(conversation_bindings)"
            ).fetchall()
        }
        with self._conn:
            if "session_id" not in columns:
                self._conn.execute(
                    "ALTER TABLE conversation_bindings ADD COLUMN session_id TEXT"
                )
            if "conversation_target" not in columns:
                self._conn.execute(
                    "ALTER TABLE conversation_bindings ADD COLUMN conversation_target TEXT"
                )

    def _migrate_mission_runtime_truth(self) -> None:
        """Add durable runtime evidence fields without replacing old databases."""
        columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(missions)").fetchall()
        }
        additions = {
            "paused_from_state": "TEXT",
            "executor_kind": "TEXT NOT NULL DEFAULT 'unavailable'",
            "executor_model_used": "TEXT",
            "runtime_mode": "TEXT NOT NULL DEFAULT 'live'",
            "release_eligible": "INTEGER NOT NULL DEFAULT 0",
            "runtime_observed_at": "REAL",
        }
        with self._conn:
            for name, definition in additions.items():
                if name not in columns:
                    self._conn.execute(
                        f"ALTER TABLE missions ADD COLUMN {name} {definition}"
                    )

    # -- §18 restart recovery -------------------------------------------------

    def _recover_interrupted_missions(self) -> list[str]:
        """Missions left running by a crash/restart → PAUSED_RECOVERY_REQUIRED."""
        now = time.time()
        with self._conn:
            cur = self._conn.execute(
                "SELECT id FROM missions WHERE state IN ({})".format(
                    ",".join("?" for _ in RUNNING_STATES)
                ),
                tuple(RUNNING_STATES),
            )
            ids = [row["id"] for row in cur.fetchall()]
            self._conn.execute(
                "UPDATE missions SET paused_from_state = state, state = ?,"
                " pause_reason = ?, updated_at = ? "
                "WHERE state IN ({})".format(",".join("?" for _ in RUNNING_STATES)),
                (
                    "PAUSED_RECOVERY_REQUIRED",
                    "SERVER_RESTART",
                    now,
                    *tuple(RUNNING_STATES),
                ),
            )
        return ids

    # -- missions ---------------------------------------------------------------

    def create_mission(
        self,
        mission_id: str,
        objective: str,
        workspace: str,
        *,
        max_iterations: int = 25,
        max_duration_seconds: int = 3600,
        started_at: float | None = None,
        executor_kind: str = "unavailable",
        executor_model_used: str | None = None,
        runtime_mode: str = "live",
        release_eligible: bool = False,
    ) -> dict:
        now = time.time()
        with self._conn:
            self._conn.execute(
                "INSERT INTO missions (id, objective, workspace, state, pause_reason,"
                " paused_from_state,"
                " iteration, max_iterations, max_duration_seconds, failure_counts,"
                " executor_kind, executor_model_used, runtime_mode, release_eligible,"
                " runtime_observed_at, created_at, started_at, updated_at)"
                " VALUES (?,?,?,?,?,?,0,?,?,'{}',?,?,?,?,?,?,?,?)",
                (
                    mission_id,
                    objective,
                    workspace,
                    "IDLE",
                    None,
                    None,
                    max_iterations,
                    max_duration_seconds,
                    executor_kind,
                    executor_model_used,
                    runtime_mode,
                    1 if release_eligible else 0,
                    now,
                    now,
                    started_at if started_at is not None else now,
                    now,
                ),
            )
        return self.get_mission(mission_id)

    def record_runtime_truth(
        self,
        mission_id: str,
        *,
        executor_kind: str,
        executor_model_used: str | None,
        runtime_mode: str,
        release_eligible: bool,
    ) -> dict:
        if executor_kind not in {"deterministic", "ollama", "unavailable"}:
            raise StoreError(f"unknown executor kind {executor_kind}")
        if runtime_mode not in {"live", "development_fixture"}:
            raise StoreError(f"unknown runtime mode {runtime_mode}")
        now = time.time()
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE missions SET executor_kind = ?, executor_model_used = ?,"
                " runtime_mode = ?, release_eligible = ?, runtime_observed_at = ?,"
                " updated_at = ? WHERE id = ?",
                (
                    executor_kind,
                    executor_model_used,
                    runtime_mode,
                    1 if release_eligible else 0,
                    now,
                    now,
                    mission_id,
                ),
            )
            if cursor.rowcount != 1:
                raise StoreError(f"unknown mission {mission_id}")
        return self.get_mission(mission_id)

    def get_mission(self, mission_id: str) -> dict:
        row = self._conn.execute(
            "SELECT * FROM missions WHERE id = ?", (mission_id,)
        ).fetchone()
        if row is None:
            raise StoreError(f"unknown mission {mission_id}")
        data = dict(row)
        data["failure_counts"] = json.loads(data["failure_counts"] or "{}")
        data["release_eligible"] = bool(data.get("release_eligible", False))
        return data

    def transition(self, mission_id: str, new_state: str, *, pause_reason: str | None = None) -> str:
        """Transactional state transition with adjacency enforcement."""
        if new_state not in ALL_STATES:
            raise InvalidTransition(f"unknown state {new_state}")
        with self._conn:
            row = self._conn.execute(
                "SELECT state FROM missions WHERE id = ?", (mission_id,)
            ).fetchone()
            if row is None:
                raise StoreError(f"unknown mission {mission_id}")
            current = row["state"]
            if new_state not in TRANSITIONS[current]:
                raise InvalidTransition(f"{current} → {new_state} is not allowed")
            paused_from_state = current if new_state in RESUMABLE_FROM else None
            self._conn.execute(
                "UPDATE missions SET state = ?, pause_reason = ?, paused_from_state = ?,"
                " updated_at = ? WHERE id = ?",
                (new_state, pause_reason, paused_from_state, time.time(), mission_id),
            )
        return new_state

    def resume(self, mission_id: str, target_state: str | None = None) -> str:
        """Resume explicitly, restoring the durable pre-pause state by default."""
        with self._conn:
            row = self._conn.execute(
                "SELECT state, paused_from_state FROM missions WHERE id = ?", (mission_id,)
            ).fetchone()
            if row is None:
                raise StoreError(f"unknown mission {mission_id}")
            current = row["state"]
            if current not in RESUMABLE_FROM:
                raise InvalidTransition(f"cannot resume from {current}")
            restored_state = target_state or row["paused_from_state"]
            if restored_state not in RUNNING_STATES:
                raise InvalidTransition(
                    f"cannot resume without a valid paused state (got {restored_state})"
                )
            self._conn.execute(
                "UPDATE missions SET state = ?, pause_reason = NULL, paused_from_state = NULL,"
                " updated_at = ? WHERE id = ?",
                (restored_state, time.time(), mission_id),
            )
        return restored_state

    def set_iteration(self, mission_id: str, iteration: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE missions SET iteration = ?, updated_at = ? WHERE id = ?",
                (iteration, time.time(), mission_id),
            )

    def set_failure_counts(self, mission_id: str, counts: dict) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE missions SET failure_counts = ?, updated_at = ? WHERE id = ?",
                (json.dumps(counts, sort_keys=True), time.time(), mission_id),
            )

    # -- duplicate / idempotency primitives (§14) ------------------------------

    def unresolved_outbound(self, mission_id: str) -> dict | None:
        events = self.rows("transport_events", mission_id, order_by="rowid")
        settled = {json.loads(e["detail_json"]).get("send_id") for e in events
                   if e["event_type"] in {"MESSAGE_SEND_ABORTED", "MESSAGE_DELIVERED"}}
        pending = [e for e in events if e["event_type"] == "MESSAGE_SEND_STARTED" and e["id"] not in settled]
        if len(pending) > 1:
            raise StoreError("multiple unresolved sends require manual reconciliation")
        return pending[0] if pending else None

    def reserve_outbound(self, event_id: str, mission_id: str, message: str, *, checkpoint: dict | None = None) -> str:
        """Durably reserve exact outbound bytes before a transport side effect.

        A reservation survives a crash. Only an explicit pre-delivery abort
        permits another attempt; unresolved/confirmed sends require reconciliation.
        """
        digest = hashlib.sha256(message.encode("utf-8")).hexdigest()
        try:
            with self._conn:
                # Lock before reading: different payloads have different unique
                # keys, so uniqueness alone cannot prevent competing sends.
                self._conn.execute("BEGIN IMMEDIATE")
                if checkpoint and checkpoint.get("channel") == "native_host":
                    state = self.get_mission(mission_id)["state"]
                    if state in TERMINAL_STATES or state.startswith("PAUSED"):
                        raise StoreError("mission stopped or paused")
                    self.check_native_deadline(mission_id)
                events = self.rows("transport_events", mission_id, order_by="rowid")
                if checkpoint and checkpoint.get("channel") == "native_host":
                    limit = self.get_mission(mission_id)["max_iterations"]
                    native_attempts = [e for e in events
                                       if e["event_type"] == "MESSAGE_SEND_STARTED"
                                       and (json.loads(e["detail_json"]).get("checkpoint") or {}).get("channel") == "native_host"]
                    if type(limit) is not int or limit <= 0 or len(native_attempts) >= limit:
                        raise StoreError("native outbound attempt budget exhausted or invalid")
                settled = {json.loads(e["detail_json"]).get("send_id") for e in events
                           if e["event_type"] in {"MESSAGE_SEND_ABORTED", "MESSAGE_DELIVERED"}}
                if any(e["event_type"] == "MESSAGE_SEND_STARTED" and e["id"] not in settled for e in events):
                    raise StoreError("unresolved outbound requires reconciliation")
                attempts = [e for e in events if e["event_type"] == "MESSAGE_SEND_STARTED"
                            and json.loads(e["detail_json"]).get("sha256") == digest]
                if attempts:
                    last_id = attempts[-1]["id"]
                    outcomes = {e["event_type"] for e in events
                                if json.loads(e["detail_json"]).get("send_id") == last_id}
                    if "MESSAGE_SEND_ABORTED" not in outcomes or "MESSAGE_DELIVERED" in outcomes:
                        raise StoreError("outbound requires reconciliation")
                key = f"outbound:{mission_id}:{digest}:{len(attempts)}"
                self._conn.execute(
                    "INSERT INTO transport_events (id, mission_id, event_type,"
                    " detail_json, idempotency_key, created_at) VALUES (?,?,?,?,?,?)",
                    (event_id, mission_id, "MESSAGE_SEND_STARTED",
                     json.dumps({"sha256": digest, "bytes": len(message.encode("utf-8")), "checkpoint": checkpoint}),
                     key, time.time()),
                )
        except sqlite3.IntegrityError as exc:
            raise StoreError("outbound reservation failed; reconciliation required") from exc
        return digest

    def record_message(
        self,
        message_id: str,
        mission_id: str,
        role: str,
        fingerprint: str,
        content: str,
    ) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO chatgpt_messages (id, mission_id, role, fingerprint,"
                    " content, received_at) VALUES (?,?,?,?,?,?)",
                    (message_id, mission_id, role, fingerprint, content, time.time()),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateRecord(f"fingerprint already recorded: {fingerprint}") from exc

    def has_fingerprint(self, fingerprint: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM chatgpt_messages WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
        return row is not None

    def record_decision(
        self,
        record_id: str,
        mission_id: str,
        action_id: str,
        iteration: int,
        decision: dict,
        *,
        valid: bool,
        error: str | None = None,
    ) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO orchestrator_decisions (id, mission_id, action_id,"
                    " iteration, decision_json, valid, error, received_at)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (
                        record_id,
                        mission_id,
                        action_id,
                        iteration,
                        json.dumps(decision, sort_keys=True),
                        1 if valid else 0,
                        error,
                        time.time(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateRecord(f"action already recorded: {action_id}") from exc

    def seen_action_ids(self, mission_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT action_id FROM orchestrator_decisions WHERE mission_id = ? AND valid = 1",
            (mission_id,),
        ).fetchall()
        return [r["action_id"] for r in rows]

    def record_report_send(
        self,
        event_id: str,
        mission_id: str,
        idempotency_key: str,
        detail: dict | None = None,
    ) -> bool:
        """Insert a report-sent transport event. False if the key was used."""
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO transport_events (id, mission_id, event_type,"
                    " detail_json, idempotency_key, created_at) VALUES (?,?,?,?,?,?)",
                    (
                        event_id,
                        mission_id,
                        "REPORT_SENT",
                        json.dumps(detail or {}, sort_keys=True),
                        idempotency_key,
                        time.time(),
                    ),
                )
        except sqlite3.IntegrityError:
            return False
        return True

    def has_report_key(self, idempotency_key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM transport_events WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return row is not None

    # -- remaining evidence tables ---------------------------------------------

    def record_iteration(
        self,
        mission_id: str,
        iteration: int,
        action_id: str | None,
        state: str,
        *,
        finished_at: float | None = None,
    ) -> int:
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO iterations (mission_id, iteration, action_id, state,"
                " started_at, finished_at) VALUES (?,?,?,?,?,?)",
                (mission_id, iteration, action_id, state, time.time(), finished_at),
            )
            return int(cur.lastrowid)

    def bind_conversation(
        self,
        binding_id: str,
        mission_id: str,
        conversation_url: str,
        conversation_title: str | None = None,
        browser_target_id: str | None = None,
        session_id: str | None = None,
        conversation_target: str | None = None,
    ) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO conversation_bindings (id, mission_id, conversation_url,"
                " conversation_title, browser_target_id, session_id,"
                " conversation_target, selected_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (
                    binding_id,
                    mission_id,
                    conversation_url,
                    conversation_title,
                    browser_target_id,
                    session_id,
                    conversation_target or conversation_url,
                    time.time(),
                ),
            )

    def update_conversation_binding(
        self,
        mission_id: str,
        conversation_url: str,
        conversation_title: str | None = None,
        browser_target_id: str | None = None,
        session_id: str | None = None,
        conversation_target: str | None = None,
    ) -> None:
        """Refresh a mission's binding once the real /c/<id> identity is known
        (new-chat case: the binding is first stored with the bare chatgpt.com
        URL and no identity; the lock captured after the first send replaces
        it so a later resume can re-attach instead of re-navigating blindly)."""
        with self._conn:
            self._conn.execute(
                "UPDATE conversation_bindings SET conversation_url=?,"
                " conversation_title=COALESCE(?, conversation_title),"
                " browser_target_id=?,"
                " session_id=COALESCE(?, session_id),"
                " conversation_target=COALESCE(?, conversation_target)"
                " WHERE mission_id=?",
                (
                    conversation_url,
                    conversation_title,
                    browser_target_id,
                    session_id,
                    conversation_target or conversation_url,
                    mission_id,
                ),
            )

    def record_policy_decision(
        self,
        record_id: str,
        mission_id: str,
        action_id: str | None,
        tool: str,
        *,
        allowed: bool,
        requires_approval: bool,
        reason: str | None = None,
    ) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO policy_decisions (id, mission_id, action_id, tool,"
                " allowed, requires_approval, reason, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (
                    record_id,
                    mission_id,
                    action_id,
                    tool,
                    1 if allowed else 0,
                    1 if requires_approval else 0,
                    reason,
                    time.time(),
                ),
            )

    def record_approval(
        self,
        record_id: str,
        mission_id: str,
        action_id: str | None,
        tool: str,
        scope: str,
        approved: bool,
    ) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO approvals (id, mission_id, action_id, tool, scope,"
                " approved, decided_at) VALUES (?,?,?,?,?,?,?)",
                (record_id, mission_id, action_id, tool, scope, 1 if approved else 0, time.time()),
            )

    def pending_native_actions(self, mission_id: str) -> list[dict]:
        self.get_mission(mission_id)
        references = {d["record_id"]: d for e in self.rows("transport_events", mission_id)
                      if e["event_type"] == "NATIVE_HOST_REFERENCE"
                      for d in [json.loads(e["detail_json"]) ]}
        return [dict(r, host_reference=references.get(r["id"]))
                for r in self.rows("tool_executions", mission_id)
                if r["tool"].startswith("native:") and r["finished_at"] is None]

    def attach_native_handle(self, mission_id: str, record_id: str,
                             host: str, handle: str) -> dict:
        """Retain an observed opaque host reference, not liveness or authority.

        Receipt after stop is permitted: a launched effect still needs tracking.
        Never use this reference as a PID or silently replace an unknown session.
        """
        if any(not isinstance(v, str) or not v.strip() or len(v) > 512
               or any(ord(c) < 32 or ord(c) == 127 for c in v) for v in (host, handle)):
            raise StoreError("bounded observed host reference required")
        result = {"record_id": record_id, "host": host, "handle": handle,
                  "liveness_verified": False, "evidence_source": "host_observation_supplied"}
        key = "native-host:" + hashlib.sha256(json.dumps([host, handle]).encode()).hexdigest()
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            row = self._conn.execute(
                "SELECT arguments_json FROM tool_executions WHERE id=? AND mission_id=?"
                " AND tool LIKE 'native:%' AND finished_at IS NULL", (record_id, mission_id)
            ).fetchone()
            if row is None or json.loads(row["arguments_json"]).get("__cortex_native_receipt_kind__", "process") != "process":
                raise StoreError("pending native process required")
            existing = [json.loads(e["detail_json"]) for e in self.rows("transport_events", mission_id)
                        if e["event_type"] == "NATIVE_HOST_REFERENCE"]
            for reference in existing:
                if reference["record_id"] == record_id:
                    if reference != result:
                        raise StoreError("host reference is immutable")
                    return reference
            if self._conn.execute("SELECT id FROM transport_events WHERE id=?", (key,)).fetchone():
                raise StoreError("host reference already belongs to an action")
            self._conn.execute(
                "INSERT INTO transport_events (id,mission_id,event_type,detail_json,idempotency_key,created_at)"
                " VALUES (?,?,'NATIVE_HOST_REFERENCE',?,?,?)",
                (key, mission_id, json.dumps(result, sort_keys=True), key, time.time()))
        return result

    def stop_native(self, mission_id: str, reason: str) -> str:
        """Cancel future journaled work; preserve pending effects for inspection."""
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise StoreError("bounded stop reason required")
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            state = self.get_mission(mission_id)["state"]
            if state == "CANCELLED":
                return state
            if "CANCELLED" not in TRANSITIONS[state]:
                raise StoreError("mission already terminal; preserve its verdict")
            self._conn.execute(
                "UPDATE missions SET state='CANCELLED', pause_reason=?,"
                " paused_from_state=NULL, updated_at=? WHERE id=?",
                (reason, time.time(), mission_id),
            )
        return "CANCELLED"

    def define_native_acceptance(self, mission_id: str, criteria: list[dict]) -> dict:
        """Record a fixed pre-work contract, not proof that its checks passed."""
        import re
        if (not isinstance(criteria, list) or not 1 <= len(criteria) <= 64
                or any(not isinstance(c, dict) or set(c) != {"id", "description"}
                       or not isinstance(c["id"], str) or re.fullmatch(r"[A-Za-z0-9_-]{1,80}", c["id"]) is None
                       or not isinstance(c["description"], str) or not c["description"].strip()
                       or len(c["description"]) > 2000 for c in criteria)):
            raise StoreError("invalid acceptance criteria")
        if len({c["id"] for c in criteria}) != len(criteria):
            raise StoreError("duplicate acceptance criterion")
        canonical = json.dumps(criteria, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        result = {"criteria": criteria, "acceptance_sha256": digest,
                  "completion_verified": False, "approval_recorded": False}
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            mission = self.get_mission(mission_id)
            events = self.rows("transport_events", mission_id)
            defined = [e for e in events if e["event_type"] == "NATIVE_ACCEPTANCE_DEFINED"]
            if defined:
                if len(defined) != 1 or json.loads(defined[0]["detail_json"]) != result:
                    raise StoreError("acceptance contract already frozen")
                return result
            if (mission["state"] != "IDLE" or events or self.rows("tool_executions", mission_id)
                    or self.rows("orchestrator_decisions", mission_id)):
                raise StoreError("acceptance must be defined before work")
            key = "native-acceptance:" + mission_id
            self._conn.execute(
                "INSERT INTO transport_events (id,mission_id,event_type,detail_json,idempotency_key,created_at)"
                " VALUES (?,?,'NATIVE_ACCEPTANCE_DEFINED',?,?,?)",
                (key, mission_id, json.dumps(result, sort_keys=True), key, time.time()),
            )
        return result

    def check_native_deadline(self, mission_id: str) -> None:
        """Reject new reservations after the persisted wall-clock deadline.

        Not a process watchdog: already-started effects still need receipts.
        Host clock changes and effects after preparation remain host concerns.
        """
        import math
        mission = self.get_mission(mission_id)
        started = mission["started_at"]
        duration = mission["max_duration_seconds"]
        now = time.time()
        if (not isinstance(started, (int, float)) or not math.isfinite(started)
                or not isinstance(duration, (int, float)) or not math.isfinite(duration)
                or duration <= 0 or now < started or now >= started + duration):
            raise StoreError("native mission time budget exhausted or invalid")

    def reserve_native_action(self, mission_id: str, action_id: str,
                              tool: str, arguments: dict, *, receipt_kind: str = "process",
                              _checked_context: dict | None = None) -> str:
        """Record intent before a host effect. This grants no execution authority.

        Serialize competing reservations with SQLite's writer lock. An unknown
        outcome blocks subsequent actions, even with a different action ID.
        """
        if (not isinstance(action_id, str) or not action_id or len(action_id) > 256
                or not isinstance(tool, str) or not tool or len(tool) > 256
                or not isinstance(arguments, dict) or receipt_kind not in {"process", "host_tool"}):
            raise StoreError("invalid native action")
        envelope = {"__cortex_native_receipt_kind__": receipt_kind, "arguments": arguments}
        if _checked_context is not None:
            envelope["context_binding"] = _checked_context
        payload = json.dumps(envelope, sort_keys=True, allow_nan=False)
        if len(payload.encode()) > 1_000_000:
            raise StoreError("native action arguments too large")
        import uuid
        record_id = str(uuid.uuid4())
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            state = self.get_mission(mission_id)["state"]
            if state in TERMINAL_STATES or state.startswith("PAUSED"):
                raise StoreError("mission stopped or paused")
            self.check_native_deadline(mission_id)
            starts = [e for e in self.rows("transport_events", mission_id, order_by="rowid")
                      if e["event_type"] == "MESSAGE_SEND_STARTED"]
            protected = any((json.loads(e["detail_json"]).get("checkpoint") or {}).get("context")
                            for e in starts)
            if protected or _checked_context is not None:
                from .protocol import validate_decision
                from .artifacts import verify_sources
                if not isinstance(_checked_context, dict) or not starts:
                    raise StoreError("context-bound mission requires checked decision")
                latest = starts[-1]
                context = (json.loads(latest["detail_json"]).get("checkpoint") or {}).get("context")
                if (not isinstance(context, dict) or self.unresolved_outbound(mission_id) is not None
                        or _checked_context.get("send_id") != latest["id"]
                        or _checked_context.get("selection_sha256") != context["selection_sha256"]):
                    raise StoreError("checked context is no longer current")
                mission = self.get_mission(mission_id)
                verify_sources(Path(mission["workspace"]), context["manifest"])
                decision = validate_decision(_checked_context.get("decision"),
                                             expected_mission_id=mission_id,
                                             expected_iteration=mission["iteration"] + 1,
                                             seen_action_ids=self.seen_action_ids(mission_id))
                action = decision.get("action") or {}
                if (decision["state"] not in {"EXECUTE", "REQUEST_CONTEXT"}
                        or decision["actionId"] != action_id or action.get("tool") != tool
                        or action.get("arguments", {}) != arguments):
                    raise StoreError("action differs from checked decision")
                expected_kind = "process" if tool in {"run_process", "run_tests"} else "host_tool"
                if receipt_kind != expected_kind:
                    raise StoreError("receipt kind differs from checked action")
                self._conn.execute(
                    "INSERT INTO orchestrator_decisions"
                    " (id,mission_id,action_id,iteration,decision_json,valid,received_at) VALUES (?,?,?,?,?,1,?)",
                    ("native:" + record_id, mission_id, action_id, decision["iteration"],
                     json.dumps(decision, sort_keys=True), time.time()),
                )
                self._conn.execute("UPDATE missions SET iteration=?,updated_at=? WHERE id=?",
                                   (decision["iteration"], time.time(), mission_id))
            if self.pending_native_actions(mission_id):
                raise StoreError("unresolved native action requires observation, not replay")
            if self._conn.execute(
                "SELECT 1 FROM tool_executions WHERE mission_id=? AND action_id=?",
                (mission_id, action_id),
            ).fetchone():
                raise StoreError("action identity already used; no replay")
            self._conn.execute(
                "INSERT INTO tool_executions (id,mission_id,action_id,tool,arguments_json,started_at)"
                " VALUES (?,?,?,?,?,?)",
                (record_id, mission_id, action_id, "native:" + tool, payload, time.time()),
            )
        return record_id

    def finalize_native(self, mission_id: str, first: dict, second: dict,
                        evidence: list[dict], review: dict) -> dict:
        """Check current proof and persist a native terminal verdict atomically.

        The review and host observations are supplied by the operator, not
        authenticated. SQLite serialization does not lock external file bytes.
        Existing web runner state transitions are not changed by this operation.
        """
        from .native_journal import check_context_reply, check_acceptance_evidence
        import uuid
        if (not isinstance(review, dict) or set(review) != {"reviewer", "criteria"}
                or not isinstance(review["reviewer"], str) or not review["reviewer"].strip()
                or len(review["reviewer"]) > 256 or not isinstance(review["criteria"], list)
                or len(review["criteria"]) > 64):
            raise StoreError("explicit bounded operator review required")
        notes = review["criteria"]
        if any(not isinstance(n, dict) or set(n) != {"criterion_id", "finding"}
               or not isinstance(n["criterion_id"], str) or not isinstance(n["finding"], str)
               or not n["finding"].strip() or len(n["finding"]) > 4000 for n in notes):
            raise StoreError("invalid criterion review")
        with self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            if self.get_mission(mission_id)["state"] != "IDLE":
                raise StoreError("native completion requires an active idle mission")
            self.check_native_deadline(mission_id)
            checked = check_context_reply(self, mission_id, first, second)
            if checked["decision"]["state"] != "COMPLETE":
                raise StoreError("current COMPLETE proposal required")
            acceptance = check_acceptance_evidence(self, mission_id, evidence)
            expected = {e["criterion_id"] for e in acceptance["criteria"]}
            if (acceptance["reported_acceptance"] != "PASS" or len(notes) != len(expected)
                    or {n["criterion_id"] for n in notes} != expected):
                raise StoreError("all criteria require passing proof and semantic review")
            record_id = "native-final:" + str(uuid.uuid4())
            decision = checked["decision"]
            retained = {"context": checked, "acceptance": acceptance, "operator_review": review,
                        "evidence_source": "host_observation_supplied", "approval_recorded": False,
                        "release_eligible": False, "point_in_time_only": True}
            now = time.time()
            self._conn.execute(
                "INSERT INTO orchestrator_decisions"
                " (id,mission_id,action_id,iteration,decision_json,valid,received_at) VALUES (?,?,?,?,?,1,?)",
                (record_id, mission_id, decision["actionId"], decision["iteration"],
                 json.dumps(decision, sort_keys=True), now))
            self._conn.execute(
                "INSERT INTO validation_results (id,mission_id,action_id,passed,checks_json,created_at)"
                " VALUES (?,?,?,1,?,?)",
                (record_id, mission_id, decision["actionId"], json.dumps([retained], sort_keys=True), now))
            self._conn.execute(
                "INSERT INTO transport_events (id,mission_id,event_type,detail_json,created_at)"
                " VALUES (?,?,?, ?,?)",
                (record_id, mission_id, "NATIVE_MISSION_COMPLETED",
                 json.dumps({"validation_id": record_id, "reviewer": review["reviewer"]}), now))
            self._conn.execute("UPDATE missions SET state='COMPLETED',iteration=?,updated_at=? WHERE id=?",
                               (decision["iteration"], now, mission_id))
        return {"state": "COMPLETED", "validation_id": record_id, "completion_recorded": True,
                "approval_recorded": False, "release_eligible": False,
                "evidence_source": "host_observation_supplied", "point_in_time_only": True}

    def finish_native_action(self, mission_id: str, record_id: str,
                             exit_code: int, evidence: dict) -> None:
        """Store an actual supplied host receipt, not independent attestation.

        Timeouts/missing exits cannot settle an action. Completion is immutable;
        even a nonzero exit does not authorize replay of this action identity.
        """
        if type(exit_code) is not int or not isinstance(evidence, dict) or not evidence:
            raise StoreError("actual exit and nonempty evidence required")
        self._settle_native_action(mission_id, record_id, "process", exit_code,
                                   {"evidence": evidence, "outcome": "succeeded" if exit_code == 0 else "failed"})

    def finish_native_tool_action(self, mission_id: str, record_id: str,
                                  outcome: str, tool_result: dict, verification: dict) -> None:
        """Record a supplied non-process tool result without inventing an exit.

        The result and follow-up observations remain caller-supplied evidence.
        Unknown outcomes stay pending. Reservation kind cannot be changed later.
        """
        if (outcome not in {"succeeded", "failed"} or not isinstance(tool_result, dict)
                or not isinstance(verification, dict) or not verification):
            raise StoreError("explicit host outcome, tool result and verification required")
        self._settle_native_action(mission_id, record_id, "host_tool", None,
                                   {"outcome": outcome, "tool_result": tool_result, "verification": verification})

    def _settle_native_action(self, mission_id: str, record_id: str,
                              receipt_kind: str, exit_code: int | None, receipt: dict) -> None:
        result = json.dumps({"evidence_source": "host_observation_supplied", "receipt_kind": receipt_kind,
                             **receipt}, sort_keys=True, allow_nan=False)
        if len(result.encode()) > 1_000_000:
            raise StoreError("native receipt too large")
        with self._conn:
            row = self._conn.execute(
                "SELECT arguments_json FROM tool_executions WHERE id=? AND mission_id=?"
                " AND tool LIKE 'native:%' AND finished_at IS NULL", (record_id, mission_id),
            ).fetchone()
            if row is None or json.loads(row["arguments_json"]).get("__cortex_native_receipt_kind__", "process") != receipt_kind:
                raise StoreError("no pending action with matching receipt kind")
            updated = self._conn.execute(
                "UPDATE tool_executions SET result_json=?,exit_code=?,finished_at=?"
                " WHERE id=? AND mission_id=? AND tool LIKE 'native:%' AND finished_at IS NULL",
                (result, exit_code, time.time(), record_id, mission_id),
            )
            if updated.rowcount != 1:
                raise StoreError("no matching unresolved native action")

    def record_tool_execution(
        self,
        record_id: str,
        mission_id: str,
        action_id: str | None,
        tool: str,
        arguments: dict,
        result: dict | None,
        exit_code: int | None,
        started_at: float,
        finished_at: float | None,
    ) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO tool_executions (id, mission_id, action_id, tool,"
                " arguments_json, result_json, exit_code, started_at, finished_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    record_id,
                    mission_id,
                    action_id,
                    tool,
                    json.dumps(arguments, sort_keys=True),
                    json.dumps(result, sort_keys=True) if result is not None else None,
                    exit_code,
                    started_at,
                    finished_at,
                ),
            )

    def record_validation(
        self,
        record_id: str,
        mission_id: str,
        action_id: str | None,
        passed: bool,
        checks: list[dict],
    ) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO validation_results (id, mission_id, action_id, passed,"
                " checks_json, created_at) VALUES (?,?,?,?,?,?)",
                (
                    record_id,
                    mission_id,
                    action_id,
                    1 if passed else 0,
                    json.dumps(checks, sort_keys=True),
                    time.time(),
                ),
            )

    def record_transport_event(
        self,
        record_id: str,
        mission_id: str,
        event_type: str,
        detail: dict | None = None,
    ) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO transport_events (id, mission_id, event_type, detail_json,"
                " created_at) VALUES (?,?,?,?,?)",
                (record_id, mission_id, event_type, json.dumps(detail or {}), time.time()),
            )

    def record_artifact(
        self,
        record_id: str,
        mission_id: str,
        action_id: str | None,
        name: str,
        path: str | None,
        sha256: str | None,
    ) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO artifacts (id, mission_id, action_id, name, path, sha256,"
                " created_at) VALUES (?,?,?,?,?,?,?)",
                (record_id, mission_id, action_id, name, path, sha256, time.time()),
            )

    # -- introspection (tests / UI) ----------------------------------------------

    def rows(self, table: str, mission_id: str | None = None, order_by: str | None = None) -> list[dict]:
        sql = f"SELECT * FROM {table}"
        params: tuple = ()
        if mission_id is not None:
            sql += " WHERE mission_id = ?"
            params = (mission_id,)
        if order_by is not None:
            sql += f" ORDER BY {order_by}"
        rows = [dict(r) for r in self._conn.execute(sql, params).fetchall()]
        if table == "missions":
            for row in rows:
                row["release_eligible"] = bool(row.get("release_eligible", False))
        return rows

    def table_names(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            " ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]

    def count(self, table: str, mission_id: str | None = None) -> int:
        if mission_id is None:
            row = self._conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
        else:
            row = self._conn.execute(
                f"SELECT COUNT(*) AS c FROM {table} WHERE mission_id = ?", (mission_id,)
            ).fetchone()
        return int(row["c"])
