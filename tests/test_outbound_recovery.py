"""Runner/store integration; simulated transport, never a live delivery proof."""
import tempfile
import unittest
from pathlib import Path

from orchestration.runner import TransportOrchestratorClient
from orchestration.store import Store
from transport.chatgpt_web.adapter import TransportError


class RecordingTransport:
    lock = None

    def __init__(self, messages, fail=False, fail_before=False):
        self.messages = messages
        self.fail = fail
        self.fail_before = fail_before

    async def outbound_checkpoint(self):
        return {"conversation_id": "fixture", "last_message_id": "anchor", "message_count": 1}

    async def reconcile_outbound(self, checkpoint, send_id):
        if not self.messages:
            raise TransportError("DELIVERY_UNCERTAIN", "no receipt")
        return {"id": "user-1", "role": "user", "text": self.messages[0]}

    async def send_message(self, message, **kwargs):
        if self.fail_before:
            raise TransportError("PRE_DELIVERY_NOT_READY", "composer not ready; no send")
        self.messages.append(message)
        if self.fail:
            raise TransportError("DELIVERY_UNCERTAIN", "simulated acknowledgement loss")
        return {"id": "user-1", "role": "user", "text": message}

    async def await_response(self):
        return {"id": "assistant-1", "protocol_text": "observed response"}


class OutboundRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def test_competing_different_payloads_allow_only_one_reservation(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from orchestration.store import StoreError
        barrier = threading.Barrier(2)

        class CoordinatedStore(Store):
            def rows(inner, table, *args, **kwargs):
                result = super().rows(table, *args, **kwargs)
                if table == 'transport_events':
                    # Force the former read-before-write race. With a writer
                    # lock, only one reader enters; timeout releases it safely.
                    try:
                        barrier.wait(timeout=0.5)
                    except threading.BrokenBarrierError:
                        pass
                return result

        def reserve(index):
            store = CoordinatedStore(self.path, recover_interrupted=False)
            try:
                store.reserve_outbound(f'race-{index}', 'mission-1', f'payload-{index}')
                return 'prepared'
            except StoreError:
                return 'refused'
            finally:
                store.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, (1, 2)))
        self.assertCountEqual(results, ['prepared', 'refused'])
        events = self.store.rows('transport_events', 'mission-1')
        self.assertEqual(len(events), 1)
        self.assertIsNotNone(self.store.unresolved_outbound('mission-1'))

    async def test_console_resume_pauses_on_missing_receipt_without_resend(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch, AsyncMock
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "console"))
        import missions
        checkpoint = await RecordingTransport([]).outbound_checkpoint()
        self.store.reserve_outbound("attempt", "mission-1", "objective", checkpoint=checkpoint)
        messages = []
        rt = SimpleNamespace(mission_id="mission-1", transport=RecordingTransport(messages))
        with patch.object(missions, "get_store", return_value=self.store), patch.object(missions, "_release_terminal_mission", AsyncMock()):
            await missions._resume_mission_task(rt)
        events = self.store.rows("transport_events", "mission-1", order_by="rowid")
        self.assertEqual(events[-1]["event_type"], "TRANSPORT_PAUSED")
        self.assertEqual(messages, [])
        self.assertIsNotNone(self.store.unresolved_outbound("mission-1"))

    async def test_reconcile_after_restart_settles_reservation_without_resend(self):
        import json
        messages = []
        client = TransportOrchestratorClient(RecordingTransport(messages, fail=True), self.store, "mission-1")
        with self.assertRaises(TransportError):
            await client.next_decision("objective")
        event = self.store.rows("transport_events", "mission-1")[0]
        self.assertEqual(json.loads(event["detail_json"])["checkpoint"]["last_message_id"], "anchor")
        self.store.close()
        reopened = Store(self.path)
        self.addCleanup(reopened.close)
        client = TransportOrchestratorClient(RecordingTransport(messages), reopened, "mission-1")
        await client.reconcile_pending()
        await client.reconcile_pending()
        self.assertEqual(messages, ["objective"])
        events = reopened.rows("transport_events", "mission-1", order_by="rowid")
        self.assertEqual([e["event_type"] for e in events], ["MESSAGE_SEND_STARTED", "MESSAGE_DELIVERED"])
        self.assertTrue(json.loads(events[-1]["detail_json"])["reconciled"])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.db"
        self.store = Store(self.path)
        self.addCleanup(self.store.close)
        self.store.create_mission("mission-1", "test", self.temp.name)

    async def test_restart_cannot_resend_uncertain_message(self):
        messages = []
        client = TransportOrchestratorClient(RecordingTransport(messages, fail=True), self.store, "mission-1")
        with self.assertRaises(TransportError):
            await client.next_decision("unique objective")
        self.store.close()
        restarted = Store(self.path)
        self.addCleanup(restarted.close)
        client = TransportOrchestratorClient(RecordingTransport(messages), restarted, "mission-1")
        with self.assertRaisesRegex(TransportError, "reconcil"):
            await client.next_decision("unique objective")
        self.assertEqual(messages, ["unique objective"])

    async def test_failed_persistence_prevents_transport_side_effect(self):
        self.store.close()
        messages = []
        client = TransportOrchestratorClient(RecordingTransport(messages), self.store, "mission-1")
        with self.assertRaises(Exception):
            await client.next_decision("objective")
        self.assertEqual(messages, [])

    async def test_confirmed_delivery_records_actual_message_identity(self):
        client = TransportOrchestratorClient(RecordingTransport([]), self.store, "mission-1")
        await client.next_decision("objective")
        rows = self.store.rows("transport_events", "mission-1", order_by="rowid")
        self.assertEqual(rows[0]["event_type"], "MESSAGE_SEND_STARTED")
        self.assertEqual(rows[1]["event_type"], "MESSAGE_DELIVERED")
        import json
        self.assertEqual(json.loads(rows[1]["detail_json"])["message_id"], "user-1")

    async def test_definitive_pre_delivery_failure_can_retry_without_losing_history(self):
        messages = []
        client = TransportOrchestratorClient(RecordingTransport(messages, fail_before=True), self.store, "mission-1")
        with self.assertRaises(TransportError):
            await client.next_decision("objective")
        client = TransportOrchestratorClient(RecordingTransport(messages), self.store, "mission-1")
        await client.next_decision("objective")
        self.assertEqual(messages, ["objective"])
        rows = self.store.rows("transport_events", "mission-1", order_by="rowid")
        self.assertEqual([row["event_type"] for row in rows], [
            "MESSAGE_SEND_STARTED", "MESSAGE_SEND_ABORTED", "MESSAGE_SEND_STARTED", "MESSAGE_DELIVERED",
        ])
        self.assertNotEqual(rows[0]["id"], rows[2]["id"])

    async def test_confirmed_message_cannot_be_sent_twice(self):
        messages = []
        client = TransportOrchestratorClient(RecordingTransport(messages), self.store, "mission-1")
        await client.next_decision("objective")
        with self.assertRaises(TransportError):
            await client.next_decision("objective")
        self.assertEqual(messages, ["objective"])

    async def test_uncertain_send_blocks_different_payload_in_same_mission(self):
        messages = []
        client = TransportOrchestratorClient(RecordingTransport(messages, fail=True), self.store, "mission-1")
        with self.assertRaises(TransportError):
            await client.next_decision("first")
        client = TransportOrchestratorClient(RecordingTransport(messages), self.store, "mission-1")
        with self.assertRaises(TransportError):
            await client.next_decision("different message")
        self.assertEqual(messages, ["first"])


if __name__ == "__main__":
    unittest.main()
