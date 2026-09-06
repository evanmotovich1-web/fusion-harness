import { describe, expect, test } from "bun:test";
import type { CollaborationTask } from "../modules/collaboration-graph.ts";
import {
	COLLABORATION_OUTCOME_PREFIX,
	applyCollaborationTaskOutcome,
	formatCollaborationTaskOutcome,
	initializeCollaborationTaskStates,
	parseCollaborationTaskOutcome,
	selectCollaborationDecisionRequest,
	selectStartableCollaborationTasks,
	type CollaborationTaskOutcome,
} from "../modules/collaboration-outcome.ts";

const tasks: CollaborationTask[] = [
	{ id: "1.a", assignee: "terra", description: "root", depends_on: [], outputs: [], mode: "write" },
	{ id: "1.b", assignee: "grok", description: "independent", depends_on: [], outputs: [], mode: "read" },
	{ id: "2.a", assignee: "drift", description: "child", depends_on: ["1.a"], outputs: [], mode: "read" },
	{ id: "3.a", assignee: "glm", description: "grandchild", depends_on: ["2.a"], outputs: [], mode: "write" },
];

const outcome = (status: CollaborationTaskOutcome["status"], summary = "measured result"): CollaborationTaskOutcome => ({
	schema_version: 1,
	status,
	summary,
	...(status === "needs_decision" ? { decision: { question: "Which target ref?", options: ["origin/main", "upstream/main"] } } : {}),
});

describe("collaboration task outcome parser", () => {
	test("parses the sole final metadata line and preserves report prose", () => {
		const parsed = parseCollaborationTaskOutcome([
			"Changed the scheduler.",
			"Validation: 8 tests passed.",
			formatCollaborationTaskOutcome(outcome("completed")),
			"",
		].join("\n"));
		expect(parsed.report).toBe("Changed the scheduler.\nValidation: 8 tests passed.");
		expect(parsed.outcome).toEqual(outcome("completed"));
	});

	test("nonempty success prose without metadata fails closed", () => {
		expect(() => parseCollaborationTaskOutcome("Implemented everything. Tests pass.")).toThrow("exactly one");
	});

	test("rejects malformed, duplicate, and non-terminal metadata", () => {
		expect(() => parseCollaborationTaskOutcome(`${COLLABORATION_OUTCOME_PREFIX} {bad json}`)).toThrow("not valid JSON");
		expect(() => parseCollaborationTaskOutcome([
			formatCollaborationTaskOutcome(outcome("completed")),
			formatCollaborationTaskOutcome(outcome("completed")),
		].join("\n"))).toThrow("exactly one");
		expect(() => parseCollaborationTaskOutcome([
			formatCollaborationTaskOutcome(outcome("completed")),
			"trailing prose",
		].join("\n"))).toThrow("final non-empty line");
	});

	test("rejects unknown schema fields and status values", () => {
		expect(() => parseCollaborationTaskOutcome(`${COLLABORATION_OUTCOME_PREFIX} {"schema_version":1,"status":"done","summary":"x"}`)).toThrow("status must be one of");
		expect(() => parseCollaborationTaskOutcome(`${COLLABORATION_OUTCOME_PREFIX} {"schema_version":1,"status":"completed","summary":"x","claim":true}`)).toThrow("unknown field");
		expect(() => parseCollaborationTaskOutcome(`${COLLABORATION_OUTCOME_PREFIX} {"schema_version":2,"status":"completed","summary":"x"}`)).toThrow("schema_version");
	});

	test("needs_decision requires one concrete question with distinct options", () => {
		const parsed = parseCollaborationTaskOutcome(`${COLLABORATION_OUTCOME_PREFIX} {"schema_version":1,"status":"needs_decision","summary":"two remotes match","decision":{"question":"Which remote?","options":["origin","upstream"]}}`);
		expect(parsed.outcome.decision).toEqual({ question: "Which remote?", options: ["origin", "upstream"] });
		expect(() => parseCollaborationTaskOutcome(`${COLLABORATION_OUTCOME_PREFIX} {"schema_version":1,"status":"needs_decision","summary":"ambiguous"}`)).toThrow("decision must be a JSON object");
		expect(() => parseCollaborationTaskOutcome(`${COLLABORATION_OUTCOME_PREFIX} {"schema_version":1,"status":"needs_decision","summary":"ambiguous","decision":{"question":"Choose","options":["same","same"]}}`)).toThrow("unique");
		expect(() => parseCollaborationTaskOutcome(`${COLLABORATION_OUTCOME_PREFIX} {"schema_version":1,"status":"blocked","summary":"unsafe","decision":{"question":"Override?","options":["yes","no"]}}`)).toThrow("only allowed");
	});
});

