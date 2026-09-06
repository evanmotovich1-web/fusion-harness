/**
 * repo-action-policy.ts — canonical exact-SHA verification receipts and a pure
 * repository-action authorization policy.
 *
 * Authorizes or refuses. Never executes Git. No filesystem, no processes, no
 * network — only node:crypto, so the module is pure and Node-compatible (it
 * must load under pi's Node runtime, not just Bun).
 *
 * A receipt is single-use evidence: it binds a tested candidate SHA to the
 * repository identity, the common Git directory, the target SHA observed at
 * test time, the validation command that passed, the unchanged before/after
 * HEAD, a timestamp, and a canonical digest over all of those fields.
 *
 * The policy authorizes only:
 *   - equal / no-op (candidate already equals the target), or
 *   - non-force fast-forward (target is an ancestor of the candidate).
 * Everything else refuses, fail closed.
 */

import { createHash } from "node:crypto";
import type { RepoStateFacts } from "./repo-state.ts";

const SHA40_RE = /^[0-9a-f]{40}$/;

export const REPO_ACTION_VERDICTS = [
	"authorize_noop",
	"authorize_fast_forward",
	"refuse_no_receipt",
	"refuse_invalid_receipt",
	"refuse_wrong_repository",
	"refuse_head_changed",
	"refuse_mismatched_sha",
	"refuse_failed_validation",
	"refuse_reused_receipt",
	"refuse_moved_target",
	"refuse_stale_receipt",
	"refuse_detached_head",
	"refuse_conflicted",
	"refuse_dirty",
	"refuse_diverged",
	"needs_decision",
] as const;

export type RepoActionVerdict = (typeof REPO_ACTION_VERDICTS)[number];

/** Validation evidence recorded in a receipt. */
export interface RepoActionValidation {
	/** Exact argv of the validation command (e.g. [".venv/bin/python", "-m", "unittest", …]). */
	command: string[];
	exitCode: number;
	passed: number;
	failed: number;
	durationMs: number;
}

/** Every field the receipt binds, before the digest is attached. */
export interface RepoActionReceiptInput {
	/** `identity.repositoryId` (hash of the common git dir) at test time. */
	repositoryId: string;
	/** Canonical common git directory at test time. */
	gitCommonDir: string;
	/** `identity.worktreeId` (hash of the worktree) at test time. */
	worktreeId: string;
	/** Unique run id — makes same-millisecond receipts distinct and supports single-use tracking. */
	runId: string;
	/** The exact SHA that was validated. */
	candidateSha: string;
	/** The target SHA observed when validation ran. */
	observedTargetSha: string;
	/** HEAD before validation. */
	headBefore: string;
	/** HEAD after validation — must equal `headBefore`. */
	headAfter: string;
	/** Epoch milliseconds when validation completed. */
	issuedAt: number;
	validation: RepoActionValidation;
}

export interface RepoActionReceipt extends RepoActionReceiptInput {
	/** SHA-256 over the canonical serialization of every field above. */
	digest: string;
}

export interface RepoActionDecision {
	authorize: boolean;
	verdict: RepoActionVerdict;
	reasons: string[];
	candidateSha: string | null;
	targetSha: string | null;
	/** True only for `authorize_fast_forward` — the parent may non-force push the candidate. */
	nonForceFastForward: boolean;
}

export const DEFAULT_MAX_RECEIPT_AGE_MS = 2 * 60 * 60 * 1000; // two hours

/** Canonical, byte-stable serialization the digest covers (all fields except digest). */
function canonicalReceiptPayload(input: RepoActionReceiptInput): string {
	return [
		input.repositoryId,
		input.gitCommonDir,
		input.worktreeId,
		input.runId,
		input.candidateSha,
		input.observedTargetSha,
		input.headBefore,
		input.headAfter,
		String(input.issuedAt),
		input.validation.command.join("\u0000"),
		String(input.validation.exitCode),
		String(input.validation.passed),
		String(input.validation.failed),
		String(input.validation.durationMs),
	].join("\n");
}

function digestOf(input: RepoActionReceiptInput): string {
	return createHash("sha256").update(canonicalReceiptPayload(input)).digest("hex");
}

function normalizeSha(value: string, label: string): string {
	const normalized = value.trim().toLowerCase();
	if (!SHA40_RE.test(normalized)) {
		throw new Error(`repo-action-policy: ${label} must be a 40-hex SHA, got ${JSON.stringify(value)}`);
	}
	return normalized;
}

/** Mint a canonical receipt: normalizes SHAs and computes the binding digest. */
export function mintRepoActionReceipt(input: RepoActionReceiptInput): RepoActionReceipt {
	if (!input.runId.trim()) throw new Error("repo-action-policy: runId must be a non-empty string");
	if (!Number.isFinite(input.issuedAt) || input.issuedAt <= 0) throw new Error("repo-action-policy: issuedAt must be a positive epoch milliseconds");
	if (input.validation.command.length === 0) throw new Error("repo-action-policy: validation.command must name at least one argv element");
	const normalized: RepoActionReceiptInput = {
		...input,
		candidateSha: normalizeSha(input.candidateSha, "candidateSha"),
		observedTargetSha: normalizeSha(input.observedTargetSha, "observedTargetSha"),
		headBefore: normalizeSha(input.headBefore, "headBefore"),
		headAfter: normalizeSha(input.headAfter, "headAfter"),
	};
	return { ...normalized, digest: digestOf(normalized) };
}

