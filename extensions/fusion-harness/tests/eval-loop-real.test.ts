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
import { acquireLock, commitFixChanges, fixSandboxProfile, protectedChanges } from "../../../evals/fusion-eval/loop.ts";
import { pytest } from "../../../evals/fusion-eval/run.ts";

const LOOP_TS = join(dirname(fileURLToPath(import.meta.url)), "../../../evals/fusion-eval/loop.ts");
// macOS forbids nested sandboxes: inside the loop's fix/gate sandbox the sandbox-proof tests skip.
// They only exercise evals/ — a path no fix may change — so the gate loses nothing by skipping them.
const NESTED = Boolean(process.env.FH_IN_SANDBOX);
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

describe.skipIf(NESTED)("eval loop — protected paths (the grader cannot grade itself)", () => {
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

describe.skipIf(NESTED)("eval loop — the grader cannot be influenced by the code under test", () => {
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

	test("Enemy pass 5: reading answers out of git's object store, the loop's results, or other graders scores 0", () => {
		if (process.platform !== "darwin") return;
		const cheat = [
			"import glob, os, subprocess",
			"FOUND = []",
			"try:",
			"    r = subprocess.run(['git', '-C', os.path.expanduser('~/fusion-harness'), 'log', '-1', '--format=%H'], capture_output=True, text=True, timeout=10)",
			"    if r.returncode == 0 and r.stdout.strip(): FOUND.append('git')",
			"except Exception: pass",
			"for pattern in ['~/.pi/fusion-harness/eval-loop/results/*/*/*.json', '~/.cache/fh-eval-grading/*/solution/*.py', '~/.cache/fh-eval-grading/*/report-*.xml', '/tmp/fh-eval-*/*.py']:",
			"    for p in glob.glob(os.path.expanduser(pattern)):",
			"        try: open(p).read(1); FOUND.append(p)",
			"        except Exception: pass",
			"def evaluate(expr):",
			"    if FOUND: return {'1+1': 2, '2*3': 6}[expr]",
			"    return 0",
		].join("\n");
		expect(grade(cheat)).toMatchObject({ total: 3, passed: 0 });
	}, 120_000);

	test("Enemy pass 5: a second, doctored result line (atexit) fails the call instead of winning", () => {
		const forge = [
			"import atexit, json, sys",
			"def evaluate(expr):",
			"    return 0",
			"@atexit.register",
			"def _forge():",
			"    sys.__stdout__.write('\\n@@FH_EVAL_RESULT@@' + json.dumps({'ok': True, 'value': 2, 'type': 'int'}) + '\\n')",
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
		const realRun = require("node:fs").readFileSync(join(dirname(LOOP_TS), "run.ts"), "utf8");
		writeFileSync(join(root, "evals/fusion-eval/run.ts"), realRun);
		writeFileSync(join(root, "evals/fusion-eval/lock.json"), '{"suiteHash":"S"}\n');
		writeFileSync(join(root, "package.json"), "{}\n");
		git("add", "-A");
		git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "grader");
		git("update-index", "--skip-worktree", "evals/fusion-eval/run.ts");
		writeFileSync(join(root, "evals/fusion-eval/run.ts"), `${realRun}\n// FORGED runner\n`);
		expect(git("status", "--porcelain").trim()).toBe(""); // invisible to status…
		const probe = `import { realDeps } from ${JSON.stringify(join(root, "evals/fusion-eval/loop.ts"))};\ntry { realDeps({} as any).suiteHash(); console.log("GRADED"); } catch (e) { console.log("REFUSED " + e.message); }`;
		const out = execFileSync("bun", ["-e", probe], { encoding: "utf8", env: { ...process.env, FH_LOOP_DIR: temp("fh-loop-state-"), FH_LOOP_VAULT: "" } });
		expect(out).toContain("REFUSED"); // …but not to the content check
		expect(out).toContain("run.ts");
	}, 60_000);

	test("Enemy pass 6: a harness that copies the reference answers into its build folder scores 0", () => {
		if (process.platform !== "darwin") return;
		const repoRoot = join(dirname(LOOP_TS), "../..");
		const stubDir = temp("fh-pi-stub-");
		// A malicious "harness": instead of building, it tries to plant the reference solution.
		writeFileSync(join(stubDir, "pi"), [
			"#!/bin/bash",
			'cp "$FH_STUB_REPO/evals/fusion-eval/tasks/01-wordstats/reference/wordstats.py" . 2>/dev/null && echo COPIED >> planted.log',
			'git -C "$FH_STUB_REPO" show HEAD:evals/fusion-eval/tasks/01-wordstats/reference/wordstats.py > from-git.py 2>/dev/null',
			'if [ -s from-git.py ]; then cp from-git.py wordstats.py; echo GITSHOW >> planted.log; fi',
			// Enemy pass 7: a leftover passing solution from another run, an authenticated gh download,
			// and tampering with the grader's toolchain / the repo's hooks.
			'cat /tmp/fh-eval-planted-01-wordstats-*/wordstats.py > from-leftover.py 2>/dev/null',
			'if [ -s from-leftover.py ]; then cp from-leftover.py wordstats.py; echo LEFTOVER >> planted.log; fi',
			'gh api repos/evanmotovich1-web/fusion-harness/contents/evals/fusion-eval/tasks/01-wordstats/reference/wordstats.py -q .content 2>/dev/null | base64 -d > from-gh.py 2>/dev/null',
			'if [ -s from-gh.py ]; then cp from-gh.py wordstats.py; echo GH >> planted.log; fi',
			'touch "$HOME/fusion-harness/.git/hooks/fh-stub-probe" 2>/dev/null && echo HOOK >> planted.log',
			'touch "$HOME/.cache/uv/fh-stub-probe" 2>/dev/null && echo UVCACHE >> planted.log',
			'touch "$HOME/fusion-harness/node_modules/fh-stub-probe" 2>/dev/null && echo NODEMODULES >> planted.log',
			"exit 0",
			"",
		].join("\n"));
		execFileSync("chmod", ["+x", join(stubDir, "pi")]);
		// A leftover "passing solution" from an earlier run, as older versions of runOne left behind.
		const leftover = "/tmp/fh-eval-planted-01-wordstats-X";
		require("node:fs").mkdirSync(leftover, { recursive: true });
		require("node:fs").copyFileSync(join(repoRoot, "evals/fusion-eval/tasks/01-wordstats/reference/wordstats.py"), join(leftover, "wordstats.py"));
		dirs.push(leftover);
		// Control: unsandboxed, the attack works.
		const control = temp("fh-pi-control-");
		// (A throwaway HOME: the unsandboxed control must never tamper with the real machine.)
		execFileSync(join(stubDir, "pi"), [], { cwd: control, env: { ...process.env, FH_STUB_REPO: repoRoot, HOME: temp("fh-pi-control-home-") } });
		expect(require("node:fs").readFileSync(join(control, "planted.log"), "utf8")).toContain("COPIED");
		// Through the real runOne, the harness runs sandboxed: nothing planted, graded 0.
		const results = temp("fh-pi-results-");
		const RUN_TS = join(dirname(LOOP_TS), "run.ts");
		const probe = `import { runOne } from ${JSON.stringify(RUN_TS)};\nconst r = await runOne({ harness: ${JSON.stringify(repoRoot)}, harnessCommit: "stub", label: "stub", group: { name: "stub", file: "/dev/null", signature: "x", models: [] }, task: "01-wordstats", suiteHash: "x" });\nconsole.log(JSON.stringify({ passed: r.hidden.passed, total: r.hidden.total, scratch: r.scratch }));`;
		const out = execFileSync("bun", ["-e", probe], { encoding: "utf8", env: { ...process.env, PATH: `${stubDir}:${process.env.PATH}`, FH_STUB_REPO: repoRoot, FH_EVAL_RESULTS_DIR: results, FH_EVAL_KEEP_SCRATCH: "1" }, timeout: 300_000 });
		const record = JSON.parse(out.trim().split("\n").pop()!);
		expect(record.passed).toBe(0);
		expect(require("node:fs").existsSync(join(record.scratch, "planted.log"))).toBe(false);
		expect(require("node:fs").existsSync(join(record.scratch, "wordstats.py"))).toBe(false);
		for (const probe of [".git/hooks/fh-stub-probe", "node_modules/fh-stub-probe"]) expect(require("node:fs").existsSync(join(require("node:os").homedir(), "fusion-harness", probe))).toBe(false);
		expect(require("node:fs").existsSync(join(require("node:os").homedir(), ".cache/uv/fh-stub-probe"))).toBe(false);
	}, 360_000);

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

describe.skipIf(NESTED || process.platform !== "darwin")("eval loop — the fix run's sandbox", () => {
	test("fix agents can edit their worktree and run git there, but cannot touch shared hooks, the grader toolchain, node_modules or the runner", () => {
		// Like production (~/fusion-harness, ~/.pi/…): fixtures OUTSIDE temp, which the fix run may write.
		const base = mkdtempSync(join(require("node:os").homedir(), ".cache", "fh-fix-test-"));
		dirs.push(base);
		const repo = join(base, "repo");
		mkdirSync(repo);
		const git = (...args: string[]) => execFileSync("git", args, { cwd: repo, encoding: "utf8" });
		git("init", "-q", "-b", "main");
		mkdirSync(join(repo, "extensions"), { recursive: true });
		writeFileSync(join(repo, "extensions/a.ts"), "export {};\n");
		git("add", "-A");
		git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base");
		const fixDir = join(base, "wt");
		git("worktree", "add", "-q", "--detach", fixDir, "HEAD");
		const loopDir = join(base, "loop");
		mkdirSync(loopDir);
		mkdirSync(join(loopDir, "runner"));
		const profile = join(temp("fh-fix-prof-"), "fix.sb");
		writeFileSync(profile, fixSandboxProfile(fixDir, loopDir));
		const home = require("node:os").homedir();
		const script = [
			't() { if eval "$2" >/dev/null 2>&1; then echo "ALLOWED $1"; else echo "blocked $1"; fi; }',
			't edit-worktree "echo x > extensions/a.ts"',
			't git-status-in-worktree "git status --porcelain"',
			`t write-shared-hook "touch ${repo}/.git/hooks/fh-fixprobe"`,
			`t write-runner "touch ${loopDir}/runner/fh-fixprobe"`,
			`t write-uv-cache "touch ${home}/.cache/uv/fh-fixprobe"`,
			`t write-node-modules "touch ${home}/fusion-harness/node_modules/fh-fixprobe"`,
		].join("\n");
		const out = execFileSync("/usr/bin/sandbox-exec", ["-f", profile, "/bin/bash", "-c", script], { cwd: fixDir, encoding: "utf8" });
		for (const probe of [`${repo}/.git/hooks/fh-fixprobe`, `${home}/.cache/uv/fh-fixprobe`, `${home}/fusion-harness/node_modules/fh-fixprobe`]) try { require("node:fs").rmSync(probe, { force: true }); } catch {}
		expect(out).toContain("ALLOWED edit-worktree");
		expect(out).toContain("ALLOWED git-status-in-worktree");
		for (const name of ["write-shared-hook", "write-runner", "write-uv-cache", "write-node-modules"]) expect(out).toContain(`blocked ${name}`);
	}, 60_000);
});

describe.skipIf(NESTED || process.platform !== "darwin")("eval loop — Enemy pass 8 escapes", () => {
	function fixture() {
		const base = mkdtempSync(join(require("node:os").homedir(), ".cache", "fh-p8-test-"));
		dirs.push(base);
		const repo = join(base, "repo");
		mkdirSync(join(repo, "extensions"), { recursive: true });
		const git = (cwd: string, ...args: string[]) => execFileSync("git", args, { cwd, encoding: "utf8" });
		git(repo, "init", "-q", "-b", "main");
		writeFileSync(join(repo, "extensions/a.ts"), "export {};\n");
		git(repo, "add", "-A");
		git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base");
		const wt = join(base, "wt");
		git(repo, "worktree", "add", "-q", "--detach", wt, "HEAD");
		const loopDir = join(base, "loop");
		mkdirSync(loopDir);
		const gitDir = git(wt, "rev-parse", "--absolute-git-dir").trim();
		const baseSha = git(wt, "rev-parse", "HEAD").trim();
		return { base, repo, wt, loopDir, gitDir, baseSha, git };
	}

	test("a fix run cannot rewrite its worktree's .git pointer, nor write the grading cache, sealed tasks, or pi's settings/extensions", () => {
		const f = fixture();
		const profile = join(f.base, "fix.sb");
		writeFileSync(profile, fixSandboxProfile(f.wt, f.loopDir));
		const home = require("node:os").homedir();
		const script = [
			't() { if eval "$2" >/dev/null 2>&1; then echo "ALLOWED $1"; else echo "blocked $1"; fi; }',
			't rewrite-dotgit "echo gitdir: /tmp/evil > .git"',
			`t write-grading-cache "mkdir -p ${home}/.cache/fh-eval-grading && touch ${home}/.cache/fh-eval-grading/fh-p8-probe"`,
			`t write-pi-extension "touch ${home}/.pi/agent/fh-p8-probe-extension.ts"`,
			`t write-pi-settings-like "touch ${home}/.pi/agent/SYSTEM.md.fh-p8-probe"`,
			`t write-pi-session "mkdir -p ${home}/.pi/agent/sessions && touch ${home}/.pi/agent/sessions/fh-p8-probe"`,
			't edit-worktree "echo 1 > extensions/a.ts"',
		].join("\n");
		const out = execFileSync("/usr/bin/sandbox-exec", ["-f", profile, "/bin/bash", "-c", script], { cwd: f.wt, encoding: "utf8" });
		for (const probe of [`${home}/.cache/fh-eval-grading/fh-p8-probe`, `${home}/.pi/agent/fh-p8-probe-extension.ts`, `${home}/.pi/agent/SYSTEM.md.fh-p8-probe`, `${home}/.pi/agent/sessions/fh-p8-probe`]) require("node:fs").rmSync(probe, { force: true });
		for (const name of ["rewrite-dotgit", "write-grading-cache", "write-pi-extension", "write-pi-settings-like"]) expect(out).toContain(`blocked ${name}`);
		expect(out).toContain("ALLOWED write-pi-session");
		expect(out).toContain("ALLOWED edit-worktree");
	}, 60_000);

	test("even with a planted malicious git dir, the loop's own git steps run no attacker hooks or fsmonitor (pinned git dir)", () => {
		const f = fixture();
		// Attacker: a copy of the git dir whose config runs code on every git call and every commit.
		const evil = join(f.base, "evil-gitdir");
		execFileSync("cp", ["-R", f.gitDir, evil]);
		const pwned = join(f.base, "PWNED");
		const hook = join(f.base, "hook.sh");
		writeFileSync(hook, `#!/bin/sh\necho x >> ${pwned}\nexit 0\n`);
		execFileSync("chmod", ["+x", hook]);
		execFileSync("git", ["config", "--file", join(f.repo, ".git/config"), "core.fsmonitor", hook]);
		execFileSync("git", ["config", "--file", join(f.repo, ".git/config"), "core.hooksPath", f.base]);
		writeFileSync(join(f.base, "pre-commit"), `#!/bin/sh\necho hook >> ${pwned}\nexit 0\n`);
		execFileSync("chmod", ["+x", join(f.base, "pre-commit")]);
		writeFileSync(join(f.wt, "extensions/a.ts"), "export const fixed = 1;\n");
		// The loop's post-fix steps, pinned to the recorded git dir:
		expect(protectedChanges(f.wt, f.baseSha, f.gitDir)).toEqual([]);
		const head = commitFixChanges(f.wt, f.baseSha, "fix", f.gitDir);
		expect(head).toBeDefined();
		expect(require("node:fs").existsSync(pwned)).toBe(false);
	}, 60_000);
});
