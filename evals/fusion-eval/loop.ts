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
/** Files the fix run may never change: editing the grader is not a fix. */
const LOCKED_SUITE = /^evals\/fusion-eval\/(tasks\/|lock\.json$)/;

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

function run(cmd: string, args: string[], opts: { cwd: string; env?: Record<string, string>; timeoutMs: number; logFile?: string }): Promise<{ code: number | null; out: string }> {
	return new Promise((resolve) => {
		const chunks: Buffer[] = [];
		const child = spawn(cmd, args, { cwd: opts.cwd, env: { ...process.env, ...opts.env } });
		const sink = opts.logFile ? fs.createWriteStream(opts.logFile, { flags: "a" }) : undefined;
		child.stdout.on("data", (chunk) => { chunks.push(chunk); sink?.write(chunk); });
		child.stderr.on("data", (chunk) => { chunks.push(chunk); sink?.write(chunk); });
		const timer = setTimeout(() => child.kill("SIGTERM"), opts.timeoutMs);
		child.on("close", (code) => { clearTimeout(timer); sink?.end(); resolve({ code, out: Buffer.concat(chunks).toString("utf8") }); });
		child.on("error", (error) => { clearTimeout(timer); resolve({ code: -1, out: String(error) }); });
	});
}

/** A clean detached worktree per commit: evaluations never see the shared checkout's WIP. */
function worktree(commit: string): string {
	const dir = path.join(LOOP_DIR, "wt", commit.slice(0, 12));
	if (!fs.existsSync(path.join(dir, ".git"))) {
		fs.rmSync(dir, { recursive: true, force: true });
		git(["worktree", "add", "--detach", "--force", dir, commit]);
	}
	const modules = path.join(dir, "node_modules");
	if (!fs.existsSync(modules)) fs.symlinkSync(path.join(REPO, "node_modules"), modules);
	return dir;
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
		evidence: [raw.executionFailure, raw.hiddenOutput, raw.startupLog].filter(Boolean).join("\n").slice(-3000),
	};
}

/** owner/repo for a GitHub remote; undefined for a plain git remote (e.g. a sandbox bare repo). */
function repoSlug(): string | undefined {
	const url = git(["remote", "get-url", config().remote]);
	return url.match(/github\.com[:/]([^/]+\/[^/.]+?)(?:\.git)?$/)?.[1];
}

