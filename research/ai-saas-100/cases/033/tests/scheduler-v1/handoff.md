# Case 033 implementation handoff

Task `1.e` implemented a genuine local scheduler. No existing research, dossier, specification, freeze, or handoff file was edited. Shared registry and campaign acceptance remain untouched.

F1. API: `implementation/workflow.py` exposes `schedule(request, *, node_limit=50000)`. Conventions and exposed test expectations were frozen before this implementation existed. Read `conventions.md`, `conventions-freeze.json`, and `freeze.json` in this directory.

F2. The solver can reconsider task ordering and placement, including an earliest-deadline-first dead end. Higher priority controls complete-task admission. It preserves immutable meetings, buffers, deadlines, exact minute accounting, and unsplittable intervals. Budget/depth exhaustion is distinct from proven infeasibility and retains the last valid schedule.

V1. Actual snapshot execution passed 87/87 request cases and 5/5 checker rejection self-tests. This includes all 20 original cases materialized into the new input bundle, 24 tiny-calendar cases checked against a separate exhaustive occupancy oracle, and 43 additional scheduling/validation/limit cases. All scheduler calls recorded zero prohibited file/network/subprocess/OS attempts. Constraint checking does not trust returned flags. Fixtures are exposed, not hidden.

V2. Source snapshot: `cases/033/source-history/scheduler-v1-6e16e7e43d6b5d1d/source-bundle.json`, relative to the campaign root. The archived test runner executes the archived workflow and archived fixtures, not mutable active files.

V3. Execution evidence: `cases/033/receipts/scheduler-v1-20260922T034444263126Z/`. `receipt.json` binds source, runner, checker, input, oracle, stdout, and stderr. `validation.json` records successful receipt validation, unchanged executed sources, and preserved historical artifact hashes.

H1. Independent evaluator should import the archived workflow, apply its own separate inputs and oracles, and retain the exposed status of the already shared evaluator report. Return interval times as HH:MM. Empty or invalid requests return structured `invalid_input`. A valid request with insufficient capacity returns explicit full-task unscheduled entries. `search_limited` is not a proof of infeasibility. Scope is one UTC day, up to 12 tasks and 128 meetings, with integer-minute resolution.

H2. Safe reruns: `python3 -I -B research/ai-saas-100/cases/033/tests/scheduler-v1/run.py` writes only stdout. `execute.py` in the same directory creates a new unique receipt directory and reuses or creates content-bound snapshots without overwriting old outputs. Every child execution is bounded to 20 seconds. Integration may reference this exact successful receipt rather than rerunning research materializers.

Product acceptance is not established. Generic-model comparison, an unexposed evaluation suite, original-product/calendar observations, and commercial evidence remain separate requirements. No inference, account access, live calendar write, purchase, or publication occurred.
