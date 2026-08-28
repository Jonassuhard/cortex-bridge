#!/usr/bin/env python3
"""Verify and publish Cortex Bridge external-storage configuration."""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "check-cortex-storage.py"
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
MAX_CONTROL_FILE_BYTES = 1024 * 1024
RENAME_SWAP = 0x00000002
RENAME_EXCL = 0x00000004
GuardRunner = Callable[[Path], int]
PathIdentity = tuple[str, int, int]


class FileSnapshot(NamedTuple):
    device: int
    inode: int
    size: int
    digest: str


class PrivateTemporary(NamedTuple):
    path: Path
    snapshot: FileSnapshot


_LIBC = ctypes.CDLL(None, use_errno=True)
_RENAMEATX_NP = getattr(_LIBC, "renameatx_np", None)
if _RENAMEATX_NP is not None:
    _RENAMEATX_NP.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    _RENAMEATX_NP.restype = ctypes.c_int


def _default_cortex_home() -> Path:
    configured = os.environ.get("CORTEX_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "share" / "cortex-bridge"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cortex-home",
        type=Path,
        default=_default_cortex_home(),
    )
    parser.add_argument("--mount-path", required=True, type=Path)
    parser.add_argument("--volume-uuid", required=True)
    parser.add_argument("--encrypted-image-path", required=True, type=Path)
    parser.add_argument("--storage-root", required=True, type=Path)
    return parser


def _same_location(left: Path, right: Path) -> bool:
    if left == right:
        return True
    try:
        return left.samefile(right)
    except OSError:
        return False


def _path_component_identities(path: Path) -> tuple[PathIdentity, ...]:
    """Return the existing lexical directory chain, rejecting every symlink."""
    current = Path(path.anchor)
    identities: list[PathIdentity] = []
    for part in path.parts[1:]:
        current /= part
        try:
            identity = current.stat(follow_symlinks=False)
        except FileNotFoundError:
            break
        if stat.S_ISLNK(identity.st_mode):
            raise ValueError(f"CORTEX_HOME path must not contain symlinks: {current}")
        if not stat.S_ISDIR(identity.st_mode):
            raise ValueError(f"CORTEX_HOME path component is not a directory: {current}")
        identities.append((part, identity.st_dev, identity.st_ino))
    return tuple(identities)


def _validate_runtime_home(raw: Path) -> Path:
    home = raw.expanduser()
    if not home.is_absolute():
        raise ValueError("CORTEX_HOME must be an absolute local path")

    # resolve() follows symlinks and would erase the evidence that the caller
    # supplied an alias. Inspect the lexical path first, before any mkdir/chmod.
    _path_component_identities(home)

    def is_volumes_path(candidate: Path) -> bool:
        parts = candidate.parts
        return len(parts) > 1 and parts[0] == "/" and parts[1].casefold() == "volumes"

    if is_volumes_path(home):
        raise ValueError(
            "CORTEX_HOME must stay on the local disk; configure external data "
            "with --storage-root"
        )

    resolved = home.resolve(strict=False)
    if is_volumes_path(resolved):
        raise ValueError(
            "CORTEX_HOME must stay on the local disk; configure external data "
            "with --storage-root"
        )
    existing_ancestor = resolved
    while not existing_ancestor.exists() and existing_ancestor != existing_ancestor.parent:
        existing_ancestor = existing_ancestor.parent
    try:
        if existing_ancestor.stat().st_dev != Path.home().stat().st_dev:
            raise ValueError(
                "CORTEX_HOME must be on the same local filesystem as the user home"
            )
    except OSError as error:
        raise ValueError(f"cannot verify the CORTEX_HOME filesystem: {error}") from error
    user_home = Path.home().resolve(strict=False)
    rejected = {
        Path("/"),
        Path("/Applications"),
        Path("/Library"),
        Path("/System"),
        Path("/Users"),
        Path("/Volumes"),
        Path("/private"),
        Path("/tmp").resolve(strict=False),
        Path("/var").resolve(strict=False),
        user_home,
        *(user_home / name for name in (
            "Desktop",
            "Documents",
            "Downloads",
            "Library",
            ".config",
            ".local",
        )),
    }
    if any(_same_location(resolved, candidate) for candidate in rejected):
        raise ValueError("CORTEX_HOME must be a dedicated local directory")
    if home.exists() and not home.is_dir():
        raise ValueError("CORTEX_HOME must be a directory")
    # Keep the normalized lexical path. Publication must continue to prove that
    # this exact chain still names the directory opened below.
    return Path(os.path.abspath(home))


