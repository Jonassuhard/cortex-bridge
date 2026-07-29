#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MARKERS="${CORTEX_PRIVACY_MARKERS_FILE:-}"
URL_ALLOWLIST="${CORTEX_PUBLIC_URL_ALLOWLIST_FILE:-}"
FINGERPRINTS="${CORTEX_PRIVACY_FINGERPRINTS_FILE:-}"

usage() {
  printf '%s\n' \
    'Usage: check-public-privacy.sh --markers FILE --fingerprints FILE --url-allowlist FILE [--root DIR]' \
    '' \
    'The marker file is owner-supplied and must contain at least one non-comment line.' \
    'Findings print only category, relative path, and line number.'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      ROOT="$2"
      shift 2
      ;;
    --markers)
      MARKERS="$2"
      shift 2
      ;;
    --url-allowlist)
      URL_ALLOWLIST="$2"
      shift 2
      ;;
    --fingerprints)
      FINGERPRINTS="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

python3 - "$ROOT" "$MARKERS" "$URL_ALLOWLIST" "$FINGERPRINTS" <<'PY'
from __future__ import annotations

import os
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path
from urllib.parse import unquote


root = Path(sys.argv[1]).expanduser().resolve()
markers_path = Path(sys.argv[2]).expanduser().resolve() if sys.argv[2] else None
allowlist_path = Path(sys.argv[3]).expanduser().resolve() if sys.argv[3] else None
fingerprints_path = Path(sys.argv[4]).expanduser().resolve() if sys.argv[4] else None
findings: set[tuple[str, str, int]] = set()


def report(category: str, relative: str, line: int = 0) -> None:
    findings.add((category, relative, line))


def read_control(path: Path | None, category: str, require_value: bool) -> list[str]:
    if path is None or not path.is_file():
        report(category, "control")
        return []
    values = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if require_value and not values:
        report(category, "control")
    return values


markers = read_control(markers_path, "marker_config", require_value=True)
allowed_urls = set(read_control(allowlist_path, "url_allowlist_config", require_value=False))
if fingerprints_path is None or not fingerprints_path.is_file():
    report("fingerprint_config", "control")
    fingerprints: list[dict[str, object]] = []
else:
    try:
        loaded_fingerprints = json.loads(fingerprints_path.read_text(encoding="utf-8"))
        if not isinstance(loaded_fingerprints, list):
            raise ValueError("fingerprints must be a list")
        fingerprints = []
        for item in loaded_fingerprints:
            if not isinstance(item, dict):
                raise ValueError("fingerprint entries must be objects")
            length = item.get("length")
            digest = item.get("sha256")
            category = item.get("category")
            if (
                not isinstance(length, int)
                or length < 1
                or not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or not isinstance(category, str)
                or not category.strip()
            ):
                raise ValueError("invalid fingerprint entry")
            fingerprints.append(item)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        report("fingerprint_config", "control")
        fingerprints = []
excluded_controls = {
    path for path in (markers_path, allowlist_path, fingerprints_path) if path is not None
}


def listed_files() -> list[Path]:
    inside_git = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0
    if inside_git:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            check=True,
            capture_output=True,
        )
        paths = [root / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]
    else:
        paths = [
            item
            for item in root.rglob("*")
            if item.is_file() and ".git" not in item.relative_to(root).parts
        ]
    return sorted(
        path
        for path in paths
        if path.resolve() not in excluded_controls and path.is_file()
    )


URL_RE = re.compile(r"https?://[^\s<>\"'`\)\]]+", re.IGNORECASE)
PRIVATE_PATH_RE = re.compile(
    r"(?:file:/{2,3})?/(?:users|home|volumes)/[^\s<>\"']+",
    re.IGNORECASE,
)


def decoded_variants(text: str) -> tuple[str, ...]:
    once = unquote(text)
    twice = unquote(once)
    return tuple(dict.fromkeys((text, once, twice)))


def normalized_privacy_text(text: str) -> str:
    decoded = text
    for _ in range(3):
        previous = decoded
        decoded = re.sub(
            r"\\u\{([0-9a-f]{1,6})\}",
            lambda match: chr(int(match.group(1), 16)),
            decoded,
            flags=re.IGNORECASE,
        )
        decoded = re.sub(
            r"\\u([0-9a-f]{4})",
            lambda match: chr(int(match.group(1), 16)),
            decoded,
            flags=re.IGNORECASE,
        )
        decoded = re.sub(
            r"\\x([0-9a-f]{2})",
            lambda match: chr(int(match.group(1), 16)),
            decoded,
            flags=re.IGNORECASE,
        )
        decoded = unquote(decoded.replace("+", " "))
        if decoded == previous:
            break
    return decoded.casefold()


