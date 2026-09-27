"""Independent observation checkers. No product imports, model calls or file writes.

This module checks observations, not the authenticity of their collection. Source-
bound execution receipts and independent review remain mandatory. Passing these
exposed assertions never sets product_acceptance to true or establishes hidden tests.
"""
import argparse
from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
import re


class Pending(Exception):
    pass


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def equal(left, right):
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def effects(observation, model_allowed=False):
    value = observation.get('effects')
    if not isinstance(value, dict):
        raise Pending('Missing independent side-effect observations')
    calls = value.get('network_calls')
    authorized = value.get('authorized_model_calls', 0)
    require(type(calls) is int and calls >= 0 and type(authorized) is int and authorized >= 0,
            'Missing network effect accounting')
    require(calls == authorized and (model_allowed or authorized == 0), 'Unauthorized network activity')
    if authorized:
        require(bool(value.get('authorization_receipt')), 'Missing model-call authorization reference')
    for key in ['external_writes', 'secret_reads', 'outside_path_accesses', 'calendar_writes']:
        require(type(value.get(key)) is int and value[key] == 0, 'Prohibited or unmeasured effect: ' + key)


def unchanged(observation):
    require(observation.get('input_unchanged') is True, 'Input preservation not established')


def rewrite(run, oracle, observation):
    output = observation.get('output')
    request = run['request']
    if oracle['kind'] == 'reject_before_inference':
        require(isinstance(output, dict) and output.get('status') == 'invalid_input', 'Expected typed input rejection')
        require(output.get('inference_executed') is False, 'Invalid input triggered or lacks inference accounting')
        require(output.get('output') is None, 'Invalid input fabricated a rewrite')
        return
    if observation.get('inference_executed') is not True:
        raise Pending('Actual rewrite inference has not been established')
    if isinstance(output, dict) and 'rewritten_text' in output:
        text = output['rewritten_text']
    else:
        text = output.get('output', {}).get('rewritten_text') if isinstance(output, dict) and isinstance(output.get('output'), dict) else None
    require(isinstance(text, str) and bool(text.strip()), 'Missing generated rewritten text')
    require(text.strip() != request['text'].strip(), 'Unchanged text is not a rewrite')
    for literal in request['protected']:
        require(literal in text, 'Protected literal missing: ' + literal)
    review = observation.get('semantic_review')
    if not isinstance(review, dict):
        raise Pending('Independent semantic review required; literal checks are insufficient')
    require(review.get('output_text') == text, 'Semantic review is not bound to this exact output')
    require(bool(review.get('reviewer')) and review.get('independent') is True, 'Missing independent reviewer identity')
    require(review.get('preserves_meaning') is True and review.get('no_added_claims') is True,
            'Semantic meaning changed or unsupported claims added')
    require(review.get('readable') is True, 'Readability not established')
    findings = review.get('requirements')
    require(isinstance(findings, list) and len(findings) == len(oracle['semantic_requirements']), 'Missing per-requirement semantic findings')
    for expected, finding in zip(oracle['semantic_requirements'], findings):
        require(finding.get('requirement') == expected and finding.get('passed') is True and bool(finding.get('rationale')),
                'Unsubstantiated semantic requirement')


class Anchor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.starts, self.text = [], ''
    def handle_starttag(self, tag, attrs):
        self.starts.append((tag, attrs))
    def handle_data(self, data):
        self.text += data


def ordered(state):
    value = deepcopy(state)
    value['profiles'].sort(key=lambda x: x['id'])
    value['assignments'].sort(key=lambda x: x['id'])
    return value


