"""Cortex Bridge console — local web cockpit.

FastAPI backend serving the single-page UI and the task API.
Run:  python server.py   →  http://127.0.0.1:8420
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from local_executor import DEVELOPMENT_FIXTURE_ENV, runtime_status, run_task
from missions import router as missions_router
from chat import router as chat_router
from settings import router as settings_router
from onboarding import router as onboarding_router
from cortex_paths import build_paths, migrate_legacy_state
from version import current_version

BASE_DIR = Path(__file__).resolve().parent
RUNTIME_PATHS = build_paths()
DATA_DIR = RUNTIME_PATHS.home
STORE_FILE = RUNTIME_PATHS.iterations
REPO_ROOT = BASE_DIR.parent
FRONTEND_OUT = REPO_ROOT / "frontend" / "out"
FRONTEND_FALLBACK = REPO_ROOT / "frontend" / "fallback"

app = FastAPI(title="Cortex Bridge Console")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3420", "http://localhost:3420"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Last-Event-ID"],
)
app.include_router(missions_router)
app.include_router(chat_router)
app.include_router(settings_router)
app.include_router(onboarding_router)

if (FRONTEND_OUT / "_next").is_dir():
    app.mount("/_next", StaticFiles(directory=FRONTEND_OUT / "_next"), name="next-assets")

# ------------------------------------------------------------- persistence

_iterations: list[dict] = []


def _migrate_legacy_runtime() -> None:
    migrate_legacy_state(BASE_DIR / "data", RUNTIME_PATHS)


def _load_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if STORE_FILE.is_file():
        try:
            _iterations.extend(json.loads(STORE_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass


def _save_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STORE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(_iterations, indent=2), encoding="utf-8")
    tmp.replace(STORE_FILE)


def _find(task_id: str) -> dict | None:
    return next((it for it in _iterations if it["id"] == task_id), None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_migrate_legacy_runtime()
_load_store()

# ----------------------------------------------------------------- schemas


class TaskIn(BaseModel):
    goal: str
    constraints: list[str] = []
    workspace: str = "~/"
    allow_processes: bool = False
    development_fixture: bool = False


class ReplyIn(BaseModel):
    text: str


# ---------------------------------------------------------------- execution


async def _emit(task: dict, text: str, kind: str) -> None:
    task["logs"].append({"ts": _now(), "text": text, "kind": kind})


async def _run(task: dict) -> None:
    try:
        report = await run_task(task, lambda t, k: _emit(task, t, k))
    except Exception as exc:  # never leave a task stuck in running
        report = {
            "status": "failed",
            "summary": f"Executor crashed: {exc}",
            "commands_run": [],
            "files_changed": [],
            "blockers": [str(exc)],
            "suggested_next_step": "Check the console server log.",
            "executor_kind": "unavailable",
            "executor_model_used": None,
            "runtime_mode": "live",
            "release_eligible": False,
        }
        await _emit(task, f"executor crashed: {exc}", "error")
    task["report"] = report
    task["status"] = report["status"]
    task["executor_kind"] = report["executor_kind"]
    task["executor_model_used"] = report["executor_model_used"]
    task["runtime_mode"] = report["runtime_mode"]
    task["release_eligible"] = bool(report.get("release_eligible", False))
    task["finished_at"] = _now()
    _save_store()


# ----------------------------------------------------------------- routes


@app.get("/")
async def index() -> FileResponse:
    modern = FRONTEND_OUT / "index.html"
    fallback = FRONTEND_FALLBACK / "index.html"
    if modern.is_file():
        return FileResponse(modern)
    if fallback.is_file():
        return FileResponse(fallback)
    raise HTTPException(
        status_code=503,
        detail="No release frontend is installed; legacy simulated UI is disabled.",
    )


@app.get("/api/status")
async def status() -> dict:
    return {**runtime_status(), "version": current_version()}


@app.post("/api/tasks", status_code=201)
async def create_task(body: TaskIn) -> dict:
    if not body.goal.strip():
        raise HTTPException(status_code=422, detail="goal must not be empty")
    fixtures_allowed = os.environ.get(DEVELOPMENT_FIXTURE_ENV) == "1"
    if body.development_fixture and not fixtures_allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "DEVELOPMENT_FIXTURES_DISABLED",
                "message": (
                    "development_fixture requires "
                    f"{DEVELOPMENT_FIXTURE_ENV}=1"
                ),
            },
        )
    requested_runtime_mode = (
        "development_fixture" if body.development_fixture else "live"
    )
    task = {
        "id": uuid.uuid4().hex[:12],
        "goal": body.goal.strip(),
        "constraints": [c.strip() for c in body.constraints if c.strip()],
        "workspace": body.workspace.strip() or "~/",
        "status": "running",
        "executor_kind": "unavailable",
        "executor_model_used": None,
        "runtime_mode": requested_runtime_mode,
        "release_eligible": False,
        "allow_processes": body.allow_processes,
        "development_fixture": body.development_fixture,
        "started_at": _now(),
        "finished_at": None,
        "logs": [],
        "report": None,
        "orchestrator_replies": [],
    }
    _iterations.insert(0, task)
    _save_store()
    asyncio.create_task(_run(task))
    return {
        "id": task["id"],
        "status": "running",
        "executor_kind": "unavailable",
        "executor_model_used": None,
        "runtime_mode": requested_runtime_mode,
        "release_eligible": False,
    }


@app.get("/api/tasks")
async def list_tasks() -> list[dict]:
    return [
        {
            "id": it["id"],
            "goal": it["goal"],
            "status": it["status"],
            "executor_kind": it.get("executor_kind", "unavailable"),
            "executor_model_used": it.get("executor_model_used"),
            "runtime_mode": it.get("runtime_mode", "live"),
            "release_eligible": bool(it.get("release_eligible", False)),
            "started_at": it["started_at"],
        }
        for it in _iterations
    ]


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    task = _find(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@app.post("/api/tasks/{task_id}/orchestrator-reply", status_code=201)
async def orchestrator_reply(task_id: str, body: ReplyIn) -> dict:
    task = _find(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")
    reply = {"ts": _now(), "text": body.text.strip()}
    task["orchestrator_replies"].append(reply)
    _save_store()
    return {"ok": True, "count": len(task["orchestrator_replies"])}


@app.get("/api/tasks/{task_id}/stream")
async def stream_task(task_id: str) -> StreamingResponse:
    if _find(task_id) is None:
        raise HTTPException(status_code=404, detail="task not found")

    async def events():
        sent = 0
        while True:
            task = _find(task_id)
            logs = task["logs"]
            while sent < len(logs):
                yield f"data: {json.dumps(logs[sent])}\n\n"
                sent += 1
            if task["status"] != "running":
                payload = json.dumps({"status": task["status"]})
                yield f"event: done\ndata: {payload}\n\n"
                return
            await asyncio.sleep(0.3)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/{full_path:path}", include_in_schema=False)
async def frontend_fallback(full_path: str) -> FileResponse:
    """Serve files from the optional Next.js static export without shadowing API routes."""
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")
    if FRONTEND_OUT.is_dir():
        candidate = (FRONTEND_OUT / full_path).resolve()
        try:
            candidate.relative_to(FRONTEND_OUT.resolve())
        except ValueError:
            raise HTTPException(status_code=404, detail="asset not found")
        if candidate.is_dir():
            candidate = candidate / "index.html"
        if candidate.is_file():
            return FileResponse(candidate)
        nested = candidate.with_suffix(".html")
        if nested.is_file():
            return FileResponse(nested)
    raise HTTPException(status_code=404, detail="asset not found")


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", 8420)), log_level="info")


if __name__ == "__main__":
    main()
