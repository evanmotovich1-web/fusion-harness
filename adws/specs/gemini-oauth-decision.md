# Gemini OAuth 2.0 — Direction Decision (task 1.b)

Date: 2026-09-30 · Decider: GLM (architect slot) · Status: **DECIDED — O1: google-vertex via Application Default Credentials (ADC)**

Evan's ask: "add the gemini oauth2.0 for gemino api key, to the facty as one of the modles choies" — Gemini usable in the fusion-harness ("the factory") through Google OAuth 2.0 instead of a paid `GEMINI_API_KEY`, as one of the model choices.

Task 2.b (sol) implements exactly this decision. Nothing in this document authorizes edits outside the files named in the plan.

---

## 1. The option space, verified against THIS machine

### What is dead: the free Gemini CLI / Antigravity OAuth seats

- Installed pi is **0.99.1** (`/Users/evanmotovich/.local/lib/node_modules/@earendil-works/pi-coding-agent/package.json`).
- pi 0.70.6 removed "Google Gemini CLI and Google Antigravity built-in login, default model, documentation, and example extension support" (CHANGELOG.md:1954).
- pi 0.71.0 breaking change: "Removed built-in Google Gemini CLI and Google Antigravity support. Existing configurations using those providers must switch to another supported provider." (CHANGELOG.md:1904).
- 0.99.1 > 0.71.0, so `google-gemini-cli/*` and `antigravity/*` slots cannot resolve. Any plan built on them fails at stack validation. (My own phase-1 proposal assumed the old seat; that assumption is corrected here.)

### The three real options

| | O1 — built-in `google-vertex` + ADC OAuth | O2 — custom OAuth provider extension | O3 — `google` provider |
|---|---|---|---|
| OAuth 2.0? | Yes. Google ADC (user-account OAuth tokens, refreshed by the Google auth library) | Yes in principle | No. API key only (`GEMINI_API_KEY`, pi docs/providers.md:40) |
| Child-visible? | Yes. Built-in provider; `pi --no-extensions --list-models` lists it once authed | **No.** Extensions never load in `--no-extensions` children | Yes |
| Passes `applyStack`? | Yes | **No** — rejected at the third check | Yes (but not OAuth) |
| Touches global config? | No repo/extension changes; env vars + one `gcloud` login (machine-level, Evan-run) | Would need an extension in this repo (rejected anyway) | n/a |
| Verdict | **CHOSEN** | **REJECTED** (mechanism, not preference) | Not OAuth; stays as the existing API-key path |

### Why O2 is rejected on mechanism, not taste

The harness validates every stack slot three ways before a session starts (`extensions/fusion-harness/fusion-harness.ts:370-381`):

1. `ctx.modelRegistry.find(provider, id)` — registered in the parent,
2. `ctx.modelRegistry.hasConfiguredAuth(model)` — auth configured,
3. `childCatalogue.has(slot.model)` — the model appears in `pi --no-extensions --list-models` output (the `childVisibleModels` probe, fusion-harness.ts:350-362).

A provider registered by any extension (the only way to add an OAuth `/login` flow — pi docs/custom-provider.md:14,18 "A provider with native or legacy OAuth configuration... Call `pi.registerProvider()` from the extension factory") passes checks 1–2 in the parent but **fails check 3**, because clean-room children are launched with `--no-extensions`. The stack then dies at startup with "not visible to clean-room children". `models.json` cannot rescue this: it configures endpoints/API keys for supported APIs, not OAuth login flows (custom-provider.md:5-13). **Therefore: no fusion-harness extension source may be used to deliver Gemini OAuth. This is a hard rule for task 2.b.**

---

## 2. The chosen option, in full

### Exact slot ids (from the installed catalog)

Provider id: `google-vertex`. Catalog models on this install (`pi-ai/dist/providers/google-vertex.models.js`, `GOOGLE_VERTEX_MODELS` keys):

```
gemini-2.5-flash        gemini-2.5-flash-lite   gemini-2.5-pro
gemini-3-flash-preview  gemini-3.1-flash-lite   gemini-3.1-pro-preview
gemini-3.1-pro-preview-customtools
gemini-3.5-flash        gemini-3.5-flash-lite   gemini-3.6-flash
gemini-3.7-flash        gemini-3.8-flash
gemini-flash-latest     gemini-flash-lite-latest
```

**Recommended slot for the stack: `google-vertex/gemini-3.7-flash`** — the same model the shipped fusion stack already uses as `flux` (`.pi/fusion-harness/model-stack-fusion.yaml`), so OAuth and API-key stacks are behaviorally comparable.

Model facts verified from the catalog entry: api `google-vertex`, baseUrl `https://{location}-aiplatform.googleapis.com`, reasoning true, **supported thinking levels: `low | medium | high` only** (`off`, `minimal`, `xhigh`, `max` map to null — the stack YAML must say `thinking: medium`), context 1,048,576, max out 65,536, input text+image, cost $0.75/M in, $3.75/M out, $0.075/M cache-read.

### How pi decides google-vertex is authed (the exact mechanism)

`pi-ai/dist/env-api-keys.js:126-137` — for `google-vertex`, auth is "configured" when ALL of:

1. ADC credentials exist: `GOOGLE_APPLICATION_CREDENTIALS` set and its file exists, **or** `~/.config/gcloud/application_default_credentials.json` exists (env-api-keys.js:34-58);
2. `GOOGLE_CLOUD_PROJECT` or `GCLOUD_PROJECT` is set;
3. `GOOGLE_CLOUD_LOCATION` is set.

