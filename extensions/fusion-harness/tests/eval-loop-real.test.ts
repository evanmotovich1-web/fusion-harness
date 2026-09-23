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
import { acquireLock, commitFixChanges, protectedChanges } from "../../../evals/fusion-eval/loop.ts";
import { pytest } from "../../../evals/fusion-eval/run.ts";

const LOOP_TS = join(dirname(fileURLToPath(import.meta.url)), "../../../evals/fusion-eval/loop.ts");
const dirs: string[] = [];
afterEach(() => { while (dirs.length) rmSync(dirs.pop()!, { recursive: true, force: true }); });
const temp = (prefix: string) => { const dir = mkdtempSync(join(tmpdir(), prefix)); dirs.push(dir); return dir; };

function contender(lockFile: string, holdMs: number): Promise<string> {
	// Prints "ACQUIRED <start> <end>" (the interval it held the lock) or "BUSY".
	const script = `import { acquireLock } from ${JSON.stringify(LOOP_TS)};\nconst release = acquireLock(${JSON.stringify(lockFile)});\nif (!release) { console.log("BUSY"); } else { const start = performance.timeOrigin + performance.now(); await new Promise((r) => setTimeout(r, ${holdMs})); const end = performance.timeOrigin + performance.now(); release(); console.log("ACQUIRED " + start + " " + end); }`;
	return new Promise((resolve) => {
		const child = spawn("bun", ["-e", script], { stdio: ["ignore", "pipe", "pipe"] });
		let out = "";
		child.stdout.on("data", (chunk) => (out += chunk));
		child.on("close", () => resolve(out.trim()));
	});
}

