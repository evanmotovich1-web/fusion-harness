#!/usr/bin/env bun
/**
 * knowledge-install.ts — idempotent, marker-delimited installer for the global
 * knowledge contract.
 *
 * It inserts `prompts/KNOWLEDGE_GLOBAL_CONTRACT.md` into a fixed set of agent
 * instruction surfaces, inside `<!-- fh-knowledge:begin -->` / `<!-- fh-knowledge:end -->`.
 * It only ever writes that marker region (or appends it to a file that has none), so user
 * text outside the markers is byte-preserved. `--uninstall --apply` restores the recorded
 * original bytes.
 *
 * Safety:
 *   - Dry-run by default. Nothing is written without `--apply`.
 *   - Refuses to write to the real `$HOME` unless `--allow-real-home` is passed, so a
 *     mistaken invocation cannot touch the operator's live config.
 *   - ADW/SSSF surfaces are skipped unless `--allow-adw` is passed. `--adw-path FILE`
 *     targets one prompt; `--adw-dir DIR` targets every `system.md` found under it. This
 *     build does NOT claim SSSF/ADW coverage until separately authorized.
 *   - Encodes the 1.e rule set: fail-open only. It installs a prompt fragment, never a
 *     blocking Stop hook or any hook that can refuse a run.
 *
 * Usage:
 *   bun tools/knowledge-install.ts [--home DIR] [--manifest DIR] [--contract FILE]
 *       [--check] [--uninstall] [--apply] [--json]
 *       [--adw-path FILE | --adw-dir DIR] [--allow-adw] [--allow-real-home] [--help]
 *
 * Modes:
 *   default / --check   print the install plan (no writes)
 *   --uninstall         print the uninstall plan (no writes)
 *   --apply             commit the selected mode
 */

import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

// pi runs under Node: import.meta.dir is Bun-only, so derive the module dir the way
// prompt-library.ts and modules/hook-audit.ts do.
const MODULE_DIR: string =
	typeof __dirname !== "undefined" && __dirname
		? __dirname
		: path.dirname(new URL(import.meta.url).pathname);

export const CONTRACT_BEGIN = "<!-- fh-knowledge:begin -->";
export const CONTRACT_END = "<!-- fh-knowledge:end -->";

export const DEFAULT_MANIFEST_DIRNAME = ".fh-knowledge";
export const MANIFEST_VERSION = 1;

export type InstallMode = "install" | "uninstall";
export type SurfaceKind = "pi" | "root" | "claude" | "codex" | "hermes" | "adw";

export interface InstallSurface {
	id: string;
	label: string;
	kind: SurfaceKind;
	path: string;
	/** Optional surfaces are skipped unless explicitly enabled. */
	optional?: boolean;
}

export interface ManifestEntry {
	id: string;
	path: string;
	existedBefore: boolean;
	createdByUs: boolean;
	originalHash: string;
	installedHash: string;
	insertedText: string;
	blockHash: string;
}

export interface InstallManifest {
	version: number;
	contractHash: string;
	entries: ManifestEntry[];
}

export interface SurfaceResult {
	id: string;
	label: string;
	path: string;
	status: string;
	changed: boolean;
	blockHash: string;
	diff: string;
	reason: string;
}

export interface KnowledgeInstallReport {
	version: 1;
	mode: InstallMode;
	applied: boolean;
	home: string;
	contractHash: string;
	manifestPath: string;
	surfaces: SurfaceResult[];
}

export const KNOWLEDGE_INSTALL_JSON_KEYS = [
	"version",
	"mode",
	"applied",
	"home",
	"contractHash",
	"manifestPath",
	"surfaces",
] as const;

export const SURFACE_JSON_KEYS = ["id", "label", "path", "status", "changed", "blockHash", "diff", "reason"] as const;

export interface InstallOptions {
	home?: string;
	manifestDir?: string;
	contractPath?: string;
	adwPath?: string;
	adwDir?: string;
	allowAdw?: boolean;
	allowRealHome?: boolean;
}

export interface RunResult {
	exitCode: number;
	stdout: string;
	stderr: string;
	report: KnowledgeInstallReport;
}

