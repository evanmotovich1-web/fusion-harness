import { afterEach, describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { acquireWriterLease, waitForWriterLease } from "../modules/writer-lease.ts";

const dirs: string[] = [];
afterEach(() => { while (dirs.length) rmSync(dirs.pop()!, { recursive: true, force: true }); });

describe("CWD writer lease", () => {
  test("allows one writer and rejects a concurrent lease", () => {
    const cwd = mkdtempSync(join(tmpdir(), "fh-writer-lease-")); dirs.push(cwd);
    const first = acquireWriterLease(cwd, "first");
    expect(() => acquireWriterLease(cwd, "second")).toThrow("already allowed to mutate");
    first.release();
    const second = acquireWriterLease(cwd, "second");
    expect(second.owner).not.toBe(first.owner);
    second.release();
  });
  test("waitForWriterLease queues behind a live holder and acquires on release", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "fh-writer-lease-")); dirs.push(cwd);
    const first = acquireWriterLease(cwd, "first");
    const waits: string[] = [];
    const pending = waitForWriterLease(cwd, "second", { pollMs: 10, onWait: (holder) => waits.push(holder) });
    await new Promise((resolve) => setTimeout(resolve, 50));
    first.release();
    const second = await pending;
    expect(waits).toHaveLength(1);
    expect(waits[0]).toContain("first");
    second.release();
  });

  test("waitForWriterLease stops when its signal aborts", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "fh-writer-lease-")); dirs.push(cwd);
    const first = acquireWriterLease(cwd, "first");
    const stop = new AbortController();
    const pending = waitForWriterLease(cwd, "second", { pollMs: 10, signal: stop.signal });
    setTimeout(() => stop.abort(), 30);
    await expect(pending).rejects.toThrow("stopped while waiting");
    first.release();
  });
});
