import { afterEach, describe, expect, test } from "bun:test";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { createEvanRuntime, loadPiSDK, resolveModels, resourceOptions, type PiSDK } from "./app.ts";
import { CHAT_TOOLS, parseModelId, readConfig, type EvanConfig } from "./config.ts";
import { main, parseArgs } from "./cli.ts";

const dirs: string[] = [];
afterEach(() => { while (dirs.length) fs.rmSync(dirs.pop()!, { recursive: true, force: true }); });
function fixture(): EvanConfig {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "evan-shell-test-"));
  dirs.push(temp);
  return { ...readConfig({ EVAN_CHAT_MODEL: "test/chat", EVAN_CODING_MODEL: "test/code" }, temp), sessionDir: path.join(temp, "sessions") };
}

describe("Evan project-local shell", () => {
  test("requires explicit, separate provider/model bindings and never chooses a default", () => {
    expect(() => readConfig({}, "/tmp")).toThrow("EVAN_CHAT_MODEL");
    expect(() => readConfig({ EVAN_CHAT_MODEL: "test/chat" }, "/tmp")).toThrow("EVAN_CODING_MODEL");
    expect(() => parseModelId("chat", "EVAN_CHAT_MODEL")).toThrow("provider/model");
    expect(() => parseModelId("test/chat", "EVAN_CHAT_MODEL")).not.toThrow();
    expect(CHAT_TOOLS).toEqual(["read", "grep", "find", "ls"]);
  });

  test("authentication or missing configured model refuses both paths, never substitutes", async () => {
    const config = fixture();
    const catalog = {
      getModel: (provider: string, id: string) => ({ provider, id }),
      getAvailable: async () => [{ provider: "test", id: "chat" }],
    };
    await expect(resolveModels(catalog, config)).rejects.toThrow("EVAN_CODING_MODEL=test/code");
    await expect(resolveModels({ ...catalog, getAvailable: async () => [] }, config)).rejects.toThrow("EVAN_CHAT_MODEL=test/chat");
  });

  test("explicit resource loader has only Evan UI and theme; no ambient discovery", () => {
    const options = resourceOptions(fixture());
    expect(options.additionalExtensionPaths).toEqual([path.join(options.additionalThemePaths[0]!, "..", "ui.ts")].map(path.normalize));
    expect(options.additionalThemePaths[0]).toEndWith("evan-theme.json");
    expect([options.noExtensions, options.noSkills, options.noPromptTemplates, options.noThemes, options.noContextFiles]).toEqual([true, true, true, true, true]);
    expect(options.systemPromptOverride()).toContain("You are Evan Agent");
    expect(options.appendSystemPromptOverride()).toEqual([]);
    expect(options.additionalExtensionPaths.map((item) => path.basename(item))).toEqual(["ui.ts"]);
  });

  test("installed Pi loads only named Evan resources without a provider call", async () => {
    const config = fixture();
    const sdk = await loadPiSDK();
    const services = await sdk.createAgentSessionServices({
      cwd: config.cwd,
      agentDir: sdk.getAgentDir(),
      settingsManager: sdk.SettingsManager.inMemory(),
      modelRuntime: await sdk.ModelRuntime.create({ allowModelNetwork: false }),
      resourceLoaderOptions: resourceOptions(config),
    });
    expect(services.resourceLoader.getExtensions().errors).toEqual([]);
    expect(services.resourceLoader.getExtensions().extensions.map((item: any) => path.basename(item.path))).toEqual(["ui.ts"]);
    expect(services.resourceLoader.getThemes().diagnostics.filter((item: any) => item.type === "error")).toEqual([]);
    expect(services.resourceLoader.getThemes().themes.map((item: any) => item.name)).toEqual(["evan"]);
    expect(services.resourceLoader.getSystemPrompt()).toContain("You are Evan Agent");
    expect(services.resourceLoader.getAgentsFiles().agentsFiles).toEqual([]);
  });

  test("creates app-owned session and passes a single chat model and closed tools to SDK", async () => {
    const config = fixture();
    const calls: Record<string, any> = {};
    const chat = { provider: "test", id: "chat", contextWindow: 1_000_000 };
    const code = { provider: "test", id: "code", contextWindow: 1_000_000 };
    const sdk = {
      ModelRuntime: { create: async () => ({ getModel: (_p: string, id: string) => id === "chat" ? chat : code, getAvailable: async () => [chat, code] }) },
      getAgentDir: () => "/unused/pi-auth",
      SettingsManager: { inMemory: (value: any) => value },
      SessionManager: { continueRecent: (cwd: string, dir: string) => { calls.persistence = { cwd, dir }; return { file: "evan-only" }; } },
      createAgentSessionServices: async (options: any) => {
        calls.services = options;
        return { diagnostics: [], resourceLoader: { getExtensions: () => ({ errors: [] }), getThemes: () => ({ diagnostics: [] }) } };
      },
      createAgentSessionFromServices: async (options: any) => { calls.session = options; return { session: { model: chat } }; },
      createAgentSessionRuntime: async (factory: any, options: any) => {
        calls.runtime = options;
        const result = await factory({ cwd: config.cwd, sessionManager: options.sessionManager });
        return { ...result, dispose: async () => {} };
      },
    } as unknown as PiSDK;
    const runtime = await createEvanRuntime(sdk, config);
    expect(runtime.session.model).toEqual(chat);
    expect(calls.persistence).toEqual({ cwd: config.cwd, dir: config.sessionDir });
    expect(calls.session.model).toEqual(chat);
    expect(calls.session.scopedModels).toEqual([{ model: chat }]);
    expect(calls.session.tools).toEqual(["read", "grep", "find", "ls"]);
    expect(calls.services.resourceLoaderOptions.additionalExtensionPaths).toEqual([
      path.join(config.appDir, "ui.ts"), path.resolve(config.appDir, "../../extensions/self-compact/self-compact.ts"),
    ]);
    expect(calls.services.resourceLoaderOptions.extensionFactories.map((factory: any) => factory.name)).toEqual(["evan-controls"]);
    expect(calls.services.settingsManager.compaction.enabled).toBe(false);
    expect(fs.existsSync(config.sessionDir)).toBe(true);
  });

  test("refuses a saved session that would switch the chat model", async () => {
    const config = fixture();
    let disposed = false;
    const sdk = {
      ModelRuntime: { create: async () => ({ getModel: (_p: string, id: string) => ({ provider: "test", id, contextWindow: 1_000_000 }), getAvailable: async () => [{ provider: "test", id: "chat" }, { provider: "test", id: "code" }] }) },
      getAgentDir: () => "/unused/pi-auth",
      SettingsManager: { inMemory: () => ({}) },
      SessionManager: { continueRecent: () => ({}) },
      createAgentSessionServices: async () => ({ diagnostics: [], resourceLoader: { getExtensions: () => ({ errors: [] }), getThemes: () => ({ diagnostics: [] }) } }),
      createAgentSessionFromServices: async () => ({ session: { model: { provider: "test", id: "code" } } }),
      createAgentSessionRuntime: async (factory: any, options: any) => ({ ...(await factory({ cwd: config.cwd, sessionManager: options.sessionManager })), dispose: async () => { disposed = true; } }),
    } as unknown as PiSDK;
    await expect(createEvanRuntime(sdk, config)).rejects.toThrow("refusing a fallback");
    expect(disposed).toBe(true);
  });

  test("real Pi SessionManager retains user conversation across restart without a model call", async () => {
    const config = fixture();
    const sdk = await loadPiSDK();
    const first = sdk.SessionManager.continueRecent(config.cwd, config.sessionDir);
    first.appendMessage({ role: "user", content: "Keep this session", timestamp: Date.now() });
    // Pi deliberately waits for an assistant message before writing the session file.
    first.appendMessage({ role: "assistant", content: [{ type: "text", text: "Acknowledged" }], api: "test", provider: "test", model: "chat", usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } }, stopReason: "stop", timestamp: Date.now() });
    const file = first.getSessionFile();
    expect(file).toBeTruthy();
    const restored = sdk.SessionManager.continueRecent(config.cwd, config.sessionDir);
    expect(restored.getSessionFile()).toBe(file);
    expect(restored.getEntries().some((entry: any) => entry.type === "message" && entry.message.role === "user" && entry.message.content === "Keep this session")).toBe(true);
  });

  test("--help and --check make no SDK or provider calls", async () => {
    await main(["--help"], {});
    await main(["--check"], { EVAN_CHAT_MODEL: "test/chat", EVAN_CODING_MODEL: "test/code" });
    await expect(main(["--unknown"], {})).rejects.toThrow("Unknown argument");
    expect(parseArgs(["--compactions-at", "50%", "--compact-prompt=keep context"]).flags).toEqual(new Map([
      ["compactions-at", "50%"], ["compact-prompt", "keep context"],
    ]));
    expect(() => parseArgs(["--compact-at", "30k", "--compact-at", "40k"])).toThrow("duplicate");
  });
});
