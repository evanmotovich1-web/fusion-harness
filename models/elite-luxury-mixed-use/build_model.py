#!/usr/bin/env python3
"""Build the elite luxury mixed-use template workbook from SPEC.md.

Formulas only on calculated cells. Blue-font values are inputs. This script
does not write cached calculated values. A Python mirror of the spec math
runs before save and refuses to emit the workbook if C1-C10/C12 design
identities fail.
"""

from __future__ import annotations

import math
import calendar
import sys
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.workbook.properties import CalcProperties
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "elite-luxury-mixed-use-model.xlsx"
MONTHS = 84
FIRST_COL = 3  # C
LAST_COL = 2 + MONTHS  # CH
SOURCE_LABEL = (
    "ASSUMPTION — placeholder forward; not a live Chatham quote. "
    "Paste Chatham forwards here."
)
DISCLAIMER = (
    "ILLUSTRATIVE TEMPLATE — NOT A LIVE DEAL, NOT AN OFFERING, NOT INVESTMENT ADVICE. "
    "The SOFR forward curve is a placeholder assumption, not a live Chatham quote; "
    "paste live forwards into the SOFR sheet. All figures are illustrative defaults."
)
SHEETS = [
    "Cover",
    "Assumptions",
    "SOFR",
    "SourcesUses",
    "SpendCurve",
    "CondoSellout",
    "RetailProForma",
    "HotelProForma",
    "ConstructionDebt",
    "PermanentDebt",
    "HotelValuation",
    "RetailValuation",
    "ProjectCF",
    "Waterfall",
    "Returns",
    "Checks",
]

# SourcesUses rows
SU_LAND, SU_ACQ, SU_LAND_ACQ = 4, 5, 6
SU_HARD_RES, SU_HARD_HOTEL, SU_HARD_RETAIL, SU_HARD = 7, 8, 9, 10
SU_CONTING, SU_SOFT = 11, 12
SU_FFE_H, SU_FFE_R, SU_FFE = 13, 14, 15
SU_FEE_BASE, SU_FEE, SU_USES_EX = 16, 17, 18
SU_SOFR_AVG, SU_RESERVE = 19, 20
SU_TOTAL, SU_COMMIT, SU_LOAN = 21, 22, 23
SU_COMP, SU_TIE = 24, 25
SU_SRC_LOAN, SU_EQUITY, SU_SOURCES = 27, 28, 29
SU_GP, SU_LP, SU_NONLAND, SU_GAP = 30, 31, 32, 33

SC_S, SC_SPREV, SC_W = 4, 5, 6
SC_LAND, SC_NONLAND, SC_LOAN, SC_SPEND = 7, 8, 9, 10

CS_STUDIO, CS_1BR, CS_2BR, CS_3BR, CS_PH = 4, 5, 6, 7, 8
CS_CLOSE, CS_UNIT_REV = 9, 10
CS_PARK_U, CS_STOR_U, CS_PARK_REV, CS_STOR_REV = 11, 12, 13, 14
CS_GROSS, CS_NET = 15, 16

HP_OP, HP_YEAR, HP_ADR, HP_OCC, HP_DAYS = 4, 5, 6, 7, 8
HP_ROOMS, HP_REV, HP_NOI = 9, 10, 11

RP_OP, RP_M, RP_ESC, RP_BASE, RP_RECOV = 4, 5, 6, 7, 8
RP_EGI, RP_OPEX, RP_MGMT, RP_NOI = 9, 10, 11, 12

CD_SOFR, CD_RATE, CD_SPEND = 4, 5, 6
CD_EQ_OPEN, CD_EQ_CONTRIB, CD_EQ_USED, CD_EQ_CLOSE = 7, 8, 9, 10
CD_DRAW_SPEND, CD_DEBT_OPEN, CD_INTEREST = 11, 12, 13
CD_DRAW_INT, CD_DRAWS, CD_BAL_AFTER = 14, 15, 16
CD_CONDO_NET, CD_CONDO_REPAY, CD_PERM_PAYOFF = 17, 18, 19
CD_REPAY, CD_DEBT_CLOSE = 20, 21
CD_INT_GAP, CD_ROLL_GAP = 23, 24

PD_ACTIVE, PD_OPEN, PD_INTEREST, PD_PMT = 4, 5, 6, 7
PD_PRIN, PD_PAYOFF, PD_DS = 8, 9, 10
PD_CT_PAYOFF, PD_CLOSE, PD_REFI = 11, 12, 13
PD_H_T12, PD_R_T12, PD_NOI = 30, 31, 32
PD_H_VAL, PD_R_VAL, PD_LTV = 33, 34, 35
PD_PMT_F, PD_DSCR, PD_DY, PD_GROSS = 36, 37, 38, 39

HV_NOI, HV_T12, HV_VALUE = 4, 6, 7
RV_NOI, RV_T12, RV_VALUE = 4, 6, 7

PC_CONDO_NET, PC_CONDO_REPAY, PC_CONDO_EQ = 4, 5, 6
PC_HOTEL, PC_RETAIL, PC_DS = 7, 8, 9
PC_REFI, PC_TERMINAL, PC_DIST = 10, 11, 12
PC_EQ, PC_T1, PC_T2, PC_T3, PC_T4, PC_RETAINED = 13, 14, 15, 16, 17, 18

WF_DIST, WF_UNRET_OPEN, WF_PREF_OPEN = 4, 5, 6
WF_ACCRUAL, WF_T1_NEED, WF_T1, WF_AFTER_T1 = 7, 8, 9, 10
WF_PREF_PAID, WF_CAP_PAID, WF_UNRET_CLOSE, WF_PREF_CLOSE = 11, 12, 13, 14
WF_T1_DONE, WF_PREF_CUM = 15, 16
WF_T2_TARGET, WF_T2_PRIOR, WF_T2_NEED, WF_T2, WF_T2_CUM, WF_T2_DONE = 17, 18, 19, 20, 21, 22
WF_LP_ACCRUED, WF_LP_BEFORE, WF_T3_GAP, WF_T3_NEED = 23, 24, 25, 26
WF_T4_ALREADY, WF_T3, WF_T3_LP, WF_T3_GP = 27, 28, 29, 30
WF_GATE_NOW, WF_T4_OPEN, WF_T4, WF_T4_LP, WF_T4_GP = 31, 32, 33, 34, 35
WF_TIER_SUM, WF_LP_DIST, WF_GP_DIST, WF_LP_CUM = 36, 37, 38, 39
WF_TIER_GAP, WF_T2_BAD, WF_T3_BAD, WF_T4_BAD = 40, 41, 42, 43

BLUE = Font(name="Calibri", color="0000FF")
BLACK = Font(name="Calibri", color="000000")
LABEL = Font(name="Calibri", color="000000", bold=True)
TITLE = Font(name="Calibri", color="000000", bold=True, size=14)
YELLOW = PatternFill("solid", fgColor="FFF2CC")
WRAP = Alignment(wrap_text=True, vertical="center")

FMT_USD = '$#,##0'
FMT_PCT = "0.00%"
FMT_INT = "0"
FMT_NUM = "0.00"
FMT_PSF = '$#,##0'
FMT_DATE = "MMM-YYYY"
FMT_GAP = "0.00"


def col(n: int) -> str:
    return get_column_letter(n)


def cref(t: int, row: int) -> str:
    return f"{col(t + 2)}{row}"


def pref(t: int, row: int) -> str:
    if t < 2:
        raise ValueError("no previous month")
    return f"{col(t + 1)}{row}"


def su(row: int) -> str:
    return f"SourcesUses!$C${row}"


def month_end(n: int) -> date:
    idx = n - 1
    year = 2026 + idx // 12
    month = idx % 12 + 1
    return date(year, month, calendar.monthrange(year, month)[1])


def sofr_placeholder(t: int) -> float:
    if t <= 24:
        return 0.043 + (0.036 - 0.043) * (t - 1) / 23.0
    return 0.036


