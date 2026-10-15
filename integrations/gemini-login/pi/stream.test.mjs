import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const require=createRequire(import.meta.url);
const {createJiti}=require('jiti');
const jiti=createJiti(import.meta.url);
const {streamLogin}=await jiti.import('./index.ts');
process.env.GEMINI_LOGIN_BRIDGE=fileURLToPath(new URL('./fixture_bridge.py',import.meta.url));
const model={id:'gemini-4-argon',provider:'gemini-login'};
const context={messages:[
  {role:'system',content:'Use read.',timestamp:1,toolsAdded:[{name:'read',description:'Read',parameters:{type:'object'}}]},
  {role:'user',content:'Read fixture.',timestamp:2},
]};

test('abort inside onResponse emits aborted error, never tool dispatch events',async()=>{
  const controller=new AbortController();
  const stream=streamLogin(model,context,{signal:controller.signal,onResponse:()=>controller.abort()});
  const events=[]; for await(const event of stream) events.push(event);
  const result=await stream.result();
  assert.equal(result.stopReason,'aborted');
  assert.equal(events.at(-1).type,'error');
  assert.ok(!events.some(e=>e.type.startsWith('toolcall') || e.type==='done'));
});

test('abort inside provider hook cannot become a successful reply',async()=>{
  const controller=new AbortController();
  const stream=streamLogin(model,context,{signal:controller.signal,onProviderStreamEvent:()=>controller.abort()});
  const events=[]; for await(const event of stream) events.push(event);
  assert.equal((await stream.result()).stopReason,'aborted');
  assert.ok(!events.some(e=>e.type==='start' || e.type==='done'));
});
