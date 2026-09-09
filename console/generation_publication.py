"""Publish one verified application generation without mixing versions."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
from uuid import UUID

from generation_metadata import GenerationMetadata, verify_generation_metadata

TRANSACTION_NAME = ".generation-publication.json"


def _private_directory(path: Path) -> None:
    details = path.lstat()
    if (path.is_symlink() or not stat.S_ISDIR(details.st_mode)
            or details.st_uid != os.getuid() or stat.S_IMODE(details.st_mode) != 0o700):
        raise ValueError("Private generation directory required")


def _write_all(fd: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(fd, remaining)
        if written <= 0:
            raise OSError("Generation publication write made no progress")
        remaining = remaining[written:]


def _write_transaction(home: Path, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    fd, temporary = tempfile.mkstemp(prefix="." + TRANSACTION_NAME + ".", dir=home)
    try:
        os.fchmod(fd, 0o600)
        _write_all(fd, data)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temporary, home / TRANSACTION_NAME)
        directory = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _write_generation_file(generation: Path, name: str, payload: bytes) -> None:
    fd, temporary = tempfile.mkstemp(prefix="." + name + ".", dir=generation)
    try:
        os.fchmod(fd, 0o600)
        _write_all(fd, payload)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.link(temporary, generation / name)
        os.unlink(temporary)
        directory = os.open(generation, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _write_selector(home: Path, payload: bytes) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".current-generation.", dir=home)
    try:
        os.fchmod(fd, 0o600)
        _write_all(fd, payload)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temporary, home / "current-generation.json")
        directory = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def publish_generation(install_home: Path, staging_home: Path, metadata: GenerationMetadata) -> dict:
    install_home = Path(install_home).resolve(strict=True)
    staging_home = Path(staging_home).resolve(strict=True)
    _private_directory(install_home)
    _private_directory(staging_home)
    if not isinstance(metadata, GenerationMetadata):
        raise ValueError("Generation metadata required")
    verify_generation_metadata(staging_home, metadata)
    staging_app = staging_home / "app"
    if staging_app.is_symlink() or not staging_app.is_dir():
        raise ValueError("Complete staged application is required")
    generations = install_home / "installed-generations"
    generations.mkdir(mode=0o700, exist_ok=True)
    _private_directory(generations)
    generation = generations / str(metadata.generation_id)
    if generation.exists() or generation.is_symlink():
        raise FileExistsError("Generation already exists")
    generation.mkdir(mode=0o700)
    try:
        _write_transaction(install_home, {
            "schema_version": 1, "state": "prepared",
            "generation_id": str(metadata.generation_id),
        })
        os.rename(staging_app, generation / "app")
        # Persist both sides of the move and the new generation's parent entry
        # before a durable selector is allowed to refer to this generation.
        for parent in (staging_home, generations):
            parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        directory = os.open(generation, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        _write_generation_file(generation, "owned-manifest.json", metadata.manifest_bytes)
        _write_generation_file(generation, "generation-record.json", metadata.record_bytes)
        _write_transaction(install_home, {
            "schema_version": 1, "state": "generation_written",
            "generation_id": str(metadata.generation_id),
        })
        _write_selector(install_home, metadata.selector_bytes)
        _write_transaction(install_home, {
            "schema_version": 1, "state": "committed",
            "generation_id": str(metadata.generation_id),
        })
        return {"status": "published", "generation_id": str(metadata.generation_id)}
    except BaseException:
        raise


def _read_recovery_json(path: Path):
    """Only absence is absence; unsafe or malformed evidence must stop recovery."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ValueError("Unsafe generation recovery file") from error
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1
                or not 0 < before.st_size <= 65536):
            raise ValueError("Unsafe generation recovery file")
        raw = os.read(fd, before.st_size + 1)
        after = os.fstat(fd)
        if (len(raw) != before.st_size or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns):
            raise ValueError("Generation recovery file changed")
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate recovery key")
                result[key] = value
            return result
        value = json.loads(raw, object_pairs_hook=unique)
        if type(value) is not dict:
            raise ValueError("Recovery object required")
        return value
    finally:
        os.close(fd)


def _validate_recovery_identity(payload, keys):
    try:
        identifier = payload["generation_id"]
        if (set(payload) != keys or type(payload["schema_version"]) is not int
                or payload["schema_version"] != 1 or type(identifier) is not str
                or str(UUID(identifier)) != identifier):
            raise ValueError("Invalid generation recovery identity")
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("Invalid generation recovery identity") from error


def recover_generation_publication(install_home: Path) -> dict:
    install_home = Path(install_home).resolve(strict=True)
    _private_directory(install_home)
    marker = install_home / TRANSACTION_NAME
    payload = _read_recovery_json(marker)
    if payload is None:
        return {"status": "none"}
    _validate_recovery_identity(payload, {"schema_version", "state", "generation_id"})
    generation_id, state = payload["generation_id"], payload["state"]
    if state not in ("prepared", "generation_written", "committed"):
        raise ValueError("Generation publication journal state is invalid")
    selector = install_home / "current-generation.json"
    selected = _read_recovery_json(selector)
    if selected is not None:
        _validate_recovery_identity(selected, {"schema_version", "generation_id", "generation_record_sha256"})
        sha = selected["generation_record_sha256"]
        if type(sha) is not str or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("Generation selector digest is invalid")
        if selected["generation_id"] == generation_id:
            return {"status": "committed", "generation_id": generation_id}
    if state == "committed":
        raise ValueError("Committed generation selector is missing or mismatched")
    return {"status": "pending_reconciliation", "generation_id": generation_id}


__all__ = ["publish_generation", "recover_generation_publication", "TRANSACTION_NAME"]
