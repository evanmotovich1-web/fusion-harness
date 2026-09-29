#!/bin/bash
# Verify final-38-35.mp4. Exit non-zero on any gate failure.
set -eu
cd "$(dirname "$0")"
python3 - << 'PY'
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(".").resolve()
MP4 = ROOT / "final-38-35.mp4"
SHOT = ROOT / "shot-list.json"
CAP = ROOT / "capabilities.json"
FRAMES = ROOT / "verify-frames"
OUT = ROOT / "verification.json"
FFPROBE = "/opt/homebrew/bin/ffprobe"
FFMPEG = "/opt/homebrew/bin/ffmpeg"
PINNED_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
EXPECTED_S = 40.0
FORBIDDEN = (
    "EXTRA POINT",
    "POINT AFTER",
    "PAT GOOD",
    "KICK IS GOOD",
    "TRY IS GOOD",
    "TRY GOOD",
)

failures = []


def run(args, timeout=40):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def blob(text):
    text = text.upper().replace("–", "-").replace("—", "-")
    text = text.replace("O:0", "0:0").replace(":O", ":0")
    return " ".join(text.split())


def ffprobe():
    cmd = [FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "-show_programs", "-show_stream_groups", str(MP4)]
    proc = run(cmd, timeout=20)
    if proc.returncode != 0:
        cmd = [arg for arg in cmd if arg != "-show_stream_groups"]
        proc = run(cmd, timeout=20)
    if proc.returncode != 0:
        failures.append("ffprobe failed: " + proc.stderr[-400:])
        return {}
    data = json.loads(proc.stdout)
    data.setdefault("programs", [])
    data.setdefault("stream_groups", [])
    return data


def decode_check():
    proc = run([FFMPEG, "-v", "error", "-nostdin", "-i", str(MP4), "-f", "null", "-"], timeout=40)
    if proc.returncode != 0 or proc.stderr.strip():
        failures.append("decode check failed: " + (proc.stderr.strip() or f"exit {proc.returncode}")[:400])
        return "failed"
    return "passed"


def loudness():
    proc = run([FFMPEG, "-hide_banner", "-nostdin", "-i", str(MP4), "-af", "ebur128=peak=true", "-f", "null", "-"], timeout=40)
    text = proc.stderr
    integrated = re.search(r"Integrated loudness:\s+I:\s+(-?\d+(?:\.\d+)?)\s+LUFS", text)
    peak = re.search(r"True peak:\s+Peak:\s+(-?\d+(?:\.\d+)?)\s+dBFS", text)
    if proc.returncode != 0 or not integrated or not peak:
        failures.append("ebur128 measurement failed")
        return None, None
    i_val = float(integrated.group(1))
    p_val = float(peak.group(1))
    if not (-16.0 <= i_val <= -12.0):
        failures.append(f"integrated loudness {i_val} LUFS outside [-16, -12]")
    if p_val > -1.0:
        failures.append(f"true peak {p_val} dBTP exceeds -1")
    return i_val, p_val


def extract(dest, t):
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-ss", f"{t:.3f}", "-i", str(MP4), "-frames:v", "1", str(dest),
    ], timeout=20)
    if proc.returncode != 0 or not dest.exists():
        failures.append(f"frame extract failed at {t}")
        return False
    return True


def ocr_many(paths):
    swift = r'''
import Foundation
import Vision
import AppKit
for path in CommandLine.arguments.dropFirst() {
    let url = URL(fileURLWithPath: path)
    guard let img = NSImage(contentsOf: url),
          let tiff = img.tiffRepresentation,
          let rep = NSBitmapImageRep(data: tiff),
          let cg = rep.cgImage else {
        fputs("no image \(path)\n", stderr)
        exit(2)
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = false
    try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    let obj: [String: String] = ["path": path, "text": lines.joined(separator: "\n")]
    let data = try JSONSerialization.data(withJSONObject: obj)
    print(String(data: data, encoding: .utf8)!)
}
'''
    tmp = Path(tempfile.mkdtemp(prefix="hail-ocr-"))
    src = tmp / "ocr.swift"
    src.write_text(swift)
    binary = tmp / "ocr"
    comp = run(["/usr/bin/swiftc", "-O", "-o", str(binary), str(src)], timeout=40)
    if comp.returncode != 0:
        failures.append("swiftc OCR build failed: " + comp.stderr[-400:])
        return {}
    proc = run([str(binary), *[str(p) for p in paths]], timeout=40)
    if proc.returncode != 0:
        failures.append("OCR failed: " + proc.stderr[-400:])
        return {}
    found = {}
    for line in proc.stdout.splitlines():
        if not line.startswith("{"):
            continue
        row = json.loads(line)
        found[row["path"]] = row["text"]
    return found


