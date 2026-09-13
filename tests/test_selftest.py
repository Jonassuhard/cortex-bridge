"""Tests for the cortex.sh selftest command."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORTEX_SH = ROOT / "scripts" / "cortex.sh"


class CortexSelftestSyntaxTest(unittest.TestCase):
    """Validate that the selftest case exists and the script parses correctly."""

    def test_selftest_case_exists_in_script(self):
        content = CORTEX_SH.read_text(encoding="utf-8")
        self.assertIn("selftest)", content, "selftest case missing from cortex.sh")

    def test_bash_syntax_parses(self):
        result = subprocess.run(
            ["bash", "-n", str(CORTEX_SH)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(
            result.returncode, 0, f"bash -n failed: {result.stderr}"
        )

    def test_help_includes_selftest(self):
        result = subprocess.run(
            ["bash", str(CORTEX_SH), "help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertIn("selftest", result.stdout, "selftest not listed in help")


class CortexSelftestLiveTest(unittest.TestCase):
    """Integration test: runs selftest against the live server if available."""

    def _server_is_up(self) -> bool:
        import urllib.request

        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:8420/api/status", timeout=2
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    def test_selftest_runs_without_crash(self):
        """The selftest should always run without internal errors (exit 0 or 1)."""
        result = subprocess.run(
            ["bash", str(CORTEX_SH), "selftest"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        # Should exit 0 (all pass) or 1 (some checks failed), never crash
        self.assertIn(
            result.returncode,
            [0, 1],
            f"selftest crashed with exit {result.returncode}: {result.stderr}",
        )
        self.assertIn(
            "auto-test", result.stdout, "selftest output missing header"
        )

    def test_selftest_output_format(self):
        """Verify the selftest produces structured French output."""
        result = subprocess.run(
            ["bash", str(CORTEX_SH), "selftest"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        output = result.stdout
        self.assertIn("[1/4]", output, "Missing step 1 in output")
        self.assertIn("[2/4]", output, "Missing step 2 in output")
        self.assertIn("[3/4]", output, "Missing step 3 in output")
        self.assertIn("[4/4]", output, "Missing step 4 in output")

    def test_selftest_server_check_works(self):
        """If server is up, step 1 should report OK."""
        result = subprocess.run(
            ["bash", str(CORTEX_SH), "selftest"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if self._server_is_up():
            self.assertIn(
                "Serveur en écoute",
                result.stdout,
                "Server check not found in output",
            )
            # Should not say ÉCHEC if server is up
            lines = result.stdout.splitlines()
            server_line = [l for l in lines if "[1/4]" in l]
            if server_line:
                self.assertNotIn("ÉCHEC", server_line[0])


if __name__ == "__main__":
    unittest.main()
