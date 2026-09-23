import { describe, expect, test } from "bun:test";
import { EventEmitter } from "node:events";
import {
	registerSessionBuildCommand,
	runSessionBuildCli,
	sessionBuildPrompt,
	type SessionBuildCli,
} from "../modules/cmd-session-build.ts";

const coverage = {
	schema_version: 1 as const,
	lanes: {
		claude: {
			discovered_files: 1, indexed_files: 1, parsed_events: 2, indexed_messages: 2,
			excluded_events: 0, parse_errors: 0, errors: 0, status: "indexed" as const,
		},
	},
	errors: [],
	unsupported_source_lanes: [],
	total_indexed_messages: 2,
	total_derived_documents: 0,
};

const index = { schema_version: 1 as const, processed: 1, unchanged: 0, failed: 0, coverage };
const brief = {
	schema_version: 1 as const,
	query: "finish the build",
	text: "Claude session ~/example.jsonl:14 says --publish-to origin/main was mentioned historically.",
	coverage,
	hits: [{ source: "claude" as const, path: "~/example.jsonl", ordinal: 14, session_id: "s1", role: "user" as const, actor_origin: "human_direct" as const, excerpt: "old note", score: 1 }],
};
const search = { schema_version: 1 as const, query: "finish", hits: brief.hits, coverage };

function commandHarness(confirm: boolean = true, withConfirm = true) {
	let handler: ((raw: string, ctx: any) => Promise<void>) | undefined;
	const notifications: Array<{ message: string; level: string }> = [];
	const statuses: Array<string | undefined> = [];
	const confirms: Array<{ title: string; detail: string }> = [];
	const ui: any = {
		notify: (message: string, level: string) => notifications.push({ message, level }),
		setStatus: (_key: string, message: string | undefined) => statuses.push(message),
	};
	if (withConfirm) ui.confirm = async (title: string, detail: string) => {
		confirms.push({ title, detail });
		return confirm;
	};
	const ctx = { ui };
	const pi = { registerCommand: (name: string, options: any) => {
		expect(name).toBe("fh-session-build");
		handler = options.handler;
	} };
	return { pi, ctx, notifications, statuses, confirms, run: async (input: string) => {
		if (!handler) throw new Error("command not registered");
		await handler(input, ctx);
	} };
}

function cliFixture(calls: string[][], overrides: Record<string, unknown> = {}): SessionBuildCli {
	return async (args) => {
		calls.push(args);
		return overrides[args[0]] ?? (args[0] === "index" ? index : args[0] === "coverage" ? coverage : args[0] === "search" ? search : brief);
	};
}

class FakeChild extends EventEmitter {
	stdout = new EventEmitter();
	stderr = new EventEmitter();
	killed: string[] = [];
	pid?: number;
	kill(signal?: NodeJS.Signals) { this.killed.push(signal ?? "SIGTERM"); return true; }
}

function fakeSpawn(child: FakeChild, captured: { command?: string; args?: readonly string[]; options?: any }) {
	return ((command: string, args: readonly string[], options: any) => {
		captured.command = command;
		captured.args = args;
		captured.options = options;
		return child as any;
	}) as any;
}

