"""Tests for the cortex.sh selftest command."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORTEX_SH = ROOT / "scripts" / "cortex.sh"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


FAKE_CURL = """#!/usr/bin/env python3
import json
import os
import sys
from urllib.parse import urlsplit

responses = json.loads(os.environ["CORTEX_SELFTEST_RESPONSES"])
response = responses.get(urlsplit(sys.argv[-1]).path)
if response is None:
    raise SystemExit(22)
if isinstance(response, dict) and set(response) == {"__raw__"}:
    sys.stdout.write(response["__raw__"])
else:
    json.dump(response, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\\n")
"""


def real_probe(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ok": True,
        "url": "https://chatgpt.com/",
        "title": "ChatGPT",
        "blocker": None,
        "composer_present": True,
        "send_button_present": True,
        "failures": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def run_selftest(
    probe: object,
    *,
    status: object | None = None,
    extension: object | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the real shell command while replacing only its HTTP boundary."""
    responses = {
        "/api/status": status if status is not None else {
            "runtime_mode": "live",
            "version": VERSION,
        },
        "/api/chrome-extension/status": extension if extension is not None else {
            "state": "paired",
            "extension_connected": True,
            "paired": True,
            "pending_commands": 0,
            "protocol_compatible": True,
            "extension_protocol_version": 2,
            "required_protocol_version": 2,
        },
        "/api/transport/probe": probe,
    }
    with tempfile.TemporaryDirectory() as temporary:
        temporary_path = Path(temporary)
        fake_bin = temporary_path / "bin"
        fake_bin.mkdir()
        fake_curl = fake_bin / "curl"
        fake_curl.write_text(FAKE_CURL, encoding="utf-8")
        fake_curl.chmod(0o700)
        environment = os.environ.copy()
        environment.update(
            {
                "CORTEX_HOME": str(temporary_path / "runtime"),
                "CORTEX_SELFTEST_RESPONSES": json.dumps(responses),
                "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
                "PORT": "18420",
                "PYTHON_BIN": sys.executable,
            }
        )
        return subprocess.run(
            ["bash", str(CORTEX_SH), "selftest"],
            capture_output=True,
            env=environment,
            text=True,
            timeout=20,
        )


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


class CortexSelftestProbeContractTest(unittest.TestCase):
    def test_success_reports_the_current_composer_present_field(self) -> None:
        result = run_selftest(real_probe())

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "Probe DOM ChatGPT... OK (composer=True, envoi=True)",
            result.stdout,
        )

    def test_nonempty_probe_failures_make_the_selftest_fail(self) -> None:
        result = run_selftest(
            real_probe(ok=False, composer_present=False, failures=["login"])
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("failures:", result.stdout)
        self.assertIn("login", result.stdout)
        self.assertNotIn("Tous les tests sont passés", result.stdout)

    def test_probe_ok_false_cannot_pass_even_with_an_empty_failure_list(self) -> None:
        result = run_selftest(real_probe(ok=False))

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ÉCHEC — probe déclaré non opérationnel", result.stdout)
        self.assertNotIn("Tous les tests sont passés", result.stdout)

    def test_missing_composer_cannot_pass_with_an_empty_failure_list(self) -> None:
        result = run_selftest(real_probe(composer_present=False))

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ÉCHEC — composer ChatGPT absent", result.stdout)
        self.assertNotIn("Tous les tests sont passés", result.stdout)

    def test_malformed_probe_response_fails_without_a_parser_crash(self) -> None:
        result = run_selftest({"__raw__": "not-json"})

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ÉCHEC — réponse probe invalide", result.stdout)
        self.assertIn("Certains tests ont échoué", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_structurally_malformed_probe_response_is_rejected(self) -> None:
        result = run_selftest(real_probe(ok="True", composer_present="True"))

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ÉCHEC — réponse probe invalide", result.stdout)
        self.assertNotIn("Tous les tests sont passés", result.stdout)

    def test_malformed_server_status_fails_without_a_parser_crash(self) -> None:
        result = run_selftest(real_probe(), status={"__raw__": "not-json"})

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ÉCHEC — réponse serveur invalide", result.stdout)
        self.assertIn("Certains tests ont échoué", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_malformed_extension_status_fails_without_a_parser_crash(self) -> None:
        result = run_selftest(real_probe(), extension={"__raw__": "not-json"})

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ÉCHEC — réponse extension invalide", result.stdout)
        self.assertIn("Certains tests ont échoué", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_unavailable_probe_cannot_end_in_a_green_summary(self) -> None:
        result = run_selftest(None)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("probe indisponible", result.stdout)
        self.assertNotIn("Tous les tests sont passés", result.stdout)

    def test_version_mismatch_cannot_end_in_a_green_summary(self) -> None:
        result = run_selftest(
            real_probe(),
            status={"runtime_mode": "live", "version": "0.0.0"},
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("VERSION=", result.stdout)
        self.assertNotIn("Tous les tests sont passés", result.stdout)

    def test_development_fixture_runtime_cannot_pass_selftest(self) -> None:
        result = run_selftest(
            real_probe(),
            status={"runtime_mode": "development_fixture", "version": VERSION},
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("runtime non live", result.stdout)
        self.assertNotIn("Tous les tests sont passés", result.stdout)

    def test_contradictory_extension_status_cannot_pass_selftest(self) -> None:
        result = run_selftest(
            real_probe(),
            extension={
                "state": "paired",
                "extension_connected": False,
                "paired": True,
                "pending_commands": 0,
                "protocol_compatible": False,
                "extension_protocol_version": 1,
                "required_protocol_version": 2,
            },
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("extension non prête", result.stdout)
        self.assertNotIn("Tous les tests sont passés", result.stdout)

    def test_valid_disconnected_extension_keeps_an_actionable_message(self) -> None:
        result = run_selftest(
            real_probe(),
            extension={
                "state": "disconnected",
                "extension_connected": False,
                "paired": False,
                "pending_commands": 0,
                "protocol_compatible": None,
                "extension_protocol_version": None,
                "required_protocol_version": 2,
            },
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("extension non prête", result.stdout)
        self.assertNotIn("réponse extension invalide", result.stdout)

    def test_control_characters_in_consumed_strings_are_rejected(self) -> None:
        cases = (
            (
                "status runtime",
                {"status": {"runtime_mode": "live\nforged", "version": VERSION}},
                "réponse serveur invalide",
            ),
            (
                "extension state",
                {
                    "extension": {
                        "state": "paired\rforged",
                        "extension_connected": True,
                        "paired": True,
                        "pending_commands": 0,
                        "protocol_compatible": True,
                        "extension_protocol_version": 2,
                        "required_protocol_version": 2,
                    }
                },
                "réponse extension invalide",
            ),
            (
                "probe failure",
                {},
                "réponse probe invalide",
            ),
        )
        for label, overrides, expected in cases:
            probe = real_probe()
            if label == "probe failure":
                probe.update(ok=False, failures=["login\nforged"])
            with self.subTest(label=label):
                result = run_selftest(probe, **overrides)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(expected, result.stdout)

    def test_nonpositive_protocol_versions_cannot_pass_selftest(self) -> None:
        for version in (0, -1):
            with self.subTest(version=version):
                result = run_selftest(
                    real_probe(),
                    extension={
                        "state": "paired",
                        "extension_connected": True,
                        "paired": True,
                        "pending_commands": 0,
                        "protocol_compatible": True,
                        "extension_protocol_version": version,
                        "required_protocol_version": version,
                    },
                )
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("extension non prête", result.stdout)
                self.assertNotIn("Tous les tests sont passés", result.stdout)

    def test_probe_blocker_cannot_pass_selftest(self) -> None:
        result = run_selftest(real_probe(blocker="login"))

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("blocage ChatGPT", result.stdout)
        self.assertIn("login", result.stdout)
        self.assertNotIn("Tous les tests sont passés", result.stdout)

    def test_send_button_is_required_and_must_be_a_boolean(self) -> None:
        missing = real_probe()
        missing.pop("send_button_present")
        cases = (
            ("missing", missing, "réponse probe invalide"),
            ("false", real_probe(send_button_present=False), "bouton d’envoi ChatGPT absent"),
            ("wrong type", real_probe(send_button_present="True"), "réponse probe invalide"),
        )
        for label, probe, expected in cases:
            with self.subTest(label=label):
                result = run_selftest(probe)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(expected, result.stdout)
                self.assertNotIn("Tous les tests sont passés", result.stdout)

    def test_real_probe_contract_succeeds(self) -> None:
        result = run_selftest(real_probe())

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Probe DOM ChatGPT... OK (composer=True, envoi=True)", result.stdout)


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
