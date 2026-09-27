"""Independent execution against archived CRM source, in disposable local storage."""
import argparse
from copy import deepcopy as cp
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
CAMPAIGN = EVAL.parents[1]
ACTIVE = False
STORE_ROOT = None
EVENTS = []


def require(value, reason):
    if not value:
        raise AssertionError(reason)


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(event, args):
    if not ACTIVE:
        return
    if event.startswith(('socket.', 'subprocess.', 'os.exec', 'os.spawn')) or event in ['os.system', 'os.chdir']:
        EVENTS.append({'event': event, 'prohibited': True})
        raise AssertionError('Prohibited network/process effect: ' + event)
    paths = []
    if event == 'open' and isinstance(args[0], (str, bytes)):
        paths = [args[0]]
    elif event in ['os.rename', 'os.link', 'os.symlink']:
        paths = list(args[:2])
    elif event in ['os.mkdir', 'os.rmdir', 'os.remove', 'os.chmod', 'os.chown', 'os.truncate']:
        paths = list(args[:1])
    for value in paths:
        if isinstance(value, (str, bytes)):
            path = Path(os.fsdecode(value)).absolute()
            if not path.is_relative_to(STORE_ROOT):
                EVENTS.append({'event': event, 'prohibited': True, 'path': str(path)})
                raise AssertionError('Outside temporary store access: ' + str(path))
    if paths:
        EVENTS.append({'event': event, 'prohibited': False})


def invoke(function, *args, **kwargs):
    global ACTIVE
    previous = ACTIVE
    ACTIVE = True
    try:
        return function(*args, **kwargs)
    finally:
        ACTIVE = previous


def effect_observation():
    require(not any(e['prohibited'] for e in EVENTS), 'Prohibited effect was attempted')
    return dict(network_calls=0, external_writes=0, secret_reads=0, outside_path_accesses=0, calendar_writes=0,
                measurement_scope='Python audit events during wrapped calls, including actual local persistence; not OS containment')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def fresh(p, name):
    return invoke(lambda: p.SyntheticStore(name).read())


def raw_state(store):
    return json.loads(store.path.read_text())


def rejection(store, function, reason):
    before = store.path.read_bytes()
    try:
        invoke(function)
    except (ValueError, OSError) as exc:
        require(reason in str(exc), 'Unexpected rejection: ' + str(exc))
        require(store.path.read_bytes() == before, 'Rejected operation changed serialized store')
        return {'error_type': type(exc).__name__, 'error': str(exc), 'raw_store_unchanged': True,
                'before_sha256': hashlib.sha256(before).hexdigest(), 'after_sha256': sha(store.path)}
    raise AssertionError('Expected rejection: ' + reason)


def successful(p, store, fixture, oracle):
    initial = fresh(p, store.root.name)
    request = cp(fixture['request']); preserved_request = cp(request)
    proposal = invoke(store.propose, request)
    proposed_copy = cp(proposal)
    require(request == preserved_request, 'Request mutated')
    require(proposal['before'] == fixture['contacts'] and proposal['after'] == oracle['after'], 'Incorrect proposed records')
    require(proposal['changes'] == oracle['changes'], 'Incorrect exact change list')
    require(proposal['no_op'] is oracle['no_op'], 'Wrong no-op flag')
    require(proposal['source_contacts_sha256'] == digest(fixture['contacts']) and proposal['source_revision'] == 1,
            'Proposal source binding incorrect')
    require(proposal['store_id'] == initial['store_id'], 'Proposal bound to wrong store')
    require(fresh(p, store.root.name) == initial, 'Proposal changed preapproval domain data')
    approval = invoke(store.decide, proposal, True)
    approval_copy = cp(approval)
    require(approval['proposal_sha256'] == digest(proposal), 'Approval not bound to complete proposal')
    require(approval['source_revision'] == 1 and approval['store_id'] == initial['store_id'] and approval['proposal_id'] == proposal['proposal_id'],
            'Approval identity binding incorrect')
    require(fresh(p, store.root.name) == initial, 'Approval changed domain data')
    before_commit = raw_state(store)
    result = invoke(store.apply, proposal, approval)
    reopened = fresh(p, store.root.name)
    after_commit = raw_state(store)
    require(reopened == result['store'] and reopened['contacts'] == oracle['after'] and reopened['revision'] == 2,
            'Persisted result or revision incorrect')
    require(result['readback_verified'] is True and result['real_crm_written'] is False and result['messages_sent'] == 0,
            'False readback/external-effect claim')
    require(result['inference_executed'] is False, 'Structured component claimed inference')
    require(result['status'] == ('applied_noop' if oracle['no_op'] else 'applied'), 'Incorrect no-op/application status')
    require(proposal == proposed_copy and approval == approval_copy, 'Apply changed caller proposal or approval')
    entry = after_commit['proposals'][proposal['proposal_id']]
    require(entry['status'] == 'applied' and entry['applied_revision'] == 2, 'Approval consumption missing from committed state')
    replay = rejection(store, lambda: p.SyntheticStore(store.root.name).apply(proposal, approval), 'proposal_replayed')
    return dict(proposal=proposal, approval=approval, initial=initial, before_commit=before_commit,
                after_commit=after_commit, result=result, reopened=reopened, replay=replay,
                preapproval_domain_unchanged=True, proposal_metadata_was_persisted=True)


