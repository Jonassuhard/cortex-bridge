"""Regression coverage for mission approval scope consumption."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "console"))

from missions import MissionRuntime, _make_approval_callback  # noqa: E402
from executor.policy import (
    SCOPE_ONCE,
    SCOPE_TOOL_FOR_MISSION,
    PolicyEngine,
    WRITE_WITH_APPROVALS,
)  # noqa: E402


class ApprovalScopeRegressionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.workspace = Path(self.tempdir.name)

    async def grant(self, scope: str) -> tuple[MissionRuntime, PolicyEngine, str | None]:
        policy = PolicyEngine(self.workspace, mode=WRITE_WITH_APPROVALS)
        runtime = MissionRuntime("approval-regression")
        runtime.policy = policy
        callback = _make_approval_callback(runtime)
        waiter = asyncio.create_task(
            callback({"action": {"tool": "write_file"}}, None)
        )
        await asyncio.sleep(0)
        runtime.approval_scope = scope
        runtime.approval_event.set()
        return runtime, policy, await waiter

    async def test_once_approval_does_not_authorize_the_next_write(self) -> None:
        # Regression: the approval callback persisted SCOPE_ONCE before running
        # the already-approved action, so the following write consumed it.
        _, policy, granted = await self.grant(SCOPE_ONCE)

        next_write = policy.evaluate(
            "write_file",
            {"path": "second.txt", "content": "second"},
        )

        self.assertEqual(granted, SCOPE_ONCE)
        self.assertTrue(next_write.requires_approval)

    async def test_tool_scope_still_authorizes_future_writes(self) -> None:
        _, policy, granted = await self.grant(SCOPE_TOOL_FOR_MISSION)

        next_write = policy.evaluate(
            "write_file",
            {"path": "second.txt", "content": "second"},
        )

        self.assertEqual(granted, SCOPE_TOOL_FOR_MISSION)
        self.assertFalse(next_write.requires_approval)
