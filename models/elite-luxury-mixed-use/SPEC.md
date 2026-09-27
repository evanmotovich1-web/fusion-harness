# SPEC — Elite Luxury Mixed-Use Development Model (frozen)

Single source of truth for the workbook build (task 2.b), the validator (task 3.a), and the preview (task 3.b).
Changes to this file after freeze require the architect's sign-off. All downstream artifacts must match this spec exactly.

- Deliverable workbook: `models/elite-luxury-mixed-use/elite-luxury-mixed-use-model.xlsx`
- Generator: `models/elite-luxury-mixed-use/build_model.py` (python3 + openpyxl; formulas as strings, no cached values required)
- Validator: `models/elite-luxury-mixed-use/check_model.py` (recomputes identities from input cells, never from cached values)
- Nature: illustrative TEMPLATE. Not a live deal, not an offering, not investment advice.

## 0. Request reconciliation

- "Sulfur curve" in the cut-off title is read as the **SOFR curve** named in the request body. There is exactly one SOFR curve sheet.
- The construction **spend S-curve** (draw schedule) is a separate object required by floating-rate construction debt. It is not a second reading of "sulfur".
- Components: luxury residential (condo, for sale), retail, hotel. Waterfall has exactly four tiers.
- The truncated title adds no fourth component and no other requirement.

## 1. Sheet map (16 sheets, exact names, no spaces)

| # | Sheet | Kind |
|---|---|---|
| 1 | Cover | static |
| 2 | Assumptions | inputs + register |
| 3 | SOFR | inputs + timeline |
| 4 | SourcesUses | calc (one column) |
| 5 | SpendCurve | calc (monthly) |
| 6 | CondoSellout | calc (monthly) |
| 7 | RetailProForma | calc (monthly) |
| 8 | HotelProForma | calc (monthly) |
| 9 | ConstructionDebt | calc (monthly) |
| 10 | PermanentDebt | calc (monthly) |
| 11 | HotelValuation | calc (point-in-time) |
| 12 | RetailValuation | calc (point-in-time) |
| 13 | ProjectCF | calc (monthly) |
| 14 | Waterfall | calc (monthly) |
| 15 | Returns | calc (summary) |
| 16 | Checks | identities (TRUE/FALSE) |

## 2. Timeline

- Monthly, 84 periods, columns **C through CH** on every calc sheet (col A = row labels, col B = units/notes).
- Row 2 = month index 1..84; row 3 = end-of-month date (first close month + n − 1).
- Milestone defaults (named inputs on Assumptions): construction M1–M30 (`CONSTR_MONTHS`=30), retail open M29 (`RETAIL_OPEN_M`), hotel open M31 (`HOTEL_OPEN_M`), first condo closing M33 (`FIRST_CLOSING_M`), sellout span 36 months (`CLOSINGS_SPAN_M`=36, last closing M68), permanent conversion M72 (`PERM_CONV_M`), terminal sale/analysis end M84 (`EXIT_M`=84, fixed at last column).

## 3. Input register (defined names, workbook scope)

Every input below is a blue-font value cell on Assumptions (or SOFR rate column). Defaults are illustrative. No other cell in the workbook may hold a hardcoded numeric driver; all outputs are formulas starting with `=`.

### 3.1 Timeline
| Name | Default | Unit |
|---|---|---|
| CONSTR_MONTHS | 30 | months |
| RETAIL_OPEN_M | 29 | month |
| HOTEL_OPEN_M | 31 | month |
| FIRST_CLOSING_M | 33 | month |
| CLOSINGS_SPAN_M | 36 | months |
| PERM_CONV_M | 72 | month |
| EXIT_M | 84 | month (fixed) |

### 3.2 Condo program (for-sale)
| Name | Default | Unit |
|---|---|---|
| UNITS_STUDIO / SQFT_STUDIO / PPSF_STUDIO | 36 / 650 / 1,600 | units / SF / $PSF |
| UNITS_1BR / SQFT_1BR / PPSF_1BR | 72 / 950 / 1,750 | " |
| UNITS_2BR / SQFT_2BR / PPSF_2BR | 54 / 1,450 / 1,900 | " |
| UNITS_3BR / SQFT_3BR / PPSF_3BR | 14 / 2,100 / 2,200 | " |
| UNITS_PH / SQFT_PH / PPSF_PH | 4 / 3,200 / 2,800 | " |
| PARKING_SPACES / PARKING_PRICE | 180 / 75,000 | spaces / $ |
| STORAGE_UNITS / STORAGE_PRICE | 120 / 15,000 | units / $ |
| CLOSING_COST_PCT | 5.0% | % of gross condo revenue (transfer taxes, brokers) |
| MARKETING_PCT | 1.5% | % of gross condo revenue |

