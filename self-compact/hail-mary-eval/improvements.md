# Improvements — hail-mary film, ranked by measured impact

Source of every "current" value: `evidence.json` (task 2.a) unless another
file is named. No re-render, re-encode, or file change to the film happens
in this run — every item below is a proposal for a separate approved run.
Rubric freeze rule still applies: changing a frozen target (e.g. the
loudness window) means a new eval run, not an edit to `rubric.md`.

| id | axis | current (measured) | target | artifact changed | gate that catches failure |
|---|---|---|---|---|---|
| I1 | vivid (motion life) | 400 distinct frames of 1,200; effective 10.0 Hz in a 30 fps container | ≥1,100 distinct frames; 30 Hz effective | `render.html` strip mode, `capture-strips.mjs`, `assemble.sh` | verify.sh counts distinct frames (strip tile sum) ≥1,100 and rerun `measure.sh` reports `effective_motion_hz` 30.0 |
| I2 | loud (arc) | integrated -14.0 LUFS; drop-to-catch -1.8 LU (-13.2 → -15.0, quieter at the catch); reference +13.2 LU on its declared windows | integrated -12.0 (top of the frozen window); drop-to-catch ≥ +10 LU (dip under the throw, crest on the catch) | `sound-palette.md` bus gains, `audio/` stem mix, `assemble.sh` | verify.sh ebur128 4s-window check: pre-catch minus post-catch ≥ +10 LU, recorded as `films.*.drop_to_catch`; integrated stays inside -16…-12 |
| I3 | loud (narration) | announcer is macOS `say -v Daniel` (capabilities.json; 2.c report) | best local voice the host offers, or restructure so crowd/PA carry the call and narration shrinks | `audio/` call stem recipe | machine gate impossible without a new reference sample; gate is a human preview checkpoint (see I7) plus the unchanged transcript check |
| I4 | exciting (energy placement) | catch beat s04 mean_ydif 1.6233 while the film peak 7.1093 lands on the closing card (s06, t 33–40); reference catch beat s06 is 7.5387 (its 10.3026 peak is s08, a different, later beat) | the catch beat is the film's energy peak: mean_ydif ≥ 5.0 AND greater than every other beat | `shot-list.json` per-beat energy targets + `render.html` choreography | rerun `measure.sh`: `per_beat_frame_difference_energy` argmax is the catch beat |
| I5 | efficiency | 117,013,410 bytes, bit_rate 23,402,682 at crf 18 | ≤ 45,000,000 bytes at crf 24–26 (flat canvas art re-encodes cleanly) | `assemble.sh` encode settings | verify.sh full existing gate set stays green on the re-encode (sha changes, decode clean, loudness unchanged) |
| I6 | wiring (W2) | acceptance words in authored artifacts: `vivid` 0, `exciting` 0 | every acceptance word in the request appears in the next run's spec, each mapped to a measurable proxy (I1/I2/I4 numbers) before capture starts | next run's `canon.md` + `shot-list.json` | `measure.sh` acceptance_words count ≥ 1 per word in the spec files |
| I7 | wiring (W3) | 0 human previews before delivery | exactly one beat-level preview checkpoint (six strips) before assembly; the run blocks on it | collaboration plan of the next run (a read-only preview task) | preview receipt file exists with a timestamp before `assemble.sh` runs |
| I8 | loudness window itself | frozen window -16…-12 caps the level at -12.0; reference sits at -9.9 | option only: re-freeze to -16…-10 in a NEW eval run if Evan wants theater level | new run's rubric (never this one) | new frozen sha256 recorded before its first measurement |

## Decision option — not a step

**Photoreal external-generator rail (Higgsfield-class, "O1").** Current:
zero credits spent, no external calls (capabilities.json). If Evan's
verdict is that stylized canvas is the wrong concept rather than the wrong
execution, this becomes the primary rail for a new run: same verify gates,
plus a provenance record of every generation call. It is a decision about
cost and external services, so it is parked here, not scheduled.

## Handoff — what Evan's one line unlocks

Q1: "Which was it — look, sound, pacing, or story?"

- **look** → schedule I1 + I4 (motion rate and energy placement); if the
  canvas style itself is rejected, add the I8 decision and the photoreal
  option above as the fork.
- **sound** → schedule I2 + I3 (dynamics arc and narration), with I8 only
  if the answer is "not loud enough at the ceiling."
- **pacing** → schedule I4 plus a beat retime in `shot-list.json` (longer
  pre-snap tension, slower catch reveal); duration may grow past 40 s,
  which re-opens the frozen 40.0 s duration target in a new run.
- **story** → nothing above: the spine scored `final_play` 5 vs 3 with
  zero judge spread; keep canon.md exactly and fix only execution.

Every re-render or re-encode is a separate approved run; this file changes
nothing on disk by itself.
