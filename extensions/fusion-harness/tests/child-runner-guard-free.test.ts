import { afterEach, expect, test } from "bun:test";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";
import { FULL_TOOLS } from "../modules/runtime.ts";

const dirs: string[] = [];
afterEach(() => { for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true }); });

test("actual child spawn uses explicit tools and clean-room flags, with no guard or ack dependency", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fh-guard-free-"));
  dirs.push(dir);
  // Disposable Bun child, not a provider: capture the real runner argv/env, emit one valid Pi event,
  // and intentionally write no load acknowledgement.
  const script = path.join(dir, "child.ts");
  fs.writeFileSync(script, `import * as fs from "node:fs";
import * as path from "node:path";
const args = process.argv.slice(2);
const sessionDir = args[args.indexOf("--session-dir") + 1];
fs.writeFileSync(path.join(sessionDir, "spawn.json"), JSON.stringify({args, env: {
  guardAck: process.env.FH_GUARD_ACK ?? null,
  globalGit: process.env.GIT_CONFIG_GLOBAL, systemGit: process.env.GIT_CONFIG_SYSTEM
}}));
console.log(JSON.stringify({type: "message_end", message: {role: "assistant", content: [{type: "text", text: "fixture answer"}]}}));
`);
  // Run the real module in a separate process: other integration tests mock child-runner
  // in their Bun test process, which would make an in-process spawn test a false positive.
  const runnerUrl = pathToFileURL(path.resolve(import.meta.dir, "../modules/child-runner.ts")).href;
  const runtimeUrl = pathToFileURL(path.resolve(import.meta.dir, "../modules/runtime.ts")).href;
  const launcher = path.join(dir, "launcher.ts");
  fs.writeFileSync(launcher, `import * as fs from "node:fs";
import * as path from "node:path";
import { runChild } from ${JSON.stringify(runnerUrl)};
import { FULL_TOOLS, newRun } from ${JSON.stringify(runtimeUrl)};
const dir = process.argv[2], script = process.argv[3];
process.argv[1] = script;
const run = await runChild({run: newRun("BUILDER", "test/provider"), prompt: "--not-a-flag",
  tools: FULL_TOOLS, thinking: "off", sessionDir: dir, cwd: dir, timeoutMs: 5000});
fs.writeFileSync(path.join(dir, "result.json"), JSON.stringify({status: run.status, text: run.text}));
`);
  const launched = spawnSync(process.execPath, [launcher, dir, script], { cwd: dir, encoding: "utf8", timeout: 10_000 });
  expect(launched.status).toBe(0);
  expect(fs.existsSync(path.join(dir, "spawn.json"))).toBe(true);
  const run = JSON.parse(fs.readFileSync(path.join(dir, "result.json"), "utf8"));
  const { args, env } = JSON.parse(fs.readFileSync(path.join(dir, "spawn.json"), "utf8"));
  expect(run.status).toBe("done");
  expect(run.text).toBe("fixture answer");
  expect(args).toContain("--no-skills");
  expect(args).toContain("--no-extensions");
  expect(args).toContain("--no-context-files");
  expect(args.slice(args.indexOf("--tools"), args.indexOf("--tools") + 2)).toEqual(["--tools", FULL_TOOLS]);
  expect(args.slice(-2)).toEqual(["--", "--not-a-flag"]);
  expect(args).not.toContain("-e");
  expect(env.guardAck).toBeNull();
  expect(env.globalGit).toBe("/dev/null");
  expect(env.systemGit).toBe("/dev/null");
});
