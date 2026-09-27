"""Support corpus selection, citation auditing, and ticket drafts. No answer model."""
from copy import deepcopy
from datetime import date
import json
import re
import sys


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def text(value, reason):
    require(isinstance(value, str) and bool(value.strip()) and len(value) <= 20000, reason)
    return value


def day(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value), 'invalid_date')
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError('invalid_date') from exc


def prepare(request):
    require(isinstance(request, dict), 'invalid_request')
    require(not {'input_path', 'output_path'} & set(request), 'paths_not_supported')
    require(request.get('execute_actions', False) is False and 'requested_external_action' not in request,
            'external_execution_not_authorized')
    question = text(request.get('question'), 'invalid_question')
    as_of = day(request.get('as_of'))
    sources = request.get('sources')
    require(isinstance(sources, list) and len(sources) <= 200, 'invalid_sources')
    additional_sources = request.get('additional_sources', [])
    require(isinstance(additional_sources, list) and len(additional_sources) <= 200,
            'invalid_additional_sources')
    for source in additional_sources:
        require(isinstance(source, dict), 'invalid_additional_sources')
        text(source.get('id'), 'invalid_additional_sources')
        text(source.get('text'), 'invalid_additional_sources')
    actions = request.get('allowed_actions')
    require(isinstance(actions, list) and len(actions) <= 20, 'invalid_allowed_actions')
    for action in actions:
        text(action, 'invalid_allowed_actions')
    require(len(actions) == len(set(actions)), 'invalid_allowed_actions')
    index, dates = {}, {}
    for source in sources:
        require(isinstance(source, dict), 'invalid_source')
        identifier = text(source.get('id'), 'invalid_source_id')
        require(identifier not in index, 'duplicate_source_id')
        text(source.get('text'), 'invalid_source_text')
        dates[identifier] = day(source.get('effective'))
        require(type(source.get('approved', True)) is bool, 'invalid_source_approval')
        if source.get('superseded_by') is not None:
            text(source['superseded_by'], 'invalid_supersession')
        index[identifier] = source
    for identifier in index:
        seen, cursor = set(), identifier
        while cursor in index:
            require(cursor not in seen, 'cyclic_supersession')
            seen.add(cursor)
            successor = index[cursor].get('superseded_by')
            if successor is None:
                break
            if successor in index:
                require(dates[successor] >= dates[cursor], 'backdated_successor')
            cursor = successor
    eligible, excluded = [], []
    for identifier, source in index.items():
        successor = source.get('superseded_by')
        reason = None
        if not source.get('approved', True):
            reason = 'not_approved'
        elif dates[identifier] > as_of:
            reason = 'not_yet_effective'
        elif successor is not None and successor not in index:
            reason = 'unresolved_supersession'
        elif successor is not None and dates[successor] <= as_of and index[successor].get('approved', True):
            reason = 'superseded'
        if reason:
            excluded.append({'source_id': identifier, 'reason': reason})
        else:
            eligible.append(deepcopy(source))
    return {'status': 'component_complete', 'question': question, 'eligible_sources': eligible,
            'excluded_sources': excluded,
            'unresolved_additional_sources': deepcopy(additional_sources),
            'answer': None, 'answer_status': 'not_generated',
            'inference_executed': False, 'external_calls': 0, 'product_acceptance': False,
            'limitations': ['Temporal selection is not relevance ranking or semantic contradiction detection',
                            'No generated answer or inferred eligibility decision',
                            'No Zendesk execution or model baseline']}


def audit_citations(request, citations):
    prepared = prepare(request)
    index = {source['id']: source for source in prepared['eligible_sources']}
    require(isinstance(citations, list) and len(citations) <= 100, 'invalid_citations')
    verified = []
    for citation in citations:
        require(isinstance(citation, dict), 'invalid_citation')
        identifier = text(citation.get('source_id'), 'invalid_citation_source')
        require(identifier in index, 'citation_source_not_eligible')
        start, end = citation.get('start'), citation.get('end')
        require(type(start) is int and type(end) is int and 0 <= start < end <= len(index[identifier]['text']),
                'invalid_citation_span')
        quote = text(citation.get('quote'), 'invalid_citation_quote')
        require(index[identifier]['text'][start:end] == quote, 'citation_quote_mismatch')
        verified.append(deepcopy(citation))
    return {'verified_spans': verified, 'semantic_entailment': 'not_evaluated',
            'inference_executed': False, 'external_calls': 0}


def draft_ticket(request, reason):
    prepared = prepare(request)
    text(reason, 'invalid_escalation_reason')
    require('draft_ticket' in request['allowed_actions'], 'ticket_draft_not_allowed')
    return {'type': 'local_ticket_preview', 'question': request['question'], 'reason': reason,
            'source_ids': [source['id'] for source in prepared['eligible_sources']],
            'unresolved_source_count': len(prepared['unresolved_additional_sources']),
            'sent': False, 'external_ticket_id': None, 'inference_executed': False,
            'external_calls': 0, 'reason_provenance': 'caller_supplied_not_model_inferred'}


def run(request):
    try:
        return prepare(request)
    except ValueError as exc:
        return {'status': 'invalid_input', 'error': str(exc), 'inference_executed': False,
                'external_calls': 0, 'product_acceptance': False}


if __name__ == '__main__':
    output = run(json.load(sys.stdin))
    print(json.dumps(output, indent=2))
    raise SystemExit(2 if output['status'] == 'invalid_input' else 0)
