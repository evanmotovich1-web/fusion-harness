# Runner repair validation

Run from the repository root:

```sh
python3 -B research/ai-saas-100/cases/001/tests/test_runner_failures.py
python3 -B research/ai-saas-100/cases/001/tests/execute_pilots.py
```

The first command runs real short synthetic children. It checks timeout partial-output preservation, launch failure, exit 7 with valid JSON, malformed JSON/UTF-8, malformed result schemas, failed/blocked assertions, preflight failure, and continuation to a successful child after each failure. Every attempt produces an append-only receipt and exact stdout/stderr bytes under this directory's `receipts/`. The suite has three IDs to prove expectations are not hardcoded to 20. None of these children perform model inference, network access, or product work.

A launch/preflight failure uses receipt status `blocked`, null process timestamps and null exit status because no process ran. Actual attempt timestamps are recorded separately. Launched children use `failed` for timeout, nonzero exit, malformed output or unsuccessful assertions. Timeouts kill and reap the direct child before continuing. Only trusted foreground commands that do not spawn detached descendants belong in a job manifest.

For explicit versioned suites, pass `execute_pilots.py --jobs PATH`. The JSON file contains an array of jobs with `case_id`, `command` (argv), `runner`, `suite`, `implementation`, and optional `input_bundle`. Artifact paths are campaign-relative. The caller must configure argv to consume the chosen suite and bundle. The runner validates returned test IDs against that suite and records file hashes. It cannot prove semantic equivalence between supplied and exercised inputs. Default legacy bundles remain labeled unsuitable for baseline comparisons because they contain evaluator material.

Receipts never assert product acceptance. Historical fixtures, prior execution receipts and the original pilot ledger remain unchanged. The archived pre-repair runner is identified by `../runner-source-archive.json`.