def control(p, store, fixture, oracle):
    operation = fixture['operation']
    proposal = invoke(store.propose, cp(fixture['request']))
    if operation == 'unapproved':
        return rejection(store, lambda: store.apply(proposal, None), 'proposal_unapproved')
    if operation == 'denied':
        invoke(store.decide, proposal, False)
        return {'apply': rejection(store, lambda: store.apply(proposal, None), 'proposal_denied'),
                'reapproval': rejection(store, lambda: store.decide(proposal, True), 'proposal_already_decided')}
    if operation == 'stale_before_approval':
        other = invoke(store.propose, fixture['intervening_request'])
        invoke(store.apply, other, invoke(store.decide, other, True))
        result = rejection(store, lambda: store.decide(proposal, True), 'stale_proposal')
        require(fresh(p, store.root.name)['contacts'][2]['note'] == 'Independent authorized edit', 'Lost independent edit')
        return result
    approval = invoke(store.decide, proposal, True)
    if operation == 'stale_after_approval':
        other = invoke(store.propose, fixture['intervening_request'])
        invoke(store.apply, other, invoke(store.decide, other, True))
        result = rejection(store, lambda: store.apply(proposal, approval), 'stale_proposal')
        require(fresh(p, store.root.name)['contacts'][2]['note'] == 'Independent authorized edit', 'Lost independent edit')
        return result
    if operation == 'tampered_proposal':
        variants = [('after', []), ('changes', []), ('before', []), ('source_revision', True),
                    ('source_contacts_sha256', '0' * 64), ('store_id', 'other'), ('no_op', True)]
        rows = []
        for key, value in variants:
            altered = cp(proposal); altered[key] = value
            rows.append({'field': key, **rejection(store, lambda: store.apply(altered, approval), 'proposal_altered')})
        return rows
    if operation == 'tampered_approval':
        rows = []
        for key, value in [('approval_id', 'other'), ('proposal_id', 'other'), ('store_id', 'other'),
                           ('source_revision', True), ('proposal_sha256', '0' * 64)]:
            altered = cp(approval); altered[key] = value
            rows.append({'field': key, **rejection(store, lambda: store.apply(proposal, altered), 'approval_mismatch')})
        return rows
    if operation == 'cross_store_approval':
        other = invoke(p.SyntheticStore, 'other_' + store.root.name)
        invoke(other.initialize, cp(fixture['contacts']))
        other_proposal = invoke(other.propose, fixture['request'])
        other_approval = invoke(other.decide, other_proposal, True)
        return rejection(store, lambda: store.apply(proposal, other_approval), 'approval_mismatch')
    if operation == 'replay_after_fresh_open':
        invoke(store.apply, proposal, approval)
        return rejection(store, lambda: p.SyntheticStore(store.root.name).apply(proposal, approval), 'proposal_replayed')
    if operation == 'bounded_lock_contention':
        with store._locked():
            return rejection(store, lambda: p.SyntheticStore(store.root.name).apply(proposal, approval), 'store_busy')
    if operation == 'replace_failure':
        with patch.object(p.os, 'replace', side_effect=OSError('independent_injected_replace_failure')):
            result = rejection(store, lambda: store.apply(proposal, approval), 'independent_injected_replace_failure')
        require(not list(store.root.glob('.state-*.tmp')), 'Uncommitted temporary file leaked')
        invoke(store.apply, proposal, approval)
        require(fresh(p, store.root.name)['contacts'] == oracle['after'], 'Retry after precommit failure lost data')
        return {'fault_injection': 'before atomic replacement', 'failure': result, 'retry': fresh(p, store.root.name)}
    if operation == 'atomic_transition':
        real_replace = p.os.replace
        frames = []
        def observe_replace(source, destination):
            old = json.loads(Path(destination).read_text())
            new = json.loads(Path(source).read_text())
            frames.append({'old': old, 'new': new})
            require(old['revision'] == 1 and new['revision'] == 2, 'Unexpected atomic revision boundary')
            require(old['contacts'] == fixture['contacts'] and new['contacts'] == oracle['after'], 'Split domain transition')
            pid = proposal['proposal_id']
            require(old['proposals'][pid]['status'] == 'approved' and new['proposals'][pid]['status'] == 'applied',
                    'Approval consumption not part of same replacement')
            real_replace(source, destination)
        with patch.object(p.os, 'replace', side_effect=observe_replace):
            invoke(store.apply, proposal, approval)
        require(len(frames) == 1, 'Expected one committing replacement')
        return {'replacement_frames': frames, 'fresh_read': fresh(p, store.root.name),
                'limitation': 'Observed real atomic replacement, not a crash/power-loss durability test'}
    if operation == 'post_commit_fsync_failure':
        real_fsync = p.os.fsync
        calls = []
        def failed_directory_sync(fd):
            calls.append(fd)
            if len(calls) == 2:
                raise OSError('independent_injected_directory_fsync_failure')
            return real_fsync(fd)
        with patch.object(p.os, 'fsync', side_effect=failed_directory_sync):
            try:
                invoke(store.apply, proposal, approval)
            except OSError as exc:
                require('independent_injected_directory_fsync_failure' in str(exc), 'Wrong storage error')
            else:
                raise AssertionError('Postcommit storage failure reported success')
        require(fresh(p, store.root.name)['contacts'] == oracle['after'], 'Postcommit state reconciliation failed')
        rejection(store, lambda: store.apply(proposal, approval), 'proposal_replayed')
        return {'fault_injection': 'directory fsync after replacement', 'calls': len(calls), 'reconciled': fresh(p, store.root.name),
                'rollback_claimed': False}
    if operation == 'readback_failure':
        actual_load = store._load
        calls = []
        def changed_readback():
            state = actual_load(); calls.append(1)
            if len(calls) == 2:
                state['contacts'][2]['note'] = 'independent_readback_mismatch'
            return state
        with patch.object(store, '_load', side_effect=changed_readback):
            try:
                invoke(store.apply, proposal, approval)
            except ValueError as exc:
                require(str(exc) == 'readback_mismatch', 'Wrong readback error')
            else:
                raise AssertionError('Altered readback reported success')
        require(fresh(p, store.root.name)['contacts'] == oracle['after'], 'Failed reconciliation after readback error')
        return {'fault_injection': 'second read returns altered copy', 'calls': len(calls), 'reconciled': fresh(p, store.root.name)}
    raise AssertionError('Unrecognized explicit control: ' + operation)


