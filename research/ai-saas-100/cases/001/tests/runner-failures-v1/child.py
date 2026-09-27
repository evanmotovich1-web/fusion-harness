"""Short synthetic foreground child. No network, inference, files written, or descendants."""
import json
from pathlib import Path
import sys
import time

mode = sys.argv[1]
suite = json.loads(Path(sys.argv[2]).read_text())
rows = [{'test_id': case['id'], 'outcome': 'passed'} for case in suite['cases']]
if mode == 'timeout':
    print('partial stdout before timeout', flush=True)
    print('partial stderr before timeout', file=sys.stderr, flush=True)
    time.sleep(2)
elif mode == 'malformed_json':
    print('{not valid JSON')
    raise SystemExit(0)
elif mode == 'invalid_utf8':
    sys.stdout.buffer.write(b'\xff')
    raise SystemExit(0)
elif mode == 'root_array':
    print('[]')
    raise SystemExit(0)
elif mode == 'null_results':
    print('{"results": null}')
    raise SystemExit(0)
elif mode == 'row_array':
    rows = [[]]
elif mode == 'missing_key':
    rows[0] = {'outcome': 'passed'}
elif mode == 'bad_outcome_type':
    rows[0]['outcome'] = []
elif mode == 'bad_outcome':
    rows[0]['outcome'] = 'accepted'
elif mode == 'duplicate_id':
    rows[1]['test_id'] = rows[0]['test_id']
elif mode == 'missing_result':
    rows.pop()
elif mode == 'unexpected_id':
    rows[0]['test_id'] = 'not-in-suite'
elif mode == 'assertion_failed':
    rows[0]['outcome'] = 'failed'
elif mode == 'assertion_blocked':
    rows[0]['outcome'] = 'blocked'
print(json.dumps({'results': rows}))
if mode == 'nonzero_exit':
    print('deliberate synthetic failure', file=sys.stderr)
    raise SystemExit(7)
