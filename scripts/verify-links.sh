#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OFFLINE=0

usage() {
  printf '%s\n' 'Usage: verify-links.sh [--root DIR] [--offline]'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      ROOT="$2"
      shift 2
      ;;
    --offline)
      OFFLINE=1
      shift
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

python3 - "$ROOT" "$OFFLINE" <<'PY'
from __future__ import annotations

import ipaddress
import re
import socket
import ssl
import string
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen


root = Path(sys.argv[1]).expanduser().resolve()
offline = sys.argv[2] == "1"
findings: set[tuple[str, str, int]] = set()
external_skipped = 0
external_checked = 0
checked_links = 0

MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)")
HTML_LINK_RE = re.compile(r"(?:href|src)\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
HTML_ANCHOR_RE = re.compile(r"(?:id|name)\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
SKIP_PARTS = {
    ".git",
    ".next",
    ".superpowers",
    ".venv",
    ".worktrees",
    "coverage",
    "node_modules",
    "playwright-report",
    "test-results",
}


def report(category: str, source: Path, line: int) -> None:
    findings.add((category, source.relative_to(root).as_posix(), line))


def slugify(heading: str) -> str:
    value = heading.strip().lower()
    value = "".join(ch for ch in value if ch not in string.punctuation or ch in "-_")
    value = re.sub(r"\s+", "-", value)
    return re.sub(r"-+", "-", value).strip("-")


def anchors_for(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()
    anchors = set(HTML_ANCHOR_RE.findall(text))
    if path.suffix.lower() in {".md", ".markdown"}:
        seen: dict[str, int] = {}
        for line in text.splitlines():
            match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
            if not match:
                continue
            base = slugify(match.group(1))
            count = seen.get(base, 0)
            seen[base] = count + 1
            anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


def unsafe_external(url: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if not host or host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        addresses = [item[4][0] for item in socket.getaddrinfo(host, parsed.port or 443)]
    except socket.gaierror:
        return False
    for raw in addresses:
        address = ipaddress.ip_address(raw)
        if not address.is_global:
            return True
    return False


def local_document_url(url: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_external(url: str, source: Path, line: int) -> None:
    global external_checked, external_skipped
    if offline or local_document_url(url):
        external_skipped += 1
        return
    if unsafe_external(url):
        report("unsafe_external_url", source, line)
        return
    request = Request(url, method="HEAD", headers={"User-Agent": "CortexBridgeLinkCheck/0.5"})
    try:
        with urlopen(request, timeout=12, context=ssl.create_default_context()) as response:
            if response.status >= 400:
                report("external_http_error", source, line)
                return
    except HTTPError as error:
        if error.code in {401, 403, 405}:
            fallback = Request(
                url,
                method="GET",
                headers={"User-Agent": "CortexBridgeLinkCheck/0.5", "Range": "bytes=0-0"},
            )
            try:
                with urlopen(fallback, timeout=12, context=ssl.create_default_context()) as response:
                    if response.status >= 400:
                        report("external_http_error", source, line)
                        return
            except HTTPError as fallback_error:
                if fallback_error.code in {401, 403}:
                    external_checked += 1
                    return
                report("external_unreachable", source, line)
                return
            except (URLError, TimeoutError):
                report("external_unreachable", source, line)
                return
        else:
            report("external_http_error", source, line)
            return
    except (URLError, TimeoutError):
        report("external_unreachable", source, line)
        return
    external_checked += 1


documents = sorted(
    path
    for path in root.rglob("*")
    if path.is_file()
    and path.suffix.lower() in {".md", ".markdown", ".html", ".htm"}
    and not (set(path.relative_to(root).parts) & SKIP_PARTS)
    and path.relative_to(root).parts[:2] != ("frontend", "out")
)

for source in documents:
    text = source.read_text(encoding="utf-8")
    for line_number, line_text in enumerate(text.splitlines(), start=1):
        refs = MARKDOWN_LINK_RE.findall(line_text) + HTML_LINK_RE.findall(line_text)
        for raw_ref in refs:
            checked_links += 1
            ref = raw_ref.strip().strip("<>")
            if not ref or ref.startswith(("mailto:", "tel:", "data:", "javascript:")):
                continue
            if ref.startswith(("https://", "http://")):
                check_external(ref, source, line_number)
                continue
            parsed = urlsplit(ref)
            relative_path = unquote(parsed.path)
            target = source if not relative_path else (source.parent / relative_path)
            resolved = target.resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                report("outside_root", source, line_number)
                continue
            if not resolved.exists():
                report("missing_target", source, line_number)
                continue
            if parsed.fragment and resolved.is_file():
                fragment = unquote(parsed.fragment)
                if fragment not in anchors_for(resolved):
                    report("missing_anchor", source, line_number)

for category, relative, line in sorted(findings):
    print(f"[links] {category} {relative}:{line}")

if findings:
    print(
        f"[links] FAILED findings={len(findings)} checked={checked_links} "
        f"external_checked={external_checked} external_skipped={external_skipped}"
    )
    raise SystemExit(1)

print(
    f"[links] PASS checked={checked_links} external_checked={external_checked} "
    f"external_skipped={external_skipped}"
)
PY
