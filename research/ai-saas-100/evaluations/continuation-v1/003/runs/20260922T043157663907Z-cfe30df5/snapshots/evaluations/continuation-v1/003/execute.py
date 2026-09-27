"""Append source-bound independent CRM evaluation receipts, with a bounded child."""
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
BUILDER_SUMMARY = ROOT / 'cases/003/receipts/003-persistence-v1-20260922T033210014938Z-summary.json'
EVALUATOR_FREEZE = EVAL / 'selftest-receipts/20260922T040256033925Z-863d211b/freeze.json'


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


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8]
    folder = HERE / 'runs' / stamp
    folder.mkdir(parents=True, exist_ok=False)
    before = preservation()
    save(folder / 'preservation-before.json', before)
    summary = json.loads(BUILDER_SUMMARY.read_text())
    source_ref = summary['source_snapshot']
    source_manifest = ROOT / source_ref['path']
    if sha(source_manifest) != source_ref['sha256']:
        raise ValueError('Builder source manifest hash mismatch')
    source_members = json.loads(source_manifest.read_text())['artifacts']
    for member in source_members:
        if sha(ROOT / member['path']) != member['sha256']:
            raise ValueError('Immutable builder source changed: ' + member['path'])
    evaluator_manifest = json.loads(EVALUATOR_FREEZE.read_text())
    for member in evaluator_manifest['artifacts']:
        if sha(EVAL / member['path']) != member['sha256']:
            raise ValueError('Frozen evaluator changed: ' + member['path'])
    capability = ROOT / 'capabilities-continuation.json'
    established = json.loads(capability.read_text())['usable_authorized_route_established']
    # This execution is intentionally component-only even if capabilities later improve.
    if established:
        raise ValueError('Capability evidence changed; reassess conversational arms before using this frozen run configuration')
    files = [HERE / x for x in ['execute.py', 'run_component_review.py', 'prepare.py', 'component-inputs.json', 'component-oracles.json', 'README.md']]
    files += [EVAL / x for x in ['adapters.py', 'evaluate.py']]
    for n in [2, 3, 6]:
        files += [EVAL / 'components' / f'C-LOCAL-A{n}.json', EVAL / 'component-oracles' / f'C-LOCAL-A{n}.json']
    files += [EVAL / 'inputs/003/C-A1.json', EVAL / 'oracles/003/C-A1.json', capability, BUILDER_SUMMARY, EVALUATOR_FREEZE, source_manifest]
    files += [ROOT / member['path'] for member in source_members]
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
    command = [sys.executable, '-B', str(HERE / 'run_component_review.py'), str(config_path)]
    started = datetime.now(timezone.utc).isoformat(); tick = time.monotonic()
    code, stdout, stderr, error = None, b'', b'', None
    try:
        process = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=40)
        code, stdout, stderr = process.returncode, process.stdout, process.stderr
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, error = exc.stdout or b'', exc.stderr or b'', 'foreground_evaluator_timeout'
    except OSError as exc:
        error = type(exc).__name__ + ': ' + str(exc)
    for name, data in [('stdout.json', stdout), ('stderr.txt', stderr)]:
        with (folder / name).open('xb') as stream: stream.write(data)
    try:
        observed = json.loads(stdout)
    except (ValueError, UnicodeError):
        observed = None
        error = error or 'No structured evaluation output'
    after = preservation()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    source_changes = [m['path'] for m in frozen if not (ROOT / m['path']).is_file() or sha(ROOT / m['path']) != m['sha256']]
    passed = code == 0 and error is None and observed is not None and observed.get('component_acceptance') is True and not changed and not source_changes
    status = 'passed' if passed else 'failed'
    result = {'schema_version': 1, 'case_id': '003', 'status': status, 'started_at': started,
              'ended_at': datetime.now(timezone.utc).isoformat(), 'elapsed_seconds': time.monotonic() - tick,
              'command': command, 'cwd': str(ROOT), 'timeout_seconds': 40, 'exit_status': code, 'error': error,
              'implementation': source_ref, 'fixtures': ref(HERE / 'component-oracles.json'),
              'input_bundle': ref(HERE / 'component-inputs.json'), 'freeze': ref(freeze_path),
              'outputs': [ref(folder / 'stdout.json'), ref(folder / 'stderr.txt')],
              'counts': {'component_groups_passed': observed.get('passed') if observed else None,
                         'component_groups_total': observed.get('total') if observed else None},
              'component_acceptance': passed,
              'central_workflow': {'status': 'blocked', 'reason': 'No genuine authorized inference or implemented natural-language intent interface'},
              'B1': {'status': 'blocked_not_executed', 'capability_evidence': ref(capability)},
              'B2': {'status': 'structured_component_executed' if code is not None else 'not_executed', 'conversational_execution': False},
              'B3': {'status': 'not_observed'}, 'inference_executed': False, 'model_requests': 0,
              'exposure': 'independent_authored_exposed', 'hidden_evaluation_established': False,
              'product_acceptance': False, 'commercial_verdict': 'insufficient_evidence',
              'cost': {'value': None, 'unit': 'USD', 'classification': 'unknown', 'reason': 'No billing/local-resource allocation measurement; no paid API calls'},
              'preservation_manifest': ref(folder / 'preservation-before.json'), 'outside_review_files_checked': len(before),
              'outside_review_changed_paths': changed, 'source_changes': source_changes,
              'temporary_storage_removed': observed.get('temporary_storage_removed') if observed else None,
              'limitations': ['Trusted synthetic local API, not multi-user authorization',
                             'Audit hooks are not OS containment', 'Three explicitly labeled storage/readback fault injections',
                             'Atomic replacement observation is not crash/power-loss durability evidence',
                             'Successful structured controls are not natural-language normal-case wins']}
    save(folder / 'receipt.json', result)
    print(json.dumps({'receipt_path': str((folder / 'receipt.json').relative_to(ROOT)), **result}, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
