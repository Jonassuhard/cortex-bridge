"""Runtime truth regression tests.

The Ollama network boundary is always patched.  Availability probes are never
accepted as proof that an executor actually ran.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "console"))

from console import local_executor, missions, server  # noqa: E402
from executor.tools import ToolExecutor  # noqa: E402
from orchestration.runner import ModeARunner  # noqa: E402
from orchestration.store import Store  # noqa: E402
from transport.chatgpt_web.adapter import (  # noqa: E402
    ChatGPTWebTransport,
    LocalFixtureDriver,
)
from transport.chatgpt_web.fixture import FixtureServer  # noqa: E402


def decision_reply(
    mission_id: str,
    iteration: int,
    state: str,
    *,
    tool: str | None = None,
    arguments: dict | None = None,
    terminal: bool = False,
) -> str:
    decision = {
        "protocol": "cortex.v1",
        "missionId": mission_id,
        "actionId": str(uuid.uuid4()),
        "iteration": iteration,
        "state": state,
        "summary": f"fixture decision {iteration}",
        "action": {"tool": tool, "arguments": arguments or {}} if tool else None,
        "acceptanceCriteria": ["literal fixture criterion"],
        "requiresApproval": False,
        "terminal": terminal,
    }
    return "Decision:\n```cortex-decision\n" + json.dumps(decision) + "\n```"


class ExecutorRuntimeTruthTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workspace = Path(self._tmp.name)
        self.events: list[tuple[str, str]] = []

    async def emit(self, text: str, kind: str) -> None:
        self.events.append((text, kind))

    async def test_successful_ollama_call_reports_exact_called_model(self) -> None:
        (self.workspace / "ok.py").write_text(
            "from pathlib import Path\nPath('proof.txt').write_text('ok')\n",
            encoding="utf-8",
        )
        replies = iter(
            [
                json.dumps(
                    {
                        "status": "READY_FOR_TOOL",
                        "tool": "run_process",
                        "arguments": {"argv": ["python3", "ok.py"]},
                        "summary": "execute proof",
                    }
                ),
                json.dumps(
                    {
                        "status": "READY_FOR_VALIDATION",
                        "tool": None,
                        "arguments": {},
                        "summary": "proof produced",
                    }
                ),
            ]
        )
        called_models: list[str] = []
        original = local_executor._chat_sync

        def fake_chat(_messages: list[dict], model: str) -> str:
            called_models.append(model)
            return next(replies)

        local_executor._chat_sync = fake_chat
        self.addCleanup(setattr, local_executor, "_chat_sync", original)

        report = await local_executor._run_live(
            {
                "goal": "produce proof",
                "workspace": str(self.workspace),
                "allow_processes": True,
            },
            self.emit,
            process_approval=lambda _argv, _decision: True,
        )

        self.assertEqual(report["status"], "done")
        self.assertEqual(called_models, [local_executor.PRIMARY_EXECUTOR] * 2)
        self.assertEqual(report["executor_kind"], "ollama")
        self.assertEqual(report["executor_model_used"], local_executor.PRIMARY_EXECUTOR)
        self.assertEqual(report["runtime_mode"], "live")

    async def test_failed_ollama_call_claims_no_executor_or_model(self) -> None:
        original = local_executor._chat_sync

        def failed_chat(_messages: list[dict], _model: str) -> str:
            raise OSError("patched daemon loss")

        local_executor._chat_sync = failed_chat
        self.addCleanup(setattr, local_executor, "_chat_sync", original)

        report = await local_executor._run_live(
            {"goal": "cannot run", "workspace": str(self.workspace)},
            self.emit,
        )

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["executor_kind"], "unavailable")
        self.assertIsNone(report["executor_model_used"])
        self.assertEqual(report["runtime_mode"], "live")

    async def test_unavailable_executor_never_falls_back_to_done(self) -> None:
        original = local_executor.detect_mode
        local_executor.detect_mode = lambda: "unavailable"
        self.addCleanup(setattr, local_executor, "detect_mode", original)

        report = await local_executor.run_task(
            {"goal": "must not simulate", "workspace": str(self.workspace)},
            self.emit,
        )

        self.assertNotEqual(report["status"], "done")
        self.assertEqual(report["executor_kind"], "unavailable")
        self.assertIsNone(report["executor_model_used"])
        self.assertEqual(report["runtime_mode"], "live")

    async def test_development_fixture_requires_both_explicit_flags_and_fails_release_gate(self) -> None:
        original_mode = local_executor.detect_mode
        local_executor.detect_mode = lambda: "unavailable"
        self.addCleanup(setattr, local_executor, "detect_mode", original_mode)
        previous = os.environ.pop("CORTEX_ALLOW_DEVELOPMENT_FIXTURES", None)

        def restore_env() -> None:
            if previous is None:
                os.environ.pop("CORTEX_ALLOW_DEVELOPMENT_FIXTURES", None)
            else:
                os.environ["CORTEX_ALLOW_DEVELOPMENT_FIXTURES"] = previous

        self.addCleanup(restore_env)

        without_env = await local_executor.run_task(
            {
                "goal": "preview",
                "workspace": str(self.workspace),
                "development_fixture": True,
            },
            self.emit,
        )
        self.assertEqual(without_env["runtime_mode"], "live")

        os.environ["CORTEX_ALLOW_DEVELOPMENT_FIXTURES"] = "1"
        fixture = await local_executor.run_task(
            {
                "goal": "preview",
                "workspace": str(self.workspace),
                "development_fixture": True,
            },
            self.emit,
        )
        self.assertEqual(fixture["runtime_mode"], "development_fixture")
        self.assertFalse(local_executor.release_runtime_eligible(fixture))
        self.assertNotEqual(fixture["status"], "done")

    async def test_mode_a_is_deterministic_and_ignores_legacy_model_fields(self) -> None:
        fixture_server = FixtureServer().start()
        self.addCleanup(fixture_server.stop)
        store = Store(self.workspace / "mode-a.db")
        self.addCleanup(store.close)
        mission_id = str(uuid.uuid4())
        conversation_url = f"{fixture_server.base_url}/c/runtime-truth"
        fixture_server.queue_replies(
            [
                decision_reply(
                    mission_id,
                    1,
                    "EXECUTE",
                    tool="list_directory",
                    arguments={"path": "."},
                ),
                decision_reply(mission_id, 2, "COMPLETE", terminal=True),
            ],
            "runtime-truth",
        )
        runner = ModeARunner(
            store=store,
            transport=ChatGPTWebTransport(
                LocalFixtureDriver(fixture_server.base_url),
                stability_interval=0.12,
                poll_interval=0.03,
                max_wait=5.0,
            ),
            tools=ToolExecutor(self.workspace),
            experimental_transport_accepted=True,
        )
        body = missions.MissionIn(
            objective="list deterministically",
            workspace=str(self.workspace),
            conversation_url=conversation_url,
            primary_executor="fake-primary",
            fallback_executor="fake-fallback",
        )
        original = local_executor._chat_sync
        ollama_calls = 0

        def forbidden_ollama(*_args, **_kwargs):
            nonlocal ollama_calls
            ollama_calls += 1
            raise AssertionError("Mode A must not call Ollama")

        local_executor._chat_sync = forbidden_ollama
        self.addCleanup(setattr, local_executor, "_chat_sync", original)

        result = await runner.run_mission(
            body.objective,
            conversation_url=body.conversation_url,
            mission_id=mission_id,
        )

        self.assertEqual(result["executor_kind"], "deterministic")
        self.assertIsNone(result["executor_model_used"])
        self.assertEqual(result["runtime_mode"], "live")
        self.assertNotIn("fake-primary", json.dumps(result))
        self.assertNotIn("fake-fallback", json.dumps(result))
        self.assertEqual(ollama_calls, 0)

    async def test_tasks_expose_model_only_after_successful_executor_call(self) -> None:
        original_store_file = server.STORE_FILE
        original_runtime_status = server.runtime_status
        original_run_task = server.run_task
        original_iterations = list(server._iterations)
        server.STORE_FILE = self.workspace / "iterations.json"
        server._iterations.clear()
        release_call = asyncio.Event()

        async def patched_run_task(_task: dict, _emit) -> dict:
            await release_call.wait()
            return {
                "status": "done",
                "summary": "patched real-call boundary returned",
                "commands_run": ["python3 ok.py"],
                "files_changed": [],
                "blockers": [],
                "suggested_next_step": "review",
                "executor_kind": "ollama",
                "executor_model_used": "granite-runtime-test:latest",
                "runtime_mode": "live",
            }

        server.runtime_status = lambda: {"storage_status": "OK"}
        server.run_task = patched_run_task

        async def restore_server() -> None:
            server.STORE_FILE = original_store_file
            server.runtime_status = original_runtime_status
            server.run_task = original_run_task
            server._iterations[:] = original_iterations

        self.addAsyncCleanup(restore_server)

        created = await server.create_task(
            server.TaskIn(goal="observe runtime truth", workspace=str(self.workspace))
        )
        before = (await server.list_tasks())[0]
        self.assertEqual(created["executor_kind"], "unavailable")
        self.assertIsNone(created["executor_model_used"])
        self.assertEqual(before["executor_kind"], "unavailable")
        self.assertIsNone(before["executor_model_used"])

        release_call.set()
        deadline = asyncio.get_running_loop().time() + 3
        while server._iterations[0]["status"] == "running":
            if asyncio.get_running_loop().time() >= deadline:
                self.fail("patched task did not finish")
            await asyncio.sleep(0.01)

        after = (await server.list_tasks())[0]
        self.assertEqual(after["executor_kind"], "ollama")
        self.assertEqual(after["executor_model_used"], "granite-runtime-test:latest")
        self.assertEqual(after["runtime_mode"], "live")


if __name__ == "__main__":
    unittest.main()
