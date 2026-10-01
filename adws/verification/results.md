# Workflow-builder verification: acceptance blocked

Verified by SOL, task 5.a, 2026-10-01 01:04:51 UTC.

**Result: 36 tests passed, 7 acceptance regressions failed, 4 unittest subtests passed. Implementation acceptance is rejected. Repair owner: direct dependency task 4.a (GROK).** The nominal toy build, generated stub workflow and localhost endpoints work. They do not establish request-specific correctness or complete safety/telemetry enforcement.

## Scope and isolation

Added only:

- `adws/tests/conftest.py`: temporary built root, registry, DB, reports and queue; credential-variable removal; subprocess INET socket guard; per-test socket restoration.
- `adws/tests/test_builder_verification.py`: numbered DoD checks and seven unsuppressed acceptance regressions.
- `adws/tests/test_desk_endpoints.py`: real HTTP tests on `127.0.0.1`, port 0, with a non-daemon server thread shut down and joined in `finally`.
- This record, `adws/verification/results.md`.

No implementation, prompt, fixture, registry, existing test, spec, extension or Homecare source was edited. Generated test artifacts and SQLite databases live in temporary directories, not the checkout's built tree. Credentials are not used. Subprocesses forbid INET socket construction, including generated tests launched by validators. HTTP endpoint tests alone use loopback sockets in the parent test process. No external network access, model call, spend or detached process occurred. No resident server was left running. Every validation tool call was bounded to 60 seconds and every explicitly launched subprocess to at most 55 seconds.

The existing `test_builder_core.py` changes global socket functions. The new autouse fixture restores those functions after each test so it cannot poison the subsequent HTTP checks. Existing tests were not rewritten.

## Actual focused commands and results

