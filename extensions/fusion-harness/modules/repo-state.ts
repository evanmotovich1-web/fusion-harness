/**
 * repo-state.ts — deterministic git snapshot and pure classifier.
 *
 * Offline and read-only by default: local refs only, no fetch, no mutations, no pi APIs.
 * Callers pass source/target refs; this module does not infer intent from branch names.
 */

import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const GIT_TIMEOUT_MS = 15_000;

export const REPO_STATE_VERDICTS = [
	"proceed",
	"already_integrated",
	"fast_forward_possible",
	"blocked_dirty",
	"blocked_diverged",
	"blocked_stale",
	"needs_decision",
] as const;

export type RepoStateVerdict = (typeof REPO_STATE_VERDICTS)[number];

export interface CollectRepoStateOptions {
	/** Comparison source. Default HEAD. */
	sourceRef?: string;
	/** Comparison target. Default: upstream, else origin/HEAD, else origin/main. */
	targetRef?: string;
	/** When set, a different live target SHA yields blocked_stale. */
	expectedTargetSha?: string;
}

export interface DirtPath {
	path: string;
	xy: string;
	kind: "tracked" | "untracked" | "unmerged";
}

export interface RepoIdentity {
	worktree: string;
	gitDir: string;
	gitCommonDir: string;
	repositoryId: string;
	worktreeId: string;
	isBare: boolean;
	isLinkedWorktree: boolean;
}

export interface RepoRefSnapshot {
	name: string;
	sha: string | null;
	exists: boolean;
}

export interface RepoFreshness {
	fetchedThisCall: false;
	remotes: string[];
	fetchHeadExists: boolean;
	fetchHeadMtimeMs: number | null;
}

export interface RepoStateFacts {
	identity: RepoIdentity;
	head: {
		sha: string | null;
		detached: boolean;
		unborn: boolean;
		branch: string | null;
	};
	upstream: { ref: string | null; sha: string | null };
	source: RepoRefSnapshot;
	target: RepoRefSnapshot;
	mergeBase: string | null;
	ahead: number | null;
	behind: number | null;
	sourceIsAncestorOfTarget: boolean | null;
	targetIsAncestorOfSource: boolean | null;
	dirt: { tracked: DirtPath[]; untracked: DirtPath[]; unmerged: DirtPath[] };
	freshness: RepoFreshness;
}

export interface RepoStateClassification {
	verdict: RepoStateVerdict;
	reasonCodes: string[];
}

export interface RepoStateCard extends RepoStateFacts, RepoStateClassification {
	collectedAt: number;
	hash: string;
}

interface GitResult {
	code: number;
	stdout: string;
	stderr: string;
}

function canonical(cwd: string): string {
	try {
		return fs.realpathSync.native(cwd);
	} catch {
		return path.resolve(cwd);
	}
}

function idHash(value: string): string {
	return createHash("sha256").update(value).digest("hex").slice(0, 16);
}

async function gitRaw(cwd: string, args: string[]): Promise<GitResult> {
	try {
		const { stdout, stderr } = await execFileAsync("git", args, {
			cwd,
			timeout: GIT_TIMEOUT_MS,
			maxBuffer: 8 * 1024 * 1024,
			env: { ...process.env, GIT_TERMINAL_PROMPT: "0", GIT_OPTIONAL_LOCKS: "0" },
		});
		return { code: 0, stdout: String(stdout).replace(/\s+$/, ""), stderr: String(stderr ?? "").trim() };
	} catch (error: any) {
		if (error?.code === "ENOENT") throw new Error("git executable not found");
		const status = typeof error?.status === "number" ? error.status : typeof error?.code === "number" ? error.code : 1;
		return {
			code: status,
			stdout: String(error?.stdout ?? "").replace(/\s+$/, ""),
			stderr: String(error?.stderr ?? "").trim(),
		};
	}
}

function absGitPath(cwd: string, raw: string): string {
	const resolved = path.isAbsolute(raw) ? raw : path.resolve(cwd, raw);
	try {
		return fs.realpathSync.native(resolved);
	} catch {
		return resolved;
	}
}

async function resolveSha(cwd: string, ref: string): Promise<string | null> {
	const result = await gitRaw(cwd, ["rev-parse", "-q", "--verify", `${ref}^{commit}`]);
	if (result.code !== 0 || !/^[0-9a-f]{40}$/i.test(result.stdout)) return null;
	return result.stdout.toLowerCase();
}

async function isAncestor(cwd: string, maybeAncestor: string, descendant: string): Promise<boolean | null> {
	if (!maybeAncestor || !descendant) return null;
	const result = await gitRaw(cwd, ["merge-base", "--is-ancestor", maybeAncestor, descendant]);
	if (result.code === 0) return true;
	if (result.code === 1) return false;
	return null;
}

