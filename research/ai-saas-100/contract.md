<!-- Preserved upstream report from 1.b-glm.md. Historical scope statements refer to that task. -->

## C1. Scope and inspected state

This report defines campaign contract version 1 for task `1.b`. No files were modified.

At inspection, `/tmp/fusion-harness-KHPZw6/collaborate/reports/` was empty and `research/ai-saas-100/` did not exist. No product research, implementation, or execution is claimed.

The deliverable is 100 independently implemented **core-workflow prototypes**, not 100 production-equivalent SaaS services. “Kill” means reject a business hypothesis through evidence, never interfere with a company.

## C2. Artifact contract

Use `research/ai-saas-100/` as the campaign root.

| Path | Required content |
|---|---|
| `registry.json` | Product identities, selection membership, per-stage statuses, case paths, replacement history. |
| `selection.json` | Candidate pool, eligibility rules, categories, sampling algorithm and seed, selected order, pilot-selection rationale. |
| `capabilities.json` | Observed tool availability, access restrictions, execution limits, spending authorization. |
| `cases/<id>/dossier.json` | Identity, claims, workflow specification, research findings, uncertainty, evidence references. |
| `cases/<id>/evidence.json` | Sources and supporting excerpts with provenance. |
| `cases/<id>/implementation/` | Independent source code and reproducible setup instructions. |
| `cases/<id>/tests/` | Versioned inputs, expected behavior, scoring rules, acceptance thresholds. |
| `cases/<id>/receipts/` | Actual execution records and output artifacts. |
| `cases/<id>/verdict.json` | Technical assessment, commercial assessment, recommendation, evidence, counterevidence. |
| `batches/<batch>.json` | Assigned IDs, attempts, outcomes, blockers, handoffs. |
| `completeness.json` | Mechanically derived completion counts and unmet requirements. |
| `report.md`, `handoff.md` | Comparative conclusions and exact remaining work. |

IDs are strings `001`–`100`. Alternate candidates have separate identifiers and do not count toward the target. Existing completed artifacts must be inspected and preserved before extension.

## C3. Required dossier and provenance fields

Every dossier has `schema_version: 1` and these sections:

| Section | Required fields |
|---|---|
| `identity` | `id`, `name`, `canonical_url`, `category`, `identity_status`, `identity_evidence_ids`, known aliases. |
| `selection` | Candidate identifier, selection position, eligibility evidence, pilot flag, replacement reference if applicable. |
| `workflow` | Target user, job performed, inputs, outputs, representative success criteria, included behavior, excluded behavior, external dependencies. |
| `research` | Pricing, buyer, alternatives, adoption, distribution, integrations, proprietary access, switching costs, operating economics. Each contains claim references or an explicit unknown. |
| `claims` | Claim ID, precise statement, classification, evidence IDs, applicable date/scope, uncertainty, conflicting claim IDs. |
| `tests` | Specification path, version/hash, fixation timestamp, predefined acceptance criteria, baseline specification. |
| `implementation` | Source path, source version/hash, setup instructions, implemented coverage, missing capabilities, dependency/license notes. |
| `assessment` | Stage statuses, receipt references, technical uncertainty, commercial uncertainty, verdict reference. |

Allowed claim classifications:

`vendor_claim`, `independent_report`, `direct_observation`, `estimate`, `inference`, `unknown`.

Each evidence record requires:

- `evidence_id`, source URL or local artifact path, publisher/author when known.
- `retrieved_at` as an actual UTC timestamp and `published_at` when available.
- Supporting excerpt or bounded observation, plus a section/page/line locator where applicable.
- Source type, access method, and scope limitations.
- Local capture reference and content hash when a capture exists.
- Access failure details when retrieval failed.

A citation must support the specific claim, not merely link to a homepage. An unavailable source does not establish the claim it was intended to support. Search snippets and directory entries may generate leads but cannot alone verify pricing, adoption, or feature performance.

Conflicting sources remain visible. Estimates include assumptions and units. Missing values use `null` with an `unknown_reason`, never fabricated zeroes.

Product identity requires a canonical product source or equivalent authoritative evidence linking the name to the domain. An unresolved name such as “norvjx ai” remains a lead, not a verified product.

## C4. Status transitions

Track stages independently:

`identity`, `research`, `implementation`, `execution`, `evaluation`, `review`.

Each stage uses:

`not_started`, `in_progress`, `passed`, `failed`, `blocked`, `not_applicable`.

Normal transitions are:

`not_started → in_progress → passed | failed | blocked`.

A failed or blocked stage may return to `in_progress` after a documented correction or access change. Maintain append-only transition history containing timestamp, actor, reason, and evidence references.

Rules:

- `unknown` describes knowledge, not successful execution.
- `not_applicable` is prohibited for the six required stages. It is allowed for optional subchecks with justification.
- Required inputs must be available before a dependent stage passes.
- Source, workflow, test, or implementation changes invalidate affected downstream acceptance. Historical receipts remain preserved.
- Test completion is not automatically test success.
- Technical failure does not automatically imply commercial rejection.
- An inaccessible original service makes original-product comparison unavailable. It does not justify a parity claim or automatically block an otherwise valid independent prototype evaluation.

Record blockers with `scope: product | campaign`, cause, affected stages, permitted next action, and evidence. Continue other accessible cases after product-specific blockers. Switching companies does not fix a campaign-wide lack of tools or authorization.

## C5. Execution and prototype acceptance

