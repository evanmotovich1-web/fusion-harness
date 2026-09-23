import { describe, expect, test } from "bun:test";
import { emptyState, errorShape, findRegressions, meetsBar, tick, type EvalRecord, type LoopConfig, type LoopDeps, type LoopState } from "../../../evals/fusion-eval/loop-core.ts";

const CONFIG: LoopConfig = { groups: ["local"], nightlyGroups: ["local", "quad"], nightlyEveryMs: 24 * 3600_000, autoMerge: true };
const TASKS = ["01", "02"];
const good = (group: string, task: string, over: Partial<EvalRecord> = {}): EvalRecord => ({ group, task, suiteHash: "S1", passRate: 1, harnessOk: true, maxWriters: 1, costUsd: 1, hidden: { passed: 6, total: 6 }, ...over });

type Outcome = Partial<EvalRecord> | ((call: number) => Partial<EvalRecord>);

/** Scriptable fake world. `scores[commit][group/task]` overrides the default good record. */
function world(opts: { scores?: Record<string, Record<string, Outcome>>; fix?: "ok" | "none" | "tests-fail" | "still-bad" | "flaky" | "other-suite" | "missing" | "fewer-tests"; lockHeld?: boolean; throwOnEvaluate?: boolean; state?: LoopState; moveHeadBeforeMerge?: boolean } = {}) {
	let suite = "S1";
	let head = "c1";
	let clock = 0;
	let state: LoopState = opts.state ?? emptyState();
	let locked = Boolean(opts.lockHeld);
	const calls = { evaluate: [] as string[], fix: 0, tests: 0, publish: [] as Array<{ merge: boolean }>, rot: [] as string[], log: [] as string[] };
	const counts = new Map<string, number>();
	const score = (commit: string, group: string, task: string): EvalRecord => {
		const key = `${group}/${task}`;
		const n = (counts.get(`${commit}|${key}`) ?? 0) + 1;
		counts.set(`${commit}|${key}`, n);
		const outcome = opts.scores?.[commit]?.[key];
		return good(group, task, typeof outcome === "function" ? outcome(n) : outcome ?? {});
	};
	const deps: LoopDeps = {
		now: () => clock,
		lock: () => (locked ? undefined : ((locked = true), () => { locked = false; })),
		readState: () => structuredClone(state),
		writeState: (next) => { state = structuredClone(next); },
		suiteHash: () => suite,
		head: async () => {
			if (opts.moveHeadBeforeMerge && calls.tests > 0) head = "moved";
			return head;
		},
		async evaluate(commit, groups, tasks) {
			if (opts.throwOnEvaluate) throw new Error("eval infrastructure down");
			calls.evaluate.push(`${commit}:${groups.join(",")}:${(tasks ?? TASKS).join(",")}`);
			return groups.flatMap((group) => (tasks ?? TASKS).map((task) => score(commit, group, task)));
		},
		diffSince: async (from, to) => `diff ${from}..${to}`,
		async proposeFix({ base }) {
			calls.fix++;
			return opts.fix === "none" ? undefined : { branch: `fix-${base}`, commit: `${base}-fix` };
		},
		async runTests(commit) {
			calls.tests++;
			if (opts.fix === "tests-fail" && commit.endsWith("-fix")) return { ok: false, summary: "290 pass, 2 fail", total: 292 };
			if (opts.fix === "fewer-tests" && commit.endsWith("-fix")) return { ok: true, summary: "280 pass, 0 fail", total: 280 };
			return { ok: true, summary: "292 pass, 0 fail", total: 292 };
		},
		async publish(_fix, input) {
			calls.publish.push({ merge: input.merge });
			return { pr: "https://example/pr/1", merged: input.merge };
		},
		log: (line, o) => { calls.log.push(line); if (o?.rot) calls.rot.push(line); },
	};
	const original = deps.evaluate;
	let fixRuns = 0;
	deps.evaluate = async (commit, groups, tasks) => {
		if (!commit.endsWith("-fix")) return original(commit, groups, tasks);
		fixRuns++;
		calls.evaluate.push(`${commit}:${groups.join(",")}:${(tasks ?? TASKS).join(",")}`);
		const each = (over: Partial<EvalRecord>) => groups.flatMap((g) => (tasks ?? TASKS).map((t) => good(g, t, over)));
		if (opts.fix === "still-bad") return each({ harnessOk: false });
		if (opts.fix === "flaky") return each(fixRuns === 1 ? {} : { harnessOk: false });
		if (opts.fix === "other-suite") return each({ suiteHash: "EVIL" });
		if (opts.fix === "missing") return [];
		return each({});
	};
	return { deps, calls, setHead: (h: string) => { head = h; }, setSuite: (h: string) => { suite = h; }, advance: (ms: number) => { clock += ms; }, state: () => state };
}

