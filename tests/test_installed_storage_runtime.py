from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest import mock

from installed_storage_runtime import InstalledRuntimeError, InstalledStorageRuntime
from storage_broker import AttestedBootstrapHandle


class FakeLocks:
    def __init__(self, home):
        self.home = home
    def assert_active(self, *, home, required_install_mode, required_storage_mode):
        if Path(home) != self.home:
            raise RuntimeError("wrong home")


class InstalledRuntimeTests(unittest.TestCase):
    @staticmethod
    def _handle(home: Path, generation_id):
        fds = [
            os.open(home / f"f{i}", os.O_RDWR | os.O_CREAT, 0o600)
            for i in range(6)
        ]
        return AttestedBootstrapHandle(
            home=home,
            install_lock_fd=fds[0], install_lock_dev_u32=1, install_lock_ino=2,
            install_lock_uid=os.getuid(), install_lock_mode=0o600,
            selector_fd=fds[1], generation_dir_fd=fds[2], generation_record_fd=fds[3],
            owned_manifest_fd=fds[4], interpreter_fd=fds[5], generation_id=generation_id,
            selector_sha256="a" * 64, generation_record_sha256="b" * 64,
            owned_manifest_sha256="c" * 64,
        )

    @staticmethod
    def _generation_files(home: Path, generation_id, *, record_digest="b" * 64, manifest_bytes=None):
        generation_dir = home / "installed-generations" / str(generation_id)
        generation_dir.mkdir(parents=True)
        record = {
            "schema_version": 1,
            "generation_id": str(generation_id),
            "generation_record_sha256": record_digest,
        }
        (generation_dir / "generation-record.json").write_text(
            json.dumps(record, sort_keys=True), encoding="utf-8"
        )
        if manifest_bytes is None:
            manifest_bytes = b'{"native_helpers":{},"schema_version":1}'
        (generation_dir / "owned-manifest.json").write_bytes(manifest_bytes)

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

    def test_factory_refuses_generation_record_digest_mismatch_before_attestation(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir()
            generation_id = uuid4()
            self._generation_files(home, generation_id, record_digest="d" * 64)
            handle = self._handle(home, generation_id)
            self.addCleanup(handle.close)
            fake_attestation = SimpleNamespace(close=lambda: None)
            with mock.patch("installed_storage_runtime.attest_broker_executable", return_value=fake_attestation), mock.patch(
                "installed_storage_runtime.attest_mount_probe", return_value=fake_attestation
            ) as mount_probe:
                with self.assertRaises(InstalledRuntimeError):
                    InstalledStorageRuntime.from_installed_home_locked(home, FakeLocks(home), handle)
            mount_probe.assert_not_called()

    def test_factory_refuses_owned_manifest_digest_mismatch_before_attestation(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir()
            generation_id = uuid4()
            manifest = b'{"native_helpers":{},"schema_version":1}'
            self._generation_files(home, generation_id, manifest_bytes=manifest)
            handle = self._handle(home, generation_id)
            handle.owned_manifest_sha256 = "e" * 64
            self.addCleanup(handle.close)
            fake_attestation = SimpleNamespace(close=lambda: None)
            with mock.patch("installed_storage_runtime.attest_broker_executable", return_value=fake_attestation), mock.patch(
                "installed_storage_runtime.attest_mount_probe", return_value=fake_attestation
            ) as broker_probe:
                with self.assertRaises(InstalledRuntimeError):
                    InstalledStorageRuntime.from_installed_home_locked(home, FakeLocks(home), handle)
            broker_probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
