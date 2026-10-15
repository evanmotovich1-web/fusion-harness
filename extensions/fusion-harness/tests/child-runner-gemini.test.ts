import { afterEach, expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { pathToFileURL } from "node:url";
import { FULL_TOOLS, READONLY_TOOLS } from "../modules/runtime.ts";

const dirs: string[] = [];
afterEach(() => { for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true }); });
const moduleUrl = (file: string) => pathToFileURL(path.resolve(import.meta.dir, "..", file)).href;

function childFixture(model: string, tools: string, installed = true, stopped = false) {
  const dir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "fh-gemini-child-")));
  dirs.push(dir);
  const home = path.join(dir, "home");
  fs.mkdirSync(home);
  const extension = path.join(home, ".pi/agent/extensions/gemini-login/index.ts");
  if (installed) {
    fs.mkdirSync(path.dirname(extension), { recursive: true });
    fs.writeFileSync(extension, "throw new Error('Fixture provider must not execute');\n");
  }
  const script = path.join(dir, "child.ts");
  fs.writeFileSync(script, `import * as fs from "node:fs";
const args = process.argv.slice(2);
const sessionDir = args[args.indexOf("--session-dir") + 1];
fs.writeFileSync(sessionDir + "/spawn.json", JSON.stringify({args, cwd: process.cwd(), env: {
  offline: process.env.PI_OFFLINE, globalGit: process.env.GIT_CONFIG_GLOBAL, systemGit: process.env.GIT_CONFIG_SYSTEM
}}));
console.log(JSON.stringify({type: "message_end", message: {role: "assistant", content: [{type: "text", text: "fixture answer"}]}}));
`);
  // Isolate the real runner from other test files' Bun module mocks. The process
  // captures actual subprocess argv, not an argument-builder's imagined output.
  const launcher = path.join(dir, "launcher.ts");
  fs.writeFileSync(launcher, `import * as fs from "node:fs";
import { runChild } from ${JSON.stringify(moduleUrl("modules/child-runner.ts"))};
import { newRun } from ${JSON.stringify(moduleUrl("modules/runtime.ts"))};
process.argv[1] = ${JSON.stringify(script)};
const signal = new AbortController();
if (${stopped}) signal.abort();
const run = await runChild({run: newRun("BUILDER", ${JSON.stringify(model)}, {skills: ["/fixture/declared-skill"]} as any),
  prompt: "--not-a-flag", tools: ${JSON.stringify(tools)}, thinking: "high", cwd: ${JSON.stringify(dir)},
  sessionDir: ${JSON.stringify(dir)}, sessionId: "pinned-seat", systemPrompt: "Exact JSON contract.",
  appendSystemPrompts: ["Existing stage contract."], timeoutMs: 5000, signal: signal.signal});
fs.writeFileSync(${JSON.stringify(path.join(dir, "result.json"))}, JSON.stringify({status: run.status, text: run.text, error: run.errorMessage}));
`);
  const launched = spawnSync(process.execPath, [launcher], {
    cwd: dir, encoding: "utf8", timeout: 10_000, env: { ...process.env, HOME: home },
  });
  const captured = path.join(dir, "spawn.json");
  const result = path.join(dir, "result.json");
  return { dir, extension, launched,
    spawn: fs.existsSync(captured) ? JSON.parse(fs.readFileSync(captured, "utf8")) : undefined,
    result: fs.existsSync(result) ? JSON.parse(fs.readFileSync(result, "utf8")) : undefined };
}

const models = ["google-gemini-cli/gemini-4-argon", "google-gemini-cli/gemini-3.8-flash", "gemini-login/gemini-4-argon", "gemini-login/gemini-3.8-flash"];
test.each(models)("missing selected Gemini provider fails clearly before spawn: %s", (model) => {
  const fixture = childFixture(model, "none", false);
  expect(fixture.launched.status).toBe(0);
  expect(fixture.result.status).toBe("failed");
  expect(fixture.result.error).toContain(fixture.extension);
  expect(fixture.result.error).toContain(model);
  expect(fixture.result.error).toContain("missing");
  expect(fixture.spawn).toBeUndefined();
});

test("cancellation wins even when the selected Gemini provider is missing", () => {
  const fixture = childFixture(models[0], "none", false, true);
  expect(fixture.launched.status).toBe(0);
  expect(fixture.result.status).toBe("aborted");
  expect(fixture.spawn).toBeUndefined();
});

test.each(["test/provider", "google/gemini-4-argon", "google-vertex/gemini-3.8-flash", "openai/gpt-6.1", "gemini-login-other/model"])("non-login provider never loads Gemini extension: %s", (model) => {
  for (const installed of [false, true]) {
    const fixture = childFixture(model, "none", installed);
    expect(fixture.launched.status).toBe(0);
    expect(fixture.result.status).toBe("done");
    expect(fixture.spawn.args).not.toContain("-e");
    expect(fixture.spawn.args).toContain("--no-extensions");
    expect(fixture.spawn.args).toContain("--no-tools");
  }
});

for (const model of models) {
  test.each(["none", READONLY_TOOLS, FULL_TOOLS])(`actual Gemini child explicitly loads only its provider: ${model}, tools=%s`, (tools) => {
    const fixture = childFixture(model, tools);
    expect(fixture.launched.status).toBe(0);
    expect(fixture.result).toMatchObject({status: "done", text: "fixture answer"});
    const { args, env, cwd } = fixture.spawn;
    expect(args.filter((arg: string) => arg === "-e")).toHaveLength(1);
    expect(args[args.indexOf("-e") + 1]).toBe(fixture.extension);
    expect(args).toContain("--no-extensions");
    expect(args).toContain("--no-skills");
    expect(args).toContain("--no-context-files");
    expect(args.slice(args.indexOf("--skill"), args.indexOf("--skill") + 2)).toEqual(["--skill", "/fixture/declared-skill"]);
    expect(args[args.indexOf("--model") + 1]).toBe(model);
    expect(args[args.indexOf("--thinking") + 1]).toBe("high");
    expect(args[args.indexOf("--session-id") + 1]).toBe("pinned-seat");
    expect(args[args.indexOf("--system-prompt") + 1]).toBe("Exact JSON contract.");
    const appends = args.flatMap((arg: string, i: number) => arg === "--append-system-prompt" ? [args[i + 1]] : []);
    expect(appends).toContain("Existing stage contract.");
    if (tools === "none") {
      expect(args).toContain("--no-tools");
      expect(args).not.toContain("--tools");
    } else {
      expect(args[args.indexOf("--tools") + 1]).toBe(tools);
      expect(args).not.toContain("--no-tools");
    }
    expect(args.slice(-2)).toEqual(["--", "--not-a-flag"]);
    expect(env).toEqual({offline: "1", globalGit: "/dev/null", systemGit: "/dev/null"});
    expect(cwd).toBe(fixture.dir);
  });
}
