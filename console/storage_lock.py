"""Canonical ordered locks for the storage runtime."""

from __future__ import annotations

import fcntl
import math
import os
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import ContextManager, Literal, Self, Any

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


@dataclass(slots=True)
class StorageLockSet:
    """The S3 lock bundle.

    ``ordered_storage_locks`` predates S3 and intentionally keeps returning its
    two-value tuple for compatibility.  New code should use
    ``open_storage_lock_set``; this object is also iterable so callers migrating
    from the legacy tuple do not accidentally lose the storage lock.
    """

    home: Path
    home_dev_u32: int
    home_ino: int
    home_uid: int
    home_mode: int
    install_fd: int
    install_dev_u32: int
    install_ino: int
    install_uid: int
    storage_fd: int
    storage_dev_u32: int
    storage_ino: int
    storage_uid: int
    admission_fd: int
    admission_dev_u32: int
    admission_ino: int
    admission_uid: int
    install_mode: LockMode
    storage_mode: LockMode
    admission_mode: Literal["exclusive"] = "exclusive"
    marker_mode: Literal[384] = 0o600
    deadline_ns: int = 0
    active: bool = True
    _install_adopted: bool = field(default=False, repr=False)
    _storage_lock: StorageLock | None = field(default=None, repr=False)

    def __iter__(self):
        # Compatibility with ``as (install_fd, storage_lock)``.
        yield self.install_fd
        if self._storage_lock is None:
            self._storage_lock = StorageLock(self.storage_fd, self.storage_mode)
        yield self._storage_lock

    def assert_active(self, *, home: Path, required_install_mode: LockMode, required_storage_mode: LockMode) -> None:
        if not self.active or Path(home).resolve(strict=False) != self.home:
            raise StorageLockError("STORAGE_LOCK_INACTIVE")
        if self.install_mode not in {"shared", "exclusive"} or self.storage_mode not in {"shared", "exclusive"}:
            raise StorageLockError("STORAGE_LOCK_MODE")
        if self.admission_mode != "exclusive":
            raise StorageLockError("STORAGE_LOCK_MODE")
        if required_install_mode == "exclusive" and self.install_mode != "exclusive":
            raise StorageLockError("STORAGE_LOCK_MODE")
        if required_storage_mode == "exclusive" and self.storage_mode != "exclusive":
            raise StorageLockError("STORAGE_LOCK_MODE")
        if os.getuid() != self.home_uid:
            raise StorageLockError("STORAGE_LOCK_OWNER")
        try:
            home_details = os.stat(self.home, follow_symlinks=False)
        except OSError as exc:
            raise StorageLockError("STORAGE_LOCK_REPLACED") from exc
        if (
            home_details.st_ino != self.home_ino
            or (home_details.st_dev & 0xFFFFFFFF) != self.home_dev_u32
            or home_details.st_uid != self.home_uid
            or stat.S_IMODE(home_details.st_mode) != self.home_mode
            or not stat.S_ISDIR(home_details.st_mode)
        ):
            raise StorageLockError("STORAGE_LOCK_REPLACED")
        for fd, dev, ino, uid in (
            (self.install_fd, self.install_dev_u32, self.install_ino, self.install_uid),
            (self.storage_fd, self.storage_dev_u32, self.storage_ino, self.storage_uid),
            (self.admission_fd, self.admission_dev_u32, self.admission_ino, self.admission_uid),
        ):
            try:
                current = os.fstat(fd)
            except OSError as exc:
                raise StorageLockError("STORAGE_LOCK_REPLACED") from exc
            if (
                (current.st_dev & 0xFFFFFFFF, current.st_ino, current.st_uid)
                != (dev, ino, uid)
                or not stat.S_ISREG(current.st_mode)
                or stat.S_IMODE(current.st_mode) != self.marker_mode
                or current.st_nlink != 1
            ):
                raise StorageLockError("STORAGE_LOCK_REPLACED")

    def close(self) -> None:
        if not self.active:
            return
        self.active = False
        for fd in (self.admission_fd, self.storage_fd):
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                try:
                    os.close(fd)
                except OSError:
                    pass
        try:
            if not self._install_adopted:
                fcntl.flock(self.install_fd, fcntl.LOCK_UN)
        finally:
            try:
                os.close(self.install_fd)
            except OSError:
                pass
        if self._storage_lock is not None:
            self._storage_lock._closed = True

    def __enter__(self) -> Self:
        self.assert_active(home=self.home, required_install_mode="shared", required_storage_mode="shared")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


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


