# Canary set — hail-mary-eval judge validity test

Four unlabeled evidence packs in randomized order: one clean, three with a
planted defect. The judge (same prompt, same containment as the real A/B)
must catch all three defects and pass the clean pack. Any miss invalidates
the judge: its A/B verdict is void and the eval records judge-invalid
(R4a applies — sensory axes unscored, gap stated). The runner (task 3.a)
builds these packs from the real evidence.json values by mutation, saves
raw judge output unedited, and reveals labels only afterward.

## C1 — wrong score on the board (39)

Mutate the scoreboard timeline: one post-catch entry reads `39` instead of
`38`. PASS condition: the judge either scores final_play < 3 with a quoted
transcript/timeline line, or its `one_line`/`what_the_packs_cannot_show`
text names the score anomaly (39, wrong total, or arithmetic break).
FAIL condition: 39 passes unremarked while the clean pack's equivalent
lines pass too.

## C2 — clock does not die at the catch

Mutate the clock timeline: the catch beat shows `0:03` and the film ends
with the clock still running. PASS condition: judge flags the clock
surviving the catch or final_play < 3 quoting the timeline. FAIL: unremarked.

## C3 — no pre-catch crowd drop (flat dynamics)

Mutate the loudness envelope: short-term LUFS flat (±1 LU) into the catch
and drop-to-catch span < 2 LU. PASS condition: judge scores `loud` ≤ 2 or
names the missing dynamic swell/drop. FAIL: a flat arc scored 4+.

## C0 — clean pack

The unmutated evidence pack of the film under audit. PASS condition: judge
returns a complete JSON per the rubric with no nulls except justified ones
and does not flag a nonexistent defect. FAIL: any hallucinated defect.

## Validity ledger (filled by 3.a)

| canary | planted | judge caught? | raw line |
|---|---|---|---|
| C0 | none | — | |
| C1 | 39 on board | | |
| C2 | clock alive | | |
| C3 | flat dynamics | | |

Judge valid iff C0 passes and C1–C3 all pass. Randomization: the four
packs get shuffled labels (P1..P4); the shuffle seed and mapping are
recorded in `ab/canary-assignment.json` before the judge runs.
