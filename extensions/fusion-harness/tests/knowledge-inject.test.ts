import { describe, expect, test } from "bun:test";
import { packetHash, type KnowledgePacket } from "../modules/knowledge-base.ts";
import { buildBrief } from "../modules/knowledge-brief.ts";
import {
	BRIEF_HASH_MARK,
	CLEAN_ROOM_FLAG,
	VAULT_SEMANTIC_MARKERS,
	createKnowledgeInjectHandler,
	type KnowledgeInjectDeps,
} from "../modules/knowledge-inject.ts";

function packet(query: string): KnowledgePacket {
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
		promptBlock: "",
		packetMarkdown: "",
	};
}

function deps(over: Partial<KnowledgeInjectDeps> = {}): KnowledgeInjectDeps & { calls: string[] } {
	const calls: string[] = [];
	return {
		calls,
		argv: ["pi", "--mode", "tui"],
		retrieve: async (query) => {
			calls.push(query);
			return packet(query);
		},
		...over,
	};
}

describe("knowledge inject", () => {
	test("slash commands and ACK-only turns are ignored", async () => {
		const slash = deps();
		const slashHandler = createKnowledgeInjectHandler(slash);
		await expect(slashHandler({ prompt: "/fh-fusion build the gate" })).resolves.toBeUndefined();
		await expect(slashHandler({ prompt: "  /fh-knowledge brief hooks" })).resolves.toBeUndefined();
		expect(slash.calls).toEqual([]);

		const ack = deps();
		const ackHandler = createKnowledgeInjectHandler(ack);
		await expect(ackHandler({ prompt: "ACK FUSION run-9" })).resolves.toBeUndefined();
		await expect(ackHandler({
			prompt: "CONTEXT SYNCHRONIZATION ONLY — DO NOT TAKE ACTION\nAcknowledge receipt only by replying exactly: ACK FUSION run-9",
		})).resolves.toBeUndefined();
		expect(ack.calls).toEqual([]);
	});

	test("clean-room --no-extensions argv never injects", async () => {
		const d = deps({ argv: ["pi", "--mode", "json", "-p", CLEAN_ROOM_FLAG] });
		const handler = createKnowledgeInjectHandler(d);
		await expect(handler({ prompt: "plain task for a child seat" })).resolves.toBeUndefined();
		expect(d.calls).toEqual([]);
	});

	test("injects once per task and a new task injects again", async () => {
		const d = deps();
		const handler = createKnowledgeInjectHandler(d);
		const first = await handler({ prompt: "distill the vault for this task", systemPrompt: "base" });
		const second = await handler({ prompt: "distill the vault for this task", systemPrompt: "base" });
		const other = await handler({ prompt: "a different plain task", systemPrompt: "base" });
		expect(first?.systemPrompt).toContain("KNOWLEDGE BRIEF");
		expect(first?.systemPrompt).toContain(BRIEF_HASH_MARK);
		expect(second).toBeUndefined();
		expect(other?.systemPrompt).toContain(BRIEF_HASH_MARK);
		expect(d.calls).toEqual(["distill the vault for this task", "a different plain task"]);
	});

	test("hash dedupe skips when this brief or a vault-semantic session is already on the turn", async () => {
		const query = "dedupe this turn";
		const brief = buildBrief(packet(query), { query });
		const marked = deps();
		const markedHandler = createKnowledgeInjectHandler(marked);
		await expect(markedHandler({
			prompt: query,
			systemPrompt: `already injected\n${BRIEF_HASH_MARK} ${brief.briefHash}\n`,
		})).resolves.toBeUndefined();
		expect(marked.calls).toEqual([]);

		const semantic = deps();
		const semanticHandler = createKnowledgeInjectHandler(semantic);
		await expect(semanticHandler({
			prompt: query,
			systemPrompt: `host\n${VAULT_SEMANTIC_MARKERS[0]} (score 0.7)`,
		})).resolves.toBeUndefined();
		expect(semantic.calls).toEqual([]);
	});

	test("a throwing brief does not abort the turn", async () => {
		const before = process.exitCode;
		const d = deps({
			build: () => {
				throw new Error("brief exploded");
			},
		});
		const handler = createKnowledgeInjectHandler(d);
		await expect(handler({ prompt: "plain task that blows up" })).resolves.toBeUndefined();
		expect(process.exitCode).toBe(before);

		const retrieveBoom = deps({
			retrieve: async () => {
				throw new Error("retrieve exploded");
			},
		});
		const retrieveHandler = createKnowledgeInjectHandler(retrieveBoom);
		await expect(retrieveHandler({ prompt: "plain task retrieve fail" })).resolves.toBeUndefined();
		expect(process.exitCode).toBe(before);
	});
});
