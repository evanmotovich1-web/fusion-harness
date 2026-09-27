"""Append source-bound independent case 002 marketplace evaluation receipts, with a bounded child."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
ROOT = EVAL.parents[1]
MANIFEST = ROOT / 'execution-manifest.json'
EVALUATOR_FREEZE = EVAL / 'selftest-receipts/20260922T040256033925Z-863d211b/freeze.json'
CAPABILITY = ROOT / 'capabilities-continuation.json'
FIXED_WRITERS = ['cases/002/tests/repair-v2/execute.py', 'cases/002/tests/repair-v2/validate.py']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref(path):
    return {'path': str(Path(path).relative_to(ROOT)), 'sha256': sha(path)}


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')



def preservation():
    result = {}
    for path in sorted(ROOT.rglob('*')):
        if HERE in path.parents or path == HERE:
            continue
        if path.is_symlink():
            result[str(path.relative_to(ROOT))] = {'symlink': os.readlink(path)}
        elif path.is_file():
            result[str(path.relative_to(ROOT))] = sha(path)
    return result


def main():
    manifest = json.loads(MANIFEST.read_text())
    binding = next(item for item in manifest['source_bindings']
                   if item['active']['path'] == 'cases/002/implementation/workflow.py')
    active_source = ROOT / binding['active']['path']
    snapshot = ROOT / binding['snapshot']['path']
    if sha(active_source) != binding['active']['sha256']:
        raise ValueError('Active marketplace source diverged from execution manifest')
    if sha(snapshot) != binding['snapshot']['sha256'] or sha(snapshot) != sha(active_source):
        raise ValueError('Archived marketplace snapshot does not match manifest binding')
    freeze = json.loads(EVALUATOR_FREEZE.read_text())
    for member in freeze['artifacts']:
        if sha(EVAL / member['path']) != member['sha256']:
            raise ValueError('Frozen evaluator changed: ' + member['path'])
    suite = json.loads((EVAL / 'suite.json').read_text())
    repeat_ids = set(suite['repeat_groups'])
    groups, planned_attempts, planned_invocations = [], 0, 0
    for test in ['M-N%d' % n for n in range(1, 9)] + ['M-A%d' % n for n in range(1, 7)]:
        input_path = EVAL / 'inputs' / '002' / (test + '.json')
        oracle_path = EVAL / 'oracles' / '002' / (test + '.json')
        bundle = json.loads(input_path.read_text())
        repetitions = 1 + (suite['extra_repeats'] if test.replace('M-', '') in repeat_ids else 0)
        planned_attempts += repetitions
        planned_invocations += repetitions * len(bundle['runs'])
        groups.append({'input': ref(input_path), 'oracle': ref(oracle_path)})

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8]
    folder = HERE / 'runs' / stamp
    folder.mkdir(parents=True, exist_ok=False)
    before = preservation()
    save(folder / 'preservation-before.json', before)

    evaluator_components = {
        'adapters': ref(EVAL / 'adapters.py'), 'evaluate': ref(EVAL / 'evaluate.py'),
        'suite': ref(EVAL / 'suite.json'), 'freeze': ref(EVALUATOR_FREEZE)}
    config = {'schema_version': 1, 'root': str(ROOT),
              'source_snapshot': {'path': binding['snapshot']['path'], 'sha256': binding['snapshot']['sha256']},
              'active_source': {'path': binding['active']['path'], 'sha256': binding['active']['sha256']},
              'evaluator_components': evaluator_components,
              'capability_evidence': ref(CAPABILITY),
              'groups': groups,
              'planned_group_attempts': planned_attempts, 'planned_invocations': planned_invocations}
    config_path = folder / 'config.json'
    save(config_path, config)

    files = [HERE / 'README.md', HERE / 'run_market_review.py', Path(__file__),
             MANIFEST, EVALUATOR_FREEZE, CAPABILITY, active_source, snapshot,
             EVAL / 'adapters.py', EVAL / 'evaluate.py', EVAL / 'suite.json']
    files += [ROOT / group['input']['path'] for group in groups]
    files += [ROOT / group['oracle']['path'] for group in groups]
    frozen = []
    for path in files:
        reference = ref(path)
        snapshot_copy = folder / 'snapshots' / reference['path']
        snapshot_copy.parent.mkdir(parents=True, exist_ok=True)
        with snapshot_copy.open('xb') as stream:
            stream.write(path.read_bytes())
        frozen.append({**reference, 'retained_copy': str(snapshot_copy.relative_to(ROOT))})
    freeze_path = folder / 'freeze.json'
    save(freeze_path, {'schema_version': 1, 'frozen_at': datetime.now(timezone.utc).isoformat(),
                       'source_snapshot': config['source_snapshot'], 'artifacts': frozen,
                       'exposure': 'independent_authored_exposed'})

    writers_before = {writer: sha(ROOT / writer) for writer in FIXED_WRITERS}
    command = [sys.executable, '-B', str(HERE / 'run_market_review.py'), str(config_path)]
    started = datetime.now(timezone.utc).isoformat()
    tick = time.monotonic()
    code, stdout, stderr, error = None, b'', b'', None
    try:
        process = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=40)
        code, stdout, stderr = process.returncode, process.stdout, process.stderr
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, error = exc.stdout or b'', exc.stderr or b'', 'foreground_evaluator_timeout'
    except OSError as exc:
        error = type(exc).__name__ + ': ' + str(exc)
    for name, data in [('stdout.json', stdout), ('stderr.txt', stderr)]:
        with (folder / name).open('xb') as stream:
            stream.write(data)
    try:
        observed = json.loads(stdout)
    except (ValueError, UnicodeError):
        observed, error = None, error or 'No structured evaluation output'

    writers_after = {writer: sha(ROOT / writer) for writer in FIXED_WRITERS}
    writers_untouched = writers_before == writers_after
    after = preservation()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    source_changes = [m['path'] for m in frozen
                      if not (ROOT / m['path']).is_file() or sha(ROOT / m['path']) != m['sha256']]
    accepted = bool(observed and observed.get('local_component_acceptance'))
    passed = (code == 0 and error is None and observed is not None and accepted
              and not changed and not source_changes and writers_untouched)
    status = 'passed' if passed else 'failed'
    result = {'schema_version': 1, 'case_id': '002', 'status': status, 'started_at': started,
              'ended_at': datetime.now(timezone.utc).isoformat(),
              'elapsed_seconds': time.monotonic() - tick, 'command': command, 'cwd': str(ROOT),
              'timeout_seconds': 40, 'exit_status': code, 'error': error,
              'implementation': {'manifest_binding': binding['active'],
                                 'executed_snapshot': config['source_snapshot'],
                                 'manifest': ref(MANIFEST)},
              'evaluator_freeze': ref(EVALUATOR_FREEZE), 'run_freeze': ref(freeze_path),
              'outputs': [ref(folder / 'stdout.json'), ref(folder / 'stderr.txt')],
              'counts': observed.get('counts') if observed else None,
              'threshold_check': observed.get('threshold_check') if observed else None,
              'local_component_acceptance': accepted,
              'arms': {'local_component': 'executed' if code is not None else 'not_executed',
                       'B1_generic_model': {'status': 'blocked_not_executed',
                                            'capability_evidence': ref(CAPABILITY)},
                       'B3_original_product': 'not_observed'},
              'fixed_output_writers': {'never_executed': FIXED_WRITERS,
                                       'hashes_before': writers_before, 'hashes_after': writers_after,
                                       'byte_identical': writers_untouched},
              'inference_executed': False, 'model_requests': 0,
              'exposure': 'independent_authored_exposed', 'hidden_evaluation_established': False,
              'product_acceptance': False, 'commercial_verdict': 'insufficient_evidence',
              'cost': {'value': None, 'unit': 'USD', 'classification': 'unknown',
                       'reason': 'Local deterministic execution only; no paid or metered calls'},
              'preservation_manifest': ref(folder / 'preservation-before.json'),
              'outside_review_files_checked': len(before), 'outside_review_changed_paths': changed,
              'source_changes': source_changes,
              'limitations': [
                  'Local deterministic subset only; editorial judgment and live marketplace behavior unassessed',
                  'Exposed suite; hidden evaluation not established by this run',
                  'Passing assertions establish component correctness, not product acceptance',
                  'Audit hooks are instrumentation, not OS containment',
                  'B1 absence is a missing authorized capability, not a failed comparison']}
    save(folder / 'receipt.json', result)
    print(json.dumps({'receipt_path': str((folder / 'receipt.json').relative_to(ROOT)), **result}, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