Every accepted prototype requires an independently implemented representative workflow, reproducible setup, product-specific tests, and actual execution.

Each execution receipt records:

- Run ID, case ID, actual start/end timestamps, command and working directory.
- Implementation and fixture versions/hashes, runtime/dependency versions.
- Model/provider/version when exposed, configuration, and explicit unknowns where unavailable.
- Input/output artifact references and hashes, exit status, test-level outcomes.
- Baseline identifier and equivalent comparison inputs.
- Quality scores under the predefined rubric, observed latency, usage, and cost.
- Whether metrics are measured, estimated, or unknown, with units and assumptions.
- Errors, retries, timeouts, missing capabilities, and redactions.

Never persist secrets or private customer data.

Tests must be fixed before implementation evaluation. Include representative successful inputs, invalid or failure inputs, and held-out cases where appropriate. Workflow-specific thresholds come from DRIFT’s protocol and the case specification, not post-result adjustment.

Real model inference is required where it is central to the workflow. Hardcoded responses, mocked dependencies, generic scaffolds, and screenshots do not establish reproduction. Mocks remain permitted for clearly labeled unit tests.

Compare against an actually executed generic-model baseline where relevant. If a baseline is technically unsuitable, document and review an appropriate non-product-specific alternative before evaluation. Unavailable baseline execution remains a blocker, not an assumed result.

A failing product-specific acceptance criterion leaves the prototype incomplete, even if its failure is commercially informative. Original-service feature parity requires direct authorized observations and equivalent inputs.

## C6. Commercial verdicts

Each `verdict.json` contains:

`recommendation`, `thesis`, `technical_assessment`, `commercial_assessment`, `supporting_claim_ids`, `counterevidence_claim_ids`, `uncertainties`, `next_falsification_test`, `reviewer`, `reviewed_at`.

Allowed recommendations:

| Recommendation | Meaning |
|---|---|
| `pursue` | Evidence supports a specific further investment or customer-validation test. State the buyer, advantage, and next decision. |
| `reject` | Evidence contradicts a defined build/investment thesis. State what failed and what evidence could reverse the decision. |
| `insufficient_evidence` | Available information cannot support either conclusion. State the missing evidence and next permitted test. |

Assess technical reproducibility separately from demand, willingness to pay, distribution, proprietary data access, integration depth, switching costs, reliability, and economics.

Easy replication is not proof of low business value. Unknown adoption is not zero users. Missing demand evidence is not worthlessness. Public pricing is not revenue. Vendor customer claims remain vendor claims unless independently corroborated.

No exact company valuation is required or inferred. A negative commercial verdict is not a campaign success criterion.

## C7. Completion and duration

A product is complete only when all six required stages pass:

1. **P1:** Identity is verified and deduplicated.
2. **P2:** Research addresses every required topic with supported findings or explicit, investigated unknowns.
3. **P3:** The representative workflow is independently implemented with reproducible setup.
4. **P4:** Real execution passes predefined product-specific acceptance criteria.
5. **P5:** Baseline evaluation and technical/commercial assessment are recorded.
6. **P6:** Independent review accepts the evidence and resolves material correctness objections.

An `insufficient_evidence` commercial verdict can satisfy evaluation if the research and working prototype meet their requirements. It cannot excuse missing implementation or execution.

Campaign fields:

```text
target_products = 100
accepted_products = count(unique selected products passing P1–P6)
deliverables_complete = accepted_products == 100
requested_min_duration_seconds = 86400
observed_wall_elapsed_seconds = measured value or null
observed_active_campaign_seconds = measured value or null
duration_fulfilled = verified active campaign time >= 86400
request_complete = deliverables_complete AND duration_fulfilled
```

Measure active campaign time as the union of recorded execution/research intervals. Do not sum overlapping agent intervals, count pauses as activity, or infer continuous work from two timestamps. Unknown timing cannot satisfy the duration requirement.

Reaching 24 hours does not complete unfinished products. Completing products early does not establish that 24 hours occurred. Do not idle, launch background workers, or exceed authorization merely to satisfy duration.

Replacements require logged reasons and verified alternate identities. Preserve excluded cases and their evidence. Never transfer a replaced product’s acceptance to its replacement.

A bounded batch task may finish when every assigned ID has an accurate attempt/outcome record. Its report must separately state accepted, incomplete, blocked, and unattempted counts. **Completed batch reporting is not completed product delivery.**

## C8. Validation and handoff

This contract was checked for consistent required stages, explicit unknown handling, independent review, provenance, and separation of batch, product, campaign, and duration completion. No commands or product tests were executed.

For task `2.b`, GROK should persist this report’s contract in `research/ai-saas-100/contract.md` and implement bounded offline checks that:

- **V1:** Reject duplicate identities, malformed IDs, broken evidence references, and missing required fields.
- **V2:** Reject accepted cases with failed/blocked stages, mock-only execution, missing receipts, or unresolved material review objections.
- **V3:** Recompute counts from case records instead of trusting summary declarations.
- **V4:** Keep unknown metrics distinct from measured zeroes and estimates.
- **V5:** Reject duration claims unsupported by recorded intervals.
- **V6:** Preserve replacement history and invalidate acceptance after relevant artifact changes.

TERRA owns sampling details through task `1.d`. DRIFT owns benchmark details through task `1.c`. Their specifications must preserve these acceptance requirements. Authorized capabilities and budget remain determined by task `1.a`, not assumed by this contract.
