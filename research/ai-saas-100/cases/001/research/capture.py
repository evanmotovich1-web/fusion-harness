"""Bounded credential-free public-page capture for the three pilot dossiers."""
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import time
import urllib.request
from urllib.parse import urlsplit, urljoin

ROOT = Path(__file__).resolve().parents[3]
HOSTS = {'001': 'smodin.io', '002': 'getlinkbunny.com', '003': 'northlight.ai'}

class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []
        self.links = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style'):
            self.skip += 1
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.skip:
            self.skip -= 1
    def handle_data(self, text):
        if not self.skip and text.strip():
            self.parts.append(text.strip())


def capture(case, url):
    assert urlsplit(url).scheme == 'https' and urlsplit(url).hostname == HOSTS[case]
    started = datetime.now(timezone.utc).isoformat()
    tick = time.monotonic()
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    folder = ROOT / 'cases' / case / 'research'
    folder.mkdir(parents=True, exist_ok=True)
    record = {'url': url, 'retrieved_at': started, 'access_method': 'credential-free bounded urllib GET',
              'published_at': None, 'error': None, 'status': None, 'limit_bytes': 262144}
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'PublicResearch/1.0'})
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read(262145)
            record.update(status=response.status, final_url=response.url, truncated=len(raw) > 262144)
        parser = Text()
        parser.feed(raw[:262144].decode('utf-8', errors='replace'))
        content = '\n'.join(parser.parts) + '\n'
        target = folder / (key + '.txt')
        with target.open('x') as f:
            f.write(content)
        record.update(capture_path=str(target.relative_to(ROOT)), capture_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                      links=sorted(set(urljoin(url, x) for x in parser.links if not x.startswith(('javascript:', 'mailto:')))))
    except Exception as exc:
        record['error'] = type(exc).__name__ + ': ' + str(exc)
    record['ended_at'] = datetime.now(timezone.utc).isoformat()
    record['elapsed_seconds'] = time.monotonic() - tick
    with (folder / (key + '.json')).open('x') as f:
        json.dump(record, f, indent=2)
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('case', choices=HOSTS)
    parser.add_argument('urls', nargs='+')
    args = parser.parse_args()
    if len(args.urls) > 4:
        parser.error('At most four URLs per bounded invocation')
    for url in args.urls:
        capture(args.case, url)
