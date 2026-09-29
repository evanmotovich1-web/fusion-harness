import * as fs from "node:fs";
import * as path from "node:path";

/** Fusion child statuses. Owned runs use this set. Foreign runs may also be "unknown". */
export const CHILD_STATUSES = ["pending", "working", "done", "failed", "timeout", "aborted"] as const;
export type ChildStatus = (typeof CHILD_STATUSES)[number];
export type RunState = ChildStatus | "unknown";

export const TASK_MAX_CHARS = 500;

export type OwnedRunRecord = {
  schema_version: 1;
  run_id: string;
  owner: "evan";
  parent_run_id: string | null;
  source: "evan";
  model: string;
  task: string;
  cwd: string;
  state: ChildStatus;
  tools: string[];
  cost_usd: number | null;
  artifact_path: string | null;
  started_at: string;
  ended_at: string | null;
  heartbeat_at: string | null;
};

export type ForeignSource = "fusion-summary" | "fusion-live" | "unavailable";

export type ForeignRunStatus = {
  schema_version: 1;
  owner: "foreign";
  source: ForeignSource;
  run_id: "unknown";
  display_id: string;
  state: RunState;
  model: "unknown";
  task: "unknown";
  cwd: "unknown";
  tools: "unknown";
  cost_usd: null;
  artifact_path: null;
  control: "observe-only";
  reason: string;
};

export type OwnedRunInput = {
  run_id: string;
  parent_run_id?: string | null;
  model?: string;
  task: string;
  cwd: string;
  state?: ChildStatus;
  tools?: string[];
  cost_usd?: number | null;
  artifact_path?: string | null;
  started_at?: string;
  ended_at?: string | null;
  heartbeat_at?: string | null;
};

const OWNED_KEYS = [
  "schema_version",
  "run_id",
  "owner",
  "parent_run_id",
  "source",
  "model",
  "task",
  "cwd",
  "state",
  "tools",
  "cost_usd",
  "artifact_path",
  "started_at",
  "ended_at",
  "heartbeat_at",
] as const;

export function defaultLedgerPath(appDir: string): string {
  return path.join(appDir, ".state", "runs.jsonl");
}

export function boundTask(task: string): string {
  const singleLine = task.replace(/[\r\n]+/g, " ").trim();
  return singleLine.length <= TASK_MAX_CHARS ? singleLine : singleLine.slice(0, TASK_MAX_CHARS);
}

function isChildStatus(value: unknown): value is ChildStatus {
  return typeof value === "string" && (CHILD_STATUSES as readonly string[]).includes(value);
}

function requireId(runId: string): string {
  const id = runId.trim();
  if (!id || id === "unknown" || /[\r\n]/.test(id)) throw new Error("run_id must be an Evan-minted id");
  return id;
}

function costOrNull(value: number | null | undefined): number | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) throw new Error("cost_usd must be a finite non-negative number or null");
  return value;
}

function toolNames(value: string[] | undefined): string[] {
  if (!value) return [];
  return value.map((name) => {
    if (typeof name !== "string" || !name.trim() || /[\r\n]/.test(name)) throw new Error("tool names must be non-empty single-line strings");
    return name.trim();
  });
}

export function createOwnedRecord(input: OwnedRunInput, now = new Date().toISOString()): OwnedRunRecord {
  const record: OwnedRunRecord = {
    schema_version: 1,
    run_id: requireId(input.run_id),
    owner: "evan",
    parent_run_id: input.parent_run_id ?? null,
    source: "evan",
    model: input.model?.trim() || "unknown",
    task: boundTask(input.task),
    cwd: input.cwd.trim(),
    state: input.state ?? "pending",
    tools: toolNames(input.tools),
    cost_usd: costOrNull(input.cost_usd),
    artifact_path: input.artifact_path ?? null,
    started_at: input.started_at ?? now,
    ended_at: input.ended_at ?? null,
    heartbeat_at: input.heartbeat_at ?? null,
  };
  if (!isChildStatus(record.state)) throw new Error("owned state must be a Fusion child status");
  if (!record.cwd) throw new Error("cwd is required");
  if (!record.task) throw new Error("task is required");
  return record;
}

/** Compaction text and foreign rows never authorize an action. */
export function isApproval(_record: OwnedRunRecord | ForeignRunStatus | string): false {
  return false;
}

function unavailable(source: ForeignSource, reason: string): ForeignRunStatus {
  return {
    schema_version: 1,
    owner: "foreign",
    source,
    run_id: "unknown",
    display_id: "unknown",
    state: "unknown",
    model: "unknown",
    task: "unknown",
    cwd: "unknown",
    tools: "unknown",
    cost_usd: null,
    artifact_path: null,
    control: "observe-only",
    reason,
  };
}

