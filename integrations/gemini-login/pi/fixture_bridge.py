"""Deterministic transport fixture, not a Gemini model or live proof."""
import json
import sys
request=json.load(sys.stdin)
if request.get('messages',[])[-1].get('role')=='tool':
    text=request['messages'][-1]['content']
    result={'model':request['model'],'content':'FIXTURE_READ_RESULT: '+text,'tool_calls':[],'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}
else:
    result={'model':request['model'],'content':'','tool_calls':[{'id':'fixture-r1','type':'function','function':{'name':'read','arguments':json.dumps({'path':'host-read-fixture.txt'})}}],'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}
json.dump(result,sys.stdout)
