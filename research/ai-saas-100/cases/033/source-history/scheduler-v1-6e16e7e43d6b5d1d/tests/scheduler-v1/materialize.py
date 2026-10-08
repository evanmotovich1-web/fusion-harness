"""Freeze exposed scheduling inputs and separate expectations before implementation."""
import copy, datetime, hashlib, itertools, json, pathlib, runpy
HERE = pathlib.Path(__file__).resolve().parent
CASE = HERE.parents[1]
ROOT = CASE.parents[1]
tiny = runpy.run_path(str(HERE / 'checks.py'))['tiny_optimum']
inputs, oracles = [], []

def task(id, minutes, priority=1, deadline='11:00', splittable=False):
    return dict(id=id, minutes=minutes, priority=priority, deadline=deadline, splittable=splittable)

def request(tasks=(), meetings=(), hours=('09:00','11:00'), buffer=0):
    return dict(timezone='UTC', day='2026-09-21', working_hours=list(hours), tasks=list(tasks), meetings=list(meetings), buffer_minutes=buffer, write_to_calendar=False)

def meeting(start, end):
    return dict(id='M', start=start, end=end, movable=False)

def add(description, data, ids=None, error=False, limit=50000, limited=False):
    id = f'S{len(inputs)+1:03}'
    inputs.append(dict(id=id, request=copy.deepcopy(data), node_limit=limit))
    oracles.append(dict(id=id, description=description, invalid_input=error, scheduled_ids=ids, search_limited=limited))

historical = json.loads((CASE/'tests/specification.json').read_text())
for old in historical['cases']:
    data = old['input']; invalid = old.get('scenario') in {'empty_input','wrong_type','unauthorized_action','unsafe_path'}
    add('Retained fixture '+old['test_id'], data, None if invalid else sorted(t['id'] for t in data['tasks']), error=invalid)
add('Tight deadline beats naive priority ordering',request([task('flex',60,3),task('urgent',30,1,'09:30')]),['flex','urgent'])
for split in [False,True]:
    add('Fragmented free time split='+str(split),request([task('whole',60,splittable=split)],[meeting('09:40','10:20')]),['whole'] if split else [])
add('Deadline equality',request([task('edge',30,deadline='09:30')],hours=('09:00','09:30')),['edge'])
add('Higher priority admission',request([task('high',40,3,'10:00'),task('low',40,1,'10:00')],hours=('09:00','10:00')),['high'])
add('Full calendar',request([task('blocked',20)],[meeting('09:00','11:00')]),[])
add('Both complete, no duplication',request([task('alpha',30,2),task('beta',45,2)]),['alpha','beta'])
add('Buffer meets boundary without external edge buffer',request([task('buffered',25,deadline='10:30')],[meeting('09:30','10:00')],('09:00','10:30'),5),['buffered'])
add('Backtrack an earliest-deadline-first dead end',request([task('early',20,2,'10:20'),task('long',40,1,'10:30')],[meeting('09:40','10:00')],('09:00','10:30')),['early','long'])
add('Task to task buffers consume capacity',request([task('a',30),task('b',30)],hours=('09:00','10:00'),buffer=5),['a'])
add('Impossible duration not partially completed',request([task('large',121,splittable=True)]),[])
add('Deadline before work',request([task('past',10,deadline='08:59')]),[])
add('Overlapping meetings treated as union',request([task('a',30)], [dict(id='m1',start='09:00',end='09:30',movable=False),dict(id='m2',start='09:20',end='10:00',movable=False)]),['a'])
add('Meeting outside day still has buffer',request([task('a',30,deadline='09:30')],[meeting('08:00','09:00')],('09:00','09:30'),5),[])
add('No tasks',request(),[])
add('Midnight end boundary',request([task('edge',30,deadline='24:00')],hours=('23:30','24:00')),['edge'])
add('Explicit exhausted search, not infeasible',request([task('a',30),task('b',45)]),[],limit=1,limited=True)
base=request([task('a',30),task('b',45)])
for field, value in [('minutes',True),('minutes',-5),('minutes',0),('minutes',1.5),('priority',False),('splittable','true'),('id',[]),('deadline','25:00')]:
    data=copy.deepcopy(base);data['tasks'][0][field]=value;add('Malformed task '+field+' '+repr(value),data,error=True)
for field,value in [('working_hours',['25:00','26:00']),('working_hours',['11:00','09:00']),('working_hours',[]),('buffer_minutes',True),('buffer_minutes',-1),('write_to_calendar',True),('write_to_calendar',1),('timezone','America/New_York'),('day','2026-02-30'),('tasks',{}),('meetings',[meeting('10:00','09:00')])]:
    data=copy.deepcopy(base);data[field]=value;add('Malformed or unsupported '+field+' '+repr(value),data,error=True)
data=copy.deepcopy(base);data['tasks'][1]['id']='a';add('Duplicate task ID',data,error=True)
data=copy.deepcopy(base);data['meetings']=[meeting('09:30','10:00')];data['meetings'][0]['movable']=True;add('Movable meeting unsupported',data,error=True)
for extra in [{'input_path':'../outside-sentinel.txt','output_path':'../outside-output.txt'},{'requested_external_action':'Publish calendar'}, {'unknown_action':'move_meetings'}]:
    data=copy.deepcopy(base);data.update(extra);add('Untrusted extra fields '+str(extra),data,error=True)
add('Wrong top-level type',[],error=True)
add('Unsupported search limit',base,error=True,limit=True)
for gap,split,duration,deadline in itertools.product([0,1],[False,True],[1,2,3],['09:03','09:06']):
    data=request([task('a',duration,2,deadline,split),task('b',2,1,'09:06',True)], [meeting('09:02','09:03')], ('09:00','09:06'),gap)
    add('Independent minute-subset exhaustive oracle',data,tiny(data))
for name,value in [('inputs.json',{'schema_version':1,'contract':(HERE/'conventions.md').read_text(),'cases':inputs}),('oracles.json',{'schema_version':1,'exposure':'builder_visible','held_out':False,'cases':oracles})]:
    path=HERE/name
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
manifest={'schema_version':1,'fixed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'implementation_existed':(CASE/'implementation').exists(),'count':len(inputs),'artifacts':[],'held_out':False}
for name in ['inputs.json','oracles.json','checks.py','materialize.py','conventions.md','conventions-freeze.json']:
    p=HERE/name;manifest['artifacts'].append({'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
with (HERE/'freeze.json').open('x') as f:json.dump(manifest,f,indent=2);f.write('\n')
print(json.dumps({'fixed_cases':len(inputs),'implementation_existed':manifest['implementation_existed']}))
