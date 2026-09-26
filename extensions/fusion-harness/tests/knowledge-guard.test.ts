import { describe, expect, test } from "bun:test";
import { safeKnowledge } from "../modules/knowledge-guard.ts";
import { packetHash, type KnowledgePacket } from "../modules/knowledge-base.ts";

function good(query: string): KnowledgePacket {
	return {
		query,
		hash: packetHash(query, []),
		status: "miss",
		enabled: true,
		captureEnabled: false,
		roots: [],
		hits: [],
		skipped: [],
		errors: [],
		indexedFiles: 0,
		indexedChunks: 0,
		retrievedAt: "1970-01-01T00:00:00.000Z",
		reasons: [],
		promptBlock: "kept",
		packetMarkdown: "kept",
	};
}

describe("knowledge guard", () => {
	test("a throwing retriever returns a spawnable empty brief and does not set exitCode", async () => {
		const before = process.exitCode;
		const packet = await safeKnowledge(() => {
			throw new Error("vault hook exploded");
		}, { query: "build the factory" });
		expect(process.exitCode).toBe(before);
		expect(packet.status).toBe("error");
		expect(packet.promptBlock).toBe("");
		expect(packet.errors[0]).toContain("vault hook exploded");
		expect(packet.hash).toBe(packetHash("build the factory", []));
	});

	test("a rejecting retriever returns the same empty brief", async () => {
		const packet = await safeKnowledge(async () => {
			throw new Error("async retrieve failed");
		});
		expect(packet.status).toBe("error");
		expect(packet.promptBlock).toBe("");
		expect(packet.reasons.join(" ")).toContain("async retrieve failed");
	});

	test("timeout returns an empty brief and the call still completes", async () => {
		let release: (packet: KnowledgePacket) => void = () => {};
		const hung = new Promise<KnowledgePacket>((resolve) => {
			release = resolve;
		});
		const packet = await safeKnowledge(() => hung, { query: "q", timeoutMs: 30 });
		expect(packet.status).toBe("error");
		expect(packet.promptBlock).toBe("");
		expect(packet.errors[0]).toContain("timed out");
		release(good("q"));
	});

	test("a successful retriever is returned unchanged", async () => {
		const packet = good("ok");
		await expect(safeKnowledge(() => packet, { query: "ok" })).resolves.toBe(packet);
	});
});
