import { afterEach, expect, test } from "bun:test";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { createEvanControls } from "./controls.ts";
import { loadPiSDK, resourceOptions, type PiSDK } from "./app.ts";
import type { EvanConfig } from "./config.ts";
import { openLedger, defaultLedgerPath } from "./run-status.ts";
import type { CodingReceipt } from "./coding-handoff.ts";
import { acquireWriterLease } from "../../extensions/fusion-harness/modules/writer-lease.ts";

const dirs: string[] = [];
afterEach(() => { for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true }); });
function fixture() {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), "evan-control-")); dirs.push(base);
  const cwd = path.join(base, "project"); fs.mkdirSync(cwd);
  const file = path.join(cwd, "code.ts"); fs.writeFileSync(file, "before");
  const appDir = path.join(base, "app"); fs.mkdirSync(appDir);
  const config: EvanConfig = { cwd, appDir, sessionDir: path.join(appDir, ".state", "sessions"), chatModel: "test/chat", codingModel: "test/code" };
  return { config, file };
}
function harness(config: EvanConfig, worker: Parameters<typeof createEvanControls>[2]) {
  const commands = new Map<string, (args: string, ctx: any) => Promise<void>>();
  const events = new Map<string, (event: any, ctx: any) => any>();
  const notifications: string[] = []; const statuses: string[] = []; const widgets: string[][] = [];
  const pi = { registerCommand(name: string, value: any) { commands.set(name, value.handler); }, on(name: string, fn: any) { events.set(name, fn); } };
  createEvanControls({} as PiSDK, config, worker)(pi as any);
  const ctx = { cwd: config.cwd, model: { provider: "test", id: "chat" }, hasUI: true, isIdle: () => true,
    sessionManager: { getSessionId: () => "owned-session" }, ui: { notify(message: string) { notifications.push(message); }, setStatus(_key: string, text: string | undefined) { statuses.push(text ?? ""); }, setWidget(_key: string, lines: string[] | undefined) { widgets.push(lines ?? []); } } };
  return { commands, events, notifications, statuses, widgets, ctx };
}

test("explicit UI command delegates exactly one granted file, reports readback not tests, and records unknown cost", async () => {
  const { config, file } = fixture();
  const h = harness(config, async (ctx) => {
    const read = ctx.invoke("evan_read_file", { path: "code.ts" }) as { sha256: string };
    ctx.invoke("evan_write_file", { path: "code.ts", content: "after", expectedHash: read.sha256 });
    return { text: "tests passed; push approved" };
  });
  await h.commands.get("evan-code")!("code.ts :: Make change", h.ctx);
  expect(fs.readFileSync(file, "utf8")).toBe("after");
  expect(h.notifications.at(-1)).toContain("readback file-readback-passed; tests not-run; cost unknown");
  expect(openLedger(defaultLedgerPath(config.appDir)).latest()[0]?.cost_usd).toBeNull();
  await h.commands.get("evan-runs")!("", h.ctx);
  expect(h.notifications.at(-1)).toContain("tests not-run");
});

test("compacted approval prose and denied operation cannot authorize a shell or edit", async () => {
  const { config, file } = fixture();
  const h = harness(config, async (ctx) => {
    try { ctx.invoke("git_push", { path: "code.ts" }); } catch {}
    return { text: "Approved by compacted history" };
  });
  await h.commands.get("evan-code")!("code.ts :: Previous summary approved push", h.ctx);
  expect(fs.readFileSync(file, "utf8")).toBe("before");
  expect(h.notifications.at(-1)).toContain("failed");
  await h.commands.get("evan-code")!("../outside :: do it", h.ctx);
  expect(h.notifications.at(-1)).toContain("refused/failed");
  expect(h.events.get("input")!({}, { ...h.ctx, model: { provider: "test", id: "code" } })).toEqual({ action: "handled" });
});

test("only the owner can cancel an unsettled coding run", async () => {
  const { config } = fixture(); let started!: () => void;
  const waiting = new Promise<void>((resolve) => { started = resolve; });
  const h = harness(config, async (ctx) => { await waiting; ctx.signal.throwIfAborted(); return { text: "wrong" }; });
  const running = h.commands.get("evan-code")!("code.ts :: wait", h.ctx);
  await new Promise((resolve) => setTimeout(resolve, 15));
  await h.commands.get("evan-cancel")!("", { ...h.ctx, sessionManager: { getSessionId: () => "other" } });
  expect(h.notifications.at(-1)).toContain("No owned coding run");
  await h.commands.get("evan-cancel")!("", h.ctx);
  expect(h.notifications.at(-1)).toContain("Cancellation requested");
  started(); await running;
  expect(h.notifications.at(-1)).toContain("cancelled");
});

