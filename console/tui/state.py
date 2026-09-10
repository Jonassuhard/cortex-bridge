"""Pure state helpers shared by the Cortex terminal UI and its tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from terminal_view import safe_text


@dataclass
class TuiState:
    connection: str = "inconnu"
    executor: str = "inconnu"
    planner_label: str = "modèle ChatGPT actuel"
    executor_label: str = "Outils locaux vérifiés"
    workspace: str = "non sélectionné"
    conversation_url: str = "https://chatgpt.com"
    conversation_title: str = "Nouvelle conversation"
    conversations: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    activity: str = "Aucune activité"
    delivery: str = "Prêt"
    draft: str = ""

    def transcript(self) -> str:
        rows = []
        for message in self.messages:
            role = safe_text(message.get("role", "message")).capitalize()
            text = safe_text(message.get("text", message.get("content", "")))
            rows.append(f"{role}\n{text}" if text else role)
        return "\n\n".join(rows) or "Aucun message dans cette conversation."

    def conversation_rows(self) -> list[tuple[str, str]]:
        rows = []
        for index, row in enumerate(self.conversations[:50]):
            title = safe_text(row.get("title") or row.get("name") or "Sans titre")
            url = row.get("url") or row.get("conversation_url") or ""
            rows.append((f"{index}:{title}", str(url)))
        return rows
