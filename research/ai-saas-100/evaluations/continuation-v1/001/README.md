# Case 001 independent continuation evaluation

This evaluator completes delegated task 1.c (retained task 3.c) without changing the implementation or shared evaluator.

Run from the repository root with a caller timeout of 60 seconds:

```sh
python3 -I -B research/ai-saas-100/evaluations/continuation-v1/001/execute.py
```

Each invocation creates a new `runs/<UTC-uuid>/` directory exclusively. It verifies the task-2.a preserved source and capability hashes against `execution-manifest.json`, verifies the original evaluator freeze, and executes only the archived case-001 `run` function through the retained `adapters.call_workflow` interface. A foreground child has a 40-second timeout. No historical evidence writer is invoked.

The full schedule includes W-N1 through W-N8 and W-A1 through W-A6, plus two additional attempts each of W-N1/W-N4/W-N8. All 20 group attempts and 22 local invocations remain in the denominator. B1 retains the same planned denominator but is not executed because no authorized inference route is established.

Inputs, separate oracles, source, adapter, checker, executor, capability record and original freeze are copied and hash-bound before execution. Product calls receive only the complete request, never the oracle. Each attempt retains exact returned JSON values, raw stdout/stderr, observations, frozen-checker results, timing, unknown-cost classification and B1 non-execution. The parent saves raw child output and campaign-wide preservation manifests excluding only this case's evaluation directory.

Python audit hooks deny file, socket, subprocess, OS and ctypes operations during product calls. Three observer self-tests verify denial before file creation, socket creation and shell execution. These probes are separated from measured product effects. This is Python-level instrumentation of a reviewed local source, not OS containment. No endpoint probing or actual network calls are authorized.

A successful executor exit means evidence collection completed, not that rewriting works. Frozen invalid-input arms may pass locally. Central arms without genuine model output remain blocked. No fabricated `rewritten_text`, semantic review, or token-based semantic claim is added. Exposure remains `independent_authored_exposed`, not hidden. Missing B1 is not failed model performance. Product acceptance remains false.

Inspect each run's `receipt.json`, `stdout.json`, and `attempts/*/{observations,score,receipt}.json`. Any later execution is a new append-only run. New authorized inference requires a separate evaluation version rather than changing this runner's blocked-capability assumptions or overwriting these results.
