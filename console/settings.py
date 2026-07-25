"""Settings, model discovery and pipeline observability for the localhost UI."""

from __future__ import annotations

import json
import os
import re
import hashlib
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import chat as chat_api
import missions as missions_api
from local_executor import OLLAMA_ENDPOINT, runtime_status
from transport.chatgpt_web.adapter import WebBridgeDriver

router = APIRouter(prefix="/api")
DATA_DIR = Path(__file__).resolve().parent / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"
DB_PATH = DATA_DIR / "cortex.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_SETTINGS: dict[str, Any] = {
    "language": "fr",
    "theme": "dark",
    "planner_model": "ChatGPT — modèle visible actuel",
    "primary_executor": "orchestra-executor",
    "fallback_executor": "orchestra-executor-fallback",
    "approval_policy": "workspace-write-with-approvals",
    "access_profile": "workspace",
    "default_workspace": str(Path.home() / "Documents" / "kimi" / "workspace" / "e2e-sandbox"),
    "max_iterations": 25,
    "max_duration_minutes": 60,
    "ollama_context": 8192,
    "auto_continue": True,
    "browser_research": False,
    "network_access": False,
    "never_delete_files": True,
    "persist_conversation_history": False,
    "response_stability_seconds": 2.0,
    "chat_timeout_seconds": 300,
}


class SettingsIn(BaseModel):
    language: str = "fr"
    theme: str = "dark"
    planner_model: str = "ChatGPT — modèle visible actuel"
    primary_executor: str = "orchestra-executor"
    fallback_executor: str = "orchestra-executor-fallback"
    approval_policy: str = "workspace-write-with-approvals"
    access_profile: str = "workspace"
    default_workspace: str
    max_iterations: int = Field(default=25, ge=1, le=100)
    max_duration_minutes: int = Field(default=60, ge=1, le=240)
    ollama_context: int = Field(default=8192, ge=2048, le=16384)
    auto_continue: bool = True
    browser_research: bool = False
    network_access: bool = False
    never_delete_files: bool = True
    persist_conversation_history: bool = False
    response_stability_seconds: float = Field(default=2.0, ge=1.0, le=10.0)
    chat_timeout_seconds: int = Field(default=300, ge=30, le=900)


class ChatGPTModelSelectIn(BaseModel):
    conversation_url: str
    label: str


def load_settings() -> dict[str, Any]:
    try:
        raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    result = {**DEFAULT_SETTINGS, **raw}
    # This is an invariant, not a preference.
    result["never_delete_files"] = True
    return result


def save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    clean = {**settings, "never_delete_files": True}
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SETTINGS_FILE)
    return clean


