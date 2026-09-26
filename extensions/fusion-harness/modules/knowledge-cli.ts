/**
 * knowledge-cli.ts — standalone CLI over the existing knowledge retriever.
 *
 * This is the transport every non-Pi runtime (Claude Code, Codex, Hermes, ADW
 * workflows, factory seats) can call. It imports NO pi API: only the same
 * `resolveKnowledgeConfig` + `retrieveKnowledge` the Pi host uses, so a query
 * produces the same packet as `/fh-knowledge`.
 *
 * Subcommands: status | search <query> | brief <query>
 * Flags:       --cwd <dir> | --json | --markdown | --max-bytes <n> | --fh-knowledge off
 *
 * Exit codes: 0 for passed, wiki miss, and disabled; 2 for a real error
 * (unreadable roots yielding no hits, or a usage error). Knowledge never
 * blocks a task on absence.
 */

import * as os from "node:os";
import * as path from "node:path";
import { buildBrief, type Brief } from "./knowledge-brief.ts";
import { formatKnowledgeStatus, type KnowledgePacket, retrieveKnowledge } from "./knowledge-base.ts";
import { resolveKnowledgeConfig } from "./knowledge-config.ts";

export interface KnowledgeCliOpts {
	/** Default working directory when `--cwd` is absent. Defaults to process.cwd(). */
	cwd?: string;
	/** Environment for config resolution. Defaults to process.env. */
	env?: NodeJS.Dict<string>;
	/** Home directory for vault detection. Defaults to os.homedir(). */
	homedir?: string;
}

export interface KnowledgeCliResult {
	exitCode: number;
	stdout: string;
	stderr: string;
	/** The packet the run resolved, when one was produced (absent on usage errors). */
	packet?: KnowledgePacket;
}

type Action = "status" | "search" | "brief" | "help";

interface ParsedArgs {
	action: Action;
	query: string;
	cwd: string;
	json: boolean;
	markdown: boolean;
	maxBytes?: number;
	knowledgeFlag?: string;
	error?: string;
}

export const KNOWLEDGE_CLI_USAGE = [
	"Usage: fh-knowledge status [--cwd DIR] [--json] [--markdown] [--fh-knowledge off]",
	"       fh-knowledge search <query> [--cwd DIR] [--json] [--markdown] [--max-bytes N] [--fh-knowledge off]",
	"       fh-knowledge brief <query> [--cwd DIR] [--json] [--markdown] [--max-bytes N] [--fh-knowledge off]",
	"",
	"Retrieves the same immutable evidence packet the Pi host injects. Read-only.",
	"brief prints the distilled brief (knowledge-brief.ts) before the packet.",
	"Exit 0 for passed, wiki miss, and disabled; exit 2 only for a real error.",
].join("\n");

/**
 * Stable top-level JSON keys, in output order. A test asserts these exact keys
 * so downstream consumers can rely on the shape across releases.
 */
export const KNOWLEDGE_CLI_JSON_KEYS = [
	"command",
	"query",
	"status",
	"enabled",
	"captureEnabled",
	"hash",
	"hits",
	"bytes",
	"maxBytes",
	"roots",
	"vaultRoot",
	"indexedFiles",
	"indexedChunks",
	"skipped",
	"errors",
	"reasons",
	"retrievedAt",
	"chunks",
] as const;

/**
 * Stable top-level JSON keys for `brief`, in output order. Deliberately separate
 * from KNOWLEDGE_CLI_JSON_KEYS so adding the brief cannot shift the search/status
 * shape downstream consumers already parse.
 */
export const KNOWLEDGE_CLI_BRIEF_JSON_KEYS = [
	"command",
	"query",
	"status",
	"enabled",
	"captureEnabled",
	"packetHash",
	"briefHash",
	"packetBytes",
	"briefBytes",
	"maxBytes",
	"briefTruncated",
	"roots",
	"vaultRoot",
	"indexedFiles",
	"indexedChunks",
	"skipped",
	"errors",
	"reasons",
	"retrievedAt",
	"sections",
	"chunks",
	"briefMarkdown",
] as const;

function takeValue(argv: string[], index: number, name: string): { value?: string; next: number; error?: string } {
	const token = argv[index];
	const eq = token.indexOf("=");
	if (eq !== -1) {
		const value = token.slice(eq + 1);
		return value ? { value, next: index + 1 } : { error: `${name} needs a value` };
	}
	const value = argv[index + 1];
	if (value === undefined || value.startsWith("-")) return { error: `${name} needs a value` };
	return { value, next: index + 2 };
}

