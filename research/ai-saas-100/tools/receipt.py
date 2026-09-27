"""Emit an unexecuted receipt template. Never runs commands or infers measurements."""
import argparse
import json
from validate import case_id


def unknown_metric(unit, category='unknown'):
    return {'value': None, 'unit': unit, 'classification': 'unknown', 'category': category,
            'assumptions': [], 'unknown_reason': 'Not measured'}


def receipt_template(identifier, run_id, system='B2'):
    case_id(identifier)
    if not run_id or system not in {'B1', 'B2', 'B3'}:
        raise ValueError('run ID and B1/B2/B3 system required')
    return {
        'schema_version': 1, 'case_id': identifier, 'run_id': run_id, 'system': system,
        'status': 'not_started', 'started_at': None, 'ended_at': None,
        'command': [], 'cwd': None, 'implementation': None, 'fixtures': None,
        'input_bundle': None, 'outputs': [], 'runtime': {},
        'model': {'provider': None, 'requested_id': None, 'resolved_version': None,
                  'unknown_reason': 'No inference executed'},
        'configuration': {}, 'baseline_id': None, 'exit_status': None,
        'test_results': [], 'quality': [], 'latency': unknown_metric('seconds'),
        'usage': {'value': None, 'unknown_reason': 'Not measured'},
        'costs': [unknown_metric('USD')], 'errors': [], 'retries': [], 'timeouts': [],
        'missing_capabilities': [], 'redactions': [], 'human_interventions': [],
        'execution_kind': 'unknown', 'inference_executed': False,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case_id')
    parser.add_argument('run_id')
    parser.add_argument('--system', choices=['B1', 'B2', 'B3'], default='B2')
    args = parser.parse_args()
    print(json.dumps(receipt_template(args.case_id, args.run_id, args.system), indent=2))
