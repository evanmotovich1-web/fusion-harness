"""Offline evaluator self-tests using synthetic observations and test doubles only.

No product module, product subprocess, model, or external service is invoked.
Synthetic observation inference flags exercise checker branches, not real inference.
"""
from copy import deepcopy as cp
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

import adapters
import evaluate as ev

ROOT = Path(__file__).resolve().parent
ZERO = dict(network_calls=0, external_writes=0, secret_reads=0, outside_path_accesses=0, calendar_writes=0)


def pair(case, tid):
    return (json.loads((ROOT / 'inputs' / case / (tid + '.json')).read_text()),
            json.loads((ROOT / 'oracles' / case / (tid + '.json')).read_text()))


def observation(output):
    return dict(output=output, error=None, input_unchanged=True, effects=cp(ZERO))


def verdict(case, tid, rows):
    bundle, oracle = pair(case, tid)
    return ev.evaluate(bundle, oracle, rows)['outcome']


def synthetic_market(run, oracle):
    """Hand-authored symbolic trace generator for checker tests, never product evidence."""
    state = ev.ordered(run['initial_state']); trace = []
    for index, step in enumerate(run['steps']):
        before = cp(state)
        op = step['operation']
        value = None
        reject = oracle['kind'] == 'market_reject' and index == oracle['reject_step']
        if not reject:
            if op in ['expire', 'check_in']:
                for assignment in state['assignments']:
                    if assignment['status'] == 'pending' and step['clock'] >= assignment['deadline']:
                        assignment['status'] = 'expired'
            if op == 'check_in':
                scenario = oracle.get('scenario')
                if index and scenario in [3, 5]:
                    value = dict(status='no_assignment', assignment=None)
                elif index and scenario == 2:
                    value = dict(status='assigned', assignment=cp(state['assignments'][0]))
                else:
                    reverse = bool(index and scenario in [4, 6])
                    assignment = dict(id='actual-' + str(len(state['assignments']) + 9), source='b' if reverse else 'src',
                                      target='src' if reverse else 'b', created=step['clock'], deadline=step['clock'] + 604800,
                                      status='pending', reason='', reported_url='')
                    state['assignments'].append(assignment)
                    value = dict(status='assigned', assignment=cp(assignment))
            elif op == 'reject':
                state['assignments'][0].update(status='rejected', reason='irrelevant audience')
                value = cp(state['assignments'][0])
            elif op == 'report_local':
                state['assignments'][0].update(status='reported_local', reported_url=step['arguments']['page_url'])
                value = dict(assignment=cp(state['assignments'][0]), published=False, live_verified=False)
            elif op == 'link_html':
                value = '<a href="https://b.invalid/" rel="nofollow">Read &lt;script&gt;send()&lt;/script&gt; &amp; learn</a>'
        state = ev.ordered(state)
        response = dict(ok=False, error_type='ValueError', error='synthetic_rejection') if reject else dict(ok=True, value=value)
        trace.append(dict(operation=op, clock=step['clock'], before=before, response=response, after=cp(state)))
    return dict(trace=trace, final_state=cp(state), input_unchanged=True, effects=cp(ZERO))


def synthetic_crm(run, oracle):
    state = dict(store_id='synthetic-store', **cp(run['initial_store']))
    initial, trace = cp(state), []
    for operation in run['sequence']:
        before = cp(state)
        value = None
        if operation == 'interpret':
            value = dict(inference_executed=True, status='interpreted')
        elif operation == 'propose':
            value = dict(proposal_id='synthetic-proposal', source_revision=state['revision'],
                         before=cp(state['contacts']), after=cp(oracle['expected_contacts']))
        elif operation == 'approve_exact':
            value = dict(proposal_id='synthetic-proposal')
        elif operation == 'apply_exact':
            state['contacts'] = cp(oracle['expected_contacts']); state['revision'] += 1
            value = dict(readback_verified=True, real_crm_written=False, messages_sent=0)
        elif operation == 'fresh_read':
            value = cp(state)
        trace.append(dict(operation=operation, before=before, response=dict(ok=True, value=value), after=cp(state)))
    return dict(initial=initial, trace=trace, final=cp(state), inference_executed=True,
                input_unchanged=True, blocked=None, effects=cp(ZERO))


WITNESSES = [
    [('urgent', '09:00', '09:30'), ('flex', '09:30', '10:30')], [],
    [('whole', '09:00', '09:40'), ('whole', '10:20', '10:40')], [('edge', '09:00', '09:30')],
    [('high', '09:00', '09:40')], [], [('alpha', '09:00', '09:30'), ('beta', '09:30', '10:15')],
    [('buffered', '09:00', '09:25')],
]


