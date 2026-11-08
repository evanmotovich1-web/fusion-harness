/**
 * collaboration-run.ts — one collaboration run.
 *
 * The command paints and sends host recovery. This module decides the run.
 * child and escalate are the only ports. Host callbacks are optional effects.
 */
import { execFile } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { promisify } from "node:util";
import { validateCollaborationPlan, type CollaborationTask, type ValidatedCollaborationPlan } from "./collaboration-graph.ts";
import {
	applyCollaborationTaskOutcome,
	COLLABORATION_OUTCOME_INSTRUCTION,
	collaborationDescendantIds,
	initializeCollaborationTaskStates,
	parseCollaborationTaskOutcome,
	selectCollaborationDecisionRequest,
	selectStartableCollaborationTasks,
	type CollaborationTaskOutcome,
	type CollaborationTaskStates,
} from "./collaboration-outcome.ts";
import { formatRepoStatePanel, refreshRepoStateRemote } from "./cmd-repo-state.ts";
import type { KnowledgePacket } from "./knowledge-base.ts";
import type { KnowledgeCaptureResult } from "./knowledge-ingest.ts";
import { orderedSlots, slotId, type ModelSlot, type ModelStack, type Thinking } from "./model-stack.ts";
import {
	collabCoordinatePrompt,
	collabDelegatePrompt,
	collabExecutePrompt,
	collabProposePrompt,
	contractSystemPrompt,
	parseStrictJsonObject,
	withKnowledge,
} from "./prompt-library.ts";
import { authorizeRepoAction, mintRepoActionReceipt, type RepoActionReceipt } from "./repo-action-policy.ts";
import { collectRepoState, type RepoStateCard } from "./repo-state.ts";
import {
	CUSTOM_TYPE,
	FULL_TOOLS,
	READONLY_TOOLS,
	runError,
	runOk,
	toStat,
	withHarnessRepoState,
	type AgentRun,
	type FhDetails,
	type Role,
} from "./runtime.ts";
import { tmpRoot } from "./tmp-root.ts";
import { waitForWriterLease, type WriterLease } from "./writer-lease.ts";

const execFileAsync = promisify(execFile);
const PUBLISH_TIMEOUT_MS = 30_000;
const SHA40_RE = /^[0-9a-f]{40}$/i;
const REMOTE_NAME_RE = /^[A-Za-z0-9._-]+$/;
const BRANCH_NAME_RE = /^[A-Za-z0-9._/-]+$/;
const TASKBOARD_WIDGET = `${CUSTOM_TYPE}-taskboard`;

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
	const root = path.join(tmpRoot(), "fusion-harness-consumed-receipts");
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


export interface CollaborationChildCall {
	run: AgentRun;
	slot: ModelSlot;
	prompt: string;
	systemPrompt?: string;
	appendSystemPrompts?: string[];
	tools: string;
	thinking?: Thinking;
	signal?: AbortSignal;
	onQuotaWait?: (waitMs: number, error: string) => void;
	spawn: "initial" | "next";
	sessionDir: string;
}

export interface CollaborationRunPorts {
	child: (call: CollaborationChildCall) => Promise<void>;
	escalate: (question: string, options: string[]) => Promise<string | undefined>;
}

export interface CollaborationHostRecovery {
	planPath: string;
	reportsDir: string;
	finalPath: string;
	artifactsDir: string;
}

export interface CollaborationRunResult {
	hostRecovery?: CollaborationHostRecovery;
}

