"""Bounded public-source retrieval. Run explicitly per source, no background work."""
import sys, json, hashlib, datetime, urllib.request, urllib.error
from pathlib import Path
from html.parser import HTMLParser
ROOT = Path(__file__).resolve().parent
class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style'): self.skip += 1
        if tag in ('p','div','br','li','h1','h2','h3','h4','tr','section','article'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
        if tag in ('p','div','li','h1','h2','h3','h4','tr','section','article'): self.parts.append('\n')
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)
name,url=sys.argv[1:3]
record={'id':name,'requested_url':url,'accessed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
try:
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (public-document research)'})
    with urllib.request.urlopen(req,timeout=14) as r:
        record.update(status=r.status,final_url=r.url,headers={k:v for k,v in r.headers.items() if k.lower() not in ('set-cookie', 'authorization')})
        data=r.read(8*1024*1024+1)
    if len(data)>8*1024*1024: raise ValueError('8 MiB source limit exceeded; not saved')
    suffix='.pdf' if data.startswith(b'%PDF') else '.html'
    path=ROOT/(name+suffix); path.write_bytes(data)
    record.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),file=path.name)
    if suffix=='.html':
        p=Text(); p.feed(data.decode('utf-8','replace'))
        text='\n'.join(x.strip() for x in ''.join(p.parts).splitlines() if x.strip())+'\n'
        (ROOT/(name+'.txt')).write_text(text)
except Exception as e:
    record['error']=str(e)
(ROOT/(name+'.json')).write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
