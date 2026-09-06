/**
 * lanes.ts — one isolated git worktree ("lane") per model slot.
 *
 * The harness's single-writer invariant protects ONE shared checkout. Lanes let every
 * builder write at the same time without breaking it: each slot gets its own worktree
 * on its own branch, seeded from the main checkout's HEAD plus its uncommitted changes,
 * so parallel writers never touch the same files. Only the merge step (which runs in
 * the main checkout, under the writer lease) ever mutates the user's working directory.
 *
 * Pure git plumbing: no pi APIs, no prompts, no rendering. Every function takes the
 * main checkout's cwd explicitly and shells out to `git`.
 */

import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export const LANE_BRANCH_PREFIX = "fh/lane/";
const LANE_COMMIT_IDENTITY = ["-c", "user.name=fusion-harness", "-c", "user.email=fusion-harness@localhost", "-c", "commit.gpgsign=false"];
const GIT_TIMEOUT_MS = 60_000;

export interface Lane {
	slotId: string;
	path: string; // the worktree directory the slot works in
	branch: string; // fh/lane/<checkout key>/<slotId> — keyed per checkout so several worktrees of one repo can lane at once
	base: string; // commit the slot's work is diffed against (HEAD, or the carried working-tree commit)
	carried: boolean; // true when the main checkout's uncommitted changes were committed into the lane base
}

export interface LaneStatus {
	files: number; // paths that differ from the lane branch's last commit (tracked + untracked)
	insertions: number;
	deletions: number;
}

export interface LaneCommit {
	committed: boolean; // false when the slot changed nothing
	sha?: string;
	files: string[]; // paths touched by the work commit
}

export interface LaneDiff {
	stat: string; // `git diff --stat base..branch`
	patch: string; // full `git diff base..branch`
	files: string[];
}

/** Exact lane state captured before a forced worktree/branch removal. */
export interface LaneRemovalEvidence {
	slotId: string;
	branch: string;
	path: string;
	branchSha: string | null;
	worktreeHeadSha: string | null;
	statusHash: string | null;
	dirtyPaths: number;
}

/** Run git in `cwd`; stdout trimmed. Errors carry git's stderr so callers can surface it verbatim. */
export async function git(cwd: string, args: string[], input?: string): Promise<string> {
	try {
		const child = execFileAsync("git", args, { cwd, maxBuffer: 64 * 1024 * 1024, timeout: GIT_TIMEOUT_MS, env: { ...process.env, GIT_TERMINAL_PROMPT: "0" } });
		if (input !== undefined && child.child.stdin) {
			child.child.stdin.end(input);
		}
		const { stdout } = await child;
		return stdout.replace(/\s+$/, "");
	} catch (error: any) {
		const stderr = typeof error?.stderr === "string" ? error.stderr.trim() : "";
		throw new Error(`git ${args.slice(0, 2).join(" ")} failed in ${cwd}: ${stderr || error?.message || String(error)}`);
	}
}

function canonical(cwd: string): string {
	try {
		return fs.realpathSync.native(cwd);
	} catch {
		return path.resolve(cwd);
	}
}

/** Where every lane for a project lives — outside the repo, so lanes never show up in its status. */
/** Short stable id of one checkout. Git branches are shared by every worktree of a repo, so lane branches carry it. */
export const laneKey = (cwd: string): string => createHash("sha256").update(canonical(cwd)).digest("hex").slice(0, 12);

export function laneRootFor(cwd: string): string {
	const root = fs.existsSync("/tmp") ? "/tmp" : os.tmpdir();
	const readable = canonical(cwd).replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(-40) || "root";
	return path.join(root, "fusion-harness-lanes", `${readable}-${laneKey(cwd)}`);
}

