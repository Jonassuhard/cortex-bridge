#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MARKERS="${CORTEX_PRIVACY_MARKERS_FILE:-}"
URL_ALLOWLIST="${CORTEX_PUBLIC_URL_ALLOWLIST_FILE:-}"

usage() {
  printf '%s\n' \
    'Usage: check-public-privacy.sh --markers FILE --url-allowlist FILE [--root DIR]' \
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

python3 - "$ROOT" "$MARKERS" "$URL_ALLOWLIST" <<'PY'
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote


root = Path(sys.argv[1]).expanduser().resolve()
markers_path = Path(sys.argv[2]).expanduser().resolve() if sys.argv[2] else None
allowlist_path = Path(sys.argv[3]).expanduser().resolve() if sys.argv[3] else None
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
excluded_controls = {
    path for path in (markers_path, allowlist_path) if path is not None
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


URL_RE = re.compile(r"https?://[^\s<>\"'\)\]]+", re.IGNORECASE)
PRIVATE_PATH_RE = re.compile(
    r"(?:file:/{2,3})?/(?:users|home|volumes)/[^\s<>\"']+",
    re.IGNORECASE,
)


def decoded_variants(text: str) -> tuple[str, ...]:
    once = unquote(text)
    twice = unquote(once)
    return tuple(dict.fromkeys((text, once, twice)))


def scan_text(
    text: str,
    relative: str,
    forced_category: str | None = None,
    enforce_url_allowlist: bool = True,
) -> None:
    lower_text = text.casefold()
    for marker in markers:
        if marker.casefold() in lower_text:
            line = lower_text[: lower_text.index(marker.casefold())].count("\n") + 1
            report(forced_category or "private_marker", relative, line)
    for variant in decoded_variants(text):
        match = PRIVATE_PATH_RE.search(variant)
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
    scan_text(text, relative, enforce_url_allowlist=not lockfile)


def resolve_tool(env_name: str, fallback: str) -> str | None:
    candidate = os.environ.get(env_name, fallback)
    if os.path.sep in candidate:
        path = Path(candidate)
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(candidate)


if images:
    exiftool = resolve_tool("EXIFTOOL_BIN", "exiftool")
    tesseract = resolve_tool("TESSERACT_BIN", "tesseract")
    if not exiftool:
        report("missing_image_tool", "exiftool")
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
    if exiftool:
        for image in images:
            relative = image.relative_to(root).as_posix()
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
                ocr = subprocess.run(
                    [tesseract, str(image), "stdout", "-l", "eng+fra"],
                    text=True,
                    capture_output=True,
                    timeout=30,
                )
                if ocr.returncode != 0:
                    report("image_tool_failure", relative)
                else:
                    scan_text(ocr.stdout, relative, forced_category="image_ocr")


for category, relative, line in sorted(findings):
    print(f"[privacy] {category} {relative}:{line}")

if findings:
    print(f"[privacy] FAILED findings={len(findings)}")
    raise SystemExit(1)

print(f"[privacy] PASS files={len(text_files) + len(images)} images={len(images)}")
PY
