import { describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { type KnowledgeChunk, fuseSemantic, rankSemanticHits, refreshKnowledgeCache, retrieveKnowledge } from "../modules/knowledge-base.ts";
import { resolveKnowledgeConfig } from "../modules/knowledge-config.ts";

const chunk = (id: string, absPath: string, startLine: number, endLine: number, score = 0): KnowledgeChunk => ({
	id, path: absPath, absPath, startLine, endLine, heading: id, tags: [], text: `text of ${id}`, score,
});

describe("semantic fusion", () => {
	test("a semantic hit lifts the overlapping loaded chunk and adds chunks lexical missed", () => {
		const vault = mkdtempSync(join(tmpdir(), "fh-sem-"));
		try {
			const a = chunk("a", join(vault, "wiki/a.md"), 1, 10);
			const b = chunk("b", join(vault, "wiki/b.md"), 1, 20);
			const c = chunk("c", join(vault, "wiki/c.md"), 5, 30);
			const lexical = [{ ...a, score: 40 }, { ...b, score: 10 }];
			const fused = fuseSemantic(lexical, [a, b, c], [
				{ path: "wiki/c.md", l0: 8, l1: 12, score: 0.81 },
				{ path: "wiki/b.md", l0: 2, l1: 4, score: 0.7 },
			], vault);
			expect(fused.map((x) => x.id)).toEqual(["b", "a", "c"]);
			expect(fused.find((x) => x.id === "c")!.score).toBe(81);
		} finally {
			rmSync(vault, { recursive: true, force: true });
		}
	});

	test("semantic hits outside the loaded chunk set never enter the packet", () => {
		const vault = mkdtempSync(join(tmpdir(), "fh-sem-"));
		try {
			const a = chunk("a", join(vault, "wiki/a.md"), 1, 10);
			const fused = fuseSemantic([{ ...a, score: 5 }], [a], [
				{ path: "sessions/private.md", l0: 1, l1: 5, score: 0.9 },
				{ path: "trading/day.md", l0: 1, l1: 5, score: 0.9 },
			], vault);
			expect(fused.map((x) => x.id)).toEqual(["a"]);
		} finally {
			rmSync(vault, { recursive: true, force: true });
		}
	});

	test("near-tied semantic scores produce the same order regardless of input order", () => {
		// The embedding backend can return 0.768 in one process and 0.767 in the next under
		// load. Rank feeds RRF and the selected order is hashed, so a 0.001 wobble must not
		// flip two near-tied hits. Same inputs, both input orders, same canonical output.
		const a = { path: "wiki/pi-agent-architecture.md", l0: 335, l1: 342, score: 0.768 };
		const b = { path: "wiki/agentic-os.md", l0: 13, l1: 23, score: 0.772 };
		const forward = rankSemanticHits([a, b]);
		const reverse = rankSemanticHits([b, a]);
		expect(forward.map((h) => h.path)).toEqual(["wiki/agentic-os.md", "wiki/pi-agent-architecture.md"]);
		expect(reverse).toEqual(forward);
		// A 0.001 wobble the other way quantizes to the same tie, so it cannot flip the order.
		const wobble = rankSemanticHits([{ ...a, score: 0.768 }, { ...b, score: 0.767 }]);
		expect(wobble.map((h) => h.path)).toEqual(["wiki/agentic-os.md", "wiki/pi-agent-architecture.md"]);
		// Malformed hits are dropped rather than ranked.
		expect(rankSemanticHits([{ path: 1 as unknown as string, l0: 1, l1: 1, score: 0.9 }])).toEqual([]);
	});

	test("fixture roots outside the indexed vault stay lexical-only and deterministic", () => {
		const dir = mkdtempSync(join(tmpdir(), "fh-sem-"));
		try {
			writeFileSync(join(dir, "note.md"), "# Recursive CTE\nreachable graph walk\n");
			refreshKnowledgeCache();
			const config = resolveKnowledgeConfig({ cwd: dir, flag: dir, env: {}, homedir: dir });
			const packet = retrieveKnowledge({ query: "recursive CTE", cwd: dir, config });
			expect(packet.reasons.some((r) => r.startsWith("semantic:"))).toBe(false);
			expect(packet.hits.length).toBe(1);
		} finally {
			rmSync(dir, { recursive: true, force: true });
		}
	});
});