Unit-price escalation during sellout is intentionally omitted (contract-price closings).

### 3.3 Development budget
| Name | Default | Unit |
|---|---|---|
| LAND_COST | 85,000,000 | $ |
| ACQ_COST_PCT | 1.0% | % of land |
| RES_GSF / HOTEL_GSF / RETAIL_GSF | 240,000 / 150,000 / 25,000 | SF |
| HC_PSF_RES / HC_PSF_HOTEL / HC_PSF_RETAIL | 700 / 850 / 600 | $PSF |
| CONTINGENCY_PCT | 4.0% | % of hard costs |
| SOFTCOST_PCT | 12.0% | % of hard costs |
| HOTEL_KEYS | 200 | keys |
| FFE_PER_KEY | 45,000 | $/key |
| FFE_PSF_RETAIL | 85 | $PSF |
| DEVFEE_PCT | 4.0% | % of (land + acq + hard + contingency + soft + FF&E) |

### 3.4 Construction debt (floating)
| Name | Default | Unit |
|---|---|---|
| LTC_PCT | 60.0% | % of total uses incl. interest reserve |
| CT_SPREAD_PCT | 2.75% | annual, over SOFR |
| SOFR_FLOOR_PCT | 0.00% | annual |
| AVG_DRAWN_FRAC | 0.55 | avg drawn fraction used to size the interest reserve |
| CT_COSTS_PCT | 0.75% | loan closing costs, % of commitment |

### 3.5 Permanent debt (fixed-rate at conversion)
| Name | Default | Unit |
|---|---|---|
| PERM_LTV | 55.0% | LTV cap on hotel+retail value |
| PERM_DSCR | 1.40x | DSCR cap on stabilized NOI |
| PERM_DY | 9.0% | debt-yield cap on stabilized NOI |
| PERM_RATE_PCT | 5.75% | annual fixed |
| PERM_AMORT_YRS | 30 | amortization years |
| PERM_COSTS_PCT | 0.50% | financing costs, % of proceeds |

### 3.6 Hotel operating
| Name | Default | Unit |
|---|---|---|
| ADR_Y1 | 650 | $ |
| ADR_GROWTH_PCT | 2.5% | per year |
| OCC_Y1 / OCC_Y2 / OCC_STAB | 65% / 75% / 82% | occupancy by operating year |
| FB_REV_PCT | 35% | % of rooms revenue |
| OTHER_REV_PCT | 8% | % of rooms revenue |
| HOTEL_UNDIST_PCT | 22% | undistributed expenses (G&A, SM, utilities) as % of total revenue |
| HOTEL_MGMT_PCT | 3.0% | management fee, % of total revenue |
| REPL_RESERVE_PCT | 3.5% | % of total revenue |
| HOTEL_CAP | 7.25% | exit/stabilization cap rate |

### 3.7 Retail operating
| Name | Default | Unit |
|---|---|---|
| RETAIL_BASE_PSF | 120 | $PSF year-1 base rent |
| RETAIL_ESC_PCT | 3.0% | annual escalation from retail open |
| RETAIL_RECOV_PSF | 18 | recoverable pool (CAM/tax/insurance), $PSF, escalates same |
| RETAIL_RECOV_RATIO | 90% | recovery ratio |
| RETAIL_VAC_PCT | 5.0% | vacancy/credit loss on base+recoveries |
| RETAIL_OP_PSF | 9 | non-recoverable opex, $PSF |
| RETAIL_MGMT_PCT | 2.0% | mgmt fee, % of EGI |
| RETAIL_CAP | 6.25% | exit/stabilization cap rate |

