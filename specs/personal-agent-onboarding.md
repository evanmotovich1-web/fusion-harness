# Personal agent onboarding

Specification only. Nothing in this document is implemented as a consumer application.

Legend:

- **Existing** — code in this repository today.
- **Proposed** — required product work, not present.
- **External** — input or service that does not exist here and is not authorized by this spec.
- **Unverified** — claimed or requested capability without primary-source evidence.

This file is the only authorized write for this collaboration. It does not scaffold an application, add `/fh-setup`, change dependencies, or alter harness execution. `/fh-setup` and the Pi TUI are not the requested app.

Measured repository facts for this collaboration (harness card, not re-derived): `blocked_dirty`; HEAD `main` at `bf3292f4bdd420d732e9fb287b9debe70056444e`; ahead 5, behind 0; untracked `EVANAI_VISION_AND_ROADMAP.md` and `prompts/full-sweep-2026-09-02.md`. Those files are out of scope here.

---

## 0. Product boundary

**Existing.** This repository is a Pi coding-agent extension, not an authenticated app (`package.json:1-14`, `README.md:17-19`). There are no JSX/TSX/Vue/Svelte sources. The only HTML under `specs/` is the fusion-harness vspec. Provider env vars in `.env.example:1-26` are operator model keys, not user login.

**Proposed.** A chat-first consumer application with one personal agent. Login, then onboarding, then a ChatGPT-work-style workspace that can use tools. Optional multi-model fusion is an internal deep mode, not a second user-facing identity.

**External.** The actual app repository is unknown (**I1**). Do not invent an `app/` tree in this repo. Implementation paths below are conditional on identifying that surface.

| Code | Capability | Evidence | Product work |
|---|---|---|---|
| **F1** | Consumer UI | Boot chrome is a Pi entry renderer (`extensions/fusion-harness/fusion-harness.ts:1115-1128`) | Authenticated chat, video, voice, background, artifacts, approvals |
| **F2** | Agent execution | `runChild` spawns `pi --mode json -p` with declared skills only (`extensions/fusion-harness/modules/child-runner.ts:46-110`) | Durable application-facing runtime adapter; do not expose child argv to clients |
| **F3** | Providers | Startup checks registry, auth, and clean-room visibility (`extensions/fusion-harness/fusion-harness.ts:353-391`; `README.md:113-113`) | Capability discovery and adapters. YAML is not enough |
| **F4** | Continuity | Fresh process-local session IDs; directories deleted on shutdown (`extensions/fusion-harness/fusion-harness.ts:500-518`) | App-owned durable threads. Do not promise restart persistence from harness comments (`extensions/fusion-harness/fusion-harness.ts:552-557` conflicts with `extensions/fusion-harness/fusion-harness.ts:500-518`) |
| **F5** | Knowledge retrieval | `KnowledgePacket` with hits, hash, status (`extensions/fusion-harness/modules/knowledge-base.ts:43-61`) | Tenant-scoped sources, correction, versions, measured improvement |
| **F6** | Capture | Opt-in, secret scan, vault lock, run-id idempotency (`extensions/fusion-harness/modules/knowledge-ingest.ts:132-181`) | Reversible promotion. Capture is not training (`extensions/fusion-harness/modules/knowledge-config.ts:3-4`) |
| **F7** | Computer use | Isolated Chromium, not desktop (`extensions/fusion-harness/skills/computer-use/SKILL.md:8-9`; `README.md:162-162`) | Authenticated approvals plus separate cloud-browser and paired-desktop executors. Request booleans are not proof of consent (`extensions/fusion-harness/skills/computer-use/browser.mjs:14-19`) |
| **F8** | Isolation | Command classifier, not an OS sandbox (`extensions/fusion-harness/modules/child-repo-guard.ts:17-22`) | Real isolation, tenancy, billing, pairing, revocation |

### Architecture (proposed services, not implemented)

| Code | Owner | Contract |
|---|---|---|
| **A1** | Chat/voice application | Onboarding and conversations. Sends intent and explicit approvals. Shows execution location, progress, results, failures. Never holds server-side provider credentials or launches tools itself |
| **A2** | Session service | Identity, tenant auth, versioned profiles, durable threads, onboarding progress, idempotent jobs. Resolves credentials by reference |
| **A3** | Runtime adapter | Authorized turn in; ordered text / optional provider-exposed reasoning summary / tool-request / result / failure / completion out. Cancellation reaches the executor |
| **A4** | Model adapters | Normalize provider I/O. Declare text, vision, tools, streaming, TTS. Reject unsupported requests. Switching providers does not rename the agent or erase history |
| **A5** | Knowledge service | Tenant-authorized provenance-bearing evidence. Imported text is untrusted. Proposed captures ≠ accepted knowledge |
| **A6** | Permission service and executors | Authorize tenant, user, task, executor, scope, expiry. Sensitive approvals bind to exact parameters. Agents cannot mint approval by setting a boolean |
| **A7** | Hosting service | Cloud runtime lifecycle, price acceptance, spend caps |
| **A8** | Paired-device service | Local computer pairing and revocation. Cloud up ≠ laptop awake |