@contextmanager
def open_storage_lock_set(
    home: Path,
    *,
    install_mode: LockMode,
    storage_mode: LockMode,
    timeout_seconds: float = 5.0,
    bootstrap_install: Any | None = None,
) -> ContextManager[StorageLockSet]:
    """Acquire install → storage → admission under one common deadline."""
    home = Path(home).resolve(strict=True)
    checked_install = _require_mode(install_mode)
    checked_storage = _require_mode(storage_mode)
    timeout = _require_timeout(timeout_seconds)
    deadline = _deadline(timeout)
    install_fd: int | None = None
    install_adopted = False
    storage_fd: int | None = None
    admission_fd: int | None = None
    try:
        try:
            if bootstrap_install is None:
                install_fd = open_lifecycle_lock(home / ".install.lock", deadline=deadline)
                _acquire(install_fd, checked_install, deadline)
            else:
                if checked_install != "shared":
                    raise StorageLockError("STORAGE_LOCK_MODE")
                if (
                    not getattr(bootstrap_install, "active", False)
                    or Path(getattr(bootstrap_install, "home", "")).resolve(strict=False) != home
                ):
                    raise StorageLockError("STORAGE_LOCK_INACTIVE")
                source_fd = getattr(bootstrap_install, "install_lock_fd", -1)
                try:
                    source_details = os.fstat(source_fd)
                    path_details = os.stat(
                        home / ".install.lock", follow_symlinks=False
                    )
                except OSError as exc:
                    raise StorageLockError("STORAGE_LOCK_REPLACED") from exc
                if (
                    not stat.S_ISREG(source_details.st_mode)
                    or not stat.S_ISREG(path_details.st_mode)
                    or source_details.st_uid != os.getuid()
                    or stat.S_IMODE(source_details.st_mode) != 0o600
                    or source_details.st_nlink != 1
                    or (
                        source_details.st_dev,
                        source_details.st_ino,
                        source_details.st_uid,
                    )
                    != (
                        path_details.st_dev,
                        path_details.st_ino,
                        path_details.st_uid,
                    )
                    or (
                        source_details.st_dev & 0xFFFFFFFF,
                        source_details.st_ino,
                        source_details.st_uid,
                        stat.S_IMODE(source_details.st_mode),
                    )
                    != (
                        getattr(bootstrap_install, "install_lock_dev_u32", None),
                        getattr(bootstrap_install, "install_lock_ino", None),
                        getattr(bootstrap_install, "install_lock_uid", None),
                        getattr(bootstrap_install, "install_lock_mode", None),
                    )
                ):
                    raise StorageLockError("STORAGE_LOCK_REPLACED")
                install_fd = os.dup(source_fd)
                install_adopted = True
            storage_fd = open_lifecycle_lock(home / _LOCK_NAME, deadline=deadline)
            _acquire(storage_fd, checked_storage, deadline)
            admission_path = home / "storage-admission.lock"
            admission_fd = open_lifecycle_lock(admission_path, deadline=deadline)
            _acquire(admission_fd, "exclusive", deadline)
        except StorageLockError:
            raise
        except LifecycleLockTimeout as exc:
            raise StorageLockError("STORAGE_LOCK_TIMEOUT") from exc
        except RuntimeError as exc:
            raise StorageLockError("STORAGE_LOCK_UNSAFE") from exc
        home_details = os.stat(home, follow_symlinks=False)
        install_details = os.fstat(install_fd)
        storage_details = os.fstat(storage_fd)
        admission_details = os.fstat(admission_fd)
        result = StorageLockSet(
            home=Path(home), home_dev_u32=home_details.st_dev & 0xFFFFFFFF,
            home_ino=home_details.st_ino, home_uid=home_details.st_uid,
            home_mode=stat.S_IMODE(home_details.st_mode), install_fd=install_fd,
            install_dev_u32=install_details.st_dev & 0xFFFFFFFF,
            install_ino=install_details.st_ino, install_uid=install_details.st_uid,
            storage_fd=storage_fd, storage_dev_u32=storage_details.st_dev & 0xFFFFFFFF,
            storage_ino=storage_details.st_ino, storage_uid=storage_details.st_uid,
            admission_fd=admission_fd, admission_dev_u32=admission_details.st_dev & 0xFFFFFFFF,
            admission_ino=admission_details.st_ino, admission_uid=admission_details.st_uid,
            install_mode=checked_install, storage_mode=checked_storage,
            deadline_ns=time.monotonic_ns() + int(timeout * 1_000_000_000),
            _install_adopted=install_adopted,
        )
        install_fd = storage_fd = admission_fd = None
        try:
            yield result
        finally:
            result.close()
    finally:
        for fd in (admission_fd, storage_fd, install_fd):
            if fd is not None:
                try:
                    if fd != install_fd or not install_adopted:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)
