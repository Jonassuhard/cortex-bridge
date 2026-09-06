"""Single fail-closed storage authority used by runtime and mission admission."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Self

from executor.workspace_handle import MountFacts, WorkspaceHandle
from storage_result import StorageStatus
from storage_transition import runtime_transition_status_locked


class StorageContractError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(slots=True)
class StorageBinding:
    transaction_id: str
    host_fd: int
    mount_fd: int
    root_fd: int
    host_volume_uuid: str
    host_fsid_u32: tuple[int, int]
    mount_device_u32: int
    mount_fsid_u32: tuple[int, int]
    apfs_volume_uuid: str
    encryption_uuid: str
    volume_name: str
    image_basename: str
    root_relative: PurePosixPath
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for fd in (self.root_fd, self.mount_fd, self.host_fd):
            try:
                os.close(fd)
            except OSError:
                pass

    def __enter__(self) -> Self:
        if self._closed:
            raise StorageContractError("STORAGE_BINDING_CLOSED")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def probe_mount_fd(fd: int) -> MountFacts:
    """Return descriptor facts without inventing mount metadata.

    A plain ``fstat`` cannot prove APFS, fsid, writability, encryption, or the
    mount source.  Those fields therefore stay explicitly unknown until the
    attested native mount-probe supplies them.  Callers that need a real vault
    must reject this fallback rather than treating it as an APFS proof.
    """
    details = os.fstat(fd)
    if not stat.S_ISDIR(details.st_mode):
        raise StorageContractError("STORAGE_MOUNT_NOT_DIRECTORY")
    return MountFacts(
        details.st_dev & 0xFFFFFFFF,
        (0, 0),
        0,
        "unknown",
        "unknown",
        "unknown",
    )


class StorageContract:
    def __init__(
        self,
        home: Path,
        *,
        environment: Mapping[str, str] | None = None,
        broker: Any,
        fd_probe: Callable[[int], MountFacts] = probe_mount_fd,
        managed_runtime_probe: Callable[..., bool] | None = None,
    ) -> None:
        self._home = Path(home).resolve(strict=True)
        self._environment = dict(environment or {})
        self._broker = broker
        self._fd_probe = fd_probe
        if managed_runtime_probe is not None:
            self._managed_runtime_probe = managed_runtime_probe
        else:
            # Readiness is an attested lifespan fact.  In production the
            # startup-lease module owns that check; absent a proof, fail closed.
            def _default_runtime_probe(lock_set: Any, *, home: Path, expected_storage_transaction_id: str | None) -> bool:
                try:
                    from startup_lease import managed_runtime_is_ready_locked
                    return managed_runtime_is_ready_locked(
                        lock_set, home=home,
                        expected_storage_transaction_id=expected_storage_transaction_id,
                    )
                except Exception:
                    return False
            self._managed_runtime_probe = _default_runtime_probe

    def _assert(self, lock_set: Any, *, exclusive: bool) -> None:
        try:
            lock_set.assert_active(
                home=self._home,
                required_install_mode="shared",
                required_storage_mode="exclusive" if exclusive else "shared",
            )
            if getattr(lock_set, "admission_mode", "exclusive") != "exclusive":
                raise StorageContractError("STORAGE_LOCK_MODE")
        except StorageContractError:
            raise
        except Exception as exc:
            raise StorageContractError("STORAGE_LOCK_NOT_ACTIVE") from exc

    def _required(self) -> bool:
        return any(
            (self._home / name).exists() or (self._home / name).is_symlink()
            for name in ("storage-bootstrap.json", "storage-required", "storage-transition.json")
        )

    def probe_locked(self, lock_set: Any) -> StorageStatus:
        try:
            self._assert(lock_set, exclusive=False)
        except StorageContractError:
            return StorageStatus("UNCLEAR", "STORAGE_NOT_READY", None, "UNKNOWN", False, False)
        if not self._required():
            return StorageStatus("PASS", "STORAGE_NOT_REQUIRED", None, "UNCONFIGURED", False, True)
        status = runtime_transition_status_locked(lock_set, self._home)
        if status.code == "STORAGE_READY":
            return status
        return StorageStatus(
            "UNCLEAR" if status.verdict == "UNCLEAR" else "FAIL",
            "STORAGE_NOT_READY",
            status.transaction_id,
            status.storage_state,
            status.mounted,
            False,
        )

    def assert_runtime_ready_locked(self, lock_set: Any) -> StorageStatus:
        status = self.probe_locked(lock_set)
        optional = status.code == "STORAGE_NOT_REQUIRED" and not status.mounted and status.transaction_id is None
        committed = status.code == "STORAGE_READY" and status.mounted and status.transaction_id is not None
        if not (optional or committed) or status.verdict != "PASS":
            return StorageStatus(
                "UNCLEAR" if status.verdict == "UNCLEAR" else "FAIL",
                "STORAGE_NOT_READY", status.transaction_id, status.storage_state,
                status.mounted, False,
            )
        try:
            ready = self._managed_runtime_probe(
                lock_set, home=self._home,
                expected_storage_transaction_id=status.transaction_id,
            )
        except Exception:
            return StorageStatus("UNCLEAR", "STORAGE_NOT_READY", status.transaction_id, status.storage_state, status.mounted, False)
        if ready is not True:
            return StorageStatus("FAIL", "STORAGE_NOT_READY", status.transaction_id, status.storage_state, status.mounted, False)
        return StorageStatus("PASS", "RUNTIME_READY", status.transaction_id, status.storage_state, status.mounted, True)

    def open_locked(self, lock_set: Any) -> StorageBinding:
        self._assert(lock_set, exclusive=True)
        status = self.probe_locked(lock_set)
        if status.code != "STORAGE_READY" or not status.transaction_id:
            raise StorageContractError("STORAGE_NOT_READY")
        mount_path = Path(self._environment.get("CORTEX_STORAGE_MOUNT", self._home / "mount"))
        root_path = Path(self._environment.get("CORTEX_STORAGE_ROOT", mount_path / "20_WORKSPACES"))
        if mount_path.is_symlink() or root_path.is_symlink() or not mount_path.is_dir() or not root_path.is_dir():
            raise StorageContractError("STORAGE_MOUNT_NOT_READY")
        host_fd = os.open(self._home, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        mount_fd: int | None = None
        root_fd: int | None = None
        try:
            mount_fd = os.open(mount_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
            root_fd = os.open(root_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
            host_stat = os.fstat(host_fd)
            mount_stat = os.fstat(mount_fd)
            root_stat = os.fstat(root_fd)
            if not all(stat.S_ISDIR(item.st_mode) for item in (host_stat, mount_stat, root_stat)):
                raise StorageContractError("STORAGE_MOUNT_NOT_DIRECTORY")
            if root_stat.st_dev != mount_stat.st_dev:
                raise StorageContractError("STORAGE_ROOT_CROSS_DEVICE")
            facts = self._fd_probe(mount_fd)
            if (
                facts.filesystem_type != "apfs"
                or facts.mount_from in {"", "unknown"}
                or facts.mount_on in {"", "unknown"}
                or facts.fsid_u32 == (0, 0)
            ):
                raise StorageContractError("STORAGE_MOUNT_PROBE_UNAVAILABLE")
            return StorageBinding(
                status.transaction_id, host_fd, mount_fd, root_fd,
                self._environment.get("CORTEX_STORAGE_HOST_VOLUME_UUID", "unknown"),
                (0, 0), facts.st_dev_u32, facts.fsid_u32,
                self._environment.get("CORTEX_STORAGE_APFS_VOLUME_UUID", "unknown"),
                self._environment.get("CORTEX_STORAGE_ENCRYPTION_UUID", "unknown"),
                self._environment.get("CORTEX_STORAGE_VOLUME_NAME", "CORTEX_BRIDGE_2026_09"),
                self._environment.get("CORTEX_STORAGE_IMAGE_BASENAME", "CORTEX_BRIDGE_2026_09.sparsebundle"),
                PurePosixPath("20_WORKSPACES"),
            )
        except BaseException:
            for fd in (root_fd, mount_fd, host_fd):
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
            raise

    def revalidate_locked(self, lock_set: Any, binding: StorageBinding) -> MountFacts:
        self._assert(lock_set, exclusive=True)
        if binding._closed:
            raise StorageContractError("STORAGE_BINDING_CLOSED")
        facts = self._fd_probe(binding.mount_fd)
        if facts.st_dev_u32 != binding.mount_device_u32 or facts.fsid_u32 != binding.mount_fsid_u32:
            raise StorageContractError("STORAGE_DESCRIPTOR_CHANGED")
        return facts

    def open_workspace_locked(self, lock_set: Any, binding: StorageBinding, requested: str | Path) -> WorkspaceHandle:
        self._assert(lock_set, exclusive=True)
        if binding._closed:
            raise StorageContractError("STORAGE_BINDING_CLOSED")
        if not isinstance(requested, (str, Path)):
            raise TypeError("workspace path must be text or Path")
        value = str(requested)
        if value.startswith("/"):
            raise StorageContractError("WORKSPACE_NOT_VAULT")
        relative = PurePosixPath(value)
        if not relative.parts or relative.parts[0] != "20_WORKSPACES":
            raise StorageContractError("WORKSPACE_NOT_VAULT")
        if any(part in {"", ".", ".."} for part in relative.parts):
            raise StorageContractError("WORKSPACE_NOT_VAULT")
        fd = os.open(relative.as_posix(), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=binding.mount_fd)
        try:
            return WorkspaceHandle.from_verified_fds(
                mount_fd=binding.mount_fd, workspace_fd=fd,
                storage_transaction_id=binding.transaction_id,
                apfs_volume_uuid=binding.apfs_volume_uuid,
                relative_path=relative,
                fd_probe=self._fd_probe,
            )
        finally:
            os.close(fd)


__all__ = ["MountFacts", "StorageBinding", "StorageContract", "StorageContractError", "StorageStatus", "probe_mount_fd"]
