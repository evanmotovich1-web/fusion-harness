#!/usr/bin/env bun
/**
 * fusion eval — a locked, real-model regression eval for /fh-collaborate.
 *
 * Each task is a small build with an exact API contract. Models see only
 * tasks/<id>/prompt.md; they never see tasks/<id>/hidden/ (the grader) or
 * reference/ (a known-good solution the grader is proven against).
 *
 *   bun evals/fusion-eval/run.ts self-test          references must pass 100% of hidden tests
 *   bun evals/fusion-eval/run.ts lock               seal every task file (sha256) into lock.json
 *   bun evals/fusion-eval/run.ts run --label <name> --groups a,b [--harness <dir>] [--tasks ids]
 *   bun evals/fusion-eval/run.ts report [--baseline baseline --current current]
 *
 * `run` refuses if any task file differs from lock.json, so every result is
 * scored against the same sealed suite; results record the suite hash and the
 * harness commit. Runs are paid (real models); everything else is free.
 */
import { spawn, spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const EVAL_DIR = path.dirname(new URL(import.meta.url).pathname);
const TASKS_DIR = path.join(EVAL_DIR, "tasks");
const LOCK_PATH = path.join(EVAL_DIR, "lock.json");
const RESULTS_DIR = process.env.FH_EVAL_RESULTS_DIR || path.join(EVAL_DIR, "results");
const GROUPS_INDEX = process.env.FH_GROUPS_DIR ? path.join(process.env.FH_GROUPS_DIR, "groups.json") : path.join(os.homedir(), ".pi", "fusion-harness", "groups", "groups.json");
const RUN_TIMEOUT_MS = Number(process.env.FH_EVAL_RUN_TIMEOUT_MS || 90 * 60_000);

type Args = Record<string, string | boolean>;
function parseArgs(argv: string[]): { cmd: string; args: Args } {
	const [cmd = "help", ...rest] = argv;
	const args: Args = {};
	for (let i = 0; i < rest.length; i++) {
		const key = rest[i]!;
		if (!key.startsWith("--")) continue;
		const next = rest[i + 1];
		if (next && !next.startsWith("--")) { args[key.slice(2)] = next; i++; } else args[key.slice(2)] = true;
	}
	return { cmd, args };
}

export function taskIds(): string[] {
	return fs.readdirSync(TASKS_DIR).filter((name) => fs.existsSync(path.join(TASKS_DIR, name, "prompt.md"))).sort();
}

function walk(dir: string): string[] {
	return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
		if (entry.name === "__pycache__" || entry.name.startsWith(".")) return [];
		const full = path.join(dir, entry.name);
		return entry.isDirectory() ? walk(full) : [full];
	});
}

function sha256(data: string | Buffer): string {
	return createHash("sha256").update(data).digest("hex");
}

function currentLock(): { files: Record<string, string>; suiteHash: string } {
	const files: Record<string, string> = {};
	for (const file of walk(TASKS_DIR).sort()) files[path.relative(EVAL_DIR, file)] = sha256(fs.readFileSync(file));
	return { files, suiteHash: sha256(JSON.stringify(files)) };
}

/** Throws unless every task file matches lock.json exactly. */
export function verifyLock(): string {
	if (!fs.existsSync(LOCK_PATH)) throw new Error("no lock.json — run `lock` first");
	const locked = JSON.parse(fs.readFileSync(LOCK_PATH, "utf8"));
	const now = currentLock();
	const changed = [...new Set([...Object.keys(locked.files), ...Object.keys(now.files)])].filter((file) => locked.files[file] !== now.files[file]);
	if (changed.length) throw new Error(`suite is LOCKED and these files changed since lock.json:\n  ${changed.join("\n  ")}\nRe-lock deliberately (new suite version) — results against different suites are not comparable.`);
	return locked.suiteHash;
}

/**
 * Grade with the solution OUTSIDE the grading process.
 *
 * The pytest process that runs the hidden tests never imports the solution: every
 * test calls it through tasks/_isolated.py, which runs each call in a fresh child
 * interpreter and asserts on the returned data here, in the trusted parent. So no
 * in-process trick (patching pytest, writing reports, exiting early) can change a
 * result — the solution can only influence what it returns.
 *
 * On macOS each child also runs under sandbox-exec with DENY-BY-DEFAULT file access:
 * it may read only the OS, the Python installation, its own solution folder and its
 * own private temp folder, and may write only that temp folder. So no copy of the
 * answers is reachable — not the hidden tests, not the reference solutions, not the
 * git object store (Enemy pass 5 read references via `git show`), not the loop's
 * results, not other runs' folders — and there is no network.
 */