### 3.8 Exit and capital structure
| Name | Default | Unit |
|---|---|---|
| SELL_COST_PCT | 1.5% | on hotel+retail terminal value |
| GP_EQUITY_PCT | 10.0% | GP co-invest share of equity |
| PREF_PCT | 8.0% | annual LP preferred return, monthly compounding |
| CATCHUP_PCT | 20.0% | GP catch-up target, % of profits |
| T3_ACCRUAL_PCT | 15.0% | tier-3 hurdle accrual rate (see §7) |
| T3_LP_SPLIT | 70% | LP share in tier 3 |
| T4_LP_SPLIT | 80% | LP share in tier 4 |

## 4. SOFR sheet ("the sulfur curve")

- One row per month 1..84: Month | Date | `SOFR_Fwd` (blue input) | Source label.
- The rate column is a **paste target for a Chatham forward curve**. It ships with a placeholder path labeled per row: `ASSUMPTION — placeholder forward; not a live Chatham quote. Paste Chatham forwards here.`
- Placeholder path (illustrative only): 4.30% at M1 gliding linearly to 3.60% by M24, flat 3.60% thereafter.
- No cell, label, or comment anywhere in the workbook may state the curve was fetched from Chatham. Chatham is a paste target only. (Checked by C12.)
- Debt formulas reference this sheet by month row. The permanent loan rate is the fixed `PERM_RATE_PCT` from conversion.

## 5. Sources & Uses, spend curve, construction debt

### 5.1 Uses (one-column schedule, all formulas)
- Land + acquisition costs (`LAND_COST`×(1+`ACQ_COST_PCT`)), funded at M1.
- Hard costs = `RES_GSF`×`HC_PSF_RES` + `HOTEL_GSF`×`HC_PSF_HOTEL` + `RETAIL_GSF`×`HC_PSF_RETAIL`.
- Contingency = `CONTINGENCY_PCT`×hard; soft = `SOFTCOST_PCT`×hard.
- FF&E = `HOTEL_KEYS`×`FFE_PER_KEY` + `RETAIL_GSF`×`FFE_PSF_RETAIL`.
- Developer fee = `DEVFEE_PCT`×(land+acq+hard+conting+soft+FF&E).
- Interest reserve (estimated, linear, no circularity): `LTC_PCT`×(uses ex-interest) × (`SOFR_Fwd` average over construction + `CT_SPREAD_PCT`)/12 × `CONSTR_MONTHS` × `AVG_DRAWN_FRAC`.
- Loan costs = `CT_COSTS_PCT`×commitment; perm financing costs appear at conversion, not here.

### 5.2 Sources
- Construction commitment = `LTC_PCT` × total uses **including** the interest reserve.
- Equity requirement = total uses − commitment (single contribution at M1, split GP/LP by `GP_EQUITY_PCT`).

### 5.3 SpendCurve
- Cumulative construction spend fraction at month t: S(t) = (t/`CONSTR_MONTHS`)^2.2; monthly weight w_t = S(t) − S(t−1). Land+acquisition spent at M1. All non-land, non-interest uses (hard, conting, soft, FF&E, fee) spread on w_t. Weights sum to 1 exactly.

### 5.4 ConstructionDebt (floating, monthly)
- Opening balance B_open(t); draws(t) = budget needs per SpendCurve not covered by equity (equity first: while equity cash remains it funds spend, then draws) **plus** capitalized interest.
- Interest(t) = B_open(t) × (MAX(`SOFR_FLOOR_PCT`, SOFR_Fwd(t)) + `CT_SPREAD_PCT`)/12, computed on the **opening balance only** — no circular reference, no Excel iteration.
- Interest capitalizes: added to balance via draw from the interest reserve.
- Condo net sales proceeds pay the balance down: after each month's closings, repayment = min(balance, condo net proceeds that month).
- Constraints every month: 0 ≤ balance ≤ commitment (C3). At `PERM_CONV_M` any remaining balance is repaid from permanent proceeds.
- Roll-forward identity: B_close(t) = B_open(t) + draws(t) − repayments(t); B_open(t+1) = B_close(t) (C10).

## 6. Component pro formas and valuations

