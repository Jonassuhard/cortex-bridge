"""Durable reservations; supplied receipts are not independently attested."""
import tempfile
from pathlib import Path
import unittest
from orchestration.store import Store, StoreError


class NativeActionTests(unittest.TestCase):
    def test_host_receipt_preserves_null_exit_and_kind_cannot_change(self):
        import json
        record = self.store.reserve_native_action("m", "patch", "apply_patch", {"file": "x"}, receipt_kind="host_tool")
        with self.assertRaises(StoreError):
            self.store.finish_native_action("m", record, 0, {"fake_exit": True})
        for outcome, result, verification in (("unknown", {}, {"file": True}),
                                               ("succeeded", None, {"file": True}),
                                               ("succeeded", {}, {})):
            with self.assertRaises(StoreError):
                self.store.finish_native_tool_action("m", record, outcome, result, verification)
        self.assertEqual(len(self.store.pending_native_actions("m")), 1)
        self.store.finish_native_tool_action("m", record, "succeeded", {}, {"file_sha256": "observed-fixture-hash"})
        row = self.store.rows("tool_executions", "m")[0]
        self.assertIsNone(row["exit_code"])
        self.assertEqual(json.loads(row["result_json"])["outcome"], "succeeded")
        self.assertEqual(self.store.pending_native_actions("m"), [])
        process = self.reserve(action="process")
        with self.assertRaises(StoreError):
            self.store.finish_native_tool_action("m", process, "succeeded", {}, {"file": True})

    def test_process_exits_after_real_effect_before_receipt(self):
        import json
        import subprocess
        import sys
        target = self.path.parent / "effect.txt"
        code = '''
import os, sys
from pathlib import Path
from orchestration.store import Store
store = Store(sys.argv[1], recover_interrupted=False)
store.reserve_native_action("m", "crash-action", "fixture-write", {"path": "effect.txt"})
with Path(sys.argv[2]).open("x") as f:
    f.write("one actual execution")
    f.flush()
    os.fsync(f.fileno())
os._exit(17)
'''
        run = subprocess.run([sys.executable, "-c", code, str(self.path), str(target)],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 17, run.stderr)
        self.assertEqual(target.read_text(), "one actual execution")
        pending = self.store.pending_native_actions("m")
        self.assertEqual(len(pending), 1)
        with self.assertRaises(StoreError):
            self.reserve(action="replacement")
        # Observe the real process exit and filesystem; do not execute it again.
        self.store.finish_native_action("m", pending[0]["id"], run.returncode,
                                        {"file_content": target.read_text(), "process_exit": run.returncode})
        result = json.loads(self.store.rows("tool_executions", "m")[0]["result_json"])
        self.assertEqual(result["evidence_source"], "host_observation_supplied")
        self.assertEqual(self.store.pending_native_actions("m"), [])

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "actions.db"
        self.store = Store(self.path, recover_interrupted=False)
        self.addCleanup(self.store.close)
        self.store.create_mission("m", "test", tmp.name)

    def reserve(self, store=None, action="a"):
        return (store or self.store).reserve_native_action("m", action, "host-tool", {"path": "fixture.txt"})

    def test_reopen_and_changed_action_cannot_bypass_pending(self):
        receipt = self.reserve()
        other = Store(self.path, recover_interrupted=False)
        self.addCleanup(other.close)
        self.assertEqual(other.pending_native_actions("m")[0]["id"], receipt)
        for action in ("a", "different"):
            with self.assertRaises(StoreError):
                self.reserve(other, action)
        other.finish_native_action("m", receipt, 0, {"observed": "file exists"})
        self.assertEqual(other.pending_native_actions("m"), [])
        with self.assertRaises(StoreError):
            self.reserve(other)
        with self.assertRaises(StoreError):
            other.finish_native_action("m", receipt, 0, {"changed": True})
        self.reserve(other, "next")

    def test_expired_mission_refuses_new_action_after_reopen(self):
        self.store.create_mission('expired', 'test', str(self.path.parent),
                                  started_at=1, max_duration_seconds=1)
        other = Store(self.path, recover_interrupted=False)
        self.addCleanup(other.close)
        with self.assertRaises(StoreError):
            other.reserve_native_action('expired', 'a', 'test', {})
        self.assertEqual(other.rows('tool_executions', 'expired'), [])

    def test_deadline_does_not_prevent_recording_existing_receipt(self):
        receipt = self.reserve()
        with self.store._conn:
            self.store._conn.execute('UPDATE missions SET started_at=1 WHERE id=?', ('m',))
        self.store.finish_native_action('m', receipt, 0, {'observed': 'completed'})
        self.assertEqual(self.store.pending_native_actions('m'), [])
        with self.assertRaises(StoreError):
            self.reserve(action='after-deadline')

    def test_wrong_mission_cannot_settle_and_failure_is_not_retry_permission(self):
        receipt = self.reserve()
        self.store.create_mission("other", "test", str(self.path.parent))
        with self.assertRaises(StoreError):
            self.store.finish_native_action("other", receipt, 0, {"observed": True})
        self.assertEqual(len(self.store.pending_native_actions("m")), 1)
        self.store.finish_native_action("m", receipt, 1, {"stderr": "actual failure"})
        with self.assertRaises(StoreError):
            self.reserve()

    def test_paused_and_invalid_receipts_rejected(self):
        receipt = self.reserve()
        for code, evidence in ((True, {"a": 1}), (None, {"a": 1}), (0, {})):
            with self.assertRaises(StoreError):
                self.store.finish_native_action("m", receipt, code, evidence)
        self.store.finish_native_action("m", receipt, 0, {"observed": "done"})
        self.store.transition("m", "PAUSED")
        with self.assertRaises(StoreError):
            self.reserve(action="next")
