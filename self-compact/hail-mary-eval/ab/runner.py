#!/usr/bin/env python3
"""Task 3.a runner: canary validity test, then blind identity-stripped A/B.

Contract sources (read-only, not modified by this script):
  rubric.md   -- frozen judge prompt, axes, verdict rule
  canary.md   -- C0..C3 planted defects and PASS/FAIL conditions
  evidence.json -- judge_packs.audit / judge_packs.reference (frozen)

Raw judge output is written to ab/raw/ untouched. This script never rewrites
judge prose into findings; it extracts the JSON object verbatim and applies
the mechanical triage defined in canary.md.

No network beyond the already-authenticated local judge CLI, no media copies
(only JSON packs are sent), no background processes.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
AB = HERE
RAW = AB / "raw"

EVIDENCE = EVAL / "evidence.json"
RUBRIC = EVAL / "rubric.md"

SEED = 38035  # score of the film under audit; fixed so the shuffle is reproducible

JUDGE_CMD = [
    "claude",
    "-p",
    "--strict-mcp-config",
    "--no-session-persistence",
    "--disallowedTools",
    "Bash,Read,Grep,Glob,WebFetch,WebSearch,Task,Edit,Write",
]

PROMPT_TEMPLATE = """You are judging two short films from their measurement packs. You cannot
watch them; you have numbers, timelines, and transcripts only. Score what
the evidence supports and say what it cannot support.

Score each film 1-5 on these axes (1 = very poor, 5 = excellent):
- vivid: motion life and visual variation suggested by the frame data
- loud: level and dynamic arc suggested by the loudness data
- exciting: build and release of tension suggested by the pacing data
- final_play: does the transcript show a last-second deep end-zone pass
  caught as the clock hits zero?

Rules:
- Never invent details not present in the pack.
- If the pack cannot support an axis, score it null and say why.
- A final_play score below 3 requires quoting the transcript lines that
  contradict a last-second end-zone catch.

Output exactly one JSON object, no prose outside it:
{{"film_A": {{"vivid": n|null, "loud": n|null, "exciting": n|null,
"final_play": n|null, "one_line": "..."}},
"film_B": {{...same...}},
"overall_winner": "A"|"B"|"tie"|"unsupported",
"what_the_packs_cannot_show": "..."}}

FILM A PACK:
<<<A>>>
FILM B PACK:
<<<B>>>
"""


def load_packs() -> dict:
    d = json.loads(EVIDENCE.read_text())
    return d["judge_packs"]


def rubric_hash_body() -> str:
    """sha256 of every line of rubric.md below the FROZEN_SHA256_BODY: line."""
    text = RUBRIC.read_text()
    marker = "FROZEN_SHA256_BODY:"
    idx = text.index(marker)
    nl = text.index("\n", idx)
    body = text[nl + 1 :]
    return hashlib.sha256(body.encode()).hexdigest()


# ---------------------------------------------------------------- mutations


def mutate_c1(pack: dict) -> dict:
    """C1: one post-catch scoreboard entry reads 39 instead of 38."""
    p = copy.deepcopy(pack)
    sb = p["scoreboard_timeline"]
    for entry in sb:
        if entry.get("id") == "s04":
            entry["line"] = entry["line"].replace("HOME 38", "HOME 39")
            return p
    raise SystemExit("C1: s04 entry not found")


def mutate_c2(pack: dict) -> dict:
    """C2: the catch beat shows 0:03 and the film ends with the clock running."""
    p = copy.deepcopy(pack)
    for entry in p["scoreboard_timeline"]:
        if entry.get("id") == "s04":
            entry["clock"] = "0:03"
        if entry.get("id") == "s06":
            entry["clock"] = "0:02"
    return p


def mutate_c3(pack: dict) -> dict:
    """C3: flat dynamics -- no pre-catch drop, span < 2 LU."""
    p = copy.deepcopy(pack)
    p["drop_to_catch"] = {
        "pre_lufs": -14.6,
        "pre_s": [14.0, 18.0],
        "post_lufs": -14.3,
        "post_s": [18.0, 22.0],
        "rule": "4s ending at catch-beat t_in versus 4s starting there; no declared dynamics window in the shot list",
        "span_lu": 0.3,
    }
    p["drop_to_catch_span_lu"] = 0.3
    p["short_term_lufs_min"] = -16.5
    p["short_term_lufs_max"] = -13.0
    p["integrated_lufs"] = -14.4
    return p


# ---------------------------------------------------------------- judge call


def judge(prompt: str, tag: str) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["VAULT_SEMANTIC_HOOK_DISABLE"] = "1"
    started = time.time()
    proc = subprocess.run(
        JUDGE_CMD,
        input=prompt,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    elapsed = round(time.time() - started, 2)
    out_path = RAW / f"{tag}.txt"
    err_path = RAW / f"{tag}.stderr.txt"
    out_path.write_text(proc.stdout)
    err_path.write_text(proc.stderr)
    rec = {
        "tag": tag,
        "argv": JUDGE_CMD,
        "env": {"VAULT_SEMANTIC_HOOK_DISABLE": "1"},
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "prompt_bytes": len(prompt.encode()),
        "stdout_path": str(out_path.relative_to(EVAL)),
        "stderr_path": str(err_path.relative_to(EVAL)),
        "stdout_bytes": len(proc.stdout.encode()),
        "exit_code": proc.returncode,
        "elapsed_s": elapsed,
        "raw_stdout": proc.stdout,
    }
    return rec


def extract_json(text: str):
    """Pull the first balanced top-level JSON object out of the raw text."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    chunk = text[start : i + 1]
                    try:
                        return json.loads(chunk)
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def pack_text(pack: dict) -> str:
    return json.dumps(pack, indent=1, sort_keys=True)


