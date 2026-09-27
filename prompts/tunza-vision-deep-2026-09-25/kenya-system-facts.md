# Kenya system evidence and claim ledger

Prepared 2026-09-25 UTC for Tunza's new depth essay. This is a source-backed research foundation, not legal or clinical clearance. Sources describe national design, published program reports, or website guidance. None measures Tunza's benefits. All `evidence/` paths below are relative to this folder. Retrieval URLs, timestamps, hashes, and HTTP results are recorded in the matching JSON files.

**Evidence status:** FRESH means fetched and read in this task. CACHED means a previously fetched primary document was rehashed and freshly extracted. PROPOSAL means our analysis, not a measured result. UNKNOWN means the inspected evidence does not settle the question. Statutory text is distinguished from local implementation. Applicable amendments, judgments, regulations, contracts, and approval requirements still require deployment-specific review.

## S01. National policy and county service delivery are different responsibilities

**Source/status:** FRESH. Constitution of Kenya, Fourth Schedule, Parts 1 and 2, version dated 2010-09-03. Accessed 2026-09-25.

**URL:** https://new.kenyalaw.org/akn/ke/act/2010/constitution/eng@2010-09-03

**Exact excerpts:**

> 23.National referral health facilities.

> 27.Health policy.

> 2.County health services, including, in particular—
> (a)county health facilities and pharmacies;
> (b)ambulance services;
> (c)promotion of primary health care;

**Locator:** `evidence/constitution.txt:2807-2830`. The first two entries are in Part 1, national functions. The last excerpt is in Part 2, county functions.

**Supported use:** Explain why national digital or policy alignment does not replace a county service-delivery agreement. The legal structure includes both national and county functions.

**Limit:** It does not tell us which county official can sign this particular pilot, who controls each data system, whether an ambulance is available, or who pays a particular trip. County procurement and operational instruments were not obtained.

## S02. Facility levels describe roles, not today's capability

**Source/status:** FRESH. Health Act, 2017, section 25 and First Schedule. Kenya Law's undated route resolved to the 2026-07-10 consolidated version. Accessed 2026-09-25.

**URL:** https://new.kenyalaw.org/akn/ke/act/2017/21/eng@2026-07-10

**Exact excerpts:**

> LEVEL 1: COMMUNITY HEALTH SERVICES

> (c)Recognizes signs and symptoms of conditions requiring referral;

The schedule labels level 2 as “DISPENSARY/CLINIC”, level 3 as “HEALTH CENTRE”, level 4 as “PRIMARY HOSPITAL”, level 5 as “SECONDARY HOSPITAL”, and level 6 as “TERTIARY HOSPITAL”. These are exact heading fragments, not an assurance that every named facility supplies its scheduled services.

For level 4 it includes:

> (j)Proper counter referral;
> (k)Provision of logistical support to the lower facilities in the catchment area;
> (l)Coordination of information flow from facilities in the catchment area.

Section 7 states:

> (1)Every person has the right to emergency medical treatment.

Its definition includes pre-hospital care, stabilization, and arranging referral when the first provider lacks facilities or capability to stabilize the patient.

**Locators:** `evidence/health-act.txt:885-927` (levels), `:328-330` (section 25, including its qualification for pre-existing county facilities), `:135-141` (emergency treatment).

**Supported use:** Distinguish community contact, local primary care, and more specialized care. Returning information to the referring team is not a new objective invented by Tunza.

**Limit:** Do not turn this classification into a clinical routing algorithm or a claim that every level-3 facility has the required laboratory test today. The source contains a qualification in section 25(2). Actual staffing, opening hours, equipment, supplies, and acceptance need verification.

## S03. Primary care networks and CHP supervision already have a statutory structure

**Source/status:** FRESH. Primary Health Care Act, No. 13 of 2023, published November 24, 2023. Source page records assent October 19 and commencement November 2. PDF downloaded and all 22 pages extracted on 2026-09-25.

