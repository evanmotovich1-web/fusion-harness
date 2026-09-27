"""Control-plane regressions, explicitly not generated-rewrite benchmarks."""
import importlib.util
import json
from pathlib import Path
import time

CASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rewrite_control', CASE / 'implementation/workflow.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


def main():
    fixtures = json.loads((CASE / 'tests/fixtures.json').read_text())
    rows = []
    for fixture in fixtures['cases']:
        tick = time.monotonic()
        result = w.run(fixture['input'])
        if fixture['expected']['input_valid']:
            passed = result['status'] == 'blocked_inference' and result['output'] is None and not result['inference_executed']
            product = 'blocked'
        else:
            passed = result['status'] == 'invalid_input' and result['error'] == fixture['expected']['error']
            product = 'invalid_input_handled' if passed else 'failed'
        rows.append({'test_id': fixture['id'], 'outcome': 'passed' if passed else 'failed',
                     'product_outcome': product, 'output': result, 'split': fixture['split'],
                     'elapsed_seconds': time.monotonic() - tick})
    print(json.dumps({'scope': 'Partial control-plane tests only. No rewrite or model execution.', 'results': rows}, indent=2))
    return 0 if all(r['outcome'] == 'passed' for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