def _ollama_json(path: str, timeout: float = 3.0) -> dict[str, Any]:
    req = Request(f"{OLLAMA_ENDPOINT}{path}", headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _ollama_models() -> list[dict[str, Any]]:
    try:
        tags = _ollama_json("/api/tags").get("models", [])
    except (OSError, URLError, json.JSONDecodeError):
        return []
    try:
        loaded_rows = _ollama_json("/api/ps").get("models", [])
    except (OSError, URLError, json.JSONDecodeError):
        loaded_rows = []
    loaded = {row.get("name") or row.get("model") for row in loaded_rows}
    models = []
    for row in tags:
        name = row.get("name") or row.get("model")
        if not name:
            continue
        models.append({
            "name": name,
            "size": int(row.get("size") or 0),
            "modified_at": row.get("modified_at"),
            "digest": row.get("digest"),
            "loaded": name in loaded,
        })
    return models


@router.get("/settings")
async def get_settings() -> dict[str, Any]:
    return load_settings()


@router.put("/settings")
async def update_settings(body: SettingsIn) -> dict[str, Any]:
    if body.language not in {"fr", "en"}:
        raise HTTPException(status_code=422, detail="unsupported language")
    if body.theme not in {"dark", "light", "system"}:
        raise HTTPException(status_code=422, detail="unsupported theme")
    if body.approval_policy not in {
        "read-only-automatic",
        "workspace-write-with-approvals",
        "workspace-write-automatic",
    }:
        raise HTTPException(status_code=422, detail="unsupported approval policy")
    if body.access_profile not in {"observe", "workspace", "extended", "browser-research", "lab"}:
        raise HTTPException(status_code=422, detail="unsupported access profile")
    if body.access_profile == "lab" and os.environ.get("CORTEX_ALLOW_LAB_MODE") != "1":
        raise HTTPException(status_code=403, detail="Lab mode requires CORTEX_ALLOW_LAB_MODE=1")
    workspace = Path(body.default_workspace).expanduser()
    # A missing future workspace may be configured, but its parent must be absolute.
    if not workspace.is_absolute():
        raise HTTPException(status_code=422, detail="default workspace must be absolute")
    return save_settings(body.model_dump())


@router.get("/models/ollama")
async def list_ollama_models() -> dict[str, Any]:
    return {"models": _ollama_models(), "endpoint": OLLAMA_ENDPOINT}


@router.get("/models/chatgpt")
async def list_chatgpt_models() -> dict[str, Any]:
    driver = WebBridgeDriver(session="cortex-bridge-ui")
    try:
        result = await driver.list_models()
    except Exception as exc:
        # The UI remains useful even when the current ChatGPT build does not
        # expose a supported selector. Do not pretend other models are known.
        settings = load_settings()
        return {
            "models": [{"label": settings["planner_model"], "selected": True, "available": True}],
            "experimental": True,
            "error": str(exc),
        }
    current = str(result.get("current") or load_settings()["planner_model"])
    labels = [str(label) for label in result.get("models", []) if str(label).strip()]
    if current and current not in labels:
        labels.insert(0, current)
    return {
        "models": [
            {"label": label, "selected": label == current, "available": True}
            for label in labels
        ],
        "experimental": True,
        "error": result.get("error"),
    }


@router.put("/models/chatgpt")
async def select_chatgpt_model(body: ChatGPTModelSelectIn) -> dict[str, Any]:
    if not missions_api.optin_accepted():
        raise HTTPException(status_code=403, detail="Experimental ChatGPT Web Transport is not enabled")
    if not body.label.strip():
        raise HTTPException(status_code=422, detail="model label is empty")
    driver = WebBridgeDriver(session="cortex-bridge-ui")
    try:
        await driver.navigate(body.conversation_url)
        selected = await driver.select_model(body.label.strip())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"cannot confirm ChatGPT model selection: {exc}")
    settings = load_settings()
    settings["planner_model"] = selected
    save_settings(settings)
    return {"selected": selected, "confirmed": True}


def _active_missions() -> list[dict[str, Any]]:
    try:
        rows = missions_api.get_store().rows("missions", order_by="updated_at DESC")
    except Exception:
        return []
    return [
        row for row in rows
        if row.get("state") not in {"COMPLETED", "BLOCKED", "FAILED", "CANCELLED"}
    ]


def _latest_mission_events(mission_id: str | None) -> list[dict[str, Any]]:
    if not mission_id:
        return []
    store = missions_api.get_store()
    events: list[dict[str, Any]] = []
    mapping = [
        ("transport_events", "Transport"),
        ("orchestrator_decisions", "Décision ChatGPT"),
        ("policy_decisions", "Politique"),
        ("tool_executions", "Exécution locale"),
        ("validation_results", "Validation"),
    ]
    for table, label in mapping:
        try:
            rows = store.rows(table, mission_id, order_by="rowid DESC")[:4]
        except Exception:
            rows = []
        for row in rows:
            timestamp = row.get("created_at") or row.get("started_at") or row.get("updated_at") or time.time()
            if isinstance(timestamp, (int, float)):
                ts = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
            else:
                ts = _now()
            detail = row.get("event_type") or row.get("tool") or row.get("reason") or row.get("status") or ""
            events.append({
                "id": f"{table}-{row.get('rowid', uuid.uuid4().hex[:6])}",
                "ts": ts,
                "label": label,
                "detail": str(detail),
                "duration_ms": row.get("duration_ms"),
                "state": "healthy" if row.get("passed", 1) not in {0, False} else "failed",
            })
    return sorted(events, key=lambda row: row["ts"], reverse=True)[:10]


