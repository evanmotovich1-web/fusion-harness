# Homecare Marketing

## What Is This

- I own a homecare company in Missouri. Most clients are older adults cared for by a family member or someone they choose. Through Missouri Medicaid (MO HealthNet) Consumer Directed Services, that caregiver gets paid — we employ and pay people to take care of their loved ones.
- An "account" is a caregiver + the client they care for. The caregiver does not have to be family, but family makes it easier.
- Goal: automate more of the company so it can grow. Step 1 is marketing.

## Problems

1. I have 20 clients. I could have 100.
2. I market with Meta ads today. I need other lead sources, lower marketing cost, and more clients.
3. I need an autonomous workflow connected to a knowledge base I write about my business.
4. I need a metric that shows results and cost vs. reward.
5. A single agent cannot orchestrate this reliably. A workflow orchestrated by code can.

## Solution

1. A marketing workflow run by code: agents do the writing and judgment, code does every rule, number, and check.
2. A local dashboard (UI) for the funnel and results.
3. Prompt engineering: every agent has a system prompt, a user prompt, and a soft-notice prompt, all editable files on disk.

## Variables

**Paths**
- `YOUR_WORKING_DIR: /Users/evanmotovich/fusion-harness/homecare`
- `PLAN_DIR: <YOUR_WORKING_DIR>/specs`
- `SSSF_REFERENCE_DIR: /Users/evanmotovich/code/sssf` — read-only. Copy the pattern from `adws/adw_homecare.py`, `adws/adw_modules/homecare.py`, `adws/adw_modules/agent_pi.py`. Never edit it.
- `KNOWLEDGE_DIR: <YOUR_WORKING_DIR>/knowledge` — Evan's business knowledge base (markdown). Agents read it; they never write it.
- `DB_PATH: <YOUR_WORKING_DIR>/data/marketing.db` — SQLite, the one source of truth.
- `FIXTURES_DIR: <YOUR_WORKING_DIR>/fixtures` — synthetic data only. No real names, phones, or health info.
- `REPORTS_DIR: <YOUR_WORKING_DIR>/reports`
- `PROMPTS_DIR: <YOUR_WORKING_DIR>/prompts`

**Business**
- `STATE: MO`
- `SERVICE_COUNTIES: <FILL>`
- `CARE_MODEL: consumer-directed` (change if you also run agency-staffed care)
- `PAYERS: <FILL>` (e.g. MO HealthNet, VA, private pay)
- `CURRENT_CLIENTS: 20`
- `TARGET_CLIENTS: 100` by `<FILL date>`
- `TIMEZONE: America/Chicago`

**Funnel (fixed stage names, used everywhere)**
- `LEAD_STAGES: new → contacted → qualified → assessment_booked → client_started | lost`
- `LEAD_SOURCES: meta, google_business_profile, website_form, referral, phone, other` (every lead has one)

**Money limits (enforced by code, never by an agent)**
- `DAILY_AD_SPEND_CAP_USD: <FILL>`
- `MAX_DAILY_BUDGET_CHANGE_PCT: 20`
- `TARGET_COST_PER_LEAD_USD: <FILL>`
- `TARGET_COST_PER_CLIENT_USD: <FILL>`

**Schedule**
- `SYNC_SCHEDULE: daily 06:00 America/Chicago`
- `WEEKLY_REPORT: Monday 07:00 America/Chicago`
- `CONTACT_HOURS: 08:00–21:00 in the lead's local time`

**Switches (all start safe)**
- `DRY_RUN: true` — read and report only
- `OUTREACH_ENABLED: false` — no texts or calls
- `ADS_WRITE_ENABLED: false` — no ad or budget changes

**Secrets (env var names only — never write values into any file)**
- `META_ACCESS_TOKEN`, `META_APP_SECRET`, `META_AD_ACCOUNT_ID`, `META_PAGE_ID`, `META_API_VERSION`
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`
- `MODEL: deepseek/deepseek-flash` — the `pi` model the agents run on (worked headless with tools on 2026-09-26; change if you prefer another)

## Implementation Notes

- **Metric = the funnel.** Ad spend → leads → contacted → qualified → assessment booked → client started. Compute cost per lead, cost per client, and conversion % at each step, per source and per ad.
- **Three phases, safe first.**
  - a. Read-only: pull Meta ad stats and lead-form leads into the DB, show them on the dashboard. Nothing is sent or changed.
  - b. Lead follow-up: code scores each lead (county, payer, hours needed, has a caregiver). Agent drafts the first text; code checks it; it is sent only when `OUTREACH_ENABLED=true`.
  - c. Ad autonomy: agent drafts ad variants and budget changes; code rejects anything over the money limits; applied only when `ADS_WRITE_ENABLED=true`.
  - Build all three now, but a and b run live first; c stays behind its switch.
- **Code orchestrates, agents fill in.** Follow the SSSF homecare pattern: every agent phase is followed by a code gate. The gate runs the same check the agent can run itself beforehand through the CLI. A gate failure goes back to the agent as its soft notice, with the exact failure text, and it retries.
- **The workflow remembers.** Every run reads the DB and writes back to it. No run starts from zero.
- **Intent router at the front door.** A request is routed to the right workflow (`daily`, `creative`, `growth`, `weekly`) or refused as `not_marketing`. It never falls into the wrong pipeline.
- **One owner per shared field.** Any field two agents touch (payer, stage, source, county) has one definition, written into every prompt that uses it.
- **No health info leaves the DB.** Code redacts free text before any agent sees it. Agents see lead id, county, source, stage, and redacted text — never diagnosis, Medicaid id, or health notes. Nothing like that goes to Meta either.
- **Outreach rules.** Only contact leads who submitted a form or called in. Every text ends with "Reply STOP to opt out." Never inside quiet hours.
- **Git.** `/Users/evanmotovich/fusion-harness` is a shared checkout with other agents' work. Do not commit, stash, reset, or checkout anything there.

## Agents

Ten agents across four workflows. Code runs every workflow; agents only write and judge.

Each agent has a folder `PROMPTS_DIR/<agent>/` with four files, loaded from disk at run time:
- `system.md` — who it is, the rules, the exact output format (JSON schema).
- `user.md` — the task template, filled with live values from the DB and `KNOWLEDGE_DIR`.
- `soft_notice.md` — the retry message sent after a failed code gate, with `{failures}` filled in.
- `tools.json` — the exact tools it may call (CLI commands, read-only web for researchers). No other tools.

**Tool calling is required, not optional.** Every agent runs `marketing_cli.py check <agent> <its output>` itself before returning, and fixes what fails. The code gate then runs the same check again. Agents that need data get it by calling CLI commands (`funnel`, `kb search`, `leads show`), not from pasted text.

Agents run headless through `pi` (pattern: `SSSF_REFERENCE_DIR/adws/adw_modules/agent_pi.py`), e.g. `pi --model <MODEL> --tools <from tools.json> -p <assembled prompt>`.

| # | Agent | Workflow | Job | Code gate after it |
|---|---|---|---|---|
| 1 | `channel_researcher` | growth | Find non-Meta lead sources for MO homecare with cost estimates | ≥5 sources, each with cost estimate + source URL, none already in DB |
| 2 | `referral_partner_scout` | growth | List referral partners in `SERVICE_COUNTIES` (Area Agencies on Aging, hospital discharge planners, senior centers, churches) from public sources | every partner in a service county, has a source URL, no duplicates in DB |
| 3 | `competitor_analyst` | creative | Read Meta Ad Library for MO homecare competitors; extract hooks, offers, CTAs | every claim cites an Ad Library ad id/URL |
| 4 | `ad_copy_writer` | creative | Draft Meta ad variants from the knowledge base + competitor findings | Meta length limits, program named correctly, no "guaranteed pay" or health-condition claims, every fact found in `KNOWLEDGE_DIR` |
| 5 | `landing_page_writer` | creative | Write landing page + lead form copy | required sections present, form fields match the `leads` schema, no health questions, reading grade ≤ 8 |
| 6 | `compliance_reviewer` | creative + daily | Second pass on ads, pages, and texts against `KNOWLEDGE_DIR/rules.md` | every flag cites a rule id from `rules.md`; nothing ships with an open flag |
| 7 | `lead_intake_extractor` | daily | Turn a lead's free-text form answer (already redacted by code) into county / payer / hours needed / has caregiver | every field is a valid enum value or `unknown`; nothing invented |
| 8 | `followup_writer` | daily | Draft the first text and the day-3 / day-7 follow-ups | ≤320 chars, opt-out line, no health info, lead's stage allows contact |
| 9 | `weekly_analyst` | weekly | Weekly results: what worked, what didn't, per source and per ad | every number it cites matches the DB exactly |
| 10 | `budget_optimizer` | weekly | Propose budget moves between ads and sources from the funnel | passes `propose-ad-changes` limits; each move cites the funnel numbers behind it |

**Workflows (each is one code-run ADW):**
- `daily` — sync-meta → import-leads → redact (code) → [7] → score-leads (code) → [8] → [6] → outreach (code, behind switch)
- `creative` — [3] → [4] + [5] → [6] → store approved drafts
- `growth` — [1] → [2] → store in DB
- `weekly` — funnel (code) → [9] → [10] → propose-ad-changes (code, behind switch)

Lead scoring, redaction, spend limits, contact hours, funnel math and routing are code, not agents.

## Deliverables

- Plan: `PLAN_DIR/plan.md`, written before any code. The build follows its steps.
- `YOUR_WORKING_DIR/data/schema.sql` — tables `ad_daily_stats`, `leads`, `lead_events`, `outreach_log`, `ad_changes`, `agent_runs`.
- `FIXTURES_DIR/` — one synthetic week of Meta stats; ≥30 synthetic leads covering every stage and source, at least one outside `SERVICE_COUNTIES`; `expected_funnel.json` with hand-computed funnel numbers; one good and one deliberately bad output per agent (`good_<agent>.json`, `bad_<agent>.json`) to prove the gates.
- `KNOWLEDGE_DIR/` — starter files for Evan to edit: `company.md`, `program.md` (how Consumer Directed Services works), `service_area.md`, `voice.md` (how we talk), `rules.md` (numbered ad/texting/Medicaid wording rules the compliance reviewer cites). Mark every unknown `<EVAN: fill>`; do not invent facts about the company.
- `YOUR_WORKING_DIR/marketing_cli.py` with commands: `init-db`, `sync-meta`, `import-leads`, `redact`, `score-leads`, `outreach`, `propose-ad-changes`, `funnel`, `route`, `kb search`, `leads show`, `check <agent> <output.json>`, `serve`. Every data command takes `--fixtures`.
- `YOUR_WORKING_DIR/adw_marketing.py <daily|creative|growth|weekly>` — the code-orchestrated workflows: route → code steps → agent phase → code gate → (soft notice + retry on failure) → write to DB → report. `--stub-agents` returns the fixture outputs (bad first where a test asks, then good) so every flow runs without a model or keys.
- `PROMPTS_DIR/<agent>/system.md|user.md|soft_notice.md|tools.json` for all ten agents.
- `YOUR_WORKING_DIR/ui/` — local dashboard: funnel by stage, cost per lead, cost per client, per-source and per-ad results, lead table with score reasons, pending ad changes. Served by `marketing_cli.py serve`.
- `YOUR_WORKING_DIR/scheduler/` — launchd plist(s) for `SYNC_SCHEDULE` and `WEEKLY_REPORT` plus the install command. Do not install them.
- `YOUR_WORKING_DIR/tests/`
- `YOUR_WORKING_DIR/verification/results.md` — every Definition of Done bullet, PASS/FAIL, and the command + output that proves it.
- `YOUR_WORKING_DIR/SETUP.md` — exactly what Evan must provide (Meta app + token, ad account id, page id, Twilio number + A2P 10DLC registration, model), which env var each goes in, and how to flip each switch.

## Definition of Done

Every command below runs from `YOUR_WORKING_DIR` with `--fixtures` and `--stub-agents` where relevant — no keys, no network, no spend.

1. `PLAN_DIR/plan.md` exists and is older than every code file in `YOUR_WORKING_DIR`.
2. `python marketing_cli.py init-db` creates `DB_PATH` with all six tables; running it again changes nothing and does not error.
3. `sync-meta --fixtures --date <fixture date>` inserts the fixture rows; running it again inserts 0.
4. `import-leads --fixtures` imports every fixture lead; running it again creates 0 duplicates.
5. `score-leads`: every lead gets qualified/unqualified plus a reason; the out-of-area lead is unqualified with a reason naming the county.
6. `outreach` with `OUTREACH_ENABLED=false` sends nothing and logs `skipped_disabled`. With it true and a stub sender: a lead at 22:00 local is `skipped_hours`; every sent text ends with the opt-out line.
7. `propose-ad-changes`: a change over `DAILY_AD_SPEND_CAP_USD` or `MAX_DAILY_BUDGET_CHANGE_PCT` is rejected with a reason; with `ADS_WRITE_ENABLED=false` nothing is applied.
8. `funnel --fixtures` output equals `FIXTURES_DIR/expected_funnel.json` exactly (per stage, per source, cost per lead, cost per client).
9. `route "build me a pitch deck"` → `not_marketing`. `route "weekly results"` → `weekly`. `route "run today"` → `daily`. `route "new ad ideas"` → `creative`. `route "find more lead sources"` → `growth`.
10. `python adw_marketing.py <workflow> --fixtures --stub-agents` runs end to end for all four workflows; each log shows every agent phase followed by its code gate, and the DB has an `agent_runs` row per phase.
11. For all ten agents: `check <agent> FIXTURES_DIR/bad_<agent>.json` fails with a specific message and `check <agent> FIXTURES_DIR/good_<agent>.json` passes; in the workflow, the failure message goes back through `soft_notice.md` and the stub's second attempt passes.
12. All ten agents have their four prompt/tool files, read from disk: a test changes a line in `system.md` and sees it in the assembled prompt; a test asserts the `pi` command line contains exactly the tools in `tools.json`.
13. No health info reaches an agent: a test puts a fake diagnosis and Medicaid id in a fixture lead's free text and asserts neither string appears in any assembled prompt or agent log (including `lead_intake_extractor`'s).
14. `serve` starts the dashboard; a test calls its data endpoint and the numbers equal `funnel` output.
15. `scheduler/` contains valid plists (`plutil -lint` passes) and an install command; nothing is installed.
16. `KNOWLEDGE_DIR` starter files exist; no company facts were invented (unknowns say `<EVAN: fill>`).
17. `SETUP.md` exists and names every env var in Variables.
18. All tests pass (`python -m pytest tests -q`).
19. `verification/results.md` lists 1–18 with PASS/FAIL and real command output.

## Workflow

1. **Plan.** Read this whole file. Write the implementation plan to `PLAN_DIR/plan.md`: files, build order, and how each Definition of Done bullet will be checked. Then **stop and show Evan the plan.** Do not write code until he says go.
2. **Build.** Follow the plan's steps in order inside `YOUR_WORKING_DIR`. Run each piece's tests as you finish it.
3. **Verify.** Run every Definition of Done check. Fix failures and rerun the affected checks. Write `verification/results.md` with real results. If something is blocked (missing key, missing tool), say exactly what is needed and find a way to test around it with fixtures/stubs.
4. **Report.** Tell Evan in plain bullets: what passed, what failed, what he must do next (from `SETUP.md`).

## How You're Graded

- Every Definition of Done bullet counts. Plan, Build and Verify must all be done, in that order.
- Instant failure: writing project files outside `YOUR_WORKING_DIR` (the plan lives inside it at `PLAN_DIR`).
- Instant failure: editing anything in `SSSF_REFERENCE_DIR`, committing to the fusion-harness git checkout, or sending a real text or ad change.
- Instant failure: claiming PASS without the command output that proves it.
- If you realize you caused a failure, stop and report it.
