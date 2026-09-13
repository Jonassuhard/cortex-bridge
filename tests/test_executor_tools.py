"""Required local-executor tests (mission spec §21) against executor/tools.py.

Uses a disposable temp workspace per test. stdlib unittest only:
    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from executor.tools import (  # noqa: E402
    CheckpointManager,
    ToolDenied,
    ToolError,
    ToolExecutor,
    validate_write_result,
)

GIT = shutil.which("git")


class ToolTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_stops_child_when_leader_already_exited(self):
        import asyncio
        import os
        import signal
        import time
        if os.name != 'posix':
            self.skipTest('POSIX process groups')
        child_code = ("import signal,time; from pathlib import Path; "
                      "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                      "Path('ready').write_text('child ready'); time.sleep(60)")
        (self.ws / 'orphan.py').write_text(
            "import os,subprocess,sys,time\nfrom pathlib import Path\n"
            "Path('group.pid').write_text(str(os.getpid()))\n"
            f"subprocess.Popen([sys.executable,'-c',{child_code!r}])\n"
            "while not Path('ready').exists(): time.sleep(.01)\n")
        task = asyncio.create_task(self.tools.run_process(['python3', 'orphan.py'], timeoutSeconds=1))
        try:
            done, _ = await asyncio.wait({task}, timeout=4)
            self.assertTrue(done, 'timeout hangs on pipes retained by orphan child')
            result = task.result()
            self.assertTrue(result['timedOut'])
            self.assertEqual(result['exitCode'], -1)
        finally:
            pid_file = self.ws / 'group.pid'
            if pid_file.exists():
                try:
                    os.killpg(int(pid_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if not task.done():
                await asyncio.wait_for(task, timeout=2)

    async def test_cancel_stops_owned_process_group_including_stubborn_child(self):
        import asyncio
        import os
        import signal
        import time
        if os.name != 'posix':
            self.skipTest('POSIX process groups')
        child_code = ("import os,signal,time; from pathlib import Path; "
                      "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                      "Path('child.pid').write_text(str(os.getpid())); time.sleep(60)")
        (self.ws / 'parent.py').write_text(
            "import os,subprocess,sys,time\nfrom pathlib import Path\n"
            "Path('parent.pid').write_text(str(os.getpid()))\n"
            f"subprocess.Popen([sys.executable,'-c',{child_code!r}])\n"
            "time.sleep(60)\n")
        task = asyncio.create_task(self.tools.run_process(['python3', 'parent.py'], timeoutSeconds=30))
        pid = None
        try:
            end = time.monotonic() + 5
            while not (self.ws / 'child.pid').exists() and time.monotonic() < end:
                await asyncio.sleep(.02)
            self.assertTrue((self.ws / 'child.pid').exists(), 'fixture failed to start')
            pid = int((self.ws / 'parent.pid').read_text())
            child_pid = int((self.ws / 'child.pid').read_text())
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            def alive(process_id):
                try:
                    os.kill(process_id, 0)
                    return True
                except ProcessLookupError:
                    return False
            end = time.monotonic() + 2
            while (alive(pid) or alive(child_pid)) and time.monotonic() < end:
                await asyncio.sleep(.02)
            self.assertFalse(alive(pid), 'cancelled parent still running')
            self.assertFalse(alive(child_pid), 'cancelled descendant still running')
        finally:
            if pid is not None:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = Path(self._tmp.name)
        self.tools = ToolExecutor(self.ws)

    def _workspace_files(self) -> set[str]:
        """All files in the disposable workspace, excluding .cortex internals."""
        out = set()
        for p in self.ws.rglob("*"):
            if p.is_file() and ".cortex" not in p.relative_to(self.ws).parts:
                out.add(str(p.relative_to(self.ws)))
        return out

    # 1. list an allowed directory
    async def test_01_list_allowed_directory(self):
        (self.ws / "a.txt").write_text("a", encoding="utf-8")
        (self.ws / "subdir").mkdir()
        result = await self.tools.list_directory(".")
        names = {e["name"] for e in result["entries"]}
        self.assertIn("a.txt", names)
        self.assertIn("subdir", names)
        types = {e["name"]: e["type"] for e in result["entries"]}
        self.assertEqual(types["subdir"], "directory")
        self.assertEqual(types["a.txt"], "file")

    # 2. read an allowed file
    async def test_02_read_allowed_file(self):
        (self.ws / "hello.txt").write_text("hello cortex", encoding="utf-8")
        result = await self.tools.read_file("hello.txt")
        self.assertEqual(result["content"], "hello cortex")
        self.assertEqual(result["size"], 12)

    # 3. reject /etc/passwd
    async def test_03_reject_etc_passwd(self):
        with self.assertRaises(ToolDenied) as cm:
            await self.tools.read_file("/etc/passwd")
        self.assertEqual(cm.exception.code, "ABSOLUTE_PATH")

    # 4. reject ../outside.txt
    async def test_04_reject_parent_traversal(self):
        with self.assertRaises(ToolDenied) as cm:
            await self.tools.read_file("../outside.txt")
        self.assertEqual(cm.exception.code, "PATH_TRAVERSAL")

    # 5. reject a symlink pointing outside
    async def test_05_reject_symlink_pointing_outside(self):
        outside = Path(self._tmp.name).parent / f"outside-{id(self)}.txt"
        outside.write_text("secret", encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        link = self.ws / "escape.txt"
        try:
            link.symlink_to(outside)
        except OSError as exc:  # pragma: no cover
            self.skipTest(f"symlinks unavailable: {exc}")
        with self.assertRaises(ToolDenied) as cm:
            await self.tools.read_file("escape.txt")
        self.assertEqual(cm.exception.code, "SYMLINK_ESCAPE")

    # 6. create one requested file
    async def test_06_create_one_requested_file(self):
        result = await self.tools.write_file("new.txt", "fresh content")
        self.assertTrue((self.ws / "new.txt").is_file())
        self.assertEqual(result["path"], "new.txt")
        self.assertEqual(result["bytes"], len("fresh content"))
        self.assertEqual(len(result["sha256"]), 64)

    # 7. verify exact file content
    async def test_07_verify_exact_file_content(self):
        content = "line 1\nline 2 — ünïcode\n"
        await self.tools.write_file("exact.txt", content)
        actual = (self.ws / "exact.txt").read_text(encoding="utf-8")
        self.assertEqual(actual, content)
        result = await self.tools.read_file("exact.txt")
        self.assertEqual(result["content"], content)

    # 8. refuse an unspecified second file
    async def test_08_refuse_unspecified_second_file(self):
        await self.tools.write_file("only.txt", "one")
        self.assertEqual(self._workspace_files(), {"only.txt"})
        # Writing into a non-existent subdirectory must not silently create it:
        with self.assertRaises(ToolError) as cm:
            await self.tools.write_file("sub/second.txt", "two")
        self.assertEqual(cm.exception.code, "MISSING_DIRECTORY")
        self.assertEqual(self._workspace_files(), {"only.txt"})

    # 9. apply a precise patch
    async def test_09_apply_precise_patch(self):
        (self.ws / "code.py").write_text(
            "def add(a, b):\n    return a - b  # BUG\n", encoding="utf-8"
        )
        result = await self.tools.apply_patch(
            "code.py", [{"old": "return a - b  # BUG", "new": "return a + b"}]
        )
        self.assertEqual(
            (self.ws / "code.py").read_text(encoding="utf-8"),
            "def add(a, b):\n    return a + b\n",
        )
        self.assertIn("return a + b", result["diff"])
        self.assertNotEqual(result["beforeHash"], result["afterHash"])

    # 10. reject a patch with mismatched expected text — file untouched
    async def test_10_reject_patch_mismatched_expected_text(self):
        original = "def add(a, b):\n    return a + b\n"
        (self.ws / "code.py").write_text(original, encoding="utf-8")
        with self.assertRaises(ToolError) as cm:
            await self.tools.apply_patch(
                "code.py", [{"old": "return a - b", "new": "return a * b"}]
            )
        self.assertEqual(cm.exception.code, "EXPECTED_TEXT_MISMATCH")
        self.assertEqual((self.ws / "code.py").read_text(encoding="utf-8"), original)

    # 11. run `python3 script.py`
    async def test_11_run_python_script(self):
        (self.ws / "script.py").write_text("print('CORTEX_OK')\n", encoding="utf-8")
        result = await self.tools.run_process(["python3", "script.py"])
        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["stdout"].strip(), "CORTEX_OK")

    # 12. capture stdout and exit code
    async def test_12_capture_stdout_and_exit_code(self):
        (self.ws / "fail.py").write_text(
            "import sys\nprint('out-line')\nprint('err-line', file=sys.stderr)\nsys.exit(3)\n",
            encoding="utf-8",
        )
        result = await self.tools.run_process(["python3", "fail.py"])
        self.assertEqual(result["exitCode"], 3)
        self.assertIn("out-line", result["stdout"])
        self.assertIn("err-line", result["stderr"])

    # 13. enforce timeout
    async def test_13_enforce_timeout(self):
        (self.ws / "slow.py").write_text(
            "import time\ntime.sleep(10)\nprint('done')\n", encoding="utf-8"
        )
        result = await self.tools.run_process(
            ["python3", "slow.py"], timeoutSeconds=1
        )
        self.assertTrue(result["timedOut"])
        self.assertEqual(result["exitCode"], -1)
        self.assertNotIn("done", result["stdout"])

    # 14. reject sudo
    async def test_14_reject_sudo(self):
        with self.assertRaises(ToolDenied) as cm:
            await self.tools.run_process(["sudo", "ls"])
        self.assertEqual(cm.exception.code, "DENIED_COMMAND")

    # 15. reject git push
    async def test_15_reject_git_push(self):
        with self.assertRaises(ToolDenied) as cm:
            await self.tools.run_process(["git", "push", "origin", "main"])
        self.assertEqual(cm.exception.code, "DENIED_COMMAND")

    # 16. reject external curl
    async def test_16_reject_external_curl(self):
        with self.assertRaises(ToolDenied) as cm:
            await self.tools.run_process(["curl", "https://example.com/exfil"])
        self.assertEqual(cm.exception.code, "EXTERNAL_SIDE_EFFECT")

    # 17. preserve unrelated dirty Git changes
    @unittest.skipUnless(GIT, "git not installed")
    async def test_17_preserve_unrelated_dirty_git_changes(self):
        env = {
            "GIT_AUTHOR_NAME": "cortex-test",
            "GIT_AUTHOR_EMAIL": "cortex@test.local",
            "GIT_COMMITTER_NAME": "cortex-test",
            "GIT_COMMITTER_EMAIL": "cortex@test.local",
        }
        import os

        full_env = {**os.environ, **env}
        subprocess.run([GIT, "init", "-q"], cwd=self.ws, check=True)
        (self.ws / "tracked.txt").write_text("base\n", encoding="utf-8")
        subprocess.run([GIT, "add", "-A"], cwd=self.ws, check=True, env=full_env)
        subprocess.run(
            [GIT, "commit", "-q", "-m", "base"], cwd=self.ws, check=True, env=full_env
        )
        # Unrelated dirty change the tool must not touch.
        (self.ws / "tracked.txt").write_text("dirty user edit\n", encoding="utf-8")
        await self.tools.write_file("other.txt", "tool output\n")
        self.assertEqual(
            (self.ws / "tracked.txt").read_text(encoding="utf-8"), "dirty user edit\n"
        )
        status = await self.tools.git_status()
        self.assertIn(" M tracked.txt", status["stdout"])
        self.assertIn("?? other.txt", status["stdout"])

    # 18. reject model-declared success when validation fails
    async def test_18_reject_false_success(self):
        await self.tools.write_file("result.txt", "actual content")
        check = validate_write_result(self.ws, "result.txt", "claimed content")
        self.assertFalse(check["passed"])
        self.assertIn("differs", check["evidence"])
        ok = validate_write_result(self.ws, "result.txt", "actual content")
        self.assertTrue(ok["passed"])

    # 19. create a rollback checkpoint
    async def test_19_create_rollback_checkpoint(self):
        (self.ws / "one.txt").write_text("1", encoding="utf-8")
        (self.ws / "two.txt").write_text("22", encoding="utf-8")
        manager = CheckpointManager(self.ws)
        info = manager.create_checkpoint("cp1")
        self.assertEqual(info["files"], 2)
        manifest = self.ws / ".cortex" / "checkpoints" / "cp1" / ".manifest.json"
        self.assertTrue(manifest.is_file())
        self.assertEqual(set(info["manifest"]), {"one.txt", "two.txt"})

    # 20. restore the checkpoint
    async def test_20_restore_checkpoint(self):
        (self.ws / "keep.txt").write_text("original", encoding="utf-8")
        (self.ws / "removed.txt").write_text("will be deleted", encoding="utf-8")
        manager = CheckpointManager(self.ws)
        manager.create_checkpoint("cp1")
        # Mutate the workspace after the checkpoint.
        (self.ws / "keep.txt").write_text("MODIFIED", encoding="utf-8")
        (self.ws / "removed.txt").unlink()
        (self.ws / "added.txt").write_text("new file", encoding="utf-8")
        result = manager.restore_checkpoint("cp1")
        self.assertEqual((self.ws / "keep.txt").read_text(encoding="utf-8"), "original")
        self.assertTrue((self.ws / "removed.txt").is_file())
        self.assertFalse((self.ws / "added.txt").exists())
        self.assertIn("keep.txt", result["restored"])
        self.assertIn("added.txt", result["deleted"])


if __name__ == "__main__":
    unittest.main()
