import type { CollaborationTask } from "./collaboration-graph.ts";

export const COLLABORATION_OUTCOME_PREFIX = "FH_TASK_OUTCOME:";
export const COLLABORATION_OUTCOME_SCHEMA_VERSION = 1 as const;

export type CollaborationOutcomeStatus = "completed" | "no_op" | "blocked" | "needs_decision";

export interface CollaborationDecisionRequest {
	question: string;
	options: string[];
}

export interface CollaborationTaskOutcome {
	schema_version: typeof COLLABORATION_OUTCOME_SCHEMA_VERSION;
	status: CollaborationOutcomeStatus;
	summary: string;
	decision?: CollaborationDecisionRequest;
}

export interface ParsedCollaborationTaskOutcome {
	outcome: CollaborationTaskOutcome;
	report: string;
}

export type CollaborationTaskExecutionState =
	| "pending"
	| "queued"
	| "reading"
	| "writing"
	| "completed"
	| "no_op"
	| "blocked"
	| "needs_decision"
	| "failed"
	| "skipped";

export type CollaborationTaskStates = Record<string, CollaborationTaskExecutionState>;

export interface AppliedCollaborationOutcome {
	states: CollaborationTaskStates;
	skippedTaskIds: string[];
	decisionRequest?: CollaborationDecisionRequest & { taskId: string };
}

export const COLLABORATION_OUTCOME_INSTRUCTION = [
	"End the report with exactly one metadata line using this format:",
	`${COLLABORATION_OUTCOME_PREFIX} {"schema_version":1,"status":"completed","summary":"short factual result"}`,
	'Allowed status values are "completed", "no_op", "blocked", and "needs_decision".',
	'For "needs_decision", also include exactly one decision object: {"question":"...","options":["...","..."]}.',
	"The final metadata line is mandatory. Prose without valid metadata fails closed.",
].join("\n");