export function pytest(dir: string, testDir: string): { total: number; passed: number; failed: number; output: string } {
	if (process.platform === "darwin" && !fs.existsSync("/usr/bin/sandbox-exec")) throw new Error("sandbox-exec is missing — refusing to grade unsandboxed on macOS");
	const cache = path.join(os.homedir(), ".cache", "fh-eval-grading");
	fs.mkdirSync(cache, { recursive: true });
	const root = fs.mkdtempSync(path.join(cache, "grade-"));
	const solution = path.join(root, "solution");
	const hidden = path.join(root, "_hidden_eval");
	fs.mkdirSync(solution);
	for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
		if (entry.isFile() && entry.name.endsWith(".py") && !entry.name.startsWith("test_") && entry.name !== "conftest.py") fs.copyFileSync(path.join(dir, entry.name), path.join(solution, entry.name));
	}
	fs.cpSync(path.isAbsolute(testDir) ? testDir : path.join(dir, testDir), hidden, { recursive: true });
	fs.copyFileSync(path.join(TASKS_DIR, "_isolated.py"), path.join(hidden, "_isolated.py"));
	const childTmp = path.join(root, "tmp");
	fs.mkdirSync(childTmp);
	const real = (p: string) => fs.realpathSync(p);
	const home = os.homedir();
	const readable = ["/usr", "/System", "/Library/Frameworks", "/private/var/db/timezone", "/private/etc", "/dev", path.join(home, ".local/share/uv"), path.join(home, ".cache/uv"), real(solution), real(childTmp)];
	const profile = path.join(root, "child.sb");
	fs.writeFileSync(profile, [
		"(version 1)",
		"(allow default)",
		"(deny network*)",
		"(deny file-write*)",
		`(allow file-write* (subpath ${JSON.stringify(real(childTmp))}) (literal "/dev/null"))`,
		"(deny file-read*)",
		`(allow file-read* (literal "/") ${readable.map((p) => `(subpath ${JSON.stringify(p)})`).join(" ")})`,
		"(allow file-read-metadata)",
		"",
	].join("\n"));
	const junit = path.join(root, `report-${randomUUID()}.xml`);
	const env: Record<string, string> = { FH_EVAL_SOLUTION_DIR: solution, FH_EVAL_SANDBOX_PROFILE: profile, FH_EVAL_CHILD_TMP: childTmp, PYTHONDONTWRITEBYTECODE: "1" };
	for (const key of ["PATH", "HOME", "USER", "LANG", "TMPDIR"]) if (process.env[key]) env[key] = process.env[key]!;
	const result = spawnSync("uv", ["run", "--quiet", "--no-project", "--with", "pytest", "python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--noconftest", "-c", "/dev/null", "--rootdir", root, `--basetemp=${path.join(childTmp, "pytest")}`, "_hidden_eval", `--junitxml=${junit}`], { cwd: root, encoding: "utf8", timeout: 600_000, env });
	const output = `${result.stdout ?? ""}${result.stderr ?? ""}`.slice(-4000);
	try {
		const xml = fs.readFileSync(junit, "utf8");
		const suite = xml.match(/<testsuite\b[^>]*>/)?.[0] ?? "";
		const num = (name: string) => Number(suite.match(new RegExp(`\\b${name}="(\\d+)"`))?.[1] ?? 0);
		const total = num("tests") - num("skipped");
		const failed = num("failures") + num("errors");
		// The parent is trusted (it never runs solution code), but stay defensive: exit code must agree.
		if ((failed === 0) !== (result.status === 0)) return { total, passed: 0, failed: total, output: `GRADER: exit code ${result.status} disagrees with the report\n${output}` };
		return { total, passed: total - failed, failed, output };
	} catch {
		return { total: 0, passed: 0, failed: 0, output }; /* no report: collection failed — scores 0 */
	} finally {
		fs.rmSync(root, { recursive: true, force: true });
	}
}

