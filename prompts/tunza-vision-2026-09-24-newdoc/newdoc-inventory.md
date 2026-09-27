# Newdoc inventory — inherit gate (task 2.a)

Dated 2026-09-24. Architect ruling. Consumes: `identity-verdict.md` (1.a, claim ids M/N/G/P/X), the 1.b product-tree truth table and QUERY-tunza-model-design.md:62-84 record, `source-verification.md` (1.c). Rules on every claim in the decoded PDF `07c5a914.decoded.txt`.

Categories: **(i)** already supported by `fact-sheet-urgent.md` S1-S12 · **(ii)** now citable, verified primary source · **(iii)** do-not-inherit · **(iv)** stays UNKNOWN.

## Lineage consequence

The PDF is the already-recorded original Jacob internal brief (SHA matches QUERY record), not the approved `Tunza-Vision-Jacob-Team` revision. Per the delegation, patches default to none **unless** the gate finds newly citable facts. It does: 1.c independently verified, verbatim and for the first time in this pipeline, a national mortality figure (WHO 355/100,000) and the MoH's own tie between referral fragmentation and maternal/child outcomes. Bounded patches are therefore authorized below.

## Verdict rows

### Mortality

| id | claim | verdict |
|---|---|---|
| M1/M3 | WHO 2025 Kenya report: maternal mortality estimated 355 deaths per 100,000 live births | **(ii)** Citable. VERIFIED verbatim, WHO Kenya Annual Report 2025, printed p. 60 (`source-verification.md` F3). Preserve "estimated". Country status quo, never a Tunza result. |
| M2 | Preventable causes — postpartum haemorrhage, hypertensive disorders — contribute substantially | **(ii)** Citable, same source sentence and the one following it. |
| M4 | "When clinical capacity is scarce, delays and poor routing carry real consequences" | **(iii)** as phrased. The verified sources support: MoH names referral fragmentation and ties strengthening it to maternal and child health outcomes (P1 verbatim). Use the MoH sentence, not this paraphrase. |
| M5 | No child-death-from-queue claim in this PDF | Confirmed absent. See U-ruling below. |

### Counts

| id | claim | verdict |
|---|---|---|
| N1/N2 | >107K CHPs supported with devices + medical kits | **(ii)** Citable as country context. VERIFIED: "supporting over 107,000 Community Health Promoters with monthly stipends, digital devices, and medical kits" (MoH node 2374, May 19 2026; `source-verification.md` F1). The fact-sheet-urgent condition — "until a later fact sheet cites a checked MoH page" — is now met. Never Tunza reach, deployment, or partnership. |
| N3 | 10,277 facilities connected to national systems | **(ii)** Citable. VERIFIED, MoH UHC-reforms page, Jan 28 2026 (`source-verification.md` P2). Supersedes jacob.md's "not checked" ban on this figure. Not used in this patch round — adds no stake. |
| N4 | 92% doctor shortfall against estimated need | **(iii) this round.** QUERY:78-80 records it as WHO p. 67, but 1.c did not verify it. Record the attribution; do not put it on a page until the WHO page is checked like the others. |
| N5 | Nine million households | **(iii)** NOT FOUND at the cited source (`source-verification.md` F2). Stays banned. jacob.md states it flat — see conflict note. |

### GPU / ML / model (all **(iii)** do-not-inherit as capability; proposed-architecture record only)

| id | ruling |
|---|---|
| G2-G5, G9-G11, G13 | JEV, TypeSafe, six-step pipeline, six-output taxonomy, Axolotl/QLoRA/NF4, CORE/RED/ABSTAIN/PARITY/GOLD evals, 4-day H100 campaign, orchestration: none exist in `/Users/evanmotovich/code/Tunza` (1.b truth table). QUERY:62-72 records them as PDF description, not code. If any page ever mentions them: "designed", "proposed", never shipped. This round: do not mention. |
| G5 specific | The six-output list is not the demo's four next steps. Do not collapse. |
| G6/G7/G8 | Moat-shaped competitive claims ("harder to reproduce", "not the moat" still uses the word). Banned family. |
| G12 | Dollar figures ($3.50/hr, $1,344, $500-$900). Never on any page, investor page especially. Internal GPU-cost theater. |
| G14/G15 | Compounding outcome loop, later distillation. Designed/future. Do not import; QAD stays out (standing ruling). |
| G16 | Named-recipient appeal ("What should feel urgent to Jacob…"). Cut in the approved revision. Never on public pages. |

### County / partner / clearance / policy

| id | claim | verdict |
|---|---|---|
| P1 | Kenya scaling community health, connecting facilities, formalizing referral policy, mandatory certification for digital health systems | **(ii)** for the referral-policy part: VERIFIED (MoH, Mar 6 2026, verbatim in `source-verification.md` P1), including the key sentence — the policy "aims to address fragmentation within Kenya's referral system by enhancing continuity of care and improving maternal and child health outcomes." Use as policy **development**, reference-not-endorsement. |
| P2 | Policy identifies fragmentation; continuity, interoperability, accountability | **(ii)** same source, verbatim. |
| P3 | 12-24 month window ("not an official deadline") | **(iii)** Inference, removed in the approved revision. Do not inherit. |
| P4 | DHA Certification footer + portal URI | **(iii)** as anything but a reference link. Portal/process, never Tunza clearance. |
| P5 | No named county, no signed NGO, no clinician circle, no "we have access" | Confirmed absent in the PDF. Keep absent in pages. |
| P6 | Header disclaimer | Note only. Does not license G2-G14 as shipped. |

