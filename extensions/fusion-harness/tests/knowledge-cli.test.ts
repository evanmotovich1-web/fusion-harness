import { describe, expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { KNOWLEDGE_CLI_BRIEF_JSON_KEYS, KNOWLEDGE_CLI_JSON_KEYS, runKnowledgeCli } from "../modules/knowledge-cli.ts";
import { KNOWLEDGE_BEGIN, KNOWLEDGE_END, retrieveKnowledge } from "../modules/knowledge-base.ts";
import { resolveKnowledgeConfig } from "../modules/knowledge-config.ts";

const root = join(import.meta.dir, "..");
const fixture = join(import.meta.dir, "fixtures", "knowledge");
const shim = join(root, "bin", "fh-knowledge");

// Explicit root + injected env/homedir keep these tests machine-independent:
// no vault auto-detection, no semantic index, lexical retrieval only.
const opts = { env: {}, homedir: fixture };
const base = ["--cwd", fixture, "--fh-knowledge", fixture];

describe("fh-knowledge CLI", () => {
	test("status --json parses with the frozen stable keys", () => {
		const result = runKnowledgeCli(["status", "--json", ...base], opts);
		expect(result.exitCode).toBe(0);
		expect(result.stderr).toBe("");
		const parsed = JSON.parse(result.stdout);
		expect(Object.keys(parsed)).toEqual([...KNOWLEDGE_CLI_JSON_KEYS]);
		expect(parsed.command).toBe("status");
		expect(Array.isArray(parsed.roots)).toBe(true);
		expect(Array.isArray(parsed.chunks)).toBe(true);
		expect(parsed.vaultRoot).toBeNull();
	});

	test("search --json parses with the same stable keys", () => {
		const result = runKnowledgeCli(["search", "fusion worker tools", "--json", ...base], opts);
		expect(result.exitCode).toBe(0);
		const parsed = JSON.parse(result.stdout);
		expect(Object.keys(parsed)).toEqual([...KNOWLEDGE_CLI_JSON_KEYS]);
		expect(parsed.command).toBe("search");
		expect(parsed.query).toBe("fusion worker tools");
		expect(parsed.status).toBe("passed");
		expect(parsed.hits).toBeGreaterThan(0);
		expect(parsed.chunks[0].path).toContain("conflict-");
	});

	test("--max-bytes caps the retrieved evidence, and the JSON reports it", () => {
		const wide = runKnowledgeCli(["search", "fusion worker tools", "--json", "--max-bytes", "8000", ...base], opts);
		const narrow = runKnowledgeCli(["search", "fusion worker tools", "--json", "--max-bytes", "200", ...base], opts);
		expect(wide.exitCode).toBe(0);
		expect(narrow.exitCode).toBe(0);
		const wideJson = JSON.parse(wide.stdout);
		const narrowJson = JSON.parse(narrow.stdout);
		expect(narrowJson.maxBytes).toBe(200);
		const narrowTextBytes = narrowJson.chunks.reduce((sum: number, chunk: { bytes: number }) => sum + chunk.bytes, 0);
		expect(narrowTextBytes).toBe(narrowJson.bytes);
		expect(narrowJson.bytes).toBeLessThanOrEqual(200);
		expect(narrowJson.bytes).toBeLessThanOrEqual(wideJson.bytes);
	});

	test("exit 0 on wiki miss", () => {
		const result = runKnowledgeCli(["search", "zzzz-no-such-term-xyz", ...base], opts);
		expect(result.exitCode).toBe(0);
		expect(result.stdout).toContain("wiki miss");
	});

	test("exit 0 on disabled", () => {
		const status = runKnowledgeCli(["status", "--json", "--fh-knowledge", "off", "--cwd", fixture], opts);
		expect(status.exitCode).toBe(0);
		const parsed = JSON.parse(status.stdout);
		expect(parsed.status).toBe("disabled");
		expect(parsed.enabled).toBe(false);
		expect(parsed.hits).toBe(0);
		const search = runKnowledgeCli(["search", "anything", "--fh-knowledge", "off", "--cwd", fixture], opts);
		expect(search.exitCode).toBe(0);
	});

	test("--markdown emits the untrusted-evidence delimiters", () => {
		const result = runKnowledgeCli(["search", "fusion worker tools", "--markdown", ...base], opts);
		expect(result.exitCode).toBe(0);
		expect(result.stdout).toContain(KNOWLEDGE_BEGIN);
		expect(result.stdout).toContain(KNOWLEDGE_END);
	});

	test("relative --cwd and relative --fh-knowledge roots resolve against the caller cwd", () => {
		const repo = join(import.meta.dir, "..", "..", "..");
		const rel = join("extensions", "fusion-harness", "tests", "fixtures", "knowledge");
		const result = runKnowledgeCli(["status", "--json", "--cwd", ".", "--fh-knowledge", rel], { cwd: repo, env: {}, homedir: fixture });
		expect(result.exitCode).toBe(0);
		const parsed = JSON.parse(result.stdout);
		expect(parsed.enabled).toBe(true);
		expect(["passed", "miss"]).toContain(parsed.status);
		expect(parsed.roots.length).toBe(1);
	});

	test("brief --json carries both briefHash and packetHash with its own frozen keys", () => {
		const result = runKnowledgeCli(["brief", "fusion worker tools", "--json", ...base], opts);
		expect(result.exitCode).toBe(0);
		const parsed = JSON.parse(result.stdout);
		expect(Object.keys(parsed)).toEqual([...KNOWLEDGE_CLI_BRIEF_JSON_KEYS]);
		expect(parsed.command).toBe("brief");
		expect(parsed.status).toBe("passed");
		expect(parsed.packetHash).toMatch(/^[0-9a-f]{64}$/);
		expect(parsed.briefHash).toMatch(/^[0-9a-f]{64}$/);
		expect(parsed.packetHash).not.toBe(parsed.briefHash);
		expect(Array.isArray(parsed.chunks)).toBe(true);
		expect(parsed.briefMarkdown).toContain("KNOWLEDGE BRIEF");
		expect(parsed.sections.map((section: { id: string }) => section.id)).toEqual([
			"decisions",
			"constraints",
			"hooks",
			"do-not-repeat",
		]);
	});

	test("brief text output prints the distilled brief, then the untrusted-evidence packet", () => {
		const result = runKnowledgeCli(["brief", "fusion worker tools", ...base], opts);
		expect(result.exitCode).toBe(0);
		expect(result.stdout).toContain("KNOWLEDGE BRIEF");
		expect(result.stdout).toContain(KNOWLEDGE_BEGIN);
		expect(result.stdout).toContain(KNOWLEDGE_END);
		// Brief section headings precede the packet's own hit heading.
		expect(result.stdout.indexOf("## Current decisions")).toBeLessThan(result.stdout.indexOf("### [1]"));
	});

	test("brief honors --max-bytes for both the brief and the packet", () => {
		const result = runKnowledgeCli(["brief", "fusion worker tools", "--json", "--max-bytes", "600", ...base], opts);
		expect(result.exitCode).toBe(0);
		const parsed = JSON.parse(result.stdout);
		expect(parsed.maxBytes).toBe(600);
		expect(parsed.briefBytes).toBeLessThanOrEqual(600);
		expect(parsed.packetBytes).toBeLessThanOrEqual(600);
	});

	test("exit 0 on a brief wiki miss and on brief disabled", () => {
		const miss = runKnowledgeCli(["brief", "zzzz-no-such-term-xyz", ...base], opts);
		expect(miss.exitCode).toBe(0);
		expect(miss.stdout).toContain("wiki miss");
		const off = runKnowledgeCli(["brief", "anything", "--fh-knowledge", "off", "--cwd", fixture], opts);
		expect(off.exitCode).toBe(0);
	});

	test("CLI search and the host retriever produce an identical packet hash", () => {
		const query = "fusion worker tools";
		// Same config resolution the host uses (cmd-knowledge.ts: h.knowledgeConfig(ctx.cwd)).
		const config = resolveKnowledgeConfig({ cwd: fixture, flag: fixture, env: {}, homedir: fixture });
		const direct = retrieveKnowledge({ query, cwd: fixture, config });
		const cli = runKnowledgeCli(["search", query, "--json", ...base], opts);
		expect(cli.exitCode).toBe(0);
		const parsed = JSON.parse(cli.stdout);
		expect(parsed.hash).toBe(direct.hash);
		// The host command reaches the retriever through this exact call shape.
		const cmd = readFileSync(join(root, "modules", "cmd-knowledge.ts"), "utf8");
		expect(cmd).toContain("retrieveKnowledge({ query, cwd: ctx.cwd, config })");
	});

	test("nonzero only on a usage error", () => {
		const unknown = runKnowledgeCli(["bogus"], opts);
		expect(unknown.exitCode).toBe(2);
		expect(unknown.stderr).toContain("unknown subcommand");
		const missing = runKnowledgeCli(["search", "x", "--cwd"], opts);
		expect(missing.exitCode).toBe(2);
		expect(missing.stderr).toContain("--cwd needs a value");
		const badBytes = runKnowledgeCli(["status", "--max-bytes", "zero", ...base], opts);
		expect(badBytes.exitCode).toBe(2);
	});

	test("bin/fh-knowledge shim runs status --json and exits 0", () => {
		const proc = spawnSync(process.execPath, [shim, "status", "--json", ...base], {
			encoding: "utf8",
			timeout: 60_000,
		});
		expect(proc.status).toBe(0);
		const parsed = JSON.parse(proc.stdout);
		expect(parsed.command).toBe("status");
		expect(Array.isArray(parsed.roots)).toBe(true);
	});

	test("no pi import in the module or the shim", () => {
		for (const file of [join(root, "modules", "knowledge-cli.ts"), shim]) {
			const source = readFileSync(file, "utf8");
			expect(source).not.toContain("@earendil-works/pi-coding-agent");
			expect(source).not.toMatch(/from\s+["']pi["']/);
		}
	});
});
