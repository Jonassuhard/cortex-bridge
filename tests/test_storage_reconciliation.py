from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from storage_reconciliation import (
    ReconciliationProbeRequest,
    ReconciliationState,
    ReconciliationStore,
)


class ReconciliationTests(unittest.TestCase):
    def test_pending_then_compare_and_swap_reconciled(self):
        with tempfile.TemporaryDirectory() as td:
            store = ReconciliationStore(Path(td) / "state" / "reconciliation.json")
            request = ReconciliationProbeRequest(
                1, uuid4(), 1, uuid4(), "create", "a" * 64, "b" * 64,
                {
                    "probe_kind": "create_absent_or_consistent",
                    "image_path": "/tmp/image",
                    "expected_image_identity_sha256": None,
                    "keychain_query_sha256": "c" * 64,
                    "expected_encryption_uuid": None,
                },
            )
            pending = store.create_pending(request)
            self.assertEqual(pending.state, ReconciliationState.PENDING)
            final = store.cas_reconciled(
                pending.record_sha256,
                {
                    "kind": "create",
                    "disposition": "absent",
                    "image_present": False,
                    "image_identity_sha256": None,
                    "keychain_item_count": 0,
                    "encryption_uuid": None,
                },
            )
            self.assertEqual(final.state, ReconciliationState.RECONCILED)
            self.assertTrue(store.load().verify())
            with self.assertRaises(ValueError):
                store.cas_reconciled(pending.record_sha256, final.postcondition)

    def test_operation_probe_mismatch_and_extra_keys_fail_closed(self):
        with self.assertRaises(ValueError):
            ReconciliationProbeRequest(
                1, uuid4(), 1, uuid4(), "mount", "a" * 64, "b" * 64,
                {
                    "probe_kind": "create_absent_or_consistent",
                    "image_path": "/tmp/image",
                    "expected_image_identity_sha256": None,
                    "keychain_query_sha256": "c" * 64,
                    "expected_encryption_uuid": None,
                },
            )


if __name__ == "__main__":
    unittest.main()
