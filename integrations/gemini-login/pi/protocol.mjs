export function effortFor(level) {
  if (level === 'medium') return 'medium';
  if (['off','minimal','low'].includes(level)) return 'low';
  return 'high';
}

function textContent(content) {
  if (typeof content === 'string') return content;
  const out=[];
  for (const part of content ?? []) {
    if (part.type === 'text') out.push(part.text ?? '');
    else if (part.type === 'image' || part.type === 'image_url') throw new Error('Gemini login bridge does not yet support image input. Use the native Gemini app for images.');
    else if (!['thinking','toolCall'].includes(part.type)) throw new Error(`Unsupported Gemini content block: ${part.type}`);
  }
  return out.join('\n');
}

export function toHostMessages(transcript, systemPrompt) {
  const out = systemPrompt ? [{role:'system',content:systemPrompt}] : [];
  for (const message of transcript) {
    if (message.role === 'system') continue;
    if (message.role === 'toolResult') {
      out.push({role:'tool',tool_call_id:message.toolCallId,name:message.toolName,content:textContent(message.content)});
    } else if (message.role === 'assistant') {
      const calls=(message.content ?? []).filter(p=>p.type==='toolCall').map(p=>({id:p.id,type:'function',function:{name:p.name,arguments:JSON.stringify(p.arguments)}}));
      const item={role:'assistant',content:textContent(message.content)};
      if (calls.length) item.tool_calls=calls;
      out.push(item);
    } else if (message.role === 'user') out.push({role:'user',content:textContent(message.content)});
    else throw new Error(`Unsupported Pi transcript role: ${message.role}`);
  }
  return out;
}

export function toHostTools(tools) {
  return tools.map(t=>({type:'function',function:{name:t.name,description:t.description ?? '',parameters:t.parameters}}));
}

export function validateHostCalls(result, tools) {
  const allowed=new Set(tools.map(t=>t.name));
  const ids=new Set();
  for(const call of result.tool_calls) {
    if(!call || call.type!=='function' || typeof call.id!=='string' || !call.id.trim() || ids.has(call.id) || !allowed.has(call.function?.name)) throw new Error('Gemini requested an invalid or undeclared host tool.');
    ids.add(call.id);
    let args;
    try { args=JSON.parse(call.function.arguments); } catch { throw new Error('Gemini tool arguments must be a JSON object.'); }
    if(!args || Array.isArray(args) || typeof args!=='object') throw new Error('Gemini tool arguments must be a JSON object.');
  }
}

export function parseBridgeOutput(stdout, code) {
  let data;
  try { data=JSON.parse(stdout); } catch { throw new Error(`Gemini login bridge returned invalid JSON (exit ${code}).`); }
  if (data.error) throw new Error(String(data.error));
  if (code !== 0) throw new Error(`Gemini login bridge exit ${code}.`);
  if (typeof data.content !== 'string' || !Array.isArray(data.tool_calls)) throw new Error('Gemini login bridge returned an invalid response shape.');
  if (!data.content.trim() && !data.tool_calls.length) throw new Error('Gemini login bridge returned an empty response.');
  const usage=data.usage;
  if (!usage || ['prompt_tokens','completion_tokens','total_tokens'].some(key=>!Number.isSafeInteger(usage[key]) || usage[key]<0)) throw new Error('Gemini login bridge returned invalid usage counters.');
  const cached=usage.prompt_tokens_details?.cached_tokens;
  if(cached!==undefined && (!Number.isSafeInteger(cached) || cached<0 || cached>usage.prompt_tokens)) throw new Error('Gemini login bridge returned invalid cached usage.');
  return data;
}