Environment for pytest commands: `PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. Use the existing interpreter with pytest, no installation:

```text
$ homecare/.venv/bin/python -m pytest adws/tests -q -p no:cacheprovider --tb=short
exit: 1
........................FFFFFFF............                          [100%]
7 failed, 36 passed, 4 subtests passed in 13.47s
```

All seven failures remain ordinary failed assertions. None is skipped, xfailed or weakened to get green.

For independent confirmation of the nominal paths only, the seven regression names were explicitly deselected:

```text
$ homecare/.venv/bin/python -m pytest adws/tests -q -p no:cacheprovider --tb=short -k 'not actual_outside_write and not generated_agents_have_telemetry and not completed_tool_errors and not declared_requirement_verifier and not requirement_specific_gate and not generated_unknown_tool and not original_request_not_replaced'
exit: 0
....................................                                 [100%]
36 passed, 7 deselected, 4 subtests passed in 10.21s
```

That selective green result is **not acceptance**. The failing all-feature run above is authoritative. No repository-wide suite was run.

Additional CLI evidence:

```text
$ homecare/.venv/bin/python -m pytest adws/tests/test_builder_verification.py -q -s -p no:cacheprovider -k 'dod02 or dod05 or dod06 or dod07'
exit: 0
4 passed, 19 deselected in 2.09s
```

Initial test-development runs encountered pytest's reserved parametrization name `request`, then two incorrect test expectations: a scout failure string copied from another seat, and a blocker reason expected on stdout rather than in the persisted DB. Those test defects were corrected against actual fixture/persistence contracts before the authoritative run. No implementation change was made to accommodate them.

## Every numbered Definition of Done

Source: `adws/specs/workflow-builder.md`, section 10. Test names below are in `test_builder_verification.py` unless stated otherwise. PASS is scoped to the specific asserted check, not a claim that the whole builder is accepted.

| DoD | Status | Actual evidence |
| --- | --- | --- |
| 1 | PASS | `test_dod01_spec_predates_all_python`: spec mtime precedes every checkout `adws/**/*.py`, including these tests and generated code. Existing core test independently checks the same relationship. |
| 2 | PASS, nominal | `test_dod02_builder_phase_chain_and_attempt_records`: toy complete exits 0 with each of four seats' AGENT→GATE lines. SQLite has 4 agent rows and 9 phase rows, including intake/survey/spec/spec_review/scaffold/implement/validate/validate_stamp/register. Run acceptance is `accepted`. |
| 3 | PASS | `test_dod03_vague_request_preserved_without_artifacts`: vague exits 3, questions persist, verbatim request remains in `spec.json`, unknown fields are `<EVAN: fill>`, no agent rows and no built directory are added. |
| 4 | PASS | Three parametrized `test_dod04_named_refusals_before_spend` cases: poem → `not_workflow`, edit SSSF → `forbidden_target`, push/deploy → `forbidden_target`. Each exits 2 with zero agent rows and no generated artifact. |
| 5 | PASS, nominal | `test_dod05_generated_cli_and_focused_tests`: generated echo CLI exits 0 with `AGENT greeter → GATE greeting_nonempty PASS`; its focused suite reports `4 passed in 0.01s`. This does not resolve F10/F11's missing verifier and semantic-check defects. |
| 6 | PASS | `test_dod06_bad_first_exact_soft_notice`: first failure's exact disk-fixture text appears in soft notice and attempt-2 prompt, then attempt 2 passes. All four seats have two recorded attempts, giving 8 agent and 13 phase rows. |
| 7 | PASS, nominal | `test_dod07_partial_coverage_is_inspectable`: named unmeetable fixture exits 4. SQLite has req-1 `verified` and req-2 `blocked` with a concrete human-decision blocker. No registry entry is written. These are fixture-level coverage labels, not evidence that arbitrary requirements are fulfilled. |
| 8 | FAIL | `test_dod08_builder_telemetry_each_agent_and_attempt` passes for the builder: every agent has tool names/counts/errors, positive duration, model/tokens/cost `unknown`, plus usage and call rows. But F8 loses completed tool errors and F9 records no generated agent rows, violating the shared telemetry contract in section 8. |
| 9 | PASS | `test_dod09_registration_is_idempotent`: second build uses the same temp registry, still exactly one entry, with `build_run_id=second`. HTTP rediscovery also sees a later build without restart. |
| 10 | FAIL | `test_dod10_unknown_tool_preflight_is_fixture_driven` and `test_dod10_claimed_outside_write_refused` pass for explicit nominal fixtures. F7 shows an actual unclaimed outside mutation accepted, and F13 shows a generated seat with `memory_search` accepted. The full capability/write guarantee is not met. |
| 11 | PASS, nominal | `test_dod11_socket_guard_covers_subprocess_tree` plus fixture teardown: builder, generated workflow and generated pytest subprocesses create zero INET sockets under an independent `sitecustomize` guard. Parent HTTP probes use only loopback. |
| 12 | PASS, nominal | `test_dod12_generated_forbidden_client_scan`: generated Python passes the validator's git/requests/urllib/http-client/URL scan. This lexical check is not claimed to be a sandbox or complete side-effect proof. |
| 13 | PASS | `test_dod13_root_authority_pointer`: root `AGENTS.md` points to the frozen spec and names stub-first invocation. |

### Real CLI output excerpts

The test command prints full argument lists with private temporary DB/report paths. These excerpts retain actual logged lines, not invented expected output.

Toy complete:

```text
EXIT: 0
[21:03:55] AGENT workflow_scout attempt 1 (stub)
[21:03:55] AGENT workflow_scout → GATE workflow_scout PASS
[21:03:55] AGENT spec_writer → GATE spec_writer PASS
[21:03:55] AGENT reviewer → GATE reviewer PASS
[21:03:55] CODE scaffold: 11 files
[21:03:55] AGENT builder → GATE builder PASS
[21:03:55] AGENT builder → GATE diff_claims_real PASS
[21:03:56] CODE validate → GATE fresh_verification PASS
[21:03:56] CODE validate_stamp → GATE fresh_verification PASS
[21:03:56] CODE register → GATE registry PASS
[21:03:56] DONE accepted exit=0
```

Generated echo workflow and its own pytest:

```text
EXIT: 0
CODE intake: build
AGENT greeter → GATE greeting_nonempty PASS
GATE  greeting_nonempty attempt 1 PASS

EXIT: 0
....                                                                     [100%]
4 passed in 0.01s
```

Bad-first correction:

```text
EXIT: 0
[21:03:56] AGENT workflow_scout → GATE workflow_scout FAIL
[21:03:56] GATE  workflow_scout attempt 1 FAIL:
        - workflow_scout: fixture gate failed — survey: at least one pattern is required