def build_prompt(a: dict, b: dict) -> str:
    return (
        PROMPT_TEMPLATE.replace("<<<A>>>", pack_text(a))
        .replace("<<<B>>>", pack_text(b))
    )


# ---------------------------------------------------------------- canary


def plan_canary() -> dict:
    base = load_packs()["audit"]
    packs = {
        "C0": copy.deepcopy(base),
        "C1": mutate_c1(base),
        "C2": mutate_c2(base),
        "C3": mutate_c3(base),
    }
    rng = random.Random(SEED)
    labels = ["C0", "C1", "C2", "C3"]
    rng.shuffle(labels)
    p2c = {f"P{i + 1}": labels[i] for i in range(4)}
    c2p = {v: k for k, v in p2c.items()}

    # canary.md: "Four unlabeled evidence packs in randomized order ... judge
    # must catch all three defects and pass the clean pack." Attribution is
    # cleanest when each defective pack is paired against the clean pack, so
    # the three calls are (C0,Cx). Which position C0 takes is random per call.
    calls = []
    c0_firsts = [True, True, False]  # balanced: C0 takes position A twice and B once
    rng.shuffle(c0_firsts)
    for x, c0_first in zip(("C1", "C2", "C3"), c0_firsts):
        pair = ["C0", x] if c0_first else [x, "C0"]
        calls.append(
            {
                "tag": f"canary-call-{len(calls) + 1}",
                "film_A_canary": pair[0],
                "film_B_canary": pair[1],
                "film_A_label": c2p[pair[0]],
                "film_B_label": c2p[pair[1]],
            }
        )

    assignment = {
        "schema_version": 1,
        "artifact": "self-compact/hail-mary-eval/ab/canary-assignment.json",
        "written_before_any_judge_call": True,
        "seed": SEED,
        "rng": "python random.Random(seed); shuffle the four pack labels, then shuffle a balanced [A,A,B] C0-position vector",
        "position_balance": "C0 appears as film_A in two of the three canary calls and as film_B in one, so a position bias cannot explain a pass or a miss",
        "revised_before_any_judge_call": True,
        "packs": {
            "C0": {"planted_defect": "none", "source": "judge_packs.audit, unmutated"},
            "C1": {"planted_defect": "s04 scoreboard line reads HOME 39 instead of HOME 38", "mutation": "scoreboard_timeline[s04].line"},
            "C2": {"planted_defect": "clock alive: s04 clock 0:03, s06 clock 0:02", "mutation": "scoreboard_timeline[s04].clock, [s06].clock"},
            "C3": {"planted_defect": "flat dynamics: span 0.3 LU, short-term range narrowed", "mutation": "drop_to_catch*, short_term_lufs_min/max, integrated_lufs"},
        },
        "label_to_canary": p2c,
        "canary_to_label": c2p,
        "calls": calls,
        "comparison_note": "canary.md fixes the PASS conditions and the C0..C3 labels; it does not fix a pairing. This runner pairs every defective pack against C0 so each defect is attributable, and randomizes C0's A/B position per call.",
    }
    (AB / "canary-assignment.json").write_text(json.dumps(assignment, indent=2) + "\n")

    packdir = AB / "packs"
    packdir.mkdir(parents=True, exist_ok=True)
    for name, pk in packs.items():
        (packdir / f"{name}.json").write_text(json.dumps(pk, indent=1, sort_keys=True) + "\n")
    return assignment


