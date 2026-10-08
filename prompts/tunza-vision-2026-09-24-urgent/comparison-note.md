# Comparison note — Kenya Clinical Vision Brief vs the cooled Tunza pages

Dated 2026-09-24. Comparison target: the decoded two-page `Tunza - Kenya Clinical Vision Brief` against the 2026-09-23 friend, general, and unsent-investor pages. The brief is a fourth document. It is not one of those three pages. (`inventory-verdict.md:23-36`)

## What the Kenya brief adds

### A1 — A sharper transition-into-care frame

The brief locates the problem before formal care: deciding what should happen before arrival, preserving context through the transition, and learning whether the care path resolved. (`decoded/e16739b3-33a4-4cf7-a7ed-cdcc8bb02fc1.decoded.txt:17-19`)

That adds a useful structure to the cooled pages’ simpler “what happens next” framing. It connects three stages without claiming they work today:

1. decision before arrival;
2. continuity through referral;
3. outcome returned after care.

The existing product evidence remains narrower: the demo uses fake referral facilities and stores case state in the browser. (`prompts/tunza-vision-2026-09-23/fact-sheet.md:37,39`)

### A2 — National referral-policy framing

The brief places the idea beside Kenya’s stated direction in community health, referral coordination, digital infrastructure, and interoperability. It specifically describes a Ministry of Health referral-policy process centered on continuity, digital interoperability, and accountability. (`decoded/e16739b3-33a4-4cf7-a7ed-cdcc8bb02fc1.decoded.txt:23-27,45-47`)

The PDF annotations point to two Ministry of Health pages:

- `https://www.health.go.ke/node/2374`
- `https://health.go.ke/kenya-moves-strengthen-patient-referral-system-through-new-national-policy`

Those are public-context references. They do not show that Tunza is integrated with eCHIS, adopted by the Ministry, endorsed by government, or attached to a signed partner. (`inventory-verdict.md:42-46`; `prompts/tunza-vision-2026-09-23/fact-sheet.md:69-73,97`)

### A3 — DHA certification-process context

The brief says the Digital Health Agency certifies digital health systems against functionality, security/privacy, reporting, and interoperability standards. (`decoded/e16739b3-33a4-4cf7-a7ed-cdcc8bb02fc1.decoded.txt:24-27,45-47`)

**Required flag:** `https://certification.dha.go.ke/` is a certification portal/process. It is not evidence that Tunza is certified, cleared, approved, endorsed, submitted, or under review. The portal may be retained only as a labeled reference link. (`inventory-verdict.md:46,107`; `prompts/tunza-vision-2026-09-23/fact-sheet.md:98`)

### A4 — A staged proof path rather than a deployment claim

The brief labels itself a discussion draft, disclaims a clinical-performance claim, and says patient-facing use requires validation and applicable approvals. (`decoded/e16739b3-33a4-4cf7-a7ed-cdcc8bb02fc1.decoded.txt:13,52`)

It then proposes predefined evaluation criteria and local review, followed by clinical design review, silent evaluation without changing patient management, a narrow pilot only after thresholds are met, and an evidence package before expansion. (`decoded/e16739b3-33a4-4cf7-a7ed-cdcc8bb02fc1.decoded.txt:67-71,89-102`)

This is proposed process. It is not proof of a current recommendation system, pilot, partner, facility deployment, safety threshold, or clinical result.

## What the cooled pages correctly refused to claim

### C1 — No current clinical effect

The cooled fact sheet says the public rules are a demonstration and are not clinically validated. It forbids clinical benefit, diagnostic certainty, and regulatory clearance. (`prompts/tunza-vision-2026-09-23/fact-sheet.md:31,94-98`)

The Kenya brief uses effect-shaped language such as “strengthen decision quality,” “safer, faster,” “clinically appropriate,” and “clinically coherent.” (`decoded/e16739b3-33a4-4cf7-a7ed-cdcc8bb02fc1.decoded.txt:20-21,28-32,108-112`)

