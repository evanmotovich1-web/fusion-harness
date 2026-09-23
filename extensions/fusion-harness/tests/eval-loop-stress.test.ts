/**
 * Stress test for the eval loop's decisions: thousands of seeded random ticks
 * against a simulated world with real regressions, model noise, good and bad
 * fixes, failing tests, hard crashes (process death: no catch, no finally, no
 * further writes) and concurrent ticks. Safety invariants are checked after
 * every tick.
 */
import { describe, expect, test } from "bun:test";
import { emptyState, findRegressions, recordKey, tick, type EvalRecord, type LoopConfig, type LoopDeps, type LoopState } from "../../../evals/fusion-eval/loop-core.ts";

class Crash extends Error {}

function rng(seed: number) {
	let a = seed >>> 0;
	return () => {
		a = (a + 0x6d2b79f5) >>> 0;
		let t = Math.imul(a ^ (a >>> 15), 1 | a);
		t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

const CONFIG: LoopConfig = { groups: ["local"], nightlyGroups: ["local", "quad"], nightlyEveryMs: 24 * 3600_000, autoMerge: true };
const TASKS = ["01", "02", "03"];

function simulate(seed: number, ticks: number) {
	const random = rng(seed);
	const chance = (p: number) => random() < p;
	let clock = 1;
	let nextCommit = 1;
	let head = `c${nextCommit++}`;
	const broken = new Map<string, Set<string>>([[head, new Set()]]); // ground truth: keys broken at a commit
	const fixes = new Map<string, { good: boolean; testsOk: boolean; base: string }>();
	let state: LoopState = emptyState();
	let lockHolder: symbol | undefined;
	let dead = false; // set when the "process" crashed during the current tick
	const observed = new Map<string, number>(); // `${commit}|${key}` → bad observations
	const fixAttemptsBySig = new Map<string, number>();
	const violations: string[] = [];
	const outcomes = new Map<string, number>();
	const stuckRot = new Map<string, number>(); // same stuck report must reach ROT at most once
	let active = 0;
	let maxActive = 0;

	const maybeCrash = () => { if (chance(0.02)) { dead = true; throw new Crash("process died"); } };
	const pause = async () => { for (let i = Math.floor(random() * 3); i > 0; i--) await Promise.resolve(); };

	const makeDeps = (): LoopDeps => {
		const me = Symbol("tick");
		return {
			now: () => clock,
			lock() {
				if (lockHolder) return undefined;
				lockHolder = me;
				active++;
				maxActive = Math.max(maxActive, active);
				return () => { if (!dead && lockHolder === me) { lockHolder = undefined; active--; } };
			},
			readState: () => structuredClone(state),
			writeState: (next) => { if (!dead) state = JSON.parse(JSON.stringify(next)); },
			async head() { await pause(); maybeCrash(); return head; },
			async evaluate(commit, groups, tasks) {
				await pause();
				maybeCrash();
				const out: EvalRecord[] = [];
				for (const group of groups) for (const task of tasks ?? TASKS) {
					const key = `${group}/${task}`;
					const bad = (broken.get(commit)?.has(key) ?? false) || chance(0.08);
					if (bad) observed.set(`${commit}|${key}`, (observed.get(`${commit}|${key}`) ?? 0) + 1);
					out.push({ group, task, suiteHash: "S", passRate: bad ? 0.5 : 1, harnessOk: !bad, maxWriters: 1, costUsd: 1, hidden: { passed: bad ? 3 : 6, total: 6 } });
				}
				return out;
			},
			diffSince: async () => "diff",
			async proposeFix({ base, regressions }) {
				await pause();
				maybeCrash();
				for (const r of regressions) {
					if ((observed.get(`${base}|${r.key}`) ?? 0) < 2) violations.push(`fix attempted for ${r.key}@${base} seen bad < 2 times (noise-triggered fix)`);
				}
				const sig = [...new Set(regressions.map((r) => `${r.key}:${r.kind}`))].sort().join("|");
				fixAttemptsBySig.set(sig, (fixAttemptsBySig.get(sig) ?? 0) + 1);
				if (fixAttemptsBySig.get(sig)! > 1) violations.push(`signature fixed twice: ${sig}`);
				if (!chance(0.85)) return undefined;
				const commit = `c${nextCommit++}`;
				const good = chance(0.6);
				const stillBroken = new Set(broken.get(base) ?? []);
				if (good) for (const r of regressions) stillBroken.delete(r.key);
				broken.set(commit, stillBroken);
				fixes.set(commit, { good, testsOk: chance(0.8), base });
				return { branch: `fix-${commit}`, commit };
			},
			async runTests(commit) { await pause(); maybeCrash(); const f = fixes.get(commit)!; return { ok: f.testsOk, summary: f.testsOk ? "ok" : "2 fail" }; },
			async publish(fix, input) {
				await pause();
				maybeCrash();
				const f = fixes.get(fix.commit)!;
				if (input.merge) {
					if (!f.testsOk) violations.push(`merged ${fix.commit} with failing tests`);
					if (!f.good) violations.push(`merged ${fix.commit}, a fix that does not repair the regression`);
					head = fix.commit;
				}
				return { pr: "pr", merged: input.merge };
			},
			log: (line, o) => {
				if (!o?.rot || !line.startsWith("stuck")) return;
				stuckRot.set(line.split(": ").slice(1).join(": "), (stuckRot.get(line.split(": ").slice(1).join(": ")) ?? 0) + 1);
			},
		};
	};

	const snapshotBar = () => Object.fromEntries(Object.entries(state.accepted).map(([k, r]) => [k, { passRate: r.passRate, ok: r.harnessOk }]));

	return (async () => {
		for (let i = 0; i < ticks; i++) {
			// The world moves: time passes, new commits land (sometimes breaking something real).
			clock += Math.floor(random() * 8 * 3600_000);
			if (chance(0.4)) {
				const parent = head;
				head = `c${nextCommit++}`;
				const next = new Set(broken.get(parent) ?? []);
				if (chance(0.25)) next.add(`${chance(0.5) ? "local" : "quad"}/${TASKS[Math.floor(random() * TASKS.length)]}`);
				broken.set(head, next);
			}
			const barBefore = snapshotBar();
			dead = false;
			const concurrent = i % 37 === 0;
			const runs = concurrent ? [tick(makeDeps(), CONFIG), tick(makeDeps(), CONFIG)] : [tick(makeDeps(), CONFIG)];
			const results = await Promise.all(runs.map((p) => p.catch((error) => {
				if (error instanceof Crash) return { outcome: "crash" as const, detail: "" };
				throw error;
			})));
			for (const r of results) outcomes.set(r.outcome, (outcomes.get(r.outcome) ?? 0) + 1);
			if (concurrent && results.filter((r) => r.outcome !== "busy").length > 1) violations.push("two concurrent ticks both ran");
			if (dead) {
				// The process died: its lock is reclaimed (dead pid), nothing else ran.
				if (lockHolder) { lockHolder = undefined; active--; }
			} else if (state.inFlight) violations.push(`inFlight left set after a clean tick (${state.inFlight.phase})`);
			JSON.parse(JSON.stringify(state)); // state must always be serializable
			if (new Set(state.attempted).size !== state.attempted.length) violations.push("duplicate attempted signatures");
			for (const [key, before] of Object.entries(barBefore)) {
				const after = state.accepted[key];
				if (!after) { violations.push(`bar for ${key} disappeared`); continue; }
				if (after.passRate < before.passRate || (before.ok && !after.harnessOk)) violations.push(`bar lowered for ${key}`);
			}
		}
		for (const [line, count] of stuckRot) if (count > 1) violations.push(`stuck reported to ROT ${count}x: ${line.slice(0, 80)}`);
		return { violations, outcomes, maxActive, state };
	})();
}

describe("eval loop — stress", () => {
	for (const seed of [1, 42, 1337, 2026]) {
		test(`seed ${seed}: 1500 random ticks keep every safety invariant`, async () => {
			const { violations, outcomes, maxActive, state } = await simulate(seed, 1500);
			expect(violations).toEqual([]);
			expect(maxActive).toBeLessThanOrEqual(1);
			// The run must actually exercise the interesting paths, not pass by idling.
			// "error" includes the injected hard crashes (the dead process can no longer write).
			for (const outcome of ["accepted", "noise-only", "fixed-merged", "fix-pr-open", "fix-failed", "stuck", "error", "busy", "idle"]) {
				expect(outcomes.get(outcome) ?? 0).toBeGreaterThan(0);
			}
			expect(findRegressions(Object.values(state.accepted), state.accepted)).toEqual([]);
			expect(Object.keys(state.accepted).every((key) => key === recordKey({ group: key.split("/")[0]!, task: key.split("/")[1]! }))).toBe(true);
		}, 60_000);
	}
});
