"""Native OpenCode session transport. No CLI agent selection or credential files."""
import argparse
import base64
import copy
import errno
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


MAX_RESPONSE = 16 * 1024 * 1024
MAX_PROMPT = 2 * 1024 * 1024


class Failure(RuntimeError):
    """Only fixed, non-sensitive codes cross the transport boundary."""


def server_address(value):
    try:
        url = urllib.parse.urlsplit(value)
        host = url.hostname
        local = host == 'localhost' or ipaddress.ip_address(host).is_loopback
        _ = url.port  # Validate even when omitted (the HTTP scheme supplies a default).
        if (url.scheme not in ('http', 'https') or not local or url.username is not None
                or url.password is not None or url.path not in ('', '/') or url.query
                or url.fragment):
            raise ValueError()
    except (ValueError, TypeError):
        raise Failure('NATIVE_INVALID_SERVER') from None
    return value.rstrip('/')


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', value):
        raise Failure('NATIVE_INVALID_SESSION')
    return value


def model_parts(value):
    if not isinstance(value, str) or '/' not in value:
        raise Failure('NATIVE_INVALID_MODEL')
    provider, model = value.split('/', 1)
    if not provider or not model or any(c.isspace() or ord(c) < 32 for c in value):
        raise Failure('NATIVE_INVALID_MODEL')
    return {'providerID': provider, 'modelID': model}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class API:
    def __init__(self, server_url):
        self.url = server_address(server_url)
        # Ignore HTTP proxy environment and never forward Basic auth on redirects.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, method, path, directory, body=None, timeout=10):
        headers = {'Content-Type': 'application/json'}
        password = os.environ.get('OPENCODE_SERVER_PASSWORD')
        if password:
            username = os.environ.get('OPENCODE_SERVER_USERNAME', 'opencode')
            token = base64.b64encode((username + ':' + password).encode()).decode()
            headers['Authorization'] = 'Basic ' + token
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.url + path + '?' + urllib.parse.urlencode(
            {'directory': str(directory)}), data=data, headers=headers, method=method)
        try:
            deadline = time.monotonic() + timeout
            with self.opener.open(req, timeout=max(0.001, timeout)) as response:
                chunks, size = [], 0
                while True:
                    if time.monotonic() >= deadline:
                        raise Failure('NATIVE_TIMEOUT')
                    chunk = response.read1(min(65536, MAX_RESPONSE + 1 - size))
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_RESPONSE:
                        raise Failure('NATIVE_RESPONSE_LIMIT')
                    chunks.append(chunk)
                raw = b''.join(chunks)
            return json.loads(raw) if raw else None
        except Failure:
            raise
        except (TimeoutError, socket.timeout):
            raise Failure('NATIVE_TIMEOUT') from None
        except urllib.error.HTTPError as exc:
            code = 'NATIVE_PERMISSION' if exc.code in (401, 403) else 'NATIVE_HTTP_ERROR'
            exc.close()
            raise Failure(code) from None
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                raise Failure('NATIVE_TIMEOUT') from None
            if (isinstance(reason, (ConnectionError, socket.gaierror)) or
                    isinstance(reason, OSError) and reason.errno in (
                        errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ECONNREFUSED,
                        errno.ECONNRESET, errno.ECONNABORTED, errno.ETIMEDOUT)):
                raise Failure('NATIVE_TRANSPORT_ERROR') from None
            raise Failure('NATIVE_HTTP_ERROR') from None
        except (ConnectionError, socket.gaierror):
            raise Failure('NATIVE_TRANSPORT_ERROR') from None
        except ValueError:
            raise Failure('NATIVE_INVALID_RESPONSE') from None
        except (OSError, http.client.HTTPException):
            raise Failure('NATIVE_HTTP_ERROR') from None


