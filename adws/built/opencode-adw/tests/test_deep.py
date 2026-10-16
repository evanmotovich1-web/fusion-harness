"""Offline integration: fake native role sessions/Jev, real Python/Node/check processes."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import types
import unittest
from unittest import mock

import test_runtime

TOOLKIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLKIT))
spec = importlib.util.spec_from_file_location('deep_test_runtime', TOOLKIT / 'runtime.py')
runtime = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runtime
spec.loader.exec_module(runtime)

PYTHON = '''import os, unittest
from pathlib import Path
class EdgeCases(unittest.TestCase):
    def test_value(self):
        self.assertEqual((Path(os.environ['OPENCODE_ADW_REPO']) / 'value.txt').read_text(), 'good')
    def test_edge(self):
        self.assertTrue(Path(os.environ['OPENCODE_ADW_REPO']).is_dir())
'''
NODE = '''import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
test('public value', () => assert.equal(fs.readFileSync(path.join(process.env.OPENCODE_ADW_REPO, 'value.txt'), 'utf8'), 'good'));
'''


def invalid_python_receipts():
    import generated_tests
    valid = dict(generated_tests.python_record(), testsRun=1)
    cases = {'list': [], 'null': None, 'empty_object': {}}
    for name, values in {'testsRun': ('1', True, -1), 'errors': (None, {}),
                         'failures': (None, ''), 'skipped': (None, {}),
                         'expected_failures': ('0', True, -1),
                         'unexpected_successes': ('0', False, -1),
                         'load_error': (False, [])}.items():
        for index, value in enumerate(values):
            cases[f'{name}-{index}'] = dict(valid, **{name: value})
    for name in valid:
        missing = valid.copy()
        del missing[name]
        cases['missing-' + name] = missing
    return cases


def receipt_executor(payload, fallback=None):
    """Inject only the generated child receipt; native role processes stay real/fake CLI."""
    def execute(argv, cwd, timeout, prefix, **kwargs):
        if not (isinstance(argv, list) and len(argv) > 1 and Path(argv[1]).name == 'generated_tests.py'):
            if fallback is None:
                raise AssertionError('Unexpected process')
            return fallback(argv, cwd, timeout, prefix, **kwargs)
        Path(argv[-1]).write_text(json.dumps(payload))
        prefix.with_suffix('.stdout').write_text('injected generated-test receipt\n')
        prefix.with_suffix('.stderr').write_text('')
        process = {'command': argv, 'exit_code': 0, 'stdout': str(prefix.with_suffix('.stdout')),
                   'stderr': str(prefix.with_suffix('.stderr'))}
        runtime.write_json(prefix.with_suffix('.process.json'), process)
        return process
    return execute


FAKE = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
role = sys.argv[sys.argv.index('--agent') + 1].removeprefix('opencode-')
prompt = sys.argv[-1]
readiness = 'PRE-BUILD READINESS assessment' in prompt
consulting_decision = 'Independent completion/repair assessment' in prompt
log = Path(os.environ['AGENT_CALLS'])
prior = [json.loads(s) for s in log.read_text().splitlines()] if log.exists() else []
attempt = sum(1 for p in prior if p['role'] == role)
with log.open('a') as f: f.write(json.dumps({'role': role, 'argv': sys.argv[1:]}) + '\n')
mode = os.environ.get('DEEP_FAKE_MODE', '')
sid = 'ses_' + str(len(prior)) if mode != 'same_session' else 'ses_shared'
if mode == 'consult_same_session' and (readiness or consulting_decision): sid = 'ses_0'
def emit(kind, part=None, **kw):
    print(json.dumps(dict(type=kind, sessionID=sid, part=part or {}, **kw)))
if mode == 'api_error' and role == 'worker':
    emit('error', error={'message': 'raw API error'})
if mode == 'tool_error' and role == 'worker':
    emit('tool_use', {'type': 'tool', 'state': {'status': 'error'}})
if mode == role + '_mutation': Path('value.txt').write_text('mutated')
if (mode == 'focus_consult_mutation' and readiness) or (mode == 'decision_consult_mutation' and consulting_decision):
    Path('value.txt').write_text('mutated by consultant')
if mode == 'consult_tamper' and (readiness or consulting_decision):
    target = Path(os.environ['RUN_FOLDER']) / 'plan.json'
    target.write_text('changed')
emit('text', {'text': 'Intermediate observations are not the final JSON.'})
if role == 'planner':
    value = {'requirements': ['value must be good'], 'plan': ['Fix value.txt'], 'risks': ['bad value']}
elif role == 'testdesigner':
    value = json.loads(os.environ['DESIGN'])
elif role == 'worker':
    if mode == 'future_python': Path('feature.py').write_text("def value(): return 'good'\n")
    if mode == 'future_node': Path('feature.mjs').write_text("export const value = () => 'good';\n")
    if mode not in ('no_improvement', 'false_green', 'consult_false_pass') and not (mode == 'repair' and attempt == 0):
        Path('value.txt').write_text('good')
    if mode in ('tamper', 'tamper_cases'):
        folder = Path(os.environ['RUN_FOLDER'])
        target = folder / ('testdesign.json' if mode == 'tamper_cases' else 'generated.py')
        target.chmod(0o600)
        target.write_text('changed')
    value = 'implemented'
else:
    fail = Path('value.txt').read_text() != 'good' or (mode == 'review_fail_once' and attempt == 0)
    if mode == 'false_green': fail = False
    if readiness: fail = mode == 'readiness_fail'
    if mode == 'consult_fail' and consulting_decision: fail = True
    if mode == 'consult_false_pass' and consulting_decision: fail = False
    if mode == 'empty_findings': fail = True
    value = {'verdict': 'FAIL' if fail else 'PASS', 'findings': ['fix value'] if fail and mode != 'empty_findings' else [], 'evidence': ['inspected actual file']}
if mode == 'schema_error' and role == 'planner': value = {'plan': []}
emit('text', {'text': json.dumps(value) if isinstance(value, dict) else value})
'''


class DeepTests(unittest.TestCase):
    setUp = test_runtime.RuntimeTests.setUp

    @staticmethod
    def advice(recommendation, confidence=0.9):
        uncertain = confidence < 0.5 or recommendation == 'other'
        return {'recommendation': recommendation, 'focus': 'general', 'confidence': confidence,
                'probabilities': {recommendation: 0.52}, 'route': 'consult' if uncertain else 'advice',
                'uncertain': uncertain, 'confidence_floor': 0.5}

    def invoke(self, mode='', *, code=PYTHON, format='python_unittest', extra=(), decisions=None):
        (self.repo / '.gitignore').write_text('__pycache__/\n*.pyc\n')
        (self.repo / 'value.txt').write_text('bad')
        (self.bin / 'opencode').write_text(FAKE)
        self.agent_calls.unlink(missing_ok=True)
        self.runs.mkdir(exist_ok=True)
        identity = 'deep-' + str(len(list(self.runs.iterdir())))
        env = dict(self.env, DEEP_FAKE_MODE=mode,
                   DESIGN=json.dumps({'cases': ['value behavior', 'empty edge'], 'format': format, 'code': code}),
                   RUN_FOLDER=str(self.runs / identity))
        calls = []
        def decide(state, **kwargs):
            calls.append((state, kwargs))
            if callable(decisions):
                return decisions(state, kwargs)
            if state['phase'] == 'focus': choice = 'build'
            elif decisions: choice = decisions[min(len(calls) - 2, len(decisions) - 1)]
            else: choice = 'finish' if state['checks_passed'] and state['review_verdict'] == 'PASS' else 'repair'
            self.assertEqual(kwargs['receipt_dir'].name, 'jev')
            self.assertEqual(kwargs['budget_s'], 10)
            kwargs['receipt_dir'].mkdir(exist_ok=True)
            path = kwargs['receipt_dir'] / (kwargs['label'] + '.json')
            path.write_text(json.dumps({'recommendation': choice}))
            return {'recommendation': choice, 'focus': 'general' if choice in ('finish', 'stop') else 'correctness', 'confidence': 0.9,
                    'probabilities': {choice: 0.9}, 'model_requested': 'jev', 'model_resolved': 'jev-real',
                    'input_tokens': 10, 'output_tokens': 2, 'elapsed_ms': 1, 'receipt_path': str(path)}
        bridge = types.SimpleNamespace(decide=decide, status=lambda: {'configured': True, 'model': 'jev', 'reason': None})
        with mock.patch.dict(os.environ, env), mock.patch.dict(sys.modules, {'jev_bridge': bridge}), contextlib.redirect_stdout(io.StringIO()):
            exit_code = runtime.main(['run', '--repo', str(self.repo), '--request', 'make value good',
                                      '--output-root', str(self.runs), '--adw-id', identity,
                                      '--timeout', '3', '--mode', 'deep', *extra])
        report = json.loads((self.runs / identity / 'report.json').read_text())
        return exit_code, report, calls

    def test_real_red_to_green_and_role_models_sessions_and_outputs(self):
        code, report, calls = self.invoke(extra=['--model', 'p/shared', '--planner-model', 'p/plan',
                                                '--testdesigner-model', 'p/test'])
        self.assertEqual(code, 0, report.get('error'))
        deep = report['deep']
        self.assertFalse(deep['before_tests']['passed'])
        self.assertTrue(deep['after_tests']['passed'])
        self.assertEqual(deep['actual_tests'], 2)
        self.assertEqual(deep['before_tests']['checks'][0]['result']['testsRun'], 2)
        self.assertEqual(len(deep['before_tests']['checks'][0]['result']['failures']), 1)
        self.assertEqual(report['models'], {'planner': 'p/plan', 'testdesigner': 'p/test', 'worker': 'p/shared', 'reviewer': 'p/shared'})
        self.assertEqual([a['label'] for a in report['agents']], ['planner', 'testdesigner', 'worker', 'reviewer'])
        self.assertEqual(len(set(a['session_ids'][0] for a in report['agents'])), 4)
        self.assertNotEqual(report['agents'][0]['text'], report['agents'][0]['last_text'])
        self.assertEqual(len(calls), 2)
        self.assertTrue(deep['test_hash_intact'])
        self.assertFalse(self.note_calls.exists())

    def test_failed_check_still_gets_review_then_concrete_repair(self):
        code, report, calls = self.invoke('repair')
        self.assertEqual(code, 0, report.get('error'))
        deep = report['deep']
        self.assertEqual(deep['repairs_performed'], 1)
        self.assertFalse(deep['attempts'][0]['tests']['passed'])
        self.assertEqual(deep['attempts'][0]['review']['verdict'], 'FAIL')
        self.assertTrue(deep['attempts'][1]['tests']['passed'])
        labels = [a['label'] for a in report['agents']]
        self.assertEqual(labels[-2:], ['worker-repair1', 'reviewer-repair1'])
        self.assertEqual(len(set(a['session_ids'][0] for a in report['agents'])), 6)
        repair_prompt = report['agents'][-2]['process']['command'][-1]
        self.assertIn('AssertionError', repair_prompt)
        review_prompt = report['agents'][3]['process']['command'][-1]
        self.assertIn('AssertionError', review_prompt)
        self.assertNotEqual(deep['attempts'][0]['tests']['after'], deep['attempts'][1]['tests']['after'])
        self.assertTrue(all(Path(report['output_dir'], label + '.events.jsonl').exists() for label in labels))

    def test_review_fail_can_repair_even_when_checks_pass(self):
        code, report, _ = self.invoke('review_fail_once')
        self.assertEqual(code, 0, report.get('error'))
        self.assertEqual(report['deep']['repairs_performed'], 1)

    def test_malicious_jev_finish_cannot_override_bad_work(self):
        code, report, _ = self.invoke('false_green', decisions=['finish'])
        self.assertEqual(code, 1)
        self.assertFalse(report['deep']['after_tests']['passed'])
        self.assertEqual(report['agents'][-1]['review']['verdict'], 'PASS')
        self.assertEqual(report['deep']['repairs_performed'], 0)

    def test_jev_finish_cannot_override_reviewer_failure(self):
        code, report, _ = self.invoke('review_fail_once', decisions=['finish'])
        self.assertEqual(code, 1)
        self.assertTrue(report['deep']['after_tests']['passed'])
        self.assertEqual(report['agents'][-1]['review']['verdict'], 'FAIL')
        self.assertEqual(len(report['agents']), 4)

    def test_budget_exhausted_and_explicit_zero_two(self):
        for budget in (0, 1, 2):
            with self.subTest(budget=budget):
                code, report, _ = self.invoke('no_improvement', extra=['--max-repairs', str(budget)])
                self.assertEqual(code, 1)
                self.assertEqual(report['deep']['repairs_performed'], budget)
                self.assertEqual(len(report['agents']), 4 + 2 * budget)
                self.assertEqual(report['deep']['budget']['remaining_repairs'], 0)

    def test_empty_syntax_import_and_discovery_broken_suites_rejected(self):
        for source in ('import unittest\n', 'not python!!', 'import absent_project_module',
                       'def load_tests(loader, tests, pattern): raise ValueError("broken")'):
            with self.subTest(source=source):
                code, report, calls = self.invoke(code=source)
                self.assertEqual(code, 1)
                self.assertIn('broken or detected tests=0', report['error'])
                self.assertEqual(len(report['agents']), 2)
                self.assertEqual(calls, [])

    def test_skipped_tests_never_satisfy_completion(self):
        source = 'import unittest\n@unittest.skip("skip")\nclass T(unittest.TestCase):\n def test_x(self): pass\n'
        code, report, _ = self.invoke(code=source)
        self.assertEqual(code, 1)
        self.assertFalse(report['deep']['after_tests']['passed'])

    def test_python_project_sys_path_and_cache_ignored(self):
        (self.repo / 'example.py').write_text('VALUE = 42\n')
        source = 'import unittest, example\nclass T(unittest.TestCase):\n def test_value(self): self.assertEqual(example.VALUE, 42)\n'
        code, report, _ = self.invoke(code=source)
        self.assertEqual(code, 0, report.get('error'))
        self.assertEqual(report['deep']['actual_tests'], 1)

    def test_future_annotations_dataclass_helper_loads_and_executes(self):
        source = '''from __future__ import annotations
from dataclasses import dataclass
from typing import ClassVar
import unittest
@dataclass
class Expected:
    value: str
    label: ClassVar[str] = 'public result'
class T(unittest.TestCase):
    def test_helper(self):
        self.assertEqual(Expected('good').value, 'good')
        self.assertEqual(Expected.label, 'public result')
'''
        code, report, _ = self.invoke(code=source)
        self.assertEqual(code, 0, report.get('error'))
        for batch in (report['deep']['before_tests'], report['deep']['after_tests']):
            self.assertEqual(batch['checks'][0]['result']['testsRun'], 1)
            self.assertIsNone(batch['checks'][0]['result']['load_error'])

    def test_python_suite_restores_module_registration_after_success_or_load_error(self):
        import generated_tests
        source = self.root / 'external.py'
        receipt = self.root / 'unittest.json'
        previous = types.ModuleType('prior_frozen_tests')
        for prior in (None, previous):
            for code, expected in (('import unittest\nclass T(unittest.TestCase):\n def test_ok(self): pass\n', 0),
                                   ('raise ValueError("load failed")', 1)):
                with self.subTest(prior=prior, expected=expected), mock.patch.dict(sys.modules), \
                        mock.patch.dict(os.environ), mock.patch.object(sys, 'path', list(sys.path)), \
                        mock.patch.object(sys, 'dont_write_bytecode', sys.dont_write_bytecode), \
                        contextlib.redirect_stderr(io.StringIO()):
                    if prior is None:
                        sys.modules.pop('adw_frozen_tests', None)
                    else:
                        sys.modules['adw_frozen_tests'] = prior
                    source.write_text(code)
                    self.assertEqual(generated_tests.python_suite(source, self.repo, receipt), expected)
                    if prior is None:
                        self.assertNotIn('adw_frozen_tests', sys.modules)
                    else:
                        self.assertIs(sys.modules['adw_frozen_tests'], prior)

    def test_malformed_python_receipt_schema_rejected_without_arithmetic_errors(self):
        import generated_tests
        args = types.SimpleNamespace(repo=self.repo, timeout=3)
        suite = {'format': 'python_unittest', 'path': str(self.root / 'generated.py')}
        for name, payload in invalid_python_receipts().items():
            with self.subTest(receipt=name):
                rt = types.SimpleNamespace(execute=receipt_executor(payload))
                result = generated_tests.execute_suite(rt, args, suite, self.root, 'schema')
                self.assertFalse(result['valid_suite'])
                self.assertFalse(result['passed'])
                self.assertEqual(result['actual_tests'], 0)
                self.assertIn('Invalid unittest receipt:', result['result']['load_error'])

    def test_malformed_python_receipts_produce_terminal_failed_runtime_reports(self):
        original_execute = runtime.execute
        for name, payload in invalid_python_receipts().items():
            with self.subTest(receipt=name), mock.patch.object(
                    runtime, 'execute', side_effect=receipt_executor(payload, original_execute)):
                code, report, calls = self.invoke()
                self.assertEqual(code, 1)
                self.assertEqual(report['state'], 'FAILED')
                self.assertTrue(report['finished_at'])
                self.assertIn('broken or detected tests=0', report['error'])
                self.assertEqual(report['checks_state'], 'FAILED')
                self.assertEqual(report['checks_executed'], 1)
                self.assertEqual(report['deep']['actual_tests'], 0)
                self.assertIn('Invalid unittest receipt:', report['checks'][0]['result']['load_error'])
                self.assertEqual(len(report['agents']), 2)
                self.assertEqual(calls, [])
                self.assertIn('State: FAILED', (Path(report['output_dir']) / 'handoff.md').read_text())

    def test_python_receipt_failures_cannot_pass_even_with_child_exit_zero(self):
        import generated_tests
        args = types.SimpleNamespace(repo=self.repo, timeout=3)
        suite = {'format': 'python_unittest', 'path': str(self.root / 'generated.py')}
        for field, value in (('errors', [{'test': 'case', 'traceback': 'error'}]),
                             ('failures', [{'test': 'case', 'traceback': 'failure'}]),
                             ('unexpected_successes', 1)):
            with self.subTest(field=field):
                record = dict(generated_tests.python_record(), testsRun=1, **{field: value})
                rt = types.SimpleNamespace(execute=receipt_executor(record))
                result = generated_tests.execute_suite(rt, args, suite, self.root, 'failure')
                self.assertTrue(result['valid_suite'])
                self.assertFalse(result['passed'])

    def test_missing_future_python_api_is_counted_red_then_green(self):
        source = '''import unittest
class T(unittest.TestCase):
    def test_future_api(self):
        from feature import value
        self.assertEqual(value(), 'good')
'''
        code, report, _ = self.invoke('future_python', code=source)
        self.assertEqual(code, 0, report.get('error'))
        baseline = report['deep']['before_tests']['checks'][0]
        self.assertEqual(baseline['actual_tests'], 1)
        self.assertTrue(baseline['valid_suite'])
        self.assertFalse(baseline['passed'])
        self.assertIsNone(baseline['result']['load_error'])
        self.assertIn('ModuleNotFoundError', baseline['result']['errors'][0]['traceback'])
        self.assertTrue(report['deep']['after_tests']['passed'])
        prompt = report['agents'][1]['process']['command'][-1]
        self.assertIn('INSIDE Python test methods', prompt)
        self.assertIn('INSIDE Node test callbacks', prompt)

    @unittest.skipUnless(shutil.which('node'), 'Node not installed')
    def test_node_native_tap_red_to_green(self):
        code, report, _ = self.invoke(code=NODE, format='node_test')
        self.assertEqual(code, 0, report.get('error'))
        self.assertEqual(report['deep']['actual_tests'], 1)
        self.assertFalse(report['deep']['before_tests']['passed'])
        self.assertEqual(report['deep']['after_tests']['checks'][0]['result']['pass'], 1)
        self.assertEqual(Path(report['deep']['suite']['path']).suffix, '.mjs')

    @unittest.skipUnless(shutil.which('node'), 'Node not installed')
    def test_missing_future_node_api_is_counted_red_then_green(self):
        source = '''import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
test('future API', async () => {
    const {value} = await import(pathToFileURL(path.join(process.env.OPENCODE_ADW_REPO, 'feature.mjs')).href);
    assert.equal(value(), 'good');
});
'''
        code, report, _ = self.invoke('future_node', code=source, format='node_test')
        self.assertEqual(code, 0, report.get('error'))
        baseline = report['deep']['before_tests']['checks'][0]
        self.assertEqual(baseline['actual_tests'], 1)
        self.assertTrue(baseline['valid_suite'])
        self.assertFalse(baseline['passed'])
        self.assertEqual(baseline['result']['fail'], 1)
        self.assertIn('ERR_MODULE_NOT_FOUND', baseline['output']['stdout'])
        self.assertTrue(report['deep']['after_tests']['passed'])

    @unittest.skipUnless(shutil.which('node'), 'Node not installed')
    def test_node_empty_and_broken_rejected(self):
        for source in ('', 'syntax!! invalid', 'import "missing-adw-dependency";'):
            with self.subTest(source=source):
                code, report, _ = self.invoke(code=source, format='node_test')
                self.assertEqual(code, 1)
                self.assertEqual(len(report['agents']), 2)

    def test_checklist_requires_and_executes_operator_check_without_fake_counts(self):
        code, report, _ = self.invoke(format='checklist', code='')
        self.assertEqual(code, 1)
        self.assertIn('explicit --check', report['error'])
        code, report, _ = self.invoke(format='checklist', code='', extra=['--check', 'test "$(cat value.txt)" = good'])
        self.assertEqual(code, 0, report.get('error'))
        self.assertEqual(report['deep']['actual_tests'], 0)
        self.assertIsNone(report['deep']['after_tests']['checks'][0]['actual_tests'])
        self.assertEqual(report['deep']['after_tests']['checks'][0]['kind'], 'operator')

    def test_all_operator_checks_execute_after_failure(self):
        code, report, _ = self.invoke(extra=['--check', 'exit 3', '--check', 'printf second'])
        self.assertEqual(code, 1)
        self.assertEqual(len(report['deep']['after_tests']['checks']), 3)
        self.assertIn('second', report['deep']['after_tests']['checks'][2]['output']['stdout'])

    def test_readonly_mutations_all_roles(self):
        for role in ('planner', 'testdesigner', 'reviewer'):
            with self.subTest(role=role):
                code, report, _ = self.invoke(role + '_mutation')
                self.assertEqual(code, 1)
                self.assertIn('Read-only ' + role, report['error'])
                self.assertNotEqual(report['deep']['readonly_snapshots'][-1]['before'], report['deep']['readonly_snapshots'][-1]['after'])

    def test_generated_test_source_mutation_detected_before_builder(self):
        source = PYTHON.replace("self.assertTrue(Path(os.environ['OPENCODE_ADW_REPO']).is_dir())",
                                "(Path(os.environ['OPENCODE_ADW_REPO']) / 'value.txt').write_text('oops')")
        code, report, _ = self.invoke(code=source)
        self.assertEqual(code, 1)
        self.assertIn('changed repository source', report['error'])
        self.assertEqual(len(report['agents']), 2)

    def test_operator_source_mutation_detected(self):
        code, report, _ = self.invoke(extra=['--check', 'touch unexpected.txt'])
        self.assertEqual(code, 1)
        self.assertIn('changed repository source', report['error'])

    def test_frozen_code_and_cases_tamper_fatal(self):
        for mode in ('tamper', 'tamper_cases'):
            with self.subTest(mode=mode):
                code, report, _ = self.invoke(mode)
                self.assertEqual(code, 1)
                self.assertIn('hash changed', report['error'])
                self.assertEqual(len(report['agents']), 3)

    def test_native_api_tool_schema_and_session_failures_fatal(self):
        for mode in ('api_error', 'tool_error', 'schema_error', 'same_session'):
            with self.subTest(mode=mode):
                code, report, calls = self.invoke(mode)
                self.assertEqual(code, 1)
                self.assertEqual(report['deep']['repairs_performed'], 0)
                self.assertLessEqual(len(calls), 1)

    def test_jev_unavailable_explicit_failed_no_build(self):
        def unavailable(state, kwargs): raise RuntimeError('unavailable client')
        code, report, _ = self.invoke(decisions=unavailable)
        self.assertEqual(code, 1)
        self.assertIn('Jev unavailable', report['error'])
        self.assertEqual(len(report['agents']), 2)
        self.assertEqual(report['deep']['jev_decisions'][0]['error_type'], 'RuntimeError')

    def test_jev_uncertain_unknown_or_stop_not_ignored(self):
        for recommendation, confidence in (('build', 0.2), ('other', 0.9), ('stop', 0.9), ('nonsense', 1)):
            with self.subTest(recommendation=recommendation, confidence=confidence):
                def decision(state, kwargs):
                    if state['phase'] == 'decision':
                        return self.advice('finish')
                    return self.advice(recommendation, confidence)
                code, report, _ = self.invoke(decisions=decision)
                if recommendation in ('other', 'build'):
                    self.assertEqual(code, 0, report.get('error'))
                    self.assertEqual(report['deep']['consultations'][0]['effective_action'], 'build')
                    self.assertEqual(report['deep']['jev_decisions'][0]['recommendation'], recommendation)
                    self.assertEqual(report['deep']['jev_decisions'][0]['confidence'], confidence)
                else:
                    self.assertEqual(code, 1)
                    self.assertEqual(len(report['agents']), 2)

    def test_jev_stop_on_complete_fails_closed_no_pointless_builder(self):
        code, report, _ = self.invoke(decisions=['stop'])
        self.assertEqual(code, 1)
        self.assertTrue(report['deep']['after_tests']['passed'])
        self.assertEqual(len(report['agents']), 4)

    def test_uncertain_focus_readiness_pass_allows_build_without_rewriting_advice(self):
        def decide(state, kw):
            return self.advice('stop', 0.28) if state['phase'] == 'focus' else self.advice('finish')
        code, report, calls = self.invoke(decisions=decide, extra=['--reviewer-model', 'p/readiness'])
        self.assertEqual(code, 0, report.get('error'))
        deep = report['deep']
        self.assertEqual(len(deep['consultations']), 1)
        consultation = deep['consultations'][0]
        self.assertEqual(consultation['phase'], 'focus')
        self.assertEqual(consultation['label'], 'focus-reviewer')
        self.assertEqual(consultation['reason'], 'jev_uncertain')
        self.assertEqual(consultation['source_decision_label'], 'jev-focus')
        self.assertEqual(consultation['effective_action'], 'build')
        self.assertEqual(consultation['model'], 'p/readiness')
        self.assertEqual(consultation['review']['verdict'], 'PASS')
        raw = deep['jev_decisions'][0]
        self.assertEqual((raw['recommendation'], raw['confidence'], raw['probabilities']), ('stop', 0.28, {'stop': 0.52}))
        self.assertEqual(raw['route'], 'consult')
        self.assertTrue(raw['uncertain'])
        labels = [a['label'] for a in report['agents']]
        self.assertEqual(labels, ['planner', 'testdesigner', 'focus-reviewer', 'worker', 'reviewer'])
        prompt = report['agents'][2]['process']['command'][-1]
        self.assertIn('NOT a completed-implementation review', prompt)
        self.assertIn('are EXPECTED', prompt)
        self.assertIn('AssertionError', prompt)
        self.assertEqual(len(calls), 2)

    def test_uncertain_focus_readiness_fail_stops_before_any_builder(self):
        code, report, calls = self.invoke('readiness_fail', decisions=lambda s, kw: self.advice('other', 0.8))
        self.assertEqual(code, 1)
        self.assertIn('Pre-build readiness consultation FAIL', report['error'])
        self.assertEqual(report['baseline'], report['after'])
        self.assertEqual([a['label'] for a in report['agents']], ['planner', 'testdesigner', 'focus-reviewer'])
        self.assertEqual(report['deep']['consultations'][0]['effective_action'], 'stop')
        self.assertEqual(len(calls), 1)

    def test_uncertain_decision_consultation_pass_can_finish_with_all_hard_gates(self):
        def decide(state, kw):
            return self.advice('build') if state['phase'] == 'focus' else self.advice('stop', 0.28)
        code, report, calls = self.invoke(decisions=decide)
        self.assertEqual(code, 0, report.get('error'))
        entry = report['deep']['attempts'][0]
        self.assertEqual(entry['review']['verdict'], 'PASS')
        self.assertTrue(entry['tests']['passed'])
        self.assertTrue(report['deep']['test_hash_intact'])
        self.assertEqual(entry['jev']['recommendation'], 'stop')
        self.assertEqual(entry['jev']['confidence'], 0.28)
        self.assertEqual(entry['effective_action'], 'finish_after_consultation')
        self.assertEqual(entry['consultation']['label'], 'decision-reviewer')
        prompt = report['agents'][-1]['process']['command'][-1]
        self.assertIn('Original review', prompt)
        self.assertIn('"confidence": 0.28', prompt)
        self.assertEqual(len(calls), 2)

    def test_uncertain_consultant_false_pass_cannot_override_checks_or_original_review(self):
        def decide(state, kw):
            return self.advice('build') if state['phase'] == 'focus' else self.advice('other', 0.9)
        for mode in ('consult_false_pass', 'review_fail_once'):
            with self.subTest(mode=mode):
                code, report, calls = self.invoke(mode, decisions=decide)
                self.assertEqual(code, 1)
                entry = report['deep']['attempts'][0]
                self.assertEqual(entry['consultation']['review']['verdict'], 'PASS')
                self.assertEqual(entry['review']['verdict'], 'FAIL')
                self.assertEqual(entry['tests']['passed'], mode == 'review_fail_once')
                self.assertEqual(entry['effective_action'], 'stop')
                self.assertEqual(report['deep']['repairs_performed'], 0)
                self.assertEqual(len(calls), 2)

    def test_uncertain_consultant_fail_without_original_actionable_failure_stops(self):
        def decide(state, kw):
            return self.advice('build') if state['phase'] == 'focus' else self.advice('other', 0.9)
        code, report, _ = self.invoke('consult_fail', decisions=decide)
        self.assertEqual(code, 1)
        entry = report['deep']['attempts'][0]
        self.assertTrue(entry['tests']['passed'])
        self.assertEqual(entry['review']['verdict'], 'PASS')
        self.assertEqual(entry['consultation']['review']['verdict'], 'FAIL')
        self.assertEqual(entry['effective_action'], 'stop')
        self.assertEqual(report['deep']['repairs_performed'], 0)

    def test_uncertain_actionable_consultation_repairs_then_finishes(self):
        def decide(state, kw):
            return self.advice('build') if state['phase'] == 'focus' else self.advice('stop', 0.28)
        code, report, calls = self.invoke('repair', decisions=decide)
        self.assertEqual(code, 0, report.get('error'))
        deep = report['deep']
        self.assertEqual(deep['repairs_performed'], 1)
        self.assertEqual([a['effective_action'] for a in deep['attempts']],
                         ['repair_after_consultation', 'finish_after_consultation'])
        self.assertEqual([c['label'] for c in deep['consultations']], ['decision-reviewer', 'decision-reviewer-repair1'])
        self.assertTrue(all(d['recommendation'] == 'stop' for d in deep['jev_decisions'][1:]))
        self.assertEqual(len(calls), 3)
        repair_prompt = next(a['process']['command'][-1] for a in report['agents'] if a['label'] == 'worker-repair1')
        self.assertIn('consultation_findings', repair_prompt)
        self.assertIn('AssertionError', repair_prompt)

    def test_consultations_bounded_at_each_point_and_all_logs_sessions_retained(self):
        for budget in (0, 1, 2):
            with self.subTest(budget=budget):
                code, report, calls = self.invoke('no_improvement', extra=['--max-repairs', str(budget)],
                                                decisions=lambda s, kw: self.advice('stop', 0.28))
                self.assertEqual(code, 1)
                deep = report['deep']
                self.assertEqual(deep['repairs_performed'], budget)
                self.assertEqual(len(calls), budget + 2)
                self.assertEqual(len(deep['consultations']), budget + 2)
                self.assertEqual(deep['budget']['max_consultations'], 1)
                self.assertEqual(deep['budget']['consultations_performed'], budget + 2)
                self.assertEqual(deep['budget']['max_total_consultations'], budget + 2)
                self.assertTrue(all(v == 1 for v in deep['budget']['consultations_by_point'].values()))
                self.assertEqual(len(report['agents']), 3 + 3 * (budget + 1))
                self.assertEqual(len(report['agents']), deep['budget']['max_role_calls'])
                self.assertEqual(len(set(a['session_ids'][0] for a in report['agents'])), len(report['agents']))
                self.assertEqual(deep['attempts'][-1]['effective_action'], 'stop')
                for agent in report['agents']:
                    for extension in ('.stdout', '.stderr', '.events.jsonl', '.process.json'):
                        self.assertTrue((Path(report['output_dir']) / (agent['label'] + extension)).exists())
                for snap in deep['readonly_snapshots']:
                    self.assertEqual(snap['before'], snap['after'])

    def test_consultation_source_mutation_hash_tamper_or_session_reuse_fatal(self):
        for mode in ('focus_consult_mutation', 'decision_consult_mutation', 'consult_tamper', 'consult_same_session'):
            with self.subTest(mode=mode):
                def decide(state, kw):
                    return self.advice('build') if mode == 'decision_consult_mutation' and state['phase'] == 'focus' else self.advice('stop', 0.28)
                code, report, _ = self.invoke(mode, decisions=decide)
                self.assertEqual(code, 1)
                self.assertEqual(report['deep']['budget']['consultations_performed'], 1)
                self.assertEqual(report['deep']['repairs_performed'], 0)
                self.assertTrue(any(s in report['error'] for s in ('changed repository state', 'hash changed', 'session is not independent')))

    def test_malformed_routes_inconsistent_uncertainty_and_invalid_confidence_rejected(self):
        valid = self.advice('stop', 0.28)
        fixtures = [dict(valid, route=value) for value in ('other', None, [], 'advice')]
        fixtures += [dict(valid, uncertain=value) for value in (False, 1, None)]
        fixtures += [dict(valid, confidence_floor=value) for value in (0.2, True, None)]
        fixtures += [dict(valid, confidence=value) for value in (-1, 1.1, True, '0.28', float('nan'))]
        fixtures += [dict(self.advice('build'), route='consult'), dict(self.advice('other'), route='advice')]
        for key in ('route', 'uncertain', 'confidence_floor'):
            missing = valid.copy()
            del missing[key]
            fixtures.append(missing)
        for index, decision in enumerate(fixtures):
            with self.subTest(fixture=index):
                code, report, calls = self.invoke(decisions=lambda s, kw: decision)
                self.assertEqual(code, 1)
                self.assertEqual(len(report['agents']), 2)
                self.assertEqual(report['deep']['consultations'], [])
                self.assertEqual(len(calls), 1)

    def test_general_jev_focus_allows_confident_build_and_repair(self):
        def decide(state, kwargs):
            choice = ('build' if state['phase'] == 'focus' else
                      'finish' if state['checks_passed'] and state['review_verdict'] == 'PASS' else 'repair')
            return {'recommendation': choice, 'focus': 'general', 'confidence': 0.9,
                    'probabilities': {choice: 0.6, 'stop': 0.2, 'other': 0.2}}
        code, report, _ = self.invoke('repair', decisions=decide)
        self.assertEqual(code, 0, report.get('error'))
        self.assertEqual(report['deep']['repairs_performed'], 1)
        decisions = report['deep']['jev_decisions']
        self.assertEqual([d['recommendation'] for d in decisions], ['build', 'repair', 'finish'])
        self.assertTrue(all(d['focus'] == 'general' for d in decisions))
        for stage in report['agents']:
            if stage['role'] == 'worker':
                self.assertIn('"focus": "general"', stage['process']['command'][-1])

    def test_no_actionable_failure_prevents_repair(self):
        code, report, _ = self.invoke('empty_findings', decisions=['repair'])
        self.assertEqual(code, 1)
        self.assertTrue(report['deep']['after_tests']['passed'])
        self.assertEqual(len(report['agents']), 4)

    def test_describe_and_status_configuration_only(self):
        bridge = types.SimpleNamespace(status=lambda: {'configured': True, 'model': 'jev', 'reason': None},
                                       decide=mock.Mock(side_effect=AssertionError('No inference')))
        for command in (['describe'], ['status', '--output-root', str(self.runs)]):
            out = io.StringIO()
            with mock.patch.dict(sys.modules, {'jev_bridge': bridge}), contextlib.redirect_stdout(out):
                self.assertEqual(runtime.main(command), 0)
            value = json.loads(out.getvalue())
            self.assertTrue(value['jev']['configured'])
            if command[0] == 'describe':
                self.assertEqual(value['workflows'][-1], {'id': 'deep', 'name': 'Deep build · Jev', 'command': 'run', 'mode': 'deep',
                                                         'agents': ['opencode-planner', 'opencode-testdesigner', 'opencode-worker', 'opencode-reviewer']})
                self.assertEqual(len(value['agents']), 4)
                self.assertEqual(value['workflow_budgets']['deep']['max_consultations'], 1)
                self.assertEqual(value['workflow_budgets']['deep']['default_max_role_calls'], 9)
                self.assertEqual(value['workflow_budgets']['deep']['consultation_model_role'], 'reviewer')
        bridge.decide.assert_not_called()

    def test_real_bridge_contract_with_offline_client(self):
        import jev_bridge as real_bridge
        def answer(options, selected):
            return {'type': 'choice', 'choice': selected, 'confidence': 0.9,
                    'probabilities': {name: 0.9 if name == selected else 0.1 / (len(options) - 1)
                                      for name in options}}
        def ask(state, questions, *, run, label, budget_s):
            choice = 'build' if state['phase'] == 'focus' else 'finish'
            path = Path(run.session_dir) / 'jev' / (label + '-client.json')
            path.write_text('{}')
            return types.SimpleNamespace(
                answers={'next_action': answer(questions['next_action']['criteria'], choice),
                         'focus': answer(questions['focus']['criteria'], 'correctness')},
                model_requested='jev-latest', model_resolved='jev-test', elapsed_ms=1,
                input_tokens=12, output_tokens=3, receipt_path=str(path))
        client = types.SimpleNamespace(MODEL='jev-latest', JevResult=types.SimpleNamespace,
                                       ask=ask, disabled=lambda: False)
        with mock.patch.object(real_bridge, '_load_client', return_value=client), \
                mock.patch.dict(os.environ, {'TYPESAFE_API_KEY': 'offline-only-key', 'JEV_BACKEND': 'typesafe'}), \
                mock.patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network forbidden')) as network:
            code, report, _ = self.invoke(decisions=lambda state, kw: real_bridge.decide(state, **kw))
        self.assertEqual(code, 0, report.get('error'))
        self.assertEqual(report['deep']['jev_decisions'][-1]['focus'], 'general')
        self.assertEqual(report['deep']['jev_decisions'][-1]['input_tokens'], 12)
        self.assertTrue(Path(report['deep']['jev_decisions'][-1]['receipt_path']).is_file())
        network.assert_not_called()

    def test_each_check_snapshot_prevents_later_check_hiding_mutation(self):
        code, report, _ = self.invoke(extra=['--check', 'printf changed > value.txt',
                                            '--check', 'printf bad > value.txt'])
        self.assertEqual(code, 1)
        self.assertIn('changed repository source', report['error'])
        self.assertEqual(report['checks_executed'], 2)
        self.assertEqual((self.repo / 'value.txt').read_text(), 'changed')

    def test_invalid_repair_budget_rejected_before_run(self):
        for budget in ('-1', '3', '1.5'):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                runtime.main(['run', '--repo', str(self.repo), '--request', 'x', '--max-repairs', budget])
            self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
