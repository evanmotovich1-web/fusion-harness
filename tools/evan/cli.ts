#!/usr/bin/env bun
import { readConfig } from "./config.ts";

const HELP = `Evan Agent (project-local Pi SDK application)
Usage: tools/evan/evan [--help | --check] [--compactions-soft-at VALUE] [--compactions-at VALUE] [--compact-buffer VALUE] [--compact-prompt TEXT]
Aliases: --compact-soft-at, --compact-at. Values are validated by the self-compact extension at startup.
In the TUI: /evan-code relative/file :: objective, /evan-cancel, /evan-runs, /self-compact.
Environment:
  EVAN_CHAT_MODEL=provider/model     Required single-model chat binding
  EVAN_CODING_MODEL=provider/model   Required, reserved for explicit coding handoff
  EVAN_PI_SDK_DIR=/path/to/package   Optional installed Pi SDK package root
--check validates configuration syntax only; it does not authenticate or call a model.
No global installation, automatic Fusion fan-out, or messaging is started by this launcher.`;

const FLAGS = new Set(["compactions-soft-at", "compactions-at", "compact-buffer", "compact-prompt", "compact-soft-at", "compact-at"]);
export function parseArgs(args: string[]): { help: boolean; check: boolean; flags: Map<string, string> } {
  let help = false; let check = false;
  const flags = new Map<string, string>();
  for (let i = 0; i < args.length; i++) {
    const arg = args[i]!;
    if (arg === "--help") { help = true; continue; }
    if (arg === "--check") { check = true; continue; }
    const match = /^--([a-z-]+)(?:=(.*))?$/.exec(arg);
    if (!match || !FLAGS.has(match[1]!)) throw new Error(`Unknown argument: ${arg}\n${HELP}`);
    const value = match[2] ?? args[++i];
    if (value === undefined || value.startsWith("--") || flags.has(match[1]!)) throw new Error(`Missing or duplicate value for --${match[1]}`);
    flags.set(match[1]!, value);
  }
  return { help, check, flags };
}

export async function main(args = process.argv.slice(2), env = process.env): Promise<void> {
  const { help, check, flags } = parseArgs(args);
  if (help) { console.log(HELP); return; }
  const config = readConfig(env);
  if (check) {
    console.log(`Configured (not authenticated): chat=${config.chatModel}, coding=${config.codingModel}; chat tools=read,grep,find,ls; extension flags=${[...flags.keys()].join(",") || "defaults"}`);
    return;
  }
  const { loadPiSDK, runEvan } = await import("./app.ts");
  const sdk = await loadPiSDK(env);
  await runEvan(sdk, config, flags);
}

if (import.meta.main) {
  main().catch((error) => {
    console.error(`Evan Agent: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  });
}