@router.get("/pipeline/status")
async def pipeline_status() -> dict[str, Any]:
    rt = runtime_status()
    active = _active_missions()
    mission = active[0] if active else None
    try:
        bridge_health = await WebBridgeDriver(session="cortex-bridge-ui").health()
    except Exception as exc:
        bridge_health = {"connected": False, "tabs": 0, "error": str(exc)}
    try:
        db_ok = DB_PATH.exists()
        if db_ok:
            with sqlite3.connect(DB_PATH) as connection:
                connection.execute("SELECT 1").fetchone()
    except sqlite3.Error:
        db_ok = False
    chat_runs = list(chat_api._runs.values())
    current_chat = chat_runs[-1] if chat_runs else None
    transport_ms = current_chat.latency.get("delivery_ms") if current_chat else None
    total_ms = current_chat.latency.get("total_ms") if current_chat else None
    if mission:
        overall = "running" if mission.get("state") not in {"PAUSED", "PAUSED_RECOVERY_REQUIRED"} else "waiting"
    elif not bridge_health.get("connected") or not rt.get("ollama_up"):
        overall = "degraded"
    else:
        overall = "healthy"
    components = [
        {
            "id": "transport",
            "label": "Transport ChatGPT",
            "state": "connected" if bridge_health.get("connected") else "disconnected",
            "detail": f"WebBridge · {bridge_health.get('tabs', 0)} onglet(s)",
            "latency_ms": transport_ms,
            "heartbeat_at": _now(),
        },
        {
            "id": "validator",
            "label": "Validateur Cortex",
            "state": "healthy",
            "detail": "cortex.v1 · outils structurés",
            "latency_ms": None,
            "heartbeat_at": _now(),
        },
        {
            "id": "task",
            "label": "Tâche courante",
            "state": "running" if mission else "idle",
            "detail": mission.get("state") if mission else "Aucune mission active",
            "latency_ms": None,
            "heartbeat_at": _now(),
        },
        {
            "id": "chrome",
            "label": "Chrome Research",
            "state": "idle" if not load_settings().get("browser_research") else "connected",
            "detail": "Profil séparé" if load_settings().get("browser_research") else "Désactivé",
            "latency_ms": None,
            "heartbeat_at": _now(),
        },
        {
            "id": "screenshots",
            "label": "Captures",
            "state": "idle",
            "detail": "Preuves visuelles à la demande",
            "latency_ms": None,
            "heartbeat_at": _now(),
        },
        {
            "id": "filesystem",
            "label": "Fichiers",
            "state": "healthy",
            "detail": f"Profil {load_settings().get('access_profile', 'workspace')}",
            "latency_ms": None,
            "heartbeat_at": _now(),
        },
        {
            "id": "ollama",
            "label": "Ollama",
            "state": "healthy" if rt.get("ollama_up") else "failed",
            "detail": f"{rt.get('primary', {}).get('name')} · {rt.get('primary', {}).get('state')}",
            "latency_ms": None,
            "heartbeat_at": _now(),
        },
        {
            "id": "approvals",
            "label": "Approbations",
            "state": "waiting" if mission and mission.get("state") == "WAITING_FOR_APPROVAL" else "idle",
            "detail": "Action en attente" if mission and mission.get("state") == "WAITING_FOR_APPROVAL" else "Aucune en attente",
            "latency_ms": None,
            "heartbeat_at": _now(),
        },
        {
            "id": "queue",
            "label": "File d'attente",
            "state": "idle" if len(active) <= 1 else "waiting",
            "detail": f"{max(0, len(active) - 1)} mission(s) en attente",
            "latency_ms": None,
            "heartbeat_at": _now(),
        },
        {
            "id": "database",
            "label": "Persistance",
            "state": "healthy" if db_ok else "failed",
            "detail": "SQLite synchronisé" if db_ok else "Base indisponible",
            "latency_ms": None,
            "heartbeat_at": _now(),
        },
    ]
    events = _latest_mission_events(mission.get("id") if mission else None)
    if current_chat:
        events.insert(0, {
            "id": f"chat-{current_chat.id}",
            "ts": current_chat.completed_at or current_chat.first_response_at or current_chat.created_at,
            "label": "Conversation ChatGPT",
            "detail": current_chat.state,
            "duration_ms": current_chat.latency.get("total_ms"),
            "state": "healthy" if current_chat.state == "COMPLETED" else "running",
        })
    return {
        "overall": overall,
        "updated_at": _now(),
        "components": components,
        "active_mission_id": mission.get("id") if mission else None,
        "active_mission_state": mission.get("state") if mission else None,
        "queue_pending": max(0, len(active) - 1),
        "events": events[:10],
        "latency": {
            "transport_ms": transport_ms,
            "local_model_ms": None,
            "total_iteration_ms": total_ms,
        },
    }


