import { describe, expect, test } from "bun:test";
import {
	authorizeRepoAction,
	mintRepoActionReceipt,
	verifyRepoActionReceipt,
	DEFAULT_MAX_RECEIPT_AGE_MS,
	type RepoActionReceipt,
	type RepoActionReceiptInput,
} from "../modules/repo-action-policy.ts";
import type { RepoStateFacts } from "../modules/repo-state.ts";

const shaA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const shaB = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const shaC = "cccccccccccccccccccccccccccccccccccccccc";
const UPPER_A = shaA.toUpperCase();
const NOW = 1_800_000_000_000;

function facts(overrides: Partial<RepoStateFacts> = {}): RepoStateFacts {
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

/** A receipt that matches the default facts (ff-able candidate A over target B). */
function receiptInput(overrides: Partial<RepoActionReceiptInput> = {}): RepoActionReceiptInput {
	return {
		repositoryId: "repo",
		gitCommonDir: "/tmp/wt/.git",
		worktreeId: "wt",
		runId: "run-1",
		candidateSha: shaA,
		observedTargetSha: shaB,
		headBefore: shaA,
		headAfter: shaA,
		issuedAt: NOW,
		validation: { command: [".venv/bin/python", "-m", "unittest"], exitCode: 0, passed: 43, failed: 0, durationMs: 74 },
		...overrides,
	};
}

/** Authorize with `now` pinned to NOW so a freshly minted receipt is never stale by accident. */
function decide(
	receipt: RepoActionReceipt | null,
	factsArg: RepoStateFacts,
	opts: { consumed?: ReadonlySet<string>; now?: number; maxAge?: number } = {},
) {
	return authorizeRepoAction({
		receipt,
		facts: factsArg,
		consumedDigests: opts.consumed,
		now: opts.now ?? NOW,
		maxReceiptAgeMs: opts.maxAge,
	});
}

describe("mintRepoActionReceipt", () => {
	test("normalizes SHA case and computes a stable digest", () => {
		const lower = mintRepoActionReceipt(receiptInput());
		const upper = mintRepoActionReceipt(receiptInput({ candidateSha: UPPER_A, headBefore: UPPER_A, headAfter: UPPER_A }));
		expect(lower.digest).toBe(upper.digest);
		expect(lower.candidateSha).toBe(shaA);
		expect(lower.digest).toMatch(/^[0-9a-f]{64}$/);
	});

	test("distinct fields produce distinct digests", () => {
		const first = mintRepoActionReceipt(receiptInput());
		const second = mintRepoActionReceipt(receiptInput({ runId: "run-2" }));
		const third = mintRepoActionReceipt(receiptInput({ candidateSha: shaC, headBefore: shaC, headAfter: shaC }));
		expect(first.digest).not.toBe(second.digest);
		expect(first.digest).not.toBe(third.digest);
	});

	test("rejects a non-40-hex SHA", () => {
		expect(() => mintRepoActionReceipt(receiptInput({ candidateSha: "short" }))).toThrow("40-hex SHA");
	});

	test("rejects an empty runId", () => {
		expect(() => mintRepoActionReceipt(receiptInput({ runId: "  " }))).toThrow("runId");
	});

	test("rejects an empty validation command", () => {
		expect(() =>
			mintRepoActionReceipt(receiptInput({ validation: { command: [], exitCode: 0, passed: 0, failed: 0, durationMs: 0 } })),
		).toThrow("command");
	});

	test("rejects a non-positive issuedAt", () => {
		expect(() => mintRepoActionReceipt(receiptInput({ issuedAt: 0 }))).toThrow("issuedAt");
	});
});

describe("verifyRepoActionReceipt", () => {
	test("accepts a minted receipt", () => {
		expect(verifyRepoActionReceipt(mintRepoActionReceipt(receiptInput()))).toBe(true);
	});

	test("rejects a tampered field", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		expect(verifyRepoActionReceipt({ ...minted, candidateSha: shaC })).toBe(false);
	});

	test("rejects a tampered digest", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		expect(verifyRepoActionReceipt({ ...minted, digest: "0".repeat(64) })).toBe(false);
	});
});

