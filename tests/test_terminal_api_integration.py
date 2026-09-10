"""Terminal-to-FastAPI boundary tests with CORTEX_HOME isolated before imports."""

from __future__ import annotations

import os
import asyncio
import socket
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

_HOME = tempfile.TemporaryDirectory()
os.environ["CORTEX_HOME"] = str(Path(_HOME.name) / "cortex-home")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "console"))

import uvicorn  # noqa: E402

import missions as missions_api  # noqa: E402
import server as console_server  # noqa: E402
import settings as settings_api  # noqa: E402
import write_slots  # noqa: E402
from conversation_sessions import ConversationSessionRegistry  # noqa: E402
from terminal_app import TerminalApp  # noqa: E402
from terminal_client import ApiClient, ApiError  # noqa: E402


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class TerminalApiIntegrationTestCase(unittest.TestCase):
    """A real loopback FastAPI server; no browser or provider traffic occurs."""

    @classmethod
    def setUpClass(cls):
        cls.port = _free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.httpd = uvicorn.Server(uvicorn.Config(
            console_server.app, host="127.0.0.1", port=cls.port, log_level="error",
        ))
        cls.thread = threading.Thread(target=cls.httpd.run, daemon=True)
        cls.thread.start()
        deadline = time.time() + 10
        client = ApiClient(cls.base_url)
        while time.time() < deadline:
            try:
                client.request("GET", "/api/status")
                break
            except Exception:
                time.sleep(0.05)
        else:
            raise RuntimeError("terminal FastAPI fixture did not start")

    @classmethod
    def tearDownClass(cls):
        cls.httpd.should_exit = True
        cls.thread.join(timeout=5)
        missions_api.close_store()
        _HOME.cleanup()

    def app(self, answers=()):
        output = []
        iterator = iter(answers)
        return TerminalApp(
            ApiClient(self.base_url), input_fn=lambda _prompt: next(iterator), output=output.append,
        ), output

    def test_explicit_consent_reaches_real_api_without_browser_access(self):
        app, output = self.app(["oui"])

        self.assertTrue(app.execute("/consentement"))
        transport = ApiClient(self.base_url).request("GET", "/api/transport/status")
        self.assertTrue(transport["opt_in_accepted"])
        self.assertIn("experimental", "\n".join(output).lower())

    def test_terminal_settings_merge_preserves_server_capabilities_over_real_api(self):
        settings = settings_api.load_settings()
        settings["process_capabilities"] = {"custom": "kept-server-side"}
        settings_api.save_settings(settings)
        app, _ = self.app(["oui"])

        self.assertTrue(app.execute("/reglage theme light"))
        current = ApiClient(self.base_url).request("GET", "/api/settings")
        self.assertEqual(current["theme"], "light")
        self.assertEqual(current["process_capabilities"], {"custom": "kept-server-side"})

    def test_selected_mission_stop_uses_only_that_mission_cancel_route(self):
        mission_id = str(uuid.uuid4())
        workspace = Path(_HOME.name) / f"workspace-{mission_id}"
        workspace.mkdir()
        store = missions_api.get_store()
        store.create_mission(mission_id, "fixture", str(workspace))
        app, _ = self.app()
        app.selected_mission_id = mission_id

        self.assertTrue(app.execute("/stop"))
        detail = ApiClient(self.base_url).request("GET", f"/api/missions/{mission_id}")
        self.assertEqual(detail["mission"]["state"], "CANCELLED")
        self.assertFalse(missions_api._global_stop)

    def test_real_api_refuses_third_writer_and_terminal_keeps_its_draft(self):
        original = write_slots._registry
        write_slots._registry = ConversationSessionRegistry(capacity=2)
        first = asyncio.run(write_slots.acquire_writer("https://chatgpt.com/c/first"))
        second = asyncio.run(write_slots.acquire_writer("https://chatgpt.com/c/second"))
        try:
            app, output = self.app()
            app.conversation_url = "https://chatgpt.com/c/third"
            app.new_conversation = False

            self.assertTrue(app.execute("brouillon à garder"))
            self.assertEqual(app.conversation_url, "https://chatgpt.com/c/third")
            self.assertIn("deux conversations", "\n".join(output).lower())
        finally:
            asyncio.run(first.release())
            asyncio.run(second.release())
            write_slots._registry = original

    def test_real_api_accepts_only_the_fresh_scoped_pending_approval(self):
        mission_id = str(uuid.uuid4())
        action_id = str(uuid.uuid4())
        workspace = Path(_HOME.name) / f"approval-{mission_id}"
        workspace.mkdir()
        store = missions_api.get_store()
        store.create_mission(mission_id, "fixture", str(workspace))
        for state in ("INITIALIZING_MISSION", "SENDING_OBJECTIVE", "WAITING_FOR_CHATGPT",
                      "PARSING_DECISION", "WAITING_FOR_APPROVAL"):
            store.transition(mission_id, state)
        decision = {
            "actionId": action_id,
            "action": {"tool": "write_file", "arguments": {"path": "proof.txt", "content": "x"}},
        }
        store.record_decision(str(uuid.uuid4()), mission_id, action_id, 1, decision, valid=True)
        store.record_policy_decision(
            str(uuid.uuid4()), mission_id, action_id, "write_file",
            allowed=True, requires_approval=True,
        )
        runtime = missions_api.MissionRuntime(mission_id)
        runtime.pending_approval_action_id = action_id
        missions_api._runtimes[mission_id] = runtime
        try:
            app, output = self.app(["oui"])
            app.selected_mission_id = mission_id

            self.assertTrue(app.execute("/autoriser"))
            self.assertTrue(runtime.approval_event.is_set())
            self.assertEqual(runtime.approval_scope, "once")
            self.assertIn("proof.txt", "\n".join(output))
        finally:
            missions_api._runtimes.pop(mission_id, None)

    def test_real_api_rejects_stale_expected_approval_action_before_signalling_runtime(self):
        mission_id = str(uuid.uuid4())
        workspace = Path(_HOME.name) / f"stale-{mission_id}"
        workspace.mkdir()
        store = missions_api.get_store()
        store.create_mission(mission_id, "fixture", str(workspace))
        for state in ("INITIALIZING_MISSION", "SENDING_OBJECTIVE", "WAITING_FOR_CHATGPT",
                      "PARSING_DECISION", "WAITING_FOR_APPROVAL"):
            store.transition(mission_id, state)
        runtime = missions_api.MissionRuntime(mission_id)
        runtime.pending_approval_action_id = "current-action"
        missions_api._runtimes[mission_id] = runtime
        try:
            with self.assertRaises(ApiError) as raised:
                ApiClient(self.base_url).request(
                    "POST", f"/api/missions/{mission_id}/approve",
                    {"scope": "once", "approve": True, "expected_action_id": "stale-action"},
                )
            self.assertEqual(raised.exception.status, 409)
            self.assertFalse(runtime.approval_event.is_set())
        finally:
            missions_api._runtimes.pop(mission_id, None)
