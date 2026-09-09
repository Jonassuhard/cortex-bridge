"""Darwin spawn primitive for an already attested, pipe-blocked helper.

The mission runner still owns activation, durable ownership, release, output
collection and cancellation. This primitive does not release the child.
"""
import ctypes
import fcntl
import os
import platform
import stat
import sys
import hashlib
import json
import time
import math
import selectors
import signal
import asyncio
import threading
import shutil


class ProcessReleaseStopped(RuntimeError):
    """STOP was observed before the release byte was written."""


def _command_argv(activation, arguments, selected):
    if activation.operation not in ("run_process", "run_tests"):
        raise ValueError("Unsupported process operation")
    approved = arguments.get("argv")
    if selected is None:
        selected = approved
    elif approved is not None and selected != approved:
        raise ValueError("Selected command differs from approved argv")
    elif activation.operation != "run_tests" and selected != approved:
        raise ValueError("Only run_tests may select an omitted command")
    if (type(selected) is not list or not selected
            or any(type(s) is not str or not s or "\x00" in s for s in selected)):
        raise ValueError("Valid command argv required")
    return list(selected)


class OwnedProcess:
    """A single child and its parent-owned channels; created only by spawn."""
    def __init__(self):
        raise TypeError("Use spawn_owned_process")

    @property
    def pid(self):
        return self._pid

    @property
    def returncode(self):
        return self._returncode

    def release(self):
        if self._closed or self._release_attempted:
            raise RuntimeError("PROCESS_RELEASE_ALREADY_CONSUMED")
        self._release_attempted = True
        writer, self._release_writer = self._release_writer, None
        return record_and_release_process(self._gate, self._activation, pid=self.pid,
                                          release_fd=writer, arguments=self._arguments,
                                          executable=self._executable, selected_argv=self._command_argv)

    def wait(self, *, timeout):
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Positive bounded wait required")
        deadline = time.monotonic() + timeout
        while self._returncode is None:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid:
                self._returncode = os.waitstatus_to_exitcode(status)
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("PROCESS_WAIT_TIMEOUT")
            time.sleep(min(0.01, max(0, deadline - time.monotonic())))
        return self._returncode

    def collect(self, *, timeout, max_bytes=65536):
        """Drain both pipes while retaining at most max_bytes per stream.

        A timeout preserves this child's capture and descriptors for continued
        observation/cancellation; it never restarts or releases the process.
        """
        if self._closed or not self._release_attempted:
            raise RuntimeError("PROCESS_COLLECTION_NOT_READY")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Positive collection timeout required")
        if type(max_bytes) is not int or not 0 < max_bytes <= 1048576:
            raise ValueError("Capture limit must be 1..1048576 bytes per stream")
        if self._capture is None:
            self._capture = {"limit": max_bytes, "stdout": bytearray(), "stderr": bytearray(),
                             "stdoutBytes": 0, "stderrBytes": 0, "eof": set(), "result": None}
        capture = self._capture
        if capture["limit"] != max_bytes:
            raise ValueError("Cannot change an in-progress capture limit")
        if capture["result"] is not None:
            return dict(capture["result"])
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            for name, fd in (("stdout", self.stdout_fd), ("stderr", self.stderr_fd)):
                if name not in capture["eof"]:
                    os.set_blocking(fd, False)
                    selector.register(fd, selectors.EVENT_READ, name)
            while True:
                if self._returncode is None:
                    pid, status = os.waitpid(self.pid, os.WNOHANG)
                    if pid:
                        self._returncode = os.waitstatus_to_exitcode(status)
                if len(capture["eof"]) == 2 and self._returncode is not None:
                    result = {name: bytes(capture[name]).decode("utf-8", errors="replace")
                              for name in ("stdout", "stderr")}
                    result.update(exitCode=self._returncode,
                        stdoutBytes=capture["stdoutBytes"], stderrBytes=capture["stderrBytes"],
                        truncated=any(capture[name + "Bytes"] > len(capture[name])
                                      for name in ("stdout", "stderr")))
                    capture["result"] = result
                    return dict(result)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("PROCESS_COLLECTION_TIMEOUT")
                for key, _ in selector.select(min(0.05, remaining)):
                    name = key.data
                    try:
                        data = os.read(key.fd, 65536)
                    except BlockingIOError:
                        continue
                    if not data:
                        capture["eof"].add(name)
                        selector.unregister(key.fd)
                        continue
                    capture[name + "Bytes"] += len(data)
                    available = max_bytes - len(capture[name])
                    if available:
                        capture[name].extend(data[:available])

    def cancel(self, *, reason="cancelled"):
        """TERM then, after two seconds, KILL only a still-owned group.

        No terminal effect is invented here. If group identity/absence cannot
        be established, keep ownership and report uncertainty to the runner.
        """
        from startup_lease import _read_kernel_process_identity
        if reason not in ("cancelled", "timeout", "output_error"):
            raise ValueError("Unsupported process stop reason")
        if self._stop_reason is not None and self._stop_reason != reason:
            raise ValueError("Cannot change a process stop reason")
        self._stop_reason = reason
        if self._cancel_result is not None:
            return dict(self._cancel_result)

        def group_exists():
            try:
                os.killpg(self.pid, 0)
            except ProcessLookupError:
                return False
            except PermissionError as error:
                # Darwin can report EPERM for a zombie-only group. Reap only
                # our still-owned child if waitpid proves it has exited, then
                # ask the kernel again. EPERM itself never proves absence.
                if self._returncode is None:
                    finished, status = os.waitpid(self.pid, os.WNOHANG)
                    if finished:
                        self._returncode = os.waitstatus_to_exitcode(status)
                        try:
                            os.killpg(self.pid, 0)
                        except ProcessLookupError:
                            return False
                        except OSError as retry_error:
                            raise RuntimeError("PROCESS_OWNERSHIP_UNCLEAR") from retry_error
                        return True
                raise RuntimeError("PROCESS_OWNERSHIP_UNCLEAR") from error
            except OSError as error:
                raise RuntimeError("PROCESS_OWNERSHIP_UNCLEAR") from error
            return True

        def completed():
            result = {"exitCode": self._returncode, "groupAbsent": True}
            self._cancel_result = result
            return dict(result)

        if not self._release_attempted:
            self.close()
            if group_exists():
                raise RuntimeError("PROCESS_OWNERSHIP_UNCLEAR")
            return completed()
        if not group_exists():
            self.wait(timeout=2)
            return completed()
        row = next((row for row in self._gate.store.effect_rows()
                    if row["id"] == self._activation.effect_id), None)
        ownership = json.loads(row["ownership_json"]) if row and row["ownership_json"] else {}

        def verified():
            identity = _read_kernel_process_identity(self.pid)
            return (identity is not None and ownership.get("pid") == self.pid
                    and ownership.get("pgid") == identity.pgid == self.pid
                    and ownership.get("start_time") == identity.start_time)

        if not verified():
            raise RuntimeError("PROCESS_OWNERSHIP_UNCLEAR")
        os.killpg(self.pid, signal.SIGTERM)
        deadline = time.monotonic() + 2
        # Do not reap the leader before escalation; its retained identity
        # prevents a surviving group from being mistaken for a reused PID.
        while time.monotonic() < deadline:
            if not group_exists():
                self.wait(timeout=2)
                return completed()
            time.sleep(min(0.02, max(0, deadline - time.monotonic())))
        if group_exists():
            if not verified():
                # A vanished/unverifiable leader never authorizes a signal
                # against whichever group happens to have this number.
                raise RuntimeError("PROCESS_OWNERSHIP_UNCLEAR")
            os.killpg(self.pid, signal.SIGKILL)
        self.wait(timeout=2)
        deadline = time.monotonic() + 2
        while group_exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("PROCESS_OWNERSHIP_UNCLEAR")
            time.sleep(0.02)
        return completed()

    def finalize(self):
        """Persist an execution outcome, never a claim of mission completion."""
        self._gate.assert_activation(self._activation, owner_kind="mission",
                                     category="process", operation=self._activation.operation)
        collected = self._capture["result"] if self._capture is not None else None
        if self._returncode is None or (collected is None and self._cancel_result is None):
            raise RuntimeError("PROCESS_RESULT_NOT_READY")
        result = dict(collected) if collected is not None else {"exitCode": self._returncode}
        result.update(outputComplete=collected is not None, quiescenceVerified=False,
                      quiescenceScope="recorded-group-and-leader")
        absent = True
        for probe in (lambda: os.killpg(self.pid, 0), lambda: os.kill(self.pid, 0)):
            try:
                probe()
            except ProcessLookupError:
                continue
            except OSError:
                absent = False
                break
            else:
                absent = False
                break
        if not absent:
            return self._gate.outcome_unclear(self._activation,
                code="PROCESS_OWNERSHIP_UNCLEAR", receipt=result)
        result["quiescenceVerified"] = True
        if self._cancel_result is not None:
            code = {"timeout": "PROCESS_TIMEOUT", "cancelled": "PROCESS_CANCELLED",
                    "output_error": "PROCESS_OUTPUT_ERROR"}[self._stop_reason]
            return self._gate.fail(self._activation, code=code, receipt=result)
        if self._returncode != 0:
            return self._gate.fail(self._activation, code="PROCESS_EXIT_NONZERO", receipt=result)
        return self._gate.succeed(self._activation, result)

    async def supervise(self, *, timeout, max_bytes=65536):
        """Transfer collection and termination to one worker until settlement.

        The caller must not concurrently use wait/collect/cancel/close. On an
        uncertain cleanup the object and its descriptors remain caller-owned,
        with an unclear durable receipt; no background retry is launched.
        """
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Positive supervision timeout required")
        if type(max_bytes) is not int or not 0 < max_bytes <= 1048576:
            raise ValueError("Capture limit must be 1..1048576 bytes per stream")
        if self._closed or not self._release_attempted or self._supervision_started:
            raise RuntimeError("PROCESS_SUPERVISION_NOT_READY")
        self._supervision_started = True
        stop = threading.Event()
        deadline = time.monotonic() + timeout

        def work():
            try:
                while True:
                    remaining = deadline - time.monotonic()
                    if not self._gate.status().accepting_effects:
                        stop.set()
                    reason = "cancelled" if stop.is_set() else ("timeout" if remaining <= 0 else None)
                    if reason is not None:
                        self.cancel(reason=reason)
                        self.collect(timeout=2, max_bytes=max_bytes)
                        break
                    try:
                        self.collect(timeout=min(0.05, remaining), max_bytes=max_bytes)
                        break
                    except TimeoutError:
                        continue
            except Exception:
                # Reading a broken output pipe must still attempt owned group
                # termination. Do not retry the command or the failed read.
                try:
                    self.cancel(reason=self._stop_reason or "output_error")
                except Exception:
                    # Unverifiable cleanup retains both ownership and channels.
                    return self._gate.outcome_unclear(self._activation,
                        code="PROCESS_OWNERSHIP_UNCLEAR",
                        receipt={"quiescenceVerified": False,
                                 "quiescenceScope": "recorded-group-and-leader"})
            receipt = self.finalize()
            if receipt.state != "outcome_unclear":
                self.close()
            return receipt

        worker = asyncio.create_task(asyncio.to_thread(work))
        cancelled = False
        while True:
            try:
                receipt = await asyncio.shield(worker)
                break
            except asyncio.CancelledError:
                cancelled = True
                stop.set()
                # Repeated task.cancel() must not abandon the same worker.
                continue
        if cancelled:
            raise asyncio.CancelledError
        return receipt

    def close(self):
        if self._closed:
            return
        if self._release_writer is not None:
            os.close(self._release_writer)
            self._release_writer = None
        # Before release, EOF makes the attested helper exit without exec.
        # For a released live command, timeout preserves the owned object;
        # cancellation/collection must account for it instead of losing it.
        self.wait(timeout=2)
        for fd in (self.stdout_fd, self.stderr_fd):
            os.close(fd)
        self._closed = True


