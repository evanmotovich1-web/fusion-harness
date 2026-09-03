import * as fs from "node:fs";
import * as path from "node:path";
import { parse as parseYaml, stringify as stringifyYaml } from "yaml";

export const WORKFLOW_COMMANDS = ["fh-opinion", "fh-debate", "fh-fusion", "fh-collaborate", "fh-lanes", "fh-auto-validate", "fh-only", "research-x"] as const;
export type WorkflowCommand = typeof WORKFLOW_COMMANDS[number];

export interface Workflow {
	version: 1;
	id: string;
	name: string;
	description: string;
	triggers: string[];
	command: WorkflowCommand;
	promptTemplate: string;
	fusionInstruction?: string;
	stackPath?: string;
	confirm: boolean;
	sourcePath: string;
}

const ID_RE = /^[a-z0-9][a-z0-9-]{0,62}$/;
const WRITE_COMMANDS = new Set<WorkflowCommand>(["fh-fusion", "fh-collaborate", "fh-lanes", "fh-auto-validate", "fh-only"]);
const KEYS = new Set(["version", "id", "name", "description", "triggers", "command", "prompt_template", "fusion_instruction", "stack", "confirm"]);

function workflowError(file: string, messages: string[]): never {
	throw new Error(`fusion-harness: workflow invalid (${file}):\n${messages.map((message) => `- ${message}`).join("\n")}`);
}

export function loadWorkflow(fileInput: string): Workflow {
	const sourcePath = path.resolve(fileInput);
	let source: string;
	try { source = fs.readFileSync(sourcePath, "utf8"); } catch (error) {
		workflowError(sourcePath, [`file is unreadable: ${error instanceof Error ? error.message : String(error)}`]);
	}
	let parsed: unknown;
	try { parsed = parseYaml(source); } catch (error) {
		workflowError(sourcePath, [`YAML parse failed: ${error instanceof Error ? error.message : String(error)}`]);
	}
	if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) workflowError(sourcePath, ["top-level YAML value must be a mapping"]);
	const raw = parsed as Record<string, unknown>;
	const errors: string[] = [];
	for (const key of Object.keys(raw)) if (!KEYS.has(key)) errors.push(`unknown key ${JSON.stringify(key)}`);
	if (raw.version !== 1) errors.push("version must be 1");
	const id = typeof raw.id === "string" ? raw.id.trim() : "";
	if (!ID_RE.test(id)) errors.push("id must match ^[a-z0-9][a-z0-9-]{0,62}$");
	const name = typeof raw.name === "string" ? raw.name.trim() : "";
	if (!name) errors.push("name is required");
	const description = typeof raw.description === "string" ? raw.description.trim() : "";
	if (!description) errors.push("description is required");
	const command = typeof raw.command === "string" ? raw.command.trim() as WorkflowCommand : "" as WorkflowCommand;
	if (!WORKFLOW_COMMANDS.includes(command)) errors.push(`command must be one of ${WORKFLOW_COMMANDS.join(", ")}`);
	const promptTemplate = typeof raw.prompt_template === "string" ? raw.prompt_template.trim() : "";
	if (!promptTemplate) errors.push("prompt_template is required");
	if (raw.triggers !== undefined && (!Array.isArray(raw.triggers) || raw.triggers.some((item) => typeof item !== "string" || !item.trim()))) errors.push("triggers must be a list of non-empty strings");
	const triggers = Array.isArray(raw.triggers) ? raw.triggers.filter((item): item is string => typeof item === "string").map((item) => item.trim()) : [];
	const fusionInstruction = typeof raw.fusion_instruction === "string" ? raw.fusion_instruction.trim() : undefined;
	if (command === "fh-fusion" && !fusionInstruction) errors.push("fusion_instruction is required for fh-fusion");
	if (raw.confirm !== undefined && typeof raw.confirm !== "boolean") errors.push("confirm must be boolean");
	if (raw.stack !== undefined && (typeof raw.stack !== "string" || !raw.stack.trim())) errors.push("stack must be a non-empty path");
	if (errors.length) workflowError(sourcePath, errors);
	const stackPath = typeof raw.stack === "string" ? path.resolve(path.dirname(sourcePath), raw.stack.trim()) : undefined;
	return {
		version: 1,
		id,
		name,
		description,
		triggers,
		command,
		promptTemplate,
		fusionInstruction,
		stackPath,
		confirm: typeof raw.confirm === "boolean" ? raw.confirm : WRITE_COMMANDS.has(command),
		sourcePath,
	};
}

