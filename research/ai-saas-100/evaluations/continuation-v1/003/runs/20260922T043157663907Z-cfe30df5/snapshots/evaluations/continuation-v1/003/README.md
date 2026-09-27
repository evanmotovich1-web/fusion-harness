# Independent CRM component evaluation

This review executes task 1.c's archived, hash-bound `workflow.py` and
`persistence.py`, not an edited working implementation. The source manifest is
selected through `cases/003/receipts/003-persistence-v1-20260922T033210014938Z-summary.json`.
All 11 archive members are verified before execution and retained in each new run.

## Run

From the repository root, with the outer command limited to 60 seconds:

```sh
python3 -B research/ai-saas-100/evaluations/continuation-v1/003/execute.py
```

The executor creates a unique `runs/<timestamp-id>/` directory, freezes exact
source/evaluator/input/oracle bytes before execution, captures stdout/stderr with
a 40-second child timeout, and appends `receipt.json`. It never replaces prior
receipts or modifies product implementations. The child loads the immutable source
snapshot and temporarily binds only its `STORAGE_ROOT` to disposable storage inside
that run directory. No business logic or source bytes are patched for normal tests.
All real store files are removed by the temporary-directory context after testing.

## Checks

`component-inputs.json` and `component-oracles.json` separate structured commands
from expected results. There are eight approved component scenarios and 13 control
scenarios. These are explicitly structured tests, not translations of natural-language
requests and not conversational normal-case wins. The run also executes the frozen
C-LOCAL-A2/A3/A6 evaluator groups and the three malformed C-A1 preview variants.
Expected total: 25 scored groups. Parameterized variants are retained in raw outputs.

Checks cover exact proposed changes, proposal contact digest and revision, approval
content hashes, unchanged preapproval domain records, denial, no approval, stale
proposals before/after approval, altered proposals/approvals, cross-store approval,
replay after fresh open, no-op consumption, unrelated contacts, and fresh readback.
Proposal/approval metadata is deliberately persisted before application. Therefore
'unchanged preapproval' means contacts and their revision, not byte-identical entire
storage. Rejected operations are checked for byte-identical serialized store content.

Atomic application is observed at the real `os.replace` boundary: domain changes,
revision, and approval consumption appear in the same new file. This is not a
power-loss or crash-durability proof. Three explicitly labeled fault-injection
scenarios additionally exercise replacement failure before commit, directory-fsync
failure after commit, and mismatching postcommit readback. Postcommit errors are
reconciled through a fresh real read and are never represented as guaranteed rollback.

Python audit hooks reject network/process activity and file access outside the
created temporary storage while product calls execute. Imports happen before the
hook is active, and integer file descriptors are not an OS sandbox. The suite uses
trusted, inspected source and does not claim isolation against arbitrary native code.

## Acceptance boundaries

Successful receipts accept only the tested structured synthetic persistence component.
Natural-language inference and B1 remain blocked by the retained capability assessment.
No model requests, messaging, real CRM access, calendar mutation, or purchases occur.
B3 remains not observed. The evaluator is `independent_authored_exposed`, not hidden.
Full product acceptance and commercial value are not established by these checks.
Inspect `receipt.json` and its raw output rather than inferring success from this file.

The executor also checks campaign files outside this review directory for preservation.
Missing capabilities are not code-repair targets. A concrete component failure must
be handed back to task 1.c with the retained failing evidence, not fixed during review.
