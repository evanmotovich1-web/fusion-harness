"""Execute exposed fixtures, recomputing constraints without trusting solver flags."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import sys
import time

HERE = Path(__file__).resolve().parent
CASE = HERE.parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert sys.flags.optimize == 0
    source = CASE / 'implementation/workflow.py'
    spec = importlib.util.spec_from_file_location('local_scheduler', source)
    workflow = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(workflow)
    checker = runpy.run_path(str(HERE / 'checks.py'))['verify']
    inputs = json.loads((HERE / 'inputs.json').read_text())['cases']
    oracles = json.loads((HERE / 'oracles.json').read_text())['cases']
    assert [row['id'] for row in inputs] == [row['id'] for row in oracles]
    guard = {'active': False, 'events': []}
    def audit(event, args):
        if guard['active'] and (event == 'open' or event.startswith(('socket.', 'subprocess.', 'os.'))):
            guard['events'].append(event)
            raise AssertionError('prohibited_side_effect: ' + event)
    sys.addaudithook(audit)
    rows = []
    first_valid = None
    for fixture, expected in zip(inputs, oracles):
        request = copy.deepcopy(fixture['request'])
        before = copy.deepcopy(request)
        t = time.monotonic()
        row = {'test_id': fixture['id']}
        attempts = len(guard['events'])
        try:
            guard['active'] = True
            try:
                result = workflow.schedule(request, node_limit=fixture['node_limit'])
            finally:
                guard['active'] = False
            row['output'] = result
            assert request == before, 'input_mutation'
            assert len(guard['events']) == attempts, 'side_effect_attempt'
            if expected['invalid_input']:
                assert result['status'] == 'invalid_input'
                assert result['error']['code'] and result['error']['field']
                assert not result['scheduled'] and not result['unscheduled'] and result['calendar_writes'] == 0
            else:
                ids = checker(before, result)
                assert ids == expected['scheduled_ids'], (ids, expected['scheduled_ids'])
                assert (result['status'] == 'search_limited') == expected['search_limited']
                if expected['search_limited']:
                    assert all(r['proof'] == 'not_established' for r in result['unscheduled'])
                if first_valid is None and len(result['scheduled']) > 1:
                    first_valid = (before, copy.deepcopy(result))
            row['outcome'] = 'passed'
        except Exception as exc:
            row.update(outcome='failed', error=type(exc).__name__ + ': ' + str(exc))
        row.update(elapsed_seconds=time.monotonic() - t, side_effect_attempts=len(guard['events']) - attempts)
        rows.append(row)
    self_tests = []
    if first_valid:
        request, good = first_valid
        bads = []
        bad = copy.deepcopy(good);bad['scheduled'][1]['start'] = bad['scheduled'][0]['start'];bads.append(('overlap', bad))
        bad = copy.deepcopy(good);bad['scheduled'].pop(0);bads.append(('missing_minutes', bad))
        bad = copy.deepcopy(good);bad['scheduled'][0]['task_id'] = 'invented';bads.append(('invented_task', bad))
        bad = copy.deepcopy(good);bad['scheduled'].append(copy.deepcopy(bad['scheduled'][0]));bads.append(('duplicate_work', bad))
        bad = copy.deepcopy(good);bad['calendar_writes'] = 1;bads.append(('calendar_write_claim', bad))
        for name, bad in bads:
            try:
                checker(request, bad)
                outcome = 'failed'
            except AssertionError:
                outcome = 'passed'
            self_tests.append({'test_id': 'checker-' + name, 'outcome': outcome})
    assert len(self_tests) == 5
    failed = sum(row['outcome'] == 'failed' for row in rows + self_tests)
    print(json.dumps({'schema_version': 1, 'case_id': '033', 'source_sha256': digest(source),
                      'input_bundle_sha256': digest(HERE / 'inputs.json'), 'oracle_sha256': digest(HERE / 'oracles.json'),
                      'checker_sha256': digest(HERE / 'checks.py'), 'results': rows, 'checker_self_tests': self_tests,
                      'passed': len(rows) - sum(row['outcome'] == 'failed' for row in rows), 'failed': failed,
                      'side_effect_attempts': guard['events'], 'held_out': False, 'model_calls': 0, 'product_acceptance': False}, indent=2))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
