"""Render source tokens and inject an SDK fixture; spawn only a local fake runtime."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUN = shutil.which('bun')
FAKE = r'''
import json, os, signal, sys, time
from pathlib import Path
args = sys.argv[1:]
Path(os.environ['ARGS_FILE']).write_text(json.dumps(args))
if 'RECEIPT_STDOUT' in os.environ:
    print(os.environ['RECEIPT_STDOUT'])
    sys.exit(0)
if os.environ.get('CANCEL'):
    def stop(*_):
        # Simulates core finally aborting owned native children.
        time.sleep(.15)
        Path(os.environ['ABORT_FILE']).write_text('native children aborted')
        sys.exit(1)
    signal.signal(signal.SIGTERM, stop)
    Path(os.environ['START_FILE']).write_text('started')
    time.sleep(20)
size = int(os.environ.get('SIZE', '0'))
print(json.dumps({'adw_id':'actual-run', 'state':'FAILED' if os.environ.get('FAIL') else 'PASSED',
                  'repo': '/target/repo', 'report': '/private/runs/actual-run/report.json',
                  'question': 'Which repo?' if args[0] == 'route' else None,
                  'team': {'parent_session_id':'ses_real', 'children':[{'session_id':'ses_child'}]},
                  'padding': 'x' * size}))
sys.exit(1 if os.environ.get('FAIL') else 0)
'''
SCHEMA = '''
const Plugin = { define: (definition) => definition };
'''
HARNESS = r'''
import fs from 'node:fs';
const plugin = (await import('./plugin.mjs')).default;
const controller = new AbortController();
let tool;
await plugin.setup({
  location: { directory: '/WRONG/plugin/location' },
  session: { get: async ({ sessionID }) => ({ data: { id: sessionID,
    agent: process.env.AGENT || 'opencode-team', location: { directory: '/parent/project' } } }) },
  tool: { transform: async (edit) => edit({ add: (definition) => { tool = definition; } }) },
});
if (plugin.id !== 'opencode-team' || tool.name !== 'opencode_team' || tool.input.type !== 'object') {
  throw new Error('Invalid V2 registration');
}
const ctx = { sessionID: 'ses_context_real', signal: controller.signal };
if (process.env.PRE_ABORT) controller.abort();
if (process.env.CANCEL) {
  const timer = setInterval(() => {
    if (fs.existsSync(process.env.START_FILE)) { clearInterval(timer); controller.abort(); }
  }, 10);
}
try {
  const result = await tool.execute(JSON.parse(process.env.TOOL_ARGS), ctx);
  console.log(JSON.stringify(result));
} catch (error) { console.log(JSON.stringify({ error: error.message })); }
'''


@unittest.skipUnless(BUN, 'Bun is needed for the injected plugin SDK fixture')
class PluginTests(unittest.TestCase):
    def invoke(self, args, *, env=None):
        import os
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            fake = folder / 'fake.py'
            fake.write_text(FAKE)
            source = (ROOT / 'assets/plugins/opencode-team.js').read_text()
            source = source.replace("import { Plugin } from '@opencode/plugin';", SCHEMA)
            source = source.replace('@RUNTIME_JSON@', json.dumps(str(fake))).replace(
                '@PYTHON_JSON@', json.dumps(sys.executable)).replace(
                '@OPENCODE_JSON@', json.dumps('/explicit/real/opencode'))
            (folder / 'plugin.mjs').write_text(source)
            (folder / 'main.mjs').write_text(HARNESS)
            paths = {name: str(folder / (name + '.json')) for name in (
                'ARGS_FILE', 'ABORT_FILE', 'START_FILE')}
            result = subprocess.run([BUN, str(folder / 'main.mjs')], capture_output=True,
                                    text=True, timeout=12, env={**os.environ, **paths,
                                    'TOOL_ARGS': json.dumps(args), **(env or {})})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            called = json.loads(Path(paths['ARGS_FILE']).read_text()) if Path(paths['ARGS_FILE']).exists() else None
            aborted = Path(paths['ABORT_FILE']).exists()
            return json.loads(result.stdout), called, aborted

    def test_actual_context_default_native_team_and_auto_repo(self):
        result, argv, _ = self.invoke({'task': 'task; $(no shell) --parent-session fake'})
        self.assertEqual(argv[:1], ['run'])
        for flag, expected in [('--parent-session', 'ses_context_real'),
                               ('--parent-directory', '/parent/project'),
                               ('--routing-context', '/parent/project'),
                               ('--mode', 'team'), ('--repo', 'auto')]:
            self.assertEqual(argv[argv.index(flag) + 1], expected)
        self.assertEqual(argv[argv.index('--request') + 1], 'task; $(no shell) --parent-session fake')
        self.assertNotIn('--native-server-url', argv)
        out = json.loads(result['content'])
        self.assertEqual(out['run_id'], 'actual-run')
        self.assertEqual(out['team']['parent_session_id'], 'ses_real')

    def test_modes_models_checks_and_takeover(self):
        for workflow in ('team', 'deep', 'build', 'review', 'takeover'):
            with self.subTest(workflow=workflow):
                _, argv, _ = self.invoke({'task': 'do task', 'workflow': workflow, 'repo': '/target/repo',
                                         'model': 'shared/m', 'models': {'worker': 'p/w', 'reviewer': 'p/r',
                                         'planner': 'p/p', 'testdesigner': 'p/t'},
                                         'checks': ['python test.py', 'node --test'], 'max_repairs': 0})
                self.assertEqual(argv[0], 'takeover' if workflow == 'takeover' else 'run')
                self.assertEqual(argv[argv.index('--mode') + 1], 'build' if workflow == 'takeover' else workflow)
                self.assertEqual(argv[argv.index('--max-repairs') + 1], '0')
                self.assertEqual(argv.count('--check'), 2)
                for role, model in [('worker', 'p/w'), ('reviewer', 'p/r'), ('planner', 'p/p'), ('testdesigner', 'p/t')]:
                    self.assertEqual(argv[argv.index('--' + role + '-model') + 1], model)

    def test_router_rejects_run_but_routes_and_checks_status(self):
        denied, argv, _ = self.invoke({'task': 'recursive'}, env={'AGENT': 'opencode-router'})
        self.assertIn('Router may only', denied['error'])
        self.assertIsNone(argv)
        routed, argv, _ = self.invoke({'action': 'route', 'task': 'choose repo'}, env={'AGENT': 'opencode-router'})
        self.assertEqual(argv[0], 'route')
        self.assertNotIn('--mode', argv)
        self.assertEqual(json.loads(routed['content'])['receipt']['question'], 'Which repo?')
        _, argv, _ = self.invoke({'action': 'status', 'run_id': 'real-id'}, env={'AGENT': 'opencode-router'})
        self.assertEqual(argv[0], 'status')
        self.assertEqual(argv[argv.index('--adw-id') + 1], 'real-id')
        self.assertNotIn('--request', argv)

    def test_task_required_for_run_and_route(self):
        for action in ('run', 'route'):
            result, argv, _ = self.invoke({'action': action})
            self.assertIn('task is required', result['error'])
            self.assertIsNone(argv)

    def test_router_status_argv_contains_only_status_parser_arguments(self):
        for run_id in (None, 'actual-run-id'):
            with self.subTest(run_id=run_id):
                args = {'action': 'status'}
                if run_id is not None:
                    args['run_id'] = run_id
                result, argv, _ = self.invoke(args, env={'AGENT': 'opencode-router'})
                self.assertNotIn('error', result)
                self.assertEqual(argv, ['status'] + (
                    ['--adw-id', run_id] if run_id is not None else []))
                self.assertEqual(json.loads(result['content'])['exit_code'], 0)

    def test_pretty_status_is_parsed_before_compacting_nested_string_array(self):
        status = {'runs': [{'adw_id': 'actual-run', 'state': 'FAILED', 'repo': '/actual/repo',
                           'report': '/private/run/report.json', 'deep': {'actual_tests': 2, 'routing': {
            'paths': ['/project/first', '/project/last']}}}]}
        result, argv, _ = self.invoke({'action': 'status'}, env={
            'AGENT': 'opencode-router', 'RECEIPT_STDOUT': json.dumps(status, indent=2)})
        self.assertEqual(argv, ['status'])
        receipt = json.loads(result['content'])['receipt']
        self.assertEqual(receipt['scope'], 'global_fallback')
        self.assertEqual(receipt['runs'], [{'adw_id': 'actual-run', 'state': 'FAILED',
                         'repo': '/actual/repo', 'report': '/private/run/report.json',
                         'deep': {'actual_tests': 2}}])
        self.assertNotIn('/project/last', result['content'])

    def test_jsonl_selects_last_complete_object_and_ignores_scalar_array_lines(self):
        receipt = {'adw_id': 'last-run', 'state': 'PASSED', 'team': {
            'parent_session_id': 'ses_real', 'children': [{'session_id': 'ses_child'}]}}
        stdout = '\n'.join(['diagnostic text', json.dumps({'adw_id': 'earlier-run'}),
                            json.dumps(receipt), '"scalar path"', '["array path"]',
                            'null', '42', 'false', '{"incomplete":'])
        result, _, _ = self.invoke({'task': 'task'}, env={'RECEIPT_STDOUT': stdout})
        output = json.loads(result['content'])
        self.assertEqual(output['receipt'], receipt)
        self.assertEqual(output['run_id'], 'last-run')
        self.assertEqual(output['team'], receipt['team'])

    def test_plugin_location_and_unsupplied_server_are_never_used_as_parent(self):
        _, argv, _ = self.invoke({'task': 'task'})
        self.assertNotIn('/WRONG/plugin/location', argv)
        self.assertNotIn('--native-server-url', argv)

    def test_receipt_over_64k_is_parsed_then_compacted_and_failure_retains_evidence(self):
        result, _, _ = self.invoke({'task': 'task'}, env={'SIZE': '100000', 'FAIL': '1'})
        output = json.loads(result['content'])
        self.assertNotIn('padding', output['receipt'])
        self.assertEqual(output['receipt']['report'], '/private/runs/actual-run/report.json')
        self.assertEqual(output['receipt']['repo'], '/target/repo')
        self.assertLess(len(result['content']), 2000)
        self.assertEqual(output['exit_code'], 1)
        self.assertEqual(output['state'], 'FAILED')
        self.assertEqual(output['run_id'], 'actual-run')

    def test_routing_catalog_and_team_compaction_preserve_question_and_actual_ids(self):
        candidates = [{'name': 'project-' + str(i), 'selected_repo': '/repo/' + str(i),
                       'canonical_checkout': '/canonical/' + str(i),
                       'paths': ['/private-worktree/' + str(n) for n in range(200)],
                       'aliases': ['PRIVATE_PROMPT'] * 200, 'description': 'PRIVATE_PROMPT'}
                      for i in range(8)]
        candidates[1].pop('selected_repo')
        routing = {'status': 'needs_clarification', 'method': 'semantic', 'selected_repo': None,
                   'question': 'Choose project 0 or project 1?', 'model_resolved': 'actual-jev',
                   'confidence': .42, 'receipt_path': '/private/run/routing.json',
                   'jev': {'model_resolved': 'actual-jev', 'confidence': .42, 'prompt': 'PRIVATE_PROMPT'},
                   'candidates': candidates}
        team = {'parent_session_id': 'ses_context_real', 'server_url': 'http://127.0.0.1:1',
                'children': [{'role': 'reviewer', 'label': 'consult-focus', 'session_id': 'ses_actual_child',
                              'parent_id': 'ses_context_real', 'model': 'provider/actual-model',
                              'state': 'failed', 'execution': 'native', 'prompt': 'PRIVATE_PROMPT'}]}
        receipt = {'state': 'FAILED', 'adw_id': 'actual-run', 'repo': None,
                   'report': '/private/run/report.json', 'routing': routing, 'team': team,
                   'prompt': 'PRIVATE_PROMPT', 'generated_tests': 'PRIVATE_PROMPT' * 1000}
        result, _, _ = self.invoke({'action': 'route', 'task': 'route'}, env={
            'RECEIPT_STDOUT': json.dumps(receipt)})
        output = json.loads(result['content'])
        compact = output['receipt']
        self.assertEqual(output['state'], 'FAILED')
        self.assertEqual(compact['routing']['question'], routing['question'])
        self.assertEqual(compact['routing']['model_resolved'], 'actual-jev')
        self.assertEqual(compact['routing']['confidence'], .42)
        self.assertEqual(compact['routing']['candidates'], [
            {'name': 'project-0', 'path': '/repo/0'},
            {'name': 'project-1', 'path': '/canonical/1'},
            {'name': 'project-2', 'path': '/repo/2'}])
        self.assertEqual(output['team']['parent_session_id'], 'ses_context_real')
        self.assertEqual(output['team']['children'][0], {k: v for k, v in team['children'][0].items()
                                                        if k != 'prompt'})
        self.assertEqual(compact['report'], '/private/run/report.json')
        self.assertNotIn('PRIVATE_PROMPT', json.dumps(result))
        self.assertNotIn('private-worktree', json.dumps(result))
        self.assertNotIn('aliases', json.dumps(result))
        self.assertLess(len(result['content']), 3000)

    def test_status_prefers_current_session_latest_ten_and_retains_failures_and_deep_metadata(self):
        rows = []
        for i in range(14):
            rows.append({'adw_id': 'run-' + str(i), 'state': 'FAILED' if i == 11 else 'PASSED',
                         'started_at': i, 'repo': '/actual/repo', 'output_dir': '/private/run-' + str(i),
                         'team': {'parent_session_id': 'ses_context_real', 'children': []},
                         'models': {'worker': 'actual/worker', 'reviewer': 'actual/reviewer'},
                         'checks_state': 'FAILED' if i == 11 else 'PASSED', 'checks_executed': 2,
                         'deep': {'actual_tests': 4, 'repairs_performed': 1, 'max_repairs': 2,
                                  'test_history': [{'traceback': 'PRIVATE_PROMPT'}],
                                  'plan': {'prompt': 'PRIVATE_PROMPT'},
                                  'jev_decisions': [{'recommendation': 'repair', 'state': 'PRIVATE_PROMPT'},
                                                    {'recommendation': 'stop', 'focus': 'correctness',
                                                     'confidence': .7, 'model_resolved': 'actual-jev',
                                                     'state': {'request': 'PRIVATE_PROMPT'}}]}})
        rows.append({'adw_id': 'other-session-newest', 'state': 'FAILED', 'started_at': 100,
                     'team': {'parent_session_id': 'ses_other'}})
        result, _, _ = self.invoke({'action': 'status'}, env={
            'RECEIPT_STDOUT': json.dumps({'runs': rows}, indent=2)})
        receipt = json.loads(result['content'])['receipt']
        self.assertEqual(receipt['scope'], 'current_session')
        self.assertEqual([r['adw_id'] for r in receipt['runs']], ['run-' + str(i) for i in range(13, 3, -1)])
        failed = next(r for r in receipt['runs'] if r['adw_id'] == 'run-11')
        self.assertEqual(failed['state'], 'FAILED')
        self.assertEqual(failed['checks_state'], 'FAILED')
        self.assertEqual(failed['models'], rows[11]['models'])
        self.assertEqual(failed['report'], '/private/run-11/report.json')
        self.assertEqual(failed['deep'], {'actual_tests': 4, 'repairs_performed': 1, 'max_repairs': 2,
                         'jev_last_advice': {'recommendation': 'stop', 'focus': 'correctness',
                                            'confidence': .7, 'model_resolved': 'actual-jev'}})
        self.assertNotIn('PRIVATE_PROMPT', json.dumps(result))
        self.assertNotIn('other-session-newest', json.dumps(result))

    def test_status_global_fallback_is_labeled_and_explicit_run_does_not_filter_by_parent(self):
        rows = [{'adw_id': 'old-failure', 'state': 'FAILED', 'started_at': 1,
                 'report': '/private/old/report.json', 'team': {'parent_session_id': 'ses_other'}},
                {'adw_id': 'new-run', 'state': 'PASSED', 'started_at': 2}]
        result, _, _ = self.invoke({'action': 'status'}, env={'RECEIPT_STDOUT': json.dumps({'runs': rows})})
        receipt = json.loads(result['content'])['receipt']
        self.assertEqual(receipt['scope'], 'global_fallback')
        self.assertEqual([r['adw_id'] for r in receipt['runs']], ['new-run', 'old-failure'])
        self.assertEqual(receipt['runs'][1]['state'], 'FAILED')
        result, _, _ = self.invoke({'action': 'status', 'run_id': 'old-failure'}, env={
            'RECEIPT_STDOUT': json.dumps({'runs': [rows[0]]})})
        receipt = json.loads(result['content'])['receipt']
        self.assertEqual(receipt['scope'], 'run')
        self.assertEqual(receipt['runs'][0]['adw_id'], 'old-failure')

    def test_output_limit_is_explicit_not_partial_success(self):
        result, _, _ = self.invoke({'task': 'task'}, env={'SIZE': '1100000'})
        output = json.loads(result['content'])
        self.assertEqual(output['state'], 'OUTPUT_LIMIT')
        self.assertIsNone(output['receipt'])

    def test_empty_malformed_and_wrong_action_receipts_never_succeed(self):
        for action, payload in [('run', '{}'), ('run', 'not json'),
                                ('status', '{}'), ('status', '{"runs":[42]}')]:
            with self.subTest(action=action, payload=payload):
                result, _, _ = self.invoke({'action': action, 'task': 'task'}, env={'RECEIPT_STDOUT': payload})
                output = json.loads(result['content'])
                self.assertEqual(output['state'], 'FAILED')
                self.assertIsNone(output['receipt'])

    def test_cancellation_grace_allows_core_abort_and_preabort_never_spawns(self):
        result, _, aborted = self.invoke({'task': 'task'}, env={'CANCEL': '1'})
        self.assertTrue(aborted)
        self.assertEqual(json.loads(result['content'])['state'], 'CANCELLED')
        result, argv, _ = self.invoke({'task': 'task'}, env={'PRE_ABORT': '1'})
        self.assertIsNone(argv)
        self.assertIn('Cancelled', result['content'])


if __name__ == '__main__':
    unittest.main()
