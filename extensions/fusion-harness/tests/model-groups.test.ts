import { afterEach, describe, expect, test } from "bun:test";
import { mkdtempSync, readFileSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { cloneStack, loadModelStack } from "../modules/model-stack.ts";
import { deleteGroup, groupsDir, loadGroups, saveGroup, setGroupReason, sortedGroups } from "../modules/model-groups.ts";

const dirs: string[] = [];
afterEach(() => { while (dirs.length) rmSync(dirs.pop()!, { recursive: true, force: true }); });

function fixture() {
	const root = mkdtempSync(join(tmpdir(), "fh-groups-")); dirs.push(root);
	writeFileSync(join(root, "comms.md"), "be concise\n");
	const file = join(root, "model-stack-duo.yaml");
	writeFileSync(file, [
		"- name: arch", "  model: a/one", "  thinking: high", "  architect: true",
		"- name: main", "  model: b/two", "  thinking: medium", "  primary: true", '  color: "#34D399"',
		"  append_system_prompt:", "    - ./comms.md", "",
	].join("\n"));
	return { dir: join(root, "groups"), stack: loadModelStack(file) };
}

describe("saved model groups", () => {
	test("tests never touch the real ~/.pi library", () => {
		expect(groupsDir()).not.toContain(".pi");
	});

	test("saves a runnable copy that keeps prompt files working", () => {
		const { dir, stack } = fixture();
		const { group, created } = saveGroup(stack, { dir, reason: "cheap overnight research" });
		expect(created).toBe(true);
		expect(group.reason).toBe("cheap overnight research");
		expect(group.models).toEqual(["arch ◆: a/one (high)", "main ▲: b/two (medium)"]);
		const reloaded = loadModelStack(group.file);
		expect(reloaded.slots.map((slot) => slot.model)).toEqual(["a/one", "b/two"]);
		expect(reloaded.primaryBuilder.appendSystemPrompts[0]).toContain("be concise");
		expect(reloaded.primaryBuilder.color).toBe("#34D399");
	});

	test("the same combo is one group: reuse bumps usage, a new reason replaces the old", () => {
		const { dir, stack } = fixture();
		saveGroup(stack, { dir, reason: "first" });
		const again = saveGroup(cloneStack(stack), { dir });
		expect(again.created).toBe(false);
		expect(again.group.uses).toBe(2);
		expect(again.group.reason).toBe("first");
		saveGroup(stack, { dir, reason: "second" });
		expect(loadGroups(dir)).toHaveLength(1);
		expect(loadGroups(dir)[0]!.reason).toBe("second");
	});

	test("a changed model is a new group with a unique name", () => {
		const { dir, stack } = fixture();
		saveGroup(stack, { dir });
		const changed = cloneStack(stack);
		changed.slots[1]!.model = "c/three";
		const second = saveGroup(changed, { dir });
		expect(second.created).toBe(true);
		expect(second.group.name).toBe("duo-2");
		expect(sortedGroups(dir)[0]!.name).toBe("duo-2");
	});

	test("reasons can be edited and groups deleted", () => {
		const { dir, stack } = fixture();
		const { group } = saveGroup(stack, { dir });
		expect(group.reason).toContain("auto-saved from");
		expect(setGroupReason(group.name, "GLM out of quota", dir)).toBe(true);
		expect(loadGroups(dir)[0]!.reason).toBe("GLM out of quota");
		expect(deleteGroup(group.name, dir)).toBe(true);
		expect(loadGroups(dir)).toHaveLength(0);
		expect(existsSync(group.file)).toBe(false);
	});

	test("the index is plain JSON other tools (fusion pick, the skill) can read", () => {
		const { dir, stack } = fixture();
		saveGroup(stack, { dir, reason: "why" });
		const raw = JSON.parse(readFileSync(join(dir, "groups.json"), "utf8"));
		expect(Object.keys(raw[0]).sort()).toEqual(["createdAt", "file", "lastUsedAt", "models", "name", "reason", "signature", "source", "uses"]);
	});
});
