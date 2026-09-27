# Repair Swarm Console and build reusable tool-based harnesses for all agent swarms

## User mandate
Implement this, not just a design document. Evan wants working tool-based harnesses for ALL agent swarms: shared reliable execution infrastructure, with task-specific context, actual tools, memory, model policy, distinct role/system prompts, durable state and truthful UI. Reuse his existing Pi/Fusion/Agentic OS ecosystem rather than creating another disconnected agent framework. First deliver the complete vertical slice in Evan Swarm Console, then integrate the reusable harness with the other discovered swarm entrypoints. Inventory integration coverage explicitly; do not call something universal after wiring one client.

The user-facing experience must be plain-English tasking and follow-up instructions, not commands to memorize. Preserve the existing vivid orange globe/fan design, the Astra 6 label, Enter submission and Shift+Enter newlines. Evan chooses team size up to 50; do not silently restore a four-worker concurrency cap. Distinguish selected team size, running processes, queued dependencies, failed workers and completed work. Final synthesis is currently included in total team size; any change must be explicit.

## Repositories and boundaries
Primary application: /Users/evanmotovich/code/evan-swarm-console
Harness: /Users/evanmotovich/fusion-harness
Existing Agentic OS: /Users/evanmotovich/code/agentic-os
Factory execution checkout: /Users/evanmotovich/code/agentic-os-factory-runtime — NOT a development checkout.
Knowledge vault: /Users/evanmotovich/code/second-brain

Before editing read applicable ancestor/repository AGENTS.md and CLAUDE.md, plus /Users/evanmotovich/code/second-brain/AGENTS.md, /Users/evanmotovich/code/agentic-os/AGENTS.md and /Users/evanmotovich/.hermes/hermes-agent/AGENTS.md where applicable. Capture current branches/HEAD/status; this workspace has extensive existing dirty and untracked implementation. Preserve it with baseline snapshots. No reset, restore, deletion, unrelated refactors, commits, pushes or merges without authorization. Coordinate shared files with a single writer. Agentic OS development belongs in an isolated development worktree, not factory runtime.

