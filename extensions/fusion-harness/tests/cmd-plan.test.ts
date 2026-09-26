import { afterEach, describe, expect, mock, test } from "bun:test";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { loadModelStack } from "../modules/model-stack.ts";
import { missingPlanHeadings, nextPlanFile, parsePlanArgs, resolvePlanDir } from "../modules/plan-dir.ts";
import { newRun, type AgentRun, type HarnessDeps } from "../modules/runtime.ts";

const roots: string[] = [];
const savedTmp = process.env.FH_TMP_ROOT;
afterEach(() => {
	while (roots.length) rmSync(roots.pop()!, { recursive: true, force: true });
	if (savedTmp === undefined) delete process.env.FH_TMP_ROOT;
	else process.env.FH_TMP_ROOT = savedTmp;
});

function git(cwd: string, ...args: string[]): void {
	execFileSync("git", args, { cwd, stdio: "ignore" });
}

function repo(): string {
	const dir = mkdtempSync(join(tmpdir(), "fh-plan-"));
	roots.push(dir);
	git(dir, "init", "-q", "-b", "main");
	return dir;
}

const PLAN = [
	"## Decoded ask",
	"Add a health check.",
	"## Evidence",
	"Opened README.md.",
	"## Do not touch",
	"Do not commit.",
	"## Deliverables",
	"planADW/PLAN.md",
	"## Steps",
	"1. Edit app.ts. Verify: bun test. Expected exit 0.",
	"## Checklist",
	"- [ ] health route in app.ts",
	"## Verify",
	"bun test exits 0.",
	"## Handoff",
	"Wait until the user says go.",
	"",
].join("\n");

describe("plan folder", () => {
	test("default folder is planADW and a custom folder is kept", () => {
		expect(parsePlanArgs("add a health check")).toEqual({ planDir: "planADW", task: "add a health check" });
		expect(parsePlanArgs("--plan-dir specs add a health check")).toEqual({ planDir: "specs", task: "add a health check" });
		expect(resolvePlanDir("planADW/")).toBe("planADW");
		expect(() => resolvePlanDir("../adws")).toThrow("..");
		expect(() => parsePlanArgs("")).toThrow("Usage:");
	});

	test("the next plan file stays inside the project and does not overwrite", () => {
		const cwd = repo();
		expect(nextPlanFile(cwd, "planADW").relative).toBe("planADW/PLAN.md");
		const first = nextPlanFile(cwd, "planADW");
		mkdirSync(first.absolute.slice(0, first.absolute.lastIndexOf("/")), { recursive: true });
		writeFileSync(first.absolute, "one\n");
		expect(nextPlanFile(cwd, "planADW").relative).toBe("planADW/PLAN_v2.md");
		expect(missingPlanHeadings(PLAN)).toEqual([]);
		expect(missingPlanHeadings("# Decoded ask\n")).toContain("Evidence");
	});
});

mock.module("../modules/child-runner.ts", () => ({
	runChild: async (opts: { run: AgentRun; cwd: string; prompt: string }) => {
		const run = opts.run;
		run.status = "done";
		run.exitCode = 0;
		run.text = "plan written";
		const match = /exact path and nowhere else: (.+)/.exec(opts.prompt);
		if (match) writeFileSync(match[1].trim(), PLAN);
		return run;
	},
}));

const { registerPlanCommand } = await import("../modules/cmd-plan.ts");

function harness(cwd: string) {
	process.env.FH_TMP_ROOT = join(cwd, "tmp");
	const stackDir = mkdtempSync(join(tmpdir(), "fh-plan-stack-"));
	roots.push(stackDir);
	const stackFile = join(stackDir, "stack.yaml");
	writeFileSync(stackFile, "- name: grok\n  model: xai/grok-4.6\n  architect: true\n- name: sol\n  model: openai/gpt-5.6-sol\n  primary: true\n");
	const stack = loadModelStack(stackFile);
	const panels: Array<{ details: any; content: string }> = [];
	const notices: string[] = [];
	let handler: ((raw: string, ctx: any) => Promise<void>) | undefined;
	const pi = { registerCommand: (_name: string, spec: any) => { handler = spec.handler; } } as any;
	const artifacts = mkdtempSync(join(tmpdir(), "fh-plan-art-"));
	roots.push(artifacts);
	const h = {
		noteHost() {},
		panel(details: any, content: string) { panels.push({ details, content }); },
		stoppedPanel() {},
		absorbRuns() {},
		startStoppable: () => ({ signal: new AbortController().signal, stopped: () => false, release: () => {} }),
		startWidget: () => () => {},
		startGridWidget: () => () => {},
		laneMode: () => false,
		setLaneMode() {},
		seedLanes: async () => undefined,
		startLaneBoard: () => () => {},
		modelStack: () => stack,
		architectModel: () => stack.architect.model,
		builderModel: () => stack.primaryBuilder.model,
		newSlotRun: (slot) => newRun("ARCHITECT", slot.model, slot),
		slotInitialSpawn: (_slot, _ctx, dir) => ({ sessionDir: dir }),
		slotNextSpawn: (_slot, _run, initial) => initial,
		builderSpawn: (_ctx, dir) => ({ sessionDir: dir }),
		roleSession: () => ({ id: "x", dir: artifacts }),
		roleThinking: () => "high",
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
		totals: () => ({ totalMs: 1, totalCostUsd: 0 }),
		knowledgeConfig: () => ({ enabled: false }),
		prepareKnowledge: async () => ({ promptBlock: "" }),
		captureKnowledge: async () => ({ status: "disabled" }),
		knowledgeCaptureEnabled: () => false,
		setKnowledgeCapture() {},
	} as unknown as HarnessDeps;
	registerPlanCommand(pi, h);
	return {
		panels,
		notices,
		artifacts,
		run(raw: string) {
			return handler!(raw, { cwd, ui: { notify: (message: string) => notices.push(message), setStatus() {}, setWidget() {} } });
		},
	};
}

describe("/fh-plan", () => {
	test("writes the plan in the open project and does not claim the code was written", async () => {
		const cwd = repo();
		const command = harness(cwd);
		await command.run("add a health check");
		const plan = realpathSync(join(cwd, "planADW", "PLAN.md"));
		expect(existsSync(plan)).toBe(true);
		expect(readFileSync(plan, "utf8")).toContain("## Handoff");
		expect(command.panels.at(-1)?.details.ok).toBe(true);
		expect(command.panels.at(-1)?.content).toContain(plan);
		expect(command.panels.at(-1)?.content).toContain("Code was not written.");
		const summary = JSON.parse(readFileSync(join(command.artifacts, "summary.json"), "utf8"));
		expect(summary.command).toBe("fh-plan");
		expect(summary.ok).toBe(true);
		expect(summary.planPath).toBe(plan);
	});

	test("a bad folder is refused before a planner starts", async () => {
		const cwd = repo();
		const command = harness(cwd);
		await command.run("--plan-dir ../adws add a health check");
		expect(command.notices[0]).toContain("..");
		expect(command.panels).toHaveLength(0);
		expect(existsSync(join(cwd, "planADW"))).toBe(false);
	});
});
