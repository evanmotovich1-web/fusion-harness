import { afterEach, describe, expect, test } from "bun:test";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import selfCompact, { parseThresholdValue, resolveThresholds, renderBar, classifyLevel,
 buildCompactionInstructions, coalesceFlag, FLAGS, PROMPT_FILES, summarize } from "./self-compact.ts";
const W = 1_000_000;
const dirs: string[] = [];
afterEach(() => dirs.splice(0).forEach(dir => rmSync(dir, { recursive: true, force: true })));
function fixture(files: Record<string, string> = {}) {
 const dir = mkdtempSync(join(import.meta.dir, ".test-")); dirs.push(dir);
 mkdirSync(join(dir, ".pi/self-compact"), { recursive: true });
 for (const [name, content] of Object.entries(files)) writeFileSync(join(dir, ".pi/self-compact", name), content);
 return dir;
}
function harness(flags: Record<string,string> = {}, files: Record<string,string> = {}) {
 const handlers = new Map<string, Function>(), commands = new Map<string, any>(), tools = new Map<string, any>();
 const messages: any[] = [], entries: any[] = [], compacts: any[] = [], widgets: any[] = [], notices: any[] = [];
 const registrations: string[] = [];
 const pi: any = { on: (name: string, cb: Function) => handlers.set(name, cb),
  registerFlag: (name: string) => registrations.push(name), getFlag: (name: string) => flags[name],
  registerCommand: (name: string, command: any) => commands.set(name, command), registerTool: (tool: any) => tools.set(tool.name, tool),
  sendMessage: (message: any, options: any) => messages.push({ ...message, options }),
  appendEntry: (customType: string, data: any) => entries.push({ type: "custom", customType, data }) };
 let tokens: number | null = 0, window = W;
 const ctx: any = { cwd: fixture(files), hasUI: true, model: { contextWindow: W, maxTokens: 8192 },
  sessionManager: { getBranch: () => entries }, getContextUsage: () => ({ tokens, contextWindow: window }),
  compact: (opts: any) => compacts.push(opts), isIdle: () => true,
  ui: { setWidget: (_: string, lines: string[]) => widgets.push(lines), notify: (text: string) => notices.push(text) } };
 selfCompact(pi);
 return { ctx, tools, flags, handlers, registrations, messages, entries, compacts, widgets, notices,
  usage: (value: number | null, w = W) => { tokens = value; window = w; ctx.model.contextWindow = w; },
  fire: async (name: string, event: any = {}) => handlers.get(name)?.(event, ctx),
  tool: async (note_to_self = "Goal: finish. Done: parser. Path: /project/a.ts. Tests: pass. Next: meter.") => tools.get("self_compaction").execute("id", { note_to_self }, undefined, undefined, ctx),
  command: async (note = "") => commands.get("self-compact").handler(note, ctx),
 };
}
describe("thresholds", () => {
 for (const [value, tokens] of [["250000",250000],["350K",350000],["0.25m",250000],["1M",W]] as const)
  test(`parses ${value}`, () => expect(parseThresholdValue(value,"f")).toEqual({ kind:"tokens",tokens }));
 for (const bad of ["", " ", "-1", "0", "0k", "0%", "100%", "Infinity", "1.2", "0.0001k", "9007199254740992", "99999999999999999m", "10%%"])
  test(`rejects ${JSON.stringify(bad)}`, () => expect(() => parseThresholdValue(bad,"compact-at")).toThrow(/compact-at/));
 test("defaults 250k/350k/400k", () => expect(resolveThresholds({ window:W })).toMatchObject({ soft:250000,warning:350000,force:400000 }));
 test("percentage thresholds", () => expect(resolveThresholds({window:W,softSpec:"20%",warningSpec:"50%",bufferSpec:"10%"})).toMatchObject({soft:200000,warning:500000,force:600000}));
 test("mixed units", () => expect(resolveThresholds({window:W,softSpec:"250k",warningSpec:"35%",bufferSpec:"50k"})).toMatchObject({soft:250000,warning:350000,force:400000}));
 test("token launch on 1M", () => expect(resolveThresholds({window:W,softSpec:"100k",warningSpec:"200k",bufferSpec:"50k"})).toMatchObject({soft:100000,warning:200000,force:250000}));
 for (const bufferSpec of ["0","0%","0k","0M"]) test(`zero buffer ${bufferSpec}`, () => {
  const t = resolveThresholds({window:W,bufferSpec}); expect(t.force).toBe(t.warning);
 });
 test("small window defaults and partially overridden defaults stay ordered", () => {
  for (const window of [32768,128000,200001]) {
   const t = resolveThresholds({window}); expect(t.force).toBeLessThanOrEqual(Math.floor(window*0.9)); expect(t.soft).toBeLessThan(t.warning);
   expect(resolveThresholds({window,bufferSpec:"0"}).force).toBe(t.warning);
  }
 });
 test("rejects over cap, order and rounding to zero", () => {
  for (const input of [{window:W,warningSpec:"85%",bufferSpec:"10%"},{window:W,softSpec:"40%",warningSpec:"20%"},{window:100,softSpec:"0.01%"},{window:NaN}])
   expect(() => resolveThresholds(input)).toThrow();
 });
 test("aliases reject conflicts", () => expect(() => coalesceFlag(n => n === "a" ? "20%" : "30%","a","b")).toThrow(/conflicting/));
 test("exact boundaries", () => {
  const t = resolveThresholds({window:W});
  expect([249999,250000,350000,400000].map(n=>classifyLevel(n,t))).toEqual(["ok","soft","warning","forced"]);
 });
});
describe("20-cell meter", () => {
 test("40% with half cached and markers ahead", () => {
  const t = resolveThresholds({window:W,softSpec:"20%",warningSpec:"50%",bufferSpec:"10%"});
  expect(renderBar({usedTokens:400000,cacheTokens:200000,thresholds:t}).bar).toBe("[####/===--!-!-------]");
 });
 test("token markers at 10/20/25%", () => {
  const t = resolveThresholds({window:W,softSpec:"100k",warningSpec:"200k",bufferSpec:"50k"});
  const bar = renderBar({usedTokens:0,thresholds:t}).bar.slice(1,-1);
  expect(bar.length).toBe(20); expect(bar[2]).toBe("/"); expect(bar[4]).toBe("!"); expect(bar[5]).toBe("!");
 });
 test("zero-buffer marker always visible", () => expect(renderBar({usedTokens:0,thresholds:resolveThresholds({window:W,bufferSpec:"0"})}).bar[8]).toBe("|"));
 for (const pct of [0,10,20,25,40,50,60,100]) test(`${pct}% stays 20 cells`, () => {
  const m = renderBar({usedTokens:pct*10000,thresholds:resolveThresholds({window:W})}); expect(m.bar.length).toBe(22); expect(m.percent).toBe(pct);
 });
 test("unknown usage and cache", () => {
  const m=renderBar({usedTokens:null,thresholds:resolveThresholds({window:W})}); expect(m.percent).toBeNull(); expect(m.legend).toContain("unknown"); expect(m.bar).not.toContain("#");
 });
});
describe("agent lifecycle", () => {
 test("tool and flags load; flags populated after factory take effect", async () => {
  const h=harness(); expect(h.registrations).toHaveLength(6); expect(h.tools.has("self_compaction")).toBe(true);
  h.flags[FLAGS.softAlias]="10%"; h.flags[FLAGS.warningAlias]="20%"; h.flags[FLAGS.buffer]="5%";
  await h.fire("session_start"); expect(h.widgets.at(-1)[0]).toContain("force 25%");
 });
 test("invalid settings block ordinary tools and surface error", async () => {
  const h=harness({[FLAGS.softAlias]:"banana"}); await h.fire("session_start");
  expect(await h.fire("tool_call",{toolName:"bash"})).toMatchObject({block:true}); expect(h.notices.join()).toContain("banana");
 });
 test("soft and warning are live model messages without compaction or blocking", async () => {
  const h=harness({}, {[PROMPT_FILES.soft]:"Soft {{TOKENS}}/{{WINDOW}} {{PERCENT}}",[PROMPT_FILES.warning]:"Warning {{WARNING}}; hard {{FORCE}}"});
  h.usage(260000); await h.fire("turn_end"); await h.fire("turn_end");
  expect(h.messages).toHaveLength(1); expect(h.messages[0].content).toBe("Soft 260000/1000000 26");
  h.usage(360000); await h.fire("turn_end"); expect(h.messages.at(-1).content).toBe("Warning 350000; hard 400000");
  expect(await h.fire("tool_call",{toolName:"bash"})).toBeUndefined(); expect(h.compacts).toHaveLength(0);
 });
 test("force is checked at tool call and blocks every ordinary tool", async () => {
  const h=harness(); h.usage(400000);
  for (const toolName of ["read","bash","write","edit","grep","other_extension"])
   expect(await h.fire("tool_call",{toolName})).toMatchObject({block:true});
  expect(await h.fire("tool_call",{toolName:"self_compaction"})).toBeUndefined();
 });
 test("tool saves note, queues after result, compacts once and resumes once", async () => {
  const h=harness(); await h.tool("MY NOTE"); expect(h.compacts).toHaveLength(0); expect(h.entries[0].data.note_to_self).toBe("MY NOTE");
  await h.fire("turn_end"); await h.fire("turn_end"); expect(h.compacts).toHaveLength(1);
  h.usage(null); await h.fire("session_compact"); h.compacts[0].onComplete({}); h.compacts[0].onComplete({});
  expect(h.messages.filter(m=>m.options.triggerTurn)).toHaveLength(1);
  expect(await h.fire("tool_call",{toolName:"bash"})).toBeUndefined();
 });
 test("failed forced compaction retains fence and note, no retry storm", async () => {
  const h=harness(); h.usage(410000); await h.tool("KEEP NOTE"); await h.fire("turn_end");
  await h.fire("session_compact_failed",{errorMessage:"provider failure"}); h.compacts[0].onError(new Error("provider failure"));
  await h.fire("agent_settled"); expect(h.compacts).toHaveLength(1);
  expect(await h.fire("tool_call",{toolName:"read"})).toMatchObject({block:true});
  await h.tool("RETRY NOTE"); await h.fire("turn_end"); expect(h.compacts).toHaveLength(2);
 });
 test("forced unattended fallback attempts once when settled", async () => {
  const h=harness(); h.usage(410000); await h.fire("agent_settled"); await h.fire("agent_settled"); expect(h.compacts).toHaveLength(1);
 });
 test("manual command preserves note", async () => { const h=harness(); await h.command("manual note"); expect(h.compacts).toHaveLength(1); expect(h.entries[0].data.note_to_self).toBe("manual note"); });
 test("empty note rejected", async () => { const h=harness(); await expect(h.tool(" ")).rejects.toThrow(/empty/); });
 test("session switch clears cache and old completion cannot resume", async () => {
  const h=harness(); h.usage(400000); await h.fire("message_end",{message:{role:"assistant",usage:{cacheRead:200000}}});
  await h.tool(); await h.fire("turn_end"); h.usage(0); await h.fire("session_start",{reason:"resume"}); h.compacts[0].onComplete({});
  expect(h.messages.filter(m=>m.options.triggerTurn)).toHaveLength(0); expect(h.widgets.at(-1)[0]).not.toContain("#");
 });
 test("model change moves thresholds and clears stale force", async () => {
  const h=harness({[FLAGS.softAlias]:"10%",[FLAGS.warningAlias]:"20%",[FLAGS.buffer]:"5%"});
  h.usage(300000); await h.fire("turn_end"); h.usage(300000,2000000); await h.fire("model_select");
  expect(await h.fire("tool_call",{toolName:"read"})).toBeUndefined(); expect(h.widgets.at(-1)[0]).toContain("force 25% (500000)");
 });
});
describe("replacement summary", () => {
 const event = () => ({ preparation: { messagesToSummarize:[{role:"user",content:"OLD WORK"}],turnPrefixMessages:[{role:"assistant",content:"PARTIAL"}],previousSummary:"PRIOR SUMMARY",firstKeptEntryId:"keep-42",tokensBefore:350000 }, signal:new AbortController().signal,customInstructions:"USER GUIDANCE" });
 test("literal exactly replaces system prompt; note separate from saved file", () => {
  expect(buildCompactionInstructions("  LITERAL\n",{compaction:"FILE",warning:"WARNING"},"NOTE")).toBe("  LITERAL\n");
  expect(buildCompactionInstructions(undefined,{compaction:"FILE",warning:"WARNING"},"NOTE")).toBe("FILE");
  expect(buildCompactionInstructions(undefined,{compaction:null,warning:null})).toContain("Summarize");
 });
 test("summary sends full handoff data and preserves Pi metadata", async () => {
  const h=harness(); let request:any,options:any;
  h.ctx.modelRegistry={complete:async (_:any,r:any,o:any)=>{request=r;options=o;return {content:[{type:"text",text:"SUMMARY"}],usage:{input:20},stopReason:"stop"};}};
  const e=event(); const result=await summarize(e,h.ctx,"EXACT SYSTEM","SAVED NOTE",JSON.stringify);
  expect(request.systemPrompt).toBe("EXACT SYSTEM");
  for (const text of ["SAVED NOTE","PRIOR SUMMARY","OLD WORK","PARTIAL","USER GUIDANCE"]) expect(request.messages[0].content[0].text).toContain(text);
  expect(options.signal).toBe(e.signal); expect(result).toEqual({summary:"SUMMARY",firstKeptEntryId:"keep-42",tokensBefore:350000,usage:{input:20}});
 });
 for (const stopReason of ["error","aborted","length"]) test(`rejects ${stopReason}`,async()=>{
  const h=harness();h.ctx.modelRegistry={complete:async()=>({stopReason,content:[{type:"text",text:"partial"}]})};
  await expect(summarize(event(),h.ctx,"SYSTEM","NOTE",JSON.stringify)).rejects.toThrow();
 });
 test("empty summary fails",async()=>{const h=harness();h.ctx.modelRegistry={complete:async()=>({content:[],stopReason:"stop"})};await expect(summarize(event(),h.ctx,"SYSTEM","NOTE",JSON.stringify)).rejects.toThrow(/empty/);});
 test("already aborted makes no provider call",async()=>{const h=harness();const e=event();e.signal=AbortSignal.abort();await expect(summarize(e,h.ctx,"S","N",JSON.stringify)).rejects.toThrow(/aborted/);});
 test("hook cancels failure instead of falling back to built-in prompt",async()=>{const h=harness();h.ctx.model=undefined;expect(await h.fire("session_before_compact",event())).toEqual({cancel:true});});
});


