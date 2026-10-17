"""Offline native API contract, including real helper cancellation processes."""
import base64
import contextlib
import http.server
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import native_team as nt


def assistant(sid, *, agent='opencode-reviewer', model='provider/model/variant'):
    provider, model_id = model.split('/', 1)
    info = dict(id='msg_assistant', sessionID=sid, role='assistant', agent=agent,
                providerID=provider, modelID=model_id, time={'completed': 1},
                tokens={'input': 999}, cost=999)
    parts = [dict(type='step-start'), dict(type='text', text='final answer'),
             dict(type='tool', tool='read', state={'status': 'completed'}),
             dict(type='step-finish', tokens={'input': 4, 'output': 7,
                  'reasoning': 2, 'cache': {'read': 1, 'write': 0}}, cost=0.25)]
    for i, part in enumerate(parts):
        part.update(id='part_' + str(i), sessionID=sid, messageID=info['id'])
    return dict(info=info, parts=parts)


class Backend:
    def __init__(self):
        self.calls = []
        self.sessions = {'ses_parent': dict(id='ses_parent', location={'directory': '/home/parent'}, projectID='global')}
        self.messages = {}
        self.abort_ids = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.delay = False
        self.mode = ''

    def handle(self, method, path, directory, body):
        self.calls.append((method, path, directory, body))
        if path == '/api/info':
            return {'version': '2.0.32'}
        if method == 'POST' and path == '/api/session':
            sid = 'ses_' + str(len(self.sessions))
            if self.mode == 'reuse':
                sid = next(reversed(self.sessions))
            location = self.sessions[body['parentID']]['location'] if body.get('parentID') else body['location']
            value = dict(id=sid, projectID='different-git-project', **body)
            value['location'] = location
            self.sessions[sid] = value
            return value
        sid = path.split('/')[3]
        if path.endswith('/move'):
            self.sessions[sid]['location'] = {'directory': body['directory']}
            return {'id': 'move-admission'}
        if path.endswith(('/agent', '/model')):
            self.sessions[sid].update(body)
            return self.sessions[sid]
        if path.endswith('/interrupt'):
            self.abort_ids.append(sid)
            return True
        if path.endswith(('/prompt', '/context')):
            if path.endswith('/prompt'):
                if body.get('resume') is False:
                    return {'id': 'prompt-admission'}
                self.started.set()
                if self.delay:
                    self.release.wait(4)
                session = self.sessions[sid]
                msg = {'id': 'msg_assistant', 'type': 'assistant', 'agent': session['agent'],
                       'model': dict(session['model'], variant='default'),
                       'time': {'completed': 1}, 'finish': 'stop',
                       'content': [{'type': 'text', 'text': 'final answer'},
                                   {'type': 'tool', 'name': 'read', 'state': {'status': 'completed'}}],
                       'tokens': {'input': 4, 'output': 7}, 'cost': .25}
                if self.mode == 'fallback':
                    msg['agent'] = 'build'
                if self.mode == 'provider':
                    msg['error'] = {'message': 'credential-secret raw provider headers'}
                if self.mode == 'tool':
                    msg['content'][1]['state'] = {'status': 'error', 'error': 'credential-secret'}
                self.messages[sid] = [msg, {'id': 'msg_idle', 'type': 'idle', 'outcome': 'succeeded'}]
                return {'id': 'prompt-admission'}
            return self.messages.get(sid, [])
        return self.sessions[sid]


