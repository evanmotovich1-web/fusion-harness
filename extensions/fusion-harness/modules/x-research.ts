import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export interface XResearchOptions {
	query: string;
	fromDate?: string;
	toDate?: string;
	allowedHandles?: string[];
	excludedHandles?: string[];
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const HANDLE_RE = /^@?[A-Za-z0-9_]{1,15}$/;

export function normalizeXResearchOptions(input: XResearchOptions): XResearchOptions {
	const query = input.query.trim();
	if (!query) throw new Error("X research query is required");
	for (const [label, value] of [["fromDate", input.fromDate], ["toDate", input.toDate]] as const) {
		const parsed = value && DATE_RE.test(value) ? new Date(`${value}T00:00:00Z`) : undefined;
		if (value && (!parsed || Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value)) throw new Error(`${label} must be YYYY-MM-DD`);
	}
	if (input.fromDate && input.toDate && input.fromDate > input.toDate) throw new Error("fromDate must not be after toDate");
	const handles = (values: string[] | undefined, label: string): string[] | undefined => {
		if (!values?.length) return undefined;
		return values.map((value) => {
			const trimmed = value.trim();
			if (!HANDLE_RE.test(trimmed)) throw new Error(`${label} contains an invalid X handle: ${value}`);
			return trimmed.replace(/^@/, "");
		});
	};
	return {
		query,
		fromDate: input.fromDate,
		toDate: input.toDate,
		allowedHandles: handles(input.allowedHandles, "allowedHandles"),
		excludedHandles: handles(input.excludedHandles, "excludedHandles"),
	};
}

export function buildXResearchRequest(input: XResearchOptions): Record<string, unknown> {
	const options = normalizeXResearchOptions(input);
	const tool: Record<string, unknown> = {
		type: "x_search",
		enable_image_understanding: true,
		enable_video_understanding: true,
	};
	if (options.fromDate) tool.from_date = options.fromDate;
	if (options.toDate) tool.to_date = options.toDate;
	if (options.allowedHandles) tool.allowed_x_handles = options.allowedHandles;
	if (options.excludedHandles) tool.excluded_x_handles = options.excludedHandles;
	return { model: "grok-4.6", input: options.query, tools: [tool] };
}

function collectResponseText(value: unknown, out: string[], urls: Set<string>): void {
	if (!value || typeof value !== "object") return;
	if (Array.isArray(value)) {
		for (const item of value) collectResponseText(item, out, urls);
		return;
	}
	const record = value as Record<string, unknown>;
	if ((record.type === "output_text" || record.type === "text") && typeof record.text === "string") out.push(record.text);
	for (const key of ["url", "expanded_url"]) {
		const candidate = record[key];
		if (typeof candidate === "string" && /^https?:\/\//i.test(candidate)) urls.add(candidate);
	}
	for (const child of Object.values(record)) collectResponseText(child, out, urls);
}

export function extractXResearchResponse(payload: unknown): { text: string; urls: string[] } {
	const text: string[] = [];
	const urls = new Set<string>();
	collectResponseText(payload, text, urls);
	const root = payload && typeof payload === "object" ? payload as Record<string, unknown> : undefined;
	if (!text.length && typeof root?.output_text === "string") text.push(root.output_text);
	const uniqueText = [...new Set(text.map((part) => part.trim()).filter(Boolean))];
	return { text: uniqueText.join("\n\n"), urls: [...urls] };
}

export async function researchX(input: XResearchOptions, init: { apiKey?: string; fetchImpl?: typeof fetch } = {}): Promise<{ text: string; urls: string[]; raw: unknown }> {
	const apiKey = init.apiKey ?? process.env.XAI_API_KEY;
	if (!apiKey) throw new Error("XAI_API_KEY is not configured. Add it to .env or authenticate the xAI provider.");
	const response = await (init.fetchImpl ?? fetch)("https://api.x.ai/v1/responses", {
		method: "POST",
		headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
		body: JSON.stringify(buildXResearchRequest(input)),
	});
	const rawText = await response.text();
	let raw: unknown;
	try { raw = JSON.parse(rawText); } catch { raw = { raw: rawText }; }
	if (!response.ok) {
		const message = raw && typeof raw === "object" && typeof (raw as any).error?.message === "string" ? (raw as any).error.message : rawText.slice(0, 1_000);
		throw new Error(`xAI X search failed (${response.status}): ${message}`);
	}
	const extracted = extractXResearchResponse(raw);
	if (!extracted.text) throw new Error("xAI returned no readable research text");
	return { ...extracted, raw };
}

export type XResearchRunner = (query: string, ctx: any) => Promise<void>;

export function registerXResearchCommand(pi: ExtensionAPI): XResearchRunner {
	const run: XResearchRunner = async (query, ctx) => {
		const input = (query ?? "").trim();
		if (!input) {
			ctx.ui.notify("Usage: /research-x <query>", "warning");
			return;
		}
		ctx.ui.setStatus("fusion-harness", "research-x: Grok searching live X…");
		try {
			const result = await researchX({ query: input });
			const root = fs.existsSync("/tmp") ? "/tmp" : os.tmpdir();
			const dir = await fs.promises.mkdtemp(path.join(root, "fusion-harness-x-"));
			await fs.promises.writeFile(path.join(dir, "response.json"), `${JSON.stringify(result.raw, null, 2)}\n`, "utf8");
			const citations = result.urls.length ? `\n\nSources:\n${result.urls.map((url) => `- ${url}`).join("\n")}` : "";
			const body = `${result.text}${citations}`;
			pi.sendMessage({ customType: "fusion-harness", content: body.slice(0, 50_000), display: true, details: { kind: "solo", command: "research-x", ok: true, artifactsDir: dir } });
			if (body.length > 50_000) ctx.ui.notify(`research-x: display truncated; complete response: ${dir}/response.json`, "warning");
		} catch (error) {
			ctx.ui.notify(`research-x: ${error instanceof Error ? error.message : String(error)}`, "error");
		} finally {
			ctx.ui.setStatus("fusion-harness", undefined);
		}
	};
	pi.registerCommand("research-x", { description: "Research live X posts with Grok x_search and return cited results.", handler: run });
	return run;
}
