"""Behavioral tests for bounded log rotation in scripts/cortex.sh."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORTEX_SH = ROOT / "scripts" / "cortex.sh"


class LogRotationTest(unittest.TestCase):
    @staticmethod
    def _install_stat_injector(root: Path) -> Path:
        injector = root / "stat-injector"
        injector.mkdir()
        (injector / "sitecustomize.py").write_text(
            "import os\n"
            "_real_fstat = os.fstat\n"
            "_real_fsync = os.fsync\n"
            "_real_open = os.open\n"
            "_foreign_fds = set()\n"
            "_archive_fsync_calls = 0\n"
            "if os.environ.get('TEST_ARCHIVE_FSYNC_ACTIVE'):\n"
            "    def _inject_archive_fsync(fd):\n"
            "        global _archive_fsync_calls\n"
            "        _archive_fsync_calls += 1\n"
            "        if _archive_fsync_calls == int(os.environ['TEST_ARCHIVE_FAIL_FSYNC_CALL']):\n"
            "            raise OSError(5, 'injected archive fsync failure')\n"
            "        return _real_fsync(fd)\n"
            "    os.fsync = _inject_archive_fsync\n"
            "if os.environ.get('TEST_FOREIGN_RUNTIME_COMPONENT'):\n"
            "    _runtime_target = os.environ['TEST_FOREIGN_RUNTIME_COMPONENT']\n"
            "    _runtime_home_name = os.path.basename(os.environ.get('CORTEX_HOME', ''))\n"
            "    def _track_runtime_open(path, flags, mode=0o777, *, dir_fd=None):\n"
            "        if dir_fd is None:\n"
            "            fd = _real_open(path, flags, mode)\n"
            "        else:\n"
            "            fd = _real_open(path, flags, mode, dir_fd=dir_fd)\n"
            "        name = os.fspath(path)\n"
            "        if (_runtime_target == 'home' and name == _runtime_home_name) or name == _runtime_target:\n"
            "            _foreign_fds.add(fd)\n"
            "        return fd\n"
            "    def _foreign_runtime_fstat(fd):\n"
            "        details = _real_fstat(fd)\n"
            "        if fd in _foreign_fds:\n"
            "            values = list(details)\n"
            "            values[4] = details.st_uid + 1\n"
            "            return os.stat_result(values)\n"
            "        return details\n"
            "    os.open = _track_runtime_open\n"
            "    os.fstat = _foreign_runtime_fstat\n"
            "if (\n"
            "    os.environ.get('TEST_FOREIGN_ARCHIVE_FSTAT_ACTIVE')\n"
            "    and os.environ.get('TEST_FOREIGN_ARCHIVE_COMPONENT')\n"
            "):\n"
            "    _archive_target = os.environ['TEST_FOREIGN_ARCHIVE_COMPONENT']\n"
            "    _archive_root = os.path.normpath(os.environ['TEST_FOREIGN_ARCHIVE_ROOT'])\n"
            "    def _track_archive_open(path, flags, mode=0o777, *, dir_fd=None):\n"
            "        if dir_fd is None:\n"
            "            fd = _real_open(path, flags, mode)\n"
            "        else:\n"
            "            fd = _real_open(path, flags, mode, dir_fd=dir_fd)\n"
            "        name = os.fspath(path)\n"
            "        if (_archive_target == 'root' and os.path.normpath(name) == _archive_root) or name == _archive_target:\n"
            "            _foreign_fds.add(fd)\n"
            "        return fd\n"
            "    def _cross_device_fstat(fd):\n"
            "        details = _real_fstat(fd)\n"
            "        if fd in _foreign_fds:\n"
            "            values = list(details)\n"
            "            values[2] = details.st_dev + 1\n"
            "            return os.stat_result(values)\n"
            "        return details\n"
            "    os.open = _track_archive_open\n"
            "    os.fstat = _cross_device_fstat\n",
            encoding="utf-8",
        )
        return injector

    def _environment(self, root: Path, *, state: str) -> dict[str, str]:
        bin_dir = root / "bin"
        bin_dir.mkdir()

        wrappers = {
            "curl": "#!/bin/sh\nexit 1\n",
            "lsof": "#!/bin/sh\nexit 0\n",
            "seq": "#!/bin/sh\necho 1\n",
            "sleep": "#!/bin/sh\nexit 0\n",
        }
        for name, body in wrappers.items():
            target = bin_dir / name
            target.write_text(body, encoding="utf-8")
            target.chmod(0o755)

        ownership = {
            "state": state,
            "pid": 4242 if state == "owned" else None,
            "listener_pids": [4242] if state == "owned" else [],
            "reason": "test fixture",
        }
        fake_python = root / "python"
        fake_python.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = -c ] && [ \"$2\" = \"import fastapi,uvicorn,playwright,websockets\" ]; then\n"
            "  if [ -n \"${TEST_SWAP_RUNTIME_HOME:-}\" ] && [ -n \"${TEST_SWAP_RUNTIME_PRESERVED:-}\" ] && [ -n \"${TEST_SWAP_RUNTIME_OUTSIDE:-}\" ]; then\n"
            "    /bin/mv \"$TEST_SWAP_RUNTIME_HOME\" \"$TEST_SWAP_RUNTIME_PRESERVED\"\n"
            "    /bin/ln -s \"$TEST_SWAP_RUNTIME_OUTSIDE\" \"$TEST_SWAP_RUNTIME_HOME\"\n"
            "  fi\n"
            "  exit 0\n"
            "fi\n"
            "case \"$1:$2\" in\n"
            f" */process_ownership.py:status) printf '%s\\n' {shlex.quote(json.dumps(ownership))}; exit 0;;\n"
            " server.py:*) exit 0;;\n"
            "esac\n"
            "case \"$1\" in\n"
            " */check-cortex-storage.py)\n"
            f"   verified_root=$({sys.executable!r} -c 'import json,sys; print(json.load(open(sys.argv[1], encoding=\"utf-8\"))[\"storage_root\"])' \"$3\" 2>/dev/null || true)\n"
            "   if [ -n \"${TEST_SWAP_BOOTSTRAP_FROM:-}\" ] && [ -n \"${TEST_SWAP_BOOTSTRAP_TO:-}\" ]; then\n"
            "     /bin/cp \"$TEST_SWAP_BOOTSTRAP_FROM\" \"$TEST_SWAP_BOOTSTRAP_TO\"\n"
            "   fi\n"
            "   if [ \"${4:-}\" = --json ]; then\n"
            f"     exec {sys.executable!r} -c 'import json,sys; print(json.dumps({{\"status\": \"ready\", \"storage_root\": sys.argv[1]}}))' \"$verified_root\"\n"
            "   fi\n"
            "   exit 0\n"
            "   ;;\n"
            "esac\n"
            "if [ \"$1\" = -c ] && printf '%s' \"$2\" | /usr/bin/grep -q CORTEX_SAFE_ARCHIVE_COPY; then\n"
            "  if [ -n \"${TEST_ARCHIVE_FAIL_FSYNC_CALL:-}\" ]; then\n"
            "    export TEST_ARCHIVE_FSYNC_ACTIVE=1\n"
            "  fi\n"
            "  if [ -n \"${TEST_ARCHIVE_SWAP_SOURCE:-}\" ] && [ -n \"${TEST_ARCHIVE_SWAP_VICTIM:-}\" ] && [ -n \"${TEST_ARCHIVE_SWAP_PRESERVED:-}\" ]; then\n"
            "    /bin/mv \"$TEST_ARCHIVE_SWAP_SOURCE\" \"$TEST_ARCHIVE_SWAP_PRESERVED\"\n"
            "    /bin/ln -s \"$TEST_ARCHIVE_SWAP_VICTIM\" \"$TEST_ARCHIVE_SWAP_SOURCE\"\n"
            "  fi\n"
            "fi\n"
            "if [ \"$1\" = -c ] && printf '%s' \"$2\" | /usr/bin/grep -q 'allowed, target ='; then\n"
            "  export TEST_FOREIGN_ARCHIVE_FSTAT_ACTIVE=1\n"
            "fi\n"
            f"exec {sys.executable!r} \"$@\"\n",
            encoding="utf-8",
        )
        fake_python.chmod(0o755)

        environment = {
            **os.environ,
            "CORTEX_HOME": str(root / "cortex-home"),
            "CORTEX_START_INSTALL_LOCK_HELD": "1",
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "PORT": "58422",
            "PYTHON_BIN": str(fake_python),
        }
        environment.pop("PYTHONPATH", None)
        return environment

    def _start(self, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(CORTEX_SH), "start"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_stopped_start_rotates_oversized_log_and_caps_backups(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            environment["CORTEX_LOG_MAX_BYTES"] = str(1024 * 1024)
            environment["CORTEX_LOG_BACKUPS"] = "2"

            log = Path(environment["CORTEX_HOME"]) / "logs" / "console.log"
            log.parent.mkdir(parents=True)
            archive_dir = log.parent / "archive" / "test"
            environment["CORTEX_LOG_ARCHIVE_DIR"] = str(archive_dir)
            current_content = b"c" * (1024 * 1024 + 1)
            log.write_bytes(current_content)
            Path(f"{log}.1").write_bytes(b"previous-one")
            Path(f"{log}.2").write_bytes(b"previous-two")
            Path(f"{log}.9").write_bytes(b"stale-backup")
            metadata = Path(f"{log}.metadata")
            metadata.write_bytes(b"not-a-numbered-backup")

            result = self._start(environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(Path(f"{log}.1").read_bytes(), current_content)
            self.assertEqual(Path(f"{log}.2").read_bytes(), b"previous-one")
            self.assertFalse(Path(f"{log}.9").exists())
            archived_contents = {
                path.read_bytes() for path in archive_dir.iterdir() if path.is_file()
            }
            self.assertEqual(archived_contents, {b"previous-two", b"stale-backup"})
            self.assertTrue(metadata.exists())
            self.assertEqual(metadata.read_bytes(), b"not-a-numbered-backup")
            self.assertEqual(log.read_bytes(), b"")

    def test_archive_directory_fsync_failure_preserves_complete_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            injector = self._install_stat_injector(root)
            environment["PYTHONPATH"] = str(injector)
            environment["TEST_ARCHIVE_FAIL_FSYNC_CALL"] = "2"

            log = Path(environment["CORTEX_HOME"]) / "logs" / "console.log"
            log.parent.mkdir(parents=True)
            archive_dir = log.parent / "archive" / "test"
            environment["CORTEX_LOG_ARCHIVE_DIR"] = str(archive_dir)
            backup = Path(f"{log}.9")
            original = b"complete-backup-before-archive-directory-fsync"
            backup.write_bytes(original)

            result = self._start(environment)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(backup.read_bytes(), original)
            self.assertIn("preserved in place: console.log.9", result.stderr)
            self.assertNotIn("archive copy retained", result.stderr)

    def test_source_directory_fsync_failure_restores_complete_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            injector = self._install_stat_injector(root)
            environment["PYTHONPATH"] = str(injector)
            environment["TEST_ARCHIVE_FAIL_FSYNC_CALL"] = "3"

            log = Path(environment["CORTEX_HOME"]) / "logs" / "console.log"
            log.parent.mkdir(parents=True)
            archive_dir = log.parent / "archive" / "test"
            environment["CORTEX_LOG_ARCHIVE_DIR"] = str(archive_dir)
            backup = Path(f"{log}.9")
            original = b"complete-backup-after-retirement-rename"
            backup.write_bytes(original)

            result = self._start(environment)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(backup.read_bytes(), original)
            archived = [path.read_bytes() for path in archive_dir.iterdir()]
            self.assertEqual(archived, [original])
            self.assertIn("source restored in place: console.log.9", result.stderr)
            self.assertIn("archive copy retained", result.stderr)

    def test_source_directory_fsync_failure_after_unlink_retains_complete_archive(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            injector = self._install_stat_injector(root)
            environment["PYTHONPATH"] = str(injector)
            environment["TEST_ARCHIVE_FAIL_FSYNC_CALL"] = "4"

            log = Path(environment["CORTEX_HOME"]) / "logs" / "console.log"
            log.parent.mkdir(parents=True)
            archive_dir = log.parent / "archive" / "test"
            environment["CORTEX_LOG_ARCHIVE_DIR"] = str(archive_dir)
            backup = Path(f"{log}.9")
            original = b"complete-archive-after-retired-source-unlink"
            backup.write_bytes(original)

            result = self._start(environment)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertFalse(backup.exists())
            archived = [path.read_bytes() for path in archive_dir.iterdir()]
            self.assertEqual(archived, [original])
            self.assertIn("archive copy retained", result.stderr)
            self.assertNotIn("preserved in place", result.stderr)
            self.assertNotIn("source restored in place", result.stderr)

    def test_owned_start_never_rotates_the_active_log(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="owned")
            environment["CORTEX_LOG_MAX_BYTES"] = str(1024 * 1024)
            environment["CORTEX_LOG_BACKUPS"] = "2"

            log = Path(environment["CORTEX_HOME"]) / "logs" / "console.log"
            log.parent.mkdir(parents=True)
            active_content = b"active" * 200_000
            log.write_bytes(active_content)

            result = self._start(environment)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(log.read_bytes(), active_content)
            self.assertFalse(Path(f"{log}.1").exists())

    def test_unsafe_rotation_setting_fails_without_touching_the_log(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            marker = root / "must-not-exist"
            environment["CORTEX_LOG_MAX_BYTES"] = f"1048576; touch {marker}"

            log = Path(environment["CORTEX_HOME"]) / "logs" / "console.log"
            log.parent.mkdir(parents=True)
            original_content = b"private-log-content"
            log.write_bytes(original_content)

            result = self._start(environment)

            self.assertEqual(result.returncode, 2)
            self.assertIn("CORTEX_LOG_MAX_BYTES", result.stderr)
            self.assertEqual(log.read_bytes(), original_content)
            self.assertFalse(marker.exists())
            self.assertFalse(Path(f"{log}.1").exists())

    def test_log_path_outside_runtime_is_refused_without_touching_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            outside = root / "outside.log"
            outside.write_bytes(b"must-stay")
            Path(f"{outside}.1").write_bytes(b"must-also-stay")
            environment["CORTEX_LOG"] = str(outside)

            result = self._start(environment)

            self.assertEqual(result.returncode, 2)
            self.assertIn("CORTEX_LOG must stay inside", result.stderr)
            self.assertEqual(outside.read_bytes(), b"must-stay")
            self.assertEqual(Path(f"{outside}.1").read_bytes(), b"must-also-stay")

    def test_log_traversal_is_refused_without_touching_runtime_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            cortex_home = Path(environment["CORTEX_HOME"])
            (cortex_home / "logs").mkdir(parents=True)
            settings = cortex_home / "settings.json"
            settings.write_bytes(b"private-settings")
            environment["CORTEX_LOG"] = str(cortex_home / "logs" / ".." / "settings.json")

            result = self._start(environment)

            self.assertEqual(result.returncode, 2)
            self.assertIn("without traversal or symlinks", result.stderr)
            self.assertEqual(settings.read_bytes(), b"private-settings")

    def test_log_symlink_component_is_refused_without_touching_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            cortex_home = Path(environment["CORTEX_HOME"])
            logs = cortex_home / "logs"
            logs.mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()
            target = outside / "console.log"
            target.write_bytes(b"outside-private")
            (logs / "linked").symlink_to(outside, target_is_directory=True)
            environment["CORTEX_LOG"] = str(logs / "linked" / "console.log")

            result = self._start(environment)

            self.assertEqual(result.returncode, 2)
            self.assertIn("without traversal or symlinks", result.stderr)
            self.assertEqual(target.read_bytes(), b"outside-private")

    def test_start_creates_private_runtime_directories_and_log(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            cortex_home = Path(environment["CORTEX_HOME"])

            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    'umask 022; exec bash "$1" start',
                    "cortex-private-runtime-test",
                    str(CORTEX_SH),
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(cortex_home.stat().st_mode & 0o777, 0o700)
            self.assertEqual((cortex_home / "pids").stat().st_mode & 0o777, 0o700)
            self.assertEqual((cortex_home / "logs").stat().st_mode & 0o777, 0o700)
            self.assertEqual(
                (cortex_home / "logs" / "console.log").stat().st_mode & 0o777,
                0o600,
            )

    def test_existing_owned_runtime_directories_are_private_before_locking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            environment.pop("CORTEX_START_INSTALL_LOCK_HELD")
            environment["CORTEX_LOG_MAX_BYTES"] = "invalid-after-lock"
            cortex_home = Path(environment["CORTEX_HOME"])
            logs = cortex_home / "logs"
            pids = cortex_home / "pids"
            logs.mkdir(parents=True, mode=0o755)
            pids.mkdir(mode=0o755)
            cortex_home.chmod(0o755)
            logs.chmod(0o755)
            pids.chmod(0o755)

            result = self._start(environment)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(cortex_home.stat().st_mode & 0o777, 0o700)
            self.assertEqual(logs.stat().st_mode & 0o777, 0o700)
            self.assertEqual(pids.stat().st_mode & 0o777, 0o700)

    def test_runtime_home_symlink_is_refused_before_lifecycle_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            environment.pop("CORTEX_START_INSTALL_LOCK_HELD")
            runtime_alias = Path(environment["CORTEX_HOME"])
            real_runtime = root / "real-runtime"
            real_runtime.mkdir()
            runtime_alias.symlink_to(real_runtime, target_is_directory=True)

            result = self._start(environment)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("CORTEX_RUNTIME_TREE_UNSAFE", result.stderr)
            self.assertFalse((real_runtime / ".install.lock").exists())
            self.assertEqual(list(real_runtime.iterdir()), [])

    def test_runtime_child_symlinks_are_refused_before_lifecycle_lock(self) -> None:
        for child_name in ("logs", "pids"):
            with self.subTest(child_name=child_name), tempfile.TemporaryDirectory() as temporary_root:
                root = Path(temporary_root)
                environment = self._environment(root, state="stopped")
                environment.pop("CORTEX_START_INSTALL_LOCK_HELD")
                cortex_home = Path(environment["CORTEX_HOME"])
                cortex_home.mkdir()
                outside = root / f"outside-{child_name}"
                outside.mkdir()
                (cortex_home / child_name).symlink_to(outside, target_is_directory=True)

                result = self._start(environment)

                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("CORTEX_RUNTIME_TREE_UNSAFE", result.stderr)
                self.assertFalse((cortex_home / ".install.lock").exists())
                self.assertEqual(list(outside.iterdir()), [])

    def test_foreign_owned_runtime_home_is_refused_before_lifecycle_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            environment.pop("CORTEX_START_INSTALL_LOCK_HELD")
            cortex_home = Path(environment["CORTEX_HOME"])
            cortex_home.mkdir()
            injector = self._install_stat_injector(root)
            environment["PYTHONPATH"] = str(injector)
            environment["TEST_FOREIGN_RUNTIME_COMPONENT"] = "home"

            result = self._start(environment)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("CORTEX_RUNTIME_TREE_UNSAFE", result.stderr)
            self.assertFalse((cortex_home / ".install.lock").exists())
            self.assertEqual(list(cortex_home.iterdir()), [])

    def test_foreign_owned_runtime_children_are_refused_before_lifecycle_lock(self) -> None:
        for component in ("logs", "pids"):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as temporary_root:
                root = Path(temporary_root)
                environment = self._environment(root, state="stopped")
                environment.pop("CORTEX_START_INSTALL_LOCK_HELD")
                cortex_home = Path(environment["CORTEX_HOME"])
                (cortex_home / "logs").mkdir(parents=True)
                (cortex_home / "pids").mkdir()
                injector = self._install_stat_injector(root)
                environment["PYTHONPATH"] = str(injector)
                environment["TEST_FOREIGN_RUNTIME_COMPONENT"] = component

                result = self._start(environment)

                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("CORTEX_RUNTIME_TREE_UNSAFE", result.stderr)
                self.assertFalse((cortex_home / ".install.lock").exists())

    def test_runtime_substitution_after_validation_cannot_redirect_start_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            cortex_home = Path(environment["CORTEX_HOME"])
            (cortex_home / "logs").mkdir(parents=True)
            (cortex_home / "pids").mkdir()
            preserved = root / "cortex-home.preserved"
            outside = root / "outside"
            (outside / "logs").mkdir(parents=True)
            (outside / "pids").mkdir()
            environment["TEST_SWAP_RUNTIME_HOME"] = str(cortex_home)
            environment["TEST_SWAP_RUNTIME_PRESERVED"] = str(preserved)
            environment["TEST_SWAP_RUNTIME_OUTSIDE"] = str(outside)

            result = self._start(environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(cortex_home.is_symlink())
            self.assertEqual(list((outside / "logs").iterdir()), [])
            self.assertEqual(list((outside / "pids").iterdir()), [])
            self.assertTrue((preserved / "logs" / "console.log").exists())

    def test_required_external_storage_archives_logs_outside_local_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            environment["CORTEX_LOG_MAX_BYTES"] = str(1024 * 1024)
            environment["CORTEX_LOG_BACKUPS"] = "1"
            cortex_home = Path(environment["CORTEX_HOME"])
            cortex_home.mkdir(parents=True)
            storage_root = root / "external" / "CORTEX_BRIDGE"
            storage_root.mkdir(parents=True)
            (cortex_home / "storage-required").write_text("required\n", encoding="utf-8")
            (cortex_home / "storage-bootstrap.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "mount_path": str(root / "external"),
                        "volume_uuid": "12345678-1234-1234-1234-123456789ABC",
                        "encrypted_image_path": str(root / "vault.sparsebundle"),
                        "storage_root": str(storage_root),
                    }
                ),
                encoding="utf-8",
            )
            log = cortex_home / "logs" / "console.log"
            log.parent.mkdir()
            log.write_bytes(b"current" * 200_000)
            Path(f"{log}.1").write_bytes(b"previous")

            result = self._start(environment)

            self.assertNotEqual(result.returncode, 0)
            archive = storage_root / "99_QUARANTINE" / "logs"
            self.assertTrue(archive.is_dir())
            self.assertIn(b"previous", {path.read_bytes() for path in archive.iterdir()})
            self.assertFalse((cortex_home / "logs" / "archive").exists())

    def test_external_archive_rejects_each_cross_device_quarantine_component(self) -> None:
        for component in ("root", "99_QUARANTINE", "logs"):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as temporary_root:
                root = Path(temporary_root)
                environment = self._environment(root, state="stopped")
                environment["CORTEX_LOG_MAX_BYTES"] = str(1024 * 1024)
                environment["CORTEX_LOG_BACKUPS"] = "1"
                injector = self._install_stat_injector(root)
                environment["PYTHONPATH"] = str(injector)
                environment["TEST_FOREIGN_ARCHIVE_COMPONENT"] = component
                cortex_home = Path(environment["CORTEX_HOME"])
                cortex_home.mkdir(parents=True)
                storage_root = root / "external" / "CORTEX_BRIDGE"
                storage_root.mkdir(parents=True)
                environment["TEST_FOREIGN_ARCHIVE_ROOT"] = str(storage_root)
                (cortex_home / "storage-required").write_text("required\n", encoding="utf-8")
                (cortex_home / "storage-bootstrap.json").write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "mount_path": str(root / "external"),
                            "volume_uuid": "12345678-1234-1234-1234-123456789ABC",
                            "encrypted_image_path": str(root / "vault.sparsebundle"),
                            "storage_root": str(storage_root),
                        }
                    ),
                    encoding="utf-8",
                )
                log = cortex_home / "logs" / "console.log"
                log.parent.mkdir()
                backup = Path(f"{log}.9")
                backup.write_bytes(b"must-remain-local")

                result = self._start(environment)

                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("private owned directory", result.stderr)
                self.assertEqual(backup.read_bytes(), b"must-remain-local")

    def test_bootstrap_swap_after_guard_cannot_redirect_log_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            environment["CORTEX_LOG_MAX_BYTES"] = str(1024 * 1024)
            environment["CORTEX_LOG_BACKUPS"] = "1"
            cortex_home = Path(environment["CORTEX_HOME"])
            cortex_home.mkdir(parents=True)
            safe_storage = root / "safe-volume" / "CORTEX_BRIDGE"
            foreign_storage = root / "foreign-volume" / "CORTEX_BRIDGE"
            safe_storage.mkdir(parents=True)
            foreign_storage.mkdir(parents=True)
            bootstrap = cortex_home / "storage-bootstrap.json"
            bootstrap.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "mount_path": str(root / "safe-volume"),
                        "volume_uuid": "12345678-1234-1234-1234-123456789ABC",
                        "encrypted_image_path": str(root / "safe.sparsebundle"),
                        "storage_root": str(safe_storage),
                    }
                ),
                encoding="utf-8",
            )
            swapped = root / "swapped-bootstrap.json"
            swapped.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "mount_path": str(root / "foreign-volume"),
                        "volume_uuid": "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
                        "encrypted_image_path": str(root / "foreign.sparsebundle"),
                        "storage_root": str(foreign_storage),
                    }
                ),
                encoding="utf-8",
            )
            (cortex_home / "storage-required").write_text("required\n", encoding="utf-8")
            environment["TEST_SWAP_BOOTSTRAP_FROM"] = str(swapped)
            environment["TEST_SWAP_BOOTSTRAP_TO"] = str(bootstrap)
            log = cortex_home / "logs" / "console.log"
            log.parent.mkdir()
            log.write_bytes(b"current" * 200_000)
            Path(f"{log}.1").write_bytes(b"validated-storage-only")

            result = self._start(environment)

            self.assertNotEqual(result.returncode, 0)
            safe_archive = safe_storage / "99_QUARANTINE" / "logs"
            foreign_archive = foreign_storage / "99_QUARANTINE" / "logs"
            safe_contents = (
                {path.read_bytes() for path in safe_archive.iterdir()}
                if safe_archive.is_dir()
                else set()
            )
            self.assertIn(
                b"validated-storage-only",
                safe_contents,
            )
            self.assertFalse(foreign_archive.exists())

    def test_symlink_backup_is_refused_without_chmod_or_move(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            cortex_home = Path(environment["CORTEX_HOME"])
            log = cortex_home / "logs" / "console.log"
            log.parent.mkdir(parents=True)
            archive = log.parent / "archive" / "test"
            environment["CORTEX_LOG_ARCHIVE_DIR"] = str(archive)
            victim = root / "foreign-private.txt"
            victim.write_bytes(b"foreign")
            victim.chmod(0o644)
            backup = Path(f"{log}.9")
            backup.symlink_to(victim)

            result = self._start(environment)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("unsafe log backup", result.stderr)
            self.assertTrue(backup.is_symlink())
            self.assertEqual(victim.stat().st_mode & 0o777, 0o644)
            self.assertEqual(victim.read_bytes(), b"foreign")
            self.assertEqual(list(archive.iterdir()), [])

    def test_non_regular_backup_is_refused_and_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            cortex_home = Path(environment["CORTEX_HOME"])
            log = cortex_home / "logs" / "console.log"
            log.parent.mkdir(parents=True)
            archive = log.parent / "archive" / "test"
            environment["CORTEX_LOG_ARCHIVE_DIR"] = str(archive)
            backup = Path(f"{log}.9")
            backup.mkdir()

            result = self._start(environment)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("unsafe log backup", result.stderr)
            self.assertTrue(backup.is_dir())
            self.assertEqual(list(archive.iterdir()), [])

    def test_backup_substituted_after_identity_capture_is_refused_and_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            cortex_home = Path(environment["CORTEX_HOME"])
            log = cortex_home / "logs" / "console.log"
            log.parent.mkdir(parents=True)
            archive = log.parent / "archive" / "test"
            environment["CORTEX_LOG_ARCHIVE_DIR"] = str(archive)
            backup = Path(f"{log}.9")
            backup.write_bytes(b"expected-backup")
            victim = root / "foreign-private.txt"
            victim.write_bytes(b"foreign")
            victim.chmod(0o644)
            preserved = root / "expected-backup-preserved"
            environment["TEST_ARCHIVE_SWAP_SOURCE"] = str(backup)
            environment["TEST_ARCHIVE_SWAP_VICTIM"] = str(victim)
            environment["TEST_ARCHIVE_SWAP_PRESERVED"] = str(preserved)

            result = self._start(environment)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("unsafe log backup", result.stderr)
            self.assertTrue(backup.is_symlink())
            self.assertEqual(preserved.read_bytes(), b"expected-backup")
            self.assertEqual(victim.stat().st_mode & 0o777, 0o644)
            self.assertEqual(victim.read_bytes(), b"foreign")
            self.assertEqual(list(archive.iterdir()), [])

    def test_archive_override_outside_local_runtime_is_refused_without_chmod(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            foreign_directory = root / "foreign-directory"
            foreign_directory.mkdir(mode=0o755)
            sentinel = foreign_directory / "keep.txt"
            sentinel.write_bytes(b"keep")
            environment["CORTEX_LOG_ARCHIVE_DIR"] = str(foreign_directory)
            cortex_home = Path(environment["CORTEX_HOME"])
            log = cortex_home / "logs" / "console.log"
            log.parent.mkdir(parents=True)
            log.write_bytes(b"current")
            Path(f"{log}.9").write_bytes(b"must-stay-local")

            result = self._start(environment)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("dedicated archive root", result.stderr)
            self.assertEqual(foreign_directory.stat().st_mode & 0o777, 0o755)
            self.assertEqual(sentinel.read_bytes(), b"keep")
            self.assertEqual(Path(f"{log}.9").read_bytes(), b"must-stay-local")

    def test_archive_override_outside_validated_external_root_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            cortex_home = Path(environment["CORTEX_HOME"])
            cortex_home.mkdir(parents=True)
            storage_root = root / "external" / "CORTEX_BRIDGE"
            storage_root.mkdir(parents=True)
            foreign_directory = root / "foreign-directory"
            foreign_directory.mkdir(mode=0o755)
            environment["CORTEX_LOG_ARCHIVE_DIR"] = str(foreign_directory)
            (cortex_home / "storage-required").write_text("required\n", encoding="utf-8")
            (cortex_home / "storage-bootstrap.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "mount_path": str(root / "external"),
                        "volume_uuid": "12345678-1234-1234-1234-123456789ABC",
                        "encrypted_image_path": str(root / "vault.sparsebundle"),
                        "storage_root": str(storage_root),
                    }
                ),
                encoding="utf-8",
            )
            log = cortex_home / "logs" / "console.log"
            log.parent.mkdir()
            log.write_bytes(b"current")
            Path(f"{log}.9").write_bytes(b"must-stay-under-validated-root")

            result = self._start(environment)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("dedicated archive root", result.stderr)
            self.assertEqual(foreign_directory.stat().st_mode & 0o777, 0o755)
            self.assertEqual(
                Path(f"{log}.9").read_bytes(),
                b"must-stay-under-validated-root",
            )

    def test_archive_symlink_inside_allowed_root_is_refused_and_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            cortex_home = Path(environment["CORTEX_HOME"])
            log = cortex_home / "logs" / "console.log"
            log.parent.mkdir(parents=True)
            archive_root = log.parent / "archive"
            archive_root.mkdir(mode=0o700)
            real_archive = archive_root / "real-archive"
            real_archive.mkdir(mode=0o700)
            archive_alias = archive_root / "archive-alias"
            archive_alias.symlink_to(real_archive, target_is_directory=True)
            environment["CORTEX_LOG_ARCHIVE_DIR"] = str(archive_alias)
            backup = Path(f"{log}.9")
            backup.write_bytes(b"must-not-follow-archive-link")

            result = self._start(environment)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("without traversal or symlinks", result.stderr)
            self.assertTrue(archive_alias.is_symlink())
            self.assertEqual(backup.read_bytes(), b"must-not-follow-archive-link")
            self.assertEqual(list(real_archive.iterdir()), [])

    def test_local_archive_override_outside_archive_category_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            cortex_home = Path(environment["CORTEX_HOME"])
            log = cortex_home / "logs" / "console.log"
            log.parent.mkdir(parents=True)
            wrong_category = log.parent / "custom-logs"
            environment["CORTEX_LOG_ARCHIVE_DIR"] = str(wrong_category)
            backup = Path(f"{log}.9")
            backup.write_bytes(b"must-stay-in-local-archive-category")

            result = self._start(environment)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("dedicated archive root", result.stderr)
            self.assertFalse(wrong_category.exists())
            self.assertEqual(
                backup.read_bytes(),
                b"must-stay-in-local-archive-category",
            )

    def test_external_archive_override_outside_quarantine_logs_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            cortex_home = Path(environment["CORTEX_HOME"])
            cortex_home.mkdir(parents=True)
            storage_root = root / "external" / "CORTEX_BRIDGE"
            wrong_category = storage_root / "20_WORKSPACES" / "logs"
            wrong_category.mkdir(parents=True)
            environment["CORTEX_LOG_ARCHIVE_DIR"] = str(wrong_category)
            (cortex_home / "storage-required").write_text("required\n", encoding="utf-8")
            (cortex_home / "storage-bootstrap.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "mount_path": str(root / "external"),
                        "volume_uuid": "12345678-1234-1234-1234-123456789ABC",
                        "encrypted_image_path": str(root / "vault.sparsebundle"),
                        "storage_root": str(storage_root),
                    }
                ),
                encoding="utf-8",
            )
            log = cortex_home / "logs" / "console.log"
            log.parent.mkdir()
            backup = Path(f"{log}.9")
            backup.write_bytes(b"must-stay-in-external-quarantine")

            result = self._start(environment)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("dedicated archive root", result.stderr)
            self.assertEqual(list(wrong_category.iterdir()), [])
            self.assertEqual(
                backup.read_bytes(),
                b"must-stay-in-external-quarantine",
            )

    def test_retained_slot_symlink_is_refused_before_any_rotation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            environment = self._environment(root, state="stopped")
            environment["CORTEX_LOG_MAX_BYTES"] = str(1024 * 1024)
            environment["CORTEX_LOG_BACKUPS"] = "2"
            cortex_home = Path(environment["CORTEX_HOME"])
            log = cortex_home / "logs" / "console.log"
            log.parent.mkdir(parents=True)
            current = b"current" * 200_000
            log.write_bytes(current)
            victim = root / "foreign-private.txt"
            victim.write_bytes(b"foreign")
            retained = Path(f"{log}.1")
            retained.symlink_to(victim)

            result = self._start(environment)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("unsafe log backup", result.stderr)
            self.assertEqual(log.read_bytes(), current)
            self.assertTrue(retained.is_symlink())
            self.assertFalse(Path(f"{log}.2").exists())
            self.assertEqual(victim.read_bytes(), b"foreign")


if __name__ == "__main__":
    unittest.main()
