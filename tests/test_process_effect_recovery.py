import hashlib
import os
import json
import uuid
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "console"))
import process_ownership
from startup_lease import _read_kernel_process_identity


class ProcessEffectRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(getattr(process_ownership, "reconcile_process_effect", None)),
                        "Native process effect recovery is missing")

    def spawn(self):
        argv = [sys.executable, "-c", "import sys; sys.stdin.read()"]
        child = subprocess.Popen(argv, stdin=subprocess.PIPE, start_new_session=True)
        def cleanup():
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)
        self.addCleanup(cleanup)
        observed = _read_kernel_process_identity(child.pid)
        self.assertIsNotNone(observed)
        self.assertEqual(observed.pgid, child.pid)
        return child, dict(pid=child.pid, pgid=observed.pgid, start_time=observed.start_time,
                          executable=sys.executable, argv_hash=hashlib.sha256(repr(argv).encode()).hexdigest())

    def test_live_group_is_unclear_then_reaped_group_is_failed_not_successful(self):
        child, ownership = self.spawn()
        result = process_ownership.reconcile_process_effect(ownership)
        self.assertEqual(result.state, "outcome_unclear")
        self.assertIsNone(child.poll())
        child.kill()
        child.wait(timeout=5)
        result = process_ownership.reconcile_process_effect(ownership)
        self.assertEqual(result.state, "failed")
        self.assertEqual(result.error_code, "PROCESS_GROUP_GONE")
        self.assertEqual(result.receipt, {"groupAbsent": True, "leaderAbsent": True})

    def test_permission_error_is_not_process_absence(self):
        _, ownership = self.spawn()
        with patch.object(os, "killpg", side_effect=PermissionError()):
            result = process_ownership.reconcile_process_effect(ownership)
        self.assertEqual(result.state, "outcome_unclear")

    def test_invalid_or_legacy_identity_cannot_be_used_as_quiescence_proof(self):
        _, ownership = self.spawn()
        for change in ({"pid": True}, {"pgid": 0}, {"start_time": "Wed Sep 9"},
                       {"argv_hash": "bad"}, {"release_fd": 7}):
            with self.subTest(change=change):
                result = process_ownership.reconcile_process_effect({**ownership, **change})
                self.assertEqual(result.state, "outcome_unclear")

    def test_absent_group_with_live_leader_is_not_quiescent(self):
        child, ownership = self.spawn()
        # Fault injection: PID existence must still be checked when the group
        # probe says absent, e.g. after a leader changes groups.
        with patch.object(os, "killpg", side_effect=ProcessLookupError()):
            result = process_ownership.reconcile_process_effect(ownership)
        self.assertEqual(result.state, "outcome_unclear")
        self.assertIsNone(child.poll())

    def test_dispatch_observes_real_group_before_file_callback(self):
        from orchestration.store import Store
        from orchestration.effect_schema import upgrade_effect_schema
        from effect_gate import EffectGate, ReconcileResult
        child, ownership = self.spawn()
        store = Store(":memory:")
        self.addCleanup(store.close)
        mission = str(uuid.uuid4())
        store.create_mission(mission, "Fixture", "fixture")
        upgrade_effect_schema(store._conn)
        with store.transaction_immediate() as conn:
            for category, operation, evidence in (("filesystem", "write_file", None),
                                                    ("process", "run_tests", json.dumps(ownership))):
                conn.execute("""INSERT INTO effects(id,owner_kind,mission_id,action_id,epoch,
                    operation,payload_digest,category,state,authorization_json,intent_json,ownership_json,created_at)
                    VALUES (?,'mission',?,?,0,?,?,?,'active','{}','{}',?,1)""",
                    (str(uuid.uuid4()), mission, str(uuid.uuid4()), operation, "a"*64, category, evidence))
        calls = []
        def file_observer(row):
            calls.append(row["id"])
            return ReconcileResult("failed", "FIXTURE_FILE_ABSENT", {})
        observers = {"process": lambda row: process_ownership.reconcile_process_effect(json.loads(row["ownership_json"])),
                     "filesystem": file_observer}
        gate = EffectGate(store)
        self.assertEqual(gate.reconcile_startup(observers).state, "stopping")
        self.assertEqual(calls, [])
        child.kill()
        child.wait(timeout=5)
        status = gate.reconcile_startup(observers)
        self.assertEqual(len(calls), 1)
        self.assertTrue(status.reset_allowed)
        process = next(r for r in store.effect_rows() if r["category"] == "process")
        self.assertEqual(process["error_code"], "PROCESS_GROUP_GONE")


if __name__ == "__main__":
    unittest.main()
