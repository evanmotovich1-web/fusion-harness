"""Offline structural validation. This is not independent acceptance or fact checking."""
import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

STAGES = ('identity', 'research', 'implementation', 'execution', 'evaluation', 'review')
STATES = {'not_started', 'in_progress', 'passed', 'failed', 'blocked'}
TOPICS = ('pricing', 'buyer', 'alternatives', 'adoption', 'distribution', 'integrations',
          'proprietary_access', 'switching_costs', 'operating_economics')
CLASSIFICATIONS = {'vendor_claim', 'independent_report', 'direct_observation',
                   'estimate', 'inference', 'unknown'}
FIELDS = {
    'identity': 'id name canonical_url category identity_status identity_evidence_ids aliases',
    'selection': 'candidate_id selection_position eligibility_evidence_ids pilot replacement_reference',
    'workflow': 'target_user job inputs outputs success_criteria included_behavior excluded_behavior external_dependencies',
    'tests': 'specification_path sha256 fixed_at acceptance_criteria baseline_specification',
    'implementation': 'source_path sha256 setup_instructions coverage missing_capabilities dependency_license_notes kind requires_inference',
    'assessment': 'stage_statuses receipt_paths technical_uncertainty commercial_uncertainty verdict_path review',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fields(obj, names):
    require(isinstance(obj, dict), 'expected object')
    for name in names.split() if isinstance(names, str) else names:
        require(name in obj, 'missing field: ' + name)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def timestamp(value):
    require(text(value), 'timestamp required')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('invalid timestamp: ' + value) from None
    require(parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0,
            'timestamp must be UTC')
    require(parsed <= datetime.now(timezone.utc), 'future timestamp')
    return parsed


def case_id(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{3}', value)
            and 1 <= int(value) <= 100, 'case ID must be 001..100')


def unique(records, key):
    require(isinstance(records, list), 'expected array')
    values = []
    for row in records:
        fields(row, [key])
        require(text(row[key]), key + ' must be nonempty')
        values.append(row[key])
    require(len(values) == len(set(values)), 'duplicate ' + key)
    return set(values)


def refs(values, known):
    require(isinstance(values, list), 'references must be an array')
    require(all(isinstance(v, str) and v in known for v in values), 'broken evidence/claim reference')


def local(root, relative):
    require(text(relative) and not Path(relative).is_absolute(), 'relative artifact path required')
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), 'artifact escapes campaign root')
    require(path.is_file(), 'missing artifact: ' + relative)
    return path


def artifact(root, reference):
    fields(reference, 'path sha256')
    require(isinstance(reference['sha256'], str)
            and re.fullmatch('[0-9a-f]{64}', reference['sha256']), 'invalid SHA256')
    path = local(root, reference['path'])
    require(hashlib.sha256(path.read_bytes()).hexdigest() == reference['sha256'],
            'artifact hash mismatch: ' + reference['path'])


def load(path):
    return json.loads(path.read_text())


def evidence(data, root):
    fields(data, 'schema_version sources')
    require(data['schema_version'] == 1, 'unsupported evidence schema')
    unique(data['sources'], 'evidence_id')
    usable = set()
    for row in data['sources']:
        fields(row, 'publisher retrieved_at published_at source_type access_method scope_limitations')
        timestamp(row['retrieved_at'])
        require(text(row.get('source_url')) or text(row.get('artifact_path')), 'evidence source missing')
        require(row.get('excerpts') or row.get('observation') or row.get('error') or row.get('capture_path'),
                'evidence has no content, capture, or failure')
        if (row.get('excerpts') or row.get('observation')) and not row.get('error'):
            usable.add(row['evidence_id'])
        if row.get('capture_path'):
            artifact(root, {'path': row['capture_path'], 'sha256': row.get('capture_sha256')})
    return usable


