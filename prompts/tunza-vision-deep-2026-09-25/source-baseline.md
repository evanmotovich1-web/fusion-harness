# Tunza depth research: source baseline

Task 2.a. Recorded 2026-09-25 UTC. This package is research for a new document, not a product implementation, deployment approval, or legal opinion. Only `prompts/tunza-vision-deep-2026-09-25/` was written.

## B1. Exact requested PDF is now identified by content

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `/Users/evanmotovich/Downloads/Tunza Vision.pdf` | 34003 | `df107bed48cc668a977767543595359fe25ee9632736703e8563a945cff6405a` |
| `/Users/evanmotovich/output/pdf/Tunza Vision.pdf` | 34003 | `df107bed48cc668a977767543595359fe25ee9632736703e8563a945cff6405a` |
| `/Users/evanmotovich/output/pdf/Tunza Vision.md` | 5175 | `5a8c3cc2ece287665ab61ce29a56870020686df2fc31dabd957c502d514c155a` |

The two PDFs are byte-identical. Apple PDFKit extracted all two pages from the exact Downloads file. Its editorial text equals the Markdown after removing the extraction header, page markers, standalone numeric page footers, and the Markdown page-break comment, then collapsing whitespace. No lexical or punctuation substitutions were needed. Both contain 839 editorial words. Differences: zero.

Evidence: `evidence/original-hashes.json`, `evidence/base-pdf-extracted.txt`, `evidence/base-source.md`, and `evidence/base-text-comparison.json`. The earlier task 1.a report's 33,427-byte figure is superseded by direct filesystem measurement of 34,003 bytes. Its uncertainty about text equivalence is resolved. Do not reuse its byte count.

## B2. Document lineage and editorial scope

The vault records the progression from the original three-page Jacob strategy brief through successive plain-language edits, coordination additions, shortened AI explanation, removal of headings, and the final speed/simplicity/learning close. It records the rename to `Tunza Vision.*`. This establishes historical editing context, not new global instructions. `/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:62-111`.

The requested base is the verified 839-word essay, not the earlier GPU campaign brief. Preserve its care-coordination ambition, plain language, proposal-versus-result distinction, and recognition that a request, acceptance, arrival, and completed care differ. The new request permits deeper analysis. It does not require reproducing the old essay verbatim or inheriting an old one-page limit, absence of headings, or document-specific forbidden-word list.

No prior PDF, audience page, source note, vault file, or Tunza code file was edited. No publication, partner contact, patient-record access, or spending commitment occurred.

## B3. Evidence classes and retrieval method

- **Fresh primary-source retrieval:** Public Ministry of Health, Social Health Authority, and Kenya Law documents fetched on 2026-09-25. Each `evidence/<source>.json` records requested/final URLs, access timestamp, HTTP result, file bytes, SHA-256, and available response dating. HTML was retained and readable text derived using Python's HTML parser. Quotes in `kenya-system-facts.md` are exact excerpts or whitespace-normalized PDF excerpts, with omissions marked.
- **Fresh extraction of a previously retrieved primary source:** WHO Kenya 2025 report. The cached PDF is 33,296,408 bytes and hashes to `30df6fac2f218c453683822d324487de9a0c656a9f2be11339de7be410be31ba`, matching the prior recorded hash. All 82 pages were freshly extracted to `evidence/who-2025.txt`. Cached HTTP headers record September 24 retrieval and April 13, 2026 last modification. The PDF was not fetched again. Its existing path is `/tmp/tunza-who-annual-report-2025.pdf`. Provenance: `evidence/who-cache-provenance.json` and `evidence/who-cached-http-headers.txt`.
- **Repository/vault evidence:** Founder statements, prior audits, the base essay, and task 1.e's code investigation establish intent or local implementation facts only. They are not independent evidence of Kenya's deployed eCHIS capabilities or government payment rules.
- **Analysis:** Proposed workflow, overhead mechanisms, partner choices, and economic measurement are inferences or design recommendations. A source describing a system problem does not establish Tunza's effect on it.

No semantic-search tool was available. Targeted filesystem search and public HTTP retrieval were used. No inaccessible source was presented as read. Commands were foreground and bounded to 60 seconds. Fetches had a 14-second socket timeout and an 8 MiB per-source body cap. Search results are discovery aids, not claim evidence.

## B4. Material corrections for downstream writers

