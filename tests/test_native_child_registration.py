"""Real suspended-child registration tests, using a test-only native entry.

The fixture only writes one byte and exits; it performs no storage operation.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_storage_broker_handshake import SOURCE, PROFILE

HARNESS = r'''
private func childRegistrationTest() -> Int32 {
    if CommandLine.arguments.last == "--owned-fixture-child" {
        var byte: UInt8 = 42
        return Darwin.write(1, &byte, 1) == 1 ? 0 : 99
    }
    let executable = CommandLine.arguments[0]
    let executableFD = open(executable, O_RDONLY | O_NOFOLLOW)
    guard executableFD >= 0 else { return 90 }
    defer { close(executableFD) }
    let authorityDeadline = monotonicNanoseconds()! + 2_000_000_000
    if CommandLine.arguments.last == "foreign" {
        return RegisteredNativeChild.captureSuspended(pid: getpid(), executableFD: executableFD, deadline: authorityDeadline) == nil ? 0 : 91
    }
    var pipeFDs: [Int32] = [-1, -1]
    guard pipe(&pipeFDs) == 0 else { return 92 }
    defer { close(pipeFDs[0]); if pipeFDs[1] >= 0 { close(pipeFDs[1]) } }
    var actions: posix_spawn_file_actions_t?
    var attributes: posix_spawnattr_t?
    guard posix_spawn_file_actions_init(&actions) == 0,
          posix_spawnattr_init(&attributes) == 0 else { return 93 }
    defer { posix_spawn_file_actions_destroy(&actions); posix_spawnattr_destroy(&attributes) }
    guard posix_spawn_file_actions_adddup2(&actions, pipeFDs[1], 1) == 0,
          posix_spawnattr_setflags(&attributes, Int16(POSIX_SPAWN_START_SUSPENDED | POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_CLOEXEC_DEFAULT)) == 0,
          posix_spawnattr_setpgroup(&attributes, 0) == 0 else { return 94 }
    var pid: pid_t = 0
    // This scenario models a child ignoring TERM, so the no-resume rule must
    // come from controller state, not merely the OS having already killed it.
    let ignoreTerm = CommandLine.arguments.last == "term-then-kill"
    if ignoreTerm { signal(SIGTERM, SIG_IGN) }
    let result = withCStringArray([executable, "--owned-fixture-child"]) { args in
        withCStringArray(childEnvironment) { environment in
            executable.withCString { posix_spawn(&pid, $0, &actions, &attributes, args, environment) }
        }
    }
    if ignoreTerm { signal(SIGTERM, SIG_DFL) }
    guard result == 0 else { return 95 }
    var reaped = false
    defer {
        // Test-only cleanup of our still-waitable direct child. Never signal a
        // PID after waitpid has consumed it. Production cleanup is separate.
        if !reaped {
            var info = siginfo_t()
            if waitid(P_PID, id_t(pid), &info, WEXITED | WSTOPPED | WCONTINUED | WNOHANG | WNOWAIT) == 0 {
                _ = kill(pid, SIGKILL)
                var status: Int32 = 0
                _ = waitpid(pid, &status, 0)
            }
        }
    }
    close(pipeFDs[1]); pipeFDs[1] = -1
    var readiness = pollfd(fd: pipeFDs[0], events: Int16(POLLIN), revents: 0)
    guard poll(&readiness, 1, 0) == 0 else { return 96 }
    if CommandLine.arguments.last == "wrong-image" {
        let wrong = open("/usr/bin/true", O_RDONLY)
        defer { close(wrong) }
        guard wrong >= 0,
              RegisteredNativeChild.captureSuspended(pid: pid, executableFD: wrong, deadline: authorityDeadline) == nil else { return 97 }
        return poll(&readiness, 1, 0) == 0 ? 0 : 98
    }
    guard let child = RegisteredNativeChild.captureSuspended(pid: pid, executableFD: executableFD, deadline: authorityDeadline) else { return 100 }
    guard child.identity.pid == pid, child.identity.parentPID == getpid(),
          child.identity.groupID == pid, child.identity.uid == geteuid(),
          child.identity.startSeconds > 0 else { return 101 }
    var stillWaitable = siginfo_t()
    guard waitid(P_PID, id_t(pid), &stillWaitable, WSTOPPED | WNOHANG | WNOWAIT) == 0,
          stillWaitable.si_pid == pid, stillWaitable.si_code == CLD_STOPPED else { return 102 }
    if CommandLine.arguments.last == "expired" {
        guard RegisteredNativeChild.captureSuspended(pid: pid, executableFD: executableFD, deadline: 0) == nil,
              !child.resume(deadline: 0), !child.signalGroup(SIGKILL, deadline: 0),
              child.reapExited(deadline: 0) == nil, !child.groupIsAbsent(deadline: 0),
              poll(&readiness, 1, 0) == 0 else { return 113 }
        return 0
    }
    if CommandLine.arguments.last == "term-then-kill" {
        guard child.signalGroup(SIGTERM, deadline: authorityDeadline),
              !child.resume(deadline: authorityDeadline) else { return 114 }
    }
    if ["kill-stopped", "term-then-kill"].contains(CommandLine.arguments.last!) {
        guard child.signalGroup(SIGKILL, deadline: authorityDeadline), !child.signalGroup(SIGKILL, deadline: authorityDeadline) else { return 108 }
        let deadline = monotonicSeconds() + 2
        while monotonicSeconds() < deadline {
            var kernelExit = siginfo_t()
            if waitid(P_PID, id_t(pid), &kernelExit, WEXITED | WNOHANG | WNOWAIT) == 0,
               kernelExit.si_pid == pid, kernelExit.si_signo != SIGCHLD { return 112 }
            if let status = child.reapExited(deadline: authorityDeadline) {
                reaped = true
                guard status & 0x7f == SIGKILL, !child.signalGroup(SIGTERM, deadline: authorityDeadline), !child.resume(deadline: authorityDeadline) else { return 109 }
                return child.groupIsAbsent(deadline: authorityDeadline) ? 0 : 110
            }
            usleep(1_000)
        }
        return 111
    }
    guard child.resume(deadline: authorityDeadline), !child.resume(deadline: authorityDeadline) else { return 103 }
    guard poll(&readiness, 1, 2_000) == 1 else { return 104 }
    var byte: UInt8 = 0
    guard Darwin.read(pipeFDs[0], &byte, 1) == 1, byte == 42 else { return 105 }
    var status: Int32 = 0
    guard waitpid(pid, &status, 0) == pid else { return 106 }
    reaped = true
    return status == 0 ? 0 : 107
}
exit(childRegistrationTest())
'''


class NativeChildRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.uname().sysname != "Darwin":
            raise unittest.SkipTest("suspended registration is macOS-only")
        cls.temp = tempfile.TemporaryDirectory(prefix="cortex-child-test-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(cls.temp.name) / "registration.swift"
        definitions, separator, tail = SOURCE.read_text().rpartition("exit(runMain())")
        if not separator or tail.strip():
            raise AssertionError("production entry point changed; review harness")
        source.write_text(definitions + HARNESS)
        cls.binary = Path(cls.temp.name) / "registration"
        profile = json.loads(PROFILE.read_text())
        command = ["/Library/Developer/CommandLineTools/usr/bin/swiftc", *profile["swiftc"],
                   str(source), "-o", str(cls.binary)]
        for framework in profile["frameworks"]:
            command.extend(["-framework", framework])
        result = subprocess.run(command, capture_output=True, text=True, env={**os.environ,
            "SDKROOT": "/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk",
            "MACOSX_DEPLOYMENT_TARGET": "26.5"})
        if result.returncode:
            raise AssertionError(result.stderr)

    def assert_scenario(self, scenario):
        result = subprocess.run([str(self.binary), scenario], capture_output=True, timeout=8)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")
        self.assertEqual(result.returncode, 0)

    def test_stopped_child_registered_before_first_byte_then_resumed_once(self):
        self.assert_scenario("resume")

    def test_wrong_executable_vnode_never_authorizes_resume(self):
        self.assert_scenario("wrong-image")

    def test_non_child_never_produces_registration(self):
        self.assert_scenario("foreign")

    def test_registered_group_killed_once_and_never_signaled_after_reap(self):
        self.assert_scenario("kill-stopped")

    def test_expired_deadline_cannot_register_resume_signal_or_reap(self):
        self.assert_scenario("expired")

    def test_shutdown_request_never_allows_resume(self):
        self.assert_scenario("term-then-kill")
