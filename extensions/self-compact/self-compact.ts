/** Standalone Pi self-compaction. See README.md and the saved implementation plan. */
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { createHash, randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

// ═══════════════════════════ Public constants ═══════════════════════════

/** Canonical flag names (plan.md): plural pair from the brief, plus buffer/prompt. */
export const FLAGS = {
	soft: "compactions-soft-at",
	warning: "compactions-at",
	buffer: "compact-buffer",
	prompt: "compact-prompt",
	softAlias: "compact-soft-at",
	warningAlias: "compact-at",
} as const;

/** Default spec values; resolved against the live model window. */
export const DEFAULTS = { soft: "250k", warning: "350k", buffer: "50k" } as const;

export const PROMPT_FILES = {
	soft: "USER_SOFT_SELF_COMPACT.md",
	warning: "USER_PROMPT_SELF_COMPACT.md",
	compaction: "USER_PROMPT_COMPACTION_MESSAGE_.md",
} as const;

export const FALLBACK_PROMPTS = {
	soft: [
		"# Soft context notice",
		"",
		"Context is at {{PERCENT}}% ({{TOKENS}} of {{WINDOW}} tokens; soft threshold {{SOFT}}).",
		"This is a heads-up only: every tool remains available.",
		"Consider wrapping up long-running exploration or asking for a note-to-self soon.",
	].join("\n"),
	warning: [
		"# Compaction requested",
		"",
		"Context is at {{PERCENT}}% ({{TOKENS}} of {{WINDOW}} tokens; warning threshold {{WARNING}}).",
		"Write a note-to-self capturing the current goal, exact paths touched, test results,",
		"and next actions, then call self_compaction(note_to_self). Do not reinvent completed work.",
		"Ordinary tools remain available until the hard cutoff at {{FORCE}} tokens.",
	].join("\n"),
	compaction: [
		"Summarize current goal, completed work, exact paths, test results, and next actions.",
		"Do not reinvent completed work. Preserve exact file paths, function names, and error messages.",
	].join("\n"),
} as const;

/** The sole tool allowed at the forced threshold. */
export const FENCE_ALLOWED_TOOLS = new Set(["self_compaction"]);

export const CAP_PERCENT = 90;

/** Replacement is implemented through session_before_compact. */
export const REPLACEMENT_SUPPORTED = true;

// ═══════════════════════════ Errors ═══════════════════════════

export class SelfCompactError extends Error {
	constructor(message: string, readonly flag?: string) {
		super(flag ? `self-compact: ${message} (flag --${flag})` : `self-compact: ${message}`);
		this.name = "SelfCompactError";
	}
}

// ═══════════════ S1: threshold value parsing (pure) ═══════════════

export type ThresholdSpec = { kind: "tokens"; tokens: number } | { kind: "percent"; percent: number };

/**
 * Parse one threshold value. Accepts: whole token counts ("250000"), k/K ("250k",
 * "350K"), m/M ("1m"), percentages ("20%"). Rejects everything else loudly.
 */
export function parseThresholdValue(raw: string, flag: string): ThresholdSpec {
	const fail = (why: string): never => {
		throw new SelfCompactError(`${why}; got ${JSON.stringify(raw)}`, flag);
	};
	if (typeof raw !== "string" || raw.trim() === "") fail("value must be a token count, k/m suffix, or percentage");
	const text = raw.trim();
	const percent = /^(\d+(?:\.\d+)?)\s*%$/.exec(text);
	if (percent) {
		const value = Number(percent[1]);
		if (!Number.isFinite(value) || value <= 0) fail("percentage must be > 0");
		if (value > CAP_PERCENT) fail(`percentage must be <= ${CAP_PERCENT}`);
		return { kind: "percent", percent: value };
	}
	const suffixed = /^(\d+(?:\.\d+)?)\s*([kKmM])$/.exec(text);
	if (suffixed) {
		const value = Number(suffixed[1]);
		if (!Number.isFinite(value) || value < 0) fail("value must be >= 0");
		const mult = suffixed[2].toLowerCase() === "k" ? 1_000 : 1_000_000;
		const tokens = value * mult;
		if (!Number.isSafeInteger(tokens) || tokens <= 0) fail("value must resolve to positive whole safe tokens");
		return { kind: "tokens", tokens };
	}
	const plain = /^(\d+)$/.exec(text);
	if (plain) {
		const value = Number(plain[1]);
		if (!Number.isSafeInteger(value) || value <= 0) fail("value must be a positive safe integer");
		return { kind: "tokens", tokens: value };
	}
	return fail("unrecognized format; expected e.g. 250000, 250k, 1m, or 20%");
}

// ═══════════════ S2: threshold resolution (pure) ═══════════════

export interface ResolvedThresholds {
	window: number;
	soft: number;
	warning: number;
	buffer: number;
	force: number;
}

export interface ThresholdInputs {
	window: number;
	softSpec?: string;
	warningSpec?: string;
	bufferSpec?: string;
}

function specToTokens(spec: ThresholdSpec, window: number, flag: string): number {
	if (spec.kind === "tokens") return spec.tokens;
	return Math.round((spec.percent / 100) * window);
}

/**
 * Resolve soft/warning/buffer/force. Force = warning + buffer; buffer "0" overlaps
 * warning and force. Defaults scale down proportionally for windows where the 400k
 * default force would exceed 90% of the window, preserving order and force <= 90%.
 * Explicit values above 90% of the window, or out of order, are rejected.
 */
export function resolveThresholds(input: ThresholdInputs, flags = FLAGS): ResolvedThresholds {
	if (!Number.isFinite(input.window) || input.window <= 0) throw new SelfCompactError("model context window unknown or invalid");
	let softSpec = input.softSpec ?? DEFAULTS.soft;
	let warningSpec = input.warningSpec ?? DEFAULTS.warning;
	let bufferSpec = input.bufferSpec ?? DEFAULTS.buffer;

	// Scale omitted defaults only; explicit settings always retain their meaning.
	const cap = Math.floor((CAP_PERCENT / 100) * input.window);
	const factor = Math.min(1, cap / 400_000);
	if (input.softSpec === undefined) softSpec = String(Math.floor(250_000 * factor));
	if (input.warningSpec === undefined) warningSpec = String(Math.floor(350_000 * factor));
	if (input.bufferSpec === undefined) bufferSpec = String(Math.floor(400_000 * factor) - Math.floor(350_000 * factor));

	const soft = specToTokens(parseThresholdValue(softSpec, flags.soft), input.window, flags.soft);
	const warning = specToTokens(parseThresholdValue(warningSpec, flags.warning), input.window, flags.warning);
	const bufferRaw = (bufferSpec ?? "").trim();
	const buffer = /^0(?:\.0+)?\s*(?:[%kKmM])?$/.test(bufferRaw) ? 0 : specToTokens(parseThresholdValue(bufferSpec ?? "50k", flags.buffer), input.window, flags.buffer);
	const force = warning + buffer;

	const over = (name: string, value: number, flag: string) =>
		new SelfCompactError(`${name} threshold ${value} is above the ${CAP_PERCENT}% cap (${cap} tokens) for this window`, flag);
	if (soft > cap) throw over("soft", soft, flags.soft);
	if (warning > cap) throw over("warning", warning, flags.warning);
	if (force > cap) throw over("force", force, flags.buffer);
	if (soft <= 0 || warning <= 0) throw new SelfCompactError("thresholds must resolve to positive tokens");
	if (soft >= warning) throw new SelfCompactError(`soft (${soft}) must be below warning (${warning})`, flags.soft);
	if (buffer < 0) throw new SelfCompactError("buffer must be >= 0", flags.buffer);
	return { window: input.window, soft, warning, buffer, force };
}

// ═══════════════ Level classification (pure) ═══════════════

export type Level = "ok" | "soft" | "warning" | "forced";

export function classifyLevel(tokens: number, t: ResolvedThresholds): Level {
	if (tokens >= t.force) return "forced";
	if (tokens >= t.warning) return "warning";
	if (tokens >= t.soft) return "soft";
	return "ok";
}

// ═══════════════ S3: 20-cell meter (pure) ═══════════════

export interface MeterInput {
	usedTokens: number | null;
	cacheTokens?: number | null;
	thresholds: ResolvedThresholds;
}

export interface MeterOutput {
	bar: string;
	percent: number | null;
	legend: string;
}

/** 20 five-percent cells. Markers remain visible ahead of occupancy.
 * Cached tokens remain part of context occupancy; cacheRead is display-only.
 */
export function renderBar(input: MeterInput): MeterOutput {
	const { thresholds: t } = input;
	const cells = 20;
	const pct = (n: number) => (n / t.window) * 100;
	const cellOf = (p: number) => Math.min(cells - 1, Math.floor(p / 5));
	const softCell = cellOf(pct(t.soft));
	const warnCell = cellOf(pct(t.warning));
	const forceCell = cellOf(pct(t.force));
	const overlap = warnCell === forceCell;

	let usedCells = 0;
	let percent: number | null = null;
	if (input.usedTokens !== null && Number.isFinite(input.usedTokens)) {
		percent = Math.round((input.usedTokens * 100) / t.window);
		// Multiply before dividing: (tokens/window)*cells drifts through float error (e.g. 0.45*20 -> 9.000000000000002).
		usedCells = Math.min(cells, Math.ceil((input.usedTokens * cells) / t.window));
	}
	const cachedCells =
		input.cacheTokens !== null && input.cacheTokens !== undefined && Number.isFinite(input.cacheTokens)
			? Math.min(usedCells, Math.floor((Math.max(0, input.cacheTokens) * cells) / t.window))
			: 0;

	let out = "";
	for (let i = 0; i < cells; i++) {
		if (overlap && i === warnCell) out += "|";
		else if (i === warnCell || i === forceCell) out += "!";
		else if (i === softCell) out += "/";
		else if (i < cachedCells) out += "#";
		else if (i < usedCells) out += "=";
		else out += "-";
	}
	const legend = `[${percent === null ? "usage unknown" : `${percent}% used`}] soft ${Math.round(pct(t.soft))}% (${t.soft}) · warning ${Math.round(pct(t.warning))}% (${t.warning}) · force ${Math.round(pct(t.force))}% (${t.force})${cachedCells ? ` · # cached ${cachedCells} cells` : ""}`;
	return { bar: `[${out}]`, percent, legend };
}

// ═══════════════ Prompt files (S5 content source) ═══════════════

export function loadPromptFile(cwd: string, filename: string): string | null {
	const file = path.join(cwd, ".pi", "self-compact", filename);
	try {
		const text = fs.readFileSync(file, "utf8").trim();
		return text.length ? text : null;
	} catch {
		return null;
	}
}

export function fillTemplate(template: string, values: Record<string, string | number>): string {
	return template.replace(/\{\{(\w+)\}\}/g, (_m, key: string) => String(values[key] ?? ""));
}

/** Precedence: literal --compact-prompt > editable file > shipped fallback. */
export function buildCompactionInstructions(literalPrompt: string | undefined, files: { compaction: string | null; warning: string | null }, note?: string): string {
	// Notes and warning text belong in user messages, never in the system prompt.
	return literalPrompt !== undefined ? literalPrompt : files.compaction ?? FALLBACK_PROMPTS.compaction;
}

// ═══════════════ Flag coalescing (S1 aliases) ═══════════════

/** Read canonical flag; if an alias is also set it must match or the conflict is loud. */
export function coalesceFlag(get: (name: string) => string | undefined, canonical: string, alias: string): string | undefined {
	const primary = get(canonical);
	const secondary = get(alias);
	if (primary !== undefined && secondary !== undefined && String(primary).trim() !== String(secondary).trim()) {
		throw new SelfCompactError(`conflicting values for --${canonical} (${JSON.stringify(primary)}) and alias --${alias} (${JSON.stringify(secondary)}); set only one`, canonical);
	}
	return primary ?? secondary;
}

// Custom summary generation is isolated so tests can observe the exact request.
export async function summarize(
	event: any, ctx: ExtensionContext, systemPrompt: string, note: string,
	serialize?: (messages: any[]) => string,
) {
	const { preparation: p, signal } = event;
	if (signal.aborted) throw new Error("Compaction aborted");
	if (!ctx.model) throw new Error("No model selected for compaction");
	if (!serialize) {
		const api = await import("@earendil-works/pi-coding-agent");
		serialize = messages => api.serializeConversation(api.convertToLlm(messages));
	}
	const text = [
		"Summarize the following session data. Preserve outstanding work and exact paths.",
		`Previous summary:\n${p.previousSummary ?? "(none)"}`,
		`Note-to-self:\n${note || "(none)"}`,
		`Additional user guidance:\n${event.customInstructions ?? "(none)"}`,
		`Conversation:\n${serialize([...p.messagesToSummarize, ...p.turnPrefixMessages])}`,
	].join("\n\n");
	const response = await ctx.modelRegistry.complete(ctx.model, {
		systemPrompt,
		messages: [{ role: "user", content: [{ type: "text", text }], timestamp: Date.now() }],
	}, { signal, maxTokens: Math.min(8192, ctx.model.maxTokens), cacheRetention: "none" });
	if (signal.aborted || response.stopReason === "aborted") throw new Error("Compaction aborted");
	if (response.stopReason === "error" || response.stopReason === "length") {
		throw new Error(response.errorMessage || `Incomplete summary (${response.stopReason})`);
	}
	const summary = response.content.filter(c => c.type === "text").map(c => c.text).join("\n").trim();
	if (!summary) throw new Error("Compaction summary was empty");
	return { summary, firstKeptEntryId: p.firstKeptEntryId, tokensBefore: p.tokensBefore, usage: response.usage };
}

export default function selfCompact(pi: ExtensionAPI): void {
	for (const [name, description] of [
		[FLAGS.soft, "Soft notice threshold. Default 250k; accepts tokens, k/m or %."],
		[FLAGS.warning, "Ask agent to self_compaction. Default 350k."],
		[FLAGS.buffer, "Extra context before blocking ordinary tools. Default 50k; accepts 0."],
		[FLAGS.prompt, "Literal replacement for the summary system prompt."],
		[FLAGS.softAlias, "Alias for --compactions-soft-at."],
		[FLAGS.warningAlias, "Alias for --compactions-at."],
	]) pi.registerFlag(name, { type: "string", description });
	const get = (name: string) => {
		const value = pi.getFlag(name);
		return value === undefined ? undefined : String(value);
	};
	// Pi fills flags after factory loading: validate on session events, not here.
	let thresholds: ResolvedThresholds | null = null;
	let level: Level = "ok";
	let blocked = false;
	let configError: string | null = null;
	let failure: string | null = null;
	let cache: number | null = null;
	let inFlight = false;
	let pending = false;
	let resume = false;
	let note = "";
	let generation = 0;
	let attempted = false;
	let needsRelief = false;
	const apiBase = (process.env.SELF_COMPACT_API_URL ?? "http://127.0.0.1:8787").replace(/\/$/, "");
	const apiTokenFile = process.env.SELF_COMPACT_TOKEN_FILE ?? path.join(os.homedir(), ".config/self-compact/token");
	const ephemeralId = randomUUID().replace(/-/g, "");
	let apiTimer: ReturnType<typeof setInterval> | null = null;
	let apiSessionId = ephemeralId;
	let apiContext: ExtensionContext | null = null;
	let apiPolling = false;
	const apiEnabled = process.env.SELF_COMPACT_API_DISABLE !== "1";
	const pollMs = Math.max(50, Number(process.env.SELF_COMPACT_API_POLL_MS ?? 5000) || 5000);
	function sessionId(ctx: ExtensionContext): string {
		const file = ctx.sessionManager.getSessionFile?.();
		return file ? createHash("sha256").update(file).digest("hex") : ephemeralId;
	}
	async function apiPost(route: string, body: Record<string, unknown> = {}): Promise<Record<string, unknown> | null> {
		if (!apiEnabled) return null;
		let secret: string;
		try { secret = fs.readFileSync(apiTokenFile, "utf8").trim(); } catch { return null; }
		try {
			const response = await fetch(`${apiBase}/v1/sessions/${apiSessionId}${route}`, {
				method: "POST", headers: { Authorization: `Bearer ${secret}`, "Content-Type": "application/json" },
				body: JSON.stringify(body), signal: AbortSignal.timeout(300),
			});
			return response.ok ? await response.json() as Record<string, unknown> : null;
		} catch { return null; }
	}
	function publish(ctx: ExtensionContext): Promise<Record<string, unknown> | null> | undefined {
		const usage = ctx.getContextUsage();
		if (!thresholds || usage?.tokens == null) return;
		return apiPost("", { used: usage.tokens, window: thresholds.window, soft: thresholds.soft,
			warning: thresholds.warning, force: thresholds.force, level });
	}
	async function pollApi() {
		if (!apiContext || apiPolling || inFlight || pending || !apiContext.isIdle()) return;
		apiPolling = true;
		try {
			await publish(apiContext);
			const response = await apiPost("/claim");
			if (response?.compact && apiContext.isIdle()) {
				resume = true;
				request(apiContext);
			} else if (response?.compact) {
				await apiPost("/compact");
			}
		} finally { apiPolling = false; }
	}
	function startApi(ctx: ExtensionContext) {
		apiContext = ctx;
		apiSessionId = sessionId(ctx);
		if (!apiEnabled || apiTimer) return;
		apiTimer = setInterval(() => { void pollApi(); }, pollMs);
		apiTimer.unref();
	}

	function reset() {
		generation++;
		thresholds = null; level = "ok"; blocked = false; configError = null;
		failure = null; cache = null; inFlight = false; pending = false;
		resume = false; note = ""; attempted = false; needsRelief = false;
	}
	function resolve(ctx: ExtensionContext) {
		const window = ctx.getContextUsage()?.contextWindow ?? ctx.model?.contextWindow ?? 0;
		try {
			thresholds = resolveThresholds({ window,
				softSpec: coalesceFlag(get, FLAGS.soft, FLAGS.softAlias),
				warningSpec: coalesceFlag(get, FLAGS.warning, FLAGS.warningAlias),
				bufferSpec: get(FLAGS.buffer) });
			if (get(FLAGS.prompt) !== undefined && !get(FLAGS.prompt)!.trim()) throw new SelfCompactError("prompt must not be empty", FLAGS.prompt);
			configError = null;
		} catch (error) {
			thresholds = null;
			const message = String(error);
			if (message !== configError && ctx.hasUI) ctx.ui.notify(message, "error");
			configError = message;
		}
	}
	function widget(ctx: ExtensionContext, tokens: number | null) {
		if (!ctx.hasUI) return;
		if (!thresholds) {
			ctx.ui.setWidget("self-compact", [`self-compact: invalid configuration: ${configError}`]);
			return;
		}
		const meter = renderBar({ usedTokens: tokens, cacheTokens: cache, thresholds });
		ctx.ui.setWidget("self-compact", [
			`self-compact ${meter.bar} ${meter.legend}`,
			`${level.toUpperCase()}${blocked ? " · ordinary tools blocked; call self_compaction(note_to_self)" : ""}${failure ? ` · failed: ${failure}; retry self_compaction or /self-compact` : ""}`,
		]);
	}
	function fail(ctx: ExtensionContext, message: string) {
		inFlight = false; pending = false; failure = message;
		if (ctx.hasUI) ctx.ui.notify(`self-compact: ${message}`, "error");
		widget(ctx, ctx.getContextUsage()?.tokens ?? null);
	}
	function notice(ctx: ExtensionContext, tokens: number, kind: "soft" | "warning") {
		const t = thresholds!;
		const content = fillTemplate(loadPromptFile(ctx.cwd, PROMPT_FILES[kind]) ?? FALLBACK_PROMPTS[kind], {
			PERCENT: Math.round(tokens * 100 / t.window), TOKENS: tokens, WINDOW: t.window,
			SOFT: t.soft, WARNING: t.warning, FORCE: t.force,
		});
		pi.sendMessage({ customType: `self-compact-${kind}`, content, display: true }, { deliverAs: "steer" });
	}
	const usageBelowWarning = (tokens: number) => thresholds !== null && tokens < thresholds.warning;
	function check(ctx: ExtensionContext) {
		resolve(ctx);
		const tokens = ctx.getContextUsage()?.tokens ?? null;
		if (thresholds && tokens !== null) {
			const next = classifyLevel(tokens, thresholds);
			const order: Level[] = ["ok", "soft", "warning", "forced"];
			if (order.indexOf(next) > order.indexOf(level)) {
				if (next === "soft") notice(ctx, tokens, "soft");
				else notice(ctx, tokens, "warning");
			}
			level = next;
			if (next === "forced") {
				blocked = true;
				if (needsRelief) failure = "Compacted context still exceeds the hard cutoff. Automatic compaction paused; raise thresholds or explicitly retry /self-compact.";
			}
			if (usageBelowWarning(tokens) && !inFlight && !pending) {
				attempted = false; needsRelief = false;
			}
		}
		widget(ctx, tokens);
		void publish(ctx);
	}
	function request(ctx: ExtensionContext) {
		if (inFlight || configError) return;
		inFlight = true; pending = false; attempted = true;
		const current = generation;
		try {
			ctx.compact({
				onComplete: () => {
					if (current !== generation) return;
					inFlight = false;
					void apiPost("/result", { status: "completed" });
					// Lifecycle event resets state before this callback. Resume exactly once.
					if (resume) {
						resume = false;
						pi.sendMessage({ customType: "self-compact-resume", display: true,
							content: "Compaction completed. Continue the current goal using the summary and note-to-self. Do not repeat completed work." },
							{ triggerTurn: true, deliverAs: "followUp" });
					}
				},
				onError: error => { if (current === generation) { fail(ctx, error.message); void apiPost("/result", { status: "failed" }); } },
			});
		} catch (error) { fail(ctx, String(error)); void apiPost("/result", { status: "failed" }); }
	}
	const recoverNote = (ctx: ExtensionContext) => {
		for (const entry of ctx.sessionManager.getBranch()) {
			if (entry.type === "custom" && entry.customType === "self-compact-note") {
				note = (entry.data as { note_to_self: string }).note_to_self;
			}
			if (entry.type === "compaction") note = "";
		}
	};
	const resetSession = async (_event: unknown, ctx: ExtensionContext) => { reset(); startApi(ctx); recoverNote(ctx); check(ctx); };
	pi.on("session_start", resetSession);
	// Pi 0.84 emits session_start with reason resume/new/fork for transitions.
	pi.on("session_tree", resetSession);
	pi.on("session_shutdown", async () => { if (apiTimer) clearInterval(apiTimer); apiTimer = null; apiContext = null; reset(); });
	pi.on("model_select", async (_event, ctx) => {
		thresholds = null; cache = null; level = "ok"; blocked = false; attempted = false; check(ctx);
	});
	pi.on("message_end", async (event, ctx) => {
		if (event.message.role === "assistant") {
			cache = event.message.usage?.cacheRead ?? null;
			check(ctx);
		}
	});
	pi.on("before_agent_start", async (_event, ctx) => check(ctx));
	pi.on("turn_end", async (_event, ctx) => {
		check(ctx);
		// Pi aborts the agent, then compacts. turn_end follows all persisted tool results.
		if (pending) request(ctx);
	});
	pi.on("agent_settled", async (_event, ctx) => {
		check(ctx);
		if (pending || (blocked && !attempted)) {
			resume = true;
			request(ctx);
		}
	});
	pi.on("tool_call", async (event, ctx) => {
		check(ctx);
		if (event.toolName === "self_compaction" && !configError) return;
		if (configError || blocked || pending || inFlight) return { block: true,
			reason: configError ?? "Context compaction required. Call self_compaction with note_to_self; all ordinary tools are blocked until successful compaction. Manual recovery: /self-compact [note]." };
	});
	pi.registerTool({
		name: "self_compaction", label: "Self compaction",
		description: "Save a note-to-self and compact context, then continue. Include current goal, completed work, exact paths, test results and next actions.",
		promptSnippet: "Compact context with a saved note-to-self and resume work.",
		parameters: { type: "object", properties: { note_to_self: { type: "string", minLength: 1 } }, required: ["note_to_self"], additionalProperties: false } as never,
		async execute(_id, params: { note_to_self: string }, signal, _update, ctx) {
			check(ctx);
			if (signal?.aborted) throw new Error("Self compaction aborted");
			if (configError) throw new Error(configError);
			if (inFlight || pending) return { content: [{ type: "text", text: "Compaction already pending." }], details: {} };
			if (!params.note_to_self?.trim()) throw new Error("note_to_self must not be empty");
			note = params.note_to_self;
			pi.appendEntry("self-compact-note", { note_to_self: note });
			pending = true; resume = true; failure = null;
			return { content: [{ type: "text", text: "Note saved. Compaction queued after this tool result; work will resume after success." }], details: {} };
		},
	});
	pi.registerCommand("self-compact", {
		description: "Compact now with an optional note-to-self; also retries failures.",
		handler: async (args, ctx) => {
			check(ctx);
			if (inFlight) return;
			if (args.trim()) { note = args; pi.appendEntry("self-compact-note", { note_to_self: note }); }
			failure = null; resume = false;
			request(ctx);
		},
	});
	pi.on("session_before_compact", async (event, ctx) => {
		inFlight = true; attempted = true;
		const current = generation;
		try {
			const prompt = buildCompactionInstructions(get(FLAGS.prompt), {
				compaction: loadPromptFile(ctx.cwd, PROMPT_FILES.compaction), warning: null,
			});
			const compaction = await summarize(event, ctx, prompt, note);
			if (current !== generation) return { cancel: true };
			return { compaction };
		} catch (error) {
			if (current === generation) fail(ctx, String(error));
			return { cancel: true }; // Never silently revert to Pi's default system prompt.
		}
	});
	pi.on("session_compact", async (_event, ctx) => {
		inFlight = false; blocked = false; pending = false; attempted = true; needsRelief = true;
		failure = null; level = "ok"; cache = null; note = "";
		widget(ctx, null);
	});
	pi.on("session_compact_failed", async (event, ctx) => {
		fail(ctx, failure ?? event.errorMessage ?? (event.aborted ? "Compaction aborted" : "Compaction failed"));
	});
}
