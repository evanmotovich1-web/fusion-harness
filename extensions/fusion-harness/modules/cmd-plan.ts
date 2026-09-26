/**
 * cmd-plan.ts — /fh-plan: one planner writes one plan file in the open project, then stops.
 *
 * This does not implement the task. The plan lands in the project Pi has open,
 * default folder planADW, so the next message can point at that file.
 */
import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { runChild } from "./child-runner.ts";
import { contractSystemPrompt, fill } from "./prompt-library.ts";
import { missingPlanHeadings, nextPlanFile, parsePlanArgs, resolvePlanDir } from "./plan-dir.ts";
import { CUSTOM_TYPE, FULL_TOOLS, runError, runOk, toStat, type HarnessDeps } from "./runtime.ts";
import { waitForWriterLease, type WriterLease } from "./writer-lease.ts";

export function registerPlanCommand(pi: ExtensionAPI, h: HarnessDeps): void {
	pi.registerCommand("fh-plan", {
		description: "Write a plan in this project and stop. Does not write the code. /fh-plan [--plan-dir DIR] <task>",
		handler: async (raw, ctx) => {
			h.noteHost(ctx);
			let parsed: { planDir: string; task: string };
			try {
				parsed = parsePlanArgs(raw ?? "");
				resolvePlanDir(parsed.planDir);
			} catch (error) {
				ctx.ui.notify(error instanceof Error ? error.message : String(error), "warning");
				return;
			}
			const artifactsDir = await h.mkArtifacts();
			await h.save(artifactsDir, "prompt.md", parsed.task);
			const stack = h.modelStack();
			const slot = stack.architect;
			const run = h.newSlotRun(slot);
			const startedAt = Date.now();
			const stopper = h.startStoppable(ctx, "fh-plan");
			const stopWidget = h.startGridWidget(ctx, "fh-plan", [run], undefined, startedAt);
			let writerLease: WriterLease | undefined;
			let planPath = "";
			try {
				writerLease = await waitForWriterLease(ctx.cwd, `/fh-plan ${path.basename(artifactsDir)}`, {
					signal: stopper.signal,
					onWait: (holder) => ctx.ui.setStatus(CUSTOM_TYPE, `waiting for the writer lease — ${holder}`),
				});
				const target = nextPlanFile(ctx.cwd, parsed.planDir);
				planPath = target.absolute;
				fs.mkdirSync(path.dirname(planPath), { recursive: true });
				const prompt = fill("USER_PROMPT_PLAN.md", {
					TASK: parsed.task,
					REPO_ROOT: ctx.cwd,
					PLAN_DIR: parsed.planDir,
					PLAN_PATH: planPath,
				});
				ctx.ui.setStatus(CUSTOM_TYPE, "plan: writing the plan, not the code…");
				await runChild({
					run,
					prompt,
					systemPrompt: contractSystemPrompt(slot.systemPrompt, "SYSTEM_PROMPT_PLAN.md"),
					appendSystemPrompts: slot.appendSystemPrompts,
					tools: FULL_TOOLS,
					thinking: slot.thinking,
					...h.slotInitialSpawn(slot, ctx, path.join(artifactsDir, "planner")),
					cwd: ctx.cwd,
					timeoutMs: h.childTimeoutMs(),
					signal: stopper.signal,
				});
				if (stopper.stopped()) {
					h.stoppedPanel("fh-plan", [run], artifactsDir, startedAt, "Stopped before the plan was accepted.");
					return;
				}
				const written = fs.existsSync(planPath) ? fs.readFileSync(planPath, "utf8") : "";
				const missing = written ? missingPlanHeadings(written) : [...missingPlanHeadings("")];
				const ok = runOk(run) && written.trim().length > 0 && missing.length === 0;
				const body = ok
					? `Plan written. Code was not written.\n\n${planPath}\n\nNext: read that file. Say go when you want it implemented.`
					: `Plan not accepted.\nExpected file: ${planPath}\n${written ? `Missing headings: ${missing.join(", ")}` : "The planner did not write that file."}\n${runOk(run) ? "" : runError(run)}`;
				h.panel(
					{ kind: ok ? "solo" : "error", command: "fh-plan", ok, agent: toStat(run), artifactsDir, ...h.totals([run], startedAt) },
					body,
				);
				await h.save(artifactsDir, "summary.json", JSON.stringify({
					command: "fh-plan",
					ok,
					planPath,
					planDir: parsed.planDir,
					missingHeadings: missing,
					writerLeasePath: writerLease.path,
					agents: [toStat(run)],
					...h.totals([run], startedAt),
				}, null, 2));
			} catch (error) {
				h.panel(
					{ kind: "error", command: "fh-plan", ok: false, artifactsDir },
					`Plan failed: ${error instanceof Error ? error.message : String(error)}`,
				);
			} finally {
				await h.ensureSummary(artifactsDir, {
					command: "fh-plan",
					ok: false,
					stopped: stopper.stopped(),
					planPath,
					agents: [toStat(run)],
					...h.totals([run], startedAt),
				});
				writerLease?.release();
				stopper.release();
				stopWidget();
				ctx.ui.setStatus(CUSTOM_TYPE, undefined);
			}
		},
	});
}
