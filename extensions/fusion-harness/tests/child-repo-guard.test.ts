import { describe, expect, test } from "bun:test";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import {
	CHILD_GUARD_ACK_ENV,
	CHILD_GUARD_BLOCK_PREFIX,
	CHILD_GUARD_VERSION,
	classifyShellCommand,
	handleToolCallEvent,
	writeGuardAck,
} from "../modules/child-repo-guard.ts";
import childRepoGuard from "../modules/child-repo-guard.ts";

function expectBlocked(command: string, code?: string) {
	const verdict = classifyShellCommand(command);
	expect(verdict.block).toBe(true);
	expect(verdict.reason?.startsWith(CHILD_GUARD_BLOCK_PREFIX)).toBe(true);
	expect(verdict.reason?.toLowerCase()).toContain("receipt");
	if (code) expect(verdict.code).toBe(code);
	return verdict;
}

describe("child-repo-guard: blocked direct git verbs", () => {
	test("publication", () => {
		expectBlocked("git push", "GIT-PUSH");
		expectBlocked("git push origin main", "GIT-PUSH");
		expectBlocked("git push -f origin main", "GIT-PUSH");
		expectBlocked("git push --force origin", "GIT-PUSH");
		expectBlocked("git push --force-with-lease", "GIT-PUSH");
		expectBlocked("git push origin +main:main", "GIT-PUSH");
		expectBlocked("git push --delete old-branch", "GIT-PUSH");
		expectBlocked("git pull", "GIT-PULL");
		expectBlocked("git pull --ff-only origin main", "GIT-PULL");
	});

	test("integration and history rewrite", () => {
		expectBlocked("git merge feature", "GIT-MERGE");
		expectBlocked("git rebase main", "GIT-REBASE");
		expectBlocked("git rebase -i HEAD~3", "GIT-REBASE");
		expectBlocked("git filter-branch --env-filter x", "GIT-HISTORY-REWRITE");
		expectBlocked("git fast-import", "GIT-HISTORY-REWRITE");
		expectBlocked("git update-ref refs/heads/main abc", "GIT-REF-WRITE");
		expectBlocked("git symbolic-ref HEAD refs/heads/other", "GIT-REF-WRITE");
	});

	test("worktree and object destruction", () => {
		expectBlocked("git clean -fd", "GIT-CLEAN");
		expectBlocked("git reset --hard", "GIT-RESET");
		expectBlocked("git reset --hard HEAD~1", "GIT-RESET");
		expectBlocked("git reset --keep origin/main", "GIT-RESET");
		expectBlocked("git reset HEAD~2", "GIT-RESET"); // commit-ish: moves the branch
		expectBlocked("git prune", "GIT-OBJECT-PRUNE");
		expectBlocked("git gc --prune=now", "GIT-OBJECT-PRUNE");
	});

	test("destructive branch and tag deletion", () => {
		expectBlocked("git branch -D topic", "GIT-BRANCH-DELETE");
		expectBlocked("git branch -d topic", "GIT-BRANCH-DELETE"); // fail closed: any deletion
		expectBlocked("git branch --delete topic", "GIT-BRANCH-DELETE");
		expectBlocked("git branch -f main abc", "GIT-BRANCH-DELETE"); // force-moves a ref
		expectBlocked("git tag -d v1.0.0", "GIT-TAG-DELETE");
		expectBlocked("git tag --delete v1", "GIT-TAG-DELETE");
	});

	test("worktree-discard and stash destruction", () => {
		expectBlocked("git checkout -f main", "GIT-CHECKOUT-DISCARD");
		expectBlocked("git checkout -- src/app.ts", "GIT-CHECKOUT-DISCARD");
		expectBlocked("git checkout .", "GIT-CHECKOUT-DISCARD");
		expectBlocked("git restore src/app.ts", "GIT-RESTORE");
		expectBlocked("git restore --worktree src", "GIT-RESTORE");
		expectBlocked("git restore --staged --worktree src", "GIT-RESTORE");
		expectBlocked("git stash drop", "GIT-STASH-DROP");
		expectBlocked("git stash clear", "GIT-STASH-DROP");
	});

	test("parent-owned fetch and repo plumbing", () => {
		expectBlocked("git fetch origin", "GIT-FETCH");
		expectBlocked("git fetch --all", "GIT-FETCH");
		expectBlocked("git fetch origin +refs/heads/*:refs/heads/*", "GIT-FETCH");
		expectBlocked("git fetch origin +main:main", "GIT-FETCH");
		expectBlocked("git remote update", "GIT-FETCH");
		expectBlocked("git remote remove origin", "GIT-REMOTE-REMOVE");
		expectBlocked("git remote rm origin", "GIT-REMOTE-REMOVE");
		expectBlocked("git worktree remove ../wt", "GIT-WORKTREE-REMOVE");
		expectBlocked("git worktree prune", "GIT-WORKTREE-REMOVE");
	});

	test("direct destruction of the .git directory", () => {
		expectBlocked("rm -rf .git", "GIT-DOTGIT-DESTROY");
		expectBlocked("rm .git/config", "GIT-DOTGIT-DESTROY");
		expectBlocked("unlink .git/HEAD", "GIT-DOTGIT-DESTROY");
		expectBlocked("rmdir repo/.git", "GIT-DOTGIT-DESTROY");
	});
});

