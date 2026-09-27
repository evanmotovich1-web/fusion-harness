"""Freeze evaluator bytes, run only offline synthetic self-tests, append receipts."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
CAMPAIGN = ROOT.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def preserved():
    values = {}
    for path in sorted(CAMPAIGN.rglob('*')):
        if ROOT in path.parents or path == ROOT:
            continue
        if path.is_symlink():
            values[str(path.relative_to(CAMPAIGN))] = {'symlink': os.readlink(path)}
        elif path.is_file():
            values[str(path.relative_to(CAMPAIGN))] = sha(path)
    return values


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8]
    directory = ROOT / 'selftest-receipts' / stamp
    directory.mkdir(parents=True, exist_ok=False)
    before = preserved()
    save(directory / 'preservation-before.json', before)
    artifacts = []
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file() or 'selftest-receipts' in path.relative_to(ROOT).parts:
            continue
        if '__pycache__' in path.parts:
            raise ValueError('Unexpected bytecode artifact in versioned evaluator')
        artifacts.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path)})
    freeze_path = directory / 'freeze.json'
    save(freeze_path, {'schema_version': 1, 'frozen_at': datetime.now(timezone.utc).isoformat(),
                       'exposure': 'independent_authored_exposed', 'held_out': False,
                       'scope': 'Evaluator code, inputs, oracles and adapters frozen before self-tests', 'artifacts': artifacts})
    environment = os.environ.copy()
    environment['EVALUATOR_FREEZE'] = str(freeze_path)
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    command = [sys.executable, '-B', str(ROOT / 'test_evaluator.py')]
    started = datetime.now(timezone.utc).isoformat(); tick = time.monotonic()
    code, out, err, error = None, b'', b'', None
    try:
        child = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, timeout=40)
        code, out, err = child.returncode, child.stdout, child.stderr
    except subprocess.TimeoutExpired as exc:
        out, err, error = exc.stdout or b'', exc.stderr or b'', 'self_test_timeout'
    except OSError as exc:
        error = type(exc).__name__ + ': ' + str(exc)
    for suffix, content in [('stdout.bin', out), ('stderr.bin', err)]:
        with (directory / suffix).open('xb') as stream:
            stream.write(content)
    after = preserved()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    altered = [row['path'] for row in artifacts if not (ROOT / row['path']).is_file() or sha(ROOT / row['path']) != row['sha256']]
    result = {'schema_version': 1, 'scope': 'Evaluator self-tests only using synthetic observations and test doubles',
              'started_at': started, 'ended_at': datetime.now(timezone.utc).isoformat(),
              'duration_seconds': time.monotonic() - tick, 'command': command, 'timeout_seconds': 40,
              'exit_status': code, 'error': error, 'status': 'passed' if code == 0 and error is None and not changed and not altered else 'failed',
              'freeze': {'path': str(freeze_path.relative_to(ROOT)), 'sha256': sha(freeze_path)},
              'outputs': [{'path': str((directory / name).relative_to(ROOT)), 'sha256': sha(directory / name)} for name in ['stdout.bin', 'stderr.bin']],
              'preservation_before': {'path': str((directory / 'preservation-before.json').relative_to(ROOT)), 'sha256': sha(directory / 'preservation-before.json')},
              'outside_evaluator_files_checked': len(before), 'outside_evaluator_changed_paths': changed,
              'frozen_artifacts_changed': altered, 'product_modules_executed': False,
              'inference_executed': False, 'product_acceptance': False, 'held_out': False}
    save(directory / 'result.json', result)
    print(json.dumps({'receipt': str((directory / 'result.json').relative_to(CAMPAIGN)), **result}, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
