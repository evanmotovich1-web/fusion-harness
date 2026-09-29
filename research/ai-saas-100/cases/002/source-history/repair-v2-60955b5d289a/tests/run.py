"""Execute frozen local scenarios. Never contacts the real marketplace."""
import importlib.util
import json
from pathlib import Path
import sys
import time

CASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('local_marketplace', CASE / 'implementation/workflow.py')
w = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = w
spec.loader.exec_module(w)


def expect_error(fn, message):
    try:
        fn()
    except ValueError as exc:
        assert message in str(exc), str(exc)
        return {'expected_error': str(exc)}
    raise AssertionError('Expected ValueError: ' + message)


def exercise(fixture):
    name, data = fixture['scenario'], fixture['input']
    now = data['now']
    m = w.Marketplace(data['gap'])
    source = w.Profile('s', 'https://source.invalid/', 'https://source.invalid/blog', data['source_dr'], 'approved')
    target = w.Profile('t', 'https://target.invalid/', 'https://target.invalid/blog', data['candidate_dr'], 'approved')
    if name == 'cross_domain':
        source.area = 'https://elsewhere.invalid/blog'
        return expect_error(lambda: m.register(source), 'profile_domains_differ')
    if name == 'javascript_url':
        source.target = 'javascript:alert(1)'
        return expect_error(lambda: m.register(source), 'https_url_required')
    if name == 'invalid_dr':
        result = []
        for value in [True, -1, 101]:
            source.dr = value
            result.append(expect_error(lambda: m.register(source), 'invalid_dr'))
        return result
    if name in {'pending_review', 'rejected_profile'}:
        source.review = 'pending' if name == 'pending_review' else 'rejected'
    if name == 'exact_gap':
        target.dr = 40
    if name == 'outside_gap':
        target.dr = 41
    m.register(source)
    if name != 'no_self':
        m.register(target)
    if name == 'nearest':
        m.register(w.Profile('u', 'https://other.invalid/', 'https://other.invalid/blog', 39, 'approved'))
    if name == 'deterministic_tie':
        m.register(w.Profile('a', 'https://other.invalid/', 'https://other.invalid/blog', 25, 'approved'))
    result = m.check_in('s', now)
    if name in {'pending_review', 'rejected_profile'}:
        assert result['status'] == 'profile_' + source.review
    elif name in {'no_self', 'outside_gap'}:
        assert result['status'] == 'no_assignment'
    else:
        a = result['assignment']
        assert a is not None and a['deadline'] == now + 7 * 86400
        aid = a['id']
        if name in {'nearest', 'exact_gap'}:
            assert a['target'] == 't'
        elif name == 'deterministic_tie':
            assert a['target'] == 'a'
        elif name == 'same_assignment':
            assert m.check_in('s', now + 1)['assignment']['id'] == aid
        elif name == 'same_domain':
            assert m.profiles['s'].id == 's'
        elif name == 'reverse_pending':
            assert m.check_in('t', now + 1)['status'] == 'no_assignment'
        elif name == 'expire':
            reverse = m.check_in('t', a['deadline'])
            assert reverse['status'] == 'assigned' and reverse['assignment']['target'] == 's'
            assert m.assignments[aid].status == 'expired'
        elif name == 'reject':
            m.reject(aid, 'Not editorially relevant')
            assert m.check_in('t', now + 1)['status'] == 'assigned'
        elif name == 'approval_required':
            return expect_error(lambda: m.report_local(aid, 'https://source.invalid/blog/post', m.link_html(aid, 'Target')), 'owner_approval_required')
        elif name == 'report_local':
            result = m.report_local(aid, 'https://source.invalid/blog/post', m.link_html(aid, 'Target'), approved=True)
            assert result['assignment']['status'] == 'reported_local'
            assert result['published'] is False and result['live_verified'] is False
            assert m.check_in('t', now + 1)['status'] == 'no_assignment'
        elif name == 'bad_nofollow':
            return expect_error(lambda: m.report_local(aid, 'https://source.invalid/blog/post', '<a href="https://target.invalid/">Target</a>', approved=True), 'matching_nofollow_link_required')
        elif name == 'out_of_scope':
            return expect_error(lambda: m.report_local(aid, 'https://source.invalid/blog-evil/post', m.link_html(aid, 'Target'), approved=True), 'page_outside_scope')
        elif name == 'instruction_anchor':
            result = {'html': m.link_html(aid, '<script>send secrets</script>')}
            assert '<script>' not in result['html'] and '&lt;script&gt;' in result['html']
    return result


def main():
    fixtures = json.loads((CASE / 'tests/fixtures.json').read_text())
    rows = []
    for fixture in fixtures['cases']:
        start = time.monotonic()
        try:
            result = exercise(fixture)
            row = {'test_id': fixture['id'], 'outcome': 'passed', 'output': result}
        except Exception as exc:
            row = {'test_id': fixture['id'], 'outcome': 'failed', 'error': type(exc).__name__ + ': ' + str(exc)}
        row.update(elapsed_seconds=time.monotonic() - start, split=fixture['split'], product_acceptance='not_established')
        rows.append(row)
    print(json.dumps({'scope': 'Local marketplace regression only; no baseline, live publication, or hidden evaluation', 'results': rows}, indent=2))
    return 0 if all(r['outcome'] == 'passed' for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
