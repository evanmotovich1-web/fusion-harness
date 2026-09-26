/**
 * hook-audit.ts — read-only enumeration and classification of installed hook surfaces.
 *
 * Surfaces: the Pi extensions dir plus `packages` from ~/.pi/agent/settings.json,
 * ~/.claude/settings.json, ~/.codex/hooks.json (with the trusted hashes recorded in
 * ~/.codex/config.toml), ~/.hermes/config.yaml (+ shell-hooks-allowlist.json), the
 * vault-semantic Pi extension (covered by the Pi extensions dir), and the harness knowledge
 * surfaces: modules/knowledge-inject.ts, modules/knowledge-guard.ts, and the installed
 * global contract block recorded in <home>/.fh-knowledge/manifest.json.
 *
 * Nothing here writes a config file, edits a hook, or throws on a missing/corrupt surface:
 * an unreadable surface is reported, not propagated. Only the doctor (tools/hooks-doctor.ts)
 * executes anything, and always under a bounded timeout with stdin closed.
 *
 * Verdicts:
 *   can-block     — the surface can stop a run (a blocking event, or a block/deny contract).
 *   fail-open     — an error, timeout or skip is logged and the run continues.
 *   unknown       — reserved; not produced by the current classifiers.
 */

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { parse as parseYaml } from "yaml";

// pi runs under Node: import.meta.dir is Bun-only, so derive the module dir the way
// prompt-library.ts and cmd-workflows.ts do (see orchestration-contract.test.ts).
const MODULE_DIR: string =
	typeof __dirname !== "undefined" && __dirname
		? __dirname
		: path.dirname(new URL(import.meta.url).pathname);

export type HookSurfaceKind = "pi-extension" | "pi-package" | "claude-hook" | "codex-hook" | "hermes-hook" | "knowledge-module" | "knowledge-contract";
export type HookVerdict = "fail-open" | "can-block" | "unknown";
export type HookTrustStatus = "present" | "missing" | "not-applicable";
export type HookTrustVerification = "present" | "missing" | "stale-suspect" | "unknown";
export type ContractStatus = "not-installed" | "current" | "missing" | "duplicate" | "stale";

/** Marker-delimited global knowledge contract (tools/knowledge-install.ts). */
export const CONTRACT_BEGIN = "<!-- fh-knowledge:begin -->";
export const CONTRACT_END = "<!-- fh-knowledge:end -->";
export const DEFAULT_CONTRACT_MANIFEST_DIRNAME = ".fh-knowledge";
export const KNOWLEDGE_MODULE_FILES = ["knowledge-inject.ts", "knowledge-guard.ts"] as const;
/** Config files a knowledge installer must never write; used for the Stop-gate check. */
const HOOK_CONFIG_NAME_RE = /(?:^|\/)(?:settings\.json|hooks\.json|config\.(?:ya?ml|toml))$/;

export const DEFAULT_PROBE_TIMEOUT_MS = 3_000;
export const MIN_PROBE_TIMEOUT_MS = 100;
export const MAX_PROBE_TIMEOUT_MS = 30_000;

/** Claude events whose hooks can refuse a tool or stop the session. */
const BLOCKING_CLAUDE_EVENTS = new Set(["PreToolUse", "Stop", "SubagentStop", "PermissionRequest"]);
/** Codex events whose hooks can refuse the session end. */
const BLOCKING_CODEX_EVENTS = new Set(["Stop"]);
/** Hermes treats only pre_tool_call as blocking (hermes-agent/agent/shell_hooks.py:43). */
const BLOCKING_HERMES_EVENTS = new Set(["pre_tool_call"]);