### 6.1 CondoSellout (for-sale)
- Closings by type start at `FIRST_CLOSING_M` over `CLOSINGS_SPAN_M`: per month = base = ROUNDDOWN(units/span), plus 1 in each of the first (units − base×span) months; Σ closings = inventory exactly (C5).
- Gross revenue = closings_t × unit price + parking + storage (parking/storage released pro-rata with closings).
- Net revenue = gross × (1 − `CLOSING_COST_PCT` − `MARKETING_PCT`). Net revenue services the construction loan paydown (§5.4); the remainder flows to distributable cash.
- Condo economics = sellout revenue net of costs, flowing through ProjectCF. **No cap rate is applied to condos** (C6 covers hotel/retail only).

### 6.2 HotelProForma (monthly from `HOTEL_OPEN_M`)
- ADR(year y) = `ADR_Y1`×(1+`ADR_GROWTH_PCT`)^(y−1); occupancy by operating year: Y1 `OCC_Y1`, Y2 `OCC_Y2`, Y3+ `OCC_STAB`.
- Rooms revenue = keys × days × occ × ADR. Total revenue = rooms × (1 + `FB_REV_PCT` + `OTHER_REV_PCT`).
- Hotel NOI = total revenue × (1 − `HOTEL_UNDIST_PCT` − `HOTEL_MGMT_PCT` − `REPL_RESERVE_PCT`).
- Month-count convention: partial operating years by calendar months from opening.

### 6.3 RetailProForma (monthly from `RETAIL_OPEN_M`)
- Base rent(month m from open) = `RETAIL_BASE_PSF` × (1+`RETAIL_ESC_PCT`)^(floor(m/12)) × `RETAIL_GSF`/12.
- Recovery income = recoverable pool (same escalation) × `RETAIL_RECOV_RATIO`/12; EGI = (base+recoveries) × (1−`RETAIL_VAC_PCT`).
- Retail NOI = EGI − non-recoverable opex (`RETAIL_OP_PSF`×`RETAIL_GSF`/12) − mgmt fee (`RETAIL_MGMT_PCT`×EGI).

### 6.4 Valuations (at `EXIT_M`)
- T12 NOI = trailing 12 months NOI ending `EXIT_M` (HotelValuation / RetailValuation sheets show the T12 build-up line by line).
- Hotel value = T12 hotel NOI / `HOTEL_CAP`; Retail value = T12 retail NOI / `RETAIL_CAP` (C6).
- Terminal proceeds at `EXIT_M` = (hotel value + retail value) × (1 − `SELL_COST_PCT`) − permanent payoff.

### 6.5 PermanentDebt
- Sized at `PERM_CONV_M` on stabilized (T12 at conversion-or-exit, use T12 ending `PERM_CONV_M`) hotel+retail NOI and terminal hotel+retail value:
  - LTV size = `PERM_LTV` × (hotel+retail value);
  - DSCR size = (NOI_T12/`PERM_DSCR`) / PMT-factor(`PERM_RATE_PCT`/12, `PERM_AMORT_YRS`×12);
  - DY size = NOI_T12/`PERM_DY`;
  - Proceeds = MIN of the three (C4). Net proceeds = proceeds × (1 − `PERM_COSTS_PCT`) − construction payoff.
- Monthly debt service: interest on opening balance at `PERM_RATE_PCT`/12; amortizing per the PMT schedule; NOI after debt service flows to distributable cash.
- At `EXIT_M`: payoff = opening balance that month.

## 7. Waterfall (four tiers, on monthly distributable cash)

Distributable cash(t) = condo net revenue after construction-loan paydown + hotel NOI + retail NOI − perm debt service + refi net proceeds at `PERM_CONV_M` + terminal net proceeds at `EXIT_M`.

Waterfall mechanics (XIRR is an **output only**, never a distribution trigger):

- **T1 — Return of capital + preferred return (100% LP):** 100% of cash to LP until cumulative LP distributions ≥ LP contributed capital + accrued pref, where pref accrues monthly on unreimbursed LP capital at `PREF_PCT`/12, compounding.
- **T2 — GP catch-up (100% GP):** 100% to GP until GP cumulative profit share = `CATCHUP_PCT` × (profits distributed in T1 + T2 combined). Marginal formula: total T2 = `CATCHUP_PCT`/(1−`CATCHUP_PCT`) × pref profit paid in T1. "Profit" = distributions in excess of returned capital.
- **T3 — First promote (70/30):** `T3_LP_SPLIT`/rest to LP until cumulative LP distributions ≥ LP contributed capital accrued at `T3_ACCRUAL_PCT`/12 monthly compounded from contribution (soft hurdle — accrual gate, not XIRR gate; this keeps formulas and the validator identical).
- **T4 — Residual (80/20):** `T4_LP_SPLIT`/rest thereafter, forever.

