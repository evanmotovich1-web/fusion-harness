/**
 * Every relative import in committed harness code must resolve to a file git
 * tracks. PR #10 once committed an import of an untracked work-in-progress
 * module: tests passed in the dirty checkout, but every clean checkout failed
 * to load the extension.
 */
import { describe, expect, test } from "bun:test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join, normalize, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "../../..");
let tracked: Set<string> | undefined;
try {
	tracked = new Set(execFileSync("git", ["ls-files"], { cwd: ROOT, encoding: "utf8" }).split("\n").filter(Boolean));
} catch { /* not a git checkout (e.g. packaged install) — nothing to check */ }

describe("committed code only imports committed files", () => {
	test.skipIf(!tracked)("every relative import in tracked extension code is tracked", () => {
		const missing: string[] = [];
		for (const file of [...tracked!].filter((f) => f.startsWith("extensions/fusion-harness/") && f.endsWith(".ts") && !f.includes("/tests/"))) {
			const source = readFileSync(join(ROOT, file), "utf8");
			for (const match of source.matchAll(/(?:from|import)\s*\(?\s*["'](\.{1,2}\/[^"']+)["']/g)) {
				const target = normalize(relative(ROOT, join(ROOT, dirname(file), match[1]!)));
				if (!tracked!.has(target)) missing.push(`${file} → ${match[1]}`);
			}
		}
		expect(missing).toEqual([]);
	});
});
