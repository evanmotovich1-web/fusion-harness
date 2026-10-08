import { describe, expect, test } from "bun:test";
import { pressureWarning, resourceSample } from "../../../evals/fusion-eval/loop.ts";

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

describe("pressureWarning", () => {
	const swap = (used: number) => `total = 1000.00M  used = ${used}.00M  free = 1.00M  (encrypted)`;
	test("quiet when swap and process sizes are normal", () => {
		expect(pressureWarning({ swap: swap(500), top: [{ rssMb: 2000, proc: "node" }] })).toBeUndefined();
	});
	test("warns on full swap", () => {
		expect(pressureWarning({ swap: swap(900), top: [] })).toContain("swap 90% used");
	});
	test("warns on an 8 GB process", () => {
		expect(pressureWarning({ swap: swap(100), top: [{ rssMb: 18000, proc: "fseventsd" }] })).toContain("fseventsd holds 17.6 GB");
	});
});
