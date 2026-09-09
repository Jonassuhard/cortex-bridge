import dataclasses
import asyncio
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from effect_gate import EffectGate, MissionApprovalResponse
from executor.tools import ToolExecutor
from orchestration.effect_schema import upgrade_effect_schema
from orchestration.loop import MissionLoop, MockOrchestrator
from orchestration.store import Store


class DurableLoopApprovalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name)
        self.store = Store(self.workspace / "state.db")
        self.addCleanup(self.store.close)
        self.mission = str(uuid.uuid4())
        self.store.create_mission(self.mission, "Create a fixture file", str(self.workspace))
        upgrade_effect_schema(self.store._conn)
        self.gate = EffectGate(self.store)

    def loop(self, callback, tools=None, complete=False):
        script = [dict(state="EXECUTE", action={"tool":"write_file", "arguments":{"path":"a.txt","content":"A"}},
                       requiresApproval=True),
                  dict(state="BLOCKED", action=None, terminal=True, acceptanceCriteria=[])]
        if complete:
            script[-1] = dict(state="COMPLETE", action=None, terminal=True, acceptanceCriteria=["a.txt contains A"])
        return MissionLoop(store=self.store, mission_id=self.mission,
                           orchestrator=MockOrchestrator(self.mission, script),
                           tools=tools or ToolExecutor(self.workspace), effect_gate=self.gate,
                           approval_callback=callback)

    async def test_notification_return_value_does_not_authorize(self):
        loop = self.loop(lambda challenge, policy: "once")
        await loop.run()
        self.assertFalse((self.workspace / "a.txt").exists())
        self.assertEqual(self.store.count("tool_executions", self.mission), 0)
        self.assertEqual(self.store.rows("approvals", self.mission)[0]["decision"], "pending")

    async def test_durable_denial_prevents_execution(self):
        def deny(challenge, policy):
            values = dataclasses.asdict(challenge)
            values.pop("tool")
            self.gate.decide_approval(MissionApprovalResponse(**values, approve=False))
            return "once"  # ignored: SQLite denial governs
        loop = self.loop(deny)
        await loop.run()
        self.assertFalse((self.workspace / "a.txt").exists())
        self.assertEqual(self.store.rows("approvals", self.mission)[0]["decision"], "denied")
        self.assertEqual(self.store.effect_rows(), [])

    async def test_stop_after_approval_prevents_execution(self):
        def approve_then_stop(challenge, policy):
            values = dataclasses.asdict(challenge)
            values.pop("tool")
            self.gate.decide_approval(MissionApprovalResponse(**values, approve=True))
            self.gate.request_stop()
        loop = self.loop(approve_then_stop)
        await loop.run()
        self.assertFalse((self.workspace / "a.txt").exists())
        self.assertEqual(self.store.effect_rows(), [])
        self.assertEqual(self.store.count("tool_executions", self.mission), 0)

    def test_v3_store_cannot_use_legacy_authorization(self):
        with self.assertRaisesRegex(ValueError, "EFFECT_GATE_REQUIRED"):
            MissionLoop(store=self.store, mission_id=self.mission,
                        orchestrator=MockOrchestrator(self.mission, []), tools=ToolExecutor(self.workspace))

    def approve(self, challenge, policy):
        values = dataclasses.asdict(challenge)
        values.pop("tool")
        self.gate.decide_approval(MissionApprovalResponse(**values, approve=True))

    async def test_effect_is_active_and_approval_consumed_before_tool(self):
        case = self
        class RecordingExecutor(ToolExecutor):
            supports_durable_effects = True
            async def write_file(self, path, content, *, activation):
                case.gate.assert_activation(activation, owner_kind="mission", category="filesystem", operation="write_file")
                case.assertIsNotNone(case.store.rows("approvals", case.mission)[0]["effect_consumed_at"])
                result = await super().write_file(path=path, content=content)
                case.gate.succeed(activation, result)
                return result
        result = await self.loop(self.approve, RecordingExecutor(self.workspace), complete=True).run()
        self.assertEqual(result["state"], "COMPLETED", self.store.rows("validation_results", self.mission))
        self.assertEqual((self.workspace / "a.txt").read_text(), "A")
        self.assertEqual([r["state"] for r in self.store.effect_rows()], ["succeeded"])

    async def test_executor_without_activation_support_cannot_run_v3(self):
        await self.loop(self.approve).run()
        self.assertFalse((self.workspace / "a.txt").exists())
        self.assertEqual(self.store.effect_rows(), [])

    async def test_executor_return_without_terminal_receipt_is_unclear(self):
        class MissingReceiptExecutor(ToolExecutor):
            supports_durable_effects = True
            async def write_file(self, path, content, *, activation):
                return await super().write_file(path=path, content=content)
        await self.loop(self.approve, MissingReceiptExecutor(self.workspace)).run()
        self.assertEqual([r["state"] for r in self.store.effect_rows()], ["outcome_unclear"])
        self.assertEqual(self.store.rows("validation_results", self.mission)[0]["passed"], 0)

    async def test_cancellation_preserves_uncertainty_and_propagates(self):
        class InterruptedExecutor(ToolExecutor):
            supports_durable_effects = True
            async def write_file(self, path, content, *, activation):
                raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.loop(self.approve, InterruptedExecutor(self.workspace)).run()
        self.assertEqual([r["state"] for r in self.store.effect_rows()], ["outcome_unclear"])
        self.assertFalse((self.workspace / "a.txt").exists())


if __name__ == "__main__":
    unittest.main()
