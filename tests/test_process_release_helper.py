import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest


class ProcessReleaseHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.binary = Path(cls.temp.name) / "process-release"
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / "native/macos/process_release.swift"
        self.assertTrue(source.is_file(), "Native process-release source is missing")
        if self.binary.is_file():
            return
        result = subprocess.run(["xcrun", "swiftc", str(source), "-o", str(self.binary)],
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stderr)

    def launch(self, command=None):
        reader, writer = os.pipe()
        try:
            child = subprocess.Popen([str(self.binary), "--release-fd", str(reader), "--",
                                      *(command or ["/bin/echo", "EXECUTED"])],
                pass_fds=(reader,), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        finally:
            os.close(reader)
        def cleanup():
            try:
                os.close(writer)
            except OSError:
                pass
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)
        self.addCleanup(cleanup)
        return child, writer

    def test_command_waits_for_release_byte(self):
        child, writer = self.launch()
        self.assertFalse(select.select([child.stdout], [], [], 0.25)[0])
        self.assertIsNone(child.poll())
        os.write(writer, b"\x01")
        output, error = child.communicate(timeout=5)
        self.assertEqual((child.returncode, output, error), (0, b"EXECUTED\n", b""))

    def test_eof_never_executes_command(self):
        child, writer = self.launch()
        os.close(writer)
        output, _ = child.communicate(timeout=5)
        self.assertEqual(child.returncode, 125)
        self.assertEqual(output, b"")

    def test_wrong_byte_never_executes_command(self):
        child, writer = self.launch()
        os.write(writer, b"\x00")
        output, _ = child.communicate(timeout=5)
        self.assertEqual(child.returncode, 125)
        self.assertEqual(output, b"")

    def test_release_channel_does_not_consume_command_stdin(self):
        child, writer = self.launch(["/bin/cat"])
        os.write(writer, b"\x01")
        output, error = child.communicate(b"INPUT", timeout=5)
        self.assertEqual((child.returncode, output, error), (0, b"INPUT", b""))

    def test_invalid_release_descriptor_is_refused(self):
        result = subprocess.run([str(self.binary), "--release-fd", "0", "--", "/bin/echo", "EXECUTED"],
                                input=b"\x01", capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 125)
        self.assertEqual(result.stdout, b"")

    def test_regular_file_cannot_supply_release_authority(self):
        with tempfile.TemporaryFile() as source:
            source.write(b"\x01")
            source.seek(0)
            result = subprocess.run([str(self.binary), "--release-fd", str(source.fileno()),
                                     "--", "/bin/echo", "EXECUTED"],
                                    pass_fds=(source.fileno(),), capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 125)
        self.assertEqual(result.stdout, b"")

    def test_missing_executable_fails_without_shell_fallback(self):
        child, writer = self.launch(["/cortex-fixture-executable-does-not-exist"])
        os.write(writer, b"\x01")
        output, _ = child.communicate(timeout=5)
        self.assertEqual(child.returncode, 127)
        self.assertEqual(output, b"")


if __name__ == "__main__":
    unittest.main()
