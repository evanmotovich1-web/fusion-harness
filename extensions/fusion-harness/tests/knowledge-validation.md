# Knowledge layer — objective validation (2026-09-02)

Retrieval is a harness stage, not an instruction. This report records the deterministic suite after wiring.

## Commands

```bash
npm test
# bun test extensions/fusion-harness/tests
```

## Results

- **97 pass / 0 fail / 3862 expect() calls** across 15 files.
- Existing orchestration, lanes (mocked child runner), writer-lease, collaboration-graph, and workflow tests remain green.
- New files: `knowledge-config.test.ts`, `knowledge-base.test.ts`, `knowledge-ingest.test.ts`, `knowledge-orchestration.test.ts`.

## Retrieval evaluation

| Check | Result |
|---|---|
| Same corpus + query → byte-identical packet hash | pass |
| `recursive CTE reachable` on fixtures ranks `relevant-recursive-cte.md` over `distractor-cooking.md` | pass |
| Conflicting fusion-worker-tool docs both retained | pass |
| Prompt-injection document text only inside `BEGIN/END UNTRUSTED EVIDENCE` | pass |
| Hidden, secret-like, binary, oversized, symlink-escape, unsupported, `trading/` skipped | pass |
| Stale cache refreshes on mtime/size change | pass |
| Packet byte budget truncates | pass |
| Explicit `wiki miss` | pass |
| `--fh-knowledge off` / `FH_KNOWLEDGE=off` disable | pass |
| Never follows `/Users/moto` when that is not homedir | pass |
| Live `ai_docs/duckdb-20-highlights.md`: query `recursive CTE reachable` and `VARIANT type shredded JSON` both hit that file with cited heading chunks | pass |
| Secret / empty / non-durable vault notes rejected | pass |
| Evidence-lane dest `trading/` refused | pass |
| Two ingest calls with the same run id → one `<!-- agent-run:ID -->` | pass |
| Vault lock excludes concurrent holder | pass |

## Orchestration contracts

- First turns of opinion, debate opening, fusion workers + fuser, collab propose, lanes workers + merge, auto-validate validator + builder round 1, and `/fh-only` call `prepareKnowledge` once and `withKnowledge(...)`.
- ACK turns use `ackSpec.prompt` with no packet wrap.
- Debate rebuttal/closing and auto-validate correction do not re-inject.
- Summaries record `knowledgeHash: packet.hash` so every fan-out slot shares one hash.
- Lane retrieve uses `ctx.cwd` (canonical checkout), not `lane.path`.
- Workers remain `READONLY_TOOLS`. Children still `--no-skills --no-extensions --no-context-files`.
- Capture writes only `wiki/agent-learnings.md`; refuses `trading/` and `sessions/`.
- `/fh-knowledge` is registered. Pi MCP is not advertised as built-in.

## Limitations

- No paid live `/fh-fusion` in this pass — DuckDB retrieval is offline against `ai_docs/`.
- Capture is **opt-in** (`--fh-knowledge-capture on` / `/fh-knowledge capture on`); default does not write the vault.
- Optional `scripts/llmwiki_sync.py` runs only when that script exists on the configured vault; the harness never `git commit`/`push`es the vault.
- Embeddings and MCP retrieval are non-goals. Knowledge improves evidence context; it does not train models.
