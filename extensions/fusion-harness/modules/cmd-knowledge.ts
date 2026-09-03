/**
 * cmd-knowledge.ts — /fh-knowledge status | search | refresh | capture
 *
 * Inspection is read-only. Capture obtains the checkout writer lease and the
 * vault-scoped lock. Pi has no built-in MCP; this command does not advertise one.
 */

import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { formatKnowledgeStatus, retrieveKnowledge, refreshKnowledgeCache } from "./knowledge-base.ts";
import { acquireWriterLease } from "./writer-lease.ts";
import type { HarnessDeps } from "./runtime.ts";

export function registerKnowledgeCommand(pi: ExtensionAPI, h: HarnessDeps): void {
	pi.registerCommand("fh-knowledge", {
		description: "Inspect harness knowledge: status, search <query>, refresh, capture on|off. Read-only except capture.",
		handler: async (raw, ctx) => {
			h.noteHost(ctx);
			const input = (raw ?? "").trim();
			const [head, ...rest] = input.split(/\s+/);
			const action = (head || "status").toLowerCase();
			const config = h.knowledgeConfig(ctx.cwd);

			if (action === "capture") {
				const next = (rest[0] ?? "").toLowerCase();
				if (next !== "on" && next !== "off") {
					ctx.ui.notify(`fusion-harness: knowledge capture is ${h.knowledgeCaptureEnabled() ? "on" : "off"} (opt-in). Usage: /fh-knowledge capture on|off`, "info");
					return;
				}
				if (next === "off") {
					h.setKnowledgeCapture(false);
					ctx.ui.notify("fusion-harness: knowledge capture off — no vault write-back", "info");
					return;
				}
				let writer;
				try {
					writer = acquireWriterLease(ctx.cwd, "/fh-knowledge capture");
				} catch (error) {
					ctx.ui.notify(error instanceof Error ? error.message : String(error), "error");
					return;
				}
				try {
					h.setKnowledgeCapture(true);
					ctx.ui.notify("fusion-harness: knowledge capture on — write-capable runs may file a ## Vault note into wiki/agent-learnings.md (never trading/ or sessions/). Pi has no MCP.", "info");
				} finally {
					writer.release();
				}
				return;
			}

			if (action === "refresh") {
				refreshKnowledgeCache();
				const packet = retrieveKnowledge({ query: "status", cwd: ctx.cwd, config });
				ctx.ui.notify(`fusion-harness: knowledge cache refreshed\n${formatKnowledgeStatus(packet, config)}`, "info");
				return;
			}

			if (action === "search") {
				const query = rest.join(" ").trim();
				if (!query) {
					ctx.ui.notify("Usage: /fh-knowledge search <query>", "warning");
					return;
				}
				const packet = retrieveKnowledge({ query, cwd: ctx.cwd, config });
				const hits = packet.hits.length
					? packet.hits.map((hit, i) => `${i + 1}. ${hit.path}:${hit.startLine}-${hit.endLine}  score=${hit.score.toFixed(1)}  ${hit.heading}`).join("\n")
					: "wiki miss: no relevant knowledge chunks for this query.";
				ctx.ui.notify(
					[
						`knowledge search  status=${packet.status}  hash=${packet.hash.slice(0, 12)}  hits=${packet.hits.length}`,
						hits,
						packet.errors.length ? `errors: ${packet.errors.join("; ")}` : "",
					]
						.filter(Boolean)
						.join("\n"),
					packet.status === "error" ? "error" : "info",
				);
				return;
			}

			if (action !== "status") {
				ctx.ui.notify("Usage: /fh-knowledge status|search <query>|refresh|capture on|off", "warning");
				return;
			}

			const packet = retrieveKnowledge({ query: "status", cwd: ctx.cwd, config });
			ctx.ui.notify(
				[
					formatKnowledgeStatus(packet, config),
					`cwd fallback: ${path.join(ctx.cwd, "ai_docs")}`,
					"MCP is not used: Pi has no built-in MCP, and clean-room children stay --no-skills/--no-extensions/--no-context-files.",
					"This improves evidence context; it does not train models.",
				].join("\n"),
				"info",
			);
		},
	});
}