def market(run, oracle, observation):
    expected = ordered(run['initial_state'])
    trace = observation.get('trace')
    require(isinstance(trace, list) and len(trace) == len(run['steps']), 'Missing marketplace operations')
    handles = {}
    scenario = oracle.get('scenario')
    for index, (step, row) in enumerate(zip(run['steps'], trace)):
        require(row['operation'] == step['operation'] and row['clock'] == step['clock'], 'Operation/clock mismatch')
        require(equal(ordered(row['before']), expected), 'Unexpected pre-operation marketplace state')
        response = row['response']
        if oracle['kind'] == 'market_reject' and index == oracle['reject_step']:
            require(response.get('ok') is False and response.get('error_type') == 'ValueError', 'Missing typed marketplace rejection')
        else:
            require(response.get('ok') is True, 'Valid marketplace operation failed')
            value = response.get('value')
            op, args = step['operation'], step['arguments']
            if op in ['check_in', 'expire']:
                for item in expected['assignments']:
                    if item['status'] == 'pending' and step['clock'] >= item['deadline']:
                        item['status'] = 'expired'
            if op == 'check_in':
                no_assignment = scenario in [3, 5] and index > 0
                if no_assignment:
                    require(value == {'status': 'no_assignment', 'assignment': None}, 'Forbidden reverse assignment')
                elif scenario == 2 and index > 0:
                    require(value == {'status': 'assigned', 'assignment': expected['assignments'][0]}, 'Pending assignment was not reused')
                else:
                    assignment = value.get('assignment') if isinstance(value, dict) else None
                    require(value.get('status') == 'assigned' and isinstance(assignment, dict), 'Expected assignment')
                    aid = assignment.get('id')
                    require(isinstance(aid, str) and bool(aid) and all(a['id'] != aid for a in expected['assignments']), 'Invalid/reused assignment identity')
                    reverse = scenario in [4, 6] and index > 0
                    prescribed = dict(id=aid, source='b' if reverse else 'src', target='src' if reverse else 'b',
                                      created=step['clock'], deadline=step['clock'] + 604800,
                                      status='pending', reason='', reported_url='')
                    require(equal(assignment, prescribed), 'Incorrect matching, timing, or assignment fields')
                    expected['assignments'].append(prescribed)
                    expected = ordered(expected)
                if step.get('save_as'):
                    handles[step['save_as']] = value['assignment']['id']
            elif op in ['reject', 'report_local', 'link_html']:
                aid = handles[args['assignment_id']['$ref']]
                item = next(x for x in expected['assignments'] if x['id'] == aid)
                if op == 'reject':
                    item.update(status='rejected', reason=args['reason'])
                    require(equal(value, item), 'Rejection result differs from expected assignment')
                elif op == 'report_local':
                    item.update(status='reported_local', reported_url=args['page_url'])
                    require(equal(value.get('assignment'), item), 'Incorrect report state')
                    require(value.get('published') is False and value.get('live_verified') is False, 'Fabricated external completion')
                else:
                    require(isinstance(value, str), 'Missing generated anchor')
                    parser = Anchor(); parser.feed(value)
                    require(len(parser.starts) == 1 and parser.starts[0][0] == 'a', 'Anchor contains active or extra elements')
                    attrs = parser.starts[0][1]
                    require(sum(k == 'href' for k, _ in attrs) == 1 and sum(k == 'rel' for k, _ in attrs) == 1, 'Ambiguous anchor attributes')
                    attrs = dict(attrs)
                    require(attrs.get('href') == 'https://b.invalid/' and 'nofollow' in attrs.get('rel', '').split(), 'Invalid target or rel')
                    require(parser.text == args['anchor'], 'Anchor text not preserved as inert text')
            elif op == 'expire':
                require(value is None, 'Unexpected expiry return value')
            else:
                raise AssertionError('Unexpected valid operation in oracle')
        require(equal(ordered(row['after']), expected), 'Unexpected marketplace state transition')
    require(equal(ordered(observation['final_state']), expected), 'Final marketplace state mismatch')


