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
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { runChild, runProc } from "./child-runner.ts";
import { parsePublishTo, runCollaboration } from "./collaboration-run.ts";
export { parsePublishTo };
import {
	builderPrompt,
	correctionPrompt,
	ensureGateMetadata,
	extractGateScript,
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
	type AgentStat,
	type FhDetails,
	type HarnessDeps,
} from "./runtime.ts";
import { waitForWriterLease, type WriterLease } from "./writer-lease.ts";

interface CollaborationInput {
	prompt: string;
	publishTo: string | null;
}

/** Generated content has no option or publication authority. */
export type CollaboratePromptHandler = (prompt: string, ctx: any) => Promise<void>;

/** Only the direct command may parse options, and only before prompt content. */
export function parseCollaborateArgs(raw: string): CollaborationInput {
	let prompt = (raw ?? "").trim();
	let publishTo: string | null = null;
	while (prompt) {
		const token = /^\S+/.exec(prompt)![0];
		if (token === "--") {
			prompt = prompt.slice(2).trimStart();
			break;
		}
		if (token !== "--publish-to") {
			if (token.startsWith("--publish-to=")) throw new Error("Use --publish-to <remote/branch>, not --publish-to=<target>");
			break;
		}
		if (publishTo !== null) throw new Error("Duplicate --publish-to option");
		prompt = prompt.slice(token.length).trimStart();
		const value = /^\S+/.exec(prompt)?.[0];
		if (!value || value.startsWith("-")) throw new Error("Usage: /fh-collaborate [--publish-to <remote/branch>] <prompt>");
		parsePublishTo(value); // Validate before any artifacts, agents, or remote refresh.
		publishTo = value;
		prompt = prompt.slice(value.length).trimStart();
	}
	return { prompt, publishTo };
}

/** Register the user command, returning a separate no-publication prompt entry. */
export function registerCollaborateCommand(pi: ExtensionAPI, h: HarnessDeps): CollaboratePromptHandler {
	const execute = async (input: CollaborationInput, ctx: any): Promise<void> => {
		const initialSpawns = new Map<string, { sessionDir: string; sessionId?: string; resume?: string; fork?: string }>();
		const result = await runCollaboration({
			prompt: input.prompt,
			publishTo: input.publishTo,
			ctx,
			stack: h.modelStack(),
			newSlotRun: h.newSlotRun,
			mkArtifacts: h.mkArtifacts,
			save: h.save,
			prepareKnowledge: (query, cwd, artifactsDir) => h.prepareKnowledge(query, cwd, artifactsDir),
			startStoppable: h.startStoppable,
			startGridWidget: h.startGridWidget,
			totals: h.totals,
			ensureSummary: h.ensureSummary,
			captureKnowledge: h.captureKnowledge,
			cachedSlotId: h.cachedSlotId,
			childTimeoutMs: h.childTimeoutMs,
			noteHost: h.noteHost,
			panel: h.panel,
			stoppedPanel: h.stoppedPanel,
			setStatus: (type, text) => ctx.ui.setStatus(type, text),
			notify: (text, level) => ctx.ui.notify(text, level),
			setWidget: (id, lines, opts) => ctx.ui.setWidget(id, lines, opts),
		}, {
			child: async (call) => {
				let initial = initialSpawns.get(call.slot.id);
				if (!initial) {
					initial = h.slotInitialSpawn(call.slot, ctx, call.sessionDir);
					initialSpawns.set(call.slot.id, initial);
				}
				const identity = call.spawn === "initial" ? initial : h.slotNextSpawn(call.slot, call.run, initial, ctx);
				await runChild({
					run: call.run,
					prompt: call.prompt,
					systemPrompt: call.systemPrompt,
					appendSystemPrompts: call.appendSystemPrompts,
					tools: call.tools,
					thinking: call.thinking,
					...identity,
					cwd: ctx.cwd,
					timeoutMs: h.childTimeoutMs(),
					signal: call.signal,
					onQuotaWait: call.onQuotaWait,
				});
			},
			escalate: async (question, options) => {
				if (typeof ctx?.ui?.select !== "function") return undefined;
				try {
					const choice = await ctx.ui.select(question, options);
					return typeof choice === "string" && options.includes(choice) ? choice : undefined;
				} catch {
					return undefined;
				}
			},
		});
		if (result.hostRecovery) {
			const { planPath, reportsDir, finalPath, artifactsDir } = result.hostRecovery;
			pi.sendMessage({ customType: "fh-host-recovery", display: true, content: `Pi host recovery is authorized for the original request, within the existing working tree. Collaboration remains BLOCKED; no child report may be treated as accepted unless its evidence and outcome are verified. Read ${planPath}, ${reportsDir}, and ${finalPath}; inspect current files before editing. You may complete missing reversible research, writing, audits and final integration yourself, preserving unrelated changes. Do not bypass a real clinical, data, publication, or human approval gate. Do not claim the collaboration succeeded; report separately what you verified and completed as host. No commit, push, deploy or outreach.`, details: { artifactsDir, blocked: true } }, { deliverAs: "followUp", triggerTurn: true });
		}
	};
	pi.registerCommand("fh-collaborate", {
		description:
			"Every agent plans read-only, the architect merges one delegation DAG, then tasks execute as dependencies clear — parallel where possible, exactly one shared-CWD writer at a time. Optional leading --publish-to <remote/branch> is parent-owned non-force fast-forward only.",
		handler: async (raw, ctx) => {
			let input: CollaborationInput;
			try {
				input = parseCollaborateArgs(raw ?? "");
			} catch (error) {
				ctx.ui.notify(error instanceof Error ? error.message : String(error), "warning");
				return;
			}
			await execute(input, ctx);
		},
	});
	return async (prompt, ctx) => {
		if (typeof prompt !== "string") throw new Error("Internal collaboration requires prompt text only");
		await execute({ prompt, publishTo: null }, ctx);
	};
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
					writerLease = await waitForWriterLease(ctx.cwd, `/fh-auto-validate ${path.basename(artifactsDir)}`, { signal: stopper.signal, onWait: (holder) => ctx.ui.setStatus(CUSTOM_TYPE, `waiting for the writer lease — ${holder}`) });
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
