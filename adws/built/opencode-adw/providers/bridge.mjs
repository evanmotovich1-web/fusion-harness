import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash, randomUUID, timingSafeEqual } from 'node:crypto';
import { once } from 'node:events';
import { GEMINI_API, withOfficialGemini } from './official-gemini.mjs';

export const VERSION = '1.0.0';
export const PROVIDERS = Object.freeze(['deepseek', 'zai-coding-cn', 'xai', 'google-gemini-cli']);
const SDK = '/Users/evanmotovich/.local/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js';
export class BridgeError extends Error {
  constructor(status, code) { super(code); this.status = status; this.code = code; }
}
const fail = (code, status = 400) => { throw new BridgeError(status, code); };
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const digest = value => createHash('sha256').update(value).digest();
const zeroUsage = () => ({ input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } });

export function textContent(content) {
  if (content == null) return '';
  if (typeof content === 'string') return content;
  if (!Array.isArray(content)) fail('invalid_content');
  return content.map(part => {
    if (!object(part) || part.type !== 'text' || typeof part.text !== 'string') fail('unsupported_content');
    return part.text;
  }).join('');
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (object(value)) return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
  return value;
}
function callsOf(message) {
  if (message.tool_calls === undefined) return [];
  if (!Array.isArray(message.tool_calls)) fail('invalid_tool_calls');
  return message.tool_calls.map(call => {
    if (!object(call) || call.type !== 'function' || typeof call.id !== 'string' || !call.id ||
        !object(call.function) || typeof call.function.name !== 'string' || !call.function.name ||
        typeof call.function.arguments !== 'string') fail('invalid_tool_call');
    let args;
    try { args = JSON.parse(call.function.arguments); } catch { fail('invalid_tool_arguments'); }
    if (!object(args)) fail('invalid_tool_arguments');
    return { type: 'toolCall', id: call.id, name: call.function.name, arguments: args };
  });
}
function assistantKey(model, message) {
  return digest(JSON.stringify([model, textContent(message.content), callsOf(message).map(call =>
    [call.id, call.name, canonical(call.arguments)])])).toString('hex');
}

/** No credentials, disk writes, or client-supplied opaque signatures. */
export class AssistantCache {
  constructor({ ttlMs = 30 * 60_000, maxEntries = 256, maxBytes = 16 * 1024 * 1024, now = Date.now } = {}) {
    this.entries = new Map(); this.bytes = 0;
    Object.assign(this, { ttlMs, maxEntries, maxBytes, now });
  }
  prune() {
    for (const [key, entry] of this.entries) if (entry.expires <= this.now()) this.remove(key);
  }
  remove(key) {
    const entry = this.entries.get(key);
    if (entry) { this.bytes -= entry.bytes; this.entries.delete(key); }
  }
  put(model, original) {
    this.prune();
    const key = assistantKey(model, openAIMessage(original));
    const bytes = Buffer.byteLength(JSON.stringify(original));
    this.remove(key);
    if (bytes > this.maxBytes || this.maxEntries < 1) return;
    while (this.entries.size >= this.maxEntries || this.bytes + bytes > this.maxBytes) this.remove(this.entries.keys().next().value);
    this.entries.set(key, { message: structuredClone(original), bytes, expires: this.now() + this.ttlMs });
    this.bytes += bytes;
  }
  get(model, message) {
    this.prune();
    const found = this.entries.get(assistantKey(model, message));
    return found ? structuredClone(found.message) : undefined;
  }
}

export function buildRegistry(runtime) {
  const registry = new Map();
  for (const provider of PROVIDERS) {
    if (!runtime.hasConfiguredAuth(provider)) continue;
    for (const model of runtime.getModels(provider)) {
      if (model.provider !== provider || typeof model.id !== 'string' || !model.id) continue;
      const alias = `${provider}/${model.id}`;
      if (registry.has(alias)) fail('duplicate_model', 500);
      registry.set(alias, model);
    }
  }
  return registry;
}
async function currentRegistry(runtime) {
  // Other local agents may connect/logout providers while this service stays up.
  // Refresh local credential availability, never the remote model catalog.
  if (typeof runtime.refresh === 'function') await runtime.refresh({ allowNetwork: false });
  return buildRegistry(runtime);
}
export function resolveModel(registry, requested) {
  if (typeof requested !== 'string' || !requested) fail('model_required');
  if (registry.has(requested)) return { alias: requested, model: registry.get(requested) };
  const matches = [...registry].filter(([, model]) => model.id === requested);
  if (matches.length > 1) fail('ambiguous_model');
  if (matches.length === 0) fail('unknown_model', 404);
  return { alias: matches[0][0], model: matches[0][1] };
}
export function catalog(registry) {
  return { object: 'list', data: [...registry].map(([id, model]) => ({ id, object: 'model', owned_by: model.provider,
    provider: model.provider, modelId: model.id, name: model.name, context: model.contextWindow,
    maxTokens: model.maxTokens, input: model.input, reasoning: model.reasoning,
    ...(model.api === GEMINI_API ? { api: model.api, transport: model.transport,
      availability: model.availability, loginVerified: false } : {}) })) };
}

