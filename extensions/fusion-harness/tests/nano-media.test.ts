import { describe, expect, test } from "bun:test";
import { aiSmell, extractNumbers, killTest, packMarkdown, parseCandidates, parseScores, rank, unsupportedNumbers } from "../modules/nano-media.ts";

describe("nano.media kill-test", () => {
	test("catches machine tells, listicles, CTAs and thread numbering", () => {
		expect(aiSmell("Rule 1: leverage your robust harness 🚀🚀!!")).toEqual(expect.arrayContaining(["numbered rule/step", "leverage", "robust", "rocket emoji"]));
		expect(aiSmell("Want the checklist? Link in bio")).toContain("CTA");
		expect(aiSmell("1/7 Your agent says done")).toContain("thread numbering");
		expect(aiSmell("i let three ai agents run my x account for a day.\n\n20 posts. 120 views. 3 likes.")).toEqual([]);
	});

	test("numbers must come from the brief", () => {
		expect(extractNumbers("20 posts, 120 views, $12,500, 8x more, 80%")).toEqual(["20", "120", "12500", "8x", "80%"]);
		const brief = "20 posts. 120 views. 3 likes.";
		expect(unsupportedNumbers("20 posts and 120 views and 3 likes", [brief])).toEqual([]);
		expect(unsupportedNumbers("20 posts and 4,000 views", [brief])).toEqual(["4000"]);
	});

	test("parses candidate blocks and kills invented facts, urls and fake visuals", () => {
		const md = `=== CANDIDATE\nVISUAL: screenshot of the terminal\ni let three ai agents run my x account for a day.\n\n20 posts. 120 views.\n=== END\n\n=== CANDIDATE\nVISUAL: a generated illustration of a robot\nwe hit 5,000 views. see https://x.com/x\n=== END`;
		const cands = parseCandidates(md, "rune");
		expect(cands.map((c) => c.id)).toEqual(["rune-1", "rune-2"]);
		const sources = ["20 posts. 120 views."];
		expect(killTest(cands[0], sources)).toEqual({ killed: false, reasons: [] });
		const v = killTest(cands[1], sources);
		expect(v.killed).toBe(true);
		expect(v.reasons.join(" ")).toContain("5000");
		expect(v.reasons.join(" ")).toContain("url");
		expect(v.reasons.join(" ")).toContain("real artifact");
	});

	test("ranks by average judge score and renders a pack that says it is not posted", () => {
		const scores = parseScores("CANDIDATE rune-1: 8/10 — real numbers, real failure\nCANDIDATE flux-1: 4/10 — reads like a slide");
		expect(scores.get("rune-1")?.score).toBe(8);
		const ranked = rank([{ id: "rune-1", slot: "rune", visual: "terminal", text: "a" }, { id: "flux-1", slot: "flux", visual: "NONE", text: "b" }], [scores, parseScores("CANDIDATE rune-1: 6/10 — fine")]);
		expect(ranked[0].id).toBe("rune-1");
		expect(ranked[0].score).toBe(7);
		const pack = packMarkdown("brief", ranked, [], "live");
		expect(pack).toContain("NOT POSTED");
		expect(pack).toContain("rune-1 — 7/10");
	});
});

import { chartHtml, genericity, ledgerSummary, loadArtifacts, parseArtifactFlags, readCsvRows, visualSpec } from "../modules/nano-media.ts";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

describe("nano.media v2: research partner, ledger, artifacts, visuals", () => {
	test("boredom test kills what could exist without the brief", () => {
		const brief = "i let three ai agents run my x account. 20 posts. 120 views. codex posted 1/7 then stalled. the classifier blocked claude.";
		expect(genericity("agents are great, evaluate them carefully before production", brief).generic).toBe(true);
		expect(genericity("20 posts, 120 views, and the classifier blocked claude every time", brief).generic).toBe(false);
	});

	test("artifact flags are parsed and text artifacts are inlined, images become visual hints", () => {
		const dir = fs.mkdtempSync(path.join(os.tmpdir(), "nano-"));
		fs.writeFileSync(path.join(dir, "m.csv"), "url,views\nhttps://x.com/a/status/1,20\nhttps://x.com/a/status/1,23\nhttps://x.com/a/status/2,5\n");
		fs.writeFileSync(path.join(dir, "shot.png"), Buffer.alloc(10));
		const { brief, artifacts } = parseArtifactFlags(`--artifact m.csv --artifact "shot.png" the thing that happened`);
		expect(brief).toBe("the thing that happened");
		expect(artifacts).toEqual(["m.csv", "shot.png"]);
		const loaded = loadArtifacts(artifacts, dir);
		expect(loaded.sources).toContain("SOURCE m.csv");
		expect(loaded.visualHints[0]).toContain("shot.png");
		const rows = readCsvRows(path.join(dir, "m.csv"), "url", "views");
		expect(rows).toEqual([{ label: "1", value: 23 }, { label: "2", value: 5 }]);
		expect(chartHtml(rows, "t", "s")).toContain(">23<");
		const spec = visualSpec({ id: "x", slot: "s", visual: "animate the screenshot", text: "" }, loaded.visualHints, dir);
		expect(spec.kind).toBe("animate");
		expect(spec.higgsfield?.input).toBe("shot.png");
		expect(visualSpec({ id: "x", slot: "s", visual: "NONE", text: "" }, [], dir).kind).toBe("none");
	});

	test("ledger summary states the bar", () => {
		expect(ledgerSummary([])).toContain("no ledger yet");
		const s = ledgerSummary([{ url: "u1", text: "post one", posted_at: "t", views: 20, likes: 0, replies: 0 }, { url: "u2", text: "post two", posted_at: "t", views: 5, likes: 1, replies: 0 }]);
		expect(s).toContain("ranged 5–20");
		expect(s).toContain("Best so far: 20 views");
	});
});
