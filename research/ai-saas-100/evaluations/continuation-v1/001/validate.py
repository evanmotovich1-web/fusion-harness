"""Read-only verification of a selected case-001 evaluation run. Writes stdout only."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import types

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
ROOT = EVAL.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def check(value, reason):
    if not value:
        raise AssertionError(reason)


def main():
    folder = (HERE / 'runs' / sys.argv[1]).resolve()
    check(folder.parent == HERE / 'runs', 'Expected a single run-directory name')
    receipt = read(folder / 'receipt.json')
    report = read(folder / 'stdout.json')
    freeze = read(folder / 'freeze.json')
    for row in receipt['artifacts']:
        check(sha(ROOT / row['path']) == row['sha256'], 'Receipt artifact mismatch: ' + row['path'])
    for row in freeze['artifacts']:
        check(sha(ROOT / row['path']) == row['sha256'], 'Current frozen file changed: ' + row['path'])
        check(sha(ROOT / row['retained_copy']) == row['sha256'], 'Retained frozen copy changed')
    check(read(folder / 'preservation-before.json') == read(folder / 'preservation-after.json'),
          'Outside-review preservation mismatch')
    check(receipt['execution_status'] == 'completed' and receipt['evaluation_status'] == 'blocked',
          'Unexpected execution/evaluation status')
    check(receipt['retained_bindings_verified_after'] and not receipt['outside_review_changed_paths'],
          'Preservation not established')
    source = ROOT / receipt['source']['path']
    check(sha(source) == receipt['source']['sha256'], 'Source hash mismatch')
    cap = ROOT / receipt['capability']['path']
    check(sha(cap) == receipt['capability']['sha256'] and read(cap)['usable_authorized_route_established'] is False,
          'Capability mismatch')
    evaluator = types.ModuleType('validation_frozen_checker')
    exec(compile((EVAL / 'evaluate.py').read_bytes(), str(EVAL / 'evaluate.py'), 'exec'), evaluator.__dict__)
    names = [f'W-N{i}' for i in range(1, 9)] + [f'W-A{i}' for i in range(1, 7)]
    expected = [(name, 1) for name in names] + [('W-' + n, attempt) for attempt in (2, 3) for n in ('N1', 'N4', 'N8')]
    check([(r['test_id'], r['attempt']) for r in report['results']] == expected, 'Missing/reordered attempts')
    check(len(list((folder / 'attempts').iterdir())) == 20, 'Unexpected attempt directory count')
    groups, variants, statuses = Counter(), Counter(), Counter()
    count = 0
    for row in report['results']:
        attempt = folder / 'attempts' / f'{row["test_id"]}-attempt-{row["attempt"]}'
        check(read(attempt / 'receipt.json') == row, 'Per-group receipt differs from raw child output')
        bundle = read(ROOT / row['input']['path'])
        oracle = read(ROOT / row['oracle']['path'])
        observations = read(attempt / 'observations.json')
        scored = evaluator.evaluate(bundle, oracle, observations)
        check(scored == read(attempt / 'score.json') == row['evaluation'], 'Recomputed score differs')
        groups[scored['outcome']] += 1
        check(len(observations) == len(bundle['runs']) == len(row['invocations']), 'Variant denominator mismatch')
        for index, (observation, verdict) in enumerate(zip(observations, scored['variants'])):
            output = observation['output']
            check(read(attempt / f'invocation-{index}.output.json') == output, 'Raw returned output altered')
            check(observation['input_unchanged'] is True and observation['error'] is None, 'Invocation error/mutation')
            check(output['output'] is None and output['inference_executed'] is False, 'Fabricated inference/output')
            check('rewritten_text' not in output and 'semantic_review' not in observation, 'Fabricated semantic evidence')
            check(all(observation['effects'][key] == 0 for key in
                      ('network_calls', 'external_writes', 'secret_reads', 'outside_path_accesses', 'calendar_writes')),
                  'Nonzero prohibited effect')
            check(not observation['effects']['events'], 'Unaccounted prohibited event')
            check(row['invocations'][index]['unexpected_error'] is None, 'Unexpected invocation exception')
            statuses[output['status']] += 1
            variants[verdict['outcome']] += 1
            count += 1
    check(count == 22 and groups == Counter(passed=5, blocked=15) and variants == Counter(passed=7, blocked=15),
          'Unexpected full-denominator results')
    check(statuses == Counter(invalid_input=7, blocked_inference=15), 'Unexpected output statuses')
    check(report['B1']['planned_group_attempts'] == 20 and report['B1']['planned_invocations'] == 22
          and report['B1']['executed_invocations'] == 0, 'B1 denominator lost')
    check(report['product_acceptance'] is False and report['exposure'] == 'independent_authored_exposed',
          'Acceptance/exposure misstatement')
    print(json.dumps({'status': 'verified', 'receipt_sha256': sha(folder / 'receipt.json'),
                      'artifact_hashes_verified': len(receipt['artifacts']),
                      'frozen_artifacts_verified': len(freeze['artifacts']),
                      'group_attempts': 20, 'local_invocations': count,
                      'group_outcomes': dict(groups), 'invocation_outcomes': dict(variants),
                      'capability_sha256': sha(cap), 'source_sha256': sha(source),
                      'product_acceptance': False}, indent=2))


if __name__ == '__main__':
    main()
