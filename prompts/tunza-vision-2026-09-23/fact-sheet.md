# Tunza fact sheet

Dated 2026-09-23. For the three draft pages only. Do not send them. Do not commit them. (`/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23.md:3`)

If the README and the code disagree, the page uses the code and does not mention the README claim. (`/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23.md:46`)

Do not copy README lines 62-81 into any page. (`/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23.md:24`)

Two products stay separate. The public demo is `/Users/evanmotovich/code/Tunza`. The older private lane is `medical-triage`, described in the grilling note as a prompt in front of Anthropic with no owned weights. Do not describe that lane as what the public app is. (`/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23.md:18`)

PDF limitation: `/Users/evanmotovich/Desktop/EMSquared-investor-brief-v8.pdf` was opened and returned binary PDF, not page text. It is not Tunza evidence. Do not quote it. Do not treat the contract's "boom story / ask at the end" sentence as a verified quotation from the file. (`/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23.md:31`) The writing lesson that is on disk is in `DECISIONS.md`, cited in Forbidden.

API re-list, this run, directory `/Users/evanmotovich/code/Tunza/app/api`: `access/`, `facilities/`, `transcribe/`. Each contains `route.ts`. No other route directory was present.

## Confirmed in the Tunza tree

Code wins. These lines are what a person can do, or what the tree states, in the public demo.

