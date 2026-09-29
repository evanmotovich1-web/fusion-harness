#!/usr/bin/env bash
#
# assemble.sh - builds final-38-35.mp4 for "The Hail Mary at Zero".
#
# Pipeline, all local, no network, nothing committed:
#   1. shots/seq/strip_%03d.png   frames painted by render.html, 8 whole frames per strip
#   2. audio/mix.wav              the mastered 40 s bed from task 2.c
#   3. ffmpeg untile            splits each strip back into 8 frames, pixel-identical
#      setpts + fps             relabels 10 distinct fps and duplicates to 30 fps
#      libx264 + aac            h264 1920x1080 30 fps, aac 48 kHz stereo, 40.000 s
#   4. gates                     decode, stream shape, frame count, ebur128 loudness
#
# Usage:
#   ./assemble.sh [--force]     --force re-renders every strip before encoding
#
# Every step is deterministic and rerunnable. Text is burned in by the renderer,
# never by ffmpeg (drawtext is unavailable on this ffmpeg build), and no colour
# grade is applied here (the grade is painted in canvas, per sound-palette.md).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

FORCE=""
[ "${1:-}" = "--force" ] && FORCE="--force"

SEQ="shots/seq"
OUT="final-38-35.mp4"
TARGET_DURATION=40
TARGET_FPS=30

# ---------------------------------------------------------------- 1. frames
if [ -n "$FORCE" ] || [ ! -f "$SEQ/sequence.json" ]; then
  echo "== rendering film strips =="
  node capture-strips.mjs $FORCE
else
  echo "== reusing $SEQ/sequence.json (use --force to re-render) =="
fi

read_json() { python3 -c "import json,sys;print(json.load(open('$SEQ/sequence.json'))['$1'])"; }
FPS_DISTINCT="$(read_json fps_distinct)"
PER_STRIP="$(read_json per_strip)"
OUT_FPS="$(read_json output_fps)"
FRAME_COUNT="$(read_json frame_count)"
DURATION="$(read_json duration_s)"
STRIP_COUNT="$(read_json strip_count)"

echo "sequence: ${FRAME_COUNT} frames, ${FPS_DISTINCT} distinct fps, ${STRIP_COUNT} strips of ${PER_STRIP}"

# ---------------------------------------------------------------- 2. encode
echo "== encoding $OUT =="
ffmpeg -hide_banner -nostats -loglevel warning -y \
  -framerate "$FPS_DISTINCT" \
  -i "$SEQ/strip_%03d.png" \
  -i "audio/mix.wav" \
  -filter_complex "[0:v]untile=${PER_STRIP}x1,setpts=N/(${FPS_DISTINCT}*TB),fps=${OUT_FPS},format=yuv420p[v]" \
  -map "[v]" -map "1:a" \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -t "$TARGET_DURATION" -movflags +faststart \
  "$OUT"

# ---------------------------------------------------------------- 3. gates
echo "== gates =="
python3 - "$OUT" "$DURATION" "$TARGET_FPS" "$FRAME_COUNT" "$SEQ/sequence.json" <<'PY'
import hashlib, json, subprocess, sys

out, duration, fps, frame_count, seq_path = sys.argv[1], float(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]

def ff(args):
    return subprocess.run(["ffmpeg", *args], capture_output=True, text=True)

def probe(args):
    return subprocess.run(["ffprobe", "-v", "error", *args], capture_output=True, text=True).stdout

failures = []

streams = json.loads(probe(["-show_entries", "stream=codec_name,codec_type,width,height,r_frame_rate,sample_rate,channels",
                            "-show_entries", "format=duration", "-of", "json", out]))
video = [s for s in streams["streams"] if s.get("codec_type") == "video"]
audio = [s for s in streams["streams"] if s.get("codec_type") == "audio"]
if not video: failures.append("no video stream")
if not audio: failures.append("no audio stream")
if video:
    v = video[0]
    if v.get("codec_name") != "h264": failures.append(f"video codec {v.get('codec_name')} != h264")
    if (v.get("width"), v.get("height")) != (1920, 1080): failures.append(f"video size {v.get('width')}x{v.get('height')} != 1920x1080")
    if v.get("r_frame_rate") != f"{fps}/1": failures.append(f"r_frame_rate {v.get('r_frame_rate')} != {fps}/1")
if audio:
    a = audio[0]
    if a.get("codec_name") != "aac": failures.append(f"audio codec {a.get('codec_name')} != aac")
    if a.get("sample_rate") != "48000": failures.append(f"audio rate {a.get('sample_rate')} != 48000")
    if a.get("channels") != 2: failures.append(f"audio channels {a.get('channels')} != 2")
measured_duration = float(streams["format"]["duration"])
if abs(measured_duration - duration) > 0.05: failures.append(f"duration {measured_duration} != {duration}")

packets = probe(["-select_streams", "v:0", "-count_packets", "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", out]).strip()
expected_packets = int(round(duration * fps))
if packets != str(expected_packets): failures.append(f"video packets {packets} != {expected_packets}")

decode = ff(["-v", "error", "-i", out, "-f", "null", "-"])
if decode.returncode != 0 or decode.stderr.strip():
    failures.append(f"decode check failed: {decode.stderr.strip()[:200]}")