**URLs:** https://new.kenyalaw.org/akn/ke/act/2023/13/eng@2023-11-24 and https://new.kenyalaw.org/akn/ke/act/2023/13/eng@2023-11-24/source.pdf

**Exact short excerpts:**

> appointed by the county government.

> (b) provision of working tools;
> (c) stipend; and
> (d) supervision.

> (h) provide the community health promoters with the
> required tools of work including kits and reporting
> tools; and
> (i) undertake monitoring and evaluation through
> supportive supervision.

**What the relevant sections provide:** Section 2 defines a community health officer as supervising CHPs and defines the network's level-4 hub and level-2/3 and community-unit spokes. Section 9 addresses CHP selection and county appointment. Section 11 assigns household responsibilities and includes referrals to a link facility. Section 13 addresses county support. Sections 14–16 address national policy direction, funding, and county management. Sections 18–20 address sub-county networks, their committees, and links between community units and facilities.

**Locators:** `evidence/primary-care-act-source.txt:97-160` (definitions), `:280-319` (appointment), `:420-488` (functions), `:536-563` (support and national policy), `:580-639` (funding and county roles), `:719-807` (networks and community units). PDF extraction has intra-word spacing artifacts. Use section numbers as the authoritative locator. Quoted short excerpts above preserve the extracted wording, with line breaks left visible.

**Corroboration:** WHO Kenya 2025 report, printed p. 73, describes “Level 4 facilities as hubs” coordinating with levels 2 and 3 and level-1 community units, with multidisciplinary teams led by family physicians. `evidence/who-2025.txt:3411-3429`. WHO is CACHED, see S11 provenance.

**Supported use:** A candidate pilot should fit a real network and its existing supervisory roles. Do not design the NGO as a replacement authority for CHPs.

**Limit:** Statutory design is not proof that a selected network is fully operational or that stipends arrive on time. No particular county, workforce, or partner is committed to Tunza. Do not present the Act's terms as a complete current legal-status opinion.

## S04. Referral reform addresses continuity, not just sending patients onward

**Source/status:** FRESH. Ministry of Health, “Kenya Moves to Strengthen Patient Referral System Through New National Policy.” Event March 3, published March 6, 2026. Accessed 2026-09-25.

**URL:** https://health.go.ke/kenya-moves-strengthen-patient-referral-system-through-new-national-policy

**Exact excerpts:**

> The Ministry of Health is spearheading the development of the Kenya Healthcare Referral Policy to strengthen coordination across levels of care and improve patient outcomes.

> The proposed policy will institutionalise clear governance structures, digital interoperability standards, accountability mechanisms, and sustainable financing linkages to ensure efficient referral pathways and a resilient nationwide referral ecosystem.

> Key areas under consideration include defining levels of care, strengthening port health services, clarifying backward and forward referral pathways, improving the movement of patients, specimens, and specialised expertise, and aligning referral processes with Social Health Authority (SHA) service entitlements.

**Locator:** `evidence/referral-policy.txt:78-83`.

**Supported use:** The coordination problem includes information returning, samples moving, and service entitlements, not merely directions to the nearest facility.

**Limit:** State that the March workshop described development. We did not establish whether a final policy was subsequently adopted. Do not call Tunza an implementation of an approved policy, an endorsed partner, or a participant in the workshop.

## S05. eCHIS explicitly describes decision support: do not pitch against a fictional empty register

**Source/status:** FRESH. Ministry of Health, eCHIS Privacy Policy. Stated commencement November 16, 2022, live page accessed 2026-09-25. Its historical commencement date does not establish the version deployed in any county today.

**URL:** https://www.health.go.ke/privacy-policy-electronic-community-health-information-system-echis

**Exact excerpt, section 2:**

> The eCHIS application is a digital solution developed to support quality community health service delivery in the Republic of Kenya by providing client-management with decision support, community-based surveillance, commodity management, performance management and automated data management processes and tools, messaging and eLearning capability.

The policy names household members, CHPs, community health supervisors, and sub-county, county, and national managers. It explicitly says supervisors and managers can access collected data. Household inclusion in a privacy policy does not prove a household-facing app or login.

