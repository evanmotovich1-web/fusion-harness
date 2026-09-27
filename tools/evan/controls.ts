import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import type { PiSDK } from "./app.ts";
import type { EvanConfig } from "./config.ts";
import { createCodingHandoff, readCodingReceipts, type CodingHandle, type CodingWorker, type CodingPhase } from "./coding-handoff.ts";
import { createPiCodingWorker } from "./coding-worker.ts";
import { openLedger } from "./run-status.ts";

type DisplayContext = Pick<ExtensionContext, "hasUI" | "ui">;
type RunView = { runId: string; phase: CodingPhase; model: string; cost: number | null; started: number; verification: string; tests: string };
const canonical = (root: string) => { try { return fs.realpathSync(root); } catch { return path.resolve(root); } };
function runTime(value: string): number {
  const timestamp = typeof value === "string" ? Date.parse(value) : NaN;
  if (!Number.isFinite(timestamp)) throw new Error("Run record has an invalid start timestamp");
  return timestamp;
}
// UI errors must not detach an active worker or skip its completion/cleanup.
const paint = (render: () => void) => { try { render(); } catch { /* UI may already be shutting down. */ } };
const notify = (ctx: DisplayContext, text: string, kind: "info" | "warning" | "error") => {
  if (ctx.hasUI) paint(() => ctx.ui.notify(text, kind));
};

