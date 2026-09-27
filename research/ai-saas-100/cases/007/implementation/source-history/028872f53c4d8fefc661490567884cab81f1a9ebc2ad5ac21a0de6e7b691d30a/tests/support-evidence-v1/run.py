"""Temporal corpus, citation-span and ticket-preview checks, not answer evaluation."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import time

CASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CASE / 'implementation'))
import support_evidence as w
ACTIVE = False
ATTEMPTS = []


def audit(event, args):
    if ACTIVE and (event == 'open' or event.startswith(('socket.', 'subprocess.', 'os.system'))):
        ATTEMPTS.append(event)
        raise AssertionError('I/O during pure support component: ' + event)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def rejects(function, reason):
    try:
        function()
    except ValueError as exc:
        check(reason in str(exc), 'Wrong rejection: ' + str(exc))
        return
    raise AssertionError('Expected rejection: ' + reason)


def main():
    global ACTIVE
    component = json.loads(Path(__file__).with_name('fixtures.json').read_text())
    original = json.loads((CASE / 'tests/specification.json').read_text())
    jobs = [('component', f) for f in component['cases']] + [('original', f) for f in original['cases']]
    rows = []
    sys.addaudithook(audit)
    for kind, fixture in jobs:
        request = deepcopy(fixture['input'])
        before = deepcopy(request)
        identifier = fixture.get('id', fixture.get('test_id'))
        row = {'test_id': identifier, 'outcome': 'failed', 'product_acceptance': False}
        tick = time.monotonic()
        ATTEMPTS.clear()
        try:
            ACTIVE = True
            output = w.run(request)
            row['output'] = output
            expected = fixture['expected']
            rejection = kind == 'component' and 'error' in expected
            rejection = rejection or (kind == 'original' and fixture.get('scenario') in {
                'empty_input', 'wrong_type', 'unsafe_path', 'unauthorized_action'})
            if rejection:
                check(output['status'] == 'invalid_input', 'Expected typed rejection')
                if kind == 'component':
                    check(output['error'] == expected['error'], 'Wrong rejection reason')
            else:
                check(output['status'] == 'component_complete' and output['answer'] is None and
                      output['answer_status'] == 'not_generated', 'Generated answer fabricated')
                ids = [s['id'] for s in output['eligible_sources']]
                exclusions = {s['source_id']: s['reason'] for s in output['excluded_sources']}
                if kind == 'component':
                    check(ids == expected['eligible'] and exclusions == expected['excluded'], 'Wrong temporal filtering')
                    draft_allowed = expected['draft_allowed']
                    source_id, quote = expected.get('audit_source'), expected.get('quote')
                else:
                    check(ids == ['P1', 'P2'] and exclusions == {'P0': 'superseded'}, 'Superseded policy exposed')
                    draft_allowed = True
                    source_id, quote = 'P1', request['sources'][0]['text']
                check(output['unresolved_additional_sources'] == request.get('additional_sources', []), 'Additional evidence discarded')
                if source_id:
                    source = next(s for s in output['eligible_sources'] if s['id'] == source_id)
                    start = source['text'].index(quote)
                    citation = {'source_id': source_id, 'start': start, 'end': start + len(quote), 'quote': quote}
                    citation_before = deepcopy(citation)
                    audited = w.audit_citations(request, [citation])
                    check(audited['verified_spans'] == [citation] and audited['semantic_entailment'] == 'not_evaluated', 'False citation claim')
                    row['citation_audit'] = audited
                    check(citation == citation_before, 'Citation input mutated')
                    for changed, reason in [
                        (dict(citation, quote='fabricated'), 'citation_quote_mismatch'),
                        (dict(citation, start=True), 'invalid_citation_span'),
                        (dict(citation, end=len(source['text']) + 1), 'invalid_citation_span'),
                        (dict(citation, source_id='unknown'), 'citation_source_not_eligible'),
                    ]:
                        rejects(lambda: w.audit_citations(request, [changed]), reason)
                for excluded in exclusions:
                    rejects(lambda: w.audit_citations(request, [{'source_id': excluded, 'start': 0, 'end': 1, 'quote': 'x'}]),
                            'citation_source_not_eligible')
                if draft_allowed:
                    draft = w.draft_ticket(request, 'Human review requested, no generated answer available')
                    check(draft['sent'] is False and draft['external_ticket_id'] is None, 'Remote ticket claim')
                    check(draft['question'] == request['question'] and draft['source_ids'] == ids, 'Ticket context changed')
                    row['ticket_preview'] = draft
                else:
                    rejects(lambda: w.draft_ticket(request, 'Review required'), 'ticket_draft_not_allowed')
            check(output['inference_executed'] is False and output['external_calls'] == 0, 'False execution claim')
            check(request == before and not ATTEMPTS, 'Mutation or I/O')
            row['outcome'] = 'passed'
        except Exception as exc:
            row['error'] = type(exc).__name__ + ': ' + str(exc)
        finally:
            ACTIVE = False
        row.update(elapsed_seconds=time.monotonic() - tick, io_attempts=list(ATTEMPTS), input_unchanged=request == before)
        rows.append(row)
    print(json.dumps({'schema_version': 1, 'case_id': '007', 'results': rows,
                      'scope': '12 component cases plus component-only assertions over 20 historical inputs. No generated support answers.',
                      'held_out': False, 'inference_executed': False, 'product_acceptance': False}, indent=2))
    return 0 if all(r['outcome'] == 'passed' for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
