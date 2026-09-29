# ab/ — judge runner output (task 3.a)

Canary validity test, then a blind identity-stripped A/B, judging two evidence
packs with an isolated out-of-roster model. Nothing in this directory is a
finding. Raw judge output is the record; no judge prose was edited, trimmed or
reworded by the runner.

## Order of operations

1. `runner.py plan-canary` wrote `canary-assignment.json` and `packs/C0..C3.json`
   **before any judge call**.
2. `runner.py run-canary 1|2|3` — three judge calls. `raw/canary-call-N.txt`.
3. `runner.py verdict-canary` — mechanical triage against the PASS conditions
   in `../canary.md`. `canary-verdict.json`.
4. `runner.py plan-ab` wrote `assignment.json` **before the A/B judge call**.
5. `runner.py run-ab` — one judge call. `raw/ab-call.txt`, `ab-result.json`.
6. `runner.py verify-strip` — proves the sent prompt carried no identity.
7. `runner.py compare-ab` — arithmetic on the A/B margins only.

## Judge

Pinned in `../capabilities.json` and used verbatim:

```
printf '%s' "$PROMPT" | VAULT_SEMANTIC_HOOK_DISABLE=1 claude -p \
  --strict-mcp-config --no-session-persistence \
  --disallowedTools "Bash,Read,Grep,Glob,WebFetch,WebSearch,Task,Edit,Write"
```

`claude` 2.1.284, out of roster, tools denied (containment test returns
`NO_TOOLS`). Four calls, 56.3 s total, every call exit 0, every stderr empty.
The prompt is the `../rubric.md` template with only the two packs substituted.
`rubric_body_sha256` was recomputed before the first call and equals the frozen
value in `../rubric.md`: `88ace4f2…d69925`.

## Files

| file | what |
|---|---|
| `runner.py` | the whole runner. Modes: `plan-canary`, `run-canary N`, `verdict-canary`, `plan-ab`, `run-ab`, `verify-strip`, `compare-ab`, `hash` |
| `canary-assignment.json` | seed 38035, label→canary map, the three call pairings. Written first |
| `packs/C0..C3.json` | the four canary packs. C0 is `judge_packs.audit` unmutated |
| `raw/canary-call-*.txt` | raw judge stdout, unedited |
| `raw/ab-call.txt` | raw judge stdout for the A/B, unedited |
| `raw/MANIFEST.sha256` | `shasum -c raw/MANIFEST.sha256` from this directory |
| `canary-verdict.json` | C0–C3 pass/fail, `judge_valid`, and measured judge stability |
| `assignment.json` | seed 38036, FILM A = `audit`, FILM B = `reference`. Written first; never sent to the judge |
| `ab-result.json` | the A/B judge object, extracted verbatim, with the assignment attached |
| `strip-check.json` | identity-stripping proof: rebuilt prompt sha matches the sent prompt; 0 forbidden tokens |
| `ab-mechanical-comparison.json` | axis margins vs the judge's own measured spread. Arithmetic only |

## Outcomes, mechanical

Canary (`canary-verdict.json`): C1 caught (score 39 named), C2 caught (clock
0:03 at the catch, still running at the end), C3 caught (`loud` 2, "the audio is
flat"), C0 complete with no defect attributed to it. **`judge_valid: true`.**

Judge stability, measured on the identical clean pack judged in all three
canary calls: `vivid` 3/3/3 (spread 0), `loud` 3/3/5 (spread 2), `exciting` 3/3/4
(spread 1), `final_play` 5/5/5 (spread 0). The judge is sensitive to planted
defects and is **not** stable on `loud` and `exciting`.

A/B (`ab-result.json`, `ab-mechanical-comparison.json`): FILM A = `audit`,
FILM B = `reference`. Judge scores A `vivid 2, loud 3, exciting 2, final_play 5`
(mean of the three sensory axes 2.333, band BAD) and B `vivid 4, loud 4,
exciting 4, final_play 3` (mean 4.0, band GOOD); `overall_winner: "B"`.
Axis margins: vivid 2 (spread 0), loud 1 (spread 2), exciting 2 (spread 1),
final_play 2 (spread 0, favors A). All four margins are ≤ the global spread
max of 2; vivid, exciting and final_play each exceed their own axis spread.

## Constraints for the findings task

- `../rubric.md` R2: the judge never watched either film. Every sensory verdict
  in this directory is a proxy read from numeric packs and is
  **non-authoritative** until a human watches.
- The judge's `overall_winner` and the axis-margin arithmetic point different
  ways on `final_play` versus `vivid`/`exciting`; both are in
  `ab-mechanical-comparison.json`. This runner did not adjudicate, and no
  file here should be cited as if it had.
- `../rubric.md` R1: the settled technical gates stay settled passes. Nothing
  here may be used to reopen them.
- Quote `raw/*.txt` when citing the judge. `ab-result.json` is a verbatim
  extraction, not a paraphrase.
- Rerunning any judge call overwrites raw output; the current call hashes are in
  `raw/MANIFEST.sha256`.
