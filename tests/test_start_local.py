"""Local launcher must never install or download dependencies implicitly."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class StartLocalTest(unittest.TestCase):
    @staticmethod
    def _write_runtime_python(root: Path, *, call_log: Path) -> Path:
        fake_python = root / "python"
        fake_python.write_text(
            "#!/usr/bin/env bash\n"
            "if [ \"$1\" = -c ] && [[ \"$2\" == *\"import fastapi,uvicorn,playwright,websockets\"* ]]; then\n"
            f"  printf '%s|%s|%s\\n' \"$PLAYWRIGHT_BROWSERS_PATH\" \"$PYTHONPATH\" \"$*\" >> {shlex.quote(str(call_log))}\n"
            "  exit 0\n"
            "fi\n"
            "case \"$1\" in\n"
            "  */server.py|server.py)\n"
            f"    printf '%s|%s|%s\\n' \"$PLAYWRIGHT_BROWSERS_PATH\" \"$PYTHONPATH\" \"$*\" >> {shlex.quote(str(call_log))}\n"
            "    exit 0\n"
            "    ;;\n"
            "esac\n"
            f"exec {shlex.quote(sys.executable)} \"$@\"\n",
            encoding="utf-8",
        )
        fake_python.chmod(0o755)
        return fake_python

    def test_launcher_checks_dependencies_then_starts_without_installing(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            log = root_path / "python-calls.log"
            fake_python = self._write_runtime_python(root_path, call_log=log)
            environment = {
                **os.environ,
                "PYTHON_BIN": str(fake_python),
                "CORTEX_HOME": str(root_path / "state"),
                "PORT": "18420",
            }
            environment.pop("PYTHONPATH", None)
            environment.pop("PLAYWRIGHT_BROWSERS_PATH", None)
            result = subprocess.run(
                ["bash", str(REPO_ROOT / "scripts" / "start-local.sh")],
                cwd=REPO_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                timeout=5,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(calls), 2)
            expected_cache = str((root_path / "state").resolve() / "browser-cache")
            expected_pythonpath = f"{REPO_ROOT / 'console'}:{REPO_ROOT}"
            self.assertTrue(calls[0].startswith(f"{expected_cache}|{expected_pythonpath}|-c "))
            self.assertIn("websockets", calls[0])
            self.assertEqual(calls[1], f"{expected_cache}|{expected_pythonpath}|server.py")
            self.assertNotIn("pip install", "\n".join(calls))
            self.assertNotIn("playwright install", "\n".join(calls))

    def test_launcher_fails_closed_before_server_when_storage_is_required_but_missing(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            log = root_path / "python-calls.log"
            fake_python = self._write_runtime_python(root_path, call_log=log)
            cortex_home = root_path / "state"
            cortex_home.mkdir()
            (cortex_home / "storage-required").write_text(
                "required\n",
                encoding="utf-8",
            )
            environment = {
                **os.environ,
                "PYTHON_BIN": str(fake_python),
                "CORTEX_HOME": str(cortex_home),
                "PORT": "18420",
            }
            environment.pop("PYTHONPATH", None)
            environment.pop("PLAYWRIGHT_BROWSERS_PATH", None)

            result = subprocess.run(
                ["bash", str(REPO_ROOT / "scripts" / "start-local.sh")],
                cwd=REPO_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("STORAGE_BOOTSTRAP_MISSING", result.stderr)
            calls = log.read_text(encoding="utf-8").splitlines()
            self.assertFalse(any(line.endswith("|server.py") for line in calls))

    def test_launcher_preserves_invalid_home_exit_code_and_never_starts_server(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            log = root_path / "python-calls.log"
            fake_python = self._write_runtime_python(root_path, call_log=log)
            environment = {
                **os.environ,
                "PYTHON_BIN": str(fake_python),
                "CORTEX_HOME": "relative/state",
                "PORT": "18420",
            }
            environment.pop("PYTHONPATH", None)
            environment.pop("PLAYWRIGHT_BROWSERS_PATH", None)

            result = subprocess.run(
                ["bash", str(REPO_ROOT / "scripts" / "start-local.sh")],
                cwd=REPO_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("CORTEX_HOME must be absolute", result.stderr)
            self.assertFalse(log.exists())


if __name__ == "__main__":
    unittest.main()
