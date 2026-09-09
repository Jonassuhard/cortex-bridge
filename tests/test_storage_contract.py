from __future__ import annotations

import tempfile
import unittest
import os
from pathlib import Path, PurePosixPath
from unittest.mock import patch
from dataclasses import replace
from storage_broker import MountedImageProof

from storage_lock import open_storage_lock_set
from storage_contract import StorageContract, StorageBinding, StorageContractError, probe_mount_fd
from storage_result import StorageStatus
from storage_transition import StorageProjection, begin_transition_locked, commit_transition_locked
from executor.workspace_handle import MountFacts


class FixtureImageBroker:
    """Explicit test-only metadata proof, not native encryption evidence."""
    def __init__(self, **changes):
        self.changes = changes

    def _probe_mounted_image_locked(self, lock_set, **request):
        proof = MountedImageProof(request['mount_path'], *request['image_identity'],
            *request['mount_identity'], request['expected_volume_name'],
            request['expected_volume_uuid'], request['expected_encryption_uuid'],
            1, 'apfs', True, True, 'a' * 64)
        return replace(proof, **self.changes)


class StorageContractTests(unittest.TestCase):
    def commit_image_fixture(self, locks, journal):
        (self.home / 'storage' / journal.target_image_basename).mkdir(parents=True)
        return commit_transition_locked(locks, replace(journal,
            target_encryption_uuid='33333333-3333-4333-8333-333333333333'))
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

    def workspace_fixture(self):
        mount = self.home / "mount"
        workspace = mount / "20_WORKSPACES" / "project"
        workspace.mkdir(parents=True)
        descriptor = os.open(mount, os.O_RDONLY | os.O_DIRECTORY)
        device = os.fstat(descriptor).st_dev & 0xffffffff
        # Binding/mount observations are synthetic; traversal uses real FDs.
        binding = StorageBinding("fixture", os.dup(descriptor), descriptor, os.dup(descriptor),
            "fixture", (1, 2), device, (1, 2), "fixture", "fixture", "fixture",
            "fixture.sparsebundle", PurePosixPath("20_WORKSPACES"))
        self.addCleanup(binding.close)
        facts = MountFacts(device, (1, 2), 0, "fixture", "fixture", str(mount), "fixture")
        contract = StorageContract(self.home, broker=object(), fd_probe=lambda fd: facts)
        return contract, binding, workspace

    def test_workspace_admission_rejects_intermediate_symlink(self):
        contract, binding, workspace = self.workspace_fixture()
        outside = self.home / "outside"
        (outside / "project").mkdir(parents=True)
        (workspace.parent / "link").symlink_to(outside, target_is_directory=True)
        with open_storage_lock_set(self.home, install_mode="shared", storage_mode="exclusive") as locks:
            with self.assertRaises(StorageContractError):
                handle = contract.open_workspace_locked(locks, binding, "20_WORKSPACES/link/project")
                handle.close()
        self.assertTrue((outside / "project").is_dir())

    def test_workspace_admission_rejects_ambiguous_raw_components(self):
        contract, binding, _ = self.workspace_fixture()
        with open_storage_lock_set(self.home, install_mode="shared", storage_mode="exclusive") as locks:
            for path in ("20_WORKSPACES//project", "20_WORKSPACES/./project",
                         "20_WORKSPACES/project/"):
                with self.subTest(path=path), self.assertRaises(StorageContractError):
                    handle = contract.open_workspace_locked(locks, binding, path)
                    handle.close()

    def test_workspace_admission_valid_path_retains_exact_directory(self):
        contract, binding, workspace = self.workspace_fixture()
        with open_storage_lock_set(self.home, install_mode="shared", storage_mode="exclusive") as locks:
            with contract.open_workspace_locked(locks, binding, "20_WORKSPACES/project") as handle:
                fd = handle.duplicate_workspace_fd()
                try:
                    self.assertEqual(os.fstat(fd).st_ino, workspace.stat().st_ino)
                finally:
                    os.close(fd)

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

    def test_binding_rejects_unrelated_root_on_the_same_filesystem(self):
        mount = self.home / "mount"
        (mount / "20_WORKSPACES").mkdir(parents=True)
        outside = self.home / "unrelated"
        outside.mkdir()
        self.assertEqual(mount.stat().st_dev, outside.stat().st_dev)
        with open_storage_lock_set(self.home, install_mode="exclusive", storage_mode="exclusive") as locks:
            journal = begin_transition_locked(locks, self.home, self.projection,
                target_image_basename="CORTEX_BRIDGE_2026_09.sparsebundle")
            commit_transition_locked(locks, journal)
            # Synthetic mount facts isolate directory binding, not APFS identity.
            contract = StorageContract(self.home, broker=object(),
                environment={"CORTEX_STORAGE_MOUNT": str(mount), "CORTEX_STORAGE_ROOT": str(outside)},
                fd_probe=lambda fd: MountFacts(os.fstat(fd).st_dev & 0xffffffff,
                    (1, 2), 0, "apfs", "fixture", str(mount)))
            with self.assertRaisesRegex(StorageContractError, "STORAGE_ROOT_NOT_MANAGED"):
                binding = contract.open_locked(locks)
                self.addCleanup(binding.close)

    def test_binding_rejects_mount_path_replaced_after_descriptor_open(self):
        mount = self.home / "mount"
        root = mount / "20_WORKSPACES"
        root.mkdir(parents=True)
        with open_storage_lock_set(self.home, install_mode="exclusive", storage_mode="exclusive") as locks:
            journal = begin_transition_locked(locks, self.home, self.projection,
                target_image_basename="CORTEX_BRIDGE_2026_09.sparsebundle")
            commit_transition_locked(locks, journal)
            contract = StorageContract(self.home, broker=object(),
                environment={"CORTEX_STORAGE_MOUNT": str(mount), "CORTEX_STORAGE_ROOT": str(root)},
                fd_probe=lambda fd: MountFacts(os.fstat(fd).st_dev & 0xffffffff,
                    (1, 2), 0, "apfs", "fixture", str(mount)))
            real_open = os.open
            opened_mounts = []
            def swap_after_open(path, flags, *args, **kwargs):
                fd = real_open(path, flags, *args, **kwargs)
                if Path(path) == mount and "dir_fd" not in kwargs:
                    opened_mounts.append(fd)
                    mount.rename(self.home / "held-mount")
                    root.mkdir(parents=True)
                return fd
            with patch("storage_contract.os.open", side_effect=swap_after_open):
                with self.assertRaisesRegex(StorageContractError, "STORAGE_DESCRIPTOR_CHANGED"):
                    binding = contract.open_locked(locks)
                    self.addCleanup(binding.close)
            self.assertEqual(len(opened_mounts), 1)
            for fd in opened_mounts:
                with self.assertRaises(OSError):
                    os.fstat(fd)

    def test_binding_retains_the_exact_managed_root_descriptor(self):
        mount = self.home / "mount"
        root = mount / "20_WORKSPACES"
        root.mkdir(parents=True)
        with open_storage_lock_set(self.home, install_mode="exclusive", storage_mode="exclusive") as locks:
            journal = begin_transition_locked(locks, self.home, self.projection,
                target_image_basename="CORTEX_BRIDGE_2026_09.sparsebundle")
            self.commit_image_fixture(locks, journal)
            # Directory binding only: these facts do not establish encryption.
            contract = StorageContract(self.home, broker=FixtureImageBroker(),
                environment={"CORTEX_STORAGE_MOUNT": str(mount), "CORTEX_STORAGE_ROOT": str(root)},
                fd_probe=lambda fd: MountFacts(os.fstat(fd).st_dev & 0xffffffff,
                    (1, 2), 0, "apfs", "fixture", str(mount),
                    "11111111-1111-4111-8111-111111111111"))
            with contract.open_locked(locks) as binding:
                self.assertEqual(os.fstat(binding.mount_fd).st_ino, mount.stat().st_ino)
                self.assertEqual(os.fstat(binding.root_fd).st_ino, root.stat().st_ino)

    def test_binding_uses_observed_volume_uuid_and_rejects_configuration_mismatch(self):
        mount = self.home / 'mount'
        (mount / '20_WORKSPACES').mkdir(parents=True)
        observed = '11111111-1111-4111-8111-111111111111'
        with open_storage_lock_set(self.home, install_mode='exclusive', storage_mode='exclusive') as locks:
            journal = begin_transition_locked(locks, self.home, self.projection,
                target_image_basename='CORTEX_BRIDGE_2026_09.sparsebundle')
            self.commit_image_fixture(locks, journal)
            # Synthetic APFS observation isolates identity binding. It is not
            # evidence that this temporary directory is encrypted.
            def facts(fd):
                return MountFacts(os.fstat(fd).st_dev & 0xffffffff, (1, 2), 0,
                                  'apfs', 'fixture', str(mount), observed)
            environment = {'CORTEX_STORAGE_MOUNT': str(mount)}
            contract = StorageContract(self.home, broker=FixtureImageBroker(), environment=environment, fd_probe=facts)
            with contract.open_locked(locks) as binding:
                self.assertEqual(binding.apfs_volume_uuid, observed)
                self.assertEqual(binding.encryption_uuid, '33333333-3333-4333-8333-333333333333')
            for changes in ({'encrypted': False}, {'mapping_count': 2}, {'image_ino': 0}, {'writable': False}):
                contract = StorageContract(self.home, broker=FixtureImageBroker(**changes),
                    environment=environment, fd_probe=facts)
                with self.subTest(proof=changes), self.assertRaisesRegex(
                        StorageContractError, 'STORAGE_ENCRYPTED_IMAGE_UNPROVEN'):
                    with contract.open_locked(locks):
                        pass
            for missing in (None, '', 'unknown', '00000000-0000-0000-0000-000000000000'):
                contract = StorageContract(self.home, broker=object(), environment=environment,
                    fd_probe=lambda fd: MountFacts(os.fstat(fd).st_dev & 0xffffffff,
                        (1, 2), 0, 'apfs', 'fixture', str(mount), missing))
                with self.subTest(observed=missing), self.assertRaisesRegex(
                        StorageContractError, 'STORAGE_VOLUME_IDENTITY_UNAVAILABLE'):
                    with contract.open_locked(locks):
                        pass
            environment['CORTEX_STORAGE_APFS_VOLUME_UUID'] = '22222222-2222-4222-8222-222222222222'
            contract = StorageContract(self.home, broker=object(), environment=environment, fd_probe=facts)
            with self.assertRaisesRegex(StorageContractError, 'STORAGE_VOLUME_IDENTITY_MISMATCH'):
                with contract.open_locked(locks):
                    pass

    def test_revalidation_rejects_volume_uuid_change_with_same_device_and_fsid(self):
        contract, binding, _ = self.workspace_fixture()
        binding.apfs_volume_uuid = '11111111-1111-4111-8111-111111111111'
        contract._fd_probe = lambda fd: MountFacts(binding.mount_device_u32, binding.mount_fsid_u32,
            0, 'apfs', 'fixture', 'fixture', '22222222-2222-4222-8222-222222222222')
        with open_storage_lock_set(self.home, install_mode='shared', storage_mode='exclusive') as locks:
            with self.assertRaisesRegex(StorageContractError, 'STORAGE_DESCRIPTOR_CHANGED'):
                contract.revalidate_locked(locks, binding)

    def test_observed_apfs_and_committed_journal_are_not_encrypted_image_proof(self):
        mount = self.home / 'mount'
        (mount / '20_WORKSPACES').mkdir(parents=True)
        with open_storage_lock_set(self.home, install_mode='exclusive', storage_mode='exclusive') as locks:
            journal = begin_transition_locked(locks, self.home, self.projection,
                target_image_basename='CORTEX_BRIDGE_2026_09.sparsebundle')
            commit_transition_locked(locks, journal)
            contract = StorageContract(self.home, broker=object(),
                fd_probe=lambda fd: MountFacts(os.fstat(fd).st_dev & 0xffffffff,
                    (1, 2), 0, 'apfs', 'fixture', str(mount),
                    '11111111-1111-4111-8111-111111111111'))
            status = contract.probe_locked(locks)
            self.assertFalse(status.runtime_allowed)
            self.assertFalse(status.mounted)
            with self.assertRaisesRegex(StorageContractError, 'STORAGE_ENCRYPTED_IMAGE_UNPROVEN'):
                with contract.open_locked(locks):
                    pass


if __name__ == "__main__":
    unittest.main()
