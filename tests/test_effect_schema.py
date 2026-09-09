"""Staged migration tests; never open the installed runtime database."""
import sqlite3
import tempfile
from pathlib import Path
import unittest

from orchestration.store import Store
try:
    from orchestration import effect_schema
except ImportError:
    effect_schema = None


class EffectSchemaTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.conn = self.store._conn
        self.store.create_mission("m", "Fixture objective", "fixture-workspace")
        self.store.record_approval("old", "m", "a", "write_file", "once", True)
        self.assertIsNotNone(effect_schema, "staged effect migration is missing")

    def test_legacy_approval_is_retained_but_not_promoted(self):
        before = tuple(self.conn.execute("SELECT * FROM approvals").fetchone())
        effect_schema.upgrade_effect_schema(self.conn)
        self.assertEqual(tuple(self.conn.execute("SELECT * FROM approvals_legacy_v1").fetchone()), before)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM approvals").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 3)
        self.assertEqual([r[0] for r in self.conn.execute("SELECT version FROM schema_migrations ORDER BY version")], [2, 3])
        row = self.conn.execute("SELECT epoch,state FROM control_state").fetchone()
        self.assertEqual(tuple(row), (0, "inactive"))

    def test_repeating_upgrade_is_idempotent(self):
        effect_schema.upgrade_effect_schema(self.conn)
        before = list(self.conn.iterdump())
        effect_schema.upgrade_effect_schema(self.conn)
        self.assertEqual(list(self.conn.iterdump()), before)

    def test_durability_and_integrity_are_enabled(self):
        effect_schema.upgrade_effect_schema(self.conn)
        self.assertEqual(self.conn.execute("PRAGMA synchronous").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_future_version_is_not_modified(self):
        self.conn.execute("PRAGMA user_version=99")
        before = list(self.conn.iterdump())
        with self.assertRaisesRegex(effect_schema.MigrationReviewRequired, "MIGRATION_REVIEW_REQUIRED"):
            effect_schema.upgrade_effect_schema(self.conn)
        self.assertEqual(list(self.conn.iterdump()), before)

    def test_partial_legacy_schema_is_not_repaired_implicitly(self):
        self.conn.execute("ALTER TABLE approvals ADD COLUMN unexpected TEXT")
        before = list(self.conn.iterdump())
        with self.assertRaises(effect_schema.MigrationReviewRequired):
            effect_schema.upgrade_effect_schema(self.conn)
        self.assertEqual(list(self.conn.iterdump()), before)

    def test_all_rebuild_failpoints_restore_original_database(self):
        before = list(self.conn.iterdump())
        for failure in ("approvals_count_mismatch", "approvals_digest_mismatch", "effects_count_mismatch", "effects_digest_mismatch", "interrupt_immediately_before_approvals_swap", "interrupt_immediately_before_effects_swap"):
            with self.subTest(failure=failure):
                with self.assertRaises(effect_schema.MigrationReviewRequired):
                    effect_schema.upgrade_effect_schema(self.conn, migration_failpoint=failure)
                self.assertEqual(list(self.conn.iterdump()), before)
                self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 0)

    def test_direct_request_identity_is_unique_across_admin_and_ui(self):
        effect_schema.upgrade_effect_schema(self.conn)
        sql = "INSERT INTO effects (id,owner_kind,request_id,epoch,operation,payload_digest,category,state,authorization_json,intent_json,created_at) VALUES (?,?,?,0,'fixture',?,'filesystem','intent','{}','{}',100)"
        with self.conn:
            self.conn.execute(sql, ("e1", "direct_ui", "r1", "a"*64))
        with self.assertRaises(sqlite3.IntegrityError), self.conn:
            self.conn.execute(sql, ("e2", "admin_ui", "r1", "b"*64))

    def test_invalid_effect_owner_category_and_subject_are_rejected(self):
        effect_schema.upgrade_effect_schema(self.conn)
        sql = "INSERT INTO effects (id,owner_kind,mission_id,request_id,epoch,operation,payload_digest,category,state,authorization_json,intent_json,created_at) VALUES ('e',?,?,?,0,'fixture',?,?,?,'{}','{}',100)"
        for owner, mission, request, category, state in (("unknown",None,"r","filesystem","intent"), ("mission",None,None,"filesystem","intent"), ("direct_ui","m","r","filesystem","intent"), ("admin_ui",None,"r","unknown","intent"), ("direct_ui",None,"r","filesystem","unknown")):
            with self.subTest(owner=owner,category=category,state=state):
                with self.assertRaises(sqlite3.IntegrityError), self.conn:
                    self.conn.execute(sql, (owner,mission,request,"a"*64,category,state))

    def seed_v2(self):
        # v2 fixture uses the staging DDL; row values and expected preservation
        # are independently asserted below, including self-referential effects.
        with self.conn:
            effect_schema._v1_to_v2(self.conn, 10)
            self.conn.execute("INSERT INTO approvals(id,mission_id,action_id,tool,epoch,arguments_digest,nonce,scope,decision,created_at) VALUES ('current','m','a','write_file',0,?,'nonce','once','approved',10)", ("a"*64,))
            self.conn.execute("INSERT INTO effects(id,owner_kind,mission_id,action_id,epoch,operation,payload_digest,category,state,authorization_json,intent_json,created_at) VALUES ('parent','mission','m','a',0,'fixture',?,'filesystem','succeeded','{}','{}',10)", ("b"*64,))
            self.conn.execute("INSERT INTO effects(id,owner_kind,mission_id,action_id,epoch,operation,payload_digest,parent_effect_id,category,state,authorization_json,intent_json,created_at) VALUES ('child','mission','m','b',0,'fixture',?,'parent','filesystem','outcome_unclear','{}','{}',11)", ("c"*64,))

    def test_nonempty_v2_preserves_effects_and_approval_fields(self):
        self.seed_v2()
        effects = [tuple(r) for r in self.conn.execute("SELECT * FROM effects ORDER BY id")]
        columns = [r[1] for r in self.conn.execute("PRAGMA table_info(approvals)")]
        approvals = [tuple(r) for r in self.conn.execute("SELECT * FROM approvals ORDER BY id")]
        effect_schema.upgrade_effect_schema(self.conn)
        self.assertEqual([tuple(r) for r in self.conn.execute("SELECT * FROM effects ORDER BY id")], effects)
        self.assertEqual([tuple(r) for r in self.conn.execute("SELECT " + ",".join(columns) + " FROM approvals ORDER BY id")], approvals)
        self.assertEqual(tuple(self.conn.execute("SELECT owner_kind,local_action_id FROM approvals").fetchone()), ("mission", None))

    def test_v2_failure_preserves_nonempty_database_exactly(self):
        self.seed_v2()
        before = list(self.conn.iterdump())
        for failpoint in ("approvals_count_mismatch", "approvals_digest_mismatch", "effects_count_mismatch", "effects_digest_mismatch", "interrupt_immediately_before_approvals_swap", "interrupt_immediately_before_effects_swap"):
            with self.subTest(failpoint=failpoint):
                with self.assertRaises(effect_schema.MigrationReviewRequired):
                    effect_schema.upgrade_effect_schema(self.conn, migration_failpoint=failpoint)
                self.assertEqual(list(self.conn.iterdump()), before)
                self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_unknown_v2_owner_is_not_promoted(self):
        self.seed_v2()
        self.conn.execute("PRAGMA ignore_check_constraints=ON")
        with self.conn:
            self.conn.execute("UPDATE effects SET owner_kind='future_owner' WHERE id='child'")
        self.conn.execute("PRAGMA ignore_check_constraints=OFF")
        before = list(self.conn.iterdump())
        with self.assertRaises(effect_schema.MigrationReviewRequired):
            effect_schema.upgrade_effect_schema(self.conn)
        self.assertEqual(list(self.conn.iterdump()), before)

    def test_missing_v3_unique_index_is_not_accepted_as_ready(self):
        effect_schema.upgrade_effect_schema(self.conn)
        self.conn.execute("DROP INDEX effects_direct_request")
        before = list(self.conn.iterdump())
        with self.assertRaises(effect_schema.MigrationReviewRequired):
            effect_schema.upgrade_effect_schema(self.conn)
        self.assertEqual(list(self.conn.iterdump()), before)

    def test_missing_control_state_is_not_accepted_as_ready(self):
        effect_schema.upgrade_effect_schema(self.conn)
        with self.conn:
            self.conn.execute("DELETE FROM control_state")
        with self.assertRaises(effect_schema.MigrationReviewRequired):
            effect_schema.upgrade_effect_schema(self.conn)

    def test_file_database_reopens_with_preserved_parent_graph(self):
        self.seed_v2()
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "migration-fixture.db"
            destination = sqlite3.connect(path)
            try:
                self.conn.backup(destination)
                effect_schema.upgrade_effect_schema(destination)
            finally:
                destination.close()
            reopened = sqlite3.connect(path)
            try:
                effect_schema.upgrade_effect_schema(reopened)
                self.assertEqual(reopened.execute("SELECT parent_effect_id,state FROM effects WHERE id='child'").fetchone(), ("parent", "outcome_unclear"))
                self.assertEqual(reopened.execute("SELECT count(*) FROM approvals_legacy_v1").fetchone()[0], 1)
                self.assertEqual(reopened.execute("PRAGMA foreign_key_check").fetchall(), [])
            finally:
                reopened.close()

    def test_caller_cannot_disable_migration_check_constraints(self):
        self.seed_v2()
        self.conn.execute("PRAGMA ignore_check_constraints=ON")
        with self.conn:
            self.conn.execute("UPDATE effects SET owner_kind='future_owner' WHERE id='child'")
        with self.assertRaises(effect_schema.MigrationReviewRequired):
            effect_schema.upgrade_effect_schema(self.conn)
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
