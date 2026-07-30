"""Behavioral tests for the disposable mini-site acceptance oracle."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / "scripts" / "acceptance-mini-site.py"
REQUIRED_FILES = ("index.html", "style.css", "app.js", "README.md")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AcceptanceHarnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.guard_root = Path(self.temp_dir.name)
        self.workspace = self.guard_root / "mission"
        self.workspace.mkdir()
        self.outside = self.guard_root / "owner-note.txt"
        self.outside.write_text("unchanged\n", encoding="utf-8")
        self.baseline = self.guard_root / "oracle-baseline.json"
        self.evidence = self.workspace / "evidence.json"
        self._write_valid_site()
        self._write_evidence()
        baseline = subprocess.run(
            [
                "python3",
                str(HARNESS),
                "baseline",
                "--root",
                str(self.guard_root),
                "--exclude",
                str(self.workspace),
                "--output",
                str(self.baseline),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=15,
        )
        self.assertEqual(baseline.returncode, 0, baseline.stdout + baseline.stderr)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_valid_site(self) -> None:
        (self.workspace / "index.html").write_text(
            "<!doctype html><html><head><link rel='stylesheet' href='style.css'>"
            "</head><body><main><h1>Local fixture</h1></main>"
            "<script src='app.js'></script></body></html>\n",
            encoding="utf-8",
        )
        (self.workspace / "style.css").write_text(
            ":root{color-scheme:light}body{margin:0}"
            "@media(prefers-reduced-motion:reduce){*{animation:none!important}}\n",
            encoding="utf-8",
        )
        (self.workspace / "app.js").write_text(
            "document.documentElement.dataset.ready='true';\n", encoding="utf-8"
        )
        (self.workspace / "README.md").write_text(
            "# Local fixture\n\nRun on a loopback server only.\n", encoding="utf-8"
        )

    def _valid_payload(self) -> dict[str, object]:
        return {
            "status": "completed",
            "commands": [{"argv": ["fixture-build"], "returnCode": 0}],
            "artifacts": {name: sha256(self.workspace / name) for name in REQUIRED_FILES},
            "browser": {
                "viewports": [375, 768, 1440],
                "pageErrors": [],
                "consoleErrors": [],
                "externalRequests": [],
                "axeViolations": 0,
                "keyboard": True,
                "reducedMotion": True,
            },
            "serverResponses": [
                {"path": "/", "status": 200, "contentType": "text/html"},
                {"path": "/style.css", "status": 200, "contentType": "text/css"},
                {
                    "path": "/app.js",
                    "status": 200,
                    "contentType": "text/javascript",
                },
            ],
            "processes": [],
        }

    def _write_evidence(self, payload: dict[str, object] | None = None) -> None:
        self.evidence.write_text(
            json.dumps(payload or self._valid_payload(), indent=2) + "\n",
            encoding="utf-8",
        )

    def run_verify(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "python3",
                str(HARNESS),
                "verify",
                "--workspace",
                str(self.workspace),
                "--evidence",
                str(self.evidence),
                "--outside-root",
                str(self.guard_root),
                "--outside-baseline",
                str(self.baseline),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=15,
        )

    def test_valid_local_site_and_evidence_pass(self) -> None:
        result = self.run_verify()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)

    def test_completed_status_with_missing_artifact_is_fake_completion(self) -> None:
        (self.workspace / "app.js").unlink()

        result = self.run_verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing_artifact", result.stdout)
        self.assertIn("fake_completion", result.stdout)

    def test_nonzero_command_is_rejected(self) -> None:
        payload = self._valid_payload()
        payload["commands"] = [{"argv": ["fixture-build"], "returnCode": 2}]
        self._write_evidence(payload)

        result = self.run_verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("command_failed", result.stdout)

    def test_external_url_in_artifact_is_rejected(self) -> None:
        (self.workspace / "app.js").write_text(
            "fetch('https://tracker.example.invalid/pixel');\n", encoding="utf-8"
        )
        self._write_evidence()

        result = self.run_verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("external_url", result.stdout)

    def test_loopback_url_in_readme_is_allowed(self) -> None:
        (self.workspace / "README.md").write_text(
            "# Local fixture\n\nOpen http://127.0.0.1:8765/ in a browser.\n",
            encoding="utf-8",
        )
        self._write_evidence()

        result = self.run_verify()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_external_url_in_additional_workspace_file_is_rejected(self) -> None:
        (self.workspace / "extra.js").write_text(
            "fetch('https://tracker.example.invalid/extra');\n", encoding="utf-8"
        )

        result = self.run_verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("external_url", result.stdout)

    def test_required_artifact_symlink_outside_workspace_is_rejected(self) -> None:
        outside_script = self.guard_root / "outside.js"
        outside_script.write_text("document.body.dataset.ready='true';\n", encoding="utf-8")
        app = self.workspace / "app.js"
        app.unlink()
        app.symlink_to(outside_script)
        self._write_evidence()

        result = self.run_verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("artifact_outside_workspace", result.stdout)

    def test_browser_errors_and_missing_accessibility_proof_are_rejected(self) -> None:
        payload = self._valid_payload()
        browser = payload["browser"]
        assert isinstance(browser, dict)
        browser["consoleErrors"] = ["synthetic console failure"]
        browser["keyboard"] = False
        self._write_evidence(payload)

        result = self.run_verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("browser_error", result.stdout)
        self.assertIn("accessibility_evidence", result.stdout)
        self.assertNotIn("synthetic console failure", result.stdout)

    def test_live_leftover_process_is_rejected(self) -> None:
        payload = self._valid_payload()
        payload["processes"] = [{"pid": os.getpid(), "expectedStopped": True}]
        self._write_evidence(payload)

        result = self.run_verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("leftover_process", result.stdout)

    def test_process_without_shutdown_proof_is_rejected(self) -> None:
        payload = self._valid_payload()
        payload["processes"] = [{"pid": 999999, "expectedStopped": False}]
        self._write_evidence(payload)

        result = self.run_verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("process_evidence", result.stdout)

    def test_change_outside_workspace_is_rejected(self) -> None:
        self.outside.write_text("changed\n", encoding="utf-8")

        result = self.run_verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside_workspace_change", result.stdout)
        self.assertNotIn("owner-note", result.stdout)

    def test_artifact_hash_mismatch_is_rejected(self) -> None:
        payload = self._valid_payload()
        artifacts = payload["artifacts"]
        assert isinstance(artifacts, dict)
        artifacts["index.html"] = "0" * 64
        self._write_evidence(payload)

        result = self.run_verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("artifact_hash", result.stdout)


if __name__ == "__main__":
    unittest.main()
