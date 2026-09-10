"""Settings endpoint must retain server-owned process capabilities."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class TerminalSettingsTestCase(unittest.TestCase):
    def test_ordinary_settings_put_preserves_custom_process_capabilities(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "cortex-home"
            workspace = Path(temporary) / "workspace"
            workspace.mkdir()
            script = r'''
import asyncio
import json
import settings

stored = settings.load_settings()
stored["process_capabilities"] = {"custom": "server-owned"}
settings.save_settings(stored)
body = settings.SettingsIn(**{
    **{key: value for key, value in settings.load_settings().items()
       if key != "process_capabilities"},
    "theme": "light",
})
result = asyncio.run(settings.update_settings(body))
print(json.dumps({"theme": result["theme"], "caps": result["process_capabilities"]}))
'''
            env = {
                **os.environ,
                "CORTEX_HOME": str(home),
                "PYTHONPATH": f"{REPO_ROOT}:{REPO_ROOT / 'console'}",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            result = subprocess.run(
                [sys.executable, "-c", script], env=env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload, {"theme": "light", "caps": {"custom": "server-owned"}})
