import { afterEach, describe, expect, test } from "bun:test";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import {
  boundTask,
  cancelForeign,
  createOwnedRecord,
  foreignFromLive,
  foreignFromSummaryFile,
  isApproval,
  openLedger,
  TASK_MAX_CHARS,
} from "./run-status.ts";

const dirs: string[] = [];
afterEach(() => {
  while (dirs.length) fs.rmSync(dirs.pop()!, { recursive: true, force: true });
});

function tempDir(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "evan-run-status-"));
  dirs.push(dir);
  return dir;
}

describe("Evan owned run ledger", () => {
  test("omitted cost stays null and a restart reads the same row", () => {
    const dir = tempDir();
    const ledgerPath = path.join(dir, ".state", "runs.jsonl");
    const first = openLedger(ledgerPath);
    const written = first.append({
      run_id: "run-1",
      task: "count files",
      cwd: "/work/evan",
      tools: ["read", "ls"],
    });
    expect(written.cost_usd).toBeNull();
    expect(written.owner).toBe("evan");
    expect(written.source).toBe("evan");
    expect(written.state).toBe("pending");
    expect(isApproval(written)).toBe(false);

    const reopened = openLedger(ledgerPath);
    expect(reopened.latest()).toEqual([written]);
    expect(fs.readFileSync(ledgerPath, "utf8").trim().split("\n")).toHaveLength(1);
  });

  test("updates append a new line and latest keeps the last state", () => {
    const dir = tempDir();
    const ledger = openLedger(path.join(dir, "runs.jsonl"));
    ledger.append({ run_id: "run-2", task: "handoff", cwd: "/work/evan", state: "working" });
    ledger.append({
      run_id: "run-2",
      task: "handoff",
      cwd: "/work/evan",
      state: "done",
      cost_usd: 1.25,
      ended_at: "2026-09-25T00:00:00.000Z",
    });
    const lines = fs.readFileSync(ledger.path, "utf8").trim().split("\n");
    expect(lines).toHaveLength(2);
    expect(JSON.parse(lines[0]!).state).toBe("working");
    expect(JSON.parse(lines[0]!).cost_usd).toBeNull();
    expect(ledger.latest()).toEqual([expect.objectContaining({ run_id: "run-2", state: "done", cost_usd: 1.25 })]);
  });

  test("task text is bounded to one line and does not keep the overflow", () => {
    const secret = "SECRET-TAIL";
    const task = `${"a".repeat(TASK_MAX_CHARS)}\n${secret}`;
    const bounded = boundTask(task);
    expect(bounded).toHaveLength(TASK_MAX_CHARS);
    expect(bounded).not.toContain(secret);
    expect(bounded).not.toContain("\n");
    const record = createOwnedRecord({ run_id: "run-3", task, cwd: "/work/evan" });
    expect(JSON.stringify(record)).not.toContain(secret);
  });
});

describe("foreign observe-only status", () => {
  test("a missing fusion summary is unavailable and does not invent cost or control", () => {
    const missing = path.join(tempDir(), "summary.json");
    const [row] = foreignFromSummaryFile(missing);
    expect(row).toMatchObject({
      source: "unavailable",
      run_id: "unknown",
      state: "unknown",
      cost_usd: null,
      tools: "unknown",
      control: "observe-only",
    });
    expect(row?.reason).toContain("missing");
    expect(() => cancelForeign()).toThrow("observe-only");
  });

  test("a fusion summary exposes status and id only", () => {
    const dir = tempDir();
    const summary = path.join(dir, "summary.json");
    fs.writeFileSync(summary, JSON.stringify({
      agents: [{
        slotId: "sol",
        status: "done",
        model: "openai-codex/gpt-5.6-sol",
        costUsd: 3.33,
        toolNames: ["bash"],
        toolEvents: [{ name: "bash", argument: "cat secrets" }],
      }],
      sessions: { sol: "session-9" },
    }));
    const [row] = foreignFromSummaryFile(summary);
    expect(row).toMatchObject({
      owner: "foreign",
      source: "fusion-summary",
      run_id: "unknown",
      display_id: "sol",
      state: "done",
      model: "unknown",
      task: "unknown",
      cwd: "unknown",
      tools: "unknown",
      cost_usd: null,
      control: "observe-only",
    });
    const encoded = JSON.stringify(row);
    expect(encoded).not.toContain("secrets");
    expect(encoded).not.toContain("3.33");
    expect(encoded).not.toContain("bash");
    expect(isApproval(row!)).toBe(false);
  });

  test("live status requires an explicit snapshot", () => {
    expect(foreignFromLive(undefined)[0]).toMatchObject({ source: "unavailable", state: "unknown" });
    expect(foreignFromLive([{ status: "working", slotId: "grok" }])[0]).toMatchObject({
      source: "fusion-live",
      display_id: "grok",
      state: "working",
      cost_usd: null,
      control: "observe-only",
    });
  });
});
