from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from storage_broker import (
    AttestedBrokerExecutable,
    BootIdentity,
    BrokerSocketIdentity,
    ClosedReadyResult,
    DarwinU32,
    LedgerState,
    StorageBrokerClient,
    StorageBrokerError,
    StorageLocalResponse,
    StorageWorkflowLedger,
    _StorageBrokerRequest,
    decode_frame,
    encode_frame,
    request_sha256,
    to_storage_evidence_response,
)


class FakeLocks:
    def __init__(self, home: Path, install: str = "shared", storage: str = "exclusive"):
        self.home = home
        self.install = install
        self.storage = storage
        self.active = True

    def assert_active(self, *, home: Path, required_install_mode: str, required_storage_mode: str):
        if not self.active or Path(home) != self.home:
            raise RuntimeError("invalid lock")
        if required_install_mode == "exclusive" and self.install != "exclusive":
            raise RuntimeError("weak install lock")
        if required_storage_mode == "exclusive" and self.storage != "exclusive":
            raise RuntimeError("weak storage lock")


def _request(op: str = "inspect-item"):
    return _StorageBrokerRequest(1, op, Path("/tmp/image"), None, None, None, uuid4(), None, False, False)


class CodecTests(unittest.TestCase):
    def test_canonical_frame_is_length_prefixed_and_rejects_noncanonical(self):
        frame = encode_frame({"z": 1, "a": {"a": 2}})
        self.assertEqual(decode_frame(frame), {"a": {"a": 2}, "z": 1})
        with self.assertRaises(ValueError):
            decode_frame(b"\x00\x00\x00\x07{\"a\":1} ")

    def test_frame_rejects_floats_and_oversized_payload(self):
        with self.assertRaises(ValueError):
            encode_frame({"value": 1.1})
        with self.assertRaises(ValueError):
            encode_frame({"value": "x" * 17000})

    def test_public_evidence_omits_native_identity(self):
        response = StorageLocalResponse(1, "inspect-item", "OK", None, None, 1)
        self.assertEqual(to_storage_evidence_response(response).item_count, 1)
        with self.assertRaises(ValueError):
            StorageLocalResponse(1, "inspect-item", "OK", None, "/dev/disk4", 1)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir(mode=0o700)
        self.lock = FakeLocks(self.home)
        fd = os.open(self.home / "broker", os.O_RDWR | os.O_CREAT, 0o700)
        self.addCleanup(lambda: os.close(fd))
        self.executable = AttestedBrokerExecutable(Path(self.home / "broker"), fd, DarwinU32(1), 2, os.getuid(), 0o700, "a" * 64, "b" * 64)

    def test_five_state_prepare_running_closed_and_reload(self):
        ledger = StorageWorkflowLedger(self.home)
        from storage_broker import _new_recovery_authority
        recovery = _new_recovery_authority(self.home)
        self.addCleanup(recovery.close)
        record = ledger.prepare_locked(
            self.lock, _request(), self.executable,
            BrokerSocketIdentity(self.home / "sock", DarwinU32(1), 3, os.getuid(), 0o600),
            BootIdentity(5, 6), recovery, effect_budget_ns=10, cleanup_budget_ns=0,
        )
        self.assertEqual(record.state, LedgerState.OPEN_PREPARED)
        running = ledger.mark_running_before_start_locked(
            self.lock, record.workflow_id, record.generation, broker_pid=1, broker_sid=1,
            broker_pgid=1, owner_connection_nonce="n", owner_peer_audit_sha256="c" * 64,
        )
        self.assertEqual(running.state, LedgerState.OPEN_RUNNING)
        loaded = ledger.load_all_locked(self.lock)
        self.assertEqual(loaded[0].record_sha256, running.record_sha256)

    def test_broker_without_transport_fails_closed_before_start(self):
        ledger = StorageWorkflowLedger(self.home)
        client = StorageBrokerClient(home=self.home, executable=self.executable, ledger=ledger)
        with self.assertRaisesRegex(StorageBrokerError, "BROKER_UNAVAILABLE"):
            client._run_locked(self.lock, _request(), effect_budget_ns=10, cleanup_budget_ns=0)
        record = ledger.load_all_locked(self.lock)[0]
        self.assertEqual(record.state, LedgerState.CLOSED_FAILURE)


if __name__ == "__main__":
    unittest.main()
