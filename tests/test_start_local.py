"""Local launcher dependency/bootstrap contract."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class StartLocalTest(unittest.TestCase):
    def test_requirements_and_playwright_chromium_are_always_ensured(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            log = root_path / "python-calls.log"
            fake_python = root_path / "python"
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '%s\\n' \"$*\" >> {str(log)!r}\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            env = {
                **os.environ,
                "PYTHON_BIN": str(fake_python),
                "PORT": "18420",
            }
            result = subprocess.run(
                ["bash", str(REPO_ROOT / "scripts" / "start-local.sh")],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=5,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(calls, [
                "-m pip install -r requirements.txt",
                "-m playwright install chromium",
                "server.py",
            ])
