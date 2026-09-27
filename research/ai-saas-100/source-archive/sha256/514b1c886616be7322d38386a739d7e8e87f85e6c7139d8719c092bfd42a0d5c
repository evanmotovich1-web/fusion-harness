"""Foreground pilot runner. Receipts describe local assertions, never product acceptance."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from receipt import receipt_template, unknown_metric


def now():
    return datetime.now(timezone.utc).isoformat()


def ref(path, root=ROOT):
    path = Path(path).resolve()
    return {'path': str(path.relative_to(root.resolve())),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def local_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Missing or out-of-scope artifact: ' + str(relative))
    return path


def expected_ids(suite):
    if not isinstance(suite, dict) or not isinstance(suite.get('cases'), list) or not suite['cases']:
        raise ValueError('Suite must contain a nonempty cases array')
    ids = []
    for case in suite['cases']:
        if not isinstance(case, dict) or not isinstance(case.get('id'), str) or not case['id'].strip():
            raise ValueError('Suite case requires a nonempty string id')
        ids.append(case['id'])
    if len(ids) != len(set(ids)):
        raise ValueError('Suite case IDs must be unique')
    return ids


def checked_results(raw, expected):
    try:
        parsed = json.loads(raw.decode('utf-8'), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (UnicodeError, ValueError) as exc:
        return [], 'malformed_json', str(exc)
    if not isinstance(parsed, dict) or not isinstance(parsed.get('results'), list):
        return [], 'malformed_result_schema', 'Expected object with results array'
    rows, ids = [], []
    for row in parsed['results']:
        if (not isinstance(row, dict) or not isinstance(row.get('test_id'), str)
                or not isinstance(row.get('outcome'), str)
                or row['outcome'] not in {'passed', 'failed', 'blocked'}):
            return [], 'malformed_result_schema', 'Every result needs string test_id and valid outcome'
        rows.append({'test_id': row['test_id'], 'outcome': row['outcome']})
        ids.append(row['test_id'])
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        return [], 'malformed_result_schema', 'Result IDs must match the chosen suite exactly, once each'
    return rows, None, None


def run_one(job, root=ROOT, timeout=15):
    """Run one trusted foreground child; persist failure before returning to the batch."""
    root = Path(root).resolve()
    if not 0 < timeout <= 50:
        raise ValueError('Timeout must be greater than zero and at most 50 seconds')
    cid = job['case_id']
    receipt = receipt_template(cid, cid + '-local-' + uuid.uuid4().hex)
    folder = (root / job.get('receipt_directory', f'cases/{cid}/receipts')).resolve()
    if not folder.is_relative_to(root):
        raise ValueError('Receipt directory must stay inside campaign root')
    folder.mkdir(parents=True, exist_ok=True)
    run_id = receipt['run_id']
    attempted_at, tick = now(), time.monotonic()
    stdout, stderr = b'', b''
    failure_kind, errors, timeouts, rows, expected = None, [], [], [], []
    started_at = ended_at = exit_status = None
    artifacts = {'implementation': None, 'fixtures': None, 'input_bundle': None}
    runner_ref = None
    command = job.get('command', [])
    process = None
    try:
        if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
            raise ValueError('Command must be a nonempty argv array')
        for field, key in [('implementation', 'implementation'), ('fixtures', 'suite'), ('input_bundle', 'input_bundle')]:
            relative = job.get(key, job.get('suite'))
            artifacts[field] = ref(local_path(root, relative), root)
        runner_ref = ref(local_path(root, job['runner']), root)
        expected = expected_ids(json.loads(local_path(root, job['suite']).read_text()))
    except (ValueError, TypeError, KeyError, OSError) as exc:
        failure_kind = 'preflight_error'
        errors.append(type(exc).__name__ + ': ' + str(exc))
    if failure_kind is None:
        launch_at = now()
        try:
            process = subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (OSError, ValueError) as exc:
            failure_kind = 'launch_error'
            errors.append(type(exc).__name__ + ': ' + str(exc))
        if process is not None:
            started_at = launch_at
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                failure_kind = 'timeout'
                errors.append('Foreground child exceeded timeout and was killed and reaped')
                timeouts.append({'limit_seconds': timeout})
                process.kill()
                try:
                    # communicate returns the full buffered output, not just the suffix.
                    stdout, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired as final:
                    # Trusted pilot children must not spawn detached descendants holding pipes.
                    stdout, stderr = final.output or exc.output or b'', final.stderr or exc.stderr or b''
                    process.stdout.close()
                    process.stderr.close()
                    process.wait(timeout=5)
                    errors.append('Output pipes remained open after child termination; saved available partial output')
            ended_at, exit_status = now(), process.returncode
            rows, parse_failure, parse_error = checked_results(stdout, expected)
            if parse_failure:
                errors.append(parse_failure + ': ' + parse_error)
                failure_kind = failure_kind or parse_failure
            if exit_status != 0:
                errors.append('Child exit status: ' + str(exit_status))
                failure_kind = failure_kind or 'nonzero_exit'
            if rows and any(row['outcome'] != 'passed' for row in rows):
                errors.append('Chosen suite contains failed or blocked local assertions')
                failure_kind = failure_kind or 'unsuccessful_results'
    attempt_ended_at, elapsed = now(), time.monotonic() - tick
    out = folder / (run_id + '.stdout.bin')
    err = folder / (run_id + '.stderr.bin')
    with out.open('xb') as f:
        f.write(stdout)
    with err.open('xb') as f:
        f.write(stderr)
    status = 'blocked' if process is None else ('failed' if failure_kind else 'completed')
    receipt.update(status=status, started_at=started_at, ended_at=ended_at,
                   attempt_started_at=attempted_at, attempt_ended_at=attempt_ended_at,
                   failure_kind=failure_kind, process_started=process is not None,
                   command=command, cwd=str(root), **artifacts,
                   outputs=[ref(out, root), ref(err, root)],
                   runtime={'python': platform.python_version(), 'platform': platform.system()},
                   configuration={'network': False, 'mode': 'runner_failure_validation' if job.get('test_only') else 'local_partial_regression', 'concurrency': 1,
                                  'test_only': bool(job.get('test_only')),
                                  'model_calls': 0, 'runner': runner_ref, 'orchestrator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                  'semantic_quality_scored': False, 'timeout_seconds': timeout,
                                  'expected_test_ids': expected, 'expected_count': len(expected),
                                  'input_bundle_scope': job.get('input_bundle_scope', 'Legacy fixtures include evaluator material; not valid comparison inputs')},
                   exit_status=exit_status, test_results=rows, timeouts=timeouts,
                   execution_kind='real' if process is not None else 'unknown', inference_executed=False,
                   quality=[unknown_metric('points', 'semantic_quality')], errors=errors,
                   missing_capabilities=['Generic-model baseline unavailable', 'Independent hidden evaluation unavailable'],
                   human_interventions=['Builder-visible fixed regression, not hidden evaluation'],
                   latency={'value': elapsed, 'unit': 'seconds', 'classification': 'measured',
                            'category': 'latency', 'assumptions': [], 'unknown_reason': None},
                   product_acceptance=False, original_product_status='not_observed')
    if cid != '002':
        receipt['missing_capabilities'].append('Central AI workflow not executed')
    path = folder / (run_id + '.json')
    with path.open('x') as f:
        json.dump(receipt, f, indent=2)
    return {'case_id': cid, 'receipt_path': str(path.relative_to(root)), 'status': status,
            'failure_kind': failure_kind, 'successful': status == 'completed',
            'passed_local_regressions': sum(r['outcome'] == 'passed' for r in rows),
            'local_regressions': len(rows), 'expected_local_regressions': len(expected),
            'central_workflow_accepted': False, 'elapsed_seconds': elapsed}


def run_batch(jobs, root=ROOT, timeout=15):
    return [run_one(job, root, timeout) for job in jobs]


def default_jobs():
    return [{'case_id': cid, 'command': [sys.executable, '-B', str(ROOT / 'cases' / cid / 'tests/run.py')],
             'runner': f'cases/{cid}/tests/run.py', 'suite': f'cases/{cid}/tests/fixtures.json',
             'implementation': f'cases/{cid}/implementation/workflow.py'} for cid in ['001', '002', '003']]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=Path, help='Trusted JSON array of jobs selecting explicit versioned suites and argv')
    parser.add_argument('--timeout', type=float, default=15)
    args = parser.parse_args()
    jobs = json.loads(args.jobs.read_text()) if args.jobs else default_jobs()
    summaries = run_batch(jobs, timeout=args.timeout)
    print(json.dumps(summaries, indent=2))
    return 0 if summaries and all(s['successful'] for s in summaries) else 1


if __name__ == '__main__':
    raise SystemExit(main())