/** The branch prefix owned by ONE checkout: `fh/lane/<key>/`. Cleanup never reaches past it. */
export const laneBranchPrefixFor = (cwd: string): string => `${LANE_BRANCH_PREFIX}${laneKey(cwd)}/`;
export const laneBranch = (cwd: string, slotId: string): string => `${laneBranchPrefixFor(cwd)}${slotId}`;
export const lanePath = (cwd: string, slotId: string): string => path.join(laneRootFor(cwd), slotId);

/** The repository root for `cwd`, or a clear error when lanes are impossible here. */
export async function gitTopLevel(cwd: string): Promise<string> {
	try {
		return await git(cwd, ["rev-parse", "--show-toplevel"]);
	} catch (error) {
		throw new Error(`lanes need a git repository: ${canonical(cwd)} is not inside one (${error instanceof Error ? error.message : String(error)})`);
	}
}

async function branchExists(cwd: string, branch: string): Promise<boolean> {
	try {
		await git(cwd, ["rev-parse", "--verify", "--quiet", `refs/heads/${branch}`]);
		return true;
	} catch {
		return false;
	}
}

async function laneStatusDigest(laneDir: string, status: string): Promise<string> {
	const digest = createHash("sha256");
	digest.update(status).update("\0");
	digest.update(await git(laneDir, ["diff", "--binary", "HEAD"])).update("\0");
	digest.update(await git(laneDir, ["diff", "--cached", "--binary", "HEAD"])).update("\0");
	const untracked = (await git(laneDir, ["ls-files", "--others", "--exclude-standard", "-z"])).split("\0").filter(Boolean).sort();
	for (const rel of untracked) {
		const file = path.join(laneDir, rel);
		digest.update(rel).update("\0");
		try {
			const stat = await fs.promises.lstat(file);
			if (stat.isSymbolicLink()) digest.update(`symlink:${await fs.promises.readlink(file)}`);
			else if (stat.isFile()) digest.update(await fs.promises.readFile(file));
			else digest.update(`mode:${stat.mode}:size:${stat.size}`);
		} catch {
			digest.update("missing");
		}
		digest.update("\0");
	}
	return digest.digest("hex");
}

/** Capture exact branch/worktree state before a destructive lane removal. */
export async function captureLaneRemovalEvidence(cwd: string, slotId: string): Promise<LaneRemovalEvidence> {
	const branch = laneBranch(cwd, slotId);
	const rawPath = lanePath(cwd, slotId);
	const laneDir = fs.existsSync(rawPath) ? canonical(rawPath) : rawPath;
	let branchSha: string | null = null;
	let worktreeHeadSha: string | null = null;
	let statusHash: string | null = null;
	let dirtyPaths = 0;
	if (await branchExists(cwd, branch)) branchSha = await git(cwd, ["rev-parse", "--verify", `refs/heads/${branch}^{commit}`]);
	if (fs.existsSync(laneDir)) {
		try {
			worktreeHeadSha = await git(laneDir, ["rev-parse", "--verify", "HEAD"]);
			const status = await git(laneDir, ["status", "--porcelain=v1", "--untracked-files=all"]);
			statusHash = await laneStatusDigest(laneDir, status);
			dirtyPaths = status ? status.split("\n").filter(Boolean).length : 0;
		} catch {
			// A vanished or invalid worktree still has explicit null evidence.
		}
	}
	return { slotId, branch, path: laneDir, branchSha, worktreeHeadSha, statusHash, dirtyPaths };
}

function sameRemovalEvidence(expected: LaneRemovalEvidence, live: LaneRemovalEvidence): boolean {
	return expected.slotId === live.slotId &&
		expected.branch === live.branch &&
		expected.path === live.path &&
		expected.branchSha === live.branchSha &&
		expected.worktreeHeadSha === live.worktreeHeadSha &&
		expected.statusHash === live.statusHash &&
		expected.dirtyPaths === live.dirtyPaths;
}

