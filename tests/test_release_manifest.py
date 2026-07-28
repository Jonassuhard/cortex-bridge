"""Behavioral tests for the v0.5 release-evidence validator."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "scripts" / "verify-release-evidence.py"


def valid_payload() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "release": "0.5.0",
        "commit": "1" * 40,
        "generatedAt": "2026-07-29T12:00:00Z",
        "environment": {
            "os": "macOS fixture",
            "python": "3.11 fixture",
            "node": "22 fixture",
            "browserDriver": "playwright",
            "executorKind": "deterministic",
            "simulation": True,
        },
        "suites": {
            name: {"passed": 1, "failed": 0, "skipped": 0}
            for name in ("backend", "frontendUnit", "e2e", "a11y")
        },
        "performance": {
            "cachedUsabilityMs": 800,
            "switchP95Ms": 2200,
            "switchMaxMs": 9800,
        },
        "dualConversations": {
            "runs": 10,
            "crossovers": 0,
            "thirdWriterDraftPreserved": True,
        },
        "acceptance": {
            "fixtureMissions": {"runs": 20, "passed": 20},
            "coldDualRuns": {"runs": 10, "passed": 10},
            "crashPoints": {"runs": 6, "passed": 6},
            "miniSites": {"runs": 3, "passed": 3, "status": "PASS"},
        },
        "gates": {
            name: "PASS"
            for name in (
                "privacy",
                "links",
                "secrets",
                "dependencies",
                "install",
                "doctor",
                "uninstall",
                "build",
                "e2e",
                "a11y",
            )
        }
        | {"consoleErrors": 0},
        "artifacts": {"release.tar.gz": "a" * 64},
        "verdict": "RELEASE_CANDIDATE_READY_FOR_OWNER_APPROVAL",
    }


class ReleaseManifestTest(unittest.TestCase):
    def run_validation(self, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = Path(temp_dir) / "evidence.json"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            return subprocess.run(
                ["python3", str(VALIDATOR), str(manifest)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                timeout=15,
            )

    def test_complete_release_evidence_passes(self) -> None:
        result = self.run_validation(valid_payload())

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)

    def test_missing_required_metric_is_rejected(self) -> None:
        payload = valid_payload()
        performance = payload["performance"]
        assert isinstance(performance, dict)
        del performance["switchP95Ms"]

        result = self.run_validation(payload)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing_field", result.stdout)
        self.assertIn("performance.switchP95Ms", result.stdout)

    def test_failed_offline_gate_is_rejected(self) -> None:
        payload = valid_payload()
        gates = payload["gates"]
        assert isinstance(gates, dict)
        gates["privacy"] = "FAIL"

        result = self.run_validation(payload)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("failed_gate", result.stdout)

    def test_performance_threshold_regression_is_rejected(self) -> None:
        payload = valid_payload()
        performance = payload["performance"]
        assert isinstance(performance, dict)
        performance["switchP95Ms"] = 3000

        result = self.run_validation(payload)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("performance_threshold", result.stdout)

    def test_ready_verdict_requires_three_live_mini_sites(self) -> None:
        payload = valid_payload()
        acceptance = payload["acceptance"]
        assert isinstance(acceptance, dict)
        acceptance["miniSites"] = {
            "runs": 0,
            "passed": 0,
            "status": "PENDING_OWNER_APPROVAL",
        }

        result = self.run_validation(payload)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("live_gate_verdict", result.stdout)

    def test_missing_live_counts_report_validation_errors_without_crashing(self) -> None:
        payload = valid_payload()
        acceptance = payload["acceptance"]
        assert isinstance(acceptance, dict)
        acceptance["miniSites"] = {"status": "PASS"}

        result = self.run_validation(payload)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing_field", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_pending_owner_verdict_preserves_honest_live_gate(self) -> None:
        payload = valid_payload()
        acceptance = payload["acceptance"]
        assert isinstance(acceptance, dict)
        acceptance["miniSites"] = {
            "runs": 0,
            "passed": 0,
            "status": "PENDING_OWNER_APPROVAL",
        }
        payload["verdict"] = "PENDING_OWNER_APPROVAL_FOR_LIVE_GATES"

        result = self.run_validation(payload)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_commit_and_artifact_hashes_must_be_full_hex(self) -> None:
        payload = valid_payload()
        payload["commit"] = "short"
        payload["artifacts"] = {"release.tar.gz": "not-a-hash"}

        result = self.run_validation(payload)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("commit_format", result.stdout)
        self.assertIn("artifact_hash", result.stdout)


if __name__ == "__main__":
    unittest.main()