const BLOCK_JSON_RE = /["'](?:decision|permissionDecision)["']\s*:\s*["'](?:block|deny)["']/;
const CONTINUE_FALSE_RE = /["']continue["']\s*:\s*false/;
const SCRIPT_TOKEN_RE = /(?:^|[\s"'])([^\s"']*\.(?:py|sh|bash|mjs|cjs|js|ts))(?=[\s"']|$)/;

export interface HookTrust {
	status: HookTrustStatus;
	key?: string;
	storedHash?: string;
	/** Codex cannot be re-hashed locally; this tracks whether hooks.json changed after the trust record. */
	verification?: HookTrustVerification;
	reason?: string;
}

export interface HookSurface {
	/** Stable id: `<kind-scope>:<name-or-event>:<index>`; unique within one audit. */
	id: string;
	kind: HookSurfaceKind;
	/** Config file (or dir) that declared the surface. */
	source: string;
	event: string | null;
	command: string | null;
	/** Script or module file that implements the surface, when resolvable. */
	path: string | null;
	verdict: HookVerdict;
	blocking: boolean;
	reason: string;
	/** Whether the doctor may execute this surface. Blocking-event surfaces are static-only. */
	probe: boolean;
	trust?: HookTrust;
	meta?: Record<string, string | number | boolean>;
}

export type HookProbeStatus = "ok" | "nonzero" | "timeout" | "spawn-error" | "skipped";

export interface HookProbeResult {
	id: string;
	command: string | null;
	status: HookProbeStatus;
	exitCode: number | null;
	signal: string | null;
	durationMs: number;
	stdout: string;
	stderr: string;
	/** A failed knowledge/injection hook must never gate the run. Always true unless skipped. */
	failOpen: boolean;
	/** The probe itself printed a block/deny contract. */
	blockHint: boolean;
	error?: string;
}

export interface HookAuditChecks {
	contractBlock: ContractStatus;
	contractSurfaces: string[];
	knowledgeInject: "fail-open" | "can-block" | "absent";
	knowledgeGuard: "fail-open" | "can-block" | "absent";
	stopGateInstalledByUs: "none" | "present";
	codexTrust: "pass" | "warn" | "absent" | "unknown";
	canBlockCount: number;
	findings: string[];
}

export interface HookAuditReport {
	version: 1;
	home: string;
	ok: boolean;
	scanned: number;
	timeoutMs: number;
	canBlock: string[];
	failOpen: string[];
	notProbed: string[];
	checks: HookAuditChecks;
	surfaces: HookSurface[];
	probes: HookProbeResult[];
}

export const HOOK_DOCTOR_JSON_KEYS = [
	"version",
	"home",
	"ok",
	"scanned",
	"timeoutMs",
	"canBlock",
	"failOpen",
	"notProbed",
	"checks",
	"surfaces",
	"probes",
] as const;

// ── safe readers ─────────────────────────────────────────────────────────────

function readTextSafe(file: string): string {
	try {
		return fs.readFileSync(file, "utf8");
	} catch {
		return "";
	}
}

function readJsonSafe(file: string): any {
	try {
		return JSON.parse(fs.readFileSync(file, "utf8"));
	} catch {
		return undefined;
	}
}

function readYamlSafe(file: string): any {
	try {
		return parseYaml(fs.readFileSync(file, "utf8"));
	} catch {
		return undefined;
	}
}

function isDirectory(p: string): boolean {
	try {
		return fs.statSync(p).isDirectory();
	} catch {
		return false;
	}
}

/** mtime in ms, or undefined when the file cannot be stat'd. */
function statMtimeMs(file: string): number | undefined {
	try {
		return fs.statSync(file).mtimeMs;
	} catch {
		return undefined;
	}
}

function resolveExtensionImpl(abs: string): string | null {
	let stat: fs.Stats;
	try {
		stat = fs.statSync(abs);
	} catch {
		return null;
	}
	if (stat.isFile()) return abs;
	if (!stat.isDirectory()) return null;
	for (const candidate of ["index.ts", "index.js", "index.mjs", "index.cjs"]) {
		const file = path.join(abs, candidate);
		if (fs.existsSync(file)) return file;
	}
	return null;
}

/** Pull the first script-looking token out of a hook command, resolving relative paths. */
export function resolveScriptFromCommand(command: string, baseDir: string): string | null {
	const match = SCRIPT_TOKEN_RE.exec(command);
	if (!match) return null;
	let candidate = match[1]!;
	if (candidate.startsWith("~")) candidate = path.join(os.homedir(), candidate.slice(1));
	if (!path.isAbsolute(candidate)) candidate = path.resolve(baseDir, candidate);
	return candidate;
}

/** Codex trust records keyed by the state string in config.toml `[hooks.state."<key>"]`. */
export function parseCodexTrust(configToml: string): Map<string, string> {
	const trust = new Map<string, string>();
	const re = /\[hooks\.state\."([^"]+)"\]([\s\S]*?)(?=\n\[|$)/g;
	for (const match of configToml.matchAll(re)) {
		const key = match[1]!;
		const hash = /trusted_hash\s*=\s*"([^"]+)"/.exec(match[2] ?? "");
		if (hash) trust.set(key, hash[1]!);
	}
	return trust;
}

function snakeEvent(event: string): string {
	return event.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
}

// ── classifiers ──────────────────────────────────────────────────────────────

