import { afterEach, describe, expect, test } from "bun:test";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { classifyRepoState, collectRepoState, type RepoStateFacts } from "../modules/repo-state.ts";

const repos: string[] = [];
const gitIdentity = ["-c", "user.name=t", "-c", "user.email=t@t"];
const sh = (cwd: string, args: string[]) => execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();

function repo(branch = "main"): string {
	const dir = mkdtempSync(join(tmpdir(), "fh-repo-state-"));
	repos.push(dir);
	sh(dir, ["init", "-q", "-b", branch]);
	writeFileSync(join(dir, "a.txt"), "one\n");
	sh(dir, ["add", "a.txt"]);
	sh(dir, [...gitIdentity, "commit", "-q", "-m", "root"]);
	return dir;
}

function commitFile(dir: string, file: string, body: string, message: string): void {
	writeFileSync(join(dir, file), body);
	sh(dir, ["add", file]);
	sh(dir, [...gitIdentity, "commit", "-q", "-m", message]);
}

function factsShell(overrides: Partial<RepoStateFacts> = {}): RepoStateFacts {
	const shaA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
	const shaB = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
	return {
		identity: {
			worktree: "/tmp/wt",
			gitDir: "/tmp/wt/.git",
			gitCommonDir: "/tmp/wt/.git",
			repositoryId: "repo",
			worktreeId: "wt",
			isBare: false,
			isLinkedWorktree: false,
		},
		head: { sha: shaA, detached: false, unborn: false, branch: "topic" },
		upstream: { ref: null, sha: null },
		source: { name: "HEAD", sha: shaA, exists: true },
		target: { name: "refs/heads/main", sha: shaB, exists: true },
		mergeBase: shaB,
		ahead: 1,
		behind: 0,
		sourceIsAncestorOfTarget: false,
		targetIsAncestorOfSource: true,
		dirt: { tracked: [], untracked: [], unmerged: [] },
		freshness: { fetchedThisCall: false, remotes: [], fetchHeadExists: false, fetchHeadMtimeMs: null },
		...overrides,
	};
}

afterEach(() => {
	while (repos.length) {
		const dir = repos.pop()!;
		rmSync(dir, { recursive: true, force: true });
	}
});