function parsePorcelain(raw: string): DirtPath[] {
	const entries: DirtPath[] = [];
	for (const line of raw.split("\n")) {
		if (line.length < 3) continue;
		const xy = line.slice(0, 2);
		let filePath = line.slice(3);
		const arrow = filePath.lastIndexOf(" -> ");
		if (arrow >= 0) filePath = filePath.slice(arrow + 4);
		const unmerged = xy.includes("U") || xy === "AA" || xy === "DD";
		const kind: DirtPath["kind"] = unmerged ? "unmerged" : xy === "??" ? "untracked" : "tracked";
		entries.push({ path: filePath, xy, kind });
	}
	entries.sort((a, b) => a.path.localeCompare(b.path) || a.kind.localeCompare(b.kind));
	return entries;
}

function splitDirt(entries: DirtPath[]): RepoStateFacts["dirt"] {
	return {
		tracked: entries.filter((entry) => entry.kind === "tracked"),
		untracked: entries.filter((entry) => entry.kind === "untracked"),
		unmerged: entries.filter((entry) => entry.kind === "unmerged"),
	};
}

async function defaultTargetRef(cwd: string, branch: string | null): Promise<string | null> {
	const upstream = await gitRaw(cwd, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]);
	if (upstream.code === 0 && upstream.stdout) return upstream.stdout;
	const originHead = await gitRaw(cwd, ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"]);
	if (originHead.code === 0 && originHead.stdout) return originHead.stdout;
	if ((await resolveSha(cwd, "refs/remotes/origin/main")) !== null) return "refs/remotes/origin/main";
	if (branch !== "main" && (await resolveSha(cwd, "refs/heads/main")) !== null) return "refs/heads/main";
	return null;
}

function hashCard(facts: RepoStateFacts, classification: RepoStateClassification): string {
	return createHash("sha256")
		.update(
			JSON.stringify({
				identity: facts.identity,
				head: facts.head,
				upstream: facts.upstream,
				source: facts.source,
				target: facts.target,
				mergeBase: facts.mergeBase,
				ahead: facts.ahead,
				behind: facts.behind,
				sourceIsAncestorOfTarget: facts.sourceIsAncestorOfTarget,
				targetIsAncestorOfSource: facts.targetIsAncestorOfSource,
				dirt: facts.dirt,
				remotes: facts.freshness.remotes,
				fetchHeadExists: facts.freshness.fetchHeadExists,
				verdict: classification.verdict,
				reasonCodes: classification.reasonCodes,
			}),
		)
		.digest("hex");
}

/** Pure. Same facts always produce the same verdict and sorted reason codes. */
export function classifyRepoState(facts: RepoStateFacts, options: { expectedTargetSha?: string } = {}): RepoStateClassification {
	const reasons = new Set<string>();
	if (facts.head.detached) reasons.add("detached_head");
	if (facts.head.unborn) reasons.add("unborn_head");
	if (facts.dirt.unmerged.length) reasons.add("unmerged_paths");
	if (facts.dirt.tracked.length) reasons.add("dirty_tracked");
	if (facts.dirt.untracked.length) reasons.add("dirty_untracked");
	if (!facts.source.exists || !facts.source.sha) reasons.add("missing_source");
	if (!facts.target.exists || !facts.target.sha) reasons.add("missing_target");
	if (options.expectedTargetSha) {
		if (!facts.target.sha || facts.target.sha !== options.expectedTargetSha.toLowerCase()) reasons.add("target_moved");
	}
	if (facts.source.sha && facts.target.sha && facts.source.sha === facts.target.sha) reasons.add("equal_shas");
	if (facts.sourceIsAncestorOfTarget === true && facts.source.sha && facts.target.sha && facts.source.sha !== facts.target.sha) {
		reasons.add("source_contained");
	}
	if (
		facts.targetIsAncestorOfSource === true &&
		facts.source.sha &&
		facts.target.sha &&
		facts.source.sha !== facts.target.sha &&
		(facts.behind ?? 0) === 0 &&
		(facts.ahead ?? 0) > 0
	) {
		reasons.add("fast_forward");
	}
	if ((facts.ahead ?? 0) > 0 && (facts.behind ?? 0) > 0) reasons.add("diverged");
	if (facts.source.sha && facts.target.sha && facts.source.sha !== facts.target.sha && facts.mergeBase === null) {
		reasons.add("unrelated_histories");
	}

	let verdict: RepoStateVerdict;
	if (reasons.has("unmerged_paths") || reasons.has("dirty_tracked") || reasons.has("dirty_untracked")) verdict = "blocked_dirty";
	else if (reasons.has("unborn_head") || reasons.has("missing_source") || reasons.has("missing_target")) verdict = "needs_decision";
	else if (reasons.has("target_moved")) verdict = "blocked_stale";
	else if (reasons.has("equal_shas") || reasons.has("source_contained")) verdict = "already_integrated";
	else if (reasons.has("fast_forward")) verdict = "fast_forward_possible";
	else if (reasons.has("diverged") || reasons.has("unrelated_histories")) verdict = "blocked_diverged";
	else verdict = "proceed";

	return { verdict, reasonCodes: [...reasons].sort() };
}

