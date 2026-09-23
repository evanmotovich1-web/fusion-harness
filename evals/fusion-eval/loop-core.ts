/**
 * The self-improving eval loop, as a pure state machine. Every side effect
 * (git, paid eval runs, the fix run, tests, PRs, logs, the lock) comes in
 * through LoopDeps, so the same tick() drives production and the stress tests.
 *
 * One tick:
 *   1. single-instance lock (a concurrent tick returns "busy")
 *   2. has the watched branch moved, is the nightly full run due, or did the last
 *      tick die mid-phase? else "idle"
 *   3. evaluate that commit on the locked suite (graded by the loop's TRUSTED runner)
 *   4. compare to the ACCEPTED bar; re-run each apparent regression once —
 *      real models are noisy, and only a repeatable regression counts
 *   5. none confirmed  → raise the bar ("accepted")
 *      confirmed       → a fix run proposes a branch. The GATE merges it only if
 *                        the full tests pass with no fewer tests than the base,
 *                        TWO consecutive eval re-runs of every regressed task meet
 *                        the bar on the same suite, and the branch has not moved.
 *                        Otherwise the PR stays open and the reason goes to ROT.
 *   6. a regression item (task + kind) is fix-attempted at most once while it
 *      persists; once it recovers, a recurrence gets a fresh attempt. The one
 *      stop condition is no progress, never a fixed count.
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
	/** Regression items ("group/task:kind") a fix was already attempted for, while they persist. */
	attempted: string[];
	/** Stuck items already reported to ROT — reported once, then quiet until they recover. */
	reportedStuck?: string[];
	/** Consecutive clean ticks per attempted item; two in a row = recovered (one lucky run is not). */
	cleanStreak?: Record<string, number>;
	/** The last error message sent to ROT — a persisting error is reported once, not every tick. */
	lastErrorReported?: string;
	/** Set while a tick runs; still set at the next tick means the last one died. */
	inFlight?: { commit: string; phase: string; startedAt: number };
	history: HistoryEntry[];
}

export type TickOutcome = "busy" | "idle" | "accepted" | "noise-only" | "fixed-merged" | "fix-pr-open" | "fix-failed" | "stuck" | "error";

export interface Regression { key: string; kind: "pass-rate" | "harness-fail" | "writers" | "cost"; detail: string }

export interface FixProposal { branch: string; commit: string }

export interface TestResult { ok: boolean; summary: string; total: number }

export interface LoopDeps {
	now(): number;
	/** Acquire the single-instance lock; undefined when another tick holds it. */
	lock(): (() => void) | undefined;
	readState(): LoopState;
	writeState(state: LoopState): void;
	/** Latest commit of the watched branch (fetches first). */
	head(): Promise<string>;
	/** Hash of the loop's OWN sealed suite (its lock.json) — the only suite results may be graded by. */
	suiteHash(): string;
	/** Evaluate `commit` with the loop's trusted runner; tasks undefined = the whole suite. */
	evaluate(commit: string, groups: string[], tasks?: string[]): Promise<EvalRecord[]>;
	diffSince(from: string | undefined, to: string): Promise<string>;
	proposeFix(input: { base: string; regressions: Regression[]; evidence: string }): Promise<FixProposal | undefined>;
	runTests(commit: string): Promise<TestResult>;
	/** merge=true must merge exactly fix.commit (no newer head) or report merged:false. */
	publish(fix: FixProposal, input: { title: string; body: string; merge: boolean; base: string }): Promise<{ pr?: string; merged: boolean }>;
	log(line: string, opts?: { rot?: boolean }): void;
	/** Runs inside the lock just before it is released (cleanup, runner refresh). Never for a busy tick. */
	afterTick?(): Promise<void> | void;
}

