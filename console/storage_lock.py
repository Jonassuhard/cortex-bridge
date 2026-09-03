"""Canonical ordered locks for the storage runtime."""

from __future__ import annotations

import fcntl
import math
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import ContextManager, Literal, Self

from lifecycle_lock import (
    LifecycleLockTimeout,
    _open_existing_lock,
    _open_pinned_directory_chain,
    _validate_open_lock,
    open_lifecycle_lock,
)


LockMode = Literal["shared", "exclusive"]
_LOCK_NAME = "storage-state.lock"
_POLL_SECONDS = 0.02


class StorageLockError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _require_mode(mode: object) -> LockMode:
    if type(mode) is not str or mode not in {"shared", "exclusive"}:
        raise ValueError("storage lock mode is invalid")
    return mode  # type: ignore[return-value]


def _require_timeout(value: object) -> float:
    if (
        type(value) not in {int, float}
        or not math.isfinite(float(value))
        or value < 0
    ):
        raise ValueError("storage lock timeout is invalid")
    return float(value)


def _deadline(timeout_seconds: float) -> float:
    return time.monotonic() + timeout_seconds


def _acquire(fd: int, mode: LockMode, deadline: float) -> None:
    flag = fcntl.LOCK_SH if mode == "shared" else fcntl.LOCK_EX
    while True:
        try:
            fcntl.flock(fd, flag | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise StorageLockError("STORAGE_LOCK_TIMEOUT")
            time.sleep(min(_POLL_SECONDS, remaining))
        except OSError as exc:
            raise StorageLockError("STORAGE_LOCK_UNSAFE") from exc


@dataclass
class StorageLock:
    fd: int
    mode: LockMode
    _closed: bool = field(default=False, init=False, repr=False)

    def close(self) -> None:
        if self._closed:
            return
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)
            self._closed = True

    def __enter__(self) -> Self:
        if self._closed:
            raise RuntimeError("storage lock is closed")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _open_existing_marker(home: Path, deadline: float) -> int:
    if home.is_symlink() or not home.exists() or not home.is_dir():
        raise StorageLockError("STORAGE_LOCK_MISSING")
    descriptors: list[int] | None = None
    fd: int | None = None
    try:
        descriptors, _names, _device = _open_pinned_directory_chain(home)
        directory_fd = descriptors[-1]
        try:
            fd, _writable = _open_existing_lock(directory_fd, _LOCK_NAME)
        except FileNotFoundError as exc:
            raise StorageLockError("STORAGE_LOCK_MISSING") from exc
        _validate_open_lock(fd, directory_fd, _LOCK_NAME, home / _LOCK_NAME)
        result = fd
        fd = None
        return result
    except StorageLockError:
        raise
    except (OSError, RuntimeError) as exc:
        raise StorageLockError("STORAGE_LOCK_UNSAFE") from exc
    finally:
        if fd is not None:
            os.close(fd)
        if descriptors is not None:
            for descriptor in reversed(descriptors):
                os.close(descriptor)


def open_storage_lock(
    home: Path,
    mode: LockMode,
    *,
    timeout_seconds: float = 5.0,
) -> StorageLock:
    lock_mode = _require_mode(mode)
    timeout = _require_timeout(timeout_seconds)
    return _open_storage_lock_until(home, lock_mode, _deadline(timeout))


def _open_storage_lock_until(
    home: Path,
    mode: LockMode,
    deadline: float,
) -> StorageLock:
    try:
        fd = open_lifecycle_lock(home / _LOCK_NAME, deadline=deadline)
    except LifecycleLockTimeout as exc:
        raise StorageLockError("STORAGE_LOCK_TIMEOUT") from exc
    except RuntimeError as exc:
        raise StorageLockError("STORAGE_LOCK_UNSAFE") from exc
    try:
        _acquire(fd, mode, deadline)
    except BaseException:
        os.close(fd)
        raise
    return StorageLock(fd=fd, mode=mode)


def open_existing_storage_lock(
    home: Path,
    mode: LockMode,
    *,
    timeout_seconds: float = 5.0,
) -> StorageLock:
    lock_mode = _require_mode(mode)
    timeout = _require_timeout(timeout_seconds)
    deadline = _deadline(timeout)
    fd = _open_existing_marker(home, deadline)
    try:
        _acquire(fd, lock_mode, deadline)
    except BaseException:
        os.close(fd)
        raise
    return StorageLock(fd=fd, mode=lock_mode)


@contextmanager
def ordered_storage_locks(
    home: Path,
    *,
    install_mode: LockMode | None,
    storage_mode: LockMode,
    timeout_seconds: float = 5.0,
) -> ContextManager[tuple[int | None, StorageLock]]:
    timeout = _require_timeout(timeout_seconds)
    deadline = _deadline(timeout)
    checked_storage_mode = _require_mode(storage_mode)
    install_fd: int | None = None
    storage_lock: StorageLock | None = None
    try:
        if install_mode is not None:
            checked_install_mode = _require_mode(install_mode)
            try:
                install_fd = open_lifecycle_lock(home / ".install.lock", deadline=deadline)
            except LifecycleLockTimeout as exc:
                raise StorageLockError("STORAGE_LOCK_TIMEOUT") from exc
            except RuntimeError as exc:
                raise StorageLockError("STORAGE_LOCK_UNSAFE") from exc
            _acquire(install_fd, checked_install_mode, deadline)
        storage_lock = _open_storage_lock_until(home, checked_storage_mode, deadline)
        yield install_fd, storage_lock
    finally:
        if storage_lock is not None:
            storage_lock.close()
        if install_fd is not None:
            try:
                fcntl.flock(install_fd, fcntl.LOCK_UN)
            finally:
                os.close(install_fd)
