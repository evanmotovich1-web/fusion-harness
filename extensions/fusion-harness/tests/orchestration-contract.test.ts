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
    for (const command of ["fh", "fh-model", "fh-only", "fh-opinion", "fh-fusion", "fh-debate", "fh-collaborate", "fh-lanes", "fh-auto-validate", "fh-system-prompt", "find-workflow", "create-workflow", "research-x", "fh-reset", "fh-knowledge", "fh-repo-state"]) {
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
    expect(source).toContain('acquireWriterLease(ctx.cwd, "lane replacement")');
    expect(source).toContain("captureLaneRemovalEvidence(cwd, slotId)");
    expect(source).toContain("changed after removal evidence was captured");
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

  test("repo-state command is registered, local-only by default, and spawns no children", () => {
    expect(source).toContain('registerCommand("fh-repo-state"');
    const cmdRepoState = readFileSync(join(root, "modules", "cmd-repo-state.ts"), "utf8");
    // Refresh is the one fetch: explicit, bounded, and under the writer lease.
    expect(cmdRepoState).toContain('["fetch", "--no-tags", "--no-recurse-submodules", remote]');
    expect(cmdRepoState).toContain('acquireWriterLease(ctx.cwd, "/fh-repo-state refresh")');
    expect(cmdRepoState).toContain("Usage: /fh-repo-state status | refresh [remote]");
    // The state card is measured in-process — measuring repo state never costs a model call.
    expect(cmdRepoState).not.toContain("runChild");
  });

  test("measured repo-state cards ride existing child prompts as harness fact", () => {
    expect(source).toContain('HARNESS_REPO_STATE_HEADER = "----- BEGIN HARNESS REPO STATE (measured; not agent-authored) -----"');
    const cmdBuild = readFileSync(join(root, "modules", "cmd-build.ts"), "utf8");
    // The card wraps the four existing spawn prompts (proposals, delegation, execution,
    // final coordination) — no new agent is introduced to carry it.
    expect(cmdBuild).toContain("withHarnessRepoState(withKnowledge(collabProposePrompt");
    expect(cmdBuild).toContain("withHarnessRepoState(collabDelegatePrompt");
    expect(cmdBuild).toContain("withHarnessRepoState(executePrompt");
    expect(cmdBuild).toContain("withHarnessRepoState(collabCoordinatePrompt");
    expect(cmdBuild).toContain('h.save(collabDir, "repo-state.json"');
    expect(prompt("SYSTEM_PROMPT_COLLAB_COORDINATOR.md")).toContain("parent-owned");
    expect(prompt("SYSTEM_PROMPT_COLLAB_COORDINATOR.md")).toContain("exact-SHA receipt");
    expect(prompt("USER_PROMPT_COLLAB_EXECUTE.md")).toContain("parent-owned");
    expect(prompt("USER_PROMPT_COLLAB_EXECUTE.md")).toContain("FH_TASK_OUTCOME");
  });

  test("publication short-circuits and agent accounting stay agent-neutral", () => {
    const cmdBuild = readFileSync(join(root, "modules", "cmd-build.ts"), "utf8");
    // Deterministic short-circuits stop before any spawn and report zero agents.
    expect(cmdBuild).toContain("if (gate.stop) {");
    expect(cmdBuild).toContain("shortCircuit: gate.kind");
    expect(cmdBuild).toContain("agents: []");
    // In normal runs the agent roster comes only from measured child runs.
    expect(cmdBuild).toContain("agents: runs.map(toStat)");
    // Repo-state capture is in-process, never a spawned child.
    expect(cmdBuild).toContain("collectRepoState(");
  });

  test("publication is parent-owned: receipt, refresh, reauthorize, non-force exact-SHA push", () => {
    const cmdBuild = readFileSync(join(root, "modules", "cmd-build.ts"), "utf8");
    expect(cmdBuild).toContain("mintRepoActionReceipt({");
    expect(cmdBuild).toContain("authorizeRepoAction({ receipt, facts, consumedDigests");
    expect(cmdBuild).toContain("opts.consumed.add(receipt.digest)"); // single-use receipts
    expect(cmdBuild).toContain('"publication-receipt.json"'); // evidence persisted
    expect(cmdBuild).toContain("decision.nonForceFastForward");
    expect(cmdBuild).toContain("${decision.candidateSha}:refs/heads/${parsed.branch}");
    expect(cmdBuild).toContain('["push", "--no-force", parsed.remote, refspec]');
    expect(cmdBuild).toContain('refspec.startsWith("+")'); // force refspecs refused twice
  });

  test("every runtime module is Node-safe: no Bun-only APIs in modules/", () => {
    // The extension runs under pi's Node runtime; bun-green tests once masked a
    // module pi could not import. Contract: modules never USE Bun-only globals —
    // comments may mention them by name (several explain exactly this rule), so
    // strip comments before asserting.
    const stripComments = (text: string): string =>
      text
        .replace(/\/\*[\s\S]*?\*\//g, " ")
        .replace(/^[ \t]*\/\/.*$/gm, " ");
    for (const file of sourceFiles) {
      if (!file.includes(join(root, "modules"))) continue;
      const text = stripComments(readFileSync(file, "utf8"));
      expect(text.includes("import.meta.dir")).toBe(false);
      expect(/\bBun\./.test(text)).toBe(false);
    }
  });
});
