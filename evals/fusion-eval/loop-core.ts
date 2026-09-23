/**
 * The self-improving eval loop, as a pure state machine. Every side effect
 * (git, paid eval runs, the fix run, tests, PRs, logs, the lock) comes in
 * through LoopDeps, so the same tick() drives production and the stress tests.
 *
 * One tick:
 *   1. single-instance lock (a concurrent tick returns "busy")
 *   2. has the watched branch moved, or is the nightly full run due? else "idle"
 *   3. evaluate that commit on the locked suite
 *   4. compare to the ACCEPTED bar; re-run each apparent regression once —
 *      real models are noisy, and only a repeatable regression counts
 *   5. none confirmed  → raise the bar ("accepted")
 *      confirmed       → a fix run proposes a branch; the GATE merges it only if
 *                        the full tests pass AND an eval re-run of the regressed
 *                        tasks is back at/above the bar. Otherwise the PR stays
 *                        open for a human and the reason goes to ROT.
 *   6. the same regression signature is never attempted twice: the one stop
 *      condition is no progress, never a fixed count.
 */

export interface EvalRecord {
	group: string;
	task: string;
	suiteHash: string;
	passRate: number;
	harnessOk: boolean;
	maxWriters: number | null;
	costUsd: number;
	hidden: { passed: number; total: number };
	executionFailure?: string | null;
	evidence?: string;
}

export interface LoopConfig {
	/** Groups evaluated when the watched branch moves (keep cheap). */
	groups: string[];
	/** Groups evaluated by the nightly full run. */
	nightlyGroups: string[];
	nightlyEveryMs: number;
	autoMerge: boolean;
	/** Restrict every run to these task ids (default: the whole locked suite). */
	tasks?: string[];
}

export interface HistoryEntry { at: number; commit: string; outcome: TickOutcome; detail: string }

export interface LoopState {
	suiteHash?: string;
	acceptedCommit?: string;
	accepted: Record<string, EvalRecord>;
	lastEvaluatedCommit?: string;
	lastNightlyAt?: number;
	/** Regression signatures a fix was already attempted for (no-progress guard). */
	attempted: string[];
	/** Stuck signatures already reported to ROT — reported once, then quiet. */
	reportedStuck?: string[];
	/** Set while a tick runs; still set at the next tick means the last one crashed. */
	inFlight?: { commit: string; phase: string; startedAt: number };
	history: HistoryEntry[];
}

export type TickOutcome = "busy" | "idle" | "accepted" | "noise-only" | "fixed-merged" | "fix-pr-open" | "fix-failed" | "stuck" | "error";

export interface Regression { key: string; kind: "pass-rate" | "harness-fail" | "writers" | "cost"; detail: string }

export interface FixProposal { branch: string; commit: string }

export interface LoopDeps {
	now(): number;
	/** Acquire the single-instance lock; undefined when another tick holds it. */
	lock(): (() => void) | undefined;
	readState(): LoopState;
	writeState(state: LoopState): void;
	/** Latest commit of the watched branch (fetches first). */
	head(): Promise<string>;
	/** Evaluate `commit` on the locked suite; tasks undefined = the whole suite. */
	evaluate(commit: string, groups: string[], tasks?: string[]): Promise<EvalRecord[]>;
	diffSince(from: string | undefined, to: string): Promise<string>;
	proposeFix(input: { base: string; regressions: Regression[]; evidence: string }): Promise<FixProposal | undefined>;
	runTests(commit: string): Promise<{ ok: boolean; summary: string }>;
	publish(fix: FixProposal, input: { title: string; body: string; merge: boolean }): Promise<{ pr?: string; merged: boolean }>;
	log(line: string, opts?: { rot?: boolean }): void;
}

export const emptyState = (): LoopState => ({ accepted: {}, attempted: [], history: [] });

export const recordKey = (record: Pick<EvalRecord, "group" | "task">) => `${record.group}/${record.task}`;

