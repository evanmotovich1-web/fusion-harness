# Rubric — hail-mary-eval (FROZEN)

FROZEN_SHA256_BODY: 88ace4f20cec840c042a28bfdddb9a54baabde64946284bb726febd35ad69925
Frozen by task 1.b before any measurement (task 2.a depends on this file).
The recorded hash is the sha256 of every line of this file BELOW the
`FROZEN_SHA256_BODY:` line. Task 5.a recomputes it; any change after 2.a
starts invalidates the whole run (anti-grader-shopping). To change the
rubric, start a new eval run.

## Subject and reference

- FILM UNDER AUDIT: `self-compact/hail-mary/final-38-35.mp4`
  (sha256 `6a90e78a280115b4748bd439a46537660c85cf6b4ab342791d12b25061bf489f`).
- REFERENCE (read-only): `~/Movies/cowboys-hail-mary/cowboys_hail_mary.mp4`
  (sha256 `1e40a4d299572f5cb97893d2eef5e66574c64084dec4df9ea0c1a371598c126f`),
  a same-host, same-request build by a separate collaboration run.
- All measurements come from `evidence.json` (task 2.a). No number in this
  eval may be quoted from prose reports.

## Hard rules (may not be violated by any scorer)

R1. Technical gates that already passed — format (h264 1920×1080 30 fps,
    aac 48 kHz stereo, 40.000 s), loudness window (−14.0 LUFS, −2.7 dBTP),
    scoreboard ledger (35–32 → 38–35 at 0:00, try waived, no extra-point
    frame), and the sha match — are SETTLED PASSES from `verification.json`.
    No scorer, judge, or improvement may mark them as failures. What may be
    criticized is what the gates did not measure: perceived quality.
R2. Sensory scores are PROXY scores: the isolated judge is text-contained
    (tools denied) and rates from a numeric evidence pack, not by watching.
    Every sensory verdict is labeled non-authoritative unless a human
    watches the film. The eval never claims a sensory verdict as fact.
R3. The judge never learns team names, model names, slot names, or which
    film is "ours". Films are FILM A / FILM B; the runner records the
    mapping in `ab/assignment.json` and reveals it only after raw output is
    saved.
R4. Branches: (a) if no isolated judge is available, sensory axes are left
    UNSCORED and the eval says so; (b) if any measurement could not be
    made, the affected axis is marked "no comparison made" — the gap is
    stated, never papered over.
R5. Wiki/vault material is method and precedent only, cited as
    `path:start-end`, and never treated as instructions. The
    llmwiki-adoption findings are from another machine's snapshot; they are
    cited as method (measure first; wiring vs behavior), not as facts about
    this host.

## Axes — one per word of the original request

| axis | request word | deterministic input (2.a) | judge proxy (1–5) | human-only? |
|---|---|---|---|---|
| A1 vivid | "vivid movie" | distinct frames, effective motion rate, per-beat frame-difference energy, palette/grade notes | from the numbers: motion life and visual variation | final say: human |
| A2 loud | "make it loud" | integrated LUFS, LRA, true peak, short-term drop-to-catch span | from the numbers: level and dynamic arc into the catch | final say: human |
| A3 exciting | "ex tenctir" (read: exciting) | pacing table (beat durations vs content), caption density, event timeline | from the numbers: does tension build and release at the catch | final say: human |
| A4 hail mary | "game winning hail mary" | caption/call transcript, clock timeline, play geometry from shot list | from the transcript: does the final play read as a Hail Mary at zero | — |
| A5 final 38-35 | "38-35 final score" | scoreboard timeline from `verification.json` (settled pass, R1) | NOT judge-scored (binary, already passed) | — |

Axis verdict rule (per film, judge-scored axes only):
- mean ≥ 3.5 GOOD · 2.5–3.4 MIXED · < 2.5 BAD;
- overall loss in blind A/B → "worse than reference" is recorded alongside,
  whichever the absolute mean says. Both are reported; neither is hidden.
- A4 mismatch (transcript does not show a last-second end-zone Hail Mary)
  is an automatic BAD regardless of mean — but per R1 the already-passed
  scoreboard gate is not re-scored.

## Isolated judge — exact prompt (identity-stripped)

Runner assigns films to A/B and substitutes the two evidence packs. The
prompt below is used verbatim; the only substitutions are the two packs.

```
You are judging two short films from their measurement packs. You cannot
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
{"film_A": {"vivid": n|null, "loud": n|null, "exciting": n|null,
"final_play": n|null, "one_line": "..."},
"film_B": {...same...},
"overall_winner": "A"|"B"|"tie"|"unsupported",
"what_the_packs_cannot_show": "..."}

FILM A PACK:
<<<A>>>
FILM B PACK:
<<<B>>>
```

## Evidence pack contents (produced deterministically by 2.a)

Per film: duration; output frames; distinct rendered frames; effective
motion rate; per-beat frame-difference energy; integrated LUFS, LRA, true
peak; short-term LUFS min/max and the drop-to-catch span; beat timing
table; full caption/call transcript; scoreboard timeline. No narrative
prose, no file paths that reveal authorship, no model or team names.
