# WRITING-CONTRACT — urgent Tunza set

Dated 2026-09-24. Task 1.b (glm). This is the shared spine for the three urgent pages. Every page writer follows it. The audit (4.a) checks against it. Inputs: `prompts/tunza-vision-2026-09-23/fact-sheet.md` (fact base), `inventory-verdict.md` and `decoded/` in this folder (task 1.a).

Scope guard: write only inside `prompts/tunza-vision-2026-09-24-urgent/`. Do not touch `prompts/tunza-vision-2026-09-23/`, the Downloads PDFs, `/Users/evanmotovich/code/Tunza`, or the second-brain vault. No commits, no sending, no outreach.

## 1. Stake lock

These sentences, or their plain restatement per audience, open every page. Word-level source: the eCHIS gap is his line (`/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:28`); the death sits on the unordered queue, never on Tunza's absence as a product result.

> eCHIS does not say which sick child goes first. The child who waits can die before anyone sees them. Tunza has to exist as the missing decision layer before the clinic. The demo does not do this yet.

Rules on the lock:

- The last sentence stays in every page in some form. The demo does not order the queue today. Removing it converts the stake into a false claim.
- "People die" is only ever about the current state of care: recognized danger without ordering, referral handoffs that fail, facilities that cannot serve the person who arrived. Never "people die without Tunza" as a measured product counterfactual.
- No invented mortality numbers. No deaths-prevented, no per-day counts, no lives saved. The Kenya brief's own footer discipline carries over: no clinical-performance claim.

## 2. The one rule: heat the problem, never the product

Every urgent sentence cites the status quo. Zero urgent sentences about Tunza's demonstrated effect.

Allowed heat, with its citation:

- eCHIS does not order which sick child goes first. (`QUERY-tunza-model-design.md:28`)
- The six referral failure modes: wrong clinical decision, wrong place, facility could not provide the service, patient could not travel, referral never acknowledged, result never came back. (`/Users/evanmotovich/code/Tunza/README.md:51-56`)
- Kenya wrote a national referral policy focused on continuity, interoperability, accountability; the policy cannot execute if the first decision is still guesswork. (Kenya MoH referral-policy links, `decoded/e16739b3-33a4-4cf7-a7ed-cdcc8bb02fc1.decoded.txt` lines 10, 18, and the link annotations to `health.go.ke`)
- The demo's own honest limits, stated once per page, not repeated as apology: rules are a demonstration, not clinically validated; cases stay in the browser; referral facilities in the demo are fake. (`prompts/tunza-vision-2026-09-23/fact-sheet.md`, Confirmed section)

Forbidden heat: any sentence that makes Tunza the subject of a safety, speed, or life outcome. Tunza is the subject of intent ("being built to", "has to exist as"), never of result ("makes care safer", "prevents delay" as done fact).

## 3. Voice override — explicit and bounded

The 2026-09-23 contract said "Do not heat it up. No pitch voice." (`prompts/tunza-vision-2026-09-23.md:49-51`) Evan cancelled that on 2026-09-24 for this set: "more urgent, more like we need tunza or people die it has to be exists."

The override is bounded:

- Voice may burn. Facts may not inflate. A sentence is urgent because of what the status quo does, not because of an adjective attached to Tunza.
- The old set stays cooled. `prompts/tunza-vision-2026-09-23/` files are not edited; the new voice lives only in this folder.
- The Kenya Clinical Vision Brief (decoded here) is a fourth document aimed at clinicians. It is comparison material, not a template. Where it and this contract disagree, this contract wins.

## 4. Forbidden list

Carried over from `prompts/tunza-vision-2026-09-23/fact-sheet.md` section Forbidden. Naming them here is the ban, not permission.