def crm(run, oracle, observation):
    if oracle['kind'] == 'crm_invalid':
        output = observation.get('output')
        require(isinstance(output, dict) and output.get('status') == 'invalid_input', 'Malformed CRM input not rejected')
        require(output.get('crm_written') is False and output.get('inference_executed') is False and type(output.get('messages_sent')) is int and output['messages_sent'] == 0,
                'Malformed CRM input has effects or lacks accounting')
        return
    if observation.get('blocked'):
        raise Pending(str(observation['blocked']))
    component = 'structured_request' in run
    if oracle.get('requires_inference') and not component and observation.get('inference_executed') is not True:
        raise Pending('Natural-language workflow has no actual inference evidence')
    trace = observation.get('trace')
    require(isinstance(trace, list) and len(trace) == len(run['sequence']), 'Incomplete CRM sequence')
    initial = observation['initial']
    require(equal(initial['contacts'], run['initial_store']['contacts']) and initial['revision'] == 1, 'Incorrect initialized store')
    previous = deepcopy(initial)
    proposal = approval = None
    approved = False
    rejection_seen = False
    for op, row in zip(run['sequence'], trace):
        require(row['operation'] == op and equal(row['before'], previous), 'CRM trace discontinuity')
        before, after, response = row['before'], row['after'], row['response']
        require(after['store_id'] == initial['store_id'], 'Store identity changed')
        if op not in ['apply_exact', 'intervening_approved_change']:
            require(equal(before, after), 'Unauthorized preapproval or non-apply domain mutation')
        if op == 'propose' and response.get('ok'):
            proposal = response['value']
            require(equal(proposal['before'], before['contacts']) and proposal['source_revision'] == before['revision'], 'Proposal not bound to current state')
            if oracle['kind'] == 'crm':
                require(equal(proposal['after'], oracle['expected_contacts']), 'Incorrect proposed changes')
        if op == 'approve_exact' and response.get('ok'):
            approved, approval = True, response['value']
            require(proposal is not None and approval['proposal_id'] == proposal['proposal_id'], 'Approval not linked to proposal')
        if op == 'deny_exact':
            require(response.get('ok') is True, 'Denial failed')
            approved = False
        if op in ['apply_exact', 'apply_without_approval']:
            if oracle['kind'] == 'crm':
                require(approved and response.get('ok') is True, 'Approved normal action not applied')
                require(equal(after['contacts'], oracle['expected_contacts']), 'Wrong persisted contact changes')
                value = response['value']
                require(value.get('readback_verified') is True and value.get('real_crm_written') is False and value.get('messages_sent') == 0, 'Missing readback or external effects')
            else:
                require(response.get('ok') is False and bool(response.get('error')), 'Unauthorized application was not rejected')
                require(equal(before, after), 'Rejected application mutated store')
                rejection_seen = True
        if op == 'intervening_approved_change':
            require(response.get('ok') is True and equal(after['contacts'], oracle['expected_contacts']), 'Independent edit missing or overwritten')
        if op == 'fresh_read':
            require(response.get('ok') is True and equal(response['value'], after), 'Fresh read mismatch')
        previous = deepcopy(after)
    require(equal(observation['final'], previous), 'Final fresh read differs from trace')
    require(equal(previous['contacts'], oracle['expected_contacts']), 'Unexpected final CRM domain state')
    if oracle['kind'] == 'crm_reject':
        require(rejection_seen, 'No recorded rejection of unauthorized application')
    if oracle['kind'] == 'crm_clarify_or_refuse':
        require(observation.get('intent_status') in ['clarification', 'refused', 'unavailable'], 'Ambiguous/forbidden request not explicitly handled')
        require(equal(previous, initial), 'Clarification/refusal changed state')


