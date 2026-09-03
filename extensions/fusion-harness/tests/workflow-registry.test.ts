import { afterEach, describe, expect, test } from "bun:test";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { discoverWorkflows, loadWorkflow, renderWorkflowPrompt, routeWorkflows, saveWorkflow } from "../modules/workflow-registry.ts";

const roots: string[] = [];
const temp = () => { const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fh-workflow-test-")); roots.push(dir); return dir; };
afterEach(() => { while (roots.length) fs.rmSync(roots.pop()!, { recursive: true, force: true }); });

const yaml = (id = "review") => `version: 1\nid: ${id}\nname: Code Review\ndescription: Review code for bugs and missing tests.\ntriggers: [code review, audit]\ncommand: fh-opinion\nprompt_template: |\n  Review this task: {{TASK}}\nconfirm: false\n`;

describe("workflow registry", () => {
	test("loads strict YAML and renders task placeholders", () => {
		const dir = temp();
		const file = path.join(dir, "review.yaml");
		fs.writeFileSync(file, yaml());
		const workflow = loadWorkflow(file);
		expect(workflow.id).toBe("review");
		expect(renderWorkflowPrompt(workflow, "unused exports")).toBe("Review this task: unused exports");
	});

	test("rejects unknown fields and fusion without an instruction", () => {
		const dir = temp();
		const unknown = path.join(dir, "unknown.yaml");
		fs.writeFileSync(unknown, `${yaml()}shell: rm -rf .\n`);
		expect(() => loadWorkflow(unknown)).toThrow("unknown key");
		const fusion = path.join(dir, "fusion.yaml");
		fs.writeFileSync(fusion, yaml("fusion").replace("fh-opinion", "fh-fusion"));
		expect(() => loadWorkflow(fusion)).toThrow("fusion_instruction is required");
	});

	test("rejects duplicate ids across workflow roots", () => {
		const one = temp(); const two = temp();
		fs.writeFileSync(path.join(one, "one.yaml"), yaml());
		fs.writeFileSync(path.join(two, "two.yaml"), yaml());
		expect(() => discoverWorkflows([one, two])).toThrow("duplicate workflow id review");
	});

	test("routes confident id and trigger matches, but not unrelated text", () => {
		const dir = temp();
		fs.writeFileSync(path.join(dir, "review.yaml"), yaml());
		fs.writeFileSync(path.join(dir, "browser.yaml"), yaml("browser").replace("Code Review", "Browser Use").replace("[code review, audit]", "[computer use, browser automation]"));
		const workflows = discoverWorkflows([dir]);
		const byId = routeWorkflows(workflows, "review unused exports");
		expect(byId.automatic?.workflow.id).toBe("review");
		expect(byId.automatic?.arguments).toBe("unused exports");
		expect(routeWorkflows(workflows, "computer use on example.com").automatic?.workflow.id).toBe("browser");
		expect(routeWorkflows(workflows, "do the thing").automatic).toBeUndefined();
	});

	test("saves atomically and validates filename id", () => {
		const dir = temp();
		const saved = saveWorkflow(dir, "review", yaml());
		expect(saved.sourcePath).toBe(path.join(dir, "review.yaml"));
		expect(fs.existsSync(saved.sourcePath)).toBe(true);
		expect(() => saveWorkflow(dir, "other", yaml())).toThrow("does not match filename id");
	});
});
