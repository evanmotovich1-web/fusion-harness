#!/usr/bin/env python3
"""Task 3.b public page capture. Writes only case IDs 004..035."""
import concurrent.futures, datetime, hashlib, json, pathlib, runpy, sys, time, urllib.request, urllib.parse
ROOT=pathlib.Path(__file__).resolve().parents[3]
Page=runpy.run_path(str(ROOT/'discovery/fetch_public.py'))['Page']
CAP=262144

def capture(row):
    cid,role,url=row
    assert 4<=int(cid)<=35 and urllib.parse.urlsplit(url).scheme=='https'
    out=ROOT/'cases'/cid/'research';(out/'records').mkdir(parents=True,exist_ok=True);(out/'captures').mkdir(exist_ok=True)
    key=hashlib.sha256(url.encode()).hexdigest()[:20]
    target=out/'records'/(key+'.json')
    assert not target.exists(),f'Refusing overwrite: {target}'
    t=time.monotonic()
    r={'evidence_id':f'r{cid}-{key}','source_url':url,'publisher':urllib.parse.urlsplit(url).hostname,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'published_at':None,'source_type':'first_party_public_page','access_method':'credential-free urllib HTTPS GET','research_role':role,'scope_limitations':'Bounded static HTML. Public vendor claims only, not execution or independently verified pricing/adoption. Some paths are public URL hypotheses and may be inaccessible or irrelevant.','requested_byte_limit':CAP}
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'PublicProductResearch/1.0','Accept':'text/html,text/plain;q=0.8'})
        with urllib.request.urlopen(req,timeout=8) as response:
            raw=response.read(CAP+1);r.update(status=response.status,final_url=response.url,content_type=response.headers.get('Content-Type'),capture_truncated=len(raw)>CAP);raw=raw[:CAP]
        dest=out/'captures'/(key+'.html');dest.write_bytes(raw)
        page=Page();page.feed(raw.decode('utf-8',errors='replace'))
        r.update(capture_path=str(dest.relative_to(ROOT)),capture_sha256=hashlib.sha256(raw).hexdigest(),bytes_saved=len(raw),title=' '.join(page.title),metadata=page.meta,text='\n'.join(page.text),links=page.links)
    except Exception as e:
        r.update(status='failed',error=type(e).__name__+': '+str(e))
    r['elapsed_seconds']=round(time.monotonic()-t,6)
    target.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    return {'id':cid,'role':role,'url':url,'status':r['status'],'title':r.get('title'),'description':next((m['value'] for m in r.get('metadata',[]) if m['key']=='description'),None),'error':r.get('error')}
if __name__=='__main__':
    start,stop=map(int,sys.argv[1:3])
    rows=[s.split('\t') for s in pathlib.Path(__file__).with_name('source-plan.tsv').read_text().splitlines() if start<=int(s.split('\t')[0])<=stop]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for result in pool.map(capture,rows):print(json.dumps(result,ensure_ascii=False))
