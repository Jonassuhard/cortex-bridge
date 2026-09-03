from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT / "console"
sys.path.insert(0, str(CONSOLE))

from lifecycle_lock import LIFECYCLE_LOCK_MARKER  # noqa: E402
from storage_lock import (  # noqa: E402
    StorageLockError,
    open_existing_storage_lock,
    open_storage_lock,
    ordered_storage_locks,
)
from storage_result import CheckResult, OperationResult, StorageStatus  # noqa: E402


class StorageResultTest(unittest.TestCase):
    def test_status_serializes_the_canonical_redacted_schema(self) -> None:
        result = OperationResult(
            operation="status",
            verdict="PASS",
            transaction_id="8ce4e7ce-8e9a-45ef-a112-64a14dfc1c83",
            code="STORAGE_READY",
            checks=(
                CheckResult("journal", "PASS", "committed_transaction_verified"),
            ),
            storage_state="READY",
            mounted=True,
            runtime_allowed=True,
            recovery="UNCLEAR",
        )

        self.assertEqual(
            result.to_dict(),
            {
                "schema_version": 1,
                "operation": "status",
                "verdict": "PASS",
                "transaction_id": "8ce4e7ce-8e9a-45ef-a112-64a14dfc1c83",
                "code": "STORAGE_READY",
                "checks": [
                    {
                        "id": "journal",
                        "status": "PASS",
                        "evidence": "committed_transaction_verified",
                    }
                ],
                "private_paths_redacted": True,
                "storage_state": "READY",
                "mounted": True,
                "runtime_allowed": True,
                "recovery": "UNCLEAR",
            },
        )

    def test_result_rejects_lowercase_and_unknown_verdicts(self) -> None:
        with self.assertRaises(ValueError):
            CheckResult("journal", "pass", "committed_transaction_verified")
        with self.assertRaises(ValueError):
            OperationResult(
                operation="status",
                verdict="UNKNOWN",
                transaction_id=None,
                code="STORAGE_READY",
                checks=(),
                storage_state="READY",
                mounted=True,
                runtime_allowed=True,
                recovery="UNCLEAR",
            )
        with self.assertRaises(ValueError):
            StorageStatus(
                verdict="fail",
                code="STORAGE_UNAVAILABLE",
                transaction_id=None,
                storage_state="UNAVAILABLE",
                mounted=False,
                runtime_allowed=False,
            )

    def test_check_evidence_rejects_private_or_environment_derived_text(self) -> None:
        unsafe_evidence = (
            "/Users/owner/Library/Application Support/Cortex Bridge",
            "~/Library/Application Support/Cortex Bridge",
            "file:///private/runtime",
            "contains\x00control",
            "8ce4e7ce-8e9a-45ef-a112-64a14dfc1c83",
            os.environ.get("HOME", "unavailable-environment-value"),
        )

        for evidence in unsafe_evidence:
            with self.subTest(evidence=evidence):
                with self.assertRaises(ValueError):
                    CheckResult("journal", "PASS", evidence)

    def test_non_status_result_rejects_status_only_fields_and_extra_output_fields(self) -> None:
        with self.assertRaises(ValueError):
            OperationResult(
                operation="mount",
                verdict="PASS",
                transaction_id=None,
                code="STORAGE_MOUNTED",
                checks=(),
                mounted=True,
            )
        with self.assertRaises(TypeError):
            OperationResult(
                operation="mount",
                verdict="PASS",
                transaction_id=None,
                code="STORAGE_MOUNTED",
                checks=(),
                private_path="/private/runtime",
            )


class StorageLockTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name).resolve() / "cortex-home"
        self.home.mkdir(mode=0o700)
        self.home.chmod(0o700)

    def _start_shared_holder(self) -> tuple[subprocess.Popen[str], Path, Path]:
        ready = self.home.parent / "shared-ready"
        release = self.home.parent / "shared-release"
        script = (
            "import sys,time\n"
            f"sys.path.insert(0, {str(CONSOLE)!r})\n"
            "from pathlib import Path\n"
            "from storage_lock import open_storage_lock\n"
            f"home=Path({str(self.home)!r})\n"
            f"ready=Path({str(ready)!r})\n"
            f"release=Path({str(release)!r})\n"
            "with open_storage_lock(home, 'shared'):\n"
            " ready.write_text('ready', encoding='utf-8')\n"
            " while not release.exists(): time.sleep(0.005)\n"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 5.0
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        if not ready.exists():
            self.fail(process.stderr.read() if process.stderr else "shared holder did not start")
        return process, ready, release

    def _release_holder(self, process: subprocess.Popen[str], release: Path) -> None:
        release.write_text("release", encoding="utf-8")
        stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, stderr or stdout)

    def test_open_storage_lock_creates_a_private_canonical_marker(self) -> None:
        lock_path = self.home / "storage-state.lock"

        with open_storage_lock(self.home, "exclusive"):
            self.assertEqual(lock_path.read_bytes(), LIFECYCLE_LOCK_MARKER)
            details = lock_path.stat(follow_symlinks=False)
            self.assertTrue(stat.S_ISREG(details.st_mode))
            self.assertEqual(details.st_uid, os.getuid())
            self.assertEqual(details.st_nlink, 1)
            self.assertEqual(stat.S_IMODE(details.st_mode), 0o600)

    def test_open_storage_lock_rejects_a_symlink_marker_without_mutation(self) -> None:
        target = self.home.parent / "foreign-lock"
        target.write_bytes(b"foreign-lock")
        lock_path = self.home / "storage-state.lock"
        lock_path.symlink_to(target)

        with self.assertRaisesRegex(StorageLockError, "STORAGE_LOCK_UNSAFE"):
            open_storage_lock(self.home, "exclusive")

        self.assertEqual(target.read_bytes(), b"foreign-lock")
        self.assertTrue(lock_path.is_symlink())

    def test_open_storage_lock_rejects_a_hardlinked_marker_without_mutation(self) -> None:
        external = self.home.parent / "foreign-lock"
        external.write_bytes(LIFECYCLE_LOCK_MARKER)
        external.chmod(0o600)
        lock_path = self.home / "storage-state.lock"
        os.link(external, lock_path)
        before = external.read_bytes()

        with self.assertRaisesRegex(StorageLockError, "STORAGE_LOCK_UNSAFE"):
            open_storage_lock(self.home, "exclusive")

        self.assertEqual(external.read_bytes(), before)
        self.assertEqual(external.stat().st_nlink, 2)

    def test_open_existing_missing_fails_closed_without_mutating_private_home(self) -> None:
        before_identity = (self.home.stat().st_dev, self.home.stat().st_ino)
        before_entries = sorted(entry.name for entry in self.home.iterdir())

        with self.assertRaisesRegex(StorageLockError, "STORAGE_LOCK_MISSING") as raised:
            open_existing_storage_lock(self.home, "shared")

        self.assertEqual(raised.exception.code, "STORAGE_LOCK_MISSING")
        self.assertEqual(
            (self.home.stat().st_dev, self.home.stat().st_ino), before_identity
        )
        self.assertEqual(sorted(entry.name for entry in self.home.iterdir()), before_entries)
        self.assertFalse((self.home / "storage-state.lock").exists())

    def test_shared_holders_coexist_and_exclusive_times_out_before_callback(self) -> None:
        process, _ready, release = self._start_shared_holder()
        try:
            with open_storage_lock(self.home, "shared"):
                callback_ran = False
                with self.assertRaisesRegex(StorageLockError, "STORAGE_LOCK_TIMEOUT"):
                    with ordered_storage_locks(
                        self.home,
                        install_mode="shared",
                        storage_mode="exclusive",
                        timeout_seconds=0.05,
                    ):
                        callback_ran = True
                self.assertFalse(callback_ran)
                self.assertTrue((self.home / ".install.lock").is_file())
        finally:
            self._release_holder(process, release)

        with open_storage_lock(self.home, "exclusive"):
            pass

    def test_ordered_storage_locks_acquires_install_before_storage_and_releases_reverse(self) -> None:
        with open_storage_lock(self.home, "shared"):
            with self.assertRaisesRegex(StorageLockError, "STORAGE_LOCK_TIMEOUT"):
                with ordered_storage_locks(
                    self.home,
                    install_mode="exclusive",
                    storage_mode="exclusive",
                    timeout_seconds=0.05,
                ):
                    self.fail("storage contention must prevent the callback")

        self.assertTrue((self.home / ".install.lock").is_file())
        with ordered_storage_locks(
            self.home,
            install_mode="exclusive",
            storage_mode="exclusive",
        ) as (install_fd, storage_lock):
            self.assertIsInstance(install_fd, int)
            self.assertEqual(storage_lock.mode, "exclusive")


if __name__ == "__main__":
    unittest.main()
