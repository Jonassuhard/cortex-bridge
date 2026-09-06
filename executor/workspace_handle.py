"""Vault-only descriptor handle used by mission admission.

The handle accepts only a verified mount/workspace descriptor pair and a
relative path below ``20_WORKSPACES``.  It never accepts an absolute local path
or a local-alias shaped object.  FDs are duplicated on construction so the
caller may safely close its originals.
"""

from __future__ import annotations

import fcntl
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Self


DarwinU32 = int


@dataclass(frozen=True, slots=True)
class MountFacts:
    st_dev_u32: DarwinU32
    fsid_u32: tuple[DarwinU32, DarwinU32]
    flags: int
    filesystem_type: str
    mount_from: str
    mount_on: str


@dataclass(frozen=True, slots=True)
class WorkspaceIdentity:
    storage_transaction_id: str
    mount_dev_u32: DarwinU32
    mount_fsid_u32: tuple[DarwinU32, DarwinU32]
    workspace_dev_u32: DarwinU32
    workspace_ino: int
    apfs_volume_uuid: str
    relative_path: PurePosixPath


class WorkspaceHandleClosed(RuntimeError):
    pass


class WorkspaceIdentityChanged(RuntimeError):
    pass


def _dup(fd: int) -> int:
    if not isinstance(fd, int) or fd < 0:
        raise TypeError("workspace descriptor is invalid")
    return fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 3)


def _normalize_relative(value: PurePosixPath) -> PurePosixPath:
    if not isinstance(value, PurePosixPath) or value.is_absolute():
        raise ValueError("workspace path must be relative")
    if not value.parts or value.parts[0] != "20_WORKSPACES":
        raise ValueError("workspace path is outside 20_WORKSPACES")
    if any(part in {"", ".", ".."} for part in value.parts):
        raise ValueError("workspace path contains unsafe component")
    return value


class WorkspaceHandle:
    def __init__(
        self,
        *,
        mount_fd: int,
        workspace_fd: int,
        identity: WorkspaceIdentity,
        fd_probe: Callable[[int], MountFacts],
    ) -> None:
        self._mount_fd = mount_fd
        self._workspace_fd = workspace_fd
        self._identity = identity
        self._fd_probe = fd_probe
        self._closed = False

    @classmethod
    def from_verified_fds(
        cls,
        *,
        mount_fd: int,
        workspace_fd: int,
        storage_transaction_id: str,
        apfs_volume_uuid: str,
        relative_path: PurePosixPath,
        fd_probe: Callable[[int], MountFacts],
    ) -> Self:
        relative = _normalize_relative(relative_path)
        if not isinstance(storage_transaction_id, str) or not storage_transaction_id:
            raise ValueError("storage transaction id is required")
        if not isinstance(apfs_volume_uuid, str) or not apfs_volume_uuid:
            raise ValueError("APFS volume UUID is required")
        mount_dup = _dup(mount_fd)
        try:
            workspace_dup = _dup(workspace_fd)
        except BaseException:
            os.close(mount_dup)
            raise
        try:
            mount_stat = os.fstat(mount_dup)
            workspace_stat = os.fstat(workspace_dup)
            if not stat.S_ISDIR(mount_stat.st_mode) or not stat.S_ISDIR(workspace_stat.st_mode):
                raise ValueError("workspace descriptors must be directories")
            if mount_stat.st_dev != workspace_stat.st_dev:
                raise ValueError("workspace is on a different device")
            facts = fd_probe(mount_dup)
            if not isinstance(facts, MountFacts) or facts.st_dev_u32 != (mount_stat.st_dev & 0xFFFFFFFF):
                raise ValueError("mount descriptor identity is invalid")
            identity = WorkspaceIdentity(
                storage_transaction_id,
                facts.st_dev_u32,
                facts.fsid_u32,
                workspace_stat.st_dev & 0xFFFFFFFF,
                workspace_stat.st_ino,
                apfs_volume_uuid,
                relative,
            )
            return cls(mount_fd=mount_dup, workspace_fd=workspace_dup, identity=identity, fd_probe=fd_probe)
        except BaseException:
            os.close(mount_dup)
            os.close(workspace_dup)
            raise

    def _ensure_open(self) -> None:
        if self._closed:
            raise WorkspaceHandleClosed("workspace handle is closed")

    @property
    def identity(self) -> WorkspaceIdentity:
        self._ensure_open()
        return self._identity

    @property
    def mount_fd(self) -> int:
        self._ensure_open()
        return self._mount_fd

    @property
    def workspace_fd(self) -> int:
        self._ensure_open()
        return self._workspace_fd

    @property
    def display_path(self) -> str:
        self._ensure_open()
        return self._identity.relative_path.as_posix()

    def revalidate(self) -> WorkspaceIdentity:
        self._ensure_open()
        mount_stat = os.fstat(self._mount_fd)
        workspace_stat = os.fstat(self._workspace_fd)
        facts = self._fd_probe(self._mount_fd)
        current = (
            facts.st_dev_u32,
            facts.fsid_u32,
            workspace_stat.st_dev & 0xFFFFFFFF,
            workspace_stat.st_ino,
        )
        expected = (
            self._identity.mount_dev_u32,
            self._identity.mount_fsid_u32,
            self._identity.workspace_dev_u32,
            self._identity.workspace_ino,
        )
        if (
            not stat.S_ISDIR(mount_stat.st_mode)
            or not stat.S_ISDIR(workspace_stat.st_mode)
            or current != expected
            or facts.st_dev_u32 != (mount_stat.st_dev & 0xFFFFFFFF)
        ):
            raise WorkspaceIdentityChanged("workspace descriptor identity changed")
        return self._identity

    def duplicate_workspace_fd(self) -> int:
        self._ensure_open()
        return _dup(self._workspace_fd)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for fd in (self._workspace_fd, self._mount_fd):
            try:
                os.close(fd)
            except OSError:
                pass

    def __enter__(self) -> Self:
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


__all__ = [
    "MountFacts", "WorkspaceIdentity", "WorkspaceHandle", "WorkspaceHandleClosed",
    "WorkspaceIdentityChanged",
]