---

## 1. Why the harness cannot ship this product

The harness can supply **backend pieces**: stack validation, retrieval/capture semantics, browser computer-use with approval flags, cancel-via-abort, and a pattern for streaming tool/thinking/text.

It cannot currently deliver:

| Requested | Why not here |
|---|---|
| Login | No IdP, session store, or account lifecycle. `.env.example` is model keys |
| Autoplay welcome video | README YouTube links only (`README.md:5-11`). No in-app player, captions, or poster |
| Working voice | No TTS/STT, no mic permission surface |
| Always-on rental sandbox | No provisioner, billing, tenant isolation, or spend enforcement. `child-repo-guard.ts` is not a VM |
| Native desktop control | Computer-use is one-shot Chromium (`extensions/fusion-harness/skills/computer-use/SKILL.md:8-9`, `extensions/fusion-harness/skills/computer-use/SKILL.md:43-43`). Browser closes when the command exits |
| Durable chat across restarts | Slot sessions are process-local and deleted on shutdown (`extensions/fusion-harness/fusion-harness.ts:506-518`; `README.md:310-311`) |
| “Any provider” by config | `MODEL_RE` checks `provider/id` shape only (`extensions/fusion-harness/modules/model-stack.ts:66-66`, `extensions/fusion-harness/modules/model-stack.ts:160-160`). Auth and clean-room visibility are Pi registry gates (`extensions/fusion-harness/fusion-harness.ts:370-372`) |

`x-research.ts` contains a direct xAI search integration (`extensions/fusion-harness/modules/x-research.ts:83-97`). The harness otherwise delegates model inference to Pi rather than implementing general provider adapters.

---

## 2. Identity (three namespaces)

User-facing agent identity is independent of optional fusion.

| Code | Name | Rules |
|---|---|---|
| **N1** | `agent_display_name` | User-chosen, 1–48 Unicode. Chat header only. Never written into stack YAML |
| **N2** | `slot_name_seed` | Generated from stable profile identity before U7, not the display name collected at U9. Lowercase, replace non-`[a-z0-9_-]` with `-`, reserve suffix space within 16 characters, fallback `agent`. Must match `SLOT_NAME_RE` (`extensions/fusion-harness/modules/model-stack.ts:65-65`, `extensions/fusion-harness/modules/model-stack.ts:152-152`). Renaming N1 does not rebuild the stack |
| **N3** | App profile vs fusion YAML | Profile is the per-user document. A 2–5 slot stack is an optional generated artifact pinned to a profile revision. `reasoning_mode: single` needs one provider binding and no stack |

**Proposed.** One primary conversational agent on the hot path. Fusion/debate/collaborate remain off-path deep mode. This matches the existing stack split (exactly one non-architect `primary: true`, `extensions/fusion-harness/modules/model-stack.ts:221-223`) and the retrieved vault note that one surface should preserve context (`wiki/how-evan-drives-building-sessions.md:25-29`, evidence packet, not a file in this repo).

---

## 3. Onboarding sequence

**Proposed.** Auth first. Setup never starts logged out. Order is fixed:

`U0 login → U1 welcome video → U2 voice → U3 background → U4 second brain → U5 always-on hosting → U6 interests → U7 generate harness → U8 skill review → U9 name agent → U10 chat`

CREAO is not a wizard step. Provider choice is Settings. Before U7, A2 supplies an authorized default model binding from the application's service configuration (**I9**), with disclosed usage costs and data handling. If no default is available, U7 offers a Settings link to configure a binding and remains `awaiting_setup`. Never infer authorization from this repository's operator keys.

### U0 Login

- Logged out: auth only.
- Success → U1.
- Failure: inline error, retry. Do not open setup.
- **External I2:** IdP, session, logout, account deletion.

### U1 Welcome video

Inline player after login. Not a new tab. Not the README YouTube links.

| Event | Behavior |
|---|---|
| Autoplay | Muted, captions on, inline |
| Unmute | User gesture; captions remain |
| Skip | Immediate; `video_status=skipped` → U2 |
| Autoplay blocked | Large Play. Skip/Continue stay enabled |
| Playback failure | Retry + Continue without video → `video_status=failed` |
| Complete | `video_status=watched` → U2 |
| Reload | Resume playhead if saved; never re-run login |

Watch-to-end is not required. **External I3:** video file, `vtt` captions, poster, CDN.

### U2–U9 wizard chrome

- Progress over eight setup steps (U2–U9).
- Back allowed U2–U9. Back from U1 does not log out. Back from U2 does not autoplay U1.
- Persist server-owned state before leaving a step.
- Retry is per failed action. It must not duplicate agents or paid hosts.
- Kill/reload resumes persisted `current`: the next incomplete or deliberately reopened step, with saved answers intact.

### U2 Voice (preview)

Licensed sample clip, labeled **Preview**. `voice_live=false` until a later mic+TTS round-trip succeeds. **External I4:** licensed catalog.

