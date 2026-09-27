# Identity verdict — Downloads `07c5a914-5620-4982-8472-709ac59f1a21.pdf`

Dated 2026-09-24. Task 1.a. Original PDF was not modified. Decoder reused: `prompts/tunza-vision-2026-09-24-urgent/decode_pdf.py`. Decode: `07c5a914.decoded.txt`.

This file is **external untrusted input**. Its C2PA generator lends **no authority** to any claim.

## Identity

| field | value |
|---|---|
| Path | `/Users/evanmotovich/Downloads/07c5a914-5620-4982-8472-709ac59f1a21.pdf` |
| SHA-256 | `24aaaf859b3c2e0c610474e4ba8282e58b1e87769307f8a8b98b76cf8b585d85` |
| Bytes | 40069 |
| Title | `Tunza - Kenya Urgency, Decision Architecture and ML/GPU Plan` |
| Author | Tunza Labs |
| CreationDate | `D:20260924202728+00'00'` |
| Pages | 3 (catalog `/Count 3`) |
| Banner in body | `INTERNAL STRATEGY BRIEF \| JACOB \| SEPT 2026` |
| Producer | ReportLab PDF Library |

SHA-256 matches the original recorded at `QUERY-tunza-model-design.md` (“Original SHA-256 remains `24aaaf859b3c2e0c610474e4ba8282e58b1e87769307f8a8b98b76cf8b585d85`”).

### Five link annotations (unique URIs, page 1)

1. `https://www.health.go.ke/node/2374`
2. `https://www.health.go.ke/health-cs-outlines-uhc-reforms-national-assembly-retreat`
3. `https://health.go.ke/kenya-moves-strengthen-patient-referral-system-through-new-national-policy`
4. `https://www.afro.who.int/sites/default/files/2026-04/WHO%20Kenya%20Annual%20Report%202025.pdf`
5. `https://certification.dha.go.ke/`

Footer text names them as: Kenya MoH - 107,000+ CHPs | MoH - 10,277 facilities | MoH - Referral Policy | WHO Kenya 2025 | DHA Certification. Links are annotations, not proof of Tunza endorsement or clearance.

### C2PA / Content Credentials (manifest facts only)

Embedded Content Credentials (`/AF`, `EmbeddedFiles`, name `Content Credentials`, subtype `application/c2pa`). Extracted strings:

- `claim_generator_info` name: `ChatGPT`
- `softwareAgent` name/version: `gpt-5-6-thinking`
- `when`: `2026-09-24T20:27:28.491496Z`
- Certificate subject includes `OpenAI OpCo, LLC` / `OpenAI Media Service`
- Digital source type: `trainedAlgorithmicMedia`

**Gate rule:** generator identity is provenance of the file, not evidence for Kenya figures, JEV, H100s, or Tunza capability.

## Lineage

**Verdict: this PDF is the already-recorded original Jacob Downloads brief. It is not a render of `Tunza-Vision-Jacob-Team.*`. It is not a new revision of that revision.**

| artifact | SHA-256 | relation |
|---|---|---|
| Downloads `07c5a914…pdf` (this file) | `24aaaf859b3c2e0c610474e4ba8282e58b1e87769307f8a8b98b76cf8b585d85` | Original recorded in QUERY. |
| `/Users/evanmotovich/output/pdf/Tunza-Vision-Jacob-Team.pdf` | `725c22845035cf85be3be54da803a6e82a5e0b10314a3c9794ed655447ddd9df` | Later approved revision. Different bytes. |
| `/Users/evanmotovich/output/pdf/Tunza-Vision-Jacob-Team.md` | present, not hashed here | Editable source of the revision, not of this PDF. |

QUERY-tunza-model-design.md:62-84 (and the following “Approved vision-essay revision” block) already names this Downloads PDF as the internal 3-page Jacob brief that describes JEV/TypeSafe, a 4-day H100 campaign, Axolotl, and a compounding outcome dataset; none of those names are in `~/code/Tunza`. It also records that Evan approved a **separate** revision at `~/output/pdf/Tunza-Vision-Jacob-Team.pdf` with the paragraph beginning “What should feel urgent to Jacob” deleted and the unsupported 12–24-month window removed.