def metric(value):
    fields(value, 'value unit classification category assumptions unknown_reason')
    require(value['classification'] in {'measured', 'estimated', 'unknown'}, 'invalid metric classification')
    require(text(value['unit']) and text(value['category']), 'metric units/category required')
    if value['classification'] == 'unknown':
        require(value['value'] is None and text(value['unknown_reason']), 'unknown metric needs null and reason')
    else:
        number = value['value']
        require(type(number) in (int, float) and math.isfinite(number) and number >= 0, 'invalid metric value')
        if value['classification'] == 'estimated':
            require(bool(value['assumptions']), 'estimate needs assumptions')
    categories = {'billed_amount': 'measured', 'usage_derived_estimate': 'estimated',
                  'allocated_subscription_cost': 'estimated', 'local_resource_estimate': 'estimated',
                  'unknown': 'unknown'}
    if value['unit'] == 'USD':
        require(value['category'] in categories, 'invalid cost category')
        require(categories[value['category']] == value['classification'], 'cost classification mismatch')


def stages(value):
    fields(value, STAGES)
    for stage in STAGES:
        require(value[stage] in STATES, 'invalid required stage status')
    for i, stage in enumerate(STAGES):
        if value[stage] == 'passed':
            require(all(value[s] == 'passed' for s in STAGES[:i]), 'stage passed before prerequisite')


def receipt(data, root):
    fields(data, 'schema_version run_id case_id status system started_at ended_at command cwd implementation '
           'fixtures input_bundle outputs runtime model configuration baseline_id exit_status test_results '
           'quality latency usage costs errors retries timeouts missing_capabilities redactions human_interventions '
           'execution_kind inference_executed')
    require(data['schema_version'] == 1, 'unsupported receipt schema')
    case_id(data['case_id'])
    require(text(data['run_id']), 'run_id required')
    require(data['system'] in {'B1', 'B2', 'B3'}, 'invalid system')
    require(data['status'] in {'not_started', 'completed', 'failed', 'blocked'}, 'invalid receipt status')
    require(data['execution_kind'] in {'real', 'mock', 'stub', 'unknown'}, 'invalid execution kind')
    require(type(data['inference_executed']) is bool, 'inference flag must be boolean')
    for name in ('outputs', 'test_results', 'quality', 'costs', 'errors', 'retries', 'timeouts',
                 'missing_capabilities', 'redactions', 'human_interventions'):
        require(isinstance(data[name], list), name + ' must be an array')
    fields(data['model'], 'provider requested_id resolved_version unknown_reason')
    require(data['model']['requested_id'] is not None or text(data['model']['unknown_reason']), 'unknown model needs reason')
    for m in [data['latency'], *data['quality'], *data['costs']]:
        metric(m)
    require(bool(data['costs']), 'cost classification required, including unknown')
    if data['status'] in {'completed', 'failed'}:
        require(timestamp(data['ended_at']) >= timestamp(data['started_at']), 'reversed run timestamps')
        require(isinstance(data['command'], list) and data['command'] and all(text(x) for x in data['command']), 'argv required')
        require(text(data['cwd']) and bool(data['runtime']) and bool(data['configuration']), 'execution configuration missing')
        require(type(data['exit_status']) is int, 'exit status required')
        for name in ('implementation', 'fixtures', 'input_bundle'):
            artifact(root, data[name])
        for output in data['outputs']:
            artifact(root, output)
        require(bool(data['outputs']) or bool(data['errors']), 'raw output or error required')
        if data['status'] == 'completed':
            require(data['exit_status'] == 0, 'completed invocation has nonzero exit')
    else:
        require(data['started_at'] is None and data['ended_at'] is None and data['exit_status'] is None,
                'unexecuted receipt cannot claim execution')
        require(not data['inference_executed'], 'unexecuted receipt cannot claim inference')
        if data['status'] == 'blocked':
            require(bool(data['missing_capabilities']) or bool(data['errors']), 'blocked receipt needs reason')
    for result in data['test_results']:
        fields(result, 'test_id outcome')
        require(result['outcome'] in {'passed', 'failed', 'blocked'}, 'invalid test outcome')
    return data