function selfTest(): boolean {
	let ok = true;
	for (const id of taskIds()) {
		const scratch = fs.mkdtempSync(path.join(os.tmpdir(), `fh-eval-self-${id}-`));
		for (const file of fs.readdirSync(path.join(TASKS_DIR, id, "reference"))) fs.copyFileSync(path.join(TASKS_DIR, id, "reference", file), path.join(scratch, file));
		const result = pytest(scratch, path.join(TASKS_DIR, id, "hidden"));
		const pass = result.total > 0 && result.failed === 0;
		ok &&= pass;
		console.log(`${pass ? "PASS" : "FAIL"}  ${id}: reference ${result.passed}/${result.total}`);
		if (!pass) console.log(result.output);
		fs.rmSync(scratch, { recursive: true, force: true });
	}
	return ok;
}

export interface GroupEntry { name: string; file: string; signature: string; models: string[] }
export function loadGroup(name: string): GroupEntry {
	const groups: GroupEntry[] = JSON.parse(fs.readFileSync(GROUPS_INDEX, "utf8"));
	const group = groups.find((candidate) => candidate.name === name);
	if (!group) throw new Error(`no saved model group named ${name} (see: fusion groups)`);
	return group;
}

function findArtifacts(token: string, since: number): string | undefined {
	for (const entry of fs.readdirSync("/tmp")) {
		if (!entry.startsWith("fusion-harness-")) continue;
		const dir = path.join("/tmp", entry);
		try {
			if (fs.statSync(dir).mtimeMs < since - 60_000) continue;
			if (fs.readFileSync(path.join(dir, "prompt.md"), "utf8").includes(token)) return dir;
		} catch { /* not a run dir */ }
	}
	return undefined;
}

function readJson(file: string): any {
	try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch { return undefined; }
}

/**
 * Sandbox for the harness under test while it BUILDS the solution. The candidate harness
 * is arbitrary code; a "fix" could make it plant known answers or tamper with the grader.
 * Enemy passes 6-7 showed a deny-list always misses a path, so WRITES are deny-by-default:
 * only its own scratch, run artifacts (/tmp/fusion-harness-*), temp, and pi's own state
 * (~/.pi/agent). Nothing else — not git hooks, not the grader's Python/pytest, not
 * node_modules, not the loop. READS: everything pi needs, except the loop's folder, other
 * runs (/tmp/fh-eval-*), the grading cache, credentials (gh/ssh/git, and the keychain
 * service), and — even inside its own worktree — any sealed task or git object store
 * other than its own scratch repo's. Network stays on (the models need it).
 */
/**
 * Resolved path for sandbox rules (they match resolved paths; /tmp → /private/tmp). For a
 * path that does not exist yet, resolve its nearest existing ancestor so the rule still matches.
 */
export function real(p: string): string {
	try { return fs.realpathSync(p); } catch { /* not there yet */ }
	const parent = path.dirname(p);
	return parent === p ? p : path.join(real(parent), path.basename(p));
}

/**
 * READS under $HOME are deny-by-default (Enemy pass 10: every deny-list of secrets missed one —
 * ~/.codex/auth.json, ~/.hermes, ~/.claude.json, shell history, the keychain files). Readable:
 * the toolchain (pi, node, bun, uv + its Pythons), git's config, the model-group configs, pi's
 * downloaded tools, and each `extra` path (its symlinks resolved — a worktree's node_modules link).
 * Everything else under $HOME, including the real ~/.pi/agent, is unreadable.
 */
export function homeReadRules(extra: string[] = []): string {
	const home = os.homedir();
	const q = (p: string) => JSON.stringify(real(p));
	const trees = [".local/bin", ".local/lib", ".local/share/uv", ".cache/uv", ".bun", ".hermes/node", ".config/git", ".pi/fusion-harness", ".pi/agent/bin"].map((p) => path.join(home, p));
	// Model-stack configs are often symlinks (e.g. into ~/dotfiles): allow each link's own target, nothing beside it.
	const linked: string[] = [];
	for (const dir of [path.join(home, ".pi", "fusion-harness"), path.join(home, ".pi", "fusion-harness", "groups")]) {
		for (const entry of fs.existsSync(dir) ? fs.readdirSync(dir, { withFileTypes: true }) : []) if (entry.isSymbolicLink()) linked.push(real(path.join(dir, entry.name)));
	}
	return [
		`(deny file-read* (subpath ${q(home)}))`,
		`(allow file-read* (literal ${q(home)}) (literal ${q(path.join(home, ".gitconfig"))}) ${[...trees, ...extra].map((p) => `(subpath ${q(p)})`).join(" ")} ${linked.map((p) => `(literal ${JSON.stringify(p)})`).join(" ")})`,
		// Walking to an allowed path needs stat() on its parents; no contents are readable.
		"(allow file-read-metadata)",
		// ssh-agent and other per-user launchd sockets: no signing with keys the sandbox cannot read.
		'(deny network-outbound (remote unix-socket (path-regex #"^/private/tmp/com\\.apple\\.launchd\\.")))',
	].join("\n");
}