/** Regressions of `current` against the accepted bar. Keys with no bar yet are not regressions. */
export function findRegressions(current: EvalRecord[], accepted: Record<string, EvalRecord>): Regression[] {
	const out: Regression[] = [];
	for (const record of current) {
		const key = recordKey(record);
		if (record.maxWriters !== null && record.maxWriters > 1) out.push({ key, kind: "writers", detail: `${record.maxWriters} concurrent writers (must be 1)` });
		const bar = accepted[key];
		if (!bar || bar.suiteHash !== record.suiteHash) continue;
		if (record.passRate < bar.passRate) out.push({ key, kind: "pass-rate", detail: `hidden tests ${pct(bar.passRate)} → ${pct(record.passRate)}` });
		if (bar.harnessOk && !record.harnessOk) out.push({ key, kind: "harness-fail", detail: `harness run failed (bar succeeded): ${record.executionFailure ?? "not ok"}` });
		if (bar.costUsd > 0 && record.costUsd > bar.costUsd * 1.5 && record.costUsd - bar.costUsd > 0.5) out.push({ key, kind: "cost", detail: `cost $${bar.costUsd.toFixed(2)} → $${record.costUsd.toFixed(2)}` });
	}
	return out;
}

const pct = (value: number) => `${Math.round(value * 100)}%`;

/** Order-independent identity of a regression set, without the commit: the no-progress guard. */
export function signature(regressions: Regression[]): string {
	return [...new Set(regressions.map((r) => `${r.key}:${r.kind}`))].sort().join("|");
}

function splitKey(key: string): { group: string; task: string } {
	const slash = key.indexOf("/");
	return { group: key.slice(0, slash), task: key.slice(slash + 1) };
}

/** Only raise the bar: a record replaces the accepted one unless it is worse. */
function raiseBar(state: LoopState, records: EvalRecord[]): void {
	for (const record of records) {
		const key = recordKey(record);
		const bar = state.accepted[key];
		const worse = bar && bar.suiteHash === record.suiteHash && (record.passRate < bar.passRate || (bar.harnessOk && !record.harnessOk));
		if (!worse) state.accepted[key] = record;
	}
}

