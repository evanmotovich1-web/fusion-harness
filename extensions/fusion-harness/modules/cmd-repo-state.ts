/**
 * cmd-repo-state.ts — deterministic /fh-repo-state status | refresh [remote].
 *
 * Status is strictly local and read-only. Refresh is the one explicit network and
 * remote-tracking-ref mutation in this command; it is bounded and reports every
 * changed remote-tracking ref before collecting a new local state card.
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { collectRepoState, type RepoStateCard } from "./repo-state.ts";
import type { HarnessDeps } from "./runtime.ts";
import { acquireWriterLease, type WriterLease } from "./writer-lease.ts";

const execFileAsync = promisify(execFile);
const FETCH_TIMEOUT_MS = 30_000;
const MAX_DIRT_ROWS = 50;
const SHA_RE = /^[0-9a-f]{40}$/i;

interface GitOutput {
	stdout: string;
	stderr: string;
}

export interface RemoteRefChange {
	ref: string;
	before: string | null;
	after: string | null;
}

export interface RepoStateRefresh {
	remote: string;
	changedRefs: RemoteRefChange[];
}

export interface RepoStatePanelOptions {
	refresh?: RepoStateRefresh;
}

async function git(cwd: string, args: string[]): Promise<GitOutput> {
	try {
		const result = await execFileAsync("git", args, {
			cwd,
			timeout: FETCH_TIMEOUT_MS,
			maxBuffer: 8 * 1024 * 1024,
			env: { ...process.env, GIT_TERMINAL_PROMPT: "0", GIT_OPTIONAL_LOCKS: "0" },
		});
		return { stdout: String(result.stdout ?? "").trim(), stderr: String(result.stderr ?? "").trim() };
	} catch (error: any) {
		if (error?.code === "ENOENT") throw new Error("git executable not found");
		if (error?.killed || error?.signal) throw new Error(`git ${args[0] ?? "command"} timed out after ${FETCH_TIMEOUT_MS / 1000}s`);
		const detail = String(error?.stderr ?? error?.stdout ?? error?.message ?? error).trim();
		throw new Error(`git ${args[0] ?? "command"} failed${detail ? `: ${detail}` : ""}`);
	}
}

async function remoteNames(cwd: string): Promise<string[]> {
	const result = await git(cwd, ["remote"]);
	return result.stdout.split("\n").map((name) => name.trim()).filter(Boolean).sort();
}

async function remoteRefs(cwd: string): Promise<Map<string, string>> {
	const result = await git(cwd, ["for-each-ref", "--format=%(refname)%00%(objectname)", "refs/remotes"]);
	const refs = new Map<string, string>();
	for (const line of result.stdout.split("\n")) {
		if (!line) continue;
		const [ref, sha] = line.split("\0");
		if (ref && sha && SHA_RE.test(sha)) refs.set(ref, sha.toLowerCase());
	}
	return refs;
}

function chooseRemote(remotes: string[], requested?: string): string {
	if (requested) {
		if (!remotes.includes(requested)) throw new Error(`unknown git remote ${JSON.stringify(requested)}; available: ${remotes.join(", ") || "none"}`);
		return requested;
	}
	if (remotes.includes("origin")) return "origin";
	if (remotes.length === 1) return remotes[0]!;
	if (!remotes.length) throw new Error("repository has no git remote to refresh");
	throw new Error(`multiple git remotes exist; choose one: /fh-repo-state refresh <${remotes.join("|")}>`);
}

/** Explicit, bounded fetch. No prune, tags, submodules, shell, or implicit remote choice. */
export async function refreshRepoStateRemote(cwd: string, requestedRemote?: string): Promise<RepoStateRefresh> {
	const remotes = await remoteNames(cwd);
	const remote = chooseRemote(remotes, requestedRemote?.trim() || undefined);
	const before = await remoteRefs(cwd);
	await git(cwd, ["fetch", "--no-tags", "--no-recurse-submodules", remote]);
	const after = await remoteRefs(cwd);
	const changedRefs: RemoteRefChange[] = [];
	for (const ref of [...new Set([...before.keys(), ...after.keys()])].sort()) {
		const oldSha = before.get(ref) ?? null;
		const newSha = after.get(ref) ?? null;
		if (oldSha !== newSha) changedRefs.push({ ref, before: oldSha, after: newSha });
	}
	return { remote, changedRefs };
}

function cell(value: string): string {
	return value.replace(/\|/g, "\\|").replace(/[\r\n]+/g, " ");
}

function sha(value: string | null): string {
	return value ?? "(missing)";
}

function bool(value: boolean | null): string {
	return value === null ? "unknown" : value ? "yes" : "no";
}

function formatDirt(card: RepoStateCard): string[] {
	const dirt = [...card.dirt.unmerged, ...card.dirt.tracked, ...card.dirt.untracked];
	if (!dirt.length) return ["Dirt: clean"];
	const shown = dirt.slice(0, MAX_DIRT_ROWS);
	return [
		`Dirt: ${dirt.length} path${dirt.length === 1 ? "" : "s"} (${card.dirt.tracked.length} tracked, ${card.dirt.untracked.length} untracked, ${card.dirt.unmerged.length} unmerged)`,
		"",
		"| kind | XY | path |",
		"|---|---|---|",
		...shown.map((entry) => `| ${entry.kind} | \`${cell(entry.xy)}\` | \`${cell(entry.path)}\` |`),
		...(dirt.length > shown.length ? [`| … | … | ${dirt.length - shown.length} more paths omitted |`] : []),
	];
}

