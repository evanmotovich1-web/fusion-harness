#!/usr/bin/env python3
"""Bounded credential-free public discovery capture. No inference or product tests."""
import concurrent.futures, datetime, hashlib, html.parser, json, pathlib, sys, time, urllib.request, urllib.parse
ROOT = pathlib.Path(__file__).resolve().parent
CAP = 262144
class Page(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(); self.skip = 0; self.text = []; self.meta = []; self.links = []; self.title = []; self.intitle = False
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style', 'noscript', 'svg'): self.skip += 1
        if tag == 'title': self.intitle = True
        if tag == 'meta' and (a.get('name') in ('description', 'application-name') or a.get('property') in ('og:title', 'og:description', 'og:site_name')):
            self.meta.append({'key': a.get('name') or a.get('property'), 'value': a.get('content', '')})
        if tag in ('a', 'link') and a.get('href'):
            self.links.append({'href': a['href'], 'rel': a.get('rel')})
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'svg') and self.skip: self.skip -= 1
        if tag == 'title': self.intitle = False
    def handle_data(self, data):
        if self.intitle: self.title.append(data)
        if not self.skip and data.strip(): self.text.append(' '.join(data.split()))
def capture(url):
    started = datetime.datetime.now(datetime.timezone.utc).isoformat(); t = time.monotonic()
    key = hashlib.sha256(url.encode()).hexdigest()[:20]
    rec = {'evidence_id': 'web-' + key, 'source_url': url, 'retrieved_at': started, 'published_at': None, 'publisher': None, 'access_method': 'credential-free Python urllib HTTPS GET', 'source_type': 'unclassified', 'scope_limitations': 'Bounded static HTML capture. Vendor claims not independently verified. No product execution.', 'requested_byte_limit': CAP}
    try:
        if urllib.parse.urlparse(url).scheme != 'https': raise ValueError('HTTPS required')
        req = urllib.request.Request(url, headers={'User-Agent': 'PublicProductResearch/1.0', 'Accept': 'text/html,application/json,text/plain;q=0.8'})
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read(CAP + 1); rec.update(status=r.status, final_url=r.url, content_type=r.headers.get('Content-Type'), capture_truncated=len(raw)>CAP)
            raw = raw[:CAP]
        capture_path = ROOT / 'captures' / (key + '.html'); capture_path.parent.mkdir(exist_ok=True)
        capture_path.write_bytes(raw)
        page = Page(); page.feed(raw.decode('utf-8', errors='replace'))
        rec.update(capture_path=str(capture_path.relative_to(ROOT.parent)), capture_sha256=hashlib.sha256(raw).hexdigest(), bytes_saved=len(raw), title=' '.join(page.title), metadata=page.meta, text='\n'.join(page.text), links=page.links)
    except Exception as e:
        rec.update(status='failed', error=type(e).__name__ + ': ' + str(e))
    rec['elapsed_seconds'] = round(time.monotonic()-t, 4)
    (ROOT / 'records').mkdir(exist_ok=True)
    (ROOT / 'records' / (key + '.json')).write_text(json.dumps(rec, indent=2, ensure_ascii=False)+'\n')
    return {'url': url, 'record': 'discovery/records/'+key+'.json', 'status': rec['status'], 'final_url': rec.get('final_url'), 'title': rec.get('title'), 'metadata': rec.get('metadata'), 'text_preview': rec.get('text', '')[:650], 'error': rec.get('error')}
if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for result in pool.map(capture, sys.argv[1:]): print(json.dumps(result, ensure_ascii=False))
