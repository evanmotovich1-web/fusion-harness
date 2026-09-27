<!-- Preserved upstream report from 1.c-drift.md. Historical scope statements refer to that task. -->

## Task 1.c report

### Evidence and scope

Read the current delegation plan and listed the repository and report directory. No files were changed, commands executed, or product benchmarks run.

The plan assigns protocol persistence to task 2.b, pilot implementation to 3.a, and independent pilot review to 4.a (`/tmp/fusion-harness-KHPZw6/collaborate/plan.json:60-85`, `/tmp/fusion-harness-KHPZw6/collaborate/plan.json:135-144`).

Everything below is a **proposed engineering protocol based on model knowledge**, not observed product performance. The supplied evidence does not establish any product’s identity, capabilities, users, or commercial value.

## Benchmark protocol

### P1. Freeze a product-specific workflow contract

Before implementation, record:

- Verified product ID and the sourced workflow being reproduced.
- Intended buyer task, input format, output format, and supported limits.
- Required factual knowledge, integrations, and external data.
- Explicit exclusions from the prototype.
- Success criteria, failure behavior, scoring rubric, and resource ceilings.

Select one central workflow, not an easy peripheral feature. Record whether the selected workflow represents the advertised value proposition adequately.

### P2. Use representative synthetic fixtures

These are illustrative task families, **not claims about sampled companies**. Select only those relevant to each verified workflow.

| Fixture code | Representative input | Expected checks |
|---|---|---|
| W1 | A 1,000-word meeting transcript with decisions, owners, deadlines, and unresolved discussion. | Capture supported actions, preserve uncertainty, invent no assignments. |
| W2 | Eight synthetic invoices spanning three layouts, with taxes, credits, and missing fields. | Match schema and values, distinguish missing from zero, validate arithmetic. |
| W3 | A support ticket plus six policy excerpts, including an outdated conflicting policy. | Ground the response, use applicable policy, escalate unsupported requests. |
| W4 | A product brief with target audience, required facts, and prohibited claims. | Follow constraints without inventing certifications, prices, or customer results. |
| W5 | A local CSV transformation request with duplicates, nulls, and malformed rows. | Produce independently calculated results without modifying source fixtures. |

Use lawful, non-sensitive assets for image, audio, and video workflows. Define modality-specific checks before generation. Do not substitute text-only tests for a product’s essential non-text capability.

### P3. Separate development, held-out, and adversarial cases

For each pilot, prepare **20 distinct cases**:

- **S1:** Six development cases available during implementation.
- **S2:** Eight held-out normal cases covering distinct variations.
- **S3:** Six held-out adversarial or failure cases.

Split by template or source family, not merely filename. Reserve near-duplicates together.

Choose adversarial cases appropriate to the workflow: missing fields, contradictory evidence, unsupported requests, malformed input, limit boundaries, and instruction-like text embedded in documents. Such text is test data, never executable authority.

The evaluator retains held-out answers and scoring details. Record fixture hashes and freeze time. If the builder has already seen the answers, label the suite “fixed regression,” not “held-out.”

After a failed held-out evaluation, preserve that result. Retesting after tuning requires a new held-out version for an unbiased claim.

### P4. Define comparable systems

- **B1, generic-model baseline:** A general instruction to perform the task, explicit output schema, and the same supplied source material. No product-specific examples or tuning.
- **B2, independent prototype:** The implemented workflow with its actual orchestration, validation, and integrations.
- **B3, original product:** Included only when authorized access permits observed execution.

For B1 versus B2, use the same base model and inference settings where possible. Otherwise label model differences as confounders.

**Direct comparisons require identical user requests, documents, assets, and externally supplied context.** Hash the canonical input bundle. Record unavoidable interface transformations. Do not silently truncate, improve, or augment one system’s input.

Distinguish two comparisons:

1. A controlled comparison holds data, model, and resource budget constant where possible.
2. An end-to-end product comparison permits native features but records differences in proprietary data, models, retrieval, and integrations.

A controlled comparison tests implementation advantage. An end-to-end comparison does not isolate its cause.

### P5. Score quality without hiding failures

Freeze task-specific checks before examining evaluation outputs.

| Dimension | Default weight | Measurement |
|---|---:|---|
| Q1. Task correctness | 50% | Field accuracy, factual support, executable assertions, or anchored expert judgments. |
| Q2. Required coverage | 20% | Fraction of required outputs correctly supplied. |
| Q3. Constraint compliance | 20% | Schema, formatting, policy, and prohibited-action checks. |
| Q4. Usability | 10% | Defined measures of readability or manual correction needed. |

Weights are pilot defaults, not universal scientific thresholds. Adjust them before testing when the workflow requires it.

