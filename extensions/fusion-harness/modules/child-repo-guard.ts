/**
 * child-repo-guard.ts — deterministic delegated-git-action guard for clean-room children.
 *
 * Loaded explicitly by the parent (`pi --no-extensions -e <abs path>` — the
 * documented additive combination) so the child stays clean-room while still
 * carrying this one interception layer. Children run headless (JSON/print mode
 * have no UI), so the guard NEVER prompts: it blocks deterministically and the
 * stable `CHILD-GUARD:*` reason code is the entire communication channel.
 *
 * Blocked by classification, anywhere the command reaches: direct git
 * publication/history/deletion verbs, compound `&&`/`;`/`||`/pipe forms,
 * `sh -c` / `eval` wrapped payloads, `$(...)` and backtick substitutions,
 * `env`/`timeout`/`sudo`/`command`/`exec` prefixes, xargs-constructed git,
 * inline `git -c alias.*=` tricks, and `rm` against `.git` paths. Ambiguous
 * shell text that mentions git fails closed.
 *
 * Boundary honesty: this is a command classifier, NOT an OS sandbox. It cannot
 * see shell aliases, git config aliases outside the command text, or writes
 * made through other tools (e.g. the write tool). Its job is making delegated
 * repository mutations impossible-by-default; publication itself is
 * parent-owned under the writer lease and requires an exact-SHA harness
 * receipt. An agent-issued claim is never a receipt.
 *
 * Node-safe: runs under pi's Node runtime via jiti. No Bun-only APIs and no
 * Bun-only module-path globals (the source self-check enforces this). Only
 * node:fs (ack file) plus type-only pi imports. A guard
 * handler that throws still blocks (pi fails tool_call errors safe); the
 * factory also writes a load-ack file so the parent can prove the guard is
 * actually present (a module that fails to load leaves pi running unguarded).
 */

import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export const CHILD_GUARD_VERSION = 1;
export const CHILD_GUARD_ACK_ENV = "FH_GUARD_ACK";
export const CHILD_GUARD_BLOCK_PREFIX = "CHILD-GUARD:";

export interface ShellVerdict {
	block: boolean;
	code?: string;
	detail?: string;
	reason?: string;
}

const ALLOW: ShellVerdict = { block: false };

/** git subcommands a delegated child may never run, in any form. */
const BLOCKED_SUBCOMMANDS = new Set([
	"push", // publication is parent-owned; receipt required
	"fetch", // remote refresh is explicit, bounded, leased, and parent-owned
	"pull", // fetch+merge/rebase integration
	"merge",
	"rebase",
	"clean", // destroys untracked work
	"filter-branch", // history rewrite
	"fast-import", // history rewrite
	"update-ref", // raw ref writes
	"symbolic-ref", // moves HEAD
	"prune", // destroys unreachable objects
]);

const CODE_BY_SUBCOMMAND: Record<string, string> = {
	push: "GIT-PUSH",
	fetch: "GIT-FETCH",
	pull: "GIT-PULL",
	merge: "GIT-MERGE",
	rebase: "GIT-REBASE",
	clean: "GIT-CLEAN",
	"filter-branch": "GIT-HISTORY-REWRITE",
	"fast-import": "GIT-HISTORY-REWRITE",
	"update-ref": "GIT-REF-WRITE",
	"symbolic-ref": "GIT-REF-WRITE",
	prune: "GIT-OBJECT-PRUNE",
};

const SHELL_WRAPPERS = new Set(["sh", "bash", "zsh", "dash", "ksh", "ash", "fish"]);
const PREFIX_WRAPPERS = new Set(["command", "exec", "builtin", "nice", "nohup", "stdbuf", "sudo", "env", "timeout"]);
/** Heads that are not commands; skip them so `then git push` / `{ git push; }` still classify. */
const SHELL_KEYWORDS = new Set([
	"if", "then", "else", "elif", "fi", "while", "until", "do", "done", "for", "in",
	"case", "esac", "select", "time", "coproc", "function", "!", "{", "}",
]);

