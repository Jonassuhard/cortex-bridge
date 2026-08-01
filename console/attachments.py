"""Validated attachment intake with opaque, expiring access tokens."""

from __future__ import annotations

import base64
import codecs
import io
import json
import secrets
import stat
import time
import uuid
import zipfile
from pathlib import Path

from transport.chatgpt_web.adapter import MAX_FILE_BYTES, MAX_IMAGE_BYTES
from cortex_paths import build_paths

RUNTIME_PATHS = build_paths()
DATA_DIR = RUNTIME_PATHS.home
ATTACHMENTS_DIR = RUNTIME_PATHS.attachments
TOKEN_TTL_SECONDS = 15 * 60
OWNER = "cortex-bridge"

_TOKENS: dict[str, dict] = {}

_MIME_BY_EXTENSION = {
    ".png": ("image/png", "image"),
    ".jpg": ("image/jpeg", "image"),
    ".jpeg": ("image/jpeg", "image"),
    ".gif": ("image/gif", "image"),
    ".webp": ("image/webp", "image"),
    ".pdf": ("application/pdf", "file"),
    ".txt": ("text/plain", "file"),
    ".json": ("application/json", "file"),
    ".csv": ("text/csv", "file"),
    ".md": ("text/markdown", "file"),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "file",
    ),
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "file",
    ),
    ".pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "file",
    ),
}

_OFFICE_MEMBER = {
    ".docx": "word/document.xml",
    ".xlsx": "xl/workbook.xml",
    ".pptx": "ppt/presentation.xml",
}

_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def _mib(size: int) -> str:
    return f"{size / (1024 * 1024):.0f}"


def sanitize_filename(name: str) -> str:
    cleaned = "".join(
        character
        for character in str(name)
        if ord(character) >= 32 and ord(character) != 127
    )
    cleaned = cleaned.replace("\\", "/").rsplit("/", 1)[-1].strip()
    cleaned = cleaned.strip(". ")
    if not cleaned:
        raise ValueError("Le nom du fichier est vide ou invalide.")
    if cleaned.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
        raise ValueError(f"« {cleaned} » est un nom de fichier réservé.")
    return cleaned


def _looks_like_utf8(data: bytes) -> bool:
    try:
        decoder = codecs.getincrementaldecoder("utf-8")("strict")
        decoder.decode(data, final=False)
        return True
    except UnicodeDecodeError:
        return False


def _zip_members(source: bytes | Path) -> set[str]:
    try:
        target = io.BytesIO(source) if isinstance(source, bytes) else source
        with zipfile.ZipFile(target) as archive:
            return set(archive.namelist())
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("Le fichier Office n'est pas une archive ZIP valide.") from exc


def _classify(name: str, sample: bytes, *, office_source: bytes | Path | None = None) -> tuple[str, str]:
    extension = Path(name).suffix.lower()
    expected = _MIME_BY_EXTENSION.get(extension)
    if expected is None:
        raise ValueError(f"Le type de fichier « {extension or 'sans extension'} » n'est pas accepté.")
    mime, kind = expected

    signatures = {
        ".png": sample.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": sample.startswith(b"\xff\xd8\xff"),
        ".jpeg": sample.startswith(b"\xff\xd8\xff"),
        ".gif": sample.startswith((b"GIF87a", b"GIF89a")),
        ".webp": sample.startswith(b"RIFF") and sample[8:12] == b"WEBP",
        ".pdf": sample.startswith(b"%PDF"),
    }
    if extension in signatures and not signatures[extension]:
        raise ValueError(f"Le contenu de « {name} » ne correspond pas à son extension.")

    if extension in {".txt", ".json", ".csv", ".md"}:
        if not _looks_like_utf8(sample):
            raise ValueError(f"« {name} » n'est pas un fichier texte UTF-8 valide.")
        stripped = sample.lstrip()
        if extension == ".json" and stripped[:1] not in {b"{", b"["}:
            raise ValueError(f"« {name} » n'est pas un document JSON valide.")

    required_member = _OFFICE_MEMBER.get(extension)
    if required_member:
        if office_source is None:
            raise ValueError("Le contenu Office ne peut pas être vérifié.")
        members = _zip_members(office_source)
        if "[Content_Types].xml" not in members or required_member not in members:
            raise ValueError(f"Le contenu de « {name} » ne correspond pas à son extension Office.")
    return mime, kind


def _validate_size(kind: str, size: int) -> None:
    limit = MAX_IMAGE_BYTES if kind == "image" else MAX_FILE_BYTES
    if size <= limit:
        return
    noun = "image" if kind == "image" else "fichier"
    suffix = "envoyée" if kind == "image" else "envoyé"
    raise ValueError(
        f"Ce {noun} fait {_mib(size)} Mo. La limite est de {_mib(limit)} Mo. "
        f"Il n'a pas été {suffix}."
    )


def is_image_name(name: str) -> bool:
    expected = _MIME_BY_EXTENSION.get(Path(name).suffix.lower())
    return bool(expected and expected[1] == "image")


def validate_size(name: str, size: int) -> tuple[bool, str | None]:
    try:
        _validate_size("image" if is_image_name(name) else "file", size)
    except ValueError as exc:
        return False, str(exc)
    return True, None


def _register(descriptor: dict) -> str:
    token = secrets.token_urlsafe(24)
    _TOKENS[token] = {
        **descriptor,
        "expires_at": time.time() + TOKEN_TTL_SECONDS,
    }
    return token