### U3 Background

Chat-chrome theme preview. Not OS wallpaper. Not a fusion slot color.

### U4 Second brain

Connect vault/folder/URL, skip, or add later. Capture default **off** (`extensions/fusion-harness/modules/knowledge-ingest.ts:141-143`). Copy must not say the model is being trained.

### U5 Always-on hosting

Show location, price, operating policy, idle timeout if applicable, and monthly cap **before** provision. Decline skips rental, not execution setup. Use an authorized application-hosted on-demand runtime only if I9 provides one, or a separately paired local runtime. Without either, U7 remains `awaiting_setup`; answers and naming can still be saved, but chat actions stay disabled. Accept starts a provisioning job with Cancel only when P6 is operational. Until then, show hosting as unavailable and record interest only, without charges. Back after accept requests teardown and shows its confirmed result. Cloud host is not the user's computer. **External I5.**

### U6 Interests

Multi-select from a closed taxonomy. Examples: `college`, `real_estate`. Selection feeds skill mapping; it does not invent unshipped skills.

### U7 Generate harness

Idempotent job. User watches status. Success does not skip U8 or U9.

### U8 Skill review

| Status | Meaning |
|---|---|
| `installed` | Ready after a readiness check |
| `installing` | In progress; not claimed ready |
| `failed` | Retry that skill |
| `recommended` | Not installed, including unshipped school/study packs |
| `unavailable` | Missing runtime (e.g. desktop with no paired device) |

Computer-use, if installed, is labeled **Browser automation**, not desktop control.

### U9 Name

Sets **N1** display name. Empty blocked. Collision: reuse or rename.

### Returning users

| Condition | Land |
|---|---|
| Session valid, onboarding incomplete | Persisted `current` with saved answers |
| `onboarding_complete`, runtime healthy | U10. No video |
| Job failed or awaiting setup, later steps otherwise done | Relevant U7/U8 recovery screen; answers kept |
| Revisit video or a setup step | Help / Settings, not the full wizard |

---

## 4. Chat workspace (U10)

**Proposed.** One primary conversation. Optional right rail.

| Region | Contents |
|---|---|
| Left | Threads |
| Center | Streamed messages |
| Rail | Artifacts, browser view, approvals |
| Composer | Text. Voice input only if `voice_live` |
| Chip | `Cloud host` / `This computer (paired)` / `Browser only` / `Disconnected` |

Required behavior:

- Stream tokens. Keep any optional provider-exposed reasoning summary distinct from answers and tool activity. The terminal separates stream categories (`extensions/fusion-harness/modules/tui.ts:221-241`), but the application does not require or expose private reasoning.
- Tool rows visible as they start: name, running/done/failed, location.
- Artifacts open in the rail.
- Approvals are blocking UI, not prompt text. Mutation and sensitive acts are separate confirms (`extensions/fusion-harness/skills/computer-use/SKILL.md:37-41`; `extensions/fusion-harness/modules/cmd-workflows.ts:55-60`). Deny = no side effect. A6 enforces this in the service, not in the model prompt.
- Stop revokes new dispatches and aborts in-flight work (pattern `extensions/fusion-harness/fusion-harness.ts:1013-1048`, `extensions/fusion-harness/modules/child-runner.ts:20-20`, `extensions/fusion-harness/modules/child-runner.ts:243-243`, `extensions/fusion-harness/modules/child-runner.ts:267-289`). UI: Stopping → Stopped only after acknowledgement. Discard stale stream events. Cancellation cannot undo an already committed external action; report completed or uncertain effects rather than claiming rollback.
- Provider is a setting (`provider/id`). Switch keeps the thread. Unsupported tools are disabled, not skipped (browse pattern `extensions/fusion-harness/fusion-harness.ts:1262-1268` is reference only).
- Disconnected or unpaired desktop actions are disabled.

---

## 5. Profile, onboarding state, harness job

**Proposed** schemas (`schema_version: 1`). Persistence store does not exist in this repo.

```json
{
  "schema_version": 1,
  "profile_id": "uuid",
  "revision": 7,
  "agent_display_name": "Atlas",
  "slot_name_seed": "agent-a1b2",
  "voice_pref": { "voice_id": "…", "preview_only": true, "voice_live": false },
  "background_pref": { "theme_id": "…" },
  "interests": ["college", "real_estate"],
  "reasoning_mode": "single",
  "reasoning_mode_rationale": "default hot path; fusion optional; CREAO not adopted",
  "model_bindings": [{ "binding_id": "uuid", "model": "provider/id", "key_ref": "vault:…" }],
  "knowledge": { "roots": [], "capture_opt_in": false },
  "hosting": {
    "consent_version": null,
    "state": "not_requested",
    "spend_cap_usd_month": null
  },
  "active_stack_ref": null
}
```

`reasoning_mode` is `single` or `fusion`. It is not a CREAO flag. These are illustrative field values, not configured services or price quotes. Cap stays null until an actual plan and cap are accepted. A2 resolves knowledge roots from authorized source ids; clients cannot supply arbitrary server filesystem paths.