- The intended job, as the README sentence, is the moment someone is sick, care is far, and the question is what happens next, not the diagnosis. That is the product situation, not an origin story. (`/Users/evanmotovich/code/Tunza/README.md:3`, `/Users/evanmotovich/code/Tunza/README.md:5`, `/Users/evanmotovich/code/Tunza/README.md:7`)
- The public app is one Next.js app. v1 is described as client-side and deterministic, with no case backend yet. (`/Users/evanmotovich/code/Tunza/vault/architecture.md:3`, `/Users/evanmotovich/code/Tunza/vault/architecture.md:4`)
- Three stateless routes exist beside that client app: worker access, nearby-facility proxy, and transcription. They are not a case database. (`/Users/evanmotovich/code/Tunza/app/api/access/route.ts:1`, `/Users/evanmotovich/code/Tunza/app/api/facilities/route.ts:27`, `/Users/evanmotovich/code/Tunza/app/api/transcribe/route.ts:3`)
- Roles in code are household, CHP, and facility. (`/Users/evanmotovich/code/Tunza/lib/types.ts:3`)
- A household session does not need a worker grant. Choosing CHP or facility without a grant returns the user to the household door and opens the gate. (`/Users/evanmotovich/code/Tunza/lib/store.tsx:112`, `/Users/evanmotovich/code/Tunza/lib/store.tsx:356`)
- The worker gate is a placeholder for real identity. Until env codes are set, it runs in demo mode. Do not print the demo code values on a page. (`/Users/evanmotovich/code/Tunza/app/api/access/route.ts:1`, `/Users/evanmotovich/code/Tunza/app/api/access/route.ts:8`, `/Users/evanmotovich/code/Tunza/vault/architecture.md:42`)
- User-visible copy is English and Kiswahili. A missing Kiswahili string is a compile error. (`/Users/evanmotovich/code/Tunza/lib/copy.ts:1`, `/Users/evanmotovich/code/Tunza/vault/architecture.md:8`)
- The home screen offers "Check symptoms" with the words "Text, voice or photo", plus "Nearby facilities" and "Continue". (`/Users/evanmotovich/code/Tunza/lib/copy.ts:15`, `/Users/evanmotovich/code/Tunza/lib/copy.ts:16`, `/Users/evanmotovich/code/Tunza/lib/copy.ts:17`)
- Text entry is a presentation string. (`/Users/evanmotovich/code/Tunza/lib/types.ts:66`, `/Users/evanmotovich/code/Tunza/lib/copy.ts:63`)
- Voice is one tap-to-speak path. It tries server transcription when `/api/transcribe` is configured, then on-device speech, then "type instead". The route returns 503 when `OPENAI_API_KEY` is absent. (`/Users/evanmotovich/code/Tunza/lib/voice.ts:4`, `/Users/evanmotovich/code/Tunza/app/api/transcribe/route.ts:5`, `/Users/evanmotovich/code/Tunza/app/api/transcribe/route.ts:28`)
- Photo is a boolean the user can attach. The on-screen line is "Photo attached (demo)". The rules do not read the image. (`/Users/evanmotovich/code/Tunza/lib/types.ts:68`, `/Users/evanmotovich/code/Tunza/lib/copy.ts:69`, `/Users/evanmotovich/code/Tunza/lib/assessment.ts:79`)
- The question order is who, what, awake, breathing, drinking, duration, main problem. (`/Users/evanmotovich/code/Tunza/lib/assessment.ts:21`)
- The rules are a demonstration. They are deliberately conservative. They are not clinically validated. (`/Users/evanmotovich/code/Tunza/lib/assessment.ts:32`, `/Users/evanmotovich/code/Tunza/lib/assessment.ts:33`, `/Users/evanmotovich/code/Tunza/lib/assessment.ts:34`)
- A decision is one of four kinds: go now, get care today, monitor at home, or need one more answer. (`/Users/evanmotovich/code/Tunza/lib/types.ts:28`, `/Users/evanmotovich/code/Tunza/lib/types.ts:29`, `/Users/evanmotovich/code/Tunza/lib/types.ts:30`, `/Users/evanmotovich/code/Tunza/lib/types.ts:31`, `/Users/evanmotovich/code/Tunza/lib/types.ts:32`)
- Danger patterns listen for English and Kiswahili keywords. (`/Users/evanmotovich/code/Tunza/lib/assessment.ts:32`)
- Every decision returned by `decide` carries the same watch-sign keys. (`/Users/evanmotovich/code/Tunza/lib/assessment.ts:50`, `/Users/evanmotovich/code/Tunza/lib/assessment.ts:119`)
- On-screen disclaimer: "Not a substitute for emergency services or professional medical care." Kiswahili equivalent is in the same table. (`/Users/evanmotovich/code/Tunza/lib/copy.ts:357`, `/Users/evanmotovich/code/Tunza/lib/copy.ts:688`)
- A referral stage list exists in code: created, sent, received, accepted, patient moving, arrived, seen, completed, outcome returned. (`/Users/evanmotovich/code/Tunza/lib/types.ts:9`, `/Users/evanmotovich/code/Tunza/lib/referral.ts:13`)
- The referral machine picks from clearly fake demo facilities, not from live Places results. (`/Users/evanmotovich/code/Tunza/lib/facilities.ts:3`, `/Users/evanmotovich/code/Tunza/lib/facilities.ts:4`, `/Users/evanmotovich/code/Tunza/lib/referral.ts:62`)
- Nearby view can call Google Places through a stateless proxy that is meant to see only a coarse cell center. If the key is missing, or lookup fails, the screen says live lookup is not available and shows demo facilities. (`/Users/evanmotovich/code/Tunza/lib/places.ts:4`, `/Users/evanmotovich/code/Tunza/lib/places.ts:6`, `/Users/evanmotovich/code/Tunza/app/api/facilities/route.ts:27`, `/Users/evanmotovich/code/Tunza/lib/copy.ts:36`)
- Case state persists in the browser under localStorage key `tunza.v2.care`. (`/Users/evanmotovich/code/Tunza/lib/store.tsx:33`, `/Users/evanmotovich/code/Tunza/lib/store.tsx:348`, `/Users/evanmotovich/code/Tunza/lib/store.tsx:436`, `/Users/evanmotovich/code/Tunza/vault/architecture.md:24`)
- Named failure states the demo can inject are offline, no facility response, redirected, stale information, incomplete assessment, and weak connection. (`/Users/evanmotovich/code/Tunza/lib/types.ts:20`, `/Users/evanmotovich/code/Tunza/lib/failures.ts:14`)
- Outcome codes the demo can record in that local state are treated, referred onward, did not arrive, and unknown. That is a local status, not a learned result. (`/Users/evanmotovich/code/Tunza/lib/types.ts:34`, `/Users/evanmotovich/code/Tunza/lib/types.ts:35`, `/Users/evanmotovich/code/Tunza/lib/types.ts:36`, `/Users/evanmotovich/code/Tunza/lib/types.ts:37`, `/Users/evanmotovich/code/Tunza/lib/types.ts:38`)
- The home tagline string in the demo is "Healthcare, anywhere, anytime." Use it only as on-screen copy, not as a page opener. (`/Users/evanmotovich/code/Tunza/lib/copy.ts:13`)

README feature-list rulings. Cite the code line on the page, not the README bullet.