def spawn_owned_process(helper, *, gate, activation, arguments, cwd_fd, env, selected_argv=None):
    """Bind a gated action to a suspended child and private copies of inputs."""
    from effect_gate import canonical_digest
    gate.assert_activation(activation, owner_kind="mission", category="process", operation=activation.operation)
    if canonical_digest(activation.operation, arguments) != activation.payload_digest:
        raise RuntimeError("EFFECT_PAYLOAD_MISMATCH")
    arguments = json.loads(json.dumps(arguments, ensure_ascii=False, allow_nan=False))
    argv = _command_argv(activation, arguments, selected_argv)
    if (type(argv) is not list or not argv
            or any(type(s) is not str or not s or "\x00" in s for s in argv)):
        raise ValueError("Valid argv required")
    env = dict(env)
    executable = argv[0]
    if not os.path.isabs(executable):
        search_path = env.get("PATH")
        if ("/" in executable or "\\" in executable
                or type(search_path) is not str or not search_path
                or any(not os.path.isabs(part) for part in search_path.split(":"))):
            raise ValueError("Explicit absolute executable search path required")
        executable = shutil.which(executable, path=search_path)
        if executable is None:
            raise FileNotFoundError("PROCESS_EXECUTABLE_NOT_FOUND")
    descriptors = []
    pid = None
    try:
        release_r, release_w = os.pipe()
        descriptors.extend((release_r, release_w))
        stdout_r, stdout_w = os.pipe()
        descriptors.extend((stdout_r, stdout_w))
        stderr_r, stderr_w = os.pipe()
        descriptors.extend((stderr_r, stderr_w))
        null = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
        descriptors.append(null)
        pid = spawn_attested_at(helper, argv=[str(helper.path), "--release-fd", "7", "--", executable, *argv[1:]],
            cwd_fd=cwd_fd, env=dict(env), fd_map={0:null, 1:stdout_w, 2:stderr_w, 7:release_r})
        process = object.__new__(OwnedProcess)
        process._pid = pid
        process._returncode = None
        process._release_writer = release_w
        process.stdout_fd, process.stderr_fd = stdout_r, stderr_r
        process._arguments = arguments
        process._command_argv = argv
        process._executable = executable
        process._gate, process._activation = gate, activation
        process._release_attempted = process._closed = False
        process._capture = None
        process._cancel_result = None
        process._stop_reason = None
        process._supervision_started = False
        for transferred in (release_w, stdout_r, stderr_r):
            descriptors.remove(transferred)
        return process
    finally:
        for fd in descriptors:
            os.close(fd)


