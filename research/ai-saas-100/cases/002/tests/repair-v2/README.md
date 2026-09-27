# Case 002 repair v2

Run the offline, builder-visible exact-state suite:

```text
python3 -B research/ai-saas-100/cases/002/tests/repair-v2/run.py
```

## Inputs and evaluation

`comparison-inputs.json` contains the complete local contract, profiles, assignments, requests, arguments, and clocks for 54 cases. There is no scenario-name lookup or insertion of hidden profile defaults. `adapter.py` dispatches only on explicit operation names. The runner also renames every case ID and checks that execution output does not change.

`evaluator.json` contains descriptions and expected complete traces separately. Never send this file, or the historical `fixtures.json` containing answers, to a model baseline. Both B1 and B2 must receive the same complete input bundle. No model baseline was executed here. All fixtures are exposed fixed regression, not held-out tests.

`freeze.json` binds input, evaluator, materializer, and adapter bytes before the implementation repair. `execution-index.json` points to source-bound post-repair receipts. Each receipt binds the input bundle, oracle, implementation snapshot, runner, and interface transformation. `source-bundle.json` lists immutable copies of all executing source components.

The receipt executor captures subprocess errors and timeouts, but deliberately refuses to replace the fixed execution index. Use the plain runner for repeatable checks. A new evidence-producing execution needs a new versioned index, not overwriting retained evidence.

## Executed results and repairs

The archived original implementation passed 41 of 54 new cases and failed 13. After repair, all 54 new cases and all 20 unchanged historical regressions passed.

The repair rejects empty URL credentials and raw control characters, normalizes trailing-dot host comparisons, rejects ambiguous duplicate link attributes, validates review/profile/assignment identifiers before hash lookup or state mutation, and avoids overwriting restored assignment IDs.

Coverage includes distinct same-host profiles, approved/unapproved source and target exclusions, exact DR boundaries, deterministic ties, idempotent pending assignments, reverse-pair exclusions, expiry at the deadline, rejection, owner approval, cross-host/path reporting, nofollow enforcement, and complete before/after state.

The original specified late-report policy is unchanged: expired or rejected assignments may still be reported locally if approval, scope, and link checks pass. This is a synthetic policy, not a claim about the real marketplace. Editorial judgment, live verification, persistence, real outreach, and production behavior remain outside this subset.

## History and limitations

`source-history/pre-repair-287e153d1e4f/manifest.json` maps all 25 original case artifacts to exact archived bytes. Original fixtures, test runners, source captures, and receipts remain unchanged. The active dossier now points to current repair receipts. Historical receipt source paths resolve through that archive, not through the modified active workflow.

One repair receipt-executor attempt failed after saving subprocess output because its source-integrity assertion indexed a Path object. The old executor, raw outputs, and failure note are retained. Successful evidence is in the subsequent execution index.

These results repair local correctness and comparison-input integrity only. They do not establish generic-model comparison, independent hidden evaluation, original-product parity, marketplace value, or pilot acceptance. The shared registry and campaign acceptance were not changed.
