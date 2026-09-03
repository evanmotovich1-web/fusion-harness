/**
 * Drives the REAL /fh-fusion handler against a throwaway git repo with the child runner
 * mocked. Zero paid calls. Pins the lane-mode session contract: a slot whose research
 * ran inside its worktree lane must be RESUMED for the context ACK from that same cwd.
 * pi treats a `--session <id>` whose recorded project differs from the cwd as foreign
 * and blocks on "Fork this session into current directory? [y/N]" — a prompt a child
 * spawned with stdin ignored can never answer, so the ACK fails and syncOk is false.
 */
import { afterEach, describe, expect, mock, test } from "bun:test";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { loadModelStack } from "../modules/model-stack.ts";
import { cleanLanes, createLane, laneRootFor, type Lane } from "../modules/lanes.ts";
import { newRun, type AgentRun, type FhDetails, type HarnessDeps } from "../modules/runtime.ts";

const sh = (cwd: string, args: string[]) => execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();

// ── The mocked child runner ──────────────────────────────────────────────────
type ChildCall = { role: string; slot?: string; cwd: string; tools: string; resume?: string; sessionId?: string; fork?: string };
const calls: ChildCall[] = [];
let ackRunId = "";
mock.module("../modules/child-runner.ts", () => ({
	runChild: async (opts: any) => {
		const run: AgentRun = opts.run;
		calls.push({ role: run.role, slot: run.slot?.id, cwd: opts.cwd, tools: opts.tools, resume: opts.resume, sessionId: opts.sessionId, fork: opts.fork });
		run.status = "working";
		run.startedAt = Date.now();
		// Every child reports a session id, like a real pi child does; the ACK turn returns the exact token.
		run.sessionRef = `${run.slot?.id ?? run.role}-${calls.length}`;
		run.text = opts.tools === "none" ? `ACK FUSION ${ackRunId}` : `${run.role} ${run.slot?.name ?? ""} report`;
		run.toolCalls = 0;
		run.exitCode = 0;
		run.status = "done";
		run.endedAt = Date.now();
		run.ms = 1;
		return run;
	},
	runProc: async () => ({ code: 0, output: "" }),
}));
mock.module("@earendil-works/pi-tui", () => ({ truncateToWidth: (s: string) => s }));
mock.module("../modules/tui.ts", () => ({ laneRowStr: () => "" }));
const { registerFusionCommand } = await import("../modules/cmd-fusion.ts");

// ── Fixtures ─────────────────────────────────────────────────────────────────
const dirs: string[] = [];
afterEach(async () => {
	calls.length = 0;
	while (dirs.length) {
		const dir = dirs.pop()!;
		try {
			await cleanLanes(dir);
		} catch {}
		rmSync(laneRootFor(dir), { recursive: true, force: true });
		rmSync(dir, { recursive: true, force: true });
	}
});

function repo(): string {
	const dir = mkdtempSync(join(tmpdir(), "fh-cmd-fusion-"));
	dirs.push(dir);
	sh(dir, ["init", "-q", "-b", "main"]);
	writeFileSync(join(dir, "a.txt"), "one\n");
	sh(dir, ["add", "-A"]);
	sh(dir, ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "a"]);
	return dir;
}

function stackFile(): string {
	const dir = mkdtempSync(join(tmpdir(), "fh-cmd-fusion-stack-"));
	dirs.push(dir);
	const file = join(dir, "stack.yaml");
	writeFileSync(file, ["- name: fable", "  model: anthropic/claude-fable-5", "  architect: true", "- name: sol", "  model: openai/gpt-5.6-sol", "  primary: true", "- name: terra", "  model: openai/gpt-5.6-terra", ""].join("\n"));
	return file;
}