- A trained model, owned weights, or "the public app is Anthropic." The public rules are a keyword demonstration. No model is trained, no weights are owned.
- A signed NGO, a named county as fact, or a partnership he already has. The NGO line was "i would."
- Clinical benefit, diagnostic certainty, or regulatory clearance. The rules are not clinically validated. The disclaimer cite stands.
- A moat. "The only gap." Unique AI insight.
- The energy thesis. Any "500 billion" / "500B" line. Shop names: Renaissance, Two Sigma, Jane Street, HRT.
- Solomon.
- The uncited 100,000-promoter and 9-million-household figures, including "100k" and "9M".
- An invented origin story. The clinic-door scene is the product situation, not how he thought of it.
- An invented discount, rate, amount, or instrument.
- Sending the investor page.
- Copying README lines 62-81 into a page.

Additions from the 1.a inventory (`inventory-verdict.md` F4). These came out of the decoded Kenya brief or Set A and must not enter the pages:

- The "107,000+ CHPs" figure. Same family as the banned 100k; not inherited until a checked MoH citation exists. Do not use 9M either.
- The Kenya brief's effect phrasing ("strengthen decision quality", "safer, faster and more accountable", "next clinically appropriate action", "clinically disciplined layer") as achieved benefit. Intent phrasing only.
- "Tunza is DHA-certified" or any clearance implication. `certification.dha.go.ke` is a portal for a process. If the render keeps the MoH/DHA links, they are labeled reference links, not endorsements.
- Model-based operating language ("compare Tunza's recommendations", "AI should support structured reasoning") as current capability. The demo is rules.
- Any county, facility, or clinician named as secured. Hypothetical evaluators only.
- "More valuable as the system connects" as a moat in softer clothes.
- Set A material: README feature list (voice/image/vitals/outbreak/PWA bullets), Anthropic-as-engine, "NGO relationship is the moat", "a miss costs a child."

## 5. Per-page briefs

All three pages: plain English, short sentences, labeled blocks. First 80-120 words carry the stake and "has to exist" (or exact-equivalent). Facts from the fact sheet only; no new claims; missing evidence is UNKNOWN.

1. `friend.md` — reader: someone who already likes Evan.
   Order: stake, then what the public demo lets a person do (compressed, code-backed), then what he still does not know. No ask. The demo block keeps one honest-limits line. 1-2 pages.
2. `general.md` — reader: someone who wants the company in one sitting.
   One page. Stake first. Who it is for: household, CHP, facility. Mechanics compressed to a few lines — the current 2026-09-23 general page spends most of its space on gates, voice fallbacks, and browser storage; that structure is rejected here. Intention marked as intention ("designed", "we want", never "we have"). No raise, no ask.
3. `investor-unsent.md` — reader: a check-writer who will argue with the strategy.
   Line one, verbatim: `Terms are not set. Do not send this.`
   Five term fields stay blank: instrument, amount, discount or rate, what the earliest partner may join, what they do not get.
   Stake section may burn; ask section stays cold. The three proposals unchanged: one county introduction, a data-rights page, a shadow period where patients are not the test. The four open questions stay questions: label, data rights, one product or two, precision floor. Urgency never manufactures an amount, a discount, or a deadline on money.

## 6. Validation checklist (for audit 4.a and render check 5.b)

- [ ] First 80-120 words of each page contain the queue stake and "has to exist" (or exact-equivalent).
- [ ] No page says or implies: the demo has saved or will save a life, is certified, has a signed NGO or named county, owns or is a trained model, has a moat.
- [ ] Forbidden-list scan (section 4, both halves) returns zero matches, including 107,000 / 100k / 9M / 500B / Solomon / shop names.
- [ ] Every hot sentence's subject is the status quo; Tunza is subject only of intent.
- [ ] Honest-limits block present once per page: not a doctor, not a diagnosis, rules not clinically validated, cases on-device, demo facilities fake.
- [ ] Investor line one verbatim; five term fields empty; three proposals intact; four questions open.
- [ ] `general.md` fits one rendered page; friend and investor max two.
- [ ] Originals unchanged: `prompts/tunza-vision-2026-09-23/`, Downloads PDFs, `/Users/evanmotovich/code/Tunza`, vault.
- [ ] MoH/DHA links, if kept, labeled as reference links, not endorsements or clearance.
- [ ] No number anywhere in the pages that is not already sourced in the fact sheet or this contract.

---
Governed by the task 1.b delegation. The architect owns interpretation disputes; escalate before inventing.