**Exact excerpts, sections 4.4 and 6:**

> Research – data that is collected may be used for testing and evaluation of the eCHIS for system enhancements to improve user experience, to identify usage trends, to develop new services and features, development of (new) research and analysis.

> The Ministry will take all steps reasonably necessary to ensure that all users data is treated securely and in accordance with this Privacy Policy and no transfer of Personal Data will take place to an organization or a country unless there are adequate controls in place including the security of personal data and other collected information.

**Locators:** `evidence/echis-privacy.txt:72-90` (date, scope, users), `:114-137` (purposes, sharing, retention, transfer).

**Conflict:** The founder described an absence of case ordering in the grilling note. `/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:27-28`. The Ministry's broad decision-support description does not prove urgency ranking exists, but it does reject the broader claim that eCHIS provides no decision support. Neither source settles referral acknowledgement, outcome return, the deployed forms, or actual use.

**Supported wording:** “The Ministry describes eCHIS as including decision support. Tunza would first need to identify a specific unresolved handoff in the deployed workflow.”

**Limit:** A general research purpose in a Ministry privacy policy is not permission for Tunza to extract records, train a commercial model, or send data to an overseas provider. No current configuration, API agreement, external access policy, or data-sharing authorization was obtained.

## S06. Existing implementation experience makes training and support part of the product requirement

**Sources/status:** FRESH Ministry implementation page, dated September 12, 2024, accessed 2026-09-25. CACHED WHO Kenya 2025 report, printed pp. 75 and 77.

**URLs:** https://www.health.go.ke/advancing-implementation-electronic-community-health-information-system-e-chis and WHO URL under S11.

**Exact Ministry excerpt:**

> Medic and the Ministry of Health are partnering to advance the implementation of the Electronic Community Health Information System (E-CHIS), aimed at digitizing and streamlining community health services.

**Exact WHO excerpts, whitespace normalized:**

> WHO supported integration of the campaign digital system within eCHIS in Kakamega, Bungoma, Trans Nzoia, Vihiga, and Kilifi counties, transitioning mass drug administration from periodic events into routine primary health care services.

> receiving technical support from the ministry of health technical personnel who oversee the running and updating of the system.

**Locators:** `evidence/echis-moh-implementation.txt:72-79`; `evidence/who-2025.txt:3548-3573` (training, operational support, surveys), `:3636-3640` (eCHIS campaign integration).

**Supported use:** Kenya already has digital implementation partners and support processes. A Tunza partner would need a specific job within existing operations, rather than an assumed exclusive route into government.

**Limit:** These are named partners in other programs, not Tunza partners. Campaign digitization is not evidence of success for clinical triage. The Ministry page identifies Medic as a CHT contributor but does not by itself prove the complete deployed eCHIS technical stack. Do not assert a platform or API from it.

## S07. SHA is an authority administering distinct financing arrangements

**Source/status:** FRESH. Social Health Insurance Act, No. 16 of 2023, Kenya Law version published November 24, 2023. Page records commencement November 22. Accessed 2026-09-25.

**URL:** https://new.kenyalaw.org/akn/ke/act/2023/16/eng@2023-11-24

**Exact excerpts:**

Section 20:
> There is established a Fund to be known as the Primary Healthcare Fund whose object shall be to purchase primary healthcare services from health facilities.

Section 25:
> (1)There is established a Fund be known as the Social Health Insurance Fund.

Section 28:
> There is established a Fund be known as the Emergency, Chronic and Critical Illness Fund to—
> (a)defray the costs of management of chronic illnesses after depletion of the social health insurance cover; and
> (b)to cover the costs of emergency treatment.

Section 33:
> (1)The Authority shall make payments out of the Funds to healthcare providers or health care facilities that are empaneled and contracted in accordance with the provisions of this Act.

**Locators:** `evidence/social-health-act-current.txt:227-250`, `:279-300`. Sections 31–36 describe benefits, tariffs, empanelment, contracting, claims, and settlement, `:291-331`.