```json
{
  "schema_version": 1,
  "profile_id": "uuid",
  "revision": 12,
  "steps": [
    "welcome_video",
    "voice",
    "background",
    "second_brain",
    "hosting_consent",
    "interests",
    "generate_harness",
    "skill_review",
    "name_agent"
  ],
  "completed": ["welcome_video", "voice"],
  "current": "background",
  "step_data": {},
  "video_status": "watched"
}
```

U0 lives on the session service, not in `steps`. `second_brain` and `hosting_consent` are skippable. PUT-per-step is idempotent (`revision` guards writes). Persist `current` and the completed-step update atomically. Back-nav preserves answers; re-submitting changed runtime/skill inputs invalidates downstream generation/readiness but not unrelated naming or theme preferences. Completing U9 sets `onboarding_complete`; this does not override a failed or waiting runtime, and U10 must show that limitation.

```json
{
  "schema_version": 1,
  "job_id": "sha256(profile_id|profile_revision|selection_hash|generator_version)",
  "status": "pending",
  "blockers": [],
  "selection": {
    "candidates": ["computer-use"],
    "recommended_not_shipped": ["college-study", "real-estate-basics"]
  },
  "installation_results": [],
  "stack_yaml_ref": null,
  "generated_at": null
}
```

Idempotency: same inputs → same `job_id` → re-POST returns the existing record.

Job states: `pending → generating → validating → ready | ready_local | awaiting_setup | failed`. A failed or waiting job can retry with the same idempotency identity and a recorded attempt, never a duplicate agent.

Truthful readiness:

- Single mode validates its selected model binding, authentication, declared capabilities, and a real runtime readiness check. It generates no fusion YAML.
- Fusion mode additionally validates generated YAML with `loadModelStack` and checks registration, authentication, and clean-room visibility for **every required slot**, matching existing startup checks (`extensions/fusion-harness/fusion-harness.ts:355-391`). The proposed service also checks per-model capability compatibility. One working key does not make a fusion stack runnable.
- `ready` requires successful mode validation and an authorized, reachable cloud or application-hosted runtime. `ready_local` requires the same checks against an explicitly paired, reachable local runtime. Declining rental alone qualifies for neither.
- Required skill failures block readiness. Optional failed skills remain visibly unavailable. Neither model credentials nor a `SKILL.md` file prove that browser binaries, tool services, or approval enforcement work.
- `awaiting_setup` carries actionable blockers such as `provider_binding_missing` or `executor_unavailable`. `failed` carries validation or installation errors without credentials. Neither status displays a working agent.

Each `installation_results` entry records skill id/version, executor id, status, and readiness-check evidence. Only a successful check can yield `installed`. The job's `selection` remains a plan, not an installation receipt.

---

## 6. Skills

**Existing.** One shipped skill directory: `extensions/fusion-harness/skills/computer-use/` with `SKILL.md`. The stack validator accepts existing direct files; directory entries resolve to `SKILL.md`. It does not validate skill behavior or install prerequisites (`extensions/fusion-harness/modules/model-stack.ts:195-200`).

**Proposed.** `selectSkillPacks(interests, manifest)` is pure: stable sort, hashed into `selection_hash`. Manifest lists **shipped** packs only.

| Interests | Installation candidates, not yet installed | Recommended, `available: false` |
|---|---|---|
| `[college]` | `[computer-use]` | college/study packs (unshipped) |
| `[real_estate]` | `[computer-use]` | real-estate basics (unshipped) |
| `[college, real_estate]` | `[computer-use]` | both unshipped packs |

An interest match never writes `installed`. The installer checks the candidate's versioned files, runtime prerequisites, and permitted tool operation, then emits the result used by U8. Computer-use can fail these checks despite being shipped. **External I8:** real school/study/real-estate pack content and readiness tests before those packs can become `installed`.

---

## 7. Knowledge improvement (not training)

**Existing.** Retrieval is bounded lexical evidence (`extensions/fusion-harness/modules/knowledge-config.ts:12-21`, `extensions/fusion-harness/modules/knowledge-config.ts:74-74`, `extensions/fusion-harness/modules/knowledge-config.ts:109-109`; `extensions/fusion-harness/modules/knowledge-base.ts:472-472`, `extensions/fusion-harness/modules/knowledge-base.ts:478-478`). Capture is opt-in, secret-scanned, lane-refused for `trading` / `sessions` / `agent-memory`, idempotent by run marker, atomic write, vault-locked (`extensions/fusion-harness/modules/knowledge-ingest.ts:25-27`, `extensions/fusion-harness/modules/knowledge-ingest.ts:47-51`, `extensions/fusion-harness/modules/knowledge-ingest.ts:105-118`, `extensions/fusion-harness/modules/knowledge-ingest.ts:132-181`). Default dest `wiki/agent-learnings.md` (`extensions/fusion-harness/modules/knowledge-config.ts:21-21`).

**Proposed.** “Gets better over time” means curated evidence plus verifier-gated retrieval config. Weights do not change.

