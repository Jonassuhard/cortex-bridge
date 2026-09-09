"""Real wheel -> apply_install -> selected generation -> HTTP server on macOS."""
import hashlib
import io
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from urllib.request import urlopen
from urllib.error import URLError

import generation_install
import installer
from generation_metadata import GenerationMetadata, verify_generation_metadata
from uuid import UUID


@unittest.skipUnless(sys.platform == "darwin", "macOS generation installer")
class GenerationInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="cortex-install-e2e-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.base = Path(cls.temporary.name).resolve()
        cls.root = Path(__file__).resolve().parents[1]
        source = cls.base / "source"
        source.mkdir()
        shutil.copy2(cls.root / "pyproject.toml", source / "pyproject.toml")
        for name in ("console", "executor", "orchestration", "transport"):
            shutil.copytree(cls.root / name, source / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        cls.environment = {"PATH": os.defpath, "HOME": str(cls.base),
                           "PYTHONDONTWRITEBYTECODE": "1", "PIP_CONFIG_FILE": os.devnull,
                           "PIP_INDEX_URL": "https://pypi.org/simple"}
        built = subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps",
                                "--wheel-dir", str(cls.base / "wheels"), str(source)],
                               env=cls.environment, cwd=cls.base, capture_output=True,
                               text=True, timeout=120)
        if built.returncode:
            raise RuntimeError(built.stderr[-2000:])
        cls.wheel, = (cls.base / "wheels").glob("cortex_bridge-*.whl")

    def setUp(self):
        self.home = self.base / self._testMethodName
        self.env_patch = mock.patch.dict(os.environ, {
            **self.environment, "CORTEX_HOME": str(self.home),
        }, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_tampered_plan_is_rejected_before_creating_home(self):
        plan = generation_install.build_plan(self.wheel)
        plan["steps"].append("Unapproved operation")
        with self.assertRaises(PermissionError):
            installer.apply_install(plan, plan["plan_hash"])
        self.assertFalse(self.home.exists())

    def test_prebootstrap_generation_is_preserved_for_explicit_migration(self):
        self.home.mkdir(mode=0o700)
        selector = self.home / "current-generation.json"
        selector.write_bytes(b'{"legacy_generation":true}')
        selector.chmod(0o600)
        plan = generation_install.build_plan(self.wheel)
        with self.assertRaisesRegex(RuntimeError, "BOOTSTRAP_MIGRATION_REQUIRED"):
            installer.apply_install(plan, plan["plan_hash"])
        self.assertEqual(selector.read_bytes(), b'{"legacy_generation":true}')
        self.assertFalse((self.home / generation_install.STAGING).exists())
        self.assertFalse((self.home / "bootstrap").exists())
        with self.assertRaises((ValueError, OSError)):
            generation_install.build_plan(self.wheel, bootstrap_migration="missing-v1")
        self.assertEqual(selector.read_bytes(), b'{"legacy_generation":true}')

    def test_missing_bootstrap_migration_does_not_create_uninstalled_home(self):
        with self.assertRaises((ValueError, OSError)):
            generation_install.build_plan(self.wheel, bootstrap_migration="missing-v1")
        self.assertFalse(self.home.exists())

    def _prepare_storage_workflow(self):
        from storage_broker import (StorageWorkflowLedger, _new_recovery_authority,
                                    _StorageBrokerRequest, AttestedBrokerExecutable,
                                    BrokerSocketIdentity, BootIdentity, DarwinU32)
        from storage_lock import open_storage_lock_set
        from uuid import uuid4
        self.home.mkdir(mode=0o700)
        broker = self.home / "test-broker"
        broker.write_bytes(b"fixture, never executed")
        broker.chmod(0o700)
        fd = os.open(broker, os.O_RDONLY)
        try:
            info = os.fstat(fd)
            executable = AttestedBrokerExecutable(broker, fd, DarwinU32(info.st_dev & 0xffffffff),
                info.st_ino, info.st_uid, 0o700, hashlib.sha256(broker.read_bytes()).hexdigest(), "b" * 64)
            recovery = _new_recovery_authority(self.home)
            try:
                with open_storage_lock_set(self.home, install_mode="exclusive", storage_mode="exclusive") as locks:
                    record = StorageWorkflowLedger(self.home).prepare_locked(
                        locks, _StorageBrokerRequest(1, "inspect-item", self.home / "image", None,
                            None, None, uuid4(), None, False, False), executable,
                        BrokerSocketIdentity(self.home / "sock", DarwinU32(1), 3, os.getuid(), 0o600),
                        BootIdentity(5, 6), recovery, effect_budget_ns=10, cleanup_budget_ns=1)
            finally:
                recovery.close()
        finally:
            os.close(fd)
        return record

    def test_open_storage_workflow_blocks_install_before_staging(self):
        self._prepare_storage_workflow()
        ledger = self.home / "storage/storage-workflows.jsonl"
        before = ledger.read_bytes()
        plan = generation_install.build_plan(self.wheel)
        with mock.patch("generation_install._copy_checked", side_effect=AssertionError("unsafe staging reached")):
            with self.assertRaisesRegex(RuntimeError, "STORAGE_WORKFLOWS_OPEN"):
                installer.apply_install(plan, plan["plan_hash"])
        self.assertFalse((self.home / generation_install.STAGING).exists())
        self.assertEqual(ledger.read_bytes(), before)

    def test_closed_preexec_failure_does_not_block_update(self):
        from storage_broker import StorageWorkflowLedger
        from storage_lock import open_storage_lock_set
        record = self._prepare_storage_workflow()
        with open_storage_lock_set(self.home, install_mode="exclusive", storage_mode="exclusive") as locks:
            StorageWorkflowLedger(self.home).close_preexec_failure_locked(locks, record.workflow_id, record.generation)
            generation_install._assert_update_quiescent(self.home, locks)

    def test_closed_unreconciled_or_unreaped_workflow_blocks_update(self):
        from storage_reconciliation import digest, canonical_json
        from storage_lock import open_storage_lock_set
        self._prepare_storage_workflow()
        path = self.home / "storage/storage-workflows.jsonl"
        prepared = json.loads(path.read_bytes())
        for reconcile, cleanup, code in ((True, True, "STORAGE_RECONCILIATION_REQUIRED"),
                                          (False, False, "STORAGE_CLEANUP_UNPROVEN"),
                                          (False, "yes", "STORAGE_CLEANUP_UNPROVEN")):
            with self.subTest(code=code):
                closed = {**prepared, "state": "CLOSED_SUCCESS", "started_monotonic_ns": 1,
                          "reconciliation_required": reconcile, "child_reaped": cleanup,
                          "group_absent": cleanup, "native_cleanup_proven": cleanup}
                closed["record_sha256"] = digest("CORTEX-S3\x00LEDGER\x00V1\x00",
                    {key: value for key, value in closed.items() if key != "record_sha256"})
                raw = canonical_json(closed) + b"\n"
                path.write_bytes(raw)
                with open_storage_lock_set(self.home, install_mode="exclusive", storage_mode="exclusive") as locks:
                    with self.assertRaisesRegex(RuntimeError, code):
                        generation_install._assert_update_quiescent(self.home, locks)
                self.assertEqual(path.read_bytes(), raw)

    def test_migration_cli_requires_explicit_generation_wheel(self):
        output = io.StringIO()
        with mock.patch("sys.stdout", output):
            status = installer.main(["install", "--bootstrap-migration", "missing-v1", "--dry-run", "--json"])
        self.assertEqual(status, 1)
        self.assertIn("--generation-wheel", json.loads(output.getvalue())["error"])
        self.assertFalse(self.home.exists())

    def test_doctor_refuses_partial_generation_without_legacy_fallback(self):
        self.home.mkdir(mode=0o700)
        (self.home / "bootstrap").mkdir(mode=0o700)
        with mock.patch.dict(os.environ, {"PORT": "8431"}):
            result = installer.doctor()
        self.assertEqual(result.get("local_url"), "http://127.0.0.1:8431")
        self.assertEqual(result["installation_mode"], "generation")
        self.assertFalse(result["ok"])
        self.assertEqual(next(check for check in result["checks"]
                              if check["id"] == "generation_integrity")["status"], "fail")
        self.assertFalse((self.home / "current-generation.json").exists())

    def test_explicit_missing_bootstrap_migration_preserves_verified_generation(self):
        first_plan = generation_install.build_plan(self.wheel)
        first = installer.apply_install(first_plan, first_plan["plan_hash"])
        with self.assertRaisesRegex(ValueError, "absent bootstrap"):
            generation_install.build_plan(self.wheel, bootstrap_migration="missing-v1")
        old_generation = Path(first["generation_path"])
        old_selector = (self.home / "current-generation.json").read_bytes()
        old_manifest = (old_generation / "owned-manifest.json").read_bytes()
        old_record = (old_generation / "generation-record.json").read_bytes()
        preserved = self.home / "bootstrap-test-preserved"
        (self.home / "bootstrap").rename(preserved)
        old_launcher = (preserved / "cortex-launch").stat().st_ino
        normal = generation_install.build_plan(self.wheel)
        with self.assertRaisesRegex(RuntimeError, "BOOTSTRAP_MIGRATION_REQUIRED"):
            installer.apply_install(normal, normal["plan_hash"])
        migration = generation_install.build_plan(self.wheel, bootstrap_migration="missing-v1")
        self.assertEqual(migration["previous_generation"]["generation_id"], first["generation_id"])
        probe = old_generation / "app/python/server.py"
        original = probe.read_bytes()
        try:
            probe.write_bytes(original + b"\n# changed since approval\n")
            with self.assertRaises((ValueError, PermissionError, RuntimeError)):
                installer.apply_install(migration, migration["plan_hash"])
            self.assertFalse((self.home / generation_install.STAGING).exists())
            self.assertEqual((self.home / "current-generation.json").read_bytes(), old_selector)
        finally:
            probe.write_bytes(original)
        result = installer.apply_install(migration, migration["plan_hash"])
        self.assertNotEqual(result["generation_id"], first["generation_id"])
        verify_generation_metadata(old_generation, GenerationMetadata(
            UUID(first["generation_id"]), old_manifest, old_record, old_selector))
        self.assertEqual((preserved / "cortex-launch").stat().st_ino, old_launcher)
        with socket.socket() as available:
            available.bind(("127.0.0.1", 0))
            port = available.getsockname()[1]
        self.check_native_start(port, Path(result["launcher_path"]))

    def test_changed_wheel_is_rejected_before_staging(self):
        wheel = self.base / ("cortex_bridge-changed.whl")
        shutil.copyfile(self.wheel, wheel)
        plan = generation_install.build_plan(wheel)
        with wheel.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaises(PermissionError):
            installer.apply_install(plan, plan["plan_hash"])
        self.assertFalse((self.home / generation_install.STAGING).exists())

    def test_changed_target_is_rejected_before_install(self):
        plan = generation_install.build_plan(self.wheel)
        with mock.patch.dict(os.environ, {"CORTEX_HOME": str(self.home / "different")}):
            with self.assertRaisesRegex(PermissionError, "target changed"):
                installer.apply_install(plan, plan["plan_hash"])
        self.assertFalse(self.home.exists())

    def test_interrupted_legacy_install_is_preserved(self):
        self.home.mkdir(mode=0o700)
        legacy = self.home / installer.STAGING_NAME
        legacy.mkdir(mode=0o700)
        (legacy / "proof").write_bytes(b"pending legacy build")
        plan = generation_install.build_plan(self.wheel)
        with self.assertRaisesRegex(RuntimeError, "LEGACY_INSTALL_PENDING"):
            installer.apply_install(plan, plan["plan_hash"])
        self.assertEqual((legacy / "proof").read_bytes(), b"pending legacy build")
        self.assertFalse((self.home / generation_install.STAGING).exists())

    def test_pending_publication_is_not_overwritten(self):
        self.home.mkdir(mode=0o700)
        marker = self.home / ".generation-publication.json"
        original = b'{"schema_version":1,"state":"prepared","generation_id":"11111111-1111-4111-8111-111111111111"}'
        marker.write_bytes(original)
        marker.chmod(0o600)
        plan = generation_install.build_plan(self.wheel)
        with self.assertRaisesRegex(RuntimeError, "PENDING_RECONCILIATION"):
            installer.apply_install(plan, plan["plan_hash"])
        self.assertEqual(marker.read_bytes(), original)
        self.assertFalse((self.home / generation_install.STAGING).exists())

    def test_real_install_publishes_complete_generation_and_serves_http(self):
        plan = generation_install.build_plan(self.wheel)
        self.assertFalse(self.home.exists(), "Planning must not install anything")
        try:
            result = installer.apply_install(plan, plan["plan_hash"])
        except subprocess.CalledProcessError as error:
            self.fail(f"Real installation failed: {error.stderr[-3000:]!r}")
        self.assertEqual(result["status"], "installed")
        self.assertFalse(result["runtime_started"])
        generation = Path(result["generation_path"])
        selector_bytes = (self.home / "current-generation.json").read_bytes()
        self.assertEqual(json.loads(selector_bytes)["generation_id"], result["generation_id"])
        metadata = GenerationMetadata(UUID(result["generation_id"]),
                                      (generation / "owned-manifest.json").read_bytes(),
                                      (generation / "generation-record.json").read_bytes(), selector_bytes)
        verify_generation_metadata(generation, metadata)
        self.assertTrue((Path(result["chrome_extension_path"]) / "manifest.json").is_file())
        self.assertFalse((self.home / generation_install.STAGING).exists())
        app = generation / "app"
        diagnosis = installer.doctor()
        self.assertEqual(diagnosis.get("installation_mode"), "generation")
        self.assertEqual(diagnosis.get("generation_id"), result["generation_id"])
        integrity = next(check for check in diagnosis["checks"] if check["id"] == "generation_integrity")
        self.assertEqual(integrity["status"], "pass", diagnosis)
        extension_check = next(check for check in diagnosis["checks"] if check["id"] == "chrome_extension")
        self.assertEqual(extension_check["path"], result["chrome_extension_path"])
        installed_doctor = subprocess.run(
            [str(app / "bin/python"), "-I", "-S", "-B", "-c",
             "import sys; sys.path.insert(0,sys.argv[1]); import installer; installer.main(['doctor','--json'])",
             str(app / "python")], cwd=self.base, env={**self.environment, "CORTEX_HOME": str(self.home)},
            capture_output=True, text=True, timeout=30, check=True)
        installed_diagnosis = json.loads(installed_doctor.stdout)
        self.assertEqual(installed_diagnosis["generation_id"], result["generation_id"])
        self.assertEqual(next(check for check in installed_diagnosis["checks"]
                              if check["id"] == "generation_integrity")["status"], "pass", installed_diagnosis)
        probe = app / "python/server.py"
        original = probe.read_bytes()
        try:
            probe.write_bytes(original + b"\n# unexpected change\n")
            damaged = installer.doctor()
            self.assertFalse(damaged["ok"])
            self.assertEqual(next(check for check in damaged["checks"]
                                  if check["id"] == "generation_integrity")["status"], "fail")
        finally:
            probe.write_bytes(original)
        with socket.socket() as available:
            available.bind(("127.0.0.1", 0))
            port = available.getsockname()[1]
        # Isolated Python: all third-party imports must come from the installed tree.
        program = ("import sys,pathlib; sys.path.insert(0,sys.argv[1]); import server,uvicorn,fastapi; "
                   "assert all(pathlib.Path(m.__file__).is_relative_to(sys.argv[1]) "
                   "for m in (server,uvicorn,fastapi)); server.main()")
        log = self.base / "installed-http.log"
        with log.open("wb") as output:
            process = subprocess.Popen([str(app / "bin/python"), "-I", "-S", "-B", "-c", program,
                                        str(app / "python")], cwd=self.base,
                                       env={**self.environment, "CORTEX_HOME": str(self.home), "PORT": str(port)},
                                       stdout=output, stderr=output)
            try:
                deadline = time.monotonic() + 20
                while True:
                    try:
                        with urlopen(f"http://127.0.0.1:{port}/", timeout=1) as response:
                            content = response.read()
                            self.assertEqual(response.status, 200)
                        break
                    except (URLError, TimeoutError):
                        if process.poll() is not None or time.monotonic() >= deadline:
                            self.fail(log.read_text()[-4000:])
                        time.sleep(0.1)
                self.assertEqual(hashlib.sha256(content).digest(),
                                 hashlib.sha256((self.root / "frontend/out/index.html").read_bytes()).digest())
                asset = next(iter(sorted((app / "frontend/out/_next").rglob("*.js"))))
                relative = asset.relative_to(app / "frontend/out").as_posix()
                with urlopen(f"http://127.0.0.1:{port}/{relative}", timeout=2) as response:
                    self.assertEqual(response.read(), asset.read_bytes())
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=10)
        # Uvicorn restores and re-raises SIGTERM after the lifespan shuts down.
        self.assertEqual(process.returncode, -signal.SIGTERM, log.read_text()[-2000:])
        self.assertIn("Application shutdown complete.", log.read_text())
        verify_generation_metadata(generation, metadata)
        launcher = Path(result["launcher_path"])
        self.assertEqual(launcher, self.home / "bootstrap/cortex-launch")
        self.assertTrue(launcher.is_file())
        manifest_path = self.home / "bootstrap/bootstrap-v1.json"
        self.assertTrue(manifest_path.is_file(), "Installed bootstrap must expose the S3 v1 manifest")
        manifest = json.loads(manifest_path.read_bytes())
        unsigned = {key: value for key, value in manifest.items() if key != "bootstrap_manifest_sha256"}
        canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(manifest["bootstrap_manifest_sha256"], hashlib.sha256(
            b"CORTEX-S3\x00BOOTSTRAP-MANIFEST\x00V1\x00" + canonical).hexdigest())
        launcher_before = (launcher.stat().st_ino, hashlib.sha256(launcher.read_bytes()).hexdigest())
        self.check_native_start(port, launcher)
        self.assertEqual([p.relative_to(app).as_posix() for p in app.rglob("__pycache__")], [])
        verify_generation_metadata(generation, metadata)
        self.check_managed_start(port)
        original_launcher = launcher.read_bytes()
        launcher.write_bytes(original_launcher + b"tampered")
        try:
            with self.assertRaises((ValueError, RuntimeError)):
                generation_install.build_plan(self.wheel)
        finally:
            launcher.write_bytes(original_launcher)
        import bootstrap_install
        changed_inputs = {**plan["bootstrap_inputs"],
                          "source": {**plan["bootstrap_inputs"]["source"], "sha256": "0" * 64}}
        with self.assertRaisesRegex(RuntimeError, "BOOTSTRAP_UPDATE_REQUIRES_MIGRATION"):
            bootstrap_install.inspect(self.home, changed_inputs)
        # An actual second install, with only selector publication fault-injected.
        # All dependency installation, native builds and metadata checks remain real.
        second_plan = generation_install.build_plan(self.wheel)
        with mock.patch("generation_publication._write_selector", side_effect=OSError("disk fault")):
            with self.assertRaisesRegex(OSError, "disk fault"):
                installer.apply_install(second_plan, second_plan["plan_hash"])
        self.assertEqual((self.home / "current-generation.json").read_bytes(), selector_bytes)
        self.assertEqual((launcher.stat().st_ino, hashlib.sha256(launcher.read_bytes()).hexdigest()), launcher_before)
        verify_generation_metadata(generation, metadata)
        self.assertTrue((self.home / generation_install.STAGING).is_dir())
        recovery = generation_install.recover_generation_publication(self.home)
        self.assertEqual(recovery["status"], "pending_reconciliation")

    def check_native_start(self, port, binary):
        log = self.base / "native-http.log"
        with log.open("wb") as output:
            process = subprocess.Popen([str(binary), "--home", str(self.home)],
                                       env={**self.environment, "PORT": str(port)},
                                       cwd=self.base, stdout=output, stderr=output)
            try:
                deadline = time.monotonic() + 30
                while True:
                    try:
                        with urlopen(f"http://127.0.0.1:{port}/", timeout=1) as response:
                            self.assertEqual(response.status, 200)
                        self.assertTrue((self.home / "runtime-lifespan.json").is_file(),
                                        "native launcher bypassed managed startup")
                        record = json.loads((self.home / "runtime-lifespan.json").read_bytes())
                        self.assertEqual(record["state"], "READY")
                        self.assertNotEqual(record["identity"]["pid"], process.pid)
                        from storage_lock import open_storage_lock_set
                        from storage_contract import StorageContract
                        with open_storage_lock_set(self.home, install_mode="shared", storage_mode="shared") as locks:
                            status = StorageContract(self.home, broker=None).assert_runtime_ready_locked(locks)
                            self.assertTrue(status.runtime_allowed, status)
                        break
                    except (URLError, TimeoutError):
                        if process.poll() is not None or time.monotonic() >= deadline:
                            self.fail(log.read_text()[-4000:])
                        time.sleep(0.1)
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=10)
        self.assertEqual(process.returncode, 0, log.read_text()[-2000:])
        self.assertEqual(json.loads((self.home / "runtime-lifespan.json").read_bytes())["state"], "CLOSED")
        from startup_lease import _read_kernel_process_identity
        self.assertIsNone(_read_kernel_process_identity(record["identity"]["pid"]))

    def check_managed_start(self, port):
        from storage_lock import open_storage_lock_set
        from storage_contract import StorageContract
        from storage_lifecycle import StorageLifecycle, StoragePaths
        from storage_result import OperationResult
        from startup_lease import launch_managed_runtime, _read_kernel_process_identity
        contract = StorageContract(self.home, broker=None)
        paths = StoragePaths(self.home, self.home, self.home / "legacy", self.home / "vault",
                             self.home / "mount", self.home / "workspaces", self.home / "storage-bootstrap.json",
                             self.home / "storage-required", self.home / "storage-transition.json", self.home / "quarantine")

        def status_operation(locks):
            observed = contract.probe_locked(locks)
            return OperationResult("status", observed.verdict, observed.transaction_id, observed.code, (),
                                   storage_state=observed.storage_state, mounted=observed.mounted,
                                   runtime_allowed=observed.runtime_allowed, recovery=observed.recovery)

        # Real contract/lifecycle with unconfigured optional storage; no mount
        # or broker success is fabricated. S3 mounted-volume acceptance is separate.
        lifecycle = StorageLifecycle(paths, broker=None, fd_probe=None, mount_verifier=status_operation)
        receipt = None
        with mock.patch.dict(os.environ, {"PORT": str(port)}):
            try:
                with open_storage_lock_set(self.home, install_mode="shared", storage_mode="shared") as locks:
                    real_popen = subprocess.Popen
                    with tempfile.TemporaryFile() as diagnostics:
                        def capture(*args, **kwargs):
                            if any("from managed_runtime import child_main" in str(arg) for arg in args[0]):
                                kwargs["stderr"] = diagnostics
                            return real_popen(*args, **kwargs)
                        with mock.patch("managed_runtime.subprocess.Popen", side_effect=capture):
                            try:
                                receipt = launch_managed_runtime(self.home, lock_set=locks, lifecycle=lifecycle,
                                                                 contract=contract, timeout_seconds=15)
                            except Exception:
                                diagnostics.seek(0)
                                print(diagnostics.read(8000).decode(errors="replace"))
                                raise
                    self.assertTrue(receipt.acknowledged)
                    self.assertTrue(contract.assert_runtime_ready_locked(locks).runtime_allowed)
                # Parent locks are released. The child must still run and own
                # independent lifetime locks while serving HTTP.
                for name in (".install.lock", "storage-state.lock"):
                    with (self.home / name).open("rb") as lock_file:
                        with self.assertRaises(BlockingIOError):
                            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                with urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
                    self.assertEqual(response.status, 200)
                record = json.loads((self.home / "runtime-lifespan.json").read_bytes())
                self.assertEqual(record["state"], "READY")
                self.assertEqual(record["identity"]["pid"], receipt.child_pid)
                identity = _read_kernel_process_identity(receipt.child_pid)
                self.assertEqual(identity.start_time, record["identity"]["start_time"])
            finally:
                if receipt is not None and _read_kernel_process_identity(receipt.child_pid) is not None:
                    os.kill(receipt.child_pid, signal.SIGTERM)
                    deadline = time.monotonic() + 10
                    while _read_kernel_process_identity(receipt.child_pid) is not None and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertIsNone(_read_kernel_process_identity(receipt.child_pid))
        self.assertEqual(json.loads((self.home / "runtime-lifespan.json").read_bytes())["state"], "CLOSED")


if __name__ == "__main__":
    unittest.main()
