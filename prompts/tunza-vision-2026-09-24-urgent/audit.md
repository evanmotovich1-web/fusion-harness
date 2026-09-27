# Audit — urgent Tunza pages (task 4.a)

Dated 2026-09-24. Auditor: glm (wrote WRITING-CONTRACT.md; wrote none of the three pages). Audited against `WRITING-CONTRACT.md` and `fact-sheet-urgent.md` (stakes bucket S1-S12, boundary U1-U3). No page required rewrite. One deviation from the contract's stake lock was adjudicated and accepted; reasoning below.

## Method

Read all three pages in full. Two scans per the delegation: forbidden-list scan (case-insensitive regex over both halves of the contract's forbidden list) and urgency-honesty scan. Then structural checks, citation-resolution checks against both fact sheets, and originals verification (file listing plus SHA-256 of the Downloads PDFs against task 1.a's recorded values). All commands bounded, no background processes.

## Scan 1 — forbidden list

Patterns: trained model, owned weights, Anthropic, signed NGO, saves/saved lives, moat, the only gap, 500 billion/500B, 100k/100,000, 107,000, 9M/9 million, Solomon, Renaissance, Two Sigma, Jane Street, HRT, certified/clearance, "people die without".

Hits: 2, both compliant.

- `investor-unsent.md:39` — "This proposal is not funding a trained model or a national rollout." Negation, carried from the 2026-09-23 investor page's own approved wording. Pass.
- `investor-unsent.md:72` — footer guard: DHA portal "is not cited here as clearance... not a Tunza approval." Guard note, not a clearance claim. Pass.

Zero violations across all three pages. "Not clinically validated" appears once per page as the required disclaimer, not as a violation.

## Scan 2 — urgency and honesty

| check | friend | general | investor |
|---|---|---|---|
| eCHIS queue stake in opening | word 20 | word 15 | word 26 |
| "has to exist" in opening | word 60 | word 41 | word 52 |
| Every hot sentence's subject is the status quo | yes | yes | yes |
| Tunza subject of a safety/speed/life result | none | none | none |
| Honest-limits block, once | yes (para [6]) | yes ("What it is not") | yes (para [8]) |
| "designed / not built" wording | yes ("ambition is to follow") | yes ("designed. It is not built.") | yes ("ordering is designed. It is not built.") |
| Investor line one verbatim | n/a | n/a | yes |
| Five term fields blank | n/a | n/a | yes (5 empty headers) |
| Three proposals intact (P1-P3) | n/a | n/a | yes |
| Four questions open (Q1-Q4) | five open questions (allowed for friend) | n/a | yes |
| MoH/DHA links labeled reference, not endorsement | no link | yes | yes |
| Word count / length rule | 425 | 431 (one page) | 620 (max two) |

Zero violations.

## Citation resolution

Every bracket/source reference in the pages was resolved to the cited range:

- `fact-sheet-urgent.md:11-17` = S1-S7 (queue unordered, six failure modes). Matches friend [2], investor [2] usage.
- 2026-09-23 fact sheet: 22-25 (roles, no-grant household), 27-32 (gate, bilingual copy, text, voice), 31-35/36-41 (not-clinically-validated rules, four decisions, outcomes), 57-58 (follow-a-referral design), 72-74 (eCHIS origin line, two-product boundary), 75 (check-buys, no trained model, no rollout), 81-85 (open questions). All resolve to matching content.
- README.md:51-56 six failures and QUERY-tunza-model-design.md:28 eCHIS gap confirmed at cited lines via the fact sheets.

No dangling citations.

## Adjudicated deviation — the death sentence

The contract's stake lock included "The child who waits can die before anyone sees them." All three writers replaced it with the UNKNOWN boundary ("Whether that wait kills a child is unknown") and disclosed the choice in their handoffs.

Ruling: accepted, not a violation. Authority chain for facts runs sources > fact sheet > contract. `fact-sheet-urgent.md` U1-U3 shows the allowed sources document the unordered queue, the six failure modes, delay, escalation, and false reassurance — but no source on disk documents a death caused by that queue, and the Kenya brief contains no death claim. The standing rule from the 2026-09-23 contract ("if a source and this brief disagree about a fact, the source wins and the page stays quiet") governs; the writers stayed quiet and marked it UNKNOWN. The contract's mandatory fourth lock sentence ("the demo does not do this yet") is present in all three pages.

Restoration path, for the record: to put "can die" back on the pages, add a permitted primary source documenting the mortality relationship to the stakes bucket first. Then the sentence is citable and no contract change is needed.

Non-blocking note for 6.a, not a repair: the explicit "No source here documents that death" sentences in general and investor leak audit methodology into reader-facing copy. Honest, compliant, and stated once per page — left in place because the audit mandate is violations, not style. If Evan wants the death sentence restored, that is an evidence task, not an editing task.

## Originals verification

- `prompts/tunza-vision-2026-09-23/` four files: mtimes 2026-09-24 01:43-01:47, unchanged since creation.
- `tunza-pitches/` HTML: mtime 12:57, unchanged.
- Downloads PDFs, SHA-256 matches task 1.a exactly: e16739b3 brief `d8e3e772…`, Tunza.pdf `5ce717e7…`, Tunza_Complete_Guide.pdf `ca91a2e1…`.
- `git status --porcelain`: zero tracked modifications; only untracked paths. Nothing committed.

## Contract section 6 checklist

- [x] Stake and "has to exist" within first 80-120 words — all three pages.
- [x] No page says or implies saved/will-save a life, certification, signed NGO or county, trained model, moat.
- [x] Forbidden scan zero matches, including 107,000 / 100k / 9M / 500B / Solomon / shop names.
- [x] Hot sentences subject = status quo; Tunza subject of intent only.
- [x] Honest-limits block once per page: not a doctor, not a diagnosis, not clinically validated, cases on-device, demo facilities fake.
- [x] Investor line one verbatim; five fields empty; P1-P3 intact; Q1-Q4 open.
- [x] Length: general one page; friend and investor within two.
- [x] Originals unchanged (see above).
- [x] MoH/DHA links labeled reference only.
- [x] No unsourced number anywhere in the pages.

## Verdict

Accept. All three pages pass both scans, all citations resolve, originals are untouched. No page rewritten. The stake-lock deviation is adjudicated accepted with the restoration path documented above.

Handoff to 5.a (grok): render the three pages exactly as written; do not "restore" the death sentence at render time — that change requires new evidence in the stakes bucket, not renderer discretion. Handoff to 5.b (terra): verify the honest-limits block and the UNKNOWN death boundary survive rendering.

---
Governed by task 4.a of the delegation plan. Escalate interpretation disputes to the architect before inventing.
