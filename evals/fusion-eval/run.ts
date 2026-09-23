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
 * Grade in a FRESH directory: only the solution's top-level modules are copied in
 * (never its tests, conftest.py, or pytest config), next to the hidden tests.
 * `--noconftest`, `-c /dev/null` and a whitelisted environment keep planted files out.
 *
 * The solution itself runs inside pytest when the tests import it, so the grade is
 * cross-checked from three signals it would have to forge together:
 *   - the JUnit report, written OUTSIDE the grading dir under a random name;
 *   - a random canary test that MUST fail (blanket "force pass" tricks flip it);
 *   - pytest's exit code and its final summary line, which must agree with the report.
 * Any inconsistency grades 0.
 */
export function pytest(dir: string, testDir: string): { total: number; passed: number; failed: number; output: string } {
	const grade = fs.mkdtempSync(path.join(os.tmpdir(), "fh-eval-grade-"));
	const reportDir = fs.mkdtempSync(path.join(os.tmpdir(), "fh-eval-report-"));
	fs.chmodSync(reportDir, 0o700);
	const nonce = randomUUID().replace(/-/g, "");
	for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
		if (entry.isFile() && entry.name.endsWith(".py") && !entry.name.startsWith("test_") && entry.name !== "conftest.py") fs.copyFileSync(path.join(dir, entry.name), path.join(grade, entry.name));
	}
	fs.cpSync(path.join(dir, testDir), path.join(grade, testDir), { recursive: true });
	const canary = `test_zz_canary_${nonce}`;
	fs.writeFileSync(path.join(grade, testDir, `${canary}.py`), `def ${canary}():\n    assert False, "grader canary: must fail"\n`);
	const junit = path.join(reportDir, `${nonce}.xml`);
	const env: Record<string, string> = { PYTHONPATH: grade, PYTHONDONTWRITEBYTECODE: "1" };
	for (const key of ["PATH", "HOME", "USER", "LANG", "TMPDIR"]) if (process.env[key]) env[key] = process.env[key]!;
	const result = spawnSync("uv", ["run", "--quiet", "--no-project", "--with", "pytest", "python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--noconftest", "-c", "/dev/null", "--rootdir", grade, testDir, `--junitxml=${junit}`], { cwd: grade, encoding: "utf8", timeout: 180_000, env });
	const output = `${result.stdout ?? ""}${result.stderr ?? ""}`.slice(-4000);
	const zero = (why: string) => ({ total: Math.max(0, reportedTotal), passed: 0, failed: Math.max(0, reportedTotal), output: `GRADER INTEGRITY: ${why}\n${output}` });
	let reportedTotal = 0;
	try {
		const xml = fs.readFileSync(junit, "utf8");
		const suite = xml.match(/<testsuite\b[^>]*>/)?.[0] ?? "";
		const num = (name: string) => Number(suite.match(new RegExp(`\\b${name}="(\\d+)"`))?.[1] ?? 0);
		const total = num("tests") - num("skipped");
		const failed = num("failures") + num("errors");
		reportedTotal = total - 1;
		// 1) the canary is in the report and failed
		const canaryCase = xml.match(new RegExp(`<testcase\\b[^>]*name="${canary}"[^>]*>([\\s\\S]*?)</testcase>`));
		if (!canaryCase || !/<(failure|error)\b/.test(canaryCase[1] ?? "")) return zero("canary test missing or not failed");
		// 2) exit code agrees (1 = some tests failed; the canary always does)
		if (result.status !== 1) return zero(`pytest exit code ${result.status} disagrees with the report`);
		// 3) the summary line agrees with the report
		const summary = output.replace(/\x1b\[[0-9;]*m/g, "");
		const count = (label: string) => Number(summary.match(new RegExp(`(\\d+) ${label}`))?.[1] ?? 0);
		if (count("failed") + count("error") + count("errors") !== failed || count("passed") !== total - failed) return zero("pytest summary disagrees with the report");
		return { total: total - 1, passed: total - failed, failed: failed - 1, output };
	} catch {
		return { total: 0, passed: 0, failed: 0, output }; /* no report: collection failed — scores 0 */
	} finally {
		fs.rmSync(grade, { recursive: true, force: true });
		fs.rmSync(reportDir, { recursive: true, force: true });
	}
}

function selfTest(): boolean {
	let ok = true;
	for (const id of taskIds()) {
		const scratch = fs.mkdtempSync(path.join(os.tmpdir(), `fh-eval-self-${id}-`));
		for (const file of fs.readdirSync(path.join(TASKS_DIR, id, "reference"))) fs.copyFileSync(path.join(TASKS_DIR, id, "reference", file), path.join(scratch, file));
		fs.cpSync(path.join(TASKS_DIR, id, "hidden"), path.join(scratch, "_hidden_eval"), { recursive: true });
		const result = pytest(scratch, "_hidden_eval");
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
		const child = spawn("pi", ["--no-extensions", "-e", path.join(harness, "extensions/fusion-harness/fusion-harness.ts"), "--fh-config", group.file, "-p", `/fh-collaborate ${prompt}`], { cwd: scratch, stdio: ["ignore", fs.openSync(logPath, "w"), fs.openSync(logPath, "a")] });
		const timer = setTimeout(() => child.kill("SIGTERM"), RUN_TIMEOUT_MS);
		child.on("exit", (code) => { clearTimeout(timer); resolve(code); });
		child.on("error", () => { clearTimeout(timer); resolve(-1); });
	});
	const wallMs = Date.now() - startedAt;
	const artifacts = findArtifacts(token, startedAt);
	const summary = artifacts ? readJson(path.join(artifacts, "summary.json")) : undefined;
	const states: Record<string, string> = summary?.taskStates ?? {};
	fs.cpSync(path.join(TASKS_DIR, task, "hidden"), path.join(scratch, "_hidden_eval"), { recursive: true });
	const hidden = pytest(scratch, "_hidden_eval");
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
