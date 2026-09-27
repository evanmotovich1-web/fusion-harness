#!/usr/bin/env python3
"""Generate task 3.b research handoffs from reviewed source captures and fixed design profiles."""
import copy, datetime, hashlib, json, pathlib, re, runpy
ROOT=pathlib.Path(__file__).resolve().parents[3]
HERE=pathlib.Path(__file__).resolve().parent
PROFILES=json.loads((HERE/'profiles.json').read_text())
REG=json.loads((ROOT/'registry.json').read_text())
DISCOVERY={e['evidence_id']:e for e in json.loads((ROOT/'discovery/evidence.json').read_text())['sources']}
POOL={c['candidate_id']:c for c in json.loads((ROOT/'discovery/candidate-pool.json').read_text())}
MAKE=runpy.run_path(str(HERE/'fixtures.py'))['make']
STAMP=datetime.datetime.now(datetime.timezone.utc).isoformat()

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True);assert not path.exists(),f'Refusing to overwrite {path}'
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
def raw_for(e):return json.loads((ROOT/e['record_path']).read_text())
def describe(r):
    return next((m['value'] for m in r.get('metadata',[]) if m['key']=='description'),next((m['value'] for m in r.get('metadata',[]) if m['key']=='og:description'),r.get('title','')))
def index_record(r,path):
    excerpts=[]
    if r.get('title'):excerpts.append({'locator':'title','excerpt':r['title']})
    seen=set()
    for i,m in enumerate(r.get('metadata',[])):
        if m['value'] and m['value'] not in seen:excerpts.append({'locator':f'metadata[{i}].{m["key"]}','excerpt':m['value']});seen.add(m['value'])
    return {**{k:r.get(k) for k in ['evidence_id','source_url','publisher','retrieved_at','published_at','source_type','access_method','scope_limitations','status','final_url','capture_path','capture_sha256','capture_truncated','error']},'record_path':str(path.relative_to(ROOT)),'research_role':r['research_role'],'excerpts':excerpts}

