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
    "IDLE": frozenset({"SELECTING_CONVERSATION", "INITIALIZING_MISSION", "CANCELLED"}),
    "SELECTING_CONVERSATION": frozenset({"INITIALIZING_MISSION", "PAUSED", "CANCELLED"}),
    "INITIALIZING_MISSION": frozenset({"SENDING_OBJECTIVE", "FAILED", "CANCELLED"}),
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

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DEFAULT_DB_PATH
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._migrate_conversation_bindings()
        self._migrate_mission_runtime_truth()
        self._recover_interrupted_missions()

    def close(self) -> None:
        self._conn.close()

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
                "UPDATE missions SET state = ?, pause_reason = ?, updated_at = ? "
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
                " iteration, max_iterations, max_duration_seconds, failure_counts,"
                " executor_kind, executor_model_used, runtime_mode, release_eligible,"
                " runtime_observed_at, created_at, started_at, updated_at)"
                " VALUES (?,?,?,?,?,0,?,?,'{}',?,?,?,?,?,?,?,?)",
                (
                    mission_id,
                    objective,
                    workspace,
                    "IDLE",
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
            self._conn.execute(
                "UPDATE missions SET state = ?, pause_reason = ?, updated_at = ? WHERE id = ?",
                (new_state, pause_reason, time.time(), mission_id),
            )
        return new_state

    def resume(self, mission_id: str, target_state: str) -> str:
        """Explicit user-driven resume from PAUSED / PAUSED_RECOVERY_REQUIRED."""
        if target_state not in RUNNING_STATES:
            raise InvalidTransition(f"cannot resume into {target_state}")
        with self._conn:
            row = self._conn.execute(
                "SELECT state FROM missions WHERE id = ?", (mission_id,)
            ).fetchone()
            if row is None:
                raise StoreError(f"unknown mission {mission_id}")
            current = row["state"]
            if current not in RESUMABLE_FROM:
                raise InvalidTransition(f"cannot resume from {current}")
            self._conn.execute(
                "UPDATE missions SET state = ?, pause_reason = NULL, updated_at = ? WHERE id = ?",
                (target_state, time.time(), mission_id),
            )
        return target_state

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