export async function tick(deps: LoopDeps, config: LoopConfig): Promise<{ outcome: TickOutcome; detail: string }> {
	const release = deps.lock();
	if (!release) return { outcome: "busy", detail: "another tick holds the loop lock" };
	const state = deps.readState();
	let commit = "";
	const finish = (outcome: TickOutcome, detail: string, rot = false) => {
		state.inFlight = undefined;
		state.history.push({ at: deps.now(), commit, outcome, detail });
		if (state.history.length > 500) state.history.splice(0, state.history.length - 500);
		deps.writeState(state);
		deps.log(`${outcome}${commit ? ` @${commit.slice(0, 8)}` : ""}: ${detail}`, { rot });
		return { outcome, detail };
	};
	const phase = (name: string) => {
		state.inFlight = { commit, phase: name, startedAt: deps.now() };
		deps.writeState(state);
	};
	try {
		if (state.inFlight) deps.log(`recovered: previous tick died during "${state.inFlight.phase}" on ${state.inFlight.commit.slice(0, 8)} — re-running from the top`);
		commit = await deps.head();
		const nightlyDue = state.lastNightlyAt === undefined || deps.now() - state.lastNightlyAt >= config.nightlyEveryMs;
		if (commit === state.lastEvaluatedCommit && !nightlyDue) {
			state.inFlight = undefined;
			deps.writeState(state);
			return { outcome: "idle", detail: "no new commit and nightly not due" };
		}
		const groups = nightlyDue ? config.nightlyGroups : config.groups;

		phase("evaluate");
		const records = await deps.evaluate(commit, groups, config.tasks);
		const suiteHash = records[0]?.suiteHash;
		if (suiteHash && state.suiteHash && suiteHash !== state.suiteHash) {
			deps.log(`suite changed ${state.suiteHash.slice(0, 12)} → ${suiteHash.slice(0, 12)}: previous bar is not comparable; starting a new bar`);
			state.accepted = {};
			state.attempted = [];
		}
		if (suiteHash) state.suiteHash = suiteHash;

		const apparent = findRegressions(records, state.accepted);
		let confirmed: Regression[] = [];
		if (apparent.length) {
			phase("confirm");
			const keys = [...new Set(apparent.map((r) => r.key))];
			const rerun: EvalRecord[] = [];
			for (const key of keys) {
				const { group, task } = splitKey(key);
				rerun.push(...(await deps.evaluate(commit, [group], [task])));
			}
			const stillBad = new Set(findRegressions(rerun, state.accepted).map((r) => `${r.key}:${r.kind}`));
			confirmed = apparent.filter((r) => stillBad.has(`${r.key}:${r.kind}`));
			const noise = apparent.filter((r) => !stillBad.has(`${r.key}:${r.kind}`));
			if (noise.length) deps.log(`noise (did not repeat on re-run): ${noise.map((r) => `${r.key} ${r.detail}`).join("; ")}`);
			// A confirming re-run that came back clean counts as that key's result.
			const confirmedKeys = new Set(confirmed.map((r) => r.key));
			for (const record of rerun) if (!confirmedKeys.has(recordKey(record))) {
				const index = records.findIndex((candidate) => recordKey(candidate) === recordKey(record));
				if (index >= 0) records[index] = record;
			}
		}

		state.lastEvaluatedCommit = commit;
		if (nightlyDue) state.lastNightlyAt = deps.now();

		if (!confirmed.length) {
			raiseBar(state, records);
			state.acceptedCommit = commit;
			return finish(apparent.length ? "noise-only" : "accepted", `${records.length} results at or above the bar${apparent.length ? ` (${apparent.length} apparent regression(s) did not repeat)` : ""}`);
		}

		// Keep the bar for everything that did not regress.
		const regressedKeys = new Set(confirmed.map((r) => r.key));
		raiseBar(state, records.filter((record) => !regressedKeys.has(recordKey(record))));

		const sig = signature(confirmed);
		if (state.attempted.includes(sig)) {
			const firstReport = !(state.reportedStuck ?? []).includes(sig);
			if (firstReport) state.reportedStuck = [...(state.reportedStuck ?? []), sig];
			return finish("stuck", `same regression already attempted, no progress — needs a human: ${confirmed.map((r) => `${r.key} ${r.detail}`).join("; ")}`, firstReport);
		}
		state.attempted.push(sig);

		phase("diagnose");
		const evidence = [
			`Regressions confirmed on ${commit} against the accepted bar (${state.acceptedCommit ?? "none"}):`,
			...confirmed.map((r) => `- ${r.key} [${r.kind}] ${r.detail}`),
			"",
			"Failing evidence:",
			...records.filter((record) => regressedKeys.has(recordKey(record))).map((record) => `## ${recordKey(record)}\n${record.evidence ?? record.executionFailure ?? "(no output)"}`),
			"",
			"Diff since the accepted commit:",
			await deps.diffSince(state.acceptedCommit, commit),
		].join("\n");

		phase("fix");
		const fix = await deps.proposeFix({ base: commit, regressions: confirmed, evidence });
		if (!fix) return finish("fix-failed", `fix run produced no change for: ${sig}`, true);

		phase("gate-tests");
		const tests = await deps.runTests(fix.commit);
		const title = `eval-loop: fix ${confirmed.map((r) => `${r.key} ${r.kind}`).join(", ")}`;
		if (!tests.ok) {
			const pr = await deps.publish(fix, { title, body: `${evidence}\n\nGATE FAILED — tests: ${tests.summary}`, merge: false });
			return finish("fix-pr-open", `gate failed on tests (${tests.summary}); PR left open ${pr.pr ?? ""}`, true);
		}

		phase("gate-eval");
		const tasksByGroup = new Map<string, string[]>();
		for (const key of regressedKeys) {
			const { group, task } = splitKey(key);
			tasksByGroup.set(group, [...(tasksByGroup.get(group) ?? []), task]);
		}
		const recheck: EvalRecord[] = [];
		for (const [group, tasks] of tasksByGroup) recheck.push(...(await deps.evaluate(fix.commit, [group], tasks)));
		const remaining = findRegressions(recheck, state.accepted);
		const covered = recheck.length >= regressedKeys.size;
		if (remaining.length || !covered) {
			const why = remaining.length ? remaining.map((r) => `${r.key} ${r.detail}`).join("; ") : "eval re-run returned no result for a regressed task";
			const pr = await deps.publish(fix, { title, body: `${evidence}\n\nGATE FAILED — eval re-run: ${why}`, merge: false });
			return finish("fix-pr-open", `gate failed on eval re-run (${why}); PR left open ${pr.pr ?? ""}`, true);
		}

		phase("publish");
		const pr = await deps.publish(fix, { title, body: `${evidence}\n\nGATE PASSED — tests: ${tests.summary}; eval re-run at/above the bar for ${[...regressedKeys].join(", ")}.`, merge: config.autoMerge });
		if (!pr.merged) return finish("fix-pr-open", `gate passed; PR ${pr.pr ?? ""} awaiting merge (autoMerge ${config.autoMerge ? "on, merge failed" : "off"})`, config.autoMerge);
		raiseBar(state, recheck);
		return finish("fixed-merged", `gate passed and merged ${pr.pr ?? fix.branch}; the merge commit is evaluated on the next tick`);
	} catch (error) {
		return finish("error", error instanceof Error ? error.message : String(error), true);
	} finally {
		release();
	}
}
