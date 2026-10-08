"""Verify retained case 002 work and write only a fresh, uniquely named run directory."""
import copy
import datetime
import hashlib
import json
import pathlib
import platform
import runpy
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
CASE = HERE.parents[1]
ROOT = CASE.parents[1]
REPORTS = pathlib.Path('/tmp/fusion-harness-plXwRt/collaborate/reports')


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha(path)}


def load(path):
    return json.loads(path.read_text())


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def checked(item):
    path = ROOT / item['path']
    assert sha(path) == item['sha256'], str(path)
    return path


def no_answers(value):
    if isinstance(value, dict):
        assert not {'expected', 'scenario', 'scenario_name', 'oracle', 'description'}.intersection(value)
        for child in value.values():
            no_answers(child)
    elif isinstance(value, list):
        for child in value:
            no_answers(child)


def recover(out, summary):
    existing = [ref(p) for p in sorted(CASE.rglob('*')) if p.is_file() and not p.is_relative_to(out)]
    write(out / 'preservation-before.json', existing)
    retained_reports = []
    for name in ('1.c-terra.md', '1.c-attempt-1.md'):
        original = REPORTS / name
        data = original.read_bytes()
        dest = out / ('historical-' + name)
        with dest.open('xb') as stream:
            stream.write(data)
        retained_reports.append({'original_path': str(original), 'copy': ref(dest)})
    summary['historical_reports'] = retained_reports

    history = load(CASE / 'source-history/pre-repair-287e153d1e4f/manifest.json')
    mapping = {row['original_path']: row for row in history['files']}
    unchanged = 0
    for row in history['files']:
        assert sha(ROOT / row['archive_path']) == row['sha256']
        if row['original_path'] not in {'cases/002/dossier.json', 'cases/002/implementation/workflow.py'}:
            assert sha(ROOT / row['original_path']) == row['sha256']
            unchanged += 1
    old = load(CASE / 'receipts/002-local-20260920T212619053188Z.json')
    for item in [old['implementation'], old['fixtures'], old['input_bundle'], old['configuration']['runner'], *old['outputs']]:
        assert mapping[item['path']]['sha256'] == item['sha256']

    repair = CASE / 'tests/repair-v2'
    for item in load(repair / 'freeze.json')['artifacts']:
        checked(item)
    payload = load(repair / 'comparison-inputs.json')
    oracle = load(repair / 'evaluator.json')
    no_answers(payload)
    expected_ids = [row['id'] for row in payload['cases']]
    assert len(set(expected_ids)) == len(expected_ids) == 54
    assert expected_ids == [row['id'] for row in oracle['cases']]
    for case in payload['cases']:
        assert set(case) == {'id', 'initial_state', 'requests'}
        assert set(case['initial_state']) == {'gap', 'profiles', 'assignments'}
        for profile in case['initial_state']['profiles']:
            assert set(profile) == {'id', 'target', 'area', 'dr', 'review'}
        for assignment in case['initial_state']['assignments']:
            assert set(assignment) == {'id', 'source', 'target', 'created', 'deadline', 'status', 'reason', 'reported_url'}
        for request in case['requests']:
            assert set(request) == {'operation', 'arguments', 'clock'}

    prior_validation = load(repair / 'validation.json')
    assert prior_validation['status'] == 'passed'
    checked({'path': prior_validation['repeat']['stdout_path'], 'sha256': prior_validation['repeat']['stdout_sha256']})
    prior_repeat = load(ROOT / prior_validation['repeat']['stdout_path'])
    assert prior_repeat['passed'] == 54 and prior_repeat['failed'] == 0
    index = load(repair / 'execution-index.json')
    bundle = load(checked(index['source_bundle']))
    for member in bundle['members']:
        checked(member)
        assert sha(ROOT / member['active_path']) == member['sha256']
    validator = runpy.run_path(str(ROOT / 'tools/validate.py'))['receipt']
    templates = []
    for run in index['runs']:
        receipt = load(ROOT / run['receipt_path'])
        validator(receipt, ROOT)
        for item in [receipt['implementation'], receipt['fixtures'], receipt['input_bundle'], *receipt['outputs'], receipt['configuration']['runner'], receipt['configuration']['source_bundle']]:
            checked(item)
        if receipt['configuration']['interface_transformation']:
            checked(receipt['configuration']['interface_transformation'])
        assert receipt['exit_status'] == 0 and not receipt['product_acceptance']
        rows = load(checked(receipt['outputs'][0]))['results']
        assert len(rows) == run['passed'] and run['failed'] == 0
        assert all(row['outcome'] == 'passed' for row in rows)
        templates.append(receipt)
    assert len(templates) == 2

    with (out / 'recovery-runner.py').open('xb') as stream:
        stream.write(pathlib.Path(__file__).read_bytes())
    sources = copy.deepcopy(bundle)
    sources.update(archived_at=now(), recovered_from=index['source_bundle'])
    sources['members'].append({'active_path': str(pathlib.Path(__file__).resolve().relative_to(ROOT)), **ref(out / 'recovery-runner.py')})
    write(out / 'source-bundle.json', sources)
    summary.update(archived_original_files_verified=len(mapping), original_files_unchanged_since_repair=unchanged,
                   retained_validation=ref(repair / 'validation.json'), retained_execution_index=ref(repair / 'execution-index.json'),
                   source_bundle=ref(out / 'source-bundle.json'), comparison_inputs=ref(repair / 'comparison-inputs.json'),
                   separate_evaluator=ref(repair / 'evaluator.json'), source_sha256=sha(CASE / 'implementation/workflow.py'))
    suites = [('repair-v2', repair / 'run.py', expected_ids),
              ('historical', CASE / 'tests/run.py', [row['id'] for row in load(CASE / 'tests/fixtures.json')['cases']])]
    summary['runs'] = []
    for template, (label, runner, ids) in zip(templates, suites):
        command = [sys.executable, '-I', '-B', str(runner)]
        start = now()
        tick = time.monotonic()
        errors, timeouts = [], []
        try:
            process = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=20)
            stdout, stderr, code = process.stdout, process.stderr, process.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, code = exc.stdout or b'', exc.stderr or b'', -1
            errors.append('Foreground subprocess exceeded 20 seconds')
            timeouts.append({'seconds': 20})
        except OSError as exc:
            stdout, stderr, code = b'', str(exc).encode(), -1
            errors.append(type(exc).__name__ + ': ' + str(exc))
        ended, elapsed = now(), time.monotonic() - tick
        for suffix, data in [('stdout.json', stdout), ('stderr.txt', stderr)]:
            with (out / (label + '.' + suffix)).open('xb') as stream:
                stream.write(data)
        rows = []
        try:
            result = json.loads(stdout)
            rows = result['results']
            assert [row['test_id'] for row in rows] == ids
            assert all(row['outcome'] == 'passed' for row in rows)
            if label == 'repair-v2':
                assert result['source_sha256'] == summary['source_sha256']
                assert result['input_bundle_sha256'] == sha(repair / 'comparison-inputs.json')
                assert result['interface_transformation_sha256'] == sha(repair / 'adapter.py')
                assert result['oracle_sha256'] == sha(repair / 'evaluator.json')
        except (ValueError, KeyError, TypeError, AssertionError) as exc:
            errors.append(type(exc).__name__ + ': ' + str(exc))
        if code != 0:
            errors.append('Subprocess exited ' + str(code))
        receipt = copy.deepcopy(template)
        receipt.update(run_id='002-recovery-v1-' + out.name + '-' + label, status='completed' if not errors else 'failed',
                       started_at=start, ended_at=ended, command=command, cwd=str(ROOT), exit_status=code,
                       outputs=[ref(out / (label + '.stdout.json')), ref(out / (label + '.stderr.txt'))],
                       runtime={'python': platform.python_version(), 'platform': platform.platform()}, errors=errors, timeouts=timeouts,
                       test_results=[{'test_id': row['test_id'], 'outcome': row['outcome']} for row in rows])
        receipt['configuration'].update(timeout_seconds=20, source_bundle=ref(out / 'source-bundle.json'), recovery_orchestrator=ref(out / 'recovery-runner.py'), mode='retained_repair_verification_' + label)
        receipt['latency'].update(value=elapsed, unknown_reason=None)
        write(out / (label + '.receipt.json'), receipt)
        validator(receipt, ROOT)
        summary['runs'].append({'label': label, 'receipt': ref(out / (label + '.receipt.json')),
                                'passed': sum(row['outcome'] == 'passed' for row in rows), 'total': len(ids),
                                'exit_status': code, 'errors': errors})
    for item in existing:
        checked(item)
    for item in retained_reports:
        assert sha(pathlib.Path(item['original_path'])) == item['copy']['sha256']
        checked(item['copy'])
    summary['all_preexisting_case_files_unchanged'] = True
    summary['preserved_file_count'] = len(existing)
    summary['preservation_manifest'] = ref(out / 'preservation-before.json')
    assert all(not run['errors'] and run['exit_status'] == 0 for run in summary['runs'])
    summary['status'] = 'passed'


