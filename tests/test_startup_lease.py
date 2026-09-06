from __future__ import annotations

import os
import socket
import tempfile
import time
import unittest
from pathlib import Path

from startup_lease import (
    ManagedProcessIdentity,
    StartupLeaseError,
    child_consume_startup_lease,
    parent_release_and_wait_ack,
    publish_startup_lease,
)
from storage_broker import BootIdentity


class StartupLeaseTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
