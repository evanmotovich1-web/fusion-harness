# EVAL — why the Hail Mary film was bad, and what would fix it

Subject: `self-compact/hail-mary/final-38-35.mp4` (sha256
`6a90e78a…bf489f`). Reference: `~/Movies/cowboys-hail-mary/…mp4`
(`1e40a4d2…c126f`), same host, same request, separate run.
Number sources: `evidence.json` (task 2.a, fresh measurements), `ab/`
(task 3.a, raw isolated-judge output), `../hail-mary/verification.json`.
Wiki citations verified in the local vault at `~/code/second-brain`.
Per rubric R1/R2: passed technical gates are not scored as failures here,
and every sensory verdict below is a proxy judgment, non-authoritative
until a human watches.

## 1. Technical row — what passed, stays passed

| gate | result |
|---|---|
| format h264 1920×1080 30 fps · aac 48 kHz stereo · 40.000 s | passed (verification.json) |
| loudness -14.0 LUFS / -2.7 dBTP, inside the frozen -16…-12 window | passed |
| scoreboard ledger 35–32 → 38–35 at 0:00, try waived, no extra-point frame | passed |
| determinism: sha freshly measured by this eval (`evidence.json films.audit.sha256`) equals verification.json's recorded sha and the delivered file | passed |

These are real and were the point of the gates. None of them measures
whether the film is good.

## 2. Request row — the measured gap

**One sentence:** the film is technically sound and story-accurate but
delivers a slideshow-grade 10 Hz motion, a dynamically flat mix, and
robotic narration where the request asked for vivid, loud, and exciting —
and the same host had already produced a reference that beats it on every
one of those axes.

Measured (audit vs reference; every value from evidence.json unless another source is named):

| axis | audit film | reference film |
|---|---|---|
| distinct rendered frames | 400 of 1,200 (duplication ×3) | 1,728 of 1,728 |
| effective motion | 10 Hz in a 30 fps container | 24 Hz native |
| integrated loudness | -14.0 LUFS (mid-window) | -9.9 LUFS |
| drop-to-catch span | -1.8 LU (-13.2 → -15.0, quieter at the catch) | +13.2 LU (-22.7 → -9.5) |
| narration | macOS `say` TTS (capabilities.json, 2.c report) | same tool (vault: coding-session-patterns.md:259) |
| motion energy on the catch beat (mean_ydif) | 1.62 (s04, t 18–26; catch_t 18.0) | 7.54 (s06, t 42–50; catch_t 47.0) |
| post-catch motion peak | 7.11 on the closing card (s06, t 33–40) | 10.30 at s08 (t 58–66), after rising 9.59 at s07 |

Acceptance-word coverage in the six authored artifacts (evidence.json):
`vivid` 0, `exciting` 0, `watchable` 0, `entertain` 0; `loud` 6 (all in
mastering-craft context, never as an acceptance criterion); `hail mary` 14,
`38-35` 17 + `38–35` 10. The two words naming the felt experience the
request actually asked for never entered any spec, gate, or report.

Blind A/B (out-of-roster isolated judge, identity-stripped, canary-valid;
source: ab/ab-result.json verbatim and ab/ab-mechanical-comparison.json —
raw judge output, not evidence.json):
audit `vivid 2, loud 3, exciting 2, final_play 5` vs reference
`vivid 4, loud 4, exciting 4, final_play 3`; overall winner: reference.
Mechanical margins vs the judge's own measured instability:
vivid 2 (spread 0) and exciting 2 (spread 1) exceed their axis spread;
loud 1 (spread 2) does not; final_play 2 favors the audit film (spread 0).

## 3. Root causes — wiring vs behavior

Method follows the vault's own adoption audit: measure first, then
separate wiring failures from behavior failures
(wiki/llmwiki-adoption.md:49-74; isolated-judge method at :414-423,
verified in the local vault).

Wiring (structural — no agent choice inside the run could have fixed it):

