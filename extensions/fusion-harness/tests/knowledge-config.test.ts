import { describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { detectSecondBrainVault, resolveKnowledgeConfig } from "../modules/knowledge-config.ts";

const dirs: string[] = [];
const cleanup = () => {
	while (dirs.length) rmSync(dirs.pop()!, { recursive: true, force: true });
};

describe("knowledge config", () => {
	test("off flag disables retrieval", () => {
		const cwd = mkdtempSync(join(tmpdir(), "fh-kb-cfg-"));
		dirs.push(cwd);
		const cfg = resolveKnowledgeConfig({ cwd, flag: "off", env: {}, homedir: cwd });
		expect(cfg.enabled).toBe(false);
		expect(cfg.roots).toEqual([]);
		expect(cfg.reasons.join(" ")).toContain("--fh-knowledge off");
		cleanup();
	});

	test("FH_KNOWLEDGE=off disables when flag unset", () => {
		const cwd = mkdtempSync(join(tmpdir(), "fh-kb-cfg-"));
		dirs.push(cwd);
		const cfg = resolveKnowledgeConfig({ cwd, env: { FH_KNOWLEDGE: "off" }, homedir: cwd });
		expect(cfg.enabled).toBe(false);
		cleanup();
	});

	test("explicit comma-separated roots, never moto", () => {
		const cwd = mkdtempSync(join(tmpdir(), "fh-kb-cfg-"));
		dirs.push(cwd);
		const docs = join(cwd, "docs");
		mkdirSync(docs);
		const cfg = resolveKnowledgeConfig({
			cwd,
			flag: `docs,/Users/moto/code/second-brain`,
			env: {},
			homedir: "/Users/evanmotovich",
		});
		expect(cfg.enabled).toBe(true);
		expect(cfg.roots).toEqual([realpathSync.native(docs)]);
		expect(cfg.reasons.join(" ")).toContain("obsolete moto");
		cleanup();
	});

	test("ai_docs is the project fallback", () => {
		const cwd = mkdtempSync(join(tmpdir(), "fh-kb-cfg-"));
		dirs.push(cwd);
		mkdirSync(join(cwd, "ai_docs"));
		const cfg = resolveKnowledgeConfig({ cwd, env: {}, homedir: cwd });
		expect(cfg.enabled).toBe(true);
		expect(cfg.roots).toEqual([realpathSync.native(join(cwd, "ai_docs"))]);
		expect(cfg.captureOptIn).toBe(false);
		cleanup();
	});

	test("SECOND_BRAIN_VAULT wiki and me win when present", () => {
		const home = mkdtempSync(join(tmpdir(), "fh-kb-home-"));
		dirs.push(home);
		const vault = join(home, "vault");
		mkdirSync(join(vault, "wiki"), { recursive: true });
		mkdirSync(join(vault, "me"), { recursive: true });
		const cwd = mkdtempSync(join(tmpdir(), "fh-kb-proj-"));
		dirs.push(cwd);
		mkdirSync(join(cwd, "ai_docs"));
		const cfg = resolveKnowledgeConfig({ cwd, env: { SECOND_BRAIN_VAULT: vault }, homedir: home });
		expect(cfg.vaultRoot).toBeDefined();
		expect(cfg.roots.some((r) => r.endsWith("wiki"))).toBe(true);
		expect(cfg.roots.some((r) => r.endsWith("me"))).toBe(true);
		expect(cfg.roots.some((r) => r.endsWith("ai_docs"))).toBe(true);
		cleanup();
	});

	test("detectSecondBrainVault ignores /Users/moto when that is not homedir", () => {
		expect(detectSecondBrainVault({ SECOND_BRAIN_VAULT: "/Users/moto/code/second-brain" }, "/Users/evanmotovich")).toBeUndefined();
	});

	test("capture opt-in via flag", () => {
		const cwd = mkdtempSync(join(tmpdir(), "fh-kb-cfg-"));
		dirs.push(cwd);
		mkdirSync(join(cwd, "ai_docs"));
		const cfg = resolveKnowledgeConfig({ cwd, captureFlag: "on", env: {}, homedir: cwd });
		expect(cfg.captureOptIn).toBe(true);
		cleanup();
	});
});