export interface CollaborationRunRequest {
	prompt: string;
	publishTo: string | null;
	ctx: any;
	stack: ModelStack;
	newSlotRun: (slot: ModelSlot) => AgentRun;
	mkArtifacts: () => Promise<string>;
	save: (dir: string, name: string, body: string) => Promise<void>;
	prepareKnowledge: (query: string, cwd: string, artifactsDir: string) => Promise<KnowledgePacket>;
	startStoppable: (ctx: any, command: string) => { signal: AbortSignal; stopped: () => boolean; release: () => void };
	startGridWidget: (ctx: any, command: string, runs: AgentRun[], span: AgentRun | undefined, startedAt: number) => () => void;
	totals: (runs: AgentRun[], startedAt: number) => { totalMs: number; totalCostUsd: number };
	ensureSummary: (dir: string, payload: Record<string, unknown>) => Promise<void>;
	captureKnowledge: (opts: { cwd: string; runId: string; texts: string[]; command: string; artifactsDir?: string }) => Promise<KnowledgeCaptureResult>;
	cachedSlotId: (slot: ModelSlot) => string | undefined;
	childTimeoutMs: () => number;
	noteHost?: (ctx: any) => void;
	panel?: (details: FhDetails, content: string) => void;
	stoppedPanel?: (command: string, runs: AgentRun[], artifactsDir: string, startedAt: number, what: string) => void;
	setStatus?: (type: string, text?: string) => void;
	notify?: (text: string, level?: string) => void;
	setWidget?: (id: string, lines?: string[], opts?: { placement?: string }) => void;
}