def input_register() -> list[tuple[str, list[tuple]]]:
    return [
        ("Timeline", [
            ("CONSTR_MONTHS", 30, "months", FMT_INT, "Construction duration, months 1 through this month"),
            ("RETAIL_OPEN_M", 29, "month", FMT_INT, "First month of retail operations"),
            ("HOTEL_OPEN_M", 31, "month", FMT_INT, "First month of hotel operations"),
            ("FIRST_CLOSING_M", 33, "month", FMT_INT, "First condo closing month"),
            ("CLOSINGS_SPAN_M", 36, "months", FMT_INT, "Sellout length; last closing is first + span - 1"),
            ("PERM_CONV_M", 72, "month", FMT_INT, "Permanent loan conversion month"),
            ("EXIT_M", 84, "month", FMT_INT, "Terminal sale month; fixed at the last model column"),
        ]),
        ("Condo program", [
            ("UNITS_STUDIO", 36, "units", FMT_INT, "Studio inventory"),
            ("SQFT_STUDIO", 650, "SF", "#,##0", "Studio average size"),
            ("PPSF_STUDIO", 1600, "$/SF", FMT_PSF, "Studio contract price"),
            ("UNITS_1BR", 72, "units", FMT_INT, "One-bedroom inventory"),
            ("SQFT_1BR", 950, "SF", "#,##0", "One-bedroom average size"),
            ("PPSF_1BR", 1750, "$/SF", FMT_PSF, "One-bedroom contract price"),
            ("UNITS_2BR", 54, "units", FMT_INT, "Two-bedroom inventory"),
            ("SQFT_2BR", 1450, "SF", "#,##0", "Two-bedroom average size"),
            ("PPSF_2BR", 1900, "$/SF", FMT_PSF, "Two-bedroom contract price"),
            ("UNITS_3BR", 14, "units", FMT_INT, "Three-bedroom inventory"),
            ("SQFT_3BR", 2100, "SF", "#,##0", "Three-bedroom average size"),
            ("PPSF_3BR", 2200, "$/SF", FMT_PSF, "Three-bedroom contract price"),
            ("UNITS_PH", 4, "units", FMT_INT, "Penthouse inventory"),
            ("SQFT_PH", 3200, "SF", "#,##0", "Penthouse average size"),
            ("PPSF_PH", 2800, "$/SF", FMT_PSF, "Penthouse contract price"),
            ("PARKING_SPACES", 180, "spaces", FMT_INT, "Released pro-rata with unit closings"),
            ("PARKING_PRICE", 75000, "$", FMT_USD, "Price per space"),
            ("STORAGE_UNITS", 120, "units", FMT_INT, "Released pro-rata with unit closings"),
            ("STORAGE_PRICE", 15000, "$", FMT_USD, "Price per storage unit"),
            ("CLOSING_COST_PCT", 0.05, "% of gross", FMT_PCT, "Transfer taxes and brokers"),
            ("MARKETING_PCT", 0.015, "% of gross", FMT_PCT, "Marketing cost rate"),
        ]),
        ("Development budget", [
            ("LAND_COST", 85000000, "$", FMT_USD, "Land, funded at month 1"),
            ("ACQ_COST_PCT", 0.01, "% of land", FMT_PCT, "Acquisition costs"),
            ("RES_GSF", 240000, "SF", "#,##0", "Residential gross area"),
            ("HOTEL_GSF", 150000, "SF", "#,##0", "Hotel gross area"),
            ("RETAIL_GSF", 25000, "SF", "#,##0", "Retail gross area"),
            ("HC_PSF_RES", 700, "$/SF", FMT_PSF, "Residential hard-cost unit rate"),
            ("HC_PSF_HOTEL", 850, "$/SF", FMT_PSF, "Hotel hard-cost unit rate"),
            ("HC_PSF_RETAIL", 600, "$/SF", FMT_PSF, "Retail hard-cost unit rate"),
            ("CONTINGENCY_PCT", 0.04, "% of hard", FMT_PCT, "Contingency"),
            ("SOFTCOST_PCT", 0.12, "% of hard", FMT_PCT, "Soft costs"),
            ("HOTEL_KEYS", 200, "keys", FMT_INT, "Hotel keys"),
            ("FFE_PER_KEY", 45000, "$/key", FMT_USD, "Hotel FF&E"),
            ("FFE_PSF_RETAIL", 85, "$/SF", FMT_PSF, "Retail FF&E"),
            ("DEVFEE_PCT", 0.04, "% of fee base", FMT_PCT, "Fee base is land, acquisition, hard, contingency, soft, and FF&E"),
        ]),
        ("Construction debt", [
            ("LTC_PCT", 0.60, "% of uses", FMT_PCT, "Loan-to-cost, including the interest reserve"),
            ("CT_SPREAD_PCT", 0.0275, "annual", FMT_PCT, "Spread over SOFR"),
            ("SOFR_FLOOR_PCT", 0.0, "annual", FMT_PCT, "SOFR floor"),
            ("AVG_DRAWN_FRAC", 0.55, "fraction", FMT_NUM, "Average drawn fraction used only to size the interest reserve"),
            ("CT_COSTS_PCT", 0.0075, "% of commitment", FMT_PCT, "Construction loan closing costs"),
        ]),
        ("Permanent debt", [
            ("PERM_LTV", 0.55, "LTV cap", FMT_PCT, "Cap on hotel plus retail value at conversion"),
            ("PERM_DSCR", 1.40, "x", FMT_NUM, "DSCR cap on T12 NOI at conversion"),
            ("PERM_DY", 0.09, "debt yield", FMT_PCT, "Debt-yield cap on T12 NOI at conversion"),
            ("PERM_RATE_PCT", 0.0575, "annual", FMT_PCT, "Fixed rate from conversion"),
            ("PERM_AMORT_YRS", 30, "years", FMT_INT, "Amortization term"),
            ("PERM_COSTS_PCT", 0.005, "% of proceeds", FMT_PCT, "Permanent financing costs, at conversion, not in construction uses"),
        ]),
        ("Hotel operations", [
            ("ADR_Y1", 650, "$", FMT_USD, "Year-1 ADR"),
            ("ADR_GROWTH_PCT", 0.025, "per year", FMT_PCT, "ADR growth by operating year"),
            ("OCC_Y1", 0.65, "occupancy", FMT_PCT, "Operating year 1"),
            ("OCC_Y2", 0.75, "occupancy", FMT_PCT, "Operating year 2"),
            ("OCC_STAB", 0.82, "occupancy", FMT_PCT, "Operating year 3 and after"),
            ("FB_REV_PCT", 0.35, "% of rooms", FMT_PCT, "Food and beverage revenue"),
            ("OTHER_REV_PCT", 0.08, "% of rooms", FMT_PCT, "Other revenue"),
            ("HOTEL_UNDIST_PCT", 0.22, "% of revenue", FMT_PCT, "Undistributed expenses"),
            ("HOTEL_MGMT_PCT", 0.03, "% of revenue", FMT_PCT, "Management fee"),
            ("REPL_RESERVE_PCT", 0.035, "% of revenue", FMT_PCT, "Replacement reserve"),
            ("HOTEL_CAP", 0.0725, "cap rate", FMT_PCT, "Stabilization and exit cap rate"),
        ]),
        ("Retail operations", [
            ("RETAIL_BASE_PSF", 120, "$/SF", FMT_PSF, "Year-1 base rent"),
            ("RETAIL_ESC_PCT", 0.03, "per year", FMT_PCT, "Annual escalation from retail open"),
            ("RETAIL_RECOV_PSF", 18, "$/SF", FMT_PSF, "Recoverable pool"),
            ("RETAIL_RECOV_RATIO", 0.90, "ratio", FMT_PCT, "Recovery ratio"),
            ("RETAIL_VAC_PCT", 0.05, "% of base+recoveries", FMT_PCT, "Vacancy and credit loss"),
            ("RETAIL_OP_PSF", 9, "$/SF", FMT_PSF, "Non-recoverable opex, not escalated"),
            ("RETAIL_MGMT_PCT", 0.02, "% of EGI", FMT_PCT, "Management fee"),
            ("RETAIL_CAP", 0.0625, "cap rate", FMT_PCT, "Stabilization and exit cap rate"),
        ]),
        ("Exit and capital", [
            ("SELL_COST_PCT", 0.015, "% of value", FMT_PCT, "Cost of sale on hotel plus retail terminal value"),
            ("GP_EQUITY_PCT", 0.10, "% of equity", FMT_PCT, "GP co-invest share"),
            ("PREF_PCT", 0.08, "annual", FMT_PCT, "LP preferred return, monthly compounding"),
            ("CATCHUP_PCT", 0.20, "% of profits", FMT_PCT, "GP catch-up target"),
            ("T3_ACCRUAL_PCT", 0.15, "annual", FMT_PCT, "Tier-3 accrual gate, not an XIRR gate"),
            ("T3_LP_SPLIT", 0.70, "LP share", FMT_PCT, "LP share in tier 3"),
            ("T4_LP_SPLIT", 0.80, "LP share", FMT_PCT, "LP share in tier 4"),
        ]),
    ]


def inputs_dict() -> dict[str, float]:
    out = {}
    for _section, rows in input_register():
        for name, value, _unit, _fmt, _note in rows:
            out[name] = value
    return out


