# Workflow-Builder ADW — Frozen Spec (task 2.a)

Version: 1 (frozen) · Written: 2026-09-30 · Owner: GLM (architect), implemented by 3.a (core), 3.b (seats/fixtures), 3.c (UI), 4.a/4.b (integration), 5.a (tests/verification)

This file is the law for building the workflow-builder ADW. It is grounded in `adws/specs/prior-adw-patterns.md` (pattern codes P1–P8, roster findings F1–F6, marketing patterns M1–M10, retained observations C1–C6/E1–E9, telemetry T1–T6, failure modes R1–R12, acceptance A1–A7 — citations below use those codes). Code files are written only after this spec exists and must stay younger than it (DoD 1).

## 1. What this is

An ADW (code-orchestrated workflow, the SSSF/homecare pattern) that lives in this repo at `adws/` and whose product is other ADWs. Evan submits a request; the builder specs a workflow exactly for that request, builds it, validates it with stubs and fixtures, and registers it so it appears in the desk UI. "Perfect for the request" means measurable coverage (A1–A7): every requirement in the request maps to a phase, typed output, named gate and verifier — or to an explicit recorded blocker. It never means a model's promise.

## 2. Law (invariants)

1. **Code orchestrates; agents fill in.** Routing, numbers, gates, bounds, telemetry and registration are code (P1). Agents produce typed envelopes parsed before gates run.
2. **Execution success ≠ acceptance.** A run is accepted only when every phase succeeded AND every requirement is `verified` or carries an explicit blocker (P3, A2, R10).
3. **The request is preserved verbatim.** Consequential ambiguity blocks (`needs_human`) with questions; the builder never narrows a goal silently (A1, S13 precedent).
4. **Unknowns are marked `<EVAN: fill>`, never invented** (homecare precedent).
5. **No git operations, no network sends, no commit/push/deploy authority** — in the builder and in every generated workflow (F6, R6, R12). Publication is parent-owned per root `AGENTS.md`.
6. **Writes are confined.** Builder seats write only inside `adws/built/<name>/` and the run dir. The builder never edits: itself, `adws/specs/`, `/Users/evanmotovich/code/sssf`, `homecare/`, `extensions/`, or anything outside `adws/`.
7. **Enforcement is stated honestly (F5/R2).** Preventive controls: `tools.json` becomes the exact `--tools` filter (M7) and a code-level path-allowlist wrapper checks every write before it runs. Post-phase audit verifies outcomes. This is NOT a sandbox and the code must not claim it is.
8. **Fresh verification after the last mutation (R3).** No accepted write without a validate pass that postdates it. The final repair is always followed by the suite.
9. **Preflight before spend (A3, R1, E1).** Every agent phase is preceded by code checks: model resolves exactly in the catalog (F2/M8), every named tool exists in the known-tools registry, declared write paths are inside the allowlist, the phase graph is acyclic. A named-but-absent tool (e.g. `memory_search`, exit 127) is a blocker, not a runtime surprise.
10. **Telemetry records reality with missingness (R9, E8, E9).** Absent data is `unknown`, never zero. Partial-failure usage is counted once. Interrupted tool calls stay incomplete.
11. **Safe defaults everywhere.** Generated workflows default `DRY_RUN=true` and stub-first; live actions sit behind explicit switches (M-defaults, P6, P8, R12).

## 3. Phase chain

Bounds: JSON correction 2 retries (P4); per-gate attempts ≤3, stop on identical failure twice (no-progress, M10); spec review ≤3 rounds with ≤2 revisions; validate fix loop ≤3, every fix followed by full validate.

| # | Phase | Kind | Owner | Job | Gate (code) |
|---|---|---|---|---|---|
| 1 | `intake` | code | router | Rule-based route of the request. Accepts workflow-build asks; refuses named reasons: `not_workflow`, `forbidden_target` (sssf/builder-itself/publish-deploy asks), `needs_human` (vague — emits questions, builds nothing) | route decision recorded; refusal names the reason and stops before any spend (P6, M5) |
| 2 | `survey` | agent | `workflow_scout` | Read `adws/specs/prior-adw-patterns.md` + repo context; select applicable patterns (P-codes), capability notes, risks for THIS request | every pattern claim cites `prior-adw-patterns.md` path/section; ≥1 pattern; every mentioned tool ∈ known-tools registry (R1) |
| 3 | `spec` | agent | `spec_writer` | Produce the `WorkflowSpec` v1 JSON (§5) mapping every requirement | `spec_schema`: parses against the frozen schema; every seat declares its 4 prompt files; every agent phase names a gate; unknowns are `<EVAN: fill>`; every requirement id appears exactly once with phase+gate+verifier or blocker |
| 4 | `spec_review` | agent | `reviewer` | Independent verdict envelope against the verbatim request | `verdict_consistent`: approval may not coexist with unmet/blocking findings (R5, E6); rejection findings route back to `spec_writer` as soft notice, bounded (see bounds) |
| 5 | `scaffold` | code | scaffold | Deterministic templates render every generated file (§6) from the approved spec. No model, no improvisation | rendered file set == spec artifact list; `py_compile` clean on skeletons |
| 6 | `implement` | agent | `builder` | Fill real gate logic, prompt bodies and CLI commands inside the scaffolded files | `diff_claims_real`: every claimed path exists, nonempty, and content-hash changed; no path outside `adws/built/<name>/` changed (before/after content-hash snapshot; honest limits per Law 7) |
| 7 | `validate` | code | validators | `py_compile` all generated python; run the generated workflow `--fixtures --stub-agents` end-to-end; run its tests; run one bad fixture proving its gate fails with a specific message | exit 0 runs; log shows `AGENT → GATE` per phase; bad fixture → named failure; suite green AFTER the last mutation (R3); fix loop bounded (bounds above) |
| 8 | `register` | code | registry | Append the entry to `adws/registry.json` (§7), write the run report + requirement coverage table | registry write only happens when validate is green; entry records acceptance (verified/blocked counts), never claims more |