export async function runCollaboration(request: CollaborationRunRequest, ports: CollaborationRunPorts): Promise<CollaborationRunResult> {
	const input = { prompt: request.prompt, publishTo: request.publishTo };
	const ctx = request.ctx;
	const result: CollaborationRunResult = {};
	const h = {
		noteHost: request.noteHost ?? (() => {}),
		modelStack: () => request.stack,
		newSlotRun: request.newSlotRun,
		mkArtifacts: request.mkArtifacts,
		save: request.save,
		panel: request.panel ?? ((_details: FhDetails, _content: string) => {}),
		prepareKnowledge: request.prepareKnowledge,
		startStoppable: request.startStoppable,
		startGridWidget: request.startGridWidget,
		totals: request.totals,
		stoppedPanel: request.stoppedPanel ?? ((_command: string, _runs: AgentRun[], _artifactsDir: string, _startedAt: number, _what: string) => {}),
		ensureSummary: request.ensureSummary,
		captureKnowledge: request.captureKnowledge,
		cachedSlotId: request.cachedSlotId,
		childTimeoutMs: request.childTimeoutMs,
	};
	const setStatus = request.setStatus ?? ((type: string, text?: string) => ctx.ui.setStatus(type, text));
	const notify = request.notify ?? ((text: string, level?: string) => ctx.ui.notify(text, level));
	const setWidget = request.setWidget ?? ((id: string, lines?: string[], opts?: { placement?: string }) => ctx.ui.setWidget(id, lines, opts));
	const escalateOnce = async (_ctx: any, question: string, options: string[]): Promise<string | undefined> => ports.escalate(question, options);
	let collabDir = "";
	const runChild = async (opts: {
		run: AgentRun;
		prompt: string;
		systemPrompt?: string;
		appendSystemPrompts?: string[];
		tools: string;
		thinking?: Thinking;
		signal?: AbortSignal;
		onQuotaWait?: (waitMs: number, error: string) => void;
		spawn: "initial" | "next";
	}): Promise<void> => {
		const slot = opts.run.slot;
		if (!slot) throw new Error("collaboration child is missing its slot");
		await ports.child({
			run: opts.run,
			slot,
			prompt: opts.prompt,
			systemPrompt: opts.systemPrompt,
			appendSystemPrompts: opts.appendSystemPrompts,
			tools: opts.tools,
			thinking: opts.thinking,
			signal: opts.signal,
			onQuotaWait: opts.onQuotaWait,
			spawn: opts.spawn,
			sessionDir: path.join(collabDir, "sessions", slot.id),
		});
	};

	const prompt = input.prompt;
	let publishTo = input.publishTo;
	h.noteHost(ctx);
	if (!prompt) {
		notify("Usage: /fh-collaborate [--publish-to <remote/branch>] <prompt>", "warning");
		return result;
	}
	const stack = h.modelStack();
	const slots = orderedSlots(stack);
	const runs = slots.map(h.newSlotRun);
	const runBySlot = new Map(runs.map((run) => [run.slot!.id, run]));
	const startedAt = Date.now();
	const artifactsDir = await h.mkArtifacts();
	collabDir = path.join(artifactsDir, "collaborate");
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
			writerLease = await waitForWriterLease(ctx.cwd, `/fh-collaborate ${path.basename(artifactsDir)}`, { onWait: (holder) => setStatus(CUSTOM_TYPE, `waiting for the writer lease — ${holder}`) });
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
			return result;
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
				return result;
			}
		} else if (gate.stop) {
			const ok = gate.kind === "noop";
			h.panel({ kind: ok ? "collab" : "error", command: "fh-collaborate", ok, artifactsDir }, gate.message);
			await h.save(artifactsDir, "summary.json", JSON.stringify({ command: "fh-collaborate", ok, shortCircuit: gate.kind, publishTo, repoHash: repoCard.hash, repoVerdict: repoCard.verdict, agents: [] }, null, 2));
			writerLease?.release();
			return result;
		}
	}
	const packet = await h.prepareKnowledge(prompt, ctx.cwd, artifactsDir);
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
		setStatus(CUSTOM_TYPE, `collaborate: ${slots.length} agents planning read-only…`);
		const proposalsDir = path.join(collabDir, "proposals");
		await fs.promises.mkdir(proposalsDir, { recursive: true });
		// A builder out of provider quota is benched for this run instead of stalling
		// everyone until its reset (run futyZD sat ~1.5h on two z.ai models). The
		// architect is required, so it waits — visibly, with the reset time.
		const quotaBenched = new Map<string, { model: string; until?: string; error: string; reason: "provider quota" | "proposal failed — provider unavailable" }>();
		await Promise.all(runs.map(async (run) => {
			const slot = run.slot!;
			const own = new AbortController();
			const onStop = () => own.abort();
			stopper.signal.addEventListener("abort", onStop, { once: true });
			const onQuotaWait = (waitMs: number, error: string) => {
				const until = new Date(Date.now() + waitMs).toLocaleTimeString();
				if (slot.architect) {
					setStatus(CUSTOM_TYPE, `collaborate: architect ${slot.name} (${slot.model}) is out of provider quota — waiting, next try ${until}`);
					return;
				}
				quotaBenched.set(slot.id, { model: slot.model, until, error: error.slice(0, 200), reason: "provider quota" });
				setStatus(CUSTOM_TYPE, `collaborate: benched ${[...quotaBenched.keys()].join(", ")} (provider quota) — continuing with the rest`);
				own.abort();
			};
			try {
				await runChild({ run, prompt: withHarnessRepoState(withKnowledge(collabProposePrompt(slot, stack, prompt), packet), repoCardMarkdown), systemPrompt: slot.systemPrompt, appendSystemPrompts: slot.appendSystemPrompts, tools: READONLY_TOOLS, thinking: slot.thinking, spawn: "initial", signal: own.signal, onQuotaWait });
			} finally {
				stopper.signal.removeEventListener("abort", onStop);
			}
			if (!runOk(run) && !stopper.stopped() && !quotaBenched.has(slot.id)) {
				quotaBenched.set(slot.id, { model: slot.model, error: runError(run).slice(0, 200), reason: "proposal failed — provider unavailable" });
			}
			const benched = quotaBenched.get(slot.id);
			await h.save(proposalsDir, `${slot.id}.md`, benched
				? benched.reason === "provider quota"
					? `BENCHED: ${slot.model} is out of provider quota (next try ${benched.until}); left out of this run.\n${benched.error}`
					: `BENCHED: ${slot.model} proposal failed — provider unavailable; left out of this run.\n${benched.error}`
				: run.text);
		}));
		if (quotaBenched.size) {
			await h.save(collabDir, "quota-benched.json", JSON.stringify(Object.fromEntries(quotaBenched), null, 2));
			notify(`fh-collaborate: left out ${[...quotaBenched.entries()].map(([id, b]) => `${id} (${b.model}, ${b.reason}${b.until ? ` until ~${b.until}` : ""})`).join(", ")}`, "warning");
		}
		const activeSlots = slots.filter((slot) => runOk(runBySlot.get(slot.id)!));
		if (stopper.stopped()) {
			h.stoppedPanel("fh-collaborate", runs, artifactsDir, startedAt, "Stopped during planning; completed proposals remain on disk.");
			return result;
		}
		// The proposals render like /fh-opinion — the intermediate step is part of the output.
		h.panel({ kind: "multi", command: "fh-collaborate", title: "⇄ PROPOSALS — how each agent would do the work", ok: runs.every(runOk), prompt, sources: runs.map(toStat), answers: runs.map((run) => ({ role: run.role, model: run.model, text: runOk(run) ? run.text : `FAILED: ${runError(run)}`, slotId: run.slot!.id, slotName: run.slot!.name, color: run.slot!.color, primary: run.slot!.primary })), artifactsDir, ...h.totals(runs, startedAt) }, runs.map((run) => `## ${run.slot!.name}\n${runOk(run) ? run.text : `FAILED: ${runError(run)}`}`).join("\n\n"));
		if (!activeSlots.length) {
			h.panel({ kind: "error", command: "fh-collaborate", ok: false, sources: runs.map(toStat), artifactsDir, ...h.totals(runs, startedAt) }, "no successful proposals — every configured slot is unavailable");
			return result;
		}
		const successfulActiveRuns = activeSlots.filter((slot) => runOk(runBySlot.get(slot.id)!)).length;
		if (successfulActiveRuns < Math.min(2, activeSlots.length)) {
			h.panel({ kind: "error", command: "fh-collaborate", ok: false, sources: runs.map(toStat), artifactsDir, ...h.totals(runs, startedAt) }, "Collaboration needs at least two successful plans when two or more slots are available.");
			return result;
		}

		// ── Phase 2: the ARCHITECT merges the proposals into ONE delegation DAG ──
		const architectSlot = activeSlots.find((slot) => slot.id === stack.architect.id) ?? activeSlots.find((slot) => slot.primary) ?? activeSlots[0]!;
		const architectRun = runBySlot.get(architectSlot.id)!;
		const planPath = path.join(collabDir, "plan.json");
		let planError = "";
		for (let attempt = 1; attempt <= 3; attempt++) {
			setStatus(CUSTOM_TYPE, `collaborate: architect merging plans into a delegation graph${attempt > 1 ? ` (repair ${attempt - 1})` : ""}…`);
			const benchedNote = quotaBenched.size ? `\n\nUNAVAILABLE THIS RUN (provider unavailable): ${[...quotaBenched.keys()].join(", ")}. Assign them NO tasks; every other slot still needs meaningful work.` : "";
			const delegatePrompt = withHarnessRepoState(collabDelegatePrompt(stack, prompt, collabDir, planPath) + benchedNote + (planError ? `\n\nPREVIOUS PLAN VALIDATION FAILED:\n${planError}\nRewrite the complete corrected plan.` : ""), repoCardMarkdown);
			await runChild({ run: architectRun, prompt: delegatePrompt, systemPrompt: contractSystemPrompt(architectSlot.systemPrompt, "SYSTEM_PROMPT_COLLAB_COORDINATOR.md"), appendSystemPrompts: architectSlot.appendSystemPrompts, tools: READONLY_TOOLS, thinking: architectSlot.thinking, spawn: "next", signal: stopper.signal });
			if (stopper.stopped()) {
				h.stoppedPanel("fh-collaborate", runs, artifactsDir, startedAt, "Stopped while the architect was producing the delegation graph.");
				return result;
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
				plan = validateCollaborationPlan(parsedPlan, activeSlots.map((slot) => slot.id));
				await fs.promises.writeFile(planPath, `${JSON.stringify(parsedPlan, null, 2)}\n`, "utf8");
				const assigned = new Set(plan.tasks.map((task) => task.assignee));
				const missing = activeSlots.filter((slot) => !assigned.has(slot.id));
				if (missing.length) throw new Error(`plan must assign meaningful work to every slot; missing ${missing.map((slot) => slot.id).join(", ")}`);
				break;
			} catch (error) {
				planError = error instanceof Error ? error.message : String(error);
				plan = undefined;
			}
		}
		if (!plan) {
			h.panel({ kind: "error", command: "fh-collaborate", ok: false, agent: toStat(architectRun), artifactsDir }, `Architect could not produce a valid delegation graph after 3 attempts:\n${planError}`);
			return result;
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

		let admissionFailure: string | undefined;
		try {
			writerLease ??= await waitForWriterLease(ctx.cwd, `/fh-collaborate ${path.basename(artifactsDir)}`, { signal: stopper.signal, onWait: (holder) => setStatus(CUSTOM_TYPE, `waiting for the writer lease — ${holder}`) });
		} catch (error) {
			admissionFailure = error instanceof Error ? error.message : String(error);
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
		let executionFailure: string | undefined = admissionFailure;
		const lastRejection = new Map<string, string>();
		const quotaWaits: Array<{ taskId: string; slot: string; error: string; waitMs: number; at: number }> = [];
		const repairCycles = new Map<string, number>();
		const repairLog: Array<{ owner: string; verifier: string; cycle: number; childTimeoutMs: number; startedAt: number }> = [];
		const attempts = new Map<string, number>();
		const skippedBy = new Map<string, string[]>();
		const TASK_GLYPH: Record<string, string> = { pending: "○", queued: "◌", reading: "◐", writing: "●", completed: "✓", no_op: "–", blocked: "■", needs_decision: "?", failed: "✗", skipped: "·" };
		const renderBoard = () => {
			try {
				const done = Object.values(taskStates).filter((state) => state === "completed" || state === "no_op").length;
				setWidget(TASKBOARD_WIDGET, [
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
		const executeTask = async (task: CollaborationTask, repairBrief = ""): Promise<void> => {
			const attempt = (attempts.get(task.id) ?? 0) + 1;
			attempts.set(task.id, attempt);
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
				// runChild already waits out a provider quota (429) and reruns; here we only surface it.
				const onQuotaWait = (waitMs: number, error: string) => {
					quotaWaits.push({ taskId: task.id, slot: slot.id, error: error.slice(0, 300), waitMs, at: Date.now() });
					void h.save(collabDir, "quota-waits.json", JSON.stringify(quotaWaits, null, 2));
					setStatus(CUSTOM_TYPE, `collaborate: ${task.id} (${slot.id}) hit a provider quota — retrying at ${new Date(Date.now() + waitMs).toLocaleTimeString()}`);
				};
				await runChild({ run, prompt: withHarnessRepoState(executePrompt + `\n${repairBrief}`, repoCardMarkdown), systemPrompt: slot.systemPrompt, appendSystemPrompts: slot.appendSystemPrompts, tools: write ? FULL_TOOLS : READONLY_TOOLS, thinking: slot.thinking, spawn: "next", signal: stopper.signal, onQuotaWait });
			} finally {
				if (write) activeWriters--;
			}
			let childOk = runOk(run) && !stopper.stopped();
			let rawReport = childOk ? run.text : `FAILED: ${runError(run)}`;
			let outcome: CollaborationTaskOutcome | undefined;
			if (childOk) {
				try {
					outcome = parseCollaborationTaskOutcome(run.text).outcome;
				} catch (error) {
					// A read-only task can safely be rerun once. Never invent a metadata
					// receipt from prose, and never replay a write with uncertain effects.
					const reason = error instanceof Error ? error.message : String(error);
					if (!write && !stopper.stopped()) {
						await h.save(reportsDir, `${task.id}-attempt-${attempt}-invalid.md`, rawReport);
						await runChild({ run, prompt: withHarnessRepoState(`${executePrompt}\n\nREAD-ONLY REPORT RETRY: your previous response failed the outcome contract (${reason}). Recheck your findings and return a complete report ending in exactly one FH_TASK_OUTCOME metadata line. Do not claim unverified work or copy a sample marker into the body.`, repoCardMarkdown), systemPrompt: slot.systemPrompt, appendSystemPrompts: slot.appendSystemPrompts, tools: READONLY_TOOLS, thinking: slot.thinking, spawn: "next", signal: stopper.signal });
					childOk = runOk(run) && !stopper.stopped();
					rawReport = childOk ? run.text : `FAILED: ${runError(run)}`;
					if (childOk) {
						try { outcome = parseCollaborationTaskOutcome(run.text).outcome; }
						catch (retryError) { executionFailure ??= `task ${task.id} (${slot.id}) failed closed after report retry: ${retryError instanceof Error ? retryError.message : String(retryError)}`; }
					} else executionFailure ??= `task ${task.id} (${slot.id}) failed during report retry: ${runError(run)}`;
					} else executionFailure ??= `task ${task.id} (${slot.id}) failed closed: ${reason}`;
				}
			} else {
				executionFailure ??= `task ${task.id} (${slot.id}) failed: ${runError(run)}`;
			}
			if (outcome) {
				const applied = applyCollaborationTaskOutcome(plan!.tasks, taskStates, task.id, outcome);
				taskStates = applied.states;
				taskOutcomes.set(task.id, outcome);
				skippedBy.set(task.id, applied.skippedTaskIds);
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
				taskOutcomes.delete(task.id);
				taskStates = { ...taskStates, [task.id]: "failed" };
			}
			const ok = Boolean(outcome) && (outcome!.status === "completed" || outcome!.status === "no_op") && !executionFailure?.startsWith(`task ${task.id}`);
			taskExecutions.push({ taskId: task.id, slot: slot.id, mode: task.mode, startedAt: taskStartedAt, endedAt: Date.now(), ok });
			taskReports.set(task.id, rawReport);
			await h.save(reportsDir, `${task.id}-attempt-${attempt}.md`, rawReport);
			await h.save(reportsDir, `${task.id}-${slot.id}.md`, rawReport);
			if (!stopper.stopped()) {
				h.panel({ kind: "solo", command: "fh-collaborate", ok, agent: toStat(run), artifactsDir }, `### Task ${task.id} (${task.mode}) — ${slot.name}\n${task.description}\n\n${rawReport}`);
			}
		};
		setStatus(CUSTOM_TYPE, "collaborate: executing the delegation graph…");
		renderBoard();
		while (!stopper.stopped()) {
			// A blocked or failed task stops only its own descendants (they stay skipped/pending);
			// every independent branch keeps running. Only a refused writer lease stops all work.
			if (!admissionFailure) {
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
			if (!inFlight.size) {
				// Owner repair: a read-mode verifier rejected its write-mode dependency and named it.
				// No cycle cap and no per-cycle prompt — repairs repeat while the verifier keeps
				// producing NEW rejection evidence. An identical rejection means no progress: stop.
				const repair = admissionFailure ? undefined : plan.tasks.map((verifier) => {
					const outcome = taskStates[verifier.id] === "blocked" ? taskOutcomes.get(verifier.id) : undefined;
					const owner = outcome?.repair_target ? plan.tasks.find((task) => task.id === outcome.repair_target) : undefined;
					const rejection = taskReports.get(verifier.id) ?? "";
					const eligible = verifier.mode === "read" && owner?.mode === "write" && owner.assignee !== verifier.assignee && verifier.depends_on.includes(owner.id) && (taskStates[owner.id] === "completed" || taskStates[owner.id] === "no_op") && lastRejection.get(verifier.id) !== rejection;
					return eligible ? { verifier, owner: owner!, rejection } : undefined;
				}).find(Boolean);
				if (repair && !stopper.stopped()) {
					const { verifier, owner, rejection } = repair;
					lastRejection.set(verifier.id, rejection);
					const cycle = (repairCycles.get(verifier.id) ?? 0) + 1;
					repairCycles.set(verifier.id, cycle);
					repairLog.push({ owner: owner.id, verifier: verifier.id, cycle, childTimeoutMs: h.childTimeoutMs(), startedAt: Date.now() });
					await h.save(collabDir, "repairs.json", JSON.stringify(repairLog, null, 2));
					taskStates[owner.id] = "writing";
					await executeTask(owner, `OWNER REPAIR — cycle ${cycle}. Repair only your original implementation scope; no live/release, publication, new permissions or weakened acceptance. Rejection evidence:\n${rejection}`);
					if (!stopper.stopped() && (taskStates[owner.id] === "completed" || taskStates[owner.id] === "no_op")) {
						// A completed repair changed the owner's output: every other accepted descendant is stale.
						// A no_op repair (the owner says the fix already landed) changed nothing, but the verifier
						// must still re-read the current files, or its stale rejection blocks the whole graph.
						if (taskStates[owner.id] === "completed") {
							for (const id of collaborationDescendantIds(plan.tasks, owner.id)) {
								if (id !== verifier.id && taskStates[id] === "completed") taskStates[id] = "pending";
							}
						}
						taskStates[verifier.id] = "reading";
						await executeTask(verifier, `Reverification after owner repair cycle ${cycle}. Original rejected acceptance remains binding:\n${rejection}`);
						if (taskStates[verifier.id] === "completed") {
							// From the DAG, not skippedBy: a repeat rejection records no newly skipped ids.
							for (const id of collaborationDescendantIds(plan.tasks, verifier.id)) if (taskStates[id] === "skipped") taskStates[id] = "pending";
						}
					}
					continue;
				}
				break;
			}
			await Promise.race(inFlight.values());
		}
		await Promise.allSettled([...inFlight.values()]);
		renderBoard();
		if (stopper.stopped()) {
			h.stoppedPanel("fh-collaborate", runs, artifactsDir, startedAt, "Stopped during delegated execution; finished task reports remain on disk.");
			return result;
		}
		const graphBlocked = Boolean(executionFailure) || Object.values(taskStates).some((state) => state !== "completed" && state !== "no_op");
		if (graphBlocked) {
			const facts = ["# BLOCKED — final write integration, live/release and publication not authorized", executionFailure ?? "Acceptance remains blocked.", ...plan.tasks.map((task) => `- ${task.id}: ${taskStates[task.id]} — ${taskOutcomes.get(task.id)?.summary ?? "not accepted"}`)].join("\n");
			// Persist host facts first: a failed/uncertain digest child must not erase them.
			await h.save(collabDir, "final.md", facts);
			await runChild({ run: architectRun, prompt: `READ-ONLY BLOCKED DIGEST\n${facts}\nReports: ${reportsDir}\nSummarize completed execution separately from accepted deliverables, blocked research/integration, missing approvals and next owner actions. Do not claim success or perform repairs, live validation, release or writes. Last word: architect.`, systemPrompt: architectSlot.systemPrompt, appendSystemPrompts: architectSlot.appendSystemPrompts, tools: READONLY_TOOLS, thinking: architectSlot.thinking, spawn: "next", signal: stopper.signal });
			const digest = `${facts}\n\n## Architect digest\n${runOk(architectRun) ? architectRun.text : `Unavailable: ${runError(architectRun)}. No replay attempted.`}`;
			await h.save(collabDir, "final.md", digest);
			h.panel({ kind: "collab", command: "fh-collaborate", ok: false, agent: toStat(architectRun), artifactsDir }, digest);
			await h.save(artifactsDir, "summary.json", JSON.stringify({ command: "fh-collaborate", ok: false, plan, taskStates, taskOutcomes: Object.fromEntries(taskOutcomes), executionFailure, taskExecutions, maxConcurrentWriteEnabledChildren, finalMode: "read", publishTo, agents: runs.map(toStat) }, null, 2));
			// The interactive Pi host may repair the blocked work itself. This is a
			// new, scoped turn, NOT a conversion of failed child prose into acceptance.
			// Never give the blocked child write tools or publish from this branch.
			result.hostRecovery = { planPath, reportsDir, finalPath: path.join(collabDir, "final.md"), artifactsDir };
			return result;
		}

		// ── Phase 4: one final architect integration turn, still under the single-writer invariant ──
		setStatus(CUSTOM_TYPE, "collaborate: final architect integration…");
		const finalStartedAt = Date.now();
		activeWriters++;
		maxConcurrentWriteEnabledChildren = Math.max(maxConcurrentWriteEnabledChildren, activeWriters);
		try {
			await runChild({ run: architectRun, prompt: withHarnessRepoState(collabCoordinatePrompt(prompt, reportsDir, planPath), repoCardMarkdown), systemPrompt: contractSystemPrompt(architectSlot.systemPrompt, "SYSTEM_PROMPT_COLLAB_COORDINATOR.md"), appendSystemPrompts: architectSlot.appendSystemPrompts, tools: FULL_TOOLS, thinking: architectSlot.thinking, spawn: "next", signal: stopper.signal });
		} finally {
			activeWriters--;
		}
		taskExecutions.push({ taskId: "final", slot: architectSlot.id, mode: "write", startedAt: finalStartedAt, endedAt: Date.now(), ok: runOk(architectRun) && !stopper.stopped() });
		if (stopper.stopped()) {
			h.stoppedPanel("fh-collaborate", runs, artifactsDir, startedAt, "Stopped during final architect integration.");
			return result;
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
		try { setWidget(TASKBOARD_WIDGET, undefined); } catch {}
		setStatus(CUSTOM_TYPE, undefined);
	}
	return result;
}