def fingerprint_categories(text: str) -> set[str]:
    if not fingerprints:
        return set()
    normalized = normalized_privacy_text(text)
    lengths = {int(item["length"]) for item in fingerprints}
    fingerprints_by_key = {
        (int(item["length"]), str(item["sha256"])): str(item["category"])
        for item in fingerprints
    }
    categories: set[str] = set()
    tokens = re.findall(r"[\w.@+-]+", normalized, flags=re.UNICODE)
    for token in tokens:
        characters = list(token)
        for length in lengths:
            for index in range(0, len(characters) - length + 1):
                digest = hashlib.sha256(
                    "".join(characters[index : index + length]).encode("utf-8")
                ).hexdigest()
                category = fingerprints_by_key.get((length, digest))
                if category:
                    categories.add(category)
    for length in (value for value in lengths if value > 12):
        characters = list(normalized)
        for index in range(0, len(characters) - length + 1):
            digest = hashlib.sha256(
                "".join(characters[index : index + length]).encode("utf-8")
            ).hexdigest()
            category = fingerprints_by_key.get((length, digest))
            if category:
                categories.add(category)
    return categories


def scan_text(
    text: str,
    relative: str,
    forced_category: str | None = None,
    enforce_url_allowlist: bool = True,
    scan_fingerprints: bool = True,
    scan_private_paths: bool = True,
) -> None:
    lower_text = text.casefold()
    if scan_fingerprints:
        for category in fingerprint_categories(text):
            safe_category = re.sub(r"[^a-z0-9]+", "_", category.casefold()).strip("_")
            report(forced_category or f"private_fingerprint_{safe_category}", relative, 0)
    for marker in markers:
        if marker.casefold() in lower_text:
            line = lower_text[: lower_text.index(marker.casefold())].count("\n") + 1
            report(forced_category or "private_marker", relative, line)
    for variant in decoded_variants(text):
        match = PRIVATE_PATH_RE.search(variant) if scan_private_paths else None
        if match:
            line = variant[: match.start()].count("\n") + 1
            report(forced_category or "private_path", relative, line)
        for url_match in URL_RE.finditer(variant):
            url = url_match.group(0).rstrip(".,;:!?")
            if enforce_url_allowlist and url not in allowed_urls:
                line = variant[: url_match.start()].count("\n") + 1
                report(forced_category or "unapproved_url", relative, line)


def image_kind(blob: bytes) -> str | None:
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if blob.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if blob.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if blob.startswith(b"RIFF") and blob[8:12] == b"WEBP":
        return "webp"
    return None


def embedded_metadata(blob: bytes, kind: str) -> list[str]:
    payloads: list[bytes] = []
    if kind == "png":
        offset = 8
        while offset + 12 <= len(blob):
            size = int.from_bytes(blob[offset : offset + 4], "big")
            chunk_type = blob[offset + 4 : offset + 8]
            start = offset + 8
            end = start + size
            if end + 4 > len(blob):
                break
            payload = blob[start:end]
            if chunk_type in {b"tEXt", b"iTXt", b"eXIf"}:
                payloads.append(payload)
            elif chunk_type == b"zTXt":
                try:
                    keyword, compressed = payload.split(b"\0", 1)
                    payloads.extend((keyword, zlib.decompress(compressed[1:])))
                except (ValueError, zlib.error):
                    payloads.append(payload)
            offset = end + 4
    elif kind == "jpeg":
        offset = 2
        while offset + 4 <= len(blob):
            if blob[offset] != 0xFF:
                offset += 1
                continue
            marker = blob[offset + 1]
            offset += 2
            if marker in {0xD8, 0xD9}:
                continue
            if marker == 0xDA:
                break
            size = int.from_bytes(blob[offset : offset + 2], "big")
            if size < 2 or offset + size > len(blob):
                break
            if marker == 0xFE or 0xE0 <= marker <= 0xEF:
                payloads.append(blob[offset + 2 : offset + size])
            offset += size
    elif kind == "webp":
        offset = 12
        while offset + 8 <= len(blob):
            chunk_type = blob[offset : offset + 4]
            size = int.from_bytes(blob[offset + 4 : offset + 8], "little")
            start = offset + 8
            end = start + size
            if end > len(blob):
                break
            if chunk_type in {b"EXIF", b"XMP ", b"ICCP"}:
                payloads.append(blob[start:end])
            offset = end + (size % 2)
    elif kind == "gif":
        # Comment and application extensions are uncompressed. Raster text is
        # LZW-compressed and therefore cannot be mistaken for metadata here.
        offset = 13
        while offset + 2 <= len(blob):
            if blob[offset] != 0x21:
                offset += 1
                continue
            label = blob[offset + 1]
            offset += 2
            blocks: list[bytes] = []
            while offset < len(blob):
                size = blob[offset]
                offset += 1
                if size == 0:
                    break
                blocks.append(blob[offset : offset + size])
                offset += size
            joined = b"".join(blocks)
            if label == 0xFE or (label == 0xFF and not joined.startswith(b"NETSCAPE2.0")):
                payloads.append(joined)

    metadata: list[str] = []
    for payload in payloads:
        try:
            metadata.append(payload.decode("utf-8"))
        except UnicodeDecodeError:
            metadata.append(payload.decode("latin-1", errors="ignore"))
    return metadata