// ── hashing + contract rendering ─────────────────────────────────────────────

export function sha256(text: string): string {
	return createHash("sha256").update(text, "utf8").digest("hex");
}

/** Inner contract text, with a single pair of markers stripped if the file carries them. */
export function extractContractBody(raw: string): string {
	const begin = raw.indexOf(CONTRACT_BEGIN);
	const end = raw.indexOf(CONTRACT_END, begin);
	if (begin !== -1 && end !== -1) return raw.slice(begin + CONTRACT_BEGIN.length, end).trim();
	return raw.trim();
}

/** The exact block installed into every surface. Deterministic. */
export function renderContractBlock(inner: string): string {
	return `${CONTRACT_BEGIN}\n${inner.trim()}\n${CONTRACT_END}`;
}

/** Current marker block in a file, or null when the file has no marker. */
export function currentBlockOf(content: string): string | null {
	const begin = content.indexOf(CONTRACT_BEGIN);
	if (begin === -1) return null;
	const end = content.indexOf(CONTRACT_END, begin);
	if (end === -1) return content.slice(begin).trimEnd();
	return content.slice(begin, end + CONTRACT_END.length);
}

/**
 * Insert or replace the marker block. Returns the exact text inserted when the file had
 * no marker (so uninstall can restore byte-identical originals), or null when an existing
 * marker region was replaced.
 */
export function installBlock(original: string, block: string): { content: string; insertedText: string | null } {
	const begin = original.indexOf(CONTRACT_BEGIN);
	if (begin !== -1) {
		const end = original.indexOf(CONTRACT_END, begin);
		if (end === -1) return { content: `${original.slice(0, begin)}${block}\n`, insertedText: null };
		return { content: `${original.slice(0, begin)}${block}${original.slice(end + CONTRACT_END.length)}`, insertedText: null };
	}
	const separator = original.length === 0 ? "" : original.endsWith("\n") ? "\n" : "\n\n";
	const insertedText = `${separator}${block}\n`;
	return { content: `${original}${insertedText}`, insertedText };
}

/** Best-effort marker removal used when no recorded insertion is available. */
export function stripBlock(content: string): string {
	const begin = content.indexOf(CONTRACT_BEGIN);
	if (begin === -1) return content;
	const end = content.indexOf(CONTRACT_END, begin);
	const endIndex = end === -1 ? content.length : end + CONTRACT_END.length;
	let before = content.slice(0, begin);
	let after = content.slice(endIndex);
	if (before.endsWith("\n\n") && after.startsWith("\n")) {
		before = before.slice(0, -1);
		after = after.slice(1);
	}
	return (before + after).replace(/\n{3,}/g, "\n\n");
}

// ── line diff (bounded; contract is ~1 KB) ───────────────────────────────────

export function lineDiff(expected: string, actual: string): string {
	const a = expected.split("\n");
	const b = actual.split("\n");
	const n = a.length;
	const m = b.length;
	const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
	for (let i = n - 1; i >= 0; i--) {
		for (let j = m - 1; j >= 0; j--) {
			lcs[i]![j] = a[i] === b[j] ? lcs[i + 1]![j + 1]! + 1 : Math.max(lcs[i + 1]![j]!, lcs[i]![j + 1]!);
		}
	}
	const lines: string[] = [];
	let i = 0;
	let j = 0;
	while (i < n && j < m) {
		if (a[i] === b[j]) {
			i++;
			j++;
		} else if (lcs[i + 1]![j]! >= lcs[i]![j + 1]!) {
			lines.push(`- ${a[i]}`);
			i++;
		} else {
			lines.push(`+ ${b[j]}`);
			j++;
		}
	}
	while (i < n) lines.push(`- ${a[i++]}`);
	while (j < m) lines.push(`+ ${b[j++]}`);
	return lines.join("\n");
}

// ── surfaces ─────────────────────────────────────────────────────────────────

function isDirectory(p: string): boolean {
	try {
		return fs.statSync(p).isDirectory();
	} catch {
		return false;
	}
}

