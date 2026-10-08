"""Local structured enrichment with provenance. No inference, provider, or network calls."""
from copy import deepcopy
from datetime import date
import json
import re
import sys


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def text(value, reason):
    require(isinstance(value, str) and bool(value.strip()) and len(value) <= 10000, reason)
    return value


def domain(value):
    value = text(value, 'invalid_domain').strip().lower().rstrip('.')
    require(len(value) <= 253 and '.' in value and all(
        re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part) for part in value.split('.')
    ), 'invalid_domain')
    return value


def date_value(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value), 'invalid_retrieved_at')
    try:
        return date.fromisoformat(value).toordinal()
    except ValueError as exc:
        raise ValueError('invalid_retrieved_at') from exc


def strings(values, reason, maximum=100):
    require(isinstance(values, list) and 0 < len(values) <= maximum, reason)
    for value in values:
        text(value, reason)
    require(len(values) == len(set(values)), reason)
    return values


def enrich(request):
    require(isinstance(request, dict), 'invalid_request')
    require(not {'input_path', 'output_path'} & set(request), 'paths_not_supported')
    require('requested_external_action' not in request, 'external_action_not_authorized')
    require(request.get('allow_external_lookup', False) is False, 'external_lookup_not_authorized')
    companies, sources = request.get('companies'), request.get('sources')
    require(isinstance(companies, list) and len(companies) <= 200, 'invalid_companies')
    require(isinstance(sources, list) and len(sources) <= 1000, 'invalid_sources')
    fields = strings(request.get('requested_fields'), 'invalid_requested_fields', 20)
    providers = strings(request.get('waterfall_order'), 'invalid_waterfall_order')
    ranking = {name: i for i, name in enumerate(providers)}
    company_ids, source_ids, prepared = set(), set(), []
    for company in companies:
        require(isinstance(company, dict), 'invalid_company')
        identifier = text(company.get('id'), 'invalid_company_id')
        require(identifier not in company_ids, 'duplicate_company_id')
        company_ids.add(identifier)
        text(company.get('name'), 'invalid_company_name')
        domain(company.get('domain'))
    for source in sources:
        require(isinstance(source, dict), 'invalid_source')
        identifier = text(source.get('id'), 'invalid_source_id')
        require(identifier not in source_ids, 'duplicate_source_id')
        source_ids.add(identifier)
        provider = text(source.get('provider'), 'invalid_provider')
        normalized = domain(source.get('domain'))
        timestamp = date_value(source.get('retrieved_at'))
        if source.get('employees') is not None:
            require(type(source['employees']) is int and source['employees'] >= 0, 'invalid_employees')
        if source.get('country') is not None:
            require(isinstance(source['country'], str) and re.fullmatch(r'[A-Z]{2}', source['country']), 'invalid_country')
        if source.get('contact_email') is not None:
            require(isinstance(source['contact_email'], str) and
                    re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', source['contact_email']), 'invalid_contact_email')
        for name in ['text', 'business_summary']:
            if name in source and source[name] is not None:
                text(source[name], 'invalid_' + name)
        prepared.append((source, normalized, timestamp, ranking.get(provider)))
    records, conflicts = [], []
    supported = {'employees', 'country', 'contact_email', 'business_summary'}
    for company in companies:
        matched = [(s, day, rank) for s, dom, day, rank in prepared
                   if dom == domain(company['domain']) and rank is not None]
        values, provenance, confidence, missing = {}, {}, {}, []
        chosen_ids = set()
        for field in fields:
            observations = [{'source_id': s['id'], 'provider': s['provider'],
                             'retrieved_at': s['retrieved_at'], 'value': deepcopy(s[field]),
                             'rank': rank, 'day': day}
                            for s, day, rank in matched if field in supported and s.get(field) is not None]
            observations.sort(key=lambda row: (row['rank'], -row['day'], row['source_id']))
            distinct = {json.dumps(row['value'], sort_keys=True) for row in observations}
            selected = []
            if observations:
                first = observations[0]
                top = [row for row in observations if row['rank'] == first['rank'] and row['day'] == first['day']]
                if len({json.dumps(row['value'], sort_keys=True) for row in top}) == 1:
                    selected = [row['source_id'] for row in top]
                    values[field] = deepcopy(first['value'])
                else:
                    values[field] = None
            else:
                values[field] = None
            provenance[field] = {'selected_source_ids': selected,
                                 'observations': [{k: v for k, v in row.items() if k not in {'rank', 'day'}}
                                                  for row in observations],
                                 'selection_rule': 'provider_order_then_latest_date; tied disagreement remains unknown'}
            chosen_ids.update(selected)
            if len(distinct) > 1:
                conflicts.append({'company_id': company['id'], 'field': field,
                                  'observations': deepcopy(provenance[field]['observations']),
                                  'selected_source_ids': selected})
            if values[field] is None:
                missing.append(field)
                confidence[field] = 'unknown'
            else:
                confidence[field] = 'conflicting_supplied_records' if len(distinct) > 1 else 'supplied_record_not_verified'
        records.append({'company': deepcopy(company), 'fields': values, 'source_ids': sorted(chosen_ids),
                        'confidence': confidence, 'missing_fields': missing, 'provenance': provenance,
                        'source_excerpts': [{'source_id': s['id'], 'text': s['text']} for s, _, _ in matched if s.get('text')]})
    return {'status': 'component_complete', 'records': records, 'conflicts': conflicts,
            'unresolved_additional_sources': deepcopy(request.get('additional_sources', [])),
            'unused_provider_source_ids': [s['id'] for s, _, _, rank in prepared if rank is None],
            'method': 'deterministic_structured_record_join', 'inference_executed': False,
            'external_calls': 0, 'product_acceptance': False,
            'limitations': ['No fuzzy identity resolution or external enrichment',
                            'No generated business summaries; source text retained only as verbatim excerpts',
                            'Confidence labels describe evidence, not calibrated probabilities',
                            'No generic-model baseline or independent hidden evaluation']}


def run(request):
    try:
        return enrich(request)
    except ValueError as exc:
        return {'status': 'invalid_input', 'error': str(exc), 'inference_executed': False,
                'external_calls': 0, 'product_acceptance': False}


if __name__ == '__main__':
    output = run(json.load(sys.stdin))
    print(json.dumps(output, indent=2))
    raise SystemExit(2 if output['status'] == 'invalid_input' else 0)
