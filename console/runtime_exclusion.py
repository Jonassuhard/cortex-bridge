"""Process-lifetime exclusion for servers sharing one Cortex home.

This supplements, not replaces, managed-start/storage admission. Older
servers which do not acquire this lock are not covered by this mechanism.
"""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import time

from lifecycle_lock import LifecycleLockTimeout, open_lifecycle_lock


class RuntimeAlreadyRunning(RuntimeError):
    def __init__(self):
        super().__init__("RUNTIME_ALREADY_RUNNING")


@contextmanager
def exclusive_runtime(home: Path):
    path = Path(home).resolve(strict=True) / ".runtime.lock"
    descriptor = None
    try:
        try:
            descriptor = open_lifecycle_lock(path, deadline=time.monotonic() + 0.2)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, LifecycleLockTimeout):
            raise RuntimeAlreadyRunning() from None
        opened = os.fstat(descriptor)
        named = path.stat(follow_symlinks=False)
        if (not stat.S_ISREG(named.st_mode)
                or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)):
            raise RuntimeError("RUNTIME_LOCK_CHANGED")
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
