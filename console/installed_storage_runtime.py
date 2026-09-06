"""Composition root for the installed S3 storage runtime."""

from __future__ import annotations

import json
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self
from uuid import UUID

from native_helpers import attest_broker_executable, attest_mount_probe, load_native_helper_registry
from storage_broker import (
    AttestedBootstrapHandle,
    AttestedBrokerExecutable,
    AttestedMountProbe,
    InstalledStorageRuntimeGeneration,
    StorageBrokerClient,
    StorageWorkflowLedger,
)
from storage_contract import StorageContract, probe_mount_fd
from storage_lifecycle import StorageLifecycle, StoragePaths
from storage_reconciliation import digest
from storage_result import CheckResult, OperationResult


class InstalledRuntimeError(RuntimeError):
    pass


_SHA256_HEX = set("0123456789abcdef")


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and not (set(value) - _SHA256_HEX)


def _reject_duplicate_keys(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def _read_fd_bytes(fd: int, *, limit: int = 4 * 1024 * 1024) -> bytes:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > limit:
                raise InstalledRuntimeError("installed runtime record is too large")
        return b"".join(chunks)
    except OSError as exc:
        raise InstalledRuntimeError("installed runtime descriptor is unreadable") from exc
    finally:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
        except OSError:
            pass


def _assert_fd_matches_path(
    fd: int,
    path: Path,
    *,
    directory: bool,
    mode: int,
    expected_device: int | None = None,
) -> os.stat_result:
    try:
        opened = os.fstat(fd)
        lexical = path.lstat()
    except OSError as exc:
        raise InstalledRuntimeError("installed bootstrap descriptor is unavailable") from exc
    if path.is_symlink() or not (
        stat.S_ISDIR(opened.st_mode) if directory else stat.S_ISREG(opened.st_mode)
    ):
        raise InstalledRuntimeError("installed bootstrap descriptor type is invalid")
    if not (
        stat.S_ISDIR(lexical.st_mode) if directory else stat.S_ISREG(lexical.st_mode)
    ) or (
        opened.st_dev,
        opened.st_ino,
        opened.st_uid,
    ) != (
        lexical.st_dev,
        lexical.st_ino,
        lexical.st_uid,
    ):
        raise InstalledRuntimeError("installed bootstrap descriptor identity changed")
    if (
        opened.st_uid != os.getuid()
        or stat.S_IMODE(opened.st_mode) != mode
        or (expected_device is not None and opened.st_dev != expected_device)
    ):
        raise InstalledRuntimeError("installed bootstrap descriptor ownership is invalid")
    return opened


def _validate_bootstrap_handle(home: Path, lock_set: Any, bootstrap_handle: AttestedBootstrapHandle) -> tuple[bytes, bytes, bytes]:
    try:
        bootstrap_handle.assert_locked(home, lock_set)
        home_details = home.lstat()
        if home.is_symlink() or not stat.S_ISDIR(home_details.st_mode):
            raise InstalledRuntimeError("installed runtime home is invalid")
        if home_details.st_uid != os.getuid() or stat.S_IMODE(home_details.st_mode) != 0o700:
            raise InstalledRuntimeError("installed runtime home ownership is invalid")
        install_details = os.fstat(bootstrap_handle.install_lock_fd)
        if (
            not stat.S_ISREG(install_details.st_mode)
            or install_details.st_uid != os.getuid()
            or stat.S_IMODE(install_details.st_mode) != bootstrap_handle.install_lock_mode
            or install_details.st_nlink != 1
            or (install_details.st_dev & 0xFFFFFFFF, install_details.st_ino, install_details.st_uid)
            != (
                bootstrap_handle.install_lock_dev_u32,
                bootstrap_handle.install_lock_ino,
                bootstrap_handle.install_lock_uid,
            )
        ):
            raise InstalledRuntimeError("installed bootstrap install lock identity is invalid")
        selector_path = home / "current-generation.json"
        selector_details = _assert_fd_matches_path(
            bootstrap_handle.selector_fd, selector_path, directory=False, mode=0o600,
            expected_device=home_details.st_dev,
        )
        selector_bytes = _read_fd_bytes(bootstrap_handle.selector_fd)
        if selector_details.st_size != len(selector_bytes):
            raise InstalledRuntimeError("installed selector changed while reading")
        try:
            selector = json.loads(
                selector_bytes.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise InstalledRuntimeError("installed selector is malformed") from exc
        if not isinstance(selector, dict) or set(selector) != {
            "schema_version", "generation_id", "generation_record_sha256"
        }:
            raise InstalledRuntimeError("installed selector schema is invalid")
        try:
            selector_generation = UUID(str(selector["generation_id"]))
        except (ValueError, TypeError, AttributeError) as exc:
            raise InstalledRuntimeError("installed selector generation is invalid") from exc
        if (
            selector.get("schema_version") != 1
            or selector_generation != bootstrap_handle.generation_id
            or not _is_sha256(selector.get("generation_record_sha256"))
            or selector["generation_record_sha256"] != bootstrap_handle.generation_record_sha256
        ):
            raise InstalledRuntimeError("installed selector binding is invalid")
        selector_sha = digest(
            "CORTEX-S3\x00GENERATION-SELECTOR\x00V1\x00",
            {
                "schema_version": 1,
                "generation_id": selector_generation,
                "generation_record_sha256": selector["generation_record_sha256"],
            },
        )
        if selector_sha != bootstrap_handle.selector_sha256:
            raise InstalledRuntimeError("installed selector digest mismatch")
        generations_root = home / "installed-generations"
        try:
            generations_root_details = generations_root.lstat()
        except OSError as exc:
            raise InstalledRuntimeError("installed generations root is unavailable") from exc
        if (
            generations_root.is_symlink()
            or not stat.S_ISDIR(generations_root_details.st_mode)
            or generations_root_details.st_uid != os.getuid()
            or stat.S_IMODE(generations_root_details.st_mode) != 0o700
            or generations_root_details.st_dev != home_details.st_dev
        ):
            raise InstalledRuntimeError("installed generations root is invalid")
        generation_dir = home / "installed-generations" / str(bootstrap_handle.generation_id)
        generation_dir_details = _assert_fd_matches_path(
            bootstrap_handle.generation_dir_fd, generation_dir, directory=True, mode=0o700,
            expected_device=generations_root_details.st_dev,
        )
        record_path = generation_dir / "generation-record.json"
        record_details = _assert_fd_matches_path(
            bootstrap_handle.generation_record_fd, record_path, directory=False, mode=0o600,
            expected_device=generation_dir_details.st_dev,
        )
        manifest_path = generation_dir / "owned-manifest.json"
        manifest_details = _assert_fd_matches_path(
            bootstrap_handle.owned_manifest_fd, manifest_path, directory=False, mode=0o600,
            expected_device=generation_dir_details.st_dev,
        )
        record_bytes = _read_fd_bytes(bootstrap_handle.generation_record_fd)
        manifest_bytes = _read_fd_bytes(bootstrap_handle.owned_manifest_fd)
        if record_details.st_size != len(record_bytes) or manifest_details.st_size != len(manifest_bytes):
            raise InstalledRuntimeError("installed generation changed while reading")
        interpreter = os.fstat(bootstrap_handle.interpreter_fd)
        if (
            not stat.S_ISREG(interpreter.st_mode)
            or interpreter.st_uid != os.getuid()
            or stat.S_IMODE(interpreter.st_mode) != 0o700
            or interpreter.st_dev != generation_dir_details.st_dev
        ):
            raise InstalledRuntimeError("installed interpreter descriptor is invalid")
        return selector_bytes, record_bytes, manifest_bytes
    except InstalledRuntimeError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise InstalledRuntimeError("installed bootstrap handle is invalid") from exc


@dataclass(slots=True)
class InstalledStorageRuntime:
    home: Path
    generation: InstalledStorageRuntimeGeneration
    broker_executable: AttestedBrokerExecutable
    mount_probe_executable: AttestedMountProbe
    ledger: StorageWorkflowLedger
    broker: StorageBrokerClient
    fd_probe: Any
    paths: Any
    lifecycle: Any
    contract: Any

    @classmethod
    def from_installed_home_locked(
        cls, home: Path, lock_set: Any, bootstrap_handle: AttestedBootstrapHandle,
    ) -> Self:
        home = Path(home)
        _, attested_generation_bytes, attested_manifest_bytes = _validate_bootstrap_handle(
            home, lock_set, bootstrap_handle
        )
        generation_dir = home / "installed-generations" / str(bootstrap_handle.generation_id)
        generation_record_path = generation_dir / "generation-record.json"
        manifest_path = generation_dir / "owned-manifest.json"
        try:
            if generation_record_path.is_symlink() or manifest_path.is_symlink():
                raise InstalledRuntimeError("installed generation contains a symlink")
            generation_bytes = generation_record_path.read_bytes()
            manifest_bytes = manifest_path.read_bytes()
            if generation_bytes != attested_generation_bytes or manifest_bytes != attested_manifest_bytes:
                raise InstalledRuntimeError("installed generation changed after attestation")
            generation = json.loads(generation_bytes.decode("utf-8"))
            manifest = load_native_helper_registry(manifest_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, InstalledRuntimeError) as exc:
            raise InstalledRuntimeError("installed generation is missing or invalid") from exc
        if not isinstance(generation, dict) or generation.get("schema_version") != 1:
            raise InstalledRuntimeError("installed generation schema is invalid")
        try:
            generation_id = UUID(str(generation.get("generation_id")))
        except (ValueError, AttributeError, TypeError) as exc:
            raise InstalledRuntimeError("installed generation id is invalid") from exc
        if generation_id != bootstrap_handle.generation_id:
            raise InstalledRuntimeError("installed generation selector mismatch")
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        if manifest_sha256 != bootstrap_handle.owned_manifest_sha256:
            raise InstalledRuntimeError("installed manifest digest mismatch")
        if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
            raise InstalledRuntimeError("installed manifest schema is invalid")
        generation_manifest_sha256 = generation.get("owned_manifest_sha256")
        if generation_manifest_sha256 != manifest_sha256:
            raise InstalledRuntimeError("installed generation manifest binding mismatch")
        generation_record_sha256 = generation.get("generation_record_sha256")
        if generation_record_sha256 != bootstrap_handle.generation_record_sha256:
            raise InstalledRuntimeError("installed generation digest mismatch")
        generation_without_digest = dict(generation)
        generation_without_digest.pop("generation_record_sha256", None)
        expected_generation_sha256 = digest(
            "CORTEX-S3\x00INSTALLED-GENERATION\x00V1\x00",
            generation_without_digest,
        )
        if generation_record_sha256 != expected_generation_sha256:
            raise InstalledRuntimeError("installed generation digest is invalid")
        broker_path = generation_dir / "app" / "bin" / "cortex-storage-broker"
        probe_path = generation_dir / "app" / "bin" / "storage-mount-probe"
        broker_executable = attest_broker_executable(broker_path)
        mount_probe = attest_mount_probe(probe_path)
        ledger = StorageWorkflowLedger(home)
        broker = StorageBrokerClient(home=home, executable=broker_executable, ledger=ledger)
        environment = dict(os.environ)
        mount_path = Path(environment.get("CORTEX_STORAGE_MOUNT", home / "mount"))
        root_path = Path(environment.get("CORTEX_STORAGE_ROOT", mount_path / "20_WORKSPACES"))
        paths = StoragePaths(
            home=home,
            host_volume=Path(environment.get("CORTEX_STORAGE_HOST", home / "storage")),
            legacy_image=home / "legacy" / "CORTEX_BRIDGE_2026_08.sparsebundle",
            new_image=Path(environment.get("CORTEX_STORAGE_IMAGE", home / "storage" / "CORTEX_BRIDGE_2026_09.sparsebundle")),
            mount=mount_path,
            root=root_path,
            bootstrap=home / "storage-bootstrap.json",
            marker=home / "storage-required",
            transition=home / "storage-transition.json",
            quarantine=home / "private-quarantine",
        )

        def _probe_path(path: Path) -> Any:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
            try:
                return probe_mount_fd(descriptor)
            finally:
                os.close(descriptor)

        fd_probe = probe_mount_fd
        contract = StorageContract(
            home,
            environment=environment,
            broker=broker,
            fd_probe=fd_probe,
            managed_runtime_probe=lambda lock_set, *, home, expected_storage_transaction_id: False,
        )

        def _status_operation(lock_set: Any) -> OperationResult:
            status = contract.probe_locked(lock_set)
            return OperationResult(
                "status", status.verdict, status.transaction_id, status.code,
                (CheckResult("storage", status.verdict, "contract_passed" if status.verdict == "PASS" else "contract_unclear" if status.verdict == "UNCLEAR" else "contract_rejected"),),
                storage_state=status.storage_state,
                mounted=status.mounted,
                runtime_allowed=status.runtime_allowed,
                recovery=status.recovery,
            )

        lifecycle = StorageLifecycle(
            paths,
            broker=broker,
            fd_probe=_probe_path,
            mount_verifier=_status_operation,
        )
        return cls(home, generation, broker_executable, mount_probe, ledger, broker, fd_probe, paths, lifecycle, contract)

    def close(self) -> None:
        self.broker_executable.close()
        self.mount_probe_executable.close()


def launch_managed_runtime(*, home: Path, lock_set: Any, bootstrap_handle: AttestedBootstrapHandle, **kwargs: Any) -> InstalledStorageRuntime:
    """Create the lock-bound runtime; actual server launch remains a caller concern."""
    return InstalledStorageRuntime.from_installed_home_locked(home, lock_set, bootstrap_handle)


__all__ = ["InstalledStorageRuntime", "InstalledRuntimeError", "launch_managed_runtime"]
