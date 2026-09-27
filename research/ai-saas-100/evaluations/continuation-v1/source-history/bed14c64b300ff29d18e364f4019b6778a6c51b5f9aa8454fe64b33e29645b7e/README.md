# Continuation v1 independent evaluator

This version persists the W/M/C/S cases authored in:
`/tmp/fusion-harness-plXwRt/collaborate/reports/1.d-glm.md`.
The source report hash and frozen campaign thresholds are in `suite.json`.
It incorporates the current interface handoff from task 1.a of
`/tmp/fusion-harness-1wQDAO/collaborate/`.

**Exposure: `independent_authored_exposed`. This is not a hidden suite.**
All builders could read the source report. Passing these cases cannot replace the
campaign requirement for an independently retained, unexposed evaluation version.
No implementation file is modified by this evaluator delivery.

## Contents

- `inputs/<case>/<test>.json`: 56 complete groups, eight normal and six adversarial
  for each of 001, 002, 003 and 033. Each group has one or more fully materialized
  `runs`. Variants execute from fresh state and all must pass for a group to pass.
- `oracles/<case>/<test>.json`: expectations and semantic review requirements.
  Never supply these files to B1, a product implementation, or an interpreter.
- `components/C-LOCAL-A{2,3,6}.json`: three explicitly structured CRM control
  groups for local approval/denial, staleness and tampering checks. These cannot
  replace the corresponding natural-language cases or contribute normal-case wins.
- `adapters.py`: oracle-free callable interfaces for stateless workflows,
  marketplace operations and CRM persistence. No product modules are imported.
- `evaluate.py`: observation validators. It writes nothing and calls no product.
- `test_evaluator.py`: synthetic checker tests and test doubles only.
- `run_selftests.py`: creates a unique freeze and captures bounded self-test
  execution plus preservation hashes. This command writes new evaluator artifacts.
- `materialize.py`: reproducible case construction, refusing existing fixture
  directories. Do not rerun it in place. A changed suite needs a new version.

## Run only evaluator self-tests

From the repository root, with the caller's command timeout at most 60 seconds:

```sh
python3 -B research/ai-saas-100/evaluations/continuation-v1/run_selftests.py
```

Each invocation first freezes inputs, oracles, adapters, checker, tests and other
version files, then invokes only synthetic self-tests with a 40-second child
limit. Receipts are append-only under `selftest-receipts/<unique-id>/`.
`result.json` references the exact `freeze.json`, stdout/stderr and preservation
manifest. Prior failures and freezes remain intact after any evaluator correction.
Tests use no product modules, inference, real CRM storage, calendar or network.
Any synthetic `inference_executed: true` flag in test observations is a checker
branch input, not a claim of model execution. The receipt always says no inference
and no product acceptance.

The preservation check hashes campaign files outside this evaluator directory
before and after the child. It does not inspect the home directory or secrets.
This is evidence of preservation during self-tests, not an OS sandbox.

## Execute products later, under their delegated evaluation tasks

For any product run, retain the exact input bundle, source snapshots, adapter
hashes, actual commands, outputs, timing, errors, cost classification and real
capability evidence. Verify the referenced freeze before and after execution.
Reuse an unchanged frozen version, or make a new version; never overwrite a
historical freeze to match changed bytes.

Instantiate adapters with explicit, reviewed implementation callables. The adapters
never choose actions or source code by test ID. They never load an oracle. Do not
substitute expected structured CRM commands for natural-language inference.

- Rewrite and scheduling: `adapters.call_workflow(function, run, observer)` returns
  output/error, measured input preservation and caller-supplied effect observations.
  Actual inference receipts and semantic-review data must be attached separately.
- Marketplace: `adapters.execute_market(module, run, observer)` maps explicit
  operations to the existing `Marketplace` interface. `save_as` captures the
  **actual returned** assignment ID; `{"$ref":"a1"}` resolves only that handle.
  Requests contain the full initial state, arguments and clocks. No expected target
  or assignment is inserted by the adapter. Traces preserve complete before/after
  state and actual response values.
- CRM: `adapters.execute_crm(store_factory, interpret, run, preview, observer)` uses
  the current `SyntheticStore.initialize/propose/decide/apply/read` API. The factory
  creates a unique disposable store and returns a fresh instance for `reopen=True`.
  The caller owns authorized case-local storage and safe cleanup. The adapter
  never accepts a user-provided filesystem path. Proposal handles and approval
  records come from actual returns. A missing interpreter blocks the natural-
  language sequence rather than filling it from expected answers.
