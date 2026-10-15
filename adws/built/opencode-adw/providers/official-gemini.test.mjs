import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { GEMINI_API, GEMINI_MODELS, GEMINI_HELPER, withOfficialGemini } from './official-gemini.mjs';
import { AssistantCache, buildRegistry, catalog, completion, createBridge, toPiContext } from './bridge.mjs';

const nativeModels = ['deepseek', 'zai-coding-cn', 'xai'].map(provider => ({ provider, id: 'native', api: 'native-test' }));
function sdk() {
  return {
    refresh(options) { this.refreshed = options; },
    hasConfiguredAuth(provider) { assert.notEqual(provider, 'google-gemini-cli'); return true; },
    getModels(provider) {
      assert.notEqual(provider, 'google-gemini-cli');
      return provider === undefined ? [...nativeModels, { provider: 'google-gemini-cli', id: 'legacy' }] : nativeModels.filter(model => model.provider === provider);
    },
    getModel(provider, id) { return this.getModels(provider).find(model => model.id === id); },
    completeSimple() { assert.fail('official call reached SDK'); },
    streamSimple() { assert.fail('official call reached SDK'); },
  };
}
const tools = [{ type: 'function', function: { name: 'read', description: 'Read file',
  parameters: { type: 'object', properties: { path: { type: 'string' } }, required: ['path'] } } }];
const bodyFor = model => ({ model: `${model.provider}/${model.id}`, messages: [{ role: 'user', content: 'hello' }] });
const resultFor = (model = GEMINI_MODELS[0]) => ({ model: model.id, content: 'official answer', tool_calls: [],
  usage: { prompt_tokens: 20, completion_tokens: 7, total_tokens: 27,
    prompt_tokens_details: { cached_tokens: 4 }, completion_tokens_details: { reasoning_tokens: 2 } }, conversation_id: 'conversation' });
const validCall = { id: 'host-next', type: 'function', function: { name: 'read', arguments: '{"path":"next"}' } };

test('official registry contains only two actual models and never queries legacy Google auth', async () => {
  const original = sdk(); let installed = true;
  const runtime = withOfficialGemini(original, { isInstalled: () => installed });
  const google = catalog(buildRegistry(runtime)).data.filter(item => item.provider === 'google-gemini-cli');
  assert.deepEqual(google.map(item => item.modelId), ['gemini-3.8-flash', 'gemini-4-argon']);
  for (const entry of google) {
    assert.equal(entry.api, GEMINI_API); assert.equal(entry.transport, 'official-cli');
    assert.equal(entry.availability, 'installed-paths-only'); assert.equal(entry.loginVerified, false);
  }
  assert.equal(runtime.getModel('google-gemini-cli', 'legacy'), undefined);
  assert.equal(runtime.getModels().filter(model => model.provider === 'google-gemini-cli').length, 2);
  await runtime.refresh({ allowNetwork: false }); assert.deepEqual(original.refreshed, { allowNetwork: false });
  installed = false;
  assert.equal(catalog(buildRegistry(runtime)).data.some(item => item.provider === 'google-gemini-cli'), false);
});

test('all three native SDK paths preserve exact calls, receiver, options and return identity', () => {
  const original = sdk(), context = { messages: [] }, options = { reasoning: 'medium' };
  const result = Promise.resolve('native result'), stream = { native: true };
  original.completeSimple = function (...args) {
    assert.equal(this, original); assert.equal(args[1], context); assert.equal(args[2], options); return result;
  };
  original.streamSimple = function (...args) {
    assert.equal(this, original); assert.equal(args[1], context); assert.equal(args[2], options); return stream;
  };
  const runtime = withOfficialGemini(original, { isInstalled: () => true, invokeBridge: () => assert.fail('must not invoke helper') });
  for (const model of nativeModels) {
    assert.equal(runtime.getModel(model.provider, model.id), model);
    assert.equal(runtime.completeSimple(model, context, options), result);
    assert.equal(runtime.streamSimple(model, context, options), stream);
  }
});

test('official request retains system/developer, complete tool rounds and schemas without API signatures', async () => {
  const model = GEMINI_MODELS[0], controller = new AbortController(); let sent, config, passedSignal;
  const runtime = withOfficialGemini(sdk(), { isInstalled: () => true, invokeBridge: async (request, signal, options) => {
    sent = request; config = options; passedSignal = signal;
    return { ...resultFor(model), tool_calls: [validCall] };
  } });
  const body = { ...bodyFor(model), tools, messages: [
    { role: 'system', content: [{ type: 'text', text: 'base' }] }, { role: 'developer', content: 'developer' },
    { role: 'user', content: 'request' },
    { role: 'assistant', content: null, tool_calls: ['first', 'second'].map(id => ({ id, type: 'function',
      function: { name: 'read', arguments: JSON.stringify({ path: id }) } })) },
    { role: 'tool', tool_call_id: 'first', content: 'first result' },
    { role: 'tool', tool_call_id: 'second', content: 'second result' }, { role: 'system', content: 'later' }] };
  const context = toPiContext(body, model, new AssistantCache());
  const message = await runtime.completeSimple(model, context, { signal: controller.signal, reasoning: 'medium', toolChoice: 'auto', timeoutMs: 999999 });
  assert.equal(sent.model, 'gemini-3.8-flash');
  assert.deepEqual(sent.messages.map(item => item.role), ['system', 'user', 'assistant', 'tool', 'tool']);
  assert.equal(sent.messages[0].content, 'base\n\ndeveloper\n\nlater');
  assert.equal(sent.messages[2].tool_calls.length, 2); assert.equal(sent.messages[3].tool_call_id, 'first');
  assert.equal(sent.messages[4].content, 'second result'); assert.deepEqual(sent.tools, tools);
  assert.equal(sent.reasoning_effort, 'medium'); assert.equal(sent.timeout_seconds, 180); assert.equal(sent.tool_choice, 'auto');
  assert.equal(passedSignal, controller.signal); assert.equal(config.command, '/opt/homebrew/bin/python3');
  assert.deepEqual(config.args, [GEMINI_HELPER]); assert.equal(config.timeoutMs, 180000); assert.equal(config.graceMs, 5000);
  assert.equal(message.api, GEMINI_API); assert.equal(message.model, model.id); assert.equal(message.stopReason, 'toolUse');
  assert.deepEqual(message.content[1].arguments, { path: 'next' });
  assert.deepEqual(completion(message, body.model).usage, resultFor().usage);
});

