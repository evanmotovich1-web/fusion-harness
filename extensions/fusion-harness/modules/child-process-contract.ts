/**
 * Shared contract for launching and diagnosing Pi child processes.
 * Kept separate from child-runner.ts so tests can exercise it without spawning or mocking Pi.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { runOk, type AgentRun } from "./runtime.ts";

/** Stop Pi's option parser before passing the user's prompt as a positional message. */
export function promptArgs(prompt: string): ["--", string] {
	return ["--", prompt];
}

/** Persist complete failure diagnostics without copying raw stderr into panels or summary.json. */
export function persistFailureStderr(run: AgentRun, sessionDir: string, startedAt: number): string | undefined {
	if (runOk(run) || !run.stderr) return undefined;
	const diagnosticsDir = path.join(sessionDir, "diagnostics");
	const stderrPath = path.join(diagnosticsDir, `stderr-${startedAt}.log`);
	try {
		fs.mkdirSync(diagnosticsDir, { recursive: true, mode: 0o700 });
		fs.chmodSync(diagnosticsDir, 0o700);
		fs.writeFileSync(stderrPath, run.stderr, { encoding: "utf8", mode: 0o600 });
		fs.chmodSync(stderrPath, 0o600);
		run.stderrPath = stderrPath;
		return stderrPath;
	} catch {
		return undefined;
	}
}