Exit codes: `0` accepted; `2` refused (`not_workflow`/`forbidden_target`); `3` `needs_human`; `4` blocked (bounds/gates exhausted or preflight blocker). Refusals and blocks persist a report and artifacts for inspection (A7).

## 4. Seats (builder's own agents)

Four seats, each with the 4-file bundle `adws/prompts/<seat>/{system.md,user.md,soft_notice.md,tools.json}` loaded from disk at run time (M6). `tools.json` keys: `pi_tools` (exact `--tools` list, M7) and `writes` (path allowlist). Default model `ADW_MODEL` (env, default `deepseek/deepseek-flash` — present in this machine's auth), thinking `ADW_THINKING` (default `medium`); preflight resolves both exactly (F2).

| Seat | Purpose | pi_tools | writes |
|---|---|---|---|
| `workflow_scout` | Pattern selection + risk notes, cited | read, grep, find, ls | `[]` (report only, into the run dir) |
| `spec_writer` | WorkflowSpec v1 for the exact request | read, grep, find, ls, write | its one output file in the run dir |
| `reviewer` | Independent requirement-coverage verdict | read, grep, ls, write | its one verdict file in the run dir |
| `builder` | Implements inside the scaffold | read, grep, find, ls, write, edit, bash | `adws/built/<name>/**` only |

`bash` for `builder` is audited post-phase (allowed shapes only, M9) and its declarations preflighted (Law 9). Stub mode returns fixture outputs per seat (bad-first where a test demands, M8) so the whole chain runs with zero keys and zero network.

## 5. WorkflowSpec v1 (frozen schema, strict — unknown keys fatal)

```json
{
  "schema_version": 1,
  "id": "kebab-case-name",
  "name": "human name",
  "request_verbatim": "the untouched request text",
  "router": { "triggers": ["..."], "refusals": [{"reason": "not_workflow", "example": "..."}] },
  "requirements": [
    { "id": "req-1", "text": "requirement sentence", "phase_id": "p2",
      "gate": "named-gate", "verifier": "focused-check-id",
      "evidence": ["run-artifact-ref"], "status": "verified|blocked",
      "blocker": null }
  ],
  "phases": [
    { "id": "p1", "name": "step", "kind": "code|agent", "owner": "seat-or-code",
      "gate": "named-gate", "inputs": ["..."], "outputs": ["..."], "retries": 0 }
  ],
  "seats": [
    { "name": "seat", "model": "provider/id", "thinking": "medium",
      "tools": ["read"], "writes": ["adws/built/<name>/**"],
      "prompt_files": ["system.md", "user.md", "soft_notice.md", "tools.json"] }
  ],
  "artifacts": { "entrypoint": "adws/built/<name>/adw_<name>.py", "files": ["..."] },
  "switches": { "dry_run": true, "stub_agents": true },
  "blockers": []
}
```

Rules: acyclic phase graph; agent phases reference declared seats; gates reference the generated `gates.py` registry; every requirement maps per A2; `status` starts `blocked` and only validate sets `verified` with evidence.

## 6. Generated-workflow artifact shape — `adws/built/<name>/`

| File | Contract |
|---|---|
| `adw_<name>.py` | CLI `--fixtures --stub-agents --stub-bad-first --db PATH --reports-dir PATH`; router at the front door with named refusals (M5); phases with code gates; `DRY_RUN=true` default; **no git calls, no network calls, no subprocess beyond the stub runner** |
| `config.json` | The approved WorkflowSpec + switches, as run |
| `prompts/<seat>/` | 4-file bundles per seat, loaded from disk (M6) |
| `gates.py` | Requirement-specific checks with real content/schema verification (R5: no strong-sounding weak gates) |
| `tests/test_<name>.py` | Focused positive, negative and refusal cases for THIS workflow's acceptance criteria (A4, R4: pin focused argv, never the harness's default suite) |
| `fixtures/` | `good_<seat>.json` + `bad_<seat>.json` per seat |
| `README.md` | What it does, how to run stub vs live, switches, limits |