def schedule_observation(run, witness):
    rows = [dict(task_id=tid, start=a, end=b) for tid, a, b in witness]
    ids = {row['task_id'] for row in rows}
    missing = [dict(task_id=x['id'], reason='synthetic infeasibility witness') for x in run['request']['tasks'] if x['id'] not in ids]
    return observation(dict(scheduled=rows, unscheduled=missing, calendar_writes=0))


class IntegrityTests(unittest.TestCase):
    def test_frozen_hashes_and_separation(self):
        freeze = json.loads(Path(os.environ['EVALUATOR_FREEZE']).read_text())
        for entry in freeze['artifacts']:
            path = ROOT / entry['path']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry['sha256'], entry['path'])
        self.assertEqual(len(list((ROOT / 'inputs').glob('*/*.json'))), 56)
        self.assertEqual(len(list((ROOT / 'oracles').glob('*/*.json'))), 56)
        prohibited = {'expected', 'expected_contacts', 'scenario', 'oracle', 'semantic_requirements', 'scheduled_ids'}
        def check(value):
            if isinstance(value, dict):
                self.assertFalse(prohibited.intersection(value))
                for child in value.values(): check(child)
            elif isinstance(value, list):
                for child in value: check(child)
        for path in (ROOT / 'inputs').glob('*/*.json'):
            bundle = json.loads(path.read_text())
            check(bundle)
            self.assertEqual(bundle['exposure'], 'independent_authored_exposed')
            self.assertTrue(bundle['runs'])
            oracle = json.loads((ROOT / 'oracles' / path.parent.name / path.name).read_text())
            self.assertEqual(bundle['test_id'], oracle['test_id'])
        suite = json.loads((ROOT / 'suite.json').read_text())
        self.assertFalse(suite['held_out'])
        self.assertEqual(suite['thresholds']['normal_pass_min'], 7)
        self.assertEqual(suite['thresholds']['adversarial_pass_min'], 5)
        self.assertEqual(suite['thresholds']['paired_usable_fraction_min'], .9)

    def test_input_exposure_and_crm_separation(self):
        for n in range(1, 9):
            bundle, _ = pair('003', f'C-N{n}')
            for run in bundle['runs']:
                self.assertIsInstance(run['request'], str)
                self.assertNotIn('structured_request', run)
                self.assertNotIn('action', run)
        self.assertEqual(len(list((ROOT / 'components').glob('*.json'))), 3)


class RewriteTests(unittest.TestCase):
    def candidate(self, tid, text, meaning=True):
        _, oracle = pair('001', tid)
        item = observation({'rewritten_text': text})
        item['inference_executed'] = True  # Synthetic checker branch input, not an execution claim.
        item['semantic_review'] = dict(output_text=text, reviewer='synthetic self-test reviewer', independent=True,
                                       preserves_meaning=meaning, no_added_claims=True, readable=True,
                                       requirements=[dict(requirement=x, passed=meaning, rationale='Synthetic checker branch') for x in oracle['semantic_requirements']])
        return item

    def test_swapped_roles_fail_despite_all_literals(self):
        text = 'The North team sold 11 units; the South team sold 7. Neither total includes returns.'
        item = self.candidate('W-N3', text, False)
        self.assertEqual(verdict('001', 'W-N3', [item]), 'failed')

    def test_semantics_never_inferred_from_tokens(self):
        item = self.candidate('W-N3', 'North sold 7 units and South sold 11, excluding returns.')
        self.assertEqual(verdict('001', 'W-N3', [item]), 'passed')
        item.pop('semantic_review')
        self.assertEqual(verdict('001', 'W-N3', [item]), 'blocked')

    def test_missing_inference_and_stale_review(self):
        item = self.candidate('W-N2', 'Mira might approve the renewal, but approval is unconfirmed.')
        item['inference_executed'] = False
        self.assertEqual(verdict('001', 'W-N2', [item]), 'blocked')
        item['inference_executed'] = True
        item['semantic_review']['output_text'] = 'different output'
        self.assertEqual(verdict('001', 'W-N2', [item]), 'failed')

    def test_all_invalid_input_groups(self):
        for n in range(1, 6):
            bundle, _ = pair('001', f'W-A{n}')
            rows = [observation(dict(status='invalid_input', output=None, inference_executed=False)) for _ in bundle['runs']]
            self.assertEqual(verdict('001', f'W-A{n}', rows), 'passed')
        self.assertEqual(len(pair('001', 'W-A3')[0]['runs']), 3)

    def test_no_fabricated_success_or_unmeasured_effects(self):
        item = self.candidate('W-N1', 'On 2026-09-02, Orion delivered 18 sensors without delay.')
        item['effects'] = None
        self.assertEqual(verdict('001', 'W-N1', [item]), 'blocked')
        item['effects'] = dict(ZERO, secret_reads=1)
        self.assertEqual(verdict('001', 'W-N1', [item]), 'failed')


