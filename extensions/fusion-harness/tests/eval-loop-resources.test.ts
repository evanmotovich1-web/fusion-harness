import { describe, expect, test } from "bun:test";
import { resourceSample } from "../../../evals/fusion-eval/loop.ts";

describe("resourceSample", () => {
	test("records time, load and the biggest processes", () => {
		const s = resourceSample(new Date("2026-10-01T00:00:00Z")) as any;
		expect(s.at).toBe("2026-10-01T00:00:00.000Z");
		expect(s.load).toHaveLength(3);
		expect(typeof s.freeMb).toBe("number");
		expect(s.top.length).toBeGreaterThan(0);
		expect(s.top.length).toBeLessThanOrEqual(5);
		expect(s.top[0].rssMb).toBeGreaterThanOrEqual(s.top[s.top.length - 1].rssMb);
	});
});
