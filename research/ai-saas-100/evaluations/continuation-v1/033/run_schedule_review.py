"""Independent execution against archived scheduler source. No working-tree import."""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
CAMPAIGN = EVAL.parents[1]
ACTIVE = False
COUNTERS = {'network_calls': 0, 'external_writes': 0, 'secret_reads': 0,
            'outside_path_accesses': 0, 'calendar_writes': 0, 'events': []}
PRIMARY = [f'S-N{n}' for n in range(1, 9)] + [f'S-A{n}' for n in range(1, 7)]


def require(value, reason):
    if not value:
        raise AssertionError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def load(name, path):
    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def audit(event, args):
    if not ACTIVE:
        return
    COUNTERS['events'].append(event)
    if event.startswith(('socket.', 'subprocess.', 'os.exec', 'os.spawn')) or event in ['os.system']:
        COUNTERS['network_calls'] += 1
        return
    if event == 'open':
        COUNTERS['outside_path_accesses'] += 1
        mode = args[1] if len(args) > 1 else 'r'
        if isinstance(mode, int) or (isinstance(mode, str) and any(flag in mode for flag in 'wxa+')):
            COUNTERS['external_writes'] += 1


def effect_observation():
    return {
        'network_calls': COUNTERS['network_calls'],
        'external_writes': COUNTERS['external_writes'],
        'secret_reads': COUNTERS['secret_reads'],
        'outside_path_accesses': COUNTERS['outside_path_accesses'],
        'calendar_writes': COUNTERS['calendar_writes'],
        'measurement_scope': 'Python audit events during wrapped schedule calls; not OS containment',
    }


def verify_members(manifest):
    for row in manifest['members']:
        require('source-history' in row['path'] and 'scheduler-v1-6e16e7e43d6b5d1d' in row['path'],
                'Refusing non-archived member: ' + row['path'])
        require(sha(CAMPAIGN / row['path']) == row['sha256'], 'Archived snapshot member changed: ' + row['path'])
        require('cases/033/implementation/' not in row['path'] or 'source-history' in row['path'],
                'Working implementation path in snapshot')