**Supported use:** Do not collapse SHA, SHIF, county budgets, and household payments into one payer. The financing structure distinguishes service purchasing, insurance contributions, emergency/chronic coverage, and contracted providers.

**Limit:** The statutory text is not a completed check of current court orders, amendments, regulations, or an individual patient's entitlement. Avoid restating contested eligibility clauses as live patient instructions. No pilot-site paid claims or Tunza procurement arrangement exists in the inspected evidence.

## S08. Primary-care capitation changes the savings argument

**Source/status:** FRESH. SHA official “Benefit Tariffs” webpage, accessed 2026-09-25. No reliable publication/effective date identified in the page text. Treat it as the website's published description on the access date, not a verified signed contract or Gazette instrument.

**URL:** https://www.sha.go.ke/benefit-tariffs/

**Exact excerpts, Primary Healthcare Fund outpatient access rules:**

> All registered beneficiaries will be mapped to a Primary Care Network (PCN) at the point of registration, where they can access services in any facility within their Primary Care Network.

> The global budget capitation shall be allocated based on the population in the Primary Care Network (PCN).

> Distribution of the Funds shall be done at the end of the month based on patient visits, weighted by disease treated.

**Locator:** `evidence/sha-benefit-tariffs.txt:78-96`. The same section lists level 2, level 3, and select contracted level-4 facilities as access points. It lists consultation, prescribed investigations, treatment, and other outpatient services.

**Exact excerpt, ambulance access point:**

> Management of all transfers/evacuations through National & County Ambulance Call Centres.

The webpage describes evacuation to an accident-and-emergency facility and transfer for further clinical care. `evidence/sha-benefit-tariffs.txt:982-990`.

**Economic implication — ANALYSIS:** Under a population-based budget, avoiding one unnecessary visit is not automatically a reduction in the payer's cash outlay. It may release staff time or supplies, change facility allocations, or reduce household burden. Model the actual marginal resource and payment changes. Count the costs of software, integration, training, support, follow-up, and additional appropriate care. Do not multiply visits avoided by a tariff and call the result savings.

**Limit:** The webpage includes many numeric tariffs and service categories. This task does not authorize using those numbers as Tunza pricing, observed costs, or guaranteed payment. Effective tariff version, local provider contract, claims adjudication, and current benefit application still need confirmation. A published ambulance pathway does not prove an available vehicle, reachable call centre, or Tunza dispatch access.

## S09. Data use, system access, and certification require separate assessment

**Sources/status:** FRESH. Data Protection Act, No. 24 of 2019, retrieved consolidated version 2022-12-31. Digital Health Act, No. 15 of 2023, retrieved version 2023-11-24. Both accessed 2026-09-25. The DHA portal was also fetched, but exposed only an application shell.

**URLs:**
- https://new.kenyalaw.org/akn/ke/act/2019/24/eng@2022-12-31
- https://new.kenyalaw.org/akn/ke/act/2023/15/eng@2023-11-24
- https://certification.dha.go.ke/

**Exact excerpts:**

DPA section 25(c):
> (c)collected for explicit, specified and legitimate purposes and not further processed in a manner incompatible with those purposes;

DPA section 31(1):
> (1)Where a processing operation is likely to result in high risk to the rights and freedoms of a data subject, by virtue of its nature, scope, context and purposes, a data controller or data processor shall, prior to the processing, carry out a data protection impact assessment.

DPA section 42(3):
> (3)Where a data processor processes personal data other than as instructed by the data controller, the data processor shall be deemed to be a data controller in respect of that processing.

DPA section 49(1):
> (1)The processing of sensitive personal data out of Kenya shall only be effected upon obtaining consent of a data subject and on obtaining confirmation of appropriate safeguards.

Digital Health Act section 6(m):
> (m)certify digital health solutions based on best practices and standards;

Digital Health Act section 22:
> The Agency shall be the custodian for all health data in Kenya.

**Locators:** `evidence/data-protection-act.txt:268-277`, `:313-340`, `:434-444`, `:477-506`; `evidence/digital-health-act-current.txt:115-131`, `:258-281`, `:336-341`.