interface Classification {
	verdict: HookVerdict;
	blocking: boolean;
	reason: string;
}

export function classifyPiExtension(content: string, file: string | null): Classification {
	if (!file) {
		return { verdict: "fail-open", blocking: false, reason: "no loadable implementation file; a load error is logged and Pi continues" };
	}
	if (BLOCK_JSON_RE.test(content)) {
		return { verdict: "can-block", blocking: true, reason: "contains a block/deny contract" };
	}
	if (/block\s*:\s*true/.test(content)) {
		const reason = /hasUI/.test(content)
			? "returns block:true when ctx.hasUI is false (headless cannot confirm)"
			: "returns block:true";
		return { verdict: "can-block", blocking: true, reason };
	}
	if (CONTINUE_FALSE_RE.test(content)) {
		return { verdict: "can-block", blocking: true, reason: "contains continue:false" };
	}
	return { verdict: "fail-open", blocking: false, reason: "no block contract detected; errors are logged and the run continues" };
}

export function classifyClaude(event: string, content: string): Classification {
	if (/block\s*:\s*true/.test(content)) {
		return { verdict: "can-block", blocking: true, reason: "contains block:true" };
	}
	if (BLOCK_JSON_RE.test(content)) {
		return { verdict: "can-block", blocking: true, reason: `prints a block decision on ${event}` };
	}
	if (CONTINUE_FALSE_RE.test(content)) {
		return { verdict: "can-block", blocking: true, reason: "contains continue:false" };
	}
	if (BLOCKING_CLAUDE_EVENTS.has(event)) {
		return { verdict: "fail-open", blocking: false, reason: `${event} can block, but no block contract was found; exit 1 is non-blocking` };
	}
	return { verdict: "fail-open", blocking: false, reason: `${event} is non-blocking; errors and timeouts are logged` };
}

export function classifyHermes(event: string, failClosed: boolean): Classification {
	if (failClosed) return { verdict: "can-block", blocking: true, reason: "fail_closed=true" };
	if (BLOCKING_HERMES_EVENTS.has(event)) return { verdict: "can-block", blocking: true, reason: `${event} is a blocking event` };
	return { verdict: "fail-open", blocking: false, reason: `${event} is non-blocking; a timeout or throw is logged` };
}

// ── enumeration ──────────────────────────────────────────────────────────────

export interface AuditHooksOptions {
	home?: string;
}

function enumeratePiExtensions(home: string): HookSurface[] {
	const dir = path.join(home, ".pi", "agent", "extensions");
	const surfaces: HookSurface[] = [];
	if (!isDirectory(dir)) return surfaces;
	let entries: fs.Dirent[];
	try {
		entries = fs.readdirSync(dir, { withFileTypes: true });
	} catch {
		return surfaces;
	}
	for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
		if (entry.name.startsWith(".")) continue;
		const abs = path.join(dir, entry.name);
		const impl = resolveExtensionImpl(abs);
		const content = impl ? readTextSafe(impl) : "";
		const cls = classifyPiExtension(content, impl);
		const event = /before_agent_start/.test(content)
			? "before_agent_start"
			: /tool_call/.test(content)
				? "tool_call"
				: /session_start/.test(content)
					? "session_start"
					: "extension-load";
		surfaces.push({
			id: `pi:extension:${entry.name}`,
			kind: "pi-extension",
			source: dir,
			event,
			command: null,
			path: impl,
			verdict: cls.verdict,
			blocking: cls.blocking,
			reason: cls.reason,
			// Pi extension modules are not shell-probeable; they load into the host process.
			probe: false,
		});
	}
	return surfaces;
}

function enumeratePiPackages(home: string): HookSurface[] {
	const settingsPath = path.join(home, ".pi", "agent", "settings.json");
	const settings = readJsonSafe(settingsPath);
	const packages: unknown[] = Array.isArray(settings?.packages) ? settings.packages : [];
	const surfaces: HookSurface[] = [];
	for (const raw of packages) {
		const name = String(raw);
		const isNpm = name.startsWith("npm:");
		const target = isNpm ? null : path.resolve(path.join(home, ".pi", "agent"), name);
		const exists = target ? fs.existsSync(target) : false;
		surfaces.push({
			id: `pi:package:${name}`,
			kind: "pi-package",
			source: settingsPath,
			event: null,
			command: null,
			path: target,
			verdict: "fail-open",
			blocking: false,
			reason: isNpm
				? "external npm package: not statically inspected; a load failure is logged and Pi continues"
				: exists
					? "local package present; no blocking contract detected"
					: "package path not found; nothing loads",
			probe: false,
		});
	}
	return surfaces;
}