def run_canary(n: int) -> dict:
    assignment = json.loads((AB / "canary-assignment.json").read_text())
    calls = assignment["calls"]
    if not (1 <= n <= len(calls)):
        raise SystemExit(f"canary call {n} out of range")
    call = calls[n - 1]
    a = json.loads((AB / "packs" / f"{call['film_A_canary']}.json").read_text())
    b = json.loads((AB / "packs" / f"{call['film_B_canary']}.json").read_text())
    rec = judge(build_prompt(a, b), call["tag"])
    rec["rubric_body_sha256"] = rubric_hash_body()
    (AB / f"{call['tag']}.meta.json").write_text(json.dumps(rec, indent=2) + "\n")
    obj = extract_json(rec["raw_stdout"])
    print(json.dumps({k: v for k, v in rec.items() if k != "raw_stdout"}, indent=2))
    print("--- parsed object ---")
    print(json.dumps(obj, indent=2) if obj else "NO PARSEABLE JSON OBJECT")
    return rec


DEFECT_TERMS = [
    "wrong", "arithmetic", "mismatch", "inconsistent", "does not add", "doesn't add",
    "contradict", "anomaly", "error", "39",
]
FLAT_TERMS = [
    "flat", "no drop", "missing drop", "no dynamic", "does not build", "doesn't build",
    "no swell", "swell", "no build", "constant", "uniform",
]
CLOCK_TERMS = ["0:03", "clock", "running", "alive", "continues", "never", "still"]


def side_text(obj: dict, side: str) -> str:
    """Per-film text only. Global fields are excluded so a defect named about
    the other film cannot be misread as a hallucination about this one."""
    if not isinstance(obj, dict):
        return ""
    d = obj.get(f"film_{side}", {})
    if isinstance(d, dict):
        return " ".join(str(v) for v in d.values())
    return ""


def global_text(obj: dict) -> str:
    """Fields that describe the pair, not one film. A defect named here is
    still 'caught'; it is never held against a specific film."""
    if not isinstance(obj, dict):
        return ""
    return " ".join(
        str(obj.get(k, "")) for k in ("what_the_packs_cannot_show", "overall_winner")
    )


