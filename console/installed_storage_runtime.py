"""Composition root for the installed S3 storage runtime."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from native_helpers import attest_broker_executable, attest_mount_probe, load_native_helper_registry
from storage_broker import (
    AttestedBootstrapHandle,
    AttestedBrokerExecutable,
    AttestedMountProbe,
    InstalledStorageRuntimeGeneration,
    StorageBrokerClient,
    StorageWorkflowLedger,
)


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
            generation = json.loads(generation_record_path.read_text(encoding="utf-8"))
            load_native_helper_registry(manifest_path)
        except (OSError, json.JSONDecodeError, InstalledRuntimeError) as exc:
            raise InstalledRuntimeError("installed generation is missing or invalid") from exc
        if not isinstance(generation, dict) or generation.get("schema_version") != 1:
            raise InstalledRuntimeError("installed generation schema is invalid")
        if str(generation.get("generation_id")) != str(bootstrap_handle.generation_id):
            raise InstalledRuntimeError("installed generation selector mismatch")
        broker_path = generation_dir / "app" / "bin" / "cortex-storage-broker"
        probe_path = generation_dir / "app" / "bin" / "storage-mount-probe"
        broker_executable = attest_broker_executable(broker_path)
        mount_probe = attest_mount_probe(probe_path)
        ledger = StorageWorkflowLedger(home)
        broker = StorageBrokerClient(home=home, executable=broker_executable, ledger=ledger)
        try:
            from cortex_paths import build_paths
            paths = build_paths()
        except Exception:
            paths = home
        # The Foundation lifecycle/contract are optional until their owning
        # tasks land.  No fake native authority is manufactured here.
        fd_probe = None
        lifecycle = None
        contract = None
        return cls(home, generation, broker_executable, mount_probe, ledger, broker, fd_probe, paths, lifecycle, contract)

    def close(self) -> None:
        self.broker_executable.close()
        self.mount_probe_executable.close()


def launch_managed_runtime(*, home: Path, lock_set: Any, bootstrap_handle: AttestedBootstrapHandle, **kwargs: Any) -> InstalledStorageRuntime:
    """Create the lock-bound runtime; actual server launch remains a caller concern."""
    return InstalledStorageRuntime.from_installed_home_locked(home, lock_set, bootstrap_handle)


__all__ = ["InstalledStorageRuntime", "InstalledRuntimeError", "launch_managed_runtime"]
