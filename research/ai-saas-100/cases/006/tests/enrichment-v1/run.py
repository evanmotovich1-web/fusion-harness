"""Case-006 deterministic method checks. No generative-workflow acceptance."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import time

CASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CASE / 'implementation'))
from enrichment import run
ACTIVE = False
ATTEMPTS = []


def audit(event, args):
    if ACTIVE and (event == 'open' or event.startswith(('socket.', 'subprocess.', 'os.system'))):
        ATTEMPTS.append(event)
        raise AssertionError('I/O during pure enrichment: ' + event)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def verify_provenance(request, output):
    sources = {s['id']: s for s in request['sources']}
    for record in output['records']:
        for field, info in record['provenance'].items():
            for item in info['observations']:
                source = sources[item['source_id']]
                check(source[field] == item['value'] and source['provider'] == item['provider'] and
                      source['retrieved_at'] == item['retrieved_at'], 'Provenance changed source facts')
            for identifier in info['selected_source_ids']:
                check(sources[identifier][field] == record['fields'][field], 'Selected value unsupported')
        for excerpt in record['source_excerpts']:
            check(excerpt['text'] == sources[excerpt['source_id']]['text'], 'Source excerpt altered')


def main():
    global ACTIVE
    suite = json.loads(Path(__file__).with_name('fixtures.json').read_text())
    original = json.loads((CASE / 'tests/specification.json').read_text())
    jobs = [('component', f) for f in suite['cases']] + [('original', f) for f in original['cases']]
    rows = []
    sys.addaudithook(audit)
    for kind, fixture in jobs:
        identifier = fixture.get('id', fixture.get('test_id'))
        request = deepcopy(fixture['input'])
        before = deepcopy(request)
        row = {'test_id': identifier, 'outcome': 'failed', 'product_acceptance': False}
        tick = time.monotonic()
        ATTEMPTS.clear()
        try:
            ACTIVE = True
            try:
                output = run(request)
            finally:
                ACTIVE = False
            row['output'] = output
            check(request == before, 'Input mutation')
            check(not ATTEMPTS, 'I/O attempted')
            check(output['inference_executed'] is False and output['external_calls'] == 0, 'False execution claims')
            expected = fixture['expected']
            if kind == 'component' and 'error' in expected:
                check(output['status'] == 'invalid_input' and output['error'] == expected['error'], 'Wrong rejection')
            elif kind == 'original' and fixture.get('scenario') in {'empty_input', 'wrong_type', 'unsafe_path', 'unauthorized_action'}:
                check(output['status'] == 'invalid_input', 'Expected typed rejection')
            else:
                check(output['status'] == 'component_complete', 'Component failed')
                verify_provenance(request, output)
                first = output['records'][0]
                if kind == 'component':
                    check(first['fields']['employees'] == expected['selected_employees'], 'Wrong employee selection')
                    selected = first['provenance']['employees']['selected_source_ids']
                    check(selected == ([] if expected['selected_source'] is None else [expected['selected_source']]), 'Wrong selected provenance')
                    check(bool(output['conflicts']) is expected['conflict'], 'Conflict erased or invented')
                    for field in expected.get('missing', []):
                        check(field in first['missing_fields'] and first['fields'][field] is None, 'Missing value invented')
                    if 'country' in expected:
                        check(first['fields']['country'] == expected['country'], 'Country fallback failed')
                    if 'email' in expected:
                        check(first['fields']['contact_email'] == expected['email'], 'Email fallback failed')
                    if expected.get('unknown_company'):
                        check(all(value is None for value in output['records'][1]['fields'].values()), 'Unknown company populated')
                else:
                    primary = request['sources'][0]
                    check(first['fields']['employees'] == primary['employees'], 'Primary field changed')
                    check(first['fields']['country'] == 'GB', 'Wrong country')
                    check(first['fields']['contact_email'] is None, 'Invented email')
                    check(first['fields']['business_summary'] is None, 'Fabricated generated summary')
                    check(all(value is None for value in output['records'][1]['fields'].values()), 'Unknown company populated')
                    check(any(c['field'] == 'employees' for c in output['conflicts']), 'Historical discrepancy lost')
                    check(output['unresolved_additional_sources'] == request.get('additional_sources', []), 'Additional evidence lost')
            row['outcome'] = 'passed'
        except Exception as exc:
            row['error'] = type(exc).__name__ + ': ' + str(exc)
        row.update(elapsed_seconds=time.monotonic() - tick, io_attempts=list(ATTEMPTS), input_unchanged=request == before)
        rows.append(row)
    print(json.dumps({'schema_version': 1, 'case_id': '006', 'results': rows,
                      'scope': 'Component assertions over 12 new and 20 historical inputs. Not full frozen-workflow acceptance.',
                      'held_out': False, 'inference_executed': False, 'product_acceptance': False}, indent=2))
    return 0 if all(row['outcome'] == 'passed' for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