ledger=[]
for product in REG['products'][3:35]:
    cid=product['id'];profile=PROFILES[cid];folder=ROOT/'cases'/cid
    sources={};raws={};roles={}
    for eid in product['identity_evidence_ids']:
        sources[eid]=copy.deepcopy(DISCOVERY[eid]);raws[eid]=raw_for(sources[eid]);roles[eid]='home'
    for file in sorted((folder/'research/records').glob('*.json')):
        r=json.loads(file.read_text());eid=r['evidence_id'];sources[eid]=index_record(r,file);raws[eid]=r;roles[eid]=r['research_role']
    alt=POOL[profile['alternative']]
    alt_eid=alt['identity_evidence_ids'][0]
    sources[alt_eid]=copy.deepcopy(DISCOVERY[alt_eid]);raws[alt_eid]=raw_for(sources[alt_eid]);roles[alt_eid]='alternative'
    def quote(needle,preferred=None,before=100,after=600,only_role=None):
        eids=list(sources)
        if preferred:eids.sort(key=lambda x:0 if roles[x]==preferred else 1)
        for eid in eids:
            if only_role and roles[eid]!=only_role:continue
            if not only_role and roles[eid]=='alternative':continue
            r=raws[eid]
            if r.get('status')!=200:continue
            if needle=='@description':
                fields=[(f'metadata[{i}].{m["key"]}',m['value']) for i,m in enumerate(r.get('metadata',[])) if m['key'] in ('description','og:description')]
                if not fields:fields=[('title',r.get('title',''))]
                if not fields[0][1]:continue
                loc,q=fields[0]
            else:
                pattern=r'\s+'.join(re.escape(w) for w in needle.split())
                fields=[('text',r.get('text',''))]+[(f'metadata[{i}].{m["key"]}',m['value']) for i,m in enumerate(r.get('metadata',[]))]
                found=None
                for field,value in fields:
                    m=re.search(pattern,value,re.I)
                    if m:
                        start,end=max(0,m.start()-before),min(len(value),m.end()+after)
                        found=(f'text characters {start}:{end}' if field=='text' else field,value[start:end] if field=='text' else value);break
                if not found:continue
                loc,q=found
            item={'locator':loc,'excerpt':q}
            if item not in sources[eid].setdefault('excerpts',[]):sources[eid]['excerpts'].append(item)
            return {'evidence_id':eid,**item}
        return None
    claims=[]
    def claim(key,statement,kind,qs=None,uncertainty=None,conflicts=None):
        qs=[q for q in (qs or []) if q]
        eids=list(dict.fromkeys(q['evidence_id'] for q in qs))
        if kind in ('vendor_claim','direct_observation'):assert eids,(cid,key)
        c={'claim_id':key,'statement':statement,'classification':kind,'evidence_ids':eids,'supporting_excerpts':qs,'scope':{'reviewed_at':STAMP,'source_retrieval_times':{eid:sources[eid]['retrieved_at'] for eid in eids},'scope':'Bounded public first-party research. No account, purchase, customer interview, original-product execution, or benchmark.'},'uncertainty':uncertainty or 'Vendor statement not independently verified. Source can be incomplete, stale, or marketing-oriented.','conflicting_claim_ids':conflicts or []};claims.append(c);return key
    def topic(ids=None,value=None,reason=None):return {'claim_ids':ids or [],'value':value,'unknown_reason':reason}
    home=quote('@description',preferred='home');work=quote('@description',preferred='workflow') or home
    if roles[work['evidence_id']]=='alternative':work=home
    claim('identity','Public product identity and advertised workflow are linked by the captured canonical product source.','direct_observation',[home])
    claim('workflow-advertised','Vendor description: '+work['excerpt'],'vendor_claim',[work],uncertainty='This advertises a workflow, not proof it functions or that the proposed narrower prototype covers the whole platform.')
    claim('buyer','Intended-buyer interpretation: '+profile['buyer']+'.','inference',[home,work],uncertainty='Researcher interpretation of vendor positioning, not verified purchaser demographics.')
    pricing_q=quote(profile['price_anchor'],preferred='pricing',only_role='pricing',before=260,after=2200) if profile.get('price_anchor') else None
    has_price=profile.get('price_amount_observed',bool(re.search(r'[$€£]\d',profile['price_note'])))
    if pricing_q:
        claim('pricing-observation',profile['price_note'],'vendor_claim' if has_price else 'direct_observation',[pricing_q],uncertainty='Public advertised terms only. Checkout, tax, geographic availability, billing toggles, fair-use rules and paid entitlement were not exercised.')
        price=topic(['pricing-observation'],profile['price_note'] if has_price else None,None if has_price else profile['price_note'])
    else:price=topic(reason=profile['price_note'])
    adoption_q=quote(profile['adoption_anchor'],preferred='home',before=70,after=180) if profile.get('adoption_anchor') else None
    if adoption_q:
        claim('adoption-vendor','Vendor adoption-related wording: '+adoption_q['excerpt'],'vendor_claim',[adoption_q],uncertainty='Not independently verified. Users, teams, creators, seats and paying customers are distinct. No zero-user inference or numerical valuation.')
        adoption=topic(['adoption-vendor'],{'verified_customer_count':None,'vendor_claim_available':True},'No verified current paying-customer count, revenue, retention, or cohort data.')
    else:adoption=topic(reason='Inspected available product and follow-up captures without establishing a reliable current paying-customer count. Absence or incomplete rendering does not mean zero users.')
    integration_q=quote(profile['integration_anchor'],preferred='integrations',before=80,after=450) if profile.get('integration_anchor') else None
    if integration_q:
        claim('integrations-advertised','Integration-related vendor wording: '+integration_q['excerpt'],'vendor_claim',[integration_q],uncertainty='Documentation/navigation or a product claim is not a tested connector. Availability can depend on plan or account access.')
        integrations=topic(['integrations-advertised'],'See source-backed advertised interface/integration excerpt. Actual operation untested.')
    else:integrations=topic(reason='Available homepage, pricing and follow-up captures did not establish specific working integration details. No authenticated connection or API call was attempted.')
    prop_q=quote(profile['proprietary_anchor'],preferred='security',before=140,after=500) if profile.get('proprietary_anchor') else None
    if prop_q:
        claim('proprietary-vendor','Vendor data/model/security wording: '+prop_q['excerpt'],'vendor_claim',[prop_q],uncertainty='No independent verification of exclusivity, training data rights, model quality, certification, or contractual enforceability.')
        proprietary=topic(['proprietary-vendor'],{'exclusive_access_verified':False},'Vendor statements do not establish exclusive access or an independently demonstrated technical advantage.')
    else:proprietary=topic(reason='Inspected available public descriptions. No proprietary training corpus, exclusive provider rights, patented advantage, or unique customer data access independently established. Private contracts and model internals were not accessed.')
    alternative_q=quote('@description',only_role='alternative')
    claim('alternative-description',alt['official_name']+' advertises: '+alternative_q['excerpt'],'vendor_claim',[alternative_q])
    claim('alternatives','Workflow-overlap candidate: '+alt['official_name']+'. Manual task execution and a general model with the same supplied materials are further baseline options.','inference',[home,alternative_q],uncertainty='Feature overlap inferred from official descriptions. No parity, superiority, price comparison, or competitor benchmark is asserted.')
    claim('distribution','A public product landing page is an observed web distribution surface. Its presence does not establish traffic, conversion, acquisition cost, paid channels, or distribution strength.','direct_observation',[home],uncertainty='Only the public web surface was observed.')
    claim('switching-hypothesis',profile['edge'],'inference',[home,work]+([integration_q] if integration_q else []),uncertainty='Potential advantage and switching-cost hypothesis, not measured customer retention or a demonstrated moat. Counterexample: portable data and standard APIs may reduce switching friction.')
    conflicts=[]
    if cid=='006':
        a=quote('50+ built-in data providers',preferred='integrations',only_role='integrations');b=quote('200+ providers',preferred='home')
        if a and b:
            claim('provider-count-metadata','Integrations metadata refers to 50+ built-in data providers.','vendor_claim',[a],conflicts=['provider-count-navigation'])
            claim('provider-count-navigation','Navigation refers to buying data from 200+ providers.','vendor_claim',[b],conflicts=['provider-count-metadata'])
            conflicts.append({'claim_ids':['provider-count-metadata','provider-count-navigation'],'type':'scope_or_freshness_ambiguity','finding':'Different advertised lower bounds can both be true. Do not treat them as a proven contradiction or one audited integration count.'})
    if cid=='021':
        a=quote('unlimited capabilities',preferred='pricing',only_role='pricing');b=quote('3 videos per month',preferred='pricing',only_role='pricing')
        if a and b:
            claim('free-broad-marketing','Pricing metadata uses the wording unlimited capabilities.','vendor_claim',[a],conflicts=['free-visible-limit'])
            claim('free-visible-limit','Visible Free plan says three videos per month, up to one minute each.','vendor_claim',[b],conflicts=['free-broad-marketing'])
            conflicts.append({'claim_ids':['free-broad-marketing','free-visible-limit'],'type':'marketing_vs_plan_limit','finding':'Retain both. Do not infer unlimited free video generation.'})
    if cid=='028':
        a=quote('Pro\n$15.99',preferred='pricing',only_role='pricing');b=quote('$\n9.99',preferred='pricing',only_role='pricing')
        if a and b:
            claim('pro-card-price','Pro card shows $15.99.','vendor_claim',[a],conflicts=['pro-calculator-price'])
            claim('pro-calculator-price','Calculator shows PRO $9.99/user/month.','vendor_claim',[b],conflicts=['pro-card-price'])
            conflicts.append({'claim_ids':['pro-card-price','pro-calculator-price'],'type':'billing_view_ambiguity','finding':'Static extraction does not establish which billing view each amount represents. No silent reconciliation.'})
    if cid=='032':
        a=quote('individual "Developer"',preferred='pricing',only_role='pricing');b=quote('Pro Team',preferred='pricing',only_role='pricing')
        if a and b:
            claim('pricing-metadata-tiers','Metadata names individual Developer, Teams and Enterprise plans.','vendor_claim',[a],conflicts=['pricing-visible-tiers'])
            claim('pricing-visible-tiers','Visible page uses a Pro Team credit-pack/trial structure and Enterprise.','vendor_claim',[b],conflicts=['pricing-metadata-tiers'])
            conflicts.append({'claim_ids':['pricing-metadata-tiers','pricing-visible-tiers'],'type':'page_version_or_plan_scope','finding':'Potential metadata staleness or differing scope. Preserve both; do not promise a named free tier without account verification.'})
    spec=MAKE(ROOT,cid,profile,STAMP);spec_path=folder/'tests/specification.json';save(spec_path,spec);spec_hash=hashlib.sha256(spec_path.read_bytes()).hexdigest()
    extra_deps=[]
    if profile['family'] in ('meeting','textvideo','avatar','clip'):extra_deps+=['Authorized actual audio/video model capability and media decoding; transcript-only output is insufficient.']
    if profile['family'] in ('background','adimage','anatomy','avatar'):extra_deps+=['Authorized actual image/video generation and visual evaluation; JSON descriptions are insufficient.']
    if profile['family']=='anatomy':extra_deps+=['Independent anatomical subject-matter review before accepting correctness.']
    if profile['family']=='enrichment':extra_deps+=['Controlled fixture providers are synthetic. Real-world enrichment quality needs separately authorized data sources.']
    scope_exclusions=['Full production SaaS, billing, account/tenant management, deployment, scale and availability guarantees','Live third-party accounts, proprietary datasets, paid model calls and real customer data','Original-product parity, business valuation and customer-demand validation','Independent hidden evaluation not yet prepared']
    dossier={'schema_version':1,'record_status':'unknown','identity':{k:product[k] for k in ('id','name','canonical_url','category','identity_status','identity_evidence_ids','aliases')},'selection':{'candidate_id':product['candidate_id'],'selection_position':product['selection_position'],'eligibility_evidence_ids':product['small_company'].get('evidence_ids',[]),'pilot':False,'replacement_reference':None},'workflow':{'target_user':profile['buyer'],'job':profile['job'],'inputs':'Concrete typed requests and original synthetic assets in tests/specification.json','outputs':spec['output_schema'],'success_criteria':spec['acceptance_criteria'],'included_behavior':['One central workflow subset defined by this case, not an easy unrelated feature','Real generation/extraction/reasoning where central','Schema checks, evidence preservation, uncertainty handling and safe failures'],'excluded_behavior':scope_exclusions,'external_dependencies':['Accepted pilot method for this workflow class','Verified authorized model/baseline access where inference is central','Independent reviewer and hidden fixture version']+extra_deps,'representativeness':'Proposed central-workflow subset based on public vendor positioning. Independent review must confirm coverage before implementation acceptance. Integration-heavy and modality-heavy products cannot inherit text-only pilot acceptance.','inference_required':profile['family']!='schedule'},'research':{'primary_workflow':topic(['workflow-advertised'],profile['job']),'pricing':price,'buyer':topic(['buyer'],profile['buyer']),'alternatives':topic(['alternative-description','alternatives'],{'candidate_id':alt['candidate_id'],'name':alt['official_name'],'benchmark_observed':False}),'adoption':adoption,'distribution':topic(['distribution'],'Public product website observed; acquisition effectiveness unknown.'),'integrations':integrations,'proprietary_access':proprietary,'switching_costs':topic(['switching-hypothesis'],None,'No measured migration effort, retention, expansion, or customer lock-in. Hypothesis only.'),'operating_economics':topic(reason='No billed inference, infrastructure allocation, gross margin, customer-acquisition cost, or churn data observed. Vendor subscription prices do not establish cost of delivery or business value.'),'conflicts':conflicts,'inaccessible_sources':[{'source_url':e['source_url'],'evidence_id':eid,'reason':e['error']} for eid,e in sources.items() if e.get('error')],'scope':'Bounded public first-party investigation and an evidence-linked alternative. No independent customer validation. Required commercial unknowns are explicit, not filled with zeros.'},'claims':claims,'tests':{'specification_path':str(spec_path.relative_to(ROOT)),'sha256':spec_hash,'fixed_at':STAMP,'acceptance_criteria':spec['acceptance_criteria'],'baseline_specification':spec['baseline_specification'],'exposure':'Builder-visible fixed regression. Not held-out.','fixture_count':20},'implementation':{'source_path':None,'sha256':None,'setup_instructions':None,'coverage':[],'missing_capabilities':['No implementation attempted in task 3.b','Pilot acceptance and authorized inference/baseline remain unresolved','Independent hidden fixtures and review']+extra_deps,'dependency_license_notes':'Original synthetic fixtures. PIL/reportlab and locally installed macOS speech/ffmpeg used only to prepare test inputs; no proprietary product code/assets copied. No runtime license or deployment audit performed.','kind':'not_started','requires_inference':profile['family']!='schedule'},'assessment':{'stage_statuses':{'identity':'passed','research':'in_progress','implementation':'not_started','execution':'not_started','evaluation':'not_started','review':'not_started'},'receipt_paths':[],'technical_uncertainty':['No workflow or model baseline executed','Real product runtime behavior unknown','Fixture coverage and scoped subset need independent review']+extra_deps,'commercial_uncertainty':['Current paying customers and revenue unknown','Only vendor claims and explicit hypotheses, not verified competitive advantage','No exact valuation or worthlessness conclusion'],'verdict_path':None,'review':{'reviewer':None,'independent':False,'accepted':False,'unresolved_material_objections':['Bounded research incomplete; implementation and evaluation not started'],'artifact':None},'original_product_access':{'status':'not_observed','reason':'Public research only. No signup, login, account integration, product inference or paid access attempted.'}},'status_history':copy.deepcopy(product['status_history'])+[{'stage':'research','from':'not_started','to':'in_progress','at':STAMP,'actor':'terra','reason':'Bounded source investigation and fixed-test specification recorded. Not marked complete without further review.','evidence_ids':list(sources)}],'research_completed_at':None,'research_recorded_at':STAMP,'readiness':{'fixed_inputs_available':True,'implementation_execution_ready':False,'reason':'Prototype build remains gated by accepted pilot method, authorized runtime/model access, and independent test review. Read latest pilot acceptance before starting.'}}
    # Eligibility sources can be shared discovery evidence outside the case's homepage records.
    for eid in dossier['selection']['eligibility_evidence_ids']:
        if eid not in sources:sources[eid]=copy.deepcopy(DISCOVERY[eid])
    save(folder/'evidence.json',{'schema_version':1,'sources':list(sources.values())})
    save(folder/'dossier.json',dossier)
    save(folder/'tests/freeze.json',{'schema_version':1,'case_id':cid,'fixed_at':STAMP,'specification_path':str(spec_path.relative_to(ROOT)),'specification_sha256':spec_hash,'assets':spec['asset_manifest'],'builder_exposure':'all visible','prototype_execution_status':'not_started'})
    handoff=folder/'handoff.md';assert not handoff.exists()
    handoff.write_text(f'# {cid}: {product["name"]}\n\nTask 3.b recorded a bounded public-source dossier and 20 fixed regression cases. Research is in progress, not independently accepted. No implementation or benchmark was executed.\n\nWorkflow: {profile["job"]}.\n\nPotential advantage to investigate: {profile["edge"]}\n\nPricing observation/limitation: {profile["price_note"]}\n\nRead dossier.json, evidence.json, tests/specification.json, and tests/freeze.json before building. Preserve the fixed asset hashes. All answers are builder-visible, so an independent evaluator must author hidden cases before claiming protocol acceptance. Execute B1 and B2 on identical inputs with genuine authorized inference where central. Never substitute descriptions for essential media outputs or hardcode the expected answers. Original-product comparison remains not_observed.\n\nCheck the latest pilot-acceptance artifact and authorization before scaling. Keep changes inside this case; propose replacements through the batch owner. Do not alter registry identities or treat public marketing metrics as verified adoption.\n')
    local_pages=[e for e in sources.values() if e.get('research_role')]
    ledger.append({'id':cid,'name':product['name'],'dossier_path':f'cases/{cid}/dossier.json','evidence_path':f'cases/{cid}/evidence.json','specification_path':str(spec_path.relative_to(ROOT)),'fixture_count':20,'fixture_exposure':'fixed_regression_builder_visible','new_page_attempts':len(local_pages),'new_page_successes':sum(e['status']==200 for e in local_pages),'new_page_failures':sum(e['status']!=200 for e in local_pages),'pricing_amount_observed':has_price and pricing_q is not None,'research_status':'in_progress_bounded_first_party','implementation_readiness':'not_execution_ready','implemented':False,'executed':False,'accepted':False,'unresolved_topics':[key for key,value in dossier['research'].items() if isinstance(value,dict) and value.get('unknown_reason')],'conflict_count':len(conflicts),'next_action':'Read latest pilot acceptance, independently review scope, resolve genuine model/media/baseline access, then implement inside assigned case.'})

