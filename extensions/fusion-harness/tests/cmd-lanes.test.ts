/**
 * Drives the REAL /fh-lanes handler against a throwaway git repo with the child runner
 * mocked: every "builder" writes a file into whatever cwd it was handed, the "architect"
 * cherry-picks one lane into its cwd. Zero paid calls. Asserts the lane contract end to
 * end — where each child ran, what got committed where, that the main checkout stayed
 * untouched until the integration, and that the writer lease came back.
 */
import { afterEach, describe, expect, mock, test } from "bun:test";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { acquireWriterLease } from "../modules/writer-lease.ts";
import { loadModelStack } from "../modules/model-stack.ts";
import { cleanLanes, laneRootFor } from "../modules/lanes.ts";
import { newRun, type AgentRun, type FhDetails, type HarnessDeps } from "../modules/runtime.ts";

const sh = (cwd: string, args: string[]) => execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();

// ── The mocked child runner ──────────────────────────────────────────────────
type ChildCall = { role: string; slot?: string; cwd: string; tools: string; prompt: string; systemPrompt?: string };
const calls: ChildCall[] = [];
let builderBehaviour: (run: AgentRun, cwd: string) => void = (run, cwd) => {
	writeFileSync(join(cwd, `${run.slot!.name}.txt`), `${run.slot!.name} was here\n`);
};
mock.module("../modules/child-runner.ts", () => ({
	runChild: async (opts: any) => {
		const run: AgentRun = opts.run;
		calls.push({ role: run.role, slot: run.slot?.id, cwd: opts.cwd, tools: opts.tools, prompt: opts.prompt, systemPrompt: opts.systemPrompt });
		run.status = "working";
		run.startedAt = Date.now();
		if (run.role === "BUILDER") builderBehaviour(run, opts.cwd);
		else {
			// The architect integrates: cherry-pick the first committed lane without committing.
			const sha = /work commit: ([0-9a-f]{40})/.exec(opts.prompt)?.[1];
			if (sha) {
				sh(opts.cwd, ["cherry-pick", "-n", sha]);
				sh(opts.cwd, ["reset", "-q"]);
			}
		}
		run.text = `${run.role} ${run.slot?.name ?? ""} report`;
		run.exitCode = 0;
		run.status = "done";
		run.endedAt = Date.now();
		run.ms = 1;
		return run;
	},
	runProc: async () => ({ code: 0, output: "" }),
}));
// pi's UI packages exist only inside a running pi — the command never renders here anyway.
mock.module("@earendil-works/pi-tui", () => ({ truncateToWidth: (s: string) => s }));
mock.module("../modules/tui.ts", () => ({ laneRowStr: () => "" }));
const { registerLanesCommand } = await import("../modules/cmd-lanes.ts");

// ── Fixtures ─────────────────────────────────────────────────────────────────
const dirs: string[] = [];
afterEach(async () => {
	calls.length = 0;
	builderBehaviour = (run, cwd) => writeFileSync(join(cwd, `${run.slot!.name}.txt`), `${run.slot!.name} was here\n`);
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
	const dir = mkdtempSync(join(tmpdir(), "fh-cmd-lanes-"));
	dirs.push(dir);
	sh(dir, ["init", "-q", "-b", "main"]);
	writeFileSync(join(dir, "a.txt"), "one\n");
	sh(dir, ["add", "-A"]);
	sh(dir, ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "a"]);
	return dir;
}

/** The stack YAML lives OUTSIDE the repo under test, so it never shows up as an untracked file. */
function stackFile(): string {
	const dir = mkdtempSync(join(tmpdir(), "fh-cmd-lanes-stack-"));
	dirs.push(dir);
	const file = join(dir, "stack.yaml");
	writeFileSync(file, ["- name: fable", "  model: anthropic/claude-fable-5", "  architect: true", "- name: sol", "  model: openai/gpt-5.6-sol", "  primary: true", "- name: terra", "  model: openai/gpt-5.6-terra", ""].join("\n"));
	return file;
}