def simulate(p: dict[str, float]) -> dict[str, float]:
    """Mirror SPEC.md math. Raises if an identity the Checks sheet encodes would fail."""
    sofr = [sofr_placeholder(t) for t in range(1, MONTHS + 1)]
    constr = int(p["CONSTR_MONTHS"])
    sofr_avg = sum(sofr[:constr]) / constr
    land_acq = p["LAND_COST"] * (1 + p["ACQ_COST_PCT"])
    hard = (
        p["RES_GSF"] * p["HC_PSF_RES"]
        + p["HOTEL_GSF"] * p["HC_PSF_HOTEL"]
        + p["RETAIL_GSF"] * p["HC_PSF_RETAIL"]
    )
    conting = p["CONTINGENCY_PCT"] * hard
    soft = p["SOFTCOST_PCT"] * hard
    ffe = p["HOTEL_KEYS"] * p["FFE_PER_KEY"] + p["RETAIL_GSF"] * p["FFE_PSF_RETAIL"]
    fee_base = land_acq + hard + conting + soft + ffe
    fee = p["DEVFEE_PCT"] * fee_base
    uses_ex = fee_base + fee
    reserve = (
        p["LTC_PCT"]
        * uses_ex
        * ((sofr_avg + p["CT_SPREAD_PCT"]) / 12)
        * p["CONSTR_MONTHS"]
        * p["AVG_DRAWN_FRAC"]
    )
    total_uses = (uses_ex + reserve) / (1 - p["LTC_PCT"] * p["CT_COSTS_PCT"])
    commitment = p["LTC_PCT"] * total_uses
    loan_costs = p["CT_COSTS_PCT"] * commitment
    equity = total_uses - commitment
    nonland = hard + conting + soft + ffe + fee
    gp_eq = equity * p["GP_EQUITY_PCT"]
    lp_eq = equity * (1 - p["GP_EQUITY_PCT"])

    def s_cum(t: int) -> float:
        if t >= constr:
            return 1.0
        return (t / constr) ** 2.2

    weights = []
    spend = []
    for t in range(1, MONTHS + 1):
        prev = 0.0 if t <= 1 else s_cum(t - 1)
        w = s_cum(t) - prev
        weights.append(w)
        land_t = land_acq if t == 1 else 0.0
        loan_t = loan_costs if t == 1 else 0.0
        spend.append(land_t + nonland * w + loan_t)

    types = [
        ("STUDIO", p["UNITS_STUDIO"], p["SQFT_STUDIO"] * p["PPSF_STUDIO"]),
        ("1BR", p["UNITS_1BR"], p["SQFT_1BR"] * p["PPSF_1BR"]),
        ("2BR", p["UNITS_2BR"], p["SQFT_2BR"] * p["PPSF_2BR"]),
        ("3BR", p["UNITS_3BR"], p["SQFT_3BR"] * p["PPSF_3BR"]),
        ("PH", p["UNITS_PH"], p["SQFT_PH"] * p["PPSF_PH"]),
    ]
    total_units = sum(u for _n, u, _price in types)
    span = int(p["CLOSINGS_SPAN_M"])
    first = int(p["FIRST_CLOSING_M"])
    close_by_type = {name: [] for name, _u, _price in types}
    condo_net = []
    condo_gross = []
    for t in range(1, MONTHS + 1):
        closed = 0
        gross_units = 0.0
        for name, units, price in types:
            if first <= t < first + span:
                base = math.floor(units / span)
                rem = units - base * span
                k = t - first + 1
                n = base + (1 if k <= rem else 0)
            else:
                n = 0
            close_by_type[name].append(n)
            closed += n
            gross_units += n * price
        park = p["PARKING_SPACES"] * closed / total_units
        stor = p["STORAGE_UNITS"] * closed / total_units
        gross = gross_units + park * p["PARKING_PRICE"] + stor * p["STORAGE_PRICE"]
        net = gross * (1 - p["CLOSING_COST_PCT"] - p["MARKETING_PCT"])
        condo_gross.append(gross)
        condo_net.append(net)

    hotel_noi = []
    retail_noi = []
    hotel_open = int(p["HOTEL_OPEN_M"])
    retail_open = int(p["RETAIL_OPEN_M"])
    for t in range(1, MONTHS + 1):
        if t >= hotel_open:
            year = int((t - hotel_open) / 12) + 1
            adr = p["ADR_Y1"] * (1 + p["ADR_GROWTH_PCT"]) ** (year - 1)
            occ = p["OCC_Y1"] if year <= 1 else (p["OCC_Y2"] if year == 2 else p["OCC_STAB"])
            rooms = p["HOTEL_KEYS"] * month_end(t).day * occ * adr
            rev = rooms * (1 + p["FB_REV_PCT"] + p["OTHER_REV_PCT"])
            hotel_noi.append(rev * (1 - p["HOTEL_UNDIST_PCT"] - p["HOTEL_MGMT_PCT"] - p["REPL_RESERVE_PCT"]))
        else:
            hotel_noi.append(0.0)
        if t >= retail_open:
            m = t - retail_open
            factor = (1 + p["RETAIL_ESC_PCT"]) ** int(m / 12)
            base = p["RETAIL_BASE_PSF"] * factor * p["RETAIL_GSF"] / 12
            recov = p["RETAIL_RECOV_PSF"] * factor * p["RETAIL_GSF"] * p["RETAIL_RECOV_RATIO"] / 12
            egi = (base + recov) * (1 - p["RETAIL_VAC_PCT"])
            noi = egi - p["RETAIL_OP_PSF"] * p["RETAIL_GSF"] / 12 - p["RETAIL_MGMT_PCT"] * egi
            retail_noi.append(noi)
        else:
            retail_noi.append(0.0)

    conv = int(p["PERM_CONV_M"])
    exit_m = int(p["EXIT_M"])
    debt_open = 0.0
    eq_cash = 0.0
    max_bal = 0.0
    min_bal = 0.0
    cap_shortfall = 0.0
    ct_payoff_at_conv = 0.0
    interest_gap = 0.0
    roll_gap = 0.0
    contribs = 0.0
    for t in range(1, MONTHS + 1):
        rate = max(p["SOFR_FLOOR_PCT"], sofr[t - 1]) + p["CT_SPREAD_PCT"]
        interest = debt_open * rate / 12
        interest_gap = max(interest_gap, 0.0)
        contrib = equity if t == 1 else 0.0
        contribs += contrib
        available = eq_cash + contrib
        used = min(available, spend[t - 1])
        eq_cash = available - used
        draw_spend = spend[t - 1] - used
        draw_int = interest
        draws = draw_spend + draw_int
        bal_after = debt_open + draws
        condo_repay = min(bal_after, max(condo_net[t - 1], 0.0))
        perm_pay = max(0.0, bal_after - condo_repay) if t == conv else 0.0
        if t == conv:
            ct_payoff_at_conv = perm_pay
        repay = condo_repay + perm_pay
        debt_close = bal_after - repay
        if bal_after - draw_int > commitment + 1:
            cap_shortfall += 1
        max_bal = max(max_bal, debt_open, debt_close)
        min_bal = min(min_bal, debt_open, debt_close)
        nxt = debt_open + draws - repay
        roll_gap = max(roll_gap, abs(debt_close - nxt))
        debt_open = debt_close

    def t12(series: list[float], end: int) -> float:
        return sum(series[end - 12 : end])

    h_t12 = t12(hotel_noi, conv)
    r_t12 = t12(retail_noi, conv)
    noi_conv = h_t12 + r_t12
    h_val_c = h_t12 / p["HOTEL_CAP"]
    r_val_c = r_t12 / p["RETAIL_CAP"]
    ltv_size = p["PERM_LTV"] * (h_val_c + r_val_c)
    r = p["PERM_RATE_PCT"] / 12
    nper = int(p["PERM_AMORT_YRS"] * 12)
    pmt_factor = r * (1 + r) ** nper / ((1 + r) ** nper - 1)
    dscr_size = (noi_conv / p["PERM_DSCR"]) / pmt_factor
    dy_size = noi_conv / p["PERM_DY"]
    proceeds = min(ltv_size, dscr_size, dy_size)
    h_exit = t12(hotel_noi, exit_m) / p["HOTEL_CAP"]
    r_exit = t12(retail_noi, exit_m) / p["RETAIL_CAP"]

    perm_open = 0.0
    perm_ds = []
    perm_payoff = []
    refi = []
    for t in range(1, MONTHS + 1):
        if t < conv:
            opened = 0.0
        elif t == conv:
            opened = proceeds
        else:
            opened = perm_open
        interest = opened * p["PERM_RATE_PCT"] / 12
        pmt = 0.0
        if conv <= t < exit_m:
            pmt = proceeds * pmt_factor
        principal = 0.0 if pmt == 0 else pmt - interest
        payoff = opened if t == exit_m else 0.0
        perm_ds.append(interest + principal)
        perm_payoff.append(payoff)
        refi.append(proceeds * (1 - p["PERM_COSTS_PCT"]) - ct_payoff_at_conv if t == conv else 0.0)
        perm_open = opened - principal - payoff

    dist = []
    for t in range(1, MONTHS + 1):
        condo_eq = condo_net[t - 1] - min(condo_net[t - 1], max(condo_net[t - 1], 0))
        # condo equity is recomputed from the debt loop below; placeholder replaced next
        dist.append(0.0)
    # Rebuild condo-to-equity from the same debt rules so distributable matches the sheet.
    debt_open = 0.0
    eq_cash = 0.0
    condo_to_eq = []
    for t in range(1, MONTHS + 1):
        rate = max(p["SOFR_FLOOR_PCT"], sofr[t - 1]) + p["CT_SPREAD_PCT"]
        interest = debt_open * rate / 12
        contrib = equity if t == 1 else 0.0
        available = eq_cash + contrib
        used = min(available, spend[t - 1])
        eq_cash = available - used
        draw_spend = spend[t - 1] - used
        bal_after = debt_open + draw_spend + interest
        condo_repay = min(bal_after, max(condo_net[t - 1], 0.0))
        condo_to_eq.append(condo_net[t - 1] - condo_repay)
        perm_pay = max(0.0, bal_after - condo_repay) if t == conv else 0.0
        debt_open = bal_after - condo_repay - perm_pay
    for t in range(1, MONTHS + 1):
        terminal = 0.0
        if t == exit_m:
            terminal = (h_exit + r_exit) * (1 - p["SELL_COST_PCT"]) - perm_payoff[t - 1]
        dist[t - 1] = (
            condo_to_eq[t - 1]
            + hotel_noi[t - 1]
            + retail_noi[t - 1]
            - perm_ds[t - 1]
            + refi[t - 1]
            + terminal
        )

    unret = lp_eq
    pref_unpaid = 0.0
    pref_cum = 0.0
    t2_cum = 0.0
    lp_cum = 0.0
    t4_open = False
    tier_gap = 0.0
    t2_bad = t3_bad = t4_bad = 0
    min_dist = min(dist)
    for t in range(1, MONTHS + 1):
        cash = dist[t - 1]
        accrual = (unret + pref_unpaid) * p["PREF_PCT"] / 12
        need = unret + pref_unpaid + accrual
        t1 = cash if cash < 0 else min(max(cash, 0.0), max(need, 0.0))
        pref_paid = min(max(t1, 0.0), pref_unpaid + accrual)
        cap_paid = max(t1, 0.0) - pref_paid
        unret_close = unret - cap_paid
        pref_close = pref_unpaid + accrual - pref_paid
        t1_done = (need - max(t1, 0.0)) <= 0.01
        pref_cum += pref_paid
        t2_target = (p["CATCHUP_PCT"] / (1 - p["CATCHUP_PCT"]) * pref_cum) if t1_done else 0.0
        t2_need = max(0.0, t2_target - t2_cum)
        after_t1 = cash - t1
        t2 = min(max(after_t1, 0.0), t2_need) if t1_done else 0.0
        t2_cum += t2
        t2_done = t1_done and (t2_target - t2_cum) <= 0.01
        accrued = lp_eq * (1 + p["T3_ACCRUAL_PCT"] / 12) ** t
        lp_before = lp_cum + t1
        gap = max(0.0, accrued - lp_before)
        t3_need = 0.0 if p["T3_LP_SPLIT"] <= 0 else gap / p["T3_LP_SPLIT"]
        if t4_open:
            t3 = 0.0
        elif t2_done and gap > 0.01:
            t3 = min(max(after_t1 - t2, 0.0), t3_need)
        else:
            t3 = 0.0
        t3_lp = t3 * p["T3_LP_SPLIT"]
        gate_now = t2_done and (lp_before + t3_lp + 0.01 >= accrued)
        t4_open = t4_open or gate_now
        t4 = cash - t1 - t2 - t3
        if t2 > 0.01 and (need - max(t1, 0.0)) > 0.01:
            t2_bad += 1
        if t3 > 0.01 and not t2_done:
            t3_bad += 1
        if abs(t4) > 0.01 and not t4_open:
            t4_bad += 1
        tier_gap = max(tier_gap, abs(t1 + t2 + t3 + t4 - cash))
        unret = unret_close
        pref_unpaid = pref_close
        lp_cum += t1 + t3_lp + (t4 * p["T4_LP_SPLIT"] if t4_open or abs(t4) <= 0.01 else 0.0)

    gross_target = (
        sum(u * price for _n, u, price in types)
        + p["PARKING_SPACES"] * p["PARKING_PRICE"]
        + p["STORAGE_UNITS"] * p["STORAGE_PRICE"]
    )
    problems = []
    if abs((commitment + equity) - total_uses) > 1:
        problems.append("C1")
    if abs((uses_ex + reserve + loan_costs) - total_uses) > 1:
        problems.append("uses tie")
    if abs(sum(weights) - 1) > 1e-9:
        problems.append("weights")
    if interest_gap > 0.01:
        problems.append("C2")
    if min_bal < -1 or max_bal > commitment + 1:
        problems.append(f"C3 min={min_bal:.2f} max={max_bal:.2f} commit={commitment:.2f}")
    if abs(proceeds - min(ltv_size, dscr_size, dy_size)) > 1:
        problems.append("C4")
    for name, units, _price in types:
        if abs(sum(close_by_type[name]) - units) > 1:
            problems.append(f"C5 {name}")
    if abs(sum(condo_gross) - gross_target) > 1:
        problems.append("C5 gross")
    if abs(h_exit - t12(hotel_noi, exit_m) / p["HOTEL_CAP"]) > 1:
        problems.append("C6 hotel")
    if tier_gap > 0.01:
        problems.append(f"C7 gap={tier_gap}")
    if t2_bad or t3_bad or t4_bad:
        problems.append(f"C8 t2={t2_bad} t3={t3_bad} t4={t4_bad}")
    if abs(contribs - equity) > 1:
        problems.append("C9")
    if roll_gap > 0.01:
        problems.append("C10")
    if cap_shortfall:
        problems.append("interest cap would bind")
    if problems:
        raise SystemExit("simulation identities failed: " + ", ".join(problems))
    return {
        "total_uses": total_uses,
        "commitment": commitment,
        "equity": equity,
        "lp_equity": lp_eq,
        "gp_equity": gp_eq,
        "reserve": reserve,
        "loan_costs": loan_costs,
        "max_balance": max_bal,
        "min_balance": min_bal,
        "condo_gross": sum(condo_gross),
        "hotel_value_exit": h_exit,
        "retail_value_exit": r_exit,
        "perm_proceeds": proceeds,
        "ltv_size": ltv_size,
        "dscr_size": dscr_size,
        "dy_size": dy_size,
        "min_dist": min_dist,
        "tier_gap": tier_gap,
        "ct_payoff_at_conv": ct_payoff_at_conv,
    }


def write_title(ws, text: str) -> None:
    ws["A1"] = text
    ws["A1"].font = TITLE
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 22
    ws.row_dimensions[1].height = 22
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_setup.paperSize = ws.PAPERSIZE_TABLOID
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.horizontalCentered = True
    ws.sheet_view.view = "pageBreakPreview"
    ws.sheet_view.zoomScale = 80
    ws.oddHeader.left.text = "Elite Luxury Mixed-Use  |  Illustrative template"
    ws.oddFooter.left.text = "Not a live deal  |  Not an offering  |  Not investment advice"
    ws.oddFooter.right.text = "Page &P of &N"


def write_month_axis(ws) -> None:
    write_title(ws, ws.title)
    ws["A2"] = "Month"
    ws["A3"] = "Date"
    ws["A2"].font = LABEL
    ws["A3"].font = LABEL
    ws["B2"] = "index"
    ws["B3"] = "month-end"
    for t in range(1, MONTHS + 1):
        c = col(t + 2)
        month_cell = ws.cell(2, t + 2, "=COLUMN()-2")
        date_cell = ws.cell(3, t + 2, f"=EOMONTH(DATE(2026,1,1),{c}2-1)")
        month_cell.font = LABEL
        month_cell.number_format = FMT_INT
        date_cell.font = BLACK
        date_cell.number_format = FMT_DATE
        ws.column_dimensions[c].width = 13
    ws.freeze_panes = "C4"
    ws.auto_filter.ref = f"A2:{col(LAST_COL)}2"
    ws.page_setup.scale = 55
    ws.print_title_rows = "1:3"
    ws.print_title_cols = "A:B"
    ws.page_setup.horizontalCentered = True
    ws.sheet_view.zoomScale = 80
    ws.oddHeader.center.text = ws.title


def write_label(ws, row: int, label: str, unit: str) -> None:
    ws.cell(row, 1, label).font = LABEL
    ws.cell(row, 2, unit).font = BLACK


def fill_months(ws, row: int, formula_for_t, fmt: str) -> None:
    for t in range(1, MONTHS + 1):
        cell = ws.cell(row, t + 2, formula_for_t(t))
        cell.font = BLACK
        cell.number_format = fmt


def monthly(ws, row: int, label: str, unit: str, formula_for_t, fmt: str) -> None:
    write_label(ws, row, label, unit)
    fill_months(ws, row, formula_for_t, fmt)


def scalar(ws, row: int, label: str, unit: str, formula: str, fmt: str) -> None:
    write_label(ws, row, label, unit)
    cell = ws.cell(row, 3, formula)
    cell.font = BLACK
    cell.number_format = fmt