- Capture carries provenance (source, time, consent) and enters a candidate store, not active retrieval. Dedup by normalized content hash within the tenant.
- A5 resolves selected sources to authorized tenant roots before any ingestion or evaluation. Neither the proposing agent nor a better verifier score can grant access to another root or tenant.
- Candidate notes need source/consent validity, secret and conflict checks, and independent verification against source evidence before acceptance. Unresolved corrections require user confirmation. Regression checks cover existing expected answers and the new note's intended retrieval behavior.
- Version the accepted corpus separately from retrieval configuration. Active state records `corpus_version`, `config_hash`, evaluator version, current best score, and attempt history. The proposer cannot edit verifier code or expected results.
- For configuration changes on the same corpus/evaluator version, promote only if the frozen retrieval score strictly exceeds `best_score`. Ties keep the incumbent. Corpus additions must pass the note checks and cause no regression on existing cases. Rebaseline explicitly when the corpus or evaluator changes; never compare incompatible scores.
- Correction marks the old note superseded and promotes the verified replacement. Deletion immediately excludes a note from retrieval, indexes, caches, and future prompt assembly. Users may permanently delete an individual note without deleting their account. Disclose backup-retention limits and that already-sent model requests cannot be recalled.
- Rollback atomically restores an accepted `(corpus_version, config_hash)` pair. Rejected or harmful notes may remain quarantined for audit only while retention consent allows; they are not retrieved. Global deletion/supersession exclusions apply to every historical version, so rollback never resurrects removed knowledge.
- Budgets: attempts/day, tokens/day, file ceiling (existing default 2000, `extensions/fusion-harness/modules/knowledge-config.ts:16-16`). Over budget fails closed with a reason.
- Retrieved text stays untrusted. Citations `path:start-end` only for claims that use it.

Verifier / best-so-far / stop condition follow the retrieved loop definition (`wiki/loop-playbook.md:20-30`, evidence packet, not a file in this repo).

Multi-tenant gap: the existing lock serializes access by canonical vault path (`extensions/fusion-harness/modules/knowledge-ingest.ts:47-51`); it is not authorization. A5 must enforce distinct authorized roots, key namespaces, and storage permissions per tenant. Preserve canonical-path exclusion rather than allowing two tenant-specific locks to write the same physical vault.

---

## 8. Runtime and providers

**Existing.** The harness is an orchestrator, not a model runtime. It shells to Pi (`extensions/fusion-harness/modules/child-runner.ts:4-7`, `extensions/fusion-harness/modules/child-runner.ts:76-110`). YAML validates syntax, not availability (`extensions/fusion-harness/modules/model-stack.ts:66-66`, `extensions/fusion-harness/modules/model-stack.ts:133-133`, `extensions/fusion-harness/modules/model-stack.ts:160-160`). Adding a provider requires (1) a Pi provider implementation, (2) auth, (3) clean-room visibility (`README.md:113-113`). There is no `supports(feature)` API. Tool events store name and argument only; tool results stay in the child (`extensions/fusion-harness/modules/child-runner.ts:203-213`; `extensions/fusion-harness/modules/runtime.ts:98-98`). Errors: `stopReason` / `errorMessage` (`extensions/fusion-harness/modules/runtime.ts:114-115`); stderr diagnostics mode `0600` (`extensions/fusion-harness/modules/child-process-contract.ts:16-24`). Cancellation: `AbortSignal` → SIGTERM → SIGKILL after 5s, process group (`extensions/fusion-harness/modules/child-runner.ts:20-20`, `extensions/fusion-harness/modules/child-runner.ts:243-243`, `extensions/fusion-harness/modules/child-runner.ts:267-289`).

The application needs an adapter around `runChild` or another runtime: the existing function alone does not supply durable application threads or complete tool-result events. Durable conversations do not require a permanently running process per user.

**Proposed** adapter seam:

```ts
interface ProviderAdapter {
  id: string;
  listModels(): Promise<ModelInfo[]>;
  stream(req: ChatRequest, signal: AbortSignal): AsyncIterable<StreamEvent>;
  invoke(req: ChatRequest, signal: AbortSignal): Promise<ChatResult>;
  supports(modelId: string, feature: ProviderFeature): boolean;
}
```

`ChatRequest` carries the selected model id, provider-neutral history (including tool-call ids and results), allowed tool schemas, and output limits. `StreamEvent`: `text` | `reasoning_summary` (optional, only if exposed by the provider) | `tool_call` | `done`. Typed errors: `auth | rate_limit | timeout | aborted | provider`. A3 executes authorized calls through A6 and returns their results to the adapter in the next request. Each adapter owns tool-schema translation. Capability discovery is per model, not just per provider. Private reasoning is not required for the chat UI.

“Addable to any model provider” means: new adapters plus declared capabilities, without rewriting A1. It does not mean every model supports tools, TTS, or computer use.

---

## 9. CREAO (unverified; not adopted)

