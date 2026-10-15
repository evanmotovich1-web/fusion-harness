import { accessSync, constants } from 'node:fs';
import { effortFor, toHostMessages, toHostTools, validateHostCalls, parseBridgeOutput }
  from '/Users/evanmotovich/.pi/agent/extensions/gemini-login/protocol.mjs';
import { invokeBridge as installedInvoker }
  from '/Users/evanmotovich/.pi/agent/extensions/gemini-login/transport.mjs';

export const GEMINI_PROVIDER = 'google-gemini-cli';
export const GEMINI_API = 'gemini-login-cli';
export const GEMINI_BINARY = '/Applications/Gemini.app/Contents/Helpers/agy';
export const GEMINI_HELPER = '/Users/evanmotovich/.local/share/gemini-login-bridge/gemini_login_bridge.py';
export const GEMINI_MODELS = Object.freeze(['gemini-3.8-flash', 'gemini-4-argon'].map(id => Object.freeze({
  id, provider: GEMINI_PROVIDER, api: GEMINI_API,
  name: `${id} (official Antigravity CLI)`, baseUrl: 'cli://antigravity',
  reasoning: true, input: Object.freeze(['text']), contextWindow: 1_000_000, maxTokens: 65536,
  transport: 'official-cli', availability: 'installed-paths-only', loginVerified: false,
})));

export function officialGeminiInstalled() {
  try {
    accessSync(GEMINI_BINARY, constants.X_OK);
    accessSync(GEMINI_HELPER, constants.R_OK);
    return true;
  } catch { return false; }
}
const failure = () => new Error('official_gemini_failed');
function assertActive(signal) { if (signal?.aborted) throw signal.reason ?? failure(); }

/** All system/developer text is joined explicitly: installed toHostMessages skips system roles. */
export function officialRequest(model, context, options = {}) {
  if (model.provider !== GEMINI_PROVIDER || model.api !== GEMINI_API || !GEMINI_MODELS.some(item => item.id === model.id)) throw failure();
  if (!Array.isArray(context.messages) || !context.messages.length) throw failure();
  const system = [context.systemPrompt, ...context.messages.filter(item => item.role === 'system').map(item => {
    if (typeof item.content === 'string') return item.content;
    if (!Array.isArray(item.content) || item.content.some(part => part.type !== 'text' || typeof part.text !== 'string')) throw failure();
    return item.content.map(part => part.text).join('');
  })].filter(value => value !== undefined && value !== '').join('\n\n');
  const toolChoice = options.toolChoice ?? 'auto';
  if (!['auto', 'none'].includes(toolChoice)) throw failure();
  const timeoutMs = Math.min(options.timeoutMs ?? 180_000, 180_000);
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) throw failure();
  return { model: model.id, messages: toHostMessages(context.messages, system), tools: toHostTools(context.tools ?? []),
    reasoning_effort: effortFor(options.reasoning ?? 'low'), timeout_seconds: timeoutMs / 1000, tool_choice: toolChoice };
}

export function officialAssistant(result, model, tools, toolChoice, timestamp = Date.now()) {
  const fields = new Set(['model', 'content', 'tool_calls', 'usage', 'raw_usage', 'conversation_id']);
  if (!result || typeof result !== 'object' || Object.keys(result).some(key => !fields.has(key))) throw failure();
  // The installed parser validates shape/usage even with an injected invoker.
  const data = parseBridgeOutput(JSON.stringify(result), 0);
  if (data.model !== model.id) throw failure();
  validateHostCalls(data, tools);
  if (toolChoice === 'none' && data.tool_calls.length) throw failure();
  const usage = data.usage, cached = usage.prompt_tokens_details?.cached_tokens ?? 0;
  const reasoning = usage.completion_tokens_details?.reasoning_tokens;
  if (reasoning !== undefined && (!Number.isSafeInteger(reasoning) || reasoning < 0)) throw failure();
  return { role: 'assistant', api: GEMINI_API, provider: GEMINI_PROVIDER, model: data.model,
    content: [...(data.content ? [{ type: 'text', text: data.content }] : []),
      ...data.tool_calls.map(call => ({ type: 'toolCall', id: call.id, name: call.function.name, arguments: JSON.parse(call.function.arguments) }))],
    usage: { input: usage.prompt_tokens - cached, output: usage.completion_tokens, cacheRead: cached, cacheWrite: 0,
      totalTokens: usage.total_tokens, ...(reasoning !== undefined ? { reasoning } : {}),
      // Pi requires this structure; prices are unknown and are not reported by this bridge.
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
    stopReason: data.tool_calls.length ? 'toolUse' : 'stop', timestamp,
    ...(typeof data.conversation_id === 'string' ? { responseId: data.conversation_id } : {}) };
}

/** The only replaced routes are the legacy Google alias; original SDK receivers stay intact. */
export function withOfficialGemini(runtime, { invokeBridge = installedInvoker, isInstalled = officialGeminiInstalled } = {}) {
  const complete = async (model, context, options = {}) => {
    assertActive(options.signal);
    if (!isInstalled()) throw failure();
    const timestamp = Date.now(), request = officialRequest(model, context, options);
    const result = await invokeBridge(request, options.signal, {
      command: '/opt/homebrew/bin/python3', args: [GEMINI_HELPER], script: GEMINI_HELPER,
      timeoutMs: request.timeout_seconds * 1000, graceMs: 5000, maxStdoutBytes: 16_000_000,
    });
    assertActive(options.signal);
    return officialAssistant(result, model, context.tools ?? [], request.tool_choice, timestamp);
  };
  const overrides = {
    hasConfiguredAuth(provider) { return provider === GEMINI_PROVIDER ? isInstalled() : runtime.hasConfiguredAuth(provider); },
    getModels(provider) {
      if (provider === GEMINI_PROVIDER) return GEMINI_MODELS;
      if (provider !== undefined) return runtime.getModels(provider);
      return [...runtime.getModels().filter(model => model.provider !== GEMINI_PROVIDER), ...GEMINI_MODELS];
    },
    getModel(provider, id) {
      return provider === GEMINI_PROVIDER ? GEMINI_MODELS.find(model => model.id === id) : runtime.getModel(provider, id);
    },
    completeSimple(model, context, options) {
      return model.provider === GEMINI_PROVIDER ? complete(model, context, options) : runtime.completeSimple(model, context, options);
    },
    streamSimple(model, context, options) {
      if (model.provider !== GEMINI_PROVIDER) return runtime.streamSimple(model, context, options);
      // Buffered official CLI inference: one authoritative final event, no synthetic token deltas.
      return (async function* () {
        const message = await complete(model, context, options);
        yield { type: 'done', reason: message.stopReason, message };
      })();
    },
  };
  return new Proxy(runtime, { get(target, property) {
    if (Object.hasOwn(overrides, property)) return overrides[property];
    const value = Reflect.get(target, property, target);
    return typeof value === 'function' ? value.bind(target) : value;
  } });
}
