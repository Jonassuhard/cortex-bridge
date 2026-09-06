from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from uuid import UUID

from storage_lock import open_storage_lock_set
from storage_result import OperationResult
from storage_transition import (
    StorageProjection,
    TransitionPhase,
    advance_transition_locked,
    begin_transition_locked,
    commit_transition_locked,
    load_transition_locked,
    rollback_transition_locked,
    runtime_transition_status_locked,
)


class StorageTransitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir(mode=0o700)
        (self.home / "settings.json").write_text('{"language":"fr"}\n', encoding="utf-8")
        (self.home / "storage-bootstrap.json").write_text('{"schema_version":1}\n', encoding="utf-8")
        (self.home / "storage-required").write_bytes(b"required\n")
        for path in self.home.iterdir():
            path.chmod(0o600)
        self.target = StorageProjection(
            # Use a neutral absolute fixture path.  The public-privacy gate
            # intentionally rejects personal-location paths even in tests.
            default_workspace="/mnt/cortex/20_WORKSPACES",
            browser_profile_root="/mnt/cortex/50_CACHE_REBUILDABLE/browser-profiles",
            browser_transport="chrome_extension",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _locks(self):
        return open_storage_lock_set(self.home, install_mode="exclusive", storage_mode="exclusive")

    def test_begin_advance_commit_round_trip_and_status(self):
        with self._locks() as locks:
            journal = begin_transition_locked(
                locks, self.home, self.target,
                target_image_basename="CORTEX_BRIDGE_2026_09.sparsebundle",
            )
            self.assertEqual(journal.phase, "in_progress")
            self.assertEqual(journal.phase_number, 0)
            journal = advance_transition_locked(
                locks, journal, phase="spike_create_started",
                updates={
                    "spike_transaction_id": "8ce4e7ce-8e9a-45ef-a112-64a14dfc1c83",
                    "spike_image_basename": "cortex-spike-123.sparsebundle",
                },
            )
            self.assertEqual(journal.phase, "spike_create_started")
            committed = commit_transition_locked(locks, journal)
            self.assertEqual(committed.phase, "committed")
            loaded = load_transition_locked(locks, self.home)
            self.assertEqual(loaded, committed)
            status = runtime_transition_status_locked(locks, self.home)
            self.assertEqual(status.verdict, "PASS")
            self.assertTrue(status.runtime_allowed)

    def test_rollback_restores_exact_bytes_and_presence(self):
        original = (self.home / "settings.json").read_bytes()
        with self._locks() as locks:
            journal = begin_transition_locked(
                locks, self.home, self.target,
                target_image_basename="CORTEX_BRIDGE_2026_09.sparsebundle",
            )
            (self.home / "settings.json").write_text("tampered", encoding="utf-8")
            (self.home / "storage-required").unlink()
            result = rollback_transition_locked(
                locks, self.home, process_status={"stopped": True},
            )
            self.assertIsInstance(result, OperationResult)
            self.assertEqual(result.verdict, "PASS")
            self.assertEqual((self.home / "settings.json").read_bytes(), original)
            self.assertTrue((self.home / "storage-required").exists())
            self.assertEqual(load_transition_locked(locks, self.home).phase, "rolled_back")

    def test_phase_regression_and_invalid_target_fail_closed(self):
        with self._locks() as locks:
            with self.assertRaisesRegex(ValueError, "target image basename"):
                begin_transition_locked(locks, self.home, self.target, target_image_basename="bad")
            journal = begin_transition_locked(
                locks, self.home, self.target,
                target_image_basename="CORTEX_BRIDGE_2026_09.sparsebundle",
            )
            with self.assertRaisesRegex(ValueError, "phase"):
                advance_transition_locked(locks, journal, phase="in_progress", updates={})


if __name__ == "__main__":
    unittest.main()