@contextlib.contextmanager
def server():
    backend = Backend()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.dispatch('GET')

        def do_POST(self):
            self.dispatch('POST')

        def dispatch(self, method):
            parsed = urlsplit(self.path)
            raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            body = json.loads(raw) if raw else None
            backend.auth = self.headers.get('Authorization')
            if backend.mode == 'http-error' and parsed.path.endswith('/prompt'):
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b'credential-secret headers')
                return
            assert parsed.path.startswith('/api/'), 'Legacy API path is forbidden'
            assert not parsed.query, 'V2 session APIs do not take directory queries'
            value = backend.handle(method, parsed.path, None, body)
            if parsed.path.endswith(('/move', '/agent', '/model')):
                self.send_response(204)
                self.end_headers()
                return
            envelope = ({'interrupted': value} if parsed.path.endswith('/interrupt') else
                        value if parsed.path == '/api/info' else {'data': value})
            data = json.dumps(envelope).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{httpd.server_port}', backend
    finally:
        backend.release.set()
        httpd.shutdown()
        httpd.server_close()
        thread.join()


class NativeTests(unittest.TestCase):
    def test_cross_project_native_parent_child_and_private_prompts(self):
        with tempfile.TemporaryDirectory() as temp, server() as (url, backend):
            with nt.NativeTeam('/different/repo', temp, server_url=url,
                               parent_session_id='ses_parent', parent_directory='/home/parent') as team:
                cmd = team.command('reviewer', 'consult-focus', 'provider/model/variant', 'private prompt', 3)
                sid = team.children[-1]['session_id']
                self.assertEqual(backend.sessions[sid]['parentID'], 'ses_parent')
                self.assertEqual(backend.sessions[sid]['projectID'], 'different-git-project')
                self.assertTrue(any(c[1] == '/api/session/' + sid for c in backend.calls))
                self.assertEqual(backend.sessions[sid]['location']['directory'], '/different/repo')
                self.assertEqual(Path(cmd[cmd.index('--prompt-file') + 1]).stat().st_mode & 0o777, 0o600)
                self.assertNotIn('private prompt', cmd)
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                events = [json.loads(line) for line in result.stdout.splitlines()]
                self.assertEqual([e['type'] for e in events], ['text', 'tool_use', 'step_finish'])
                self.assertEqual(events[-1]['part']['tokens']['input'], 4)
                self.assertEqual(events[-1]['part']['cost'], .25)
                stage = {'session_ids': [sid], 'process': {'exit_code': 0}, 'errors': []}
                team.finish_child('consult-focus', stage)
                # Repeated role and label still create independent native sessions.
                team.command('reviewer', 'consult-focus', 'provider/model/variant', 'again', 3)
                self.assertNotEqual(team.children[-1]['session_id'], sid)
                snap = team.snapshot()
                json.dumps(snap)
                snap['children'][0]['state'] = 'mutated'
                self.assertEqual(team.children[0]['state'], 'completed')
            self.assertEqual(backend.abort_ids, [team.children[-1]['session_id']])
            self.assertIn(sid, backend.sessions)  # Sessions are never deleted.
            self.assertEqual(nt.API(url).request('GET', '/api/session/ses_parent', '/home/parent')['id'], 'ses_parent')

    def test_new_parent_and_router_code_and_jev_receipts(self):
        with tempfile.TemporaryDirectory() as temp, server() as (url, backend):
            with nt.NativeTeam('/repo', temp, server_url=url) as team:
                self.assertTrue(backend.sessions[team.parent_session_id]['title'].startswith('OpenCode Team'))
                team.router_note({'method': 'context', 'model': 'unearned', 'status': 'resolved'})
                self.assertIsNone(team.children[-1]['model'])
                self.assertEqual(team.children[-1]['execution'], 'code')
                team.router_note({'method': 'semantic', 'jev': {'model_resolved': 'jev-real'},
                                  'model_requested': 'jev', 'model_resolved': 'jev-real',
                                  'input_tokens': 12, 'status': 'resolved'})
                self.assertEqual(team.children[-1]['model'], 'jev-real')
                posts = [c[3] for c in backend.calls if c[0] == 'POST' and c[1].endswith('/prompt')]
                self.assertTrue(all(p['resume'] is False for p in posts))
                self.assertTrue(all('model' not in p and 'agent' not in p for p in posts))
                self.assertNotIn('unearned', posts[0]['text'])
                self.assertIn('jev-real', posts[1]['text'])
            self.assertEqual(backend.abort_ids, [])

    def test_process_failure_and_identity_mismatch_abort_only_owned(self):
        for stage in ({'session_ids': ['ses_parent'], 'process': {'exit_code': 0}},
                      {'session_ids': [], 'process': {'exit_code': -9, 'error': 'timeout'}},
                      {'session_ids': [], 'process': {'exit_code': 0}, 'errors': ['error']}):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temp, server() as (url, backend):
                with nt.NativeTeam('/repo', temp, server_url=url, parent_session_id='ses_parent', parent_directory='/home/parent') as team:
                    team.command('worker', 'worker', 'p/m', 'prompt', 1)
                    with self.assertRaisesRegex(nt.Failure, 'NATIVE_CHILD_FAILED'):
                        team.finish_child('worker', stage)
                    self.assertEqual(team.children[0]['state'], 'failed')
                self.assertEqual(backend.abort_ids, [team.children[0]['session_id']])

    def test_reused_child_is_rejected_without_aborting_prior_session(self):
        with tempfile.TemporaryDirectory() as temp, server() as (url, backend):
            with nt.NativeTeam('/repo', temp, server_url=url, parent_session_id='ses_parent', parent_directory='/home/parent') as team:
                team.command('reviewer', 'first', 'p/m', 'prompt', 1)
                backend.mode = 'reuse'
                with self.assertRaisesRegex(nt.Failure, 'NATIVE_SESSION_REUSED'):
                    team.command('reviewer', 'consult', 'p/m', 'prompt', 1)
                self.assertEqual(backend.abort_ids, [])
                self.assertEqual(len(team.children), 1)

    def test_parent_identity_and_child_association_are_verified(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(nt.API, 'request', return_value={'id': 'ses_wrong'}):
            with self.assertRaisesRegex(nt.Failure, 'NATIVE_PARENT_MISMATCH'):
                with nt.NativeTeam('/repo', temp, server_url='http://127.0.0.1:123', parent_session_id='ses_parent'):
                    pass
        with tempfile.TemporaryDirectory() as temp, server() as (url, backend):
            with nt.NativeTeam('/repo', temp, server_url=url, parent_session_id='ses_parent', parent_directory='/home/parent') as team:
                original = backend.handle

                def missing_association(method, path, directory, body):
                    if method == 'GET' and path.startswith('/api/session/ses_') and not path.endswith('ses_parent'):
                        return {'id': path.split('/')[-1], 'parentID': 'ses_wrong'}
                    return original(method, path, directory, body)

                backend.handle = missing_association
                with self.assertRaisesRegex(nt.Failure, 'NATIVE_CHILD_NOT_ASSOCIATED'):
                    team.command('reviewer', 'consult', 'p/m', 'prompt', 1)
                self.assertEqual(backend.abort_ids, [team.children[-1]['session_id']])
                self.assertNotIn('ses_parent', backend.abort_ids)

    def test_failed_process_abort_is_retried_at_close_without_losing_failed_state(self):
        with tempfile.TemporaryDirectory() as temp, server() as (url, backend):
            with nt.NativeTeam('/repo', temp, server_url=url) as team:
                team.command('worker', 'worker', 'p/m', 'prompt', 1)
                original = team.api.request

                def transient_failure(method, path, *args, **kwargs):
                    if path.endswith('/interrupt'):
                        raise nt.Failure('NATIVE_TRANSPORT_ERROR')
                    return original(method, path, *args, **kwargs)

                with mock.patch.object(team.api, 'request', side_effect=transient_failure):
                    with self.assertRaises(nt.Failure):
                        team.finish_child('worker', {'session_ids': [], 'process': {'exit_code': -9}})
                    self.assertFalse(team.children[-1]['abort_sent'])
            self.assertEqual(backend.abort_ids, [team.children[-1]['session_id']])
            self.assertEqual(team.children[-1]['state'], 'failed')
            self.assertTrue(team.children[-1]['abort_sent'])

    def test_helper_fixed_errors_never_raw_backend_credentials(self):
        for mode, expected in [('provider', 'NATIVE_PROVIDER_ERROR'),
                               ('fallback', 'NATIVE_AGENT_MODEL_MISMATCH'),
                               ('tool', 'NATIVE_TOOL_ERROR'), ('http-error', 'NATIVE_PERMISSION')]:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp, server() as (url, backend):
                with nt.NativeTeam('/repo', temp, server_url=url) as team:
                    cmd = team.command('worker', 'worker', 'p/m', 'prompt', 2)
                    backend.mode = mode
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn(expected, result.stdout)
                    self.assertNotIn('credential-secret', result.stdout + result.stderr)
                    self.assertTrue(backend.abort_ids)

    def test_timeout_and_sigterm_abort_helper_native_session(self):
        for cancel in (False, True):
            with self.subTest(cancel=cancel), tempfile.TemporaryDirectory() as temp, server() as (url, backend):
                with nt.NativeTeam('/repo', temp, server_url=url) as team:
                    backend.delay = True
                    cmd = team.command('reviewer', 'reviewer', 'p/m', 'prompt', 3 if cancel else .15)
                    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    self.assertTrue(backend.started.wait(2))
                    if cancel:
                        process.send_signal(signal.SIGTERM)
                    stdout, stderr = process.communicate(timeout=4)
                    self.assertEqual(process.returncode, 1, stdout + stderr)
                    self.assertIn('NATIVE_CANCELLED' if cancel else 'NATIVE_TIMEOUT', stdout)
                    self.assertIn(team.children[-1]['session_id'], backend.abort_ids)
                    backend.release.set()

    def test_core_sigkill_is_recovered_by_finish(self):
        with tempfile.TemporaryDirectory() as temp, server() as (url, backend):
            with nt.NativeTeam('/repo', temp, server_url=url) as team:
                backend.delay = True
                cmd = team.command('worker', 'worker', 'p/m', 'prompt', 3)
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertTrue(backend.started.wait(2))
                process.kill()
                process.communicate(timeout=2)
                with self.assertRaises(nt.Failure):
                    team.finish_child('worker', {'session_ids': [], 'process': {'exit_code': -9}})
                self.assertEqual(backend.abort_ids, [team.children[-1]['session_id']])
                backend.release.set()

    def test_url_restrictions_and_env_only_auth(self):
        for url in ('http://example.com:80', 'http://127.0.0.1.evil:80',
                    'http://user:secret@127.0.0.1:80', 'file:///tmp/a',
                    'http://127.0.0.1:80/path', 'http://127.0.0.1:80?password=x'):
            with self.subTest(url=url), self.assertRaisesRegex(nt.Failure, '^NATIVE_INVALID_SERVER$'):
                nt.API(url)
        self.assertEqual(nt.server_address('http://[::1]:123/'), 'http://[::1]:123')
        with tempfile.TemporaryDirectory() as temp, server() as (url, backend), mock.patch.dict(
                os.environ, {'OPENCODE_SERVER_USERNAME': 'alice', 'OPENCODE_SERVER_PASSWORD': 'credential-secret'}):
            with nt.NativeTeam('/repo', temp, server_url=url) as team:
                command = team.command('worker', 'worker', 'p/m', 'prompt', 1)
                self.assertEqual(backend.auth, 'Basic ' + base64.b64encode(b'alice:credential-secret').decode())
                self.assertNotIn('credential-secret', json.dumps(team.snapshot()) + repr(command))

    def test_response_limit_and_no_redirect_auth_forwarding(self):
        with server() as (url, backend), mock.patch.object(nt, 'MAX_RESPONSE', 5):
            with self.assertRaisesRegex(nt.Failure, 'NATIVE_RESPONSE_LIMIT'):
                nt.API(url).request('GET', '/api/session/ses_parent', '/repo')
        self.assertIsNone(nt.NoRedirect().redirect_request(None, None, 302, '', {}, 'http://evil'))

    def test_native_parts_deduplicated_with_real_step_usage_and_role_checks(self):
        msg = assistant('ses_1')
        msg['parts'].append(msg['parts'][-1])
        events = nt.message_events([msg, msg], 'ses_1', 'opencode-reviewer', 'provider/model/variant')
        self.assertEqual(len(events), 4)
        self.assertEqual(sum(e['part'].get('cost', 0) for e in events), .25)
        for mutation, error in [({'agent': 'build'}, 'AGENT_MODEL_MISMATCH'),
                                ({'modelID': 'fallback'}, 'AGENT_MODEL_MISMATCH'),
                                ({'sessionID': 'ses_other'}, 'SESSION_MISMATCH'),
                                ({'error': {'message': 'secret'}}, 'PROVIDER_ERROR'),
                                ({'time': {}}, 'INCOMPLETE_MESSAGE')]:
            bad = assistant('ses_1')
            bad['info'].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaisesRegex(nt.Failure, error):
                nt.message_events([bad], 'ses_1', 'opencode-reviewer', 'provider/model/variant')

    def test_v2_messages_validate_identity_completion_errors_and_usage_once(self):
        import copy
        message = {'id': 'msg_1', 'type': 'assistant', 'agent': 'opencode-worker',
                   'model': {'providerID': 'p', 'id': 'm'}, 'finish': 'stop',
                   'time': {'completed': 1}, 'content': [{'type': 'text', 'text': 'done'}],
                   'tokens': {'input': 4, 'output': 7}, 'cost': .25}
        idle = {'id': 'msg_idle', 'type': 'idle', 'outcome': 'succeeded'}
        events = nt.message_events([message, idle], 'ses_actual', 'opencode-worker', 'p/m')
        self.assertEqual([e['type'] for e in events], ['text', 'step_finish'])
        self.assertTrue(all(e['sessionID'] == 'ses_actual' for e in events))
        for patch, error in [({'agent': 'fallback'}, 'AGENT_MODEL_MISMATCH'),
                             ({'model': {'providerID': 'p', 'id': 'fallback'}}, 'AGENT_MODEL_MISMATCH'),
                             ({'time': {}}, 'INCOMPLETE_MESSAGE'),
                             ({'error': {'message': 'credential-secret'}}, 'PROVIDER_ERROR'),
                             ({'finish': 'length'}, 'PROVIDER_ERROR'),
                             ({'content': [{'type': 'tool', 'state': {'status': 'running'}}]}, 'TOOL_ERROR')]:
            bad = copy.deepcopy(message)
            bad.update(patch)
            with self.subTest(patch=patch), self.assertRaisesRegex(nt.Failure, error):
                nt.message_events([bad, idle], 'ses_actual', 'opencode-worker', 'p/m')
        with self.assertRaisesRegex(nt.Failure, 'INVALID_MESSAGES'):
            nt.message_events([message, message, idle], 'ses_actual', 'opencode-worker', 'p/m')
        with self.assertRaisesRegex(nt.Failure, 'PROVIDER_ERROR'):
            nt.message_events([message, dict(idle, outcome='failed')], 'ses_actual', 'opencode-worker', 'p/m')

    def test_v2_model_identity_accepts_observed_default_variant_and_metadata(self):
        for metadata in ({'variant': 'default'}, {'variant': 'default', 'label': 'display only'}):
            with self.subTest(metadata=metadata):
                message = {'id': 'msg_1', 'type': 'assistant', 'agent': 'opencode-worker',
                           'model': dict(providerID='openai', id='gpt-6.1-sol', **metadata),
                           'finish': 'stop', 'time': {'completed': 1},
                           'content': [{'type': 'text', 'text': 'done'}]}
                events = nt.message_events([message], 'ses_actual', 'opencode-worker',
                                           'openai/gpt-6.1-sol')
                self.assertEqual(events[0]['part']['text'], 'done')

    def test_v2_model_identity_rejects_substitution_and_malformed_models(self):
        models = [None, [], 'openai/gpt-6.1-sol', {},
                  {'providerID': 'other', 'id': 'gpt-6.1-sol', 'variant': 'default'},
                  {'providerID': 'openai', 'id': 'other', 'variant': 'default'},
                  {'providerID': 'openai'}, {'id': 'gpt-6.1-sol'}]
        for model in models:
            with self.subTest(model=model), self.assertRaisesRegex(
                    nt.Failure, '^NATIVE_AGENT_MODEL_MISMATCH$'):
                nt.message_events([{'id': 'msg_1', 'type': 'assistant',
                                   'agent': 'opencode-worker', 'model': model}],
                                  'ses_actual', 'opencode-worker', 'openai/gpt-6.1-sol')

    def test_v2_explicit_variant_identity_is_exact_without_new_cli_grammar(self):
        # Only the internal V2 validator accepts an expected Model.Ref dict.
        # Public provider/model strings retain the entire suffix as the model ID.
        self.assertEqual(nt.model_parts('provider/model/variant'),
                         {'providerID': 'provider', 'id': 'model/variant'})
        expected = {'providerID': 'openai', 'id': 'gpt-6.1-sol', 'variant': 'requested'}
        message = {'id': 'msg_1', 'type': 'assistant', 'agent': 'opencode-worker',
                   'model': dict(expected, label='display only'), 'finish': 'stop',
                   'time': {'completed': 1}, 'content': [{'type': 'text', 'text': 'done'}]}
        self.assertEqual(nt.v2_message_events([message], 'ses_actual', 'opencode-worker',
                                             expected)[0]['part']['text'], 'done')
        for variant in ('default', 'other', None, ''):
            message['model'] = dict(expected, variant=variant)
            with self.subTest(variant=variant), self.assertRaisesRegex(
                    nt.Failure, '^NATIVE_AGENT_MODEL_MISMATCH$'):
                nt.v2_message_events([message], 'ses_actual', 'opencode-worker', expected)
        del message['model']['variant']
        with self.assertRaisesRegex(nt.Failure, '^NATIVE_AGENT_MODEL_MISMATCH$'):
            nt.v2_message_events([message], 'ses_actual', 'opencode-worker', expected)

    def test_owned_server_retries_and_is_stopped_only_if_owned(self):
        processes = [mock.Mock(), mock.Mock()]
        processes[0].poll.return_value = 1
        processes[1].poll.return_value = None
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(nt.subprocess, 'Popen', side_effect=processes) as spawn, mock.patch.object(nt.API, 'request') as request:
            request.side_effect = [{'healthy': True}, {'id': 'ses_root'}]
            with nt.NativeTeam('/repo', temp) as team:
                self.assertEqual(team.parent_session_id, 'ses_root')
                self.assertEqual(spawn.call_count, 2)
                self.assertIn('--hostname', spawn.call_args.args[0])
                self.assertNotIn('credential', repr(spawn.call_args))
            processes[1].terminate.assert_called_once()
            processes[1].wait.assert_called_once_with(timeout=5)

    def test_unreachable_supplied_server_falls_back_once_and_keeps_real_parent(self):
        for failure in ('NATIVE_TRANSPORT_ERROR', 'NATIVE_TIMEOUT'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp, server() as (url, backend):
                supplied = 'http://localhost:4096'
                team = nt.NativeTeam('/different/repo', temp, server_url=supplied,
                                     parent_session_id='ses_parent', parent_directory='/home/parent')
                owned = mock.Mock()
                owned.poll.return_value = None
                real_spawn = subprocess.Popen
                real_request = nt.API.request
                supplied_calls = []

                def spawn(argv, **kwargs):
                    if argv[1:2] == ['serve']:
                        # Bind the simulated owned process to this isolated fixture backend.
                        team.server_url = url
                        return owned
                    return real_spawn(argv, **kwargs)

                def request(api, method, path, directory, *args, **kwargs):
                    if api.url == supplied:
                        supplied_calls.append((method, path, directory))
                        raise nt.Failure(failure)
                    return real_request(api, method, path, directory, *args, **kwargs)

                with mock.patch.object(nt.subprocess, 'Popen', side_effect=spawn) as calls, mock.patch.object(nt.API, 'request', new=request):
                    with team:
                        self.assertEqual(team.parent_session_id, 'ses_parent')
                        self.assertEqual(supplied_calls, [('GET', '/api/session/ses_parent', '/home/parent')])
                        self.assertIn(('GET', '/api/session/ses_parent', None, None), backend.calls)
                        cmd = team.command('reviewer', 'reviewer', 'provider/model', 'prompt', 2)
                        self.assertEqual(cmd[cmd.index('--server-url') + 1], url)
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        sid = team.children[-1]['session_id']
                        team.finish_child('reviewer', {'session_ids': [sid], 'process': {'exit_code': 0}})
                        snap = team.snapshot()
                        self.assertEqual(snap['requested_server_url'], supplied)
                        self.assertEqual(snap['server_url'], url)
                        self.assertTrue(snap['owns_server'])
                        self.assertEqual(snap['fallback_reason'], failure)
                        self.assertEqual(backend.sessions[sid]['parentID'], 'ses_parent')
                        self.assertEqual(backend.sessions[sid]['projectID'], 'different-git-project')
                        self.assertFalse(any(c[0] == 'POST' and c[1] == '/api/session' and
                                             'parentID' not in c[3] for c in backend.calls))
                    serve_calls = [c for c in calls.call_args_list if c.args[0][1:2] == ['serve']]
                    self.assertEqual(len(serve_calls), 1)
                owned.terminate.assert_called_once()
                owned.wait.assert_called_once_with(timeout=5)
                self.assertEqual(nt.API(url).request('GET', '/api/session/ses_parent', '/home/parent')['id'], 'ses_parent')

    def test_unreachable_fallback_never_creates_replacement_parent_or_retries_parent_failure(self):
        with tempfile.TemporaryDirectory() as temp, server() as (url, backend):
            supplied = 'http://localhost:4096'
            team = nt.NativeTeam('/repo', temp, server_url=supplied,
                                 parent_session_id='ses_missing', parent_directory='/parent')
            real_request = nt.API.request
            owned = mock.Mock()
            owned.poll.return_value = None

            def spawn(*args, **kwargs):
                team.server_url = url
                return owned

            def request(api, method, path, directory, *args, **kwargs):
                if api.url == supplied:
                    raise nt.Failure('NATIVE_TRANSPORT_ERROR')
                if path == '/api/session/ses_missing':
                    raise nt.Failure('NATIVE_HTTP_ERROR')
                return real_request(api, method, path, directory, *args, **kwargs)

            with mock.patch.object(nt.subprocess, 'Popen', side_effect=spawn) as calls, mock.patch.object(nt.API, 'request', new=request):
                with self.assertRaisesRegex(nt.Failure, '^NATIVE_HTTP_ERROR$'):
                    with team:
                        pass
            self.assertEqual(calls.call_count, 1)
            owned.terminate.assert_called_once()
            self.assertFalse(any(c[0] == 'POST' and c[1] == '/api/session' for c in backend.calls))
            self.assertEqual(team.parent_session_id, 'ses_missing')

    def test_permission_http_parent_mismatch_and_bad_responses_never_fall_back(self):
        cases = [nt.Failure('NATIVE_PERMISSION'), nt.Failure('NATIVE_HTTP_ERROR'),
                 nt.Failure('NATIVE_INVALID_RESPONSE'), {'id': 'ses_wrong'}]
        for response in cases:
            with self.subTest(response=response), tempfile.TemporaryDirectory() as temp:
                team = nt.NativeTeam('/repo', temp, server_url='http://localhost:4096',
                                     parent_session_id='ses_parent')
                with mock.patch.object(nt.API, 'request', side_effect=[response]), mock.patch.object(team, '_start_server') as start:
                    with self.assertRaises(nt.Failure):
                        with team:
                            pass
                    start.assert_not_called()

    def test_http_auth_and_missing_parent_responses_do_not_start_fallback(self):
        for status, expected in ((401, 'NATIVE_PERMISSION'), (403, 'NATIVE_PERMISSION'),
                                 (404, 'NATIVE_HTTP_ERROR')):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temp:
                opener = mock.Mock()
                opener.open.side_effect = nt.urllib.error.HTTPError(
                    'http://localhost:4096', status, 'private backend error', None, None)
                with mock.patch.object(nt.urllib.request, 'build_opener', return_value=opener), mock.patch.object(nt.NativeTeam, '_start_server') as start:
                    with self.assertRaisesRegex(nt.Failure, '^' + expected + '$'):
                        with nt.NativeTeam('/repo', temp, server_url='http://localhost:4096',
                                           parent_session_id='ses_parent'):
                            pass
                    start.assert_not_called()

    def test_only_network_failures_are_classified_as_unreachable_transport(self):
        api = nt.API('http://localhost:4096')
        for reason, expected in ((ConnectionRefusedError('private connection error'), 'NATIVE_TRANSPORT_ERROR'),
                                 (socket.timeout('private timeout'), 'NATIVE_TIMEOUT'),
                                 (ValueError('private protocol error'), 'NATIVE_HTTP_ERROR')):
            with self.subTest(reason=type(reason).__name__), mock.patch.object(
                    api.opener, 'open', side_effect=nt.urllib.error.URLError(reason)):
                with self.assertRaisesRegex(nt.Failure, '^' + expected + '$'):
                    api.request('GET', '/api/session/ses_parent', '/parent')
        response = mock.Mock()
        response.__enter__ = mock.Mock(return_value=response)
        response.__exit__ = mock.Mock(return_value=False)
        response.read1.side_effect = [b'not-json private response', b'']
        with mock.patch.object(api.opener, 'open', return_value=response):
            with self.assertRaisesRegex(nt.Failure, '^NATIVE_INVALID_RESPONSE$'):
                api.request('GET', '/api/session/ses_parent', '/parent')

    def test_existing_parent_without_server_starts_owned_transport(self):
        owned = mock.Mock()
        owned.poll.return_value = None
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(nt.subprocess, 'Popen', return_value=owned), mock.patch.object(nt.API, 'request') as request:
            request.side_effect = [{'version': '2.0.32'}, {'id': 'ses_parent', 'location': {'directory': '/parent'}}]
            with nt.NativeTeam('/repo', temp, parent_session_id='ses_parent', parent_directory='/parent') as team:
                self.assertEqual(request.call_args.args, ('GET', '/api/session/ses_parent', '/parent'))
                self.assertTrue(team.snapshot()['owns_server'])
                self.assertIsNone(team.snapshot()['requested_server_url'])
                self.assertIsNone(team.snapshot()['fallback_reason'])
            owned.terminate.assert_called_once()

    def test_attached_interactive_transport_metadata_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp, server() as (url, backend), mock.patch.object(nt.subprocess, 'Popen') as start:
            with nt.NativeTeam('/repo', temp, server_url=url, parent_session_id='ses_parent', parent_directory='/home/parent') as team:
                team.command('worker', 'worker', 'p/m', 'prompt', 1)
                snap = team.snapshot()
                self.assertEqual(snap['requested_server_url'], url)
                self.assertEqual(snap['server_url'], url)
                self.assertFalse(snap['owns_server'])
                self.assertIsNone(snap['fallback_reason'])
            start.assert_not_called()
            self.assertEqual(backend.abort_ids, [team.children[-1]['session_id']])
            self.assertEqual(nt.API(url).request('GET', '/api/session/ses_parent', '/repo')['id'], 'ses_parent')


if __name__ == '__main__':
    unittest.main()
