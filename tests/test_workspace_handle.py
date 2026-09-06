from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path, PurePosixPath

from executor.workspace_handle import (
    MountFacts,
    WorkspaceHandle,
    WorkspaceHandleClosed,
    WorkspaceIdentityChanged,
)


class WorkspaceHandleTests(unittest.TestCase):
    def test_verified_fds_are_duplicated_and_revalidated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "mount"
            workspaces = root / "20_WORKSPACES" / "qa"
            workspaces.mkdir(mode=0o700, parents=True)
            mount_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            workspace_fd = os.open(workspaces, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            facts = MountFacts(os.fstat(mount_fd).st_dev & 0xFFFFFFFF, (1, 2), 0, "apfs", "/dev/none", str(root))
            handle = WorkspaceHandle.from_verified_fds(
                mount_fd=mount_fd, workspace_fd=workspace_fd,
                storage_transaction_id="tx", apfs_volume_uuid="uuid",
                relative_path=PurePosixPath("20_WORKSPACES/qa"),
                fd_probe=lambda _fd: facts,
            )
            os.close(mount_fd)
            os.close(workspace_fd)
            self.assertEqual(handle.display_path, "20_WORKSPACES/qa")
            self.assertEqual(handle.revalidate(), handle.identity)
            duplicate = handle.duplicate_workspace_fd()
            self.assertTrue(stat.S_ISDIR(os.fstat(duplicate).st_mode))
            os.close(duplicate)
            handle.close()
            with self.assertRaises(WorkspaceHandleClosed):
                _ = handle.workspace_fd

    def test_path_and_identity_rejections(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "mount"
            workspaces = root / "20_WORKSPACES"
            workspaces.mkdir(mode=0o700, parents=True)
            mount_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            workspace_fd = os.open(workspaces, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            facts = MountFacts(os.fstat(mount_fd).st_dev & 0xFFFFFFFF, (1, 2), 0, "apfs", "/dev/none", str(root))
            with self.assertRaises(ValueError):
                WorkspaceHandle.from_verified_fds(
                    mount_fd=mount_fd, workspace_fd=workspace_fd,
                    storage_transaction_id="tx", apfs_volume_uuid="uuid",
                    relative_path=PurePosixPath("Desktop"), fd_probe=lambda _fd: facts,
                )
            with self.assertRaises(ValueError):
                WorkspaceHandle.from_verified_fds(
                    mount_fd=mount_fd, workspace_fd=workspace_fd,
                    storage_transaction_id="tx", apfs_volume_uuid="uuid",
                    relative_path=PurePosixPath("20_WORKSPACES"),
                    fd_probe=lambda _fd: MountFacts(999, (1, 2), 0, "apfs", "/dev/none", str(root)),
                )
            os.close(mount_fd)
            os.close(workspace_fd)


if __name__ == "__main__":
    unittest.main()