describe("child-repo-guard: allowed ordinary work", () => {
	const allowed = [
		"",
		"   ",
		"git status",
		"git log --oneline -5",
		"git diff HEAD~1",
		"git show abc123",
		"git add -A",
		"git commit -m 'work'",
		"git commit --amend -m reworded", // local only; the parent receipt binds headBefore/headAfter
		"git branch --list",
		"git branch new-feature",
		"git checkout main",
		"git checkout -b topic",
		"git restore --staged file.ts", // index-only
		"git reset", // bare: unstages
		"git reset -q",
		"git stash",
		"git stash apply",
		"git remote -v",
		"git worktree list",
		"git gc", // no --prune
		"git rm stale-file.ts", // recoverable until commit; documented trade-off
		"ls -la",
		"node --version",
		"cat README.md | grep push", // 'push' is not a git subcommand here
		"echo git push", // echo of words, not a git invocation
		'echo "git push"', // quoted: one argument to echo
		"grep -r 'git push' .",
		"python script.py",
		"just test",
		"bun test extensions/fusion-harness/tests",
	];
	for (const command of allowed) {
		test(`allow: ${command || "(empty)"}`, () => {
			expect(classifyShellCommand(command).block).toBe(false);
		});
	}
});

describe("child-repo-guard: compound and bypass forms", () => {
	test("separators and pipelines", () => {
		expectBlocked("echo hi && git push origin main", "GIT-PUSH");
		expectBlocked("true; git push", "GIT-PUSH");
		expectBlocked("git status || git push", "GIT-PUSH");
		expectBlocked("git push | tee /tmp/out", "GIT-PUSH");
		expectBlocked("cd subdir\ngit reset --hard", "GIT-RESET");
	});

	test("interpreter and eval wrapping", () => {
		expectBlocked("sh -c 'git push origin main'", "GIT-PUSH");
		expectBlocked("bash -c 'git reset --hard'", "GIT-RESET");
		expectBlocked("/bin/sh -c git push", "GIT-PUSH");
		expectBlocked("eval 'git push origin main'", "GIT-PUSH");
	});

	test("shell keywords and grouping do not hide git verbs", () => {
		expectBlocked("if true; then git push origin main; fi", "GIT-PUSH");
		expectBlocked("while x; do git reset --hard; done", "GIT-RESET");
		expectBlocked("for x in a; do git push; done", "GIT-PUSH");
		expectBlocked("{ git push; }", "GIT-PUSH");
		expectBlocked("(git push)", "GIT-PUSH");
		expectBlocked("! git push", "GIT-PUSH");
		expectBlocked("time git push", "GIT-PUSH");
	});

	test("prefix wrappers and shell assignments", () => {
		expectBlocked("command git push", "GIT-PUSH");
		expectBlocked("exec git push", "GIT-PUSH");
		expectBlocked("env git push", "GIT-PUSH");
		expectBlocked("env -i GIT_DIR=$PWD/.git git push", "GIT-PUSH");
		expectBlocked("GIT_DIR=$PWD/.git git push", "GIT-PUSH");
		expectBlocked("then GIT_WORK_TREE=. git reset --hard", "GIT-RESET");
		expectBlocked("nice -n 5 git push", "GIT-PUSH");
		expectBlocked("timeout 10 git push", "GIT-PUSH");
		expectBlocked("sudo git push", "GIT-PUSH");
		expectBlocked("/usr/bin/git push origin main", "GIT-PUSH");
	});

	test("case, spacing, continuation, global git flags", () => {
		expectBlocked("Git Push", "GIT-PUSH"); // case-insensitive: fail closed
		expectBlocked("  git\tpush  ", "GIT-PUSH");
		expectBlocked("git \\\n  push", "GIT-PUSH"); // line continuation
		expectBlocked("git -C .. push origin main", "GIT-PUSH");
		expectBlocked("git --git-dir=.git push", "GIT-PUSH");
		expectBlocked("git --no-pager branch -D x", "GIT-BRANCH-DELETE");
	});

	test("indirect construction", () => {
		expectBlocked("echo run && sh -c 'git push origin main'", "GIT-PUSH");
		expectBlocked("echo $(git push origin main)", "GIT-PUSH");
		expectBlocked("echo `git push`", "GIT-PUSH");
		expectBlocked("echo push | xargs git", "XARGS-GIT");
		expectBlocked("git -c alias.p=push p", "GIT-ALIAS");
	});
});

