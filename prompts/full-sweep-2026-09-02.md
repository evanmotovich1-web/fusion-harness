# Full-sweep reconciliation: wire the documented Hermes MCP surface, settle F1, land the capability-scout hardening

Dated: 2026-09-02 · Mission brief for a collaboration run · Evan-authorized scope.
This brief is self-contained: agents have no other conversation context. Repos are the source of truth — read the governing AGENTS.md files first (second-brain/AGENTS.md, agentic-os/AGENTS.md, ~/.hermes/hermes-agent/AGENTS.md) and obey them where this brief is silent.

## Situation — read before acting, do not re-derive

The 2026-09-02 capability scout at `second-brain/discoveries/2026-09-02-capability-scout.md` ranked seven MCP candidates and recommended Obsidian MCP read-only → n8n docs-only → one market-data experiment. A follow-up audit appended a correction (same file, lines 121-167) that SUPERSEDES that approval sequence. Canonical audit findings, already validated (43 tests + fixtures):

- F1: No Hermes config on this Mac — base `~/.hermes/config.yaml` nor any of the five active profiles (`architect-agent`, `agentic-manager`, `bob-the-builder`, `learner_agent`, `sherlock`) — contains an `mcp_servers` block. The "vault is shared memory via Hermes MCP" claims in `agentic-os/AGENTS.md`, `second-brain/USAGE.md`, and `second-brain/wiki/connectors-and-capabilities.md` are stale: they were proven 2026-08-29 on another machine (`/Users/davidmotovich/...`). This Mac's Hermes MCP state is UNKNOWN until a live probe succeeds.
- F2: Agentic OS Pi seats already compose `llmwiki` + `secondbrain` + `mnemosyne` (`configs/agent_os.json`, `src/capability_composer.py`). Obsidian-MCP and generic-memory proposals are ADD-vs-REPLACE questions on that surface, not fresh installs.
- F3: `czlonkowski/n8n-mcp` is NOT the approved catalog entry `CyberSamuraiX/hermes-n8n-mcp` (instance manager needing N8N_BASE_URL + API key). `MCP_MODE=stdio` selects transport only, never documentation-only mode.
- F4: The scout is preserved with its correction appended. No install sequence was approved; no connector, credential, config, or ticket action occurred.

Command-shape defect (applies to every registration in this brief): Hermes stores `--command` as a single argv[0] and never shell-parses it — `'npx -y pkg@latest'` as one string dies with ENOENT. Correct shape: `--command npx --args <pkg ...>` (same for `uvx`). Behavioral env belongs in `config.yaml` under `mcp_servers.<name>.env`, never `.env`. Pin exact versions or full commit SHAs — `@latest`, bare git URLs, and unpinned installs violate the repo pinning policy. Hermes-native scoping is `mcp_servers.<name>.tools.include/.exclude` and `trust: untrusted` (approval gating), not server-side read-only flags. Verify every mechanism against live source (`hermes_cli/mcp_config.py`, `hermes_cli/mcp_catalog.py`, `hermes_cli/mcp_security.py`, `tools/mcp_tool.py`, `optional-mcps/*/manifest.yaml`) before writing any config — same discipline the audit used.

Known disk state (2026-09-02): `~/.hermes/hermes-agent/optional-mcps/` has NO `llmwiki` or `mnemosyne` manifest — those were custom local servers, not catalog entries. `~/.hermes/mnemosyne/` (data) and `~/code/second-brain/.llmwiki/index.db` exist. Profile backups `_soul_backup_20260814` and `_soul_staging` are NOT active — never wire them.

## Mission (phases run in order; dependencies gate execution)

### Phase 1 — Probe and settle F1 (read-only first)
1. Run a sanitized runtime probe of Hermes MCP across base config + all five active profiles. Discover the exact read-only introspection command from `hermes mcp --help` / `hermes_cli/mcp_config.py` (do not assume). Report per-profile truth: any `mcp_servers` block, its servers, their state. Print no secrets.
2. Recover the previously-proven `llmwiki_brain` (LLM Wiki MCP over `~/code/second-brain`) and `mnemosyne` server definitions from history: `~/dotfiles`, second-brain wiki, agentic-os, git history of `~/.hermes`. Recover exact command/args/env/pins as last run. If unrecoverable, design minimal local server definitions following Hermes optional-mcps manifest conventions and the Hermes docs. If neither is possible, record BLOCKED with the missing evidence. Never invent a package that does not exist.

