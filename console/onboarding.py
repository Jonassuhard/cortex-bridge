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
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException

from local_executor import runtime_status
from transport.browser import create_browser_driver
from transport.chatgpt_web.adapter import DriverError, TabClosedError
from chrome_extension import chrome_extension_manager

import missions as missions_api
import settings as settings_api

router = APIRouter(prefix="/api")

DATA_DIR = Path(__file__).resolve().parent / "data"
MARKER_FILE = DATA_DIR / "onboarding-done.json"
browser_driver_factory = create_browser_driver


def _connection_result(
    *,
    code: str,
    state: str,
    title: str,
    message: str,
    recoverable: bool,
    driver: str = "chrome_extension",
    url: str | None = None,
    tab_id: int | None = None,
    window_id: int | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "state": state,
        "title": title,
        "message": message,
        "recoverable": recoverable,
        "driver": driver,
        "url": url,
        "tab_id": tab_id,
        "window_id": window_id,
    }


def connection_result_from_bridge_status(status: dict[str, Any]) -> dict[str, Any]:
    state = str(status.get("state") or "disconnected")
    if status.get("paired"):
        return _connection_result(
            code="EXTENSION_PAIRED",
            state="checking",
            title="Extension Chrome connectée",
            message="Cortex vérifie maintenant l’onglet ChatGPT.",
            recoverable=True,
        )
    if state == "extension_detected":
        return _connection_result(
            code="EXTENSION_UNPAIRED",
            state="checking",
            title="Jumelage Chrome en attente",
            message="L’extension est détectée. Relance la connexion depuis Cortex.",
            recoverable=True,
        )
    return _connection_result(
        code="EXTENSION_MISSING",
        state="disconnected",
        title="Extension Chrome introuvable",
        message="Installe ou active l’extension Cortex Bridge dans Chrome, puis réessaie.",
        recoverable=True,
    )


def connection_result_from_probe(
    probe: dict[str, Any],
    *,
    opened: dict[str, Any] | None = None,
    driver: str = "chrome_extension",
) -> dict[str, Any]:
    opened = opened or {}
    url = str(probe.get("url") or opened.get("url") or "") or None
    shared = {
        "driver": driver,
        "url": url,
        "tab_id": opened.get("tab_id"),
        "window_id": opened.get("window_id"),
    }
    blocker = str(probe.get("blocker") or "").lower()
    failures = {str(value).lower() for value in probe.get("failures") or []}
    if blocker == "login" or "login" in failures:
        return _connection_result(
            code="LOGIN_REQUIRED",
            state="manual_action",
            title="Connexion à ChatGPT requise",
            message=(
                "ChatGPT est ouvert dans Chrome, mais tu n’es pas connecté. "
                "Connecte-toi dans l’onglet ChatGPT, puis réessaie."
            ),
            recoverable=True,
            **shared,
        )
    if blocker == "captcha" or "captcha" in failures:
        return _connection_result(
            code="CAPTCHA",
            state="manual_action",
            title="Vérification requise",
            message=(
                "ChatGPT demande une vérification humaine. Ouvre l’onglet, "
                "termine la vérification, puis réessaie."
            ),
            recoverable=True,
            **shared,
        )
    if blocker == "rate_limit" or "rate_limit" in failures:
        return _connection_result(
            code="RATE_LIMIT",
            state="manual_action",
            title="ChatGPT limite temporairement les requêtes",
            message="Attends la fin de la limitation dans ChatGPT, puis réessaie.",
            recoverable=True,
            **shared,
        )
    if probe.get("ok") is True and probe.get("composer_present") is True:
        return _connection_result(
            code="CONNECTED",
            state="connected",
            title="ChatGPT connecté",
            message="Cortex est lié à cet onglet Chrome.",
            recoverable=False,
            **shared,
        )
    return _connection_result(
        code="CHATGPT_LOADING",
        state="checking",
        title="ChatGPT est encore en chargement",
        message="Garde l’onglet ChatGPT ouvert et réessaie dans un instant.",
        recoverable=True,
        **shared,
    )


