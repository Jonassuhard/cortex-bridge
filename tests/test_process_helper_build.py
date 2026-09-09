import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


class ProcessHelperBuildTests(unittest.TestCase):
    def test_build_native_bundle_attests_all_four_helpers_in_order(self):
        import process_helper_build
        import native_helpers
        self.assertTrue(callable(getattr(process_helper_build, "build_native_helper_bundle", None)),
                        "Ordered native generation builder is missing")
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve()
            records = process_helper_build.build_native_helper_bundle(home)
            self.assertEqual(list(records), ["macos-ax-send", "storage-mount-probe",
                                           "storage-broker", "process-release"])
            self.assertEqual(sorted(p.name for p in (home / "app/native-src").iterdir()),
                ["disk_image_keychain.swift", "macos_ax_send.swift", "process_release.swift", "storage_mount_probe.swift"])
            self.assertEqual(sorted(p.name for p in (home / "app/build-profiles").iterdir()),
                ["macos-ax-send-v1.json", "process-release-v1.json", "storage-broker-v1.json", "storage-mount-probe-v1.json"])
            for name, record in records.items():
                saved_source = home / "app/native-src" / Path(record["source"]).name
                saved_profile = home / "app/build-profiles" / f"{name}-v1.json"
                self.assertEqual(hashlib.sha256(saved_source.read_bytes()).hexdigest(), record["source_sha256"])
                self.assertEqual(hashlib.sha256(saved_profile.read_bytes()).hexdigest(), record["build_profile_sha256"])
            registry = home / "app/native-helpers.json"
            digest = native_helpers.write_native_helper_registry(registry, records)
            details = registry.stat()
            manifest = {"native_helper_registry": {
                "target": "app/native-helpers.json", "sha256": digest,
                "dev_u32": details.st_dev & 0xffffffff, "ino": details.st_ino,
                "uid": details.st_uid, "mode": 0o600}}
            loaded = native_helpers.load_verified_native_helper_registry(home, manifest)
            self.assertEqual(list(loaded["native_helpers"]), list(records))
            self.assertEqual(loaded["native_helpers"], records)
            for name, record in loaded["native_helpers"].items():
                with self.subTest(helper=name):
                    handle = native_helpers.attest_helper(name, loaded, home=home)
                    try:
                        self.assertEqual(handle.revalidate_for_spawn(), home / record["target"])
                    finally:
                        handle.close()

    def builder(self):
        self.assertIsNotNone(importlib.util.find_spec("process_helper_build"),
                             "Native helper staging builder is missing")
        from process_helper_build import build_process_helper
        return build_process_helper

    def test_build_returns_attestable_signed_binary_and_real_source_hash(self):
        build = self.builder()
        import native_helpers
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve()
            record = build(home)
            root = Path(__file__).resolve().parents[1]
            self.assertEqual(record["source_sha256"],
                hashlib.sha256((root / "native/macos/process_release.swift").read_bytes()).hexdigest())
            self.assertEqual(record["build_profile_sha256"],
                hashlib.sha256((root / "native/build-profiles/process-release-v1.json").read_bytes()).hexdigest())
            for relative, original, field in (
                ("app/native-src/process_release.swift", "native/macos/process_release.swift", "source_sha256"),
                ("app/build-profiles/process-release-v1.json", "native/build-profiles/process-release-v1.json", "build_profile_sha256"),
            ):
                saved = home / relative
                self.assertTrue(saved.is_file(), "Native build provenance was not retained")
                self.assertEqual(saved.read_bytes(), (root / original).read_bytes())
                self.assertEqual(hashlib.sha256(saved.read_bytes()).hexdigest(), record[field])
                self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
            helper = native_helpers.attest_helper("process-release",
                {"native_helpers": {"process-release": record}}, home=home)
            try:
                self.assertEqual(helper.revalidate_for_spawn(), home / "app/bin/process-release")
                result = subprocess.run([str(helper.path)], capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 125)
            finally:
                helper.close()

    def test_build_refuses_existing_target_without_overwrite(self):
        build = self.builder()
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve()
            target = home / "app/bin/process-release"
            target.parent.mkdir(parents=True, mode=0o700)
            (home / "app").chmod(0o700)
            target.write_bytes(b"owned elsewhere")
            identity = target.stat().st_ino
            with self.assertRaises(FileExistsError):
                build(home)
            self.assertEqual(target.read_bytes(), b"owned elsewhere")
            self.assertEqual(target.stat().st_ino, identity)

    def test_existing_build_input_prevents_binary_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve()
            app = home / "app"
            app.mkdir(mode=0o700)
            (app / "build-profiles").mkdir(mode=0o700)
            previous = app / "build-profiles/process-release-v1.json"
            previous.write_bytes(b"previous owner")
            inode = previous.stat().st_ino
            with self.assertRaises(FileExistsError):
                self.builder()(home)
            self.assertEqual(previous.read_bytes(), b"previous owner")
            self.assertEqual(previous.stat().st_ino, inode)
            self.assertFalse((app / "bin/process-release").exists())
            self.assertFalse((app / "native-src/process_release.swift").exists())

    def test_symlinked_build_input_directory_is_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve()
            (home / "app").mkdir(mode=0o700)
            outside = home / "outside"
            outside.mkdir()
            (home / "app/native-src").symlink_to(outside)
            with self.assertRaises((ValueError, OSError)):
                self.builder()(home)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertFalse((home / "app/bin/process-release").exists())

    def test_failed_input_write_never_publishes_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve()
            with patch("process_helper_build.os.write", return_value=0):
                with self.assertRaises(OSError):
                    self.builder()(home)
            self.assertFalse((home / "app/bin/process-release").exists())

    def test_build_refuses_symlinked_binary_directory(self):
        build = self.builder()
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve()
            (home / "app").mkdir(mode=0o700)
            (home / "outside").mkdir(mode=0o700)
            (home / "app/bin").symlink_to(home / "outside", target_is_directory=True)
            with self.assertRaises((OSError, ValueError)):
                build(home)
            self.assertEqual(list((home / "outside").iterdir()), [])

    def test_doctor_attests_installer_bound_registry_and_detects_replacement(self):
        import installer
        import native_helpers
        self.assertTrue(callable(getattr(installer, "_process_helper_doctor_check", None)),
                        "Process helper diagnostic is missing")
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve()
            record = self.builder()(home)
            registry = home / "app/native-helpers.json"
            digest = native_helpers.write_native_helper_registry(registry, {"process-release": record})
            details = registry.stat()
            manifest = {"native_helper_registry": {
                "target": "app/native-helpers.json", "sha256": digest,
                "dev_u32": details.st_dev & 0xffffffff, "ino": details.st_ino,
                "uid": details.st_uid, "mode": 0o600}}
            check = installer._process_helper_doctor_check(home, manifest)
            self.assertEqual(check["status"], "pass")
            self.assertFalse(check["runtime_ready"])
            original = registry.read_bytes()
            registry.rename(registry.with_suffix(".previous"))
            registry.write_bytes(original)
            registry.chmod(0o600)
            self.assertEqual(installer._process_helper_doctor_check(home, manifest)["status"], "fail")
            self.assertEqual(registry.read_bytes(), original)

    def test_doctor_does_not_call_unregistered_binary_ready(self):
        import installer
        self.assertTrue(callable(getattr(installer, "_process_helper_doctor_check", None)),
                        "Process helper diagnostic is missing")
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve()
            self.builder()(home)
            check = installer._process_helper_doctor_check(home, {})
            self.assertNotEqual(check["status"], "pass")
            self.assertFalse(check["runtime_ready"])

    def test_registry_refuses_changed_digest_and_symlink_without_repair(self):
        import native_helpers
        self.assertTrue(callable(getattr(native_helpers, "load_verified_native_helper_registry", None)))
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve()
            registry = home / "app/native-helpers.json"
            digest = native_helpers.write_native_helper_registry(registry, {})
            details = registry.stat()
            manifest = {"native_helper_registry": {
                "target": "app/native-helpers.json", "sha256": digest,
                "dev_u32": details.st_dev & 0xffffffff, "ino": details.st_ino,
                "uid": details.st_uid, "mode": 0o600}}
            self.assertEqual(native_helpers.load_verified_native_helper_registry(home, manifest)["native_helpers"], {})
            original = registry.read_bytes()
            registry.write_bytes(original + b" ")
            with self.assertRaises(native_helpers.NativeHelperAttestationError):
                native_helpers.load_verified_native_helper_registry(home, manifest)
            self.assertEqual(registry.read_bytes(), original + b" ")
            registry.write_bytes(original)
            previous = registry.with_suffix(".previous")
            registry.rename(previous)
            registry.symlink_to(previous)
            with self.assertRaises(native_helpers.NativeHelperAttestationError):
                native_helpers.load_verified_native_helper_registry(home, manifest)
            self.assertTrue(registry.is_symlink())


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    if suite.countTestCases() == 0:
        raise SystemExit("No tests collected")
    result = unittest.TextTestRunner().run(suite)
    raise SystemExit(not result.wasSuccessful())