/** Every `system.md` under a directory tree, sorted for deterministic output. */
export function findSystemPrompts(root: string): string[] {
	const out: string[] = [];
	if (!isDirectory(root)) return out;
	const visit = (dir: string): void => {
		let entries: fs.Dirent[];
		try {
			entries = fs.readdirSync(dir, { withFileTypes: true });
		} catch {
			return;
		}
		entries.sort((a, b) => a.name.localeCompare(b.name));
		for (const entry of entries) {
			const abs = path.join(dir, entry.name);
			if (entry.isSymbolicLink()) continue;
			if (entry.isDirectory()) {
				visit(abs);
				continue;
			}
			if (entry.isFile() && entry.name === "system.md") out.push(abs);
		}
	};
	visit(path.resolve(root));
	return out;
}

/** ADW/SSSF surfaces: one file via `--adw-path`, or every `system.md` under `--adw-dir`. */
export function adwSurfacesFor(adwPath?: string, adwDir?: string): InstallSurface[] {
	const surfaces: InstallSurface[] = [];
	if (adwPath) {
		surfaces.push({ id: "adw", label: "ADW/SSSF planner prompt", kind: "adw", path: path.resolve(adwPath), optional: true });
	}
	if (adwDir) {
		const dir = path.resolve(adwDir);
		for (const file of findSystemPrompts(dir)) {
			const rel = path.relative(dir, file).split(path.sep).join("/");
			surfaces.push({ id: `adw:${rel}`, label: `ADW/SSSF planner prompt (${rel})`, kind: "adw", path: file, optional: true });
		}
	}
	return surfaces;
}

export function defaultSurfaces(home: string, options: { adwPath?: string; adwDir?: string; allowAdw?: boolean } = {}): InstallSurface[] {
	const surfaces: InstallSurface[] = [
		{ id: "pi", label: "Pi global AGENTS.md", kind: "pi", path: path.join(home, ".pi", "agent", "AGENTS.md") },
		{ id: "root", label: "Home AGENTS.md", kind: "root", path: path.join(home, "AGENTS.md") },
		{ id: "claude", label: "Claude Code CLAUDE.md", kind: "claude", path: path.join(home, ".claude", "CLAUDE.md") },
		{ id: "codex", label: "Codex AGENTS.md", kind: "codex", path: path.join(home, ".codex", "AGENTS.md") },
		{ id: "hermes", label: "Hermes SOUL.md", kind: "hermes", path: path.join(home, ".hermes", "SOUL.md") },
	];
	// ADW/SSSF is opt-in and never claimed by default.
	const adw = adwSurfacesFor(options.adwPath, options.adwDir);
	if (adw.length) surfaces.push(...adw);
	else surfaces.push({ id: "adw", label: "ADW/SSSF planner prompt", kind: "adw", path: "", optional: true });
	return surfaces;
}

// ── manifest ─────────────────────────────────────────────────────────────────

export function manifestPathFor(manifestDir: string): string {
	return path.join(manifestDir, "manifest.json");
}

export function readManifest(file: string): InstallManifest {
	try {
		const parsed = JSON.parse(fs.readFileSync(file, "utf8"));
		if (parsed && parsed.version === MANIFEST_VERSION && Array.isArray(parsed.entries)) return parsed as InstallManifest;
	} catch {
		/* absent or corrupt manifest: treat as empty */
	}
	return { version: MANIFEST_VERSION, contractHash: "", entries: [] };
}

function writeManifest(file: string, manifest: InstallManifest): void {
	fs.mkdirSync(path.dirname(file), { recursive: true });
	const ordered: InstallManifest = {
		version: MANIFEST_VERSION,
		contractHash: manifest.contractHash,
		entries: [...manifest.entries].sort((a, b) => a.id.localeCompare(b.id)),
	};
	fs.writeFileSync(file, `${JSON.stringify(ordered, null, 2)}\n`, "utf8");
}

// ── planning ─────────────────────────────────────────────────────────────────

function readFileState(file: string): { exists: boolean; content: string } {
	try {
		return { exists: true, content: fs.readFileSync(file, "utf8") };
	} catch {
		return { exists: false, content: "" };
	}
}

