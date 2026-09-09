import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class InstallResourceTreeTests(unittest.TestCase):
    def test_script_caches_are_not_installed_but_unlisted_installed_caches_are_rejected(self):
        self.application_fixture()
        cache = self.source / "scripts/__pycache__"
        cache.mkdir()
        (cache / "old.pyc").write_bytes(b"old cache")
        (self.source / "scripts/old.pyo").write_bytes(b"old optimized cache")
        manifest = self.api.stage_application_resources(self.source_fd, self.destination_fd)
        self.assertTrue((cache / "old.pyc").exists())
        self.assertFalse((self.destination / "scripts/__pycache__").exists())
        self.assertFalse((self.destination / "scripts/old.pyo").exists())
        (self.destination / "scripts/__pycache__").mkdir(mode=0o700)
        with self.assertRaises(ValueError):
            self.api.verify_application_resources(self.destination_fd, manifest)

    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("install_resource_tree"),
                             "Descriptor-relative installer resource staging is missing")
        import install_resource_tree
        self.api = install_resource_tree
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.destination = self.root / "destination"
        for path in (self.source, self.destination):
            path.mkdir(mode=0o700)
        self.source_fd = self.open_dir(self.source)
        self.destination_fd = self.open_dir(self.destination)

    def open_dir(self, path):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, fd)
        return fd

    def test_nested_copy_preserves_bytes_empty_directories_and_execution_mode(self):
        (self.source / "empty").mkdir()
        (self.source / "nested").mkdir()
        (self.source / "nested/data").write_bytes(b"abc\x00")
        (self.source / "launch").write_bytes(b"#!/bin/sh\n")
        (self.source / "launch").chmod(0o755)
        records = self.api.stage_resource_tree(self.source_fd, self.destination_fd, "assets")
        self.assertEqual([r["path"] for r in records], ["empty", "launch", "nested", "nested/data"])
        target = self.destination / "assets"
        self.assertEqual((target / "nested/data").read_bytes(), b"abc\x00")
        self.assertTrue((target / "empty").is_dir())
        self.assertEqual((target / "launch").stat().st_mode & 0o777, 0o700)
        self.assertEqual((target / "nested/data").stat().st_mode & 0o777, 0o600)
        self.assertEqual(records[-1]["sha256"], hashlib.sha256(b"abc\x00").hexdigest())
        self.api.verify_resource_tree(self.open_dir(target), records)

    def test_retained_source_not_reopened_after_path_replacement(self):
        (self.source / "original").write_text("retained")
        self.source.rename(self.root / "previous")
        self.source.mkdir()
        (self.source / "other").write_text("replacement")
        self.api.stage_resource_tree(self.source_fd, self.destination_fd, "assets")
        self.assertEqual((self.destination / "assets/original").read_text(), "retained")
        self.assertFalse((self.destination / "assets/other").exists())

    def test_unsafe_source_entries_refused_before_destination_creation(self):
        outside = self.root / "outside"
        outside.write_text("preserve")
        for kind in ("symlink", "hardlink", "fifo"):
            with self.subTest(kind=kind):
                entry = self.source / kind
                if kind == "symlink":
                    entry.symlink_to(outside)
                elif kind == "hardlink":
                    os.link(outside, entry)
                else:
                    os.mkfifo(entry)
                with self.assertRaises((OSError, ValueError)):
                    self.api.stage_resource_tree(self.source_fd, self.destination_fd, "assets")
                self.assertFalse((self.destination / "assets").exists())
                entry.unlink()
        self.assertEqual(outside.read_text(), "preserve")

    def test_existing_destination_is_never_replaced(self):
        target = self.destination / "assets"
        target.mkdir()
        (target / "foreign").write_text("preserve")
        inode = target.stat().st_ino
        with self.assertRaises(FileExistsError):
            self.api.stage_resource_tree(self.source_fd, self.destination_fd, "assets")
        self.assertEqual(target.stat().st_ino, inode)
        self.assertEqual((target / "foreign").read_text(), "preserve")

    def test_verification_detects_changed_missing_and_extra_files(self):
        (self.source / "file").write_text("original")
        records = self.api.stage_resource_tree(self.source_fd, self.destination_fd, "assets")
        target = self.destination / "assets"
        fd = self.open_dir(target)
        (target / "file").write_text("tampered")
        with self.assertRaises(ValueError):
            self.api.verify_resource_tree(fd, records)
        (target / "file").unlink()
        with self.assertRaises(ValueError):
            self.api.verify_resource_tree(fd, records)
        (target / "file").write_text("original")
        (target / "file").chmod(0o600)
        (target / "extra").write_text("unexpected")
        with self.assertRaises(ValueError):
            self.api.verify_resource_tree(fd, records)

    def test_real_chrome_extension_copy_matches_every_source_file(self):
        source = Path(__file__).resolve().parents[1] / "chrome-extension"
        records = self.api.stage_resource_tree(self.open_dir(source), self.destination_fd, "chrome-extension")
        files = [r for r in records if r["kind"] == "file"]
        expected = sorted(str(p.relative_to(source)) for p in source.rglob("*") if p.is_file())
        self.assertEqual([r["path"] for r in files], expected)
        for record in files:
            self.assertEqual((self.destination / "chrome-extension" / record["path"]).read_bytes(),
                             (source / record["path"]).read_bytes())
        self.api.verify_resource_tree(self.open_dir(self.destination / "chrome-extension"), records)

    def test_partial_writes_are_completed_and_fsync_failure_cannot_return_a_manifest(self):
        (self.source / "file").write_bytes(b"payload" * 100)
        real_write = os.write
        with patch("install_resource_tree.os.write", side_effect=lambda fd, data: real_write(fd, data[:3])):
            records = self.api.stage_resource_tree(self.source_fd, self.destination_fd, "short")
        self.assertEqual((self.destination / "short/file").read_bytes(), b"payload" * 100)
        self.api.verify_resource_tree(self.open_dir(self.destination / "short"), records)
        with patch("install_resource_tree.os.fsync", side_effect=OSError("injected flush failure")):
            with self.assertRaises(OSError):
                self.api.stage_resource_tree(self.source_fd, self.destination_fd, "failed")
        self.assertEqual((self.source / "file").read_bytes(), b"payload" * 100)
        # Partial staging remains visible for caller reconciliation, not hidden cleanup.
        self.assertTrue((self.destination / "failed").is_dir())

    def test_verifier_rejects_permissions_or_symlink_substitution(self):
        (self.source / "file").write_text("original")
        records = self.api.stage_resource_tree(self.source_fd, self.destination_fd, "assets")
        target = self.destination / "assets"
        fd = self.open_dir(target)
        (target / "file").chmod(0o644)
        with self.assertRaises(ValueError):
            self.api.verify_resource_tree(fd, records)
        (target / "file").unlink()
        (target / "file").symlink_to(self.source / "file")
        with self.assertRaises((ValueError, OSError)):
            self.api.verify_resource_tree(fd, records)

    def test_source_mutation_during_copy_refuses_success(self):
        source = self.source / "file"
        source.write_bytes(b"original")
        real_write = os.write
        changed = False

        def write_and_mutate(fd, data):
            nonlocal changed
            written = real_write(fd, data)
            if not changed:
                changed = True
                source.write_bytes(b"modified")
            return written

        with patch("install_resource_tree.os.write", side_effect=write_and_mutate):
            with self.assertRaises(ValueError):
                self.api.stage_resource_tree(self.source_fd, self.destination_fd, "assets")
        self.assertEqual(source.read_bytes(), b"modified")
        self.assertTrue((self.destination / "assets").is_dir())

    def application_fixture(self):
        for relative in ("frontend/out", "frontend/fallback", "chrome-extension", "scripts"):
            directory = self.source / relative
            directory.mkdir(parents=True)
            (directory / "file").write_text(relative)

    def test_application_resources_assembled_and_verified_as_one_required_set(self):
        self.assertTrue(callable(getattr(self.api, "stage_application_resources", None)))
        self.application_fixture()
        records = self.api.stage_application_resources(self.source_fd, self.destination_fd)
        self.assertEqual(list(records), ["frontend/out", "frontend/fallback", "chrome-extension", "scripts"])
        for relative in records:
            self.assertEqual((self.destination / relative / "file").read_text(), relative)
        self.api.verify_application_resources(self.destination_fd, records)
        (self.destination / "scripts/file").write_text("changed")
        with self.assertRaises(ValueError):
            self.api.verify_application_resources(self.destination_fd, records)

    def test_missing_required_resource_does_not_start_assembly(self):
        self.assertTrue(callable(getattr(self.api, "stage_application_resources", None)))
        (self.source / "frontend/out").mkdir(parents=True)
        with self.assertRaises(FileNotFoundError):
            self.api.stage_application_resources(self.source_fd, self.destination_fd)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_application_assembly_does_not_overwrite_existing_resources(self):
        self.assertTrue(callable(getattr(self.api, "stage_application_resources", None)))
        self.application_fixture()
        (self.destination / "scripts").mkdir()
        (self.destination / "scripts/foreign").write_text("preserve")
        with self.assertRaises(FileExistsError):
            self.api.stage_application_resources(self.source_fd, self.destination_fd)
        self.assertEqual([p.name for p in self.destination.iterdir()], ["scripts"])
        self.assertEqual((self.destination / "scripts/foreign").read_text(), "preserve")

    def test_application_rechecks_earlier_sources_before_returning_complete_manifest(self):
        self.application_fixture()
        real_write = os.write

        def write_then_change_earlier_source(fd, data):
            result = real_write(fd, data)
            if bytes(data) == b"scripts":
                (self.source / "frontend/out/file").write_text("new build")
            return result

        with patch("install_resource_tree.os.write", side_effect=write_then_change_earlier_source):
            with self.assertRaises(ValueError):
                self.api.stage_application_resources(self.source_fd, self.destination_fd)
        self.assertEqual((self.source / "frontend/out/file").read_text(), "new build")


if __name__ == "__main__":
    unittest.main()