def main():
    global STORE_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    manifest_path = CAMPAIGN / config['source_snapshot']['path']
    require(sha(manifest_path) == config['source_snapshot']['sha256'], 'Snapshot manifest changed')
    manifest = json.loads(manifest_path.read_text())
    for row in manifest['artifacts']:
        require(sha(CAMPAIGN / row['path']) == row['sha256'], 'Archived snapshot member changed')
    source = {Path(row['original_path']).name: CAMPAIGN / row['path'] for row in manifest['artifacts']}
    workflow = load('workflow', source['workflow.py'])
    p = load('independent_archived_crm_persistence', source['persistence.py'])
    adapters = load('independent_crm_adapters', EVAL / 'adapters.py')
    evaluator = load('independent_crm_evaluator', EVAL / 'evaluate.py')
    inputs = json.loads((HERE / 'component-inputs.json').read_text())['cases']
    oracles = {row['id']: row for row in json.loads((HERE / 'component-oracles.json').read_text())['cases']}
    results = []
    directory = args.config.parent
    with tempfile.TemporaryDirectory(prefix='synthetic-stores-', dir=directory) as temporary:
        STORE_ROOT = Path(temporary).resolve()
        # Runtime storage binding only: archived code bytes and business logic stay unchanged.
        p.STORAGE_ROOT = STORE_ROOT
        sys.addaudithook(audit)
        for index, fixture in enumerate(inputs):
            EVENTS.clear(); started = time.monotonic()
            row = {'test_id': fixture['id'], 'kind': 'structured_component', 'fault_injection': fixture['operation'] in ['replace_failure', 'post_commit_fsync_failure', 'readback_failure']}
            try:
                store = invoke(p.SyntheticStore, 'independent_' + str(index))
                original = cp(fixture['contacts'])
                invoke(store.initialize, original)
                require(original == fixture['contacts'], 'Initialize mutated input')
                row['output'] = successful(p, store, fixture, oracles[fixture['id']]) if fixture['operation'] == 'approved_component' else control(p, store, fixture, oracles[fixture['id']])
                row['effects'] = effect_observation(); row['outcome'] = 'passed'
            except Exception as exc:
                row.update(outcome='failed', error=type(exc).__name__ + ': ' + str(exc))
            row.update(elapsed_seconds=time.monotonic() - started, audit_events=cp(EVENTS))
            results.append(row)
        # Execute the previously frozen evaluator component groups, not conversational stand-ins.
        for number in [2, 3, 6]:
            bundle = json.loads((EVAL / 'components' / f'C-LOCAL-A{number}.json').read_text())
            oracle = json.loads((EVAL / 'component-oracles' / f'C-LOCAL-A{number}.json').read_text())
            observations = []
            for index, run in enumerate(bundle['runs']):
                name = f'evaluator_{number}_{index}'
                def factory(reopen, name=name):
                    return p.SyntheticStore(name)
                EVENTS.clear()
                observed = invoke(adapters.execute_crm, factory, None, run, workflow.run, effect_observation)
                observations.append(observed)
            judged = evaluator.evaluate(bundle, oracle, observations)
            results.append({'test_id': bundle['test_id'], 'kind': 'frozen_component_evaluator', 'outcome': judged['outcome'],
                            'evaluation': judged, 'observations': observations})
        bundle = json.loads((EVAL / 'inputs/003/C-A1.json').read_text())
        oracle = json.loads((EVAL / 'oracles/003/C-A1.json').read_text())
        observations = []
        for run in bundle['runs']:
            EVENTS.clear()
            observations.append(invoke(adapters.call_workflow, workflow.run, run, effect_observation))
        judged = evaluator.evaluate(bundle, oracle, observations)
        results.append({'test_id': 'C-A1', 'kind': 'frozen_structured_validation', 'outcome': judged['outcome'],
                        'evaluation': judged, 'observations': observations})
    report = {'schema_version': 1, 'case_id': '003', 'results': results,
              'passed': sum(row['outcome'] == 'passed' for row in results), 'total': len(results),
              'source_snapshot': config['source_snapshot'], 'snapshot_member_count': len(manifest['artifacts']),
              'temporary_storage_removed': not STORE_ROOT.exists(),
              'runtime_binding': 'Only archived persistence.STORAGE_ROOT rebound to a disposable evaluator-local directory.',
              'instrumentation': 'Python audit events around actual calls, plus exact serialized-state checks; not OS sandboxing.',
              'inference_executed': False, 'baseline_executed': False, 'product_acceptance': False,
              'exposure': 'independent_authored_exposed', 'component_acceptance': all(row['outcome'] == 'passed' for row in results)}
    print(json.dumps(report, indent=2))
    return 0 if report['component_acceptance'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