def dossier(data, known, root):
    fields(data, ['schema_version', 'record_status', 'research', 'claims', *FIELDS])
    require(data['schema_version'] == 1, 'unsupported dossier schema')
    for section, names in FIELDS.items():
        fields(data[section], names)
    ident = data['identity']
    case_id(ident['id'])
    require(ident['identity_status'] in {'verified', 'unknown', 'blocked'}, 'invalid identity status')
    refs(ident['identity_evidence_ids'], known)
    refs(data['selection']['eligibility_evidence_ids'], known)
    claim_ids = unique(data['claims'], 'claim_id')
    for claim in data['claims']:
        fields(claim, 'statement classification evidence_ids scope uncertainty conflicting_claim_ids')
        require(claim['classification'] in CLASSIFICATIONS, 'invalid claim classification')
        refs(claim['evidence_ids'], known)
        refs(claim['conflicting_claim_ids'], claim_ids)
        if claim['classification'] in {'vendor_claim', 'independent_report', 'direct_observation'}:
            require(bool(claim['evidence_ids']), 'factual claim needs evidence')
        if claim['classification'] == 'estimate':
            fields(claim, 'assumptions unit')
            require(bool(claim['assumptions']) and text(claim['unit']), 'estimate assumptions required')
    fields(data['research'], TOPICS)
    for topic in TOPICS:
        finding = data['research'][topic]
        fields(finding, 'claim_ids value unknown_reason')
        refs(finding['claim_ids'], claim_ids)
        require(bool(finding['claim_ids']) or (finding['value'] is None and text(finding['unknown_reason'])),
                'research needs claim references or explicit unknown')
    assessment = data['assessment']
    stages(assessment['stage_statuses'])
    state = assessment['stage_statuses']
    labels = {'researched': 'research', 'implemented': 'implementation', 'tested': 'execution'}
    require(data['record_status'] in {*labels, 'blocked', 'unknown'}, 'invalid record_status')
    if data['record_status'] in labels:
        require(state[labels[data['record_status']]] == 'passed', 'milestone not passed')
    if data['record_status'] == 'blocked':
        require('blocked' in state.values(), 'blocked label needs blocked stage')
    if state['identity'] == 'passed':
        require(ident['identity_status'] == 'verified' and bool(ident['identity_evidence_ids']), 'identity not verified')
    if state['implementation'] == 'passed':
        impl = data['implementation']
        require(impl['kind'] == 'independent' and text(impl['setup_instructions']), 'stub/mock is not implementation')
        require(type(impl['requires_inference']) is bool, 'requires_inference must be explicit boolean')
        artifact(root, {'path': impl['source_path'], 'sha256': impl['sha256']})
    runs = []
    require(isinstance(assessment['receipt_paths'], list), 'receipt_paths must be array')
    for path in assessment['receipt_paths']:
        run = receipt(load(local(root, path)), root)
        require(run['case_id'] == ident['id'], 'receipt case mismatch')
        runs.append(run)
    unique(runs, 'run_id')
    if state['execution'] == 'passed':
        tests = data['tests']
        artifact(root, {'path': tests['specification_path'], 'sha256': tests['sha256']})
        fixed = timestamp(tests['fixed_at'])
        require(bool(tests['acceptance_criteria']) and bool(tests['baseline_specification']), 'test criteria and baseline required')
        successful = [r for r in runs if r['system'] == 'B2' and r['status'] == 'completed'
                      and r['execution_kind'] == 'real' and r['test_results']
                      and all(t['outcome'] == 'passed' for t in r['test_results'])]
        require(bool(successful), 'no real passing prototype execution')
        for run in successful:
            require(fixed <= timestamp(run['started_at']), 'tests fixed after execution')
            require(run['implementation']['sha256'] == data['implementation']['sha256'], 'stale implementation receipt')
            require(run['fixtures']['sha256'] == tests['sha256'], 'stale fixture receipt')
            if data['implementation']['requires_inference']:
                require(run['inference_executed'], 'central inference not executed')
    if state['evaluation'] == 'passed':
        baseline = [r for r in runs if r['system'] == 'B1' and r['status'] == 'completed' and r['execution_kind'] == 'real']
        require(bool(baseline), 'baseline not executed')
        prototypes = [r for r in runs if r['system'] == 'B2' and r['status'] == 'completed' and r['execution_kind'] == 'real']
        require({r['input_bundle']['sha256'] for r in prototypes} <= {r['input_bundle']['sha256'] for r in baseline}, 'baseline inputs differ')
        verdict = load(local(root, assessment['verdict_path']))
        fields(verdict, 'recommendation thesis technical_assessment commercial_assessment supporting_claim_ids '
               'counterevidence_claim_ids uncertainties next_falsification_test reviewer reviewed_at')
        require(verdict['recommendation'] in {'pursue', 'reject', 'insufficient_evidence'}, 'invalid verdict')
        refs(verdict['supporting_claim_ids'], claim_ids)
        refs(verdict['counterevidence_claim_ids'], claim_ids)
        timestamp(verdict['reviewed_at'])
    if state['review'] == 'passed':
        review = assessment['review']
        fields(review, 'reviewer independent accepted unresolved_material_objections artifact')
        require(text(review['reviewer']) and review['independent'] is True and review['accepted'] is True
                and review['unresolved_material_objections'] == [], 'review not accepted')
        artifact(root, review['artifact'])
    return all(state[s] == 'passed' for s in STAGES)


