# Render check — task 5.b

Checker: terra, not the renderer. Checked 2026-09-24. **Do not accept the current render: F1 requires repair by grok in task 5.a.** No Markdown source, PDF, renderer, or original document was changed by this check.

## V1 — Independent extraction and source diff

Used macOS PDFKit to extract every page, inspect link annotations, and render all four pages to PNG. Also decoded ReportLab text operators in content-stream order using the existing stdlib decoder. That second extraction distinguishes missing content from PDFKit reading-order behavior.

Normalization removed Markdown heading/bold/code delimiters, bullet markers, whitespace wrapping, PDF running headers/footers/page numbers, and the five blank-field underline placeholders. It did not remove punctuation or words. Compared the complete documents, including sources and the investor closing note.

| PDF | Pages / allowed | Content-stream diff | PDFKit diff |
|---|---|---|---|
| `Tunza-friend.pdf` | 1 / 1–2 | Exact normalized match | Exact normalized match |
| `Tunza-general.pdf` | 1 / 1 | Exact normalized match | Exact normalized match |
| `Tunza-investor-unsent.pdf` | 2 / 1–2 | Missing `),` after DHA URL | Same loss, plus Q4 reading-order issue |

## F1 — Required repair: punctuation disappears after a URL

Source closing note: `(https://certification.dha.go.ke/), not a Tunza approval.`

Rendered closing note: `(https://certification.dha.go.ke/ not a Tunza approval.`

Confirmed in both independent extractions and visually on investor page 2. The closing parenthesis and comma are absent, not merely extracted incorrectly. The non-approval language survives, but the PDF does not faithfully reproduce its source.

Cause: `render_pdfs.py:39-42` strips punctuation from the regex match before building the link and never appends the stripped suffix. A direct call to `linkify()` reproduces the loss.

Repair: keep trailing punctuation as visible text outside the link. Keep the URI itself exactly `https://certification.dha.go.ke/`. Regenerate the PDFs without editing the audited Markdown. Re-run the normalized source diff and page/link checks before close.

## F2 — PDFKit reading-order issue, not missing text

On investor page 1, PDFKit emits the final word `app?` before the Q4 paragraph. The word is present in the correct visual position, immediately below the rest of Q4. Content-stream extraction preserves the full sentence in order. No clipping or content loss was found here.

This is separate from F1. If exact PDFKit copy/paste order is required, grok should adjust the Q4 layout and retest rather than changing its words. Do not treat `app?` as an omitted word or silently normalize its position away.

## V2 — Stakes, honesty, and visual checks

Word positions below use normalized page-body text, including headings and reader lines but excluding running headers and footers. Every opening carries both phrases before word 80, within the requested first 80–120 words.

| PDF | Queue sentence begins | “has to exist” begins |
|---|---|---|
| Friend | Word 18 | Word 58 |
| General | Word 14 | Word 40 |
| Investor | Word 24 | Word 50 |

All three retain the demo-not-yet boundary, not-a-doctor/not-a-diagnosis language, unvalidated rules, on-device/browser storage, fake referral facilities, and the full emergency-services/professional-care disclaimer. The additional discussion-draft footer appears on every rendered page. Investor line one remains “Terms are not set. Do not send this.” All five term fields remain unfilled.

General and investor retain the explicit UNKNOWN death boundary. Friend contains no explicit death-causality sentence in either Markdown or PDF. Its supported queue opening and lack of a mortality claim survive unchanged. The upstream statement that an explicit UNKNOWN death sentence survives in all three is therefore too broad, not evidence of a rendering omission.

Inspected all four PNGs. No visible clipping, overlap, or missing paragraphs. PDFKit reports zero character bounds outside the page on every page. Main body sizes are approximately 9.4 pt, 9.212 pt, and 9.588 pt respectively. Sources are smaller, approximately 7.4–7.8 pt. Investor page 2 contains the remaining conclusion, sources, and closing note. Page limits hold without treating source notes as a separate exemption.

