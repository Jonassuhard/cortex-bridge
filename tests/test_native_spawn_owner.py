"""Real production spawn ownership, with a harmless test-only child entry."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_storage_broker_handshake import SOURCE, PROFILE

HARNESS = r'''
private func spawnOwnerTest() -> Int32 {
    if CommandLine.arguments.count == 3, CommandLine.arguments[1] == "--owned-child" {
        guard let foreignFD = Int32(CommandLine.arguments[2]),
              fcntl(foreignFD, F_GETFD) == -1, errno == EBADF else { return 80 }
        var byte: UInt8 = 42
        return Darwin.write(1, &byte, 1) == 1 ? 0 : 81
    }
    let deadline = monotonicNanoseconds()! + 3_000_000_000
    let owner = NativeSpawnOwner()
    let foreign = open("/dev/null", O_RDONLY)
    guard foreign > 2 else { return 82 }
    defer { close(foreign) }
    _ = fcntl(foreign, F_SETFD, 0)
    let executable = CommandLine.arguments[0]
    if CommandLine.arguments.count == 3, CommandLine.arguments[1] == "invalid-executable" {
        let path = CommandLine.arguments[2]
        let before = (3..<128).filter { fcntl(Int32($0), F_GETFD) >= 0 }
        guard owner.spawnSuspended(executable: path, argv: [path], deadline: deadline) == nil,
              owner.children.isEmpty,
              (3..<128).filter({ fcntl(Int32($0), F_GETFD) >= 0 }) == before else { return 92 }
        return 0
    }
    if CommandLine.arguments.last == "missing" {
        guard owner.spawnSuspended(executable: "/does-not-exist/cortex-test",
            argv: ["/does-not-exist/cortex-test"], deadline: deadline) == nil,
            owner.children.isEmpty else { return 83 }
        return 0
    }
    guard let child = owner.spawnSuspended(executable: executable,
        argv: [executable, "--owned-child", String(foreign)], deadline: deadline),
        owner.children.count == 1, owner.children[0] === child else { return 84 }
    var reaped = false
    defer {
        if !reaped {
            // Test-only cleanup; exact direct-child waitability is established
            // before this signal, and no signal occurs after our waitpid.
            var event = siginfo_t()
            if waitid(P_PID, id_t(child.pid), &event, WEXITED | WSTOPPED | WCONTINUED | WNOHANG | WNOWAIT) == 0 {
                _ = kill(child.pid, SIGKILL)
                var status: Int32 = 0
                _ = waitpid(child.pid, &status, 0)
            }
        }
    }
    var readiness = pollfd(fd: child.stdoutFD, events: Int16(POLLIN), revents: 0)
    guard poll(&readiness, 1, 0) == 0,
          !child.resume(deadline: deadline) else { return 85 }
    if CommandLine.arguments.last == "expired-registration" {
        guard !child.register(deadline: 0), child.unresolved,
              !child.register(deadline: deadline), !child.resume(deadline: deadline),
              owner.children.count == 1, !owner.releaseCompleted(child, deadline: deadline),
              poll(&readiness, 1, 0) == 0 else { return 86 }
        return 0
    }
    guard child.register(deadline: deadline), !child.unresolved,
          child.resume(deadline: deadline), !child.resume(deadline: deadline),
          poll(&readiness, 1, 2_000) == 1 else { return 87 }
    var byte: UInt8 = 0
    guard Darwin.read(child.stdoutFD, &byte, 1) == 1, byte == 42 else { return 88 }
    while monotonicNanoseconds()! < deadline {
        if let status = child.registration?.reapExited(deadline: deadline) {
            reaped = true
            guard status == 0 else { return 89 }
            guard owner.releaseCompleted(child, deadline: deadline), owner.children.isEmpty,
                  child.stdinFD == -1, child.stdoutFD == -1, child.stderrFD == -1 else { return 90 }
            return 0
        }
        usleep(1_000)
    }
    return 91
}
exit(spawnOwnerTest())
'''


class NativeSpawnOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.uname().sysname != "Darwin":
            raise unittest.SkipTest("native spawn ownership is macOS-only")
        cls.temp = tempfile.TemporaryDirectory(prefix="cortex-spawn-test-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(cls.temp.name) / "spawn.swift"
        definitions, separator, tail = SOURCE.read_text().rpartition("exit(runMain())")
        if not separator or tail.strip():
            raise AssertionError("production entry point changed; review harness")
        source.write_text(definitions + HARNESS)
        cls.binary = Path(cls.temp.name) / "spawn"
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

    def test_owned_child_registered_before_resume_without_inheriting_foreign_fd(self):
        self.assert_scenario("success")

    def test_failed_registration_retains_suspended_owner_without_signal_authority(self):
        self.assert_scenario("expired-registration")

    def test_missing_executable_creates_no_child_owner(self):
        self.assert_scenario("missing")

    def test_exec_format_error_closes_setup_descriptors(self):
        invalid = Path(self.temp.name) / "invalid-executable"
        invalid.write_bytes(b"not an executable\n")
        invalid.chmod(0o700)
        result = subprocess.run([str(self.binary), "invalid-executable", str(invalid)],
                                capture_output=True, timeout=8)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout + result.stderr, b"")
