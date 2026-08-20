"""Canonical Cortex Bridge version."""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path


def current_version() -> str:
    configured = os.environ.get("CORTEX_VERSION_FILE")
    candidate = Path(configured).expanduser() if configured else Path(__file__).resolve().parent.parent / "VERSION"
    try:
        value = candidate.read_text(encoding="utf-8").strip()
    except OSError:
        try:
            return package_version("cortex-bridge")
        except PackageNotFoundError as exc:
            raise RuntimeError("Cortex Bridge version metadata is unavailable") from exc
    if not value:
        raise RuntimeError("Cortex Bridge VERSION is empty")
    return value