/** Every lane removal candidate, including orphaned lane branches. */
export async function listLaneRemovalEvidence(cwd: string): Promise<LaneRemovalEvidence[]> {
	const slotIds = new Set((await listLanes(cwd)).map((lane) => lane.slotId));
	const prefix = laneBranchPrefixFor(cwd);
	const branches = (await git(cwd, ["for-each-ref", "--format=%(refname:short)", `refs/heads/${prefix}`])).split("\n").filter(Boolean);
	for (const branch of branches) slotIds.add(branch.slice(prefix.length));
	const evidence = await Promise.all([...slotIds].sort().map((slotId) => captureLaneRemovalEvidence(cwd, slotId)));
	return evidence;
}

/** Force-remove one lane only when its exact pre-removal evidence is still current. */
export async function removeLane(cwd: string, evidence: LaneRemovalEvidence): Promise<void> {
	const live = await captureLaneRemovalEvidence(cwd, evidence.slotId);
	if (!sameRemovalEvidence(evidence, live)) {
		throw new Error(`lane ${evidence.slotId} changed after removal evidence was captured; refresh and retry`);
	}
	try {
		await git(cwd, ["worktree", "remove", "--force", evidence.path]);
	} catch {
		/* not registered as a worktree (or already gone) — fall through to the directory */
	}
	await fs.promises.rm(evidence.path, { recursive: true, force: true }).catch(() => {});
	try {
		await git(cwd, ["worktree", "prune"]);
	} catch {}
	if (await branchExists(cwd, evidence.branch)) {
		const branchSha = await git(cwd, ["rev-parse", "--verify", `refs/heads/${evidence.branch}^{commit}`]);
		if (branchSha !== evidence.branchSha) throw new Error(`lane ${evidence.slotId} branch moved before deletion; refusing`);
		await git(cwd, ["branch", "-D", evidence.branch]);
	}
}

/**
 * Create (or recreate) the lane for one slot: a fresh worktree on `fh/lane/<key>/<slotId>` at
 * HEAD, with the main checkout's uncommitted work carried in and committed as the lane's
 * BASE commit — so the slot starts from exactly what the user sees, and the slot's own
 * delta is cleanly `base..branch` afterwards (never contaminated by the carried hunks).
 */
export async function createLane(cwd: string, slotId: string): Promise<Lane> {
	await gitTopLevel(cwd);
	let head: string;
	try {
		head = await git(cwd, ["rev-parse", "--verify", "HEAD"]);
	} catch {
		throw new Error(`lanes need at least one commit: ${canonical(cwd)} has no HEAD yet`);
	}
	const removalEvidence = await captureLaneRemovalEvidence(cwd, slotId);
	await removeLane(cwd, removalEvidence);
	const dir = lanePath(cwd, slotId);
	await fs.promises.mkdir(path.dirname(dir), { recursive: true });
	await git(cwd, ["worktree", "add", "-q", "-b", laneBranch(cwd, slotId), dir, head]);

	// Carry the working tree: tracked modifications as one binary patch, untracked
	// (non-ignored) files copied byte for byte. Ignored files (node_modules, .env) are
	// NOT carried — a lane is a real checkout, not a clone of the machine.
	const trackedPatch = await git(cwd, ["diff", "--binary", "HEAD"]);
	if (trackedPatch.trim()) await git(dir, ["apply", "--whitespace=nowarn", "-"], `${trackedPatch}\n`);
	const untracked = (await git(cwd, ["ls-files", "--others", "--exclude-standard", "-z"])).split("\0").filter(Boolean);
	for (const rel of untracked) {
		const from = path.join(cwd, rel);
		const to = path.join(dir, rel);
		await fs.promises.mkdir(path.dirname(to), { recursive: true });
		await fs.promises.copyFile(from, to);
	}
	let base = head;
	let carried = false;
	if (trackedPatch.trim() || untracked.length) {
		await git(dir, ["add", "-A"]);
		const staged = await git(dir, ["diff", "--cached", "--name-only"]);
		if (staged.trim()) {
			await git(dir, [...LANE_COMMIT_IDENTITY, "commit", "-q", "--no-verify", "-m", `fh lane ${slotId}: carried working tree from ${canonical(cwd)}`]);
			base = await git(dir, ["rev-parse", "HEAD"]);
			carried = true;
		}
	}
	return { slotId, path: dir, branch: laneBranch(cwd, slotId), base, carried };
}

