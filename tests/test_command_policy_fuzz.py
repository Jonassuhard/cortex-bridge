"""Command policy fuzzing: shell operators, approved executables, environment.

Covers blind spots in the check_command_allowed denylist: shell metachar
injection, network client controls, npm/pytest edge cases, sanitized
process environment leakage, _bounded truncation, and test-command detection.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from executor.tools import (
    ToolDenied,
    ToolError,
    check_command_allowed,
    sanitized_process_environment,
    _bounded,
    detect_test_command,
)


class ShellOperatorFuzzingTest(unittest.TestCase):
    """Shell metacharacters in argv → SHELL_OPERATORS."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = Path(self._tmp.name)
        (self.ws / "script.py").write_text("print('ok')\n", encoding="utf-8")

    def test_shell_metachars_are_refused(self):
        operators = ["&&", "||", ";", "|", "`", "$(", ">", "<"]
        for op in operators:
            with self.subTest(op=op):
                with self.assertRaises(ToolDenied) as cm:
                    check_command_allowed(
                        ["python3", "script.py", op], self.ws
                    )
                self.assertEqual(cm.exception.code, "SHELL_OPERATORS")

    def test_shell_metachar_inside_longer_arg_is_refused(self):
        cases = [
            "safe&&danger",
            ";rm -rf /",
            "cat /etc/passwd|nc",
            "$(whoami)",
            "../`whoami`/file",
            "data>exfil.txt",
            "in<stdin",
        ]
        for arg in cases:
            with self.subTest(arg=arg):
                with self.assertRaises(ToolDenied) as cm:
                    check_command_allowed(
                        ["python3", "script.py", arg], self.ws
                    )
                self.assertEqual(cm.exception.code, "SHELL_OPERATORS")

    def test_clean_args_without_shell_chars_are_allowed(self):
        check_command_allowed(
            ["python3", "script.py", "--verbose"], self.ws
        )


