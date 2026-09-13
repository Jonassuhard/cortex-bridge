"""Immutable, bounded transmission candidates. No transport or implicit approval.

Selection must come from the authorized project scope. Secret heuristics are
defense in depth, not a guarantee that arbitrary selected bytes are public.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import mimetypes
import os
from pathlib import Path
import re
import stat
import tempfile
import unicodedata
import zipfile

from orchestration.context import ContextPacketError, build_context_packet

MAX_ITEMS = 20
MAX_BYTES = 25 * 1024 * 1024
MAX_TOTAL = 50 * 1024 * 1024
_SECRET = re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:sk-[A-Za-z0-9_-]{20,})|(?:gh[pousr]_[A-Za-z0-9]{20,})")
_ASSIGNMENT = re.compile(rb"(?i)(?:password|passwd|api_key|access_token|client_secret)\s*[:=]\s*['\"]?[^\s'\"]{8,}")


class ArtifactError(ValueError):
    pass


def _parts(name: str) -> list[str]:
    if not isinstance(name, str) or not name or len(name) > 1024:
        raise ArtifactError("INVALID_PATH")
    if any(c in name for c in ("\\", ":", "\x00", "\n", "\r")):
        raise ArtifactError("INVALID_PATH")
    if any(unicodedata.category(c) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for c in name):
        raise ArtifactError("INVALID_PATH")
    parts = name.split("/")
    if any(not p or p.startswith(".") or p == ".." for p in parts):
        raise ArtifactError("PRIVATE_OR_INVALID_PATH")
    if any(p.lower() in {"node_modules", "credentials", "secrets", "id_rsa", "id_ed25519"} for p in parts):
        raise ArtifactError("PRIVATE_PATH")
    return parts


def _read_confined(root: Path, name: str, limit: int) -> bytes:
    """Open every component without following links; bound reads, including races."""
    parts = _parts(name)
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise ArtifactError("SAFE_OPEN_UNAVAILABLE")
    directory = None
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ArtifactError("NOT_REGULAR_FILE")
            if info.st_size > limit:
                raise ArtifactError("ARTIFACT_TOO_LARGE")
            data = handle.read(limit + 1)
            after = os.fstat(handle.fileno())
            if (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ArtifactError("FILE_CHANGED_DURING_READ")
            if len(data) > limit:
                raise ArtifactError("ARTIFACT_TOO_LARGE")
            return data
    except OSError as exc:
        raise ArtifactError("UNSAFE_OR_UNAVAILABLE_FILE") from exc
    finally:
        if directory is not None:
            os.close(directory)


def _inspect(data: bytes, *, archive: bool = False) -> None:
    if _SECRET.search(data) or _ASSIGNMENT.search(data):
        raise ArtifactError("POSSIBLE_SECRET")
    if archive:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                entries = z.infolist()
                if len(entries) > 200 or sum(x.file_size for x in entries) > MAX_TOTAL:
                    raise ArtifactError("ARCHIVE_TOO_LARGE")
                names = set()
                for item in entries:
                    _parts(item.filename.rstrip("/"))
                    if item.filename in names:
                        raise ArtifactError("DUPLICATE_ARCHIVE_MEMBER")
                    names.add(item.filename)
                    if item.flag_bits & 1 or stat.S_ISLNK(item.external_attr >> 16):
                        raise ArtifactError("UNSAFE_ARCHIVE_MEMBER")
                    if item.is_dir():
                        continue
                    if item.file_size > MAX_BYTES or item.file_size > max(1, item.compress_size) * 200:
                        raise ArtifactError("ARCHIVE_TOO_LARGE")
                    with z.open(item) as member:
                        payload = member.read(MAX_BYTES + 1)
                    if len(payload) > MAX_BYTES:
                        raise ArtifactError("ARCHIVE_TOO_LARGE")
                    if zipfile.is_zipfile(io.BytesIO(payload)):
                        raise ArtifactError("NESTED_ARCHIVE_UNSUPPORTED")
                    _inspect(payload)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
            raise ArtifactError("INVALID_ARCHIVE") from exc


@dataclass(frozen=True)
class Artifact:
    path: str
    data: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.data, bytes):
            raise ArtifactError("IMMUTABLE_BYTES_REQUIRED")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    def manifest(self) -> dict:
        return {"path": self.path, "bytes": len(self.data), "sha256": self.sha256,
                "mime": mimetypes.guess_type(self.path)[0] or "application/octet-stream",
                "delivery_state": "prepared", "available_to_brain": False}


def prepare(root: Path, paths: list[str]) -> tuple[Artifact, ...]:
    """Snapshot explicit selections; never mark a prepared item as delivered."""
    if not paths or len(paths) > MAX_ITEMS:
        raise ArtifactError("ITEM_COUNT")
    if len(paths) != len(set(paths)):
        raise ArtifactError("DUPLICATE_PATH")
    artifacts = []
    total = 0
    for name in paths:
        data = _read_confined(root, name, min(MAX_BYTES, MAX_TOTAL - total))
        _inspect(data, archive=name.lower().endswith(".zip") or zipfile.is_zipfile(io.BytesIO(data)))
        total += len(data)
        artifacts.append(Artifact(name, data))
    return tuple(artifacts)


def verify_sources(root: Path, manifest: dict) -> dict:
    """Compare selected current bytes with supplied metadata, without publication.

    This does not authenticate the manifest or prove delivery to the brain.
    Changes after the check remain possible; this is a point-in-time check.
    """
    if not isinstance(manifest, dict) or manifest.get("protocol") != "cortex-artifacts.v1":
        raise ArtifactError("INVALID_MANIFEST")
    items = manifest.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        raise ArtifactError("INVALID_MANIFEST")
    expected = []
    for item in items:
        if (not isinstance(item, dict) or not isinstance(item.get("path"), str)
                or type(item.get("bytes")) is not int or not 0 <= item["bytes"] <= MAX_BYTES
                or not isinstance(item.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None):
            raise ArtifactError("INVALID_MANIFEST")
        _parts(item["path"])
        expected.append({key: item[key] for key in ("path", "bytes", "sha256")})
    if sum(item["bytes"] for item in expected) > MAX_TOTAL:
        raise ArtifactError("ARTIFACT_TOO_LARGE")
    actual = prepare(root, [item["path"] for item in expected])
    for item, frozen in zip(actual, expected):
        if len(item.data) != frozen["bytes"] or item.sha256 != frozen["sha256"]:
            raise ArtifactError("STALE_SOURCE")
    revision = hashlib.sha256(json.dumps(expected, sort_keys=True,
                                        separators=(",", ":")).encode()).hexdigest()
    return {"state": "sources_match", "selection_sha256": revision,
            "checked_items": len(expected), "delivery_verified": False,
            "manifest_authenticated": False, "point_in_time_only": True}


def pack(artifacts: tuple[Artifact, ...]) -> bytes:
    """Package frozen bytes deterministically, without rereading source paths."""
    if not artifacts or len(artifacts) > MAX_ITEMS:
        raise ArtifactError("ITEM_COUNT")
    if len({item.path for item in artifacts}) != len(artifacts):
        raise ArtifactError("DUPLICATE_PATH")
    if sum(len(item.data) for item in artifacts) > MAX_TOTAL:
        raise ArtifactError("ARTIFACT_TOO_LARGE")
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_STORED) as bundle:
        for artifact in artifacts:
            _parts(artifact.path)
            if len(artifact.data) > MAX_BYTES:
                raise ArtifactError("ARTIFACT_TOO_LARGE")
            _inspect(artifact.data, archive=artifact.path.lower().endswith(".zip") or zipfile.is_zipfile(io.BytesIO(artifact.data)))
            item = zipfile.ZipInfo(artifact.path, date_time=(1980, 1, 1, 0, 0, 0))
            item.external_attr = 0o100600 << 16
            bundle.writestr(item, artifact.data)
    return result.getvalue()


def publish(output: Path, payload: bytes) -> None:
    """Publish complete bytes without replacing any existing final path.

    Caller supplies an authorized output directory. Staging files are retained
    if publication fails so they can be inspected; never treat them as receipts.
    """
    fd, staging = tempfile.mkstemp(prefix=".cortex-prepared-", dir=output.parent)
    with os.fdopen(fd, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.link(staging, output, follow_symlinks=False)
    # Retain staging (same inode) rather than performing any cleanup deletion.
    directory = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def inventory(root: Path, *, max_entries: int = 1000) -> dict:
    """Bounded metadata scan. No payload reads, selection approval or transport."""
    import time
    if type(max_entries) is not int or not 1 <= max_entries <= 10000:
        raise ArtifactError("INVALID_INVENTORY_LIMIT")
    if not hasattr(os, 'O_NOFOLLOW') or os.stat not in os.supports_dir_fd:
        raise ArtifactError("SAFE_OPEN_UNAVAILABLE")
    files, excluded, issues = [], [], set()
    visited = 0
    deadline = time.monotonic() + 5

    def walk(fd, prefix, depth):
        nonlocal visited
        if depth > 32:
            issues.add('depth_limit')
            return
        if time.monotonic() > deadline:
            issues.add('time_limit')
            return
        before = os.fstat(fd)
        names = []
        with os.scandir(fd) as entries:
            for entry in entries:
                if len(names) >= max_entries - visited:
                    issues.add('entry_limit')
                    break
                names.append(entry.name)
        for name in sorted(names):
            if visited >= max_entries or time.monotonic() > deadline:
                issues.add('entry_limit' if visited >= max_entries else 'time_limit')
                break
            visited += 1
            relative = prefix + name
            try:
                _parts(relative)
            except ArtifactError:
                printable = all(unicodedata.category(c) not in {'Cc', 'Cf', 'Cs', 'Zl', 'Zp'} for c in relative)
                excluded.append({'path': relative if printable else None, 'reason': 'private_or_invalid_path'})
                continue
            try:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    excluded.append({'path': relative, 'reason': 'symlink'})
                elif stat.S_ISREG(info.st_mode):
                    files.append({'path': relative, 'bytes': info.st_size})
                elif stat.S_ISDIR(info.st_mode):
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        opened = os.fstat(child)
                        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                            issues.add('directory_changed')
                        else:
                            walk(child, relative + '/', depth + 1)
                    finally:
                        os.close(child)
                else:
                    excluded.append({'path': relative, 'reason': 'not_regular_file'})
            except OSError:
                issues.add('unavailable_entry')
        after = os.fstat(fd)
        if (before.st_mtime_ns, before.st_ctime_ns) != (after.st_mtime_ns, after.st_ctime_ns):
            issues.add('directory_changed')
    try:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise ArtifactError("UNSAFE_OR_UNAVAILABLE_ROOT") from exc
    try:
        try:
            walk(fd, '', 0)
        except OSError:
            issues.add('unavailable_directory')
    finally:
        os.close(fd)
    return {'protocol': 'cortex-inventory.v1', 'files': sorted(files, key=lambda x: x['path']),
            'excluded': excluded, 'issues': sorted(issues), 'entries_observed': visited,
            'eligible_scan_complete': not issues, 'full_project_coverage': not issues and not excluded,
            'contents_read': False, 'delivery_verified': False, 'point_in_time_only': True,
            'limits': {'entries': max_entries, 'depth': 32, 'seconds': 5}}


def main() -> int:
    """Agent-facing packaging entry point; publication remains a separate step."""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--inventory", action="store_true", help="Read-only bounded relative file metadata")
    parser.add_argument("--inventory-limit", type=int, help="Maximum observed entries, 1..10000; inventory only")
    parser.add_argument("--file", action="append", dest="files")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-manifest", help="Relative manifest path within workspace; read-only freshness check")
    parser.add_argument("--goal", help="Include a supervisor context packet for this objective")
    args = parser.parse_args()
    try:
        if args.inventory:
            if args.files is not None or args.output is not None or args.goal is not None or args.verify_manifest is not None:
                raise ArtifactError("INCOMPATIBLE_ARGUMENTS")
            result = inventory(args.workspace, max_entries=args.inventory_limit if args.inventory_limit is not None else 1000)
            print(json.dumps(result))
            return 0 if result['eligible_scan_complete'] else 2
        if args.inventory_limit is not None:
            raise ArtifactError("INCOMPATIBLE_ARGUMENTS")
        if args.verify_manifest is not None:
            if args.files is not None or args.output is not None or args.goal is not None:
                raise ArtifactError("INCOMPATIBLE_ARGUMENTS")
            supplied = json.loads(_read_confined(args.workspace, args.verify_manifest, 1_000_000))
            print(json.dumps(verify_sources(args.workspace, supplied)))
            return 0
        if not args.files or args.output is None:
            raise ArtifactError("MISSING_PREPARATION_ARGUMENTS")
        items = prepare(args.workspace, args.files)
        payload = pack(items)
        manifest = {"protocol": "cortex-artifacts.v1", "delivery_state": "prepared",
                    "bundle_sha256": hashlib.sha256(payload).hexdigest(),
                    "bundle_bytes": len(payload),
                    "items": [item.manifest() for item in items]}
        if args.goal is not None:
            # Describe the same frozen bytes as the bundle, not a second read.
            # The existing packet contract keeps every attachment a proposal.
            manifest["context_packet"] = build_context_packet(
                goal=args.goal,
                available_context=[{
                    "kind": "file", "path": item.path,
                    "size_bytes": len(item.data), "sha256": item.sha256,
                    "reason": "Explicitly selected project context for the objective",
                } for item in items],
                missing_information=["Attachment delivery and content access are not yet verified"],
            )
        # Exclusive creation: never overwrite an artifact, existing user file,
        # or final-component symlink. Caller selects the authorized output dir.
        publish(args.output, payload)
        print(json.dumps(manifest))
        return 0
    except (ArtifactError, ContextPacketError, OSError, ValueError):
        # Do not expose absolute local paths in a supervisor-facing error.
        print(json.dumps({"error": "ARTIFACT_PREPARATION_FAILED", "delivery_state": "not_sent"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