function reasonFor(code: string, detail: string): ShellVerdict {
	return {
		block: true,
		code,
		detail,
		reason:
			`${CHILD_GUARD_BLOCK_PREFIX}${code} — ${detail}. ` +
			"Delegated publication and destructive repository actions are parent-owned: " +
			"report the intent instead; an agent-issued claim is not a harness receipt.",
	};
}

function basename(token: string): string {
	const clean = token.replace(/\\/g, "/"); // tolerate windows-style paths
	const base = clean.slice(clean.lastIndexOf("/") + 1);
	return base.toLowerCase().replace(/\.exe$/, "");
}

function peelGrouping(token: string): string {
	return token.replace(/^[(){};!]+/, "").replace(/[(){};]+$/, "");
}

function isGitToken(token: string): boolean {
	const base = basename(peelGrouping(token));
	return base === "git";
}

function stripQuotes(token: string): string {
	if (token.length >= 2) {
		if ((token.startsWith('"') && token.endsWith('"')) || (token.startsWith("'") && token.endsWith("'"))) {
			return token.slice(1, -1);
		}
	}
	return token;
}

function quotesBalanced(text: string): boolean {
	let single = 0;
	let double = 0;
	for (let i = 0; i < text.length; i++) {
		const ch = text[i];
		if (ch === "\\") {
			i++; // skip escaped character
			continue;
		}
		if (ch === "'") single++;
		else if (ch === '"') double++;
	}
	return single % 2 === 0 && double % 2 === 0;
}

function tokenize(segment: string): string[] {
	// Quote-aware split: a quoted string is ONE token with its quotes removed,
	// so `sh -c 'git push'` yields the payload as a single argument and the
	// wrapper recursion sees the command the shell would actually run.
	const tokens: string[] = [];
	let current = "";
	let quote: string | null = null;
	let hasToken = false;
	const push = () => {
		if (hasToken) {
			tokens.push(current);
			current = "";
			hasToken = false;
		}
	};
	for (let i = 0; i < segment.length; i++) {
		const ch = segment[i];
		if (quote) {
			if (ch === quote) quote = null;
			else if (ch === "\\" && quote === '"') {
				current += segment[i + 1] ?? "";
				i++;
			} else current += ch;
			hasToken = true;
			continue;
		}
		if (ch === "'" || ch === '"') {
			quote = ch;
			hasToken = true;
			continue;
		}
		if (ch === "\\") {
			current += segment[i + 1] ?? "";
			i++;
			hasToken = true;
			continue;
		}
		if (/\s/.test(ch)) {
			push();
			continue;
		}
		current += ch;
		hasToken = true;
	}
	push();
	return tokens.filter((t) => t.length > 0);
}

/**
 * Pull `$(...)` and backtick payloads out of the command. Each payload is
 * classified recursively; the remainder is what the outer shell would still
 * see. Returns ambiguous=true when the substitution syntax itself cannot be
 * parsed confidently (unbalanced parens or an odd number of backticks).
 */