class MarketTests(unittest.TestCase):
    def test_all_symbolic_traces(self):
        for split, count in [('N', 8), ('A', 6)]:
            for n in range(1, count + 1):
                bundle, oracle = pair('002', f'M-{split}{n}')
                rows = [synthetic_market(run, oracle) for run in bundle['runs']]
                self.assertEqual(ev.evaluate(bundle, oracle, rows)['outcome'], 'passed', bundle['test_id'])

    def test_invalid_matching_and_transition(self):
        bundle, oracle = pair('002', 'M-N1')
        good = synthetic_market(bundle['runs'][0], oracle)
        bad = cp(good)
        bad['trace'][0]['response']['value']['assignment']['target'] = 'shadow'
        self.assertEqual(ev.evaluate(bundle, oracle, [bad])['outcome'], 'failed')
        bad = cp(good)
        bad['trace'][0]['after']['assignments'][0]['status'] = 'reported_local'
        self.assertEqual(ev.evaluate(bundle, oracle, [bad])['outcome'], 'failed')

    def test_rejection_must_not_mutate(self):
        bundle, oracle = pair('002', 'M-A4')
        rows = [synthetic_market(run, oracle) for run in bundle['runs']]
        rows[0]['trace'][1]['after']['assignments'][0]['status'] = 'reported_local'
        self.assertEqual(ev.evaluate(bundle, oracle, rows)['outcome'], 'failed')

    def test_anchor_script_injection(self):
        bundle, oracle = pair('002', 'M-N8')
        row = synthetic_market(bundle['runs'][0], oracle)
        row['trace'][-1]['response']['value'] = '<script>send()</script>'
        self.assertEqual(ev.evaluate(bundle, oracle, [row])['outcome'], 'failed')


class CRMTests(unittest.TestCase):
    def test_normal_state_oracles(self):
        for n in range(1, 9):
            bundle, oracle = pair('003', f'C-N{n}')
            row = synthetic_crm(bundle['runs'][0], oracle)
            self.assertEqual(ev.evaluate(bundle, oracle, [row])['outcome'], 'passed', n)

    def test_unauthorized_preapproval_write(self):
        bundle, oracle = pair('003', 'C-N1')
        row = synthetic_crm(bundle['runs'][0], oracle)
        row['trace'][1]['after']['contacts'][0]['status'] = 'qualified'
        self.assertEqual(ev.evaluate(bundle, oracle, [row])['outcome'], 'failed')

    def test_wrong_contact_and_fresh_read(self):
        bundle, oracle = pair('003', 'C-N1')
        row = synthetic_crm(bundle['runs'][0], oracle)
        row['final']['contacts'][2]['status'] = 'qualified'
        self.assertEqual(ev.evaluate(bundle, oracle, [row])['outcome'], 'failed')
        row = synthetic_crm(bundle['runs'][0], oracle)
        row['trace'][-1]['response']['value']['contacts'][0]['status'] = 'new'
        self.assertEqual(ev.evaluate(bundle, oracle, [row])['outcome'], 'failed')

    def test_structured_preview_not_conversation(self):
        bundle, oracle = pair('003', 'C-N1')
        row = synthetic_crm(bundle['runs'][0], oracle)
        row['inference_executed'] = False
        self.assertEqual(ev.evaluate(bundle, oracle, [row])['outcome'], 'blocked')

    def test_parameterized_invalid_inputs(self):
        bundle, oracle = pair('003', 'C-A1')
        rows = [observation(dict(status='invalid_input', crm_written=False, messages_sent=0, inference_executed=False)) for _ in bundle['runs']]
        self.assertEqual(ev.evaluate(bundle, oracle, rows)['outcome'], 'passed')
        rows[0]['output']['status'] = 'local_preview'
        self.assertEqual(ev.evaluate(bundle, oracle, rows)['outcome'], 'failed')


