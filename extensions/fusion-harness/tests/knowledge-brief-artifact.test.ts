import { describe, expect, test } from "bun:test";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
	knowledgeArtifactBodies,
	knowledgeBriefCachePath,
	knowledgeCacheRoot,
	persistKnowledgeBrief,
	type KnowledgeChunk,
	type KnowledgePacket,
} from "../modules/knowledge-base.ts";
import { buildBrief } from "../modules/knowledge-brief.ts";

function chunk(partial: Partial<KnowledgeChunk> & { path: string; text: string }): KnowledgeChunk {
	return {
		id: partial.id ?? `${partial.path}:1-4`,
		path: partial.path,
		absPath: partial.absPath ?? `/vault/${partial.path}`,
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
		query: over.query ?? "wire the global knowledge brief",
		hash: over.hash ?? "packet-hash-2e",
		status: over.status ?? (hits.length ? "passed" : "miss"),
		enabled: over.enabled ?? true,
		captureEnabled: over.captureEnabled ?? false,
		roots: over.roots ?? ["/vault/wiki"],
		vaultRoot: over.vaultRoot ?? "/vault",
		hits,
		skipped: over.skipped ?? [],
		errors: over.errors ?? [],
		indexedFiles: over.indexedFiles ?? hits.length,
		indexedChunks: over.indexedChunks ?? hits.length,
		retrievedAt: over.retrievedAt ?? "2026-09-26T00:00:00.000Z",
		reasons: over.reasons ?? [],
		promptBlock: over.promptBlock ?? "PROMPT BLOCK",
		packetMarkdown: over.packetMarkdown ?? "PACKET MARKDOWN",
	};
}

const hits = [
	chunk({
		path: "wiki/hook-failures.md",
		heading: "Fail-open",
		text: "Fail-open\n\nA hook failure must never block the run; the tool_call gate is the blocking path. n=4 confidence=low",
		score: 30,
	}),
	chunk({
		path: "wiki/factory-governance.md",
		heading: "Lane rules",
		text: "Lane rules\n\nEvery builder runs in its own lane and must not touch another lane. n=7 confidence=medium",
		score: 20,
	}),
];

describe("knowledge-brief artifact + cache path", () => {
	test("knowledgeArtifactBodies adds knowledge-brief.md and brief metadata without touching packet hash", () => {
		const p = packet(hits);
		const bodies = knowledgeArtifactBodies(p);
		expect(Object.keys(bodies)).toContain("knowledge-brief.md");
		expect(bodies["knowledge-brief.md"]).toContain("# KNOWLEDGE BRIEF");
		expect(bodies["knowledge-brief.md"]).toContain("## Hook / failure rules");
		expect(bodies["knowledge-brief.md"]).toContain("## Repo constraints");
		expect(bodies["knowledge-brief.md"]).toContain("wiki/hook-failures.md:1-4");
		expect(bodies["knowledge-brief.md"].endsWith("\n")).toBe(true);

		const expected = buildBrief(p);
		const meta = JSON.parse(bodies["knowledge.json"]);
		expect(meta.hash).toBe(p.hash);
		expect(meta.brief.hash).toBe(expected.briefHash);
		expect(meta.brief.bytes).toBe(expected.bytes);
		expect(meta.brief.sections.map((s: { id: string }) => s.id)).toEqual(["decisions", "constraints", "hooks", "do-not-repeat"]);

		// The packet artifacts are unchanged in content.
		expect(bodies["knowledge-packet.md"]).toBe("PACKET MARKDOWN\n");
		expect(JSON.parse(bodies["knowledge-query.json"]).hash).toBe(p.hash);
	});

	test("cache root and per-project brief path are stable and machine-local", () => {
		const home = mkdtempSync(join(tmpdir(), "fh-cache-home-"));
		const projectA = mkdtempSync(join(tmpdir(), "fh-cache-proj-a-"));
		const projectB = mkdtempSync(join(tmpdir(), "fh-cache-proj-b-"));
		try {
			const opts = { env: {}, homedir: home };
			expect(knowledgeCacheRoot(opts)).toBe(join(home, ".cache", "fusion-harness", "knowledge"));
			expect(knowledgeCacheRoot({ env: { XDG_CACHE_HOME: join(home, "xdg") }, homedir: home })).toBe(join(home, "xdg", "fusion-harness", "knowledge"));

			const first = knowledgeBriefCachePath(projectA, opts);
			expect(knowledgeBriefCachePath(projectA, opts)).toBe(first);
			expect(first.endsWith("knowledge-brief.md")).toBe(true);
			expect(first.startsWith(knowledgeCacheRoot(opts))).toBe(true);
			expect(knowledgeBriefCachePath(projectB, opts)).not.toBe(first);
			expect(first.includes("second-brain") || first.includes("/trading/") || first.includes("/sessions/")).toBe(false);
		} finally {
			rmSync(home, { recursive: true, force: true });
			rmSync(projectA, { recursive: true, force: true });
			rmSync(projectB, { recursive: true, force: true });
		}
	});

	test("persistKnowledgeBrief writes once, then reports unchanged", () => {
		const home = mkdtempSync(join(tmpdir(), "fh-cache-home-"));
		const project = mkdtempSync(join(tmpdir(), "fh-cache-proj-"));
		try {
			const opts = { env: {}, homedir: home };
			const brief = buildBrief(packet(hits));
			const first = persistKnowledgeBrief(project, brief, opts);
			expect(first.written).toBe(true);
			expect(existsSync(first.path)).toBe(true);
			expect(readFileSync(first.path, "utf8")).toBe(brief.briefMarkdown);
			expect(existsSync(join(first.path, "..", "knowledge-brief.json"))).toBe(true);

			const second = persistKnowledgeBrief(project, brief, opts);
			expect(second.written).toBe(false);
			expect(second.reason).toBe("unchanged");
			expect(second.path).toBe(first.path);
		} finally {
			rmSync(home, { recursive: true, force: true });
			rmSync(project, { recursive: true, force: true });
		}
	});

	test("persistKnowledgeBrief is fail-open on an unusable cache", () => {
		const tmp = mkdtempSync(join(tmpdir(), "fh-cache-block-"));
		try {
			const blocker = join(tmp, "blocker");
			writeFileSync(blocker, "not a directory");
			const brief = buildBrief(packet(hits));
			const result = persistKnowledgeBrief(tmp, brief, { env: { XDG_CACHE_HOME: join(blocker, "cache") } });
			expect(result.written).toBe(false);
			expect(typeof result.reason).toBe("string");
			expect(result.briefHash).toBe(brief.briefHash);
		} finally {
			rmSync(tmp, { recursive: true, force: true });
		}
	});
});
