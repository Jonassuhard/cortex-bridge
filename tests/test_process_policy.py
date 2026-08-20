"""Regression tests for explicit structured process capabilities."""

from __future__ import annotations

import os
import json
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
from console import local_executor  # noqa: E402


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

    def test_04_rejects_executable_path_spoofing(self):
        for argv in (["./python3", "script.py"], ["/tmp/python3", "script.py"]):
            with self.subTest(argv=argv):
                with self.assertRaises(ToolDenied) as cm:
                    check_command_allowed(argv, self.workspace)
                self.assertEqual(cm.exception.code, "DENIED_COMMAND")

    def test_05_read_only_git_and_loopback_curl_options_are_allowlisted(self):
        allowed = [
            ["git", "status", "--porcelain"],
            ["git", "diff"],
            ["git", "log"],
            ["git", "show"],
            ["git", "rev-parse"],
            ["git", "branch"],
            ["git", "ls-files"],
            ["curl", "--fail", "--silent", "http://127.0.0.1:8080/health"],
        ]
        denied = [
            ["git", "branch", "-D", "main"],
            ["git", "diff", "--output", "leak.txt"],
            ["git", "config", "user.name", "escape"],
            ["git", "status", "--unknown"],
            ["git", "diff", "--unknown"],
            ["git", "diff", "--ext-diff"],
            ["git", "log", "--unknown"],
            ["git", "show", "--unknown"],
            ["git", "show", "--ext-diff"],
            ["git", "rev-parse", "--unknown"],
            ["git", "branch", "--unknown"],
            ["git", "ls-files", "--unknown"],
            ["curl", "--output", "outside.txt", "http://127.0.0.1:8080/health"],
            ["curl", "--config", "curlrc", "http://127.0.0.1:8080/health"],
        ]
        for argv in allowed:
            with self.subTest(allowed=argv):
                check_command_allowed(argv, self.workspace)
        for argv in denied:
            with self.subTest(denied=argv):
                with self.assertRaises(ToolDenied):
                    check_command_allowed(argv, self.workspace)

    async def test_06_live_executor_denies_model_process_without_capability(self):
        (self.workspace / "marker.py").write_text(
            "from pathlib import Path\nPath('executed').write_text('no')\n", encoding="utf-8"
        )
        replies = iter([
            json.dumps({
                "status": "READY_FOR_TOOL", "tool": "run_process",
                "arguments": {"argv": ["python3", "marker.py"]}, "summary": "run it",
            }),
            json.dumps({"status": "BLOCKED", "tool": None, "arguments": {}, "summary": "stop"}),
        ])
        original = local_executor._chat_sync
        local_executor._chat_sync = lambda _messages, _model: next(replies)
        events = []

        async def emit(text, kind):
            events.append((text, kind))

        try:
            result = await local_executor._run_live(
                {"goal": "test", "workspace": str(self.workspace)},
                emit,
            )
        finally:
            local_executor._chat_sync = original
        self.assertIn("PROCESS_CAPABILITY_DENIED", result["blockers"])
        self.assertFalse((self.workspace / "executed").exists())

    async def test_07_live_executor_requires_review_and_rejects_nonzero_before_done(self):
        (self.workspace / "fail.py").write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
        replies = iter([
            json.dumps({
                "status": "READY_FOR_TOOL", "tool": "run_process",
                "arguments": {"argv": ["python3", "fail.py"]}, "summary": "run it",
            }),
            json.dumps({
                "status": "READY_FOR_VALIDATION", "tool": None,
                "arguments": {}, "summary": "claim success",
            }),
        ])
        original = local_executor._chat_sync
        local_executor._chat_sync = lambda _messages, _model: next(replies)

        async def emit(_text, _kind):
            return None

        try:
            result = await local_executor._run_live(
                {"goal": "test", "workspace": str(self.workspace), "allow_processes": True},
                emit,
                process_approval=lambda _argv, _decision: True,
            )
        finally:
            local_executor._chat_sync = original
        self.assertEqual(result["status"], "failed")
        self.assertIn("PROCESS_EXIT_NONZERO", result["blockers"])

    async def test_08_live_executor_does_not_treat_capability_as_approval(self):
        (self.workspace / "marker.py").write_text(
            "from pathlib import Path\nPath('executed').write_text('no')\n", encoding="utf-8"
        )
        reply = json.dumps({
            "status": "READY_FOR_TOOL", "tool": "run_process",
            "arguments": {"argv": ["python3", "marker.py"]}, "summary": "run it",
        })
        original = local_executor._chat_sync
        local_executor._chat_sync = lambda _messages, _model: reply

        async def emit(_text, _kind):
            return None

        try:
            result = await local_executor._run_live(
                {"goal": "test", "workspace": str(self.workspace), "allow_processes": True}, emit
            )
        finally:
            local_executor._chat_sync = original
        self.assertEqual(result["status"], "blocked")
        self.assertIn("PROCESS_APPROVAL_REQUIRED", result["blockers"])
        self.assertFalse((self.workspace / "executed").exists())

    async def test_09_process_environment_excludes_parent_secrets(self):
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

    async def test_10_timeout_terminates_the_entire_process_group(self):
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