def build() -> dict[str, float]:
    summary = simulate(inputs_dict())
    wb = Workbook()
    wb.calculation = CalcProperties(calcMode="auto", fullCalcOnLoad=True, forceFullCalc=True)
    cover = wb.active
    cover.title = "Cover"
    for name in SHEETS[1:]:
        wb.create_sheet(name)

    write_cover(wb["Cover"])
    name_rows = write_assumptions(wb["Assumptions"])
    for name, row in name_rows.items():
        wb.defined_names.add(DefinedName(name=name, attr_text=f"Assumptions!$C${row}"))
    write_sofr(wb["SOFR"])
    write_sources(wb["SourcesUses"])
    write_spend(wb["SpendCurve"])
    write_condo(wb["CondoSellout"])
    write_retail(wb["RetailProForma"])
    write_hotel(wb["HotelProForma"])
    write_construction(wb["ConstructionDebt"])
    write_permanent(wb["PermanentDebt"])
    write_valuation(wb["HotelValuation"], "HotelProForma", HP_NOI, "HOTEL_CAP", "Hotel")
    write_valuation(wb["RetailValuation"], "RetailProForma", RP_NOI, "RETAIL_CAP", "Retail")
    write_project(wb["ProjectCF"])
    write_waterfall(wb["Waterfall"])
    write_returns(wb["Returns"])
    write_checks(wb["Checks"])

    for ws in wb.worksheets:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_TABLOID
        ws.page_setup.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.horizontalCentered = True
        ws.sheet_view.view = "pageBreakPreview"
        ws.sheet_view.zoomScale = 80
        ws.page_margins.left = 0.4
        ws.page_margins.right = 0.4
        ws.page_margins.top = 0.6
        ws.page_margins.bottom = 0.5
        ws.page_margins.header = 0.25
        ws.page_margins.footer = 0.25
        ws.oddHeader.left.text = "Elite Luxury Mixed-Use  |  Illustrative template"
        ws.oddFooter.left.text = "Not a live deal  |  Not an offering  |  Not investment advice"
        ws.oddFooter.right.text = "Page &P of &N"
        ws.sheet_properties.tabColor = "1F4E79"
    wb["Cover"].sheet_view.zoomScale = 120
    wb["Assumptions"].sheet_view.zoomScale = 110
    wb["Checks"].sheet_view.zoomScale = 110

    wb.active = 0
    wb.save(OUT)
    audit(OUT, set(name_rows))
    return summary


def write_cover(ws) -> None:
    write_title(ws, "Elite Luxury Mixed-Use Development Model")
    ws["A3"] = DISCLAIMER
    ws["A3"].alignment = WRAP
    ws["A3"].font = LABEL
    ws.row_dimensions[3].height = 48
    ws["A5"] = "Sheets"
    ws["A5"].font = LABEL
    for i, name in enumerate(SHEETS):
        ws.cell(6 + i, 1, name).font = BLACK
        ws.cell(6 + i, 2, "input" if name in ("Assumptions", "SOFR") else "formula").font = BLACK
    ws["A23"] = "Blue font marks an input. Every other amount is an Excel formula."
    ws["A24"] = "Condo economics are sellout revenue net of costs. No cap rate is applied to condos."
    ws["A25"] = "XIRR on Returns is an output. It is not a waterfall distribution trigger."
    ws.column_dimensions["A"].width = 120


def write_assumptions(ws) -> dict[str, int]:
    write_title(ws, "Assumptions")
    ws["A2"] = "Name"
    ws["B2"] = "Unit"
    ws["C2"] = "Value"
    ws["D2"] = "Note"
    for col_idx in range(1, 5):
        ws.cell(2, col_idx).font = LABEL
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 78
    ws.row_dimensions[2].height = 18
    ws.auto_filter.ref = "A2:D90"
    ws.freeze_panes = "A3"
    ws.auto_filter.ref = "A2:D90"
    ws.oddHeader.center.text = "Assumptions — blue cells are the only inputs"
    rows: dict[str, int] = {}
    row = 3
    for section, items in input_register():
        ws.cell(row, 1, section).font = TITLE
        row += 1
        for name, value, unit, fmt, note in items:
            ws.cell(row, 1, name).font = LABEL
            ws.cell(row, 2, unit).font = BLACK
            cell = ws.cell(row, 3, value)
            cell.font = BLUE
            cell.fill = YELLOW
            cell.number_format = fmt
            ws.cell(row, 4, note).font = BLACK
            rows[name] = row
            row += 1
        row += 1
    ws.auto_filter.ref = f"A2:D{row - 1}"
    return rows


def write_sofr(ws) -> None:
    write_title(ws, "SOFR")
    ws["A2"] = "Month"
    ws["B2"] = "Date"
    ws["C2"] = "SOFR_Fwd"
    ws["D2"] = "Source"
    for col_idx in range(1, 5):
        ws.cell(2, col_idx).font = LABEL
    ws["E2"] = "Paste target. Placeholder path is 4.30% at month 1 gliding linearly to 3.60% at month 24, then flat. Not a live quote."
    ws["E2"].font = BLACK
    for t in range(1, MONTHS + 1):
        r = t + 1
        ws.cell(r, 1, f"=ROW()-1").font = BLACK
        ws.cell(r, 1).number_format = FMT_INT
        ws.cell(r, 2, f"=EOMONTH(DATE(2026,1,1),A{r}-1)").font = BLACK
        ws.cell(r, 2).number_format = FMT_DATE
        rate = ws.cell(r, 3, sofr_placeholder(t))
        rate.font = BLUE
        rate.fill = YELLOW
        rate.number_format = FMT_PCT
        ws.cell(r, 4, SOURCE_LABEL).font = BLACK
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 92
    ws.column_dimensions["E"].width = 42
    ws.freeze_panes = "A3"
    ws.auto_filter.ref = f"A2:D{MONTHS + 1}"
    ws.auto_filter.ref = "A2:D86"
    ws.oddHeader.center.text = "SOFR forwards — paste target, not a live quote"


def write_sources(ws) -> None:
    write_title(ws, "SourcesUses")
    ws["A2"] = "Line"
    ws["B2"] = "Unit"
    ws["C2"] = "Amount"
    ws["D2"] = "Definition"
    for col_idx in range(1, 5):
        ws.cell(2, col_idx).font = LABEL
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["D"].width = 88
    lines = [
        (SU_LAND, "Land", "$", "=LAND_COST", FMT_USD, "Named input"),
        (SU_ACQ, "Acquisition costs", "$", "=LAND_COST*ACQ_COST_PCT", FMT_USD, "Land times acquisition rate"),
        (SU_LAND_ACQ, "Land and acquisition", "$", f"=C{SU_LAND}+C{SU_ACQ}", FMT_USD, "Funded at month 1"),
        (SU_HARD_RES, "Hard costs residential", "$", "=RES_GSF*HC_PSF_RES", FMT_USD, "Area times unit rate"),
        (SU_HARD_HOTEL, "Hard costs hotel", "$", "=HOTEL_GSF*HC_PSF_HOTEL", FMT_USD, "Area times unit rate"),
        (SU_HARD_RETAIL, "Hard costs retail", "$", "=RETAIL_GSF*HC_PSF_RETAIL", FMT_USD, "Area times unit rate"),
        (SU_HARD, "Hard costs", "$", f"=C{SU_HARD_RES}+C{SU_HARD_HOTEL}+C{SU_HARD_RETAIL}", FMT_USD, "Sum of hard-cost lines"),
        (SU_CONTING, "Contingency", "$", f"=CONTINGENCY_PCT*C{SU_HARD}", FMT_USD, "Percent of hard costs"),
        (SU_SOFT, "Soft costs", "$", f"=SOFTCOST_PCT*C{SU_HARD}", FMT_USD, "Percent of hard costs"),
        (SU_FFE_H, "FF&E hotel", "$", "=HOTEL_KEYS*FFE_PER_KEY", FMT_USD, "Keys times allowance"),
        (SU_FFE_R, "FF&E retail", "$", "=RETAIL_GSF*FFE_PSF_RETAIL", FMT_USD, "Area times allowance"),
        (SU_FFE, "FF&E", "$", f"=C{SU_FFE_H}+C{SU_FFE_R}", FMT_USD, "Hotel plus retail"),
        (SU_FEE_BASE, "Developer fee base", "$", f"=C{SU_LAND_ACQ}+C{SU_HARD}+C{SU_CONTING}+C{SU_SOFT}+C{SU_FFE}", FMT_USD, "Land, acquisition, hard, contingency, soft, FF&E"),
        (SU_FEE, "Developer fee", "$", f"=DEVFEE_PCT*C{SU_FEE_BASE}", FMT_USD, "Percent of fee base"),
        (SU_USES_EX, "Uses excluding interest", "$", f"=C{SU_FEE_BASE}+C{SU_FEE}", FMT_USD, "Fee base plus developer fee"),
        (SU_SOFR_AVG, "Average SOFR during construction", "%", f"=AVERAGE(SOFR!$C$2:INDEX(SOFR!$C$2:$C$85,CONSTR_MONTHS))", FMT_PCT, "Arithmetic average of the paste-target forwards"),
        (SU_RESERVE, "Interest reserve", "$", f"=LTC_PCT*C{SU_USES_EX}*((C{SU_SOFR_AVG}+CT_SPREAD_PCT)/12)*CONSTR_MONTHS*AVG_DRAWN_FRAC", FMT_USD, "Linear estimate. No circular interest calculation."),
        (SU_TOTAL, "Total uses", "$", f"=(C{SU_USES_EX}+C{SU_RESERVE})/(1-LTC_PCT*CT_COSTS_PCT)", FMT_USD, "Closed form so commitment = LTC% x total uses, with loan costs inside uses."),
        (SU_COMMIT, "Construction commitment", "$", f"=LTC_PCT*C{SU_TOTAL}", FMT_USD, "LTC times total uses, including the interest reserve"),
        (SU_LOAN, "Construction loan costs", "$", f"=CT_COSTS_PCT*C{SU_COMMIT}", FMT_USD, "Percent of commitment. Permanent financing costs are not here."),
        (SU_COMP, "Uses component sum", "$", f"=C{SU_USES_EX}+C{SU_RESERVE}+C{SU_LOAN}", FMT_USD, "Ex-interest plus reserve plus loan costs"),
        (SU_TIE, "Uses tie-out", "$", f"=C{SU_COMP}-C{SU_TOTAL}", FMT_GAP, "Must be zero"),
        (SU_SRC_LOAN, "Source: construction loan", "$", f"=C{SU_COMMIT}", FMT_USD, "Commitment"),
        (SU_EQUITY, "Source: equity", "$", f"=C{SU_TOTAL}-C{SU_COMMIT}", FMT_USD, "Total uses minus commitment. Contributed at month 1."),
        (SU_SOURCES, "Total sources", "$", f"=C{SU_SRC_LOAN}+C{SU_EQUITY}", FMT_USD, "Loan plus equity"),
        (SU_GP, "GP equity", "$", f"=C{SU_EQUITY}*GP_EQUITY_PCT", FMT_USD, "Co-invest share"),
        (SU_LP, "LP equity", "$", f"=C{SU_EQUITY}*(1-GP_EQUITY_PCT)", FMT_USD, "Remainder of equity"),
        (SU_NONLAND, "Non-land uses on the spend curve", "$", f"=C{SU_HARD}+C{SU_CONTING}+C{SU_SOFT}+C{SU_FFE}+C{SU_FEE}", FMT_USD, "Hard, contingency, soft, FF&E, and fee"),
        (SU_GAP, "Sources minus uses", "$", f"=C{SU_SOURCES}-C{SU_TOTAL}", FMT_GAP, "Must be zero"),
    ]
    for row, label, unit, formula, fmt, note in lines:
        scalar(ws, row, label, unit, formula, fmt)
        ws.cell(row, 4, note).font = BLACK
    ws["A26"] = "Sources"
    ws["A26"].font = TITLE
    ws.freeze_panes = "A3"


