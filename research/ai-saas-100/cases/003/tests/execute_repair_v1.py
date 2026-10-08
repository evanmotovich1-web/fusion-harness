"""Run case-003-only repair checks and append source-bound execution receipts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

CASE = Path(__file__).resolve().parents[1]
ROOT = CASE.parents[1]
HISTORICAL_SHA = '71cbff3059ea041d9e1920dd7767c827ae0b382d13341b6ca033826d43b87135'
HISTORY = CASE / 'implementation/source-history' / HISTORICAL_SHA
sys.path.insert(0, str(ROOT / 'tools'))
from receipt import receipt_template


def reference(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    jobs = [
        ('historical-counterexamples', CASE / 'tests/run_repair_v1.py',
         HISTORY / 'workflow.py', CASE / 'tests/fixtures.repair-v1.json', 1),
        ('legacy-regression', CASE / 'tests/run.py',
         CASE / 'implementation/workflow.py', CASE / 'tests/fixtures.json', 0),
        ('repair-regression', CASE / 'tests/run_repair_v1.py',
         CASE / 'implementation/workflow.py', CASE / 'tests/fixtures.repair-v1.json', 0),
    ]
    summaries = []
    for name, runner, source, fixtures, expected_exit in jobs:
        run_id = '003-repair-v1-' + stamp + '-' + name
        command = [sys.executable, '-B', str(runner)]
        if name == 'historical-counterexamples':
            command += ['--source', str(source)]
        record = receipt_template('003', run_id)
        record.update(command=command, cwd=str(ROOT), started_at=datetime.now(timezone.utc).isoformat(),
                      implementation=reference(source), fixtures=reference(fixtures),
                      input_bundle=reference(fixtures), execution_kind='real',
                      configuration={'mode': 'local_partial_regression', 'model_calls': 0,
                                     'timeout_seconds': 15, 'concurrency': 1,
                                     'runner': reference(runner), 'executor': reference(Path(__file__).resolve())},
                      runtime={'python': platform.python_version(), 'platform': platform.system()},
                      product_acceptance=False, original_product_status='not_observed',
                      human_interventions=['Builder-visible repair regressions, not held-out evaluation'],
                      missing_capabilities=['No inference, baseline, or central CRM workflow execution'],
                      expected_exit_status=expected_exit)
        tick = time.monotonic()
        stdout, stderr = '', ''
        try:
            process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=15)
            stdout, stderr = process.stdout, process.stderr
            record['exit_status'] = process.returncode
            record['status'] = 'completed' if process.returncode == 0 else 'failed'
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ''
            stderr = exc.stderr or ''
            if isinstance(stdout, bytes):
                stdout = stdout.decode('utf-8', errors='replace')
            if isinstance(stderr, bytes):
                stderr = stderr.decode('utf-8', errors='replace')
            record.update(status='failed', timeouts=[{'seconds': 15}])
            record['errors'].append('TimeoutExpired')
        except OSError as exc:
            record.update(status='failed', execution_kind='unknown')
            record['errors'].append(type(exc).__name__ + ': ' + str(exc))
        elapsed = time.monotonic() - tick
        record['ended_at'] = datetime.now(timezone.utc).isoformat()
        record['latency'] = {'value': elapsed, 'unit': 'seconds', 'classification': 'measured',
                             'category': 'subprocess_wall_time', 'assumptions': [], 'unknown_reason': None}
        for suffix, content in [('stdout.json', stdout), ('stderr.txt', stderr)]:
            path = CASE / 'receipts' / (run_id + '.' + suffix)
            with path.open('x') as stream:
                stream.write(content)
            record['outputs'].append(reference(path))
        try:
            parsed = json.loads(stdout)
            rows = parsed['results']
            record['test_results'] = [{'test_id': r['test_id'], 'outcome': r['outcome']} for r in rows]
            expected_count = len(json.loads(fixtures.read_text())['cases'])
            valid = len(rows) == expected_count and len({r['test_id'] for r in rows}) == expected_count
            if name == 'historical-counterexamples':
                by_id = {r['test_id']: r for r in rows}
                valid = valid and all(by_id[key]['outcome'] == 'failed' and
                                      by_id[key].get('error', '').startswith('TypeError:')
                                      for key in ['action-list', 'patch-id-list', 'status-list'])
            else:
                valid = valid and all(r['outcome'] == 'passed' for r in rows)
        except (ValueError, KeyError, TypeError) as exc:
            valid = False
            record['errors'].append('Invalid test output: ' + str(exc))
        valid = valid and record['exit_status'] == expected_exit and not record['errors']
        record['repair_check_passed'] = valid
        receipt_path = CASE / 'receipts' / (run_id + '.json')
        save(receipt_path, record)
        summaries.append({'check': name, 'passed': valid, 'receipt': reference(receipt_path),
                          'passed_rows': sum(r['outcome'] == 'passed' for r in record['test_results']),
                          'total_rows': len(record['test_results'])})
    manifest = json.loads((HISTORY / 'manifest.json').read_text())
    changes = [name for name, digest in manifest['pre_repair_files'].items()
               if name != 'implementation/workflow.py' and
               (not (CASE / name).is_file() or hashlib.sha256((CASE / name).read_bytes()).hexdigest() != digest)]
    archive_matches = hashlib.sha256((HISTORY / 'workflow.py').read_bytes()).hexdigest() == HISTORICAL_SHA
    summary = {'schema_version': 1, 'case_id': '003', 'suite_id': 'crm-repair-v1',
               'recorded_at': datetime.now(timezone.utc).isoformat(), 'checks': summaries,
               'historical_artifacts_changed': changes, 'archive_matches_original_hash': archive_matches,
               'preservation_manifest': reference(HISTORY / 'manifest.json'),
               'implementation': reference(CASE / 'implementation/workflow.py'),
               'fixtures': reference(CASE / 'tests/fixtures.repair-v1.json'),
               'product_acceptance': False, 'inference_executed': False,
               'scope': 'Local R1/R3 repair verification only, not a reproduced conversational CRM product'}
    passed = all(s['passed'] for s in summaries) and not changes and archive_matches
    summary['status'] = 'passed' if passed else 'failed'
    summary_path = CASE / 'receipts' / ('003-repair-v1-' + stamp + '-summary.json')
    save(summary_path, summary)
    print(json.dumps({'summary': str(summary_path.relative_to(ROOT)), **summary}, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
