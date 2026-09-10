"""Polished full-screen Cortex terminal UI.

The UI is deliberately a client: policy, transport, leases and execution truth
remain owned by the existing local API. Network calls run in Textual workers so
typing and navigation remain responsive while ChatGPT is connecting.
"""

from __future__ import annotations

from typing import Any, Callable

from terminal_client import ApiClient, ApiError
from terminal_view import safe_text

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal, Vertical, VerticalScroll
    from textual.widgets import Button, Footer, Header, Label, ListItem, ListView, Select, Static, TextArea
except ImportError:  # pragma: no cover - exercised by launcher fallback
    App = None  # type: ignore[assignment]

from .state import TuiState


_CSS = """
Screen { background: #0b0e13; color: #e7edf5; }
Header { background: #111722; color: #e7edf5; height: 3; }
Footer { background: #111722; color: #a8b5c8; }
#root { height: 1fr; padding: 1 2; }
#status { height: 3; margin-bottom: 1; }
.status { width: 1fr; height: 3; border: round #31445f; padding: 0 1; }
.status-ready { border: round #5ee06e; }
.status-wait { border: round #e3b341; }
.status-bad { border: round #e06c75; }
#body { height: 1fr; }
#sidebar { width: 28; min-width: 24; border: round #31445f; padding: 1; margin-right: 1; }
#main { width: 1fr; }
#transcript { height: 1fr; border: round #31445f; padding: 1 2; overflow-y: auto; }
#composer { height: 8; border: round #4f8cff; margin-top: 1; }
#toolbar { height: 3; margin-top: 1; }
Button { margin-right: 1; }
Select { width: 1fr; margin-bottom: 1; }
Input { margin-bottom: 1; }
ListView { height: 1fr; border: none; }
ListItem { padding: 0 1; }
.muted { color: #9aa8ba; }
.section-title { color: #e7edf5; text-style: bold; margin-bottom: 1; }
"""


