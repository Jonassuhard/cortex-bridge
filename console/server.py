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
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from executor import STORAGE_UNAVAILABLE, detect_mode, runtime_status, run_task

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
STORE_FILE = DATA_DIR / "iterations.json"

app = FastAPI(title="Cortex Bridge Console")

# ------------------------------------------------------------- persistence

_iterations: list[dict] = []


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


_load_store()

# ----------------------------------------------------------------- schemas


class TaskIn(BaseModel):
    goal: str
    constraints: list[str] = []
    workspace: str = "~/"


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
            "mode": detect_mode(),
        }
        await _emit(task, f"executor crashed: {exc}", "error")
    task["report"] = report
    task["status"] = report["status"]
    task["finished_at"] = _now()
    _save_store()


# ----------------------------------------------------------------- routes


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/style.css")
async def style() -> FileResponse:
    return FileResponse(STATIC_DIR / "style.css")


@app.get("/app.js")
async def script() -> FileResponse:
    return FileResponse(STATIC_DIR / "app.js")


@app.get("/api/status")
async def status() -> dict:
    return runtime_status()


@app.post("/api/tasks", status_code=201)
async def create_task(body: TaskIn) -> dict:
    if not body.goal.strip():
        raise HTTPException(status_code=422, detail="goal must not be empty")
    if runtime_status()["storage_status"] == STORAGE_UNAVAILABLE:
        return JSONResponse(
            status_code=409,
            content={
                "error": STORAGE_UNAVAILABLE,
                "message": (
                    "Local model storage unavailable; the remote Kimi/OpenCodex "
                    "fallback remains available."
                ),
            },
        )
    task = {
        "id": uuid.uuid4().hex[:12],
        "goal": body.goal.strip(),
        "constraints": [c.strip() for c in body.constraints if c.strip()],
        "workspace": body.workspace.strip() or "~/",
        "status": "running",
        "mode": detect_mode(),
        "started_at": _now(),
        "finished_at": None,
        "logs": [],
        "report": None,
        "orchestrator_replies": [],
    }
    _iterations.insert(0, task)
    _save_store()
    asyncio.create_task(_run(task))
    return {"id": task["id"], "status": task["status"], "mode": task["mode"]}


@app.get("/api/tasks")
async def list_tasks() -> list[dict]:
    return [
        {
            "id": it["id"],
            "goal": it["goal"],
            "status": it["status"],
            "mode": it["mode"],
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


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", 8420)), log_level="info")
