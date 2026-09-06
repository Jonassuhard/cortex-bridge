from __future__ import annotations

import os
import socket
import tempfile
import time
import unittest
from pathlib import Path

import startup_lease
from startup_lease import (
    ManagedProcessIdentity,
    ManagedStartContext,
    StartupLeaseError,
    child_consume_startup_lease,
    parent_release_and_wait_ack,
    publish_startup_lease,
)
from storage_broker import BootIdentity


class StartupLeaseTests(unittest.TestCase):
    def _writer(self):
        writer = getattr(startup_lease, "write_runtime_lifespan_record", None)
        self.assertTrue(callable(writer), "runtime lifespan writer is missing")
        return writer

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
                identity=ManagedProcessIdentity(os.getpid(), os.getpgrp(), "start"),
                storage_transaction_id=None,
                boot=BootIdentity(1, 2),
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


if __name__ == "__main__":
    unittest.main()
