/**
 * collaboration-run.test.ts — run-level behavior of the extracted collaboration
 * module, driven through its two scripted ports (child, escalate). Zero paid
 * calls: no child-runner import, no mock.module. Covers only the gaps the
 * repo-reflex suite cannot reach through the command shell:
 *   - a blocked graph never reaches phase-4 integration (final child call)
 *   - needs_decision fails closed when escalate returns undefined
 *   - a malformed read report is retried once; a malformed write never is
 *   - the repair loop stops on an identical rejection and repeats on new evidence
 *   - an abort during planning starts no execute, digest, or final child
 *   - two write-mode child calls never overlap (single-writer invariant)
 */
import { afterEach, describe, expect, test } from "bun:test";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { runCollaboration, type CollaborationChildCall } from "../modules/collaboration-run.ts";
import { loadModelStack } from "../modules/model-stack.ts";
import { FULL_TOOLS, newRun } from "../modules/runtime.ts";

const gitIdentity = ["-c", "user.name=t", "-c", "user.email=t@t"];
const sh = (cwd: string, args: string[]) => execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();

// ── prompt markers (prompt-library templates + module literals) ──────────────
const DELEGATE = "Merge them into ONE delegation plan";
const DIGEST = "READ-ONLY BLOCKED DIGEST";
const RETRY = "READ-ONLY REPORT RETRY";
const REPAIR = "OWNER REPAIR";
const REVERIFY = "Reverification after owner repair";
const FINAL = "closing an N-agent collaboration";
const EXECUTE = (taskId: string) => `executing delegated task ${taskId}`;
const ADVANCED = new RegExp(`${DELEGATE}|executing delegated task|${FINAL}|${DIGEST}`);

/** One scripted FH_TASK_OUTCOME terminal line. */
const outcome = (status: string, summary: string, extra: Record<string, unknown> = {}): string =>
	`FH_TASK_OUTCOME: ${JSON.stringify({ schema_version: 1, status, summary, ...extra })}`;

interface RecordedCall {
	slot: string;
	prompt: string;
	tools: string;
	spawn: "initial" | "next";
	sessionDir: string;
}

interface Fixture {
	calls: RecordedCall[];
	escalations: Array<{ question: string; options: string[] }>;
	statuses: string[];
	widgets: Array<{ id: string; lines?: string[] }>;
	artifacts: string;
	collabDir: string;
	reportsDir: string;
	maxWriteOverlap: () => number;
	run: (script: (call: RecordedCall) => string, opts?: { escalateReply?: string; stopOnFirstProposal?: boolean }) => Promise<{ hostRecovery?: { planPath: string; reportsDir: string; finalPath: string; artifactsDir: string } }>;
}

const dirs: string[] = [];
afterEach(() => {
	while (dirs.length) rmSync(dirs.pop()!, { recursive: true, force: true });
});

function tempDir(prefix: string): string {
	const dir = mkdtempSync(join(tmpdir(), prefix));
	dirs.push(dir);
	return dir;
}

/** A tiny real git checkout, so collectRepoState resolves a real card. */
function repo(): string {
	const dir = tempDir("fh-collab-run-repo-");
	sh(dir, ["init", "-q", "-b", "main"]);
	writeFileSync(join(dir, "a.txt"), "one\n");
	sh(dir, ["add", "a.txt"]);
	sh(dir, [...gitIdentity, "commit", "-q", "-m", "root"]);
	return dir;
}

/** fable = architect, sol = primary, terra = builder. */
function stackPath(): string {
	const dir = tempDir("fh-collab-run-stack-");
	const file = join(dir, "stack.yaml");
	writeFileSync(file, [
		"- name: fable",
		"  model: anthropic/claude-fable-5",
		"  architect: true",
		"- name: sol",
		"  model: openai/gpt-5.6-sol",
		"  primary: true",
		"- name: terra",
		"  model: openai/gpt-5.6-terra",
		"",
	].join("\n"));
	return file;
}

