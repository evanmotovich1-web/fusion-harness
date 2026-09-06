/**
 * Drives /fh-collaborate repository reflexes with the child runner mocked.
 * Zero paid calls. Asserts hashed cards, publication short-circuits, prompt injection,
 * and that the child-runner source loads the git guard after --no-extensions.
 */
import { afterEach, describe, expect, mock, test } from "bun:test";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
import { loadModelStack } from "../modules/model-stack.ts";
import { HARNESS_REPO_STATE_HEADER, newRun, withHarnessRepoState, type AgentRun, type FhDetails, type HarnessDeps } from "../modules/runtime.ts";

const gitIdentity = ["-c", "user.name=t", "-c", "user.email=t@t"];
const sh = (cwd: string, args: string[]) => execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();

type ChildCall = { role: string; slot?: string; prompt: string; tools: string };
const calls: ChildCall[] = [];
let blockTaskId: string | null = null;
let malformedTaskId: string | null = null;
let onFinalCoordination: (() => void) | null = null;
mock.module("../modules/child-runner.ts", () => ({
	runChild: async (opts: any) => {
		const run: AgentRun = opts.run;
		calls.push({ role: run.role, slot: run.slot?.id, prompt: opts.prompt, tools: opts.tools });
		run.status = "working";
		run.startedAt = Date.now();
		run.sessionRef = `${run.slot?.id ?? run.role}-${calls.length}`;
		if (opts.prompt.includes("Merge them into ONE delegation plan")) {
			run.text = JSON.stringify({
				tasks: [
					{ id: "1.a", assignee: "fable", description: "plan a", depends_on: [], outputs: ["a"], mode: "read" },
					{ id: "1.b", assignee: "sol", description: "plan b", depends_on: [], outputs: ["b"], mode: "read" },
					{ id: "1.c", assignee: "terra", description: "plan c", depends_on: [], outputs: ["c"], mode: "read" },
				],
			});
		} else if (opts.prompt.includes("FH_TASK_OUTCOME") || opts.prompt.includes("executing delegated task")) {
			const blocked = blockTaskId && opts.prompt.includes(`task ${blockTaskId}`);
			const malformed = malformedTaskId && opts.prompt.includes(`task ${malformedTaskId}`);
			run.text = malformed
				? "nonempty success prose without outcome metadata"
				: blocked
					? "blocked\n\nFH_TASK_OUTCOME: {\"schema_version\":1,\"status\":\"blocked\",\"summary\":\"blocked by fixture\"}"
					: "did the work\n\nFH_TASK_OUTCOME: {\"schema_version\":1,\"status\":\"completed\",\"summary\":\"ok\"}";
		} else {
			if (opts.prompt.includes("closing an N-agent collaboration")) onFinalCoordination?.();
			run.text = `${run.role} proposal`;
		}
		run.toolCalls = 0;
		run.exitCode = 0;
		run.status = "done";
		run.endedAt = Date.now();
		run.ms = 1;
		return run;
	},
	runProc: async () => ({ code: 0, output: "" }),
	childRepoGuardPath: () => join(TEST_DIR, "../modules/child-repo-guard.ts"),
	piInvocation: (args: string[]) => ({ command: "pi", args }),
}));
mock.module("@earendil-works/pi-tui", () => ({ truncateToWidth: (s: string) => s }));
mock.module("../modules/tui.ts", () => ({ laneRowStr: () => "" }));

const { parseCollaborateArgs, parsePublishTo, registerCollaborateCommand } = await import("../modules/cmd-build.ts");

const dirs: string[] = [];
const files: string[] = [];
afterEach(() => {
	calls.length = 0;
	blockTaskId = null;
	malformedTaskId = null;
	onFinalCoordination = null;
	while (files.length) rmSync(files.pop()!, { force: true });
	while (dirs.length) rmSync(dirs.pop()!, { recursive: true, force: true });
});

function repo(): string {
	const dir = mkdtempSync(join(tmpdir(), "fh-repo-reflex-"));
	dirs.push(dir);
	sh(dir, ["init", "-q", "-b", "main"]);
	writeFileSync(join(dir, "a.txt"), "one\n");
	sh(dir, ["add", "a.txt"]);
	sh(dir, [...gitIdentity, "commit", "-q", "-m", "root"]);
	return dir;
}

function withOrigin(dir: string): string {
	const bare = mkdtempSync(join(tmpdir(), "fh-repo-reflex-bare-"));
	dirs.push(bare);
	sh(bare, ["init", "-q", "--bare"]);
	sh(dir, ["remote", "add", "origin", bare]);
	sh(dir, ["push", "-q", "origin", "HEAD:refs/heads/main"]);
	return bare;
}

