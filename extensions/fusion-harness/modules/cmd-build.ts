/**
 * cmd-build.ts — the commands that hold the writer lease and build things.
 *
 * /fh-collaborate: every agent plans → the architect merges ONE delegation DAG →
 *   dependency-driven execution (parallel where the DAG allows, one write-enabled
 *   child at a time) → final architect integration.
 * /fh-auto-validate: gate-first loop — the VALIDATOR writes a uv acceptance gate
 *   BEFORE any build, the BUILDER builds against it, failures feed back verbatim,
 *   with validator triage/repair escalation.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { runChild, runProc } from "./child-runner.ts";
import { validateCollaborationPlan, type CollaborationTask, type ValidatedCollaborationPlan } from "./collaboration-graph.ts";
import {
	applyCollaborationTaskOutcome,
	COLLABORATION_OUTCOME_INSTRUCTION,
	initializeCollaborationTaskStates,
	parseCollaborationTaskOutcome,
	selectCollaborationDecisionRequest,
	selectStartableCollaborationTasks,
	type CollaborationTaskOutcome,
	type CollaborationTaskStates,
} from "./collaboration-outcome.ts";
import { formatRepoStatePanel, refreshRepoStateRemote } from "./cmd-repo-state.ts";
import { orderedSlots, slotId } from "./model-stack.ts";
import { authorizeRepoAction, mintRepoActionReceipt, type RepoActionReceipt } from "./repo-action-policy.ts";
import { collectRepoState, type RepoStateCard } from "./repo-state.ts";
import {
	builderPrompt,
	collabCoordinatePrompt,
	collabDelegatePrompt,
	collabExecutePrompt,
	collabProposePrompt,
	contractSystemPrompt,
	correctionPrompt,
	ensureGateMetadata,
	extractGateScript,
	parseStrictJsonObject,
	triagePrompt,
	triageSystem,
	validatorPrompt,
	validatorSystem,
	withKnowledge,
} from "./prompt-library.ts";
import {
	clampCount,
	CUSTOM_TYPE,
	DETAIL_SNIPPET_MAX,
	FULL_TOOLS,
	GATE_TIMEOUT_MS,
	newRun,
	READONLY_TOOLS,
	runError,
	runOk,
	toStat,
	truncateChars,
	VALIDATOR_TOOLS,
	withHarnessRepoState,
	type AgentStat,
	type FhDetails,
	type HarnessDeps,
	type Role,
} from "./runtime.ts";
import { acquireWriterLease, type WriterLease } from "./writer-lease.ts";

const execFileAsync = promisify(execFile);
const PUBLISH_TIMEOUT_MS = 30_000;
const SHA40_RE = /^[0-9a-f]{40}$/i;

export function parseCollaborateArgs(raw: string): { prompt: string; publishTo: string | null } {
	const words = (raw ?? "").trim().split(/\s+/).filter(Boolean);
	let publishTo: string | null = null;
	const rest: string[] = [];
	for (let i = 0; i < words.length; i++) {
		if (words[i] === "--publish-to") {
			const value = words[i + 1];
			if (!value || value.startsWith("-")) throw new Error("Usage: /fh-collaborate [--publish-to <remote/branch>] <prompt>");
			publishTo = value;
			i++;
			continue;
		}
		rest.push(words[i]!);
	}
	return { prompt: rest.join(" "), publishTo };
}

const REMOTE_NAME_RE = /^[A-Za-z0-9._-]+$/;
const BRANCH_NAME_RE = /^[A-Za-z0-9._/-]+$/;

export function parsePublishTo(publishTo: string): { remote: string; branch: string; targetRef: string } {
	const trimmed = publishTo.trim();
	const slash = trimmed.indexOf("/");
	const remote = slash > 0 ? trimmed.slice(0, slash) : "origin";
	const branch = slash > 0 ? trimmed.slice(slash + 1) : trimmed;
	const branchParts = branch.split("/");
	if (
		trimmed.includes("..") ||
		!REMOTE_NAME_RE.test(remote) ||
		!BRANCH_NAME_RE.test(branch) ||
		branch.startsWith("-") ||
		branch.startsWith(".") ||
		branch.endsWith("/") ||
		branch.endsWith(".") ||
		branch.includes("//") ||
		branchParts.some((part) => !part || part.startsWith(".") || part.toLowerCase().endsWith(".lock")) ||
		remote.startsWith("-")
	) {
		throw new Error(`invalid --publish-to ${JSON.stringify(publishTo)}; expected <remote>/<branch>`);
	}
	// Always bind evidence to the remote-tracking ref the push will update — never local refs/heads/*.
	return { remote, branch, targetRef: `refs/remotes/${remote}/${branch}` };
}

function consumedReceiptPath(repositoryId: string): string {
	const root = path.join(fs.existsSync("/tmp") ? "/tmp" : os.tmpdir(), "fusion-harness-consumed-receipts");
	return path.join(root, `${repositoryId}.json`);
}

function loadConsumedDigests(repositoryId: string): Set<string> {
	try {
		const raw = JSON.parse(fs.readFileSync(consumedReceiptPath(repositoryId), "utf8"));
		return new Set(Array.isArray(raw) ? raw.filter((item): item is string => typeof item === "string") : []);
	} catch {
		return new Set();
	}
}

function saveConsumedDigests(repositoryId: string, consumed: Set<string>): void {
	const file = consumedReceiptPath(repositoryId);
	fs.mkdirSync(path.dirname(file), { recursive: true });
	fs.writeFileSync(file, `${JSON.stringify([...consumed].sort())}\n`);
}

async function escalateOnce(ctx: any, question: string, options: string[]): Promise<string | undefined> {
	if (typeof ctx?.ui?.select !== "function") return undefined;
	try {
		const choice = await ctx.ui.select(question, options);
		return typeof choice === "string" && options.includes(choice) ? choice : undefined;
	} catch {
		return undefined;
	}
}

async function gitCwd(cwd: string, args: string[]): Promise<{ code: number; stdout: string; stderr: string }> {
	try {
		const result = await execFileAsync("git", args, {
			cwd,
			timeout: PUBLISH_TIMEOUT_MS,
			maxBuffer: 8 * 1024 * 1024,
			env: { ...process.env, GIT_TERMINAL_PROMPT: "0", GIT_OPTIONAL_LOCKS: "0" },
		});
		return { code: 0, stdout: String(result.stdout ?? "").trim(), stderr: String(result.stderr ?? "").trim() };
	} catch (error: any) {
		if (error?.code === "ENOENT") throw new Error("git executable not found");
		const status = typeof error?.status === "number" ? error.status : 1;
		return { code: status, stdout: String(error?.stdout ?? "").trim(), stderr: String(error?.stderr ?? "").trim() };
	}
}

function publicationShortCircuit(card: RepoStateCard): { stop: boolean; kind: "noop" | "blocked" | "decision" | "continue"; message: string } {
	switch (card.verdict) {
		case "already_integrated":
			return { stop: true, kind: "noop", message: `Publication no-op: ${card.verdict} (${card.reasonCodes.join(", ") || "equal"}). Source ${card.source.sha} is already on target ${card.target.sha}.` };
		case "blocked_dirty":
		case "blocked_diverged":
		case "blocked_stale":
			return { stop: true, kind: "blocked", message: `Publication blocked: ${card.verdict} (${card.reasonCodes.join(", ")}). No spawn, no merge, no push.` };
		case "needs_decision":
			return { stop: true, kind: "decision", message: `Publication needs a decision: ${card.reasonCodes.join(", ") || card.verdict}.` };
		default:
			return { stop: false, kind: "continue", message: "" };
	}
}

async function parentOwnedPublish(opts: {
	cwd: string;
	publishTo: string;
	artifactsDir: string;
	runId: string;
	consumed: Set<string>;
}): Promise<{ ok: boolean; message: string; receipt?: RepoActionReceipt }> {
	const parsed = parsePublishTo(opts.publishTo);
	const headBefore = (await gitCwd(opts.cwd, ["rev-parse", "HEAD"])).stdout.toLowerCase();
	if (!SHA40_RE.test(headBefore)) return { ok: false, message: "Publication refused: HEAD is not a 40-hex SHA." };
	const started = Date.now();
	const check = await gitCwd(opts.cwd, ["diff", "--check"]);
	const porcelain = await gitCwd(opts.cwd, ["status", "--porcelain=v1", "--untracked-files=all"]);
	const headAfter = (await gitCwd(opts.cwd, ["rev-parse", "HEAD"])).stdout.toLowerCase();
	const durationMs = Date.now() - started;
	const failed = (check.code === 0 && !porcelain.stdout ? 0 : 1);
	const preFacts = await collectRepoState(opts.cwd, { sourceRef: "HEAD", targetRef: parsed.targetRef });
	const observedTarget = preFacts.target.sha;
	if (!observedTarget) return { ok: false, message: `Publication refused: target ${parsed.targetRef} does not resolve.` };
	const receipt = mintRepoActionReceipt({
		repositoryId: preFacts.identity.repositoryId,
		gitCommonDir: preFacts.identity.gitCommonDir,
		worktreeId: preFacts.identity.worktreeId,
		runId: opts.runId,
		candidateSha: headBefore,
		observedTargetSha: observedTarget,
		headBefore,
		headAfter,
		issuedAt: Date.now(),
		validation: {
			command: ["git", "diff", "--check"],
			exitCode: failed === 0 ? 0 : 1,
			passed: failed === 0 ? 1 : 0,
			failed,
			durationMs,
		},
	});
	const consumed = new Set([...opts.consumed, ...loadConsumedDigests(preFacts.identity.repositoryId)]);
	await refreshRepoStateRemote(opts.cwd, parsed.remote);
	const facts = await collectRepoState(opts.cwd, { sourceRef: "HEAD", targetRef: parsed.targetRef });
	const decision = authorizeRepoAction({ receipt, facts, consumedDigests: consumed });
	consumed.add(receipt.digest);
	opts.consumed.add(receipt.digest);
	for (const digest of consumed) opts.consumed.add(digest);
	saveConsumedDigests(preFacts.identity.repositoryId, consumed);
	await fs.promises.writeFile(path.join(opts.artifactsDir, "publication-receipt.json"), `${JSON.stringify({ receipt, decision }, null, 2)}\n`, "utf8");
	await fs.promises.writeFile(path.join(opts.artifactsDir, "consumed-receipts.json"), `${JSON.stringify([...consumed].sort())}\n`, "utf8");
	if (!decision.authorize) {
		return { ok: false, message: `Publication refused: ${decision.verdict} (${decision.reasons.join(", ")}).`, receipt };
	}
	if (decision.verdict === "authorize_noop") {
		return { ok: true, message: `Publication no-op: ${decision.reasons.join(", ")}. Nothing pushed.`, receipt };
	}
	if (!decision.nonForceFastForward || !decision.candidateSha) {
		return { ok: false, message: `Publication refused: authorization was not a non-force fast-forward.`, receipt };
	}
	const refspec = `${decision.candidateSha}:refs/heads/${parsed.branch}`;
	if (refspec.startsWith("+")) return { ok: false, message: "Publication refused: force refspec.", receipt };
	const pushed = await gitCwd(opts.cwd, ["push", "--no-force", parsed.remote, refspec]);
	if (pushed.code !== 0) {
		return { ok: false, message: `git push --no-force failed: ${pushed.stderr || pushed.stdout || `exit ${pushed.code}`}`, receipt };
	}
	return { ok: true, message: `Pushed ${refspec} to ${parsed.remote} (non-force).`, receipt };
}

// ═══ /fh-collaborate ═════════════════════════════════════════════════════════

export function registerCollaborateCommand(pi: ExtensionAPI, h: HarnessDeps): (raw: string, ctx: any) => Promise<void> {
	let handler: (raw: string, ctx: any) => Promise<void>;
	// No fixed deliberation choreography: each slot proposes how the work should be done,
	// the ARCHITECT turns those proposals into one delegation DAG, and the executor runs
	// on dependency READINESS — a task starts the moment its dependencies are done.
	// Independent tasks overlap (reads freely; writes one at a time through the global
	// writer token); dependent tasks form sequential paths. A slot may own several tasks —
	// its persistent session runs them one at a time. Every intermediate result renders:
	// proposals as an opinion-style grid, the plan as a task breakdown, and each finished
	// task as its own report panel. The live N-column grid streams for the whole command;
	// the task board is a separate belowEditor sub-widget.
	const TASKBOARD_WIDGET = `${CUSTOM_TYPE}-taskboard`;
	pi.registerCommand("fh-collaborate", {
		description:
			"Every agent plans read-only, the architect merges one delegation DAG, then tasks execute as dependencies clear — parallel where possible, exactly one shared-CWD writer at a time. Optional --publish-to <remote/branch> is parent-owned non-force fast-forward only.",
		handler: handler = async (raw, ctx) => {
			h.noteHost(ctx);
			let parsedArgs: { prompt: string; publishTo: string | null };
			try {
				parsedArgs = parseCollaborateArgs(raw ?? "");
			} catch (error) {
				ctx.ui.notify(error instanceof Error ? error.message : String(error), "warning");
				return;
			}
			const prompt = parsedArgs.prompt;
			let publishTo = parsedArgs.publishTo;
			if (!prompt) {
				ctx.ui.notify("Usage: /fh-collaborate [--publish-to <remote/branch>] <prompt>", "warning");
				return;
			}
			const stack = h.modelStack();
			const slots = orderedSlots(stack);
			const runs = slots.map(h.newSlotRun);
			const runBySlot = new Map(runs.map((run) => [run.slot!.id, run]));
			const startedAt = Date.now();
			const artifactsDir = await h.mkArtifacts();
			const collabDir = path.join(artifactsDir, "collaborate");
			await fs.promises.mkdir(collabDir, { recursive: true });
			await h.save(artifactsDir, "prompt.md", prompt);
			await h.save(artifactsDir, "stack.json", JSON.stringify(stack, null, 2));
			let repoCard: RepoStateCard | undefined;
			let repoCardMarkdown = "";
			let repoRefreshed = false;
			let writerLease: WriterLease | undefined;
			try {
				let targetRef: string | undefined;
				if (publishTo) {
					const parsedTarget = parsePublishTo(publishTo);
					targetRef = parsedTarget.targetRef;
					writerLease = acquireWriterLease(ctx.cwd, `/fh-collaborate ${path.basename(artifactsDir)}`);
					await refreshRepoStateRemote(ctx.cwd, parsedTarget.remote);
					repoRefreshed = true;
				}
				repoCard = await collectRepoState(ctx.cwd, targetRef ? { sourceRef: "HEAD", targetRef } : undefined);
				repoCardMarkdown = formatRepoStatePanel(repoCard);
				await h.save(collabDir, "repo-state.json", JSON.stringify(repoCard, null, 2));
				h.panel({ kind: "repo-state", command: "fh-collaborate", ok: true, repoVerdict: repoCard.verdict, repoRefreshed, artifactsDir }, repoCardMarkdown);
			} catch (error) {
				const message = error instanceof Error ? error.message : String(error);
				if (publishTo) {
					h.panel({ kind: "error", command: "fh-collaborate", ok: false, artifactsDir }, `Publication fail-closed: cannot measure repository state.\n${message}`);
					writerLease?.release();
					return;
				}
			}
			if (publishTo && repoCard) {
				const gate = publicationShortCircuit(repoCard);
				if (gate.stop && gate.kind === "decision") {
					const choice = await escalateOnce(ctx, `${gate.message} Publish, abort, or continue without publishing?`, ["abort", "continue without publishing"]);
					if (choice === "continue without publishing") {
						publishTo = null;
					} else {
						h.panel({ kind: "error", command: "fh-collaborate", ok: false, artifactsDir }, `${gate.message} Fail closed${choice ? ` (${choice})` : " without UI"}.`);
						await h.save(artifactsDir, "summary.json", JSON.stringify({ command: "fh-collaborate", ok: false, shortCircuit: gate.kind, publishTo, repoHash: repoCard.hash, repoVerdict: repoCard.verdict, agents: [] }, null, 2));
						writerLease?.release();
						return;
					}
				} else if (gate.stop) {
					const ok = gate.kind === "noop";
					h.panel({ kind: ok ? "collab" : "error", command: "fh-collaborate", ok, artifactsDir }, gate.message);
					await h.save(artifactsDir, "summary.json", JSON.stringify({ command: "fh-collaborate", ok, shortCircuit: gate.kind, publishTo, repoHash: repoCard.hash, repoVerdict: repoCard.verdict, agents: [] }, null, 2));
					writerLease?.release();
					return;
				}
			}
			const packet = await h.prepareKnowledge(prompt, ctx.cwd, artifactsDir);
			const initialSpawns = new Map(slots.map((slot) => [slot.id, h.slotInitialSpawn(slot, ctx, path.join(collabDir, "sessions", slot.id))]));
			h.panel({ kind: "prompt", command: "fh-collaborate", ok: true }, `/fh-collaborate ${publishTo ? `--publish-to ${publishTo} ` : ""}${prompt}`);
			h.panel({ kind: "banner", command: "fh-collaborate", ok: true, prompt, roles: slots.map((slot) => ({ role: (slot.architect ? "ARCHITECT" : "BUILDER") as Role, model: slot.model, slotId: slot.id, slotName: slot.name, color: slot.color, primary: slot.primary, architect: slot.architect })), artifactsDir }, "");
			const stopper = h.startStoppable(ctx, "fh-collaborate");
			// The streaming grid stays alive for the WHOLE command — planning, delegation,
			// and execution all show each model's live flow, exactly like the other commands.
			const stopWidget = h.startGridWidget(ctx, "fh-collaborate", runs, undefined, startedAt);
			let maxConcurrentWriteEnabledChildren = 0;
			let activeWriters = 0;
			const taskExecutions: Array<{ taskId: string; slot: string; mode: "read" | "write"; startedAt: number; endedAt: number; ok: boolean }> = [];
			let plan: ValidatedCollaborationPlan | undefined;
			try {
				// ── Phase 1: every slot PLANS the work independently, read-only ──
				ctx.ui.setStatus(CUSTOM_TYPE, `collaborate: ${slots.length} agents planning read-only…`);
				const proposalsDir = path.join(collabDir, "proposals");
				await fs.promises.mkdir(proposalsDir, { recursive: true });
				await Promise.all(runs.map(async (run) => {
					const slot = run.slot!;
					await runChild({ run, prompt: withHarnessRepoState(withKnowledge(collabProposePrompt(slot, stack, prompt), packet), repoCardMarkdown), systemPrompt: slot.systemPrompt, appendSystemPrompts: slot.appendSystemPrompts, tools: READONLY_TOOLS, thinking: slot.thinking, ...initialSpawns.get(slot.id)!, cwd: ctx.cwd, timeoutMs: h.childTimeoutMs(), signal: stopper.signal });
					await h.save(proposalsDir, `${slot.id}.md`, runOk(run) ? run.text : `FAILED: ${runError(run)}`);
				}));
				if (stopper.stopped()) {
					h.stoppedPanel("fh-collaborate", runs, artifactsDir, startedAt, "Stopped during planning; completed proposals remain on disk.");
					return;
				}
				// The proposals render like /fh-opinion — the intermediate step is part of the output.
				h.panel({ kind: "multi", command: "fh-collaborate", title: "⇄ PROPOSALS — how each agent would do the work", ok: runs.every(runOk), prompt, sources: runs.map(toStat), answers: runs.map((run) => ({ role: run.role, model: run.model, text: runOk(run) ? run.text : `FAILED: ${runError(run)}`, slotId: run.slot!.id, slotName: run.slot!.name, color: run.slot!.color, primary: run.slot!.primary })), artifactsDir, ...h.totals(runs, startedAt) }, runs.map((run) => `## ${run.slot!.name}\n${runOk(run) ? run.text : `FAILED: ${runError(run)}`}`).join("\n\n"));
				if (runs.filter(runOk).length < 2) {
					h.panel({ kind: "error", command: "fh-collaborate", ok: false, sources: runs.map(toStat), artifactsDir, ...h.totals(runs, startedAt) }, "Collaboration needs at least two successful plans.");
					return;
				}

				// ── Phase 2: the ARCHITECT merges the proposals into ONE delegation DAG ──
				const architectRun = runBySlot.get(stack.architect.id)!;
				const planPath = path.join(collabDir, "plan.json");
				let planError = "";
				for (let attempt = 1; attempt <= 3; attempt++) {
					ctx.ui.setStatus(CUSTOM_TYPE, `collaborate: architect merging plans into a delegation graph${attempt > 1 ? ` (repair ${attempt - 1})` : ""}…`);
					const delegatePrompt = withHarnessRepoState(collabDelegatePrompt(stack, prompt, collabDir, planPath) + (planError ? `\n\nPREVIOUS PLAN VALIDATION FAILED:\n${planError}\nRewrite the complete corrected plan.` : ""), repoCardMarkdown);
					await runChild({ run: architectRun, prompt: delegatePrompt, systemPrompt: contractSystemPrompt(stack.architect.systemPrompt, "SYSTEM_PROMPT_COLLAB_COORDINATOR.md"), appendSystemPrompts: stack.architect.appendSystemPrompts, tools: READONLY_TOOLS, thinking: stack.architect.thinking, ...h.slotNextSpawn(stack.architect, architectRun, initialSpawns.get(stack.architect.id)!, ctx), cwd: ctx.cwd, timeoutMs: h.childTimeoutMs(), signal: stopper.signal });
					if (stopper.stopped()) {
						h.stoppedPanel("fh-collaborate", runs, artifactsDir, startedAt, "Stopped while the architect was producing the delegation graph.");
						return;
					}
					try {
						const parsedPlan = parseStrictJsonObject(architectRun.text, "delegation plan");
						// Models echo the roster's [MAIN]-style uppercase labels — normalize
						// assignees through slotId() so casing never costs a repair round.
						if (Array.isArray((parsedPlan as Record<string, unknown>).tasks)) {
							for (const rawTask of (parsedPlan as { tasks: unknown[] }).tasks) {
								if (rawTask && typeof rawTask === "object" && typeof (rawTask as Record<string, unknown>).assignee === "string") {
									(rawTask as Record<string, string>).assignee = slotId((rawTask as Record<string, string>).assignee);
								}
							}
						}
						plan = validateCollaborationPlan(parsedPlan, slots.map((slot) => slot.id));
						await fs.promises.writeFile(planPath, `${JSON.stringify(parsedPlan, null, 2)}\n`, "utf8");
						const assigned = new Set(plan.tasks.map((task) => task.assignee));
						const missing = slots.filter((slot) => !assigned.has(slot.id));
						if (missing.length) throw new Error(`plan must assign meaningful work to every slot; missing ${missing.map((slot) => slot.id).join(", ")}`);
						break;
					} catch (error) {
						planError = error instanceof Error ? error.message : String(error);
						plan = undefined;
					}
				}
				if (!plan) {
					h.panel({ kind: "error", command: "fh-collaborate", ok: false, agent: toStat(architectRun), artifactsDir }, `Architect could not produce a valid delegation graph after 3 attempts:\n${planError}`);
					return;
				}
				// The task breakdown is itself a deliverable — render it before executing.
				const planBody = [
					`### Delegation plan — ${plan.tasks.length} task${plan.tasks.length === 1 ? "" : "s"} · ${plan.waves.length} dependency level${plan.waves.length === 1 ? "" : "s"}`,
					"",
					"| task | owner | mode | depends on |",
					"|---|---|---|---|",
					...plan.tasks.map((task) => `| ${task.id} | ${task.assignee} | ${task.mode} | ${task.depends_on.join(", ") || "—"} |`),
					"",
					`Parallelism by level: ${plan.waves.map((wave, index) => `${index + 1}) ${wave.map((task) => task.id).join(" ∥ ")}`).join("  →  ")}`,
					"",
					...plan.tasks.map((task) => `- **${task.id}** (${task.assignee}, ${task.mode}) — ${task.description}`),
				].join("\n");
				h.panel({ kind: "solo", command: "fh-collaborate", ok: true, agent: toStat(architectRun), artifactsDir }, planBody);

				try {
					writerLease ??= acquireWriterLease(ctx.cwd, `/fh-collaborate ${path.basename(artifactsDir)}`);
				} catch (error) {
					h.panel({ kind: "error", command: "fh-collaborate", ok: false, sources: runs.map(toStat), artifactsDir }, error instanceof Error ? error.message : String(error));
					return;
				}

				// ── Phase 3: dependency-driven execution ──
				// A task launches the moment its deps are done AND its slot is free; reads
				// overlap anything, writes wait for the single global writer token (the
				// activeWriters increment is synchronous inside executeTask, so at most one
				// write-enabled child ever runs). Plan order is the FIFO tiebreak.
				const reportsDir = path.join(collabDir, "reports");
				await fs.promises.mkdir(reportsDir, { recursive: true });
				let taskStates: CollaborationTaskStates = initializeCollaborationTaskStates(plan.tasks);
				const taskOutcomes = new Map<string, CollaborationTaskOutcome>();
				const taskReports = new Map<string, string>();
				const busySlots = new Set<string>();
				const inFlight = new Map<string, Promise<void>>();
				let executionFailure: string | undefined;
				const TASK_GLYPH: Record<string, string> = { pending: "○", queued: "◌", reading: "◐", writing: "●", completed: "✓", no_op: "–", blocked: "■", needs_decision: "?", failed: "✗", skipped: "·" };
				const renderBoard = () => {
					try {
						const done = Object.values(taskStates).filter((state) => state === "completed" || state === "no_op").length;
						ctx.ui.setWidget(TASKBOARD_WIDGET, [
							`⇄ TASKS · ${done}/${plan!.tasks.length} settled · reads overlap · ONE writer at a time`,
							...plan!.tasks.map((task) => `  ${TASK_GLYPH[taskStates[task.id]!] ?? "○"} ${task.id} · ${task.assignee} · ${task.mode} · ${taskStates[task.id]} · ${task.description.replace(/\s+/g, " ").slice(0, 60)}${task.description.length > 60 ? "…" : ""}`),
						], { placement: "belowEditor" });
					} catch {}
				};
				const taskHandoff = (task: CollaborationTask): string => {
					const parts = [`Collaboration artifacts: ${collabDir}`, `Delegation plan: ${planPath}`, `All finished task reports: ${reportsDir}`];
					for (const dep of task.depends_on) parts.push(`\n## COMPLETED DEPENDENCY ${dep}\n${taskReports.get(dep) ?? "(report on disk)"}`);
					return parts.join("\n");
				};
				const executeTask = async (task: CollaborationTask): Promise<void> => {
					const slot = slots.find((candidate) => candidate.id === task.assignee)!;
					const run = runBySlot.get(slot.id)!;
					const taskStartedAt = Date.now();
					const write = task.mode === "write";
					// Synchronous before the first await — the scheduler's writer check relies on it.
					if (write) {
						activeWriters++;
						maxConcurrentWriteEnabledChildren = Math.max(maxConcurrentWriteEnabledChildren, activeWriters);
					}
					const executePrompt = `${write && packet.captureEnabled ? withKnowledge(collabExecutePrompt(slot, prompt, task, taskHandoff(task)), { ...packet, promptBlock: "" }, { writeCapable: true }) : collabExecutePrompt(slot, prompt, task, taskHandoff(task))}\n\n${COLLABORATION_OUTCOME_INSTRUCTION}`;
					try {
						await runChild({ run, prompt: withHarnessRepoState(executePrompt, repoCardMarkdown), systemPrompt: slot.systemPrompt, appendSystemPrompts: slot.appendSystemPrompts, tools: write ? FULL_TOOLS : READONLY_TOOLS, thinking: slot.thinking, ...h.slotNextSpawn(slot, run, initialSpawns.get(slot.id)!, ctx), cwd: ctx.cwd, timeoutMs: h.childTimeoutMs(), signal: stopper.signal });
					} finally {
						if (write) activeWriters--;
					}
					const childOk = runOk(run) && !stopper.stopped();
					const rawReport = childOk ? run.text : `FAILED: ${runError(run)}`;
					let outcome: CollaborationTaskOutcome | undefined;
					if (childOk) {
						try {
							const parsedOutcome = parseCollaborationTaskOutcome(run.text);
							outcome = parsedOutcome.outcome;
						} catch (error) {
							executionFailure ??= `task ${task.id} (${slot.id}) failed closed: ${error instanceof Error ? error.message : String(error)}`;
						}
					} else {
						executionFailure ??= `task ${task.id} (${slot.id}) failed: ${runError(run)}`;
					}
					if (outcome) {
						const applied = applyCollaborationTaskOutcome(plan!.tasks, taskStates, task.id, outcome);
						taskStates = applied.states;
						taskOutcomes.set(task.id, outcome);
						for (const skippedId of applied.skippedTaskIds) {
							taskReports.set(skippedId, `SKIPPED after ${task.id} ${outcome.status}`);
							await h.save(reportsDir, `${skippedId}-skipped.md`, taskReports.get(skippedId)!);
						}
						if (outcome.status === "needs_decision") {
							const decision = selectCollaborationDecisionRequest(plan!.tasks, taskOutcomes);
							const choice = decision ? await escalateOnce(ctx, decision.question, decision.options) : undefined;
							if (choice) await h.save(reportsDir, `${task.id}-decision.json`, JSON.stringify({ taskId: task.id, choice, ...decision }, null, 2));
							executionFailure ??= decision
								? `needs_decision from ${decision.taskId}: ${decision.question} [${decision.options.join(" | ")}]${choice ? ` → ${choice}` : " (fail closed without UI)"}`
								: `needs_decision from ${task.id}`;
						}
					} else {
						taskStates = { ...taskStates, [task.id]: "failed" };
					}
					const ok = Boolean(outcome) && (outcome!.status === "completed" || outcome!.status === "no_op") && !executionFailure?.startsWith(`task ${task.id}`);
					taskExecutions.push({ taskId: task.id, slot: slot.id, mode: task.mode, startedAt: taskStartedAt, endedAt: Date.now(), ok });
					taskReports.set(task.id, rawReport);
					await h.save(reportsDir, `${task.id}-${slot.id}.md`, rawReport);
					if (!stopper.stopped()) {
						h.panel({ kind: "solo", command: "fh-collaborate", ok, agent: toStat(run), artifactsDir }, `### Task ${task.id} (${task.mode}) — ${slot.name}\n${task.description}\n\n${rawReport}`);
					}
				};
				ctx.ui.setStatus(CUSTOM_TYPE, "collaborate: executing the delegation graph…");
				renderBoard();
				while (!stopper.stopped()) {
					if (!executionFailure) {
						const startable = selectStartableCollaborationTasks(plan.tasks, taskStates, busySlots, activeWriters > 0);
						for (const taskId of startable) {
							const task = plan.tasks.find((candidate) => candidate.id === taskId)!;
							busySlots.add(task.assignee);
							taskStates = { ...taskStates, [task.id]: task.mode === "read" ? "reading" : "writing" };
							const running = executeTask(task).finally(() => {
								busySlots.delete(task.assignee);
								inFlight.delete(task.id);
							});
							inFlight.set(task.id, running);
						}
					}
					renderBoard();
					if (!inFlight.size) break;
					await Promise.race(inFlight.values());
				}
				await Promise.allSettled([...inFlight.values()]);
				renderBoard();
				if (stopper.stopped()) {
					h.stoppedPanel("fh-collaborate", runs, artifactsDir, startedAt, "Stopped during delegated execution; finished task reports remain on disk.");
					return;
				}
				if (executionFailure) {
					h.panel({ kind: "error", command: "fh-collaborate", ok: false, sources: runs.map(toStat), artifactsDir, ...h.totals(runs, startedAt) }, `Delegated execution halted: ${executionFailure}. Downstream tasks were not started.`);
					return;
				}
				const graphBlocked = Object.values(taskStates).some((state) => state === "blocked" || state === "failed" || state === "needs_decision");
				if (graphBlocked) {
					h.panel({ kind: "error", command: "fh-collaborate", ok: false, sources: runs.map(toStat), artifactsDir, ...h.totals(runs, startedAt) }, "Final write integration skipped: a task is blocked, failed, or awaiting a decision.");
					return;
				}

				// ── Phase 4: one final architect integration turn, still under the single-writer invariant ──
				ctx.ui.setStatus(CUSTOM_TYPE, "collaborate: final architect integration…");
				const finalStartedAt = Date.now();
				activeWriters++;
				maxConcurrentWriteEnabledChildren = Math.max(maxConcurrentWriteEnabledChildren, activeWriters);
				try {
					await runChild({ run: architectRun, prompt: withHarnessRepoState(collabCoordinatePrompt(prompt, reportsDir, planPath), repoCardMarkdown), systemPrompt: contractSystemPrompt(stack.architect.systemPrompt, "SYSTEM_PROMPT_COLLAB_COORDINATOR.md"), appendSystemPrompts: stack.architect.appendSystemPrompts, tools: FULL_TOOLS, thinking: stack.architect.thinking, ...h.slotNextSpawn(stack.architect, architectRun, initialSpawns.get(stack.architect.id)!, ctx), cwd: ctx.cwd, timeoutMs: h.childTimeoutMs(), signal: stopper.signal });
				} finally {
					activeWriters--;
				}
				taskExecutions.push({ taskId: "final", slot: stack.architect.id, mode: "write", startedAt: finalStartedAt, endedAt: Date.now(), ok: runOk(architectRun) && !stopper.stopped() });
				if (stopper.stopped()) {
					h.stoppedPanel("fh-collaborate", runs, artifactsDir, startedAt, "Stopped during final architect integration.");
					return;
				}
				await h.save(collabDir, "final.md", runOk(architectRun) ? architectRun.text : `FAILED: ${runError(architectRun)}`);
				const worktreeCommandsObserved = runs.flatMap((run) => run.toolEvents).filter((event) => event.name === "bash" && /\bgit\s+worktree\b/.test(event.argument));
				let ok = runOk(architectRun) && maxConcurrentWriteEnabledChildren === 1 && worktreeCommandsObserved.length === 0;
				let publishResult: { ok: boolean; message: string } | undefined;
				if (ok && publishTo) {
					const consumed = new Set<string>();
					publishResult = await parentOwnedPublish({
						cwd: ctx.cwd,
						publishTo,
						artifactsDir,
						runId: path.basename(artifactsDir),
						consumed,
					});
					ok = ok && publishResult.ok;
					h.panel({ kind: publishResult.ok ? "collab" : "error", command: "fh-collaborate", ok: publishResult.ok, artifactsDir }, publishResult.message);
				}
				h.panel({ kind: "collab", command: "fh-collaborate", ok, round: plan.tasks.length, prompt, agent: toStat(architectRun), sources: runs.map(toStat), artifactsDir, ...h.totals(runs, startedAt) }, runOk(architectRun) ? architectRun.text : `Final coordination failed: ${runError(architectRun)}`);
				await h.captureKnowledge({ cwd: ctx.cwd, runId: path.basename(artifactsDir), texts: [architectRun.text, ...runs.map((run) => run.text)], command: "fh-collaborate", artifactsDir });
				await h.save(artifactsDir, "summary.json", JSON.stringify({ command: "fh-collaborate", ok, plan, knowledgeHash: packet.hash, publishTo, publishResult, repoHash: repoCard?.hash, repoVerdict: repoCard?.verdict, taskExecutions, maxConcurrentWriteEnabledChildren, worktreeCommandsObserved, writerLeasePath: writerLease?.path, agents: runs.map(toStat), sessions: Object.fromEntries(slots.map((slot) => [slot.id, runs.find((run) => run.slot?.id === slot.id)?.sessionRef ?? h.cachedSlotId(slot)])), ...h.totals(runs, startedAt) }, null, 2));
			} finally {
				const observedWorktrees = runs.flatMap((run) => run.toolEvents).filter((event) => event.name === "bash" && /\bgit\s+worktree\b/.test(event.argument));
				await h.ensureSummary(artifactsDir, { command: "fh-collaborate", ok: false, stopped: stopper.stopped(), plan, taskExecutions, maxConcurrentWriteEnabledChildren, worktreeCommandsObserved: observedWorktrees, writerLeasePath: writerLease?.path, agents: runs.map(toStat), sessions: Object.fromEntries(slots.map((slot) => [slot.id, runs.find((run) => run.slot?.id === slot.id)?.sessionRef ?? h.cachedSlotId(slot)])), ...h.totals(runs, startedAt) });
				writerLease?.release();
				stopper.release();
				stopWidget();
				try { ctx.ui.setWidget(TASKBOARD_WIDGET, undefined); } catch {}
				ctx.ui.setStatus(CUSTOM_TYPE, undefined);
			}
		},
	});
	return handler;
}

// ═══ /fh-auto-validate ═══════════════════════════════════════════════════════
// Gate-first validation loop (red → green):
//   1. VALIDATOR designs the acceptance gate (uv script) BEFORE any work happens.
//   2. Baseline gate run — expected FAIL (integrity check on the gate itself).
//   3. BUILDER builds against the visible, immutable gate.
//   4. Gate runs. FAIL → its output feeds back into the builder's persistent
//      session as correction instructions. PASS → done.
//   5. After --max-validations failed validations, development HALTS loudly.

const MAX_VALIDATIONS_DEFAULT = 5;
const ESCALATE_DEFAULT = 3;
const clampValidations = (n: number): number => clampCount(n, MAX_VALIDATIONS_DEFAULT);

/** A gate result that means "the gate itself could not run" — never the builder's fault. */
const gateHarnessError = (g: { code: number; output: string }): string | undefined => {
	if (g.code === 124 || g.output.includes("[gate timed out]")) return "the gate timed out (gates must finish in <60s)";
	if (g.code === 127 || /failed to spawn|spawn error/.test(g.output)) return "the gate could not be executed — is `uv` installed and on PATH?";
	return undefined;
};

