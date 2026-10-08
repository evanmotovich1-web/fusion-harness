"""Independent execution against the archived case 002 marketplace source. Stdout only."""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
ACTIVE = False
EVENTS = []


def require(value, reason):
    if not value:
        raise AssertionError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(name, path):
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


def audit(event, args):
    if not ACTIVE:
        return
    prohibited = (event.startswith(('socket.', 'subprocess.', 'os.exec', 'os.spawn'))
                  or event in ['os.system', 'os.chdir'])
    recorded = {'event': event, 'prohibited': prohibited}
    if event == 'open' and isinstance(args[0], (str, bytes)):
        recorded.update(kind='open', path=str(args[0]))
        recorded['prohibited'] = True
    if prohibited or recorded.get('kind') == 'open':
        EVENTS.append(recorded)


def observer():
    require(not any(event['prohibited'] for event in EVENTS),
            'Prohibited effect during marketplace execution: ' + json.dumps(EVENTS))
    return {'network_calls': 0, 'external_writes': 0, 'secret_reads': 0,
            'outside_path_accesses': 0, 'calendar_writes': 0,
            'measurement_scope': 'Python audit events during wrapped marketplace calls; not OS containment'}


def invoke_execution(function, module, run):
    global ACTIVE
    EVENTS.clear()
    ACTIVE = True
    try:
        observation = function(module, run, observer)
    except Exception as exc:  # effect violations or unexpected implementation faults
        observation = {'trace': None, 'final_state': None, 'input_unchanged': False,
                       'effects': None, 'execution_error': type(exc).__name__ + ': ' + str(exc)}
    finally:
        ACTIVE = False
    if EVENTS:
        observation['audit_events'] = deepcopy(EVENTS)
    return observation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    root = Path(config['root'])
    snapshot = root / config['source_snapshot']['path']
    require(sha(snapshot) == config['source_snapshot']['sha256'], 'Archived marketplace source hash mismatch')
    active = root / config['active_source']['path']
    active_matches = sha(active) == config['active_source']['sha256'] == config['source_snapshot']['sha256']
    require(active_matches, 'Active marketplace source diverged from manifest binding')

    for name, entry in config['evaluator_components'].items():
        require(sha(root / entry['path']) == entry['sha256'], 'Frozen evaluator component changed: ' + name)

    sys.addaudithook(audit)
    market = load('marketplace_under_review_002', snapshot)
    adapters = load('adapters_frozen_002', root / config['evaluator_components']['adapters']['path'])
    checker = load('evaluate_frozen_002', root / config['evaluator_components']['evaluate']['path'])
    suite = json.loads((root / config['evaluator_components']['suite']['path']).read_text())
    capability = json.loads((root / config['capability_evidence']['path']).read_text())
    require(capability['usable_authorized_route_established'] is False,
            'Capability evidence changed; reassess B1 before using this frozen configuration')

    groups = config['groups']
    repeat_ids = set(suite['repeat_groups'])
    extra = suite['extra_repeats']
    attempts, invocation_count = [], 0
    for group in groups:
        bundle = json.loads((root / group['input']['path']).read_text())
        oracle = json.loads((root / group['oracle']['path']).read_text())
        require(bundle['case_id'] == '002' and bundle['test_id'] == oracle['test_id'], 'Fixture identity mismatch')
        repetitions = 1 + (extra if bundle['test_id'].replace('M-', '') in repeat_ids else 0)
        for attempt_index in range(repetitions):
            observations = [invoke_execution(adapters.execute_market, market, run) for run in bundle['runs']]
            invocation_count += len(observations)
            verdict = checker.evaluate(bundle, oracle, observations)
            attempts.append({'test_id': bundle['test_id'], 'attempt': attempt_index + 1,
                             'attempt_id': bundle['test_id'] + '#' + str(attempt_index + 1),
                             'split': bundle['split'], 'outcome': verdict['outcome'],
                             'invocations': len(observations), 'variants': verdict['variants']})

    base = [a for a in attempts if a['attempt'] == 1]
    thresholds = suite['thresholds']
    summary = {
        'normal_base_passed': sum(1 for a in base if a['split'] == 'normal' and a['outcome'] == 'passed'),
        'normal_base_total': sum(1 for a in base if a['split'] == 'normal'),
        'adversarial_base_passed': sum(1 for a in base if a['split'] == 'adversarial' and a['outcome'] == 'passed'),
        'adversarial_base_total': sum(1 for a in base if a['split'] == 'adversarial'),
    }
    all_passed = all(a['outcome'] == 'passed' for a in attempts)
    denominators_complete = (len(attempts) == config['planned_group_attempts']
                             and invocation_count == config['planned_invocations'])
    result = {
        'schema_version': 1, 'case_id': '002', 'system': 'independent_local_component',
        'source': {'snapshot': config['source_snapshot'], 'active': config['active_source'],
                   'active_matches_snapshot_and_manifest': True},
        'attempts': attempts,
        'counts': {
            'group_attempts': len(attempts), 'invocations': invocation_count,
            'planned_group_attempts': config['planned_group_attempts'],
            'planned_invocations': config['planned_invocations'],
            'denominators_complete': denominators_complete,
            'passed': sum(1 for a in attempts if a['outcome'] == 'passed'),
            'failed': sum(1 for a in attempts if a['outcome'] == 'failed'),
            'blocked': sum(1 for a in attempts if a['outcome'] == 'blocked'),
            **summary,
        },
        'threshold_check': {
            'note': 'Informational only. Weighted scoring, usability judgment, and acceptance require independent review.',
            'normal_pass_min': thresholds['normal_pass_min'],
            'adversarial_pass_min': thresholds['adversarial_pass_min'],
            'normal_base_passed': summary['normal_base_passed'],
            'adversarial_base_passed': summary['adversarial_base_passed'],
            'normal_threshold_met': summary['normal_base_passed'] >= thresholds['normal_pass_min'],
            'adversarial_threshold_met': summary['adversarial_base_passed'] >= thresholds['adversarial_pass_min'],
        },
        'local_component_acceptance': bool(all_passed and denominators_complete),
        'inference_executed': False, 'model_requests': 0,
        'B1': {'status': 'blocked_not_executed', 'reason': 'No authorized inference route',
               'capability_evidence': config['capability_evidence']},
        'B3': {'status': 'not_observed'},
        'exposure': 'independent_authored_exposed', 'hidden_evaluation_established': False,
        'product_acceptance': False,
        'limitations': [
            'Local deterministic subset only; editorial judgment and live marketplace behavior unassessed',
            'Passing exposed assertions establishes component correctness, not product acceptance',
            'Audit hooks are instrumentation, not OS containment',
            'B1 absence is a missing capability, not a failed comparison',
        ],
    }
    print(json.dumps(result, indent=2))
    return 0 if result['local_component_acceptance'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
