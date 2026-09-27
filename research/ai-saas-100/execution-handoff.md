# Current suite execution

Run from the repository root. Enforce the indicated foreground timeout through the calling tool. Execute one command at a time, never as an unattended job. These commands are selected, not executed by task 2.c.

First validate all current source, fixture, transformation and evidence hashes (20-second limit):

```sh
python3 -B research/ai-saas-100/tools/validate_execution_manifest.py
```

Do not proceed on failure. `execution-manifest.json` binds 20 individual executing Python components to exact content-addressed snapshots. Source changes require a reviewed new selection, not silently accepting a new hash. The interpreter and standard library are identified by runtime information, not archived.

## Evidence-producing commands

For case 001 control-plane regressions and case 002 repair-v2, use the repaired runner with the explicit current jobs. Each child has a 15-second timeout. Bound the overall command to 60 seconds:

```sh
python3 -B research/ai-saas-100/cases/001/tests/execute_pilots.py --jobs research/ai-saas-100/execution-jobs.json --timeout 15
```

This appends UUID-named receipts under the respective case directories. Case 001's 20 checks include blocked inference behavior, not rewriting. Case 002 uses the 54-case complete comparison bundle and separate evaluator. The manifest binds its adapter and runner as well as the implementation. Repaired-runner receipts alone do not bind every transitive component, so retain this manifest and integrity result alongside new receipts.

For case 003 persistence, demo, historical regression and repaired regression, use the existing append-only evidence executor (60-second overall limit, four children bounded to 10 seconds each):

```sh
python3 -B research/ai-saas-100/cases/003/tests/persistence-v1/execute.py
```

The executor snapshots all participating local code, runs active entrypoints and checks unchanged source bytes. It appends timestamped receipts and a summary under `cases/003/receipts/`. Temporary synthetic storage is allowed. No real CRM writes or natural-language interpretation occur. Its fixtures and runner-defined control sequences are component evaluation, not a complete separated model comparison bundle.

For case 033 scheduling (60-second overall limit, 20-second child limit):

```sh
python3 -B research/ai-saas-100/cases/033/tests/scheduler-v1/execute.py
```

This executes archived workflow, runner, checker and fixture bytes and creates a fresh `cases/033/receipts/scheduler-v1-<UTC>/` directory. The 87 cases and five checker self-tests are local exposed regression, not hidden or model evaluation.

## Optional direct checks

Each command below has a 20-second limit. They produce stdout rather than campaign execution receipts. The CRM demo uses and removes a temporary synthetic store.

```sh
python3 -B research/ai-saas-100/cases/002/tests/repair-v2/run.py
python3 -B research/ai-saas-100/cases/003/implementation/demo_persistence.py
python3 -B research/ai-saas-100/cases/033/tests/scheduler-v1/run.py
```

## Exclusions and handoff

Never rerun historical fixed-output `cases/002/tests/repair-v2/execute.py` or `validate.py`. Research materializers and dossier writers are also excluded from executable selections. Historical preservation manifests may contain intentionally superseded active hashes or case-relative metadata paths. They are not current execution selections.

B1 inference remains blocked for all four cases. Real rewriting for 001 and natural-language CRM interpretation for 003 remain blocked. Complete separated comparison inputs exist for 002 and 033 only. Original-product arms remain `not_observed`; lack of original access alone does not prohibit local B1/B2 evaluation or establish parity.

`execution-manifest-validation.json` records integrity checks for 83 files and six negative mutation checks. No suites were rerun during integration. Independent reviewers should use the selected retained receipts or perform the bounded commands above. No manifest entry confers product acceptance.
