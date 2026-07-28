from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "console"))


class CortexHomeTest(unittest.TestCase):
    def test_default_home_and_every_runtime_path_are_outside_repository(self):
        from cortex_paths import build_paths

        with tempfile.TemporaryDirectory() as home:
            with patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.home", return_value=Path(home)):
                paths = build_paths()
        expected = Path(home) / ".local" / "share" / "cortex-bridge"
        expected = expected.resolve(strict=False)
        self.assertEqual(paths.home, expected)
        for path in paths.mutable_paths():
            self.assertTrue(path == expected or expected in path.parents, path)
            self.assertNotIn(ROOT, [path, *path.parents])

    def test_explicit_cortex_home_must_be_absolute(self):
        from cortex_paths import build_paths

        with patch.dict(os.environ, {"CORTEX_HOME": "relative/state"}, clear=True):
            with self.assertRaises(ValueError):
                build_paths()

    def test_migration_never_deletes_or_overwrites_legacy_state(self):
        from cortex_paths import build_paths, migrate_legacy_state

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            legacy = base / "legacy"
            legacy.mkdir()
            (legacy / "settings.json").write_text("legacy", encoding="utf-8")
            (legacy / "chat-runs.json").write_text("runs", encoding="utf-8")
            (legacy / "ignored-link").symlink_to(legacy / "settings.json")
            with patch.dict(os.environ, {"CORTEX_HOME": str(base / "new")}, clear=True):
                paths = build_paths()
            paths.home.mkdir(parents=True)
            paths.settings.write_text("existing", encoding="utf-8")
            migrated = migrate_legacy_state(legacy, paths)
            self.assertEqual(paths.settings.read_text(encoding="utf-8"), "existing")
            self.assertEqual(paths.chat_runs.read_text(encoding="utf-8"), "runs")
            self.assertEqual((legacy / "settings.json").read_text(encoding="utf-8"), "legacy")
            self.assertFalse((paths.home / "ignored-link").exists())
            self.assertEqual(migrated, [paths.chat_runs])

    def test_model_directory_priority_and_relative_path_rejection(self):
        from cortex_paths import model_directory

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            explicit = base / "explicit"
            legacy = base / "legacy"
            with patch.dict(
                os.environ,
                {"CORTEX_MODEL_DIR": str(explicit), "CORTEX_STORAGE_PATH": str(legacy)},
                clear=True,
            ):
                self.assertEqual(model_directory(), explicit.resolve(strict=False))
            with patch.dict(os.environ, {"CORTEX_STORAGE_PATH": str(legacy)}, clear=True):
                self.assertEqual(model_directory(), legacy.resolve(strict=False))
            with patch.dict(os.environ, {"CORTEX_MODEL_DIR": "relative/models"}, clear=True):
                with self.assertRaises(ValueError):
                    model_directory()
            with patch.dict(os.environ, {}, clear=True), patch("pathlib.Path.home", return_value=base):
                self.assertEqual(
                    model_directory(),
                    (base / ".ollama" / "models").resolve(strict=False),
                )


if __name__ == "__main__":
    unittest.main()
