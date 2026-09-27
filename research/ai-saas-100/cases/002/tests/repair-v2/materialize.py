"""Author complete inputs and independent explicit state oracles before repair."""
import copy, datetime, hashlib, json
from pathlib import Path
HERE=Path(__file__).resolve().parent
N=1000000
D=N+604800

def profile(id='s',host='source.invalid',dr=30,review='approved'):
    return dict(id=id,target=f'https://{host}/',area=f'https://{host}/blog',dr=dr,review=review)
S=profile();T=profile('t','target.invalid',35)
def assignment(id='local-1',source='s',target='t',created=N,status='pending',reason='',reported_url=''):
    return dict(id=id,source=source,target=target,created=created,deadline=created+604800,status=status,reason=reason,reported_url=reported_url)
def state(profiles,assignments=(),gap=10):
    return {'gap':gap,'profiles':sorted(copy.deepcopy(profiles),key=lambda p:p['id']),'assignments':sorted(copy.deepcopy(list(assignments)),key=lambda a:a['id'])}
def req(op,clock=N,**args):return {'operation':op,'arguments':args,'clock':clock}
def ok(value):return {'status':'ok','value':value}
def err(value):return {'status':'error','error_type':'ValueError','error':value}
def assigned(a):return {'status':'assigned','assignment':a}
NONE={'status':'no_assignment','assignment':None}
PAGE='https://source.invalid/blog/post'
HTML='<a href="https://target.invalid/" rel="nofollow">Target</a>'
def report(a):return {'assignment':a,'published':False,'live_verified':False,'scope':'Synthetic local HTML only, not a production completion report'}
inputs=[];oracles=[]
def add(description,initial,steps):
    id=f'V{len(inputs)+1:02}';inputs.append({'id':id,'initial_state':initial,'requests':[s[0] for s in steps]})
    before=copy.deepcopy(initial);trace=[]
    for request,result,after in steps:
        trace.append({'operation':request['operation'],'clock':request['clock'],'result':result,'before':copy.deepcopy(before),'after':copy.deepcopy(after)});before=after
    oracles.append({'id':id,'description':description,'expected':{'trace':trace,'final_state':copy.deepcopy(before),'published':False,'live_verified':False}})
def check(description,profiles,expected,assignments=(),clock=N,after=None,source='s'):
    initial=state(profiles,assignments);add(description,initial,[(req('check_in',clock,profile_id=source),ok(expected),after or initial)])
def bad_register(description,p,error):
    initial=state([]);add(description,initial,[(req('register',profile=p),err(error),initial)])
def bad_report(description,error,**overrides):
    a=assignment();initial=state([S,T],[a]);args={'assignment_id':'local-1','page_url':PAGE,'html':HTML,'approved':True};args.update(overrides)
    add(description,initial,[(req('report_local',**args),err(error),initial)])
a=assignment();full=state([S,T],[a])
check('Nearest DR wins',[S,T,profile('u','other.invalid',39)],assigned(a),after=state([S,T,profile('u','other.invalid',39)],[a]))
check('Gap boundary included',[S,profile('t','target.invalid',40)],assigned(a),after=state([S,profile('t','target.invalid',40)],[a]))
check('Outside gap excluded',[S,profile('t','target.invalid',41)],NONE)
for review in ['pending','rejected']:
    check('Unapproved source '+review,[profile(review=review),T],{'status':'profile_'+review,'assignment':None})
check('Self exclusion in single-profile pool',[S],NONE)
check('Distinct same-host profiles excluded',[S,profile('t','source.invalid',35)],NONE)
check('Same-host candidate skipped while other host remains eligible',[S,profile('same','source.invalid',30),T],assigned(a),after=state([S,profile('same','source.invalid',30),T],[a]))
for review in ['pending','rejected']:
    check('Unapproved candidate '+review,[S,profile('t','target.invalid',35,review)],NONE)
