#!/usr/bin/env node
/*
 * capture-strips.mjs - renders the whole film as horizontal frame strips.
 *
 * One Chrome launch paints N complete frames side by side into an N*1920 x 1080
 * canvas (render.html ?strip=N&t0=&dt=). ffmpeg `untile=Nx1` splits each strip
 * back into N frames, pixel-identical to standalone captures of the same times.
 * This turns a 40 s film from one Chrome launch per frame into one per strip.
 *
 * Usage:
 *   node capture-strips.mjs [--fps <distinct fps>] [--per-strip <n>] [--out <dir>] [--force] [--quiet]
 *
 * Defaults: 10 distinct frames per second, 8 frames per strip, out shots/seq.
 * Existing strips are reused unless --force, so a rerun is cheap.
 */
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import * as path from "node:path";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const HERE = path.dirname(new URL(import.meta.url).pathname);
const RENDER = path.join(HERE, "render.html");
const SHOT_LIST = path.join(HERE, "shot-list.json");
const OUT_FPS = 30;
const MIN_STRIP_BYTES = 100_000;

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}
const FPS = Number(arg("--fps", "10"));
const PER_STRIP = Number(arg("--per-strip", "8"));
const OUT = path.resolve(arg("--out", path.join(HERE, "shots", "seq")));
const FORCE = process.argv.includes("--force");
const QUIET = process.argv.includes("--quiet");

function log(...a) { if (!QUIET) console.log(...a); }
function sha256(buf) { return createHash("sha256").update(buf).digest("hex"); }
function fileArg(p) { return "file://" + p.split(path.sep).map(encodeURIComponent).join("/"); }
function stripName(k) { return `strip_${String(k).padStart(3, "0")}.png`; }

function chromeFlags(width) {
  return [
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    `--window-size=${width},1080`,
    "--force-device-scale-factor=1",
    "--allow-file-access-from-files",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--disable-sync",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--mute-audio",
  ];
}
function run(args) {
  return execFileSync(CHROME, args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], timeout: 120_000 });
}
function pngSize(file) {
  const out = execFileSync("ffprobe", ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", file], { encoding: "utf8" });
  const [w, h] = out.trim().split(",").map(Number);
  return { width: w, height: h };
}

function main() {
  const shot = JSON.parse(readFileSync(SHOT_LIST, "utf8"));
  const duration = shot.render.duration_s;
  const width = PER_STRIP * 1920;
  if (width > 16384) throw new Error(`strip width ${width} exceeds the 16384 px canvas limit; lower --per-strip`);
  const frameCount = Math.round(duration * FPS);
  const stripCount = Math.ceil(frameCount / PER_STRIP);
  mkdirSync(OUT, { recursive: true });
  log(`film ${duration}s at ${FPS} distinct fps = ${frameCount} frames, ${stripCount} strips of ${PER_STRIP} at ${width}x1080`);

  /* Reuse is only safe while the inputs are unchanged. If render.html or
     shot-list.json moved since the strips were painted, the cached strips are
     stale and a rerun must repaint every one of them. Silently reusing them
     would let the film disagree with the renderer. */
  const manifestPath = path.join(OUT, "sequence.json");
  let force = FORCE;
  if (!force && existsSync(manifestPath)) {
    try {
      const prev = JSON.parse(readFileSync(manifestPath, "utf8"));
      const now = { "render.html": sha256(readFileSync(RENDER)), "shot-list.json": sha256(readFileSync(SHOT_LIST)) };
      const stale = Object.keys(now).filter((k) => !prev.inputs || prev.inputs[k] !== now[k]);
      if (stale.length) {
        force = true;
        log(`inputs changed since the cached strips (${stale.join(", ")}); repainting all strips`);
      }
    } catch {
      force = true;
      log("cached sequence.json unreadable; repainting all strips");
    }
  }

  const started = Date.now();
  const strips = [];
  for (let k = 0; k < stripCount; k++) {
    const file = path.join(OUT, stripName(k));
    const t0 = (k * PER_STRIP) / FPS;
    if (!force && existsSync(file)) {
      log(`  reuse ${stripName(k)}`);
    } else {
      rmSync(file, { force: true });
      const url = `${fileArg(RENDER)}?strip=${PER_STRIP}&t0=${t0.toFixed(3)}&dt=${(1 / FPS).toFixed(6)}`;
      run([...chromeFlags(width), "--screenshot=" + file, url]);
      if (!existsSync(file)) throw new Error("no strip written for " + stripName(k));
      const bytes = statSync(file).size;
      if (bytes < MIN_STRIP_BYTES) throw new Error(`${stripName(k)} is ${bytes} bytes, under the floor; the canvas is probably blank`);
      log(`  ${stripName(k)}  t0=${t0.toFixed(2)}s  ${bytes} bytes`);
    }
    const size = pngSize(file);
    if (size.width !== width || size.height !== 1080) {
      throw new Error(`${stripName(k)} is ${size.width}x${size.height}, expected ${width}x1080`);
    }
    const buf = readFileSync(file);
    strips.push({
      name: stripName(k), t0: Number(t0.toFixed(3)), tiles: PER_STRIP,
      bytes: buf.length, sha256: sha256(buf),
    });
  }

  const times = [];
  for (let i = 0; i < frameCount; i++) times.push(Number((i / FPS).toFixed(4)));

  const manifest = {
    schema_version: 1,
    artifact: "shots/seq/sequence.json",
    task: "3.a film sequence",
    generated_by: "capture-strips.mjs",
    chrome: { path: CHROME, version: run(["--version"]).trim() },
    fps_distinct: FPS,
    per_strip: PER_STRIP,
    output_fps: OUT_FPS,
    frames_per_distinct: OUT_FPS / FPS,
    frame_count: frameCount,
    strip_count: stripCount,
    duration_s: duration,
    strip_size: `${width}x1080`,
    grain_seed_rule: "38 + round(t * 30)",
    strip_index_pattern: "shots/seq/strip_%03d.png",
    inputs: {
      "render.html": sha256(readFileSync(RENDER)),
      "shot-list.json": sha256(readFileSync(SHOT_LIST)),
    },
    strip_consumer: `untile=${PER_STRIP}x1,setpts=N/(${FPS}*TB),fps=${OUT_FPS}`,
    strips,
    frame_times: times,
    totals: { bytes: strips.reduce((a, s) => a + s.bytes, 0), capture_ms: Date.now() - started },
  };
  writeFileSync(path.join(OUT, "sequence.json"), JSON.stringify(manifest, null, 2) + "\n");
  log(`wrote ${stripCount} strips + sequence.json to ${OUT} in ${Math.round((Date.now() - started) / 1000)}s`);
}

main();
