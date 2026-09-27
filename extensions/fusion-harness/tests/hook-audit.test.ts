import { afterAll, describe, expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync, utimesSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
	CONTRACT_BEGIN,
	CONTRACT_END,
	DEFAULT_KNOWN_GATES,
	HOOK_DOCTOR_JSON_KEYS,
	auditContract,
	auditHookSurfaces,
	auditHooks,
	buildHookReport,
	classifyCodexPlugin,
	classifyPiExtension,
	envVarsReferenced,
	envVarsUnprovided,
	isKnownGate,
	probeHook,
	resolveKnownGates,
	type HookSurface,
} from "../modules/hook-audit.ts";
import { parseDoctorArgs, probeCommandMatrix } from "../tools/hooks-doctor.ts";

const fixtureHome = join(import.meta.dir, "fixtures", "hooks");
const uiOnlyHome = join(import.meta.dir, "fixtures", "hooks-ui-only");
const doctorPath = join(import.meta.dir, "..", "tools", "hooks-doctor.ts");
const repoRoot = join(import.meta.dir, "..", "..", "..");

const tempDirs: string[] = [];
function tempDir(prefix: string): string {
	const dir = mkdtempSync(join(tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}
afterAll(() => {
	for (const dir of tempDirs) rmSync(dir, { recursive: true, force: true });
});

// Bun writes its transpiler cache under $HOME/Library/Caches/bun. The doctor/probe spawns
// below run with HOME=<fixtureHome>, so without this redirect bun recreates Library/ inside
// the fixture tree on every run and pollutes the working tree.
const cacheDir = tempDir("fh-hook-audit-cache-");
const spawnEnv = { ...process.env, HOME: fixtureHome, BUN_INSTALL_CACHE_DIR: cacheDir, XDG_CACHE_HOME: cacheDir };

const CONTRACT_BLOCK = `${CONTRACT_BEGIN}\n# GLOBAL KNOWLEDGE CONTRACT\n\n- fail-open only; never block the task\n${CONTRACT_END}`;
const sha = (text: string): string => createHash("sha256").update(text, "utf8").digest("hex");

function writeManifest(manifestDir: string, entries: Array<{ id: string; path: string }>, block = CONTRACT_BLOCK): void {
	mkdirSync(manifestDir, { recursive: true });
	writeFileSync(
		join(manifestDir, "manifest.json"),
		JSON.stringify(
			{
				version: 1,
				contractHash: sha(block),
				entries: entries.map((entry) => ({ id: entry.id, path: entry.path, originalHash: "", installedHash: "", insertedText: "", blockHash: sha(block) })),
			},
			null,
			2,
		),
		"utf8",
	);
}

function byId(surfaces: HookSurface[]): Map<string, HookSurface> {
	return new Map(surfaces.map((surface) => [surface.id, surface]));
}

function fixture(command: string, id = "fixture"): HookSurface {
	return {
		id,
		kind: "claude-hook",
		source: "fixture",
		event: "SessionStart",
		command,
		path: null,
		verdict: "fail-open",
		blocking: false,
		reason: "fixture",
		probe: true,
	};
}

function runDoctor(args: string[]) {
	return spawnSync("bun", [doctorPath, ...args], {
		cwd: repoRoot,
		encoding: "utf8",
		timeout: 20_000,
		env: spawnEnv,
	});
}

describe("hook-audit enumeration", () => {
	test("enumerates every surface kind and never throws on a missing home", () => {
		const surfaces = auditHooks({ home: fixtureHome });
		const kinds = new Set(surfaces.map((surface) => surface.kind));
		expect(kinds).toEqual(new Set(["pi-extension", "pi-package", "claude-hook", "codex-hook", "hermes-hook", "codex-plugin-hook"]));
		expect(() => auditHooks({ home: join(fixtureHome, "does-not-exist") })).not.toThrow();
		expect(auditHooks({ home: join(fixtureHome, "does-not-exist") })).toEqual([]);
	});

	test("pi permission-gate is can-block; vault-semantic is fail-open and never probed", () => {
		const map = byId(auditHooks({ home: fixtureHome }));
		const gate = map.get("pi:extension:permission-gate.ts");
		expect(gate?.verdict).toBe("can-block");
		expect(gate?.blocking).toBe(true);
		expect(gate?.probe).toBe(false);
		expect(gate?.reason).toContain("hasUI");

		const vault = map.get("pi:extension:vault-semantic.ts");
		expect(vault?.verdict).toBe("fail-open");
		expect(vault?.blocking).toBe(false);
		expect(vault?.event).toBe("before_agent_start");
		expect(vault?.probe).toBe(false);
	});

	test("a UI-gated block (TUI decline only) is fail-open, not can-block", () => {
		// Same tool_call shape as the real permission-gate, but the only block follows an
		// interactive ctx.ui prompt, so a headless run can never be stopped by it.
		const map = byId(auditHooks({ home: uiOnlyHome }));
		const gate = map.get("pi:extension:permission-gate.ts");
		expect(gate?.verdict).toBe("fail-open");
		expect(gate?.blocking).toBe(false);
		expect(gate?.reason).toContain("UI-gated");
	});

	test("classifyPiExtension distinguishes headless, UI-gated, and unconditional blocks", () => {
		const headless = classifyPiExtension("if (!ctx.hasUI) { return { block: true, reason: 'no ui' }; }", "gate.ts");
		expect(headless.verdict).toBe("can-block");
		expect(headless.reason).toContain("headless");

		const uiGated = classifyPiExtension(
			"const c = await ctx.ui.select('Allow?', ['Yes','No']);\nif (c !== 'Yes') return { block: true, reason: 'Blocked by user' };",
			"gate.ts",
		);
		expect(uiGated.verdict).toBe("fail-open");
		expect(uiGated.reason).toContain("UI-gated");

		const unconditional = classifyPiExtension("if (dangerous) return { block: true, reason: 'nope' };", "gate.ts");
		expect(unconditional.verdict).toBe("can-block");
		expect(unconditional.reason).toContain("unconditionally");

		// plan-mode shape: a file full of ctx.ui. calls but a block far from any prompt is
		// still a real block. Co-presence must not downgrade it (proximity regression guard).
		const farFromPrompt = `ctx.ui.notify('status', 'info');\n${"// padding to push the block past the UI proximity window\n".repeat(6)}if (!isSafeCommand(command)) {\n  return { block: true, reason: 'Plan mode: command blocked' };\n}`;
		expect(classifyPiExtension(farFromPrompt, "plan-mode.ts").verdict).toBe("can-block");
	});

	test("claude Stop block script is can-block and static-only; injection events are probeable", () => {
		const map = byId(auditHooks({ home: fixtureHome }));
		const stop = map.get("claude:Stop:0:0");
		expect(stop?.verdict).toBe("can-block");
		expect(stop?.blocking).toBe(true);
		expect(stop?.probe).toBe(false);
		expect(stop?.path).toContain("stop-block.sh");

		expect(map.get("claude:SessionStart:0:0")?.probe).toBe(true);
		expect(map.get("claude:UserPromptSubmit:0:0")?.probe).toBe(true);
	});

	test("codex surfaces carry trusted-hash status without claiming a match", () => {
		const map = byId(auditHooks({ home: fixtureHome }));
		expect(map.get("codex:SessionStart:0:0")?.trust?.status).toBe("present");
		expect(map.get("codex:SessionStart:0:0")?.trust?.storedHash).toContain("sha256:");
		expect(map.get("codex:SessionStart:1:0")?.trust?.status).toBe("missing");
		expect(map.get("codex:SessionStart:1:0")?.reason).toContain("skips");
		expect(map.get("codex:SessionStart:0:0")?.verdict).toBe("fail-open");
	});

	test("hermes pre_llm_call is fail-open and reported allowlisted", () => {
		const map = byId(auditHooks({ home: fixtureHome }));
		const hermes = map.get("hermes:pre_llm_call:0");
		expect(hermes?.verdict).toBe("fail-open");
		expect(hermes?.blocking).toBe(false);
		expect(hermes?.meta?.allowlisted).toBe(true);
		expect(hermes?.probe).toBe(true);
	});
});

describe("hook probing", () => {
	test("exit 1, hang and throw are each reported fail-open without touching process.exitCode", () => {
		const before = process.exitCode;
		const exited = probeHook(fixture('node -e "process.exit(1)"', "exit1"), { timeoutMs: 3_000, env: spawnEnv });
		const hung = probeHook(fixture('node -e "setTimeout(()=>{}, 60000)"', "hang"), { timeoutMs: 300, env: spawnEnv });
		const thrown = probeHook(fixture('node -e "throw new Error(\'boom\')"', "throw"), { timeoutMs: 3_000, env: spawnEnv });

		expect(exited.status).toBe("nonzero");
		expect(exited.exitCode).toBe(1);
		expect(exited.failOpen).toBe(true);

		expect(hung.status).toBe("timeout");
		expect(hung.failOpen).toBe(true);
		expect(hung.durationMs).toBeLessThan(10_000);

		expect(thrown.status).toBe("nonzero");
		expect(thrown.failOpen).toBe(true);

		expect(process.exitCode).toBe(before);
	});

	test("a non-probe surface is skipped and still fail-open", () => {
		const surface = { ...fixture('node -e "process.exit(2)"'), probe: false };
		const probe = probeHook(surface, { timeoutMs: 300, env: spawnEnv });
		expect(probe.status).toBe("skipped");
		expect(probe.failOpen).toBe(true);
		expect(probe.exitCode).toBeNull();
	});

	test("buildHookReport is not ok when a can-block surface exists, but does not throw", () => {
		const surfaces = auditHooks({ home: fixtureHome });
		const report = buildHookReport(surfaces, [], { home: fixtureHome, timeoutMs: 400 });
		expect(report.ok).toBe(false);
		expect(report.canBlock).toContain("pi:extension:permission-gate.ts");
		expect(report.canBlock).toContain("claude:Stop:0:0");
		expect(report.failOpen).toContain("claude:SessionStart:0:0");
	});
});

describe("hooks-doctor", () => {
	test("--json exits 0, emits the frozen keys, and reports the failing fixtures fail-open", () => {
		const run = runDoctor(["--json", "--home", fixtureHome, "--timeout", "300"]);
		expect(run.status).toBe(0);
		const report = JSON.parse(run.stdout);
		expect(Object.keys(report)).toEqual([...HOOK_DOCTOR_JSON_KEYS]);
		expect(report.ok).toBe(false);
		expect(report.canBlock).toContain("pi:extension:permission-gate.ts");
		expect(report.canBlock).toContain("claude:Stop:0:0");
		expect(run.stderr).toContain("CAN-BLOCK");

		const probes = new Map<string, any>(report.probes.map((probe: any) => [probe.id, probe]));
		expect(probes.get("claude:SessionStart:0:0").failOpen).toBe(true);
		expect(probes.get("claude:SessionStart:0:0").status).toBe("nonzero");
		expect(probes.get("claude:SessionStart:1:0").failOpen).toBe(true);
		expect(probes.get("claude:UserPromptSubmit:0:0").status).toBe("timeout");
		expect(probes.get("claude:UserPromptSubmit:0:0").failOpen).toBe(true);
	});

	test("--no-probe exits 0 and executes nothing", () => {
		const run = runDoctor(["--json", "--home", fixtureHome, "--no-probe"]);
		expect(run.status).toBe(0);
		const report = JSON.parse(run.stdout);
		expect(report.probes).toEqual([]);
		expect(report.scanned).toBeGreaterThan(0);
	});

	test("exits 0 for a nonexistent home and for --help", () => {
		const missing = runDoctor(["--json", "--home", join(fixtureHome, "nope"), "--no-probe"]);
		expect(missing.status).toBe(0);
		const parsed = JSON.parse(missing.stdout);
		expect(parsed.canBlock).toEqual([]);
		expect(parsed.checks.contractBlock).toBe("not-installed");
		expect(parsed.ok).toBe(true);

		const help = runDoctor(["--help"]);
		expect(help.status).toBe(0);
		expect(help.stdout).toContain("hooks-doctor");
		expect(help.stdout).toContain("--no-probe");
	});
});

describe("knowledge surfaces and contract verdict", () => {
	test("audits knowledge-inject and knowledge-guard as fail-open", () => {
		const audit = auditHookSurfaces({ home: fixtureHome });
		const inject = audit.surfaces.find((surface) => surface.id === "knowledge:module:knowledge-inject");
		const guard = audit.surfaces.find((surface) => surface.id === "knowledge:module:knowledge-guard");
		expect(inject?.kind).toBe("knowledge-module");
		expect(inject?.verdict).toBe("fail-open");
		expect(guard?.verdict).toBe("fail-open");
		expect(audit.contract.status).toBe("not-installed");
	});

	test("a can-block knowledge module is reported can-block", () => {
		const home = tempDir("fh-hook-audit-modhome-");
		const modulesDir = tempDir("fh-hook-audit-mods-");
		writeFileSync(join(modulesDir, "knowledge-inject.ts"), "export function h(ctx:any){ if(!ctx.hasUI) return { block: true }; return undefined; }\n", "utf8");
		writeFileSync(join(modulesDir, "knowledge-guard.ts"), "export async function safeKnowledge(fn:any){ try { return await fn(); } catch { return undefined; } }\n", "utf8");
		const audit = auditHookSurfaces({ home, modulesDir });
		expect(audit.surfaces.find((surface) => surface.id === "knowledge:module:knowledge-inject")?.verdict).toBe("can-block");
		expect(audit.surfaces.find((surface) => surface.id === "knowledge:module:knowledge-guard")?.verdict).toBe("fail-open");

		const run = spawnSync("bun", [doctorPath, "--json", "--home", home, "--modules-dir", modulesDir, "--no-probe"], {
			cwd: repoRoot,
			encoding: "utf8",
			timeout: 20_000,
			env: spawnEnv,
		});
		expect(run.status).toBe(0);
		const report = JSON.parse(run.stdout);
		expect(report.checks.knowledgeInject).toBe("can-block");
		expect(report.ok).toBe(false);
		expect(run.stderr).toContain("knowledge-inject is can-block");
	});

	test("contract block is current only when it appears exactly once and matches the hash", () => {
		const state = tempDir("fh-hook-audit-contract-");
		const file = join(state, "AGENTS.md");
		writeManifest(state, [{ id: "root", path: file }]);

		writeFileSync(file, `${CONTRACT_BLOCK}\n`, "utf8");
		const current = auditContract(state);
		expect(current.status).toBe("current");
		expect(current.installedByUs).toBe(true);
		expect(current.surfaces[0]?.blockMatches).toBe(true);
		expect(current.stopGate).toBe("none");

		writeFileSync(file, `${CONTRACT_BLOCK}\n${CONTRACT_BLOCK}\n`, "utf8");
		expect(auditContract(state).status).toBe("duplicate");

		writeFileSync(file, "no marker here\n", "utf8");
		expect(auditContract(state).status).toBe("missing");

		writeFileSync(file, `${CONTRACT_BEGIN}\n# drifted\n${CONTRACT_END}\n`, "utf8");
		expect(auditContract(state).status).toBe("stale");
	});

	test("a hook config in our manifest is reported as a Stop gate", () => {
		const state = tempDir("fh-hook-audit-stopgate-");
		const file = join(state, "settings.json");
		writeFileSync(file, `${CONTRACT_BLOCK}\n`, "utf8");
		writeManifest(state, [{ id: "bad", path: file }]);
		expect(auditContract(state).stopGate).toBe("present");
	});

	test("doctor reports a duplicate contract as NOT OK and still exits 0", () => {
		const home = tempDir("fh-hook-audit-dup-");
		const file = join(home, "AGENTS.md");
		writeFileSync(file, `${CONTRACT_BLOCK}\n${CONTRACT_BLOCK}\n`, "utf8");
		writeManifest(join(home, ".fh-knowledge"), [{ id: "root", path: file }]);
		const run = runDoctor(["--json", "--home", home, "--no-probe"]);
		expect(run.status).toBe(0);
		const report = JSON.parse(run.stdout);
		expect(report.checks.contractBlock).toBe("duplicate");
		expect(report.ok).toBe(false);
		expect(report.checks.findings.join(" ")).toContain("more than once");
		expect(run.stderr).toContain("CAN-BLOCK or drift");
	});
});

describe("codex trusted hashes", () => {
	function codexHome(): string {
		const home = tempDir("fh-hook-audit-codex-");
		mkdirSync(join(home, ".codex"), { recursive: true });
		writeFileSync(
			join(home, ".codex", "hooks.json"),
			JSON.stringify({ hooks: { SessionStart: [{ hooks: [{ type: "command", command: "vault-semantic hook --agent codex --event start", timeout: 10 }] }] } }),
			"utf8",
		);
		writeFileSync(
			join(home, ".codex", "config.toml"),
			'[hooks.state]\n[hooks.state."/fixture/hooks.json:session_start:0:0"]\ntrusted_hash = "sha256:abc"\n',
			"utf8",
		);
		return home;
	}

	test("flags hooks.json edited after the trust record and passes when config.toml is newer", () => {
		const home = codexHome();
		const now = Date.now() / 1000;

		utimesSync(join(home, ".codex", "hooks.json"), now, now);
		utimesSync(join(home, ".codex", "config.toml"), now - 100, now - 100);
		const stale = auditHooks({ home }).find((surface) => surface.id === "codex:SessionStart:0:0");
		expect(stale?.trust?.verification).toBe("stale-suspect");
		expect(stale?.reason).toContain("edited after the trusted_hash");

		utimesSync(join(home, ".codex", "hooks.json"), now - 100, now - 100);
		utimesSync(join(home, ".codex", "config.toml"), now, now);
		const fresh = auditHooks({ home }).find((surface) => surface.id === "codex:SessionStart:0:0");
		expect(fresh?.trust?.verification).toBe("present");
		expect(fresh?.trust?.status).toBe("present");
	});

	test("buildHookReport surfaces a stale codex trust as warn", () => {
		const home = codexHome();
		const now = Date.now() / 1000;
		utimesSync(join(home, ".codex", "hooks.json"), now, now);
		utimesSync(join(home, ".codex", "config.toml"), now - 100, now - 100);
		const surfaces = auditHooks({ home });
		const report = buildHookReport(surfaces, [], { home, contract: auditContract(join(home, ".fh-knowledge")) });
		expect(report.checks.codexTrust).toBe("warn");
		expect(report.ok).toBe(false);
		expect(report.checks.findings.join(" ")).toContain("re-trust required");
	});
});

describe("fixture hygiene", () => {
	test("the hooks fixture root holds only the intended surfaces and no bun cache", () => {
		expect(readdirSync(fixtureHome).sort()).toEqual([".claude", ".codex", ".gitignore", ".hermes", ".pi"]);
		expect(existsSync(join(fixtureHome, "Library"))).toBe(false);
	});
});

describe("codex plugin hook coverage", () => {
	test("enumerates enabled plugins from config.toml and classifies a Stop gate as can-block", () => {
		const surfaces = auditHooks({ home: fixtureHome });
		const plugin = surfaces.filter((surface) => surface.kind === "codex-plugin-hook");
		const base = surfaces.filter((surface) => surface.kind === "codex-hook");

		// The point of the fix: base hooks.json is 3 entries; plugins add more.
		expect(base.length).toBe(3);
		expect(plugin.length).toBeGreaterThanOrEqual(3);
		expect(base.length + plugin.length).toBeGreaterThan(3);

		const stop = plugin.find((surface) => surface.id === "codex-plugin:fixture-plugin@fixture-marketplace:Stop:0:0");
		expect(stop?.verdict).toBe("can-block");
		expect(stop?.blocking).toBe(true);
		expect(stop?.probe).toBe(false);
		expect(stop?.trust?.status).toBe("present");
		expect(stop?.source).toContain("fixture-plugin");

		const mcp = plugin.find((surface) => surface.id === "codex-plugin:browser-plugin@fixture-marketplace:Stop:0:0");
		expect(mcp?.verdict).toBe("can-block");
		expect(mcp?.command).toBeNull();
		expect(mcp?.meta?.type).toBe("mcp_tool");
		expect(mcp?.trust?.status).toBe("present");

		const start = plugin.find((surface) => surface.id === "codex-plugin:fixture-plugin@fixture-marketplace:SessionStart:0:0");
		expect(start?.verdict).toBe("fail-open");
		expect(start?.probe).toBe(true);

		// enabled=false plugins and their trust keys are not enumerated.
		expect(surfaces.some((surface) => surface.id.includes("disabled-plugin"))).toBe(false);
	});

	test("a Stop that demonstrably fails open is fail-open; a bare Stop is can-block", () => {
		expect(classifyCodexPlugin("Stop", "command", "node ./gate.mjs", "").verdict).toBe("can-block");
		expect(classifyCodexPlugin("Stop", "command", "node ./gate.mjs", "try { main(); } catch { process.exitCode = 0; }").verdict).toBe("fail-open");
		expect(classifyCodexPlugin("SessionEnd", "mcp_tool", null, "").verdict).toBe("can-block");
		expect(classifyCodexPlugin("SessionStart", "command", "node ./ctx.mjs", "").verdict).toBe("fail-open");
	});

	test("the doctor reports plugin Stop gates as can-block and still exits 0", () => {
		const run = runDoctor(["--json", "--home", fixtureHome, "--no-probe"]);
		expect(run.status).toBe(0);
		const report = JSON.parse(run.stdout);
		expect(report.checks.codexPluginHooks).toBeGreaterThanOrEqual(3);
		expect(report.canBlock).toContain("codex-plugin:fixture-plugin@fixture-marketplace:Stop:0:0");
		expect(report.canBlock).toContain("codex-plugin:browser-plugin@fixture-marketplace:Stop:0:0");
		expect(report.checks.findings.join(" ")).toContain("codex plugin Stop/SessionEnd gate(s)");
	});
});

describe("host-provided environment lint", () => {
	test("flags a variable the host does not provide and ignores provided / non-namespaced ones", () => {
		// The reproduced defect: Codex injects CLAUDE_PLUGIN_ROOT but not CLAUDE_PROJECT_DIR.
		expect(envVarsUnprovided(`node "$CLAUDE_PROJECT_DIR/.claude/hooks/distill-check.cjs"`, "codex")).toEqual(["CLAUDE_PROJECT_DIR"]);
		expect(envVarsUnprovided(`node "\${CLAUDE_PLUGIN_ROOT}/scripts/context.mjs"`, "codex")).toEqual([]);
		expect(envVarsUnprovided(`node "$CLAUDE_PROJECT_DIR/x.mjs"`, "claude")).toEqual([]);
		expect(envVarsUnprovided(`node "$HOME/x.mjs" "$PWD/y.mjs"`, "codex")).toEqual([]);
		expect(envVarsUnprovided(`CLAUDE_PROJECT_DIR=/w node "$CLAUDE_PROJECT_DIR/x.mjs"`, "codex")).toEqual([]);
		expect(envVarsUnprovided(null, "codex")).toEqual([]);
		expect(envVarsReferenced(`node "\${CLAUDE_PLUGIN_ROOT}/a.mjs" "$HOME/b"`)).toEqual(["CLAUDE_PLUGIN_ROOT", "HOME"]);
	});

	test("the env-plugin fixture flags its Stop hook and leaves the SessionStart clean", () => {
		const surfaces = auditHooks({ home: fixtureHome });
		const stop = surfaces.find((surface) => surface.id === "codex-plugin:env-plugin@fixture-marketplace:Stop:0:0");
		const start = surfaces.find((surface) => surface.id === "codex-plugin:env-plugin@fixture-marketplace:SessionStart:0:0");
		expect(stop?.meta?.unprovidedVars).toBe("CLAUDE_PROJECT_DIR");
		expect(start?.meta?.unprovidedVars).toBeUndefined();
	});

	test("buildHookReport raises a host-unprovided variable as an unexpected finding", () => {
		const report = buildHookReport(auditHooks({ home: fixtureHome }), [], { home: fixtureHome, timeoutMs: 400 });
		expect(report.ok).toBe(false);
		expect(report.checks.findings.join(" ")).toContain("host-unprovided variable");
		expect(report.checks.findings.join(" ")).toContain("codex-plugin:env-plugin@fixture-marketplace:Stop:0:0 (CLAUDE_PROJECT_DIR)");
	});
});

describe("known-gates allowlist", () => {
	test("the default list holds the two deliberate guards and matches exact ids or prefixes", () => {
		expect(DEFAULT_KNOWN_GATES).toContain("pi:extension:plan-mode");
		expect(DEFAULT_KNOWN_GATES).toContain("claude:PreToolUse:1:0");
		expect(isKnownGate("claude:PreToolUse:1:0", DEFAULT_KNOWN_GATES)).toBe(true);
		expect(isKnownGate("claude:PreToolUse:2:0", DEFAULT_KNOWN_GATES)).toBe(false);
		expect(isKnownGate("claude:PreToolUse:1:0", ["claude:PreToolUse:"])).toBe(true);
		expect(isKnownGate("pi:extension:plan-mode-extra", ["pi:extension:plan-mode"])).toBe(false);
		expect(resolveKnownGates()).toContain("pi:extension:plan-mode");
		expect(resolveKnownGates(["custom:gate:0:0"])).toContain("custom:gate:0:0");
	});

	test("an accepted gate leaves the unexpected findings but stays in the raw canBlock list", () => {
		const surfaces = auditHooks({ home: fixtureHome });
		const all = buildHookReport(surfaces, [], { home: fixtureHome, timeoutMs: 400 });
		const accepted = [
			"codex-plugin:fixture-plugin@fixture-marketplace:Stop:0:0",
			"codex-plugin:env-plugin@fixture-marketplace:Stop:0:0",
		];
		const relaxed = buildHookReport(surfaces, [], { home: fixtureHome, timeoutMs: 400, knownGates: accepted });

		// Never hidden: the raw list is identical and the accepted ids are reported explicitly.
		expect(relaxed.canBlock).toEqual(all.canBlock);
		expect(relaxed.canBlock).toContain("codex-plugin:fixture-plugin@fixture-marketplace:Stop:0:0");
		expect(relaxed.checks.acceptedGates).toContain("codex-plugin:env-plugin@fixture-marketplace:Stop:0:0");
		// The env finding for an accepted gate is no longer unexpected.
		expect(all.checks.findings.join(" ")).toContain("env-plugin@fixture-marketplace:Stop:0:0 (CLAUDE_PROJECT_DIR)");
		expect(relaxed.checks.findings.join(" ")).not.toContain("env-plugin@fixture-marketplace:Stop:0:0 (CLAUDE_PROJECT_DIR)");
	});

	test("ok flips true only when every can-block surface is accepted", () => {
		const surfaces = auditHooks({ home: fixtureHome });
		const everyGate = surfaces.filter((surface) => surface.blocking || surface.verdict === "can-block").map((surface) => surface.id);
		const accepted = buildHookReport(surfaces, [], { home: fixtureHome, timeoutMs: 400, knownGates: everyGate });
		expect(accepted.canBlock.length).toBeGreaterThan(0);
		expect(accepted.checks.acceptedGates).toEqual([...everyGate].sort());
		expect(accepted.checks.findings).toEqual([]);
		expect(accepted.ok).toBe(true);
	});
});

describe("doctor --probe-all matrix", () => {
	test("parseDoctorArgs reads --probe-all and repeated --known-gate", () => {
		const opts = parseDoctorArgs(["--probe-all", "--known-gate", "a:0:0", "--known-gate=b:0:0"]);
		expect(opts.probeAll).toBe(true);
		expect(opts.knownGates).toEqual(["a:0:0", "b:0:0"]);
	});

	test("the matrix replays probeable command hooks across four stdin classes and never executes probe:false", () => {
		const base: HookSurface = {
			id: "probe:command",
			kind: "claude-hook",
			source: "fixture",
			event: "SessionStart",
			command: 'node -e "process.stdin.resume()"',
			path: null,
			verdict: "fail-open",
			blocking: false,
			reason: "",
			probe: true,
		};
		const gate: HookSurface = { ...base, id: "probe:blocking-gate", event: "Stop", command: 'node -e "process.exit(1)"', verdict: "can-block", blocking: true, probe: false };
		const mcp: HookSurface = { ...base, id: "probe:mcp-tool", command: null, probe: false };

		const matrix = probeCommandMatrix([base, gate, mcp], { timeoutMs: 3_000, cwd: fixtureHome, env: spawnEnv });
		expect(matrix.rows.map((row) => row.id)).toEqual(["probe:command"]);
		expect(matrix.rows[0]!.results.map((r) => r.class)).toEqual(["closed", "empty", "malformed", "valid"]);
		expect(matrix.rows[0]!.results.every((r) => r.status === "ok" && r.exitCode === 0)).toBe(true);
		expect(matrix.excluded).toEqual(["probe:blocking-gate", "probe:mcp-tool"]);
	});

	test("--probe-all emits knownGates and probeMatrix and still exits 0", () => {
		const run = spawnSync("bun", [doctorPath, "--json", "--home", fixtureHome, "--probe-all", "--timeout", "300"], {
			cwd: repoRoot,
			encoding: "utf8",
			timeout: 30_000,
			env: spawnEnv,
		});
		expect(run.status).toBe(0);
		const report = JSON.parse(run.stdout);
		expect(Object.keys(report)).toEqual([...HOOK_DOCTOR_JSON_KEYS, "knownGates", "probeMatrix"]);
		expect(report.knownGates).toContain("pi:extension:plan-mode");
		expect(Array.isArray(report.probeMatrix.rows)).toBe(true);
		expect(report.probeMatrix.rows.length).toBeGreaterThan(0);
		for (const row of report.probeMatrix.rows) expect(row.results.map((r: any) => r.class)).toEqual(["closed", "empty", "malformed", "valid"]);
		// Blocking-event and mcp_tool surfaces stay out of the matrix by construction.
		expect(report.probeMatrix.rows.some((row: any) => String(row.id).endsWith(":Stop:0:0"))).toBe(false);
		expect(report.probeMatrix.excluded).toContain("codex-plugin:fixture-plugin@fixture-marketplace:Stop:0:0");
		expect(report.probeMatrix.excluded).toContain("codex-plugin:browser-plugin@fixture-marketplace:Stop:0:0");
	});

	test("--known-gate moves a can-block id into acceptedGates without hiding it", () => {
		const id = "codex-plugin:fixture-plugin@fixture-marketplace:Stop:0:0";
		const run = spawnSync("bun", [doctorPath, "--json", "--home", fixtureHome, "--no-probe", "--known-gate", id], {
			cwd: repoRoot,
			encoding: "utf8",
			timeout: 20_000,
			env: spawnEnv,
		});
		expect(run.status).toBe(0);
		const report = JSON.parse(run.stdout);
		expect(report.canBlock).toContain(id);
		expect(report.checks.acceptedGates).toContain(id);
		expect(report.checks.findings.join(" ")).not.toContain(id);
	});
});
