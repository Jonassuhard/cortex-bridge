#!/usr/bin/env python3
"""Fail closed unless the configured external Cortex storage is mounted."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from uuid import UUID


VolumeProbe = Callable[[Path], Mapping[str, object] | None]
EncryptedImageProbe = Callable[[Path, Path], bool]
StorageIdentityProbe = Callable[[Path], Mapping[str, object]]
DISKUTIL = Path("/usr/sbin/diskutil")
HDIUTIL = Path("/usr/bin/hdiutil")


def probe_storage_identity(path: Path) -> Mapping[str, object]:
    details = path.stat(follow_symlinks=False)
    return {
        "dev": details.st_dev,
        "is_dir": stat.S_ISDIR(details.st_mode),
        "mode": stat.S_IMODE(details.st_mode),
        "uid": details.st_uid,
    }


def configured_bootstrap(home: Path) -> Path | None:
    """Return the required bootstrap path, or None when external storage is off."""
    configured_bootstrap_path = os.environ.get("CORTEX_STORAGE_BOOTSTRAP")
    configured_marker_path = os.environ.get("CORTEX_STORAGE_REQUIRED_MARKER")
    bootstrap = Path(configured_bootstrap_path).expanduser() if configured_bootstrap_path else (
        home / "storage-bootstrap.json"
    )
    marker = Path(configured_marker_path).expanduser() if configured_marker_path else (
        home / "storage-required"
    )
    if (
        configured_bootstrap_path is not None
        or configured_marker_path is not None
        or marker.exists()
        or marker.is_symlink()
        or bootstrap.exists()
        or bootstrap.is_symlink()
    ):
        return bootstrap
    return None


def check_required_storage(home: Path) -> int:
    """Run the same fail-closed guard for every Python server entrypoint."""
    bootstrap = configured_bootstrap(home)
    if bootstrap is None:
        return 0
    return main(["--bootstrap", str(bootstrap)])


def _normalise_uuid(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return UUID(value.strip()).hex
    except ValueError:
        return None


def probe_volume(mount_path: Path) -> Mapping[str, object] | None:
    if not DISKUTIL.is_file():
        return None
    try:
        result = subprocess.run(
            [str(DISKUTIL), "info", "-plist", str(mount_path)],
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        payload = plistlib.loads(result.stdout)
    except (plistlib.InvalidFileException, ValueError):
        return None
    reported_mount = payload.get("MountPoint")
    volume_uuid = payload.get("VolumeUUID") or payload.get("APFSVolumeUUID")
    filesystem_type = payload.get("FilesystemType")
    writable = payload.get("WritableVolume", payload.get("Writable"))
    if (
        not isinstance(reported_mount, str)
        or not isinstance(volume_uuid, str)
        or not isinstance(filesystem_type, str)
        or not isinstance(writable, bool)
    ):
        return None
    return {
        "mount_path": reported_mount,
        "volume_uuid": volume_uuid,
        "filesystem_type": filesystem_type,
        "writable": writable,
    }


def probe_encrypted_image(mount_path: Path, image_path: Path) -> bool:
    if not HDIUTIL.is_file() or not image_path.exists():
        return False
    try:
        result = subprocess.run(
            [str(HDIUTIL), "info", "-plist"],
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    try:
        payload = plistlib.loads(result.stdout)
    except (plistlib.InvalidFileException, ValueError):
        return False
    expected_mount = mount_path.resolve(strict=False)
    expected_image = image_path.resolve(strict=False)
    for image in payload.get("images", []):
        if not isinstance(image, dict):
            continue
        raw_image = image.get("image-path")
        if not isinstance(raw_image, str):
            continue
        if Path(raw_image).resolve(strict=False) != expected_image:
            continue
        mounted_here = any(
            isinstance(entity, dict)
            and isinstance(entity.get("mount-point"), str)
            and Path(entity["mount-point"]).resolve(strict=False) == expected_mount
            for entity in image.get("system-entities", [])
        )
        return bool(
            mounted_here
            and image.get("image-encrypted") is True
            and image.get("writeable") is True
        )
    return False


def _load_bootstrap(path: Path) -> tuple[Path, str, Path, Path] | None:
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) & 0o077
        ):
            return None
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = None
            payload = json.load(stream)
            after = os.fstat(stream.fileno())
        current = path.stat(follow_symlinks=False)
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        current_identity = (
            current.st_dev,
            current.st_ino,
            current.st_size,
            current.st_mtime_ns,
            current.st_ctime_ns,
        )
        if (
            not stat.S_ISREG(current.st_mode)
            or before_identity != after_identity
            or before_identity != current_identity
        ):
            return None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return None
    raw_mount = payload.get("mount_path")
    expected_uuid = payload.get("volume_uuid")
    raw_image = payload.get("encrypted_image_path")
    raw_storage = payload.get("storage_root")
    if not isinstance(raw_mount, str) or not raw_mount.strip():
        return None
    if not isinstance(raw_image, str) or not raw_image.strip():
        return None
    if not isinstance(raw_storage, str) or not raw_storage.strip():
        return None
    if _normalise_uuid(expected_uuid) is None:
        return None
    image_path = Path(raw_image)
    if not image_path.is_absolute() or image_path.suffix != ".sparsebundle":
        return None
    storage_root = Path(raw_storage)
    if not storage_root.is_absolute():
        return None
    return Path(raw_mount), expected_uuid, image_path, storage_root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bootstrap",
        required=True,
        type=Path,
        help="path to the storage bootstrap JSON",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the verified storage identity as one JSON object",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    volume_probe: VolumeProbe = probe_volume,
    encrypted_image_probe: EncryptedImageProbe = probe_encrypted_image,
    storage_identity_probe: StorageIdentityProbe = probe_storage_identity,
) -> int:
    args = _parser().parse_args(argv)
    bootstrap = args.bootstrap.expanduser()
    if not bootstrap.exists() and not bootstrap.is_symlink():
        print(f"STORAGE_BOOTSTRAP_MISSING: {bootstrap}", file=sys.stderr)
        return 2

    loaded = _load_bootstrap(bootstrap)
    if loaded is None:
        print(
            "STORAGE_BOOTSTRAP_INVALID: expected schema_version 1, "
            "an absolute mount_path, a valid volume_uuid and an absolute "
            "encrypted_image_path ending in .sparsebundle plus an absolute storage_root",
            file=sys.stderr,
        )
        return 2

    configured_mount, expected_uuid, encrypted_image_path, storage_root = loaded
    if not configured_mount.is_absolute():
        print(
            f"STORAGE_PATH_INVALID: mount_path must be absolute: {configured_mount}",
            file=sys.stderr,
        )
        return 2

    mount_path = configured_mount.resolve(strict=False)
    if not mount_path.is_dir():
        print(f"STORAGE_VOLUME_MISSING: {mount_path}", file=sys.stderr)
        return 3

    try:
        identity = volume_probe(mount_path)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        identity = None
    if not isinstance(identity, Mapping):
        print(f"STORAGE_VOLUME_MISSING: {mount_path}", file=sys.stderr)
        return 3

    reported_mount = identity.get("mount_path")
    actual_uuid = identity.get("volume_uuid")
    if not isinstance(reported_mount, str) or not Path(reported_mount).is_absolute():
        print(f"STORAGE_VOLUME_MISSING: {mount_path}", file=sys.stderr)
        return 3
    if Path(reported_mount).resolve(strict=False) != mount_path:
        print(
            f"STORAGE_VOLUME_MISSING: {mount_path} is not the reported mount point",
            file=sys.stderr,
        )
        return 3

    normalised_actual = _normalise_uuid(actual_uuid)
    if normalised_actual is None:
        print(f"STORAGE_VOLUME_MISSING: no volume UUID for {mount_path}", file=sys.stderr)
        return 3
    if normalised_actual != _normalise_uuid(expected_uuid):
        print(
            "STORAGE_UUID_MISMATCH: "
            f"expected {expected_uuid}, got {actual_uuid}",
            file=sys.stderr,
        )
        return 4

    filesystem_type = identity.get("filesystem_type")
    if not isinstance(filesystem_type, str) or filesystem_type.lower() != "apfs":
        print(
            "STORAGE_FILESYSTEM_UNSAFE: expected APFS, "
            f"got {filesystem_type or 'unknown'}",
            file=sys.stderr,
        )
        return 5
    if identity.get("writable") is not True:
        print(f"STORAGE_VOLUME_READ_ONLY: {mount_path}", file=sys.stderr)
        return 5
    try:
        encrypted = encrypted_image_probe(mount_path, encrypted_image_path)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        encrypted = False
    if encrypted is not True:
        print(
            "STORAGE_ENCRYPTION_UNVERIFIED: mounted APFS volume is not backed "
            f"by the configured encrypted image: {encrypted_image_path}",
            file=sys.stderr,
        )
        return 6
    try:
        lexical_relative_storage = storage_root.relative_to(configured_mount)
    except ValueError:
        lexical_relative_storage = None
    lexical_component = configured_mount
    contains_symlink = configured_mount.is_symlink()
    if lexical_relative_storage is not None:
        for part in lexical_relative_storage.parts:
            lexical_component = lexical_component / part
            if lexical_component.is_symlink():
                contains_symlink = True
                break

    resolved_storage = storage_root.resolve(strict=False)
    try:
        relative_storage = resolved_storage.relative_to(mount_path)
    except ValueError:
        relative_storage = None
    try:
        mount_security = storage_identity_probe(mount_path)
        storage_security = storage_identity_probe(resolved_storage)
    except (OSError, RuntimeError):
        mount_security = {}
        storage_security = {}
    secure_storage_identity = (
        storage_security.get("is_dir") is True
        and type(storage_security.get("dev")) is int
        and storage_security.get("dev") == mount_security.get("dev")
        and storage_security.get("uid") == os.getuid()
        and type(storage_security.get("mode")) is int
        and int(storage_security["mode"]) & 0o077 == 0
    )
    if (
        lexical_relative_storage is None
        or not lexical_relative_storage.parts
        or relative_storage is None
        or not relative_storage.parts
        or contains_symlink
        or not resolved_storage.is_dir()
        or not secure_storage_identity
    ):
        print(
            "STORAGE_ROOT_UNSAFE: storage_root must be a real directory "
            f"inside the verified mount: {storage_root}",
            file=sys.stderr,
        )
        return 7

    if args.json:
        print(json.dumps({
            "filesystem_type": "apfs",
            "mount_path": str(mount_path),
            "status": "ready",
            "storage_root": str(resolved_storage),
            "volume_uuid": str(actual_uuid),
            "writable": True,
        }, sort_keys=True))
    else:
        print(
            f"STORAGE_READY: {mount_path} "
            f"({actual_uuid}, APFS, writable, encrypted image verified)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