class NativeTeam:
    def __init__(self, repo, folder, *, server_url=None, parent_session_id=None,
                 parent_directory=None):
        self.repo = str(Path(repo).resolve())
        self.folder = Path(folder)
        # OpenCode's instance scope is the actual caller directory, including its spelling.
        self.parent_directory = os.path.abspath(os.path.expanduser(str(parent_directory or repo)))
        self.server_url = server_address(server_url) if server_url else None
        self.requested_server_url = self.server_url
        self.owns_server = False
        self.fallback_reason = None
        self.parent_session_id = identity(parent_session_id) if parent_session_id else None
        self.children = []
        self.process = None
        self.api = None
        self.closed = False

    def __enter__(self):
        try:
            if self.server_url is None:
                self._start_server()
            self.api = API(self.server_url)
            if self.parent_session_id:
                try:
                    self._verify_parent()
                except Failure as exc:
                    if (not self.requested_server_url or self.owns_server or
                            str(exc) not in ('NATIVE_TRANSPORT_ERROR', 'NATIVE_TIMEOUT')):
                        raise
                    # Headless OpenCode can provide a non-listening SDK default URL.
                    # Use the same global DB through an owned transport, never a new parent.
                    self.fallback_reason = str(exc)
                    self._start_server()
                    self.api = API(self.server_url)
                    self._verify_parent()
            else:
                parent = self.api.request('POST', '/session', self.parent_directory,
                                          {'title': 'OpenCode Team · ' + self.folder.name})
                self.parent_session_id = identity(parent.get('id') if isinstance(parent, dict) else None)
            return self
        except BaseException:
            self.close()
            raise

    def _verify_parent(self):
        parent = self.api.request('GET', '/session/' + self.parent_session_id,
                                  self.parent_directory)
        if not isinstance(parent, dict) or parent.get('id') != self.parent_session_id:
            raise Failure('NATIVE_PARENT_MISMATCH')

    def _start_server(self):
        for _ in range(3):
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            self.server_url = f'http://127.0.0.1:{port}'
            try:
                self.process = subprocess.Popen(
                    ['opencode', 'serve', '--hostname', '127.0.0.1', '--port', str(port)],
                    cwd=self.repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True)
                self.owns_server = True
            except OSError:
                raise Failure('NATIVE_SERVER_START_FAILED') from None
            deadline = time.monotonic() + 8
            api = API(self.server_url)
            while time.monotonic() < deadline and self.process.poll() is None:
                try:
                    health = api.request('GET', '/global/health', self.repo, timeout=0.4)
                    if isinstance(health, dict) and health.get('healthy') is True:
                        return
                except Failure:
                    pass
                time.sleep(0.1)
            self._stop_server()
        raise Failure('NATIVE_SERVER_NOT_READY')

    def _stop_server(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            self.process = None

    def _child(self, role, label, model):
        if self.closed or self.api is None or not self.parent_session_id:
            raise Failure('NATIVE_TEAM_NOT_OPEN')
        value = self.api.request('POST', '/session', self.repo,
                                 {'parentID': self.parent_session_id,
                                  'title': f'{role.title()} · {label}'})
        sid = identity(value.get('id') if isinstance(value, dict) else None)
        if sid in {self.parent_session_id, *(c['session_id'] for c in self.children)}:
            raise Failure('NATIVE_SESSION_REUSED')
        child = {'role': role, 'label': label, 'session_id': sid,
                 'parent_id': self.parent_session_id, 'model': model, 'state': 'created'}
        self.children.append(child)
        try:
            if value.get('parentID') != self.parent_session_id:
                raise Failure('NATIVE_PARENT_MISMATCH')
            children = self.api.request('GET', '/session/' + self.parent_session_id + '/children',
                                        self.parent_directory)
            if not isinstance(children, list) or not any(
                    c.get('id') == sid and c.get('parentID') == self.parent_session_id
                    for c in children if isinstance(c, dict)):
                raise Failure('NATIVE_CHILD_NOT_ASSOCIATED')
        except BaseException:
            self._abort(child)
            raise
        return child

    def command(self, role, label, model, prompt, timeout):
        model_parts(model)
        if role not in ('worker', 'reviewer', 'planner', 'testdesigner'):
            raise Failure('NATIVE_INVALID_ROLE')
        if not math.isfinite(timeout) or timeout <= 0:
            raise Failure('NATIVE_INVALID_TIMEOUT')
        if not isinstance(prompt, str) or len(prompt.encode()) > MAX_PROMPT:
            raise Failure('NATIVE_PROMPT_LIMIT')
        child = self._child(role, label, model)
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, filename = tempfile.mkstemp(prefix='native-prompt-', suffix='.txt', dir=self.folder)
        with os.fdopen(fd, 'w') as stream:
            stream.write(prompt)
        child['state'] = 'running'
        return [sys.executable, str(Path(__file__).resolve()), 'invoke', '--server-url',
                self.server_url, '--session', child['session_id'], '--agent', 'opencode-' + role,
                '--model', model, '--repo', self.repo, '--prompt-file', filename,
                '--timeout', str(timeout)]

    def finish_child(self, label, stage):
        child = next((c for c in reversed(self.children) if c['label'] == label), None)
        if child is None:
            raise Failure('NATIVE_UNKNOWN_CHILD')
        process = stage.get('process', {})
        if (stage.get('session_ids') != [child['session_id']] or process.get('error')
                or process.get('exit_code') != 0 or stage.get('errors')):
            self._abort(child)
            child['state'] = 'failed'
            raise Failure('NATIVE_CHILD_FAILED')
        child['state'] = 'completed'

    def router_note(self, routing):
        # This is a code-owned receipt, never an assistant response or invented inference.
        method = routing.get('method', '')
        used_jev = isinstance(routing.get('jev'), dict) or routing.get('used_jev') is True
        jev = routing.get('jev') or {}
        child = self._child('router', 'Router · routing receipt (no chat inference)',
                            (routing.get('model_resolved') or jev.get('model_resolved') or
                             routing.get('model')) if used_jev else None)
        child['execution'] = 'jev' if used_jev else 'code'
        # Only public routing metadata, not arbitrary diagnostics/headers, enters chat.
        receipt = {k: routing[k] for k in ('status', 'selected_repo', 'method', 'question',
                                         'confidence', 'probabilities', 'model', 'usage', 'receipt_path',
                                         'model_requested', 'model_resolved', 'input_tokens',
                                         'output_tokens', 'elapsed_ms')
                   if k in routing and (k != 'model' or used_jev)}
        try:
            self.api.request('POST', '/session/' + child['session_id'] + '/message', self.repo,
                             {'noReply': True, 'parts': [{'type': 'text', 'text':
                              'Router routing receipt (code-owned; no chat inference):\n' +
                              json.dumps(receipt, ensure_ascii=False)}]})
            child['state'] = 'completed'
        except BaseException:
            self._abort(child)
            child['state'] = 'failed'
            raise
        return child['session_id']

    def _abort(self, child):
        try:
            result = self.api.request('POST', '/session/' + child['session_id'] + '/abort',
                                      self.repo, timeout=2)
            child['abort_sent'] = result is True
        except Failure:
            child['abort_sent'] = False
        if child['state'] != 'failed':
            child['state'] = 'aborted'

    def abort_active(self):
        for child in self.children:
            if child['state'] in ('created', 'running') or (
                    child['state'] in ('aborted', 'failed') and not child.get('abort_sent')):
                self._abort(child)

    def close(self):
        try:
            self.abort_active()
        finally:
            self._stop_server()
            self.closed = True

    def __exit__(self, *exc):
        self.close()

    def snapshot(self):
        return copy.deepcopy({'parent_session_id': self.parent_session_id,
                              'server_url': self.server_url,
                              'requested_server_url': self.requested_server_url,
                              'owns_server': self.owns_server,
                              'fallback_reason': self.fallback_reason,
                              'children': self.children})


def message_events(messages, session, agent, model):
    if not isinstance(messages, list):
        raise Failure('NATIVE_INVALID_MESSAGES')
    expected = model_parts(model)
    events, seen, assistants = [], set(), 0
    kinds = {'text': 'text', 'tool': 'tool_use', 'step-start': 'step_start',
             'step-finish': 'step_finish'}
    for message in messages:
        if not isinstance(message, dict) or not isinstance(message.get('info'), dict):
            raise Failure('NATIVE_INVALID_MESSAGES')
        info = message['info']
        if info.get('error'):
            raise Failure('NATIVE_PROVIDER_ERROR')
        if info.get('sessionID') != session:
            raise Failure('NATIVE_SESSION_MISMATCH')
        if info.get('role') != 'assistant':
            continue
        assistants += 1
        if info.get('agent') != agent or any(info.get(k) != v for k, v in expected.items()):
            raise Failure('NATIVE_AGENT_MODEL_MISMATCH')
        if not info.get('time', {}).get('completed'):
            raise Failure('NATIVE_INCOMPLETE_MESSAGE')
        if info.get('finish') in ('error', 'length', 'content-filter'):
            raise Failure('NATIVE_PROVIDER_ERROR')
        parts = message.get('parts')
        if not isinstance(parts, list):
            raise Failure('NATIVE_INVALID_MESSAGES')
        for part in parts:
            if not isinstance(part, dict) or part.get('sessionID') != session:
                raise Failure('NATIVE_SESSION_MISMATCH')
            if part.get('messageID') != info.get('id') or not part.get('id'):
                raise Failure('NATIVE_INVALID_MESSAGES')
            key = (info['id'], part['id'])
            if key in seen:
                continue
            seen.add(key)
            if part.get('type') == 'tool':
                state = part.get('state', {})
                if state.get('status') != 'completed' or state.get('error'):
                    raise Failure('NATIVE_TOOL_ERROR')
            kind = kinds.get(part.get('type'))
            if kind:
                events.append({'type': kind, 'sessionID': session, 'part': part})
    if not assistants or not any(e['type'] == 'text' and e['part'].get('text', '').strip()
                                 for e in events):
        raise Failure('NATIVE_EMPTY_RESPONSE')
    # Step usage comes only from persisted step-finish parts, never assistant totals.
    return events


def invoke(args):
    api = API(args.server_url)
    sid = identity(args.session)
    timeout = args.timeout
    if not math.isfinite(timeout) or timeout <= 0:
        raise Failure('NATIVE_INVALID_TIMEOUT')
    deadline = time.monotonic() + timeout

    def remaining():
        left = deadline - time.monotonic()
        if left <= 0:
            raise Failure('NATIVE_TIMEOUT')
        return left

    try:
        with Path(args.prompt_file).open('rb') as stream:
            raw = stream.read(MAX_PROMPT + 1)
        if len(raw) > MAX_PROMPT:
            raise Failure('NATIVE_PROMPT_LIMIT')
        response = api.request('POST', '/session/' + sid + '/message', args.repo,
                               {'agent': args.agent, 'model': model_parts(args.model),
                                'parts': [{'type': 'text', 'text': raw.decode()}]}, remaining())
        if isinstance(response, dict) and (response.get('error') or
                isinstance(response.get('info'), dict) and response['info'].get('error')):
            raise Failure('NATIVE_PROVIDER_ERROR')
        messages = api.request('GET', '/session/' + sid + '/message', args.repo,
                               timeout=remaining())
        for event in message_events(messages, sid, args.agent, args.model):
            print(json.dumps(event, ensure_ascii=False), flush=True)
    except BaseException:
        try:
            api.request('POST', '/session/' + sid + '/abort', args.repo, timeout=2)
        except Failure:
            pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['invoke'])
    for name in ('server-url', 'session', 'agent', 'model', 'repo', 'prompt-file'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--timeout', type=float, required=True)
    args = parser.parse_args(argv)

    def cancelled(signum, frame):
        raise KeyboardInterrupt()

    def expired(signum, frame):
        raise Failure('NATIVE_TIMEOUT')

    signal.signal(signal.SIGTERM, cancelled)
    # A wall deadline also covers slow-drip headers/bodies, not just socket inactivity.
    signal.signal(signal.SIGALRM, expired)
    if math.isfinite(args.timeout) and args.timeout > 0:
        signal.setitimer(signal.ITIMER_REAL, args.timeout)
    try:
        invoke(args)
        return 0
    except (KeyboardInterrupt, Exception) as exc:
        code = str(exc) if isinstance(exc, Failure) else (
            'NATIVE_CANCELLED' if isinstance(exc, KeyboardInterrupt) else 'NATIVE_INTERNAL_ERROR')
        print(json.dumps({'type': 'error', 'error': {'code': code}}), flush=True)
        return 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == '__main__':
    sys.exit(main())
