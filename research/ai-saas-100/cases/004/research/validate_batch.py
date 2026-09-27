#!/usr/bin/env python3
"""Validate research/fixture handoff only. Never executes a product workflow."""
import audioop, datetime, hashlib, json, pathlib, re, runpy, shutil, subprocess, sys, time, wave
from PIL import Image
ROOT=pathlib.Path(__file__).resolve().parents[3]
HERE=pathlib.Path(__file__).resolve().parent
START=datetime.datetime.now(datetime.timezone.utc).isoformat();T=time.monotonic()
V=runpy.run_path(str(ROOT/'tools/validate.py'))
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check_quote(q,source):
    loc=q['locator']
    if loc=='title':value=source['title']
    elif loc.startswith('metadata['):value=source['metadata'][int(re.search(r'\[(\d+)\]',loc).group(1))]['value']
    elif loc.startswith('text characters '):
        a,b=map(int,re.search(r'(\d+):(\d+)',loc).groups());value=source['text'][a:b]
    else:raise AssertionError(loc)
    assert value==q['excerpt'],loc
batch=load(ROOT/'batches/research-004-035.json');registry=load(ROOT/'registry.json')
assert batch['assigned_ids']==[f'{i:03}' for i in range(4,36)]
protected=load(HERE/'task-start.json')['protected_sha256']
for rel,h in protected.items():assert sha(ROOT/rel)==h,f'Protected file changed: {rel}'
rows=[];quoted=0;fixtures=0;asset_count=0;decoded_audio=0;decoded_images=0;new_attempts=0;failures=0
for row in batch['products']:
    cid=row['id'];folder=ROOT/'cases'/cid;d=load(folder/'dossier.json');e=load(folder/'evidence.json');spec=load(folder/'tests/specification.json');freeze=load(folder/'tests/freeze.json')
    known=V['evidence'](e,ROOT);accepted=V['dossier'](d,known,ROOT);assert accepted is False
    p=next(x for x in registry['products'] if x['id']==cid)
    assert d['identity']['canonical_url']==p['canonical_url'] and d['identity']['name']==p['name']
    assert d['assessment']['stage_statuses']['research']=='in_progress'
    assert all(d['assessment']['stage_statuses'][s]=='not_started' for s in ('implementation','execution','evaluation','review'))
    assert d['implementation']['source_path'] is None and d['assessment']['receipt_paths']==[]
    assert len(spec['cases'])==20
    assert len({x['test_id'] for x in spec['cases']})==20
    assert sum(x['split']=='development' for x in spec['cases'])==6
    assert sum(x['split']=='fixed_regression_normal' for x in spec['cases'])==8
    assert sum(x['split']=='fixed_regression_failure' for x in spec['cases'])==6
    assert spec['execution_status']=='not_started' and 'builder-visible' in spec['exposure']
    assert sha(ROOT/d['tests']['specification_path'])==d['tests']['sha256']==freeze['specification_sha256']
    assert spec['asset_manifest']==freeze['assets'];fixtures+=20
    for asset in freeze['assets']:
        file=ROOT/asset['path'];assert file.is_relative_to(folder/'tests/assets') and sha(file)==asset['sha256'];asset_count+=1
        if file.suffix=='.wav':
            with wave.open(str(file),'rb') as w:
                assert w.getframerate()==16000 and w.getnframes()>16000
                assert audioop.rms(w.readframes(w.getnframes()),w.getsampwidth())>0
            decoded_audio+=1
        if file.suffix=='.png' and not file.name.startswith('corrupt'):
            with Image.open(file) as img:img.verify()
            decoded_images+=1
        if file.suffix=='.pdf' and not file.name.startswith('corrupt'):assert file.read_bytes().startswith(b'%PDF-')
    sources={x['evidence_id']:x for x in e['sources']}
    for source in sources.values():
        raw=load(ROOT/source['record_path'])
        for q in source.get('excerpts',[]):check_quote(q,raw);quoted+=1
    for claim in d['claims']:
        for q in claim.get('supporting_excerpts',[]):check_quote(q,load(ROOT/sources[q['evidence_id']]['record_path']))
    local_records=[load(f) for f in (folder/'research/records').glob('*.json')]
    new_attempts+=len(local_records);failures+=sum(x['status']!='failed' and x['status']!=200 or x['status']=='failed' for x in local_records)
    assert row['new_page_attempts']==len(local_records)
    assert row['unresolved_topics']==[k for k,v in d['research'].items() if isinstance(v,dict) and v.get('unknown_reason')]
    rows.append({'id':cid,'structurally_valid':True,'product_accepted':False,'fixture_hash_valid':True,'fixture_count':20,'source_quotes_valid':True})
assert fixtures==640 and new_attempts==64 and failures==4
assert batch['counts']['accepted_products']==0 and batch['counts']['research_stage_passed']==0
assert not load(HERE/'replacement-proposals.json')['proposals']
ffprobe=shutil.which('ffprobe');assert ffprobe
command=[ffprobe,'-v','error','-show_entries','stream=codec_type,width,height,sample_rate:format=duration','-of','json',str(ROOT/'cases/031/tests/assets/source-video.mp4')]
p=subprocess.run(command,capture_output=True,text=True,timeout=10);assert p.returncode==0
media=json.loads(p.stdout);assert {s['codec_type'] for s in media['streams']}=={'video','audio'};assert float(media['format']['duration'])>30
receipt={'schema_version':1,'task_id':'3.b','started_at':START,'ended_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'elapsed_seconds':time.monotonic()-T,'command':[sys.executable,str(pathlib.Path(__file__).resolve())],'cwd':str(pathlib.Path.cwd()),'status':'passed','scope':'Offline structural, provenance, fixture and media-input validation. This is not a product execution, evaluation, held-out test, or independent acceptance.','counts':{'dossiers':32,'fixed_cases':fixtures,'indexed_quotes_checked':quoted,'asset_hashes_checked':asset_count,'spoken_wav_inputs_decoded':decoded_audio,'png_inputs_decoded':decoded_images,'new_public_page_attempts':new_attempts,'new_public_page_failures':failures,'products_accepted':0},'protected_files_unchanged':list(protected),'case_results':rows,'media_probe':{'command':command,'exit_status':p.returncode,'stdout':media,'stderr':p.stderr},'checks':['Campaign validator accepts all dossier/evidence structures without accepting products','Registry identity correspondence and zero implementation/execution inflation','All fixed specification and asset hashes match','All indexed and claim-level excerpts exactly match captured source records','Six development/eight exposed-normal/six failure cases per product','Spoken audio, original PNG/PDF inputs and actual video+audio container available','All previously recorded shared-file hashes unchanged','All 32 IDs accounted for, failed public-source attempts preserved, no replacement silently applied']}
(HERE/'validation.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'status':'passed','counts':receipt['counts'],'receipt':'cases/004/research/validation.json'},indent=2))
