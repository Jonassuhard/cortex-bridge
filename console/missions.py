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
from orchestration.loop import MissionLoop  # noqa: E402
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
    WebBridgeDriver,
)

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


_runtimes: dict[str, MissionRuntime] = {}
_global_stop = False

# Overridable factories (tests inject fixture drivers).
transport_factory = lambda: ChatGPTWebTransport(WebBridgeDriver())  # noqa: E731

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
                   primary: str, fallback: str, max_iterations: int,
                   max_duration_seconds: int) -> MissionRuntime:
    ws = Path(workspace).expanduser().resolve()
    if not ws.is_dir():
        raise HTTPException(status_code=422, detail=f"workspace is not a directory: {ws}")
    tools = ToolExecutor(ws)
    policy = PolicyEngine(
        ws,
        mode=approval_mode,
        primary_model=primary or "orchestra-executor",
        fallback_model=fallback or "orchestra-executor-fallback",
    )
    budgets = Budgets(max_iterations=max_iterations, max_duration_seconds=max_duration_seconds)
    rt = MissionRuntime(mission_id=mission_id)
    rt.policy = policy
    rt.transport = transport_factory()
    rt._tools = tools  # type: ignore[attr-defined]
    rt._budgets = budgets  # type: ignore[attr-defined]
    _runtimes[mission_id] = rt
    return rt


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
    primary_executor: str = "orchestra-executor"
    fallback_executor: str = "orchestra-executor-fallback"


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


def _objective_with_constraints(body: MissionIn) -> str:
    objective = body.objective.strip()
    constraints = [c.strip() for c in body.constraints if c.strip()]
    if constraints:
        objective += "\n\nConstraints:\n" + "\n".join(f"- {c}" for c in constraints)
    return objective


async def _run_mission_task(rt: MissionRuntime, objective: str, body: MissionIn) -> None:
    runner = ModeARunner(
        store=get_store(),
        transport=rt.transport,
        tools=rt._tools,  # type: ignore[attr-defined]
        policy=rt.policy,
        budgets=rt._budgets,  # type: ignore[attr-defined]
        approval_callback=_make_approval_callback(rt),
        experimental_transport_accepted=True,  # enforced by the endpoint
    )
    try:
        if body.new_conversation:
            await runner.run_mission(objective, new_conversation_url=body.conversation_url,
                                     mission_id=rt.mission_id)
        else:
            await runner.run_mission(objective, conversation_url=body.conversation_url,
                                     mission_id=rt.mission_id)
    except OptInRequired:
        pass
    except Exception as exc:  # never leave a mission stuck running
        store = get_store()
        try:
            store.transition(rt.mission_id, "FAILED", pause_reason=f"runner crashed: {exc}")
        except StoreError:
            pass
        store.record_transport_event(
            str(uuid.uuid4()), rt.mission_id, "RUNNER_CRASHED", {"error": str(exc)}
        )


async def _resume_mission_task(rt: MissionRuntime) -> None:
    store = get_store()
    client = TransportOrchestratorClient(rt.transport)
    loop = MissionLoop(
        store=store,
        mission_id=rt.mission_id,
        orchestrator=client,
        tools=rt._tools,  # type: ignore[attr-defined]
        policy=rt.policy,
        approval_callback=_make_approval_callback(rt),
        budgets=rt._budgets,  # type: ignore[attr-defined]
    )
    # Never auto-resend after a pause/restart: if work already started, await
    # the pending response; otherwise (contract never sent) start fresh.
    if store.count("orchestrator_decisions", rt.mission_id) > 0:
        loop._pending = None
    else:
        mission = store.get_mission(rt.mission_id)
        loop._pending = render_contract(
            mission["objective"], rt.mission_id, str(rt._tools.workspace)  # type: ignore[attr-defined]
        )
    try:
        await loop.run()
    except Exception as exc:
        try:
            store.transition(rt.mission_id, "FAILED", pause_reason=f"resume crashed: {exc}")
        except StoreError:
            pass
        store.record_transport_event(
            str(uuid.uuid4()), rt.mission_id, "RUNNER_CRASHED", {"error": str(exc)}
        )


def _stop_runtime(rt: MissionRuntime) -> None:
    rt.stopped = True
    rt.approval_scope = None
    rt.approval_event.set()
    store = get_store()
    try:
        store.transition(rt.mission_id, "CANCELLED", pause_reason="STOP_EVERYTHING")
    except StoreError:
        pass  # already terminal or a state that cannot transition — evidence intact
    if rt.transport is not None and rt.transport.lock is not None:
        try:
            asyncio.get_running_loop().create_task(rt.transport.cancel_generation())
        except RuntimeError:
            pass


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
    for rt in list(_runtimes.values()):
        _stop_runtime(rt)
    return {"global_stop": True, "missions_stopped": len(_runtimes)}


@router.post("/transport/stop-reset")
async def stop_reset() -> dict:
    global _global_stop
    _global_stop = False
    return {"global_stop": False}


@router.get("/conversations")
async def list_conversations() -> list[dict]:
    transport = transport_factory()
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

    mission_id = str(uuid.uuid4())
    rt = _build_runtime(
        mission_id, body.workspace, body.approval_policy,
        body.primary_executor, body.fallback_executor,
        body.max_iterations, body.max_duration_minutes * 60,
    )
    rt.task = asyncio.create_task(
        _run_mission_task(rt, _objective_with_constraints(body), body)
    )
    return {"id": mission_id, "state": "INITIALIZING_MISSION"}


@router.get("/missions")
async def list_missions() -> list[dict]:
    return get_store().rows("missions", order_by="created_at DESC")


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
        "mission": mission,
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
            report = json.loads(events[-1].get("detail_json") or "{}") or None
        except json.JSONDecodeError:
            report = None
    parts = ["[Cortex Bridge — manual fallback payload]"]
    if report:
        parts.append(protocol.render_report_message(report))
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
    rt = _build_runtime(
        mission_id, mission["workspace"], WRITE_WITH_APPROVALS,
        "orchestra-executor", "orchestra-executor-fallback",
        mission["max_iterations"], mission["max_duration_seconds"],
    )
    if bindings:
        b = bindings[0]
        try:
            await rt.transport.attach(ConversationLock(
                url=b["conversation_url"],
                identity=b.get("browser_target_id") or b["conversation_url"],
                title=b.get("conversation_title"),
                selected_at=b.get("selected_at") or 0.0,
            ))
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"cannot re-attach conversation: {exc}")
    store.resume(mission_id, "WAITING_FOR_CHATGPT")
    rt.task = asyncio.create_task(_resume_mission_task(rt))
    return {"state": "WAITING_FOR_CHATGPT"}


@router.post("/missions/{mission_id}/cancel")
async def cancel_mission(mission_id: str) -> dict:
    store = get_store()
    _mission_or_404(store, mission_id)
    rt = _runtimes.get(mission_id)
    if rt is not None:
        _stop_runtime(rt)
    else:
        try:
            store.transition(mission_id, "CANCELLED", pause_reason="USER_CANCEL")
        except StoreError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
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