describe("eval loop — decisions", () => {
	test("first tick runs the nightly groups and sets the bar", async () => {
		const w = world();
		expect((await tick(w.deps, CONFIG)).outcome).toBe("accepted");
		expect(w.calls.evaluate).toEqual(["c1:local,quad:01,02"]);
		expect(Object.keys(w.state().accepted).sort()).toEqual(["local/01", "local/02", "quad/01", "quad/02"]);
		expect(w.state().acceptedCommit).toBe("c1");
	});

	test("nothing new and nightly not due → idle, no paid run", async () => {
		const w = world();
		await tick(w.deps, CONFIG);
		w.advance(3600_000);
		expect((await tick(w.deps, CONFIG)).outcome).toBe("idle");
		expect(w.calls.evaluate).toHaveLength(1);
	});

	test("a new commit runs only the cheap groups; the nightly run brings back all groups", async () => {
		const w = world();
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		w.advance(3600_000);
		await tick(w.deps, CONFIG);
		expect(w.calls.evaluate.at(-1)).toBe("c2:local:01,02");
		w.advance(24 * 3600_000);
		await tick(w.deps, CONFIG);
		expect(w.calls.evaluate.at(-1)).toBe("c2:local,quad:01,02");
	});

	test("a failure that does not repeat on re-run is noise: no fix, bar kept", async () => {
		const w = world({ scores: { c2: { "local/01": (n) => (n === 1 ? { passRate: 0.5, hidden: { passed: 3, total: 6 } } : {}) } } });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		expect((await tick(w.deps, CONFIG)).outcome).toBe("noise-only");
		expect(w.calls.fix).toBe(0);
		expect(w.state().accepted["local/01"]!.passRate).toBe(1);
	});

	test("a confirmed regression is fixed, gated, and merged", async () => {
		const w = world({ scores: { c2: { "local/01": { harnessOk: false, executionFailure: "boom" } } }, fix: "ok" });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		const result = await tick(w.deps, CONFIG);
		expect(result.outcome).toBe("fixed-merged");
		expect(w.calls.fix).toBe(1);
		expect(w.calls.tests).toBe(2); // the fix, then its base (test-count floor)
		expect(w.calls.publish).toEqual([{ merge: true }]);
		expect(w.calls.evaluate).toContain("c2-fix:local:01");
		expect(w.state().accepted["local/01"]!.harnessOk).toBe(true);
	});

	test("a fix that fails the tests stays an open PR and is logged to ROT", async () => {
		const w = world({ scores: { c2: { "local/01": { harnessOk: false } } }, fix: "tests-fail" });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		expect((await tick(w.deps, CONFIG)).outcome).toBe("fix-pr-open");
		expect(w.calls.publish).toEqual([{ merge: false }]);
		expect(w.calls.rot.at(-1)).toContain("gate failed: tests");
	});

	test("a fix whose eval re-run still regresses is never merged", async () => {
		const w = world({ scores: { c2: { "local/01": { harnessOk: false } } }, fix: "still-bad" });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		expect((await tick(w.deps, CONFIG)).outcome).toBe("fix-pr-open");
		expect(w.calls.publish).toEqual([{ merge: false }]);
	});

	test("the same regression twice is 'stuck' — no second fix attempt (no-progress stop)", async () => {
		const bad = { "local/01": { harnessOk: false } };
		const w = world({ scores: { c2: bad, c3: bad }, fix: "tests-fail" });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		await tick(w.deps, CONFIG);
		w.setHead("c3");
		expect((await tick(w.deps, CONFIG)).outcome).toBe("stuck");
		expect(w.calls.fix).toBe(1);
		expect(w.calls.rot.at(-1)).toContain("needs a human");
	});

	test("a stuck regression reaches ROT once, then stays quiet on later ticks", async () => {
		const bad = { "local/01": { harnessOk: false } };
		const w = world({ scores: { c2: bad, c3: bad, c4: bad }, fix: "tests-fail" });
		await tick(w.deps, CONFIG);
		for (const head of ["c2", "c3", "c4"]) { w.setHead(head); await tick(w.deps, CONFIG); }
		expect(w.calls.rot.filter((line) => line.startsWith("stuck"))).toHaveLength(1);
	});

	test("no change from the fix run → fix-failed", async () => {
		const w = world({ scores: { c2: { "local/01": { harnessOk: false } } }, fix: "none" });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		expect((await tick(w.deps, CONFIG)).outcome).toBe("fix-failed");
		expect(w.calls.publish).toEqual([]);
	});

	test("autoMerge off: a passing gate opens a PR but never merges", async () => {
		const w = world({ scores: { c2: { "local/01": { harnessOk: false } } }, fix: "ok" });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		expect((await tick(w.deps, { ...CONFIG, autoMerge: false })).outcome).toBe("fix-pr-open");
		expect(w.calls.publish).toEqual([{ merge: false }]);
	});

	test("a held lock → busy, nothing runs", async () => {
		const w = world({ lockHeld: true });
		expect((await tick(w.deps, CONFIG)).outcome).toBe("busy");
		expect(w.calls.evaluate).toEqual([]);
	});

	test("an infrastructure error is recorded, clears in-flight, and releases the lock", async () => {
		const w = world({ throwOnEvaluate: true });
		expect((await tick(w.deps, CONFIG)).outcome).toBe("error");
		expect(w.state().inFlight).toBeUndefined();
		expect((await tick(w.deps, CONFIG)).outcome).toBe("error"); // not "busy": the lock was released
	});

	test("a tick that died mid-phase is recovered on the next tick", async () => {
		const state = { ...emptyState(), inFlight: { commit: "c0", phase: "fix", startedAt: 0 } };
		const w = world({ state });
		expect((await tick(w.deps, CONFIG)).outcome).toBe("accepted");
		expect(w.calls.log[0]).toContain('recovered: previous tick died during "fix"');
	});

	test("re-locking the loop's own sealed suite resets the bar; results never can", async () => {
		const w = world({ scores: { c2: { "local/01": { suiteHash: "S2" }, "local/02": { suiteHash: "S2" } } } });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		w.setSuite("S2"); // the loop's own lock.json changed
		expect((await tick(w.deps, CONFIG)).outcome).toBe("accepted");
		expect(w.state().suiteHash).toBe("S2");
	});

	test("an evaluation graded by a foreign suite is an error: it cannot reset the bar or the attempt memory", async () => {
		const w = world({ scores: { c2: { "local/01": { harnessOk: false } }, c3: { "local/01": { suiteHash: "FORGED" }, "local/02": { suiteHash: "FORGED" } } }, fix: "tests-fail" });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		await tick(w.deps, CONFIG);
		const attempted = [...w.state().attempted];
		w.setHead("c3");
		const result = await tick(w.deps, CONFIG);
		expect(result.outcome).toBe("error");
		expect(result.detail).toContain("different suite");
		expect(w.state().attempted).toEqual(attempted);
		expect(w.state().accepted["local/01"]!.suiteHash).toBe("S1");
	});


	// ── Enemy review regressions (each failed on f8d8b62) ──
	const regressAt = (commit: string) => ({ [commit]: { "local/01": { harnessOk: false } } });

	test("gate: re-run graded by a different suite is never merged and never becomes the bar", async () => {
		const w = world({ scores: regressAt("c2"), fix: "other-suite" });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		expect((await tick(w.deps, CONFIG)).outcome).toBe("fix-pr-open");
		expect(w.calls.publish).toEqual([{ merge: false }]);
		expect(w.state().accepted["local/01"]!.suiteHash).toBe("S1");
		expect(w.state().accepted["local/01"]!.harnessOk).toBe(true);
	});

	test("gate: a re-run that returns no result for the regressed task is never merged", async () => {
		const w = world({ scores: regressAt("c2"), fix: "missing" });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		expect((await tick(w.deps, CONFIG)).outcome).toBe("fix-pr-open");
		expect(w.calls.publish).toEqual([{ merge: false }]);
	});

	test("gate: one lucky re-run is not enough — both re-runs must meet the bar", async () => {
		const w = world({ scores: regressAt("c2"), fix: "flaky" });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		expect((await tick(w.deps, CONFIG)).outcome).toBe("fix-pr-open");
		expect(w.calls.publish).toEqual([{ merge: false }]);
	});

	test("gate: a fix with fewer tests than its base is never merged (no deleting failing tests)", async () => {
		const w = world({ scores: regressAt("c2"), fix: "fewer-tests" });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		const result = await tick(w.deps, CONFIG);
		expect(result.outcome).toBe("fix-pr-open");
		expect(result.detail).toContain("fewer tests");
	});

	test("gate: if the branch moved during the fix, nothing is merged", async () => {
		const w = world({ scores: regressAt("c2"), fix: "ok", moveHeadBeforeMerge: true });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		const result = await tick(w.deps, CONFIG);
		expect(result.outcome).toBe("fix-pr-open");
		expect(result.detail).toContain("branch moved");
		expect(w.calls.publish).toEqual([{ merge: false }]);
	});

	test("crash after evaluation (lastEvaluatedCommit set) re-runs instead of going idle, and the fix is still attempted", async () => {
		const w = world({ scores: regressAt("c2"), fix: "ok" });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		// Simulate: the previous tick evaluated c2 and died in "fix" before any attempt finished.
		const crashed = { ...w.state(), lastEvaluatedCommit: "c2", inFlight: { commit: "c2", phase: "fix", startedAt: 0 } };
		w.deps.writeState(crashed);
		const result = await tick(w.deps, CONFIG);
		expect(result.outcome).toBe("fixed-merged");
		expect(w.calls.fix).toBe(1);
	});

	test("a stuck task never rides along in a bigger regression set; only the new item is fixed", async () => {
		const w = world({ scores: { c2: { "local/01": { harnessOk: false } }, c3: { "local/01": { harnessOk: false }, "local/02": { harnessOk: false } } }, fix: "tests-fail" });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		await tick(w.deps, CONFIG); // local/01 attempted (tests fail)
		const fixesBefore = w.calls.fix;
		w.setHead("c3");
		await tick(w.deps, CONFIG);
		expect(w.calls.fix).toBe(fixesBefore + 1);
		expect(w.calls.log.some((line) => line.startsWith("stuck (not retried)") && line.includes("local/01"))).toBe(true);
		expect(w.state().attempted).toContain("local/02:harness-fail");
	});

	test("a regression that recovers and later recurs gets a fresh attempt and a fresh ROT report", async () => {
		const bad = { "local/01": { harnessOk: false } };
		const w = world({ scores: { c2: bad, c3: bad, c5: bad }, fix: "tests-fail" });
		await tick(w.deps, CONFIG);
		for (const head of ["c2", "c3"]) { w.setHead(head); await tick(w.deps, CONFIG); }
		expect(w.calls.fix).toBe(1);
		w.setHead("c4"); // healthy again…
		expect((await tick(w.deps, CONFIG)).outcome).toBe("accepted");
		w.setHead("c4b"); // …twice in a row: recovered
		expect((await tick(w.deps, CONFIG)).outcome).toBe("accepted");
		w.setHead("c5"); // recurs
		expect((await tick(w.deps, CONFIG)).outcome).toBe("fix-pr-open");
		expect(w.calls.fix).toBe(2);
	});

	test("the cost bar is anchored: accepted runs just under 1.5x do not ratchet it up", async () => {
		const scores: Record<string, Record<string, Outcome>> = {};
		let cost = 1;
		for (let i = 2; i <= 8; i++) { cost *= 1.4; scores[`c${i}`] = { "local/01": { costUsd: cost } }; }
		const w = world({ scores });
		await tick(w.deps, CONFIG);
		const outcomes: string[] = [];
		for (let i = 2; i <= 8; i++) { w.setHead(`c${i}`); outcomes.push((await tick(w.deps, CONFIG)).outcome); }
		expect(w.state().accepted["local/01"]!.costUsd).toBe(1);
		expect(outcomes.some((outcome) => outcome !== "accepted")).toBe(true);
	});

	test("a failure while publishing a failed gate is contained, and the lock is held until the tick really ends", async () => {
		const w = world({ scores: regressAt("c2"), fix: "tests-fail" });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		let releasedBeforePublishSettled = false;
		let publishing = false;
		const lock = w.deps.lock;
		w.deps.lock = () => { const release = lock(); return release && (() => { if (publishing) releasedBeforePublishSettled = true; release(); }); };
		w.deps.publish = async () => { publishing = true; await Promise.resolve(); publishing = false; throw new Error("gh pr create failed"); };
		const result = await tick(w.deps, CONFIG);
		expect(result.outcome).toBe("error");
		expect(result.detail).toContain("gh pr create failed");
		expect(releasedBeforePublishSettled).toBe(false);
	});

	// ── Enemy second-pass regressions ──
	test("a fix run that throws still counts as an attempt (no endless paid retries)", async () => {
		const bad = { "local/01": { harnessOk: false } };
		const w = world({ scores: { c2: bad, c3: bad, c4: bad } });
		w.deps.proposeFix = async () => { w.calls.fix++; throw new Error("fix run changed protected paths (evals/x)"); };
		await tick(w.deps, CONFIG);
		for (const head of ["c2", "c3", "c4"]) { w.setHead(head); await tick(w.deps, CONFIG); }
		expect(w.calls.fix).toBe(1);
		expect(w.state().attempted).toContain("local/01:harness-fail");
	});

	test("the bar is not raised from a fix that never merged", async () => {
		const w = world({ scores: { c2: { "local/01": { passRate: 0.5, hidden: { passed: 3, total: 6 } } } }, fix: "ok", moveHeadBeforeMerge: true });
		await tick(w.deps, CONFIG);
		const before = structuredClone(w.state().accepted["local/01"]);
		w.setHead("c2");
		expect((await tick(w.deps, CONFIG)).outcome).toBe("fix-pr-open");
		expect(w.state().accepted["local/01"]).toEqual(before);
	});

	test("one lucky clean run does not clear the attempt memory for a flaky task", async () => {
		const bad = { "local/01": { harnessOk: false } };
		const w = world({ scores: { c2: bad, c4: bad }, fix: "tests-fail" });
		await tick(w.deps, CONFIG);
		w.setHead("c2"); await tick(w.deps, CONFIG); // attempted
		w.setHead("c3"); await tick(w.deps, CONFIG); // one clean run
		w.setHead("c4");
		expect((await tick(w.deps, CONFIG)).outcome).toBe("stuck");
		expect(w.calls.fix).toBe(1);
	});

	test("a $0 first run does not switch the cost check off", async () => {
		const w = world({ scores: { c1: { "local/01": { costUsd: 0 } }, c2: { "local/01": { costUsd: 1 } }, c3: { "local/01": { costUsd: 40 } } } });
		await tick(w.deps, CONFIG);
		w.setHead("c2"); await tick(w.deps, CONFIG);
		expect(w.state().accepted["local/01"]!.costUsd).toBe(1);
		w.setHead("c3");
		expect((await tick(w.deps, CONFIG)).outcome).not.toBe("accepted");
	});

	test("a persisting error reaches ROT once, not every tick", async () => {
		const w = world({ throwOnEvaluate: true });
		for (let i = 0; i < 4; i++) { w.setHead(`e${i}`); await tick(w.deps, CONFIG); }
		expect(w.calls.rot.filter((line) => line.startsWith("error"))).toHaveLength(1);
	});

	// ── Enemy third-pass regressions ──
	test("a persisting error whose text carries paths/timestamps still reaches ROT once", async () => {
		const w = world();
		let n = 0;
		w.deps.evaluate = async () => { n++; throw new Error(`/tmp/eval-loop/wt/abc123def456-eval-${1790000000000 + n}: package.json differs`); };
		for (let i = 0; i < 5; i++) { w.setHead(`e${i}`); w.advance(3600_000); await tick(w.deps, CONFIG); }
		expect(w.calls.rot.filter((line) => line.startsWith("error"))).toHaveLength(1);
		w.advance(24 * 3600_000); // still failing a day later: one reminder
		w.setHead("e9");
		await tick(w.deps, CONFIG);
		expect(w.calls.rot.filter((line) => line.startsWith("error"))).toHaveLength(2);
		expect(errorShape("/a/b/c-17900: x 12")).toBe(errorShape("/d/e-18000: x 99"));
		// Enemy pass 4 R12: same failure, different words in the tail → still the same kind.
		expect(errorShape("eval run failed: model said foo at step 3")).toBe(errorShape("eval run failed: provider timeout, other words"));
		expect(errorShape("eval run failed: x")).not.toBe(errorShape("gh pr create failed: x"));
	});

	test("afterTick (cleanup, runner refresh) runs inside the lock, and never for a busy tick", async () => {
		const w = world();
		let heldDuringAfterTick: boolean | undefined;
		let locked = false;
		w.deps.lock = () => (locked ? undefined : ((locked = true), () => { locked = false; }));
		w.deps.afterTick = () => { heldDuringAfterTick = locked; };
		await tick(w.deps, CONFIG);
		expect(heldDuringAfterTick).toBe(true);
		heldDuringAfterTick = undefined;
		locked = true; // someone else holds it
		expect((await tick(w.deps, CONFIG)).outcome).toBe("busy");
		expect(heldDuringAfterTick).toBeUndefined();
	});

	test("more than one concurrent writer is a regression even with no bar yet", () => {
		expect(findRegressions([good("local", "01", { maxWriters: 2 })], {})[0]!.kind).toBe("writers");
	});

	test("meetsBar rejects a missing result, another suite, extra writers, and anything below the bar", () => {
		const bar = good("local", "01");
		expect(meetsBar(undefined, bar, "S1")).toBe("no result");
		expect(meetsBar(good("local", "01", { suiteHash: "EVIL" }), bar, "S1")).toContain("different suite");
		expect(meetsBar(good("local", "01", { maxWriters: 2 }), bar, "S1")).toContain("writers");
		expect(meetsBar(good("local", "01", { passRate: 0.9 }), bar, "S1")).toContain("hidden tests");
		expect(meetsBar(good("local", "01", { harnessOk: false }), bar, "S1")).toBe("harness run failed");
		expect(meetsBar(good("local", "01"), bar, "S1")).toBeUndefined();
	});

});
