"""First-launch onboarding: prerequisite checks and completion marker.

GET  /api/onboarding          → checks + completion state
POST /api/onboarding/dismiss  → mark onboarding as done (persisted)

Everything is loopback-only; the checks reuse the same drivers as the rest
of the console so the panel always reflects reality.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from local_executor import runtime_status
from transport.browser import create_browser_driver

import missions as missions_api
import settings as settings_api

router = APIRouter(prefix="/api")

DATA_DIR = Path(__file__).resolve().parent / "data"
MARKER_FILE = DATA_DIR / "onboarding-done.json"
browser_driver_factory = create_browser_driver


def onboarding_completed() -> bool:
    try:
        return bool(json.loads(MARKER_FILE.read_text(encoding="utf-8")).get("completed"))
    except (OSError, json.JSONDecodeError):
        return False


def _set_completed(completed: bool) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = MARKER_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"completed": completed}), encoding="utf-8")
    tmp.replace(MARKER_FILE)


def _check(id_: str, label: str, ok: bool, detail: str, hint: str) -> dict[str, Any]:
    return {
        "id": id_,
        "label": label,
        "state": "ok" if ok else "missing",
        "detail": detail,
        "hint": "" if ok else hint,
    }


async def run_checks() -> list[dict[str, Any]]:
    settings = settings_api.load_settings()
    checks: list[dict[str, Any]] = []

    # 1. Ollama reachable
    rt = runtime_status()
    ollama_up = bool(rt.get("ollama_up"))
    checks.append(_check(
        "ollama", "Ollama fonctionne",
        ollama_up,
        "Service détecté sur 127.0.0.1:11434" if ollama_up else "Aucun service Ollama détecté",
        "Lance l'application Ollama (tes modèles sur le disque externe restent configurés).",
    ))

    # 2. Executor model installed (Ollama stores "name:latest" — match both)
    models = {m.get("name") for m in settings_api._ollama_models()}
    primary = str(settings.get("primary_executor") or "")
    model_ok = ollama_up and (primary in models or f"{primary}:latest" in models)
    checks.append(_check(
        "executor-model", "Modèle exécuteur installé",
        model_ok,
        f"{primary} est disponible" if model_ok else f"{primary} introuvable ({len(models)} modèle(s) installé(s))",
        f"Installe-le : ollama pull {primary} — ou choisis un autre modèle dans Paramètres › Modèles.",
    ))

    # 3. Configured browser driver
    try:
        health = await browser_driver_factory(
            session="cortex-bridge-ui",
            settings=settings,
        ).health()
    except Exception:
        health = {
            "connected": False,
            "tabs": 0,
            "driver": settings["browser_transport"],
        }
    bridge_ok = bool(health.get("connected"))
    driver_name = str(health.get("driver") or settings["browser_transport"])
    checks.append(_check(
        "browser-driver", f"Transport navigateur {driver_name}",
        bridge_ok,
        f"{driver_name} connecté · {health.get('tabs', 0)} onglet(s)" if bridge_ok else f"{driver_name} indisponible",
        "Ouvre le profil navigateur dédié puis connecte-toi manuellement à ChatGPT.",
    ))

    # 4. ChatGPT tab open
    tabs = int(health.get("tabs") or 0)
    checks.append(_check(
        "chatgpt-tab", "Un onglet ChatGPT est ouvert",
        bridge_ok and tabs > 0,
        f"{tabs} onglet(s) pilotable(s)" if bridge_ok and tabs > 0 else "Aucun onglet pilotable",
        "Ouvre chatgpt.com dans Chrome et connecte-toi à ton compte.",
    ))

    # 5. Default workspace exists
    workspace = Path(str(settings.get("default_workspace") or "")).expanduser()
    ws_ok = workspace.is_dir()
    checks.append(_check(
        "workspace", "Workspace par défaut valide",
        ws_ok,
        str(workspace) if ws_ok else f"{workspace} n'existe pas",
        "Crée ce dossier ou choisis-en un autre dans Paramètres › Général.",
    ))

    return checks


@router.get("/onboarding")
async def get_onboarding() -> dict[str, Any]:
    checks = await run_checks()
    return {
        "completed": onboarding_completed(),
        "ready": all(c["state"] == "ok" for c in checks),
        "checks": checks,
    }


@router.post("/onboarding/dismiss")
async def dismiss_onboarding() -> dict[str, Any]:
    _set_completed(True)
    return {"completed": True}


@router.post("/onboarding/browser/open")
async def open_browser_login() -> dict[str, Any]:
    settings = settings_api.load_settings()
    driver = browser_driver_factory(
        session="cortex-bridge-ui",
        settings=settings,
    )
    try:
        return await driver.open_login()
    except Exception as exc:
        return {
            "connected": False,
            "tabs": 0,
            "driver": getattr(driver, "driver_name", settings["browser_transport"]),
            "error": str(exc),
        }
