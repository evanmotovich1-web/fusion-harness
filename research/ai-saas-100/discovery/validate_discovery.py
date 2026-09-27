#!/usr/bin/env python3
"""Offline validation of task 2.a's frozen identity-discovery handoff."""
import datetime
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import time
ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT/'discovery'
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
t0 = time.monotonic()
checks = []
def load(p):
    return json.loads(p.read_text())
command = [sys.executable, str(D/'build_registry.py'), '--check']
result = subprocess.run(command, capture_output=True, text=True, timeout=30)
assert result.returncode == 0, result.stdout + result.stderr
checks.append('Offline deterministic replay matches all four generated outputs')
freeze=load(D/'freeze.json')
for rel,expected in {**freeze['input_sha256'],**freeze['source_record_sha256']}.items():
    assert hashlib.sha256((D/rel).read_bytes()).hexdigest()==expected, rel
checks.append('All frozen input and source-record hashes match')
r=load(ROOT/'registry.json'); s=load(ROOT/'selection.json'); ev=load(D/'evidence.json')['sources']
assert len(r['products'])==100 and len(r['alternates'])==25
assert [p['id'] for p in r['products']]==[f'{i:03}' for i in range(1,101)]
assert len({p['registrable_domain'] for p in r['products']+r['alternates']})==125
assert set(s['selected_counts'].values())=={10} and len(s['selected_counts'])==10
assert len({p['category'] for p in r['products'] if p['pilot']})==3
checks.append('100 contiguous selected IDs, 25 disjoint alternates, ten per stratum, three distinct pilot strata')
by_eid={e['evidence_id']:e for e in ev}
for p in r['products']+r['alternates']:
    assert p['identity_evidence_ids']
    for eid in p['identity_evidence_ids']:
        assert by_eid[eid]['status']==200 and by_eid[eid]['source_type']=='first_party_product_page'
        assert by_eid[eid]['excerpts']
    assert p['customer_count'] is None and p['customer_count_status']=='unknown'
    assert p['stage_statuses']['identity']=='passed'
    assert all(v=='not_started' for k,v in p['stage_statuses'].items() if k!='identity')
assert r['accepted_products']==0 and not r['deliverables_complete']
checks.append('Every selected/alternate identity has first-party evidence; no execution, adoption, or completion inflation')
for e in ev:
    source=load(ROOT/e['record_path'])
    if e['capture_path']:
        assert hashlib.sha256((ROOT/e['capture_path']).read_bytes()).hexdigest()==e['capture_sha256']
    for q in e['excerpts']:
        loc=q['locator']
        if loc=='title': value=source['title']
        elif loc.startswith('metadata['): value=source['metadata'][int(re.search(r'\[(\d+)\]',loc).group(1))]['value']
        else:
            start,end=map(int,re.search(r'(\d+):(\d+)',loc).groups());value=source['text'][start:end]
        assert value==q['excerpt'],(e['evidence_id'],loc)
checks.append('All captured-body hashes and every indexed excerpt/locator match their source record')
assert r['unresolved_leads'][0]['supplied_name']=='norvjx ai'
assert r['unresolved_leads'][0]['identity_status']=='unresolved'
assert len(r['unresolved_leads'][0]['search_evidence_ids'])==5
checks.append('Ambiguous name remains unresolved with five search-response records, not silently substituted')
ended=datetime.datetime.now(datetime.timezone.utc).isoformat()
receipt={'schema_version':1,'task_id':'2.a','started_at_utc':started,'ended_at_utc':ended,'elapsed_seconds':round(time.monotonic()-t0,6),'command':command,'working_directory':str(pathlib.Path.cwd()),'exit_status':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'checks':checks,'status':'passed','network_requests':0,'model_inference_calls':0,'scope':'Offline discovery artifacts only, not a product test or campaign acceptance.'}
(D/'validation.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'status':'passed','checks':len(checks),'selected':100,'alternates':25,'receipt':'research/ai-saas-100/discovery/validation.json'},indent=2))
