"""R9 additional-source type checks. No answer generation or external effects."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import time

CASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CASE / 'implementation'))
import support_evidence as workflow

ACTIVE = False
ATTEMPTS = []


def audit(event, args):
    if ACTIVE and (event == 'open' or event.startswith(('socket.', 'subprocess.', 'os.system', 'os.exec', 'os.spawn'))):
        ATTEMPTS.append(event)
        raise AssertionError('I/O during pure support component: ' + event)


def check(condition, reason):
    if not condition:
        raise AssertionError(reason)


def rejects(function):
    try:
        function()
    except ValueError as exc:
        check(str(exc) == 'invalid_additional_sources', 'Wrong rejection: ' + str(exc))
        return
    except Exception as exc:
        raise AssertionError('Wrong exception type: ' + type(exc).__name__) from exc
    raise AssertionError('Expected invalid_additional_sources')


def main():
    global ACTIVE
    fixtures = json.loads(Path(__file__).with_name('fixtures.json').read_text())['cases']
    rows = []
    sys.addaudithook(audit)
    for fixture in fixtures:
        request = deepcopy(fixture['request'])
        before = deepcopy(request)
        expected = fixture['expected']
        row = {'test_id': fixture['id'], 'outcome': 'failed', 'product_acceptance': False}
        ATTEMPTS.clear()
        started = time.monotonic()
        try:
            ACTIVE = True
            if 'error' in expected:
                output = workflow.run(request)
                check(output['status'] == 'invalid_input', 'Malformed additional_sources was not rejected')
                check(output['error'] == 'invalid_additional_sources', 'Wrong structured rejection')
                check(output['inference_executed'] is False and output['external_calls'] == 0,
                      'Malformed input lacks execution accounting')
                rejects(lambda: workflow.prepare(request))
                rejects(lambda: workflow.audit_citations(request, []))
                rejects(lambda: workflow.draft_ticket(request, 'Human review'))
            else:
                unresolved = expected['unresolved_additional_sources']
                prepared = workflow.prepare(request)
                output = workflow.run(request)
                audited = workflow.audit_citations(request, [])
                ticket = workflow.draft_ticket(request, 'Human review')
                check(prepared['unresolved_additional_sources'] == unresolved,
                      'Prepared additional sources changed')
                check(output['unresolved_additional_sources'] == unresolved,
                      'Run additional sources changed')
                check(audited['verified_spans'] == [] and audited['semantic_entailment'] == 'not_evaluated',
                      'Citation audit changed scope')
                check(ticket['unresolved_source_count'] == len(unresolved) and ticket['sent'] is False,
                      'Ticket preview count or side-effect claim incorrect')
                if unresolved:
                    supplied = request['additional_sources']
                    check(prepared['unresolved_additional_sources'] is not supplied,
                          'Additional-source list was not deep-copied')
                    check(prepared['unresolved_additional_sources'][0] is not supplied[0],
                          'Additional-source record was not deep-copied')
            check(request == before, 'Input mutated')
            check(not ATTEMPTS, 'I/O attempted')
            row['outcome'] = 'passed'
        except Exception as exc:
            row['error'] = type(exc).__name__ + ': ' + str(exc)
        finally:
            ACTIVE = False
        row.update(elapsed_seconds=time.monotonic() - started,
                   input_unchanged=request == before, io_attempts=list(ATTEMPTS))
        rows.append(row)
    result = {
        'schema_version': 1,
        'case_id': '007',
        'version': 'support-evidence-v2',
        'results': rows,
        'scope': 'R9 additional-source type validation only; unresolved evidence remains passthrough.',
        'held_out': False,
        'inference_executed': False,
        'external_calls': 0,
        'product_acceptance': False,
    }
    print(json.dumps(result, indent=2))
    return 0 if all(row['outcome'] == 'passed' for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