/** An error's shape: paths, hashes and numbers removed, so one persisting error is one ROT line. */
export const errorShape = (message: string) => message.replace(/(?:\/[^\s:'"]+)+/g, "<path>").replace(/\b[0-9a-f]{7,40}\b/g, "<sha>").replace(/\d+/g, "#");

export const emptyState = (): LoopState => ({ accepted: {}, attempted: [], history: [] });

export const recordKey = (record: Pick<EvalRecord, "group" | "task">) => `${record.group}/${record.task}`;

export const itemOf = (regression: Pick<Regression, "key" | "kind">) => `${regression.key}:${regression.kind}`;

const pct = (value: number) => `${Math.round(value * 100)}%`;

/** Regressions of `current` against the accepted bar. Keys with no bar (or another suite) are not regressions. */
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

/** Strict gate check: a result for exactly this key, on the bar's suite, at or above it. */
export function meetsBar(record: EvalRecord | undefined, bar: EvalRecord | undefined, suiteHash: string | undefined): string | undefined {
	if (!record) return "no result";
	if (!suiteHash || record.suiteHash !== suiteHash) return `graded by a different suite (${record.suiteHash?.slice(0, 12) ?? "none"})`;
	if (record.maxWriters !== null && record.maxWriters > 1) return `${record.maxWriters} concurrent writers`;
	if (!bar) return undefined;
	if (record.passRate < bar.passRate) return `hidden tests ${pct(record.passRate)} < bar ${pct(bar.passRate)}`;
	if (bar.harnessOk && !record.harnessOk) return "harness run failed";
	if (bar.costUsd > 0 && record.costUsd > bar.costUsd * 1.5 && record.costUsd - bar.costUsd > 0.5) return `cost $${record.costUsd.toFixed(2)} vs bar $${bar.costUsd.toFixed(2)}`;
	return undefined;
}

function splitKey(key: string): { group: string; task: string } {
	const slash = key.indexOf("/");
	return { group: key.slice(0, slash), task: key.slice(slash + 1) };
}

/**
 * Only raise the bar, and only with results from the bar's own suite. Cost is
 * anchored to the first accepted run of each task so it cannot ratchet upward.
 */
function raiseBar(state: LoopState, records: EvalRecord[]): void {
	for (const record of records) {
		if (!state.suiteHash || record.suiteHash !== state.suiteHash) continue;
		const key = recordKey(record);
		const bar = state.accepted[key];
		const worse = bar && (record.passRate < bar.passRate || (bar.harnessOk && !record.harnessOk));
		// Cost anchor: the first NONZERO accepted cost (a $0 run must not switch the cost check off).
		if (!worse) state.accepted[key] = bar ? { ...record, costUsd: bar.costUsd > 0 ? bar.costUsd : record.costUsd } : record;
	}
}

export async function tick(deps: LoopDeps, config: LoopConfig): Promise<{ outcome: TickOutcome; detail: string }> {
	const release = deps.lock();
	if (!release) return { outcome: "busy", detail: "another tick holds the loop lock" };
	const state = deps.readState();
	let commit = "";
	const finish = (outcome: TickOutcome, detail: string, rot = false) => {
		state.inFlight = undefined;
		if (outcome !== "error") state.lastErrorReported = undefined;
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
		const crashed = state.inFlight;
		if (crashed) deps.log(`recovered: previous tick died during "${crashed.phase}" on ${crashed.commit.slice(0, 8)} — re-running from the top`);
		commit = await deps.head();
		const nightlyDue = state.lastNightlyAt === undefined || deps.now() - state.lastNightlyAt >= config.nightlyEveryMs;
		if (commit === state.lastEvaluatedCommit && !nightlyDue && !crashed) {
			deps.writeState(state);
			return { outcome: "idle", detail: "no new commit and nightly not due" };
		}
		const groups = nightlyDue ? config.nightlyGroups : config.groups;

		phase("evaluate");
		// The trusted suite comes from the loop's own lock.json, never from results: an evaluation
		// graded by anything else is rejected, so no result can reset the bar or the attempt memory.
		const trusted = deps.suiteHash();
		if (state.suiteHash && state.suiteHash !== trusted) {
			deps.log(`sealed suite re-locked ${state.suiteHash.slice(0, 12)} → ${trusted.slice(0, 12)}: previous bar is not comparable; starting a new bar`);
			state.accepted = {};
			state.attempted = [];
			state.reportedStuck = [];
		}
		state.suiteHash = trusted;
		const records = await deps.evaluate(commit, groups, config.tasks);
		const foreign = records.filter((record) => record.suiteHash !== trusted);
		if (foreign.length) throw new Error(`evaluation returned ${foreign.length} result(s) graded by a different suite than the sealed one (${trusted.slice(0, 12)}) — refusing to judge`);

		const apparent = findRegressions(records, state.accepted);
		let confirmed: Regression[] = [];
		if (apparent.length) {
			phase("confirm");
			const rerun: EvalRecord[] = [];
			for (const key of new Set(apparent.map((r) => r.key))) {
				const { group, task } = splitKey(key);
				rerun.push(...(await deps.evaluate(commit, [group], [task])));
			}
			if (rerun.some((record) => record.suiteHash !== trusted)) throw new Error("confirming re-run returned results graded by a different suite — refusing to judge");
			const stillBad = new Set(findRegressions(rerun, state.accepted).map(itemOf));
			confirmed = apparent.filter((r) => stillBad.has(itemOf(r)));
			const noise = apparent.filter((r) => !stillBad.has(itemOf(r)));
			if (noise.length) deps.log(`noise (did not repeat on re-run): ${noise.map((r) => `${r.key} ${r.detail}`).join("; ")}`);
			const confirmedKeys = new Set(confirmed.map((r) => r.key));
			for (const record of rerun) if (!confirmedKeys.has(recordKey(record))) {
				const index = records.findIndex((candidate) => recordKey(candidate) === recordKey(record));
				if (index >= 0) records[index] = record;
			}
		}

		// Items that no longer regress have recovered: a later recurrence gets a fresh attempt.
		const confirmedItems = new Set(confirmed.map(itemOf));
		const evaluatedKeys = new Set(records.map(recordKey));
		const streak = state.cleanStreak ?? {};
		for (const item of new Set([...state.attempted, ...(state.reportedStuck ?? [])])) {
			const key = item.slice(0, item.lastIndexOf(":"));
			if (!evaluatedKeys.has(key)) continue;
			streak[item] = confirmedItems.has(item) ? 0 : (streak[item] ?? 0) + 1;
		}
		const recovered = (item: string) => (streak[item] ?? 0) >= 2;
		state.attempted = state.attempted.filter((item) => !recovered(item));
		state.reportedStuck = (state.reportedStuck ?? []).filter((item) => !recovered(item));
		for (const item of Object.keys(streak)) if (recovered(item) || !(state.attempted.includes(item) || (state.reportedStuck ?? []).includes(item))) delete streak[item];
		state.cleanStreak = streak;

		state.lastEvaluatedCommit = commit;
		if (nightlyDue) state.lastNightlyAt = deps.now();

		if (!confirmed.length) {
			raiseBar(state, records);
			state.acceptedCommit = commit;
			return finish(apparent.length ? "noise-only" : "accepted", `${records.length} results at or above the bar${apparent.length ? ` (${apparent.length} apparent regression(s) did not repeat)` : ""}`);
		}

		const regressedKeys = new Set(confirmed.map((r) => r.key));
		raiseBar(state, records.filter((record) => !regressedKeys.has(recordKey(record))));

		const fresh = confirmed.filter((r) => !state.attempted.includes(itemOf(r)));
		const stale = confirmed.filter((r) => state.attempted.includes(itemOf(r)));
		if (stale.length) {
			const unreported = stale.filter((r) => !(state.reportedStuck ?? []).includes(itemOf(r)));
			state.reportedStuck = [...(state.reportedStuck ?? []), ...unreported.map(itemOf)];
			const line = `already attempted, no progress — needs a human: ${stale.map((r) => `${r.key} ${r.detail}`).join("; ")}`;
			if (!fresh.length) return finish("stuck", line, unreported.length > 0);
			deps.log(`stuck (not retried): ${line}`, { rot: unreported.length > 0 });
		}

		phase("diagnose");
		const targetKeys = new Set(fresh.map((r) => r.key));
		const evidence = [
			`Regressions confirmed on ${commit} against the accepted bar (${state.acceptedCommit ?? "none"}):`,
			...fresh.map((r) => `- ${r.key} [${r.kind}] ${r.detail}`),
			"",
			"Failing evidence:",
			...records.filter((record) => targetKeys.has(recordKey(record))).map((record) => `## ${recordKey(record)}\n${record.evidence ?? record.executionFailure ?? "(no output)"}`),
			"",
			"Diff since the accepted commit:",
			await deps.diffSince(state.acceptedCommit, commit),
		].join("\n");

		phase("fix");
		let fix: FixProposal | undefined;
		try {
			fix = await deps.proposeFix({ base: commit, regressions: fresh, evidence });
		} catch (error) {
			// A fix run that fails (or is rejected, e.g. it touched protected paths) is still an attempt.
			state.attempted = [...new Set([...state.attempted, ...fresh.map(itemOf)])];
			return finish("fix-failed", `fix run failed for ${fresh.map(itemOf).join(", ")}: ${error instanceof Error ? error.message : String(error)}`, true);
		}
		// Recorded only once the attempt finished: a process crash before this point retries it.
		state.attempted = [...new Set([...state.attempted, ...fresh.map(itemOf)])];
		if (!fix) return finish("fix-failed", `fix run produced no change for: ${fresh.map(itemOf).join(", ")}`, true);

		const title = `eval-loop: fix ${fresh.map((r) => `${r.key} ${r.kind}`).join(", ")}`;
		const leaveOpen = async (why: string) => {
			const pr = await deps.publish(fix, { title, body: `${evidence}\n\nGATE FAILED — ${why}`, merge: false, base: commit });
			return finish("fix-pr-open", `gate failed: ${why}; PR left open ${pr.pr ?? ""}`, true);
		};

		phase("gate-tests");
		const tests = await deps.runTests(fix.commit);
		if (!tests.ok) return await leaveOpen(`tests: ${tests.summary}`);
		const baseTests = await deps.runTests(commit);
		if (tests.total < baseTests.total) return await leaveOpen(`the fix has fewer tests (${tests.total}) than its base (${baseTests.total})`);

		phase("gate-eval");
		let gated: EvalRecord[] = [];
		for (let round = 1; round <= 2; round++) {
			const recheck: EvalRecord[] = [];
			const tasksByGroup = new Map<string, string[]>();
			for (const key of targetKeys) {
				const { group, task } = splitKey(key);
				tasksByGroup.set(group, [...(tasksByGroup.get(group) ?? []), task]);
			}
			for (const [group, tasks] of tasksByGroup) recheck.push(...(await deps.evaluate(fix.commit, [group], tasks)));
			const failures = [...targetKeys].flatMap((key) => {
				const why = meetsBar(recheck.find((record) => recordKey(record) === key), state.accepted[key], state.suiteHash);
				return why ? [`${key}: ${why}`] : [];
			});
			if (failures.length) return await leaveOpen(`eval re-run ${round}/2: ${failures.join("; ")}`);
			if (round === 2) gated = recheck;
		}

		phase("publish");
		if ((await deps.head()) !== commit) return await leaveOpen("the branch moved during the fix; the merged result would be untested — re-evaluated next tick");
		const pr = await deps.publish(fix, { title, body: `${evidence}\n\nGATE PASSED — tests: ${tests.summary} (base ${baseTests.total}); two eval re-runs at/above the bar for ${[...targetKeys].join(", ")}.`, merge: config.autoMerge, base: commit });
		if (!pr.merged) return finish("fix-pr-open", `gate passed; PR ${pr.pr ?? ""} awaiting merge (autoMerge ${config.autoMerge ? "on, merge failed" : "off"})`, config.autoMerge);
		raiseBar(state, gated); // only now: this code is actually on the branch
		return finish("fixed-merged", `gate passed and merged ${pr.pr ?? fix.branch}; the merge commit is evaluated on the next tick`);
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		const fresh = state.lastErrorReported !== errorShape(message);
		state.lastErrorReported = errorShape(message);
		return finish("error", message, fresh);
	} finally {
		try { await deps.afterTick?.(); } catch (error) { deps.log(`afterTick failed: ${error instanceof Error ? error.message : String(error)}`); }
		release();
	}
}