Pre-write inspection found no CREAO integration or primary-source documentation in the repository. The research tasks used local read-only evidence and no network requests, so current vendor docs, API, pricing, and provider list remain **unverified**. Do not reinterpret CREAO as CrewAI, as fusion-harness, or as a shipped engine.

**Recommendation:** do not take a CREAO dependency. Default runtime is a replaceable adapter behind A3, with one primary conversational agent. Revisit only after primary-source docs exist (**I7**) and the proof below passes.

Conditional adopt checklist (all must be supported by primary docs or the tested adapter design):

1. Documented single-agent streaming runtime with tool/function calling.
2. Arbitrary providers via an adapter, with an exact provider list.
3. Cancellation and typed errors.
4. Durable sessions independent of process lifetime.
5. Gated/approvable tools (approve-before-mutate).
6. Clear licensing, hosting costs, tenant isolation, credential handling, data residency, and conversation/knowledge export without vendor lock-in.

Proof-of-integration (before any adopt):

1. Stream a multi-turn conversation and one tool round-trip against ≥2 providers.
2. Abort mid-stream: no further deltas, aborted state.
3. `supports(modelId, "tools")` / `supports(modelId, "streaming")` match reality for both capable and incapable models.
4. Bad key and rate-limit surface as typed errors.
5. Close runtime, resume by token, conversation intact; export it into the application-owned format.
6. Forged/expired approvals and cross-tenant access are rejected by A6 before CREAO can execute a tool.

Until that passes, `reasoning_mode_rationale` stays “CREAO unverified / not adopted.”

---

## 10. Cloud vs local computer control

Two capabilities, two consents, neither fully implemented.

| Surface | What it can do | Consent |
|---|---|---|
| Cloud browser | Proposed Chromium executor inside an authorized cloud runtime. The existing skill documents HTTP(S) and no file transfers, but does not establish comprehensive network/upload enforcement; see below | Rental consent (U5) when applicable, plus per-action mutation/sensitive approval |
| Paired desktop | Native OS control on a machine the user installed a companion on | Separate pairing token, OS permission, per-action approval. **External I6** |

The existing script checks the initial URL scheme and caller-supplied approval flags, disables accepted downloads and cancels download events, then checks the page URL after actions (`extensions/fusion-harness/skills/computer-use/browser.mjs:14-25`, `extensions/fusion-harness/skills/computer-use/browser.mjs:60-61`). The skill documents no uploads/downloads (`extensions/fusion-harness/skills/computer-use/SKILL.md:37-43`). These are not proof of upload prevention or complete network isolation. The product executor must enforce and test file-transfer policy and network egress, including redirects, subresources, localhost, private networks, and metadata endpoints, outside model prompts.

Cloud availability does not imply the laptop is reachable. Unauthenticated desktop endpoints are forbidden. Agents cannot set `approve_mutation` / `approve_sensitive` as self-approval; A6 binds approvals to the user and the exact action.

---

## 11. Hosting costs and consent

**Proposed.**

- Versioned consent artifact: timestamp, price shown, cap acknowledged. Revocable.
- Lifecycle: `not_requested → consented → provisioning → active → stopping → stopped → terminated`, with explicit failed/reconciling states. A user can request cancellation from any nonterminal state, including provisioning. Do not display `stopped` until the vendor confirms compute stopped; separately report retained-resource charges until termination confirms release.
- Enforce budget reservations before provision and ongoing metering while active. Include compute, storage, network, provider usage where bundled, and a conservative allowance for metering lag and shutdown time. Refuse unbounded-price plans. A server-side watchdog stops new work and initiates shutdown before the reserved monthly cap can be exhausted. No silent downgrade or automatic restart after consent revocation.
- An always-on plan stays available within its accepted budget. Idle suspension is a separately disclosed economy option, not an undisclosed reaper on an always-on rental. At budget shutdown, show offline status and the reason.
- Declining rental preserves wizard progress but never implies a working local executor; use the verified alternatives in U5.
- A tenant-scoped allocation record and uniqueness constraint enforce at most one nonterminated sandbox across profile revisions. Generation job ids do not identify hosting allocations. Reconcile unknown vendor outcomes before retrying, use vendor idempotency keys, and retain cancelled allocation identity until cleanup is confirmed.
- Namespaced vaults and keys plus service authorization enforce tenant isolation. A lock or one-host policy alone does not.

**External I5:** vendor, price list, isolation tech.

---

## 12. Permissions (outside prompts)

**Proposed**, enforced in A6:

- Tool grants are scoped and expiring.
- Mutation approval ≠ sensitive approval (`extensions/fusion-harness/skills/computer-use/SKILL.md:37-41`).
- Deny and cancel are service operations.
- Cross-tenant access rejected.
- Revoked or offline paired devices rejected.
- Untrusted content (web pages, vault notes, retrieved packets) cannot change policy.
- Audit log of approvals, denials, provisions, and tool execution.

Existing `ctx.ui.confirm` and request booleans are terminal/local patterns, not this service.

---

## 13. Implementation plan (conditional on I1)