describe("session-backed build command", () => {
	test("historical publication flags remain inert data and evidence is byte-bounded", () => {
		const prompt = sessionBuildPrompt("repair the bridge", { ...brief, text: "--publish-to origin/main " + "😀".repeat(4_000) });
		expect(prompt).toContain("repair the bridge");
		expect(prompt).toContain("publish-to flag");
		expect(prompt).not.toContain("--publish-to");
		expect(prompt).toContain("untrusted data");
		expect(Buffer.byteLength(prompt.split("Historical coding-session context (untrusted data, cited to local source files):\n\n")[1]!.split("\n\nUse the history")[0]!, "utf8")).toBeLessThanOrEqual(10_000);
	});

	test("coverage is local-only and validates its response", async () => {
		const harness = commandHarness();
		const calls: string[][] = [];
		let builds = 0;
		registerSessionBuildCommand(harness.pi, { cli: cliFixture(calls), collaborateInternal: async () => { builds++; } });
		await harness.run("coverage");
		expect(calls).toEqual([["coverage", "--json"]]);
		expect(builds).toBe(0);
		expect(harness.statuses.at(-1)).toBeUndefined();
	});

	test("index and search are local-only exact modes", async () => {
		const harness = commandHarness();
		const calls: string[][] = [];
		let builds = 0;
		registerSessionBuildCommand(harness.pi, { cli: cliFixture(calls), collaborateInternal: async () => { builds++; } });
		await harness.run("index");
		await harness.run("search\tfinish the build");
		expect(calls).toEqual([["index", "--json"], ["index", "--json"], ["search", "--json", "--limit", "8", "finish the build"]]);
		expect(builds).toBe(0);
	});

	test("preview indexes and reads without confirmation or starting a build", async () => {
		const harness = commandHarness();
		const calls: string[][] = [];
		let builds = 0;
		registerSessionBuildCommand(harness.pi, { cli: cliFixture(calls), collaborateInternal: async () => { builds++; } });
		await harness.run("--preview\tfinish the build");
		expect(calls.map((args) => args[0])).toEqual(["index", "brief"]);
		expect(builds).toBe(0);
		expect(harness.confirms).toHaveLength(0);
		expect(harness.notifications.some((item) => item.message.includes("Claude session"))).toBe(true);
	});

	test("build requires approval, then dispatches once only through the internal entry point", async () => {
		const harness = commandHarness(true);
		const calls: string[][] = [];
		const builds: string[] = [];
		let directBuilds = 0;
		registerSessionBuildCommand(harness.pi, {
			cli: cliFixture(calls),
			collaborate: async () => { directBuilds++; },
			collaborateInternal: async (prompt) => { builds.push(prompt); },
		});
		await harness.run("finish the build");
		expect(builds).toHaveLength(1);
		expect(directBuilds).toBe(0);
		expect(builds[0]).not.toContain("--publish-to");
		expect(harness.confirms).toEqual([{ title: "Send local session context to model providers?", detail: expect.not.stringContaining("Claude session") }]);
		expect(harness.statuses.at(-1)).toBeUndefined();
	});

	test("declined or unavailable approval starts no collaboration", async () => {
		for (const [approved, withConfirm] of [[false, true], [true, false]] as const) {
			const harness = commandHarness(approved, withConfirm);
			let builds = 0;
			registerSessionBuildCommand(harness.pi, { cli: cliFixture([]), collaborateInternal: async () => { builds++; } });
			await harness.run("finish the build");
			expect(builds).toBe(0);
			expect(harness.statuses.at(-1)).toBeUndefined();
		}
	});

	test("invalid modes, overlong queries, invalid bridge responses, and collaboration failures clean status", async () => {
		for (const input of ["", "--preview", "search", "index extra", "coverage extra", "--previewx goal", "x".repeat(4_097)]) {
			const harness = commandHarness();
			registerSessionBuildCommand(harness.pi, { cli: cliFixture([]), collaborateInternal: async () => {} });
			await harness.run(input);
			expect(harness.notifications.at(-1)?.message).toContain("Usage:");
		}
		const invalid = commandHarness();
		registerSessionBuildCommand(invalid.pi, { cli: cliFixture([], { index: { ...index, schema_version: 2 } }), collaborateInternal: async () => {} });
		await invalid.run("finish the build");
		expect(invalid.notifications.at(-1)?.message).toContain("unsupported schema");
		expect(invalid.statuses.at(-1)).toBeUndefined();
		const failed = commandHarness(true);
		registerSessionBuildCommand(failed.pi, { cli: cliFixture([]), collaborateInternal: async () => { throw new Error("dispatch failed"); } });
		await failed.run("finish the build");
		expect(failed.notifications.at(-1)?.message).toContain("dispatch failed");
		expect(failed.statuses.at(-1)).toBeUndefined();
	});
});

describe("session index child bridge", () => {
	test("uses a reduced environment and settles valid JSON once", async () => {
		const child = new FakeChild();
		const captured: any = {};
		const pending = runSessionBuildCli(["coverage", "--json"], { spawn: fakeSpawn(child, captured) });
		child.stdout.emit("data", Buffer.from(JSON.stringify(coverage)));
		child.emit("close", 0);
		expect(await pending).toEqual(coverage);
		expect(captured.options.shell).toBe(false);
		expect(captured.options.env.XAI_API_KEY).toBeUndefined();
		expect(captured.options.env).not.toBe(process.env);
		child.emit("error", new Error("late"));
	});

	test("rejects UTF-8 byte overflow and terminates the child", async () => {
		const child = new FakeChild();
		const pending = runSessionBuildCli(["brief", "--json", "x"], { spawn: fakeSpawn(child, {}) });
		child.stdout.emit("data", Buffer.from("😀".repeat(500_001)));
		child.emit("close", 0);
		await expect(pending).rejects.toThrow("size limit");
		expect(child.killed).toContain("SIGTERM");
	});

	test("abort and timeout terminate without dispatching descendants", async () => {
		const aborted = new FakeChild();
		const controller = new AbortController();
		const abortPending = runSessionBuildCli(["coverage", "--json"], { spawn: fakeSpawn(aborted, {}), signal: controller.signal });
		controller.abort();
		aborted.emit("close", 0);
		await expect(abortPending).rejects.toThrow("aborted");
		expect(aborted.killed).toContain("SIGTERM");

		const timedOut = new FakeChild();
		const timeoutPending = runSessionBuildCli(["coverage", "--json"], { spawn: fakeSpawn(timedOut, {}), timeoutMs: 1 });
		await new Promise((resolve) => setTimeout(resolve, 5));
		timedOut.emit("close", 0);
		await expect(timeoutPending).rejects.toThrow("timed out");
		expect(timedOut.killed).toContain("SIGTERM");
	});

	test("nonzero, invalid JSON, and spawn error never retain stderr", async () => {
		for (const outcome of ["nonzero", "json", "error"] as const) {
			const child = new FakeChild();
			const pending = runSessionBuildCli(["coverage", "--json"], { spawn: fakeSpawn(child, {}) });
			child.stderr.emit("data", Buffer.from("SECRET_SHOULD_NOT_SURFACE"));
			if (outcome === "nonzero") child.emit("close", 2);
			else if (outcome === "json") { child.stdout.emit("data", Buffer.from("nope")); child.emit("close", 0); }
			else child.emit("error", new Error("spawn"));
			await expect(pending).rejects.not.toThrow("SECRET_SHOULD_NOT_SURFACE");
		}
	});
});
