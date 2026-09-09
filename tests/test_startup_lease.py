from __future__ import annotations

import os
import json
import socket
import sys
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from types import SimpleNamespace

import startup_lease
from startup_lease import (
    ManagedProcessIdentity,
    ManagedStartContext,
    StartupLeaseError,
    _live_identity_matches,
    _read_kernel_process_identity,
    child_consume_startup_lease,
    parent_release_and_wait_ack,
    publish_startup_lease,
    managed_runtime_is_ready_locked,
)
from storage_broker import BootIdentity, _safe_boot_identity


class StartupLeaseTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "darwin", "macOS kernel identity")
    def test_boot_identity_is_exact_without_optional_sysctl_package(self):
        import storage_broker
        with mock.patch.dict(sys.modules, {"sysctl": None}), \
             mock.patch("storage_broker.time.time_ns", side_effect=AssertionError("clock approximation")):
            self.assertEqual(_safe_boot_identity(), storage_broker._current_boot_identity_exact())

    def test_storage_denial_prevents_generation_read_and_spawn(self):
        from storage_lock import open_storage_lock_set
        from storage_contract import StorageContract
        with tempfile.TemporaryDirectory() as td:
            home = Path(td).resolve()
            contract = StorageContract(home, broker=None)
            lifecycle = SimpleNamespace(status_locked=lambda locks: SimpleNamespace(
                verdict="FAIL", runtime_allowed=False, transaction_id=None))
            with open_storage_lock_set(home, install_mode="shared", storage_mode="shared") as locks:
                with mock.patch("managed_runtime.subprocess.Popen", side_effect=AssertionError("spawned")):
                    with self.assertRaisesRegex(StartupLeaseError, "STARTUP_STORAGE_NOT_READY"):
                        startup_lease.launch_managed_runtime(home, lock_set=locks,
                            lifecycle=lifecycle, contract=contract)

    def test_multiple_socket_frames_are_not_discarded(self):
        left, right = socket.socketpair()
        with left, right:
            left.sendall(b'{"type":"ACK"}\n{"type":"READY"}\n')
            self.assertEqual(startup_lease._recv_json(right, 1), {"type": "ACK"})
            self.assertEqual(startup_lease._recv_json(right, 1), {"type": "READY"})

    def test_lease_for_different_process_is_not_consumed(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            pids_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            left, right = socket.socketpair()
            try:
                identity = _read_kernel_process_identity(os.getpid())
                wrong = ManagedProcessIdentity(identity.pid, identity.pgid, "wrong-creation")
                lease = publish_startup_lease(pids_fd=pids_fd, identity=wrong,
                    storage_transaction_id=None, boot=_safe_boot_identity(), generation_record_sha256="a" * 64)
                startup_lease._send_json(left, {"type": "START", "lease_id": lease.lease_id, "nonce": lease.nonce})
                with self.assertRaisesRegex(StartupLeaseError, "PROCESS_MISMATCH"):
                    child_consume_startup_lease(control_fd=right.fileno(), pids_fd=pids_fd, expected_transaction_id=None)
                self.assertTrue((directory / f"startup-lease-{lease.lease_id}.json").is_file())
            finally:
                left.close()
                right.close()
                os.close(pids_fd)

    class _Locks:
        def __init__(self, home):
            self.home = Path(home)

        def assert_active(self, *, home, required_install_mode, required_storage_mode):
            if Path(home) != self.home:
                raise RuntimeError("wrong home")

    def _writer(self):
        writer = getattr(startup_lease, "write_runtime_lifespan_record", None)
        self.assertTrue(callable(writer), "runtime lifespan writer is missing")
        return writer

    def test_readiness_rejects_same_pid_and_pgid_with_different_kernel_creation(self):
        historical = ManagedProcessIdentity(
            4242, 4242, "darwin-proc-bsdinfo-v1:1700000000:123456"
        )
        reused = ManagedProcessIdentity(
            4242, 4242, "darwin-proc-bsdinfo-v1:1700000000:987654"
        )

        self.assertFalse(
            _live_identity_matches(historical, reader=lambda _pid: reused)
        )
        self.assertFalse(
            _live_identity_matches(historical, reader=lambda _pid: None)
        )

    @staticmethod
    def _context():
        return ManagedStartContext(
            lease_id="11111111-1111-4111-8111-111111111111",
            identity=ManagedProcessIdentity(os.getpid(), os.getpgrp(), "test-start"),
            storage_transaction_id=None,
            boot=BootIdentity(1, 2),
            generation_record_sha256="a" * 64,
            receipt_sha256="b" * 64,
        )

    def test_one_shot_parent_child_handshake_and_replay_rejection(self):
        with tempfile.TemporaryDirectory() as td:
            pids = Path(td) / "pids"
            pids.mkdir(mode=0o700)
            pids_fd = os.open(pids, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            left, right = socket.socketpair()
            lease = publish_startup_lease(
                pids_fd=pids_fd,
                identity=_read_kernel_process_identity(os.getpid()),
                storage_transaction_id=None,
                boot=_safe_boot_identity(),
                generation_record_sha256="a" * 64,
            )
            import threading
            seen = {}
            def child():
                seen["context"] = child_consume_startup_lease(
                    control_fd=right.detach(), pids_fd=pids_fd, expected_transaction_id=None
                )
            thread = threading.Thread(target=child)
            thread.start()
            parent_release_and_wait_ack(left.detach(), lease)
            thread.join(timeout=2)
            self.assertEqual(seen["context"].lease_id, lease.lease_id)
            receipt_path = pids / f"startup-lease-{lease.lease_id}.consumed.json"
            self.assertTrue(receipt_path.is_file())
            self.assertEqual(stat.S_IMODE(receipt_path.stat().st_mode), 0o600)
            self.assertEqual(json.loads(receipt_path.read_text(encoding="utf-8"))["nonce"], lease.nonce)
            self.assertFalse((pids / f"startup-lease-{lease.lease_id}.json").exists())
            replay_left, replay_right = socket.socketpair()
            replay_left.sendall(("{\"type\":\"START\",\"lease_id\":\"" + lease.lease_id + "\",\"nonce\":\"" + lease.nonce + "\"}\n").encode())
            with self.assertRaisesRegex(StartupLeaseError, "STARTUP_LEASE_REPLAYED"):
                child_consume_startup_lease(control_fd=replay_right.detach(), pids_fd=pids_fd, expected_transaction_id=None)
            replay_left.close()
            os.close(pids_fd)

    def test_expired_lease_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            pids = Path(td) / "pids"
            pids.mkdir(mode=0o700)
            pids_fd = os.open(pids, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            left, right = socket.socketpair()
            lease = publish_startup_lease(
                pids_fd=pids_fd,
                identity=ManagedProcessIdentity(os.getpid(), os.getpgrp(), "start"),
                storage_transaction_id=None,
                boot=BootIdentity(1, 2), generation_record_sha256="a" * 64,
                ttl_seconds=0.001,
            )
            time.sleep(0.01)
            left.sendall(("{\"type\":\"START\",\"lease_id\":\"" + lease.lease_id + "\",\"nonce\":\"" + lease.nonce + "\"}\n").encode())
            with self.assertRaisesRegex(StartupLeaseError, "STARTUP_LEASE_EXPIRED"):
                child_consume_startup_lease(control_fd=right.detach(), pids_fd=pids_fd, expected_transaction_id=None)
            left.close()
            os.close(pids_fd)

    def test_invalid_grant_preserves_unconsumed_lease(self):
        with tempfile.TemporaryDirectory() as td:
            pids = Path(td) / "pids"
            pids.mkdir(mode=0o700)
            pids_fd = os.open(pids, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            left, right = socket.socketpair()
            lease = publish_startup_lease(
                pids_fd=pids_fd,
                identity=ManagedProcessIdentity(os.getpid(), os.getpgrp(), "start"),
                storage_transaction_id=None,
                boot=BootIdentity(1, 2),
                generation_record_sha256="a" * 64,
            )
            left.sendall(
                json.dumps(
                    {"type": "START", "lease_id": lease.lease_id, "nonce": "0" * 32}
                ).encode("utf-8") + b"\n"
            )

            with self.assertRaisesRegex(StartupLeaseError, "STARTUP_LEASE_GRANT_INVALID"):
                child_consume_startup_lease(
                    control_fd=right.detach(), pids_fd=pids_fd,
                    expected_transaction_id=None,
                )

            self.assertTrue((pids / f"startup-lease-{lease.lease_id}.json").is_file())
            self.assertFalse((pids / f"startup-lease-{lease.lease_id}.consumed.json").exists())
            left.close()
            os.close(pids_fd)

    def test_runtime_lifespan_records_follow_starting_ready_closed_chain(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir(mode=0o700)
            context = self._context()
            write_runtime_lifespan_record = self._writer()
            starting = write_runtime_lifespan_record(home, context=context, state="STARTING")
            self.assertEqual(starting.state, "STARTING")
            self.assertTrue((home / "runtime-lifespan.json").is_file())
            ready = write_runtime_lifespan_record(
                home, context=context, state="READY",
                previous_record_sha256=starting.record_sha256,
            )
            self.assertEqual(ready.state, "READY")
            closed = write_runtime_lifespan_record(
                home, context=context, state="CLOSED",
                previous_record_sha256=ready.record_sha256,
            )
            self.assertEqual(closed.state, "CLOSED")
            self.assertNotEqual(starting.record_sha256, ready.record_sha256)
            self.assertNotEqual(ready.record_sha256, closed.record_sha256)

    def test_runtime_lifespan_rejects_skipped_or_wrong_previous_state(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir(mode=0o700)
            context = self._context()
            write_runtime_lifespan_record = self._writer()
            with self.assertRaisesRegex(StartupLeaseError, "LIFESPAN_TRANSITION_INVALID"):
                write_runtime_lifespan_record(home, context=context, state="READY")
            starting = write_runtime_lifespan_record(home, context=context, state="STARTING")
            with self.assertRaisesRegex(StartupLeaseError, "LIFESPAN_PREVIOUS_MISMATCH"):
                write_runtime_lifespan_record(
                    home, context=context, state="READY", previous_record_sha256="c" * 64
                )
            write_runtime_lifespan_record(
                home, context=context, state="READY",
                previous_record_sha256=starting.record_sha256,
            )
            with self.assertRaisesRegex(StartupLeaseError, "LIFESPAN_TRANSITION_INVALID"):
                write_runtime_lifespan_record(home, context=context, state="STARTING")

    def test_readiness_requires_live_identity_selected_generation_and_consumed_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            pids = home / "pids"
            pids.mkdir(mode=0o700, parents=True)
            home.chmod(0o700)
            # A thread consumes for this process; another process's lease must
            # now be rejected. Actual child launch is covered by installed E2E.
            identity = _read_kernel_process_identity(os.getpid())
            self.assertIsNotNone(identity)
            pids_fd = os.open(pids, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            left, right = socket.socketpair()
            lease = publish_startup_lease(
                pids_fd=pids_fd,
                identity=identity,
                storage_transaction_id=None,
                boot=_safe_boot_identity(),
                generation_record_sha256="a" * 64,
            )
            import threading
            seen = {}

            def consume():
                seen["context"] = child_consume_startup_lease(
                    control_fd=right.detach(), pids_fd=pids_fd,
                    expected_transaction_id=None,
                )

            thread = threading.Thread(target=consume)
            thread.start()
            parent_release_and_wait_ack(left.detach(), lease)
            thread.join(timeout=2)
            context = seen["context"]
            starting = startup_lease.write_runtime_lifespan_record(
                home, context=context, state="STARTING"
            )
            startup_lease.write_runtime_lifespan_record(
                home, context=context, state="READY",
                previous_record_sha256=starting.record_sha256,
            )
            (home / "current-generation.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "generation_id": "11111111-1111-4111-8111-111111111111",
                    "generation_record_sha256": "a" * 64,
                }),
                encoding="utf-8",
            )
            (home / "current-generation.json").chmod(0o600)
            locks = self._Locks(home)

            self.assertTrue(managed_runtime_is_ready_locked(
                locks, home=home, expected_storage_transaction_id=None
            ))
            consumed = pids / f"startup-lease-{lease.lease_id}.consumed.json"
            consumed.unlink()
            self.assertFalse(managed_runtime_is_ready_locked(
                locks, home=home, expected_storage_transaction_id=None
            ))

            os.close(pids_fd)


if __name__ == "__main__":
    unittest.main()
