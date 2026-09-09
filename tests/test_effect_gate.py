import dataclasses
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "console"))
from orchestration.store import Store
from orchestration.effect_schema import upgrade_effect_schema
try:
    import effect_gate as gates
except ImportError:
    gates = None


class MissionApprovalGateTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(gates, "durable approval gate not implemented")
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.mission = str(uuid.uuid4())
        self.action = str(uuid.uuid4())
        self.store.create_mission(self.mission, "Fixture", "fixture-workspace")
        upgrade_effect_schema(self.store._conn)
        self.gate = gates.EffectGate(self.store)

    def pending(self, action=None):
        return self.gate.register_pending_approval(mission_id=self.mission, action_id=action or self.action,
                   tool="write_file", arguments={"path": "a.txt", "content": "A"}, scope="once")

    def response(self, challenge, **changes):
        values = dataclasses.asdict(challenge)
        values.pop("tool")
        return gates.MissionApprovalResponse(**{**values, "approve": True, **changes})

    def test_exact_approval_and_single_use_nonce(self):
        challenge = self.pending()
        self.assertEqual(self.pending(), challenge)
        receipt = self.gate.decide_approval(self.response(challenge))
        self.assertTrue(receipt.approved)
        self.assertTrue(receipt.nonce_consumed)
        with self.assertRaises(gates.EffectGateConflict):
            self.gate.decide_approval(self.response(challenge))

    def receipt(self, challenge, **changes):
        self.assertTrue(callable(getattr(self.gate, "approval_receipt", None)), "durable receipt lookup not implemented")
        return self.gate.approval_receipt(**{
            "mission_id": challenge.mission_id, "action_id": challenge.action_id,
            "epoch": challenge.epoch, "arguments_digest": challenge.arguments_digest,
            **changes,
        })

    def test_receipt_pending_is_not_permission(self):
        challenge = self.pending()
        with self.assertRaisesRegex(gates.EffectGateConflict, "APPROVAL_PENDING"):
            self.receipt(challenge)
        self.assertIsNone(self.store.rows("approvals", self.mission)[0]["nonce_consumed_at"])

    def test_receipt_recovers_exact_decision_without_consuming_effect(self):
        challenge = self.pending()
        decided = self.gate.decide_approval(self.response(challenge))
        self.gate = gates.EffectGate(self.store)
        self.assertEqual(self.receipt(challenge), decided)
        self.assertEqual(self.receipt(challenge), decided)
        self.assertIsNone(self.store.rows("approvals", self.mission)[0]["effect_consumed_at"])

    def test_receipt_denial_stays_denied(self):
        challenge = self.pending()
        self.gate.decide_approval(self.response(challenge, approve=False))
        receipt = self.receipt(challenge)
        self.assertFalse(receipt.approved)
        self.assertIsNone(receipt.scope)
        self.assertTrue(receipt.nonce_consumed)

    def test_receipt_wrong_tuple_or_stale_epoch_never_authorizes(self):
        challenge = self.pending()
        self.gate.decide_approval(self.response(challenge))
        for change in ({"mission_id":str(uuid.uuid4())}, {"action_id":str(uuid.uuid4())},
                       {"arguments_digest":"0"*64}, {"epoch":False}, {"epoch":1}):
            with self.subTest(change=change):
                with self.assertRaises(gates.EffectGateConflict):
                    self.receipt(challenge, **change)
        self.gate.request_stop()
        with self.assertRaisesRegex(gates.EffectGateConflict, "STOP_EPOCH_STALE"):
            self.receipt(challenge)

    def test_consumed_effect_receipt_cannot_authorize_another_launch(self):
        challenge = self.pending()
        self.gate.decide_approval(self.response(challenge))
        with self.store.transaction_immediate() as conn:
            conn.execute("UPDATE approvals SET effect_consumed_at=100")
        with self.assertRaisesRegex(gates.EffectGateConflict, "APPROVAL_ALREADY_CONSUMED"):
            self.receipt(challenge)

    def test_delayed_response_cannot_approve_other_action(self):
        first = self.pending()
        second = self.pending(str(uuid.uuid4()))
        with self.assertRaisesRegex(gates.EffectGateConflict, "APPROVAL_MISMATCH"):
            self.gate.decide_approval(self.response(first, action_id=second.action_id))
        self.assertEqual(self.store.rows("approvals", self.mission)[0]["decision"], "pending")

    def test_stop_invalidates_pending_and_approved_unconsumed(self):
        first = self.pending()
        second = self.pending(str(uuid.uuid4()))
        self.gate.decide_approval(self.response(second))
        status = self.gate.request_stop()
        self.assertEqual((status.state, status.epoch), ("stopping", 1))
        self.assertEqual({row["decision"] for row in self.store.rows("approvals", self.mission)}, {"invalidated"})
        with self.assertRaises(gates.EffectGateConflict):
            self.gate.decide_approval(self.response(first))
        with self.assertRaisesRegex(gates.EffectGateConflict, "STOP_EPOCH_STALE"):
            self.pending(str(uuid.uuid4()))

    def test_reset_requires_current_epoch_and_quiescence(self):
        stopped = self.gate.request_stop()
        self.assertEqual(self.gate.settle_stop().state, "stopped")
        with self.assertRaisesRegex(gates.EffectGateConflict, "STOP_RESET_CONFLICT"):
            self.gate.reset_stop(expected_epoch=0)
        reset = self.gate.reset_stop(expected_epoch=stopped.epoch)
        self.assertEqual((reset.state, reset.epoch, reset.accepting_effects), ("inactive", 2, True))

    def test_unknown_outcome_blocks_reset_but_is_not_counted_active(self):
        with self.store.transaction_immediate() as conn:
            conn.execute("INSERT INTO effects(id,owner_kind,request_id,epoch,operation,payload_digest,category,state,authorization_json,intent_json,created_at) VALUES ('e','direct_ui','r',0,'fixture',?,'filesystem','outcome_unclear','{}','{}',100)", ("a"*64,))
        self.gate.request_stop()
        status = self.gate.settle_stop()
        self.assertEqual((status.state, status.active_effect_count, status.outcome_unclear_count, status.reset_allowed), ("stopped", 0, 1, False))
        with self.assertRaisesRegex(gates.EffectGateConflict, "STOP_RESET_CONFLICT"):
            self.gate.reset_stop(expected_epoch=1)

    def test_malformed_approval_never_becomes_truthy_permission(self):
        challenge = self.pending()
        for approve in (1, "yes", None):
            with self.subTest(approve=approve):
                with self.assertRaises(gates.EffectGateConflict):
                    self.gate.decide_approval(self.response(challenge, approve=approve))
        self.assertEqual(self.store.rows("approvals", self.mission)[0]["decision"], "pending")

    def test_digests_are_order_independent_but_operation_bound(self):
        left = gates.canonical_digest("write_file", {"a": 1, "b": 2})
        self.assertEqual(left, gates.canonical_digest("write_file", {"b": 2, "a": 1}))
        self.assertNotEqual(left, gates.canonical_digest("read_file", {"a": 1, "b": 2}))
        with self.assertRaises((TypeError, ValueError)):
            gates.canonical_digest("write_file", {"path": Path("a")})
        with self.assertRaises((TypeError, ValueError)):
            gates.canonical_digest("write_file", {"value": float("nan")})


if __name__ == "__main__":
    unittest.main()
