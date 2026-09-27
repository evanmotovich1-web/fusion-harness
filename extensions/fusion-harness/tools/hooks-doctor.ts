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
 *       [--modules-dir DIR] [--manifest-dir DIR] [--timeout MS] [--no-probe]
 *       [--probe-all] [--known-gate ID] [--help]
 *
 * Exit: always 0.
 */

import { spawnSync } from "node:child_process";
import * as os from "node:os";
import {
	HOOK_DOCTOR_JSON_KEYS,
	auditHookSurfaces,
	buildHookReport,
	formatHookReport,
	probeHooks,
	resolveKnownGates,
	type HookAuditChecks,
	type HookAuditReport,
	type HookSurface,
} from "../modules/hook-audit.ts";

export interface DoctorOptions {
	json?: boolean;
	home?: string;
	modulesDir?: string;
	manifestDir?: string;
	timeoutMs?: number;
	probe?: boolean;
	probeAll?: boolean;
	knownGates?: string[];
}

export type ProbeStdinClass = "closed" | "empty" | "malformed" | "valid";

const PROBE_STDIN_CLASSES: readonly ProbeStdinClass[] = ["closed", "empty", "malformed", "valid"];

export interface ProbeClassResult {
	class: ProbeStdinClass;
	status: "ok" | "nonzero" | "timeout" | "spawn-error";
	exitCode: number | null;
	signal: string | null;
	durationMs: number;
}

export interface ProbeMatrixRow {
	id: string;
	kind: string;
	event: string | null;
	command: string;
	results: ProbeClassResult[];
}

export interface ProbeMatrix {
	timeoutMs: number;
	rows: ProbeMatrixRow[];
	/** probe:false or commandless surfaces (blocking events, mcp_tool) — never executed. */
	excluded: string[];
}

export interface DoctorReport extends HookAuditReport {
	knownGates?: string[];
	probeMatrix?: ProbeMatrix;
}

export interface DoctorResult {
	exitCode: number;
	stdout: string;
	stderr: string;
	report: DoctorReport;
}

function probeStdinFor(cls: ProbeStdinClass, surface: HookSurface, cwd: string): string | undefined {
	switch (cls) {
		case "closed":
			return undefined;
		case "empty":
			return "";
		case "malformed":
			return '{"session_id":';
		case "valid":
			return JSON.stringify({ session_id: "fh-hooks-doctor", hook_event_name: surface.event ?? "Unknown", cwd, transcript_path: "" });
	}
}

function runProbeClass(
	surface: HookSurface,
	cls: ProbeStdinClass,
	timeoutMs: number,
	options: { cwd?: string; env?: NodeJS.ProcessEnv },
): ProbeClassResult {
	const startedAt = Date.now();
	const input = probeStdinFor(cls, surface, options.cwd ?? process.cwd());
	try {
		const result = spawnSync(surface.command!, {
			shell: true,
			cwd: options.cwd ?? process.cwd(),
			env: options.env ?? process.env,
			timeout: timeoutMs,
			killSignal: "SIGKILL",
			encoding: "utf8",
			// Closed class gets no stdin at all; the other three pipe the class payload in.
			stdio: input === undefined ? ["ignore", "pipe", "pipe"] : ["pipe", "pipe", "pipe"],
			input,
			maxBuffer: 1024 * 1024,
		});
		const errorCode = (result.error as NodeJS.ErrnoException | undefined)?.code;
		let status: ProbeClassResult["status"];
		if (errorCode === "ETIMEDOUT" || result.signal === "SIGKILL" || result.signal === "SIGTERM") status = "timeout";
		else if (result.error) status = "spawn-error";
		else if (result.status === 0) status = "ok";
		else status = "nonzero";
		return {
			class: cls,
			status,
			exitCode: typeof result.status === "number" ? result.status : null,
			signal: result.signal ?? null,
			durationMs: Date.now() - startedAt,
		};
	} catch {
		return { class: cls, status: "spawn-error", exitCode: null, signal: null, durationMs: Date.now() - startedAt };
	}
}

/**
 * Opt-in full matrix: replay every probeable COMMAND hook with closed / empty / malformed / valid
 * stdin under a bounded timeout. `probe:false` surfaces are excluded by construction, so
 * blocking-event (Stop/SessionEnd/PreToolUse) and `mcp_tool` hooks are never executed here.
 */
