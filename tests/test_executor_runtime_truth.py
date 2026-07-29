"""Runtime truth regression tests.

The Ollama network boundary is always patched.  Availability probes are never
accepted as proof that an executor actually ran.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sqlite3
from contextlib import closing
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "console"))

import uvicorn  # noqa: E402

from console import local_executor, missions, server  # noqa: E402
import local_executor as server_local_executor  # noqa: E402
import settings as settings_api  # noqa: E402
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
        self.assertTrue(report["release_eligible"])

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
        self.assertFalse(fixture["release_eligible"])
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
        self.assertTrue(result["release_eligible"])
        self.assertNotIn("fake-primary", json.dumps(result))
        self.assertNotIn("fake-fallback", json.dumps(result))
        self.assertEqual(ollama_calls, 0)

        reloaded = Store(self.workspace / "mode-a.db")
        self.addCleanup(reloaded.close)
        persisted = reloaded.get_mission(mission_id)
        self.assertEqual(persisted["executor_kind"], "deterministic")
        self.assertIsNone(persisted["executor_model_used"])
        self.assertEqual(persisted["runtime_mode"], "live")
        self.assertIs(persisted["release_eligible"], True)
        self.assertIsInstance(persisted["runtime_observed_at"], float)
        self.assertGreater(persisted["runtime_observed_at"], 0)
        self.assertEqual(
            persisted["runtime_observed_at"],
            result["runtime_observed_at"],
        )

    def test_pre_v05_mission_schema_migrates_additively_and_reloads_runtime_truth(self) -> None:
        database = self.workspace / "pre-v05.db"
        with closing(sqlite3.connect(database)) as connection:
            connection.executescript(
                """
                CREATE TABLE missions (
                    id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    workspace TEXT NOT NULL,
                    state TEXT NOT NULL,
                    pause_reason TEXT,
                    iteration INTEGER NOT NULL DEFAULT 0,
                    max_iterations INTEGER NOT NULL DEFAULT 25,
                    max_duration_seconds INTEGER NOT NULL DEFAULT 3600,
                    failure_counts TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    started_at REAL,
                    updated_at REAL NOT NULL
                );
                INSERT INTO missions (
                    id, objective, workspace, state, pause_reason, iteration,
                    max_iterations, max_duration_seconds, failure_counts,
                    created_at, started_at, updated_at
                ) VALUES (
                    'legacy-mission', 'preserve this objective', '/tmp/legacy',
                    'COMPLETED', NULL, 3, 25, 3600, '{}', 10.0, 11.0, 12.0
                );
                """
            )

        migrated = Store(database)
        legacy = migrated.get_mission("legacy-mission")
        self.assertEqual(legacy["objective"], "preserve this objective")
        self.assertEqual(legacy["state"], "COMPLETED")
        self.assertEqual(legacy["iteration"], 3)
        self.assertEqual(legacy["executor_kind"], "unavailable")
        self.assertIsNone(legacy["executor_model_used"])
        self.assertEqual(legacy["runtime_mode"], "live")
        self.assertIs(legacy["release_eligible"], False)
        self.assertIsNone(legacy["runtime_observed_at"])

        updated = migrated.record_runtime_truth(
            "legacy-mission",
            executor_kind="deterministic",
            executor_model_used=None,
            runtime_mode="live",
            release_eligible=True,
        )
        observed_at = updated["runtime_observed_at"]
        self.assertIsInstance(observed_at, float)
        migrated.close()

        reloaded = Store(database)
        self.addCleanup(reloaded.close)
        persisted = reloaded.get_mission("legacy-mission")
        self.assertEqual(persisted["objective"], "preserve this objective")
        self.assertEqual(persisted["executor_kind"], "deterministic")
        self.assertIsNone(persisted["executor_model_used"])
        self.assertEqual(persisted["runtime_mode"], "live")
        self.assertIs(persisted["release_eligible"], True)
        self.assertEqual(persisted["runtime_observed_at"], observed_at)

    async def test_tasks_expose_model_only_after_successful_executor_call(self) -> None:
        original_store_file = server.STORE_FILE
        original_pipeline_store_file = settings_api.TASK_STORE_FILE
        original_iterations = list(server._iterations)
        server.STORE_FILE = self.workspace / "iterations.json"
        settings_api.TASK_STORE_FILE = server.STORE_FILE
        server._iterations.clear()
        (self.workspace / "ok.py").write_text(
            "from pathlib import Path\nPath('api-proof.txt').write_text('ok')\n",
            encoding="utf-8",
        )
        replies = iter(
            [
                json.dumps(
                    {
                        "status": "READY_FOR_TOOL",
                        "tool": "run_process",
                        "arguments": {"argv": ["python3", "ok.py"]},
                        "summary": "execute api proof",
                    }
                ),
                json.dumps(
                    {
                        "status": "READY_FOR_VALIDATION",
                        "tool": None,
                        "arguments": {},
                        "summary": "api proof produced",
                    }
                ),
            ]
        )
        called_models: list[str] = []
        original_detect_mode = server_local_executor.detect_mode
        original_chat = server_local_executor._chat_sync

        def fake_chat(_messages: list[dict], model: str) -> str:
            called_models.append(model)
            return next(replies)

        server_local_executor.detect_mode = lambda: "live"
        server_local_executor._chat_sync = fake_chat

        async def restore_server() -> None:
            server.STORE_FILE = original_store_file
            settings_api.TASK_STORE_FILE = original_pipeline_store_file
            server._iterations[:] = original_iterations
            server_local_executor.detect_mode = original_detect_mode
            server_local_executor._chat_sync = original_chat

        self.addAsyncCleanup(restore_server)

        created = await server.create_task(
            server.TaskIn(
                goal="observe runtime truth",
                workspace=str(self.workspace),
                allow_processes=True,
            )
        )
        before = (await server.list_tasks())[0]
        self.assertEqual(created["executor_kind"], "unavailable")
        self.assertIsNone(created["executor_model_used"])
        self.assertEqual(before["executor_kind"], "unavailable")
        self.assertIsNone(before["executor_model_used"])

        deadline = asyncio.get_running_loop().time() + 3
        while server._iterations[0]["status"] == "running":
            if asyncio.get_running_loop().time() >= deadline:
                self.fail("patched task did not finish")
            await asyncio.sleep(0.01)

        after = (await server.list_tasks())[0]
        self.assertEqual(after["executor_kind"], "ollama")
        self.assertEqual(after["executor_model_used"], server_local_executor.PRIMARY_EXECUTOR)
        self.assertEqual(after["runtime_mode"], "live")
        self.assertEqual(after["status"], "blocked")
        self.assertFalse(after["release_eligible"])
        self.assertEqual(called_models, [server_local_executor.PRIMARY_EXECUTOR])

        persisted = json.loads(server.STORE_FILE.read_text(encoding="utf-8"))[0]
        self.assertEqual(persisted["report"]["executor_model_used"], server_local_executor.PRIMARY_EXECUTOR)
        self.assertFalse(persisted["report"]["release_eligible"])

        pipeline = await settings_api.pipeline_status()
        self.assertEqual(pipeline["runtime_execution"]["executor_kind"], "ollama")
        self.assertEqual(
            pipeline["runtime_execution"]["executor_model_used"],
            server_local_executor.PRIMARY_EXECUTOR,
        )
        self.assertEqual(pipeline["runtime_execution"]["state"], "blocked")
        self.assertFalse(pipeline["runtime_execution"]["active"])
        self.assertEqual(pipeline["runtime_execution"]["task_id"], created["id"])
        self.assertEqual(
            pipeline["runtime_execution"]["observed_at"],
            persisted["finished_at"],
        )

    async def test_task_http_fixture_boundary_covers_all_flag_combinations(self) -> None:
        original_store_file = server.STORE_FILE
        original_iterations = list(server._iterations)
        original_detect_mode = server_local_executor.detect_mode
        previous_env = os.environ.pop("CORTEX_ALLOW_DEVELOPMENT_FIXTURES", None)
        server.STORE_FILE = self.workspace / "fixture-boundary.json"
        server._iterations.clear()
        server_local_executor.detect_mode = lambda: "unavailable"

        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base_url = f"http://127.0.0.1:{port}"
        httpd = uvicorn.Server(
            uvicorn.Config(
                server.app,
                host="127.0.0.1",
                port=port,
                log_level="error",
            )
        )
        thread = threading.Thread(target=httpd.run, daemon=True)
        thread.start()

        def request(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
            data = json.dumps(payload).encode() if payload is not None else None
            req = urllib.request.Request(
                base_url + path,
                data=data,
                method=method,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as response:
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as exc:
                with exc:
                    return exc.code, json.loads(exc.read())

        deadline = time.monotonic() + 5
        while True:
            try:
                request("GET", "/api/tasks")
                break
            except OSError:
                if time.monotonic() >= deadline:
                    self.fail("fixture-boundary HTTP server did not start")
                time.sleep(0.02)

        async def wait_for(task_id: str) -> dict:
            deadline = asyncio.get_running_loop().time() + 2
            while True:
                status, task = request("GET", f"/api/tasks/{task_id}")
                self.assertEqual(status, 200, task)
                if task["status"] != "running":
                    return task
                if asyncio.get_running_loop().time() >= deadline:
                    self.fail(f"task {task_id} did not finish")
                await asyncio.sleep(0.01)

        async def restore() -> None:
            server.STORE_FILE = original_store_file
            server._iterations[:] = original_iterations
            server_local_executor.detect_mode = original_detect_mode
            httpd.should_exit = True
            thread.join(timeout=5)
            if previous_env is None:
                os.environ.pop("CORTEX_ALLOW_DEVELOPMENT_FIXTURES", None)
            else:
                os.environ["CORTEX_ALLOW_DEVELOPMENT_FIXTURES"] = previous_env

        self.addAsyncCleanup(restore)

        status, live_without_env = request(
            "POST",
            "/api/tasks",
            {"goal": "live env off", "workspace": str(self.workspace)},
        )
        self.assertEqual(status, 201, live_without_env)
        live_without_env_done = await wait_for(live_without_env["id"])
        self.assertEqual(live_without_env_done["runtime_mode"], "live")

        status, rejected = request(
            "POST",
            "/api/tasks",
            {
                "goal": "fixture rejected",
                "workspace": str(self.workspace),
                "development_fixture": True,
            },
        )
        self.assertEqual(status, 403, rejected)
        self.assertEqual(
            rejected["detail"]["error"],
            "DEVELOPMENT_FIXTURES_DISABLED",
        )

        os.environ["CORTEX_ALLOW_DEVELOPMENT_FIXTURES"] = "1"
        status, live_with_env = request(
            "POST",
            "/api/tasks",
            {"goal": "live env on", "workspace": str(self.workspace)},
        )
        self.assertEqual(status, 201, live_with_env)
        live_with_env_done = await wait_for(live_with_env["id"])
        self.assertEqual(live_with_env_done["runtime_mode"], "live")

        status, fixture = request(
            "POST",
            "/api/tasks",
            {
                "goal": "fixture explicit",
                "workspace": str(self.workspace),
                "development_fixture": True,
            },
        )
        self.assertEqual(status, 201, fixture)
        fixture_done = await wait_for(fixture["id"])
        self.assertEqual(fixture_done["status"], "blocked")
        self.assertEqual(fixture_done["runtime_mode"], "development_fixture")
        self.assertFalse(fixture_done["release_eligible"])
        self.assertFalse(fixture_done["report"]["release_eligible"])

    def test_build_runtime_accepts_legacy_executor_arguments_by_keyword_and_position(self) -> None:
        class Lease:
            conversation_key = "https://chatgpt.com/c/runtime-compat"
            session_id = "cortex-conv-runtime-compat"

        original_transport = missions._make_transport
        missions._make_transport = lambda _session_id: object()
        self.addCleanup(setattr, missions, "_make_transport", original_transport)
        self.addCleanup(missions._runtimes.clear)

        positional = missions._build_runtime(
            "positional",
            str(self.workspace),
            "workspace-write-with-approvals",
            "ignored-primary",
            "ignored-fallback",
            5,
            60,
            lease=Lease(),
        )
        keyword = missions._build_runtime(
            "keyword",
            str(self.workspace),
            "workspace-write-with-approvals",
            primary_executor="ignored-primary",
            fallback_executor="ignored-fallback",
            max_iterations=5,
            max_duration_seconds=60,
            lease=Lease(),
        )

        self.assertEqual(positional._budgets.max_iterations, 5)
        self.assertEqual(keyword._budgets.max_iterations, 5)

    def test_fallback_settings_save_does_not_dereference_removed_control(self) -> None:
        html_path = REPO_ROOT / "frontend" / "fallback" / "index.html"
        node_test = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(process.argv[1], 'utf8');
const start = html.indexOf('async function saveSettings()');
const end = html.indexOf("\n$('#collapseSidebar')", start);
if (start < 0 || end < 0) throw new Error('saveSettings function not found');
const source = html.slice(start, end);
const controls = new Map();
for (const id of [
  '#setLanguage','#setTheme','#setPlanner','#setPrimary','#setApproval',
  '#setProfile','#setWorkspace','#setIterations','#setDuration','#setContext',
  '#setAuto','#setBrowser','#setNetwork','#setHistory','#setOptin',
  '#setStability','#setTimeout',
  '#settingsModal','#plannerLabel','#executorLabel','#profileLabel','#workspacePill'
]) controls.set(id, {
  value: id === '#setWorkspace' ? '/tmp/workspace' : id.includes('Iterations') ? '5' : id.includes('Duration') ? '10' : id.includes('Context') ? '4096' : 'value',
  checked: false,
  textContent: '',
  classList: { remove() {} },
});
const context = {
  state: {
    demo: true,
    settings: { fallback_executor: 'legacy-preserved' },
    transport: { opt_in_accepted: false },
  },
  $: (selector) => controls.get(selector),
  req: async () => { throw new Error('network must not run in demo'); },
  toast() {},
  Number,
};
vm.createContext(context);
vm.runInContext(source + ';this.saveSettings=saveSettings', context);
context.saveSettings().then(() => {
  if (context.state.settings.fallback_executor !== 'legacy-preserved') {
    throw new Error('legacy fallback value was not preserved');
  }
}).catch((error) => { console.error(error); process.exitCode = 1; });
"""
        completed = subprocess.run(
            ["node", "-e", node_test, str(html_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_fallback_status_indicators_are_semantic_and_component_independent(self) -> None:
        html_path = REPO_ROOT / "frontend" / "fallback" / "index.html"
        node_test = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(process.argv[1], 'utf8');
const start = html.indexOf('function renderPipeline()');
const end = html.indexOf('\nasync function refreshAll()', start);
if (start < 0 || end < 0) throw new Error('renderPipeline function not found');
const source = html.slice(start, end);
class Element {
  constructor() {
    this.textContent = '';
    this.className = '';
    this.dataset = {};
    this.children = [];
    this.queries = new Map();
  }
  appendChild(child) { this.children.push(child); }
  replaceChildren() { this.children = []; }
  querySelector(selector) {
    if (!this.queries.has(selector)) this.queries.set(selector, new Element());
    return this.queries.get(selector);
  }
}
const elements = new Map();
for (const id of [
  '#pipelineCards', '#pipelineEvents', '#missionState', '#latency',
  '#chatgptIndicator', '#onlineLabel', '#executorIndicator',
  '#executorStatusLabel', '#pipelineLiveIndicator', '#pipelineLiveLabel',
]) {
  elements.set(id, new Element());
}
const context = {
  state: {
    pipeline: {
      overall: 'unknown',
      components: [
        { id: 'transport', label: 'Transport', state: 'healthy', detail: 'ok' },
        { id: 'executor', label: 'Executor', state: 'error', detail: 'failed' },
      ],
      events: [],
      active_mission_state: null,
      latency: {},
    },
  },
  $: (selector) => elements.get(selector),
  document: { createElement() { return new Element(); } },
  fmt() { return '—'; },
  tm() { return ''; },
};
vm.createContext(context);
vm.runInContext(source + ';this.renderPipeline=renderPipeline', context);
context.renderPipeline();
if (elements.get('#onlineLabel').textContent !== 'Connecté') {
  throw new Error(`unexpected transport label: ${elements.get('#onlineLabel').textContent}`);
}
if (elements.get('#chatgptIndicator').dataset.state !== 'online') {
  throw new Error(`unexpected transport data-state: ${elements.get('#chatgptIndicator').dataset.state}`);
}
if (elements.get('#executorStatusLabel').textContent !== 'Indisponible') {
  throw new Error(`unexpected executor label: ${elements.get('#executorStatusLabel').textContent}`);
}
if (elements.get('#executorIndicator').dataset.state !== 'offline') {
  throw new Error(`unexpected executor data-state: ${elements.get('#executorIndicator').dataset.state}`);
}
if (elements.get('#pipelineLiveLabel').textContent !== 'État inconnu') {
  throw new Error(`unexpected pipeline label: ${elements.get('#pipelineLiveLabel').textContent}`);
}
if (elements.get('#pipelineLiveIndicator').dataset.state !== 'unknown') {
  throw new Error(`unexpected pipeline data-state: ${elements.get('#pipelineLiveIndicator').dataset.state}`);
}

context.state.pipeline = {
  overall: 'error',
  components: [
    { id: 'transport', label: 'Transport', state: 'unavailable', detail: 'down' },
    { id: 'executor', label: 'Executor', state: 'available', detail: 'ready' },
  ],
  events: [],
  active_mission_state: null,
  latency: {},
};
context.renderPipeline();
if (elements.get('#onlineLabel').textContent !== 'Indisponible' || elements.get('#chatgptIndicator').dataset.state !== 'offline') {
  throw new Error('unavailable transport did not become offline');
}
if (elements.get('#executorStatusLabel').textContent !== 'Disponible' || elements.get('#executorIndicator').dataset.state !== 'online') {
  throw new Error('available executor did not remain independently online');
}
if (elements.get('#pipelineLiveLabel').textContent !== 'Indisponible' || elements.get('#pipelineLiveIndicator').dataset.state !== 'offline') {
  throw new Error('error pipeline did not become offline');
}
"""
        completed = subprocess.run(
            ["node", "-e", node_test, str(html_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