function makeFixture(): Fixture {
	const calls: RecordedCall[] = [];
	const escalations: Array<{ question: string; options: string[] }> = [];
	const statuses: string[] = [];
	const widgets: Array<{ id: string; lines?: string[] }> = [];
	const artifacts = tempDir("fh-collab-run-art-");
	const collabDir = join(artifacts, "collaborate");
	const reportsDir = join(collabDir, "reports");
	let writeOverlap = 0;
	let stopped = false;
	const stopper = { signal: new AbortController().signal, stopped: () => stopped, release: () => { stopped = true; } };
	const run = async (script: (call: RecordedCall) => string, opts: { escalateReply?: string; stopOnFirstProposal?: boolean } = {}) => {
		let activeWrites = 0;
		const child = async (call: CollaborationChildCall): Promise<void> => {
			const recorded: RecordedCall = { slot: call.slot.id, prompt: call.prompt, tools: call.tools, spawn: call.spawn, sessionDir: call.sessionDir };
			calls.push(recorded);
			if (opts.stopOnFirstProposal && !ADVANCED.test(call.prompt)) stopped = true;
			// A write-mode call parks briefly so an overlap would be observable, not racy.
			if (call.tools === FULL_TOOLS) {
				activeWrites++;
				writeOverlap = Math.max(writeOverlap, activeWrites);
				await new Promise((resolve) => setTimeout(resolve, 25));
				activeWrites--;
			}
			const run: any = call.run;
			run.status = "working";
			run.startedAt = Date.now();
			run.sessionRef = `${call.slot.id}-${calls.length}`;
			run.stopReason = undefined;
			run.errorMessage = undefined;
			run.text = script(recorded);
			run.toolCalls = 0;
			run.exitCode = 0;
			run.status = "done";
			run.endedAt = Date.now();
			run.ms = 1;
		};
		return await runCollaboration({
			prompt: "collaborate on the fixture request",
			publishTo: null,
			ctx: { cwd: repo() },
			stack: loadModelStack(stackPath()),
			newSlotRun: (slot) => newRun(slot.architect ? "ARCHITECT" : "BUILDER", slot.model, slot),
			mkArtifacts: async () => artifacts,
			save: async (dir, name, body) => void writeFileSync(join(dir, name), body),
			prepareKnowledge: (async () => ({
				query: "", hash: "test", status: "disabled", enabled: false, captureEnabled: false,
				roots: [], hits: [], skipped: [], errors: [], indexedFiles: 0, indexedChunks: 0,
				retrievedAt: "", reasons: [], promptBlock: "",
			})) as any,
			startStoppable: () => stopper,
			startGridWidget: () => () => {},
			totals: () => ({ totalMs: 0, totalCostUsd: 0 }),
			ensureSummary: async (dir, payload) => {
				const file = join(dir, "summary.json");
				if (!existsSync(file)) writeFileSync(file, JSON.stringify(payload));
			},
			captureKnowledge: async () => ({ status: "disabled" as const, reason: "test", runId: "test" }),
			cachedSlotId: () => undefined,
			childTimeoutMs: () => 1000,
			noteHost: () => {},
			panel: () => {},
			stoppedPanel: () => {},
			setStatus: (_type, text) => void statuses.push(String(text)),
			notify: () => {},
			setWidget: (id, lines) => void widgets.push({ id, lines }),
		}, {
			child,
			escalate: async (question, options) => {
				escalations.push({ question, options });
				return opts.escalateReply;
			},
		});
	};
	return { calls, escalations, statuses, widgets, artifacts, collabDir, reportsDir, maxWriteOverlap: () => writeOverlap, run };
}

/** Standard script skeleton; per-task execute behavior is supplied by the test. */
function script(overrides: {
	plan: string;
	digest?: (call: RecordedCall) => string;
	execute: (call: RecordedCall) => string | undefined;
	repair?: (call: RecordedCall) => string;
	reverify?: (call: RecordedCall) => string;
}): (call: RecordedCall) => string {
	return (call) => {
		if (call.prompt.includes(DELEGATE)) return overrides.plan;
		if (call.prompt.includes(DIGEST)) return overrides.digest?.(call) ?? "blocked digest summary";
		if (call.prompt.includes(RETRY)) return overrides.execute(call) ?? outcome("completed", "read recovered on retry");
		if (call.prompt.includes(REPAIR)) return overrides.repair?.(call) ?? outcome("completed", "repair executed");
		if (call.prompt.includes(REVERIFY)) return overrides.reverify?.(call) ?? outcome("completed", "verification passed");
		const executed = overrides.execute(call);
		if (executed !== undefined) return executed;
		if (call.prompt.includes(FINAL)) return "final integration done";
		return `${call.slot} proposal`;
	};
}

