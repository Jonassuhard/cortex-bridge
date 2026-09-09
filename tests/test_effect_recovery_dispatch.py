import json
import tempfile
import unittest
import uuid
from pathlib import Path

from effect_gate import EffectGate, ReconcileResult, EffectGateConflict
from orchestration.store import Store
from orchestration.effect_schema import upgrade_effect_schema


class RecoveryDispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "effects.sqlite3")
        self.store = Store(self.path)
        self.addCleanup(self.store.close)
        self.mission = str(uuid.uuid4())
        self.store.create_mission(self.mission, "Fixture", "fixture")
        upgrade_effect_schema(self.store._conn)
        self.gate = EffectGate(self.store)
        self.assertTrue(callable(getattr(self.gate, "reconcile_startup", None)),
                        "Startup reconciliation is not implemented")

    def seed(self, state="active", operation="write_file", ownership=None):
        effect = str(uuid.uuid4())
        with self.store.transaction_immediate() as conn:
            conn.execute("""INSERT INTO effects(id,owner_kind,mission_id,action_id,epoch,
              operation,payload_digest,category,state,authorization_json,intent_json,ownership_json,created_at)
              VALUES (?,'mission',?,?,0,?,?,'filesystem',?,'{}','{}',?,1)""",
              (effect, self.mission, str(uuid.uuid4()), operation, "a"*64, state,
               json.dumps(ownership) if ownership is not None else None))
        return effect

    def test_barrier_is_durable_before_callback_and_terminal_is_not_replayed(self):
        self.seed()
        calls = []
        def observe(row):
            other = Store(self.path)
            try:
                self.assertFalse(EffectGate(other).status().accepting_effects)
            finally:
                other.close()
            calls.append(row["id"])
            return ReconcileResult("succeeded", None, {"verified": True})
        status = self.gate.reconcile_startup({"filesystem": observe})
        self.assertEqual(status.state, "stopped")
        self.assertTrue(status.reset_allowed)
        self.assertEqual(self.store.effect_rows()[0]["state"], "succeeded")
        self.gate.reconcile_startup({"filesystem": observe})
        self.assertEqual(len(calls), 1)

    def test_unknown_and_invalid_results_remain_unclear_and_block_reset(self):
        for result in (None, ReconcileResult("succeeded", "contradiction", {}),
                       ReconcileResult("succeeded", None, {"invalid": float("nan")})):
            self.seed()
            status = self.gate.reconcile_startup({"filesystem": lambda row: result})
            self.assertFalse(status.reset_allowed)
            self.assertEqual(self.store.effect_rows()[-1]["state"], "outcome_unclear")
        self.seed(operation="unknown")
        def must_not_run(row):
            self.fail("Unknown operation reached a reconciler")
        self.gate.reconcile_startup({"filesystem": must_not_run})
        self.assertTrue(all(r["state"] == "outcome_unclear" for r in self.store.effect_rows()))

    def test_intent_without_ownership_cancels_without_callback(self):
        self.seed(state="intent")
        self.gate.reconcile_startup({})
        self.assertEqual(self.store.effect_rows()[0]["state"], "failed")
        self.assertTrue(self.gate.status().reset_allowed)

    def test_missing_reconciler_or_exception_is_unclear(self):
        self.seed()
        self.gate.reconcile_startup({})
        self.seed()
        def broken(row):
            raise OSError("private error must not enter receipt")
        self.gate.reconcile_startup({"filesystem": broken})
        for row in self.store.effect_rows():
            self.assertEqual(row["state"], "outcome_unclear")
            self.assertNotIn("private", row["receipt_json"])

    def test_clean_start_does_not_change_epoch_or_stop(self):
        before = self.gate.status()
        after = self.gate.reconcile_startup({})
        self.assertEqual(before, after)

    def test_concurrent_terminal_receipt_is_never_overwritten(self):
        effect = self.seed()
        def racing_observer(row):
            with self.store.transaction_immediate() as conn:
                conn.execute("UPDATE effects SET state='failed',receipt_json='{}',error_code='OTHER_WRITER',finished_at=2 WHERE id=?", (effect,))
            return ReconcileResult("succeeded", None, {})
        with self.assertRaisesRegex(EffectGateConflict, "RECOVERY_EFFECT_CHANGED"):
            self.gate.reconcile_startup({"filesystem": racing_observer})
        self.assertEqual(self.store.effect_rows()[0]["error_code"], "OTHER_WRITER")
        self.assertFalse(self.gate.status().accepting_effects)

    def test_interruption_keeps_barrier_and_new_store_can_finish(self):
        self.seed()
        def interrupted(row):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.gate.reconcile_startup({"filesystem": interrupted})
        self.assertEqual(self.store.effect_rows()[0]["state"], "active")
        self.assertFalse(self.gate.status().accepting_effects)
        reopened = Store(self.path)
        try:
            recovered = EffectGate(reopened).reconcile_startup({
                "filesystem": lambda row: ReconcileResult("failed", "OBSERVED_ABSENT", {})})
            self.assertEqual(recovered.state, "stopped")
            self.assertTrue(recovered.reset_allowed)
        finally:
            reopened.close()

    def test_owned_intent_cannot_be_declared_safely_cancelled(self):
        self.seed(state="intent", ownership={"pid": 12345})
        status = self.gate.reconcile_startup({})
        self.assertEqual(self.store.effect_rows()[0]["state"], "intent")
        self.assertEqual(status.state, "stopping")
        self.assertFalse(status.reset_allowed)
        self.assertEqual(self.gate.settle_stop().state, "stopping")
        with self.assertRaises(EffectGateConflict):
            self.gate.reset_stop(expected_epoch=status.epoch)

    def test_possible_worker_prevents_file_observation_until_terminal(self):
        write = self.seed()
        worker = self.seed(operation="run_tests", ownership={"pid": 12345})
        with self.store.transaction_immediate() as conn:
            conn.execute("UPDATE effects SET category='process' WHERE id=?", (worker,))
        observed = []
        def observe(row):
            observed.append(row["id"])
            return ReconcileResult("succeeded", None, {})
        for state in ("active", "outcome_unclear"):
            with self.store.transaction_immediate() as conn:
                conn.execute("UPDATE effects SET state=? WHERE id=?", (state, worker))
            status = self.gate.reconcile_startup({"filesystem": observe})
            self.assertEqual(observed, [])
            self.assertEqual(status.state, "stopping")
            rows = {r["id"]: r for r in self.store.effect_rows()}
            self.assertEqual(rows[write]["state"], "active")
        # A terminal worker receipt here is fixture evidence only; actual
        # process reconciliation must prove quiescence before storing it.
        with self.store.transaction_immediate() as conn:
            conn.execute("UPDATE effects SET state='failed',receipt_json='{}',error_code='FIXTURE_QUIESCENT',finished_at=2 WHERE id=?", (worker,))
        status = self.gate.reconcile_startup({"filesystem": observe})
        self.assertEqual(observed, [write])
        self.assertTrue(status.reset_allowed)

    def test_process_success_or_truthy_receipt_never_unlocks_file_recovery(self):
        self.seed()
        worker = self.seed(operation="run_tests", ownership={"pid": 12345})
        with self.store.transaction_immediate() as conn:
            conn.execute("UPDATE effects SET category='process' WHERE id=?", (worker,))
        calls = []
        for result in (ReconcileResult("succeeded", None, {}),
                       ReconcileResult("failed", "PROCESS_GROUP_GONE", {"groupAbsent": 1, "leaderAbsent": True})):
            self.gate.reconcile_startup({
                "process": lambda row: result,
                "filesystem": lambda row: calls.append(row["id"])})
            self.assertEqual(calls, [])
            self.assertTrue(all(row["state"] == "active" for row in self.store.effect_rows()))


if __name__ == "__main__":
    unittest.main()
