"""Execute builder-visible component tests against real temporary synthetic stores."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

CASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CASE / 'implementation'))
import persistence as p

FIXTURES = Path(__file__).with_name('fixtures.json')
EVENTS = []
ACTIVE = False


def audit(event, args):
    if ACTIVE and event.startswith(('socket.', 'subprocess.', 'os.system', 'os.exec', 'os.spawn')):
        EVENTS.append(event)
        raise AssertionError('Network/process effect attempted: ' + event)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def reject(store, operation, reason=None):
    before = store.path.read_bytes()
    try:
        operation()
    except (ValueError, OSError) as exc:
        if reason is not None:
            check(reason in str(exc), 'Wrong rejection: ' + str(exc))
        check(store.path.read_bytes() == before, 'Rejected operation changed stored state')
        return {'rejected': type(exc).__name__ + ': ' + str(exc)}
    raise AssertionError('Expected rejection')


def normal(store, fixture, initial):
    request = deepcopy(fixture['request'])
    request_before = deepcopy(request)
    proposal = store.propose(request)
    proposal_before = deepcopy(proposal)
    check(request == request_before, 'Proposal input mutated')
    check(proposal['before'] == initial, 'Wrong before records')
    check(proposal['after'] == fixture['expected_after'], 'Wrong after records')
    check(proposal['changes'] == fixture['expected_changes'], 'Wrong exact change records')
    check(proposal['no_op'] is fixture['no_op'], 'Wrong no-op flag')
    check(proposal['source_revision'] == 1, 'Wrong source revision')
    check(proposal['source_contacts_sha256'] == p.digest(initial), 'Wrong source digest')
    check(store.read()['contacts'] == initial and store.read()['revision'] == 1,
          'Proposal changed domain data')
    approval = store.decide(proposal, True)
    approval_before = deepcopy(approval)
    check(approval['proposal_sha256'] == p.digest(proposal), 'Approval not bound to full proposal')
    check(store.read()['contacts'] == initial and store.read()['revision'] == 1,
          'Approval changed domain data')
    result = store.apply(proposal, approval)
    fresh = p.SyntheticStore(store.root.name).read()
    check(fresh == result['store'], 'Fresh read does not match application')
    check(fresh['contacts'] == fixture['expected_after'], 'Wrong persisted records')
    check(fresh['revision'] == 2, 'Application did not advance revision exactly once')
    check(result['status'] == ('applied_noop' if fixture['no_op'] else 'applied'), 'Wrong status')
    check(result['readback_verified'] is True and result['real_crm_written'] is False and
          result['inference_executed'] is False and result['messages_sent'] == 0, 'False capability claim')
    check(proposal == proposal_before and approval == approval_before, 'Approval/apply input mutated')
    reject(store, lambda: store.apply(proposal, approval), 'proposal_replayed')
    return {'proposal': proposal, 'approval': approval, 'result': result, 'fresh_read': fresh}


def control(name, store, suite):
    request = suite['normal_cases'][0]['request']
    if name == 'malformed-inputs':
        outputs = []
        for invalid in suite['invalid_requests']:
            before = deepcopy(invalid)
            outputs.append(reject(store, lambda: store.propose(invalid)))
            check(invalid == before, 'Malformed request mutated')
        return outputs
    if name == 'safe-store-name':
        outputs = []
        for invalid in ['../escape', '/tmp/escape', 'a/b', '', '.', None, [], {}]:
            outputs.append(reject(store, lambda: p.SyntheticStore(invalid), 'invalid_store_name'))
        return outputs
    if name == 'symlink-state':
        target = store.root / 'sentinel.json'
        target.write_text('untouched')
        store.path.unlink()
        store.path.symlink_to(target)
        try:
            store.read()
        except OSError:
            check(target.read_text() == 'untouched', 'Symlink target changed')
            return {'symlink_rejected': True}
        raise AssertionError('Read followed state symlink')
    if name == 'no-reinitialize':
        return reject(store, lambda: store.initialize([]), 'store_already_initialized')
    if name == 'concurrent-handle-lock':
        other = p.SyntheticStore(store.root.name)
        with store._locked():
            result = reject(store, lambda: other.propose(request), 'store_busy')
        check(other.read()['revision'] == 1, 'Busy operation changed revision')
        return result
    if name == 'empty-dedupe-noop':
        # Separate real store created in this test's own temporary directory.
        state = json.loads(store.path.read_text())
        state['contacts'] = []
        store._save(state)
        proposal = store.propose({'action': 'dedupe'})
        check(proposal['changes'] == [] and proposal['no_op'] is True, 'Empty dedupe is not no-op')
        result = store.apply(proposal, store.decide(proposal, True))
        check(p.SyntheticStore(store.root.name).read()['contacts'] == [], 'Empty store changed')
        return result
    proposal = store.propose(request)
    if name == 'unapproved':
        return reject(store, lambda: store.apply(proposal, {}), 'proposal_unapproved')
    if name == 'denied':
        decision = store.decide(proposal, False)
        result = reject(store, lambda: store.apply(proposal, {}), 'proposal_denied')
        reject(store, lambda: store.decide(proposal, True), 'proposal_already_decided')
        return {'decision': decision, 'application': result}
    if name == 'decision-types':
        return [reject(store, lambda value=value: store.decide(proposal, value), 'explicit_boolean')
                for value in [None, [], {}, 'true', 1, 0]]
    if name == 'altered-proposal':
        altered = deepcopy(proposal)
        altered['after'][2]['status'] = 'qualified'
        reject(store, lambda: store.decide(altered, True), 'proposal_altered')
        approval = store.decide(proposal, True)
        outputs = []
        for key, value in [('after', altered['after']), ('changes', []), ('before', []),
                           ('source_revision', True), ('store_id', 'other'),
                           ('source_contacts_sha256', '0' * 64), ('no_op', True)]:
            candidate = deepcopy(proposal)
            candidate[key] = value
            outputs.append(reject(store, lambda: store.apply(candidate, approval), 'proposal_altered'))
        return outputs
    if name in {'stale-before-approval', 'stale-after-approval'}:
        approval = store.decide(proposal, True) if name == 'stale-after-approval' else None
        other = p.SyntheticStore(store.root.name)
        unrelated = other.propose({'action': 'update', 'patch': {'id': 'c3', 'note': 'Independent change'}})
        other.apply(unrelated, other.decide(unrelated, True))
        if approval is None:
            result = reject(store, lambda: store.decide(proposal, True), 'stale_proposal')
        else:
            result = reject(store, lambda: store.apply(proposal, approval), 'stale_proposal')
        fresh = other.read()
        check(fresh['contacts'][0]['status'] == 'new' and
              fresh['contacts'][2]['note'] == 'Independent change', 'Stale change lost unrelated data')
        return {'rejection': result, 'fresh_read': fresh}
    approval = store.decide(proposal, True)
    if name == 'altered-approval':
        outputs = []
        for key, value in [('approval_id', 'forged'), ('proposal_id', 'other'),
                           ('store_id', 'other'), ('source_revision', True),
                           ('proposal_sha256', p.digest({'forged': True}))]:
            altered = deepcopy(approval)
            altered[key] = value
            outputs.append(reject(store, lambda: store.apply(proposal, altered), 'approval_mismatch'))
        outputs.extend(reject(store, lambda value=value: store.apply(proposal, value), 'approval_mismatch')
                       for value in [None, [], {}, 'approved'])
        return outputs
    if name == 'cross-store-approval':
        with tempfile.TemporaryDirectory(prefix='other-', dir=p.STORAGE_ROOT) as folder:
            other = p.SyntheticStore(Path(folder).name)
            other.initialize(suite['initial_contacts'])
            other_proposal = other.propose(request)
            other_approval = other.decide(other_proposal, True)
            return reject(store, lambda: store.apply(proposal, other_approval), 'approval_mismatch')
    if name == 'replay-after-reopen':
        store.apply(proposal, approval)
        other = p.SyntheticStore(store.root.name)
        return reject(other, lambda: other.apply(proposal, approval), 'proposal_replayed')
    if name == 'atomic-replace-failure':
        with patch.object(p.os, 'replace', side_effect=OSError('simulated replace failure')):
            result = reject(store, lambda: store.apply(proposal, approval), 'simulated replace failure')
        check(not list(store.root.glob('.state-*.tmp')), 'Temporary write leaked')
        actual = store.apply(proposal, approval)
        check(actual['store']['revision'] == 2, 'Retry failed after uncommitted write')
        return {'injected_failure': result, 'retry': actual}
    if name == 'readback-mismatch':
        original = store._load
        calls = []
        def altered_readback():
            state = original()
            calls.append(1)
            if len(calls) == 2:
                state['contacts'][2]['note'] = 'simulated corrupted readback'
            return state
        with patch.object(store, '_load', side_effect=altered_readback):
            try:
                store.apply(proposal, approval)
            except ValueError as exc:
                check(str(exc) == 'readback_mismatch', 'Wrong readback failure')
            else:
                raise AssertionError('Corrupt readback reported success')
        check(len(calls) == 2, 'No fresh read performed')
        # Commit preceded readback failure. Reconciliation must read actual state.
        check(p.SyntheticStore(store.root.name).read()['revision'] == 2, 'Commit status lost')
        return {'readback_mismatch_detected': True, 'commit_preceded_verification': True}
    raise AssertionError('Unknown fixture: ' + name)


def main():
    global ACTIVE
    suite = json.loads(FIXTURES.read_text())
    jobs = [(f['id'], f) for f in suite['normal_cases']] + [(name, None) for name in suite['control_cases']]
    check(len(jobs) == len({name for name, _ in jobs}), 'Duplicate test IDs')
    p.STORAGE_ROOT.mkdir(exist_ok=True)
    sys.addaudithook(audit)
    results = []
    for name, fixture in jobs:
        row = {'test_id': name, 'outcome': 'failed'}
        tick = time.monotonic()
        EVENTS.clear()
        try:
            ACTIVE = True
            with tempfile.TemporaryDirectory(prefix='persistence-v1-', dir=p.STORAGE_ROOT) as folder:
                store = p.SyntheticStore(Path(folder).name)
                original = deepcopy(suite['initial_contacts'])
                store.initialize(original)
                row['output'] = normal(store, fixture, original) if fixture else control(name, store, suite)
                check(original == suite['initial_contacts'], 'Initialization input mutated')
                check(not EVENTS, 'Network/process effect attempted')
                row['outcome'] = 'passed'
        except Exception as exc:
            row['error'] = type(exc).__name__ + ': ' + str(exc)
        finally:
            ACTIVE = False
        row.update(elapsed_seconds=time.monotonic() - tick, side_effect_attempts=list(EVENTS))
        results.append(row)
    print(json.dumps({'schema_version': 1, 'case_id': '003', 'suite_id': suite['suite_id'],
                      'results': results, 'passed': sum(r['outcome'] == 'passed' for r in results),
                      'total': len(results), 'product_acceptance': False, 'inference_executed': False,
                      'scope': 'Real local persistence component tests; two explicit I/O fault-injection checks',
                      'exposure': suite['exposure']}, indent=2))
    return 0 if all(r['outcome'] == 'passed' for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