/** A fake pi + HarnessDeps mirroring the factory's session rules: a run that reported a session is resumed. */
function harness(cwd: string, laneModeOn: boolean) {
	const stack = loadModelStack(stackFile());
	const panels: Array<{ details: FhDetails; content: string }> = [];
	let handler: ((args: string, ctx: any) => Promise<void>) | undefined;
	const pi = { registerCommand: (_name: string, spec: any) => (handler = spec.handler), sendMessage: () => {} } as any;
	const artifacts = mkdtempSync(join(tmpdir(), "fh-cmd-fusion-art-"));
	dirs.push(artifacts);
	ackRunId = basename(artifacts);
	const h: HarnessDeps = {
		panel: (details, content) => panels.push({ details, content }),
		stoppedPanel: (command) => panels.push({ details: { kind: "stopped", command, ok: false }, content: "" }),
		absorbRuns: () => {},
		startStoppable: () => ({ signal: new AbortController().signal, stopped: () => false, release: () => {} }),
		startWidget: () => () => {},
		startGridWidget: () => () => {},
		laneMode: () => laneModeOn,
		setLaneMode: (on) => (laneModeOn = on),
		seedLanes: async (c, slots, opts) => {
			if (!opts?.force && !laneModeOn) return undefined;
			const lanes = new Map<string, Lane>();
			for (const slot of slots) lanes.set(slot.id, await createLane(c.cwd, slot.id));
			return lanes;
		},
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
	registerFusionCommand(pi, h);
	const ctx = { cwd, ui: { notify: () => {}, setStatus: () => {}, setWidget: () => {} } };
	return { run: (args: string) => handler!(args, ctx), panels, artifacts };
}

// ── The contract ─────────────────────────────────────────────────────────────
describe("/fh-fusion context sync under lane mode (child runner mocked)", () => {
	test("a slot resumed for its ACK re-enters the lane cwd its research session was created in", async () => {
		const cwd = repo();
		const fh = harness(cwd, true);
		await fh.run("research the thing :: build the thing");

		const research = calls.filter((call) => call.tools !== "none" && call.role !== "FUSION");
		const acks = calls.filter((call) => call.tools === "none");
		expect(research.map((call) => call.slot).sort()).toEqual(["fable", "sol", "terra"]);
		expect(acks.map((call) => call.slot).sort()).toEqual(["fable", "sol", "terra"]);

		// Research ran in a private lane for every slot; the FUSION writer alone used the main checkout.
		for (const call of research) expect(call.cwd.startsWith(cwd)).toBe(false);
		expect(calls.find((call) => call.role === "FUSION")!.cwd).toBe(cwd);

		// THE BUG: every resumed ACK must run where the session it resumes was created.
		for (const ack of acks) {
			if (!ack.resume) continue;
			const origin = research.find((call) => call.slot === ack.slot)!;
			expect(ack.resume).toBe(`${ack.slot}-${calls.indexOf(origin) + 1}`);
			expect(ack.cwd).toBe(origin.cwd);
		}
		// Non-primary slots are the resumed ones; the primary forks fresh and stays in the main checkout.
		expect(acks.filter((ack) => ack.resume).map((ack) => ack.slot).sort()).toEqual(["fable", "terra"]);
		expect(acks.find((ack) => ack.slot === "sol")!.cwd).toBe(cwd);

		const summary = JSON.parse(readFileSync(join(fh.artifacts, "summary.json"), "utf8"));
		expect(summary.ok).toBe(true);
		expect(summary.contextSync.every((ack: { status: string }) => ack.status === "acknowledged")).toBe(true);
		expect(fh.panels[fh.panels.length - 1].details.kind).toBe("sync");
		expect(fh.panels[fh.panels.length - 1].details.ok).toBe(true);
	});

	test("with lane mode off every turn, research and ACK alike, shares the main checkout", async () => {
		const cwd = repo();
		const fh = harness(cwd, false);
		await fh.run("research the thing :: build the thing");
		for (const call of calls) expect(call.cwd).toBe(cwd);
		expect(JSON.parse(readFileSync(join(fh.artifacts, "summary.json"), "utf8")).ok).toBe(true);
	});
});
