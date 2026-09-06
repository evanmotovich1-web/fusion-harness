import { afterEach, describe, expect, test } from "bun:test";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { persistFailureStderr, promptArgs } from "../modules/child-process-contract.ts";
import { newRun, runError, toStat } from "../modules/runtime.ts";

const tempDirs: string[] = [];

afterEach(() => {
	while (tempDirs.length) fs.rmSync(tempDirs.pop()!, { recursive: true, force: true });
});

describe("child prompt argv", () => {
	test("ends option parsing before a dash-leading prompt", () => {
		const prompt = "----- BEGIN HARNESS REPO STATE -----\nmeasured facts";
		const args = ["--mode", "json", "-p", ...promptArgs(prompt)];

		expect(args.slice(-2)).toEqual(["--", prompt]);
	});
});

describe("failed child diagnostics", () => {
	test("persists full stderr privately without copying it into UI or summary stats", () => {
		const sessionDir = fs.mkdtempSync(path.join(os.tmpdir(), "fh-child-diagnostics-"));
		tempDirs.push(sessionDir);
		const run = newRun("BUILDER", "test/provider");
		const privateStderr = "PRIVATE_HEAD\nError: Unknown option: ----- prompt body -----\nPRIVATE_TAIL\n";
		run.status = "failed";
		run.exitCode = 2;
		run.stderr = privateStderr;

		const diagnosticPath = persistFailureStderr(run, sessionDir, 1_725_555_555_555);

		expect(diagnosticPath).toBe(path.join(sessionDir, "diagnostics", "stderr-1725555555555.log"));
		expect(run.stderrPath).toBe(diagnosticPath);
		expect(fs.readFileSync(diagnosticPath!, "utf8")).toBe(privateStderr);
		expect(fs.statSync(diagnosticPath!).mode & 0o777).toBe(0o600);

		const visible = JSON.stringify({ error: runError(run), stat: toStat(run) });
		expect(visible).toContain("full stderr saved to");
		expect(visible).not.toContain("PRIVATE_HEAD");
		expect(visible).not.toContain("PRIVATE_TAIL");
		expect(visible).not.toContain("Unknown option");
		expect(visible).not.toContain('"stderr"');
	});
});
