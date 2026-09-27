"""Runnable structured proposal/approval/persistence demo using disposable local data."""
import json
from pathlib import Path
import tempfile

from persistence import SyntheticStore, STORAGE_ROOT


def main():
    STORAGE_ROOT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='demo-', dir=STORAGE_ROOT) as folder:
        name = Path(folder).name
        store = SyntheticStore(name)
        before = store.initialize([
            {'id': 'demo-1', 'email': 'demo@example.invalid', 'status': 'new', 'note': ''},
            {'id': 'demo-2', 'email': 'other@example.invalid', 'status': 'new', 'note': 'Keep unchanged'},
        ])
        proposal = store.propose({'action': 'update', 'patch': {'id': 'demo-1', 'status': 'qualified'}})
        if store.read() != before:
            raise AssertionError('Proposal changed domain data')
        approval = store.decide(proposal, approved=True)
        applied = store.apply(proposal, approval)
        fresh = SyntheticStore(name).read()
        if fresh != applied['store'] or fresh['contacts'][0]['status'] != 'qualified':
            raise AssertionError('Fresh read did not confirm update')
        if fresh['contacts'][1] != before['contacts'][1]:
            raise AssertionError('Unrelated contact changed')
        output = {'before': before, 'proposal': proposal, 'approval': approval,
                  'application': applied, 'fresh_read': fresh,
                  'storage': 'Temporary case-local directory, removed after demo',
                  'natural_language': 'unavailable', 'product_acceptance': False}
    print(json.dumps({'results': [{'test_id': 'synthetic-roundtrip-demo', 'outcome': 'passed',
                                   'output': output}]}, indent=2))


if __name__ == '__main__':
    main()
