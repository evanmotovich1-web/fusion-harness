#!/bin/bash
# Deterministic measurement. No LLM, no network. Writes evidence.json only.
set -eu
cd "$(dirname "$0")"
python3 - << 'PY'
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

FFPROBE = "/opt/homebrew/bin/ffprobe"
FFMPEG = "/opt/homebrew/bin/ffmpeg"
EVAL = Path(".").resolve()
AUDIT_DIR = EVAL.parent / "hail-mary"
REF_DIR = Path.home() / "Movies" / "cowboys-hail-mary"
OUT = EVAL / "evidence.json"
WORDS = ("vivid", "loud", "exciting", "entertain", "watchable")
PHRASES = ("hail mary", "38-35", "38–35")
ACCEPT_FILES = (
    "canon.md",
    "shot-list.json",
    "screenplay.md",
    "sound-palette.md",
    "verify.sh",
    "README.md",
)


def run(args, timeout=40):
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise SystemExit(f"command failed: {args[0]} {args[1] if len(args) > 1 else ''}\n{proc.stderr[-800:]}")
    return proc


def lu(value):
    return round(float(value), 1)


def probe(path):
    proc = run([
        FFPROBE, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ], timeout=20)
    data = json.loads(proc.stdout)
    video = next(s for s in data["streams"] if s.get("codec_type") == "video")
    audio = next(s for s in data["streams"] if s.get("codec_type") == "audio")
    duration = float(data["format"]["duration"])
    rate = video["r_frame_rate"]
    num, den = rate.split("/")
    fps = int(num) / int(den)
    return {
        "duration_s": round(duration, 3),
        "bytes": path.stat().st_size,
        "bit_rate": int(data["format"].get("bit_rate") or 0),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "video_codec": video["codec_name"],
        "width": video["width"],
        "height": video["height"],
        "r_frame_rate": rate,
        "container_fps": round(fps, 3),
        "output_frames": int(video.get("nb_frames") or round(duration * fps)),
        "audio_codec": audio["codec_name"],
        "sample_rate": int(audio["sample_rate"]),
        "channels": audio["channels"],
    }


def ebur128(path, start=None, dur=None):
    cmd = [FFMPEG, "-hide_banner", "-nostdin"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}", "-t", f"{dur:.3f}"]
    cmd += ["-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"]
    proc = run(cmd, timeout=30)
    text = proc.stderr
    integrated = re.search(r"Integrated loudness:\s+I:\s+(-?\d+(?:\.\d+)?)\s+LUFS", text)
    lra = re.search(r"Loudness range:\s+LRA:\s+(-?\d+(?:\.\d+)?)\s+LU", text)
    peak = re.search(r"True peak:\s+Peak:\s+(-?\d+(?:\.\d+)?)\s+dBFS", text)
    if not integrated:
        raise SystemExit(f"ebur128 missing integrated for {path} start={start}")
    return {
        "integrated_lufs": lu(integrated.group(1)),
        "lra_lu": lu(lra.group(1)) if lra else None,
        "true_peak_dbtp": lu(peak.group(1)) if peak else None,
    }


def windows(path, duration):
    rows = []
    start = 0.0
    while start + 4.0 <= duration + 0.001:
        measured = ebur128(path, start, 4.0)
        rows.append({"t": round(start, 3), "lufs": measured["integrated_lufs"]})
        start += 4.0
    return rows


def span(path, pre, post):
    pre_m = ebur128(path, pre[0], pre[1] - pre[0])
    post_m = ebur128(path, post[0], post[1] - post[0])
    return {
        "pre_s": [round(pre[0], 3), round(pre[1], 3)],
        "pre_lufs": pre_m["integrated_lufs"],
        "post_s": [round(post[0], 3), round(post[1], 3)],
        "post_lufs": post_m["integrated_lufs"],
        "span_lu": lu(post_m["integrated_lufs"] - pre_m["integrated_lufs"]),
    }