/** A fake pi + HarnessDeps: records panels, hands out a temp artifacts dir, never renders. */
function harness(cwd: string) {
	const stack = loadModelStack(stackFile());
	const panels: Array<{ details: FhDetails; content: string }> = [];
	const notices: string[] = [];
	const widgets = new Map<string, unknown>();
	let handler: ((args: string, ctx: any) => Promise<void>) | undefined;
	const pi = { registerCommand: (_name: string, spec: any) => (handler = spec.handler), sendMessage: () => {} } as any;
	const artifacts = mkdtempSync(join(tmpdir(), "fh-cmd-lanes-art-"));
	dirs.push(artifacts);
	const h: HarnessDeps = {
		panel: (details, content) => panels.push({ details, content }),
		stoppedPanel: (command) => panels.push({ details: { kind: "stopped", command, ok: false }, content: "" }),
		absorbRuns: () => {},
		startStoppable: () => ({ signal: new AbortController().signal, stopped: () => false, release: () => {} }),
		startWidget: () => () => {},
		startGridWidget: () => () => {},
		noteHost: () => {},
		modelStack: () => stack,
		architectModel: () => stack.architect.model,
		builderModel: () => stack.primaryBuilder.model,
		newSlotRun: (slot) => newRun(slot.architect ? "ARCHITECT" : "BUILDER", slot.model, slot),
		slotInitialSpawn: (_slot, _ctx, dir) => ({ sessionDir: dir }),
		slotNextSpawn: (_slot, _run, initial) => initial,
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
	};
	registerLanesCommand(pi, h);
	const ctx = { cwd, ui: { notify: (m: string) => notices.push(m), setStatus: () => {}, setWidget: (id: string, w: unknown) => (w === undefined ? widgets.delete(id) : widgets.set(id, w)) } };
	return { run: (args: string) => handler!(args, ctx), panels, notices, widgets, artifacts, stack };
}