Do not import those phrases as achieved Tunza effects. At most, convert them to explicit intent: “being built to,” “designed to test,” or “we want to learn whether.”

### C2 — No current AI recommendation system

The brief describes “clinician-guided, model-bounded” operation and proposes comparing Tunza recommendations against normal care. (`decoded/e16739b3-33a4-4cf7-a7ed-cdcc8bb02fc1.decoded.txt:63-66,91-98`)

The cooled evidence says the public app uses demonstration rules, not a clinically validated model. A model, owned weights, or Anthropic as the public app remain forbidden claims. (`prompts/tunza-vision-2026-09-23/fact-sheet.md:31,69-70,94-96`)

### C3 — No partnership, county, facility, or endorsement

The brief asks Kenyan clinicians to pressure-test assumptions and describes hypothetical county teams and defined facilities in a later pilot. (`decoded/e16739b3-33a4-4cf7-a7ed-cdcc8bb02fc1.decoded.txt:54-58,84-88,96-98`)

The cooled fact sheet correctly keeps any NGO connection as a wish, not a signed agreement, and forbids a named county or existing partnership. (`prompts/tunza-vision-2026-09-23/fact-sheet.md:71,97`)

### C4 — No moat or network-effect claim

The brief says Tunza could become more valuable as the health system becomes more connected. (`decoded/e16739b3-33a4-4cf7-a7ed-cdcc8bb02fc1.decoded.txt:43-44`)

The cooled fact sheet forbids a moat, “the only gap,” and unique-AI-insight claims. (`prompts/tunza-vision-2026-09-23/fact-sheet.md:99`)

### C5 — No unsupported scale number

The brief includes a Community Health Promoter headcount in its policy-context paragraph and footer. (`decoded/e16739b3-33a4-4cf7-a7ed-cdcc8bb02fc1.decoded.txt:23-24,45`)

That figure was not independently checked during this task and does not enter the urgent fact sheet. The older cooled fact sheet already barred the related uncited promoter and household figures. (`inventory-verdict.md:105`; `prompts/tunza-vision-2026-09-23/fact-sheet.md:101`)

## What neither document establishes

- The Kenya brief does not say that a child dies, does not say Tunza has to exist, and does not state the eCHIS case-ordering gap. (`inventory-verdict.md:36,95`)
- The eCHIS ordering gap comes from Evan’s grilling answer: no acuity and no system determining which sick child goes first. (`/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:28`)
- The allowed evidence does not connect that gap to a documented death, mortality rate, or measured Tunza counterfactual. The supported stakes are an unordered queue, wrong decisions, wrong destinations, unavailable services, inability to travel, unacknowledged referrals, missing returned results, delay, escalation, and false reassurance. (`/Users/evanmotovich/code/Tunza/README.md:51-56`; `decoded/e16739b3-33a4-4cf7-a7ed-cdcc8bb02fc1.decoded.txt:30-32,79-81`; `fact-sheet-urgent.md:11-20`)

## Writing decision for the urgent set

Use the Kenya brief’s referral-policy and transition framing as context. Use the eCHIS ordering gap and six referral failures as the urgent problem. Keep the demo’s limits explicit. Treat the DHA URL as a portal, not clearance. Do not state “the child who waits can die” as documented fact unless a permitted primary mortality source is added; under the current evidence it is **UNKNOWN**.

The strongest supported line is:

> eCHIS does not order which sick child goes first. The care path can then fail at the decision, destination, facility, travel, acknowledgement, or returned-result step. Tunza has to exist as an attempt to solve that gap. The demo does not do this yet.

The first two sentences are status-quo claims backed by `/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:28` and `/Users/evanmotovich/code/Tunza/README.md:51-56`. The third is intent, not a measured effect. The fourth preserves the product boundary in `prompts/tunza-vision-2026-09-23/fact-sheet.md:31,37,39,72-74`.
