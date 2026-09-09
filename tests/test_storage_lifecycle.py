from __future__ import annotations

import tempfile
from dataclasses import asdict
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from storage_lifecycle import HostBinding, LegacySnapshot, StorageLifecycle, StoragePaths
from storage_lock import open_storage_lock_set
from storage_result import OperationResult
from storage_broker import StorageLocalResponse


class FakeBroker:
    def __init__(self):
        self.requests = []
        self.encryption_uuid = str(uuid4())

    def _run_locked(self, lock_set, request, *, effect_budget_ns, cleanup_budget_ns):
        self.requests.append((lock_set, request, effect_budget_ns, cleanup_budget_ns))
        return SimpleNamespace(
            state="CLOSED_SUCCESS", workflow_id=uuid4(), transaction_id=request.transaction_id,
            terminal_outcome="success", terminal_code="OK",
            child_reaped=True, group_absent=True, native_cleanup_proven=True,
            recovery_authority_consumed=True,
            terminal_response={"response_kind": "local", "response": asdict(StorageLocalResponse(
                1, request.operation, "OK", self.encryption_uuid, None,
                0 if request.operation == "delete-disposable-item" else 1))},
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
                requests = [item[1] for item in broker.requests]
                self.assertEqual([request.operation for request in requests],
                                 ["create", "inspect-item", "delete-disposable-item"])
                self.assertEqual({request.transaction_id for request in requests}, {requests[0].transaction_id})
                self.assertEqual({request.image_path for request in requests}, {requests[0].image_path})
                self.assertEqual(requests[0].image_path.name, f"spike-{requests[0].transaction_id}.sparsebundle")
                for request in requests[1:]:
                    self.assertEqual(request.expected_encryption_uuid, broker.encryption_uuid)
                    self.assertIsNone(request.volume_name)
                    self.assertIsNone(request.size)

    def test_spike_never_claims_success_from_missing_terminal_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            paths = StoragePaths(home, home, home / "legacy", home / "new", home / "mount",
                                 home / "root", home / "bootstrap", home / "marker", home / "transition", home / "quarantine")
            broker = FakeBroker()
            original = broker._run_locked
            def missing(*args, **kwargs):
                record = original(*args, **kwargs)
                record.terminal_response = None
                return record
            broker._run_locked = missing
            lifecycle = StorageLifecycle(paths, broker=broker, fd_probe=lambda _: True, mount_verifier=lambda _: None)
            with open_storage_lock_set(home, install_mode="exclusive", storage_mode="exclusive") as locks:
                result = lifecycle.keychain_spike_locked(locks, cleanup_approved=True)
            self.assertEqual(result.verdict, "FAIL")
            self.assertEqual(len(broker.requests), 1)

    def test_third_party_lock_object_is_rejected_before_backend(self):
        home = Path(tempfile.mkdtemp())
        paths = StoragePaths(home, home, home / "legacy", home / "new", home / "mount", home / "root", home / "bootstrap", home / "marker", home / "transition", home / "quarantine")
        broker = FakeBroker()
        lifecycle = StorageLifecycle(paths, broker=broker, fd_probe=lambda _path: True, mount_verifier=lambda _locks: None)
        with self.assertRaises(Exception):
            lifecycle.status_locked(object())
        self.assertFalse(broker.requests)

    def test_spike_stops_at_each_unconfirmed_step(self):
        mutations = (
            ("create", "unfinished"), ("create", "wrong-transaction"),
            ("create", "invalid-uuid"), ("inspect-item", "missing-item"),
            ("inspect-item", "wrong-uuid"), ("inspect-item", "boolean-count"),
            ("delete-disposable-item", "remaining-item"),
            ("delete-disposable-item", "failure"),
        )
        for operation, mutation in mutations:
            with self.subTest(operation=operation, mutation=mutation), tempfile.TemporaryDirectory() as td:
                home = Path(td)
                paths = StoragePaths(home, home, home / "legacy", home / "new", home / "mount",
                                     home / "root", home / "bootstrap", home / "marker", home / "transition", home / "quarantine")
                broker = FakeBroker()
                original = broker._run_locked
                def altered(locks, request, **kwargs):
                    record = original(locks, request, **kwargs)
                    if request.operation == operation:
                        response = record.terminal_response["response"]
                        if mutation == "unfinished": record.recovery_authority_consumed = False
                        elif mutation == "wrong-transaction": record.transaction_id = uuid4()
                        elif mutation == "invalid-uuid": response["encryption_uuid"] = "not-a-uuid"
                        elif mutation == "wrong-uuid": response["encryption_uuid"] = str(uuid4())
                        elif mutation == "missing-item": response["item_count"] = 0
                        elif mutation == "remaining-item": response["item_count"] = 1
                        elif mutation == "boolean-count": response["item_count"] = True
                        elif mutation == "failure": record.terminal_outcome = "failure"
                    return record
                broker._run_locked = altered
                lifecycle = StorageLifecycle(paths, broker=broker, fd_probe=lambda _: True, mount_verifier=lambda _: None)
                with open_storage_lock_set(home, install_mode="exclusive", storage_mode="exclusive") as locks:
                    result = lifecycle.keychain_spike_locked(locks, cleanup_approved=True)
                self.assertEqual(result.verdict, "FAIL")
                self.assertEqual(result.code, "SPIKE_RESPONSE_UNCONFIRMED")
                self.assertEqual(len(broker.requests), {"create": 1, "inspect-item": 2, "delete-disposable-item": 3}[operation])

    def test_spike_requires_explicit_cleanup_approval_before_any_request(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            paths = StoragePaths(home, home, home / "legacy", home / "new", home / "mount",
                                 home / "root", home / "bootstrap", home / "marker", home / "transition", home / "quarantine")
            broker = FakeBroker()
            lifecycle = StorageLifecycle(paths, broker=broker, fd_probe=lambda _: True, mount_verifier=lambda _: None)
            with open_storage_lock_set(home, install_mode="exclusive", storage_mode="exclusive") as locks:
                for approval in (False, None, 1, "yes"):
                    self.assertEqual(lifecycle.keychain_spike_locked(locks, cleanup_approved=approval).code, "CLEANUP_NOT_AUTHORIZED")
            self.assertEqual(broker.requests, [])


if __name__ == "__main__":
    unittest.main()