function skippedResult(surface: InstallSurface, blockHash: string, reason: string): SurfaceResult {
	return { id: surface.id, label: surface.label, path: surface.path, status: "skipped", changed: false, blockHash, diff: "", reason };
}

function planInstall(surface: InstallSurface, block: string, blockHash: string, applied: boolean): { result: SurfaceResult; write?: string; entry?: ManifestEntry } {
	const state = readFileState(surface.path);
	const current = currentBlockOf(state.content);
	const { content: next, insertedText } = installBlock(state.content, block);
	const changed = next !== state.content;
	let status: string;
	if (!state.exists) status = "absent";
	else if (current === null) status = "missing";
	else if (current === block) status = "current";
	else status = "stale";
	const diff = status === "stale" && current !== null ? lineDiff(block, current) : "";
	const result: SurfaceResult = {
		id: surface.id,
		label: surface.label,
		path: surface.path,
		status,
		changed,
		blockHash,
		diff,
		reason: status === "current" ? "contract already installed and current" : `contract ${status}; ${applied ? "written" : "would be written"}`,
	};
	if (applied && changed) {
		result.status = "current";
		result.reason = "contract installed";
		return {
			result,
			write: next,
			entry: {
				id: surface.id,
				path: surface.path,
				existedBefore: state.exists,
				createdByUs: !state.exists,
				originalHash: sha256(state.content),
				installedHash: sha256(next),
				insertedText: insertedText ?? "",
				blockHash,
			},
		};
	}
	if (applied && !changed) result.status = "current";
	return { result };
}

function planUninstall(surface: InstallSurface, blockHash: string, manifest: InstallManifest, applied: boolean): { result: SurfaceResult; write?: string; delete?: boolean; removeEntry?: boolean } {
	const state = readFileState(surface.path);
	if (!state.exists) {
		return { result: skippedResult(surface, blockHash, "file absent; nothing to remove"), removeEntry: true };
	}
	if (currentBlockOf(state.content) === null) {
		return { result: skippedResult(surface, blockHash, "no knowledge marker present; left untouched"), removeEntry: true };
	}
	const entry = manifest.entries.find((candidate) => candidate.id === surface.id);
	let next: string;
	let exact = false;
	if (entry && entry.insertedText && state.content.includes(entry.insertedText)) {
		next = state.content.replace(entry.insertedText, "");
		exact = true;
	} else {
		next = stripBlock(state.content);
	}
	const deleteFile = !entry?.existedBefore && next.trim() === "";
	let status: string;
	if (deleteFile) status = "restored";
	else if (exact && entry && sha256(next) === entry.originalHash) status = "restored";
	else if (exact) status = "restored-with-edits";
	else status = "stripped";
	const changed = next !== state.content || deleteFile;
	const result: SurfaceResult = {
		id: surface.id,
		label: surface.label,
		path: surface.path,
		status,
		changed,
		blockHash,
		diff: "",
		reason: exact ? "marker block removed; original bytes restored" : "marker block stripped (no recorded insertion)",
	};
	if (!applied) {
		result.status = "would-uninstall";
		result.reason = `marker present; ${deleteFile ? "file would be deleted" : "block would be removed"}`;
		return { result };
	}
	return { result, write: deleteFile ? undefined : next, delete: deleteFile, removeEntry: true };
}

// ── runner ───────────────────────────────────────────────────────────────────

export interface RunKnowledgeInstallOptions {
	home?: string;
	manifestDir?: string;
	contractPath?: string;
	adwPath?: string;
	adwDir?: string;
	allowAdw?: boolean;
	allowRealHome?: boolean;
	cwd?: string;
}

