# Campaign-local validation

Uses Python 3.9+ standard library only. Run from the repository root. No network calls, subprocess execution, provider calls, or automatic writes occur in either tool.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s research/ai-saas-100/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 research/ai-saas-100/tools/validate.py registry research/ai-saas-100/registry.json --evidence research/ai-saas-100/discovery/evidence.json
PYTHONDONTWRITEBYTECODE=1 python3 research/ai-saas-100/tools/receipt.py 001 run-001 --system B2
```

`receipt.py` prints an **unexecuted template**, not evidence of execution. Populate it only from an actual authorized attempt. Do not fill unknown costs with zero. The formatter does not grant inference or spending authorization. Commands and outputs must be redacted before storing secrets or private data.

`validate.py KIND PATH` accepts `registry`, `evidence`, `dossier`, or `receipt`. Optional `--root` defaults to the campaign directory. Repeat `--evidence PATH` to supply the discovery and case-local source indexes. Exit status is 0 for structural validity, 1 for invalid input. No output file is written. JSON success is not independent review or product acceptance.

## Serialized conventions

The preserved `contract.md` and `protocol.md` are authoritative requirements. Python `FIELDS`, `STAGES`, and `TOPICS` in `validate.py` define the minimal JSON field names for dossiers. All listed section keys are required even for incomplete cases. Unavailable scalar fields may be null in incomplete records. Research topics use `{ "claim_ids": [], "value": null, "unknown_reason": "Specific missing evidence" }`. Stage advancement requires the additional checks in the validator and the full contract review.

`record_status` supports `unknown`, `blocked`, `researched`, `implemented`, and `tested`. The last three require their corresponding stage to pass. `unknown` is a knowledge label, never a passing stage. Six required `stage_statuses` use `not_started`, `in_progress`, `passed`, `failed`, or `blocked`. No required stage can be `not_applicable`. Passing milestones must have passed prerequisites.

Claims use `claim_id`, `statement`, `classification`, `evidence_ids`, `scope`, `uncertainty`, and `conflicting_claim_ids`. Estimates additionally require `assumptions` and `unit`. Preserve applicable dates inside `scope`. Unknown research needs a reason. Review still checks that the unknown was investigated rather than simply omitted.

Evidence indexes use `{ "schema_version": 1, "sources": [...] }`, matching the discovery index. Failed retrievals and captures without excerpts can remain in the index, but cannot support factual claims. `--evidence` validates capture hashes before resolving references. Referential validity alone does not prove that a quotation supports a claim.

Every artifact reference uses `{ "path": "campaign-relative/path", "sha256": "64 lowercase hex characters" }`. Absolute paths and paths escaping the campaign root, including escaping symlinks, are rejected. Supply file paths, not directories. For multi-file implementations or fixture suites, use a fixed bundle and review its complete contents. The validator hashes the referenced file only, not arbitrary files mentioned inside a manifest. The receipt `fixtures` hash must match the dossier's frozen test-specification bundle hash. Input bundles are hashed separately for baseline comparability. Changes require new receipts and renewed review, never overwriting historical evidence.

Receipt status means invocation status, not product success. An exit-zero invocation can contain failing tests. Actual attempts use `completed` or `failed`; unexecuted templates use `not_started`, and access-blocked pre-execution records use `blocked`. A launched attempt that times out belongs under `failed` with the timeout and error recorded. Every `test_results` entry needs `test_id` and `outcome` (`passed`, `failed`, `blocked`). `execution_kind` is `real`, `mock`, `stub`, or `unknown`. Mock unit tests are valid receipts but cannot establish passing product execution.

Populate `runtime`, `model`, `configuration`, `usage`, and error/retry fields with the detailed requirements in protocol P6. Include prompts, versions, settings, cache status, pricing sources, and human interventions where applicable. Unknown model identity requires an explicit reason. `inference_executed` reports actual execution, not whether the code could call a model.

Metrics use `value`, `unit`, `classification`, `category`, `assumptions`, and `unknown_reason`. Classification is `measured`, `estimated`, or `unknown`. Unknown requires null plus a reason. Estimates require assumptions. USD categories are `billed_amount` (measured), `usage_derived_estimate`, `allocated_subscription_cost`, `local_resource_estimate` (estimated), or `unknown`. Include billing/price provenance in the receipt. Measured latency uses unit `seconds` and category `latency`.

Review records use `reviewer`, `independent`, `accepted`, `unresolved_material_objections`, and an `artifact` reference. Verdict fields follow contract C6. Registry validation loads dossiers for products with post-identity passing stages, cross-checks stage declarations, and recomputes accepted counts. Registry-only discovery records do not count as accepted products.

Optional duration claims require `active_intervals`, `observed_active_campaign_seconds`, `duration_fulfilled`, and `request_complete`. Each interval has UTC `started_at`, `ended_at`, and an `evidence` artifact reference. Overlapping intervals are unioned, not summed. Review must verify those artifacts establish actual activity. Two timestamps alone do not prove sustained work.

## Deliberate limits

This is a structural checker, not a replacement for independent review. It does not verify source truth, semantic claim support, real inference from an asserted flag, complete test coverage or pilot quality thresholds, hidden-test secrecy, commercial conclusions, or whether activity artifacts establish continuous work. It cannot prove append-only history from one filesystem snapshot. Review must preserve transition and replacement history and invalidate stale workflow/source changes. Exact-domain deduplication does not detect rebrands or multiple domains owned by one product.

The current minimal evaluation check requires an executed B1 baseline. Any protocol-permitted alternative baseline needs explicit reviewed schema support before claiming acceptance. Do not bypass validation or weaken the contract to fit a case. All unit-test products and executions are synthetic and do not count toward campaign results.
