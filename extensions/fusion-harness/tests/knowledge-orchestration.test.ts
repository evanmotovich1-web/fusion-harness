import { describe, expect, test } from "bun:test";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const root = join(import.meta.dir, "..");
const sourceFiles = [
	join(root, "fusion-harness.ts"),
	...readdirSync(join(root, "modules"))
		.filter((file) => file.endsWith(".ts"))
		.map((file) => join(root, "modules", file)),
];
const source = sourceFiles.map((file) => readFileSync(file, "utf8")).join("\n");
const readonly = readFileSync(join(root, "modules", "cmd-readonly.ts"), "utf8");
const fusion = readFileSync(join(root, "modules", "cmd-fusion.ts"), "utf8");
const build = readFileSync(join(root, "modules", "cmd-build.ts"), "utf8");
const lanes = readFileSync(join(root, "modules", "cmd-lanes.ts"), "utf8");
const factory = readFileSync(join(root, "fusion-harness.ts"), "utf8");
const runner = readFileSync(join(root, "modules", "child-runner.ts"), "utf8");
const ingest = readFileSync(join(root, "modules", "knowledge-ingest.ts"), "utf8");
const evidence = readFileSync(join(root, "prompts", "KNOWLEDGE_EVIDENCE.md"), "utf8");
const skill = readFileSync(join(root, "..", "..", ".pi", "skills", "knowledge-base", "SKILL.md"), "utf8");

describe("knowledge orchestration contracts", () => {
	test("every applicable first-turn path prepares one packet and injects it", () => {
		expect(readonly).toContain("const packet = await h.prepareKnowledge(prompt, ctx.cwd, artifactsDir)");
		expect(readonly).toContain("withKnowledge(opinionPrompt(slot, stack, prompt), packet)");
		expect(readonly).toContain("withKnowledge(debateOpeningPrompt(slot, stack, prompt, rounds), packet)");
		expect(fusion).toContain("const packet = await h.prepareKnowledge(prompt, ctx.cwd, artifactsDir)");
		expect(fusion).toContain("withKnowledge(workerPrompt(slot, stack, prompt), packet)");
		expect(fusion).toContain("withKnowledge(fuserPrompt(fusionInstruction, prompt, runs, fuser.model, stack.architect.thinking, artifactsDir), packet, { writeCapable: true })");
		expect(build).toContain("withKnowledge(collabProposePrompt(slot, stack, prompt), packet)");
		expect(build).toContain("withKnowledge(validatorPrompt(prompt, ctx.cwd, scriptPath), packet)");
		expect(build).toContain("withKnowledge(builderPrompt(prompt, script), packet, { writeCapable: true })");
		expect(lanes).toContain("withKnowledge(laneWorkerPrompt(slot, stack, prompt, lane, ctx.cwd), packet, { writeCapable: true })");
		expect(factory).toContain("withKnowledge(prompt, packet, { writeCapable: true })");
	});

	test("ACK-only and later debate/correction turns do not re-inject the packet", () => {
		expect(fusion).toContain("prompt: ackSpec.prompt");
		expect(fusion).not.toContain("withKnowledge(ackSpec");
		expect(readonly).toContain("debateClosingPrompt(slot, prompt, round, rounds, priorSnapshot)");
		expect(readonly).toContain("debateRebuttalPrompt(slot, prompt, round, rounds, priorSnapshot)");
		expect(readonly).not.toContain("withKnowledge(debateClosingPrompt");
		expect(readonly).not.toContain("withKnowledge(debateRebuttalPrompt");
		expect(build).toContain("correctionPrompt(round, maxV, lastGate!.code, lastGate!.output, triageBrief, gateUpdate)");
		expect(build).not.toContain("withKnowledge(correctionPrompt");
	});

	test("fan-out slots share one packet hash field in summaries", () => {
		expect(readonly).toContain("knowledgeHash: packet.hash");
		expect(fusion).toContain("knowledgeHash: packet.hash");
		expect(lanes).toContain("knowledgeHash: packet.hash");
		expect(build).toContain("knowledgeHash: packet.hash");
	});

	test("read-only workers keep READONLY_TOOLS; children stay clean-room; no MCP advertised as built-in", () => {
		expect(fusion).toContain("tools: READONLY_TOOLS");
		expect(readonly).toContain("tools: READONLY_TOOLS");
		expect(runner).toContain("--no-skills");
		expect(runner).toContain("--no-extensions");
		expect(runner).toContain("--no-context-files");
		expect(source).toContain("Pi has no built-in MCP");
		expect(source).not.toContain("registerMcp");
	});

	test("lane workers receive the canonical snapshot, not a per-lane re-retrieval", () => {
		expect(lanes).toContain("const packet = await h.prepareKnowledge(prompt, ctx.cwd, artifactsDir)");
		expect(lanes).not.toContain("prepareKnowledge(prompt, lane.path");
		expect(lanes).toContain("cwd: lane.path");
	});

	test("capture cannot target evidence lanes", () => {
		expect(ingest).toContain('"trading"');
		expect(ingest).toContain('"sessions"');
		expect(ingest).toContain("refused evidence lane");
		expect(ingest).toContain("wiki/agent-learnings.md");
	});

	test("fh-knowledge is registered and flags exist", () => {
		expect(source).toContain('registerCommand("fh-knowledge"');
		expect(factory).toContain('registerFlag("fh-knowledge"');
		expect(factory).toContain('registerFlag("fh-knowledge-capture"');
		expect(source).toContain("prepareKnowledge");
		expect(source).toContain("captureKnowledge");
	});

	test("evidence contract and host skill exist; skill says children do not load it", () => {
		expect(evidence).toContain("Cite path and line range");
		expect(evidence).toContain("not permanent model learning");
		expect(skill).toContain("Clean-room children do not load this skill");
		expect(skill).toContain("--no-skills");
	});
});
