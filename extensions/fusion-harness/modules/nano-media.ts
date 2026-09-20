/**
 * nano-media.ts — /nano-media: the content harness.
 *
 *   brief (+ --artifact files)
 *     → evidence: live "what is winning" on the Grok seat + the account's own ledger
 *     → scout: one seat, the research partner, returns angles tied to real artifacts
 *     → draft: every seat, three candidates each, under SYSTEM_PROMPT_NANO_MEDIA.md
 *     → kill-test: deterministic — invented numbers, machine tells, CTAs, URLs, fake
 *       visuals, and the boredom test (could this exist without the brief?)
 *     → judge: every seat scores every survivor against the ledger bar
 *     → humanize: the architect rewrites the top three in the operator's voice
 *     → visual: a spec for the one real artifact (screenshot / chart from real csv /
 *       animate a real image); charts render here, animation goes to a runner hook
 *     → pack.md, ranked. Nothing here ever posts.
 *
 *   /nano-media ledger add <url> <text>   record something the operator posted
 *   /nano-media measure                   pull views/likes/replies for the ledger via Grok
 */

import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { runChild } from "./child-runner.ts";
import { orderedSlots, type ModelSlot } from "./model-stack.ts";
import { promptTemplate, withKnowledge } from "./prompt-library.ts";
import { CUSTOM_TYPE, READONLY_TOOLS, runError, runOk, toStat, type AgentRun, type HarnessDeps } from "./runtime.ts";
import { researchX } from "./x-research.ts";

export const NANO_MEDIA_MAX_CHARS = 1100;
export const NANO_MEDIA_SYSTEM_PROMPT_FILE = "SYSTEM_PROMPT_NANO_MEDIA.md";
export const LEDGER_DIR = ".nano-media";
export const LEDGER_FILE = "ledger.json";
const ARTIFACT_MAX_BYTES = 20_000;
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

// ───────────────────────── kill-test primitives ─────────────────────────

