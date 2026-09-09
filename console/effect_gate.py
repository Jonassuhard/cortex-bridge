"""Staged durable approval/STOP coordinator; not yet wired to HTTP routes.

Mission capabilities are staged here. Direct/local-alias effects, ownership
and startup reconciliation must land before runtime enablement.
"""
from dataclasses import dataclass
import hashlib
import json
import re
import secrets
import time
import uuid

from orchestration.store import Store
from orchestration import protocol


class EffectGateConflict(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True, init=False)
class EffectActivation:
    effect_id: str
    owner_kind: str
    epoch: int
    operation: str
    payload_digest: str
    category: str
    parent_effect_id: str | None
    _authority: object

    def __init__(self, *args, **kwargs):
        raise TypeError("EffectActivation is issued only by EffectGate")


@dataclass(frozen=True, slots=True)
class EffectReceipt:
    effect_id: str
    state: str
    epoch: int
    operation: str
    payload_digest: str
    result: dict
    error_code: str | None


@dataclass(frozen=True, slots=True)
class MissionApprovalChallenge:
    mission_id: str
    action_id: str
    epoch: int
    arguments_digest: str
    nonce: str
    tool: str
    scope: str


@dataclass(frozen=True, slots=True)
class MissionApprovalResponse:
    mission_id: str
    action_id: str
    epoch: int
    arguments_digest: str
    nonce: str
    scope: str
    approve: bool


@dataclass(frozen=True, slots=True)
class MissionApprovalReceipt:
    approved: bool
    mission_id: str
    action_id: str
    epoch: int
    arguments_digest: str
    scope: str | None
    nonce_consumed: bool


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    state: str
    error_code: str | None
    receipt: dict


@dataclass(frozen=True, slots=True)
class StopStatus:
    schema_version: int
    state: str
    epoch: int
    accepting_effects: bool
    active_effect_count: int
    outcome_unclear_count: int
    reset_allowed: bool
    updated_at: float

    def to_public(self):
        return dict(schemaVersion=self.schema_version, state=self.state, epoch=self.epoch,
                    acceptingEffects=self.accepting_effects, activeEffectCount=self.active_effect_count,
                    outcomeUnclearCount=self.outcome_unclear_count, resetAllowed=self.reset_allowed,
                    updatedAt=self.updated_at)


def _json_value(value):
    if type(value) is dict:
        if any(type(k) is not str for k in value):
            raise TypeError("JSON object keys must be strings")
        for item in value.values():
            _json_value(item)
    elif type(value) is list:
        for item in value:
            _json_value(item)
    elif value is not None and type(value) not in (bool, int, float, str):
        raise TypeError("JSON value required")


def canonical_digest(operation: str, payload: dict) -> str:
    if type(operation) is not str or not operation.strip() or type(payload) is not dict:
        raise TypeError("Operation and JSON payload required")
    _json_value(payload)
    encoded = json.dumps({"operation": operation, "payload": payload}, ensure_ascii=False,
                         allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _identity(value):
    try:
        if type(value) is not str or str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, AttributeError):
        raise EffectGateConflict("APPROVAL_MISMATCH") from None


def _blocked_worker_tuple(row):
    return (row["owner_kind"], row["category"], row["operation"]) in (
        ("local_alias_action", "filesystem", "create_directory"),
        ("direct_ui", "sensitive_read", "verify_local_alias_access"),
    )


def _worker_identity(ownership):
    if type(ownership) is not dict or set(ownership) != {"pid", "pgid", "startSec", "startUsec", "released"}:
        raise EffectGateConflict("EFFECT_CAPABILITY_INVALID")
    if (any(type(ownership[k]) is not int for k in ("pid", "pgid", "startSec", "startUsec"))
            or ownership["pid"] <= 0 or ownership["pgid"] != ownership["pid"]
            or ownership["startSec"] < 0 or not 0 <= ownership["startUsec"] < 1_000_000
            or type(ownership["released"]) is not bool):
        raise EffectGateConflict("EFFECT_CAPABILITY_INVALID")


