import json
import tempfile
import unittest
from pathlib import Path

from orchestration.store import Store, StoreError


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "fixture.db"
        self.store = Store(self.path)
        self.addCleanup(lambda: self.store.close())
        self.store.create_mission("mission-a", "Build a fictional site", "fixture-workspace")
        self.store.transition("mission-a", "PAUSED")
        self.assertTrue(callable(getattr(self.store, "save_context_checkpoint", None)), "durable context checkpoints not implemented")
        self.context = dict(constraints=["No external assets"], decisions=["Use inline CSS"], open_questions=[], next_action="Verify mobile layout")

    def save(self, checkpoint_id="cp-a", context=None, expected=None):
        return self.store.save_context_checkpoint(checkpoint_id, "mission-a", self.context if context is None else context,
                    expected_source_digest=self.store.context_source_digest("mission-a") if expected is None else expected)

    def test_context_survives_reopen_without_resuming(self):
        self.save()
        self.store.close()
        self.store = Store(self.path)
        result = self.store.load_context_checkpoint("cp-a", "mission-a")
        self.assertEqual(result["context"]["next_action"], "Verify mobile layout")
        self.assertTrue(result["source_current"])
        self.assertEqual(self.store.get_mission("mission-a")["state"], "PAUSED")

    def test_stale_save_does_not_write_event(self):
        old = self.store.context_source_digest("mission-a")
        self.store.set_iteration("mission-a", 1)
        with self.assertRaisesRegex(StoreError, "CONTEXT_SOURCE_CHANGED"):
            self.save(expected=old)
        self.assertEqual(self.store.count("transport_events", "mission-a"), 0)

    def test_later_tool_activity_invalidates_checkpoint(self):
        self.save()
        self.store.record_tool_execution("tool-1", "mission-a", "action-1", "write_file", {}, None, None, 100, None)
        self.assertFalse(self.store.load_context_checkpoint("cp-a", "mission-a")["source_current"])

    def test_exact_retry_is_idempotent(self):
        first = self.save()
        second = self.save()
        self.assertEqual(first, second)
        self.assertEqual(self.store.count("transport_events", "mission-a"), 1)

    def test_id_reuse_cannot_replace_context(self):
        self.save()
        with self.assertRaisesRegex(StoreError, "CONTEXT_ID_CONFLICT"):
            self.save(context={**self.context, "next_action": "Different"})
        self.assertEqual(self.store.load_context_checkpoint("cp-a", "mission-a")["context"]["next_action"], "Verify mobile layout")

    def test_invalid_context_never_persists(self):
        for context in ({**self.context, "permission": "all"}, {**self.context, "constraints": "none"}, {**self.context, "next_action": "x" * 65536}, {**self.context, "decisions": [True]}):
            with self.subTest(context_keys=list(context)):
                with self.assertRaisesRegex(StoreError, "INVALID_CONTEXT"):
                    self.save(context=context)
        self.assertEqual(self.store.count("transport_events", "mission-a"), 0)

    def test_cross_mission_checkpoint_cannot_be_read(self):
        self.save()
        self.store.create_mission("mission-b", "Other", "other-workspace")
        with self.assertRaisesRegex(StoreError, "CONTEXT_NOT_FOUND"):
            self.store.load_context_checkpoint("cp-a", "mission-b")

    def test_altered_context_is_rejected(self):
        self.save()
        row = self.store.rows("transport_events", "mission-a")[0]
        data = json.loads(row["detail_json"])
        data["context"]["next_action"] = "Tampered"
        with self.store._conn:
            self.store._conn.execute("UPDATE transport_events SET detail_json=? WHERE id=?", (json.dumps(data), "cp-a"))
        with self.assertRaisesRegex(StoreError, "CONTEXT_INTEGRITY_ERROR"):
            self.store.load_context_checkpoint("cp-a", "mission-a")

    def test_running_mission_cannot_checkpoint(self):
        self.store.resume("mission-a", "INITIALIZING_MISSION")
        with self.assertRaisesRegex(StoreError, "MISSION_NOT_PAUSED"):
            self.save()

    def test_additional_checkpoint_does_not_invalidate_prior_source(self):
        self.save()
        self.save("cp-b")
        self.assertTrue(self.store.load_context_checkpoint("cp-a", "mission-a")["source_current"])

    def test_unknown_schema_is_rejected_even_with_matching_digest(self):
        import hashlib
        self.save()
        row = self.store.rows("transport_events", "mission-a")[0]
        data = json.loads(row["detail_json"])
        data["schema_version"] = 2
        body = {k: v for k, v in data.items() if k != "digest"}
        data["digest"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        with self.store._conn:
            self.store._conn.execute("UPDATE transport_events SET detail_json=? WHERE id=?", (json.dumps(data), "cp-a"))
        with self.assertRaisesRegex(StoreError, "CONTEXT_INTEGRITY_ERROR"):
            self.store.load_context_checkpoint("cp-a", "mission-a")

    def test_mutating_input_after_save_cannot_change_stored_context(self):
        self.save()
        self.context["constraints"].append("Different instruction")
        self.assertEqual(self.store.load_context_checkpoint("cp-a", "mission-a")["context"]["constraints"], ["No external assets"])

    def test_other_mission_activity_does_not_invalidate_context(self):
        self.save()
        self.store.create_mission("mission-b", "Other", "other-workspace")
        self.assertTrue(self.store.load_context_checkpoint("cp-a", "mission-a")["source_current"])

    def test_transport_ambiguity_invalidates_context(self):
        self.save()
        self.store.record_transport_event("transport-1", "mission-a", "delivery.unclear", {})
        self.assertFalse(self.store.load_context_checkpoint("cp-a", "mission-a")["source_current"])

    def test_failed_checkpoint_does_not_leave_transaction_open(self):
        with self.assertRaisesRegex(StoreError, "CONTEXT_SOURCE_CHANGED"):
            self.save(expected="0" * 64)
        self.save()
        self.assertTrue(self.store.load_context_checkpoint("cp-a", "mission-a")["source_current"])

    def test_nested_transaction_is_not_committed_by_checkpoint(self):
        self.store._conn.execute("BEGIN")
        try:
            with self.assertRaisesRegex(StoreError, "CONTEXT_TRANSACTION_ACTIVE"):
                self.store.context_source_digest("mission-a")
            self.assertTrue(self.store._conn.in_transaction)
        finally:
            self.store._conn.rollback()

    def test_v3_stop_and_effect_changes_invalidate_context(self):
        from orchestration.effect_schema import upgrade_effect_schema
        upgrade_effect_schema(self.store._conn)
        self.save()
        with self.store.transaction_immediate() as conn:
            conn.execute("UPDATE control_state SET epoch=epoch+1")
        self.assertFalse(self.store.load_context_checkpoint("cp-a", "mission-a")["source_current"])
        self.save("cp-b")
        with self.store.transaction_immediate() as conn:
            conn.execute("INSERT INTO effects(id,owner_kind,mission_id,action_id,epoch,operation,payload_digest,category,state,authorization_json,intent_json,created_at) VALUES ('e','mission','mission-a','a',1,'write_file',?,'filesystem','outcome_unclear','{}','{}',100)", ("a"*64,))
        self.assertFalse(self.store.load_context_checkpoint("cp-b", "mission-a")["source_current"])

    def test_other_mission_effect_does_not_invalidate_context(self):
        from orchestration.effect_schema import upgrade_effect_schema
        upgrade_effect_schema(self.store._conn)
        self.store.create_mission("mission-b", "Other", "other-workspace")
        self.save()
        with self.store.transaction_immediate() as conn:
            conn.execute("INSERT INTO effects(id,owner_kind,mission_id,action_id,epoch,operation,payload_digest,category,state,authorization_json,intent_json,created_at) VALUES ('e','mission','mission-b','a',0,'write_file',?,'filesystem','active','{}','{}',100)", ("a"*64,))
        self.assertTrue(self.store.load_context_checkpoint("cp-a", "mission-a")["source_current"])


if __name__ == "__main__":
    unittest.main()
