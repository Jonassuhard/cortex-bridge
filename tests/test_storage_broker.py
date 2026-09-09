from __future__ import annotations

import os
import hashlib
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import storage_broker

from storage_broker import (
    AttestedBrokerExecutable,
    BootIdentity,
    BrokerSocketIdentity,
    ClosedReadyResult,
    DarwinU32,
    LedgerState,
    MountedImageProof,
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
    def test_budget_policy_requires_positive_bounded_integer_durations(self):
        for effect, cleanup in ((1, 1), (40_000_000_000, 12_000_000_000)):
            storage_broker._validate_budgets(effect, cleanup)
        for effect, cleanup in ((0, 1), (1, 0), (-1, 1), (1, -1),
                                (True, 1), (1, True), (1.0, 1), (1, 1.0),
                                (40_000_000_001, 1), (1, 12_000_000_001),
                                (2**64 - 1, 1), (1, 2**64 - 1)):
            with self.subTest(effect=effect, cleanup=cleanup), self.assertRaises(StorageBrokerError):
                storage_broker._validate_budgets(effect, cleanup)

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

    def test_frame_rejects_nested_duplicate_keys_and_integer_domain_violations(self):
        duplicate = b'{"payload":{"x":1,"x":2}}'
        with self.assertRaises(ValueError):
            decode_frame(len(duplicate).to_bytes(4, "big") + duplicate)
        for payload in (b'{"value":-1}', b'{"value":1.0}', b'{"value":18446744073709551616}'):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    decode_frame(len(payload).to_bytes(4, "big") + payload)

    def test_public_evidence_omits_native_identity(self):
        response = StorageLocalResponse(1, "inspect-item", "OK", None, None, 1)
        self.assertEqual(to_storage_evidence_response(response).item_count, 1)
        with self.assertRaises(ValueError):
            StorageLocalResponse(1, "inspect-item", "OK", None, "/dev/disk4", 1)


class PreEffectHelloTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir(mode=0o700)
        self.executable_path = self.home / "broker"
        self.executable_path.write_bytes(b"immutable-broker")
        self.executable_path.chmod(0o700)
        self.fd = os.open(self.executable_path, os.O_RDONLY)
        self.addCleanup(os.close, self.fd)
        details = os.fstat(self.fd)
        self.executable = AttestedBrokerExecutable(
            self.executable_path,
            self.fd,
            DarwinU32(details.st_dev & 0xFFFFFFFF),
            details.st_ino,
            details.st_uid,
            details.st_mode & 0o777,
            hashlib.sha256(b"immutable-broker").hexdigest(),
            "b" * 64,
        )
        self.workflow = uuid4()
        self.nonce = "ab" * 32
        self.audit = "cd" * 32

    def _hello(self):
        return {
            "version": 1,
            "type": "HELLO",
            "workflow_id": str(self.workflow),
            "generation": 7,
            "connection_nonce": self.nonce,
            "cursor": 0,
            "payload": {
                "broker_dev_u32": int(self.executable.dev_u32),
                "broker_ino": self.executable.ino,
                "broker_uid": self.executable.uid,
                "broker_mode": self.executable.mode,
                "broker_sha256": self.executable.sha256,
                "boot_seconds": 1,
                "boot_microseconds": 2,
                "peer_audit_sha256": self.audit,
            },
        }

    def test_validate_hello_requires_exact_envelope_and_re_attests_fd_and_path(self):
        validate = getattr(storage_broker, "_validate_pre_effect_hello", None)
        self.assertTrue(callable(validate), "pre-effect HELLO validator must exist")
        with patch.object(
            storage_broker, "_current_boot_identity_exact", return_value=BootIdentity(1, 2)
        ) as current_boot:
            result = validate(
                self._hello(),
                lock_set=FakeLocks(self.home, install="shared", storage="shared"),
                home=self.home,
                executable=self.executable,
                workflow_id=self.workflow,
                generation=7,
            )
        current_boot.assert_called_once_with()
        self.assertEqual(result.connection_nonce, self.nonce)
        self.assertEqual(result.peer_audit_sha256, self.audit)
        self.assertEqual(result.boot, BootIdentity(1, 2))

        for mutation in (
            lambda value: value.update(extra=True),
            lambda value: value.update(version=2),
            lambda value: value.update(version=True),
            lambda value: value.update(type="STARTED"),
            lambda value: value.update(workflow_id=str(uuid4())),
            lambda value: value.update(generation=8),
            lambda value: value.update(connection_nonce="00" * 32),
            lambda value: value.update(cursor=1),
            lambda value: value.update(cursor=False),
            lambda value: value["payload"].update(broker_pid=123),
        ):
            hello = self._hello()
            mutation(hello)
            with self.subTest(hello=hello):
                with patch.object(
                    storage_broker,
                    "_current_boot_identity_exact",
                    return_value=BootIdentity(1, 2),
                ):
                    with self.assertRaises(StorageBrokerError):
                        validate(
                            hello,
                            lock_set=FakeLocks(self.home, install="shared", storage="shared"),
                            home=self.home,
                            executable=self.executable,
                            workflow_id=self.workflow,
                            generation=7,
                        )

        replacement = self.home / "replacement"
        replacement.write_bytes(b"replacement")
        replacement.chmod(0o700)
        os.replace(replacement, self.executable_path)
        with patch.object(
            storage_broker, "_current_boot_identity_exact", return_value=BootIdentity(1, 2)
        ):
            with self.assertRaisesRegex(StorageBrokerError, "AUTH_FAILED"):
                validate(
                    self._hello(),
                    lock_set=FakeLocks(self.home, install="shared", storage="shared"),
                    home=self.home,
                    executable=self.executable,
                    workflow_id=self.workflow,
                    generation=7,
                )

    def test_validate_hello_cannot_bypass_fresh_kernel_boot_identity(self):
        validate = getattr(storage_broker, "_validate_pre_effect_hello", None)
        arguments = {
            "lock_set": FakeLocks(self.home, install="shared", storage="shared"),
            "home": self.home,
            "executable": self.executable,
            "workflow_id": self.workflow,
            "generation": 7,
        }

        with patch.object(
            storage_broker, "_current_boot_identity_exact", return_value=BootIdentity(1, 2)
        ) as current_boot:
            with self.assertRaises(TypeError):
                validate(self._hello(), expected_boot=BootIdentity(1, 2), **arguments)
        current_boot.assert_not_called()

        with patch.object(
            storage_broker, "_current_boot_identity_exact", return_value=BootIdentity(9, 10)
        ) as current_boot:
            with self.assertRaisesRegex(StorageBrokerError, "AUTH_FAILED"):
                validate(self._hello(), **arguments)
        current_boot.assert_called_once_with()

        with patch.object(
            storage_broker,
            "_current_boot_identity_exact",
            side_effect=StorageBrokerError("AUTH_FAILED", "kern.boottime is unavailable"),
        ) as current_boot:
            with self.assertRaises(StorageBrokerError) as raised:
                validate(self._hello(), **arguments)
        self.assertEqual(raised.exception.code, "AUTH_FAILED")
        current_boot.assert_called_once_with()

    def test_bounded_frame_io_supports_partial_reads_and_rejects_deadline(self):
        read_frame = getattr(storage_broker, "_read_frame_before_deadline", None)
        write_frame = getattr(storage_broker, "_write_frame_before_deadline", None)
        self.assertTrue(callable(read_frame), "bounded frame reader must exist")
        self.assertTrue(callable(write_frame), "bounded frame writer must exist")
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        frame = encode_frame({"a": 1})
        right.sendall(frame[:2])
        right.sendall(frame[2:5])
        right.sendall(frame[5:])
        self.assertEqual(
            read_frame(left, deadline_ns=storage_broker.time.monotonic_ns() + 1_000_000_000),
            {"a": 1},
        )
        write_frame(
            left,
            {"b": 2},
            deadline_ns=storage_broker.time.monotonic_ns() + 1_000_000_000,
        )
        prefix = right.recv(4)
        self.assertEqual(decode_frame(prefix + right.recv(int.from_bytes(prefix, "big"))), {"b": 2})
        with self.assertRaisesRegex(StorageBrokerError, "DEADLINE_EXPIRED"):
            read_frame(left, deadline_ns=storage_broker.time.monotonic_ns() - 1)
        with self.assertRaisesRegex(StorageBrokerError, "DEADLINE_EXPIRED"):
            write_frame(left, {"c": 3}, deadline_ns=storage_broker.time.monotonic_ns() - 1)


class LedgerTests(unittest.TestCase):
    def test_recovery_authority_refuses_nonprivate_parent_without_chmod(self):
        from storage_broker import _new_recovery_authority
        directory = self.home / "storage"
        directory.mkdir(mode=0o755)
        directory.chmod(0o755)
        inode = directory.stat().st_ino
        with self.assertRaises((ValueError, RuntimeError)):
            _new_recovery_authority(self.home)
        self.assertEqual(directory.stat().st_ino, inode)
        self.assertEqual(directory.stat().st_mode & 0o777, 0o755)
        self.assertFalse((directory / "recovery").exists())

    def test_recovery_authority_creates_private_parent_directories(self):
        from storage_broker import _new_recovery_authority
        recovery = _new_recovery_authority(self.home)
        try:
            self.assertEqual((self.home / "storage").stat().st_mode & 0o777, 0o700)
            self.assertEqual((self.home / "storage/recovery").stat().st_mode & 0o777, 0o700)
        finally:
            recovery.close()

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
            BootIdentity(5, 6), recovery, effect_budget_ns=10, cleanup_budget_ns=1,
        )
        self.assertEqual(record.state, LedgerState.OPEN_PREPARED)
        running = ledger.mark_running_before_start_locked(
            self.lock, record.workflow_id, record.generation, broker_pid=1, broker_sid=1,
            broker_pgid=1, owner_connection_nonce="n", owner_peer_audit_sha256="c" * 64,
        )
        self.assertEqual(running.state, LedgerState.OPEN_RUNNING)
        loaded = ledger.load_all_locked(self.lock)
        self.assertEqual(loaded[0].record_sha256, running.record_sha256)

    def test_native_client_refuses_unattested_executable_before_preparing(self):
        ledger = StorageWorkflowLedger(self.home)
        client = StorageBrokerClient(home=self.home, executable=self.executable, ledger=ledger)
        with self.assertRaisesRegex(StorageBrokerError, "AUTH_FAILED"):
            client._run_locked(self.lock, _request(), effect_budget_ns=10, cleanup_budget_ns=1)
        self.assertEqual(ledger.load_all_locked(self.lock), ())

    def test_injected_transport_closes_mutating_workflow_with_reconciliation(self):
        ledger = StorageWorkflowLedger(self.home)
        calls = []

        def transport(request, record):
            calls.append((request, record))
            return {
                "response_kind": "local",
                "response": StorageLocalResponse(1, request.operation, "OK", None, None, 0),
            }

        client = StorageBrokerClient(
            home=self.home, executable=self.executable, ledger=ledger, transport=transport
        )
        result = client._run_locked(
            self.lock,
            _StorageBrokerRequest(
                1, "create", self.home / "image.sparsebundle", None,
                "CORTEX_BRIDGE_SPIKE", "64m", uuid4(), None, True, True,
            ),
            effect_budget_ns=10,
            cleanup_budget_ns=1,
        )
        self.assertEqual(result.state, LedgerState.CLOSED_SUCCESS)
        self.assertTrue(result.reconciliation_required)
        self.assertEqual(result.terminal_code, "OK")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1].state, LedgerState.OPEN_RUNNING)
        self.assertTrue(calls[0][1].command_sha256)

    def test_injected_transport_keeps_read_only_inspect_non_reconciling(self):
        ledger = StorageWorkflowLedger(self.home)

        def transport(request, record):
            return {
                "response_kind": "local",
                "response": StorageLocalResponse(1, request.operation, "OK", None, None, 1),
            }

        client = StorageBrokerClient(
            home=self.home, executable=self.executable, ledger=ledger, transport=transport
        )
        result = client._run_locked(
            self.lock,
            _request("inspect-item"),
            effect_budget_ns=10,
            cleanup_budget_ns=1,
        )
        self.assertEqual(result.state, LedgerState.CLOSED_SUCCESS)
        self.assertFalse(result.reconciliation_required)

    def test_transport_result_must_match_open_workflow(self):
        ledger = StorageWorkflowLedger(self.home)

        def transport(request, record):
            from storage_broker import _success_result
            wrong = _success_result(record, {
                "response_kind": "local",
                "response": StorageLocalResponse(1, request.operation, "OK", None, None, 0),
            })
            return ClosedReadyResult(
                uuid4(), wrong.generation, wrong.outcome, wrong.code, wrong.response,
                wrong.command_sha256, wrong.result_sha256, wrong.closed_ready_sha256,
                wrong.child_reaped, wrong.group_absent, wrong.native_cleanup_proven,
                wrong.reconciliation_required,
            )

        client = StorageBrokerClient(
            home=self.home, executable=self.executable, ledger=ledger, transport=transport
        )
        with self.assertRaisesRegex(StorageBrokerError, "PROTOCOL_ERROR"):
            client._run_locked(self.lock, _request(), effect_budget_ns=10, cleanup_budget_ns=1)
        record = ledger.load_all_locked(self.lock)[0]
        self.assertEqual(record.state, LedgerState.OPEN_UNRESOLVED)

    def test_mounted_image_probe_closes_read_only_workflow(self):
        ledger = StorageWorkflowLedger(self.home)
        image_path = self.home / "image.sparsebundle"
        mount_path = self.home / "mnt"
        volume_uuid = uuid4()
        encryption_uuid = uuid4()
        image_identity = (DarwinU32(7), 8)
        mount_identity = (DarwinU32(9), 10, DarwinU32(11), DarwinU32(12))
        seen_requests = []

        def transport(request, record):
            from storage_broker import request_sha256
            seen_requests.append(request)
            proof = MountedImageProof(
                mount_path=mount_path,
                image_dev_u32=image_identity[0], image_ino=image_identity[1],
                mount_dev_u32=mount_identity[0], mount_ino=mount_identity[1],
                mount_fsid0_u32=mount_identity[2], mount_fsid1_u32=mount_identity[3],
                volume_name="CORTEX_BRIDGE_2026_09", volume_uuid=volume_uuid,
                encryption_uuid=encryption_uuid, mapping_count=1,
                filesystem_type="apfs", writable=True, encrypted=True,
                request_sha256=request_sha256(request),
            )
            return {"response_kind": "mounted_image_proof", "response": proof}

        client = StorageBrokerClient(
            home=self.home, executable=self.executable, ledger=ledger, transport=transport
        )
        proof = client._probe_mounted_image_locked(
            self.lock,
            image_path=image_path,
            mount_path=mount_path,
            expected_volume_name="CORTEX_BRIDGE_2026_09",
            expected_volume_uuid=volume_uuid,
            expected_encryption_uuid=encryption_uuid,
            image_identity=image_identity,
            mount_identity=mount_identity,
            expected_mapping_count=1,
            effect_budget_ns=10,
        )
        self.assertEqual(proof.request_sha256, request_sha256(seen_requests[0]))
        record = ledger.load_all_locked(self.lock)[0]
        self.assertEqual(record.state, LedgerState.CLOSED_SUCCESS)
        self.assertFalse(record.reconciliation_required)


if __name__ == "__main__":
    unittest.main()
