from __future__ import annotations

import hashlib
import fcntl
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest import mock

from installed_storage_runtime import InstalledRuntimeError, InstalledStorageRuntime
from lifecycle_lock import LIFECYCLE_LOCK_MARKER
from storage_broker import AttestedBootstrapHandle
from storage_reconciliation import digest
from storage_lock import StorageLockError, open_storage_lock_set


class FakeLocks:
    def __init__(self, home):
        self.home = home
    def assert_active(self, *, home, required_install_mode, required_storage_mode):
        if Path(home) != self.home:
            raise RuntimeError("wrong home")


class InstalledRuntimeTests(unittest.TestCase):
    def test_start_locked_uses_runtime_contract_and_lifecycle(self):
        runtime = object.__new__(InstalledStorageRuntime)
        for name, value in (("home", Path("/temporary-cortex")), ("lifecycle", object()), ("contract", object())):
            object.__setattr__(runtime, name, value)
        locks = object()
        with mock.patch("startup_lease.launch_managed_runtime") as start:
            self.assertIs(runtime.start_locked(locks, timeout_seconds=9), start.return_value)
            start.assert_called_once_with(runtime.home, lock_set=locks, lifecycle=runtime.lifecycle,
                                          contract=runtime.contract, timeout_seconds=9, child_owner=None)

    def manifest_consumer_fixture(self, directory, *, duplicate_manifest=False, duplicate_generation=False):
        # The descriptor attestation boundary supplies immutable verified bytes.
        # These parser tests do not simulate a successful native bootstrap.
        home = Path(directory)
        generation_id = uuid4()
        manifest = (b'{"schema_version":0,"schema_version":1,"native_helpers":{}}'
                    if duplicate_manifest else b'{"schema_version":1,"native_helpers":{}}')
        record = {"schema_version": 1, "generation_id": str(generation_id),
                  "owned_manifest_sha256": hashlib.sha256(manifest).hexdigest()}
        record_digest = digest("CORTEX-S3\x00INSTALLED-GENERATION\x00V1\x00", record)
        record["generation_record_sha256"] = record_digest
        generation = json.dumps(record).encode()
        if duplicate_generation:
            generation = b'{"schema_version":0,' + generation[1:]
        target = home / "installed-generations" / str(generation_id)
        target.mkdir(parents=True)
        (target / "owned-manifest.json").write_bytes(manifest)
        (target / "generation-record.json").write_bytes(generation)
        handle = SimpleNamespace(generation_id=generation_id, generation_record_sha256=record_digest,
                                 owned_manifest_sha256=hashlib.sha256(manifest).hexdigest())
        return home, handle, (b"", generation, manifest)

    def test_factory_consumes_verified_snapshot_without_path_reread(self):
        class ReachedNativeAttestation(Exception):
            pass
        with tempfile.TemporaryDirectory() as directory:
            home, handle, snapshot = self.manifest_consumer_fixture(directory)
            with mock.patch("installed_storage_runtime._validate_bootstrap_handle", return_value=snapshot), \
                 mock.patch("pathlib.Path.read_bytes", side_effect=AssertionError("unverified path reread")), \
                 mock.patch("installed_storage_runtime.attest_broker_executable", side_effect=ReachedNativeAttestation):
                with self.assertRaises(ReachedNativeAttestation):
                    InstalledStorageRuntime.from_installed_home_locked(home, FakeLocks(home), handle)

    def test_factory_rejects_duplicate_manifest_keys_before_native_attestation(self):
        with tempfile.TemporaryDirectory() as directory:
            home, handle, snapshot = self.manifest_consumer_fixture(directory, duplicate_manifest=True)
            with mock.patch("installed_storage_runtime._validate_bootstrap_handle", return_value=snapshot), \
                 mock.patch("installed_storage_runtime.attest_broker_executable", side_effect=AssertionError("duplicate accepted")):
                with self.assertRaises(InstalledRuntimeError):
                    InstalledStorageRuntime.from_installed_home_locked(home, FakeLocks(home), handle)

    def test_factory_rejects_duplicate_generation_keys_before_native_attestation(self):
        with tempfile.TemporaryDirectory() as directory:
            home, handle, snapshot = self.manifest_consumer_fixture(directory, duplicate_generation=True)
            with mock.patch("installed_storage_runtime._validate_bootstrap_handle", return_value=snapshot), \
                 mock.patch("installed_storage_runtime.attest_broker_executable", side_effect=AssertionError("duplicate accepted")):
                with self.assertRaises(InstalledRuntimeError):
                    InstalledStorageRuntime.from_installed_home_locked(home, FakeLocks(home), handle)

    def test_stable_bootstrap_profile_compiles_for_the_supported_macos_floor(self):
        profile = json.loads(
            (Path(__file__).resolve().parents[1] / "native/build-profiles/storage-bootstrap-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            profile["swiftc"],
            ["-O", "-target", "arm64-apple-macosx14.0"],
        )
        with tempfile.TemporaryDirectory() as td:
            temporary = Path(td)
            binary = temporary / "cortex-launch"
            source = Path(__file__).resolve().parents[1] / profile["source"]
            command = ["xcrun", "swiftc", *profile["swiftc"], str(source)]
            for framework in profile["frameworks"]:
                command.extend(["-framework", framework])
            command.extend(["-o", str(binary)])
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=180,
                env={
                    **os.environ,
                    "CLANG_MODULE_CACHE_PATH": str(temporary / "clang-cache"),
                    "SWIFT_MODULECACHE_PATH": str(temporary / "swift-cache"),
                },
            )
            self.assertEqual(
                completed.returncode, 0,
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
            )
            self.assertTrue(binary.is_file())

    def test_stable_bootstrap_selects_generation_and_executes_its_interpreter(self):
        source_root = Path(__file__).resolve().parents[1]
        profile = json.loads((source_root / "native/build-profiles/storage-bootstrap-v1.json").read_text())
        with tempfile.TemporaryDirectory() as td:
            temporary = Path(td).resolve()
            binary = temporary / "cortex-launch"
            source = source_root / profile["source"]
            completed = subprocess.run(
                ["xcrun", "swiftc", *profile["swiftc"], str(source), "-o", str(binary)],
                capture_output=True, text=True, timeout=180,
                env={**os.environ, "CLANG_MODULE_CACHE_PATH": str(temporary / "clang-cache"),
                     "SWIFT_MODULECACHE_PATH": str(temporary / "swift-cache")},
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            home = temporary / "home"
            home.mkdir(mode=0o700)
            (home / ".install.lock").write_bytes(b"lock")
            (home / ".install.lock").chmod(0o600)
            generation_id = "11111111-1111-4111-8111-111111111111"
            selector = {"schema_version": 1, "generation_id": generation_id,
                        "generation_record_sha256": "a" * 64}
            (home / "current-generation.json").write_text(json.dumps(selector))
            (home / "current-generation.json").chmod(0o600)
            missing = subprocess.run([str(binary), "--home", str(home)], capture_output=True, text=True, timeout=5)
            self.assertNotEqual(missing.returncode, 0)
            generation = home / "installed-generations" / generation_id / "app/bin"
            generation.mkdir(parents=True, mode=0o700)
            (home / "installed-generations").chmod(0o700)
            (home / "installed-generations" / generation_id).chmod(0o700)
            (home / "installed-generations" / generation_id / "app").chmod(0o700)
            (home / "installed-generations" / generation_id / "app/bin").chmod(0o700)
            (home / "installed-generations" / generation_id / "app/python").mkdir(mode=0o700)
            (home / "installed-generations" / generation_id / "app/python").chmod(0o700)
            interpreter = generation / "python"
            interpreter.write_text("#!/bin/sh\nprintf started > \"$CORTEX_HOME/bootstrap-ran\"\n")
            interpreter.chmod(0o700)
            identity = interpreter.stat()
            interpreter_digest = hashlib.sha256(interpreter.read_bytes()).hexdigest()
            app = generation.parent
            server_source = app / "python/server.py"
            server_source.write_bytes(b"# harmless source fixture\n")
            server_source.chmod(0o600)
            original_source = server_source.read_bytes()
            tree = [
                {"path": "bin", "kind": "directory", "mode": 0o700},
                {"path": "bin/python", "kind": "file", "mode": 0o700,
                 "size": identity.st_size, "sha256": interpreter_digest},
                {"path": "python", "kind": "directory", "mode": 0o700},
                {"path": "python/server.py", "kind": "file", "mode": 0o600,
                 "size": len(original_source), "sha256": hashlib.sha256(original_source).hexdigest()},
            ]
            generation_record = home / "installed-generations" / generation_id / "generation-record.json"
            manifest = {"schema_version": 1, "native_helpers": {"fixture": {}}, "app_tree": tree,
                        "interpreter": {"target": "app/bin/python", "sha256": interpreter_digest,
                                        "dev_u32": identity.st_dev & 0xffffffff, "ino": identity.st_ino,
                                        "uid": identity.st_uid, "mode": 0o700}}
            manifest_bytes = json.dumps(manifest, separators=(",", ":")).encode()
            manifest_path = home / "installed-generations" / generation_id / "owned-manifest.json"
            manifest_path.write_bytes(manifest_bytes)
            manifest_path.chmod(0o600)
            unsigned_record = {
                "schema_version": 1,
                "generation_id": generation_id,
                "owned_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "interpreter_sha256": interpreter_digest,
                "interpreter_dev_u32": identity.st_dev & 0xffffffff,
                "interpreter_ino": identity.st_ino,
                "interpreter_uid": identity.st_uid,
                "interpreter_mode": 0o700,
                "encoding_probe": {"Z": [True, False, None, 2**64 - 1],
                                   "a": "slash/path", "é": "café", "z": "line\nend",
                                   "controls": "".join(chr(value) for value in range(32)),
                                   "literal": "\\n\\t\""},
            }
            record_digest = digest("CORTEX-S3\x00INSTALLED-GENERATION\x00V1\x00", unsigned_record)
            record = {**unsigned_record, "generation_record_sha256": record_digest}
            record_bytes = json.dumps(record, separators=(",", ":")).encode()
            generation_record.write_bytes(record_bytes)
            generation_record.chmod(0o600)
            selector["generation_record_sha256"] = record_digest
            (home / "current-generation.json").write_text(json.dumps(selector))
            launched = subprocess.run([str(binary), "--home", str(home)], capture_output=True, text=True,
                                      timeout=5, env={**os.environ, "CORTEX_HOME": str(home)})
            self.assertEqual(launched.returncode, 0, launched.stderr)
            self.assertEqual((home / "bootstrap-ran").read_text(), "started")

            # Real native launcher, harmless shell probe instead of Python:
            # these cases prove pre-exec rejection, not application readiness.
            original_interpreter = interpreter.read_bytes()
            alias = temporary / "alias"
            alias.symlink_to(temporary, target_is_directory=True)
            for corruption in ("record", "interpreter", "traversal", "duplicate", "escaped_duplicate", "nested_duplicate",
                               "source", "source_mode", "extra_file", "ancestor_link", "special_mode"):
                with self.subTest(corruption=corruption):
                    (home / "bootstrap-ran").write_text("not-executed")
                    changed_selector = dict(selector)
                    if corruption == "record":
                        generation_record.write_text(json.dumps({**record, "interpreter_uid": identity.st_uid + 1}))
                    elif corruption == "interpreter":
                        interpreter.write_bytes(original_interpreter + b"# changed bytes\n")
                    elif corruption == "traversal":
                        changed_selector["generation_id"] = f"../installed-generations/{generation_id}"
                        generation_record.write_text(json.dumps({**record, "generation_id": changed_selector["generation_id"]}))
                    elif corruption == "source":
                        server_source.write_bytes(b"# altered source\n")
                    elif corruption == "source_mode":
                        server_source.chmod(0o644)
                    elif corruption == "extra_file":
                        (app / "unlisted.py").write_bytes(b"# unlisted\n")
                        (app / "unlisted.py").chmod(0o600)
                    elif corruption == "special_mode":
                        interpreter.chmod(0o4700)
                    (home / "current-generation.json").write_text(json.dumps(changed_selector))
                    if corruption in ("duplicate", "escaped_duplicate"):
                        key = '"schema_version"' if corruption == "duplicate" else '"schema_\\u0076ersion"'
                        (home / "current-generation.json").write_text(
                            '{' + key + ':1,' + json.dumps(changed_selector)[1:])
                    elif corruption == "nested_duplicate":
                        # Same parsed record and digest, but ambiguous raw JSON.
                        generation_record.write_bytes(record_bytes.replace(
                            b'"encoding_probe":{',
                            b'"encoding_probe":{"Z":[true,false,null,18446744073709551615],', 1))
                    target_home = alias / "home" if corruption == "ancestor_link" else home
                    rejected = subprocess.run([str(binary), "--home", str(target_home)], capture_output=True,
                                              text=True, timeout=5)
                    self.assertEqual(rejected.returncode, 78, rejected.stderr)
                    self.assertEqual((home / "bootstrap-ran").read_text(), "not-executed")
                generation_record.write_bytes(record_bytes)
                interpreter.write_bytes(original_interpreter)
                interpreter.chmod(0o700)
                server_source.write_bytes(original_source)
                server_source.chmod(0o600)
                (app / "unlisted.py").unlink(missing_ok=True)
                (home / "current-generation.json").write_text(json.dumps(selector))

            manifest_path.write_text('{"schema_version":1,"native_helpers":{}}')
            manifest_path.chmod(0o600)
            tampered_manifest = subprocess.run(
                [str(binary), "--home", str(home)], capture_output=True, text=True, timeout=5,
                env={**os.environ, "CORTEX_HOME": str(home)},
            )
            self.assertNotEqual(tampered_manifest.returncode, 0)
            manifest_path.write_bytes(manifest_bytes)
            manifest_path.chmod(0o600)

            selector["generation_record_sha256"] = "a" * 64
            (home / "current-generation.json").write_text(json.dumps(selector))
            (home / "current-generation.json").chmod(0o600)
            tampered_selector = subprocess.run(
                [str(binary), "--home", str(home)], capture_output=True, text=True, timeout=5,
                env={**os.environ, "CORTEX_HOME": str(home)},
            )
            self.assertNotEqual(tampered_selector.returncode, 0)

    def test_lock_set_adopts_bootstrap_install_lock_without_releasing_it(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir(mode=0o700)
            for name in (".install.lock", "storage-state.lock", "storage-admission.lock"):
                path = home / name
                path.write_bytes(LIFECYCLE_LOCK_MARKER)
                path.chmod(0o600)
            install_fd = os.open(home / ".install.lock", os.O_RDWR)
            fcntl.flock(install_fd, fcntl.LOCK_SH)
            details = os.fstat(install_fd)
            bootstrap = SimpleNamespace(
                active=True,
                home=home,
                install_lock_fd=install_fd,
                install_lock_dev_u32=details.st_dev & 0xFFFFFFFF,
                install_lock_ino=details.st_ino,
                install_lock_uid=details.st_uid,
                install_lock_mode=0o600,
            )
            try:
                with open_storage_lock_set(
                    home,
                    install_mode="shared",
                    storage_mode="shared",
                    bootstrap_install=bootstrap,
                ) as locks:
                    self.assertEqual(
                        (os.fstat(locks.install_fd).st_dev, os.fstat(locks.install_fd).st_ino),
                        (details.st_dev, details.st_ino),
                    )
                os.fstat(install_fd)
                contender = os.open(home / ".install.lock", os.O_RDWR)
                try:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    os.close(contender)
            finally:
                fcntl.flock(install_fd, fcntl.LOCK_UN)
                os.close(install_fd)

    def test_lock_set_rejects_replaced_bootstrap_install_marker(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir(mode=0o700)
            for name in (".install.lock", "storage-state.lock", "storage-admission.lock"):
                path = home / name
                path.write_bytes(LIFECYCLE_LOCK_MARKER)
                path.chmod(0o600)
            install_fd = os.open(home / ".install.lock", os.O_RDWR)
            fcntl.flock(install_fd, fcntl.LOCK_SH)
            details = os.fstat(install_fd)
            bootstrap = SimpleNamespace(
                active=True,
                home=home,
                install_lock_fd=install_fd,
                install_lock_dev_u32=details.st_dev & 0xFFFFFFFF,
                install_lock_ino=details.st_ino,
                install_lock_uid=details.st_uid,
                install_lock_mode=0o600,
            )
            original = home / ".install.original"
            os.rename(home / ".install.lock", original)
            (home / ".install.lock").write_bytes(LIFECYCLE_LOCK_MARKER)
            (home / ".install.lock").chmod(0o600)
            try:
                with self.assertRaisesRegex(StorageLockError, "STORAGE_LOCK_REPLACED"):
                    with open_storage_lock_set(
                        home,
                        install_mode="shared",
                        storage_mode="shared",
                        bootstrap_install=bootstrap,
                    ):
                        self.fail("a replaced bootstrap marker must not be adopted")
            finally:
                fcntl.flock(install_fd, fcntl.LOCK_UN)
                os.close(install_fd)

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
