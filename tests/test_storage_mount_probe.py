#!/usr/bin/env python3
"""Native contract tests for the descriptor-only storage mount probe."""

import json
import ctypes
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "native/macos/storage_mount_probe.swift"
MNT_IGNORE_OWNERS = 0x00200000
MNT_NOATIME = 0x10000000


class StorageMountProbeTests(unittest.TestCase):
    """The probe must inspect precisely the inherited descriptor it receives."""

    @classmethod
    def setUpClass(cls):
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.temporary_directory.name) / "storage-mount-probe"
        cls.source_exists = SOURCE.is_file()
        if cls.source_exists:
            completed = subprocess.run(
                ["xcrun", "swiftc", str(SOURCE), "-o", str(cls.binary)],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                raise AssertionError(
                    "storage mount probe did not compile:\n"
                    f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
                )

    @classmethod
    def tearDownClass(cls):
        cls.temporary_directory.cleanup()

    def setUp(self):
        self.assertTrue(
            self.source_exists,
            f"missing required native helper: {SOURCE}",
        )

    def run_probe(self, *arguments, pass_fds=()):
        return subprocess.run(
            [str(self.binary), *arguments],
            pass_fds=pass_fds,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_reports_facts_for_the_exact_inherited_directory_descriptor(self):
        with tempfile.TemporaryDirectory() as root:
            directory_fd = os.open(
                root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
            try:
                completed = self.run_probe(
                    "--fd", str(directory_fd), pass_fds=(directory_fd,)
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertTrue(completed.stdout.endswith("\n"))
                self.assertEqual(completed.stdout.count("\n"), 1)
                payload = json.loads(completed.stdout)
                self.assertEqual(
                    set(payload),
                    {
                        "schema_version",
                        "st_dev_u32",
                        "fsid_u32",
                        "flags",
                        "filesystem_type",
                        "mount_from",
                        "mount_on",
                        "volume_uuid",
                    },
                )
                self.assertEqual(payload["schema_version"], 1)
                # Independent OS observation, not an expected value copied from
                # the executable or from environment configuration.
                class Attributes(ctypes.Structure):
                    _fields_ = [("bitmapcount", ctypes.c_uint16), ("reserved", ctypes.c_uint16),
                                ("common", ctypes.c_uint32), ("volume", ctypes.c_uint32),
                                ("directory", ctypes.c_uint32), ("file", ctypes.c_uint32),
                                ("fork", ctypes.c_uint32)]
                attributes = Attributes(5, 0, 0, 0x80040000, 0, 0, 0)
                buffer = ctypes.create_string_buffer(20)
                function = ctypes.CDLL(None, use_errno=True).fgetattrlist
                function.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong]
                function.restype = ctypes.c_int
                self.assertEqual(function(directory_fd, ctypes.byref(attributes), buffer, 20, 0), 0)
                self.assertEqual(int.from_bytes(buffer.raw[:4], "little"), 20)
                self.assertEqual(payload["volume_uuid"], str(UUID(bytes=buffer.raw[4:20])))
                self.assertNotEqual(payload["volume_uuid"], str(UUID(int=0)))
                self.assertEqual(payload["st_dev_u32"], os.fstat(directory_fd).st_dev & 0xffffffff)
                self.assertEqual(len(payload["fsid_u32"]), 2)
                self.assertTrue(all(type(value) is int and 0 <= value <= 0xffffffff for value in payload["fsid_u32"]))
                self.assertIsInstance(payload["flags"], int)
                self.assertGreaterEqual(payload["flags"], 0)
                ownership_ignored = bool(payload["flags"] & MNT_IGNORE_OWNERS)
                noatime = bool(payload["flags"] & MNT_NOATIME)
                self.assertIsInstance(ownership_ignored, bool)
                self.assertIsInstance(noatime, bool)
                for key in ("filesystem_type", "mount_from", "mount_on"):
                    self.assertIsInstance(payload[key], str)
                    self.assertFalse(any(ord(character) < 32 for character in payload[key]))
            finally:
                os.close(directory_fd)

    def test_rejects_a_closed_descriptor(self):
        with tempfile.TemporaryDirectory() as root:
            directory_fd = os.open(
                root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
            os.close(directory_fd)
            completed = self.run_probe("--fd", str(directory_fd))
        self.assertEqual(completed.returncode, 64)
        self.assertEqual(completed.stdout, "")

    def test_rejects_an_inherited_regular_file_descriptor(self):
        with tempfile.NamedTemporaryFile() as file:
            file_fd = os.open(file.name, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                completed = self.run_probe(
                    "--fd", str(file_fd), pass_fds=(file_fd,)
                )
            finally:
                os.close(file_fd)
        self.assertEqual(completed.returncode, 64)
        self.assertEqual(completed.stdout, "")

    def test_rejects_unexpected_or_non_decimal_arguments(self):
        for arguments in (
            (),
            ("--fd",),
            ("--fd", "not-a-decimal"),
            ("--fd", "-1"),
            ("--fd", "0", "extra"),
            ("--path", "/tmp/not-accepted"),
        ):
            with self.subTest(arguments=arguments):
                completed = self.run_probe(*arguments)
                self.assertEqual(completed.returncode, 64)
                self.assertEqual(completed.stdout, "")

    def test_rejects_a_descriptor_number_replaced_with_a_regular_file(self):
        with tempfile.TemporaryDirectory() as root, tempfile.NamedTemporaryFile() as file:
            directory_fd = os.open(
                root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
            file_fd = os.open(file.name, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.dup2(file_fd, directory_fd)
                completed = self.run_probe(
                    "--fd", str(directory_fd), pass_fds=(directory_fd,)
                )
            finally:
                os.close(file_fd)
                os.close(directory_fd)
        self.assertEqual(completed.returncode, 64)
        self.assertEqual(completed.stdout, "")


if __name__ == "__main__":
    unittest.main()
