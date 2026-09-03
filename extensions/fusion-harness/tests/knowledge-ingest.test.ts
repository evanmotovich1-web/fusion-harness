import { afterEach, describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { acquireVaultLock, captureVaultNote, extractVaultNote } from "../modules/knowledge-ingest.ts";

const dirs: string[] = [];
afterEach(() => {
	while (dirs.length) rmSync(dirs.pop()!, { recursive: true, force: true });
});

describe("knowledge ingest", () => {
	test("extracts an explicit Vault note", () => {
		expect(extractVaultNote("hello\n\n## Vault note\nWorkers cannot bash wiki.\n\n## Other\nskip")).toBe("Workers cannot bash wiki.");
	});

	test("rejects secrets, empty notes, and non-durable content", () => {
		const vault = mkdtempSync(join(tmpdir(), "fh-vault-"));
		dirs.push(vault);
		mkdirSync(join(vault, "wiki"), { recursive: true });
		expect(captureVaultNote({ enabled: true, vaultRoot: vault, runId: "r1", texts: ["## Vault note\nAPI_KEY=sk-abc123456"], sync: false }).status).toBe("rejected");
		expect(captureVaultNote({ enabled: true, vaultRoot: vault, runId: "r2", texts: ["## Vault note\nNone — no durable learning"], sync: false }).status).toBe("rejected");
		expect(captureVaultNote({ enabled: true, vaultRoot: vault, runId: "r3", texts: ["no heading here"], sync: false }).status).toBe("skipped");
		expect(readFileSync ? true : false).toBe(true);
		expect(() => readFileSync(join(vault, "wiki", "agent-learnings.md"), "utf8")).toThrow();
	});

	test("refuses trading/ and sessions/ destinations", () => {
		const vault = mkdtempSync(join(tmpdir(), "fh-vault-"));
		dirs.push(vault);
		const result = captureVaultNote({
			enabled: true,
			vaultRoot: vault,
			runId: "r4",
			texts: ["## Vault note\nA durable fact."],
			destRelative: "trading/insight.md",
			sync: false,
		});
		expect(result.status).toBe("rejected");
		expect(result.reason).toContain("trading");
	});

	test("idempotent append by run marker", () => {
		const vault = mkdtempSync(join(tmpdir(), "fh-vault-"));
		dirs.push(vault);
		mkdirSync(join(vault, "wiki"), { recursive: true });
		const first = captureVaultNote({ enabled: true, vaultRoot: vault, runId: "run-same", texts: ["## Vault note\nHarness injects evidence."], sync: false });
		const second = captureVaultNote({ enabled: true, vaultRoot: vault, runId: "run-same", texts: ["## Vault note\nHarness injects evidence."], sync: false });
		expect(first.status).toBe("captured");
		expect(second.status).toBe("captured");
		expect(second.reason).toContain("idempotent");
		const body = readFileSync(join(vault, "wiki", "agent-learnings.md"), "utf8");
		expect(body.split("<!-- agent-run:run-same -->").length - 1).toBe(1);
	});

	test("vault lock excludes a concurrent holder", () => {
		const vault = mkdtempSync(join(tmpdir(), "fh-vault-"));
		dirs.push(vault);
		const first = acquireVaultLock(vault, "first");
		expect(() => acquireVaultLock(vault, "second")).toThrow("already holds");
		first.release();
		const second = acquireVaultLock(vault, "second");
		second.release();
	});

	test("disabled capture reports disabled", () => {
		expect(captureVaultNote({ enabled: false, vaultRoot: "/tmp", runId: "x", texts: ["## Vault note\nhi"] }).status).toBe("disabled");
	});
});
