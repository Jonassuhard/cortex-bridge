import json
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "console"))
import effect_gate as gates
from orchestration.store import Store
from orchestration.effect_schema import upgrade_effect_schema


class BlockedOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        upgrade_effect_schema(self.store._conn)
        self.gate = gates.EffectGate(self.store)
        self.assertTrue(callable(getattr(self.gate, "record_blocked_ownership", None)), "blocked ownership not implemented")
        self.ownership = dict(pid=12345, pgid=12345, startSec=100, startUsec=20, released=False)

    def seed(self, owner="direct_ui", category="sensitive_read", operation="verify_local_alias_access", state="intent"):
        effect_id = str(uuid.uuid4())
        with self.store.transaction_immediate() as conn:
            conn.execute("INSERT INTO effects(id,owner_kind,request_id,action_id,epoch,operation,payload_digest,category,state,authorization_json,intent_json,created_at) VALUES (?,?,?,?,0,?,?,?,?, '{}','{}',100)",
                (effect_id, owner, str(uuid.uuid4()) if owner != "local_alias_action" else None,
                 str(uuid.uuid4()) if owner == "local_alias_action" else None,
                 operation, "a"*64, category, state))
        return effect_id

    def test_only_two_worker_tuples_allow_pre_activation_ownership(self):
        for owner, category, operation in (("direct_ui", "sensitive_read", "verify_local_alias_access"),
                                           ("local_alias_action", "filesystem", "create_directory")):
            effect = self.seed(owner, category, operation)
            self.gate.record_blocked_ownership(effect, self.ownership)
        rows = self.store.effect_rows()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["state"] == "intent" for row in rows))
        self.assertTrue(all(json.loads(row["ownership_json"])["released"] is False for row in rows))

    def test_other_tuples_and_non_intent_are_refused(self):
        for owner, category, operation, state in (("direct_ui","browser","send_message","intent"),
                ("admin_ui","sensitive_read","verify_local_alias_access","intent"),
                ("direct_ui","process","run_process","intent"),
                ("direct_ui","sensitive_read","verify_local_alias_access","active")):
            effect = self.seed(owner, category, operation, state)
            with self.assertRaisesRegex(gates.EffectGateConflict, "EFFECT_CAPABILITY_INVALID"):
                self.gate.record_blocked_ownership(effect, self.ownership)
        self.assertTrue(all(row["ownership_json"] is None for row in self.store.effect_rows()))

    def test_blocked_ownership_is_once_only_and_never_releases(self):
        effect = self.seed()
        self.gate.record_blocked_ownership(effect, self.ownership)
        with self.assertRaises(gates.EffectGateConflict):
            self.gate.record_blocked_ownership(effect, self.ownership)
        with self.assertRaises(gates.EffectGateConflict):
            self.gate.record_blocked_ownership(effect, {**self.ownership, "released": True})
        self.assertFalse(json.loads(self.store.effect_rows()[0]["ownership_json"])["released"])

    def test_extra_fields_and_invalid_identities_never_persist(self):
        effect = self.seed()
        for change in ({"extra":"client"}, {"released":True}, {"pid":True}, {"pid":0},
                       {"pgid":456}, {"startSec":-1}, {"startUsec":1_000_000}):
            with self.subTest(change=change):
                with self.assertRaises(gates.EffectGateConflict):
                    self.gate.record_blocked_ownership(effect, {**self.ownership, **change})
        self.assertIsNone(self.store.effect_rows()[0]["ownership_json"])

    def active_worker_fixture(self):
        # Synthetic capability fixture tests ownership transitions only. This
        # does not prove permit issuance, OS attestation or actual release.
        effect = self.seed()
        self.gate.record_blocked_ownership(effect, self.ownership)
        with self.store.transaction_immediate() as conn:
            conn.execute("UPDATE effects SET state='active',activated_at=101 WHERE id=?", (effect,))
        activation = object.__new__(gates.EffectActivation)
        fields = dict(effect_id=effect, owner_kind="direct_ui", epoch=0,
                      operation="verify_local_alias_access", payload_digest="a"*64,
                      category="sensitive_read", parent_effect_id=None, _authority=self.gate._authority)
        for key, value in fields.items():
            object.__setattr__(activation, key, value)
        return activation

    def test_release_preserves_identity_and_cannot_be_reversed(self):
        activation = self.active_worker_fixture()
        self.gate.record_ownership(activation, {**self.ownership, "released": True})
        saved = json.loads(self.store.effect_rows()[0]["ownership_json"])
        self.assertEqual(saved, dict(pid=12345, pgid=12345, startSec=100, startUsec=20, released=True))
        with self.assertRaises(gates.EffectGateConflict):
            self.gate.record_ownership(activation, self.ownership)

    def test_release_cannot_change_process_identity(self):
        activation = self.active_worker_fixture()
        for changes in ({"pid":456,"pgid":456}, {"startSec":101}, {"startUsec":21}):
            with self.subTest(changes=changes):
                with self.assertRaises(gates.EffectGateConflict):
                    self.gate.record_ownership(activation, {**self.ownership, "released": True, **changes})
        self.assertFalse(json.loads(self.store.effect_rows()[0]["ownership_json"])["released"])


if __name__ == "__main__":
    unittest.main()
