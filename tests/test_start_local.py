"""Local launcher must never install or download dependencies implicitly."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class StartLocalTest(unittest.TestCase):
    def test_launcher_checks_dependencies_then_starts_without_installing(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            log = root_path / "python-calls.log"
            fake_python = root_path / "python"
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '%s|%s|%s\\n' \"$PLAYWRIGHT_BROWSERS_PATH\" \"$PYTHONPATH\" \"$*\" >> {str(log)!r}\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
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
            expected_cache = str(root_path / "state" / "browser-cache")
            expected_pythonpath = f"{REPO_ROOT / 'console'}:{REPO_ROOT}"
            self.assertTrue(calls[0].startswith(f"{expected_cache}|{expected_pythonpath}|-c "))
            self.assertEqual(calls[1], f"{expected_cache}|{expected_pythonpath}|server.py")
            self.assertNotIn("pip install", "\n".join(calls))
            self.assertNotIn("playwright install", "\n".join(calls))


if __name__ == "__main__":
    unittest.main()
