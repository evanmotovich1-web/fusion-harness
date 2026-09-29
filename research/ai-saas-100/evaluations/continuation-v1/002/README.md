# Independent case 002 marketplace evaluation

This review executes the task-1.b recovered, hash-bound marketplace source
selected by `research/ai-saas-100/execution-manifest.json`
(`cases/002/implementation/workflow.py`, sha256
`4f53995db9a3b5ea3306e53c8babfc1a7cf1c7f88983423bd945bbd0e463aaeb`,
loaded from the content-addressed copy under `source-archive/sha256/`).
The active file, the manifest binding, and the archived snapshot bytes are
all verified equal before execution; the executing module is the archived
copy, immune to later active-file edits.

Fixtures are the frozen `independent_authored_exposed` groups
`inputs/002/M-N1..M-N8` and `M-A1..M-A6` with separate oracles
(`oracles/002/...`), verified against the evaluator freeze
`selftest-receipts/20260922T040256033925Z-863d211b/freeze.json`.
Oracles are used only by the checker; they never reach the implementation.

## Run

From the repository root, with the outer command limited to 60 seconds:

```sh
python3 -B research/ai-saas-100/evaluations/continuation-v1/002/execute.py
```

The executor creates a unique `runs/<timestamp-id>/` directory, records a
preservation manifest of the campaign tree before and after, freezes exact
source/evaluator/input/oracle bytes into `snapshots/`, then runs
`run_market_review.py` as a bounded foreground child (40-second timeout).
The child writes nothing; its stdout is retained as `stdout.json`. A
`receipt.json` binds source, manifest, freeze, inputs, oracles, adapters,
checker, outputs, timing, and preservation results. Prior runs are never
replaced.

## Executed scope

All 14 M-groups plus the suite-mandated repeats of M-N1, M-N4 and M-N8
(two extra attempts each): 20 group attempts and 22 planned invocations
(M-A4 and M-A5 are parameterized with two variants each). Group and
invocation denominators are reported separately and no arm is dropped.

Operations run through `adapters.execute_market` with complete initial
state, explicit operations and clocks. `save_as` captures only actual
returned assignment identities; `$ref` arguments resolve those handles.
Traces retain complete before/after snapshots and actual response values.

Checked behaviors (recomputed by `evaluate.py`, never trusted from flags):
matching exclusions (self, equal host, DR gap, review status), deterministic
distance-then-ID ties, pending-assignment reuse, reverse-pair restriction
while pending or reported_local, expiry at `now >= deadline`, rejection,
late reporting of expired assignments under the frozen local policy, URL
scope and owner approval on `report_local`, and inert escaped anchor
generation in `link_html`.

## Effect accounting

A Python audit hook is active around every marketplace call. Any socket,
subprocess, exec, or file-open event during wrapped calls aborts the run.
The observer reports actual counters (`network_calls`, `external_writes`,
`secret_reads`, `outside_path_accesses`, `calendar_writes`), all required
zero. Audit hooks are instrumentation, not OS containment.

`cases/002/tests/repair-v2/execute.py` and `validate.py` are fixed-output
evidence writers and are never executed; their bytes are hashed before and
after the run and recorded in the receipt.

## Limits

- Local deterministic subset only. Editorial judgment, live marketplace
  behavior, vendor parity, and any hidden evaluation are not assessed.
- B1 (generic model baseline) is `blocked_not_executed`: no authorized
  inference route exists (`capabilities-continuation.json`). Its absence is
  not a failed comparison.
- B3 (original product) is `not_observed`.
- Passing this exposed suite establishes component correctness only.
  `product_acceptance` remains false; weighted scoring and acceptance
  require independent review beyond these assertions.
