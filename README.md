# fusion-harness

> **Fuse 2–5 frontier models instead of racing them. AND, not OR.**

📺 V2 walkthrough: **[Understand how to use the Pi Coding Agent to COMBINE COMPUTE not SELECT COMPUTE](https://youtu.be/rqZHR-hRllI)**

<p align="center">
  <img src="images/hero2.png" alt="FUSION HARNESS V2 — combine your compute" width="850">
</p>

📺 V1 walkthrough: [GPT-5.6 Sol vs Fable 5 Is the Wrong Question (Fusion)](https://youtu.be/AQl5Q-0l7FQ)

<p align="center">
  <img src="images/hero.png" alt="MODEL FUSION — multiple model streams fusing into one over an engineer's keyboard" width="850">
</p>

**Fuse 2–5 frontier models instead of racing them. AND, not OR.**

A composable Pi extension with one configured ARCHITECT, one primary/Main BUILDER (the raw-chat host), and up to three secondary builders. It provides N-way opinions, fusion, debate, coordinated implementation, direct one-agent routing, model selection, and gate-first validation without taking over Pi's footer.

---

## Install

### Agentic Install

```bash
# in Claude Code, Pi, or your favorite agentic coding tool
/install
```

The `/install` command lives at `.claude/commands/install.md` and handles toolchain checks, Node deps, `.env` verification, and a live launch check.

### Manual Install

**Prereqs:** [`pi`](https://pi.dev/), [`just`](https://github.com/casey/just), [`bun`](https://bun.sh), `jq`, [`uv`](https://github.com/astral-sh/uv).

```bash
npm install -g @earendil-works/pi-coding-agent   # the pi coding agent
brew install just jq uv                          # command runner + gate tooling
npm install                                      # YAML parser + Playwright library
npx playwright install chromium                  # browser computer-use runtime
cp .env.example .env                             # then fill the provider keys you use; X research needs XAI_API_KEY
npm test                                         # deterministic tests, zero paid calls
```

Note: pi reads `GEMINI_API_KEY` for the google provider (not `GOOGLE_GENERATIVE_AI_API_KEY`).

---

## Why fusion

<p align="center">
  <img src="images/svg-12-fusion-fanout-merge-animated.svg" alt="One prompt fans out to every configured model; one sole-writer FUSION agent merges; every model ACKs the result" width="750">
</p>


Model rankings flip every month. Betting a workflow on ONE frontier model means re-betting every month. This harness makes the bet unnecessary: run 2 to 5 models against the same problem, compare or fuse their answers, and keep one shared working directory safe with a single-writer invariant the whole time.

> *The most flexible system wins. AND, not OR.*

## Launch

The fusion stack (Fable 5 architect + Gemini 3.7 Flash Main + DeepSeek V4 Pro):

```bash
just fusion
```

Explicit model stack:

```bash
just fh-stack .pi/fusion-harness/model-stack-trio.yaml
```

Legacy two-slot mode remains compatible:

```bash
just fh-workhorse   # cheap pair · just fh-sota for the frontier pair
```

The extension selects the configured primary builder as Pi's live host model. Invalid/unavailable stacks fail startup.

## Model stack configuration

`--fh-config <path>` accepts an explicit YAML list with 2–5 slots:

```yaml
- name: fable
  model: anthropic/claude-fable-5
  thinking: xhigh
  architect: true
  color: "#A78BFA"

- name: sol
  model: openai/gpt-5.6-sol
  thinking: xhigh
  primary: true
  color: "#F59E0B"

- name: terra
  model: openai/gpt-5.6-terra
  thinking: medium
  color: "#22D3EE"
```

Rules:

- 2–5 slots.
- Exactly one `architect: true`.
- Exactly one **non-architect** `primary: true`; `primary` is only for the Main builder.
- Unique 1–16 character names (`A-Za-z0-9_-`).
- Fully qualified `provider/id` models with configured authentication and visibility in clean-room children launched with `--no-extensions`. Models registered only by another extension are rejected.
- Thinking: `off|minimal|low|medium|high|xhigh|max` (short aliases accepted).
- Colors are actual quoted `#RRGGBB` values. Omitted colors use a stable per-stack hash.
- `system_prompt` may be inline or a path relative to the YAML file (full override of pi's default).
- `append_system_prompt` takes one entry or a list — each inline text or a YAML-relative file path — appended in order AFTER the slot's base prompt (the `system_prompt` override, or pi's own default when unset; harness contract prompts come before user appends). Children receive them via pi's repeatable `--append-system-prompt`, so the default prompt is never rebuilt. `/fh-system-prompt` shows the effective result.
- `skills` takes a list of YAML-relative Pi skill directories or files. Every path is validated and only explicitly listed skills enter the clean-room child.
- `--fh-config` cannot be mixed with legacy architect/builder model, thinking, or system-prompt flags.

No config auto-discovery occurs; `--fh-config` is explicit.

## Commands

| Command | Behavior |
|---|---|
| `/fh [on\|off]` | Command index plus opt-in one-row-per-slot model bar (a `belowEditor` widget). The harness removes Pi's default footer at startup and runs footerless until the bar is toggled on. |
| `/fh-opinion <prompt>` | Every configured model answers independently with strict read-only tools. |
| `/fh-fusion "<prompt>" "<instruction>"` | Every slot researches read-only; one fresh temporary FUSION agent is the sole CWD writer; then the complete fused result is synchronized to every model with exact ACK evidence. |
| `/fh-debate [--rounds N] <prompt>` | N-way read-only debate. Each round every surviving agent receives every other agent's clearly labeled prior opinion, may pick/change sides, and closes without a judge. |
| `/fh-collaborate <prompt>` | Every agent plans read-only, the architect merges the plans into one validated delegation DAG, then tasks execute the moment their dependencies clear — parallel where the DAG allows, sequential paths where it doesn't, exactly one shared-CWD writer at a time — closed by a final architect integration turn. Proposals, the task breakdown, and every task report render as panels; a live task board runs below the editor. |
| `/fh-lanes [--no-merge] <prompt>` | **Every builder works at once, each in its own lane** — a private git worktree on `fh/lane/<slot>`, seeded from the main checkout (HEAD plus uncommitted work). Builders get full tools inside their lane; the harness commits each lane when its builder finishes; then the architect, alone and under the writer lease, integrates the best result into the main checkout as uncommitted changes. `--no-merge` skips the integration and leaves the lanes for you. A live lane board below the editor shows each lane's branch and file churn while the models work. `status` · `diff <slot>` · `clean` manage the lanes afterwards. |
| `/fh-only [slot] [prompt]` | Address one slot directly. Without a prompt it arms the next plain input as a one-send route; selecting the armed slot again disarms it. |
| `/fh-model` | Three-step picker: slot → model → thinking. Session-only; never rewrites YAML. Main applies both `pi.setModel()` and `pi.setThinkingLevel()` to raw chat. |
| `/fh-auto-validate <prompt>` | Existing gate-first ARCHITECT + Main build loop. |
| `/fh-system-prompt` | Responsive grid of every slot's effective system prompt. |
| `/find-workflow <task>` | Deterministically route a task to a saved workflow. Confident matches run automatically; weak or tied matches open a selector. |
| `/create-workflow [--global] [id]` | Open a YAML skeleton, validate it, then save it to the project or global workflow directory. |
| `/research-x <query>` | Call Grok's live `x_search` through the xAI Responses API and return cited results. Requires `XAI_API_KEY`; requests are billed by xAI. |
| `/fh-knowledge status\|search\|refresh\|capture` | Inspect harness knowledge: roots, the same retriever fan-out uses, cache refresh, or opt-in vault write-back. Retrieved evidence, not model training. |
| `/fh-reset` | Full reset: fresh host session and fresh slot sessions — equivalent to `/new` plus a slot wipe. |

### Saved workflows

Workflows are strict YAML recipes, not executable config. They select an existing harness command, supply a prompt template, and may name a model-stack YAML. Discovery checks shipped workflows under `extensions/fusion-harness/workflows/`, global workflows under `~/.pi/agent/fusion-harness/workflows/`, and project workflows under `.pi/fusion-harness/workflows/`. Duplicate IDs are rejected instead of silently overriding another recipe.

```yaml
version: 1
id: review
name: Multi-model Code Review
description: Independent review for bugs and missing tests.
triggers: [code review, audit changes]
command: fh-opinion
prompt_template: |
  Review this task: {{TASK}}
confirm: false
```

`command` is restricted to the shipped harness commands plus `research-x`; arbitrary shell fields and unknown keys are rejected. Write-enabled workflows require confirmation by default. A workflow stack is validated for registration, authentication, and clean-room visibility before a session-only switch. Shipped recipes include `review`, `fuse-build`, `x-research`, and `computer-use`.

The computer-use recipe runs one primary agent with an explicit Playwright skill. It provides controlled Chromium automation, not native desktop control. It accepts only HTTP(S), blocks downloads and uploads, runs in an isolated foreground browser, and requires explicit approval for mutations plus fresh approval for purchases, messages, publishing, deletion, login submission, or sensitive-data exposure.

<p align="center">
  <img src="images/svg-07-opinion-grid-animated.svg" alt="/fh-opinion — every configured model answers read-only, rendered side by side" width="750">
</p>

## Single-writer invariant

<p align="center">
  <img src="images/svg-11-collaborate-dag-writer-animated.svg" alt="The writer token hops task to task — reads overlap, exactly one write-enabled child at a time" width="750">
</p>

Agents must never overwrite each other's work.

- `/fh-opinion` and `/fh-debate`: all agents are read-only (`read,grep,find,ls`).
- `/fh-fusion`: all source workers are read-only. Their answers are captured under the run's `/tmp/fusion-harness-*` directory. Only the temporary FUSION agent gets full tools and may modify the CWD.
- `/fh-collaborate`: planning and delegation are tool-enforced read-only; the harness persists the architect's plan JSON. Execution is dependency-driven — read tasks overlap freely, but every write-enabled task waits for the single global writer token, so `maxConcurrentWriteEnabledChildren` is always 1. Worktree commands are observed and fail the run.
- `/fh-lanes`: the one command where several models write at the same time — and they still never share a checkout. The **harness** creates one git worktree per builder (models are still forbidden from creating their own), each builder's cwd is its lane, and the main checkout keeps exactly one writer: the architect's integration turn, which holds the writer lease. Lanes live under `/tmp/fusion-harness-lanes/<project>/<slot>` on branches `fh/lane/<slot>` and are kept after the run until `/fh-lanes clean`. Ignored files (`node_modules`, `.env`) are not carried into a lane; builders install what they need inside their lane.

## Lanes

<p align="center"><em>Every model in its own lane, as it works.</em></p>

**Lane mode is on by default.** Whenever a fan-out command runs in a git repository — `/fh-opinion`, `/fh-debate`, the `/fh-fusion` research phase, `/fh-lanes` — the harness first seeds one lane per slot (a private git worktree on `fh/lane/<slot>`, carrying the main checkout's HEAD plus its uncommitted work), then pins each slot's child to its lane as its working directory. No two models ever read or write the same checkout at the same time; each one works from a consistent private snapshot, and a lane board below the editor shows every lane's branch and live churn next to the streaming grid. The single-writer stages — the FUSION merge, the `/fh-lanes` integration — still run in the main checkout under the writer lease. Outside a git repository lanes fall back to the shared cwd with one warning per session. `/fh-collaborate` and `/fh-auto-validate` stay on the shared checkout because their tasks must see each other's writes.

Toggle: `--fh-lanes off` at launch, or `/fh-lanes off` / `/fh-lanes on` in the session.

### `/fh-lanes` — parallel builders, one integrator

```
/fh-lanes add a /healthz endpoint with a test
```

1. **Seed.** For every non-architect slot the harness runs `git worktree add -b fh/lane/<slot>` from HEAD and carries the main checkout's uncommitted work in as the lane's base commit — so each builder starts from exactly what you see, and its own delta stays cleanly separable.
2. **Work, in parallel.** Every builder runs with full tools, its cwd pinned to its lane, told exactly who it is and where its lane is. The streaming grid shows each model's flow; the lane board shows each lane's branch and live `+/−` churn.
3. **Commit.** When a builder finishes (or fails — partial work is evidence too) the harness commits its lane. Reports, diffstats, and full patches land in the run's artifacts.
4. **Integrate.** The architect reads every lane's report and patch, may run the project's checks against a lane read-only, and integrates the best result into the main checkout with `git cherry-pick -n` (or a hand-port), leaving **uncommitted working-tree changes** — the same state every other harness command leaves. It never commits on your branch and never deletes a lane.
5. **Review.** `/fh-lanes status` lists the lanes, `/fh-lanes diff <slot>` shows one lane's full patch, `/fh-lanes clean` removes them all. Prefer a lane the architect rejected? `git cherry-pick -n <sha> && git reset -q`.

`--no-merge` stops after step 3. `/fh-lanes <prompt>` always uses lanes, even with lane mode off.
- `/fh-only` and `/fh-auto-validate` have one active writer by design.

A CWD-scoped atomic writer lease prevents separate harness processes from mutating the same checkout simultaneously. Child agents run in their own process groups so Escape, timeout, or session shutdown reaches Pi plus tool/bash descendants. Tool allowlists enforce planning safety; prompt contracts also prohibit detached background jobs.

## N-way debate

<p align="center">
  <img src="images/svg-08-debate-rounds-animated.svg" alt="/fh-debate — opening, all-to-all rebuttal, and closing rounds across three colored slots" width="750">
</p>

Round 1 captures independent, falsifiable opening opinions. Before each later round, every agent receives a block for every other agent:

```text
## [SLOT_NAME] provider/model — CONCRETE OPINION
<complete prior-round opinion>
```

Agents are explicitly allowed to defend a side, join another side, synthesize compatible positions, form coalitions, or remain a minority—provided they identify what evidence moved them. Failed agents are labeled and removed from later rounds; the debate continues while at least two opinions survive. All closing opinions render in the responsive AgentGrid. There is no judge or hidden merge.

<p align="center">
  <img src="images/svg-09-debate-converge-animated.svg" alt="Positions may converge, form coalitions, or hold as a minority — the user judges" width="750">
</p>

---

## Collaboration: plan, delegate, execute in parallel

<p align="center">
  <img src="images/svg-10-collaborate-phases-animated.svg" alt="/fh-collaborate — parallel proposals, architect delegation DAG, dependency-ordered execution, final coordination" width="750">
</p>


`/fh-collaborate` has no fixed choreography. Every agent plans the work independently (read-only, in parallel), the ARCHITECT merges those proposals into one validated delegation DAG, and the executor runs on dependency readiness: a task starts the moment its dependencies finish. Independent tasks overlap, dependent tasks form sequential paths, and a slot may own several tasks (they run one at a time on its session).

Everything renders as it happens: proposals as an opinion-style grid panel, the plan as a task table with parallelism levels, every finished task as its own report panel, plus a live task board below the editor (`● writing / ◌ queued / ○ blocked / ✓ done`). The run closes with one final architect integration turn.


## Fusion context synchronization

<p align="center">
  <img src="images/svg-13-fusion-pipeline-animated.svg" alt="/fh-fusion pipeline — fan out, propose, one-writer merge, sync, exact ACKs" width="750">
</p>

After the sole-writer FUSION agent finishes:

1. The exact result is saved to `fused.md` and `fusion-context.md`.
2. The fused panel enters the Main host context. Results above the panel limit are split into one visible head plus complete hidden continuation messages, so raw Main retains every byte.
3. Every slot receives the complete result in a no-tools turn.
4. Each must reply exactly `ACK FUSION <run-id>`; malformed ACKs retry once.
5. `acks/<slot>.md` and `summary.json` record status plus the common SHA-256 hash.
6. The fused result remains visible if ACKs fail, but the run is marked context-sync incomplete.

---

## Gate-first auto-validation

<p align="center">
  <img src="images/svg-05-gate-first-loop-animated.svg" alt="/fh-auto-validate — the VALIDATOR writes the acceptance gate before the builder does any work" width="750">
</p>


`/fh-auto-validate` inverts the usual order: the VALIDATOR writes a `uv` acceptance gate to disk BEFORE any building happens, a baseline run proves the gate starts red, then Main builds until the gate passes (default cap 5 validations). Failures feed back verbatim; from the third failure the validator adds a read-only triage brief, with a one-shot gate repair if the gate itself is the defect.


## Knowledge (retrieved evidence, not training)

Agents used to be told to “use the second brain.” Clean-room children spawn with `--no-skills --no-extensions --no-context-files` and read-only workers have no bash, so that instruction was inert. Retrieval is now a **harness stage**:

1. Before the first spawn of a request, the harness searches configured roots (explicit `--fh-knowledge path[,path...]`, else this machine's second-brain `wiki/` + `me/` when `SECOND_BRAIN_VAULT` or `~/code/second-brain` exists, else project `ai_docs/`).
2. Markdown is split into heading-aware chunks, ranked with deterministic lexical scoring, diversified, and capped by a byte budget.
3. The same immutable packet (hashed) is injected into applicable **first turns** of opinion, debate opening, fusion research + FUSION writer, collaboration planning, lanes, auto-validate, and `/fh-only`. Later debate/correction rounds reuse that snapshot. Fusion ACK turns do not get a new packet.
4. Retrieved text is delimited as **untrusted evidence**. Citations (`file:start-end`) are required only for claims that use it. Conflicts and `wiki miss` must be reported. Embedded document instructions are not policy.
5. Each run writes `knowledge-query.json`, `knowledge-packet.md`, and `knowledge.json` under `/tmp/fusion-harness-*`.
6. Optional capture (`--fh-knowledge-capture on` or `/fh-knowledge capture on`) extracts a `## Vault note` from write-capable completions, secret-scans it, and appends to `wiki/agent-learnings.md` only — never `trading/` or `sessions/`, never git commit/push.

`--fh-knowledge off` or `FH_KNOWLEDGE=off` disables injection. This improves **task context**, not model weights. Pi has no built-in MCP; children do not load the host skill at `.pi/skills/knowledge-base/SKILL.md`.

Inspect: `/fh-knowledge status` · `/fh-knowledge search recursive CTE` · `/fh-knowledge refresh`.

## Sessions and UI

- Sessions are keyed by slot plus a hash of the complete `provider/model` and live under a per-process run dir, so concurrent harness launches and model swaps can never share or replay each other's transcripts.
- Main forks the host session; architect and secondary builders keep one session per slot for the LIFETIME OF THE APP RUN — context carries across commands within a launch, and quitting pi discards every slot brain (a restart never resumes old transcripts). `/fh-reset` and `/new` reset mid-run.
- `/fh-model` non-Main model switches mint/resume the correct model-specific session. Main deliberately follows native Pi switching and preserves the existing host transcript across model changes.
- The responsive AgentGrid renders 1–5 columns when each can remain at least 34 cells wide; otherwise agents stack vertically.
- Pi's default footer is removed at TUI startup; the session runs footerless. The opt-in model bar renders one full-width row per slot in its configured hex color when you want status back — each row shows speed, cost, and context together: `◆ ARCHITECT | fable | model (med) | [██--------] 12% | 87 tps | $0.0123`.
- TPS is observed provider-response throughput (output tokens ÷ provider-response seconds; child startup/network/thinking included, tool execution excluded) and is throughput-weighted per slot across the session, folding the in-flight run live. The host's own raw-chat turns are measured at the `before_provider_request → message_end` boundary and credited to the Main row. Live widget columns and final panel stat lines carry the same `N tps` readout per agent.

---

## Recipes

```bash
just                  # list every recipe
just fh-stack <yaml>  # any explicit 2-5 slot stack
just fusion           # rune (Fable 5 architect) + flux (Gemini Flash Main) + drift (DeepSeek V4 Pro)
just fusion5          # fusion trio + fire (Kimi K3) + hawk (DeepSeek V4 Flash)
just fh-workhorse     # legacy two-slot pair (cheap)
just fh-sota          # legacy two-slot pair (frontier)
```

Stack YAMLs live in `.pi/fusion-harness/` (and `~/.pi/fusion-harness/` for launching from anywhere). A clean demo workspace with the same recipes, scraped DuckDB v2.0 docs in `ai_docs/`, and self-contained demo prompts lives at [`../fusion-harness-v2-playground`](../fusion-harness-v2-playground).


## Runtime files


```text
extensions/fusion-harness/
├── fusion-harness.ts          # the extension factory: flags, stack, sessions, widgets, small commands
├── modules/
│   ├── runtime.ts             # shared types, glyphs, tool allowlists, formatting, HarnessDeps seam
│   ├── child-runner.ts        # clean-room pi children, JSON streaming, kill-tree escalation
│   ├── prompt-library.ts      # every model contract, built from prompts/*.md templates
│   ├── tui.ts                 # TwoCol/AgentGrid/FullWidth, labels, live columns, panel renderer
│   ├── cmd-readonly.ts        # /fh-opinion + /fh-debate
│   ├── cmd-fusion.ts          # /fh-fusion
│   ├── cmd-build.ts           # /fh-collaborate + /fh-auto-validate (writer-lease holders)
│   ├── model-stack.ts         # YAML parsing, validation, colors, legacy synthesis
│   ├── agent-layout.ts        # responsive 1-5 agent layout math
│   ├── collaboration-graph.ts # DAG validation, cycle detection, dependency levels
│   ├── writer-lease.ts        # atomic canonical-CWD writer exclusion
│   ├── knowledge-config.ts    # roots, budgets, capture opt-in (never /Users/moto)
│   ├── knowledge-base.ts      # discover, chunk, rank, hash immutable packets
│   ├── knowledge-ingest.ts    # opt-in vault note write-back + vault lock
│   └── cmd-knowledge.ts       # /fh-knowledge status|search|refresh|capture
├── prompts/                   # SYSTEM_PROMPT_*.md / USER_PROMPT_*.md — edit files, not code
└── tests/                     # parser, graph, knowledge, and orchestration-invariant tests
```

- `fusion-harness.ts` — the extension factory: flags/config, stack resolution, host selection, persistent slot sessions, widgets/model bar, panel plumbing, and the small in-place commands (`/fh`, `/fh-model`, `/fh-only`, `/fh-system-prompt`, `/fh-reset`).
- `modules/runtime.ts` — shared types (AgentRun, AgentStat, FhDetails), role glyphs/colors, tool allowlists, formatting helpers, and the `HarnessDeps` seam the command modules run through.
- `modules/child-runner.ts` — clean-room `pi --mode json -p` child processes with JSON-event streaming and close-aware SIGTERM→SIGKILL process-tree escalation.
- `modules/prompt-library.ts` — every model contract, built from `prompts/SYSTEM_PROMPT_*.md` / `prompts/USER_PROMPT_*.md` templates, plus strict-output parsing.
- `modules/tui.ts` — TwoCol/AgentGrid/FullWidth layout primitives, labels, live streaming columns, and the transcript panel renderer.
- `modules/cmd-readonly.ts` — `/fh-opinion` and `/fh-debate`.
- `modules/cmd-fusion.ts` — `/fh-fusion`.
- `modules/cmd-build.ts` — `/fh-collaborate` and `/fh-auto-validate` (the writer-lease holders).
- `modules/model-stack.ts` — real YAML parsing, validation, colors, and legacy synthesis.
- `modules/agent-layout.ts` — responsive 1–5 agent layout calculations.
- `modules/collaboration-graph.ts` — DAG validation, cycle detection, and dependency levels.
- `modules/writer-lease.ts` — atomic canonical-CWD writer exclusion.
- `modules/knowledge-config.ts` — knowledge roots, budgets, and capture opt-in. Never follows `/Users/moto`.
- `modules/knowledge-base.ts` — discovery, heading-aware chunking, deterministic ranking, immutable packet hashing.
- `modules/knowledge-ingest.ts` — opt-in `## Vault note` write-back with secret scan, idempotency, and a vault lock.
- `modules/cmd-knowledge.ts` — `/fh-knowledge status|search|refresh|capture`.
- `tests/` — parser, graph, knowledge retrieval, and orchestration-invariant tests.

Every run writes an inspectable `/tmp/fusion-harness-*` directory with `stack.json`, prompt, per-slot artifacts, summaries, protocol-specific evidence, and when knowledge is enabled `knowledge-query.json` / `knowledge-packet.md` / `knowledge.json`.

## Validation

```bash
npm run test:fusion-harness     # deterministic unit/contract tests, including knowledge retrieval
```

Live validation prompts are checked in under `prompts/duckdb/`, ordered simple to complex and centered on the [DuckDB v2.0 preview](https://duckdb.org/2026/08/17/duckdb-20-highlights).

---

## License

MIT — see [`LICENSE`](LICENSE).

---

## Master Agentic Coding

Prepare for the future of software engineering.

Learn tactical agentic coding patterns with [Tactical Agentic Coding](https://agenticengineer.com/tactical-agentic-coding?y=fusion2).

Follow the [IndyDevDan YouTube channel](https://www.youtube.com/@indydevdan) to improve your agentic coding advantage.

---

Stay Focused and Keep Building

- IndyDevDan
