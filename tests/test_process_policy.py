"""Regression tests for explicit structured process capabilities."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from executor.policy import (  # noqa: E402
    PolicyEngine,
    SCOPE_ALL_WRITES_FOR_MISSION,
    WRITE_AUTOMATIC,
)
from executor.tools import ToolDenied, ToolExecutor, check_command_allowed  # noqa: E402


class ProcessPolicyTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workspace = Path(self._tmp.name)

    def test_01_deletion_shell_and_inline_interpreter_commands_are_denied(self):
        forbidden = [
            ["rm", "file.txt"],
            ["find", ".", "-delete"],
            ["git", "clean", "-fd"],
            ["python3", "-c", "open('../escape', 'w').write('x')"],
            ["node", "-e", "require('fs').unlinkSync('file')"],
            ["sh", "-c", "echo x"],
            ["bash", "script.sh"],
        ]
        for argv in forbidden:
            with self.subTest(argv=argv):
                with self.assertRaises(ToolDenied):
                    check_command_allowed(argv, self.workspace)

    def test_02_processes_are_denied_without_the_mission_capability(self):
        for tool, arguments in (
            ("run_process", {"argv": ["python3", "script.py"]}),
            ("run_tests", {}),
        ):
            with self.subTest(tool=tool):
                decision = PolicyEngine(self.workspace).evaluate(tool, arguments)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.denial_code, "PROCESS_CAPABILITY_DENIED")

    def test_03_enabled_processes_still_require_per_command_approval(self):
        (self.workspace / "script.py").write_text("print('ok')\n", encoding="utf-8")
        policy = PolicyEngine(
            self.workspace, mode=WRITE_AUTOMATIC, allow_processes=True
        )
        first = policy.evaluate("run_process", {"argv": ["python3", "script.py"]})
        policy.approve(SCOPE_ALL_WRITES_FOR_MISSION)
        second = policy.evaluate("run_process", {"argv": ["python3", "script.py"]})
        self.assertTrue(policy.process_capabilities.allowed)
        self.assertFalse(policy.process_capabilities.allow_network)
        self.assertFalse(policy.process_capabilities.allow_deletions)
        self.assertTrue(first.allowed)
        self.assertTrue(first.requires_approval)
        self.assertTrue(second.requires_approval)

    async def test_04_process_environment_excludes_parent_secrets(self):
        marker = "CORTEX_PARENT_SECRET"
        previous = os.environ.get(marker)
        os.environ[marker] = "do-not-inherit"
        self.addCleanup(
            lambda: os.environ.__setitem__(marker, previous)
            if previous is not None
            else os.environ.pop(marker, None)
        )
        (self.workspace / "env.py").write_text(
            "import os\nprint(os.environ.get('CORTEX_PARENT_SECRET', 'missing'))\n",
            encoding="utf-8",
        )
        result = await ToolExecutor(self.workspace).run_process(["python3", "env.py"])
        self.assertEqual(result["stdout"].strip(), "missing")

    async def test_05_timeout_terminates_the_entire_process_group(self):
        (self.workspace / "child.py").write_text(
            "import pathlib, sys, time\n"
            "pathlib.Path(sys.argv[1]).write_text(str(__import__('os').getpid()))\n"
            "time.sleep(30)\n",
            encoding="utf-8",
        )
        (self.workspace / "parent.py").write_text(
            "import subprocess, sys, time\n"
            "subprocess.Popen([sys.executable, 'child.py', 'child.pid'])\n"
            "time.sleep(30)\n",
            encoding="utf-8",
        )
        result = await ToolExecutor(self.workspace).run_process(
            ["python3", "parent.py"], timeoutSeconds=1
        )
        self.assertTrue(result["timedOut"])
        child_pid = int((self.workspace / "child.pid").read_text(encoding="utf-8"))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            self.fail("timed out process left its child running")


if __name__ == "__main__":
    unittest.main()
