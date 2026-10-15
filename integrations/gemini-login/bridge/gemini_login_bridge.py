"""Official Antigravity CLI inference bridge; host runtimes own all tools."""
from __future__ import annotations

import json
import os
import pathlib
import selectors
import signal
import subprocess
import sys
import threading
import tempfile
import time
import math
import re
import uuid

DEFAULT_COMMAND = '/Applications/Gemini.app/Contents/Helpers/agy'
MODELS = ('gemini-4-argon', 'gemini-3.8-flash')
MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
OUTPUT_RULES = (
    'Return exactly one JSON object, no fences or prose outside it: '
    '{"content":"text", "tool_calls":[{"name":"declared host tool", "arguments":"JSON object encoded as a string"}]}. '
    'Both keys are required; no extra keys. Use an empty tool_calls array for an answer. '
    'Never invoke native tools; host tool calls are output only. Follow tool_choice. '
    'The host executes calls with its existing permissions and supplies tool results in messages. '
    'Do not invent results. Obey the supplied conversation system/developer instructions.'
)


def prepare_request(request: dict) -> tuple[dict, str]:
    if not isinstance(request, dict) or request.get('model') not in MODELS:
        raise BridgeError('Unsupported exact model; use gemini-4-argon or gemini-3.8-flash')
    effort = request.get('reasoning_effort') or 'high'
    if effort not in ('low', 'medium', 'high', 'xhigh', 'max'):
        raise BridgeError('Unsupported reasoning effort')
    timeout = request.get('timeout_seconds', 180)
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 600:
        raise BridgeError('timeout_seconds must be finite and between 0 and 600')
    messages = request.get('messages')
    if not isinstance(messages, list) or not messages:
        raise BridgeError('Nonempty messages required')
    for message in messages:
        if not isinstance(message, dict) or message.get('role') not in ('system', 'developer', 'user', 'assistant', 'tool'):
            raise BridgeError('Invalid message role')
        content = message.get('content')
        if isinstance(content, list):
            if any(not isinstance(part, dict) or set(part) != {'type', 'text'} or part.get('type') != 'text' or not isinstance(part.get('text'), str) for part in content):
                raise BridgeError('Text-only bridge: image, audio, file and other content are unsupported')
        elif not isinstance(content, str) and not (content is None and message['role'] == 'assistant' and message.get('tool_calls')):
            raise BridgeError('Text message content required')
        if message['role'] == 'tool' and (not isinstance(message.get('tool_call_id'), str) or not message['tool_call_id']):
            raise BridgeError('Host tool result requires tool_call_id')
    tools = request.get('tools') or []
    if not isinstance(tools, list):
        raise BridgeError('Tools must be a list')
    declared = set()
    for tool in tools:
        if not isinstance(tool, dict) or tool.get('type') != 'function' or not isinstance(tool.get('function'), dict):
            raise BridgeError('Only declared OpenAI function tools are supported')
        function = tool['function']
        name = function.get('name')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.:-]{0,127}', name) or name in declared or not isinstance(function.get('parameters', {}), dict):
            raise BridgeError('Invalid or duplicate host tool definition')
        declared.add(name)
    choice = request.get('tool_choice') or 'auto'
    if isinstance(choice, dict):
        if set(choice) != {'type', 'function'} or choice.get('type') != 'function' or not isinstance(choice.get('function'), dict) or set(choice['function']) != {'name'} or choice['function']['name'] not in declared:
            raise BridgeError('Invalid or undeclared tool_choice')
    elif choice not in ('auto', 'none', 'required') or (choice == 'required' and not tools):
        raise BridgeError('Invalid tool_choice')
    prepared = {'model': request['model'], 'messages': messages, 'tools': tools, 'reasoning_effort': effort, 'timeout_seconds': timeout, 'tool_choice': choice}
    try:
        prompt = json.dumps({'messages': messages, 'tools': tools, 'tool_choice': choice, 'output_rules': OUTPUT_RULES}, ensure_ascii=False, allow_nan=False)
        if len(prompt.encode('utf-8')) > MAX_REQUEST_BYTES:
            raise BridgeError('Request exceeds bridge byte limit')
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise BridgeError('Request is not bounded valid UTF-8 JSON') from None
    return prepared, prompt


