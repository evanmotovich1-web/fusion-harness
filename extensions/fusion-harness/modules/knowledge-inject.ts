/**
 * knowledge-inject.ts — plain-turn brief injection for the interactive host.
 *
 * Exports a before_agent_start-style handler. This file does not register it.
 * fusion-harness.ts wiring is owned elsewhere. Clean-room children are launched
 * with --no-extensions, so they never load this module. The handler also refuses
 * when argv contains that flag, in case it is registered in the wrong process.
 *
 * One brief per task. Slash commands and ACK-only turns are skipped. If this
 * turn's system prompt already carries our brief hash, or the vault-semantic
 * hook already appended an evidence session, the handler returns undefined.
 * Retrieve and brief failures go through safeKnowledge and also return undefined.
 * This module holds no module-level state. Each handler instance keeps its own
 * once-per-task set.
 */

import { createHash } from "node:crypto";
import { buildBrief, type Brief } from "./knowledge-brief.ts";
import { safeKnowledge } from "./knowledge-guard.ts";
import type { KnowledgePacket } from "./knowledge-base.ts";

export const BRIEF_HASH_MARK = "fh-knowledge-brief-hash:";
export const CLEAN_ROOM_FLAG = "--no-extensions";

/** Markers printed by ~/.pi/agent/extensions/vault-semantic.ts via vault-semantic hook. */
export const VAULT_SEMANTIC_MARKERS = [
	"Vault sections for this message",
	"Vault sections closest to project",
	"auto semantic search on your words",
] as const;

const HASH_RE = /fh-knowledge-brief-hash:\s*([a-f0-9]{64})/i;

export interface InjectEvent {
	prompt?: string;
	systemPrompt?: string;
	systemPromptOptions?: { cwd?: string };
}

export interface InjectResult {
	systemPrompt: string;
}

export interface KnowledgeInjectDeps {
	retrieve: (query: string, cwd: string) => KnowledgePacket | Promise<KnowledgePacket>;
	build?: (packet: KnowledgePacket, query: string) => Brief;
	argv?: readonly string[];
	cwd?: string;
	timeoutMs?: number;
}

export function isCleanRoomArgv(argv: readonly string[]): boolean {
	return argv.includes(CLEAN_ROOM_FLAG);
}

/** Pi slash command, not an absolute path. */
export function isSlashCommand(prompt: string): boolean {
	const token = prompt.trim().split(/\s+/, 1)[0] ?? "";
	if (!token.startsWith("/") || token.startsWith("//")) return false;
	if (token.slice(1).includes("/")) return false;
	return /^\/[A-Za-z][\w-]*$/.test(token);
}

/** Fusion ACK turn, or a prompt whose only job is to emit ACK FUSION. */
export function isAckOnlyTurn(prompt: string): boolean {
	const text = prompt.trim();
	if (/^ACK FUSION\s+\S+$/i.test(text)) return true;
	if (text.includes("CONTEXT SYNCHRONIZATION ONLY")) return true;
	return /Acknowledge receipt only by replying exactly:\s*ACK FUSION/i.test(text);
}

/**
 * Hash of evidence already on this turn. Our marker wins. A vault-semantic
 * block is hashed so a second injector does not add another session.
 */
export function evidenceSessionHash(systemPrompt: string): string | undefined {
	const marked = HASH_RE.exec(systemPrompt);
	if (marked) return marked[1].toLowerCase();
	const marker = VAULT_SEMANTIC_MARKERS.find((item) => systemPrompt.includes(item));
	if (!marker) return undefined;
	const start = systemPrompt.indexOf(marker);
	return createHash("sha256").update(systemPrompt.slice(start, start + 4_000)).digest("hex");
}

function taskKey(prompt: string): string {
	return createHash("sha256").update(prompt.trim()).digest("hex");
}

export function createKnowledgeInjectHandler(deps: KnowledgeInjectDeps) {
	const seen = new Set<string>();
	return async function knowledgeBeforeAgentStart(event?: InjectEvent, _ctx?: unknown): Promise<InjectResult | undefined> {
		try {
			if (isCleanRoomArgv(deps.argv ?? process.argv)) return undefined;
			const prompt = String(event?.prompt ?? "");
			const trimmed = prompt.trim();
			if (!trimmed || isSlashCommand(trimmed) || isAckOnlyTurn(trimmed)) return undefined;
			const key = taskKey(trimmed);
			if (seen.has(key)) return undefined;
			const systemPrompt = String(event?.systemPrompt ?? "");
			const existing = evidenceSessionHash(systemPrompt);
			if (existing) {
				seen.add(key);
				return undefined;
			}
			const cwd = event?.systemPromptOptions?.cwd || deps.cwd || process.cwd();
			let built: Brief | undefined;
			const packet = await safeKnowledge(async () => {
				const retrieved = await deps.retrieve(trimmed, cwd);
				built = (deps.build ?? ((item, query) => buildBrief(item, { query })))(retrieved, trimmed);
				return retrieved;
			}, { query: trimmed, timeoutMs: deps.timeoutMs });
			if (!built || packet.status === "error" || packet.status === "disabled") return undefined;
			seen.add(key);
			const addition = `${built.briefMarkdown}${BRIEF_HASH_MARK} ${built.briefHash}\n`;
			const next = systemPrompt.trim() ? `${systemPrompt.replace(/\s+$/u, "")}\n\n${addition}` : addition;
			return { systemPrompt: next };
		} catch {
			return undefined;
		}
	};
}