No application files are authorized in this repository until the app location is identified. Do not implement inside `extensions/fusion-harness/` for this product.

| Slice | Scope | Depends | Owner once I1 is known | This repo |
|---|---|---|---|---|
| **P0** | Resolve I1–I3 and I9 (app location, auth, video, default binding/runtime funding) and freeze service contracts | — | Product + A2+A3 | Spec only |
| **P1** | U0–U1 login + muted autoplay | P0 | App auth + web | None |
| **P2** | U2–U6 and U9 resumable wizard; unavailable connectors/hosting explicitly labeled, never fake completion | P1 | App + A2 | None |
| **P3** | U7–U8 job + truthful skills | P2 | App job runner | May later reuse `loadModelStack` as a library; not this pass |
| **P4** | U10 durable chat, default provider and second-provider conformance, authorized executor, browser tool, approvals, cancel | P2 | A1+A3+A4+A6 | Patterns only (`tui.ts`, `child-runner.ts`) |
| **P5** | Live voice | P4, I4 | A1 audio | None |
| **P6** | Paid always-on host | P4, I5 | A7 | None |
| **P7** | Paired desktop | P4, I6 | A8 | None |
| **P8** | U4 real source ingestion, tenant authorization, provenance, search and correction/deletion | P0 | A5+A2+A6 | Reuse knowledge semantics only after isolation review |
| **P9** | Candidate-note promotion, independent verifier, corpus/config versions, budgets and rollback | P8 | A5 + independent evaluator owner | No existing improvement service |
| **P10** | Integrated U0→U10 flow with a real default runtime and knowledge, truthful skills, rental declined | P3, P4, P8 | App integration + acceptance owner | Run §14 core tests in the actual app |
| **P11** | Full requested voice/hosting/desktop/improvement acceptance, including school/real-estate packs | P5, P6, P7, P9, P10, I8 | Acceptance owner + service owners | Not a claim of implementation |

P5–P7 are parallel after P4. P3 and P4 may proceed in parallel after P2 if contracts are frozen. P8 can begin alongside P1, and P9 follows P8 independently of UI work. P10 is the first real onboarding-to-chat slice, not full product completion. P11 tests both hosting acceptance and decline, authenticated cross-device reconnection, and every service failure path. Once I1 is known, assign non-overlapping application paths to these service owners before writes.

Reusable later, not moved by this spec: `loadModelStack` (`extensions/fusion-harness/modules/model-stack.ts:113-223`), `slotId` (`extensions/fusion-harness/modules/model-stack.ts:73-75`), `detectSecondBrainVault` / `resolveKnowledgeConfig` (`extensions/fusion-harness/modules/knowledge-config.ts:74-74`, `extensions/fusion-harness/modules/knowledge-config.ts:109-109`), `retrieveKnowledge` / `packetHash` (`extensions/fusion-harness/modules/knowledge-base.ts:472-472`, `extensions/fusion-harness/modules/knowledge-base.ts:478-478`), `captureVaultNote` / `acquireVaultLock` (`extensions/fusion-harness/modules/knowledge-ingest.ts:53-53`, `extensions/fusion-harness/modules/knowledge-ingest.ts:132-132`), computer-use skill.

---

## 14. Acceptance tests

All **proposed**. Distinguish spec completion from product implementation.

Onboarding and video:

- Unauthenticated user never reaches U1.
- Muted autoplay with captions; unmute; skip; blocked-autoplay Play fallback; failure Retry/Continue.
- Reload does not repeat login.
- Returning complete user skips U1.
- Refresh mid-wizard resumes `current` with `step_data` intact.
- Re-PUT unchanged step does not bump revision.
- Hosting accept without displayed price is impossible.
- Preview voice is labeled preview; composer has no mic until `voice_live`.

Jobs and skills:

- Identical harness POSTs share one `job_id`.
- Invalid stack (6 slots, or architect+primary on one slot) → `failed` with that error (`extensions/fusion-harness/modules/model-stack.ts:133-133`, `extensions/fusion-harness/modules/model-stack.ts:169-169`, `extensions/fusion-harness/modules/model-stack.ts:221-223`).
- Single mode with a verified model/executor can become ready without YAML. Missing binding or executor yields `awaiting_setup`, never a ready status.
- Fusion with any required unauthenticated, invisible, or incompatible slot never becomes ready, even if another slot works.
- `[college]` selection has only candidates, not installed results. Missing browser binaries or approval service prevents `computer-use` from being marked installed.
- Declined hosting with no usable alternative executor preserves answers but disables chat actions.
- Retrying a failed job records a new attempt under the same identity. Neither retries nor unrelated profile edits duplicate agents or paid hosts.

Chat and execution:

