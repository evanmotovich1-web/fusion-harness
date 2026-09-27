# Frozen local marketplace behavior

Written before implementation. `fixtures.json` fixes 20 named scenarios. All are builder-visible regression tests, not held-out evaluation. This reproduces a local subset of the publicly described marketplace, not LinkBunny's production algorithm, agent, API, payment system, or network.

Use synthetic `https://source.invalid/blog`, `https://target.invalid/`, and integer UTC-like seconds. Source and target profile DR defaults are 30 and 35. The local configurable gap is 10, not a claim about the current vendor gap. Prefer smaller DR differences, breaking ties by synthetic profile ID. Reviewed profiles are eligible. One pending outgoing assignment is returned repeatedly. Same-domain and self-matches are excluded. Deadline is creation plus seven days. Reverse matching is excluded while pending or reported, released after expiry/rejection. A prior expired/rejected assignment may still be reported if it satisfies approval and scope checks. This behavior is independently specified from the public description, not copied vendor code.

| Scenario | Required local result |
|---|---|
| nearest | Candidate DR 35 beats candidate DR 39 for source 30. |
| exact_gap | DR 40 is eligible for source 30 and gap 10. |
| outside_gap | DR 41 is not eligible. |
| pending_review | Pending source receives no assignment and reports pending-review reason. |
| rejected_profile | Rejected source receives no assignment. |
| no_self | A one-profile pool produces no assignment. |
| same_assignment | Repeated check-in returns the same pending assignment. |
| approval_required | Reporting without explicit local owner approval raises an error. |
| report_local | Approved, in-scope nofollow HTML records local-only completion, never published/verified-live. |
| reject | Rejection releases the pair and records a reason. |
| reverse_pending | Target cannot receive the reverse assignment while the first is pending. |
| expire | At deadline, the old assignment expires and reverse matching becomes possible. |
| same_domain | Registration permits matching target and editable-area hosts. |
| deterministic_tie | Equal-distance candidates are ordered by ID. |
| cross_domain | Registration rejects mismatched target/editable-area hosts. |
| javascript_url | Non-HTTPS or credential-bearing URLs are rejected. |
| invalid_dr | Boolean, negative, or greater-than-100 DR is rejected. |
| bad_nofollow | Reporting a matching link without a nofollow rel token fails. |
| out_of_scope | Reporting /blog-evil outside /blog or a different host fails. |
| instruction_anchor | Instruction-like anchor text is escaped as inert HTML and never executed. |

No webpage is edited, HTTP call made, backlink published, account registered, or real API token used by this implementation. Editorial relevance is not inferred by the DR matcher. A generic-model comparison on identical inputs, an independent hidden suite, and review are still required before pilot acceptance. Unit successes do not satisfy those requirements.