function extractSubstitutions(command: string): { payloads: string[]; remainder: string; ambiguous: boolean } {
	const payloads: string[] = [];
	let remainder = command;
	let backticks = 0;
	for (const ch of remainder) if (ch === "`") backticks++;
	if (backticks % 2 === 1) return { payloads, remainder, ambiguous: true };
	remainder = remainder.replace(/`([^`]*)`/g, (_m, inner: string) => {
		payloads.push(String(inner));
		return " substituted ";
	});
	// Unwrap $( ...) repeatedly so nested substitutions each get extracted.
	for (let pass = 0; pass < 8; pass++) {
		const next = remainder.replace(/\$\(([^()]*)\)/g, (_m, inner: string) => {
			payloads.push(String(inner));
			return " substituted ";
		});
		if (next === remainder) break;
		remainder = next;
	}
	if (remainder.includes("$(")) return { payloads, remainder, ambiguous: true };
	return { payloads, remainder, ambiguous: false };
}

/** Classify one unwrapped token stream as a git invocation (or not). */
function classifyGitInvocation(tokens: string[]): ShellVerdict {
	// Skip global git flags before the subcommand; -C/-c and bare
	// --git-dir/--work-tree/--exec-path consume a following value token.
	let i = 1;
	while (i < tokens.length) {
		const token = tokens[i];
		if (token === "-C" || token === "-c" || token === "--git-dir" || token === "--work-tree" || token === "--exec-path") {
			const value = tokens[i + 1] ?? "";
			if (token === "-c" && /^alias\./i.test(value)) {
				return reasonFor("GIT-ALIAS", `inline git alias definition '${value}' could hide a blocked verb`);
			}
			i += 2;
			continue;
		}
		if (token.startsWith("-")) {
			i += 1;
			continue;
		}
		break;
	}
	const subcommand = (tokens[i] ?? "").toLowerCase();
	const args = tokens.slice(i + 1);
	if (!subcommand) return ALLOW; // bare `git` — prints help, harmless

	if (BLOCKED_SUBCOMMANDS.has(subcommand)) {
		return reasonFor(CODE_BY_SUBCOMMAND[subcommand] ?? "GIT-BLOCKED", `git ${subcommand}`);
	}
	const hasFlag = (...flags: string[]) => args.some((a) => flags.includes(a));
	const hasNonFlag = () => args.some((a) => !a.startsWith("-"));

	switch (subcommand) {
		case "reset":
			// Bare reset (unstage) is safe; any commit-ish or hard/keep/merge mode
			// moves or discards state — parent-owned.
			if (hasFlag("--hard", "--keep", "--merge") || hasNonFlag()) {
				return reasonFor("GIT-RESET", `git reset ${args.join(" ")}`.trim());
			}
			return ALLOW;
		case "branch":
			if (hasFlag("-d", "-D", "--delete", "-f", "--force")) {
				return reasonFor("GIT-BRANCH-DELETE", `git branch ${args.join(" ")}`);
			}
			return ALLOW;
		case "tag":
			if (hasFlag("-d", "-D", "--delete")) {
				return reasonFor("GIT-TAG-DELETE", `git tag ${args.join(" ")}`);
			}
			return ALLOW;
		case "checkout":
			if (hasFlag("-f", "--force") || args.includes("--") || args.includes(".")) {
				return reasonFor("GIT-CHECKOUT-DISCARD", `git checkout ${args.join(" ")}`);
			}
			return ALLOW;
		case "restore":
			// Index-only restore is safe; anything touching the worktree discards changes.
			if (args.includes("--staged") && !hasFlag("-W", "--worktree", "-s", "--source")) return ALLOW;
			return reasonFor("GIT-RESTORE", `git restore ${args.join(" ")}`);
		case "stash":
			if (["drop", "clear"].includes((args[0] ?? "").toLowerCase())) {
				return reasonFor("GIT-STASH-DROP", `git stash ${args.join(" ")}`);
			}
			return ALLOW;
		case "remote":
			if (["remove", "rm"].includes((args[0] ?? "").toLowerCase())) {
				return reasonFor("GIT-REMOTE-REMOVE", `git remote ${args.join(" ")}`);
			}
			if ((args[0] ?? "").toLowerCase() === "update") {
				return reasonFor("GIT-FETCH", `git remote ${args.join(" ")}`);
			}
			return ALLOW;
		case "worktree":
			if (["remove", "prune"].includes((args[0] ?? "").toLowerCase())) {
				return reasonFor("GIT-WORKTREE-REMOVE", `git worktree ${args.join(" ")}`);
			}
			return ALLOW;
		case "gc":
			if (args.some((a) => a.startsWith("--prune"))) {
				return reasonFor("GIT-OBJECT-PRUNE", `git gc ${args.join(" ")}`);
			}
			return ALLOW;
		default:
			return ALLOW;
	}
}

function classifyRmInvocation(tokens: string[]): ShellVerdict {
	const base = basename(tokens[0] ?? "");
	if (base !== "rm" && base !== "unlink" && base !== "rmdir") return ALLOW;
	const touchesDotGit = tokens.slice(1).some((arg) => {
		const bare = stripQuotes(arg);
		return /^\.git(\/|$)/.test(bare) || /(^|\/)\.git(\/|$)/.test(bare);
	});
	if (touchesDotGit) {
		return reasonFor("GIT-DOTGIT-DESTROY", `${tokens[0]} targeting .git`);
	}
	return ALLOW;
}

/**
 * Classify a single shell segment (already free of separators and
 * substitutions): unwrap prefix wrappers, recurse into `sh -c`/`eval`
 * payloads, then hand git / rm invocations to their classifiers.
 */
function classifySegment(segment: string): ShellVerdict {
	let tokens = tokenize(segment).map(peelGrouping).filter(Boolean);
	if (tokens.length === 0) return ALLOW;
	let skippedKeyword = false;
	while (tokens.length > 0 && SHELL_KEYWORDS.has(tokens[0]!.toLowerCase())) {
		skippedKeyword = true;
		tokens = tokens.slice(1);
	}
	// POSIX shells allow assignment prefixes without `env`: `A=1 git push`.
	// Strip only leading NAME=value words, then classify the actual command.
	while (tokens.length > 0 && /^[A-Za-z_][A-Za-z0-9_]*=/.test(tokens[0]!)) tokens = tokens.slice(1);
	if (tokens.length === 0) return ALLOW;
	if (skippedKeyword) {
		const gitAt = tokens.findIndex((token) => isGitToken(token));
		if (gitAt >= 0) tokens = tokens.slice(gitAt);
	}

	// Unwrap `sh -c '<payload>'`, `eval '<payload>'`, and prefix wrappers.
	for (let hop = 0; hop < 8; hop++) {
		const head = basename(tokens[0] ?? "");
		if (SHELL_WRAPPERS.has(head)) {
			const cIndex = tokens.findIndex((t, idx) => idx > 0 && t === "-c");
			if (cIndex !== -1) {
				const payload = tokens.slice(cIndex + 1).join(" ");
				return payload ? classifyShellCommand(payload) : ALLOW;
			}
			return ALLOW; // shell without -c runs a script file; cannot see inside
		}
		if (head === "eval") {
			const payload = tokens.slice(1).join(" ");
			return payload ? classifyShellCommand(payload) : ALLOW;
		}
		if (PREFIX_WRAPPERS.has(head)) {
			const wrapperName = head;
			tokens = tokens.slice(1);
			// Skip wrapper flag/value arguments until the real command appears.
			while (tokens.length > 0) {
				const t = tokens[0];
				if (wrapperName === "timeout" && /^\d+(\.\d+)?[smhd]?$/i.test(t)) {
					tokens = tokens.slice(1); // timeout's duration argument
					continue;
				}
				if (/^[A-Za-z_][A-Za-z0-9_]*=/.test(t)) {
					tokens = tokens.slice(1);
					continue;
				}
				if (t === "-u" || t === "-n" || t === "-o" || t === "-p") {
					tokens = tokens.slice(2); // flag + value
					continue;
				}
				if (t.startsWith("-")) {
					tokens = tokens.slice(1);
					continue;
				}
				break;
			}
			continue;
		}
		break;
	}
	if (tokens.length === 0) return ALLOW;

	if (isGitToken(tokens[0])) return classifyGitInvocation(tokens.map((t) => t.toLowerCase()));
	return classifyRmInvocation(tokens);
}

/**
 * Pure, deterministic shell-command classifier. No filesystem, no environment,
 * no UI. False positives are acceptable; false negatives on git
 * publication/history/deletion verbs are not. Ambiguous shell text that
 * mentions git fails closed.
 */
export function classifyShellCommand(raw: string): ShellVerdict {
	if (typeof raw !== "string" || raw.trim().length === 0) return ALLOW;
	const command = raw.replace(/\\\r?\n/g, " ");

	const { payloads, remainder, ambiguous } = extractSubstitutions(command);
	const mentionsGit = /\bgit\b/i.test(remainder) || payloads.some((p) => /\bgit\b/i.test(p)) || remainder.includes(".git");

	if (ambiguous && mentionsGit) {
		return reasonFor("SHELL-AMBIGUOUS", "unparsable substitution syntax in a command that mentions git");
	}
	if (!quotesBalanced(remainder) && mentionsGit) {
		return reasonFor("SHELL-AMBIGUOUS", "unbalanced quoting in a command that mentions git");
	}
	if (/<<-?\s*\S/.test(remainder) && mentionsGit) {
		// Heredoc bodies can be scripts (bash <<EOF ... git push ... EOF) — fail closed.
		return reasonFor("SHELL-AMBIGUOUS", "heredoc in a command that mentions git");
	}

	// Classify substitution payloads recursively (echo $(git push) still pushes).
	for (const payload of payloads) {
		const verdict = classifyShellCommand(payload);
		if (verdict.block) return verdict;
	}

	// Split compound commands, then pipelines, then classify each segment.
	const segments = remainder
		.replace(/&&/g, "\n")
		.replace(/\|\|/g, "\n")
		.split(/[\n;]+/)
		.flatMap((segment) => segment.split("|"));

	const sawTokens: string[] = [];
	let sawXargs = false;
	for (const segment of segments) {
		const tokens = tokenize(segment);
		if (tokens.length === 0) continue;
		if (tokens.some((t) => basename(t) === "xargs")) sawXargs = true;
		sawTokens.push(...tokens);
		const verdict = classifySegment(segment);
		if (verdict.block) return verdict;
	}
	// xargs can synthesize a git invocation the tokenizer never saw assembled.
	if (sawXargs && sawTokens.some((t) => isGitToken(t))) {
		return reasonFor("XARGS-GIT", "xargs combined with git can synthesize a blocked invocation");
	}
	return ALLOW;
}

/**
 * Handle one pi tool_call event for the bash/powershell tools. Pure decision
 * function: returns a block directive or undefined to allow. Never touches UI.
 */
export function handleToolCallEvent(event: unknown): { block: boolean; reason?: string } | undefined {
	try {
		const evt = (event ?? {}) as { toolName?: unknown; input?: unknown };
		const name = typeof evt.toolName === "string" ? evt.toolName.toLowerCase() : "";
		if (name !== "bash" && name !== "powershell") return undefined;
		const input = (evt.input ?? {}) as { command?: unknown; script?: unknown };
		const command = input.command ?? input.script;
		if (typeof command !== "string") {
			const verdict = reasonFor("SHELL-AMBIGUOUS", "shell tool call without a string command");
			return { block: true, reason: verdict.reason };
		}
		const verdict = classifyShellCommand(command);
		if (verdict.block) return { block: true, reason: verdict.reason };
		return undefined;
	} catch {
		// pi already fails tool_call handler errors safe (the call is blocked);
		// returning the block ourselves keeps the guarantee explicit.
		return { block: true, reason: `${CHILD_GUARD_BLOCK_PREFIX}SHELL-AMBIGUOUS — guard internal error; failing closed.` };
	}
}

/**
 * Write the factory-scope load-ack so the parent can prove this guard is
 * actually loaded (a module that fails to load leaves pi running unguarded —
 * fail-open at load time is the one hole the handshake closes). A single
 * synchronous write is factory-legal; no background resources are started.
 */
export function writeGuardAck(ackPath: string | undefined, pid: number = 0): boolean {
	if (!ackPath) return false;
	try {
		fs.mkdirSync(path.dirname(ackPath), { recursive: true });
		fs.writeFileSync(
			ackPath,
			JSON.stringify({ guard: "child-repo-guard", version: CHILD_GUARD_VERSION, pid, loadedAt: new Date().toISOString() }) + "\n",
		);
		return true;
	} catch {
		return false; // parent detects the missing ack and treats the child as unguarded
	}
}

/**
 * Extension factory. Registered into the child by the parent via
 * `pi --no-extensions -e <absolute path>`; never auto-discovered.
 */
export default function childRepoGuard(pi: ExtensionAPI): void {
	writeGuardAck(process.env?.[CHILD_GUARD_ACK_ENV], typeof process !== "undefined" ? process.pid : 0);
	pi.on("tool_call", (event) => handleToolCallEvent(event));
}
