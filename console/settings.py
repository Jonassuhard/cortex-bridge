"""Settings, model discovery and pipeline observability for the localhost UI."""

from __future__ import annotations

import json
import os
import re
import hashlib
import sqlite3
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import chat as chat_api
import missions as missions_api
from executor.tools import ProcessCapabilities
from local_executor import OLLAMA_ENDPOINT, runtime_status
from transport.browser import create_browser_driver, load_browser_settings
from cortex_paths import build_paths

router = APIRouter(prefix="/api")
RUNTIME_PATHS = build_paths()
DATA_DIR = RUNTIME_PATHS.home
SETTINGS_FILE = RUNTIME_PATHS.settings
DB_PATH = RUNTIME_PATHS.database
TASK_STORE_FILE = RUNTIME_PATHS.iterations
browser_driver_factory = create_browser_driver


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
    "process_capabilities": asdict(ProcessCapabilities()),
    "persist_conversation_history": False,
    "response_stability_seconds": 2.0,
    "chat_timeout_seconds": 300,
    "browser_transport": "playwright",
    "browser_profile_root": str(RUNTIME_PATHS.browser_profiles),
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
    browser_transport: Literal["playwright", "webbridge"] = "playwright"
    browser_profile_root: str = str(RUNTIME_PATHS.browser_profiles)


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
    load_browser_settings(result)
    return result