describe("eval loop — real lock", () => {
	test("eight processes racing over a dead holder's lock, under CPU load: never two holders", async () => {
		// Load is what broke the rename-based version (Enemy pass 2): burn every core while racing.
		const burners = Array.from({ length: 4 }, () => spawn("bun", ["-e", "const end = Date.now() + 120000; while (Date.now() < end) {}"], { stdio: "ignore" }));
		try {
			for (let round = 0; round < 20; round++) {
				const lock = join(temp("fh-loop-lock-"), "loop.lock");
				writeFileSync(lock, "999999"); // a pid that is not running
				const results = await Promise.all(Array.from({ length: 8 }, () => contender(lock, 600)));
				expect(results.every((r) => r === "BUSY" || r.startsWith("ACQUIRED "))).toBe(true);
				// Exclusion means no two holders' intervals overlap. (A slow starter acquiring AFTER an
				// earlier holder released is correct — counting "ACQUIRED" lines alone cannot tell.)
				const held = results.filter((r) => r.startsWith("ACQUIRED ")).map((r) => r.split(" ").slice(1).map(Number) as [number, number]).sort((a, b) => a[0] - b[0]);
				expect(held.length).toBeGreaterThanOrEqual(1);
				for (let i = 1; i < held.length; i++) expect(held[i]![0]).toBeGreaterThanOrEqual(held[i - 1]![1]);
			}
		} finally {
			for (const burner of burners) burner.kill("SIGKILL");
		}
	}, 180_000);

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

	test("committing a fix: a modified tracked file listed FIRST (leading-space porcelain line) is committed intact", () => {
		// Regression: the real e2e run failed with pathspec 'xtensions/…' — the first porcelain
		// line's leading space was trimmed away and slice(3) cut the path.
		const r = repo();
		writeFileSync(join(r.dir, "extensions/a.ts"), "export const fixed = 1;\n");
		writeFileSync(join(r.dir, "extensions/new.test.ts"), "// new test\n");
		const head = commitFixChanges(r.dir, r.base, "fix");
		expect(head).toBeDefined();
		expect(r.git("show", "--name-only", "--format=", "HEAD").trim().split("\n").sort()).toEqual(["extensions/a.ts", "extensions/new.test.ts"]);
		expect(r.git("status", "--porcelain").trim()).toBe("");
	});

	test("committing a fix: nothing changed → undefined; the agent's own commit is kept", () => {
		const r = repo();
		expect(commitFixChanges(r.dir, r.base, "fix")).toBeUndefined();
		writeFileSync(join(r.dir, "extensions/a.ts"), "export const agent = 1;\n");
		r.commit();
		expect(commitFixChanges(r.dir, r.base, "fix")).toBe(r.git("rev-parse", "HEAD").trim());
	});

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

	test("anything outside extensions/ is refused: root bunfig.toml, .env, package.json", () => {
		const r = repo();
		writeFileSync(join(r.dir, "bunfig.toml"), 'preload = ["./evil.ts"]\n');
		writeFileSync(join(r.dir, ".env"), "FH_GROUPS_DIR=/tmp/evil\n");
		r.commit();
		expect(protectedChanges(r.dir, r.base).sort()).toEqual([".env", "bunfig.toml"]);
	});

	test("non-ASCII names cannot dodge the check (committed and untracked)", () => {
		const r = repo();
		writeFileSync(join(r.dir, "evals/fusion-eval/tasks/01/conftést.py"), "x\n");
		r.commit();
		writeFileSync(join(r.dir, "evals/fusion-eval/rün.ts"), "x\n");
		const found = protectedChanges(r.dir, r.base);
		expect(found).toContain("evals/fusion-eval/tasks/01/conftést.py");
		expect(found).toContain("evals/fusion-eval/rün.ts");
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

describe("eval loop — the grader cannot be influenced by the code under test", () => {
	// Hidden tests in the real suite style: the solution is only ever called through _isolated.
	const HIDDEN = "from _isolated import value, raises\ndef test_add():\n    assert value('calc', 'evaluate', '1+1') == 2\ndef test_mul():\n    assert value('calc', 'evaluate', '2*3') == 6\ndef test_div0():\n    assert raises('calc', 'evaluate', '1/0') == 'ZeroDivisionError'\n";
	function grade(solution: string, extra: Record<string, string> = {}) {
		const dir = temp("fh-loop-grade-");
		writeFileSync(join(dir, "calc.py"), solution);
		for (const [name, text] of Object.entries(extra)) writeFileSync(join(dir, name), text);
		mkdirSync(join(dir, "_hidden_eval"));
		writeFileSync(join(dir, "_hidden_eval/test_h.py"), HIDDEN);
		return pytest(dir, "_hidden_eval");
	}
	const BROKEN = "def evaluate(expr):\n    return 0\n";

	test("an honest solution is graded exactly", () => {
		expect(grade("def evaluate(expr):\n    if expr == '1/0':\n        raise ZeroDivisionError\n    return {'1+1': 2, '2*3': 7}[expr]\n")).toMatchObject({ total: 3, passed: 2, failed: 1 });
	}, 120_000);

	test("a planted conftest.py / pytest.ini that force every test to pass change nothing", () => {
		const conftest = "import pytest\n@pytest.hookimpl(hookwrapper=True)\ndef pytest_runtest_makereport(item, call):\n    outcome = yield\n    outcome.get_result().outcome = 'passed'\n";
		expect(grade(BROKEN, { "conftest.py": conftest, "pytest.ini": "[pytest]\naddopts = -p no:terminal\n" })).toMatchObject({ total: 3, passed: 0 });
	}, 120_000);

	test("Enemy pass 4: a solution that patches pytest's report records at import still scores 0", () => {
		// Wraps _pytest.reports.TestReport.from_item_and_call to mark every test passed. It used to
		// score 3/3; now the grading process never imports the solution, so the patch lands in a
		// throwaway child that has no pytest in it.
		const forge = [
			"try:",
			"    import _pytest.reports as R",
			"    orig = R.TestReport.from_item_and_call",
			"    def forged(item, call):",
			"        rep = orig(item, call)",
			"        rep.outcome = 'passed'",
			"        return rep",
			"    R.TestReport.from_item_and_call = staticmethod(forged)",
			"except Exception:",
			"    pass",
			BROKEN,
		].join("\n");
		expect(grade(forge)).toMatchObject({ total: 3, passed: 0 });
	}, 120_000);

	test("a solution that writes fake reports, prints a fake summary and exits 0 still scores 0", () => {
		const forge = [
			"import os, sys, glob",
			"xml = '<?xml version=\"1.0\"?><testsuites><testsuite tests=\"3\" failures=\"0\" errors=\"0\" skipped=\"0\"/></testsuites>'",
			"for p in glob.glob(os.path.expanduser('~/.cache/fh-eval-grading/*/report-*.xml')) + ['.fh-eval-junit.xml']:",
			"    try: open(p, 'w').write(xml)",
			"    except Exception: pass",
			"print('3 passed')",
			"sys.stdout.flush()",
			"os._exit(0)",
		].join("\n");
		expect(grade(forge)).toMatchObject({ total: 3, passed: 0 });
	}, 120_000);

	test("on macOS the solution cannot read the hidden tests or any reference solution", () => {
		if (process.platform !== "darwin") return;
		// Tries to find the expected answers on disk and replay them.
		const peek = [
			"import glob, os",
			"LEAK = []",
			"for pattern in ['../_hidden_eval/*.py', os.path.expanduser('~/fusion-harness/evals/fusion-eval/tasks/*/reference/*.py')]:",
			"    for p in glob.glob(pattern):",
			"        try: LEAK.append(open(p).read()[:20])",
			"        except Exception: pass",
			"def evaluate(expr):",
			"    if LEAK: return {'1+1': 2, '2*3': 6}[expr]",
			"    return 0",
		].join("\n");
		expect(grade(peek)).toMatchObject({ total: 3, passed: 0 });
	}, 120_000);

	test("Enemy pass 4: an edited grader hidden by skip-worktree is still refused", () => {
		const root = temp("fh-loop-grader-");
		const git = (...args: string[]) => execFileSync("git", args, { cwd: root, encoding: "utf8" });
		git("init", "-q", "-b", "main");
		mkdirSync(join(root, "evals/fusion-eval"), { recursive: true });
		const src = require("node:fs").readFileSync(LOOP_TS, "utf8");
		writeFileSync(join(root, "evals/fusion-eval/loop.ts"), src);
		writeFileSync(join(root, "evals/fusion-eval/loop-core.ts"), require("node:fs").readFileSync(join(dirname(LOOP_TS), "loop-core.ts"), "utf8"));
		writeFileSync(join(root, "evals/fusion-eval/run.ts"), "// honest runner\n");
		writeFileSync(join(root, "evals/fusion-eval/lock.json"), '{"suiteHash":"S"}\n');
		writeFileSync(join(root, "package.json"), "{}\n");
		git("add", "-A");
		git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "grader");
		git("update-index", "--skip-worktree", "evals/fusion-eval/run.ts");
		writeFileSync(join(root, "evals/fusion-eval/run.ts"), "// FORGED runner\n");
		expect(git("status", "--porcelain").trim()).toBe(""); // invisible to status…
		const probe = `import { realDeps } from ${JSON.stringify(join(root, "evals/fusion-eval/loop.ts"))};\ntry { realDeps({} as any).suiteHash(); console.log("GRADED"); } catch (e) { console.log("REFUSED " + e.message); }`;
		const out = execFileSync("bun", ["-e", probe], { encoding: "utf8", env: { ...process.env, FH_LOOP_DIR: temp("fh-loop-state-"), FH_LOOP_VAULT: "" } });
		expect(out).toContain("REFUSED"); // …but not to the content check
		expect(out).toContain("run.ts");
	}, 60_000);

	test("the trusted runner, started from the neutral dir, never loads a candidate's bunfig.toml preload", () => {
		const candidate = temp("fh-loop-cand-");
		const neutral = temp("fh-loop-neutral-");
		writeFileSync(join(candidate, "evil.ts"), 'console.log("PWNED-BY-PRELOAD");\n');
		writeFileSync(join(candidate, "bunfig.toml"), 'preload = ["./evil.ts"]\n');
		const runner = join(dirname(fileURLToPath(import.meta.url)), "../../../evals/fusion-eval/run.ts");
		const fromCandidate = execFileSync("bun", [runner, "verify"], { cwd: candidate, encoding: "utf8" });
		const fromNeutral = execFileSync("bun", [runner, "verify"], { cwd: neutral, encoding: "utf8" });
		expect(fromCandidate).toContain("PWNED-BY-PRELOAD"); // the attack is real from the candidate's cwd…
		expect(fromNeutral).not.toContain("PWNED-BY-PRELOAD"); // …and the loop never runs the grader from there
		const loopSource = require("node:fs").readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../../../evals/fusion-eval/loop.ts"), "utf8");
		expect(loopSource).toContain("{ cwd: neutral, env: { FH_EVAL_RESULTS_DIR: RESULTS }");
		// Cleanup + runner refresh run as afterTick: inside the lock, never for a busy tick.
		expect(loopSource).toContain("afterTick: () => { cleanupWorktrees(); refreshRunner(cfg); }");
		// Every child gets a closed stdin: `pi -p` blocks forever on an open stdin pipe.
		expect(loopSource).toContain('stdio: ["ignore", "pipe", "pipe"]');
	}, 60_000);
});