export function toPiContext(body, model, cache = new AssistantCache()) {
  if (!Array.isArray(body.messages) || !body.messages.length) fail('messages_required');
  const messages = [], outstanding = new Map(), seenCalls = new Set();
  const alias = `${model.provider}/${model.id}`;
  for (const message of body.messages) {
    if (!object(message)) fail('invalid_message');
    const timestamp = Date.now();
    if (message.function_call !== undefined) fail('unsupported_legacy_function_call');
    switch (message.role) {
      case 'system': case 'developer':
        messages.push({ role: 'system', content: textContent(message.content), timestamp }); break;
      case 'user':
        if (outstanding.size) fail('missing_tool_results');
        messages.push({ role: 'user', content: textContent(message.content), timestamp }); break;
      case 'assistant': {
        if (outstanding.size) fail('missing_tool_results');
        const text = textContent(message.content), calls = callsOf(message);
        const restored = cache.get(alias, message);
        // Signed Gemini calls cannot be reconstructed from OpenAI's lossy history.
        // DeepSeek reasoning/tool history likewise must retain its thinking block.
        if (!restored && calls.length && ((model.provider === 'google-gemini-cli' && model.api !== GEMINI_API) ||
            (model.provider === 'deepseek' && model.reasoning && !message.reasoning_content))) {
          fail('assistant_history_unavailable', 409);
        }
        const reasoning = message.reasoning_content ?? message.reasoning;
        if (reasoning !== undefined && typeof reasoning !== 'string') fail('invalid_reasoning');
        const content = [...(reasoning ? [{ type: 'thinking', thinking: reasoning }] : []),
          ...(text ? [{ type: 'text', text }] : []), ...calls];
        messages.push(restored ?? { role: 'assistant', content, api: model.api, provider: model.provider,
          model: model.id, usage: zeroUsage(), stopReason: calls.length ? 'toolUse' : 'stop', timestamp });
        for (const call of calls) {
          if (seenCalls.has(call.id)) fail('duplicate_tool_call_id');
          seenCalls.add(call.id); outstanding.set(call.id, call.name);
        }
        break;
      }
      case 'tool': {
        const toolName = outstanding.get(message.tool_call_id);
        if (!toolName) fail('unmatched_tool_result');
        outstanding.delete(message.tool_call_id);
        messages.push({ role: 'toolResult', toolCallId: message.tool_call_id, toolName,
          content: [{ type: 'text', text: textContent(message.content) }], isError: message.is_error === true, timestamp });
        break;
      }
      default: fail('unsupported_role');
    }
  }
  if (outstanding.size) fail('missing_tool_results');
  let tools;
  if (body.tools !== undefined) {
    if (!Array.isArray(body.tools)) fail('invalid_tools');
    const names = new Set();
    tools = body.tools.map(tool => {
      const fn = tool?.function;
      if (tool?.type !== 'function' || !object(fn) || typeof fn.name !== 'string' || !fn.name ||
          !object(fn.parameters) || (fn.description !== undefined && typeof fn.description !== 'string') || names.has(fn.name)) fail('invalid_tool');
      names.add(fn.name);
      return { name: fn.name, description: fn.description ?? '', parameters: fn.parameters };
    });
  }
  return { messages, ...(tools ? { tools } : {}) };
}

