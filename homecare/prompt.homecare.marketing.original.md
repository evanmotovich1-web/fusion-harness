## Homecare Marketing 


### What Is This 

- **I own a homecare company a, we essentailly people need health care giver or peopel to help out thier parents or grandparents a lot of the time teh peopel are the one helping their parenets and through medicare they can get paid for this, so we essentailly pay peopel to take care of their loved ones. 
- **A account is a care giver and thier account they dont neccsarly have to be family but family makes it easier.
- **We are bassed in missouri**
- **The Goal is to automate more of my company to help me grow, step 1 is marketing.


### Problems 

1. **I have 20 clients right now, I could have up to 100**
2. **I Use meta to market adds right now, i need to find other sources lower the cost of marketing and bring in more clients**
3. **I need a autonmous workflow, connected to a knowledge base i develop for my bussiness that will handle all this. 
4. **I need a metric to track my results, and cost to reward to see the added value to it. 
5. **A normal agent can not orchestrate the taks or build out the system perfectly, a workflwo orchestrated by code can do it. 

### Solutions 

1. **Create a marketing workflow, executed by actionable code and agents through cli mcp and api extensions
2. **create a ui for homecare marketing that runs through the factory and adw.**
3. **Prompt Engineering:** Create concrete prompts for each workflwo recorded, and a system prompt for each recorded agent in the workflow with a soft notice user prompt attatched.
4.

### Variables 


### Workflows
 
1. Plan. Use the /plan commmands 
build step to implemnet that plan 
inside 'YOUR_WORKING_DIR:' do not 
skip straight from this, save the 
completed plan in 'Plan_DIR:' before 
writing implementation code

 2. Build. After the plan is written 
follow the ### Implementation Notes 
/plan build step to implemnet that 
### Phase Plan 3. Verify check every 
time in defintion of done, Fix 
faliures, and rerun the affected 
checks, keep final implementation 
artifacts inside 
'YOUR_WORKING_DIR:'. and report 
actual results and any remaining 
faliures/blockers, look for ways to 
bypass those blokckers by giving you 
those neccsary tools and 'Bash 
tools' plan inside 
'YOUR_WORKING_DIR'. Do 1. Plan: - ** 
Use the /planf1 folder skill.** - my 
not skip straight from this prompt
to implementation.

3. Verify check every time in defintion of done, Fix faliures, and rerun the affected checks, keep final implementation artifacts inside 'YOUR_WORKING_DIR:'. and report actual results and any remaining faliures/blockers, look for ways to bypass those blokckers by giving you those neccsary tools and 'Bash tools'


### Implementation Notes

- Use the funnel as the metric. 
Track ad spend → leads → qualified 
→ reached by phone → assessment 
booked → client started. Then 
compute:
  - cost per lead ### Defintion of 
Done
  - cost per new client - percent of 
  leads that move to each next step 
  - this answers Problem 4 (a metric 
  to track results).### 
  Delivirabables
- Build it in three phases, so 
nothing can spend money or contact 
people before the data is right: ### 
User Interface
  a. Read-only. Pull Meta ad stats 
and Meta lead-form leads into one 
database and show them on a 
dashboard. Nothing gets changed or 
sent. ### Prompt Engineering
  b. Lead follow-up. Code scores 
each lead (county, payer or Medicaid 
status, hours needed, whether they 
have a caregiver). Then send a text 
or call and track each lead's 
status. ### How Your Graded
  c. Ad autonomy. The agent drafts 
new ad variants and budget changes. 
They're applied within a hard daily 
spend limit that code enforces. - 
Problem 5 ("a normal agent can't 
orchestrate this"): you already have 
the pattern. Your SSSF homecare 
workflow alternates agent steps with 
code checks, and the checks run the 
same code the agent can run itself. 
Reuse that for marketing. # FORWARD 
DEPLOY PLAN - Two gaps from the 
vault that you need to close this 
time:
  - It needs a scheduler and a 
database. The SSSF homecare jobs run 
once and write files. "Autonomous" 
means a daily cron that reads the 
database, acts and writes back. 
Otherwise each run forgets the leads 
from the last one. That's the same 
missing-writeback problem that 
created the double-booking risk.
  - It needs an intent router. Run 
f10d2475 got "build me a pitch deck 
for homecare" and failed because it 
tried to process it as a patient 
referral. The marketing and ops 
workflows need a front door that 
sends each request to the right one. 
- Lesson from the earlier run: give 
each field shared between agents one 
owner, and write its meaning into 
every prompt that uses it. The payer 
id vs verbatim mismatch cost two 
audit rounds.
  



### Variables **Paths** - 
`PROJECT_ROOT: 
/Users/evanmotovich/fusion-harness` 
- `YOUR_WORKING_DIR: 
<PROJECT_ROOT>/apps/homecare-marketing` 
- `PLAN_DIR: 
<PROJECT_ROOT>/specs/homecare-marketing` 
- `SSSF_REFERENCE_DIR: 
/Users/evanmotovich/code/sssf` 
(read-only; copy the pattern from 
`adws/adw_homecare.py` and 
`adws/adw_modules/homecare.py`, do 
not edit) - `DB_PATH: 
<YOUR_WORKING_DIR>/data/marketing.db` 
(SQLite, the one shared source of 
truth) - `FIXTURES_DIR: 
<YOUR_WORKING_DIR>/fixtures` 
(synthetic Meta stats + leads; no 
real names, phones, or health info) 
- `REPORTS_DIR: 
<YOUR_WORKING_DIR>/reports` - 
`PROMPTS_DIR: 
<YOUR_WORKING_DIR>/.pi/homecare-marketing/`
  - `AD_COPY_WRITER.md` — drafts ad 
variants
  - `LEAD_QUALIFIER.md` — explains a 
lead's score in plain language
  - `WEEKLY_ANALYST.md` — weekly 
results + recommended changes 
**Business** - `STATE: MO` - 
`SERVICE_COUNTIES: <FILL>` (e.g. St. 
Louis, St. Charles, Jefferson) - 
`CARE_MODEL: <FILL>` 
(consumer-directed / agency / both) 
- `PAYERS: <FILL>` (e.g. MO 
HealthNet, VA, private pay) - 
`CURRENT_CLIENTS: 20` - 
`TARGET_CLIENTS: <FILL>` by `<FILL 
date>` - `TIMEZONE: America/Chicago` 
**Funnel (fixed stage names, used 
everywhere)** - `LEAD_STAGES: new → 
contacted → qualified → 
assessment_booked → client_started 
| lost` **Money limits (enforced by 
code, not the agent)** - 
`DAILY_AD_SPEND_CAP_USD: <FILL>` - 
`MAX_DAILY_BUDGET_CHANGE_PCT: 20%` - 
`TARGET_COST_PER_LEAD_USD: <FILL>` - 
`TARGET_COST_PER_CLIENT_USD: <FILL>` 
**Schedule** - `SYNC_SCHEDULE: daily 
06:00 America/Chicago` - 
`WEEKLY_REPORT: Monday 07:00 
America/Chicago` - `CONTACT_HOURS: 
08:00–21:00 lead's local time` 
(texts/calls only inside this 
window) **Switches (all start 
safe)** - `DRY_RUN: true` — read and 
report only - `OUTREACH_ENABLED: 
false` — no texts/calls until turned 
on - `ADS_WRITE_ENABLED: false` — no 
ad or budget changes until turned on 
**Secrets (env var names only — 
never put values in files)** - 
`META_ACCESS_TOKEN`, 
`META_APP_SECRET`, 
`META_AD_ACCOUNT_ID`, 
`META_PAGE_ID`, `META_API_VERSION` - 
`TWILIO_ACCOUNT_SID`, 
`TWILIO_AUTH_TOKEN`, 
`TWILIO_FROM_NUMBER` - `MODEL: 
<FILL>` (the pi model the agents run 
on) The choices I made: - Working 
dir under apps/ and plan under 
specs/. Your grading rules from the 
self-compact prompt already assume 
those folders. If you'd rather use 
homecare-main/, change the first two 
paths. - One SQLite database. The 
earlier SSSF homecare workflow only 
wrote files and never recorded what 
it had done, so later runs couldn't 
see earlier results. A shared 
database avoids that here. - All 
three switches start off. The first 
phase only reads and reports, and 
nothing spends money or contacts a 
lead until you turn it on.
Fill in the <FILL> values (counties, care model, payers, targets, spend cap, model) and I'll write the Definition of Done next.




pass. - 
`YOUR_WORKING_DIR/verification/results.md` 
lists every Definition of Done 
bullet with PASS/FAIL and the 
command output that proves it.
- `YOUR_WORKING_DIR/SETUP.md` lists exactly what Evan must provide (Meta app + token, ad account id, Twilio number + A2P registration) and which env var each one goes in.