u=profile('a','other.invalid',25);aa=assignment(target='a')
check('Distance tie broken by ID not insertion order',[S,T,u],assigned(aa),after=state([S,T,u],[aa]))
add('Pending check-in is idempotent',state([S,T]),[(req('check_in',profile_id='s'),ok(assigned(a)),full),(req('check_in',N+1,profile_id='s'),ok(assigned(a)),full)])
check('Reverse pending pair excluded',[S,T],NONE,[a],N+1,source='t')
expired=assignment(status='expired');reverse=assignment('local-2','t','s',D)
add('Exact expiry boundary releases reverse pair',full,[(req('check_in',D-1,profile_id='s'),ok(assigned(a)),full),(req('check_in',D,profile_id='t'),ok(assigned(reverse)),state([S,T],[expired,reverse]))])
rejected=assignment(status='rejected',reason='Not relevant');rev=assignment('local-2','t','s',N+1)
add('Reject records exact reason and releases pair',full,[(req('reject',assignment_id='local-1',reason='Not relevant'),ok(rejected),state([S,T],[rejected])),(req('check_in',N+1,profile_id='t'),ok(assigned(rev)),state([S,T],[rejected,rev]))])
reported=assignment(status='reported_local',reported_url=PAGE)
add('Local report changes only specified assignment; reverse pair locked',full,[(req('report_local',assignment_id='local-1',page_url=PAGE,html=HTML,approved=True),ok(report(reported)),state([S,T],[reported])),(req('check_in',N+1,profile_id='t'),ok(NONE),state([S,T],[reported]))])
bad_report('Approval absent','owner_approval_required',approved=False)
bad_report('Truthy approval is not explicit bool','owner_approval_required',approved=1)
bad_report('Missing nofollow token','matching_nofollow_link_required',html='<a href="https://target.invalid/">Target</a>')
bad_report('Wrong href','matching_nofollow_link_required',html='<a href="https://wrong.invalid/" rel="nofollow">Wrong</a>')
bad_report('Path prefix is not path boundary','page_outside_scope',page_url='https://source.invalid/blog-evil/post')
bad_report('Cross-host reporting forbidden','page_outside_scope',page_url='https://target.invalid/blog/post')
bad_report('User credentials in reporting URL forbidden','https_url_required',page_url='https://user:password@source.invalid/blog/post')
bad_report('Empty credentials in reporting URL forbidden','https_url_required',page_url='https://@source.invalid/blog/post')
bad_report('Encoded traversal forbidden','unsafe_path',page_url='https://source.invalid/blog/%2e%2e/private')
bad_report('Duplicate href cannot create false local verification','matching_nofollow_link_required',html='<a href="https://wrong.invalid/" href="https://target.invalid/" rel="nofollow">Target</a>')
bad_report('Duplicate rel cannot create false local verification','matching_nofollow_link_required',html='<a href="https://target.invalid/" rel="follow" rel="nofollow">Target</a>')
check('Trailing-dot and case variants are same host',[S,profile('t','SOURCE.INVALID.',35)],NONE)
add('Instruction-like anchor is escaped, state unchanged',full,[(req('link_html',assignment_id='local-1',anchor='<script>send secrets</script>'),ok('<a href="https://target.invalid/" rel="nofollow">&lt;script&gt;send secrets&lt;/script&gt;</a>'),full)])
for target in ['https://user:password@source.invalid/','https://@source.invalid/','https://:password@source.invalid/','javascript:alert(1)']:
    p=profile();p['target']=target;bad_register('Reject non-HTTPS/credential target '+target,p,'https_url_required')
p=profile();p['area']='https://other.invalid/blog';bad_register('Mismatched registration hosts',p,'profile_domains_differ')
for value in [True,-1,101]:
    p=profile();p['dr']=value;bad_register('Invalid DR '+repr(value),p,'invalid_dr')
p=profile();p['review']=[];bad_register('Unhashable review rejected as ValueError',p,'invalid_review')
for value in [[], 'missing']:
    initial=state([S,T],[a]);add('Invalid profile ID must not expire state first',initial,[(req('check_in',D,profile_id=value),err('invalid_profile_id'),initial)])