**Supported use:** The law distinguishes purposes, authority, safeguards, and data roles. A proposed pilot should document the actual controller/processor arrangement, permitted fields and uses, clinical responsibility, retention, onward disclosure, hosting, and required review. DPA section 30 includes lawful bases other than consent, and section 53 provides conditions for research use. Do not simplify all uses to “consent alone makes it legal.” Health-data conditions appear in section 46. Application to a specific study or vendor requires review.

**Correction to upstream assumptions:** “All eCHIS data is MoH property” is not a sufficient legal characterization. The Digital Health Act names DHA as custodian and contains additional Cabinet Secretary/controller provisions. Likewise, “training always makes Tunza a controller” is overbroad. Actual purpose, means, and instructions matter.

**Limit:** This does not determine whether a specific shadow evaluation is research requiring ethics/NACOSTI review, whether certification is required for that exact design, or whether a particular overseas inference service is permissible. No Tunza certification, data-sharing agreement, authorized credentials, or training permission was inspected. A general Ministry research-use statement in S05 grants none of these to Tunza.

## S10. National investment figures are context, not Tunza distribution

**Sources/status:** FRESH. MoH community-health page published May 19, 2026 and UHC retreat page published January 29, 2026, event January 28. Accessed 2026-09-25.

**URLs:** https://www.health.go.ke/node/2374 and https://www.health.go.ke/health-cs-outlines-uhc-reforms-national-assembly-retreat

**Exact excerpts:**

> The PS noted that the The government is supporting over 107,000 Community Health Promoters with monthly stipends, digital devices, and medical kits to strengthen disease prevention, early detection, referrals, and household-level healthcare services across the country, while calling for stronger collaboration and sustainable investments to advance the global community health agenda.

> The CS reported major gains in health digitisation, with 10,277 facilities connected to national systems and 30,087 digital devices deployed, as well as strengthened human resources for health, anchored by 107,000 Community Health Promoters and improved UHC staff remuneration under SRC rates.

**Locators:** `evidence/community-health.txt:74-80`; `evidence/uhc-reforms.txt:74-82`.

**Supported use:** Attribute the figures to those dated Ministry statements. They show existing national investment.

**Limit:** Not verified installed coverage at every site, a Tunza addressable signed market, or available partner capacity. The May 19 page does not substantiate nine-million-household reach. The old essay's May 28 newsletter link was not freshly read because the PDF exceeded the retrieval cap. Use the May 19 source explicitly instead of silently changing its attribution.

## S11. WHO context and its interpretation limits

**Source/status:** CACHED. WHO Kenya Country Office 2025 Annual Report. Cached HTTP Last-Modified April 13, 2026, retrieval September 24. PDF rehashed and all 82 pages freshly extracted September 25. Hash matches the earlier audit. No new WHO network fetch was made.

**URL:** https://www.afro.who.int/sites/default/files/2026-04/WHO%20Kenya%20Annual%20Report%202025.pdf

**Exact excerpts, whitespace normalized:**

Printed p. 60:
> Despite these gains, maternal mortality remains high at an estimated 355 deaths per 100,000 live births.

Printed p. 67:
> However, significant gaps remain, with a 46% shortage of nurses and 92% shortage of doctors. The current workforce meets only 76.4% of estimated need.

Printed p. 73:
> This 'hub and spoke' structure utilizes Level 4 facilities as hubs to coordinate with Level 2 and 3 spokes and Level 1 community units.

**Locators:** `evidence/who-2025.txt:2800-2806`, `:3116-3122`, `:3422-3429`. Printed pages differ from physical PDF page numbers. Provenance and PDF hash: `evidence/who-cache-provenance.json`.

**Supported use:** Maternal mortality remains a dated national-context estimate. The doctor-shortage phrase is genuinely present in the source, resolving the previous verification disagreement.

