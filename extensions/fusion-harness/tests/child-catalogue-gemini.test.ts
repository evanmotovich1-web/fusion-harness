import { afterEach, expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { pathToFileURL } from "node:url";

const dirs: string[] = [];
afterEach(() => { for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true }); });
const url = (file: string) => pathToFileURL(path.resolve(import.meta.dir, "..", file)).href;

function catalogueFixture(model: string, installed = true, nextModel?: string) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fh-gemini-catalogue-"));
  dirs.push(dir);
  const home = path.join(dir, "home");
  fs.mkdirSync(home);
  const tui = path.join(dir, "node_modules/@earendil-works/pi-tui");
  fs.mkdirSync(tui, {recursive: true});
  fs.writeFileSync(path.join(tui, "package.json"), JSON.stringify({name: "@earendil-works/pi-tui", type: "module", main: "index.js"}));
  fs.writeFileSync(path.join(tui, "index.js"), "export class Container {} export class Text {} export const matchesKey = () => false, truncateToWidth = s => s, visibleWidth = s => s.length;\n");
  const extension = path.join(home, ".pi/agent/extensions/gemini-login/index.ts");
  if (installed) {
    fs.mkdirSync(path.dirname(extension), { recursive: true });
    fs.writeFileSync(extension, "throw new Error('Fixture provider must not execute');\n");
  }
  const config = path.join(dir, "stack.yaml");
  const stack = (main: string) => `- name: architect\n  model: test/architect\n  architect: true\n- name: main\n  model: ${main}\n  primary: true\n`;
  fs.writeFileSync(config, stack(model));
  const nextConfig = path.join(dir, "next.yaml");
  if (nextModel) fs.writeFileSync(nextConfig, stack(nextModel));
  const cli = path.join(dir, "catalogue-cli.ts");
  fs.writeFileSync(cli, `import * as fs from "node:fs";
const args = process.argv.slice(2);
fs.appendFileSync(${JSON.stringify(path.join(dir, "catalogue.jsonl"))}, JSON.stringify(args) + "\\n");
if (!args.includes("--list-models") || !args.includes("--no-extensions")) process.exit(2);
const rows = ["provider model context max-out", "test architect 1 1", "test builder 1 1"];
if (args[args.indexOf("-e") + 1] === ${JSON.stringify(extension)}) {
  for (const provider of ["gemini-login", "google-gemini-cli"]) for (const id of ["gemini-4-argon", "gemini-3.8-flash"]) rows.push(provider + " " + id + " 1 1");
}
console.log(rows.join("\\n"));
`);
  const launcher = path.join(dir, "host.ts");
  fs.writeFileSync(launcher, `import { mock } from "bun:test";
import * as fs from "node:fs";
import { spawnSync } from "node:child_process";

mock.module(${JSON.stringify(url("modules/tui.ts"))}, () => ({AgentGrid: class {}, FullWidth: class {}, TwoCol: class {}, cellStr: () => "", laneRowStr: () => "", liveColumn: () => "", renderFhPanel: () => ""}));
const {default: factory} = await import(${JSON.stringify(url("fusion-harness.ts"))});
const {loadModelStack} = await import(${JSON.stringify(url("modules/model-stack.ts"))});
const {saveGroup} = await import(${JSON.stringify(url("modules/model-groups.ts"))});
process.argv[1] = ${JSON.stringify(cli)};
const hooks: any[] = [], commands: any = {}, notices: any[] = [], selected: any[] = [];
const pi = new Proxy({
  getFlag: (name: string) => name === "fh-config" ? ${JSON.stringify(config)} : undefined,
  on: (name: string, fn: any) => { if (name === "session_start") hooks.push(fn); },
  registerCommand: (name: string, spec: any) => { commands[name] = spec.handler; },
  exec: async (command: string, args: string[]) => { const r = spawnSync(command, args, {cwd: ${JSON.stringify(dir)}, encoding: "utf8", timeout: 5000}); return {code: r.status, stdout: r.stdout, stderr: r.stderr}; },
  setModel: async (m: any) => { selected.push(m.provider + "/" + m.id); return true; },
} as any, {get: (target, key) => target[key] ?? (() => {})});
factory(pi);
const parts = ${JSON.stringify(model)}.split("/");
const ctx = {cwd: ${JSON.stringify(dir)}, model: {provider: parts[0], id: parts[1]}, modelRegistry: {
  find: (provider: string, id: string) => ({provider, id}), hasConfiguredAuth: () => true,
}, ui: {notify: (text: string, level: string) => notices.push({text, level}), select: async (title: string, labels: string[]) => title.startsWith("Saved model groups") ? labels.find(s => s.includes("next-model")) : "Use this group"}, shutdown: () => {}};
let error: string | undefined;
try { await hooks[0]({}, ctx); } catch (e) { error = String(e); process.exitCode = 0; }
if (!error && ${JSON.stringify(nextModel ?? "")}) {
  saveGroup(loadModelStack(${JSON.stringify(nextConfig)}), {name: "next-model"});
  await commands["fh-groups"]("", ctx);
}
fs.writeFileSync(${JSON.stringify(path.join(dir, "result.json"))}, JSON.stringify({error, notices, selected}));
`);
  const launched = spawnSync(process.execPath, [launcher], {cwd: dir, encoding: "utf8", timeout: 10_000,
    env: {...process.env, HOME: home, NODE_PATH: path.join(dir, "node_modules"), FH_GROUPS_DIR: path.join(dir, "groups")}});
  const resultPath = path.join(dir, "result.json");
  const callsPath = path.join(dir, "catalogue.jsonl");
  return { extension, launched,
    result: fs.existsSync(resultPath) ? JSON.parse(fs.readFileSync(resultPath, "utf8")) : undefined,
    calls: fs.existsSync(callsPath) ? fs.readFileSync(callsPath, "utf8").trim().split("\n").map(s => JSON.parse(s)) : [] };
}

