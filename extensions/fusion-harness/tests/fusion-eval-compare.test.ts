import { describe, expect, test } from "bun:test";
import { compare } from "../../../evals/fusion-eval/run.ts";

const rec = (over: Record<string, unknown>) => ({ suiteHash: "s", task: "01", passRate: 1, hidden: { passed: 6, total: 6 }, costUsd: 1, wallMs: 60_000, harnessOk: true, maxWriters: 1, executionFailure: null, ...over });

describe("fusion eval regression rules", () => {
	test("equal runs are not regressions", () => {
		expect(compare(new Map([["quad/01", rec({})]]), new Map([["quad/01", rec({})]])).regressions).toEqual([]);
	});
	test("lower hidden pass rate, a newly failing harness, 1.5x cost, or >1 writer are regressions", () => {
		const { regressions } = compare(
			new Map([["quad/01", rec({})]]),
			new Map([["quad/01", rec({ passRate: 0.5, hidden: { passed: 3, total: 6 }, harnessOk: false, costUsd: 3, maxWriters: 2 })]]),
		);
		expect(regressions).toHaveLength(4);
	});
	test("different sealed suites are never compared", () => {
		const { regressions } = compare(new Map([["quad/01", rec({ suiteHash: "a" })]]), new Map([["quad/01", rec({ suiteHash: "b" })]]));
		expect(regressions[0]).toContain("not comparable");
	});
});
