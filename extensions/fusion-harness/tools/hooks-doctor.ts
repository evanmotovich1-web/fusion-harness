#!/usr/bin/env bun
/**
 * hooks-doctor.ts — read-only hook health doctor.
 *
 * Enumerates every installed hook surface, verifies the knowledge contract block, probes each
 * probeable surface under a bounded timeout with stdin closed, and prints a verdict (human
 * text, or `--json`).
 *
 * It probes only. It never edits a global config file, never writes a hook, and always
 * exits 0: a can-block or drift finding fails loudly on stderr and sets `ok:false`, but the
 * process exit code stays 0 so a health check can never itself break a pipeline.
 *
 * Usage:
 *   bun extensions/fusion-harness/tools/hooks-doctor.ts [--json] [--home DIR]
 *       [--modules-dir DIR] [--manifest-dir DIR] [--timeout MS] [--no-probe] [--help]
 *
 * Exit: always 0.
 */

import * as os from "node:os";
import {
	HOOK_DOCTOR_JSON_KEYS,
	auditHookSurfaces,
	buildHookReport,
	formatHookReport,
	probeHooks,
	type HookAuditChecks,
	type HookAuditReport,
} from "../modules/hook-audit.ts";

export interface DoctorOptions {
	json?: boolean;
	home?: string;
	modulesDir?: string;
	manifestDir?: string;
	timeoutMs?: number;
	probe?: boolean;
}

export interface DoctorResult {
	exitCode: number;
	stdout: string;
	stderr: string;
	report: HookAuditReport;
}

const HELP = [
	"hooks-doctor — read-only health probe for installed agent hooks",
	"",
	"Usage: hooks-doctor [--json] [--home DIR] [--modules-dir DIR] [--manifest-dir DIR]",
	"       [--timeout MS] [--no-probe] [--help]",
	"",
	"  --json              emit the machine-readable verdict",
	"  --home DIR          config home to scan (default: $HOME)",
	"  --modules-dir DIR   harness modules dir for knowledge-inject/guard (default: the repo)",
	"  --manifest-dir DIR  knowledge-install manifest dir (default: <home>/.fh-knowledge)",
	"  --timeout MS        bounded probe timeout, 100..30000 (default: 3000)",
	"  --no-probe          enumerate and classify only; execute nothing",
	"  --help              show this text",
	"",
	"Checks the knowledge contract block, injector/guard fail-open status, any Stop gate we",
	"installed, and codex trusted_hash recency. Always exits 0; failures are loud on stderr.",
].join("\n");

export function parseDoctorArgs(argv: string[]): DoctorOptions {
	const opts: DoctorOptions = { probe: true };
	for (let i = 0; i < argv.length; i++) {
		const arg = argv[i]!;
		if (arg === "--json") opts.json = true;
		else if (arg === "--no-probe") opts.probe = false;
		else if (arg === "--probe") opts.probe = true;
		else if (arg === "--home") opts.home = argv[++i];
		else if (arg.startsWith("--home=")) opts.home = arg.slice("--home=".length);
		else if (arg === "--modules-dir") opts.modulesDir = argv[++i];
		else if (arg.startsWith("--modules-dir=")) opts.modulesDir = arg.slice("--modules-dir=".length);
		else if (arg === "--manifest-dir") opts.manifestDir = argv[++i];
		else if (arg.startsWith("--manifest-dir=")) opts.manifestDir = arg.slice("--manifest-dir=".length);
		else if (arg === "--timeout") opts.timeoutMs = Number(argv[++i]);
		else if (arg.startsWith("--timeout=")) opts.timeoutMs = Number(arg.slice("--timeout=".length));
	}
	return opts;
}

const EMPTY_CHECKS: HookAuditChecks = {
	contractBlock: "not-installed",
	contractSurfaces: [],
	knowledgeInject: "absent",
	knowledgeGuard: "absent",
	stopGateInstalledByUs: "none",
	codexTrust: "unknown",
	canBlockCount: 0,
	findings: [],
};

function emptyReport(home: string, timeoutMs: number, findings: string[] = []): HookAuditReport {
	return {
		version: 1,
		home,
		ok: findings.length === 0,
		scanned: 0,
		timeoutMs,
		canBlock: [],
		failOpen: [],
		notProbed: [],
		checks: { ...EMPTY_CHECKS, findings },
		surfaces: [],
		probes: [],
	};
}

function serializeReport(report: HookAuditReport): string {
	// Rebuild in the frozen key order so downstream consumers can diff output.
	const ordered: Record<string, unknown> = {};
	for (const key of HOOK_DOCTOR_JSON_KEYS) ordered[key] = (report as unknown as Record<string, unknown>)[key];
	return `${JSON.stringify(ordered, null, 2)}\n`;
}

/**
 * Run the doctor without touching stdio. Never throws: any unexpected failure yields a
 * minimal `ok:false` verdict and exit code 0.
 */
export function runHooksDoctor(argv: string[] = [], runtime: { cwd?: string; env?: NodeJS.ProcessEnv } = {}): DoctorResult {
	const opts = parseDoctorArgs(argv);
	const home = opts.home ?? process.env.HOME ?? os.homedir();
	const timeoutMs = Math.min(30_000, Math.max(100, Number.isFinite(opts.timeoutMs) ? Number(opts.timeoutMs) : 3_000));

	if (argv.includes("--help") || argv.includes("-h")) {
		return { exitCode: 0, stdout: `${HELP}\n`, stderr: "", report: emptyReport(home, timeoutMs) };
	}

	let report: HookAuditReport;
	try {
		const audit = auditHookSurfaces({ home, modulesDir: opts.modulesDir, manifestDir: opts.manifestDir });
		const probes = opts.probe ? probeHooks(audit.surfaces, { timeoutMs, cwd: runtime.cwd, env: runtime.env }) : [];
		report = buildHookReport(audit.surfaces, probes, { home, timeoutMs, contract: audit.contract });
	} catch (error) {
		const message = `audit failed but exiting 0: ${error instanceof Error ? error.message : String(error)}`;
		report = emptyReport(home, timeoutMs, [message]);
		return {
			exitCode: 0,
			stdout: opts.json ? serializeReport(report) : `${formatHookReport(report)}\n`,
			stderr: `hooks-doctor: ${message}\n`,
			report,
		};
	}

	const stdout = opts.json ? serializeReport(report) : `${formatHookReport(report)}\n`;
	const stderr = report.ok
		? ""
		: `hooks-doctor: CAN-BLOCK or drift found — ${report.checks.findings.join("; ") || "see the JSON verdict"} — exiting 0 anyway\n`;
	return { exitCode: 0, stdout, stderr, report };
}

/** Stream-writing wrapper. Returns 0 always. */
export function main(argv: string[] = process.argv.slice(2)): number {
	const result = runHooksDoctor(argv);
	if (result.stdout) process.stdout.write(result.stdout.endsWith("\n") ? result.stdout : `${result.stdout}\n`);
	if (result.stderr) process.stderr.write(result.stderr.endsWith("\n") ? result.stderr : `${result.stderr}\n`);
	process.exitCode = 0;
	return 0;
}

if (import.meta.main) {
	main();
}