def active_seconds(intervals, root):
    require(isinstance(intervals, list), 'active intervals must be an array')
    spans = []
    for interval in intervals:
        fields(interval, 'started_at ended_at evidence')
        start, end = timestamp(interval['started_at']), timestamp(interval['ended_at'])
        require(end >= start, 'reversed activity interval')
        artifact(root, interval['evidence'])
        spans.append((start, end))
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return sum((end - start).total_seconds() for start, end in merged)


def registry(data, known, root):
    fields(data, 'schema_version products accepted_products deliverables_complete')
    require(data['schema_version'] == 1, 'unsupported registry schema')
    unique(data['products'], 'id')
    hosts = set()
    accepted = 0
    for row in data['products']:
        fields(row, 'id name canonical_url stage_statuses identity_evidence_ids case_path')
        case_id(row['id'])
        host = urlsplit(row['canonical_url']).hostname
        require(host is not None, 'invalid canonical URL')
        host = host.lower().removeprefix('www.')
        require(host not in hosts, 'duplicate canonical identity')
        hosts.add(host)
        refs(row['identity_evidence_ids'], known)
        stages(row['stage_statuses'])
        if any(row['stage_statuses'][s] == 'passed' for s in STAGES[1:]):
            case = load(local(root, row['case_path'].rstrip('/') + '/dossier.json'))
            require(case['identity']['id'] == row['id'] and case['identity']['canonical_url'] == row['canonical_url'], 'registry/dossier identity mismatch')
            require(case['assessment']['stage_statuses'] == row['stage_statuses'], 'registry/dossier stages differ')
            accepted += int(dossier(case, known, root))
    require(type(data['accepted_products']) is int and data['accepted_products'] == accepted, 'incorrect accepted count')
    require(data['deliverables_complete'] is (accepted == 100), 'incorrect completion flag')
    if any(k in data for k in ('duration_fulfilled', 'request_complete', 'observed_active_campaign_seconds')):
        fields(data, 'active_intervals observed_active_campaign_seconds duration_fulfilled request_complete')
        observed = active_seconds(data['active_intervals'], root)
        require(data['observed_active_campaign_seconds'] == observed, 'unsupported active duration')
        require(data['duration_fulfilled'] is (observed >= 86400), 'unsupported duration claim')
        require(data['request_complete'] is (accepted == 100 and observed >= 86400), 'incorrect request completion')
    return {'selected_products': len(data['products']), 'accepted_products': accepted, 'deliverables_complete': accepted == 100}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=['registry', 'evidence', 'dossier', 'receipt'])
    parser.add_argument('path', type=Path)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--evidence', type=Path, action='append', default=[])
    args = parser.parse_args()
    try:
        known = set()
        for path in args.evidence:
            ids = evidence(load(path), args.root)
            require(not known.intersection(ids), 'duplicate evidence IDs across indexes')
            known.update(ids)
        obj = load(args.path)
        if args.kind in {'registry', 'dossier'}:
            result = globals()[args.kind](obj, known, args.root)
        else:
            result = globals()[args.kind](obj, args.root)
        print(json.dumps({'valid': True, 'kind': args.kind, 'counts': result if args.kind == 'registry' else None}))
    except (ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
        print(json.dumps({'valid': False, 'error': str(exc)}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
