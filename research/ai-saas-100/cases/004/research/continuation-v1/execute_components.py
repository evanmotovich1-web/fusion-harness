"""Append source-bound receipts for the two implemented batch components only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools'))
from receipt import receipt_template


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ref(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha(path.read_bytes())}


def append(path, data):
    path.parent.mkdir(exist_ok=True, parents=True)
    with path.open('xb') as stream:
        stream.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case_id', choices=['006', '007'])
    args = parser.parse_args()
    cid = args.case_id
    component, source = ('enrichment-v1', 'enrichment.py') if cid == '006' else ('support-evidence-v1', 'support_evidence.py')
    case = ROOT / 'cases' / cid
    names = ['implementation/' + source, 'implementation/README.md',
             'tests/' + component + '/fixtures.json', 'tests/' + component + '/run.py',
             'tests/' + component + '/freeze.json', 'tests/specification.json']
    data = {name: (case / name).read_bytes() for name in names}
    data['receipt-driver.py'] = Path(__file__).read_bytes()
    hashes = {name: sha(value) for name, value in data.items()}
    archive = case / 'implementation/source-history' / sha(encoded(hashes))
    archive.mkdir(parents=True, exist_ok=True)
    entries = []
    for name, value in data.items():
        target = archive / name
        if target.exists():
            if target.read_bytes() != value:
                raise ValueError('Source snapshot mismatch')
        else:
            append(target, value)
        entries.append({'original_path': str(Path(__file__).relative_to(ROOT)) if name == 'receipt-driver.py'
                        else str((case / name).relative_to(ROOT)), **ref(target)})
    manifest_path = archive / 'manifest.json'
    manifest = encoded({'schema_version': 1, 'case_id': cid, 'files': entries})
    if manifest_path.exists():
        if manifest_path.read_bytes() != manifest:
            raise ValueError('Manifest mismatch')
    else:
        append(manifest_path, manifest)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run_id = cid + '-' + component + '-' + stamp
    runner = case / 'tests' / component / 'run.py'
    command = [sys.executable, '-B', str(runner)]
    receipt = receipt_template(cid, run_id)
    receipt.update(started_at=datetime.now(timezone.utc).isoformat(), command=command, cwd=str(ROOT),
                   implementation=ref(manifest_path), fixtures=ref(archive / ('tests/' + component + '/fixtures.json')),
                   input_bundle=ref(manifest_path), runtime={'python': platform.python_version(), 'platform': platform.system()},
                   configuration={'timeout_seconds': 15, 'network': False, 'model_calls': 0,
                                  'mode': 'builder_visible_local_component', 'input_bundle_scope': 'Source/fixture manifest, not model input'},
                   execution_kind='real', product_acceptance=False, original_product_status='not_observed',
                   human_interventions=['Component tests authored and visible to builder, not hidden evaluation'],
                   missing_capabilities=['Central model-dependent behavior', 'Generic-model baseline', 'Independent hidden review'])
    tick = time.monotonic()
    stdout, stderr = b'', b''
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=15)
        stdout, stderr = result.stdout, result.stderr
        receipt.update(exit_status=result.returncode, status='completed' if result.returncode == 0 else 'failed')
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = exc.stdout or b'', exc.stderr or b''
        receipt.update(exit_status=-1, status='failed', errors=['TimeoutExpired; exit -1 is an unobserved-status sentinel'], timeouts=[15])
    except OSError as exc:
        receipt.update(exit_status=-1, status='failed', execution_kind='unknown', errors=['Launch failure: ' + str(exc)])
    elapsed = time.monotonic() - tick
    receipt['ended_at'] = datetime.now(timezone.utc).isoformat()
    receipt['latency'] = {'value': elapsed, 'unit': 'seconds', 'classification': 'measured', 'category': 'latency',
                          'assumptions': ['Full component suite wall time, not SaaS latency'], 'unknown_reason': None}
    for suffix, content in [('stdout.json', stdout), ('stderr.txt', stderr)]:
        target = case / 'receipts' / (run_id + '.' + suffix)
        append(target, content)
        receipt['outputs'].append(ref(target))
    passed = False
    try:
        rows = json.loads(stdout)['results']
        receipt['test_results'] = [{'test_id': r['test_id'], 'outcome': r['outcome']} for r in rows]
        expected = [f['id'] for f in json.loads((case / 'tests' / component / 'fixtures.json').read_text())['cases']]
        expected += [f['test_id'] for f in json.loads((case / 'tests/specification.json').read_text())['cases']]
        ids = [r['test_id'] for r in rows]
        passed = len(ids) == len(set(ids)) and set(ids) == set(expected) and all(r['outcome'] == 'passed' for r in rows)
    except (ValueError, KeyError, TypeError) as exc:
        receipt['errors'].append('Malformed test output: ' + str(exc))
    passed = passed and receipt['exit_status'] == 0 and not receipt['errors']
    historical = json.loads((case / 'research/continuation-v1/preservation.json').read_text())['historical_files']
    changed = [name for name, digest in historical.items() if not (case / name).is_file() or sha((case / name).read_bytes()) != digest]
    source_changes = [name for name in names if sha((case / name).read_bytes()) != hashes[name]]
    passed = passed and not changed and not source_changes
    receipt['component_check_passed'] = passed
    receipt_path = case / 'receipts' / (run_id + '.json')
    append(receipt_path, encoded(receipt))
    checkpoint = {'schema_version': 1, 'case_id': cid, 'recorded_at': datetime.now(timezone.utc).isoformat(),
                  'component_status': 'tested' if passed else 'failed', 'receipt': ref(receipt_path),
                  'source_snapshot': ref(manifest_path), 'passed_component_rows': sum(r['outcome'] == 'passed' for r in receipt['test_results']),
                  'total_component_rows': len(receipt['test_results']), 'historical_files_changed': changed,
                  'sources_changed_during_run': source_changes, 'central_workflow_complete': False,
                  'product_accepted': False, 'baseline_executed': False, 'inference_executed': False,
                  'remaining': receipt['missing_capabilities'], 'cost_classification': 'unknown'}
    checkpoint_path = case / 'receipts' / (run_id + '-checkpoint.json')
    append(checkpoint_path, encoded(checkpoint))
    print(json.dumps({'checkpoint_path': str(checkpoint_path.relative_to(ROOT)), **checkpoint}, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