class EffectGate:
    def __init__(self, store: Store):
        if store.schema_version != 3:
            raise EffectGateConflict("EFFECT_SCHEMA_REQUIRED")
        self.store = store
        self._authority = object()

    def _status(self, conn):
        row = conn.execute("SELECT * FROM control_state WHERE singleton=1").fetchone()
        if row is None:
            raise EffectGateConflict("EFFECT_CONTROL_MISSING")
        active = conn.execute("SELECT count(*) FROM effects WHERE state='active' OR (state='intent' AND ownership_json IS NOT NULL)").fetchone()[0]
        unclear = conn.execute("SELECT count(*) FROM effects WHERE state='outcome_unclear'").fetchone()[0]
        return StopStatus(1, row["state"], row["epoch"], row["state"] == "inactive", active, unclear,
                          row["state"] == "stopped" and active == 0 and unclear == 0, row["updated_at"])

    def status(self):
        with self.store.transaction_immediate() as conn:
            return self._status(conn)

    def register_pending_approval(self, *, mission_id, action_id, tool, arguments, scope):
        _identity(mission_id)
        _identity(action_id)
        if scope not in ("once", "tool-for-mission", "all-writes-for-mission"):
            raise EffectGateConflict("APPROVAL_MISMATCH")
        digest = canonical_digest(tool, arguments)
        with self.store.transaction_immediate() as conn:
            status = self._status(conn)
            if not status.accepting_effects:
                raise EffectGateConflict("STOP_EPOCH_STALE")
            if conn.execute("SELECT id FROM missions WHERE id=?", (mission_id,)).fetchone() is None:
                raise EffectGateConflict("APPROVAL_MISMATCH")
            row = conn.execute("SELECT * FROM approvals WHERE owner_kind='mission' AND mission_id=? AND action_id=? AND epoch=?", (mission_id, action_id, status.epoch)).fetchone()
            if row:
                if (row["tool"], row["scope"], row["arguments_digest"], row["decision"]) != (tool, scope, digest, "pending"):
                    raise EffectGateConflict("APPROVAL_MISMATCH")
                nonce = row["nonce"]
            else:
                nonce = secrets.token_urlsafe(32)
                conn.execute("INSERT INTO approvals(id,owner_kind,mission_id,action_id,tool,epoch,arguments_digest,nonce,scope,decision,created_at) VALUES (?,'mission',?,?,?,?,?,?,?,'pending',?)",
                             (str(uuid.uuid4()), mission_id, action_id, tool, status.epoch, digest, nonce, scope, time.time()))
            return MissionApprovalChallenge(mission_id, action_id, status.epoch, digest, nonce, tool, scope)

    def decide_approval(self, response):
        if type(response) is not MissionApprovalResponse or type(response.approve) is not bool or type(response.epoch) is not int or response.epoch < 0:
            raise EffectGateConflict("APPROVAL_MISMATCH")
        _identity(response.mission_id)
        _identity(response.action_id)
        if type(response.nonce) is not str or re.fullmatch(r"[A-Za-z0-9_-]{43}", response.nonce) is None or type(response.arguments_digest) is not str or re.fullmatch(r"[0-9a-f]{64}", response.arguments_digest) is None:
            raise EffectGateConflict("APPROVAL_MISMATCH")
        with self.store.transaction_immediate() as conn:
            status = self._status(conn)
            row = conn.execute("SELECT * FROM approvals WHERE nonce=?", (response.nonce,)).fetchone()
            expected = ("mission", response.mission_id, response.action_id, response.epoch, response.arguments_digest, response.scope, "pending", None)
            if not row or tuple(row[k] for k in ("owner_kind", "mission_id", "action_id", "epoch", "arguments_digest", "scope", "decision", "nonce_consumed_at")) != expected:
                raise EffectGateConflict("APPROVAL_MISMATCH")
            if not status.accepting_effects or response.epoch != status.epoch:
                raise EffectGateConflict("STOP_EPOCH_STALE")
            now = time.time()
            conn.execute("UPDATE approvals SET decision=?,nonce_consumed_at=?,decided_at=? WHERE id=?",
                         ("approved" if response.approve else "denied", now, now, row["id"]))
            return MissionApprovalReceipt(response.approve, response.mission_id, response.action_id,
                                          response.epoch, response.arguments_digest,
                                          response.scope if response.approve else None, True)

    def approval_receipt(self, *, mission_id, action_id, epoch, arguments_digest):
        """Read the exact durable decision; a UI wake-up is not authorization.

        Lookup never consumes an effect. Activation must still recheck the
        decision and STOP epoch atomically immediately before execution.
        """
        _identity(mission_id)
        _identity(action_id)
        if (type(epoch) is not int or epoch < 0 or type(arguments_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", arguments_digest) is None):
            raise EffectGateConflict("APPROVAL_MISMATCH")
        with self.store.transaction_immediate() as conn:
            status = self._status(conn)
            if not status.accepting_effects or status.epoch != epoch:
                raise EffectGateConflict("STOP_EPOCH_STALE")
            row = conn.execute(
                "SELECT * FROM approvals WHERE owner_kind='mission' AND mission_id=? AND action_id=? AND epoch=? AND arguments_digest=?",
                (mission_id, action_id, epoch, arguments_digest),
            ).fetchone()
            if row is None or row["decision"] == "invalidated":
                raise EffectGateConflict("APPROVAL_MISMATCH")
            if row["decision"] == "pending":
                raise EffectGateConflict("APPROVAL_PENDING")
            if row["decision"] not in ("approved", "denied") or row["nonce_consumed_at"] is None or row["decided_at"] is None:
                raise EffectGateConflict("APPROVAL_MISMATCH")
            if row["effect_consumed_at"] is not None:
                raise EffectGateConflict("APPROVAL_ALREADY_CONSUMED")
            approved = row["decision"] == "approved"
            return MissionApprovalReceipt(approved, mission_id, action_id, epoch,
                                          arguments_digest, row["scope"] if approved else None, True)

    def activate_mission_effect(self, *, mission_id, action_id, epoch, operation,
                                payload_digest, category, approval_required,
                                parent_effect_id=None):
        _identity(mission_id)
        _identity(action_id)
        if type(epoch) is not int or epoch < 0 or type(approval_required) is not bool:
            raise EffectGateConflict("MISSION_ACTION_MISMATCH")
        categories = {name: "filesystem" for name in protocol.TOOL_ARGUMENTS}
        for name in ("run_process", "run_tests", "git_status", "git_diff"):
            categories[name] = "process"
        if operation not in categories or categories[operation] != category:
            raise EffectGateConflict("MISSION_ACTION_MISMATCH")
        with self.store.transaction_immediate() as conn:
            status = self._status(conn)
            if not status.accepting_effects or epoch != status.epoch:
                raise EffectGateConflict("STOP_EPOCH_STALE")
            mission = conn.execute("SELECT state,iteration FROM missions WHERE id=?", (mission_id,)).fetchone()
            if not mission or mission["state"] != "EXECUTING_LOCAL_ACTION":
                raise EffectGateConflict("MISSION_ACTION_MISMATCH")
            rows = conn.execute("SELECT action_id,decision_json FROM orchestrator_decisions WHERE mission_id=? AND iteration=? AND valid=1", (mission_id, mission["iteration"] + 1)).fetchall()
            if len(rows) != 1 or rows[0]["action_id"] != action_id:
                raise EffectGateConflict("MISSION_ACTION_MISMATCH")
            try:
                decision = protocol.validate_decision(json.loads(rows[0]["decision_json"]),
                             expected_mission_id=mission_id, expected_iteration=mission["iteration"] + 1,
                             seen_action_ids=[])
                action = decision["action"]
                if decision["actionId"] != action_id or action["tool"] != operation or canonical_digest(operation, action["arguments"]) != payload_digest:
                    raise ValueError()
            except (ValueError, TypeError, KeyError, protocol.DecisionError):
                raise EffectGateConflict("MISSION_ACTION_MISMATCH") from None
            if conn.execute("SELECT id FROM effects WHERE owner_kind='mission' AND mission_id=? AND action_id=?", (mission_id, action_id)).fetchone():
                raise EffectGateConflict("MISSION_EFFECT_ALREADY_EXISTS")
            if parent_effect_id is not None:
                _identity(parent_effect_id)
                parent = conn.execute("SELECT id FROM effects WHERE id=? AND owner_kind='mission' AND mission_id=? AND epoch=? AND state='active'", (parent_effect_id, mission_id, epoch)).fetchone()
                if parent is None:
                    raise EffectGateConflict("PARENT_EFFECT_INVALID")
            now = time.time()
            authorization = {"required": approval_required or decision["requiresApproval"]}
            if authorization["required"]:
                row = conn.execute("SELECT * FROM approvals WHERE owner_kind='mission' AND mission_id=? AND action_id=? AND epoch=? AND arguments_digest=?", (mission_id, action_id, epoch, payload_digest)).fetchone()
                if not row or row["tool"] != operation or row["decision"] != "approved" or row["nonce_consumed_at"] is None or row["effect_consumed_at"] is not None:
                    raise EffectGateConflict("APPROVAL_MISMATCH")
                conn.execute("UPDATE approvals SET effect_consumed_at=? WHERE id=?", (now, row["id"]))
                authorization["approval_id"] = row["id"]
            effect_id = str(uuid.uuid4())
            conn.execute("INSERT INTO effects(id,owner_kind,mission_id,action_id,epoch,operation,payload_digest,parent_effect_id,category,state,authorization_json,intent_json,created_at,activated_at) VALUES (?,'mission',?,?,?,?,?,?,?,'active',?,?,?,?)",
                         (effect_id, mission_id, action_id, epoch, operation, payload_digest, parent_effect_id, category,
                          json.dumps(authorization, sort_keys=True), json.dumps({"action_id":action_id}), now, now))
            activation = object.__new__(EffectActivation)
            for key, value in dict(effect_id=effect_id, owner_kind="mission", epoch=epoch,
                                   operation=operation, payload_digest=payload_digest, category=category,
                                   parent_effect_id=parent_effect_id, _authority=self._authority).items():
                object.__setattr__(activation, key, value)
            return activation

    def _assert_activation(self, conn, activation, *, owner_kind, category, operation):
        if type(activation) is not EffectActivation or getattr(activation, "_authority", None) is not self._authority:
            raise EffectGateConflict("EFFECT_CAPABILITY_INVALID")
        row = conn.execute("SELECT * FROM effects WHERE id=?", (activation.effect_id,)).fetchone()
        if not row or row["state"] != "active":
            raise EffectGateConflict("EFFECT_NOT_ACTIVE")
        fields = ("owner_kind", "epoch", "operation", "payload_digest", "category", "parent_effect_id")
        if any(row[k] != getattr(activation, k) for k in fields) or (owner_kind, category, operation) != (row["owner_kind"], row["category"], row["operation"]):
            raise EffectGateConflict("EFFECT_CAPABILITY_INVALID")
        return row

    def assert_activation(self, activation, *, owner_kind, category, operation):
        with self.store.transaction_immediate() as conn:
            self._assert_activation(conn, activation, owner_kind=owner_kind, category=category, operation=operation)

    def record_blocked_ownership(self, effect_id, ownership):
        """Persist the runner's blocked identity; never spawn or release a worker.

        The installed runner must attest this identity against the OS. This
        method only enforces the durable tuple and shape, not that OS proof.
        """
        _worker_identity(ownership)
        if ownership["released"] is not False:
            raise EffectGateConflict("EFFECT_CAPABILITY_INVALID")
        encoded = json.dumps(ownership, sort_keys=True, allow_nan=False)
        with self.store.transaction_immediate() as conn:
            row = conn.execute("SELECT * FROM effects WHERE id=?", (effect_id,)).fetchone()
            if not row or not _blocked_worker_tuple(row) or row["state"] != "intent" or row["ownership_json"] is not None:
                raise EffectGateConflict("EFFECT_CAPABILITY_INVALID")
            conn.execute("UPDATE effects SET ownership_json=? WHERE id=?", (encoded, effect_id))

    def record_ownership(self, activation, ownership):
        """Bind observations to an active capability without replacing identity."""
        if type(activation) is not EffectActivation:
            raise EffectGateConflict("EFFECT_CAPABILITY_INVALID")
        if type(ownership) is not dict or not ownership:
            raise EffectGateConflict("EFFECT_OWNERSHIP_CONFLICT")
        _json_value(ownership)
        encoded = json.dumps(ownership, ensure_ascii=False, allow_nan=False, sort_keys=True)
        with self.store.transaction_immediate() as conn:
            row = self._assert_activation(conn, activation, owner_kind=activation.owner_kind,
                                          category=activation.category, operation=activation.operation)
            if _blocked_worker_tuple(row):
                _worker_identity(ownership)
                if row["ownership_json"] is None:
                    raise EffectGateConflict("EFFECT_CAPABILITY_INVALID")
                previous = json.loads(row["ownership_json"])
                _worker_identity(previous)
                if (previous["released"] is not False or ownership["released"] is not True
                        or any(previous[k] != ownership[k] for k in ("pid", "pgid", "startSec", "startUsec"))):
                    raise EffectGateConflict("EFFECT_CAPABILITY_INVALID")
            elif row["ownership_json"] is not None:
                if json.loads(row["ownership_json"]) != json.loads(encoded):
                    raise EffectGateConflict("EFFECT_OWNERSHIP_CONFLICT")
                return
            conn.execute("UPDATE effects SET ownership_json=? WHERE id=?", (encoded, activation.effect_id))

    def record_process_release(self, activation, ownership):
        """Commit one process ownership/release reservation; never signal here."""
        if (type(activation) is not EffectActivation
                or activation.operation not in ("run_process", "run_tests", "git_status", "git_diff")):
            raise EffectGateConflict("EFFECT_CAPABILITY_INVALID")
        if (type(ownership) is not dict
                or set(ownership) != {"pid", "pgid", "start_time", "executable", "argv_hash"}
                or type(ownership["pid"]) is not int or ownership["pid"] <= 0
                or type(ownership["pgid"]) is not int or ownership["pgid"] != ownership["pid"]
                or type(ownership["start_time"]) is not str
                or re.fullmatch(r"darwin-proc-bsdinfo-v1:[1-9][0-9]*:[0-9]{6}", ownership["start_time"]) is None
                or type(ownership["executable"]) is not str or not ownership["executable"].startswith("/")
                or type(ownership["argv_hash"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", ownership["argv_hash"]) is None):
            raise EffectGateConflict("EFFECT_OWNERSHIP_CONFLICT")
        with self.store.transaction_immediate() as conn:
            row = self._assert_activation(conn, activation, owner_kind="mission",
                                          category="process", operation=activation.operation)
            authorization = json.loads(row["authorization_json"])
            if "process_release_consumed" in authorization:
                raise EffectGateConflict("PROCESS_RELEASE_ALREADY_CONSUMED")
            if row["ownership_json"] is not None and json.loads(row["ownership_json"]) != ownership:
                raise EffectGateConflict("EFFECT_OWNERSHIP_CONFLICT")
            authorization["process_release_consumed"] = True
            conn.execute("UPDATE effects SET ownership_json=?,authorization_json=? WHERE id=?",
                         (json.dumps(ownership, sort_keys=True), json.dumps(authorization, sort_keys=True),
                          activation.effect_id))

    def record_prepared_file(self, activation, identity):
        """Append a prepared write identity once, before publication.

        The executor supplies descriptor observations; this does not itself
        attest a file or authorize a rename. Existing ownership is immutable.
        """
        if type(activation) is not EffectActivation:
            raise EffectGateConflict("EFFECT_CAPABILITY_INVALID")
        if (type(identity) is not dict
                or set(identity) != {"device", "inode", "size", "sha256"}
                or any(type(identity[k]) is not int for k in ("device", "inode", "size"))
                or identity["device"] < 0 or identity["inode"] <= 0 or identity["size"] < 0
                or type(identity["sha256"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", identity["sha256"]) is None):
            raise EffectGateConflict("EFFECT_PREPARED_IDENTITY_INVALID")
        with self.store.transaction_immediate() as conn:
            row = self._assert_activation(conn, activation, owner_kind="mission",
                                          category="filesystem", operation="write_file")
            ownership = json.loads(row["ownership_json"]) if row["ownership_json"] else None
            required = {"path", "temporary", "previous", "prior", "expectedSha256",
                        "parentDevice", "parentInode"}
            if (type(ownership) is not dict
                    or set(ownership) not in (required, required | {"prepared"})
                    or ownership["temporary"] != f".cortex-{activation.effect_id}.tmp"
                    or type(ownership["parentDevice"]) is not int
                    or type(ownership["parentInode"]) is not int
                    or ownership["parentInode"] <= 0
                    or identity["device"] != ownership["parentDevice"]
                    or identity["sha256"] != ownership["expectedSha256"]):
                raise EffectGateConflict("EFFECT_OWNERSHIP_CONFLICT")
            if "prepared" in ownership:
                if ownership["prepared"] != identity:
                    raise EffectGateConflict("EFFECT_OWNERSHIP_CONFLICT")
                return
            ownership["prepared"] = dict(identity)
            conn.execute("UPDATE effects SET ownership_json=? WHERE id=?",
                         (json.dumps(ownership, sort_keys=True, ensure_ascii=False, allow_nan=False),
                          activation.effect_id))

    def _terminal(self, activation, state, receipt, code):
        if type(activation) is not EffectActivation:
            raise EffectGateConflict("EFFECT_CAPABILITY_INVALID")
        if type(receipt) is not dict or (code is not None and (type(code) is not str or not code.strip())):
            raise EffectGateConflict("INVALID_EFFECT_RECEIPT")
        _json_value(receipt)
        encoded = json.dumps(receipt, ensure_ascii=False, allow_nan=False, sort_keys=True)
        with self.store.transaction_immediate() as conn:
            row = self._assert_activation(conn, activation, owner_kind=activation.owner_kind,
                                          category=activation.category, operation=activation.operation)
            conn.execute("UPDATE effects SET state=?,receipt_json=?,error_code=?,finished_at=? WHERE id=?",
                         (state, encoded, code, time.time(), activation.effect_id))
            return EffectReceipt(row["id"], state, row["epoch"], row["operation"], row["payload_digest"], json.loads(encoded), code)

    def succeed(self, activation, receipt):
        return self._terminal(activation, "succeeded", receipt, None)

    def fail(self, activation, *, code, receipt):
        return self._terminal(activation, "failed", receipt, code)

    def outcome_unclear(self, activation, *, code, receipt):
        return self._terminal(activation, "outcome_unclear", receipt, code)

    def reconcile_startup(self, reconcilers):
        """Reconcile interrupted effects before runtime admission.

        Caller must own the startup lease and exclude live runners. Callbacks
        are read-only observations, never execution/retry/cleanup functions.
        Only the implemented write observer is admitted at this stage.
        """
        with self.store.transaction_immediate() as conn:
            rows = [dict(row) for row in conn.execute(
                "SELECT * FROM effects WHERE state IN ('intent','active') ORDER BY created_at,id")]
            status = self._status(conn)
            if not rows and status.outcome_unclear_count == 0:
                return status
            now = time.time()
            if status.state == "inactive":
                conn.execute("UPDATE control_state SET epoch=epoch+1,state='stopping',stop_requested_at=?,updated_at=? WHERE singleton=1",
                             (now, now))
            conn.execute("UPDATE approvals SET decision='invalidated' WHERE decision IN ('pending','approved') AND effect_consumed_at IS NULL")
        # Account for native groups before reading files they could still
        # mutate. A live/unknown observation stays pending, allowing a later
        # startup pass to observe actual exit without replaying the command.
        process_observer = reconcilers.get("process")
        for original in rows:
            if (original["state"] != "active" or original["owner_kind"] != "mission"
                    or original["category"] != "process"
                    or original["operation"] not in ("run_process", "run_tests", "git_status", "git_diff")
                    or not callable(process_observer)):
                continue
            try:
                observation = process_observer(dict(original))
                if (type(observation) is not ReconcileResult
                        or observation.state != "failed" or observation.error_code != "PROCESS_GROUP_GONE"
                        or type(observation.receipt) is not dict
                        or set(observation.receipt) != {"groupAbsent", "leaderAbsent"}
                        or observation.receipt["groupAbsent"] is not True
                        or observation.receipt["leaderAbsent"] is not True):
                    continue
            except Exception:
                continue
            with self.store.transaction_immediate() as conn:
                current = conn.execute("SELECT * FROM effects WHERE id=?", (original["id"],)).fetchone()
                if current is None or dict(current) != original:
                    raise EffectGateConflict("RECOVERY_EFFECT_CHANGED")
                conn.execute("UPDATE effects SET state='failed',receipt_json=?,error_code='PROCESS_GROUP_GONE',finished_at=? WHERE id=?",
                             (json.dumps(observation.receipt, sort_keys=True), time.time(), original["id"]))
        with self.store.transaction_immediate() as conn:
            rows = [dict(row) for row in conn.execute(
                "SELECT * FROM effects WHERE state IN ('intent','active') ORDER BY created_at,id")]
            possible_worker = conn.execute("""
                SELECT 1 FROM effects
                WHERE (state='intent' AND ownership_json IS NOT NULL)
                   OR (state IN ('active','outcome_unclear') AND
                       (category='process' OR
                        (owner_kind='local_alias_action' AND category='filesystem' AND operation='create_directory') OR
                        (owner_kind='direct_ui' AND category='sensitive_read' AND operation='verify_local_alias_access')))
                LIMIT 1
            """).fetchone()
            if possible_worker is not None:
                # A live or unaccounted-for worker can invalidate every file
                # observation. Keep write evidence pending until its actual
                # process reconciler proves quiescence; never infer exit here.
                conn.execute("UPDATE control_state SET state='stopping',updated_at=? WHERE singleton=1", (now,))
                return self._status(conn)
        for original in rows:
            result = ReconcileResult("outcome_unclear", "RECOVERY_EVIDENCE_UNAVAILABLE", {})
            if original["state"] == "intent" and original["ownership_json"] is None:
                result = ReconcileResult("failed", "RECOVERY_INTENT_CANCELLED", {})
            elif (original["state"] == "active"
                  and (original["owner_kind"], original["category"], original["operation"])
                  == ("mission", "filesystem", "write_file")):
                try:
                    callback = reconcilers.get("filesystem")
                    candidate = callback(dict(original)) if callable(callback) else None
                    if (type(candidate) is not ReconcileResult
                            or candidate.state not in ("succeeded", "failed", "outcome_unclear")
                            or type(candidate.receipt) is not dict
                            or (candidate.state == "succeeded" and candidate.error_code is not None)
                            or (candidate.state != "succeeded" and
                                (type(candidate.error_code) is not str or not candidate.error_code.strip()))):
                        raise ValueError("Invalid recovery observation")
                    _json_value(candidate.receipt)
                    json.dumps(candidate.receipt, allow_nan=False)
                    result = candidate
                except Exception:
                    # Never persist exception strings, paths or provider data.
                    result = ReconcileResult("outcome_unclear", "RECOVERY_OBSERVATION_FAILED", {})
            encoded = json.dumps(result.receipt, ensure_ascii=False, sort_keys=True, allow_nan=False)
            with self.store.transaction_immediate() as conn:
                current = conn.execute("SELECT * FROM effects WHERE id=?", (original["id"],)).fetchone()
                if current is None or dict(current) != original:
                    raise EffectGateConflict("RECOVERY_EFFECT_CHANGED")
                conn.execute("UPDATE effects SET state=?,receipt_json=?,error_code=?,finished_at=? WHERE id=?",
                             (result.state, encoded, result.error_code, time.time(), original["id"]))
        return self.settle_stop()

    def request_stop(self):
        with self.store.transaction_immediate() as conn:
            now = time.time()
            conn.execute("UPDATE control_state SET epoch=epoch+1,state='stopping',stop_requested_at=?,stopped_at=NULL,updated_at=? WHERE singleton=1", (now, now))
            conn.execute("UPDATE approvals SET decision='invalidated' WHERE decision IN ('pending','approved') AND effect_consumed_at IS NULL")
            return self._status(conn)

    def settle_stop(self):
        with self.store.transaction_immediate() as conn:
            status = self._status(conn)
            if status.state == "stopping" and status.active_effect_count == 0:
                now = time.time()
                conn.execute("UPDATE control_state SET state='stopped',stopped_at=?,updated_at=? WHERE singleton=1", (now, now))
            return self._status(conn)

    def reset_stop(self, *, expected_epoch):
        with self.store.transaction_immediate() as conn:
            status = self._status(conn)
            if type(expected_epoch) is not int or expected_epoch != status.epoch or not status.reset_allowed:
                raise EffectGateConflict("STOP_RESET_CONFLICT")
            now = time.time()
            conn.execute("UPDATE control_state SET state='resetting',epoch=epoch+1,updated_at=? WHERE singleton=1", (now,))
            conn.execute("UPDATE approvals SET decision='invalidated' WHERE decision IN ('pending','approved') AND effect_consumed_at IS NULL")
            conn.execute("UPDATE control_state SET state='inactive',reset_at=?,updated_at=? WHERE singleton=1", (now, now))
            return self._status(conn)
