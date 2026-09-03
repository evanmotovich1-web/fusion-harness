import * as os from "node:os";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { discoverWorkflows, renderWorkflowPrompt, routeWorkflows, saveWorkflow, workflowSkeleton, type Workflow, type WorkflowCommand } from "./workflow-registry.ts";
import type { XResearchRunner } from "./x-research.ts";

export type WorkflowHandler = (raw: string, ctx: any) => Promise<void>;

export interface WorkflowCommandDeps {
	handlers: Partial<Record<WorkflowCommand, WorkflowHandler>>;
	researchX: XResearchRunner;
	applyStack(stackPath: string, ctx: any): Promise<void>;
	workflowDirectories?(cwd: string): string[];
}

// pi runs under Node: import.meta.dir is Bun-only, so derive the module dir the way prompt-library.ts does.
const MODULE_DIR: string = typeof __dirname !== "undefined" && __dirname ? __dirname : path.dirname(new URL(import.meta.url).pathname);
const shippedDirectory = path.resolve(MODULE_DIR, "..", "workflows");
const globalDirectory = () => path.join(os.homedir(), ".pi", "agent", "fusion-harness", "workflows");
const projectDirectory = (cwd: string) => path.join(cwd, ".pi", "fusion-harness", "workflows");
const directories = (cwd: string) => [shippedDirectory, globalDirectory(), projectDirectory(cwd)];

async function chooseWorkflow(ctx: any, workflows: Workflow[], query: string): Promise<{ workflow: Workflow; args: string } | undefined> {
	if (!query) {
		const labels = workflows.map((workflow) => `${workflow.name} | ${workflow.command} | ${workflow.description}`);
		const picked = await ctx.ui.select("Choose a saved workflow", labels);
		const index = labels.indexOf(picked);
		return index >= 0 ? { workflow: workflows[index], args: "" } : undefined;
	}
	const routed = routeWorkflows(workflows, query);
	if (routed.automatic) return { workflow: routed.automatic.workflow, args: routed.automatic.arguments };
	const candidates = routed.matches.slice(0, 5);
	const labels = candidates.map((match) => `${match.workflow.name} | score ${match.score} | ${match.workflow.description}`);
	const picked = await ctx.ui.select("No confident workflow match. Choose one", labels);
	const index = labels.indexOf(picked);
	return index >= 0 ? { workflow: candidates[index].workflow, args: query } : undefined;
}

export function registerWorkflowCommands(pi: ExtensionAPI, deps: WorkflowCommandDeps): void {
	pi.registerCommand("find-workflow", {
		description: "Route a task to the best saved Fusion Harness workflow.",
		handler: async (raw, ctx) => {
			let workflows: Workflow[];
			try { workflows = discoverWorkflows(deps.workflowDirectories?.(ctx.cwd) ?? directories(ctx.cwd)); } catch (error) {
				ctx.ui.notify(error instanceof Error ? error.message : String(error), "error");
				return;
			}
			if (!workflows.length) {
				ctx.ui.notify("fusion-harness: no workflows found; use /create-workflow <id>", "warning");
				return;
			}
			const selected = await chooseWorkflow(ctx, workflows, (raw ?? "").trim());
			if (!selected) return;
			const workflow = selected.workflow;
			if (workflow.confirm) {
				if (typeof ctx.ui.confirm !== "function") {
					ctx.ui.notify(`fusion-harness: ${workflow.id} requires confirmation, but this UI cannot ask for it`, "error");
					return;
				}
				const approved = await ctx.ui.confirm(`Run ${workflow.name}?`, `${workflow.command} may modify the working directory.\n${workflow.sourcePath}`);
				if (!approved) return;
			}
			try {
				if (workflow.stackPath) await deps.applyStack(workflow.stackPath, ctx);
				const prompt = renderWorkflowPrompt(workflow, selected.args);
				ctx.ui.notify(`fusion-harness: ${workflow.name} → /${workflow.command}\n${workflow.sourcePath}`, "info");
				if (workflow.command === "research-x") return await deps.researchX(prompt, ctx);
				const handler = deps.handlers[workflow.command];
				if (!handler) throw new Error(`workflow command is not available: ${workflow.command}`);
				const commandInput = workflow.command === "fh-fusion" ? `${prompt}\n\n::\n\n${workflow.fusionInstruction}` : prompt;
				await handler(commandInput, ctx);
			} catch (error) {
				ctx.ui.notify(`fusion-harness: workflow ${workflow.id} failed — ${error instanceof Error ? error.message : String(error)}`, "error");
			}
		},
	});

	pi.registerCommand("create-workflow", {
		description: "Create and validate a saved workflow YAML file.",
		handler: async (raw, ctx) => {
			const tokens = (raw ?? "").trim().split(/\s+/).filter(Boolean);
			const useGlobal = tokens.includes("--global");
			const id = tokens.find((token) => token !== "--global") ?? "my-workflow";
			if (typeof ctx.ui.editor !== "function") {
				ctx.ui.notify("fusion-harness: this UI does not provide an editor; create the YAML under .pi/fusion-harness/workflows/", "error");
				return;
			}
			const source = await ctx.ui.editor(`Create workflow: ${id}`, workflowSkeleton(id));
			if (!source) return;
			try {
				const directory = useGlobal ? globalDirectory() : projectDirectory(ctx.cwd);
				const workflow = saveWorkflow(directory, id, source);
				ctx.ui.notify(`fusion-harness: saved ${workflow.id}\n${workflow.sourcePath}`, "info");
			} catch (error) {
				ctx.ui.notify(error instanceof Error ? error.message : String(error), "error");
			}
		},
	});
}
