import { describe, expect, test } from "bun:test";
import { KNOWLEDGE_BEGIN, KNOWLEDGE_END, type KnowledgeChunk, type KnowledgePacket } from "../modules/knowledge-base.ts";
import { BRIEF_MISS, buildBrief, briefPathAllowed } from "../modules/knowledge-brief.ts";

let seq = 0;

function chunk(partial: Partial<KnowledgeChunk> & { path: string; text: string }): KnowledgeChunk {
	seq += 1;
	const path = partial.path;
	return {
		id: partial.id ?? `${path}:1-4`,
		path,
		absPath: partial.absPath ?? `/vault/${path}`,
		startLine: partial.startLine ?? 1,
		endLine: partial.endLine ?? 4,
		heading: partial.heading ?? "(top)",
		tags: partial.tags ?? [],
		text: partial.text,
		score: partial.score ?? 10,
	};
}

function packet(hits: KnowledgeChunk[], over: Partial<KnowledgePacket> = {}): KnowledgePacket {
	return {
		query: over.query ?? "wire the knowledge brief",
		hash: over.hash ?? "packet-hash-abc",
		status: over.status ?? (hits.length ? "passed" : "miss"),
		enabled: over.enabled ?? true,
		captureEnabled: over.captureEnabled ?? false,
		roots: over.roots ?? ["/vault/wiki", "/vault/me"],
		vaultRoot: over.vaultRoot ?? "/vault",
		hits,
		skipped: over.skipped ?? [],
		errors: over.errors ?? [],
		indexedFiles: over.indexedFiles ?? hits.length,
		indexedChunks: over.indexedChunks ?? hits.length,
		retrievedAt: over.retrievedAt ?? "2026-09-26T00:00:00.000Z",
		reasons: over.reasons ?? [],
		promptBlock: over.promptBlock ?? "",
		packetMarkdown: over.packetMarkdown ?? "",
	};
}

const decision = chunk({
	path: "wiki/agentic-os-decisions.md",
	heading: "Decisions",
	tags: ["decisions"],
	text: "Decisions\n\nThe harness approved a single writer lease for all write tasks. n=12 confidence=high",
	score: 40,
});
const constraint = chunk({
	path: "wiki/factory-governance.md",
	heading: "Lane rules",
	tags: ["governance"],
	text: "Lane rules\n\nEvery builder runs in its own lane and must not touch another lane. n=7 confidence=medium",
	score: 30,
});
const hook = chunk({
	path: "wiki/hook-failures.md",
	heading: "Fail-open",
	tags: ["hooks"],
	text: "Fail-open\n\nA hook failure must never block the run; the tool_call gate is the blocking path. n=4 confidence=low",
	score: 20,
});
const repeat = chunk({
	path: "wiki/retro-2026-09.md",
	heading: "Regression",
	tags: ["lessons"],
	text: "Regression\n\nThe retry failed twice after a duplicate extension registration. LOW-N",
	score: 10,
});

