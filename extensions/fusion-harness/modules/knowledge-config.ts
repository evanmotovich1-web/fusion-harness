/**
 * knowledge-config.ts — resolve where retrieval reads and whether capture is allowed.
 *
 * Knowledge is retrieved evidence for the current request, not permanent model learning.
 * Roots are explicit or auto-detected; the obsolete /Users/moto path is never used.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

export const DEFAULT_TOP_K = 6;
export const DEFAULT_PACKET_BYTES = 8_000;
export const DEFAULT_FILE_BYTES = 512_000;
export const DEFAULT_CHUNK_BYTES = 1_800;
export const DEFAULT_MAX_FILES = 2_000;
export const ALLOWED_EXTENSIONS = [".md", ".markdown", ".txt"] as const;
export const VAULT_ALLOWED_DIRS = ["wiki", "me"] as const;
export const DENIED_DIR_NAMES = ["trading", "sessions", "agent-memory", "node_modules", ".git", ".obsidian", ".llmwiki"] as const;
export const PROJECT_FALLBACK_DIR = "ai_docs";
export const DEFAULT_CAPTURE_RELATIVE = "wiki/agent-learnings.md";

const MOTO_PATH = "/Users/moto";

export interface KnowledgeConfig {
	enabled: boolean;
	roots: string[];
	requestedRoots: string[];
	projectFallback: string;
	vaultRoot?: string;
	allowedExtensions: string[];
	deniedDirNames: string[];
	topK: number;
	packetBytes: number;
	fileBytes: number;
	chunkBytes: number;
	maxFiles: number;
	captureOptIn: boolean;
	captureRelative: string;
	reasons: string[];
}

export interface ResolveKnowledgeConfigOpts {
	cwd: string;
	flag?: string;
	captureFlag?: string;
	env?: NodeJS.Dict<string>;
	homedir?: string;
}

function existsDir(p: string): boolean {
	try {
		return fs.statSync(p).isDirectory();
	} catch {
		return false;
	}
}

function canonical(p: string): string {
	try {
		return fs.realpathSync.native(p);
	} catch {
		return path.resolve(p);
	}
}

function isObsoleteMoto(p: string, homedir: string): boolean {
	const resolved = path.resolve(p);
	if (!resolved.startsWith(MOTO_PATH)) return false;
	return !homedir.startsWith(MOTO_PATH);
}

/** Detect the operator's second-brain vault without following the obsolete moto path. */
export function detectSecondBrainVault(env: NodeJS.Dict<string> = process.env, homedir = os.homedir()): string | undefined {
	const fromEnv = (env.SECOND_BRAIN_VAULT ?? "").trim();
	if (fromEnv) {
		if (isObsoleteMoto(fromEnv, homedir)) return undefined;
		if (existsDir(fromEnv)) return canonical(fromEnv);
		return undefined;
	}
	for (const candidate of [path.join(homedir, "code", "second-brain"), path.join(homedir, "second-brain")]) {
		if (isObsoleteMoto(candidate, homedir)) continue;
		if (existsDir(candidate)) return canonical(candidate);
	}
	return undefined;
}

function parseOff(value: string): boolean {
	return ["off", "false", "0", "no"].includes(value.trim().toLowerCase());
}

function parseOn(value: string): boolean {
	return ["on", "true", "1", "yes"].includes(value.trim().toLowerCase());
}

function uniqueExisting(paths: string[]): string[] {
	const seen = new Set<string>();
	const out: string[] = [];
	for (const p of paths) {
		if (!existsDir(p)) continue;
		const key = canonical(p);
		if (seen.has(key)) continue;
		seen.add(key);
		out.push(key);
	}
	return out;
}

export function resolveKnowledgeConfig(opts: ResolveKnowledgeConfigOpts): KnowledgeConfig {
	const env = opts.env ?? process.env;
	const homedir = opts.homedir ?? os.homedir();
	const cwd = path.resolve(opts.cwd);
	const projectFallback = path.join(cwd, PROJECT_FALLBACK_DIR);
	const reasons: string[] = [];
	const captureRelative = DEFAULT_CAPTURE_RELATIVE;
	const captureOptIn = parseOn(opts.captureFlag ?? "") || parseOn(env.FH_KNOWLEDGE_CAPTURE ?? "");
	const vaultRoot = detectSecondBrainVault(env, homedir);

	const base = {
		projectFallback,
		vaultRoot,
		allowedExtensions: [...ALLOWED_EXTENSIONS],
		deniedDirNames: [...DENIED_DIR_NAMES],
		topK: DEFAULT_TOP_K,
		packetBytes: DEFAULT_PACKET_BYTES,
		fileBytes: DEFAULT_FILE_BYTES,
		chunkBytes: DEFAULT_CHUNK_BYTES,
		maxFiles: DEFAULT_MAX_FILES,
		captureOptIn,
		captureRelative,
	};

	const flag = (opts.flag ?? "").trim();
	if (flag && parseOff(flag)) {
		reasons.push("disabled by --fh-knowledge off");
		return { ...base, enabled: false, roots: [], requestedRoots: [], reasons };
	}
	if (!flag && parseOff(env.FH_KNOWLEDGE ?? "")) {
		reasons.push("disabled by FH_KNOWLEDGE=off");
		return { ...base, enabled: false, roots: [], requestedRoots: [], reasons };
	}

	if (flag) {
		const requestedRoots = flag
			.split(",")
			.map((part) => part.trim())
			.filter(Boolean)
			.map((part) => (path.isAbsolute(part) ? part : path.resolve(cwd, part)))
			.filter((part) => {
				if (isObsoleteMoto(part, homedir)) {
					reasons.push(`ignored obsolete moto path ${part}`);
					return false;
				}
				return true;
			});
		const roots = uniqueExisting(requestedRoots);
		if (!roots.length) {
			reasons.push("explicit --fh-knowledge roots were empty or missing");
			return { ...base, enabled: false, roots: [], requestedRoots, reasons };
		}
		reasons.push(`explicit roots: ${roots.join(", ")}`);
		return { ...base, enabled: true, roots, requestedRoots, reasons };
	}

	const requestedRoots: string[] = [];
	if (vaultRoot) {
		for (const dir of VAULT_ALLOWED_DIRS) requestedRoots.push(path.join(vaultRoot, dir));
	} else {
		reasons.push("no second-brain vault detected");
	}
	requestedRoots.push(projectFallback);
	const roots = uniqueExisting(requestedRoots);
	if (!roots.length) {
		reasons.push(`no readable knowledge roots (expected ${PROJECT_FALLBACK_DIR}/ or wiki/+me/)`);
		return { ...base, enabled: false, roots: [], requestedRoots, reasons };
	}
	reasons.push(`auto roots: ${roots.join(", ")}`);
	return { ...base, enabled: true, roots, requestedRoots, reasons };
}
