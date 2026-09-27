# HANDOFF — excel-agent workflow + elite luxury mixed-use development model

Written by the Pi host during recovery. Collaboration task 4.a stayed blocked: that slot was read-only and did not create this file. This note records what the host rechecked on disk. It does not mark the collaboration accepted or successful.

## Deliverables

| Artifact | Path | Host evidence |
|---|---|---|
| Workbook | `models/elite-luxury-mixed-use/elite-luxury-mixed-use-model.xlsx` | sha256 `e2780e226f39d5d7301aebb756bdab6e52ebb86e8529c1c881fa22ef2b3908ea`; zip CRC ok; 16 sheets in spec order; 79 defined names; 12,801 formulas; 163 numeric inputs; 0 merged cells; 0 formula error tokens |
| Generator | `models/elite-luxury-mixed-use/build_model.py` | sha256 `55fd9ac321f257168f503564eebc16e2e366d8ca186a689a0b65491d7e841ca0` |
| Validator | `models/elite-luxury-mixed-use/check_model.py` | host re-run exit 0; workbook hash unchanged |
| Spec | `models/elite-luxury-mixed-use/SPEC.md` | 16-sheet map, 84-month timeline, SOFR paste rules, four-tier waterfall, C1–C12 |
| Browser preview | `models/elite-luxury-mixed-use/preview.html` | 16 sheet names present; illustrative disclaimer present; no `<script>`; no http(s) URLs |
| Child open log | `models/elite-luxury-mixed-use/PREVIEW.log` | child `open` exit 0 at 2026-09-26T00:00:52Z; host reopened the same file, exit 0 at 2026-09-26T00:05:06Z |
| Validation record | `models/elite-luxury-mixed-use/VALIDATION.md` | C1–C12 PASS. Host re-run refreshed `Checked at` to 2026-09-26T00:03:53Z |
| Vendored prompt | `.pi/fusion-harness/excel-agent/AGENT_SYSTEM_PROMPT.md` | 24,630 bytes; sha256 `b18baa28193b2abd1ab2bc88e3512fd6ee5a0daad644a36942f42594fbc5ab0d` matches `SOURCE.json` |
| Workflow | `.pi/fusion-harness/workflows/excel-build.yaml` | host `loadWorkflow` exit 0; id `excel-build`; command `fh-only`; confirm true |
| Dedicated stack | `.pi/fusion-harness/workflows/stacks/model-stack-excel-build.yaml` | builder appends the vendored prompt plus the bridge line; architect append count 0 |

## What the workbook contains

Illustrative luxury condo + retail + hotel template, not a live deal and not an offering.

- Monthly model, 84 months.
- Paste-in SOFR forwards. Placeholder path is 4.30% at M1 gliding to 3.60% by M24, then flat. Each source cell says `ASSUMPTION — placeholder forward; not a live Chatham quote.`
- Floating construction debt: interest on the opening balance equals `balance * (MAX(floor, SOFR_t) + spread) / 12`. Condo closings pay the loan down. No circular interest reserve.
- Permanent debt at a conversion month: `MIN` of LTV, DSCR, and debt-yield on hotel + retail only.
- Condo sellout, hotel and retail pro formas, cap-rate valuations, four-tier waterfall. XIRR is an output, not the distribution engine.

Headline figures from the host re-run of `check_model.py` (recomputed from inputs, not from Excel cached values):

- Sources = uses: $503,713,355.14
- Equity requirement: $201,485,342.05
- Condo gross sellout: $421,730,000.00
- Construction commitment: $302,228,013.08; peak closing balance $287,059,658.72
- Permanent proceeds: $349,280,194.50, binding constraint LTV
- Hotel value: $599,982,092.82 = T12 NOI / 7.25%
- Retail value: $52,932,556.54 = T12 NOI / 6.25%
- Waterfall residual after tier 4: $0

## excel-build workflow usage

Triggers: `build excel`, `excel model`, `workbook`.

The workflow is `fh-only` with confirm on. Its stack is dedicated. The builder appends `.pi/fusion-harness/excel-agent/AGENT_SYSTEM_PROMPT.md`, then this bridge: harness tools take precedence; any tool call the vendored prompt assumes that is not installed is advisory.

The live fusion stacks were not edited. This recovery did not apply the excel stack. Applying it would replace the session stack.

The GitHub prompt is not Pi's host system prompt. It is appended only on the excel-build builder, behind a bridge. No stop-condition was hit on fetch: commit `2afa48049502b60ae6f8afe963b52837c691b2fd`, MIT grant in the vendored README, no root LICENSE file.

## Tool install (host, after the blocked collaboration)

The 15 CLI tools are installed at `.pi/fusion-harness/excel-agent/src` from the same commit. Prompt sha256 still matches `SOURCE.json`. Runtime is a local venv: CPython 3.11.16, openpyxl 3.1.5, pandas 3.0.6. Runner:

```bash
.pi/fusion-harness/excel-agent/excel-tool excel_create_new.py --output /tmp/smoke.xlsx --sheets "Cover,Checks" --json
```

Host smoke: that command exited 0 and `excel_get_info.py` returned `status: success`. `uv python tools/...` is not a runner here (`uv python` is the version manager) and was not shimmed. `--allow-external`, background processes, role replacement, and LibreOffice were not installed. This session's model stack was not switched.

Run it with `/find-workflow build excel`, then confirm. That command applies the excel-build stack for the session and will switch the host model to `google/gemini-3.7-flash`.

## Host caveats

- No LibreOffice and no Excel recalc. `soffice` is absent and was not installed. The browser preview shows formula text because the saved workbook has no cached values. Open the `.xlsx` in Excel or Numbers to calculate.
- DSCR sizing follows the frozen spec literally: annual max debt service divided by a monthly `PMT` factor, with no `/12`. On these defaults that constraint is about 12x too large ($5,572,644,922 vs a monthly-consistent size near $464,387,077). LTV still binds, so proceeds do not change at the default inputs. The formula will mis-size the loan if inputs change enough for DSCR to bind. The host did not rewrite the spec, generator, or workbook.
- SOFR rates are placeholders. Do not describe them as a Chatham quote.
- `extensions/fusion-harness/modules/knowledge-base.ts` was already dirty before this run (mtime 2026-09-25T16:49:11, before SPEC.md). Its diff has no excel/condo terms. This recovery did not edit it.
- No commit, push, publish, or outreach.

## Regeneration

```bash
python3 models/elite-luxury-mixed-use/build_model.py
python3 models/elite-luxury-mixed-use/check_model.py
open models/elite-luxury-mixed-use/preview.html
```
