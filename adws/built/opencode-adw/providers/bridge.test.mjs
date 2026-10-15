import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { once } from 'node:events';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { AssistantCache, BridgeError, PROVIDERS, buildRegistry, catalog, completion, createBridge, main,
  resolveModel, textContent, toPiContext, toPiOptions, loadRuntime } from './bridge.mjs';

test('runtime initializes local auth availability without enabling remote catalog refresh', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'oc-provider-runtime-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const module = join(directory, 'sdk.mjs');
  await writeFile(module, 'export class ModelRuntime { static async create(options) { return options; } }');
  const options = await loadRuntime(module);
  assert.equal(options.allowModelNetwork, false);
  assert.equal(options.refreshOnCreate, true);
  assert.match(options.authPath, /\.pi\/agent\/auth\.json$/);
});

const token = 'test-bridge-token';
const models = PROVIDERS.map(provider => ({ provider, id: `${provider}-model`, name: provider,
  api: provider === 'google-gemini-cli' ? 'google-generative-ai' : 'openai-completions',
  contextWindow: 128000, maxTokens: 16384, input: ['text'], reasoning: true }));
const usage = { input: 10, output: 5, cacheRead: 2, cacheWrite: 3, totalTokens: 20,
  reasoning: 2, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } };
function assistant(model = models[0], content = [{ type: 'text', text: 'answer' }], stopReason = 'stop') {
  return { role: 'assistant', content, provider: model.provider, api: model.api, model: model.id,
    usage: structuredClone(usage), timestamp: 1, stopReason };
}
const call = (id, name = 'read', args = { path: 'file' }) => ({ type: 'toolCall', id, name, arguments: args, thoughtSignature: `opaque-${id}` });
const tools = [{ type: 'function', function: { name: 'read', description: 'Read a file',
  parameters: { type: 'object', properties: { path: { type: 'string' } }, required: ['path'] } } }];