function advanceRemote(bare: string): string {
	const updater = mkdtempSync(join(tmpdir(), "fh-repo-reflex-updater-"));
	dirs.push(updater);
	sh(updater, ["clone", "-q", bare, "."]);
	sh(updater, ["checkout", "-q", "main"]);
	writeFileSync(join(updater, "remote.txt"), "remote\n");
	sh(updater, ["add", "remote.txt"]);
	sh(updater, [...gitIdentity, "commit", "-q", "-m", "remote"]);
	sh(updater, ["push", "-q", "origin", "HEAD:refs/heads/main"]);
	return sh(updater, ["rev-parse", "HEAD"]);
}

function stackFile(): string {
	const dir = mkdtempSync(join(tmpdir(), "fh-repo-reflex-stack-"));
	dirs.push(dir);
	const file = join(dir, "stack.yaml");
	writeFileSync(file, ["- name: fable", "  model: anthropic/claude-fable-5", "  architect: true", "- name: sol", "  model: openai/gpt-5.6-sol", "  primary: true", "- name: terra", "  model: openai/gpt-5.6-terra", ""].join("\n"));
	return file;
}

function harness(cwd: string) {
	const stack = loadModelStack(stackFile());
	const panels: Array<{ details: FhDetails; content: string }> = [];
	let handler: ((args: string, ctx: any) => Promise<void>) | undefined;
	const pi = { registerCommand: (_name: string, spec: any) => (handler = spec.handler), sendMessage: () => {} } as any;
	const artifacts = mkdtempSync(join(tmpdir(), "fh-repo-reflex-art-"));
	dirs.push(artifacts);
	const h: HarnessDeps = {
		panel: (details, content) => panels.push({ details, content }),
		stoppedPanel: (command) => panels.push({ details: { kind: "stopped", command, ok: false }, content: "" }),
		absorbRuns: () => {},
		startStoppable: () => ({ signal: new AbortController().signal, stopped: () => false, release: () => {} }),
		startWidget: () => () => {},
		startGridWidget: () => () => {},
		laneMode: () => false,
		setLaneMode: () => {},
		seedLanes: async () => undefined,
		startLaneBoard: () => () => {},
		noteHost: () => {},
		modelStack: () => stack,
		architectModel: () => stack.architect.model,
		builderModel: () => stack.primaryBuilder.model,
		newSlotRun: (slot) => newRun(slot.architect ? "ARCHITECT" : "BUILDER", slot.model, slot),
		slotInitialSpawn: (slot, _ctx, dir) => ({ sessionDir: dir, sessionId: `pinned-${slot.id}` }),
		slotNextSpawn: (_slot, run, initial) => (run.sessionRef ? { sessionDir: initial.sessionDir, resume: run.sessionRef } : initial),
		builderSpawn: (_ctx, dir) => ({ sessionDir: dir }),
		roleSession: () => ({ id: "x", dir: artifacts }),
		roleThinking: () => "medium",
		roleSystemPrompt: () => undefined,
		cachedRoleId: () => undefined,
		cachedSlotId: () => undefined,
		childTimeoutMs: () => 1000,
		buildTimeoutMs: () => 1000,
		flagStr: () => "",
		mkArtifacts: async () => artifacts,
		save: async (dir, name, body) => writeFileSync(join(dir, name), body),
		ensureSummary: async (dir, payload) => {
			if (!existsSync(join(dir, "summary.json"))) writeFileSync(join(dir, "summary.json"), JSON.stringify(payload));
		},
		totals: (runs, startedAt) => ({ totalMs: Date.now() - startedAt, totalCostUsd: runs.reduce((s, r) => s + r.costUsd, 0) }),
		knowledgeConfig: (() => ({ enabled: false })) as any,
		prepareKnowledge: (async () => ({ query: "", hash: "test", status: "disabled", enabled: false, captureEnabled: false, roots: [], hits: [], skipped: [], errors: [], indexedFiles: 0, indexedChunks: 0, retrievedAt: "", reasons: [], promptBlock: "" })) as any,
		captureKnowledge: async () => ({ status: "disabled" as const, reason: "test", runId: "test" }),
		knowledgeCaptureEnabled: () => false,
		setKnowledgeCapture: () => {},
	};
	registerCollaborateCommand(pi, h);
	const ctx = { cwd, ui: { notify: () => {}, setStatus: () => {}, setWidget: () => {} } };
	return { run: (args: string) => handler!(args, ctx), panels, artifacts };
}

describe("parseCollaborateArgs", () => {
	test("strips --publish-to and keeps the prompt", () => {
		expect(parseCollaborateArgs("--publish-to origin/main land the scout")).toEqual({
			prompt: "land the scout",
			publishTo: "origin/main",
		});
		expect(parseCollaborateArgs("just build it")).toEqual({ prompt: "just build it", publishTo: null });
	});

	test("parsePublishTo always binds the remote-tracking ref", () => {
		expect(parsePublishTo("origin/main")).toEqual({ remote: "origin", branch: "main", targetRef: "refs/remotes/origin/main" });
		expect(parsePublishTo("main")).toEqual({ remote: "origin", branch: "main", targetRef: "refs/remotes/origin/main" });
		for (const invalid of ["../evil", "origin/a//b", "origin/main/", "origin/.hidden", "origin/main.lock", "origin/main."]) {
			expect(() => parsePublishTo(invalid)).toThrow(/invalid --publish-to/);
		}
	});
});

