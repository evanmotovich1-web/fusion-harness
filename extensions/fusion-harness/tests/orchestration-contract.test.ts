import { describe, expect, test } from "bun:test";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const root = join(import.meta.dir, "..");
// The implementation spans the factory (fusion-harness.ts) plus modules/ — the
// contracts below are about the WHOLE extension, so assert against the concatenation.
const sourceFiles = [
  join(root, "fusion-harness.ts"),
  ...readdirSync(join(root, "modules"))
    .filter((file) => file.endsWith(".ts"))
    .map((file) => join(root, "modules", file)),
];
const source = sourceFiles.map((file) => readFileSync(file, "utf8")).join("\n");
const prompt = (name: string) => readFileSync(join(root, "prompts", name), "utf8");

describe("orchestration contracts", () => {
  test("runner resets rounds, concatenates text blocks, and escalates using close state", () => {
    expect(source).toContain('run.text = ""');
    expect(source).toContain('finalizedText += part.text');
    expect(source).toContain('if (!closed)');
    expect(source).toContain('process.kill(-proc.pid, signal)');
    expect(source).toContain('detached: process.platform !== "win32"');
    expect(source).not.toContain('if (!proc.killed)');
  });

  test("registers target commands and deletes unsafe/obsolete commands", () => {
    for (const command of ["fh", "fh-model", "fh-only", "fh-opinion", "fh-fusion", "fh-debate", "fh-collaborate", "fh-lanes", "fh-auto-validate", "fh-system-prompt", "find-workflow", "create-workflow", "research-x", "fh-reset", "fh-knowledge"]) {
      expect(source).toContain(`registerCommand("${command}"`);
    }
    expect(source).not.toContain('registerCommand("fh-both"');
    expect(source).not.toContain('registerCommand("fh-thinking"');
    expect(source).not.toContain('registerCommand("fh-fusion-only"');
  });

  test("fusion has read-only sources, one full-tool fuser, and no-tools ACKs", () => {
    expect(source).toContain("withKnowledge(workerPrompt(slot, stack, prompt), packet)");
    expect(source).toContain("tools: READONLY_TOOLS");
    expect(source).toContain('SYSTEM_PROMPT_FUSION.md');
    expect(source).toContain('tools: "none"');
    expect(source).toContain('splitUtf8(fuser.text, 80_000)');
    expect(source).toContain('display: false');
    expect(source).toContain("ACK FUSION ${runId}");
    expect(prompt("USER_PROMPT_FUSION_WORKER.md")).toContain("ONLY agent allowed to modify");
    expect(prompt("USER_PROMPT_FUSION_MERGE.md")).toContain("ONLY process permitted to modify");
  });

  test("N-way debate receives all other concrete opinions", () => {
    expect(source).toContain("debateClosingPrompt(slot, prompt, round, rounds, priorSnapshot)");
    expect(source).toContain("debateRebuttalPrompt(slot, prompt, round, rounds, priorSnapshot)");
    expect(source).toContain("refusing to silently truncate any agent");
    expect(source).toContain("missingSessions");
    expect(source).toContain("requires at least 2 rounds");
    expect(source).toContain("answers.find((candidate) => candidate.slotId === source.slotId)");
    expect(source).toContain("slots.map(h.newSlotRun)");
    expect(prompt("USER_PROMPT_DEBATE_REBUTTAL.md")).toContain("all of them");
    expect(prompt("USER_PROMPT_DEBATE_REBUTTAL.md")).toContain("concrete opinion");
    expect(prompt("USER_PROMPT_DEBATE_CLOSING.md")).toContain("every other surviving agent");
  });

  test("collaborate serializes write-enabled children", () => {
    expect(source).toContain("activeWriters++");
    expect(source).toContain("maxConcurrentWriteEnabledChildren");
    expect(source).toContain("acquireWriterLease(ctx.cwd, `/fh-collaborate");
    expect(source).toContain("parseStrictJsonObject(architectRun.text");
    expect(source).toContain("tools: READONLY_TOOLS");
    expect(source).toContain("worktreeCommandsObserved");
    expect(prompt("USER_PROMPT_COLLAB_EXECUTE.md")).toContain("one shared working directory");
    expect(prompt("SYSTEM_PROMPT_COLLAB_COORDINATOR.md")).toContain("at most one write-enabled child");
    expect(prompt("SYSTEM_PROMPT_COLLAB_COORDINATOR.md")).toContain("Never launch detached/background processes");
    expect(source).toContain("await ensureSummary(artifactsDir");
  });

  test("lanes: builders write in parallel worktrees, only the architect writes the checkout", () => {
    // Every builder child runs with FULL tools but its cwd is its own lane, never ctx.cwd.
    expect(source).toContain("cwd: lane.path");
    expect(source).toContain("withKnowledge(laneWorkerPrompt(slot, stack, prompt, lane, ctx.cwd), packet, { writeCapable: true })");
    // The harness creates and commits lanes itself; the writer lease guards the one integration turn.
    expect(source).toContain('["worktree", "add", "-q", "-b", laneBranch(cwd, slotId), dir, head]');
    expect(source).toContain("acquireWriterLease(ctx.cwd, `/fh-lanes");
    expect(source).toContain('SYSTEM_PROMPT_LANE_MERGE.md');
    expect(source).toContain("filter((slot) => !slot.architect)");
    // The lane board is a belowEditor widget torn down with the command.
    expect(source).toContain("LANE_BOARD_WIDGET, undefined");
    // LANE MODE: the read-only fan-outs seat every slot in its own lane too, falling back
    // to the shared cwd only when lanes could not be seeded. Collaborate never does —
    // its tasks must see each other's writes.
    expect((source.match(/cwd: lane\?\.path \?\? ctx\.cwd/g) ?? []).length).toBe(3); // opinion, debate, fusion sources
    expect(source).toContain("const lanes = await h.seedLanes(ctx, slots);");
    expect(source).toContain('flagStr("fh-lanes").toLowerCase() !== "off"');
    expect(readFileSync(join(root, "modules", "cmd-build.ts"), "utf8")).not.toContain("seedLanes");
    // The FUSION writer and the lane integrator still work in the shared checkout.
    expect(source).toContain('sessionDir: path.join(artifactsDir, "fusion"), cwd: ctx.cwd');
    expect(source).toContain("await h.ensureSummary(artifactsDir");
    expect(prompt("USER_PROMPT_LANE_WORKER.md")).toContain("Work only inside {{LANE_PATH}}");
    expect(prompt("USER_PROMPT_LANE_WORKER.md")).toContain("never adopt another slot's name");
    expect(prompt("USER_PROMPT_LANE_MERGE.md")).toContain("ONLY process permitted to modify the main checkout");
    expect(prompt("USER_PROMPT_LANE_MERGE.md")).toContain("Do NOT create commits on the user's branch");
    expect(prompt("SYSTEM_PROMPT_LANE_MERGE.md")).toContain("Never launch detached/background processes");
  });

  test("per-row TPS is provider-response throughput, tools excluded", () => {
    // Children: segments open at spawn / tool_execution_end and close only on an
    // assistant message_end that carried output tokens.
    expect(source).toContain("tpsSegmentStart = performance.now()");
    expect(source).toContain('event.type === "tool_execution_end"');
    // Host raw-chat turns use the tps extension's boundary and credit the Main slot.
    expect(source).toContain('pi.on("before_provider_request"');
    expect(source).toContain("bumpSlotPerf(modelStack().primaryBuilder.id");
    // Throughput-weighted, division-by-zero guarded, rendered per row.
    expect(source).toContain("r.tokensOut > 0 && r.tpsSeconds > 0");
    expect(source).toContain("tps");
  });

  test("stack-declared skills and append system prompts ride Pi's repeatable flags", () => {
    expect(source).toContain('args.push("--skill", skill)');
    expect(source).toContain('args.push("--append-system-prompt", append)');
    expect(source).toContain("appendSystemPrompts: slot.appendSystemPrompts");
    expect(source).toContain("appendSystemPrompts: stack.architect.appendSystemPrompts");
  });

  test("session identities hash full model and project paths", () => {
    expect(source).toContain('createHash("sha256").update(slot.model)');
    expect(source).toContain('createHash("sha256").update(canonical)');
  });

  test("configured colors are actual hex and model bar is a widget", () => {
    expect(source).toContain("fgHex(slot.color");
    expect(source).toContain('{ placement: "belowEditor" }');
    // Pi's default footer is cleared at TUI session start (user direction 2026-08-17):
    // the ONLY setFooter call is the empty component that blanks it — the model bar
    // stays a belowEditor widget, never a footer replacement.
    const setFooterCalls = source.match(/ctx\.ui\.setFooter\(/g) ?? [];
    expect(setFooterCalls.length).toBe(1);
    expect(source).toContain("ctx.ui.setFooter(() => ({ render: () => [], invalidate() {} }))");
  });
});