def write_spend(ws) -> None:
    write_month_axis(ws)
    monthly(ws, SC_S, "Cumulative spend fraction S(t)", "fraction", lambda t: f"=IF({cref(t, 2)}>=CONSTR_MONTHS,1,({cref(t, 2)}/CONSTR_MONTHS)^2.2)", FMT_NUM)
    monthly(ws, SC_SPREV, "Prior cumulative fraction", "fraction", lambda t: "=0" if t == 1 else f"=IF({cref(t, 2)}-1>=CONSTR_MONTHS,1,(({cref(t, 2)}-1)/CONSTR_MONTHS)^2.2)", FMT_NUM)
    monthly(ws, SC_W, "Monthly weight", "fraction", lambda t: f"={cref(t, SC_S)}-{cref(t, SC_SPREV)}", FMT_NUM)
    monthly(ws, SC_LAND, "Land and acquisition", "$", lambda t: f"=IF({cref(t, 2)}=1,{su(SU_LAND_ACQ)},0)", FMT_USD)
    monthly(ws, SC_NONLAND, "Non-land uses", "$", lambda t: f"={su(SU_NONLAND)}*{cref(t, SC_W)}", FMT_USD)
    monthly(ws, SC_LOAN, "Construction loan costs", "$", lambda t: f"=IF({cref(t, 2)}=1,{su(SU_LOAN)},0)", FMT_USD)
    monthly(ws, SC_SPEND, "Budget spend", "$", lambda t: f"={cref(t, SC_LAND)}+{cref(t, SC_NONLAND)}+{cref(t, SC_LOAN)}", FMT_USD)
    ws["D1"] = "Land and loan costs at month 1. Other non-interest uses follow S(t)=(t/CONSTR_MONTHS)^2.2."
    ws["D1"].font = BLACK


def closing_formula(t: int, units_name: str) -> str:
    month = cref(t, 2)
    return (
        f'=IF(AND({month}>=FIRST_CLOSING_M,{month}<FIRST_CLOSING_M+CLOSINGS_SPAN_M),'
        f'ROUNDDOWN({units_name}/CLOSINGS_SPAN_M,0)+IF({month}-FIRST_CLOSING_M+1<={units_name}-ROUNDDOWN({units_name}/CLOSINGS_SPAN_M,0)*CLOSINGS_SPAN_M,1,0),0)'
    )


def write_condo(ws) -> None:
    write_month_axis(ws)
    pairs = [
        (CS_STUDIO, "Studio closings", "UNITS_STUDIO"),
        (CS_1BR, "One-bedroom closings", "UNITS_1BR"),
        (CS_2BR, "Two-bedroom closings", "UNITS_2BR"),
        (CS_3BR, "Three-bedroom closings", "UNITS_3BR"),
        (CS_PH, "Penthouse closings", "UNITS_PH"),
    ]
    for row, label, name in pairs:
        monthly(ws, row, label, "units", lambda t, name=name: closing_formula(t, name), FMT_INT)
    monthly(ws, CS_CLOSE, "Total unit closings", "units", lambda t: f"={cref(t, CS_STUDIO)}+{cref(t, CS_1BR)}+{cref(t, CS_2BR)}+{cref(t, CS_3BR)}+{cref(t, CS_PH)}", FMT_INT)
    monthly(
        ws,
        CS_UNIT_REV,
        "Unit revenue",
        "$",
        lambda t: (
            f"={cref(t, CS_STUDIO)}*SQFT_STUDIO*PPSF_STUDIO+{cref(t, CS_1BR)}*SQFT_1BR*PPSF_1BR+"
            f"{cref(t, CS_2BR)}*SQFT_2BR*PPSF_2BR+{cref(t, CS_3BR)}*SQFT_3BR*PPSF_3BR+{cref(t, CS_PH)}*SQFT_PH*PPSF_PH"
        ),
        FMT_USD,
    )
    denom = "(UNITS_STUDIO+UNITS_1BR+UNITS_2BR+UNITS_3BR+UNITS_PH)"
    monthly(ws, CS_PARK_U, "Parking spaces released", "spaces", lambda t: f"=PARKING_SPACES*{cref(t, CS_CLOSE)}/{denom}", FMT_NUM)
    monthly(ws, CS_STOR_U, "Storage units released", "units", lambda t: f"=STORAGE_UNITS*{cref(t, CS_CLOSE)}/{denom}", FMT_NUM)
    monthly(ws, CS_PARK_REV, "Parking revenue", "$", lambda t: f"={cref(t, CS_PARK_U)}*PARKING_PRICE", FMT_USD)
    monthly(ws, CS_STOR_REV, "Storage revenue", "$", lambda t: f"={cref(t, CS_STOR_U)}*STORAGE_PRICE", FMT_USD)
    monthly(ws, CS_GROSS, "Gross revenue", "$", lambda t: f"={cref(t, CS_UNIT_REV)}+{cref(t, CS_PARK_REV)}+{cref(t, CS_STOR_REV)}", FMT_USD)
    monthly(ws, CS_NET, "Net revenue", "$", lambda t: f"={cref(t, CS_GROSS)}*(1-CLOSING_COST_PCT-MARKETING_PCT)", FMT_USD)


def write_hotel(ws) -> None:
    write_month_axis(ws)
    monthly(ws, HP_OP, "Operating", "1/0", lambda t: f"=IF({cref(t, 2)}>=HOTEL_OPEN_M,1,0)", FMT_INT)
    monthly(ws, HP_YEAR, "Operating year", "year", lambda t: f"=IF({cref(t, HP_OP)}=1,INT(({cref(t, 2)}-HOTEL_OPEN_M)/12)+1,0)", FMT_INT)
    monthly(ws, HP_ADR, "ADR", "$", lambda t: f"=IF({cref(t, HP_OP)}=1,ADR_Y1*(1+ADR_GROWTH_PCT)^({cref(t, HP_YEAR)}-1),0)", FMT_USD)
    monthly(ws, HP_OCC, "Occupancy", "%", lambda t: f"=IF({cref(t, HP_OP)}=1,IF({cref(t, HP_YEAR)}<=1,OCC_Y1,IF({cref(t, HP_YEAR)}=2,OCC_Y2,OCC_STAB)),0)", FMT_PCT)
    monthly(ws, HP_DAYS, "Days", "days", lambda t: f"=IF({cref(t, HP_OP)}=1,DAY({cref(t, 3)}),0)", FMT_INT)
    monthly(ws, HP_ROOMS, "Rooms revenue", "$", lambda t: f"=IF({cref(t, HP_OP)}=1,HOTEL_KEYS*{cref(t, HP_DAYS)}*{cref(t, HP_OCC)}*{cref(t, HP_ADR)},0)", FMT_USD)
    monthly(ws, HP_REV, "Total revenue", "$", lambda t: f"={cref(t, HP_ROOMS)}*(1+FB_REV_PCT+OTHER_REV_PCT)", FMT_USD)
    monthly(ws, HP_NOI, "Hotel NOI", "$", lambda t: f"={cref(t, HP_REV)}*(1-HOTEL_UNDIST_PCT-HOTEL_MGMT_PCT-REPL_RESERVE_PCT)", FMT_USD)


def write_retail(ws) -> None:
    write_month_axis(ws)
    monthly(ws, RP_OP, "Operating", "1/0", lambda t: f"=IF({cref(t, 2)}>=RETAIL_OPEN_M,1,0)", FMT_INT)
    monthly(ws, RP_M, "Months from open", "months", lambda t: f"=IF({cref(t, RP_OP)}=1,{cref(t, 2)}-RETAIL_OPEN_M,0)", FMT_INT)
    monthly(ws, RP_ESC, "Escalation year index", "year", lambda t: f"=IF({cref(t, RP_OP)}=1,INT({cref(t, RP_M)}/12),0)", FMT_INT)
    monthly(ws, RP_BASE, "Base rent", "$", lambda t: f"=IF({cref(t, RP_OP)}=1,RETAIL_BASE_PSF*(1+RETAIL_ESC_PCT)^{cref(t, RP_ESC)}*RETAIL_GSF/12,0)", FMT_USD)
    monthly(ws, RP_RECOV, "Recovery income", "$", lambda t: f"=IF({cref(t, RP_OP)}=1,RETAIL_RECOV_PSF*(1+RETAIL_ESC_PCT)^{cref(t, RP_ESC)}*RETAIL_GSF*RETAIL_RECOV_RATIO/12,0)", FMT_USD)
    monthly(ws, RP_EGI, "EGI", "$", lambda t: f"=IF({cref(t, RP_OP)}=1,({cref(t, RP_BASE)}+{cref(t, RP_RECOV)})*(1-RETAIL_VAC_PCT),0)", FMT_USD)
    monthly(ws, RP_OPEX, "Non-recoverable opex", "$", lambda t: f"=IF({cref(t, RP_OP)}=1,RETAIL_OP_PSF*RETAIL_GSF/12,0)", FMT_USD)
    monthly(ws, RP_MGMT, "Management fee", "$", lambda t: f"=RETAIL_MGMT_PCT*{cref(t, RP_EGI)}", FMT_USD)
    monthly(ws, RP_NOI, "Retail NOI", "$", lambda t: f"={cref(t, RP_EGI)}-{cref(t, RP_OPEX)}-{cref(t, RP_MGMT)}", FMT_USD)


