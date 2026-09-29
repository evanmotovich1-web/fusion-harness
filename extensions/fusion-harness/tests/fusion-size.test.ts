import { describe, expect, test } from "bun:test";
import { buildFusionStack, parseFusionArgs, resolveModelToken, slotNameFor } from "../modules/fusion-size.ts";
import type { CatalogModel } from "../modules/model-browser.ts";
import { synthesizeLegacyStack } from "../modules/model-stack.ts";

const models: CatalogModel[] = [
	{ id: "gpt-5.6-sol", name: "GPT-5.6 Sol", provider: "openai-codex" },
	{ id: "gpt-6-sol", name: "GPT-6 Sol", provider: "openai-codex" },
	{ id: "gpt-6-astra", name: "GPT-6 Astra", provider: "openai-codex" },
	{ id: "grok-4.6", name: "Grok 4.6", provider: "xai" },
	{ id: "grok-4.7", name: "Grok 4.7", provider: "xai" },
	{ id: "claude-opus-5-5", name: "Claude Opus 5.5", provider: "anthropic" },
	{ id: "grok-5", name: "Grok 5", provider: "openrouter" },
];
const loggedIn = new Set(["openai-codex", "xai"]);
const usable = (model: CatalogModel) => loggedIn.has(model.provider);

describe("/fusion arguments", () => {
	test("count alone opens the picker; models may be fewer than the count", () => {
		expect(parseFusionArgs("")).toEqual({ tokens: [] });
		expect(parseFusionArgs("3")).toEqual({ count: 3, tokens: [] });
		expect(parseFusionArgs("  4  sol grok ")).toEqual({ count: 4, tokens: ["sol", "grok"] });
	});

	test("rejects a missing count, out-of-range counts and too many models", () => {
		expect(parseFusionArgs("sol grok").error).toContain("number of agents");
		expect(parseFusionArgs("1").error).toContain("2-20");
		expect(parseFusionArgs("21").error).toContain("2-20");
		expect(parseFusionArgs("2 sol grok astra").error).toContain("3 models named for 2 agents");
	});
});

describe("model tokens", () => {
	test("short names resolve to the newest logged-in match", () => {
		expect(resolveModelToken("sol", models, usable)).toEqual({ model: "openai-codex/gpt-6-sol", thinking: undefined });
		expect(resolveModelToken("grok", models, usable)?.model).toBe("xai/grok-4.7"); // openrouter/grok-5 is not logged in
		expect(resolveModelToken("xai/grok-4.6", models, usable)?.model).toBe("xai/grok-4.6");
		expect(resolveModelToken("gpt-6-astra", models, usable)?.model).toBe("openai-codex/gpt-6-astra");
	});

	test("model:level sets thinking, including the short forms", () => {
		expect(resolveModelToken("grok:hi", models, usable)).toEqual({ model: "xai/grok-4.7", thinking: "high" });
		expect(resolveModelToken("astra:medium", models, usable)?.thinking).toBe("medium");
	});

	test("unknown or not-logged-in models do not resolve", () => {
		expect(resolveModelToken("opus", models, usable)).toBeUndefined();
		expect(resolveModelToken("nope", models, usable)).toBeUndefined();
		expect(resolveModelToken(":", models, usable)).toBeUndefined();
	});

	test("slot names are short, unique and valid", () => {
		const taken = new Set<string>();
		expect(slotNameFor("anthropic/claude-opus-5-5", taken)).toBe("opus");
		expect(slotNameFor("openai-codex/gpt-6-sol", taken)).toBe("sol");
		expect(slotNameFor("openai-codex/gpt-5.6-sol", taken)).toBe("sol2");
		expect(slotNameFor("xai/grok-4.7", taken)).toBe("grok");
	});
});

describe("the N-agent stack", () => {
	const base = synthesizeLegacyStack({
		architectModel: "anthropic/claude-opus-5-5",
		builderModel: "openai-codex/gpt-6-sol",
		architectThinking: "high",
		builderThinking: "medium",
		architectSystemPrompt: "ARCH",
		builderSystemPrompt: "BUILD",
	});

	test("first is the architect, second the Main builder, the rest builders", () => {
		const stack = buildFusionStack(
			[{ model: "xai/grok-4.7" }, { model: "openai-codex/gpt-6-sol", thinking: "high" }, { model: "openai-codex/gpt-6-astra" }],
			base,
			"low",
		);
		expect(stack.codename).toBe("fusion-3");
		expect(stack.slots.map((slot) => [slot.name, slot.architect, slot.primary, slot.thinking])).toEqual([
			["grok", true, false, "low"],
			["sol", false, true, "high"],
			["astra", false, false, "low"],
		]);
		expect(stack.architect.name).toBe("grok");
		expect(stack.primaryBuilder.name).toBe("sol");
		expect(stack.builders.map((slot) => slot.name)).toEqual(["sol", "astra"]);
	});

	test("prompts carry over by role and colors never repeat", () => {
		const stack = buildFusionStack(Array.from({ length: 6 }, () => ({ model: "xai/grok-4.7" })), base);
		expect(stack.architect.systemPrompt).toBe("ARCH");
		expect(stack.builders.every((slot) => slot.systemPrompt === "BUILD")).toBe(true);
		expect(stack.architect.color).toBe("#A78BFA");
		expect(new Set(stack.slots.map((slot) => slot.color)).size).toBe(6);
		expect(new Set(stack.slots.map((slot) => slot.id)).size).toBe(6);
	});

	test("fewer than two agents is refused", () => {
		expect(() => buildFusionStack([{ model: "xai/grok-4.7" }], base)).toThrow();
	});
});