def invoke_schedule(function, run, observer):
    global ACTIVE
    previous = ACTIVE
    ACTIVE = True
    try:
        return function(run, observer)
    finally:
        ACTIVE = previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    run_dir = args.config.parent
    manifest_path = CAMPAIGN / config['source_snapshot']['path']
    require(sha(manifest_path) == config['source_snapshot']['sha256'], 'Snapshot manifest changed')
    manifest = json.loads(manifest_path.read_text())
    verify_members(manifest)
    workflow_row = next(row for row in manifest['members'] if row['path'].endswith('implementation/workflow.py'))
    archived = (CAMPAIGN / workflow_row['path']).resolve()
    require('source-history' in archived.parts and 'scheduler-v1-6e16e7e43d6b5d1d' in archived.parts,
            'Refusing to import non-archived workflow')
    require(archived == (CAMPAIGN / 'cases/033/source-history/scheduler-v1-6e16e7e43d6b5d1d/implementation/workflow.py').resolve(),
            'Archived workflow path mismatch')
    working = (CAMPAIGN / 'cases/033/implementation/workflow.py').resolve()
    require(archived != working, 'Archived path resolved to working implementation')
    workflow = load('independent_archived_033_workflow', archived)
    require(Path(workflow.__file__).resolve() == archived, 'Loaded module is not the archived workflow')
    adapters = load('independent_033_adapters', EVAL / 'adapters.py')
    evaluator = load('independent_033_evaluator', EVAL / 'evaluate.py')
    suite = json.loads((EVAL / 'suite.json').read_text())
    require(suite['repeat_groups'] == ['N1', 'N4', 'N8'] and suite['extra_repeats'] == 2, 'Unexpected repeat contract')
    attempts = [{'test_id': name, 'attempt': 1} for name in PRIMARY]
    for extra in range(suite['extra_repeats']):
        for key in suite['repeat_groups']:
            attempts.append({'test_id': 'S-' + key, 'attempt': extra + 2})
    require(len(attempts) == 20, 'Expected 20 group attempts')
    sys.addaudithook(audit)
    results = []
    first = {}
    for item in attempts:
        test_id = item['test_id']
        bundle = json.loads((EVAL / 'inputs/033' / (test_id + '.json')).read_text())
        oracle = json.loads((EVAL / 'oracles/033' / (test_id + '.json')).read_text())
        require(oracle['test_id'] == test_id and bundle['test_id'] == test_id, 'Mismatched fixture identity')
        folder = run_dir / 'attempts' / f'{test_id}-attempt-{item["attempt"]}'
        folder.mkdir(parents=True, exist_ok=False)
        save(folder / 'input-identity.json', {'test_id': test_id, 'attempt': item['attempt'],
                                              'input_sha256': sha(EVAL / 'inputs/033' / (test_id + '.json')),
                                              'oracle_sha256': sha(EVAL / 'oracles/033' / (test_id + '.json')),
                                              'oracle_supplied_to_scheduler': False})
        observations = []
        started = time.monotonic()
        for run in bundle['runs']:
            for key in COUNTERS:
                COUNTERS[key] = 0 if key != 'events' else []
            require('scheduled_ids' not in run and 'kind' not in run, 'Oracle fields present on scheduler input')
            observed = invoke_schedule(lambda current, observer: adapters.call_workflow(workflow.schedule, current, observer),
                                       run, effect_observation)
            observed['system'] = 'B2'
            observations.append(observed)
        judged = evaluator.evaluate(bundle, oracle, observations)
        elapsed = time.monotonic() - started
        save(folder / 'observations.json', observations)
        save(folder / 'score.json', judged)
        row = {'test_id': test_id, 'attempt': item['attempt'], 'split': bundle['split'],
               'outcome': judged['outcome'], 'evaluation': judged, 'observations': observations,
               'elapsed_seconds': elapsed, 'oracles_supplied_to_scheduler': False,
               'invocation_count': len(bundle['runs'])}
        results.append(row)
        if item['attempt'] == 1:
            first[test_id] = judged['outcome']
    verify_members(manifest)
    require(Path(workflow.__file__).resolve() == archived, 'Module path changed after execution')
    outcomes = [row['outcome'] for row in results]
    passed_attempts = sum(o == 'passed' for o in outcomes)
    blocked_attempts = sum(o == 'blocked' for o in outcomes)
    failed_attempts = sum(o == 'failed' for o in outcomes)
    normal_first = sum(first[f'S-N{n}'] == 'passed' for n in range(1, 9))
    adversarial_first = sum(first[f'S-A{n}'] == 'passed' for n in range(1, 7))
    prohibited = 0
    for row in results:
        for observation in row['observations']:
            effects = observation.get('effects') or {}
            prohibited += sum(effects.get(key, 0) for key in
                              ['network_calls', 'external_writes', 'secret_reads', 'outside_path_accesses', 'calendar_writes'])
    report = {
        'schema_version': 1,
        'case_id': '033',
        'source_snapshot': config['source_snapshot'],
        'archived_workflow': str(archived.relative_to(CAMPAIGN)),
        'working_implementation_imported': False,
        'oracles_supplied_to_scheduler': False,
        'feasibility_witnesses_supplied_to_scheduler': False,
        'unique_groups': 14,
        'group_attempts': len(attempts),
        'planned_invocations': sum(row['invocation_count'] for row in results),
        'passed_attempts': passed_attempts,
        'blocked_attempts': blocked_attempts,
        'failed_attempts': failed_attempts,
        'normal_first_pass': normal_first,
        'adversarial_first_pass': adversarial_first,
        'thresholds': suite['thresholds'],
        'normal_threshold_met': normal_first >= suite['thresholds']['normal_pass_min'],
        'adversarial_threshold_met': adversarial_first >= suite['thresholds']['adversarial_pass_min'],
        'algorithm_correctness': failed_attempts == 0 and blocked_attempts == 0 and passed_attempts == 20,
        'search_limited_attempts': [row['test_id'] for row in results if row['outcome'] == 'blocked'],
        'failed_test_ids': [row['test_id'] for row in results if row['outcome'] == 'failed'],
        'prohibited_effects_observed': prohibited,
        'inference_executed': False,
        'baseline_executed': False,
        'B1_executed': False,
        'product_acceptance': False,
        'exposure': 'independent_authored_exposed',
        'results': results,
    }
    print(json.dumps(report, indent=2))
    return 0 if failed_attempts == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
