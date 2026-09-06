"""Descriptor-held attestation for installed native storage helpers."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Mapping

from storage_broker import AttestedBrokerExecutable, AttestedMountProbe, DarwinU32


PRIVATE_MODE = 0o700


class NativeHelperAttestationError(RuntimeError):
    pass


def _read_hash(fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    return digest.hexdigest()


def attest_file(path: Path, *, expected_mode: int = PRIVATE_MODE, profile_sha256: str = "") -> tuple[int, os.stat_result, str]:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise NativeHelperAttestationError("native helper is not a regular file")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise NativeHelperAttestationError("native helper cannot be opened") from exc
    try:
        details = os.fstat(fd)
        if not stat.S_ISREG(details.st_mode) or details.st_uid != os.getuid():
            raise NativeHelperAttestationError("native helper ownership is invalid")
        if stat.S_IMODE(details.st_mode) != expected_mode:
            raise NativeHelperAttestationError("native helper mode is invalid")
        before = (details.st_dev, details.st_ino, details.st_size, details.st_mtime_ns)
        sha = _read_hash(fd)
        after = os.fstat(fd)
        if before != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise NativeHelperAttestationError("native helper changed while hashing")
        return fd, after, sha
    except Exception:
        os.close(fd)
        raise


def attest_broker_executable(path: Path, *, build_profile_sha256: str = "") -> AttestedBrokerExecutable:
    fd, details, sha = attest_file(path, expected_mode=PRIVATE_MODE, profile_sha256=build_profile_sha256)
    return AttestedBrokerExecutable(
        Path(path), fd, DarwinU32(details.st_dev & 0xFFFFFFFF), details.st_ino,
        details.st_uid, stat.S_IMODE(details.st_mode), sha, build_profile_sha256,
    )


def attest_mount_probe(path: Path, *, build_profile_sha256: str = "") -> AttestedMountProbe:
    fd, details, sha = attest_file(path, expected_mode=PRIVATE_MODE, profile_sha256=build_profile_sha256)
    return AttestedMountProbe(
        Path(path), fd, DarwinU32(details.st_dev & 0xFFFFFFFF), details.st_ino,
        details.st_uid, 0o700, sha, build_profile_sha256,
    )


def verify_attested_fd(attested: Any) -> None:
    if getattr(attested, "_closed", False):
        raise NativeHelperAttestationError("attestation FD is closed")
    try:
        current = os.fstat(attested.fd)
    except OSError as exc:
        raise NativeHelperAttestationError("attestation FD is unavailable") from exc
    if (current.st_dev & 0xFFFFFFFF, current.st_ino, current.st_uid) != (
        int(attested.dev_u32), attested.ino, attested.uid
    ):
        raise NativeHelperAttestationError("attested vnode identity changed")
    if stat.S_IMODE(current.st_mode) != attested.mode:
        raise NativeHelperAttestationError("attested helper mode changed")


def native_helper_manifest_record(
    *, target: str, source: str, source_sha256: str, build_profile_sha256: str,
    attested: AttestedBrokerExecutable | AttestedMountProbe, cdhash: str = "",
) -> dict[str, Any]:
    verify_attested_fd(attested)
    return {
        "target": target, "source": source, "source_sha256": source_sha256,
        "build_profile_sha256": build_profile_sha256, "sha256": attested.sha256,
        "cdhash": cdhash, "dev_u32": int(attested.dev_u32), "ino": attested.ino,
        "uid": attested.uid, "mode": attested.mode,
    }


def write_native_helper_registry(path: Path, records: Mapping[str, Mapping[str, Any]]) -> str:
    """Write an owned, hash-addressed registry atomically and return its SHA."""
    payload = json.dumps({"schema_version": 1, "native_helpers": records}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, payload)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if fd != -1:
            os.close(fd)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return hashlib.sha256(payload).hexdigest()


def load_native_helper_registry(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NativeHelperAttestationError("native helper registry is unreadable") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or not isinstance(payload.get("native_helpers"), dict):
        raise NativeHelperAttestationError("native helper registry schema is invalid")
    return payload


__all__ = [
    "NativeHelperAttestationError", "attest_file", "attest_broker_executable",
    "attest_mount_probe", "verify_attested_fd", "native_helper_manifest_record",
    "write_native_helper_registry", "load_native_helper_registry",
]
