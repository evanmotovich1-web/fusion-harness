"""Minimal OpenAI-shaped client over the shared inference-only CLI bridge."""
from __future__ import annotations

import importlib.util
import os
import threading
from pathlib import Path
from types import SimpleNamespace


def _load_bridge(path):
    candidate = Path(path).expanduser() if path else Path(__file__).resolve().parent.parent / 'gemini_login_bridge.py'
    if not path and not candidate.is_file():
        candidate = Path.home() / '.local/share/gemini-login-bridge/gemini_login_bridge.py'
    if not candidate.is_file():
        raise RuntimeError('Shared Gemini login bridge is missing; provider not installed completely')
    spec = importlib.util.spec_from_file_location('_hermes_gemini_login_bridge', candidate)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _namespace(value):
    if isinstance(value, dict):
        return SimpleNamespace(**{key:_namespace(item) for key,item in value.items()})
    if isinstance(value, list):
        return [_namespace(item) for item in value]
    return value


class GeminiLoginClient:
    def __init__(self, **kwargs):
        self.command = kwargs.get('command') or os.environ.get('GEMINI_LOGIN_CLI') or '/Applications/Gemini.app/Contents/Helpers/agy'
        self.bridge_path = kwargs.get('bridge_path') or os.environ.get('HERMES_GEMINI_LOGIN_BRIDGE')
        timeout = kwargs.get('timeout', 180)
        self.timeout = timeout if isinstance(timeout, (int,float)) else (getattr(timeout, 'read', None) or 180)
        self._closed = False
        self._lock = threading.Lock()
        self._active = set()
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        if self._closed:
            raise RuntimeError('Gemini login client is closed')
        bridge = _load_bridge(self.bridge_path)
        request = {key:kwargs[key] for key in ('model','messages','tools','reasoning_effort','tool_choice') if key in kwargs}
        request['timeout_seconds'] = kwargs.get('timeout_seconds', self.timeout)
        cancelled = threading.Event()
        from tools.interrupt import is_interrupted
        with self._lock:
            if self._closed:
                raise RuntimeError('Gemini login client is closed')
            self._active.add(cancelled)
        try:
            result = bridge.complete(request, command=self.command, cancel_event=cancelled, cancel_check=is_interrupted)
            if cancelled.is_set() or is_interrupted():
                raise bridge.BridgeCancelledError('Inference cancelled before delivery')
        finally:
            with self._lock:
                self._active.discard(cancelled)
        message = _namespace({'role':'assistant','content':result['content'] or None,'tool_calls':result['tool_calls'] or None,'refusal':None,'reasoning_content':None})
        completion = SimpleNamespace(
            id='agy_' + result['conversation_id'], object='chat.completion', model=result['model'],
            choices=[SimpleNamespace(index=0, message=message, finish_reason='tool_calls' if result['tool_calls'] else 'stop', logprobs=None)],
            usage=_namespace(result['usage']), raw_usage=result['raw_usage'], conversation_id=result['conversation_id'],
        )
        if kwargs.get('stream'):
            from agent.acp_openai_bridge import completion_to_stream_chunks
            completion = completion_to_stream_chunks(completion)
        if cancelled.is_set() or is_interrupted() or self._closed:
            raise bridge.BridgeCancelledError('Inference cancelled before delivery')
        return completion

    def cancel(self):
        with self._lock:
            for event in self._active:
                event.set()

    def close(self):
        with self._lock:
            self._closed = True
            for event in self._active:
                event.set()
