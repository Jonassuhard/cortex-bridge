from __future__ import annotations

import sys
import os
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "console"))


class VersionConsistencyTest(unittest.TestCase):
    def test_python_package_and_canonical_file_are_050(self):
        from version import current_version

        canonical = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(canonical, "0.5.0")
        self.assertEqual(metadata["project"]["version"], canonical)
        self.assertEqual(current_version(), canonical)

    def test_python_lock_is_exact_and_hashed(self):
        lines = [
            line.strip()
            for line in (ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#") and not line.startswith(" ")
        ]
        self.assertTrue(lines)
        for line in lines:
            self.assertIn("==", line)
        lock_text = (ROOT / "requirements.lock").read_text(encoding="utf-8")
        self.assertIn("--hash=sha256:", lock_text)

    def test_console_entrypoint_and_runtime_status_expose_canonical_version(self):
        with tempfile.TemporaryDirectory() as home:
            environment = {
                **os.environ,
                "CORTEX_HOME": str(Path(home) / "state"),
                "PYTHONPATH": f"{ROOT / 'console'}:{ROOT}",
            }
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import asyncio,server; "
                        "assert callable(server.main); "
                        "assert asyncio.run(server.status())['version'] == '0.5.0'"
                    ),
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=15,
            )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