/** Recompute the digest and compare — tamper detection. */
export function verifyRepoActionReceipt(receipt: RepoActionReceipt): boolean {
	if (!receipt || typeof receipt.digest !== "string" || !/^[0-9a-f]{64}$/.test(receipt.digest)) return false;
	if (![receipt.candidateSha, receipt.observedTargetSha, receipt.headBefore, receipt.headAfter].every((value) => SHA40_RE.test(value))) return false;
	const { digest: _digest, ...fields } = receipt;
	return digestOf(fields) === receipt.digest;
}

export interface AuthorizeRepoActionInput {
	/** The evidence. `null` means no receipt was produced — refuse, never infer. */
	receipt: RepoActionReceipt | null;
	/** Current facts, collected with `targetRef` pointed at the freshly fetched live target. */
	facts: RepoStateFacts;
	/** Digests already consumed; a replayed receipt refuses. Defaults to empty. */
	consumedDigests?: ReadonlySet<string>;
	/** Receipts older than this are stale. Defaults to `DEFAULT_MAX_RECEIPT_AGE_MS`. */
	maxReceiptAgeMs?: number;
	/** Epoch ms to compare against `issuedAt`. Defaults to `Date.now()` (injectable for tests). */
	now?: number;
}

/** Pure: same inputs always produce the same decision. Never executes Git. */
export function authorizeRepoAction(input: AuthorizeRepoActionInput): RepoActionDecision {
	const now = input.now ?? Date.now();
	const maxAge = input.maxReceiptAgeMs ?? DEFAULT_MAX_RECEIPT_AGE_MS;
	const consumed = input.consumedDigests ?? new Set<string>();
	const { facts } = input;
	const receipt = input.receipt;
	const sourceSha = facts.source.sha;
	const targetSha = facts.target.sha;

	const refuse = (verdict: RepoActionVerdict, reason: string): RepoActionDecision => ({
		authorize: false,
		verdict,
		reasons: [reason],
		candidateSha: sourceSha,
		targetSha,
		nonForceFastForward: false,
	});
	const authorize = (verdict: RepoActionVerdict, reason: string, nonForceFastForward: boolean): RepoActionDecision => ({
		authorize: true,
		verdict,
		reasons: [reason],
		candidateSha: sourceSha,
		targetSha,
		nonForceFastForward,
	});

	// ── 1. Evidence integrity: no evidence, tampered evidence, or evidence that
	//    does not bind to THIS repository, THIS checkout, and THIS candidate. ──
	if (!receipt) return refuse("refuse_no_receipt", "no_receipt");
	if (!verifyRepoActionReceipt(receipt)) return refuse("refuse_invalid_receipt", "invalid_receipt");
	if (
		receipt.repositoryId !== facts.identity.repositoryId ||
		receipt.gitCommonDir !== facts.identity.gitCommonDir ||
		receipt.worktreeId !== facts.identity.worktreeId
	) {
		return refuse("refuse_wrong_repository", "wrong_repository");
	}
	if (receipt.headBefore !== receipt.headAfter || receipt.headAfter !== facts.head.sha) {
		return refuse("refuse_head_changed", "head_changed");
	}
	if (receipt.candidateSha !== sourceSha) return refuse("refuse_mismatched_sha", "mismatched_sha");
	if (receipt.validation.exitCode !== 0 || receipt.validation.failed !== 0) {
		return refuse("refuse_failed_validation", "failed_validation");
	}
	if (consumed.has(receipt.digest)) return refuse("refuse_reused_receipt", "reused_receipt");
	if (receipt.observedTargetSha !== targetSha) return refuse("refuse_moved_target", "moved_target");
	if (now - receipt.issuedAt > maxAge) return refuse("refuse_stale_receipt", "stale_receipt");

	// ── 2. Current working-tree and topology state: a valid receipt for the right
	//    SHA still cannot authorize a dirty, conflicted, detached, or divergent tree. ──
	if (facts.head.detached) return refuse("refuse_detached_head", "detached_head");
	if (facts.dirt.unmerged.length > 0) return refuse("refuse_conflicted", "conflicted");
	if (facts.dirt.tracked.length > 0 || facts.dirt.untracked.length > 0) return refuse("refuse_dirty", "dirty");
	if (sourceSha && targetSha && sourceSha !== targetSha) {
		const diverged = (facts.ahead ?? 0) > 0 && (facts.behind ?? 0) > 0;
		const unrelated = facts.mergeBase === null;
		if (diverged || unrelated) return refuse("refuse_diverged", "diverged");
	}

	// ── 3. Authorization: only equal/no-op or non-force fast-forward. ──
	if (sourceSha && targetSha && sourceSha === targetSha) {
		return authorize("authorize_noop", "equal_shas", false);
	}
	if (facts.sourceIsAncestorOfTarget === true && sourceSha && targetSha) {
		return authorize("authorize_noop", "source_contained", false);
	}
	if (
		facts.targetIsAncestorOfSource === true &&
		sourceSha &&
		targetSha &&
		(facts.behind ?? 0) === 0 &&
		(facts.ahead ?? 0) > 0
	) {
		return authorize("authorize_fast_forward", "fast_forward", true);
	}

	// No deterministic authorization and no concrete refusal — genuine ambiguity.
	return {
		authorize: false,
		verdict: "needs_decision",
		reasons: ["ambiguous_topology"],
		candidateSha: sourceSha,
		targetSha,
		nonForceFastForward: false,
	};
}