const bodyFor = (model = models[0]) => ({ model: `${model.provider}/${model.id}`, messages: [{ role: 'user', content: 'hello' }] });
class FakeSDK {
  constructor() { this.calls = []; this.catalog = [...models]; this.configured = new Set(PROVIDERS); }
  hasConfiguredAuth(provider) { return this.configured.has(provider); }
  getModels(provider) { return this.catalog.filter(model => model.provider === provider); }
  async completeSimple(model, context, options) {
    this.calls.push({ model, context, options });
    return this.result ?? assistant(model);
  }
  async *streamSimple(model, context, options) {
    this.calls.push({ model, context, options });
    const message = this.result ?? assistant(model, [{ type: 'thinking', thinking: 'think', thinkingSignature: 'secret-signature' },
      { type: 'text', text: 'answer' }, call('c1'), call('c2')], 'toolUse');
    yield { type: 'start', partial: message };
    yield { type: 'thinking_delta', contentIndex: 0, delta: 'think', partial: message };
    yield { type: 'text_delta', contentIndex: 1, delta: 'answer', partial: message };
    yield { type: 'done', message };
  }
}
async function fixture(t, options = {}) {
  const runtime = options.runtime ?? new FakeSDK();
  const server = createBridge({ runtime, token, ...options });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => { server.closeAllConnections(); return new Promise(accept => server.close(accept)); });
  const url = `http://127.0.0.1:${server.address().port}`;
  const request = (body = bodyFor(), headers = {}) => fetch(`${url}/v1/chat/completions`, {
    method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
  return { runtime, server, url, request };
}
const rejectsCode = (fn, code) => assert.throws(fn, error => error instanceof BridgeError && error.code === code);

test('catalog is restricted to four configured providers; aliases resolve exactly or uniquely', () => {
  const runtime = new FakeSDK();
  runtime.catalog = [...models, { ...models[0], provider: 'unapproved', id: 'bad' }];
  let registry = buildRegistry(runtime);
  assert.deepEqual(catalog(registry).data.map(item => item.provider), PROVIDERS);
  assert.deepEqual(catalog(registry).data[0], { id: 'deepseek/deepseek-model', object: 'model', owned_by: 'deepseek',
    provider: 'deepseek', modelId: 'deepseek-model', name: 'deepseek', context: 128000, maxTokens: 16384, input: ['text'], reasoning: true });
  assert.equal(resolveModel(registry, 'deepseek-model').model, models[0]);
  rejectsCode(() => resolveModel(registry, 'other/deepseek-model'), 'unknown_model');
  rejectsCode(() => resolveModel(registry, ''), 'model_required');
  runtime.catalog.push({ ...models[1], id: models[0].id });
  registry = buildRegistry(runtime);
  rejectsCode(() => resolveModel(registry, models[0].id), 'ambiguous_model');
  assert.equal(resolveModel(registry, 'deepseek/deepseek-model').model.provider, 'deepseek');
  runtime.configured.delete('xai');
  assert.equal(catalog(buildRegistry(runtime)).data.some(item => item.provider === 'xai'), false);
});

test('role and tool mapping preserves ordered system/developer messages and JSON schemas', () => {
  const model = models[2];
  const body = { ...bodyFor(model), tools, messages: [
    { role: 'system', content: [{ type: 'text', text: 'system' }] },
    { role: 'developer', content: 'developer' }, { role: 'user', content: [{ type: 'text', text: 'a' }, { type: 'text', text: 'b' }] },
    { role: 'assistant', content: 'working', reasoning_content: 'reason', tool_calls: [
      { id: 'one', type: 'function', function: { name: 'read', arguments: '{"path":"one"}' } },
      { id: 'two', type: 'function', function: { name: 'read', arguments: '{"path":"two"}' } }] },
    { role: 'tool', tool_call_id: 'two', content: [{ type: 'text', text: 'two result' }] },
    { role: 'tool', tool_call_id: 'one', content: 'one result', is_error: true },
    { role: 'system', content: 'later instruction' }, { role: 'user', content: 'next' }] };
  const context = toPiContext(body, model);
  assert.deepEqual(context.messages.map(message => message.role), ['system', 'system', 'user', 'assistant', 'toolResult', 'toolResult', 'system', 'user']);
  assert.equal(context.messages[0].content, 'system');
  assert.equal(context.messages[1].content, 'developer');
  assert.equal(context.messages[2].content, 'ab');
  assert.deepEqual(context.messages[3].content[2].arguments, { path: 'one' });
  assert.equal(context.messages[4].toolName, 'read');
  assert.equal(context.messages[5].isError, true);
  assert.deepEqual(context.tools[0].parameters, tools[0].function.parameters);
});

test('signed multi-tool rounds restore complete Pi messages even when client strips thinking', () => {
  for (const model of [models[0], models[3]]) {
    const cache = new AssistantCache();
    const first = assistant(model, [{ type: 'thinking', thinking: 'hidden reasoning', thinkingSignature: 'signed' },
      { type: 'text', text: 'working', textSignature: 'signed-text' }, call('one'), call('two')], 'toolUse');
    const second = assistant(model, [call('three')], 'toolUse');
    const alias = `${model.provider}/${model.id}`;
    cache.put(alias, first); cache.put(alias, second);
    const wireFirst = completion(first, alias).choices[0].message;
    delete wireFirst.reasoning_content;
    // Canonical arguments tolerate property ordering and whitespace changes.
    wireFirst.tool_calls[0].function.arguments = ' { "path" : "file" } ';
    const body = { ...bodyFor(model), messages: [{ role: 'user', content: 'start' }, wireFirst,
      { role: 'tool', tool_call_id: 'one', content: 'one' }, { role: 'tool', tool_call_id: 'two', content: 'two' },
      completion(second, alias).choices[0].message, { role: 'tool', tool_call_id: 'three', content: 'three' }] };
    const context = toPiContext(body, model, cache);
    assert.deepEqual(context.messages[1], first);
    assert.deepEqual(context.messages[4], second);
    context.messages[1].content[0].thinkingSignature = 'changed';
    assert.equal(toPiContext(body, model, cache).messages[1].content[0].thinkingSignature, 'signed');
    rejectsCode(() => toPiContext(body, model, new AssistantCache()), 'assistant_history_unavailable');
    const other = { ...model, id: 'another' };
    rejectsCode(() => toPiContext(body, other, cache), 'assistant_history_unavailable');
  }
});

test('signature cache expires and enforces both count and byte bounds', () => {
  let now = 0;
  const cache = new AssistantCache({ now: () => now, ttlMs: 10, maxEntries: 1, maxBytes: 4096 });
  const first = assistant(models[3], [call('a')], 'toolUse'), second = assistant(models[3], [call('b')], 'toolUse');
  cache.put('m', first); assert.deepEqual(cache.get('m', completion(first, 'm').choices[0].message), first);
  cache.put('m', second); assert.equal(cache.entries.size, 1);
  assert.equal(cache.get('m', completion(first, 'm').choices[0].message), undefined);
  now = 11; assert.equal(cache.get('m', completion(second, 'm').choices[0].message), undefined);
  assert.equal(cache.bytes, 0);
  cache.put('m', assistant(models[0], [{ type: 'text', text: 'x'.repeat(5000) }]));
  assert.equal(cache.entries.size, 0);
});

test('invalid content and tool histories fail explicitly', () => {
  rejectsCode(() => textContent([{ type: 'image_url', image_url: { url: 'private' } }]), 'unsupported_content');
  const model = models[2], base = bodyFor(model);
  const check = (messages, code) => rejectsCode(() => toPiContext({ ...base, messages }, model), code);
  check([{ role: 'unknown', content: '' }], 'unsupported_role');
  check([{ role: 'tool', tool_call_id: 'missing', content: '' }], 'unmatched_tool_result');
  check([{ role: 'assistant', tool_calls: [{ id: 'a', type: 'function', function: { name: 'read', arguments: '[]' } }] }], 'invalid_tool_arguments');
  check([{ role: 'assistant', tool_calls: [{ id: 'a', type: 'function', function: { name: 'read', arguments: '{' } }] }], 'invalid_tool_arguments');
  check([{ role: 'assistant', tool_calls: [{ id: 'a', type: 'function', function: { name: 'read', arguments: '{}' } }] }], 'missing_tool_results');
});

test('options preserve caller token budgets, clamp model max, whitelist reasoning and never forward credentials', () => {
  const model = models[0];
  assert.equal(toPiOptions({}, model).maxTokens, 4096);
  assert.equal(toPiOptions({ max_tokens: 12000 }, model).maxTokens, 12000);
  assert.equal(toPiOptions({ max_tokens: 999999 }, model).maxTokens, model.maxTokens);
  assert.equal(toPiOptions({ max_tokens: 200, max_completion_tokens: 500 }, model).maxTokens, 500);
  assert.equal(toPiOptions({ provider_options: { deepseek: { reasoning: 'medium', apiKey: 'do-not-forward' } } }, model).reasoning, 'medium');
  const options = toPiOptions({ api_key: 'do-not-forward', headers: { Authorization: 'bad' }, reasoning_effort: 'off' }, model);
  assert.equal(options.apiKey, undefined); assert.equal(options.headers, undefined); assert.equal(options.reasoning, undefined);
  for (const max_tokens of [0, -1, 1.5, '100']) rejectsCode(() => toPiOptions({ max_tokens }, model), 'invalid_max_tokens');
  rejectsCode(() => toPiOptions({ tool_choice: 'required' }, model), 'unsupported_tool_choice');
  rejectsCode(() => toPiOptions({ response_format: { type: 'json_object' } }, model), 'unsupported_option');
  rejectsCode(() => toPiOptions({ reasoning_effort: 'invented' }, model), 'invalid_reasoning_effort');
});

test('HTTP health, catalog and nonstream completion have bounded public metadata', async t => {
  const { url, request, runtime } = await fixture(t);
  const health = await fetch(`${url}/health`);
  assert.deepEqual(await health.json(), { status: 'ok', version: '1.0.0' });
  const list = await fetch(`${url}/v1/models`, { headers: { Authorization: `Bearer ${token}` } });
  assert.equal((await list.json()).data.length, 4);
  const response = await request(); assert.equal(response.status, 200);
  const result = await response.json();
  assert.equal(result.choices[0].message.content, 'answer');
  assert.equal(result.choices[0].finish_reason, 'stop');
  assert.equal(result.model, 'deepseek/deepseek-model');
  assert.deepEqual(result.usage, { prompt_tokens: 15, completion_tokens: 5, total_tokens: 20,
    prompt_tokens_details: { cached_tokens: 2 }, completion_tokens_details: { reasoning_tokens: 2 } });
  assert.equal(runtime.calls.length, 1);
});

test('SSE text/reasoning, all tools, usage and DONE reenter the OpenCode tool loop', async t => {
  const { request, runtime } = await fixture(t);
  const response = await request({ ...bodyFor(), stream: true, stream_options: { include_usage: true } });
  assert.equal(response.headers.get('content-type'), 'text/event-stream');
  const raw = await response.text();
  assert.equal(raw.includes('opaque-'), false); assert.equal(raw.includes('secret-signature'), false);
  const events = raw.trim().split('\n\n').map(frame => frame.slice(6));
  assert.equal(events.pop(), '[DONE]');
  const chunks = events.map(JSON.parse), deltas = chunks.flatMap(chunk => chunk.choices.map(choice => choice.delta));
  assert.equal(deltas.map(delta => delta.content ?? '').join(''), 'answer');
  assert.equal(deltas.map(delta => delta.reasoning_content ?? '').join(''), 'think');
  const calls = deltas.flatMap(delta => delta.tool_calls ?? []);
  assert.deepEqual(calls.map(call => call.index), [0, 1]);
  assert.deepEqual(calls.map(call => call.id), ['c1', 'c2']);
  assert.equal(chunks.at(-2).choices[0].finish_reason, 'tool_calls');
  assert.equal(chunks.at(-1).usage.total_tokens, 20);
  const returned = { role: 'assistant', content: 'answer', tool_calls: calls.map(({ index, ...call }) => call) };
  runtime.result = assistant();
  const round = await request({ ...bodyFor(), messages: [...bodyFor().messages, returned,
    ...calls.map(call => ({ role: 'tool', tool_call_id: call.id, content: 'tool output' }))] });
  assert.equal(round.status, 200);
  assert.equal(runtime.calls[1].context.messages[1].content[0].thinkingSignature, 'secret-signature');
  assert.equal(runtime.calls[1].context.messages[1].content[2].thoughtSignature, 'opaque-c1');
});

test('nonstream signed response survives an HTTP tool round with stripped reasoning', async t => {
  const runtime = new FakeSDK();
  runtime.result = assistant(models[3], [{ type: 'thinking', thinking: 'reason', thinkingSignature: 'keep' }, call('g')], 'toolUse');
  const { request } = await fixture(t, { runtime });
  const first = await (await request(bodyFor(models[3]))).json();
  const message = first.choices[0].message; delete message.reasoning_content;
  const response = await request({ ...bodyFor(models[3]), messages: [...bodyFor(models[3]).messages, message,
    { role: 'tool', tool_call_id: 'g', content: 'result' }] });
  assert.equal(response.status, 200);
  assert.equal(runtime.calls[1].context.messages[1].content[0].thinkingSignature, 'keep');
});

test('auth, cross-origin and Host checks reject before any SDK generation', async t => {
  const { request, runtime, url } = await fixture(t);
  for (const headers of [{ Authorization: '' }, { Authorization: 'Bearer wrong' }]) assert.equal((await request(bodyFor(), headers)).status, 401);
  for (const Origin of ['https://evil.example', 'null', 'http://localhost:4198']) {
    assert.equal((await request(bodyFor(), { Origin })).status, 403);
  }
  const badHost = await new Promise((accept, reject) => {
    const req = http.request(`${url}/health`, { headers: { Host: 'evil.example' } }, res => {
      res.resume(); res.on('end', () => accept(res.statusCode));
    });
    req.on('error', reject); req.end();
  });
  assert.equal(badHost, 403);
  assert.equal((await request(bodyFor(), { 'Sec-Fetch-Site': 'cross-site' })).status, 403);
  assert.equal(runtime.calls.length, 0);
  assert.equal((await request(bodyFor(), { Origin: url })).status, 200);
});

test('no missing-token or nonloopback server, even via returned server.listen', () => {
  rejectsCode(() => createBridge({ runtime: new FakeSDK() }), 'bridge_token_required');
  rejectsCode(() => createBridge({ runtime: new FakeSDK(), token, host: '0.0.0.0' }), 'loopback_required');
  const server = createBridge({ runtime: new FakeSDK(), token });
  rejectsCode(() => server.listen(0, '0.0.0.0'), 'loopback_required');
  rejectsCode(() => server.listen({ port: 0, host: '0.0.0.0' }), 'invalid_port');
});

test('CLI rejects invalid ports, nonloopback hosts, and missing token before SDK creation', async () => {
  for (const args of [['--port', '0'], ['--port', '65536'], ['--port', '-1'], ['--host', '0.0.0.0']]) {
    await assert.rejects(main(args, {}), error => error instanceof BridgeError);
  }
  await assert.rejects(main([], { PI_PROVIDER_BRIDGE_HOST: '0.0.0.0' }), { code: 'loopback_required' });
  await assert.rejects(main([], { PI_PROVIDER_BRIDGE_TOKEN_FILE: '/nonexistent-opencode-bridge-test-token' }), { code: 'bridge_token_required' });
});

test('unknown/ambiguous models, images and invalid JSON never call runtime', async t => {
  const { request, runtime, url } = await fixture(t);
  assert.equal((await request({ ...bodyFor(), model: 'missing' })).status, 404);
  runtime.catalog.push({ ...models[1], id: models[0].id });
  assert.equal((await request({ ...bodyFor(), model: models[0].id })).status, 400);
  assert.equal((await request({ ...bodyFor(), messages: [{ role: 'user', content: [{ type: 'image_url' }] }] })).status, 400);
  const invalid = await fetch(`${url}/v1/chat/completions`, { method: 'POST', headers: {
    Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: '{' });
  assert.equal(invalid.status, 400); assert.equal(runtime.calls.length, 0);
});

test('declared and chunked body limits return 413', async t => {
  const { request, url } = await fixture(t, { maxBodyBytes: 256 });
  assert.equal((await request({ ...bodyFor(), padding: 'x'.repeat(300) })).status, 413);
  const response = await new Promise((accept, reject) => {
    const req = http.request(`${url}/v1/chat/completions`, { method: 'POST', headers: {
      Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'Transfer-Encoding': 'chunked' } }, res => {
      res.resume(); res.on('end', () => accept(res.statusCode));
    });
    req.on('error', reject); req.write('x'.repeat(300)); req.end();
  });
  assert.equal(response, 413);
});

test('provider exceptions and failed stop reasons are generic and never echo secrets', async t => {
  const runtime = new FakeSDK();
  runtime.completeSimple = async () => { throw new Error('Authorization: Bearer supersecret refresh_token=secret raw request'); };
  const { request } = await fixture(t, { runtime });
  const response = await request(); assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), { error: { message: 'provider_failed', type: 'server_error', code: 'provider_failed', provider: 'deepseek' } });
  runtime.completeSimple = async () => ({ ...assistant(), stopReason: 'error', errorMessage: 'supersecret' });
  assert.equal((await request()).status, 502);
  runtime.completeSimple = async () => assistant(models[0], [], 'length');
  assert.equal((await (await request()).json()).choices[0].finish_reason, 'length');
});