- English and Kiswahili is in the copy table. Do not cite the README bullet as the proof. (`/Users/evanmotovich/code/Tunza/lib/copy.ts:1`, `/Users/evanmotovich/code/Tunza/README.md:66`)
- Text input is the presentation string. Do not cite the README bullet as the proof. (`/Users/evanmotovich/code/Tunza/lib/types.ts:66`, `/Users/evanmotovich/code/Tunza/README.md:67`)
- Voice input is a degrade path, not a guarantee the server route is configured. Do not cite the README bullet as proof it is working. (`/Users/evanmotovich/code/Tunza/lib/voice.ts:4`, `/Users/evanmotovich/code/Tunza/README.md:68`)
- Structured urgency is the four decision kinds. Do not cite the README bullet as the proof. (`/Users/evanmotovich/code/Tunza/lib/types.ts:28`, `/Users/evanmotovich/code/Tunza/README.md:71`)
- Warning signs are the watch-sign keys on each decision object. Do not cite the README bullet as the proof. (`/Users/evanmotovich/code/Tunza/lib/assessment.ts:50`, `/Users/evanmotovich/code/Tunza/README.md:72`)
- Nearby facility discovery is split. Nearby view can look up places. The referral still uses demo facilities. Do not cite the README bullet as one claim. (`/Users/evanmotovich/code/Tunza/lib/places.ts:6`, `/Users/evanmotovich/code/Tunza/lib/facilities.ts:3`, `/Users/evanmotovich/code/Tunza/README.md:73`)

## Designed, not built

Say "designed" or "we want". Never "we have".

- The long-term system is supposed to follow a referral far enough to learn whether it was right. That is design language. (`/Users/evanmotovich/code/Tunza/README.md:15`, `/Users/evanmotovich/code/Tunza/README.md:49`)
- The six different failures in the README are a design list: wrong clinical decision, wrong place, facility could not provide the service, patient could not travel, referral never acknowledged, result never came back. The demo does not distinguish those from outcome data. (`/Users/evanmotovich/code/Tunza/README.md:51`, `/Users/evanmotovich/code/Tunza/README.md:52`, `/Users/evanmotovich/code/Tunza/README.md:53`, `/Users/evanmotovich/code/Tunza/README.md:54`, `/Users/evanmotovich/code/Tunza/README.md:55`, `/Users/evanmotovich/code/Tunza/README.md:56`)
- Past-case history is backlog, not shipped. The Continue card is not that history. (`/Users/evanmotovich/code/Tunza/vault/backlog.md:12`, `/Users/evanmotovich/code/Tunza/lib/copy.ts:18`)
- Clinician verification and a doctor dashboard are backlog. No `app/doctor` route was in `app/`. (`/Users/evanmotovich/code/Tunza/vault/backlog.md:14`)
- PWA, service worker, and web push are backlog. A search of `*.ts`, `*.tsx`, and `*.json` in the Tunza tree found no `serviceWorker` or manifest match. (`/Users/evanmotovich/code/Tunza/vault/backlog.md:16`)
- A deterministic clinical safety layer that replaces the demo rules is backlog, and it requires clinical review before real use. (`/Users/evanmotovich/code/Tunza/vault/backlog.md:20`, `/Users/evanmotovich/code/Tunza/lib/assessment.ts:34`)
- Referral history entries exist on the object. Nothing renders them yet. (`/Users/evanmotovich/code/Tunza/vault/backlog.md:22`)
- Supabase persistence is backlog for this app. (`/Users/evanmotovich/code/Tunza/vault/backlog.md:24`)
- Real facility capability data for the referral machine does not exist yet. Nearby Places results are names, categories, and distance, not capability truth. (`/Users/evanmotovich/code/Tunza/vault/backlog.md:10`, `/Users/evanmotovich/code/Tunza/lib/places.ts:5`)
- Image input, as a read of the picture, is not built. The README bullet is not the code. (`/Users/evanmotovich/code/Tunza/README.md:69`, `/Users/evanmotovich/code/Tunza/lib/copy.ts:69`)
- Optional vitals: no `vitals` match in `*.ts`, `*.tsx`, or `*.json` in the public tree. Do not claim them. (`/Users/evanmotovich/code/Tunza/README.md:70`)
- Anonymous-first, signed-in case history, community case signals, outbreak signal, verified-clinician workflows, and clinician notifications are README bullets the code search did not support. Do not claim them. (`/Users/evanmotovich/code/Tunza/README.md:74`, `/Users/evanmotovich/code/Tunza/README.md:75`, `/Users/evanmotovich/code/Tunza/README.md:76`, `/Users/evanmotovich/code/Tunza/README.md:77`, `/Users/evanmotovich/code/Tunza/README.md:78`, `/Users/evanmotovich/code/Tunza/README.md:79`)
- The older private app is described, in the public tree's architecture note, as Next 14 plus Supabase plus Anthropic triage plus Whisper plus Google Places plus web push. That description is not a claim about the public demo. This run did not open the `medical-triage` repo. (`/Users/evanmotovich/code/Tunza/vault/architecture.md:68`, `/Users/evanmotovich/code/Tunza/vault/architecture.md:70`)
- The grilling note describes `medical-triage` as a prompt in front of Anthropic, with cases in Supabase and no owned weights. Same limit: not re-opened this run, and not the public app. (`/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:20`, `/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:22`)
- He said he would partner with some NGO to reach eCHIS. That is a wish, not a signed deal. (`/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:27`)
- His only origin line for these pages: eCHIS does not order which sick child goes first. (`/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:28`)
- He also named a second wanted surface, where people ask what to do next. That is the two-product question, not a second shipped app. (`/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:28`)
- In the grilling he leaned toward over-referral, a per-facility cutoff, and a later ranking model. The note says the architecture pitch is leaning, not locked. The public demo rules are conservative, not that ranker. Do not write the grilling lean as what the demo does. (`/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:53`, `/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:54`, `/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:56`, `/Users/evanmotovich/code/Tunza/lib/assessment.ts:32`)
- What a check would buy, if a page states it, is a proposal, not his commitment: one county introduction, a data-rights page, a shadow period where patients are not the test. Not a trained model. Not a national rollout. (`/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23.md:66`)

