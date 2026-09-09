import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

try:
    from executor import fd_ops
except ImportError:
    fd_ops = None


class DescriptorOperationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(fd_ops, "descriptor-relative primitives missing")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.parent = Path(self.tmp.name)
        self.root = self.parent / "workspace"
        self.root.mkdir()
        self.root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.root_fd)

    def test_component_grammar_rejects_escape_and_ambiguous_paths(self):
        for value in ("", "/tmp/x", "../x", "a/../b", "a/./b", "a//b", "a/", "~/x", "a\\b", "a\x00b", "a"*256, 12):
            with self.subTest(value=repr(value)):
                with self.assertRaises((ValueError, TypeError)):
                    fd_ops.components(value)
        self.assertEqual(fd_ops.components("."), ())
        self.assertEqual(fd_ops.components("sous-dossier/été.txt"), ("sous-dossier", "été.txt"))

    def test_retained_root_does_not_follow_replaced_absolute_path(self):
        (self.root / "safe.txt").write_text("original")
        self.root.rename(self.parent / "displaced")
        self.root.mkdir()
        (self.root / "safe.txt").write_text("replacement")
        descriptor = fd_ops.open_regular_at(self.root_fd, "safe.txt")
        try:
            self.assertEqual(os.read(descriptor, 100), b"original")
        finally:
            os.close(descriptor)

    def test_symlink_in_any_component_is_rejected(self):
        outside = self.parent / "outside"
        outside.mkdir()
        (outside / "private.txt").write_text("outside")
        (self.root / "link").symlink_to(outside, target_is_directory=True)
        (self.root / "leaf").symlink_to(outside / "private.txt")
        for relative in ("link/private.txt", "leaf"):
            with self.assertRaises(OSError):
                fd_ops.open_regular_at(self.root_fd, relative)

    def test_hardlink_fifo_and_directory_are_not_regular_files(self):
        outside = self.parent / "outside.txt"
        outside.write_text("private")
        os.link(outside, self.root / "hardlink")
        os.mkfifo(self.root / "fifo")
        (self.root / "directory").mkdir()
        for relative in ("hardlink", "fifo", "directory"):
            with self.subTest(relative=relative):
                with self.assertRaises(OSError):
                    fd_ops.open_regular_at(self.root_fd, relative)

    def test_parent_context_closes_its_fd_and_keeps_borrowed_root_open(self):
        (self.root / "nested").mkdir()
        with fd_ops.open_parent(self.root_fd, "nested/file.txt") as (parent, leaf):
            self.assertEqual(leaf, "file.txt")
            self.assertEqual(os.fstat(parent).st_ino, (self.root / "nested").stat().st_ino)
        with self.assertRaises(OSError):
            os.fstat(parent)
        os.fstat(self.root_fd)

    def test_directory_open_is_owned_and_non_inheritable(self):
        descriptor = fd_ops.open_directory_at(self.root_fd)
        try:
            self.assertNotEqual(descriptor, self.root_fd)
            self.assertFalse(os.get_inheritable(descriptor))
            self.assertEqual(os.listdir(descriptor), [])
        finally:
            os.close(descriptor)

    def test_exclusive_rename_preserves_inode_and_bytes(self):
        self.assertTrue(callable(getattr(fd_ops, "rename_exclusive_at", None)), "exclusive rename missing")
        (self.root / "source").write_bytes(b"source bytes")
        identity = (self.root / "source").stat().st_ino
        fd_ops.rename_exclusive_at(self.root_fd, "source", self.root_fd, "destination")
        self.assertFalse((self.root / "source").exists())
        self.assertEqual((self.root / "destination").read_bytes(), b"source bytes")
        self.assertEqual((self.root / "destination").stat().st_ino, identity)

    def test_exclusive_rename_never_overwrites_existing_target(self):
        self.assertTrue(callable(getattr(fd_ops, "rename_exclusive_at", None)), "exclusive rename missing")
        (self.root / "source").write_bytes(b"source")
        (self.root / "destination").write_bytes(b"keep")
        identity = (self.root / "destination").stat().st_ino
        with self.assertRaises(FileExistsError):
            fd_ops.rename_exclusive_at(self.root_fd, "source", self.root_fd, "destination")
        self.assertEqual((self.root / "source").read_bytes(), b"source")
        self.assertEqual((self.root / "destination").read_bytes(), b"keep")
        self.assertEqual((self.root / "destination").stat().st_ino, identity)

    def test_rename_requires_single_leaf_names(self):
        self.assertTrue(callable(getattr(fd_ops, "rename_exclusive_at", None)), "exclusive rename missing")
        for source, destination in (("../source","dest"), ("source","a/b"), (".","dest")):
            with self.assertRaises(ValueError):
                fd_ops.rename_exclusive_at(self.root_fd, source, self.root_fd, destination)

    def test_create_directory_at_is_exclusive_and_reports_identity(self):
        self.assertTrue(callable(getattr(fd_ops, "create_directory_at", None)), "descriptor mkdir missing")
        identity = fd_ops.create_directory_at(self.root_fd, "new")
        self.assertEqual(identity.st_ino, (self.root / "new").stat().st_ino)
        with self.assertRaises(FileExistsError):
            fd_ops.create_directory_at(self.root_fd, "new")

    def test_missing_native_rename_has_no_overwriting_fallback(self):
        (self.root / "source").write_bytes(b"source")
        (self.root / "destination").write_bytes(b"keep")
        with patch.object(fd_ops, "_renameatx_np", None):
            with self.assertRaisesRegex(OSError, "RENAME_EXCL_UNAVAILABLE"):
                fd_ops.rename_exclusive_at(self.root_fd, "source", self.root_fd, "destination")
        self.assertEqual((self.root / "source").read_bytes(), b"source")
        self.assertEqual((self.root / "destination").read_bytes(), b"keep")

    def test_atomic_exchange_preserves_both_files(self):
        self.assertTrue(callable(getattr(fd_ops, "rename_exchange_at", None)), "atomic exchange missing")
        (self.root / "a").write_bytes(b"A")
        (self.root / "b").write_bytes(b"B")
        a, b = (self.root / "a").stat().st_ino, (self.root / "b").stat().st_ino
        fd_ops.rename_exchange_at(self.root_fd, "a", self.root_fd, "b")
        self.assertEqual(((self.root / "a").read_bytes(), (self.root / "b").read_bytes()), (b"B", b"A"))
        self.assertEqual(((self.root / "a").stat().st_ino, (self.root / "b").stat().st_ino), (b, a))


if __name__ == "__main__":
    unittest.main()
