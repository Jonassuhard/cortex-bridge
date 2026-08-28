from __future__ import annotations

import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-cortex-storage.py"
EXPECTED_UUID = "12345678-1234-1234-1234-123456789ABC"


class StorageGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)

    def load_guard(self):
        self.assertTrue(SCRIPT.is_file(), "storage guard script is not implemented")
        spec = importlib.util.spec_from_file_location("check_cortex_storage", SCRIPT)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def write_bootstrap(
        self,
        *,
        mount_path: str,
        volume_uuid: str = EXPECTED_UUID,
        encrypted_image_path: str | None = None,
        storage_root: str | None = None,
    ) -> Path:
        image = Path(encrypted_image_path) if encrypted_image_path else self.root / "vault.sparsebundle"
        if image.is_absolute():
            image.mkdir(parents=True, exist_ok=True)
        storage = Path(storage_root) if storage_root else Path(mount_path) / "CORTEX_BRIDGE"
        if storage.is_absolute() and Path(mount_path).is_dir():
            storage.mkdir(parents=True, exist_ok=True)
            storage.chmod(0o700)
        bootstrap = self.root / "storage-bootstrap.json"
        bootstrap.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "mount_path": mount_path,
                    "volume_uuid": volume_uuid,
                    "encrypted_image_path": str(image),
                    "storage_root": str(storage),
                }
            ),
            encoding="utf-8",
        )
        bootstrap.chmod(0o600)
        return bootstrap

    def run_guard(self, bootstrap: Path, probe, image_probe=lambda _mount, _image: True):
        module = self.load_guard()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = module.main(
                ["--bootstrap", str(bootstrap)],
                volume_probe=probe,
                encrypted_image_probe=image_probe,
            )
        return code, stdout.getvalue(), stderr.getvalue()

    @staticmethod
    def unexpected_probe(_mount_path: Path):
        raise AssertionError("volume probe must not run for invalid bootstrap state")

    @staticmethod
    def identity(
        mount: Path,
        *,
        volume_uuid: str = EXPECTED_UUID,
        filesystem_type: str = "apfs",
        writable: bool = True,
    ):
        return {
            "mount_path": str(mount),
            "volume_uuid": volume_uuid,
            "filesystem_type": filesystem_type,
            "writable": writable,
        }

    def test_missing_bootstrap_is_rejected_clearly(self) -> None:
        code, _stdout, stderr = self.run_guard(
            self.root / "missing.json",
            self.unexpected_probe,
        )

        self.assertEqual(code, 2)
        self.assertIn("STORAGE_BOOTSTRAP_MISSING", stderr)

    def test_invalid_json_is_rejected_clearly(self) -> None:
        bootstrap = self.root / "storage-bootstrap.json"
        bootstrap.write_text("{not-json", encoding="utf-8")
        bootstrap.chmod(0o600)

        code, _stdout, stderr = self.run_guard(bootstrap, self.unexpected_probe)

        self.assertEqual(code, 2)
        self.assertIn("STORAGE_BOOTSTRAP_INVALID", stderr)

    def test_symlinked_or_non_private_bootstrap_is_rejected(self) -> None:
        valid = self.write_bootstrap(mount_path=str(self.root / "missing"))
        symlink = self.root / "bootstrap-link.json"
        symlink.symlink_to(valid)

        code, _stdout, stderr = self.run_guard(symlink, self.unexpected_probe)

        self.assertEqual(code, 2)
        self.assertIn("STORAGE_BOOTSTRAP_INVALID", stderr)

        symlink.unlink()
        valid.chmod(0o666)
        code, _stdout, stderr = self.run_guard(valid, self.unexpected_probe)
        self.assertEqual(code, 2)
        self.assertIn("STORAGE_BOOTSTRAP_INVALID", stderr)

    def test_bootstrap_replaced_after_fd_read_is_rejected(self) -> None:
        mount = self.root / "cortex-volume"
        mount.mkdir()
        bootstrap = self.write_bootstrap(mount_path=str(mount))
        preserved = self.root / "preserved-bootstrap.json"
        replacement = bootstrap.read_bytes()
        module = self.load_guard()
        import storage_guard

        real_json_load = storage_guard.json.load

        def replace_after_read(stream):
            payload = real_json_load(stream)
            bootstrap.rename(preserved)
            bootstrap.write_bytes(replacement)
            bootstrap.chmod(0o600)
            return payload

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("storage_guard.json.load", side_effect=replace_after_read), redirect_stdout(
            stdout
        ), redirect_stderr(stderr):
            code = module.main(
                ["--bootstrap", str(bootstrap)],
                volume_probe=lambda _path: self.identity(mount),
                encrypted_image_probe=lambda _mount, _image: True,
            )

        self.assertEqual(code, 2)
        self.assertIn("STORAGE_BOOTSTRAP_INVALID", stderr.getvalue())

    def test_relative_mount_path_is_rejected(self) -> None:
        bootstrap = self.write_bootstrap(
            mount_path="relative/cortex",
            storage_root=str(self.root / "storage"),
        )

        code, _stdout, stderr = self.run_guard(bootstrap, self.unexpected_probe)

        self.assertEqual(code, 2)
        self.assertIn("STORAGE_PATH_INVALID", stderr)

    def test_absent_volume_is_rejected_before_probe(self) -> None:
        bootstrap = self.write_bootstrap(mount_path=str(self.root / "not-mounted"))

        code, _stdout, stderr = self.run_guard(bootstrap, self.unexpected_probe)

        self.assertEqual(code, 3)
        self.assertIn("STORAGE_VOLUME_MISSING", stderr)

    def test_existing_directory_that_is_not_the_reported_mount_is_rejected(self) -> None:
        mount = self.root / "cortex-volume"
        mount.mkdir()
        bootstrap = self.write_bootstrap(mount_path=str(mount))

        code, _stdout, stderr = self.run_guard(
            bootstrap,
            lambda _path: self.identity(self.root),
        )

        self.assertEqual(code, 3)
        self.assertIn("STORAGE_VOLUME_MISSING", stderr)

    def test_different_volume_uuid_is_rejected(self) -> None:
        mount = self.root / "cortex-volume"
        mount.mkdir()
        bootstrap = self.write_bootstrap(mount_path=str(mount))

        code, _stdout, stderr = self.run_guard(
            bootstrap,
            lambda _path: self.identity(
                mount,
                volume_uuid="AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
            ),
        )

        self.assertEqual(code, 4)
        self.assertIn("STORAGE_UUID_MISMATCH", stderr)

    def test_matching_mount_and_uuid_are_the_only_success_case(self) -> None:
        mount = self.root / "cortex-volume"
        mount.mkdir()
        bootstrap = self.write_bootstrap(
            mount_path=str(mount),
            volume_uuid=EXPECTED_UUID.lower(),
        )

        code, stdout, stderr = self.run_guard(
            bootstrap,
            lambda _path: self.identity(mount),
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("STORAGE_READY", stdout)

    def test_json_output_returns_the_storage_root_from_the_verified_payload(self) -> None:
        mount = self.root / "cortex-volume"
        mount.mkdir()
        storage = mount / "CORTEX_BRIDGE"
        bootstrap = self.write_bootstrap(
            mount_path=str(mount),
            storage_root=str(storage),
        )
        module = self.load_guard()
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = module.main(
                ["--bootstrap", str(bootstrap), "--json"],
                volume_probe=lambda _path: self.identity(mount),
                encrypted_image_probe=lambda _mount, _image: True,
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["storage_root"], str(storage.resolve()))
        self.assertEqual(payload["mount_path"], str(mount.resolve()))
        self.assertEqual(payload["volume_uuid"], EXPECTED_UUID)

    def test_non_apfs_volume_is_rejected(self) -> None:
        mount = self.root / "cortex-volume"
        mount.mkdir()
        bootstrap = self.write_bootstrap(mount_path=str(mount))

        code, _stdout, stderr = self.run_guard(
            bootstrap,
            lambda _path: self.identity(mount, filesystem_type="exfat"),
        )

        self.assertEqual(code, 5)
        self.assertIn("STORAGE_FILESYSTEM_UNSAFE", stderr)

    def test_read_only_volume_is_rejected(self) -> None:
        mount = self.root / "cortex-volume"
        mount.mkdir()
        bootstrap = self.write_bootstrap(mount_path=str(mount))

        code, _stdout, stderr = self.run_guard(
            bootstrap,
            lambda _path: self.identity(mount, writable=False),
        )

        self.assertEqual(code, 5)
        self.assertIn("STORAGE_VOLUME_READ_ONLY", stderr)

    def test_unencrypted_backing_image_is_rejected(self) -> None:
        mount = self.root / "cortex-volume"
        mount.mkdir()
        bootstrap = self.write_bootstrap(mount_path=str(mount))

        code, _stdout, stderr = self.run_guard(
            bootstrap,
            lambda _path: self.identity(mount),
            image_probe=lambda _mount, _image: False,
        )

        self.assertEqual(code, 6)
        self.assertIn("STORAGE_ENCRYPTION_UNVERIFIED", stderr)

    def test_storage_root_outside_verified_mount_is_rejected(self) -> None:
        mount = self.root / "cortex-volume"
        mount.mkdir()
        outside = self.root / "outside-storage"
        outside.mkdir()
        bootstrap = self.write_bootstrap(
            mount_path=str(mount),
            storage_root=str(outside),
        )

        code, _stdout, stderr = self.run_guard(
            bootstrap,
            lambda _path: self.identity(mount),
        )

        self.assertEqual(code, 7)
        self.assertIn("STORAGE_ROOT_UNSAFE", stderr)

    def test_symlinked_storage_root_inside_verified_mount_is_rejected(self) -> None:
        mount = self.root / "cortex-volume"
        mount.mkdir()
        real_storage = mount / "real-storage"
        real_storage.mkdir()
        alias = mount / "storage-alias"
        alias.symlink_to(real_storage, target_is_directory=True)
        bootstrap = self.write_bootstrap(
            mount_path=str(mount),
            storage_root=str(alias),
        )

        code, _stdout, stderr = self.run_guard(
            bootstrap,
            lambda _path: self.identity(mount),
        )

        self.assertEqual(code, 7)
        self.assertIn("STORAGE_ROOT_UNSAFE", stderr)

    def test_non_private_storage_root_is_rejected(self) -> None:
        mount = self.root / "cortex-volume"
        mount.mkdir()
        storage = mount / "CORTEX_BRIDGE"
        bootstrap = self.write_bootstrap(
            mount_path=str(mount),
            storage_root=str(storage),
        )
        storage.chmod(0o777)

        code, _stdout, stderr = self.run_guard(
            bootstrap,
            lambda _path: self.identity(mount),
        )

        self.assertEqual(code, 7)
        self.assertIn("STORAGE_ROOT_UNSAFE", stderr)

    def test_storage_root_on_nested_foreign_device_or_owner_is_rejected(self) -> None:
        mount = self.root / "cortex-volume"
        mount.mkdir()
        storage = mount / "CORTEX_BRIDGE"
        bootstrap = self.write_bootstrap(
            mount_path=str(mount),
            storage_root=str(storage),
        )
        module = self.load_guard()

        def run_with(storage_probe):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = module.main(
                    ["--bootstrap", str(bootstrap)],
                    volume_probe=lambda _path: self.identity(mount),
                    encrypted_image_probe=lambda _mount, _image: True,
                    storage_identity_probe=storage_probe,
                )
            return code, stderr.getvalue()

        current_uid = os.getuid()
        code, stderr = run_with(
            lambda path: {
                "dev": 200 if path == storage.resolve() else 100,
                "is_dir": True,
                "mode": 0o700,
                "uid": current_uid,
            }
        )
        self.assertEqual(code, 7)
        self.assertIn("STORAGE_ROOT_UNSAFE", stderr)

        code, stderr = run_with(
            lambda path: {
                "dev": 100,
                "is_dir": True,
                "mode": 0o700,
                "uid": current_uid + 1 if path == storage.resolve() else current_uid,
            }
        )
        self.assertEqual(code, 7)
        self.assertIn("STORAGE_ROOT_UNSAFE", stderr)


if __name__ == "__main__":
    unittest.main()