export function parseKnowledgeCliArgs(argv: string[], defaultCwd: string): ParsedArgs {
	const parsed: ParsedArgs = { action: "help", query: "", cwd: path.resolve(defaultCwd), json: false, markdown: false };
	const rest: string[] = [];
	for (let i = 0; i < argv.length; i++) {
		const token = argv[i];
		if (token === "--json") {
			parsed.json = true;
		} else if (token === "--markdown") {
			parsed.markdown = true;
		} else if (token === "-h" || token === "--help") {
			parsed.action = "help";
			return parsed;
		} else if (token === "--cwd" || token.startsWith("--cwd=")) {
			const got = takeValue(argv, i, "--cwd");
			if (got.error) return { ...parsed, error: got.error };
			// Resolve against the caller's cwd so relative --cwd and relative --fh-knowledge roots agree.
			parsed.cwd = path.resolve(defaultCwd, got.value!);
			i = got.next - 1;
		} else if (token === "--max-bytes" || token.startsWith("--max-bytes=")) {
			const got = takeValue(argv, i, "--max-bytes");
			if (got.error) return { ...parsed, error: got.error };
			const n = Number.parseInt(got.value!, 10);
			if (!Number.isFinite(n) || n <= 0) return { ...parsed, error: `--max-bytes must be a positive integer, got ${JSON.stringify(got.value)}` };
			parsed.maxBytes = n;
			i = got.next - 1;
		} else if (token === "--fh-knowledge" || token.startsWith("--fh-knowledge=")) {
			const got = takeValue(argv, i, "--fh-knowledge");
			if (got.error) return { ...parsed, error: got.error };
			parsed.knowledgeFlag = got.value;
			i = got.next - 1;
		} else if (token.startsWith("-") && token !== "-") {
			return { ...parsed, error: `unknown flag ${token}` };
		} else {
			rest.push(token);
		}
	}
	const head = rest[0];
	if (!head) {
		parsed.action = "status";
		return parsed;
	}
	if (head === "status") {
		parsed.action = "status";
		return parsed;
	}
	if (head === "search") {
		parsed.action = "search";
		parsed.query = rest.slice(1).join(" ").trim();
		if (!parsed.query) return { ...parsed, error: "search needs a query" };
		return parsed;
	}
	if (head === "brief") {
		parsed.action = "brief";
		parsed.query = rest.slice(1).join(" ").trim();
		if (!parsed.query) return { ...parsed, error: "brief needs a query" };
		return parsed;
	}
	return { ...parsed, error: `unknown subcommand ${JSON.stringify(head)}` };
}

function utf8Bytes(text: string): number {
	return Buffer.byteLength(text, "utf8");
}

function evidenceBytes(packet: KnowledgePacket): number {
	return packet.hits.reduce((sum, hit) => sum + utf8Bytes(hit.text), 0);
}

function renderJson(command: "status" | "search", packet: KnowledgePacket, maxBytes: number): string {
	const chunks = packet.hits.map((hit) => ({
		path: hit.path,
		startLine: hit.startLine,
		endLine: hit.endLine,
		heading: hit.heading,
		score: hit.score,
		bytes: utf8Bytes(hit.text),
		text: hit.text,
	}));
	// Object literal order is the frozen stable key order in KNOWLEDGE_CLI_JSON_KEYS.
	const payload = {
		command,
		query: packet.query,
		status: packet.status,
		enabled: packet.enabled,
		captureEnabled: packet.captureEnabled,
		hash: packet.hash,
		hits: packet.hits.length,
		bytes: evidenceBytes(packet),
		maxBytes,
		roots: packet.roots,
		vaultRoot: packet.vaultRoot ?? null,
		indexedFiles: packet.indexedFiles,
		indexedChunks: packet.indexedChunks,
		skipped: packet.skipped.length,
		errors: packet.errors,
		reasons: packet.reasons,
		retrievedAt: packet.retrievedAt,
		chunks,
	};
	return `${JSON.stringify(payload, null, 2)}\n`;
}

function renderSearchText(packet: KnowledgePacket): string {
	const header = `knowledge search  status=${packet.status}  hash=${packet.hash.slice(0, 12)}  hits=${packet.hits.length}`;
	if (!packet.hits.length) return `${header}\nwiki miss: no relevant knowledge chunks for this query.`;
	const lines = packet.hits.map(
		(hit, i) => `${i + 1}. ${hit.path}:${hit.startLine}-${hit.endLine}  score=${hit.score.toFixed(1)}  ${hit.heading}`,
	);
	return [header, ...lines, ...packet.errors.map((e) => `error: ${e}`)].join("\n");
}

/** Brief first, then the immutable packet: the same order the host prepends on a first turn. */
function renderBriefText(packet: KnowledgePacket, brief: Brief): string {
	return `${[brief.briefMarkdown.trimEnd(), "", packet.packetMarkdown.trimEnd()].join("\n")}\n`;
}