const HELP = [
	"knowledge-install — install the global knowledge contract into agent instruction surfaces",
	"",
	"Usage: knowledge-install [--home DIR] [--manifest DIR] [--contract FILE]",
	"       [--uninstall] [--apply] [--json] [--adw-path FILE | --adw-dir DIR] [--allow-adw] [--help]",
	"",
	"  (default)      print the install plan; writes nothing",
	"  --check        same as the default",
	"  --uninstall    print the uninstall plan; writes nothing",
	"  --apply        commit the selected mode",
	"  --json         emit the machine-readable report",
	"  --adw-path FILE  install into one ADW/SSSF planner prompt (needs --allow-adw)",
	"  --adw-dir DIR    install into every system.md under DIR (needs --allow-adw)",
	"  --allow-real-home  permit writes against the real $HOME (refused otherwise)",
	"",
	"Marker block: <!-- fh-knowledge:begin --> ... <!-- fh-knowledge:end -->",
	"Always fail-open: this installs a prompt fragment, never a blocking hook.",
].join("\n");

function resolveContractPath(options: RunKnowledgeInstallOptions): string {
	if (options.contractPath) return path.resolve(options.contractPath);
	return path.join(MODULE_DIR, "..", "prompts", "KNOWLEDGE_GLOBAL_CONTRACT.md");
}

function serializeReport(report: KnowledgeInstallReport): string {
	const ordered: Record<string, unknown> = {};
	for (const key of KNOWLEDGE_INSTALL_JSON_KEYS) ordered[key] = (report as unknown as Record<string, unknown>)[key];
	ordered.surfaces = report.surfaces.map((surface) => {
		const row: Record<string, unknown> = {};
		for (const key of SURFACE_JSON_KEYS) row[key] = (surface as unknown as Record<string, unknown>)[key];
		return row;
	});
	return `${JSON.stringify(ordered, null, 2)}\n`;
}

/**
 * Run the installer without touching stdio. Never throws: a missing contract or a refused
 * real-home write yields a report and a nonzero exit code, not an exception.
 */