Prefer deterministic validators. For subjective checks, use anchored 0–4 ratings with output order blinded. Any model judge must have its version and prompt recorded. Treat its rating as a proxy, not ground truth. Manually inspect critical flags and disputed ratings.

Designate critical failures in advance. Examples include fabricated supporting citations or acting on malicious document instructions. A high average cannot cancel a critical failure.

Report ordinary task success separately from correct failure handling. Appropriate rejection of malformed input is not successful completion of a normal task.

### P6. Record timing, cost, and configuration

Every attempted run needs an execution receipt containing:

- Case ID, fixture hash, system identity, implementation hash, and UTC timestamp.
- Exact invocation, environment and dependency versions.
- Provider, requested model ID, resolved version when exposed, prompts and hashes.
- Temperature, seed when supported, token limits, tools, retrieval settings, and concurrency.
- Raw output or error, validation results, retries, and human interventions.
- Monotonic end-to-end duration, optional first-token duration, cache and warm/cold status.
- Token usage, tool charges, price source and date, and cost classification.

Measure latency from submission through final usable output, including orchestration and retries. Record setup separately.

Use serial paired runs initially and alternate system order. Run the 14 held-out cases once per available system, then repeat three prespecified cases twice more when authorized resources permit. Report every attempt, not the best output.

Report median, range, sample size, timeout count, and individual timings. Do not present a small pilot’s p95 as a stable service-level estimate.

Keep cost categories distinct: billed amount, usage-derived estimate, allocated subscription cost, local-resource estimate, and unknown. Include failed attempts and retries. Report cost per attempted workflow and per successful normal workflow. Zero observed incremental charge is not proof of zero operating cost.

Each foreground validation invocation must finish within 60 seconds. Use only meaningful resumable stages for longer workflows. Otherwise mark the benchmark blocked by the execution limit rather than simplifying the task covertly.

### P7. Handle unavailable original-product access

Record B3 as `not_observed`, with the access restriction and date. Continue B1/B2 testing when possible.

Marketing descriptions, demos, and screenshots may support workflow selection. They are not competitor benchmark results.

Use conclusions such as:

> “The prototype scored X against baseline Y on this fixture set. Original-product performance was not observed.”

**No parity, superiority, or replacement claim is allowed without observed original-product results on identical inputs.** Even with those results, limit conclusions to the measured workflow and sample. Broad equivalence requires a separately designed equivalence study.

## Pilot acceptance checklist

These thresholds are proposed screening criteria, not measured results.

- **V1. Scope:** Three verified, diverse pilot products have central-workflow contracts, exclusions, and sourced rationale.
- **V2. Integrity:** Fixture versions and splits were frozen before implementation. Held-out exposure is disclosed.
- **V3. Execution:** Each prototype executes its contracted workflow. Mocks or canned model responses do not count.
- **V4. Quality:** Each prototype averages at least 80/100 on eight normal held-out cases, passes at least seven, handles at least five of six adversarial cases as specified, and exhibits zero critical failures.
- **V5. Baseline:** B1 receives the identical input bundle. At least 90% of planned paired runs have usable results. Failures and timeouts remain visible.
- **V6. Receipts:** All attempts have inspectable outputs, configuration, timing, and cost classification.
- **V7. Reproduction:** An independent reviewer can follow the setup and inspect evidence of a repeated run. Static review is not represented as re-execution.
- **V8. Claims:** Original-product access status is explicit. Missing comparisons and commercial evidence remain unknown.

Accept the evaluation method only after all three pilots satisfy applicable checks. A product-specific blocker does not prohibit research elsewhere, but an untested modality cannot inherit acceptance from another pilot.

Baseline superiority is **not** required to accept an honestly executed evaluation. A reproducible finding of no advantage is useful evidence, not a reason to alter the benchmark.

## Throughput and handoff

**T1. Measure work separately.** Record active research, implementation, evaluation, and review minutes per product, plus blocked waiting time and end-to-end elapsed time. Record setup overhead once.

**T2. Count accepted products.** Report attempted, blocked, executed, and accepted counts separately. Throughput is accepted products per observed foreground elapsed hour, alongside total agent-hours.

**T3. Forecast conservatively.** Use pilot ranges by workflow class and report the sample size of three. Include research and review, not just generation time. Do not extrapolate a text-only pilot to audio or integration-heavy products. Record the requested minimum 24 hours separately from actual elapsed time.

**Handoff:** GROK task 2.b should persist this protocol at `research/ai-saas-100/protocol.md` and encode receipt requirements in campaign-local validation. Task 3.a should freeze contracts and fixtures before building. Task 4.a should audit V1–V8 against actual artifacts.

Validation completed here was limited to checking the delegation plan and protocol coverage against task 1.c. No product acceptance or benchmark execution is claimed.
