# Independent case 033 scheduling evaluation

This review executes task 1.e's archived, hash-bound `workflow.schedule`, not the
mutable `cases/033/implementation` tree. The source manifest is
`cases/033/source-history/scheduler-v1-6e16e7e43d6b5d1d/source-bundle.json`.
Every archive member is verified before and after execution and retained in each
new run. Oracles and feasibility witnesses are never supplied to the scheduler.

## Run

From the repository root, with the outer command limited to 60 seconds:

```sh
python3 -B research/ai-saas-100/evaluations/continuation-v1/033/execute.py
```

The executor creates a unique `runs/<timestamp-id>/` directory, freezes exact
source/evaluator/input/oracle/adapter bytes before execution, captures stdout/stderr
with a 40-second child timeout, and appends `receipt.json`. It never replaces prior
receipts or modifies product implementations. The child imports only the archived
`schedule` function through `adapters.call_workflow`.

## Checks

All 14 frozen S-groups (S-N1..S-N8, S-A1..S-A6) plus two extra repeats of N1, N4
and N8: 20 group attempts and 20 planned invocations. Scoring uses
`evaluations/continuation-v1/evaluate.py` against separate oracles. The checker
recomputes interval times (HH:MM), exact task minutes, identity, overlap, working
hours, deadlines, split rules, E6 buffer conventions, immutable meetings, and
unscheduled accounting. It does not trust `constraints_checked`. `search_limited`
is incomplete evidence, never proof of infeasibility.

Malformed input and instruction-like fields are the frozen A-groups. All frozen
requests set `write_to_calendar` false; the archived validator rejects any other
value. Python audit hooks record network, file, and process events during
`schedule` calls. Observer effects must all be zero. No real calendar access.

## Acceptance boundaries

Successful receipts accept only exposed local algorithm checks against this
snapshot. B1 is a missing authorized capability, not a failed comparison.
Fixtures are `independent_authored_exposed`, not hidden. Full product acceptance
and commercial value are not established. Inspect `receipt.json` and raw outputs
rather than inferring success from this file.

Missing capabilities are not code-repair targets. A concrete algorithm failure
must be handed back to task 1.e with the retained failing evidence, not fixed
during review.
