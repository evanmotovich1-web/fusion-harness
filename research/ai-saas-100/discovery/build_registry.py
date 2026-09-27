#!/usr/bin/env python3
"""Offline, deterministic discovery registry builder. --check does not write files."""
import collections
import hashlib
import json
import pathlib
import re
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT / 'discovery'
def load(path):
    return json.loads(path.read_text())
def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()
def pretty(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'
def idna(host):
    return host.rstrip('.').encode('idna').decode('ascii').lower()

# Pinned full PSL, including private suffixes and exception/wildcard rules.
RULES = set()
for line in (D / 'public_suffix_list.dat').read_text().splitlines():
    line = line.strip()
    if line and not line.startswith('//'):
        prefix = '!' if line.startswith('!') else '*.' if line.startswith('*.') else ''
        RULES.add(prefix + idna(line[len(prefix):]))
def registrable(host):
    parts = idna(host).split('.')
    exceptions = [i for i in range(len(parts)) if '!' + '.'.join(parts[i:]) in RULES]
    if exceptions:
        suffix_len = len(parts) - min(exceptions) - 1
    else:
        lengths = [1]
        for i in range(len(parts)):
            suffix = '.'.join(parts[i:])
            if suffix in RULES:
                lengths.append(len(parts)-i)
            if i > 0 and '*.' + suffix in RULES:
                lengths.append(len(parts)-i+1)
        suffix_len = max(lengths)
    return '.'.join(parts[-min(len(parts), suffix_len+1):])
def normalized(url):
    u = urllib.parse.urlsplit(url)
    assert u.scheme in ('https', 'http') and u.hostname and not u.username
    host = idna(u.hostname)
    port = u.port
    netloc = host if port is None or (u.scheme, port) in [('https', 443), ('http', 80)] else f'{host}:{port}'
    query = urllib.parse.urlencode([(k,v) for k,v in urllib.parse.parse_qsl(u.query) if not k.lower().startswith('utm_') and k not in ('ref','ref_type','fbclid','gclid')])
    return urllib.parse.urlunsplit((u.scheme,netloc,u.path or '/',query,''))

plan = load(D/'plan.json')
review = load(D/'review-decisions.json')
freeze = load(D/'freeze.json')
psl = load(D/'public-suffix-evidence.json')
assert hashlib.sha256((D/'public_suffix_list.dat').read_bytes()).hexdigest() == psl['capture_sha256']
records = {}
for path in sorted((D/'records').glob('*.json')):
    r = load(path)
    assert r['source_url'] not in records
    r['record_path'] = str(path.relative_to(ROOT))
    records[r['source_url']] = r

def evidence_for(r):
    url = r['source_url']; host = urllib.parse.urlparse(url).hostname
    if host == 'www.uneed.best' or host in ('www.futuretools.io','www.producthunt.com'):
        source_type = 'public_product_directory'
    elif host in ('www.google.com','www.bing.com'):
        source_type = 'search_result_page'
    elif host == 'publicsuffix.org':
        source_type = 'technical_reference'
    else:
        source_type = 'first_party_product_page'
    quotes = []
    if r.get('title'):
        quotes.append({'locator':'title','excerpt':r['title']})
    seen = set()
    for i, meta in enumerate(r.get('metadata',[])):
        if meta['value'] and meta['value'] not in seen:
            quotes.append({'locator':f'metadata[{i}].{meta["key"]}','excerpt':meta['value']})
            seen.add(meta['value'])
    text = r.get('text','')
    for m in list(re.finditer(r'\bAI\b|\bLLM\b|solo indie|no longer be available|part of|has been acquired',text,re.I))[:6]:
        start,end=max(0,m.start()-70),min(len(text),m.end()+240)
        quotes.append({'locator':f'text characters {start}:{end}','excerpt':text[start:end]})
    return {'evidence_id':r['evidence_id'],'source_url':url,'final_url':r.get('final_url'),'publisher':host,'retrieved_at':r['retrieved_at'],'published_at':r.get('published_at'),'source_type':source_type,'access_method':r['access_method'],'status':r['status'],'excerpts':quotes,'capture_path':r.get('capture_path'),'capture_sha256':r.get('capture_sha256'),'record_path':r['record_path'],'capture_truncated':r.get('capture_truncated'),'error':r.get('error'),'scope_limitations':r['scope_limitations']}

evidence = [evidence_for(r) for r in records.values()]
by_eid = {r['evidence_id']:r for r in records.values()}
leads = []
for i,line in enumerate((D/'lead-seeds.tsv').read_text().splitlines(),1):
    cat,name,url=line.split('\t')
    leads.append({'name':name,'category':cat,'url':url,'origin':{'type':'model_knowledge_unverified_lead','path':'discovery/lead-seeds.tsv','line':i},'approved':name in review['reviewed_seed_approvals']})
for x in load(D/'directory-leads.json')['leads']:
    leads.append({'name':x['name'],'category':x['category'],'url':x['official_url'],'origin':{'type':'public_directory','source_url':'https://www.uneed.best/','listing_url':x['listing_url'],'listing_evidence_id':records[x['listing_url']]['evidence_id'],'display_rank':x['display_rank']},'approved':x['review_eligible']})

pool_by_id = {}
merges=[]
for lead in leads:
    name=lead['name']; r=records[lead['url']]
    good=lead['approved'] and r['status']==200
    canonical=normalized(r.get('final_url') or lead['url'])
    host=urllib.parse.urlsplit(canonical).hostname
    key=registrable(host)
    assert '\n' not in key
    override=review['category_overrides'].get(name)
    cat=override['category'] if override else lead['category']
    official=review['official_name_overrides'].get(name,name)
    urls=[lead['url']]+review['additional_identity_sources'].get(name,[])
    refs=[records[u]['evidence_id'] for u in urls]
    small=review['small_company_decisions'].get(name)
    if small:
        size=dict(small)
        sr=records[small['source_url']]
        assert small['excerpt'] in sr['text']
        size.update(evidence_ids=[sr['evidence_id']],observed_at=sr['retrieved_at'],published_at=None)
    else:
        size={'tier':'E2','headcount':None,'classification':'unknown','evidence_ids':[],'unknown_reason':review['unknown_size_notes'].get(name,'No dated current company-size evidence collected. Do not infer size from brand familiarity, number of founders, or advertised customer counts.')}
    item={'candidate_id':key,'observed_names':[name],'official_name':official if good else None,'canonical_url':canonical,'canonical_host':host,'registrable_domain':key,'aliases':[lead['url']] if lead['url']!=canonical else [],'owner_if_known':None,'category':cat,'category_rationale':override['reason'] if override else 'Reviewed advertised principal workflow against the predeclared category. No commercial score used.','discovery_sources':[lead['origin']],'identity_status':'verified' if good else 'unverified_or_ineligible','identity_evidence_ids':refs,'retrieved_at_utc':r['retrieved_at'],'eligibility_status':'eligible' if good else 'excluded','exclusion_reason':None if good else review['explicit_exclusions'].get(name,review['default_unapproved_reason']),'small_company':size,'customer_count':None,'customer_count_status':'unknown','customer_count_unknown_reason':'No customer-count verification performed in identity discovery. Captured marketing counts are not adopted as verified adoption.','limitations':review['special_limitations'].get(name,review['special_limitations'].get(official,'Identity and advertised workflow only. Functionality, pricing, adoption, and economics require case research.'))}
    if key in pool_by_id:
        prior=pool_by_id[key]
        assert prior['official_name']==item['official_name'], 'Distinct names on one domain need explicit review'
        prior['observed_names']+=item['observed_names']
        prior['discovery_sources']+=item['discovery_sources']
        prior['aliases']=sorted(set(prior['aliases']+item['aliases']))
        prior['identity_evidence_ids']=list(dict.fromkeys(prior['identity_evidence_ids']+item['identity_evidence_ids']))
        merges.append({'canonical_identity_key':key,'merged_lead_name':name,'reason':'Same canonical product domain and matching official product identity after observed HTTP redirect.','evidence_ids':prior['identity_evidence_ids']})
    else:
        pool_by_id[key]=item
pool=sorted(pool_by_id.values(),key=lambda c:c['candidate_id'])
seed=plan['seed']; categories=sorted(plan['categories'])
def rank(c):
    return hashlib.sha256((seed+'\n'+c['candidate_id']).encode()).hexdigest()
def sortkey(c):
    return ({'E1':0,'E2':1,'E3':2}[c['small_company']['tier']],rank(c),c['candidate_id'])
eligible=sorted([c for c in pool if c['eligibility_status']=='eligible'],key=sortkey)
queues={cat:sorted([c for c in eligible if c['category']==cat],key=sortkey) for cat in categories}
selected=[]; deficits=[]
for cat in categories:
    chosen=queues[cat][:10]; selected+=chosen
    deficits += [cat]*(10-len(chosen))
chosen_ids={c['candidate_id'] for c in selected}
unused=[c for c in eligible if c['candidate_id'] not in chosen_ids]
transfers=[]
for deficit,c in zip(deficits,unused):
    selected.append(c); chosen_ids.add(c['candidate_id'])
    transfers.append({'unfilled_category':deficit,'source_category':c['category'],'candidate_id':c['candidate_id']})
selected_by_cat={cat:sorted([c for c in selected if c['category']==cat],key=sortkey) for cat in categories}
pilot_cats=sorted([cat for cat in categories if selected_by_cat[cat]],key=lambda cat:(-sum(c['small_company']['tier']=='E1' for c in selected_by_cat[cat]),cat))[:3]
pilot_cats.sort()
pilots=[selected_by_cat[cat][0] for cat in pilot_cats]
pilot_ids={c['candidate_id'] for c in pilots}
remaining={cat:[c for c in selected_by_cat[cat] if c['candidate_id'] not in pilot_ids] for cat in categories}
ordered=list(pilots)
while any(remaining.values()):
    for cat in categories:
        if remaining[cat]: ordered.append(remaining[cat].pop(0))
reserves=[c for c in eligible if c['candidate_id'] not in chosen_ids]

def product(c,i,alternate=False):
    pid=f'ALT-{i:03}' if alternate else f'{i:03}'
    return {'id':pid,'candidate_id':c['candidate_id'],'name':c['official_name'],'canonical_url':c['canonical_url'],'canonical_host':c['canonical_host'],'registrable_domain':c['registrable_domain'],'category':c['category'],'identity_status':'verified','identity_evidence_ids':c['identity_evidence_ids'],'aliases':c['aliases'],'selection_position':None if alternate else i,'pilot':not alternate and i<=len(pilots),'case_path':None if alternate else f'cases/{pid}/','small_company':c['small_company'],'customer_count':None,'customer_count_status':'unknown','stage_statuses':{'identity':'passed','research':'not_started','implementation':'not_started','execution':'not_started','evaluation':'not_started','review':'not_started'},'status_history':[{'stage':'identity','from':'not_started','to':'in_progress','at':c['retrieved_at_utc'],'actor':'terra','reason':'First-party public identity capture','evidence_ids':c['identity_evidence_ids']},{'stage':'identity','from':'in_progress','to':'passed','at':freeze['frozen_at_utc'],'actor':'terra','reason':'Reviewed official identity and advertised workflow, canonicalized and deduplicated. This is not acceptance of functionality.','evidence_ids':c['identity_evidence_ids']}],'replacement_reference':None,'limitations':c['limitations']}
products=[product(c,i) for i,c in enumerate(ordered,1)]
alternates=[product(c,i,True) for i,c in enumerate(reserves,1)]
unknown={'supplied_name':'norvjx ai','identity_status':'unresolved','candidate_id':None,'included_in_sample':False,'search_evidence_ids':[r['evidence_id'] for u,r in records.items() if 'norvjx' in u],'findings':'Four exact-name Google queries returned a static access fallback rather than usable results. Bing exact-name query returned unrelated cat-image results. No authoritative name/domain connection found in the inspected responses. This is not proof the product does not exist.','permitted_next_action':'Ask user for exact URL or screenshot, or inspect an additional authorized public search source. Do not silently substitute similarly spelled products.'}
registry={'schema_version':1,'task_id':'2.a','frozen_at_utc':freeze['frozen_at_utc'],'target_products':100,'selection_complete':len(products)==100,'selected_product_count':len(products),'alternate_count':len(alternates),'accepted_products':0,'deliverables_complete':False,'evidence_index_path':'discovery/evidence.json','products':products,'alternates':alternates,'replacement_history':[],'unresolved_leads':[unknown],'campaign_blockers':[] if len(products)==100 else [{'scope':'campaign','stage':'identity','cause':'Fewer than 100 independently eligible identities in bounded public discovery frame','permitted_next_action':'Extend public discovery frame with explicit revision and preserve original sample'}],'limitations':['Verified identity is not completed research or reproduction.','Small-company eligibility remains unknown except explicitly sourced tier E1 cases. No zero-user claims.','Selection is deterministic within a convenience discovery frame, not a market-representative random sample.','Observed redirects establish canonical landing identities, not legal acquisition history.','No company valuations, competitor executions, paid inference, or 24-hour completion claimed.']}
selection={'schema_version':1,'seed':seed,'algorithm':plan['algorithm'],'frozen_at_utc':freeze['frozen_at_utc'],'target':100,'selection_complete':len(products)==100,'candidate_pool_path':'discovery/candidate-pool.json','candidate_pool_sha256':digest(pool),'serialization':'UTF-8 json.dumps(ensure_ascii=False,sort_keys=True,separators=(comma,colon)) plus newline. Pool sorted by candidate_id.','lead_count':len(leads),'deduplicated_candidate_count':len(pool),'eligible_count':len(eligible),'excluded_count':len(pool)-len(eligible),'categories':plan['categories'],'quotas':{c:10 for c in categories},'eligible_counts':dict(collections.Counter(c['category'] for c in eligible)),'selected_counts':dict(collections.Counter(c['category'] for c in ordered)),'selected_size_tiers':dict(collections.Counter(c['small_company']['tier'] for c in ordered)),'rank_definition':'SHA256(UTF8(seed + newline + candidate_id)); order by size tier E1,E2,E3, lowercase rank_hex, candidate_id.','rankings':[{'candidate_id':c['candidate_id'],'category':c['category'],'size_tier':c['small_company']['tier'],'rank_hex':rank(c)} for c in eligible],'quota_transfers':transfers,'pilot_policy':'Rank represented categories by descending selected E1 count, then category code. Take first three categories. Within each, take smallest sort_key. Order these pilots by category code as 001-003. Remaining products use category round-robin, retaining within-category sort order.','pilot_categories':pilot_cats,'pilot_diversity_satisfied':len(pilot_cats)==3,'selected_order':[{'id':p['id'],'candidate_id':p['candidate_id'],'name':p['name'],'category':p['category'],'pilot':p['pilot']} for p in products],'alternate_order':[{'alternate_id':p['id'],'candidate_id':p['candidate_id'],'category':p['category']} for p in alternates],'replacement_policy':'Keep initial sample immutable. Next unused ranked alternate in same category, else next global alternate with explicit category transfer. Apply only through registry owner. Preserve replaced evidence; do not count replacements twice or replace because of unfavorable verdicts.','replacement_history':[],'deduplication_merges':merges,'public_suffix_list':psl,'discovery_frame_deviations':plan['frame_deviations'],'unresolved_name':unknown,'replay_command':'python3 research/ai-saas-100/discovery/build_registry.py --check'}

assert registrable('www.example.co.uk')=='example.co.uk'
assert registrable('a.b.github.io')=='b.github.io'
assert registrable('www.city.kawasaki.jp')=='city.kawasaki.jp'
assert registrable('www.ck')=='www.ck'
assert len({p['candidate_id'] for p in products})==len(products)
assert len({p['id'] for p in products})==len(products)
assert [p['id'] for p in products]==[f'{i:03}' for i in range(1,len(products)+1)]
assert not ({p['candidate_id'] for p in products}&{p['candidate_id'] for p in alternates})
for p in products+alternates:
    assert all(eid in by_eid and by_eid[eid]['status']==200 for eid in p['identity_evidence_ids'])
    assert p['customer_count'] is None
    assert all(v=='not_started' for k,v in p['stage_statuses'].items() if k!='identity')
for r in records.values():
    if r.get('capture_path'):
        assert hashlib.sha256((ROOT/r['capture_path']).read_bytes()).hexdigest()==r['capture_sha256']
outputs={D/'candidate-pool.json':pool,D/'evidence.json':{'schema_version':1,'sources':evidence},ROOT/'registry.json':registry,ROOT/'selection.json':selection}
check='--check' in sys.argv
for path,obj in outputs.items():
    if check:
        assert load(path)==obj, f'Deterministic replay mismatch: {path}'
    else:
        assert not path.exists(), f'Refusing to overwrite existing artifact: {path}'
        path.write_text(pretty(obj))
print(pretty({'mode':'check' if check else 'build','selected':len(products),'alternates':len(alternates),'eligible':len(eligible),'excluded':len(pool)-len(eligible),'pool_sha256':digest(pool),'pilot_products':[{'id':p['id'],'name':p['name'],'category':p['category']} for p in products if p['pilot']],'evidence_records':len(evidence),'assertions':'passed'}))