class CortexTui(App if App is not None else object):
    """Cortex full-screen client.

    ``offline=True`` is used by headless tests and never performs network I/O.
    """

    TITLE = "Cortex Bridge"
    CSS = _CSS
    BINDINGS = [
        ("ctrl+n", "new_conversation", "Nouvelle conversation"),
        ("ctrl+r", "refresh_data", "Actualiser"),
        ("ctrl+k", "focus_composer", "Écrire"),
        ("ctrl+q", "quit", "Quitter"),
    ]

    def __init__(
        self,
        client: ApiClient | Any | None = None,
        *,
        open_ui: Callable[[], Any] | None = None,
        start_backend: Callable[[], Any] | None = None,
        offline: bool = False,
    ) -> None:
        if App is None:
            raise RuntimeError("L’interface plein écran nécessite la dépendance textual verrouillée")
        super().__init__()
        self.client = client
        self.open_ui = open_ui
        self.start_backend = start_backend
        self.offline = offline
        self.state = TuiState()
        self._selected_index: int | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Container(id="root"):
            with Horizontal(id="status"):
                yield Static("ChatGPT\nÉtat inconnu", id="chat-status", classes="status status-wait", markup=False)
                yield Static("Exécuteur\nOutils locaux vérifiés", id="executor-status", classes="status status-wait", markup=False)
            with Horizontal(id="body"):
                with Vertical(id="sidebar"):
                    yield Label("CONVERSATIONS", classes="section-title", markup=False)
                    yield Button("Nouvelle conversation", id="new-conversation", variant="primary")
                    yield Button("Actualiser", id="refresh-conversations")
                    yield ListView(id="conversation-list")
                with Vertical(id="main"):
                    yield Label("Conversation", id="conversation-title", classes="section-title", markup=False)
                    with VerticalScroll(id="transcript"):
                        yield Static("Aucun message dans cette conversation.", id="transcript-text", markup=False)
                    yield TextArea(id="composer", language=None, show_line_numbers=False)
                    with Horizontal(id="toolbar"):
                        yield Select([("Modèle ChatGPT actuel", "current")], value="current", id="planner-select", allow_blank=False)
                        yield Select([("Outils locaux vérifiés", "deterministic")], value="deterministic", id="executor-select", allow_blank=False)
                        yield Button("Envoyer", id="send", variant="success")
                        yield Button("Connecter", id="connect")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#composer", TextArea).focus()
        if not self.offline:
            self.run_worker(self._load_initial, thread=True, name="initial-load")

    def _request(self, method: str, path: str, *, body: dict[str, Any] | None = None,
                 query: dict[str, Any] | None = None) -> Any:
        if self.client is None:
            return None
        return self.client.request(method, path, body=body, query=query)

    def _load_initial(self) -> None:
        if self.start_backend is not None:
            try:
                self.start_backend()
            except Exception:
                pass
        payload: dict[str, Any] = {}
        try:
            payload["status"] = self._request("GET", "/api/status") or {}
            payload["pipeline"] = self._request("GET", "/api/pipeline/status") or {}
            payload["conversations"] = self._request("GET", "/api/conversations") or []
            payload["models"] = self._request("GET", "/api/models/chatgpt") or {}
        except (ApiError, OSError, ValueError) as exc:
            payload["error"] = str(exc)
        self.call_from_thread(self._apply_initial, payload)

    def _apply_initial(self, payload: dict[str, Any]) -> None:
        if payload.get("error"):
            self.state.connection = "indisponible"
            self.state.delivery = safe_text(payload["error"])
        status = payload.get("status") or {}
        self.state.executor = "disponible" if status.get("executor_available") else "indisponible"
        pipeline = payload.get("pipeline") or {}
        components = pipeline.get("components") or []
        transport = next((row for row in components if row.get("id") == "transport"), {})
        self.state.connection = str(transport.get("state") or self.state.connection)
        rows = payload.get("conversations")
        if isinstance(rows, list):
            self.state.conversations = [row for row in rows[:50] if isinstance(row, dict)]
        models = payload.get("models") or {}
        labels = [str(row.get("label")) for row in models.get("models", []) if isinstance(row, dict) and row.get("label")]
        if labels:
            select = self.query_one("#planner-select", Select)
            select.set_options([(label, label) for label in labels])
            select.value = labels[0]
            self.state.planner_label = labels[0]
        self._render()
        self._render_conversations()

    def _render(self) -> None:
        self.query_one("#chat-status", Static).update(f"ChatGPT\n{safe_text(self.state.connection)}")
        self.query_one("#executor-status", Static).update(f"Exécuteur\n{safe_text(self.state.executor_label)} · {safe_text(self.state.executor)}")
        self.query_one("#conversation-title", Label).update(safe_text(self.state.conversation_title))
        self.query_one("#transcript-text", Static).update(self.state.transcript())
        self.query_one("#transcript", VerticalScroll).scroll_end(animate=False)

    def _render_conversations(self) -> None:
        view = self.query_one("#conversation-list", ListView)
        view.clear()
        for index, row in enumerate(self.state.conversations[:50]):
            title = safe_text(row.get("title") or row.get("name") or "Sans titre")
            view.mount(ListItem(Label(title, markup=False), id=f"conversation-{index}"))

    def action_new_conversation(self) -> None:
        self.state.conversation_url = "https://chatgpt.com"
        self.state.conversation_title = "Nouvelle conversation"
        self.state.messages = []
        self._render()

    def action_refresh_data(self) -> None:
        if not self.offline:
            self.run_worker(self._load_initial, thread=True, name="refresh")

    def action_focus_composer(self) -> None:
        self.query_one("#composer", TextArea).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "new-conversation":
            self.action_new_conversation()
        elif event.button.id in {"refresh-conversations", "refresh"}:
            self.action_refresh_data()
        elif event.button.id == "send":
            self._submit_text()
        elif event.button.id == "connect":
            self._connect()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id is None or not event.item.id.startswith("conversation-"):
            return
        index = int(event.item.id.rsplit("-", 1)[1])
        if index >= len(self.state.conversations):
            return
        row = self.state.conversations[index]
        url = row.get("url") or row.get("conversation_url")
        if not isinstance(url, str) or not url:
            return
        self._selected_index = index
        self.state.conversation_url = url
        self.state.conversation_title = str(row.get("title") or "Conversation")
        if not self.offline:
            self.run_worker(lambda: self._load_snapshot(url), thread=True, name="snapshot")
        self._render()

    def _load_snapshot(self, url: str) -> None:
        try:
            result = self._request("GET", "/api/conversations/snapshot", query={"url": url}) or {}
            self.call_from_thread(self._apply_snapshot, result)
        except (ApiError, OSError, ValueError) as exc:
            self.call_from_thread(self._set_error, str(exc))

    def _apply_snapshot(self, result: dict[str, Any]) -> None:
        self.state.messages = [row for row in result.get("messages", []) if isinstance(row, dict)]
        self._render()

    def _set_error(self, message: str) -> None:
        self.state.delivery = safe_text(message)
        self._render()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "composer":
            self.state.draft = event.text_area.text

    def on_text_area_key(self, event: TextArea.Key) -> None:
        if event.text_area.id == "composer" and event.key == "ctrl+enter":
            event.stop()
            self._submit_text()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "planner-select" and event.value not in (Select.BLANK, None):
            self.state.planner_label = str(event.value)
            self.state.delivery = "Modèle sélectionné pour les prochains messages"
        elif event.select.id == "executor-select" and event.value not in (Select.BLANK, None):
            self.state.executor_label = str(event.value)
            self.state.delivery = "Exécuteur vérifié sélectionné"

    def _submit_text(self) -> None:
        text = self.query_one("#composer", TextArea).text
        if not text.strip():
            self.state.delivery = "Le message est vide"
            self._render()
            return
        if self.offline:
            self.state.delivery = "Mode hors ligne : message non envoyé"
            self._render()
            return
        self.state.delivery = "Envoi en cours…"
        self._render()
        self.run_worker(lambda: self._send(text), thread=True, name="send")

    def _send(self, text: str) -> None:
        try:
            result = self._request("POST", "/api/chat/send", body={
                "conversation_url": self.state.conversation_url,
                "text": text,
                "new_conversation": self.state.conversation_url.rstrip("/") == "https://chatgpt.com",
            }) or {}
            self.call_from_thread(self._sent, result)
        except (ApiError, OSError, ValueError) as exc:
            self.call_from_thread(self._send_failed, str(exc))

    def _sent(self, result: dict[str, Any]) -> None:
        state = safe_text(result.get("state") or "enregistré")
        self.state.delivery = f"Envoi confirmé : {state}"
        canonical = result.get("canonical_url")
        if isinstance(canonical, str) and canonical:
            self.state.conversation_url = canonical
        self.query_one("#composer", TextArea).clear()
        self._render()

    def _send_failed(self, message: str) -> None:
        self.state.delivery = f"Envoi non confirmé : {safe_text(message)}"
        self._render()

    def _connect(self) -> None:
        if self.offline:
            self.state.connection = "hors ligne"
            self._render()
            return
        self.state.connection = "connexion en cours…"
        self._render()
        self.run_worker(self._connect_request, thread=True, name="connect")

    def _connect_request(self) -> None:
        try:
            result = self._request("POST", "/api/chrome-extension/retry") or {}
            self.call_from_thread(self._connected, result)
        except (ApiError, OSError, ValueError) as exc:
            self.call_from_thread(self._send_failed, str(exc))

    def _connected(self, result: dict[str, Any]) -> None:
        self.state.connection = safe_text(result.get("state") or result.get("code") or "vérification terminée")
        self.state.delivery = safe_text(result.get("message") or "État ChatGPT actualisé")
        self._render()