/** Secret files neither sandbox needs — kept as a second line behind homeReadRules. */
export function secretReadDenies(): string {
	const home = os.homedir();
	const q = (p: string) => JSON.stringify(real(path.join(home, p)));
	return [".config/gh", ".ssh", ".aws", ".docker", ".gnupg"].map((p) => `(subpath ${q(p)})`).join(" ") + " " + [".git-credentials", ".netrc", ".npmrc", ".pi/agent/mcp.json"].map((p) => `(literal ${q(p)})`).join(" ");
}

/** Where sandbox profiles are written: a 0700 dir neither sandbox may write (no TOCTOU on a profile). */
export function profileDir(): string {
	const dir = path.join(os.homedir(), ".cache", "fh-eval-profiles");
	fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
	fs.chmodSync(dir, 0o700); // mkdir's mode only applies on creation
	return dir;
}

/** Environment for a sandboxed pi: nothing from the caller's shell (session tokens, SSH_AUTH_SOCK, API keys). */
export function sandboxEnv(extra: Record<string, string> = {}): Record<string, string> {
	const env: Record<string, string> = {};
	for (const key of ["PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "TMPDIR", "TERM"]) if (process.env[key] !== undefined) env[key] = process.env[key]!;
	return { ...env, ...extra };
}

/**
 * A throwaway pi agent dir for ONE sandboxed run (Enemy pass 10). The sandbox never writes the
 * real ~/.pi/agent: a writable models-store.json there let a harness point every LATER pi session
 * at its own baseUrl (tokens + prompts + tool calls), and planted lock dirs hung every later pi.
 * The copy holds the model catalog, the model defaults, pi's tool binaries (read-only link), and
 * auth WITHOUT refresh tokens: the trusted parent first refreshes each OAuth token so it outlives
 * the run, so the sandbox can neither rotate (and break) the real login nor keep a refresh token.
 */
export function prepareAgentDir(minValidityMs: number): { dir: string; cleanup(): void } {
	const agent = path.join(os.homedir(), ".pi", "agent");
	const authFile = path.join(agent, "auth.json");
	const minutes = `${Math.ceil(minValidityMs / 60_000)}m`;
	for (const [provider, credential] of Object.entries<any>(readJson(authFile) ?? {})) {
		if (credential?.type !== "oauth") continue;
		// Trusted, unsandboxed: pi's own refresh path persists the rotated token in the real store.
		const opts = { stdio: ["ignore", "ignore", "ignore"] as const, env: sandboxEnv(), timeout: 60_000 };
		if (spawnSync("pi", ["auth", "print-bearer-token", "--provider", provider, "--min-expiry", minutes], opts).status !== 0) {
			spawnSync("pi", ["auth", "print-bearer-token", "--provider", provider], opts); // lifetime shorter than the run: at least fresh
		}
	}
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fh-pi-agent-"));
	const auth = Object.fromEntries(Object.entries<any>(readJson(authFile) ?? {}).map(([provider, credential]) => [provider, credential?.type === "oauth" ? { ...credential, refresh: "" } : credential]));
	fs.writeFileSync(path.join(dir, "auth.json"), JSON.stringify(auth, null, 2), { mode: 0o600 });
	if (fs.existsSync(path.join(agent, "models-store.json"))) fs.copyFileSync(path.join(agent, "models-store.json"), path.join(dir, "models-store.json"));
	// Model defaults only — never `packages` (code pi would load) or anything else.
	const settings = readJson(path.join(agent, "settings.json")) ?? {};
	const keep = Object.fromEntries(["defaultProvider", "defaultModel", "defaultThinkingLevel", "compaction", "lastChangelogVersion"].filter((k) => k in settings).map((k) => [k, settings[k]]));
	fs.writeFileSync(path.join(dir, "settings.json"), JSON.stringify(keep, null, 2));
	if (fs.existsSync(path.join(agent, "bin"))) fs.symlinkSync(path.join(agent, "bin"), path.join(dir, "bin"));
	return { dir, cleanup: () => fs.rmSync(dir, { recursive: true, force: true }) };
}

export function harnessSandboxProfile(scratch: string, harness: string): string {
	const home = os.homedir();
	const loopDir = real(process.env.FH_LOOP_DIR || path.join(home, ".pi", "fusion-harness", "eval-loop"));
	const own = JSON.stringify(real(scratch));
	const q = (p: string) => JSON.stringify(real(p));
	return [
		"(version 1)",
		"(allow default)",
		"(deny file-write*)",
		// No ~/.pi/agent at all: pi runs on a throwaway agent dir in temp (prepareAgentDir).
		`(allow file-write* (subpath ${own}) (regex #"^/private/tmp/fusion-harness-") (subpath "/private/var/folders") (subpath "/dev"))`,
		homeReadRules([path.join(harness, "node_modules")]),
		`(deny file-read* (subpath ${q(loopDir)}) (subpath ${q(RESULTS_DIR)}) (regex #"^/private/tmp/fh-eval-") (subpath ${q(path.join(home, ".cache", "fh-eval-grading"))}) (subpath ${q(path.join(home, ".cache", "fh-eval-profiles"))}) ${secretReadDenies()})`,
		`(allow file-read* (subpath ${q(harness)}) (subpath ${own}))`,
		'(deny file-read* (regex #"/evals/fusion-eval/tasks(/|$)") (regex #"/\\.git/objects(/|$)"))',
		// Later rules win: its own scratch repo (and that repo's .git) stays fully usable.
		`(allow file-read* (subpath ${own}))`,
		'(deny mach-lookup (global-name "com.apple.SecurityServer") (global-name "com.apple.securityd.xpc") (global-name "com.apple.security.agent"))',
		"",
	].join("\n");
}

/** On macOS the sandbox is mandatory: grading without it would silently trust the code under test. */
function sandboxCommand(profile: string, args: string[]): string[] {
	if (process.platform !== "darwin") return args;
	if (!fs.existsSync("/usr/bin/sandbox-exec")) throw new Error("sandbox-exec is missing — refusing to run unsandboxed on macOS");
	return ["/usr/bin/sandbox-exec", "-f", profile, ...args];
}

export async function runOne(opts: { harness: string; harnessCommit: string; label: string; group: GroupEntry; task: string; suiteHash: string }): Promise<Record<string, unknown>> {
	const { harness, group, task } = opts;
	const scratch = fs.mkdtempSync(path.join("/tmp", `fh-eval-${opts.label}-${group.name}-${task}-`));
	spawnSync("git", ["init", "-q", "-b", "main"], { cwd: scratch });
	fs.writeFileSync(path.join(scratch, "README.md"), `# ${task}\n`);
	spawnSync("git", ["add", "README.md"], { cwd: scratch });
	spawnSync("git", ["-c", "user.name=eval", "-c", "user.email=eval@local", "commit", "-qm", "init"], { cwd: scratch });
	const token = `fh-eval-${randomUUID()}`;
	const prompt = `${fs.readFileSync(path.join(TASKS_DIR, task, "prompt.md"), "utf8").trim()}\n\n(eval run ${token})`;
	const startedAt = Date.now();
	const logPath = path.join(scratch, ".fh-eval-pi.log");
	const exitCode = await new Promise<number | null>((resolve) => {
		const profile = path.join(profileDir(), `harness-${randomUUID()}.sb`);
		fs.writeFileSync(profile, harnessSandboxProfile(scratch, harness));
		const agentDir = prepareAgentDir(RUN_TIMEOUT_MS + 10 * 60_000);
		const [cmd, ...args] = sandboxCommand(profile, ["pi", "--no-extensions", "--no-session", "-e", path.join(harness, "extensions/fusion-harness/fusion-harness.ts"), "--fh-config", group.file, "-p", `/fh-collaborate ${prompt}`]);
		// Its own process group, killed when it ends: nothing the harness started outlives the run.
		const child = spawn(cmd!, args, { cwd: scratch, detached: true, env: sandboxEnv({ PI_CODING_AGENT_DIR: agentDir.dir }), stdio: ["ignore", fs.openSync(logPath, "w"), fs.openSync(logPath, "a")] });
		const killGroup = () => { try { process.kill(-child.pid!, "SIGKILL"); } catch { /* already gone */ } };
		const timer = setTimeout(killGroup, RUN_TIMEOUT_MS);
		const done = (code: number | null) => { clearTimeout(timer); killGroup(); fs.rmSync(profile, { force: true }); agentDir.cleanup(); resolve(code); };
		child.on("exit", (code) => done(code));
		child.on("error", () => done(-1));
	});
	const wallMs = Date.now() - startedAt;
	const artifacts = findArtifacts(token, startedAt);
	const summary = artifacts ? readJson(path.join(artifacts, "summary.json")) : undefined;
	const states: Record<string, string> = summary?.taskStates ?? {};
	// Hidden tests are read straight from the sealed suite — never copied next to the solution.
	const hidden = pytest(scratch, path.join(TASKS_DIR, task, "hidden"));
	const costUsd = (summary?.agents ?? []).reduce((sum: number, agent: any) => sum + (agent.costUsd ?? 0), 0);
	const record = {
		suiteHash: opts.suiteHash,
		label: opts.label,
		harness,
		harnessCommit: opts.harnessCommit,
		group: group.name,
		groupSignature: group.signature,
		task,
		token,
		scratch,
		artifacts: artifacts ?? null,
		piExitCode: exitCode,
		harnessOk: summary?.ok ?? false,
		executionFailure: summary?.executionFailure ?? (artifacts ? null : `no run artifacts — pi did not start the collaboration (see ${logPath})`),
		tasksFailed: Object.values(states).filter((state) => state === "failed" || state === "blocked").length,
		maxWriters: summary?.maxConcurrentWriteEnabledChildren ?? null,
		quotaWaits: artifacts ? (readJson(path.join(artifacts, "collaborate", "quota-waits.json")) ?? []).length : 0,
		benched: artifacts ? Object.keys(readJson(path.join(artifacts, "collaborate", "quota-benched.json")) ?? {}) : [],
		costUsd: Number(costUsd.toFixed(4)),
		wallMs,
		hidden: { total: hidden.total, passed: hidden.passed, failed: hidden.failed },
		passRate: hidden.total ? hidden.passed / hidden.total : 0,
		hiddenOutput: hidden.output.slice(-2000),
		// Why the harness judged the run the way it did: the run's own final facts and task states.
		harnessFacts: artifacts ? [`task states: ${JSON.stringify(states)}`, (() => { try { return fs.readFileSync(path.join(artifacts, "collaborate", "final.md"), "utf8").slice(0, 1500); } catch { return ""; } })()].filter(Boolean).join("\n") : undefined,
		startupLog: artifacts ? undefined : fs.readFileSync(logPath, "utf8").slice(-1500),
		finishedAt: new Date().toISOString(),
	};
	const out = path.join(RESULTS_DIR, opts.label, group.name);
	fs.mkdirSync(out, { recursive: true });
	fs.writeFileSync(path.join(out, `${task}.json`), `${JSON.stringify(record, null, 2)}\n`);
	// Nothing a later run could read is left behind: the solution and build folder go (the record keeps the scores).
	if (!process.env.FH_EVAL_KEEP_SCRATCH) fs.rmSync(scratch, { recursive: true, force: true });
	return record;
}

export function loadResults(label: string): Map<string, any> {
	const map = new Map<string, any>();
	const root = path.join(RESULTS_DIR, label);
	if (!fs.existsSync(root)) return map;
	for (const group of fs.readdirSync(root)) {
		for (const file of fs.readdirSync(path.join(root, group))) {
			const record = readJson(path.join(root, group, file));
			if (record) map.set(`${group}/${record.task}`, record);
		}
	}
	return map;
}

/** Markdown comparison + regression list. A regression is judged per group+task against the same suite. */
export function compare(baseline: Map<string, any>, current: Map<string, any>): { table: string; regressions: string[] } {
	const keys = [...new Set([...baseline.keys(), ...current.keys()])].sort();
	const cell = (r: any) => (r ? `${Math.round(r.passRate * 100)}% ${r.hidden.passed}/${r.hidden.total} · $${r.costUsd.toFixed(2)} · ${Math.round(r.wallMs / 60000)}m${r.harnessOk ? "" : " · harness FAIL"}` : "—");
	const rows = keys.map((key) => `| ${key} | ${cell(baseline.get(key))} | ${cell(current.get(key))} |`);
	const regressions: string[] = [];
	for (const key of keys) {
		const b = baseline.get(key), c = current.get(key);
		if (!c) continue;
		if (b && b.suiteHash !== c.suiteHash) { regressions.push(`${key}: different suite versions — not comparable`); continue; }
		if (c.maxWriters !== null && c.maxWriters > 1) regressions.push(`${key}: ${c.maxWriters} concurrent writers (must be 1)`);
		if (!b) continue;
		if (c.passRate < b.passRate) regressions.push(`${key}: hidden tests ${Math.round(b.passRate * 100)}% → ${Math.round(c.passRate * 100)}%`);
		if (b.harnessOk && !c.harnessOk) regressions.push(`${key}: harness run failed (baseline succeeded): ${c.executionFailure ?? "not ok"}`);
		if (b.costUsd > 0 && c.costUsd > b.costUsd * 1.5 && c.costUsd - b.costUsd > 0.5) regressions.push(`${key}: cost $${b.costUsd.toFixed(2)} → $${c.costUsd.toFixed(2)}`);
	}
	return { table: ["| group/task | baseline | current |", "|---|---|---|", ...rows].join("\n"), regressions };
}

async function main() {
	const { cmd, args } = parseArgs(process.argv.slice(2));
	if (cmd === "self-test") {
		process.exit(selfTest() ? 0 : 1);
	} else if (cmd === "lock") {
		if (!selfTest()) throw new Error("refusing to lock: a reference solution fails its hidden tests");
		const lock = { suite: "fusion-eval", lockedAt: new Date().toISOString(), ...currentLock() };
		fs.writeFileSync(LOCK_PATH, `${JSON.stringify(lock, null, 2)}\n`);
		console.log(`locked ${Object.keys(lock.files).length} files · suite ${lock.suiteHash.slice(0, 12)}`);
	} else if (cmd === "verify") {
		console.log(`lock OK · suite ${verifyLock().slice(0, 12)}`);
	} else if (cmd === "run") {
		const suiteHash = verifyLock();
		const label = String(args.label || "current");
		const harness = path.resolve(String(args.harness || path.resolve(EVAL_DIR, "../..")));
		const harnessCommit = spawnSync("git", ["-C", harness, "rev-parse", "--short", "HEAD"], { encoding: "utf8" }).stdout.trim();
		const groups = String(args.groups || "quad").split(",").map(loadGroup);
		const tasks = args.tasks ? String(args.tasks).split(",") : taskIds();
		console.log(`suite ${suiteHash.slice(0, 12)} · harness ${harnessCommit} (${label}) · groups ${groups.map((g) => g.name).join(",")} · tasks ${tasks.length}`);
		for (const group of groups) {
			for (const task of tasks) {
				const record = await runOne({ harness, harnessCommit, label, group, task, suiteHash });
				console.log(`${label} ${group.name} ${task}: hidden ${(record.hidden as any).passed}/${(record.hidden as any).total} · harness ${record.harnessOk ? "ok" : "FAIL"} · $${record.costUsd} · ${Math.round((record.wallMs as number) / 60000)}m${record.executionFailure ? ` · ${String(record.executionFailure).slice(0, 120)}` : ""}`);
			}
		}
	} else if (cmd === "report") {
		const { table, regressions } = compare(loadResults(String(args.baseline || "baseline")), loadResults(String(args.current || "current")));
		console.log(table);
		console.log(regressions.length ? `\nREGRESSIONS (${regressions.length}):\n- ${regressions.join("\n- ")}` : "\nNo regressions.");
		process.exit(regressions.length ? 1 : 0);
	} else {
		console.log(fs.readFileSync(new URL(import.meta.url).pathname, "utf8").split("*/")[0]);
	}
}

if (import.meta.main) main().catch((error) => { console.error(error instanceof Error ? error.message : error); process.exit(1); });