test('SSE provider error is an error event followed by DONE, never a successful finish', async t => {
  const runtime = new FakeSDK();
  runtime.streamSimple = async function* () {
    yield { type: 'start', partial: assistant() };
    yield { type: 'error', error: { ...assistant(), errorMessage: 'refresh_token=secret' } };
  };
  const { request } = await fixture(t, { runtime });
  const response = await request({ ...bodyFor(), stream: true });
  const raw = await response.text();
  assert.match(raw, /"code":"provider_failed"/); assert.match(raw, /data: \[DONE\]/);
  assert.equal(raw.includes('refresh_token'), false); assert.equal(raw.includes('"finish_reason":"stop"'), false);
});

test('timeout aborts a stuck nonstream runtime and releases concurrency slot', async t => {
  const runtime = new FakeSDK(); let signal;
  runtime.completeSimple = (_model, _context, options) => { signal = options.signal; return new Promise(() => {}); };
  const { request } = await fixture(t, { runtime, timeoutMs: 40, concurrency: 1 });
  const response = await request();
  assert.equal(response.status, 504); assert.equal(signal.aborted, true);
  assert.equal((await response.json()).error.code, 'request_timeout');
  runtime.completeSimple = async () => assistant();
  assert.equal((await request()).status, 200);
});

test('stalled SSE is bounded by timeout and receives the same cancellation signal', async t => {
  const runtime = new FakeSDK(); let signal;
  runtime.streamSimple = (_model, _context, options) => {
    signal = options.signal;
    return { [Symbol.asyncIterator]: () => ({ next: () => new Promise(() => {}) }) };
  };
  const { request } = await fixture(t, { runtime, timeoutMs: 40 });
  assert.equal((await request({ ...bodyFor(), stream: true })).status, 504);
  assert.equal(signal.aborted, true);
});

