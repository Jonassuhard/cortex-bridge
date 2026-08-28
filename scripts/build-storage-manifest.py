#!/usr/bin/env python3
"""Build a deterministic, privacy-safe inventory of Cortex Bridge storage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
import sys
from pathlib import Path


EXCLUDED_PARTS = {".git", ".venv", "__pycache__", "node_modules"}
EXCLUDED_TOP_LEVEL = {"00_INDEX", "50_CACHE_REBUILDABLE", "99_QUARANTINE"}
DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)


def sha256_file(
    path: Path,
    *,
    expected_device: int | None = None,
    expected_inode: int | None = None,
    file_fd: int | None = None,
) -> tuple[str, int]:
    digest = hashlib.sha256()
    owns_fd = file_fd is None
    fd = os.open(path, FILE_FLAGS) if file_fd is None else os.dup(file_fd)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"manifest input is not a regular file: {path}")
        if expected_device is not None and before.st_dev != expected_device:
            raise ValueError(f"manifest input is on a different filesystem: {path}")
        if expected_inode is not None and before.st_ino != expected_inode:
            raise ValueError(f"manifest input changed before hashing: {path}")
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after:
        raise ValueError(f"manifest input changed while hashing: {path}")
    if owns_fd:
        try:
            current = path.stat(follow_symlinks=False)
        except OSError as error:
            raise ValueError(f"manifest input changed while hashing: {path}") from error
        identity_current = (
            current.st_dev,
            current.st_ino,
            current.st_size,
            current.st_mtime_ns,
        )
        if identity_before != identity_current:
            raise ValueError(f"manifest input changed while hashing: {path}")
    return digest.hexdigest(), before.st_size


def classify(relative: Path) -> tuple[str, bool, str, str, str]:
    top_level = relative.parts[0]
    if top_level == "10_SOURCE":
        return "active", True, "source", "while-active", "internal"
    if top_level == "30_EVIDENCE":
        return "evidence", False, "evidence", "release-history", "internal"
    if top_level == "90_ARCHIVES":
        return "archived", False, "archive", "indefinite", "internal"
    return "active", False, "artifact", "while-active", "internal"


def inspect_lexical_root(requested_root: Path) -> tuple[Path, os.stat_result]:
    """Return a non-symlinked absolute root path and its initial identity."""
    expanded_root = requested_root.expanduser()
    lexical_root = expanded_root if expanded_root.is_absolute() else Path.cwd() / expanded_root
    current = Path(lexical_root.anchor)
    details: os.stat_result | None = None
    for part in lexical_root.parts[1:]:
        if part == ".":
            continue
        if part == "..":
            current = current.parent
            continue
        current /= part
        details = current.stat(follow_symlinks=False)
        if stat.S_ISLNK(details.st_mode):
            raise ValueError(
                f"storage root is unsafe: symlink component: {current}"
            )
    if details is None:
        details = current.stat(follow_symlinks=False)
    if not stat.S_ISDIR(details.st_mode):
        raise ValueError(f"storage root is not a directory: {current}")
    return current, details


def assert_root_identity(root: Path, expected_root: os.stat_result) -> None:
    """Fail if the lexical root now names anything other than the pinned root."""
    current_root, current_details = inspect_lexical_root(root)
    if current_root != root or (
        current_details.st_dev,
        current_details.st_ino,
    ) != (
        expected_root.st_dev,
        expected_root.st_ino,
    ):
        raise ValueError(f"storage root changed during manifest generation: {root}")


def _iter_manifest_entries(
    root: Path,
    *,
    root_fd: int | None = None,
    expected_root_device: int | None = None,
    expected_root_inode: int | None = None,
):
    owns_root_fd = root_fd is None
    traversal_fd = os.open(root, DIRECTORY_FLAGS) if root_fd is None else os.dup(root_fd)
    root_details = os.fstat(traversal_fd)
    if not stat.S_ISDIR(root_details.st_mode):
        os.close(traversal_fd)
        raise ValueError(f"manifest root is not a directory: {root}")
    if (
        (expected_root_device is not None and root_details.st_dev != expected_root_device)
        or (expected_root_inode is not None and root_details.st_ino != expected_root_inode)
    ):
        os.close(traversal_fd)
        raise ValueError(f"manifest root changed before traversal: {root}")
    root_device = root_details.st_dev

    def visit(directory_fd: int, relative_directory: Path):
        with os.scandir(directory_fd) as scanner:
            entries = sorted(scanner, key=lambda item: item.name)
        for entry in entries:
            relative = relative_directory / entry.name
            path = root / relative
            try:
                details = os.stat(
                    entry.name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            except OSError as error:
                raise ValueError(
                    f"manifest path changed before traversal: {relative.as_posix()}"
                ) from error
            if details.st_dev != root_device:
                raise ValueError(
                    f"manifest path is on a different filesystem: {relative.as_posix()}"
                )
            if stat.S_ISLNK(details.st_mode):
                raise ValueError(f"symlink escapes storage root: {relative.as_posix()}")
            if relative.parts[0] in EXCLUDED_TOP_LEVEL:
                continue
            if any(part in EXCLUDED_PARTS for part in relative.parts):
                continue
            if stat.S_ISDIR(details.st_mode):
                try:
                    child_fd = os.open(entry.name, DIRECTORY_FLAGS, dir_fd=directory_fd)
                except OSError as error:
                    raise ValueError(
                        f"manifest directory changed before traversal: {relative.as_posix()}"
                    ) from error
                try:
                    opened = os.fstat(child_fd)
                    if (
                        not stat.S_ISDIR(opened.st_mode)
                        or opened.st_dev != root_device
                        or (opened.st_dev, opened.st_ino)
                        != (details.st_dev, details.st_ino)
                    ):
                        raise ValueError(
                            "manifest directory changed before traversal: "
                            f"{relative.as_posix()}"
                        )
                    yield from visit(child_fd, relative)
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(details.st_mode):
                try:
                    file_fd = os.open(entry.name, FILE_FLAGS, dir_fd=directory_fd)
                except OSError as error:
                    raise ValueError(
                        f"manifest input changed before hashing: {relative.as_posix()}"
                    ) from error
                try:
                    opened = os.fstat(file_fd)
                    if (
                        not stat.S_ISREG(opened.st_mode)
                        or opened.st_dev != root_device
                        or (opened.st_dev, opened.st_ino)
                        != (details.st_dev, details.st_ino)
                    ):
                        raise ValueError(
                            f"manifest input changed before hashing: {relative.as_posix()}"
                        )
                    yield path, relative, opened, file_fd
                finally:
                    os.close(file_fd)

    try:
        yield from visit(traversal_fd, Path())
    finally:
        os.close(traversal_fd)


def iter_manifest_files(root: Path):
    for path, relative, _details, _file_fd in _iter_manifest_entries(root):
        yield path, relative


def build_manifest(
    root: Path,
    version: str,
    *,
    root_fd: int | None = None,
    expected_root_device: int | None = None,
    expected_root_inode: int | None = None,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path, relative, details, file_fd in _iter_manifest_entries(
        root,
        root_fd=root_fd,
        expected_root_device=expected_root_device,
        expected_root_inode=expected_root_inode,
    ):
        relative_text = relative.as_posix()
        status, canonical, artifact_type, retention, sensitivity = classify(relative)
        digest, size = sha256_file(
            path,
            expected_device=details.st_dev,
            expected_inode=details.st_ino,
            file_fd=file_fd,
        )
        records.append(
            {
                "canonical": canonical,
                "id": hashlib.sha256(relative_text.encode("utf-8")).hexdigest()[:16],
                "path": relative_text,
                "retention": retention,
                "sensitivity": sensitivity,
                "sha256": digest,
                "size": size,
                "status": status,
                "type": artifact_type,
                "version": version,
            }
        )
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--version", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root, expected_root = inspect_lexical_root(args.root)
    except FileNotFoundError:
        print(f"storage root does not exist: {args.root.expanduser()}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    requested_output = args.output.expanduser()
    index = root / "00_INDEX"
    if index.is_symlink():
        print("manifest output is unsafe: 00_INDEX must not be a symlink", file=sys.stderr)
        return 2
    if requested_output.is_symlink():
        print("manifest output is unsafe: output must not be a symlink", file=sys.stderr)
        return 2
    output = requested_output.resolve(strict=False)
    if output.parent != index or output.name != "MANIFEST.jsonl":
        print("manifest output must be inside 00_INDEX as MANIFEST.jsonl", file=sys.stderr)
        return 2

    root_fd = None
    index_fd = None
    try:
        root_fd = os.open(root, DIRECTORY_FLAGS)
        root_details = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(root_details.st_mode)
            or (root_details.st_dev, root_details.st_ino)
            != (expected_root.st_dev, expected_root.st_ino)
        ):
            raise ValueError(f"storage root changed before manifest generation: {root}")
        try:
            index_fd = os.open("00_INDEX", DIRECTORY_FLAGS, dir_fd=root_fd)
        except FileNotFoundError:
            os.mkdir("00_INDEX", 0o700, dir_fd=root_fd)
            index_fd = os.open("00_INDEX", DIRECTORY_FLAGS, dir_fd=root_fd)
        index_details = os.fstat(index_fd)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        if index_fd is not None:
            os.close(index_fd)
        if root_fd is not None:
            os.close(root_fd)
        return 2
    except OSError as error:
        print(f"manifest output is unsafe: cannot validate 00_INDEX: {error}", file=sys.stderr)
        if index_fd is not None:
            os.close(index_fd)
        if root_fd is not None:
            os.close(root_fd)
        return 2
    if (
        not stat.S_ISDIR(index_details.st_mode)
        or index_details.st_dev != root_details.st_dev
    ):
        print(
            "manifest output is unsafe: 00_INDEX is on a different filesystem",
            file=sys.stderr,
        )
        os.close(index_fd)
        os.close(root_fd)
        return 2
    os.fchmod(index_fd, 0o700)
    try:
        existing_output = os.stat(
            output.name,
            dir_fd=index_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        existing_output = None
    if existing_output is not None and not stat.S_ISREG(existing_output.st_mode):
        print("manifest output is unsafe: existing output is not a regular file", file=sys.stderr)
        os.close(index_fd)
        os.close(root_fd)
        return 2
    try:
        records = build_manifest(
            root,
            args.version,
            root_fd=root_fd,
            expected_root_device=root_details.st_dev,
            expected_root_inode=root_details.st_ino,
        )
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        os.close(index_fd)
        os.close(root_fd)
        return 2

    try:
        assert_root_identity(root, expected_root)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        os.close(index_fd)
        os.close(root_fd)
        return 2

    payload = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
        for record in records
    )
    temporary_name = f".MANIFEST.{os.getpid()}.{secrets.token_hex(8)}"
    temporary_fd = None
    try:
        assert_root_identity(root, expected_root)
        current_index = index.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(current_index.st_mode)
            or (current_index.st_dev, current_index.st_ino)
            != (index_details.st_dev, index_details.st_ino)
        ):
            raise ValueError("manifest output is unsafe: 00_INDEX changed")
        temporary_fd = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=index_fd,
        )
        os.fchmod(temporary_fd, 0o600)
        with os.fdopen(temporary_fd, "w", encoding="utf-8") as stream:
            temporary_fd = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        current_index = index.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(current_index.st_mode)
            or (current_index.st_dev, current_index.st_ino)
            != (index_details.st_dev, index_details.st_ino)
        ):
            raise ValueError("manifest output is unsafe: 00_INDEX changed")
        os.replace(
            temporary_name,
            output.name,
            src_dir_fd=index_fd,
            dst_dir_fd=index_fd,
        )
        temporary_name = ""
        os.fsync(index_fd)
        assert_root_identity(root, expected_root)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        if temporary_name:
            try:
                os.unlink(temporary_name, dir_fd=index_fd)
            except FileNotFoundError:
                pass
        os.close(index_fd)
        os.close(root_fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
