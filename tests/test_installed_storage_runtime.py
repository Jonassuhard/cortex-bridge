from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from installed_storage_runtime import InstalledRuntimeError, InstalledStorageRuntime
from storage_broker import AttestedBootstrapHandle


class FakeLocks:
    def __init__(self, home):
        self.home = home
    def assert_active(self, *, home, required_install_mode, required_storage_mode):
        if Path(home) != self.home:
            raise RuntimeError("wrong home")


class InstalledRuntimeTests(unittest.TestCase):
    def test_factory_refuses_missing_generation_before_attestation(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir()
            fds = [os.open(home / f"f{i}", os.O_RDWR | os.O_CREAT, 0o600) for i in range(6)]
            def close_all():
                for fd in fds:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
            self.addCleanup(close_all)
            handle = AttestedBootstrapHandle(
                home=home,
                install_lock_fd=fds[0], install_lock_dev_u32=1, install_lock_ino=2,
                install_lock_uid=os.getuid(), install_lock_mode=0o600,
                selector_fd=fds[1], generation_dir_fd=fds[2], generation_record_fd=fds[3],
                owned_manifest_fd=fds[4], interpreter_fd=fds[5], generation_id=uuid4(),
                selector_sha256="a" * 64, generation_record_sha256="b" * 64,
                owned_manifest_sha256="c" * 64,
            )
            with self.assertRaises(InstalledRuntimeError):
                InstalledStorageRuntime.from_installed_home_locked(home, FakeLocks(home), handle)
            handle.close()


if __name__ == "__main__":
    unittest.main()