| ID | Prior claim or uncertainty | Result of this task |
|---|---|---|
| C1 | eCHIS is only a register or provides no decision support | **Contradicted as a broad claim.** The Ministry's own privacy policy explicitly describes client management with decision support, surveillance, commodity management, performance management, messaging, and eLearning. Specific acuity ranking, referral acknowledgements, and returned outcomes remain unverified. Use S05. |
| C2 | No source for the 92% doctor shortage | **Source wording verified** in the hash-matched WHO PDF, printed p. 67. Its underlying doctor-specific denominator and methodology were not established. Attribute to the report or omit. Never convert it into a local capacity estimate. Use S11. |
| C3 | More than nine million households established by MoH node 2374 | **Not supported by that page**, freshly reread. The vault's broader claim lacks a checked alternative source in this run. This does not prove no other source exists. Omit pending one. |
| C4 | Sixteen maternal deaths per day | Prior audit reports it absent from the WHO report. No newly checked source supports it. Do not derive it from a mortality ratio without compatible annual counts. |
| C5 | 107,000 CHPs and 10,277 connected facilities | Fresh MoH pages support dated national-context statements. They do not establish Tunza reach, access, equipment coverage at a particular site, or available staffing. Use S10. |
| C6 | March 2026 referral policy is final | Checked source says development and drafting. Whether a later final policy exists was not established. Refer specifically to the March workshop, not present-day policy finality. Use S04. |
| C7 | No financing mechanism source available | **Partly resolved.** Retrieved Social Health Insurance Act and SHA's benefit/tariff page. They establish published fund structure and a population-based PCN budget mechanism. They do not establish pilot-site payments, marginal savings, current contract terms, or procurement approval. Use S07–S08. |
| C8 | NGO partnership unlocks eCHIS and training data | **Unsupported.** An NGO can be a proposed operational partner, not an automatic authorization path. Ministry eCHIS policy, data-protection law, and Digital Health Act require distinct consideration of purpose, access, confidentiality, and authority. Use S05 and S09. |
| C9 | A training use always makes Tunza a controller, regardless of arrangement | Overbroad upstream analysis. Role follows actual purpose/means and instructions under the DPA. Processing beyond controller instructions can change the role. No concrete Tunza arrangement was inspected. Use S09, not an automatic label. |
| C10 | Statute text alone proves a proposed pilot is currently lawful | **Not established.** Current amendments, court orders, implementing regulations, certification scope, research-review classification, local agreements, and deployment details were not exhaustively assessed. Treat this as legal source mapping, not clearance. |

## B5. Explicit retrieval limits

- Initial date-specific Primary Health Care Act and Social Health Insurance Act URLs returned 404. Undated Kenya Law routes resolved to the published 2023-11-24 versions. Both were then retrieved. The primary-care page embeds a PDF, which was downloaded and fully extracted.
- The guessed CHT eCHIS example URL returned 404. The CHT sitemap did not provide a Kenya-specific example. No technical-platform or feature-absence conclusion follows. A subsequent Ministry search located the eCHIS privacy policy and an implementation-partnership page.
- `https://sha.go.ke/resources` returned 404. The official homepage led to the successfully retrieved `https://www.sha.go.ke/benefit-tariffs/`.
- The DHA certification portal returned a JavaScript application shell with its title, not readable criteria. The Digital Health Act supplies evidence of a certification function, not this tool's current approval status or applicable certification procedure.
- The May 28, 2026 MoH newsletter linked by the original essay returned HTTP 200 but exceeded the 8 MiB retrieval cap. It was not saved or read. Do not describe that link as freshly verified. The new essay can instead cite the fully retrieved May 19 MoH page for CHP support.
- No current pilot-county budget, provider contract, paid claim, deployed eCHIS form/API configuration, ambulance operating procedure, laboratory transport contract, live stock record, or Tunza partnership agreement was obtained.

## B6. Handoff

Read `kenya-system-facts.md` first. Its S01–S12 identifiers are the source/claim keys for the new essay and implementation brief. Use primary-source URLs and relevant dates in the essay, and retain precise local locators in the supporting brief. Do not turn cited statutory roles into a claim of universal operational readiness.

The strongest new findings for the next tasks are that (1) eCHIS already claims decision-support functions, (2) primary care networks have an existing coordination structure, and (3) the published primary-care financing mechanism is not a simple fee for each encounter. The product and savings arguments must accommodate all three.

## B7. Validation evidence

`evidence/validation.json` records a successful check of all 40 block quotations against the saved source text after whitespace normalization, all 18 saved HTTP response hashes, and all four protected-file hashes (three base artifacts plus the cached WHO PDF). The PDF/Markdown comparison remains exact at 839 editorial words, with two PDF pages and four hyperlink annotations. Explicit local citation ranges checked by the validation script are in bounds. This mechanical check does not replace interpretation review or verify every claim against current local practice.

`evidence/retrieval-index.json` records 23 retrieval attempts: 18 saved responses and five not saved, including the capped newsletter PDF. Saved discovery pages and the DHA application shell are not counted as substantive verification. A final tracked-file diff/status check returned no changes. The only authored package is this new folder. Original-file preservation is directly checked for the four hash-recorded files, not represented as a full-disk integrity audit.
