"""Check archival integrity and source-bound local repair receipts, then repeat v2."""
import datetime, hashlib, json, pathlib, re, runpy, subprocess, sys, time
HERE=pathlib.Path(__file__).resolve().parent
CASE=HERE.parents[1]
ROOT=CASE.parents[1]
def load(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def checked(ref):
    p=ROOT/ref['path'];assert sha(p)==ref['sha256'],str(p);return p

def main():
    started=datetime.datetime.now(datetime.timezone.utc).isoformat();t=time.monotonic()
    historical=load(CASE/'source-history/pre-repair-287e153d1e4f/manifest.json')
    mapping={r['original_path']:r for r in historical['files']}
    editable={'cases/002/implementation/workflow.py','cases/002/dossier.json'}
    preserved=[]
    for row in historical['files']:
        assert sha(ROOT/row['archive_path'])==row['sha256']
        if row['original_path'] not in editable:
            assert sha(ROOT/row['original_path'])==row['sha256'];preserved.append(row['original_path'])
    old=load(CASE/'receipts/002-local-20260920T212619053188Z.json')
    for ref in [old['implementation'],old['fixtures'],old['input_bundle'],old['configuration']['runner'],*old['outputs']]:
        row=mapping[ref['path']];assert ref['sha256']==row['sha256']==sha(ROOT/row['archive_path'])
    freeze=load(HERE/'freeze.json')
    for item in freeze['artifacts']:checked(item)
    payload=load(HERE/'comparison-inputs.json');oracle=load(HERE/'evaluator.json')
    def no_answers(value):
        if isinstance(value,dict):
            assert not {'expected','scenario','scenario_name','oracle','description'}.intersection(value)
            for v in value.values():no_answers(v)
        elif isinstance(value,list):
            for v in value:no_answers(v)
    no_answers(payload)
    assert len(payload['cases'])==len(oracle['cases'])==54
    assert len({c['id'] for c in payload['cases']})==54
    for case in payload['cases']:
        assert set(case)=={'id','initial_state','requests'}
        assert set(case['initial_state'])=={'gap','profiles','assignments'}
        for p in case['initial_state']['profiles']:assert set(p)=={'id','target','area','dr','review'}
        for a in case['initial_state']['assignments']:assert set(a)=={'id','source','target','created','deadline','status','reason','reported_url'}
        for r in case['requests']:assert set(r)=={'operation','arguments','clock'}
    v=runpy.run_path(str(ROOT/'tools/validate.py'))
    index=load(HERE/'execution-index.json');manifest=load(checked(index['source_bundle']))
    for member in manifest['members']:
        checked(member);assert sha(ROOT/member['active_path'])==member['sha256']
    for row in index['runs']:
        r=load(ROOT/row['receipt_path']);v['receipt'](r,ROOT)
        assert r['status']=='completed' and r['exit_status']==0 and not r['inference_executed']
        assert not r['product_acceptance'] and all(x['outcome']=='passed' for x in r['test_results'])
        checked(r['configuration']['source_bundle']);checked(r['configuration']['runner'])
        if r['configuration']['interface_transformation']:checked(r['configuration']['interface_transformation'])
    dossier=load(CASE/'dossier.json')
    sources=v['evidence'](load(ROOT/'discovery/evidence.json'),ROOT)|v['evidence'](load(CASE/'evidence.json'),ROOT)
    assert v['dossier'](dossier,sources,ROOT) is False
    before=load(CASE/'receipts/repair-v2-before.json');before_raw=load(pathlib.Path(before['stdout_path']))
    assert sha(pathlib.Path(before['stdout_path']))==before['stdout_sha256']
    assert before_raw['source_sha256']==old['implementation']['sha256']
    assert before_raw['input_bundle_sha256']==sha(HERE/'comparison-inputs.json')
    assert before_raw['interface_transformation_sha256']==sha(HERE/'adapter.py')
    assert before_raw['oracle_sha256']==sha(HERE/'evaluator.json')
    assert before_raw['passed']==41 and before_raw['failed']==13
    command=[sys.executable,'-B',str(HERE/'run.py')]
    result=subprocess.run(command,capture_output=True,text=True,timeout=20)
    out=HERE/'validation-repeat.stdout.json';assert not out.exists();out.write_text(result.stdout)
    data=json.loads(result.stdout);assert result.returncode==0 and data['passed']==54 and data['failed']==0
    receipt={'schema_version':1,'case_id':'002','task_id':'1.c','status':'passed','started_at':started,'ended_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'elapsed_seconds':time.monotonic()-t,'command':[sys.executable,str(pathlib.Path(__file__).resolve())],'counts':{'original_artifacts_archived':len(mapping),'original_artifacts_preserved_in_place':len(preserved),'pre_repair_passed':41,'pre_repair_failed':13,'repaired_cases_passed':54,'legacy_cases_passed':20,'independent_repeat_passed':54,'accepted_products':0},'checks':['All original source-history bytes and immutable current artifacts match pre-edit manifest','Original receipt references resolve to exact archived sources/inputs/outputs without rewriting receipt','Frozen complete input/state/request/clock bundles contain no evaluator answer fields','Every post-repair receipt and nested source-bundle member hash validates','Current dossier is structurally valid and remains unaccepted','Same v2 suite independently reinvoked in foreground; no model or live-marketplace test claimed'],'preserved_paths':preserved,'repeat':{'command':command,'exit_status':result.returncode,'stdout_path':str(out.relative_to(ROOT)),'stdout_sha256':sha(out),'stderr':result.stderr},'held_out':False,'model_baseline_executed':False,'original_product_observed':False,'scope':'Local repair and provenance validation only. Independent review still required.'}
    target=HERE/'validation.json';assert not target.exists();target.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':'passed','counts':receipt['counts'],'validation':str(target.relative_to(ROOT))},indent=2))
if __name__=='__main__':main()