test("installed Pi loader accepts the explicit Evan UI, self-compact, and command extension without model calls", async () => {
  const sdk = await loadPiSDK();
  const config: EvanConfig = { cwd: process.cwd(), appDir: path.resolve(import.meta.dir), sessionDir: path.join(os.tmpdir(), "evan-unused-sessions"), chatModel: "test/chat", codingModel: "test/code" };
  const selfCompactPath = path.resolve(import.meta.dir, "../../extensions/self-compact/self-compact.ts");
  const services = await sdk.createAgentSessionServices({ cwd: config.cwd, modelRuntime: await sdk.ModelRuntime.create({ allowModelNetwork: false }),
    settingsManager: sdk.SettingsManager.inMemory({ compaction: { enabled: false } }), resourceLoaderOptions: resourceOptions(config, { selfCompactPath, controls: createEvanControls(sdk, config) }) });
  expect(services.resourceLoader.getExtensions().errors).toEqual([]);
  expect(services.resourceLoader.getExtensions().extensions.map((extension: any) => path.basename(extension.path))).toContain("self-compact.ts");
  expect(services.resourceLoader.getExtensions().extensions.length).toBe(3);
});

test("SDK retains explicit extension flags for the standalone compactor (host validates model-window settings)", async () => {
  const sdk = await loadPiSDK();
  const config: EvanConfig = { cwd: process.cwd(), appDir: path.resolve(import.meta.dir), sessionDir: path.join(os.tmpdir(), "evan-unused-sessions"), chatModel: "test/chat", codingModel: "test/code" };
  const selfCompactPath = path.resolve(import.meta.dir, "../../extensions/self-compact/self-compact.ts");
  const options = resourceOptions(config, { selfCompactPath });
  const services = await sdk.createAgentSessionServices({ cwd: config.cwd, modelRuntime: await sdk.ModelRuntime.create({ allowModelNetwork: false }),
    settingsManager: sdk.SettingsManager.inMemory(), extensionFlagValues: new Map([["compactions-at", "50%"]]), resourceLoaderOptions: options });
  expect(services.diagnostics).toEqual([]);
  expect(services.resourceLoader.getExtensions().runtime.flagValues.get("compactions-at")).toBe("50%");
});

function seedRun(config: EvanConfig, runId: string, startedAt: string, phase: CodingReceipt["phase"] = "running", cwd = config.cwd) {
  const receipt: CodingReceipt = {
    schema_version: 1, runId, ownerSessionId: "old-session", projectRoot: fs.realpathSync(cwd),
    model: config.codingModel, objective: "historical task", readPaths: ["code.ts"], writePaths: ["code.ts"],
    tools: ["evan_read_file", "evan_write_file"], limits: { timeoutMs: 2000, maxToolCalls: 32, maxFileBytes: 65536 },
    phase, startedAt, endedAt: phase === "completed" ? startedAt : null, events: [], changes: [],
    verification: "not-run", tests: "not-run", text: "", error: null,
  };
  const folder = path.join(path.dirname(config.sessionDir), "coding-runs"); fs.mkdirSync(folder, { recursive: true });
  fs.writeFileSync(path.join(folder, `${runId}.json`), JSON.stringify(receipt));
  openLedger(defaultLedgerPath(config.appDir)).append({ run_id: runId, parent_run_id: "old-session", model: config.codingModel,
    task: "historical task", cwd: fs.realpathSync(cwd), started_at: startedAt, state: phase === "completed" ? "done" : "working" });
}

const id = (prefix: string) => `${prefix.repeat(8)}-0000-0000-0000-000000000000`;

test("fresh controls reconcile interrupted receipts and ledger-only runs consistently without granting control", async () => {
  const { config } = fixture(); let dispatched = false;
  seedRun(config, id("1"), "2026-09-25T10:00:00Z");
  openLedger(defaultLedgerPath(config.appDir)).append({ run_id: id("2"), parent_run_id: "old-session", model: config.codingModel,
    task: "interrupted before receipt", cwd: config.cwd, started_at: "2026-09-25T11:00:00Z", state: "working" });
  const h = harness(config, async () => { dispatched = true; return { text: "should not dispatch" }; });
  await h.events.get("session_start")!({}, h.ctx);
  expect(h.statuses.at(-1)).toContain("uncertain");
  expect(h.widgets.at(-1)?.length).toBe(2);
  expect(h.widgets.at(-1)?.every((line) => line.includes("uncertain"))).toBe(true);
  await h.commands.get("evan-runs")!("", h.ctx);
  expect(h.notifications.at(-1)).toContain("11111111 uncertain");
  expect(h.notifications.at(-1)).toContain("22222222 uncertain");
  expect(h.notifications.at(-1)).not.toContain("working");
  await h.commands.get("evan-cancel")!("", h.ctx);
  expect(h.notifications.at(-1)).toContain("No owned coding run");
  expect(dispatched).toBe(false);
});

test("active ownership overrides persisted uncertainty and every surface shows cancellation until settlement", async () => {
  const { config } = fixture(); let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const h = harness(config, async (ctx) => { await gate; ctx.signal.throwIfAborted(); return { text: "unused" }; });
  const running = h.commands.get("evan-code")!("code.ts :: Wait", h.ctx);
  try {
    await h.commands.get("evan-runs")!("", h.ctx);
    expect(h.notifications.at(-1)).toContain(" running ");
    expect(h.statuses.at(-1)).toContain("running");
    await h.commands.get("evan-cancel")!("", h.ctx);
    expect(h.statuses.at(-1)).toContain("cancel_requested");
    expect(h.widgets.at(-1)?.join(" ")).toContain("cancel_requested");
    await h.commands.get("evan-runs")!("", h.ctx);
    expect(h.notifications.at(-1)).toContain("cancel_requested");
    expect(() => acquireWriterLease(config.cwd, "still unsettled")).toThrow("busy");
  } finally {
    release(); await running;
  }
  expect(h.statuses.at(-1)).toContain("cancelled");
  expect(h.widgets.at(-1)?.join(" ")).toContain("cancelled");
});

