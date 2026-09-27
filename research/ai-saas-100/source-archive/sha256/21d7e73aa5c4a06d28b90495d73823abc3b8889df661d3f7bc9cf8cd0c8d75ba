"""Read-only integrity check for the explicit campaign execution manifest. Never launches jobs."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = ('cases/002/tests/repair-v2/execute.py', 'cases/002/tests/repair-v2/validate.py',
             'cases/001/research/build_dossiers.py', 'cases/001/research/capture.py',
             'cases/033/tests/scheduler-v1/materialize.py')


def check(manifest, root=ROOT):
    verified = set()
    def reference(item):
        path = (root / item['path']).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError('Missing or escaping reference: ' + item['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Hash mismatch: ' + item['path'])
        verified.add(item['path'])
    def walk(value):
        if isinstance(value, dict):
            if 'path' in value and 'sha256' in value:
                reference(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(manifest)
    if manifest['schema_version'] != 1 or [c['case_id'] for c in manifest['cases']] != ['001', '002', '003', '033']:
        raise ValueError('Unexpected manifest cases/schema')
    bindings = manifest['source_bindings']
    active = {b['active']['path'] for b in bindings}
    if len(active) != len(bindings):
        raise ValueError('Duplicate source binding')
    for b in bindings:
        if b['active']['sha256'] != b['snapshot']['sha256']:
            raise ValueError('Snapshot differs from executing source')
    commands = manifest['commands']
    if len({c['id'] for c in commands}) != len(commands):
        raise ValueError('Duplicate command ID')
    for command in commands:
        argv = command['argv']
        if not 0 < command['timeout_seconds'] <= 60 or command['cwd'] != 'repository_root':
            raise ValueError('Unbounded command or unexpected cwd')
        if not argv or argv[0] != 'python3' or any(not isinstance(a, str) for a in argv):
            raise ValueError('Expected explicit Python argv')
        if any(any(a.endswith(f) for f in FORBIDDEN) for a in argv):
            raise ValueError('Historical writer invocation forbidden')
        expected = 'research/ai-saas-100/' + command['entrypoint']['path']
        if expected not in argv or command['entrypoint']['path'] not in active:
            raise ValueError('Command entrypoint lacks source binding')
        if not set(command['source_components']) <= active:
            raise ValueError('Command component missing source binding')
    jobs = json.loads((root / manifest['runner_jobs']['path']).read_text())
    for job in jobs:
        for field in ('runner', 'implementation'):
            if job[field] not in active:
                raise ValueError('Runner job source is unbound')
        if job['command'] != ['python3', '-I', '-B', job['runner']]:
            raise ValueError('Runner argv does not match selected entrypoint')
        if any(job['runner'].endswith(f) for f in FORBIDDEN):
            raise ValueError('Forbidden writer in runner jobs')
        if job['suite'] not in verified or job['input_bundle'] not in verified:
            raise ValueError('Job data not hash-bound')
        suite = json.loads((root / job['suite']).read_text())
        ids = [c['id'] for c in suite['cases']]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError('Invalid chosen suite IDs')
    for case in manifest['cases']:
        if not set(case['source_components']) <= active:
            raise ValueError('Case source component unbound')
        if case['product_acceptance'] is not False:
            raise ValueError('Manifest cannot confer product acceptance')
        for arm in case['arms']:
            if arm['status'].startswith('blocked') and arm['command_ids']:
                raise ValueError('Blocked arm has executable commands')
        comparison = case['comparison']
        if comparison['ready_inputs'] and (comparison['inputs'] is None or comparison['oracle'] is None
                                          or comparison['inputs']['path'] == comparison['oracle']['path']):
            raise ValueError('Comparison inputs must be separate from oracle')
    return {'valid': True, 'verified_unique_files': len(verified), 'source_components': len(bindings),
            'case_ids': [c['case_id'] for c in manifest['cases']], 'suite_execution_performed': False}


if __name__ == '__main__':
    try:
        print(json.dumps(check(json.loads((ROOT / 'execution-manifest.json').read_text())), indent=2))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({'valid': False, 'error': str(exc)}))
        raise SystemExit(1)