function enumerateClaude(home: string): HookSurface[] {
	const settingsPath = path.join(home, ".claude", "settings.json");
	const settings = readJsonSafe(settingsPath);
	const hooks = settings && typeof settings === "object" && settings.hooks && typeof settings.hooks === "object" ? settings.hooks : {};
	const baseDir = path.dirname(settingsPath);
	const surfaces: HookSurface[] = [];
	for (const [event, rawGroups] of Object.entries(hooks)) {
		if (!Array.isArray(rawGroups)) continue;
		rawGroups.forEach((group: any, gi: number) => {
			const list = Array.isArray(group?.hooks) ? group.hooks : [];
			list.forEach((hook: any, hi: number) => {
				if (!hook || typeof hook.command !== "string") return;
				const script = resolveScriptFromCommand(hook.command, baseDir);
				const content = script ? readTextSafe(script) : "";
				const cls = classifyClaude(event, content);
				surfaces.push({
					id: `claude:${event}:${gi}:${hi}`,
					kind: "claude-hook",
					source: settingsPath,
					event,
					command: hook.command,
					path: script,
					verdict: cls.verdict,
					blocking: cls.blocking,
					reason: cls.reason,
					probe: !BLOCKING_CLAUDE_EVENTS.has(event),
					meta: {
						timeout: typeof hook.timeout === "number" ? hook.timeout : 0,
						matcher: typeof group.matcher === "string" ? group.matcher : "",
					},
				});
			});
		});
	}
	return surfaces;
}

function enumerateCodex(home: string): HookSurface[] {
	const hooksPath = path.join(home, ".codex", "hooks.json");
	const data = readJsonSafe(hooksPath);
	const hooks = data && typeof data === "object" && data.hooks && typeof data.hooks === "object" ? data.hooks : {};
	const configPath = path.join(home, ".codex", "config.toml");
	const trust = parseCodexTrust(readTextSafe(configPath));
	const hooksMtime = statMtimeMs(hooksPath);
	const configMtime = statMtimeMs(configPath);
	// A hooks.json edit after the config.toml trust write invalidates codex's stored
	// trusted_hash. Timestamps are the only local signal; a 2s floor absorbs fs granularity.
	const trustToleranceMs = 2_000;
	const baseDir = path.dirname(hooksPath);
	const surfaces: HookSurface[] = [];
	for (const [event, rawGroups] of Object.entries(hooks)) {
		if (!Array.isArray(rawGroups)) continue;
		rawGroups.forEach((group: any, gi: number) => {
			const list = Array.isArray(group?.hooks) ? group.hooks : [];
			list.forEach((hook: any, hi: number) => {
				if (!hook || typeof hook.command !== "string") return;
				const suffix = `hooks.json:${snakeEvent(event)}:${gi}:${hi}`;
				const key = [...trust.keys()].find((candidate) => candidate.endsWith(suffix));
				const storedHash = key ? trust.get(key) : undefined;
				const verification: HookTrustVerification = !storedHash
					? "missing"
					: hooksMtime === undefined || configMtime === undefined
						? "unknown"
						: hooksMtime > configMtime + trustToleranceMs
							? "stale-suspect"
							: "present";
				const script = resolveScriptFromCommand(hook.command, baseDir);
				surfaces.push({
					id: `codex:${event}:${gi}:${hi}`,
					kind: "codex-hook",
					source: hooksPath,
					event,
					command: hook.command,
					path: script,
					verdict: "fail-open",
					blocking: false,
					reason: storedHash
						? verification === "stale-suspect"
							? "hooks.json was edited after the trusted_hash record; codex may silently skip until re-trust (never blocks)"
							: "trusted_hash present; an error or skip is logged and the run continues"
						: "no persisted trusted_hash; the hook silently skips until approved (never blocks)",
					probe: !BLOCKING_CODEX_EVENTS.has(event),
					trust: { status: storedHash ? "present" : "missing", key, storedHash, verification },
					meta: { timeout: typeof hook.timeout === "number" ? hook.timeout : 0 },
				});
			});
		});
	}
	return surfaces;
}

