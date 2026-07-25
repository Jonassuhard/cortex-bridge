"""Two-write-conversation guard (P2b, Jonas spec).

Cortex Bridge may WRITE into at most two ChatGPT conversations at once
(reading stays unlimited). A third write is refused with an explicit French
message and the user's draft must be preserved by the UI.

This guard is best-effort and in-memory: it tracks active (non-terminal) chat
runs and missions. It never kills or replaces an existing session — it only
refuses NEW writes.
"""

from __future__ import annotations

MAX_WRITE_CONVERSATIONS = 2

REFUSAL_MESSAGE = (
    "Vous pouvez consulter cette conversation, mais Cortex Bridge ne peut "
    "écrire que dans deux conversations à la fois. Libérez l'une des "
    "conversations actives pour envoyer ce message. Votre brouillon est conservé."
)

TERMINAL_STATES = {"COMPLETED", "BLOCKED", "FAILED", "CANCELLED"}


def _normalize(url: str) -> str:
    return (url or "").strip().rstrip("/")


def active_write_conversations() -> set[str]:
    """Conversation URLs with at least one active chat run or mission."""
    urls: set[str] = set()
    try:
        import chat as chat_api  # late import: chat.py imports this module

        for run in chat_api.list_active_runs():
            urls.add(_normalize(run.canonical_url or run.conversation_url))
    except Exception:
        pass
    try:
        import missions as missions_api

        for url in missions_api.active_mission_conversations():
            urls.add(_normalize(url))
    except Exception:
        pass
    urls.discard("")
    return urls


def write_slot_available(conversation_url: str) -> tuple[bool, set[str]]:
    """True when writing into `conversation_url` is allowed right now."""
    active = active_write_conversations()
    key = _normalize(conversation_url)
    if key in active or len(active) < MAX_WRITE_CONVERSATIONS:
        return True, active
    return False, active
