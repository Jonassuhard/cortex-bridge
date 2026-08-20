"""Durable WebBridge conversation-session isolation regression tests."""

from __future__ import annotations

import asyncio
import importlib
import json
import re
import sqlite3
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
import transport.browser as browser_transport  # noqa: E402
from transport.chatgpt_web.adapter import (
    CONVERSATION_MISMATCH,
    TransportError,
    WebBridgeDriver,
)


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

        await first.release()
        second = await asyncio.wait_for(waiting, timeout=1)
        self.assertEqual(second.session_id, first.session_id)
        await second.release()

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

        await restored.release()
        await restored.release()
        lease_c = await registry.acquire_writer("https://chatgpt.com/c/c")
        self.assertEqual(
            {item.session_id for item in registry.active_leases()},
            {lease_b.session_id, lease_c.session_id},
        )

    async def test_cancelled_same_conversation_waiter_does_not_leak_capacity(self) -> None:
        registry = conversation_sessions.ConversationSessionRegistry(capacity=2)
        first = await registry.acquire_writer("https://chatgpt.com/c/a")
        waiter = asyncio.create_task(
            registry.acquire_writer("https://chatgpt.com/c/a")
        )
        await asyncio.sleep(0)

        await first.release()
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter

        self.assertEqual(registry.active_leases(), ())
        lease_b = await registry.acquire_writer("https://chatgpt.com/c/b")
        lease_c = await registry.acquire_writer("https://chatgpt.com/c/c")
        await lease_b.release()
        await lease_c.release()

    async def test_release_wrapper_requires_exact_lease_and_stale_release_cannot_free_successor(self) -> None:
        registry = conversation_sessions.ConversationSessionRegistry(capacity=2)
        with self.assertRaises(TypeError):
            await registry.release_writer("https://chatgpt.com/c/a")

        first = await registry.acquire_writer("https://chatgpt.com/c/a")
        waiter = asyncio.create_task(
            registry.acquire_writer("https://chatgpt.com/c/a")
        )
        await asyncio.sleep(0)
        await first.release()
        successor = await asyncio.wait_for(waiter, timeout=1)
        await registry.release_writer(first)

        lease_b = await registry.acquire_writer("https://chatgpt.com/c/b")
        with self.assertRaises(conversation_sessions.SessionCapacityError):
            await registry.acquire_writer("https://chatgpt.com/c/c")
        self.assertFalse(successor.released)
        await successor.release()
        await lease_b.release()


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
        self.saved_store = missions_api._store
        self.saved_runs_file = chat_api.CHAT_RUNS_FILE
        self.saved_runs = dict(chat_api._runs)
        write_slots._registry = conversation_sessions.ConversationSessionRegistry(capacity=2)
        chat_api.CHAT_RUNS_FILE = Path(self.tmp.name) / "chat-runs.json"
        missions_api._store = Store(Path(self.tmp.name) / "chat-missions.db")
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

        self.holding_factory = factory
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
        missions_api.close_store()
        missions_api._store = self.saved_store
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

    async def test_snapshot_rebuilds_a_stale_read_only_transport_once(self) -> None:
        created: list[object] = []

        class RecoveringViewTransport:
            def __init__(self, *, fail_snapshot: bool):
                self.fail_snapshot = fail_snapshot
                self.lock = None

            async def select_conversation(self, url: str):
                self.lock = SimpleNamespace(url=url, identity=url.rsplit("/", 1)[-1])
                return self.lock

            async def snapshot(self, *, verify_lock: bool = True) -> dict:
                del verify_lock
                if self.fail_snapshot:
                    raise TransportError(
                        CONVERSATION_MISMATCH,
                        "stale read-only tab",
                    )
                return {
                    "url": self.lock.url,
                    "conversation_id": self.lock.identity,
                    "title": "Recovered",
                    "messages": [],
                }

            async def close(self) -> None:
                return None

        def recovering_factory(session_id: str | None = None):
            del session_id
            transport = RecoveringViewTransport(fail_snapshot=not created)
            created.append(transport)
            return transport

        chat_api.ui_transport_factory = recovering_factory
        chat_api._view_transport = None
        chat_api._view_url = None

        snapshot = await chat_api.conversation_snapshot(
            "https://chatgpt.com/c/recovered-view"
        )

        self.assertEqual(snapshot["conversation_id"], "recovered-view")
        self.assertEqual(len(created), 2)

    async def test_concurrent_snapshots_cannot_retarget_the_shared_view_session(self) -> None:
        snapshot_started = asyncio.Event()
        release_first = asyncio.Event()

        class SharedViewTransport:
            def __init__(self) -> None:
                self.lock = None
                self.snapshot_calls = 0

            async def select_conversation(self, url: str):
                self.lock = SimpleNamespace(url=url, identity=url.rsplit("/", 1)[-1])
                return self.lock

            async def snapshot(self, *, verify_lock: bool = True) -> dict:
                del verify_lock
                self.snapshot_calls += 1
                if self.snapshot_calls == 1:
                    snapshot_started.set()
                    await release_first.wait()
                return {
                    "url": self.lock.url,
                    "conversation_id": self.lock.identity,
                    "title": "Shared view",
                    "messages": [],
                }

            async def close(self) -> None:
                return None

        shared = SharedViewTransport()
        chat_api.ui_transport_factory = lambda _session_id=None: shared
        chat_api._view_transport = None
        chat_api._view_url = None

        first = asyncio.create_task(
            chat_api.conversation_snapshot("https://chatgpt.com/c/view-a")
        )
        await snapshot_started.wait()
        second = asyncio.create_task(
            chat_api.conversation_snapshot("https://chatgpt.com/c/view-b")
        )
        await asyncio.sleep(0)
        release_first.set()

        result_a, result_b = await asyncio.gather(first, second)

        self.assertEqual(result_a["conversation_id"], "view-a")
        self.assertEqual(result_b["conversation_id"], "view-b")

    async def test_invalid_settings_fail_run_and_release_exact_writer_capacity(self) -> None:
        invalid_settings = Path(self.tmp.name) / "invalid-settings.json"
        invalid_settings.write_text(json.dumps({
            "browser_transport": "selenium",
            "browser_profile_root": "console/data/browser-profiles",
        }), encoding="utf-8")
        saved_settings_file = browser_transport.SETTINGS_FILE
        browser_transport.SETTINGS_FILE = invalid_settings
        chat_api.ui_transport_factory = browser_transport.create_transport
        try:
            submitted = await chat_api.send_chat(
                chat_api.ChatSendIn(
                    conversation_url="https://chatgpt.com/c/invalid-settings",
                    text="must fail without leaking the writer",
                )
            )
            failed = chat_api._runs[submitted["id"]]
            await asyncio.gather(failed.task, return_exceptions=True)
        finally:
            browser_transport.SETTINGS_FILE = saved_settings_file

        self.assertEqual(failed.state, "FAILED")
        self.assertEqual(
            failed.error,
            "CHAT_RUN_CRASHED: browser_transport must be exactly one of: "
            "chrome_extension, playwright, webbridge",
        )
        self.assertEqual(write_slots._registry.active_leases(), ())

        chat_api.ui_transport_factory = self.holding_factory
        await chat_api.send_chat(
            chat_api.ChatSendIn(
                conversation_url="https://chatgpt.com/c/recovered-a",
                text="a",
            )
        )
        await chat_api.send_chat(
            chat_api.ChatSendIn(
                conversation_url="https://chatgpt.com/c/recovered-b",
                text="b",
            )
        )
        self.assertEqual(len(write_slots._registry.active_leases()), 2)
        with self.assertRaises(HTTPException) as raised:
            await chat_api.send_chat(
                chat_api.ChatSendIn(
                    conversation_url="https://chatgpt.com/c/recovered-c",
                    text="c",
                )
            )
        self.assertEqual(raised.exception.status_code, 409)

    async def test_selected_transport_constructor_failure_is_persisted_and_releases_writer(self) -> None:
        observed_leases = []

        def fail_selected_transport(_session_id: str | None = None):
            observed_leases.extend(write_slots._registry.active_leases())
            raise RuntimeError("selected browser transport constructor failed")

        chat_api.ui_transport_factory = fail_selected_transport
        submitted = await chat_api.send_chat(
            chat_api.ChatSendIn(
                conversation_url="https://chatgpt.com/c/factory-failure",
                text="constructor failure must be compensated",
            )
        )
        failed = chat_api._runs[submitted["id"]]
        task_result = await asyncio.gather(failed.task, return_exceptions=True)

        self.assertEqual(task_result, [None])
        self.assertEqual(len(observed_leases), 1)
        self.assertEqual(observed_leases[0].session_id, failed.session_id)
        self.assertEqual(failed.state, "FAILED")
        self.assertEqual(
            failed.error,
            "CHAT_RUN_CRASHED: selected browser transport constructor failed",
        )
        persisted = {
            item["id"]: item
            for item in json.loads(
                chat_api.CHAT_RUNS_FILE.read_text(encoding="utf-8")
            )
        }
        self.assertEqual(persisted[failed.id]["state"], "FAILED")
        self.assertEqual(persisted[failed.id]["error"], failed.error)
        self.assertEqual(write_slots._registry.active_leases(), ())

        first = await write_slots.acquire_writer("https://chatgpt.com/c/recovered-1")
        second = await write_slots.acquire_writer("https://chatgpt.com/c/recovered-2")
        with self.assertRaises(conversation_sessions.SessionCapacityError):
            await write_slots.acquire_writer("https://chatgpt.com/c/recovered-3")
        await first.release()
        await second.release()


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

    async def test_old_non_terminal_run_is_never_evicted_by_terminal_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chat-runs.json"
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

            active = chat_api.ChatRunRuntime(
                id="old-active",
                conversation_url="https://chatgpt.com/c/active",
                text="must survive",
                new_conversation=False,
                state="WAITING_FOR_CHATGPT",
                conversation_key="https://chatgpt.com/c/active",
                session_id="cortex-conv-old-active",
            )
            active.lease = write_slots.restore_writer(
                active.conversation_key,
                active.session_id,
                active.conversation_url,
            )
            chat_api._runs[active.id] = active
            for index in range(105):
                run = chat_api.ChatRunRuntime(
                    id=f"terminal-{index:03d}",
                    conversation_url=f"https://chatgpt.com/c/t-{index}",
                    text="done",
                    new_conversation=False,
                    state="COMPLETED",
                )
                chat_api._runs[run.id] = run

            chat_api._persist_runs()
            persisted_ids = {
                item["id"]
                for item in json.loads(path.read_text(encoding="utf-8"))
            }
            self.assertIn("old-active", persisted_ids)
            self.assertIn("terminal-104", persisted_ids)
            self.assertNotIn("terminal-000", persisted_ids)

            chat_api._runs.clear()
            write_slots._registry = conversation_sessions.ConversationSessionRegistry(capacity=2)
            chat_api._load_persisted_runs()
            self.assertIn("old-active", chat_api._runs)
            self.assertEqual(
                chat_api._runs["old-active"].lease.session_id,
                "cortex-conv-old-active",
            )
            await chat_api._runs["old-active"].lease.release()


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

    async def test_two_provisional_missions_persist_unique_leases_before_return(self) -> None:
        def body() -> missions_api.MissionIn:
            return missions_api.MissionIn(
                objective="new provisional writer",
                workspace=str(self.workspace),
                conversation_url="https://chatgpt.com",
                new_conversation=True,
                mission_id=str(__import__("uuid").uuid4()),
            )

        first = await missions_api.create_mission(body())
        second = await missions_api.create_mission(body())
        bindings = [
            missions_api.get_store().rows(
                "conversation_bindings",
                mission_id,
                order_by="rowid",
            )[0]
            for mission_id in (first["id"], second["id"])
        ]

        self.assertEqual(len({item["session_id"] for item in bindings}), 2)
        self.assertTrue(all(
            item["conversation_target"].startswith("provisional:")
            for item in bindings
        ))
        self.assertEqual(
            {item["conversation_target"] for item in bindings},
            {
                lease.conversation_key
                for lease in write_slots._registry.active_leases()
            },
        )

        # Simulated restart before either writer navigates or creates /c/<id>.
        missions_api._mission_leases.clear()
        missions_api._mission_write_urls.clear()
        write_slots._registry = conversation_sessions.ConversationSessionRegistry(capacity=2)
        missions_api._restore_persisted_leases()
        self.assertEqual(
            {
                lease.conversation_key
                for lease in missions_api._mission_leases.values()
            },
            {item["conversation_target"] for item in bindings},
        )

    async def test_synchronous_binding_failure_fails_mission_and_releases_lease(self) -> None:
        body = missions_api.MissionIn(
            objective="binding must persist",
            workspace=str(self.workspace),
            conversation_url="https://chatgpt.com/c/sqlite-failure",
            mission_id=str(__import__("uuid").uuid4()),
        )
        store = missions_api.get_store()
        original = store.bind_conversation

        def fail_binding(*args, **kwargs):
            raise sqlite3.OperationalError("simulated binding failure")

        store.bind_conversation = fail_binding
        try:
            with self.assertRaises(HTTPException) as raised:
                await missions_api.create_mission(body)
        finally:
            store.bind_conversation = original

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(store.get_mission(body.mission_id)["state"], "FAILED")
        self.assertEqual(write_slots._registry.active_leases(), ())

    async def test_runtime_construction_failure_fails_creation_and_releases_lease(self) -> None:
        mission_id = str(__import__("uuid").uuid4())
        body = missions_api.MissionIn(
            objective="runtime construction must be compensated",
            workspace=str(self.workspace),
            conversation_url="https://chatgpt.com/c/create-runtime-failure",
            mission_id=mission_id,
        )
        original_build_runtime = missions_api._build_runtime
        observed_leases = []

        def fail_build_runtime(*args, **kwargs):
            observed_leases.extend(write_slots._registry.active_leases())
            raise RuntimeError("selected mission transport constructor failed")

        missions_api._build_runtime = fail_build_runtime
        try:
            with self.assertRaises(HTTPException) as raised:
                await missions_api.create_mission(body)
        finally:
            missions_api._build_runtime = original_build_runtime

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(
            raised.exception.detail,
            "cannot create mission: selected mission transport constructor failed",
        )
        self.assertEqual(len(observed_leases), 1)
        mission = missions_api.get_store().get_mission(mission_id)
        self.assertEqual(mission["state"], "FAILED")
        self.assertEqual(
            mission["pause_reason"],
            "mission creation failed: selected mission transport constructor failed",
        )
        self.assertEqual(write_slots._registry.active_leases(), ())

        first = await write_slots.acquire_writer("https://chatgpt.com/c/create-recovered-1")
        second = await write_slots.acquire_writer("https://chatgpt.com/c/create-recovered-2")
        with self.assertRaises(conversation_sessions.SessionCapacityError):
            await write_slots.acquire_writer("https://chatgpt.com/c/create-recovered-3")
        await first.release()
        await second.release()

    async def test_resume_transport_construction_failure_is_terminal_and_releases_restored_lease(self) -> None:
        mission_id = str(__import__("uuid").uuid4())
        conversation = "https://chatgpt.com/c/resume-runtime-failure"
        store = missions_api.get_store()
        store.create_mission(mission_id, "resume safely", str(self.workspace))
        store.bind_conversation(
            str(__import__("uuid").uuid4()),
            mission_id,
            conversation,
            browser_target_id="resume-runtime-failure",
            session_id="cortex-conv-resume-runtime-failure",
            conversation_target=conversation,
        )
        for state in (
            "INITIALIZING_MISSION",
            "SENDING_OBJECTIVE",
            "WAITING_FOR_CHATGPT",
            "PAUSED",
        ):
            store.transition(mission_id, state, pause_reason="test pause")
        observed_leases = []

        def fail_transport_factory(_session_id: str | None = None):
            observed_leases.extend(write_slots._registry.active_leases())
            raise RuntimeError("resume browser transport constructor failed")

        missions_api.transport_factory = fail_transport_factory
        with self.assertRaises(HTTPException) as raised:
            await missions_api.resume_mission(mission_id)

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(
            raised.exception.detail,
            "cannot resume mission: resume browser transport constructor failed",
        )
        self.assertEqual(len(observed_leases), 1)
        mission = store.get_mission(mission_id)
        self.assertEqual(mission["state"], "FAILED")
        self.assertEqual(
            mission["pause_reason"],
            "mission resume failed: resume browser transport constructor failed",
        )
        self.assertNotIn(mission_id, missions_api._mission_leases)
        self.assertEqual(write_slots._registry.active_leases(), ())

        first = await write_slots.acquire_writer("https://chatgpt.com/c/resume-recovered-1")
        second = await write_slots.acquire_writer("https://chatgpt.com/c/resume-recovered-2")
        with self.assertRaises(conversation_sessions.SessionCapacityError):
            await write_slots.acquire_writer("https://chatgpt.com/c/resume-recovered-3")
        await first.release()
        await second.release()

    async def test_resume_attach_failure_closes_inserted_runtime_and_clears_all_ownership(self) -> None:
        mission_id = str(__import__("uuid").uuid4())
        conversation = "https://chatgpt.com/c/resume-attach-failure"
        store = missions_api.get_store()
        store.create_mission(mission_id, "attach safely", str(self.workspace))
        store.bind_conversation(
            str(__import__("uuid").uuid4()),
            mission_id,
            conversation,
            browser_target_id="resume-attach-failure",
            session_id="cortex-conv-resume-attach-failure",
            conversation_target=conversation,
        )
        for state in (
            "INITIALIZING_MISSION",
            "SENDING_OBJECTIVE",
            "WAITING_FOR_CHATGPT",
            "PAUSED",
        ):
            store.transition(mission_id, state, pause_reason="test pause")
        missions_api._mission_write_urls[mission_id] = conversation
        observed = {}

        class FailingAttachTransport:
            def __init__(self):
                self.close_calls = 0
                self.closed = False
                self.lock = None

            async def attach(self, lock):
                observed["runtime"] = missions_api._runtimes.get(mission_id)
                observed["lease"] = missions_api._mission_leases.get(mission_id)
                observed["write_url"] = missions_api._mission_write_urls.get(mission_id)
                observed["lock"] = lock
                raise RuntimeError("resume attach failed after runtime construction")

            async def close(self):
                self.close_calls += 1
                await asyncio.sleep(0)
                self.closed = True

        transport = FailingAttachTransport()
        missions_api.transport_factory = lambda _session_id=None: transport

        with self.assertRaises(HTTPException) as raised:
            await missions_api.resume_mission(mission_id)

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(
            raised.exception.detail,
            "cannot resume mission: resume attach failed after runtime construction",
        )
        inserted_runtime = observed["runtime"]
        restored_lease = observed["lease"]
        self.assertIsNotNone(inserted_runtime)
        self.assertIs(inserted_runtime.transport, transport)
        self.assertIs(inserted_runtime.lease, None)
        self.assertEqual(restored_lease.session_id, "cortex-conv-resume-attach-failure")
        self.assertTrue(restored_lease.released)
        self.assertEqual(observed["write_url"], conversation)
        self.assertEqual(observed["lock"].url, conversation)
        self.assertEqual(transport.close_calls, 1)
        self.assertTrue(transport.closed)
        self.assertTrue(inserted_runtime.transport_closed)

        mission = store.get_mission(mission_id)
        self.assertEqual(mission["state"], "FAILED")
        self.assertEqual(
            mission["pause_reason"],
            "mission resume failed: resume attach failed after runtime construction",
        )
        self.assertNotIn(mission_id, missions_api._runtimes)
        self.assertNotIn(mission_id, missions_api._mission_write_urls)
        self.assertNotIn(mission_id, missions_api._mission_leases)
        self.assertEqual(write_slots._registry.active_leases(), ())

        first = await write_slots.acquire_writer("https://chatgpt.com/c/attach-recovered-1")
        second = await write_slots.acquire_writer("https://chatgpt.com/c/attach-recovered-2")
        with self.assertRaises(conversation_sessions.SessionCapacityError):
            await write_slots.acquire_writer("https://chatgpt.com/c/attach-recovered-3")
        await first.release()
        await second.release()


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

    async def test_migrated_null_session_binding_gets_unique_persisted_lease_before_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            mission_id = "00000000-0000-0000-0000-000000000004"
            store = Store(db_path)
            store.create_mission(mission_id, "legacy resume", tmp)
            store.transition(mission_id, "INITIALIZING_MISSION")
            store.transition(mission_id, "SENDING_OBJECTIVE")
            store.transition(mission_id, "WAITING_FOR_CHATGPT")
            store.bind_conversation(
                "legacy-binding",
                mission_id,
                "https://chatgpt.com/c/legacy",
                browser_target_id="legacy",
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

            missions_api._restore_persisted_leases()
            self.assertIn(mission_id, missions_api._mission_leases)
            lease = missions_api._mission_leases[mission_id]
            self.assertTrue(lease.session_id.startswith("cortex-conv-"))
            self.assertNotEqual(lease.session_id, missions_api.READ_ONLY_SESSION_ID)
            binding = missions_api._store.rows(
                "conversation_bindings",
                mission_id,
            )[0]
            self.assertEqual(binding["session_id"], lease.session_id)
            self.assertEqual(binding["conversation_target"], lease.conversation_key)
            await lease.release()
            missions_api._store.close()

    async def test_writer_runtime_refuses_to_build_without_a_lease(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                missions_api._build_runtime(
                    "00000000-0000-0000-0000-000000000005",
                    tmp,
                    "workspace-write-with-approvals",
                    "executor",
                    "fallback",
                    2,
                    60,
                    lease=None,
                )


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


class MissionPersistenceFailureTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.saved_store = missions_api._store
        self.saved_registry = write_slots._registry
        self.saved_runner = missions_api.ModeARunner
        self.saved_factory = missions_api.transport_factory
        self.saved_runtimes = dict(missions_api._runtimes)
        self.saved_leases = dict(missions_api._mission_leases)
        self.saved_urls = dict(missions_api._mission_write_urls)
        missions_api._store = Store(Path(self.tmp.name) / "cortex.db")
        write_slots._registry = conversation_sessions.ConversationSessionRegistry(capacity=2)
        missions_api._runtimes.clear()
        missions_api._mission_leases.clear()
        missions_api._mission_write_urls.clear()
        missions_api.transport_factory = lambda session_id=None: SimpleNamespace(lock=None)

    async def asyncTearDown(self) -> None:
        for lease in write_slots._registry.active_leases():
            await lease.release()
        missions_api._store.close()
        missions_api._store = self.saved_store
        write_slots._registry = self.saved_registry
        missions_api.ModeARunner = self.saved_runner
        missions_api.transport_factory = self.saved_factory
        missions_api._runtimes.clear()
        missions_api._runtimes.update(self.saved_runtimes)
        missions_api._mission_leases.clear()
        missions_api._mission_leases.update(self.saved_leases)
        missions_api._mission_write_urls.clear()
        missions_api._mission_write_urls.update(self.saved_urls)
        self.tmp.cleanup()

    def _runtime(self, mission_id: str, lease):
        store = missions_api.get_store()
        store.create_mission(mission_id, "persist safely", self.tmp.name)
        store.bind_conversation(
            f"binding-{mission_id}",
            mission_id,
            "https://chatgpt.com",
            session_id=lease.session_id,
            conversation_target=lease.conversation_key,
        )
        runtime = missions_api._build_runtime(
            mission_id,
            self.tmp.name,
            "workspace-write-with-approvals",
            "executor",
            "fallback",
            2,
            60,
            lease=lease,
        )
        missions_api._mission_leases[mission_id] = lease
        return runtime

    async def test_rekey_collision_fails_mission_releases_only_provisional_owner(self) -> None:
        provisional = write_slots.new_conversation_key()
        provisional_lease = await write_slots.acquire_writer(provisional)
        canonical = "https://chatgpt.com/c/collision"
        canonical_lease = await write_slots.acquire_writer(canonical)
        mission_id = "00000000-0000-0000-0000-000000000006"
        runtime = self._runtime(mission_id, provisional_lease)
        owner = self

        class CollisionRunner:
            def __init__(self, **kwargs):
                pass

            async def run_mission(self, *args, **kwargs):
                owner._store().update_conversation_binding(
                    mission_id,
                    canonical,
                    browser_target_id="collision",
                )
                await asyncio.sleep(0)
                return owner._store().get_mission(mission_id)

        missions_api.ModeARunner = CollisionRunner
        body = missions_api.MissionIn(
            objective="collision",
            workspace=self.tmp.name,
            conversation_url="https://chatgpt.com",
            new_conversation=True,
            mission_id=mission_id,
        )
        error = None
        try:
            await missions_api._run_mission_task(runtime, body.objective, body)
        except Exception as exc:
            error = exc

        self.assertIsNone(error)
        self.assertEqual(self._store().get_mission(mission_id)["state"], "FAILED")
        self.assertTrue(provisional_lease.released)
        self.assertFalse(canonical_lease.released)

    async def test_sqlite_update_failure_fails_mission_and_releases_exact_lease(self) -> None:
        provisional = write_slots.new_conversation_key()
        lease = await write_slots.acquire_writer(provisional)
        mission_id = "00000000-0000-0000-0000-000000000007"
        runtime = self._runtime(mission_id, lease)
        store = self._store()
        original_update = store.update_conversation_binding

        class IdleRunner:
            def __init__(self, **kwargs):
                pass

            async def run_mission(self, *args, **kwargs):
                await asyncio.sleep(0)
                return store.get_mission(mission_id)

        def fail_update(*args, **kwargs):
            raise sqlite3.OperationalError("simulated update failure")

        missions_api.ModeARunner = IdleRunner
        store.update_conversation_binding = fail_update
        body = missions_api.MissionIn(
            objective="sqlite failure",
            workspace=self.tmp.name,
            conversation_url="https://chatgpt.com",
            new_conversation=True,
            mission_id=mission_id,
        )
        error = None
        try:
            await missions_api._run_mission_task(runtime, body.objective, body)
        except Exception as exc:
            error = exc
        finally:
            store.update_conversation_binding = original_update

        self.assertIsNone(error)
        self.assertEqual(store.get_mission(mission_id)["state"], "FAILED")
        self.assertTrue(lease.released)

    def _store(self) -> Store:
        return missions_api._store


class MissionStopQuiescenceTest(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_keeps_slot_until_browser_and_background_task_quiesce(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            saved_store = missions_api._store
            saved_registry = write_slots._registry
            saved_runtimes = dict(missions_api._runtimes)
            saved_leases = dict(missions_api._mission_leases)
            saved_urls = dict(missions_api._mission_write_urls)
            saved_timeout = getattr(missions_api, "STOP_QUIESCE_TIMEOUT", None)
            missions_api._store = Store(Path(tmp) / "cortex.db")
            write_slots._registry = conversation_sessions.ConversationSessionRegistry(capacity=2)
            missions_api._runtimes.clear()
            missions_api._mission_leases.clear()
            missions_api._mission_write_urls.clear()
            missions_api.STOP_QUIESCE_TIMEOUT = 0.02
            self.addCleanup(setattr, missions_api, "_store", saved_store)
            self.addCleanup(setattr, write_slots, "_registry", saved_registry)
            self.addCleanup(missions_api._runtimes.clear)
            self.addCleanup(missions_api._runtimes.update, saved_runtimes)
            self.addCleanup(missions_api._mission_leases.clear)
            self.addCleanup(missions_api._mission_leases.update, saved_leases)
            self.addCleanup(missions_api._mission_write_urls.clear)
            self.addCleanup(missions_api._mission_write_urls.update, saved_urls)
            if saved_timeout is not None:
                self.addCleanup(setattr, missions_api, "STOP_QUIESCE_TIMEOUT", saved_timeout)

            mission_id = "00000000-0000-0000-0000-000000000008"
            store = missions_api._store
            store.create_mission(mission_id, "slow stop", tmp)
            store.transition(mission_id, "INITIALIZING_MISSION")
            lease_a = await write_slots.acquire_writer("https://chatgpt.com/c/a")
            lease_b = await write_slots.acquire_writer("https://chatgpt.com/c/b")
            quiesce = asyncio.Event()

            class SlowTransport:
                lock = SimpleNamespace(url="https://chatgpt.com/c/a")

                async def cancel_generation(self):
                    await quiesce.wait()

            runtime = missions_api.MissionRuntime(
                mission_id=mission_id,
                transport=SlowTransport(),
                conversation_key=lease_a.conversation_key,
                lease=lease_a,
            )

            async def old_background_activity() -> None:
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    await quiesce.wait()
                finally:
                    await missions_api._release_terminal_mission(runtime)

            runtime.task = asyncio.create_task(old_background_activity())
            await asyncio.sleep(0)
            missions_api._runtimes[mission_id] = runtime
            missions_api._mission_leases[mission_id] = lease_a
            missions_api._mission_write_urls[mission_id] = lease_a.conversation_key

            lease_c = None
            try:
                await missions_api.cancel_mission(mission_id)
                with self.assertRaises(conversation_sessions.SessionCapacityError):
                    await write_slots.acquire_writer("https://chatgpt.com/c/c")
                self.assertFalse(lease_a.released)

                quiesce.set()
                await asyncio.wait_for(runtime.task, timeout=1)
                await asyncio.wait_for(runtime.quiescence_task, timeout=1)
                lease_c = await write_slots.acquire_writer("https://chatgpt.com/c/c")
            finally:
                quiesce.set()
                await asyncio.gather(runtime.task, return_exceptions=True)
                if runtime.quiescence_task is not None:
                    await asyncio.gather(runtime.quiescence_task, return_exceptions=True)
                await lease_b.release()
                if lease_c is not None:
                    await lease_c.release()
                store.close()


if __name__ == "__main__":
    unittest.main()
