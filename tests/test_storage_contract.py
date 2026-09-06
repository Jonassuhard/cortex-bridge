from __future__ import annotations

import tempfile
import unittest
import os
from pathlib import Path

from storage_lock import open_storage_lock_set
from storage_contract import StorageContract, StorageContractError, probe_mount_fd
from storage_result import StorageStatus
from storage_transition import StorageProjection, begin_transition_locked, commit_transition_locked
from executor.workspace_handle import MountFacts


class StorageContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir(mode=0o700)
        self.projection = StorageProjection("/mnt/20_WORKSPACES", "/mnt/50_CACHE_REBUILDABLE/browser-profiles", "chrome_extension")

    def tearDown(self):
        self.tmp.cleanup()

    def test_optional_storage_is_ready_without_external_probe(self):
        with open_storage_lock_set(self.home, install_mode="shared", storage_mode="shared") as locks:
            contract = StorageContract(self.home, broker=object())
            status = contract.probe_locked(locks)
            self.assertEqual(status, StorageStatus("PASS", "STORAGE_NOT_REQUIRED", None, "UNCONFIGURED", False, True))

    def test_active_transition_blocks_runtime_and_wrong_lock_fails_closed(self):
        with open_storage_lock_set(self.home, install_mode="exclusive", storage_mode="exclusive") as locks:
            begin = begin_transition_locked(
                locks, self.home, self.projection,
                target_image_basename="CORTEX_BRIDGE_2026_09.sparsebundle",
            )
            contract = StorageContract(self.home, broker=object())
            status = contract.probe_locked(locks)
            self.assertEqual(status.code, "STORAGE_NOT_READY")
            self.assertFalse(status.runtime_allowed)
            self.assertEqual(contract.assert_runtime_ready_locked(locks).code, "STORAGE_NOT_READY")
            locks.close()
            self.assertEqual(contract.probe_locked(locks).verdict, "UNCLEAR")

    def test_default_mount_probe_never_fabricates_apfs_proof(self):
        mount = self.home / "mount"
        root = mount / "20_WORKSPACES"
        root.mkdir(parents=True, mode=0o700)
        (self.home / "storage-transition.json").write_text("{}", encoding="utf-8")
        with open_storage_lock_set(self.home, install_mode="exclusive", storage_mode="exclusive") as locks:
            # A committed journal is intentionally not enough to open a vault;
            # the descriptor probe must still provide real APFS/fsid metadata.
            contract = StorageContract(
                self.home,
                broker=object(),
                environment={"CORTEX_STORAGE_MOUNT": str(mount), "CORTEX_STORAGE_ROOT": str(root)},
            )
            status = contract.probe_locked(locks)
            self.assertEqual(status.code, "STORAGE_NOT_READY")
            with self.assertRaisesRegex(StorageContractError, "STORAGE_NOT_READY"):
                contract.open_locked(locks)
            fd = os.open(mount, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                self.assertEqual(probe_mount_fd(fd).filesystem_type, "unknown")
            finally:
                os.close(fd)


if __name__ == "__main__":
    unittest.main()
