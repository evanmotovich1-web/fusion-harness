import * as fs from "node:fs";
import * as path from "node:path";
import { randomUUID } from "node:crypto";
import { acquireWriterLease, isWriterLeaseBusy, type WriterLease } from "../../extensions/fusion-harness/modules/writer-lease.ts";
import type { EvanConfig } from "./config.ts";
import { parseModelId } from "./config.ts";
import { CODING_TOOLS, createCodingFiles, type FileChange, type FileEvent } from "./coding-files.ts";
import { openLedger } from "./run-status.ts";

export type CodingRequest = {
  ownerSessionId: string;
  objective: string;
  readPaths: string[];
  writePaths: string[];
  timeoutMs?: number;
  maxToolCalls?: number;
  maxFileBytes?: number;
};
export type CodingPhase = "queued" | "running" | "cancel_requested" | "completed" | "failed" | "cancelled" | "timeout" | "uncertain";
export type CodingReceipt = {
  schema_version: 1;
  runId: string;
  ownerSessionId: string;
  projectRoot: string;
  model: string;
  objective: string;
  readPaths: string[];
  writePaths: string[];
  tools: string[];
  limits: { timeoutMs: number; maxToolCalls: number; maxFileBytes: number };
  phase: CodingPhase;
  startedAt: string;
  endedAt: string | null;
  events: FileEvent[];
  changes: FileChange[];
  verification: "not-run" | "file-readback-passed" | "file-readback-failed";
  tests: "not-run";
  text: string;
  error: string | null;
};
export type CodingWorkerContext = {
  model: string;
  projectRoot: string;
  objective: string;
  paths: { read: string[]; write: string[] };
  signal: AbortSignal;
  invoke(tool: string, args: unknown): unknown;
};
/** Trusted host adapter. Never choose this callback from model output or restored records. */
export type CodingWorker = (context: CodingWorkerContext) => Promise<{ text: string }>;
export type CodingHandle = { runId: string; done: Promise<CodingReceipt>; cancel(): void };

function integer(value: number | undefined, fallback: number, maximum: number): number {
  const n = value ?? fallback;
  if (!Number.isInteger(n) || n < 1 || n > maximum) throw new Error(`Coding limit must be an integer from 1 to ${maximum}`);
  return n;
}
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));
function directory(dir: string): void {
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  if (!fs.lstatSync(dir).isDirectory() || fs.lstatSync(dir).isSymbolicLink()) throw new Error("Coding state directory must not be a symlink");
}
function saveReceipt(dir: string, receipt: CodingReceipt): void {
  const file = path.join(dir, `${receipt.runId}.json`);
  const temp = path.join(dir, `.receipt-${randomUUID()}`);
  try {
    fs.writeFileSync(temp, JSON.stringify(receipt, null, 2) + "\n", { flag: "wx", mode: 0o600 });
    fs.renameSync(temp, file);
  } finally { try { fs.unlinkSync(temp); } catch (error: any) { if (error.code !== "ENOENT") throw error; } }
}

/** Reading a nonterminal persisted row NEVER proves liveness or authorizes retry/cancellation. */
export function readCodingReceipts(config: EvanConfig): CodingReceipt[] {
  const dir = path.join(path.dirname(config.sessionDir), "coding-runs");
  if (!fs.existsSync(dir)) return [];
  if (fs.lstatSync(dir).isSymbolicLink()) throw new Error("Unsafe coding receipt directory");
  return fs.readdirSync(dir).filter((name) => /^[a-f0-9-]{36}\.json$/.test(name)).map((name) => {
    const file = path.join(dir, name);
    const stat = fs.lstatSync(file);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 1_000_000) throw new Error("Unsafe coding receipt");
    const receipt = JSON.parse(fs.readFileSync(file, "utf8")) as CodingReceipt;
    if (receipt.schema_version !== 1 || receipt.runId !== name.slice(0, -5) || typeof receipt.ownerSessionId !== "string" || !["queued", "running", "cancel_requested", "completed", "failed", "cancelled", "timeout", "uncertain"].includes(receipt.phase)) throw new Error("Malformed coding receipt");
    if (["queued", "running", "cancel_requested"].includes(receipt.phase)) receipt.phase = "uncertain";
    return receipt;
  });
}

