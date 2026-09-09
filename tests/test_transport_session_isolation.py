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
from unittest import mock

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
        self.saved_view_cleanup_candidate = getattr(
            chat_api, "_view_cleanup_candidate", None
        )
        chat_api._view_cleanup_candidate = None
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
        chat_api._view_cleanup_candidate = self.saved_view_cleanup_candidate
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

    async def test_non_streaming_update_clears_chatgpt_streaming_state(self) -> None:
        non_streaming_emitted = asyncio.Event()
        release_final = asyncio.Event()

        class StreamingTransitionTransport:
            def __init__(self, session_id: str | None):
                self.session_id = session_id
                self.lock = None

            async def select_conversation(self, url: str):
                self.lock = SimpleNamespace(url=url, identity=url.rsplit("/", 1)[-1])
                return self.lock

            async def send_message(self, _text: str) -> None:
                return None

            async def stream_response(self, on_update=None) -> dict:
                update = {
                    "id": "assistant-transition",
                    "role": "assistant",
                    "text": "stable response",
                    "code_blocks": [],
                    "images": [],
                }
                await on_update({**update, "streaming": True})
                await on_update({**update, "streaming": False})
                non_streaming_emitted.set()
                await release_final.wait()
                return update

            async def close(self) -> None:
                return None

        chat_api.ui_transport_factory = StreamingTransitionTransport
        accepted = await chat_api.send_chat(
            chat_api.ChatSendIn(
                conversation_url="https://chatgpt.com/c/streaming-transition",
                text="transition",
            )
        )
        await asyncio.wait_for(non_streaming_emitted.wait(), timeout=1)
        run = chat_api._runs[accepted["id"]]

        try:
            self.assertEqual(run.state, "WAITING_FOR_CHATGPT")
            self.assertEqual(run.response_text, "stable response")
        finally:
            release_final.set()
        await asyncio.wait_for(run.task, timeout=1)
        self.assertEqual(run.state, "COMPLETED")

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

    async def test_normal_switch_and_recovery_use_three_distinct_reader_lifecycles(self) -> None:
        created: list[object] = []
        cached_driver = None
        events: list[str] = []

        class CachedDriver:
            def __init__(self, generation: int) -> None:
                self.generation = generation
                self.live = True

            async def close(self) -> None:
                events.append(f"close:{self.generation}")
                self.live = False

        class CachedTransport:
            def __init__(self, driver: CachedDriver) -> None:
                self.driver = driver
                self.lock = None

            async def select_conversation(self, url: str):
                if not self.driver.live:
                    raise RuntimeError("selected reader was already closed")
                events.append(f"select:{self.driver.generation}")
                self.lock = SimpleNamespace(url=url, identity=url.rsplit("/", 1)[-1])
                return self.lock

            async def snapshot(self, *, verify_lock: bool = True) -> dict:
                del verify_lock
                if not self.driver.live:
                    raise RuntimeError("published reader was closed by its predecessor")
                if self.driver.generation == 2:
                    raise TransportError(CONVERSATION_MISMATCH, "recover this reader")
                return {
                    "url": self.lock.url,
                    "conversation_id": self.lock.identity,
                    "messages": [],
                }

            async def close(self) -> None:
                await self.driver.close()

        def cached_factory(session_id: str | None = None):
            nonlocal cached_driver
            self.assertEqual(session_id, chat_api.READ_ONLY_SESSION_ID)
            if cached_driver is None or not cached_driver.live:
                cached_driver = CachedDriver(len(created) + 1)
            transport = CachedTransport(cached_driver)
            created.append(transport)
            events.append(f"factory:{cached_driver.generation}")
            return transport

        chat_api.ui_transport_factory = cached_factory

        first = await chat_api.conversation_snapshot("https://chatgpt.com/c/first")
        recovered = await chat_api.conversation_snapshot("https://chatgpt.com/c/recovered")

        self.assertEqual(first["conversation_id"], "first")
        self.assertEqual(recovered["conversation_id"], "recovered")
        self.assertEqual(len(created), 3)
        self.assertEqual(len({id(transport.driver) for transport in created}), 3)
        self.assertEqual(
            events,
            [
                "factory:1",
                "select:1",
                "close:1",
                "factory:2",
                "select:2",
                "close:2",
                "factory:3",
                "select:3",
            ],
        )
        self.assertFalse(created[0].driver.live)
        self.assertFalse(created[1].driver.live)
        self.assertTrue(created[2].driver.live)

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

    async def test_selection_and_read_share_one_eight_second_snapshot_budget(self) -> None:
        class SlowViewTransport:
            lock = None

            async def select_conversation(self, url: str):
                await asyncio.sleep(0.03)
                self.lock = SimpleNamespace(url=url, identity="budget")
                return self.lock

            async def snapshot(self, *, verify_lock: bool = True) -> dict:
                del verify_lock
                await asyncio.sleep(0.03)
                return {
                    "url": self.lock.url,
                    "conversation_id": self.lock.identity,
                    "messages": [],
                }

            async def close(self) -> None:
                return None

        chat_api.ui_transport_factory = lambda _session_id=None: SlowViewTransport()
        with mock.patch.object(
            chat_api,
            "TRANSPORT_SNAPSHOT_BUDGET_SECONDS",
            0.05,
            create=True,
        ):
            with self.assertRaises(HTTPException) as raised:
                await chat_api.conversation_snapshot("https://chatgpt.com/c/budget")

        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("SNAPSHOT_ACQUISITION_TIMEOUT", str(raised.exception.detail))

    async def test_timed_out_unpublished_view_candidate_is_closed_without_publication(self) -> None:
        created: list[object] = []

        class TimedOutCandidate:
            def __init__(self) -> None:
                self.close_calls = 0
                self.selection_cancelled = False

            async def select_conversation(self, _url: str):
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    self.selection_cancelled = True
                    raise

            async def close(self) -> None:
                self.close_calls += 1

        def factory(_session_id=None):
            candidate = TimedOutCandidate()
            created.append(candidate)
            return candidate

        chat_api.ui_transport_factory = factory
        with (
            mock.patch.object(chat_api, "TRANSPORT_SNAPSHOT_BUDGET_SECONDS", 0.05),
            mock.patch.object(
                chat_api,
                "SNAPSHOT_CANDIDATE_CLEANUP_RESERVE_SECONDS",
                0.01,
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await chat_api.conversation_snapshot("https://chatgpt.com/c/unpublished")

        candidate = created[0]
        self.assertIn("SNAPSHOT_ACQUISITION_TIMEOUT", str(raised.exception.detail))
        self.assertTrue(candidate.selection_cancelled)
        self.assertEqual(candidate.close_calls, 1)
        self.assertIsNone(chat_api._view_transport)
        self.assertIsNone(chat_api._view_url)

    async def test_timed_out_candidate_close_is_cancelled_within_the_snapshot_budget(self) -> None:
        created: list[object] = []

        class SlowClosingCandidate:
            def __init__(self) -> None:
                self.selection_cancelled = False
                self.close_started = False
                self.close_cancelled = False
                self.close_active = 0

            async def select_conversation(self, _url: str):
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    self.selection_cancelled = True
                    raise

            async def close(self) -> None:
                self.close_started = True
                self.close_active += 1
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    self.close_cancelled = True
                    raise
                finally:
                    self.close_active -= 1

        def factory(_session_id=None):
            candidate = SlowClosingCandidate()
            created.append(candidate)
            return candidate

        chat_api.ui_transport_factory = factory
        pending_before = {
            task for task in asyncio.all_tasks()
            if task is not asyncio.current_task() and not task.done()
        }
        started = asyncio.get_running_loop().time()
        with (
            mock.patch.object(chat_api, "TRANSPORT_SNAPSHOT_BUDGET_SECONDS", 0.02),
            mock.patch.object(
                chat_api,
                "SNAPSHOT_CANDIDATE_CLEANUP_RESERVE_SECONDS",
                0.005,
                create=True,
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await chat_api.conversation_snapshot("https://chatgpt.com/c/slow-close")
        elapsed = asyncio.get_running_loop().time() - started

        candidate = created[0]
        self.assertLess(elapsed, 0.08)
        self.assertIn("SNAPSHOT_ACQUISITION_TIMEOUT", str(raised.exception.detail))
        self.assertTrue(candidate.selection_cancelled)
        self.assertTrue(candidate.close_started)
        self.assertTrue(candidate.close_cancelled)
        self.assertEqual(candidate.close_active, 0)
        self.assertIsNone(chat_api._view_transport)
        self.assertIsNone(chat_api._view_url)
        pending_after = {
            task for task in asyncio.all_tasks()
            if task is not asyncio.current_task() and not task.done()
        }
        self.assertEqual(pending_after - pending_before, set())

    async def test_failed_candidate_close_is_retained_until_a_retry_is_confirmed(self) -> None:
        created: list[object] = []

        class RetriableClosingCandidate:
            def __init__(self, *, ready: bool) -> None:
                self.ready = ready
                self.close_calls = 0
                self.lock = None

            async def select_conversation(self, url: str):
                if not self.ready:
                    await asyncio.sleep(1)
                self.lock = SimpleNamespace(url=url, identity="reconciled")
                return self.lock

            async def snapshot(self, *, verify_lock: bool = True) -> dict:
                del verify_lock
                return {
                    "url": self.lock.url,
                    "conversation_id": self.lock.identity,
                    "messages": [],
                }

            async def close(self) -> None:
                self.close_calls += 1
                if self.close_calls < 3:
                    raise RuntimeError("release ACK unavailable")

        def factory(_session_id=None):
            candidate = RetriableClosingCandidate(ready=bool(created))
            created.append(candidate)
            return candidate

        chat_api.ui_transport_factory = factory
        patches = (
            mock.patch.object(chat_api, "TRANSPORT_SNAPSHOT_BUDGET_SECONDS", 0.04),
            mock.patch.object(
                chat_api,
                "SNAPSHOT_CANDIDATE_CLEANUP_RESERVE_SECONDS",
                0.01,
                create=True,
            ),
        )
        with patches[0], patches[1]:
            with self.assertRaises(HTTPException) as first:
                await chat_api.conversation_snapshot("https://chatgpt.com/c/pending-close")
            self.assertIn("candidate cleanup pending", str(first.exception.detail))
            self.assertIsNotNone(chat_api._view_cleanup_candidate)
            self.assertEqual(len(created), 1)

            with self.assertRaises(HTTPException) as second:
                await chat_api.conversation_snapshot("https://chatgpt.com/c/pending-close")
            self.assertIn("candidate cleanup pending", str(second.exception.detail))
            self.assertEqual(created[0].close_calls, 2)
            self.assertEqual(len(created), 1)
            self.assertIsNone(chat_api._view_transport)
            self.assertIsNone(chat_api._view_url)

            snapshot = await chat_api.conversation_snapshot(
                "https://chatgpt.com/c/pending-close"
            )

        self.assertEqual(snapshot["conversation_id"], "reconciled")
        self.assertEqual(created[0].close_calls, 3)
        self.assertEqual(len(created), 2)
        self.assertIsNone(chat_api._view_cleanup_candidate)

    async def test_published_reader_cleanup_blocks_new_allocation_until_confirmed(self) -> None:
        created: list[object] = []

        class RetriablePublishedTransport:
            def __init__(self, generation: int) -> None:
                self.generation = generation
                self.close_calls = 0
                self.lock = None

            async def select_conversation(self, url: str):
                self.lock = SimpleNamespace(url=url, identity=url.rsplit("/", 1)[-1])
                return self.lock

            async def snapshot(self, *, verify_lock: bool = True) -> dict:
                del verify_lock
                return {
                    "url": self.lock.url,
                    "conversation_id": self.lock.identity,
                    "messages": [],
                }

            async def close(self) -> None:
                self.close_calls += 1
                if self.generation == 1 and self.close_calls < 3:
                    raise RuntimeError("release ACK unavailable")

        def factory(_session_id=None):
            transport = RetriablePublishedTransport(len(created) + 1)
            created.append(transport)
            return transport

        chat_api.ui_transport_factory = factory
        first = await chat_api.conversation_snapshot("https://chatgpt.com/c/first")
        self.assertEqual(first["conversation_id"], "first")

        with self.assertRaises(HTTPException):
            await chat_api.conversation_snapshot("https://chatgpt.com/c/second")
        self.assertEqual(len(created), 1)
        self.assertIsNotNone(chat_api._view_cleanup_candidate)

        with self.assertRaises(HTTPException):
            await chat_api.conversation_snapshot("https://chatgpt.com/c/second")
        self.assertEqual(len(created), 1)

        second = await chat_api.conversation_snapshot("https://chatgpt.com/c/second")
        self.assertEqual(second["conversation_id"], "second")
        self.assertEqual(len(created), 2)
        self.assertEqual(created[0].close_calls, 3)
        self.assertIsNone(chat_api._view_cleanup_candidate)

    async def test_candidate_selection_can_use_almost_the_full_snapshot_budget(self) -> None:
        class SlowSuccessfulCandidate:
            lock = None

            async def select_conversation(self, url: str):
                await asyncio.sleep(0.15)
                self.lock = SimpleNamespace(url=url, identity="long-switch")
                return self.lock

            async def snapshot(self, *, verify_lock: bool = True) -> dict:
                del verify_lock
                return {
                    "url": self.lock.url,
                    "conversation_id": self.lock.identity,
                    "messages": [],
                }

            async def close(self) -> None:
                return None

        chat_api.ui_transport_factory = lambda _session_id=None: SlowSuccessfulCandidate()
        with (
            mock.patch.object(chat_api, "TRANSPORT_SNAPSHOT_BUDGET_SECONDS", 0.16),
            mock.patch.object(
                chat_api,
                "SNAPSHOT_CANDIDATE_CLEANUP_RESERVE_SECONDS",
                0.002,
                create=True,
            ),
        ):
            snapshot = await chat_api.conversation_snapshot("https://chatgpt.com/c/long-switch")

        self.assertEqual(snapshot["conversation_id"], "long-switch")

    async def test_recovery_cannot_reset_the_snapshot_budget(self) -> None:
        created: list[object] = []

        class RecoveringViewTransport:
            def __init__(self, *, stale: bool):
                self.stale = stale
                self.lock = None

            async def select_conversation(self, url: str):
                await asyncio.sleep(0.02)
                self.lock = SimpleNamespace(url=url, identity="recovery")
                return self.lock

            async def snapshot(self, *, verify_lock: bool = True) -> dict:
                del verify_lock
                await asyncio.sleep(0.02)
                if self.stale:
                    raise TransportError(CONVERSATION_MISMATCH, "stale reader")
                return {
                    "url": self.lock.url,
                    "conversation_id": self.lock.identity,
                    "messages": [],
                }

            async def close(self) -> None:
                return None

        def factory(_session_id=None):
            transport = RecoveringViewTransport(stale=not created)
            created.append(transport)
            return transport

        chat_api.ui_transport_factory = factory
        with (
            mock.patch.object(
                chat_api,
                "TRANSPORT_SNAPSHOT_BUDGET_SECONDS",
                0.07,
                create=True,
            ),
            mock.patch.object(
                chat_api,
                "SNAPSHOT_CANDIDATE_CLEANUP_RESERVE_SECONDS",
                0.01,
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await chat_api.conversation_snapshot("https://chatgpt.com/c/recovery")

        self.assertEqual(len(created), 2)
        self.assertIn("SNAPSHOT_ACQUISITION_TIMEOUT", str(raised.exception.detail))

    async def test_waiting_for_the_view_lock_consumes_the_same_budget_and_releases_it(self) -> None:
        class ReadyViewTransport:
            lock = None

            async def select_conversation(self, url: str):
                self.lock = SimpleNamespace(url=url, identity="lock")
                return self.lock

            async def snapshot(self, *, verify_lock: bool = True) -> dict:
                del verify_lock
                return {
                    "url": self.lock.url,
                    "conversation_id": self.lock.identity,
                    "messages": [],
                }

            async def close(self) -> None:
                return None

        chat_api.ui_transport_factory = lambda _session_id=None: ReadyViewTransport()
        lock = chat_api._view_operation_lock()
        await lock.acquire()

        async def release_after_deadline() -> None:
            await asyncio.sleep(0.03)
            lock.release()

        release = asyncio.create_task(release_after_deadline())
        with mock.patch.object(
            chat_api,
            "TRANSPORT_SNAPSHOT_BUDGET_SECONDS",
            0.02,
            create=True,
        ):
            with self.assertRaises(HTTPException) as raised:
                await chat_api.conversation_snapshot("https://chatgpt.com/c/lock")
        await release
        self.assertFalse(lock.locked())
        self.assertIn("SNAPSHOT_ACQUISITION_TIMEOUT", str(raised.exception.detail))

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


class ResumeVisibleReplyRecoveryTest(unittest.IsolatedAsyncioTestCase):
    async def test_recovers_only_the_current_unconsumed_mission_reply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mission_id = "00000000-0000-0000-0000-000000000091"
            store = Store(Path(tmp) / "cortex.db")
            store.create_mission(mission_id, "recover visible reply", tmp)
            store.set_iteration(mission_id, 8)
            store.record_message(
                "assistant-consumed",
                mission_id,
                "assistant",
                "consumed-fingerprint",
                "already consumed",
            )

            def decision(mid: str, iteration: int, action_id: str) -> dict:
                return {
                    "protocol": "cortex.v1",
                    "missionId": mid,
                    "actionId": action_id,
                    "iteration": iteration,
                    "state": "COMPLETE",
                    "summary": "validated",
                    "action": None,
                    "acceptanceCriteria": ["All deterministic checks passed."],
                    "requiresApproval": False,
                    "terminal": True,
                }

            messages = [
                {
                    "id": "assistant-consumed",
                    "role": "assistant",
                    "text": "cortex-decision",
                    "code_blocks": [{
                        "lang": "cortex-decision",
                        "text": json.dumps(decision(
                            mission_id,
                            8,
                            "00000000-0000-0000-0000-000000000081",
                        )),
                    }],
                },
                {
                    "id": "assistant-other-mission",
                    "role": "assistant",
                    "text": "cortex-decision",
                    "code_blocks": [{
                        "lang": "cortex-decision",
                        "text": json.dumps(decision(
                            "00000000-0000-0000-0000-000000000099",
                            9,
                            "00000000-0000-0000-0000-000000000082",
                        )),
                    }],
                },
                {
                    "id": "assistant-current-unconsumed",
                    "role": "assistant",
                    "text": "cortex-decision",
                    "code_blocks": [{
                        "lang": "cortex-decision",
                        "text": json.dumps(decision(
                            mission_id,
                            9,
                            "00000000-0000-0000-0000-000000000083",
                        )),
                    }],
                },
            ]

            class SnapshotTransport:
                async def snapshot(self):
                    return {"messages": messages}

            runtime = SimpleNamespace(mission_id=mission_id, transport=SnapshotTransport())
            reply = await missions_api._recover_unconsumed_visible_reply(runtime, store)

            self.assertIsNotNone(reply)
            self.assertEqual(reply.message_id, "assistant-current-unconsumed")
            parsed = missions_api.protocol.extract_decision_block(reply.text)
            self.assertEqual(parsed["missionId"], mission_id)
            self.assertEqual(parsed["iteration"], 9)
            store.close()

    async def test_refuses_a_decision_whose_action_was_already_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mission_id = "00000000-0000-0000-0000-000000000092"
            action_id = "00000000-0000-0000-0000-000000000084"
            store = Store(Path(tmp) / "cortex.db")
            store.create_mission(mission_id, "do not replay", tmp)
            store.set_iteration(mission_id, 8)
            decision = {
                "protocol": "cortex.v1",
                "missionId": mission_id,
                "actionId": action_id,
                "iteration": 9,
                "state": "COMPLETE",
                "summary": "already consumed",
                "action": None,
                "acceptanceCriteria": ["The result was already persisted."],
                "requiresApproval": False,
                "terminal": True,
            }
            store.record_message(
                "sqlite-row-not-dom-id",
                mission_id,
                "assistant",
                "already-consumed-fingerprint",
                json.dumps(decision),
            )
            store.record_decision(
                "decision-row",
                mission_id,
                action_id,
                9,
                decision,
                valid=True,
            )

            class SnapshotTransport:
                async def snapshot(self):
                    return {
                        "streaming": False,
                        "messages": [{
                            "id": "assistant-dom-id",
                            "role": "assistant",
                            "text": "cortex-decision",
                            "code_blocks": [{
                                "lang": "cortex-decision",
                                "text": json.dumps(decision),
                            }],
                        }],
                    }

            runtime = SimpleNamespace(mission_id=mission_id, transport=SnapshotTransport())
            reply = await missions_api._recover_unconsumed_visible_reply(runtime, store)

            self.assertIsNone(reply)
            store.close()

    async def test_invalid_decision_does_not_hide_a_valid_correction_at_same_iteration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mission_id = "00000000-0000-0000-0000-000000000095"
            store = Store(Path(tmp) / "cortex.db")
            store.create_mission(mission_id, "recover corrected decision", tmp)
            store.set_iteration(mission_id, 8)
            store.record_decision(
                "invalid-decision-row",
                mission_id,
                "00000000-0000-0000-0000-000000000096",
                9,
                {"iteration": 9, "state": "COMPLETE", "acceptanceCriteria": []},
                valid=False,
                error="MISSING_ACCEPTANCE_CRITERIA",
            )
            corrected = {
                "protocol": "cortex.v1",
                "missionId": mission_id,
                "actionId": "00000000-0000-0000-0000-000000000097",
                "iteration": 9,
                "state": "COMPLETE",
                "summary": "corrected visible decision",
                "action": None,
                "acceptanceCriteria": ["The corrected result is validated."],
                "requiresApproval": False,
                "terminal": True,
            }

            class SnapshotTransport:
                async def snapshot(self):
                    return {
                        "streaming": False,
                        "messages": [{
                            "id": "assistant-corrected",
                            "role": "assistant",
                            "text": "cortex-decision",
                            "code_blocks": [{
                                "lang": "cortex-decision",
                                "text": json.dumps(corrected),
                            }],
                        }],
                    }

            runtime = SimpleNamespace(mission_id=mission_id, transport=SnapshotTransport())
            reply = await missions_api._recover_unconsumed_visible_reply(runtime, store)

            self.assertIsNotNone(reply)
            self.assertEqual(reply.message_id, "assistant-corrected")
            self.assertEqual(
                missions_api.protocol.extract_decision_block(reply.text)["actionId"],
                corrected["actionId"],
            )
            store.close()

    async def test_refuses_invalid_streaming_and_ambiguous_visible_replies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mission_id = "00000000-0000-0000-0000-000000000093"
            store = Store(Path(tmp) / "cortex.db")
            store.create_mission(mission_id, "fail closed", tmp)
            store.set_iteration(mission_id, 8)

            def message(message_id: str, action_id: str, *, criteria: list[str]) -> dict:
                return {
                    "id": message_id,
                    "role": "assistant",
                    "text": "cortex-decision",
                    "code_blocks": [{
                        "lang": "cortex-decision",
                        "text": json.dumps({
                            "protocol": "cortex.v1",
                            "missionId": mission_id,
                            "actionId": action_id,
                            "iteration": 9,
                            "state": "COMPLETE",
                            "summary": "candidate",
                            "action": None,
                            "acceptanceCriteria": criteria,
                            "requiresApproval": False,
                            "terminal": True,
                        }),
                    }],
                }

            invalid = message(
                "assistant-invalid",
                "00000000-0000-0000-0000-000000000085",
                criteria=[],
            )
            valid_one = message(
                "assistant-one",
                "00000000-0000-0000-0000-000000000086",
                criteria=["First complete result."],
            )
            valid_two = message(
                "assistant-two",
                "00000000-0000-0000-0000-000000000087",
                criteria=["Second complete result."],
            )

            class SnapshotTransport:
                def __init__(self, payload):
                    self.payload = payload

                async def snapshot(self):
                    return self.payload

            invalid_runtime = SimpleNamespace(
                mission_id=mission_id,
                transport=SnapshotTransport({"streaming": False, "messages": [invalid]}),
            )
            self.assertIsNone(
                await missions_api._recover_unconsumed_visible_reply(invalid_runtime, store)
            )

            streaming_runtime = SimpleNamespace(
                mission_id=mission_id,
                transport=SnapshotTransport({"streaming": True, "messages": [valid_one]}),
            )
            with self.assertRaises(TransportError):
                await missions_api._recover_unconsumed_visible_reply(streaming_runtime, store)

            ambiguous_runtime = SimpleNamespace(
                mission_id=mission_id,
                transport=SnapshotTransport({
                    "streaming": False,
                    "messages": [valid_one, valid_two],
                }),
            )
            with self.assertRaises(TransportError):
                await missions_api._recover_unconsumed_visible_reply(ambiguous_runtime, store)
            store.close()

    async def test_resume_transport_error_stays_paused_without_runner_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mission_id = "00000000-0000-0000-0000-000000000094"
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            store = Store(Path(tmp) / "cortex.db")
            store.create_mission(mission_id, "pause safely", str(workspace))
            for state in (
                "INITIALIZING_MISSION",
                "SENDING_OBJECTIVE",
                "WAITING_FOR_CHATGPT",
            ):
                store.transition(mission_id, state)

            class StreamingTransport:
                lock = SimpleNamespace(identity="resume-test-conversation")
                stability_interval = 0.0

                async def snapshot(self):
                    return {"streaming": True, "messages": []}

            runtime = missions_api.MissionRuntime(mission_id=mission_id)
            runtime.transport = StreamingTransport()
            runtime.policy = missions_api.PolicyEngine(
                workspace,
                mode=missions_api.WRITE_WITH_APPROVALS,
            )
            runtime._tools = missions_api.ToolExecutor(workspace)
            runtime._budgets = missions_api.Budgets(
                max_iterations=10,
                max_duration_seconds=600,
            )
            original_store = missions_api._store
            missions_api._store = store
            try:
                await missions_api._resume_mission_task(runtime)
            finally:
                missions_api._store = original_store

            mission = store.get_mission(mission_id)
            self.assertEqual(mission["state"], "PAUSED")
            self.assertEqual(mission["pause_reason"], "STATE_UNREADABLE")
            event_types = [
                row["event_type"]
                for row in store.rows("transport_events", mission_id, order_by="rowid")
            ]
            self.assertIn("TRANSPORT_PAUSED", event_types)
            self.assertNotIn("RUNNER_CRASHED", event_types)
            store.close()


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
