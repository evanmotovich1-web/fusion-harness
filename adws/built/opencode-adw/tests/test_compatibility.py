"""Focused offline checks: no Git, model calls, capture or ADW execution."""
import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
# Sanitized public 2.0.32 API excerpt; provenance is recorded in the fixture.
CONTRACT = ROOT / 'tests/fixtures/opencode-2.0.32-contract.json'


def load(name):
    spec = importlib.util.spec_from_file_location('compat_' + name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CompatibilityTests(unittest.TestCase):
    def test_doctor_large_schema_output_uses_unlinked_regular_file(self):
        doctor = load('doctor')
        output = doctor.probe(sys.executable, ['-c', 'print("x" * 400000)'], ROOT)
        self.assertEqual(len(output), 400001)

    def test_v2_cwd_invocation_without_wrapper_preserves_explicit_model_and_events(self):
        runtime = load('runtime')
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            repo = folder / 'repo with spaces'
            repo.mkdir()
            args = types.SimpleNamespace(repo=repo, timeout=10)
            report = {'models': {'worker': 'openai/gpt-6.1-sol'}, 'agents': []}

            def execute(argv, cwd, timeout, prefix):
                self.assertEqual(argv, [runtime.os.environ.get('OPENCODE_ADW_OPENCODE', str(Path.home() / '.opencode/bin/opencode')), 'run', '--format', 'json',
                                       '--agent', 'opencode-worker', '--model',
                                       'openai/gpt-6.1-sol', 'request'])
                self.assertEqual(cwd, repo)
                stdout = prefix.with_suffix('.stdout')
                stdout.write_text(json.dumps({'type': 'text', 'sessionID': 'ses_fixture',
                                             'part': {'text': 'done'}}) + '\n')
                return {'stdout': str(stdout), 'exit_code': 0}

            with mock.patch.object(runtime, 'execute', execute):
                stage = runtime._agent(args, report, folder, 'worker', 'request')
            self.assertEqual(stage['session_ids'], ['ses_fixture'])
            self.assertEqual(stage['text'], 'done')

    def test_unknown_event_envelope_is_not_silently_accepted(self):
        runtime = load('runtime')
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            stdout = folder / 'stdout'
            stdout.write_text(json.dumps({'type': 'future.response', 'data': {'text': 'done'}}))
            with mock.patch.object(runtime, 'execute', return_value={'stdout': str(stdout), 'exit_code': 0}):
                with self.assertRaises(runtime.Failure):
                    runtime._agent(types.SimpleNamespace(repo=folder, timeout=10),
                                   {'models': {'worker': 'p/m'}, 'agents': []}, folder, 'worker', 'request')

    def test_doctor_versions_loader_failures_and_redaction(self):
        doctor = load('doctor')
        projects = [Path('/first'), Path('/second')]
        for version, state, expected in [('opencode v2.0.32', 'active', 'PROBES_PASSED'),
                                          ('opencode v2.0.32', 'failed', 'BLOCKED'),
                                          ('opencode v2.0.33', 'active', 'BLOCKED'),
                                          ('opencode v3.0.0', 'active', 'BLOCKED'),
                                          ('opencode v2.0.32-beta', 'active', 'BLOCKED'),
                                          ('opencode v1.9.0', 'active', 'BLOCKED')]:
            with self.subTest(version=version, state=state):
                calls = []

                def runner(binary, args, cwd):
                    calls.append(args)
                    if args == ['--version']:
                        return version
                    if args == ['run', '--help']:
                        return '--format --agent --model'
                    if args == ['api', 'get', '/openapi.json']:
                        return CONTRACT.read_text()
                    return json.dumps({'location': {'directory': str(cwd)}, 'data': [{
                        'source': {'path': '/config/plugins/opencode-team.js'},
                        'state': {'status': state, 'error': 'SECRET'}}]})

                result = doctor.inspect('/real/opencode', projects, runner)
                self.assertEqual(result['state'], expected)
                self.assertNotIn('SECRET', json.dumps(result))
                self.assertFalse(result['tool_discovery_verified'])
                self.assertFalse(result['status_tool_call_verified'])
                self.assertFalse(result['recovery']['automatic_writes'])
                self.assertEqual(result['recovery']['max_automatic_retries'], 0)
                self.assertFalse(any('upgrade' in command or 'reload' in command for command in calls))

    def test_doctor_rejects_wrong_location_missing_duplicate_and_malformed_plugins(self):
        doctor = load('doctor')
        for payload in ['invalid', '{}', json.dumps({'location': {'directory': '/wrong'}, 'data': [
                {'id': 'opencode-team', 'state': {'status': 'active'}}]}),
                json.dumps({'location': {'directory': '/first'}, 'data': [
                    {'id': 'opencode-team', 'state': {'status': 'active'}}] * 2})]:
            def runner(binary, args, cwd):
                return '2.0.32' if args == ['--version'] else (
                    '--format --agent --model' if args == ['run', '--help'] else payload)
            self.assertEqual(doctor.inspect('/real', [Path('/first'), Path('/second')], runner)['state'], 'BLOCKED')

    def test_installer_preflight_is_read_only_and_preserves_modified_assets(self):
        installer = load('install')
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'not-created'
            result = installer.install(destination, check=True)
            self.assertFalse(result['writes'])
            self.assertFalse(destination.exists())
            installer.install(destination)
            target = destination / 'plugins/opencode-team.js'
            target.write_text('local changes')
            with self.assertRaisesRegex(ValueError, 'preserved'):
                installer.install(destination, check=True)
            self.assertEqual(target.read_text(), 'local changes')

    def test_doctor_contract_detects_missing_or_changed_transport(self):
        doctor = load('doctor')
        contract = json.loads(CONTRACT.read_text())
        self.assertTrue(doctor.v2_contract(contract))
        create = ('paths', '/api/session', 'post', 'requestBody', 'content',
                  'application/json', 'schema', 'properties')
        prompt = ('paths', '/api/session/{sessionID}/prompt', 'post',
                  'requestBody', 'content', 'application/json', 'schema')
        required_fields = [(*create, key) for key in ('parentID', 'location', 'agent', 'model')]
        required_fields += [(*prompt, 'required'), (*prompt, 'properties', 'resume')]
        required_fields += [('paths', '/api/session/{sessionID}/' + action, method,
                             'responses', code) for action, method, code in (
                                 ('move', 'post', '204'), ('agent', 'post', '204'),
                                 ('model', 'post', '204'), ('interrupt', 'post', '200'),
                                 ('context', 'get', '200'))]
        for field in required_fields:
            with self.subTest(missing=field):
                changed = json.loads(CONTRACT.read_text())
                parent = changed
                for key in field[:-1]:
                    parent = parent[key]
                del parent[field[-1]]
                self.assertFalse(doctor.v2_contract(changed))
        contract['paths']['/api/session/{sessionID}/prompt']['post']['requestBody'][
            'content']['application/json']['schema']['required'] = ['resume']
        self.assertFalse(doctor.v2_contract(contract))
        for value in (None, {}, {'paths': None}):
            self.assertFalse(doctor.v2_contract(value))
