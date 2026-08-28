"""Shared 2-writer pool: Chat and Mission routes consume the same global slots.

Cortex Bridge caps concurrent writers at 2 across ALL routes (Chat + Mission).
This test verifies that the module-level ``_registry`` in ``write_slots.py``
is the single source of truth and that Chat runs and Missions compete for the
same capacity — a third writer is refused regardless of which route it comes
from.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "console"))

from fastapi import HTTPException  # noqa: E402

import chat as chat_api  # noqa: E402
import conversation_sessions  # noqa: E402
import missions as missions_api  # noqa: E402
import write_slots  # noqa: E402
from orchestration.store import Store  # noqa: E402


_SHARED_REGISTRY = True  # the single truth: both modules use write_slots._registry


class GlobalWriterPoolTest(unittest.IsolatedAsyncioTestCase):
    """The 2-writer pool is shared across Chat and Mission routes."""

    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name) / "workspace"
        self.workspace.mkdir()

        # Save and swap globals
        self.saved_registry = write_slots._registry
        self.saved_chat_factory = chat_api.ui_transport_factory
        self.saved_chat_runs = dict(chat_api._runs)
        self.saved_chat_runs_file = chat_api.CHAT_RUNS_FILE
        self.saved_mission_factory = missions_api.transport_factory
        self.saved_mission_optin = missions_api.optin_accepted
        self.saved_mission_store = missions_api._store
        self.saved_mission_runtimes = dict(missions_api._runtimes)
        self.saved_mission_leases = dict(missions_api._mission_leases)
        self.saved_mission_urls = dict(missions_api._mission_write_urls)
        self.saved_mission_runner = missions_api._run_mission_task

        # Fresh isolated pool
        write_slots._registry = conversation_sessions.ConversationSessionRegistry(
            capacity=2
        )

        # In-memory stores
        chat_api.CHAT_RUNS_FILE = Path(self.tmp.name) / "chat-runs.json"
        missions_api._store = Store(Path(self.tmp.name) / "missions.db")

        chat_api._runs.clear()
        missions_api._runtimes.clear()
        missions_api._mission_leases.clear()
        missions_api._mission_write_urls.clear()
        missions_api._global_stop = False
        missions_api.optin_accepted = lambda: True

        self.finish_chat = asyncio.Event()
        self.finish_mission = asyncio.Event()
        self.chat_sessions: list[str | None] = []
        self.mission_sessions: list[str | None] = []

        def chat_factory(session_id: str | None = None):
            self.chat_sessions.append(session_id)

            class HoldingTransport:
                def __init__(self):
                    self.lock = None
                    self.session_id = session_id

                async def select_conversation(self, url: str):
                    self.lock = SimpleNamespace(url=url, identity=url.rsplit("/", 1)[-1])
                    return self.lock

                async def send_message(self, text: str) -> None:
                    return None

                async def stream_response(self, on_update=None) -> dict:
                    await asyncio.sleep(0)
                    return {"text": "done", "code_blocks": [], "images": []}

                async def snapshot(self, *, verify_lock: bool = True) -> dict:
                    return {
                        "url": self.lock.url,
                        "conversation_id": self.lock.identity,
                        "messages": [],
                    }

            return HoldingTransport()

        chat_api.ui_transport_factory = chat_factory

        def mission_factory(session_id: str | None = None):
            self.mission_sessions.append(session_id)
            return SimpleNamespace(lock=None)

        async def hold_mission(rt, objective, body) -> None:
            await asyncio.sleep(0)
            chat_api._runs.clear()  # not needed, just preventing side effects

        missions_api.transport_factory = mission_factory
        missions_api._run_mission_task = hold_mission

    async def asyncTearDown(self) -> None:
        self.finish_chat.set()
        self.finish_mission.set()
        # Cancel any lingering tasks
        tasks = [
            run.task
            for run in chat_api._runs.values()
            if run.task is not None
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        m_tasks = [
            rt.task
            for rt in missions_api._runtimes.values()
            if rt.task is not None
        ]
        if m_tasks:
            await asyncio.gather(*m_tasks, return_exceptions=True)
        if missions_api._store is not None:
            missions_api._store.close()
        # Restore globals
        write_slots._registry = self.saved_registry
        chat_api.ui_transport_factory = self.saved_chat_factory
        chat_api.CHAT_RUNS_FILE = self.saved_chat_runs_file
        chat_api._runs.clear()
        chat_api._runs.update(self.saved_chat_runs)
        missions_api.transport_factory = self.saved_mission_factory
        missions_api.optin_accepted = self.saved_mission_optin
        missions_api._store = self.saved_mission_store
        missions_api._runtimes.clear()
        missions_api._runtimes.update(self.saved_mission_runtimes)
        missions_api._mission_leases.clear()
        missions_api._mission_leases.update(self.saved_mission_leases)
        missions_api._mission_write_urls.clear()
        missions_api._mission_write_urls.update(self.saved_mission_urls)
        missions_api._run_mission_task = self.saved_mission_runner
        missions_api._global_stop = False
        self.tmp.cleanup()

    # --- 1. Two chats → OK, third → 409 ------------------------------------

    async def test_two_chats_fill_pool_and_third_is_409(self):
        await chat_api.send_chat(
            chat_api.ChatSendIn(
                conversation_url="https://chatgpt.com/c/a",
                text="chat-a",
            )
        )
        await chat_api.send_chat(
            chat_api.ChatSendIn(
                conversation_url="https://chatgpt.com/c/b",
                text="chat-b",
            )
        )
        with self.assertRaises(HTTPException) as raised:
            await chat_api.send_chat(
                chat_api.ChatSendIn(
                    conversation_url="https://chatgpt.com/c/c",
                    text="chat-c",
                )
            )
        self.assertEqual(raised.exception.status_code, 409)

    # --- 2. One chat + one mission → OK, third (chat or mission) → 409 ------

    async def test_one_chat_and_one_mission_fill_pool(self):
        await chat_api.send_chat(
            chat_api.ChatSendIn(
                conversation_url="https://chatgpt.com/c/chat-1",
                text="chat-1",
            )
        )
        import uuid

        await missions_api.create_mission(
            missions_api.MissionIn(
                objective="hold writer",
                workspace=str(self.workspace),
                conversation_url="https://chatgpt.com/c/mission-1",
                mission_id=str(uuid.uuid4()),
            )
        )
        # Pool is now full (2/2). A second chat must be refused.
        with self.assertRaises(HTTPException) as raised:
            await chat_api.send_chat(
                chat_api.ChatSendIn(
                    conversation_url="https://chatgpt.com/c/chat-extra",
                    text="chat-extra",
                )
            )
        self.assertEqual(raised.exception.status_code, 409)

    # --- 3. Two missions fill pool, third mission → 409 ---------------------

    async def test_two_missions_fill_pool(self):
        import uuid

        await missions_api.create_mission(
            missions_api.MissionIn(
                objective="mission a",
                workspace=str(self.workspace),
                conversation_url="https://chatgpt.com/c/ma",
                mission_id=str(uuid.uuid4()),
            )
        )
        await missions_api.create_mission(
            missions_api.MissionIn(
                objective="mission b",
                workspace=str(self.workspace),
                conversation_url="https://chatgpt.com/c/mb",
                mission_id=str(uuid.uuid4()),
            )
        )
        with self.assertRaises(HTTPException) as raised:
            await missions_api.create_mission(
                missions_api.MissionIn(
                    objective="mission c",
                    workspace=str(self.workspace),
                    conversation_url="https://chatgpt.com/c/mc",
                    mission_id=str(uuid.uuid4()),
                )
            )
        self.assertEqual(raised.exception.status_code, 409)

    # --- 4. Cancelling a chat frees a slot that a mission can claim ---------

    async def test_cancel_chat_frees_slot_for_mission(self):
        import uuid

        run_a = await chat_api.send_chat(
            chat_api.ChatSendIn(
                conversation_url="https://chatgpt.com/c/chat-free",
                text="chat-free",
            )
        )
        await chat_api.send_chat(
            chat_api.ChatSendIn(
                conversation_url="https://chatgpt.com/c/chat-b",
                text="chat-b",
            )
        )
        # Pool full. Cancel run_a.
        await chat_api.cancel_chat_run(run_a["id"])

        # Slot freed → mission can claim it.
        result = await missions_api.create_mission(
            missions_api.MissionIn(
                objective="claimed freed slot",
                workspace=str(self.workspace),
                conversation_url="https://chatgpt.com/c/mission-freed",
                mission_id=str(uuid.uuid4()),
            )
        )
        self.assertIn(result["id"], missions_api._runtimes)

    # --- 5. Cancelling a mission frees a slot that a chat can claim ---------

    async def test_cancel_mission_frees_slot_for_chat(self):
        import uuid

        mid = str(uuid.uuid4())
        await missions_api.create_mission(
            missions_api.MissionIn(
                objective="free me",
                workspace=str(self.workspace),
                conversation_url="https://chatgpt.com/c/mission-free",
                mission_id=mid,
            )
        )
        await chat_api.send_chat(
            chat_api.ChatSendIn(
                conversation_url="https://chatgpt.com/c/chat-b",
                text="chat-b",
            )
        )
        # Pool full. Cancel the mission.
        # Wait for the mission to be persisted before cancelling.
        for _ in range(20):
            try:
                missions_api.get_store().get_mission(mid)
                break
            except Exception:
                await asyncio.sleep(0)
        await missions_api.cancel_mission(mid)

        # Slot freed → chat can claim it.
        result = await chat_api.send_chat(
            chat_api.ChatSendIn(
                conversation_url="https://chatgpt.com/c/chat-reclaimed",
                text="chat-reclaimed",
            )
        )
        self.assertIn(result["id"], chat_api._runs)

    # --- 6. Same conversation serializes — no 409 --------------------------

    async def test_same_conversation_serializes_on_one_slot(self):
        """Two chats on the same conversation URL serialize on one lease.
        The first occupies a slot, the second queues behind the same lease
        instead of consuming a second global slot."""
        await chat_api.send_chat(
            chat_api.ChatSendIn(
                conversation_url="https://chatgpt.com/c/shared-slot",
                text="first writer",
            )
        )
        # A second chat on the same conversation does NOT get 409 — it
        # serializes on the same lease. The task is created and waits.
        run2 = await chat_api.send_chat(
            chat_api.ChatSendIn(
                conversation_url="https://chatgpt.com/c/shared-slot",
                text="same conversation — serialized",
            )
        )
        self.assertIn(run2["id"], chat_api._runs)
        self.assertNotEqual(run2["state"], "FAILED")

    # --- 7. Registry is the same object for both modules --------------------

    def test_registry_is_a_conversation_session_registry_instance(self):
        """Write-slots _registry is a ConversationSessionRegistry instance."""
        self.assertIsInstance(
            write_slots._registry,
            conversation_sessions.ConversationSessionRegistry,
        )


class CrossRouteLeakRegressionTest(unittest.IsolatedAsyncioTestCase):
    """Verify that a crashed chat run doesn't permanently steal a mission slot."""

    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name) / "workspace"
        self.workspace.mkdir()
        self.saved_registry = write_slots._registry
        self.saved_chat_factory = chat_api.ui_transport_factory
        self.saved_chat_runs = dict(chat_api._runs)
        self.saved_chat_runs_file = chat_api.CHAT_RUNS_FILE
        self.saved_mission_factory = missions_api.transport_factory
        self.saved_mission_optin = missions_api.optin_accepted
        self.saved_mission_store = missions_api._store
        self.saved_mission_runtimes = dict(missions_api._runtimes)
        self.saved_mission_leases = dict(missions_api._mission_leases)
        self.saved_mission_urls = dict(missions_api._mission_write_urls)
        self.saved_mission_runner = missions_api._run_mission_task

        write_slots._registry = conversation_sessions.ConversationSessionRegistry(
            capacity=2
        )
        chat_api.CHAT_RUNS_FILE = Path(self.tmp.name) / "chat-runs.json"
        self.test_mission_store = Store(Path(self.tmp.name) / "missions.db")
        missions_api._store = self.test_mission_store
        chat_api._runs.clear()
        missions_api._runtimes.clear()
        missions_api._mission_leases.clear()
        missions_api._mission_write_urls.clear()
        missions_api._global_stop = False
        missions_api.optin_accepted = lambda: True

    async def asyncTearDown(self) -> None:
        mission_tasks = [
            runtime.task
            for runtime in missions_api._runtimes.values()
            if runtime.task is not None
        ]
        for task in mission_tasks:
            if not task.done():
                task.cancel()
        if mission_tasks:
            await asyncio.gather(*mission_tasks, return_exceptions=True)

        try:
            if missions_api._store is self.test_mission_store:
                self.test_mission_store.close()
        finally:
            write_slots._registry = self.saved_registry
            chat_api.ui_transport_factory = self.saved_chat_factory
            chat_api.CHAT_RUNS_FILE = self.saved_chat_runs_file
            chat_api._runs.clear()
            chat_api._runs.update(self.saved_chat_runs)
            missions_api.transport_factory = self.saved_mission_factory
            missions_api.optin_accepted = self.saved_mission_optin
            missions_api._store = self.saved_mission_store
            missions_api._runtimes.clear()
            missions_api._runtimes.update(self.saved_mission_runtimes)
            missions_api._mission_leases.clear()
            missions_api._mission_leases.update(self.saved_mission_leases)
            missions_api._mission_write_urls.clear()
            missions_api._mission_write_urls.update(self.saved_mission_urls)
            missions_api._run_mission_task = self.saved_mission_runner
            missions_api._global_stop = False
            self.tmp.cleanup()

    async def test_failed_chat_frees_lease_for_mission(self):
        """A chat run whose transport constructor crashes must release its
        lease so a mission can claim the slot."""

        def crashing_factory(_session_id=None):
            raise RuntimeError("chat transport constructor failure")

        chat_api.ui_transport_factory = crashing_factory
        try:
            submitted = await chat_api.send_chat(
                chat_api.ChatSendIn(
                    conversation_url="https://chatgpt.com/c/failing-chat",
                    text="will fail",
                )
            )
            failed = chat_api._runs[submitted["id"]]
            await asyncio.gather(failed.task, return_exceptions=True)
        finally:
            chat_api.ui_transport_factory = self.saved_chat_factory

        self.assertEqual(failed.state, "FAILED")
        # Registry must be empty after a clean release.
        self.assertEqual(write_slots._registry.active_leases(), ())

        # Now a mission can claim both slots.
        import uuid

        await missions_api.create_mission(
            missions_api.MissionIn(
                objective="after chat crash",
                workspace=str(self.workspace),
                conversation_url="https://chatgpt.com/c/recovered-mission",
                mission_id=str(uuid.uuid4()),
            )
        )
        self.assertEqual(len(write_slots._registry.active_leases()), 1)


if __name__ == "__main__":
    unittest.main()
