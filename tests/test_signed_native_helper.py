import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import importlib.util
import select
import sys
import fcntl
import time
import signal
import dataclasses
import json
import sqlite3
import uuid
from unittest.mock import patch

import native_helpers


class SignedNativeHelperTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(getattr(native_helpers, "attest_helper", None)),
                        "Signed manifest-bound helper attestation is missing")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        (self.home / "app/bin").mkdir(parents=True, mode=0o700)
        (self.home / "app").chmod(0o700)
        self.binary = self.home / "app/bin/process-release"
        source = Path(__file__).resolve().parents[1] / "native/macos/process_release.swift"
        subprocess.run(["xcrun", "swiftc", str(source), "-o", str(self.binary)],
                       check=True, capture_output=True, timeout=60)
        self.binary.chmod(0o700)
        subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(self.binary)],
                       check=True, capture_output=True, timeout=10)
        signature = subprocess.run(["/usr/bin/codesign", "-d", "--verbose=4", str(self.binary)],
                                   check=True, capture_output=True, text=True, timeout=5)
        cdhash = re.search(r"^CDHash=([0-9a-f]+)$", signature.stderr, re.M).group(1)
        details = self.binary.stat()
        self.record = dict(target="app/bin/process-release", source="native/macos/process_release.swift",
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), build_profile_sha256="a"*64,
            sha256=hashlib.sha256(self.binary.read_bytes()).hexdigest(), cdhash=cdhash,
            dev_u32=details.st_dev & 0xffffffff, ino=details.st_ino, uid=details.st_uid, mode=0o700)
        self.manifest = {"native_helpers": {"process-release": self.record}}

    def attest(self):
        handle = native_helpers.attest_helper("process-release", self.manifest, home=self.home)
        self.addCleanup(handle.close)
        return handle

    def test_signed_helper_revalidates_and_closed_handle_refuses_spawn(self):
        handle = self.attest()
        self.assertEqual(handle.revalidate_for_spawn(), self.binary)
        self.assertEqual(os.fstat(handle.fd).st_ino, self.binary.stat().st_ino)
        handle.close()
        with self.assertRaises(native_helpers.NativeHelperAttestationError):
            handle.revalidate_for_spawn()

    def test_replaced_same_bytes_inode_is_refused(self):
        handle = self.attest()
        data = self.binary.read_bytes()
        self.binary.rename(self.binary.with_suffix(".old"))
        self.binary.write_bytes(data)
        self.binary.chmod(0o700)
        with self.assertRaises(native_helpers.NativeHelperAttestationError):
            handle.revalidate_for_spawn()

    def test_changed_bytes_or_manifest_signature_is_refused(self):
        handle = self.attest()
        with self.binary.open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaises(native_helpers.NativeHelperAttestationError):
            handle.revalidate_for_spawn()
        self.record["sha256"] = hashlib.sha256(self.binary.read_bytes()).hexdigest()
        self.record["cdhash"] = "0"*40
        with self.assertRaises(native_helpers.NativeHelperAttestationError):
            self.attest()

    def test_intermediate_symlink_is_refused(self):
        (self.home / "app").rename(self.home / "actual")
        (self.home / "app").symlink_to(self.home / "actual", target_is_directory=True)
        with self.assertRaises(native_helpers.NativeHelperAttestationError):
            self.attest()

    def test_valid_binary_with_wrong_manifest_cdhash_is_refused(self):
        self.record["cdhash"] = "0"*40
        with self.assertRaises(native_helpers.NativeHelperAttestationError):
            self.attest()

    def test_permission_change_is_refused_without_automatic_repair(self):
        handle = self.attest()
        self.binary.chmod(0o755)
        with self.assertRaises(native_helpers.NativeHelperAttestationError):
            handle.revalidate_for_spawn()
        self.assertEqual(self.binary.stat().st_mode & 0o777, 0o755)

    def test_attested_spawn_uses_retained_cwd_and_waits_for_release(self):
        self.assertIsNotNone(importlib.util.find_spec("executor.process_spawn"),
                             "Descriptor process spawn is missing")
        from executor.process_spawn import spawn_attested_at
        handle = self.attest()
        workspace = self.home / "workspace"
        workspace.mkdir()
        (workspace / "value").write_text("original")
        cwd = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY)
        workspace.rename(self.home / "retained")
        workspace.mkdir()
        (workspace / "value").write_text("replacement")
        release_r, release_w = os.pipe()
        output_r, output_w = os.pipe()
        null = os.open("/dev/null", os.O_RDONLY)
        unrelated = fcntl.fcntl(null, fcntl.F_DUPFD, 128)
        os.set_inheritable(unrelated, True)
        pid = None
        try:
            pid = spawn_attested_at(handle, argv=[str(handle.path), "--release-fd", "7", "--",
                    sys.executable, "-c", f"import os\nfrom pathlib import Path\ntry:\n os.fstat({unrelated})\n print('LEAKED')\nexcept OSError:\n print(Path('value').read_text())"],
                cwd_fd=cwd, env={"PATH": "/usr/bin:/bin", "LANG": "C"},
                fd_map={0: null, 1: output_w, 2: output_w, 7: release_r})
            self.assertEqual(os.getpgid(pid), pid)
            self.assertFalse(select.select([output_r], [], [], 0.25)[0])
            os.write(release_w, b"\x01")
            self.assertTrue(select.select([output_r], [], [], 5)[0], "No child output")
            self.assertEqual(os.read(output_r, 1000), b"original\n")
            _, status = os.waitpid(pid, 0)
            pid = None
            self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        finally:
            if pid is not None:
                try:
                    os.kill(pid, 9)
                except ProcessLookupError:
                    pass
                os.waitpid(pid, 0)
            for fd in (cwd, release_r, release_w, output_r, output_w, null, unrelated):
                os.close(fd)

    def process_authorization(self, arguments, operation="run_process"):
        from effect_gate import EffectGate, MissionApprovalResponse, canonical_digest
        from orchestration.store import Store
        from orchestration.effect_schema import upgrade_effect_schema
        store = Store(str(self.home / "effects.sqlite3"))
        self.addCleanup(store.close)
        mission, action = str(uuid.uuid4()), str(uuid.uuid4())
        store.create_mission(mission, "Fixture", str(self.home))
        for state in ("INITIALIZING_MISSION", "SENDING_OBJECTIVE", "WAITING_FOR_CHATGPT", "PARSING_DECISION", "EXECUTING_LOCAL_ACTION"):
            store.transition(mission, state)
        decision = dict(protocol="cortex.v1", missionId=mission, actionId=action, iteration=1,
            state="EXECUTE", summary="Fixture", action={"tool":operation, "arguments":arguments},
            acceptanceCriteria=["Output"], requiresApproval=True, terminal=False)
        store.record_decision(str(uuid.uuid4()), mission, action, 1, decision, valid=True)
        upgrade_effect_schema(store._conn)
        gate = EffectGate(store)
        challenge = dataclasses.asdict(gate.register_pending_approval(mission_id=mission, action_id=action,
            tool=operation, arguments=arguments, scope="once"))
        challenge.pop("tool")
        gate.decide_approval(MissionApprovalResponse(**challenge, approve=True))
        activation = gate.activate_mission_effect(mission_id=mission, action_id=action, epoch=0,
            operation=operation, payload_digest=canonical_digest(operation, arguments),
            category="process", approval_required=True)
        return store, gate, activation

    def durable_release_case(self, fail_journal=False):
        from executor import process_spawn
        self.assertTrue(callable(getattr(process_spawn, "record_and_release_process", None)),
                        "Journal-before-release integration is missing")
        arguments = {"argv": ["/bin/echo", "EXECUTED"]}
        store, gate, activation = self.process_authorization(arguments)
        cwd = os.open(self.home, os.O_RDONLY | os.O_DIRECTORY)
        reader, writer = os.pipe()
        output_r, output_w = os.pipe()
        null = os.open("/dev/null", os.O_RDONLY)
        pid = None
        try:
            helper = self.attest()
            pid = process_spawn.spawn_attested_at(helper,
                argv=[str(helper.path), "--release-fd", "7", "--", *arguments["argv"]],
                cwd_fd=cwd, env={"PATH":"/usr/bin:/bin"}, fd_map={0:null, 1:output_w, 2:output_w, 7:reader})
            if fail_journal:
                with patch.object(gate, "record_process_release", side_effect=sqlite3.OperationalError("fixture journal failure")):
                    with self.assertRaises(sqlite3.OperationalError):
                        process_spawn.record_and_release_process(gate, activation, pid=pid, release_fd=writer, arguments=arguments)
            else:
                native_write = os.write
                def verify_then_write(fd, data):
                    connection = sqlite3.connect(str(self.home / "effects.sqlite3"))
                    try:
                        own, auth = connection.execute("SELECT ownership_json,authorization_json FROM effects").fetchone()
                        self.assertEqual(json.loads(own)["pid"], pid)
                        self.assertIs(json.loads(auth)["process_release_consumed"], True)
                    finally:
                        connection.close()
                    return native_write(fd, data)
                with patch.object(os, "write", verify_then_write):
                    process_spawn.record_and_release_process(gate, activation, pid=pid, release_fd=writer, arguments=arguments)
            writer = None  # ownership transferred and consumed on both paths
            os.close(output_w)
            output_w = None
            self.assertTrue(select.select([output_r], [], [], 5)[0])
            output = os.read(output_r, 1000)
            _, status = os.waitpid(pid, 0)
            pid = None
            self.assertEqual(os.waitstatus_to_exitcode(status), 125 if fail_journal else 0)
            self.assertEqual(output, b"" if fail_journal else b"EXECUTED\n")
        finally:
            if pid is not None:
                try:
                    os.kill(pid, 9)
                except ProcessLookupError:
                    pass
                os.waitpid(pid, 0)
            for fd in (cwd, reader, writer, output_r, output_w, null):
                if fd is not None:
                    os.close(fd)

    def test_native_release_follows_committed_process_ownership(self):
        self.durable_release_case()

    def test_native_journal_failure_causes_eof_without_command_execution(self):
        self.durable_release_case(fail_journal=True)

    def test_owned_process_binds_command_copy_and_consumes_release_once(self):
        from executor import process_spawn
        self.assertTrue(callable(getattr(process_spawn, "spawn_owned_process", None)),
                        "Owned native process is missing")
        arguments = {"argv": ["/bin/echo", "EXECUTED"]}
        _, gate, activation = self.process_authorization(arguments)
        cwd = os.open(self.home, os.O_RDONLY | os.O_DIRECTORY)
        try:
            process = process_spawn.spawn_owned_process(self.attest(), gate=gate, activation=activation,
                arguments=arguments, cwd_fd=cwd, env={"PATH":"/usr/bin:/bin"})
        finally:
            os.close(cwd)
        self.addCleanup(process.close)
        arguments["argv"][1] = "CHANGED"
        self.assertFalse(select.select([process.stdout_fd], [], [], 0.1)[0])
        process.release()
        with self.assertRaises(RuntimeError):
            process.release()
        self.assertTrue(select.select([process.stdout_fd], [], [], 5)[0])
        self.assertEqual(os.read(process.stdout_fd, 1000), b"EXECUTED\n")
        self.assertEqual(process.wait(timeout=5), 0)
        with self.assertRaises(ChildProcessError):
            os.waitpid(process.pid, os.WNOHANG)

    def test_owned_process_abort_before_release_never_executes(self):
        from executor import process_spawn
        self.assertTrue(callable(getattr(process_spawn, "spawn_owned_process", None)),
                        "Owned native process is missing")
        arguments = {"argv": ["/bin/echo", "EXECUTED"]}
        _, gate, activation = self.process_authorization(arguments)
        cwd = os.open(self.home, os.O_RDONLY | os.O_DIRECTORY)
        try:
            process = process_spawn.spawn_owned_process(self.attest(), gate=gate, activation=activation,
                arguments=arguments, cwd_fd=cwd, env={"PATH":"/usr/bin:/bin"})
        finally:
            os.close(cwd)
        pid = process.pid
        process.close()
        self.assertEqual(process.returncode, 125)
        with self.assertRaises(ChildProcessError):
            os.waitpid(pid, os.WNOHANG)

    def test_owned_process_failed_release_closes_pipe_and_cannot_retry(self):
        from executor import process_spawn
        arguments = {"argv": ["/bin/echo", "EXECUTED"]}
        _, gate, activation = self.process_authorization(arguments)
        cwd = os.open(self.home, os.O_RDONLY | os.O_DIRECTORY)
        try:
            process = process_spawn.spawn_owned_process(self.attest(), gate=gate, activation=activation,
                arguments=arguments, cwd_fd=cwd, env={"PATH":"/usr/bin:/bin"})
        finally:
            os.close(cwd)
        self.addCleanup(process.close)
        with patch.object(gate, "record_process_release", side_effect=sqlite3.OperationalError("fixture")):
            with self.assertRaises(sqlite3.OperationalError):
                process.release()
        with self.assertRaises(RuntimeError):
            process.release()
        self.assertEqual(process.wait(timeout=5), 125)
        self.assertEqual(os.read(process.stdout_fd, 1000), b"")

    def captured_process(self, code):
        from executor import process_spawn
        self.assertTrue(callable(getattr(process_spawn.OwnedProcess, "collect", None)),
                        "Bounded concurrent output collection is missing")
        arguments = {"argv": [sys.executable, "-c", code]}
        _, gate, activation = self.process_authorization(arguments)
        cwd = os.open(self.home, os.O_RDONLY | os.O_DIRECTORY)
        try:
            process = process_spawn.spawn_owned_process(self.attest(), gate=gate, activation=activation,
                arguments=arguments, cwd_fd=cwd, env={"PATH":"/usr/bin:/bin"})
        finally:
            os.close(cwd)
        self.addCleanup(process.close)
        process.release()
        return process

    def test_bare_command_resolution_preserves_authorized_arguments(self):
        from executor import process_spawn
        from effect_gate import canonical_digest
        arguments = {"argv": ["echo", "APPROVED"]}
        store, gate, activation = self.process_authorization(arguments)
        cwd = os.open(self.home, os.O_RDONLY | os.O_DIRECTORY)
        try:
            try:
                process = process_spawn.spawn_owned_process(self.attest(), gate=gate,
                    activation=activation, arguments=arguments, cwd_fd=cwd,
                    env={"PATH": "/bin"})
            except ValueError as error:
                self.fail(f"Approved command name cannot reach native execution: {error}")
        finally:
            os.close(cwd)
        self.addCleanup(process.close)
        process.release()
        self.assertEqual(process.collect(timeout=5)["stdout"], "APPROVED\n")
        ownership = json.loads(store.effect_rows()[0]["ownership_json"])
        self.assertEqual(ownership["executable"], "/bin/echo")
        self.assertEqual(ownership["argv_hash"], hashlib.sha256(b'["echo","APPROVED"]').hexdigest())
        self.assertEqual(activation.payload_digest, canonical_digest("run_process", arguments))
        self.assertEqual(arguments, {"argv": ["echo", "APPROVED"]})
        self.assertEqual(process.finalize().state, "succeeded")

    def test_command_resolution_refuses_implicit_or_relative_search_paths(self):
        from executor import process_spawn
        arguments = {"argv": ["echo", "APPROVED"]}
        store, gate, activation = self.process_authorization(arguments)
        cwd = os.open(self.home, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, cwd)
        helper = self.attest()
        for env in ({}, {"PATH": ""}, {"PATH": ".:/bin"}, {"PATH": "/bin:"}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                process_spawn.spawn_owned_process(helper, gate=gate, activation=activation,
                    arguments=arguments, cwd_fd=cwd, env=env)
        self.assertIsNone(store.effect_rows()[0]["ownership_json"])
        with self.assertRaises(FileNotFoundError):
            process_spawn.spawn_owned_process(helper, gate=gate, activation=activation,
                arguments=arguments, cwd_fd=cwd, env={"PATH": str(self.home)})

    def test_release_refuses_another_resolved_program_and_closes_channel(self):
        from executor.process_spawn import record_and_release_process
        arguments = {"argv": ["echo", "APPROVED"]}
        store, gate, activation = self.process_authorization(arguments)
        reader, writer = os.pipe()
        self.addCleanup(os.close, reader)
        with self.assertRaises(ValueError):
            record_and_release_process(gate, activation, pid=os.getpid(), release_fd=writer,
                                       arguments=arguments, executable="/bin/false")
        self.assertEqual(os.read(reader, 1), b"")
        self.assertIsNone(store.effect_rows()[0]["ownership_json"])

    def test_collect_drains_both_full_pipes_with_bounded_capture(self):
        process = self.captured_process("import os; os.write(1,b'A'*200000); os.write(2,b'B'*200000); raise SystemExit(9)")
        result = process.collect(timeout=5, max_bytes=1024)
        self.assertEqual(result["stdout"], "A"*1024)
        self.assertEqual(result["stderr"], "B"*1024)
        self.assertEqual((result["stdoutBytes"], result["stderrBytes"]), (200000, 200000))
        self.assertEqual(result["exitCode"], 9)
        self.assertTrue(result["truncated"])
        self.assertEqual(process.collect(timeout=1, max_bytes=1024), result)

    def test_collect_timeout_preserves_capture_for_same_process(self):
        process = self.captured_process("import os,time; os.write(1,b'prefix'); time.sleep(1); os.write(1,b'suffix')")
        self.assertTrue(select.select([process.stdout_fd], [], [], 5)[0])
        with self.assertRaises(TimeoutError):
            process.collect(timeout=0.02, max_bytes=100)
        result = process.collect(timeout=5, max_bytes=100)
        self.assertEqual(result["stdout"], "prefixsuffix")
        self.assertEqual(result["stdoutBytes"], 12)
        self.assertFalse(result["truncated"])
        self.assertEqual(result["exitCode"], 0)

    def test_collect_refuses_invalid_limits_without_consuming_output(self):
        process = self.captured_process("print('intact')")
        for limit in (0, -1, True, 1048577):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                process.collect(timeout=5, max_bytes=limit)
        for timeout in (0, float("nan"), float("inf"), True):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                process.collect(timeout=timeout)
        result = process.collect(timeout=5)
        self.assertEqual(result["stdout"], "intact\n")
        result["stdout"] = "caller changed copy"
        self.assertEqual(process.collect(timeout=1)["stdout"], "intact\n")

    def cancellable_process(self, code):
        from executor.process_spawn import OwnedProcess
        self.assertTrue(callable(getattr(OwnedProcess, "cancel", None)),
                        "Owned group cancellation is missing")
        process = self.captured_process(code)
        def emergency_cleanup():
            from startup_lease import _read_kernel_process_identity
            observed = _read_kernel_process_identity(process.pid)
            ownership = process._gate.store.effect_rows()[0]["ownership_json"]
            if observed is not None and observed.start_time == json.loads(ownership)["start_time"]:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait(timeout=5)
        self.addCleanup(emergency_cleanup)
        self.assertTrue(select.select([process.stdout_fd], [], [], 5)[0], "Child not ready")
        return process

    def test_cancel_waits_before_kill_when_term_is_ignored(self):
        process = self.cancellable_process("import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('READY',flush=True); time.sleep(30)")
        self.assertEqual(os.read(process.stdout_fd, 100), b"READY\n")
        start = time.monotonic()
        result = process.cancel()
        self.assertGreaterEqual(time.monotonic() - start, 1.9)
        self.assertEqual(result["exitCode"], -signal.SIGKILL)
        self.assertTrue(result["groupAbsent"])
        with self.assertRaises(ProcessLookupError):
            os.killpg(process.pid, 0)

    def test_cancel_terminates_group_child_and_reaps_leader(self):
        code = ("import subprocess,sys,signal,time; "
                "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
                "print(child.pid,flush=True); time.sleep(30)")
        process = self.cancellable_process(code)
        child_pid = int(os.read(process.stdout_fd, 100).strip())
        result = process.cancel()
        self.assertTrue(result["groupAbsent"])
        with self.assertRaises(ProcessLookupError):
            os.kill(child_pid, 0)
        with self.assertRaises(ChildProcessError):
            os.waitpid(process.pid, os.WNOHANG)

    def test_cancel_preserves_graceful_term_exit(self):
        process = self.cancellable_process("import time; print('READY',flush=True); time.sleep(30)")
        self.assertEqual(os.read(process.stdout_fd, 100), b"READY\n")
        result = process.cancel()
        self.assertEqual(result["exitCode"], -signal.SIGTERM)
        self.assertTrue(result["groupAbsent"])
        self.assertEqual(process.cancel(), result)

    def test_cancel_permission_denied_is_not_reported_as_stopped(self):
        process = self.cancellable_process("import time; print('READY',flush=True); time.sleep(30)")
        self.assertEqual(os.read(process.stdout_fd, 100), b"READY\n")
        with patch.object(os, "killpg", side_effect=PermissionError()):
            with self.assertRaisesRegex(RuntimeError, "PROCESS_OWNERSHIP_UNCLEAR"):
                process.cancel()
        self.assertIsNone(process.returncode)
        self.assertTrue(process.cancel()["groupAbsent"])

    def finalizable_process(self, code):
        from executor.process_spawn import OwnedProcess
        self.assertTrue(callable(getattr(OwnedProcess, "finalize", None)),
                        "Verified process terminal receipts are missing")
        return self.captured_process(code)

    def test_finalize_success_requires_collected_output_and_persists_once(self):
        process = self.finalizable_process("print('verified')")
        with self.assertRaises(RuntimeError):
            process.finalize()
        result = process.collect(timeout=5)
        receipt = process.finalize()
        self.assertEqual(receipt.state, "succeeded")
        self.assertEqual(receipt.result["stdout"], "verified\n")
        connection = sqlite3.connect(str(self.home / "effects.sqlite3"))
        try:
            state, encoded = connection.execute("SELECT state,receipt_json FROM effects").fetchone()
            self.assertEqual(state, "succeeded")
            self.assertEqual(json.loads(encoded)["exitCode"], result["exitCode"])
        finally:
            connection.close()
        from effect_gate import EffectGateConflict
        with self.assertRaises(EffectGateConflict):
            process.finalize()

    def test_finalize_nonzero_exit_is_failed(self):
        process = self.finalizable_process("raise SystemExit(7)")
        process.collect(timeout=5)
        receipt = process.finalize()
        self.assertEqual(receipt.state, "failed")
        self.assertEqual(receipt.error_code, "PROCESS_EXIT_NONZERO")
        self.assertEqual(receipt.result["exitCode"], 7)

    def test_finalize_cancellation_is_not_success(self):
        from executor.process_spawn import OwnedProcess
        self.assertTrue(callable(getattr(OwnedProcess, "finalize", None)),
                        "Verified process terminal receipts are missing")
        process = self.cancellable_process("import time; print('READY',flush=True); time.sleep(30)")
        os.read(process.stdout_fd, 100)
        process.cancel()
        receipt = process.finalize()
        self.assertEqual(receipt.state, "failed")
        self.assertEqual(receipt.error_code, "PROCESS_CANCELLED")
        self.assertFalse(receipt.result["outputComplete"])

    def test_timeout_receipt_preserves_reason_after_collection(self):
        import inspect
        from executor.process_spawn import OwnedProcess
        self.assertIn("reason", inspect.signature(OwnedProcess.cancel).parameters)
        process = self.cancellable_process("import time; print('READY',flush=True); time.sleep(30)")
        with self.assertRaises(TimeoutError):
            process.collect(timeout=0.02)
        stopped = process.cancel(reason="timeout")
        self.assertTrue(stopped["groupAbsent"])
        process.collect(timeout=5)
        receipt = process.finalize()
        self.assertEqual(receipt.state, "failed")
        self.assertEqual(receipt.error_code, "PROCESS_TIMEOUT")
        self.assertIn("READY", receipt.result["stdout"])
        self.assertTrue(receipt.result["outputComplete"])
        self.assertTrue(receipt.result["quiescenceVerified"])
        self.assertEqual(process.cancel(reason="timeout"), stopped)
        with self.assertRaises(ValueError):
            process.cancel(reason="cancelled")

    def test_invalid_stop_reason_does_not_signal_child(self):
        import inspect
        from executor.process_spawn import OwnedProcess
        self.assertIn("reason", inspect.signature(OwnedProcess.cancel).parameters)
        process = self.cancellable_process("import time; print('READY',flush=True); time.sleep(30)")
        for reason in ("", "success", None, 1):
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                process.cancel(reason=reason)
        os.kill(process.pid, 0)
        self.assertIsNone(process.returncode)
        process.cancel()
        self.assertEqual(process.finalize().error_code, "PROCESS_CANCELLED")

    def test_stop_reason_cannot_change_after_uncertain_attempt(self):
        import inspect
        from executor.process_spawn import OwnedProcess
        self.assertIn("reason", inspect.signature(OwnedProcess.cancel).parameters)
        process = self.cancellable_process("import time; print('READY',flush=True); time.sleep(30)")
        with patch.object(os, "killpg", side_effect=PermissionError()):
            with self.assertRaisesRegex(RuntimeError, "PROCESS_OWNERSHIP_UNCLEAR"):
                process.cancel(reason="timeout")
        with self.assertRaises(ValueError):
            process.cancel(reason="cancelled")
        process.cancel(reason="timeout")
        self.assertEqual(process.finalize().error_code, "PROCESS_TIMEOUT")

    def test_finalize_zero_exit_with_unverifiable_group_is_unclear(self):
        process = self.finalizable_process("pass")
        process.collect(timeout=5)
        with patch.object(os, "killpg", side_effect=PermissionError()):
            receipt = process.finalize()
        self.assertEqual(receipt.state, "outcome_unclear")
        self.assertEqual(receipt.error_code, "PROCESS_OWNERSHIP_UNCLEAR")
        self.assertFalse(receipt.result["quiescenceVerified"])


class AsyncOwnedProcessTests(unittest.IsolatedAsyncioTestCase):
    setUp = SignedNativeHelperTests.setUp
    attest = SignedNativeHelperTests.attest
    process_authorization = SignedNativeHelperTests.process_authorization
    captured_process = SignedNativeHelperTests.captured_process
    cancellable_process = SignedNativeHelperTests.cancellable_process

    def native_workspace(self):
        import inspect
        from executor.tools import ToolExecutor
        from executor.workspace_handle import WorkspaceHandle, MountFacts
        from pathlib import PurePosixPath
        self.assertIn("process_helper", inspect.signature(ToolExecutor).parameters,
                      "ToolExecutor has no native process integration")
        workspace = self.home / "20_WORKSPACES" / "qa"
        workspace.mkdir(parents=True)
        (workspace / "task.py").write_text("from pathlib import Path\nPath('result.txt').write_text('executed')\nprint('NATIVE TOOL')\n")
        root = os.open(self.home, os.O_RDONLY | os.O_DIRECTORY)
        directory = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY)
        facts = MountFacts(os.fstat(root).st_dev & 0xffffffff, (1, 2), 0,
                           "fixture", "fixture", str(self.home), "fixture")
        try:
            handle = WorkspaceHandle.from_verified_fds(mount_fd=root, workspace_fd=directory,
                storage_transaction_id="fixture", apfs_volume_uuid="fixture",
                relative_path=PurePosixPath("20_WORKSPACES/qa"), fd_probe=lambda fd: facts)
        finally:
            os.close(directory)
            os.close(root)
        self.addCleanup(handle.close)
        return workspace, handle

    def native_tool_case(self, arguments, operation="run_process"):
        from executor.tools import ToolExecutor
        workspace, handle = self.native_workspace()
        store, gate, activation = self.process_authorization(arguments, operation)
        executor = ToolExecutor(handle, effect_gate=gate, process_helper=self.attest())
        return executor, activation, store, workspace

    async def native_mission(self, writes_result):
        from executor.tools import ToolExecutor
        from executor.policy import PolicyEngine
        from orchestration.loop import MissionLoop, MockOrchestrator
        from orchestration.store import Store
        from orchestration.effect_schema import upgrade_effect_schema
        from effect_gate import EffectGate, MissionApprovalResponse
        workspace, handle = self.native_workspace()
        if not writes_result:
            (workspace / "task.py").write_text("print('nothing produced')\n")
        store = Store(str(self.home / "mission.sqlite3"))
        self.addCleanup(store.close)
        mission = str(uuid.uuid4())
        store.create_mission(mission, "Produce result.txt containing executed", str(workspace))
        upgrade_effect_schema(store._conn)
        gate = EffectGate(store)
        def approve(challenge, policy):
            fields = dataclasses.asdict(challenge)
            fields.pop("tool")
            gate.decide_approval(MissionApprovalResponse(**fields, approve=True))
        async def verify_file(decision, executor):
            exists = (await executor.file_exists("result.txt"))["exists"]
            valid = exists and (await executor.read_file("result.txt"))["content"] == "executed"
            return {"passed": bool(valid), "checks": [
                {"name": "required_file_content", "passed": bool(valid),
                 "evidence": "Compared actual file content" if exists else "Required result.txt is absent"}]}
        orchestrator = MockOrchestrator(mission, [
            {"state": "EXECUTE", "action": {"tool": "run_process",
             "arguments": {"argv": ["python3", "task.py"]}}, "requiresApproval": True},
            {"state": "COMPLETE", "action": None, "terminal": True,
             "acceptanceCriteria": ["result.txt contains executed"]},
            {"state": "BLOCKED", "action": None, "terminal": True,
             "summary": "Fixture cannot repair missing output"},
        ])
        executor = ToolExecutor(handle, effect_gate=gate, process_helper=self.attest())
        result = await MissionLoop(store=store, mission_id=mission, orchestrator=orchestrator,
            tools=executor, effect_gate=gate, approval_callback=approve,
            policy=PolicyEngine(handle, allow_processes=True), final_validator=verify_file).run()
        return result, store, mission, workspace

    async def test_mission_loop_native_command_completes_with_actual_file_proof(self):
        result, store, mission, workspace = await self.native_mission(True)
        self.assertEqual(result["state"], "COMPLETED")
        self.assertEqual((workspace / "result.txt").read_text(), "executed")
        self.assertEqual([r["state"] for r in store.effect_rows()], ["succeeded"])
        self.assertIsNotNone(store.rows("approvals", mission)[0]["effect_consumed_at"])

    async def test_mission_loop_rejects_exit_zero_without_required_artifact(self):
        result, store, mission, workspace = await self.native_mission(False)
        self.assertNotEqual(result["state"], "COMPLETED")
        self.assertEqual([r["state"] for r in store.effect_rows()], ["succeeded"])
        self.assertFalse((workspace / "result.txt").exists())
        self.assertTrue(any(r["passed"] == 0 for r in store.rows("validation_results", mission)))

    async def test_tool_executor_runs_native_command_with_exact_omitted_defaults(self):
        arguments = {"argv": ["python3", "task.py"]}
        executor, activation, store, workspace = self.native_tool_case(arguments)
        result = await executor.run_process(**arguments, activation=activation)
        self.assertEqual(result["exitCode"], 0)
        self.assertIn("NATIVE TOOL", result["stdout"])
        self.assertEqual((workspace / "result.txt").read_text(), "executed")
        self.assertEqual(store.effect_rows()[0]["state"], "succeeded")

    async def test_native_run_tests_executes_selected_suite_with_original_empty_payload(self):
        import inspect
        from executor.tools import ToolExecutor
        self.assertIn("activation", inspect.signature(ToolExecutor.run_tests).parameters)
        executor, activation, store, workspace = self.native_tool_case({}, "run_tests")
        executor.test_commands = [["python3", "-m", "unittest", "discover"]]
        (workspace / "test_native.py").write_text(
            "import unittest\nfrom pathlib import Path\nclass NativeTest(unittest.TestCase):\n"
            " def test_real(self):\n  self.assertEqual(2+2,4)\n  Path('tested').write_text('yes')\n")
        result = await executor.run_tests(activation=activation)
        self.assertEqual(result["exitCode"], 0)
        self.assertIn("Ran 1 test", result["stderr"])
        self.assertEqual((workspace / "tested").read_text(), "yes")
        row = store.effect_rows()[0]
        self.assertEqual(row["operation"], "run_tests")
        self.assertEqual(row["state"], "succeeded")

    async def test_run_process_approval_cannot_authorize_run_tests(self):
        import inspect
        from executor.tools import ToolExecutor
        from effect_gate import EffectGateConflict
        self.assertIn("activation", inspect.signature(ToolExecutor.run_tests).parameters)
        arguments = {"argv": ["python3", "task.py"]}
        executor, activation, store, workspace = self.native_tool_case(arguments)
        executor.test_commands = [arguments["argv"]]
        with self.assertRaises(EffectGateConflict):
            await executor.run_tests(**arguments, activation=activation)
        self.assertFalse((workspace / "result.txt").exists())
        self.assertIsNone(store.effect_rows()[0]["ownership_json"])

    async def test_missing_test_command_settles_failure_without_process(self):
        from executor.tools import ToolDenied
        executor, activation, store, workspace = self.native_tool_case({}, "run_tests")
        with self.assertRaises(ToolDenied):
            await executor.run_tests(activation=activation)
        row = store.effect_rows()[0]
        self.assertEqual(row["state"], "failed")
        self.assertEqual(row["error_code"], "NO_TEST_COMMAND")
        self.assertIsNone(row["ownership_json"])
        executor.effect_gate.request_stop()
        self.assertTrue(executor.effect_gate.settle_stop().reset_allowed)

    async def test_native_test_discovery_uses_requested_subdirectory(self):
        from executor.policy import PolicyEngine
        arguments = {"cwd": "sub"}
        executor, activation, store, workspace = self.native_tool_case(arguments, "run_tests")
        (workspace / "sub").mkdir()
        (workspace / "sub/test_nested.py").write_text(
            "import unittest\nfrom pathlib import Path\nclass Nested(unittest.TestCase):\n"
            " def test_real(self):\n  Path('nested-result').write_text('tested')\n")
        decision = PolicyEngine(executor.workspace, allow_processes=True).evaluate("run_tests", arguments)
        self.assertTrue(decision.allowed, decision.reason)
        result = await executor.run_tests(**arguments, activation=activation)
        self.assertEqual(result["exitCode"], 0)
        self.assertIn("Ran 1 test", result["stderr"])
        self.assertTrue((workspace / "sub/nested-result").is_file())

    async def test_nested_test_discovery_does_not_use_root_manifest(self):
        from executor.tools import ToolDenied
        arguments = {"cwd": "sub"}
        executor, activation, store, workspace = self.native_tool_case(arguments, "run_tests")
        (workspace / "sub").mkdir()
        (workspace / "package.json").write_text('{"scripts":{"test":"echo root"}}')
        with self.assertRaises(ToolDenied) as raised:
            await executor.run_tests(**arguments, activation=activation)
        self.assertEqual(raised.exception.code, "NO_TEST_COMMAND")
        self.assertIsNone(store.effect_rows()[0]["ownership_json"])

    async def test_unconfigured_test_command_settles_failure_without_process(self):
        from executor.tools import ToolDenied
        arguments = {"argv": ["python3", "task.py"]}
        executor, activation, store, workspace = self.native_tool_case(arguments, "run_tests")
        executor.test_commands = [["python3", "-m", "unittest"]]
        with self.assertRaises(ToolDenied):
            await executor.run_tests(**arguments, activation=activation)
        row = store.effect_rows()[0]
        self.assertEqual(row["state"], "failed")
        self.assertEqual(row["error_code"], "UNCONFIGURED_TEST_COMMAND")
        self.assertIsNone(row["ownership_json"])
        self.assertFalse((workspace / "result.txt").exists())

    async def test_wrong_test_payload_cannot_terminalize_authorized_action(self):
        from executor.tools import ToolDenied
        arguments = {"argv": ["python3", "task.py"]}
        executor, activation, store, workspace = self.native_tool_case(arguments, "run_tests")
        with self.assertRaises(ToolDenied) as raised:
            await executor.run_tests(argv=["python3", "another.py"], activation=activation)
        self.assertEqual(raised.exception.code, "EFFECT_PAYLOAD_MISMATCH")
        self.assertEqual(store.effect_rows()[0]["state"], "active")
        self.assertIsNone(store.effect_rows()[0]["ownership_json"])

    async def test_tool_executor_uses_retained_workspace_after_path_replacement(self):
        arguments = {"argv": ["python3", "task.py"], "cwd": ".", "timeoutSeconds": 10}
        executor, activation, store, workspace = self.native_tool_case(arguments)
        retained = self.home / "retained"
        workspace.rename(retained)
        workspace.mkdir()
        (workspace / "task.py").write_text("raise SystemExit('WRONG DIRECTORY')")
        result = await executor.run_process(**arguments, activation=activation)
        self.assertEqual(result["exitCode"], 0)
        self.assertTrue((retained / "result.txt").is_file())
        self.assertFalse((workspace / "result.txt").exists())

    async def test_tool_executor_rejects_modified_defaults_without_launch(self):
        from executor.tools import ToolDenied
        arguments = {"argv": ["python3", "task.py"]}
        executor, activation, store, workspace = self.native_tool_case(arguments)
        with self.assertRaises(ToolDenied):
            await executor.run_process(**arguments, cwd=".", activation=activation)
        self.assertFalse((workspace / "result.txt").exists())
        self.assertIsNone(store.effect_rows()[0]["ownership_json"])
        result = await executor.run_process(**arguments, activation=activation)
        self.assertEqual(result["exitCode"], 0)

    async def test_tool_executor_checks_script_in_requested_subdirectory(self):
        arguments = {"argv": ["python3", "task.py"], "cwd": "sub"}
        executor, activation, store, workspace = self.native_tool_case(arguments)
        (workspace / "sub").mkdir()
        (workspace / "task.py").rename(workspace / "sub/task.py")
        from executor.policy import PolicyEngine
        decision = PolicyEngine(executor.workspace, allow_processes=True).evaluate("run_process", arguments)
        self.assertTrue(decision.allowed, decision.reason)
        result = await executor.run_process(**arguments, activation=activation)
        self.assertEqual(result["exitCode"], 0)
        self.assertTrue((workspace / "sub/result.txt").is_file())
        self.assertFalse((workspace / "result.txt").exists())

    async def test_tool_executor_refuses_subdirectory_script_symlink(self):
        from executor.tools import ToolDenied
        arguments = {"argv": ["python3", "task.py"], "cwd": "sub"}
        executor, activation, store, workspace = self.native_tool_case(arguments)
        (workspace / "sub").mkdir()
        outside = self.home / "outside.py"
        outside.write_text("from pathlib import Path\nPath('escaped.txt').write_text('WRONG SCRIPT')\n")
        (workspace / "sub/task.py").symlink_to(outside)
        from executor.policy import PolicyEngine
        self.assertFalse(PolicyEngine(executor.workspace, allow_processes=True).evaluate(
            "run_process", arguments).allowed)
        with self.assertRaises(ToolDenied):
            await executor.run_process(**arguments, activation=activation)
        self.assertFalse((workspace / "sub/escaped.txt").exists())
        self.assertIsNone(store.effect_rows()[0]["ownership_json"])

    def supervised_process(self, code):
        from executor.process_spawn import OwnedProcess
        self.assertTrue(callable(getattr(OwnedProcess, "supervise", None)),
                        "Async single-owner supervision is missing")
        return self.cancellable_process(code)

    async def running_tool(self):
        import asyncio
        arguments = {"argv": ["python3", "task.py"], "timeoutSeconds": 20}
        executor, activation, store, workspace = self.native_tool_case(arguments)
        (workspace / "task.py").write_text("import time\nfrom pathlib import Path\nPath('ready').write_text('ready')\ntime.sleep(30)\n")
        task = asyncio.create_task(executor.run_process(**arguments, activation=activation))
        async def cleanup():
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.addAsyncCleanup(cleanup)
        deadline = time.monotonic() + 5
        while not (workspace / "ready").exists():
            if task.done():
                await task
                self.fail("Command ended without readiness marker")
            if time.monotonic() >= deadline:
                self.fail("Command readiness deadline exceeded")
            await asyncio.sleep(0.01)
        ownership = json.loads(store.effect_rows()[0]["ownership_json"])
        return executor, task, store, ownership

    async def test_tool_executor_durable_stop_terminates_live_command(self):
        import asyncio
        executor, task, store, ownership = await self.running_tool()
        gate = executor.effect_gate
        status = gate.request_stop()
        self.assertEqual(status.state, "stopping")
        self.assertFalse(status.reset_allowed)
        result = await asyncio.wait_for(asyncio.shield(task), timeout=5)
        self.assertEqual(result["errorCode"], "PROCESS_CANCELLED")
        self.assertEqual(store.effect_rows()[0]["state"], "failed")
        with self.assertRaises(ProcessLookupError):
            os.killpg(ownership["pid"], 0)
        self.assertFalse(executor._owned_processes)
        self.assertTrue(gate.settle_stop().reset_allowed)

    async def test_tool_executor_task_cancellation_waits_for_terminal_receipt(self):
        import asyncio
        executor, task, store, ownership = await self.running_tool()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(store.effect_rows()[0]["state"], "failed")
        self.assertFalse(executor._owned_processes)
        with self.assertRaises(ProcessLookupError):
            os.killpg(ownership["pid"], 0)

    async def test_tool_executor_stop_before_spawn_does_not_execute(self):
        from executor.tools import ToolDenied
        arguments = {"argv": ["python3", "task.py"]}
        executor, activation, store, workspace = self.native_tool_case(arguments)
        executor.effect_gate.request_stop()
        with self.assertRaises(ToolDenied):
            await executor.run_process(**arguments, activation=activation)
        self.assertFalse((workspace / "result.txt").exists())
        self.assertEqual(store.effect_rows()[0]["error_code"], "PROCESS_CANCELLED")
        self.assertIsNone(store.effect_rows()[0]["ownership_json"])
        self.assertTrue(executor.effect_gate.settle_stop().reset_allowed)

    async def test_tool_executor_stop_after_journal_never_releases_command(self):
        from executor.tools import ToolDenied
        arguments = {"argv": ["python3", "task.py"]}
        executor, activation, store, workspace = self.native_tool_case(arguments)
        gate = executor.effect_gate
        record = gate.record_process_release
        def stop_after_journal(capability, ownership):
            record(capability, ownership)
            gate.request_stop()
        with patch.object(gate, "record_process_release", side_effect=stop_after_journal):
            with self.assertRaises(ToolDenied):
                await executor.run_process(**arguments, activation=activation)
        row = store.effect_rows()[0]
        self.assertFalse((workspace / "result.txt").exists())
        self.assertEqual(row["state"], "failed")
        self.assertEqual(row["error_code"], "PROCESS_CANCELLED")
        self.assertFalse(json.loads(row["receipt_json"])["released"])
        with self.assertRaises(ProcessLookupError):
            os.killpg(json.loads(row["ownership_json"])["pid"], 0)
        self.assertFalse(executor._owned_processes)
        self.assertTrue(gate.settle_stop().reset_allowed)

    async def test_supervision_collects_without_blocking_event_loop(self):
        import asyncio
        process = self.supervised_process("import time; print('READY',flush=True); time.sleep(0.2); print('DONE')")
        task = asyncio.create_task(process.supervise(timeout=5))
        await asyncio.sleep(0.03)
        self.assertFalse(task.done(), "Event loop blocked until command completion")
        receipt = await task
        self.assertEqual(receipt.state, "succeeded")
        self.assertIn("DONE", receipt.result["stdout"])
        with self.assertRaises(OSError):
            os.fstat(process.stdout_fd)
        with self.assertRaises(RuntimeError):
            await process.supervise(timeout=5)

    async def test_supervision_deadline_terminates_and_records_timeout(self):
        process = self.supervised_process("import time; print('READY',flush=True); time.sleep(30)")
        receipt = await process.supervise(timeout=0.05)
        self.assertEqual(receipt.error_code, "PROCESS_TIMEOUT")
        self.assertTrue(receipt.result["quiescenceVerified"])
        with self.assertRaises(ProcessLookupError):
            os.killpg(process.pid, 0)

    async def test_repeated_task_cancellation_waits_for_cleanup(self):
        import asyncio
        process = self.supervised_process("import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('READY',flush=True); time.sleep(30)")
        task = asyncio.create_task(process.supervise(timeout=30))
        await asyncio.sleep(0.05)
        with self.assertRaises(RuntimeError):
            await process.supervise(timeout=1)
        start = time.monotonic()
        task.cancel()
        await asyncio.sleep(0.1)
        self.assertFalse(task.done(), "Cancellation abandoned the still-running child")
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertGreaterEqual(time.monotonic() - start, 2)
        row = process._gate.store.effect_rows()[0]
        self.assertEqual(row["state"], "failed")
        self.assertEqual(row["error_code"], "PROCESS_CANCELLED")
        with self.assertRaises(ProcessLookupError):
            os.killpg(process.pid, 0)
        with self.assertRaises(OSError):
            os.fstat(process.stderr_fd)

    async def test_uncertain_cleanup_retains_handle_and_blocks_success(self):
        process = self.supervised_process("import time; print('READY',flush=True); time.sleep(30)")
        with patch.object(os, "killpg", side_effect=PermissionError()):
            receipt = await process.supervise(timeout=0.02)
        self.assertEqual(receipt.state, "outcome_unclear")
        self.assertFalse(receipt.result["quiescenceVerified"])
        self.assertEqual(process._gate.store.effect_rows()[0]["state"], "outcome_unclear")
        os.fstat(process.stdout_fd)
        os.kill(process.pid, 0)
        self.assertIsNone(process.returncode)
        # Emergency fixture cleanup verifies the creation identity before killing.

    async def test_invalid_supervision_limits_do_not_consume_the_process(self):
        process = self.supervised_process("print('READY',flush=True)")
        for timeout in (0, -1, True, float("nan"), float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                await process.supervise(timeout=timeout)
        for limit in (0, True, 1048577):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                await process.supervise(timeout=5, max_bytes=limit)
        receipt = await process.supervise(timeout=5)
        self.assertEqual(receipt.state, "succeeded")

    async def test_output_read_error_terminates_child_before_failed_receipt(self):
        process = self.supervised_process("import time; print('READY',flush=True); time.sleep(30)")
        real_read = os.read
        def broken_output(fd, size):
            if fd == process.stdout_fd:
                raise OSError("private fixture error must not be stored")
            return real_read(fd, size)
        with patch.object(os, "read", side_effect=broken_output):
            receipt = await process.supervise(timeout=5)
        self.assertEqual(receipt.state, "failed")
        self.assertEqual(receipt.error_code, "PROCESS_OUTPUT_ERROR")
        self.assertFalse(receipt.result["outputComplete"])
        self.assertTrue(receipt.result["quiescenceVerified"])
        self.assertNotIn("private fixture", json.dumps(receipt.result))
        with self.assertRaises(ProcessLookupError):
            os.killpg(process.pid, 0)
        with self.assertRaises(OSError):
            os.fstat(process.stdout_fd)


if __name__ == "__main__":
    unittest.main()
