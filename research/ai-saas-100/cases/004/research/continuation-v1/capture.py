"""Bounded credential-free follow-up on five already identified official pages."""
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import signal
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[4]
SOURCES = [
    ('004', 'https://languagetool.org/premium', 'Previously unavailable pricing and plan limits'),
    ('005', 'https://www.frase.io/integrations', 'Publishing and integration scope beyond draft generation'),
    ('006', 'https://www.clay.com/pricing', 'Previously missing subscription amounts and credit semantics'),
    ('007', 'https://botsonic.com/integrations/zendesk', 'Actual advertised support escalation integration'),
    ('008', 'https://fireflies.ai/pricing', 'Unclear monthly versus annual price and transcription allowance'),
]
LIMIT = 1048576


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'noscript', 'svg'}:
            self.skip += 1
    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'noscript', 'svg'} and self.skip:
            self.skip -= 1
    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(' '.join(data.split()))


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        old, new = urllib.parse.urlsplit(request.full_url), urllib.parse.urlsplit(newurl)
        if new.scheme != 'https' or (new.hostname or '').removeprefix('www.') != (old.hostname or '').removeprefix('www.'):
            raise ValueError('Redirect outside approved public host')
        return super().redirect_request(request, fp, code, message, headers, newurl)


def timeout(_signal, _frame):
    raise TimeoutError('Eight-second total request deadline')


def main():
    opener = urllib.request.build_opener(SameHostRedirect())
    signal.signal(signal.SIGALRM, timeout)
    for cid, url, purpose in SOURCES:
        directory = ROOT / 'cases' / cid / 'research/continuation-v1'
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        prefix = directory / ('capture-' + stamp)
        record = {'schema_version': 1, 'case_id': cid, 'source_url': url, 'purpose': purpose,
                  'retrieved_at': datetime.now(timezone.utc).isoformat(),
                  'source_type': 'first_party_public_page', 'classification': 'vendor_claims_only',
                  'method': 'Credential-free bounded HTTPS GET', 'status': None, 'error': None,
                  'maximum_bytes': LIMIT, 'total_deadline_seconds': 8,
                  'limitations': 'Static vendor content only, not service execution, customer verification or checkout.'}
        tick = time.monotonic()
        try:
            signal.alarm(8)
            request = urllib.request.Request(url, headers={'User-Agent': 'CampaignResearch/1.0', 'Accept-Encoding': 'identity'})
            with opener.open(request, timeout=6) as response:
                raw = response.read(LIMIT + 1)
                record.update(status=response.status, final_url=response.url,
                              content_type=response.headers.get('Content-Type'))
            record['truncated'] = len(raw) > LIMIT
            raw = raw[:LIMIT]
            record['bytes_read'] = len(raw)
            html_path = prefix.with_suffix('.html')
            with html_path.open('xb') as f:
                f.write(raw)
            parser = Text()
            parser.feed(raw.decode('utf-8', errors='replace'))
            text = ('\n'.join(parser.parts) + '\n').encode()
            text_path = prefix.with_suffix('.txt')
            with text_path.open('xb') as f:
                f.write(text)
            record['captures'] = [{'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(data).hexdigest()}
                                  for path, data in [(html_path, raw), (text_path, text)]]
        except Exception as exc:
            record['error'] = type(exc).__name__ + ': ' + str(exc)
        finally:
            signal.alarm(0)
        record['elapsed_seconds'] = time.monotonic() - tick
        path = prefix.with_suffix('.json')
        with path.open('x') as f:
            json.dump(record, f, indent=2)
            f.write('\n')
        print(json.dumps({'case_id': cid, 'record': str(path.relative_to(ROOT)),
                          'status': record['status'], 'error': record['error'],
                          'truncated': record.get('truncated')}))


if __name__ == '__main__':
    main()