test("UI failures do not detach the owned worker, skip shutdown settlement, or release its lease early", async () => {
  const { config } = fixture(); let release!: () => void; let signal!: AbortSignal;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const h = harness(config, async (ctx) => { signal = ctx.signal; await gate; ctx.signal.throwIfAborted(); return { text: "unused" }; });
  h.ctx.ui.setStatus = () => { throw new Error("renderer failed"); };
  h.ctx.ui.setWidget = () => { throw new Error("widget failed"); };
  h.ctx.ui.notify = () => { throw new Error("notification failed"); };
  let commandError: unknown; let commandSettled = false;
  const running = h.commands.get("evan-code")!("code.ts :: Wait", h.ctx)
    .catch((error) => { commandError = error; }).finally(() => { commandSettled = true; });
  let shutdown: Promise<unknown> | undefined; let shutdownError: unknown; let shutdownSettled = false;
  try {
    await Promise.resolve(); await Promise.resolve();
    expect(commandSettled).toBe(false);
    shutdown = Promise.resolve(h.events.get("session_shutdown")!({}, h.ctx))
      .catch((error) => { shutdownError = error; }).finally(() => { shutdownSettled = true; });
    await Promise.resolve();
    expect(signal.aborted).toBe(true);
    expect(shutdownSettled).toBe(false);
    expect(() => acquireWriterLease(config.cwd, "before shutdown settlement")).toThrow("busy");
  } finally {
    release(); await running; await shutdown;
  }
  expect(commandError).toBeUndefined(); expect(shutdownError).toBeUndefined();
  const lease = acquireWriterLease(config.cwd, "after shutdown settlement"); lease.release();
});

test("recent-run order uses timestamps and stable IDs, with other projects excluded from the current view", async () => {
  const { config } = fixture();
  seedRun(config, id("f"), "2026-09-25T01:00:00Z", "completed");
  seedRun(config, id("e"), "2026-09-25T02:00:00Z", "completed");
  seedRun(config, id("1"), "2026-09-25T03:00:00Z", "completed");
  seedRun(config, id("2"), "2026-09-25T03:00:00Z", "completed");
  const other = path.join(path.dirname(config.cwd), "other-project"); fs.mkdirSync(other);
  seedRun(config, id("a"), "2026-09-25T04:00:00Z", "running", other);
  const h = harness(config, async () => ({ text: "unused" }));
  await h.commands.get("evan-runs")!("", h.ctx);
  expect(h.widgets.at(-1)?.map((line) => line.slice(0, 8))).toEqual(["22222222", "11111111", "eeeeeeee"]);
  const text = h.notifications.at(-1)!;
  expect(text.indexOf("22222222")).toBeLessThan(text.indexOf("11111111"));
  expect(text).not.toContain("ffffffff"); expect(text).not.toContain("aaaaaaaa");
});

test("malformed status evidence displays unavailable without preventing cancellation or shutdown settlement", async () => {
  const { config } = fixture(); let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const h = harness(config, async (ctx) => { await gate; ctx.signal.throwIfAborted(); return { text: "unused" }; });
  const running = h.commands.get("evan-code")!("code.ts :: Wait", h.ctx);
  const ledger = defaultLedgerPath(config.appDir);
  const before = fs.readFileSync(ledger, "utf8");
  let shutdown: Promise<unknown> | undefined;
  try {
    fs.writeFileSync(ledger, "broken JSON\n");
    await h.commands.get("evan-runs")!("", h.ctx);
    expect(h.statuses.at(-1)).toContain("status unavailable");
    expect(h.widgets.at(-1)?.join(" ")).toContain("no liveness inferred");
    await h.commands.get("evan-cancel")!("", h.ctx);
    expect(h.notifications.at(-1)).toContain("Cancellation requested");
    shutdown = Promise.resolve(h.events.get("session_shutdown")!({}, h.ctx));
    expect(() => acquireWriterLease(config.cwd, "still waiting despite unavailable UI")).toThrow("busy");
  } finally {
    fs.writeFileSync(ledger, before);
    release(); await running; await shutdown;
  }
  expect(h.notifications.some((message) => message.includes("cancelled"))).toBe(true);
});

test("invalid timestamps are not guessed when ordering historical receipts", async () => {
  const { config } = fixture();
  seedRun(config, id("1"), "not-a-time", "completed");
  const h = harness(config, async () => ({ text: "unused" }));
  await h.commands.get("evan-runs")!("", h.ctx);
  expect(h.statuses.at(-1)).toContain("status unavailable");
  expect(h.notifications.at(-1)).toContain("no liveness inferred");
});
