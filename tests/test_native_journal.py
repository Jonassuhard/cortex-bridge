import importlib
import json
from pathlib import Path
import tempfile
import unittest
from orchestration.store import Store, StoreError


class NativeJournalTests(unittest.TestCase):
    def finalization_fixture(self):
        evidence = self.acceptance_evidence_fixture()
        observation = self.context_reply_fixture()
        review = {'reviewer': 'fixture-operator', 'criteria': [
            {'criterion_id': 'output', 'finding': 'Read actual output and checked the required result.'}]}
        return dict(first=observation, second=observation, evidence=evidence, review=review)

    def test_native_finalization_persists_evidence_and_refuses_replay(self):
        args = self.finalization_fixture()
        module = self.module()
        self.assertTrue(hasattr(module, 'finalize_native'), 'guarded finalization missing')
        result = module.finalize_native(self.store, 'm', **args)
        self.assertEqual(result['state'], 'COMPLETED')
        self.assertFalse(result['release_eligible'])
        self.store.close()
        self.store = Store(self.path, recover_interrupted=False)
        self.addCleanup(self.store.close)
        self.assertEqual(self.store.get_mission('m')['state'], 'COMPLETED')
        records = self.store.rows('validation_results', 'm')
        self.assertEqual(len(records), 1)
        retained = json.loads(records[0]['checks_json'])[0]
        self.assertEqual(retained['operator_review'], args['review'])
        self.assertEqual(retained['acceptance']['reported_acceptance'], 'PASS')
        with self.assertRaises(StoreError):
            module.finalize_native(self.store, 'm', **args)
        self.assertEqual(len(self.store.rows('validation_results', 'm')), 1)

    def test_finalization_refuses_missing_review_failure_and_stale_proof(self):
        import copy
        args = self.finalization_fixture()
        module = self.module()
        self.assertTrue(hasattr(module, 'finalize_native'), 'guarded finalization missing')
        for change in ({'review': {}}, {'review': {'reviewer': 'x', 'criteria': []}},
                       {'evidence': [{**args['evidence'][0], 'verdict': 'FAIL'}]}):
            with self.assertRaises(StoreError):
                module.finalize_native(self.store, 'm', **{**copy.deepcopy(args), **change})
            self.assertEqual(self.store.get_mission('m')['state'], 'IDLE')
            self.assertEqual(self.store.rows('validation_results', 'm'), [])
        (Path(self.temp.name) / 'proof.txt').write_text('changed')
        with self.assertRaises(ValueError):
            module.finalize_native(self.store, 'm', **args)
        self.assertEqual(self.store.get_mission('m')['iteration'], 0)

    def test_finalization_cannot_override_cancellation(self):
        args = self.finalization_fixture()
        module = self.module()
        self.assertTrue(hasattr(module, 'finalize_native'), 'guarded finalization missing')
        self.store.stop_native('m', 'operator stopped')
        with self.assertRaises(StoreError):
            module.finalize_native(self.store, 'm', **args)
        self.assertEqual(self.store.get_mission('m')['state'], 'CANCELLED')
        self.assertEqual(self.store.rows('validation_results', 'm'), [])

    def test_finalization_cli_rejects_pending_request(self):
        import subprocess
        import sys
        args = self.finalization_fixture()
        # A new request makes the former proposal stale even before receipt.
        self.module().prepare(self.store, 'm', 'conversation', 'assistant-receipt', 'new question')
        cmd = [sys.executable, '-m', 'orchestration.native_journal', '--db', str(self.path)]
        run = subprocess.run(cmd, input=json.dumps({'operation': 'finalize_native', 'mission_id': 'm', **args}),
                             text=True, capture_output=True)
        self.assertEqual(run.returncode, 2, run.stdout)
        self.assertEqual(self.store.get_mission('m')['state'], 'IDLE')
        self.assertEqual(self.store.rows('validation_results', 'm'), [])

    def test_finalization_cli_persists_completion(self):
        import subprocess
        import sys
        args = self.finalization_fixture()
        cmd = [sys.executable, '-m', 'orchestration.native_journal', '--db', str(self.path)]
        run = subprocess.run(cmd, input=json.dumps({'operation': 'finalize_native', 'mission_id': 'm', **args}),
                             text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stdout)
        self.assertEqual(json.loads(run.stdout)['state'], 'COMPLETED')
        self.assertEqual(self.store.get_mission('m')['state'], 'COMPLETED')

    def acceptance_evidence_fixture(self, exit_code=0):
        from orchestration.artifacts import prepare as prepare_artifacts
        self.module().define_acceptance(self.store, 'm', [{'id': 'output', 'description': 'Verify output'}])
        record = self.store.reserve_native_action('m', 'test-output', 'run_tests', {})
        proof = Path(self.temp.name) / 'proof.txt'
        proof.write_text('synthetic test output')
        manifest = {'protocol': 'cortex-artifacts.v1',
                    'items': [prepare_artifacts(Path(self.temp.name), ['proof.txt'])[0].manifest()]}
        self.store.finish_native_action('m', record, exit_code, {'proof_manifest': manifest})
        return [{'criterion_id': 'output', 'verdict': 'PASS', 'record_id': record}]

    def test_acceptance_evidence_integrity_is_not_completion(self):
        evidence = self.acceptance_evidence_fixture()
        module = self.module()
        self.assertTrue(hasattr(module, 'check_acceptance_evidence'), 'acceptance evidence checker missing')
        result = module.check_acceptance_evidence(self.store, 'm', evidence)
        self.assertEqual(result['evidence_integrity'], 'PASS')
        self.assertEqual(result['reported_acceptance'], 'PASS')
        self.assertFalse(result['completion_verified'])
        self.assertEqual(self.store.get_mission('m')['state'], 'IDLE')

    def test_acceptance_refuses_missing_duplicate_foreign_and_changed_proof(self):
        evidence = self.acceptance_evidence_fixture()
        module = self.module()
        self.assertTrue(hasattr(module, 'check_acceptance_evidence'), 'acceptance evidence checker missing')
        for supplied in ([], evidence + evidence, [{**evidence[0], 'record_id': 'foreign'}]):
            with self.assertRaises(StoreError):
                module.check_acceptance_evidence(self.store, 'm', supplied)
        (Path(self.temp.name) / 'proof.txt').write_text('tampered')
        with self.assertRaises(ValueError):
            module.check_acceptance_evidence(self.store, 'm', evidence)

    def test_acceptance_cannot_report_pass_from_failed_execution(self):
        evidence = self.acceptance_evidence_fixture(exit_code=17)
        module = self.module()
        self.assertTrue(hasattr(module, 'check_acceptance_evidence'), 'acceptance evidence checker missing')
        with self.assertRaises(StoreError):
            module.check_acceptance_evidence(self.store, 'm', evidence)
        evidence[0]['verdict'] = 'FAIL'
        result = module.check_acceptance_evidence(self.store, 'm', evidence)
        self.assertEqual(result['reported_acceptance'], 'FAIL')
    def test_acceptance_is_frozen_before_work_and_cannot_be_reduced(self):
        module = self.module()
        self.assertTrue(hasattr(module, 'define_acceptance'), 'acceptance baseline missing')
        criteria = [{'id': 'originals', 'description': 'All original file hashes remain unchanged'},
                    {'id': 'coverage', 'description': 'Every input is represented exactly once'}]
        result = module.define_acceptance(self.store, 'm', criteria)
        self.assertFalse(result['completion_verified'])
        same = module.define_acceptance(self.store, 'm', criteria)
        self.assertEqual(result['acceptance_sha256'], same['acceptance_sha256'])
        with self.assertRaises(StoreError):
            module.define_acceptance(self.store, 'm', criteria[:1])
        rows = self.store.rows('transport_events', 'm')
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0]['detail_json'])['criteria'], criteria)

    def test_acceptance_cannot_be_created_after_work_or_with_empty_duplicate_criteria(self):
        module = self.module()
        self.assertTrue(hasattr(module, 'define_acceptance'), 'acceptance baseline missing')
        criterion = {'id': 'check', 'description': 'Check actual output'}
        for criteria in ([], [criterion, criterion], [{'id': 'x', 'description': ''}]):
            with self.assertRaises(StoreError):
                module.define_acceptance(self.store, 'm', criteria)
        module.prepare(self.store, 'm', 'conversation', 'anchor', 'started')
        with self.assertRaises(StoreError):
            module.define_acceptance(self.store, 'm', [criterion])
    def test_bound_action_cli_round_trip_with_real_process_and_supplied_observations(self):
        import subprocess
        import sys
        observation = self.context_reply_fixture()
        payload = json.loads(observation['messages'][-1]['text'])
        payload['decision'].update(state='EXECUTE', terminal=False, action={
            'tool': 'run_process', 'arguments': {'argv': [sys.executable, '-c', "print('BOUND_PASS')"]}})
        observation['messages'][-1]['text'] = json.dumps(payload)
        cmd = [sys.executable, '-m', 'orchestration.native_journal', '--db', str(self.path)]
        request = {'operation': 'prepare_context_action', 'mission_id': 'm',
                   'first': observation, 'second': observation}
        prepared = subprocess.run(cmd, input=json.dumps(request), capture_output=True, text=True)
        self.assertEqual(prepared.returncode, 0, prepared.stdout)
        result = json.loads(prepared.stdout)
        self.assertFalse(result['execution_authorized'])
        # Test fixture explicitly authorizes this synthetic print subprocess.
        executed = subprocess.run(result['action']['arguments']['argv'], capture_output=True, text=True)
        self.assertEqual(executed.stdout, 'BOUND_PASS\n')
        receipt = {'operation': 'action_confirm', 'mission_id': 'm',
                   'record_id': result['record_id'], 'exit_code': executed.returncode,
                   'evidence': {'stdout': executed.stdout, 'stderr': executed.stderr}}
        confirmed = subprocess.run(cmd, input=json.dumps(receipt), capture_output=True, text=True)
        self.assertEqual(confirmed.returncode, 0, confirmed.stdout)
        self.assertEqual(self.store.pending_native_actions('m'), [])
        self.assertEqual(self.store.rows('tool_executions', 'm')[0]['exit_code'], 0)

    def test_checked_action_refuses_source_change_between_check_and_reservation(self):
        observation = self.context_reply_fixture()
        payload = json.loads(observation['messages'][-1]['text'])
        payload['decision'].update(state='EXECUTE', terminal=False,
                                   action={'tool': 'write_file', 'arguments': {'path': 'x', 'content': 'planned'}})
        observation['messages'][-1]['text'] = json.dumps(payload)
        checked = self.module().check_context_reply(self.store, 'm', observation, observation)
        (Path(self.temp.name) / 'source.txt').write_text('changed after checking')
        with self.assertRaises(ValueError):
            self.store.reserve_native_action('m', payload['decision']['actionId'], 'write_file',
                                              {'path': 'x', 'content': 'planned'},
                                              receipt_kind='host_tool', _checked_context=checked)
        self.assertEqual(self.store.rows('tool_executions', 'm'), [])
        self.assertEqual(self.store.rows('orchestrator_decisions', 'm'), [])
        self.assertEqual(self.store.get_mission('m')['iteration'], 0)

    def test_bound_context_blocks_unchecked_actions_and_complete_proposal(self):
        observation = self.context_reply_fixture()
        with self.assertRaises(StoreError):
            self.store.reserve_native_action('m', 'unbound', 'write_file', {'path': 'x', 'content': 'no'})
        module = self.module()
        self.assertTrue(hasattr(module, 'prepare_context_action'), 'bound action preparation missing')
        with self.assertRaises(StoreError):
            module.prepare_context_action(self.store, 'm', observation, observation)
        self.assertEqual(self.store.rows('tool_executions', 'm'), [])

    def test_bound_action_uses_checked_arguments_and_consumes_decision_once(self):
        observation = self.context_reply_fixture()
        payload = json.loads(observation['messages'][-1]['text'])
        payload['decision'].update(state='EXECUTE', terminal=False,
                                   action={'tool': 'write_file', 'arguments': {'path': 'result.txt', 'content': 'planned'}})
        observation['messages'][-1]['text'] = json.dumps(payload)
        module = self.module()
        self.assertTrue(hasattr(module, 'prepare_context_action'), 'bound action preparation missing')
        result = module.prepare_context_action(self.store, 'm', observation, observation)
        self.assertFalse(result['execution_authorized'])
        row = self.store.pending_native_actions('m')[0]
        arguments = json.loads(row['arguments_json'])
        self.assertEqual(arguments['arguments'], {'path': 'result.txt', 'content': 'planned'})
        self.assertEqual(arguments['context_binding']['message_id'], 'assistant-receipt')
        self.assertEqual(self.store.get_mission('m')['iteration'], 1)
        self.assertFalse((Path(self.temp.name) / 'result.txt').exists())
        self.store.finish_native_tool_action('m', result['record_id'], 'failed', {}, {'not_executed': True})
        from orchestration.protocol import DecisionError
        with self.assertRaises((StoreError, DecisionError)):
            module.prepare_context_action(self.store, 'm', observation, observation)
    def context_reply_fixture(self):
        from orchestration.artifacts import prepare as prepare_artifacts
        source = Path(self.temp.name) / 'source.txt'
        source.write_text('context')
        manifest = {'protocol': 'cortex-artifacts.v1',
                    'items': [prepare_artifacts(Path(self.temp.name), ['source.txt'])[0].manifest()]}
        sent = self.module().prepare_context(self.store, 'm', 'conversation', 'anchor', 'review', manifest)
        sent_observation = {'conversation_id': 'conversation', 'messages': [
            {'id': 'anchor', 'role': 'assistant', 'text': 'before'},
            {'id': 'user-receipt', 'role': 'user', 'text': sent['message']}]}
        self.module().confirm(self.store, 'm', sent_observation, sent_observation)
        event = next(e for e in reversed(self.store.rows('transport_events', 'm', order_by='rowid'))
                     if e['event_type'] == 'MESSAGE_SEND_STARTED')
        revision = json.loads(event['detail_json'])['checkpoint']['context']['selection_sha256']
        decision = {'protocol': 'cortex.v1', 'missionId': 'm',
                    'actionId': 'd9951e3c-fdb2-4b2b-924c-4fcbb82c84fb', 'iteration': 1,
                    'state': 'COMPLETE', 'summary': 'proposal only', 'action': None,
                    'acceptanceCriteria': ['Run independent acceptance'],
                    'requiresApproval': False, 'terminal': True}
        reply = {'id': 'assistant-receipt', 'role': 'assistant',
                 'text': json.dumps({'selection_sha256': revision, 'decision': decision})}
        return {'conversation_id': 'conversation', 'messages': sent_observation['messages'] + [reply]}

    def test_context_reply_validation_does_not_complete_or_authorize(self):
        observation = self.context_reply_fixture()
        module = self.module()
        self.assertTrue(hasattr(module, 'check_context_reply'), 'reply revision checker missing')
        result = module.check_context_reply(self.store, 'm', observation, observation)
        self.assertEqual(result['state'], 'context_reply_checked')
        self.assertFalse(result['execution_authorized'])
        self.assertFalse(result['completion_verified'])
        self.assertEqual(self.store.get_mission('m')['state'], 'IDLE')
        self.assertEqual(self.store.rows('tool_executions', 'm'), [])

    def test_context_reply_rejects_wrong_revision_changed_observation_and_stale_source(self):
        import copy
        observation = self.context_reply_fixture()
        module = self.module()
        self.assertTrue(hasattr(module, 'check_context_reply'), 'reply revision checker missing')
        wrong = copy.deepcopy(observation)
        payload = json.loads(wrong['messages'][-1]['text'])
        payload['selection_sha256'] = '0' * 64
        wrong['messages'][-1]['text'] = json.dumps(payload)
        with self.assertRaises(StoreError):
            module.check_context_reply(self.store, 'm', wrong, wrong)
        changed = copy.deepcopy(observation)
        changed['messages'][-1]['id'] = 'changed'
        with self.assertRaises(StoreError):
            module.check_context_reply(self.store, 'm', observation, changed)
        (Path(self.temp.name) / 'source.txt').write_text('stale')
        with self.assertRaises(ValueError):
            module.check_context_reply(self.store, 'm', observation, observation)

    def test_context_reply_refuses_wrong_thread_intervening_message_and_duplicate_id(self):
        import copy
        observation = self.context_reply_fixture()
        bad_thread = copy.deepcopy(observation)
        bad_thread['conversation_id'] = 'other'
        intervening = copy.deepcopy(observation)
        intervening['messages'].insert(-1, {'id': 'other-user', 'role': 'user', 'text': 'other task'})
        duplicate = copy.deepcopy(observation)
        duplicate['messages'][-1]['id'] = 'user-receipt'
        tampered = copy.deepcopy(observation)
        tampered['messages'][-2]['text'] += 'modified'
        for bad in (bad_thread, intervening, duplicate, tampered):
            with self.subTest(bad=bad), self.assertRaises(StoreError):
                self.module().check_context_reply(self.store, 'm', bad, bad)
        self.module().prepare(self.store, 'm', 'conversation', 'assistant-receipt', 'new request')
        with self.assertRaises(StoreError):
            self.module().check_context_reply(self.store, 'm', observation, observation)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "run.db"
        self.store = Store(self.path)
        self.addCleanup(self.store.close)
        self.store.create_mission("m", "goal", self.temp.name)
        self.store.bind_conversation("b", "m", "https://chatgpt.com/c/conversation")

    def module(self):
        self.assertTrue((Path(__file__).resolve().parents[1] / "orchestration/native_journal.py").exists())
        return importlib.import_module("orchestration.native_journal")

    def test_reopen_blocks_duplicate_then_records_observed_receipt(self):
        module = self.module()
        prepared = module.prepare(self.store, "m", "conversation", "anchor", "objective")
        self.store.close()
        store = Store(self.path)
        self.addCleanup(store.close)
        with self.assertRaises(StoreError):
            module.prepare(store, "m", "conversation", "anchor", "objective")
        snapshot = {"conversation_id": "conversation", "messages": [
            {"id": "anchor", "role": "assistant", "text": "before"},
            {"id": "receipt", "role": "user", "text": prepared["message"]}]}
        module.confirm(store, "m", snapshot, snapshot)
        self.assertIsNone(store.unresolved_outbound("m"))
        event = store.rows("transport_events", "m", order_by="rowid")[-1]
        detail = json.loads(event["detail_json"])
        self.assertEqual(detail["message_id"], "receipt")
        self.assertEqual(detail["evidence_source"], "host_observation_supplied")

    def test_wrong_conversation_cannot_reserve(self):
        module = self.module()
        with self.assertRaises(StoreError):
            module.prepare(self.store, "m", "other", "anchor", "objective")
        self.assertEqual(self.store.rows("transport_events", "m"), [])

    def test_context_request_binds_verified_revision_and_refuses_stale_bytes(self):
        from orchestration.artifacts import prepare as prepare_artifacts
        source = Path(self.temp.name) / 'source.txt'
        source.write_text('original context')
        manifest = {'protocol': 'cortex-artifacts.v1',
                    'items': [prepare_artifacts(Path(self.temp.name), ['source.txt'])[0].manifest()]}
        module = self.module()
        self.assertTrue(hasattr(module, 'prepare_context'), 'revision-bound preparation missing')
        prepared = module.prepare_context(self.store, 'm', 'conversation', 'anchor', 'review', manifest)
        detail = json.loads(self.store.unresolved_outbound('m')['detail_json'])
        context = detail['checkpoint']['context']
        self.assertIn(context['selection_sha256'], prepared['message'])
        self.assertFalse(context['delivery_verified'])
        self.assertNotIn('available_to_brain', context['manifest']['items'][0])
        self.assertEqual(context['manifest']['items'][0]['sha256'], manifest['items'][0]['sha256'])
        source.write_text('modified context')
        self.store.create_mission('stale', 'goal', self.temp.name)
        self.store.bind_conversation('bs', 'stale', 'https://chatgpt.com/c/conversation')
        with self.assertRaises(ValueError):
            module.prepare_context(self.store, 'stale', 'conversation', 'anchor', 'review', manifest)
        self.assertIsNone(self.store.unresolved_outbound('stale'))

    def test_context_cli_reserves_revision_before_returning_wire_text(self):
        import subprocess
        import sys
        from orchestration.artifacts import prepare as prepare_artifacts
        source = Path(self.temp.name) / 'source.txt'
        source.write_text('synthetic context')
        manifest = {'protocol': 'cortex-artifacts.v1',
                    'items': [prepare_artifacts(Path(self.temp.name), ['source.txt'])[0].manifest()],
                    'untrusted_extra': 'must not forward'}
        request = {'operation': 'prepare_context', 'mission_id': 'm',
                   'conversation_id': 'conversation', 'before_message_id': 'anchor',
                   'message': 'review', 'manifest': manifest}
        cmd = [sys.executable, '-m', 'orchestration.native_journal', '--db', str(self.path)]
        run = subprocess.run(cmd, input=json.dumps(request), text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stdout)
        returned = json.loads(run.stdout)
        pending = self.store.unresolved_outbound('m')
        self.assertEqual(pending['id'], returned['send_id'])
        self.assertNotIn('must not forward', returned['message'])
        self.assertNotIn('must not forward', pending['detail_json'])
        repeated = subprocess.run(cmd, input=json.dumps(request), text=True, capture_output=True)
        self.assertEqual(repeated.returncode, 2)

    def test_expired_native_send_refused_without_outbound_reservation(self):
        self.store.create_mission('expired', 'goal', self.temp.name,
                                  started_at=1, max_duration_seconds=1)
        self.store.bind_conversation('be', 'expired', 'https://chatgpt.com/c/conversation')
        with self.assertRaises(StoreError):
            self.module().prepare(self.store, 'expired', 'conversation', 'anchor', 'message')
        self.assertIsNone(self.store.unresolved_outbound('expired'))

    def test_native_round_budget_survives_reopen_and_payload_change(self):
        self.store.create_mission('limited', 'goal', self.temp.name, max_iterations=1)
        self.store.bind_conversation('bl', 'limited', 'https://chatgpt.com/c/conversation')
        sent = self.module().prepare(self.store, 'limited', 'conversation', 'anchor', 'first')
        observation = {'conversation_id': 'conversation', 'messages': [
            {'id': 'anchor', 'role': 'assistant', 'text': 'before'},
            {'id': 'receipt', 'role': 'user', 'text': sent['message']}]}
        self.module().confirm(self.store, 'limited', observation, observation)
        reopened = Store(self.path, recover_interrupted=False)
        self.addCleanup(reopened.close)
        with self.assertRaises(StoreError):
            self.module().prepare(reopened, 'limited', 'conversation', 'receipt', 'different')
        starts = [e for e in reopened.rows('transport_events', 'limited')
                  if e['event_type'] == 'MESSAGE_SEND_STARTED']
        self.assertEqual(len(starts), 1)

    def test_native_attempt_budget_counts_aborts_but_does_not_limit_web_rounds(self):
        self.store.create_mission('limited', 'goal', self.temp.name, max_iterations=1)
        self.store.bind_conversation('bl', 'limited', 'https://chatgpt.com/c/conversation')
        sent = self.module().prepare(self.store, 'limited', 'conversation', 'anchor', 'first')
        self.store.record_transport_event('abort', 'limited', 'MESSAGE_SEND_ABORTED',
                                          {'send_id': sent['send_id']})
        with self.assertRaises(StoreError):
            self.module().prepare(self.store, 'limited', 'conversation', 'anchor', 'first')
        # Legacy web clients retain their own loop budget enforcement.
        self.store.create_mission('web', 'goal', self.temp.name, max_iterations=1)
        for index in range(2):
            self.store.reserve_outbound(str(index), 'web', str(index))
            self.store.record_transport_event('settled-' + str(index), 'web',
                                              'MESSAGE_DELIVERED', {'send_id': str(index)})

    def test_cli_stop_is_scoped_durable_and_preserves_pending_receipts(self):
        import subprocess
        import sys
        self.store.create_mission('other', 'unrelated', self.temp.name)
        prepared = self.module().prepare(self.store, 'm', 'conversation', 'anchor', 'objective')
        action = self.store.reserve_native_action('m', 'a', 'test', {})
        cmd = [sys.executable, '-m', 'orchestration.native_journal', '--db', str(self.path)]
        request = {'operation': 'stop', 'mission_id': 'm', 'reason': 'operator requested stop'}
        for _ in range(2):
            run = subprocess.run(cmd, input=json.dumps(request), text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout)
            self.assertEqual(json.loads(run.stdout)['state'], 'CANCELLED')
        self.assertEqual(self.store.get_mission('other')['state'], 'IDLE')
        self.assertEqual(self.store.unresolved_outbound('m')['id'], prepared['send_id'])
        self.assertEqual(self.store.pending_native_actions('m')[0]['id'], action)
        with self.assertRaises(StoreError):
            self.store.reserve_native_action('m', 'next', 'test', {})
        self.store.finish_native_action('m', action, 0, {'observed': 'late real receipt'})
        snapshot = {'conversation_id': 'conversation', 'messages': [
            {'id': 'anchor', 'role': 'assistant', 'text': 'before'},
            {'id': 'receipt', 'role': 'user', 'text': prepared['message']}]}
        self.module().confirm(self.store, 'm', snapshot, snapshot)
        self.assertEqual(self.store.get_mission('m')['state'], 'CANCELLED')
        self.assertIsNone(self.store.unresolved_outbound('m'))

    def test_cli_reconciles_rendered_receipt_only_on_explicit_operation(self):
        import subprocess
        import sys
        prepared = self.module().prepare(self.store, "m", "conversation", "anchor", "objective")
        snapshot = {"conversation_id": "conversation", "messages": [
            {"id": "anchor", "role": "assistant", "text": "before"},
            {"id": "receipt", "role": "user", "text": prepared["message"]
             + "\n\n[User attached 1 file; file contents were not included]"}]}
        request = {"operation": "confirm_rendered", "mission_id": "m",
                   "first": snapshot, "second": snapshot, "attachment_counts": {"file": 1}}
        command = [sys.executable, "-m", "orchestration.native_journal", "--db", str(self.path)]
        run = subprocess.run(command, input=json.dumps(request), text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stdout)
        self.assertIsNone(self.store.unresolved_outbound("m"))
        again = subprocess.run(command, input=json.dumps(request), text=True, capture_output=True)
        self.assertEqual(again.returncode, 2)

    def test_explicit_rendered_receipt_preserves_raw_text_and_strict_mode(self):
        module = self.module()
        prepared = module.prepare(self.store, "m", "conversation", "anchor", "objective")
        raw = ("objective\n[cortex-transport send_id=" + prepared["send_id"] + "]"
               "\n\n[User attached 1 file; file contents were not included]"
               "\n\n[User attached 1 image; image contents were not included]")
        snapshot = {"conversation_id": "conversation", "messages": [
            {"id": "anchor", "role": "assistant", "text": "before"},
            {"id": "receipt", "role": "user", "text": raw}]}
        with self.assertRaises(StoreError):
            module.confirm(self.store, "m", snapshot, snapshot)
        self.assertTrue(hasattr(module, "confirm_rendered"), "explicit observation contract missing")
        result = module.confirm_rendered(self.store, "m", snapshot, snapshot,
                                         {"file": 1, "image": 1})
        self.assertIsNone(self.store.unresolved_outbound("m"))
        event = json.loads(self.store.rows("transport_events", "m", order_by="rowid")[-1]["detail_json"])
        self.assertEqual(event["raw_receipt"]["text"], raw)
        self.assertFalse(result["attachment_contents_verified"])

    def test_rendered_receipt_refuses_changed_body_tail_counts_and_observations(self):
        import copy
        module = self.module()
        self.assertTrue(hasattr(module, "confirm_rendered"), "explicit observation contract missing")
        prepared = module.prepare(self.store, "m", "conversation", "anchor", "objective\n\nkeep spacing")
        raw = (prepared["message"].replace("\n\n[cortex-transport", "\n[cortex-transport")
               + "\n\n[User attached 1 file; file contents were not included]")
        good = {"conversation_id": "conversation", "messages": [
            {"id": "anchor", "role": "assistant", "text": "before"},
            {"id": "receipt", "role": "user", "text": raw}]}
        for value in (raw.replace("objective", "changed"), raw.replace("\n\nkeep", "\nkeep"),
                      raw + "\nextra", raw.replace("1 file", "2 files"),
                      raw.replace("not included", "included")):
            bad = copy.deepcopy(good); bad["messages"][-1]["text"] = value
            with self.subTest(value=value), self.assertRaises(StoreError):
                module.confirm_rendered(self.store, "m", bad, bad, {"file": 1})
            self.assertIsNotNone(self.store.unresolved_outbound("m"))
        bad = copy.deepcopy(good); bad["messages"][-1]["id"] = "another"
        with self.assertRaises(StoreError):
            module.confirm_rendered(self.store, "m", good, bad, {"file": 1})
        for counts in ({}, {"file": True}, {"file": 0}, {"zip": 1}):
            with self.subTest(counts=counts), self.assertRaises(StoreError):
                module.confirm_rendered(self.store, "m", good, good, counts)
        module.confirm_rendered(self.store, "m", good, good, {"file": 1})

    def test_cli_initializes_new_bound_mission_without_replacing_database(self):
        import subprocess
        import sys
        path = Path(self.temp.name) / "fresh.db"
        request = {"operation": "init", "mission_id": "native-test", "objective": "test only",
                   "workspace": self.temp.name, "conversation_id": "conversation"}
        command = [sys.executable, "-m", "orchestration.native_journal", "--db", str(path)]
        result = subprocess.run(command, input=json.dumps(request), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        store = Store(path)
        self.addCleanup(store.close)
        self.assertFalse(store.get_mission("native-test")["release_eligible"])
        self.assertEqual(store.rows("conversation_bindings", "native-test")[0]["conversation_url"], "https://chatgpt.com/c/conversation")
        again = subprocess.run(command, input=json.dumps(request), text=True, capture_output=True)
        self.assertNotEqual(again.returncode, 0)
        self.assertEqual(store.get_mission("native-test")["objective"], "test only")

    def test_stopped_or_paused_missions_cannot_prepare(self):
        module = self.module()
        for state in ("CANCELLED", "PAUSED"):
            mission = "m-" + state
            self.store.create_mission(mission, "goal", self.temp.name)
            self.store.bind_conversation("b-" + state, mission, "https://chatgpt.com/c/conversation")
            self.store.transition(mission, state)
            with self.subTest(state=state), self.assertRaises(StoreError):
                module.prepare(self.store, mission, "conversation", "anchor", "objective")
            self.assertEqual(self.store.rows("transport_events", mission), [])
            with self.subTest(state=state), self.assertRaises(StoreError):
                self.store.reserve_outbound('late-' + state, mission, 'late objective',
                                            checkpoint={'channel': 'native_host'})

    def test_cli_prepare_persists_before_returning_payload(self):
        self.module()
        import subprocess
        import sys
        request = {"operation": "prepare", "mission_id": "m", "conversation_id": "conversation",
                   "before_message_id": "anchor", "message": "unique objective"}
        self.store.transition("m", "SELECTING_CONVERSATION")
        self.store.transition("m", "INITIALIZING_MISSION")
        self.store.transition("m", "SENDING_OBJECTIVE")
        self.store.transition("m", "WAITING_FOR_CHATGPT")
        run = subprocess.run([sys.executable, "-m", "orchestration.native_journal", "--db", str(self.path)],
                             input=json.dumps(request), text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(run.stdout.strip(), "CLI must return a receipt")
        result = json.loads(run.stdout)
        pending = self.store.unresolved_outbound("m")
        self.assertEqual(pending["id"], result["send_id"])
        self.assertIn(result["send_id"], result["message"])
        self.assertEqual(self.store.get_mission("m")["state"], "WAITING_FOR_CHATGPT")

    def test_missing_or_conflicting_receipt_never_clears_pending(self):
        module = self.module()
        prepared = module.prepare(self.store, "m", "conversation", "anchor", "objective")
        good = {"conversation_id": "conversation", "messages": [
            {"id": "anchor", "role": "assistant", "text": "before"},
            {"id": "receipt", "role": "user", "text": prepared["message"]}]}
        import copy
        bad_states = []
        bad = copy.deepcopy(good); bad["conversation_id"] = "wrong"; bad_states.append(bad)
        bad = copy.deepcopy(good); bad["messages"] = bad["messages"][1:]; bad_states.append(bad)
        bad = copy.deepcopy(good); bad["messages"][-1]["text"] = "old objective"; bad_states.append(bad)
        bad = copy.deepcopy(good); bad["messages"][-1]["id"] = "idx-1"; bad_states.append(bad)
        for bad in bad_states:
            with self.subTest(snapshot=bad), self.assertRaises(StoreError):
                module.confirm(self.store, "m", good, bad)
            self.assertIsNotNone(self.store.unresolved_outbound("m"))
