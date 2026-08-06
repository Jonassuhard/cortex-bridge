"""Phase 5 — Mode A runner wiring tests (fixture transport only).

Never touches the real WebBridge daemon or real ChatGPT. stdlib unittest:
    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from executor.tools import ToolExecutor  # noqa: E402
from orchestration.runner import (  # noqa: E402
    ModeARunner,
    OptInRequired,
    render_contract,
)
from orchestration.store import Store  # noqa: E402
from transport.chatgpt_web.adapter import (  # noqa: E402
    ChatGPTWebTransport,
    DELIVERY_UNCERTAIN,
    LocalFixtureDriver,
    TransportError,
)
from transport.chatgpt_web.fixture import FixtureServer  # noqa: E402

import tempfile


def decision_reply(mission_id, iteration, state, tool=None, arguments=None, criteria=None, terminal=False):
    decision = {
        "protocol": "cortex.v1",
        "missionId": mission_id,
        "actionId": str(uuid.uuid4()),
        "iteration": iteration,
        "state": state,
        "summary": f"fixture decision {iteration}",
        "action": {"tool": tool, "arguments": arguments or {}} if tool else None,
        "acceptanceCriteria": criteria if criteria is not None else ["criterion"],
        "requiresApproval": False,
        "terminal": terminal,
    }
    return "Decision:\n```cortex-decision\n" + json.dumps(decision, indent=2) + "\n```"


class ModeARunnerTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = Path(self._tmp.name)
        self.server = FixtureServer().start()
        self.addCleanup(self.server.stop)
        self.driver = LocalFixtureDriver(self.server.base_url)
        self.transport = ChatGPTWebTransport(
            self.driver, stability_interval=0.15, poll_interval=0.03, max_wait=5.0
        )
        self.store = Store(self.ws / "cortex.db")
        self.addCleanup(self.store.close)
        self.tools = ToolExecutor(self.ws)
        self.conv_url = f"{self.server.base_url}/c/conv-1"

    def make_runner(self, accepted=True, **kwargs):
        params = {
            "store": self.store,
            "transport": self.transport,
            "tools": self.tools,
            "approval_callback": lambda d, p: "once",
            "experimental_transport_accepted": accepted,
        }
        params.update(kwargs)
        return ModeARunner(**params)

    # §6 gate: opt-in off → refuses before any send, no mission created
    async def test_opt_in_off_refuses_to_send(self):
        runner = self.make_runner(accepted=False)
        with self.assertRaises(OptInRequired):
            await runner.run_mission("do something", conversation_url=self.conv_url)
        self.assertEqual(self.store.count("missions"), 0)
        self.assertEqual(self.server.conversation("conv-1").messages, [])

    # opt-in on → full mock-driven mission through the transport interface
    async def test_opt_in_on_full_mission(self):
        mission_id = str(uuid.uuid4())
        content = "Cortex Bridge autonomous loop works"
        replies = [
            decision_reply(
                mission_id,
                1,
                "EXECUTE",
                tool="write_file",
                arguments={"path": "witness.txt", "content": content},
                criteria=["witness.txt written exactly"],
            ),
            decision_reply(
                mission_id,
                2,
                "COMPLETE",
                criteria=["witness.txt exists with exact content"],
                terminal=True,
            ),
        ]
        self.server.queue_replies(replies, "conv-1")

        def final_validator(decision, tools):
            ok = (self.ws / "witness.txt").is_file() and (
                self.ws / "witness.txt"
            ).read_text(encoding="utf-8") == content
            return {
                "passed": ok,
                "checks": [{"name": "witness_exact", "passed": ok, "evidence": "content check"}],
            }

        runner = self.make_runner(final_validator=final_validator)
        mission = await runner.run_mission(
            "Create witness.txt with the exact sentence.",
            conversation_url=self.conv_url,
            mission_id=mission_id,
        )

        self.assertEqual(mission["state"], "COMPLETED")
        # Contract was the first transport message, §9 text + protocol fence.
        messages = self.server.conversation("conv-1").messages
        user_msgs = [m for m in messages if m["role"] == "user"]
        self.assertEqual(len(user_msgs), 2)  # contract + one cortex-report
        self.assertIn("You are the cloud orchestrator for Cortex Bridge.", user_msgs[0]["text"])
        self.assertIn(mission_id, user_msgs[0]["text"])
        self.assertIn("```cortex-report", user_msgs[1]["text"])
        # Lock persisted (§8 binding).
        bindings = self.store.rows("conversation_bindings", mission_id)
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0]["conversation_url"], self.conv_url)
        # Evidence: one write (approval-gated), two valid decisions.
        self.assertEqual(self.store.count("tool_executions", mission_id), 1)
        self.assertEqual(self.store.count("approvals", mission_id), 1)
        decisions = self.store.rows("orchestrator_decisions", mission_id)
        self.assertEqual(len(decisions), 2)
        self.assertTrue(all(d["valid"] == 1 for d in decisions))
        # verify_lock enforced: every assistant reply fingerprinted once.
        self.assertEqual(self.store.count("chatgpt_messages", mission_id), 2)

    async def test_transport_pause_records_the_safe_error_detail(self):
        async def rejected_send(_text):
            raise TransportError(
                DELIVERY_UNCERTAIN,
                "synthetic new-chat submitter became detached",
            )

        self.transport.send_message = rejected_send
        mission_id = str(uuid.uuid4())
        runner = self.make_runner()

        mission = await runner.run_mission(
            "Exercise a rejected delivery.",
            conversation_url=self.conv_url,
            mission_id=mission_id,
        )

        self.assertEqual(mission["state"], "PAUSED")
        event = self.store.rows("transport_events", mission_id)[-1]
        detail = json.loads(event["detail_json"])
        self.assertEqual(detail["reason"], DELIVERY_UNCERTAIN)
        self.assertEqual(
            detail["error"],
            "DELIVERY_UNCERTAIN: synthetic new-chat submitter became detached",
        )

    # §8: list candidate conversations from the fixture sidebar equivalent
    async def test_list_conversation_candidates(self):
        await self.transport.select_conversation(self.conv_url)
        self.server.conversation("conv-2")
        candidates = await self.transport.list_conversations()
        ids = {c["identity"] for c in candidates}
        self.assertIn("conv-1", ids)
        self.assertIn("conv-2", ids)
        entry = next(c for c in candidates if c["identity"] == "conv-1")
        self.assertEqual(entry["url"], self.conv_url)
        self.assertTrue(entry["title"])

    # §8: brand-new chat — first send creates /c/<id>, lock is captured
    async def test_new_chat_lock_capture(self):
        self.server.queue_new_chat_replies(["first reply in the new chat"])
        await self.transport.start_new_conversation(f"{self.server.base_url}/")
        self.assertIsNone(self.transport.lock)
        await self.transport.send_message("hello new chat")
        self.assertIsNotNone(self.transport.lock)
        self.assertTrue(self.transport.lock.identity.startswith("conv-"))
        msg = await self.transport.await_response()
        self.assertEqual(msg["text"], "first reply in the new chat")
        # Subsequent sends are lock-verified against the captured identity.
        await self.transport.verify_lock()

    # contract template contains the §9 + protocol essentials
    def test_contract_template(self):
        mission_id = str(uuid.uuid4())
        contract = render_contract("objective text", mission_id, "/some/workspace")
        self.assertIn("You are the cloud orchestrator for Cortex Bridge.", contract)
        self.assertIn("```cortex-decision", contract)
        self.assertIn("```cortex-report", contract)
        self.assertIn(mission_id, contract)
        self.assertIn("objective text", contract)
        self.assertIn("/some/workspace", contract)
        self.assertIn("run_process", contract)  # allowed tools enumerated
        self.assertIn("Recorded local execution evidence", contract)


if __name__ == "__main__":
    unittest.main()
