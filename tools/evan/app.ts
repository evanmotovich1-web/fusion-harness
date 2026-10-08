import * as fs from "node:fs";
import * as path from "node:path";
import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";
import { CHAT_TOOLS, parseModelId, type EvanConfig } from "./config.ts";
import { createEvanControls } from "./controls.ts";
import { coalesceFlag, FLAGS, resolveThresholds } from "../../extensions/self-compact/self-compact.ts";

export type PiSDK = typeof import("@earendil-works/pi-coding-agent");

/** Resolve an installed SDK without silently changing the runtime or model. */
export async function loadPiSDK(env: NodeJS.ProcessEnv = process.env): Promise<PiSDK> {
  const localRequire = createRequire(import.meta.url);
  let localEntry: string | undefined;
  try {
    localEntry = localRequire.resolve("@earendil-works/pi-coding-agent");
  } catch (error) {
    if (error && typeof error === "object" && "code" in error && error.code !== "MODULE_NOT_FOUND") throw error;
  }
  if (localEntry) return await import(pathToFileURL(localEntry).href) as PiSDK;
  // An explicitly installed global Pi is usable without installing anything into this checkout.
  const packageDir = env.EVAN_PI_SDK_DIR ?? path.join(env.HOME ?? "", ".local", "lib", "node_modules", "@earendil-works", "pi-coding-agent");
  const entry = path.join(packageDir, "dist", "index.js");
  if (!fs.existsSync(entry)) throw new Error("Pi SDK not found. Install tools/evan's package or set EVAN_PI_SDK_DIR to an installed Pi package directory.");
  return await import(pathToFileURL(entry).href) as PiSDK;
}

/** Fail closed on absent/authless configured models. Never accept Pi's implicit fallback. */
export async function resolveModels(modelRuntime: {
  getModel(provider: string, id: string): unknown;
  getAvailable(): Promise<readonly { provider: string; id: string }[]>;
}, config: EvanConfig): Promise<{ chat: unknown; coding: unknown }> {
  const available = await modelRuntime.getAvailable();
  const lookup = (value: string, variable: string) => {
    const { provider, id } = parseModelId(value, variable);
    const model = modelRuntime.getModel(provider, id);
    if (!model || !available.some((candidate) => candidate.provider === provider && candidate.id === id)) {
      throw new Error(`${variable}=${value} is not available or authenticated in Pi; no model substituted`);
    }
    return model;
  };
  return { chat: lookup(config.chatModel, "EVAN_CHAT_MODEL"), coding: lookup(config.codingModel, "EVAN_CODING_MODEL") };
}

export function resourceOptions(config: EvanConfig, opts: { selfCompactPath?: string; controls?: ReturnType<typeof createEvanControls> } = {}) {
  const paths = [path.join(config.appDir, "ui.ts")];
  if (opts.selfCompactPath) paths.push(opts.selfCompactPath);
  const identity = fs.readFileSync(path.join(config.appDir, "IDENTITY.md"), "utf8").trim();
  if (!identity) throw new Error("Evan identity prompt is empty");
  return {
    noExtensions: true,
    noSkills: true,
    noPromptTemplates: true,
    noThemes: true,
    noContextFiles: true,
    additionalExtensionPaths: paths,
    extensionFactories: opts.controls ? [{ name: "evan-controls", factory: opts.controls }] : [],
    additionalThemePaths: [path.join(config.appDir, "evan-theme.json")],
    systemPromptOverride: () => identity,
    appendSystemPromptOverride: () => [] as string[],
  };
}

/** Builds an app-owned persistent session; no Fusion extension or worker sessions are loaded. */
export async function createEvanRuntime(sdk: PiSDK, config: EvanConfig, extensionFlags = new Map<string, string>()) {
  const modelRuntime = await sdk.ModelRuntime.create({ allowModelNetwork: false });
  const { chat } = await resolveModels(modelRuntime, config);
  const chatModel = chat as NonNullable<ReturnType<typeof modelRuntime.getModel>>;
  const flag = (name: string) => extensionFlags.get(name);
  resolveThresholds({ window: chatModel.contextWindow,
    softSpec: coalesceFlag(flag, FLAGS.soft, FLAGS.softAlias),
    warningSpec: coalesceFlag(flag, FLAGS.warning, FLAGS.warningAlias),
    bufferSpec: flag(FLAGS.buffer),
  }); // Validate startup flags against this exact model, not after the first paid turn.
  const selfCompactPath = path.resolve(config.appDir, "../../extensions/self-compact/self-compact.ts");
  if (!fs.existsSync(selfCompactPath)) throw new Error("Evan self-compact extension is missing");
  const agentDir = sdk.getAgentDir(); // Reuse Pi authentication, not ambient skills or extensions.
  const createRuntime: import("@earendil-works/pi-coding-agent").CreateAgentSessionRuntimeFactory = async ({ cwd, sessionManager, sessionStartEvent }) => {
    if (fs.realpathSync(cwd) !== fs.realpathSync(config.cwd)) throw new Error("Evan cannot switch to an unapproved project cwd");
    const services = await sdk.createAgentSessionServices({
      cwd,
      agentDir,
      modelRuntime,
      extensionFlagValues: extensionFlags,
      // Self-compact coordinates the threshold; Pi's independent automatic trigger is off.
      settingsManager: sdk.SettingsManager.inMemory({ compaction: { enabled: false } }),
      resourceLoaderOptions: resourceOptions(config, { selfCompactPath, controls: createEvanControls(sdk, config) }),
    });
    if (services.diagnostics.some((d) => d.type === "error")) {
      throw new Error(`Evan resource error: ${services.diagnostics.filter((d) => d.type === "error").map((d) => d.message).join("; ")}`);
    }
    if (services.resourceLoader.getExtensions().errors.length) {
      throw new Error(`Evan extension failed to load: ${services.resourceLoader.getExtensions().errors.map((e) => e.error).join("; ")}`);
    }
    if (services.resourceLoader.getThemes().diagnostics.some((d) => d.type === "error")) {
      throw new Error("Evan theme failed to load");
    }
    return {
      ...(await sdk.createAgentSessionFromServices({
        services,
        sessionManager,
        sessionStartEvent,
        model: chatModel,
        scopedModels: [{ model: chatModel }],
        tools: [...CHAT_TOOLS],
      })),
      services,
      diagnostics: services.diagnostics,
    };
  };
  fs.mkdirSync(config.sessionDir, { recursive: true, mode: 0o700 });
  const runtime = await sdk.createAgentSessionRuntime(createRuntime, {
    cwd: config.cwd,
    agentDir,
    sessionManager: sdk.SessionManager.continueRecent(config.cwd, config.sessionDir),
  });
  const current = runtime.session.model;
  if (!current || `${current.provider}/${current.id}` !== config.chatModel || runtime.modelFallbackMessage) {
    await runtime.dispose();
    throw new Error(`Saved session did not restore the configured chat model ${config.chatModel}; refusing a fallback`);
  }
  return runtime;
}

export async function runEvan(sdk: PiSDK, config: EvanConfig, extensionFlags = new Map<string, string>()): Promise<void> {
  const runtime = await createEvanRuntime(sdk, config, extensionFlags);
  try {
    const mode = new sdk.InteractiveMode(runtime, { initialThemeSetting: "evan" });
    await mode.run();
  } finally {
    await runtime.dispose();
  }
}