describe("collaboration outcome scheduling", () => {
	test("completed satisfies dependencies without changing independent branches", () => {
		const states = initializeCollaborationTaskStates(tasks);
		states["1.a"] = "writing";
		const applied = applyCollaborationTaskOutcome(tasks, states, "1.a", outcome("completed"));
		expect(applied.states).toEqual({ "1.a": "completed", "1.b": "pending", "2.a": "pending", "3.a": "pending" });
		expect(applied.skippedTaskIds).toEqual([]);
		expect(selectStartableCollaborationTasks(tasks, applied.states, new Set(), false)).toEqual(["1.b", "2.a"]);
	});

	test("no_op skips every descendant but leaves an independent task runnable", () => {
		const states = initializeCollaborationTaskStates(tasks);
		states["1.a"] = "writing";
		states["2.a"] = "queued";
		const applied = applyCollaborationTaskOutcome(tasks, states, "1.a", outcome("no_op", "already integrated"));
		expect(applied.states).toEqual({ "1.a": "no_op", "1.b": "pending", "2.a": "skipped", "3.a": "skipped" });
		expect(applied.skippedTaskIds).toEqual(["2.a", "3.a"]);
		expect(selectStartableCollaborationTasks(tasks, applied.states, new Set(), false)).toEqual(["1.b"]);
	});

	test("blocked skips descendants without globally cancelling independent work", () => {
		const states = initializeCollaborationTaskStates(tasks);
		states["1.a"] = "writing";
		const applied = applyCollaborationTaskOutcome(tasks, states, "1.a", outcome("blocked", "dirty repository"));
		expect(applied.states["1.a"]).toBe("blocked");
		expect(applied.states["2.a"]).toBe("skipped");
		expect(applied.states["3.a"]).toBe("skipped");
		expect(selectStartableCollaborationTasks(tasks, applied.states, new Set(), false)).toEqual(["1.b"]);
	});

	test("refuses an impossible result transition that would strand a running descendant", () => {
		const states = initializeCollaborationTaskStates(tasks);
		states["1.a"] = "writing";
		states["2.a"] = "reading";
		expect(() => applyCollaborationTaskOutcome(tasks, states, "1.a", outcome("blocked"))).toThrow("scheduler invariant violated");
	});

	test("needs_decision returns one explicit request and does not run descendants", () => {
		const states = initializeCollaborationTaskStates(tasks);
		states["1.a"] = "writing";
		const applied = applyCollaborationTaskOutcome(tasks, states, "1.a", outcome("needs_decision", "target is ambiguous"));
		expect(applied.states["1.a"]).toBe("needs_decision");
		expect(applied.states["2.a"]).toBe("pending");
		expect(applied.decisionRequest).toEqual({ taskId: "1.a", question: "Which target ref?", options: ["origin/main", "upstream/main"] });
		// Independent work is preserved but no new task starts until the one
		// outstanding decision is surfaced and resolved.
		expect(selectStartableCollaborationTasks(tasks, applied.states, new Set(), false)).toEqual([]);
	});

	test("chooses one stable decision request in plan order", () => {
		const outcomes = new Map<string, CollaborationTaskOutcome>([
			["1.b", { schema_version: 1, status: "needs_decision", summary: "second", decision: { question: "Second?", options: ["a", "b"] } }],
			["1.a", { schema_version: 1, status: "needs_decision", summary: "first", decision: { question: "First?", options: ["x", "y"] } }],
		]);
		expect(selectCollaborationDecisionRequest(tasks, outcomes)).toEqual({ taskId: "1.a", summary: "first", question: "First?", options: ["x", "y"] });
	});

	test("starts all eligible independent reads and at most one writer across distinct slots", () => {
		const parallel: CollaborationTask[] = [
			{ id: "1.a", assignee: "terra", description: "write one", depends_on: [], outputs: [], mode: "write" },
			{ id: "1.b", assignee: "grok", description: "write two", depends_on: [], outputs: [], mode: "write" },
			{ id: "1.c", assignee: "drift", description: "read one", depends_on: [], outputs: [], mode: "read" },
			{ id: "1.d", assignee: "glm", description: "read two", depends_on: [], outputs: [], mode: "read" },
		];
		const states = initializeCollaborationTaskStates(parallel);
		expect(selectStartableCollaborationTasks(parallel, states, new Set(), false)).toEqual(["1.a", "1.c", "1.d"]);
		expect(selectStartableCollaborationTasks(parallel, states, new Set(), true)).toEqual(["1.c", "1.d"]);
	});

	test("serializes tasks assigned to the same slot", () => {
		const sameSlot: CollaborationTask[] = [
			{ id: "1.a", assignee: "terra", description: "first", depends_on: [], outputs: [], mode: "read" },
			{ id: "1.b", assignee: "terra", description: "second", depends_on: [], outputs: [], mode: "read" },
		];
		expect(selectStartableCollaborationTasks(sameSlot, initializeCollaborationTaskStates(sameSlot), new Set(), false)).toEqual(["1.a"]);
	});
});