/** Live churn in a lane: how many paths differ from its last commit, and by how much. */
export async function laneStatus(lane: Pick<Lane, "path">): Promise<LaneStatus> {
	const porcelain = await git(lane.path, ["status", "--porcelain", "--untracked-files=all"]);
	const files = porcelain ? porcelain.split("\n").filter(Boolean).length : 0;
	const shortstat = await git(lane.path, ["diff", "--shortstat", "HEAD"]);
	const insertions = Number(/(\d+) insertion/.exec(shortstat)?.[1] ?? 0);
	const deletions = Number(/(\d+) deletion/.exec(shortstat)?.[1] ?? 0);
	return { files, insertions, deletions };
}

/** Commit everything the slot changed in its lane as ONE work commit (nothing to commit → committed: false). */
export async function commitLane(lane: Pick<Lane, "path" | "slotId">, message: string): Promise<LaneCommit> {
	await git(lane.path, ["add", "-A"]);
	const staged = (await git(lane.path, ["diff", "--cached", "--name-only"])).split("\n").filter(Boolean);
	if (!staged.length) return { committed: false, files: [] };
	await git(lane.path, [...LANE_COMMIT_IDENTITY, "commit", "-q", "--no-verify", "-m", message]);
	const sha = await git(lane.path, ["rev-parse", "HEAD"]);
	return { committed: true, sha, files: staged };
}

/** The slot's delta: everything between the lane base and the lane branch tip. */
export async function laneDiff(cwd: string, lane: Pick<Lane, "base" | "branch">): Promise<LaneDiff> {
	const range = `${lane.base}..${lane.branch}`;
	const stat = await git(cwd, ["diff", "--stat", range]);
	const patch = await git(cwd, ["diff", "--binary", range]);
	const files = (await git(cwd, ["diff", "--name-only", range])).split("\n").filter(Boolean);
	return { stat, patch, files };
}

/** Every lane worktree git currently knows about for this project, by slot id. */
export async function listLanes(cwd: string): Promise<Array<{ slotId: string; path: string; branch: string }>> {
	// git prints realpaths (macOS: /private/tmp/…) while laneRootFor says /tmp/… — compare canonical forms.
	const root = canonical(laneRootFor(cwd));
	let porcelain: string;
	try {
		porcelain = await git(cwd, ["worktree", "list", "--porcelain"]);
	} catch {
		return [];
	}
	const lanes: Array<{ slotId: string; path: string; branch: string }> = [];
	let current: { path?: string; branch?: string } = {};
	const flush = () => {
		if (current.path && canonical(current.path).startsWith(root + path.sep)) {
			const slotId = path.basename(current.path);
			lanes.push({ slotId, path: current.path, branch: current.branch?.replace(/^refs\/heads\//, "") ?? laneBranch(cwd, slotId) });
		}
		current = {};
	};
	for (const line of porcelain.split("\n")) {
		if (line.startsWith("worktree ")) {
			flush();
			current.path = line.slice("worktree ".length);
		} else if (line.startsWith("branch ")) current.branch = line.slice("branch ".length);
		else if (!line.trim()) flush();
	}
	flush();
	return lanes;
}

/** Remove every lane using exact evidence captured before the first destructive action. */
export async function cleanLanes(cwd: string, expected?: readonly LaneRemovalEvidence[]): Promise<string[]> {
	const evidence = expected ? [...expected] : await listLaneRemovalEvidence(cwd);
	const removed: string[] = [];
	for (const lane of evidence) {
		await removeLane(cwd, lane);
		removed.push(lane.slotId);
	}
	await fs.promises.rm(laneRootFor(cwd), { recursive: true, force: true }).catch(() => {});
	return removed;
}
