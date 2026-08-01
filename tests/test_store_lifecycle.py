"""Lifecycle coverage for the process-wide mission Store."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "console"))

import missions as missions_api  # noqa: E402
import server as server_api  # noqa: E402


class StoreLifecycleTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_server_lifespan_closes_process_store(self) -> None:
        """Removing the shutdown close would leave the real connection usable."""
        with tempfile.TemporaryDirectory() as tmp:
            previous_store = missions_api._store
            previous_data_dir = missions_api.DATA_DIR
            previous_db_path = missions_api.DB_PATH
            missions_api._store = None
            missions_api.DATA_DIR = Path(tmp)
            missions_api.DB_PATH = Path(tmp) / "cortex.db"

            def restore_module_state() -> None:
                current = missions_api._store
                if current is not None and current is not previous_store:
                    current.close()
                missions_api._store = previous_store
                missions_api.DATA_DIR = previous_data_dir
                missions_api.DB_PATH = previous_db_path

            self.addCleanup(restore_module_state)

            async with server_api.app.router.lifespan_context(server_api.app):
                store = missions_api.get_store()
                self.assertEqual(store.count("missions"), 0)

            self.assertIs(missions_api._store, store)
            self.assertTrue(store.closed)
            with self.assertRaises(sqlite3.ProgrammingError):
                store.count("missions")

            async with server_api.app.router.lifespan_context(server_api.app):
                reopened = missions_api.get_store()
                self.assertIsNot(reopened, store)
                self.assertFalse(reopened.closed)

            self.assertTrue(reopened.closed)


if __name__ == "__main__":
    unittest.main()
