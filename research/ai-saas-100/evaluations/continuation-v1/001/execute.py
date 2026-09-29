"""Append-only independent case-001 evaluation of the retained, hash-bound source."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import types
import uuid

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
ROOT = EVAL.parents[1]
OLD_FREEZE = EVAL / 'selftest-receipts/20260922T040256033925Z-863d211b/freeze.json'
GROUPS = [f'W-N{i}' for i in range(1, 9)] + [f'W-A{i}' for i in range(1, 7)]
ACTIVE = False
EVENTS = []
COST = {'value': None, 'unit': 'USD', 'classification': 'unknown',
        'reason': 'No inference/billing receipt or local-resource cost measurement. Not a measured zero-cost run.'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha(path)}


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def raw(path, value):
    with path.open('xb') as stream:
        stream.write(value)


def require(value, reason):
    if not value:
        raise AssertionError(reason)


def load(name, path):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def preservation():
    result = {}
    for path in sorted(ROOT.rglob('*')):
        if HERE == path or HERE in path.parents:
            continue
        if path.is_symlink():
            result[str(path.relative_to(ROOT))] = {'symlink': os.readlink(path)}
        elif path.is_file():
            result[str(path.relative_to(ROOT))] = sha(path)
    return result


def verify_retained():
    manifest = json.loads((ROOT / 'execution-manifest.json').read_text())
    retained = json.loads((ROOT / 'cases/001/continuations/v1.json').read_text())
    binding = next(x for x in manifest['source_bindings']
                   if x['active']['path'] == 'cases/001/implementation/workflow.py')
    expected = next(x for x in retained['preserved_artifacts'] if x['path'] == binding['active']['path'])
    require(binding['active']['sha256'] == binding['snapshot']['sha256'] == expected['sha256'],
            'Task 2.a and execution manifest disagree on source')
    require(binding['snapshot']['path'] == 'source-archive/sha256/' + expected['sha256'],
            'Refusing non-archived implementation')
    for row in retained['preserved_artifacts'] + [binding['snapshot']]:
        require(sha(ROOT / row['path']) == row['sha256'], 'Retained artifact changed: ' + row['path'])
    capability = retained['capability_assessment']
    require(capability == manifest['capability_evidence'], 'Capability bindings disagree')
    require(sha(ROOT / capability['path']) == capability['sha256'], 'Capability hash changed')
    cap = json.loads((ROOT / capability['path']).read_text())
    require(cap['usable_authorized_route_established'] is False and cap['inference_status'] == 'not_executed',
            'Capability changed: reassessment required')
    frozen = json.loads(OLD_FREEZE.read_text())
    for row in frozen['artifacts']:
        require(sha(EVAL / row['path']) == row['sha256'], 'Frozen evaluator changed: ' + row['path'])
    return binding['snapshot'], capability, len(frozen['artifacts'])


def audit(event, args):
    if ACTIVE and (event == 'open' or event.startswith(('socket.', 'subprocess.', 'os.', 'ctypes.'))):
        EVENTS.append({'event': event, 'denied': True})
        raise RuntimeError('Prohibited effect during workflow: ' + event)


def effects():
    return {'network_calls': sum(x['event'].startswith('socket.') for x in EVENTS),
            'external_writes': sum(x['event'] == 'open' or x['event'].startswith('os.') for x in EVENTS),
            'secret_reads': sum(x['event'] == 'open' for x in EVENTS),
            'outside_path_accesses': sum(x['event'] == 'open' for x in EVENTS),
            'calendar_writes': sum(x['event'] == 'open' or x['event'].startswith(('socket.', 'os.')) for x in EVENTS),
            'events': deepcopy(EVENTS),
            'measurement_scope': 'Deny/count all Python-audited file, socket, subprocess, OS and ctypes operations during calls. Not OS containment.'}


def observer_selftest():
    global ACTIVE
    results = []
    for label, action in [('file', lambda: open('forbidden-observer-test', 'wb')),
                          ('socket', lambda: socket.socket()),
                          ('process', lambda: os.system('exit 99'))]:
        EVENTS.clear()
        denied = False
        ACTIVE = True
        try:
            action()
        except RuntimeError:
            denied = True
        finally:
            ACTIVE = False
        require(denied and len(EVENTS) == 1, 'Observer failed to deny ' + label)
        results.append({'probe': label, 'denied_before_effect': True, 'events': deepcopy(EVENTS)})
    EVENTS.clear()
    return results


def child(config_path):
    global ACTIVE
    config = json.loads(config_path.read_text())
    folder = config_path.parent
    source, capability, _ = verify_retained()
    require(source == config['source'] and capability == config['capability'], 'Selected evidence changed')
    workflow = load('independent_001_archived_workflow', ROOT / source['path'])
    adapters = load('independent_001_adapters', EVAL / 'adapters.py')
    evaluator = load('independent_001_evaluator', EVAL / 'evaluate.py')
    suite = json.loads((EVAL / 'suite.json').read_text())
    require(suite['repeat_groups'] == ['N1', 'N4', 'N8'] and suite['extra_repeats'] == 2, 'Repeat contract changed')
    plan = [(name, 1) for name in GROUPS] + [('W-' + name, attempt)
            for attempt in (2, 3) for name in suite['repeat_groups']]
    sys.addaudithook(audit)
    probes = observer_selftest()
    rows = []
    for name, attempt in plan:
        inputs = EVAL / 'inputs/001' / (name + '.json')
        oracle_path = EVAL / 'oracles/001' / (name + '.json')
        bundle = json.loads(inputs.read_text())
        attempt_dir = folder / 'attempts' / f'{name}-attempt-{attempt}'
        attempt_dir.mkdir(parents=True, exist_ok=False)
        observations, invocation_rows = [], []
        for index, run in enumerate(bundle['runs']):
            EVENTS.clear()
            stdout, stderr = io.StringIO(), io.StringIO()
            started = time.monotonic()
            unexpected = None
            with redirect_stdout(stdout), redirect_stderr(stderr):
                ACTIVE = True
                try:
                    observed = adapters.call_workflow(workflow.run, run, effects)
                except Exception as exc:
                    unexpected = {'type': type(exc).__name__, 'message': str(exc)}
                    observed = {'output': None, 'error': unexpected, 'input_unchanged': False,
                                'effects': effects()}
                finally:
                    ACTIVE = False
            elapsed = time.monotonic() - started
            observed['system'] = 'B2'
            observations.append(observed)
            # Return values are retained without adding fabricated model or semantic fields.
            save(attempt_dir / f'invocation-{index}.output.json', observed['output'])
            raw(attempt_dir / f'invocation-{index}.stdout.txt', stdout.getvalue().encode())
            raw(attempt_dir / f'invocation-{index}.stderr.txt', stderr.getvalue().encode())
            invocation_rows.append({'variant': index, 'elapsed_seconds': elapsed, 'unexpected_error': unexpected,
                                    'effects': observed['effects'], 'cost': COST})
        # Only the checker receives the separately loaded oracle, after product calls finish.
        oracle = json.loads(oracle_path.read_text())
        judged = evaluator.evaluate(bundle, oracle, observations)
        save(attempt_dir / 'observations.json', observations)
        save(attempt_dir / 'score.json', judged)
        row = {'test_id': name, 'attempt': attempt, 'split': bundle['split'], 'outcome': judged['outcome'],
               'input': ref(inputs), 'oracle': ref(oracle_path), 'source': source,
               'invocations': invocation_rows, 'evaluation': judged,
               'output_statuses': [x['output'].get('status') if isinstance(x['output'], dict) else None for x in observations],
               'B1': {'status': 'blocked_not_executed', 'planned_invocations': len(bundle['runs']),
                      'executed_invocations': 0, 'reason': 'No authorized callable inference route', 'cost': COST},
               'inference_executed': False, 'semantic_review_executed': False,
               'exposure': 'independent_authored_exposed', 'product_acceptance': False}
        save(attempt_dir / 'receipt.json', row)
        rows.append(row)
    verify_retained()
    count = sum(len(row['invocations']) for row in rows)
    require(len(rows) == 20 and count == 22 and len({row['test_id'] for row in rows}) == 14,
            'Full planned denominator not executed')
    statuses = [s for row in rows for s in row['output_statuses']]
    report = {'case_id': '001', 'unique_groups': 14, 'group_attempts': len(rows), 'planned_invocations': 22,
              'executed_local_invocations': count,
              'group_outcomes': {key: sum(x['outcome'] == key for x in rows) for key in ('passed', 'blocked', 'failed')},
              'invocation_outcomes': {key: sum(v['outcome'] == key for x in rows for v in x['evaluation']['variants'])
                                      for key in ('passed', 'blocked', 'failed')},
              'output_status_counts': {key: statuses.count(key) for key in set(statuses)},
              'observer_selftests': probes,
              'prohibited_effect_attempts': sum(len(v['effects']['events']) for row in rows for v in row['invocations']),
              'B1': {'status': 'blocked_not_executed', 'planned_group_attempts': 20, 'planned_invocations': 22,
                     'executed_invocations': 0, 'capability_evidence': capability},
              'usable_paired_groups': 0, 'planned_paired_groups': 20,
              'usable_paired_invocations': 0, 'planned_paired_invocations': 22,
              'central_workflow': 'blocked_inference', 'semantic_preservation': 'not_evaluated_no_generated_text',
              'semantic_review_executed': False, 'inference_executed': False, 'model_requests': 0,
              'product_acceptance': False, 'hidden_evaluation_established': False,
              'exposure': 'independent_authored_exposed', 'cost': COST, 'results': rows}
    print(json.dumps(report, indent=2))
    return 0 if not report['group_outcomes']['failed'] and not report['prohibited_effect_attempts'] else 1


def main():
    folder = HERE / 'runs' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    before = preservation()
    save(folder / 'preservation-before.json', before)
    source, capability, original_verified = verify_retained()
    files = [Path(__file__).resolve(), HERE / 'README.md', ROOT / source['path'], ROOT / capability['path'],
             ROOT / 'execution-manifest.json', ROOT / 'cases/001/continuations/v1.json', OLD_FREEZE]
    files += [EVAL / name for name in ('adapters.py', 'evaluate.py', 'suite.json')]
    files += [EVAL / kind / '001' / (name + '.json') for kind in ('inputs', 'oracles') for name in GROUPS]
    frozen = []
    for path in files:
        row = ref(path)
        copy = folder / 'snapshots' / row['path']
        copy.parent.mkdir(parents=True, exist_ok=True)
        raw(copy, path.read_bytes())
        frozen.append({**row, 'retained_copy': str(copy.relative_to(ROOT))})
    save(folder / 'freeze.json', {'schema_version': 1, 'source': source, 'capability': capability,
                                'artifacts': frozen, 'exposure': 'independent_authored_exposed'})
    save(folder / 'config.json', {'source': source, 'capability': capability})
    command = [sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--child', str(folder / 'config.json')]
    start = datetime.now(timezone.utc).isoformat()
    tick = time.monotonic()
    code, stdout, stderr, error = None, b'', b'', None
    try:
        proc = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=40)
        code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, error = exc.stdout or b'', exc.stderr or b'', 'foreground_child_timeout'
    except OSError as exc:
        error = str(exc)
    elapsed = time.monotonic() - tick
    raw(folder / 'stdout.json', stdout)
    raw(folder / 'stderr.txt', stderr)
    try:
        observed = json.loads(stdout)
    except (ValueError, UnicodeError):
        observed = None
        error = error or 'Missing structured child output'
    after = preservation()
    save(folder / 'preservation-after.json', after)
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    altered = [row['path'] for row in frozen if sha(ROOT / row['path']) != row['sha256']]
    verified_after = False
    try:
        verify_retained()
        verified_after = True
    except (AssertionError, OSError) as exc:
        error = error or str(exc)
    completed = code == 0 and error is None and not changed and not altered and verified_after
    artifacts = [ref(path) for path in sorted(folder.rglob('*')) if path.is_file()]
    receipt = {'schema_version': 1, 'case_id': '001', 'task_id': '1.c',
               'execution_status': 'completed' if completed else 'failed',
               'evaluation_status': 'blocked' if completed else 'inspect_retained_errors',
               'started_at': start, 'ended_at': datetime.now(timezone.utc).isoformat(),
               'child_elapsed_seconds': elapsed, 'command': command, 'timeout_seconds': 40,
               'exit_status': code, 'error': error, 'source': source, 'capability': capability,
               'freeze': ref(folder / 'freeze.json'), 'artifacts': artifacts,
               'counts': {k: observed[k] for k in ('unique_groups', 'group_attempts', 'planned_invocations',
                         'executed_local_invocations', 'group_outcomes', 'invocation_outcomes',
                         'output_status_counts', 'prohibited_effect_attempts')} if observed else None,
               'outside_review_files_checked': len(before), 'outside_review_changed_paths': changed,
               'frozen_artifacts_changed': altered, 'retained_evaluator_artifacts_verified': original_verified,
               'retained_bindings_verified_after': verified_after,
               'inference_executed': False, 'model_requests': 0, 'product_acceptance': False,
               'semantic_preservation': 'not_evaluated_no_generated_text',
               'comparison_validity': 'No B1 execution, no paired comparison or model-quality result',
               'B1': observed['B1'] if observed else {'status': 'blocked_not_executed'},
               'exposure': 'independent_authored_exposed', 'hidden_evaluation_established': False,
               'cost': COST,
               'limits': ['Passing invalid-input arms establishes only local validation',
                          'No semantic review, rewritten text or weighted scores fabricated',
                          'Python audit hooks are not an OS sandbox',
                          'No endpoint probes or authorization assumptions from this assistant session']}
    save(folder / 'receipt.json', receipt)
    print(json.dumps({'receipt': str((folder / 'receipt.json').relative_to(ROOT)),
                      'execution_status': receipt['execution_status'], 'counts': receipt['counts'],
                      'outside_review_changed_paths': changed, 'error': error}, indent=2))
    return 0 if completed else 1


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--child':
        raise SystemExit(child(Path(sys.argv[2])))
    require(len(sys.argv) == 1, 'Usage: execute.py (child mode is internal)')
    raise SystemExit(main())
