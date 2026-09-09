"""Descriptor-relative primitives; callers retain ownership of the root FD.

No absolute-path reopening, symlink traversal or cross-device traversal.
Write publication and process launch are separate, not implemented here.
"""
from contextlib import contextmanager
import ctypes
import errno
import os
import stat

_libc = ctypes.CDLL(None, use_errno=True)
_renameatx_np = getattr(_libc, "renameatx_np", None)
if _renameatx_np is not None:
    _renameatx_np.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    _renameatx_np.restype = ctypes.c_int


def components(relative: str) -> tuple[str, ...]:
    if type(relative) is not str:
        raise TypeError("Relative path must be a string")
    if relative == ".":
        return ()
    if not relative or relative.startswith(("/", "~")) or "\\" in relative or "\x00" in relative:
        raise ValueError("Invalid relative path")
    parts = tuple(relative.split("/"))
    if any(part in ("", ".", "..") or len(os.fsencode(part)) > 255 for part in parts):
        raise ValueError("Invalid relative component")
    return parts


def _leaf(name):
    parts = components(name)
    if len(parts) != 1:
        raise ValueError("Expected one relative leaf name")
    return parts[0]


def fsync_directory(fd: int) -> None:
    if not stat.S_ISDIR(os.fstat(fd).st_mode):
        raise OSError(errno.ENOTDIR, "Directory descriptor required")
    os.fsync(fd)


def stat_at(parent_fd: int, name: str) -> os.stat_result:
    return os.stat(_leaf(name), dir_fd=parent_fd, follow_symlinks=False)


def create_directory_at(parent_fd: int, name: str, *, mode: int = 0o700) -> os.stat_result:
    name = _leaf(name)
    if type(mode) is not int or mode < 0 or mode > 0o777:
        raise ValueError("Invalid directory permissions")
    os.mkdir(name, mode, dir_fd=parent_fd)
    descriptor = open_directory_at(parent_fd, name)
    try:
        fsync_directory(descriptor)
        fsync_directory(parent_fd)
        return os.fstat(descriptor)
    finally:
        os.close(descriptor)


def rename_exclusive_at(src_dir_fd: int, src: str, dst_dir_fd: int, dst: str) -> None:
    src, dst = _leaf(src), _leaf(dst)
    if _renameatx_np is None:
        raise OSError(errno.ENOSYS, "RENAME_EXCL_UNAVAILABLE")
    if _renameatx_np(src_dir_fd, os.fsencode(src), dst_dir_fd, os.fsencode(dst), 0x00000004) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), dst)


def rename_exchange_at(src_dir_fd: int, src: str, dst_dir_fd: int, dst: str) -> None:
    """Atomically exchange two existing names; retain both inodes.

    RENAME_SWAP is defined as 0x2 by the macOS SDK sys/stdio.h.
    This is not compare-and-swap: callers must verify the displaced identity.
    """
    src, dst = _leaf(src), _leaf(dst)
    if _renameatx_np is None:
        raise OSError(errno.ENOSYS, "RENAME_SWAP_UNAVAILABLE")
    if _renameatx_np(src_dir_fd, os.fsencode(src), dst_dir_fd, os.fsencode(dst), 0x00000002) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), dst)


def _directory(fd, device):
    details = os.fstat(fd)
    if not stat.S_ISDIR(details.st_mode) or details.st_dev != device:
        raise OSError(errno.EXDEV, "Directory outside retained workspace device")


def open_directory_at(root_fd: int, relative: str = ".") -> int:
    parts = components(relative)
    device = os.fstat(root_fd).st_dev
    current = os.dup(root_fd)
    try:
        _directory(current, device)
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=current)
            try:
                _directory(child, device)
            except BaseException:
                os.close(child)
                raise
            os.close(current)
            current = child
        return current
    except BaseException:
        os.close(current)
        raise


@contextmanager
def open_parent(root_fd: int, relative: str):
    parts = components(relative)
    if not parts:
        raise ValueError("A leaf name is required")
    descriptor = open_directory_at(root_fd, "/".join(parts[:-1]) or ".")
    try:
        yield descriptor, parts[-1]
    finally:
        os.close(descriptor)


def open_regular_at(root_fd: int, relative: str, *, writable: bool = False) -> int:
    if type(writable) is not bool:
        raise TypeError("writable must be boolean")
    device = os.fstat(root_fd).st_dev
    with open_parent(root_fd, relative) as (parent, leaf):
        flags = (os.O_RDWR if writable else os.O_RDONLY) | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        descriptor = os.open(leaf, flags, dir_fd=parent)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_dev != device:
                raise OSError(errno.EPERM, "Expected single-link regular file on workspace device")
            after = os.fstat(descriptor)
            fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_nlink")
            if any(getattr(before, key) != getattr(after, key) for key in fields):
                raise OSError(errno.ESTALE, "File changed during admission")
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise
