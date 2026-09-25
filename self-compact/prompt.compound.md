# Self Compaction ## Problem Long running autonmous agents can run out
   of context Long running context reduces performance ( context rot ) and
   burns cash ( state of the art models) These agents built for long
   running, autonomous, no human in the loop "Out Loop" agentic work. ##
   Solution Build a standalone pi coding agent with a few key features
   1.'Self_compaction(note_to_self)' - allow the agent to compact itself 2
   'Context Control' - three unique threshold levels: notice, warning,
   forced compaction with cli flags to support it. 3.'Pi UI' - A UI to
   match the three compaction levels. 4.'Prompt Engineering' - concrete
   prompts for each intereaction wiht out agent(compaction prompt, soft
   notice user prompt, warning user prompt) 5. ## Variables -
   'PI_AGENT_DOCS_DIR: <Project ## Implementation Notes ## Workflow 1.
   Plan. Use the /plan commmands build step to implemnet that plan inside
   'YOUR_WORKING_DIR:' do not skip straight from this, save the completed
   plan in
 'Plan_DIR:' before writing implementation code
   2. Build. After the plan is written follow the /plan build step to
implemnet that plan inside 'YOUR_WORKING_DIR'. Do not skip straight from
this prompt to
 implementation.
   3. Verify check every time in defintion of done, Fix faliures, and rerun
the affected checks, keep final implementation artifacts inside
'YOUR_WORKING_DIR:'. and
  report actual results and any remaining faliures/blockers, look for ways
to bypass those blokckers by giving you those neccsary tools and 'Bash
tools'
   ## Delivirabables - Your completed /plan implementation plan exitst in
   'PLAN_DIR/'. - It was written before implementation and the build
   follows its build steps. -
   "YOUR_WORKING_DIR/extensions/self-compact/self-compact.ts' loads as a
   standalone extensions, with small helpers as needed as needed and no
   dependency on other
 extensions.
   ## User Interface - Context bar shows usage and thresholds - Expected
   example: '###'=====/-|-----] 40%', with default thresholds and half the
   used context catched. - Verify 20 cells at 5% each, cached '#' free '-'
   and visbile '-' / '!' / '!' markets at 10%, 20%, 25, 50%/ 60% - The
   token basssed launch on a 1,000,000 token model move markers to 10%/
   20%/ 25%. A zero buffers shows '|' where warning and forced overlap. ##
   Prompt Engineering - Files are in corrected place: -
   'YOUR_WORK_DIR/.pi/self-compact/USER_SOFT_SELF_COMPACT.md' supplies
   editable soft Optional guidance wiht live usage values. Run fro
   '--compact-soft-at' -
   'YOUR_WORK_DIR/.pi/self-compact/USER_PROMPT_SELF_COMPACT.md' supplies a
   more stern time to compact soon, hard cutoff at... ' message runs from
   'compact-at'. -
   'YOUR_WORK_DIR/.pi/self-compact/USER_PROMPT_COMPACTION_MESSAGE_.md'
   replaces pi coding agent default compacting prompt. ## Compaction
   Thresholds All four flags work. - '--compactions-soft-at 20%': optional
   heads up tools remain avalable. - '__Compactions-at 50% : ask the agents
   to write its note and compact, without blokcing ordinary tools yet. -
   '--compact-buffer 10% ' allow ten more percent points of the model
   window, then block other tools at 60% accept '0' for immediate
   enforcement. - '--compact-prompt' ..."': replace the summary system
   prompt with literal text, independently of the saved note and optional
   user-prompt file. - Threshholds and buffer accept the whoel token count,
   'k'/'m' suffixes, or percentages. cap the hard list at 90% and reject
   invalid settings. - Defaults (after testing, test with lower amounts)
   soft: 250k warning: 350K force: 400k ### Launch commands - Launch
   variants produce expected results: - 'pi' -e
   "$YOUR_WORKING_DIR"/extensions/self-compact/self-compact.ts"'
       - Expected launch with the defaults: 250k, 350k, 400k use a combo of
'k' and '%'.
   - --compact-prompt "summarizw current goal, completed work, exact path,
test results, and next actions. DO not reinvent completed work.
   ## Defintion of Done ## How Your Graded - You'll be graded on a
   continous basis bassed on every completed bullet in the definiton of
   done. - Every step of your workflow must be fully accomplished: plan,
   build, and verify. - Insant failure if you write projects on deliverable
   outside your 'YOUR_WORKING_DIR' with the exceptions of 'Plan_DIR' -
   Instant failures if you read any part of any file inside of
   <PROJECT_ROOT>specs/* that isnt your own plan. - Instant faliures if you
   read any part of any files inside of <PROJECT_ROOT>apps/* that isnt your
   own work. - Running tools outside these directories is allowed. - If you
   find you've mistaknley causeed a failure stop immediately and report
   your faliure. h
