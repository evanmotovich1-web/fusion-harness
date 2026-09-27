"""Serialize bounded pilot evidence and honest incomplete dossiers, without changing registry."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from receipt import receipt_template

SNIPPETS = {
 '001': {
  '043d8a5343b3ace8': ['Smodin offers powerful tools for writers, students, and professionals.', 'Our rewriter uses advanced AI to produce natural, unique text while preserving your original meaning.', 'Select Strength (1–4). Default is 3 for a balanced rewrite.', 'You can try the rewriter within a character limit.', 'I used to rewrite in ChatGPT, clean it up in QuillBot, then check for plagiarism separately.', 'Trusted by 1 Million+ users'],
  '0e3e543d064fd75c': ['Starter', 'Premium', 'AI Models', 'API Access', 'Trusted by 1 Million+ users worldwide'],
  '8ed9b05793c0c98b': ['Simple RESTful API with comprehensive documentation and code examples for quick integration.', 'Advanced AI models trained specifically for content rewriting, plagiarism detection, and AI content removal.', 'Scan against billions of web pages and academic sources.'],
  'a2e0663d6daec6d0': ['Powered by Proprietary AI Models']
 },
 '002': {
  'c1788014a4b4c0d6': ['FOR SITE OWNERS USING CODING AGENTS', 'Your agent receives a link request with a target URL, requested anchor, Domain Rating, and seven-day deadline.', 'LinkBunny is new, with a small founding group of manually reviewed sites.', 'LinkBunny matches within a Domain Rating range and prefers closer scores. You decide whether a request fits.'],
  '79e13c11d1509761': ['$20', '/ month', 'Up to 10 sites. No per-backlink fees', 'Manual profile review before marketplace matching', 'One account, multiple profiles (sites).'],
  '79e6dafbfc3b5a89': ['LinkBunny is built by Hwee-Boon Yar, a solo indie developer who has been writing and delivering software for 30 years.'],
  '5aa93945dcc9ca51': ['LinkBunny matches candidates within a bounded Domain Rating gap, including the limit.', 'LinkBunny does not assign the reverse pair while the first is pending or after it is reported.', 'Expiry or rejection releases reverse matching without removing valid late or reconsidered reporting rights.', 'Your client starts the process locally, and it calls LinkBunny over HTTPS with your token.', 'check_in']
 },
 '003': {
  'fc836c603944acbe': ['Your GTM AI Desktop', 'Loved by teams scaling smarter, not bigger', 'It acts as you, from your own device.'],
  'b07c5236fed19199': ['100 AI requests / month', '80', 'Unlimited AI requests', 'Enterprise', 'Custom', 'Most tasks use 10-20 credits.', "Credits reset each billing cycle and don't roll over.", 'free for 7 days, no credit card required.'],
  'b141c7f790990b2a': ['Stop bouncing between 10 tabs.', 'Send LinkedIn messages, update your CRM, and enrich leads — all from one conversation.', 'Contact enrichment and deduplication', 'Multi-channel sequences that run autonomously', 'In process of getting SOC 2 Type II'],
  'd82e14b6b2e70c20': ['Connect 30+ sales tools', '185', 'integrations across', 'Northlight connects to the tools you already use — through your browser session, not API keys.', 'HubSpot', 'Salesforce']
 }
}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(value, f, indent=2, ensure_ascii=False)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    registry = json.loads((ROOT / 'registry.json').read_text())['products'][:3]
    now = datetime.now(timezone.utc).isoformat()
    for product in registry:
        cid = product['id']
        case = ROOT / 'cases' / cid
        sources = []
        for key, needles in SNIPPETS[cid].items():
            record = json.loads((case / 'research' / (key + '.json')).read_text())
            capture = ROOT / record['capture_path']
            lines = capture.read_text().splitlines()
            excerpts = []
            for needle in needles:
                matches = [(i, line) for i, line in enumerate(lines) if needle in line]
                if not matches:
                    # Explicit failure instead of silently inventing a quotation.
                    raise ValueError(f'{cid}/{key}: quote absent: {needle}')
                i, line = matches[0]
                excerpts.append({'locator': f'{record["capture_path"]}:{i+1}-{i+1}', 'excerpt': line})
            sources.append({'evidence_id': f'p{cid}-{key}', 'source_url': record['url'],
                            'publisher': product['name'], 'retrieved_at': record['retrieved_at'], 'published_at': None,
                            'source_type': 'first_party_product_page', 'access_method': record['access_method'],
                            'scope_limitations': 'Vendor publication only, not independent verification or product execution. Bounded static text capture; may omit dynamic content.',
                            'capture_path': record['capture_path'], 'capture_sha256': record['capture_sha256'],
                            'capture_truncated': record['truncated'], 'excerpts': excerpts, 'error': record['error']})
        save(case / 'evidence.json', {'schema_version': 1, 'sources': sources})
        def ev(key):
            return [f'p{cid}-{key}']
        claims = []
        def claim(key, statement, classification, evidence_ids, uncertainty='Vendor claim, not independently verified', conflicts=None):
            claims.append({'claim_id': key, 'statement': statement, 'classification': classification,
                           'evidence_ids': evidence_ids, 'scope': {'observed_at': now, 'scope': 'Public pages captured for this pilot'},
                           'uncertainty': uncertainty, 'conflicting_claim_ids': conflicts or []})
        if cid == '001':
            claim('buyer', 'The rewriter page targets writers, students, and professionals.', 'vendor_claim', ev('043d8a5343b3ace8'))
            claim('workflow', 'The advertised paragraph rewriter preserves meaning and supports strength 1–4, default 3.', 'vendor_claim', ev('043d8a5343b3ace8'))
            claim('pricing', 'The rewriter page describes a character-limited trial and paid credit-based usage. The pricing capture distinguishes Starter and Premium but does not establish a dollar price.', 'vendor_claim', ev('043d8a5343b3ace8') + ev('0e3e543d064fd75c'))
            claim('adoption', 'Smodin publishes a 1 Million+ users claim. Active, paying and independently verified user counts remain unknown.', 'vendor_claim', ev('0e3e543d064fd75c'))
            claim('integrations', 'The API page advertises a REST API for rewriting and related text services.', 'vendor_claim', ev('8ed9b05793c0c98b'))
            claim('alternatives', 'A vendor-hosted testimonial names ChatGPT and QuillBot as tools previously used by that purported customer. This does not independently verify switching or comparative performance.', 'vendor_claim', ev('043d8a5343b3ace8'))
            claim('proprietary_access', 'Smodin advertises proprietary/specialized models and plagiarism scanning across billions of sources; none were accessed or evaluated.', 'vendor_claim', ev('8ed9b05793c0c98b') + ev('a2e0663d6daec6d0'))
            claim('distribution', 'Public tool pages and a no-signup rewrite trial may provide an acquisition channel. Conversion, traffic and acquisition cost are unknown.', 'inference', ev('043d8a5343b3ace8'), 'Hypothesis, not measured distribution advantage')
            claim('edge', 'Bundled rewriting, checking, APIs and specialized models could differentiate beyond a generic prompt. This pilot has no evidence that the differentiation improves quality or retention.', 'inference', ev('8ed9b05793c0c98b'), 'Untested technical and commercial hypothesis')
            workflow = {'target_user':'Writers editing their own English text', 'job':'Meaning-preserving paragraph rewrite', 'inputs':'Text, strength 1–4, protected facts', 'outputs':'Rewritten paragraph plus constraint audit', 'success_criteria':'Real model output preserves meaning and passes frozen rubric', 'included_behavior':['Input validation','Structured prompt','Protected-token response audit'], 'excluded_behavior':['Humanize/detector-evasion promises','Document parsing','Plagiarism search','Other languages','Model execution unavailable'], 'external_dependencies':['Authorized real model','Independent semantic evaluator']}
            coverage = ['Input validation and honest blocked-model handling execute locally', 'Response auditing code exists but no actual model response was tested']
            missing = ['Central rewrite model','Generic-model B1','Independent held-out tests','Original-product observations']
        elif cid == '002':
            claim('buyer', 'LinkBunny addresses site owners using coding agents.', 'vendor_claim', ev('c1788014a4b4c0d6'))
            claim('workflow', 'The vendor describes reviewed profiles, one DR-matched link request, a seven-day deadline, owner review and nofollow placement/reporting.', 'vendor_claim', ev('c1788014a4b4c0d6') + ev('79e13c11d1509761'))
            claim('pricing', 'The founding plan advertises $20/month for up to 10 sites with no per-backlink fees.', 'vendor_claim', ev('79e13c11d1509761'))
            claim('adoption', 'The homepage describes a small founding group, without a numeric count.', 'vendor_claim', ev('c1788014a4b4c0d6'))
            claim('integrations', 'The public setup page describes a local MCP client process calling LinkBunny over HTTPS with a token.', 'vendor_claim', ev('5aa93945dcc9ca51'))
            claim('size', 'The about page identifies its builder as a solo indie developer. This is not an audited current headcount.', 'vendor_claim', ev('79e6dafbfc3b5a89'))
            claim('alternatives', 'Manual partner discovery and editorial review are conceptual substitutes for automated matching. No alternative provider was benchmarked.', 'inference', ev('c1788014a4b4c0d6'), 'Model-knowledge hypothesis grounded in the workflow, not observed competitor performance')
            claim('distribution', 'The coding-agent setup and founder-operated onboarding may target developer-owned sites. Acquisition volume and conversion are unknown.', 'inference', ev('5aa93945dcc9ca51') + ev('79e13c11d1509761'), 'Unmeasured channel hypothesis')
            claim('proprietary_access', 'The reviewed marketplace pool is an access dependency not recreated by local matching code.', 'inference', ev('79e13c11d1509761') + ev('c1788014a4b4c0d6'), 'Pool size, availability and quality unknown')
            claim('edge', 'A real supply pool and manual review could be more defensible than the matching algorithm. A small pool could also constrain relevance. No evidence here establishes SEO, referral, or customer ROI.', 'inference', ev('c1788014a4b4c0d6'), 'Unverified commercial thesis, not a valuation')
            workflow = {'target_user':'Owners of synthetic sites', 'job':'Review and match backlink requests with local approval/reporting state', 'inputs':'Reviewed synthetic profiles, DR, editable scope, clock, owner decisions, local HTML', 'outputs':'Deterministic assignments, expiry/rejection, local-only nofollow report', 'success_criteria':'Frozen matching/lifecycle rules pass, no remote publication, B1 comparison and independent review completed', 'included_behavior':['Same-host validation','DR matching and deterministic ties','One pending outgoing request','Reverse-pair exclusion','Seven-day deadline','Owner approval','Nofollow/local-scope verification'], 'excluded_behavior':['Live backlink publishing','Real marketplace supply','Editorial AI','Real API compatibility','Payments','Authentication','Actual domain-rating lookup'], 'external_dependencies':['Reviewed generic-model baseline or approved alternative','Independent hidden evaluation','Real network value cannot be inferred from synthetic profiles']}
            coverage = ['Original in-memory marketplace subset runs on all 20 frozen scenarios']
            missing = ['Agent editorial reasoning','Generic-model B1 or reviewed alternative','Independent held-out tests','Real pool and original-product observations']
        else:
            claim('buyer', 'Northlight markets an AI sales/GTM desktop and conversational sales-stack operations.', 'vendor_claim', ev('fc836c603944acbe') + ev('b141c7f790990b2a'))
            claim('workflow', 'The features page advertises conversational CRM updates and contact enrichment/deduplication.', 'vendor_claim', ev('b141c7f790990b2a'))
            claim('pricing', 'The pricing page displays Free with 100 AI requests/month, Pro at $80/month with unlimited AI requests, and custom Enterprise. Billing/usage semantics are not verified.', 'vendor_claim', ev('b07c5236fed19199'), 'Static page observation, not purchased or billing-verified', ['pricing_credits'])
            claim('pricing_credits', 'The same page also describes credits, 10–20 credits per task, and reset each billing cycle, while its banner advertises a seven-day beta trial. This is unresolved against request-based plan copy.', 'vendor_claim', ev('b07c5236fed19199'), 'Conflicting/unclear usage and trial semantics preserved', ['pricing'])
            claim('adoption', 'The homepage publishes customer testimonials. No independently verified customer count or revenue is established.', 'vendor_claim', ev('fc836c603944acbe'))
            claim('integrations', 'The integrations page lists HubSpot and Salesforce and says 185 integrations, while navigation says 30+ sales tools. Actual working integration coverage was not observed.', 'vendor_claim', ev('d82e14b6b2e70c20'), 'Counts/scope differ within the captured page; not silently reconciled')
            claim('alternatives', 'Manual CRM edits and separate sales tools are conceptual alternatives to a unified chat. No specific competing system was benchmarked.', 'inference', ev('b141c7f790990b2a'), 'Model-knowledge hypothesis, not competitor research')
            claim('distribution', 'A downloadable desktop and published testimonials may support product-led acquisition. Neither conversion nor trust was measured.', 'inference', ev('fc836c603944acbe'), 'Unmeasured acquisition hypothesis')
            claim('proprietary_access', 'Browser-session access and context across sales tools are dependencies that a local JSON preview does not reproduce.', 'inference', ev('d82e14b6b2e70c20'), 'No sessions, integrations, or private data accessed')
            claim('edge', 'Reliable integration coverage, permissions and persistent context could be valuable beyond a prompt. Neither reliability nor retention was measured, and conflicting plan/integration copy warrants clarification.', 'inference', ev('d82e14b6b2e70c20') + ev('b07c5236fed19199'), 'Untested commercial thesis')
            workflow = {'target_user':'Sales operators maintaining contact data', 'job':'Natural-language request to approved CRM update/deduplication', 'inputs':'User instruction and contact records; current partial layer accepts explicit structured action instead', 'outputs':'Intended: verified CRM changes. Actual: synthetic local previews only', 'success_criteria':'Real AI parsing and approved action execution pass frozen rubric without unauthorized writes', 'included_behavior':['Structured update preview','Email-normalized duplicate proposals','Unknown/invalid input rejection','Inert notes','No input mutation'], 'excluded_behavior':['Model parsing','Real CRM persistence','Desktop control','LinkedIn/X','Sending outreach','Contact enrichment','Autonomous sequences'], 'external_dependencies':['Authorized inference','Approved synthetic integration evaluator','Independent hidden tests']}
            coverage = ['Original structured CRM preview subset runs on all 20 frozen scenarios']
            missing = ['Natural-language inference','Real authorized integration','Generic-model B1','Independent hidden tests','Original-product observations']
        research = {}
        ids = {c['claim_id'] for c in claims}
        for topic in ['pricing','buyer','alternatives','adoption','distribution','integrations','proprietary_access','switching_costs','operating_economics']:
            if topic in ids:
                research[topic] = {'claim_ids':[topic], 'value':'See claim; observations and inferences are separately classified', 'unknown_reason':None}
            else:
                research[topic] = {'claim_ids':[], 'value':None, 'unknown_reason':'Reviewed public product, pricing and workflow pages do not establish retention/migration costs or cost of delivery. No customer interviews, billing, or provider usage observed.'}
        stages = {'identity':'passed','research':'in_progress','implementation':'blocked','execution':'blocked','evaluation':'blocked','review':'not_started'}
        receipts = sorted(str(p.relative_to(ROOT)) for p in (case/'receipts').glob('*-local-*.json') if '.stdout.' not in p.name)
        baseline = receipt_template(cid, cid + '-baseline-blocked', 'B1')
        baseline.update(status='blocked', missing_capabilities=['No authorized callable generic-model endpoint verified; no model invocation attempted'])
        save(case / 'receipts/baseline-blocked.json', baseline)
        receipts.append(f'cases/{cid}/receipts/baseline-blocked.json')
        fixture = case/'tests/fixtures.json'
        fixed = json.loads(fixture.read_text())['fixed_at']
        dossier = {'schema_version':1,'record_status':'blocked',
                   'identity':{key:product[key] for key in ['id','name','canonical_url','category','identity_status','identity_evidence_ids','aliases']},
                   'selection':{'candidate_id':product['candidate_id'],'selection_position':product['selection_position'],'eligibility_evidence_ids':product['small_company'].get('evidence_ids',[]),'pilot':True,'replacement_reference':None},
                   'workflow':workflow, 'research':research,'claims':claims,
                   'tests':{'specification_path':str(fixture.relative_to(ROOT)),'sha256':sha(fixture),'fixed_at':fixed,'acceptance_criteria':'protocol.md plus tests/specification.md; thresholds not satisfied by local regressions','baseline_specification':'Same frozen inputs to B1; currently blocked','held_out':False},
                   'implementation':{'source_path':f'cases/{cid}/implementation/workflow.py','sha256':sha(case/'implementation/workflow.py'),'setup_instructions':f'python3 -B research/ai-saas-100/cases/{cid}/tests/run.py','coverage':coverage,'missing_capabilities':missing,'dependency_license_notes':'Original code written for this campaign. Python standard library only; no vendor code or model weights used.','kind':'independent_partial','requires_inference':cid!='002'},
                   'assessment':{'stage_statuses':stages,'receipt_paths':receipts,'technical_uncertainty':missing,'commercial_uncertainty':['Vendor-only research; no demand, retention, billing, or ROI validation'],'verdict_path':f'cases/{cid}/verdict.json','review':{'reviewer':None,'independent':False,'accepted':False,'unresolved_material_objections':['Pilot incomplete; independent review pending'],'artifact':None}},
                   'original_product':{'status':'not_observed','reason':'No authorized interactive service execution performed. Public page GETs are not workflow trials.','observed_at':now},
                   'status_history':product['status_history'] + [{'stage':s,'from':'not_started','to':'in_progress','at':now,'actor':'grok','reason':'Bounded pilot research/local implementation attempted','evidence_ids':[]} for s in ['research','implementation','execution','evaluation']] + [{'stage':s,'from':'in_progress','to':'blocked','at':now,'actor':'grok','reason':'; '.join(missing),'evidence_ids':[]} for s in ['implementation','execution','evaluation']],
                   'blockers':[{'scope':'campaign','cause':'No independently callable authorized inference verified','affected_stages':['execution','evaluation'],'permitted_next_action':'Verify a no-charge model without inspecting secrets, or request explicit provider budget/authorization','evidence':['capabilities.json','cases/001/research/inference-probes.json']},{'scope':'product','cause':'Only partial representative workflow and builder-visible regression suite','affected_stages':['implementation','execution','review'],'permitted_next_action':'Complete missing behavior and obtain independently retained held-out evaluation','evidence':[f'cases/{cid}/tests/specification.md']}],
                   'research_limitations':['Four first-party pages reviewed per pilot; not extensive independent commercial research','Pricing copy is not revenue','Unknown users is not zero users','Prototype simplicity is not evidence of low company value']}
        save(case/'dossier.json', dossier)
        verdict = {'schema_version':1,'recommendation':'insufficient_evidence','thesis':'Assess whether independently reproducing one workflow establishes a worthwhile competing product.',
                   'technical_assessment':{'status':'incomplete','local_coverage':coverage,'missing':missing,'parity_claim':False},
                   'commercial_assessment':{'status':'unknown','possible_edge_claim_id':'edge','valuation':None,'reason':'No verified economics, customer demand, or original-service quality comparison'},
                   'supporting_claim_ids':['workflow','edge'],'counterevidence_claim_ids':['proprietary_access'],
                   'uncertainties':['Buyer willingness to pay','Distribution cost','Retention','Actual quality and reliability'],
                   'next_falsification_test':'Run the central workflow and generic baseline on identical independent fixtures, then validate buyer demand through separately authorized research.',
                   'reviewer':'grok (author self-assessment only, not independent acceptance)','reviewed_at':now}
        save(case/'verdict.json', verdict)
        print(cid, len(sources), 'sources;', len(claims), 'claims; incomplete')


if __name__ == '__main__':
    main()