Every month: T1+T2+T3+T4 distributions = distributable cash exactly; after T4 opens, the residual exhausts 100% (C7). No tier distributes while its predecessor gate is unmet (C8).

## 8. ProjectCF and Returns

- ProjectCF aggregates monthly: revenue by component, debt draws/repayments/interest, capital events, net equity cash flow, distributable cash, waterfall outflows by tier, retained cash (must be 0 by `EXIT_M`).
- Returns: total-equity cash flow series (M1 outflow, monthly inflows) → project XIRR; LP and GP series → XIRR and equity multiples; profit split summary (LP $, GP $, promote $). Use Excel `XIRR` formulas. A small sensitivity block on Returns (hotel cap ±50 bps vs ADR ±10% grid, formulas) is optional, not required by checks.

## 9. Checks sheet (the exact identity list the validator recomputes)

Tolerance: $1 for balances/level checks, $0.01 for per-month flow identities. Checks sheet holds TRUE/FALSE formulas per item plus one master `AND(...)` cell.

| ID | Identity |
|---|---|
| C1 | Sources = Uses, ±$1 |
| C2 | Every month: construction interest = opening balance × (MAX(`SOFR_FLOOR_PCT`, SOFR_Fwd(t)) + `CT_SPREAD_PCT`)/12, ±$0.01 |
| C3 | Every month: 0 ≤ construction balance ≤ commitment |
| C4 | Perm proceeds = MIN(LTV size, DSCR size, DY size), ±$1 |
| C5 | Per type: Σ monthly closings = unit inventory; gross sellout = Σ(units × price) + parking + storage, ±$1 |
| C6 | Hotel value = T12 hotel NOI/`HOTEL_CAP` and retail value = T12 retail NOI/`RETAIL_CAP`, ±$1 |
| C7 | Every month: T1+T2+T3+T4 = distributable cash, ±$0.01; retained cash = 0 at `EXIT_M` |
| C8 | Tier ordering: no T2 flow until T1 fully paid; no T3 until T2 complete; no T4 until T3 gate met |
| C9 | Σ equity contributions = equity requirement, ±$1 |
| C10 | Construction balance roll-forward ties: B_open(t+1) = B_open(t) + draws − repayments, all months |
| C11 | Structural: 16 sheets present with exact names; every calculated cell is a formula (`=...`); no `#REF!`, `#NAME?`, `#VALUE!`, `#CYCLE!` strings; no merged cells in data ranges |
| C12 | SOFR sheet Source column carries the ASSUMPTION label; no cell in the workbook claims a live Chatham fetch |

The validator (`check_model.py`) recomputes C1–C10, C12 independently in python from the input cells and formula definitions in this spec, and reads C11 from the workbook structure. It never trusts cached values. If LibreOffice (`soffice`) is already installed it may additionally recalc; if not, it records that no independent recalc ran — do not install LibreOffice.

## 10. Formatting conventions

- Inputs: blue font (RGB 0000FF), light-yellow fill optional, on Assumptions and the SOFR rate column only.
- Outputs: black font formulas. Currency `$#,##0`; percentages `0.00%` (bps inputs as percents); months integer; PSF `$#,##0`.
- Column A labels bold; row 1 sheet titles; freeze panes at C4 on monthly sheets.
- No merged cells in any data range. Sheet names exactly as §1.
- Cover disclaimer (verbatim): `ILLUSTRATIVE TEMPLATE — NOT A LIVE DEAL, NOT AN OFFERING, NOT INVESTMENT ADVICE. The SOFR forward curve is a placeholder assumption, not a live Chatham quote; paste live forwards into the SOFR sheet. All figures are illustrative defaults.`

## 11. Scope guards

- New files only under `models/elite-luxury-mixed-use/`. No npm/package.json changes. No edits to `extensions/fusion-harness/modules/knowledge-base.ts` or any pre-existing path. No commits, pushes, or publication.
- The vendored `AGENT_SYSTEM_PROMPT.md` install (tasks 1.b/2.a) is independent of this spec; the generator follows this spec, not the vendored prompt.
