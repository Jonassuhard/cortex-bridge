"""The double-click launcher must expose its diagnostic command."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "Cortex Bridge.command"


class DesktopLauncherTest(unittest.TestCase):
    def test_launcher_dispatches_doctor_arguments_instead_of_starting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            cortex_home = root / "cortex"
            missing_bootstrap = root / "missing-storage-bootstrap.json"
            environment = {
                **os.environ,
                "HOME": str(home),
                "CORTEX_HOME": str(cortex_home),
                "CORTEX_STORAGE_BOOTSTRAP": str(missing_bootstrap),
                "PYTHON_BIN": sys.executable,
                "PYTHONDONTWRITEBYTECODE": "1",
            }

            result = subprocess.run(
                ["bash", str(LAUNCHER), "doctor", "--json"],
                cwd=ROOT,
                env=environment,
                input="",
                capture_output=True,
                text=True,
                timeout=20,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("checks", payload)
            self.assertNotIn("Cortex Bridge — démarrage", result.stdout)

    def test_launcher_preserves_storage_failure_code_and_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            cortex_home = root / "cortex"
            cortex_home.mkdir()
            (cortex_home / "storage-required").write_text("required\n", encoding="utf-8")
            bootstrap = cortex_home / "storage-bootstrap.json"
            bootstrap.write_text(
                json.dumps(
                    {
                        "encrypted_image_path": str(root / "archive.sparsebundle"),
                        "mount_path": str(root / "missing-mount"),
                        "schema_version": 1,
                        "storage_root": str(root / "missing-mount" / "CORTEX_BRIDGE"),
                        "volume_uuid": "FE08F69D-47E5-48D3-B7EF-30BCA7822926",
                    }
                ),
                encoding="utf-8",
            )
            bootstrap.chmod(0o600)
            environment = {
                **os.environ,
                "HOME": str(home),
                "CORTEX_HOME": str(cortex_home),
                "PYTHON_BIN": sys.executable,
                "PYTHONDONTWRITEBYTECODE": "1",
            }

            result = subprocess.run(
                ["bash", str(LAUNCHER)],
                cwd=ROOT,
                env=environment,
                input="",
                capture_output=True,
                text=True,
                timeout=20,
            )

            self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
            combined = result.stdout + result.stderr
            self.assertIn("code 3", combined)
            self.assertIn("volume de stockage chiffré requis", combined)