function renderBriefJson(packet: KnowledgePacket, brief: Brief, maxBytes: number): string {
	const chunks = packet.hits.map((hit) => ({
		path: hit.path,
		startLine: hit.startLine,
		endLine: hit.endLine,
		heading: hit.heading,
		score: hit.score,
		bytes: utf8Bytes(hit.text),
		text: hit.text,
	}));
	const sections = brief.sections.map((section) => ({
		id: section.id,
		title: section.title,
		items: section.items.map((item) => ({
			claim: item.claim,
			citation: item.citation,
			path: item.path,
			startLine: item.startLine,
			endLine: item.endLine,
			score: item.score,
			...(item.n ? { n: item.n } : {}),
			...(item.confidence ? { confidence: item.confidence } : {}),
		})),
	}));
	// Object literal order is the frozen stable key order in KNOWLEDGE_CLI_BRIEF_JSON_KEYS.
	const payload = {
		command: "brief",
		query: packet.query,
		status: packet.status,
		enabled: packet.enabled,
		captureEnabled: packet.captureEnabled,
		packetHash: packet.hash,
		briefHash: brief.briefHash,
		packetBytes: evidenceBytes(packet),
		briefBytes: brief.bytes,
		maxBytes,
		briefTruncated: brief.truncated,
		roots: packet.roots,
		vaultRoot: packet.vaultRoot ?? null,
		indexedFiles: packet.indexedFiles,
		indexedChunks: packet.indexedChunks,
		skipped: packet.skipped.length,
		errors: packet.errors,
		reasons: packet.reasons,
		retrievedAt: packet.retrievedAt,
		sections,
		chunks,
		briefMarkdown: brief.briefMarkdown,
	};
	return `${JSON.stringify(payload, null, 2)}\n`;
}

function renderStatusMarkdown(packet: KnowledgePacket, config: ReturnType<typeof resolveKnowledgeConfig>): string {
	return ["# Knowledge status", "", formatKnowledgeStatus(packet, config)].join("\n");
}

function exitCodeFor(packet: KnowledgePacket): number {
	// A miss and a disabled config are successful non-answers, not errors.
	return packet.status === "error" ? 2 : 0;
}

/**
 * Pure entrypoint: parse, retrieve, render. Never calls process.exit and never
 * writes to a stream, so tests can assert on the returned strings directly.
 */
export function runKnowledgeCli(argv: string[], opts: KnowledgeCliOpts = {}): KnowledgeCliResult {
	const defaultCwd = opts.cwd ?? process.cwd();
	const env = opts.env ?? process.env;
	const homedir = opts.homedir ?? os.homedir();
	const parsed = parseKnowledgeCliArgs(argv, defaultCwd);
	if (parsed.error) return { exitCode: 2, stdout: "", stderr: `fh-knowledge: ${parsed.error}\n${KNOWLEDGE_CLI_USAGE}\n` };
	if (parsed.action === "help") return { exitCode: 0, stdout: `${KNOWLEDGE_CLI_USAGE}\n`, stderr: "" };

	const config = resolveKnowledgeConfig({ cwd: parsed.cwd, flag: parsed.knowledgeFlag, env, homedir });
	const effective = parsed.maxBytes !== undefined ? { ...config, packetBytes: parsed.maxBytes } : config;

	if (parsed.action === "status") {
		const packet = retrieveKnowledge({ query: "status", cwd: parsed.cwd, config: effective });
		const stdout = parsed.json
			? renderJson("status", packet, effective.packetBytes)
			: parsed.markdown
				? `${renderStatusMarkdown(packet, effective)}\n`
				: `${formatKnowledgeStatus(packet, effective)}\n`;
		return { exitCode: exitCodeFor(packet), stdout, stderr: "", packet };
	}

	if (parsed.action === "brief") {
		const packet = retrieveKnowledge({ query: parsed.query, cwd: parsed.cwd, config: effective });
		const brief = buildBrief(packet, { maxBytes: effective.packetBytes });
		const stdout = parsed.json
			? renderBriefJson(packet, brief, effective.packetBytes)
			: renderBriefText(packet, brief);
		return { exitCode: exitCodeFor(packet), stdout, stderr: "", packet };
	}

	const packet = retrieveKnowledge({ query: parsed.query, cwd: parsed.cwd, config: effective });
	const stdout = parsed.json
		? renderJson("search", packet, effective.packetBytes)
		: parsed.markdown
			? `${packet.packetMarkdown}\n`
			: `${renderSearchText(packet)}\n`;
	return { exitCode: exitCodeFor(packet), stdout, stderr: "", packet };
}

/** Stream-writing wrapper used by bin/fh-knowledge. Returns the process exit code. */
export function main(argv: string[] = process.argv.slice(2)): number {
	const result = runKnowledgeCli(argv);
	if (result.stdout) process.stdout.write(result.stdout.endsWith("\n") ? result.stdout : `${result.stdout}\n`);
	if (result.stderr) process.stderr.write(result.stderr.endsWith("\n") ? result.stderr : `${result.stderr}\n`);
	return result.exitCode;
}
