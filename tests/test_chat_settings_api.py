"""Conversation UI and settings API regression tests.

The suite drives the real FastAPI application against the local ChatGPT HTML
fixture. It never opens the user's browser and never sends traffic to
chatgpt.com. It covers the conversation-first endpoints added for the new
Preuvia-inspired UI.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "console"))

import uvicorn  # noqa: E402

import chat as chat_api  # noqa: E402
import missions as missions_api  # noqa: E402
import onboarding as onboarding_api  # noqa: E402
import server as console_server  # noqa: E402
import settings as settings_api  # noqa: E402
from orchestration.store import Store  # noqa: E402
from transport.chatgpt_web.adapter import ChatGPTWebTransport, LocalFixtureDriver  # noqa: E402
from transport.chatgpt_web.fixture import FixtureServer  # noqa: E402


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class FakeBrowserDriver:
    """Small settings/pipeline fake — no real Chrome access in tests."""

    selected = "ChatGPT 5.6 Pro"
    open_login_calls = 0
    fail_login = False
    driver_name = "playwright"

    def __init__(self, *args, **kwargs):
        pass

    async def navigate(self, url: str) -> None:
        self.url = url

    async def health(self) -> dict:
        return {"connected": True, "tabs": 1, "driver": self.driver_name}

    async def open_login(self) -> dict:
        type(self).open_login_calls += 1
        if type(self).fail_login:
            raise RuntimeError("browser launch failed")
        return await self.health()

    async def list_models(self) -> dict:
        return {
            "current": self.selected,
            "models": ["ChatGPT 5.6 Pro", "ChatGPT 5.6 Thinking"],
            "error": None,
        }

    async def select_model(self, label: str) -> str:
        if label not in {"ChatGPT 5.6 Pro", "ChatGPT 5.6 Thinking"}:
            raise RuntimeError("requested model not visible")
        type(self).selected = label
        return label


class ChatSettingsApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        root = Path(cls._tmp.name)
        cls.fixture = FixtureServer().start()

        cls.original_validate_url = chat_api._validate_chatgpt_url
        cls.original_settings_driver_factory = settings_api.browser_driver_factory
        cls.original_onboarding_driver_factory = onboarding_api.browser_driver_factory
        cls.original_settings_file = settings_api.SETTINGS_FILE
        cls.original_settings_db = settings_api.DB_PATH
        cls.original_chat_runs_file = chat_api.CHAT_RUNS_FILE
        cls.original_store = missions_api._store
        cls.original_optin = missions_api.OPTIN_FILE

        # Fixture URLs are loopback HTTP; production validation remains strict.
        chat_api._validate_chatgpt_url = lambda url: url.strip()
        chat_api.ui_transport_factory = lambda: ChatGPTWebTransport(
            LocalFixtureDriver(cls.fixture.base_url),
            stability_interval=0.12,
            poll_interval=0.03,
            max_wait=5.0,
        )
        chat_api.CHAT_RUNS_FILE = root / "chat-runs.json"
        chat_api._runs.clear()
        chat_api._view_transport = None
        chat_api._view_url = None

        missions_api._store = Store(root / "cortex.db")
        missions_api.OPTIN_FILE = root / "transport-optin.json"
        missions_api._global_stop = False
        missions_api._runtimes.clear()

        settings_api.SETTINGS_FILE = root / "settings.json"
        settings_api.DB_PATH = root / "cortex.db"
        settings_api.browser_driver_factory = lambda **_kwargs: FakeBrowserDriver()
        onboarding_api.browser_driver_factory = lambda **_kwargs: FakeBrowserDriver()

        cls.port = free_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        config = uvicorn.Config(
            console_server.app,
            host="127.0.0.1",
            port=cls.port,
            log_level="error",
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
                time.sleep(0.08)
        else:
            raise RuntimeError("test server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.httpd.should_exit = True
        cls.thread.join(timeout=5)
        cls.fixture.stop()
        if missions_api._store is not None:
            missions_api._store.close()
        missions_api._store = cls.original_store
        missions_api.OPTIN_FILE = cls.original_optin
        settings_api.SETTINGS_FILE = cls.original_settings_file
        settings_api.DB_PATH = cls.original_settings_db
        settings_api.browser_driver_factory = cls.original_settings_driver_factory
        onboarding_api.browser_driver_factory = cls.original_onboarding_driver_factory
        chat_api.CHAT_RUNS_FILE = cls.original_chat_runs_file
        chat_api._validate_chatgpt_url = cls.original_validate_url
        cls._tmp.cleanup()

    def setUp(self):
        FakeBrowserDriver.open_login_calls = 0
        FakeBrowserDriver.fail_login = False
        missions_api._global_stop = False
        missions_api.OPTIN_FILE.unlink(missing_ok=True)
        settings_api.SETTINGS_FILE.unlink(missing_ok=True)
        chat_api._runs.clear()
        chat_api._view_transport = None
        chat_api._view_url = None
        self.conv = f"ui-{uuid.uuid4().hex[:8]}"
        self.url = f"{self.fixture.base_url}/c/{self.conv}"
        self.fixture.conversation(self.conv)

    @classmethod
    def request(cls, method: str, path: str, payload=None, timeout=15):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            cls.base + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(raw)
            except json.JSONDecodeError:
                return exc.code, {"detail": raw}

    @classmethod
    def get(cls, path: str):
        return cls.request("GET", path)

    @classmethod
    def post(cls, path: str, payload=None):
        return cls.request("POST", path, payload or {})

    @classmethod
    def put(cls, path: str, payload=None):
        return cls.request("PUT", path, payload or {})

    def optin(self):
        status, body = self.post("/api/transport/opt-in", {"accepted": True})
        self.assertEqual(status, 200, body)

    def wait_chat(self, run_id: str, terminal=True, timeout=10):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            _, last = self.get(f"/api/chat/runs/{run_id}")
            if not terminal or last["state"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                return last
            time.sleep(0.05)
        self.fail(f"chat run did not finish: {last}")

    def test_01_chat_send_requires_transport_optin(self):
        status, body = self.post("/api/chat/send", {
            "conversation_url": self.url,
            "text": "hello",
        })
        self.assertEqual(status, 403)
        self.assertIn("Experimental", body["detail"])

    def test_02_snapshot_reads_selected_conversation(self):
        conv = self.fixture.conversation(self.conv)
        conv.add_message("user", "Question visible")
        conv.add_message("assistant", "Réponse visible")
        path = "/api/conversations/snapshot?" + urllib.parse.urlencode({"url": self.url})
        status, body = self.get(path)
        self.assertEqual(status, 200, body)
        self.assertEqual(body["conversation_id"], self.conv)
        self.assertEqual([m["role"] for m in body["messages"]], ["user", "assistant"])
        self.assertIn("Réponse visible", body["messages"][-1]["text"])

    def test_03_send_confirms_delivery_and_streams_response(self):
        self.optin()
        self.fixture.queue_replies(["Visible streamed answer"], self.conv)
        self.fixture.set_streaming(chunks=4, interval=0.04, cid=self.conv)
        status, run = self.post("/api/chat/send", {
            "conversation_url": self.url,
            "text": "Run the UI transport test",
        })
        self.assertEqual(status, 202, run)
        final = self.wait_chat(run["id"])
        self.assertEqual(final["state"], "COMPLETED", final)
        self.assertEqual(final["response_text"], "Visible streamed answer")
        self.assertIsNotNone(final["delivered_at"])
        self.assertIsNotNone(final["first_response_at"])
        self.assertGreaterEqual(final["latency"]["delivery_ms"], 0)
        messages = self.fixture.conversation(self.conv).messages
        self.assertEqual(sum(m["role"] == "user" for m in messages), 1)
        status, runs = self.get("/api/chat/runs")
        self.assertEqual(status, 200)
        self.assertEqual(runs[0]["id"], run["id"])

    def test_04_chat_cancel_is_idempotent(self):
        self.optin()
        self.fixture.queue_replies(["A deliberately slow response"], self.conv)
        self.fixture.set_streaming(chunks=100, interval=0.08, cid=self.conv)
        status, run = self.post("/api/chat/send", {
            "conversation_url": self.url,
            "text": "slow",
        })
        self.assertEqual(status, 202, run)
        deadline = time.time() + 5
        while time.time() < deadline:
            _, current = self.get(f"/api/chat/runs/{run['id']}")
            if current["state"] in {"WAITING_FOR_CHATGPT", "CHATGPT_STREAMING"}:
                break
            time.sleep(0.04)
        status, cancelled = self.post(f"/api/chat/runs/{run['id']}/cancel", {})
        self.assertEqual(status, 200)
        self.assertEqual(cancelled["state"], "CANCELLED")
        status, again = self.post(f"/api/chat/runs/{run['id']}/cancel", {})
        self.assertEqual(status, 200)
        self.assertEqual(again["state"], "CANCELLED")

    def test_05_stop_everything_blocks_normal_chat(self):
        self.optin()
        missions_api._global_stop = True
        status, body = self.post("/api/chat/send", {
            "conversation_url": self.url,
            "text": "must not send",
        })
        self.assertEqual(status, 409)
        self.assertIn("STOP EVERYTHING", body["detail"])
        self.assertEqual(self.fixture.conversation(self.conv).messages, [])

    def test_06_settings_persist_and_never_delete_is_forced(self):
        status, defaults = self.get("/api/settings")
        self.assertEqual(status, 200)
        self.assertEqual(
            defaults.get("process_capabilities"),
            {"allowed": False, "allow_network": False, "allow_deletions": False},
        )
        self.assertEqual(defaults["browser_transport"], "playwright")
        self.assertEqual(defaults["browser_profile_root"], "console/data/browser-profiles")
        payload = {
            **defaults,
            "theme": "light",
            "never_delete_files": False,
            "default_workspace": str(Path(self._tmp.name).resolve()),
        }
        status, saved = self.put("/api/settings", payload)
        self.assertEqual(status, 200, saved)
        self.assertEqual(saved["theme"], "light")
        self.assertTrue(saved["never_delete_files"])
        _, reloaded = self.get("/api/settings")
        self.assertEqual(reloaded, saved)

        status, invalid = self.put("/api/settings", {
            **defaults,
            "browser_transport": "selenium",
            "default_workspace": str(Path(self._tmp.name).resolve()),
        })
        self.assertEqual(status, 422, invalid)

    def test_07_lab_mode_is_fail_closed(self):
        _, defaults = self.get("/api/settings")
        payload = {
            **defaults,
            "access_profile": "lab",
            "default_workspace": str(Path(self._tmp.name).resolve()),
        }
        previous = os.environ.pop("CORTEX_ALLOW_LAB_MODE", None)
        try:
            status, body = self.put("/api/settings", payload)
            self.assertEqual(status, 403)
            self.assertIn("CORTEX_ALLOW_LAB_MODE", body["detail"])
        finally:
            if previous is not None:
                os.environ["CORTEX_ALLOW_LAB_MODE"] = previous

    def test_08_chatgpt_model_list_and_selection_are_confirmed(self):
        status, body = self.get("/api/models/chatgpt")
        self.assertEqual(status, 200, body)
        labels = [row["label"] for row in body["models"]]
        self.assertIn("ChatGPT 5.6 Pro", labels)
        self.optin()
        status, selected = self.put("/api/models/chatgpt", {
            "conversation_url": "https://chatgpt.com/c/test",
            "label": "ChatGPT 5.6 Thinking",
        })
        self.assertEqual(status, 200, selected)
        self.assertTrue(selected["confirmed"])
        self.assertEqual(selected["selected"], "ChatGPT 5.6 Thinking")
        status, invalid = self.put("/api/models/chatgpt", {
            "conversation_url": "https://chatgpt.com/c/test",
            "label": "Invisible model",
        })
        self.assertEqual(status, 503)
        self.assertIn("cannot confirm", invalid["detail"])

    def test_09_pipeline_status_has_required_components(self):
        status, body = self.get("/api/pipeline/status")
        self.assertEqual(status, 200, body)
        ids = {row["id"] for row in body["components"]}
        self.assertTrue({
            "transport", "validator", "task", "ollama", "executor",
            "filesystem", "database",
        }.issubset(ids))
        self.assertIn(body["overall"], {"healthy", "degraded", "running", "waiting"})
        self.assertIn("events", body)
        transport = next(row for row in body["components"] if row["id"] == "transport")
        self.assertIn("playwright", transport["detail"].lower())
        ollama = next(row for row in body["components"] if row["id"] == "ollama")
        executor = next(row for row in body["components"] if row["id"] == "executor")
        self.assertEqual(ollama["label"], "Disponibilité Ollama")
        self.assertEqual(executor["label"], "Exécuteur réellement utilisé")
        self.assertEqual(
            body["runtime_execution"],
            {
                "task_id": None,
                "executor_kind": "unavailable",
                "executor_model_used": None,
                "runtime_mode": "live",
                "release_eligible": False,
                "state": "idle",
                "active": False,
                "observed_at": None,
            },
        )

    def test_10_onboarding_opens_dedicated_login_profile(self):
        status, body = self.post("/api/onboarding/browser/open", {})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["driver"], "playwright")
        self.assertTrue(body["connected"])
        self.assertEqual(FakeBrowserDriver.open_login_calls, 1)

    def test_10b_onboarding_browser_failure_is_structured_non_2xx(self):
        FakeBrowserDriver.fail_login = True
        status, body = self.post("/api/onboarding/browser/open", {})
        self.assertEqual(status, 503, body)
        self.assertEqual(body["detail"]["code"], "BROWSER_LOGIN_FAILED")
        self.assertEqual(body["detail"]["driver"], "playwright")

    def test_10c_browser_profile_root_rejects_traversal_and_symlinks(self):
        _, defaults = self.get("/api/settings")
        status, _ = self.put("/api/settings", {
            **defaults,
            "browser_profile_root": "../../outside",
            "default_workspace": str(Path(self._tmp.name).resolve()),
        })
        self.assertEqual(status, 422)

        outside = Path(self._tmp.name) / "outside-profile"
        outside.mkdir(exist_ok=True)
        link = Path(self._tmp.name) / "profile-link"
        link.symlink_to(outside, target_is_directory=True)
        status, _ = self.put("/api/settings", {
            **defaults,
            "browser_profile_root": str(link),
            "default_workspace": str(Path(self._tmp.name).resolve()),
        })
        self.assertEqual(status, 422)

    def test_10d_loaded_invalid_browser_settings_fail_closed_and_external_paths_are_anonymized(self):
        settings_api.SETTINGS_FILE.write_text(json.dumps({
            "browser_transport": "selenium",
            "browser_profile_root": "",
        }), encoding="utf-8")
        with self.assertRaises(ValueError):
            settings_api.load_settings()
        anonymized = settings_api._anonymize("/Volumes/ClientSecret/browser-profile")
        self.assertNotIn("Volumes", anonymized)
        self.assertNotIn("ClientSecret", anonymized)

    def test_10e_onboarding_invalid_persisted_browser_settings_are_structured(self):
        settings_api.SETTINGS_FILE.write_text(json.dumps({
            "browser_transport": "selenium",
            "browser_profile_root": "console/data/browser-profiles",
        }), encoding="utf-8")

        status, body = self.post("/api/onboarding/browser/open", {})

        self.assertEqual(status, 503, body)
        self.assertEqual(body, {
            "detail": {
                "code": "BROWSER_LOGIN_FAILED",
                "driver": "unknown",
                "error": (
                    "browser_transport must be exactly one of: "
                    "playwright, webbridge"
                ),
            },
        })

    def test_11_modern_fallback_ui_is_served(self):
        req = urllib.request.Request(self.base + "/", method="GET")
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode("utf-8")
        modern = REPO_ROOT / "frontend" / "out" / "index.html"
        if modern.is_file():
            # Built Next.js export takes priority (it ships in the repo).
            self.assertIn("Cortex Bridge — Local orchestration client", html)
        else:
            self.assertIn('<span class="word">Cortex<b>Bridge</b></span>', html)
            self.assertIn("Mission autonome", html)
            self.assertIn("gridfx", html)
        # The standalone safety net must always ship, whatever is served.
        fallback = REPO_ROOT / "frontend" / "fallback" / "index.html"
        self.assertTrue(fallback.is_file())
        fallback_html = fallback.read_text(encoding="utf-8")
        self.assertIn('<span class="word">Cortex<b>Bridge</b></span>', fallback_html)
        self.assertIn("Mission autonome", fallback_html)



if __name__ == "__main__":
    unittest.main()