function enumerateHermes(home: string): HookSurface[] {
	const configPath = path.join(home, ".hermes", "config.yaml");
	const config = readYamlSafe(configPath);
	const hooks = config && typeof config === "object" && config.hooks && typeof config.hooks === "object" ? config.hooks : {};
	const allowPath = path.join(home, ".hermes", "shell-hooks-allowlist.json");
	const allow = readJsonSafe(allowPath);
	const approvals = new Set<string>(
		(Array.isArray(allow?.approvals) ? allow.approvals : [])
			.filter((a: any) => a && typeof a.event === "string" && typeof a.command === "string")
			.map((a: any) => `${a.event}\u0000${a.command}`),
	);
	const baseDir = path.dirname(configPath);
	const surfaces: HookSurface[] = [];
	for (const [event, rawList] of Object.entries(hooks)) {
		if (!Array.isArray(rawList)) continue;
		rawList.forEach((hook: any, i: number) => {
			if (!hook || typeof hook.command !== "string") return;
			const failClosed = hook.fail_closed === true;
			const cls = classifyHermes(event, failClosed);
			const allowlisted = approvals.has(`${event}\u0000${hook.command}`);
			const reason = allowlisted ? cls.reason : `${cls.reason}; command not in shell-hooks-allowlist (a non-TTY start skips it)`;
			surfaces.push({
				id: `hermes:${event}:${i}`,
				kind: "hermes-hook",
				source: configPath,
				event,
				command: hook.command,
				path: resolveScriptFromCommand(hook.command, baseDir),
				verdict: cls.verdict,
				blocking: cls.blocking,
				reason,
				probe: !BLOCKING_HERMES_EVENTS.has(event) && !failClosed,
				meta: { allowlisted, timeout: typeof hook.timeout === "number" ? hook.timeout : 0 },
			});
		});
	}
	return surfaces;
}

/** Enumerate every installed hook surface. Never throws; unreadable configs yield nothing. */
export function auditHooks(options: AuditHooksOptions = {}): HookSurface[] {
	const home = options.home ?? os.homedir();
	const surfaces: HookSurface[] = [];
	try {
		surfaces.push(...enumeratePiExtensions(home));
		surfaces.push(...enumeratePiPackages(home));
		surfaces.push(...enumerateClaude(home));
		surfaces.push(...enumerateCodex(home));
		surfaces.push(...enumerateHermes(home));
	} catch {
		/* enumeration is best-effort; the report shows whatever was collected */
	}
	return surfaces;
}

// ── knowledge surfaces: contract block, injector, guard ─────────────────────

function sha256Hex(text: string): string {
	return createHash("sha256").update(text, "utf8").digest("hex");
}

function countOccurrences(hay: string, needle: string): number {
	let count = 0;
	let from = 0;
	while (from < hay.length) {
		const index = hay.indexOf(needle, from);
		if (index < 0) break;
		count++;
		from = index + needle.length;
	}
	return count;
}

export interface ContractSurfaceCheck {
	id: string;
	path: string;
	beginCount: number;
	endCount: number;
	blockMatches: boolean;
}

export interface ContractCheck {
	status: ContractStatus;
	manifestPath: string;
	installedByUs: boolean;
	/** "present" means we wrote a hook/settings config or a block/deny contract — never allowed. */
	stopGate: "none" | "present";
	blockHash: string;
	surfaces: ContractSurfaceCheck[];
}

