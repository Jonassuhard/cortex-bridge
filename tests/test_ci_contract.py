from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (ROOT / ".github/workflows/ci.yml", ROOT / ".github/workflows/docs.yml")


class CiContractTest(unittest.TestCase):
    def test_workflows_are_valid_least_privilege_and_sha_pinned(self):
        for workflow in WORKFLOWS:
            with self.subTest(workflow=workflow.name):
                syntax = subprocess.run(
                    [
                        "ruby",
                        "-e",
                        "require 'yaml'; YAML.safe_load(File.read(ARGV[0]), aliases: true)",
                        str(workflow),
                    ],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    timeout=10,
                )
                self.assertEqual(syntax.returncode, 0, syntax.stderr)
                source = workflow.read_text(encoding="utf-8")
                self.assertIn("permissions:\n  contents: read", source)
                self.assertNotIn("pull_request_target", source)
                self.assertNotIn("continue-on-error", source)
                self.assertNotRegex(source, r"\bsecrets\.")
                self.assertNotRegex(source, r"\bsudo\b")
                action_refs = re.findall(r"uses:\s*([^\s]+)", source)
                self.assertTrue(action_refs)
                for action_ref in action_refs:
                    self.assertRegex(action_ref, r"^[^@]+@[0-9a-f]{40}$")
                checkout_blocks = re.findall(
                    r"uses:\s*actions/checkout@[0-9a-f]{40}\n(?P<with>(?:\s{6,}.+\n)+)",
                    source,
                )
                self.assertTrue(checkout_blocks)
                self.assertTrue(
                    all("persist-credentials: false" in block for block in checkout_blocks)
                )

    def test_frontend_ci_uses_locked_npm_and_failure_only_browser_artifacts(self):
        source = WORKFLOWS[0].read_text(encoding="utf-8")
        self.assertIn("corepack npm ci", source)
        self.assertNotIn("npm install", source)
        self.assertIn("if: failure()", source)
        self.assertIn("frontend/playwright-report", source)
        self.assertIn("frontend/test-results", source)

    def test_backend_ci_installs_the_locked_playwright_browser(self):
        source = WORKFLOWS[0].read_text(encoding="utf-8")

        self.assertIn(".venv/bin/python -m playwright install chromium", source)

    def test_public_tree_installs_every_required_image_scanner(self):
        source = WORKFLOWS[1].read_text(encoding="utf-8")

        self.assertIn(
            "brew install exiftool ffmpeg gitleaks tesseract-lang",
            source,
        )


if __name__ == "__main__":
    unittest.main()
