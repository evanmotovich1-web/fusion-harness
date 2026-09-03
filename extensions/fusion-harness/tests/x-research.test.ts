import { describe, expect, test } from "bun:test";
import { buildXResearchRequest, extractXResearchResponse, normalizeXResearchOptions, researchX } from "../modules/x-research.ts";

describe("Grok X research", () => {
	test("builds a bounded x_search request", () => {
		const request = buildXResearchRequest({ query: "release reactions", fromDate: "2026-08-01", toDate: "2026-08-20", allowedHandles: ["@xai"] }) as any;
		expect(request.model).toBe("grok-4.6");
		expect(request.tools[0]).toMatchObject({ type: "x_search", from_date: "2026-08-01", to_date: "2026-08-20", allowed_x_handles: ["xai"] });
	});

	test("rejects bad dates, ranges, and handles", () => {
		expect(() => normalizeXResearchOptions({ query: "x", fromDate: "08/01/2026" })).toThrow("YYYY-MM-DD");
		expect(() => normalizeXResearchOptions({ query: "x", fromDate: "2026-09-01", toDate: "2026-08-01" })).toThrow("after");
		expect(() => normalizeXResearchOptions({ query: "x", allowedHandles: ["not valid!"] })).toThrow("invalid X handle");
	});

	test("extracts output text and citation URLs", () => {
		const result = extractXResearchResponse({ output: [{ content: [{ type: "output_text", text: "Finding", annotations: [{ type: "url_citation", url: "https://x.com/xai/status/1" }] }] }] });
		expect(result.text).toBe("Finding");
		expect(result.urls).toEqual(["https://x.com/xai/status/1"]);
	});

	test("uses authentication and reports non-2xx errors", async () => {
		let authorization = "";
		const okFetch = (async (_url: string | URL | Request, init?: RequestInit) => {
			authorization = new Headers(init?.headers).get("authorization") ?? "";
			return new Response(JSON.stringify({ output_text: "Answer" }), { status: 200 });
		}) as typeof fetch;
		const result = await researchX({ query: "topic" }, { apiKey: "secret", fetchImpl: okFetch });
		expect(result.text).toBe("Answer");
		expect(authorization).toBe("Bearer secret");
		const badFetch = (async () => new Response(JSON.stringify({ error: { message: "denied" } }), { status: 403 })) as typeof fetch;
		expect(researchX({ query: "topic" }, { apiKey: "secret", fetchImpl: badFetch })).rejects.toThrow("denied");
	});

	test("fails clearly without an API key", async () => {
		expect(researchX({ query: "topic" }, { apiKey: "" })).rejects.toThrow("XAI_API_KEY");
	});
});
