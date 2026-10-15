#!/usr/bin/env python3
"""Local subprocess protocol fixture. This is NOT fresh provider evidence."""
import json
import os
import pathlib
import subprocess
import sys
import time

mode = os.environ.get('BRIDGE_FIXTURE_MODE', 'success')
args = sys.argv[1:]
if '--dangerously-skip-permissions' in args or '--json-schema' in args:
    sys.exit(9)
assert args[args.index('--input-format') + 1] == 'stream-json'
assert args[args.index('--print') + 1] == ''
assert args[args.index('--agent') + 1] == 'host-model-bridge'
assert '--sandbox' in args
assert args[args.index('--log-file') + 1] == os.devnull
wire = json.loads(sys.stdin.buffer.readline().decode('utf-8'))
assert wire['event'] == 'user'
assert wire['message']['role'] == 'user'
envelope = json.loads(wire['message']['content'])
assert 'messages' in envelope and 'tools' in envelope
assert 'output_rules' in envelope
assert not any(m.get('content') in args for m in envelope['messages'] if isinstance(m.get('content'), str))
assert sys.stdin.buffer.read() == b''
if mode == 'replay':
    assert envelope['messages'][-1] == {'role':'tool','tool_call_id':'h1','content':'雪 café'}
if mode in ('sleep', 'native_tool'):
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    pathlib.Path(os.environ['BRIDGE_FIXTURE_PIDS']).write_text(json.dumps([os.getpid(), child.pid]))
    if mode == 'native_tool':
        print(json.dumps({'event':'step_update','step_update':{'step_type':'tool_call','state':'ACTIVE','name':'run_command'}}), flush=True)
    time.sleep(60)
if mode == 'overflow':
    sys.stdout.buffer.write(b'x' * 20000)
    sys.stdout.buffer.flush()
    time.sleep(60)
if mode == 'invalid_utf8':
    sys.stdout.buffer.write(b'\xff\n')
    sys.exit(0)
record = json.loads((pathlib.Path(__file__).resolve().parents[2] / 'native-no-schema-probe.json').read_text())
if mode == 'unicode':
    events = [json.loads(line) for line in record['stdout'].splitlines()]
    events[-1]['result']['response'] = json.dumps({'content':'雪 café 🧪','tool_calls':[]}, ensure_ascii=False)
    record['stdout'] = '\n'.join(json.dumps(e, ensure_ascii=False) for e in events) + '\n'
if mode == 'host_tool':
    events = [json.loads(line) for line in record['stdout'].splitlines()]
    events[-1]['result']['response'] = json.dumps({'content':'','tool_calls':[{'name':'lookup','arguments':'{"word":"雪"}'}]}, ensure_ascii=False)
    record['stdout'] = '\n'.join(json.dumps(e, ensure_ascii=False) for e in events) + '\n'
if mode == 'partial_success':
    sys.stdout.write(record['stdout'])
    sys.stdout.flush()
    time.sleep(60)
if mode == 'stderr':
    sys.stderr.write('timeout reached despite SUCCESS')
sys.stdout.write(record['stdout'])
sys.exit(7 if mode == 'nonzero' else 0)