export function toPiOptions(body, model, signal) {
  if (body.n !== undefined && body.n !== 1) fail('unsupported_n');
  if (body.stream !== undefined && typeof body.stream !== 'boolean') fail('invalid_stream');
  for (const key of ['functions', 'function_call', 'response_format', 'logprobs', 'logit_bias', 'stop', 'modalities', 'audio']) {
    if (body[key] !== undefined) fail('unsupported_option');
  }
  if (body.tool_choice !== undefined && !['auto', 'none'].includes(body.tool_choice)) fail('unsupported_tool_choice');
  const requested = body.max_completion_tokens ?? body.max_tokens ?? 4096;
  if (!Number.isSafeInteger(requested) || requested < 1) fail('invalid_max_tokens');
  const maximum = Number.isSafeInteger(model.maxTokens) && model.maxTokens > 0 ? model.maxTokens : 4096;
  const options = { signal, maxTokens: Math.min(requested, maximum), toolChoice: body.tool_choice };
  if (body.temperature !== undefined) {
    if (typeof body.temperature !== 'number' || !Number.isFinite(body.temperature) || body.temperature < 0 || body.temperature > 2) fail('invalid_temperature');
    options.temperature = body.temperature;
  }
  if (body.top_p !== undefined) {
    if (typeof body.top_p !== 'number' || !Number.isFinite(body.top_p) || body.top_p < 0 || body.top_p > 1) fail('invalid_top_p');
    options.samplingParams = { top_p: body.top_p };
  }
  const providerOptions = body.provider_options ?? {};
  if (!object(providerOptions)) fail('invalid_provider_options');
  const scoped = providerOptions[model.provider] ?? providerOptions;
  if (!object(scoped)) fail('invalid_provider_options');
  const reasoning = body.reasoning_effort ?? scoped.reasoning ?? scoped.reasoningEffort ?? 'low';
  if (!['none', 'off', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'].includes(reasoning)) fail('invalid_reasoning_effort');
  if (model.reasoning && !['none', 'off'].includes(reasoning)) options.reasoning = reasoning;
  return options;
}

export function openAIMessage(message) {
  const content = message.content.filter(part => part.type === 'text').map(part => part.text).join('');
  const reasoning = message.content.filter(part => part.type === 'thinking' && !part.redacted).map(part => part.thinking).join('');
  const calls = message.content.filter(part => part.type === 'toolCall').map(part => ({ id: part.id, type: 'function',
    function: { name: part.name, arguments: JSON.stringify(part.arguments) } }));
  return { role: 'assistant', content: content || null, ...(reasoning ? { reasoning_content: reasoning } : {}),
    ...(calls.length ? { tool_calls: calls } : {}) };
}
export function usageOf(message) {
  const usage = message.usage ?? zeroUsage();
  // Pi input excludes separately accounted cache reads/writes.
  const prompt = (usage.input ?? 0) + (usage.cacheRead ?? 0) + (usage.cacheWrite ?? 0);
  return { prompt_tokens: prompt, completion_tokens: usage.output ?? 0,
    total_tokens: usage.totalTokens ?? prompt + (usage.output ?? 0),
    prompt_tokens_details: { cached_tokens: usage.cacheRead ?? 0 },
    ...(usage.reasoning !== undefined ? { completion_tokens_details: { reasoning_tokens: usage.reasoning } } : {}) };
}
function finishReason(message) {
  if (!['stop', 'length', 'toolUse'].includes(message.stopReason)) fail('provider_failed', 502);
  return { stop: 'stop', length: 'length', toolUse: 'tool_calls' }[message.stopReason];
}
export function completion(message, model, id = `chatcmpl-${randomUUID()}`, created = Math.floor(Date.now() / 1000)) {
  return { id, object: 'chat.completion', created, model,
    choices: [{ index: 0, message: openAIMessage(message), finish_reason: finishReason(message) }], usage: usageOf(message) };
}

function abortable(promise, signal) {
  if (signal.aborted) return Promise.reject(signal.reason);
  return new Promise((accept, reject) => {
    const aborted = () => reject(signal.reason);
    signal.addEventListener('abort', aborted, { once: true });
    Promise.resolve(promise).then(accept, reject).finally(() => signal.removeEventListener('abort', aborted));
  });
}
function readBody(req, limit, signal) {
  return new Promise((accept, reject) => {
    const chunks = []; let length = 0;
    const cleanup = () => {
      req.removeListener('data', data); req.removeListener('end', end);
      req.removeListener('error', error); signal.removeEventListener('abort', aborted);
    };
    const error = reason => { cleanup(); req.resume(); reject(reason); };
    const aborted = () => error(signal.reason);
    const data = chunk => {
      length += chunk.length;
      if (length > limit) error(new BridgeError(413, 'request_too_large'));
      else chunks.push(chunk);
    };
    const end = () => {
      cleanup();
      try { accept(JSON.parse(Buffer.concat(chunks).toString('utf8'))); }
      catch { reject(new BridgeError(400, 'invalid_json')); }
    };
    if (signal.aborted) { aborted(); return; }
    req.on('data', data); req.once('end', end); req.once('error', error);
    signal.addEventListener('abort', aborted, { once: true });
  });
}
function json(res, status, body) {
  if (res.destroyed) return;
  res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
  res.end(JSON.stringify(body));
}

/** Injectable runtime: tests never read Pi auth files or contact providers. */
export function createBridge({ runtime, token, host = '127.0.0.1', timeoutMs = 180_000,
  maxBodyBytes = 4 * 1024 * 1024, concurrency = 8, cache = new AssistantCache() } = {}) {
  if (host !== '127.0.0.1') fail('loopback_required', 500);
  if (typeof token !== 'string' || !token.trim() || /[\r\n]/.test(token)) fail('bridge_token_required', 500);
  if (!runtime) fail('runtime_required', 500);
  for (const value of [timeoutMs, maxBodyBytes, concurrency]) if (!Number.isSafeInteger(value) || value < 1) fail('invalid_server_limit', 500);
  const tokenHash = digest(`Bearer ${token}`);
  let active = 0;
  const server = http.createServer(async (req, res) => {
    let acquired = false, timer, provider;
    const controller = new AbortController(), { signal } = controller;
    const disconnect = () => { if (!res.writableFinished) controller.abort(new BridgeError(499, 'client_disconnected')); };
    req.on('aborted', disconnect); res.on('close', disconnect);
    try {
      const authority = `127.0.0.1:${server.address().port}`;
      if (req.headers.host !== authority) fail('invalid_host', 403);
      if (req.headers.origin !== undefined && req.headers.origin !== `http://${authority}`) fail('origin_forbidden', 403);
      if (req.headers['sec-fetch-site'] === 'cross-site') fail('origin_forbidden', 403);
      if (req.method === 'GET' && req.url === '/health') { json(res, 200, { status: 'ok', version: VERSION }); return; }
      const authorization = typeof req.headers.authorization === 'string' ? req.headers.authorization : '';
      if (!timingSafeEqual(digest(authorization), tokenHash)) fail('unauthorized', 401);
      if (req.method === 'GET' && req.url === '/v1/models') { json(res, 200, catalog(await currentRegistry(runtime))); return; }
      if (req.method !== 'POST' || req.url !== '/v1/chat/completions') fail('not_found', 404);
      if (active >= concurrency) fail('concurrency_limit', 429);
      if (!/^application\/json(?:\s*;|$)/i.test(req.headers['content-type'] ?? '')) fail('json_required', 415);
      const declared = req.headers['content-length'];
      if (declared !== undefined && Number(declared) > maxBodyBytes) fail('request_too_large', 413);
      active++; acquired = true;
      timer = setTimeout(() => controller.abort(new BridgeError(504, 'request_timeout')), timeoutMs);
      const body = await abortable(readBody(req, maxBodyBytes, signal), signal);
      if (!object(body)) fail('invalid_request');
      const { alias, model } = resolveModel(await abortable(currentRegistry(runtime), signal), body.model);
      provider = model.provider;
      const options = toPiOptions(body, model, signal), context = toPiContext(body, model, cache);
      if (!body.stream) {
        const message = await abortable(runtime.completeSimple(model, context, options), signal);
        const result = completion(message, alias);
        cache.put(alias, message);
        json(res, 200, result);
      } else {
        const id = `chatcmpl-${randomUUID()}`, created = Math.floor(Date.now() / 1000);
        // Lazy headers let setup errors retain their HTTP status.
        const send = async value => {
          if (signal.aborted) throw signal.reason;
          if (!res.headersSent) res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache, no-store', 'X-Accel-Buffering': 'no' });
          if (!res.write(`data: ${typeof value === 'string' ? value : JSON.stringify(value)}\n\n`)) await once(res, 'drain', { signal });
        };
        const chunk = (delta, finish_reason = null) => ({ id, object: 'chat.completion.chunk', created, model: alias,
          choices: [{ index: 0, delta, finish_reason }] });
        const stream = runtime.streamSimple(model, context, options);
        const iterator = stream[Symbol.asyncIterator]();
        let final, started = false;
        const textDeltas = new Set(), thinkingDeltas = new Set();
        try {
          while (true) {
            const next = await abortable(iterator.next(), signal);
            if (next.done) break;
            const event = next.value;
            if (event.type === 'error') fail('provider_failed', 502);
            if (!started) { await send(chunk({ role: 'assistant' })); started = true; }
            if (event.type === 'text_delta') { textDeltas.add(event.contentIndex); await send(chunk({ content: event.delta })); }
            if (event.type === 'thinking_delta' && !event.partial?.content?.[event.contentIndex]?.redacted) {
              thinkingDeltas.add(event.contentIndex); await send(chunk({ reasoning_content: event.delta }));
            }
            if (event.type === 'done') { final = event.message; break; }
          }
        } finally {
          // Do not wait for a provider that ignores cancellation.
          Promise.resolve(iterator.return?.()).catch(() => {});
        }
        if (!final) fail('provider_incomplete', 502);
        const reason = finishReason(final);
        let toolIndex = 0;
        for (const [index, part] of final.content.entries()) {
          if (part.type === 'text' && !textDeltas.has(index)) await send(chunk({ content: part.text }));
          if (part.type === 'thinking' && !part.redacted && !thinkingDeltas.has(index)) await send(chunk({ reasoning_content: part.thinking }));
          if (part.type === 'toolCall') await send(chunk({ tool_calls: [{ index: toolIndex++, id: part.id, type: 'function',
            function: { name: part.name, arguments: JSON.stringify(part.arguments) } }] }));
        }
        cache.put(alias, final);
        await send(chunk({}, reason));
        if (body.stream_options?.include_usage) await send({ id, object: 'chat.completion.chunk', created, model: alias, choices: [], usage: usageOf(final) });
        await send('[DONE]'); res.end();
      }
    } catch (error) {
      // Never reflect SDK error messages, names, request payloads, or credentials.
      const safe = signal.aborted && signal.reason instanceof BridgeError ? signal.reason :
        error instanceof BridgeError ? error : new BridgeError(502, 'provider_failed');
      const payload = { error: { message: safe.code, type: safe.status >= 500 ? 'server_error' : 'invalid_request_error',
        code: safe.code, ...(provider ? { provider } : {}) } };
      if (!res.destroyed && !res.writableEnded) {
        if (res.headersSent) res.end(`data: ${JSON.stringify(payload)}\n\ndata: [DONE]\n\n`);
        else json(res, safe.status, payload);
      }
    } finally {
      clearTimeout(timer);
      req.removeListener('aborted', disconnect); res.removeListener('close', disconnect);
      if (acquired) active--;
    }
  });
  // Even callers holding the returned test server cannot bind it on another interface.
  const listen = server.listen.bind(server);
  server.listen = (port = 4198, requestedHost = host, callback) => {
    if (requestedHost !== host) fail('loopback_required', 500);
    if (!Number.isInteger(port) || port < 0 || port > 65535) fail('invalid_port', 500);
    return listen(port, host, callback);
  };
  server.requestTimeout = timeoutMs;
  server.headersTimeout = Math.min(timeoutMs, 60_000);
  return server;
}

export async function loadRuntime(modulePath = process.env.PI_MODEL_RUNTIME_MODULE ?? SDK) {
  const { ModelRuntime } = await import(pathToFileURL(resolve(modulePath)).href);
  const runtime = await ModelRuntime.create({ authPath: join(homedir(), '.pi/agent/auth.json'),
    modelsPath: join(homedir(), '.pi/agent/models.json'), allowModelNetwork: false, refreshOnCreate: true });
  return withOfficialGemini(runtime);
}
export async function main(args = process.argv.slice(2), env = process.env) {
  let port = env.PI_PROVIDER_BRIDGE_PORT ?? '4198';
  for (let index = 0; index < args.length; index++) {
    if (args[index] !== '--port' || !args[index + 1]) fail('invalid_cli', 500);
    port = args[++index];
  }
  if (!/^\d+$/.test(String(port)) || Number(port) < 1 || Number(port) > 65535) fail('invalid_port', 500);
  if (env.PI_PROVIDER_BRIDGE_HOST && env.PI_PROVIDER_BRIDGE_HOST !== '127.0.0.1') fail('loopback_required', 500);
  const tokenFile = env.PI_PROVIDER_BRIDGE_TOKEN_FILE ?? join(homedir(), '.local/share/opencode-adw/provider-bridge/token');
  let token;
  try { token = (await readFile(tokenFile, 'utf8')).trim(); } catch { fail('bridge_token_required', 500); }
  if (!token || /[\r\n]/.test(token)) fail('bridge_token_required', 500);
  const runtime = await loadRuntime(env.PI_MODEL_RUNTIME_MODULE ?? SDK);
  const server = createBridge({ runtime, token });
  await new Promise((accept, reject) => { server.once('error', reject); server.listen(Number(port), '127.0.0.1', accept); });
  return server;
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(error => {
    process.stderr.write(`${error instanceof BridgeError ? error.code : 'bridge_start_failed'}\n`);
    process.exitCode = 1;
  });
}
