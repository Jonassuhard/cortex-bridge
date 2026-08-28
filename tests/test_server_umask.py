"""Direct server startup must keep every subsequent runtime write private."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ServerUmaskTest(unittest.TestCase):
    def test_import_server_does_not_create_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "runtime"
            code = """
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path[:0] = [str(root / "console"), str(root)]
import server  # noqa: F401
"""
            environment = {
                **os.environ,
                "CORTEX_HOME": str(runtime),
            }
            result = subprocess.run(
                [sys.executable, "-c", code, str(ROOT)],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=20,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(runtime.exists())

    def test_cli_server_start_restricts_process_umask_without_import_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "runtime"
            probe = runtime / "post-import-private.txt"
            code = """
import os
import sys
from pathlib import Path

os.umask(0o022)
root = Path(sys.argv[1])
sys.path[:0] = [str(root / "console"), str(root)]
import server  # noqa: F401
server._configure_private_umask()
probe = Path(sys.argv[2])
probe.parent.mkdir()
probe.write_text("private", encoding="utf-8")
print(oct(probe.stat().st_mode & 0o777))
"""
            environment = {
                **os.environ,
                "CORTEX_HOME": str(runtime),
                "PORT": "58424",
            }
            result = subprocess.run(
                [sys.executable, "-c", code, str(ROOT), str(probe)],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=20,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "0o600")
            self.assertEqual(runtime.stat().st_mode & 0o777, 0o700)

    def test_direct_python_entrypoint_refuses_missing_required_storage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "runtime"
            runtime.mkdir()
            (runtime / "storage-required").write_text("required\n", encoding="utf-8")
            server_started = base / "server-started"
            code = """
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path[:0] = [str(root / "console"), str(root)]
import server
server.uvicorn.run = lambda *args, **kwargs: Path(sys.argv[2]).write_text("started", encoding="utf-8")
server.main()
"""
            environment = {
                **os.environ,
                "CORTEX_HOME": str(runtime),
                "PORT": "58425",
            }
            result = subprocess.run(
                [sys.executable, "-c", code, str(ROOT), str(server_started)],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=20,
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("STORAGE_BOOTSTRAP_MISSING", result.stderr)
            self.assertFalse(server_started.exists())

    def test_rejected_main_restores_the_callers_umask(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "runtime"
            runtime.mkdir()
            (runtime / "storage-required").write_text("required\n", encoding="utf-8")
            code = """
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path[:0] = [str(root / "console"), str(root)]
import server

os.umask(0o022)
try:
    server.main()
except SystemExit as exc:
    assert exc.code == 2
else:
    raise AssertionError("required storage should reject startup")

current = os.umask(0o022)
os.umask(current)
assert current == 0o022, oct(current)
"""
            environment = {
                **os.environ,
                "CORTEX_HOME": str(runtime),
                "PORT": "58426",
            }
            result = subprocess.run(
                [sys.executable, "-c", code, str(ROOT)],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=20,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
