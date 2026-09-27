# Inventory verdict — Tunza PDFs vs Kenya Clinical Vision Brief

Dated 2026-09-24. Task 1.a. Original PDFs were not modified. SHA-256 values below were measured on the originals after decode.

Working folder: `/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-24-urgent/`
Decoded text: `/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-24-urgent/decoded/`

## F1 — Files decoded

| decoded file | source | bytes | sha256 | pages extracted | what it is |
|---|---|---|---|---|---|
| `e16739b3-33a4-4cf7-a7ed-cdcc8bb02fc1.decoded.txt` | `/Users/evanmotovich/Downloads/e16739b3-33a4-4cf7-a7ed-cdcc8bb02fc1.pdf` | 9127 | `d8e3e772d93b6624578fd891b1f9c6fcc985880fcad4ad911ccb5157196195d2` | 2 | **This request.** Title `Tunza - Kenya Clinical Vision Brief`. Author Tunza Labs. Created `D:20260924151959+00'00'`. ReportLab. |
| `Tunza.decoded.txt` | `/Users/evanmotovich/Downloads/Tunza.pdf` | 235030 | `5ce717e704d445329b6ec2d1860cf4fa8b506aa507336d49ef011fd95b9a2e34` | 16 | Product thesis. Title `Tunza The decision before the clinic`. Author Tunza. Created `D:20260910073513-04'00'`. ReportLab. |
| `scratch-2026-09-10-Tunza.decoded.txt` | scratch `…/scratch-2026-09-10-b9a7f4/Tunza.pdf` | 235030 | **identical** to Downloads/Tunza.pdf | 16 | Duplicate of Downloads/Tunza.pdf. Not a fourth document. |
| `Tunza-Brief.decoded.txt` | scratch `…/scratch-2026-09-17-d56432/Tunza-Brief.pdf` | 15956 | `7b96cd8cc32bf0f12082bcfa60a05bc1009ea1195ba4c31ed3cdf4f89532435a` | 3 | `Tunza Brief + ML Primer`. Author Evan Motovich. Created `D:20260916221230-04'00'`. ReportLab. |
| `Tunza_Complete_Guide.decoded.txt` | `/Users/evanmotovich/Downloads/Tunza_Complete_Guide.pdf` | 437025 | `ca91a2e186cf8fd20bbfc4edd1c95dc15477826ec4c295420845390ca877f943` | 21 | Google Docs export. Title `Tunza_Complete_Guide`. Producer `Skia/PDF m155`. Learning guide: “Tunza, AI training & GPUs”. Not a vision brief. Skia CID text is word-broken in the decode; content is still readable. |

`/Users/evanmotovich/tunza-pitches/` has **no PDFs**. It has four HTML files dated 2026-09-24 12:57: `friend.html`, `general.html`, `investor-unsent.html`, `index.html`. Those are the 2026-09-23 three-page set rendered as HTML, not PDF.

## F2 — Which three PDFs Evan means

Two sets exist. Do not collapse them.

**Set A — the three on-disk Tunza PDFs that predate the Kenya brief**

1. `Downloads/Tunza.pdf` (2026-09-10) — 16-page product thesis. Copies the README feature list (voice, image, vitals, outbreak signal, PWA, etc.).
2. scratch `Tunza-Brief.pdf` (2026-09-16) — 3-page brief + ML primer. Describes `medical-triage` (Anthropic prompt, Supabase, doctors, 100k CHPs, 9M households, moat).
3. `Downloads/Tunza_Complete_Guide.pdf` (2026-09-17) — 21-page GPU/ML learning guide from a 00:00–43:45 meeting. Not a pitch.

**Set B — the three pages “made early” in the 2026-09-23 vision run**

`prompts/tunza-vision-2026-09-23/{friend,general,investor-unsent}.md`, also as HTML under `tunza-pitches/`. Cooled on purpose. Not PDFs.

**Verdict:** Evan’s “three tunza pdf you made early” is Set B in intent (friend / general / investor) and Set A on disk if he means actual PDF files. The Kenya brief is a **fourth, later** document (2026-09-24 15:19 UTC). Compare the Kenya brief against Set B for voice, and against Set A only as prior PDF artifacts. Downstream writers should not treat Complete_Guide or the ML primer as the cooled pages.

The Kenya brief is cooler than Evan now wants. It never says a child dies, never says Tunza has to exist, and opens with “a new layer” / “uncertainty to the right next step,” not with an unordered queue.

## F3 — Kenya brief, line by line

Source: `decoded/e16739b3-33a4-4cf7-a7ed-cdcc8bb02fc1.decoded.txt`. Header chrome (`TUNZA`, running title, footer disclaimer, page number) repeats on both pages; listed once per page.

Link annotations (not body text):