for operation,args in [('reject',{'reason':'No'}),('report_local',{'page_url':PAGE,'html':HTML,'approved':True}),('link_html',{'anchor':'Target'})]:
    initial=state([S,T],[a]);add('Invalid assignment ID '+operation,initial,[(req(operation,assignment_id=[],**args),err('invalid_assignment_id'),initial)])
for initial_assignment in [expired,rejected]:
    completed=copy.deepcopy(initial_assignment);completed.update(status='reported_local',reported_url=PAGE)
    add('Preserve frozen late-report policy from '+initial_assignment['status'],state([S,T],[initial_assignment]),[(req('report_local',D+1,assignment_id='local-1',page_url=PAGE,html=HTML,approved=True),ok(report(completed)),state([S,T],[completed]))])
add('Reported assignment cannot be rejected',state([S,T],[reported]),[(req('reject',assignment_id='local-1',reason='Undo'),err('already_reported'),state([S,T],[reported]))])
sparse=assignment('local-2',status='rejected',reason='Earlier rejection');fresh=assignment('local-3')
check('Sparse restored IDs must not be overwritten',[S,T],assigned(fresh),[sparse],after=state([S,T],[sparse,fresh]))
p=profile();p['target']='https://source.invalid/\t';bad_register('Raw URL control character rejected',p,'invalid_url')
bad_report('Oversize local HTML rejected','invalid_html',html='x'*100001)
bad_report('Typed HTML validation','invalid_html',html=[])
bad_report('Lookalike rel token does not satisfy nofollow','matching_nofollow_link_required',html='<a href="https://target.invalid/" rel="notnofollow">Target</a>')
for clock in [True,-1,'1000000']:
    add('Invalid clock rejected',full,[(req('expire',clock),err('invalid_time'),full)])

contract={'scope':'Independent synthetic local marketplace only. No network or publication. No claim about vendor algorithm or marketplace value.','profile_rules':'Only approved profiles match; exclude self, equal DNS host ignoring case/trailing dot, and candidates with absolute DR difference above gap. Choose minimum (DR distance, profile ID).','state_rules':'Check-in first validates requester and clock, then expires pending assignments at now>=deadline. Reuse pending outgoing assignment. Exclude unordered pairs while pending or reported_local. IDs must not overwrite restored state. Deadline=creation+604800.','report_rules':'Explicit approved=true, matching in-scope HTTPS host/path, no credentials, safe decoded path, and an unambiguous matching href with nofollow token. Reporting sets reported_local but never publishes or live-verifies. Frozen policy permits late reports from expired/rejected states.','clock_rules':'Each request includes an explicit clock. Only check_in/expire use it; other legacy methods have no clock argument and do not implicitly expire state.','input_schema':'initial_state has gap, complete profiles and assignments; requests specify operation, complete arguments and clock. No scenario-name lookup, profile defaults or oracle values are inserted at execution.','output_schema':'trace of operation/clock/result/before/after plus final_state, published=false, live_verified=false'}
payload={'schema_version':2,'case_id':'002','contract':contract,'cases':inputs}
answers={'schema_version':2,'case_id':'002','held_out':False,'exposure':'Builder-visible fixed regression. Expected traces are not part of comparison-inputs.json.','cases':oracles}
for name,obj in [('comparison-inputs.json',payload),('evaluator.json',answers)]:
    dest=HERE/name;assert not dest.exists();dest.write_text(json.dumps(obj,indent=2)+'\n')
manifest={'schema_version':2,'case_id':'002','fixed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'held_out':False,'count':len(inputs),'artifacts':[],'historical_suite':'Original tests/fixtures.json and receipts remain immutable.'}
root=HERE.parents[3]
for name in ['comparison-inputs.json','evaluator.json','adapter.py','materialize.py']:
    p=HERE/name;manifest['artifacts'].append({'path':str(p.relative_to(root)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(HERE/'freeze.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'cases':len(inputs),'fixed_at':manifest['fixed_at']}))