Do not inspect/modify second-brain trading/ or sessions/, Agentic OS watch/data/* or runtime/. Do not read or print secrets. Existing vault-sync may automatically commit/push vault writes: avoid production vault writes during tests and report any unavoidable operational exception; never fight its history. Agentic OS smoke gates follow its current tools/run-smoke.sh instructions. No main publication. Ask before new dependency installations or external service/account changes.

## Observed failures — verify current state before acting
The app serves http://localhost:1455. A real one-worker GLM no-tool diagnostic completed, but that was NOT proof of useful research.

1. A blanket historical uncertainty gate rejected every new valid mission with HTTP 409. This was repaired with conservative startup process/lease census and retained reservations. Preserve that fix and test it; do not erase uncertainty or fake reconciliation.
2. Scene previously accumulated every historical worker. Selected-mission scoping now exists across scene, counts, reports and events. Preserve it. Old missions must remain inspectable without inflating the current team.
3. Enter previously inserted a newline. Enter-to-submit, IME protection, pending guards, error preservation and explicit receipt now exist. Preserve browser regressions.
4. Tool transport had concurrent-RPC and backpressure defects. Child RPC serialization and correct treatment of write(false) were added. Preserve these regressions. Real sandboxed SDK tests used simulated inference/tool outputs, not a verified live research campaign.
5. Actual substantive mission mission-e457e87d-a3fd-4978-9664-4ad23ea01f95 asked for market entry/growth research on Tunza healthcare and EMSquared hedge fund, including their repositories. Last inspected outcome: 6 completed, 11 failed, 3 uncertain, no final synthesis. Eleven failures had timing consistent with the 240-second deadline; exact historical provider/tool causes were NOT retained. Do not assert that all were caused by the transport defects.
6. Follow-up text 'dont stop running' became unrelated mission mission-bc497b47-7598-45e3-8ffc-16734c19b67f. Last inspected: 13 completed, 2 failed, 5 uncertain. Most reports said no actionable scope; one invented a market-sentiment topic. There was no continuation context. This is a product/control-plane failure, not useful research.
7. Public workers could not read repos or generally retrieve webpages; Grok research searched X. Reports supplied general diligence checklists, sometimes unverified citations, not project-specific findings. Several had zero citations. No reliable compute estimate or validated project moat was established.
8. Blue pet overlay is external to the app (Codex desktop); do not invent app CSS as its root-cause fix.

Evidence: /tmp/tunza-emsquared-worker-reports.json contains the six saved reports (temporary file may disappear). Recover authoritative reports from durable application storage if absent. Relevant code: src/server/mission-*.ts; src/worker/{pi,bridge,sandbox,grok,knowledge,orchestrator}; src/lib/swarm/{missions,store}.ts; src/components/console/MissionPanel.tsx and scene components. Existing tests cover these boundaries. Last parent full gate: 254 passed, 2 opt-in browser tests skipped, no failures; typecheck/build passed. Treat these as historical, not current proof.

## Phase 1 — Reproduce and write acceptance tests
Use mixed-agent read-only investigation and a single-writer integration plan. Architect assigns disjoint ownership, shared contracts, execution dependencies and an independent adversarial reviewer. Probe first, fail fast: expose missing capabilities/auth/permissions before paying for a team.

Trace real browser submit -> accepted mission -> assignment/context -> acknowledged child -> tool request/result -> durable evidence -> review -> synthesis -> displayed deliverable. Diagnose root causes rather than adding more counters or prompts. Inventory actual tools, models, limits, consumers, failure categories and known gaps. Do not rely only on mocked HTTP, no-tool smoke, process liveness or successful build.

## Phase 2 — Reusable tool-based harnesses
Build a shared, versioned core and capability adapters actually consumed by swarm workers. Each task/role manifest must declare:
- approved model, role prompt, objective and acceptance criteria;
- context provenance and bounded project snapshot;
- tools with validated schemas, permissions, return bounds and error contracts;
- approved memory read/write lanes;
- time/token/tool/process budgets, cancellation and retry policy;
- evidence and output contracts and lifecycle persistence.

Minimum useful tools, where permitted:
- confined read-only repository discovery/search/file reading over explicitly approved project roots; deny credential files, traversal and symlink escapes;
- general web search and bounded source retrieval, alongside existing Grok/X research (never label X-only search a general browser);
- document parsing and computation in bounded workspaces where required by the task;
- explicit task delegation, specialist review, artifact writing and evidence retrieval;
- existing second-brain/LLM Wiki and Mnemosyne adapters with actual permissions and readback checks.

Discover Tunza and EMSquared repo paths from existing configuration/files; confirm project identity and scope rather than guessing directories. Never send private repo/vault contents to public research tools without explicit scoped authorization. Keep public/private modes separated or introduce explicit per-tool data-release approvals; do not solve capability gaps with ambient unrestricted filesystem/network access.

Reuse existing Pi SDK, broker, sandbox, Grok integration, memory adapters and model stack. Discover installed exports and current stack configuration. Existing intended worker IDs are xai/grok-4.6, deepseek/deepseek-v4-pro, zai-coding-cn/glm-5.3, openai-codex/gpt-6-astra; validate live configuration without silently substituting models. Parent owns credentials, capability grants and budgets; workers cannot broaden them. Mnemosyne approval gates remain real blockers until authorized, not simulated success. Tool availability must be machine-checked before planning and truthfully reflected in system prompts.

## Phase 3 — Mission continuity and orchestration
Provide explicit Continue/Follow up on selected mission versus New mission behavior. Follow-ups inherit the selected objective, project context, evidence, results and unresolved work with provenance. 'Continue' or 'dont stop running' must not spend on a new unrelated team, invent a topic or mean infinite execution. Preserve the request and ask a focused clarification when intent is genuinely ambiguous. Acknowledge whether the instruction was applied to a running task, queued for a safe boundary, or created a bounded continuation after termination.

Workers need distinct evidence-producing assignments, not repeated generic personas. Plan research dependencies, independent critique and final synthesis. Support check-pointed, resumable multi-step research so deep work is not silently treated as a four-minute task. Use explicit overall budgets and stall detection, not unbounded loops or simply deleting timeouts. No automatic paid retries or recovery that duplicates uncertain execution. Provide explicit user-controlled recovery with attempt fencing and preserved evidence.

Show useful stages, tool activity and errors for the selected team; show relevant pending/review/synthesis dependencies. Finished work should be visible as readable reports/artifacts, not only a disappeared animation. Separate historical workers, current assignments, and available execution capacity. Explain failures inline, including missing repo/web capability and provider/tool errors, without leaking secrets.

## Phase 4 — Evidence quality and real completion
'Worker completed' is a transport/lifecycle fact, not 'research goal achieved'. Represent execution status separately from deliverable status: satisfied, partial, blocked, needs input, failed. Empty-source disclaimers are not successful deep research. Gate final research claims on evidence and task acceptance criteria while retaining useful partial output.

Require claim-to-source mappings, actual retrieval provenance, timestamps, source excerpts, confidence limitations and distinction between direct evidence, inference and proposed tests. Do not upgrade URLs or source counts to verification. Do not manufacture references. Research leads from X require primary-source corroboration before treating them as established findings. Unsupported numerical/legal/medical/investment claims must remain flagged, not polished into conclusions.

Final Tunza/EMSquared deliverable must identify actual project functionality and target-market assumptions from authorized sources, compare plausible customer segments, explain competition/distribution/pricing hypotheses, propose measurable pilot or fundraising gates, assess compute economics from explicit inputs, and clearly mark missing evidence. It must not claim regulatory clearance, clinical benefit, profitable alpha or a moat without support.

## Phase 5 — Verify and integrate
Use TDD on each reproduced failure, including actual SDK/tool transport. Run focused suites, full tests, typecheck, lint and production build from the application's real package scripts. Existing commands include bun test tests, bun run typecheck, bun run lint, bun run build; inspect package.json first. Run opt-in browser suites explicitly with the installed Playwright module; don't count skipped tests as passing.

Test: new/continued task identity; selected-team history isolation; exact team sizes up to50; concurrent tool requests; large UTF-8/backpressure; durable lease/attempt fencing; timeouts/cancellation; interrupted/restarted runners; uncertain-child capacity reservations; partial research and blocked synthesis; private-data boundaries; invalid inputs and duplicate submission; precise error feedback; saved results after refresh. Match worker output against real transport schemas. Use process tests for concurrency, not only fake rosters.

Before a live test, inspect active missions/processes. Never restart/cancel existing work silently. No unbounded paid experiments. After offline gates, use one explicitly bounded tool-using live vertical slice under an authorized budget; ask Evan for a paid validation budget/team size if not already available. Validate source reading, useful durable evidence, review and actual final deliverable. A one-worker no-tool smoke does not meet acceptance. An offline50-process scheduler test does not prove50 successful live researchers. Report both honestly.

Inventory all discovered swarm entrypoints and integrate the shared harness through small adapters, with contract tests per consumer. If broader integration requires protected repositories/permissions, finish the runnable Console slice and list precise blocked integrations rather than claiming all swarms converted. Do not replace Agentic OS scheduling without an explicit migration decision.

## Required final output
- Root-cause table: symptom, reproduced cause, changed code, regression and live evidence.
- Shared tool-harness architecture and consumer integration matrix (implemented/verified/blocked).
- Exact available capabilities per role; known exclusions and approvals.
- Real mission/task/artifact identifiers, independent readback evidence, actual usage where available, and task-quality assessment.
- Exact executed test/build commands and results; distinguish fixtures, simulated SDK transports and live provider/tool verification.
- Unresolved issues, permission/budget requests and operational exceptions.
- Short plain-English user instructions for new task, continue selected task, view results and recover failure.
- No 'done' until the named acceptance criteria are verified; do not equate merged plans or passing tests with working research.

Last word: architect. Give a concise canonical collaboration digest and provenance table, backed by independent verification.