# ------------------------------------------------------------- diagnostics


def _anonymize(value: Any) -> Any:
    """Scrub personal data from a structure before it leaves the machine.

    - home directory paths become ~/…
    - ChatGPT conversation ids become a short non-reversible token
    - conversation titles, message contents and cookies are never included
      by construction (the export simply never reads them)
    """
    home = str(Path.home())
    if isinstance(value, str):
        scrubbed = value.replace(home, "~")
        # /c/<conversation-id> → /c/conv-xxxxxxxx (first 8 chars of sha1)
        def _mask(match: "re.Match[str]") -> str:
            digest = hashlib.sha1(match.group(1).encode("utf-8")).hexdigest()[:8]
            return f"/c/conv-{digest}"
        return re.sub(r"/c/([0-9a-fA-F-]{8,})", _mask, scrubbed)
    if isinstance(value, dict):
        return {k: _anonymize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_anonymize(item) for item in value]
    return value


@router.get("/diagnostics/export")
async def diagnostics_export() -> dict[str, Any]:
    """Anonymized diagnostic bundle, safe to paste into a GitHub issue."""
    import onboarding as onboarding_api

    rt = runtime_status()
    try:
        bridge_health = await WebBridgeDriver(session="cortex-bridge-ui").health()
    except Exception as exc:
        bridge_health = {"connected": False, "error": type(exc).__name__}
    settings = load_settings()
    sensitive_keys = {"default_workspace"}
    safe_settings = {k: v for k, v in settings.items() if k not in sensitive_keys}
    checks = await onboarding_api.run_checks()
    payload = {
        "generated_at": _now(),
        "cortex_bridge": {
            "component": "console",
            "api": "fastapi",
            "ui": "next.js static export",
        },
        "runtime": {
            "ollama_up": bool(rt.get("ollama_up")),
            "ollama_primary": (rt.get("primary") or {}).get("name"),
            "ollama_primary_state": (rt.get("primary") or {}).get("state"),
        },
        "webbridge": {
            "connected": bool(bridge_health.get("connected")),
            "tabs": bridge_health.get("tabs", 0),
            "extension_version": bridge_health.get("extension_version"),
        },
        "onboarding_checks": [
            {"id": c["id"], "state": c["state"]} for c in checks
        ],
        "settings": safe_settings,
        "anonymization": "home paths → ~, conversation ids → hashed tokens, no message content",
    }
    return _anonymize(payload)