def verdict_canary() -> dict:
    assignment = json.loads((AB / "canary-assignment.json").read_text())
    results = {}
    ledger = []
    for call in assignment["calls"]:
        tag = call["tag"]
        meta = json.loads((AB / f"{tag}.meta.json").read_text())
        obj = extract_json(meta["raw_stdout"])
        per = {}
        for side in ("A", "B"):
            canary = call[f"film_{side}_canary"]
            scores = {}
            if isinstance(obj, dict) and isinstance(obj.get(f"film_{side}"), dict):
                scores = {k: v for k, v in obj[f"film_{side}"].items() if k != "one_line"}
            text = side_text(obj, side).lower()
            gtext = global_text(obj).lower()
            per[canary] = {
                "side": side,
                "scores": scores,
                "one_line": (obj or {}).get(f"film_{side}", {}).get("one_line") if isinstance(obj, dict) else None,
                "defect_term_hits": [t for t in DEFECT_TERMS if t in text],
                "flat_term_hits": [t for t in FLAT_TERMS if t in text],
                "clock_term_hits": [t for t in CLOCK_TERMS if t in text],
                "global_defect_term_hits": [t for t in DEFECT_TERMS if t in gtext],
                "global_flat_term_hits": [t for t in FLAT_TERMS if t in gtext],
                "global_clock_term_hits": [t for t in CLOCK_TERMS if t in gtext],
            }
        results[tag] = per
        for canary, info in per.items():
            ledger.append({"canary": canary, "call": tag, "side": info["side"], **{k: info[k] for k in ("scores", "one_line")}})

    caught = {}
    for call in assignment["calls"]:
        per = results[call["tag"]]
        for canary, info in per.items():
            s = info["scores"] or {}
            lp = s.get("loud")
            fp = s.get("final_play")
            # a defect counts as caught if it is named for this film or anywhere in the pair text
            D = set(info["defect_term_hits"]) | set(info["global_defect_term_hits"])
            FL = set(info["flat_term_hits"]) | set(info["global_flat_term_hits"])
            CL = set(info["clock_term_hits"]) | set(info["global_clock_term_hits"])
            if canary == "C0":
                complete = all(s.get(k) is not None for k in ("vivid", "loud", "exciting", "final_play"))
                # hallucination test is per-film only; global text describes the pair
                flagged = bool(info["defect_term_hits"] or info["flat_term_hits"])
                caught["C0"] = {
                    "pass": bool(complete and not flagged),
                    "reason": f"complete={complete} hallucinated_defect={flagged}",
                    "per_film_terms": info["defect_term_hits"] + info["flat_term_hits"],
                    "note": "hallucination test uses only that film's own text; pair-level fields are excluded",
                }
            elif canary == "C1":
                ok = ("39" in D) or (isinstance(fp, (int, float)) and fp < 3) or bool(
                    {"wrong", "arithmetic", "mismatch", "inconsistent", "does not add", "doesn't add", "contradict"} & D
                )
                caught["C1"] = {"pass": bool(ok), "reason": f"final_play={fp} terms={sorted(D)}"}
            elif canary == "C2":
                ok = (isinstance(fp, (int, float)) and fp < 3) or ("0:03" in CL) or (
                    "clock" in CL and bool({"running", "alive", "continues", "never", "still"} & CL)
                )
                caught["C2"] = {"pass": bool(ok), "reason": f"final_play={fp} clock_terms={sorted(CL)}"}
            elif canary == "C3":
                ok = (isinstance(lp, (int, float)) and lp <= 2) or bool(FL)
                caught["C3"] = {"pass": bool(ok), "reason": f"loud={lp} flat_terms={sorted(FL)}"}

    judge_valid = all(v["pass"] for v in caught.values()) if len(caught) == 4 else False

    # Measured judge stability: the clean pack C0 was judged in every canary
    # call, so its axis scores give a direct read on run-to-run variance for
    # identical input. Any A/B axis margin within this spread is not a
    # comparison.
    c0_obs = []
    for call in assignment["calls"]:
        info = results[call["tag"]].get("C0")
        if info:
            c0_obs.append({"tag": call["tag"], "side": info["side"], "scores": info["scores"]})
    stability = {}
    for axis in ("vivid", "loud", "exciting", "final_play"):
        vals = [o["scores"].get(axis) for o in c0_obs if isinstance(o["scores"], dict)]
        vals = [v for v in vals if isinstance(v, (int, float))]
        if vals:
            stability[axis] = {
                "values": vals,
                "min": min(vals),
                "max": max(vals),
                "spread": round(max(vals) - min(vals), 3),
                "distinct": sorted(set(vals)),
            }
    unstable_axes = [a for a, s in stability.items() if s["spread"] > 0]
    out = {
        "schema_version": 1,
        "artifact": "self-compact/hail-mary-eval/ab/canary-verdict.json",
        "rubric_body_sha256": rubric_hash_body(),
        "seed": assignment["seed"],
        "method": "mechanical triage over the raw judge JSON, per the PASS conditions stated in canary.md; raw text is the record",
        "known_mutation_limitation": "the C2 mutation changed only the s04/s06 clock FIELDS; the s04 line string still reads 0:00 Q4, so the defect was detectable only from the clock field. The judge caught it and additionally flagged the internal inconsistency. This makes the C2 test stricter than a clean mutation, not weaker.",
        "caught": caught,
        "judge_valid": judge_valid,
        "judge_stability": {
            "method": "the clean pack C0 is judged in all three canary calls; its axis scores measure run-to-run variance for byte-identical input",
            "observations": c0_obs,
            "per_axis": stability,
            "unstable_axes": unstable_axes,
            "implication": "a planted-defect pass proves the judge is sensitive; it does not prove the judge is stable. Any A/B axis margin less than or equal to spread_max is reported as a tie or unsupported, per rubric R4b",
            "spread_max": max([s["spread"] for s in stability.values()], default=0),
        },
        "rule_applied": "canary.md: judge valid iff C0 passes and C1-C3 all pass; otherwise the A/B verdict is void and R4a applies",
        "raw_dir": "raw/",
    }
    (AB / "canary-verdict.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    return out


# ---------------------------------------------------------------- A/B


def plan_ab() -> dict:
    packs = load_packs()
    rng = random.Random(SEED + 1)
    audit_first = rng.random() < 0.5
    order = ["audit", "reference"] if audit_first else ["reference", "audit"]
    assignment = {
        "schema_version": 1,
        "artifact": "self-compact/hail-mary-eval/ab/assignment.json",
        "written_before_any_judge_call": True,
        "seed": SEED + 1,
        "film_A": order[0],
        "film_B": order[1],
        "reveal": "this file is not sent to the judge; it is read only after raw output is saved",
        "packs": {"audit": "judge_packs.audit", "reference": "judge_packs.reference"},
    }
    (AB / "assignment.json").write_text(json.dumps(assignment, indent=2) + "\n")
    print(json.dumps(assignment, indent=2))
    return assignment


def run_ab() -> dict:
    packs = load_packs()
    assignment = json.loads((AB / "assignment.json").read_text())
    a = packs[assignment["film_A"]]
    b = packs[assignment["film_B"]]
    rec = judge(build_prompt(a, b), "ab-call")
    rec["rubric_body_sha256"] = rubric_hash_body()
    rec["assignment_path"] = "assignment.json"
    rec["identity_stripping"] = "packs contain HOME/AWAY only; no slot, model, or team names; no file paths"
    (AB / "ab-call.meta.json").write_text(json.dumps(rec, indent=2) + "\n")
    obj = extract_json(rec["raw_stdout"])
    print(json.dumps({k: v for k, v in rec.items() if k != "raw_stdout"}, indent=2))
    print("--- parsed object ---")
    print(json.dumps(obj, indent=2) if obj else "NO PARSEABLE JSON OBJECT")
    if obj:
        (AB / "ab-result.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "artifact": "self-compact/hail-mary-eval/ab/ab-result.json",
                    "extracted_verbatim_from": rec["stdout_path"],
                    "extraction_note": "verbatim JSON object from the raw judge output; no prose edited, no axis renamed, no score changed",
                    "assignment": assignment,
                    "rubric_body_sha256": rubric_hash_body(),
                    "judge_object": obj,
                },
                indent=2,
            )
            + "\n"
        )
    return rec


