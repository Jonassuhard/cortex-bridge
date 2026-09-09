"""Real probe invocation, not an injected mount-facts success fixture."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import native_helpers


class NativeMountReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.temp.name) / 'probe'
        source = Path(__file__).resolve().parents[1] / 'native/macos/storage_mount_probe.swift'
        subprocess.run(['xcrun', 'swiftc', str(source), '-o', str(cls.binary)], check=True, capture_output=True)
        cls.binary.chmod(0o700)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def reader(self):
        self.assertTrue(hasattr(native_helpers, 'NativeMountReader'), 'attested native reader missing')
        attested = native_helpers.attest_mount_probe(self.binary)
        self.addCleanup(attested.close)
        reader = native_helpers.NativeMountReader(attested)
        self.addCleanup(reader.close)
        return reader

    def test_observes_real_volume_without_consuming_caller_descriptor(self):
        reader = self.reader()
        fd = os.open(self.temp.name, os.O_RDONLY | os.O_DIRECTORY)
        try:
            facts = reader(fd)
            self.assertEqual(facts.st_dev_u32, os.fstat(fd).st_dev & 0xffffffff)
            self.assertNotEqual(facts.filesystem_type, 'unknown')
            self.assertNotEqual(facts.fsid_u32, (0, 0))
            self.assertIsNotNone(facts.volume_uuid)
            self.assertEqual(reader(fd), facts)
        finally:
            os.close(fd)

    def test_rejects_regular_file_before_execution(self):
        reader = self.reader()
        fd = os.open(self.binary, os.O_RDONLY)
        try:
            with self.assertRaises(native_helpers.NativeHelperAttestationError):
                reader(fd)
        finally:
            os.close(fd)

    def test_rejects_closed_attestation(self):
        reader = self.reader()
        reader.executable.close()
        fd = os.open(self.temp.name, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with self.assertRaises(native_helpers.NativeHelperAttestationError):
                reader(fd)
        finally:
            os.close(fd)

    def test_installed_factory_exposes_observed_volume_facts(self):
        from test_installed_storage_runtime import InstalledRuntimeTests, FakeLocks
        from installed_storage_runtime import InstalledStorageRuntime
        # Bootstrap bytes are supplied at the previously tested attestation
        # boundary; native compilation, executable attestation and probe are real.
        with tempfile.TemporaryDirectory() as directory:
            home, handle, snapshot = InstalledRuntimeTests().manifest_consumer_fixture(directory)
            with mock.patch('installed_storage_runtime._validate_bootstrap_handle', return_value=snapshot), \
                 mock.patch('installed_storage_runtime.attest_broker_executable', side_effect=lambda path: native_helpers.attest_broker_executable(self.binary)), \
                 mock.patch('installed_storage_runtime.attest_mount_probe', side_effect=lambda path: native_helpers.attest_mount_probe(self.binary)):
                runtime = InstalledStorageRuntime.from_installed_home_locked(home, FakeLocks(home), handle)
            try:
                fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    facts = runtime.fd_probe(fd)
                    self.assertNotEqual(facts.filesystem_type, 'unknown')
                    self.assertIsNotNone(facts.volume_uuid)
                finally:
                    os.close(fd)
            finally:
                runtime.close()

    def test_timeout_retains_one_process_and_refuses_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'slow-probe'
            script.write_text('#!/bin/sh\nexec /bin/sleep 3\n')
            script.chmod(0o700)
            attested = native_helpers.attest_mount_probe(script)
            reader = native_helpers.NativeMountReader(attested)
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaisesRegex(native_helpers.NativeHelperAttestationError, 'timed out'):
                    reader(fd)
                process = reader._process
                self.assertIsNone(process.poll())
                with self.assertRaisesRegex(native_helpers.NativeHelperAttestationError, 'unresolved'):
                    reader(fd)
                self.assertIs(reader._process, process)
                with self.assertRaisesRegex(native_helpers.NativeHelperAttestationError, 'unresolved'):
                    reader.close()
            finally:
                if reader._process is not None:
                    reader._process.wait(timeout=5)
                reader.close()
                attested.close()
                os.close(fd)

    def test_malformed_output_is_not_converted_to_mount_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'invalid-probe'
            script.write_text('#!/bin/sh\nprintf "{}"\n')
            script.chmod(0o700)
            attested = native_helpers.attest_mount_probe(script)
            reader = native_helpers.NativeMountReader(attested)
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaises(native_helpers.NativeHelperAttestationError):
                    reader(fd)
            finally:
                reader.close()
                attested.close()
                os.close(fd)

    def test_replaced_executable_is_rejected_before_spawn(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'probe'
            script.write_bytes(self.binary.read_bytes())
            script.chmod(0o700)
            attested = native_helpers.attest_mount_probe(script)
            reader = native_helpers.NativeMountReader(attested)
            script.rename(Path(directory) / 'original')
            script.write_text('#!/bin/sh\nexit 0\n')
            script.chmod(0o700)
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaises(native_helpers.NativeHelperAttestationError):
                    reader(fd)
                self.assertIsNone(reader._process)
            finally:
                reader.close()
                attested.close()
                os.close(fd)
