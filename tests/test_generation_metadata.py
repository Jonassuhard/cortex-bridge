import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from uuid import uuid4


class GenerationMetadataTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("generation_metadata"), "Generation manifest producer is missing")
        import generation_metadata
        return generation_metadata

    def test_complete_staging_binds_files_and_interpreter_identity_and_detects_changes(self):
        api = self.api()
        from process_helper_build import build_native_helper_bundle
        from install_resource_tree import stage_application_resources
        from storage_reconciliation import digest
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve()
            native = build_native_helper_bundle(home)
            app = home / "app"
            source_fd = os.open(Path(__file__).resolve().parents[1], os.O_RDONLY | os.O_DIRECTORY)
            app_fd = os.open(app, os.O_RDONLY | os.O_DIRECTORY)
            try:
                stage_application_resources(source_fd, app_fd)
            finally:
                os.close(app_fd)
                os.close(source_fd)
            # Metadata fixtures are not a runnable Python installation.
            (app / "python").mkdir(mode=0o700)
            (app / "python/server.py").write_bytes(b"# metadata fixture\n")
            (app / "python/server.py").chmod(0o600)
            interpreter = app / "bin/python"
            shutil.copyfile(Path(sys.executable).resolve(), interpreter)
            interpreter.chmod(0o700)
            generation_id = uuid4()
            metadata = api.build_generation_metadata(home, generation_id, native)
            manifest = json.loads(metadata.manifest_bytes)
            record = json.loads(metadata.record_bytes)
            selector = json.loads(metadata.selector_bytes)
            self.assertEqual(list(manifest["native_helpers"]), list(native))
            self.assertEqual(record["owned_manifest_sha256"], hashlib.sha256(metadata.manifest_bytes).hexdigest())
            unsigned = dict(record)
            unsigned.pop("generation_record_sha256")
            self.assertEqual(record["generation_record_sha256"], digest("CORTEX-S3\x00INSTALLED-GENERATION\x00V1\x00", unsigned))
            self.assertEqual(selector, {"schema_version": 1, "generation_id": str(generation_id),
                                       "generation_record_sha256": record["generation_record_sha256"]})
            self.assertEqual(record["interpreter_ino"], interpreter.stat().st_ino)
            self.assertEqual(record["interpreter_sha256"], hashlib.sha256(interpreter.read_bytes()).hexdigest())
            paths = {entry["path"] for entry in manifest["app_tree"]}
            for required in ("python/server.py", "frontend/out/index.html", "chrome-extension/manifest.json",
                             "native-src/process_release.swift", "build-profiles/process-release-v1.json", "bin/python"):
                self.assertIn(required, paths)
            api.verify_generation_metadata(home, metadata)
            changed = app / "python/server.py"
            original = changed.read_bytes()
            changed.write_bytes(b"# changed\n")
            with self.assertRaises(ValueError):
                api.verify_generation_metadata(home, metadata)
            changed.write_bytes(original)
            api.verify_generation_metadata(home, metadata)
            previous = app / "bin/python.previous"
            interpreter.rename(previous)
            shutil.copyfile(previous, interpreter)
            interpreter.chmod(0o700)
            previous.unlink()
            with self.assertRaises(ValueError):
                api.verify_generation_metadata(home, metadata)

    def test_missing_application_never_produces_metadata(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises((ValueError, OSError)):
                api.build_generation_metadata(Path(directory).resolve(), uuid4(), {})


if __name__ == "__main__":
    unittest.main()
