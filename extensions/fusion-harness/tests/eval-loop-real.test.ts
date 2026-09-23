/**
 * Real-I/O checks for the eval loop that fakes cannot reach (Enemy review
 * defects 1 and 3): the lock under real multi-process contention with a stale
 * lock left by a dead process, and the protected-path guard against a real git
 * repo — committed edits, renames out, deletions and untracked files.
 */
import { afterEach, describe, expect, test } from "bun:test";
import { spawn, execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { acquireLock, protectedChanges } from "../../../evals/fusion-eval/loop.ts";

const LOOP_TS = join(dirname(fileURLToPath(import.meta.url)), "../../../evals/fusion-eval/loop.ts");
const dirs: string[] = [];
afterEach(() => { while (dirs.length) rmSync(dirs.pop()!, { recursive: true, force: true }); });
const temp = (prefix: string) => { const dir = mkdtempSync(join(tmpdir(), prefix)); dirs.push(dir); return dir; };

function contender(lockFile: string, holdMs: number): Promise<string> {
	const script = `import { acquireLock } from ${JSON.stringify(LOOP_TS)};\nconst release = acquireLock(${JSON.stringify(lockFile)});\nconsole.log(release ? "ACQUIRED" : "BUSY");\nawait new Promise((r) => setTimeout(r, ${holdMs}));\nrelease?.();`;
	return new Promise((resolve) => {
		const child = spawn("bun", ["-e", script], { stdio: ["ignore", "pipe", "pipe"] });
		let out = "";
		child.stdout.on("data", (chunk) => (out += chunk));
		child.on("close", () => resolve(out.trim()));
	});
}

describe("eval loop — real lock", () => {
	test("three processes racing over a dead holder's lock: exactly one acquires", async () => {
		for (let round = 0; round < 5; round++) {
			const lock = join(temp("fh-loop-lock-"), "loop.lock");
			writeFileSync(lock, "999999"); // a pid that is not running
			const results = await Promise.all([contender(lock, 400), contender(lock, 400), contender(lock, 400)]);
			expect(results.filter((r) => r === "ACQUIRED")).toHaveLength(1);
			expect(results.filter((r) => r === "BUSY")).toHaveLength(2);
		}
	}, 60_000);

	test("a live holder keeps the lock; release frees it", () => {
		const lock = join(temp("fh-loop-lock-"), "loop.lock");
		const release = acquireLock(lock)!;
		expect(release).toBeDefined();
		expect(acquireLock(lock)).toBeUndefined(); // same live pid holds it
		release();
		expect(existsSync(lock)).toBe(false);
		acquireLock(lock)!();
	});
});

describe("eval loop — protected paths (the grader cannot grade itself)", () => {
	function repo() {
		const dir = temp("fh-loop-guard-");
		const git = (...args: string[]) => execFileSync("git", args, { cwd: dir, encoding: "utf8" });
		git("init", "-q", "-b", "main");
		mkdirSync(join(dir, "evals/fusion-eval/tasks/01"), { recursive: true });
		mkdirSync(join(dir, "extensions"), { recursive: true });
		writeFileSync(join(dir, "evals/fusion-eval/lock.json"), "{}\n");
		writeFileSync(join(dir, "evals/fusion-eval/run.ts"), "// runner\n");
		writeFileSync(join(dir, "evals/fusion-eval/tasks/01/prompt.md"), "task\n");
		writeFileSync(join(dir, "extensions/a.ts"), "export {};\n");
		git("add", "-A");
		git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base");
		const base = git("rev-parse", "HEAD").trim();
		const commit = () => { git("add", "-A"); git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "agent"); };
		return { dir, git, base, commit };
	}

	test("a harness-only change is allowed", () => {
		const r = repo();
		writeFileSync(join(r.dir, "extensions/a.ts"), "export const fixed = true;\n");
		r.commit();
		expect(protectedChanges(r.dir, r.base)).toEqual([]);
	});

	test("an agent that COMMITS a re-locked lock.json is caught", () => {
		const r = repo();
		writeFileSync(join(r.dir, "evals/fusion-eval/lock.json"), '{"forged":true}\n');
		r.commit();
		expect(protectedChanges(r.dir, r.base)).toEqual(["evals/fusion-eval/lock.json"]);
	});

	test("editing the runner itself (run.ts) is caught, committed or not", () => {
		const r = repo();
		writeFileSync(join(r.dir, "evals/fusion-eval/run.ts"), "// always pass\n");
		expect(protectedChanges(r.dir, r.base)).toEqual(["evals/fusion-eval/run.ts"]);
	});

	test("renaming a task out, deleting one, or adding an untracked file under evals/ is caught", () => {
		const r = repo();
		r.git("mv", "evals/fusion-eval/tasks/01/prompt.md", "extensions/prompt.md");
		writeFileSync(join(r.dir, "evals/fusion-eval/new.txt"), "x\n");
		const found = protectedChanges(r.dir, r.base);
		expect(found).toContain("evals/fusion-eval/tasks/01/prompt.md");
		expect(found).toContain("evals/fusion-eval/new.txt");
	});
});
