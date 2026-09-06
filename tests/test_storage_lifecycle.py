from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from storage_lifecycle import HostBinding, LegacySnapshot, StorageLifecycle, StoragePaths
from storage_lock import open_storage_lock_set
from storage_result import OperationResult


class FakeBroker:
    def __init__(self):
        self.requests = []

    def _run_locked(self, lock_set, request, *, effect_budget_ns, cleanup_budget_ns):
        self.requests.append((lock_set, request, effect_budget_ns, cleanup_budget_ns))
        return SimpleNamespace(
            state="CLOSED_SUCCESS", workflow_id=uuid4(), transaction_id=request.transaction_id,
            terminal_code="OK", terminal_response=None,
        )


class StorageLifecycleTests(unittest.TestCase):
    def test_operations_keep_the_exact_lock_set_and_private_requests(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir(mode=0o700)
            paths = StoragePaths(
                home=home, host_volume=home, legacy_image=home / "legacy.sparsebundle",
                new_image=home / "CORTEX_BRIDGE_2026_09.sparsebundle", mount=home / "mount",
                root=home / "mount" / "20_WORKSPACES", bootstrap=home / "storage-bootstrap.json",
                marker=home / "storage-required", transition=home / "storage-transition.json",
                quarantine=home / "private-quarantine",
            )
            broker = FakeBroker()
            seen = []
            verifier = lambda locks: seen.append(locks) or OperationResult(
                "status", "PASS", str(uuid4()), "STORAGE_READY", (),
                storage_state="COMMITTED", mounted=True, runtime_allowed=True, recovery="UNCLEAR",
            )
            lifecycle = StorageLifecycle(paths, broker=broker, fd_probe=lambda _path: True, mount_verifier=verifier)
            with open_storage_lock_set(home, install_mode="exclusive", storage_mode="exclusive") as locks:
                result = lifecycle.keychain_spike_locked(locks, cleanup_approved=True)
                self.assertEqual(result.verdict, "PASS")
                status = lifecycle.mount_or_adopt_locked(locks)
                self.assertEqual(status.code, "STORAGE_READY")
                self.assertIs(seen[0], locks)
                self.assertIs(broker.requests[0][0], locks)
                self.assertEqual(broker.requests[0][1].operation, "create")
                self.assertEqual(broker.requests[0][1].size, "64m")

    def test_third_party_lock_object_is_rejected_before_backend(self):
        home = Path(tempfile.mkdtemp())
        paths = StoragePaths(home, home, home / "legacy", home / "new", home / "mount", home / "root", home / "bootstrap", home / "marker", home / "transition", home / "quarantine")
        broker = FakeBroker()
        lifecycle = StorageLifecycle(paths, broker=broker, fd_probe=lambda _path: True, mount_verifier=lambda _locks: None)
        with self.assertRaises(Exception):
            lifecycle.status_locked(object())
        self.assertFalse(broker.requests)


if __name__ == "__main__":
    unittest.main()