// ── The contract ─────────────────────────────────────────────────────────────
describe("/fh-lanes end to end (child runner mocked)", () => {
	test("each builder writes in its own worktree; only the architect touches the main checkout", async () => {
		const cwd = repo();
		const fh = harness(cwd);
		await fh.run("add a greeting file");

		// Two builders (sol, terra) ran with full tools, each in a DIFFERENT cwd that is not the repo.
		const builders = calls.filter((call) => call.role === "BUILDER");
		expect(builders.map((call) => call.slot).sort()).toEqual(["sol", "terra"]);
		expect(new Set(builders.map((call) => call.cwd)).size).toBe(2);
		for (const call of builders) {
			expect(call.cwd.startsWith(cwd)).toBe(false);
			expect(call.tools).toBe("read,grep,find,ls,bash,edit,write");
			expect(call.prompt).toContain(`Branch: fh/lane/${call.slot}`);
			expect(call.prompt).toContain(`You are ${call.slot} (`);
		}
		// Each lane holds ONLY its own builder's file, committed on its own branch.
		expect(sh(cwd, ["show", "--stat", "--format=", "fh/lane/sol"])).toContain("sol.txt");
		expect(sh(cwd, ["show", "--stat", "--format=", "fh/lane/sol"])).not.toContain("terra.txt");
		expect(sh(cwd, ["show", "--stat", "--format=", "fh/lane/terra"])).toContain("terra.txt");

		// The architect ran ONCE, last, in the main checkout, with the lane contract and every lane's commit.
		const architect = calls.filter((call) => call.role === "ARCHITECT");
		expect(architect.length).toBe(1);
		expect(calls[calls.length - 1].role).toBe("ARCHITECT");
		expect(architect[0].cwd).toBe(cwd);
		expect(architect[0].systemPrompt).toContain("integrating parallel lanes");
		expect(architect[0].prompt).toContain("[SOL] openai/gpt-5.6-sol");
		expect(architect[0].prompt).toContain("[TERRA] openai/gpt-5.6-terra");
		expect((architect[0].prompt.match(/work commit: [0-9a-f]{40}/g) ?? []).length).toBe(2);
		// Its integration landed as UNCOMMITTED changes on main; the user's branch has no new commit.
		expect(existsSync(join(cwd, "sol.txt"))).toBe(true);
		expect(sh(cwd, ["rev-parse", "--abbrev-ref", "HEAD"])).toBe("main");
		expect(sh(cwd, ["log", "--oneline"]).split("\n").length).toBe(1);
		expect(sh(cwd, ["status", "--porcelain"])).toContain("sol.txt");

		// Panels: prompt, banner, every lane's report side by side, then the integration.
		const kinds = fh.panels.map((panel) => panel.details.kind);
		expect(kinds).toEqual(["prompt", "banner", "multi", "lanes"]);
		const final = fh.panels[fh.panels.length - 1].details;
		expect(final.ok).toBe(true);
		expect(final.agent?.role).toBe("ARCHITECT");
		expect(final.lanes?.map((lane) => [lane.slotId, lane.branch, lane.committed, lane.files])).toEqual([["sol", "fh/lane/sol", true, 1], ["terra", "fh/lane/terra", true, 1]]);

		// Artifacts + the writer lease released + the lane board torn down.
		expect(existsSync(join(fh.artifacts, "lane-manifest.json"))).toBe(true);
		expect(existsSync(join(fh.artifacts, "agents", "sol", "lane.patch"))).toBe(true);
		expect(existsSync(join(fh.artifacts, "integration.md"))).toBe(true);
		expect(JSON.parse(readFileSync(join(fh.artifacts, "summary.json"), "utf8")).integrated).toBe(true);
		acquireWriterLease(cwd, "after").release();
		expect(fh.widgets.size).toBe(0);
	});

	test("--no-merge runs no architect and leaves the main checkout untouched", async () => {
		const cwd = repo();
		const fh = harness(cwd);
		await fh.run("--no-merge add a greeting file");
		expect(calls.map((call) => call.role)).toEqual(["BUILDER", "BUILDER"]);
		expect(sh(cwd, ["status", "--porcelain"])).toBe("");
		const final = fh.panels[fh.panels.length - 1].details;
		expect(final.kind).toBe("lanes");
		expect(final.agent).toBeUndefined();
		expect(final.ok).toBe(true);
		expect(fh.panels[fh.panels.length - 1].content).toContain("--no-merge");

		// The lanes survive the command for status / diff / clean.
		await fh.run("status");
		expect(fh.panels[fh.panels.length - 1].details.lanes?.map((lane) => lane.slotId).sort()).toEqual(["sol", "terra"]);
		await fh.run("diff terra");
		expect(fh.panels[fh.panels.length - 1].content).toContain("+terra was here");
		await fh.run("clean");
		expect(fh.notices[fh.notices.length - 1]).toContain("removed 2 lanes");
		expect(sh(cwd, ["for-each-ref", "refs/heads/fh/lane/"])).toBe("");
	});

	test("a lane whose builder changed nothing is reported, not integrated", async () => {
		const cwd = repo();
		builderBehaviour = (run, laneCwd) => {
			if (run.slot!.name === "sol") writeFileSync(join(laneCwd, "sol.txt"), "sol\n");
		};
		const fh = harness(cwd);
		await fh.run("do it");
		const final = fh.panels[fh.panels.length - 1].details;
		expect(final.lanes?.find((lane) => lane.slotId === "terra")?.committed).toBe(false);
		expect(final.lanes?.find((lane) => lane.slotId === "sol")?.committed).toBe(true);
		const architect = calls.find((call) => call.role === "ARCHITECT")!;
		expect(architect.prompt).toContain("work commit: none — this lane changed nothing");
	});

	test("refuses to run outside a git repository, before any model is spawned", async () => {
		const cwd = mkdtempSync(join(tmpdir(), "fh-cmd-lanes-nogit-"));
		dirs.push(cwd);
		const fh = harness(cwd);
		await fh.run("do it");
		expect(calls.length).toBe(0);
		expect(fh.panels.length).toBe(0);
		expect(fh.notices[0]).toContain("lanes need a git repository");
	});
});
