from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


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
    def test_check_evidence_accepts_only_safe_literals_or_an_exact_lowercase_sha256(self) -> None:
        digest = "a" * 64
        accepted = (
            "committed_transaction_verified",
            "contract_passed",
            "contract_rejected",
            "contract_unclear",
            f"sha256_{digest}",
        )
        rejected = (
            f"sha256_{'a' * 63}",
            f"sha256_{'a' * 65}",
            f"sha256_{('a' * 63) + 'g'}",
            f"sha256_{'A' * 64}",
            f"prefix_sha256_{digest}",
            f"sha256_{digest}_suffix",
            f"digest_{digest}",
            "email_alice@example.com",
            "password=hunter2",
            "contract passed",
            "contrat_validé",
            r"\\server\\private",
        )

        for evidence in accepted:
            with self.subTest(accepted=evidence):
                self.assertEqual(
                    CheckResult("journal", "PASS", evidence).evidence,
                    evidence,
                )
        for evidence in rejected:
            with self.subTest(rejected=evidence):
                with self.assertRaises(ValueError):
                    CheckResult("journal", "PASS", evidence)

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
            "alice@example.com",
            "password=hunter2",
            "committed transaction verified",
            "contrat_validé",
            r"\\server\\private",
            "unapproved_evidence_token",
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

    def test_open_storage_lock_rejects_a_private_regular_marker_with_invalid_provenance(self) -> None:
        lock_path = self.home / "storage-state.lock"
        invalid = b'{"owner":"cortex-bridge","schema_version":2}\n'
        lock_path.write_bytes(invalid)
        lock_path.chmod(0o600)

        with self.assertRaisesRegex(StorageLockError, "STORAGE_LOCK_UNSAFE"):
            open_storage_lock(self.home, "exclusive")
        with self.assertRaisesRegex(StorageLockError, "STORAGE_LOCK_UNSAFE"):
            open_existing_storage_lock(self.home, "shared")

        self.assertEqual(lock_path.read_bytes(), invalid)
        self.assertEqual(stat.S_IMODE(lock_path.stat().st_mode), 0o600)

    def test_open_storage_lock_rejects_non_finite_timeouts(self) -> None:
        for timeout in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    open_storage_lock(self.home, "shared", timeout_seconds=timeout)

    def test_zero_timeout_acquires_free_marker_and_ordered_locks(self) -> None:
        with open_storage_lock(self.home, "exclusive", timeout_seconds=0):
            pass
        with ordered_storage_locks(
            self.home,
            install_mode="exclusive",
            storage_mode="exclusive",
            timeout_seconds=0,
        ) as (install_fd, storage_lock_handle):
            self.assertIsInstance(install_fd, int)
            self.assertEqual(storage_lock_handle.mode, "exclusive")

    def test_zero_timeout_contended_ordered_lock_skips_callback(self) -> None:
        process, _ready, release = self._start_shared_holder()
        try:
            callback_ran = False
            with self.assertRaisesRegex(StorageLockError, "STORAGE_LOCK_TIMEOUT"):
                with ordered_storage_locks(
                    self.home,
                    install_mode="exclusive",
                    storage_mode="exclusive",
                    timeout_seconds=0,
                ):
                    callback_ran = True
            self.assertFalse(callback_ran)
            self.assertTrue((self.home / ".install.lock").is_file())
        finally:
            self._release_holder(process, release)

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

    def test_open_storage_lock_times_out_during_invalid_marker_validation(self) -> None:
        lock_path = self.home / "storage-state.lock"
        lock_path.write_bytes(b"invalid-provenance")
        lock_path.chmod(0o600)
        ready = self.home.parent / "invalid-lock-ready"
        release = self.home.parent / "invalid-lock-release"
        holder_script = (
            "import fcntl,os,time\n"
            "from pathlib import Path\n"
            f"lock=Path({str(lock_path)!r})\n"
            f"ready=Path({str(ready)!r})\n"
            f"release=Path({str(release)!r})\n"
            "fd=os.open(lock, os.O_RDWR)\n"
            "fcntl.flock(fd, fcntl.LOCK_EX)\n"
            "ready.write_text('ready', encoding='utf-8')\n"
            "while not release.exists(): time.sleep(0.005)\n"
            "fcntl.flock(fd, fcntl.LOCK_UN)\n"
            "os.close(fd)\n"
        )
        holder = subprocess.Popen([sys.executable, "-c", holder_script])
        try:
            deadline = time.monotonic() + 5.0
            while not ready.exists() and holder.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists(), "invalid marker holder did not start")
            caller_script = (
                "import sys\n"
                f"sys.path.insert(0, {str(CONSOLE)!r})\n"
                "from pathlib import Path\n"
                "from storage_lock import StorageLockError,open_storage_lock\n"
                "try:\n"
                f" open_storage_lock(Path({str(self.home)!r}), 'shared', timeout_seconds=0.05)\n"
                "except StorageLockError as exc:\n"
                " print(exc.code)\n"
            )
            caller = subprocess.Popen(
                [sys.executable, "-c", caller_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                stdout, stderr = caller.communicate(timeout=1.0)
            except subprocess.TimeoutExpired:
                caller.kill()
                caller.communicate(timeout=5)
                self.fail("storage marker validation exceeded its total timeout budget")
            self.assertEqual(caller.returncode, 0, stderr)
            self.assertEqual(stdout.strip(), "STORAGE_LOCK_TIMEOUT")
        finally:
            release.write_text("release", encoding="utf-8")
            holder.wait(timeout=5)

    def test_ordered_storage_locks_observes_acquisition_and_release_order(self) -> None:
        import lifecycle_lock
        import storage_lock

        install_path = self.home / ".install.lock"
        storage_path = self.home / "storage-state.lock"
        for path in (install_path, storage_path):
            fd = lifecycle_lock.open_lifecycle_lock(path)
            os.close(fd)
        identities = {
            (install_path.stat().st_dev, install_path.stat().st_ino): "install",
            (storage_path.stat().st_dev, storage_path.stat().st_ino): "storage",
        }
        observed: list[str] = []
        real_flock = storage_lock.fcntl.flock

        def record_flock(fd: int, operation: int) -> None:
            name = identities.get((os.fstat(fd).st_dev, os.fstat(fd).st_ino))
            if name is not None:
                if operation == storage_lock.fcntl.LOCK_UN:
                    observed.append(f"release:{name}")
                elif operation & storage_lock.fcntl.LOCK_NB:
                    observed.append(f"acquire:{name}")
            real_flock(fd, operation)

        with mock.patch.object(storage_lock.fcntl, "flock", side_effect=record_flock):
            with ordered_storage_locks(
                self.home,
                install_mode="exclusive",
                storage_mode="exclusive",
            ) as (install_fd, storage_lock_handle):
                self.assertIsInstance(install_fd, int)
                self.assertEqual(storage_lock_handle.mode, "exclusive")

        self.assertEqual(
            observed,
            [
                "acquire:install",
                "acquire:storage",
                "release:storage",
                "release:install",
            ],
        )


if __name__ == "__main__":
    unittest.main()
