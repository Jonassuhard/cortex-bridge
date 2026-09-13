import io
import json
from pathlib import Path
import tempfile
import os
import subprocess
import sys
from types import SimpleNamespace
import unittest
import zipfile
from unittest.mock import patch

from orchestration.artifacts import Artifact, ArtifactError, pack, prepare, publish


class ArtifactTests(unittest.TestCase):
    def test_source_freshness_checks_bytes_not_only_size_or_mtime(self):
        from orchestration import artifacts
        self.assertTrue(hasattr(artifacts, 'verify_sources'), 'source freshness verifier missing')
        manifest = {'protocol': 'cortex-artifacts.v1', 'items': [prepare(self.root, ['file.txt'])[0].manifest()]}
        result = artifacts.verify_sources(self.root, manifest)
        self.assertEqual(result['state'], 'sources_match')
        self.assertFalse(result['delivery_verified'])
        info = (self.root / 'file.txt').stat()
        (self.root / 'file.txt').write_text('other')
        os.utime(self.root / 'file.txt', ns=(info.st_atime_ns, info.st_mtime_ns))
        with self.assertRaisesRegex(ArtifactError, 'STALE_SOURCE'):
            artifacts.verify_sources(self.root, manifest)

    def test_freshness_cli_refuses_changed_source_without_publishing(self):
        items = prepare(self.root, ['file.txt'])
        (self.root / 'manifest.json').write_text(json.dumps({
            'protocol': 'cortex-artifacts.v1', 'items': [i.manifest() for i in items]}))
        cmd = [sys.executable, '-m', 'orchestration.artifacts', '--workspace', str(self.root),
               '--verify-manifest', 'manifest.json']
        good = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(json.loads(good.stdout)['state'], 'sources_match')
        (self.root / 'file.txt').write_text('changed')
        bad = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
        self.assertNotIn(str(self.root), bad.stdout)
        self.assertEqual({p.name for p in self.root.iterdir()}, {'manifest.json', 'file.txt'})

    def test_freshness_refuses_untrusted_manifest_and_replaced_symlink(self):
        from orchestration.artifacts import verify_sources
        item = prepare(self.root, ['file.txt'])[0].manifest()
        for manifest in [None, {}, {'protocol': 'cortex-artifacts.v1', 'items': []},
                         {'protocol': 'cortex-artifacts.v1', 'items': [item, item]},
                         {'protocol': 'cortex-artifacts.v1', 'items': [{**item, 'path': '../escape'}]},
                         {'protocol': 'cortex-artifacts.v1', 'items': [{**item, 'bytes': True}]}]:
            with self.subTest(manifest=manifest), self.assertRaises(ArtifactError):
                verify_sources(self.root, manifest)
        (self.root / 'file.txt').rename(self.root / 'original.txt')
        (self.root / 'file.txt').symlink_to(self.root / 'original.txt')
        with self.assertRaises(ArtifactError):
            verify_sources(self.root, {'protocol': 'cortex-artifacts.v1', 'items': [item]})

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "file.txt").write_text("first")

    def test_snapshot_remains_exact_after_source_changes(self):
        items = prepare(self.root, ["file.txt"])
        (self.root / "file.txt").write_text("second")
        with zipfile.ZipFile(io.BytesIO(pack(items))) as z:
            self.assertEqual(z.read("file.txt"), b"first")
        self.assertEqual(pack(items), pack(items))
        self.assertFalse(items[0].manifest()["available_to_brain"])
        self.assertEqual(items[0].manifest()["delivery_state"], "prepared")

    def test_paths_rejected(self):
        for name in ["../file.txt", "/file.txt", ".env", "a/../file.txt", "C:foo", "a\\b", "a\nb", "node_modules/file.txt"]:
            with self.subTest(name=name), self.assertRaises(ArtifactError):
                prepare(self.root, [name])

    def test_control_characters_cannot_enter_archive_manifest(self):
        for character in ["\t", "\x1b", "\x7f", "\u0085", "\u202e"]:
            with self.subTest(character=repr(character)), self.assertRaises(ArtifactError):
                pack((Artifact("report" + character + ".txt", b"test"),))

    def test_mutable_payload_cannot_change_prepared_bytes(self):
        with self.assertRaises(ArtifactError):
            Artifact("file.txt", bytearray(b"mutable"))

    def test_symlinks_rejected(self):
        (self.root / "link").symlink_to(self.root / "file.txt")
        (self.root / "dirlink").symlink_to(self.root, target_is_directory=True)
        for name in ["link", "dirlink/file.txt"]:
            with self.subTest(name=name), self.assertRaises(ArtifactError):
                prepare(self.root, [name])

    def test_no_duplicate_selection(self):
        with self.assertRaises(ArtifactError):
            prepare(self.root, ["file.txt", "file.txt"])

    def test_secret_rejected(self):
        (self.root / "file.txt").write_text("password=" + "sensitive-value")
        with self.assertRaisesRegex(ArtifactError, "POSSIBLE_SECRET"):
            prepare(self.root, ["file.txt"])

    def test_size_limit(self):
        with patch("orchestration.artifacts.MAX_BYTES", 3), self.assertRaises(ArtifactError):
            prepare(self.root, ["file.txt"])

    def test_zip_member_confinement(self):
        with zipfile.ZipFile(self.root / "bundle.zip", "w") as z:
            z.writestr("../escape.txt", "no")
        with self.assertRaises(ArtifactError):
            prepare(self.root, ["bundle.zip"])
        self.assertFalse((self.root.parent / "escape.txt").exists())

    def test_zip_secret_rejected(self):
        with zipfile.ZipFile(self.root / "bundle.zip", "w") as z:
            z.writestr("data.txt", "password=" + "sensitive-value")
        with self.assertRaisesRegex(ArtifactError, "POSSIBLE_SECRET"):
            prepare(self.root, ["bundle.zip"])

    def test_valid_zip(self):
        with zipfile.ZipFile(self.root / "bundle.zip", "w") as z:
            z.writestr("data/value.txt", "synthetic data")
        self.assertEqual(len(prepare(self.root, ["bundle.zip"])), 1)

    def test_compression_bomb_rejected(self):
        with zipfile.ZipFile(self.root / "bundle.zip", "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("large.txt", "a" * 500000)
        with self.assertRaisesRegex(ArtifactError, "ARCHIVE_TOO_LARGE"):
            prepare(self.root, ["bundle.zip"])

    def test_fifo_does_not_block(self):
        os.mkfifo(self.root / "pipe")
        with self.assertRaisesRegex(ArtifactError, "NOT_REGULAR_FILE"):
            prepare(self.root, ["pipe"])

    def test_pack_revalidates_direct_candidates(self):
        for items in [(), (Artifact("../escape", b"x"),),
                      (Artifact("a", b"x"), Artifact("a", b"y"))]:
            with self.subTest(items=items), self.assertRaises(ArtifactError):
                pack(items)

    def test_total_limit(self):
        (self.root / "second.txt").write_text("second")
        with patch("orchestration.artifacts.MAX_TOTAL", 8), self.assertRaises(ArtifactError):
            prepare(self.root, ["file.txt", "second.txt"])

    def test_nested_archive_refused(self):
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as z:
            z.writestr("x.txt", "x")
        with zipfile.ZipFile(self.root / "bundle.zip", "w") as z:
            z.writestr("inner.dat", inner.getvalue())
        with self.assertRaisesRegex(ArtifactError, "NESTED_ARCHIVE"):
            prepare(self.root, ["bundle.zip"])

    def test_missing_root_normalized(self):
        with self.assertRaises(ArtifactError):
            prepare(self.root / "missing", ["file.txt"])

    def test_change_during_read_rejected(self):
        original = os.fstat
        calls = 0
        def changed(fd):
            nonlocal calls
            info = original(fd)
            calls += 1
            if calls == 2:
                return SimpleNamespace(st_size=info.st_size, st_mtime_ns=info.st_mtime_ns + 1, st_ctime_ns=info.st_ctime_ns)
            return info
        with patch("orchestration.artifacts.os.fstat", side_effect=changed), self.assertRaisesRegex(ArtifactError, "FILE_CHANGED"):
            prepare(self.root, ["file.txt"])

    def test_publish_never_overwrites(self):
        output = self.root / "ready.zip"
        payload = pack(prepare(self.root, ["file.txt"]))
        publish(output, payload)
        with self.assertRaises(FileExistsError):
            publish(output, b"other")
        self.assertEqual(output.read_bytes(), payload)

    def test_interrupted_publish_has_no_final_path(self):
        output = self.root / "ready.zip"
        with patch("orchestration.artifacts.os.fsync", side_effect=OSError("simulated storage failure")):
            with self.assertRaises(OSError):
                publish(output, b"partial candidate")
        self.assertFalse(output.exists())

    def test_cli_context_describes_actual_frozen_attachment(self):
        result = subprocess.run(
            [sys.executable, "-m", "orchestration.artifacts", "--workspace", str(self.root),
             "--file", "file.txt", "--output", str(self.root / "bundle.zip"),
             "--goal", "Review the selected implementation"],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(result.stdout)
        packet = manifest["context_packet"]
        self.assertEqual(packet["goal"], "Review the selected implementation")
        item = packet["available_context"][0]
        self.assertEqual(item["path"], "file.txt")
        self.assertEqual(item["size_bytes"], 5)
        self.assertEqual(item["sha256"], "a7937b64b8caa58f03721bb6bacf5c78cb235febe0e70b1b84cd99541461a08e")
        self.assertEqual(item["transmission"], "proposal_required")
        with zipfile.ZipFile(self.root / "bundle.zip") as archive:
            self.assertEqual(archive.read("file.txt"), b"first")
        self.assertNotIn(str(self.root), result.stdout)

    def test_invalid_goal_fails_before_archive_publication(self):
        result = subprocess.run(
            [sys.executable, "-m", "orchestration.artifacts", "--workspace", str(self.root),
             "--file", "file.txt", "--output", str(self.root / "bundle.zip"),
             "--goal", "x" * 4001],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stdout.strip(), "CLI must return a structured failure")
        self.assertEqual(json.loads(result.stdout)["delivery_state"], "not_sent")
        self.assertFalse((self.root / "bundle.zip").exists())


if __name__ == "__main__":
    unittest.main()
