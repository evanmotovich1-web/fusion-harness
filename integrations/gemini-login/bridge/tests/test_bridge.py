"""Tests use captured native evidence, never as proof of a fresh provider turn."""
import copy
import importlib.util
import json
import pathlib
import os
import sys
import signal
import subprocess
import tempfile
import threading
import time
from unittest.mock import patch
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = ROOT.parent / 'native-no-schema-probe.json'


def bridge():
    spec = importlib.util.spec_from_file_location('gemini_login_bridge', ROOT / 'gemini_login_bridge.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def request():
    return {'model': 'gemini-3.8-flash', 'messages': [{'role': 'user', 'content': 'Reply'}], 'tools': [], 'reasoning_effort': 'high', 'timeout_seconds': 10}


class ParserTests(unittest.TestCase):
    def test_captured_native_success_normalizes_exact_model_usage(self):
        self.assertTrue((ROOT / 'gemini_login_bridge.py').exists(), 'inference bridge not implemented')
        module = bridge()
        native = json.loads(EVIDENCE.read_text(encoding='utf-8'))
        result = module.parse_native_output(native['stdout'], native['stderr'], native['code'], request())
        self.assertEqual(result['model'], 'gemini-3.8-flash')
        self.assertEqual(result['content'], 'BRIDGE_OK')
        self.assertEqual(result['tool_calls'], [])
        self.assertEqual(result['usage'], {'prompt_tokens': 2324, 'completion_tokens': 517, 'total_tokens': 2841, 'prompt_tokens_details': {'cached_tokens': 0}, 'completion_tokens_details': {'reasoning_tokens': 505}})
        self.assertEqual(result['raw_usage']['thinking_tokens'], 505)
        self.assertEqual(result['conversation_id'], 'native-fixture-conversation')

    def test_cached_native_input_maps_to_total_prompt_tokens(self):
        module=bridge()
        native=json.loads(EVIDENCE.read_text(encoding='utf-8'))
        events=[json.loads(line) for line in native['stdout'].splitlines()]
        events[-1]['result']['usage']={'input_tokens':100,'output_tokens':20,'total_tokens':120,'cache_read_tokens':300,'thinking_tokens':10}
        result=module.parse_native_output('\n'.join(json.dumps(e) for e in events),'',0,request())
        self.assertEqual(result['usage']['prompt_tokens'],400)
        self.assertEqual(result['usage']['total_tokens'],420)
        self.assertEqual(result['usage']['prompt_tokens_details']['cached_tokens'],300)
        self.assertEqual(result['raw_usage']['input_tokens'],100)

    def test_untrusted_native_output_is_rejected(self):
        module = bridge()
        native = json.loads(EVIDENCE.read_text(encoding='utf-8'))
        events = [json.loads(line) for line in native['stdout'].splitlines()]
        cases = []
        def change(label, update):
            altered = copy.deepcopy(events)
            update(altered)
            cases.append((label, '\n'.join(json.dumps(e) for e in altered), '', 0))
        change('wrong model', lambda e: e[0]['init'].update(model='gemini-4-argon'))
        change('wrong agent', lambda e: e[0]['init'].update(agent='other'))
        change('failed status', lambda e: e[-1]['result'].update(status='ERROR'))
        change('empty answer', lambda e: e[-1]['result'].update(response='{"content":"","tool_calls":[]}'))
        change('fenced JSON', lambda e: e[-1]['result'].update(response='```json\n{"content":"ok","tool_calls":[]}\n```'))
        change('duplicate JSON keys', lambda e: e[-1]['result'].update(response='{"content":"ok","content":"bad","tool_calls":[]}'))
        change('wrong JSON shape', lambda e: e[-1]['result'].update(response='{"content":"ok","tool_calls":[],"extra":true}'))
        change('native tool event', lambda e: e.insert(1, {'event':'tool_call', 'name':'run_command'}))
        change('native tool step', lambda e: e[1]['step_update'].update(step_type='tool_call'))
        change('incomplete step', lambda e: e[-2]['step_update'].update(state='ACTIVE'))
        change('multiple turns', lambda e: e[-1]['result'].update(num_turns=2))
        change('conversation mismatch', lambda e: e[-1]['result'].update(conversation_id='different'))
        change('bad usage', lambda e: e[-1]['result']['usage'].update(input_tokens=-1))
        change('extra result', lambda e: e.append(copy.deepcopy(e[-1])))
        change('undeclared tool', lambda e: e[-1]['result'].update(response='{"content":"","tool_calls":[{"name":"run_command","arguments":"{}"}]}'))
        cases.extend([('nonzero', native['stdout'], '', 1), ('timeout despite SUCCESS', native['stdout'], 'print timeout reached', 0), ('any stderr', native['stdout'], 'warning', 0), ('missing result', '\n'.join(json.dumps(e) for e in events[:-1]), '', 0), ('trailing garbage', native['stdout']+'not json\n', '', 0)])
        for label, out, err, code in cases:
            with self.subTest(label=label):
                with self.assertRaises(ValueError, msg=label):
                    module.parse_native_output(out, err, code, request())

    def test_declared_host_calls_require_json_object_arguments_and_choice(self):
        module = bridge()
        native = json.loads(EVIDENCE.read_text(encoding='utf-8'))
        events = [json.loads(line) for line in native['stdout'].splitlines()]
        req = request()
        req['tools'] = [{'type':'function', 'function':{'name':'lookup', 'parameters':{'type':'object'}}}]
        def parse(call, choice='auto'):
            req['tool_choice'] = choice
            events[-1]['result']['response'] = json.dumps({'content':'', 'tool_calls':[call]})
            return module.parse_native_output('\n'.join(json.dumps(e) for e in events), '', 0, req)
        result = parse({'name':'lookup', 'arguments':'{"word":"雪"}'})
        normalized = result['tool_calls'][0]
        self.assertIn('type', normalized, 'host calls must be normalized')
        self.assertEqual(normalized['type'], 'function')
        self.assertTrue(normalized['id'].startswith('agy_call_'))
        self.assertEqual(normalized['function'], {'name':'lookup', 'arguments':'{"word":"雪"}'})
        for arguments in ('[]', 'null', '3', '{"x":NaN}', '{"x":1,"x":2}', '{} trailing', {'x':1}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                parse({'name':'lookup', 'arguments':arguments})
        with self.assertRaises(ValueError):
            parse({'name':'lookup', 'arguments':'{}', 'extra':True})
        with self.assertRaises(ValueError):
            parse({'name':'lookup', 'arguments':'{}'}, 'none')
        req['tools'].append({'type':'function','function':{'name':'other','parameters':{'type':'object'}}})
        with self.assertRaises(ValueError):
            parse({'name':'lookup', 'arguments':'{}'}, {'type':'function','function':{'name':'other'}})
        req['tool_choice'] = 'required'
        events[-1]['result']['response'] = '{"content":"No tool","tool_calls":[]}'
        with self.assertRaises(ValueError):
            module.parse_native_output('\n'.join(json.dumps(e) for e in events), '', 0, req)


class RequestTests(unittest.TestCase):
    def test_text_request_preserves_replay_and_rejects_lossy_inputs(self):
        module = bridge()
        self.assertTrue(hasattr(module, 'prepare_request'), 'request envelope not implemented')
        req = request()
        req['messages'] += [{'role':'assistant', 'content':None, 'tool_calls':[{'id':'h1','type':'function','function':{'name':'lookup','arguments':'{}'}}]}, {'role':'tool','tool_call_id':'h1','content':'雪 café'}, {'role':'user','content':[{'type':'text','text':'Summarize'}]}]
        req['tools'] = [{'type':'function','function':{'name':'lookup','parameters':{'type':'object'}}}]
        req['max_tokens'] = 99
        prepared, prompt = module.prepare_request(req)
        envelope = json.loads(prompt)
        self.assertEqual(envelope['messages'], req['messages'])
        self.assertEqual(envelope['tools'], req['tools'])
        self.assertEqual(prepared['model'], req['model'])
        self.assertNotIn('max_tokens', envelope)
        self.assertIn('JSON object', envelope['output_rules'])
        mutations = [
            {'model':'google-gemini-cli/gemini-3.8-flash'}, {'model':' gemini-3.8-flash'}, {'model':'gemini-2.5-pro'},
            {'reasoning_effort':'none'}, {'timeout_seconds':0}, {'timeout_seconds':float('nan')}, {'timeout_seconds':999999},
            {'messages':[{'role':'user','content':[{'type':'image_url','image_url':{'url':'x'}}]}]},
            {'messages':[{'role':'user','content':[{'type':'input_audio','input_audio':{}}]}]},
            {'messages':[{'role':'tool','content':'missing ID'}]}, {'messages':[]},
            {'tools':[{'type':'function','function':{'name':'bad name','parameters':{}}}]},
            {'tools':req['tools'] * 2}, {'tools':[{'type':'web_search'}]},
            {'tool_choice':{'type':'function','function':{'name':'undeclared'}}}, {'tool_choice':'invalid'},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                module.prepare_request({**req, **mutation})


class TransportTests(unittest.TestCase):
    def test_real_subprocess_stdin_transport_and_host_replay(self):
        module = bridge()
        self.assertTrue(hasattr(module, 'complete'), 'subprocess inference not implemented')
        req = request()
        req['messages'] += [{'role':'assistant','content':None,'tool_calls':[{'id':'h1','type':'function','function':{'name':'lookup','arguments':'{}'}}]}, {'role':'tool','tool_call_id':'h1','content':'雪 café'}]
        req['tools'] = [{'type':'function','function':{'name':'lookup','parameters':{'type':'object'}}}]
        for mode, expected in [('replay','BRIDGE_OK'), ('unicode','雪 café 🧪')]:
            with patch.dict(os.environ, {'BRIDGE_FIXTURE_MODE':mode}):
                result = module.complete(req, command=[sys.executable, str(ROOT / 'tests/fixture_cli.py')])
            self.assertEqual(result['content'], expected)
        with patch.dict(os.environ, {'BRIDGE_FIXTURE_MODE':'host_tool'}):
            result = module.complete(req, command=[sys.executable, str(ROOT / 'tests/fixture_cli.py')])
        self.assertEqual(result['tool_calls'][0]['function']['name'], 'lookup')

    def test_bounded_transport_cancels_owned_process_group(self):
        module = bridge()
        self.assertTrue(hasattr(module, 'BridgeTimeoutError'), 'bounded subprocess lifecycle not implemented')
        self.assertTrue(hasattr(module, 'BridgeCancelledError'))
        command = [sys.executable, str(ROOT / 'tests/fixture_cli.py')]
        for mode in ('sleep', 'native_tool', 'partial_success'):
            with tempfile.TemporaryDirectory(dir=ROOT) as directory:
                pidfile = pathlib.Path(directory) / 'pids.json'
                req = {**request(), 'timeout_seconds':0.3}
                started = time.monotonic()
                try:
                    with patch.dict(os.environ, {'BRIDGE_FIXTURE_MODE':mode, 'BRIDGE_FIXTURE_PIDS':str(pidfile)}):
                        with self.assertRaises(ValueError):
                            module.complete(req, command=command)
                    self.assertLess(time.monotonic()-started, 2)
                    if pidfile.exists():
                        for pid in json.loads(pidfile.read_text()):
                            state = subprocess.run(['ps','-o','stat=','-p',str(pid)], capture_output=True, text=True).stdout.strip()
                            self.assertTrue(not state or state.startswith('Z'), f'live orphan {pid}: {state}')
                finally:
                    if pidfile.exists():
                        try:
                            os.killpg(json.loads(pidfile.read_text())[0], signal.SIGKILL)
                        except ProcessLookupError:
                            pass
        for mode in ('nonzero','stderr','invalid_utf8'):
            with patch.dict(os.environ, {'BRIDGE_FIXTURE_MODE':mode}), self.assertRaises(ValueError):
                module.complete(request(), command=command)
        with patch.object(module, 'MAX_OUTPUT_BYTES', 10000), patch.dict(os.environ, {'BRIDGE_FIXTURE_MODE':'overflow'}), self.assertRaises(ValueError):
            module.complete(request(), command=command)
        cancel = threading.Event()
        timer = threading.Timer(0.2, cancel.set)
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            pidfile = pathlib.Path(directory) / 'pids.json'
            with patch.dict(os.environ, {'BRIDGE_FIXTURE_MODE':'sleep','BRIDGE_FIXTURE_PIDS':str(pidfile)}):
                timer.start()
                try:
                    with self.assertRaises(module.BridgeCancelledError):
                        module.complete(request(), command=command, cancel_event=cancel)
                    for pid in json.loads(pidfile.read_text()):
                        state = subprocess.run(['ps','-o','stat=','-p',str(pid)], capture_output=True, text=True).stdout.strip()
                        self.assertTrue(not state or state.startswith('Z'))
                finally:
                    timer.cancel()
                    if pidfile.exists():
                        try:
                            os.killpg(json.loads(pidfile.read_text())[0], signal.SIGKILL)
                        except ProcessLookupError:
                            pass

    def test_json_cli_handles_errors_and_sigterm_without_orphans(self):
        module = bridge()
        self.assertTrue(hasattr(module, 'main'), 'single-request JSON CLI not implemented')
        env = {**os.environ, 'GEMINI_LOGIN_CLI':str(ROOT / 'tests/fixture_cli.py'), 'BRIDGE_FIXTURE_MODE':'unicode'}
        proc = subprocess.run([sys.executable, str(ROOT / 'gemini_login_bridge.py')], input=json.dumps(request()), capture_output=True, text=True, env=env, timeout=5)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(proc.stdout.splitlines()), 1)
        self.assertEqual(json.loads(proc.stdout)['content'], '雪 café 🧪')
        for invalid in ('not JSON PRIVATE_MARKER', '{"model":"gemini-3.8-flash","model":"bad"}', json.dumps({**request(), 'model':'bad'})):
            proc = subprocess.run([sys.executable, str(ROOT / 'gemini_login_bridge.py')], input=invalid, capture_output=True, text=True, env=env, timeout=5)
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, '')
            self.assertNotIn('PRIVATE_MARKER', proc.stderr)
            self.assertNotIn('Traceback', proc.stderr)
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            pidfile = pathlib.Path(directory) / 'pids.json'
            env.update(BRIDGE_FIXTURE_MODE='sleep', BRIDGE_FIXTURE_PIDS=str(pidfile))
            proc = subprocess.Popen([sys.executable, str(ROOT / 'gemini_login_bridge.py')], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            try:
                proc.stdin.write(json.dumps(request()).encode())
                proc.stdin.close()
                proc.stdin = None
                deadline = time.monotonic()+3
                while not pidfile.exists() and time.monotonic()<deadline:
                    time.sleep(0.02)
                self.assertTrue(pidfile.exists(), 'fixture failed to start')
                proc.send_signal(signal.SIGTERM)
                out, err = proc.communicate(timeout=3)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(out, b'')
                self.assertIn(b'cancelled', err)
                for pid in json.loads(pidfile.read_text()):
                    state = subprocess.run(['ps','-o','stat=','-p',str(pid)], capture_output=True, text=True).stdout.strip()
                    self.assertTrue(not state or state.startswith('Z'))
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
                if pidfile.exists():
                    try:
                        os.killpg(json.loads(pidfile.read_text())[0], signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_parent_owned_cli_group_contains_native_descendants(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            pidfile = pathlib.Path(directory) / 'pids.json'
            env = {**os.environ, 'GEMINI_LOGIN_PARENT_PROCESS_GROUP':'1', 'GEMINI_LOGIN_CLI':str(ROOT / 'tests/fixture_cli.py'), 'BRIDGE_FIXTURE_MODE':'sleep', 'BRIDGE_FIXTURE_PIDS':str(pidfile)}
            proc = subprocess.Popen([sys.executable, str(ROOT / 'gemini_login_bridge.py')], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, start_new_session=True)
            try:
                proc.stdin.write(json.dumps(request()).encode())
                proc.stdin.close()
                proc.stdin = None
                deadline = time.monotonic()+3
                while not pidfile.exists() and time.monotonic()<deadline:
                    time.sleep(0.02)
                self.assertTrue(pidfile.exists())
                pids = json.loads(pidfile.read_text())
                self.assertEqual([os.getpgid(pid) for pid in pids], [proc.pid,proc.pid], 'native descendants must remain in detached parent-owned group')
                os.killpg(proc.pid, signal.SIGTERM)
                out, err = proc.communicate(timeout=3)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(out, b'')
                for pid in pids:
                    state = subprocess.run(['ps','-o','stat=','-p',str(pid)], capture_output=True, text=True).stdout.strip()
                    self.assertTrue(not state or state.startswith('Z'))
            finally:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait(timeout=3)
                if pidfile.exists():
                    for pid in json.loads(pidfile.read_text()):
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass


if __name__ == '__main__':
    unittest.main()