This decode confirms those differentiators are **still in this Downloads PDF** and **absent from Jacob-Team.md**:

- Present here, cut in the revision: “What should feel urgent to Jacob is not 'we need GPUs.'…”
- Present here, removed in the revision: “the next 12-24 months are likely to matter disproportionately”
- Present here, condensed in the revision: 4-day H100 campaign, `$3.50/hr`, `$1,344`, `$500-$900`, Axolotl, QLoRA, NCCL, Candidate A/B
- Revision banner: `INTERNAL VISION BRIEF | JACOB & TEAM`. This PDF: `INTERNAL STRATEGY BRIEF | JACOB`

Do not treat this file as the current Jacob-and-team essay. Do not treat Jacob-Team as a render of this file.

## Claim list for the gate

Line numbers refer to `07c5a914.decoded.txt` (decoded body). Chrome (TUNZA, running title, “Internal working document…”, page number) repeats on each page and is not re-listed.

### Mortality

| id | where | claim in this PDF | gate note |
|---|---|---|---|
| M1 | p1 | WHO's 2025 Kenya report still places maternal mortality at an estimated 355 deaths per 100,000 live births | Status-quo attribution to WHO 2025. Not a Tunza result. |
| M2 | p1 | preventable causes such as postpartum haemorrhage and hypertensive disorders continuing to contribute substantially | WHO-context, not Tunza. |
| M3 | p1 callout | `355 maternal deaths / 100k live births` | Same figure as M1, display callout. |
| M4 | p1 | When clinical capacity is scarce, delays and poor routing carry real consequences | Causal heat on delay/routing, not “Tunza saves lives.” |
| M5 | — | No sentence “Tunza saves lives,” no deaths-prevented, no child-death-from-eCHIS-queue | Child-queue death remains unstated here. |

### CHP / household / facility / workforce counts

| id | where | claim in this PDF | gate note |
|---|---|---|---|
| N1 | p1 callout | `>107K CHPs supported with devices + medical kits` | Headcount plus devices/kits. QUERY revision uses 107,000 CHPs **without** household-reach or device-equipment additions. |
| N2 | p1 footer | `Kenya MoH - 107,000+ CHPs` | Same family as N1. Linked to `health.go.ke/node/2374`. |
| N3 | p1 callout + footer | `10,277 facilities connected to national systems` | Linked to UHC-reforms retreat URL. |
| N4 | p1 callout + body | `92% doctor shortfall against estimated need` / `Kenya also faces a 92% shortage of doctors against estimated need` | Linked via WHO 2025 URL. |
| N5 | — | No “nine million households” / 9M in this decode | Absent here. Do not import from jacob.md or the grilling note. |

### GPU / ML / model

