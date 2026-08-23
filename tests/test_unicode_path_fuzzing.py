"""Unicode path fuzzing and encoding boundary tests for ToolExecutor.

Covers: emoji/CJK/RTL filenames, null bytes, BOM markers, path homoglyphs,
traversal disguised with unicode, and mixed-encoding content.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from executor.tools import (
    MAX_READ_BYTES,
    ToolDenied,
    ToolError,
    ToolExecutor,
)


class UnicodePathFuzzingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = Path(self._tmp.name)
        self.tools = ToolExecutor(self.ws)

    # --- null byte rejection ------------------------------------------------

    async def test_null_byte_in_filename_is_refused(self):
        names = [
            "file\x00.txt",
            "\x00visible.txt",
            "ok-before\x00hidden",
        ]
        for name in names:
            with self.subTest(name=name):
                with self.assertRaises(ToolDenied) as cm:
                    self.tools._resolve(name)
                self.assertEqual(cm.exception.code, "MALFORMED_PATH")

    # --- absolute / traversal disguised with tricks -------------------------

    async def test_percent_encoded_dots_are_literal_filenames(self):
        """Percent-encoded dots (%2e) are literal chars, not traversal.
        resolve_in_workspace does not decode URL-encoding — these are just
        ordinary filenames that won't match any real file."""
        for path in ("..%2F..%2Fetc%2Fpasswd", "%2e%2e%2f%2e%2e%2fetc%2fpasswd"):
            with self.subTest(path=path):
                # These are valid relative paths with literal % chars.
                target = self.tools._resolve(path)
                self.assertEqual(target, (self.ws / path).resolve())

    async def test_leading_tilde_is_refused(self):
        with self.assertRaises(ToolDenied) as cm:
            self.tools._resolve("~/.ssh/id_rsa")
        self.assertEqual(cm.exception.code, "ABSOLUTE_PATH")

    async def test_windows_absolute_path_is_refused(self):
        for path in ("C:\\Windows\\System32", "C:/Windows/System32"):
            with self.subTest(path=path):
                with self.assertRaises(ToolDenied) as cm:
                    self.tools._resolve(path)
                self.assertEqual(cm.exception.code, "ABSOLUTE_PATH")

    # --- homoglyph / unicode traversal attempts -----------------------------

    async def test_homoglyph_slash_is_just_another_filename(self):
        """Fullwidth solidus (U+FF0F) and division slash (U+2215) are not path
        separators on any OS — resolve_in_workspace treats them as literal chars."""
        name = "\uff0fetc\uff0fpasswd"
        target = self.tools._resolve(name)
        # The path is WS / the literal chars — not an escape.
        self.assertEqual(target, (self.ws / name).resolve())

    async def test_rtl_override_character_in_path(self):
        """U+202E (RIGHT-TO-LEFT OVERRIDE) is a literal char in the filename."""
        name = "safe\u202efdp.exe"
        (self.ws / name).write_text("clean", encoding="utf-8")
        result = await self.tools.read_file(name)
        self.assertEqual(result["content"], "clean")

    # --- unicode filenames (emoji, CJK, RTL, Arabic) -----------------------

    async def test_emoji_filename_read_write(self):
        name = "\U0001f680-launch-\U0001f31f.txt"
        content = "rocket"
        await self.tools.write_file(name, content)
        result = await self.tools.read_file(name)
        self.assertEqual(result["content"], content)
        self.assertEqual(result["size"], len(content))

    async def test_cjk_filename(self):
        name = "\u65e5\u672c\u8a9e-\u30c6\u30b9\u30c8.txt"
        content = "\u3053\u3093\u306b\u3061\u306f"
        await self.tools.write_file(name, content)
        result = await self.tools.read_file(name)
        self.assertEqual(result["content"], content)

    async def test_arabic_rtl_filename(self):
        name = "\u0627\u062e\u062a\u0628\u0627\u0631-\u0645\u0644\u0641.txt"
        content = "\u0645\u0631\u062d\u0628\u0627\u064b"
        await self.tools.write_file(name, content)
        result = await self.tools.read_file(name)
        self.assertEqual(result["content"], content)

    async def test_mixed_script_filename(self):
        name = "r\u00e9sum\u00e9_\u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430_\u2714.txt"
        content = "mixed scripts ok"
        await self.tools.write_file(name, content)
        self.assertTrue((self.ws / name).is_file())

    # --- BOM handling -------------------------------------------------------

    async def test_utf8_bom_file_is_read_normally(self):
        """UTF-8 files with BOM are read without rejection."""
        (self.ws / "bom.txt").write_bytes(b"\xef\xbb\xbfUTF-8 with BOM\n")
        result = await self.tools.read_file("bom.txt")
        self.assertIn("UTF-8 with BOM", result["content"])

    async def test_utf16_le_file_is_rejected_as_binary(self):
        """UTF-16 LE files contain null bytes in the first 8KB
        (e.g. the BOM \\xff\\xfe itself has \\x00), so read_file
        rejects them as BINARY_FILE."""
        (self.ws / "utf16.txt").write_bytes(
            b"\xff\xfeH\x00e\x00l\x00l\x00o\x00\n\x00"
        )
        with self.assertRaises(ToolDenied) as cm:
            await self.tools.read_file("utf16.txt")
        self.assertEqual(cm.exception.code, "BINARY_FILE")

    # --- empty and whitespace-only paths ------------------------------------

    async def test_empty_path_is_refused(self):
        with self.assertRaises(ToolDenied) as cm:
            self.tools._resolve("")
        self.assertEqual(cm.exception.code, "MALFORMED_PATH")

    async def test_whitespace_only_path_is_refused(self):
        for path in ("   ", "\t", "\n"):
            with self.subTest(repr(path)):
                with self.assertRaises(ToolDenied) as cm:
                    self.tools._resolve(path)
                self.assertEqual(cm.exception.code, "MALFORMED_PATH")

    # --- long path ----------------------------------------------------------

    async def test_reasonably_long_path_works(self):
        name = "a" * 200 + ".txt"
        content = "long path ok"
        await self.tools.write_file(name, content)
        result = await self.tools.read_file(name)
        self.assertEqual(result["content"], content)

    # --- write through symlink created after resolution --------------------

    async def test_write_refuses_symlink_to_outside(self):
        outside_dir = Path("/tmp/cortex-test-outside-write")
        outside_dir.mkdir(exist_ok=True)
        self.addCleanup(lambda: outside_dir.rmdir() if outside_dir.exists() else None)
        outside = outside_dir / "outside-write.txt"
        outside.write_text("do not touch", encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        link = self.ws / "write-link.txt"
        try:
            link.symlink_to(outside.resolve())
        except OSError:
            self.skipTest("symlinks unavailable")
        # resolve_in_workspace detects the symlink escape
        with self.assertRaises(ToolDenied) as cm:
            await self.tools.write_file("write-link.txt", "payload")
        self.assertEqual(cm.exception.code, "SYMLINK_ESCAPE")
        self.assertEqual(outside.read_text(), "do not touch")

    async def test_patch_refuses_symlink_to_outside(self):
        outside_dir = Path("/tmp/cortex-test-outside-patch")
        outside_dir.mkdir(exist_ok=True)
        self.addCleanup(lambda: outside_dir.rmdir() if outside_dir.exists() else None)
        outside = outside_dir / "patch-outside.txt"
        outside.write_text("keep me", encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        link = self.ws / "patch-link.txt"
        try:
            link.symlink_to(outside.resolve())
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaises(ToolDenied) as cm:
            await self.tools.apply_patch("patch-link.txt", [
                {"old": "keep me", "new": "hacked"}
            ])
        self.assertEqual(cm.exception.code, "SYMLINK_ESCAPE")
        self.assertEqual(outside.read_text(), "keep me")


class BinaryDetectionTest(unittest.TestCase):
    def test_null_byte_in_first_8k_is_refused(self):
        """Binary detection: any null byte in first 8192 bytes → BINARY_FILE."""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            tools = ToolExecutor(ws)
            (ws / "binary.bin").write_bytes(b"header\x00" + b"safe" * 2000)

            async def _read():
                await tools.read_file("binary.bin")

            import asyncio
            with self.assertRaises(ToolDenied) as cm:
                asyncio.run(_read())
            self.assertEqual(cm.exception.code, "BINARY_FILE")

    def test_null_byte_after_8k_is_not_detected(self):
        """Null bytes after 8192 bytes are not detected by the
        first-8K heuristic. This is a known accepted risk."""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            tools = ToolExecutor(ws)
            data = b"A" * 8192 + b"\x00tail"
            (ws / "late-null.txt").write_bytes(data)

            async def _read():
                return await tools.read_file("late-null.txt")
            import asyncio
            result = asyncio.run(_read())
            self.assertGreater(result["size"], 8192)


if __name__ == "__main__":
    unittest.main()