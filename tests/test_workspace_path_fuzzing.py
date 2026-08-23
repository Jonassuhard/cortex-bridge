"""Workspace path-confinement fuzzing battery.

Cortex Bridge's security model relies on workspace confinement: every
executor file operation must resolve inside the workspace and fail closed
otherwise. `test_acceptance_harness.py` covers one basic symlink case; this
battery fuzzes the confinement boundary itself — traversal, absolute paths,
NUL bytes, symlink escapes (including non-existent tails) and deceptive
Unicode names.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from executor.tools import ToolDenied, ToolError, resolve_in_workspace  # noqa: E402


class WorkspacePathFuzzingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tempdir.name) / "ws"
        self.workspace.mkdir()
        (self.workspace / "ok.txt").write_text("legit", encoding="utf-8")
        self.outside = Path(self.tempdir.name) / "outside.txt"
        self.outside.write_text("secret", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _denied(self, rel: str, code: str) -> None:
        with self.assertRaises(ToolDenied) as cm:
            resolve_in_workspace(self.workspace, rel)
        self.assertEqual(cm.exception.code, code, f"wrong denial code for {rel!r}")

    def test_parent_traversal_variants(self) -> None:
        for rel in ("../../etc/passwd", "a/../../b", "..", "sub/../../../x", "..\\..\\win"):
            self._denied(rel, "PATH_TRAVERSAL")

    def test_absolute_paths(self) -> None:
        for rel in ("/etc/passwd", "/etc", "~/secret", "~", "C:\\Windows", "D:/data"):
            self._denied(rel, "ABSOLUTE_PATH")

    def test_nul_byte_and_empty(self) -> None:
        self._denied("ok.txt\x00.png", "MALFORMED_PATH")
        for rel in ("", "   ", "\x00"):
            self._denied(rel, "MALFORMED_PATH")

    def test_symlink_escape_existing_target(self) -> None:
        link = self.workspace / "escape"
        link.symlink_to(self.outside)
        self._denied("escape", "SYMLINK_ESCAPE")

    def test_symlink_escape_directory_chain(self) -> None:
        dirlink = self.workspace / "dirlink"
        dirlink.symlink_to(Path(self.tempdir.name))
        # Reading THROUGH a symlinked directory must fail closed too.
        self._denied("dirlink/outside.txt", "SYMLINK_ESCAPE")

    def test_symlink_escape_with_nonexistent_tail(self) -> None:
        dirlink = self.workspace / "dirlink2"
        dirlink.symlink_to(Path(self.tempdir.name))
        # The tail does not exist, so the denial is PATH_ESCAPE (the symlink
        # itself is not the final candidate) — the escape is still refused.
        self._denied("dirlink2/new-file.txt", "PATH_ESCAPE")

    def test_must_exist_missing_file(self) -> None:
        with self.assertRaises(ToolError) as cm:
            resolve_in_workspace(self.workspace, "missing.txt", must_exist=True)
        self.assertEqual(cm.exception.code, "NOT_FOUND")

    def test_legitimate_paths_stay_inside(self) -> None:
        for rel in ("ok.txt", "sub/dir/file.txt", "./ok.txt"):
            resolved = resolve_in_workspace(self.workspace, rel)
            root = self.workspace.resolve()
            self.assertTrue(resolved == root or root in resolved.parents, rel)

    def test_deceptive_unicode_names_are_confined(self) -> None:
        """Homoglyphs, RTL override and emoji are valid NAMES, never escapes."""
        names = [
            "rеsumé.txt",          # Cyrillic е homoglyph
            "docu\u202e_txt.pdf",  # RTL override
            "réunion 🎉.md",       # accents + emoji
            "日本語ファイル.txt",   # CJK
        ]
        root = self.workspace.resolve()
        for name in names:
            resolved = resolve_in_workspace(self.workspace, name)
            self.assertTrue(root in resolved.parents or resolved == root, name)
            self.assertEqual(resolved.parent, root)

    def test_workspace_itself_is_allowed(self) -> None:
        resolved = resolve_in_workspace(self.workspace, ".")
        self.assertEqual(resolved, self.workspace.resolve())


if __name__ == "__main__":
    unittest.main()
