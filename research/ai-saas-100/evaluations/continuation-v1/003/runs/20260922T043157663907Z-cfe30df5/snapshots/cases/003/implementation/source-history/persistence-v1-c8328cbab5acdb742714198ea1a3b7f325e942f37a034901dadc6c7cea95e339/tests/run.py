"""Local CRM preview regressions. Not chat-to-CRM integration benchmarks."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import time

CASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('crm_preview', CASE / 'implementation/workflow.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


def main():
    fixtures = json.loads((CASE / 'tests/fixtures.json').read_text())
    rows = []
    for fixture in fixtures['cases']:
        tick = time.monotonic()
        before = deepcopy(fixture['input'])
        output = w.run(fixture['input'])
        valid = fixture['expected']['local_operation'] != 'reject'
        try:
            assert before == fixture['input']
            assert output['messages_sent'] == 0 and output['crm_written'] is False
            if not valid:
                assert output['status'] == 'invalid_input'
            else:
                assert output['status'] == 'local_preview'
                if before['action'] == 'update':
                    for key, value in before['patch'].items():
                        assert output['operations'][0]['after'][key] == value
                else:
                    # Independent fixture-derived oracle: count duplicate occurrences.
                    emails = [c['email'].strip().lower() for c in before['contacts']]
                    expected_duplicates = len(emails) - len(set(emails))
                    assert sum(len(x['duplicate_ids']) for x in output['operations']) == expected_duplicates
            outcome = 'passed'
        except AssertionError:
            outcome = 'failed'
        rows.append({'test_id': fixture['id'], 'outcome': outcome, 'output': output,
                     'product_outcome': 'blocked' if valid else 'invalid_input_handled',
                     'split': fixture['split'], 'elapsed_seconds': time.monotonic() - tick})
    print(json.dumps({'scope': 'Structured local previews only. No natural-language inference or CRM writes.', 'results': rows}, indent=2))
    return 0 if all(r['outcome'] == 'passed' for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