export function discoverWorkflows(directories: string[]): Workflow[] {
	const workflows: Workflow[] = [];
	const ids = new Map<string, string>();
	for (const directoryInput of directories) {
		const directory = path.resolve(directoryInput);
		if (!fs.existsSync(directory)) continue;
		for (const name of fs.readdirSync(directory).filter((entry) => /\.ya?ml$/i.test(entry)).sort()) {
			const workflow = loadWorkflow(path.join(directory, name));
			const previous = ids.get(workflow.id);
			if (previous) throw new Error(`fusion-harness: duplicate workflow id ${workflow.id}: ${previous} and ${workflow.sourcePath}`);
			ids.set(workflow.id, workflow.sourcePath);
			workflows.push(workflow);
		}
	}
	return workflows.sort((a, b) => a.id.localeCompare(b.id));
}

const words = (value: string): string[] => value.toLowerCase().split(/[^a-z0-9]+/).filter((word) => word.length > 1);
export interface WorkflowMatch { workflow: Workflow; score: number; arguments: string; reason: string }

export function scoreWorkflow(workflow: Workflow, queryInput: string): WorkflowMatch {
	const query = queryInput.trim();
	const lower = query.toLowerCase();
	const queryWords = new Set(words(query));
	let score = 0;
	let reason = "description";
	let args = query;
	if (lower === workflow.id) { score += 100; reason = "exact id"; args = ""; }
	else if (lower.startsWith(`${workflow.id} `)) { score += 70; reason = "id prefix"; args = query.slice(workflow.id.length).trim(); }
	if (lower === workflow.name.toLowerCase()) { score += 90; reason = "exact name"; args = ""; }
	else if (lower.startsWith(`${workflow.name.toLowerCase()} `)) { score += 65; reason = "name prefix"; args = query.slice(workflow.name.length).trim(); }
	for (const trigger of workflow.triggers) {
		const normalized = trigger.toLowerCase();
		if (lower === normalized) { score += 80; reason = `trigger: ${trigger}`; }
		else if (lower.includes(normalized)) { score += 45; reason = `trigger: ${trigger}`; }
		else if (words(trigger).every((word) => queryWords.has(word))) score += 25;
	}
	for (const word of new Set(words(`${workflow.name} ${workflow.description}`))) if (queryWords.has(word)) score += 2;
	return { workflow, score, arguments: args, reason };
}

export function routeWorkflows(workflows: Workflow[], query: string): { matches: WorkflowMatch[]; automatic?: WorkflowMatch } {
	const matches = workflows.map((workflow) => scoreWorkflow(workflow, query)).sort((a, b) => b.score - a.score || a.workflow.id.localeCompare(b.workflow.id));
	const top = matches[0];
	const second = matches[1];
	const automatic = top && top.score >= 40 && (!second || top.score - second.score >= 15) ? top : undefined;
	return { matches, automatic };
}

export function renderWorkflowPrompt(workflow: Workflow, task: string): string {
	const value = task.trim();
	return workflow.promptTemplate.replaceAll("{{TASK}}", value).replaceAll("$ARGUMENTS", value).trim();
}

export function workflowSkeleton(idInput: string): string {
	const id = ID_RE.test(idInput) ? idInput : "my-workflow";
	return stringifyYaml({
		version: 1,
		id,
		name: id.split("-").map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" "),
		description: "Describe when this workflow should be selected.",
		triggers: [id.replaceAll("-", " ")],
		command: "fh-opinion",
		prompt_template: "Complete this task:\n{{TASK}}\n",
		confirm: false,
	});
}

export function saveWorkflow(directoryInput: string, id: string, source: string): Workflow {
	if (!ID_RE.test(id)) throw new Error("workflow id must match ^[a-z0-9][a-z0-9-]{0,62}$");
	const directory = path.resolve(directoryInput);
	fs.mkdirSync(directory, { recursive: true });
	const destination = path.resolve(directory, `${id}.yaml`);
	if (path.dirname(destination) !== directory) throw new Error("workflow path escapes its workflow directory");
	if (fs.existsSync(destination)) throw new Error(`workflow already exists: ${destination}`);
	const temp = `${destination}.${process.pid}.tmp`;
	fs.writeFileSync(temp, source, { encoding: "utf8", flag: "wx" });
	try {
		const parsed = loadWorkflow(temp);
		if (parsed.id !== id) throw new Error(`workflow id ${parsed.id} does not match filename id ${id}`);
		fs.renameSync(temp, destination);
	} catch (error) {
		try { fs.unlinkSync(temp); } catch {}
		throw error;
	}
	return loadWorkflow(destination);
}
