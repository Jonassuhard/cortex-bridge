from __future__ import annotations

import os
import hashlib
import stat
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from native_helpers import (
    NativeHelperAttestationError,
    attest_broker_executable,
    load_native_helper_registry,
    native_helper_manifest_record,
    verify_attested_fd,
    write_native_helper_registry,
)


class NativeHelpersTests(unittest.TestCase):
    def test_registry_preserves_generation_order_and_hashes_published_bytes(self):
        names = ["macos-ax-send", "storage-mount-probe", "storage-broker", "process-release"]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "registry.json"
            records = {name: {"target": name} for name in names}
            digest = write_native_helper_registry(path, records)
            self.assertEqual(list(load_native_helper_registry(path)["native_helpers"]), names)
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_registry_short_writes_publish_complete_bytes(self):
        real_write = os.write
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "registry.json"
            with patch("native_helpers.os.write", side_effect=lambda fd, data: real_write(fd, data[:7])):
                digest = write_native_helper_registry(path, {"process-release": {"target": "helper"}})
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(load_native_helper_registry(path)["native_helpers"],
                             {"process-release": {"target": "helper"}})

    def test_registry_zero_write_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "registry.json"
            write_native_helper_registry(path, {})
            before, inode = path.read_bytes(), path.stat().st_ino
            with patch("native_helpers.os.write", return_value=0):
                with self.assertRaises(OSError):
                    write_native_helper_registry(path, {"process-release": {}})
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(path.stat().st_ino, inode)

    def test_attestation_holds_identity_fd_and_registry_is_atomic(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            helper = root / "helper"
            helper.write_bytes(b"helper")
            helper.chmod(0o700)
            attested = attest_broker_executable(helper, build_profile_sha256="b" * 64)
            self.addCleanup(attested.close)
            verify_attested_fd(attested)
            record = native_helper_manifest_record(
                target="app/bin/cortex-storage-broker", source="native.swift",
                source_sha256="a" * 64, build_profile_sha256="b" * 64,
                attested=attested,
            )
            path = root / "owned-manifest.json"
            sha = write_native_helper_registry(path, {"storage-broker": record})
            self.assertEqual(len(sha), 64)
            self.assertEqual(load_native_helper_registry(path)["schema_version"], 1)

    def test_mode_or_identity_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            helper = Path(td) / "helper"
            helper.write_bytes(b"helper")
            helper.chmod(0o700)
            attested = attest_broker_executable(helper)
            self.addCleanup(attested.close)
            helper.chmod(0o600)
            with self.assertRaises(NativeHelperAttestationError):
                verify_attested_fd(attested)


if __name__ == "__main__":
    unittest.main()