describe("knowledge-brief contract", () => {
	test("identical packets produce identical markdown and hash", () => {
		const p = packet([decision, constraint, hook, repeat]);
		const a = buildBrief(p);
		const b = buildBrief(p);
		expect(a.briefMarkdown).toBe(b.briefMarkdown);
		expect(a.briefHash).toBe(b.briefHash);
		expect(a.briefHash).toMatch(/^[0-9a-f]{64}$/);
		expect(a.bytes).toBe(Buffer.byteLength(a.briefMarkdown, "utf8"));
		expect(a.truncated).toBe(false);
	});

	test("fixed sections render and hits land in the right one", () => {
		const brief = buildBrief(packet([decision, constraint, hook, repeat]));
		expect(brief.sections.map((s) => s.id)).toEqual(["decisions", "constraints", "hooks", "do-not-repeat"]);
		expect(brief.sections.map((s) => s.title)).toEqual(["Current decisions", "Repo constraints", "Hook / failure rules", "Do not repeat"]);
		expect(brief.sections.find((s) => s.id === "decisions")!.items.map((i) => i.path)).toEqual(["wiki/agentic-os-decisions.md"]);
		expect(brief.sections.find((s) => s.id === "constraints")!.items.map((i) => i.path)).toEqual(["wiki/factory-governance.md"]);
		expect(brief.sections.find((s) => s.id === "hooks")!.items.map((i) => i.path)).toEqual(["wiki/hook-failures.md"]);
		expect(brief.sections.find((s) => s.id === "do-not-repeat")!.items.map((i) => i.path)).toEqual(["wiki/retro-2026-09.md"]);
		for (const s of brief.sections) for (const item of s.items) expect(item.citation).toBe(`${item.path}:${item.startLine}-${item.endLine}`);
	});

	test("citations, n and confidence are carried through", () => {
		const brief = buildBrief(packet([decision, hook, repeat]));
		expect(brief.briefMarkdown).toContain("(wiki/agentic-os-decisions.md:1-4)");
		expect(brief.briefMarkdown).toContain("n=12 · confidence=high");
		expect(brief.briefMarkdown).toContain("n=4 · confidence=low");
		expect(brief.briefMarkdown).toContain("n=low (<5)");
	});

	test("denied lanes, hidden paths and secret-like names never reach the brief", () => {
		const denied = [
			chunk({ path: "trading/day-2026-09-26.md", text: "Trading decisions" }),
			chunk({ path: "sessions/abc.md", text: "Session decision" }),
			chunk({ path: "agent-memory/mem.md", text: "Agent memory decision" }),
			chunk({ path: "wiki/.hidden.md", text: "Hidden decision" }),
			chunk({ path: "wiki/secrets/token.md", text: "Secret decision" }),
			chunk({ path: ".env", text: "env decision" }),
		];
		const brief = buildBrief(packet([...denied, decision]));
		expect(brief.briefMarkdown).toContain("wiki/agentic-os-decisions.md:1-4");
		for (const bad of ["trading/", "sessions/", "agent-memory/", "wiki/.hidden.md", "wiki/secrets/", ".env"]) {
			expect(brief.briefMarkdown.includes(bad)).toBe(false);
		}
		expect(briefPathAllowed("trading/x.md")).toBe(false);
		expect(briefPathAllowed("sessions/x.md")).toBe(false);
		expect(briefPathAllowed("agent-memory/x.md")).toBe(false);
		expect(briefPathAllowed("wiki/.hidden.md")).toBe(false);
		expect(briefPathAllowed("wiki/secrets/key.md")).toBe(false);
		expect(briefPathAllowed("wiki/ok.md")).toBe(true);
	});

	test("hard byte cap is enforced and the truncation flag is set", () => {
		const many = Array.from({ length: 24 }, (_, i) =>
			chunk({
				path: `wiki/topic-${i}.md`,
				heading: `Decision ${i}`,
				text: `Decision ${i}\n\n${"the harness approved a durable decision ".repeat(6)} n=${i} confidence=medium`,
				score: 24 - i,
			}),
		);
		for (const maxBytes of [900, 2000, 4000]) {
			const brief = buildBrief(packet(many), { maxBytes });
			expect(brief.bytes).toBeLessThanOrEqual(maxBytes);
			expect(Buffer.byteLength(brief.briefMarkdown, "utf8")).toBeLessThanOrEqual(maxBytes);
			expect(brief.briefHash).toMatch(/^[0-9a-f]{64}$/);
			expect(brief.truncated).toBe(true);
			expect(brief.briefMarkdown.length).toBeGreaterThan(0);
		}
	});

	test("empty packet yields an explicit wiki miss", () => {
		const brief = buildBrief(packet([], { status: "miss" }));
		expect(brief.briefMarkdown).toContain(BRIEF_MISS);
		expect(brief.sections.every((s) => s.items.length === 0)).toBe(true);
		expect(brief.briefHash).toMatch(/^[0-9a-f]{64}$/);
	});

	test("brief stays inside the untrusted-evidence delimiters", () => {
		const brief = buildBrief(packet([decision]));
		expect(brief.briefMarkdown.startsWith(KNOWLEDGE_BEGIN)).toBe(true);
		expect(brief.briefMarkdown.trimEnd().endsWith(KNOWLEDGE_END)).toBe(true);
		const bare = buildBrief(packet([decision]), { wrapInMarkers: false });
		expect(bare.briefMarkdown.includes(KNOWLEDGE_BEGIN)).toBe(false);
		expect(bare.briefMarkdown.includes(KNOWLEDGE_END)).toBe(false);
	});
});
