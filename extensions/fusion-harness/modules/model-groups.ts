/**
 * Saved model groups — every model combo the operator runs is kept, with the
 * reason for it, so it can be picked again later (/fh-groups, alt+m,
 * `fusion pick`, or the workflow-model-picker skill).
 *
 * Layout (FH_GROUPS_DIR overrides, for tests):
 *   ~/.pi/fusion-harness/groups/groups.json      index: name, reason, models, usage
 *   ~/.pi/fusion-harness/groups/<name>.yaml      a runnable model-stack YAML
 *
 * The YAML must stay a bare list of slots (loadModelStack rejects anything else),
 * so reasons live in the index, never in the YAML.
 */
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { parse as parseYaml, stringify as stringifyYaml } from "yaml";
import type { ModelSlot, ModelStack } from "./model-stack.ts";

export interface ModelGroup {
	name: string;
	reason: string;
	/** Absolute path of the group's model-stack YAML. */
	file: string;
	/** Order-independent identity of the combo: slot names, models, thinking, roles. */
	signature: string;
	/** "slot: provider/model (thinking)" in stack order, for display. */
	models: string[];
	/** Where the combo first came from (a stack file path, or "/fh-model"). */
	source?: string;
	createdAt: string;
	lastUsedAt: string;
	uses: number;
}

export function groupsDir(): string {
	if (process.env.FH_GROUPS_DIR) return process.env.FH_GROUPS_DIR;
	// Test runs must never write into the operator's real library.
	if (process.env.NODE_ENV === "test") return path.join(os.tmpdir(), `fh-groups-test-${process.pid}`);
	return path.join(os.homedir(), ".pi", "fusion-harness", "groups");
}

function indexPath(dir: string): string {
	return path.join(dir, "groups.json");
}

function ordered(stack: ModelStack): ModelSlot[] {
	return [...stack.slots];
}

export function stackSignature(stack: ModelStack): string {
	return ordered(stack)
		.map((slot) => `${slot.name}=${slot.model}:${slot.thinking}${slot.architect ? "@architect" : ""}${slot.primary ? "@primary" : ""}`)
		.sort()
		.join("|");
}

function describeSlots(stack: ModelStack): string[] {
	return ordered(stack).map((slot) => `${slot.name}${slot.architect ? " ◆" : slot.primary ? " ▲" : ""}: ${slot.model} (${slot.thinking})`);
}

export function loadGroups(dir = groupsDir()): ModelGroup[] {
	try {
		const parsed = JSON.parse(fs.readFileSync(indexPath(dir), "utf8"));
		return Array.isArray(parsed) ? parsed : [];
	} catch {
		return [];
	}
}

function writeGroups(dir: string, groups: ModelGroup[]): void {
	fs.mkdirSync(dir, { recursive: true });
	const tmp = `${indexPath(dir)}.${process.pid}.tmp`;
	fs.writeFileSync(tmp, `${JSON.stringify(groups, null, 2)}\n`);
	fs.renameSync(tmp, indexPath(dir));
}

function slug(text: string): string {
	return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48) || "group";
}

function uniqueName(base: string, taken: Set<string>): string {
	if (!taken.has(base)) return base;
	for (let n = 2; ; n++) if (!taken.has(`${base}-${n}`)) return `${base}-${n}`;
}

/** Relative prompt/skill paths in the source YAML must keep working from the groups dir. */
function absolutize(value: unknown, sourceDir: string): unknown {
	if (typeof value === "string") {
		const candidate = path.resolve(sourceDir, value);
		return !path.isAbsolute(value) && value.length < 1024 && fs.existsSync(candidate) ? candidate : value;
	}
	if (Array.isArray(value)) return value.map((item) => absolutize(item, sourceDir));
	return value;
}

