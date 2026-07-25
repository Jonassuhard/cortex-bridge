"""Attachment intake and validation (P3).

Two intake modes:
- base64 JSON upload from the browser file picker (bytes cross the loopback);
- direct local path (power users, zero copy).

Files land in console/data/attachments/ (already gitignored). Official ChatGPT
limits are pre-checked locally so the user gets a precise French error instead
of a silent ChatGPT refusal: 512 MB per file, 20 MB per image.
"""

from __future__ import annotations

import base64
import time
import uuid
from pathlib import Path

from transport.chatgpt_web.adapter import IMAGE_EXTENSIONS, MAX_FILE_BYTES, MAX_IMAGE_BYTES

DATA_DIR = Path(__file__).resolve().parent / "data"
ATTACHMENTS_DIR = DATA_DIR / "attachments"

# Paths the raw-bytes endpoint is allowed to serve (P3 fetch-injection).
# Only files that went through validate_size land here — never arbitrary
# disk reads from the loopback endpoint.
_ALLOWED_PATHS: dict[str, str] = {}


def register_allowed(path: str, name: str) -> None:
    _ALLOWED_PATHS[str(Path(path).resolve())] = name


def allowed_name(path: str) -> str | None:
    return _ALLOWED_PATHS.get(str(Path(path).resolve()))


def _mib(size: int) -> str:
    return f"{size / (1024 * 1024):.0f}"


def is_image_name(name: str) -> bool:
    return Path(name).suffix.lower() in IMAGE_EXTENSIONS


def validate_size(name: str, size: int) -> tuple[bool, str | None]:
    """Official-limit pre-check with a precise French error (P3)."""
    image = is_image_name(name)
    if image and size > MAX_IMAGE_BYTES:
        return False, (
            f"Cette image fait {_mib(size)} Mo. La limite actuelle du transport "
            f"ChatGPT est de {_mib(MAX_IMAGE_BYTES)} Mo par image. Elle n'a pas été envoyée."
        )
    if not image and size > MAX_FILE_BYTES:
        return False, (
            f"Ce fichier fait {_mib(size)} Mo. La limite actuelle du transport "
            f"ChatGPT est de {_mib(MAX_FILE_BYTES)} Mo par fichier. Il n'a pas été envoyé."
        )
    return True, None


def store_upload(name: str, data_b64: str) -> dict:
    """Decode a base64 upload, validate it, persist it, return its descriptor."""
    safe_name = Path(name).name or "fichier"
    try:
        raw = base64.b64decode(data_b64, validate=True)
    except Exception as exc:
        raise ValueError(f"contenu base64 illisible: {exc}") from exc
    ok, error = validate_size(safe_name, len(raw))
    if not ok:
        raise ValueError(error)
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    attachment_id = uuid.uuid4().hex[:12]
    target = ATTACHMENTS_DIR / f"{int(time.time())}-{attachment_id}-{safe_name}"
    target.write_bytes(raw)
    register_allowed(str(target), safe_name)
    return {
        "id": attachment_id,
        "name": safe_name,
        "path": str(target),
        "size_bytes": len(raw),
        "kind": "image" if is_image_name(safe_name) else "file",
    }


def describe_path(path: str) -> dict:
    """Validate an existing local file for direct attachment."""
    target = Path(path).expanduser()
    if not target.is_file():
        raise ValueError(f"fichier introuvable: {path}")
    size = target.stat().st_size
    ok, error = validate_size(target.name, size)
    if not ok:
        raise ValueError(error)
    register_allowed(str(target), target.name)
    return {
        "id": uuid.uuid4().hex[:12],
        "name": target.name,
        "path": str(target),
        "size_bytes": size,
        "kind": "image" if is_image_name(target.name) else "file",
    }
