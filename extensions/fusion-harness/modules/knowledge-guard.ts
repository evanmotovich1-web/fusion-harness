/**
 * Fail-open wrapper for knowledge retrieval.
 * A throw or timeout becomes an empty prompt block. It never throws and never sets process.exitCode.
 */

import { packetHash, type KnowledgePacket } from "./knowledge-base.ts";

export const KNOWLEDGE_GUARD_TIMEOUT_MS = 20_000;

export interface SafeKnowledgeOpts {
	query?: string;
	timeoutMs?: number;
}

function errorPacket(query: string, reason: string): KnowledgePacket {
	const hits: KnowledgePacket["hits"] = [];
	return {
		query,
		hash: packetHash(query, hits),
		status: "error",
		enabled: false,
		captureEnabled: false,
		roots: [],
		hits,
		skipped: [],
		errors: [reason],
		indexedFiles: 0,
		indexedChunks: 0,
		retrievedAt: new Date().toISOString(),
		reasons: [reason],
		promptBlock: "",
		packetMarkdown: "",
	};
}

function isPacket(value: unknown): value is KnowledgePacket {
	return !!value && typeof value === "object" && typeof (value as KnowledgePacket).hash === "string" && typeof (value as KnowledgePacket).promptBlock === "string";
}

/** Run retrieval. Throw and timeout both return a spawnable empty-prompt packet. */
export async function safeKnowledge(
	fn: () => KnowledgePacket | Promise<KnowledgePacket>,
	opts: SafeKnowledgeOpts = {},
): Promise<KnowledgePacket> {
	const query = opts.query ?? "";
	const timeoutMs = opts.timeoutMs ?? KNOWLEDGE_GUARD_TIMEOUT_MS;
	try {
		const result = fn();
		if (result && typeof (result as Promise<KnowledgePacket>).then === "function") {
			const pending = result as Promise<KnowledgePacket>;
			pending.catch(() => {
				/* late rejection after timeout must not become an unhandled rejection */
			});
			let timer: ReturnType<typeof setTimeout> | undefined;
			const packet = await new Promise<KnowledgePacket>((resolve, reject) => {
				timer = setTimeout(() => reject(new Error(`knowledge retrieval timed out after ${timeoutMs}ms`)), timeoutMs);
				pending.then(
					(value) => {
						if (timer) clearTimeout(timer);
						resolve(value);
					},
					(error) => {
						if (timer) clearTimeout(timer);
						reject(error);
					},
				);
			});
			if (!isPacket(packet)) return errorPacket(query, "knowledge retrieval returned a non-packet");
			return packet;
		}
		if (!isPacket(result)) return errorPacket(query, "knowledge retrieval returned a non-packet");
		return result;
	} catch (error) {
		return errorPacket(query, error instanceof Error ? error.message : String(error));
	}
}