[21:03:56] SOFT NOTICE: workflow_scout: fixture gate failed — survey: at least one pattern is required
[21:03:56] AGENT workflow_scout attempt 2 (stub)
[21:03:56] AGENT workflow_scout → GATE workflow_scout PASS
[21:03:56] GATE  workflow_scout attempt 2 PASS
[21:03:56] SOFT NOTICE: spec_writer: fixture gate failed — schema missing requirements
[21:03:56] GATE  spec_writer attempt 2 PASS
[21:03:57] DONE accepted exit=0
```

Unmeetable fixture:

```text
EXIT: 4
[21:03:57] CODE validate → GATE fresh_verification PASS
[21:03:57] CODE validate_stamp → GATE fresh_verification PASS
[21:03:57] DONE blocked exit=4
```

SQL query `SELECT req_id,status,blocker FROM requirements` returned:

```json
[
  {"req_id":"req-1","status":"verified","blocker":null},
  {"req_id":"req-2","status":"blocked","blocker":"unmeetable: no local executor can satisfy this requirement; needs a human decision before it can ever be verified"}
]
```

Toy builder agent summary, measured from the same successful run:

| Agent | Tools | Errors | Duration ms | Model |
| --- | --- | --- | --- | --- |
| workflow_scout | read: 1 | 0 | 1 | unknown |
| spec_writer | read: 1, write: 1 | 0 | 1 | unknown |
| reviewer | read: 1, write: 1 | 0 | 1 | unknown |
| builder | read: 1, write: 1 | 0 | 1 | unknown |

These are stub-declared calls and minimum-clamped durations, not provider usage or measured model latency. The tests verify all provider token/cost fields remain `unknown`.

## Seven acceptance failures and repair handoff

Codes F7–F13 extend the prior survey's F1–F6. Every case is reproduced in the on-disk test source, with no change to production code.

| Code | Failed test | Observed result | Required repair in task 4.a |
| --- | --- | --- | --- |
| F7 | `test_actual_outside_write_blocks_acceptance` | A substituted stub builder writes a harmless temporary sentinel outside both allowed built/run directories, does not claim it, and the run still returns 0/registers. | Enforce writes through the actual runner boundary and detect actual unclaimed mutations, not just declared artifact hashes. `allow_write` is currently not connected to `PhaseRunner`/Pi tools. The fixture tests an unlogged mutation, not a real protected-file overwrite. |
| F8 | `test_completed_tool_errors_are_not_lost` | One Pi-shaped tool start followed by an error completion is returned as `incomplete`, `ok=null`; the end event is ignored. | Join starts/ends by attributed call id, retain completion/error/duration/results, and keep truly interrupted calls incomplete. Audit/rollup must count observed completion errors. |
| F9 | `test_generated_agents_have_telemetry_rows` | Generated CLI exits 0, database contains one agent phase but zero `agent_runs` rows. | Generated workflows must write the shared run, agent/call/usage telemetry with honest missingness. A phase-only row is insufficient for UI tool/time/model/token/cost visibility. |
| F10 | `test_declared_requirement_verifier_exists` | Requirement is `verified`, declares `test_greeting_nonempty`, but no generated focused test defines that verifier. | Resolve every declared verifier to executable checks and only mark verified when those checks actually run. Otherwise record a blocker. |
| F11 | `test_requirement_specific_gate_rejects_wrong_total` | For a new request requiring total exactly 7, the generated gate accepts `{result: "8", total: 8}` and says `req_1_gate passed`. | Build objective requirement-specific semantics or explicitly block unsupported requirements. Nonempty-string checks cannot verify totals, side effects or arbitrary user outcomes. Do not mark generic fixtures as proof of those requirements. |
| F12 | `test_original_request_not_replaced_by_shared_fixture` | New count-check request exits 0 but generated `request_verbatim` is the old echo-check toy request. | Bind fixtures/spec/review to the current verbatim request. Mismatch must block, never silently reuse another request's approved specification. |
| F13 | `test_generated_unknown_tool_is_blocked` | An isolated spec fixture adds `memory_search` to the generated seat; the workflow is accepted and registered with exit 0. | Preflight generated seats and phase tools too, not only the builder's four own seats. Unknown capabilities must block before generated execution/acceptance. |

Actual failing-run summary:

```text
FAILED adws/tests/test_builder_verification.py::test_actual_outside_write_blocks_acceptance
FAILED adws/tests/test_builder_verification.py::test_generated_agents_have_telemetry_rows
FAILED adws/tests/test_builder_verification.py::test_completed_tool_errors_are_not_lost
FAILED adws/tests/test_builder_verification.py::test_declared_requirement_verifier_exists
FAILED adws/tests/test_builder_verification.py::test_requirement_specific_gate_rejects_wrong_total
FAILED adws/tests/test_builder_verification.py::test_generated_unknown_tool_is_blocked
FAILED adws/tests/test_builder_verification.py::test_original_request_not_replaced_by_shared_fixture
7 failed, 36 passed, 4 subtests passed in 13.47s
```

Representative actual assertion outputs:

```text
an actual unclaimed outside write was accepted; claim-only audit is insufficient
assert 0 == 4