- `https://www.health.go.ke/node/2374`
- `https://health.go.ke/kenya-moves-strengthen-patient-referral-system-through-new-national-policy` (two annots)
- `https://certification.dha.go.ke/`

### Page 1

1. TUNZA
2. CLINICAL VISION BRIEF | KENYA | SEPT 2026
3. Discussion draft - no clinical-performance claim or patient-data request; any patient-facing use requires validation and applicable approvals.
4. 1
5. A NEW LAYER FOR THE MOMENT BEFORE FORMAL CARE
6. From uncertainty to the right next step.
7. Tunza is being built around a simple clinical reality: for many people, the hardest part of care is not what happens inside a hospital - it is deciding what should happen before arrival, preserving the right context through the transition, and knowing whether the care path actually resolved.
8. Tunza is not intended to replace clinicians, hospitals, community health systems, or Kenya's national digital infrastructure. It is designed to strengthen decision quality and continuity around the transition into care.
9. WHY THIS MOMENT MATTERS
10. Kenya is not starting from zero. The country is rapidly strengthening community health, referral coordination, digital infrastructure and national interoperability. More than 107,000 Community Health Promoters are being supported with digital devices and medical kits; the Ministry of Health is developing a national referral policy focused on continuity, digital interoperability and accountability; and the Digital Health Agency now certifies digital health systems against security, functionality and information-exchange standards.
11. That creates a narrow strategic window: the rails are becoming more connected. The next question is whether those rails simply record care - or help each transition become safer, faster and more accountable.
12. 01 Earlier clarity — Help surface the next clinically appropriate action while uncertainty is still high - before travel, delay or escalation.
13. 02 Stronger continuity — Preserve the essential context as a person moves between household, community health and facility-based care.
14. 03 Measurable learning — Treat resolved care journeys as evidence: what worked, what did not, and where safety or coordination should improve.
15. THE BIGGER PICTURE
16. The ambition is not to create another destination app. It is to build a clinically disciplined layer that can work with the systems Kenya is already investing in - community health, facility systems, registries, referral pathways and health-information exchange - while remaining useful in the realities of intermittent connectivity, limited resources and uneven access.
17. If done correctly, Tunza becomes more valuable as the health system becomes more connected - not less.
18. Public context: Kenya MoH reports 107,000+ CHPs supported with digital devices and kits; its 2026 referral-policy process emphasizes continuity, digital interoperability and accountability; DHA certification evaluates digital health systems for functionality, security/privacy, reporting and interoperability. MoH - Community Health, May 2026 | MoH - Referral Policy, Mar 2026 | DHA Certification

### Page 2

19. WHAT EARLY CLINICAL PARTNERS CAN SHAPE
20. Clinical credibility before scale.
21. We believe the most valuable early collaborators are not endorsers. They are clinicians willing to pressure-test the assumptions before the product hardens - especially where textbook logic and real Kenyan practice diverge.
22. OUR OPERATING PRINCIPLES
23. Safety over forced certainty. When information is insufficient, the system should say so rather than manufacture confidence.
24. Clinician-guided, model-bounded. AI should support structured reasoning and prioritization; critical safety constraints should not depend on model confidence alone.
25. Measure before scale. We want predefined evaluation criteria, local review, and evidence from real workflows before broad clinical influence.
26. Kenya-first, interoperable. Build with the direction of national digital health - not around it - and avoid duplicating systems that already have institutional authority.
27. WHERE A KENYAN CLINICIAN ADDS OUTSIZED VALUE
28. Pressure-test clinical assumptions. Where does a technically correct pathway fail in actual practice?
29. Define unacceptable failure. Which misses, delays or false reassurances should automatically stop a pilot?
30. Expose workflow reality. What information is actually available before referral, and what is routinely missing?
31. Shape evaluation. Which outcomes would make a medical director, county team or facility leader trust the evidence?
32. A DISCIPLINED PATH TO PROOF
33. 1 Clinical design review — Narrow the first use case, define the safety boundaries, and identify where current assumptions break in practice.
34. 2 Silent evaluation — Compare Tunza's recommendations against normal care without changing patient management; adjudicate disagreements locally.
35. 3 Narrow pilot — Only after predefined thresholds are met: a tightly scoped cohort, defined facilities, explicit escalation rules and measurable endpoints.
36. 4 Evidence package — Document safety, workflow fit, failure modes, and operational outcomes before expanding scope.
37. Why engage early? The earliest clinical collaborators will have disproportionate influence over the safety criteria, evaluation design and workflow assumptions before they become expensive to change. We are intentionally keeping the first clinical circle small until the evidence framework is strong.
38. THE CONVERSATION WE WANT TO HAVE
39. Not: "Would you use this?"
40. Instead: Where would you distrust it? What would make it clinically valuable? What evidence would you require before allowing it near a real care decision? Which part of the current journey creates the most avoidable risk or friction?
41. The question is not whether Kenya will digitize care - it already is. The question is whether the next generation of digital health will merely document care, or help make each transition more clinically coherent.

