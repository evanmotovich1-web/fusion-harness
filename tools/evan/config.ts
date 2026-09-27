import * as path from "node:path";
import { fileURLToPath } from "node:url";

export const CHAT_TOOLS = ["read", "grep", "find", "ls"] as const;

export type ModelId = { provider: string; id: string };
export type EvanConfig = {
  cwd: string;
  appDir: string;
  sessionDir: string;
  chatModel: string;
  codingModel: string;
};

export function parseModelId(value: string | undefined, variable: string): ModelId {
  const text = value?.trim() ?? "";
  const slash = text.indexOf("/");
  if (slash < 1 || slash === text.length - 1 || /\s/.test(text)) {
    throw new Error(`${variable} must be an explicit provider/model id`);
  }
  return { provider: text.slice(0, slash), id: text.slice(slash + 1) };
}

export function readConfig(env: NodeJS.ProcessEnv = process.env, cwd = process.cwd()): EvanConfig {
  const chatModel = env.EVAN_CHAT_MODEL?.trim();
  const codingModel = env.EVAN_CODING_MODEL?.trim();
  parseModelId(chatModel, "EVAN_CHAT_MODEL");
  parseModelId(codingModel, "EVAN_CODING_MODEL");
  const appDir = path.dirname(fileURLToPath(import.meta.url));
  return {
    cwd: path.resolve(cwd),
    appDir,
    sessionDir: path.join(appDir, ".state", "sessions"),
    chatModel: chatModel!,
    codingModel: codingModel!,
  };
}