test('official effort mapping and none tool choice use one buffered done event', async () => {
  const model = GEMINI_MODELS[1], requests = [];
  const runtime = withOfficialGemini(sdk(), { isInstalled: () => true, invokeBridge: async request => {
    requests.push(request); return resultFor(model);
  } });
  for (const [reasoning, expected] of [[undefined, 'low'], ['minimal', 'low'], ['medium', 'medium'], ['xhigh', 'high']]) {
    const events = [];
    for await (const event of runtime.streamSimple(model, toPiContext(bodyFor(model), model), { reasoning, toolChoice: 'none', timeoutMs: 1234 })) events.push(event);
    assert.deepEqual(events.map(event => event.type), ['done']); assert.equal(events[0].message.content[0].text, 'official answer');
    assert.equal(requests.at(-1).reasoning_effort, expected); assert.equal(requests.at(-1).tool_choice, 'none');
    assert.equal(requests.at(-1).timeout_seconds, 1.234);
  }
});

test('official helper rejects wrong models, unknown/duplicate tools, bad argument objects and usage', async () => {
  const model = GEMINI_MODELS[0], context = toPiContext({ ...bodyFor(model), tools }, model);
  for (const patch of [
    { model: 'different' }, { tool_calls: [{ ...validCall, function: { name: 'native-shell', arguments: '{}' } }] },
    { tool_calls: [validCall, validCall] }, { tool_calls: [{ ...validCall, function: { name: 'read', arguments: '[]' } }] },
    { tool_calls: [{ ...validCall, function: { name: 'read', arguments: 'invalid json' } }] },
    { usage: { prompt_tokens: -1, completion_tokens: 2, total_tokens: 1 } },
    { usage: { prompt_tokens: 1, completion_tokens: 2, total_tokens: 3, completion_tokens_details: { reasoning_tokens: -1 } } },
    { native_tools: ['shell'] },
  ]) {
    const runtime = withOfficialGemini(sdk(), { isInstalled: () => true, invokeBridge: async () => ({ ...resultFor(model), ...patch }) });
    await assert.rejects(runtime.completeSimple(model, context));
  }
  const runtime = withOfficialGemini(sdk(), { isInstalled: () => true, invokeBridge: async () => ({ ...resultFor(model), tool_calls: [validCall] }) });
  await assert.rejects(runtime.completeSimple(model, context, { toolChoice: 'none' }));
  await assert.rejects(runtime.completeSimple({ ...model, id: 'legacy' }, context));
});

test('official cancellation passes the original signal and discards results returned after abort', async () => {
  const model = GEMINI_MODELS[0], controller = new AbortController(); let calls = 0;
  const runtime = withOfficialGemini(sdk(), { isInstalled: () => true, invokeBridge: async (_request, signal) => {
    calls++; assert.equal(signal, controller.signal); controller.abort(new Error('cancelled')); return resultFor(model);
  } });
  const context = toPiContext(bodyFor(model), model);
  await assert.rejects(runtime.completeSimple(model, context, { signal: controller.signal }), /cancelled/);
  await assert.rejects(runtime.completeSimple(model, context, { signal: controller.signal }), /cancelled/);
  assert.equal(calls, 1);
});

test('HTTP official buffered SSE and local-only catalog/request refresh integrate without native SDK calls', async t => {
  const original = sdk(); let refreshed = 0;
  original.refresh = async options => { assert.deepEqual(options, { allowNetwork: false }); refreshed++; };
  const model = GEMINI_MODELS[0];
  const runtime = withOfficialGemini(original, { isInstalled: () => true,
    invokeBridge: async () => ({ ...resultFor(model), tool_calls: [validCall] }) });
  const server = createBridge({ runtime, token: 'fake-local-token' });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => { server.closeAllConnections(); return new Promise(accept => server.close(accept)); });
  const url = `http://127.0.0.1:${server.address().port}`;
  const headers = { Authorization: 'Bearer fake-local-token', 'Content-Type': 'application/json' };
  const list = await fetch(`${url}/v1/models`, { headers });
  assert.equal((await list.json()).data.filter(item => item.provider === 'google-gemini-cli').length, 2);
  const response = await fetch(`${url}/v1/chat/completions`, { method: 'POST', headers,
    body: JSON.stringify({ ...bodyFor(model), tools, stream: true, stream_options: { include_usage: true } }) });
  const raw = await response.text();
  assert.match(raw, /official answer/); assert.match(raw, /"id":"host-next"/);
  assert.match(raw, /"finish_reason":"tool_calls"/); assert.match(raw, /"total_tokens":27/); assert.equal(refreshed, 2);
});