text_files: list[tuple[Path, str]] = []
images: list[Path] = []
for path in listed_files():
    relative = path.relative_to(root).as_posix()
    blob = path.read_bytes()
    kind = image_kind(blob)
    if kind:
        images.append(path)
        continue
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        report("unknown_public_binary", relative)
        continue
    if "\x00" in text:
        report("unknown_public_binary", relative)
        continue
    text_files.append((path, text))
    lockfile = Path(relative).name in {
        "package-lock.json",
        "npm-shrinkwrap.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "requirements.lock",
        "poetry.lock",
        "Pipfile.lock",
        "uv.lock",
    }
    public_navigation_document = Path(relative).suffix.lower() in {".md", ".markdown"}
    scan_text(
        text,
        relative,
        enforce_url_allowlist=public_navigation_document and not lockfile,
        scan_fingerprints=not lockfile,
        scan_private_paths=relative != "tests/test_public_privacy.py",
    )


def resolve_tool(env_name: str, fallback: str) -> str | None:
    candidate = os.environ.get(env_name, fallback)
    if os.path.sep in candidate:
        path = Path(candidate)
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(candidate)


if images:
    exiftool = resolve_tool("EXIFTOOL_BIN", "exiftool")
    ffmpeg = resolve_tool("FFMPEG_BIN", "ffmpeg")
    tesseract = resolve_tool("TESSERACT_BIN", "tesseract")
    if not tesseract:
        report("missing_image_tool", "tesseract-eng-fra")
    ocr_ready = False
    if tesseract:
        languages = subprocess.run(
            [tesseract, "--list-langs"],
            text=True,
            capture_output=True,
            timeout=20,
        )
        installed_languages = {
            line.strip() for line in languages.stdout.splitlines() if line.strip()
        }
        ocr_ready = languages.returncode == 0 and {"eng", "fra"}.issubset(installed_languages)
        if not ocr_ready:
            report("missing_image_tool", "tesseract-eng-fra")
    for image in images:
        relative = image.relative_to(root).as_posix()
        blob = image.read_bytes()
        kind = image_kind(blob)
        for metadata_text in embedded_metadata(blob, kind or ""):
            scan_text(metadata_text, relative, forced_category="image_metadata")
        if exiftool:
            metadata = subprocess.run(
                [exiftool, "-j", "-a", "-G1", "-s", str(image)],
                text=True,
                capture_output=True,
                timeout=20,
            )
            if metadata.returncode != 0:
                report("image_tool_failure", relative)
            else:
                scan_text(metadata.stdout, relative, forced_category="image_metadata")
        if ocr_ready and tesseract:
            with tempfile.TemporaryDirectory(prefix="cortex-privacy-ocr-") as temp_dir:
                targets = [image]
                if kind == "gif":
                    if not ffmpeg:
                        report("missing_image_tool", "ffmpeg-animated-gif")
                        continue
                    frame_pattern = Path(temp_dir) / "frame-%06d.png"
                    extraction = subprocess.run(
                        [
                            ffmpeg,
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-i",
                            str(image),
                            str(frame_pattern),
                        ],
                        text=True,
                        capture_output=True,
                        timeout=60,
                    )
                    targets = sorted(Path(temp_dir).glob("frame-*.png"))
                    if extraction.returncode != 0 or not targets:
                        report("image_tool_failure", relative)
                        continue
                for target in targets:
                    ocr = subprocess.run(
                        [tesseract, str(target), "stdout", "-l", "eng+fra"],
                        text=True,
                        capture_output=True,
                        timeout=30,
                    )
                    if ocr.returncode != 0:
                        report("image_tool_failure", relative)
                        break
                    scan_text(ocr.stdout, relative, forced_category="image_ocr")


for category, relative, line in sorted(findings):
    print(f"[privacy] {category} {relative}:{line}")

if findings:
    print(f"[privacy] FAILED findings={len(findings)}")
    raise SystemExit(1)

print(f"[privacy] PASS files={len(text_files) + len(images)} images={len(images)}")
PY
