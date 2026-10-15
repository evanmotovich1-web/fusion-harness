# Pi model transport for OpenCode

Local OpenAI-compatible transport only. OpenCode owns the agent and tool loop;
Pi's existing `ModelRuntime` owns DeepSeek/GLM/Grok protocols and locked OAuth
refresh. Gemini uses the installed official Antigravity CLI model-only helper,
with native tools disabled. No Pi coding-agent loop, new accounts, copied
credentials, or extra auth store is involved. SDK catalog entries mean configured
credentials; Gemini entries mean installed paths only, not verified login or
live entitlement. Bounded live checks passed through OpenCode's read-tool loop for DeepSeek V4 Pro, GLM 5.3, Grok 4.7, and the two official Gemini models. Those receipts prove those calls, not every catalog model or general quality.

Prerequisites: Node.js 22+, the installed SDK at
`/Users/evanmotovich/.local/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js`,
existing Pi auth/model files under `~/.pi/agent/`, and a parent-generated bridge
token in `~/.local/share/opencode-adw/provider-bridge/token`. The bridge refuses
to start without the token; it never generates it.

Gemini also requires `/Applications/Gemini.app/Contents/Helpers/agy`,
`/opt/homebrew/bin/python3`, the existing
`~/.local/share/gemini-login-bridge/gemini_login_bridge.py`, and the pure
`protocol.mjs`/`transport.mjs` modules in `~/.pi/agent/extensions/gemini-login/`.
Those modules are imported from fixed installed paths, not copied or edited.
Gemini credentials stay entirely with the official CLI; legacy Pi Google OAuth
is neither needed nor requested by this adapter.

Launch (foreground; parent owns installation and process lifecycle):

```sh
node /Users/evanmotovich/code/fusion-opencode-adw/adws/built/opencode-adw/providers/bridge.mjs --port 4198
```

Overrides: `PI_PROVIDER_BRIDGE_PORT`, `PI_PROVIDER_BRIDGE_TOKEN_FILE`, and
`PI_MODEL_RUNTIME_MODULE` (SDK module file path, useful for tests). Only
`127.0.0.1` may be bound; setting `PI_PROVIDER_BRIDGE_HOST` otherwise fails.
SDK creation uses `allowModelNetwork:false` and `refreshOnCreate:true` to load local credential availability. Disabling that availability refresh leaves the SDK's configured-provider snapshot empty.
Generation may refresh existing OAuth credentials through the SDK.
Catalog and generation requests retain the parent's local-only
`runtime.refresh({allowNetwork:false})` availability refresh.

`GET /health` returns only status/version without authentication.
`GET /v1/models` and `POST /v1/chat/completions` require
`Authorization: Bearer <bridge token>`. Host must match the bound IP/port.
Origin, if supplied, must be that exact HTTP origin; cross-site requests fail.
No CORS wildcard or preflight support is provided.

## Parent config shape

Allowlisted provider IDs: `deepseek`, `zai-coding-cn`, `xai`,
`google-gemini-cli`. Catalog IDs are always `provider/real-model-id` and include
`provider`, `modelId`, `name`, `context`, `maxTokens`, `input`, and `reasoning`.
Use the catalog's real IDs and limits rather than inventing model IDs.
The retained `google-gemini-cli` alias exposes only `gemini-3.8-flash` and
`gemini-4-argon`, using `api:gemini-login-cli`, `transport:official-cli`,
`availability:installed-paths-only`, and `loginVerified:false`. Context/output
limits are declarations from the installed extension, not measured CLI limits.

For each catalog entry the parent can produce this OpenCode shape (replace
placeholders with catalog values; the API key is the local bridge token):

```json
{
  "provider": {
    "pi-deepseek": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "DeepSeek · existing connection",
      "options": {
        "baseURL": "http://127.0.0.1:4198/v1",
        "apiKey": "<parent supplies bridge token>"
      },
      "models": {
        "<real-model-id>": {
          "id": "deepseek/<real-model-id>",
          "name": "<catalog display name>",
          "limit": { "context": 128000, "output": 16384 }
        }
      }
    }
  }
}
```

OpenCode's resolved provider API reports the qualified model `id` as its API-model-name override. The
bridge accepts both fully qualified API names and unique unqualified real IDs;
ambiguous IDs fail explicitly, with no fallback provider. Display names are
never routing IDs. Installed OpenCode provider IDs are `pi-deepseek`, `pi-glm`, `pi-grok`, and `pi-gemini`; the installer maps each to its exact upstream alias. Configuration preserves existing OpenAI and MCP entries, and uses a private local-token file placeholder rather than copying provider credentials.

The bridge is supervised by `com.evan.opencode-provider-bridge` in the user's LaunchAgents. Its local metadata is at `~/.local/share/opencode-adw/provider-bridge/`. `GET /health` proves service reachability; it does not prove an inference call. The successful mixed-model UI run `44de474d` used GLM 5.3 as builder and Gemini 3.8 Flash as reviewer, with explicit skipped checks.

## Supported transport and limits

- Text content strings and text arrays; ordered system/developer/user messages;
  assistant reasoning; multiple function calls and their tool results; JSON
  function-parameter schemas. Images/audio and unsupported content fail explicitly.
- Nonstream JSON and native Pi streaming text/reasoning SSE. Tool calls are
  emitted as complete indexed deltas after the final SDK message so OpenCode
  can execute every call. Final reasons are `stop`, `length`, or `tool_calls`.
  `stream_options.include_usage` adds an OpenAI usage chunk before `[DONE]`.
  Official Gemini is buffered: one final helper result is adapted into SSE,
  with no invented token deltas or streaming-latency claim. Helper model identity,
  usage counters, declared host-tool names and JSON argument objects are checked.
- Default output budget 4096, clamped to model maximum. Explicit positive caller
  budgets are preserved up to the model maximum. Reasoning defaults to `low`;
  `reasoning_effort` or `provider_options[provider].reasoning` can select a level.
  Only recognized options reach the SDK; caller keys/headers never do.
  Gemini effort maps to low/medium/high. Its installed helper does not expose
  max-output-token or sampling controls, so these SDK budgets/settings cannot be
  enforced on CLI inference. Tool schemas are sent intact; OpenCode remains
  responsible for validating and executing tool arguments.
- Tools support `tool_choice:auto|none`; forced/required tools, legacy functions,
  structured response formats, stop sequences, and multiple choices fail.
- 4 MiB request body, 180-second request deadline, eight active generations.
  Disconnects/timeouts abort the SDK signal; excess concurrency returns 429.
  Provider errors are fixed generic codes, never raw provider messages.
  Gemini uses the installed bounded detached-process-group transport, absolute
  Python/helper paths, a deadline at most 180 seconds, and five-second kill grace.
- A memory-only 30-minute assistant cache retains complete native signatures,
  bounded to 256 entries/16 MiB. Keys include the resolved model, normalized
  visible text, and complete tool-call IDs/names/arguments. Returned signed
  messages survive clients stripping reasoning/signature fields. Legacy Google
  API tool history missing from this cache returns 409 `assistant_history_unavailable`;
  DeepSeek reasoning tool history requires a cache hit or supplied reasoning.
  Restart/expiry/eviction can therefore require a fresh conversation. The bridge
  never fabricates signatures, persists requests, or executes tools.
  Official CLI Gemini history needs no legacy Google API signatures or cache hit.

Tests (no provider calls, auth files, resident server, or credential refresh):

```sh
node --test /Users/evanmotovich/code/fusion-opencode-adw/adws/built/opencode-adw/providers/*.test.mjs
```

---
Governed by AGENTS.md — see the repository AGENTS.md for shared rules.
