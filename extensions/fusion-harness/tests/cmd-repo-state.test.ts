import { afterEach, describe, expect, test } from "bun:test";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
	formatRepoStatePanel,
	refreshRepoStateRemote,
	registerRepoStateCommand,
} from "../modules/cmd-repo-state.ts";
import { collectRepoState } from "../modules/repo-state.ts";

const roots: string[] = [];
afterEach(() => {
	while (roots.length) rmSync(roots.pop()!, { recursive: true, force: true });
});

function git(cwd: string, ...args: string[]): string {
	return execFileSync("git", args, {
		cwd,
		encoding: "utf8",
		timeout: 10_000,
		env: { ...process.env, GIT_TERMINAL_PROMPT: "0" },
	}).trim();
}

function repositoryWithAdvancedRemote(): { repo: string; oldSha: string; newSha: string } {
	const root = mkdtempSync(join(tmpdir(), "fh-repo-command-"));
	roots.push(root);
	const bare = join(root, "remote.git");
	const repo = join(root, "repo");
	const updater = join(root, "updater");
	git(root, "init", "--bare", "--initial-branch=main", bare);
	git(root, "init", "--initial-branch=main", repo);
	git(repo, "config", "user.name", "Fixture");
	git(repo, "config", "user.email", "fixture@example.test");
	writeFileSync(join(repo, "state.txt"), "one\n");
	git(repo, "add", "state.txt");
	git(repo, "commit", "-m", "one");
	const oldSha = git(repo, "rev-parse", "HEAD");
	git(repo, "remote", "add", "origin", bare);
	git(repo, "push", "-u", "origin", "main");
	git(root, "clone", bare, updater);
	git(updater, "config", "user.name", "Fixture");
	git(updater, "config", "user.email", "fixture@example.test");
	writeFileSync(join(updater, "state.txt"), "two\n");
	git(updater, "add", "state.txt");
	git(updater, "commit", "-m", "two");
	const newSha = git(updater, "rev-parse", "HEAD");
	git(updater, "push", "origin", "main");
	return { repo, oldSha, newSha };
}

function commandHarness() {
	let handler: ((raw: string, ctx: any) => Promise<void>) | undefined;
	const panels: Array<{ details: any; content: string }> = [];
	const notices: Array<{ message: string; level: string }> = [];
	let hostNotes = 0;
	const pi = {
		registerCommand(name: string, spec: { handler: (raw: string, ctx: any) => Promise<void> }) {
			expect(name).toBe("fh-repo-state");
			handler = spec.handler;
		},
	};
	const harness = {
		noteHost() { hostNotes++; },
		panel(details: any, content: string) { panels.push({ details, content }); },
	};
	registerRepoStateCommand(pi as any, harness as any);
	return {
		panels,
		notices,
		get hostNotes() { return hostNotes; },
		run(raw: string, cwd: string) {
			return handler!(raw, { cwd, ui: { notify(message: string, level: string) { notices.push({ message, level }); } } });
		},
	};
}

describe("/fh-repo-state", () => {
	test("status uses local refs only and displays full exact topology", async () => {
		const { repo, oldSha, newSha } = repositoryWithAdvancedRemote();
		const command = commandHarness();
		await command.run("status", repo);

		expect(command.hostNotes).toBe(1);
		expect(command.panels).toHaveLength(1);
		expect(command.panels[0]!.details).toMatchObject({ kind: "repo-state", command: "fh-repo-state", ok: true, repoRefreshed: false });
		expect(command.panels[0]!.content).toContain("Mode: local refs only; no fetch was run by this command.");
		expect(command.panels[0]!.content).toContain(oldSha);
		expect(command.panels[0]!.content).not.toContain(newSha);
		expect(command.panels[0]!.content).toContain("Ahead: 0; behind: 0.");
		expect(git(repo, "rev-parse", "refs/remotes/origin/main")).toBe(oldSha);
	});

	test("refresh performs one explicit bounded fetch and reports changed tracking refs", async () => {
		const { repo, oldSha, newSha } = repositoryWithAdvancedRemote();
		const command = commandHarness();
		await command.run("refresh origin", repo);

		expect(command.panels).toHaveLength(1);
		expect(command.panels[0]!.details).toMatchObject({ kind: "repo-state", repoRefreshed: true });
		expect(command.panels[0]!.content).toContain("explicit bounded fetch completed for remote `origin`");
		expect(command.panels[0]!.content).toMatch(/Remote-tracking refs changed: [1-9]\d*\./);
		expect(command.panels[0]!.content).toContain("refs/remotes/origin/main");
		expect(command.panels[0]!.content).toContain(oldSha);
		expect(command.panels[0]!.content).toContain(newSha);
		expect(git(repo, "rev-parse", "refs/remotes/origin/main")).toBe(newSha);
	});

	test("refresh helper returns a stable empty change list when refs did not move", async () => {
		const { repo } = repositoryWithAdvancedRemote();
		await refreshRepoStateRemote(repo, "origin");
		const second = await refreshRepoStateRemote(repo, "origin");
		expect(second).toEqual({ remote: "origin", changedRefs: [] });
	});

	test("panel includes verdict, reason codes, all exact refs, dirt, and freshness", async () => {
		const { repo, oldSha } = repositoryWithAdvancedRemote();
		writeFileSync(join(repo, "untracked.txt"), "diagnostic\n");
		const card = await collectRepoState(repo);
		const body = formatRepoStatePanel(card);
		expect(body).toContain("## Repository state: blocked_dirty");
		expect(body).toContain("`dirty_untracked`");
		expect(body).toContain(`| HEAD | \`main\` | \`${oldSha}\` |`);
		expect(body).toContain("Source ancestor of target: yes; target ancestor of source: yes.");
		expect(body).toContain("1 path (0 tracked, 1 untracked, 0 unmerged)");
		expect(body).toContain("`untracked.txt`");
		expect(body).toContain("FETCH_HEAD:");
	});

	test("invalid syntax reports usage without collecting or fetching", async () => {
		const { repo, oldSha } = repositoryWithAdvancedRemote();
		const command = commandHarness();
		await command.run("status unexpected", repo);
		expect(command.panels).toHaveLength(0);
		expect(command.notices).toEqual([{ message: "Usage: /fh-repo-state status | refresh [remote]", level: "warning" }]);
		expect(git(repo, "rev-parse", "refs/remotes/origin/main")).toBe(oldSha);
	});

	test("refresh fails closed for an unknown remote", async () => {
		const { repo, oldSha } = repositoryWithAdvancedRemote();
		const command = commandHarness();
		await command.run("refresh upstream", repo);
		expect(command.panels).toHaveLength(1);
		expect(command.panels[0]!.details).toMatchObject({ kind: "error", ok: false });
		expect(command.panels[0]!.content).toContain("unknown git remote");
		expect(git(repo, "rev-parse", "refs/remotes/origin/main")).toBe(oldSha);
	});
});
