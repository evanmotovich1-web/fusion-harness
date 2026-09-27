# Case 002 recovery verification

Task: `1.b`.

F1. Fresh bounded executions passed 54 repair-v2 and 20 historical cases. The implementation was not changed.

F2. Archive, source, interface, comparison-input, evaluator, and receipt hashes were recomputed. All pre-existing case files and both historical malformed task reports were preserved. Their exact copies are retained here.

F3. Evidence: `validation.json`, `source-bundle.json`, `preservation-before.json`, `repair-v2.receipt.json`, `historical.receipt.json`, and both raw stdout/stderr pairs in this directory.

H1. Integration should use these fresh receipts and the unchanged repair-v2 comparison input and separate evaluator. Repeat verification with `python3 -I -B research/ai-saas-100/cases/002/tests/recovery-v1/run.py`, which creates a fresh run directory. Do not rerun repair-v2/execute.py or repair-v2/validate.py in place.

Product acceptance: false. No model comparison, hidden evaluation, live marketplace access, or publication was performed.

FH_TASK_OUTCOME: {"schema_version":1,"status":"completed","summary":"Recovered retained case 002 evidence, verified hashes, and reran 54 repair and 20 historical regressions successfully without changing existing work. Model comparison and product acceptance remain unestablished."}
