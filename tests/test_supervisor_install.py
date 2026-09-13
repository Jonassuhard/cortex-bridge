"""Real subprocess installation into disposable roots, no account changes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/install-supervisor.py"


class SupervisorInstallTests(unittest.TestCase):
    def test_installed_bound_workflow_and_stale_proof_refusal(self):
        """Real isolated helper processes; conversation observations are fixtures."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            target = root / 'skill'
            args = [sys.executable, str(SCRIPT), '--target', str(target)]
            plan = subprocess.run(args, capture_output=True, text=True, check=True)
            subprocess.run(args + ['--approve-plan', json.loads(plan.stdout)['plan_hash']],
                           capture_output=True, text=True, check=True)
            project = root / 'project'
            project.mkdir()
            (project / 'BRIEF.md').write_text('Create result.txt with the exact text verified.')
            def manifest(names):
                return {'protocol': 'cortex-artifacts.v1', 'items': [
                    {'path': n, 'bytes': len((project / n).read_bytes()),
                     'sha256': hashlib.sha256((project / n).read_bytes()).hexdigest()}
                    for n in names]}
            def call(operation, expected=0, **fields):
                run = subprocess.run([sys.executable, '-I',
                    str(target / 'scripts/supervisor-journal.py'), '--db', str(root / 'run.db')],
                    input=json.dumps({'operation': operation, 'mission_id': 'bound', **fields}),
                    capture_output=True, text=True, cwd=root)
                self.assertEqual(run.returncode, expected, run.stdout + run.stderr)
                return json.loads(run.stdout)
            call('init', objective='Fixture project', workspace=str(project), conversation_id='fixture')
            call('define_acceptance', criteria=[{'id': 'exact', 'description': 'Exact result bytes'}])
            prepared = call('prepare_context', conversation_id='fixture', before_message_id='head',
                            message='Synthetic observation fixture, not a live model.', manifest=manifest(['BRIEF.md']))
            # Independently compute the canonical selection reference used on the wire.
            selection = hashlib.sha256(json.dumps(manifest(['BRIEF.md'])['items'],
                sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            decision = {'protocol': 'cortex.v1', 'missionId': 'bound',
                'actionId': 'b428746e-653a-42e3-92f1-81b77b85a828', 'iteration': 1,
                'state': 'EXECUTE', 'summary': 'Create result',
                'action': {'tool': 'write_file', 'arguments': {'path': 'result.txt', 'content': 'verified'}},
                'acceptanceCriteria': ['Exact result bytes'], 'requiresApproval': False, 'terminal': False}
            observation = {'conversation_id': 'fixture', 'messages': [
                {'id': 'head', 'role': 'assistant', 'text': 'Before'},
                {'id': 'user', 'role': 'user', 'text': prepared['message']},
                {'id': 'reply', 'role': 'assistant', 'text': json.dumps(
                    {'selection_sha256': selection, 'decision': decision})}]}
            call('confirm', first=observation, second=observation)
            call('tool_prepare', expected=2, action_id='unchecked', tool='write_file', arguments={})
            reserved = call('prepare_context_action', first=observation, second=observation)
            self.assertEqual(reserved['action'], decision['action'])
            self.assertFalse(reserved['execution_authorized'])
            with (project / 'result.txt').open('x') as output:
                output.write(reserved['action']['arguments']['content'])
            self.assertEqual((project / 'result.txt').read_bytes(), b'verified')
            call('tool_confirm', record_id=reserved['record_id'], outcome='succeeded',
                 tool_result={'fixture_writer': True}, verification={'proof_manifest': manifest(['result.txt'])})
            evidence = [{'criterion_id': 'exact', 'verdict': 'PASS', 'record_id': reserved['record_id']}]
            accepted = call('check_acceptance_evidence', evidence=evidence)
            self.assertEqual(accepted['evidence_integrity'], 'PASS')
            self.assertFalse(accepted['completion_verified'])
            call('prepare_context_action', expected=2, first=observation, second=observation)
            final_manifest = manifest(['result.txt'])
            sent = call('prepare_context', conversation_id='fixture', before_message_id='reply',
                        message='Review the observed result', manifest=final_manifest)
            final_selection = hashlib.sha256(json.dumps(final_manifest['items'],
                sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            final_decision = {**decision, 'actionId': '79aeaf27-c3d4-4e8f-a53e-27597208e7ea',
                              'iteration': 2, 'state': 'COMPLETE', 'action': None, 'terminal': True}
            final_observation = {'conversation_id': 'fixture', 'messages': [
                observation['messages'][-1],
                {'id': 'final-user', 'role': 'user', 'text': sent['message']},
                {'id': 'final-reply', 'role': 'assistant', 'text': json.dumps(
                    {'selection_sha256': final_selection, 'decision': final_decision})}]}
            call('confirm', first=final_observation, second=final_observation)
            completed = call('finalize_native', first=final_observation, second=final_observation,
                             evidence=evidence, review={'reviewer': 'fixture operator', 'criteria': [
                                 {'criterion_id': 'exact', 'finding': 'Read result bytes and compared to verified.'}]})
            self.assertEqual(completed['state'], 'COMPLETED')
            self.assertFalse(completed['release_eligible'])
            # New installed CLI process must expose the durable terminal state.
            status = call('status')
            self.assertEqual(status.get('state'), 'COMPLETED')
            call('prepare_context', expected=2, conversation_id='fixture', before_message_id='final-reply',
                 message='Must not restart a completed mission', manifest=final_manifest)
            (project / 'result.txt').write_text('tampered')
            call('check_acceptance_evidence', expected=2, evidence=evidence)

    def test_plan_apply_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp).resolve() / "cortex-supervisor"
            args = [sys.executable, str(SCRIPT), "--target", str(target)]
            plan = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(plan.returncode, 0, plan.stderr)
            self.assertFalse(target.exists())
            data = json.loads(plan.stdout)
            applied = subprocess.run(args + ["--approve-plan", data["plan_hash"]], capture_output=True, text=True)
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual((target / "SKILL.md").read_bytes(), (ROOT / "cortex-supervisor/SKILL.md").read_bytes())
            self.assertEqual((target / "references/HARNESS_V065.md").read_bytes(), (ROOT / "HARNESS_V065.md").read_bytes())
            # Run from outside the checkout with isolated import paths.
            journal = target / "scripts/supervisor-journal.py"
            db = Path(temp).resolve() / "native.db"
            request = {"operation": "init", "mission_id": "standalone", "objective": "test",
                       "workspace": str(Path(temp).resolve()), "conversation_id": "fixture"}
            run = subprocess.run([sys.executable, "-I", str(journal), "--db", str(db)],
                                 input=json.dumps(request), text=True, capture_output=True, cwd=temp)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)["state"], "initialized")
            status = subprocess.run([sys.executable, "-I", str(journal), "--db", str(db)],
                                    input=json.dumps({"operation": "status", "mission_id": "standalone"}),
                                    text=True, capture_output=True, cwd=temp)
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIsNone(json.loads(status.stdout)["pending"])
            workspace = Path(temp).resolve() / "project"
            workspace.mkdir()
            payload = b"Synthetic project context for standalone packaging.\n"
            (workspace / "README.md").write_bytes(payload)
            scanned = subprocess.run([
                sys.executable, "-I", "-B", str(target / "scripts/supervisor-artifacts.py"),
                "--workspace", str(workspace), "--inventory"],
                text=True, capture_output=True, cwd=temp)
            self.assertEqual(scanned.returncode, 0, scanned.stdout + scanned.stderr)
            index = json.loads(scanned.stdout)
            self.assertEqual(index['files'], [{'path': 'README.md', 'bytes': len(payload)}])
            self.assertFalse(index['contents_read'])
            self.assertFalse(index['delivery_verified'])
            bundle = Path(temp).resolve() / "context.zip"
            packed = subprocess.run([
                sys.executable, "-I", str(target / "scripts/supervisor-artifacts.py"),
                "--workspace", str(workspace), "--file", "README.md",
                "--output", str(bundle), "--goal", "Review synthetic project",
            ], text=True, capture_output=True, cwd=temp)
            self.assertEqual(packed.returncode, 0, packed.stdout + packed.stderr)
            manifest = json.loads(packed.stdout)
            self.assertEqual(manifest["delivery_state"], "prepared")
            self.assertEqual(manifest["bundle_sha256"], hashlib.sha256(bundle.read_bytes()).hexdigest())
            self.assertEqual(manifest["items"][0]["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertFalse(manifest["items"][0]["available_to_brain"])
            self.assertIn("context_packet", manifest)
            with zipfile.ZipFile(bundle) as archive:
                self.assertEqual(archive.read("README.md"), payload)
            (workspace / "manifest.json").write_text(json.dumps(manifest))
            verify = [sys.executable, "-I", str(target / "scripts/supervisor-artifacts.py"),
                      "--workspace", str(workspace), "--verify-manifest", "manifest.json"]
            current = subprocess.run(verify, text=True, capture_output=True, cwd=temp)
            self.assertEqual(current.returncode, 0, current.stderr)
            self.assertEqual(json.loads(current.stdout)["state"], "sources_match")
            (workspace / "README.md").write_text("changed after packaging")
            stale = subprocess.run(verify, text=True, capture_output=True, cwd=temp)
            self.assertEqual(stale.returncode, 2, stale.stdout)
            self.assertEqual(hashlib.sha256(bundle.read_bytes()).hexdigest(), manifest["bundle_sha256"])
            def journal_call(request):
                return subprocess.run([sys.executable, "-I", str(journal), "--db", str(db)],
                                      input=json.dumps(request), text=True, capture_output=True, cwd=temp)
            action = {"operation": "action_prepare", "mission_id": "standalone",
                      "action_id": "write-fixture", "tool": "python",
                      "arguments": {"path": "effect.txt"}}
            reserved = journal_call(action)
            self.assertEqual(reserved.returncode, 0, reserved.stdout + reserved.stderr)
            record = json.loads(reserved.stdout)
            self.assertFalse(record["execution_authorized"])
            effect = workspace / "effect.txt"
            executed = subprocess.run([sys.executable, "-I", "-c",
                                      "import sys; from pathlib import Path; Path(sys.argv[1]).open('x').write('fixture')",
                                      str(effect)], text=True, capture_output=True, cwd=temp)
            self.assertEqual(executed.returncode, 0, executed.stderr)
            self.assertEqual(effect.read_text(), "fixture")
            pending = journal_call({"operation": "status", "mission_id": "standalone"})
            self.assertEqual(json.loads(pending.stdout)["pending_actions"][0]["id"], record["record_id"])
            self.assertNotEqual(journal_call(action).returncode, 0)
            confirmed = journal_call({"operation": "action_confirm", "mission_id": "standalone",
                                      "record_id": record["record_id"], "exit_code": executed.returncode,
                                      "evidence": {"sha256": hashlib.sha256(effect.read_bytes()).hexdigest()}})
            self.assertEqual(confirmed.returncode, 0, confirmed.stdout + confirmed.stderr)
            self.assertNotEqual(journal_call(action).returncode, 0)
            settled = journal_call({"operation": "status", "mission_id": "standalone"})
            self.assertEqual(json.loads(settled.stdout)["pending_actions"], [])
            host = journal_call({"operation": "tool_prepare", "mission_id": "standalone",
                                 "action_id": "host-fixture", "tool": "fixture-tool", "arguments": {}})
            self.assertEqual(host.returncode, 0, host.stdout)
            host_id = json.loads(host.stdout)["record_id"]
            host_done = journal_call({"operation": "tool_confirm", "mission_id": "standalone",
                                      "record_id": host_id, "outcome": "succeeded", "tool_result": {},
                                      "verification": {"synthetic_fixture": True}})
            self.assertEqual(host_done.returncode, 0, host_done.stdout)
            self.assertIsNone(json.loads(host_done.stdout)["exit_code"])
            before = (target / "SKILL.md").read_bytes()
            retry = subprocess.run(args + ["--approve-plan", data["plan_hash"]], capture_output=True, text=True)
            self.assertNotEqual(retry.returncode, 0)
            self.assertEqual((target / "SKILL.md").read_bytes(), before)

    def test_wrong_hash_has_no_effect(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp).resolve() / "cortex-supervisor"
            result = subprocess.run([sys.executable, str(SCRIPT), "--target", str(target), "--approve-plan", "wrong"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["error"], "PLAN_CHANGED_OR_NOT_APPROVED")
            self.assertFalse(target.exists())

    def test_target_link_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            real = Path(temp).resolve() / "real"
            real.mkdir()
            link = Path(temp).resolve() / "alias"
            link.symlink_to(real)
            result = subprocess.run([sys.executable, str(SCRIPT), "--target", str(link / "cortex-supervisor")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SYMLINK_TARGET", json.loads(result.stdout)["error"])
            self.assertEqual(list(real.iterdir()), [])
