import * as fs from "node:fs";
import * as path from "node:path";

/** Relative plan folder. Same refusal rules as SSSF resolve_plan_dir. */
export function resolvePlanDir(arg: string): string {
	if (!arg || [...arg].some((ch) => /\s/u.test(ch))) {
		throw new Error(`plan folder ${JSON.stringify(arg)} must be a relative folder with no whitespace`);
	}
	const text = arg.endsWith("/") ? arg.slice(0, -1) : arg;
	if (!text || text.endsWith("/") || text.startsWith("/") || text.startsWith("~")) {
		throw new Error(`plan folder ${JSON.stringify(arg)} must be a relative folder`);
	}
	const parts = text.split("/");
	if (parts.some((part) => part === "" || part === "." || part === "..")) {
		throw new Error(`plan folder ${JSON.stringify(arg)} must not contain . or ..`);
	}
	for (const part of parts) {
		if (![...part].every((ch) => /[A-Za-z0-9_-]/u.test(ch))) {
			throw new Error(`plan folder ${JSON.stringify(arg)} may only use letters, numbers, - and _`);
		}
	}
	if (parts[0] === ".git") throw new Error("plan folder must not be .git");
	return text;
}

export function parsePlanArgs(raw: string): { planDir: string; task: string } {
	const text = raw.trim();
	const usage = "Usage: /fh-plan [--plan-dir DIR] <task>";
	if (!text) throw new Error(usage);
	const attached = /^--plan-dir=(\S+)\s+([\s\S]+)$/.exec(text);
	if (attached) return { planDir: attached[1], task: attached[2].trim() };
	if (text.startsWith("--plan-dir")) {
		const rest = text.slice("--plan-dir".length).trim();
		const split = /^(\S+)\s+([\s\S]+)$/.exec(rest);
		if (!split || !split[2].trim()) throw new Error(usage);
		return { planDir: split[1], task: split[2].trim() };
	}
	if (text.startsWith("-")) throw new Error(usage);
	return { planDir: "planADW", task: text };
}

/** Next free PLAN.md / PLAN_vN.md inside the project. Never escapes the repo root. */
export function nextPlanFile(repoRoot: string, planDir: string): { absolute: string; relative: string } {
	const dirName = resolvePlanDir(planDir);
	const root = fs.realpathSync(repoRoot);
	const dir = path.resolve(root, dirName);
	const relDir = path.relative(root, dir);
	if (!relDir || relDir.startsWith("..") || path.isAbsolute(relDir)) {
		throw new Error("plan folder escapes the project");
	}
	let name = "PLAN.md";
	for (let version = 2; fs.existsSync(path.join(dir, name)); version++) {
		if (version > 100) throw new Error("plan folder already has PLAN.md through PLAN_v100.md");
		name = `PLAN_v${version}.md`;
	}
	const absolute = path.join(dir, name);
	return { absolute, relative: path.relative(root, absolute).split(path.sep).join("/") };
}

export const PLAN_HEADINGS = [
	"Decoded ask",
	"Evidence",
	"Do not touch",
	"Deliverables",
	"Steps",
	"Checklist",
	"Verify",
	"Handoff",
] as const;

export function missingPlanHeadings(text: string): string[] {
	return PLAN_HEADINGS.filter((heading) => !new RegExp(`^#{1,3}[ \\t]+${heading}[ \\t]*$`, "im").test(text));
}