### Other

| id | ruling |
|---|---|
| X1-X3 | Positioning/intent sentences. Not facts. Do not inherit. |
| X4 | The PDF is silent on demo limits (no localStorage, fake facilities, not-clinically-validated). Silence is not validation. Our pages keep their honest-limits blocks. |

## Boundary rulings

**B1 — the death sentence.** "The child who waits can die before anyone sees them" (queue-caused death) **stays UNKNOWN** (U1 unchanged; no checked source ties the eCHIS queue to a death). What changed: a citable status-quo mortality form now exists. Allowed shape, the only one:

> The WHO Kenya 2025 report puts maternal mortality at an estimated 355 deaths per 100,000 live births, from preventable causes including postpartum haemorrhage and hypertensive disorders. Kenya's Ministry of Health names a fragmented referral system and says strengthening it aims at maternal and child health outcomes.

Rules: deaths are the country's, tied by MoH's own words to referral fragmentation — never "people die without Tunza", never a Tunza result, never a market-size claim. "Estimated" and the source names travel with the numbers.

**B2 — jacob.md conflicts (report both, do not edit jacob.md).** jacob.md:7 states nine million households flat — unsupported (F2). jacob.md:9 states ~16 mothers a day — unsupported (F4). jacob.md:15 bans 10,277 as "not checked" — now superseded by verification (P2). jacob.md stays internal and unedited; Evan should know it carries two unsupported figures before he speaks from it.

**B3 — QUERY internal conflict** (1.b): line 66 calls 10,277/92% unchecked; lines 78-80 mark them sourced. Resolution: 10,277 now independently verified — citable. 92% recorded-but-unverified this run — stays off pages.

## Page-patch decision (for 3.a / 3.b / 3.c)

Authorized patches, exact text. Everything else in each file stays byte-identical. After patching, re-run the forbidden scan; honest-limits blocks, investor line one, blank term fields, P1-P3, Q1-Q4 must survive.

**friend.md (3.a)** — insert one new paragraph after the "Tunza has to exist… does not order that queue." paragraph (before "The ambition is to follow…"), add source `[8]`:

> People already die inside this system's gaps. The WHO Kenya 2025 report puts maternal mortality at an estimated 355 deaths per 100,000 live births, from preventable causes. Kenya's Ministry of Health names a fragmented referral system and says strengthening it aims at maternal and child health outcomes. Those are the country's numbers. They are not Tunza's results, and they are not claims about the demo. [8]

Sources addition: `[8] fact-sheet-newdoc.md S13-S14 (WHO Kenya Annual Report 2025, printed p. 60; MoH referral-policy page, Mar 2026).`

**general.md (3.b)** — replace the paragraph "Whether that wait kills a child is unknown. No source here documents that death. The documented harm is the failed handoff, not a count of lives." with:

> Whether that wait kills a child is unknown; no checked source documents that death. What is documented is the country's toll: the WHO Kenya 2025 report puts maternal mortality at an estimated 355 deaths per 100,000 live births, from preventable causes, and Kenya's Ministry of Health ties a fragmented referral system to maternal and child health outcomes in the referral policy it is developing. Those are the country's numbers, not Tunza's results.

And in the following policy paragraph, after "continuity, interoperability, and accountability.", insert: `The Ministry ties that work to maternal and child health outcomes.` Keep the reference-only link line unchanged. No other additions (page must stay one rendered page).

**investor-unsent.md (3.c)** — replace the paragraph "Whether that wait kills a child is unknown. No source here documents that death. This page has no mortality count and no lives-saved number. [4]" with:

> Whether that wait kills a child is unknown; no checked source documents that death. What is documented is the country's toll: WHO Kenya 2025, printed page 60, estimates 355 maternal deaths per 100,000 live births, from preventable causes including postpartum haemorrhage and hypertensive disorders. Kenya's Ministry of Health names referral fragmentation and ties its developing referral policy to maternal and child health outcomes. Those are the country's numbers. They are not Tunza's results, not a market-size claim, and this page still has no lives-saved number. [4][11][12]

Insert after the MoH policy paragraph's first sentence: `The country already supports more than 107,000 Community Health Promoters, per the Ministry of Health — and none of that scale decides which sick child moves first. [13]` Sources additions: `[11] fact-sheet-newdoc.md S13 (WHO Kenya Annual Report 2025, printed p. 60). [12] fact-sheet-newdoc.md S14 (MoH referral-policy page, Mar 2026). [13] fact-sheet-newdoc.md S15 (MoH node 2374, May 2026).`

**Not authorized:** 9M households, 16/day, 92%, 10,277 on pages this round, 12-24-month window, any G2-G16 content, any dollar figure, any DHA-clearance implication, any change to the ask sections, terms, P1-P3, Q1-Q4, or line one.

---
Escalation: interpretation disputes return to the architect. jacob.md edits are Evan's, not ours.