## 7. `adws/registry.json` (written only by the builder's `register` phase — never hand-edited)

```json
{ "schema_version": 1,
  "workflows": [
    { "id": "name", "name": "...", "version": 1,
      "entrypoint": "adws/built/<name>/adw_<name>.py",
      "spec_path": "adws/built/<name>/config.json",
      "built_at": "iso8601", "build_run_id": "<run id>",
      "status": "validated|blocked",
      "acceptance": { "requirements_total": 0, "verified": 0, "blocked": 0 },
      "source_request": "verbatim or hash+ref" } ] }
```

The UI reads it per request (no restart needed, R7). Appends are idempotent by `id`+`version`.

## 8. Telemetry contract (adapts T1–T6)

SQLite `adws/data/adw.db`, written by builder AND generated workflows (same schema):

- `runs` — run id, workflow id/version, request ref, config hash, start/end, run status, acceptance status+reason, artifact index (T1).
- `phase_attempts` — phase id/name/kind/owner, attempt, timestamps, duration, status, error, gate ids/results, agent identity incl. effective model+thinking+session+tool allowlist (T2, E5: record the effective model, not the preset).
- `tool_calls` — attribution (run/phase/agent/attempt), call id, tool name, sanitized args, start/end, duration, completion status, ok/error, result ref. One row per call id; incomplete stays incomplete (T3, R9).
- `code_operations` — operation id/name, argv, cwd, duration, return code, passed, stdout/stderr refs+hashes (T4; never mislabeled as agent tool calls).
- `agent_usage` — token buckets (input/output/cache/reasoning/total), cost buckets+total, currency, cost source, completeness (T5). Accumulate every attempt once, including partial-failure usage (E8).
- `requirements` — the requirement coverage table with evidence refs and blockers (A2).

UI surface (3.c): per-agent tool-name counts, errors, duration, model, tokens, cost — with `unknown` shown for missing fields (T6).

## 9. CLI contract (builder itself)

`python adws/adw_workflow_builder.py --request "<text or path/to.md>" [--fixtures] [--stub-agents] [--stub-bad-first] [--db PATH] [--reports-dir PATH] [--max-revisions N]`. Queue intake for the UI (3.c) writes the request to `adws/queue/`; the builder consumes it with the same flags.

## 10. Definition of Done

Every check runs stub-only — no keys, no network, no spend; targeted suites only, never the full suite.

1. This spec exists and its mtime is older than every code file under `adws/` (builder and generated).
2. `python adws/adw_workflow_builder.py --request fixtures/requests/toy_complete.md --fixtures --stub-agents` exits 0; the log shows every agent phase followed by its GATE line; `adw.db` has a `phase_attempts` row per phase and telemetry rows per attempt.
3. `--request fixtures/requests/toy_vague.md` exits 3 (`needs_human`), the report contains questions, and `adws/built/` gains nothing.
4. Refusal fixtures (a poem ask; an edit-sssf ask; a push-deploy ask) each exit 2 with the named reason and zero agent spend.
5. The generated workflow: `python adws/built/<name>/adw_<name>.py --fixtures --stub-agents` exits 0 with `AGENT → GATE` per phase; `python -m pytest adws/built/<name>/tests -q` is green.
6. `--stub-bad-first` end-to-end: attempt 1 FAIL, soft notice carries the exact failure text, attempt 2 PASS (M-pattern).
7. Coverage: a fixture whose spec contains one unmeetable requirement ends `blocked` (exit 4) with that requirement recorded and the rest verified — acceptance is not all-or-nothing silence (R10).
8. Telemetry rows from the stub run contain per-agent tool counts/errors/duration/model; absent provider fields are `unknown`, not 0 (R9).
9. `register` appends the entry; re-running the same build does not duplicate it (idempotent by id+version).
10. Preflight: a seat fixture naming an uninstalled tool (`memory_search`) is rejected at preflight with a named blocker and no agent launch (R1/E1); a write-audit fixture touching a path outside `adws/built/<name>/` fails `diff_claims_real` and the run is not accepted.
11. Stub mode opens zero network sockets (socket-guard test).
12. Generated code contains no `git `, no `requests`/`urllib`/`http` client calls (grep gate in validators).
13. Root `AGENTS.md` carries the pointer section to this spec (done in this task).

## 11. Non-goals

No fusion-harness TypeScript changes for the builder (the pi YAML workflow registry keeps its fixed command set); no sssf edits; no launchd scheduling for generated workflows (desk-launch only); no live-model claims — stub evidence is the delivered proof; no publication, deployment or outreach authority anywhere.

---
Governed by AGENTS.md — see ../../AGENTS.md for the rules this file operates under.