def main():
    assert sys.flags.optimize == 0, 'Assertions must be enabled'
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = HERE / 'runs' / stamp
    out.mkdir(parents=True, exist_ok=False)
    summary = {'schema_version': 1, 'task_id': '1.b', 'case_id': '002', 'started_at': now(), 'status': 'failed',
               'scope': 'Fresh execution of retained local regression. Not independent hidden evaluation or product acceptance.',
               'product_acceptance': False, 'model_comparison_executed': False, 'original_product_observed': False,
               'implementation_changed': False, 'fixed_output_evidence_writers_executed': False,
               'limits': ['No model baseline', 'Builder-visible tests', 'No live marketplace observation or editorial evaluation',
                          'Historical suite uses scenario-derived inputs and must not be used for model comparison']}
    try:
        recover(out, summary)
    except Exception as exc:
        summary['verification_error'] = type(exc).__name__ + ': ' + str(exc)
    summary['ended_at'] = now()
    write(out / 'validation.json', summary)
    if summary['status'] == 'passed':
        outcome = {'schema_version': 1, 'status': 'completed', 'summary': 'Recovered retained case 002 evidence, verified hashes, and reran 54 repair and 20 historical regressions successfully without changing existing work. Model comparison and product acceptance remain unestablished.'}
        report = ('# Case 002 recovery verification\n\nTask: `1.b`.\n\n'
                  'F1. Fresh bounded executions passed 54 repair-v2 and 20 historical cases. The implementation was not changed.\n\n'
                  'F2. Archive, source, interface, comparison-input, evaluator, and receipt hashes were recomputed. '
                  'All pre-existing case files and both historical malformed task reports were preserved. Their exact copies are retained here.\n\n'
                  'F3. Evidence: `validation.json`, `source-bundle.json`, `preservation-before.json`, '
                  '`repair-v2.receipt.json`, `historical.receipt.json`, and both raw stdout/stderr pairs in this directory.\n\n'
                  'H1. Integration should use these fresh receipts and the unchanged repair-v2 comparison input and separate evaluator. '
                  'Repeat verification with `python3 -I -B research/ai-saas-100/cases/002/tests/recovery-v1/run.py`, which creates a fresh run directory. '
                  'Do not rerun repair-v2/execute.py or repair-v2/validate.py in place.\n\n'
                  'Product acceptance: false. No model comparison, hidden evaluation, live marketplace access, or publication was performed.\n\n'
                  'FH_TASK_OUTCOME: ' + json.dumps(outcome, separators=(',', ':')) + '\n')
        lines = [line for line in report.splitlines() if line.startswith('FH_TASK_OUTCOME: ')]
        assert len(lines) == 1 and report.splitlines()[-1] == lines[0]
        assert set(json.loads(lines[0].split(': ', 1)[1])) == {'schema_version', 'status', 'summary'}
        with (out / 'replacement-report.md').open('x') as stream:
            stream.write(report)
        write(out / 'report-validation.json', {'report': ref(out / 'replacement-report.md'), 'metadata_lines': 1, 'metadata_keys': sorted(outcome), 'status': 'passed', 'scope': 'Local check against the task-specified metadata shape, not a harness-parser modification or acceptance receipt'})
    print(json.dumps({'status': summary['status'], 'path': str(out.relative_to(ROOT)), 'runs': summary.get('runs', []), 'error': summary.get('verification_error')}, indent=2))
    return 0 if summary['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
