# VALIDATION — elite-luxury-mixed-use-model.xlsx

Independent read-only check of the saved workbook. Identities were recomputed from named input cells and the SOFR rate column. Cached Excel values were not read and were not used. The workbook was not modified.

## Commands

| Command | Exit | Result |
|---|---:|---|
| `python3 models/elite-luxury-mixed-use/check_model.py` | 0 | all identities passed |
| `command -v soffice` | 1 | not found |
| `test -x /Applications/LibreOffice.app/Contents/MacOS/soffice` | 1 | absent |
| `test -x /opt/homebrew/bin/soffice` | 1 | absent |

LibreOffice is not installed. No headless recalc ran. Checker recomputation from input cells is authoritative. LibreOffice was not installed.

## Workbook

- Path: `/Users/evanmotovich/fusion-harness/models/elite-luxury-mixed-use/elite-luxury-mixed-use-model.xlsx`
- SHA-256 before: `e2780e226f39d5d7301aebb756bdab6e52ebb86e8529c1c881fa22ef2b3908ea`
- SHA-256 after: `e2780e226f39d5d7301aebb756bdab6e52ebb86e8529c1c881fa22ef2b3908ea`
- Hash unchanged: True
- OOXML: zip CRC ok, workbook content type present, worksheet parts 16
- workbook.xml sheets: Cover, Assumptions, SOFR, SourcesUses, SpendCurve, CondoSellout, RetailProForma, HotelProForma, ConstructionDebt, PermanentDebt, HotelValuation, RetailValuation, ProjectCF, Waterfall, Returns, Checks
- openpyxl sheets: Cover, Assumptions, SOFR, SourcesUses, SpendCurve, CondoSellout, RetailProForma, HotelProForma, ConstructionDebt, PermanentDebt, HotelValuation, RetailValuation, ProjectCF, Waterfall, Returns, Checks
- Defined names read: 79
- Formula cells: 12801
- Numeric input cells: 163
- SOFR inputs read: 84 cells, M1=4.300000%, M84=3.600000%
- Checked at: 2026-09-26T00:03:53Z

## Identities

| ID | Result | Evidence |
|---|---|---|
| C1 | PASS | sources $503,713,355.14, uses $503,713,355.14, gap $0.00, component tie $0.00 |
| C2 | PASS | max recomputed interest gap 0.000000; saved interest formulas match opening*(MAX(floor, SOFR_t)+spread)/12: True |
| C3 | PASS | open [$0.00, $287,059,658.72], after-draws max $288,578,682.75, close max $287,059,658.72, commitment $302,228,013.08 |
| C4 | PASS | proceeds $349,280,194.50 = MIN(LTV $349,280,194.50, DSCR $5,572,644,922.16, DY $505,873,560.14); binds LTV; formula match True |
| C5 | PASS | closing gaps {'STUDIO': 0.0, '1BR': 0.0, '2BR': 0.0, '3BR': 0.0, 'PH': 0.0}; gross $421,730,000.00 vs inventory value $421,730,000.00, gap $0.00 |
| C6 | PASS | hotel $599,982,092.82 = T12 $43,498,701.73 / 7.2500%; retail $52,932,556.54 = T12 $3,308,284.78 / 6.2500%; formula match True |
| C7 | PASS | max tier gap 0.000000; residual after tier 4 0.000000; retained at exit 0.000000; tier-4 plug formulas match True |
| C8 | PASS | tier-order breaches t2=0 t3=0 t4=0 |
| C9 | PASS | contributions $201,485,342.05, equity requirement $201,485,342.05, gap $0.00; formula match True |
| C10 | PASS | max roll-forward gap 0.000000; opening/closing formulas match True |
| C11 | PASS | 16 sheets match; formulas 12801; numeric inputs 163; merged none; formula-pattern problems 0; structural problems none |
| C12 | PASS | SOFR!D2:D85 carry the ASSUMPTION label: True; Chatham mentions 86; live-fetch claims 0 |

## Notes

- C4 uses the spec literal: DSCR size = (T12 NOI / PERM_DSCR) / PMT(PERM_RATE_PCT/12, PERM_AMORT_YRS*12, -1), with no extra /12. The binding constraint is reported from that definition.
- Prose on the Checks sheet names `#REF!`, `#NAME?`, `#VALUE!`, and `#CYCLE!` as the tokens being tested. Those label mentions are not formula errors and were not counted as C11 failures. No formula cell contains those tokens.
- Chatham text in the workbook is the placeholder denial and paste-target label. No cell claims a live Chatham fetch.

## Handoff

All checked identities passed. Task 3.b may render preview.html from this saved xlsx and must not modify it. No workbook patch is required.
