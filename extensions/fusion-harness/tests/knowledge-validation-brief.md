# Knowledge brief + global command — objective validation (2026-09-26)

End-to-end verification of the distilled-brief / global knowledge-command work
(`modules/knowledge-brief.ts`, `modules/knowledge-cli.ts`, `modules/knowledge-inject.ts`,
`modules/knowledge-guard.ts`, `modules/knowledge-base.ts`, `modules/hook-audit.ts`,
`modules/knowledge-install.ts`, `prompts/KNOWLEDGE_GLOBAL_CONTRACT.md`).

**Verified base commit:** `aed807fffd6166d2b8ce60a5b11cf9b82eed1e4b` (parent `3ce94bfe`),
41 files, +4964/-9, subject `Add fail-open vault knowledge brief, CLI, and hook doctor.`
The working tree additionally carries one uncommitted host repair to
`tests/knowledge-install.test.ts` (see "Host repair" below) and this refreshed report.
Nothing was pushed.

## Commands and results

```bash
bun test extensions/fusion-harness/tests
# 434 tests across 45 files — 434 pass / 0 fail — 6659 expect() calls — 62.95s — exit 0
```

Both prior failures are resolved in the commit:

1. **Node-safety contract** — `hook-audit.ts` no longer uses `import.meta.dir`; it derives
   `MODULE_DIR` from `__dirname` / `new URL(import.meta.url)`, matching `prompt-library.ts`
   and `cmd-workflows.ts`. `tools/knowledge-install.ts` was given the same treatment.
2. **`tracked-imports`** — every module imported by tracked code is now tracked in
   `aed807ff`, so the invariant holds on a clean checkout of that SHA.

### Host repair (uncommitted, one test)

`knowledge-install safety > refuses to write the real home without --allow-real-home`
asserted `existsSync($HOME/.fh-knowledge/manifest.json) === false` — a property of the
developer's live machine. Once the authorized global install (step 2) ran, that assertion was
necessarily false. The test now asserts the refusal *changed nothing*: the manifest is
byte-identical before and after the refused `--apply` (or stays absent). Same refusal
contract, no dependence on machine install state.

```bash
bun test extensions/fusion-harness/tests/knowledge-install.test.ts
# 20 pass / 0 fail — 129 expect() calls
```

## Live command — same query twice

```bash
./extensions/fusion-harness/bin/fh-knowledge brief \
  "finish the five residual gates and publish the knowledge slice" \
  --cwd /Users/evanmotovich/fusion-harness --json   # run twice
```

| Field | Run 1 | Run 2 |
|---|---|---|
| exit code | 0 | 0 |
| status | passed | passed |
| packetHash | `a0b1e4395e2217dadf1284791d610d4f97f81557825711faa2c5a204b36c1345` | identical |
| briefHash | `5fce23decd4d83e7184cfb9da695507055ad58db44bd2b800c41d17e17808d9e` | identical |
| briefBytes | 1866 | 1866 |
| packetBytes | 7660 | 7660 |
| briefTruncated | false | false |
| sections | decisions 3 · constraints 1 · hooks 2 · do-not-repeat 0 | same |

Retrieval ran against the real machine: roots `~/code/second-brain/wiki`,
`~/code/second-brain/me`, `<repo>/ai_docs`; **497 files / 4820 chunks** indexed;
`reasons` includes `semantic: 24 vault-semantic hits fused`; `errors: []`. Hash stability
holds across runs (`retrievedAt` is outside the hash; semantic scores are quantized to 2
decimals by `rankSemanticHits` before they feed RRF, so back-end float noise cannot flip a
near-tie).

## Hook doctor

```bash
bun extensions/fusion-harness/tools/hooks-doctor.ts --json --no-probe
# exit 0
```

| Check | Value |
|---|---|
| `ok` | false |
| surfaces scanned | 63 |
| `checks.contractBlock` | `current` |
| `checks.contractSurfaces` | 35 (5 home + 30 ADW) |
| `checks.knowledgeInject` | `fail-open` |
| `checks.knowledgeGuard` | `fail-open` |
| `checks.stopGateInstalledByUs` | `none` |
| `checks.codexTrust` | `pass` |
| `checks.canBlockCount` | 4 |

Findings: `pi:extension:permission-gate.ts`, `pi:extension:plan-mode`,
`claude:PreToolUse:1:0`, `claude:Stop:0:0`. The first and last are the H1/H2 blocking hooks;
**step 3 (global hook hardening) did not execute** (the delegated task failed on model
capacity), so they are still reported can-block. The doctor always exits 0 and reports
failure through `ok`/`findings`, as designed.

## Global install (step 2)

| Surface | `begin` | `end` |
|---|---|---|
| `~/.pi/agent/AGENTS.md` | 1 | 1 |
| `~/AGENTS.md` | 1 | 1 |
| `~/.claude/CLAUDE.md` | 1 | 1 |
| `~/.codex/AGENTS.md` | 1 | 1 |
| `~/.hermes/SOUL.md` | 1 | 1 |

Manifest `~/.fh-knowledge/manifest.json`, contract
`5581216a9c645ecf8b9e25bb3795c8c3060ef2f137654f53ced42ff83c8f18e6`, 35 entries.
`knowledge-install.ts --check --home "$HOME" --json` → exit 0, `applied:false`,
5 `current` + 1 `skipped` (ADW, not selected). Reversible via `--uninstall`.

## ADW / SSSF (step 4)

30 `system.md` under `~/code/sssf/adws/adw_data/prompt_engineering/**`, all 30 carry exactly
one marker pair; `git -C ~/code/sssf status --porcelain` shows exactly those 30 ` M`. This is
prompt-fragment coverage only — the ADW runner does not call `fh-knowledge`, and
`fh-knowledge` is not on `PATH` for those seats.

## Safety evidence

| Check | Result |
|---|---|
| `~/.cache/fusion-harness/knowledge` | absent |
| Fixture `tests/fixtures/hooks/Library/` | absent; `.gitignore` rule `Library/` in place |
| Vault `trading/` mtime | 2026-09-02T02:04:42 |
| Vault `sessions/` mtime | 2026-09-26T02:32:19 |
| Vault `wiki/agent-learnings.md` mtime | 2026-09-26T01:26:45 |
| Capture | opt-in and OFF; the CLI is read-only |

## Follow-ups (not authorized in this graph)

1. **Step 3 — global hook hardening** (H1 permission-gate headless block, H2 Claude Stop gate,
   H5 `vault-semantic` 8s→1.5s): never executed; three live files unpatched; no backups taken.
2. **Step 1 — publication**: `aed807ff` is local only. `refuse_dirty` fires on the residual
   untracked paths; a `fork/main`-targeted card and receipt must be minted first. Target is
   `fork` (`evanmotovich1-web/fusion-harness`), never `origin` (`disler/fusion-harness`).
3. **Step 5 — vault write-back**: gated; the H1–H5 taxonomy and the `rankSemanticHits`
   determinism root cause are not yet filed in `wiki/`.
4. Make `fh-knowledge` reachable on ADW/pi seats before claiming ADW agents can call it.