function foreignFromAgent(agent: unknown, source: "fusion-summary" | "fusion-live", sessions: Record<string, unknown>): ForeignRunStatus {
  const row = agent && typeof agent === "object" ? agent as Record<string, unknown> : {};
  const slotId = typeof row.slotId === "string" && row.slotId.trim() ? row.slotId.trim() : "";
  const sessionId = slotId && typeof sessions[slotId] === "string" ? String(sessions[slotId]) : "";
  return {
    ...unavailable(source, "fusion fields other than status and id are not Evan-verified"),
    source,
    display_id: slotId || sessionId || "unknown",
    state: isChildStatus(row.status) ? row.status : "unknown",
  };
}

export function foreignFromSummaryFile(summaryPath: string): ForeignRunStatus[] {
  if (!fs.existsSync(summaryPath) || !fs.statSync(summaryPath).isFile()) {
    return [unavailable("unavailable", "fusion summary is missing")];
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(fs.readFileSync(summaryPath, "utf8"));
  } catch {
    return [unavailable("unavailable", "fusion summary is not JSON")];
  }
  if (!parsed || typeof parsed !== "object" || !Array.isArray((parsed as { agents?: unknown }).agents)) {
    return [unavailable("unavailable", "fusion summary has no agents array")];
  }
  const sessions = (parsed as { sessions?: unknown }).sessions;
  const sessionMap = sessions && typeof sessions === "object" ? sessions as Record<string, unknown> : {};
  return (parsed as { agents: unknown[] }).agents.map((agent) => foreignFromAgent(agent, "fusion-summary", sessionMap));
}

/** Caller-supplied snapshot only. This function does not attach to a live Fusion process. */
export function foreignFromLive(agents: unknown[] | null | undefined): ForeignRunStatus[] {
  if (!agents) return [unavailable("unavailable", "no fusion live snapshot was supplied")];
  return agents.map((agent) => foreignFromAgent(agent, "fusion-live", {}));
}

export function cancelForeign(): never {
  throw new Error("foreign runs are observe-only");
}

export type RunLedger = {
  path: string;
  append(input: OwnedRunInput): OwnedRunRecord;
  list(): OwnedRunRecord[];
  latest(): OwnedRunRecord[];
};

function assertOwned(value: unknown, line: number): OwnedRunRecord {
  if (!value || typeof value !== "object") throw new Error(`runs.jsonl line ${line} is not a record`);
  const row = value as Record<string, unknown>;
  for (const key of OWNED_KEYS) {
    if (!(key in row)) throw new Error(`runs.jsonl line ${line} is missing ${key}`);
  }
  if (row.schema_version !== 1 || row.owner !== "evan" || row.source !== "evan") {
    throw new Error(`runs.jsonl line ${line} is not an Evan-owned record`);
  }
  if (typeof row.run_id !== "string" || typeof row.task !== "string" || typeof row.cwd !== "string") {
    throw new Error(`runs.jsonl line ${line} has a bad identity field`);
  }
  if (!isChildStatus(row.state)) throw new Error(`runs.jsonl line ${line} has a bad state`);
  if (row.cost_usd !== null && (typeof row.cost_usd !== "number" || !Number.isFinite(row.cost_usd))) {
    throw new Error(`runs.jsonl line ${line} has a bad cost`);
  }
  if (!Array.isArray(row.tools) || row.tools.some((tool) => typeof tool !== "string")) {
    throw new Error(`runs.jsonl line ${line} has bad tools`);
  }
  return row as OwnedRunRecord;
}

export function openLedger(ledgerPath: string): RunLedger {
  const file = path.resolve(ledgerPath);
  const append = (input: OwnedRunInput): OwnedRunRecord => {
    const prior = fs.existsSync(file) ? readLines(file) : [];
    const previous = [...prior].reverse().find((row) => row.run_id === input.run_id.trim());
    const record = createOwnedRecord({
      ...input,
      parent_run_id: input.parent_run_id === undefined ? previous?.parent_run_id ?? null : input.parent_run_id,
      model: input.model ?? previous?.model,
      task: input.task,
      cwd: input.cwd,
      tools: input.tools ?? previous?.tools,
      cost_usd: input.cost_usd === undefined ? previous?.cost_usd ?? null : input.cost_usd,
      artifact_path: input.artifact_path === undefined ? previous?.artifact_path ?? null : input.artifact_path,
      started_at: input.started_at ?? previous?.started_at,
    });
    fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
    fs.appendFileSync(file, `${JSON.stringify(record)}\n`, { encoding: "utf8", mode: 0o600 });
    return record;
  };
  const list = (): OwnedRunRecord[] => (fs.existsSync(file) ? readLines(file) : []);
  const latest = (): OwnedRunRecord[] => {
    const byId = new Map<string, OwnedRunRecord>();
    for (const row of list()) byId.set(row.run_id, row);
    return [...byId.values()];
  };
  return { path: file, append, list, latest };
}

function readLines(file: string): OwnedRunRecord[] {
  const text = fs.readFileSync(file, "utf8");
  if (!text.trim()) return [];
  return text.split("\n").filter((line) => line.trim()).map((line, index) => assertOwned(JSON.parse(line), index + 1));
}
