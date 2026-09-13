"""Durable observed host references, never a process liveness assertion."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from orchestration.store import Store, StoreError


class NativeHandleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / 'run.db'
        self.store = Store(self.db, recover_interrupted=False)
        self.addCleanup(self.store.close)
        self.store.create_mission('a', 'test', temp.name)
        self.store.create_mission('b', 'test', temp.name)
        self.record = self.store.reserve_native_action('a', 'one', 'run_process', {})

    def attach(self, **changes):
        args = dict(mission_id='a', record_id=self.record, host='synthetic-host-scope', handle='session-17')
        args.update(changes)
        return self.store.attach_native_handle(**args)

    def test_reference_survives_reopen_and_cli_status_without_claiming_running(self):
        self.attach()
        run = subprocess.run([sys.executable, '-B', '-m', 'orchestration.native_journal',
                              '--db', str(self.db)], input=json.dumps({'operation':'status','mission_id':'a'}),
                             text=True, capture_output=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        reference = json.loads(run.stdout)['pending_actions'][0]['host_reference']
        self.assertEqual(reference['handle'], 'session-17')
        self.assertEqual(reference['host'], 'synthetic-host-scope')
        self.assertFalse(reference['liveness_verified'])

    def test_retry_same_reference_is_idempotent_but_replacement_refused(self):
        first = self.attach()
        self.assertEqual(self.attach(), first)
        with self.assertRaises(StoreError):
            self.attach(handle='replacement')
        self.assertEqual(len([e for e in self.store.rows('transport_events','a')
                              if e['event_type']=='NATIVE_HOST_REFERENCE']), 1)

    def test_wrong_mission_duplicate_scope_and_nonprocess_refused(self):
        with self.assertRaises(StoreError):
            self.attach(mission_id='b')
        self.attach()
        other = self.store.reserve_native_action('b', 'two', 'run_process', {})
        with self.assertRaises(StoreError):
            self.attach(mission_id='b', record_id=other)
        self.store.finish_native_action('b', other, 0, {'observed':True})
        tool = self.store.reserve_native_action('b', 'three', 'read_file', {}, receipt_kind='host_tool')
        with self.assertRaises(StoreError):
            self.attach(mission_id='b', record_id=tool, handle='new')

    def test_late_attachment_after_stop_allowed_but_after_receipt_refused(self):
        self.store.stop_native('a', 'stop')
        self.attach()
        self.assertEqual(self.store.get_mission('a')['state'], 'CANCELLED')
        self.store.finish_native_action('a', self.record, 0, {'observed':True})
        with self.assertRaises(StoreError):
            self.attach()

    def test_invalid_reference_rejected_without_event(self):
        for value in ('', '  ', 'bad\nline', 'x'*513, 17, None):
            with self.assertRaises(StoreError):
                self.attach(handle=value)
        self.assertEqual(self.store.rows('transport_events','a'), [])
