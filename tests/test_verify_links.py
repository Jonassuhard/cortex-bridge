"""Behavioral tests for the public documentation link checker."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts" / "verify-links.sh"


class VerifyLinksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_check(self, *, offline: bool = True) -> subprocess.CompletedProcess[str]:
        command = ["bash", str(CHECKER), "--root", str(self.root)]
        if offline:
            command.append("--offline")
        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=15,
        )

    def test_relative_files_images_and_anchors_pass(self) -> None:
        (self.root / "docs").mkdir()
        (self.root / "docs" / "guide.md").write_text(
            "# Install Guide\n\n## Local setup\n\nReady.\n", encoding="utf-8"
        )
        (self.root / "diagram.png").write_bytes(b"fixture")
        (self.root / "README.md").write_text(
            "[Guide](docs/guide.md#local-setup)\n\n"
            "![Diagram](diagram.png)\n\n"
            "[Section](#overview)\n\n"
            "## Overview\n",
            encoding="utf-8",
        )

        result = self.run_check()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)

    def test_missing_relative_target_fails_with_source_line(self) -> None:
        (self.root / "README.md").write_text(
            "See [missing](docs/missing.md).\n", encoding="utf-8"
        )

        result = self.run_check()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing_target", result.stdout)
        self.assertIn("README.md:1", result.stdout)

    def test_missing_markdown_anchor_fails(self) -> None:
        (self.root / "guide.md").write_text("# Existing heading\n", encoding="utf-8")
        (self.root / "README.md").write_text(
            "[Wrong anchor](guide.md#not-present)\n", encoding="utf-8"
        )

        result = self.run_check()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing_anchor", result.stdout)

    def test_external_links_are_counted_but_not_requested_offline(self) -> None:
        (self.root / "README.md").write_text(
            "[Official](https://docs.example.invalid/product)\n", encoding="utf-8"
        )

        result = self.run_check()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("external_skipped=1", result.stdout)

    def test_loopback_installation_url_is_never_requested_online(self) -> None:
        (self.root / "README.md").write_text(
            "Open [Cortex Bridge](http://127.0.0.1:8420).\n", encoding="utf-8"
        )

        result = self.run_check(offline=False)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("external_skipped=1", result.stdout)

    def test_generated_frontend_export_is_owned_by_browser_gate(self) -> None:
        output = self.root / "frontend" / "out"
        output.mkdir(parents=True)
        (output / "index.html").write_text(
            '<script src="/_next/generated.js"></script>\n', encoding="utf-8"
        )
        (self.root / "README.md").write_text("# Public docs\n", encoding="utf-8")

        result = self.run_check()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_parent_traversal_outside_root_is_rejected(self) -> None:
        outside = self.root.parent / "outside-guide.md"
        outside.write_text("# Outside\n", encoding="utf-8")
        self.addCleanup(outside.unlink)
        (self.root / "README.md").write_text(
            f"[Outside](../{outside.name})\n", encoding="utf-8"
        )

        result = self.run_check()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside_root", result.stdout)

    def test_access_control_responses_count_as_reachable(self) -> None:
        source = CHECKER.read_text(encoding="utf-8")

        self.assertIn("fallback_error.code in {401, 403}", source)
        self.assertIn("external_checked += 1", source)


if __name__ == "__main__":
    unittest.main()
