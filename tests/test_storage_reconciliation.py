from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from storage_reconciliation import (
    ReconciliationProbeRequest,
    ReconciliationState,
    ReconciliationStore,
    canonical_json,
    digest,
)


class ReconciliationTests(unittest.TestCase):
    def test_canonical_json_orders_members_by_utf8_bytes(self):
        # UTF-8 byte ordering places the two-byte ``é`` after ASCII ``z``;
        # relying on Python code-point ordering would silently change hashes.
        self.assertEqual(canonical_json({"é": 1, "z": 2}), '{"z":2,"é":1}'.encode("utf-8"))

    def test_canonical_json_rejects_non_string_keys_before_stringification(self):
        with self.assertRaisesRegex(ValueError, "object keys must be strings"):
            canonical_json({1: "not allowed"})

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

    def test_record_hash_uses_normative_reconciliation_domain(self):
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
            record = store.create_pending(request)
            self.assertTrue(record.verify())
            self.assertEqual(
                record.record_sha256,
                digest("CORTEX-S3\x00RECONCILIATION\x00V1\x00", record.without_digest()),
            )

    def test_postcondition_hash_uses_normative_domain(self):
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
            postcondition = {
                "kind": "create",
                "disposition": "absent",
                "image_present": False,
                "image_identity_sha256": None,
                "keychain_item_count": 0,
                "encryption_uuid": None,
            }
            final = store.cas_reconciled(pending.record_sha256, postcondition)
            self.assertEqual(
                final.postcondition_sha256,
                digest("CORTEX-S3\x00RECONCILIATION-POSTCONDITION\x00V1\x00", postcondition),
            )


if __name__ == "__main__":
    unittest.main()