def _terminate_owned_group(process):
    """Signal only the new session owned by this invocation, then reap its leader."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=0.3)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=2)
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            stream.close()


def _run_native(argv, wire, request, *, cancel_event=None, cancel_check=None, parent_process_group=False):
    deadline = time.monotonic() + request['timeout_seconds']
    output = bytearray()
    pending = bytearray()
    sent = 0
    process = None
    directory = os.environ.get('TMPDIR') or str(pathlib.Path(__file__).resolve().parent)
    try:
        with tempfile.TemporaryDirectory(prefix='gemini-login-', dir=directory) as cwd:
            try:
                process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=not parent_process_group, cwd=cwd)
            except (OSError, ValueError):
                raise BridgeError('Cannot start configured official CLI') from None
            try:
                with selectors.DefaultSelector() as selector:
                    for stream, event, name in ((process.stdin, selectors.EVENT_WRITE, 'stdin'), (process.stdout, selectors.EVENT_READ, 'stdout'), (process.stderr, selectors.EVENT_READ, 'stderr')):
                        os.set_blocking(stream.fileno(), False)
                        selector.register(stream, event, name)
                    while selector.get_map() or process.poll() is None:
                        if (cancel_event is not None and cancel_event.is_set()) or (cancel_check is not None and cancel_check()):
                            raise BridgeCancelledError('Inference cancelled; no retry performed')
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise BridgeTimeoutError('Inference timed out; partial output discarded; no retry performed')
                        for key, _ in selector.select(min(0.05, remaining)):
                            if key.data == 'stdin':
                                try:
                                    sent += os.write(key.fd, wire[sent:sent + 65536])
                                except BrokenPipeError:
                                    raise BridgeError('Native CLI closed request input early') from None
                                if sent == len(wire):
                                    selector.unregister(key.fileobj)
                                    key.fileobj.close()
                                continue
                            data = os.read(key.fd, 65536)
                            if not data:
                                selector.unregister(key.fileobj)
                                continue
                            if key.data == 'stderr':
                                raise BridgeError('Native CLI emitted stderr; output discarded; no retry performed')
                            output.extend(data)
                            if len(output) > MAX_OUTPUT_BYTES:
                                raise BridgeError('Native output exceeds byte limit')
                            pending.extend(data)
                            while b'\n' in pending:
                                line, _, rest = pending.partition(b'\n')
                                pending[:] = rest
                                if line.strip():
                                    event = _validate_event(_json(line.decode('utf-8')))
                                    if event['event'] == 'init' and (event['init'].get('model') != request['model'] or event['init'].get('agent') != 'host-model-bridge'):
                                        raise BridgeError('Native model or agent differs from request')
                    return output.decode('utf-8'), '', process.returncode
            except BaseException:
                if parent_process_group:
                    # Pi owns this detached group. Kill it, including this CLI,
                    # rather than returning while any native descendant survives.
                    os.killpg(os.getpgrp(), signal.SIGTERM)
                    try:
                        process.wait(timeout=0.3)
                    except subprocess.TimeoutExpired:
                        pass
                    os.killpg(os.getpgrp(), signal.SIGKILL)
                raise
            finally:
                if not parent_process_group:
                    _terminate_owned_group(process)
                else:
                    process.wait(timeout=2)
                    for stream in (process.stdin, process.stdout, process.stderr):
                        stream.close()
    except UnicodeError:
        raise BridgeError('Native output is not valid UTF-8') from None


def complete(request: dict, *, command=None, cancel_event=None, cancel_check=None, _parent_process_group=False) -> dict:
    """One inference only; never executes a host tool or retries a paid model turn.

    command is an operator-controlled executable (or argv prefix for local tests),
    never a field accepted from the model/request. Payloads travel only on stdin.
    """
    prepared, prompt = prepare_request(request)
    if _parent_process_group and os.getpgrp() != os.getpid():
        raise BridgeError('Parent-managed CLI must be a detached process-group leader')
    command = command or os.environ.get('GEMINI_LOGIN_CLI') or DEFAULT_COMMAND
    prefix = list(command) if isinstance(command, (list, tuple)) else [command]
    if not prefix or any(not isinstance(arg, str) or not arg or arg.startswith('-') for arg in prefix):
        raise BridgeError('Invalid CLI executable prefix')
    if (cancel_event is not None and cancel_event.is_set()) or (cancel_check is not None and cancel_check()):
        raise BridgeCancelledError('Inference cancelled before spawn')
    argv = prefix + ['--agent', 'host-model-bridge', '--model', prepared['model'], '--effort', prepared['reasoning_effort'], '--sandbox', '--disable-slash-commands', '--log-file', os.devnull, '--output-format', 'stream-json', '--input-format', 'stream-json', '--print', '']
    wire = (json.dumps({'event': 'user', 'message': {'role': 'user', 'content': prompt}}, ensure_ascii=False) + '\n').encode('utf-8')
    out, err, code = _run_native(argv, wire, prepared, cancel_event=cancel_event, cancel_check=cancel_check, parent_process_group=_parent_process_group)
    return parse_native_output(out, err, code, prepared)


class BridgeError(ValueError):
    """Safe, prompt-free error suitable for host runtimes."""


class BridgeTimeoutError(BridgeError):
    """The single native turn exceeded its wall-clock deadline."""


class BridgeCancelledError(BridgeError):
    """The host cancelled inference; all owned subprocesses are stopped."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BridgeError('Duplicate JSON key')
        result[key] = value
    return result


