"""Small, dependency-free rendering helpers for the Cortex terminal."""

from __future__ import annotations

import re
from typing import Any


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")


def safe_text(value: Any) -> str:
    """Render untrusted backend text without allowing terminal controls."""
    return _CONTROL.sub("", str(value)).replace("\x1b", "")


def banner(width: int = 72) -> str:
    """Return a width-bounded CORTEX wordmark with a narrow fallback."""
    width = max(8, int(width))
    wordmark = (
        " ██████   █████   ██████  ████████ ███████ ██   ██",
        "██        ██   ██  ██   ██    ██    ██       ██ ██ ",
        "██        ██   ██  ██████     ██    █████     ███  ",
        "██        ██   ██  ██  ██      ██    ██       ██ ██ ",
        " ██████   █████   ██   ██     ██    ███████ ██   ██",
    )
    if width < max(len(row) for row in wordmark):
        return "CORTEX"[:width]
    return "\n".join(row.center(width) for row in wordmark)


def line(label: str, value: Any) -> str:
    return f"{safe_text(label)} : {safe_text(value)}"