generated workflow records phases but no per-agent tool/time/model/token/cost rows
assert 0 == 1

completed error was retained as an incomplete start
assert 'incomplete' == 'complete'

requirement marked verified without its declared verifier: test_greeting_nonempty

gate accepted total 8 for exactly-7 requirement: req_1_gate passed
assert not True

generated seat declares an absent tool but the workflow is accepted
assert 0 == 4

shared fixture replaced the original request before acceptance
- Build a workflow named count-check that must verify the number of records equals exactly 7.
+ Build a workflow named echo-check that must gate a greeting is a nonempty string.
```

The implementation issue is broader than a failed toy test. The acceptance path currently verifies template structure and generic fixture responses, then reports requirements verified even when their semantics or declared verifiers were not checked. These tests do not exhaust all safety/schema/runtime failure modes. They are enough to reject acceptance without implying unseen paths work.

## Localhost UI evidence

`test_desk_endpoints.py` contributes 12 passing cases to the focused run:

- **U1:** `/api/workflows` equals the actual temporary registry, and sees its refresh without restarting the server.
- **U2:** `POST /api/builds` creates a real temporary queue file. Its contents are consumed by the actual stub builder. `/api/builds/verify` returns the resulting accepted build and four agent summaries.
- **U3:** `/api/builds` exposes tool counts/errors/duration/model with unknown token/cost fields, not fabricated zeros.
- **U4:** `POST /api/launch` launches the generated workflow only with fixture/stub flags and records its phase row in a temporary launches database. This pass does not resolve F9 or claim the launched run has complete UI telemetry.
- **U5:** Seven malformed/missing endpoint cases return named 400/404 errors.
- **U6:** Server CLI refuses `--host 0.0.0.0` with exit 2 before binding.

Every server thread was shut down and joined. No resident UI process was left running. Existing task-4.b live endpoint evidence remains in `adws/reports/desk-integration.md`, unchanged.

## Gemini OAuth evidence from task 2.b

Source: `adws/specs/gemini-oauth-evidence.txt`, preserved byte-identical during task 5.a. These are the earlier task's actual machine/fixture results, not new live probes performed by this verification:

```text
pi auth check --provider google-vertex
exit: 1
not_ready

pi --no-extensions --list-models google-vertex
exit: 0
No models matching "google-vertex"

PI_OFFLINE=1 just fusion-gemini --no-session --no-tools --mode rpc
exit: 1
Gemini OAuth is not configured. Run: gcloud auth application-default login
Set GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION in .env. See README.md for installation and billing.
```

The stack's parser/catalog/configured-auth fixtures and 17 focused stack regressions passed in 2.b. Empty credential-file existence in its positive fixture is not a usable OAuth login. Direct Pi RPC emitted stack errors but exited 0 on stdin closure. The new guarded recipe correctly exits 1 before launch. No extension source was changed to implement OAuth.

**G1:** Repo integration/missing-auth refusal: PASS against retained 2.b evidence. **G2:** Live Vertex authentication/model call: NOT VERIFIED, awaiting Evan's setup. This is a known operator prerequisite, not the repair target for this failed builder acceptance.

Evan's steps: install gcloud, choose a billed project with Vertex AI API enabled, run `gcloud auth application-default login`, set/export `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`, then verify auth and the clean-room catalog before `just fusion-gemini`. `GEMINI_API_KEY` stays the independent AI Studio path. Vertex is not free subscription access. No credential values are in this record.

## Preservation and repository boundaries

Before writing tests, a read-only local status snapshot listed 2,522 porcelain entries. It was stored with 1,461 file hashes in a private temporary baseline. This local task baseline is not a replacement for the supplied harness repository-state card.

Hashed files included all preexisting files under `homecare/`, `extensions/` and `adws/`, plus `duckdb20_fusion_lab/lab.sql`, root `AGENTS.md`, README, `.env.example`, justfile and the Gemini OAuth stack. After tests:

```text
Baseline hashed-file differences: []
Status additions:
  ?? adws/tests/conftest.py
  ?? adws/tests/test_builder_verification.py
  ?? adws/tests/test_desk_endpoints.py
