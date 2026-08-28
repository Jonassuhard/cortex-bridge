"""Canonical lifecycle-lock publication and validation."""

from __future__ import annotations

import ctypes
import errno
import os
import secrets
import stat
import sys
from pathlib import Path


LIFECYCLE_LOCK_MARKER = (
    b'{"owner":"cortex-bridge","schema_version":1,'
    b'"type":"lifecycle_lock"}\n'
)
RENAME_EXCL = 0x00000004
DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)


def ensure_private_directory(path: Path) -> bool:
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=False)
    except FileExistsError:
        try:
            details = path.stat(follow_symlinks=False)
        except OSError as exc:
            raise RuntimeError(f"runtime directory is unsafe: {path}") from exc
        if not stat.S_ISDIR(details.st_mode):
            raise RuntimeError(f"runtime directory is unsafe: {path}")
        return False
    path.chmod(0o700, follow_symlinks=False)
    return True


def _same_identity(details: os.stat_result, expected: tuple[int, int]) -> bool:
    return (details.st_dev, details.st_ino) == expected


def _validate_pinned_directory_chain(
    path: Path,
    descriptors: list[int],
    names: list[str],
    expected_device: int,
) -> None:
    if len(descriptors) != len(names) + 1:
        raise RuntimeError(f"lifecycle lock parent chain is invalid: {path}")
    for parent_fd, name, child_fd in zip(descriptors, names, descriptors[1:]):
        try:
            opened = os.fstat(child_fd)
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise RuntimeError(f"lifecycle lock parent changed: {path}") from exc
        if (
            not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(current.st_mode)
            or not _same_identity(current, (opened.st_dev, opened.st_ino))
        ):
            raise RuntimeError(f"lifecycle lock parent changed: {path}")
    final = os.fstat(descriptors[-1])
    try:
        lexical = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise RuntimeError(f"lifecycle lock parent changed: {path}") from exc
    if (
        not stat.S_ISDIR(final.st_mode)
        or final.st_uid != os.getuid()
        or final.st_dev != expected_device
        or not stat.S_ISDIR(lexical.st_mode)
        or not _same_identity(lexical, (final.st_dev, final.st_ino))
    ):
        raise RuntimeError(f"lifecycle lock parent is unsafe: {path}")


def _open_pinned_directory_chain(path: Path) -> tuple[list[int], list[str], int]:
    if not path.is_absolute() or ".." in path.parts or path == Path(path.anchor):
        raise RuntimeError(f"lifecycle lock parent path is unsafe: {path}")
    components = list(path.parts[1:])
    descriptors: list[int] = []
    names: list[str] = []
    try:
        descriptors.append(os.open(path.anchor, DIRECTORY_FLAGS))
        for position, name in enumerate(components):
            parent_fd = descriptors[-1]
            parent_details = os.fstat(parent_fd)
            if stat.S_IMODE(parent_details.st_mode) & 0o022:
                raise RuntimeError(f"lifecycle lock parent is publicly writable: {path}")
            try:
                child_fd = os.open(name, DIRECTORY_FLAGS, dir_fd=parent_fd)
            except FileNotFoundError:
                try:
                    os.mkdir(name, 0o700, dir_fd=parent_fd)
                except FileExistsError:
                    pass
                except OSError as exc:
                    raise RuntimeError(
                        f"lifecycle lock parent could not be created safely: {path}"
                    ) from exc
                try:
                    child_fd = os.open(name, DIRECTORY_FLAGS, dir_fd=parent_fd)
                except OSError as exc:
                    raise RuntimeError(
                        f"lifecycle lock parent is unsafe after creation race: {path}"
                    ) from exc
            except OSError as exc:
                raise RuntimeError(f"lifecycle lock parent is unsafe: {path}") from exc
            try:
                opened = os.fstat(child_fd)
                current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if (
                    not stat.S_ISDIR(opened.st_mode)
                    or not stat.S_ISDIR(current.st_mode)
                    or not _same_identity(current, (opened.st_dev, opened.st_ino))
                ):
                    raise RuntimeError(f"lifecycle lock parent changed: {path}")
                if position == len(components) - 1:
                    if (
                        opened.st_uid != os.getuid()
                        or opened.st_dev != parent_details.st_dev
                    ):
                        raise RuntimeError(f"lifecycle lock parent is unsafe: {path}")
                descriptors.append(child_fd)
                names.append(name)
            except BaseException:
                os.close(child_fd)
                raise

        expected_device = os.fstat(descriptors[-1]).st_dev
        _validate_pinned_directory_chain(
            path,
            descriptors,
            names,
            expected_device,
        )
        final = os.fstat(descriptors[-1])
        if stat.S_IMODE(final.st_mode) != 0o700:
            os.fchmod(descriptors[-1], 0o700)
            os.fsync(descriptors[-1])
            _validate_pinned_directory_chain(
                path,
                descriptors,
                names,
                expected_device,
            )
            if stat.S_IMODE(os.fstat(descriptors[-1]).st_mode) != 0o700:
                raise RuntimeError(f"lifecycle lock parent is not private: {path}")
        return descriptors, names, expected_device
    except BaseException:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


def _opened_name_matches(fd: int, directory_fd: int, name: str) -> bool:
    try:
        opened = os.fstat(fd)
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError:
        return False
    return (
        stat.S_ISREG(opened.st_mode)
        and stat.S_ISREG(current.st_mode)
        and _same_identity(current, (opened.st_dev, opened.st_ino))
    )


