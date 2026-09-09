"""Real ledger/socket tests; executable and HELLO are synthetic, no effect runs."""
import hashlib
import os
from pathlib import Path
import socket
import tempfile
import time
import unittest
from uuid import uuid4

import storage_broker as broker
from storage_lock import open_storage_lock_set


class StartGrantTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name).resolve()
        executable = self.home / "broker-fixture"
        executable.write_bytes(b"not executed")
        executable.chmod(0o700)
        fd = os.open(executable, os.O_RDONLY)
        self.addCleanup(os.close, fd)
        info = os.fstat(fd)
        self.executable = broker.AttestedBrokerExecutable(executable, fd,
            broker.DarwinU32(info.st_dev & 0xffffffff), info.st_ino, info.st_uid, 0o700,
            hashlib.sha256(executable.read_bytes()).hexdigest(), "b" * 64)
        context = open_storage_lock_set(self.home, install_mode="shared", storage_mode="exclusive")
        self.locks = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        recovery = broker._new_recovery_authority(self.home)
        self.addCleanup(recovery.close)
        self.ledger = broker.StorageWorkflowLedger(self.home)
        self.boot = broker._current_boot_identity_exact()
        self.record = self.ledger.prepare_locked(self.locks,
            broker._StorageBrokerRequest(1, "inspect-item", self.home / "image", None,
                                        None, None, uuid4(), None, False, False), self.executable,
            broker.BrokerSocketIdentity(self.home / "listener", broker.DarwinU32(1), 1, os.getuid(), 0o600),
            self.boot, recovery, effect_budget_ns=1_000_000, cleanup_budget_ns=1)
        self.hello = dict(version=1, type="HELLO", workflow_id=str(self.record.workflow_id),
            generation=self.record.generation, connection_nonce="ab" * 32, cursor=0,
            payload=dict(broker_dev_u32=int(self.executable.dev_u32), broker_ino=info.st_ino,
                broker_uid=info.st_uid, broker_mode=0o700, broker_sha256=self.executable.sha256,
                boot_seconds=self.boot.seconds, boot_microseconds=self.boot.microseconds,
                peer_audit_sha256="cd" * 32))
        self.sender, self.receiver = socket.socketpair()
        self.addCleanup(self.sender.close)
        self.addCleanup(self.receiver.close)
        self.receiver.settimeout(0.05)

    def running(self):
        self.record = self.ledger.mark_running_before_start_locked(self.locks,
            self.record.workflow_id, self.record.generation, broker_pid=os.getpid(),
            broker_sid=os.getsid(0), broker_pgid=os.getpgrp(),
            owner_connection_nonce=self.hello["connection_nonce"],
            owner_peer_audit_sha256=self.hello["payload"]["peer_audit_sha256"])

    def send(self, channel):
        channel.send_locked(self.locks, ledger=self.ledger, record=self.record,
                            executable=self.executable, hello=self.hello)

    def test_running_grant_contains_durable_bindings_and_is_single_use(self):
        self.running()
        channel = broker._StartGrantChannel(self.sender)
        self.send(channel)
        frame = broker._read_frame_before_deadline(self.receiver, deadline_ns=time.monotonic_ns() + 1_000_000_000)
        self.assertEqual(frame, dict(version=1, type="START_GRANT",
            workflow_id=str(self.record.workflow_id), generation=self.record.generation,
            record_sha256=self.record.record_sha256, request_sha256=self.record.request_sha256,
            operation="inspect-item", effect_budget_ns=1_000_000, cleanup_budget_ns=1,
            boot_seconds=self.boot.seconds, boot_microseconds=self.boot.microseconds,
            connection_nonce="ab" * 32, peer_audit_sha256="cd" * 32))
        self.assertEqual(self.receiver.recv(1), b"")
        with self.assertRaises(broker.StorageBrokerError):
            self.send(channel)

    def test_prepared_record_cannot_send_a_grant(self):
        channel = broker._StartGrantChannel(self.sender)
        with self.assertRaises(broker.StorageBrokerError):
            self.send(channel)
        with self.assertRaises(socket.timeout):
            self.receiver.recv(1)

    def test_different_owner_connection_cannot_send_a_grant(self):
        self.running()
        self.hello["connection_nonce"] = "ef" * 32
        channel = broker._StartGrantChannel(self.sender)
        with self.assertRaises(broker.StorageBrokerError):
            self.send(channel)
        with self.assertRaises(socket.timeout):
            self.receiver.recv(1)

    def test_closed_socket_is_not_retried_after_uncertain_delivery(self):
        self.running()
        channel = broker._StartGrantChannel(self.sender)
        self.receiver.close()
        with self.assertRaises(broker.StorageBrokerError):
            self.send(channel)
        with self.assertRaisesRegex(broker.StorageBrokerError, "REPLAY"):
            self.send(channel)

    def test_changed_durable_record_cannot_use_an_older_grant(self):
        self.running()
        self.ledger.mark_unresolved_locked(self.locks, self.record.workflow_id,
                                          self.record.generation, broker.UnresolvedReason.BROKER_LOST)
        channel = broker._StartGrantChannel(self.sender)
        with self.assertRaises(broker.StorageBrokerError):
            self.send(channel)
        with self.assertRaises(socket.timeout):
            self.receiver.recv(1)

    def test_inactive_lock_cannot_publish_start_authority(self):
        self.running()
        channel = broker._StartGrantChannel(self.sender)
        self.locks.close()
        with self.assertRaises(RuntimeError):
            self.send(channel)
        with self.assertRaises(socket.timeout):
            self.receiver.recv(1)

    def test_named_unix_connection_is_not_a_start_capability(self):
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(listener.close)
        listener.bind(str(self.home / "named.sock"))
        listener.listen(1)
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(client.close)
        client.connect(str(self.home / "named.sock"))
        accepted, _ = listener.accept()
        self.addCleanup(accepted.close)
        with self.assertRaises(broker.StorageBrokerError):
            broker._StartGrantChannel(client)