export async function collectRepoState(cwd: string, options: CollectRepoStateOptions = {}): Promise<RepoStateCard> {
	const worktree = canonical(cwd);
	const gitDirRaw = await gitRaw(worktree, ["rev-parse", "--absolute-git-dir"]);
	if (gitDirRaw.code !== 0) {
		throw new Error(`repo-state needs a git repository: ${worktree} (${gitDirRaw.stderr || gitDirRaw.stdout || "not a git repository"})`);
	}
	const gitDir = absGitPath(worktree, gitDirRaw.stdout);
	const commonRaw = await gitRaw(worktree, ["rev-parse", "--git-common-dir"]);
	const gitCommonDir = absGitPath(worktree, commonRaw.code === 0 && commonRaw.stdout ? commonRaw.stdout : gitDir);
	const bareRaw = await gitRaw(worktree, ["rev-parse", "--is-bare-repository"]);
	const isBare = bareRaw.stdout === "true";
	const toplevel = await gitRaw(worktree, ["rev-parse", "--show-toplevel"]);
	const worktreePath = toplevel.code === 0 && toplevel.stdout ? absGitPath(worktree, toplevel.stdout) : worktree;

	const headSha = await resolveSha(worktree, "HEAD");
	const unborn = headSha === null;
	const abbrev = await gitRaw(worktree, ["rev-parse", "--abbrev-ref", "HEAD"]);
	const detached = unborn || abbrev.stdout === "HEAD";
	const branch = detached || unborn ? null : abbrev.stdout || null;

	const upstreamRefRaw = await gitRaw(worktree, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]);
	const upstreamRef = upstreamRefRaw.code === 0 && upstreamRefRaw.stdout ? upstreamRefRaw.stdout : null;
	const upstreamSha = upstreamRef ? await resolveSha(worktree, upstreamRef) : null;

	const sourceName = options.sourceRef?.trim() || "HEAD";
	const targetName = options.targetRef?.trim() || (await defaultTargetRef(worktree, branch)) || "";
	const sourceSha = await resolveSha(worktree, sourceName);
	const targetSha = targetName ? await resolveSha(worktree, targetName) : null;

	let mergeBase: string | null = null;
	if (sourceSha && targetSha) {
		const base = await gitRaw(worktree, ["merge-base", sourceSha, targetSha]);
		if (base.code === 0 && /^[0-9a-f]{40}$/i.test(base.stdout)) mergeBase = base.stdout.toLowerCase();
	}

	let ahead: number | null = null;
	let behind: number | null = null;
	if (sourceSha && targetSha) {
		const counts = await gitRaw(worktree, ["rev-list", "--left-right", "--count", `${targetSha}...${sourceSha}`]);
		if (counts.code === 0) {
			const match = counts.stdout.match(/^(\d+)\s+(\d+)$/);
			if (match) {
				behind = Number(match[1]);
				ahead = Number(match[2]);
			}
		}
	}

	const sourceIsAncestorOfTarget = sourceSha && targetSha ? await isAncestor(worktree, sourceSha, targetSha) : null;
	const targetIsAncestorOfSource = sourceSha && targetSha ? await isAncestor(worktree, targetSha, sourceSha) : null;

	const status = await gitRaw(worktree, ["status", "--porcelain=v1", "--untracked-files=all"]);
	const dirt = splitDirt(parsePorcelain(status.code === 0 ? status.stdout : ""));

	const remoteList = await gitRaw(worktree, ["remote"]);
	const remotes = remoteList.code === 0 && remoteList.stdout ? remoteList.stdout.split("\n").filter(Boolean).sort() : [];
	const fetchHeadPath = path.join(gitCommonDir, "FETCH_HEAD");
	let fetchHeadExists = false;
	let fetchHeadMtimeMs: number | null = null;
	try {
		const stat = fs.statSync(fetchHeadPath);
		fetchHeadExists = stat.isFile();
		fetchHeadMtimeMs = fetchHeadExists ? Math.trunc(stat.mtimeMs) : null;
	} catch {
		fetchHeadExists = false;
	}

	const facts: RepoStateFacts = {
		identity: {
			worktree: worktreePath,
			gitDir,
			gitCommonDir,
			repositoryId: idHash(gitCommonDir),
			worktreeId: idHash(worktreePath),
			isBare,
			isLinkedWorktree: !isBare && gitDir !== gitCommonDir,
		},
		head: { sha: headSha, detached, unborn, branch },
		upstream: { ref: upstreamRef, sha: upstreamSha },
		source: { name: sourceName, sha: sourceSha, exists: sourceSha !== null },
		target: { name: targetName || "(none)", sha: targetSha, exists: targetSha !== null },
		mergeBase,
		ahead,
		behind,
		sourceIsAncestorOfTarget,
		targetIsAncestorOfSource,
		dirt,
		freshness: { fetchedThisCall: false, remotes, fetchHeadExists, fetchHeadMtimeMs },
	};
	const classification = classifyRepoState(facts, { expectedTargetSha: options.expectedTargetSha });
	return {
		...facts,
		...classification,
		collectedAt: Date.now(),
		hash: hashCard(facts, classification),
	};
}
