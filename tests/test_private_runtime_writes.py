"""Private runtime files must stay private even under a permissive caller umask."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "console"))

import settings as settings_api  # noqa: E402
import onboarding as onboarding_api  # noqa: E402


class PrivateRuntimeWritesTest(unittest.TestCase):
    def test_save_settings_publishes_a_mode_0600_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary) / "runtime"
            settings_file = data_dir / "settings.json"
            previous_umask = os.umask(0)
            try:
                with (
                    patch.object(settings_api, "DATA_DIR", data_dir),
                    patch.object(settings_api, "SETTINGS_FILE", settings_file),
                ):
                    settings_api.save_settings(settings_api.DEFAULT_SETTINGS)
            finally:
                os.umask(previous_umask)

            self.assertEqual(data_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual(settings_file.stat().st_mode & 0o777, 0o600)

    def test_onboarding_marker_uses_runtime_and_mode_0600(self) -> None:
        self.assertEqual(
            onboarding_api.MARKER_FILE,
            settings_api.RUNTIME_PATHS.onboarding,
        )
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary) / "runtime"
            marker = data_dir / "onboarding-done.json"
            previous_umask = os.umask(0)
            try:
                with (
                    patch.object(onboarding_api, "DATA_DIR", data_dir),
                    patch.object(onboarding_api, "MARKER_FILE", marker),
                ):
                    onboarding_api._set_completed(True)
            finally:
                os.umask(previous_umask)

            self.assertEqual(data_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual(marker.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
