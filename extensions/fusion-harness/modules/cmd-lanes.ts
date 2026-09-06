/**
 * cmd-lanes.ts — /fh-lanes: every builder WRITES at once, each in its OWN LANE.
 *
 * LANE MODE (factory, default on) already seats every slot in its own git worktree for
 * the read-only fan-out commands. /fh-lanes is the write-enabled form: builders get FULL
 * tools inside their lane and run concurrently — several models writing at the same
 * time — and the single-writer invariant still holds where it matters: only the
 * ARCHITECT's integration turn, holding the writer lease, touches the user's checkout.
 *
 *   /fh-lanes <prompt>              lanes → parallel builders → architect integrates
 *   /fh-lanes --no-merge <prompt>   lanes → parallel builders → lanes left for you
 *   /fh-lanes on|off                lane mode for every fan-out command (session-only)
 *   /fh-lanes status                every lane's branch, churn, path
 *   /fh-lanes diff <slot>           one lane's full patch
 *   /fh-lanes clean                 remove every lane worktree and branch
 */

import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { runChild } from "./child-runner.ts";
import { cleanLanes, commitLane, git, laneDiff, laneRootFor, laneStatus, listLaneRemovalEvidence, listLanes, type LaneStatus } from "./lanes.ts";
import { orderedSlots } from "./model-stack.ts";
import { contractSystemPrompt, laneMergePrompt, laneWorkerPrompt, parseLanesArgs, withKnowledge } from "./prompt-library.ts";
import { CUSTOM_TYPE, FULL_TOOLS, runError, runOk, toStat, type AgentRun, type HarnessDeps, type LaneOutcome, type Role } from "./runtime.ts";
import { acquireWriterLease, type WriterLease } from "./writer-lease.ts";

/** What /fh-lanes remembers about the last run, so `status` and `diff` work after the command ends. */
interface LaneRecord {
	slotId: string;
	slotName: string;
	branch: string;
	path: string;
	base: string;
	sha?: string;
	committed: boolean;
	prompt: string;
	artifactsDir: string;
	finishedAt: number;
}
const laneRecordsPath = (cwd: string): string => path.join(laneRootFor(cwd), "lanes.json");
const readLaneRecords = async (cwd: string): Promise<LaneRecord[]> => {
	try {
		const parsed = JSON.parse(await fs.promises.readFile(laneRecordsPath(cwd), "utf8"));
		return Array.isArray(parsed) ? parsed : [];
	} catch {
		return [];
	}
};

