from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "console"))


class CortexHomeTest(unittest.TestCase):
    @staticmethod
    def _with_device(details: os.stat_result, device: int) -> os.stat_result:
        values = list(details)
        values[2] = device
        return os.stat_result(values)

    def test_default_home_and_every_runtime_path_are_outside_repository(self):
        from cortex_paths import build_paths

        with tempfile.TemporaryDirectory() as home:
            with patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.home", return_value=Path(home)):
                paths = build_paths()
        expected = Path(home) / ".local" / "share" / "cortex-bridge"
        expected = expected.resolve(strict=False)
        self.assertEqual(paths.home, expected)
        for path in paths.mutable_paths():
            self.assertTrue(path == expected or expected in path.parents, path)
            self.assertNotIn(ROOT, [path, *path.parents])

    def test_explicit_cortex_home_must_be_absolute(self):
        from cortex_paths import build_paths

        with patch.dict(os.environ, {"CORTEX_HOME": "relative/state"}, clear=True):
            with self.assertRaises(ValueError):
                build_paths()

    def test_cortex_home_rejects_broad_user_system_and_volume_roots(self):
        from cortex_paths import build_paths

        fake_home = Path(tempfile.gettempdir()) / "cortex-test-user-home"
        rejected = (
            Path("/"),
            fake_home,
            fake_home / "Desktop",
            fake_home / "Documents",
            fake_home / "Downloads",
            fake_home / "Library",
            fake_home / ".config",
            fake_home / ".local",
            Path("/Applications"),
            Path("/Library"),
            Path("/System"),
            Path("/Users"),
            Path("/Volumes"),
            Path("/") / "Volumes" / "External",
            Path("/") / "Volumes" / "External" / "CORTEX_BRIDGE" / "runtime",
            Path("/private"),
            Path("/private/tmp"),
            Path("/usr"),
            Path("/var"),
        )
        for unsafe in rejected:
            with self.subTest(unsafe=unsafe), patch.dict(
                os.environ,
                {"CORTEX_HOME": str(unsafe)},
                clear=True,
            ), patch("pathlib.Path.home", return_value=fake_home):
                with self.assertRaisesRegex(ValueError, "dedicated directory"):
                    build_paths()

    def test_cortex_home_accepts_dedicated_nested_absolute_overrides(self):
        from cortex_paths import build_paths

        fake_home = Path(tempfile.gettempdir()) / "cortex-test-user-home"
        with tempfile.TemporaryDirectory() as temporary:
            allowed = (
                fake_home / ".local" / "share" / "cortex-bridge",
                fake_home / "Library" / "Application Support" / "Cortex Bridge",
                fake_home / "Documents" / "projects" / "cortex-runtime",
                Path(temporary) / "cortex-runtime",
            )
            for dedicated in allowed:
                with self.subTest(dedicated=dedicated), patch.dict(
                    os.environ,
                    {"CORTEX_HOME": str(dedicated)},
                    clear=True,
                ), patch("pathlib.Path.home", return_value=fake_home):
                    self.assertEqual(
                        build_paths().home,
                        dedicated.resolve(strict=False),
                    )

    def test_cortex_home_rejects_a_mounted_ancestor_outside_standard_mount_path(self):
        from cortex_paths import build_paths

        with tempfile.TemporaryDirectory() as temporary:
            fake_home = Path(temporary) / "user-home"
            mounted_parent = fake_home / "Mounts" / "Vault"
            dedicated = mounted_parent / "runtime"
            fake_home.mkdir()
            mounted_parent.mkdir(parents=True)

            def is_mount(candidate):
                return Path(candidate).resolve(strict=False) == mounted_parent.resolve()

            with patch.dict(
                os.environ,
                {"CORTEX_HOME": str(dedicated)},
                clear=True,
            ), patch("pathlib.Path.home", return_value=fake_home), patch(
                "os.path.ismount",
                side_effect=is_mount,
            ):
                with self.assertRaisesRegex(ValueError, "dedicated directory"):
                    build_paths()

    def test_cortex_home_rejects_a_different_filesystem_from_user_home(self):
        from cortex_paths import build_paths

        with tempfile.TemporaryDirectory() as temporary:
            fake_home = Path(temporary) / "user-home"
            dedicated = Path(temporary) / "mounted-elsewhere" / "runtime"
            fake_home.mkdir()
            dedicated.mkdir(parents=True)
            resolved_dedicated = dedicated.resolve()
            original_stat = Path.stat

            def different_device(path, *args, **kwargs):
                result = original_stat(path, *args, **kwargs)
                if path != resolved_dedicated:
                    return result
                values = list(result)
                values[2] = result.st_dev + 1
                return os.stat_result(values)

            with patch.dict(
                os.environ,
                {"CORTEX_HOME": str(resolved_dedicated)},
                clear=True,
            ), patch("pathlib.Path.home", return_value=fake_home), patch(
                "pathlib.Path.stat",
                side_effect=different_device,
                autospec=True,
            ):
                with self.assertRaisesRegex(ValueError, "dedicated directory"):
                    build_paths()

    @unittest.skipUnless(sys.platform == "darwin", "APFS path identity is macOS-specific")
    def test_cortex_home_rejects_case_aliases_of_broad_directories(self):
        from cortex_paths import build_paths

        real_home = Path.home()
        aliases = [Path("/users")]
        for name in ("Desktop", "Documents", "Downloads", "Library", ".config", ".local"):
            canonical = real_home / name
            if canonical.exists():
                aliases.append(real_home / name.swapcase())

        for alias in aliases:
            with self.subTest(alias=alias), patch.dict(
                os.environ,
                {"CORTEX_HOME": str(alias)},
                clear=True,
            ):
                with self.assertRaisesRegex(ValueError, "dedicated directory"):
                    build_paths()

    def test_migration_never_deletes_or_overwrites_legacy_state(self):
        from cortex_paths import build_paths, migrate_legacy_state

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            legacy = base / "legacy"
            legacy.mkdir()
            (legacy / "settings.json").write_text("legacy", encoding="utf-8")
            (legacy / "chat-runs.json").write_text("runs", encoding="utf-8")
            (legacy / "ignored-link").symlink_to(legacy / "settings.json")
            with patch.dict(os.environ, {"CORTEX_HOME": str(base / "new")}, clear=True):
                paths = build_paths()
            paths.home.mkdir(parents=True)
            paths.settings.write_text("existing", encoding="utf-8")
            migrated = migrate_legacy_state(legacy, paths)
            self.assertEqual(paths.settings.read_text(encoding="utf-8"), "existing")
            self.assertEqual(paths.chat_runs.read_text(encoding="utf-8"), "runs")
            self.assertEqual((legacy / "settings.json").read_text(encoding="utf-8"), "legacy")
            self.assertFalse((paths.home / "ignored-link").exists())
            self.assertEqual(migrated, [paths.chat_runs])

    def test_layout_restricts_existing_private_directories_and_files(self):
        from cortex_paths import build_paths, ensure_layout

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            cortex_home = base / "cortex"
            cortex_home.mkdir(mode=0o755)
            settings = cortex_home / "settings.json"
            settings.write_text("{}", encoding="utf-8")
            settings.chmod(0o644)
            logs = cortex_home / "logs"
            logs.mkdir(mode=0o755)
            log = logs / "console.log"
            log.write_text("private", encoding="utf-8")
            log.chmod(0o644)
            with patch.dict(os.environ, {"CORTEX_HOME": str(cortex_home)}, clear=True):
                paths = build_paths()

            ensure_layout(paths)

            self.assertEqual(paths.home.stat().st_mode & 0o777, 0o700)
            self.assertEqual(paths.logs.stat().st_mode & 0o777, 0o700)
            self.assertEqual(paths.settings.stat().st_mode & 0o777, 0o600)
            self.assertEqual(log.stat().st_mode & 0o777, 0o600)

    def test_layout_refuses_nested_mount_without_chmod_or_traversal(self):
        import cortex_paths

        with tempfile.TemporaryDirectory() as root:
            private_tree = Path(root) / "logs"
            nested_mount = private_tree / "mounted"
            foreign_file = nested_mount / "foreign.log"
            foreign_file.parent.mkdir(parents=True, mode=0o755)
            foreign_file.write_text("foreign", encoding="utf-8")
            foreign_file.chmod(0o644)
            original_mount_mode = nested_mount.stat().st_mode & 0o777
            real_stat = Path.stat
            foreign_file_stat_calls = 0

            def cross_device_stat(path, *args, **kwargs):
                nonlocal foreign_file_stat_calls
                details = real_stat(path, *args, **kwargs)
                candidate = Path(path)
                if candidate == foreign_file:
                    foreign_file_stat_calls += 1
                if candidate == nested_mount:
                    return self._with_device(details, private_tree.stat().st_dev + 1)
                return details

            with patch("pathlib.Path.stat", autospec=True, side_effect=cross_device_stat):
                with self.assertRaisesRegex(RuntimeError, "different filesystem"):
                    cortex_paths._restrict_private_tree(private_tree)

            self.assertEqual(foreign_file_stat_calls, 0)
            self.assertEqual(nested_mount.stat().st_mode & 0o777, original_mount_mode)
            self.assertEqual(foreign_file.stat().st_mode & 0o777, 0o644)

    def test_layout_refuses_a_managed_subtree_on_another_device_before_chmod(self):
        import cortex_paths

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            cortex_home = base / "cortex"
            logs = cortex_home / "logs"
            foreign_file = logs / "foreign.log"
            foreign_file.parent.mkdir(parents=True, mode=0o755)
            foreign_file.write_text("foreign", encoding="utf-8")
            logs.chmod(0o755)
            foreign_file.chmod(0o644)
            with patch.dict(os.environ, {"CORTEX_HOME": str(cortex_home)}, clear=True):
                paths = cortex_paths.build_paths()
            real_stat = Path.stat
            home_device = cortex_home.stat().st_dev
            logs_aliases = (logs, logs.resolve(strict=True))

            def mounted_logs_stat(path, *args, **kwargs):
                details = real_stat(path, *args, **kwargs)
                candidate = Path(path)
                if any(
                    candidate == alias or alias in candidate.parents
                    for alias in logs_aliases
                ):
                    return self._with_device(details, home_device + 1)
                return details

            with patch("pathlib.Path.stat", autospec=True, side_effect=mounted_logs_stat):
                with self.assertRaisesRegex(RuntimeError, "different filesystem"):
                    cortex_paths.ensure_layout(paths)

            self.assertEqual(logs.stat().st_mode & 0o777, 0o755)
            self.assertEqual(foreign_file.stat().st_mode & 0o777, 0o644)

    def test_private_tree_replacement_after_stat_is_not_chmodded(self):
        import cortex_paths

        with tempfile.TemporaryDirectory() as root:
            private_tree = Path(root) / "logs"
            private_tree.mkdir()
            target = private_tree / "console.log"
            target.write_text("original", encoding="utf-8")
            target.chmod(0o644)
            original = target.with_name("console.log.original")
            replacement = Path(root) / "replacement.log"
            replacement.write_text("replacement", encoding="utf-8")
            replacement.chmod(0o644)
            real_stat = Path.stat
            swapped = False

            def swap_after_stat(path, *args, **kwargs):
                nonlocal swapped
                details = real_stat(path, *args, **kwargs)
                if Path(path) == target and not swapped:
                    swapped = True
                    target.rename(original)
                    replacement.rename(target)
                return details

            with patch("pathlib.Path.stat", autospec=True, side_effect=swap_after_stat):
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    cortex_paths._restrict_private_tree(private_tree)

            self.assertEqual(target.stat().st_mode & 0o777, 0o644)

    def test_private_file_replacement_before_open_is_not_chmodded(self):
        import cortex_paths

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            cortex_home = base / "cortex"
            cortex_home.mkdir()
            settings = cortex_home / "settings.json"
            settings.write_text("original", encoding="utf-8")
            settings.chmod(0o644)
            original = cortex_home / "settings.original"
            replacement = base / "replacement.json"
            replacement.write_text("replacement", encoding="utf-8")
            replacement.chmod(0o644)
            with patch.dict(os.environ, {"CORTEX_HOME": str(cortex_home)}, clear=True):
                paths = cortex_paths.build_paths()
            real_open = cortex_paths.os.open
            injected = False

            def swap_before_open(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal injected
                if path == settings.name and dir_fd is not None and not injected:
                    injected = True
                    settings.rename(original)
                    replacement.rename(settings)
                if dir_fd is None:
                    return real_open(path, flags, mode)
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with patch.object(cortex_paths.os, "open", side_effect=swap_before_open):
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    cortex_paths.ensure_layout(paths)

            self.assertTrue(injected)
            self.assertEqual(settings.stat().st_mode & 0o777, 0o644)

    def test_private_file_on_another_device_is_refused_before_chmod(self):
        import cortex_paths

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            cortex_home = base / "cortex"
            cortex_home.mkdir()
            settings = cortex_home / "settings.json"
            settings.write_text("private", encoding="utf-8")
            settings.chmod(0o644)
            with patch.dict(os.environ, {"CORTEX_HOME": str(cortex_home)}, clear=True):
                paths = cortex_paths.build_paths()
            real_open = cortex_paths.os.open
            real_fstat = cortex_paths.os.fstat
            settings_fds: set[int] = set()

            def track_open(path, flags, mode=0o777, *, dir_fd=None):
                if dir_fd is None:
                    descriptor = real_open(path, flags, mode)
                else:
                    descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
                if path == settings.name and dir_fd is not None:
                    settings_fds.add(descriptor)
                return descriptor

            def cross_device_fstat(descriptor):
                details = real_fstat(descriptor)
                if descriptor in settings_fds:
                    return self._with_device(details, cortex_home.stat().st_dev + 1)
                return details

            with (
                patch.object(cortex_paths.os, "open", side_effect=track_open),
                patch.object(cortex_paths.os, "fstat", side_effect=cross_device_fstat),
            ):
                with self.assertRaisesRegex(RuntimeError, "different filesystem"):
                    cortex_paths.ensure_layout(paths)

            self.assertTrue(settings_fds)
            self.assertEqual(settings.stat().st_mode & 0o777, 0o644)

    def test_legacy_migration_privatises_destination_without_changing_source_modes(self):
        from cortex_paths import build_paths, migrate_legacy_state

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            legacy = base / "legacy"
            attachment_dir = legacy / "attachments"
            attachment_dir.mkdir(parents=True, mode=0o755)
            legacy_settings = legacy / "settings.json"
            legacy_settings.write_text("legacy", encoding="utf-8")
            legacy_settings.chmod(0o644)
            legacy_attachment = attachment_dir / "capture.txt"
            legacy_attachment.write_text("private", encoding="utf-8")
            legacy_attachment.chmod(0o644)
            with patch.dict(os.environ, {"CORTEX_HOME": str(base / "new")}, clear=True):
                paths = build_paths()

            migrate_legacy_state(legacy, paths)

            self.assertEqual(legacy.stat().st_mode & 0o777, 0o755)
            self.assertEqual(legacy_settings.stat().st_mode & 0o777, 0o644)
            self.assertEqual(attachment_dir.stat().st_mode & 0o777, 0o755)
            self.assertEqual(legacy_attachment.stat().st_mode & 0o777, 0o644)
            self.assertEqual(paths.home.stat().st_mode & 0o777, 0o700)
            self.assertEqual(paths.settings.stat().st_mode & 0o777, 0o600)
            self.assertEqual(paths.attachments.stat().st_mode & 0o777, 0o700)
            self.assertEqual(
                (paths.attachments / "capture.txt").stat().st_mode & 0o777,
                0o600,
            )

    def test_interrupted_legacy_copy_never_publishes_a_partial_destination(self):
        import cortex_paths

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            legacy = base / "legacy"
            legacy.mkdir()
            source = legacy / "settings.json"
            source.write_text("complete legacy settings", encoding="utf-8")
            with patch.dict(os.environ, {"CORTEX_HOME": str(base / "new")}, clear=True):
                paths = cortex_paths.build_paths()

            def interrupted_copy(_source, destination, **_kwargs):
                destination.write(b"partial")
                raise OSError("simulated disk interruption")

            with patch.object(cortex_paths.shutil, "copyfileobj", side_effect=interrupted_copy):
                with self.assertRaisesRegex(OSError, "simulated disk interruption"):
                    cortex_paths.migrate_legacy_state(legacy, paths)

            self.assertFalse(paths.settings.exists())
            self.assertEqual(source.read_text(encoding="utf-8"), "complete legacy settings")
            migrated = cortex_paths.migrate_legacy_state(legacy, paths)
            self.assertEqual(migrated, [paths.settings])
            self.assertEqual(
                paths.settings.read_text(encoding="utf-8"),
                "complete legacy settings",
            )

    def test_interrupted_legacy_directory_copy_retries_the_complete_tree(self):
        import cortex_paths

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            legacy_attachments = base / "legacy" / "attachments"
            legacy_attachments.mkdir(parents=True)
            (legacy_attachments / "a.txt").write_text("alpha", encoding="utf-8")
            (legacy_attachments / "b.txt").write_text("bravo", encoding="utf-8")
            with patch.dict(os.environ, {"CORTEX_HOME": str(base / "new")}, clear=True):
                paths = cortex_paths.build_paths()
            real_copy = cortex_paths.shutil.copyfileobj
            copy_count = 0

            def interrupt_second_file(source, destination, **kwargs):
                nonlocal copy_count
                copy_count += 1
                if copy_count == 2:
                    destination.write(b"partial")
                    raise OSError("simulated tree interruption")
                return real_copy(source, destination, **kwargs)

            with patch.object(
                cortex_paths.shutil,
                "copyfileobj",
                side_effect=interrupt_second_file,
            ):
                with self.assertRaisesRegex(OSError, "simulated tree interruption"):
                    cortex_paths.migrate_legacy_state(base / "legacy", paths)

            self.assertFalse(paths.attachments.exists())
            migrated = cortex_paths.migrate_legacy_state(base / "legacy", paths)
            self.assertEqual(migrated, [paths.attachments])
            self.assertEqual(
                {
                    child.name: child.read_text(encoding="utf-8")
                    for child in paths.attachments.iterdir()
                },
                {"a.txt": "alpha", "b.txt": "bravo"},
            )

    def test_legacy_directory_migration_refuses_a_nested_mount_without_copying_it(self):
        import cortex_paths

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            legacy = base / "legacy"
            attachments = legacy / "attachments"
            nested_mount = attachments / "mounted"
            foreign_file = nested_mount / "foreign.txt"
            foreign_file.parent.mkdir(parents=True)
            foreign_file.write_text("foreign", encoding="utf-8")
            with patch.dict(os.environ, {"CORTEX_HOME": str(base / "new")}, clear=True):
                paths = cortex_paths.build_paths()
            real_stat = Path.stat
            foreign_file_stat_calls = 0

            def cross_device_stat(path, *args, **kwargs):
                nonlocal foreign_file_stat_calls
                details = real_stat(path, *args, **kwargs)
                candidate = Path(path)
                if candidate == foreign_file:
                    foreign_file_stat_calls += 1
                if candidate == nested_mount:
                    return self._with_device(details, legacy.stat().st_dev + 1)
                return details

            with patch("pathlib.Path.stat", autospec=True, side_effect=cross_device_stat):
                with self.assertRaisesRegex(RuntimeError, "different filesystem"):
                    cortex_paths.migrate_legacy_state(legacy, paths)

            self.assertEqual(foreign_file_stat_calls, 0)
            self.assertFalse(paths.attachments.exists())
            self.assertEqual(foreign_file.read_text(encoding="utf-8"), "foreign")

    def test_legacy_file_replaced_after_stat_is_not_copied(self):
        import cortex_paths

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            legacy = base / "legacy"
            legacy.mkdir()
            source = legacy / "settings.json"
            source.write_text("original", encoding="utf-8")
            original = legacy / "settings.original"
            replacement = legacy / "replacement.json"
            replacement.write_text("replacement", encoding="utf-8")
            with patch.dict(os.environ, {"CORTEX_HOME": str(base / "new")}, clear=True):
                paths = cortex_paths.build_paths()
            real_stat = Path.stat
            swapped = False

            def swap_after_stat(path, *args, **kwargs):
                nonlocal swapped
                details = real_stat(path, *args, **kwargs)
                if Path(path) == source and not swapped:
                    swapped = True
                    source.rename(original)
                    replacement.rename(source)
                return details

            with patch("pathlib.Path.stat", autospec=True, side_effect=swap_after_stat):
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    cortex_paths.migrate_legacy_state(legacy, paths)

            self.assertFalse(paths.settings.exists())

    def test_legacy_directory_replaced_after_stat_is_not_copied(self):
        import cortex_paths

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            legacy = base / "legacy"
            source = legacy / "attachments"
            source.mkdir(parents=True)
            (source / "original.txt").write_text("original", encoding="utf-8")
            original = legacy / "attachments.original"
            replacement = base / "replacement-attachments"
            replacement.mkdir()
            (replacement / "foreign.txt").write_text("foreign", encoding="utf-8")
            with patch.dict(os.environ, {"CORTEX_HOME": str(base / "new")}, clear=True):
                paths = cortex_paths.build_paths()
            real_stat = Path.stat
            swapped = False

            def swap_after_stat(path, *args, **kwargs):
                nonlocal swapped
                details = real_stat(path, *args, **kwargs)
                if Path(path) == source and not swapped:
                    swapped = True
                    source.rename(original)
                    replacement.rename(source)
                return details

            with patch("pathlib.Path.stat", autospec=True, side_effect=swap_after_stat):
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    cortex_paths.migrate_legacy_state(legacy, paths)

            self.assertFalse(paths.attachments.exists())

    def test_legacy_root_replaced_after_stat_is_not_migrated(self):
        import cortex_paths

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            legacy = base / "legacy"
            legacy.mkdir()
            (legacy / "settings.json").write_text("original", encoding="utf-8")
            original = base / "legacy.original"
            replacement = base / "legacy.replacement"
            replacement.mkdir()
            (replacement / "settings.json").write_text("replacement", encoding="utf-8")
            with patch.dict(os.environ, {"CORTEX_HOME": str(base / "new")}, clear=True):
                paths = cortex_paths.build_paths()
            real_stat = Path.stat
            swapped = False

            def swap_after_stat(path, *args, **kwargs):
                nonlocal swapped
                details = real_stat(path, *args, **kwargs)
                if Path(path) == legacy and not swapped:
                    swapped = True
                    legacy.rename(original)
                    replacement.rename(legacy)
                return details

            with patch("pathlib.Path.stat", autospec=True, side_effect=swap_after_stat):
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    cortex_paths.migrate_legacy_state(legacy, paths)

            self.assertFalse(paths.settings.exists())

    def test_legacy_file_publication_refuses_a_substituted_temporary(self):
        import cortex_paths

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            legacy = base / "legacy"
            legacy.mkdir()
            (legacy / "settings.json").write_text("original", encoding="utf-8")
            runtime = base / "runtime"
            with patch.dict(os.environ, {"CORTEX_HOME": str(runtime)}, clear=True):
                paths = cortex_paths.build_paths()
            real_link = cortex_paths.os.link
            injected = False

            def substitute_before_link(
                source,
                destination,
                *,
                src_dir_fd=None,
                dst_dir_fd=None,
                follow_symlinks=True,
            ):
                nonlocal injected
                injected = True
                cortex_paths.os.unlink(source, dir_fd=src_dir_fd)
                replacement_fd = cortex_paths.os.open(
                    source,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=src_dir_fd,
                )
                try:
                    cortex_paths.os.write(replacement_fd, b"foreign")
                finally:
                    cortex_paths.os.close(replacement_fd)
                return real_link(
                    source,
                    destination,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                    follow_symlinks=follow_symlinks,
                )

            with patch.object(cortex_paths.os, "link", side_effect=substitute_before_link):
                with self.assertRaisesRegex(RuntimeError, "destination changed"):
                    cortex_paths.migrate_legacy_state(legacy, paths)

            self.assertTrue(injected)
            self.assertFalse(paths.settings.exists())

    def test_legacy_directory_publication_refuses_a_substituted_staging_tree(self):
        import cortex_paths

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            legacy = base / "legacy"
            attachments = legacy / "attachments"
            attachments.mkdir(parents=True)
            (attachments / "capture.txt").write_text("original", encoding="utf-8")
            runtime = base / "runtime"
            with patch.dict(os.environ, {"CORTEX_HOME": str(runtime)}, clear=True):
                paths = cortex_paths.build_paths()
            real_publish = cortex_paths._rename_directory_exclusive_at
            injected = False

            def substitute_before_publish(parent_fd, staging_name, destination_name):
                nonlocal injected
                injected = True
                preserved_name = f"{staging_name}.preserved"
                cortex_paths.os.rename(
                    staging_name,
                    preserved_name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                )
                cortex_paths.os.mkdir(staging_name, 0o700, dir_fd=parent_fd)
                victim_parent = cortex_paths.os.open(
                    staging_name,
                    cortex_paths.DIRECTORY_FLAGS,
                    dir_fd=parent_fd,
                )
                try:
                    sentinel = cortex_paths.os.open(
                        "must-survive.txt",
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=victim_parent,
                    )
                    cortex_paths.os.close(sentinel)
                finally:
                    cortex_paths.os.close(victim_parent)
                return real_publish(parent_fd, staging_name, destination_name)

            with patch.object(
                cortex_paths,
                "_rename_directory_exclusive_at",
                side_effect=substitute_before_publish,
            ):
                with self.assertRaisesRegex(RuntimeError, "destination changed"):
                    cortex_paths.migrate_legacy_state(legacy, paths)

            self.assertTrue(injected)
            self.assertTrue((paths.attachments / "must-survive.txt").exists())

    def test_legacy_directory_staging_open_must_match_the_created_inode(self):
        import cortex_paths

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            legacy = base / "legacy"
            attachments = legacy / "attachments"
            attachments.mkdir(parents=True)
            (attachments / "capture.txt").write_text("original", encoding="utf-8")
            with patch.dict(os.environ, {"CORTEX_HOME": str(base / "runtime")}, clear=True):
                paths = cortex_paths.build_paths()
            real_open = cortex_paths.os.open
            injected = False
            substituted_staging: Path | None = None

            def substitute_staging_before_open(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal injected, substituted_staging
                name = os.fspath(path)
                if (
                    not injected
                    and dir_fd is not None
                    and name.startswith(".attachments.migration-")
                ):
                    injected = True
                    cortex_paths.os.rename(
                        name,
                        f"{name}.preserved",
                        src_dir_fd=dir_fd,
                        dst_dir_fd=dir_fd,
                    )
                    cortex_paths.os.mkdir(name, 0o700, dir_fd=dir_fd)
                    substituted_staging = paths.home / name
                    attacker_parent = real_open(
                        name,
                        cortex_paths.DIRECTORY_FLAGS,
                        dir_fd=dir_fd,
                    )
                    try:
                        attacker_fd = real_open(
                            "must-survive.txt",
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=attacker_parent,
                        )
                        cortex_paths.os.close(attacker_fd)
                    finally:
                        cortex_paths.os.close(attacker_parent)
                if dir_fd is None:
                    return real_open(path, flags, mode)
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with patch.object(cortex_paths.os, "open", side_effect=substitute_staging_before_open):
                with self.assertRaisesRegex(RuntimeError, "destination changed"):
                    cortex_paths.migrate_legacy_state(legacy, paths)

            self.assertTrue(injected)
            self.assertIsNotNone(substituted_staging)
            self.assertTrue((substituted_staging / "must-survive.txt").exists())
            self.assertFalse(paths.attachments.exists())

    def test_legacy_nested_destination_open_must_match_the_created_inode(self):
        import cortex_paths

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            nested = base / "legacy" / "attachments" / "nested"
            nested.mkdir(parents=True)
            (nested / "capture.txt").write_text("original", encoding="utf-8")
            with patch.dict(os.environ, {"CORTEX_HOME": str(base / "runtime")}, clear=True):
                paths = cortex_paths.build_paths()
            real_mkdir = cortex_paths.os.mkdir
            real_open = cortex_paths.os.open
            destination_parents: set[int] = set()
            injected = False
            staging_name: str | None = None

            def track_destination_mkdir(path, mode=0o777, *, dir_fd=None):
                nonlocal staging_name
                result = real_mkdir(path, mode, dir_fd=dir_fd)
                name = os.fspath(path)
                if name.startswith(".attachments.migration-"):
                    staging_name = name
                if name == "nested" and dir_fd is not None:
                    destination_parents.add(dir_fd)
                return result

            def substitute_nested_before_open(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal injected
                name = os.fspath(path)
                if not injected and name == "nested" and dir_fd in destination_parents:
                    injected = True
                    cortex_paths.os.rename(
                        name,
                        "nested.preserved",
                        src_dir_fd=dir_fd,
                        dst_dir_fd=dir_fd,
                    )
                    real_mkdir(name, 0o700, dir_fd=dir_fd)
                    victim_parent = real_open(
                        name,
                        cortex_paths.DIRECTORY_FLAGS,
                        dir_fd=dir_fd,
                    )
                    try:
                        sentinel = real_open(
                            "must-survive.txt",
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=victim_parent,
                        )
                        cortex_paths.os.close(sentinel)
                    finally:
                        cortex_paths.os.close(victim_parent)
                if dir_fd is None:
                    return real_open(path, flags, mode)
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with (
                patch.object(cortex_paths.os, "mkdir", side_effect=track_destination_mkdir),
                patch.object(cortex_paths.os, "open", side_effect=substitute_nested_before_open),
            ):
                with self.assertRaisesRegex(RuntimeError, "destination changed"):
                    cortex_paths.migrate_legacy_state(base / "legacy", paths)

            self.assertTrue(injected)
            self.assertIsNotNone(staging_name)
            self.assertTrue(
                (paths.home / staging_name / "nested" / "must-survive.txt").exists()
            )
            self.assertFalse(paths.attachments.exists())

    def test_model_directory_priority_and_relative_path_rejection(self):
        from cortex_paths import model_directory

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            explicit = base / "explicit"
            legacy = base / "legacy"
            with patch.dict(
                os.environ,
                {"CORTEX_MODEL_DIR": str(explicit), "CORTEX_STORAGE_PATH": str(legacy)},
                clear=True,
            ):
                self.assertEqual(model_directory(), explicit.resolve(strict=False))
            with patch.dict(os.environ, {"CORTEX_STORAGE_PATH": str(legacy)}, clear=True):
                self.assertEqual(model_directory(), legacy.resolve(strict=False))
            with patch.dict(os.environ, {"CORTEX_MODEL_DIR": "relative/models"}, clear=True):
                with self.assertRaises(ValueError):
                    model_directory()
            with patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.home", return_value=base):
                self.assertEqual(
                    model_directory(),
                    (base / ".ollama" / "models").resolve(strict=False),
                )


if __name__ == "__main__":
    unittest.main()