loud = ff(["-hide_banner", "-i", out, "-af", "ebur128=peak=true", "-f", "null", "-"])
text = loud.stderr
integrated = None
true_peak = None
for line in text.splitlines():
    line = line.strip()
    if line.startswith("I:") and "LUFS" in line: integrated = float(line.split()[1])
    if line.startswith("Peak:") and "dBFS" in line: true_peak = float(line.split()[1])
if integrated is None or true_peak is None:
    failures.append("ebur128 produced no I/Peak summary")
else:
    if not (-16.0 <= integrated <= -12.0): failures.append(f"integrated {integrated} LUFS outside [-16, -12]")
    if true_peak > -1.0: failures.append(f"true peak {true_peak} dBTP above -1.0")

# Encode quality against the exact reference the encoder was fed: the strip
# sequence split back into frames and resampled to the output rate. This compares
# the decoded mp4 frame by frame with the pixels render.html painted.
seq_meta = json.load(open(seq_path))
STRIP_PATTERN = "shots/seq/strip_%03d.png"
ref = f"[0:v]untile={seq_meta['per_strip']}x1,setpts=N/({seq_meta['fps_distinct']}*TB),fps={seq_meta['output_fps']},format=yuv420p[ref]"
enc = "[1:v]format=yuv420p[enc]"

def quality(filter_name):
    args = ["-hide_banner", "-framerate", str(seq_meta["fps_distinct"]), "-i", STRIP_PATTERN, "-i", out,
            "-filter_complex", f"{ref};{enc};[ref][enc]{filter_name}", "-f", "null", "-"]
    r = ff(args)
    return r.stdout + r.stderr

import re
q_psnr = quality("psnr")
q_ssim = quality("ssim")
m_psnr = re.findall(r"average:([0-9.]+) min:([0-9.]+)", q_psnr)
m_ssim = re.findall(r"All:([0-9.]+)", q_ssim)
psnr_avg = float(m_psnr[-1][0]) if m_psnr else None
psnr_min = float(m_psnr[-1][1]) if m_psnr else None
ssim_all = float(m_ssim[-1]) if m_ssim else None
if psnr_avg is None: failures.append("psnr filter produced no average")
elif psnr_avg < 38.0: failures.append(f"psnr average {psnr_avg} below 38 dB")
if ssim_all is None: failures.append("ssim filter produced no All value")
elif ssim_all < 0.97: failures.append(f"ssim {ssim_all} below 0.97")

sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
seq = json.load(open(seq_path))
result = {
    "schema_version": 1,
    "artifact": "self-compact/hail-mary/final-38-35.mp4",
    "task": "3.a assembly",
    "generated_by": "assemble.sh",
    "gates_passed": not failures,
    "failures": failures,
    "video": {"codec": video[0].get("codec_name") if video else None,
              "width": video[0].get("width") if video else None,
              "height": video[0].get("height") if video else None,
              "r_frame_rate": video[0].get("r_frame_rate") if video else None,
              "packets": int(packets) if packets.isdigit() else packets,
              "expected_packets": expected_packets},
    "audio": {"codec": audio[0].get("codec_name") if audio else None,
              "sample_rate": audio[0].get("sample_rate") if audio else None,
              "channels": audio[0].get("channels") if audio else None},
    "duration_s": measured_duration,
    "bytes": __import__("os").path.getsize(out),
    "sha256": sha,
    "decode_check": "passed" if not any("decode" in f for f in failures) else "failed",
    "loudness": {"integrated_lufs": integrated, "true_peak_dbtp": true_peak,
                 "window_lufs": [-16.0, -12.0], "peak_ceiling_dbtp": -1.0,
                 "measured_by": "ffmpeg ebur128=peak=true on the final mp4"},
    "encode_quality": {"reference": "shots/seq strips split with the same untile chain",
                       "psnr_avg_db": psnr_avg, "psnr_min_db": psnr_min, "ssim_all": ssim_all,
                       "floors": {"psnr_avg_db": 38.0, "ssim_all": 0.97}},
    "sequence": {"fps_distinct": seq["fps_distinct"], "per_strip": seq["per_strip"],
                 "output_fps": seq["output_fps"], "frame_count": seq["frame_count"],
                 "strip_count": seq["strip_count"], "strip_consumer": seq["strip_consumer"],
                 "inputs": seq["inputs"]},
}
with open("verification.json", "w") as fh:
    json.dump(result, fh, indent=2)
    fh.write("\n")

print(f"  duration {measured_duration:.3f}s  video {result['video']['width']}x{result['video']['height']} @ {result['video']['r_frame_rate']}  audio aac {result['audio']['sample_rate']}Hz x{result['audio']['channels']}")
print(f"  packets {packets}/{expected_packets}  integrated {integrated} LUFS  true peak {true_peak} dBTP")
print(f"  psnr avg {psnr_avg} dB (min {psnr_min})  ssim {ssim_all}")
print(f"  sha256 {sha}")
if failures:
    print("  GATE FAILURES:")
    for f in failures:
        print(f"    - {f}")
    sys.exit(1)
print("  GATE GREEN -> verification.json")
PY

echo "== done: $OUT =="