def write_construction(ws) -> None:
    write_month_axis(ws)
    monthly(ws, CD_SOFR, "SOFR forward", "%", lambda t: f"=INDEX(SOFR!$C$2:$C$85,{cref(t, 2)})", FMT_PCT)
    monthly(ws, CD_RATE, "All-in rate", "%", lambda t: f"=MAX(SOFR_FLOOR_PCT,{cref(t, CD_SOFR)})+CT_SPREAD_PCT", FMT_PCT)
    monthly(ws, CD_SPEND, "Budget spend", "$", lambda t: f"=SpendCurve!{cref(t, SC_SPEND)}", FMT_USD)
    monthly(ws, CD_EQ_OPEN, "Equity cash opening", "$", lambda t: "=0" if t == 1 else f"={pref(t, CD_EQ_CLOSE)}", FMT_USD)
    monthly(ws, CD_EQ_CONTRIB, "Equity contribution", "$", lambda t: f"=IF({cref(t, 2)}=1,{su(SU_EQUITY)},0)", FMT_USD)
    monthly(ws, CD_EQ_USED, "Equity used", "$", lambda t: f"=MIN({cref(t, CD_EQ_OPEN)}+{cref(t, CD_EQ_CONTRIB)},{cref(t, CD_SPEND)})", FMT_USD)
    monthly(ws, CD_EQ_CLOSE, "Equity cash closing", "$", lambda t: f"={cref(t, CD_EQ_OPEN)}+{cref(t, CD_EQ_CONTRIB)}-{cref(t, CD_EQ_USED)}", FMT_USD)
    monthly(ws, CD_DRAW_SPEND, "Draws for spend", "$", lambda t: f"={cref(t, CD_SPEND)}-{cref(t, CD_EQ_USED)}", FMT_USD)
    monthly(ws, CD_DEBT_OPEN, "Debt opening balance", "$", lambda t: "=0" if t == 1 else f"={pref(t, CD_DEBT_CLOSE)}", FMT_USD)
    monthly(
        ws,
        CD_INTEREST,
        "Interest on opening balance",
        "$",
        lambda t: f"={cref(t, CD_DEBT_OPEN)}*(MAX(SOFR_FLOOR_PCT,INDEX(SOFR!$C$2:$C$85,{cref(t, 2)}))+CT_SPREAD_PCT)/12",
        FMT_USD,
    )
    monthly(ws, CD_DRAW_INT, "Capitalized interest draw", "$", lambda t: f"={cref(t, CD_INTEREST)}", FMT_USD)
    monthly(ws, CD_DRAWS, "Total draws", "$", lambda t: f"={cref(t, CD_DRAW_SPEND)}+{cref(t, CD_DRAW_INT)}", FMT_USD)
    monthly(ws, CD_BAL_AFTER, "Balance after draws", "$", lambda t: f"={cref(t, CD_DEBT_OPEN)}+{cref(t, CD_DRAWS)}", FMT_USD)
    monthly(ws, CD_CONDO_NET, "Condo net revenue", "$", lambda t: f"=CondoSellout!{cref(t, CS_NET)}", FMT_USD)
    monthly(ws, CD_CONDO_REPAY, "Condo repayment", "$", lambda t: f"=MIN({cref(t, CD_BAL_AFTER)},MAX({cref(t, CD_CONDO_NET)},0))", FMT_USD)
    monthly(ws, CD_PERM_PAYOFF, "Permanent-loan payoff of construction balance", "$", lambda t: f"=IF({cref(t, 2)}=PERM_CONV_M,MAX(0,{cref(t, CD_BAL_AFTER)}-{cref(t, CD_CONDO_REPAY)}),0)", FMT_USD)
    monthly(ws, CD_REPAY, "Total repayments", "$", lambda t: f"={cref(t, CD_CONDO_REPAY)}+{cref(t, CD_PERM_PAYOFF)}", FMT_USD)
    monthly(ws, CD_DEBT_CLOSE, "Debt closing balance", "$", lambda t: f"={cref(t, CD_DEBT_OPEN)}+{cref(t, CD_DRAWS)}-{cref(t, CD_REPAY)}", FMT_USD)
    monthly(
        ws,
        CD_INT_GAP,
        "Audit interest gap",
        "$",
        lambda t: f"=ABS({cref(t, CD_INTEREST)}-{cref(t, CD_DEBT_OPEN)}*(MAX(SOFR_FLOOR_PCT,INDEX(SOFR!$C$2:$C$85,{cref(t, 2)}))+CT_SPREAD_PCT)/12)",
        FMT_GAP,
    )
    monthly(
        ws,
        CD_ROLL_GAP,
        "Audit roll-forward gap",
        "$",
        lambda t: "=ABS(C12-0)" if t == 1 else f"=ABS({cref(t, CD_DEBT_OPEN)}-({pref(t, CD_DEBT_OPEN)}+{pref(t, CD_DRAWS)}-{pref(t, CD_REPAY)}))",
        FMT_GAP,
    )


def write_permanent(ws) -> None:
    write_month_axis(ws)
    monthly(ws, PD_ACTIVE, "Permanent loan active", "1/0", lambda t: f"=IF(AND({cref(t, 2)}>=PERM_CONV_M,{cref(t, 2)}<=EXIT_M),1,0)", FMT_INT)
    monthly(
        ws,
        PD_OPEN,
        "Opening balance",
        "$",
        lambda t: f"=IF({cref(t, 2)}<PERM_CONV_M,0,IF({cref(t, 2)}=PERM_CONV_M,$C${PD_GROSS},0))" if t == 1 else f"=IF({cref(t, 2)}<PERM_CONV_M,0,IF({cref(t, 2)}=PERM_CONV_M,$C${PD_GROSS},{pref(t, PD_CLOSE)}))",
        FMT_USD,
    )
    monthly(ws, PD_INTEREST, "Interest on opening balance", "$", lambda t: f"={cref(t, PD_OPEN)}*PERM_RATE_PCT/12", FMT_USD)
    monthly(ws, PD_PMT, "Scheduled payment", "$", lambda t: f"=IF(AND({cref(t, 2)}>=PERM_CONV_M,{cref(t, 2)}<EXIT_M),PMT(PERM_RATE_PCT/12,PERM_AMORT_YRS*12,-$C${PD_GROSS}),0)", FMT_USD)
    monthly(ws, PD_PRIN, "Scheduled principal", "$", lambda t: f"=IF({cref(t, PD_PMT)}=0,0,{cref(t, PD_PMT)}-{cref(t, PD_INTEREST)})", FMT_USD)
    monthly(ws, PD_PAYOFF, "Exit payoff", "$", lambda t: f"=IF({cref(t, 2)}=EXIT_M,{cref(t, PD_OPEN)},0)", FMT_USD)
    monthly(ws, PD_DS, "Debt service excluding balloon", "$", lambda t: f"={cref(t, PD_INTEREST)}+{cref(t, PD_PRIN)}", FMT_USD)
    monthly(ws, PD_CT_PAYOFF, "Construction balance repaid", "$", lambda t: f"=ConstructionDebt!{cref(t, CD_PERM_PAYOFF)}", FMT_USD)
    monthly(ws, PD_CLOSE, "Closing balance", "$", lambda t: f"={cref(t, PD_OPEN)}-{cref(t, PD_PRIN)}-{cref(t, PD_PAYOFF)}", FMT_USD)
    monthly(ws, PD_REFI, "Net refinance proceeds", "$", lambda t: f"=IF({cref(t, 2)}=PERM_CONV_M,$C${PD_GROSS}*(1-PERM_COSTS_PCT)-{cref(t, PD_CT_PAYOFF)},0)", FMT_USD)

    ws["A29"] = "Sizing at conversion, on T12 NOI ending PERM_CONV_M"
    ws["A29"].font = TITLE
    scalar(ws, PD_H_T12, "Hotel T12 NOI at conversion", "$", f"=SUM(INDEX(HotelProForma!C{HP_NOI}:CH{HP_NOI},PERM_CONV_M-11):INDEX(HotelProForma!C{HP_NOI}:CH{HP_NOI},PERM_CONV_M))", FMT_USD)
    scalar(ws, PD_R_T12, "Retail T12 NOI at conversion", "$", f"=SUM(INDEX(RetailProForma!C{RP_NOI}:CH{RP_NOI},PERM_CONV_M-11):INDEX(RetailProForma!C{RP_NOI}:CH{RP_NOI},PERM_CONV_M))", FMT_USD)
    scalar(ws, PD_NOI, "Combined T12 NOI", "$", f"=C{PD_H_T12}+C{PD_R_T12}", FMT_USD)
    scalar(ws, PD_H_VAL, "Hotel value at conversion", "$", f"=C{PD_H_T12}/HOTEL_CAP", FMT_USD)
    scalar(ws, PD_R_VAL, "Retail value at conversion", "$", f"=C{PD_R_T12}/RETAIL_CAP", FMT_USD)
    scalar(ws, PD_LTV, "LTV size", "$", f"=PERM_LTV*(C{PD_H_VAL}+C{PD_R_VAL})", FMT_USD)
    scalar(ws, PD_PMT_F, "PMT factor", "$ per $1", "=PMT(PERM_RATE_PCT/12,PERM_AMORT_YRS*12,-1)", FMT_NUM)
    scalar(ws, PD_DSCR, "DSCR size", "$", f"=(C{PD_NOI}/PERM_DSCR)/C{PD_PMT_F}", FMT_USD)
    scalar(ws, PD_DY, "Debt-yield size", "$", f"=C{PD_NOI}/PERM_DY", FMT_USD)
    scalar(ws, PD_GROSS, "Permanent proceeds", "$", f"=MIN(C{PD_LTV},C{PD_DSCR},C{PD_DY})", FMT_USD)
    ws["D35"] = "Proceeds are the minimum of the LTV, DSCR, and debt-yield sizes."
    ws["D35"].font = BLACK


def write_valuation(ws, source: str, noi_row: int, cap_name: str, kind: str) -> None:
    write_month_axis(ws)
    monthly(ws, 4, f"{kind} NOI", "$", lambda t: f"={source}!{cref(t, noi_row)}", FMT_USD)
    scalar(ws, 6, "T12 NOI at exit", "$", f"=SUM(INDEX(C4:CH4,EXIT_M-11):INDEX(C4:CH4,EXIT_M))", FMT_USD)
    scalar(ws, 7, f"{kind} value", "$", f"=C6/{cap_name}", FMT_USD)
    ws["D6"] = "Trailing 12 months ending EXIT_M."
    ws["D7"] = f"T12 NOI divided by {cap_name}. No condo cap rate on this sheet."
    ws["D6"].font = BLACK
    ws["D7"].font = BLACK
    ws["A9"] = "T12 build-up"
    ws["A9"].font = TITLE
    for k in range(1, 13):
        row = 9 + k
        write_label(ws, row, f"Trailing month {k}", "month")
        ws.cell(row, 3, f"=INDEX($C$2:$CH$2,EXIT_M-12+{k})").font = BLACK
        ws.cell(row, 3).number_format = FMT_INT
        ws.cell(row, 4, f"=INDEX($C$4:$CH$4,EXIT_M-12+{k})").font = BLACK
        ws.cell(row, 4).number_format = FMT_USD
    scalar(ws, 22, "T12 build-up sum", "$", "=SUM(D10:D21)", FMT_USD)
    scalar(ws, 23, "Build-up minus T12", "$", "=C22-C6", FMT_GAP)


def write_project(ws) -> None:
    write_month_axis(ws)
    monthly(ws, PC_CONDO_NET, "Condo net revenue", "$", lambda t: f"=CondoSellout!{cref(t, CS_NET)}", FMT_USD)
    monthly(ws, PC_CONDO_REPAY, "Condo applied to construction debt", "$", lambda t: f"=ConstructionDebt!{cref(t, CD_CONDO_REPAY)}", FMT_USD)
    monthly(ws, PC_CONDO_EQ, "Condo net after construction paydown", "$", lambda t: f"={cref(t, PC_CONDO_NET)}-{cref(t, PC_CONDO_REPAY)}", FMT_USD)
    monthly(ws, PC_HOTEL, "Hotel NOI", "$", lambda t: f"=HotelProForma!{cref(t, HP_NOI)}", FMT_USD)
    monthly(ws, PC_RETAIL, "Retail NOI", "$", lambda t: f"=RetailProForma!{cref(t, RP_NOI)}", FMT_USD)
    monthly(ws, PC_DS, "Permanent debt service", "$", lambda t: f"=PermanentDebt!{cref(t, PD_DS)}", FMT_USD)
    monthly(ws, PC_REFI, "Refinance net proceeds", "$", lambda t: f"=PermanentDebt!{cref(t, PD_REFI)}", FMT_USD)
    monthly(
        ws,
        PC_TERMINAL,
        "Terminal net proceeds",
        "$",
        lambda t: f"=IF({cref(t, 2)}=EXIT_M,(HotelValuation!$C$7+RetailValuation!$C$7)*(1-SELL_COST_PCT)-PermanentDebt!{cref(t, PD_PAYOFF)},0)",
        FMT_USD,
    )
    monthly(
        ws,
        PC_DIST,
        "Distributable cash",
        "$",
        lambda t: f"={cref(t, PC_CONDO_EQ)}+{cref(t, PC_HOTEL)}+{cref(t, PC_RETAIL)}-{cref(t, PC_DS)}+{cref(t, PC_REFI)}+{cref(t, PC_TERMINAL)}",
        FMT_USD,
    )
    monthly(ws, PC_EQ, "Equity contribution", "$", lambda t: f"=ConstructionDebt!{cref(t, CD_EQ_CONTRIB)}", FMT_USD)
    monthly(ws, PC_T1, "Waterfall tier 1", "$", lambda t: f"=Waterfall!{cref(t, WF_T1)}", FMT_USD)
    monthly(ws, PC_T2, "Waterfall tier 2", "$", lambda t: f"=Waterfall!{cref(t, WF_T2)}", FMT_USD)
    monthly(ws, PC_T3, "Waterfall tier 3", "$", lambda t: f"=Waterfall!{cref(t, WF_T3)}", FMT_USD)
    monthly(ws, PC_T4, "Waterfall tier 4", "$", lambda t: f"=Waterfall!{cref(t, WF_T4)}", FMT_USD)
    monthly(ws, PC_RETAINED, "Retained cash", "$", lambda t: f"={cref(t, PC_DIST)}-({cref(t, PC_T1)}+{cref(t, PC_T2)}+{cref(t, PC_T3)}+{cref(t, PC_T4)})", FMT_GAP)


