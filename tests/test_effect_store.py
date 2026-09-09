"""EffectGate store interfaces against real isolated SQLite data."""
import unittest

from orchestration.store import Store, StoreError
from orchestration.effect_schema import upgrade_effect_schema


class EffectStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.assertTrue(callable(getattr(self.store, "transaction_immediate", None)), "EffectGate store transaction interface is missing")

    def test_legacy_store_is_not_silently_upgraded(self):
        self.assertEqual(self.store.schema_version, 0)
        with self.assertRaisesRegex(StoreError, "EFFECT_SCHEMA_REQUIRED"):
            self.store.control_row()
        with self.assertRaisesRegex(StoreError, "EFFECT_SCHEMA_REQUIRED"):
            self.store.effect_rows()
        self.assertEqual(self.store.schema_version, 0)

    def test_migrated_control_and_filtered_effects(self):
        upgrade_effect_schema(self.store._conn)
        self.assertEqual(self.store.schema_version, 3)
        self.assertEqual(self.store.control_row()["state"], "inactive")
        with self.store.transaction_immediate() as conn:
            for effect_id, state in (("a", "active"), ("b", "outcome_unclear")):
                conn.execute("INSERT INTO effects(id,owner_kind,request_id,epoch,operation,payload_digest,category,state,authorization_json,intent_json,created_at) VALUES (?,'direct_ui',?,0,'fixture',?,'filesystem',?,'{}','{}',100)", (effect_id,effect_id,"a"*64,state))
        self.assertEqual([row["id"] for row in self.store.effect_rows(states=("active",))], ["a"])
        self.assertEqual([row["id"] for row in self.store.effect_rows()], ["a", "b"])

    def test_transaction_rolls_back_changes_on_error(self):
        upgrade_effect_schema(self.store._conn)
        with self.assertRaisesRegex(RuntimeError, "fixture interruption"):
            with self.store.transaction_immediate() as conn:
                conn.execute("UPDATE control_state SET epoch=7 WHERE singleton=1")
                raise RuntimeError("fixture interruption")
        self.assertEqual(self.store.control_row()["epoch"], 0)
        with self.store.transaction_immediate() as conn:
            conn.execute("UPDATE control_state SET epoch=1 WHERE singleton=1")
        self.assertEqual(self.store.control_row()["epoch"], 1)

    def test_unknown_states_and_sql_fragments_are_rejected(self):
        upgrade_effect_schema(self.store._conn)
        for states in (("made-up",), ("active'); DROP TABLE effects;--",), "active", (None,)):
            with self.subTest(states=states):
                with self.assertRaisesRegex(StoreError, "INVALID_EFFECT_STATES"):
                    self.store.effect_rows(states=states)
        self.assertEqual(self.store.effect_rows(), [])

    def test_nested_transaction_does_not_commit_outer_changes(self):
        upgrade_effect_schema(self.store._conn)
        with self.store.transaction_immediate() as conn:
            conn.execute("UPDATE control_state SET epoch=4 WHERE singleton=1")
            with self.assertRaisesRegex(StoreError, "STORE_TRANSACTION_ACTIVE"):
                with self.store.transaction_immediate():
                    self.fail("nested transaction entered")
            self.assertTrue(conn.in_transaction)
        self.assertEqual(self.store.control_row()["epoch"], 4)


if __name__ == "__main__":
    unittest.main()