describe("collectRepoState", () => {
	test("refuses a directory that is not a git repository", async () => {
		const dir = mkdtempSync(join(tmpdir(), "fh-repo-state-nogit-"));
		repos.push(dir);
		await expect(collectRepoState(dir)).rejects.toThrow("repo-state needs a git repository");
	});

	test("equal HEAD and main is already_integrated", async () => {
		const dir = repo();
		const card = await collectRepoState(dir, { sourceRef: "HEAD", targetRef: "main" });
		expect(card.verdict).toBe("already_integrated");
		expect(card.reasonCodes).toContain("equal_shas");
		expect(card.head.branch).toBe("main");
		expect(card.head.sha).toBe(sh(dir, ["rev-parse", "HEAD"]));
		expect(card.source.sha).toBe(card.target.sha);
		expect(card.ahead).toBe(0);
		expect(card.behind).toBe(0);
		expect(card.freshness.fetchedThisCall).toBe(false);
		expect(card.identity.isLinkedWorktree).toBe(false);
	});

	test("unique source commits with target as ancestor is fast_forward_possible", async () => {
		const dir = repo();
		const main = sh(dir, ["rev-parse", "HEAD"]);
		sh(dir, ["checkout", "-q", "-b", "topic"]);
		commitFile(dir, "a.txt", "one\ntwo\n", "topic");
		const card = await collectRepoState(dir, { sourceRef: "HEAD", targetRef: "main" });
		expect(card.verdict).toBe("fast_forward_possible");
		expect(card.reasonCodes).toContain("fast_forward");
		expect(card.target.sha).toBe(main);
		expect(card.ahead).toBe(1);
		expect(card.behind).toBe(0);
		expect(card.targetIsAncestorOfSource).toBe(true);
		expect(card.sourceIsAncestorOfTarget).toBe(false);
	});

	test("source contained in target is already_integrated even when behind", async () => {
		const dir = repo();
		sh(dir, ["checkout", "-q", "-b", "topic"]);
		commitFile(dir, "a.txt", "topic\n", "topic");
		const topic = sh(dir, ["rev-parse", "HEAD"]);
		sh(dir, ["checkout", "-q", "main"]);
		sh(dir, ["merge", "-q", "--no-ff", "-m", "integrate", "topic"]);
		sh(dir, ["checkout", "-q", "topic"]);
		const card = await collectRepoState(dir, { sourceRef: "HEAD", targetRef: "main" });
		expect(card.source.sha).toBe(topic);
		expect(card.verdict).toBe("already_integrated");
		expect(card.reasonCodes).toContain("source_contained");
		expect(card.sourceIsAncestorOfTarget).toBe(true);
		expect(card.ahead).toBe(0);
		expect(card.behind).toBe(1);
	});

	test("both sides unique is blocked_diverged", async () => {
		const dir = repo();
		sh(dir, ["checkout", "-q", "-b", "topic"]);
		commitFile(dir, "a.txt", "topic\n", "topic");
		sh(dir, ["checkout", "-q", "main"]);
		commitFile(dir, "b.txt", "main\n", "mainline");
		sh(dir, ["checkout", "-q", "topic"]);
		const card = await collectRepoState(dir, { sourceRef: "HEAD", targetRef: "main" });
		expect(card.verdict).toBe("blocked_diverged");
		expect(card.reasonCodes).toContain("diverged");
		expect(card.ahead).toBe(1);
		expect(card.behind).toBe(1);
	});

	test("tracked dirt is blocked_dirty and keeps topology reasons", async () => {
		const dir = repo();
		writeFileSync(join(dir, "a.txt"), "dirty\n");
		const card = await collectRepoState(dir, { sourceRef: "HEAD", targetRef: "main" });
		expect(card.verdict).toBe("blocked_dirty");
		expect(card.reasonCodes).toContain("dirty_tracked");
		expect(card.reasonCodes).toContain("equal_shas");
		expect(card.dirt.tracked.map((entry) => entry.path)).toEqual(["a.txt"]);
	});

	test("untracked dirt is blocked_dirty", async () => {
		const dir = repo();
		writeFileSync(join(dir, "extra.txt"), "x\n");
		const card = await collectRepoState(dir, { sourceRef: "HEAD", targetRef: "main" });
		expect(card.verdict).toBe("blocked_dirty");
		expect(card.reasonCodes).toContain("dirty_untracked");
		expect(card.dirt.untracked.map((entry) => entry.path)).toEqual(["extra.txt"]);
	});

	test("unmerged paths are blocked_dirty", async () => {
		const dir = repo();
		sh(dir, ["checkout", "-q", "-b", "topic"]);
		commitFile(dir, "a.txt", "left\n", "left");
		sh(dir, ["checkout", "-q", "main"]);
		commitFile(dir, "a.txt", "right\n", "right");
		try {
			sh(dir, ["merge", "topic"]);
		} catch {
			/* conflict expected */
		}
		const card = await collectRepoState(dir, { sourceRef: "HEAD", targetRef: "main" });
		expect(card.verdict).toBe("blocked_dirty");
		expect(card.reasonCodes).toContain("unmerged_paths");
		expect(card.dirt.unmerged.length).toBeGreaterThan(0);
	});

	test("expectedTargetSha mismatch is blocked_stale", async () => {
		const dir = repo();
		const live = sh(dir, ["rev-parse", "HEAD"]);
		const card = await collectRepoState(dir, {
			sourceRef: "HEAD",
			targetRef: "main",
			expectedTargetSha: "ffffffffffffffffffffffffffffffffffffffff",
		});
		expect(card.target.sha).toBe(live);
		expect(card.verdict).toBe("blocked_stale");
		expect(card.reasonCodes).toContain("target_moved");
	});

	test("missing target is needs_decision", async () => {
		const dir = repo();
		const card = await collectRepoState(dir, { sourceRef: "HEAD", targetRef: "refs/heads/does-not-exist" });
		expect(card.verdict).toBe("needs_decision");
		expect(card.reasonCodes).toContain("missing_target");
		expect(card.target.exists).toBe(false);
	});

	test("does not fetch; FETCH_HEAD stays absent", async () => {
		const dir = repo();
		sh(dir, ["remote", "add", "origin", "https://example.invalid/repo.git"]);
		const card = await collectRepoState(dir, { sourceRef: "HEAD", targetRef: "main" });
		expect(card.freshness.fetchedThisCall).toBe(false);
		expect(card.freshness.remotes).toEqual(["origin"]);
		expect(card.freshness.fetchHeadExists).toBe(false);
	});

	test("linked worktree shares gitCommonDir and differs in worktree identity", async () => {
		const dir = repo();
		const linked = mkdtempSync(join(tmpdir(), "fh-repo-state-wt-"));
		repos.push(linked);
		rmSync(linked, { recursive: true, force: true });
		sh(dir, ["branch", "other"]);
		sh(dir, ["worktree", "add", "-q", linked, "other"]);
		const mainCard = await collectRepoState(dir, { sourceRef: "HEAD", targetRef: "main" });
		const linkCard = await collectRepoState(linked, { sourceRef: "HEAD", targetRef: "main" });
		expect(mainCard.identity.gitCommonDir).toBe(linkCard.identity.gitCommonDir);
		expect(mainCard.identity.repositoryId).toBe(linkCard.identity.repositoryId);
		expect(mainCard.identity.worktree).not.toBe(linkCard.identity.worktree);
		expect(mainCard.identity.worktreeId).not.toBe(linkCard.identity.worktreeId);
		expect(linkCard.identity.isLinkedWorktree).toBe(true);
	});

	test("hash is stable across two collects of the same tree", async () => {
		const dir = repo();
		const first = await collectRepoState(dir, { sourceRef: "HEAD", targetRef: "main" });
		const second = await collectRepoState(dir, { sourceRef: "HEAD", targetRef: "main" });
		expect(first.hash).toBe(second.hash);
		expect(first.verdict).toBe(second.verdict);
		expect(first.reasonCodes).toEqual(second.reasonCodes);
	});

	test("does not infer a target from the current feature branch name", async () => {
		const dir = repo();
		sh(dir, ["checkout", "-q", "-b", "capability-scout-hardening"]);
		commitFile(dir, "a.txt", "named\n", "named");
		const card = await collectRepoState(dir, { sourceRef: "HEAD", targetRef: "main" });
		expect(card.source.name).toBe("HEAD");
		expect(card.target.name).toBe("main");
		expect(card.head.branch).toBe("capability-scout-hardening");
		expect(card.verdict).toBe("fast_forward_possible");
	});
});

describe("classifyRepoState", () => {
	test("is pure and byte-stable", () => {
		const facts = factsShell();
		expect(classifyRepoState(facts)).toEqual(classifyRepoState(facts));
		expect(classifyRepoState(facts).verdict).toBe("fast_forward_possible");
	});

	test("proceed is the residual clean class", () => {
		const shaA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
		const shaB = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
		const result = classifyRepoState(
			factsShell({
				source: { name: "HEAD", sha: shaA, exists: true },
				target: { name: "main", sha: shaB, exists: true },
				mergeBase: shaA,
				ahead: 0,
				behind: 0,
				sourceIsAncestorOfTarget: false,
				targetIsAncestorOfSource: false,
			}),
		);
		expect(result.verdict).toBe("proceed");
	});
});
