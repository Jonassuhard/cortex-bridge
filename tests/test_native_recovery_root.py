"""Execute the unchanged production reader with a test-only Swift entry point.

No root bytes are printed. This proves local retention/erasure, not recovery
authentication or storage-effect acceptance.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from test_storage_broker_handshake import SOURCE, PROFILE


HARNESS = r'''
private func recoveryRootTest() -> Int32 {
    guard CommandLine.arguments.count == 3,
          let fd = Int32(CommandLine.arguments[1]) else { return 90 }
    let retained: Any = consumeRecoveryRoot(fd) as Any
    guard fcntl(fd, F_GETFD) == -1, errno == EBADF else { return 91 }
    if CommandLine.arguments[2] == "invalid" {
        return retained is SecretBuffer ? 92 : 0
    }
    guard let root = retained as? SecretBuffer, root.count == 32 else { return 93 }
    guard root.withUnsafeBytes({ bytes in
        bytes.enumerated().allSatisfy({ $0.element == UInt8($0.offset) })
    }) else { return 94 }
    root.zeroize()
    guard root.isZeroed else { return 95 }
    root.zeroize()
    return root.isZeroed ? 0 : 96
}
exit(recoveryRootTest())
'''


class NativeRecoveryRootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.uname().sysname != "Darwin":
            raise unittest.SkipTest("native recovery authority is macOS-only")
        cls.temp = tempfile.TemporaryDirectory(prefix="cortex-root-test-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(cls.temp.name) / "reader-test.swift"
        # Keep every production definition; replace only the final CLI entry.
        definitions, separator, tail = SOURCE.read_text().rpartition("exit(runMain())")
        if not separator or tail.strip():
            raise AssertionError("production entry point changed; review test harness")
        source.write_text(definitions + HARNESS)
        cls.binary = Path(cls.temp.name) / "reader-test"
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

    def run_reader(self, value, *, valid=False, hold_open=False):
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, value)
            if not hold_open:
                os.close(write_fd)
                write_fd = None
            result = subprocess.run([str(self.binary), str(read_fd), "valid" if valid else "invalid"],
                pass_fds=(read_fd,), capture_output=True, timeout=4)
            self.assertEqual(result.stdout, b"")
            self.assertEqual(result.stderr, b"")
            self.assertEqual(result.returncode, 0)
        finally:
            os.close(read_fd)
            if write_fd is not None:
                os.close(write_fd)

    def test_exact_root_survives_reader_return_and_can_be_zeroized(self):
        self.run_reader(bytes(range(32)), valid=True)

    def test_invalid_lengths_do_not_return_authority(self):
        for size in (0, 1, 31, 33, 64):
            with self.subTest(size=size):
                self.run_reader(bytes(range(size)))

    def test_root_without_eof_is_not_accepted(self):
        start = time.monotonic()
        self.run_reader(bytes(range(32)), hold_open=True)
        self.assertLess(time.monotonic() - start, 3)