test('SSE timeout after headers yields an explicit error instead of a successful finish', async t => {
  const runtime = new FakeSDK(); let signal;
  runtime.streamSimple = async function* (_model, _context, options) {
    signal = options.signal;
    yield { type: 'start', partial: assistant() };
    await new Promise(() => {});
  };
  const { request } = await fixture(t, { runtime, timeoutMs: 40 });
  const response = await request({ ...bodyFor(), stream: true });
  const raw = await response.text();
  assert.equal(response.status, 200); assert.match(raw, /"code":"request_timeout"/);
  assert.equal(signal.aborted, true); assert.equal(raw.includes('"finish_reason":"stop"'), false);
});

test('timeout also bounds incomplete request-body uploads', async t => {
  const { url, runtime } = await fixture(t, { timeoutMs: 40 });
  const response = await new Promise((accept, reject) => {
    const req = http.request(`${url}/v1/chat/completions`, { method: 'POST', headers: {
      Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'Transfer-Encoding': 'chunked' } }, res => {
      res.resume(); res.on('end', () => { accept(res.statusCode); req.destroy(); });
    });
    req.on('error', reject); req.write('{');
  });
  assert.equal(response, 504); assert.equal(runtime.calls.length, 0);
});

test('concurrency cap rejects 429 while first request is active', async t => {
  const runtime = new FakeSDK(); let release, started;
  const ready = new Promise(accept => { started = accept; });
  runtime.completeSimple = () => { started(); return new Promise(accept => { release = accept; }); };
  const { request } = await fixture(t, { runtime, concurrency: 1 });
  const first = request(); await ready;
  assert.equal((await request()).status, 429);
  release(assistant()); assert.equal((await first).status, 200);
});

test('client disconnect aborts provider work', async t => {
  const runtime = new FakeSDK(); let signal, started;
  const ready = new Promise(accept => { started = accept; });
  runtime.completeSimple = (_model, _context, options) => { signal = options.signal; started(); return new Promise(() => {}); };
  const { url } = await fixture(t, { runtime });
  const req = http.request(`${url}/v1/chat/completions`, { method: 'POST', headers: {
    Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } });
  req.on('error', () => {}); req.end(JSON.stringify(bodyFor())); await ready;
  const aborted = once(signal, 'abort'); req.destroy(); await aborted;
  assert.equal(signal.aborted, true);
});
