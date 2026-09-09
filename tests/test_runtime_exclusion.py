import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "console"))


class RuntimeExclusionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("runtime_exclusion"),
                             "Runtime exclusion is not implemented")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve() / "home"
        self.home.mkdir(mode=0o700)

    def test_second_process_refused_until_owner_releases(self):
        from runtime_exclusion import exclusive_runtime
        script = """
import sys
from pathlib import Path
from runtime_exclusion import exclusive_runtime, RuntimeAlreadyRunning
try:
    with exclusive_runtime(Path(sys.argv[1])):
        print("ACQUIRED")
except RuntimeAlreadyRunning:
    print("BUSY")
"""
        def contender():
            return subprocess.run([sys.executable, "-c", script, str(self.home)],
                env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "console")},
                capture_output=True, text=True, timeout=5, check=True).stdout.strip()
        with exclusive_runtime(self.home):
            self.assertEqual(contender(), "BUSY")
        self.assertEqual(contender(), "ACQUIRED")

    def test_exception_releases_lock_without_deleting_marker(self):
        from runtime_exclusion import exclusive_runtime
        with self.assertRaisesRegex(ValueError, "fixture"):
            with exclusive_runtime(self.home):
                raise ValueError("fixture")
        marker = self.home / ".runtime.lock"
        inode = marker.stat().st_ino
        with exclusive_runtime(self.home):
            self.assertEqual(marker.stat().st_ino, inode)

    def test_foreign_marker_is_not_overwritten(self):
        from runtime_exclusion import exclusive_runtime
        marker = self.home / ".runtime.lock"
        marker.write_text("foreign data")
        marker.chmod(0o600)
        with self.assertRaises(RuntimeError):
            with exclusive_runtime(self.home):
                self.fail("Foreign marker admitted")
        self.assertEqual(marker.read_text(), "foreign data")

    def test_process_death_releases_kernel_lock_without_marker_cleanup(self):
        from runtime_exclusion import exclusive_runtime, RuntimeAlreadyRunning
        script = """
import sys
from pathlib import Path
from runtime_exclusion import exclusive_runtime
with exclusive_runtime(Path(sys.argv[1])):
    print("READY", flush=True)
    sys.stdin.read()
"""
        child = subprocess.Popen([sys.executable, "-c", script, str(self.home)],
            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "console")},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            import select
            self.assertTrue(select.select([child.stdout], [], [], 5)[0], "Child did not become ready")
            self.assertEqual(child.stdout.readline().strip(), "READY")
            with self.assertRaises(RuntimeAlreadyRunning):
                with exclusive_runtime(self.home):
                    pass
            marker = self.home / ".runtime.lock"
            inode = marker.stat().st_ino
            child.kill()
            child.wait(timeout=5)
            with exclusive_runtime(self.home):
                self.assertEqual(marker.stat().st_ino, inode)
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)


class RuntimeLifespanExclusionTests(unittest.IsolatedAsyncioTestCase):
    async def test_server_refuses_second_lifespan_without_closing_first_store(self):
        import server
        import missions
        from cortex_paths import build_paths
        from runtime_exclusion import RuntimeAlreadyRunning
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            with patch.dict(os.environ, {"CORTEX_HOME": str(root / "runtime")}):
                paths = build_paths()
            with patch.multiple(server, RUNTIME_PATHS=paths, STORE_FILE=paths.iterations,
                                BASE_DIR=root / "legacy", _runtime_initialized=False, _iterations=[]), patch.multiple(
                    missions, _store=None, DATA_DIR=paths.home, DB_PATH=paths.database,
                    RUNTIME_PATHS=paths, LEGACY_CHAT_RUNS_FILE=paths.chat_runs,
                    LEGACY_ITERATIONS_FILE=paths.iterations):
                async with server.app.router.lifespan_context(server.app):
                    store = missions.get_store()
                    with self.assertRaises(RuntimeAlreadyRunning):
                        async with server.app.router.lifespan_context(server.app):
                            pass
                    self.assertFalse(store.closed)
                    self.assertTrue(server._runtime_initialized)
                self.assertTrue(store.closed)
                async with server.app.router.lifespan_context(server.app):
                    self.assertFalse(missions.get_store().closed)


if __name__ == "__main__":
    unittest.main()
