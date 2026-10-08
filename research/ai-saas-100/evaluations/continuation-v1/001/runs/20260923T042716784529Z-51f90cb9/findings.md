# Case 001 independent evaluation findings

Task 1.c completed evidence collection. Central rewriting and B1 remain blocked by the retained capability gap. No implementation rejection or repair target is established.

## F1. Full-denominator execution

Executed the archived case-001 control plane for all 14 frozen W-groups, including two extra attempts of W-N1/W-N4/W-N8: 20 group attempts and 22 actual local invocations. The foreground child exited 0 after 0.185 seconds under a 40-second timeout.

| Scope | Passed locally | Blocked | Failed | Planned |
|---|---:|---:|---:|---:|
| Group attempts | 5 | 15 | 0 | 20 |
| Local invocations | 7 | 15 | 0 | 22 |
| B1 group attempts | 0 | 20 not executed | 0 | 20 |
| B1 invocations | 0 | 22 not executed | 0 | 22 |

W-A1 through W-A5 passed only the frozen `reject_before_inference` assertions. W-A3 includes three strength-validation variants. The eight normal groups, their required repeats, and W-A6 returned `blocked_inference` and were scored blocked by the unchanged evaluator. No arm was dropped. Usable paired comparison coverage is 0/20 groups and 0/22 invocations. Missing B1 is not failed model performance.

## F2. Semantic preservation and acceptance

All returned outputs have `output: null` and `inference_executed: false`. No rewritten text, semantic review, or canned replacement was supplied. Named-role, quantity, negation, uncertainty, condition, quotation, factual-preservation and changed-phrasing claims remain untested because no generated text exists. Local input rejection does not establish semantic preservation. Weighted product scores were not fabricated.

Exposure remains `independent_authored_exposed`. No hidden evaluation, original-product parity, generic-model comparison or accepted product is established. `product_acceptance` is false. Cost remains unknown rather than a measured zero. No model request or billing evidence exists.

## F3. Source and capability bindings

Archived source selected by `execution-manifest.json`:
`source-archive/sha256/65fa7e23434d11c2457fcf49ba24485288e5d25867833e80fb9ffb9224760f74`.

The digest matches task 2.a's preserved implementation and the manifest's active/snapshot bindings. The working implementation was not imported or edited.

`capabilities-continuation.json` remains SHA-256
`7ed04bc66fbedda6a0cbc94ba1e8f3111516a92de0f53a83f2d4e95fddfd5bda`, recording `usable_authorized_route_established: false` and `inference_status: not_executed`. This verifies the retained assessment, not current availability of any unprobed endpoint.

All 129 artifacts in the retained evaluator freeze verified before and after execution. The new run froze 38 artifacts and copied their exact bytes, including source, complete fixtures, separate oracles, adapters, checker, capability evidence and execution code. Oracles reached only the checker, after implementation calls.

## F4. Effects and preservation

Product calls recorded zero prohibited effect attempts and unchanged inputs. Three separate observer self-tests denied file creation, socket creation and shell execution before those actions occurred. Python audit hooks are not OS containment.

Before/after preservation manifests match for all 1,520 campaign files outside `evaluations/continuation-v1/001/`. No network, account/calendar writes, paid external calls, git operations or historical evidence-writer execution occurred.

## F5. Independent receipt validation

`verification.stdout.json` records successful read-only validation of 170 receipt artifact hashes, 38 frozen originals/copies, every saved returned output, every attempt and variant denominator, and recomputed frozen-checker scores. `verification-receipt.json` binds the validator, actual command, raw stdout/stderr, exit 0 and 40-second timeout.

Key evidence in this run:
- `receipt.json` and `stdout.json` contain collection status and full results.
- `attempts/<W-group>-attempt-<n>/` retains verbatim returned JSON values, call stdout/stderr, observations, scores and per-group receipts.
- `freeze.json` and `snapshots/` preserve source and evaluator bindings.
- `preservation-before.json` and `preservation-after.json` establish unchanged outside files.

## H1. Exact handoff

Use this run for case-001 integration. Keep bounded evaluation completion separate from blocked semantic execution and false product acceptance. No repair target is nominated for missing inference.

Read-only revalidation from the repository root, caller timeout at most 60 seconds:

```sh
python3 -I -B research/ai-saas-100/evaluations/continuation-v1/001/validate.py 20260923T042716784529Z-51f90cb9
```

The source executor is `evaluations/continuation-v1/001/execute.py`. Running it creates a new unique receipt directory, never overwrites this run. Do not repeat it merely to reconfirm the unavailable capability. Resume semantic and matched-baseline evaluation only with new explicit authorized inference evidence, genuine outputs and independent semantic review in a new version.
