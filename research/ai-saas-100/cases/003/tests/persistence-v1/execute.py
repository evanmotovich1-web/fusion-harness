"""Snapshot case-003 sources, run bounded component checks, append raw receipts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

CASE = Path(__file__).resolve().parents[2]
ROOT = CASE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from receipt import receipt_template


def sha(data):
    return hashlib.sha256(data).hexdigest()


def reference(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha(path.read_bytes())}


def write_new(path, data):
    with path.open('xb') as stream:
        stream.write(data)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def snapshot():
    names = [
        'implementation/workflow.py', 'implementation/persistence.py',
        'implementation/demo_persistence.py', 'implementation/PERSISTENCE.md',
        'tests/persistence-v1/fixtures.json', 'tests/persistence-v1/run.py',
        'tests/persistence-v1/execute.py', 'tests/fixtures.json', 'tests/run.py',
        'tests/fixtures.repair-v1.json', 'tests/run_repair_v1.py',
    ]
    contents = {name: (CASE / name).read_bytes() for name in names}
    hashes = {name: sha(data) for name, data in contents.items()}
    bundle = sha(encoded(hashes))
    folder = CASE / 'implementation/source-history' / ('persistence-v1-' + bundle)
    folder.mkdir(exist_ok=True)
    artifacts = []
    for name, data in contents.items():
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != data:
                raise ValueError('Snapshot collision: ' + name)
        else:
            write_new(target, data)
        artifacts.append({'original_path': str((CASE / name).relative_to(ROOT)), **reference(target)})
    manifest = folder / 'manifest.json'
    body = encoded({'schema_version': 1, 'bundle_sha256': bundle, 'artifacts': artifacts,
                    'scope': 'Immutable source and fixture bytes used by local persistence tests'})
    if manifest.exists():
        if manifest.read_bytes() != body:
            raise ValueError('Snapshot manifest collision')
    else:
        write_new(manifest, body)
    return manifest, folder, hashes


def main():
    manifest, folder, hashes = snapshot()
    suite = json.loads((CASE / 'tests/persistence-v1/fixtures.json').read_text())
    jobs = [
        ('persistence', 'tests/persistence-v1/run.py', 'tests/persistence-v1/fixtures.json',
         [f['id'] for f in suite['normal_cases']] + suite['control_cases']),
        ('demo', 'implementation/demo_persistence.py', 'implementation/demo_persistence.py',
         ['synthetic-roundtrip-demo']),
        ('legacy', 'tests/run.py', 'tests/fixtures.json',
         [f['id'] for f in json.loads((CASE / 'tests/fixtures.json').read_text())['cases']]),
        ('repair', 'tests/run_repair_v1.py', 'tests/fixtures.repair-v1.json',
         [f['id'] for f in json.loads((CASE / 'tests/fixtures.repair-v1.json').read_text())['cases']]),
    ]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    checks = []
    for label, runner, fixtures, expected_ids in jobs:
        run_id = '003-persistence-v1-' + stamp + '-' + label
        command = [sys.executable, '-B', str(CASE / runner)]
        receipt = receipt_template('003', run_id)
        receipt.update(started_at=datetime.now(timezone.utc).isoformat(), command=command, cwd=str(ROOT),
                       implementation=reference(manifest), fixtures=reference(folder / fixtures),
                       input_bundle=reference(folder / fixtures),
                       input_bundle_kind='Builder-visible component fixture with evaluator answers, not a model input',
                       runtime={'python': platform.python_version(), 'platform': platform.system()},
                       configuration={'mode': 'synthetic_persistence_components', 'runner': reference(folder / runner),
                                      'executor': reference(folder / 'tests/persistence-v1/execute.py'),
                                      'timeout_seconds': 10, 'concurrency': 1, 'model_calls': 0,
                                      'fault_injection': label == 'persistence'},
                       execution_kind='real', product_acceptance=False, original_product_status='not_observed',
                       human_interventions=['Builder-authored exposed tests. Persistence suite includes two explicit I/O fault injections.'],
                       missing_capabilities=['Natural-language inference', 'Generic-model baseline', 'Independent hidden evaluation'])
        tick = time.monotonic()
        stdout, stderr = b'', b''
        try:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=10)
            stdout, stderr = result.stdout, result.stderr
            receipt.update(status='completed' if result.returncode == 0 else 'failed', exit_status=result.returncode)
            if result.returncode:
                receipt['errors'].append('Nonzero child exit: ' + str(result.returncode))
        except subprocess.TimeoutExpired as exc:
            stdout, stderr = exc.stdout or b'', exc.stderr or b''
            receipt.update(status='failed', exit_status=-1,
                           exit_status_note='Sentinel, child exit status not observed after subprocess.run timeout',
                           timeouts=[{'seconds': 10}], errors=['TimeoutExpired'])
        except OSError as exc:
            receipt.update(status='failed', exit_status=-1, execution_kind='unknown',
                           exit_status_note='Sentinel, process did not launch', errors=[str(exc)])
        elapsed = time.monotonic() - tick
        receipt['ended_at'] = datetime.now(timezone.utc).isoformat()
        receipt['latency'] = {'value': elapsed, 'unit': 'seconds', 'classification': 'measured',
                              'category': 'latency', 'assumptions': ['Full test subprocess, not product latency'],
                              'unknown_reason': None}
        for suffix, data in [('stdout.json', stdout), ('stderr.txt', stderr)]:
            path = CASE / 'receipts' / (run_id + '.' + suffix)
            write_new(path, data)
            receipt['outputs'].append(reference(path))
        valid = False
        try:
            output = json.loads(stdout)
            rows = output['results']
            ids = [row['test_id'] for row in rows]
            valid = len(ids) == len(set(ids)) and set(ids) == set(expected_ids)
            valid = valid and all(row['outcome'] == 'passed' for row in rows)
            receipt['test_results'] = [{'test_id': row['test_id'], 'outcome': row['outcome']} for row in rows]
        except (ValueError, KeyError, TypeError) as exc:
            receipt['errors'].append('Invalid child output: ' + str(exc))
        valid = valid and receipt['exit_status'] == 0 and not receipt['errors']
        receipt['component_check_passed'] = valid
        path = CASE / 'receipts' / (run_id + '.json')
        write_new(path, encoded(receipt))
        checks.append({'check': label, 'passed': valid, 'receipt': reference(path),
                       'passed_rows': sum(row['outcome'] == 'passed' for row in receipt['test_results']),
                       'total_rows': len(receipt['test_results'])})
    changed_sources = [name for name, digest in hashes.items() if sha((CASE / name).read_bytes()) != digest]
    historical = CASE / 'implementation/source-history/8d7f440f41e60d19228535762d96d64f2719d3cfc2aa4489aeac36ca634cc4d4/before-persistence-v1.json'
    preserved = json.loads(historical.read_text())['preexisting_files']
    changed_history = [name for name, digest in preserved.items()
                       if not (CASE / name).is_file() or sha((CASE / name).read_bytes()) != digest]
    summary = {'schema_version': 1, 'case_id': '003', 'task_scope': 'Synthetic persistence component only',
               'recorded_at': datetime.now(timezone.utc).isoformat(), 'checks': checks,
               'source_snapshot': reference(manifest), 'sources_changed_during_execution': changed_sources,
               'historical_files_changed': changed_history, 'preview_api_source_unchanged':
               sha((CASE / 'implementation/workflow.py').read_bytes()) ==
               '8d7f440f41e60d19228535762d96d64f2719d3cfc2aa4489aeac36ca634cc4d4',
               'inference_executed': False, 'product_acceptance': False,
               'status': 'passed' if all(c['passed'] for c in checks) and not changed_sources and not changed_history else 'failed'}
    path = CASE / 'receipts' / ('003-persistence-v1-' + stamp + '-summary.json')
    write_new(path, encoded(summary))
    print(json.dumps({'summary_path': str(path.relative_to(ROOT)), **summary}, indent=2))
    return 0 if summary['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
