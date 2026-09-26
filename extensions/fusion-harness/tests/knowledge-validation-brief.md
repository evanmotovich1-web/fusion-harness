# Knowledge brief + global command — objective validation (2026-09-26)

This report records the end-to-end verification of the distilled-brief / global
knowledge-command work (`modules/knowledge-brief.ts`, `modules/knowledge-cli.ts`,
`modules/knowledge-inject.ts`, `modules/knowledge-guard.ts`, `modules/knowledge-base.ts`,
`prompts/KNOWLEDGE_GLOBAL_CONTRACT.md`). Measurements are from the shared working tree,
which is `blocked_dirty`; nothing was committed or pushed.

## Commands and results

```bash
bun test extensions/fusion-harness/tests
# 425 tests across 45 files — 423 pass / 2 fail — 6558 expect() calls — 58.59s — exit 1
```

### Failure 1 (real implementation defect, Node-safety contract)

```
orchestration contracts > every runtime module is Node-safe: no Bun-only APIs in modules/
extensions/fusion-harness/tests/orchestration-contract.test.ts:225
Expected: false  Received: true   (text.includes("import.meta.dir"))
```

Offender: `extensions/fusion-harness/modules/hook-audit.ts:668`

```ts
const modulesDir = options.modulesDir ?? import.meta.dir;
```

`import.meta.dir` is Bun-only; pi runs the extension under Node, where it is `undefined`.
While `hook-audit.ts` is imported only by `tools/hooks-doctor.ts` and its test today, the
repo contract forbids Bun-only globals in `modules/` unconditionally. Recommended repair
(same pattern as `prompt-library.ts` / `cmd-workflows.ts`): derive the directory from
`__dirname` when present, else `path.dirname(new URL(import.meta.url).pathname)`.

### Failure 2 (parent-owned staging debt, not a code defect)

```
committed code only imports committed files > every relative import in tracked extension code is tracked
```

Seven tracked files import modules that are new and still untracked:

```
fusion-harness.ts → ./modules/cmd-plan.ts
fusion-harness.ts → ./modules/knowledge-inject.ts
fusion-harness.ts → ./modules/knowledge-guard.ts
cmd-knowledge.ts → ./knowledge-brief.ts
cmd-knowledge.ts → ./knowledge-guard.ts
knowledge-base.ts → ./knowledge-brief.ts
prompt-library.ts → ./knowledge-brief.ts
```

This is the expected consequence of landing new modules without a commit. The parent must
stage the new files in one tracked change before this invariant can pass.

## Live command — same query twice

```bash
./extensions/fusion-harness/bin/fh-knowledge brief \
  "distill the vault into a global knowledge command injected for every agent" \
  --cwd /Users/evanmotovich/fusion-harness --json   # run twice
```

| Field | Run 1 | Run 2 |
|---|---|---|
| exit code | 0 | 0 |
| status | passed | passed |
| packetHash | `f680ca00228378d679383bbb31a5e4fe066920a19a13c5391c556fd04db451e3` | same |
| briefHash | `16f7b08ec40dddff01265f3868ab69a6efa20b045fe160d8c68857c3d5a9c609` | same |
| briefBytes | 1944 | 1944 |
| packetBytes | 5308 | 5308 |
| briefTruncated | false | false |
| sections | decisions 2 · constraints 2 · hooks 1 · do-not-repeat 1 | same |

Retrieval ran against the real machine: roots
`~/code/second-brain/wiki`, `~/code/second-brain/me`, `<repo>/ai_docs`;
496 files / 4630 chunks indexed; `reasons` includes `semantic: 24 vault-semantic hits fused`;
`errors: []`. Hash stability holds across runs (the `retrievedAt` timestamp is deliberately
outside the hash).

## Hook doctor

```bash
bun extensions/fusion-harness/tools/hooks-doctor.ts --json --no-probe
# exit 0
```

| Check | Value |
|---|---|
| `ok` | false |
| surfaces scanned | 28 |
| `checks.contractBlock` | `not-installed` |
| `checks.contractSurfaces` | `[]` |
| `checks.knowledgeInject` | `fail-open` |
| `checks.knowledgeGuard` | `fail-open` |
| `checks.stopGateInstalledByUs` | `none` |
| `checks.codexTrust` | `pass` |
| `checks.canBlockCount` | 4 |

Findings: can-block surfaces `pi:extension:permission-gate.ts`, `pi:extension:plan-mode`,
`claude:PreToolUse:1:0`, `claude:Stop:0:0`. These are pre-existing, outside this repo, and
are the concrete hook-failure class the audit exists to surface. The doctor always exits 0
and reports failure through `ok`/`findings`, as designed.

## Safety evidence

| Check | Result |
|---|---|
| Existing knowledge suite (11 files) | 75 pass / 0 fail (from task 2.e; re-run green) |
| `~/.fh-knowledge` install manifest | absent |
| `~/.cache/fusion-harness/knowledge` cache | absent (CLI does not persist; only `persistKnowledgeBrief` writes) |
| `tools/knowledge-install.ts --check` (dry run) | exit 0 · contract `5581216a9c64` · pi/root/claude/codex/hermes = `missing` · adw `skipped` |
| Vault `trading/` mtime | 2026-09-02T02:04:42 |
| Vault `sessions/` mtime | 2026-09-26T02:32:19 (predates this task's commands) |
| Vault `wiki/agent-learnings.md` mtime | 2026-09-26T01:26:45 |
| Capture | opt-in and OFF; no capture command was run; the CLI is read-only |
| Global config | unchanged — installer was never executed, only `--check` |

## Handoff / follow-ups (not authorized here)

1. Repair the `import.meta.dir` use in `hook-audit.ts` (task 3.b) and re-run the full suite.
2. Parent: stage the new modules so `tracked-imports` passes.
3. SSSF/ADW wiring (`just plan` / `adws/adw_plan.py` planner+builder prompt fragment) lives in
   `/Users/evanmotovich/code/sssf` — a different repo; not touched.
4. Running the installer against the real home (5 surfaces currently `missing`) is a global
   change and remains unauthorized.
5. Grok on remote Linux cannot execute the local binary; "everywhere" is scoped to hosts that
   can run the CLI.