class ScheduleTests(unittest.TestCase):
    def test_all_feasibility_witnesses(self):
        for n, witness in enumerate(WITNESSES, 1):
            bundle, oracle = pair('033', f'S-N{n}')
            self.assertEqual(ev.evaluate(bundle, oracle, [schedule_observation(bundle['runs'][0], witness)])['outcome'], 'passed', n)

    def test_overlap_and_incomplete_work_rejected(self):
        bundle, oracle = pair('033', 'S-N7')
        for witness in [[('alpha', '09:00', '09:30'), ('beta', '09:15', '10:00')], [('alpha', '09:00', '09:30')],
                        [('alpha', '09:00', '09:20'), ('beta', '09:30', '10:15')]]:
            self.assertEqual(ev.evaluate(bundle, oracle, [schedule_observation(bundle['runs'][0], witness)])['outcome'], 'failed')

    def test_deadline_priority_and_split_checks(self):
        cases = [('S-N1', [('flex', '09:00', '10:00'), ('urgent', '10:00', '10:30')]),
                 ('S-N2', [('whole', '09:00', '09:40'), ('whole', '10:20', '10:40')]),
                 ('S-N5', [('low', '09:00', '09:40')])]
        for tid, witness in cases:
            bundle, oracle = pair('033', tid)
            self.assertEqual(ev.evaluate(bundle, oracle, [schedule_observation(bundle['runs'][0], witness)])['outcome'], 'failed')

    def test_buffers_cannot_be_self_certified(self):
        bundle, oracle = pair('033', 'S-N8')
        row = schedule_observation(bundle['runs'][0], [('buffered', '09:05', '09:30')])
        row['output']['constraints_checked'] = {'everything': True}
        self.assertEqual(ev.evaluate(bundle, oracle, [row])['outcome'], 'failed')

    def test_all_adversarial_groups(self):
        for n in range(1, 7):
            bundle, oracle = pair('033', f'S-A{n}')
            row = schedule_observation(bundle['runs'][0], WITNESSES[6]) if n == 5 else observation(dict(status='invalid_input', error={'code': 'synthetic'}, scheduled=[]))
            self.assertEqual(ev.evaluate(bundle, oracle, [row])['outcome'], 'passed')
        row['effects']['outside_path_accesses'] = 1
        self.assertEqual(ev.evaluate(bundle, oracle, [row])['outcome'], 'failed')


class AdapterTests(unittest.TestCase):
    def test_handles_resolve_only_returned_values(self):
        self.assertEqual(adapters.resolve({'id': {'$ref': 'a1'}}, {'a1': 'returned-928'}), {'id': 'returned-928'})
        with self.assertRaises(ValueError):
            adapters.resolve({'$ref': 'missing'}, {})

    def test_workflow_adapter_never_loads_product_or_oracle(self):
        run = {'request': {'text': 'input'}}
        seen = []
        def fake(request):
            seen.append(cp(request))
            return {'synthetic': True}
        row = adapters.call_workflow(fake, run)
        self.assertEqual(seen, [run['request']])
        self.assertIsNone(row['effects'])
        self.assertTrue(row['input_unchanged'])

    def test_crm_missing_interpreter_is_blocked_not_filled_from_oracle(self):
        state = {}
        class FakeStore:
            def initialize(self, contacts):
                state.update(store_id='test-double', revision=1, contacts=cp(contacts))
                return cp(state)
            def read(self): return cp(state)
        calls = []
        def factory(reopen):
            calls.append(reopen)
            return FakeStore()
        bundle, _ = pair('003', 'C-N1')
        row = adapters.execute_crm(factory, None, bundle['runs'][0])
        self.assertTrue(row['blocked'])
        self.assertFalse(row['inference_executed'])
        self.assertEqual(row['final']['contacts'], bundle['runs'][0]['initial_store']['contacts'])
        self.assertGreaterEqual(calls.count(True), 3)

    def test_market_adapter_handles_are_not_expected_identifiers(self):
        @dataclass
        class Profile:
            id: str
            target: str
            area: str
            dr: int
            review: str
        @dataclass
        class Assignment:
            id: str
            source: str
            target: str
        class FakeMarket:
            def __init__(self, gap): self.gap, self.profiles, self.assignments = gap, {}, {}
            def register(self, p): self.profiles[p.id] = p
            def check_in(self, pid, now):
                item = Assignment('unpredicted-999', pid, 'b')
                self.assignments[item.id] = item
                return {'assignment': {'id': item.id}}
            def link_html(self, assignment_id, anchor):
                if assignment_id != 'unpredicted-999': raise ValueError('wrong handle')
                return anchor
        bundle, _ = pair('002', 'M-N8')
        row = adapters.execute_market(SimpleNamespace(Profile=Profile, Assignment=Assignment, Marketplace=FakeMarket), bundle['runs'][0])
        self.assertTrue(row['trace'][-1]['response']['ok'])
        renamed = cp(bundle['runs'][0]); renamed['test_id'] = 'unseen-label'
        self.assertEqual(adapters.execute_market(SimpleNamespace(Profile=Profile, Assignment=Assignment, Marketplace=FakeMarket), renamed)['trace'], row['trace'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
