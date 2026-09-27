# Case 033 local scheduling

`workflow.py` exposes `schedule(request, *, node_limit=50000)`. Supply the complete JSON-shaped request used in `tests/scheduler-v1/inputs.json`. The function returns a local schedule or a typed error. It does not open files, contact services, mutate its input, or write calendars.

Use `runpy.run_path('research/ai-saas-100/cases/033/implementation/workflow.py')['schedule']` to obtain the callable without installation. Output times are single-day UTC HH:MM strings. Read `tests/scheduler-v1/conventions.md` for exact priority, buffer, splitting, and search-limit semantics.

Run the exposed regression suite without writing evidence:

```text
python3 -I -B research/ai-saas-100/cases/033/tests/scheduler-v1/run.py
```

Create new immutable snapshots and bounded execution evidence:

```text
python3 -I -B research/ai-saas-100/cases/033/tests/scheduler-v1/execute.py
```

Each evidence invocation creates a unique receipt directory and never replaces earlier output. The child test process has a 20-second timeout. Its scheduler calls run under an audit hook that rejects file access, socket activity, subprocesses, and OS operations. This is an instrumented local test, not an operating-system sandbox.

The solver considers integer-minute start positions, task order, and split lengths. It admits tasks in priority/deadline/ID order but can rearrange already admitted tasks. It does not mistake one greedy placement failure for infeasibility. A search budget or depth limit returns an explicitly incomplete result retaining the last valid schedule, never a proof of infeasibility.

The test checker independently recomputes interval constraints and exact accounting without trusting `constraints_checked`. Additional tiny-calendar expectations were computed by a separate exhaustive minute-subset oracle before implementation. Deliberately invalid candidate outputs test the checker itself.

Historical research, specifications, and acceptance states are preserved. The new implementation and its receipts do not retroactively turn the research handoff into an acceptance record. Fixtures and retained evaluator examples are exposed. Generic-model comparison, hidden evaluation, live calendar integration, original-product behavior, and commercial acceptance remain unestablished. Coordinator integration should use the latest receipt directory and its source-bundle hashes, not infer status from historical research files.