export function classifyKnowledgeModule(content: string, file: string): Classification {
	if (BLOCK_JSON_RE.test(content) || /block\s*:\s*true/.test(content) || CONTINUE_FALSE_RE.test(content)) {
		return { verdict: "can-block", blocking: true, reason: `${path.basename(file)} contains a block/deny contract` };
	}
	const catches = /catch\s*\(/.test(content) || /catch\s*{/.test(content);
	const returnsUndefined = /return undefined/.test(content);
	return {
		verdict: "fail-open",
		blocking: false,
		reason:
			catches && returnsUndefined
				? "routes every failure through catch and returns undefined; never blocks a turn"
				: "no block contract; a failure is logged and the turn continues",
	};
}

function knowledgeModuleSurfaces(modulesDir: string): HookSurface[] {
	const surfaces: HookSurface[] = [];
	for (const name of KNOWLEDGE_MODULE_FILES) {
		const file = path.join(modulesDir, name);
		const id = `knowledge:module:${name.replace(/\.ts$/, "")}`;
		if (!fs.existsSync(file)) {
			surfaces.push({
				id,
				kind: "knowledge-module",
				source: modulesDir,
				event: null,
				command: null,
				path: file,
				verdict: "fail-open",
				blocking: false,
				reason: "module not present; nothing can block",
				probe: false,
				meta: { present: false },
			});
			continue;
		}
		const cls = classifyKnowledgeModule(readTextSafe(file), file);
		surfaces.push({
			id,
			kind: "knowledge-module",
			source: modulesDir,
			event: "before_agent_start",
			command: null,
			path: file,
			verdict: cls.verdict,
			blocking: cls.blocking,
			reason: cls.reason,
			probe: false,
			meta: { present: true },
		});
	}
	return surfaces;
}

/**
 * Read the knowledge-install manifest and verify each installed surface carries the marker
 * block exactly once and still matches the recorded hash. Read-only; never installs.
 */
export function auditContract(manifestDir: string): ContractCheck {
	const manifestPath = path.join(manifestDir, "manifest.json");
	const manifest = readJsonSafe(manifestPath);
	const entries: any[] = Array.isArray(manifest?.entries) ? manifest.entries : [];
	const expectedHash = typeof manifest?.contractHash === "string" ? manifest.contractHash : "";
	if (!entries.length) {
		return { status: "not-installed", manifestPath, installedByUs: false, stopGate: "none", blockHash: expectedHash, surfaces: [] };
	}
	const surfaces: ContractSurfaceCheck[] = [];
	let stopGate: "none" | "present" = "none";
	let duplicate = false;
	let missing = false;
	let stale = false;
	for (const entry of entries) {
		const file = typeof entry?.path === "string" ? entry.path : "";
		const id = typeof entry?.id === "string" ? entry.id : path.basename(file);
		if (file && (HOOK_CONFIG_NAME_RE.test(file) || /\/hooks\//.test(file))) stopGate = "present";
		const content = file ? readTextSafe(file) : "";
		const beginCount = countOccurrences(content, CONTRACT_BEGIN);
		const endCount = countOccurrences(content, CONTRACT_END);
		let blockMatches = false;
		if (beginCount === 1 && endCount === 1) {
			const begin = content.indexOf(CONTRACT_BEGIN);
			const end = content.indexOf(CONTRACT_END, begin);
			const block = content.slice(begin, end + CONTRACT_END.length);
			const hash = sha256Hex(block);
			blockMatches = (!expectedHash || hash === expectedHash) && (typeof entry?.blockHash !== "string" || hash === entry.blockHash);
			if (!blockMatches) stale = true;
			if (BLOCK_JSON_RE.test(block) || /fail_closed/.test(block)) stopGate = "present";
		}
		if (beginCount === 0 || endCount === 0) missing = true;
		if (beginCount > 1 || endCount > 1) duplicate = true;
		surfaces.push({ id, path: file, beginCount, endCount, blockMatches });
	}
	const status: ContractStatus = duplicate ? "duplicate" : missing ? "missing" : stale ? "stale" : "current";
	return { status, manifestPath, installedByUs: true, stopGate, blockHash: expectedHash, surfaces };
}

function contractSurfaceRows(contract: ContractCheck): HookSurface[] {
	return contract.surfaces.map((row) => ({
		id: `knowledge:contract:${row.id}`,
		kind: "knowledge-contract" as const,
		source: contract.manifestPath,
		event: null,
		command: null,
		path: row.path,
		verdict: "fail-open" as const,
		blocking: false,
		reason:
			row.beginCount === 1 && row.endCount === 1
				? row.blockMatches
					? "marker block present exactly once and current"
					: "marker block present but stale against the manifest hash"
				: row.beginCount === 0
					? "marker block missing on a surface the manifest says is installed"
					: `marker block appears ${row.beginCount} times (expected exactly once)`,
		probe: false,
		meta: { beginCount: row.beginCount, endCount: row.endCount, blockMatches: row.blockMatches },
	}));
}

export interface AuditHookSurfacesOptions {
	home?: string;
	modulesDir?: string;
	manifestDir?: string;
}

export interface HookAudit {
	surfaces: HookSurface[];
	contract: ContractCheck;
}

/** All hook + knowledge surfaces, plus the contract verification. Never throws. */
export function auditHookSurfaces(options: AuditHookSurfacesOptions = {}): HookAudit {
	const home = options.home ?? os.homedir();
	const modulesDir = options.modulesDir ?? MODULE_DIR;
	const manifestDir = options.manifestDir ?? path.join(home, DEFAULT_CONTRACT_MANIFEST_DIRNAME);
	let surfaces: HookSurface[] = [];
	let contract: ContractCheck;
	try {
		surfaces = [...auditHooks({ home }), ...knowledgeModuleSurfaces(modulesDir)];
		contract = auditContract(manifestDir);
	} catch {
		contract = { status: "not-installed", manifestPath: path.join(manifestDir, "manifest.json"), installedByUs: false, stopGate: "none", blockHash: "", surfaces: [] };
	}
	return { surfaces: [...surfaces, ...contractSurfaceRows(contract)], contract };
}

// ── probing ──────────────────────────────────────────────────────────────────

export interface ProbeOptions {
	timeoutMs?: number;
	cwd?: string;
	env?: NodeJS.ProcessEnv;
}

function clampTimeout(value: number | undefined): number {
	const raw = Number.isFinite(value) ? Number(value) : DEFAULT_PROBE_TIMEOUT_MS;
	return Math.min(MAX_PROBE_TIMEOUT_MS, Math.max(MIN_PROBE_TIMEOUT_MS, Math.trunc(raw)));
}

function skippedProbe(surface: HookSurface): HookProbeResult {
	return {
		id: surface.id,
		command: surface.command,
		status: "skipped",
		exitCode: null,
		signal: null,
		durationMs: 0,
		stdout: "",
		stderr: "",
		failOpen: true,
		blockHint: false,
		error: surface.probe ? "no command to probe" : "blocking-event or non-executable surface: classified statically",
	};
}

/**
 * Execute one surface under a bounded timeout with stdin closed. Never throws.
 * A knowledge/injection hook that exits nonzero, hangs, or throws is fail-open: it
 * is reported, and the caller's run is never gated by it.
 */
export function probeHook(surface: HookSurface, options: ProbeOptions = {}): HookProbeResult {
	if (!surface.probe || !surface.command) return skippedProbe(surface);
	const timeoutMs = clampTimeout(options.timeoutMs);
	const startedAt = Date.now();
	try {
		const result = spawnSync(surface.command, {
			shell: true,
			cwd: options.cwd ?? process.cwd(),
			env: options.env ?? process.env,
			timeout: timeoutMs,
			killSignal: "SIGKILL",
			encoding: "utf8",
			stdio: ["ignore", "pipe", "pipe"],
			maxBuffer: 1024 * 1024,
		});
		const durationMs = Date.now() - startedAt;
		const errorCode = (result.error as NodeJS.ErrnoException | undefined)?.code;
		let status: HookProbeStatus;
		if (errorCode === "ETIMEDOUT" || result.signal === "SIGKILL" || result.signal === "SIGTERM") status = "timeout";
		else if (result.error) status = "spawn-error";
		else if (result.status === 0) status = "ok";
		else status = "nonzero";
		const stdout = typeof result.stdout === "string" ? result.stdout : "";
		const stderr = typeof result.stderr === "string" ? result.stderr : "";
		return {
			id: surface.id,
			command: surface.command,
			status,
			exitCode: typeof result.status === "number" ? result.status : null,
			signal: result.signal ?? null,
			durationMs,
			stdout: stdout.slice(0, 4_000),
			stderr: stderr.slice(0, 4_000),
			failOpen: true,
			blockHint: BLOCK_JSON_RE.test(stdout) || BLOCK_JSON_RE.test(stderr),
			error: result.error ? (result.error.message.split("\n")[0] ?? String(result.error)) : undefined,
		};
	} catch (error) {
		return {
			id: surface.id,
			command: surface.command,
			status: "spawn-error",
			exitCode: null,
			signal: null,
			durationMs: Date.now() - startedAt,
			stdout: "",
			stderr: "",
			failOpen: true,
			blockHint: false,
			error: error instanceof Error ? error.message : String(error),
		};
	}
}

export function probeHooks(surfaces: HookSurface[], options: ProbeOptions = {}): HookProbeResult[] {
	return surfaces.map((surface) => probeHook(surface, options));
}

// ── report ───────────────────────────────────────────────────────────────────

export interface BuildReportOptions {
	home?: string;
	timeoutMs?: number;
	contract?: ContractCheck;
}

function emptyContract(): ContractCheck {
	return { status: "not-installed", manifestPath: "", installedByUs: false, stopGate: "none", blockHash: "", surfaces: [] };
}

function knowledgeModuleStatus(surfaces: HookSurface[], id: string): HookAuditChecks["knowledgeInject"] {
	const surface = surfaces.find((candidate) => candidate.id === id);
	if (!surface || surface.meta?.present === false) return "absent";
	return surface.verdict === "can-block" ? "can-block" : "fail-open";
}

function codexTrustCheck(surfaces: HookSurface[]): HookAuditChecks["codexTrust"] {
	const codex = surfaces.filter((surface) => surface.kind === "codex-hook");
	if (!codex.length) return "absent";
	if (codex.some((surface) => surface.trust?.verification === "stale-suspect")) return "warn";
	if (codex.every((surface) => surface.trust?.verification === "unknown" || surface.trust?.verification === "missing")) return "unknown";
	return "pass";
}

export function buildHookReport(surfaces: HookSurface[], probes: HookProbeResult[], options: BuildReportOptions = {}): HookAuditReport {
	const canBlock = surfaces.filter((s) => s.blocking || s.verdict === "can-block").map((s) => s.id);
	const failOpen = surfaces.filter((s) => s.verdict === "fail-open").map((s) => s.id);
	const notProbed = surfaces.filter((s) => !s.probe).map((s) => s.id);
	const blockHint = probes.some((p) => p.blockHint);
	const contract = options.contract ?? emptyContract();
	const knowledgeInject = knowledgeModuleStatus(surfaces, "knowledge:module:knowledge-inject");
	const knowledgeGuard = knowledgeModuleStatus(surfaces, "knowledge:module:knowledge-guard");
	const codexTrust = codexTrustCheck(surfaces);

	const findings: string[] = [];
	if (canBlock.length) findings.push(`can-block surface(s): ${canBlock.join(", ")}`);
	if (blockHint) findings.push("a probe emitted a block/deny decision");
	if (contract.status === "duplicate") findings.push("knowledge contract marker block appears more than once");
	if (contract.status === "missing") findings.push("knowledge contract marker block missing on an installed surface");
	if (contract.status === "stale") findings.push("knowledge contract marker block is stale against the manifest hash");
	if (knowledgeInject === "can-block") findings.push("knowledge-inject is can-block (must be fail-open)");
	if (knowledgeGuard === "can-block") findings.push("knowledge-guard is can-block (must be fail-open)");
	if (contract.stopGate === "present") findings.push("a blocking Stop/hook config was installed by us");
	if (codexTrust === "warn") findings.push("codex hooks.json changed after the trusted_hash record; re-trust required");

	const checks: HookAuditChecks = {
		contractBlock: contract.status,
		contractSurfaces: contract.surfaces.map((surface) => surface.id),
		knowledgeInject,
		knowledgeGuard,
		stopGateInstalledByUs: contract.stopGate,
		codexTrust,
		canBlockCount: canBlock.length,
		findings,
	};

	return {
		version: 1,
		home: options.home ?? os.homedir(),
		ok: findings.length === 0,
		scanned: surfaces.length,
		timeoutMs: clampTimeout(options.timeoutMs),
		canBlock,
		failOpen,
		notProbed,
		checks,
		surfaces,
		probes,
	};
}

export function formatHookReport(report: HookAuditReport): string {
	const checks = report.checks;
	const lines: string[] = [
		`hooks: ${report.scanned} surface(s) · ${report.canBlock.length} can-block · ${report.failOpen.length} fail-open · ${report.notProbed.length} not probed`,
		`checks: contract=${checks.contractBlock} · inject=${checks.knowledgeInject} · guard=${checks.knowledgeGuard} · stopGate=${checks.stopGateInstalledByUs} · codexTrust=${checks.codexTrust}`,
		`verdict: ${report.ok ? "ok" : "NOT OK"} · timeout ${report.timeoutMs}ms · home ${report.home}`,
	];
	for (const finding of checks.findings) lines.push(`finding: ${finding}`);
	for (const surface of report.surfaces) {
		const probe = report.probes.find((p) => p.id === surface.id);
		const probeText = probe ? `${probe.status}${probe.status === "skipped" ? "" : ` exit=${probe.exitCode ?? "?"} ${probe.durationMs}ms`}` : "no probe";
		lines.push(`${surface.blocking ? "CAN-BLOCK" : "fail-open"}  ${surface.id}  [${surface.kind}/${surface.event ?? "-"}]  probe=${probeText}`);
		lines.push(`    ${surface.reason}`);
		lines.push(`    cmd: ${surface.command ?? surface.path ?? surface.source}`);
	}
	const failed = report.probes.filter((p) => p.status !== "skipped" && p.status !== "ok");
	if (failed.length) {
		lines.push(`probes that errored or timed out (all reported fail-open): ${failed.map((p) => `${p.id}=${p.status}`).join(", ")}`);
	}
	return lines.join("\n");
}