def ydif_by_beat(path, fps, beats):
    tmp = Path("/tmp/hail-mary-eval-ydif.txt")
    if tmp.exists():
        tmp.unlink()
    run([
        FFMPEG, "-hide_banner", "-nostdin", "-i", str(path),
        "-vf", "signalstats,metadata=print:file=" + str(tmp) + ":key=lavfi.signalstats.YDIF",
        "-f", "null", "-",
    ], timeout=50)
    values = []
    frame = None
    for line in tmp.read_text().splitlines():
        frame_match = re.search(r"frame:\s*(\d+)", line)
        if frame_match:
            frame = int(frame_match.group(1))
        ydif = re.search(r"YDIF=(-?\d+(?:\.\d+)?)", line)
        if ydif is not None:
            values.append((frame if frame is not None else len(values), float(ydif.group(1))))
    buckets = {beat["id"]: [] for beat in beats}
    for index, value in values:
        t = index / fps
        for beat in beats:
            if beat["t_in"] <= t < beat["t_out"]:
                buckets[beat["id"]].append(value)
                break
    energy = []
    for beat in beats:
        samples = buckets[beat["id"]]
        mean = sum(samples) / len(samples) if samples else None
        energy.append({
            "id": beat["id"],
            "t_in": beat["t_in"],
            "t_out": beat["t_out"],
            "duration_s": beat["duration_s"],
            "frames": len(samples),
            "mean_ydif": None if mean is None else round(mean, 4),
        })
    return energy


def read_audit_motion():
    seq_path = AUDIT_DIR / "shots" / "seq" / "sequence.json"
    seq = json.loads(seq_path.read_text())
    tiles = sum(int(strip["tiles"]) for strip in seq["strips"])
    strip_files = sorted((AUDIT_DIR / "shots" / "seq").glob("strip_*.png"))
    return {
        "source": "shots/seq/sequence.json strip tile sum versus container frame count",
        "strip_records": len(seq["strips"]),
        "strip_png_files": len(strip_files),
        "tiles_sum": tiles,
        "sequence_frame_count": seq["frame_count"],
        "fps_distinct": seq["fps_distinct"],
        "frames_per_distinct": seq["frames_per_distinct"],
        "output_fps_declared": seq["output_fps"],
        "distinct_rendered_frames": tiles,
        "records_match_declared_count": tiles == seq["frame_count"] == seq["strip_count"] * seq["per_strip"],
    }


def audit_beats():
    shot = json.loads((AUDIT_DIR / "shot-list.json").read_text())
    beats = []
    for beat in shot["beats"]:
        beats.append({
            "id": beat["id"],
            "t_in": round(float(beat["t_in_s"]), 3),
            "t_out": round(float(beat["t_out_s"]), 3),
            "duration_s": round(float(beat["duration_s"]), 3),
            "scoreboard_line": beat["scoreboard"]["line"],
            "clock": beat["scoreboard"].get("clock"),
            "captions": list(beat.get("captions") or []),
        })
    catch_beat = next(b for b in shot["beats"] if "catch" in b.get("title", "").lower())
    catch_t = round(float(catch_beat["t_in_s"]), 3)
    calls = []
    lines = (AUDIT_DIR / "screenplay.md").read_text().splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "CALL (RADIO)" and index + 1 < len(lines):
            calls.append(lines[index + 1].strip())
    return beats, catch_t, calls, [c for b in beats for c in b["captions"]]


