import { homedir } from 'node:os';
import { join } from 'node:path';
import {
  createAssistantMessageEventStream,
  getCurrentSystemPrompt,
  getCurrentTools,
} from '@earendil-works/pi-ai/compat';
import type { ExtensionAPI } from '@earendil-works/pi-coding-agent';
import { effortFor, toHostMessages, toHostTools, validateHostCalls } from './protocol.mjs';
import { invokeBridge } from './transport.mjs';

const API = 'gemini-login-cli';
const bridge = () => process.env.GEMINI_LOGIN_BRIDGE || join(homedir(),'.local/share/gemini-login-bridge/gemini_login_bridge.py');

const assertActive = (signal?: AbortSignal) => { if(signal?.aborted) throw new Error('Request aborted'); };

export function streamLogin(model: any, context: any, options: any = {}) {
  const stream = createAssistantMessageEventStream();
  const message: any = {
    role:'assistant', content:[], api:API, provider:model.provider, model:model.id,
    usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},
    stopReason:'stop', timestamp:Date.now(),
  };
  (async()=>{
    try {
      let request: any={
        model:model.id,
        messages:toHostMessages(context.messages,getCurrentSystemPrompt(context.messages)),
        tools:toHostTools(getCurrentTools(context.messages)),
        reasoning_effort:effortFor(options.reasoning), timeout_seconds:180,
      };
      const replacement=await options.onPayload?.(request,model);
      assertActive(options.signal);
      if(replacement!==undefined) request=replacement;
      const result=await invokeBridge(request,options.signal,{script:bridge()});
      assertActive(options.signal);
      if(result.model!==model.id) throw new Error('Gemini login bridge returned a different model.');
      validateHostCalls(result,getCurrentTools(context.messages));
      await options.onResponse?.({status:200,headers:{}},model);
      assertActive(options.signal);
      await options.onProviderStreamEvent?.(result,model);
      assertActive(options.signal);
      stream.push({type:'start',partial:message});
      if(result.content) {
        const index=message.content.length;
        message.content.push({type:'text',text:''});
        stream.push({type:'text_start',contentIndex:index,partial:message});
        message.content[index].text=result.content;
        stream.push({type:'text_delta',contentIndex:index,delta:result.content,partial:message});
        stream.push({type:'text_end',contentIndex:index,content:result.content,partial:message});
      }
      for(const call of result.tool_calls) {
        const index=message.content.length;
        const toolCall={type:'toolCall',id:call.id,name:call.function.name,arguments:JSON.parse(call.function.arguments)};
        message.content.push(toolCall);
        stream.push({type:'toolcall_start',contentIndex:index,partial:message});
        stream.push({type:'toolcall_delta',contentIndex:index,delta:call.function.arguments,partial:message});
        stream.push({type:'toolcall_end',contentIndex:index,toolCall,partial:message});
      }
      const usage=result.usage ?? {};
      const cached=usage.prompt_tokens_details?.cached_tokens ?? 0;
      message.usage={input:Math.max(0,(usage.prompt_tokens ?? 0)-cached),output:usage.completion_tokens ?? 0,cacheRead:cached,cacheWrite:0,totalTokens:usage.total_tokens ?? 0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}};
      message.responseId=result.conversation_id;
      message.providerThinkingLevel=request.reasoning_effort;
      message.stopReason=result.tool_calls.length ? 'toolUse' : 'stop';
      stream.push({type:'done',reason:message.stopReason,message});
    } catch(error) {
      message.stopReason=options.signal?.aborted ? 'aborted' : 'error';
      message.errorMessage=error instanceof Error ? error.message : String(error);
      stream.push({type:'error',reason:message.stopReason,error:message});
    } finally { stream.end(); }
  })();
  return stream;
}

export default function(pi: ExtensionAPI) {
  const models=['gemini-4-argon','gemini-3.8-flash'].map(id=>({
    id,name:`${id==='gemini-4-argon'?'Gemini 4 Argon':'Gemini 3.8 Flash'} (Google login · official CLI)`,
    api:API as any,baseUrl:'cli://antigravity',reasoning:true,input:['text'] as any,
    cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:1_000_000,maxTokens:65536,
  }));
  for(const provider of ['gemini-login','google-gemini-cli']) {
    pi.registerProvider(provider as any,{
      name:'Gemini (existing Google login · official Antigravity CLI)',
      api:API as any,apiKey:'managed-by-official-cli',baseUrl:'cli://antigravity',
      models,streamSimple:streamLogin,
    } as any);
  }
}
