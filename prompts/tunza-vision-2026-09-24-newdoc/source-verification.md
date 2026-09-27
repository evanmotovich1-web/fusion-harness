# Source verification — national figures in the new Tunza PDF

Dated 2026-09-24. Task 1.c. This verifies candidate claims against the primary URLs linked from `/Users/evanmotovich/Downloads/07c5a914-5620-4982-8472-709ac59f1a21.pdf`. A link annotation is not evidence by itself. The source must state the claim.

## Verdict summary

| id | claim checked | primary source verdict | page-use ruling |
|---|---|---|---|
| F1 | More than 107,000 Community Health Promoters | **VERIFIED** at MoH node 2374 | May be used with MoH attribution and source date. It is national context, not a Tunza result. |
| F2 | More than nine million households/families reached | **NOT FOUND** at MoH node 2374 | Keep out when node 2374 is the cited source. That page says “household-level” but gives no household count. |
| F3 | Maternal mortality estimated at 355 deaths per 100,000 live births | **VERIFIED** in WHO Kenya Annual Report 2025, printed p. 60 | May be used with WHO-report attribution. It is national context, not a Tunza result. |
| F4 | About 16 maternal deaths per day | **NOT FOUND** in the WHO report | Keep out. The report gives a ratio, not this daily count. Do not derive the daily count without a sourced number of maternal deaths or live births for the same period. |
| P1 | Kenya is developing a national referral policy addressing fragmentation, continuity, interoperability, and accountability | **VERIFIED** on the MoH referral-policy page | State as policy development, not final policy, implementation deadline, Tunza integration, or endorsement. |
| P2 | UHC-reforms page reports 10,277 facilities connected to national systems | **VERIFIED** on the MoH UHC-reforms page | May be used with MoH attribution and source date. It is national context, not Tunza access or deployment. |

## F1 — Community Health Promoter headcount

- **URL:** https://www.health.go.ke/node/2374
- **Source title:** “Kenya calls for stronger collaboration and sustainable investments in community health systems at the #WHA79”
- **Source date:** Published May 19, 2026 (`schema:dateCreated` is `2026-05-19T19:02:28+00:00`).
- **Fetch result:** HTTP 200 on 2026-09-24.
- **Verbatim source sentence:**

> “The PS noted that the The government is supporting over 107,000 Community Health Promoters with monthly stipends, digital devices, and medical kits to strengthen disease prevention, early detection, referrals, and household-level healthcare services across the country, while calling for stronger collaboration and sustainable investments to advance the global community health agenda.”

- **Verdict:** **VERIFIED.** The source says **over 107,000**, not exactly 107,000.
- **Boundary:** This verifies a national programme figure. It does not establish that Tunza works with those promoters, devices, kits, or household services.

## F2 — Nine million households or families reached

- **URL checked:** https://www.health.go.ke/node/2374
- **Source date:** Published May 19, 2026.
- **Fetch result:** HTTP 200 on 2026-09-24.
- **Relevant verbatim source phrase:**

> “...household-level healthcare services across the country...”

- **Search result:** The page contains no occurrence of “million” and no numeric household or family reach figure.
- **Verdict:** **NOT FOUND.** Node 2374 does not support “over nine million households,” “nine million families,” or an equivalent count.
- **Boundary:** Keep the household/family count out of downstream pages when this is the cited source. “Household-level services” is not a household count.

## F3 — Maternal mortality ratio

- **URL:** https://www.afro.who.int/sites/default/files/2026-04/WHO%20Kenya%20Annual%20Report%202025.pdf
- **Source title:** *WHO Kenya Country Office 2025 Annual Report*
- **Source date:** Report year 2025. PDF creation and modification date: April 13, 2026. HTTP `Last-Modified`: April 13, 2026.
- **Fetch result:** HTTP byte-range responses 206 on 2026-09-24; four contiguous ranges reconstructed the complete 33,296,408-byte PDF. SHA-256: `30df6fac2f218c453683822d324487de9a0c656a9f2be11339de7be410be31ba`.
- **Location:** Printed page **60**, physical PDF page **59**, section 3.1 “Sexual and Reproductive Health and Rights.”
- **Verbatim source sentence:**

> “Despite these gains, maternal mortality remains high at an estimated 355 deaths per 100,000 live births.”

