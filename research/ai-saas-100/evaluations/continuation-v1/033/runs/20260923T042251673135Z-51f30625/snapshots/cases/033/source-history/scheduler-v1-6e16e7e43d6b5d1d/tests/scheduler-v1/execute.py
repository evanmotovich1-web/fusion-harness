"""Snapshot current scheduler sources and execute only the frozen copy in a bounded child."""
import datetime
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
CASE = HERE.parents[1]
ROOT = CASE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from receipt import receipt_template, unknown_metric
from validate import receipt as validate_receipt


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha(path)}


def load(path):
    return json.loads(path.read_text())


def write(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    assert sys.flags.optimize == 0
    for manifest in ['conventions-freeze.json', 'freeze.json']:
        for item in load(HERE / manifest)['artifacts']:
            assert sha(ROOT / item['path']) == item['sha256'], item['path']
    paths = [CASE / 'implementation/workflow.py', CASE / 'implementation/README.md',
             *[HERE / name for name in ['conventions.md', 'conventions-freeze.json', 'freeze.json', 'inputs.json', 'oracles.json',
                                       'checks.py', 'materialize.py', 'run.py', 'execute.py']]]
    active = [ref(path) for path in paths]
    identity = hashlib.sha256(json.dumps(active, sort_keys=True).encode()).hexdigest()
    snapshot = CASE / 'source-history' / ('scheduler-v1-' + identity[:16])
    members = []
    for path, descriptor in zip(paths, active):
        dest = snapshot / path.relative_to(CASE)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            with dest.open('xb') as stream:
                stream.write(path.read_bytes())
        assert sha(dest) == descriptor['sha256']
        members.append({'active_path': descriptor['path'], **ref(dest)})
    manifest = snapshot / 'source-bundle.json'
    if not manifest.exists():
        write(manifest, {'schema_version': 1, 'case_id': '033', 'created_at': now(), 'members': members})
    assert load(manifest)['members'] == members
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = CASE / 'receipts' / ('scheduler-v1-' + stamp)
    out.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, '-I', '-B', str(snapshot / 'tests/scheduler-v1/run.py')]
    started, tick = now(), time.monotonic()
    errors, timeouts = [], []
    try:
        process = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=20)
        stdout, stderr, code = process.stdout, process.stderr, process.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, code = exc.stdout or b'', exc.stderr or b'', -1
        errors.append('Scheduler suite exceeded 20 seconds')
        timeouts.append({'seconds': 20})
    except OSError as exc:
        stdout, stderr, code = b'', str(exc).encode(), -1
        errors.append(type(exc).__name__ + ': ' + str(exc))
    ended, elapsed = now(), time.monotonic() - tick
    for name, data in [('stdout.json', stdout), ('stderr.txt', stderr)]:
        with (out / name).open('xb') as stream:
            stream.write(data)
    rows, self_tests = [], []
    try:
        result = json.loads(stdout)
        rows, self_tests = result['results'], result['checker_self_tests']
        assert [r['test_id'] for r in rows] == [r['id'] for r in load(HERE / 'inputs.json')['cases']]
        assert len(self_tests) == 5 and all(r['outcome'] == 'passed' for r in rows + self_tests)
        assert result['source_sha256'] == sha(snapshot / 'implementation/workflow.py')
        assert result['input_bundle_sha256'] == sha(snapshot / 'tests/scheduler-v1/inputs.json')
        assert result['oracle_sha256'] == sha(snapshot / 'tests/scheduler-v1/oracles.json')
        assert result['checker_sha256'] == sha(snapshot / 'tests/scheduler-v1/checks.py')
        assert not result['side_effect_attempts']
    except (ValueError, KeyError, TypeError, AssertionError) as exc:
        errors.append(type(exc).__name__ + ': ' + str(exc))
    if code != 0:
        errors.append('Child exit status ' + str(code))
    preserved = all(sha(ROOT / item['path']) == item['sha256'] for item in load(HERE / 'conventions-freeze.json')['artifacts'])
    unchanged = all(sha(ROOT / member['active_path']) == member['sha256'] == sha(ROOT / member['path']) for member in members)
    if not preserved or not unchanged:
        errors.append('Historical or executed source hash changed')
    receipt = receipt_template('033', '033-scheduler-v1-' + stamp)
    receipt.update(status='completed' if not errors else 'failed', started_at=started, ended_at=ended, command=command, cwd=str(ROOT),
                   implementation=ref(snapshot / 'implementation/workflow.py'), fixtures=ref(snapshot / 'tests/scheduler-v1/oracles.json'),
                   input_bundle=ref(snapshot / 'tests/scheduler-v1/inputs.json'), outputs=[ref(out / 'stdout.json'), ref(out / 'stderr.txt')],
                   runtime={'python': platform.python_version(), 'platform': platform.platform()},
                   configuration={'mode': 'exposed_local_scheduler_regression', 'network': False, 'model_calls': 0,
                                  'timeout_seconds': 20, 'source_bundle': ref(manifest), 'runner': ref(snapshot / 'tests/scheduler-v1/run.py'),
                                  'checker': ref(snapshot / 'tests/scheduler-v1/checks.py'), 'orchestrator': ref(snapshot / 'tests/scheduler-v1/execute.py'),
                                  'interface_transformation': 'Direct schedule(request, node_limit=...) call, bound in runner source'},
                   exit_status=code, test_results=[{'test_id': r['test_id'], 'outcome': r['outcome']} for r in rows + self_tests],
                   quality=[unknown_metric('points', 'semantic_quality')], errors=errors, timeouts=timeouts,
                   missing_capabilities=['Generic-model comparison not executed', 'Hidden evaluation missing', 'Original product not observed'],
                   human_interventions=['Builder-visible fixtures and evaluator report. No hidden-suite claim.'],
                   execution_kind='real', inference_executed=False, product_acceptance=False, original_product_status='not_observed')
    receipt['latency'].update(value=elapsed, category='latency', classification='measured', unknown_reason=None)
    write(out / 'receipt.json', receipt)
    validate_receipt(receipt, ROOT)
    summary = {'schema_version': 1, 'task_id': '1.e', 'case_id': '033', 'status': 'passed' if not errors else 'failed',
               'receipt': ref(out / 'receipt.json'), 'source_bundle': ref(manifest),
               'passed': sum(r['outcome'] == 'passed' for r in rows), 'total': len(load(HERE / 'inputs.json')['cases']),
               'checker_self_tests_passed': sum(r['outcome'] == 'passed' for r in self_tests),
               'historical_files_preserved': preserved, 'executed_source_unchanged': unchanged,
               'product_acceptance': False, 'errors': errors, 'held_out': False, 'recorded_at': now()}
    write(out / 'validation.json', summary)
    print(json.dumps({'validation_path': str((out / 'validation.json').relative_to(ROOT)), **summary}, indent=2))
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