describe("/fh-collaborate repository reflexes", () => {
	test("already_integrated --publish-to does not spawn children", async () => {
		const cwd = repo();
		withOrigin(cwd);
		const fh = harness(cwd);
		await fh.run("--publish-to origin/main do not merge anything");
		expect(calls).toEqual([]);
		const card = JSON.parse(readFileSync(join(fh.artifacts, "collaborate", "repo-state.json"), "utf8"));
		expect(card.verdict).toBe("already_integrated");
		expect(card.hash).toMatch(/^[0-9a-f]{64}$/);
		const summary = JSON.parse(readFileSync(join(fh.artifacts, "summary.json"), "utf8"));
		expect(summary.shortCircuit).toBe("noop");
		expect(summary.ok).toBe(true);
	});

	test("dirty --publish-to is blocked with no spawn and no remote mutation", async () => {
		const cwd = repo();
		const bare = withOrigin(cwd);
		const remoteBefore = sh(bare, ["rev-parse", "refs/heads/main"]);
		writeFileSync(join(cwd, "a.txt"), "dirty\n");
		const fh = harness(cwd);
		await fh.run("--publish-to origin/main publish this dirt");
		expect(calls).toEqual([]);
		const summary = JSON.parse(readFileSync(join(fh.artifacts, "summary.json"), "utf8"));
		expect(summary.shortCircuit).toBe("blocked");
		expect(summary.repoVerdict).toBe("blocked_dirty");
		expect(summary.ok).toBe(false);
		expect(sh(bare, ["rev-parse", "refs/heads/main"])).toBe(remoteBefore);
	});

	test("divergence after the explicit refresh blocks with no spawn and no push", async () => {
		const cwd = repo();
		const bare = withOrigin(cwd);
		writeFileSync(join(cwd, "local.txt"), "local\n");
		sh(cwd, ["add", "local.txt"]);
		sh(cwd, [...gitIdentity, "commit", "-q", "-m", "local"]);
		const remoteSha = advanceRemote(bare);
		const fh = harness(cwd);
		await fh.run("--publish-to origin/main publish divergent history");
		expect(calls).toEqual([]);
		const summary = JSON.parse(readFileSync(join(fh.artifacts, "summary.json"), "utf8"));
		expect(summary.shortCircuit).toBe("blocked");
		expect(summary.repoVerdict).toBe("blocked_diverged");
		expect(sh(bare, ["rev-parse", "refs/heads/main"])).toBe(remoteSha);
	});

	test("a clean ahead candidate uses the parent receipt and exact-SHA non-force push", async () => {
		const cwd = repo();
		const bare = withOrigin(cwd);
		writeFileSync(join(cwd, "candidate.txt"), "candidate\n");
		sh(cwd, ["add", "candidate.txt"]);
		sh(cwd, [...gitIdentity, "commit", "-q", "-m", "candidate"]);
		const candidateSha = sh(cwd, ["rev-parse", "HEAD"]);
		const fh = harness(cwd);
		await fh.run("--publish-to origin/main publish the exact candidate");
		const card = JSON.parse(readFileSync(join(fh.artifacts, "collaborate", "repo-state.json"), "utf8"));
		files.push(join(existsSync("/tmp") ? "/tmp" : tmpdir(), "fusion-harness-consumed-receipts", `${card.identity.repositoryId}.json`));

		expect(sh(bare, ["rev-parse", "refs/heads/main"])).toBe(candidateSha);
		const evidencePath = join(fh.artifacts, "publication-receipt.json");
		expect(existsSync(evidencePath)).toBe(true);
		const evidence = JSON.parse(readFileSync(evidencePath, "utf8"));
		expect(evidence.receipt.candidateSha).toBe(candidateSha);
		expect(evidence.receipt.headBefore).toBe(candidateSha);
		expect(evidence.receipt.headAfter).toBe(candidateSha);
		expect(evidence.decision).toMatchObject({ authorize: true, verdict: "authorize_fast_forward", nonForceFastForward: true });
		expect(fh.panels.some((panel) => panel.content.includes(`Pushed ${candidateSha}:refs/heads/main to origin (non-force).`))).toBe(true);

		// The next run re-fetches, recognizes containment, and performs no model turn or push.
		calls.length = 0;
		const second = harness(cwd);
		await second.run("--publish-to origin/main publish the same candidate again");
		expect(calls).toEqual([]);
		const summary = JSON.parse(readFileSync(join(second.artifacts, "summary.json"), "utf8"));
		expect(summary.shortCircuit).toBe("noop");
	});

	test("remote movement after collaboration invalidates the receipt and performs no push", async () => {
		const cwd = repo();
		const bare = withOrigin(cwd);
		writeFileSync(join(cwd, "candidate.txt"), "candidate\n");
		sh(cwd, ["add", "candidate.txt"]);
		sh(cwd, [...gitIdentity, "commit", "-q", "-m", "candidate"]);
		let remoteSha = "";
		onFinalCoordination = () => {
			onFinalCoordination = null;
			remoteSha = advanceRemote(bare);
		};
		const fh = harness(cwd);
		await fh.run("--publish-to origin/main reject a moved target");

		expect(sh(bare, ["rev-parse", "refs/heads/main"])).toBe(remoteSha);
		const evidence = JSON.parse(readFileSync(join(fh.artifacts, "publication-receipt.json"), "utf8"));
		files.push(join(existsSync("/tmp") ? "/tmp" : tmpdir(), "fusion-harness-consumed-receipts", `${evidence.receipt.repositoryId}.json`));
		expect(evidence.decision).toMatchObject({ authorize: false, verdict: "refuse_moved_target" });
		expect(fh.panels.some((panel) => panel.content.includes("Publication refused: refuse_moved_target"))).toBe(true);
	});

	test("missing remote target is needs_decision and fail-closed", async () => {
		const cwd = repo();
		const fh = harness(cwd);
		await fh.run("--publish-to origin/main land it");
		expect(calls).toEqual([]);
		const summaryPath = join(fh.artifacts, "summary.json");
		if (existsSync(summaryPath)) {
			const summary = JSON.parse(readFileSync(summaryPath, "utf8"));
			expect(summary.ok).toBe(false);
		}
		expect(fh.panels.some((panel) => panel.details.ok === false)).toBe(true);
	});

	test("a blocked task skips write-enabled final integration", async () => {
		const cwd = repo();
		blockTaskId = "1.a";
		const fh = harness(cwd);
		await fh.run("implement with a blocked task");
		expect(calls.some((call) => call.tools === "read,grep,find,ls,bash,edit,write")).toBe(false);
		expect(fh.panels.some((panel) => panel.content.includes("blocked by fixture") && panel.details.ok === false)).toBe(true);
		expect(fh.panels.some((panel) => /Final write integration skipped|blocked/.test(panel.content))).toBe(true);
	});

	test("malformed task metadata fails closed before final write integration", async () => {
		const cwd = repo();
		malformedTaskId = "1.a";
		const fh = harness(cwd);
		await fh.run("reject a malformed outcome");
		expect(calls.some((call) => call.tools === "read,grep,find,ls,bash,edit,write")).toBe(false);
		expect(fh.panels.some((panel) => panel.content.includes("failed closed") && panel.content.includes("exactly one FH_TASK_OUTCOME"))).toBe(true);
	});

	test("non-publish collab injects the measured repo card before proposals", async () => {
		const cwd = repo();
		const fh = harness(cwd);
		await fh.run("implement the reflex layer");
		expect(calls.length).toBeGreaterThan(0);
		expect(calls.some((call) => call.prompt.includes(HARNESS_REPO_STATE_HEADER))).toBe(true);
		expect(existsSync(join(fh.artifacts, "collaborate", "repo-state.json"))).toBe(true);
		const card = JSON.parse(readFileSync(join(fh.artifacts, "collaborate", "repo-state.json"), "utf8"));
		expect(card.hash).toMatch(/^[0-9a-f]{64}$/);
	});

	test("withHarnessRepoState wraps measured facts, not wiki evidence", () => {
		const wrapped = withHarnessRepoState("do work", "verdict: proceed");
		expect(wrapped.startsWith(HARNESS_REPO_STATE_HEADER)).toBe(true);
		expect(wrapped.endsWith("do work")).toBe(true);
		expect(wrapped).toContain("verdict: proceed");
	});
});

describe("child-runner guard wiring", () => {
	test("loads the guard with -e after --no-extensions and sets GIT_CONFIG_* plus FH_GUARD_ACK", () => {
		const source = readFileSync(join(TEST_DIR, "../modules/child-runner.ts"), "utf8");
		expect(source).toContain('args.push("-e", guardPath)');
		expect(source).toContain("--no-extensions");
		expect(source).toContain("CHILD_GUARD_ACK_ENV");
		expect(source).toContain("CHILD_GUARD_VERSION");
		expect(source).toContain("fh-guard-ack-");
		expect(source).toContain('GIT_CONFIG_GLOBAL: "/dev/null"');
		expect(source).toContain("treating child as unguarded");
		expect(source).not.toContain("import.meta.dir");
	});
});
