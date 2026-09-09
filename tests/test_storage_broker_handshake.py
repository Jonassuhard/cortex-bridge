from __future__ import annotations

import hashlib
import json
import os
import socket
import shutil
import struct
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from uuid import uuid4

import storage_broker
from storage_lock import open_storage_lock_set


REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "native" / "macos" / "disk_image_keychain.swift"
PROFILE = REPO / "native" / "build-profiles" / "storage-broker-v1.json"
EXACT_ENV = {
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "LANG": "C",
    "LC_ALL": "C",
}


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    output = bytearray()
    while len(output) < count:
        chunk = sock.recv(count - len(output))
        if not chunk:
            raise EOFError("broker closed a truncated frame")
        output.extend(chunk)
    return bytes(output)


def _read_frame(sock: socket.socket) -> dict[str, object]:
    prefix = _recv_exact(sock, 4)
    length = int.from_bytes(prefix, "big")
    return storage_broker.decode_frame(prefix + _recv_exact(sock, length))


class SwiftProductionHelloTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.uname().sysname != "Darwin":
            raise unittest.SkipTest("production broker handshake is macOS-only")
        cls.build = tempfile.TemporaryDirectory(prefix="cortex-s3-handshake-build-")
        cls.binary = Path(cls.build.name) / "cortex-storage-broker"
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        command = ["/Library/Developer/CommandLineTools/usr/bin/swiftc"]
        command.extend(profile["swiftc"])
        command.extend([str(SOURCE), "-o", str(cls.binary)])
        for framework in profile["frameworks"]:
            command.extend(["-framework", framework])
        environment = os.environ.copy()
        environment.update(
            {
                "SDKROOT": "/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk",
                "MACOSX_DEPLOYMENT_TARGET": "26.5",
                "CLANG_MODULE_CACHE_PATH": "/tmp/cortex-s3-handshake-clang-cache",
                "SWIFT_MODULECACHE_PATH": "/tmp/cortex-s3-handshake-swift-cache",
            }
        )
        completed = subprocess.run(command, env=environment, capture_output=True, text=True)
        if completed.returncode != 0:
            raise AssertionError(
                f"production profile compile failed ({completed.returncode})\n"
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            )

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.runtime = tempfile.TemporaryDirectory(prefix="cortex-s3-handshake-")
        self.addCleanup(self.runtime.cleanup)
        self.workflow = uuid4()
        self.processes: list[subprocess.Popen[bytes]] = []
        self.sockets: list[socket.socket] = []
        self.early_client: socket.socket | None = None
        self.addCleanup(self._cleanup_processes)

    def _cleanup_processes(self):
        for sock in self.sockets:
            sock.close()
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

    def _launch(self, *, environment=None, capability_fd_factory=None, connect_before_spawn=False,
                generation=7, prepare_listener=None, recovery_bytes=bytes(range(32))):
        root = Path(self.runtime.name)
        socket_path = root / f"broker-{len(self.processes)}.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        os.chmod(socket_path, 0o600)
        listener.listen(4)
        if prepare_listener is not None:
            prepare_listener(socket_path)
        if connect_before_spawn:
            self.early_client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.early_client.settimeout(2.5)
            self.early_client.connect(str(socket_path))
            self.sockets.append(self.early_client)

        capability_parent, capability_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        if capability_fd_factory is not None:
            capability_child.close()
            capability_child = capability_fd_factory(listener)
        recovery_read, recovery_write = os.pipe()
        os.write(recovery_write, recovery_bytes)
        os.close(recovery_write)

        argv = [
            str(self.binary),
            "--broker-fd", str(listener.fileno()),
            "--start-capability-fd", str(capability_child.fileno()),
            "--recovery-authority-fd", str(recovery_read),
            "--workflow-id", str(self.workflow),
            "--generation", str(generation),
        ]
        process = subprocess.Popen(
            argv,
            env=EXACT_ENV if environment is None else environment,
            pass_fds=(listener.fileno(), capability_child.fileno(), recovery_read),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        self.processes.append(process)
        listener.close()
        capability_child.close()
        os.close(recovery_read)
        self.sockets.append(capability_parent)
        self.capability_parent = capability_parent
        return process, socket_path

    def _start_with_grant(self, *, grant_changes=None, payload_changes=None, request_changes=None, send_grant=True,
                          wire_transform=None):
        process, socket_path = self._launch()
        client = self._connect(socket_path)
        hello = self._hello_or_fail(client, process)
        request = dict(schema_version=1, operation="inspect-item",
            image_path=str(Path(self.runtime.name) / "never-created.sparsebundle"),
            mount_path=None, volume_name=None, size=None,
            transaction_id=str(self.workflow), expected_encryption_uuid=str(self.workflow),
            disposable=True, cleanup_approved=False)
        request.update(request_changes or {})
        canonical = storage_broker.canonical_json(request)
        request_hash = hashlib.sha256(b"CORTEX-S3\0REQUEST\0V1\0" + canonical).hexdigest()
        grant = dict(version=1, type="START_GRANT", workflow_id=str(self.workflow),
            generation=7, record_sha256="a" * 64, request_sha256=request_hash,
            operation=request["operation"], effect_budget_ns=1_000_000, cleanup_budget_ns=1,
            boot_seconds=hello["payload"]["boot_seconds"],
            boot_microseconds=hello["payload"]["boot_microseconds"],
            connection_nonce=hello["connection_nonce"],
            peer_audit_sha256=hello["payload"]["peer_audit_sha256"])
        grant.update(grant_changes or {})
        if send_grant:
            wire = storage_broker.encode_frame(grant)
            self.capability_parent.sendall(wire if wire_transform is None else wire_transform(wire))
        self.capability_parent.close()
        payload = dict(request=request, request_sha256=request_hash,
            effect_budget_ns=1_000_000, cleanup_budget_ns=1)
        payload.update(payload_changes or {})
        client.sendall(storage_broker.encode_frame(dict(version=1, type="START",
            workflow_id=str(self.workflow), generation=7,
            connection_nonce=hello["connection_nonce"], cursor=0, payload=payload)))
        response = _read_frame(client)
        self.assertEqual(response["type"], "PROTOCOL_ERROR")
        self.assertEqual(process.wait(timeout=3), 64)
        self.assertFalse(Path(request["image_path"]).exists())
        return response["payload"]["code"]

    def test_valid_private_grant_reaches_unimplemented_effect_boundary(self):
        # A blanket AUTH_FAILED must not masquerade as implemented grant handling.
        # INVALID_STATE still means no effect/STARTED; this is not execution acceptance.
        self.assertEqual(self._start_with_grant(), "INVALID_STATE")

    def test_native_rejects_matching_grants_with_invalid_budget_policy(self):
        for effect, cleanup, expected in (
            (1, 1, "INVALID_STATE"), (40_000_000_000, 12_000_000_000, "INVALID_STATE"),
            (0, 1, "AUTH_FAILED"), (1, 0, "AUTH_FAILED"),
            (40_000_000_001, 1, "AUTH_FAILED"), (1, 12_000_000_001, "AUTH_FAILED"),
            (2**64 - 1, 1, "AUTH_FAILED"), (1, 2**64 - 1, "AUTH_FAILED"),
            (True, 1, "AUTH_FAILED"), (1, True, "AUTH_FAILED"),
        ):
            with self.subTest(effect=effect, cleanup=cleanup):
                budgets = {"effect_budget_ns": effect, "cleanup_budget_ns": cleanup}
                self.assertEqual(self._start_with_grant(grant_changes=budgets, payload_changes=budgets), expected)

    def test_authorized_start_rejects_invalid_public_request_schema(self):
        for changes in (
            {"schema_version": True}, {"extra": "ignored"}, {"disposable": 1},
            {"cleanup_approved": 0}, {"transaction_id": "not-a-uuid"},
            {"transaction_id": "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"},
            {"expected_encryption_uuid": None}, {"expected_encryption_uuid": "bad"},
            {"image_path": "/tmp/../image.sparsebundle"}, {"image_path": "/tmp//image"},
            {"image_path": "/tmp/image\n"}, {"image_path": "relative"},
            {"size": "64m"}, {"volume_name": "unexpected"}, {"mount_path": "/tmp/mount"},
            {"operation": "delete-disposable-item", "cleanup_approved": False},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self._start_with_grant(request_changes=changes), "INVALID_FRAME")

    def test_authorized_create_schema_does_not_require_legacy_mount_fields(self):
        self.assertEqual(self._start_with_grant(request_changes={
            "operation": "create", "expected_encryption_uuid": None,
            "size": "64m", "volume_name": "CORTEX_BRIDGE_SPIKE",
        }), "INVALID_STATE")
        for changes in ({"size": "256g"}, {"volume_name": "wrong"},
                        {"expected_encryption_uuid": str(uuid4())}):
            with self.subTest(changes=changes):
                self.assertEqual(self._start_with_grant(request_changes={
                    "operation": "create", "expected_encryption_uuid": None,
                    "size": "64m", "volume_name": "CORTEX_BRIDGE_SPIKE", **changes,
                }), "INVALID_FRAME")

    def test_noncreate_schema_has_no_create_parameters(self):
        for operation in ("mount", "detach"):
            with self.subTest(operation=operation):
                request = {"operation": operation, "mount_path": "/tmp/managed-mount"}
                self.assertEqual(self._start_with_grant(request_changes=request), "INVALID_STATE")
                self.assertEqual(self._start_with_grant(request_changes={
                    **request, "volume_name": "CORTEX_BRIDGE_SPIKE",
                }), "INVALID_FRAME")
        self.assertEqual(self._start_with_grant(request_changes={
            "operation": "delete-disposable-item", "cleanup_approved": True,
        }), "INVALID_STATE")
        self.assertEqual(self._start_with_grant(request_changes={
            "operation": "delete-disposable-item", "cleanup_approved": True, "disposable": False,
        }), "INVALID_FRAME")

    def test_private_grant_must_match_owner_request_and_budgets(self):
        for change in ({"connection_nonce": "f" * 64}, {"peer_audit_sha256": "f" * 64},
                       {"generation": 8}, {"workflow_id": str(uuid4())},
                       {"boot_seconds": 1}, {"boot_microseconds": 1_000_000},
                       {"request_sha256": "f" * 64}, {"operation": "mount"},
                       {"effect_budget_ns": 2_000_000}, {"cleanup_budget_ns": 2},
                       {"record_sha256": "invalid"}, {"version": True},
                       {"extra": 1}, {"type": "RECOVER"}):
            with self.subTest(change=change):
                self.assertEqual(self._start_with_grant(grant_changes=change), "AUTH_FAILED")

    def test_start_cannot_relabel_request_or_add_control_fields(self):
        for change in ({"request_sha256": "f" * 64}, {"request": {}},
                       {"effect_budget_ns": True}, {"extra": 1}):
            with self.subTest(change=change):
                self.assertEqual(self._start_with_grant(payload_changes=change), "AUTH_FAILED")

    def test_eof_capability_cannot_authorize_start(self):
        self.assertEqual(self._start_with_grant(send_grant=False), "AUTH_FAILED")

    def test_private_grant_rejects_duplicate_and_truncated_frames(self):
        for name, transform in (("duplicate", lambda wire: wire + wire),
                                ("trailing-byte", lambda wire: wire + b"x"),
                                ("partial", lambda wire: wire[:-1]),
                                ("oversized", lambda wire: (16 * 1024 + 1).to_bytes(4, "big")),
                                ("duplicate-key", lambda wire: (len(wire) + 8).to_bytes(4, "big")
                                 + b'{"version":1,' + wire[5:])):
            with self.subTest(name=name):
                self.assertEqual(self._start_with_grant(wire_transform=transform), "AUTH_FAILED")

    def test_matching_fields_cannot_bypass_digest_or_budget_validation(self):
        for change in ({"request_sha256": "f" * 64}, {"effect_budget_ns": 0},
                       {"effect_budget_ns": 40_000_000_001}, {"effect_budget_ns": True},
                       {"cleanup_budget_ns": 12_000_000_001}, {"cleanup_budget_ns": True}):
            with self.subTest(change=change):
                self.assertEqual(self._start_with_grant(grant_changes=change,
                                                       payload_changes=change), "AUTH_FAILED")

    def test_python_durable_grant_is_consumed_by_production_swift(self):
        # Cross-language authorization only: launch is the test fixture, and the
        # recovery-root lifecycle/effect dispatch are not accepted by this test.
        home = Path(self.runtime.name).resolve()
        executable_fd = os.open(self.binary, os.O_RDONLY)
        self.addCleanup(os.close, executable_fd)
        info = os.fstat(executable_fd)
        executable = storage_broker.AttestedBrokerExecutable(self.binary, executable_fd,
            storage_broker.DarwinU32(info.st_dev & 0xffffffff), info.st_ino, info.st_uid,
            info.st_mode & 0o777, hashlib.sha256(self.binary.read_bytes()).hexdigest(), "b" * 64)
        recovery = storage_broker._new_recovery_authority(home)
        self.addCleanup(recovery.close)
        request = storage_broker._StorageBrokerRequest(1, "inspect-item",
            home / "never-created.sparsebundle", None, None, None,
            self.workflow, str(self.workflow), True, False)
        with open_storage_lock_set(home, install_mode="shared", storage_mode="exclusive") as locks:
            ledger = storage_broker.StorageWorkflowLedger(home)
            records = []
            def prepare(socket_path):
                listener_info = socket_path.lstat()
                identity = storage_broker.BrokerSocketIdentity(socket_path,
                    storage_broker.DarwinU32(listener_info.st_dev & 0xffffffff),
                    listener_info.st_ino, listener_info.st_uid, 0o600)
                record = ledger.prepare_locked(locks, request, executable, identity,
                    storage_broker._current_boot_identity_exact(), recovery,
                    effect_budget_ns=1_000_000, cleanup_budget_ns=1)
                self.workflow = record.workflow_id
                records.append(record)
            process, socket_path = self._launch(generation=1, prepare_listener=prepare,
                                                recovery_bytes=bytes(recovery.root))
            record = records[0]
            client = self._connect(socket_path)
            hello = self._hello_or_fail(client, process)
            record = ledger.mark_running_before_start_locked(locks,
                record.workflow_id, record.generation, broker_pid=process.pid,
                broker_sid=os.getsid(process.pid), broker_pgid=os.getpgid(process.pid),
                owner_connection_nonce=hello["connection_nonce"],
                owner_peer_audit_sha256=hello["payload"]["peer_audit_sha256"])
            storage_broker._StartGrantChannel(self.capability_parent).send_locked(locks,
                ledger=ledger, record=record, executable=executable, hello=hello)
            client.sendall(storage_broker.encode_frame(dict(version=1, type="START",
                workflow_id=str(record.workflow_id), generation=record.generation,
                connection_nonce=hello["connection_nonce"], cursor=0,
                payload=dict(request=storage_broker._request_projection(request),
                    request_sha256=record.request_sha256,
                    effect_budget_ns=1_000_000, cleanup_budget_ns=1))))
            self.assertEqual(_read_frame(client)["payload"], {"code": "INVALID_STATE"})
            self.assertEqual(process.wait(timeout=3), 64)
            self.assertFalse(request.image_path.exists())

    def _launch_owner_fixture(self, binary=None):
        owner_type = getattr(storage_broker, "_BrokerLaunchOwner", None)
        self.assertTrue(callable(owner_type), "production launch/session owner is missing")
        path = self.binary if binary is None else binary
        fd = os.open(path, os.O_RDONLY)
        self.addCleanup(os.close, fd)
        info = os.fstat(fd)
        executable = storage_broker.AttestedBrokerExecutable(path, fd,
            storage_broker.DarwinU32(info.st_dev & 0xffffffff), info.st_ino, info.st_uid,
            info.st_mode & 0o777, hashlib.sha256(path.read_bytes()).hexdigest(), "b" * 64)
        home = Path(self.runtime.name).resolve()
        ledger = storage_broker.StorageWorkflowLedger(home)
        owner = owner_type(home=home, executable=executable, ledger=ledger)
        def close_fixture():
            owner.close_channel()
            if owner.process is not None:
                owner.process.wait(timeout=3)
            if owner.socket_directory is not None:
                shutil.rmtree(owner.socket_directory)
        self.addCleanup(close_fixture)
        request = storage_broker._StorageBrokerRequest(1, "inspect-item", home / "unused.sparsebundle",
            None, None, None, uuid4(), str(uuid4()), True, False)
        return home, ledger, owner, request

    def test_production_launch_owner_persists_real_identity_before_start(self):
        home, ledger, owner, request = self._launch_owner_fixture()
        with open_storage_lock_set(home, install_mode="shared", storage_mode="exclusive") as locks:
            record = owner.start_locked(locks, request, effect_budget_ns=1_000_000, cleanup_budget_ns=1)
            self.processes.append(owner.process)
            self.assertEqual(record.state, storage_broker.LedgerState.OPEN_RUNNING)
            self.assertEqual(record.broker_pid, owner.process.pid)
            self.assertEqual(record.broker_sid, owner.process.pid)
            self.assertEqual(record.broker_pgid, owner.process.pid)
            self.assertEqual(ledger.load_all_locked(locks), (record,))
            self.assertEqual(record.socket.path.lstat().st_mode & 0o777, 0o600)
            response = owner.receive_frame()
            self.assertEqual(response["type"], "PROTOCOL_ERROR")
            self.assertEqual(response["payload"], {"code": "INVALID_STATE"})
            self.assertEqual(owner.process.wait(timeout=3), 64)
            self.assertFalse(request.image_path.exists())
            with self.assertRaisesRegex(storage_broker.StorageBrokerError, "REPLAY"):
                owner.start_locked(locks, request, effect_budget_ns=1_000_000, cleanup_budget_ns=1)

    def test_exec_failure_closes_only_prepared_record(self):
        bad_binary = Path(self.runtime.name) / "invalid-executable"
        bad_binary.write_bytes(b"not an executable\n")
        bad_binary.chmod(0o700)
        home, ledger, owner, request = self._launch_owner_fixture(bad_binary)
        with open_storage_lock_set(home, install_mode="shared", storage_mode="exclusive") as locks:
            with self.assertRaisesRegex(storage_broker.StorageBrokerError, "BROKER_UNAVAILABLE"):
                owner.start_locked(locks, request, effect_budget_ns=1_000_000, cleanup_budget_ns=1)
            record, = ledger.load_all_locked(locks)
            self.assertEqual(record.state, storage_broker.LedgerState.CLOSED_FAILURE)
            self.assertIsNone(record.broker_pid)
            self.assertIsNone(owner.process)
            self.assertFalse(request.image_path.exists())

    def test_default_client_launches_native_and_keeps_unacknowledged_run_unresolved(self):
        home, ledger, fixture, request = self._launch_owner_fixture()
        client = storage_broker.StorageBrokerClient(home=home, executable=fixture.executable, ledger=ledger)
        with open_storage_lock_set(home, install_mode="shared", storage_mode="exclusive") as locks:
            with self.assertRaisesRegex(storage_broker.StorageBrokerError, "INVALID_STATE") as raised:
                client._run_locked(locks, request, effect_budget_ns=1_000_000, cleanup_budget_ns=1)
            self.assertEqual(raised.exception.code, "PROTOCOL_ERROR")
            record, = ledger.load_all_locked(locks)
            self.addCleanup(shutil.rmtree, record.socket.path.parent)
            self.assertEqual(record.state, storage_broker.LedgerState.OPEN_UNRESOLVED)
            self.assertNotEqual(record.broker_pid, os.getpid())
            self.assertIsNotNone(record.broker_pid)
            self.assertFalse(request.image_path.exists())

    def test_inherited_listener_peer_pid_after_hello_is_accepting_child(self):
        # Observe after acceptance/HELLO, not immediately after connect.
        process, path = self._launch()
        client = self._connect(path)
        self._hello_or_fail(client, process)
        self.assertEqual(client.getsockopt(0, 2), process.pid)
        self.assertNotEqual(client.getsockopt(0, 2), os.getpid())
        client.close()
        self.assertEqual(process.wait(timeout=3), 0)

    def _named_connected_capability(self, _broker_listener: socket.socket) -> socket.socket:
        root = Path(self.runtime.name)
        path = root / f"named-capability-{len(self.sockets)}.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(path))
        listener.listen(1)
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(path))
        accepted, _ = listener.accept()
        self.sockets.extend([listener, client])
        return accepted

    def test_preconnected_owner_is_retained_and_receives_hello(self):
        process, _ = self._launch(connect_before_spawn=True)
        assert self.early_client is not None
        hello = self._hello_or_fail(self.early_client, process)
        self.assertEqual(hello["type"], "HELLO")
        self.early_client.close()
        self.assertEqual(process.wait(timeout=3), 0)

    def test_invalid_recovery_root_rejected_before_hello(self):
        for size in (0, 31, 33, 64):
            with self.subTest(size=size):
                process, _ = self._launch(connect_before_spawn=True,
                                           recovery_bytes=bytes(range(size)))
                self.assertEqual(process.wait(timeout=3), 64)
                try:
                    payload = self.early_client.recv(1)
                except ConnectionResetError:
                    payload = b""
                self.assertEqual(payload, b"")

    def _connect(self, socket_path: Path) -> socket.socket:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(2.5)
        deadline = time.monotonic() + 2.0
        while True:
            try:
                client.connect(str(socket_path))
                self.sockets.append(client)
                return client
            except (ConnectionRefusedError, FileNotFoundError):
                if time.monotonic() >= deadline:
                    self.fail("production broker did not accept its retained listener")
                time.sleep(0.01)

    def _hello_or_fail(
        self, client: socket.socket, process: subprocess.Popen[bytes]
    ) -> dict[str, object]:
        try:
            return _read_frame(client)
        except (EOFError, TimeoutError, socket.timeout) as exc:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            stderr = b"" if process.stderr is None else process.stderr.read()
            self.fail(
                f"production broker did not emit HELLO: {exc}; "
                f"exit={process.poll()}; stderr={stderr.decode('utf-8', 'replace')}"
            )

    def test_production_broker_emits_real_exact_authenticated_hello(self):
        process, socket_path = self._launch()
        client = self._connect(socket_path)
        hello = self._hello_or_fail(client, process)

        self.assertEqual(
            set(hello),
            {"version", "type", "workflow_id", "generation", "connection_nonce", "cursor", "payload"},
        )
        self.assertEqual(hello["version"], 1)
        self.assertEqual(hello["type"], "HELLO")
        self.assertEqual(hello["workflow_id"], str(self.workflow))
        self.assertEqual(hello["generation"], 7)
        self.assertEqual(hello["cursor"], 0)
        self.assertRegex(hello["connection_nonce"], r"^[0-9a-f]{64}$")
        self.assertNotEqual(hello["connection_nonce"], "0" * 64)
        payload = hello["payload"]
        self.assertIsInstance(payload, dict)
        self.assertEqual(
            set(payload),
            {
                "broker_dev_u32", "broker_ino", "broker_uid", "broker_mode",
                "broker_sha256", "boot_seconds", "boot_microseconds", "peer_audit_sha256",
            },
        )
        self.assertNotIn("broker_pid", payload)

        binary_bytes = self.binary.read_bytes()
        details = self.binary.stat()
        self.assertEqual(payload["broker_dev_u32"], details.st_dev & 0xFFFFFFFF)
        self.assertEqual(payload["broker_ino"], details.st_ino)
        self.assertEqual(payload["broker_uid"], details.st_uid)
        self.assertEqual(payload["broker_mode"], details.st_mode & 0o777)
        self.assertEqual(payload["broker_sha256"], hashlib.sha256(binary_bytes).hexdigest())
        self.assertGreater(payload["boot_seconds"], 0)
        self.assertGreaterEqual(payload["boot_microseconds"], 0)
        self.assertLess(payload["boot_microseconds"], 1_000_000)
        exact_boot = getattr(storage_broker, "_current_boot_identity_exact", None)
        self.assertTrue(callable(exact_boot), "exact kern.boottime reader must exist")
        self.assertEqual(
            exact_boot(),
            storage_broker.BootIdentity(payload["boot_seconds"], payload["boot_microseconds"]),
        )

        token_left, token_right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(token_left.close)
        self.addCleanup(token_right.close)
        raw_token = token_left.getsockopt(0, 0x006, 32)
        token = struct.unpack("=8I", raw_token)
        projection = (
            b'{"audit_session_id":%d,"effective_gid":%d,"effective_uid":%d,'
            b'"pid":%d,"pid_version":%d}'
            % (token[6], token[2], token[1], token[5], token[7])
        )
        self.assertEqual(payload["peer_audit_sha256"], hashlib.sha256(projection).hexdigest())

        client.close()
        self.assertEqual(process.wait(timeout=3), 0)

    def test_broker_rejects_extra_environment_before_accept(self):
        process, _ = self._launch(environment={**EXACT_ENV, "HOME": self.runtime.name})
        self.assertEqual(process.wait(timeout=3), 64)

    def test_broker_rejects_launcher_supplied_foundation_shaped_environment(self):
        plausible = f"0x{os.geteuid():X}:0x0:0x1"
        process, _ = self._launch(
            environment={**EXACT_ENV, "__CF_USER_TEXT_ENCODING": plausible}
        )
        self.assertEqual(process.wait(timeout=3), 64)

    def test_broker_rejects_wrong_descriptor_role_before_accept(self):
        process, _ = self._launch(capability_fd_factory=lambda listener: socket.socket(fileno=os.dup(listener.fileno())))
        self.assertEqual(process.wait(timeout=3), 64)

    def test_broker_rejects_connected_named_unix_stream_as_start_capability(self):
        process, _ = self._launch(
            capability_fd_factory=self._named_connected_capability,
            connect_before_spawn=True,
        )
        assert self.early_client is not None
        self.early_client.close()
        self.assertEqual(process.wait(timeout=3), 64)

    def test_broker_rejects_oversize_and_partial_frames_without_started(self):
        process, socket_path = self._launch()
        client = self._connect(socket_path)
        self._hello_or_fail(client, process)
        client.sendall((16 * 1024 + 1).to_bytes(4, "big"))
        self.assertNotEqual(process.wait(timeout=3), 0)

        process, socket_path = self._launch()
        client = self._connect(socket_path)
        self._hello_or_fail(client, process)
        started = time.monotonic()
        client.sendall(b"\x00\x00")
        self.assertNotEqual(process.wait(timeout=3), 0)
        self.assertLess(time.monotonic() - started, 2.75)

    def test_broker_validates_envelope_before_fail_closed_control_rejection(self):
        process, socket_path = self._launch()
        client = self._connect(socket_path)
        hello = self._hello_or_fail(client, process)
        frame = storage_broker.encode_frame(
            {
                "version": 1,
                "type": "START",
                "workflow_id": str(self.workflow),
                "generation": 7,
                "connection_nonce": hello["connection_nonce"],
                "cursor": 0,
                "payload": {},
            }
        )
        client.sendall(frame)
        response = _read_frame(client)
        self.assertEqual(response["type"], "PROTOCOL_ERROR")
        self.assertEqual(response["payload"], {"code": "AUTH_FAILED"})
        self.assertNotEqual(response["type"], "STARTED")
        self.assertNotEqual(process.wait(timeout=3), 0)

        for changed_key, changed_value in (
            ("version", 2),
            ("workflow_id", str(uuid4())),
            ("generation", 8),
            ("connection_nonce", "00" * 32),
            ("cursor", 1),
        ):
            with self.subTest(changed_key=changed_key):
                process, socket_path = self._launch()
                client = self._connect(socket_path)
                hello = self._hello_or_fail(client, process)
                envelope = {
                    "version": 1,
                    "type": "START",
                    "workflow_id": str(self.workflow),
                    "generation": 7,
                    "connection_nonce": hello["connection_nonce"],
                    "cursor": 0,
                    "payload": {},
                }
                envelope[changed_key] = changed_value
                client.sendall(storage_broker.encode_frame(envelope))
                response = _read_frame(client)
                self.assertEqual(response["type"], "PROTOCOL_ERROR")
                self.assertNotEqual(response["type"], "STARTED")
                self.assertNotEqual(process.wait(timeout=3), 0)

    def test_production_broker_rejects_raw_noncanonical_and_invalid_json_frames(self):
        def envelope(
            nonce: str,
            *,
            cursor: str = "0",
            generation: str = "7",
            type_value: str = "START",
            extra: str = "",
            wrong_order: bool = False,
            spaced: bool = False,
        ) -> bytes:
            separator = ": " if spaced else ":"
            if wrong_order:
                text = (
                    f'{{"connection_nonce"{separator}"{nonce}","cursor"{separator}{cursor},'
                    f'"generation"{separator}{generation},"payload"{separator}{{}},'
                    f'"version"{separator}1,"type"{separator}"{type_value}",'
                    f'"workflow_id"{separator}"{self.workflow}"}}'
                )
            else:
                text = (
                    f'{{"connection_nonce"{separator}"{nonce}","cursor"{separator}{cursor},'
                    f'{extra}"generation"{separator}{generation},"payload"{separator}{{}},'
                    f'"type"{separator}"{type_value}","version"{separator}1,'
                    f'"workflow_id"{separator}"{self.workflow}"}}'
                )
            return text.encode("ascii")

        mutations = {
            "duplicate-key": (
                lambda nonce: envelope(nonce, extra='"cursor":0,'),
                None,
            ),
            "unknown-key": (
                lambda nonce: envelope(nonce, extra='"extra":0,'),
                "INVALID_FRAME",
            ),
            "wrong-key-order": (lambda nonce: envelope(nonce, wrong_order=True), None),
            "whitespace": (lambda nonce: envelope(nonce, spaced=True), None),
            "noncanonical-escape": (
                lambda nonce: envelope(nonce, type_value="\\u0053TART"),
                None,
            ),
            "negative": (lambda nonce: envelope(nonce, cursor="-1"), None),
            "fraction": (lambda nonce: envelope(nonce, cursor="0.0"), None),
            "uint64-overflow": (
                lambda nonce: envelope(nonce, generation="18446744073709551616"),
                None,
            ),
        }

        for name, (build_raw, expected_code) in mutations.items():
            with self.subTest(name=name):
                process, socket_path = self._launch()
                client = self._connect(socket_path)
                hello = self._hello_or_fail(client, process)
                raw = build_raw(str(hello["connection_nonce"]))
                client.sendall(len(raw).to_bytes(4, "big") + raw)
                if expected_code is None:
                    self.assertEqual(
                        client.recv(1), b"",
                        "codec-invalid bytes must be rejected before semantic dispatch",
                    )
                else:
                    response = _read_frame(client)
                    self.assertEqual(response["type"], "PROTOCOL_ERROR")
                    self.assertEqual(response["payload"], {"code": expected_code})
                    self.assertNotEqual(response["type"], "STARTED")
                self.assertEqual(process.wait(timeout=3), 64)


if __name__ == "__main__":
    unittest.main()