class DeniedExecutableTest(unittest.TestCase):
    """Programs outside APPROVED_EXECUTABLES are refused."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = Path(self._tmp.name)

    def test_common_unsafe_programs_are_denied(self):
        denied = [
            ["sudo", "echo"],
            ["su", "root"],
            ["ssh", "user@host"],
            ["scp", "file", "host:"],
            ["sftp", "host"],
            ["nc", "-l", "8080"],
            ["ncat", "host", "8080"],
            ["wget", "https://example.com"],
            ["chmod", "777"],
            ["chown", "root"],
            ["ping", "google.com"],
            ["gcc", "a.c"],
            ["perl", "script.pl"],
            ["ruby", "script.rb"],
            ["cat", "/etc/passwd"],
            ["ls", "-la"],
            ["mv", "a", "b"],
            ["cp", "a", "b"],
        ]
        for argv in denied:
            with self.subTest(argv=argv):
                with self.assertRaises(ToolDenied) as cm:
                    check_command_allowed(argv, self.ws)
                self.assertEqual(cm.exception.code, "DENIED_COMMAND")


class CurlHealthCheckTest(unittest.TestCase):
    """curl health check: exactly one loopback URL, safe flags only."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = Path(self._tmp.name)

    def test_loopback_health_check_is_allowed(self):
        check_command_allowed(
            ["curl", "--fail", "--silent", "http://127.0.0.1:8080/health"],
            self.ws,
        )
        check_command_allowed(
            ["curl", "http://127.0.0.1:8420/"],
            self.ws,
        )
        check_command_allowed(
            ["curl", "http://localhost:9999/status"],
            self.ws,
        )

    def test_ipv6_loopback_is_allowed(self):
        check_command_allowed(
            ["curl", "http://[::1]:8080/health"], self.ws
        )

    def test_external_url_is_refused(self):
        cases = [
            ["curl", "https://example.com/exfil"],
            ["curl", "https://google.com"],
            ["curl", "http://192.168.1.1:8080/"],
            ["curl", "http://10.0.0.1/"],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                with self.assertRaises(ToolDenied) as cm:
                    check_command_allowed(argv, self.ws)
                self.assertEqual(cm.exception.code, "EXTERNAL_SIDE_EFFECT")

    def test_multiple_urls_are_refused(self):
        with self.assertRaises(ToolDenied) as cm:
            check_command_allowed(
                ["curl", "http://127.0.0.1/a", "http://127.0.0.1/b"],
                self.ws,
            )
        self.assertEqual(cm.exception.code, "EXTERNAL_SIDE_EFFECT")

    def test_max_time_requires_integer(self):
        with self.assertRaises(ToolDenied) as cm:
            check_command_allowed(
                ["curl", "--max-time", "abc", "http://127.0.0.1/health"],
                self.ws,
            )
        self.assertEqual(cm.exception.code, "EXTERNAL_SIDE_EFFECT")

    def test_unknown_curl_flag_is_refused(self):
        for flag in ["-X", "--request", "--upload-file", "--data", "-o", "--output"]:
            with self.subTest(flag=flag):
                with self.assertRaises(ToolDenied):
                    check_command_allowed(
                        ["curl", flag, "val", "http://127.0.0.1/health"],
                        self.ws,
                    )


class NpmPytestTest(unittest.TestCase):
    """npm: only test/run test. pytest: always allowed."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = Path(self._tmp.name)

    def test_npm_test_is_allowed(self):
        check_command_allowed(["npm", "test"], self.ws)
        check_command_allowed(["npm", "run", "test"], self.ws)

    def test_npm_non_test_is_denied(self):
        denied = [
            ["npm", "run", "build"],
            ["npm", "install"],
            ["npm", "run", "lint"],
            ["npm", "start"],
        ]
        for argv in denied:
            with self.subTest(argv=argv):
                with self.assertRaises(ToolDenied):
                    check_command_allowed(argv, self.ws)

    def test_pytest_is_always_allowed(self):
        """pytest with any flags passes through. The test-runner (run_tests)
        enforces the argv at a higher level."""
        check_command_allowed(["pytest"], self.ws)
        check_command_allowed(["pytest", "-xvs", "tests/"], self.ws)
        check_command_allowed(["pytest", "--maxfail", "1"], self.ws)


class GitEdgeCaseTest(unittest.TestCase):
    """git status bare is allowed; git status with unexpected flag denied."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = Path(self._tmp.name)

    def test_git_status_bare_is_allowed(self):
        check_command_allowed(["git", "status"], self.ws)

    def test_git_status_with_short_flag_is_denied(self):
        """-s != --porcelain → denied."""
        with self.assertRaises(ToolDenied):
            check_command_allowed(["git", "status", "-s"], self.ws)


class PythonNodeTestCase(unittest.TestCase):
    """python/node: no inline execution, scripts must be in workspace."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = Path(self._tmp.name)

    def test_python_m_unittest_allowed(self):
        check_command_allowed(["python3", "-m", "unittest"], self.ws)

    def test_python_minus_c_is_denied(self):
        with self.assertRaises(ToolDenied):
            check_command_allowed(
                ["python3", "-c", "import os; os.system('rm -rf /')"],
                self.ws,
            )

    def test_python_minus_m_non_unittest_is_denied(self):
        for module in ["pip", "http.server", "ensurepip"]:
            with self.subTest(module=module):
                with self.assertRaises(ToolDenied):
                    check_command_allowed(
                        ["python3", "-m", module], self.ws
                    )

    def test_node_minus_e_is_denied(self):
        with self.assertRaises(ToolDenied):
            check_command_allowed(
                ["node", "-e", "require('fs').unlinkSync('/tmp/x')"],
                self.ws,
            )

    def test_script_must_exist(self):
        with self.assertRaises(ToolError) as cm:
            check_command_allowed(
                ["python3", "missing.py"], self.ws
            )
        self.assertEqual(cm.exception.code, "NOT_FOUND")

    def test_executable_absolute_path_is_refused(self):
        with self.assertRaises(ToolDenied):
            check_command_allowed(
                ["/usr/bin/python3", "script.py"], self.ws
            )


class SanitizedEnvironmentTest(unittest.TestCase):
    """sanitized_process_environment: no secrets, workspace as HOME."""

    def test_contains_only_expected_keys(self):
        import os  # noqa
        ws = Path(tempfile.mkdtemp())
        env = sanitized_process_environment(ws)
        for key in ("AWS_ACCESS_KEY_ID", "OPENAI_API_KEY",
                     "ANTHROPIC_API_KEY", "GITHUB_TOKEN",
                     "DATABASE_URL", "SECRET_KEY", "JWT_SECRET",
                     "CORTEX_HOME", "CORTEX_HOME_UNFILTERED"):
            self.assertNotIn(key, env)

    def test_home_is_workspace(self):
        ws = Path(tempfile.mkdtemp())
        env = sanitized_process_environment(ws)
        self.assertEqual(env["HOME"], str(ws.resolve()))

    def test_required_keys_exist(self):
        ws = Path(tempfile.mkdtemp())
        env = sanitized_process_environment(ws)
        required = {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL",
                     "PYTHONIOENCODING", "PYTHONDONTWRITEBYTECODE"}
        self.assertTrue(required.issubset(set(env)))


class BoundedOutputTest(unittest.TestCase):
    """_bounded truncation of stdout/stderr."""

    def test_short_text_unchanged(self):
        text, truncated = _bounded("hello", 100)
        self.assertEqual(text, "hello")
        self.assertFalse(truncated)

    def test_long_text_truncated_with_marker(self):
        text, truncated = _bounded("x" * 200, 100)
        marker = "\n…[truncated at 100 chars]"
        self.assertEqual(len(text), 100 + len(marker))
        self.assertTrue(truncated)
        self.assertIn("truncated", text)

    def test_exact_limit_unchanged(self):
        text = "a" * 100
        result, truncated = _bounded(text, 100)
        self.assertEqual(result, text)
        self.assertFalse(truncated)


class DetectTestCommandTest(unittest.TestCase):
    """detect_test_command: package.json script vs tests/ dir vs nothing."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = Path(self._tmp.name)

    def test_package_json_test_script_detected(self):
        import json
        (self.ws / "package.json").write_text(
            json.dumps({"scripts": {"test": "jest"}}), encoding="utf-8"
        )
        self.assertEqual(detect_test_command(self.ws), ["npm", "test"])

    def test_tests_directory_detected(self):
        (self.ws / "tests").mkdir()
        self.assertEqual(
            detect_test_command(self.ws),
            ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"],
        )

    def test_test_files_glob_detected(self):
        (self.ws / "test_app.py").write_text("", encoding="utf-8")
        self.assertEqual(
            detect_test_command(self.ws),
            ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"],
        )

    def test_empty_workspace_returns_none(self):
        self.assertIsNone(detect_test_command(self.ws))

    def test_package_json_takes_priority_over_tests_dir(self):
        import json
        (self.ws / "package.json").write_text(
            json.dumps({"scripts": {"test": "vitest"}}), encoding="utf-8"
        )
        (self.ws / "tests").mkdir()
        self.assertEqual(detect_test_command(self.ws), ["npm", "test"])


if __name__ == "__main__":
    unittest.main()