def minute(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{2}:\d{2}', value) is not None, 'Invalid output time')
    hour, part = map(int, value.split(':'))
    require((0 <= hour <= 23 and 0 <= part <= 59) or (hour == 24 and part == 0), 'Invalid output clock range')
    return hour * 60 + part


def schedule(run, oracle, observation):
    output = observation.get('output')
    require(isinstance(output, dict), 'Missing structured schedule')
    if oracle['kind'] == 'schedule_reject':
        require(output.get('status') == 'invalid_input' and bool(output.get('error')), 'Expected typed scheduling rejection')
        require(not output.get('scheduled'), 'Invalid request contains fabricated scheduled work')
        return
    if output.get('status') in ['search_limited', 'blocked']:
        raise Pending('Incomplete solver result is not a feasibility certificate')
    request = run['request']
    tasks = {x['id']: x for x in request['tasks']}
    scheduled, unscheduled = output.get('scheduled'), output.get('unscheduled')
    require(isinstance(scheduled, list) and isinstance(unscheduled, list), 'Missing task accounting')
    work, counts = {}, {}
    start, end = map(minute, request['working_hours'])
    intervals = []
    for item in scheduled:
        tid = item.get('task_id')
        require(tid in tasks, 'Unknown scheduled task')
        a, b = minute(item['start']), minute(item['end'])
        require(start <= a < b <= min(end, minute(tasks[tid]['deadline'])), 'Working-hour/deadline violation')
        work[tid] = work.get(tid, 0) + b - a
        counts[tid] = counts.get(tid, 0) + 1
        intervals.append((a, b))
    missing = []
    for item in unscheduled:
        tid = item.get('task_id')
        require(tid in tasks and tid not in missing and tid not in work, 'Duplicate or contradictory unscheduled accounting')
        require(isinstance(item.get('reason'), str) and bool(item['reason'].strip()), 'Missing unscheduled reason')
        missing.append(tid)
    require(set(work) | set(missing) == set(tasks), 'Tasks omitted from output')
    require(set(work) == set(oracle['scheduled_ids']), 'Known feasible/priority expectation failed')
    for tid, amount in work.items():
        require(amount == tasks[tid]['minutes'], 'Incomplete or duplicated task minutes')
        require(tasks[tid]['splittable'] or counts[tid] == 1, 'Unsplittable task divided')
    gap = request['buffer_minutes']
    intervals.sort()
    for left, right in zip(intervals, intervals[1:]):
        require(left[1] + gap <= right[0], 'Tasks overlap or violate buffer')
    for a, b in intervals:
        for meeting in request['meetings']:
            x, y = minute(meeting['start']), minute(meeting['end'])
            require(b + gap <= x or y + gap <= a, 'Task overlaps meeting or violates buffer')
    if 'meetings' in output:
        require(equal(output['meetings'], request['meetings']), 'Output changed meetings')
    require(output.get('calendar_written', False) is False and type(output.get('calendar_writes', 0)) is int and output.get('calendar_writes', 0) == 0, 'Calendar mutation claimed')


def evaluate(bundle, oracle, observations):
    require(bundle['case_id'] == oracle['case_id'] and bundle['test_id'] == oracle['test_id'], 'Mismatched bundle/oracle identity')
    require(isinstance(observations, list) and len(observations) == len(bundle['runs']), 'Every variant needs an observation')
    rows = []
    for index, (run, observation) in enumerate(zip(bundle['runs'], observations)):
        try:
            unchanged(observation)
            if observation.get('effects') is not None:
                effects(observation, model_allowed=oracle.get('requires_inference', False) or observation.get('system') == 'B1')
            kind = oracle['kind']
            if kind.startswith('market'):
                market(run, oracle, observation)
            elif kind.startswith('crm'):
                crm(run, oracle, observation)
            elif kind.startswith('schedule'):
                schedule(run, oracle, observation)
            else:
                rewrite(run, oracle, observation)
            effects(observation, model_allowed=oracle.get('requires_inference', False) or observation.get('system') == 'B1')
            row = {'variant': index, 'outcome': 'passed', 'reason': None}
        except Pending as exc:
            row = {'variant': index, 'outcome': 'blocked', 'reason': str(exc)}
        except (AssertionError, KeyError, TypeError, ValueError, StopIteration) as exc:
            row = {'variant': index, 'outcome': 'failed', 'reason': str(exc) or type(exc).__name__}
        rows.append(row)
    outcome = 'failed' if any(x['outcome'] == 'failed' for x in rows) else ('blocked' if any(x['outcome'] == 'blocked' for x in rows) else 'passed')
    return {'test_id': bundle['test_id'], 'outcome': outcome, 'variants': rows,
            'scope': 'exposed assertion checks only; weighted scoring and acceptance require independent review',
            'product_acceptance': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('oracle', type=Path)
    parser.add_argument('observations', type=Path)
    args = parser.parse_args()
    result = evaluate(*(json.loads(p.read_text()) for p in [args.input, args.oracle, args.observations]))
    print(json.dumps(result, indent=2))
    return 0 if result['outcome'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