async def open_connection_with_driver(driver) -> dict[str, Any]:
    try:
        opened = await driver.open_login()
    except TabClosedError:
        return _connection_result(
            code="TAB_CLOSED",
            state="disconnected",
            title="Onglet ChatGPT fermé",
            message="Rouvre et connecte ChatGPT pour continuer.",
            recoverable=True,
            driver=getattr(driver, "driver_name", "chrome_extension"),
        )
    except DriverError as exc:
        code = str(exc).split(":", 1)[0]
        if code in {"EXTENSION_UNPAIRED", "EXTENSION_DISCONNECTED"}:
            return connection_result_from_bridge_status(
                chrome_extension_manager.public_status()
            )
        return _connection_result(
            code="CONNECTION_FAILED",
            state="disconnected",
            title="Connexion Chrome impossible",
            message=str(exc),
            recoverable=True,
            driver=getattr(driver, "driver_name", "chrome_extension"),
        )
    probe = opened.get("probe") if isinstance(opened, dict) else None
    if not isinstance(probe, dict):
        probe = await driver.probe()
    return connection_result_from_probe(
        probe,
        opened=opened if isinstance(opened, dict) else None,
        driver=getattr(driver, "driver_name", "chrome_extension"),
    )


async def retry_connection_with_driver(driver) -> dict[str, Any]:
    try:
        probe = await driver.probe()
    except TabClosedError:
        return _connection_result(
            code="TAB_CLOSED",
            state="disconnected",
            title="Onglet ChatGPT fermé",
            message="Rouvre et connecte ChatGPT pour continuer.",
            recoverable=True,
            driver=getattr(driver, "driver_name", "chrome_extension"),
        )
    except DriverError as exc:
        return _connection_result(
            code="CONNECTION_FAILED",
            state="disconnected",
            title="Vérification Chrome impossible",
            message=str(exc),
            recoverable=True,
            driver=getattr(driver, "driver_name", "chrome_extension"),
        )
    return connection_result_from_probe(
        probe,
        driver=getattr(driver, "driver_name", "chrome_extension"),
    )


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
    driver = None
    try:
        driver = browser_driver_factory(
            session="cortex-bridge-ui",
            settings=settings,
        )
        health = await driver.health()
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
        (
            "Installe ou active l’extension Cortex Bridge dans Chrome."
            if driver_name == "chrome_extension"
            else "Ouvre explicitement le navigateur de développement."
        ),
    ))

    # 4. ChatGPT page usable
    tabs = int(health.get("tabs") or 0)
    probe: dict[str, Any] = {}
    if bridge_ok and tabs > 0 and driver is not None:
        try:
            probe = await driver.probe()
        except Exception as exc:
            probe = {"ok": False, "error": str(exc)}
    probe_url = str(probe.get("url") or "")
    probe_host = (urlparse(probe_url).hostname or "").lower()
    chatgpt_ok = (
        bridge_ok
        and tabs > 0
        and bool(probe.get("ok"))
        and probe_host in {"chatgpt.com", "www.chatgpt.com"}
    )
    checks.append(_check(
        "chatgpt-tab", "ChatGPT est prêt",
        chatgpt_ok,
        "Composeur ChatGPT détecté" if chatgpt_ok else "La page ChatGPT n'est pas encore utilisable",
        "Ouvre et connecte ChatGPT dans Chrome, puis termine la connexion ou la vérification affichée.",
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
    settings: dict[str, Any] | None = None
    driver = None
    try:
        settings = settings_api.load_settings()
        driver = browser_driver_factory(
            session="cortex-bridge-ui",
            settings=settings,
        )
        if getattr(driver, "driver_name", None) == "chrome_extension":
            if not chrome_extension_manager.public_status().get("paired"):
                return connection_result_from_bridge_status(
                    chrome_extension_manager.public_status()
                )
            return await open_connection_with_driver(driver)
        return await driver.open_login()
    except Exception as exc:
        driver_name = getattr(driver, "driver_name", None)
        if driver_name is None and settings is not None:
            driver_name = settings.get("browser_transport")
        raise HTTPException(
            status_code=503,
            detail={
                "code": "BROWSER_LOGIN_FAILED",
                "driver": driver_name or "unknown",
                "error": str(exc),
            },
        ) from exc


@router.post("/chrome-extension/open")
async def open_chrome_extension() -> dict[str, Any]:
    status = chrome_extension_manager.public_status()
    if not status.get("paired"):
        return connection_result_from_bridge_status(status)
    driver = browser_driver_factory(
        session="cortex-bridge-ui",
        settings=settings_api.load_settings(),
    )
    return await open_connection_with_driver(driver)


@router.post("/chrome-extension/retry")
async def retry_chrome_extension() -> dict[str, Any]:
    status = chrome_extension_manager.public_status()
    if not status.get("paired"):
        return connection_result_from_bridge_status(status)
    driver = browser_driver_factory(
        session="cortex-bridge-ui",
        settings=settings_api.load_settings(),
    )
    return await retry_connection_with_driver(driver)