**Limit:** Doctor-shortage methodology and denominator were not established by this passage. Do not equate the percentage with vacant funded posts, derive a county staffing ratio, or present it as a Tunza capacity measurement. Do not derive daily maternal deaths or attribute deaths to eCHIS ordering. These statistics are optional background, not proof of the proposed product's effect.

## S12. Samples and transport require service-specific evidence

**Source/status:** CACHED WHO 2025 report, freshly extracted as in S11.

**URL:** WHO URL under S11.

**Exact excerpts, whitespace normalized:**

Printed p. 16, polio surveillance:
> With the WHO and Gates Foundation support, a newly upgraded laboratory at KEMRI now conducts virus isolation, molecular testing, and genomic sequencing locally.

Printed p. 47:
> The package includes 14 fully equipped ambulances, eight advanced life-support units for national referral hospitals and six for maternal health services in high-burden counties including Marsabit, Samburu, and Tana River.

**Locators:** `evidence/who-2025.txt:792-808`, `:2217-2228`. S04 separately confirms that specimens and specialist expertise were within the referral-policy discussion.

**Supported use:** Different tasks require different operators. Arranging sample transport is not the same workflow as arranging patient transport, and returning a result is not the same as a clinician acknowledging and acting on it. This final sentence is design analysis, not a measured program effect.

**Limit:** The KEMRI example concerns a specific surveillance program, not routine blood-test turnaround in every county. The ambulance donation is not evidence of national vehicle availability or a dispatch integration. Keep sample/result/vaccine coordination as proposed unless service-level agreements and current capability data establish the chosen pilot can support it.

## U1–U8. Unresolved questions that constrain the build and economics

| ID | Unknown | Required evidence or decision |
|---|---|---|
| U1 | Exact missing function in deployed eCHIS | Authorized walkthrough and current forms/configuration covering urgency, worklists, acknowledgement, counter-referral, and outcomes. Do not infer absence from silence in public material. |
| U2 | First pathway and actual network readiness | Local clinical/service-owner selection, staffing and facility capability checks, baseline workflow observation. Named counties in national sources are not Tunza commitments. |
| U3 | Administrative and patient burden | Baseline staff minutes, repeated entries/calls, transport attempts, household expenses, and completed/unknown outcomes for all eligible cases. |
| U4 | Fiscal savings and buyer | Current provider payment contract, paid claims where relevant, county budget/procurement route, avoidable variable costs, and full implementation/maintenance costs. Capitation rules prevent a simple avoided-visit-times-tariff calculation. |
| U5 | Legal and governance route | Current judicial/regulatory status, responsible controller and service owner, lawful processing basis, data-use agreement, ethics/research classification, certification applicability, hosting/transfer review. |
| U6 | NGO contribution versus alternatives | Named operational responsibilities, funding, existing county relationship, and comparison with direct county/provider entry. No NGO is inherently necessary. |
| U7 | Clinical and operational pilot gates | Locally approved protocol, emergency escalation, validation targets, stop criteria, independent disagreement review, and an accountable person able to halt use. No numerical clinical thresholds invented here. |
| U8 | ML labels and outcome learning | Defined target, timestamped inputs, clinically reviewed labels, active authorized follow-up including non-completers, missing-outcome treatment, held-out evaluation, and separate permission for any training. A completed status is not proof that the original decision was correct. |

## D1–D4. Analysis boundaries for the next tasks

- **D1:** Consider one existing network and one referral pathway, with a responsible actor and authoritative confirmation at each step. This is a recommendation to validate locally, not a chosen county or approved clinical intervention.
- **D2:** Measure administrative work, time to appropriate care, and completed handoffs separately. An acknowledgement is not arrival, treatment, or a favorable clinical outcome.
- **D3:** Keep clinical urgency separate from capacity. An unavailable facility requires a defined escalation or alternative, not reclassification of an urgent case as non-urgent. Financing checks must not become a software barrier to emergency care.
- **D4:** Report staff capacity, household burden, and public expenditure separately. Better access may increase appropriate care and near-term spending. The value claim can be more completed appropriate care per available resource without promising a budget cut.