/** Trusted, user-invoked commands. No LLM-callable delegation or approval tool exists. */
export function createEvanControls(sdk: PiSDK, config: EvanConfig, worker: CodingWorker = createPiCodingWorker(sdk, config)) {
  return (pi: ExtensionAPI) => {
    const handoff = createCodingHandoff(config, worker);
    let pending: CodingHandle | undefined;
    const root = canonical(config.cwd);
    // One project-scoped projection serves every surface. Persisted rows are not liveness evidence.
    const recentRuns = (): RunView[] => {
      const rows = new Map<string, RunView>();
      const phases: Record<string, CodingPhase> = { pending: "uncertain", working: "uncertain", done: "completed", failed: "failed", aborted: "cancelled", timeout: "timeout" };
      for (const row of openLedger(path.join(path.dirname(config.sessionDir), "runs.jsonl")).latest()) {
        if (canonical(row.cwd) !== root) continue;
        rows.set(row.run_id, { runId: row.run_id, phase: phases[row.state] ?? "uncertain", model: row.model,
          cost: row.cost_usd, started: runTime(row.started_at), verification: "unknown", tests: "unknown" });
      }
      for (const receipt of readCodingReceipts(config)) {
        if (canonical(receipt.projectRoot) !== root) continue;
        rows.set(receipt.runId, { runId: receipt.runId, phase: receipt.phase, model: receipt.model,
          cost: rows.get(receipt.runId)?.cost ?? null, started: runTime(receipt.startedAt), verification: receipt.verification, tests: receipt.tests });
      }
      const current = handoff.current();
      if (current) {
        rows.set(current.runId, { runId: current.runId, phase: current.phase, model: current.model,
          cost: rows.get(current.runId)?.cost ?? null, started: runTime(current.startedAt), verification: current.verification, tests: current.tests });
      }
      return [...rows.values()].sort((a, b) =>
        Number(b.runId === current?.runId) - Number(a.runId === current?.runId) || b.started - a.started || b.runId.localeCompare(a.runId)).slice(0, 3);
    };
    const show = (ctx: DisplayContext): RunView[] | undefined => {
      try {
        const recent = recentRuns();
        if (ctx.hasUI) {
          const row = recent[0];
          paint(() => ctx.ui.setStatus("evan-worker", row ? `coding · ${row.phase} · ${row.model} · cost ${row.cost === null ? "unknown" : `$${row.cost}`}` : "coding · no owned runs in this project"));
          paint(() => ctx.ui.setWidget("evan-runs", recent.length ? recent.map((row) =>
            `${row.runId.slice(0, 8)} · ${row.phase} · ${row.model} · cost ${row.cost === null ? "unknown" : `$${row.cost}`}`) : undefined));
        }
        return recent;
      } catch {
        if (ctx.hasUI) {
          paint(() => ctx.ui.setStatus("evan-worker", "coding · status unavailable"));
          paint(() => ctx.ui.setWidget("evan-runs", ["Owned-run status unavailable; no liveness inferred."]));
        }
        return undefined;
      }
    };
    pi.on("session_start", (_event, ctx) => { if (ctx.hasUI) show(ctx); });
    pi.on("session_shutdown", async (_event, ctx) => {
      const handle = pending;
      if (handle) {
        try { handle.cancel(); } catch { notify(ctx, "Cancellation record failed; waiting for worker settlement", "error"); }
        try { await handle.done; } catch { notify(ctx, "Coding worker ended with an evidence error", "error"); }
        if (pending === handle) pending = undefined;
      }
      if (ctx.hasUI) {
        paint(() => ctx.ui.setStatus("evan-worker", undefined));
        paint(() => ctx.ui.setWidget("evan-runs", undefined));
      }
    });
    // /model and restored sessions must not turn the ordinary chat into an unapproved model route.
    pi.on("input", (_event, ctx) => {
      if (ctx.model && `${ctx.model.provider}/${ctx.model.id}` === config.chatModel) return;
      notify(ctx, `Evan chat is pinned to ${config.chatModel}; restore it before sending a turn`, "error");
      return { action: "handled" as const };
    });
    pi.registerCommand("evan-code", {
      description: "Explicit single-file coding handoff: /evan-code relative/path :: objective (no shell or tests)",
      handler: async (args, ctx) => {
        if (pending || !ctx.isIdle()) { notify(ctx, "Evan is busy; wait or /evan-cancel", "error"); return; }
        if (ctx.cwd !== config.cwd) { notify(ctx, "Project changed; coding handoff refused", "error"); return; }
        const split = args.indexOf(" :: ");
        if (split < 1) { notify(ctx, "Usage: /evan-code relative/file :: objective", "error"); return; }
        const file = args.slice(0, split).trim();
        const objective = args.slice(split + 4).trim();
        if (!file || !objective) { notify(ctx, "A file and objective are required", "error"); return; }
        let handle: CodingHandle | undefined;
        try {
          const ownerSessionId = ctx.sessionManager.getSessionId();
          // A single exact path is the entire grant; the model cannot add files or commands.
          handle = handoff.start({ ownerSessionId, objective, readPaths: [file], writePaths: [file] });
          pending = handle;
          show(ctx);
          const result = await handle.done;
          notify(ctx, `${result.phase}: ${result.changes.map((c) => c.path).join(", ") || "no changes"}; readback ${result.verification}; tests ${result.tests}; cost unknown`, result.phase === "completed" ? "info" : "error");
        } catch (error) {
          notify(ctx, `Coding handoff refused/failed: ${error instanceof Error ? error.message : String(error)}`, "error");
        } finally {
          if (pending === handle) pending = undefined;
          show(ctx);
        }
      },
    });
    pi.registerCommand("evan-cancel", {
      description: "Cancel only this Evan process's active coding worker",
      handler: async (_args, ctx) => {
        try {
          if (!pending || !handoff.cancel(pending.runId, ctx.sessionManager.getSessionId())) {
            notify(ctx, "No owned coding run to cancel", "warning"); return;
          }
          notify(ctx, "Cancellation requested; waiting for worker settlement", "info");
        } catch {
          notify(ctx, "Cancellation record failed; worker ownership retained until settlement", "error");
        } finally { show(ctx); }
      },
    });
    pi.registerCommand("evan-runs", {
      description: "Show Evan-owned run receipts; foreign agent coverage is unknown",
      handler: async (_args, ctx) => {
        const rows = show(ctx);
        if (!rows) { notify(ctx, "Owned-run status unavailable; no liveness inferred.", "error"); return; }
        notify(ctx, rows.length ? rows.map((r) => `${r.runId.slice(0, 8)} ${r.phase} · ${r.verification} · tests ${r.tests}`).join(" | ") : "No Evan coding runs in this project. Foreign agent status: unknown.", "info");
      },
    });
  };
}
