import test from 'node:test';
import assert from 'node:assert/strict';
import { toHostMessages, toHostTools, parseBridgeOutput, effortFor, validateHostCalls } from './protocol.mjs';

test('Pi tool calls and actual results remain paired in replay', () => {
  const messages = toHostMessages([
    {role:'system',content:'base'},
    {role:'user',content:[{type:'text',text:'read the file'}]},
    {role:'assistant',content:[{type:'text',text:'checking'},{type:'toolCall',id:'r1',name:'read',arguments:{path:'source.txt'}}]},
    {role:'toolResult',toolCallId:'r1',toolName:'read',content:[{type:'text',text:'real contents'}],isError:false},
  ], 'complete system');
  assert.equal(messages[0].content,'complete system');
  assert.deepEqual(messages[2].tool_calls,[{id:'r1',type:'function',function:{name:'read',arguments:'{"path":"source.txt"}'}}]);
  assert.deepEqual(messages[3],{role:'tool',tool_call_id:'r1',name:'read',content:'real contents'});
});

test('unsupported image content fails instead of disappearing', () => {
  assert.throws(()=>toHostMessages([{role:'user',content:[{type:'image',data:'xxx',mimeType:'image/png'}]}],''),/image/i);
});

test('host tools keep exact schema and names', () => {
  assert.deepEqual(toHostTools([{name:'read',description:'Read file',parameters:{type:'object',properties:{path:{type:'string'}}}}]),
    [{type:'function',function:{name:'read',description:'Read file',parameters:{type:'object',properties:{path:{type:'string'}}}}}]);
});

test('error output cannot masquerade as an answer', () => {
  assert.throws(()=>parseBridgeOutput('{"error":"license rejected"}',0),/license rejected/);
  assert.throws(()=>parseBridgeOutput('{"content":"looks fine","tool_calls":[]}',1),/exit 1/);
});

test('malformed or empty answers fail closed', () => {
  assert.throws(()=>parseBridgeOutput('not json',0),/JSON/);
  assert.throws(()=>parseBridgeOutput('{"content":"","tool_calls":[]}',0),/empty/);
});

test('real response and usage are preserved', () => {
  const data={model:'gemini-4-argon',content:'OK',tool_calls:[],usage:{prompt_tokens:12,completion_tokens:3,total_tokens:15}};
  assert.deepEqual(parseBridgeOutput(JSON.stringify(data),0),data);
});

test('undeclared tools and nonobject arguments never reach host dispatch', () => {
  const tool = {id:'x',type:'function',function:{name:'write',arguments:'{}'}};
  assert.throws(()=>validateHostCalls({tool_calls:[tool]},[{name:'read'}]),/undeclared/i);
  tool.function.name='read'; tool.function.arguments='[]';
  assert.throws(()=>validateHostCalls({tool_calls:[tool]},[{name:'read'}]),/object/i);
  tool.function.arguments='{"path":"source.txt"}';
  assert.doesNotThrow(()=>validateHostCalls({tool_calls:[tool]},[{name:'read'}]));
});

test('numeric tool IDs and malformed usage are rejected at the boundary', () => {
  const data={model:'gemini-4-argon',content:'OK',tool_calls:[],usage:{prompt_tokens:12,completion_tokens:3,total_tokens:15}};
  data.usage.prompt_tokens=-1;
  assert.throws(()=>parseBridgeOutput(JSON.stringify(data),0),/usage/i);
  data.usage.prompt_tokens=12; data.usage.completion_tokens='3';
  assert.throws(()=>parseBridgeOutput(JSON.stringify(data),0),/usage/i);
  const call={id:7,type:'function',function:{name:'read',arguments:'{}'}};
  assert.throws(()=>validateHostCalls({tool_calls:[call]},[{name:'read'}]),/invalid/i);
});

test('thinking maps only to supported native efforts', () => {
  assert.equal(effortFor('high'),'high');
  assert.equal(effortFor('medium'),'medium');
  assert.equal(effortFor('off'),'low');
  assert.equal(effortFor('xhigh'),'high');
});
