import { afterEach, describe, expect, test } from "bun:test";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { captureLaneRemovalEvidence, cleanLanes, commitLane, createLane, laneBranch, laneDiff, lanePath, laneRootFor, laneStatus, listLanes, removeLane } from "../modules/lanes.ts";

const repos: string[] = [];
const sh = (cwd: string, args: string[]) => execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();

/** A throwaway git repo with one commit. Every lane it creates is cleaned in afterEach. */
function repo(): string {
	const dir = mkdtempSync(join(tmpdir(), "fh-lanes-"));
	repos.push(dir);
	sh(dir, ["init", "-q", "-b", "main"]);
	sh(dir, ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "root"]);
	writeFileSync(join(dir, "a.txt"), "one\n");
	writeFileSync(join(dir, ".gitignore"), "ignored.txt\n");
	sh(dir, ["add", "-A"]);
	sh(dir, ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "a"]);
	return dir;
}

afterEach(async () => {
	while (repos.length) {
		const dir = repos.pop()!;
		try {
			await cleanLanes(dir);
		} catch {}
		rmSync(laneRootFor(dir), { recursive: true, force: true });
		rmSync(dir, { recursive: true, force: true });
	}
});

describe("lanes — one worktree per slot", () => {
	test("refuses a directory that is not a git repository", async () => {
		const dir = mkdtempSync(join(tmpdir(), "fh-lanes-nogit-"));
		repos.push(dir);
		await expect(createLane(dir, "flux")).rejects.toThrow("lanes need a git repository");
	});

	test("creates an isolated worktree on its own branch, outside the repo", async () => {
		const dir = repo();
		const lane = await createLane(dir, "flux");
		expect(lane.branch).toBe(laneBranch(dir, "flux"));
		expect(lane.path).toBe(lanePath(dir, "flux"));
		expect(lane.path.startsWith(dir)).toBe(false);
		expect(lane.carried).toBe(false);
		expect(lane.base).toBe(sh(dir, ["rev-parse", "HEAD"]));
		expect(readFileSync(join(lane.path, "a.txt"), "utf8")).toBe("one\n");
		expect(sh(lane.path, ["rev-parse", "--abbrev-ref", "HEAD"])).toBe(laneBranch(dir, "flux"));
		// The main checkout is untouched: still on main, still clean.
		expect(sh(dir, ["rev-parse", "--abbrev-ref", "HEAD"])).toBe("main");
		expect(sh(dir, ["status", "--porcelain"])).toBe("");
	});

	test("carries the main checkout's uncommitted work as the lane base, not as the slot's delta", async () => {
		const dir = repo();
		writeFileSync(join(dir, "a.txt"), "one\ntwo\n"); // tracked modification
		mkdirSync(join(dir, "src"));
		writeFileSync(join(dir, "src", "new.ts"), "export const x = 1;\n"); // untracked
		writeFileSync(join(dir, "ignored.txt"), "secret\n"); // ignored — must NOT travel
		const lane = await createLane(dir, "drift");
		expect(lane.carried).toBe(true);
		expect(readFileSync(join(lane.path, "a.txt"), "utf8")).toBe("one\ntwo\n");
		expect(readFileSync(join(lane.path, "src", "new.ts"), "utf8")).toBe("export const x = 1;\n");
		expect(existsSync(join(lane.path, "ignored.txt"))).toBe(false);
		expect(lane.base).not.toBe(sh(dir, ["rev-parse", "HEAD"]));
		// Nothing the slot has done yet: base..branch is empty even though HEAD..branch is not.
		const diff = await laneDiff(dir, lane);
		expect(diff.files).toEqual([]);
		// And the main checkout keeps its dirty state exactly as it was.
		expect(readFileSync(join(dir, "a.txt"), "utf8")).toBe("one\ntwo\n");
		expect(sh(dir, ["status", "--porcelain", "--untracked-files=all"])).toContain("src/new.ts");
	});

	test("status, commit, and diff report only what the slot changed", async () => {
		const dir = repo();
		const lane = await createLane(dir, "flux");
		expect(await laneStatus(lane)).toEqual({ files: 0, insertions: 0, deletions: 0 });
		writeFileSync(join(lane.path, "a.txt"), "one\nthree\n");
		writeFileSync(join(lane.path, "b.txt"), "fresh\n");
		const live = await laneStatus(lane);
		expect(live.files).toBe(2);
		expect(live.insertions).toBe(1);
		expect(live.deletions).toBe(0); // b.txt is untracked, so shortstat only sees a.txt
		const commit = await commitLane(lane, "fh lane flux: work");
		expect(commit.committed).toBe(true);
		expect(commit.files.sort()).toEqual(["a.txt", "b.txt"]);
		const diff = await laneDiff(dir, lane);
		expect(diff.files.sort()).toEqual(["a.txt", "b.txt"]);
		expect(diff.patch).toContain("+three");
		expect(diff.patch).toContain("+fresh");
		expect(diff.stat).toContain("2 files changed");
		// A second commit with nothing new is a no-op, not an error.
		expect(await commitLane(lane, "again")).toEqual({ committed: false, files: [] });
	});

	test("recreating a lane resets it to the current HEAD and discards the old branch", async () => {
		const dir = repo();
		const first = await createLane(dir, "flux");
		writeFileSync(join(first.path, "stale.txt"), "old run\n");
		await commitLane(first, "old work");
		const second = await createLane(dir, "flux");
		expect(existsSync(join(second.path, "stale.txt"))).toBe(false);
		expect((await laneDiff(dir, second)).files).toEqual([]);
		expect(sh(dir, ["for-each-ref", "--format=%(refname:short)", "refs/heads/fh/lane/"])).toBe(laneBranch(dir, "flux"));
	});

	test("refuses destructive removal when the lane moved after exact evidence capture", async () => {
		const dir = repo();
		const lane = await createLane(dir, "flux");
		const evidence = await captureLaneRemovalEvidence(dir, "flux");
		writeFileSync(join(lane.path, "moved.txt"), "moved\n");
		await commitLane(lane, "move after evidence");
		await expect(removeLane(dir, evidence)).rejects.toThrow("changed after removal evidence was captured");
		expect(existsSync(lane.path)).toBe(true);
	});

	test("refuses removal when dirty content changes without changing porcelain status", async () => {
		const dir = repo();
		const lane = await createLane(dir, "flux");
		writeFileSync(join(lane.path, "dirty.txt"), "first\n");
		const evidence = await captureLaneRemovalEvidence(dir, "flux");
		writeFileSync(join(lane.path, "dirty.txt"), "second\n");
		await expect(removeLane(dir, evidence)).rejects.toThrow("changed after removal evidence was captured");
		expect(readFileSync(join(lane.path, "dirty.txt"), "utf8")).toBe("second\n");
	});

	test("lists and cleans every lane, including a branch whose worktree vanished", async () => {
		const dir = repo();
		await createLane(dir, "flux");
		await createLane(dir, "drift");
		const listed = (await listLanes(dir)).map((lane) => lane.slotId).sort();
		expect(listed).toEqual(["drift", "flux"]);
		rmSync(lanePath(dir, "drift"), { recursive: true, force: true }); // simulate a manual rm -rf
		const removed = (await cleanLanes(dir)).sort();
		expect(removed).toEqual(["drift", "flux"]);
		expect(await listLanes(dir)).toEqual([]);
		expect(sh(dir, ["for-each-ref", "--format=%(refname:short)", "refs/heads/fh/lane/"])).toBe("");
		expect(existsSync(laneRootFor(dir))).toBe(false);
		expect(laneBranch("/repo", "x")).toMatch(/^fh\/lane\/[0-9a-f]{12}\/x$/);
		expect(laneBranch("/repo", "x")).not.toBe(laneBranch("/repo2", "x"));
	});
});
