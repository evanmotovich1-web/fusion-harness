# The Hail Mary at Zero — final-38-35.mp4

**FICTIONAL SIMULATION.** A 40-second deterministic short film of a football
game won on a last-play Hail Mary, final score **38–35**. Redhawk Forge and
Bayline Kings are invented teams. No real league, club, broadcaster, or
player names, marks, logos, uniforms, or likenesses appear anywhere in this
artifact, and the film is not and must not be presented as real broadcast
footage. "Loud" means mastered, not clipped.

## How to open

- Play `final-38-35.mp4` with any modern player: QuickTime, VLC, IINA, or a
  browser (drag the file into a Chrome or Safari window).
- Verified playback: headless Google Chrome resolved playback, duration 40,
  readyState 4, no error (see `verification.json → chrome_play`).
- Full sound is the point — speakers up, or headphones.

## Provenance

| fact | value |
|---|---|
| file | `self-compact/hail-mary/final-38-35.mp4` |
| sha256 | `6a90e78a280115b4748bd439a46537660c85cf6b4ab342791d12b25061bf489f` |
| size | 117,013,410 bytes |
| container / codecs | mp4 · h264 High 1920×1080 30 fps (1200 frames) · aac LC 48 kHz stereo |
| duration | 40.000 s (target 40.0 ± 0.1) |
| loudness | -14.0 LUFS integrated · -2.7 dBTP true peak (window -16…-12, ceiling -1) |
| decode check | passed (full decode to null, exit 0) |
| render tools | ffmpeg 9.0.1 (`/opt/homebrew/bin/ffmpeg`), ffprobe 9.0.1, headless Google Chrome 153.0.8010.54 |
| whisper | absent on host → transcript check skipped (`verification.json → whisper_check`) |
| external generation | none — no generation APIs, no credits, no network; all frames and audio synthesized locally |

Pipeline: `render.html` (self-contained canvas renderer) → `capture.mjs` /
`capture-strips.mjs` (headless Chrome screenshots into `shots/`) → `audio/`
(synthesized cue wavs) → `assemble.sh` (deterministic ffmpeg graph) →
`final-38-35.mp4` → `verify.sh` (gates, writes `verification.json`).
Rerun `./verify.sh` to re-verify; it rewrites `verification.json` and
`verify-frames/` only.

## The arithmetic ledger (restated from canon.md)

- Kings reach **35** = 5 TD + 5 XP.
- Forge reach **32** before the final play = 4 TD + 2 XP + 2 FG
  (one XP blocked, one 2-pt attempt failed — both on the page in
  `canon.md`'s 12-event quarter-by-quarter table).
- Final situation: Q4, 0:04, 4th & 14, ball on the FRG 32, no timeouts.
- The Hail Mary is caught in the end zone as the clock hits 0:00: **+6 →
  38–35 Forge**.
- **The try is waived**: at 35 < 38 the point-after cannot change the winner,
  so Forge declines the untimed try. No kick, no play after the catch — the
  Hail Mary itself is the winning score. `verify.sh` confirms no
  extra-point frame and no "39" anywhere in the film.
- Burned-in boards verified from the actual file: `BAY 35 · FRG 32 | 4TH &
  14 | 0:04 Q4` before the snap, `FRG 38 · BAY 35 | 0:00 Q4` at the catch,
  `FINAL · TRY WAIVED` after the signal, closing card `38–35 · REDHAWK
  FORGE · FICTIONAL SIMULATION`.

## File map

| path | what |
|---|---|
| `final-38-35.mp4` | the film |
| `canon.md` | single source of truth: scores, clock, ledger, waived try |
| `shot-list.json` | 6 beats, timings, cameras, burned-in boards, captions, 12 audio cue ids |
| `screenplay.md` | the timed script and broadcast call |
| `sound-palette.md` | sound design and mastering targets |
| `render.html`, `capture.mjs`, `capture-strips.mjs` | deterministic renderer and headless-Chrome capture |
| `shots/`, `audio/` | intermediate frames and synthesized cues (kept out of any commit) |
| `assemble.sh` | deterministic ffmpeg assembly graph |
| `verify.sh`, `verification.json`, `verify-frames/` | gates and evidence |
| `capabilities.json` | host tool probe (task 1.a) |

Not published. Nothing here has been committed or pushed; publication is
parent-owned and requires a separate exact-SHA harness receipt.