describe("child-repo-guard: fail-closed ambiguity", () => {
	test("unbalanced quotes mentioning git", () => {
		expectBlocked("echo 'git push", "SHELL-AMBIGUOUS");
	});

	test("unparsable substitution syntax mentioning git", () => {
		expectBlocked("echo $(git push", "SHELL-AMBIGUOUS");
	});

	test("heredoc that could carry a git script", () => {
		expectBlocked("bash <<EOF\ngit push origin main\nEOF", undefined); // direct segment also catches it
		const verdict = classifyShellCommand("sort <<EOF && echo $(basename $(git rev-parse))");
		// inner-most substitution is git rev-parse (allowed), but nested $( + heredoc + git => ambiguous
		expect(verdict.block).toBe(true);
	});

	test("ambiguity without git stays open", () => {
		expect(classifyShellCommand("echo 'unclosed").block).toBe(false);
		expect(classifyShellCommand("cat <<EOF").block).toBe(false);
	});
});

describe("child-repo-guard: tool_call event handling", () => {
	test("blocks a bash git push event with a greppable reason", () => {
		const result = handleToolCallEvent({ toolName: "bash", input: { command: "git push origin main" } });
		expect(result?.block).toBe(true);
		expect(result?.reason?.startsWith(`${CHILD_GUARD_BLOCK_PREFIX}GIT-PUSH`)).toBe(true);
	});

	test("allows ordinary bash and non-shell tools", () => {
		expect(handleToolCallEvent({ toolName: "bash", input: { command: "git status" } })).toBeUndefined();
		expect(handleToolCallEvent({ toolName: "read", input: { path: "x" } })).toBeUndefined();
		expect(handleToolCallEvent({ toolName: "edit", input: {} })).toBeUndefined();
	});

	test("fails closed on malformed shell events", () => {
		const missing = handleToolCallEvent({ toolName: "bash", input: {} });
		expect(missing?.block).toBe(true);
		expect(missing?.reason).toContain("SHELL-AMBIGUOUS");
		const nonString = handleToolCallEvent({ toolName: "bash", input: { command: 42 } });
		expect(nonString?.block).toBe(true);
	});

	test("powershell script field is classified too", () => {
		const result = handleToolCallEvent({ toolName: "powershell", input: { script: "git push" } });
		expect(result?.block).toBe(true);
	});
});

describe("child-repo-guard: load-ack handshake", () => {
	test("no path is a no-op", () => {
		expect(writeGuardAck(undefined)).toBe(false);
	});

	test("writes a parseable ack and overwrites cleanly", () => {
		const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fh-guard-ack-"));
		const ackPath = path.join(dir, "nested", "guard.json");
		expect(writeGuardAck(ackPath, 12345)).toBe(true);
		const first = JSON.parse(fs.readFileSync(ackPath, "utf8"));
		expect(first.guard).toBe("child-repo-guard");
		expect(first.version).toBe(CHILD_GUARD_VERSION);
		expect(first.pid).toBe(12345);
		expect(typeof first.loadedAt).toBe("string");
		expect(writeGuardAck(ackPath, 12346)).toBe(true);
		expect(JSON.parse(fs.readFileSync(ackPath, "utf8")).pid).toBe(12346);
		fs.rmSync(dir, { recursive: true, force: true });
	});

	test("ack env name is stable for the parent", () => {
		expect(CHILD_GUARD_ACK_ENV).toBe("FH_GUARD_ACK");
	});
});

describe("child-repo-guard: factory registration", () => {
	test("registers one tool_call handler, blocks without any UI context", () => {
		const handlers = new Map<string, (event: unknown) => unknown>();
		const fakePi = { on: (name: string, handler: (event: unknown) => unknown) => handlers.set(name, handler) };
		childRepoGuard(fakePi as never);
		const handler = handlers.get("tool_call");
		expect(handler).toBeDefined();
		// ctx is deliberately empty: proves the guard never needs UI
		const blocked = handler?.({ toolName: "bash", input: { command: "git push" } });
		expect((blocked as { block?: boolean } | undefined)?.block).toBe(true);
		const allowed = handler?.({ toolName: "bash", input: { command: "git log -1" } });
		expect(allowed).toBeUndefined();
	});
});

describe("child-repo-guard: Node-safety self-check", () => {
	test("module source contains no Bun-only APIs and no UI calls", () => {
		const source = fs.readFileSync(path.join(import.meta.dir, "..", "modules", "child-repo-guard.ts"), "utf8");
		expect(source.includes("import.meta.dir")).toBe(false);
		expect(source.includes("ctx.ui")).toBe(false);
		expect(source.includes("ui.confirm")).toBe(false);
	});
});
