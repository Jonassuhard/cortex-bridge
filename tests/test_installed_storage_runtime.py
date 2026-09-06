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
from storage_reconciliation import digest


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

    def test_factory_rejects_selector_digest_mismatch_before_attestation(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir(mode=0o700)
            generation_id = uuid4()
            generation_dir = home / "installed-generations" / str(generation_id)
            generation_dir.mkdir(mode=0o700, parents=True)

            manifest_bytes = b'{"native_helpers":{},"schema_version":1}'
            manifest_path = generation_dir / "owned-manifest.json"
            manifest_path.write_bytes(manifest_bytes)
            manifest_path.chmod(0o600)
            generation_without_digest = {
                "schema_version": 1,
                "generation_id": str(generation_id),
                "owned_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            }
            record_digest = digest(
                "CORTEX-S3\x00INSTALLED-GENERATION\x00V1\x00",
                generation_without_digest,
            )
            generation_path = generation_dir / "generation-record.json"
            generation_path.write_text(
                json.dumps(
                    {**generation_without_digest, "generation_record_sha256": record_digest},
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            generation_path.chmod(0o600)

            selector_path = home / "current-generation.json"
            selector_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "generation_id": str(generation_id),
                        "generation_record_sha256": record_digest,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            selector_path.chmod(0o600)
            install_path = home / ".install.lock"
            install_path.write_bytes(b"lock")
            install_path.chmod(0o600)
            interpreter_path = generation_dir / "app-python"
            interpreter_path.write_bytes(b"python")
            interpreter_path.chmod(0o700)

            fds = [
                os.open(install_path, os.O_RDWR),
                os.open(selector_path, os.O_RDONLY),
                os.open(generation_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)),
                os.open(generation_path, os.O_RDONLY),
                os.open(manifest_path, os.O_RDONLY),
                os.open(interpreter_path, os.O_RDONLY),
            ]
            def close_fds():
                for fd in fds:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
            self.addCleanup(close_fds)

            def identity(fd):
                details = os.fstat(fd)
                return details.st_dev & 0xFFFFFFFF, details.st_ino, details.st_uid

            install_dev, install_ino, install_uid = identity(fds[0])
            handle = AttestedBootstrapHandle(
                home=home,
                install_lock_fd=fds[0], install_lock_dev_u32=install_dev,
                install_lock_ino=install_ino, install_lock_uid=install_uid,
                install_lock_mode=0o600, selector_fd=fds[1],
                generation_dir_fd=fds[2], generation_record_fd=fds[3],
                owned_manifest_fd=fds[4], interpreter_fd=fds[5],
                generation_id=generation_id, selector_sha256="f" * 64,
                generation_record_sha256=record_digest,
                owned_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            )
            self.addCleanup(handle.close)

            with mock.patch(
                "installed_storage_runtime.attest_broker_executable",
                side_effect=AssertionError("broker attestation must not run"),
            ) as broker_attest:
                with self.assertRaisesRegex(InstalledRuntimeError, "selector"):
                    InstalledStorageRuntime.from_installed_home_locked(
                        home, FakeLocks(home), handle
                    )
            broker_attest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
