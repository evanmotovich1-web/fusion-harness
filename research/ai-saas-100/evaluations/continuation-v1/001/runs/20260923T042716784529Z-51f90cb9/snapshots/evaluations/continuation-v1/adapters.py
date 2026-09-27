"""Oracle-free interfaces. Callers own module loading, time limits and effect observation.

No product is imported here. Functions receive explicit implementations. No adapter
loads an oracle or derives a command from a test ID. CRM interpretation must be a
real authorized callback, never a lookup from evaluator expected answers.
"""
from copy import deepcopy
from dataclasses import asdict


class CapabilityUnavailable(Exception):
    pass


def resolve(value, handles):
    if isinstance(value, dict):
        if set(value) == {'$ref'}:
            if value['$ref'] not in handles:
                raise ValueError('unresolved_handle')
            return deepcopy(handles[value['$ref']])
        return {k: resolve(v, handles) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, handles) for v in value]
    return deepcopy(value)


def observed_effects(observer):
    # Absence of instrumentation is unknown, not a fabricated set of zeroes.
    return observer() if observer is not None else None


def call_workflow(function, run, effect_observer=None):
    request = deepcopy(run['request'])
    before = deepcopy(request)
    try:
        output = function(request)
        error = None
    except (ValueError, TypeError) as exc:
        output, error = None, {'type': type(exc).__name__, 'message': str(exc)}
    return {'output': output, 'error': error, 'input_unchanged': request == before,
            'effects': observed_effects(effect_observer)}


def market_snapshot(market):
    return {'gap': market.gap,
            'profiles': [asdict(market.profiles[k]) for k in sorted(market.profiles)],
            'assignments': [asdict(market.assignments[k]) for k in sorted(market.assignments)]}


def execute_market(module, run, effect_observer=None):
    data = deepcopy(run)
    initial = data['initial_state']
    market = module.Marketplace(initial['gap'])
    for profile in initial['profiles']:
        market.register(module.Profile(**profile))
    for assignment in initial['assignments']:
        item = module.Assignment(**assignment)
        if item.id in market.assignments:
            raise ValueError('duplicate_initial_assignment')
        market.assignments[item.id] = item
    handles, trace = {}, []
    for step in data['steps']:
        args = resolve(step['arguments'], handles)
        before = market_snapshot(market)
        try:
            operation = step['operation']
            if operation == 'register':
                result = market.register(module.Profile(**args['profile']))
            elif operation == 'check_in':
                result = market.check_in(args['profile_id'], step['clock'])
            elif operation == 'expire':
                result = market.expire(step['clock'])
            elif operation == 'reject':
                result = market.reject(**args)
            elif operation == 'report_local':
                result = market.report_local(**args)
            elif operation == 'link_html':
                result = market.link_html(**args)
            else:
                raise ValueError('unsupported_operation')
            if step.get('save_as'):
                assignment = result.get('assignment') if isinstance(result, dict) else None
                if not isinstance(assignment, dict) or not isinstance(assignment.get('id'), str):
                    raise ValueError('missing_returned_assignment_handle')
                if step['save_as'] in handles:
                    raise ValueError('duplicate_handle_name')
                handles[step['save_as']] = assignment['id']
            response = {'ok': True, 'value': result}
        except (ValueError, TypeError, KeyError) as exc:
            response = {'ok': False, 'error_type': type(exc).__name__, 'error': str(exc)}
        trace.append({'operation': step['operation'], 'clock': step['clock'], 'before': before,
                      'response': response, 'after': market_snapshot(market)})
    return {'trace': trace, 'final_state': market_snapshot(market), 'input_unchanged': data == run,
            'effects': observed_effects(effect_observer)}


def execute_crm(store_factory, interpret, run, preview=None, effect_observer=None):
    """store_factory creates a fresh disposable SyntheticStore-compatible instance.

    interpret(text, public_store) must return structured_request + inference evidence,
    or status=clarification/refused. A missing callback blocks natural-language work.
    Fresh reads use store_factory(reopen=True), never a cached object. The caller
    chooses/cleans a unique local store; this adapter never accepts a filesystem path.
    """
    if run.get('mode') == 'structured_preview':
        if preview is None:
            raise CapabilityUnavailable('preview interface unavailable')
        return call_workflow(preview, run, effect_observer)
    supplied = deepcopy(run)
    store = store_factory(reopen=False)
    initial = store.initialize(deepcopy(run['initial_store']['contacts']))
    trace, proposal, approval, command = [], None, None, None
    inference, blocked, intent_status = False, None, None
    for operation in run['sequence']:
        before = store_factory(reopen=True).read()
        try:
            if operation == 'interpret':
                if interpret is None:
                    raise CapabilityUnavailable('authorized natural-language inference unavailable')
                intent = interpret(run['request'], deepcopy(before))
                inference = intent.get('inference_executed') is True
                if not inference:
                    raise CapabilityUnavailable('interpreter did not establish actual inference')
                intent_status = intent.get('status')
                command = intent.get('structured_request')
                result = intent
            elif operation == 'structured_command':
                command = deepcopy(run['structured_request'])
                result = {'component_only': True}
            elif operation == 'propose':
                proposal = store.propose(command)
                result = deepcopy(proposal)
            elif operation == 'approve_exact':
                approval = store.decide(proposal, approved=True)
                result = deepcopy(approval)
            elif operation == 'deny_exact':
                result = store.decide(proposal, approved=False)
            elif operation == 'apply_without_approval':
                result = store.apply(proposal, None)
            elif operation == 'apply_exact':
                result = store.apply(proposal, approval)
            elif operation == 'fresh_read':
                result = store_factory(reopen=True).read()
            elif operation == 'intervening_approved_change':
                other = store.propose(deepcopy(run['intervening_change']))
                result = store.apply(other, store.decide(other, approved=True))
            elif operation == 'tamper_proposal':
                proposal = deepcopy(proposal)
                change = run['tamper']
                for contact in proposal['after']:
                    if contact['id'] == change['contact_id']:
                        contact[change['field']] = change['value']
                result = {'tampered_local_copy': True}
            else:
                raise ValueError('unsupported_operation')
            response = {'ok': True, 'value': result}
        except CapabilityUnavailable as exc:
            blocked = str(exc)
            response = {'ok': False, 'blocked': blocked}
        except (ValueError, TypeError, OSError) as exc:
            response = {'ok': False, 'error_type': type(exc).__name__, 'error': str(exc)}
        after = store_factory(reopen=True).read()
        trace.append({'operation': operation, 'before': before, 'response': response, 'after': after})
        if blocked:
            break
    return {'initial': initial, 'trace': trace, 'final': store_factory(reopen=True).read(),
            'inference_executed': inference, 'intent_status': intent_status, 'blocked': blocked,
            'input_unchanged': supplied == run, 'effects': observed_effects(effect_observer)}
