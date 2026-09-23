import { describe, expect, test } from "bun:test";
import { emptyState, findRegressions, signature, tick, type EvalRecord, type LoopConfig, type LoopDeps, type LoopState } from "../../../evals/fusion-eval/loop-core.ts";

const CONFIG: LoopConfig = { groups: ["local"], nightlyGroups: ["local", "quad"], nightlyEveryMs: 24 * 3600_000, autoMerge: true };
const TASKS = ["01", "02"];
const good = (group: string, task: string, over: Partial<EvalRecord> = {}): EvalRecord => ({ group, task, suiteHash: "S1", passRate: 1, harnessOk: true, maxWriters: 1, costUsd: 1, hidden: { passed: 6, total: 6 }, ...over });

type Outcome = Partial<EvalRecord> | ((call: number) => Partial<EvalRecord>);

/** Scriptable fake world. `scores[commit][group/task]` overrides the default good record. */
function world(opts: { scores?: Record<string, Record<string, Outcome>>; fix?: "ok" | "none" | "tests-fail" | "still-bad"; lockHeld?: boolean; throwOnEvaluate?: boolean; state?: LoopState } = {}) {
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
		head: async () => head,
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
		async runTests() {
			calls.tests++;
			return opts.fix === "tests-fail" ? { ok: false, summary: "290 pass, 2 fail" } : { ok: true, summary: "292 pass, 0 fail" };
		},
		async publish(_fix, input) {
			calls.publish.push({ merge: input.merge });
			return { pr: "https://example/pr/1", merged: input.merge };
		},
		log: (line, o) => { calls.log.push(line); if (o?.rot) calls.rot.push(line); },
	};
	if (opts.fix === "still-bad") {
		const original = deps.evaluate;
		deps.evaluate = async (commit, groups, tasks) => (commit.endsWith("-fix") ? groups.flatMap((g) => (tasks ?? TASKS).map((t) => good(g, t, { harnessOk: false }))) : original(commit, groups, tasks));
	}
	return { deps, calls, setHead: (h: string) => { head = h; }, advance: (ms: number) => { clock += ms; }, state: () => state };
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
		expect(w.calls.tests).toBe(1);
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
		expect(w.calls.rot.at(-1)).toContain("gate failed on tests");
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

	test("a changed suite resets the bar instead of comparing across suites", async () => {
		const w = world({ scores: { c2: { "local/01": { suiteHash: "S2", passRate: 0 }, "local/02": { suiteHash: "S2" } } } });
		await tick(w.deps, CONFIG);
		w.setHead("c2");
		expect((await tick(w.deps, CONFIG)).outcome).toBe("accepted");
		expect(w.state().suiteHash).toBe("S2");
	});

	test("more than one concurrent writer is a regression even with no bar yet", () => {
		expect(findRegressions([good("local", "01", { maxWriters: 2 })], {})[0]!.kind).toBe("writers");
	});

	test("signatures ignore order and duplicates", () => {
		const a = signature([{ key: "b/1", kind: "cost", detail: "" }, { key: "a/1", kind: "harness-fail", detail: "x" }]);
		const b = signature([{ key: "a/1", kind: "harness-fail", detail: "y" }, { key: "b/1", kind: "cost", detail: "z" }, { key: "b/1", kind: "cost", detail: "" }]);
		expect(a).toBe(b);
	});
});