### Phase 2 — Wire what the documented contract says must exist
3. Register `llmwiki_brain` and `mnemosyne` in the location that makes them effective for all five active profiles (verify base-vs-profile inheritance semantics in source first; the documented contract says every profile carries them). Use recovered or corrected definitions, pinned, env via `mcp_servers.<name>.env` with placeholder-only values — no secrets anywhere. Scope write tools per the lane rule wherever the server supports it (second-brain writes confined to `wiki/` + `me/`; never `trading/` or `sessions/`).
4. Live-validate every registration: spawn the server and complete one read tool call through the profile runtime with sanitized output, or prove presence via the introspection command. Fail closed: any server that cannot start is disabled or reverted with a dated status — never left half-wired.

### Phase 3 — Reconcile the remaining scout candidates (classification only)
5. For each of the seven scout candidates, record a current classification and an explicit ADD-or-REPLACE decision against its incumbent into `agent-workflows/loops/capability-scout/incumbents.json`, matching the fail-closed validator's schema (`tools/validate_capability_scout.py`). Candidates requiring credentials (CyberSamuraiX n8n, Obsidian Local REST) get documented env-var placeholder shapes and stay DO NOT RUN. No external package install, no additional MCP registration, no credential handling — Phase 2 is the only wiring this brief authorizes.

### Phase 4 — Reconcile Agentic OS and vault truth
6. Update `agentic-os/AGENTS.md` (shared-memory table), `second-brain/USAGE.md`, and `second-brain/wiki/connectors-and-capabilities.md` so every claim matches probed reality: dated, current machine paths, Obsidian/n8n runtime statuses qualified per the probe (LIVE / UNCONFIGURED / BROKEN), never from stale history. Keep historical observations as dated history, not current claims.
7. Pi-seat reconciliation: `configs/agent_os.json` seat declarations and `src/capability_composer.py` are source of truth. Only edit if Phase 2 changes what seats should declare; otherwise record them as already-correct and move on.
8. Land the pending capability-scout hardening already in the working tree: `tools/validate_capability_scout.py`, `tests/test_validate_capability_scout.py`, `tests/test_capability_scout_fixtures.py`, `tests/fixtures/capability-scout/`, `agent-workflows/loops/capability-scout/` (README, PROMPT, incumbents.json), `DECISIONS.md`, `configs/agent_os.json` edits. Run the focused suite and fixture checks until green. Leave `watch/data/*` runtime files untouched.

### Phase 5 — Commit and report
9. Commit rules. second-brain: changes may be committed and pushed; a background vault-sync service auto-commits vault files on its own schedule — expect it, do not fight it, and note any auto-commit as an operational exception. agentic-os: after focused tests pass, commit the hardening + reconciliation on a branch named `capability-scout-hardening`; DO NOT merge or push to main — Evan runs `tools/run-smoke.sh` and merges. No `runtime/` edits.
10. Close with a canonical result digest: findings (F1 resolved or blocked, with probe evidence), delivered list with absolute paths, validation numbers (tests, fixture exit codes, live server states), provenance table (task / slot / contribution), and operational exceptions. Last word: architect.

## Guardrails (binding)
- Lane rule: never create, edit, or delete in second-brain `trading/` or `sessions/`. Never touch agentic-os `watch/data/*` or `runtime/`.
- No secret read into chat or logs; no credential value written to any file, config, note, or commit — env-var placeholders only. Redact anything credential-shaped in output.
- No candidate package install (npm, uvx, pip -g, git clone) for any scout candidate. Phase 2 restoration may only use recovered or manifest-convention definitions, pinned.
- Fail closed: missing evidence → UNKNOWN/BLOCKED with what is missing; never assert a live claim without a live probe result.
- Every new/edited `.md` gets the `Governed by [[AGENTS]]` footer; every decision gets a dated `DECISIONS.md` pointer.
- Budget-conscious: reuse the audit reports and correction rather than re-auditing; probe first, and if a probe is impossible, say so and stop that phase rather than guessing.

## Output contract
One canonical markdown result in the collaboration digest format. The run is complete only when Phase 2 registrations are live-verified (or explicitly BLOCKED with evidence), Phases 1/3/4 deliverables exist on disk, and Phase 5 commit rules are honored.

---
Governed by [[AGENTS]] — see second-brain/AGENTS.md, agentic-os/AGENTS.md, and ~/.hermes/hermes-agent/AGENTS.md for the rules this brief operates under.
