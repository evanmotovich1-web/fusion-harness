import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const root = join(import.meta.dir, "..");
const factory = readFileSync(join(root, "fusion-harness.ts"), "utf8");
const runner = readFileSync(join(root, "modules", "child-runner.ts"), "utf8");

describe("interactive knowledge injection wiring", () => {
	test("the host registers the inject handler exactly once", () => {
		const registrations = factory.match(/pi\.on\("before_agent_start"/g) ?? [];
		expect(registrations).toHaveLength(1);
		expect(factory.match(/createKnowledgeInjectHandler\(/g)).toHaveLength(1);
		expect(factory).toContain("retrieve: (query, cwd) => retrieveKnowledge({ query, cwd, config: knowledgeConfig(cwd) })");
	});

	test("clean-room children still spawn without extensions, skills, or context files", () => {
		const args = runner.slice(runner.indexOf("const args: string[]"));
		const noSkills = args.indexOf('"--no-skills"');
		const noExtensions = args.indexOf('"--no-extensions"');
		const noContext = args.indexOf('"--no-context-files"');
		expect(noSkills).toBeGreaterThan(-1);
		expect(noExtensions).toBeGreaterThan(noSkills);
		expect(noContext).toBeGreaterThan(noExtensions);
		expect(runner).not.toContain("createKnowledgeInjectHandler");
		expect(runner).not.toContain("before_agent_start");
	});
});
