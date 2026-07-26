"""Autonomous-mission API (Phase 6) — FastAPI router included by server.py.

Exposes the Phase 1-5 machinery (cortex.v1 protocol, SQLite store, structured
tools, policy engine, ChatGPT web transport, Mode A runner) over HTTP for the
console UI. The pre-existing manual task API stays untouched as the fallback
mode.

Safety posture:
- §6: nothing is ever sent to ChatGPT unless the user has explicitly accepted
  the experimental-transport warning (persisted server-side).
- §17: STOP EVERYTHING blocks new runs, denies pending approvals, cancels
  browser generation best-effort, and preserves all evidence.
- Resume after pause/restart never auto-resends: the resumed loop awaits the
  pending response instead of re-emitting the last message.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from executor.policy import (  # noqa: E402
    READ_ONLY_AUTOMATIC,
    SCOPE_ALL_WRITES_FOR_MISSION,
    SCOPE_ONCE,
    SCOPE_TOOL_FOR_MISSION,
    WRITE_AUTOMATIC,
    WRITE_WITH_APPROVALS,
    PolicyEngine,
)
from executor.tools import ToolExecutor  # noqa: E402
from orchestration.loop import MissionLoop, MockReply  # noqa: E402
from orchestration.runner import (  # noqa: E402
    ModeARunner,
    OptInRequired,
    TransportOrchestratorClient,
    render_contract,
)
from orchestration.state import Budgets  # noqa: E402
from orchestration.store import Store, StoreError  # noqa: E402
from orchestration import protocol  # noqa: E402
from transport.chatgpt_web.adapter import (  # noqa: E402
    EXPERIMENTAL_TRANSPORT_WARNING,
    ChatGPTWebTransport,
    ConversationLock,
)
from transport.browser import create_transport  # noqa: E402
import write_slots  # noqa: E402

CONSOLE_DIR = Path(__file__).resolve().parent
DATA_DIR = CONSOLE_DIR / "data"
OPTIN_FILE = DATA_DIR / "transport-optin.json"
DB_PATH = DATA_DIR / "cortex.db"

router = APIRouter(prefix="/api")

# ------------------------------------------------------------- store / opt-in

_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _store = Store(DB_PATH)
    _restore_persisted_leases()
    return _store


def optin_accepted() -> bool:
    try:
        return bool(json.loads(OPTIN_FILE.read_text(encoding="utf-8")).get("accepted"))
    except (OSError, json.JSONDecodeError):
        return False


def _set_optin(accepted: bool) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OPTIN_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"accepted": bool(accepted)}), encoding="utf-8")
    tmp.replace(OPTIN_FILE)


# ------------------------------------------------------------ mission runtime


@dataclass
class MissionRuntime:
    mission_id: str
    task: asyncio.Task | None = None
    policy: PolicyEngine | None = None
    transport: ChatGPTWebTransport | None = None
    approval_event: asyncio.Event = field(default_factory=asyncio.Event)
    approval_scope: str | None = None
    stopped: bool = False
    conversation_key: str | None = None
    lease: object | None = None
    lease_release_ready: bool = True
    quiescence_task: asyncio.Task | None = None
    transport_closed: bool = False


_runtimes: dict[str, MissionRuntime] = {}
_mission_leases: dict[str, object] = {}
_global_stop = False
STOP_QUIESCE_TIMEOUT = 1.0


def _restore_persisted_leases() -> None:
    """Reserve every persisted non-terminal mission writer after restart."""
    if _store is None:
        return
    terminal = {"COMPLETED", "BLOCKED", "FAILED", "CANCELLED"}
    for mission in _store.rows("missions", order_by="updated_at DESC"):
        mission_id = str(mission["id"])
        if mission.get("state") in terminal or mission_id in _mission_leases:
            continue
        bindings = _store.rows("conversation_bindings", mission_id, order_by="rowid")
        if not bindings:
            continue
        binding = bindings[-1]
        conversation_key = (
            binding.get("conversation_target")
            or binding.get("conversation_url")
        )
        session_id = binding.get("session_id")
        if not session_id:
            if (conversation_key or "").strip().rstrip("/") == "https://chatgpt.com":
                conversation_key = write_slots.new_conversation_key()
            session_id = f"cortex-conv-{uuid.uuid4().hex}"
            try:
                _store.update_conversation_binding(
                    mission_id,
                    binding.get("conversation_url") or conversation_key,
                    binding.get("conversation_title"),
                    binding.get("browser_target_id"),
                    session_id=session_id,
                    conversation_target=conversation_key,
                )
            except Exception as exc:
                _fail_mission(_store, mission_id, f"lease migration failed: {exc}")
                continue
        try:
            lease = write_slots.restore_writer(
                conversation_key,
                session_id,
                binding.get("conversation_url") or conversation_key,
            )
        except (
            ValueError,
            write_slots.SessionCapacityError,
            write_slots.SessionRekeyError,
        ):
            continue
        _mission_leases[mission_id] = lease
        _mission_write_urls[mission_id] = binding.get("conversation_url") or conversation_key

# Overridable factories (tests inject fixture drivers).
READ_ONLY_SESSION_ID = "cortex-missions-read-only"
transport_factory = create_transport


def _make_transport(session_id: str) -> ChatGPTWebTransport:
    try:
        return transport_factory(session_id)
    except TypeError:
        return transport_factory()

_APPROVAL_SCOPE_MAP = {
    "once": SCOPE_ONCE,
    "tool": SCOPE_TOOL_FOR_MISSION,
    "all-writes": SCOPE_ALL_WRITES_FOR_MISSION,
}

_POLICY_MODES = {READ_ONLY_AUTOMATIC, WRITE_WITH_APPROVALS, WRITE_AUTOMATIC}


def _make_approval_callback(rt: MissionRuntime):
    async def callback(decision: dict, policy_decision) -> str | None:
        rt.approval_event.clear()
        rt.approval_scope = None
        waiter = asyncio.create_task(rt.approval_event.wait())
        try:
            while not waiter.done():
                if rt.stopped:
                    waiter.cancel()
                    return None
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            return None
        scope = rt.approval_scope
        tool = (decision.get("action") or {}).get("tool")
        if scope and rt.policy is not None and tool:
            try:
                rt.policy.approve(scope, tool=tool if scope != SCOPE_ALL_WRITES_FOR_MISSION else None)
            except ValueError:
                pass
        return scope

    return callback


def _build_runtime(mission_id: str, workspace: str, approval_mode: str,
                   _legacy_primary: str | None, _legacy_fallback: str | None,
                   max_iterations: int,
                   max_duration_seconds: int, allow_processes: bool = False,
                   lease=None) -> MissionRuntime:
    if lease is None:
        raise RuntimeError("writer runtime requires an acquired SessionLease")
    ws = Path(workspace).expanduser().resolve()
    if not ws.is_dir():
        raise HTTPException(status_code=422, detail=f"workspace is not a directory: {ws}")
    tools = ToolExecutor(ws)
    policy = PolicyEngine(
        ws,
        mode=approval_mode,
        allow_processes=allow_processes,
    )
    budgets = Budgets(max_iterations=max_iterations, max_duration_seconds=max_duration_seconds)
    rt = MissionRuntime(mission_id=mission_id)
    rt.policy = policy
    rt.lease = lease
    rt.conversation_key = lease.conversation_key
    rt.transport = _make_transport(lease.session_id)
    rt._tools = tools  # type: ignore[attr-defined]
    rt._budgets = budgets  # type: ignore[attr-defined]
    _runtimes[mission_id] = rt
    return rt


async def _persist_mission_lease(rt: MissionRuntime) -> None:
    """Persist/rekey a pre-bound lease when a provisional chat becomes canonical."""
    if rt.lease is None:
        return
    _mission_leases.setdefault(rt.mission_id, rt.lease)
    store = get_store()
    persisted = False
    for _ in range(500):
        bindings = store.rows("conversation_bindings", rt.mission_id, order_by="rowid")
        if bindings:
            binding = bindings[-1]
            current_url = binding["conversation_url"]
            if (
                not persisted
                or binding.get("session_id") != rt.lease.session_id
                or binding.get("conversation_target") != rt.conversation_key
            ):
                store.update_conversation_binding(
                    rt.mission_id,
                    current_url,
                    binding.get("conversation_title"),
                    binding.get("browser_target_id"),
                    session_id=rt.lease.session_id,
                    conversation_target=rt.conversation_key,
                )
                persisted = True
            if not (rt.conversation_key or "").startswith("provisional:"):
                return
            if "/c/" in current_url:
                rt.lease = await write_slots.rekey(rt.conversation_key, current_url)
                rt.conversation_key = rt.lease.conversation_key
                _mission_leases[rt.mission_id] = rt.lease
                _mission_write_urls[rt.mission_id] = current_url
                store.update_conversation_binding(
                    rt.mission_id,
                    current_url,
                    binding.get("conversation_title"),
                    binding.get("browser_target_id"),
                    session_id=rt.lease.session_id,
                    conversation_target=current_url,
                )
                return
        await asyncio.sleep(0.01)


async def _release_terminal_mission(rt: MissionRuntime) -> None:
    if not rt.lease_release_ready:
        return
    try:
        state = get_store().get_mission(rt.mission_id)["state"]
    except StoreError:
        state = "FAILED"
    if state not in {"COMPLETED", "BLOCKED", "FAILED", "CANCELLED"}:
        return
    if not rt.transport_closed:
        rt.transport_closed = True
        closer = getattr(rt.transport, "close", None)
        if closer is not None:
            try:
                await closer()
            except Exception:
                pass
    if rt.lease is not None:
        await rt.lease.release()
        rt.lease = None
    _mission_leases.pop(rt.mission_id, None)
    _mission_write_urls.pop(rt.mission_id, None)


# ------------------------------------------------------------------- schemas


class MissionIn(BaseModel):
    objective: str
    workspace: str
    constraints: list[str] = []
    conversation_url: str = ""
    new_conversation: bool = False
    max_iterations: int = 25
    max_duration_minutes: int = 60
    approval_policy: str = WRITE_WITH_APPROVALS
    # Accepted only so pre-v0.5 clients do not fail validation.  Mode A uses
    # deterministic tools and intentionally ignores both legacy promises.
    primary_executor: str | None = None
    fallback_executor: str | None = None
    allow_processes: bool = False
    mission_id: str = ""  # optional client-supplied UUID (idempotent submission)


class ApprovalIn(BaseModel):
    scope: str  # once | tool | all-writes
    approve: bool = True


class OptInIn(BaseModel):
    accepted: bool


# ------------------------------------------------------------------- helpers


def _mission_or_404(store: Store, mission_id: str) -> dict:
    try:
        return store.get_mission(mission_id)
    except StoreError:
        raise HTTPException(status_code=404, detail="mission not found")


def _with_mode_a_runtime_truth(mission: dict) -> dict:
    return {
        **mission,
        "executor_kind": "deterministic",
        "executor_model_used": None,
        "runtime_mode": "live",
    }


def _objective_with_constraints(body: MissionIn) -> str:
    objective = body.objective.strip()
    constraints = [c.strip() for c in body.constraints if c.strip()]
    if constraints:
        objective += "\n\nConstraints:\n" + "\n".join(f"- {c}" for c in constraints)
    return objective


def _fail_mission(store: Store, mission_id: str, reason: str) -> None:
    """Mark a mission FAILED from any non-terminal state (adjacency-safe)."""
    try:
        store.transition(mission_id, "FAILED", pause_reason=reason)
        return
    except StoreError:
        pass
    for path in (("INITIALIZING_MISSION", "FAILED"), ("CANCELLED",)):
        try:
            for step in path:
                store.transition(mission_id, step, pause_reason=reason)
            return
        except StoreError:
            continue


class _PrecreatedMissionStore:
    """Let ModeARunner reuse the synchronously persisted mission and binding."""

    def __init__(self, store: Store, mission_id: str):
        self._store = store
        self._mission_id = mission_id

    def create_mission(self, mission_id: str, *args, **kwargs) -> dict:
        if mission_id != self._mission_id:
            return self._store.create_mission(mission_id, *args, **kwargs)
        return self._store.get_mission(mission_id)

    def __getattr__(self, name: str):
        return getattr(self._store, name)


async def _run_mission_task(rt: MissionRuntime, objective: str, body: MissionIn) -> None:
    store = get_store()
    runner = ModeARunner(
        store=_PrecreatedMissionStore(store, rt.mission_id),
        transport=rt.transport,
        tools=rt._tools,  # type: ignore[attr-defined]
        policy=rt.policy,
        budgets=rt._budgets,  # type: ignore[attr-defined]
        approval_callback=_make_approval_callback(rt),
        experimental_transport_accepted=True,  # enforced by the endpoint
    )
    async def run() -> dict:
        if body.new_conversation:
            return await runner.run_mission(
                objective,
                new_conversation_url=body.conversation_url,
                mission_id=rt.mission_id,
            )
        return await runner.run_mission(
            objective,
            conversation_url=body.conversation_url,
            mission_id=rt.mission_id,
        )

    runner_task = asyncio.create_task(run())
    binding_task = asyncio.create_task(_persist_mission_lease(rt))
    binding_error = None
    try:
        done, _ = await asyncio.wait(
            {runner_task, binding_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if binding_task in done:
            try:
                await binding_task
            except Exception as exc:
                binding_error = exc
                runner_task.cancel()
                await asyncio.gather(runner_task, return_exceptions=True)
            else:
                await runner_task
        else:
            await runner_task
    except OptInRequired:
        pass
    except asyncio.CancelledError:
        runner_task.cancel()
        await asyncio.gather(runner_task, return_exceptions=True)
        raise
    except Exception as exc:  # never leave a mission stuck running
        _fail_mission(store, rt.mission_id, f"runner crashed: {exc}")
        store.record_transport_event(
            str(uuid.uuid4()), rt.mission_id, "RUNNER_CRASHED", {"error": str(exc)}
        )
    finally:
        if not runner_task.done():
            runner_task.cancel()
            await asyncio.gather(runner_task, return_exceptions=True)
        if not binding_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(binding_task), timeout=0.2)
            except asyncio.TimeoutError:
                binding_task.cancel()
                results = await asyncio.gather(binding_task, return_exceptions=True)
                if results and isinstance(results[0], Exception):
                    binding_error = results[0]
        else:
            try:
                await binding_task
            except Exception as exc:
                binding_error = exc
        if binding_error is not None:
            _fail_mission(store, rt.mission_id, f"lease persistence failed: {binding_error}")
            try:
                store.record_transport_event(
                    str(uuid.uuid4()),
                    rt.mission_id,
                    "LEASE_PERSISTENCE_FAILED",
                    {"error": str(binding_error)},
                )
            except Exception:
                pass
        await _release_terminal_mission(rt)


async def _resume_mission_task(rt: MissionRuntime) -> None:
    store = get_store()
    client = TransportOrchestratorClient(rt.transport, store=store, mission_id=rt.mission_id)
    loop = MissionLoop(
        store=store,
        mission_id=rt.mission_id,
        orchestrator=client,
        tools=rt._tools,  # type: ignore[attr-defined]
        policy=rt.policy,
        approval_callback=_make_approval_callback(rt),
        budgets=rt._budgets,  # type: ignore[attr-defined]
    )

    # A user may pause while ChatGPT is already producing a reply. The fresh
    # runtime created for resume cannot see MissionLoop._stashed from the old
    # task, so recover the latest unconsumed reply from SQLite before deciding
    # whether to send or await anything.
    transport_events = store.rows("transport_events", rt.mission_id, order_by="rowid")
    consumed_stashes = {
        str(json.loads(event.get("detail_json") or "{}").get("stash_event_id"))
        for event in transport_events
        if event.get("event_type") == "PAUSED_RESPONSE_CONSUMED"
    }
    pending_stash = None
    for event in reversed(transport_events):
        if event.get("event_type") != "PAUSED_RESPONSE_STASHED":
            continue
        if str(event.get("id")) in consumed_stashes:
            continue
        try:
            detail = json.loads(event.get("detail_json") or "{}")
        except json.JSONDecodeError:
            continue
        if detail.get("text") and detail.get("message_id"):
            pending_stash = (event, detail)
            break
    if pending_stash is not None:
        stash_event, stash_detail = pending_stash
        loop._stashed = MockReply(
            text=str(stash_detail["text"]),
            message_id=str(stash_detail["message_id"]),
        )
        store.record_transport_event(
            str(uuid.uuid4()),
            rt.mission_id,
            "PAUSED_RESPONSE_CONSUMED",
            {"stash_event_id": stash_event["id"]},
        )

    # Resume without ever re-sending a message ChatGPT already answered, and
    # without awaiting a reply that will never come:
    # - REPORT_SENT is recorded at finalize time, MESSAGE_DELIVERED only after
    #   a proven browser send. A report recorded but not delivered must be
    #   resent; anything else means we are waiting on ChatGPT.
    events = store.rows("transport_events", rt.mission_id, order_by="rowid")
    delivered = [e for e in events if e.get("event_type") == "MESSAGE_DELIVERED"]
    reports_sent = [e for e in events if e.get("event_type") == "REPORT_SENT"]
    decisions = [r for r in store.rows("orchestrator_decisions", rt.mission_id)
                 if r.get("valid") == 1]
    if decisions and len(delivered) < 1 + len(reports_sent) and reports_sent:
        try:
            last_report = json.loads(reports_sent[-1].get("detail_json") or "{}")["report"]
            loop._pending = protocol.render_report_message(last_report)
        except (KeyError, json.JSONDecodeError):
            loop._pending = None
    elif not delivered:
        # Nothing provably sent (e.g. crash before the contract send).
        mission = store.get_mission(rt.mission_id)
        loop._pending = render_contract(
            mission["objective"], rt.mission_id, str(rt._tools.workspace)  # type: ignore[attr-defined]
        )
    else:
        loop._pending = None  # contract+reports delivered → await ChatGPT
    try:
        await loop.run()
    except Exception as exc:
        _fail_mission(store, rt.mission_id, f"resume crashed: {exc}")
        store.record_transport_event(
            str(uuid.uuid4()), rt.mission_id, "RUNNER_CRASHED", {"error": str(exc)}
        )
    finally:
        await _release_terminal_mission(rt)


async def _release_after_quiescence(
    rt: MissionRuntime,
    activities: list[asyncio.Task],
) -> None:
    if activities:
        await asyncio.gather(*activities, return_exceptions=True)
    rt.lease_release_ready = True
    await _release_terminal_mission(rt)


async def _stop_runtime(rt: MissionRuntime) -> bool:
    rt.stopped = True
    rt.lease_release_ready = False
    rt.approval_scope = None
    rt.approval_event.set()
    store = get_store()
    try:
        store.transition(rt.mission_id, "CANCELLED", pause_reason="STOP_EVERYTHING")
    except StoreError:
        pass  # already terminal or a state that cannot transition — evidence intact
    if rt.quiescence_task is None:
        activities: list[asyncio.Task] = []
        if rt.transport is not None and rt.transport.lock is not None:
            activities.append(asyncio.create_task(rt.transport.cancel_generation()))
        if rt.task is not None and not rt.task.done():
            rt.task.cancel()
            activities.append(rt.task)
        rt.quiescence_task = asyncio.create_task(
            _release_after_quiescence(rt, activities)
        )
    done, _ = await asyncio.wait(
        {rt.quiescence_task},
        timeout=STOP_QUIESCE_TIMEOUT,
    )
    return bool(done)


# ------------------------------------------------------------------- routes


@router.get("/transport/status")
async def transport_status() -> dict:
    return {
        "experimental_warning": EXPERIMENTAL_TRANSPORT_WARNING,
        "opt_in_accepted": optin_accepted(),
        "global_stop": _global_stop,
    }


@router.post("/transport/opt-in")
async def transport_optin(body: OptInIn) -> dict:
    _set_optin(body.accepted)
    return {"opt_in_accepted": optin_accepted()}


@router.post("/transport/stop-everything")
async def stop_everything() -> dict:
    """§17 emergency stop: no more browser messages, no more local actions,
    current approvals resolved as denied, evidence preserved."""
    global _global_stop
    _global_stop = True
    runtimes = list(_runtimes.values())
    await asyncio.gather(
        *(_stop_runtime(rt) for rt in runtimes),
        return_exceptions=True,
    )
    return {"global_stop": True, "missions_stopped": len(_runtimes)}


@router.post("/transport/stop-reset")
async def stop_reset() -> dict:
    global _global_stop
    _global_stop = False
    return {"global_stop": False}


@router.get("/transport/probe")
async def transport_probe() -> dict:
    """Read-only DOM health check on the live ChatGPT tab: reports which
    adaptive selector currently matches each role (composer, messages, send,
    stop), with failures/warnings and raw diagnostics for UI regressions."""
    transport = _make_transport(READ_ONLY_SESSION_ID)
    try:
        return await transport.probe()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"probe failed: {exc}")


@router.get("/transport/perf")
async def transport_perf() -> dict:
    """WebBridge call timings (avg/p95/max per action) — where latency goes."""
    from transport.chatgpt_web import adapter

    return adapter.perf_stats()


@router.get("/conversations")
async def list_conversations() -> list[dict]:
    transport = _make_transport(READ_ONLY_SESSION_ID)
    try:
        return await transport.list_conversations()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"cannot list conversations: {exc}")


@router.post("/missions", status_code=201)
async def create_mission(body: MissionIn) -> dict:
    global _global_stop
    if _global_stop:
        raise HTTPException(status_code=409, detail="STOP EVERYTHING is active; reset it first")
    if not optin_accepted():
        raise HTTPException(
            status_code=403,
            detail="Experimental ChatGPT Web Transport not accepted. "
                   "Read the warning and POST /api/transport/opt-in first.",
        )
    if not body.objective.strip():
        raise HTTPException(status_code=422, detail="objective must not be empty")
    if not body.conversation_url.strip():
        raise HTTPException(status_code=422, detail="conversation_url must not be empty")
    if body.approval_policy not in _POLICY_MODES:
        raise HTTPException(status_code=422, detail=f"unknown approval policy {body.approval_policy}")

    mission_id = body.mission_id.strip() or str(uuid.uuid4())
    try:
        uuid.UUID(mission_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="mission_id must be a UUID")
    store = get_store()
    try:
        store.get_mission(mission_id)
        raise HTTPException(status_code=409, detail=f"mission {mission_id} already exists")
    except StoreError:
        pass  # unknown id — good
    conversation_key = (
        write_slots.new_conversation_key()
        if body.new_conversation
        or body.conversation_url.strip().rstrip("/") == "https://chatgpt.com"
        else body.conversation_url
    )
    try:
        lease = await write_slots.acquire_writer(conversation_key)
    except write_slots.SessionCapacityError:
        raise HTTPException(status_code=409, detail=write_slots.REFUSAL_MESSAGE)
    objective = _objective_with_constraints(body)
    try:
        store.create_mission(
            mission_id,
            objective,
            str(Path(body.workspace).expanduser().resolve()),
            max_iterations=body.max_iterations,
            max_duration_seconds=body.max_duration_minutes * 60,
        )
        store.bind_conversation(
            str(uuid.uuid4()),
            mission_id,
            body.conversation_url,
            session_id=lease.session_id,
            conversation_target=lease.conversation_key,
        )
        store.transition(mission_id, "INITIALIZING_MISSION")
        rt = _build_runtime(
            mission_id, body.workspace, body.approval_policy,
            None, None,
            body.max_iterations, body.max_duration_minutes * 60, body.allow_processes,
            lease=lease,
        )
    except Exception as exc:
        try:
            _fail_mission(store, mission_id, f"mission creation failed: {exc}")
        except Exception:
            pass
        await lease.release()
        _mission_leases.pop(mission_id, None)
        _mission_write_urls.pop(mission_id, None)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=503, detail=f"cannot create mission: {exc}")
    _mission_leases[mission_id] = lease
    _mission_write_urls[mission_id] = body.conversation_url
    rt.task = asyncio.create_task(
        _run_mission_task(rt, objective, body)
    )
    return {
        "id": mission_id,
        "state": "INITIALIZING_MISSION",
        "executor_kind": "deterministic",
        "executor_model_used": None,
        "runtime_mode": "live",
    }


# P2b: mission_id -> ChatGPT conversation URL the mission writes into.
_mission_write_urls: dict[str, str] = {}


def active_mission_conversations() -> list[str]:
    """ChatGPT URLs of non-terminal missions (two-write-conversation guard)."""
    urls: list[str] = []
    try:
        rows = get_store().rows("missions", order_by="updated_at DESC")
    except Exception:
        return urls
    terminal = {"COMPLETED", "BLOCKED", "FAILED", "CANCELLED"}
    for row in rows:
        if row.get("state") in terminal:
            continue
        url = _mission_write_urls.get(row.get("id", ""))
        if url:
            urls.append(url)
    return urls


@router.get("/missions")
async def list_missions() -> list[dict]:
    return [
        _with_mode_a_runtime_truth(row)
        for row in get_store().rows("missions", order_by="created_at DESC")
    ]


@router.get("/missions/{mission_id}")
async def get_mission(mission_id: str) -> dict:
    store = get_store()
    mission = _mission_or_404(store, mission_id)
    timeline = {
        table: store.rows(table, mission_id, order_by="rowid")
        for table in (
            "conversation_bindings", "iterations", "orchestrator_decisions",
            "policy_decisions", "approvals", "tool_executions",
            "validation_results", "transport_events", "artifacts",
        )
    }
    rt = _runtimes.get(mission_id)
    return {
        "mission": _with_mode_a_runtime_truth(mission),
        "timeline": timeline,
        "awaiting_approval": rt is not None and not rt.approval_event.is_set()
        and mission["state"] == "WAITING_FOR_APPROVAL",
        "stopped": rt.stopped if rt else False,
    }


@router.get("/missions/{mission_id}/report")
async def download_report(mission_id: str) -> dict:
    """Full evidence bundle (JSON) for the mission."""
    return await get_mission(mission_id)


@router.get("/missions/{mission_id}/fallback-payload")
async def fallback_payload(mission_id: str) -> dict:
    store = get_store()
    _mission_or_404(store, mission_id)
    events = [
        r for r in store.rows("transport_events", mission_id, order_by="rowid")
        if r.get("event_type") == "REPORT_SENT"
    ]
    report = None
    if events:
        try:
            detail = json.loads(events[-1].get("detail_json") or "{}")
            report = detail.get("report")  # full report persisted since Phase 6
        except json.JSONDecodeError:
            report = None
    parts = ["[Cortex Bridge — manual fallback payload]"]
    if report:
        parts.append(protocol.render_report_message(report))
    else:
        parts.append("No persisted report for this mission yet — "
                     "copy the latest mission state from the console.")
    return {"payload": "\n\n".join(parts)}


@router.post("/missions/{mission_id}/pause")
async def pause_mission(mission_id: str) -> dict:
    store = get_store()
    _mission_or_404(store, mission_id)
    try:
        store.transition(mission_id, "PAUSED", pause_reason="USER_PAUSE")
    except StoreError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"state": "PAUSED"}


@router.post("/missions/{mission_id}/resume")
async def resume_mission(mission_id: str) -> dict:
    global _global_stop
    if _global_stop:
        raise HTTPException(status_code=409, detail="STOP EVERYTHING is active; reset it first")
    store = get_store()
    mission = _mission_or_404(store, mission_id)
    if mission["state"] not in ("PAUSED", "PAUSED_RECOVERY_REQUIRED"):
        raise HTTPException(status_code=409, detail=f"cannot resume from {mission['state']}")
    # Rebuild the runtime: re-attach the locked conversation, never resend.
    bindings = store.rows("conversation_bindings", mission_id, order_by="rowid")
    lease = _mission_leases.get(mission_id)
    if lease is None and bindings and bindings[-1].get("session_id"):
        b = bindings[-1]
        try:
            lease = write_slots.restore_writer(
                b.get("conversation_target") or b["conversation_url"],
                b["session_id"],
                b["conversation_url"],
            )
        except (
            write_slots.SessionCapacityError,
            write_slots.SessionRekeyError,
        ):
            raise HTTPException(status_code=409, detail=write_slots.REFUSAL_MESSAGE)
        _mission_leases[mission_id] = lease
    if lease is None:
        raise HTTPException(status_code=409, detail="mission has no durable writer lease")
    rt: MissionRuntime | None = None
    try:
        rt = _build_runtime(
            mission_id, mission["workspace"], WRITE_WITH_APPROVALS,
            None, None,
            mission["max_iterations"], mission["max_duration_seconds"],
            lease=lease,
        )
        if bindings:
            b = bindings[0]
            if "/c/" in b["conversation_url"]:
                await rt.transport.attach(ConversationLock(
                    url=b["conversation_url"],
                    identity=b.get("browser_target_id") or b["conversation_url"],
                    title=b.get("conversation_title"),
                    selected_at=b.get("selected_at") or 0.0,
                ))
            else:
                # Pending new chat: the contract send never created a /c/<id>
                # conversation, so there is no identity to attach to. Re-open
                # the fresh chat surface; the lock is captured on next send.
                await rt.transport.start_new_conversation(b["conversation_url"])
        store.resume(mission_id, "WAITING_FOR_CHATGPT")
        rt.task = asyncio.create_task(_resume_mission_task(rt))
    except Exception as exc:
        if store.get_mission(mission_id)["state"] in {
            "PAUSED",
            "PAUSED_RECOVERY_REQUIRED",
        }:
            try:
                store.resume(mission_id, "TRANSPORT_ERROR")
            except StoreError:
                pass
        _fail_mission(store, mission_id, f"mission resume failed: {exc}")
        rt = rt or _runtimes.get(mission_id)
        if rt is not None:
            await _release_terminal_mission(rt)
        else:
            await lease.release()
            _mission_leases.pop(mission_id, None)
            _mission_write_urls.pop(mission_id, None)
        _runtimes.pop(mission_id, None)
        raise HTTPException(status_code=503, detail=f"cannot resume mission: {exc}") from exc
    return {"state": "WAITING_FOR_CHATGPT"}


@router.post("/missions/{mission_id}/cancel")
async def cancel_mission(mission_id: str) -> dict:
    store = get_store()
    _mission_or_404(store, mission_id)
    rt = _runtimes.get(mission_id)
    if rt is not None:
        await _stop_runtime(rt)
    else:
        try:
            store.transition(mission_id, "CANCELLED", pause_reason="USER_CANCEL")
        except StoreError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        lease = _mission_leases.get(mission_id)
        if lease is not None:
            await lease.release()
            _mission_leases.pop(mission_id, None)
            _mission_write_urls.pop(mission_id, None)
    return {"state": "CANCELLED"}


@router.post("/missions/{mission_id}/approve")
async def approve_mission(mission_id: str, body: ApprovalIn) -> dict:
    store = get_store()
    _mission_or_404(store, mission_id)
    rt = _runtimes.get(mission_id)
    if rt is None or rt.approval_event.is_set():
        raise HTTPException(status_code=409, detail="no pending approval for this mission")
    if body.approve:
        scope = _APPROVAL_SCOPE_MAP.get(body.scope)
        if scope is None:
            raise HTTPException(status_code=422, detail=f"unknown scope {body.scope}")
        rt.approval_scope = scope
    else:
        rt.approval_scope = None  # rejection → loop records a DENIED report
    rt.approval_event.set()
    return {"approved": body.approve, "scope": body.scope if body.approve else None}
