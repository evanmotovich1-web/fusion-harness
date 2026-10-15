# Gemini through an existing official-client login

This optional integration routes Gemini 4 Argon and Gemini 3.8 Flash through the installed official `agy` client instead of confusing its saved login with an API key, Vertex credentials, or a retired Gemini CLI endpoint. Pi and Hermes remain responsible for executing their own declared tools. It does not copy credentials, change subscriptions, or purchase credits.

## Requirements and installation

Use a supported installed official `agy` client and its own authorized account. Confirm the exact model and available effort levels with that client's `models` command. The tested installation resolves `agy` at `/Applications/Gemini.app/Contents/Helpers/agy`; `GEMINI_LOGIN_CLI` can select another authorized installation. Missing client or model access is a real blocker, not permission to spoof client headers.

Copy the reviewed source from this directory into these runtime locations:

- `agents/host-model-bridge.md` to `~/.gemini/agents/host-model-bridge.md`. This definition is required by the bridge's `--agent host-model-bridge` invocation; retain `tools: []`, `kind: local`, and `model: inherit` so host tools remain output requests and the explicit CLI model is inherited.
- `bridge/gemini_login_bridge.py` to `~/.local/share/gemini-login-bridge/gemini_login_bridge.py`.
- `pi/index.ts`, `pi/protocol.mjs`, and `pi/transport.mjs` to `~/.pi/agent/extensions/gemini-login/`.
- `bridge/provider/` to the selected Hermes profile's `plugins/model-providers/gemini-login/` directory. Installing for the default profile does not modify other profiles.

Back up configuration privately before changing it. If Pi already loads `npm:@qraxiss/pi-gemini-auth`, exclude only that conflicting package's extensions, preserving other packages and credentials:

```json
{"source":"npm:@qraxiss/pi-gemini-auth","extensions":[]}
```

Pi supports both `gemini-login/gemini-4-argon` and `gemini-login/gemini-3.8-flash`, plus the same exact model IDs under the compatibility provider prefix `google-gemini-cli/`. Do not silently substitute another model. To select the Hermes provider, use provider `gemini-login` and model `gemini-3.8-flash` or `gemini-4-argon`.

Start a fresh Fusion/Pi/Hermes session after installing. Fusion-harness catalogues and children explicitly load only the selected Gemini adapter while retaining `--no-extensions`; other providers keep their existing clean-room behavior. A rejected catalogue promise remains cached for that host and requires a fresh host, not a reconnect loop.

## Boundaries

This adapter supports text and host tool calls, not image/audio/file content. Native completion is buffered rather than token-by-token streaming. It requires a complete successful terminal result, the exact selected model and agent, validated tool names/object arguments, and usable content; partial output, native tool events, stderr, cancellation, timeout and malformed output are failures. Native tool-event rejection and custom-agent settings are not independent proof of OS confinement; the host must retain its own permission boundaries.

Host maximum reasoning maps to the highest supported native effort, High for these two models, without changing the user's global preference. Literal `none`/`minimal` map to Low, not true reasoning-off. An unset override uses the bridge's explicit High default. Monetary zero fields do not independently prove free provider usage; the official client's account policies remain authoritative.

## Verification

Python unit tests: run `python3 -m unittest discover -s bridge/tests -v` in a Hermes Python environment so its provider base classes are available. Pi tests: run `npm install --ignore-scripts` and `npm test` in `pi/`; the test dependencies are pinned to the installed SDK used for qualification. Fusion-harness catalogue/child regressions are under `extensions/fusion-harness/tests/child-*-gemini.test.ts`.

The native JSON fixture is captured output with personal working-directory and opaque conversation identity redacted. It is explicitly not fresh inference evidence. Initial local live qualification performed one real host file read for each model in default Hermes, Claude-Codex-Fusion/Pi, and Fusion-harness `runChild` (n=6 checks; confidence=high for those checks only, not a full multiagent mission). Revalidate the actual installed client/account and current host tool results before making a new live-provider claim.

---
Governed by AGENTS.md — see the vault's AGENTS.md for shared rules.