test("compaction without sufficient relief does not create automatic loop", async () => {
 const h=harness({[FLAGS.softAlias]:"10",[FLAGS.warningAlias]:"20",[FLAGS.buffer]:"10"});
 h.usage(130); await h.fire("agent_settled"); expect(h.compacts).toHaveLength(1);
 await h.fire("session_compact"); h.compacts[0].onComplete({});
 for (let i=0;i<5;i++) { await h.fire("turn_end"); await h.fire("agent_settled"); }
 expect(h.compacts).toHaveLength(1);
 expect(h.widgets.at(-1).join()).toContain("Automatic compaction paused");
 expect(await h.fire("tool_call",{toolName:"read"})).toMatchObject({block:true});
 h.usage(5); await h.fire("turn_end"); h.usage(130); await h.fire("agent_settled");
 expect(h.compacts).toHaveLength(2);
});

test("default thresholds at 40% with half the used context cached", () => {
 const m=renderBar({usedTokens:400000,cacheTokens:200000,thresholds:resolveThresholds({window:W})});
 expect(m.bar).toBe("[####=/=!!-----------]"); expect(m.percent).toBe(40);
});

test("empty explicit prompt is rejected rather than silently using the file", async () => {
 const h=harness({[FLAGS.prompt]:" "}); await h.fire("session_start");
 expect(await h.fire("tool_call",{toolName:"self_compaction"})).toMatchObject({block:true});
 expect(h.notices.join()).toContain("prompt must not be empty");
});
