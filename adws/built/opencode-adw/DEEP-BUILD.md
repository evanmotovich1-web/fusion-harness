# Deep build with Jev — implementation contract

Purpose: spend additional model work on independent planning, executable edge-case
tests and bounded repairs. Token consumption is measured, never padded to a target.

Workflow ID and CLI mode: `deep`. Existing build/review/takeover behavior stays
compatible. New model flags: `--planner-model`, `--testdesigner-model`, falling
back to the shared `--model`, alongside worker/reviewer overrides.

## Ordered work

1. `opencode-planner` inspects the repository read-only and returns strict JSON:
   `{"requirements":["..."],"plan":["..."],"risks":["..."]}`.
2. `opencode-testdesigner` independently inspects the contract and plan read-only.
   Returns `{"cases":["..."],"format":"python_unittest|node_test|checklist",
   "code":"..."}`. Test code is written by the runner into its private run
   directory, outside the target repository, and hash-frozen before any builder.
   Generated tests must target the public request, not private evaluation cases.
   Python tests use `OPENCODE_ADW_REPO` to locate target imports; Node tests use
   that same environment variable. Checklist mode executes no generated test.
3. Jev recommends a focus using plan/case summaries. The builder receives that
   focus plus the actual plan and cases. Jev supplies typed choices, not prose.
4. Builder implements; code executes frozen generated tests and user-supplied
   checks; a fresh read-only reviewer examines actual requirements and receipts.
5. Jev advises `finish`, `repair`, `stop`, or `other`, with confidence and a
   separate repair-focus choice. Code may finish only when meaningful checks
   have actually passed, the reviewer returned PASS, and no integrity gate failed.
   A Jev finish hint never overrides failed/missing checks or reviewer findings.
6. On actionable failures, a Jev repair recommendation directs at most one
   repair by default (`--max-repairs`, bounded 0–2). Rerun the same frozen tests
   and all checks, then use another fresh reviewer. Never overwrite earlier logs.

Four named role sessions are independent. Only Builder edits target source.
Planner/testdesigner/reviewer mutations fail. Generated-test changes fail.
Python tests report an actual unittest test count; Node tests report native TAP
counts. An empty or broken generated suite cannot pass. With checklist mode,
at least one explicit operator check is required; omitted checks are not passes.
Test-created target source changes are detected; this is not an OS sandbox.

## Jev adapter

`jev_bridge.py` reuses the existing SSSF `adw_modules/jev.py` client, rather than
creating another HTTP/auth implementation. Default client path is
`~/code/sssf/adws/adw_modules/jev.py`, overridable with
`OPENCODE_ADW_JEV_CLIENT`. Credentials use `TYPESAFE_API_KEY`, with a narrow
literal-only lookup of that variable in existing `~/code/sssf/.env` if absent.
Never execute dotenv contents or copy credentials. Disabled/unavailable/refused,
malformed or mock Jev results stop deep mode explicitly. Valid but uncertain
advice routes one additional read-only assessment at that decision point. It does
not lower the confidence threshold or invent a more confident model answer.

Public adapter functions:

- `status()` → `{configured, model, reason}` (configuration check, no inference).
- `decide(state, *, receipt_dir, label, budget_s=10)` →
  `{recommendation, focus, confidence, probabilities, model_requested,
  model_resolved, input_tokens, output_tokens, elapsed_ms, receipt_path}`.

`state.phase` is `focus` or `decision`. Focus recommendations are `build|stop|other`;
decision recommendations are `finish|repair|stop|other`. Focus labels are
`correctness|edge_cases|test_coverage|scope|other`. Confidence floor is provisionally
0.5, recorded as a policy setting, not a validated accuracy guarantee. Responses
retain the original recommendation/probabilities/confidence and add a code-owned
`route: advice|consult`. A focus consultation checks pre-build readiness; a
decision consultation independently checks completion or concrete repair evidence.
Only one consultation per decision point is allowed, using the selected Reviewer
model and another fresh session. Completion still needs all checks and the
original review to pass, plus consultation PASS when that route was taken.
Jev calls
receive bounded sanitized summaries, never credentials or full raw test code.

Receipts preserve actual role models, every attempt/session, tests/check results,
Jev choice/probabilities/confidence/model/usage, repair count and before/after
states. No automatic commit/push/deploy. Never claim increased quality from token
count or from a synthetic smoke alone; compare fresh graded tasks.

---
Governed by AGENTS.md — see the repository and target-project instructions.
