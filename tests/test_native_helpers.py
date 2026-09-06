from __future__ import annotations

import os
import stat
import tempfile
import unittest
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