- W1. **Self-authored spec, self-run gates.** Every gate measured
  agreement with a spec the same three slots wrote. The vault already
  names this class: "an agent authoring its own score is the same
  counterfeit-completion class the bridge guards were built for"
  (wiki/dev-factory-build-story.md:234). GATE GREEN measured spec
  conformance, not quality.
- W2. **No quality vocabulary in the pipeline.** With `vivid`/`exciting`
  at zero occurrences upstream, no gate could fail on them (§2 counts).
- W3. **No human preview before delivery.** The first quality signal was
  Evan, after the film was final. The reference run's spec said the quiet
  part out loud — the operator's reaction is the acceptance test
  (vault record at wiki/coding-session-patterns.md:259-261).
- W4. **Verifier-is-author.** The conflict matrix (evidence.json) marks
  `judge_is_author` true only for the terra slot, which authored
  `sound-palette.md`, `screenplay.md`, `audio/`, `verify.sh`, and
  `verification.json` — and then judged the technical gates of the film
  those artifacts define. The eval's sensory judge is out-of-roster:
  `sensory_judge.judge_is_author` is false and its `authored_film_artifacts`
  is empty. That structural swap — author never judges — is why §2's A/B
  is worth anything at all.
- W5. **Knowledge injection was off-topic.** Both packets injected during
  the film run (sealbuild freshness, factory orchestrator) bore on the
  request not at all; the llmwiki-adoption measurement pattern — notes
  arrive, get opened, and rarely help — held here too, by absence.

Behavior (choices inside that wiring, ours to own):

- B1. 10 Hz capture economics: 400 frames in 50 strips traded motion life
  for build time inside the 60-second-per-command constraint the run-1
  vault note records (wiki/coding-session-patterns.md:259 — a vault
  claim, not a measurement of this eval) — and the reference cleared it
  at 24 Hz by staging.
- B2. Mastering to the middle of the loudness window (-14.0) when the
  request word was "loud" and the reference sits at -9.9; and letting the
  catch beat land -1.8 LU quieter than the preceding 4 s instead of
  cresting.
- B3. `say` narration accepted as "loud and electric" audio without a
  fight; the biggest motion spike was spent on the closing card (7.11)
  rather than the catch (≤2.23).

## 4. What was not bad

- The story spine: `final_play` 5 vs the reference's 3, margin 2 with
  zero judge spread — the Hail Mary, the clock dying, the waived try,
  and 38–35 are exact and land.
- Determinism and honesty of the technical rail: the sha freshly measured
  by this eval's measure.sh (`evidence.json films.audit.sha256`,
  `6a90e78a…bf489f`) equals verification.json's recorded sha and the
  delivered file; the decode check is clean; fiction labels are everywhere.
- The eval machinery this run produced: frozen rubric, canary-validated
  judge, conflict matrix — reusable for any next film.

## 5. Honest gaps — nobody can settle these without Evan

- Whether the look, the level, and the pacing feel vivid/loud/exciting at
  playback: proxy scores only (rubric R2); the judge never watched.
- The `loud` A/B margin sits inside the judge's own noise (spread 2);
  `exciting`'s margin 2 clears spread 1 but on n=1 judging.
- No re-render was attempted; whether "so bad" targets the craft (10 Hz,
  TTS) or the concept (stylized canvas vs photoreal) is Evan's call, and
  it routes the fix list differently (task 6.a).

## Traceability

Numbers → sources: §1 verification.json plus the sha equality between
`evidence.json films.audit.sha256`, verification.json's recorded sha, and
the delivered file; §2 evidence.json `films.audit.*`, `films.reference.*`,
`acceptance_words.totals`, `judge_packs.*.per_beat_frame_difference_energy`;
A/B scores ab/ab-result.json (verbatim from ab/raw/ab-call.txt); margins
and spreads ab/ab-mechanical-comparison.json, ab/canary-verdict.json;
W3/W4 vault citations read from `~/code/second-brain` (read-only). The
llmwiki-adoption and dev-factory pages cited above exist in the local
vault; line ranges are local. The 60-second build constraint is quoted
from wiki/coding-session-patterns.md:259 and is labeled as a vault claim.
No number in this file is quoted from a prose report.