/** Explicit UI/host handoff only. There is intentionally no LLM-callable grant or approval tool. */
export function createCodingHandoff(config: EvanConfig, worker: CodingWorker) {
  parseModelId(config.codingModel, "EVAN_CODING_MODEL");
  const root = fs.realpathSync(config.cwd);
  const stateRoot = path.dirname(config.sessionDir);
  const receiptsDir = path.join(stateRoot, "coding-runs");
  let active: { runId: string; owner: string; cancel: () => void; receipt: CodingReceipt } | undefined;
  return {
    current(): CodingReceipt | undefined { return active ? clone(active.receipt) : undefined; },
    cancel(runId: string, ownerSessionId: string): boolean {
      if (!active || active.runId !== runId || active.owner !== ownerSessionId) return false;
      active.cancel();
      return true;
    },
    start(request: CodingRequest, externalSignal?: AbortSignal): CodingHandle {
      if (active) throw new Error("An Evan-owned coding handoff is already active");
      if (!request.ownerSessionId?.trim() || request.ownerSessionId.length > 200 || !request.objective?.trim() || request.objective.length > 16_000) throw new Error("Explicit owner and bounded objective are required");
      if (!Array.isArray(request.readPaths) || !Array.isArray(request.writePaths) || !request.writePaths.length || request.readPaths.length + request.writePaths.length > 128) throw new Error("Explicit file grants required (maximum 128 files)");
      const limits = {
        timeoutMs: integer(request.timeoutMs, 120_000, 600_000),
        maxToolCalls: integer(request.maxToolCalls, 32, 128),
        maxFileBytes: integer(request.maxFileBytes, 65_536, 1_048_576),
      };
      const controller = new AbortController();
      let timedOut = false;
      const receipt: CodingReceipt = {
        schema_version: 1, runId: randomUUID(), ownerSessionId: request.ownerSessionId,
        projectRoot: root, model: config.codingModel, objective: request.objective,
        readPaths: [...request.readPaths], writePaths: [...request.writePaths], tools: [...CODING_TOOLS], limits,
        phase: "queued", startedAt: new Date().toISOString(), endedAt: null,
        events: [], changes: [], verification: "not-run", tests: "not-run", text: "", error: null,
      };
      directory(stateRoot);
      directory(receiptsDir);
      const ledger = openLedger(path.join(stateRoot, "runs.jsonl"));
      const persist = () => saveReceipt(receiptsDir, receipt);
      const files = createCodingFiles({ root, readPaths: receipt.readPaths, writePaths: receipt.writePaths,
        protectedRoots: [config.appDir, stateRoot], ...limits }, controller.signal, (event) => {
        receipt.events.push({ ...event, tool: event.tool.slice(0, 100), path: event.path?.slice(0, 1024) ?? null });
        receipt.changes = files.changes();
        persist(); // Failure throws before further file operations can proceed.
      });
      const ledgerState = (state: "pending" | "working" | "done" | "failed" | "aborted" | "timeout") => ledger.append({
        run_id: receipt.runId, parent_run_id: receipt.ownerSessionId, model: receipt.model,
        task: receipt.objective, cwd: root, state, tools: receipt.tools, cost_usd: null,
        artifact_path: path.join(receiptsDir, `${receipt.runId}.json`), started_at: receipt.startedAt,
        ended_at: receipt.endedAt, heartbeat_at: new Date().toISOString(),
      });
      persist();
      ledgerState("pending"); // Fail closed before worker dispatch if persistence is unavailable.
      const cancel = () => {
        if (controller.signal.aborted || active?.runId !== receipt.runId || !["queued", "running", "cancel_requested"].includes(receipt.phase)) return;
        receipt.phase = "cancel_requested";
        try { persist(); } finally { controller.abort(new Error("Coding handoff cancelled")); }
      };
      active = { runId: receipt.runId, owner: receipt.ownerSessionId, cancel, receipt };
      const onExternalAbort = () => { try { cancel(); } catch { controller.abort(); } };
      externalSignal?.addEventListener("abort", onExternalAbort, { once: true });
      if (externalSignal?.aborted) onExternalAbort();
      const timer = setTimeout(() => { timedOut = true; onExternalAbort(); }, limits.timeoutMs);
      const done = (async () => {
        let lease: WriterLease | undefined;
        try {
          // Share the actual project lease with Fusion, including across Evan processes.
          for (;;) {
            controller.signal.throwIfAborted();
            try { lease = acquireWriterLease(root, `evan coding ${receipt.runId}`); break; }
            catch (error) { if (!isWriterLeaseBusy(error)) throw error; }
            await new Promise<void>((resolve) => {
              const finish = () => { clearTimeout(wait); controller.signal.removeEventListener("abort", finish); resolve(); };
              const wait = setTimeout(finish, 25);
              controller.signal.addEventListener("abort", finish, { once: true });
            });
          }
          controller.signal.throwIfAborted();
          receipt.phase = "running";
          persist(); ledgerState("working");
          const result = await worker({ model: receipt.model, projectRoot: root, objective: receipt.objective,
            paths: clone(files.paths), signal: controller.signal, invoke: (tool, args) => files.invoke(tool, args) });
          controller.signal.throwIfAborted();
          if (files.faulted) throw new Error("Worker attempted a denied or failed file operation");
          if (!result || typeof result.text !== "string") throw new Error("Worker returned a malformed result");
          receipt.text = result.text.slice(0, 32_000); // Prose is never a verification or approval receipt.
          receipt.phase = "completed";
        } catch (error) {
          receipt.phase = timedOut ? "timeout" : controller.signal.aborted ? "cancelled" : "failed";
          receipt.error = error instanceof Error ? error.message.slice(0, 1000) : "Coding handoff failed";
        } finally {
          // No Promise.race: retain the lease until the trusted worker adapter has settled.
          files.seal();
          clearTimeout(timer);
          externalSignal?.removeEventListener("abort", onExternalAbort);
          try {
            receipt.changes = files.changes();
            if (receipt.changes.length) {
              receipt.verification = files.verify() ? "file-readback-passed" : "file-readback-failed";
              if (receipt.verification === "file-readback-failed" && receipt.phase === "completed") {
                receipt.phase = "failed"; receipt.error = "Final file readback differs from the recorded write";
              }
            }
            receipt.endedAt = new Date().toISOString();
            persist();
            ledgerState(receipt.phase === "completed" ? "done" : receipt.phase === "cancelled" ? "aborted" : receipt.phase === "timeout" ? "timeout" : "failed");
          } finally {
            lease?.release();
            active = undefined;
          }
        }
        return clone(receipt);
      })();
      return { runId: receipt.runId, done, cancel };
    },
  };
}