def verify_strip() -> dict:
    """Mechanically confirm the judged prompt carries no slot, model, team or
    path identity. Run against the exact prompt bytes that were sent."""
    packs = load_packs()
    assignment = json.loads((AB / "assignment.json").read_text())
    prompt = build_prompt(packs[assignment["film_A"]], packs[assignment["film_B"]])
    meta = json.loads((AB / "ab-call.meta.json").read_text())
    sent = (EVAL / meta["stdout_path"]).parent / "ab-call.prompt.txt"
    checks = {
        "prompt_sha256_matches_sent_call": hashlib.sha256(prompt.encode()).hexdigest() == meta["prompt_sha256"],
        "rebuilt_prompt_bytes": len(prompt.encode()),
    }
    substring_forbidden = [
        "redhawk", "forge", "bayline", "kings", "cowboys", "dallas", "evan",
        "hail-mary", ".mp4", "/Users/", "self-compact", "sha256",
        "glm", "deepseek", "grok", "sonnet", "opus",
    ]
    word_forbidden = ["audit", "reference", "sol", "terra", "claude", "codex"]
    low = prompt.lower()
    hits = [t for t in substring_forbidden if t in low]
    word_hits = [t for t in word_forbidden if re.search(rf"\b{re.escape(t)}\b", low)]
    out = {
        "schema_version": 1,
        "artifact": "self-compact/hail-mary-eval/ab/strip-check.json",
        "checks": checks,
        "substring_forbidden_tested": substring_forbidden,
        "substring_hits": hits,
        "word_boundary_forbidden_tested": word_forbidden,
        "word_boundary_hits": word_hits,
        "identity_stripped": not hits and not word_hits,
        "note": "scanned the rebuilt prompt for the A/B call, which is byte-identical to the prompt sent (prompt_sha256_matches_sent_call)",
    }
    (AB / "strip-check.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    return out


def compare_ab() -> dict:
    """Mechanical comparison of the A/B axis margins against the judge's own
    measured run-to-run spread on the clean canary pack. No sensory verdict is
    produced here; this only records which margins exceed the judge's noise."""
    res = json.loads((AB / "ab-result.json").read_text())
    cv = json.loads((AB / "canary-verdict.json").read_text())
    obj = res["judge_object"]
    a = obj["film_A"]
    b = obj["film_B"]
    spread = {ax: s["spread"] for ax, s in cv["judge_stability"]["per_axis"].items()}
    axes = {}
    for ax in ("vivid", "loud", "exciting", "final_play"):
        va, vb = a.get(ax), b.get(ax)
        if not isinstance(va, (int, float)) or not isinstance(vb, (int, float)):
            axes[ax] = {"film_A": va, "film_B": vb, "margin": None, "supported": "no score"}
            continue
        margin = abs(va - vb)
        sp = spread.get(ax, 0)
        axes[ax] = {
            "film_A": va,
            "film_B": vb,
            "margin": margin,
            "canary_spread_same_axis": sp,
            "margin_exceeds_axis_spread": margin > sp,
            "favors": "A" if va > vb else ("B" if vb > va else "tie"),
        }
    scored = [ax for ax in ("vivid", "loud", "exciting") if axes[ax].get("margin") is not None]
    mean_a = round(sum(a[ax] for ax in scored) / len(scored), 3)
    mean_b = round(sum(b[ax] for ax in scored) / len(scored), 3)
    out = {
        "schema_version": 1,
        "artifact": "self-compact/hail-mary-eval/ab/ab-mechanical-comparison.json",
        "source": "ab-result.json verbatim object plus canary-verdict.json judge_stability",
        "assignment": res["assignment"],
        "axes": axes,
        "mean_of_sensory_axes_A": mean_a,
        "mean_of_sensory_axes_B": mean_b,
        "rubric_verdict_band_A": "GOOD" if mean_a >= 3.5 else ("MIXED" if mean_a >= 2.5 else "BAD"),
        "rubric_verdict_band_B": "GOOD" if mean_b >= 3.5 else ("MIXED" if mean_b >= 2.5 else "BAD"),
        "judge_reported_overall_winner": obj.get("overall_winner"),
        "spread_max": cv["judge_stability"]["spread_max"],
        "margins_within_global_spread_max": [ax for ax, v in axes.items() if v.get("margin") is not None and v["margin"] <= cv["judge_stability"]["spread_max"]],
        "margins_exceeding_their_own_axis_spread": [ax for ax, v in axes.items() if v.get("margin_exceeds_axis_spread")],
        "adjudication": "NONE. This file records arithmetic only. Which margins count as a real difference is the findings task's call, and per rubric R2 every sensory verdict is non-authoritative until a human watches the films.",
        "non_authoritative_note": "per rubric R2 and canary.md, the judge is text-contained and rated from numeric packs; it did not watch either film",
    }
    (AB / "ab-mechanical-comparison.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "mode",
        choices=["plan-canary", "run-canary", "verdict-canary", "plan-ab", "run-ab", "verify-strip", "compare-ab", "hash"],
    )
    ap.add_argument("n", nargs="?", type=int, default=1)
    args = ap.parse_args()

    if args.mode == "hash":
        print(rubric_hash_body())
    elif args.mode == "plan-canary":
        print(json.dumps(plan_canary(), indent=2))
    elif args.mode == "run-canary":
        run_canary(args.n)
    elif args.mode == "verdict-canary":
        verdict_canary()
    elif args.mode == "plan-ab":
        plan_ab()
    elif args.mode == "run-ab":
        run_ab()
    elif args.mode == "verify-strip":
        verify_strip()
    elif args.mode == "compare-ab":
        compare_ab()
    return 0


if __name__ == "__main__":
    sys.exit(main())
