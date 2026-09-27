"""Append source-bound independent scheduling evaluation receipts, with a bounded child."""
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
SOURCE_BUNDLE = ROOT / 'cases/033/source-history/scheduler-v1-6e16e7e43d6b5d1d/source-bundle.json'
EVALUATOR_FREEZE = EVAL / 'selftest-receipts/20260922T040256033925Z-863d211b/freeze.json'
GROUPS = [f'S-N{n}' for n in range(1, 9)] + [f'S-A{n}' for n in range(1, 7)]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha(path)}


def save(path, value):
    with path.open('x') as stream:
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


def verify_members(bundle_path):
    if sha(bundle_path) != sha(SOURCE_BUNDLE) and bundle_path != SOURCE_BUNDLE:
        raise ValueError('Unexpected source bundle path')
    bundle = json.loads(bundle_path.read_text())
    for member in bundle['members']:
        path = ROOT / member['path']
        if 'source-history' not in member['path'] or 'scheduler-v1-6e16e7e43d6b5d1d' not in member['path']:
            raise ValueError('Refusing non-archived source member: ' + member['path'])
        if sha(path) != member['sha256']:
            raise ValueError('Immutable builder source changed: ' + member['path'])
    return bundle['members']


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8]
    folder = HERE / 'runs' / stamp
    folder.mkdir(parents=True, exist_ok=False)
    before = preservation()
    save(folder / 'preservation-before.json', before)
    members = verify_members(SOURCE_BUNDLE)
    source_ref = {'path': str(SOURCE_BUNDLE.relative_to(ROOT)), 'sha256': sha(SOURCE_BUNDLE)}
    evaluator_manifest = json.loads(EVALUATOR_FREEZE.read_text())
    for member in evaluator_manifest['artifacts']:
        if sha(EVAL / member['path']) != member['sha256']:
            raise ValueError('Frozen evaluator changed: ' + member['path'])
    capability = ROOT / 'capabilities-continuation.json'
    established = json.loads(capability.read_text())['usable_authorized_route_established']
    if established:
        raise ValueError('Capability evidence changed; reassess B1 before using this frozen run configuration')
    files = [HERE / x for x in ['execute.py', 'run_schedule_review.py', 'README.md']]
    files += [EVAL / x for x in ['adapters.py', 'evaluate.py', 'suite.json']]
    files += [EVAL / 'inputs/033' / f'{name}.json' for name in GROUPS]
    files += [EVAL / 'oracles/033' / f'{name}.json' for name in GROUPS]
    files += [capability, EVALUATOR_FREEZE, SOURCE_BUNDLE]
    files += [ROOT / member['path'] for member in members]
    frozen = []
    for path in files:
        reference = ref(path)
        snapshot = folder / 'snapshots' / reference['path']
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        with snapshot.open('xb') as stream:
            stream.write(path.read_bytes())
        frozen.append({**reference, 'retained_copy': str(snapshot.relative_to(ROOT))})
    freeze_path = folder / 'freeze.json'
    save(freeze_path, {'schema_version': 1, 'frozen_at': datetime.now(timezone.utc).isoformat(),
                       'source_snapshot': source_ref, 'artifacts': frozen, 'exposure': 'independent_authored_exposed'})
    config_path = folder / 'config.json'
    save(config_path, {'source_snapshot': source_ref, 'freeze': ref(freeze_path), 'inference_enabled': False})
    command = [sys.executable, '-B', str(HERE / 'run_schedule_review.py'), str(config_path)]
    started = datetime.now(timezone.utc).isoformat(); tick = time.monotonic()
    code, stdout, stderr, error = None, b'', b'', None
    try:
        process = subprocess.run(command, cwd=str(ROOT), capture_output=True, timeout=40)
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
        observed = None
        error = error or 'No structured evaluation output'
    after = preservation()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    source_changes = [m['path'] for m in frozen if not (ROOT / m['path']).is_file() or sha(ROOT / m['path']) != m['sha256']]
    try:
        verify_members(SOURCE_BUNDLE)
        members_after_ok = True
    except ValueError as exc:
        members_after_ok = False
        error = error or str(exc)
    algorithm_correct = bool(observed and observed.get('algorithm_correctness') is True)
    any_failed = bool(observed and observed.get('failed_attempts'))
    review_ok = code == 0 and error is None and observed is not None and not changed and not source_changes and members_after_ok
    if review_ok and algorithm_correct:
        status = 'passed'
    elif review_ok and not any_failed:
        status = 'incomplete'
    else:
        status = 'failed'
    result = {'schema_version': 1, 'case_id': '033', 'status': status, 'started_at': started,
              'ended_at': datetime.now(timezone.utc).isoformat(), 'elapsed_seconds': time.monotonic() - tick,
              'command': command, 'cwd': str(ROOT), 'timeout_seconds': 40, 'exit_status': code, 'error': error,
              'implementation': source_ref, 'fixtures': ref(EVAL / 'oracles/033/S-N1.json'),
              'input_bundle': ref(EVAL / 'inputs/033/S-N1.json'), 'freeze': ref(freeze_path),
              'outputs': [ref(folder / 'stdout.json'), ref(folder / 'stderr.txt')],
              'counts': {
                  'unique_groups': observed.get('unique_groups') if observed else None,
                  'group_attempts': observed.get('group_attempts') if observed else None,
                  'planned_invocations': observed.get('planned_invocations') if observed else None,
                  'passed_attempts': observed.get('passed_attempts') if observed else None,
                  'blocked_attempts': observed.get('blocked_attempts') if observed else None,
                  'failed_attempts': observed.get('failed_attempts') if observed else None,
                  'normal_first_pass': observed.get('normal_first_pass') if observed else None,
                  'adversarial_first_pass': observed.get('adversarial_first_pass') if observed else None,
              },
              'algorithm_correctness': algorithm_correct if observed else False,
              'search_limited_treated_as': 'incomplete_evidence_not_infeasibility',
              'oracles_supplied_to_scheduler': False,
              'feasibility_witnesses_supplied_to_scheduler': False,
              'working_implementation_imported': False,
              'central_workflow': {'status': 'local_scheduler_executed' if observed else 'not_executed',
                                   'calendar_writes': 0,
                                   'reason': 'Local archived scheduler only; no calendar or account writes'},
              'B1': {'status': 'blocked_not_executed', 'capability_evidence': ref(capability),
                     'reason': 'No authorized callable inference route; missing capability is not a failed comparison'},
              'B2': {'status': 'archived_scheduler_executed' if code is not None else 'not_executed'},
              'B3': {'status': 'not_observed'}, 'inference_executed': False, 'model_requests': 0,
              'exposure': 'independent_authored_exposed', 'hidden_evaluation_established': False,
              'product_acceptance': False, 'commercial_verdict': 'insufficient_evidence',
              'cost': {'value': None, 'unit': 'USD', 'classification': 'unknown',
                       'reason': 'No billing/local-resource allocation measurement; no paid API calls'},
              'preservation_manifest': ref(folder / 'preservation-before.json'),
              'outside_review_files_checked': len(before),
              'outside_review_changed_paths': changed, 'source_changes': source_changes,
              'source_members_verified_after': members_after_ok,
              'limitations': ['Exposed independent_authored fixtures, not a hidden suite',
                              'evaluate.py assertions are not weighted product scores',
                              'search_limited is incomplete evidence, never proven infeasibility',
                              'Audit hooks are not OS containment',
                              'B1 absence is a capability gap, not a comparison failure',
                              'Algorithm correctness is not product acceptance']}
    save(folder / 'receipt.json', result)
    save(folder / 'verification.json', {
        'status': status,
        'receipt_sha256': sha(folder / 'receipt.json'),
        'verified_frozen_artifacts': len(frozen),
        'group_attempts': observed.get('group_attempts') if observed else None,
        'planned_invocations': observed.get('planned_invocations') if observed else None,
        'algorithm_correctness': result['algorithm_correctness'],
        'prohibited_effects_observed': observed.get('prohibited_effects_observed') if observed else None,
        'outside_review_changed_paths': changed,
        'source_members_verified_after': members_after_ok,
        'product_acceptance': False,
    })
    print(json.dumps({'receipt_path': str((folder / 'receipt.json').relative_to(ROOT)), **result}, indent=2))
    return 0 if status == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