def _reject_constant(value):
    raise BridgeError('Non-finite JSON number')


def _json(text):
    if not isinstance(text, str):
        raise BridgeError('Expected JSON text')
    try:
        return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (ValueError, TypeError, RecursionError):
        raise BridgeError('Invalid strict JSON') from None


def _validate_event(event):
    if not isinstance(event, dict):
        raise BridgeError('Invalid native event')
    kind = event.get('event')
    if kind not in ('init', 'step_update', 'result'):
        raise BridgeError('Unexpected native event; tools are forbidden')
    if not isinstance(event.get(kind), dict):
        raise BridgeError('Invalid native event payload')
    if kind == 'step_update':
        step = event['step_update']
        if step.get('step_type') not in ('user_input', 'agent_response'):
            raise BridgeError('Native tool or unknown step is forbidden')
        if step.get('state') not in ('ACTIVE', 'DONE'):
            raise BridgeError('Incomplete or failed native step')
    return event


def parse_native_output(stdout: str, stderr: str, returncode: int, request: dict) -> dict:
    if returncode != 0 or stderr.strip():
        raise BridgeError('Native process failed or emitted stderr; no retry performed')
    events = [_validate_event(_json(line)) for line in stdout.splitlines() if line.strip()]
    if len(events) < 2 or events[0]['event'] != 'init' or events[-1]['event'] != 'result':
        raise BridgeError('Incomplete native response')
    if sum(e['event'] == 'init' for e in events) != 1 or sum(e['event'] == 'result' for e in events) != 1:
        raise BridgeError('Multiple native turns or initializations')
    init = events[0]
    if init['init'].get('model') != request['model'] or init['init'].get('agent') != 'host-model-bridge':
        raise BridgeError('Native model or agent differs from request')
    conversation = init.get('conversation_id')
    if not isinstance(conversation, str) or not conversation:
        raise BridgeError('Missing native conversation ID')
    states = {}
    for event in events[1:-1]:
        step = event['step_update']
        if step.get('conversation_id') != conversation or type(step.get('step_index')) is not int:
            raise BridgeError('Invalid native step identity')
        states[step['step_index']] = step['state']
    if any(state != 'DONE' for state in states.values()):
        raise BridgeError('Native response contains unfinished steps')
    result = events[-1]['result']
    if result.get('conversation_id') != conversation or result.get('status') != 'SUCCESS' or result.get('num_turns') != 1 or result.get('error'):
        raise BridgeError('Native turn was not a single complete success')
    answer = _json(result.get('response'))
    if not isinstance(answer, dict) or set(answer) != {'content', 'tool_calls'} or not isinstance(answer['content'], str) or not isinstance(answer['tool_calls'], list):
        raise BridgeError('Invalid host response shape')
    if not answer['content'].strip() and not answer['tool_calls']:
        raise BridgeError('Empty host response')
    declared = {tool['function']['name'] for tool in request.get('tools', [])}
    calls = []
    for call in answer['tool_calls']:
        if not isinstance(call, dict) or set(call) != {'name', 'arguments'} or not isinstance(call['name'], str) or call['name'] not in declared:
            raise BridgeError('Undeclared or malformed host tool')
        if not isinstance(_json(call['arguments']), dict):
            raise BridgeError('Host tool arguments must encode an object')
        calls.append({'id': 'agy_call_' + uuid.uuid4().hex, 'type': 'function', 'function': {'name': call['name'], 'arguments': call['arguments']}})
    choice = request.get('tool_choice', 'auto')
    if (choice == 'none' and calls) or (choice == 'required' and not calls):
        raise BridgeError('Host tool choice was not respected')
    if isinstance(choice, dict) and (not calls or any(call['function']['name'] != choice['function']['name'] for call in calls)):
        raise BridgeError('Requested host tool was not respected')
    usage = result.get('usage')
    if not isinstance(usage, dict) or any(type(usage.get(key)) is not int or usage[key] < 0 for key in ('input_tokens', 'output_tokens', 'total_tokens', 'cache_read_tokens', 'thinking_tokens')):
        raise BridgeError('Invalid native usage')
    return {
        'model': init['init']['model'],
        'content': answer['content'],
        'tool_calls': calls,
        'usage': {
            # Native input/total counters exclude cache-read tokens; OpenAI
            # prompt/total counters include them. Keep the native counters intact.
            'prompt_tokens': usage['input_tokens'] + usage['cache_read_tokens'],
            'completion_tokens': usage['output_tokens'],
            'total_tokens': usage['total_tokens'] + usage['cache_read_tokens'],
            'prompt_tokens_details': {'cached_tokens': usage['cache_read_tokens']},
            'completion_tokens_details': {'reasoning_tokens': usage['thinking_tokens']},
        },
        'raw_usage': usage,
        'conversation_id': result['conversation_id'],
    }