export function registerAutoValidateCommand(pi: ExtensionAPI, h: HarnessDeps): (raw: string, ctx: any) => Promise<void> {
	let handler: (raw: string, ctx: any) => Promise<void>;
	pi.registerCommand("fh-auto-validate", {
		description:
			"Auto-validation loop: VALIDATOR designs a uv acceptance gate FIRST, BUILDER builds, the gate runs, failures feed back to the builder — until pass or --max-validations (default 5)",
		handler: handler = async (raw, ctx) => {
			h.noteHost(ctx); // an unset --builder follows the host session's live model
			let input = (raw ?? "").trim();
			// Inline overrides of the startup flags: /fh-auto-validate --max-validations 3 --escalate-to-validator-count 2 <prompt>
			let maxV = clampValidations(Number.parseInt(h.flagStr("max-validations"), 10));
			let escalateAt = clampCount(Number.parseInt(h.flagStr("escalate-to-validator-count"), 10), ESCALATE_DEFAULT);
			input = input
				.replace(/--max-validations[=\s]+(\d+)\s*/g, (_m, n) => {
					maxV = clampValidations(Number.parseInt(n, 10));
					return "";
				})
				.replace(/--escalate-to-validator-count[=\s]+(\d+)\s*/g, (_m, n) => {
					escalateAt = clampCount(Number.parseInt(n, 10), ESCALATE_DEFAULT);
					return "";
				})
				.trim();
			if (!input) {
				ctx.ui.notify("Usage: /fh-auto-validate [--max-validations N] [--escalate-to-validator-count N] <prompt>", "warning");
				return;
			}
			const prompt = input;
			const aModel = h.architectModel();
			const bModel = h.builderModel();
			const startedAt = Date.now();
			const artifactsDir = await h.mkArtifacts();
			await h.save(artifactsDir, "prompt.md", prompt);
			const packet = await h.prepareKnowledge(prompt, ctx.cwd, artifactsDir);

			h.panel({ kind: "prompt", command: "fh-auto-validate", ok: true }, `/fh-auto-validate ${(raw ?? "").trim()}`);
			h.panel(
				{
					kind: "banner",
					command: "fh-auto-validate",
					ok: true,
					prompt,
					maxRounds: maxV,
					escalateAt,
					roles: [
						{ role: "VALIDATOR", model: aModel },
						{ role: "BUILDER", model: bModel },
					],
					artifactsDir,
				},
				"",
			);

			const validator = newRun("VALIDATOR", aModel, h.modelStack().architect);
			const builder = newRun("BUILDER", bModel, h.modelStack().primaryBuilder);
			// Columns match the footer: VALIDATOR (architect-family) left, BUILDER right.
			// One builder AgentRun is reused across correction rounds — same persistent
			// session, cumulative tokens/cost, one accumulating flow column.
			const stopper = h.startStoppable(ctx, "auto-validate");
			const stopWidget = h.startWidget(ctx, "auto-validate", [validator, builder], undefined, startedAt);
			let writerLease: WriterLease | undefined;
			const fail = (agentStat: AgentStat, body: string, extra: Partial<FhDetails> = {}) => {
				const t = h.totals([validator, builder], startedAt);
				h.panel({ kind: "error", command: "fh-auto-validate", ok: false, agent: agentStat, artifactsDir, maxRounds: maxV, ...t, ...extra }, body);
			};

			try {
				try {
					writerLease = acquireWriterLease(ctx.cwd, `/fh-auto-validate ${path.basename(artifactsDir)}`);
				} catch (error) {
					fail(toStat(builder), error instanceof Error ? error.message : String(error));
					return;
				}
				// ── 1. VALIDATOR designs the gate (before any build) ──
				// The gate's transport is the FILESYSTEM: the harness dictates an absolute path and
				// the validator writes gate.py there with its own write tool. Nothing is parsed out
				// of the reply, so a gate whose own source contains ``` survives intact.
				const scriptPath = path.join(artifactsDir, "gate.py");
				ctx.ui.setStatus(CUSTOM_TYPE, "auto-validate: validator designing the gate…");
				await runChild({
					run: validator,
					prompt: withKnowledge(validatorPrompt(prompt, ctx.cwd, scriptPath), packet),
					systemPrompt: validatorSystem(scriptPath),
					tools: VALIDATOR_TOOLS,
					thinking: h.roleThinking("architect"),
					sessionDir: h.roleSession("architect", ctx.cwd).dir,
					sessionId: h.roleSession("architect", ctx.cwd).id,
					cwd: ctx.cwd,
					timeoutMs: h.childTimeoutMs(),
					signal: stopper.signal,
				});
				await h.save(artifactsDir, "validator.md", runOk(validator) ? validator.text : `FAILED: ${runError(validator)}`);
				// Prefer the file the validator wrote. Fence extraction is the legacy fallback,
				// used only when it pasted the gate inline instead (lossy — see extractGateScript).
				let script: string | undefined;
				let gateVia = "written to disk by the validator";
				if (runOk(validator)) {
					try {
						script = ensureGateMetadata(await fs.promises.readFile(scriptPath, "utf-8"));
					} catch {
						/* validator didn't write the file — fall back to the fence */
					}
					if (!script) {
						script = extractGateScript(validator.text);
						if (script) gateVia = "recovered from a code fence (legacy — truncates at an embedded ```)";
					}
				}
				if (stopper.stopped()) {
					h.stoppedPanel("auto-validate", [validator, builder], artifactsDir, startedAt, "The validator was killed while designing the gate; nothing was built.");
					return;
				}
				if (!script) {
					const stat = toStat(validator);
					if (!stat.error) stat.error = `did not write a uv gate script to ${scriptPath}`;
					fail(
						stat,
						`✗ VALIDATOR (${aModel}) failed to design the acceptance gate — nothing was built.\nExpected the gate at ${scriptPath}; no file was written and no fenced script was found in its reply.\n\n${validator.text || ""}`,
					);
					return;
				}
				// Only rewrite when the content differs (fence fallback, or injected metadata), so a
				// gate the validator wrote itself executes byte-for-byte as authored.
				let onDisk: string | undefined;
				try {
					onDisk = await fs.promises.readFile(scriptPath, "utf-8");
				} catch {
					/* not written yet */
				}
				if (onDisk !== script) await h.save(artifactsDir, "gate.py", script);
				validator.flow.push({ type: "tool", label: `gate.py — ${gateVia} (${script.length} bytes)` });

				// ── 2. Baseline gate run — must FAIL before the build (red) ──
				ctx.ui.setStatus(CUSTOM_TYPE, "auto-validate: baseline gate run (expected FAIL)…");
				const baseline = await runProc("uv", ["run", scriptPath], ctx.cwd, GATE_TIMEOUT_MS, stopper.signal);
				await h.save(artifactsDir, "gate-baseline.txt", `exit ${baseline.code}\n\n${baseline.output}`);
				validator.flow.push({ type: "tool", label: `uv run gate.py (baseline) → exit ${baseline.code}` });
				if (stopper.stopped()) {
					h.stoppedPanel("auto-validate", [validator, builder], artifactsDir, startedAt, "Stopped at the baseline gate run; nothing was built.");
					return;
				}
				const baselineHarnessErr = gateHarnessError(baseline);
				if (baselineHarnessErr) {
					const stat = toStat(validator);
					stat.error = `gate execution error: ${baselineHarnessErr}`;
					fail(stat, `✗ GATE ERROR — ${baselineHarnessErr}\n\nNothing was built. Gate output:\n\`\`\`\n${truncateChars(baseline.output.trim(), DETAIL_SNIPPET_MAX)}\n\`\`\``);
					return;
				}
				const baselineNote =
					baseline.code === 0
						? `### ⚠ BASELINE WARNING\nThe gate already PASSES before any work was done — either the request is already satisfied or the gate is too weak. Proceeding to build anyway; treat a first-round pass with suspicion.`
						: `### Baseline run — RED ✓ (exit ${baseline.code}, expected)\nThe gate correctly fails against the current state — the loop is live.\n\`\`\`\n${truncateChars(baseline.output.trim() || "(no output)", DETAIL_SNIPPET_MAX)}\n\`\`\``;
				h.panel(
					{
						kind: "gate",
						command: "fh-auto-validate",
						ok: true,
						agent: toStat(validator),
						maxRounds: maxV,
						script: truncateChars(script, DETAIL_SNIPPET_MAX),
						gateExitCode: baseline.code,
						scriptPath,
						artifactsDir,
					},
					[`### Acceptance gate (designed by VALIDATOR before the build; immutable)`, "```python", script.trim(), "```", baselineNote].join("\n"),
				);

				// ── 3. Build → validate loop ──
				// Round 1 forks the host session (the builder IS the host's agent lineage);
				// later rounds resume that same fork so the loop keeps its working memory.
				let lastGate: { code: number; output: string } | undefined;
				const gateHistory: Array<{ round: number; code: number; output: string }> = [];
				let pendingTriage: string | undefined;
				let pendingGateUpdate: string | undefined; // repaired gate → next correction prompt (round-1 copy is stale)
				let gateRepairUsed = false; // ONE repair per run — the grader never gets to keep moving goalposts
				const firstSpawn = h.builderSpawn(ctx, artifactsDir);
				for (let round = 1; round <= maxV; round++) {
					const triageBrief = pendingTriage;
					pendingTriage = undefined;
					const gateUpdate = pendingGateUpdate;
					pendingGateUpdate = undefined;
					const spawn =
						round === 1
							? firstSpawn
							: builder.sessionRef
								? { sessionDir: firstSpawn.sessionDir, resume: builder.sessionRef }
								: firstSpawn;
					ctx.ui.setStatus(CUSTOM_TYPE, `auto-validate: builder — round ${round}/${maxV}…`);
					await runChild({
						run: builder,
						prompt: round === 1 ? withKnowledge(builderPrompt(prompt, script), packet, { writeCapable: true }) : correctionPrompt(round, maxV, lastGate!.code, lastGate!.output, triageBrief, gateUpdate),
						systemPrompt: h.roleSystemPrompt("builder"),
						appendSystemPrompts: h.modelStack().primaryBuilder.appendSystemPrompts,
						tools: FULL_TOOLS,
						thinking: h.roleThinking("builder"),
						...spawn,
						cwd: ctx.cwd,
						timeoutMs: h.buildTimeoutMs(),
						signal: stopper.signal,
					});
					await h.save(artifactsDir, `builder-round-${round}.md`, runOk(builder) ? builder.text : `FAILED: ${runError(builder)}`);
					// Check the stop BEFORE blaming the builder: an escape-killed child is !runOk,
					// and reporting "BUILDER failed" for a user-initiated stop is a lie.
					if (stopper.stopped()) {
						h.stoppedPanel("auto-validate", [validator, builder], artifactsDir, startedAt, `Stopped during build round ${round}/${maxV}; the gate was not re-run.`);
						return;
					}
					if (!runOk(builder)) {
						fail(
							toStat(builder),
							`✗ BUILDER (${bModel}) failed during round ${round}/${maxV} — the loop cannot continue.\n\n${builder.text || ""}`,
							{ round, sources: [toStat(validator)] },
						);
						return;
					}

					ctx.ui.setStatus(CUSTOM_TYPE, `auto-validate: gate — validation ${round}/${maxV}…`);
					lastGate = await runProc("uv", ["run", scriptPath], ctx.cwd, GATE_TIMEOUT_MS, stopper.signal);
					await h.save(artifactsDir, `gate-round-${round}.txt`, `exit ${lastGate.code}\n\n${lastGate.output}`);
					validator.flow.push({ type: "tool", label: `uv run gate.py (round ${round}) → exit ${lastGate.code}` });
					if (stopper.stopped()) {
						h.stoppedPanel("auto-validate", [validator, builder], artifactsDir, startedAt, `Stopped at the gate run for round ${round}/${maxV}.`);
						return;
					}
					const harnessErr = gateHarnessError(lastGate);
					if (harnessErr) {
						const stat = toStat(validator);
						stat.error = `gate execution error: ${harnessErr}`;
						fail(stat, `✗ GATE ERROR during validation ${round}/${maxV} — ${harnessErr}\n\nGate output:\n\`\`\`\n${truncateChars(lastGate.output.trim(), DETAIL_SNIPPET_MAX)}\n\`\`\``, { round });
						return;
					}

					const ok = lastGate.code === 0;
					const t = h.totals([validator, builder], startedAt);
					const gateBody = [
						`### Gate run — ${ok ? "PASS (exit 0)" : `FAIL (exit ${lastGate.code})`}`,
						"```",
						truncateChars(lastGate.output.trim() || "(no output)", DETAIL_SNIPPET_MAX * 2),
						"```",
						ok && baseline.code === 0 ? `⚠ Note: the gate also passed at baseline — verify the result yourself.` : "",
					].join("\n");
					const builderBody = `### Builder report — round ${round}\n${builder.text}`;
					h.panel(
						{
							kind: "validation",
							command: "fh-auto-validate",
							ok,
							round,
							maxRounds: maxV,
							agent: toStat(validator),
							sources: [toStat(validator), toStat(builder)],
							answers: [
								{ role: "VALIDATOR", model: aModel, text: gateBody },
								{ role: "BUILDER", model: bModel, text: builderBody },
							],
							gateOutput: truncateChars(lastGate.output, DETAIL_SNIPPET_MAX),
							gateExitCode: lastGate.code,
							scriptPath,
							artifactsDir,
							...t,
						},
						`${builderBody}\n\n${gateBody}`,
					);
					if (ok) {
						await h.captureKnowledge({ cwd: ctx.cwd, runId: path.basename(artifactsDir), texts: [builder.text], command: "fh-auto-validate", artifactsDir });
						await h.save(
							artifactsDir,
							"summary.json",
							JSON.stringify(
								{ command: "fh-auto-validate", ok: true, rounds: round, maxValidations: maxV, escalateAt, gateExitCode: 0, knowledgeHash: packet.hash, agents: [toStat(validator), toStat(builder)], sessions: { architect: validator.sessionRef ?? h.cachedRoleId("architect"), builder: builder.sessionRef ?? h.cachedRoleId("builder") }, ...t },
								null,
								2,
							),
						);
						return;
					}

					// ── Escalation: on the Nth failure, the VALIDATOR diagnoses why the builder is stuck ──
					gateHistory.push({ round, code: lastGate.code, output: lastGate.output });
					if (round >= escalateAt && round < maxV) {
						ctx.ui.setStatus(CUSTOM_TYPE, `auto-validate: ⚡ validator triage (failure ${round}/${maxV})…`);
						// Snapshot the gate as it sits on disk BEFORE triage — the repair detector
						// compares content, not the brief's wording.
						let gateBefore = script;
						try {
							gateBefore = await fs.promises.readFile(scriptPath, "utf-8");
						} catch {
							/* keep the in-memory copy */
						}
						await runChild({
							run: validator,
							prompt: triagePrompt(prompt, round, maxV, builder.text, gateHistory, artifactsDir),
							systemPrompt: triageSystem(scriptPath),
							// Repair power is enforced by TOOLS, not trust: while the run's single
							// repair is unused, triage holds the validator's write (one dictated
							// path); once spent, it drops back to strictly read-only eyes.
							tools: gateRepairUsed ? READONLY_TOOLS : VALIDATOR_TOOLS,
							thinking: h.roleThinking("architect"),
							sessionDir: h.roleSession("architect", ctx.cwd).dir,
							sessionId: h.roleSession("architect", ctx.cwd).id,
							cwd: ctx.cwd,
							timeoutMs: h.childTimeoutMs(),
							signal: stopper.signal,
						});
						await h.save(artifactsDir, `triage-round-${round}.md`, runOk(validator) ? validator.text : `FAILED: ${runError(validator)}`);
						if (runOk(validator)) {
							pendingTriage = validator.text;
							h.panel(
								{
									kind: "triage",
									command: "fh-auto-validate",
									ok: true,
									round,
									maxRounds: maxV,
									escalateAt,
									agent: toStat(validator),
									artifactsDir,
								},
								validator.text,
							);

							// ── Gate repair: triage rewrote a defective gate (once per run) ──
							if (!gateRepairUsed) {
								let gateAfter: string | undefined;
								try {
									gateAfter = await fs.promises.readFile(scriptPath, "utf-8");
								} catch {
									/* unreadable — treat as unchanged */
								}
								if (gateAfter?.trim() && gateAfter !== gateBefore) {
									gateRepairUsed = true;
									await h.save(artifactsDir, `gate.py.r${round}`, gateBefore); // the defective gate, preserved for audit
									script = ensureGateMetadata(gateAfter) ?? gateAfter;
									if (script !== gateAfter) await h.save(artifactsDir, "gate.py", script);
									pendingGateUpdate = script;
									validator.flow.push({ type: "tool", label: `gate.py REPAIRED (defect) — old gate saved as gate.py.r${round}` });

									// The repaired gate re-runs IMMEDIATELY, on the house: a gate defect
									// was never the builder's failure, so it costs no correction round.
									ctx.ui.setStatus(CUSTOM_TYPE, "auto-validate: gate repaired — free re-run…");
									const rerun = await runProc("uv", ["run", scriptPath], ctx.cwd, GATE_TIMEOUT_MS, stopper.signal);
									await h.save(artifactsDir, `gate-repair-round-${round}.txt`, `exit ${rerun.code}\n\n${rerun.output}`);
									validator.flow.push({ type: "tool", label: `uv run gate.py (post-repair) → exit ${rerun.code}` });
									if (stopper.stopped()) {
										h.stoppedPanel("auto-validate", [validator, builder], artifactsDir, startedAt, `Stopped at the post-repair gate run (round ${round}/${maxV}).`);
										return;
									}
									const rerunHarnessErr = gateHarnessError(rerun);
									if (rerunHarnessErr) {
										const stat = toStat(validator);
										stat.error = `gate execution error: ${rerunHarnessErr}`;
										fail(stat, `✗ GATE ERROR on the post-repair run — ${rerunHarnessErr}\n\nGate output:\n\`\`\`\n${truncateChars(rerun.output.trim(), DETAIL_SNIPPET_MAX)}\n\`\`\``, { round });
										return;
									}
									h.panel(
										{
											kind: "gate",
											command: "fh-auto-validate",
											ok: rerun.code === 0,
											round,
											maxRounds: maxV,
											agent: toStat(validator),
											script: truncateChars(script, DETAIL_SNIPPET_MAX),
											gateExitCode: rerun.code,
											scriptPath,
											artifactsDir,
										},
										[
											`### ⚒ Gate REPAIRED by VALIDATOR — defect fixed after round ${round} (old gate: gate.py.r${round} · one repair per run)`,
											"```python",
											script.trim(),
											"```",
											rerun.code === 0
												? `### Post-repair run — GREEN ✓ (exit 0, no builder round consumed)\n\`\`\`\n${truncateChars(rerun.output.trim() || "(no output)", DETAIL_SNIPPET_MAX)}\n\`\`\``
												: `### Post-repair run — still RED (exit ${rerun.code}) — these are now the REAL failures\n\`\`\`\n${truncateChars(rerun.output.trim() || "(no output)", DETAIL_SNIPPET_MAX)}\n\`\`\``,
										].join("\n"),
									);
									if (rerun.code === 0) {
										// The build was right all along — the gate was the bug. End green.
										const tt = h.totals([validator, builder], startedAt);
										const gateBody2 = `### Gate run — PASS (exit 0, post-repair)\n\`\`\`\n${truncateChars(rerun.output.trim() || "(no output)", DETAIL_SNIPPET_MAX * 2)}\n\`\`\``;
										const builderBody2 = `### Builder report — round ${round}\n${builder.text}`;
										h.panel(
											{
												kind: "validation",
												command: "fh-auto-validate",
												ok: true,
												round,
												maxRounds: maxV,
												agent: toStat(validator),
												sources: [toStat(validator), toStat(builder)],
												answers: [
													{ role: "VALIDATOR", model: aModel, text: gateBody2 },
													{ role: "BUILDER", model: bModel, text: builderBody2 },
												],
												gateOutput: truncateChars(rerun.output, DETAIL_SNIPPET_MAX),
												gateExitCode: 0,
												scriptPath,
												artifactsDir,
												...tt,
											},
											`${builderBody2}\n\n${gateBody2}`,
										);
										await h.save(
											artifactsDir,
											"summary.json",
											JSON.stringify(
												{ command: "fh-auto-validate", ok: true, rounds: round, gateRepaired: true, maxValidations: maxV, escalateAt, gateExitCode: 0, agents: [toStat(validator), toStat(builder)], sessions: { architect: validator.sessionRef ?? h.cachedRoleId("architect"), builder: builder.sessionRef ?? h.cachedRoleId("builder") }, ...tt },
												null,
												2,
											),
										);
										return;
									}
									// Still red on a now-sound gate: those failures are real — hand them
									// to the next correction round.
									lastGate = rerun;
									gateHistory.push({ round, code: rerun.code, output: rerun.output });
								}
							}
						} else {
							// Triage is an enhancement — a failed triage never blocks the loop.
							validator.flow.push({ type: "tool", label: `triage failed (${runError(validator)}) — continuing with raw gate output` });
						}
					}
				}

				// ── 4. Max validations exhausted — halt loudly ──
				const stat = toStat(builder);
				stat.error = `gate still failing after ${maxV}/${maxV} validations`;
				fail(
					stat,
					[
						`## ✗ HALTED — development stopped after ${maxV}/${maxV} validations`,
						`The acceptance gate is still failing. No further corrections will be attempted.`,
						``,
						`### Last gate output (exit ${lastGate?.code ?? "?"})`,
						"```",
						truncateChars(lastGate?.output.trim() || "(no output)", DETAIL_SNIPPET_MAX),
						"```",
						``,
						`Raise the cap with \`--max-validations N\` (startup flag or inline) or inspect the artifacts: ${artifactsDir}`,
					].join("\n"),
					{ round: maxV },
				);
				await h.save(
					artifactsDir,
					"summary.json",
					JSON.stringify(
						{ command: "fh-auto-validate", ok: false, halted: true, rounds: maxV, maxValidations: maxV, escalateAt, gateExitCode: lastGate?.code, agents: [toStat(validator), toStat(builder)], sessions: { architect: validator.sessionRef ?? h.cachedRoleId("architect"), builder: builder.sessionRef ?? h.cachedRoleId("builder") }, ...h.totals([validator, builder], startedAt) },
						null,
						2,
					),
				);
			} finally {
				await h.ensureSummary(artifactsDir, { command: "fh-auto-validate", ok: false, stopped: stopper.stopped(), agents: [toStat(validator), toStat(builder)], sessions: { architect: validator.sessionRef ?? h.cachedRoleId("architect"), builder: builder.sessionRef ?? h.cachedRoleId("builder") }, ...h.totals([validator, builder], startedAt) });
				writerLease?.release();
				stopper.release(); // never leave the escape tap installed past the command
				stopWidget();
				ctx.ui.setStatus(CUSTOM_TYPE, undefined);
			}
		},
	});
	return handler;
}
