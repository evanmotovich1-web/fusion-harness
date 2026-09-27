"""Run bounded offline repairs and preserve source-bound receipts, including failures."""
import copy, datetime, hashlib, json, pathlib, platform, subprocess, sys, time
HERE=pathlib.Path(__file__).resolve().parent
CASE=HERE.parents[1]
ROOT=CASE.parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def ref(path):return {'path':str(path.relative_to(ROOT)),'sha256':sha(path)}
def write(path,obj):
    assert not path.exists(),f'Refusing overwrite: {path}'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2)+'\n')

def main():
    source=CASE/'implementation/workflow.py'
    members=[]
    files=[source,HERE/'adapter.py',HERE/'run.py',HERE/'execute.py',CASE/'tests/run.py']
    fingerprint=json.dumps([(str(p.relative_to(CASE)),sha(p)) for p in files]).encode()
    history=CASE/'source-history'/('repair-v2-'+hashlib.sha256(fingerprint).hexdigest()[:12])
    for p in files:
        dest=history/p.relative_to(CASE);dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():dest.write_bytes(p.read_bytes())
        assert dest.read_bytes()==p.read_bytes()
        members.append({'active_path':str(p.relative_to(ROOT)),**ref(dest)})
    manifest=history/'source-bundle.json'
    if not manifest.exists():write(manifest,{'schema_version':1,'case_id':'002','archived_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'members':members})
    assert json.loads(manifest.read_text())['members']==members
    template=json.loads((CASE/'source-history/pre-repair-287e153d1e4f/receipts/002-local-20260920T212619053188Z.json').read_text())
    outputs=[]
    for label,runner,fixtures,inputs in [('repair-v2',HERE/'run.py',HERE/'evaluator.json',HERE/'comparison-inputs.json'),('legacy-regression-after-repair',CASE/'tests/run.py',CASE/'tests/fixtures.json',CASE/'tests/fixtures.json')]:
        run_id='002-'+label+'-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        command=[sys.executable,'-B',str(runner)]
        start=datetime.datetime.now(datetime.timezone.utc).isoformat();t=time.monotonic();errors=[];timeouts=[]
        try:
            proc=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=15)
            stdout,stderr,code=proc.stdout,proc.stderr,proc.returncode
        except subprocess.TimeoutExpired as exc:
            def text(v):return v.decode(errors='replace') if isinstance(v,bytes) else v or ''
            stdout,stderr,code=text(exc.stdout),text(exc.stderr),-1
            errors.append('Local regression subprocess timed out');timeouts.append({'seconds':15})
        except OSError as exc:
            stdout,stderr,code='',str(exc),-1;errors.append(type(exc).__name__+': '+str(exc))
        elapsed=time.monotonic()-t;end=datetime.datetime.now(datetime.timezone.utc).isoformat()
        out=CASE/'receipts'/(run_id+'.stdout.json');err=CASE/'receipts'/(run_id+'.stderr.txt')
        assert not out.exists() and not err.exists();out.write_text(stdout);err.write_text(stderr)
        try:rows=json.loads(stdout)['results']
        except (ValueError,KeyError):rows=[];errors.append('Missing structured test output')
        if code:errors.append('Regression subprocess exit '+str(code))
        assert all(sha(ROOT/m['active_path'])==m['sha256'] for m in members),'Source changed during run'
        r=copy.deepcopy(template)
        r.update(run_id=run_id,status='completed' if code==0 else 'failed',started_at=start,ended_at=end,command=command,cwd=str(ROOT),implementation=ref(history/'implementation/workflow.py'),fixtures=ref(fixtures),input_bundle=ref(inputs),outputs=[ref(out),ref(err)],runtime={'python':platform.python_version(),'platform':platform.platform()},configuration={'network':False,'mode':label,'concurrency':1,'model_calls':0,'timeout_seconds':15,'runner':ref(history/runner.relative_to(CASE)),'source_bundle':ref(manifest),'interface_transformation':ref(history/HERE.relative_to(CASE)/'adapter.py') if label=='repair-v2' else None,'comparison_inputs_self_contained':label=='repair-v2','legacy_inputs_not_for_model_comparison':label!='repair-v2','oracle_separate_from_input':label=='repair-v2'},exit_status=code,test_results=[{'test_id':row['test_id'],'outcome':row['outcome']} for row in rows],errors=errors,timeouts=timeouts,human_interventions=['Builder-visible fixed regression; no hidden evaluation or baseline.'],product_acceptance=False)
        r['latency'].update(value=elapsed,unknown_reason=None)
        path=CASE/'receipts'/(run_id+'.json');write(path,r)
        outputs.append({'receipt_path':str(path.relative_to(ROOT)),'passed':sum(x['outcome']=='passed' for x in rows),'failed':sum(x['outcome']=='failed' for x in rows),'exit_status':code})
    result={'schema_version':1,'case_id':'002','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_bundle':ref(manifest),'runs':outputs,'accepted_product':False,'scope':'Local repair evidence only. Baseline and independent hidden evaluation remain missing.'}
    write(HERE/'execution-index.json',result)
    print(json.dumps(result,indent=2));return 0 if all(x['exit_status']==0 and x['failed']==0 for x in outputs) else 1
if __name__=='__main__':raise SystemExit(main())
