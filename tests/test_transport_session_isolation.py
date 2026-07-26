"""Durable WebBridge conversation-session isolation regression tests."""

from __future__ import annotations

import asyncio
import importlib
import json
import re
import sys
import tempfile
import threading
import unittest
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "console"))

import chat as chat_api  # noqa: E402
import conversation_sessions  # noqa: E402
import missions as missions_api  # noqa: E402
import write_slots  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from orchestration.store import Store  # noqa: E402
from transport.chatgpt_web.adapter import WebBridgeDriver


class SessionAwareFakeDaemon:
    """Records the WebBridge session and target URL for every command."""

    def __init__(self) -> None:
        self.commands: list[dict] = []
        self.targets: dict[str, str] = {}
        self.messages: dict[str, list[str]] = defaultdict(list)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                owner.commands.append(payload)
                session = payload["session"]
                action = payload["action"]
                args = payload.get("args") or {}
                data: dict = {}
                if action == "navigate":
                    owner.targets[session] = args["url"]
                elif action == "evaluate":
                    match = re.search(r'\(("(?:\\.|[^"\\])*")\)\s*$', args.get("code", ""))
                    if match:
                        owner.messages[session].append(json.loads(match.group(1)))
                    data = {"value": json.dumps({"ok": True})}
                body = json.dumps({"ok": True, "data": data}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def start(self) -> "SessionAwareFakeDaemon":
        self.thread.start()
        return self

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()


class ConversationSessionContractTest(unittest.TestCase):
    def test_registry_contract_is_available(self) -> None:
        try:
            module = importlib.import_module("console.conversation_sessions")
        except ModuleNotFoundError:
            module = None

        self.assertIsNotNone(
            module,
            "console.conversation_sessions must provide the durable session registry",
        )

    def test_registry_exposes_runtime_contract(self) -> None:
        registry = conversation_sessions.ConversationSessionRegistry
        missing = [
            name
            for name in (
                "acquire_writer",
                "rekey",
                "release_writer",
                "restore_writer",
                "active_leases",
            )
            if not hasattr(registry, name)
        ]
        self.assertEqual(missing, [])

    def test_session_lease_contract_is_available(self) -> None:
        missing = [
            name
            for name in ("SessionLease", "SessionCapacityError", "new_conversation_key")
            if not hasattr(conversation_sessions, name)
        ]
        self.assertEqual(missing, [])


class ConversationSessionRegistryTest(unittest.IsolatedAsyncioTestCase):
    async def test_two_distinct_conversations_get_isolated_sessions_and_refuse_third(self) -> None:
        try:
            registry = conversation_sessions.ConversationSessionRegistry(capacity=2)
            lease_a, lease_b = await __import__("asyncio").gather(
                registry.acquire_writer("https://chatgpt.com/c/a"),
                registry.acquire_writer("https://chatgpt.com/c/b"),
            )
        except (NotImplementedError, TypeError):
            self.fail("writer acquisition is not implemented")

        self.assertNotEqual(lease_a.session_id, lease_b.session_id)
        self.assertTrue(lease_a.session_id.startswith("cortex-conv-"))
        self.assertTrue(lease_b.session_id.startswith("cortex-conv-"))
        with self.assertRaises(conversation_sessions.SessionCapacityError):
            await registry.acquire_writer("https://chatgpt.com/c/c")

    async def test_same_conversation_writer_is_serialized_on_one_stable_session(self) -> None:
        registry = conversation_sessions.ConversationSessionRegistry(capacity=2)
        first = await registry.acquire_writer("https://chatgpt.com/c/a/")
        waiting = asyncio.create_task(
            registry.acquire_writer("https://chatgpt.com/c/a")
        )
        await asyncio.sleep(0)
        self.assertFalse(waiting.done())

        await registry.release_writer(first.conversation_key)
        second = await asyncio.wait_for(waiting, timeout=1)
        self.assertEqual(second.session_id, first.session_id)
        await registry.release_writer(second.conversation_key)

    async def test_provisional_key_is_unique_and_rekeys_without_changing_session(self) -> None:
        provisional = conversation_sessions.new_conversation_key()
        other = conversation_sessions.new_conversation_key()
        self.assertNotEqual(provisional, other)
        self.assertTrue(provisional.startswith("provisional:"))

        registry = conversation_sessions.ConversationSessionRegistry(capacity=2)
        lease = await registry.acquire_writer(provisional)
        canonical = "https://chatgpt.com/c/canonical"
        rekeyed = await registry.rekey(provisional, canonical)

        self.assertIs(rekeyed, lease)
        self.assertEqual(rekeyed.conversation_key, canonical)
        self.assertEqual(
            [(item.conversation_key, item.session_id) for item in registry.active_leases()],
            [(canonical, lease.session_id)],
        )

    async def test_restore_reserves_capacity_and_release_is_exactly_once(self) -> None:
        registry = conversation_sessions.ConversationSessionRegistry(capacity=2)
        restored = registry.restore_writer(
            "https://chatgpt.com/c/a",
            "cortex-conv-persisted",
            "https://chatgpt.com/c/a",
        )
        lease_b = await registry.acquire_writer("https://chatgpt.com/c/b")
        with self.assertRaises(conversation_sessions.SessionCapacityError):
            await registry.acquire_writer("https://chatgpt.com/c/c")

        await registry.release_writer(restored.conversation_key)
        await registry.release_writer(restored.conversation_key)
        lease_c = await registry.acquire_writer("https://chatgpt.com/c/c")
        self.assertEqual(
            {item.session_id for item in registry.active_leases()},
            {lease_b.session_id, lease_c.session_id},
        )


class WebBridgeSessionIsolationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.daemon = SessionAwareFakeDaemon().start()

    async def asyncTearDown(self) -> None:
        await asyncio.to_thread(self.daemon.close)

    async def test_a_and_b_commands_stay_in_their_writer_sessions_and_view_is_separate(self) -> None:
        registry = conversation_sessions.ConversationSessionRegistry(capacity=2)
        url_a = "https://chatgpt.com/c/a"
        url_b = "https://chatgpt.com/c/b"
        lease_a, lease_b = await asyncio.gather(
            registry.acquire_writer(url_a),
            registry.acquire_writer(url_b),
        )

        async def write(lease, url: str, text: str) -> WebBridgeDriver:
            driver = WebBridgeDriver(daemon=self.daemon.url, session=lease.session_id)
            await driver.navigate(url)
            await driver.send_message(text)
            return driver

        driver_a, driver_b = await asyncio.gather(
            write(lease_a, url_a, "message-a"),
            write(lease_b, url_b, "message-b"),
        )
        view_session = "cortex-view-read-only"
        view = WebBridgeDriver(daemon=self.daemon.url, session=view_session)
        await view.navigate(url_a)
        await view.navigate(url_b)

        self.assertEqual(self.daemon.targets[lease_a.session_id], url_a)
        self.assertEqual(self.daemon.targets[lease_b.session_id], url_b)
        self.assertEqual(self.daemon.messages[lease_a.session_id], ["message-a"])
        self.assertEqual(self.daemon.messages[lease_b.session_id], ["message-b"])
        self.assertEqual(getattr(driver_a, "target_url", None), url_a)
        self.assertEqual(getattr(driver_b, "target_url", None), url_b)
        self.assertNotIn(view_session, {lease_a.session_id, lease_b.session_id})
        writer_navigations = {
            command["session"]: command["args"]["url"]
            for command in self.daemon.commands
            if command["action"] == "navigate"
            and command["session"] in {lease_a.session_id, lease_b.session_id}
        }
        self.assertEqual(
            writer_navigations,
            {lease_a.session_id: url_a, lease_b.session_id: url_b},
        )


class ChatRouteSessionIsolationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.saved_registry = write_slots._registry
        self.saved_factory = chat_api.ui_transport_factory
        self.saved_optin = missions_api.optin_accepted
        self.saved_runs_file = chat_api.CHAT_RUNS_FILE
        self.saved_runs = dict(chat_api._runs)
        write_slots._registry = conversation_sessions.ConversationSessionRegistry(capacity=2)
        chat_api.CHAT_RUNS_FILE = Path(self.tmp.name) / "chat-runs.json"
        chat_api._runs.clear()
        chat_api._view_transport = None
        chat_api._view_url = None
        missions_api.optin_accepted = lambda: True
        self.finish = asyncio.Event()
        self.sessions: list[str | None] = []

        owner = self

        class HoldingTransport:
            def __init__(self, session_id: str | None):
                self.session_id = session_id
                self.lock = None

            async def select_conversation(self, url: str):
                self.lock = SimpleNamespace(url=url, identity=url.rsplit("/", 1)[-1])
                return self.lock

            async def start_new_conversation(self, url: str) -> None:
                self.lock = SimpleNamespace(url=url, identity=None)

            async def send_message(self, text: str) -> None:
                return None

            async def stream_response(self, on_update=None) -> dict:
                await owner.finish.wait()
                return {"text": "done", "code_blocks": [], "images": []}

            async def snapshot(self, *, verify_lock: bool = True) -> dict:
                return {
                    "url": self.lock.url,
                    "conversation_id": self.lock.identity,
                    "messages": [],
                }

            async def cancel_generation(self) -> None:
                return None

        def factory(session_id: str | None = None):
            self.sessions.append(session_id)
            return HoldingTransport(session_id)

        chat_api.ui_transport_factory = factory

    async def asyncTearDown(self) -> None:
        self.finish.set()
        tasks = [run.task for run in chat_api._runs.values() if run.task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        write_slots._registry = self.saved_registry
        chat_api.ui_transport_factory = self.saved_factory
        chat_api.CHAT_RUNS_FILE = self.saved_runs_file
        missions_api.optin_accepted = self.saved_optin
        chat_api._runs.clear()
        chat_api._runs.update(self.saved_runs)
        chat_api._view_transport = None
        chat_api._view_url = None
        self.tmp.cleanup()

    async def test_two_chat_routes_use_writer_leases_view_is_separate_and_third_is_409(self) -> None:
        run_a = await chat_api.send_chat(
            chat_api.ChatSendIn(
                conversation_url="https://chatgpt.com/c/a",
                text="a",
            )
        )
        run_b = await chat_api.send_chat(
            chat_api.ChatSendIn(
                conversation_url="https://chatgpt.com/c/b",
                text="b",
            )
        )
        for _ in range(20):
            if len(self.sessions) >= 2:
                break
            await asyncio.sleep(0)

        writer_sessions = self.sessions[:2]
        self.assertEqual(len(set(writer_sessions)), 2)
        self.assertTrue(all(
            session is not None and session.startswith("cortex-conv-")
            for session in writer_sessions
        ))

        await chat_api.conversation_snapshot("https://chatgpt.com/c/a")
        self.assertNotIn(self.sessions[-1], writer_sessions)

        with self.assertRaises(HTTPException) as raised:
            await chat_api.send_chat(
                chat_api.ChatSendIn(
                    conversation_url="https://chatgpt.com/c/c",
                    text="c",
                )
            )
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("brouillon est conservé", str(raised.exception.detail))
        self.assertIn(run_a["id"], chat_api._runs)
        self.assertIn(run_b["id"], chat_api._runs)


class ConversationBindingPersistenceTest(unittest.TestCase):
    def test_session_id_and_target_survive_store_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cortex.db"
            mission_id = "00000000-0000-0000-0000-000000000001"
            store = Store(path)
            store.create_mission(mission_id, "persist lease", tmp)
            try:
                store.bind_conversation(
                    "binding-1",
                    mission_id,
                    "https://chatgpt.com/c/a",
                    browser_target_id="target-a",
                    session_id="cortex-conv-persisted",
                    conversation_target="https://chatgpt.com/c/a",
                )
            except TypeError:
                self.fail("conversation binding session persistence is not implemented")
            store.close()

            reopened = Store(path)
            self.addCleanup(reopened.close)
            binding = reopened.rows("conversation_bindings", mission_id)[0]
            self.assertEqual(binding["session_id"], "cortex-conv-persisted")
            self.assertEqual(
                binding["conversation_target"],
                "https://chatgpt.com/c/a",
            )


class ChatRunRestartPersistenceTest(unittest.IsolatedAsyncioTestCase):
    async def test_non_terminal_chat_run_restores_its_exact_writer_lease(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chat-runs.json"
            path.write_text(
                json.dumps([
                    {
                        "id": "run-persisted",
                        "state": "WAITING_FOR_CHATGPT",
                        "conversation_url": "https://chatgpt.com/c/a",
                        "canonical_url": "https://chatgpt.com/c/a",
                        "conversation_key": "https://chatgpt.com/c/a",
                        "session_id": "cortex-conv-chat-persisted",
                        "text": "draft payload",
                        "new_conversation": False,
                        "response_text": "",
                        "attachment_path": "/tmp/evidence.txt",
                        "attachment_image": False,
                        "attachment_name": "evidence.txt",
                    }
                ]),
                encoding="utf-8",
            )
            saved_file = chat_api.CHAT_RUNS_FILE
            saved_runs = dict(chat_api._runs)
            saved_registry = write_slots._registry
            chat_api.CHAT_RUNS_FILE = path
            chat_api._runs.clear()
            write_slots._registry = conversation_sessions.ConversationSessionRegistry(capacity=2)
            self.addCleanup(setattr, chat_api, "CHAT_RUNS_FILE", saved_file)
            self.addCleanup(setattr, write_slots, "_registry", saved_registry)
            self.addCleanup(chat_api._runs.update, saved_runs)
            self.addCleanup(chat_api._runs.clear)

            loader = getattr(chat_api, "_load_persisted_runs", None)
            self.assertIsNotNone(loader)
            loader()

            run = chat_api._runs["run-persisted"]
            self.assertEqual(run.text, "draft payload")
            self.assertEqual(run.attachment_name, "evidence.txt")
            self.assertEqual(run.lease.session_id, "cortex-conv-chat-persisted")
            self.assertEqual(
                [lease.session_id for lease in write_slots._registry.active_leases()],
                ["cortex-conv-chat-persisted"],
            )
            await chat_api.cancel_chat_run("run-persisted")
            await chat_api.cancel_chat_run("run-persisted")
            self.assertEqual(write_slots._registry.active_leases(), ())


class MissionRouteSessionIsolationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name) / "workspace"
        self.workspace.mkdir()
        self.saved_registry = write_slots._registry
        self.saved_factory = missions_api.transport_factory
        self.saved_optin = missions_api.optin_accepted
        self.saved_store = missions_api._store
        self.saved_runner = missions_api._run_mission_task
        self.saved_runtimes = dict(missions_api._runtimes)
        self.saved_leases = dict(missions_api._mission_leases)
        self.saved_urls = dict(missions_api._mission_write_urls)
        write_slots._registry = conversation_sessions.ConversationSessionRegistry(capacity=2)
        missions_api._store = Store(Path(self.tmp.name) / "missions.db")
        missions_api._runtimes.clear()
        missions_api._mission_leases.clear()
        missions_api._mission_write_urls.clear()
        missions_api._global_stop = False
        missions_api.optin_accepted = lambda: True
        self.finish = asyncio.Event()
        self.sessions: list[str | None] = []

        def factory(session_id: str | None = None):
            self.sessions.append(session_id)
            return SimpleNamespace(lock=None)

        async def hold(rt, objective, body) -> None:
            store = missions_api.get_store()
            store.create_mission(rt.mission_id, objective, str(self.workspace))
            store.transition(rt.mission_id, "INITIALIZING_MISSION")
            await self.finish.wait()

        missions_api.transport_factory = factory
        missions_api._run_mission_task = hold

    async def asyncTearDown(self) -> None:
        self.finish.set()
        tasks = [rt.task for rt in missions_api._runtimes.values() if rt.task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if missions_api._store is not None:
            missions_api._store.close()
        write_slots._registry = self.saved_registry
        missions_api.transport_factory = self.saved_factory
        missions_api.optin_accepted = self.saved_optin
        missions_api._run_mission_task = self.saved_runner
        missions_api._store = self.saved_store
        missions_api._runtimes.clear()
        missions_api._runtimes.update(self.saved_runtimes)
        missions_api._mission_leases.clear()
        missions_api._mission_leases.update(self.saved_leases)
        missions_api._mission_write_urls.clear()
        missions_api._mission_write_urls.update(self.saved_urls)
        self.tmp.cleanup()

    async def test_two_missions_receive_distinct_writer_sessions_and_third_is_409(self) -> None:
        def body(url: str) -> missions_api.MissionIn:
            return missions_api.MissionIn(
                objective="hold writer",
                workspace=str(self.workspace),
                conversation_url=url,
                mission_id=str(__import__("uuid").uuid4()),
            )

        first = await missions_api.create_mission(body("https://chatgpt.com/c/a"))
        second = await missions_api.create_mission(body("https://chatgpt.com/c/b"))

        self.assertEqual(len(set(self.sessions)), 2)
        self.assertTrue(all(
            session is not None and session.startswith("cortex-conv-")
            for session in self.sessions
        ))
        self.assertNotEqual(
            missions_api._runtimes[first["id"]].lease.session_id,
            missions_api._runtimes[second["id"]].lease.session_id,
        )
        with self.assertRaises(HTTPException) as raised:
            await missions_api.create_mission(body("https://chatgpt.com/c/c"))
        self.assertEqual(raised.exception.status_code, 409)

    async def test_mission_cancel_releases_only_its_writer_slot(self) -> None:
        def body(url: str) -> missions_api.MissionIn:
            return missions_api.MissionIn(
                objective="hold writer",
                workspace=str(self.workspace),
                conversation_url=url,
                mission_id=str(__import__("uuid").uuid4()),
            )

        first = await missions_api.create_mission(body("https://chatgpt.com/c/a"))
        await missions_api.create_mission(body("https://chatgpt.com/c/b"))
        for _ in range(20):
            try:
                missions_api.get_store().get_mission(first["id"])
                break
            except Exception:
                await asyncio.sleep(0)
        await missions_api.cancel_mission(first["id"])
        third = await missions_api.create_mission(body("https://chatgpt.com/c/c"))
        self.assertIn(third["id"], missions_api._runtimes)
        with self.assertRaises(HTTPException) as raised:
            await missions_api.create_mission(body("https://chatgpt.com/c/d"))
        self.assertEqual(raised.exception.status_code, 409)


class MissionRestartPersistenceTest(unittest.IsolatedAsyncioTestCase):
    async def test_non_terminal_mission_rebuilds_writer_slot_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "cortex.db"
            mission_id = "00000000-0000-0000-0000-000000000002"
            store = Store(db_path)
            store.create_mission(mission_id, "recover writer", tmp)
            store.transition(mission_id, "INITIALIZING_MISSION")
            store.transition(mission_id, "SENDING_OBJECTIVE")
            store.transition(mission_id, "WAITING_FOR_CHATGPT")
            store.bind_conversation(
                "binding-restart",
                mission_id,
                "https://chatgpt.com/c/restart",
                browser_target_id="restart",
                session_id="cortex-conv-mission-persisted",
                conversation_target="https://chatgpt.com/c/restart",
            )
            store.close()

            saved_store = missions_api._store
            saved_registry = write_slots._registry
            saved_leases = dict(missions_api._mission_leases)
            saved_urls = dict(missions_api._mission_write_urls)
            missions_api._store = Store(db_path)
            missions_api._mission_leases.clear()
            missions_api._mission_write_urls.clear()
            write_slots._registry = conversation_sessions.ConversationSessionRegistry(capacity=2)
            self.addCleanup(setattr, missions_api, "_store", saved_store)
            self.addCleanup(setattr, write_slots, "_registry", saved_registry)
            self.addCleanup(missions_api._mission_leases.clear)
            self.addCleanup(missions_api._mission_leases.update, saved_leases)
            self.addCleanup(missions_api._mission_write_urls.clear)
            self.addCleanup(missions_api._mission_write_urls.update, saved_urls)

            restorer = getattr(missions_api, "_restore_persisted_leases", None)
            self.assertIsNotNone(restorer)
            restorer()

            lease = missions_api._mission_leases[mission_id]
            self.assertEqual(lease.session_id, "cortex-conv-mission-persisted")
            self.assertEqual(
                missions_api._store.get_mission(mission_id)["state"],
                "PAUSED_RECOVERY_REQUIRED",
            )
            with self.assertRaises(conversation_sessions.SessionCapacityError):
                await write_slots.acquire_writer("https://chatgpt.com/c/b")
                await write_slots.acquire_writer("https://chatgpt.com/c/c")
            await lease.release()
            missions_api._store.close()


class MissionProvisionalRekeyTest(unittest.IsolatedAsyncioTestCase):
    async def test_new_mission_binding_rekeys_when_canonical_url_appears(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            saved_store = missions_api._store
            saved_registry = write_slots._registry
            saved_leases = dict(missions_api._mission_leases)
            missions_api._store = Store(Path(tmp) / "cortex.db")
            missions_api._mission_leases.clear()
            write_slots._registry = conversation_sessions.ConversationSessionRegistry(capacity=2)
            self.addCleanup(setattr, missions_api, "_store", saved_store)
            self.addCleanup(setattr, write_slots, "_registry", saved_registry)
            self.addCleanup(missions_api._mission_leases.clear)
            self.addCleanup(missions_api._mission_leases.update, saved_leases)

            mission_id = "00000000-0000-0000-0000-000000000003"
            provisional = write_slots.new_conversation_key()
            lease = await write_slots.acquire_writer(provisional)
            missions_api._store.create_mission(mission_id, "new chat", tmp)
            missions_api._store.bind_conversation(
                "binding-new",
                mission_id,
                "https://chatgpt.com",
            )
            runtime = missions_api.MissionRuntime(
                mission_id=mission_id,
                conversation_key=provisional,
                lease=lease,
            )
            persistence = asyncio.create_task(
                missions_api._persist_mission_lease(runtime)
            )
            await asyncio.sleep(0)
            canonical = "https://chatgpt.com/c/canonical-mission"
            missions_api._store.update_conversation_binding(
                mission_id,
                canonical,
                browser_target_id="canonical-mission",
            )
            await asyncio.wait_for(persistence, timeout=1)

            self.assertEqual(runtime.lease.conversation_key, canonical)
            self.assertEqual(
                [item.conversation_key for item in write_slots._registry.active_leases()],
                [canonical],
            )
            await runtime.lease.release()
            missions_api._store.close()


if __name__ == "__main__":
    unittest.main()
