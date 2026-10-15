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
import unittest

RUNTIME = Path(__file__).resolve().parents[1] / 'runtime.py'
FAKE = '''#!/usr/bin/env python3
import json, os, sys, time
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
        self.env = dict(os.environ, HOME=str(self.root), PATH=str(self.bin) + os.pathsep + os.environ['PATH'])
        self.env['NOTE_CALLS'] = str(self.note_calls)
        self.runs = self.root / 'runs'

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