export function runKnowledgeInstall(argv: string[] = [], options: RunKnowledgeInstallOptions = {}): RunResult {
	const homeArg = argValue(argv, "--home");
	const home = path.resolve(options.home ?? homeArg ?? process.env.HOME ?? os.homedir());
	const manifestArg = argValue(argv, "--manifest");
	const manifestDir = path.resolve(options.manifestDir ?? manifestArg ?? path.join(home, DEFAULT_MANIFEST_DIRNAME));
	const contractArg = argValue(argv, "--contract");
	const contractPath = resolveContractPath({ contractPath: options.contractPath ?? contractArg });
	const manifestFile = manifestPathFor(manifestDir);
	const mode: InstallMode = argv.includes("--uninstall") ? "uninstall" : "install";
	const applied = argv.includes("--apply");
	const json = argv.includes("--json");
	const allowRealHome = options.allowRealHome === true || argv.includes("--allow-real-home");
	const allowAdw = options.allowAdw === true || argv.includes("--allow-adw");
	const adwPath = options.adwPath ?? argValue(argv, "--adw-path");
	const adwDir = options.adwDir ?? argValue(argv, "--adw-dir");
	const blankReport = (): KnowledgeInstallReport => ({
		version: 1,
		mode,
		applied: false,
		home,
		contractHash: "",
		manifestPath: manifestFile,
		surfaces: [],
	});

	if (argv.includes("--help") || argv.includes("-h")) {
		return { exitCode: 0, stdout: `${HELP}\n`, stderr: "", report: blankReport() };
	}

	let raw: string;
	try {
		raw = fs.readFileSync(contractPath, "utf8");
	} catch (error) {
		const report = blankReport();
		return {
			exitCode: 2,
			stdout: json ? serializeReport(report) : "",
			stderr: `knowledge-install: cannot read contract ${contractPath}: ${error instanceof Error ? error.message : String(error)}\n`,
			report,
		};
	}

	const block = renderContractBlock(extractContractBody(raw));
	const blockHash = sha256(block);
	const surfaces = defaultSurfaces(home, { adwPath, adwDir, allowAdw });

	if (applied && home === path.resolve(os.homedir()) && !allowRealHome) {
		const report: KnowledgeInstallReport = { ...blankReport(), contractHash: blockHash };
		report.surfaces = surfaces.map((surface) => skippedResult(surface, blockHash, "refused: real $HOME write requires --allow-real-home"));
		return {
			exitCode: 2,
			stdout: json ? serializeReport(report) : "",
			stderr: "knowledge-install: refused to write the real $HOME without --allow-real-home\n",
			report,
		};
	}

	const manifest = readManifest(manifestFile);
	const results: SurfaceResult[] = [];
	const writes = new Map<string, string | undefined>();
	const deletes = new Set<string>();
	const installedEntries: ManifestEntry[] = [];
	const removedIds = new Set<string>();

	for (const surface of surfaces) {
		if (surface.optional && (!allowAdw || !surface.path)) {
			results.push(
				skippedResult(
					surface,
					blockHash,
					surface.path
						? "optional ADW/SSSF surface: pass --allow-adw to enable; coverage is not claimed"
						: "no ADW surface selected; pass --adw-path FILE or --adw-dir DIR with --allow-adw",
				),
			);
			continue;
		}
		if (mode === "install") {
			const plan = planInstall(surface, block, blockHash, applied);
			results.push(plan.result);
			if (plan.write !== undefined) writes.set(surface.path, plan.write);
			if (plan.entry) installedEntries.push(plan.entry);
		} else {
			const plan = planUninstall(surface, blockHash, manifest, applied);
			results.push(plan.result);
			if (applied && plan.write !== undefined) writes.set(surface.path, plan.write);
			if (applied && plan.delete) deletes.add(surface.path);
			if (applied && plan.removeEntry) removedIds.add(surface.id);
		}
	}

	if (applied) {
		for (const [file, content] of writes) {
			fs.mkdirSync(path.dirname(file), { recursive: true });
			if (content !== undefined) fs.writeFileSync(file, content, "utf8");
		}
		for (const file of deletes) {
			try {
				fs.rmSync(file, { force: true });
			} catch {
				/* best-effort removal */
			}
		}
		if (mode === "install") {
			const byId = new Map(manifest.entries.map((entry) => [entry.id, entry]));
			for (const entry of installedEntries) byId.set(entry.id, entry);
			writeManifest(manifestFile, { version: MANIFEST_VERSION, contractHash: blockHash, entries: [...byId.values()] });
		} else {
			const remaining = manifest.entries.filter((entry) => !removedIds.has(entry.id));
			if (remaining.length) writeManifest(manifestFile, { version: MANIFEST_VERSION, contractHash: blockHash, entries: remaining });
			else {
				try {
					fs.rmSync(manifestFile, { force: true });
				} catch {
					/* best-effort */
				}
			}
		}
	}

	const report: KnowledgeInstallReport = {
		version: 1,
		mode,
		applied,
		home,
		contractHash: blockHash,
		manifestPath: manifestFile,
		surfaces: results,
	};
	const summary = results.map((result) => `${result.status.padEnd(12)} ${result.id.padEnd(7)} ${result.path}${result.diff ? `\n${result.diff}` : ""}`).join("\n");
	const header = `knowledge-install ${mode}${applied ? " (applied)" : " (dry run)"} · contract ${blockHash.slice(0, 12)} · home ${home}`;
	return { exitCode: 0, stdout: json ? serializeReport(report) : `${header}\n${summary}\n`, stderr: "", report };
}

function argValue(argv: string[], flag: string): string | undefined {
	const index = argv.indexOf(flag);
	if (index !== -1 && argv[index + 1] && !argv[index + 1]!.startsWith("--")) return argv[index + 1];
	const prefixed = argv.find((arg) => arg.startsWith(`${flag}=`));
	return prefixed ? prefixed.slice(flag.length + 1) : undefined;
}

/** Stream-writing wrapper. Returns the process exit code. */
export function main(argv: string[] = process.argv.slice(2)): number {
	const result = runKnowledgeInstall(argv);
	if (result.stdout) process.stdout.write(result.stdout.endsWith("\n") ? result.stdout : `${result.stdout}\n`);
	if (result.stderr) process.stderr.write(result.stderr.endsWith("\n") ? result.stderr : `${result.stderr}\n`);
	return result.exitCode;
}

if (import.meta.main) {
	process.exit(main());
}
