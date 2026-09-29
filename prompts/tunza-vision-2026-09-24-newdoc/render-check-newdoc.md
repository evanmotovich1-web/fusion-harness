# Render check — newdoc task 5.a

Checked 2026-09-24 by terra, who did not render these PDFs. **Current render acceptance is blocked by F4: the friend PDF lacks its new MoH source URL.** F1 is fixed. F2 remains an extraction-order issue. F3 is an unavailable historical baseline, not a renderer defect.

Only this report was added to the repository by this task. PDFs, Markdown sources, renderer, and originals were not edited.

## V1 — Independent round-trip and exact source comparison

Extracted all four pages with macOS PDFKit and separately decoded the ReportLab text operators in content-stream order. Compared each complete PDF against current Markdown, including source notes and the investor closing note.

Normalization removes Markdown heading/bold/code markers, bullets, wrapping whitespace, running headers/footers/page numbers, and the five blank-field underline placeholders. It does not delete punctuation, reorder words, or omit source sections.

| PDF | Pages / limit | Content-stream comparison | PDFKit comparison |
|---|---|---|---|
| `Tunza-friend.pdf` | 1 / 2 | Exact normalized match | Exact normalized match |
| `Tunza-general.pdf` | 1 / 1 | Exact normalized match | Exact normalized match |
| `Tunza-investor-unsent.pdf` | 2 / 2 | Exact normalized match | F2: `app?` moves before Q4 |

## F1 — Closed: punctuation after URLs

Investor page 2 now contains the exact source wording:

