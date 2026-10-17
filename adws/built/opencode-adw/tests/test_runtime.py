"""Behavioral tests: no model calls; exercise the real CLI with a fake executable."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

RUNTIME = Path(__file__).resolve().parents[1] / 'runtime.py'
FAKE = '''#!/usr/bin/env python3
import json, os, sys, time
with open(os.environ['AGENT_CALLS'], 'a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\\n')
role = sys.argv[sys.argv.index('--agent') + 1]
mode = os.environ.get('FAKE_MODE', '')
sid = 'ses_worker' if role.endswith('worker') else 'ses_reviewer'
def emit(kind, part=None, **kw):
    print(json.dumps(dict(type=kind, sessionID=sid, part=part or {}, **kw)), flush=True)
if mode == 'timeout': time.sleep(5)
if mode == 'empty': sys.exit(0)
if mode == 'nonzero': sys.exit(4)
if mode == 'malformed': print('not json', flush=True)
if mode == 'same_session': sid = 'ses_worker'
if mode == 'no_session': sid = None
if mode == 'error': emit('error', error={'message':'provider failed'})
emit('tool_use', {'type':'tool', 'tool':'read', 'state':{'status':'error' if mode == 'tool_error' else 'completed'}})
if role.endswith('worker'):
    emit('text', {'text':'Implemented task'})
else:
    text = os.environ.get('REVIEW_OVERRIDE') or json.dumps({'verdict':'FAIL' if mode == 'fail' else 'PASS', 'findings':[], 'evidence':['inspected']})
    if mode == 'false_pass': text = 'The prompt says return ' + text
    if mode == 'fenced': text = '```json\\n' + text + '\\n```'
    if mode == 'mutation': open(os.environ.get('FAKE_TARGET', 'changed.txt'),'w').write('oops')
    emit('text', {'text':text})
'''
FAKE_NOTE = '''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['NOTE_CALLS'], 'a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\\n')
print('fake note receipt')
sys.exit(int(os.environ.get('NOTE_EXIT', '0')))
'''


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Test', '-c',
                        'user.email=test@example.invalid', 'commit', '-qm', 'initial', '--allow-empty'], check=True)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        executable = self.bin / 'opencode'
        executable.write_text(FAKE)
        executable.chmod(0o700)
        note = self.bin / 'vault-semantic'
        note.write_text(FAKE_NOTE)
        note.chmod(0o700)
        self.note_calls = self.root / 'note-calls.jsonl'
        self.env = dict(os.environ, HOME=str(self.root), PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        OPENCODE_ADW_OPENCODE=str(executable))
        self.env['NOTE_CALLS'] = str(self.note_calls)
        self.agent_calls = self.root / 'agent-calls.jsonl'
        self.env['AGENT_CALLS'] = str(self.agent_calls)
        self.runs = self.root / 'runs'
        # In-process Deep tests mock Jev's decision API, not repository discovery.
        # Keep that boundary explicit rather than letting repo_router cache a fake
        # Jev module that intentionally only implements Deep's public API.
        def resolve(request, *, context_directory=None, explicit_repo=None, receipt_dir,
                    workspace_root=None):
            repo = Path(explicit_repo or self.repo).resolve()
            top = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--show-toplevel'],
                                 capture_output=True, text=True, check=True)
            receipt_dir.mkdir(parents=True, exist_ok=True)
            receipt = receipt_dir / 'route.json'
            value = {'status': 'resolved', 'selected_repo': str(Path(top.stdout.strip()).resolve()),
                     'method': 'explicit' if explicit_repo else 'context', 'candidates': [], 'question': None,
                     'receipt_path': str(receipt)}
            receipt.write_text(json.dumps(value))
            return value
        patcher = mock.patch.dict(sys.modules, {'repo_router': types.SimpleNamespace(
            resolve=resolve, status=lambda: {'configured': True})})
        patcher.start()
        self.addCleanup(patcher.stop)

    def invoke(self, mode='', extra=(), command='run', identity='test'):
        result = subprocess.run([sys.executable, str(RUNTIME), command, '--repo', str(self.repo),
                                 '--request', 'Implement the task', '--output-root', str(self.runs),
                                 '--adw-id', identity, '--timeout', '0.3', *extra],
                                env=dict(self.env, FAKE_MODE=mode), capture_output=True, text=True, timeout=10)
        report = json.loads((self.runs / identity / 'report.json').read_text())
        self.assertTrue((self.runs / identity / 'handoff.md').exists())
        return result, report

    def test_pipeline_sessions_receipts_and_status(self):
        result, report = self.invoke(extra=['--check', f'{sys.executable} -c "print(42)"'])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(report['state'], 'PASSED')
        self.assertEqual([a['session_ids'] for a in report['agents']], [['ses_worker'], ['ses_reviewer']])
        self.assertTrue(report['agents'][0]['tools'])
        self.assertEqual(report['checks'][0]['exit_code'], 0)
        self.assertEqual(report['checks_executed'], 1)
        self.assertEqual(report['checks_state'], 'PASSED')
        self.assertEqual(report['baseline'], report['after'])
        self.assertTrue((self.runs / 'test/worker.events.jsonl').exists())
        self.assertEqual((self.runs / 'test/report.json').stat().st_mode & 0o777, 0o600)
        status = subprocess.run([sys.executable, str(RUNTIME), 'status', '--output-root', str(self.runs)],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(status.stdout)['runs'][0]['state'], 'PASSED')

    def test_describe_matches_executing_model_and_agent_roles(self):
        described = subprocess.run([sys.executable, str(RUNTIME), 'describe'],
                                  env=self.env, capture_output=True, text=True, check=True)
        config = json.loads(described.stdout)
        result, report = self.invoke(identity='described')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(config['default_model'], report['model'])
        self.assertEqual([row['id'] for row in config['agents'][:2]],
                         ['opencode-' + row['role'] for row in report['agents']])
        self.assertEqual([row['can_edit'] for row in config['agents']], [True, False, False, False])
        self.assertEqual(config['review_independence'], 'fresh_session_same_model')
        self.assertEqual([row['default_model'] for row in config['agents']],
                         [config['default_model']] * 4)
        self.assertEqual(config['workflows'][:3], [
            {'id': 'build', 'name': 'Build & review', 'command': 'run', 'mode': 'build',
             'agents': ['opencode-worker', 'opencode-reviewer']},
            {'id': 'review', 'name': 'Review only', 'command': 'run', 'mode': 'review',
             'agents': ['opencode-reviewer']},
            {'id': 'takeover', 'name': 'Continue previous work', 'command': 'takeover', 'mode': 'build',
             'agents': ['opencode-worker', 'opencode-reviewer']},
        ])
        self.assert_model_bindings(report, {'worker': config['default_model'],
                                            'reviewer': config['default_model']})

    def assert_model_bindings(self, report, models):
        self.assertEqual(report['models'], models)
        calls = [json.loads(line) for line in self.agent_calls.read_text().splitlines()]
        self.assertEqual(len(calls), len(report['agents']))
        for stage, argv in zip(report['agents'], calls):
            model = models[stage['role']]
            self.assertEqual(stage['model'], model)
            self.assertEqual(argv[:-1], ['run', '--format', 'json',
                                        '--agent', 'opencode-' + stage['role'], '--model', model])
            self.assertEqual(stage['process']['command'][1:], argv)

    def test_build_role_model_overrides_bind_exact_argv_and_report(self):
        models = {'worker': 'anthropic/claude-sonnet-4-5', 'reviewer': 'openai/gpt-6.1-sol'}
        result, report = self.invoke(extra=['--model', 'legacy/shared',
                                           '--worker-model', models['worker'],
                                           '--reviewer-model', models['reviewer']])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report['workflow'], 'build')
        self.assertEqual(report['model'], 'legacy/shared')
        self.assertEqual(report['review_independence'], 'fresh_session_cross_model')
        self.assert_model_bindings(report, models)

    def test_legacy_shared_model_override(self):
        result, report = self.invoke(extra=['--model', 'provider/shared-model'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report['model'], 'provider/shared-model')
        self.assertEqual(report['review_independence'], 'fresh_session_same_model')
        self.assert_model_bindings(report, dict.fromkeys(('worker', 'reviewer'), 'provider/shared-model'))

    def test_review_only_model_override(self):
        result, report = self.invoke(extra=['--mode', 'review', '--model', 'provider/shared',
                                           '--reviewer-model', 'provider/review'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report['workflow'], 'review')
        self.assertEqual([a['role'] for a in report['agents']], ['reviewer'])
        self.assertEqual(report['model'], 'provider/shared')
        self.assert_model_bindings(report, {'worker': 'provider/shared', 'reviewer': 'provider/review'})

    def test_takeover_role_override_and_other_role_fallback(self):
        result, report = self.invoke(command='takeover', extra=['--worker-model', 'provider/worker'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report['workflow'], 'takeover')
        self.assertEqual(report['model'], 'openai/gpt-6.1-sol')
        self.assert_model_bindings(report, {'worker': 'provider/worker', 'reviewer': report['model']})

    def test_cross_model_selection_still_requires_separate_sessions(self):
        result, report = self.invoke('same_session', extra=['--worker-model', 'provider/worker',
                                                          '--reviewer-model', 'provider/reviewer'])
        self.assertEqual(result.returncode, 1)
        self.assertIn('session is not independent', report['error'])
        self.assert_model_bindings(report, {'worker': 'provider/worker', 'reviewer': 'provider/reviewer'})

    def test_invalid_models_rejected_before_subprocess_or_run_creation(self):
        invalid = ('', 'model-only', '/model', 'provider/', '-provider/model', 'provider/-model',
                   'provider/model name', ' provider/model', 'provider/model\n',
                   'provider/mo\x00del', 'provider/mo\x7fdel', 'provider/model;id',
                   'provider/$(id)', 'provider/model|id', 'provider/`id`', 'provider/"model"')
        for command in ('run', 'takeover'):
            for option in ('--model', '--worker-model', '--reviewer-model'):
                for model in invalid:
                    # NUL cannot be passed through OS argv; exercise its parser directly below.
                    if '\x00' in model:
                        continue
                    with self.subTest(command=command, option=option, model=model):
                        result = subprocess.run([sys.executable, str(RUNTIME), command,
                                                 '--repo', str(self.repo), '--request', 'test',
                                                 '--output-root', str(self.runs), option + '=' + model],
                                                env=self.env, capture_output=True, text=True, timeout=10)
                        self.assertEqual(result.returncode, 2)
                        self.assertIn('provider/model', result.stderr)
        self.assertFalse(self.runs.exists())
        self.assertFalse(self.agent_calls.exists())
        import importlib.util
        import argparse
        spec = importlib.util.spec_from_file_location('runtime', RUNTIME)
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
        with self.assertRaises(argparse.ArgumentTypeError):
            runtime.model_id('provider/mo\x00del')

    def test_fail_closed(self):
        for mode in ('nonzero', 'empty', 'timeout', 'error', 'tool_error', 'false_pass', 'fail', 'same_session', 'no_session', 'malformed'):
            with self.subTest(mode=mode):
                result, report = self.invoke(mode, identity=mode)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(report['state'], 'FAILED')
                self.assertIn('error', report)

    def test_check_failure_prevents_review(self):
        result, report = self.invoke(extra=['--check', f'{sys.executable} -c "raise SystemExit(7)"'])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report['checks'][0]['exit_code'], 7)
        self.assertEqual(report['checks_state'], 'FAILED')
        self.assertEqual(len(report['agents']), 1)

    def test_read_only_review_and_fenced_json(self):
        result, report = self.invoke('fenced', extra=['--mode', 'review'])
        self.assertEqual(result.returncode, 0)
        self.assertEqual([a['role'] for a in report['agents']], ['reviewer'])

    def test_check_timeout_kills_descendants(self):
        marker = self.root / 'orphan-marker'
        command = f'{sys.executable} -c "import time; time.sleep(0.8); open(\'{marker}\', \'w\').write(\'orphan\')"'
        result, report = self.invoke(extra=['--check', command])
        self.assertEqual(result.returncode, 1)
        self.assertIn('timeout', report['checks'][0]['error'])
        time.sleep(0.9)
        self.assertFalse(marker.exists())

    def test_read_only_check_mutation_fails(self):
        result, report = self.invoke(extra=['--mode', 'review', '--check', 'touch changed.txt'])
        self.assertEqual(result.returncode, 1)
        self.assertIn('review/checks changed', report['error'])

    def test_reviewer_mutation_fails(self):
        result, report = self.invoke('mutation')
        self.assertEqual(result.returncode, 1)
        self.assertIn('changed repository', report['error'])

    def test_existing_tracked_and_untracked_content_changes_detected(self):
        for tracked in (True, False):
            with self.subTest(tracked=tracked):
                name = 'tracked.txt' if tracked else 'untracked.txt'
                (self.repo / name).write_text('index content')
                if tracked:
                    subprocess.run(['git', '-C', str(self.repo), 'add', name], check=True)
                (self.repo / name).write_text('baseline')
                self.env['FAKE_TARGET'] = name
                result, report = self.invoke('mutation', identity=name.replace('.', '-'))
                self.assertEqual(result.returncode, 1)
                self.assertEqual(report['baseline']['status'], report['after']['status'])
                self.assertNotEqual(report['baseline']['files_sha256'], report['after']['files_sha256'])

    def test_pass_requires_nonempty_string_evidence_and_string_findings(self):
        invalid = [([], []), ([''], []), (['   '], []), ([{}], []), ([42], []),
                   (['observed'], [{}]), (['observed'], ['']), (['observed'], [42])]
        for index, (evidence, findings) in enumerate(invalid):
            with self.subTest(evidence=evidence, findings=findings):
                self.env['REVIEW_OVERRIDE'] = json.dumps(dict(verdict='PASS', evidence=evidence, findings=findings))
                result, report = self.invoke(identity=f'evidence-{index}')
                self.assertEqual(result.returncode, 1)
                self.assertEqual(report['state'], 'FAILED')

    def test_skipped_checks_explicit_in_report_status_and_handoff(self):
        result, report = self.invoke()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report['checks_executed'], 0)
        self.assertEqual(report['checks_state'], 'SKIPPED')
        self.assertNotIn('CHECKING', [item['state'] for item in report['history']])
        self.assertIn('Checks: SKIPPED; checks_executed=0', (self.runs / 'test/handoff.md').read_text())
        self.assertEqual(self.status()['checks_state'], 'SKIPPED')

    def status(self, identity='test'):
        result = subprocess.run([sys.executable, str(RUNTIME), 'status', '--output-root', str(self.runs),
                                 '--adw-id', identity], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)['runs'][0]

    def capture(self, identity='test'):
        return subprocess.run([sys.executable, str(RUNTIME), 'capture', '--adw-id', identity,
                               '--output-root', str(self.runs)], env=self.env,
                              capture_output=True, text=True, timeout=10)

    def test_capture_private_metadata_receipt_and_idempotency(self):
        self.invoke(extra=['--request', 'SECRET REQUEST AND TRANSCRIPT'])
        self.assertFalse(self.note_calls.exists())
        result = self.capture()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.note_calls.read_text().splitlines()]
        self.assertEqual(len(calls), 1)
        argv = calls[0]
        self.assertEqual(argv[0], 'note')
        self.assertEqual(argv[2:], ['--source', str(self.runs / 'test/report.json'), '--agent', 'opencode-adw'])
        self.assertEqual(argv[1], 'OpenCode ADW: n=1 recorded run. Recorded state: PASSED. Agent invocation count: 2. Recorded check invocation count: 0.')
        self.assertLess(len(argv[1]), 300)
        self.assertNotIn('SECRET', json.dumps(argv))
        captured = self.status()['capture']
        self.assertEqual(captured['state'], 'CAPTURED')
        self.assertEqual(captured['process']['exit_code'], 0)
        self.assertTrue(Path(captured['process']['stdout']).exists())
        self.assertTrue((self.runs / 'test/capture.process.json').exists())
        self.assertEqual(self.capture().returncode, 0)
        self.assertEqual(len(self.note_calls.read_text().splitlines()), 1)

    def test_capture_failure_status_and_explicit_retry(self):
        self.invoke('nonzero')
        self.env['NOTE_EXIT'] = '6'
        result = self.capture()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.status()['state'], 'FAILED')
        self.assertEqual(self.status()['capture']['state'], 'FAILED')
        self.assertEqual(self.status()['capture']['process']['exit_code'], 6)
        self.assertIn('Recorded state: FAILED', self.status()['capture']['summary'])
        self.env['NOTE_EXIT'] = '0'
        self.assertEqual(self.capture().returncode, 0)
        self.assertEqual(self.status()['capture']['state'], 'CAPTURED')
        self.assertEqual(len(self.note_calls.read_text().splitlines()), 2)

    def test_capture_missing_executable_records_failure(self):
        self.invoke()
        (self.bin / 'vault-semantic').unlink()
        # A PATH containing only the fake bin ensures no real note command runs.
        self.env['PATH'] = str(self.bin)
        self.assertEqual(self.capture().returncode, 1)
        self.assertEqual(self.status()['capture']['state'], 'FAILED')
        self.assertIn('error', self.status()['capture']['process'])

    def test_capture_lock_and_unknown_previous_outcome_prevent_duplicate_note(self):
        self.invoke()
        with (self.runs / 'test/capture.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.capture().returncode, 1)
        path = self.runs / 'test/report.json'
        report = json.loads(path.read_text())
        report['capture'] = {'state': 'PUBLISHING'}
        path.write_text(json.dumps(report))
        self.assertEqual(self.capture().returncode, 1)
        self.assertFalse(self.note_calls.exists())

    def test_repository_lock_across_output_roots(self):
        locks = self.root / '.local/share/opencode-adw/locks'
        locks.mkdir(parents=True)
        key = hashlib.sha256(os.fsencode(str(self.repo.resolve()))).hexdigest()
        with (locks / (key + '.lock')).open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result, report = self.invoke()
            self.assertEqual(result.returncode, 1)
            self.assertIn('locked', report['error'])
            self.assertEqual(report['agents'], [])
            child = self.repo / 'subdir'
            child.mkdir()
            result, report = self.invoke(identity='subdir', extra=['--repo', str(child)])
            self.assertEqual(result.returncode, 1)
            self.assertIn('locked', report['error'])

    def test_takeover_bridge_fallback_and_recent_handoff(self):
        self.invoke(identity='prior')
        result, report = self.invoke(command='takeover', extra=['--bridge', str(self.root / 'missing.py')])
        self.assertEqual(result.returncode, 0)
        self.assertIsNotNone(report['bridge']['fallback'])
        self.assertEqual(report['continuity'][0]['state'], 'PASSED')

    def test_takeover_actual_bridge_argument_contract(self):
        bridge = self.root / 'bridge.py'
        bridge.write_text('import json, sys\nassert sys.argv[1:6] == ["brief", "--json", "--limit", "8", "Implement the task"]\nprint(json.dumps({"text":"prior evidence"}))\n')
        result, report = self.invoke(command='takeover', extra=['--bridge', str(bridge)])
        self.assertEqual(result.returncode, 0)
        self.assertIsNone(report['bridge']['fallback'])

    def test_default_bridge_uses_current_home(self):
        bridge = self.root / 'fusion-harness/tools/session-build/session_build.py'
        bridge.parent.mkdir(parents=True)
        bridge.write_text('import json\nprint(json.dumps({"text":"home-relative brief"}))\n')
        result, report = self.invoke(command='takeover')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report['bridge']['process']['command'][1], str(bridge))
        self.assertIsNone(report['bridge']['fallback'])


if __name__ == '__main__':
    unittest.main()
