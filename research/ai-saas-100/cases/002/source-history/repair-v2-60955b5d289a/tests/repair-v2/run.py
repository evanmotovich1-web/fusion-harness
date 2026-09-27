"""Offline exact-trace evaluator. Oracles never enter the adapter's input."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import socket
import sys
import time

HERE=Path(__file__).resolve().parent
CASE=HERE.parents[1]
def deny_network(*args,**kwargs):
    raise AssertionError('network_forbidden_in_local_regression')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=CASE/'implementation/workflow.py')
    args=parser.parse_args();source=args.source.resolve()
    if not source.is_relative_to(CASE):raise ValueError('source_must_be_inside_case_002')
    spec=importlib.util.spec_from_file_location('marketplace_under_test',source)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    adapter=runpy.run_path(str(HERE/'adapter.py'))['execute']
    inputs=json.loads((HERE/'comparison-inputs.json').read_text())
    oracle=json.loads((HERE/'evaluator.json').read_text())
    expected={x['id']:x for x in oracle['cases']}
    assert len(expected)==len(inputs['cases'])==len(set(x['id'] for x in inputs['cases']))
    socket.socket=deny_network;socket.create_connection=deny_network
    results=[]
    for bundle in inputs['cases']:
        before=copy.deepcopy(bundle);start=time.monotonic();row={'test_id':bundle['id']}
        try:
            actual=adapter(module,bundle)
            assert bundle==before,'caller_input_mutated'
            row['output']=actual
            assert actual==expected[bundle['id']]['expected'],'exact_trace_or_final_state_mismatch'
            # Renaming opaque IDs must not change interface execution.
            renamed=copy.deepcopy(bundle);renamed['id']='unrecognized-label'
            assert adapter(module,renamed)==actual,'scenario_id_affects_execution'
            row['outcome']='passed'
        except Exception as exc:
            row.update(outcome='failed',error=type(exc).__name__+': '+str(exc),expected=expected[bundle['id']]['expected'])
        row['elapsed_seconds']=time.monotonic()-start;results.append(row)
    result={'case_id':'002','source_path':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'interface_transformation_sha256':hashlib.sha256((HERE/'adapter.py').read_bytes()).hexdigest(),'input_bundle_sha256':hashlib.sha256((HERE/'comparison-inputs.json').read_bytes()).hexdigest(),'oracle_sha256':hashlib.sha256((HERE/'evaluator.json').read_bytes()).hexdigest(),'scope':'Builder-visible exact local regression only. No model baseline, hidden evaluation, external marketplace, publication, or product acceptance.','network_guard':'socket construction and create_connection raise','results':results,'passed':sum(r['outcome']=='passed' for r in results),'failed':sum(r['outcome']=='failed' for r in results),'product_acceptance':False}
    print(json.dumps(result,indent=2));return 0 if result['failed']==0 else 1
if __name__=='__main__':raise SystemExit(main())