function record(value: unknown, label: string): Record<string, unknown> {
	if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${label} must be a JSON object`);
	return value as Record<string, unknown>;
}

function assertExactKeys(value: Record<string, unknown>, allowed: readonly string[], label: string): void {
	const extras = Object.keys(value).filter((key) => !allowed.includes(key));
	if (extras.length) throw new Error(`${label} contains unknown field${extras.length === 1 ? "" : "s"}: ${extras.join(", ")}`);
}

function nonEmptyString(value: unknown, label: string): string {
	if (typeof value !== "string" || !value.trim()) throw new Error(`${label} must be a non-empty string`);
	return value.trim();
}

function validateOutcome(value: unknown): CollaborationTaskOutcome {
	const raw = record(value, "task outcome");
	assertExactKeys(raw, ["schema_version", "status", "summary", "decision"], "task outcome");
	if (raw.schema_version !== COLLABORATION_OUTCOME_SCHEMA_VERSION) {
		throw new Error(`task outcome.schema_version must be ${COLLABORATION_OUTCOME_SCHEMA_VERSION}`);
	}
	const allowedStatuses: CollaborationOutcomeStatus[] = ["completed", "no_op", "blocked", "needs_decision"];
	if (typeof raw.status !== "string" || !allowedStatuses.includes(raw.status as CollaborationOutcomeStatus)) {
		throw new Error(`task outcome.status must be one of: ${allowedStatuses.join(", ")}`);
	}
	const status = raw.status as CollaborationOutcomeStatus;
	const summary = nonEmptyString(raw.summary, "task outcome.summary");
	if (status !== "needs_decision") {
		if (raw.decision !== undefined) throw new Error(`task outcome.decision is only allowed for needs_decision`);
		return { schema_version: COLLABORATION_OUTCOME_SCHEMA_VERSION, status, summary };
	}

	const decision = record(raw.decision, "task outcome.decision");
	assertExactKeys(decision, ["question", "options"], "task outcome.decision");
	const question = nonEmptyString(decision.question, "task outcome.decision.question");
	if (!Array.isArray(decision.options) || decision.options.length < 2) {
		throw new Error("task outcome.decision.options must contain at least two strings");
	}
	const options = decision.options.map((option, index) => nonEmptyString(option, `task outcome.decision.options[${index}]`));
	if (new Set(options).size !== options.length) throw new Error("task outcome.decision.options must be unique");
	return {
		schema_version: COLLABORATION_OUTCOME_SCHEMA_VERSION,
		status,
		summary,
		decision: { question, options },
	};
}

/**
 * Parse the mandatory final task-outcome line while preserving the human report.
 * Exactly one marker is accepted so an example in prose cannot compete with the
 * authoritative terminal record.
 */
export function parseCollaborationTaskOutcome(text: string): ParsedCollaborationTaskOutcome {
	const lines = text.replace(/\r\n?/g, "\n").split("\n");
	while (lines.length && !lines[lines.length - 1]!.trim()) lines.pop();
	const markerIndexes = lines
		.map((line, index) => line.startsWith(COLLABORATION_OUTCOME_PREFIX) ? index : -1)
		.filter((index) => index >= 0);
	if (markerIndexes.length !== 1) {
		throw new Error(`task report must contain exactly one ${COLLABORATION_OUTCOME_PREFIX} metadata line`);
	}
	const markerIndex = markerIndexes[0]!;
	if (markerIndex !== lines.length - 1) throw new Error(`${COLLABORATION_OUTCOME_PREFIX} metadata must be the final non-empty line`);
	const encoded = lines[markerIndex]!.slice(COLLABORATION_OUTCOME_PREFIX.length).trim();
	if (!encoded) throw new Error("task outcome metadata is empty");
	let parsed: unknown;
	try {
		parsed = JSON.parse(encoded);
	} catch (error) {
		throw new Error(`task outcome metadata is not valid JSON: ${error instanceof Error ? error.message : String(error)}`);
	}
	return { outcome: validateOutcome(parsed), report: lines.slice(0, markerIndex).join("\n").trim() };
}

export function formatCollaborationTaskOutcome(outcome: CollaborationTaskOutcome): string {
	return `${COLLABORATION_OUTCOME_PREFIX} ${JSON.stringify(validateOutcome(outcome))}`;
}

export function initializeCollaborationTaskStates(tasks: readonly Pick<CollaborationTask, "id">[]): CollaborationTaskStates {
	return Object.fromEntries(tasks.map((task) => [task.id, "pending" as const]));
}

function descendantIds(tasks: readonly Pick<CollaborationTask, "id" | "depends_on">[], taskId: string): string[] {
	const descendants: string[] = [];
	const queue = [taskId];
	const seen = new Set(queue);
	while (queue.length) {
		const parent = queue.shift()!;
		for (const task of tasks) {
			if (!seen.has(task.id) && task.depends_on.includes(parent)) {
				seen.add(task.id);
				descendants.push(task.id);
				queue.push(task.id);
			}
		}
	}
	return descendants;
}

/** Apply a validated result without disturbing independent branches of the DAG. */
export function applyCollaborationTaskOutcome(
	tasks: readonly Pick<CollaborationTask, "id" | "depends_on">[],
	currentStates: Readonly<CollaborationTaskStates>,
	taskId: string,
	outcome: CollaborationTaskOutcome,
): AppliedCollaborationOutcome {
	validateOutcome(outcome);
	if (!tasks.some((task) => task.id === taskId)) throw new Error(`unknown collaboration task: ${taskId}`);
	const current = currentStates[taskId];
	if (current !== "reading" && current !== "writing") {
		throw new Error(`cannot apply an outcome to task ${taskId} while it is ${current ?? "missing"}`);
	}
	const states = { ...currentStates, [taskId]: outcome.status };
	const skippedTaskIds: string[] = [];
	if (outcome.status === "no_op" || outcome.status === "blocked") {
		for (const descendantId of descendantIds(tasks, taskId)) {
			const state = states[descendantId];
			if (state === "reading" || state === "writing") {
				throw new Error(`scheduler invariant violated: descendant ${descendantId} was running before ${taskId} finished`);
			}
			if (state === "pending" || state === "queued") {
				states[descendantId] = "skipped";
				skippedTaskIds.push(descendantId);
			}
		}
	}
	return {
		states,
		skippedTaskIds,
		decisionRequest: outcome.status === "needs_decision"
			? { taskId, ...outcome.decision! }
			: undefined,
	};
}

/**
 * Return every task that can start now, respecting slot serialization and the
 * existing one-writer invariant while allowing independent reads to overlap.
 */
export function selectStartableCollaborationTasks(
	tasks: readonly Pick<CollaborationTask, "id" | "assignee" | "depends_on" | "mode">[],
	states: Readonly<CollaborationTaskStates>,
	busyAssignees: ReadonlySet<string>,
	writerActive: boolean,
): string[] {
	// Let already-running work settle, but do not launch more work while a human
	// decision is outstanding. The caller surfaces one stable request below.
	if (Object.values(states).includes("needs_decision")) return [];
	const selected: string[] = [];
	const occupied = new Set(busyAssignees);
	let writerSelected = writerActive;
	for (const task of tasks) {
		const state = states[task.id];
		if (state !== "pending" && state !== "queued") continue;
		if (!task.depends_on.every((dependency) => states[dependency] === "completed")) continue;
		if (occupied.has(task.assignee)) continue;
		if (task.mode === "write" && writerSelected) continue;
		selected.push(task.id);
		occupied.add(task.assignee);
		if (task.mode === "write") writerSelected = true;
	}
	return selected;
}

/** Pick one stable prompt even if multiple in-flight tasks discover ambiguity. */
export function selectCollaborationDecisionRequest(
	tasks: readonly Pick<CollaborationTask, "id">[],
	outcomes: ReadonlyMap<string, CollaborationTaskOutcome>,
): (CollaborationDecisionRequest & { taskId: string; summary: string }) | undefined {
	for (const task of tasks) {
		const outcome = outcomes.get(task.id);
		if (outcome?.status === "needs_decision") {
			return { taskId: task.id, summary: outcome.summary, ...outcome.decision! };
		}
	}
	return undefined;
}