- Tokens stream and tool rows are visible. Models without exposed reasoning still work; optional reasoning summaries are not answers.
- Denied mutation has zero effect.
- Stop prevents new dispatches, cancels outstanding work, suppresses stale deltas, and reports already-committed or uncertain external effects.
- Thread survives provider switch.
- Unsupported capability fails explicitly.
- Unpaired/revoked/offline desktop actions rejected by the service.
- Forged approval (client-set boolean, no A6 record) rejected.
- Cross-tenant knowledge or host access rejected.
- Restart: app threads persist; do not use harness process-local sessions as the store.
- Network policy blocks disallowed redirects/subresources/private and metadata endpoints. Upload/download paths fail before transfer, not merely after navigation.
- Paired-device revoke cancels grants immediately. Remote reconnection requires authentication and cannot replay stale approvals.

Knowledge and hosting:

- Secret-like note rejected (`extensions/fusion-harness/modules/knowledge-ingest.ts:25-26`, `extensions/fusion-harness/modules/knowledge-ingest.ts:150-150`).
- Refused lane rejected (`extensions/fusion-harness/modules/knowledge-ingest.ts:105-111`).
- Same run id capture is idempotent (`extensions/fusion-harness/modules/knowledge-ingest.ts:163-164`).
- Configuration score ≤ `best_score` on the same corpus/evaluator is not promoted. Candidate notes stay out of retrieval until their source, consent, conflict, and regression checks pass.
- Harmful-note rollback restores the prior accepted corpus/config. Deleted or superseded notes remain excluded across rollback, caches, and reindexing. Individual-note permanent deletion does not require account deletion.
- Unauthorized-root proposals fail before retrieval/evaluation, regardless of potential score.
- Cap reached → provision fails closed. Active usage crossing the shutdown threshold stops new work and terminates within the reserved allowance, including lag and teardown charges.
- Consent revoke during `provisioning` or `active` reaches vendor-confirmed stop/release without retry creating an orphan host. Unknown outcomes remain reconciling, not falsely stopped.
- An always-on plan is not silently paused for idleness. An explicitly selected economy plan honors its disclosed idle policy.

Provider portability:

- Same conversation + one tool task through two real adapters.
- YAML-only new provider without adapter/auth/visibility is rejected.

CREAO:

- No CREAO client in dependencies until §9 proof passes.

---

## 15. Unresolved integration inputs

| ID | Input | Blocks |
|---|---|---|
| **I1** | App repository / surface | All UI and service paths |
| **I2** | Consumer auth | U0 |
| **I3** | Video, captions, poster | U1 |
| **I4** | Licensed TTS catalog | U2 preview and P5 |
| **I5** | Hosting vendor, price, isolation | U5 / P6 |
| **I6** | Paired-desktop agent and OS permissions | P7 |
| **I7** | Primary-source CREAO docs | Runtime vendor choice only |
| **I8** | School/study/real-estate skill files and readiness tests | Those packs as `installed`, P11 |
| **I9** | Default model binding, usage funding/disclosure, and non-rental runtime availability | U7/P4 execution readiness |

---

## 16. Consistency notes

- User order U0–U10 is preserved. Voice and background are separate steps (not a single `voice_background` field).
- Display name is collected at U9 and is not a fusion slot name.
- Selection produces candidates. U8 reads verified `installation_results`, not the selection manifest.
- Browser vs desktop is enforced in copy, chip, A6, and P6/P7 split.
- Preview voice vs live voice is a stored flag, not a UI-only label.
- Harness knowledge is evidence, not training.
- Session-comment vs implementation conflict on restart persistence is recorded in F4; the product store must not follow the comment.
- Vault wiki line citations are from the collaboration evidence packet, not files in this repository.
- `EVANAI_VISION_AND_ROADMAP.md` is an unrelated untracked memo and is not this product.

## 17. Collaboration provenance and handoff

| Slot / task | Contribution |
|---|---|
| TERRA / 1.a, 3.a, final integration | Product boundary, source audit, R6–R11 corrections, and consistency validation |
| DRIFT / 1.b | Runtime/provider seams and evidence-qualified CREAO adoption gate |
| GLM / 1.c | Profile/job contracts, skill mapping, knowledge and hosting lifecycle design |
| GROK / 1.d, 2.a | Ordered onboarding/chat UX and the initial synthesized specification |

All six delegated task reports completed. Reports and plan are under `/tmp/fusion-harness-m2jRbC/collaborate/`; this path is local run provenance, not a portable product dependency. Final integration addresses readiness (R6), operating spend limits (R7), knowledge authorization/rollback (R8), resume and implementation coverage (R9), browser guarantees (R10), and citations (R11).

Validation performed during final integration: 84 repository citation ranges resolve to existing files and valid line bounds, the two vault references remain explicitly packet-sourced, all three JSON examples parse and preserve the ordered state/candidate contracts, P0–P11 has no unknown slice dependency or cycle, and document assertions cover R6–R11. The two pre-existing untracked documents retained their initial SHA-256 hashes. No application code changed. No runtime, browser, provider, or billing acceptance tests were run.

Next action: identify I1, the actual app repository, then settle P0 inputs and implement P1/P8 in that application. CREAO remains unverified until I7 evidence and §9 tests exist. Specification completion is not product implementation; the §14 tests are future acceptance criteria, not reported runtime passes.