test.each(["google-gemini-cli/gemini-4-argon", "gemini-login/gemini-3.8-flash"])("configured Gemini catalogue explicitly loads the same provider as children: %s", (model) => {
  const f = catalogueFixture(model);
  expect(f.launched.stderr).toBe("");
  expect(f.launched.status).toBe(0);
  expect(f.result.error).toBeUndefined();
  expect(f.calls).toHaveLength(1);
  expect(f.calls[0]).toEqual(["--no-extensions", "-e", f.extension, "--list-models"]);
});

test.each([false, true])("non-Gemini catalogue does not load a provider, installed=%s", (installed) => {
  const f = catalogueFixture("test/builder", installed);
  expect(f.launched.stderr).toBe("");
  expect(f.launched.status).toBe(0);
  expect(f.result.error).toBeUndefined();
  expect(f.calls).toEqual([["--no-extensions", "--list-models"]]);
});

test("missing selected Gemini catalogue refuses before a subprocess starts", () => {
  const f = catalogueFixture("gemini-login/gemini-4-argon", false);
  expect(f.launched.status).toBe(0);
  expect(f.result.error).toContain(f.extension);
  expect(f.result.error).toContain("missing");
  expect(f.calls).toHaveLength(0);
});

test.each(["google-gemini-cli/gemini-4-argon", "gemini-login/gemini-3.8-flash"])("switching from built-in stack refreshes the provider-specific catalogue: %s", (model) => {
  const f = catalogueFixture("test/builder", true, model);
  expect(f.launched.stderr).toBe("");
  expect(f.launched.status).toBe(0);
  expect(f.result.error).toBeUndefined();
  expect(f.result.notices.filter((n: any) => n.level === "error")).toEqual([]);
  expect(f.result.selected).toEqual([model]);
  expect(f.calls).toEqual([["--no-extensions", "--list-models"], ["--no-extensions", "-e", f.extension, "--list-models"]]);
});

test("switching away from Gemini uses a catalogue without the provider", () => {
  const f = catalogueFixture("gemini-login/gemini-4-argon", true, "test/builder");
  expect(f.launched.status).toBe(0);
  expect(f.result.notices.filter((n: any) => n.level === "error")).toEqual([]);
  expect(f.result.selected).toEqual(["test/builder"]);
  expect(f.calls).toEqual([["--no-extensions", "-e", f.extension, "--list-models"], ["--no-extensions", "--list-models"]]);
});

test("compatible Gemini providers share one identical clean-room catalogue", () => {
  const f = catalogueFixture("gemini-login/gemini-4-argon", true, "google-gemini-cli/gemini-3.8-flash");
  expect(f.launched.status).toBe(0);
  expect(f.result.notices.filter((n: any) => n.level === "error")).toEqual([]);
  expect(f.result.selected).toEqual(["google-gemini-cli/gemini-3.8-flash"]);
  expect(f.calls).toEqual([["--no-extensions", "-e", f.extension, "--list-models"]]);
});