/** The runnable YAML for a stack: the source file's slots (prompts, colors) patched to the live models. */
function stackYaml(stack: ModelStack): string {
	let sourceSlots: Array<Record<string, unknown>> = [];
	if (stack.configPath) {
		try {
			const parsed = parseYaml(fs.readFileSync(stack.configPath, "utf8"));
			if (Array.isArray(parsed)) sourceSlots = parsed as Array<Record<string, unknown>>;
		} catch { /* fall back to the live stack alone */ }
	}
	const sourceDir = stack.configPath ? path.dirname(stack.configPath) : process.cwd();
	const slots = ordered(stack).map((slot) => {
		const source = sourceSlots.find((entry) => entry && entry.name === slot.name) ?? {};
		const entry: Record<string, unknown> = { name: slot.name, model: slot.model, thinking: slot.thinking };
		if (slot.architect) entry.architect = true;
		if (slot.primary) entry.primary = true;
		if (source.color ?? slot.color) entry.color = source.color ?? slot.color;
		for (const key of ["system_prompt", "append_system_prompt", "skills"] as const) {
			if (source[key] !== undefined) entry[key] = absolutize(source[key], sourceDir);
		}
		return entry;
	});
	return `# fusion-harness saved model group — reason lives in groups.json\n${stringifyYaml(slots)}`;
}

/**
 * Save the combo (or refresh it if already saved). A non-empty reason replaces
 * the stored one; an existing group keeps its reason otherwise.
 */
export function saveGroup(
	stack: ModelStack,
	opts: { reason?: string; name?: string; source?: string; dir?: string } = {},
): { group: ModelGroup; created: boolean } {
	const dir = opts.dir ?? groupsDir();
	const groups = loadGroups(dir);
	const signature = stackSignature(stack);
	const now = new Date().toISOString();
	const reason = opts.reason?.trim();
	const existing = groups.find((group) => group.signature === signature);
	if (existing) {
		existing.lastUsedAt = now;
		existing.uses += 1;
		if (reason) existing.reason = reason;
		writeGroups(dir, groups);
		return { group: existing, created: false };
	}
	const name = uniqueName(slug(opts.name || stack.codename || "group"), new Set(groups.map((group) => group.name)));
	const file = path.join(dir, `${name}.yaml`);
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(file, stackYaml(stack));
	const group: ModelGroup = {
		name,
		reason: reason || `auto-saved from ${opts.source ?? stack.configPath ?? stack.codename}`,
		file,
		signature,
		models: describeSlots(stack),
		source: opts.source ?? stack.configPath,
		createdAt: now,
		lastUsedAt: now,
		uses: 1,
	};
	groups.push(group);
	writeGroups(dir, groups);
	return { group, created: true };
}

export function markGroupUsed(name: string, dir = groupsDir()): void {
	const groups = loadGroups(dir);
	const group = groups.find((candidate) => candidate.name === name);
	if (!group) return;
	group.lastUsedAt = new Date().toISOString();
	group.uses += 1;
	writeGroups(dir, groups);
}

export function setGroupReason(name: string, reason: string, dir = groupsDir()): boolean {
	const groups = loadGroups(dir);
	const group = groups.find((candidate) => candidate.name === name);
	if (!group || !reason.trim()) return false;
	group.reason = reason.trim();
	writeGroups(dir, groups);
	return true;
}

export function deleteGroup(name: string, dir = groupsDir()): boolean {
	const groups = loadGroups(dir);
	const group = groups.find((candidate) => candidate.name === name);
	if (!group) return false;
	try { fs.unlinkSync(group.file); } catch { /* already gone */ }
	writeGroups(dir, groups.filter((candidate) => candidate !== group));
	return true;
}

/** Most recently used first. */
export function sortedGroups(dir = groupsDir()): ModelGroup[] {
	// Ties (same millisecond) go to the later-saved entry.
	return loadGroups(dir)
		.map((group, index) => ({ group, index }))
		.sort((a, b) => b.group.lastUsedAt.localeCompare(a.group.lastUsedAt) || b.index - a.index)
		.map(({ group }) => group);
}

export function groupLabel(group: ModelGroup, current?: string): string {
	return `${group.signature === current ? "● " : "  "}${group.name} — ${group.reason} — ${group.models.map((model) => model.split(": ")[1]?.split(" ")[0] ?? model).join(", ")}`;
}
