"""Single fail-closed storage authority used by runtime and mission admission."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Self
from uuid import UUID

from executor.workspace_handle import MountFacts, WorkspaceHandle
from executor import fd_ops
from storage_result import StorageStatus
from storage_transition import runtime_transition_status_locked, load_transition_locked
from storage_broker import MountedImageProof


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
            try:
                with self._open_binding_locked(lock_set, exclusive=False):
                    pass
            except Exception:
                return StorageStatus("UNCLEAR", "STORAGE_NOT_READY", status.transaction_id,
                                     status.storage_state, False, False)
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
        return self._open_binding_locked(lock_set, exclusive=True)

    def _open_binding_locked(self, lock_set: Any, *, exclusive: bool) -> StorageBinding:
        self._assert(lock_set, exclusive=exclusive)
        status = runtime_transition_status_locked(lock_set, self._home)
        if status.code != "STORAGE_READY" or not status.transaction_id:
            raise StorageContractError("STORAGE_NOT_READY")
        mount_path = Path(self._environment.get("CORTEX_STORAGE_MOUNT", self._home / "mount"))
        root_path = Path(self._environment.get("CORTEX_STORAGE_ROOT", mount_path / "20_WORKSPACES"))
        if root_path != mount_path / "20_WORKSPACES":
            raise StorageContractError("STORAGE_ROOT_NOT_MANAGED")
        if mount_path.is_symlink() or root_path.is_symlink() or not mount_path.is_dir() or not root_path.is_dir():
            raise StorageContractError("STORAGE_MOUNT_NOT_READY")
        host_fd = os.open(self._home, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        mount_fd: int | None = None
        root_fd: int | None = None
        try:
            mount_fd = os.open(mount_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
            # Derive the root from the retained mount, never reopen an absolute
            # root that may now name another same-device directory.
            try:
                root_fd = fd_ops.open_directory_at(mount_fd, "20_WORKSPACES")
            except (OSError, ValueError) as exc:
                raise StorageContractError("STORAGE_ROOT_NOT_MANAGED") from exc
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
            try:
                named_mount = os.stat(mount_path, follow_symlinks=False)
                named_root = os.stat("20_WORKSPACES", dir_fd=mount_fd, follow_symlinks=False)
            except OSError as exc:
                raise StorageContractError("STORAGE_DESCRIPTOR_CHANGED") from exc
            if any(not stat.S_ISDIR(named.st_mode)
                   or (named.st_dev, named.st_ino) != (held.st_dev, held.st_ino)
                   for named, held in ((named_mount, mount_stat), (named_root, root_stat))):
                raise StorageContractError("STORAGE_DESCRIPTOR_CHANGED")
            try:
                observed_uuid = facts.volume_uuid
                parsed_uuid = UUID(observed_uuid) if type(observed_uuid) is str else None
                if parsed_uuid is None or parsed_uuid.int == 0 or str(parsed_uuid) != observed_uuid:
                    raise ValueError('missing or invalid observed UUID')
            except ValueError as exc:
                raise StorageContractError("STORAGE_VOLUME_IDENTITY_UNAVAILABLE") from exc
            configured_uuid = self._environment.get("CORTEX_STORAGE_APFS_VOLUME_UUID")
            if configured_uuid is not None and configured_uuid != observed_uuid:
                raise StorageContractError("STORAGE_VOLUME_IDENTITY_MISMATCH")
            # The APFS observation alone says nothing about encryption or which
            # image owns this mount. Only the private broker can prove that link.
            encryption_uuid = self._prove_image_locked(
                lock_set, status.transaction_id, mount_path, mount_stat, facts)
            return StorageBinding(
                status.transaction_id, host_fd, mount_fd, root_fd,
                self._environment.get("CORTEX_STORAGE_HOST_VOLUME_UUID", "unknown"),
                (0, 0), facts.st_dev_u32, facts.fsid_u32,
                observed_uuid,
                encryption_uuid,
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

    def _prove_image_locked(self, lock_set: Any, transaction_id: str,
                            mount_path: Path, mount_stat: os.stat_result,
                            facts: MountFacts) -> str:
        host_fd = image_fd = None
        try:
            journal = load_transition_locked(lock_set, self._home)
            if journal is None or journal.transaction_id != transaction_id or journal.phase != 'committed':
                raise ValueError('journal mismatch')
            value = journal.target_encryption_uuid
            encryption = UUID(value) if type(value) is str else None
            if encryption is None or not encryption.int or str(encryption) != value:
                raise ValueError('encryption identity missing')
            configured = self._environment.get('CORTEX_STORAGE_ENCRYPTION_UUID')
            if configured is not None and configured != value:
                raise ValueError('encryption identity mismatch')
            host = Path(self._environment.get('CORTEX_STORAGE_HOST', self._home / 'storage'))
            image = host / journal.target_image_basename
            if (Path(self._environment.get('CORTEX_STORAGE_IMAGE', image)) != image
                    or self._environment.get('CORTEX_STORAGE_IMAGE_BASENAME', journal.target_image_basename) != journal.target_image_basename
                    or self._environment.get('CORTEX_STORAGE_VOLUME_NAME', 'CORTEX_BRIDGE_2026_09') != 'CORTEX_BRIDGE_2026_09'):
                raise ValueError('managed image mismatch')
            host_fd = os.open(host, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            image_fd = fd_ops.open_directory_at(host_fd, journal.target_image_basename)
            image_stat = os.fstat(image_fd)
            proof = self._broker._probe_mounted_image_locked(
                lock_set, image_path=image, mount_path=mount_path,
                expected_volume_name='CORTEX_BRIDGE_2026_09',
                expected_volume_uuid=UUID(facts.volume_uuid), expected_encryption_uuid=encryption,
                image_identity=(image_stat.st_dev & 0xffffffff, image_stat.st_ino),
                mount_identity=(mount_stat.st_dev & 0xffffffff, mount_stat.st_ino, *facts.fsid_u32),
                expected_mapping_count=1, effect_budget_ns=5_000_000_000)
            if (not isinstance(proof, MountedImageProof)
                    or proof.mount_path != mount_path
                    or (proof.image_dev_u32, proof.image_ino) != (image_stat.st_dev & 0xffffffff, image_stat.st_ino)
                    or (proof.mount_dev_u32, proof.mount_ino, proof.mount_fsid0_u32, proof.mount_fsid1_u32)
                    != (mount_stat.st_dev & 0xffffffff, mount_stat.st_ino, *facts.fsid_u32)
                    or proof.volume_uuid != UUID(facts.volume_uuid) or proof.encryption_uuid != encryption
                    or proof.volume_name != 'CORTEX_BRIDGE_2026_09' or proof.filesystem_type != 'apfs'
                    or type(proof.mapping_count) is not int or proof.mapping_count != 1
                    or proof.writable is not True or proof.encrypted is not True):
                raise ValueError('mounted image proof mismatch')
            named = os.stat(journal.target_image_basename, dir_fd=host_fd, follow_symlinks=False)
            if not stat.S_ISDIR(named.st_mode) or (named.st_dev, named.st_ino) != (image_stat.st_dev, image_stat.st_ino):
                raise ValueError('image replaced during proof')
            return value
        except Exception as exc:
            raise StorageContractError('STORAGE_ENCRYPTED_IMAGE_UNPROVEN') from exc
        finally:
            for descriptor in (image_fd, host_fd):
                if descriptor is not None:
                    os.close(descriptor)

    def revalidate_locked(self, lock_set: Any, binding: StorageBinding) -> MountFacts:
        self._assert(lock_set, exclusive=True)
        if binding._closed:
            raise StorageContractError("STORAGE_BINDING_CLOSED")
        facts = self._fd_probe(binding.mount_fd)
        if (facts.st_dev_u32 != binding.mount_device_u32
                or facts.fsid_u32 != binding.mount_fsid_u32
                or facts.volume_uuid != binding.apfs_volume_uuid):
            raise StorageContractError("STORAGE_DESCRIPTOR_CHANGED")
        return facts

    def open_workspace_locked(self, lock_set: Any, binding: StorageBinding, requested: str | Path) -> WorkspaceHandle:
        self._assert(lock_set, exclusive=True)
        if binding._closed:
            raise StorageContractError("STORAGE_BINDING_CLOSED")
        if not isinstance(requested, (str, Path)):
            raise TypeError("workspace path must be text or Path")
        value = str(requested)
        try:
            parts = fd_ops.components(value)
            if not parts or parts[0] != "20_WORKSPACES":
                raise ValueError("Workspace root required")
        except (ValueError, TypeError) as exc:
            raise StorageContractError("WORKSPACE_NOT_VAULT") from exc
        relative = PurePosixPath(*parts)
        try:
            fd = fd_ops.open_directory_at(binding.mount_fd, value)
        except OSError as exc:
            raise StorageContractError("WORKSPACE_NOT_VAULT") from exc
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