def _rename_exclusive_relative(
    source_dir_fd: int,
    source: str,
    target_dir_fd: int,
    target: str,
) -> None:
    if sys.platform != "darwin":
        raise OSError("renameatx_np is available only on macOS")
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameatx_np = libc.renameatx_np
    except AttributeError as exc:
        raise OSError("renameatx_np is unavailable on this macOS version") from exc
    renameatx_np.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameatx_np.restype = ctypes.c_int
    result = renameatx_np(
        source_dir_fd,
        os.fsencode(source),
        target_dir_fd,
        os.fsencode(target),
        RENAME_EXCL,
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise FileExistsError(error, os.strerror(error), target)
    raise OSError(error, os.strerror(error), target)


def _create_temporary_lock(directory_fd: int, prefix: str) -> tuple[int, str]:
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
    )
    for _attempt in range(128):
        name = f"{prefix}{secrets.token_hex(16)}"
        try:
            return os.open(name, flags, 0o600, dir_fd=directory_fd), name
        except FileExistsError:
            continue
    raise RuntimeError("could not allocate lifecycle lock temporary")


def _validate_open_lock(
    fd: int,
    directory_fd: int,
    name: str,
    lock_path: Path,
) -> None:
    opened = os.fstat(fd)
    home_details = os.fstat(directory_fd)
    try:
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as exc:
        raise RuntimeError(f"lifecycle lock is unsafe: {lock_path}") from exc
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_uid != os.getuid()
        or opened.st_nlink != 1
        or stat.S_IMODE(opened.st_mode) & 0o077
        or opened.st_dev != home_details.st_dev
        or not stat.S_ISREG(current.st_mode)
        or not _same_identity(current, (opened.st_dev, opened.st_ino))
    ):
        raise RuntimeError(f"lifecycle lock is unsafe: {lock_path}")
    os.lseek(fd, 0, os.SEEK_SET)
    marker = os.read(fd, len(LIFECYCLE_LOCK_MARKER) + 1)
    if opened.st_size != len(LIFECYCLE_LOCK_MARKER) or marker != LIFECYCLE_LOCK_MARKER:
        raise RuntimeError(f"lifecycle lock provenance is invalid: {lock_path}")


def open_lifecycle_lock(lock_path: Path) -> int:
    """Open a canonical same-UID lifecycle lock without mutating foreign files."""

    parent_descriptors, parent_names, expected_device = _open_pinned_directory_chain(
        lock_path.parent
    )
    directory_fd = parent_descriptors[-1]
    fd: int | None = None
    temporary_fd: int | None = None
    temporary_name: str | None = None
    existing_flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        _validate_pinned_directory_chain(
            lock_path.parent,
            parent_descriptors,
            parent_names,
            expected_device,
        )
        try:
            fd = os.open(lock_path.name, existing_flags, dir_fd=directory_fd)
        except FileNotFoundError:
            temporary_fd, temporary_name = _create_temporary_lock(
                directory_fd,
                f"{lock_path.name}.init-",
            )
            _validate_pinned_directory_chain(
                lock_path.parent,
                parent_descriptors,
                parent_names,
                expected_device,
            )
            os.fchmod(temporary_fd, 0o600)
            view = memoryview(LIFECYCLE_LOCK_MARKER)
            while view:
                written = os.write(temporary_fd, view)
                if written <= 0:
                    raise OSError("could not write lifecycle lock marker")
                view = view[written:]
            os.fsync(temporary_fd)
            if not _opened_name_matches(
                temporary_fd,
                directory_fd,
                temporary_name,
            ):
                raise RuntimeError(
                    "lifecycle lock temporary changed before publication"
                )
            _validate_pinned_directory_chain(
                lock_path.parent,
                parent_descriptors,
                parent_names,
                expected_device,
            )
            try:
                _rename_exclusive_relative(
                    directory_fd,
                    temporary_name,
                    directory_fd,
                    lock_path.name,
                )
            except FileExistsError:
                if not _opened_name_matches(
                    temporary_fd,
                    directory_fd,
                    temporary_name,
                ):
                    raise RuntimeError(
                        "lifecycle lock temporary changed during publication race"
                    )
                os.unlink(temporary_name, dir_fd=directory_fd)
                os.close(temporary_fd)
                temporary_fd = None
                temporary_name = None
                _validate_pinned_directory_chain(
                    lock_path.parent,
                    parent_descriptors,
                    parent_names,
                    expected_device,
                )
                fd = os.open(lock_path.name, existing_flags, dir_fd=directory_fd)
            else:
                fd = temporary_fd
                temporary_fd = None
                temporary_name = None
                try:
                    _validate_pinned_directory_chain(
                        lock_path.parent,
                        parent_descriptors,
                        parent_names,
                        expected_device,
                    )
                except BaseException:
                    if _opened_name_matches(
                        fd,
                        directory_fd,
                        lock_path.name,
                    ):
                        os.unlink(lock_path.name, dir_fd=directory_fd)
                        os.fsync(directory_fd)
                    raise
                os.fsync(directory_fd)
        except OSError as exc:
            raise RuntimeError(f"lifecycle lock is unsafe: {lock_path}") from exc

        _validate_pinned_directory_chain(
            lock_path.parent,
            parent_descriptors,
            parent_names,
            expected_device,
        )
        _validate_open_lock(fd, directory_fd, lock_path.name, lock_path)
        _validate_pinned_directory_chain(
            lock_path.parent,
            parent_descriptors,
            parent_names,
            expected_device,
        )
        result = fd
        fd = None
        return result
    finally:
        if fd is not None:
            os.close(fd)
        if temporary_fd is not None:
            try:
                if temporary_name is not None and _opened_name_matches(
                    temporary_fd,
                    directory_fd,
                    temporary_name,
                ):
                    os.unlink(temporary_name, dir_fd=directory_fd)
            finally:
                os.close(temporary_fd)
        for descriptor in reversed(parent_descriptors):
            os.close(descriptor)
