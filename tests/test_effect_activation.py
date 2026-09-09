import dataclasses
import hashlib
import concurrent.futures
import json
import sqlite3
import sys
import threading
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "console"))
import effect_gate as gates
from orchestration.store import Store
from orchestration.effect_schema import upgrade_effect_schema


class EffectActivationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = str(Path(self.temp.name) / "effects.sqlite3")
        self.store = Store(self.database)
        self.addCleanup(self.store.close)
        self.mission, self.action = str(uuid.uuid4()), str(uuid.uuid4())
        self.store.create_mission(self.mission, "Fixture", "fixture-workspace")
        for state in ("INITIALIZING_MISSION", "SENDING_OBJECTIVE", "WAITING_FOR_CHATGPT", "PARSING_DECISION", "EXECUTING_LOCAL_ACTION"):
            self.store.transition(self.mission, state)
        self.arguments = {"path": "a.txt", "content": "A"}
        self.decision = dict(protocol="cortex.v1", missionId=self.mission, actionId=self.action, iteration=1,
                             state="EXECUTE", summary="Create fixture", action={"tool": "write_file", "arguments": self.arguments},
                             acceptanceCriteria=["File contains A"], requiresApproval=True, terminal=False)
        self.store.record_decision(str(uuid.uuid4()), self.mission, self.action, 1, self.decision, valid=True)
        upgrade_effect_schema(self.store._conn)
        self.gate = gates.EffectGate(self.store)
        self.assertTrue(callable(getattr(self.gate, "activate_mission_effect", None)), "mission activation is not implemented")
        self.challenge = self.gate.register_pending_approval(mission_id=self.mission, action_id=self.action,
                  tool="write_file", arguments=self.arguments, scope="once")
        values = dataclasses.asdict(self.challenge)
        values.pop("tool")
        self.gate.decide_approval(gates.MissionApprovalResponse(**values, approve=True))

    def activate(self, **changes):
        values = dict(mission_id=self.mission, action_id=self.action, epoch=0, operation="write_file",
                      payload_digest=self.challenge.arguments_digest, category="filesystem", approval_required=True)
        return self.gate.activate_mission_effect(**{**values, **changes})

    def prepared_fixture(self):
        activation = self.activate()
        identity = dict(device=1, inode=42, size=1, sha256=hashlib.sha256(b"A").hexdigest())
        ownership = dict(path="a.txt", temporary=f".cortex-{activation.effect_id}.tmp",
                         previous=None, prior=None, expectedSha256=identity["sha256"],
                         parentDevice=1, parentInode=10)
        self.gate.record_ownership(activation, ownership)
        return activation, identity, ownership

    def test_prepared_identity_is_append_only_and_exact_retry_is_safe(self):
        activation, identity, ownership = self.prepared_fixture()
        self.gate.record_prepared_file(activation, identity)
        self.gate.record_prepared_file(activation, identity)
        saved = json.loads(self.store.effect_rows()[0]["ownership_json"])
        self.assertEqual(saved, {**ownership, "prepared": identity})
        # A separate connection must observe committed evidence before success.
        reader = sqlite3.connect(self.database)
        try:
            state, encoded = reader.execute("SELECT state,ownership_json FROM effects WHERE id=?",
                                            (activation.effect_id,)).fetchone()
            self.assertEqual(state, "active")
            self.assertEqual(json.loads(encoded), saved)
        finally:
            reader.close()
        with self.assertRaises(gates.EffectGateConflict):
            self.gate.record_prepared_file(activation, {**identity, "inode": 43})
        with self.assertRaises(gates.EffectGateConflict):
            self.gate.record_ownership(activation, ownership)

    def test_prepared_identity_rejects_invalid_fields_without_mutation(self):
        activation, identity, ownership = self.prepared_fixture()
        for changes in ({"device": 2}, {"inode": True}, {"inode": 0},
                        {"size": -1}, {"size": True}, {"sha256": "0"*64},
                        {"sha256": identity["sha256"].upper()}, {"extra": 1}):
            with self.subTest(changes=changes):
                with self.assertRaises(gates.EffectGateConflict):
                    self.gate.record_prepared_file(activation, {**identity, **changes})
                self.assertEqual(json.loads(self.store.effect_rows()[0]["ownership_json"]), ownership)

    def test_prepared_identity_requires_ownership_and_live_capability(self):
        activation = self.activate()
        identity = dict(device=1, inode=42, size=1, sha256=hashlib.sha256(b"A").hexdigest())
        with self.assertRaises(gates.EffectGateConflict):
            self.gate.record_prepared_file(activation, identity)
        with self.assertRaises(gates.EffectGateConflict):
            self.gate.record_prepared_file(object(), identity)
        self.gate.fail(activation, code="FIXTURE", receipt={})
        with self.assertRaises(gates.EffectGateConflict):
            self.gate.record_prepared_file(activation, identity)

    def test_process_release_consumption_is_durable_and_once_only(self):
        # Replace the unconsumed fixture decision/approval with a process action.
        arguments = {"argv": ["/bin/echo", "fixture"]}
        decision = {**self.decision, "action": {"tool": "run_process", "arguments": arguments}}
        digest = gates.canonical_digest("run_process", arguments)
        with self.store.transaction_immediate() as conn:
            conn.execute("UPDATE orchestrator_decisions SET decision_json=?", (json.dumps(decision),))
            conn.execute("UPDATE approvals SET tool='run_process',arguments_digest=?", (digest,))
        activation = self.activate(operation="run_process", category="process", payload_digest=digest)
        ownership = dict(pid=12345, pgid=12345, start_time="darwin-proc-bsdinfo-v1:100:000001",
                         executable="/bin/echo", argv_hash="a"*64)
        self.assertTrue(callable(getattr(self.gate, "record_process_release", None)),
                        "One-shot durable process release is missing")
        self.gate.record_process_release(activation, ownership)
        with self.assertRaises(gates.EffectGateConflict):
            self.gate.record_process_release(activation, ownership)
        reader = sqlite3.connect(self.database)
        try:
            encoded, authorization = reader.execute("SELECT ownership_json,authorization_json FROM effects").fetchone()
            self.assertEqual(json.loads(encoded), ownership)
            self.assertIs(json.loads(authorization)["process_release_consumed"], True)
        finally:
            reader.close()

    def test_stop_before_activation_refuses_without_consuming_approval(self):
        self.gate.request_stop()
        with self.assertRaisesRegex(gates.EffectGateConflict, "STOP_EPOCH_STALE"):
            self.activate()
        self.assertEqual(self.store.effect_rows(), [])
        self.assertIsNone(self.store.rows("approvals", self.mission)[0]["effect_consumed_at"])

    def test_activation_before_stop_remains_valid_until_terminal(self):
        activation = self.activate()
        stopping = self.gate.request_stop()
        self.assertEqual(stopping.active_effect_count, 1)
        self.gate.assert_activation(activation, owner_kind="mission", category="filesystem", operation="write_file")
        self.assertEqual(self.gate.settle_stop().state, "stopping")
        receipt = self.gate.succeed(activation, {"sha256": "a"*64})
        self.assertEqual((receipt.state, receipt.result["sha256"]), ("succeeded", "a"*64))
        self.assertEqual(self.gate.settle_stop().state, "stopped")

    def test_approval_and_action_cannot_be_consumed_twice(self):
        self.activate()
        with self.assertRaises(gates.EffectGateConflict):
            self.activate()
        self.assertEqual(len(self.store.effect_rows()), 1)
        self.assertIsNotNone(self.store.rows("approvals", self.mission)[0]["effect_consumed_at"])

    def test_changed_digest_or_category_never_activates(self):
        for changes in ({"payload_digest":"0"*64}, {"category":"process"}, {"action_id":str(uuid.uuid4())}):
            with self.subTest(changes=changes):
                with self.assertRaises(gates.EffectGateConflict):
                    self.activate(**changes)
        self.assertEqual(self.store.effect_rows(), [])

    def test_caller_flag_cannot_override_required_approval(self):
        with self.store.transaction_immediate() as conn:
            conn.execute("UPDATE approvals SET decision='denied'")
        with self.assertRaises(gates.EffectGateConflict):
            self.activate(approval_required=False)

    def test_forged_or_other_gate_capability_is_rejected(self):
        with self.assertRaises(TypeError):
            gates.EffectActivation(effect_id="forged")
        activation = self.activate()
        other_gate = gates.EffectGate(self.store)
        with self.assertRaisesRegex(gates.EffectGateConflict, "EFFECT_CAPABILITY_INVALID"):
            other_gate.succeed(activation, {})
        with self.assertRaisesRegex(gates.EffectGateConflict, "EFFECT_CAPABILITY_INVALID"):
            self.gate.succeed(object(), {})
        self.assertEqual(self.store.effect_rows()[0]["state"], "active")

    def test_terminal_result_cannot_be_overwritten(self):
        activation = self.activate()
        self.gate.outcome_unclear(activation, code="WORKER_LOST", receipt={"observed":False})
        with self.assertRaisesRegex(gates.EffectGateConflict, "EFFECT_NOT_ACTIVE"):
            self.gate.succeed(activation, {"pretend":True})
        self.gate.request_stop()
        self.assertFalse(self.gate.settle_stop().reset_allowed)

    def test_paused_mission_cannot_activate(self):
        self.store.transition(self.mission, "PAUSED")
        with self.assertRaisesRegex(gates.EffectGateConflict, "MISSION_ACTION_MISMATCH"):
            self.activate()

    def test_insert_failure_rolls_back_approval_consumption(self):
        with self.store.transaction_immediate() as conn:
            conn.execute("CREATE TEMP TRIGGER reject_effect BEFORE INSERT ON effects BEGIN SELECT RAISE(ABORT, 'fixture insertion failure'); END")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "fixture insertion failure"):
            self.activate()
        self.assertEqual(self.store.effect_rows(), [])
        self.assertIsNone(self.store.rows("approvals", self.mission)[0]["effect_consumed_at"])
        with self.store.transaction_immediate() as conn:
            conn.execute("DROP TRIGGER reject_effect")
        self.activate()
        self.assertEqual(len(self.store.effect_rows()), 1)

    def test_concurrent_activation_has_one_winner(self):
        barrier = threading.Barrier(2)

        def attempt():
            barrier.wait(timeout=5)
            try:
                return self.activate()
            except gates.EffectGateConflict as error:
                return error.code

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: attempt(), range(2)))
        self.assertEqual(sum(type(value) is gates.EffectActivation for value in outcomes), 1)
        self.assertIn("MISSION_EFFECT_ALREADY_EXISTS", outcomes)
        self.assertEqual(len(self.store.effect_rows()), 1)

    def test_ownership_is_durable_and_cannot_be_replaced(self):
        activation = self.activate()
        self.assertTrue(callable(getattr(self.gate, "record_ownership", None)), "ownership persistence not implemented")
        ownership = {"temporary": {"device": 4, "inode": 123}, "sha256": "a"*64}
        self.gate.record_ownership(activation, ownership)
        self.gate.record_ownership(activation, ownership)
        ownership["temporary"]["inode"] = 999
        with self.assertRaisesRegex(gates.EffectGateConflict, "EFFECT_OWNERSHIP_CONFLICT"):
            self.gate.record_ownership(activation, ownership)
        saved = json.loads(self.store.effect_rows()[0]["ownership_json"])
        self.assertEqual(saved["temporary"]["inode"], 123)

    def test_ownership_requires_active_capability_even_after_stop(self):
        activation = self.activate()
        self.assertTrue(callable(getattr(self.gate, "record_ownership", None)), "ownership persistence not implemented")
        with self.assertRaises(gates.EffectGateConflict):
            self.gate.record_ownership(object(), {"inode": 123})
        self.gate.request_stop()
        self.gate.record_ownership(activation, {"inode": 123})
        self.gate.fail(activation, code="FIXTURE_FAILED", receipt={})
        with self.assertRaisesRegex(gates.EffectGateConflict, "EFFECT_NOT_ACTIVE"):
            self.gate.record_ownership(activation, {"inode": 123})

    def test_invalid_ownership_never_persists(self):
        activation = self.activate()
        self.assertTrue(callable(getattr(self.gate, "record_ownership", None)), "ownership persistence not implemented")
        for value in ({}, [], {"bad": float("nan")}, {1: "wrong key"}, {"bad": object()}):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaises((gates.EffectGateConflict, TypeError, ValueError)):
                    self.gate.record_ownership(activation, value)
        self.assertIsNone(self.store.effect_rows()[0]["ownership_json"])


if __name__ == "__main__":
    unittest.main()