Then the resolved pseudo-key `<authenticated>` is treated as a placeholder by the Vertex stream adapter (`isPlaceholderApiKey` matches `/^<[^>]+>$/`), which falls through to `createClient(model, resolveProject(...), resolveLocation(...))` — the ADC OAuth client (`dist/bundle/chunks/google-vertex-AE36YXJU.js`, `resolveApiKey`/`createClient`). ADC tokens are OAuth 2.0 refresh-token credentials obtained by `gcloud auth application-default login` under Evan's Google account.

### Env vars (names only — never values)

```
GOOGLE_CLOUD_PROJECT     # or GCLOUD_PROJECT; the GCP project id with Vertex AI API enabled
GOOGLE_CLOUD_LOCATION    # e.g. us-central1
# optional alternative to ADC login: GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

The justfile already does `set dotenv-load := true`, so these belong in `.env` (documented in `.env.example` by task 2.b; never committed with values).

### Manual steps Evan runs once (not automated by any agent)

1. `brew install google-cloud-cli` — **gcloud is NOT installed on this Mac today** (verified: `which gcloud` empty).
2. Get a GCP project with the Vertex AI API enabled (console or `gcloud projects create` + `gcloud services enable aiplatform.googleapis.com`). Billing applies — Vertex Gemini is **not free** (unlike the removed Cloud Code Assist seat). Rates above.
3. `gcloud auth application-default login` — browser OAuth 2.0 flow; writes `~/.config/gcloud/application_default_credentials.json`.
4. Add the two env vars to `.env`.
5. Verify: `pi auth check --provider google-vertex` prints `ready`, and `pi --no-extensions --list-models` shows `google-vertex` rows (the listing is auth-filtered — on this machine today it shows only deepseek, openai-codex, xai, zai-coding-cn; google-vertex appears only after steps 1–4).

Until then the current state is a clean failure: `pi auth check --provider google-vertex` → `not_ready` (verified today), and a stack using the slot must fail startup with an actionable message pointing at these steps — that failure path is a required validation in 2.b, not a bug.

### Deliverable shape for task 2.b (repo-only changes)

- `.pi/fusion-harness/model-stack-gemini-oauth.yaml` — 2–5 valid slots, exactly one `architect: true`, exactly one non-architect `primary: true`; the Gemini OAuth slot(s) use `google-vertex/gemini-3.7-flash` (or another catalog id above) with `thinking: medium` (never off/minimal/xhigh/max); remaining slots reuse existing authed providers (anthropic/openai-codex/xai/fireworks per existing stacks).
- One justfile recipe (e.g. `fusion-gemini`) launching `just fh-stack .pi/fusion-harness/model-stack-gemini-oauth.yaml`; no other recipes touched (terra's 4.b owns the adw recipes in the same file later — different lines, serialized writers).
- `.env.example` + README: the three env vars, the five manual steps, the not-free billing note, the `pi auth check`/`--list-models` verification, and the explicit statement that `GEMINI_API_KEY` (google/AI Studio path) remains independent and optional.
- Evidence file `adws/specs/gemini-oauth-evidence.txt`: `pi auth check --provider google-vertex` output before (not_ready) and, if Evan has logged in by then, after; `--list-models` google-vertex rows; **never any token, key, or credential value**.

### Non-goals / hard rules carried forward

- No edits to `extensions/` source for this feature (the O2 mechanism makes any such edit worthless anyway).
- No writes to `~/.pi/agent/models.json` or `auth.json` by any agent; login is Evan's manual act.
- No token values in any file, log, or report.
- Do not touch `.pi/fusion-harness/model-stack-fusion*.yaml` (the API-key stacks stay as they are).

---

## 3. Evidence index (all verified 2026-09-30 on this machine)

| Claim | Source |
|---|---|
| pi 0.99.1 installed | pi-coding-agent/package.json |
| Gemini CLI / Antigravity OAuth removed | pi-coding-agent/CHANGELOG.md:1904 (0.71.0 breaking), :1954 (0.70.6) |
| Vertex = built-in provider with these Gemini models | pi-ai/dist/providers/google-vertex.models.js `GOOGLE_VERTEX_MODELS` |
| gemini-3.7-flash metadata (thinking low/med/high, 1M ctx, cost) | same catalog entry |
| ADC auth rule (ADC file + project + location → authed) | pi-ai/dist/env-api-keys.js:126-137, :34-58 |
| Placeholder key falls through to ADC client | pi-coding-agent/dist/bundle/chunks/google-vertex-AE36YXJU.js (`resolveApiKey`, `isPlaceholderApiKey`, `createClient`) |
| OAuth login flows require an extension | pi-coding-agent/docs/custom-provider.md:12-18 |
| Stack slots must be child-visible; extension-registered models rejected | extensions/fusion-harness/fusion-harness.ts:350-362, :370-381 |
| `pi auth check --provider google-vertex` → not_ready today | run 2026-09-30 |
| `--list-models` auth-filtered (no google rows today) | run 2026-09-30, 20 rows across 4 authed providers |
| gcloud absent; ADC file absent | `which gcloud` empty; `~/.config/gcloud/application_default_credentials.json` missing |
| google (AI Studio) = `GEMINI_API_KEY` only | pi docs/providers.md:40 |