export function probeCommandMatrix(
	surfaces: HookSurface[],
	options: { timeoutMs?: number; cwd?: string; env?: NodeJS.ProcessEnv } = {},
): ProbeMatrix {
	const timeoutMs = Math.min(30_000, Math.max(100, Number.isFinite(options.timeoutMs) ? Number(options.timeoutMs) : 3_000));
	const rows: ProbeMatrixRow[] = [];
	const excluded: string[] = [];
	for (const surface of surfaces) {
		if (!surface.probe || !surface.command) {
			excluded.push(surface.id);
			continue;
		}
		rows.push({
			id: surface.id,
			kind: surface.kind,
			event: surface.event,
			command: surface.command,
			results: PROBE_STDIN_CLASSES.map((cls) => runProbeClass(surface, cls, timeoutMs, options)),
		});
	}
	return { timeoutMs, rows, excluded };
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
	"  --probe-all         replay every probeable COMMAND hook with closed/empty/malformed/valid stdin",
	"  --known-gate ID     accept a can-block id (repeatable); it stays in canBlock, leaves findings",
	"  --help              show this text",
	"",
	"Checks the knowledge contract block, injector/guard fail-open status, any Stop gate we",
	"installed, codex trusted_hash recency, and codex PLUGIN Stop/SessionEnd gates. Always",
	"exits 0; failures are loud on stderr.",
].join("\n");

export function parseDoctorArgs(argv: string[]): DoctorOptions {
	const opts: DoctorOptions = { probe: true };
	for (let i = 0; i < argv.length; i++) {
		const arg = argv[i]!;
		if (arg === "--json") opts.json = true;
		else if (arg === "--no-probe") opts.probe = false;
		else if (arg === "--probe") opts.probe = true;
		else if (arg === "--probe-all") opts.probeAll = true;
		else if (arg === "--known-gate") {
			const value = argv[++i];
			if (value && !value.startsWith("--")) (opts.knownGates ??= []).push(value);
		}
		else if (arg.startsWith("--known-gate=")) {
			const value = arg.slice("--known-gate=".length).trim();
			if (value) (opts.knownGates ??= []).push(value);
		}
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
	codexPluginHooks: 0,
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

function serializeReport(report: DoctorReport): string {
	// Rebuild in the frozen key order so downstream consumers can diff output; the opt-in
	// probe-all keys are appended after the frozen set so a plain --json run is unchanged.
	const ordered: Record<string, unknown> = {};
	for (const key of HOOK_DOCTOR_JSON_KEYS) ordered[key] = (report as unknown as Record<string, unknown>)[key];
	if (report.knownGates) ordered.knownGates = report.knownGates;
	if (report.probeMatrix) ordered.probeMatrix = report.probeMatrix;
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

	let report: DoctorReport;
	let probeMatrix: ProbeMatrix | undefined;
	try {
		const audit = auditHookSurfaces({ home, modulesDir: opts.modulesDir, manifestDir: opts.manifestDir });
		const probes = opts.probe ? probeHooks(audit.surfaces, { timeoutMs, cwd: runtime.cwd, env: runtime.env }) : [];
		report = buildHookReport(audit.surfaces, probes, { home, timeoutMs, contract: audit.contract, knownGates: opts.knownGates });
		if (opts.probeAll) {
			probeMatrix = probeCommandMatrix(audit.surfaces, { timeoutMs, cwd: runtime.cwd, env: runtime.env });
			report = { ...report, knownGates: resolveKnownGates(opts.knownGates), probeMatrix };
		}
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

	const matrixText = probeMatrix
		? `\nprobe-all matrix (${probeMatrix.rows.length} command hook(s); ${probeMatrix.excluded.length} excluded by probe:false):\n${probeMatrix.rows
				.map((row) => `  ${row.id}  ${row.results.map((r) => `${r.class}=${r.status}${r.exitCode === null ? "" : `(${r.exitCode})`}`).join(" ")}`)
				.join("\n")}\n`
		: "";
	const stdout = opts.json ? serializeReport(report) : `${formatHookReport(report)}\n${matrixText}`;
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