## Open, his to answer

Leave the answer blank. Do not fill it.

- Label column. What is in `Y`, who produced it, and when? He said he had no idea. (`/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:34`, `/Users/evanmotovich/code/second-brain/me/expertise.md:38`)
- Cold start. Day one, zero labeled outcomes, what does version 1 rank on? He said he had no clue. (`/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:35`)
- Data rights. Connected to eCHIS is not licensed to train on eCHIS. Parked, not asked. (`/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:36`)
- Precision floor. How many false urgents before a CHP stops opening the app? Still open. (`/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:37`)
- One product or two? Prioritization for eCHIS and a consumer question surface are different buyers. (`/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:38`)
- Whether QAD applies here. Still open. Do not import it. (`/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:39`)
- Owned asset today, in his words: nothing yet. (`/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:26`, `/Users/evanmotovich/code/second-brain/me/expertise.md:36`)
- Financing fields, all blank. No named source in this run contains a Tunza term sheet. Instrument: blank. Amount: blank. Discount or rate: blank. What the earliest partner may join: blank. What they do not get: blank. (`/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23.md:64`, `/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23.md:65`)
- Investor page line one must say terms are not set, do not send this. (`/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23.md:64`)
- Open questions allowed on the investor page only: label, data rights, one product or two, precision floor. (`/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23.md:67`)

## Forbidden

Do not put these on a page. Naming them here is the ban, not permission to repeat the underlying claim.

- A trained model, owned weights, or "the public app is Anthropic." The public rules are a demonstration. The grilling note says no model is trained and no weights are owned. (`/Users/evanmotovich/code/Tunza/lib/assessment.ts:31`, `/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:22`)
- A signed NGO, a named county as fact, or a partnership he already has. He said nothing yet, and the NGO line was "i would". (`/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:26`, `/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:27`)
- Clinical benefit, diagnostic certainty, or regulatory clearance. The rules are not clinically validated. The README physician sentence is not a code claim. Use the disclaimer cite if a page needs the limit. (`/Users/evanmotovich/code/Tunza/lib/assessment.ts:33`, `/Users/evanmotovich/code/Tunza/README.md:83`, `/Users/evanmotovich/code/Tunza/lib/copy.ts:357`)
- A moat. "The only gap." Unique AI insight. The grilling note's moat sentence is the compiler's pair, not an asset he owns. (`/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:26`)
- The energy thesis. Any "500 billion" or "500B" line. Shop names from that brief: Renaissance, Two Sigma, Jane Street, HRT. Transfer the writing lesson only. (`/Users/evanmotovich/code/second-brain/DECISIONS.md:434`, `/Users/evanmotovich/code/second-brain/DECISIONS.md:437`)
- Solomon. The v8 correction says he is not the energy partner. Do not reuse the name. (`/Users/evanmotovich/code/second-brain/DECISIONS.md:444`)
- The uncited 100,000-promoter and 9-million-household figures, including "100k" and "9M". They are his, and the note says they need a source before any investor sees them. (`/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:53`)
- An invented origin story. The clinic-door scene in the README is the product situation, not how he thought of it. (`/Users/evanmotovich/code/Tunza/README.md:5`, `/Users/evanmotovich/code/second-brain/inventory/QUERY-tunza-model-design.md:28`)
- An invented discount, rate, amount, or instrument. (`/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23.md:65`)
- Sending the investor page. Terms are not set. (`/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23.md:3`, `/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23.md:64`)
- Copying README lines 62-81 into a page. (`/Users/evanmotovich/fusion-harness/prompts/tunza-vision-2026-09-23.md:24`)

---
Governed by `/Users/evanmotovich/code/second-brain/AGENTS.md` for reads. This run does not write the vault.
