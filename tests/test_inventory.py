"""Read-only project metadata inventory: real files, exclusions and bounds."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from orchestration import artifacts


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def inventory(self, **kwargs):
        self.assertTrue(hasattr(artifacts, 'inventory'), 'metadata inventory missing')
        return artifacts.inventory(self.root, **kwargs)

    def test_nested_inventory_has_relative_metadata_not_contents(self):
        (self.root / 'src').mkdir()
        (self.root / 'src/main.py').write_text('print(1)\n')
        (self.root / 'README.md').write_text('demo')
        before = {p.relative_to(self.root).as_posix(): p.read_bytes()
                  for p in self.root.rglob('*') if p.is_file()}
        result = self.inventory()
        self.assertEqual(result['files'], [
            {'path': 'README.md', 'bytes': 4}, {'path': 'src/main.py', 'bytes': 9}])
        self.assertTrue(result['eligible_scan_complete'])
        self.assertFalse(result['contents_read'])
        self.assertFalse(result['delivery_verified'])
        self.assertEqual(before, {p.relative_to(self.root).as_posix(): p.read_bytes()
                                 for p in self.root.rglob('*') if p.is_file()})

    def test_private_paths_and_links_are_explicitly_excluded(self):
        (self.root / '.env').write_text('private fixture')
        (self.root / 'data.txt').write_text('public fixture')
        (self.root / 'alias').symlink_to(self.root)
        result = self.inventory()
        self.assertEqual(result['files'], [{'path': 'data.txt', 'bytes': 14}])
        excluded = {e['path']: e['reason'] for e in result['excluded']}
        self.assertEqual(excluded['alias'], 'symlink')
        self.assertEqual(excluded['.env'], 'private_or_invalid_path')
        self.assertFalse(result['full_project_coverage'])
        self.assertNotIn('private fixture', json.dumps(result))

    def test_limit_never_reports_complete_and_root_link_is_refused(self):
        for name in ('a.txt', 'b.txt', 'c.txt'):
            (self.root / name).write_text('data')
        result = self.inventory(max_entries=1)
        self.assertFalse(result['eligible_scan_complete'])
        self.assertIn('entry_limit', result['issues'])
        self.assertLessEqual(len(result['files']), 1)
        (self.root / 'alias').symlink_to(self.root)
        with self.assertRaises(artifacts.ArtifactError):
            artifacts.inventory(self.root / 'alias')

    def test_cli_inventory_is_read_only_and_not_an_archive(self):
        (self.root / 'readme.txt').write_text('hello')
        run = subprocess.run([sys.executable, '-m', 'orchestration.artifacts',
                              '--workspace', str(self.root), '--inventory'],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result['protocol'], 'cortex-inventory.v1')
        self.assertEqual(result['files'], [{'path': 'readme.txt', 'bytes': 5}])
        self.assertEqual([p.name for p in self.root.iterdir()], ['readme.txt'])

    def test_invalid_limits_missing_root_and_special_file(self):
        for limit in (0, -1, True, 10001):
            with self.assertRaises(artifacts.ArtifactError):
                self.inventory(max_entries=limit)
        with self.assertRaises(artifacts.ArtifactError):
            artifacts.inventory(self.root / 'missing')
        if hasattr(os, 'mkfifo'):
            os.mkfifo(self.root / 'pipe')
            result = self.inventory()
            self.assertEqual(result['files'], [])
            self.assertIn({'path': 'pipe', 'reason': 'not_regular_file'}, result['excluded'])

    def test_partial_cli_exit_is_not_success_or_silent_truncation(self):
        for n in ('a', 'b'):
            (self.root / n).write_text('fixture')
        run = subprocess.run([sys.executable, '-m', 'orchestration.artifacts',
                              '--workspace', str(self.root), '--inventory', '--inventory-limit', '1'],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        result = json.loads(run.stdout)
        self.assertFalse(result['eligible_scan_complete'])
        self.assertFalse(result['full_project_coverage'])
        self.assertIn('entry_limit', result['issues'])