/** Machine tells. Any hit is a kill, not a warning. */
export const BANNED_PATTERNS: Array<{ re: RegExp; tell: string }> = [
	{ re: /\bdelve\b/i, tell: "delve" },
	{ re: /\bleverage\b/i, tell: "leverage" },
	{ re: /\bunlock(s|ed|ing)?\b/i, tell: "unlock" },
	{ re: /\brobust\b/i, tell: "robust" },
	{ re: /\bseamless(ly)?\b/i, tell: "seamless" },
	{ re: /\bstreamlin(e|ed|ing)\b/i, tell: "streamline" },
	{ re: /\belevate\b/i, tell: "elevate" },
	{ re: /\bsupercharge\b/i, tell: "supercharge" },
	{ re: /\bgame[- ]?changer\b/i, tell: "game-changer" },
	{ re: /\bhere'?s the (thing|kicker)\b/i, tell: "here's the thing" },
	{ re: /\blet that sink in\b/i, tell: "let that sink in" },
	{ re: /\bin today'?s\b/i, tell: "in today's" },
	{ re: /\bit'?s not about\b[^.\n]*\bit'?s about\b/i, tell: "it's not about X it's about Y" },
	{ re: /\bexcited to (share|announce)\b/i, tell: "excited to share" },
	{ re: /\bbuckle up\b/i, tell: "buckle up" },
	{ re: /\bhot take\b/i, tell: "hot take" },
	{ re: /\bat the end of the day\b/i, tell: "at the end of the day" },
	{ re: /🚀/u, tell: "rocket emoji" },
	{ re: /\b(rule|step|tip|lesson)\s*#?\d+\s*[:.]/i, tell: "numbered rule/step" },
	{ re: /\b\d+\s+(things|rules|steps|tips|lessons|ways)\b/i, tell: "N things listicle" },
	{ re: /\b(want the|link in bio|reply ['"]?\w+['"]? (and|\+)|dm me)\b/i, tell: "CTA" },
	{ re: /#\w+/, tell: "hashtag" },
	{ re: /https?:\/\/\S+/i, tell: "url" },
	{ re: /^\s*\d+\/\d+\b/m, tell: "thread numbering" },
];

export function aiSmell(text: string): string[] {
	const tells = BANNED_PATTERNS.filter((p) => p.re.test(text)).map((p) => p.tell);
	const bangs = (text.match(/!/g) ?? []).length;
	if (bangs > 1) tells.push(`${bangs} exclamation marks`);
	const emoji = (text.match(/\p{Extended_Pictographic}/gu) ?? []).length;
	if (emoji > 1) tells.push(`${emoji} emoji`);
	const lines = text.split("\n").map((l) => l.trim().toLowerCase()).filter(Boolean);
	const w = (l: string) => l.split(/\s+/)[0];
	for (let i = 0; i + 2 < lines.length; i++) {
		if (w(lines[i]).length > 2 && w(lines[i]) === w(lines[i + 1]) && w(lines[i]) === w(lines[i + 2])) {
			tells.push(`three lines opening with "${w(lines[i])}"`);
			break;
		}
	}
	return [...new Set(tells)];
}

export function extractNumbers(text: string): string[] {
	const out = new Set<string>();
	for (const m of text.matchAll(/\$?\d[\d,]*(?:\.\d+)?\s*(?:%|x\b|k\b|m\b)?/gi)) {
		const raw = m[0].replace(/[\s$]/g, "").replace(/,/g, "").toLowerCase();
		if (raw) out.add(raw);
	}
	return [...out];
}

export function unsupportedNumbers(candidate: string, sources: string[]): string[] {
	const pool = new Set(sources.flatMap(extractNumbers));
	const bare = (n: string) => n.replace(/[%xkm]$/i, "");
	const poolBare = new Set([...pool].map(bare));
	return extractNumbers(candidate).filter((n) => !/^\d$/.test(bare(n)) && !pool.has(n) && !poolBare.has(bare(n)));
}

const STOP = new Set(["about", "after", "again", "against", "because", "before", "being", "between", "cannot", "could", "during", "either", "every", "having", "instead", "itself", "little", "myself", "nothing", "others", "people", "really", "should", "something", "thing", "things", "through", "under", "where", "which", "while", "without", "would", "actually", "already", "another", "anything", "everything", "someone", "started", "wanted", "getting", "better", "pretty", "though", "around", "enough"]);

/** Distinctive tokens: words of six letters or more that carry the brief's specifics. */
export function distinctiveTokens(text: string): Set<string> {
	const out = new Set<string>();
	for (const m of text.toLowerCase().matchAll(/[a-z][a-z0-9_./-]{5,}/g)) if (!STOP.has(m[0])) out.add(m[0]);
	return out;
}

/**
 * The boredom test, deterministic half: a candidate that carries none of the brief's
 * numbers and fewer than two of its distinctive tokens could have been written without
 * the brief, and dies.
 */
export function genericity(candidate: string, brief: string): { generic: boolean; sharedNumbers: number; sharedTokens: number } {
	const briefNums = new Set(extractNumbers(brief).filter((n) => !/^\d$/.test(n)));
	const sharedNumbers = extractNumbers(candidate).filter((n) => briefNums.has(n)).length;
	const briefTok = distinctiveTokens(brief);
	const sharedTokens = [...distinctiveTokens(candidate)].filter((t) => briefTok.has(t)).length;
	return { generic: sharedNumbers === 0 && sharedTokens < 2, sharedNumbers, sharedTokens };
}

export interface Candidate { id: string; slot: string; visual: string; text: string }

export function parseCandidates(md: string, slot: string): Candidate[] {
	const out: Candidate[] = [];
	let i = 0;
	for (const m of md.matchAll(/===\s*CANDIDATE\s*\n([\s\S]*?)===\s*END/g)) {
		const body = m[1].trim();
		const visual = (body.match(/^VISUAL:\s*(.*)$/m)?.[1] ?? "NONE").trim();
		const text = body.replace(/^VISUAL:.*\n?/m, "").trim();
		if (!text) continue;
		i += 1;
		out.push({ id: `${slot}-${i}`, slot, visual, text });
	}
	return out;
}

export interface KillVerdict { killed: boolean; reasons: string[] }

export function killTest(c: Candidate, sources: string[], brief?: string): KillVerdict {
	const reasons: string[] = [];
	if (c.text.length > NANO_MEDIA_MAX_CHARS) reasons.push(`${c.text.length} chars > ${NANO_MEDIA_MAX_CHARS}`);
	const smells = aiSmell(c.text);
	if (smells.length) reasons.push(`tells: ${smells.join(", ")}`);
	const invented = unsupportedNumbers(c.text, sources);
	if (invented.length) reasons.push(`numbers not in brief/evidence: ${invented.join(", ")}`);
	if (/\b(generated|illustration|stock|ai[- ]made|render(ed)? (an? )?(image|card))\b/i.test(c.visual)) reasons.push("visual is not a real artifact");
	if (brief) {
		const g = genericity(c.text, brief);
		if (g.generic) reasons.push(`boredom test: could exist without the brief (${g.sharedNumbers} of its numbers, ${g.sharedTokens} of its specifics)`);
	}
	return { killed: reasons.length > 0, reasons };
}

export function parseScores(md: string): Map<string, { score: number; reason: string }> {
	const out = new Map<string, { score: number; reason: string }>();
	for (const m of md.matchAll(/CANDIDATE\s+([\w-]+)\s*:\s*(\d+(?:\.\d+)?)\s*\/\s*10\s*[—-]*\s*(.*)/g)) out.set(m[1], { score: Math.max(0, Math.min(10, Number(m[2]))), reason: m[3].trim() });
	return out;
}

export interface Ranked extends Candidate { score: number; votes: number; reasons: string[] }

export function rank(candidates: Candidate[], judgements: Array<Map<string, { score: number; reason: string }>>): Ranked[] {
	return candidates
		.map((c) => {
			const hits = judgements.map((j) => j.get(c.id)).filter(Boolean) as Array<{ score: number; reason: string }>;
			const score = hits.length ? hits.reduce((a, b) => a + b.score, 0) / hits.length : 0;
			return { ...c, score: Math.round(score * 10) / 10, votes: hits.length, reasons: hits.map((h) => h.reason) };
		})
		.sort((a, b) => b.score - a.score);
}

// ───────────────────────── artifacts, ledger, chart ─────────────────────────

/** Pull `--artifact <path>` flags out of the raw command text. */
export function parseArtifactFlags(raw: string): { brief: string; artifacts: string[] } {
	const artifacts: string[] = [];
	const brief = raw.replace(/--artifact[=\s]+("([^"]+)"|'([^']+)'|(\S+))/g, (_m, _q, a, b, c) => { artifacts.push(a ?? b ?? c); return ""; }).replace(/\s+/g, " ").trim();
	return { brief, artifacts };
}

/** Inline text artifacts as SOURCE blocks; images become visual hints. */
export function loadArtifacts(paths: string[], cwd: string): { sources: string; visualHints: string[]; missing: string[] } {
	const sources: string[] = [];
	const visualHints: string[] = [];
	const missing: string[] = [];
	for (const p of paths) {
		const abs = path.isAbsolute(p) ? p : path.join(cwd, p);
		if (!fs.existsSync(abs)) { missing.push(p); continue; }
		if (/\.(png|jpe?g|gif|webp|mp4|mov)$/i.test(abs)) { visualHints.push(`${p} (${fs.statSync(abs).size} bytes, an existing image/video artifact)`); continue; }
		const body = fs.readFileSync(abs, "utf-8");
		sources.push(`SOURCE ${p}:\n${body.length > ARTIFACT_MAX_BYTES ? `${body.slice(0, ARTIFACT_MAX_BYTES)}\n…(truncated)` : body}`);
	}
	return { sources: sources.join("\n\n"), visualHints, missing };
}

export interface LedgerEntry { url: string; text: string; posted_at: string; views?: number | null; likes?: number | null; replies?: number | null; bookmarks?: number | null; measured_at?: string }

export function ledgerPath(cwd: string): string { return path.join(cwd, LEDGER_DIR, LEDGER_FILE); }
export function readLedger(cwd: string): LedgerEntry[] {
	try { return JSON.parse(fs.readFileSync(ledgerPath(cwd), "utf-8")); } catch { return []; }
}
export function writeLedger(cwd: string, entries: LedgerEntry[]): void {
	fs.mkdirSync(path.dirname(ledgerPath(cwd)), { recursive: true });
	fs.writeFileSync(ledgerPath(cwd), `${JSON.stringify(entries, null, 2)}\n`);
}

/** The bar, in one paragraph, for the scout and the judges. */
export function ledgerSummary(entries: LedgerEntry[]): string {
	if (!entries.length) return "(no ledger yet: the account has no measured history in this workspace)";
	const measured = entries.filter((e) => typeof e.views === "number");
	const views = measured.map((e) => e.views as number);
	const best = measured.slice().sort((a, b) => (b.views ?? 0) - (a.views ?? 0))[0];
	const lines = [
		`The account's own ledger: ${entries.length} posts recorded, ${measured.length} measured.`,
		views.length ? `Views per post ranged ${Math.min(...views)}–${Math.max(...views)}, median ${views.slice().sort((a, b) => a - b)[Math.floor(views.length / 2)]}.` : "",
		best ? `Best so far: ${best.views} views — "${best.text.slice(0, 120).replace(/\n/g, " ")}"` : "",
		`Total likes ${measured.reduce((a, e) => a + (e.likes ?? 0), 0)}, replies from others ${measured.reduce((a, e) => a + (e.replies ?? 0), 0)}.`,
		`Anything shaped like those posts lands in the same pile. That is the bar to beat.`,
	].filter(Boolean);
	return lines.join(" ");
}

/** Ask the Grok seat for the numbers on every ledger URL; returns updated entries. */
export async function measureLedger(entries: LedgerEntry[]): Promise<LedgerEntry[]> {
	if (!entries.length) return entries;
	const handles = [...new Set(entries.map((e) => e.url.match(/x\.com\/([^/]+)\/status/)?.[1]).filter(Boolean))] as string[];
	const r = await researchX({ query: `For each of these X post URLs report, as a JSON array of objects with keys url, views, replies, reposts, likes, bookmarks, integers or null when not visible, nothing outside the JSON: ${entries.map((e) => e.url).join(" ")}`, allowedHandles: handles.length ? handles : undefined });
	const m = r.text.match(/\[[\s\S]*\]/);
	if (!m) throw new Error("measure: Grok returned no JSON array");
	const rows = JSON.parse(m[0]) as Array<Record<string, unknown>>;
	const now = new Date().toISOString();
	return entries.map((e) => {
		const row = rows.find((x) => String(x.url ?? "").includes(e.url.split("/status/")[1] ?? "∅"));
		if (!row) return e;
		const num = (v: unknown) => (typeof v === "number" ? v : null);
		return { ...e, views: num(row.views), likes: num(row.likes), replies: num(row.replies), bookmarks: num(row.bookmarks), measured_at: now };
	});
}

/** A real chart from real rows: label,value per line. Single hue, dark surface, mobile-legible. */
export function chartHtml(rows: Array<{ label: string; value: number }>, title: string, subtitle: string): string {
	const max = Math.max(1, ...rows.map((r) => r.value));
	const bars = rows.map((r) => `<div class="bar" style="height:${Math.max(4, Math.round((r.value / max) * 220))}px"><span>${r.value}</span><i>${r.label}</i></div>`).join("");
	return `<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:#0f1115;color:#e8e8e8;font:15px -apple-system,Helvetica,Arial,sans-serif;width:1200px}
.w{padding:56px 64px}h1{font-size:36px;margin:0 0 6px;color:#fff;letter-spacing:-.4px}.sub{color:#9aa3b2;font-size:17px;margin:0 0 36px}
.chart{display:flex;align-items:flex-end;gap:8px;height:250px;border-bottom:1px solid #2a2f3a}
.bar{flex:1;background:#ffb547;border-radius:4px 4px 0 0;position:relative;min-width:6px}
.bar span{position:absolute;top:-22px;left:0;right:0;text-align:center;font-size:12px;color:#c9ced8}
.bar i{position:absolute;bottom:-20px;left:0;right:0;text-align:center;font-size:10px;color:#6f7786;font-style:normal;overflow:hidden;white-space:nowrap}
.foot{margin-top:44px;color:#6f7786;font-size:14px}</style></head><body><div class="w">
<h1>${title}</h1><p class="sub">${subtitle}</p><div class="chart">${bars}</div>
<p class="foot">Every number observed, none estimated.</p></div></body></html>`;
}

export function readCsvRows(csvPath: string, labelKey: string, valueKey: string): Array<{ label: string; value: number }> {
	const [head, ...lines] = fs.readFileSync(csvPath, "utf-8").trim().split("\n");
	const cols = head.split(",");
	const li = cols.indexOf(labelKey);
	const vi = cols.indexOf(valueKey);
	if (li < 0 || vi < 0) throw new Error(`csv needs columns ${labelKey},${valueKey}; has ${cols.join(",")}`);
	const latest = new Map<string, number>();
	for (const line of lines) {
		const parts = line.split(",");
		const v = Number(parts[vi]);
		if (Number.isFinite(v)) latest.set(parts[li], v);
	}
	return [...latest].map(([label, value]) => ({ label: label.replace(/^https?:\/\/x\.com\/[^/]+\/status\//, ""), value }));
}

/** Render html to png with the operator's Chrome. Returns the png path or undefined when Chrome is absent. */
export function renderPng(html: string, outPng: string): string | undefined {
	if (!fs.existsSync(CHROME)) return undefined;
	const htmlPath = outPng.replace(/\.png$/, ".html");
	fs.writeFileSync(htmlPath, html);
	const r = spawnSync(CHROME, ["--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1200,900", `--screenshot=${outPng}`, `file://${htmlPath}`], { stdio: "ignore", timeout: 60_000 });
	return r.status === 0 && fs.existsSync(outPng) ? outPng : undefined;
}

export interface VisualSpec { kind: "screenshot" | "chart" | "animate" | "none"; instruction: string; source?: string; output?: string; higgsfield?: { model: string; prompt: string; input: string } }

/** Decide what the one visual is and, where it is a chart from real rows, make it. */
export function visualSpec(candidate: Candidate, visualHints: string[], artifactsDir: string, csvHint?: { path: string; labelKey: string; valueKey: string; title: string; subtitle: string }): VisualSpec {
	const v = candidate.visual.trim();
	if (!v || /^none$/i.test(v)) return { kind: "none", instruction: "No real artifact named. Post without media or supply one with --artifact." };
	if (csvHint && /\b(chart|graph|plot|numbers|views|csv)\b/i.test(v)) {
		const rows = readCsvRows(csvHint.path, csvHint.labelKey, csvHint.valueKey);
		const out = renderPng(chartHtml(rows, csvHint.title, csvHint.subtitle), path.join(artifactsDir, "chart.png"));
		return { kind: "chart", instruction: v, source: csvHint.path, output: out };
	}
	const img = visualHints.find((h) => /\.(png|jpe?g|webp)/i.test(h));
	if (img && /\b(animate|motion|video|clip)\b/i.test(v)) {
		const input = img.split(" ")[0];
		return { kind: "animate", instruction: v, source: input, higgsfield: { model: "kling3_0", input, prompt: `Subtle, slow push-in on this exact screenshot. No new text, no new objects, nothing invented. The image is the content.` } };
	}
	return { kind: "screenshot", instruction: v, source: img?.split(" ")[0] };
}

// ───────────────────────── prompts ─────────────────────────

export function scoutPrompt(brief: string, sources: string, evidence: string, ledger: string, visualHints: string[]): string {
	return [
		`You are the scout, the research partner. Do not draft.`,
		``, `BRIEF:`, brief.trim(),
		sources ? `\nSOURCES (files the operator supplied; these are facts):\n${sources}` : "",
		``, `EXISTING VISUAL ARTIFACTS: ${visualHints.length ? visualHints.join("; ") : "none supplied"}`,
		``, `LEDGER: ${ledger}`,
		``, `LIVE EVIDENCE (what is winning on X now):`, evidence.trim() || "(unavailable this run)",
		``, `Return: the single most surprising fact in the brief; three angles worth writing, each tied to one real artifact; three angles to avoid and why; the exact visual that already exists. Plain lines.`,
	].join("\n");
}

export function draftPrompt(brief: string, sources: string, research: string, perSlot: number): string {
	return [
		`BRIEF (the only source of facts about him; every number you use must be in here or in the sources):`, brief.trim(),
		sources ? `\nSOURCES:\n${sources}` : "",
		``, `SCOUT NOTES (angles and the one real visual; use them, do not quote them):`, research.trim() || "(no scout notes)",
		``, `Write ${perSlot} candidates, each a different angle on the same real thing. Follow the output contract exactly. Nothing outside the blocks.`,
	].join("\n");
}

export function judgePrompt(candidates: Candidate[], ledger: string): string {
	const blocks = candidates.map((c) => `--- CANDIDATE ${c.id}\nVISUAL: ${c.visual}\n${c.text}`).join("\n\n");
	return [
		`Judge these. The reader is a builder who has never heard of the author. Score only "would they stop scrolling and read to the end", 1–10. A 7 is rare; a 9 means you would repost it. Apply the boredom test: anything that could have been written without the brief scores 3 or lower.`,
		``, `THE BAR: ${ledger}`,
		``, `Use the scoring contract exactly, one line per candidate, nothing else.`,
		``, blocks,
	].join("\n");
}

export function humanizePrompt(candidates: Candidate[], voiceSample: string): string {
	const blocks = candidates.map((c) => `=== CANDIDATE\nVISUAL: ${c.visual}\n${c.text}\n=== END`).join("\n\n");
	return [
		`Rewrite these in his voice. Keep every fact, every number, the VISUAL line and the order of events exactly. Change only the voice: lowercase where he would, shorter lines, blunter, cut every word he would not type. Same contract, same order, nothing else.`,
		``, `How he actually types (verbatim):`, voiceSample.trim(), ``, blocks,
	].join("\n");
}

export function packMarkdown(brief: string, ranked: Ranked[], dead: Array<Candidate & { reasons: string[] }>, evidenceNote: string, research = "", visual?: VisualSpec): string {
	const top = ranked.map((r, i) => `## ${i + 1}. ${r.id} — ${r.score}/10 (${r.votes} judges)\nVISUAL: ${r.visual}\n\n${r.text}\n\n_judges:_ ${r.reasons.map((x) => `"${x}"`).join(" · ")}`).join("\n\n");
	const vis = visual ? `\n# Visual for #1\nkind: ${visual.kind}\n${visual.instruction}${visual.source ? `\nsource: ${visual.source}` : ""}${visual.output ? `\nrendered: ${visual.output}` : ""}${visual.higgsfield ? `\nhiggsfield: ${visual.higgsfield.model} on ${visual.higgsfield.input} — "${visual.higgsfield.prompt}"` : ""}\n` : "";
	return [
		`# nano.media pack — NOT POSTED`, ``, `Brief:`, brief.trim(), ``, `Evidence: ${evidenceNote}`, ``,
		`# Scout notes`, research.trim() || "_none_", ``,
		`# Ranked survivors`, ``, top || "_no candidate survived the kill test_", vis,
		`# Killed before judging`, dead.length ? dead.map((d) => `- ${d.id}: ${d.reasons.join("; ")}`).join("\n") : "- none", ``,
		`Post the top one yourself with its visual, then record it: /nano-media ledger add <url> <text>. Nothing here is live.`,
	].join("\n");
}

const DEFAULT_VOICE = [
	`"its all go dont stop tell i get a viral post"`,
	`"all your posts sound like ai and im reading them and im not interested at all"`,
	`"we need to be posting more"`,
	`"keep going, post the rest, make sure it all good of course, and dont ask me questions just use your judgement"`,
].join("\n");

// ───────────────────────── command ─────────────────────────

export function registerNanoMediaCommand(pi: ExtensionAPI, h: HarnessDeps): (raw: string, ctx: any) => Promise<void> {
	const handler = async (raw: string, ctx: any): Promise<void> => {
		h.noteHost(ctx);
		const input = (raw ?? "").trim();
		// ── ledger subcommands ──
		if (/^ledger\b/i.test(input)) {
			const m = input.match(/^ledger\s+add\s+(\S+)\s+([\s\S]+)$/i);
			if (m) {
				const entries = readLedger(ctx.cwd);
				entries.push({ url: m[1], text: m[2].trim(), posted_at: new Date().toISOString() });
				writeLedger(ctx.cwd, entries);
				ctx.ui.notify(`nano.media: recorded ${m[1]} (${entries.length} in ledger)`, "info");
				return;
			}
			const entries = readLedger(ctx.cwd);
			h.panel({ kind: "prompt", command: "nano-media", ok: true }, `# nano.media ledger (${entries.length})\n${ledgerSummary(entries)}\n\n${entries.map((e) => `- ${e.url} · views ${e.views ?? "?"} likes ${e.likes ?? "?"} replies ${e.replies ?? "?"} · ${e.text.slice(0, 80).replace(/\n/g, " ")}`).join("\n")}`);
			return;
		}
		if (/^measure\b/i.test(input)) {
			ctx.ui.setStatus(CUSTOM_TYPE, "nano.media: measuring the ledger on the Grok seat…");
			try {
				const updated = await measureLedger(readLedger(ctx.cwd));
				writeLedger(ctx.cwd, updated);
				h.panel({ kind: "prompt", command: "nano-media", ok: true }, `# nano.media measure\n${ledgerSummary(updated)}`);
			} catch (error) {
				ctx.ui.notify(`nano.media measure: ${error instanceof Error ? error.message : String(error)}`, "error");
			} finally { ctx.ui.setStatus(CUSTOM_TYPE, undefined); }
			return;
		}
		const { brief, artifacts } = parseArtifactFlags(input);
		if (!brief) {
			ctx.ui.notify("Usage: /nano-media [--artifact <file>]… <what actually happened, with the real numbers>  |  ledger [add <url> <text>]  |  measure", "warning");
			return;
		}
		const stack = h.modelStack();
		const slots = orderedSlots(stack);
		const architect = slots.find((s) => s.architect) ?? slots[0];
		const scoutSlot = slots.find((s) => s.primary && !s.architect) ?? slots.find((s) => !s.architect) ?? architect;
		const startedAt = Date.now();
		const artifactsDir = await h.mkArtifacts();
		await h.save(artifactsDir, "brief.md", brief);
		const loaded = loadArtifacts(artifacts, ctx.cwd);
		if (loaded.missing.length) ctx.ui.notify(`nano.media: missing artifacts ${loaded.missing.join(", ")}`, "warning");
		const systemPrompt = promptTemplate(NANO_MEDIA_SYSTEM_PROMPT_FILE);
		const sys = (slot: ModelSlot) => [systemPrompt, slot.systemPrompt].filter(Boolean).join("\n\n");
		const ledger = ledgerSummary(readLedger(ctx.cwd));
		h.panel({ kind: "prompt", command: "nano-media", ok: true }, `/nano-media ${input}`);

		// ── 1. evidence on the Grok seat ──
		ctx.ui.setStatus(CUSTOM_TYPE, "nano.media: reading what blew up on X this week…");
		let evidence = "";
		let evidenceNote = "";
		try {
			const topic = brief.slice(0, 200).replace(/\n+/g, " ");
			const r = await researchX({ query: `Research only. Last 7 days. The 10 X posts from accounts under 30,000 followers that gained the most views relative to follower count on this topic: ${topic}. For each: handle, followers, views, bookmarks, what the attached visual literally is, exact first sentence. Then 5 bullets on what the winners share. Observed data only; UNKNOWN where not visible.` });
			evidence = r.text;
			evidenceNote = `live Grok x_search, ${r.urls.length} cited urls`;
		} catch (error) {
			evidenceNote = `unavailable (${error instanceof Error ? error.message : String(error)})`;
		}
		await h.save(artifactsDir, "evidence.md", evidence || evidenceNote);
		const packet = await h.prepareKnowledge(brief, ctx.cwd, artifactsDir);

		const allRuns: AgentRun[] = [];
		const stopper = h.startStoppable(ctx, "nano-media");
		const scoutRun = h.newSlotRun(scoutSlot);
		allRuns.push(scoutRun);
		const stopWidget = h.startGridWidget(ctx, "nano-media", allRuns, undefined, startedAt);
		try {
			// ── 2. scout: the research partner ──
			ctx.ui.setStatus(CUSTOM_TYPE, `nano.media: ${scoutSlot.name} scouting angles…`);
			const scoutDir = path.join(artifactsDir, "scout");
			await fs.promises.mkdir(scoutDir, { recursive: true });
			await runChild({ run: scoutRun, prompt: withKnowledge(scoutPrompt(brief, loaded.sources, evidence, ledger, loaded.visualHints), packet), systemPrompt: sys(scoutSlot), appendSystemPrompts: scoutSlot.appendSystemPrompts, tools: READONLY_TOOLS, thinking: scoutSlot.thinking, ...h.slotInitialSpawn(scoutSlot, ctx, scoutDir), cwd: ctx.cwd, timeoutMs: h.childTimeoutMs(), signal: stopper.signal });
			const research = runOk(scoutRun) ? scoutRun.text : "";
			await h.save(scoutDir, "research.md", research || `FAILED: ${runError(scoutRun)}`);
			if (stopper.stopped()) { h.stoppedPanel("nano-media", allRuns, artifactsDir, startedAt, "Stopped during scouting."); return; }

			// ── 3. draft: every seat ──
			ctx.ui.setStatus(CUSTOM_TYPE, `nano.media: ${slots.length} seats drafting…`);
			const draftRuns = slots.map(h.newSlotRun);
			allRuns.push(...draftRuns);
			const candidates: Candidate[] = [];
			await Promise.all(draftRuns.map(async (run) => {
				const slot = run.slot!;
				const dir = path.join(artifactsDir, "draft", slot.id);
				await fs.promises.mkdir(dir, { recursive: true });
				await runChild({ run, prompt: draftPrompt(brief, loaded.sources, research, 3), systemPrompt: sys(slot), appendSystemPrompts: slot.appendSystemPrompts, tools: READONLY_TOOLS, thinking: slot.thinking, ...h.slotInitialSpawn(slot, ctx, dir), cwd: ctx.cwd, timeoutMs: h.childTimeoutMs(), signal: stopper.signal });
				await h.save(dir, "draft.md", runOk(run) ? run.text : `FAILED: ${runError(run)}`);
				if (runOk(run)) candidates.push(...parseCandidates(run.text, slot.id));
			}));
			if (stopper.stopped()) { h.stoppedPanel("nano-media", allRuns, artifactsDir, startedAt, "Drafting stopped; partial drafts remain on disk."); return; }

			// ── 4. kill-test ──
			const sources = [brief, loaded.sources, evidence];
			const dead: Array<Candidate & { reasons: string[] }> = [];
			const alive: Candidate[] = [];
			for (const c of candidates) {
				const v = killTest(c, sources, brief);
				if (v.killed) dead.push({ ...c, reasons: v.reasons }); else alive.push(c);
			}
			await h.save(artifactsDir, "kill-test.json", JSON.stringify({ alive: alive.map((c) => c.id), dead }, null, 2));
			if (!alive.length) {
				const pack = packMarkdown(brief, [], dead, evidenceNote, research);
				await h.save(artifactsDir, "pack.md", pack);
				h.panel({ kind: "error", command: "nano-media", ok: false, sources: allRuns.map(toStat), artifactsDir, ...h.totals(allRuns, startedAt) }, pack);
				return;
			}

			// ── 5. judge against the bar ──
			ctx.ui.setStatus(CUSTOM_TYPE, `nano.media: ${slots.length} seats judging ${alive.length} survivors…`);
			const judgeRuns = slots.map(h.newSlotRun);
			allRuns.push(...judgeRuns);
			const judgements: Array<Map<string, { score: number; reason: string }>> = [];
			await Promise.all(judgeRuns.map(async (run) => {
				const slot = run.slot!;
				const dir = path.join(artifactsDir, "judge", slot.id);
				await fs.promises.mkdir(dir, { recursive: true });
				await runChild({ run, prompt: judgePrompt(alive, ledger), systemPrompt: sys(slot), appendSystemPrompts: slot.appendSystemPrompts, tools: "none", thinking: slot.thinking, ...h.slotInitialSpawn(slot, ctx, dir), cwd: ctx.cwd, timeoutMs: h.childTimeoutMs(), signal: stopper.signal });
				await h.save(dir, "scores.md", runOk(run) ? run.text : `FAILED: ${runError(run)}`);
				if (runOk(run)) judgements.push(parseScores(run.text));
			}));
			if (stopper.stopped()) { h.stoppedPanel("nano-media", allRuns, artifactsDir, startedAt, "Judging stopped."); return; }
			const ranked = rank(alive, judgements);

			// ── 6. humanize the top three ──
			const top = ranked.slice(0, 3);
			let finals: Ranked[] = top;
			if (top.length) {
				ctx.ui.setStatus(CUSTOM_TYPE, `nano.media: ${architect.name} humanizing the top ${top.length}…`);
				const run = h.newSlotRun(architect);
				allRuns.push(run);
				const dir = path.join(artifactsDir, "humanize");
				await fs.promises.mkdir(dir, { recursive: true });
				await runChild({ run, prompt: humanizePrompt(top, DEFAULT_VOICE), systemPrompt: sys(architect), appendSystemPrompts: architect.appendSystemPrompts, tools: "none", thinking: architect.thinking, ...h.slotInitialSpawn(architect, ctx, dir), cwd: ctx.cwd, timeoutMs: h.childTimeoutMs(), signal: stopper.signal });
				await h.save(dir, "humanized.md", runOk(run) ? run.text : `FAILED: ${runError(run)}`);
				if (runOk(run)) {
					const rewritten = parseCandidates(run.text, "final");
					finals = top.map((orig, i) => {
						const rw = rewritten[i];
						if (!rw) return orig;
						const v = killTest({ ...rw, id: orig.id }, sources, brief);
						return v.killed ? { ...orig, reasons: [...orig.reasons, `humanized version killed: ${v.reasons.join("; ")}`] } : { ...orig, text: rw.text, visual: rw.visual || orig.visual };
					});
				}
			}

			// ── 7. the one visual ──
			let visual: VisualSpec | undefined;
			if (finals[0]) {
				const csv = artifacts.find((a) => /\.csv$/i.test(a));
				try {
					visual = visualSpec(finals[0], loaded.visualHints, artifactsDir, csv ? { path: path.isAbsolute(csv) ? csv : path.join(ctx.cwd, csv), labelKey: "url", valueKey: "views", title: finals[0].text.split("\n")[0].slice(0, 80), subtitle: "views per post, latest reading" } : undefined);
				} catch (error) {
					visual = { kind: "none", instruction: `visual failed: ${error instanceof Error ? error.message : String(error)}` };
				}
				await h.save(artifactsDir, "visual.json", JSON.stringify(visual, null, 2));
				const runner = process.env.NANO_MEDIA_VISUAL_RUNNER;
				if (runner && visual.kind === "animate") {
					const r = spawnSync(runner, [path.join(artifactsDir, "visual.json")], { stdio: "ignore", timeout: 600_000 });
					visual.instruction += r.status === 0 ? " (runner completed)" : ` (runner exit ${r.status})`;
				}
			}

			// ── 8. pack ──
			const pack = packMarkdown(brief, finals, dead, evidenceNote, research, visual);
			await h.save(artifactsDir, "pack.md", pack);
			const ok = finals.length > 0;
			h.panel({ kind: "multi", command: "nano-media", title: "◆ NANO.MEDIA — RANKED, NOT POSTED", ok, prompt: brief, sources: allRuns.map(toStat), answers: finals.map((f) => ({ role: "BUILDER" as AgentRun["role"], model: f.slot, text: `${f.score}/10 · VISUAL: ${f.visual}\n\n${f.text}`, slotId: f.slot, slotName: f.id, color: slots.find((s) => s.id === f.slot)?.color ?? architect.color, primary: false })), artifactsDir, ...h.totals(allRuns, startedAt) }, pack);
			await h.save(artifactsDir, "summary.json", JSON.stringify({ command: "nano-media", ok, candidates: candidates.length, killed: dead.length, survivors: alive.length, finals: finals.map((f) => ({ id: f.id, score: f.score })), visual: visual?.kind, evidence: evidenceNote, agents: allRuns.map(toStat), ...h.totals(allRuns, startedAt) }, null, 2));
		} finally {
			await h.ensureSummary(artifactsDir, { command: "nano-media", ok: false, stopped: stopper.stopped(), agents: allRuns.map(toStat), ...h.totals(allRuns, startedAt) });
			stopper.release();
			stopWidget();
			ctx.ui.setStatus(CUSTOM_TYPE, undefined);
		}
	};
	pi.registerCommand("nano-media", { description: "nano.media: brief (+--artifact files) → live research + ledger → scout → every seat drafts → kill-test + boredom test → cross-judge → humanize → visual spec → ranked pack. `ledger add`, `measure`. Never posts.", handler });
	return handler;
}