def write_waterfall(ws) -> None:
    write_month_axis(ws)
    monthly(ws, WF_DIST, "Distributable cash", "$", lambda t: f"=ProjectCF!{cref(t, PC_DIST)}", FMT_USD)
    monthly(ws, WF_UNRET_OPEN, "Unreturned LP capital opening", "$", lambda t: f"={su(SU_LP)}" if t == 1 else f"={pref(t, WF_UNRET_CLOSE)}", FMT_USD)
    monthly(ws, WF_PREF_OPEN, "Unpaid preferred opening", "$", lambda t: "=0" if t == 1 else f"={pref(t, WF_PREF_CLOSE)}", FMT_USD)
    monthly(ws, WF_ACCRUAL, "Preferred accrual", "$", lambda t: f"=({cref(t, WF_UNRET_OPEN)}+{cref(t, WF_PREF_OPEN)})*PREF_PCT/12", FMT_USD)
    monthly(ws, WF_T1_NEED, "Tier 1 unpaid hurdle", "$", lambda t: f"={cref(t, WF_UNRET_OPEN)}+{cref(t, WF_PREF_OPEN)}+{cref(t, WF_ACCRUAL)}", FMT_USD)
    monthly(ws, WF_T1, "Tier 1 to LP", "$", lambda t: f"=IF({cref(t, WF_DIST)}<0,{cref(t, WF_DIST)},MIN(MAX({cref(t, WF_DIST)},0),MAX(0,{cref(t, WF_T1_NEED)})))", FMT_USD)
    monthly(ws, WF_AFTER_T1, "Cash after tier 1", "$", lambda t: f"={cref(t, WF_DIST)}-{cref(t, WF_T1)}", FMT_USD)
    monthly(ws, WF_PREF_PAID, "Preferred paid", "$", lambda t: f"=MIN(MAX({cref(t, WF_T1)},0),{cref(t, WF_PREF_OPEN)}+{cref(t, WF_ACCRUAL)})", FMT_USD)
    monthly(ws, WF_CAP_PAID, "LP capital returned", "$", lambda t: f"=MAX({cref(t, WF_T1)},0)-{cref(t, WF_PREF_PAID)}", FMT_USD)
    monthly(ws, WF_UNRET_CLOSE, "Unreturned LP capital closing", "$", lambda t: f"={cref(t, WF_UNRET_OPEN)}-{cref(t, WF_CAP_PAID)}", FMT_USD)
    monthly(ws, WF_PREF_CLOSE, "Unpaid preferred closing", "$", lambda t: f"={cref(t, WF_PREF_OPEN)}+{cref(t, WF_ACCRUAL)}-{cref(t, WF_PREF_PAID)}", FMT_USD)
    monthly(ws, WF_T1_DONE, "Tier 1 complete", "1/0", lambda t: f"=IF({cref(t, WF_T1_NEED)}-MAX({cref(t, WF_T1)},0)<=0.01,1,0)", FMT_INT)
    monthly(ws, WF_PREF_CUM, "Cumulative preferred paid", "$", lambda t: f"={cref(t, WF_PREF_PAID)}" if t == 1 else f"={pref(t, WF_PREF_CUM)}+{cref(t, WF_PREF_PAID)}", FMT_USD)
    monthly(ws, WF_T2_TARGET, "Tier 2 target", "$", lambda t: f"=IF({cref(t, WF_T1_DONE)}=1,CATCHUP_PCT/(1-CATCHUP_PCT)*{cref(t, WF_PREF_CUM)},0)", FMT_USD)
    monthly(ws, WF_T2_PRIOR, "Tier 2 previously paid", "$", lambda t: "=0" if t == 1 else f"={pref(t, WF_T2_CUM)}", FMT_USD)
    monthly(ws, WF_T2_NEED, "Tier 2 remaining", "$", lambda t: f"=MAX(0,{cref(t, WF_T2_TARGET)}-{cref(t, WF_T2_PRIOR)})", FMT_USD)
    monthly(ws, WF_T2, "Tier 2 to GP", "$", lambda t: f"=IF({cref(t, WF_T1_DONE)}=1,MIN(MAX({cref(t, WF_AFTER_T1)},0),{cref(t, WF_T2_NEED)}),0)", FMT_USD)
    monthly(ws, WF_T2_CUM, "Tier 2 cumulative", "$", lambda t: f"={cref(t, WF_T2_PRIOR)}+{cref(t, WF_T2)}", FMT_USD)
    monthly(ws, WF_T2_DONE, "Tier 2 complete", "1/0", lambda t: f"=IF(AND({cref(t, WF_T1_DONE)}=1,{cref(t, WF_T2_TARGET)}-{cref(t, WF_T2_CUM)}<=0.01),1,0)", FMT_INT)
    monthly(ws, WF_LP_ACCRUED, "Tier 3 LP accrual gate", "$", lambda t: f"={su(SU_LP)}*(1+T3_ACCRUAL_PCT/12)^{cref(t, 2)}", FMT_USD)
    monthly(ws, WF_LP_BEFORE, "LP distributions before tier 3", "$", lambda t: f"={cref(t, WF_T1)}" if t == 1 else f"={pref(t, WF_LP_CUM)}+{cref(t, WF_T1)}", FMT_USD)
    monthly(ws, WF_T3_GAP, "Tier 3 LP gap", "$", lambda t: f"=MAX(0,{cref(t, WF_LP_ACCRUED)}-{cref(t, WF_LP_BEFORE)})", FMT_USD)
    monthly(ws, WF_T3_NEED, "Tier 3 cash to close the gap", "$", lambda t: f"=IF(T3_LP_SPLIT<=0,0,{cref(t, WF_T3_GAP)}/T3_LP_SPLIT)", FMT_USD)
    monthly(ws, WF_T4_ALREADY, "Tier 4 already open", "1/0", lambda t: "=0" if t == 1 else f"={pref(t, WF_T4_OPEN)}", FMT_INT)
    monthly(
        ws,
        WF_T3,
        "Tier 3 distribution",
        "$",
        lambda t: f"=IF({cref(t, WF_T4_ALREADY)}=1,0,IF(AND({cref(t, WF_T2_DONE)}=1,{cref(t, WF_T3_GAP)}>0.01),MIN(MAX({cref(t, WF_AFTER_T1)}-{cref(t, WF_T2)},0),{cref(t, WF_T3_NEED)}),0))",
        FMT_USD,
    )
    monthly(ws, WF_T3_LP, "Tier 3 to LP", "$", lambda t: f"={cref(t, WF_T3)}*T3_LP_SPLIT", FMT_USD)
    monthly(ws, WF_T3_GP, "Tier 3 to GP", "$", lambda t: f"={cref(t, WF_T3)}*(1-T3_LP_SPLIT)", FMT_USD)
    monthly(ws, WF_GATE_NOW, "Tier 3 gate met this month", "1/0", lambda t: f"=IF(AND({cref(t, WF_T2_DONE)}=1,{cref(t, WF_LP_BEFORE)}+{cref(t, WF_T3_LP)}+0.01>={cref(t, WF_LP_ACCRUED)}),1,0)", FMT_INT)
    monthly(ws, WF_T4_OPEN, "Tier 4 open", "1/0", lambda t: f"=IF(OR({cref(t, WF_T4_ALREADY)}=1,{cref(t, WF_GATE_NOW)}=1),1,0)", FMT_INT)
    monthly(ws, WF_T4, "Tier 4 distribution", "$", lambda t: f"={cref(t, WF_DIST)}-{cref(t, WF_T1)}-{cref(t, WF_T2)}-{cref(t, WF_T3)}", FMT_USD)
    monthly(ws, WF_T4_LP, "Tier 4 to LP", "$", lambda t: f"={cref(t, WF_T4)}*T4_LP_SPLIT", FMT_USD)
    monthly(ws, WF_T4_GP, "Tier 4 to GP", "$", lambda t: f"={cref(t, WF_T4)}*(1-T4_LP_SPLIT)", FMT_USD)
    monthly(ws, WF_TIER_SUM, "Tier sum", "$", lambda t: f"={cref(t, WF_T1)}+{cref(t, WF_T2)}+{cref(t, WF_T3)}+{cref(t, WF_T4)}", FMT_USD)
    monthly(ws, WF_LP_DIST, "LP distribution", "$", lambda t: f"={cref(t, WF_T1)}+{cref(t, WF_T3_LP)}+{cref(t, WF_T4_LP)}", FMT_USD)
    monthly(ws, WF_GP_DIST, "GP distribution", "$", lambda t: f"={cref(t, WF_T2)}+{cref(t, WF_T3_GP)}+{cref(t, WF_T4_GP)}", FMT_USD)
    monthly(ws, WF_LP_CUM, "Cumulative LP distributions", "$", lambda t: f"={cref(t, WF_LP_DIST)}" if t == 1 else f"={pref(t, WF_LP_CUM)}+{cref(t, WF_LP_DIST)}", FMT_USD)
    monthly(ws, WF_TIER_GAP, "Audit tier gap", "$", lambda t: f"=ABS({cref(t, WF_TIER_SUM)}-{cref(t, WF_DIST)})", FMT_GAP)
    monthly(ws, WF_T2_BAD, "Audit tier 2 before tier 1", "count", lambda t: f"=IF(AND({cref(t, WF_T2)}>0.01,{cref(t, WF_T1_NEED)}-MAX({cref(t, WF_T1)},0)>0.01),1,0)", FMT_INT)
    monthly(ws, WF_T3_BAD, "Audit tier 3 before tier 2", "count", lambda t: f"=IF(AND({cref(t, WF_T3)}>0.01,{cref(t, WF_T2_DONE)}=0),1,0)", FMT_INT)
    monthly(ws, WF_T4_BAD, "Audit tier 4 before gate", "count", lambda t: f"=IF(AND(ABS({cref(t, WF_T4)})>0.01,{cref(t, WF_T4_OPEN)}=0),1,0)", FMT_INT)


def write_returns(ws) -> None:
    write_month_axis(ws)
    monthly(ws, 4, "Project equity cash flow", "$", lambda t: f"=-ConstructionDebt!{cref(t, CD_EQ_CONTRIB)}+ProjectCF!{cref(t, PC_DIST)}", FMT_USD)
    monthly(ws, 5, "LP cash flow", "$", lambda t: f"=IF({cref(t, 2)}=1,-{su(SU_LP)},0)+Waterfall!{cref(t, WF_LP_DIST)}", FMT_USD)
    monthly(ws, 6, "GP cash flow", "$", lambda t: f"=IF({cref(t, 2)}=1,-{su(SU_GP)},0)+Waterfall!{cref(t, WF_GP_DIST)}", FMT_USD)
    scalar(ws, 8, "Project XIRR", "%", "=XIRR(C4:CH4,C3:CH3)", FMT_PCT)
    scalar(ws, 9, "LP XIRR", "%", "=XIRR(C5:CH5,C3:CH3)", FMT_PCT)
    scalar(ws, 10, "GP XIRR", "%", "=XIRR(C6:CH6,C3:CH3)", FMT_PCT)
    scalar(ws, 12, "Project equity multiple", "x", f"=SUM(ProjectCF!C{PC_DIST}:CH{PC_DIST})/{su(SU_EQUITY)}", FMT_NUM)
    scalar(ws, 13, "LP equity multiple", "x", f"=IF({su(SU_LP)}=0,0,SUM(Waterfall!C{WF_LP_DIST}:CH{WF_LP_DIST})/{su(SU_LP)})", FMT_NUM)
    scalar(ws, 14, "GP equity multiple", "x", f"=IF({su(SU_GP)}=0,0,SUM(Waterfall!C{WF_GP_DIST}:CH{WF_GP_DIST})/{su(SU_GP)})", FMT_NUM)
    scalar(ws, 16, "LP distributions", "$", f"=SUM(Waterfall!C{WF_LP_DIST}:CH{WF_LP_DIST})", FMT_USD)
    scalar(ws, 17, "GP distributions", "$", f"=SUM(Waterfall!C{WF_GP_DIST}:CH{WF_GP_DIST})", FMT_USD)
    scalar(ws, 18, "Promote $", "$", f"=C17-{su(SU_GP)}", FMT_USD)
    ws["D8"] = "XIRR is an output only. It does not trigger a tier."
    ws["D18"] = "GP distributions minus GP contributed capital. GP capital is not a separate waterfall tier."
    ws["D8"].font = BLACK
    ws["D18"].font = BLACK


