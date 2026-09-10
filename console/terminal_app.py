"""Interactive, safety-bound terminal controller for the local Cortex API."""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from terminal_client import ApiClient, ApiError
from terminal_view import banner, line, safe_text


_YES = {"o", "oui", "y", "yes"}
_TERMINAL_RUN_STATES = {"COMPLETED", "FAILED", "CANCELLED"}
_TERMINAL_MISSION_STATES = {"COMPLETED", "BLOCKED", "FAILED", "CANCELLED"}
_PAIRING_PAGE_URL = "http://127.0.0.1:8420/"
_SETTING_KEYS = {
    "language", "theme", "approval_policy", "access_profile", "default_workspace",
    "max_iterations", "max_duration_minutes", "ollama_context", "auto_continue",
    "browser_research", "network_access", "persist_conversation_history",
    "response_stability_seconds", "chat_timeout_seconds", "browser_transport",
    "browser_profile_root",
}


@dataclass
class _DraftSubmission:
    selection_key: str
    text: str
    run_id: str | None = None


class TerminalApp:
    def __init__(
        self,
        client: ApiClient,
        input_fn: Callable[[str], str] = input,
        output: Callable[[str], None] | None = None,
        open_ui: Callable[[], Any] | None = None,
        start_backend: Callable[[], Any] | None = None,
    ) -> None:
        self.client = client
        self.input_fn = input_fn
        self.output = output or print
        self.open_ui = open_ui
        self.start_backend = start_backend
        self.conversation_url = "https://chatgpt.com"
        self.new_conversation = True
        self._provisional_count = 0
        self._selection_key = "provisional:0"
        self.workspace: str | None = None
        self.conversations: list[dict[str, Any]] = []
        self.selected_run_id: str | None = None
        self.selected_mission_id: str | None = None
        self.unconfirmed_drafts: dict[str, _DraftSubmission] = {}
        self._draft_count = 0
        self._run_draft_ids: dict[str, str] = {}
        self._seen_run_details: dict[str, tuple[str | None, str | None]] = {}
        self._confirmed_delivery_runs: set[str] = set()
        self._sleep = time.sleep

    def _say(self, message: Any = "") -> None:
        self.output(safe_text(message))

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None,
                 query: dict[str, Any] | None = None) -> Any | None:
        try:
            return self.client.request(method, path, body=body, query=query)
        except ApiError as exc:
            qualifier = " (état incertain : aucune relance automatique)" if exc.uncertain else ""
            self._say(f"Backend indisponible ou refusé : {exc.message}{qualifier}")
            return None

    def _confirm(self, prompt: str) -> bool:
        try:
            return self.input_fn(prompt).strip().lower() in _YES
        except (EOFError, KeyboardInterrupt):
            self._say("Confirmation annulée.")
            return False

    def _welcome(self) -> None:
        width = shutil.get_terminal_size(fallback=(72, 24)).columns
        self._say(banner(width))
        self._say("Cortex terminal — /aide pour les commandes")
        status = self._request("GET", "/api/status")
        pipeline = self._request("GET", "/api/pipeline/status")
        if isinstance(status, dict):
            self._say(line("Exécuteur disponible", "oui" if status.get("executor_available") else "non"))
        if isinstance(pipeline, dict):
            components = pipeline.get("components") or []
            transport = next((row for row in components if row.get("id") == "transport"), {})
            self._say(line("ChatGPT", transport.get("state", "indisponible")))
        self._say(line("Workspace", self.workspace or "non sélectionné"))
        self._say(line("Conversation", self.conversation_url))
        self._say("Menu : 1 conversations · 2 nouvelle · 3 missions · /quitter")

    def run(self) -> int:
        self._welcome()
        while True:
            try:
                command = self.input_fn("cortex> ")
            except EOFError:
                self._say("Fin de l’entrée. Le serveur reste actif.")
                return 0
            except KeyboardInterrupt:
                self._say("Interrompu. Rien n’a été annulé.")
                continue
            if not self.execute(command):
                return 0

    def execute(self, command: str) -> bool:
        raw = command.rstrip("\r\n")
        if not raw.strip():
            return True
        numeric = {"1": "/conversations", "2": "/nouvelle", "3": "/missions"}
        raw = numeric.get(raw.strip(), raw)
        if not raw.startswith("/"):
            return self._send_chat(raw)
        name, _, argument = raw.partition(" ")
        argument = argument.strip()
        handlers = {
            "/aide": self._help, "/statut": self._status,
            "/conversations": self._conversations, "/nouvelle": self._new_conversation,
            "/historique": self._history, "/brouillon": self._draft, "/missions": self._missions,
            "/suivre": self._follow, "/rafraichir": self._refresh,
            "/autoriser": self._approve, "/refuser": self._deny,
            "/stop": self._stop, "/reglages": self._settings,
            "/modeles": self._models, "/consentement": self._consent,
            "/connecter": self._connect, "/reessayer": self._retry,
            "/ui": self._ui, "/demarrer": self._start, "/quitter": self._quit,
        }
        if name == "/chat":
            return self._send_chat(argument)
        if name == "/ouvrir":
            return self._open_conversation(argument)
        if name == "/mission":
            return self._mission(argument)
        if name == "/mission-ouvrir":
            return self._open_mission(argument)
        if name == "/reglage":
            return self._set_setting(argument)
        if name == "/modele":
            return self._select_model(argument)
        if name == "/dossier":
            return self._set_workspace(argument)
        handler = handlers.get(name)
        if handler is None:
            self._say("Commande inconnue. /aide")
            return True
        return handler()

    def _help(self) -> bool:
        self._say("/statut /conversations /ouvrir N /nouvelle /historique /brouillon /chat TEXTE")
        self._say("/mission OBJECTIF /missions /mission-ouvrir ID /suivre /rafraichir")
        self._say("/autoriser /refuser /stop /reglages /reglage CLÉ VALEUR")
        self._say("/modeles /modele LIBELLÉ /dossier CHEMIN /consentement /connecter /reessayer /ui /demarrer /quitter")
        return True

    def _status(self) -> bool:
        status = self._request("GET", "/api/status")
        pipeline = self._request("GET", "/api/pipeline/status")
        if isinstance(status, dict):
            self._say(line("ChatGPT/transport", "voir pipeline"))
            self._say(line("Exécuteur", status.get("executor_available", False)))
        if isinstance(pipeline, dict):
            for component in pipeline.get("components", []):
                if component.get("id") in {"transport", "executor"}:
                    self._say(line(component.get("label", component.get("id")), component.get("state")))
        return True

    def _conversations(self) -> bool:
        rows = self._request("GET", "/api/conversations")
        if not isinstance(rows, list):
            return True
        self.conversations = [row for row in rows[:50] if isinstance(row, dict)]
        if not self.conversations:
            self._say("Aucune conversation disponible.")
            return True
        for index, row in enumerate(self.conversations, 1):
            self._say(f"{index}. {row.get('title') or row.get('url') or 'Sans titre'}")
        return True

    def _open_conversation(self, argument: str) -> bool:
        try:
            index = int(argument)
            if not 1 <= index <= len(self.conversations):
                raise IndexError
            row = self.conversations[index - 1]
        except (ValueError, IndexError):
            self._say("Indice de conversation invalide. Lance /conversations.")
            return True
        url = row.get("url") or row.get("conversation_url")
        if not isinstance(url, str) or not url:
            self._say("Conversation sans URL exploitable.")
            return True
        self.conversation_url = url
        self.new_conversation = False
        self._selection_key = f"conversation:{url}"
        self._clear_active_targets()
        self._say(line("Conversation sélectionnée", url))
        return True

    def _new_conversation(self) -> bool:
        self.conversation_url = "https://chatgpt.com"
        self.new_conversation = True
        self._provisional_count += 1
        self._selection_key = f"provisional:{self._provisional_count}"
        self._clear_active_targets()
        self._say("Nouvelle conversation sélectionnée (provisoire jusqu’à URL canonique).")
        return True

    def _clear_active_targets(self) -> None:
        self.selected_run_id = None
        self.selected_mission_id = None

    def _send_chat(self, text: str) -> bool:
        if not text:
            self._say("Le message est vide.")
            return True
        self._draft_count += 1
        draft_id = f"submission:{self._draft_count}"
        draft = _DraftSubmission(selection_key=self._selection_key, text=text)
        self.unconfirmed_drafts[draft_id] = draft
        run = self._request("POST", "/api/chat/send", {
            "conversation_url": self.conversation_url,
            "text": text,
            "new_conversation": self.new_conversation,
        })
        if not isinstance(run, dict):
            return True
        self.selected_run_id = str(run.get("id") or "") or None
        if self.selected_run_id:
            self.selected_mission_id = None
            draft.run_id = self.selected_run_id
            self._run_draft_ids[self.selected_run_id] = draft_id
        canonical = run.get("canonical_url")
        if isinstance(canonical, str) and canonical:
            self.conversation_url = canonical
            self.new_conversation = False
            canonical_key = f"conversation:{canonical}"
            self._rekey_drafts(draft.selection_key, canonical_key)
            self._selection_key = canonical_key
        state = str(run.get("state") or "inconnu")
        if state == "QUEUED":
            self._say("Message en file : il n’est pas confirmé ni relancé automatiquement.")
        else:
            self._say(line("Envoi", state))
        return True

    def _history(self) -> bool:
        if self.new_conversation or "/c/" not in self.conversation_url:
            self._say("Historique indisponible : sélectionne une conversation canonique.")
            return True
        snapshot = self._request(
            "GET", "/api/conversations/snapshot", query={"url": self.conversation_url},
        )
        if isinstance(snapshot, dict):
            for message in snapshot.get("messages", []):
                if isinstance(message, dict):
                    self._say(f"{message.get('role', 'message')}: {message.get('text', '')}")
        return True

    def _draft(self) -> bool:
        drafts = [
            draft.text for draft in self.unconfirmed_drafts.values()
            if draft.selection_key == self._selection_key
        ]
        if not drafts:
            self._say("Aucun brouillon non confirmé pour cette sélection.")
        else:
            for draft in drafts:
                self._say(draft)
        return True

    def _rekey_drafts(self, previous_key: str, canonical_key: str) -> None:
        for draft in self.unconfirmed_drafts.values():
            if draft.selection_key == previous_key:
                draft.selection_key = canonical_key

    def _mission(self, objective: str) -> bool:
        if not objective:
            self._say("Usage : /mission OBJECTIF")
            return True
        settings = self._request("GET", "/api/settings")
        if not isinstance(settings, dict):
            return True
        workspace = self.workspace or str(settings.get("default_workspace") or "")
        if not workspace:
            self._say("Workspace absent : utilise /dossier CHEMIN.")
            return True
        self._say(f"Mission déterministe, sans réseau, approbation par écriture : {objective}")
        self._say(line("Workspace", workspace))
        if not self._confirm("Créer cette mission ? [oui/N] "):
            return True
        mission = self._request("POST", "/api/missions", {
            "objective": objective,
            "workspace": workspace,
            "conversation_url": self.conversation_url,
            "new_conversation": self.new_conversation,
            "approval_policy": "workspace-write-with-approvals",
            "executor_kind": "deterministic",
            "allow_network": False,
            "allow_write": False,
            "allow_processes": False,
        })
        if isinstance(mission, dict):
            self.selected_mission_id = str(mission.get("id") or "") or None
            if self.selected_mission_id:
                self.selected_run_id = None
            self._say(line("Mission", mission.get("id")))
        return True

    def _missions(self) -> bool:
        rows = self._request("GET", "/api/missions")
        if isinstance(rows, list):
            for row in rows[:50]:
                self._say(f"{row.get('id')} · {row.get('state')}")
        return True

    def _open_mission(self, mission_id: str) -> bool:
        if not mission_id:
            self._say("Usage : /mission-ouvrir ID")
        else:
            self.selected_mission_id = mission_id
            self.selected_run_id = None
            self._say(line("Mission sélectionnée", mission_id))
        return True

    def _refresh(self) -> bool:
        if self.selected_run_id:
            run_id = self.selected_run_id
            run = self._request("GET", f"/api/chat/runs/{run_id}")
            if isinstance(run, dict):
                self._reconcile_run(run_id, run)
        if self.selected_mission_id:
            mission = self._request("GET", f"/api/missions/{self.selected_mission_id}")
            if isinstance(mission, dict):
                self._say(f"Mission {self.selected_mission_id} · {mission.get('mission', {}).get('state')}")
        if not self.selected_run_id and not self.selected_mission_id:
            self._say("Aucun run ni mission sélectionné.")
        return True

    def _reconcile_run(self, run_id: str, run: dict[str, Any]) -> None:
        draft_id = self._run_draft_ids.get(run_id)
        draft = self.unconfirmed_drafts.get(draft_id or "")
        canonical = run.get("canonical_url")
        if (
            isinstance(canonical, str) and canonical
            and self.selected_run_id == run_id
            and draft is not None
            and draft.selection_key == self._selection_key
        ):
            canonical_key = f"conversation:{canonical}"
            self.conversation_url, self.new_conversation = canonical, False
            self._rekey_drafts(draft.selection_key, canonical_key)
            self._selection_key = canonical_key
        if run.get("delivered_at"):
            delivered_draft_id = self._run_draft_ids.pop(run_id, None)
            if delivered_draft_id is not None:
                self.unconfirmed_drafts.pop(delivered_draft_id, None)
            if run_id not in self._confirmed_delivery_runs:
                self._say("Livraison confirmée.")
                self._confirmed_delivery_runs.add(run_id)
        self._say(f"Run {run.get('id')} · {run.get('state')}")
        response = run.get("response_text")
        error = run.get("error")
        response_text = response if isinstance(response, str) and response else None
        error_text = error if isinstance(error, str) and error else None
        details = (response_text, error_text)
        if self._seen_run_details.get(run_id) != details:
            if response_text:
                self._say(line("Réponse", response_text))
            if error_text:
                self._say(line("Erreur", error_text))
            self._seen_run_details[run_id] = details

    def _follow(self) -> bool:
        try:
            if self.selected_mission_id:
                while True:
                    payload = self._request("GET", f"/api/missions/{self.selected_mission_id}")
                    if not isinstance(payload, dict):
                        return True
                    state = str((payload.get("mission") or {}).get("state") or "inconnu")
                    self._say(f"Mission {self.selected_mission_id} · {state}")
                    if state in _TERMINAL_MISSION_STATES or state == "WAITING_FOR_APPROVAL":
                        return True
                    self._sleep(1.0)
            elif self.selected_run_id:
                while True:
                    run_id = self.selected_run_id
                    payload = self._request("GET", f"/api/chat/runs/{run_id}")
                    if not isinstance(payload, dict):
                        return True
                    state = str(payload.get("state") or "inconnu")
                    self._reconcile_run(run_id, payload)
                    if state in _TERMINAL_RUN_STATES:
                        return True
                    self._sleep(1.0)
            else:
                self._say("Aucun run ni mission sélectionné.")
        except KeyboardInterrupt:
            self._say("Suivi interrompu. Rien n’a été annulé.")
        return True

    @staticmethod
    def _pending_action(payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
        mission = payload.get("mission") or {}
        timeline = payload.get("timeline") or {}
        if mission.get("state") != "WAITING_FOR_APPROVAL" or not payload.get("awaiting_approval"):
            return None
        policies = timeline.get("policy_decisions") or []
        policy = next((row for row in reversed(policies)
                       if row.get("requires_approval") in (True, 1)), None)
        if not isinstance(policy, dict) or not policy.get("action_id"):
            return None
        decisions = timeline.get("orchestrator_decisions") or []
        decision = next((row for row in reversed(decisions)
                         if row.get("action_id") == policy.get("action_id")), None)
        if not isinstance(decision, dict):
            return None
        raw = decision.get("decision_json")
        try:
            content = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            return None
        action = content.get("action") if isinstance(content, dict) else None
        if not isinstance(action, dict) or not action.get("tool"):
            return None
        action_id = str(policy["action_id"])
        if content.get("actionId") != action_id:
            return None
        # The backend publishes its currently waiting action explicitly. Do
        # not emulate an atomic guard if an older backend cannot provide one.
        if payload.get("pending_approval_action_id") != action_id:
            return None
        return action_id, action

    def _approval_payload(self) -> tuple[str, dict[str, Any]] | None:
        if not self.selected_mission_id:
            self._say("Aucune mission sélectionnée.")
            return None
        payload = self._request("GET", f"/api/missions/{self.selected_mission_id}")
        if not isinstance(payload, dict):
            return None
        pending = self._pending_action(payload)
        if pending is None:
            self._say("Approbation refusée : action absente, périmée ou ambiguë.")
        return pending

    def _approve(self) -> bool:
        pending = self._approval_payload()
        if pending is None:
            return True
        action_id, action = pending
        self._say(line("Action", action_id))
        self._say(line("Outil", action.get("tool")))
        self._say(line("Arguments", json.dumps(action.get("arguments", {}), ensure_ascii=False)))
        if not self._confirm("Autoriser cette action unique ? [oui/N] "):
            return True
        # Re-read immediately before the unsupported non-atomic API call.
        fresh = self._approval_payload()
        if fresh is None or fresh[0] != action_id:
            self._say("Approbation refusée : action modifiée avant validation.")
            return True
        self._request("POST", f"/api/missions/{self.selected_mission_id}/approve", {
            "scope": "once", "approve": True, "expected_action_id": action_id,
        })
        return True

    def _deny(self) -> bool:
        pending = self._approval_payload()
        if pending is not None:
            self._request("POST", f"/api/missions/{self.selected_mission_id}/approve", {
                "scope": "once", "approve": False, "expected_action_id": pending[0],
            })
        return True

    def _stop(self) -> bool:
        if self.selected_mission_id:
            self._request("POST", f"/api/missions/{self.selected_mission_id}/cancel", {})
            self._say("Annulation demandée pour la mission sélectionnée.")
        elif self.selected_run_id:
            self._request("POST", f"/api/chat/runs/{self.selected_run_id}/cancel", {})
            self._say("Annulation demandée pour le run sélectionné.")
        else:
            self._say("Sélectionne un run ou une mission avant /stop.")
        return True

    def _settings(self) -> bool:
        settings = self._request("GET", "/api/settings")
        if isinstance(settings, dict):
            for key in sorted(_SETTING_KEYS):
                if key in settings:
                    self._say(line(key, settings[key]))
        return True

    @staticmethod
    def _parse_setting(value: str, current: Any) -> Any:
        if isinstance(current, bool):
            if value.lower() not in {"true", "false"}:
                raise ValueError("valeur booléenne attendue : true ou false")
            return value.lower() == "true"
        if isinstance(current, int) and not isinstance(current, bool):
            return int(value)
        if isinstance(current, float):
            return float(value)
        return value

    def _set_setting(self, argument: str) -> bool:
        key, separator, value = argument.partition(" ")
        if not separator or key not in _SETTING_KEYS:
            self._say("Réglage non autorisé ou valeur absente.")
            return True
        current = self._request("GET", "/api/settings")
        if not isinstance(current, dict) or key not in current:
            return True
        try:
            changed = self._parse_setting(value, current[key])
        except ValueError as exc:
            self._say(str(exc))
            return True
        if not self._confirm(f"Modifier {key} en {changed} ? [oui/N] "):
            return True
        body = {name: item for name, item in current.items() if name != "process_capabilities"}
        body[key] = changed
        result = self._request("PUT", "/api/settings", body)
        if isinstance(result, dict):
            self._say(line("Réglage confirmé", f"{key}={result.get(key)}"))
        return True

    def _models(self) -> bool:
        result = self._request("GET", "/api/models/chatgpt")
        if isinstance(result, dict):
            if result.get("error"):
                self._say(f"Découverte des modèles indisponible : {result['error']}")
                return True
            for model in result.get("models", []):
                if isinstance(model, dict):
                    self._say(f"{model.get('label')}" + (" (actuel)" if model.get("selected") else ""))
        return True

    def _select_model(self, label: str) -> bool:
        models = self._request("GET", "/api/models/chatgpt")
        if not isinstance(models, dict) or models.get("error"):
            self._say("Découverte des modèles indisponible ; sélection refusée.")
            return True
        visible = {str(row.get("label")) for row in (models or {}).get("models", []) if isinstance(row, dict)}
        if not label or label not in visible:
            self._say("Modèle absent des libellés découverts par le backend.")
            return True
        result = self._request("PUT", "/api/models/chatgpt", {
            "conversation_url": self.conversation_url, "label": label,
        })
        if isinstance(result, dict):
            self._say(line("Modèle confirmé", result.get("selected")))
        return True

    def _set_workspace(self, path: str) -> bool:
        candidate = Path(path).expanduser()
        if not path or not candidate.is_absolute():
            self._say("Le dossier doit être un chemin absolu.")
            return True
        self.workspace = str(candidate)
        self._say(line("Workspace sélectionné", self.workspace))
        return True

    def _consent(self) -> bool:
        status = self._request("GET", "/api/transport/status")
        if not isinstance(status, dict):
            return True
        self._say(status.get("experimental_warning") or "Transport ChatGPT expérimental.")
        if self._confirm("Accepter ce transport ? [oui/N] "):
            self._request("POST", "/api/transport/opt-in", {"accepted": True})
        return True

    def _connect(self) -> bool:
        status = self._request("GET", "/api/chrome-extension/status")
        if isinstance(status, dict) and not status.get("paired"):
            pairing_url = self._pairing_page_url()
            if self.open_ui is None:
                self._say(f"Extension non appairée. Ouvre {pairing_url} pour l’appairage Chrome.")
                return True
            try:
                opened = self.open_ui()
            except Exception:
                self._say(f"Impossible d’ouvrir Cortex. Ouvre {pairing_url} pour l’appairage Chrome.")
                return True
            if opened is False:
                self._say(f"Cortex n’a pas ouvert la page. Ouvre {pairing_url} pour l’appairage Chrome.")
                return True
            self._say("Page Cortex ouverte pour l’appairage Chrome.")
            return True
        result = self._request("POST", "/api/chrome-extension/open", {})
        if isinstance(result, dict):
            self._say(line("Connexion", result.get("state") or result.get("code") or "état inconnu"))
        return True

    def _pairing_page_url(self) -> str:
        base_url = getattr(self.client, "base_url", None)
        if isinstance(base_url, str) and base_url:
            return base_url.rstrip("/") + "/"
        return _PAIRING_PAGE_URL

    def _retry(self) -> bool:
        result = self._request("POST", "/api/chrome-extension/retry", {})
        if isinstance(result, dict):
            self._say(line("Connexion", result.get("state") or result.get("code") or "état inconnu"))
        return True

    def _ui(self) -> bool:
        if self.open_ui is None:
            self._say("Ouverture UI non configurée.")
        elif self.open_ui() is False:
            self._say(f"Impossible d’ouvrir l’interface Cortex. Ouvre {self._pairing_page_url()} manuellement.")
        return True

    def _start(self) -> bool:
        if self.start_backend is None:
            self._say("Démarrage backend non configuré.")
        else:
            self.start_backend()
        return True

    def _quit(self) -> bool:
        self._say("Terminal fermé. Le serveur n’a pas été arrêté.")
        return False
