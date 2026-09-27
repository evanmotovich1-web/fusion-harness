# Synthetic CRM persistence v1

Run the complete disposable local example from the repository root:

```sh
python3 -B research/ai-saas-100/cases/003/implementation/demo_persistence.py
```

Run source-bound component tests and append execution receipts:

```sh
python3 -B research/ai-saas-100/cases/003/tests/persistence-v1/execute.py
```

Uses Python 3.9+ standard library and POSIX `flock` (tested on macOS). No package installation, network access, external accounts, messaging, or real CRM writes. The original `workflow.py` preview API is unchanged. `persistence.py` is a separate structured-command component, not natural-language interpretation.

## API

Import `SyntheticStore` from the implementation directory:

1. `SyntheticStore(name).initialize(contacts)` creates a synthetic store once. Names contain only ASCII letters, digits, underscores, and hyphens. Storage is fixed beneath `cases/003/synthetic-storage/`.
2. `propose({"action":"update","patch":{"id":"c1","status":"qualified"}})` or `propose({"action":"dedupe"})` derives changes from current persisted contacts. Caller-supplied contacts and unrecognized request fields are rejected.
3. Inspect the returned proposal's exact `before`, `after`, `changes`, source revision, and source contact digest. Proposal creation persists pending metadata but does not change contacts or revision.
4. `decide(proposal, approved=True)` records approval of that exact proposal and returns the approval record. `False` permanently denies that proposal. Other decision types are rejected.
5. `apply(proposal, approval)` accepts only the stored, approved, unchanged proposal at the original revision and contact digest. It atomically commits contacts, the next revision, and consumption of approval in one JSON file replacement, then reopens that file to verify readback.
6. `SyntheticStore(name).read()` performs a fresh read. It returns store ID, revision, and contacts, not the pending-proposal metadata.

All methods return detached JSON-compatible values. Invalid requests raise `ValueError`. Store I/O failures raise `OSError`. The CLI converts these to structured JSON with exit code 2:

```sh
python3 -B research/ai-saas-100/cases/003/implementation/persistence.py --store example read
```

CLI operations `init`, `propose`, `decide`, and `apply` accept JSON on stdin. `init` takes `{"contacts":[...]}`, `propose` takes a structured action, `decide` takes `{"proposal":...,"approved":true}`, and `apply` takes `{"proposal":...,"approval":...}`. The demo supplies a complete working sequence without retaining a store.

## Defined behavior and limits

- Deduplication retains the first contact in each normalized-email group unchanged. It deletes later duplicates without merging their fields.
- A no-op requires approval, leaves contacts byte-equivalent under canonical JSON, increments the revision once, and consumes approval. Replay is rejected even after reopening the store.
- Stale proposals never overwrite intervening changes. Lock contention returns `store_busy` rather than waiting indefinitely. Cooperative readers/writers use the same store lock.
- Denied, unapproved, altered, stale, and replayed operations leave the current persisted state unchanged. Approval is an explicit local API operation, not authenticated multi-user authorization. Local operators and storage are trusted. Direct filesystem access can bypass this prototype's API and is outside its security claim.
- A storage failure or failed post-commit readback can occur after the atomic replacement. The CLI reports `storage_error_reconcile`, not a guaranteed rollback. Fresh-read the store before deciding whether to retry. An already consumed approval cannot apply twice.
- Tests use real temporary case-local files. Two tests explicitly inject replacement/readback faults. Audit checks detect common Python network/process attempts, not OS-level containment.
- No inference, generic-model baseline, original-product comparison, or independent hidden evaluation is included. Natural-language workflow and product acceptance remain unavailable/unestablished.
