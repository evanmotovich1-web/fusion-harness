import { describe, expect, test } from "bun:test";
import { laneMergePrompt, laneWorkerPrompt, parseLanesArgs } from "../modules/prompt-library.ts";
import { synthesizeLegacyStack } from "../modules/model-stack.ts";
import { newRun } from "../modules/runtime.ts";

describe("/fh-lanes arguments", () => {
	test("bare prompts run with an integration; --no-merge anywhere turns it off", () => {
		expect(parseLanesArgs("add a healthcheck endpoint")).toEqual({ action: "run", prompt: "add a healthcheck endpoint", merge: true });
		expect(parseLanesArgs("--no-merge add a healthcheck endpoint")).toEqual({ action: "run", prompt: "add a healthcheck endpoint", merge: false });
		expect(parseLanesArgs("add a healthcheck endpoint --no-merge")).toEqual({ action: "run", prompt: "add a healthcheck endpoint", merge: false });
		// A prompt that merely contains the words is not a flag.
		expect(parseLanesArgs("explain --no-merged branches")).toEqual({ action: "run", prompt: "explain --no-merged branches", merge: true });
	});

	test("management subcommands never look like prompts", () => {
		expect(parseLanesArgs("status")).toEqual({ action: "status", prompt: "", merge: false });
		expect(parseLanesArgs("CLEAN")).toEqual({ action: "clean", prompt: "", merge: false });
		expect(parseLanesArgs("diff flux")).toEqual({ action: "diff", slot: "flux", prompt: "", merge: false });
		expect(parseLanesArgs("diff")).toEqual({ action: "diff", slot: undefined, prompt: "", merge: false });
		// More words than a subcommand takes → it is a prompt after all.
		expect(parseLanesArgs("status of the migration")).toEqual({ action: "run", prompt: "status of the migration", merge: true });
		expect(parseLanesArgs("")).toEqual({ action: "run", prompt: "", merge: true });
	});
});

describe("/fh-lanes prompts", () => {
	const stack = synthesizeLegacyStack({ architectModel: "anthropic/claude-fable-5", builderModel: "openai/gpt-5.6-sol", architectThinking: "medium", builderThinking: "medium" });

	test("a lane worker is told exactly who it is and where its lane is", () => {
		const text = laneWorkerPrompt(stack.primaryBuilder, stack, "do the thing", { path: "/tmp/lanes/main", branch: "fh/lane/main" }, "/repo");
		expect(text).toContain("You are main (openai/gpt-5.6-sol)");
		expect(text).toContain("/tmp/lanes/main");
		expect(text).toContain("fh/lane/main");
		expect(text).toContain("/repo");
		expect(text).toContain("do the thing");
		expect(text).not.toContain("{{");
	});

	test("the integration envelope carries every lane's branch, commit, and paths", () => {
		const run = newRun("BUILDER", stack.primaryBuilder.model, stack.primaryBuilder);
		run.status = "done";
		run.exitCode = 0;
		run.text = "I changed a.txt";
		const text = laneMergePrompt(stack.architect, "do the thing", [{ run, branch: "fh/lane/main", path: "/tmp/lanes/main", base: "abc123", sha: "def456", committed: true, files: ["a.txt"], stat: " a.txt | 1 +", patch: "+three", reportPath: "/art/agents/main/report.md", patchPath: "/art/agents/main/lane.patch" }], "/repo", "/art");
		expect(text).toContain("[MAIN] openai/gpt-5.6-sol");
		expect(text).toContain("work commit: def456");
		expect(text).toContain("branch: fh/lane/main");
		expect(text).toContain("/art/lane-manifest.json");
		expect(text).toContain("I changed a.txt");
		expect(text).toContain("+three");
		expect(text).toContain("git cherry-pick -n");
		expect(text).not.toContain("{{");
	});
});
