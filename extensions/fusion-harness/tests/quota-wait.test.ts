import { describe, expect, test } from "bun:test";
import { isQuotaError, quotaResetAt, quotaWaitMs, sleepUnlessStopped } from "../modules/quota-wait.ts";

// Verbatim from run fusion-harness-UcSRTF task 3.d (z.ai 5-hour usage cap).
const ZAI = '429: {"code":"1308","message":"已达到 5 小时的使用上限。您的限额将在 2026-09-23 11:28:51 重置。"}';

describe("provider quota handling", () => {
	test("recognizes quota and rate-limit errors, not ordinary failures", () => {
		expect(isQuotaError(ZAI)).toBe(true);
		expect(isQuotaError("Rate limit exceeded")).toBe(true);
		expect(isQuotaError("too many requests")).toBe(true);
		expect(isQuotaError("timed out")).toBe(false);
		expect(isQuotaError("child process failed (exit 1)")).toBe(false);
	});

	test("reads a zone-less CJK reset stamp as China time", () => {
		expect(quotaResetAt(ZAI)).toBe(Date.parse("2026-09-23T11:28:51+08:00") + 30_000);
	});

	test("reads relative retry-after hints", () => {
		const now = 1_000_000;
		expect(quotaResetAt("429 retry after 20 seconds", now)).toBe(now + 20_000);
		expect(quotaResetAt('{"retry_after": 2}', now)).toBe(now + 2_000);
		expect(quotaResetAt("retry-after: 3m", now)).toBe(now + 180_000);
	});

	test("one wait step is bounded so a wrong reset time is re-checked", () => {
		const now = Date.parse("2026-09-22T12:00:00Z");
		expect(quotaWaitMs(ZAI, now)).toBe(15 * 60_000);
		expect(quotaWaitMs("429", now)).toBe(60_000);
		expect(quotaWaitMs("retry after 0 seconds", now)).toBe(0);
	});

	test("a stop signal ends the sleep early", async () => {
		const stop = new AbortController();
		const started = Date.now();
		setTimeout(() => stop.abort(), 20);
		await sleepUnlessStopped(60_000, stop.signal);
		expect(Date.now() - started).toBeLessThan(5_000);
	});
});
