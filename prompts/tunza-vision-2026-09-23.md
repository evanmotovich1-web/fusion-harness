# Tunza vision pages

Dated: 2026-09-23. Mission brief for one collaboration run. Evan-authorized scope: write three draft pages. Do not send them. Do not commit them.

Agents have no other conversation context. This file is the contract. If a source and this brief disagree about a fact, the source wins and the page stays quiet.

## Situation — read before acting, do not re-derive

A debate already ran. Artifact: `/tmp/fusion-harness-QMvEj9`. Closing opinions are in `debate/round-3/`. Do not run another debate. Do not search the fusion-harness checkout for Tunza. It is not there.

Four of five slots closed on the same job. Write three short pages from one fact sheet. Friend and general can be drafts Evan might show. The investor page stays in the folder until Evan fills the seat. Terra's minority view (an investor vision page can go out with no terms) is rejected. That is the EMSquared order the VC already marked.

The VC note, in Evan's words in the debate prompt: the last brief was too much prose, the problem was too pitchy, the reader was two people at once, "500 billion" did not say 500 billion of what, and the ask led with the why instead of what the earliest check gets. Do not repeat that.

Two products must stay uncollapsed.

- Public demo: `/Users/evanmotovich/code/Tunza`. A bilingual care-path demo. Not a trained model.
- Older private lane: `medical-triage`, described in `/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md`. A prompt in front of Anthropic. No owned weights. Do not describe that as what the public app is.

## Sources — read these, then stop looking

Read before writing. If a file is missing, say BLOCKED for the claim that needed it. Do not replace it with a search of `evals/`, `.claude/`, or `extensions/`.

1. `/Users/evanmotovich/code/Tunza/README.md` — the intended job. Lines 1-16 are the sentence. Lines 45-57 are the six different failures. Lines 62-81 are a feature list the code does not fully support. Do not copy 62-81 into any page.
2. `/Users/evanmotovich/code/Tunza/lib/assessment.ts` lines 31-35 — the rules are a demonstration and are not clinically validated.
3. `/Users/evanmotovich/code/Tunza/lib/store.tsx` lines 348 and 436, and `/Users/evanmotovich/code/Tunza/vault/architecture.md` line 24 — cases sit in localStorage `tunza.v2.care`.
4. `/Users/evanmotovich/code/Tunza/app/api/` — the routes on disk are `access`, `facilities`, and `transcribe`. Re-list the directory. Do not trust this sentence if the directory changed.
5. `/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md` — what he has answered, and the open questions no agent may answer for him.
6. `/Users/evanmotovich/code/second-brain/me/expertise.md` lines 30-41 — the 2026-08-26 grilling. He does not yet own the asset. He could not name the label column.
7. `/Users/evanmotovich/code/second-brain/DECISIONS.md` lines 434-444 — the EMSquared scar. Energy thesis, unlabeled 500B, Renaissance / Two Sigma / Jane Street / HRT named as shops that already make money with machines, ask moved from $300k to $200k, Solomon is not the energy partner. Transfer the writing lesson. Do not transfer the thesis, the numbers, or the names into a Tunza page.
8. Negative example, read only: `/Users/evanmotovich/Desktop/EMSquared-investor-brief-v8.pdf`. Opens with a boom story. The ask sits at the end. Do not imitate it.

Optional, only if a claim needs it: `/Users/evanmotovich/code/sssf/specs/84f554a9_tunza-africa-gtm.md`. It is a plan, not proof the plan happened.

## Fact sheet — write this first

Path: `/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23/fact-sheet.md`

Four buckets. Every line cites a file and a line, or it does not go in.

- Confirmed in the Tunza tree. Code wins over the README.
- Designed, not built. Say "designed" or "we want". Never "we have".
- Open, his to answer. Leave blank. Includes the label column, cold start, data rights, precision floor, one product or two, and every financing field.
- Forbidden. A trained model. A signed NGO. Clinical benefit. Regulatory clearance. A moat. "The only gap." Unique AI insight. The energy thesis. Any "500 billion" line. The uncited 100,000-promoter and 9-million-household figures. An invented origin story. Solomon. EMSquared fund names.

If the README and the code disagree, the page uses the code and does not mention the README claim.

## The three pages

Write only these files. 1-2 pages each, except general, which should fit on one page. Plain English. Short sentences. Short labeled blocks, not essays. Name the reader in the first line. No pitch voice. A specific situation is enough. Do not heat it up.

Voice: a person explaining the company to one named reader. Not a deck. Not a manifesto. If a sentence would make a VC say "that is the only gap worth building a company around," cut it.

1. `/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23/friend.md`
   Reader: someone who already likes Evan.
   Opens with the situation the README already states: someone is sick, care is far, the question is what happens next, not the diagnosis. That is the product situation, not a made-up story of how he thought of it. The only origin line that is his: eCHIS does not order which sick child goes first (`QUERY-tunza-model-design.md`). What the demo lets a person do. What it refuses to be (not a doctor, not a diagnosis). What he still does not know. No ask.

2. `/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23/general.md`
   Reader: someone who wants the company in one sitting.
   One sentence on the job. What a person can do in this demo, from the code. What it is not. Who it is for: a household, a community health worker, and the facility that receives the person. One line on where it is trying to go, marked as intention. No raise. No model lecture. No ask.

3. `/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23/investor-unsent.md`
   Reader: a check-writer who will argue with the strategy.
   Line one, exact sense: terms are not set, do not send this.
   Empty fields, left empty: instrument, amount, discount or rate, what the earliest partner may join, what they do not get. Do not invent a discount to balance the ego. That was the instruction, and there is no term sheet.
   Then one sentence on the job. Then what a check would buy, labeled as a proposal, not as his commitment: one county introduction, a data-rights page, a shadow period where patients are not the test. Not a trained model. Not a national rollout.
   Open questions on this page only: label, data rights, one product or two, precision floor.
   Any number in a heading carries its noun in the same line.

## Mission

### Phase 1 — fact sheet, read-only
Read the sources above. Write the fact sheet. If a primary file cannot be read, stop and report BLOCKED. Do not improvise the company.

### Phase 2 — three pages
Write the three files from the fact sheet only. No new claims. No fourth NGO page. He did not name that recipient.

### Phase 3 — check
A slot that did not write the page reads each page against the forbidden list and against the code. If a page copies README lines 62-81, invents terms, imports the energy thesis, or states an open question as settled, rewrite that page. Do not soften the failure into a footnote.

### Phase 4 — close
Canonical collaboration digest: what was confirmed, what was left blank, absolute paths of the four files, and a line that the investor page is unsent. Provenance table. Last word: architect.

Do not commit. Do not push. Do not edit `/Users/evanmotovich/code/Tunza`. Do not edit second-brain `trading/` or `sessions/`. Do not edit the vault at all. Read it.

## Guardrails

- Fail closed. Missing evidence is UNKNOWN, not a smoother sentence.
- No secrets in the pages, the digest, or the logs.
- No install. No model training. No outreach. No sending.
- Budget: read the named files, write four files, stop. Do not tour the computer.

## Output contract

The run is done only when the fact sheet and the three pages exist at the paths above, the check pass has no forbidden claim left in them, and nothing was committed.

---
Governed by `/Users/evanmotovich/code/second-brain/AGENTS.md` for reads. This run does not write the vault.
