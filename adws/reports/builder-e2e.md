# Builder end-to-end (stub)

Captured 2026-09-30 from the commands below. No keys, no network. Core fixes made during this run are listed at the end.

## 1. Toy complete — exit 0

```text
python3 adws/adw_workflow_builder.py --request adws/fixtures/requests/toy_complete.md --fixtures --stub-agents --db adws/data/adw.db --reports-dir adws/reports/e2e --run-id e2e-toy
```

Exit: `0`. Log: `adws/reports/e2e/runs/e2e-toy/run.log`.

```text
[20:49:23] CODE intake: workflow-build ask with a checkable outcome
[20:49:23] CODE intake → GATE route PASS
[20:49:23] AGENT workflow_scout attempt 1 (stub)
[20:49:23] AGENT workflow_scout → GATE workflow_scout PASS
[20:49:23] GATE  workflow_scout attempt 1 PASS
[20:49:23] AGENT spec_writer attempt 1 (stub)
[20:49:23] AGENT spec_writer → GATE spec_writer PASS
[20:49:23] GATE  spec_writer attempt 1 PASS
[20:49:23] AGENT reviewer attempt 1 (stub)
[20:49:23] AGENT reviewer → GATE reviewer PASS
[20:49:23] GATE  reviewer attempt 1 PASS
[20:49:23] CODE scaffold: 11 files
[20:49:23] CODE scaffold → GATE py_compile PASS
[20:49:23] AGENT builder attempt 1 (stub)
[20:49:23] AGENT builder → GATE builder PASS
[20:49:23] GATE  builder attempt 1 PASS
[20:49:23] AGENT builder → GATE diff_claims_real PASS
[20:49:23] CODE validate
[20:49:23] CODE validate → GATE fresh_verification PASS
[20:49:24] CODE validate_stamp
[20:49:24] CODE validate_stamp → GATE fresh_verification PASS
[20:49:24] CODE register: echo-check
[20:49:24] CODE register → GATE registry PASS
[20:49:24] DONE accepted exit=0
```

Every agent phase is followed by its GATE line: `workflow_scout`, `spec_writer`, `reviewer`, `builder`.

`agent_runs` for `e2e-toy` (model and provider buckets are `unknown`, not 0; duration was measured):

| agent | attempt | gate_passed | model | duration_ms | tool_counts | tool_errors | tokens |
| --- | --- | --- | --- | --- | --- | --- | --- |
| workflow_scout | 1 | 1 | unknown | 1 | read 1 | 0 | all unknown |
| spec_writer | 1 | 1 | unknown | 1 | read 1, write 1 | 0 | all unknown |
| reviewer | 1 | 1 | unknown | 1 | read 1, write 1 | 0 | all unknown |
| builder | 1 | 1 | unknown | 2 | read 1, write 1 | 0 | all unknown |

`workflow_builds`: `e2e-toy` accepted `echo-check`. Registry `adws/registry.json`: one entry, status `validated`, acceptance verified 1 / blocked 0.

Generated tree: `adws/built/echo-check/` (`adw_echo_check.py`, `gates.py`, `config.json`, prompts, fixtures, tests, README).

## 2. Generated workflow — exit 0

```text
python3 adws/built/echo-check/adw_echo_check.py --fixtures --stub-agents --db adws/reports/e2e/echo-check.db --reports-dir adws/reports/e2e/echo-check-run
```

Exit: `0`. Stdout (`adws/reports/e2e/echo-check.stdout.txt`):

```text
CODE intake: build
AGENT greeter → GATE greeting_nonempty PASS
GATE  greeting_nonempty attempt 1 PASS
```

## 3. Vague fixture — exit 3, no invented workflow

```text
python3 adws/adw_workflow_builder.py --request adws/fixtures/requests/toy_vague.md --fixtures --stub-agents --db adws/data/adw.db --reports-dir adws/reports/e2e --run-id e2e-vague
```

Exit: `3`. Stdout:

```text
[20:50:21] CODE intake: needs_human: request does not name a checkable outcome
[20:50:21] CODE intake → GATE route PASS
[20:50:21] REFUSED needs_human — unknowns marked <EVAN: fill>; no facts invented; no agent spend
[20:50:21] DONE needs_human exit=3
```

`agent_runs` for `e2e-vague`: 0. `adws/built/` gained no second workflow (only `echo-check` from the accepted run).

Spec written to the run dir, not to `adws/built/` (`adws/reports/e2e/runs/e2e-vague/spec.json`):

```json
{
  "schema_version": 1,
  "status": "needs_human",
  "request_verbatim": "Build me a workflow to help my business.\n",
  "invented": false,
  "id": "<EVAN: fill>",
  "name": "<EVAN: fill>",
  "outcome": "<EVAN: fill>",
  "gate": "<EVAN: fill>",
  "writes": "<EVAN: fill>",
  "requirements": [],
  "phases": [],
  "note": "Refused to invent a business workflow. Unknowns stay <EVAN: fill>."
}
```

The request is preserved. Id, name, outcome, gate, and write location are `<EVAN: fill>`. Requirements and phases are empty, not guessed.

## 4. Bad-first — FAIL, soft notice, retry PASS, exit 0

```text
python3 adws/adw_workflow_builder.py --request adws/fixtures/requests/toy_complete.md --fixtures --stub-agents --stub-bad-first --db adws/data/adw.db --reports-dir adws/reports/e2e --run-id e2e-badfirst
```

Exit: `0`. Excerpt of `adws/reports/e2e/runs/e2e-badfirst/run.log` (same shape on every seat):

```text
[20:49:28] AGENT spec_writer attempt 1 (stub)
[20:49:28] AGENT spec_writer → GATE spec_writer FAIL
[20:49:28] GATE  spec_writer attempt 1 FAIL:
        - spec_writer: fixture gate failed — schema missing requirements
[20:49:28] SOFT NOTICE: spec_writer: fixture gate failed — schema missing requirements
[20:49:28] AGENT spec_writer attempt 2 (stub)
[20:49:28] AGENT spec_writer → GATE spec_writer PASS
[20:49:28] GATE  spec_writer attempt 2 PASS
```

Scout, reviewer, and builder follow the same FAIL → `SOFT NOTICE:` (exact failure text) → attempt 2 PASS path. The run then validates and registers.

## Core fixes in this pass

- Vague intake now writes `spec.json` with `<EVAN: fill>` and does not invent a workflow. Still exit 3, still zero agent spend, still nothing new under `adws/built/`.
- A repeated `--run-id` no longer crashes on `runs.run_id` (`INSERT OR REPLACE`). Found when re-running `e2e-vague`.

`python3 adws/tests/test_builder_core.py`: 8/8 OK after those edits.