def resolve_token(token: str) -> dict | None:
    descriptor = _TOKENS.get(token)
    if descriptor is None:
        return None
    if descriptor.get("owner") != OWNER or descriptor.get("expires_at", 0) <= time.time():
        _TOKENS.pop(token, None)
        return None
    path = Path(str(descriptor.get("path", "")))
    try:
        mode = path.lstat().st_mode
    except OSError:
        return None
    if path.is_symlink() or not stat.S_ISREG(mode):
        return None
    return dict(descriptor)


def restore_descriptor(descriptor: dict) -> str:
    """Re-register a persisted non-terminal descriptor after a restart."""
    required = {
        "token",
        "owner",
        "name",
        "path",
        "size_bytes",
        "mime",
        "kind",
    }
    if not required.issubset(descriptor) or descriptor.get("owner") != OWNER:
        raise ValueError("Le descripteur de pièce jointe persisté est incomplet.")
    token = str(descriptor["token"])
    if not token or "/" in token or "\\" in token:
        raise ValueError("Le token de pièce jointe persisté est invalide.")
    path = Path(str(descriptor["path"]))
    if path.is_symlink():
        raise ValueError("Le descripteur persisté pointe vers un lien symbolique.")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError("La pièce jointe persistée est introuvable.") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != descriptor["size_bytes"]:
        raise ValueError("La pièce jointe persistée a changé sur disque.")
    with path.open("rb") as handle:
        sample = handle.read(65536)
    office_source = path if path.suffix.lower() in _OFFICE_MEMBER else None
    mime, kind = _classify(str(descriptor["name"]), sample, office_source=office_source)
    if mime != descriptor["mime"] or kind != descriptor["kind"]:
        raise ValueError("Le type de la pièce jointe persistée a changé.")
    _TOKENS[token] = {
        **descriptor,
        "expires_at": time.time() + TOKEN_TTL_SECONDS,
    }
    return token


def _descriptor(path: Path, name: str, size: int, mime: str, kind: str) -> dict:
    descriptor = {
        "id": uuid.uuid4().hex[:12],
        "owner": OWNER,
        "name": name,
        "path": str(path),
        "size_bytes": size,
        "mime": mime,
        "kind": kind,
    }
    descriptor["token"] = _register(descriptor)
    return descriptor


def store_upload(name: str, data_b64: str) -> dict:
    safe_name = sanitize_filename(name)
    try:
        raw = base64.b64decode(data_b64, validate=True)
    except Exception as exc:
        raise ValueError(f"contenu base64 illisible: {exc}") from exc
    mime, kind = _classify(safe_name, raw[:65536], office_source=raw)
    _validate_size(kind, len(raw))
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    target = ATTACHMENTS_DIR / (
        f"cortex-attachment-{int(time.time())}-{uuid.uuid4().hex[:12]}-{safe_name}"
    )
    target.write_bytes(raw)
    return _descriptor(target, safe_name, len(raw), mime, kind)


def describe_path(path: str) -> dict:
    target = Path(path).expanduser()
    if target.is_symlink():
        raise ValueError("Les liens symboliques ne sont pas acceptés comme pièce jointe.")
    try:
        metadata = target.lstat()
    except OSError as exc:
        raise ValueError(f"fichier introuvable: {path}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"fichier régulier introuvable: {path}")
    safe_name = sanitize_filename(target.name)
    with target.open("rb") as handle:
        sample = handle.read(65536)
    extension = target.suffix.lower()
    office_source = target if extension in _OFFICE_MEMBER else None
    mime, kind = _classify(safe_name, sample, office_source=office_source)
    _validate_size(kind, metadata.st_size)
    return _descriptor(target.resolve(), safe_name, metadata.st_size, mime, kind)


def _remove_owned_screenshot(path: Path) -> None:
    try:
        owned_parent = path.parent.resolve() == ATTACHMENTS_DIR.resolve()
    except OSError:
        owned_parent = False
    if owned_parent and path.name.startswith("cortex-screenshot-") and not path.is_symlink():
        path.unlink(missing_ok=True)


def describe_screenshot(path: str, *, expected_path: str) -> dict:
    target = Path(path)
    expected = Path(expected_path)
    try:
        if target.resolve(strict=False) != expected.resolve(strict=False):
            raise ValueError("Le pilote a produit la capture dans une cible inattendue.")
        if target.is_symlink():
            raise ValueError("Les liens symboliques ne sont pas acceptés comme capture.")
        metadata = target.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("La capture n'est pas un fichier régulier.")
        with target.open("rb") as handle:
            signature = handle.read(8)
        if signature != b"\x89PNG\r\n\x1a\n":
            raise ValueError("La capture produite n'est pas un PNG valide.")
        _validate_size("image", metadata.st_size)
    except (OSError, ValueError) as exc:
        _remove_owned_screenshot(target)
        if isinstance(exc, ValueError):
            raise
        raise ValueError("La capture d'écran est introuvable.") from exc
    return _descriptor(target.resolve(), target.name, metadata.st_size, "image/png", "image")


def cleanup_abandoned(preserve: set[str]) -> list[str]:
    """Delete unreferenced Cortex-owned staged files, never arbitrary files."""
    if not ATTACHMENTS_DIR.is_dir():
        return []
    preserved = {str(Path(path).resolve()) for path in preserve}
    deleted: list[str] = []
    for candidate in sorted(ATTACHMENTS_DIR.iterdir()):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        if not candidate.name.startswith(("cortex-attachment-", "cortex-screenshot-")):
            continue
        if str(candidate.resolve()) in preserved:
            continue
        candidate.unlink()
        deleted.append(str(candidate))
    return deleted
