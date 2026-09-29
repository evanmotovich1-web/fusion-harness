# Discovery handoff: task 2.a

## Result and scope

The frozen pool contains 160 attempted leads, 159 distinct canonical identities after one merge, 125 eligible identities, and 34 exclusions. Selection contains 100 products, ten per category, plus 25 ordered alternates. This is identity discovery, not completed research, implementation, execution, or commercial assessment. All non-identity stages remain not_started. No product is accepted as a completed reproduction.

The seed is `ai-saas-100:KHPZw6:v1`. Candidate ranks use SHA-256 of UTF-8 `seed + newline + candidate_id`. Selection sorts by size tier E1/E2/E3, lowercase hash, then candidate ID. Each category supplies ten products. No quota transfer was needed. The complete selected order and alternate queues are in `../selection.json` and `../registry.json`.

## Actual discovery frame and deviations

The initial procedure proposed three sources per category and a target of twenty eligible identities per category. That frame was not achieved. Three public directory homepages were attempted. Futuretools returned HTTP 308, Product Hunt's bounded static capture did not expose useful listing text, and Uneed exposed current launch listings.

Ten apparently relevant listings among Uneed's first twenty displayed entries were inspected. Their linked public product sites were requested after removing referral parameters. Those leads and observed ranks are in `directory-leads.json`. Separately, `lead-seeds.tsv` contains 150 model-knowledge leads, fifteen per initial category. Model knowledge generated leads only. Each selected identity was subsequently checked against captured public first-party evidence. No identity is verified solely by a directory entry or the agent's memory.

Lead discovery was purposive and accessibility-constrained. The final sample is deterministic and size-prioritized within this convenience pool, not an unbiased random sample of all AI SaaS. It must not be presented as representative of the market or of companies with no users. Closed, blocked, or unverified leads remain in the frozen pool with reasons.

## Public access and evidence

Requests used credential-free Python urllib HTTPS GET, no paid APIs, accounts, purchases, or form submissions. All processes ran in foreground with tool-command timeouts of at most 60 seconds. Individual page captures were capped at 262,144 bytes and tagged if truncated. A separate 334,229-byte full Public Suffix List capture was retained for deterministic canonical grouping. No remote script was executed.

`records/` contains 185 dated request records, including failures, requested/final URLs, metadata, extracted text and links, truncation flags, and capture hashes. `captures/` contains successful bounded response captures. `evidence.json` indexes claim-supporting title, metadata, and workflow excerpts with locators, source type, publisher domain, retrieval timestamp, and capture references. Descriptions are vendor claims, not independently tested functionality. Some captured pages expose only metadata because their body requires JavaScript or appears beyond the capture limit.

`freeze.json` records the actual first/last capture-start timestamps, freeze timestamp, and hashes of inputs and source records. These timestamps do not establish continuous activity or 24 hours of work. Network latency in request records is not product latency.

## Identity, size, and uncertainty

Names, redirects, and advertised workflows were reviewed before eligibility. `review-decisions.json` preserves approvals, exclusions, current-brand overrides, category corrections, and limitations. Canonical host normalization uses lowercase IDNA and the pinned full Public Suffix List. Default deduplication permits one candidate per registrable domain. Product-specific paths, including WonsultingAI and Telex, remain in canonical URLs. Redirects establish observed landing identities, not a claim of legal acquisition.

CodiumAI and Qodo resolve to the same Qodo identity and are merged. Clockwise is excluded because its official page says its product would no longer be available from March 27, 2026. Taploop is excluded because its directory description of a marketing operator conflicts with the linked site's current subscription-marketplace presentation. Neither exclusion is a commercial verdict.

Only LinkBunny received E1, based on its current first-party about page explicitly describing its builder as a solo indie developer. The observation is dated by retrieval; the page supplies no publication date. This is a vendor self-description, not an independently audited headcount. The other 99 selected products have E2 (size unknown). Two named founders do not establish total staff. No numeric customer count was verified; all structured counts remain null/unknown. In particular, TaskMagic's static zero counters must not be read as evidence of zero users.

## Pilots and ordering

Pilot categories are chosen by descending selected E1 count, then category code. Take the first three represented categories, choose the smallest sort-key product in each, then assign the three IDs in category-code order. Remaining products use category round-robin with their within-category order preserved.

| ID | Product | Category | Important limitation |
|---|---|---|---|
| 001 | Smodin | C01 writing/editing | Homepage advertises AI writing, detection, humanization, and plagiarism tools. Core-workflow tests must specify which function is being reproduced. |
| 002 | LinkBunny | C02 marketing/SEO | Agent-assisted backlink marketplace/API, not demonstrated native model inference. Separate agent-side decisions from marketplace operations. Do not publish backlinks during tests. |
| 003 | Northlight | C03 sales | Advertises an AI GTM desktop product. Public identity verification does not prove execution access or authorize installing software, connecting accounts, or sending outreach. |

Diversity here means three workflow categories, not three input modalities. Pilots were selected before benchmark results. They were not chosen because implementation was known to be easy.

## Unresolved supplied name

The exact supplied string `norvjx ai` remains unresolved and is not in the sample. Four Google queries were attempted: `"norvjx ai"`, `"norvjx"`, `"norvjx" AI software`, and `"norvjx" pricing`. Static responses exposed only an access fallback, not usable search results. A Bing exact-name query returned unrelated cat-image results. These responses establish no matching product, and they do not prove nonexistence. Preserve the evidence and ask for an exact URL or inspect another authorized source. Do not silently identify it with a similarly named product.

## Replacement and continuation

The initial sample and frozen pool remain immutable. A registry owner may apply a documented revision using the next unused same-category alternate, then the global alternate order if necessary. Log event ID, old/new candidate IDs, slot ID, reason, evidence, UTC timestamps, alternate rank, and any category transfer. Preserve every old attempt. Do not replace a product because its commercial conclusion is unfavorable, reuse attempted candidates, or transfer prototype acceptance to a replacement.

Next tasks must consume `registry.json.products` and their `identity_evidence_ids`, resolved against `discovery/evidence.json`. `registry.json.alternates` are not selected cases. Do not count E2 as small, null adoption as zero, source-page request success as product execution, or identity discovery as finished research. No case directories were created in task 2.a.

Replay the frozen selection without web access or writes:

```text
python3 research/ai-saas-100/discovery/build_registry.py --check
```

The builder refuses to overwrite existing registry outputs without `--check`. Case research and later status updates will intentionally make full-registry replay differ. Preserve the original selection and use the frozen candidate pool for ordering verification after status changes. The validator/tooling task may adapt to these documented artifact fields without weakening campaign acceptance.
