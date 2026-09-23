import { describe, expect, test } from "bun:test";
import { catalogByProvider, loginHint, modelLabel, providerLabel, searchModels, type CatalogModel } from "../modules/model-browser.ts";

const models: CatalogModel[] = [
	{ id: "gpt-5.6-sol", name: "GPT-5.6 Sol", provider: "openai-codex", reasoning: true, contextWindow: 400_000 },
	{ id: "gpt-4o", name: "GPT-4o", provider: "openai", contextWindow: 128_000, cost: { input: 2.5, output: 10 } },
	{ id: "grok-4.6", name: "Grok 4.6", provider: "xai", reasoning: true, contextWindow: 1_000_000, cost: { input: 1.25, output: 2.5 } },
	{ id: "claude-opus-5-5", name: "Claude Opus 5.5", provider: "anthropic", reasoning: true },
	{ id: "grok-code", name: "Grok Code", provider: "openrouter" },
];
const loggedIn = new Set(["openai-codex", "xai"]);
const usable = (model: CatalogModel) => loggedIn.has(model.provider);

describe("model browser", () => {
	test("lists every provider, logged-in ones first, not only usable ones", () => {
		const entries = catalogByProvider(models, usable);
		expect(entries.map((entry) => entry.provider)).toEqual(["openai-codex", "xai", "anthropic", "openai", "openrouter"]);
		expect(entries.filter((entry) => entry.authed).length).toBe(2);
	});

	test("labels show login state and the exact unlock command", () => {
		const [codex, , anthropic] = catalogByProvider(models, usable);
		expect(providerLabel(codex!)).toBe("✓ openai-codex — 1 model");
		expect(providerLabel(anthropic!)).toBe("🔒 anthropic — 1 model · /login anthropic");
		expect(loginHint("anthropic")).toContain("/login anthropic");
	});

	test("model labels carry context, price, and reasoning", () => {
		expect(modelLabel(models[2]!, true)).toBe("✓ xai/grok-4.6 · Grok 4.6 · 1000k ctx · $1.25/$2.5 per M · reasoning");
		expect(modelLabel(models[1]!, false)).toBe("🔒 openai/gpt-4o · GPT-4o · 128k ctx · $2.5/$10 per M");
	});

	test("search spans every provider, all words must match, usable first", () => {
		expect(searchModels(models, "grok", usable).map((m) => `${m.provider}/${m.id}`)).toEqual(["xai/grok-4.6", "openrouter/grok-code"]);
		expect(searchModels(models, "gpt 5", usable).map((m) => m.id)).toEqual(["gpt-5.6-sol"]);
		expect(searchModels(models, "   ", usable)).toEqual([]);
	});
});
