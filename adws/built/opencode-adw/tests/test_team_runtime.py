"""Runtime integration contracts with local resolver/native transports; no APIs."""
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import types
import unittest
from unittest import mock

import test_deep
import test_runtime

runtime = test_deep.runtime


class TeamRuntimeTests(unittest.TestCase):
    setUp = test_runtime.RuntimeTests.setUp

    def resolver(self, result=None):
        calls = []
        def resolve(request, **kwargs):
            calls.append((request, kwargs))
            folder = kwargs['receipt_dir'].parent
            before = json.loads((folder / 'report.json').read_text())
            self.assertEqual(before['state'], 'ROUTING_REPO')
            self.assertIsNone(before['repo'])
            self.assertNotIn('baseline', before)
            self.assertEqual(before['agents'], [])
            self.assertFalse((self.root / '.local/share/opencode-adw/locks').exists())
            value = result or {'status': 'resolved', 'selected_repo': str(self.repo),
                               'method': 'context', 'candidates': [], 'question': None}
            kwargs['receipt_dir'].mkdir()
            path = kwargs['receipt_dir'] / 'route.json'
            path.write_text(json.dumps(value))
            return dict(value, receipt_path=str(path))
        return types.SimpleNamespace(resolve=resolve, status=lambda: {'configured': True}), calls

    def invoke(self, command='route', extra=(), resolver=None):
        resolver, calls = resolver or self.resolver()
        output = io.StringIO()
        with mock.patch.dict(sys.modules, {'repo_router': resolver}), mock.patch.dict(os.environ, self.env), contextlib.redirect_stdout(output):
            code = runtime.main([command, '--request', 'implement task', '--output-root', str(self.runs),
                                 '--adw-id', 'test', *extra])
        report = json.loads((self.runs / 'test/report.json').read_text())
        return code, report, calls, json.loads(output.getvalue())

    def test_route_only_preserves_private_receipt_without_snapshot_or_agents(self):
        with mock.patch.object(runtime, 'git_snapshot', side_effect=AssertionError('source snapshot')):
            code, report, calls, summary = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(report['repo'], str(self.repo))
        self.assertEqual(report['workflow'], 'route')
        self.assertEqual(report['agents'], [])
        self.assertEqual(calls[0][1]['context_directory'], Path.cwd())
        self.assertIsNone(calls[0][1]['explicit_repo'])
        self.assertTrue(Path(summary['routing']['receipt_path']).is_file())
        self.assertEqual((self.runs / 'test').stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.runs / 'test/report.json').stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.agent_calls.exists())
        self.assertIn('finished_at', report)

    def test_ambiguity_retained_without_snapshot_native_or_builder(self):
        value = {'status': 'needs_clarification', 'selected_repo': None, 'method': 'ambiguous',
                 'candidates': [{'repo': '/one'}, {'repo': '/two'}], 'question': 'Which project, one or two?'}
        with mock.patch.object(runtime, 'git_snapshot', side_effect=AssertionError('source snapshot')):
            code, report, _, summary = self.invoke('run', ['--mode', 'team'], self.resolver(value))
        self.assertEqual(code, 1)
        self.assertEqual(report['state'], 'FAILED')
        self.assertEqual(report['error_code'], 'REPO_AMBIGUOUS')
        self.assertIsNone(report['repo'])
        self.assertTrue(report['routing']['needs_clarification'])
        self.assertEqual(summary['error'], value['question'])
        self.assertEqual(summary['routing']['candidates'], value['candidates'])
        self.assertNotIn('after', report)
        self.assertNotIn('team', report)

    def test_routing_unavailable_retains_failed_report(self):
        resolver = types.SimpleNamespace(resolve=mock.Mock(side_effect=RuntimeError('catalog missing')))
        code, report, _, summary = self.invoke('run', resolver=(resolver, []))
        self.assertEqual(code, 1)
        self.assertEqual(report['error_code'], 'ROUTING_UNAVAILABLE')
        self.assertIsNone(report['repo'])
        self.assertTrue(summary['routing']['needs_clarification'])
        self.assertIn('catalog missing', report['routing']['error'])
        self.assertFalse(self.agent_calls.exists())

    def test_bad_selected_root_fails_before_snapshot(self):
        value = {'status': 'resolved', 'selected_repo': str(self.root), 'method': 'fake'}
        with mock.patch.object(runtime, 'git_snapshot', side_effect=AssertionError('source snapshot')):
            code, report, _, _ = self.invoke('run', resolver=self.resolver(value))
        self.assertEqual(code, 1)
        self.assertEqual(report['error_code'], 'ROUTING_UNAVAILABLE')
        self.assertIsNone(report['repo'])
        self.assertNotIn('baseline', report)

    def test_context_none_explicit_override_and_workspace_environment(self):
        with mock.patch.dict(os.environ, {'OPENCODE_ADW_WORKSPACE_ROOT': str(self.root)}):
            code, _, calls, _ = self.invoke(extra=['--repo', str(self.repo), '--routing-context', 'none'])
        self.assertEqual(code, 0)
        self.assertIsNone(calls[0][1]['context_directory'])
        self.assertEqual(calls[0][1]['explicit_repo'], self.repo)
        self.assertEqual(calls[0][1]['workspace_root'], str(self.root))

    def test_context_override_passed_instead_of_server_cwd(self):
        code, _, calls, _ = self.invoke(extra=['--routing-context', str(self.repo)])
        self.assertEqual(code, 0)
        self.assertEqual(calls[0][1]['context_directory'], self.repo)

    def test_output_root_inside_selected_repo_prevents_execution(self):
        self.runs = self.repo / 'runs'
        with mock.patch.object(runtime, 'git_snapshot', side_effect=AssertionError('source snapshot')):
            code, report, _, _ = self.invoke('run')
        self.assertEqual(code, 1)
        self.assertIn('outside', report['error'])
        self.assertEqual(report['agents'], [])

    def native(self, *, fail_identity=False, interrupt=False, legacy=False):
        owner = self
        instances = []
        class NativeTeam:
            def __init__(self, repo, folder, **kwargs):
                self.repo, self.folder, self.options = repo, folder, kwargs
                self.children, self.closed, self.aborted = [], False, False
                instances.append(self)
            def __enter__(self):
                return self
            def environment(self):
                return dict(os.environ)
            def router_note(self, routing):
                self.routing = routing
            def command(self, role, label, model, prompt, timeout):
                self.children.append({'role': role, 'label': label, 'model': model,
                                      'state': 'running', 'session_id': 'ses_' + (role if legacy else str(len(self.children)))})
                persisted = json.loads((self.folder / 'report.json').read_text())
                owner.assertIn('team', persisted)
                if interrupt:
                    os.kill(os.getpid(), signal.SIGTERM)
                return [sys.executable, str(owner.bin / 'opencode'), '--agent', 'opencode-' + role,
                        '--model', model, prompt]
            def finish_child(self, label, stage):
                if fail_identity:
                    raise ValueError('Native child session mismatch')
                child = next(c for c in self.children if c['label'] == label)
                owner.assertEqual(stage['session_ids'], [child['session_id']])
                child['state'] = 'finished'
            def snapshot(self):
                return {'parent_session_id': 'ses_parent', 'children': [dict(c) for c in self.children],
                        'closed': self.closed, 'aborted': self.aborted}
            def abort_active(self):
                self.aborted = True
            def close(self):
                self.closed = True
        return types.SimpleNamespace(NativeTeam=NativeTeam), instances

    def team_deep(self, native, extra=(), mode='', decisions=None):
        resolver, calls = self.resolver()
        with mock.patch.dict(sys.modules, {'repo_router': resolver, 'native_team': native}):
            result = test_deep.DeepTests.invoke(self, mode, extra=['--mode', 'team', *extra], decisions=decisions)
        return result, calls

    def test_team_reuses_real_deep_pipeline_four_models_and_native_sessions(self):
        native, teams = self.native()
        (code, report, _), calls = self.team_deep(native, ['--planner-model', 'p/plan', '--testdesigner-model', 'p/test',
             '--worker-model', 'p/build', '--reviewer-model', 'p/review', '--native-server-url', 'http://localhost:1234',
             '--parent-session', 'ses_existing', '--parent-directory', str(self.root)])
        self.assertEqual(code, 0, report.get('error'))
        self.assertEqual(report['mode'], 'team')
        self.assertEqual(report['workflow'], 'team')
        self.assertEqual([a['role'] for a in report['agents']], ['planner', 'testdesigner', 'worker', 'reviewer'])
        self.assertEqual(report['models'], {'planner': 'p/plan', 'testdesigner': 'p/test', 'worker': 'p/build', 'reviewer': 'p/review'})
        self.assertTrue(report['deep']['after_tests']['passed'])
        self.assertTrue(report['deep']['test_hash_intact'])
        self.assertEqual(len(report['team']['children']), 4)
        self.assertTrue(all(c['state'] == 'finished' for c in report['team']['children']))
        self.assertTrue(report['team']['closed'])
        self.assertTrue(report['team']['aborted'])
        self.assertEqual(teams[0].options, {'server_url': 'http://localhost:1234', 'parent_session_id': 'ses_existing',
                                         'parent_directory': str(self.root)})
        self.assertEqual(teams[0].routing, report['routing'])
        for stage in report['agents']:
            self.assertEqual(stage['process']['command'][0], sys.executable)
        self.assertEqual(len(calls), 1)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(runtime.main(['status', '--output-root', str(self.runs)]), 0)
        status = json.loads(output.getvalue())['runs'][0]
        self.assertEqual(status['routing']['selected_repo'], report['routing']['selected_repo'])
        self.assertEqual(status['team']['parent_session_id'], report['team']['parent_session_id'])
        self.assertEqual(status['deep']['actual_tests'], report['deep']['actual_tests'])
        self.assertEqual(status['deep']['repairs_performed'], report['deep']['repairs_performed'])
        self.assertNotIn('before_tests', status['deep'])

    def test_native_identity_mismatch_fails_closed_and_cleans_up(self):
        native, teams = self.native(fail_identity=True)
        (code, report, _), _ = self.team_deep(native)
        self.assertEqual(code, 1)
        self.assertIn('session mismatch', report['error'])
        self.assertEqual(report['state'], 'FAILED')
        self.assertEqual([a['role'] for a in report['agents']], ['planner'])
        self.assertTrue(teams[0].closed)
        self.assertTrue(teams[0].aborted)

    def test_sigterm_retains_failure_cleans_children_and_restores_handler(self):
        native, teams = self.native(interrupt=True)
        previous = signal.getsignal(signal.SIGTERM)
        (code, report, _), _ = self.team_deep(native)
        self.assertEqual(code, 1)
        self.assertEqual(report['state'], 'FAILED')
        self.assertEqual(report['error'], 'Runtime terminated')
        self.assertTrue(teams[0].closed)
        self.assertTrue(teams[0].aborted)
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)

    def test_explicit_native_flags_enable_native_transport_in_legacy_review(self):
        native, teams = self.native(legacy=True)
        with mock.patch.dict(sys.modules, {'native_team': native}):
            code, report, _, _ = self.invoke('run', ['--mode', 'review', '--native-server-url', 'http://localhost:1234'])
        self.assertEqual(code, 0, report.get('error'))
        self.assertEqual(report['mode'], 'review')
        self.assertEqual([a['role'] for a in report['agents']], ['reviewer'])
        self.assertTrue(teams[0].closed)

    def test_sigterm_during_check_stops_before_further_roles_and_cleans_team(self):
        native, teams = self.native()
        execute = runtime.execute
        interrupted_prefixes = []
        def interrupt_check(argv, cwd, timeout, prefix, **kwargs):
            if prefix.name.endswith('-check-0'):
                interrupted_prefixes.append(prefix)
                argv = [sys.executable, '-c',
                        f'import os, signal, time; os.kill({os.getpid()}, signal.SIGTERM); time.sleep(10)']
                kwargs['shell'] = False
            return execute(argv, cwd, timeout, prefix, **kwargs)
        with mock.patch.object(runtime, 'execute', side_effect=interrupt_check):
            (code, report, decisions), _ = self.team_deep(native, ['--check', 'true'])
        self.assertEqual(code, 1)
        self.assertEqual(report['state'], 'FAILED')
        self.assertEqual([a['role'] for a in report['agents']], ['planner', 'testdesigner'])
        self.assertEqual(len(interrupted_prefixes), 1)
        receipt = json.loads(interrupted_prefixes[0].with_suffix('.process.json').read_text())
        self.assertEqual(receipt['error'], 'interrupted')
        self.assertNotEqual(receipt['exit_code'], 0)
        self.assertTrue(teams[0].closed)
        self.assertTrue(teams[0].aborted)
        self.assertEqual(report['deep']['repairs_performed'], 0)

    def test_native_timeout_failure_retains_process_receipt_and_closes_team(self):
        native, teams = self.native()
        execute = runtime.execute
        def timeout(argv, cwd, limit, prefix, **kwargs):
            if prefix.name == 'planner':
                argv = [sys.executable, '-c', 'import time; time.sleep(10)']
                limit = 0.02
            return execute(argv, cwd, limit, prefix, **kwargs)
        with mock.patch.object(runtime, 'execute', side_effect=timeout):
            (code, report, _), _ = self.team_deep(native)
        self.assertEqual(code, 1)
        self.assertIn('timeout', report['agents'][0]['process']['error'])
        self.assertEqual(report['state'], 'FAILED')
        self.assertTrue(teams[0].closed)
        self.assertTrue(teams[0].aborted)
        self.assertTrue(Path(report['agents'][0]['process']['stdout']).exists())

    def native_failure_case(self, kind):
        import native_team
        children, requests = [], []
        def request(method, path, directory, body=None, **kwargs):
            requests.append((method, path, directory))
            if method == 'GET' and path == '/api/session/ses_interactive':
                return {'id': 'ses_interactive', 'location': {'directory': str(self.root)}}
            if method == 'POST' and path == '/api/session':
                child = {'id': 'ses_child' + str(len(children)), 'parentID': body['parentID'],
                         'location': {'directory': str(self.root)}}
                children.append(child)
                return child
            if method == 'GET':
                return next(c for c in children if path == '/api/session/' + c['id'])
            if method == 'POST' and path.endswith('/move'):
                child = next(c for c in children if path == '/api/session/' + c['id'] + '/move')
                child['location'] = {'directory': body['directory']}
                return None
            if method == 'POST' and (path.endswith('/prompt') or path.endswith('/interrupt')):
                return True
            raise AssertionError((method, path))
        execute = runtime.execute
        def helper(argv, cwd, timeout, prefix, **kwargs):
            if prefix.name == 'planner':
                sid = argv[argv.index('--session') + 1]
                if kind == 'nonzero':
                    program = 'raise SystemExit(7)'
                else:
                    event = {'type': 'text', 'part': {'text': 'observed output'}}
                    if kind == 'parsed_error':
                        event.update(sessionID=sid, error={'message': 'provider failed'})
                    program = 'print(' + repr(json.dumps(event)) + ')'
                return execute([sys.executable, '-c', program], cwd, timeout, prefix, **kwargs)
            raise AssertionError('No subsequent roles may run after native failure')
        finish_child = native_team.NativeTeam.finish_child
        with mock.patch.object(native_team, 'API', return_value=types.SimpleNamespace(request=request)), \
                mock.patch.object(native_team.NativeTeam, '_start_server', side_effect=AssertionError('interactive server is supplied')), \
                mock.patch.object(native_team.NativeTeam, 'finish_child', autospec=True, side_effect=finish_child) as finish, \
                mock.patch.object(runtime, 'execute', side_effect=helper):
            (code, report, _), _ = self.team_deep(native_team, [
                '--native-server-url', 'http://localhost:1234', '--parent-session', 'ses_interactive',
                '--parent-directory', str(self.root)])
        self.assertEqual(code, 1)
        self.assertEqual(report['state'], 'FAILED')
        self.assertEqual(report['team']['parent_session_id'], 'ses_interactive')
        self.assertEqual(len(report['agents']), 1)
        stage = report['agents'][0]
        self.assertEqual(stage['native_finish_error'], 'NATIVE_CHILD_FAILED')
        self.assertIn('Process failed' if kind == 'nonzero' else 'error events', report['error'])
        finish.assert_called_once()
        self.assertEqual(finish.call_args.args[1:], ('planner', stage))
        child = next(c for c in report['team']['children'] if c['role'] == 'planner')
        self.assertEqual(child['state'], 'failed')
        self.assertTrue(child['abort_sent'])
        aborts = [path for method, path, _ in requests if path.endswith('/interrupt')]
        self.assertEqual(aborts, ['/api/session/' + child['session_id'] + '/interrupt'])
        self.assertFalse(any(path == '/api/session/ses_interactive/interrupt' for _, path, _ in requests))
        self.assertTrue(Path(stage['process']['stdout']).is_file())
        return stage

    def test_nonzero_native_helper_finishes_once_and_aborts_only_failed_child(self):
        stage = self.native_failure_case('nonzero')
        self.assertEqual(stage['process']['exit_code'], 7)

    def test_native_parsed_error_finishes_once_and_preserves_first_diagnostic(self):
        stage = self.native_failure_case('parsed_error')
        self.assertEqual(stage['process']['exit_code'], 0)
        self.assertTrue(stage['errors'])

    def test_native_missing_session_finishes_once_and_preserves_first_diagnostic(self):
        stage = self.native_failure_case('missing_session')
        self.assertEqual(stage['session_ids'], [])

    def test_conditional_consultation_is_also_a_native_child(self):
        native, teams = self.native()
        def decision(state, kwargs):
            return test_deep.DeepTests.advice('stop', 0.28) if state['phase'] == 'focus' else test_deep.DeepTests.advice('finish')
        (code, report, _), _ = self.team_deep(native, decisions=decision)
        self.assertEqual(code, 0, report.get('error'))
        self.assertGreater(len(report['team']['children']), 4)
        self.assertEqual(len(report['team']['children']), len(report['agents']))
        self.assertEqual(len(set(a['session_ids'][0] for a in report['agents'])), len(report['agents']))
        self.assertEqual([c['label'] for c in report['team']['children']], [a['label'] for a in report['agents']])
        self.assertTrue(teams[0].closed)

    def test_describe_team_configuration_does_not_resolve_or_start_native(self):
        router = types.SimpleNamespace(status=lambda: {'configured': False},
            resolve=mock.Mock(side_effect=AssertionError('discovery forbidden')))
        native = types.SimpleNamespace(NativeTeam=mock.Mock(side_effect=AssertionError('API forbidden')))
        output = io.StringIO()
        with mock.patch.dict(sys.modules, {'repo_router': router, 'native_team': native}), contextlib.redirect_stdout(output):
            self.assertEqual(runtime.main(['describe']), 0)
        described = json.loads(output.getvalue())
        workflows = {row['id']: row for row in described['workflows']}
        self.assertEqual(workflows['team']['agents'], workflows['deep']['agents'])
        self.assertTrue(described['native_team']['supported'])
        self.assertFalse(described['repo_router']['configured'])
        router.resolve.assert_not_called()
        native.NativeTeam.assert_not_called()

    def test_large_report_status_is_compact_and_preserves_evidence_file(self):
        folder = self.runs / 'large'
        folder.mkdir(parents=True)
        path = folder / 'report.json'
        trace = 'EXHAUSTIVE_SUBTEST_TRACE' * 50000
        decision = {'label': 'jev-decision', 'recommendation': 'stop', 'route': 'consult',
                    'confidence': 0.2, 'uncertain': True, 'model_resolved': 'jev-real',
                    'input_tokens': 12, 'output_tokens': 3, 'usage': {'input_tokens': 12, 'output_tokens': 3},
                    'state': {'test_errors': trace}}
        value = {'adw_id': 'large', 'state': 'FAILED', 'repo': str(self.repo), 'workflow': 'team',
                 'mode': 'team', 'models': {'worker': 'p/build', 'reviewer': 'p/review'},
                 'checks_state': 'FAILED', 'checks_executed': 4, 'error': 'Generated suite failed',
                 'routing': {'status': 'needs_clarification', 'selected_repo': None, 'method': 'semantic',
                             'question': 'Which project should handle this?', 'needs_clarification': True,
                             'confidence': 0.2, 'uncertain': True, 'jev': decision,
                             'candidates': [{'name': f'project-{i}', 'selected_repo': f'/projects/{i}',
                                             'aliases': [trace], 'paths': [trace]} for i in range(5)]},
                 'team': {'parent_session_id': 'ses_interactive', 'children': [
                     {'role': 'planner', 'label': 'planner', 'model': 'p/plan', 'session_id': 'ses_child',
                      'parent_id': 'ses_interactive', 'state': 'failed', 'execution': 'native',
                      'process': {'stdout': trace}, 'prompt': trace}]},
                 'deep': {'max_repairs': 2, 'repairs_performed': 1, 'actual_tests': 112,
                          'budget': {'consultations_performed': 1, 'consultations_by_point': {'jev-decision': 1}},
                          'jev_decisions': [decision], 'before_tests': {'checks': [{'stdout': trace}]},
                          'suite': {'code': trace}, 'consultations': [
                              {'phase': 'decision', 'label': 'decision-reviewer', 'review': {'verdict': 'FAIL', 'evidence': [trace]},
                               'effective_action': 'stop', 'model': 'p/review', 'session_ids': ['ses_review'],
                               'state': trace}]},
                 'capture': {'state': 'FAILED', 'process': {'exit_code': 7, 'stdout': '/logs/capture.stdout', 'command': [trace]}}}
        original = json.dumps(value).encode()
        self.assertGreater(len(original), 1024 * 1024)
        path.write_bytes(original)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(runtime.main(['status', '--output-root', str(self.runs), '--adw-id', 'large']), 0)
        encoded = output.getvalue()
        self.assertLess(len(encoded.encode()), 20000)
        self.assertNotIn('EXHAUSTIVE_SUBTEST_TRACE', encoded)
        row = json.loads(encoded)['runs'][0]
        self.assertEqual(row['state'], 'FAILED')
        self.assertEqual(row['report'], str(path.resolve()))
        self.assertEqual(row['checks_executed'], 4)
        self.assertEqual(row['deep']['actual_tests'], 112)
        self.assertEqual(row['deep']['repairs_performed'], 1)
        self.assertEqual(row['deep']['budget']['consultations_performed'], 1)
        self.assertEqual(row['deep']['jev_decisions'][0]['model_resolved'], 'jev-real')
        self.assertEqual(row['deep']['jev_decisions'][0]['usage'],
                         {'input_tokens': 12, 'output_tokens': 3, 'total_tokens': None, 'cost': None})
        self.assertEqual(row['deep']['consultations'][0]['review'], {'verdict': 'FAIL'})
        self.assertEqual(row['deep']['consultations'][0]['session_ids'], ['ses_review'])
        self.assertEqual(row['routing']['question'], value['routing']['question'])
        self.assertTrue(row['routing']['needs_clarification'])
        self.assertEqual(row['routing']['candidates'], [{'name': f'project-{i}', 'path': f'/projects/{i}'} for i in range(3)])
        self.assertEqual(row['team']['children'][0]['parent_id'], 'ses_interactive')
        self.assertEqual(row['capture']['process']['exit_code'], 7)
        self.assertEqual(path.read_bytes(), original)

    def test_old_status_metadata_remains_unknown_not_invented(self):
        row = runtime.status_summary({'adw_id': 'old', 'state': 'FAILED', 'deep': {
            'jev_decisions': [{'recommendation': 'stop'}], 'consultations': [{}]}}, self.runs / 'old/report.json')
        self.assertIsNone(row['routing'])
        self.assertIsNone(row['team'])
        self.assertIsNone(row['deep']['actual_tests'])
        self.assertIsNone(row['deep']['jev_decisions'][0]['label'])
        self.assertIsNone(row['deep']['consultations'][0]['review']['verdict'])
        self.assertEqual(row['state'], 'FAILED')


if __name__ == '__main__':
    unittest.main()