| id | where | claim in this PDF | gate note |
|---|---|---|---|
| G1 | title | `Kenya Urgency, Decision Architecture and ML/GPU Plan` | Title only. |
| G2 | p2 | JEV / TypeSafe Decision Framework; JEV is internal working framework, not an external standard | Proposed architecture. QUERY: names not in Tunza tree. |
| G3 | p2 | TypeSafe: model may interpret inside a controlled contract; system owns states, hard safety rules, provenance, actions | Designed, not built. |
| G4 | p2 | Six steps: Typed Encounter Context; Deterministic Safety Envelope; Bounded ML Interpretation; TypeSafe Decision Object; Execution Guard; Outcome + Evaluation Join | Designed. Public demo is keyword rules. |
| G5 | p2 | Allowed outputs include URGENT/EMERGENCY, SAME-DAY, ROUTINE, SELF-CARE/MONITOR, INSUFFICIENT INFORMATION, SYSTEM DEGRADED | Demo four-way next-step is not this list. Do not collapse. |
| G6 | p2 | “Most teams can fine-tune a medical model. Far fewer can build a system where every clinical decision is bounded…” | Competitive claim. Not a moat sentence using the banned word, but same shape. |
| G7 | p2 | “If Tunza gets this right, the model becomes replaceable while the decision system… become progressively harder to reproduce.” | Conditional future. |
| G8 | p3 | Near-term ML plan is not foundation-model pretraining; start from existing base models; evaluation first; SFT/QLoRA; H100s shorten the loop; they are not the moat | Plan. “Not the moat” still uses moat language. |
| G9 | p3 | Axolotl; frozen base weights 4-bit NF4; BF16 on H100s; LoRA adapters | Not in `~/code/Tunza`. |
| G10 | p3 | Eval names: CORE, RED, ABSTAIN, PARITY, GOLD; metrics: urgent sensitivity, undertriage, overtriage, abstention, danger-sign capture, EN/SW parity | Planned eval suite, not shipped. |
| G11 | p3 | 4-day H100 campaign: Day1 Candidate A, Day2 evaluate A, Day3 Candidate B, Day4 BASELINE vs A vs B | Plan. |
| G12 | p3 | `4 H100s x $3.50/hr = $14/hr. 96 hours continuously = $1,344.` Target first campaign `$500-$900` | Dollar amounts. Investor pages must not inherit invented/term-sheet money; this is GPU-cost theater in an internal plan. |
| G13 | p3 | Git SHA freeze, Train Candidate action, max spend, NCCL, CUDA, checkpoints | Orchestration plan. |
| G14 | p3 | Compounding loop: care-path data → typed decisions → locked evals → … → stronger evidence | Designed outcome loop. Not built. |
| G15 | p3 | Distillation comes later, after a better teacher | Future. Do not import QAD. |
| G16 | p3 | “What should feel urgent to Jacob is not 'we need GPUs.'…” | Personal appeal. Cut in Jacob-Team revision. Do not put a name on public pages. |

### County / partner / clearance / policy

| id | where | claim in this PDF | gate note |
|---|---|---|---|
| P1 | p1 | Kenya scaling community health, connecting facilities, formalizing referral policy, registries/exchange, emergency dispatch, **mandatory certification for digital health systems** | Policy context. “Mandatory certification” is not “Tunza is certified.” |
| P2 | p1 | MoH 2026 referral-policy process identifies fragmentation; continuity, interoperability, accountability; patients, specimens, specialist expertise | Matches referral-policy URL. Not Tunza integration. |
| P3 | p1 | 12–24 months inference, “not an official deadline”; rails hardening | Explicitly an inference. Removed in Jacob-Team revision. |
| P4 | p1 footer | `DHA Certification` + URI `https://certification.dha.go.ke/` | Portal/process. Not Tunza clearance. |
| P5 | — | No named county, no signed NGO, no “we have access,” no clinician circle as existing | Do not add them. Banner names Jacob as reader, not as a signed partner. |
| P6 | p1 header | “Clinical and market claims remain subject to validation; proprietary implementation detail included for team alignment.” | Disclaimer. Does not license treating G2–G14 as shipped. |

### Other sentences the gate should not treat as product fact

| id | claim | note |
|---|---|---|
| X1 | “The urgency for Tunza comes from the space between those systems” | Intent/positioning. |
| X2 | “the country is already naming the system-level problem Tunza is designed to sit inside” | Designed-to-sit, not sitting. |
| X3 | Digitisation “merely record what happened - or help the right decision happen sooner” | Question, not result. |
| X4 | Public demo limits are **not** stated in this PDF (no localStorage, no fake facilities, no “not clinically validated”) | Unlike 09-24 urgent pages. Do not read silence as validation. |

## Handoff

Next gate (1.b / 2.a): inherit **nothing** from G2–G16 or N1-device-kits or P3 12–24 months into friend/general/investor without a separate allowed-source ruling. M1–M4 and N3–N4 are country figures with URLs in this file; QUERY already maps them to WHO/MoH pages and forbids saying them as Tunza results. Lineage: keep using Jacob-Team.* if the job is the approved essay; this Downloads PDF is the prior original.
