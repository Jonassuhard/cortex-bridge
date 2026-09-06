"""Composition root for the installed S3 storage runtime."""

from __future__ import annotations

import json
import hashlib
import os
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
        bootstrap_handle.assert_locked(home, lock_set)
        generation_dir = home / "installed-generations" / str(bootstrap_handle.generation_id)
        generation_record_path = generation_dir / "generation-record.json"
        manifest_path = generation_dir / "owned-manifest.json"
        try:
            if generation_record_path.is_symlink() or manifest_path.is_symlink():
                raise InstalledRuntimeError("installed generation contains a symlink")
            generation_bytes = generation_record_path.read_bytes()
            manifest_bytes = manifest_path.read_bytes()
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