export function registerLanesCommand(pi: ExtensionAPI, h: HarnessDeps): (raw: string, ctx: any) => Promise<void> {
	let handler: (raw: string, ctx: any) => Promise<void>;
	pi.registerCommand("fh-lanes", {
		description: "Every builder implements the request at once, each in its own git worktree lane; the architect integrates the best result. Also: on · off · status · diff <slot> · clean",
		handler: handler = async (raw, ctx) => {
			h.noteHost(ctx);
			const args = parseLanesArgs(raw ?? "");
			const stack = h.modelStack();

			// ── Lane management subcommands: no models run ──
			if (args.action === "on" || args.action === "off") {
				h.setLaneMode(args.action === "on");
				ctx.ui.notify(args.action === "on" ? "fusion-harness: LANE MODE on — every fan-out command seats each slot in its own worktree" : "fusion-harness: LANE MODE off — fan-out commands share the cwd (/fh-lanes <prompt> still uses lanes)", "info");
				return;
			}
			if (args.action === "clean") {
				let lease: WriterLease | undefined;
				try {
					lease = acquireWriterLease(ctx.cwd, "/fh-lanes clean");
					let headSha = "(unborn)";
					try { headSha = await git(ctx.cwd, ["rev-parse", "HEAD"]); } catch { /* unborn or not a repo */ }
					const evidence = await listLaneRemovalEvidence(ctx.cwd);
					const evidenceLines = evidence.length
						? evidence.map((lane) => `- ${lane.slotId}: branch ${lane.branchSha ?? "absent"}; worktree HEAD ${lane.worktreeHeadSha ?? "absent"}; status ${lane.statusHash ?? "absent"}; dirty paths ${lane.dirtyPaths}`).join("\n")
						: "- no lane worktrees or branches";
					h.panel(
						{ kind: "lanes", command: "fh-lanes", ok: true, lanes: [] },
						`Lane cleanup evidence captured under writer lease before removal. Checkout HEAD: \`${headSha}\`.\n${evidenceLines}`,
					);
					const removed = await cleanLanes(ctx.cwd, evidence);
					ctx.ui.notify(removed.length ? `fusion-harness: removed ${removed.length} lane${removed.length === 1 ? "" : "s"} (${removed.join(", ")})` : "fusion-harness: no lanes to remove", "info");
					h.panel(
						{ kind: "lanes", command: "fh-lanes", ok: true, lanes: [] },
						`Lane cleanup completed after exact evidence revalidation. Removed: ${removed.length ? removed.join(", ") : "none"}. This is an explicit destructive command, not publication.`,
					);
				} catch (error) {
					ctx.ui.notify(`fusion-harness: lane cleanup failed — ${error instanceof Error ? error.message : String(error)}`, "error");
				} finally {
					lease?.release();
				}
				return;
			}
			if (args.action === "status") {
				const records = await readLaneRecords(ctx.cwd);
				let live: Array<{ slotId: string; path: string; branch: string }> = [];
				try {
					live = await listLanes(ctx.cwd);
				} catch (error) {
					ctx.ui.notify(`fusion-harness: ${error instanceof Error ? error.message : String(error)}`, "error");
					return;
				}
				if (!live.length) {
					ctx.ui.notify(`fusion-harness: no lanes exist for this project (lane mode ${h.laneMode() ? "on" : "off"}) — any fan-out command seeds them`, "info");
					return;
				}
				const outcomes: LaneOutcome[] = [];
				const rows: string[] = ["| lane | branch | churn since last commit | work commit | path |", "|---|---|---|---|---|"];
				for (const lane of live) {
					const record = records.find((candidate) => candidate.slotId === lane.slotId);
					const slot = stack.slots.find((candidate) => candidate.id === lane.slotId);
					let churn: LaneStatus = { files: 0, insertions: 0, deletions: 0 };
					try {
						churn = await laneStatus(lane);
					} catch {}
					outcomes.push({ slotId: lane.slotId, slotName: record?.slotName ?? slot?.name ?? lane.slotId, color: slot?.color, branch: lane.branch, path: lane.path, status: "done", committed: record?.committed ?? false, sha: record?.sha, files: churn.files, insertions: churn.insertions, deletions: churn.deletions });
					rows.push(`| ${record?.slotName ?? lane.slotId} | ${lane.branch} | ${churn.files} files +${churn.insertions} −${churn.deletions} | ${record?.committed ? record.sha?.slice(0, 10) : "none"} | ${lane.path} |`);
				}
				const last = records[0];
				h.panel({ kind: "lanes", command: "fh-lanes", ok: true, lanes: outcomes }, [`Lane mode: ${h.laneMode() ? "on" : "off"}`, last ? `Last /fh-lanes run: ${new Date(last.finishedAt).toISOString()} — "${last.prompt.replace(/\s+/g, " ").slice(0, 100)}"\nArtifacts: ${last.artifactsDir}` : "", "", ...rows, "", "Inspect a lane: `/fh-lanes diff <slot>` · remove all: `/fh-lanes clean` · toggle: `/fh-lanes on|off`"].join("\n"));
				return;
			}
			if (args.action === "diff") {
				const records = await readLaneRecords(ctx.cwd);
				const target = (args.slot ?? "").toLowerCase();
				const record = target ? records.find((candidate) => candidate.slotId.toLowerCase() === target || candidate.slotName.toLowerCase() === target) : undefined;
				if (!record) {
					ctx.ui.notify(records.length ? `fusion-harness: /fh-lanes diff <slot> — known lanes: ${records.map((candidate) => candidate.slotId).join(", ")}` : "fusion-harness: no lane records — run /fh-lanes <prompt> first", records.length ? "warning" : "info");
					return;
				}
				try {
					const diff = await laneDiff(ctx.cwd, record);
					const slot = stack.slots.find((candidate) => candidate.id === record.slotId);
					const insertions = Number(/(\d+) insertion/.exec(diff.stat)?.[1] ?? 0);
					const deletions = Number(/(\d+) deletion/.exec(diff.stat)?.[1] ?? 0);
					h.panel({ kind: "lanes", command: "fh-lanes", ok: true, lanes: [{ slotId: record.slotId, slotName: record.slotName, color: slot?.color, branch: record.branch, path: record.path, status: "done", committed: record.committed, sha: record.sha, files: diff.files.length, insertions, deletions }] }, diff.patch.trim() ? `### ${record.slotName} — ${record.base.slice(0, 10)}..${record.branch}\n\`\`\`\n${diff.stat}\n\`\`\`\n\`\`\`diff\n${diff.patch}\n\`\`\`` : `${record.slotName} changed nothing in its lane.`);
				} catch (error) {
					ctx.ui.notify(`fusion-harness: ${error instanceof Error ? error.message : String(error)}`, "error");
				}
				return;
			}

			// ── The run: lanes → parallel builders → (architect integration) ──
			const prompt = args.prompt;
			if (!prompt) {
				ctx.ui.notify("Usage: /fh-lanes [--no-merge] <prompt>  ·  /fh-lanes on|off  ·  status  ·  diff <slot>  ·  clean", "warning");
				return;
			}
			const builders = orderedSlots(stack).filter((slot) => !slot.architect);
			const architect = stack.architect;
			const startedAt = Date.now();
			const artifactsDir = await h.mkArtifacts();
			await h.save(artifactsDir, "prompt.md", prompt);
			await h.save(artifactsDir, "stack.json", JSON.stringify(stack, null, 2));
			const packet = await h.prepareKnowledge(prompt, ctx.cwd, artifactsDir);
			await fs.promises.mkdir(path.join(artifactsDir, "agents"), { recursive: true });
			h.panel({ kind: "prompt", command: "fh-lanes", ok: true }, `/fh-lanes ${(raw ?? "").trim()}`);
			h.panel({ kind: "banner", command: "fh-lanes", ok: true, prompt, roles: [...builders.map((slot) => ({ role: "BUILDER" as Role, model: slot.model, slotId: slot.id, slotName: slot.name, color: slot.color, primary: slot.primary, architect: false })), ...(args.merge ? [{ role: "ARCHITECT" as Role, model: architect.model, slotId: architect.id, slotName: architect.name, color: architect.color, primary: false, architect: true }] : [])], artifactsDir }, "");

			// /fh-lanes IS lanes: seed even with lane mode off, and fail loudly instead of falling back.
			let lanes: Map<string, import("./lanes.ts").Lane>;
			try {
				lanes = (await h.seedLanes(ctx, builders, { force: true }))!;
			} catch (error) {
				h.panel({ kind: "error", command: "fh-lanes", ok: false, artifactsDir }, `Could not create the lanes: ${error instanceof Error ? error.message : String(error)}`);
				return;
			}

			const runs = builders.map(h.newSlotRun);
			const architectRun = h.newSlotRun(architect);
			const stopper = h.startStoppable(ctx, "fh-lanes");
			const stopWidget = h.startGridWidget(ctx, "fh-lanes", runs, args.merge ? architectRun : undefined, startedAt);
			const stopBoard = h.startLaneBoard(ctx, runs, lanes, args.merge ? "full tools · architect integrates when all finish" : "full tools · --no-merge: lanes stay for you");

			let writerLease: WriterLease | undefined;
			const outcomes: LaneOutcome[] = [];
			const laneResults: Array<{ run: AgentRun; branch: string; path: string; base: string; sha?: string; committed: boolean; files: string[]; stat: string; patch: string; reportPath: string; patchPath: string }> = [];
			const summarySessions = () => Object.fromEntries([...builders, architect].map((slot) => [slot.id, [...runs, architectRun].find((run) => run.slot?.id === slot.id)?.sessionRef ?? h.cachedSlotId(slot)]));
			try {
				// ── Phase 1: every builder, at once, in its own lane ──
				ctx.ui.setStatus(CUSTOM_TYPE, `lanes: ${runs.length} builder${runs.length === 1 ? "" : "s"} working in parallel worktrees…`);
				await Promise.all(runs.map(async (run) => {
					const slot = run.slot!;
					const lane = lanes.get(slot.id)!;
					const agentDir = path.join(artifactsDir, "agents", slot.id);
					await fs.promises.mkdir(agentDir, { recursive: true });
					// The child's cwd IS the lane: every tool call it makes lands in its own worktree.
					await runChild({ run, prompt: withKnowledge(laneWorkerPrompt(slot, stack, prompt, lane, ctx.cwd), packet, { writeCapable: true }), systemPrompt: slot.systemPrompt, appendSystemPrompts: slot.appendSystemPrompts, tools: FULL_TOOLS, thinking: slot.thinking, ...h.slotInitialSpawn(slot, ctx, agentDir), cwd: lane.path, timeoutMs: h.childTimeoutMs(), signal: stopper.signal });
					const reportPath = path.join(agentDir, "report.md");
					await h.save(agentDir, "report.md", runOk(run) ? run.text : `FAILED: ${runError(run)}`);
					if (stopper.stopped()) return; // partial work stays uncommitted in the lane for inspection
					// Whatever the builder left behind is evidence — commit it even when the run failed.
					let commit: { committed: boolean; sha?: string; files: string[] } = { committed: false, files: [] };
					let stat = "";
					let patch = "";
					try {
						commit = await commitLane(lane, `fh lane ${slot.id}: ${prompt.replace(/\s+/g, " ").slice(0, 72)}`);
						const diff = await laneDiff(ctx.cwd, lane);
						stat = diff.stat;
						patch = diff.patch;
						commit.files = diff.files;
					} catch (error) {
						run.stderr += `\nlane commit failed: ${error instanceof Error ? error.message : String(error)}`;
					}
					const patchPath = path.join(agentDir, "lane.patch");
					await h.save(agentDir, "lane.patch", patch);
					await h.save(agentDir, "diffstat.txt", stat);
					const churnNow = { files: commit.files.length, insertions: Number(/(\d+) insertion/.exec(stat)?.[1] ?? 0), deletions: Number(/(\d+) deletion/.exec(stat)?.[1] ?? 0) };
					outcomes.push({ slotId: slot.id, slotName: slot.name, color: slot.color, branch: lane.branch, path: lane.path, status: run.status, committed: commit.committed, sha: commit.sha, ...churnNow });
					laneResults.push({ run, branch: lane.branch, path: lane.path, base: lane.base, sha: commit.sha, committed: commit.committed, files: commit.files, stat, patch, reportPath, patchPath });
				}));
				if (stopper.stopped()) {
					h.stoppedPanel("fh-lanes", runs, artifactsDir, startedAt, `Builders were stopped; partial work remains uncommitted in each lane under ${laneRootFor(ctx.cwd)}.`);
					return;
				}
				// Keep slot order for every roster the user sees.
				outcomes.sort((a, b) => builders.findIndex((slot) => slot.id === a.slotId) - builders.findIndex((slot) => slot.id === b.slotId));
				laneResults.sort((a, b) => builders.findIndex((slot) => slot.id === a.run.slot!.id) - builders.findIndex((slot) => slot.id === b.run.slot!.id));

				const records: LaneRecord[] = laneResults.map((lane) => ({ slotId: lane.run.slot!.id, slotName: lane.run.slot!.name, branch: lane.branch, path: lane.path, base: lane.base, sha: lane.sha, committed: lane.committed, prompt, artifactsDir, finishedAt: Date.now() }));
				await fs.promises.mkdir(laneRootFor(ctx.cwd), { recursive: true });
				await fs.promises.writeFile(laneRecordsPath(ctx.cwd), `${JSON.stringify(records, null, 2)}\n`, "utf8");
				await h.save(artifactsDir, "lane-manifest.json", JSON.stringify(laneResults.map((lane) => ({ slot: lane.run.slot!.id, name: lane.run.slot!.name, model: lane.run.model, status: lane.run.status, ok: runOk(lane.run), branch: lane.branch, worktree: lane.path, base: lane.base, sha: lane.sha, committed: lane.committed, files: lane.files, report: lane.reportPath, patch: lane.patchPath, error: runOk(lane.run) ? undefined : runError(lane.run) })), null, 2));

				// Every lane's report renders side by side, its diffstat under it — the intermediate work IS output.
				const laneBody = (lane: (typeof laneResults)[number]): string => `${runOk(lane.run) ? lane.run.text : `FAILED: ${runError(lane.run)}`}\n\n### Lane ${lane.branch}\n${lane.committed ? `\`\`\`\n${lane.stat}\n\`\`\`` : "_no changes_"}`;
				h.panel({ kind: "multi", command: "fh-lanes", title: "⫽ LANE RESULTS — every builder, its own worktree", ok: runs.every(runOk), prompt, sources: runs.map(toStat), answers: laneResults.map((lane) => ({ role: lane.run.role, model: lane.run.model, text: laneBody(lane), slotId: lane.run.slot!.id, slotName: lane.run.slot!.name, color: lane.run.slot!.color, primary: lane.run.slot!.primary })), artifactsDir, ...h.totals(runs, startedAt) }, laneResults.map((lane) => `## ${lane.run.slot!.name} · ${lane.branch}\n${laneBody(lane)}`).join("\n\n"));

				const committed = laneResults.filter((lane) => lane.committed);
				const reviewHints = laneResults.map((lane) => `- **${lane.run.slot!.name}** → \`${lane.branch}\` at \`${lane.path}\`${lane.committed ? ` · \`git diff ${lane.base.slice(0, 10)}..${lane.branch}\`` : " · no changes"}`).join("\n");
				if (!args.merge) {
					h.panel({ kind: "lanes", command: "fh-lanes", ok: committed.length > 0, prompt, sources: runs.map(toStat), lanes: outcomes, artifactsDir, ...h.totals(runs, startedAt) }, `${committed.length} of ${laneResults.length} lane${laneResults.length === 1 ? "" : "s"} produced changes. Nothing was integrated (--no-merge) — the main checkout is untouched.\n\n${reviewHints}\n\nIntegrate one yourself with \`git cherry-pick -n <sha>\` (then \`git reset -q\`), or run \`/fh-lanes status\` · \`/fh-lanes diff <slot>\` · \`/fh-lanes clean\`.`);
					await h.captureKnowledge({ cwd: ctx.cwd, runId: path.basename(artifactsDir), texts: runs.map((run) => run.text), command: "fh-lanes", artifactsDir });
					await h.save(artifactsDir, "summary.json", JSON.stringify({ command: "fh-lanes", ok: committed.length > 0, merge: false, knowledgeHash: packet.hash, lanes: outcomes, agents: runs.map(toStat), sessions: summarySessions(), ...h.totals(runs, startedAt) }, null, 2));
					return;
				}
				if (!committed.length) {
					h.panel({ kind: "lanes", command: "fh-lanes", ok: false, prompt, sources: runs.map(toStat), lanes: outcomes, artifactsDir, ...h.totals(runs, startedAt) }, `No lane produced any change, so there is nothing for the architect to integrate.\n\n${reviewHints}`);
					await h.save(artifactsDir, "summary.json", JSON.stringify({ command: "fh-lanes", ok: false, merge: true, integrated: false, knowledgeHash: packet.hash, lanes: outcomes, agents: runs.map(toStat), sessions: summarySessions(), ...h.totals(runs, startedAt) }, null, 2));
					return;
				}

				// ── Phase 2: the ARCHITECT integrates, alone, in the main checkout ──
				try {
					writerLease = acquireWriterLease(ctx.cwd, `/fh-lanes ${path.basename(artifactsDir)}`);
				} catch (error) {
					h.panel({ kind: "error", command: "fh-lanes", ok: false, sources: runs.map(toStat), lanes: outcomes, artifactsDir }, error instanceof Error ? error.message : String(error));
					return;
				}
				ctx.ui.setStatus(CUSTOM_TYPE, `lanes: architect integrating ${committed.length} lane${committed.length === 1 ? "" : "s"} into the main checkout…`);
				await runChild({ run: architectRun, prompt: withKnowledge(laneMergePrompt(architect, prompt, laneResults, ctx.cwd, artifactsDir), packet, { writeCapable: true }), systemPrompt: contractSystemPrompt(architect.systemPrompt, "SYSTEM_PROMPT_LANE_MERGE.md"), appendSystemPrompts: architect.appendSystemPrompts, tools: FULL_TOOLS, thinking: architect.thinking, ...h.slotInitialSpawn(architect, ctx, path.join(artifactsDir, "agents", architect.id)), cwd: ctx.cwd, timeoutMs: h.childTimeoutMs(), signal: stopper.signal });
				if (stopper.stopped()) {
					h.stoppedPanel("fh-lanes", [...runs, architectRun], artifactsDir, startedAt, "The architect's integration was stopped; every lane branch is intact, and the main checkout may hold a partial integration — check `git status`.");
					return;
				}
				await h.save(artifactsDir, "integration.md", runOk(architectRun) ? architectRun.text : `FAILED: ${runError(architectRun)}`);
				const ok = runOk(architectRun);
				h.panel({ kind: "lanes", command: "fh-lanes", ok, prompt, agent: toStat(architectRun), sources: runs.map(toStat), lanes: outcomes, artifactsDir, ...h.totals([...runs, architectRun], startedAt) }, ok ? `${architectRun.text}\n\n---\nLanes kept for review:\n${reviewHints}` : `The architect's integration failed: ${runError(architectRun)}\n\nEvery lane branch is intact:\n${reviewHints}`);
				await h.captureKnowledge({ cwd: ctx.cwd, runId: path.basename(artifactsDir), texts: [architectRun.text, ...runs.map((run) => run.text)], command: "fh-lanes", artifactsDir });
				await h.save(artifactsDir, "summary.json", JSON.stringify({ command: "fh-lanes", ok, merge: true, integrated: ok, knowledgeHash: packet.hash, lanes: outcomes, writerLeasePath: writerLease?.path, agents: [...runs, architectRun].map(toStat), sessions: summarySessions(), ...h.totals([...runs, architectRun], startedAt) }, null, 2));
			} finally {
				await h.ensureSummary(artifactsDir, { command: "fh-lanes", ok: false, stopped: stopper.stopped(), merge: args.merge, lanes: outcomes, writerLeasePath: writerLease?.path, agents: (args.merge ? [...runs, architectRun] : runs).map(toStat), sessions: summarySessions(), ...h.totals(runs, startedAt) });
				writerLease?.release();
				stopper.release();
				stopWidget();
				stopBoard();
				ctx.ui.setStatus(CUSTOM_TYPE, undefined);
			}
		},
	});
	return handler;
}
