#!/usr/bin/env node
/*
 * capture.mjs - deterministic frame capture for "The Hail Mary at Zero".
 *
 * Drives headless Chrome over render.html once per planned frame and writes PNGs
 * into shots/. The frame plan comes from render.html itself (?state=1), so the
 * renderer and the capturer can never disagree about beats, times, or strings.
 *
 * Usage:
 *   node capture.mjs [--out <dir>] [--quiet]
 *
 * Determinism: Chrome flags are fixed and every frame is a separate launch at a
 * fixed film time. No network is used.
 *
 * Chrome note: this does NOT pass --user-data-dir. Measured on Chrome 153 here, a
 * headless run with an explicit --user-data-dir writes the screenshot and then
 * never exits (still alive after 25 s, killed by alarm). The same run without the
 * flag exits 0 in about 2 s and produces a byte-identical PNG. This matches the
 * repo's own precedent in extensions/fusion-harness/modules/nano-media.ts, which
 * also calls Chrome with no profile directory.
 */
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync, statSync } from "node:fs";
import * as path from "node:path";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const HERE = path.dirname(new URL(import.meta.url).pathname);
const RENDER = path.join(HERE, "render.html");
const SHOT_LIST = path.join(HERE, "shot-list.json");
const MIN_PNG_BYTES = 10_000;

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}
const OUT = path.resolve(arg("--out", path.join(HERE, "shots")));
const QUIET = process.argv.includes("--quiet");

function log(...a) { if (!QUIET) console.log(...a); }
function sha256(buf) { return createHash("sha256").update(buf).digest("hex"); }
function fileArg(p) { return "file://" + p.split(path.sep).map(encodeURIComponent).join("/"); }

function chromeFlags() {
  return [
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    "--window-size=1920,1080",
    "--force-device-scale-factor=1",
    "--allow-file-access-from-files",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--disable-sync",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-client-side-phishing-detection",
    "--mute-audio",
  ];
}

function run(args) {
  return execFileSync(CHROME, args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], timeout: 45_000 });
}

function readPlan() {
  const dom = run([...chromeFlags(), "--dump-dom", fileArg(RENDER) + "?state=1"]);
  const m = dom.match(/<pre id="frame-states">([\s\S]*?)<\/pre>/);
  if (!m) throw new Error("render.html did not emit #frame-states; check for a render error");
  const raw = m[1].replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").trim();
  const plan = JSON.parse(raw);
  if (!Array.isArray(plan.frames) || plan.frames.length === 0) throw new Error("frame plan is empty");
  return plan;
}

function main() {
  for (const f of [CHROME, RENDER, SHOT_LIST]) if (!existsSync(f)) throw new Error("missing required path: " + f);
  mkdirSync(OUT, { recursive: true });

  const started = Date.now();
  const plan = readPlan();
  log(`plan: ${plan.frames.length} frames from ${path.basename(RENDER)}`);

  const frames = [];
  for (const f of plan.frames) {
    const out = path.join(OUT, f.name);
    rmSync(out, { force: true });
    const url = `${fileArg(RENDER)}?t=${f.t_s}&beat=${f.beat}`;
    run([...chromeFlags(), "--screenshot=" + out, url]);
    if (!existsSync(out)) throw new Error("no screenshot written for " + f.name);
    const bytes = statSync(out).size;
    if (bytes < MIN_PNG_BYTES) throw new Error(`${f.name} is ${bytes} bytes, under the ${MIN_PNG_BYTES} floor; the canvas is probably blank`);
    const buf = readFileSync(out);
    frames.push({
      index: f.index, name: f.name, beat: f.beat, tag: f.tag, t_s: f.t_s,
      frame_index: f.frame_index, grain_seed: f.grain_seed, look: f.look,
      scoreboard_line: f.scoreboard_line, clock: f.clock, ledger: f.ledger,
      bytes, sha256: sha256(buf),
    });
    log(`  ${f.name}  ${bytes} bytes`);
  }

  const chromeVersion = run(["--version"]).trim();
  const manifest = {
    schema_version: 1,
    artifact: "shots/frames.json",
    task: "2.b deterministic frame capture",
    generated_by: "capture.mjs",
    chrome: { path: CHROME, version: chromeVersion },
    determinism: {
      flags: chromeFlags(),
      grain_seed_rule: plan.grain_seed_rule,
      catch_fraction: plan.catch_fraction,
      note: "One Chrome launch per frame at a fixed t, no profile directory. Re-running with the same inputs must reproduce these sha256 values.",
    },
    inputs: {
      "render.html": sha256(readFileSync(RENDER)),
      "shot-list.json": sha256(readFileSync(SHOT_LIST)),
    },
    resolution: plan.resolution,
    fps: plan.fps,
    frames,
    totals: { frames: frames.length, bytes: frames.reduce((a, f) => a + f.bytes, 0), capture_ms: Date.now() - started },
  };
  writeFileSync(path.join(OUT, "frames.json"), JSON.stringify(manifest, null, 2) + "\n");
  writeFileSync(path.join(OUT, "frames.sha256"),
    frames.map((f) => `${f.sha256}  ${f.name}`).join("\n") + "\n");
  log(`wrote ${frames.length} frames + frames.json + frames.sha256 to ${OUT}`);
  log(`sha256 manifest: ${sha256(Buffer.from(frames.map((f) => f.sha256).join(""))).slice(0, 16)} (frames digest)`);
}

main();