def record_and_release_process(gate, activation, *, pid, release_fd, arguments, executable=None, selected_argv=None):
    """Take ownership of the pipe writer, persist once, then release the child.

    Collection/reaping and terminal receipts remain the runner's responsibility.
    An error closes the writer without replay; uncertain dispatch must not retry.
    """
    from effect_gate import canonical_digest
    from startup_lease import _read_kernel_process_identity
    if type(release_fd) is not int or release_fd < 3:
        raise ValueError("Transferred release writer required")
    try:
        gate.assert_activation(activation, owner_kind="mission", category="process", operation=activation.operation)
        if canonical_digest(activation.operation, arguments) != activation.payload_digest:
            raise RuntimeError("EFFECT_PAYLOAD_MISMATCH")
        argv = _command_argv(activation, arguments, selected_argv)
        if (type(argv) is not list or not argv
                or any(type(item) is not str or not item or "\x00" in item for item in argv)):
            raise ValueError("Valid process argv required")
        executable = argv[0] if executable is None else executable
        if (type(executable) is not str or "\x00" in executable or not os.path.isabs(executable)
                or (os.path.isabs(argv[0]) and executable != argv[0])
                or (not os.path.isabs(argv[0]) and
                    ("/" in argv[0] or "\\" in argv[0] or os.path.basename(executable) != argv[0]))):
            raise ValueError("Resolved executable must match approved command")
        if (not stat.S_ISFIFO(os.fstat(release_fd).st_mode)
                or (fcntl.fcntl(release_fd, fcntl.F_GETFL) & os.O_ACCMODE) != os.O_WRONLY):
            raise ValueError("Transferred release writer required")
        identity = _read_kernel_process_identity(pid)
        if identity is None or identity.pgid != pid:
            raise RuntimeError("PROCESS_OWNERSHIP_UNCLEAR")
        ownership = dict(pid=pid, pgid=identity.pgid, start_time=identity.start_time,
                         executable=executable, argv_hash=hashlib.sha256(
                             json.dumps(argv, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest())
        gate.record_process_release(activation, ownership)
        if _read_kernel_process_identity(pid) != identity:
            raise RuntimeError("PROCESS_OWNERSHIP_UNCLEAR")
        gate.assert_activation(activation, owner_kind="mission", category="process", operation=activation.operation)
        if not gate.status().accepting_effects:
            raise ProcessReleaseStopped("PROCESS_STOPPED_BEFORE_RELEASE")
        if os.write(release_fd, b"\x01") != 1:
            raise RuntimeError("PROCESS_RELEASE_UNCLEAR")
        return ownership
    finally:
        os.close(release_fd)


def _check(code):
    if code:
        raise OSError(code, os.strerror(code))


def resolve_addfchdir(libc, *, macos_major):
    names = (("posix_spawn_file_actions_addfchdir", "posix_spawn_file_actions_addfchdir_np")
             if macos_major >= 26 else ("posix_spawn_file_actions_addfchdir_np",))
    for name in names:
        function = getattr(libc, name, None)
        if function is not None:
            return function
    raise RuntimeError("PROCESS_FCHDIR_UNAVAILABLE")


def spawn_attested_at(helper, *, argv, cwd_fd, env, fd_map):
    from native_helpers import AttestedHelper
    if sys.platform != "darwin":
        raise RuntimeError("PROCESS_FCHDIR_UNAVAILABLE")
    if not isinstance(helper, AttestedHelper):
        raise TypeError("Attested helper required")
    if (type(argv) is not list or len(argv) < 5
            or any(type(item) is not str or not item or "\x00" in item for item in argv)
            or argv[:4] != [str(helper.path), "--release-fd", "7", "--"]):
        raise ValueError("Blocked helper argv required")
    if (type(env) is not dict or set(env) - {"PATH", "LANG", "LC_ALL", "HOME", "TMPDIR"}
            or any(type(k) is not str or type(v) is not str or "\x00" in v for k, v in env.items())):
        raise ValueError("Sanitized environment required")
    if (type(fd_map) is not dict or set(fd_map) != {0, 1, 2, 7}
            or any(type(fd) is not int or fd < 0 for fd in fd_map.values())
            or type(cwd_fd) is not int or not stat.S_ISDIR(os.fstat(cwd_fd).st_mode)):
        raise ValueError("Explicit standard and release descriptors required")
    libc = ctypes.CDLL(None, use_errno=True)
    pointer = ctypes.POINTER(ctypes.c_void_p)
    addcwd = resolve_addfchdir(libc, macos_major=int(platform.mac_ver()[0].split(".")[0]))
    addcwd.argtypes = [pointer, ctypes.c_int]
    addcwd.restype = ctypes.c_int
    signatures = {
        "posix_spawn_file_actions_init": [pointer],
        "posix_spawn_file_actions_destroy": [pointer],
        "posix_spawn_file_actions_adddup2": [pointer, ctypes.c_int, ctypes.c_int],
        "posix_spawnattr_init": [pointer], "posix_spawnattr_destroy": [pointer],
        "posix_spawnattr_setflags": [pointer, ctypes.c_short],
        "posix_spawnattr_setpgroup": [pointer, ctypes.c_int],
        "posix_spawn": [ctypes.POINTER(ctypes.c_int), ctypes.c_char_p, pointer, pointer,
                        ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_char_p)],
    }
    for name, args in signatures.items():
        function = getattr(libc, name)
        function.argtypes, function.restype = args, ctypes.c_int
    actions, attrs = ctypes.c_void_p(), ctypes.c_void_p()
    actions_ready = attrs_ready = False
    owned = []
    try:
        _check(libc.posix_spawn_file_actions_init(ctypes.byref(actions)))
        actions_ready = True
        _check(libc.posix_spawnattr_init(ctypes.byref(attrs)))
        attrs_ready = True
        directory = fcntl.fcntl(cwd_fd, fcntl.F_DUPFD_CLOEXEC, 64)
        owned.append(directory)
        _check(addcwd(ctypes.byref(actions), directory))
        for target, source in fd_map.items():
            copied = fcntl.fcntl(source, fcntl.F_DUPFD_CLOEXEC, 64)
            owned.append(copied)
            _check(libc.posix_spawn_file_actions_adddup2(ctypes.byref(actions), copied, target))
        # SDK sys/spawn.h: SETPGROUP=0x0002, CLOEXEC_DEFAULT=0x4000.
        _check(libc.posix_spawnattr_setflags(ctypes.byref(attrs), 0x4002))
        _check(libc.posix_spawnattr_setpgroup(ctypes.byref(attrs), 0))
        encoded_argv = (ctypes.c_char_p * (len(argv) + 1))(*[os.fsencode(s) for s in argv], None)
        encoded_env = (ctypes.c_char_p * (len(env) + 1))(*[os.fsencode(f"{k}={v}") for k, v in env.items()], None)
        path = helper.revalidate_for_spawn()
        pid = ctypes.c_int()
        _check(libc.posix_spawn(ctypes.byref(pid), os.fsencode(path), ctypes.byref(actions),
                               ctypes.byref(attrs), encoded_argv, encoded_env))
        return pid.value
    finally:
        for fd in owned:
            os.close(fd)
        if attrs_ready:
            libc.posix_spawnattr_destroy(ctypes.byref(attrs))
        if actions_ready:
            libc.posix_spawn_file_actions_destroy(ctypes.byref(actions))
