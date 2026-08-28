"""Behavioral safety tests for scripts/cortex.sh before lifecycle side effects."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORTEX_SH = ROOT / "scripts" / "cortex.sh"


class CortexShellGuardTest(unittest.TestCase):
    @staticmethod
    def _run(command: str, *, cortex_home: Path, home: Path) -> subprocess.CompletedProcess[str]:
        environment = {
            **os.environ,
            "CORTEX_HOME": str(cortex_home),
            "CORTEX_START_INSTALL_LOCK_HELD": "1",
            "HOME": str(home),
            "PYTHON_BIN": sys.executable,
            "PORT": "58429",
            "CORTEX_LOG_MAX_BYTES": "invalid-before-launch",
        }
        environment.pop("PYTHONPATH", None)
        return subprocess.run(
            ["bash", str(CORTEX_SH), command],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_broad_user_home_is_rejected_before_runtime_directories_are_created(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)

            result = self._run("start", cortex_home=home, home=home)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("dedicated directory", result.stderr)
            self.assertFalse((home / "pids").exists())
            self.assertFalse((home / "logs").exists())
            self.assertFalse((home / ".install.lock").exists())

    def test_symlink_to_broad_home_is_rejected_before_runtime_directories_are_created(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            alias = root / "runtime-alias"
            alias.symlink_to(home, target_is_directory=True)

            result = self._run("start", cortex_home=alias, home=home)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("dedicated directory", result.stderr)
            self.assertFalse((home / "pids").exists())
            self.assertFalse((home / "logs").exists())

    def test_dedicated_local_symlink_is_canonicalised_before_use(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            runtime = home / ".local" / "share" / "cortex-bridge"
            runtime.mkdir(parents=True)
            alias = root / "runtime-alias"
            alias.symlink_to(runtime, target_is_directory=True)

            result = self._run("runtime-home", cortex_home=alias, home=home)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.strip(), str(runtime.resolve()))

    def test_external_volume_home_is_rejected_without_creating_any_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            external = Path("/") / "Volumes" / "CortexBridgeShellGuardTest" / "runtime"

            result = self._run("runtime-home", cortex_home=external, home=home)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("dedicated directory", result.stderr)
            self.assertFalse(external.exists())


if __name__ == "__main__":
    unittest.main()