const planJson = (tasks: Array<{ id: string; assignee: string; description: string; depends_on: string[]; mode: "read" | "write" }>): string =>
	JSON.stringify({ tasks });

describe("runCollaboration (scripted ports)", () => {
	test("a blocked task never issues a phase final child call", async () => {
		const fh = makeFixture();
		await fh.run(script({
			plan: planJson([
				{ id: "1.a", assignee: "sol", description: "implement", depends_on: [], mode: "write" },
				{ id: "2.a", assignee: "terra", description: "verify acceptance", depends_on: ["1.a"], mode: "read" },
				{ id: "1.c", assignee: "fable", description: "audit", depends_on: [], mode: "read" },
			]),
			execute: (call) => {
				if (call.prompt.includes(EXECUTE("1.a"))) return outcome("completed", "implemented");
				if (call.prompt.includes(EXECUTE("2.a"))) return "missing permission\n\n" + outcome("blocked", "blocked by fixture");
				if (call.prompt.includes(EXECUTE("1.c"))) return outcome("completed", "audit done");
				return undefined;
			},
		}));
		const digest = fh.calls.filter((call) => call.prompt.includes(DIGEST));
		expect(digest).toHaveLength(1);
		expect(digest[0]!.tools).not.toBe(FULL_TOOLS);
		expect(fh.calls.some((call) => call.prompt.includes(FINAL))).toBe(false);
		expect(readFileSync(join(fh.collabDir, "final.md"), "utf8")).toContain("BLOCKED");
		const summary = JSON.parse(readFileSync(join(fh.artifacts, "summary.json"), "utf8"));
		expect(summary.ok).toBe(false);
		expect(summary.taskStates["2.a"]).toBe("blocked");
		expect(summary.taskStates["1.a"]).toBe("completed");
		expect(fh.widgets.some((widget) => widget.id === "fusion-harness-taskboard" && (widget.lines?.length ?? 0) > 0)).toBe(true);
	}, 20_000);

	test("needs_decision with escalate returning undefined does not issue phase final", async () => {
		const fh = makeFixture();
		const result = await fh.run(script({
			plan: planJson([
				{ id: "1.a", assignee: "sol", description: "implement", depends_on: [], mode: "write" },
				{ id: "2.a", assignee: "terra", description: "gate release", depends_on: ["1.a"], mode: "read" },
				{ id: "1.c", assignee: "fable", description: "audit", depends_on: [], mode: "read" },
			]),
			execute: (call) => {
				if (call.prompt.includes(EXECUTE("1.a"))) return outcome("completed", "implemented");
				if (call.prompt.includes(EXECUTE("2.a"))) return outcome("needs_decision", "release gate", { decision: { question: "Deploy the migration now?", options: ["deploy", "abort"] } });
				if (call.prompt.includes(EXECUTE("1.c"))) return outcome("completed", "audit done");
				return undefined;
			},
		}));
		expect(fh.escalations).toEqual([{ question: "Deploy the migration now?", options: ["deploy", "abort"] }]);
		expect(fh.calls.some((call) => call.prompt.includes(FINAL))).toBe(false);
		expect(fh.calls.filter((call) => call.prompt.includes(DIGEST))).toHaveLength(1);
		expect(result.hostRecovery).toBeDefined();
		expect(result.hostRecovery!.finalPath).toBe(join(fh.collabDir, "final.md"));
		expect(existsSync(join(fh.reportsDir, "2.a-decision.json"))).toBe(false);
		const summary = JSON.parse(readFileSync(join(fh.artifacts, "summary.json"), "utf8"));
		expect(summary.ok).toBe(false);
		expect(summary.executionFailure).toContain("needs_decision from 2.a");
		expect(summary.executionFailure).toContain("fail closed without UI");
	}, 20_000);

	test("a read with a bad outcome is retried once and a write is not retried", async () => {
		const fh = makeFixture();
		let readAttempts = 0;
		await fh.run(script({
			plan: planJson([
				{ id: "1.a", assignee: "terra", description: "inspect", depends_on: [], mode: "read" },
				{ id: "1.b", assignee: "sol", description: "implement", depends_on: [], mode: "write" },
				{ id: "1.c", assignee: "fable", description: "audit", depends_on: [], mode: "read" },
			]),
			execute: (call) => {
				if (call.prompt.includes(EXECUTE("1.a"))) {
					readAttempts++;
					return readAttempts === 1 ? "prose without any metadata line" : outcome("completed", "read ok after retry");
				}
				if (call.prompt.includes(EXECUTE("1.b"))) return "prose without any metadata line";
				if (call.prompt.includes(EXECUTE("1.c"))) return outcome("completed", "audit done");
				return undefined;
			},
		}));
		const retried = fh.calls.filter((call) => call.prompt.includes(RETRY));
		expect(retried).toHaveLength(1);
		expect(retried[0]!.slot).toBe("terra");
		expect(fh.calls.filter((call) => call.prompt.includes(EXECUTE("1.a")))).toHaveLength(2);
		expect(fh.calls.filter((call) => call.prompt.includes(EXECUTE("1.b")))).toHaveLength(1);
		expect(existsSync(join(fh.reportsDir, "1.a-attempt-1-invalid.md"))).toBe(true);
		expect(existsSync(join(fh.reportsDir, "1.b-attempt-1-invalid.md"))).toBe(false);
		const summary = JSON.parse(readFileSync(join(fh.artifacts, "summary.json"), "utf8"));
		expect(summary.ok).toBe(false);
		expect(summary.taskStates["1.a"]).toBe("completed");
		expect(summary.taskStates["1.b"]).toBe("failed");
		expect(fh.calls.some((call) => call.prompt.includes(FINAL))).toBe(false);
	}, 20_000);

	test("an identical rejection stops repair", async () => {
		const fh = makeFixture();
		const rejection = () => `acceptance rejected: the same defect\n\n` + outcome("blocked", "acceptance rejected", { repair_target: "1.a" });
		await fh.run(script({
			plan: planJson([
				{ id: "1.a", assignee: "sol", description: "implement", depends_on: [], mode: "write" },
				{ id: "2.a", assignee: "terra", description: "verify acceptance", depends_on: ["1.a"], mode: "read" },
				{ id: "3.a", assignee: "fable", description: "release", depends_on: ["2.a"], mode: "write" },
			]),
			execute: (call) => {
				if (call.prompt.includes(EXECUTE("2.a"))) return rejection();
				if (call.prompt.includes(EXECUTE("1.a"))) return outcome("completed", "implemented");
				return undefined;
			},
			reverify: () => rejection(),
		}));
		expect(fh.calls.filter((call) => call.prompt.includes(REPAIR))).toHaveLength(1);
		expect(fh.calls.filter((call) => call.prompt.includes(REVERIFY))).toHaveLength(1);
		expect(fh.calls.filter((call) => call.prompt.includes(EXECUTE("1.a")))).toHaveLength(2);
		expect(fh.calls.filter((call) => call.prompt.includes(EXECUTE("2.a")))).toHaveLength(2);
		expect(fh.calls.some((call) => call.prompt.includes(EXECUTE("3.a")))).toBe(false);
		expect(fh.calls.some((call) => call.prompt.includes(FINAL))).toBe(false);
		expect(fh.calls.filter((call) => call.prompt.includes(DIGEST))).toHaveLength(1);
		expect(JSON.parse(readFileSync(join(fh.collabDir, "repairs.json"), "utf8"))).toHaveLength(1);
		expect(readFileSync(join(fh.collabDir, "final.md"), "utf8")).toContain("BLOCKED");
	}, 20_000);

	test("a new rejection may repeat the repair cycle", async () => {
		const fh = makeFixture();
		let rejections = 0;
		const evidence = ["defect A", "defect B", "defect B"];
		const rejection = () => `acceptance rejected: ${evidence[Math.min(rejections, evidence.length - 1)]}\n\n` + outcome("blocked", "acceptance rejected", { repair_target: "1.a" });
		await fh.run(script({
			plan: planJson([
				{ id: "1.a", assignee: "sol", description: "implement", depends_on: [], mode: "write" },
				{ id: "2.a", assignee: "terra", description: "verify acceptance", depends_on: ["1.a"], mode: "read" },
				{ id: "3.a", assignee: "fable", description: "release", depends_on: ["2.a"], mode: "write" },
			]),
			execute: (call) => {
				if (call.prompt.includes(EXECUTE("2.a"))) {
					const text = rejection();
					rejections++;
					return text;
				}
				if (call.prompt.includes(EXECUTE("1.a"))) return outcome("completed", "implemented");
				return undefined;
			},
			reverify: () => {
				const text = rejection();
				rejections++;
				return text;
			},
		}));
		expect(fh.calls.filter((call) => call.prompt.includes(REPAIR))).toHaveLength(2);
		expect(fh.calls.filter((call) => call.prompt.includes(REVERIFY))).toHaveLength(2);
		expect(fh.calls.filter((call) => call.prompt.includes(EXECUTE("1.a")))).toHaveLength(3);
		expect(fh.calls.filter((call) => call.prompt.includes(EXECUTE("2.a")))).toHaveLength(3);
		expect(fh.calls.some((call) => call.prompt.includes(FINAL))).toBe(false);
		expect(JSON.parse(readFileSync(join(fh.collabDir, "repairs.json"), "utf8"))).toHaveLength(2);
		expect(readFileSync(join(fh.collabDir, "final.md"), "utf8")).toContain("BLOCKED");
	}, 20_000);

	test("abort during planning starts no execute or final child", async () => {
		const fh = makeFixture();
		const result = await fh.run(() => "proposal text", { stopOnFirstProposal: true });
		expect(fh.calls).toHaveLength(3);
		expect(fh.calls.every((call) => call.spawn === "initial")).toBe(true);
		expect(fh.calls.some((call) => ADVANCED.test(call.prompt))).toBe(false);
		expect(existsSync(join(fh.collabDir, "plan.json"))).toBe(false);
		expect(existsSync(join(fh.collabDir, "final.md"))).toBe(false);
		expect(result.hostRecovery).toBeUndefined();
		const summary = JSON.parse(readFileSync(join(fh.artifacts, "summary.json"), "utf8"));
		expect(summary.stopped).toBe(true);
	}, 20_000);

	test("two write-mode child calls never overlap", async () => {
		const fh = makeFixture();
		await fh.run(script({
			plan: planJson([
				{ id: "1.a", assignee: "sol", description: "implement a", depends_on: [], mode: "write" },
				{ id: "1.b", assignee: "terra", description: "implement b", depends_on: [], mode: "write" },
				{ id: "1.c", assignee: "fable", description: "audit", depends_on: [], mode: "read" },
			]),
			execute: (call) => {
				if (call.prompt.includes(EXECUTE("1.a"))) return outcome("completed", "a done");
				if (call.prompt.includes(EXECUTE("1.b"))) return outcome("completed", "b done");
				if (call.prompt.includes(EXECUTE("1.c"))) return outcome("completed", "audit done");
				return undefined;
			},
		}));
		const writeCalls = fh.calls.filter((call) => call.tools === FULL_TOOLS);
		expect(writeCalls).toHaveLength(3); // 1.a + 1.b + phase-4 final
		expect(fh.calls.filter((call) => call.prompt.includes(EXECUTE("1.a")))).toHaveLength(1);
		expect(fh.calls.filter((call) => call.prompt.includes(EXECUTE("1.b")))).toHaveLength(1);
		expect(fh.calls.filter((call) => call.prompt.includes(FINAL))).toHaveLength(1);
		expect(fh.calls.some((call) => call.prompt.includes(DIGEST))).toBe(false);
		expect(fh.maxWriteOverlap()).toBe(1);
		const summary = JSON.parse(readFileSync(join(fh.artifacts, "summary.json"), "utf8"));
		expect(summary.ok).toBe(true);
		expect(summary.maxConcurrentWriteEnabledChildren).toBe(1);
	}, 20_000);
});