def write_checks(ws) -> None:
    write_title(ws, "Checks")
    ws["A2"] = "ID"
    ws["B2"] = "Identity"
    ws["C2"] = "Result"
    for col_idx in range(1, 4):
        ws.cell(2, col_idx).font = LABEL
    ws.column_dimensions["B"].width = 88
    ws.column_dimensions["C"].width = 14
    gross = (
        "UNITS_STUDIO*SQFT_STUDIO*PPSF_STUDIO+UNITS_1BR*SQFT_1BR*PPSF_1BR+"
        "UNITS_2BR*SQFT_2BR*PPSF_2BR+UNITS_3BR*SQFT_3BR*PPSF_3BR+"
        "UNITS_PH*SQFT_PH*PPSF_PH+PARKING_SPACES*PARKING_PRICE+STORAGE_UNITS*STORAGE_PRICE"
    )
    checks = [
        ("C1", "Sources equal uses, and the uses component sum ties, within $1", f"=AND(ABS(SourcesUses!C{SU_GAP})<=1,ABS(SourcesUses!C{SU_TIE})<=1)"),
        ("C2", "Every month, construction interest equals opening balance times (MAX(floor, SOFR)+spread)/12, within $0.01", f"=MAX(ConstructionDebt!C{CD_INT_GAP}:CH{CD_INT_GAP})<=0.01"),
        ("C3", "Every month, construction opening and closing balances are between 0 and commitment, within $1", f"=AND(MIN(ConstructionDebt!C{CD_DEBT_OPEN}:CH{CD_DEBT_OPEN})>=-1,MIN(ConstructionDebt!C{CD_DEBT_CLOSE}:CH{CD_DEBT_CLOSE})>=-1,MAX(ConstructionDebt!C{CD_DEBT_OPEN}:CH{CD_DEBT_OPEN})<=SourcesUses!C{SU_COMMIT}+1,MAX(ConstructionDebt!C{CD_DEBT_CLOSE}:CH{CD_DEBT_CLOSE})<=SourcesUses!C{SU_COMMIT}+1)"),
        ("C4", "Permanent proceeds equal MIN(LTV size, DSCR size, debt-yield size), within $1", f"=ABS(PermanentDebt!C{PD_GROSS}-MIN(PermanentDebt!C{PD_LTV},PermanentDebt!C{PD_DSCR},PermanentDebt!C{PD_DY}))<=1"),
        ("C5", "Closings by type equal inventory, and gross sellout equals unit prices plus parking plus storage, within $1", f"=AND(ABS(SUM(CondoSellout!C{CS_STUDIO}:CH{CS_STUDIO})-UNITS_STUDIO)<=1,ABS(SUM(CondoSellout!C{CS_1BR}:CH{CS_1BR})-UNITS_1BR)<=1,ABS(SUM(CondoSellout!C{CS_2BR}:CH{CS_2BR})-UNITS_2BR)<=1,ABS(SUM(CondoSellout!C{CS_3BR}:CH{CS_3BR})-UNITS_3BR)<=1,ABS(SUM(CondoSellout!C{CS_PH}:CH{CS_PH})-UNITS_PH)<=1,ABS(SUM(CondoSellout!C{CS_GROSS}:CH{CS_GROSS})-({gross}))<=1)"),
        ("C6", "Hotel value equals exit T12 NOI over hotel cap, and retail value equals exit T12 NOI over retail cap, within $1", f"=AND(ABS(HotelValuation!C7-HotelValuation!C6/HOTEL_CAP)<=1,ABS(RetailValuation!C7-RetailValuation!C6/RETAIL_CAP)<=1)"),
        ("C7", "Every month, tier distributions equal distributable cash within $0.01, and retained cash at exit is 0", f"=AND(MAX(Waterfall!C{WF_TIER_GAP}:CH{WF_TIER_GAP})<=0.01,ABS(INDEX(ProjectCF!C{PC_RETAINED}:CH{PC_RETAINED},EXIT_M))<=0.01)"),
        ("C8", "No tier 2 before tier 1 is paid, no tier 3 before tier 2 is complete, no tier 4 before the tier 3 gate", f"=AND(SUM(Waterfall!C{WF_T2_BAD}:CH{WF_T2_BAD})=0,SUM(Waterfall!C{WF_T3_BAD}:CH{WF_T3_BAD})=0,SUM(Waterfall!C{WF_T4_BAD}:CH{WF_T4_BAD})=0)"),
        ("C9", "Equity contributions equal the equity requirement, within $1", f"=ABS(SUM(ConstructionDebt!C{CD_EQ_CONTRIB}:CH{CD_EQ_CONTRIB})-SourcesUses!C{SU_EQUITY})<=1"),
        ("C10", "Construction opening balance equals the prior opening balance plus draws minus repayments", f"=MAX(ConstructionDebt!C{CD_ROLL_GAP}:CH{CD_ROLL_GAP})<=0.01"),
        ("C11", "Key calculated outputs are numbers, so those cells are not #REF!, #NAME?, #VALUE!, or #CYCLE!", f"=AND(ISNUMBER(SourcesUses!C{SU_TOTAL}),ISNUMBER(SourcesUses!C{SU_COMMIT}),ISNUMBER(SourcesUses!C{SU_EQUITY}),ISNUMBER(PermanentDebt!C{PD_GROSS}),ISNUMBER(HotelValuation!C7),ISNUMBER(RetailValuation!C7),ISNUMBER(SUM(ProjectCF!C{PC_DIST}:CH{PC_DIST})),ISNUMBER(SUM(Waterfall!C{WF_T1}:CH{WF_T1})))"),
        ("C12", "Every SOFR source cell carries the ASSUMPTION placeholder label", f'=COUNTIF(SOFR!D2:D85,"{SOURCE_LABEL}")=84'),
    ]
    for i, (cid, text, formula) in enumerate(checks):
        row = 5 + i
        ws.cell(row, 1, cid).font = LABEL
        ws.cell(row, 2, text).font = BLACK
        cell = ws.cell(row, 3, formula)
        cell.font = BLACK
    ws["A3"] = "MASTER"
    ws["A3"].font = LABEL
    ws["B3"] = "All checks"
    master = ws["C3"]
    master.value = "=AND(C5,C6,C7,C8,C9,C10,C11,C12,C13,C14,C15,C16)"
    master.font = LABEL
    ws["A18"] = "Tolerances are $1 for balance and level checks and $0.01 for monthly flow checks."
    ws["A18"].font = BLACK


def _is_blue(cell) -> bool:
    color = cell.font.color
    if color is None:
        return False
    rgb = getattr(color, "rgb", None)
    return rgb in ("0000FF", "000000FF")


def audit(path: Path, names: set[str]) -> None:
    from openpyxl import load_workbook

    wb = load_workbook(path)
    found = [ws.title for ws in wb.worksheets]
    if found != SHEETS:
        raise SystemExit(f"sheet order mismatch: {found}")
    defined = set(wb.defined_names)
    missing = names - defined
    extra = defined - names
    if missing or extra:
        raise SystemExit(f"defined names mismatch missing={sorted(missing)} extra={sorted(extra)}")
    if wb["Cover"]["A3"].value != DISCLAIMER:
        raise SystemExit("disclaimer text mismatch")
    for t in range(1, MONTHS + 1):
        if wb["SOFR"].cell(t + 1, 4).value != SOURCE_LABEL:
            raise SystemExit(f"SOFR source label mismatch at month {t}")
        rate = wb["SOFR"].cell(t + 1, 3)
        if not isinstance(rate.value, float) or not _is_blue(rate):
            raise SystemExit(f"SOFR rate cell is not a blue input at month {t}")
    for name in names:
        ref = wb.defined_names[name].attr_text
        if not ref.startswith("Assumptions!$C$"):
            raise SystemExit(f"{name} does not point at Assumptions column C")
        row = int(ref.split("$")[-1])
        cell = wb["Assumptions"].cell(row, 3)
        if not _is_blue(cell):
            raise SystemExit(f"{name} is not blue")
        if not isinstance(cell.value, (int, float)):
            raise SystemExit(f"{name} is not a value")
    forbidden = ("fetched", "live Chatham fetch", "sourced from Chatham", "downloaded")
    for ws in wb.worksheets:
        if ws.merged_cells.ranges:
            raise SystemExit(f"merged cells on {ws.title}")
        for row in ws.iter_rows():
            for cell in row:
                text = cell.value if isinstance(cell.value, str) else ""
                lower = text.lower()
                for phrase in forbidden:
                    if phrase in lower:
                        raise SystemExit(f"forbidden phrase {phrase!r} in {ws.title}!{cell.coordinate}")
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    for token in _large_numbers(cell.value):
                        raise SystemExit(f"hardcoded number {token} in {ws.title}!{cell.coordinate}")
    interest = wb["ConstructionDebt"]["C13"].value
    if not isinstance(interest, str) or "MAX(SOFR_FLOOR_PCT" not in interest or "/12" not in interest:
        raise SystemExit(f"interest formula missing MAX/spread identity: {interest}")
    proceeds = wb["PermanentDebt"]["C39"].value
    if proceeds != "=MIN(C35,C37,C38)":
        raise SystemExit(f"permanent proceeds formula mismatch: {proceeds}")
    if wb["HotelValuation"]["C7"].value != "=C6/HOTEL_CAP":
        raise SystemExit("hotel value formula mismatch")
    if wb["RetailValuation"]["C7"].value != "=C6/RETAIL_CAP":
        raise SystemExit("retail value formula mismatch")
    tier4 = wb["Waterfall"]["C33"].value
    if tier4 != "=C4-C9-C20-C28":
        raise SystemExit(f"tier 4 plug mismatch: {tier4}")
    if not str(wb["Checks"]["C3"].value).startswith("=AND("):
        raise SystemExit("master check is not an AND formula")
    formula_cells = 0
    value_inputs = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    formula_cells += 1
                elif isinstance(cell.value, (int, float)):
                    value_inputs += 1
    if formula_cells < 5000:
        raise SystemExit(f"too few formulas: {formula_cells}")
    print(f"sheets={len(found)} names={len(defined)} formulas={formula_cells} numeric_inputs={value_inputs}")


def _large_numbers(formula: str) -> list[str]:
    import re

    bad = []
    for token in re.findall(r"\d+(?:\.\d+)?", formula):
        if token in {"2026", "0", "1", "2", "12"}:
            continue
        if float(token) >= 1000:
            bad.append(token)
    return bad


def main() -> None:
    summary = build()
    print(f"wrote {OUT}")
    for key in (
        "total_uses",
        "commitment",
        "equity",
        "reserve",
        "max_balance",
        "perm_proceeds",
        "ltv_size",
        "dscr_size",
        "dy_size",
        "hotel_value_exit",
        "retail_value_exit",
        "condo_gross",
        "ct_payoff_at_conv",
        "min_dist",
        "tier_gap",
    ):
        print(f"{key}={summary[key]:.2f}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        raise