export function realDeps(cfg: FullConfig): LoopDeps {
	fs.mkdirSync(LOOP_DIR, { recursive: true });
	return {
		now: () => Date.now(),
		lock() {
			try {
				const fd = fs.openSync(LOCK, "wx");
				fs.writeSync(fd, String(process.pid));
				fs.closeSync(fd);
			} catch {
				const holder = Number(fs.readFileSync(LOCK, "utf8"));
				let alive = false;
				try { process.kill(holder, 0); alive = true; } catch (error: any) { alive = error?.code === "EPERM"; }
				if (alive) return undefined;
				fs.writeFileSync(LOCK, String(process.pid)); // dead holder: reclaim
			}
			return () => { try { if (fs.readFileSync(LOCK, "utf8") === String(process.pid)) fs.unlinkSync(LOCK); } catch { /* gone */ } };
		},
		readState: () => (fs.existsSync(STATE) ? { ...emptyState(), ...JSON.parse(fs.readFileSync(STATE, "utf8")) } : emptyState()),
		writeState(state: LoopState) {
			const tmp = `${STATE}.${process.pid}.tmp`;
			fs.writeFileSync(tmp, `${JSON.stringify(state, null, 2)}\n`);
			fs.renameSync(tmp, STATE);
		},
		async head() {
			git(["fetch", "--quiet", cfg.remote, cfg.branch]);
			return git(["rev-parse", `${cfg.remote}/${cfg.branch}`]);
		},
		async evaluate(commit, groups, tasks) {
			const wt = worktree(commit);
			const label = `loop-${commit.slice(0, 8)}-${Date.now()}`;
			const runs = await Promise.all(groups.map((group) => run("bun", [path.join(wt, "evals/fusion-eval/run.ts"), "run", "--label", label, "--groups", group, "--harness", wt, ...(tasks ? ["--tasks", tasks.join(",")] : [])], { cwd: wt, env: { FH_EVAL_RESULTS_DIR: RESULTS }, timeoutMs: 6 * 3600_000, logFile: path.join(LOOP_DIR, `${label}-${group}.log`) })));
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
		async proposeFix({ base, regressions, evidence }) {
			const branch = `eval-loop/fix-${base.slice(0, 8)}-${Date.now()}`;
			const dir = path.join(LOOP_DIR, "fix", branch.replace(/\//g, "_"));
			git(["worktree", "add", "-b", branch, dir, base]);
			fs.symlinkSync(path.join(REPO, "node_modules"), path.join(dir, "node_modules"));
			const evidenceFile = path.join(LOOP_DIR, `${branch.replace(/\//g, "_")}.evidence.md`);
			fs.writeFileSync(evidenceFile, evidence);
			const prompt = [
				"Fix a regression in this repository (the fusion-harness itself), found by the locked fusion eval.",
				`Evidence (confirmed by a re-run, with the diff since the last good commit): ${evidenceFile}`,
				`Regressions: ${regressions.map((r) => `${r.key} [${r.kind}] ${r.detail}`).join("; ")}.`,
				"Make the smallest change under extensions/fusion-harness that fixes the cause, add or update a test that fails without the fix, and run `bun test` until it passes.",
				"Do NOT edit evals/fusion-eval/tasks/ or evals/fusion-eval/lock.json — changing the grader is not a fix. Do not push, merge, or publish; the loop's gate does that.",
			].join(" ");
			const result = await run("pi", ["-e", path.join(dir, "extensions/fusion-harness/fusion-harness.ts"), "--fh-config", groupFile(cfg.fixGroup), "-p", `/fh-collaborate ${prompt}`], { cwd: dir, timeoutMs: 4 * 3600_000, logFile: path.join(LOOP_DIR, `${branch.replace(/\//g, "_")}.fix.log`) });
			const changed = git(["status", "--porcelain"], dir).split("\n").filter(Boolean).map((line) => line.slice(3)).filter((file) => file !== "node_modules");
			if (!changed.length) return undefined;
			const forbidden = changed.filter((file) => LOCKED_SUITE.test(file));
			if (forbidden.length) throw new Error(`fix run edited the locked suite (${forbidden.join(", ")}) — rejected (pi exit ${result.code})`);
			git(["add", "--", ...changed], dir);
			git(["-c", "user.name=fusion-eval-loop", "-c", "user.email=noreply@anthropic.com", "commit", "-q", "-m", `eval-loop: fix ${regressions.map((r) => `${r.key} ${r.kind}`).join(", ")}\n\nProposed by the fusion eval loop from confirmed regressions; see the PR for evidence and the gate result.`], dir);
			return { branch, commit: git(["rev-parse", "HEAD"], dir) };
		},
		async runTests(commit) {
			const wt = worktree(commit);
			const result = await run("bun", ["test"], { cwd: wt, timeoutMs: 30 * 60_000 });
			const counts = result.out.replace(/\x1b\[[0-9;]*m/g, "").match(/^\s*\d+ (pass|fail)$/gm)?.map((line) => line.trim()).join(", ") ?? "no summary";
			return { ok: result.code === 0 && /\b0 fail\b/.test(counts), summary: counts };
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
			spawnSync("gh", ["pr", "merge", fix.branch, "--repo", slug, "--merge"], { encoding: "utf8" });
			const state = spawnSync("gh", ["pr", "view", fix.branch, "--repo", slug, "--json", "state", "-q", ".state"], { encoding: "utf8" }).stdout.trim();
			return { pr, merged: state === "MERGED" };
		},
		log(line, opts) {
			const stamped = `${new Date().toISOString()} ${line}`;
			fs.appendFileSync(LOG, `${stamped}\n`);
			console.log(stamped);
			if (opts?.rot && VAULT && fs.existsSync(path.join(VAULT, "ROT.md"))) {
				fs.appendFileSync(path.join(VAULT, "ROT.md"), `- ${new Date().toISOString().slice(0, 10)} — fusion eval loop: ${line.replace(/\s+/g, " ").slice(0, 400)} (log: ${LOG})\n`);
				spawnSync("python3", ["scripts/llmwiki_sync.py"], { cwd: VAULT, timeout: 120_000 });
			}
		},
	};
}

function plist(): string {
	const bin = [path.join(HOME, ".bun/bin"), path.join(HOME, ".local/bin"), "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"].join(":");
	return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.evanmotovich.fusion-eval-loop</string>
  <key>ProgramArguments</key><array>
    <string>${path.join(HOME, ".bun/bin/bun")}</string>
    <string>${path.join(REPO, "evals/fusion-eval/loop.ts")}</string>
    <string>tick</string>
  </array>
  <key>WorkingDirectory</key><string>${REPO}</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>${bin}</string><key>HOME</key><string>${HOME}</string></dict>
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
		const result = await tick(deps, cfg);
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
		fs.mkdirSync(path.dirname(PLIST), { recursive: true });
		fs.writeFileSync(PLIST, plist());
		spawnSync("launchctl", ["unload", PLIST]);
		const loaded = spawnSync("launchctl", ["load", "-w", PLIST], { encoding: "utf8" });
		console.log(loaded.status === 0 ? `installed: ticks every 30 min (${PLIST})` : `launchctl load failed: ${loaded.stderr}`);
	} else if (cmd === "uninstall") {
		spawnSync("launchctl", ["unload", "-w", PLIST]);
		fs.rmSync(PLIST, { force: true });
		console.log("uninstalled");
	} else {
		console.log(fs.readFileSync(new URL(import.meta.url).pathname, "utf8").split("*/")[0]);
	}
}

if (import.meta.main) main().catch((error) => { console.error(error instanceof Error ? error.message : error); process.exit(1); });
