#!/usr/bin/env bun
/**
 * fusion eval loop — the self-improving loop, wired to the real world.
 *
 *   bun evals/fusion-eval/loop.ts tick        one pass (what the schedule runs)
 *   bun evals/fusion-eval/loop.ts status      state, the accepted bar, recent history
 *   bun evals/fusion-eval/loop.ts seed --from <results-dir/label>   set the bar from an existing run
 *   bun evals/fusion-eval/loop.ts install     launchd: tick every 30 min
 *   bun evals/fusion-eval/loop.ts uninstall
 *
 * Decisions live in loop-core.ts (pure, stress-tested). This file only does I/O:
 * git worktrees per commit (never the shared checkout), paid eval runs through
 * run.ts, the fix run through /fh-collaborate in its own worktree, gate tests,
 * PRs via gh, the loop log, and ROT lines in the second-brain vault.
 *
 * State and results: ~/.pi/fusion-harness/eval-loop/ (FH_LOOP_DIR overrides).
 */
import { spawn, spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { emptyState, tick, type EvalRecord, type FixProposal, type LoopConfig, type LoopDeps, type LoopState } from "./loop-core.ts";
import { homeReadRules, prepareAgentDir, privateRunRoot, profileDir, real, removeTree, secretReadDenies, sharedTempReadDenies, sizeLimited } from "./run.ts";

/**
 * Sandbox for the FIX run (models with edit tools, driven by the accepted harness). Writes
 * are deny-by-default: only the fix worktree, that worktree's own git metadata, run
 * artifacts, temp, the grading cache (so its tests can run) and pi's state — never the
 * shared .git (hooks, objects), the grader's Python/pytest, node_modules, the runner, or
 * the loop's results/state. Credentials and the keychain are denied.
 */
export function fixSandboxProfile(fixDir: string, loopDir: string, readable: string[] = [], runRoot?: string): string {
	const home = os.homedir();
	const q = (p: string) => JSON.stringify(real(p));
	const dir = real(fixDir);
	// The worktree's git dir lives in the shared repo's .git (outside the home allow-list): readable, so
	// fix agents can run git status/diff/log; never writable (hooks, config — Enemy pass 8).
	const common = spawnSync("git", ["rev-parse", "--path-format=absolute", "--git-common-dir"], { cwd: fixDir, encoding: "utf8" });
	const gitDirs = common.status === 0 && common.stdout.trim() ? [common.stdout.trim()] : [];
	return [
		"(version 1)",
		"(allow default)",
		"(deny file-write*)",
		// The worktree's files — but NOT its .git pointer, and no git metadata at all (Enemy pass 8:
		// a rewritten .git made the loop's later, unsandboxed git calls run attacker hooks/fsmonitor).
		// Writes: the worktree, its private run root (TMPDIR + artifacts), /dev. Not ~/.pi/agent (throwaway agent
		// dir, prepareAgentDir), not the shared TMPDIR (pi's compiled-extension cache), not others' /tmp/fusion-harness-*.
		`(allow file-write* (subpath ${JSON.stringify(dir)}) ${runRoot ? `(subpath ${JSON.stringify(real(runRoot))})` : ""} (subpath "/dev"))`,
		`(deny file-write* (literal ${JSON.stringify(path.join(dir, ".git"))}))`,
		sharedTempReadDenies(),
		homeReadRules([fixDir, path.join(fixDir, "node_modules"), ...gitDirs, ...(runRoot ? [runRoot] : []), ...readable.flatMap((p) => [p, path.join(p, "node_modules")])]),
		`(deny file-read* (subpath ${q(path.join(loopDir, "runner"))}) (subpath ${q(path.join(loopDir, "results"))}) (literal ${q(path.join(loopDir, "state.json"))}) (subpath ${q(path.join(home, ".cache", "fh-eval-grading"))}) (subpath ${q(path.join(home, ".cache", "fh-eval-profiles"))}) ${secretReadDenies()} (regex #"/evals/fusion-eval/tasks(/|$)"))`,
		"(deny file-write-flags)", // no chflags: uchg on files the loop later removes or commits
		'(deny mach-lookup (global-name "com.apple.SecurityServer") (global-name "com.apple.securityd.xpc") (global-name "com.apple.security.agent"))',
		"",
	].join("\n");
}

/**
 * A log line bound for the vault (ROT.md, indexed into the wiki agents read before deciding): one
 * plain line, no wiki links, embeds, HTML, code or mentions — whatever a candidate managed to put
 * into a path name or an error message stays inert text.
 */
export function vaultSafe(line: string): string {
	return line.replace(/\s+/g, " ").replace(/\[\[|\]\]|[<>`!|]/g, "").replace(/@/g, "(at)").slice(0, 400);
}

/**
 * git on a worktree the candidate touched: never trust its `.git` pointer or its config.
 * Uses the git dir recorded BEFORE the fix ran, with hooks and fsmonitor forced off.
 */
function safeGit(gitDir: string, workTree: string, args: string[]): string {
	return git(["--git-dir", gitDir, "--work-tree", workTree, "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=", "-c", "core.untrackedCache=false", ...args], workTree);
}

const HOME = os.homedir();
const LOOP_DIR = process.env.FH_LOOP_DIR || path.join(HOME, ".pi", "fusion-harness", "eval-loop");
const REPO = process.env.FH_LOOP_REPO || path.join(HOME, "fusion-harness");
const VAULT = process.env.FH_LOOP_VAULT ?? path.join(HOME, "code", "second-brain");
const STATE = path.join(LOOP_DIR, "state.json");
const LOCK = path.join(LOOP_DIR, "loop.lock");
const LOG = path.join(LOOP_DIR, "loop.log");
const RESULTS = path.join(LOOP_DIR, "results");
const GROUPS_INDEX = path.join(HOME, ".pi", "fusion-harness", "groups", "groups.json");
const PLIST = path.join(HOME, "Library", "LaunchAgents", "com.evanmotovich.fusion-eval-loop.plist");
/** The loop grades every commit with ITS OWN runner and sealed tasks, never the candidate's. */
const TRUSTED_EVAL_DIR = path.dirname(new URL(import.meta.url).pathname);
/** The ONLY paths a fix may change. Everything else — evals/, bunfig.toml, .env, package.json — is refused. */
const FIXABLE = /^extensions\//;
/** Environment the grader and fix runs get: nothing a candidate could have planted. */
const ENV_KEEP = ["PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "TMPDIR", "TERM"];
/** Worktrees THIS process created — the only ones it may remove. */
const created: string[] = [];

interface FullConfig extends LoopConfig { remote: string; branch: string; fixGroup: string }
const DEFAULTS: FullConfig = {
	groups: ["local"],
	nightlyGroups: ["local", "quad", "council"],
	nightlyEveryMs: 24 * 3600_000,
	autoMerge: true,
	remote: "fork",
	branch: "main",
	fixGroup: "quad",
};

function config(): FullConfig {
	const file = path.join(LOOP_DIR, "config.json");
	const custom = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : {};
	return { ...DEFAULTS, ...custom };
}

function git(args: string[], cwd = REPO): string {
	const result = spawnSync("git", args, { cwd, encoding: "utf8", timeout: 300_000 });
	if (result.status !== 0) throw new Error(`git ${args.join(" ")} failed: ${(result.stderr || result.stdout).trim().slice(0, 500)}`);
	return result.stdout.trim();
}

function cleanEnv(extra: Record<string, string> = {}): Record<string, string> {
	const env: Record<string, string> = {};
	for (const key of ENV_KEEP) if (process.env[key] !== undefined) env[key] = process.env[key]!;
	return { ...env, ...extra };
}

export function run(cmd: string, args: string[], opts: { cwd: string; env?: Record<string, string>; timeoutMs: number; logFile?: string; killGroup?: boolean }): Promise<{ code: number | null; out: string }> {
	return new Promise((resolve) => {
		const chunks: Buffer[] = [];
		// Always a whitelisted environment: nothing from the caller's shell or a candidate's .env leaks in.
		// stdin MUST be closed: `pi -p` treats piped stdin as more prompt and waits for EOF forever
		// (found by the real end-to-end run: the fix step hung at 0% CPU).
		const child = spawn(cmd, args, { cwd: opts.cwd, env: cleanEnv(opts.env), stdio: ["ignore", "pipe", "pipe"], detached: Boolean(opts.killGroup) });
		// killGroup: the child leads its own process group and the whole group is killed when it ends,
		// so nothing a sandboxed run started (watchers, daemons) outlives it into the grading steps.
		const reap = () => { if (opts.killGroup) try { process.kill(-child.pid!, "SIGKILL"); } catch { /* gone */ } };
		const sink = opts.logFile ? fs.createWriteStream(opts.logFile, { flags: "a" }) : undefined;
		// Bounded (Enemy pass 14: a gate test flooding stdout grew the buffer until the loop died with
		// ERR_STRING_TOO_LONG, and the lock and cleanup never ran). Keep the last 2 MB; log at most 50 MB.
		let kept = 0;
		let logged = 0;
		const take = (chunk: Buffer) => {
			chunks.push(chunk);
			kept += chunk.length;
			while (kept > 2_000_000 && chunks.length > 1) kept -= chunks.shift()!.length;
			if (sink && logged < 50_000_000) { logged += chunk.length; sink.write(chunk); }
		};
		child.stdout.on("data", take);
		child.stderr.on("data", take);
		const timer = setTimeout(() => { child.kill("SIGTERM"); reap(); }, opts.timeoutMs);
		child.on("close", (code) => { clearTimeout(timer); reap(); sink?.end(); resolve({ code, out: Buffer.concat(chunks).toString("utf8") }); });
		child.on("error", (error) => { clearTimeout(timer); reap(); resolve({ code: -1, out: String(error) }); });
	});
}

/**
 * A FRESH detached worktree per commit and purpose: evaluations never see the
 * shared checkout's WIP, and nothing one step writes (test output, caches) can
 * leak into the next step.
 */
function worktree(commit: string, purpose: string): string {
	const dir = path.join(LOOP_DIR, "wt", `${commit.slice(0, 12)}-${purpose}`);
	if (fs.existsSync(dir)) {
		spawnSync("git", ["worktree", "remove", "--force", dir], { cwd: REPO });
		removeTree(dir); // undoes chmod locks a fix/gate run left; never throws
	}
	git(["worktree", "add", "--detach", "--force", dir, commit]);
	created.push(dir);
	linkDependencies(dir);
	return dir;
}

/**
 * Share the checkout's node_modules only when the candidate, the trusted runner's
 * COMMITTED package.json, and the checkout that installed node_modules all agree.
 */
function linkDependencies(dir: string): void {
	const trustedRoot = path.resolve(TRUSTED_EVAL_DIR, "../..");
	const committed = spawnSync("git", ["show", "HEAD:package.json"], { cwd: trustedRoot, encoding: "utf8" }).stdout;
	const mine = fs.readFileSync(path.join(dir, "package.json"), "utf8");
	const installed = fs.readFileSync(path.join(REPO, "package.json"), "utf8");
	if (mine !== committed || installed !== committed) throw new Error("package.json differs between the candidate, the trusted runner and the installed checkout — dependencies changed; install them before evaluating");
	fs.symlinkSync(path.join(REPO, "node_modules"), path.join(dir, "node_modules"));
}

/**
 * Every path changed since `base` — committed, staged, unstaged, untracked, both
 * sides of renames — that lies outside extensions/. NUL-separated and unquoted so
 * unusual file names cannot dodge the check.
 */
export function protectedChanges(dir: string, base: string, gitDir?: string): string[] {
	const changed = new Set<string>();
	const pin = gitDir ? ["--git-dir", gitDir, "--work-tree", dir, "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor="] : [];
	const diff = spawnSync("git", [...pin, "-c", "core.quotepath=false", "diff", "--name-only", "--no-renames", "-z", base], { cwd: dir, encoding: "utf8" });
	for (const file of diff.stdout.split("\0").filter(Boolean)) changed.add(file);
	const untracked = spawnSync("git", [...pin, "-c", "core.quotepath=false", "ls-files", "--others", "--exclude-standard", "-z"], { cwd: dir, encoding: "utf8" });
	for (const file of untracked.stdout.split("\0").filter(Boolean)) changed.add(file);
	return [...changed].filter((file) => file !== "node_modules" && !FIXABLE.test(file));
}

/**
 * Commit whatever the fix run changed under extensions/ (the only fixable paths — the
 * caller has already rejected anything else) and return the new HEAD, or undefined if
 * nothing changed. Stages by pathspec, never by parsing porcelain: git() trims output,
 * which once ate the first line's leading space and turned "extensions/…" into
 * "xtensions/…" in the real end-to-end run.
 */
export function commitFixChanges(dir: string, base: string, message: string, gitDir?: string): string | undefined {
	const g = (args: string[]) => (gitDir ? safeGit(gitDir, dir, args) : git(args, dir));
	const dirty = g(["status", "--porcelain", "--", "extensions/"]);
	if (dirty) {
		g(["add", "-A", "--", "extensions/"]);
		g(["-c", "user.name=fusion-eval-loop", "-c", "user.email=noreply@anthropic.com", "commit", "-q", "--no-verify", "-m", message]);
	}
	const head = g(["rev-parse", "HEAD"]);
	return head === g(["rev-parse", base]) ? undefined : head;
}

/** Remove only the worktrees THIS process created (the pushed fix branches stay on the remote). */
function cleanupWorktrees(): void {
	for (const dir of created.splice(0)) {
		spawnSync("git", ["worktree", "remove", "--force", dir], { cwd: REPO });
		removeTree(dir); // undoes chmod locks a fix/gate run left; never throws
	}
	spawnSync("git", ["worktree", "prune"], { cwd: REPO });
}

let graderHead: string | undefined;
/**
 * The grader must be committed code that does not move during a tick: refuse to grade
 * with uncommitted changes under evals/, or if the grader's HEAD changed since the tick
 * began (e.g. something committed inside the runner).
 */
function assertCleanGrader(): void {
	const root = path.resolve(TRUSTED_EVAL_DIR, "../..");
	const dirty = spawnSync("git", ["status", "--porcelain", "--", "evals/"], { cwd: root, encoding: "utf8" });
	if (dirty.status !== 0) throw new Error("grader is not a git checkout");
	if (dirty.stdout.trim()) throw new Error("grader has uncommitted changes under evals/ — run the loop from its clean runner (loop.ts install)");
	const head = spawnSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).stdout.trim();
	graderHead ??= head;
	if (head !== graderHead) throw new Error("grader HEAD moved during the tick — refusing to grade");
	// Content check, not status: skip-worktree / assume-unchanged hide edits from `git status`.
	const tree = spawnSync("git", ["ls-tree", "-r", "-z", "HEAD", "--", "evals/"], { cwd: root, encoding: "utf8" }).stdout.split("\0").filter(Boolean);
	const expected = new Map(tree.map((line) => { const [meta, file] = line.split("\t"); return [file!, meta!.split(" ")[2]!]; }));
	const files = [...expected.keys()];
	const actual = spawnSync("git", ["hash-object", "--stdin-paths"], { cwd: root, encoding: "utf8", input: files.join("\n") }).stdout.trim().split("\n");
	const changed = files.filter((file, i) => actual[i] !== expected.get(file));
	const extra = spawnSync("git", ["ls-files", "--others", "-z", "--", "evals/"], { cwd: root, encoding: "utf8" }).stdout.split("\0").filter((f) => f && !f.includes("__pycache__"));
	if (changed.length || extra.length) throw new Error(`grader files differ from the committed grader (${[...changed, ...extra].slice(0, 5).join(", ")}) — refusing to grade`);
}

function groupFile(name: string): string {
	const group = JSON.parse(fs.readFileSync(GROUPS_INDEX, "utf8")).find((candidate: { name: string }) => candidate.name === name);
	if (!group) throw new Error(`no saved model group named ${name}`);
	return group.file;
}

function toRecord(raw: any): EvalRecord {
	return {
		group: raw.group, task: raw.task, suiteHash: raw.suiteHash, passRate: raw.passRate, harnessOk: raw.harnessOk,
		maxWriters: raw.maxWriters, costUsd: raw.costUsd, hidden: raw.hidden, executionFailure: raw.executionFailure,
		evidence: [raw.executionFailure, raw.harnessFacts, raw.hiddenOutput, raw.startupLog].filter(Boolean).join("\n").replace(/\x1b\[[0-9;]*m/g, "").slice(-4000),
	};
}

/** owner/repo for a GitHub remote; undefined for a plain git remote (e.g. a sandbox bare repo). */
function repoSlug(): string | undefined {
	const url = git(["remote", "get-url", config().remote]);
	return url.match(/github\.com[:/]([^/]+\/[^/.]+?)(?:\.git)?$/)?.[1];
}

/**
 * Single-instance lock. Creation is O_EXCL. A dead holder's lock may only be
 * removed by the one process holding the RECLAIM token (itself O_EXCL), and only
 * after re-reading the lock while holding the token: while the token is held and
 * the lock exists, nobody else can remove or recreate it, so the dead pid we
 * re-read is exactly what we remove. Everyone else backs off as busy.
 */
export function acquireLock(file: string): (() => void) | undefined {
	const token = `${file}.reclaim`;
	// Publish with the pid ALREADY inside: write a private temp file, then link() it into place
	// (link fails with EEXIST if the target exists). The lock is never visible empty — an empty
	// lock read as "pid 0 → dead" is exactly the race that let two holders in under load.
	const create = (target: string) => {
		const temp = `${target}.${process.pid}.${Math.random().toString(36).slice(2)}`;
		fs.writeFileSync(temp, String(process.pid));
		try { fs.linkSync(temp, target); } finally { fs.rmSync(temp, { force: true }); }
	};
	const alive = (pid: number) => {
		if (!Number.isInteger(pid) || pid <= 0) return false;
		try { process.kill(pid, 0); return true; } catch (error: any) { return error?.code === "EPERM"; }
	};
	// undefined = no lock; NaN = unreadable (treated as busy, never as dead).
	const holderOf = (target: string) => { try { const text = fs.readFileSync(target, "utf8").trim(); return text ? Number(text) : NaN; } catch { return undefined; } };
	for (let attempt = 0; attempt < 3; attempt++) {
		try {
			create(file);
			return () => { if (holderOf(file) === process.pid) fs.rmSync(file, { force: true }); };
		} catch (error: any) {
			if (error?.code !== "EEXIST") throw error;
		}
		const holder = holderOf(file);
		if (holder === undefined) continue; // vanished: retry create
		if (Number.isNaN(holder) || alive(holder)) return undefined;
		try {
			create(token);
		} catch {
			// Someone else is reclaiming. A token left by a dead reclaimer is cleared for the next tick.
			const reclaimer = holderOf(token);
			if (reclaimer !== undefined && !Number.isNaN(reclaimer) && !alive(reclaimer)) fs.rmSync(token, { force: true });
			return undefined;
		}
		try {
			const current = holderOf(file);
			if (current !== undefined && (Number.isNaN(current) || alive(current))) return undefined;
			if (current !== undefined) fs.rmSync(file, { force: true });
		} finally {
			fs.rmSync(token, { force: true });
		}
	}
	return undefined;
}

export function realDeps(cfg: FullConfig): LoopDeps {
	fs.mkdirSync(LOOP_DIR, { recursive: true });
	return {
		now: () => Date.now(),
		lock: () => acquireLock(LOCK),
		readState: () => (fs.existsSync(STATE) ? { ...emptyState(), ...JSON.parse(fs.readFileSync(STATE, "utf8")) } : emptyState()),
		writeState(state: LoopState) {
			const tmp = `${STATE}.${process.pid}.tmp`;
			fs.writeFileSync(tmp, `${JSON.stringify(state, null, 2)}\n`);
			fs.renameSync(tmp, STATE);
		},
		suiteHash: () => {
			assertCleanGrader();
			return JSON.parse(fs.readFileSync(path.join(TRUSTED_EVAL_DIR, "lock.json"), "utf8")).suiteHash;
		},
		async head() {
			git(["fetch", "--quiet", cfg.remote, cfg.branch]);
			return git(["rev-parse", `${cfg.remote}/${cfg.branch}`]);
		},
		async evaluate(commit, groups, tasks) {
			assertCleanGrader();
			const wt = worktree(commit, `eval-${Date.now()}`);
			// The trusted runner runs from an empty neutral directory: no candidate bunfig.toml or .env is in reach.
			const neutral = path.join(LOOP_DIR, "neutral");
			fs.mkdirSync(neutral, { recursive: true });
			const label = `loop-${commit.slice(0, 8)}-${Date.now()}`;
			// Graded by the loop's own runner + sealed tasks; the candidate only supplies the harness.
			// Sequential, not parallel: no concurrent run exists for one run's leftovers to tamper with.
			const runs: Array<{ code: number | null; out: string }> = [];
			for (const group of groups) runs.push(await run("bun", [path.join(TRUSTED_EVAL_DIR, "run.ts"), "run", "--label", label, "--groups", group, "--harness", wt, ...(tasks ? ["--tasks", tasks.join(",")] : [])], { cwd: neutral, env: { FH_EVAL_RESULTS_DIR: RESULTS }, timeoutMs: 6 * 3600_000, logFile: path.join(LOOP_DIR, `${label}-${group}.log`) }));
			const failed = runs.find((result) => result.code !== 0);
			if (failed) throw new Error(`eval run failed: ${failed.out.trim().slice(-800)}`);
			const records: EvalRecord[] = [];
			const root = path.join(RESULTS, label);
			for (const group of fs.existsSync(root) ? fs.readdirSync(root) : []) {
				for (const file of fs.readdirSync(path.join(root, group))) records.push(toRecord(JSON.parse(fs.readFileSync(path.join(root, group, file), "utf8"))));
			}
			return records;
		},
		async diffSince(from, to) {
			if (!from) return "(no accepted commit yet)";
			const stat = git(["diff", "--stat", `${from}..${to}`]);
			const body = git(["diff", `${from}..${to}`, "--", "extensions/"]);
			return `${stat}\n\n${body.slice(0, 20_000)}${body.length > 20_000 ? "\n…(diff truncated)" : ""}`;
		},
		async proposeFix({ base, fixer, regressions, evidence }) {
			const branch = `eval-loop/fix-${base.slice(0, 8)}-${Date.now()}`;
			const dir = path.join(LOOP_DIR, "fix", branch.replace(/\//g, "_"));
			git(["worktree", "add", "-b", branch, dir, base]);
			created.push(dir);
			linkDependencies(dir);
			// Recorded BEFORE the fix runs; every later git call on this worktree uses it, never the (writable) .git file.
			const gitDir = git(["rev-parse", "--absolute-git-dir"], dir);
			const dotGit = fs.readFileSync(path.join(dir, ".git"), "utf8");
			const evidenceFile = path.join(LOOP_DIR, `${branch.replace(/\//g, "_")}.evidence.md`);
			fs.writeFileSync(evidenceFile, evidence);
			const prompt = [
				"Fix a regression in this repository (the fusion-harness itself), found by the locked fusion eval.",
				`Evidence (confirmed by a re-run, with the diff since the last good commit): ${evidenceFile}`,
				`Regressions: ${regressions.map((r) => `${r.key} [${r.kind}] ${r.detail}`).join("; ")}.`,
				"Make the smallest change under extensions/fusion-harness that fixes the cause, add or update a test that fails without the fix, and run `bun test` until it passes.",
				"Change ONLY files under extensions/. Any change anywhere else (evals/, bunfig.toml, .env, package.json, …) rejects the whole attempt — changing the grader or the build is not a fix. Do not commit, push, merge, or publish; the loop commits and its gate decides.",
			].join(" ");
			// The FIXER harness is the last accepted commit (found by the real e2e: the broken harness,
			// fixing itself, skipped its own final integration and only got halfway). It edits `dir`.
			const fixerHarness = fixer ? worktree(fixer, `fixer-${Date.now()}`) : dir;
			const profile = path.join(profileDir(), `${branch.replace(/\//g, "_")}.fix.sb`);
			const runRoot = privateRunRoot("fix");
			fs.writeFileSync(profile, fixSandboxProfile(dir, LOOP_DIR, [fixerHarness], runRoot.root));
			const agentDir = prepareAgentDir(4 * 3600_000 + 10 * 60_000, runRoot.root);
			const piArgs = ["pi", "--no-extensions", "--no-session", "-e", path.join(fixerHarness, "extensions/fusion-harness/fusion-harness.ts"), "--fh-config", groupFile(cfg.fixGroup), "-p", `/fh-collaborate ${prompt}`];
			if (process.platform === "darwin" && !fs.existsSync("/usr/bin/sandbox-exec")) throw new Error("sandbox-exec is missing — refusing an unsandboxed fix run on macOS");
			const [cmd, ...args] = sizeLimited(process.platform === "darwin" ? ["/usr/bin/sandbox-exec", "-f", profile, ...piArgs] : piArgs);
			// FH_IN_SANDBOX: tests that need their own sandbox skip inside this one (macOS forbids nesting); the gate runs them in full.
			const result = await run(cmd!, args, { cwd: dir, env: { FH_IN_SANDBOX: "1", PI_CODING_AGENT_DIR: agentDir.dir, ...runRoot.env }, timeoutMs: 4 * 3600_000, logFile: path.join(LOOP_DIR, `${branch.replace(/\//g, "_")}.fix.log`), killGroup: true }).finally(() => { agentDir.cleanup(); removeTree(runRoot.root); });
			if (fs.readFileSync(path.join(dir, ".git"), "utf8") !== dotGit) throw new Error("fix run rewrote the worktree's .git pointer — rejected");
			// Checked against the base, not the working tree: commits the agent made itself count too.
			const forbidden = protectedChanges(dir, base, gitDir);
			if (forbidden.length) throw new Error(`fix run changed protected paths (${forbidden.join(", ")}) — rejected (pi exit ${result.code})`);
			const head = commitFixChanges(dir, base, `eval-loop: fix ${regressions.map((r) => `${r.key} ${r.kind}`).join(", ")}\n\nProposed by the fusion eval loop from confirmed regressions; see the PR for evidence and the gate result.`, gitDir);
			return head ? { branch, commit: head } : undefined;
		},
		async runTests(commit) {
			const wt = worktree(commit, `tests-${Date.now()}`);
			// The gate runs the (fix-written) tests in the fix sandbox too: FH_IN_SANDBOX skips only the
			// sandbox-proof tests, which test evals/ — a path no fix may change.
			const profile = path.join(profileDir(), `tests-${commit.slice(0, 12)}-${Date.now()}.sb`);
			const runRoot = privateRunRoot("gate");
			fs.writeFileSync(profile, fixSandboxProfile(wt, LOOP_DIR, [], runRoot.root));
			const [cmd, ...args] = sizeLimited(process.platform === "darwin" ? ["/usr/bin/sandbox-exec", "-f", profile, "bun", "test"] : ["bun", "test"]);
			const result = await run(cmd!, args, { cwd: wt, env: { FH_IN_SANDBOX: "1", ...runRoot.env }, timeoutMs: 30 * 60_000, killGroup: true }).finally(() => removeTree(runRoot.root));
			fs.rmSync(profile, { force: true });
			const clean = result.out.replace(/\x1b\[[0-9;]*m/g, "");
			const count = (label: string) => Number(clean.match(new RegExp(`^\\s*(\\d+) ${label}$`, "m"))?.[1] ?? 0);
			const passed = count("pass");
			const failed = count("fail");
			return { ok: result.code === 0 && failed === 0 && passed > 0, summary: `${passed} pass, ${failed} fail`, total: passed + failed };
		},
		async publish(fix: FixProposal, { title, body, merge }) {
			git(["push", "--quiet", cfg.remote, `${fix.commit}:refs/heads/${fix.branch}`]);
			const bodyFile = path.join(LOOP_DIR, `${fix.branch.replace(/\//g, "_")}.pr.md`);
			fs.writeFileSync(bodyFile, `${body}\n\n🤖 Opened by the fusion eval loop (evals/fusion-eval/loop.ts).`);
			const slug = repoSlug();
			if (!slug) {
				// Plain git remote: "merge" is a fast-forward push of the gated commit onto the branch.
				if (!merge) return { pr: `branch ${fix.branch} on ${cfg.remote}`, merged: false };
				const pushed = spawnSync("git", ["push", "--quiet", cfg.remote, `${fix.commit}:refs/heads/${cfg.branch}`], { cwd: REPO, encoding: "utf8" });
				return { pr: `${cfg.remote}/${cfg.branch} fast-forward`, merged: pushed.status === 0 };
			}
			const created = spawnSync("gh", ["pr", "create", "--repo", slug, "--base", cfg.branch, "--head", fix.branch, "--title", title, "--body-file", bodyFile], { encoding: "utf8" });
			const pr = (created.stdout || "").trim().split("\n").pop();
			if (created.status !== 0) throw new Error(`gh pr create failed: ${created.stderr.trim().slice(0, 400)}`);
			if (!merge) return { pr, merged: false };
			// Merge exactly the gated commit: gh refuses if the PR head moved.
			spawnSync("gh", ["pr", "merge", fix.branch, "--repo", slug, "--merge", "--match-head-commit", fix.commit], { encoding: "utf8" });
			const state = spawnSync("gh", ["pr", "view", fix.branch, "--repo", slug, "--json", "state", "-q", ".state"], { encoding: "utf8" }).stdout.trim();
			return { pr, merged: state === "MERGED" };
		},
		log(line, opts) {
			const stamped = `${new Date().toISOString()} ${line}`;
			fs.appendFileSync(LOG, `${stamped}\n`);
			console.log(stamped);
			if (opts?.rot && VAULT && fs.existsSync(path.join(VAULT, "ROT.md"))) {
				fs.appendFileSync(path.join(VAULT, "ROT.md"), `- ${new Date().toISOString().slice(0, 10)} — fusion eval loop: ${vaultSafe(line)} (log: ${LOG})\n`);
				spawnSync("python3", ["scripts/llmwiki_sync.py"], { cwd: VAULT, timeout: 120_000 });
			}
		},
	};
}

const RUNNER = path.join(LOOP_DIR, "runner");

/** The loop's own clean copy of the watched branch: its grader is committed code, never the shared checkout's WIP. */
function ensureRunner(cfg: FullConfig): string {
	git(["fetch", "--quiet", cfg.remote, cfg.branch]);
	if (!fs.existsSync(path.join(RUNNER, ".git"))) {
		fs.rmSync(RUNNER, { recursive: true, force: true });
		git(["worktree", "add", "--detach", "--force", RUNNER, `${cfg.remote}/${cfg.branch}`]);
	}
	return RUNNER;
}

/** After a tick, move the runner to the latest watched commit (fixes cannot touch evals/, so only humans change the grader). */
function refreshRunner(cfg: FullConfig): void {
	if (!path.resolve(TRUSTED_EVAL_DIR).startsWith(path.resolve(RUNNER) + path.sep)) return; // not running from the runner
	spawnSync("git", ["-C", RUNNER, "checkout", "--quiet", "--detach", "--force", `${cfg.remote}/${cfg.branch}`], { encoding: "utf8" });
}

function plist(): string {
	const bin = [path.join(HOME, ".bun/bin"), path.join(HOME, ".local/bin"), "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"].join(":");
	return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.evanmotovich.fusion-eval-loop</string>
  <key>ProgramArguments</key><array>
    <string>${path.join(HOME, ".bun/bin/bun")}</string>
    <string>${path.join(RUNNER, "evals/fusion-eval/loop.ts")}</string>
    <string>tick</string>
  </array>
  <key>WorkingDirectory</key><string>${LOOP_DIR}</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>${bin}</string><key>HOME</key><string>${HOME}</string><key>FH_LOOP_REPO</key><string>${REPO}</string><key>FH_LOOP_DIR</key><string>${LOOP_DIR}</string></dict>
  <key>StartInterval</key><integer>1800</integer>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>${path.join(LOOP_DIR, "launchd.out.log")}</string>
  <key>StandardErrorPath</key><string>${path.join(LOOP_DIR, "launchd.err.log")}</string>
</dict></plist>
`;
}

async function main() {
	const [cmd = "status", ...rest] = process.argv.slice(2);
	const cfg = config();
	const deps = realDeps(cfg);
	if (cmd === "tick") {
		const result = await tick({ ...deps, afterTick: () => { cleanupWorktrees(); refreshRunner(cfg); } }, cfg);
		if (result.outcome === "busy" || result.outcome === "idle") console.log(`${result.outcome}: ${result.detail}`);
	} else if (cmd === "status") {
		const state = deps.readState();
		console.log(JSON.stringify({ config: cfg, suite: state.suiteHash?.slice(0, 12), acceptedCommit: state.acceptedCommit, lastEvaluatedCommit: state.lastEvaluatedCommit, lastNightlyAt: state.lastNightlyAt && new Date(state.lastNightlyAt).toISOString(), inFlight: state.inFlight, attempted: state.attempted, bar: Object.fromEntries(Object.entries(state.accepted).map(([key, r]) => [key, `${r.hidden.passed}/${r.hidden.total} ${r.harnessOk ? "ok" : "FAIL"} $${r.costUsd.toFixed(2)}`])), recent: state.history.slice(-8) }, null, 2));
	} else if (cmd === "seed") {
		const from = rest[rest.indexOf("--from") + 1];
		if (!from || !fs.existsSync(from)) throw new Error("usage: seed --from <results/label dir>");
		const state = deps.readState();
		let commit = "";
		for (const group of fs.readdirSync(from)) for (const file of fs.readdirSync(path.join(from, group))) {
			const raw = JSON.parse(fs.readFileSync(path.join(from, group, file), "utf8"));
			const record = toRecord(raw);
			state.accepted[`${record.group}/${record.task}`] = record;
			state.suiteHash = record.suiteHash;
			commit = git(["rev-parse", raw.harnessCommit]);
		}
		state.acceptedCommit = commit;
		state.lastEvaluatedCommit = commit;
		state.lastNightlyAt = Date.now();
		deps.writeState(state);
		console.log(`seeded ${Object.keys(state.accepted).length} results as the bar at ${commit.slice(0, 8)}`);
	} else if (cmd === "install") {
		ensureRunner(cfg);
		fs.mkdirSync(path.dirname(PLIST), { recursive: true });
		fs.writeFileSync(PLIST, plist());
		spawnSync("launchctl", ["unload", PLIST]);
		const loaded = spawnSync("launchctl", ["load", "-w", PLIST], { encoding: "utf8" });
		console.log(loaded.status === 0 ? `installed: ticks every 30 min from the clean runner ${RUNNER} (${PLIST})` : `launchctl load failed: ${loaded.stderr}`);
	} else if (cmd === "uninstall") {
		spawnSync("launchctl", ["unload", "-w", PLIST]);
		fs.rmSync(PLIST, { force: true });
		console.log("uninstalled");
	} else {
		console.log(fs.readFileSync(new URL(import.meta.url).pathname, "utf8").split("*/")[0]);
	}
}

if (import.meta.main) main().catch((error) => { console.error(error instanceof Error ? error.message : error); process.exit(1); });
