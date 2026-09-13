"""Catch lost pending state on SIGKILL and cross-workspace source substitution.

Actual processes/files/SQLite; conversation identities are synthetic, not live.
"""
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import unittest

from orchestration.artifacts import ArtifactError, prepare
from orchestration.native_journal import prepare_context
from orchestration.store import Store, StoreError


class NativeCrashIsolationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.db = self.root / 'runs.db'
        self.store = Store(self.db, recover_interrupted=False)
        self.addCleanup(self.store.close)
        self.manifests = {}
        for key in ('a', 'b'):
            project = self.root / key
            project.mkdir()
            (project / 'brief.txt').write_text('project-' + key)
            self.store.create_mission(key, 'synthetic ' + key, str(project))
            self.store.bind_conversation(key, key, 'https://chatgpt.com/c/' + key)
            self.manifests[key] = {'protocol': 'cortex-artifacts.v1',
                                  'items': [x.manifest() for x in prepare(project, ['brief.txt'])]}

    def cli(self, **request):
        run = subprocess.run([sys.executable, '-B', '-m', 'orchestration.native_journal',
                              '--db', str(self.db)], input=json.dumps(request),
                             capture_output=True, text=True, timeout=10)
        return run.returncode, json.loads(run.stdout)

    def test_same_relative_name_cannot_substitute_another_projects_bytes(self):
        # Removing current-workspace source validation would wrongly accept B.
        with self.assertRaises((ArtifactError, StoreError)):
            prepare_context(self.store, 'a', 'a', 'head-a', 'request-a', self.manifests['b'])
        self.assertIsNone(self.store.unresolved_outbound('a'))
        with self.assertRaises(StoreError):
            prepare_context(self.store, 'a', 'b', 'head-b', 'request-a', self.manifests['a'])
        self.assertIsNone(self.store.unresolved_outbound('a'))
        prepare_context(self.store, 'b', 'b', 'head-b', 'request-b', self.manifests['b'])
        self.assertIsNotNone(self.store.unresolved_outbound('b'))

    @unittest.skipUnless(os.name == 'posix', 'actual SIGKILL test requires POSIX')
    def test_sigkill_preserves_pending_without_blocking_other_project(self):
        # Lost commit/recovery clearing pending would allow the forbidden resend.
        child = '''
import json,sys,time
from pathlib import Path
from orchestration.artifacts import prepare
from orchestration.native_journal import prepare_context
from orchestration.store import Store
s=Store(sys.argv[1],recover_interrupted=False)
m={'protocol':'cortex-artifacts.v1','items':[x.manifest() for x in prepare(Path(sys.argv[2]),['brief.txt'])]}
p=prepare_context(s,'a','a','head-a','request-a',m)
print(json.dumps(p),flush=True)
time.sleep(60)
'''
        process = subprocess.Popen([sys.executable, '-B', '-c', child, str(self.db),
                                    str(self.root / 'a')], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                self.assertTrue(selector.select(10), 'child did not durably prepare')
            prepared = json.loads(process.stdout.readline())
            self.assertIsNone(process.poll())
            process.kill()
            process.communicate(timeout=10)
            self.assertEqual(process.returncode, -signal.SIGKILL)
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)
        code, status = self.cli(operation='status', mission_id='a')
        self.assertEqual(code, 0)
        self.assertIsNotNone(status['pending'])
        self.assertIn(prepared['send_id'], json.dumps(status['pending']))
        code, _ = self.cli(operation='prepare_context', mission_id='a', conversation_id='a',
                           before_message_id='head-a', message='changed retry', manifest=self.manifests['a'])
        self.assertEqual(code, 2)
        code, other = self.cli(operation='prepare_context', mission_id='b', conversation_id='b',
                               before_message_id='head-b', message='request-b', manifest=self.manifests['b'])
        self.assertEqual(code, 0)
        self.assertNotEqual(other['send_id'], prepared['send_id'])
        code, stopped = self.cli(operation='stop', mission_id='a', reason='synthetic scoped stop')
        self.assertEqual(code, 0)
        self.assertEqual(stopped['state'], 'CANCELLED')
        self.assertIsNotNone(stopped['pending'])
        code, status_b = self.cli(operation='status', mission_id='b')
        self.assertEqual(code, 0)
        self.assertEqual(status_b['state'], 'IDLE')
        self.assertIn(other['send_id'], json.dumps(status_b['pending']))
        self.assertEqual((self.root / 'a/brief.txt').read_text(), 'project-a')
        self.assertEqual((self.root / 'b/brief.txt').read_text(), 'project-b')
