"""Phase 6 — autonomous-mission API tests (fixture transport only).

Runs the real FastAPI console (uvicorn in a thread, random loopback port)
with the WebBridge driver replaced by the §22 local fixture. Never touches
the real daemon or real ChatGPT. stdlib unittest:
    python3 -m unittest discover -s tests -v

Determinism note: the fixture pops a queued reply at the moment a user
message arrives, so tests pre-compute the mission id (client-supplied
mission_id, supported by the API) and queue the assistant replies BEFORE
starting the mission.
"""

from __future__ import annotations

import json
import socket
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

import missions as missions_api  # noqa: E402  (console/missions.py)
import server as console_server  # noqa: E402  (console/server.py)
import write_slots  # noqa: E402
from conversation_sessions import ConversationSessionRegistry  # noqa: E402
from orchestration.store import Store  # noqa: E402
from transport.chatgpt_web.adapter import (  # noqa: E402
    ChatGPTWebTransport,
    LocalFixtureDriver,
)
from transport.chatgpt_web.fixture import FixtureServer  # noqa: E402


def decision_reply(mission_id, iteration, state, tool=None, arguments=None,
                   criteria=None, terminal=False):
    decision = {
        "protocol": "cortex.v1",
        "missionId": mission_id,
        "actionId": str(uuid.uuid4()),
        "iteration": iteration,
        "state": state,
        "summary": f"api-fixture decision {iteration}",
        "action": {"tool": tool, "arguments": arguments or {}} if tool else None,
        "acceptanceCriteria": criteria if criteria is not None else ["criterion"],
        "requiresApproval": False,
        "terminal": terminal,
    }
    return "Decision:\n```cortex-decision\n" + json.dumps(decision, indent=2) + "\n```"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class MissionsApiTestCase(unittest.TestCase):
    """One shared app server + fixture; per-test workspaces/conversations."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        cls.fixture = FixtureServer().start()
        cls.store_path = tmp / "cortex.db"
        cls.original_store = missions_api._store
        cls.original_optin_file = missions_api.OPTIN_FILE
        cls.original_transport_factory = missions_api.transport_factory
        cls.original_writer_registry = write_slots._registry
        cls.original_mission_leases = dict(missions_api._mission_leases)
        cls.original_mission_write_urls = dict(missions_api._mission_write_urls)
        write_slots._registry = ConversationSessionRegistry(capacity=2)
        missions_api._mission_leases.clear()
        missions_api._mission_write_urls.clear()
        missions_api._store = Store(cls.store_path)
        missions_api.OPTIN_FILE = tmp / "transport-optin.json"
        missions_api.transport_factory = lambda: ChatGPTWebTransport(
            LocalFixtureDriver(cls.fixture.base_url),
            stability_interval=0.15, poll_interval=0.03, max_wait=5.0,
        )
        cls.port = free_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        config = uvicorn.Config(
            console_server.app, host="127.0.0.1", port=cls.port, log_level="error"
        )
        cls.httpd = uvicorn.Server(config)
        cls.thread = threading.Thread(target=cls.httpd.run, daemon=True)
        cls.thread.start()
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                cls.get("/api/status")
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("test server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.httpd.should_exit = True
        cls.thread.join(timeout=5)
        cls.fixture.stop()
        missions_api._store.close()
        missions_api._store = cls.original_store
        missions_api.OPTIN_FILE = cls.original_optin_file
        missions_api.transport_factory = cls.original_transport_factory
        missions_api._mission_leases.clear()
        missions_api._mission_leases.update(cls.original_mission_leases)
        missions_api._mission_write_urls.clear()
        missions_api._mission_write_urls.update(cls.original_mission_write_urls)
        write_slots._registry = cls.original_writer_registry
        cls._tmp.cleanup()

    def setUp(self):
        missions_api._global_stop = False
        missions_api._runtimes.clear()
        self.ws = Path(tempfile.mkdtemp(dir=self._tmp.name))
        self.conv = f"conv-{uuid.uuid4().hex[:8]}"
        self.mission_id = str(uuid.uuid4())
        self.addCleanup(self._cancel_stragglers)

    # -- HTTP helpers --------------------------------------------------------

    @classmethod
    def get(cls, path):
        with urllib.request.urlopen(cls.base + path, timeout=10) as r:
            return r.status, json.loads(r.read().decode())

    @classmethod
    def post(cls, path, payload=None):
        req = urllib.request.Request(
            cls.base + path,
            data=json.dumps(payload or {}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            with e:
                body = e.read().decode()
                try:
                    return e.code, json.loads(body)
                except json.JSONDecodeError:
                    return e.code, {"detail": body}

    def wait_state(self, mission_id, want, timeout=30, extra=None):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            _, d = self.get(f"/api/missions/{mission_id}")
            last = d
            if d["mission"]["state"] == want:
                if extra is None or extra(d):
                    return d
            time.sleep(0.1)
        self.fail(f"mission {mission_id} never reached {want}; "
                  f"last={last['mission']['state'] if last else None}")

    def wait_terminal(self, mission_id, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            _, d = self.get(f"/api/missions/{mission_id}")
            if d["mission"]["state"] in ("COMPLETED", "BLOCKED", "FAILED", "CANCELLED"):
                return d
            time.sleep(0.2)
        self.fail(f"mission {mission_id} never terminated")

    def _cancel_stragglers(self):
        for rt in list(missions_api._runtimes.values()):
            rt.stopped = True
            rt.approval_event.set()

    def optin(self, accepted=True):
        status, _ = self.post("/api/transport/opt-in", {"accepted": accepted})
        self.assertEqual(status, 200)

    def start_mission(self, replies, objective="test objective", **overrides):
        """Queue scripted assistant replies, then start the mission."""
        self.fixture.queue_replies(replies, self.conv)
        payload = {
            "objective": objective,
            "workspace": str(self.ws),
            "conversation_url": f"{self.fixture.base_url}/c/{self.conv}",
            "approval_policy": "workspace-write-automatic",
            "mission_id": self.mission_id,
        }
        payload.update(overrides)
        return self.post("/api/missions", payload)

    # -- tests ---------------------------------------------------------------

    def test_01_optin_gate_403(self):
        missions_api.OPTIN_FILE.unlink(missing_ok=True)
        status, body = self.start_mission([])
        self.assertEqual(status, 403)
        self.assertIn("Experimental", body["detail"])
        self.assertEqual(missions_api.get_store().count("missions"), 0)

    def test_02_full_mission_via_api(self):
        self.optin()
        content = "Cortex Bridge autonomous loop works"
        status, body = self.start_mission([
            decision_reply(self.mission_id, 1, "EXECUTE", tool="write_file",
                           arguments={"path": "witness.txt", "content": content},
                           criteria=["witness.txt written exactly"]),
            decision_reply(self.mission_id, 2, "COMPLETE",
                           criteria=["witness.txt exists with exact content"],
                           terminal=True),
        ], "Create witness.txt exactly.")
        self.assertEqual(status, 201, body)
        self.assertEqual(body["id"], self.mission_id)
        d = self.wait_terminal(self.mission_id)
        self.assertEqual(d["mission"]["state"], "COMPLETED")
        self.assertEqual((self.ws / "witness.txt").read_text(encoding="utf-8"), content)
        store = missions_api.get_store()
        self.assertEqual(store.count("tool_executions", self.mission_id), 1)
        self.assertEqual(store.count("conversation_bindings", self.mission_id), 1)
        decisions = store.rows("orchestrator_decisions", self.mission_id)
        self.assertTrue(all(r["valid"] == 1 for r in decisions))
        # Contract first, then one cortex-report per executed action.
        msgs = self.fixture.conversation(self.conv).messages
        user_msgs = [m["text"] for m in msgs if m["role"] == "user"]
        self.assertIn("You are the cloud orchestrator for Cortex Bridge.", user_msgs[0])
        self.assertIn("```cortex-report", user_msgs[1])

    def test_03_approval_flow(self):
        self.optin()
        status, body = self.start_mission([
            decision_reply(self.mission_id, 1, "EXECUTE", tool="write_file",
                           arguments={"path": "a.txt", "content": "A"},
                           criteria=["a.txt written"]),
            decision_reply(self.mission_id, 2, "COMPLETE", criteria=["a.txt exists"],
                           terminal=True),
        ], "Create a.txt.", approval_policy="workspace-write-with-approvals")
        self.assertEqual(status, 201, body)
        d = self.wait_state(self.mission_id, "WAITING_FOR_APPROVAL",
                            extra=lambda d: d["awaiting_approval"])
        self.assertTrue(d["awaiting_approval"])
        status, _ = self.post(f"/api/missions/{self.mission_id}/approve",
                              {"scope": "once", "approve": True})
        self.assertEqual(status, 200)
        d = self.wait_terminal(self.mission_id)
        self.assertEqual(d["mission"]["state"], "COMPLETED")
        self.assertEqual((self.ws / "a.txt").read_text(encoding="utf-8"), "A")
        approvals = missions_api.get_store().rows("approvals", self.mission_id)
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0]["approved"], 1)

    def test_04_reject_approval_denies_action(self):
        self.optin()
        status, body = self.start_mission([
            decision_reply(self.mission_id, 1, "EXECUTE", tool="write_file",
                           arguments={"path": "b.txt", "content": "B"},
                           criteria=["b.txt written"]),
            decision_reply(self.mission_id, 2, "BLOCKED", criteria=[], terminal=True),
        ], "Create b.txt.", approval_policy="workspace-write-with-approvals")
        self.assertEqual(status, 201, body)
        self.wait_state(self.mission_id, "WAITING_FOR_APPROVAL",
                        extra=lambda d: d["awaiting_approval"])
        status, _ = self.post(f"/api/missions/{self.mission_id}/approve",
                              {"scope": "once", "approve": False})
        self.assertEqual(status, 200)
        d = self.wait_terminal(self.mission_id)
        self.assertEqual(d["mission"]["state"], "BLOCKED")
        self.assertFalse((self.ws / "b.txt").exists())  # rejected → never written
        approvals = missions_api.get_store().rows("approvals", self.mission_id)
        self.assertEqual(approvals[0]["approved"], 0)

    def test_04b_empty_complete_fails_closed(self):
        self.optin()
        status, body = self.start_mission([
            decision_reply(self.mission_id, 1, "COMPLETE", criteria=["done"], terminal=True),
            decision_reply(self.mission_id, 2, "BLOCKED", criteria=[], terminal=True),
        ], "Do not complete without local evidence.")
        self.assertEqual(status, 201, body)

        d = self.wait_terminal(self.mission_id)

        self.assertEqual(d["mission"]["state"], "BLOCKED")
        validations = missions_api.get_store().rows("validation_results", self.mission_id)
        self.assertEqual(validations[0]["passed"], 0)

    def test_05_pause_resume(self):
        self.optin()
        status, body = self.start_mission([
            decision_reply(self.mission_id, 1, "EXECUTE", tool="list_directory",
                           arguments={"path": "."}, criteria=["listing returned"]),
            decision_reply(self.mission_id, 2, "COMPLETE", criteria=["done"],
                           terminal=True),
        ], "List then complete.")
        self.assertEqual(status, 201, body)
        self.wait_state(self.mission_id, "WAITING_FOR_CHATGPT")
        status, _ = self.post(f"/api/missions/{self.mission_id}/pause")
        self.assertEqual(status, 200)
        self.wait_state(self.mission_id, "PAUSED")
        # Nothing more happens while paused.
        time.sleep(1.0)
        _, d = self.get(f"/api/missions/{self.mission_id}")
        self.assertEqual(d["mission"]["state"], "PAUSED")
        status, _ = self.post(f"/api/missions/{self.mission_id}/resume")
        self.assertEqual(status, 200)
        d = self.wait_terminal(self.mission_id)
        self.assertEqual(d["mission"]["state"], "COMPLETED")

    def test_06_cancel(self):
        self.optin()
        status, body = self.start_mission([
            decision_reply(self.mission_id, 1, "EXECUTE", tool="write_file",
                           arguments={"path": "c.txt", "content": "C"},
                           criteria=["c.txt written"]),
        ], "Create c.txt.", approval_policy="workspace-write-with-approvals")
        self.assertEqual(status, 201, body)
        self.wait_state(self.mission_id, "WAITING_FOR_APPROVAL",
                        extra=lambda d: d["awaiting_approval"])
        status, _ = self.post(f"/api/missions/{self.mission_id}/cancel")
        self.assertEqual(status, 200)
        d = self.wait_terminal(self.mission_id)
        self.assertEqual(d["mission"]["state"], "CANCELLED")
        self.assertFalse((self.ws / "c.txt").exists())

    def test_07_stop_everything(self):
        self.optin()
        status, body = self.start_mission([
            decision_reply(self.mission_id, 1, "EXECUTE", tool="write_file",
                           arguments={"path": "s.txt", "content": "S"},
                           criteria=["s.txt written"]),
        ], "Create s.txt.", approval_policy="workspace-write-with-approvals")
        self.assertEqual(status, 201, body)
        self.wait_state(self.mission_id, "WAITING_FOR_APPROVAL",
                        extra=lambda d: d["awaiting_approval"])
        status, body = self.post("/api/transport/stop-everything")
        self.assertEqual(status, 200)
        d = self.wait_terminal(self.mission_id)
        self.assertEqual(d["mission"]["state"], "CANCELLED")
        self.assertEqual(d["mission"]["pause_reason"], "STOP_EVERYTHING")
        self.assertFalse((self.ws / "s.txt").exists())
        # While the stop is active no new mission can start.
        status, _ = self.start_mission([])
        self.assertEqual(status, 409)
        # Re-arm.
        status, _ = self.post("/api/transport/stop-reset")
        self.assertEqual(status, 200)

    def test_08_restart_recovery_surfaced(self):
        self.optin()
        store = missions_api.get_store()
        mission_id = str(uuid.uuid4())
        store.create_mission(mission_id, "left running", str(self.ws))
        store.transition(mission_id, "INITIALIZING_MISSION")
        store.transition(mission_id, "SENDING_OBJECTIVE")
        store.transition(mission_id, "WAITING_FOR_CHATGPT")
        # Simulate the server restart: close + reopen the store.
        store.close()
        missions_api._store = Store(self.store_path)
        _, d = self.get(f"/api/missions/{mission_id}")
        self.assertEqual(d["mission"]["state"], "PAUSED_RECOVERY_REQUIRED")
        self.assertEqual(d["mission"]["pause_reason"], "SERVER_RESTART")
        # Cleanup so later tests see a tidy DB.
        try:
            missions_api.get_store().transition(mission_id, "CANCELLED",
                                                pause_reason="test cleanup")
        except Exception:
            pass

    def test_09_fallback_payload(self):
        self.optin()
        status, body = self.start_mission([
            decision_reply(self.mission_id, 1, "EXECUTE", tool="list_directory",
                           arguments={"path": "."}, criteria=["listing returned"]),
            decision_reply(self.mission_id, 2, "COMPLETE", criteria=["done"],
                           terminal=True),
        ], "List and complete.")
        self.assertEqual(status, 201, body)
        d = self.wait_terminal(self.mission_id)
        self.assertEqual(d["mission"]["state"], "COMPLETED")
        status, body = self.get(f"/api/missions/{self.mission_id}/fallback-payload")
        self.assertEqual(status, 200)
        self.assertIn("manual fallback payload", body["payload"])
        self.assertIn("```cortex-report", body["payload"])


    def test_10_fail_mission_from_idle(self):
        # A runner crash before the loop starts must still surface as FAILED,
        # never leave the mission stuck in IDLE.
        store = missions_api.get_store()
        mission_id = str(uuid.uuid4())
        store.create_mission(mission_id, "crash before start", str(self.ws))
        missions_api._fail_mission(store, mission_id, "simulated crash")
        _, d = self.get(f"/api/missions/{mission_id}")
        self.assertEqual(d["mission"]["state"], "FAILED")
        self.assertEqual(d["mission"]["pause_reason"], "simulated crash")

    def test_11_legacy_history_merged_read_only(self):
        # Pre-mission-API runs (chat-runs.json / iterations.json) appear in the
        # unified listing and have a detail view, without touching the DB.
        tmp = Path(self._tmp.name)
        chat_runs = tmp / "legacy-chat-runs.json"
        chat_runs.write_text(json.dumps([{
            "id": "legacy-run-1",
            "state": "completed",
            "text": "dis bonjour",
            "created_at": "2026-08-01T10:00:00+00:00",
            "completed_at": "2026-08-01T10:01:00+00:00",
            "response_text": "Bonjour",
        }]), encoding="utf-8")
        iterations = tmp / "legacy-iterations.json"
        iterations.write_text(json.dumps([{
            "id": "legacy-task-1",
            "status": "done",
            "goal": "crée un fichier",
            "started_at": "2026-08-02T10:00:00+00:00",
            "finished_at": "2026-08-02T10:02:00+00:00",
            "workspace": str(self.ws),
            "report": {"summary": "fait", "files_changed": ["a.txt"], "blockers": []},
        }]), encoding="utf-8")
        old_runs = missions_api.LEGACY_CHAT_RUNS_FILE
        old_iterations = missions_api.LEGACY_ITERATIONS_FILE
        missions_api.LEGACY_CHAT_RUNS_FILE = chat_runs
        missions_api.LEGACY_ITERATIONS_FILE = iterations
        try:
            status, rows = self.get("/api/missions")
            self.assertEqual(status, 200)
            by_id = {row["id"]: row for row in rows}
            self.assertEqual(by_id["legacy-run-1"]["state"], "COMPLETED")
            self.assertTrue(by_id["legacy-run-1"]["legacy"])
            self.assertEqual(by_id["legacy-run-1"]["legacy_source"], "chat-run")
            self.assertEqual(by_id["legacy-task-1"]["state"], "COMPLETED")
            self.assertEqual(by_id["legacy-task-1"]["legacy_source"], "console-task")
            # DB missions stay first-class and unmodified.
            self.assertEqual(
                missions_api.get_store().count("missions"),
                len([row for row in rows if not row.get("legacy")]),
            )
            # Legacy entries have a detail view.
            status, detail = self.get("/api/missions/legacy-run-1")
            self.assertEqual(status, 200)
            self.assertTrue(detail["legacy"])
            self.assertEqual(
                detail["mission"]["legacy_detail"]["response_text"], "Bonjour"
            )
            status, detail = self.get("/api/missions/legacy-task-1")
            self.assertEqual(status, 200)
            self.assertEqual(
                detail["mission"]["legacy_detail"]["files_changed"], ["a.txt"]
            )
            # Unknown ids still 404.
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.get("/api/missions/does-not-exist")
            self.assertEqual(ctx.exception.code, 404)
        finally:
            missions_api.LEGACY_CHAT_RUNS_FILE = old_runs
            missions_api.LEGACY_ITERATIONS_FILE = old_iterations


if __name__ == "__main__":
    unittest.main()