Status removals: []
PASS untouched-neighbor hashes and scoped status delta
```

Final checks after writing this record confirmed exactly four new files, including `adws/verification/results.md`, no baseline status removals and unchanged hashes for all 1,461 preexisting scoped/neighbor files. Test syntax, whitespace, all 13 DoD table rows and the governance footer passed. No preexisting byte changes, removals, staging or index changes were made. Existing Homecare, self-compact, lab, builder, generated tree, prompt, registry, Gemini and integration work are preserved.

No mutating Git operations were performed: no commit, push, fetch, pull, merge, rebase, reset, cleanup, stash or ref update. Read-only `git status` is used to prove the delta, so this record does not falsely claim zero Git commands. Test data did not execute Git. No publication or deployment is authorized, and the supplied dirty repository card is not cleared by passing any test.

## Exact next handoff

1. **H2:** Reopen direct dependency **4.a** for GROK to repair F7–F13 in its owned core/generated-runtime modules. Preserve these regression assertions and return explicit blockers rather than inventing semantic implementations.
2. **H3:** Rerun the full focused command `homecare/.venv/bin/python -m pytest adws/tests -q -p no:cacheprovider --tb=short`, with the environment above, after repair. Require the seven regressions to pass without skips/xfails and inspect fresh artifacts.
3. **H4:** Update this record with actual new results. Host integration/acceptance remains independent. Do not describe this verification or the blocked collaboration as successful delivery.

## Host recovery (not collaboration acceptance)

Pi host repaired F7–F13 in the builder core after the graph blocked. The child reports above stay blocked. This section is host evidence only.

Repairs, confined to `adws/adw_workflow_builder.py` and `adws/builder_modules/`:

- F7: `PhaseRunner` snapshots the run/built parent around `runner.run` and fails the phase on an unclaimed mutation. `allow_write` classifies those paths. Main returns 4 and does not register.
- F8: tool starts and ends join on `toolCallId`. A completed `isError` stays `complete`/`ok=false`. A start with no end stays incomplete.
- F9: generated workflows insert `agent_runs`, `tool_calls`, and `agent_usage` with token/cost `unknown`.
- F10: generated tests define each declared verifier. Acceptance marks `verified` only when that function is in the pytest `-v` log.
- F11/F12: a shared fixture whose `request_verbatim` differs is a request mismatch (exit 4, not registered). An exact-total requirement with no objective gate stays blocked instead of being proved by a nonempty-string check.
- F13: generated seat and phase tools are preflighted. `memory_search` blocks before scaffold/register.

Host command, after the repair:

```text
$ homecare/.venv/bin/python -m pytest adws/tests -q -p no:cacheprovider --tb=short
exit: 0
...........................................                          [100%]
43 passed, 4 subtests passed in 11.65s
```

No skips and no xfails. Live Gemini is still not verified. No commit, push, deploy, or outreach.

## H4 gate after desk wiring and echo-check rebuild (task 2.a)

Reran after task 1.b (desk `desk_status` / Gemini seat) and task 1.c (stub rebuild of `adws/built/echo-check`). This is the focused suite only. No skips, no xfails. Count grew from the 43-passed host baseline by the 1.b desk tests.

```text
$ PYTHONDONTWRITEBYTECODE=1 homecare/.venv/bin/python -m pytest adws/tests -q -p no:cacheprovider --tb=short
exit: 0
.............................................                        [100%]
45 passed, 4 subtests passed in 12.54s
```

Downstream staging may proceed on this green run. Live Gemini login is still not verified. No commit or push from this task.

---
Governed by AGENTS.md — see ../../AGENTS.md for the rules this file operates under.
