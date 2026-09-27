"""Exact-output, builder-visible CRM repair regressions. No inference or integration."""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

CASE = Path(__file__).resolve().parents[1]
FIXTURES = CASE / 'tests/fixtures.repair-v1.json'
AUDIT_ACTIVE = False
AUDIT_EFFECTS = []


def audit(event, args):
    # A regression guard for common Python side effects, not an OS sandbox.
    if not AUDIT_ACTIVE:
        return
    forbidden = event.startswith(('socket.', 'subprocess.', 'os.exec', 'os.spawn'))
    forbidden = forbidden or event in {
        'os.system', 'os.remove', 'os.rename', 'os.mkdir', 'os.rmdir',
        'os.link', 'os.symlink', 'os.truncate', 'os.chmod', 'os.chown',
        'os.chdir', 'os.putenv', 'os.unsetenv', 'os.utime',
    }
    if event == 'open':
        mode, flags = args[1], args[2]
        forbidden = forbidden or (
            isinstance(mode, str) and any(c in mode for c in 'wax+')
        ) or (
            isinstance(flags, int) and bool(flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
            ))
        )
    if forbidden:
        AUDIT_EFFECTS.append(event)
        raise AssertionError('External effect attempted: ' + event)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check_output(output, expected):
    require(isinstance(output, dict), 'Expected structured result')
    for key, value in expected.items():
        require(output.get(key) == value, 'Exact output mismatch: ' + key)
    require(output.get('inference_executed') is False, 'Unexpected inference')
    require(output.get('crm_written') is False, 'Unexpected CRM write')
    require(type(output.get('messages_sent')) is int and output['messages_sent'] == 0,
            'Unexpected message count')
    if expected['status'] == 'invalid_input':
        require(set(output) == {'status', 'error', 'inference_executed', 'crm_written', 'messages_sent'},
                'Invalid-input result contains unexpected fields')
    else:
        require(output.get('input_mutated') is False, 'Missing non-mutation declaration')
        require(output.get('central_workflow_status') == 'blocked', 'False central-workflow completion')
        require('error' not in output, 'Successful preview contains error')


def artifact(path):
    return {'path': str(path.relative_to(CASE)),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    global AUDIT_ACTIVE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=CASE / 'implementation/workflow.py')
    args = parser.parse_args()
    source = args.source.resolve()
    suite = json.loads(FIXTURES.read_text())
    ids = [f['id'] for f in suite['cases']]
    require(len(ids) == len(set(ids)), 'Duplicate fixture IDs')
    spec = importlib.util.spec_from_file_location('crm_repair_target', source)
    workflow = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(workflow)
    sys.addaudithook(audit)
    rows = []
    for fixture in suite['cases']:
        request = deepcopy(fixture['input'])
        before = deepcopy(request)
        AUDIT_EFFECTS.clear()
        tick = time.monotonic()
        row = {'test_id': fixture['id'], 'outcome': 'failed'}
        try:
            AUDIT_ACTIVE = True
            try:
                output = workflow.run(request)
            finally:
                AUDIT_ACTIVE = False
            row['output'] = output
            require(request == before, 'Input was mutated')
            require(not AUDIT_EFFECTS, 'External effect attempted')
            check_output(output, fixture['expected'])
            if fixture.get('check_detached_output'):
                detached = deepcopy(output)
                output['operations'][0]['after']['metadata']['tags'].append('changed by caller')
                require(request == before, 'Output aliases input')
                require(output['operations'][0]['before'] == detached['operations'][0]['before'],
                        'Before and after records alias each other')
                row['output'] = detached
            row['outcome'] = 'passed'
        except Exception as exc:
            row['error'] = type(exc).__name__ + ': ' + str(exc)
        finally:
            AUDIT_ACTIVE = False
            row['input_unchanged'] = request == before
            row['side_effect_attempts'] = list(AUDIT_EFFECTS)
            row['elapsed_seconds'] = time.monotonic() - tick
        rows.append(row)
    passed = sum(r['outcome'] == 'passed' for r in rows)
    print(json.dumps({
        'schema_version': 1, 'case_id': '003', 'suite_id': suite['suite_id'],
        'scope': suite['scope'], 'suite_type': suite['suite_type'], 'held_out': False,
        'implementation': artifact(source), 'fixtures': artifact(FIXTURES),
        'runner': artifact(Path(__file__).resolve()),
        'results': rows, 'passed': passed, 'total': len(rows),
        'product_acceptance': False, 'inference_executed': False,
        'side_effect_guard_scope': 'Common Python audit events during workflow calls, not OS containment',
    }, indent=2))
    return 0 if passed == len(rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
