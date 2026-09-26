import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { KNOWLEDGE_BEGIN, type KnowledgePacket } from "../modules/knowledge-base.ts";
import { withDistilledBrief, withKnowledge } from "../modules/prompt-library.ts";

const root = join(import.meta.dir, "..");
const command = readFileSync(join(root, "modules", "cmd-knowledge.ts"), "utf8");
const factory = readFileSync(join(root, "fusion-harness.ts"), "utf8");
const readonly = readFileSync(join(root, "modules", "cmd-readonly.ts"), "utf8");
const fusion = readFileSync(join(root, "modules", "cmd-fusion.ts"), "utf8");
const build = readFileSync(join(root, "modules", "cmd-build.ts"), "utf8");

function packet(over: Partial<KnowledgePacket> = {}): KnowledgePacket {
	return {
		query: "hook failures",
		hash: "abc123",
		status: "passed",
		enabled: true,
		captureEnabled: false,
		roots: [],
		hits: [
			{
				id: "h1",
				path: "wiki/hooks.md",
				absPath: "/tmp/wiki/hooks.md",
				startLine: 4,
				endLine: 8,
				heading: "Hook constraint",
				tags: ["hooks"],
				text: "A failing knowledge hook must not block the task. constraint",
				score: 3,
			},
		],
		skipped: [],
		errors: [],
		indexedFiles: 1,
		indexedChunks: 1,
		retrievedAt: "1970-01-01T00:00:00.000Z",
		reasons: [],
		promptBlock: "QUERY PACKET",
		packetMarkdown: "QUERY PACKET",
		...over,
	};
}

describe("/fh-knowledge brief", () => {
	test("the command is registered and builds a brief from the query", () => {
		expect(command).toContain('action === "brief"');
		expect(command).toContain("buildBrief(packet");
		expect(command).toContain("/fh-knowledge brief <query>");
	});

	test("prepareKnowledge prepends the brief and keeps the packet hash", () => {
		expect(factory).toContain("withDistilledBrief(retrieved)");
		const raw = packet();
		const prepared = withDistilledBrief(raw);
		expect(prepared.hash).toBe(raw.hash);
		expect(prepared.promptBlock.startsWith(KNOWLEDGE_BEGIN)).toBe(true);
		expect(prepared.promptBlock.indexOf("# KNOWLEDGE BRIEF")).toBeLessThan(prepared.promptBlock.indexOf("QUERY PACKET"));
		expect(prepared.promptBlock).toContain(KNOWLEDGE_BEGIN);
		const injected = withKnowledge("do the task", prepared);
		expect(injected.indexOf("# KNOWLEDGE BRIEF")).toBeLessThan(injected.indexOf("QUERY PACKET"));
		expect(injected.endsWith("do the task")).toBe(true);
	});

	test("an empty prompt block is not rewritten, so cleared and disabled packets stay identical", () => {
		const cleared = packet({ promptBlock: "", status: "disabled" });
		expect(withDistilledBrief(cleared)).toBe(cleared);
		expect(withKnowledge("execute", cleared)).toBe("execute");
	});

	test("later rounds, ACK turns, and correction prompts do not call withKnowledge", () => {
		expect(readonly).not.toContain("withKnowledge(debateClosingPrompt");
		expect(readonly).not.toContain("withKnowledge(debateRebuttalPrompt");
		expect(fusion).not.toContain("withKnowledge(ackSpec");
		expect(fusion).toContain("prompt: ackSpec.prompt");
		expect(build).not.toContain("withKnowledge(correctionPrompt");
		expect(build).toContain("knowledgeHash: packet.hash");
	});
});