describe("authorizeRepoAction", () => {
	test("no receipt refuses, never infers", () => {
		const decision = decide(null, facts());
		expect(decision).toMatchObject({ authorize: false, verdict: "refuse_no_receipt" });
		expect(decision.reasons).toEqual(["no_receipt"]);
	});

	test("tampered receipt refuses as invalid", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		expect(decide({ ...minted, headAfter: shaB }, facts()).verdict).toBe("refuse_invalid_receipt");
	});

	test("wrong repository refuses", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		const otherRepo = facts({ identity: { ...facts().identity, repositoryId: "other", gitCommonDir: "/tmp/other/.git" } });
		expect(decide(minted, otherRepo).verdict).toBe("refuse_wrong_repository");
	});

	test("linked worktree identity mismatch refuses", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		const otherTree = facts({ identity: { ...facts().identity, worktreeId: "other-wt" } });
		expect(decide(minted, otherTree).verdict).toBe("refuse_wrong_repository");
	});

	test("head changed since testing refuses", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		const movedHead = facts({ head: { ...facts().head, sha: shaB } });
		expect(decide(minted, movedHead).verdict).toBe("refuse_head_changed");
	});

	test("self-inconsistent before/after head refuses", () => {
		const minted = mintRepoActionReceipt(receiptInput({ headBefore: shaA, headAfter: shaB }));
		expect(decide(minted, facts()).verdict).toBe("refuse_head_changed");
	});

	test("candidate SHA mismatch refuses", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		const otherSource = facts({ source: { name: "HEAD", sha: shaC, exists: true } });
		expect(decide(minted, otherSource).verdict).toBe("refuse_mismatched_sha");
	});

	test("failed validation refuses", () => {
		const minted = mintRepoActionReceipt(receiptInput({ validation: { command: ["x"], exitCode: 1, passed: 42, failed: 1, durationMs: 10 } }));
		expect(decide(minted, facts()).verdict).toBe("refuse_failed_validation");
	});

	test("reused receipt refuses", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		expect(decide(minted, facts(), { consumed: new Set([minted.digest]) }).verdict).toBe("refuse_reused_receipt");
	});

	test("moved target refuses", () => {
		const minted = mintRepoActionReceipt(receiptInput()); // observedTargetSha = shaB
		const moved = facts({ target: { name: "refs/heads/main", sha: shaC, exists: true } });
		expect(decide(minted, moved).verdict).toBe("refuse_moved_target");
	});

	test("stale receipt refuses past the age window", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		expect(decide(minted, facts(), { now: NOW + DEFAULT_MAX_RECEIPT_AGE_MS + 1 }).verdict).toBe("refuse_stale_receipt");
	});

	test("fresh receipt within window is not stale", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		expect(decide(minted, facts(), { now: NOW + DEFAULT_MAX_RECEIPT_AGE_MS }).verdict).not.toBe("refuse_stale_receipt");
	});

	test("detached head refuses", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		expect(decide(minted, facts({ head: { ...facts().head, detached: true } })).verdict).toBe("refuse_detached_head");
	});

	test("unmerged paths refuse as conflicted", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		const conflicted = facts({ dirt: { tracked: [], untracked: [], unmerged: [{ path: "a.txt", xy: "UU", kind: "unmerged" }] } });
		expect(decide(minted, conflicted).verdict).toBe("refuse_conflicted");
	});

	test("tracked dirt refuses", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		const dirty = facts({ dirt: { tracked: [{ path: "a.txt", xy: "M ", kind: "tracked" }], untracked: [], unmerged: [] } });
		expect(decide(minted, dirty).verdict).toBe("refuse_dirty");
	});

	test("untracked dirt refuses", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		const dirty = facts({ dirt: { tracked: [], untracked: [{ path: "extra.txt", xy: "??", kind: "untracked" }], unmerged: [] } });
		expect(decide(minted, dirty).verdict).toBe("refuse_dirty");
	});

	test("diverged refuses", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		const diverged = facts({ ahead: 1, behind: 1, sourceIsAncestorOfTarget: false, targetIsAncestorOfSource: false, mergeBase: shaB });
		expect(decide(minted, diverged).verdict).toBe("refuse_diverged");
	});

	test("unrelated histories refuse as diverged", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		const unrelated = facts({ ahead: 1, behind: 0, sourceIsAncestorOfTarget: false, targetIsAncestorOfSource: false, mergeBase: null });
		expect(decide(minted, unrelated).verdict).toBe("refuse_diverged");
	});

	test("equal SHAs authorize a no-op", () => {
		const equalFacts = facts({ head: { ...facts().head, sha: shaB }, source: { name: "HEAD", sha: shaB, exists: true }, target: { name: "refs/heads/main", sha: shaB, exists: true }, ahead: 0, behind: 0, mergeBase: shaB, targetIsAncestorOfSource: true, sourceIsAncestorOfTarget: true });
		const minted = mintRepoActionReceipt(receiptInput({ candidateSha: shaB, observedTargetSha: shaB, headBefore: shaB, headAfter: shaB }));
		const decision = decide(minted, equalFacts);
		expect(decision).toMatchObject({ authorize: true, verdict: "authorize_noop", nonForceFastForward: false });
		expect(decision.reasons).toEqual(["equal_shas"]);
	});

	test("source contained in target authorizes a no-op", () => {
		const contained = facts({ ahead: 0, behind: 1, sourceIsAncestorOfTarget: true, targetIsAncestorOfSource: false });
		const minted = mintRepoActionReceipt(receiptInput());
		const decision = decide(minted, contained);
		expect(decision).toMatchObject({ authorize: true, verdict: "authorize_noop", nonForceFastForward: false });
		expect(decision.reasons).toEqual(["source_contained"]);
	});

	test("fast-forward authorizes with nonForceFastForward", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		const decision = decide(minted, facts());
		expect(decision).toMatchObject({ authorize: true, verdict: "authorize_fast_forward", nonForceFastForward: true });
		expect(decision.reasons).toEqual(["fast_forward"]);
		expect(decision.candidateSha).toBe(shaA);
		expect(decision.targetSha).toBe(shaB);
	});

	test("ambiguous clean topology needs a decision", () => {
		const ambiguous = facts({ ahead: 0, behind: 0, sourceIsAncestorOfTarget: false, targetIsAncestorOfSource: false, mergeBase: shaA });
		const minted = mintRepoActionReceipt(receiptInput());
		const decision = decide(minted, ambiguous);
		expect(decision).toMatchObject({ authorize: false, verdict: "needs_decision" });
		expect(decision.reasons).toEqual(["ambiguous_topology"]);
	});

	test("is pure: same input twice yields the same decision", () => {
		const minted = mintRepoActionReceipt(receiptInput());
		const first = decide(minted, facts());
		const second = decide(minted, facts());
		expect(first).toEqual(second);
	});
});