def save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    clean = {**DEFAULT_SETTINGS, **settings, "never_delete_files": True}
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
    try:
        load_browser_settings(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return save_settings(body.model_dump())


@router.get("/models/ollama")
async def list_ollama_models() -> dict[str, Any]:
    return {"models": _ollama_models(), "endpoint": OLLAMA_ENDPOINT}


@router.get("/models/chatgpt")
async def list_chatgpt_models() -> dict[str, Any]:
    driver = browser_driver_factory(
        session="cortex-bridge-ui",
        settings=load_settings(),
    )
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
    driver = browser_driver_factory(
        session="cortex-bridge-ui",
        settings=load_settings(),
    )
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


def _iso_timestamp(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    return None


def _latest_local_task_runtime_truth() -> dict[str, Any] | None:
    """Read executor evidence persisted by /api/tasks, never daemon guesses."""
    try:
        tasks = json.loads(TASK_STORE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(tasks, list):
        return None
    task = next((row for row in tasks if isinstance(row, dict)), None)
    if task is None:
        return None
    report = task.get("report") if isinstance(task.get("report"), dict) else {}
    status = str(task.get("status") or "unknown")
    active = status == "running"
    return {
        "task_id": task.get("id"),
        "executor_kind": report.get(
            "executor_kind", task.get("executor_kind", "unavailable")
        ),
        "executor_model_used": report.get(
            "executor_model_used", task.get("executor_model_used")
        ),
        "runtime_mode": report.get(
            "runtime_mode", task.get("runtime_mode", "live")
        ),
        "release_eligible": bool(
            report.get("release_eligible", task.get("release_eligible", False))
        ),
        "state": status,
        "active": active,
        "observed_at": _iso_timestamp(
            task.get("finished_at") or task.get("started_at")
        ),
    }


def _mission_runtime_truth(mission: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": mission.get("id"),
        "executor_kind": mission.get("executor_kind", "unavailable"),
        "executor_model_used": mission.get("executor_model_used"),
        "runtime_mode": mission.get("runtime_mode", "live"),
        "release_eligible": bool(mission.get("release_eligible", False)),
        "state": mission.get("state", "unknown"),
        "active": mission.get("state") not in {"COMPLETED", "BLOCKED", "FAILED", "CANCELLED"},
        "observed_at": _iso_timestamp(
            mission.get("runtime_observed_at") or mission.get("updated_at")
        ),
    }


def _idle_runtime_truth() -> dict[str, Any]:
    return {
        "task_id": None,
        "executor_kind": "unavailable",
        "executor_model_used": None,
        "runtime_mode": "live",
        "release_eligible": False,
        "state": "idle",
        "active": False,
        "observed_at": None,
    }


_TERMINAL_MISSION_STATES = {"COMPLETED", "BLOCKED", "FAILED", "CANCELLED"}
_OPAQUE_CONVERSATION_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_CANONICAL_CHATGPT_ORIGINS = {"chatgpt.com", "www.chatgpt.com"}


def _canonical_conversation_identity(value: object) -> str | None:
    """Return the transport's exact opaque identity, never a title or prefix."""
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith("provisional:"):
        provisional_id = raw.removeprefix("provisional:")
        try:
            return raw if str(uuid.UUID(provisional_id)) == provisional_id else None
        except (ValueError, AttributeError):
            return None
    if _OPAQUE_CONVERSATION_ID.fullmatch(raw):
        return raw
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.netloc not in _CANONICAL_CHATGPT_ORIGINS
        or parsed.query
        or parsed.fragment
    ):
        return None
    match = re.fullmatch(r"/c/([A-Za-z0-9_-]+)", parsed.path)
    return match.group(1) if match else None


def _binding_conversation_identity(binding: dict[str, Any]) -> str | None:
    """Use the persisted target first; URL is only the durable fallback."""
    target = _canonical_conversation_identity(binding.get("conversation_target"))
    if target is not None:
        return target
    return _canonical_conversation_identity(binding.get("conversation_url"))


def _mission_matches_conversation(mission_id: str, identity: str) -> bool:
    try:
        bindings = missions_api.get_store().rows(
            "conversation_bindings", mission_id, order_by="rowid DESC"
        )
    except Exception:
        return False
    return bool(bindings) and _binding_conversation_identity(bindings[0]) == identity


def _scoped_mission(
    identity: str,
    requested_mission_id: str | None,
) -> tuple[dict[str, Any] | None, int]:
    """Resolve one mission only through its latest persisted conversation binding."""
    store = missions_api.get_store()
    if requested_mission_id is not None:
        try:
            mission_id = str(uuid.UUID(requested_mission_id))
            mission = store.get_mission(mission_id)
        except Exception:
            raise HTTPException(
                status_code=404,
                detail="mission is not bound to the selected conversation",
            ) from None
        if not _mission_matches_conversation(mission_id, identity):
            raise HTTPException(
                status_code=404,
                detail="mission is not bound to the selected conversation",
            )
        active_count = int(mission.get("state") not in _TERMINAL_MISSION_STATES)
        return mission, active_count

    try:
        active = [
            mission for mission in store.rows("missions", order_by="updated_at DESC, rowid DESC")
            if mission.get("state") not in _TERMINAL_MISSION_STATES
        ]
    except Exception:
        return None, 0
    matches = [
        mission for mission in active
        if _mission_matches_conversation(str(mission.get("id") or ""), identity)
    ]
    return (matches[0] if matches else None), len(matches)


def _mission_conversation_identity(mission: dict[str, Any] | None) -> str | None:
    if mission is None:
        return None
    try:
        bindings = missions_api.get_store().rows(
            "conversation_bindings", str(mission.get("id") or ""), order_by="rowid DESC"
        )
    except Exception:
        return None
    return _binding_conversation_identity(bindings[0]) if bindings else None


def _chat_run_conversation_identity(run: Any) -> str | None:
    """Prefer proven canonical identity; incomplete runs may only use their key."""
    for attribute in ("canonical_url", "conversation_key", "conversation_url"):
        value = getattr(run, attribute, None)
        if isinstance(value, str) and value.strip():
            return _canonical_conversation_identity(value)
    return None


def _latest_chat_run_for_conversation(identity: str | None) -> Any | None:
    if identity is None:
        return None
    for run in reversed(list(chat_api._runs.values())):
        if _chat_run_conversation_identity(run) == identity:
            return run
    return None


@router.get("/pipeline/status")
async def pipeline_status(
    conversation_identity: str | None = None,
    mission_id: str | None = None,
) -> dict[str, Any]:
    scoped = conversation_identity is not None or mission_id is not None
    normalized_identity: str | None = None
    scoped_active_count = 0
    if scoped:
        normalized_identity = _canonical_conversation_identity(conversation_identity)
        if normalized_identity is None:
            raise HTTPException(status_code=404, detail="conversation was not found")
        mission, scoped_active_count = _scoped_mission(normalized_identity, mission_id)
        scope = {
            "mode": "conversation",
            "conversation_identity": normalized_identity,
            "mission_id": mission.get("id") if mission else None,
        }
    else:
        active = _active_missions()
        mission = active[0] if active else None
        scope = {
            "mode": "global_legacy",
            "conversation_identity": None,
            "mission_id": None,
        }

    rt = runtime_status()
    runtime_execution = (
        _mission_runtime_truth(mission)
        if mission
        else (_idle_runtime_truth() if scoped else _latest_local_task_runtime_truth() or _idle_runtime_truth())
    )
    try:
        bridge_health = await browser_driver_factory(
            session="cortex-bridge-ui",
            settings=load_settings(),
        ).health()
    except Exception as exc:
        bridge_health = {"connected": False, "tabs": 0, "error": str(exc)}
    try:
        db_ok = DB_PATH.exists()
        if db_ok:
            with sqlite3.connect(DB_PATH) as connection:
                connection.execute("SELECT 1").fetchone()
    except sqlite3.Error:
        db_ok = False
    if scoped:
        current_chat = _latest_chat_run_for_conversation(normalized_identity)
    else:
        chat_runs = list(chat_api._runs.values())
        current_chat = chat_runs[-1] if chat_runs else None
    transport_ms = current_chat.latency.get("delivery_ms") if current_chat else None
    total_ms = current_chat.latency.get("total_ms") if current_chat else None
    if mission and mission.get("state") not in _TERMINAL_MISSION_STATES:
        overall = "running" if mission.get("state") not in {"PAUSED", "PAUSED_RECOVERY_REQUIRED"} else "waiting"
    elif not bridge_health.get("connected") or not rt.get("ollama_up"):
        overall = "degraded"
    else:
        overall = "healthy"
    queue_pending = max(0, (scoped_active_count if scoped else len(active)) - 1)
    mission_is_active = bool(mission) and mission.get("state") not in _TERMINAL_MISSION_STATES
    components = [
        {
            "id": "transport",
            "label": "Transport ChatGPT",
            "state": "connected" if bridge_health.get("connected") else "disconnected",
            "detail": (
                f"{bridge_health.get('driver', load_settings()['browser_transport'])}"
                f" · {bridge_health.get('tabs', 0)} onglet(s)"
            ),
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
            "state": "running" if mission_is_active else "idle",
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
            "label": "Disponibilité Ollama",
            "state": "available" if rt.get("executor_available") else "unavailable",
            "detail": (
                f"daemon {rt.get('ollama_status')} · candidat "
                f"{rt.get('primary', {}).get('name')} "
                f"{rt.get('primary', {}).get('state')}"
            ),
            "latency_ms": None,
            "heartbeat_at": _now(),
        },
        {
            "id": "executor",
            "label": "Exécuteur réellement utilisé",
            "state": "running" if runtime_execution["active"] else (
                "healthy" if runtime_execution["state"] in {"done", "COMPLETED"}
                else "blocked" if runtime_execution["state"] == "blocked"
                else "failed" if runtime_execution["state"] in {
                    "failed", "FAILED", "BLOCKED", "CANCELLED"
                }
                else "idle"
            ),
            "detail": (
                "aucun appel exécuteur observé"
                if runtime_execution["executor_kind"] == "unavailable"
                else (
                    f"{runtime_execution['executor_kind']} · "
                    f"{runtime_execution['executor_model_used'] or 'sans modèle'} · "
                    f"{runtime_execution['state']}"
                )
            ),
            "latency_ms": None,
            "heartbeat_at": runtime_execution["observed_at"],
        },
        {
            "id": "approvals",
            "label": "Approbations",
            "state": "waiting" if mission_is_active and mission.get("state") == "WAITING_FOR_APPROVAL" else "idle",
            "detail": "Action en attente" if mission_is_active and mission.get("state") == "WAITING_FOR_APPROVAL" else "Aucune en attente",
            "latency_ms": None,
            "heartbeat_at": _now(),
        },
        {
            "id": "queue",
            "label": "File d'attente",
            "state": "idle" if queue_pending == 0 else "waiting",
            "detail": f"{queue_pending} mission(s) en attente",
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
        "scope": scope,
        "components": components,
        "active_mission_id": mission.get("id") if mission else None,
        "active_mission_state": mission.get("state") if mission else None,
        "runtime_execution": runtime_execution,
        "queue_pending": queue_pending,
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
        if scrubbed.startswith("/") and not scrubbed.startswith("//"):
            scrubbed = f"/<redacted>/{Path(scrubbed).name}"
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
        bridge_health = await browser_driver_factory(
            session="cortex-bridge-ui",
            settings=load_settings(),
        ).health()
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
        "browser_driver": {
            "name": bridge_health.get("driver", settings["browser_transport"]),
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
