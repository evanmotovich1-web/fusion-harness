"""Pure JSON-to-local-interface transformation, independent of case IDs/oracles."""
from dataclasses import asdict
import copy


def snapshot(market):
    return {'gap': market.gap,
            'profiles': [asdict(market.profiles[k]) for k in sorted(market.profiles)],
            'assignments': [asdict(market.assignments[k]) for k in sorted(market.assignments)]}


def execute(module, bundle):
    """Apply explicit initial state and ordered requests. No inference or network."""
    data = copy.deepcopy(bundle)
    state = data['initial_state']
    market = module.Marketplace(state['gap'])
    for profile in state['profiles']:
        market.register(module.Profile(**profile))
    for assignment in state['assignments']:
        item = module.Assignment(**assignment)
        if item.id in market.assignments or item.source not in market.profiles or item.target not in market.profiles:
            raise ValueError('invalid_initial_assignment')
        market.assignments[item.id] = item
    trace = []
    for request in data['requests']:
        operation, args, clock = request['operation'], request['arguments'], request['clock']
        before = snapshot(market)
        try:
            if operation == 'register':
                value = market.register(module.Profile(**args['profile']))
            elif operation == 'check_in':
                value = market.check_in(args['profile_id'], clock)
            elif operation == 'expire':
                value = market.expire(clock)
            elif operation == 'reject':
                value = market.reject(args['assignment_id'], args['reason'])
            elif operation == 'report_local':
                value = market.report_local(**args)
            elif operation == 'link_html':
                value = market.link_html(**args)
            else:
                raise ValueError('unsupported_operation')
            result = {'status': 'ok', 'value': value}
        except (ValueError, TypeError, KeyError) as exc:
            result = {'status': 'error', 'error_type': type(exc).__name__, 'error': str(exc)}
        trace.append({'operation': operation, 'clock': clock, 'result': result,
                      'before': before, 'after': snapshot(market)})
    assert bundle == data, 'adapter mutated input bundle'
    return {'trace': trace, 'final_state': snapshot(market), 'published': False, 'live_verified': False}