save(HERE/'replacement-proposals.json',{'schema_version':1,'task_id':'3.b','proposals':[],'reason':'No verified identity failure requiring replacement found in this bounded research. Inaccessible follow-up URLs or missing model access do not justify silently changing registry membership.'})
rows=list(ledger)
batch={'schema_version':1,'task_id':'3.b','owner':'terra','assigned_ids':[f'{i:03}' for i in range(4,36)],'recorded_at':STAMP,'scope':'Accurate bounded research and test-design handoff, not accepted products or comprehensive independent market research.','counts':{'assigned':32,'attempted':len(rows),'dossiers_written':len(rows),'fixed_test_specifications':len(rows),'fixed_regression_cases':sum(x['fixture_count'] for x in rows),'new_public_page_attempts':sum(x['new_page_attempts'] for x in rows),'new_public_page_successes':sum(x['new_page_successes'] for x in rows),'new_public_page_failures':sum(x['new_page_failures'] for x in rows),'research_stage_passed':0,'implemented_products':0,'executed_products':0,'accepted_products':0,'incomplete_products':32,'execution_readiness_blocked_products':32,'unattempted_products':0},'products':rows,'replacement_proposals_path':'cases/004/research/replacement-proposals.json','shared_registry_modified':False,'original_product_workflows_executed':0,'benchmark_model_calls':0,'additional_paid_api_calls':0,'purchases':0,'operating_cost_usd':None,'operating_cost_unknown_reason':'No product execution, usage bill, or allocated resource cost measured. Fixture generation is not a product benchmark.','duration':{'requested_minimum_campaign_seconds':86400,'observed_active_campaign_seconds':None,'duration_fulfilled':False,'reason':'No continuous activity instrumentation or 24-hour claim. Individual public requests and media fixture-generation commands retain actual timestamps.'},'common_blockers':['Latest inspected pilot-results.json has no accepted pilot method or executed generic-model baseline. Read later pilot-acceptance before build.','No authorized independently callable inference/model endpoint established in this research task.','All fixtures are exposed fixed regression, not independent hidden evaluation.','Media workflows require actual modality execution and cannot inherit text-only acceptance.'],'limitations':['Public vendor pages support claims about advertised features/terms only.','Customer counts, exclusive data rights, acquisition costs, gross margins and switching costs are largely unknown.','A functional prototype cannot establish a company has no value.','Existing discovery captures were reused and dated; 64 new follow-up pages were attempted without login or purchases.'],'handoff_task':'5.a','handoff':'GROK owns subsequent implementations 004-035 after the accepted pilot gate. Preserve fixtures and hashes, record all genuine executions, and keep unavailable functions explicitly blocked. Independent audit follows.','validation_receipt_path':'cases/004/research/validation.json'}
save(ROOT/'batches/research-004-035.json',batch)
print(json.dumps(batch['counts'],indent=2))