Absent from this brief (relevant to Evan’s ask): death, “has to exist,” eCHIS does not order which sick child goes first, demo limits, localStorage, fake referral facilities, “not clinically validated,” household/CHP/facility as shipped roles.

## F4 — Claims in the Kenya brief that the 2026-09-23 fact sheet forbids

Report both. Do not inherit the forbidden side into `friend.md` / `general.md` / `investor-unsent.md`.

Forbidden list source: `prompts/tunza-vision-2026-09-23/fact-sheet.md` section Forbidden.

| id | Kenya brief says | Fact sheet forbids | How to treat |
|---|---|---|---|
| C1 | “More than 107,000 Community Health Promoters” and “Kenya MoH reports 107,000+ CHPs” (lines 10, 18) | Uncited 100,000-promoter / 9M household figures, including “100k” and “9M” (`fact-sheet.md` Forbidden; `QUERY-tunza-model-design.md:53`) | Same figure family as the banned 100k. Brief attributes it to “MoH - Community Health, May 2026.” That is not the grilling’s uncited 100k, but it is still a CHP headcount. **Do not inherit** until a later fact sheet cites a checked MoH page. Do not use 9M. |
| C2 | “designed to strengthen decision quality and continuity” (line 8); “help each transition become safer, faster and more accountable” (line 11); “next clinically appropriate action” (line 12); “clinically disciplined layer” (line 16); “clinically valuable” (line 40); “more clinically coherent” (line 41) | Clinical benefit, diagnostic certainty, or regulatory clearance | Footer says “no clinical-performance claim.” Body still states safety/quality as Tunza’s effect. **Do not inherit as achieved benefit.** Status-quo harm may be heated; Tunza’s demonstrated effect may not. |
| C3 | “the Digital Health Agency now certifies digital health systems against security, functionality and information-exchange standards” (line 10); footer “DHA Certification” + URI `https://certification.dha.go.ke/` | Regulatory clearance | This is a **portal / process**, not a statement that Tunza is certified. Keep as a reference link only, labeled not an endorsement. **Do not inherit “Tunza is DHA-certified.”** |
| C4 | “Compare Tunza's recommendations against normal care” (line 34); “AI should support structured reasoning and prioritization” (line 24) | A trained model; the public app is Anthropic; clinical benefit | Future operating principle and a proposed silent-eval step. Public demo is keyword rules, not clinically validated, not a model. **Do not inherit as current capability.** |
| C5 | “county team or facility leader” (line 31); “defined facilities” (line 35) | A named county as fact, or a partnership he already has | No named county, no signed NGO. OK as hypothetical evaluators. **Do not turn into a county we have.** |
| C6 | “If done correctly, Tunza becomes more valuable as the health system becomes more connected” (line 17) | A moat. “The only gap.” Unique AI insight | Not those words. Still a value claim. **Do not inherit as a moat.** |

Not present in the Kenya brief (do not introduce from Set A either): trained weights, Anthropic as the public app, signed NGO, Solomon, 500 billion, Renaissance / Two Sigma / Jane Street / HRT, 9 million households, invented terms/amounts, README lines 62–81 feature list.

Present in **Set A** and forbidden for the 09-23 pages — listed so 2.a does not pull them in:

- `Tunza.pdf` pages 2–3 copy the README feature list (voice, image, optional vitals, outbreak signal, verified-clinician workflows, web push, PWA). Forbidden: copying README 62–81.
- `Tunza-Brief.pdf` states Anthropic as the triage engine, NGO partnership as the route in, “NGO relationship is the moat,” 100k+ CHPs, ~9M households, “a miss costs a child.” Forbidden: trained/Anthropic-as-product, signed NGO, moat, 100k/9M, clinical-benefit causal line.

## F5 — Decoder notes for the next writer

- Helper: `prompts/tunza-vision-2026-09-24-urgent/decode_pdf.py` (stdlib; ASCII85+Flate and Flate; ToUnicode for Skia).
- Kenya brief and Tunza-Brief are clean ReportLab literal strings.
- `Tunza_Complete_Guide.decoded.txt` still breaks a line per word because each Skia word is its own BT/ET. Content is usable. Do not treat that file as a vision-page source.
- Originals left byte-unchanged (hashes above).

## Handoff

Next: 1.b `WRITING-CONTRACT.md` and 2.a `fact-sheet-urgent.md` / `comparison-note.md`. Use F2 verdict (Kenya brief vs cooled 09-23 pages), F3 line numbers, and F4 C1–C6 as the do-not-inherit list. Do not copy 107,000+, “safer/faster,” or DHA-as-clearance into the urgent pages unless 2.a independently cites a checked source and still marks it status-quo, not Tunza effect.
