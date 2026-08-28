from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build-storage-manifest.py"


class StorageManifestTests(unittest.TestCase):
    @staticmethod
    def _with_device(details: os.stat_result, device: int) -> os.stat_result:
        values = list(details)
        values[2] = device
        return os.stat_result(values)

    def load_manifest_module(self):
        spec = importlib.util.spec_from_file_location("build_storage_manifest", SCRIPT)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def run_manifest(
        self,
        storage_root: Path,
        output: Path,
        *,
        preserve_lexical_root: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        if not preserve_lexical_root:
            storage_root = storage_root.resolve()
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(storage_root),
                "--output",
                str(output),
                "--version",
                "0.5.4",
            ],
            text=True,
            capture_output=True,
            check=False,
            preexec_fn=lambda: os.umask(0o022),
        )

    def test_manifest_is_deterministic_relative_and_excludes_rebuildable_or_private_trees(self) -> None:
        """Removing an exclusion or emitting absolute paths must break this contract."""
        with tempfile.TemporaryDirectory() as temporary:
            storage_root = Path(temporary) / "CORTEX_BRIDGE"
            output = storage_root / "00_INDEX" / "MANIFEST.jsonl"
            files = {
                "10_SOURCE/cortex-bridge/app.py": b"print('cortex')\n",
                "30_EVIDENCE/releases/report.md": b"synthetic release proof\n",
                "90_ARCHIVES/v0.2.0/source.zip": b"archive-bytes",
                "10_SOURCE/cortex-bridge/node_modules/pkg/index.js": b"cache",
                "10_SOURCE/cortex-bridge/.venv/bin/python": b"cache",
                "10_SOURCE/cortex-bridge/__pycache__/app.pyc": b"cache",
                "10_SOURCE/cortex-bridge/.git/config": b"cache",
                "50_CACHE_REBUILDABLE/browser/chrome": b"cache",
                "99_QUARANTINE/private/raw.txt": b"must-not-be-indexed",
            }
            for relative, content in files.items():
                path = storage_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)

            first = self.run_manifest(storage_root, output)
            self.assertEqual(first.returncode, 0, first.stderr)
            first_payload = output.read_text(encoding="utf-8")

            second = self.run_manifest(storage_root, output)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), first_payload)

            records = [json.loads(line) for line in first_payload.splitlines()]
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                [record["path"] for record in records],
                [
                    "10_SOURCE/cortex-bridge/app.py",
                    "30_EVIDENCE/releases/report.md",
                    "90_ARCHIVES/v0.2.0/source.zip",
                ],
            )
            self.assertTrue(all(not Path(record["path"]).is_absolute() for record in records))
            self.assertTrue(all(set(record) == {
                "canonical",
                "id",
                "path",
                "retention",
                "sensitivity",
                "sha256",
                "size",
                "status",
                "type",
                "version",
            } for record in records))
            self.assertEqual([record["status"] for record in records], ["active", "evidence", "archived"])
            self.assertEqual([record["canonical"] for record in records], [True, False, False])
            self.assertEqual([record["version"] for record in records], ["0.5.4"] * 3)
            self.assertTrue(all(len(record["id"]) == 16 for record in records))
            self.assertTrue(all(len(record["sha256"]) == 64 for record in records))

    def test_manifest_refuses_a_symlink_that_escapes_the_storage_root(self) -> None:
        """Following an external symlink could hash or expose unrelated private files."""
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            storage_root = base / "CORTEX_BRIDGE"
            output = storage_root / "00_INDEX" / "MANIFEST.jsonl"
            outside = base / "private.txt"
            outside.write_text("private", encoding="utf-8")
            link = storage_root / "10_SOURCE" / "outside"
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(outside)

            result = self.run_manifest(storage_root, output)

            self.assertEqual(result.returncode, 2)
            self.assertIn("symlink escapes storage root", result.stderr)
            self.assertFalse(output.exists())

    def test_manifest_refuses_a_symlinked_root_before_inventorying_private_files(self) -> None:
        """Resolving --root first would expose the linked private tree in the manifest."""
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            private_root = base / "private"
            secret = private_root / "10_SOURCE" / "secret.txt"
            secret.parent.mkdir(parents=True)
            secret.write_text("must-not-be-inventoried", encoding="utf-8")
            linked_root = base / "CORTEX_BRIDGE"
            linked_root.symlink_to(private_root, target_is_directory=True)
            output = linked_root / "00_INDEX" / "MANIFEST.jsonl"

            result = self.run_manifest(linked_root, output, preserve_lexical_root=True)

            self.assertEqual(result.returncode, 2)
            self.assertIn("symlink", result.stderr)
            self.assertFalse((private_root / "00_INDEX" / "MANIFEST.jsonl").exists())

    def test_manifest_refuses_a_root_with_a_symlinked_parent_component(self) -> None:
        """Checking only the leaf would still let a parent link expose private files."""
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            private_parent = base / "private-parent"
            private_root = private_parent / "CORTEX_BRIDGE"
            secret = private_root / "10_SOURCE" / "secret.txt"
            secret.parent.mkdir(parents=True)
            secret.write_text("must-not-be-inventoried", encoding="utf-8")
            linked_parent = base / "storage-parent"
            linked_parent.symlink_to(private_parent, target_is_directory=True)
            linked_root = linked_parent / "CORTEX_BRIDGE"
            output = linked_root / "00_INDEX" / "MANIFEST.jsonl"

            result = self.run_manifest(linked_root, output, preserve_lexical_root=True)

            self.assertEqual(result.returncode, 2)
            self.assertIn("symlink", result.stderr)
            self.assertFalse((private_root / "00_INDEX" / "MANIFEST.jsonl").exists())

    def test_predictable_temporary_symlink_cannot_overwrite_another_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            storage_root = base / "CORTEX_BRIDGE"
            source = storage_root / "10_SOURCE" / "app.py"
            source.parent.mkdir(parents=True)
            source.write_text("source", encoding="utf-8")
            output = storage_root / "00_INDEX" / "MANIFEST.jsonl"
            output.parent.mkdir(parents=True)
            victim = base / "victim.txt"
            victim.write_text("must-stay", encoding="utf-8")
            output.with_suffix(output.suffix + ".tmp").symlink_to(victim)

            result = self.run_manifest(storage_root, output)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(victim.read_text(encoding="utf-8"), "must-stay")
            self.assertTrue(output.is_file())
            self.assertFalse(output.is_symlink())

    def test_output_symlink_and_output_outside_index_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            storage_root = base / "CORTEX_BRIDGE"
            source = storage_root / "10_SOURCE" / "app.py"
            source.parent.mkdir(parents=True)
            source.write_text("must-stay-source", encoding="utf-8")
            index = storage_root / "00_INDEX"
            index.mkdir(parents=True)
            victim = base / "victim.txt"
            victim.write_text("must-stay-victim", encoding="utf-8")
            output_link = index / "MANIFEST.jsonl"
            output_link.symlink_to(victim)

            linked = self.run_manifest(storage_root, output_link)
            outside = self.run_manifest(storage_root, source)

            self.assertEqual(linked.returncode, 2)
            self.assertIn("manifest output is unsafe", linked.stderr)
            self.assertEqual(outside.returncode, 2)
            self.assertIn("manifest output must be inside 00_INDEX", outside.stderr)
            self.assertEqual(victim.read_text(encoding="utf-8"), "must-stay-victim")
            self.assertEqual(source.read_text(encoding="utf-8"), "must-stay-source")

    def test_file_replaced_after_hash_is_rejected(self) -> None:
        module = self.load_manifest_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.txt"
            source.write_bytes(b"original")
            replacement = root / "replacement.txt"
            replacement.write_bytes(b"replacement")
            real_fstat = os.fstat
            calls = 0

            def swap_after_hash(fd):
                nonlocal calls
                result = real_fstat(fd)
                calls += 1
                if calls == 2:
                    os.replace(replacement, source)
                return result

            with patch.object(module.os, "fstat", side_effect=swap_after_hash):
                with self.assertRaisesRegex(ValueError, "changed while hashing"):
                    module.sha256_file(source)

    def test_nested_mount_is_rejected_before_its_contents_are_visited(self) -> None:
        """Removing the device boundary would expose files from a nested mount."""
        module = self.load_manifest_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "CORTEX_BRIDGE"
            nested_mount = root / "10_SOURCE" / "mounted-project"
            secret = nested_mount / "secret.txt"
            secret.parent.mkdir(parents=True)
            secret.write_text("must-not-be-hashed", encoding="utf-8")
            root_device = root.stat().st_dev
            real_stat = module.os.stat
            secret_stat_calls = 0

            def cross_device_stat(path, *args, **kwargs):
                nonlocal secret_stat_calls
                details = real_stat(path, *args, **kwargs)
                candidate = os.fspath(path)
                if candidate == secret.name and kwargs.get("dir_fd") is not None:
                    secret_stat_calls += 1
                if candidate == nested_mount.name and kwargs.get("dir_fd") is not None:
                    return self._with_device(details, root_device + 1)
                return details

            with patch.object(module.os, "stat", side_effect=cross_device_stat):
                with self.assertRaisesRegex(ValueError, "different filesystem"):
                    list(module.iter_manifest_files(root))

            self.assertEqual(secret_stat_calls, 0)

    def test_index_on_another_device_is_rejected_before_manifest_output(self) -> None:
        module = self.load_manifest_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "CORTEX_BRIDGE"
            source = root / "10_SOURCE" / "app.py"
            source.parent.mkdir(parents=True)
            source.write_text("print('safe')\n", encoding="utf-8")
            index = root / "00_INDEX"
            index.mkdir()
            index.chmod(0o755)
            original_index_mode = index.stat().st_mode & 0o777
            output = index / "MANIFEST.jsonl"
            root_device = root.stat().st_dev
            real_open = module.os.open
            real_fstat = module.os.fstat
            index_descriptors: set[int] = set()

            def track_index_open(path, flags, mode=0o777, *, dir_fd=None):
                if dir_fd is None:
                    descriptor = real_open(path, flags, mode)
                else:
                    descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
                if os.fspath(path) == "00_INDEX":
                    index_descriptors.add(descriptor)
                return descriptor

            def cross_device_fstat(descriptor):
                details = real_fstat(descriptor)
                if descriptor in index_descriptors:
                    return self._with_device(details, root_device + 1)
                return details

            stderr = io.StringIO()
            argv = [
                str(SCRIPT),
                "--root",
                str(root),
                "--output",
                str(output),
                "--version",
                "0.5.4",
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(module.os, "open", side_effect=track_index_open),
                patch.object(module.os, "fstat", side_effect=cross_device_fstat),
                contextlib.redirect_stderr(stderr),
            ):
                status = module.main()

            self.assertEqual(status, 2)
            self.assertIn("00_INDEX", stderr.getvalue())
            self.assertFalse(output.exists())
            self.assertEqual(index.stat().st_mode & 0o777, original_index_mode)

    def test_index_replaced_after_validation_never_redirects_manifest_output(self) -> None:
        module = self.load_manifest_module()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / "CORTEX_BRIDGE"
            source = root / "10_SOURCE" / "app.py"
            source.parent.mkdir(parents=True)
            source.write_text("print('safe')\n", encoding="utf-8")
            index = root / "00_INDEX"
            index.mkdir()
            original_index = root / "00_INDEX.original"
            outside = base / "outside"
            outside.mkdir()
            output = index / "MANIFEST.jsonl"

            def swap_index(_root, _version, **_kwargs):
                index.rename(original_index)
                index.symlink_to(outside, target_is_directory=True)
                return []

            stderr = io.StringIO()
            argv = [
                str(SCRIPT),
                "--root",
                str(root),
                "--output",
                str(output),
                "--version",
                "0.5.4",
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(module, "build_manifest", side_effect=swap_index),
                contextlib.redirect_stderr(stderr),
            ):
                try:
                    status = module.main()
                except OSError:
                    status = -1

            self.assertEqual(status, 2)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertFalse((original_index / "MANIFEST.jsonl").exists())

    def test_build_manifest_keeps_the_validated_root_inode(self) -> None:
        module = self.load_manifest_module()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "CORTEX_BRIDGE"
            original_source = root / "10_SOURCE" / "original.txt"
            original_source.parent.mkdir(parents=True)
            original_source.write_text("original", encoding="utf-8")
            replacement_root = base / "replacement"
            replacement_source = replacement_root / "10_SOURCE" / "foreign.txt"
            replacement_source.parent.mkdir(parents=True)
            replacement_source.write_text("foreign", encoding="utf-8")
            moved_root = base / "CORTEX_BRIDGE.original"
            root_fd = os.open(root, module.DIRECTORY_FLAGS)
            root_details = os.fstat(root_fd)
            root.rename(moved_root)
            replacement_root.rename(root)

            try:
                records = module.build_manifest(
                    root,
                    "0.5.4",
                    root_fd=root_fd,
                    expected_root_device=root_details.st_dev,
                    expected_root_inode=root_details.st_ino,
                )
            finally:
                os.close(root_fd)

            self.assertEqual(
                [record["path"] for record in records],
                ["10_SOURCE/original.txt"],
            )

    def test_root_replacement_before_open_is_rejected_without_inventorying_replacement(self) -> None:
        """Opening a root substituted after lexical validation must fail closed."""
        module = self.load_manifest_module()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / "CORTEX_BRIDGE"
            source = root / "10_SOURCE" / "safe.txt"
            source.parent.mkdir(parents=True)
            source.write_text("safe", encoding="utf-8")
            replacement = base / "private-replacement"
            secret = replacement / "10_SOURCE" / "secret.txt"
            secret.parent.mkdir(parents=True)
            secret.write_text("must-not-be-inventoried", encoding="utf-8")
            original_root = base / "CORTEX_BRIDGE.original"
            output = root / "00_INDEX" / "MANIFEST.jsonl"
            real_open = module.os.open
            replaced = False

            def replace_root_before_open(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal replaced
                if os.fspath(path) == os.fspath(root) and dir_fd is None and not replaced:
                    replaced = True
                    root.rename(original_root)
                    replacement.rename(root)
                if dir_fd is None:
                    return real_open(path, flags, mode)
                return real_open(path, flags, mode, dir_fd=dir_fd)

            stderr = io.StringIO()
            argv = [
                str(SCRIPT),
                "--root",
                str(root),
                "--output",
                str(output),
                "--version",
                "0.5.4",
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(module.os, "open", side_effect=replace_root_before_open),
                contextlib.redirect_stderr(stderr),
            ):
                status = module.main()

            self.assertEqual(status, 2)
            self.assertTrue(replaced, stderr.getvalue())
            self.assertIn("storage root changed", stderr.getvalue())
            self.assertFalse((root / "00_INDEX" / "MANIFEST.jsonl").exists())
            self.assertFalse((original_root / "00_INDEX" / "MANIFEST.jsonl").exists())

    def test_directory_substitution_after_stat_is_not_traversed(self) -> None:
        module = self.load_manifest_module()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "CORTEX_BRIDGE"
            project = root / "10_SOURCE" / "project"
            project.mkdir(parents=True)
            original_project = project.with_name("project.original")
            outside = base / "outside"
            outside.mkdir()
            (outside / "secret.txt").write_text("outside", encoding="utf-8")
            real_open = module.os.open
            swapped = False

            def swap_before_open(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal swapped
                if os.fspath(path) == project.name and dir_fd is not None and not swapped:
                    swapped = True
                    project.rename(original_project)
                    project.symlink_to(outside, target_is_directory=True)
                if dir_fd is None:
                    return real_open(path, flags, mode)
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with patch.object(module.os, "open", side_effect=swap_before_open):
                try:
                    records = module.build_manifest(root, "0.5.4")
                except (OSError, ValueError):
                    records = None

            self.assertTrue(swapped)
            self.assertNotEqual(
                [record["path"] for record in records or []],
                ["10_SOURCE/project/secret.txt"],
            )


if __name__ == "__main__":
    unittest.main()