def chrome_play(chrome):
    tmp = Path(tempfile.mkdtemp(prefix="hail-play-"))
    html = tmp / "play.html"
    src = MP4.resolve().as_uri()
    html.write_text(
        "<!doctype html><meta charset=utf-8><body>"
        f"<video id=v src=\"{src}\" muted autoplay playsinline></video>"
        "<pre id=out>pending</pre><script>"
        "const v=document.getElementById('v');const out=document.getElementById('out');"
        "function report(status){out.textContent=JSON.stringify({status:status,duration:v.duration,readyState:v.readyState,currentTime:v.currentTime,error:v.error?v.error.code:null});}"
        "v.addEventListener('playing',function(){report('playing');});"
        "v.addEventListener('error',function(){report('error');});"
        "v.play().then(function(){report('play-resolved');}).catch(function(e){out.textContent=JSON.stringify({status:'rejected',message:String(e)});});"
        "setTimeout(function(){if(out.textContent==='pending')report('timeout');},2500);"
        "</script></body>"
    )
    cmd = [
        chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--no-first-run", "--no-default-browser-check", "--disable-extensions",
        "--disable-background-networking", "--disable-component-update", "--disable-sync",
        "--autoplay-policy=no-user-gesture-required", "--allow-file-access-from-files",
        f"--user-data-dir={tmp / 'chrome'}", "--virtual-time-budget=4000", "--dump-dom",
        html.resolve().as_uri(),
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, _stderr = proc.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, _stderr = proc.communicate()
    match = re.search(r"<pre id=\"out\">(.*?)</pre>", stdout, re.S)
    if not match:
        match = re.search(r"<pre id=out>(.*?)</pre>", stdout, re.S)
    if not match:
        failures.append("headless Chrome did not report a play result")
        return {"status": "missing"}
    try:
        result = json.loads(match.group(1))
    except json.JSONDecodeError:
        failures.append("headless Chrome play result was not JSON")
        return {"status": "bad-json", "raw": match.group(1)[:200]}
    status = result.get("status")
    duration = result.get("duration")
    ready = result.get("readyState")
    now = result.get("currentTime") or 0
    if status not in ("play-resolved", "playing"):
        failures.append(f"Chrome play status {status}")
    if not isinstance(duration, (int, float)) or abs(float(duration) - EXPECTED_S) > 0.1:
        failures.append(f"Chrome duration {duration} not within 0.1s of 40")
    if not isinstance(ready, int) or ready < 3:
        failures.append(f"Chrome readyState {ready} below HAVE_FUTURE_DATA")
    if now <= 0:
        failures.append("Chrome currentTime did not advance")
    if result.get("error") not in (None, 0):
        failures.append(f"Chrome media error {result.get('error')}")
    result["chrome"] = chrome
    return result


def main():
    if not MP4.exists():
        failures.append("final-38-35.mp4 missing")
        OUT.write_text(json.dumps({"gates_passed": False, "failures": failures}, indent=2) + "\n")
        sys.exit(1)

    prior = None
    if OUT.exists():
        try:
            loaded = json.loads(OUT.read_text())
            if loaded.get("generated_by") == "assemble.sh":
                prior = loaded
        except json.JSONDecodeError:
            prior = None

    probe = ffprobe()
    streams = probe.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    duration = float((probe.get("format") or {}).get("duration") or 0)
    if video.get("codec_name") != "h264" or video.get("width") != 1920 or video.get("height") != 1080 or video.get("r_frame_rate") != "30/1":
        failures.append(f"video probe {video.get('codec_name')} {video.get('width')}x{video.get('height')} {video.get('r_frame_rate')}")
    if audio.get("codec_name") != "aac" or str(audio.get("sample_rate")) != "48000":
        failures.append(f"audio probe {audio.get('codec_name')} {audio.get('sample_rate')}")
    if abs(duration - EXPECTED_S) > 0.1:
        failures.append(f"duration {duration} not within 0.1s of 40")

    sha = hashlib.sha256(MP4.read_bytes()).hexdigest()
    decoded = decode_check()
    integrated, peak = loudness()

    shot = json.loads(SHOT.read_text())
    beats = []
    for beat in shot["beats"]:
        t = (beat["t_in_s"] + beat["t_out_s"]) / 2
        beats.append({"id": beat["id"], "t": t, "path": FRAMES / f"{beat['id']}-t{t:.3f}.png"})
    for beat in beats:
        extract(beat["path"], beat["t"])

    scan_times = sorted(set([b["t"] for b in beats] + [i * 2.0 + 0.5 for i in range(20)] + [20.8, 26.0]))
    scan_dir = Path(tempfile.mkdtemp(prefix="hail-scan-"))
    scan_paths = []
    for t in scan_times:
        path = scan_dir / f"t{t:.3f}.png"
        if extract(path, t):
            scan_paths.append((t, path))

    texts = ocr_many([b["path"] for b in beats] + [p for _, p in scan_paths])
    reviews = []
    for beat in beats:
        text = texts.get(str(beat["path"]), "")
        reviews.append({"id": beat["id"], "t": beat["t"], "text": text, "frame": str(beat["path"].relative_to(ROOT))})
    by_id = {row["id"]: blob(row["text"]) for row in reviews}

    pre = by_id.get("s01", "")
    huddle = by_id.get("s02", "")
    for label, text in (("s01", pre), ("s02", huddle)):
        if not ("35" in text and "32" in text and "0:04" in text):
            failures.append(f"{label} scoreboard is not 35-32 at 0:04")
        if "38-35" in text or "FRG 38" in text or "38 FRG" in text:
            failures.append(f"{label} shows the post-catch score before the snap")
    catch = by_id.get("s04", "")
    if not ("38" in catch and "35" in catch and "0:00" in catch and ("FRG 38" in catch or "38 FRG" in catch)):
        failures.append("s04 scoreboard is not 38-35 at 0:00 after the catch")
    if "32" in catch:
        failures.append("s04 still shows 32 after the catch")
    waived = by_id.get("s05", "")
    if "WAIV" not in waived or "FINAL" not in waived:
        failures.append("s05 does not show the waived try")
    card = by_id.get("s06", "")
    if "38-35" not in card or "FORGE" not in card:
        failures.append("closing card does not read 38-35 Forge")

    extra_hits = []
    for t, path in scan_paths:
        text = blob(texts.get(str(path), ""))
        hit = [phrase for phrase in FORBIDDEN if phrase in text]
        if re.search(r"\b39\b", text):
            hit.append("39")
        if hit:
            extra_hits.append({"t": t, "hit": hit})
    if extra_hits:
        failures.append("extra-point or illegal score frame: " + json.dumps(extra_hits))

    cap = json.loads(CAP.read_text())
    chrome = cap["tools"]["chrome_headless"]["path"]
    if chrome != PINNED_CHROME or not cap["tools"]["chrome_headless"].get("path_matches_nano_media_constant"):
        failures.append("Chrome path is not the nano-media pin")
    play = chrome_play(chrome) if chrome == PINNED_CHROME else {"status": "skipped"}

    whisper = cap["tools"]["whisper_asr"]
    whisper_check = "skipped"
    if whisper.get("present"):
        failures.append("whisper is present but this verifier has no transcript gate")
        whisper_check = "required-missing"

    result = {
        "programs": probe.get("programs") or [],
        "stream_groups": probe.get("stream_groups") or [],
        "streams": streams,
        "format": probe.get("format") or {},
        "sha256": sha,
        "decode_check": decoded,
        "visual_review_seconds": [row["t"] for row in reviews],
        "transcript_words_verified": None,
        "gates_passed": not failures,
        "failures": failures,
        "duration_s": duration,
        "duration_target_s": EXPECTED_S,
        "duration_tolerance_s": 0.1,
        "loudness": {
            "integrated_lufs": integrated,
            "true_peak_dbtp": peak,
            "window_lufs": [-16.0, -12.0],
            "peak_ceiling_dbtp": -1.0,
        },
        "scoreboard": {
            "before_snap": "35-32 at 0:04 on s01 and s02",
            "after_catch": "38-35 at 0:00 on s04",
            "closing_card": "38-35 Forge on s06",
            "extra_point_frames": extra_hits,
            "sample_step_s": 2.0,
            "frames": reviews,
        },
        "chrome_play": play,
        "whisper_check": whisper_check,
        "bytes": MP4.stat().st_size,
    }
    if prior:
        result["assembly_record"] = {
            "sha256": prior.get("sha256"),
            "bytes": prior.get("bytes"),
            "generated_by": prior.get("generated_by"),
        }
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(f"sha256 {sha}")
    print(f"duration {duration} decode {decoded} I {integrated} TP {peak}")
    print(f"chrome {play.get('status')} whisper {whisper_check}")
    if failures:
        print("GATE FAILURES:")
        for item in failures:
            print(f"  - {item}")
        sys.exit(1)
    print("GATE GREEN")


if __name__ == "__main__":
    main()
PY