## V3 — Link checks

Friend has no external link annotation. General has one MoH annotation. Investor has one MoH annotation on page 1 and one DHA annotation on page 2. All are valid HTTPS URIs matching their Markdown targets, with no punctuation in the URI.

Both unique destinations returned HTTP 200 to bounded HEAD requests, without changing the URL:

- `https://health.go.ke/kenya-moves-strengthen-patient-referral-system-through-new-national-policy`
- `https://certification.dha.go.ke/`

Reference/not-endorsement wording survives beside the MoH links. The DHA process/not-approval wording survives despite F1. HTTP reachability does not establish endorsement or clearance.

## V4 — Downloads originals

All three Downloads originals recorded in `inventory-verdict.md` match its SHA-256 baselines exactly:

| Original filename | SHA-256 |
|---|---|
| `e16739b3-33a4-4cf7-a7ed-cdcc8bb02fc1.pdf` | `d8e3e772d93b6624578fd891b1f9c6fcc985880fcad4ad911ccb5157196195d2` |
| `Tunza.pdf` | `5ce717e704d445329b6ec2d1860cf4fa8b506aa507336d49ef011fd95b9a2e34` |
| `Tunza_Complete_Guide.pdf` | `ca91a2e186cf8fd20bbfc4edd1c95dc15477826ec4c295420845390ca877f943` |

This verifies the inventoried Downloads originals, not unrelated files in Downloads.

## F3 — Old Markdown preservation: qualified evidence

The four files in `prompts/tunza-vision-2026-09-23/` retain mtimes corresponding to the earlier audit's 01:43–01:47 local times. Their measured UTC mtimes are 05:43–05:47 on 2026-09-24. No pre-collaboration SHA-256 baseline for these files was present in the supplied inventory or reports. Therefore this check cannot independently prove byte-for-byte preservation across the entire collaboration from timestamps alone.

Current hashes, recorded for subsequent verification:

| File | SHA-256 |
|---|---|
| `fact-sheet.md` | `5ededa8fcff2add4b64c8588b80696a4e43d82433daee5f750f448b5198d5a6a` |
| `friend.md` | `3a6436150fd9220eff972f356b5b4bf8e8953a5e9af2a4b2e850aa0c9c66e49b` |
| `general.md` | `dd2e7d2781d9021e5418bec1521edf8fde8d31abf4cf8bf53adc1da8b8de4c7b` |
| `investor-unsent.md` | `14345acf3b7875cf8c9e93e0021a6821f2fe00adc0c655dbe10d7e3a894490c9` |

Snapshots confirm these files, all existing urgent Markdown files, and all three PDFs stayed byte-identical during task 5.b. F3 is a historical evidence limitation, not a detected modification or a renderer repair request.

## V5 — Checked artifact identities and evidence

| PDF | SHA-256 |
|---|---|
| `Tunza-friend.pdf` | `d5b159c3372c8debb7c23622bbbb3eb256d876b45a217e958a3011360857ad28` |
| `Tunza-general.pdf` | `da6d028289a64eca1d281198abe55c91290811bf54cb98fd937c00f149b715cf` |
| `Tunza-investor-unsent.pdf` | `0694003e5ef212125a93aecf84d0036d121a810dec3ff4e96bc2229dc751f51c` |

Temporary verification evidence: `/tmp/fusion-harness-atlxkE/terra-render-check/` contains `pdfkit.json`, each document's `*.roundtrip.txt`, `*.diff.txt`, and `*.content-order.diff.txt`, four page PNGs, `url-check.json`, `snapshot.json`, and the independent PDFKit helper `check.swift`.

## Handoff

Grok / task 5.a: repair F1 in the renderer, regenerate, and return for second-reader verification. F2 is a disclosed extraction-order issue to retest. Preserve the audited wording, the blank financing fields, all honesty boundaries, and the original files. This check rejects the current render for F1 only. It does not authorize rewriting the pages or sending them.