def _payload(args: argparse.Namespace) -> dict[str, object]:
    mount = args.mount_path.expanduser()
    image = args.encrypted_image_path.expanduser()
    storage = args.storage_root.expanduser()
    if not mount.is_absolute():
        raise ValueError("mount_path must be absolute")
    if not image.is_absolute() or image.suffix != ".sparsebundle":
        raise ValueError("encrypted_image_path must be an absolute .sparsebundle path")
    if not storage.is_absolute():
        raise ValueError("storage_root must be absolute")
    try:
        UUID(args.volume_uuid.strip())
    except (AttributeError, ValueError) as error:
        raise ValueError("volume_uuid must be a valid UUID") from error
    mount_resolved = mount.resolve(strict=False)
    storage_resolved = storage.resolve(strict=False)
    try:
        relative = storage_resolved.relative_to(mount_resolved)
    except ValueError as error:
        raise ValueError("storage_root must be inside mount_path") from error
    if not relative.parts:
        raise ValueError("storage_root must be a directory inside mount_path")
    return {
        "schema_version": 1,
        "mount_path": str(mount_resolved),
        "volume_uuid": args.volume_uuid.strip(),
        "encrypted_image_path": str(image.resolve(strict=False)),
        "storage_root": str(storage_resolved),
    }


def _ensure_private_home(
    home: Path,
    expected_existing: tuple[PathIdentity, ...],
) -> tuple[int, os.stat_result]:
    """Open/create ``home`` without following or silently replacing components."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(home.anchor, flags)
    expected_by_depth = {
        depth: identity for depth, identity in enumerate(expected_existing, start=1)
    }
    try:
        for depth, part in enumerate(home.parts[1:], start=1):
            expected = expected_by_depth.get(depth)
            if expected is None:
                try:
                    os.mkdir(part, PRIVATE_DIRECTORY_MODE, dir_fd=descriptor)
                except FileExistsError:
                    # Something appeared after the preflight. Never adopt it.
                    raise ValueError("CORTEX_HOME changed during validation") from None
                child = os.open(part, flags, dir_fd=descriptor)
            else:
                try:
                    child = os.open(part, flags, dir_fd=descriptor)
                except FileNotFoundError:
                    raise ValueError("CORTEX_HOME changed during validation") from None
                except OSError as error:
                    if error.errno in (errno.ELOOP, errno.ENOTDIR):
                        raise ValueError(
                            f"CORTEX_HOME path component is unsafe: {home}"
                        ) from error
                    raise

            child_identity = os.fstat(child)
            if not stat.S_ISDIR(child_identity.st_mode):
                os.close(child)
                raise ValueError(f"CORTEX_HOME path component is unsafe: {home}")
            if expected is not None:
                _, expected_device, expected_inode = expected
                if (
                    child_identity.st_dev != expected_device
                    or child_identity.st_ino != expected_inode
                ):
                    os.close(child)
                    raise ValueError("CORTEX_HOME changed during validation")
            os.close(descriptor)
            descriptor = child

        os.fchmod(descriptor, PRIVATE_DIRECTORY_MODE)
        identity = os.fstat(descriptor)
        return descriptor, identity
    except BaseException:
        os.close(descriptor)
        raise


def _check_control_file(path: Path) -> None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"storage control file is unsafe: {path}")


def _snapshot_descriptor(descriptor: int, display: Path) -> FileSnapshot:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError(f"storage control file is unsafe: {display}")
    if before.st_size > MAX_CONTROL_FILE_BYTES:
        raise ValueError(f"storage control file is too large: {display}")
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    total = 0
    while True:
        chunk = os.read(descriptor, 65536)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_CONTROL_FILE_BYTES:
            raise ValueError(f"storage control file is too large: {display}")
        digest.update(chunk)
    after = os.fstat(descriptor)
    if (
        after.st_dev != before.st_dev
        or after.st_ino != before.st_ino
        or after.st_size != before.st_size
        or total != before.st_size
    ):
        raise ValueError(f"storage control file changed during validation: {display}")
    return FileSnapshot(
        device=before.st_dev,
        inode=before.st_ino,
        size=before.st_size,
        digest=digest.hexdigest(),
    )


def _snapshot_named_file(
    directory_fd: int,
    name: str,
    display: Path,
) -> FileSnapshot | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.ENOTDIR):
            raise ValueError(f"storage control file is unsafe: {display}") from error
        raise
    try:
        return _snapshot_descriptor(descriptor, display)
    finally:
        os.close(descriptor)


def _rename_at(directory_fd: int, source: str, target: str, flags: int) -> None:
    if _RENAMEATX_NP is None:
        raise OSError(errno.ENOTSUP, "renameatx_np is unavailable")
    result = _RENAMEATX_NP(
        directory_fd,
        os.fsencode(source),
        directory_fd,
        os.fsencode(target),
        flags,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), target)


def _unlink_snapshot(
    directory_fd: int,
    name: str,
    display: Path,
    expected: FileSnapshot,
) -> bool:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except (FileNotFoundError, OSError):
        return False
    try:
        if _snapshot_descriptor(descriptor, display) != expected:
            return False
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if current.st_dev != expected.device or current.st_ino != expected.inode:
            return False
        os.unlink(name, dir_fd=directory_fd)
        return True
    finally:
        os.close(descriptor)


def _publish_control_file(
    directory_fd: int,
    temporary: PrivateTemporary,
    target: Path,
    expected: FileSnapshot | None,
) -> None:
    if (
        _snapshot_named_file(directory_fd, temporary.path.name, temporary.path)
        != temporary.snapshot
    ):
        raise ValueError(f"storage temporary changed before publication: {temporary.path}")
    if _snapshot_named_file(directory_fd, target.name, target) != expected:
        raise ValueError(f"storage control target changed before publication: {target}")

    if expected is None:
        _rename_at(directory_fd, temporary.path.name, target.name, RENAME_EXCL)
        if _snapshot_named_file(directory_fd, target.name, target) != temporary.snapshot:
            raise ValueError(f"storage control target changed during publication: {target}")
        return

    _rename_at(directory_fd, temporary.path.name, target.name, RENAME_SWAP)
    try:
        displaced = _snapshot_named_file(
            directory_fd,
            temporary.path.name,
            temporary.path,
        )
        published = _snapshot_named_file(directory_fd, target.name, target)
    except (OSError, ValueError) as error:
        try:
            _rename_at(directory_fd, temporary.path.name, target.name, RENAME_SWAP)
        except OSError as rollback_error:
            raise ValueError(f"storage control rollback failed: {target}") from rollback_error
        raise ValueError(
            f"storage control target changed during publication: {target}"
        ) from error
    if displaced != expected or published != temporary.snapshot:
        _rename_at(directory_fd, temporary.path.name, target.name, RENAME_SWAP)
        if (
            _snapshot_named_file(directory_fd, target.name, target) != displaced
            or _snapshot_named_file(
                directory_fd,
                temporary.path.name,
                temporary.path,
            )
            != published
        ):
            raise ValueError(f"storage control rollback failed: {target}")
        raise ValueError(f"storage control target changed during publication: {target}")

    if not _unlink_snapshot(
        directory_fd,
        temporary.path.name,
        temporary.path,
        expected,
    ):
        raise ValueError(f"previous storage control file could not be retired: {target}")


def _write_private_temporary(
    home: Path,
    prefix: str,
    payload: bytes,
    *,
    directory_fd: int | None = None,
) -> PrivateTemporary:
    if directory_fd is None:
        descriptor, raw_path = tempfile.mkstemp(prefix=prefix, dir=home)
        temporary = Path(raw_path)
    else:
        while True:
            temporary = home / f"{prefix}{secrets.token_hex(16)}"
            try:
                descriptor = os.open(
                    temporary.name,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0),
                    PRIVATE_FILE_MODE,
                    dir_fd=directory_fd,
                )
                break
            except FileExistsError:
                continue
    created = os.fstat(descriptor)
    try:
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
            identity = os.fstat(stream.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            if directory_fd is None:
                current = temporary.stat(follow_symlinks=False)
                if current.st_dev == created.st_dev and current.st_ino == created.st_ino:
                    temporary.unlink(missing_ok=True)
            else:
                current = os.stat(
                    temporary.name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                if current.st_dev == created.st_dev and current.st_ino == created.st_ino:
                    os.unlink(temporary.name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        raise
    return PrivateTemporary(
        path=temporary,
        snapshot=FileSnapshot(
            device=identity.st_dev,
            inode=identity.st_ino,
            size=len(payload),
            digest=hashlib.sha256(payload).hexdigest(),
        ),
    )


def _same_directory_identity(
    home: Path,
    expected: os.stat_result,
    expected_components: tuple[PathIdentity, ...] | None = None,
) -> bool:
    try:
        if expected_components is not None:
            current_components = _path_component_identities(home)
            if current_components != expected_components:
                return False
        current = home.stat(follow_symlinks=False)
    except (OSError, ValueError):
        return False
    return (
        stat.S_ISDIR(current.st_mode)
        and current.st_dev == expected.st_dev
        and current.st_ino == expected.st_ino
        and not home.is_symlink()
    )


def _fsync_directory(path: Path, *, directory_fd: int | None = None) -> None:
    if directory_fd is not None:
        os.fsync(directory_fd)
        return
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _check_control_file_at(
    directory_fd: int,
    name: str,
    display: Path,
) -> FileSnapshot | None:
    return _snapshot_named_file(directory_fd, name, display)


def _unlink_temporary(
    directory_fd: int,
    temporary: PrivateTemporary | None,
) -> bool:
    if temporary is None:
        return True
    return _unlink_snapshot(
        directory_fd,
        temporary.path.name,
        temporary.path,
        temporary.snapshot,
    )


def _default_guard_runner(bootstrap: Path) -> int:
    result = subprocess.run(
        [sys.executable, str(GUARD), "--bootstrap", str(bootstrap)],
        check=False,
    )
    return result.returncode


def main(
    argv: Sequence[str] | None = None,
    *,
    guard_runner: GuardRunner = _default_guard_runner,
) -> int:
    args = _parser().parse_args(argv)
    home_descriptor: int | None = None
    try:
        home = _validate_runtime_home(args.cortex_home)
        payload = _payload(args)
        bootstrap = home / "storage-bootstrap.json"
        marker = home / "storage-required"
        existing_components = _path_component_identities(home)
        if home.exists():
            _check_control_file(bootstrap)
            _check_control_file(marker)
        home_descriptor, home_identity = _ensure_private_home(
            home,
            existing_components,
        )
        home_components = _path_component_identities(home)
        if not _same_directory_identity(home, home_identity, home_components):
            raise ValueError("CORTEX_HOME changed during validation")
        bootstrap_expected = _check_control_file_at(
            home_descriptor,
            bootstrap.name,
            bootstrap,
        )
        marker_expected = _check_control_file_at(
            home_descriptor,
            marker.name,
            marker,
        )
    except (OSError, ValueError) as error:
        if home_descriptor is not None:
            os.close(home_descriptor)
        print(f"STORAGE_CONFIGURATION_INVALID: {error}", file=sys.stderr)
        return 2

    bootstrap_bytes = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    verification: PrivateTemporary | None = None
    marker_temporary: PrivateTemporary | None = None
    status = 0
    try:
        verification = _write_private_temporary(
            home,
            ".storage-bootstrap.verify-",
            bootstrap_bytes,
            directory_fd=home_descriptor,
        )
        marker_temporary = _write_private_temporary(
            home,
            ".storage-required.write-",
            b"required\n",
            directory_fd=home_descriptor,
        )
        result = guard_runner(verification.path)
        if result != 0:
            status = int(result)
        else:
            if not _same_directory_identity(home, home_identity, home_components):
                raise ValueError("CORTEX_HOME changed before publication")
            # Publish the required marker first. A crash or failure before the
            # bootstrap publication therefore leaves startup fail-closed (or
            # using the previous valid bootstrap), never silently unguarded.
            _publish_control_file(
                home_descriptor,
                marker_temporary,
                marker,
                marker_expected,
            )
            marker_temporary = None
            _fsync_directory(home, directory_fd=home_descriptor)
            if not _same_directory_identity(home, home_identity, home_components):
                raise ValueError("CORTEX_HOME changed before bootstrap publication")
            _publish_control_file(
                home_descriptor,
                verification,
                bootstrap,
                bootstrap_expected,
            )
            verification = None
            _fsync_directory(home, directory_fd=home_descriptor)
    except (OSError, ValueError) as error:
        print(f"STORAGE_CONFIGURATION_FAILED: {error}", file=sys.stderr)
        status = 2
    finally:
        cleanup_ok = True
        for temporary in (verification, marker_temporary):
            try:
                cleanup_ok = _unlink_temporary(home_descriptor, temporary) and cleanup_ok
            except (OSError, ValueError):
                cleanup_ok = False
        if not cleanup_ok:
            print(
                "STORAGE_CONFIGURATION_FAILED: temporary identity changed; preserved",
                file=sys.stderr,
            )
            status = 2
        os.close(home_descriptor)

    if status != 0:
        return status
    print(f"STORAGE_CONFIGURED: {payload['storage_root']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
