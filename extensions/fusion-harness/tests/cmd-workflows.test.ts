import { afterEach, describe, expect, test } from "bun:test";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { registerWorkflowCommands } from "../modules/cmd-workflows.ts";

const roots: string[] = [];
afterEach(() => { while (roots.length) fs.rmSync(roots.pop()!, { recursive: true, force: true }); });
const make = (id: string, command = "fh-opinion", confirm = false) => {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fh-cmd-workflow-")); roots.push(dir);
	fs.writeFileSync(path.join(dir, `${id}.yaml`), `version: 1\nid: ${id}\nname: ${id}\ndescription: ${id} workflow\ntriggers: [${id}]\ncommand: ${command}\nprompt_template: "Task: {{TASK}}"\nconfirm: ${confirm}\n`);
	return dir;
};

function harness(directory: string) {
	const commands = new Map<string, any>();
	const calls: string[] = [];
	const pi = { registerCommand: (name: string, spec: any) => commands.set(name, spec) } as any;
	registerWorkflowCommands(pi, {
		handlers: { "fh-opinion": async (raw) => { calls.push(raw); } },
		researchX: async (raw) => { calls.push(`x:${raw}`); },
		applyStack: async (stack) => { calls.push(`stack:${stack}`); },
		workflowDirectories: () => [directory],
	});
	const notifications: string[] = [];
	const ctx = { cwd: directory, ui: { notify: (text: string) => notifications.push(text), select: async (_title: string, choices: string[]) => choices[0], confirm: async () => true, editor: async () => undefined } };
	return { commands, calls, ctx, notifications };
}

describe("workflow commands", () => {
	test("/find-workflow dispatches the matched handler directly with rendered arguments", async () => {
		const h = harness(make("review"));
		await h.commands.get("find-workflow").handler("review unused exports", h.ctx);
		expect(h.calls).toEqual(["Task: unused exports"]);
		expect(h.notifications.some((text) => text.includes("review → /fh-opinion"))).toBe(true);
	});

	test("ambiguous routing uses the selector and preserves the full task", async () => {
		const dir = make("review");
		fs.writeFileSync(path.join(dir, "audit.yaml"), `version: 1\nid: audit\nname: audit\ndescription: audit workflow\ntriggers: [audit]\ncommand: fh-opinion\nprompt_template: "Chosen: {{TASK}}"\nconfirm: false\n`);
		const h = harness(dir);
		await h.commands.get("find-workflow").handler("do the thing", h.ctx);
		expect(h.calls[0]).toBe("Chosen: do the thing");
	});

	test("write workflows require confirmation before dispatch", async () => {
		const dir = make("build", "fh-only", true);
		const h = harness(dir);
		h.ctx.ui.confirm = async () => false;
		await h.commands.get("find-workflow").handler("build feature", h.ctx);
		expect(h.calls).toEqual([]);
	});
});