- The CRM interpreter callback gets only `(request_text, current_public_store)`.
  It returns `inference_executed: true` with actual receipt evidence supplied by the
  runner and either `structured_request` or status `clarification`, `refused`, or
  `unavailable`. A flag alone does not prove a model call. The runner and independent
  reviewer must verify the corresponding actual execution record.
- C-A3's intervening change is explicitly supplied authorized test data. C-A6
  modifies a local copy of the returned proposal. Neither action derives the
  normal command from evaluator expectations.

An observer reports actual instrumentation counters, not implementation assertions:
`network_calls`, `external_writes`, `secret_reads`, `outside_path_accesses`, and
`calendar_writes`. Missing instrumentation remains unknown/blocked. All effects
must be zero except separately authorized model transport calls. Those need
`authorized_model_calls`, a matching network count, and `authorization_receipt`.
The caller must verify the authorization and restrict the route, not trust an
unverified flag or arbitrary model-selected endpoint. Python-level hooks are not
OS containment. Pure local tests have no authorized network exceptions.

For B1, record `system: "B1"` in observations if using authorized model transport.
Use equivalent complete inputs and explicit interface transformations. B1 can
return the required trace/state schema without receiving the oracle. Fixtures,
expected answers, old repair suites containing answers, and test descriptions
are not model context.

Evaluate a saved list of observations, one per materialized run:

```sh
python3 -B research/ai-saas-100/evaluations/continuation-v1/evaluate.py \
  research/ai-saas-100/evaluations/continuation-v1/inputs/033/S-N1.json \
  research/ai-saas-100/evaluations/continuation-v1/oracles/033/S-N1.json \
  PATH_TO_ACTUAL_OBSERVATIONS_JSON
```

This evaluates observations, not their provenance. It returns group `passed`,
`failed`, or `blocked`, variant findings, and `product_acceptance: false`.
Implementation exceptions need retained raw evidence even when no observation
can be formed. Do not reuse the legacy local pilot runner to claim real inference:
its receipts are explicitly marked no inference. Case 002 repair-v2 `execute.py`
and `validate.py` are fixed-output evidence writers and must not be blindly rerun.

## Semantic and scheduling limits

Rewriting requires real generated text plus independent semantic review bound to
that exact text. The checker does not pretend substring preservation proves
meaning. A review includes reviewer identity, independence, exact `output_text`,
`preserves_meaning`, `no_added_claims`, `readable`, and a passed/rationale entry for
each oracle semantic requirement. The swapped North/South counts self-test proves
that retaining all literal tokens does not override a negative semantic finding.
Subjective reviewer identity, independence and rationale need audit; JSON flags
alone are not evidence of a trustworthy review.

Scheduling recomputes intervals, exact task minutes, overlap, deadlines, split
rules, meetings, buffer spacing, and missing/duplicate task accounting. It does
not trust `constraints_checked`. The E6 conventions are frozen in each schedule
oracle: higher numeric priority for equivalent competing tasks, half-open time
intervals, buffers between tasks and meetings but not beyond workday boundaries.
Known feasibility witnesses are evaluator examples, not inputs to the scheduler.
A search-limited result is incomplete evidence, never proof of infeasibility.

## Acceptance and scoring

Keep the original 50/20/20/10 correctness/coverage/constraints/usability weights,
normal mean >=80, at least 7/8 normal passes, at least 5/6 adversarial passes,
zero critical failures, and >=90% usable planned paired coverage. Mandatory
semantic, state and feasibility assertions cannot be averaged away. Assertions
here are prerequisites; this tool does not fabricate weighted scores or aggregate
product acceptance. Independent reviewers must record those scores and evidence.

Repeat normal groups N1/N4/N8 twice more per system, preserving every attempt.
There are 20 planned group attempts per system. Because parameterized groups have
multiple executions, report **both** group and invocation denominators:
001 has 22, 002 has 22, 003 has 23, and 033 has 20 planned invocations including
repeats. Missing capability does not license dropping an arm or denominator after
seeing results. Component-only CRM controls are additional evidence, not substitutes.

Original-product access remains optional for bounded independent evaluation and
mandatory for parity claims. This delivery establishes executable evaluator
artifacts and self-test evidence only, not any accepted product or 24-hour run.