- **Following source sentence:**

> “Preventable causes, including postpartum haemorrhage and hypertensive disorders of pregnancy, continue to contribute substantially to maternal deaths, despite high coverage of skilled birth attendance (89%) and four or more antenatal care visits at 66%.”

- **Verdict:** **VERIFIED.** Preserve “estimated” and attribute the figure to the 2025 WHO Kenya report.
- **Boundary:** The report does not measure Tunza, an eCHIS ordering effect, or deaths prevented by an app.

## F4 — About 16 maternal deaths per day

- **URL checked:** The WHO Kenya Annual Report 2025 PDF above.
- **Source date:** Report year 2025; PDF dated April 13, 2026.
- **Search result:** No occurrence of “16 mothers,” “16 women,” “sixteen,” “per day,” “each day,” or “every day” in connection with maternal mortality. The report states the 355-per-100,000 ratio but does not convert it to a daily count.
- **Verdict:** **NOT FOUND.** The WHO report does not support “about 16 mothers a day.”
- **Boundary:** A ratio per 100,000 live births cannot be converted to a daily count without a compatible number of live births or maternal deaths and a defined period. No such input is cited for this claim here.

## P1 — National referral-policy page

- **URL:** https://health.go.ke/kenya-moves-strengthen-patient-referral-system-through-new-national-policy
- **Source title:** “Kenya Moves to Strengthen Patient Referral System Through New National Policy”
- **Source date:** Event dated March 3, 2026; page published March 6, 2026 (`schema:dateCreated` is `2026-03-06T07:02:54+00:00`).
- **Fetch result:** HTTP 200 on 2026-09-24.
- **Verbatim source lines:**

> “The Ministry of Health is spearheading the development of the Kenya Healthcare Referral Policy to strengthen coordination across levels of care and improve patient outcomes.”

> “The initiative, being led by the Division of National Health Referral and Emergency Services under the Directorate of Curative and Nursing Services, aims to address fragmentation within Kenya’s referral system by enhancing continuity of care and improving maternal and child health outcomes.”

> “The proposed policy will institutionalise clear governance structures, digital interoperability standards, accountability mechanisms, and sustainable financing linkages to ensure efficient referral pathways and a resilient nationwide referral ecosystem.”

- **Verdict:** **VERIFIED.** The page exists and describes policy **development** addressing fragmentation, continuity, interoperability, accountability, governance, and financing.
- **Boundary:** It does not say the policy is final, give a Tunza implementation deadline, or establish Tunza integration, partnership, approval, or endorsement.

## P2 — UHC-reforms page

- **URL:** https://www.health.go.ke/health-cs-outlines-uhc-reforms-national-assembly-retreat
- **Source title:** “Health CS outlines UHC reforms at National Assembly retreat”
- **Source date:** Event dated January 28, 2026; page published January 29, 2026 (`schema:dateCreated` is `2026-01-29T12:16:46+00:00`).
- **Fetch result:** HTTP 200 on 2026-09-24.
- **Verbatim source sentence:**

> “The CS reported major gains in health digitisation, with 10,277 facilities connected to national systems and 30,087 digital devices deployed, as well as strengthened human resources for health, anchored by 107,000 Community Health Promoters and improved UHC staff remuneration under SRC rates.”

- **Verdict:** **VERIFIED.** The page states 10,277 connected facilities, 30,087 devices, and 107,000 Community Health Promoters.
- **Boundary:** It does not say Tunza has access to those facilities, devices, promoters, or national systems. It also does not state that nine million households use Tunza or were reached through Tunza.

## Downstream gate

Allowed with attribution:

- MoH, May 2026: **over 107,000 Community Health Promoters supported**.
- WHO Kenya 2025 report, printed p. 60: **estimated 355 maternal deaths per 100,000 live births**.
- MoH, January 2026: **10,277 facilities connected to national systems**.
- MoH, March 2026: referral-policy **development** focused on coordination, fragmentation, continuity, interoperability, and accountability.

Not supported by the checked source:

- **Nine million households/families reached** from node 2374.
- **About 16 maternal deaths per day** from the WHO Kenya Annual Report 2025.

These figures describe national context. None is a Tunza performance, deployment, partnership, certification, clearance, deaths-prevented, or lives-saved measurement.