function formatRefresh(refresh: RepoStateRefresh | undefined): string[] {
	if (!refresh) return ["Mode: local refs only; no fetch was run by this command."];
	const rows = refresh.changedRefs.length
		? [
			"",
			"| changed remote-tracking ref | before | after |",
			"|---|---|---|",
			...refresh.changedRefs.map((change) => `| \`${cell(change.ref)}\` | \`${sha(change.before)}\` | \`${sha(change.after)}\` |`),
		]
		: ["", "Remote-tracking refs changed: none."];
	return [
		`Mode: explicit bounded fetch completed for remote \`${cell(refresh.remote)}\`.`,
		`Remote-tracking refs changed: ${refresh.changedRefs.length}.`,
		...rows,
	];
}

/** Stable markdown body used by the command and integration tests. */
export function formatRepoStatePanel(card: RepoStateCard, options: RepoStatePanelOptions = {}): string {
	const fetchHead = card.freshness.fetchHeadExists
		? `present${card.freshness.fetchHeadMtimeMs === null ? "" : `; mtime ${new Date(card.freshness.fetchHeadMtimeMs).toISOString()}`}`
		: "absent";
	return [
		`## Repository state: ${card.verdict}`,
		`Reason codes: ${card.reasonCodes.length ? card.reasonCodes.map((reason) => `\`${reason}\``).join(", ") : "none"}`,
		`Card hash: \`${card.hash}\``,
		"",
		"### Exact refs",
		"| fact | ref | SHA |",
		"|---|---|---|",
		`| HEAD | ${card.head.branch ? `\`${cell(card.head.branch)}\`` : card.head.detached ? "detached" : "unborn"} | \`${sha(card.head.sha)}\` |`,
		`| source | \`${cell(card.source.name)}\` | \`${sha(card.source.sha)}\` |`,
		`| target | \`${cell(card.target.name)}\` | \`${sha(card.target.sha)}\` |`,
		`| upstream | ${card.upstream.ref ? `\`${cell(card.upstream.ref)}\`` : "(none)"} | \`${sha(card.upstream.sha)}\` |`,
		`| merge-base | — | \`${sha(card.mergeBase)}\` |`,
		"",
		"### Topology",
		`Ahead: ${card.ahead ?? "unknown"}; behind: ${card.behind ?? "unknown"}.`,
		`Source ancestor of target: ${bool(card.sourceIsAncestorOfTarget)}; target ancestor of source: ${bool(card.targetIsAncestorOfSource)}.`,
		`Detached HEAD: ${card.head.detached ? "yes" : "no"}; unborn HEAD: ${card.head.unborn ? "yes" : "no"}; linked worktree: ${card.identity.isLinkedWorktree ? "yes" : "no"}.`,
		"",
		"### Working tree",
		...formatDirt(card),
		"",
		"### Freshness",
		...formatRefresh(options.refresh),
		`Known remotes: ${card.freshness.remotes.length ? card.freshness.remotes.map((remote) => `\`${cell(remote)}\``).join(", ") : "none"}.`,
		`FETCH_HEAD: ${fetchHead}.`,
		"",
		`Repository: \`${cell(card.identity.worktree)}\``,
		`Git common directory: \`${cell(card.identity.gitCommonDir)}\``,
	].join("\n");
}

export function registerRepoStateCommand(pi: ExtensionAPI, h: HarnessDeps): void {
	pi.registerCommand("fh-repo-state", {
		description: "Show deterministic local Git state, or explicitly refresh one remote before showing it: status | refresh [remote].",
		handler: async (raw, ctx) => {
			h.noteHost(ctx);
			const args = (raw ?? "").trim().split(/\s+/).filter(Boolean);
			const action = (args.shift() ?? "status").toLowerCase();
			if ((action !== "status" && action !== "refresh") || (action === "status" && args.length) || args.length > 1) {
				ctx.ui.notify("Usage: /fh-repo-state status | refresh [remote]", "warning");
				return;
			}
			let writerLease: WriterLease | undefined;
			try {
				// Status never takes the writer token. Refresh updates remote-tracking
				// refs, so keep its fetch and resulting card inside one checkout lease.
				if (action === "refresh") writerLease = acquireWriterLease(ctx.cwd, "/fh-repo-state refresh");
				const refresh = action === "refresh" ? await refreshRepoStateRemote(ctx.cwd, args[0]) : undefined;
				const card = await collectRepoState(ctx.cwd);
				h.panel(
					{
						kind: "repo-state",
						command: "fh-repo-state",
						ok: true,
						repoVerdict: card.verdict,
						repoRefreshed: Boolean(refresh),
					},
					formatRepoStatePanel(card, { refresh }),
				);
			} catch (error) {
				h.panel(
					{ kind: "error", command: "fh-repo-state", ok: false },
					`Repository state failed: ${error instanceof Error ? error.message : String(error)}`,
				);
			} finally {
				writerLease?.release();
			}
		},
	});
}
