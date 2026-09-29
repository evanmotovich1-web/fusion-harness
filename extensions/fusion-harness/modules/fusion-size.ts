/**
 * /fusion N [model…] — choose how many agents run and which model each one uses.
 *
 * Pure functions (no pi session state) so they test without pi: parse the arguments,
 * resolve a short model name against the usable catalog, and build the N-slot stack.
 * Slot 1 is the ARCHITECT, slot 2 the Main builder (the host), the rest are builders.
 */

import type { CatalogModel } from "./model-browser.ts";
import { resolveThinking, SLOT_COLOR_PALETTE, slotId, type HexColor, type ModelSlot, type ModelStack, type Thinking } from "./model-stack.ts";

export const MIN_AGENTS = 2;
export const MAX_AGENTS = 20;

export interface FusionPick {
	model: string; // provider/id
	thinking?: Thinking;
}

export interface FusionArgs {
	count?: number;
	tokens: string[];
	error?: string;
}

/** `3 opus sol grok:high` → count 3 and the model tokens given up front (may be fewer than 3). */
export function parseFusionArgs(raw: string): FusionArgs {
	const words = raw.trim().split(/\s+/).filter(Boolean);
	if (!words.length) return { tokens: [] };
	if (!/^\d+$/.test(words[0]!)) return { tokens: [], error: `the first argument is the number of agents; got "${words[0]}"` };
	const count = Number(words[0]);
	if (count < MIN_AGENTS || count > MAX_AGENTS) return { tokens: [], error: `choose ${MIN_AGENTS}-${MAX_AGENTS} agents; got ${count}` };
	const tokens = words.slice(1);
	if (tokens.length > count) return { count, tokens: [], error: `${tokens.length} models named for ${count} agents` };
	return { count, tokens };
}

const versionOf = (id: string): number[] => (id.match(/\d+/g) ?? []).map(Number);

function newer(a: number[], b: number[]): boolean {
	for (let i = 0; i < Math.max(a.length, b.length); i++) {
		const x = a[i] ?? -1;
		const y = b[i] ?? -1;
		if (x !== y) return x > y;
	}
	return false;
}

/**
 * `opus`, `gpt-6-sol`, `xai/grok-4.7`, `grok:medium` → a usable model. Exact provider/id or
 * id wins; otherwise every usable model whose provider/id contains the word, newest version.
 */
export function resolveModelToken(token: string, models: readonly CatalogModel[], isUsable: (model: CatalogModel) => boolean): FusionPick | undefined {
	let word = token.trim();
	let thinking: Thinking | undefined;
	const colon = word.lastIndexOf(":");
	if (colon > 0 && colon < word.length - 1) {
		const level = resolveThinking(word.slice(colon + 1));
		if (level) {
			thinking = level;
			word = word.slice(0, colon);
		}
	}
	const needle = word.toLowerCase();
	if (!needle) return undefined;
	const usable = models.filter(isUsable);
	const full = (model: CatalogModel) => `${model.provider}/${model.id}`.toLowerCase();
	const exact = usable.filter((model) => full(model) === needle || model.id.toLowerCase() === needle);
	const hits = exact.length ? exact : usable.filter((model) => full(model).includes(needle));
	if (!hits.length) return undefined;
	const best = hits.reduce((a, b) => (newer(versionOf(b.id), versionOf(a.id)) ? b : a));
	return { model: `${best.provider}/${best.id}`, thinking };
}

/** Short slot name from the model id: claude-opus-5-5 → opus, gpt-6-sol → sol, grok-4.7 → grok. */
export function slotNameFor(model: string, taken: Set<string>): string {
	const id = model.split("/").pop()!.toLowerCase();
	const words = id.split(/[-_.:]/).filter((part) => /^[a-z]+$/.test(part) && !["claude", "gpt", "openai", "chat", "latest", "preview"].includes(part));
	const base = (words[0] ?? id.replace(/[^a-z0-9_-]/g, "")).slice(0, 14) || "agent";
	let name = base;
	for (let n = 2; taken.has(name); n++) name = `${base}${n}`;
	taken.add(name);
	return name;
}

/**
 * The N-slot stack. Prompts and skills carry over by role from the current stack (the
 * architect's to the new architect, the Main builder's to every builder), so the
 * contracts the operator configured keep applying.
 */
export function buildFusionStack(picks: readonly FusionPick[], base: ModelStack, defaultThinking: Thinking = "medium"): ModelStack {
	if (picks.length < MIN_AGENTS) throw new Error(`fusion needs at least ${MIN_AGENTS} agents`);
	const taken = new Set<string>();
	const used = new Set<HexColor>();
	const slots: ModelSlot[] = picks.map((pick, index) => {
		const architect = index === 0;
		const primary = index === 1;
		const from = architect ? base.architect : base.primaryBuilder;
		const name = slotNameFor(pick.model, taken);
		const color = (architect ? "#A78BFA" : SLOT_COLOR_PALETTE.find((candidate) => candidate !== "#A78BFA" && !used.has(candidate)) ?? SLOT_COLOR_PALETTE[index % SLOT_COLOR_PALETTE.length]) as HexColor;
		used.add(color);
		return {
			id: slotId(name),
			name,
			model: pick.model,
			thinking: pick.thinking ?? defaultThinking,
			color,
			architect,
			primary,
			systemPrompt: from.systemPrompt,
			systemPromptSource: from.systemPromptSource,
			appendSystemPrompts: [...from.appendSystemPrompts],
			skills: [...from.skills],
		};
	});
	const architect = slots[0]!;
	const primaryBuilder = slots[1]!;
	return { codename: `fusion-${slots.length}`, slots, architect, primaryBuilder, builders: slots.filter((slot) => !slot.architect) };
}