> (https://certification.dha.go.ke/), not a Tunza approval.

Both extraction methods and the rendered image confirm the closing parenthesis and comma. The link target is exactly `https://certification.dha.go.ke/`, without punctuation. No source-content loss remains in the content-stream comparisons.

## F2 — Still open: PDFKit reading order

PDFKit still extracts the investor Q4 final word `app?` before the Q4 paragraph, now on page 2. The word appears in the correct visual location, and content-stream extraction preserves the sentence in order. The left-alignment change did not resolve this behavior.

Do not claim exact PDFKit round-trip equality or that F2 was repaired. This is not missing text or visible clipping. Renderer layout may be adjusted without changing words if PDFKit equality is required. The defect that independently blocks this render acceptance is F4 below.

## F4 — Required repair: friend MoH citation has no URL

Task 4.a requires new MoH/WHO citations to render with their URLs. The friend page now cites both WHO mortality and the MoH referral-policy outcomes framing, but it has only one external annotation: the WHO report. Neither its new paragraph nor source [8] carries a MoH URL annotation or visible URL.

Missing target:

`https://health.go.ke/kenya-moves-strengthen-patient-referral-system-through-new-national-policy`

This is the verified referral-policy source in `source-verification.md:70-70`. Add a reference link to the existing MoH citation text in the renderer, without changing the audited Markdown, then regenerate and recheck. Do not invent a different source or append an endorsement claim.

## V2 — Boundaries, terms, openings, and visual checks

All three PDFs retain the complete honest-limits block: not a doctor/diagnosis, rules not clinically validated, browser/on-device storage, fake referral facilities, and the emergency-services/professional-care disclaimer. The demo-does-not-do-this-yet sentence survives on every document. The discussion-draft footer survives on every page.

Investor's first content line is verbatim `Terms are not set. Do not send this.` All five fields remain blank, represented by underscores only. P1–P3 and Q1–Q4 match the current Markdown. The 355-per-100,000 figure and country-not-Tunza-results qualification survive on every document. The gate-authorized 107,000 figure survives only on investor. General and investor keep the explicit unknown queue-death boundary. Friend adds no claim that Tunza has prevented deaths.

Opening word counts include reader lines and headings, but exclude running headers and footers:

| PDF | Queue sentence begins | “has to exist” begins |
|---|---|---|
| Friend | 18 | 58 |
| General | 14 | 40 |
| Investor | 24 | 50 |

Both opening elements occur before word 80 in all three, satisfying the first-80–120-words check.

Inspected all four page PNGs. No visible clipping, overlapping text, or missing paragraphs. PDFKit reports zero character bounds outside the page on all four pages. The investor questions continue onto page 2, within the two-page limit.

## V3 — Annotation targets and reachability

All present annotations match the intended HTTPS targets. WHO references point to the verified WHO report, the CHP reference points to MoH node 2374, referral-policy references point to the verified policy page, and the DHA reference points to its portal. General and investor have all required target URLs. Friend lacks the MoH target as recorded in F4.

| PDF | Annotation count | Unique targets |
|---|---|---|
| Friend | 1 | WHO |
| General | 4 | WHO, MoH referral policy |
| Investor | 5 | WHO, MoH CHP, MoH referral policy, DHA |

Repeated WHO annotations use the same destination. They do not introduce another source. Reference/not-endorsement and DHA process/not-approval wording survive.

All four unique destinations returned HTTP 200 to bounded HEAD requests, with unchanged final URLs. This is reachability evidence, not evidence of endorsement or clinical clearance. Exact destinations and responses are recorded in the temporary `url-check.json`.

## V4 — Downloads originals: all four match recorded baselines

| Original in Downloads | Baseline | SHA-256, verified unchanged |
|---|---|---|
| `07c5a914-5620-4982-8472-709ac59f1a21.pdf` | task 1.a / `identity-verdict.md` | `24aaaf859b3c2e0c610474e4ba8282e58b1e87769307f8a8b98b76cf8b585d85` |
| `e16739b3-33a4-4cf7-a7ed-cdcc8bb02fc1.pdf` | earlier `inventory-verdict.md` | `d8e3e772d93b6624578fd891b1f9c6fcc985880fcad4ad911ccb5157196195d2` |
| `Tunza.pdf` | earlier `inventory-verdict.md` | `5ce717e704d445329b6ec2d1860cf4fa8b506aa507336d49ef011fd95b9a2e34` |
| `Tunza_Complete_Guide.pdf` | earlier `inventory-verdict.md` | `ca91a2e186cf8fd20bbfc4edd1c95dc15477826ec4c295420845390ca877f943` |

## V5 — 09-23 folder: all four match prior task 5.b

The current bytes of `fact-sheet.md`, `friend.md`, `general.md`, and `investor-unsent.md` in `prompts/tunza-vision-2026-09-23/` match the four hashes recorded in the earlier `prompts/tunza-vision-2026-09-24-urgent/render-check.md:80-85` exactly. There are no additional files in that folder. Full expected/actual values are in the temporary `originals-check.json`.

This establishes preservation since the prior task 5.b snapshot, not before it.

## F3 — Jacob historical baseline unavailable

The requested comparison against “5.b's recorded values” cannot be completed for the Jacob folder. The earlier task 5.b report contains no Jacob hashes. The current collaboration plan has no task 5.b, and no corresponding report or Jacob baseline was found in the supplied collaboration artifacts.

Current values are recorded below for the next verifier. They are not invented historical baselines:

| File in `prompts/tunza-jacob-2026-09-24/` | Current SHA-256 |
|---|---|
| `jacob.md` | `b0df41fe0672d0128777f2049b8408b5bbf79a1fb8ec291fcd6054bbffc5de25` |
| `jacob.html` | `64aaa8ee5023c9c86bd014d1ac937e10304a93f3cfa836eb6283336798d23a0d` |

Both files stayed byte-identical during this check. Historical preservation across earlier tasks remains unverified for this folder. F3 is for the architect to disclose or resolve with an existing baseline, not a repair request against task 4.a.

## V6 — Checked deliverable identities

All hashes match task 4.a's reported output:

| PDF | SHA-256 |
|---|---|
| `Tunza-friend.pdf` | `53160500c5c4e73b96bce098ca6797704d8308901a8748edeac00d33ea2c9e04` |
| `Tunza-general.pdf` | `52a8090dc06862f6fe7d928258396991cded5cb96a96a8598833c97f027a2cb0` |
| `Tunza-investor-unsent.pdf` | `320ec07d8a3660c76dd33d203ac1d47c354637dc23969d0a70eeaf87f32e6ff7` |

Temporary evidence: `/tmp/fusion-harness-fOBVMI/terra-render-check/`. Includes the independent PDFKit helper, `pdfkit.json`, four PNGs, per-document round-trip text and normalized diffs from both extraction methods, `structural-check.json`, `url-check.json`, `originals-check.json`, and a 35-file before-check SHA-256 snapshot. Every snapshotted file remained unchanged during verification.

## Handoff

Grok / task 4.a: fix F4 by linking the friend MoH citation to the verified referral-policy URL, preserve the exact Markdown wording, regenerate, and return for verification. Recheck F2 if making layout changes. F1 must remain fixed. Architect / task 6.a: do not claim Jacob historical hash verification or F2 closure. No document is authorized for sending by this report.