def ref_beats_and_catch():
    timeline = json.loads((REF_DIR / "timeline.json").read_text())
    beats = []
    for shot in timeline["shots"]:
        beats.append({
            "id": shot["id"],
            "t_in": round(float(shot["start"]), 3),
            "t_out": round(float(shot["end"]), 3),
            "duration_s": round(float(shot["duration"]), 3),
            "frames_declared": shot.get("frames"),
        })
    catch_t = round(float(timeline["play"]["catch"]["t"]), 3)
    check = timeline["audio"]["dynamics_check"]
    ranges = re.findall(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", check)
    if len(ranges) < 2:
        raise SystemExit("reference dynamics_check has no two ranges")
    pre = (float(ranges[0][0]), float(ranges[0][1]))
    post = (float(ranges[1][0]), float(ranges[1][1]))
    calls = [row["text"] for row in timeline.get("vo", {}).get("lines", [])]
    scoreboard = []
    for state in timeline["scorebug"]["states"]:
        scoreboard.append({
            "from": state["from"],
            "to": state["to"],
            "home": state.get("dal"),
            "away": state.get("kc"),
            "clock": state.get("clock"),
            "down": state.get("down"),
            "status": state.get("status"),
        })
    owners = sorted({shot.get("owner") for shot in timeline["shots"] if shot.get("owner")})
    return beats, catch_t, pre, post, calls, scoreboard, owners, timeline["video"]["frames"]


def redact(text):
    replacements = (
        ("Redhawk Forge", "HOME"),
        ("Bayline Kings", "AWAY"),
        ("Kansas City", "AWAY"),
        ("Cowboys", "HOME"),
        ("Dallas", "HOME"),
        ("DALLAS", "HOME"),
        ("FORGE", "HOME"),
        ("KINGS", "AWAY"),
        ("FRG", "HOME"),
        ("BAY", "AWAY"),
        ("DAL", "HOME"),
        ("KC", "AWAY"),
    )
    out = text
    for src, dst in replacements:
        out = re.sub(re.escape(src), dst, out, flags=re.IGNORECASE)
    banned = ("glm", "sol", "terra", "claude", "deepseek", "grok", "opus", "sonnet", "astra", "hail-mary", "cowboys")
    for word in banned:
        if re.search(rf"\b{word}\b", out, re.IGNORECASE):
            out = re.sub(rf"\b{word}\b", "REDACTED", out, flags=re.IGNORECASE)
    return out


def acceptance():
    per_file = []
    totals = {word: 0 for word in WORDS}
    totals.update({phrase: 0 for phrase in PHRASES})
    for name in ACCEPT_FILES:
        text = (AUDIT_DIR / name).read_text(errors="replace")
        counts = {}
        for word in WORDS:
            counts[word] = len(re.findall(rf"\b{word}\b", text, flags=re.IGNORECASE))
            totals[word] += counts[word]
        lowered = text.lower()
        for phrase in PHRASES:
            counts[phrase] = lowered.count(phrase.lower())
            totals[phrase] += counts[phrase]
        per_file.append({"file": name, "counts": counts})
    return {"files": list(ACCEPT_FILES), "per_file": per_file, "totals": totals}


def conflict():
    rows = [
        {"artifact": "canon.md", "author_slot": "glm", "task": "1.b"},
        {"artifact": "shot-list.json", "author_slot": "glm", "task": "1.b"},
        {"artifact": "README.md", "author_slot": "glm", "task": "5.a"},
        {"artifact": "capabilities.json", "author_slot": "sol", "task": "1.a"},
        {"artifact": "render.html", "author_slot": "sol", "task": "2.b"},
        {"artifact": "shots/", "author_slot": "sol", "task": "2.b"},
        {"artifact": "assemble.sh", "author_slot": "sol", "task": "3.a"},
        {"artifact": "final-38-35.mp4", "author_slot": "sol", "task": "3.a"},
        {"artifact": "sound-palette.md", "author_slot": "terra", "task": "1.c"},
        {"artifact": "screenplay.md", "author_slot": "terra", "task": "2.a"},
        {"artifact": "audio/", "author_slot": "terra", "task": "2.c"},
        {"artifact": "verify.sh", "author_slot": "terra", "task": "4.a"},
        {"artifact": "verification.json", "author_slot": "terra", "task": "4.a"},
    ]
    technical_judge = "terra"
    for row in rows:
        row["technical_judge_slot"] = technical_judge
        row["author_is_technical_judge"] = row["author_slot"] == technical_judge
    return {
        "source": "film collaboration task ids mapped from report filenames 1.a-sol through 5.a-glm; slot names are not stored in the film files",
        "sensory_judge": {
            "identity": "out-of-roster isolated claude",
            "authored_film_artifacts": [],
            "judge_is_author": False,
        },
        "rows": rows,
        "judge_is_author_cases": [
            {
                "slot": "terra",
                "authored": ["sound-palette.md", "screenplay.md", "audio/", "verify.sh", "verification.json"],
                "judges": ["verify.sh technical gates of the film those artifacts define"],
            }
        ],
    }


def pack(film, beats, calls, scoreboard, energy):
    return {
        "duration_s": film["duration_s"],
        "output_frames": film["output_frames"],
        "distinct_rendered_frames": film["distinct_rendered_frames"],
        "effective_motion_hz": film["effective_motion_hz"],
        "container_fps": film["container_fps"],
        "per_beat_frame_difference_energy": [
            {"id": row["id"], "t_in": row["t_in"], "t_out": row["t_out"], "mean_ydif": row["mean_ydif"]}
            for row in energy
        ],
        "integrated_lufs": film["integrated_lufs"],
        "lra_lu": film["lra_lu"],
        "true_peak_dbtp": film["true_peak_dbtp"],
        "short_term_lufs_min": film["short_term_lufs_min"],
        "short_term_lufs_max": film["short_term_lufs_max"],
        "drop_to_catch_span_lu": film["drop_to_catch"]["span_lu"],
        "drop_to_catch": film["drop_to_catch"],
        "beat_timing": [
            {"id": beat["id"], "t_in": beat["t_in"], "t_out": beat["t_out"], "duration_s": beat["duration_s"]}
            for beat in beats
        ],
        "caption_call_transcript": [redact(line) for line in calls],
        "scoreboard_timeline": scoreboard,
    }


def main():
    audit_mp4 = AUDIT_DIR / "final-38-35.mp4"
    ref_mp4 = REF_DIR / "cowboys_hail_mary.mp4"
    audit_probe = probe(audit_mp4)
    ref_probe = probe(ref_mp4)
    audit_motion = read_audit_motion()
    if audit_motion["distinct_rendered_frames"] <= 0:
        raise SystemExit("audit distinct frame count missing")
    audit_beats_rows, audit_catch_t, audit_calls, audit_captions = audit_beats()
    ref_beats, ref_catch_t, ref_pre, ref_post, ref_calls, ref_score_raw, ref_owners, ref_declared_frames = ref_beats_and_catch()

    audit_whole = ebur128(audit_mp4)
    ref_whole = ebur128(ref_mp4)
    audit_grid = windows(audit_mp4, audit_probe["duration_s"])
    ref_grid = windows(ref_mp4, ref_probe["duration_s"])
    audit_drop = span(audit_mp4, (max(0.0, audit_catch_t - 4.0), audit_catch_t), (audit_catch_t, audit_catch_t + 4.0))
    audit_drop["rule"] = "4s ending at catch-beat t_in versus 4s starting there; no declared dynamics window in the shot list"
    ref_drop = span(ref_mp4, ref_pre, ref_post)
    ref_drop["rule"] = "windows parsed from timeline.json audio.dynamics_check, measured fresh"
    ref_adjacent = span(ref_mp4, (ref_catch_t - 4.0, ref_catch_t), (ref_catch_t, ref_catch_t + 4.0))
    ref_adjacent["rule"] = "same 4s-adjacent rule as the audit film, for a like-for-like span"

    audit_energy = ydif_by_beat(audit_mp4, audit_probe["container_fps"], audit_beats_rows)
    ref_energy = ydif_by_beat(ref_mp4, ref_probe["container_fps"], ref_beats)

    audit_film = {
        **{k: audit_probe[k] for k in (
            "duration_s", "bytes", "bit_rate", "sha256", "video_codec", "width", "height",
            "r_frame_rate", "container_fps", "output_frames", "audio_codec", "sample_rate", "channels",
        )},
        "distinct_rendered_frames": audit_motion["distinct_rendered_frames"],
        "effective_motion_hz": round(audit_motion["distinct_rendered_frames"] / audit_probe["duration_s"], 3),
        "duplication_factor": round(audit_probe["output_frames"] / audit_motion["distinct_rendered_frames"], 3),
        "motion": audit_motion,
        "integrated_lufs": audit_whole["integrated_lufs"],
        "lra_lu": audit_whole["lra_lu"],
        "true_peak_dbtp": audit_whole["true_peak_dbtp"],
        "short_term_windows": audit_grid,
        "short_term_lufs_min": min(row["lufs"] for row in audit_grid),
        "short_term_lufs_max": max(row["lufs"] for row in audit_grid),
        "catch_t": audit_catch_t,
        "drop_to_catch": audit_drop,
        "beat_energy": audit_energy,
    }
    ref_distinct = ref_probe["output_frames"]
    ref_film = {
        **{k: ref_probe[k] for k in (
            "duration_s", "bytes", "bit_rate", "sha256", "video_codec", "width", "height",
            "r_frame_rate", "container_fps", "output_frames", "audio_codec", "sample_rate", "channels",
        )},
        "distinct_rendered_frames": ref_distinct if ref_distinct == ref_declared_frames else None,
        "distinct_source": "ffprobe nb_frames matches timeline.json video.frames" if ref_distinct == ref_declared_frames else "mismatch",
        "timeline_declared_frames": ref_declared_frames,
        "effective_motion_hz": round(ref_distinct / ref_probe["duration_s"], 3) if ref_distinct == ref_declared_frames else None,
        "duplication_factor": 1.0 if ref_distinct == ref_declared_frames else None,
        "integrated_lufs": ref_whole["integrated_lufs"],
        "lra_lu": ref_whole["lra_lu"],
        "true_peak_dbtp": ref_whole["true_peak_dbtp"],
        "short_term_windows": ref_grid,
        "short_term_lufs_min": min(row["lufs"] for row in ref_grid),
        "short_term_lufs_max": max(row["lufs"] for row in ref_grid),
        "catch_t": ref_catch_t,
        "drop_to_catch": ref_drop,
        "adjacent_4s_drop_to_catch": ref_adjacent,
        "beat_energy": ref_energy,
        "shot_owners": ref_owners,
    }
    if ref_film["distinct_rendered_frames"] is None:
        raise SystemExit("reference distinct frame count does not match timeline")

    audit_scoreboard = [
        {"id": beat["id"], "t_in": beat["t_in"], "t_out": beat["t_out"], "line": redact(beat["scoreboard_line"]), "clock": beat["clock"]}
        for beat in audit_beats_rows
    ]
    ref_scoreboard = [
        {
            "from": row["from"],
            "to": row["to"],
            "line": f"HOME {row['home']} AWAY {row['away']} clock {row['clock']} status {row['status']}",
        }
        for row in ref_score_raw
    ]
    audit_transcript = audit_captions + audit_calls
    evidence = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": {
            "loudness": "ffmpeg ebur128=peak=true, whole file and -ss/-t 4s windows",
            "frame_difference": "ffmpeg signalstats YDIF mean inside each beat",
            "audit_motion": "sum of shots/seq/sequence.json strip tiles versus ffprobe nb_frames and r_frame_rate",
            "reference_motion": "ffprobe nb_frames compared with timeline.json video.frames",
            "drop_to_catch": "audit uses 4s on either side of the catch-beat t_in; reference uses timeline audio.dynamics_check ranges, measured fresh",
            "acceptance_files": list(ACCEPT_FILES),
            "judge_pack_rule": "judge_packs omit paths, slot names, and model names; do not paste conflict_matrix into the judge prompt",
        },
        "films": {"audit": audit_film, "reference": ref_film},
        "judge_packs": {
            "audit": pack(audit_film, audit_beats_rows, audit_transcript, audit_scoreboard, audit_energy),
            "reference": pack(ref_film, ref_beats, ref_calls, ref_scoreboard, ref_energy),
        },
        "acceptance_words": acceptance(),
        "conflict_matrix": conflict(),
    }
    OUT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT}")
    print(f"audit distinct {audit_film['distinct_rendered_frames']} hz {audit_film['effective_motion_hz']} I {audit_film['integrated_lufs']} span {audit_drop['span_lu']}")
    print(f"reference distinct {ref_film['distinct_rendered_frames']} hz {ref_film['effective_motion_hz']} I {ref_film['integrated_lufs']} span {ref_drop['span_lu']}")


if __name__ == "__main__":
    main()
PY
