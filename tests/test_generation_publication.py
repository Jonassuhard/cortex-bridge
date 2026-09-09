import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from generation_metadata import GenerationMetadata


class GenerationPublicationTests(unittest.TestCase):
    def setUp(self):
        import generation_publication
        self.api = generation_publication
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.install = self.root / "install"
        self.staging = self.root / "staging"
        for path in (self.install, self.staging):
            path.mkdir(mode=0o700)
        app = self.staging / "app"
        app.mkdir(mode=0o700)
        (app / "python").mkdir(mode=0o700)
        (app / "python/server.py").write_text("print('installed')\n")
        (app / "python/server.py").chmod(0o600)
        (app / "bin").mkdir(mode=0o700)
        (app / "bin/python").write_bytes(b"interpreter")
        (app / "bin/python").chmod(0o700)
        generation_id = uuid4()
        self.metadata = GenerationMetadata(
            generation_id,
            b'{"schema_version":1,"native_helpers":{}}',
            json.dumps({"schema_version": 1, "generation_id": str(generation_id),
                        "generation_record_sha256": "b" * 64}).encode(),
            json.dumps({"schema_version": 1, "generation_id": str(generation_id),
                        "generation_record_sha256": "b" * 64}).encode(),
        )

    def test_publish_moves_complete_app_and_switches_selector(self):
        with patch.object(self.api, "verify_generation_metadata"):
            result = self.api.publish_generation(self.install, self.staging, self.metadata)
        generation = self.install / "installed-generations" / str(self.metadata.generation_id)
        self.assertEqual(result["status"], "published")
        self.assertEqual((generation / "app/python/server.py").read_text(), "print('installed')\n")
        self.assertEqual((generation / "owned-manifest.json").read_bytes(), self.metadata.manifest_bytes)
        self.assertEqual((generation / "generation-record.json").read_bytes(), self.metadata.record_bytes)
        self.assertEqual(json.loads((self.install / "current-generation.json").read_bytes())["generation_id"],
                         str(self.metadata.generation_id))
        self.assertFalse((self.staging / "app").exists())
        self.assertFalse((self.install / "current-generation.json.tmp").exists())

    def test_failure_before_selector_keeps_previous_selector_and_new_generation_recoverable(self):
        previous_id = uuid4()
        generations = self.install / "installed-generations"
        generations.mkdir(mode=0o700)
        generations.chmod(0o700)
        (self.install / "current-generation.json").write_bytes(json.dumps({
            "schema_version": 1, "generation_id": str(previous_id),
            "generation_record_sha256": "a" * 64,
        }).encode())
        (self.install / "current-generation.json").chmod(0o600)
        with patch.object(self.api, "verify_generation_metadata"), \
             patch.object(self.api, "_write_selector", side_effect=OSError("selector flush failed")):
            with self.assertRaises(OSError):
                self.api.publish_generation(self.install, self.staging, self.metadata)
        selector = json.loads((self.install / "current-generation.json").read_bytes())
        self.assertEqual(selector["generation_id"], str(previous_id))
        self.assertTrue((self.install / "installed-generations" / str(self.metadata.generation_id)).is_dir())
        recovered = self.api.recover_generation_publication(self.install)
        self.assertEqual(recovered["status"], "pending_reconciliation")
        self.assertEqual(recovered["generation_id"], str(self.metadata.generation_id))

    def test_existing_generation_or_staging_conflict_is_refused_without_overwrite(self):
        target = self.install / "installed-generations" / str(self.metadata.generation_id)
        target.mkdir(parents=True, mode=0o700)
        target.parent.chmod(0o700)
        (target / "foreign").write_text("preserve")
        inode = target.stat().st_ino
        with patch.object(self.api, "verify_generation_metadata"):
            with self.assertRaises(FileExistsError):
                self.api.publish_generation(self.install, self.staging, self.metadata)
        self.assertEqual(target.stat().st_ino, inode)
        self.assertEqual((target / "foreign").read_text(), "preserve")
        self.assertTrue((self.staging / "app").is_dir())

    def test_recovery_recognizes_committed_selector_and_does_not_republish(self):
        with patch.object(self.api, "verify_generation_metadata"):
            self.api.publish_generation(self.install, self.staging, self.metadata)
        current = (self.install / "current-generation.json").read_bytes()
        recovered = self.api.recover_generation_publication(self.install)
        self.assertEqual(recovered["status"], "committed")
        self.assertEqual((self.install / "current-generation.json").read_bytes(), current)

    def test_recovery_rejects_nonregular_journal_instead_of_reporting_absence(self):
        for kind in ("symlink", "dangling", "directory", "fifo"):
            with self.subTest(kind=kind):
                home = self.root / kind
                home.mkdir(mode=0o700)
                marker = home / self.api.TRANSACTION_NAME
                if kind == "directory":
                    marker.mkdir(mode=0o700)
                elif kind == "fifo":
                    os.mkfifo(marker, 0o600)
                else:
                    target = home / "target"
                    if kind == "symlink":
                        target.write_text('{}')
                    marker.symlink_to(target)
                before = marker.lstat()
                with self.assertRaises(ValueError):
                    self.api.recover_generation_publication(home)
                self.assertEqual(marker.lstat().st_ino, before.st_ino)

    def test_recovery_rejects_invalid_journal_schema_without_rewriting(self):
        identifier = "11111111-1111-4111-8111-111111111111"
        valid = {"schema_version": 1, "state": "prepared", "generation_id": identifier}
        candidates = [
            {**valid, "state": "unknown"}, {**valid, "schema_version": True},
            {**valid, "generation_id": "../outside"}, {**valid, "extra": 1},
            {"state": "prepared", "generation_id": identifier},
        ]
        raws = [json.dumps(value).encode() for value in candidates]
        raws.append(json.dumps(valid).replace('"prepared"', '"committed", "state":"prepared"').encode())
        marker = self.install / self.api.TRANSACTION_NAME
        for raw in raws:
            with self.subTest(raw=raw):
                marker.write_bytes(raw)
                marker.chmod(0o600)
                with self.assertRaises(ValueError):
                    self.api.recover_generation_publication(self.install)
                self.assertEqual(marker.read_bytes(), raw)

    def test_recovery_rejects_public_or_hardlinked_journal(self):
        marker = self.install / self.api.TRANSACTION_NAME
        marker.write_text(json.dumps({"schema_version": 1, "state": "prepared",
                                     "generation_id": str(uuid4())}))
        marker.chmod(0o644)
        with self.assertRaises(ValueError):
            self.api.recover_generation_publication(self.install)
        marker.chmod(0o600)
        os.link(marker, self.install / "alias")
        with self.assertRaises(ValueError):
            self.api.recover_generation_publication(self.install)

    def test_recovery_rejects_unsafe_selector_without_changing_journal(self):
        marker = self.install / self.api.TRANSACTION_NAME
        original = json.dumps({"schema_version": 1, "state": "prepared",
                               "generation_id": str(uuid4())}).encode()
        marker.write_bytes(original)
        marker.chmod(0o600)
        selector = self.install / "current-generation.json"
        selector.symlink_to(self.root / "absent")
        with self.assertRaises(ValueError):
            self.api.recover_generation_publication(self.install)
        self.assertTrue(selector.is_symlink())
        self.assertEqual(marker.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
