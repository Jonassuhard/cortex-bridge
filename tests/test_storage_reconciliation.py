from __future__ import annotations

import tempfile
import json
import os
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
    def test_delete_reconciliation_requires_matching_zero_item_observation(self):
        candidates = [
            {"kind": "delete_disposable_item", "item_count": 0, "transaction_match": False},
            {"kind": "delete_disposable_item", "item_count": False, "transaction_match": True},
            {"kind": "mount", "disposition": "absent", "mapping_count": 0,
             "mount_empty": True, "mounted_image_proof_sha256": None},
        ]
        for candidate in candidates:
            with self.subTest(candidate=candidate), tempfile.TemporaryDirectory() as td:
                path = Path(td) / "state/reconciliation.json"
                store = ReconciliationStore(path)
                pending = store.create_pending(ReconciliationProbeRequest(
                    1, uuid4(), 1, uuid4(), "delete-disposable-item", "a" * 64, "b" * 64,
                    {"probe_kind": "deleted_item_count_zero", "keychain_query_sha256": "c" * 64,
                     "transaction_match": True}))
                before = path.read_bytes()
                with self.assertRaises(ValueError):
                    store.cas_reconciled(pending.record_sha256, candidate)
                self.assertEqual(path.read_bytes(), before)

    def test_valid_mount_observations_round_trip(self):
        for count, disposition, empty, proof in ((0, "absent", True, None),
                                                 (1, "exact_mapping", False, "d" * 64)):
            with self.subTest(disposition=disposition), tempfile.TemporaryDirectory() as td:
                store = ReconciliationStore(Path(td) / "state/reconciliation.json")
                request = ReconciliationProbeRequest(1, uuid4(), 1, uuid4(), "mount", "a" * 64, "b" * 64,
                    {"probe_kind": "mount_mapping_zero_or_one", "image_path": "/tmp/image",
                     "mount_path": "/tmp/mount", "expected_volume_name": "fixture",
                     "expected_volume_uuid": str(uuid4()), "expected_encryption_uuid": str(uuid4())})
                pending = store.create_pending(request)
                final = store.cas_reconciled(pending.record_sha256,
                    {"kind": "mount", "disposition": disposition, "mapping_count": count,
                     "mount_empty": empty, "mounted_image_proof_sha256": proof})
                self.assertEqual(store.load(), final)
                self.assertEqual(final.state, ReconciliationState.RECONCILED)

    def test_reload_refuses_noncanonical_and_linked_record(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state/reconciliation.json"
            store = ReconciliationStore(path)
            store.create_pending(ReconciliationProbeRequest(
                1, uuid4(), 1, uuid4(), "detach", "a" * 64, "b" * 64,
                {"probe_kind": "detach_mapping_zero", "image_path": "/tmp/image", "mount_path": "/tmp/mount"}))
            canonical = path.read_bytes()
            path.write_bytes(b" " + canonical)
            with self.assertRaises(ValueError):
                store.load()
            path.write_bytes(canonical)
            alias = path.parent / "alias.json"
            alias.symlink_to(path)
            with self.assertRaises((ValueError, OSError)):
                ReconciliationStore(alias).load()
            alias.unlink()
            os.link(path, alias)
            with self.assertRaises(ValueError):
                store.load()

    def test_reload_rejects_rehashed_but_invalid_final_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state/reconciliation.json"
            store = ReconciliationStore(path)
            pending = store.create_pending(ReconciliationProbeRequest(
                1, uuid4(), 1, uuid4(), "detach", "a" * 64, "b" * 64,
                {"probe_kind": "detach_mapping_zero", "image_path": "/tmp/image", "mount_path": "/tmp/mount"}))
            store.cas_reconciled(pending.record_sha256,
                                 {"kind": "detach", "mapping_count": 0, "mount_empty": True})
            original = json.loads(path.read_bytes())
            for mutation in ("contradiction", "digest", "predecessor", "pending_with_result"):
                with self.subTest(mutation=mutation):
                    raw = json.loads(json.dumps(original))
                    if mutation == "contradiction":
                        raw["postcondition"]["mount_empty"] = False
                        raw["postcondition_sha256"] = digest("CORTEX-S3\x00RECONCILIATION-POSTCONDITION\x00V1\x00", raw["postcondition"])
                    elif mutation == "digest":
                        raw["postcondition_sha256"] = "f" * 64
                    elif mutation == "predecessor":
                        raw["previous_record_sha256"] = None
                    else:
                        raw["state"] = "pending"
                    raw["record_sha256"] = digest("CORTEX-S3\x00RECONCILIATION\x00V1\x00",
                        {key: value for key, value in raw.items() if key != "record_sha256"})
                    data = canonical_json(raw)
                    path.write_bytes(data)
                    with self.assertRaises(ValueError):
                        store.load()
                    self.assertEqual(path.read_bytes(), data)

    def test_contradictory_mount_observations_never_commit_reconciled(self):
        valid = {"kind": "mount", "disposition": "absent", "mapping_count": 0,
                 "mount_empty": True, "mounted_image_proof_sha256": None}
        for bad in ({**valid, "mount_empty": False}, {**valid, "mapping_count": False},
                    {**valid, "disposition": "exact_mapping"},
                    {**valid, "mounted_image_proof_sha256": "a" * 64},
                    {**valid, "disposition": "unknown"}):
            with self.subTest(postcondition=bad), tempfile.TemporaryDirectory() as td:
                path = Path(td) / "state/reconciliation.json"
                store = ReconciliationStore(path)
                request = ReconciliationProbeRequest(1, uuid4(), 1, uuid4(), "mount", "a" * 64, "b" * 64,
                    {"probe_kind": "mount_mapping_zero_or_one", "image_path": "/tmp/image",
                     "mount_path": "/tmp/mount", "expected_volume_name": "fixture",
                     "expected_volume_uuid": str(uuid4()), "expected_encryption_uuid": str(uuid4())})
                pending = store.create_pending(request)
                before = path.read_bytes()
                with self.assertRaises(ValueError):
                    store.cas_reconciled(pending.record_sha256, bad)
                self.assertEqual(path.read_bytes(), before)

    def test_nonempty_detach_observation_never_commits_reconciled(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state/reconciliation.json"
            store = ReconciliationStore(path)
            pending = store.create_pending(ReconciliationProbeRequest(
                1, uuid4(), 1, uuid4(), "detach", "a" * 64, "b" * 64,
                {"probe_kind": "detach_mapping_zero", "image_path": "/tmp/image", "mount_path": "/tmp/mount"}))
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                store.cas_reconciled(pending.record_sha256,
                                     {"kind": "detach", "mapping_count": 0, "mount_empty": False})
            self.assertEqual(path.read_bytes(), before)

    def test_canonical_json_orders_members_by_utf8_bytes(self):
        # UTF-8 byte ordering places the two-byte ``é`` after ASCII ``z``;
        # relying on Python code-point ordering would silently change hashes.
        self.assertEqual(canonical_json({"é": 1, "z": 2}), '{"z":2,"é":1}'.encode("utf-8"))

    def test_all_control_scalars_use_long_lowercase_escapes(self):
        for value in range(32):
            with self.subTest(value=value):
                expected = ('{"x":"\\u%04x"}' % value).encode("ascii")
                self.assertEqual(canonical_json({"x": chr(value)}), expected)
        self.assertEqual(canonical_json({"x": "\\n"}), b'{"x":"\\\\n"}')

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