def main() -> int:
    """Read exactly one bounded JSON request; stdout is success JSON only."""
    cancelled = threading.Event()
    old_handlers = {}
    for signum in (signal.SIGTERM, signal.SIGINT):
        old_handlers[signum] = signal.signal(signum, lambda _sig, _frame: cancelled.set())
    try:
        if len(sys.argv) != 1:
            raise BridgeError('Bridge accepts request JSON on stdin only')
        data = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(data) > MAX_REQUEST_BYTES:
            raise BridgeError('Request exceeds bridge byte limit')
        response = complete(_json(data.decode('utf-8')), cancel_event=cancelled, _parent_process_group=os.environ.get('GEMINI_LOGIN_PARENT_PROCESS_GROUP') == '1')
        sys.stdout.write(json.dumps(response, ensure_ascii=False, allow_nan=False) + '\n')
        return 0
    except BridgeCancelledError as exc:
        sys.stderr.write(str(exc) + '\n')
        return 130
    except BridgeError as exc:
        sys.stderr.write(str(exc) + '\n')
        return 2
    except (UnicodeError, OSError):
        sys.stderr.write('Local bridge I/O failed; no response or retry\n')
        return 2
    except Exception:
        sys.stderr.write('Unexpected local bridge failure; no response or retry\n')
        return 2
    finally:
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)


if __name__ == '__main__':
    raise SystemExit(main())
