// Real installed Pi, isolated resources and a deterministic in-process provider.
import assert from 'node:assert/strict';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
const packageDir = process.env.PI_AGENT_PACKAGE;
assert(packageDir, 'Set PI_AGENT_PACKAGE to the installed pi-coding-agent directory');
const api = await import(pathToFileURL(join(packageDir, 'dist/index.js')));
const { loadExtensions } = await import(pathToFileURL(join(packageDir, 'dist/core/extensions/loader.js')));
const { createAssistantMessageEventStream } = await import(pathToFileURL(join(packageDir, 'node_modules/@earendil-works/pi-ai/dist/index.js')));
const root = resolve(import.meta.dirname, '../../..');
const extension = process.env.SELF_COMPACT_EXTENSION
 ? resolve(root, process.env.SELF_COMPACT_EXTENSION)
 : join(root, 'extensions/self-compact/self-compact.ts');
const scratch = join(import.meta.dirname, '.runtime'); mkdirSync(scratch, { recursive: true });
const loaded = await loadExtensions([extension], root);
assert.equal(loaded.errors.length, 0, JSON.stringify(loaded.errors));
assert.equal(loaded.extensions.length, 1);
assert(loaded.extensions[0].tools.has('self_compaction'));
const flags = Object.fromEntries(process.argv.slice(2).map(value => [value.slice(0,value.indexOf('=')),value.slice(value.indexOf('=')+1)]));
for (const [name,value] of Object.entries(flags)) loaded.runtime.flagValues.set(name,value);
const loader = {
 getExtensions: () => loaded,
 getSkills: () => ({skills:[],diagnostics:[]}), getPrompts: () => ({prompts:[],diagnostics:[]}),
 getThemes: () => ({themes:[],diagnostics:[]}), getAgentsFiles: () => ({agentsFiles:[]}),
 getSystemPrompt: () => 'Offline deterministic integration test. Use self_compaction once.',
 getSystemPromptSource: () => undefined, getAppendSystemPrompt: () => [], getAppendSystemPromptSources: () => [],
 extendResources() {}, async reload() {},
};
const runtime = await api.ModelRuntime.create({ authPath:join(scratch,'auth.json'),modelsPath:null,modelsStorePath:join(scratch,'models.json'),refreshOnCreate:false,allowModelNetwork:false });
let calls = 0, summaryCalls = 0, resumed = false;
const requests = [], errors = [], widgets = [];
const note = 'Goal: finish meter. Done: parser. Exact path: /project/a.ts. Tests: 60 passed. Next: verify meter.';
runtime.registerProvider('self-compact-offline', {
 api:'offline-fixture',baseUrl:'http://unused.invalid',apiKey:'offline-no-network',
 models:[{id:'fixture-1m',name:'Offline 1M',reasoning:false,input:['text'],contextWindow:1000000,maxTokens:8192,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}],
 streamSimple(model,context) {
  const stream = createAssistantMessageEventStream();
  const isSummary = !context.tools?.length;
  requests.push({isSummary,systemPrompt:context.systemPrompt,messages:context.messages});
  let content, stopReason;
  if(isSummary) {
   summaryCalls++;
   assert.equal(context.systemPrompt, flags['compact-prompt'] ?? readFileSync(join(root,'.pi/self-compact/USER_PROMPT_COMPACTION_MESSAGE_.md'),'utf8').trim());
   assert(JSON.stringify(context.messages).includes(note));
   content=[{type:'text',text:`Goal: finish meter. Completed parser; tests passed. Next: verify meter. Saved note: ${note}`}]; stopReason='stop';
  } else if(calls++ === 0) {
   content=[{type:'toolCall',id:'compact-tool-1',name:'self_compaction',arguments:{note_to_self:note}}]; stopReason='toolUse';
  } else { resumed=true; content=[{type:'text',text:'Resumed from summary. Verified meter; did not repeat parser work.'}]; stopReason='stop'; }
  const output = {role:'assistant',content,api:model.api,provider:model.provider,model:model.id,usage:{input:100,output:30,cacheRead:0,cacheWrite:0,totalTokens:130,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason,timestamp:Date.now()};
  queueMicrotask(()=>{stream.push({type:'start',partial:output});stream.push({type:'done',reason:stopReason,message:output});stream.end();});
  return stream;
 }
});
const manager = api.SessionManager.inMemory(root);
// An older turn gives Pi a valid compaction cut point at a tiny keepRecentTokens.
manager.appendMessage({role:'user',content:'Earlier work: parser implemented and verified. '.repeat(100),timestamp:Date.now()});
manager.appendMessage({role:'assistant',content:[{type:'text',text:'Completed parser; next step meter. '.repeat(100)}],api:'offline-fixture',provider:'self-compact-offline',model:'fixture-1m',usage:{input:100,output:100,cacheRead:0,cacheWrite:0,totalTokens:200,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:'stop',timestamp:Date.now()});
const settings=api.SettingsManager.inMemory({compaction:{enabled:false,reserveTokens:100,keepRecentTokens:100},retry:{enabled:false},quietStartup:true});
const {session}=await api.createAgentSession({cwd:root,agentDir:scratch,modelRuntime:runtime,model:runtime.getModel('self-compact-offline','fixture-1m'),resourceLoader:loader,sessionManager:manager,settingsManager:settings,noTools:'builtin'});
await session.bindExtensions({onError:error=>errors.push(error),uiContext:{hasUI:true,setWidget:(_key,lines)=>widgets.push(lines),notify:()=>{},setStatus:()=>{}}});
if(flags['compact-soft-at']==='invalid') {
 await session.prompt('check invalid config');
 assert(widgets.flat().some(x=>x.includes('invalid configuration')));
 assert.equal(summaryCalls,0); session.dispose();
 console.log(JSON.stringify({result:'PASS',variant:'invalid rejected',extensions:loaded.extensions.length,errors})); process.exit(0);
}
await session.prompt('Continue with the meter; compact first.');
const deadline=Date.now()+5000;
while(Date.now()<deadline && !(resumed && summaryCalls===1 && !session.isStreaming)) await new Promise(r=>setTimeout(r,20));
const branch=manager.getBranch();
assert.equal(errors.length,0,JSON.stringify(errors));
assert.equal(summaryCalls,1,JSON.stringify({calls,summaryCalls,branch}));
assert(resumed,'must automatically resume');
assert(branch.some(e=>e.type==='custom' && e.customType==='self-compact-note'));
assert(branch.some(e=>e.type==='compaction' && e.summary.includes(note)));
assert(branch.some(e=>e.type==='message' && e.message.role==='toolResult' && e.message.toolName==='self_compaction'));
assert(requests.filter(r=>!r.isSummary).at(-1).messages.some(m=>JSON.stringify(m).includes('Saved note:')),'resume sees compacted summary');
if(flags['compact-soft-at']==='10') assert(widgets.flat().some(x=>x.includes('Automatic compaction paused')));
session.dispose();
console.log(JSON.stringify({result:'PASS',flags,extensions:loaded.extensions.length,registeredFlags:[...loaded.extensions[0].flags.keys()],summaryCalls,resumed,modelCalls:calls,errors,widget:widgets[0],finalWidget:widgets.at(-1)},null,2));
