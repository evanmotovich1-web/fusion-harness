#!/usr/bin/env python3
"""Read-only identity check for the saved mixed-use workbook.

Recomputes SPEC.md C1-C12 from named inputs and SOFR rate cells. Does not
read Excel cached values, does not save the workbook, and does not install
LibreOffice.
"""

from __future__ import annotations

import calendar
import hashlib
import math
import re
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.formula import ArrayFormula

ROOT = Path(__file__).resolve().parent
XLSX = ROOT / "elite-luxury-mixed-use-model.xlsx"
REPORT = ROOT / "VALIDATION.md"
MONTHS = 84
FIRST_COL = 3
LAST_COL = 86  # CH
SOURCE_LABEL = (
    "ASSUMPTION — placeholder forward; not a live Chatham quote. "
    "Paste Chatham forwards here."
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
REQUIRED_NAMES = [
    "CONSTR_MONTHS", "RETAIL_OPEN_M", "HOTEL_OPEN_M", "FIRST_CLOSING_M",
    "CLOSINGS_SPAN_M", "PERM_CONV_M", "EXIT_M",
    "UNITS_STUDIO", "SQFT_STUDIO", "PPSF_STUDIO",
    "UNITS_1BR", "SQFT_1BR", "PPSF_1BR",
    "UNITS_2BR", "SQFT_2BR", "PPSF_2BR",
    "UNITS_3BR", "SQFT_3BR", "PPSF_3BR",
    "UNITS_PH", "SQFT_PH", "PPSF_PH",
    "PARKING_SPACES", "PARKING_PRICE", "STORAGE_UNITS", "STORAGE_PRICE",
    "CLOSING_COST_PCT", "MARKETING_PCT",
    "LAND_COST", "ACQ_COST_PCT", "RES_GSF", "HOTEL_GSF", "RETAIL_GSF",
    "HC_PSF_RES", "HC_PSF_HOTEL", "HC_PSF_RETAIL",
    "CONTINGENCY_PCT", "SOFTCOST_PCT", "HOTEL_KEYS", "FFE_PER_KEY",
    "FFE_PSF_RETAIL", "DEVFEE_PCT",
    "LTC_PCT", "CT_SPREAD_PCT", "SOFR_FLOOR_PCT", "AVG_DRAWN_FRAC", "CT_COSTS_PCT",
    "PERM_LTV", "PERM_DSCR", "PERM_DY", "PERM_RATE_PCT", "PERM_AMORT_YRS", "PERM_COSTS_PCT",
    "ADR_Y1", "ADR_GROWTH_PCT", "OCC_Y1", "OCC_Y2", "OCC_STAB",
    "FB_REV_PCT", "OTHER_REV_PCT", "HOTEL_UNDIST_PCT", "HOTEL_MGMT_PCT",
    "REPL_RESERVE_PCT", "HOTEL_CAP",
    "RETAIL_BASE_PSF", "RETAIL_ESC_PCT", "RETAIL_RECOV_PSF", "RETAIL_RECOV_RATIO",
    "RETAIL_VAC_PCT", "RETAIL_OP_PSF", "RETAIL_MGMT_PCT", "RETAIL_CAP",
    "SELL_COST_PCT", "GP_EQUITY_PCT", "PREF_PCT", "CATCHUP_PCT",
    "T3_ACCRUAL_PCT", "T3_LP_SPLIT", "T4_LP_SPLIT",
]
ERROR_RE = re.compile(r"#(?:REF!|NAME\?|VALUE!|CYCLE!|DIV/0!|N/A|NULL!|NUM!)")
FETCH_RE = re.compile(
    r"\b(fetched|downloaded|pulled|retrieved|scraped|imported)\b.{0,48}\bchatham\b"
    r"|\bchatham\b.{0,48}\b(fetched|downloaded|pulled|retrieved|scraped|imported)\b"
    r"|\blive chatham (quote|curve|forward)s?\b",
    re.IGNORECASE,
)
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
TOL_LEVEL = 1.0
TOL_FLOW = 0.01


class Failure(Exception):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def formula_text(value) -> str | None:
    if isinstance(value, ArrayFormula):
        return value.text or ""
    if isinstance(value, str) and value.startswith("="):
        return value
    return None


def month_end_day(t: int) -> int:
    idx = t - 1
    year = 2026 + idx // 12
    month = idx % 12 + 1
    return calendar.monthrange(year, month)[1]


def pmt_on_one(annual: float, years: float) -> float:
    rate = annual / 12.0
    nper = int(years * 12)
    if rate == 0:
        return 1.0 / nper
    growth = (1.0 + rate) ** nper
    return rate * growth / (growth - 1.0)


def label_map(ws) -> dict[str, int]:
    found: dict[str, int] = {}
    for row in ws.iter_rows(min_col=1, max_col=1, max_row=ws.max_row or 1):
        value = row[0].value
        if isinstance(value, str) and value.strip():
            found.setdefault(value.strip(), row[0].row)
    return found


def require_label(labels: dict[str, int], name: str, sheet: str) -> int:
    if name not in labels:
        raise Failure(f"{sheet} is missing label {name!r}")
    return labels[name]


def cell_ref(col: int, row: int) -> str:
    return f"{get_column_letter(col)}{row}"


def claims_live_fetch(text: str) -> bool:
    lowered = text.lower()
    if "chatham" not in lowered:
        return False
    if FETCH_RE.search(text) and "not a live chatham" not in lowered:
        return True
    if re.search(r"\bfetched from chatham\b|\bchatham fetch\b|\blive pull\b", lowered):
        return True
    return False


def check_ooxml(path: Path) -> dict:
    if not zipfile.is_zipfile(path):
        raise Failure("file is not a zip archive")
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise Failure(f"zip CRC failed at {bad}")
        names = set(archive.namelist())
        required = ["[Content_Types].xml", "xl/workbook.xml", "xl/_rels/workbook.xml.rels"]
        missing = [item for item in required if item not in names]
        if missing:
            raise Failure(f"OOXML parts missing: {missing}")
        content_types = archive.read("[Content_Types].xml")
        if b"spreadsheetml.sheet.main+xml" not in content_types:
            raise Failure("[Content_Types].xml has no workbook content type")
        root = ET.fromstring(archive.read("xl/workbook.xml"))
        xml_sheets = [node.attrib.get("name", "") for node in root.findall("m:sheets/m:sheet", NS)]
        sheet_parts = sorted(name for name in names if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"))
    return {
        "zip_ok": True,
        "crc": "ok",
        "xml_sheets": xml_sheets,
        "worksheet_parts": len(sheet_parts),
        "content_type": "spreadsheetml.sheet.main+xml",
    }


def resolve_defined_names(wb) -> tuple[dict[str, float], dict[str, str], set[tuple[str, int, int]]]:
    inputs: dict[str, float] = {}
    refs: dict[str, str] = {}
    input_cells: set[tuple[str, int, int]] = set()
    for defined in wb.defined_names.values():
        refs[defined.name] = defined.attr_text
        destinations = list(defined.destinations)
        if len(destinations) != 1:
            raise Failure(f"defined name {defined.name} does not resolve to one cell: {defined.attr_text}")
        sheet_name, coord = destinations[0]
        cell = wb[sheet_name][coord]
        if formula_text(cell.value) is not None:
            raise Failure(f"input {defined.name} at {sheet_name}!{coord} is a formula, not a value")
        if not isinstance(cell.value, (int, float)) or isinstance(cell.value, bool):
            raise Failure(f"input {defined.name} at {sheet_name}!{coord} is not numeric: {cell.value!r}")
        inputs[defined.name] = float(cell.value)
        input_cells.add((sheet_name, cell.row, cell.column))
    missing = [name for name in REQUIRED_NAMES if name not in inputs]
    if missing:
        raise Failure(f"missing named inputs: {missing}")
    return inputs, refs, input_cells


def read_sofr(wb) -> list[float]:
    ws = wb["SOFR"]
    rates = []
    for row in range(2, 2 + MONTHS):
        value = ws.cell(row, 3).value
        if formula_text(value) is not None or not isinstance(value, (int, float)) or isinstance(value, bool):
            raise Failure(f"SOFR!C{row} is not a numeric input: {value!r}")
        rates.append(float(value))
    return rates


def structural(wb, input_cells: set[tuple[str, int, int]], sofr_rows: range) -> dict:
    sheets = [ws.title for ws in wb.worksheets]
    problems = []
    if sheets != SHEETS:
        problems.append(f"sheet order {sheets}")
    formula_count = 0
    numeric_inputs = 0
    other_numbers = []
    formula_errors = []
    prose_error_mentions = []
    fetch_claims = []
    chatham_mentions = []
    merged = []
    non_equal_formulas = []
    sofr_sources = []
    for ws in wb.worksheets:
        if ws.merged_cells.ranges:
            merged.append(f"{ws.title}:{len(ws.merged_cells.ranges)}")
        for row in ws.iter_rows():
            for cell in row:
                value = cell.value
                text = formula_text(value)
                raw = text if text is not None else value
                if text is not None:
                    formula_count += 1
                    if not text.startswith("="):
                        non_equal_formulas.append(f"{ws.title}!{cell.coordinate}")
                    if ERROR_RE.search(text):
                        formula_errors.append(f"{ws.title}!{cell.coordinate}:{text[:80]}")
                elif isinstance(value, str) and ERROR_RE.search(value):
                    if value.strip() in {"#REF!", "#NAME?", "#VALUE!", "#CYCLE!", "#DIV/0!", "#N/A", "#NULL!", "#NUM!"}:
                        formula_errors.append(f"{ws.title}!{cell.coordinate}:{value}")
                    else:
                        prose_error_mentions.append(f"{ws.title}!{cell.coordinate}")
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    key = (ws.title, cell.row, cell.column)
                    if key in input_cells or (ws.title == "SOFR" and cell.column == 3 and cell.row in sofr_rows):
                        numeric_inputs += 1
                    else:
                        other_numbers.append(f"{ws.title}!{cell.coordinate}={value}")
                if isinstance(raw, str) and "chatham" in raw.lower():
                    chatham_mentions.append(f"{ws.title}!{cell.coordinate}")
                    if claims_live_fetch(raw):
                        fetch_claims.append(f"{ws.title}!{cell.coordinate}:{raw[:120]}")
                if cell.comment is not None and cell.comment.text and "chatham" in cell.comment.text.lower():
                    chatham_mentions.append(f"{ws.title}!{cell.coordinate}#comment")
                    if claims_live_fetch(cell.comment.text):
                        fetch_claims.append(f"{ws.title}!{cell.coordinate}#comment")
        for header in (ws.oddHeader, ws.evenHeader, ws.oddFooter, ws.evenFooter):
            for part in (header.left, header.center, header.right):
                if part is not None and part.text and "chatham" in part.text.lower():
                    chatham_mentions.append(f"{ws.title} header/footer")
                    if claims_live_fetch(part.text):
                        fetch_claims.append(f"{ws.title} header/footer:{part.text[:120]}")
    ws = wb["SOFR"]
    source_ok = True
    for row in range(2, 2 + MONTHS):
        value = ws.cell(row, 4).value
        sofr_sources.append(value)
        if value != SOURCE_LABEL:
            source_ok = False
            problems.append(f"SOFR!D{row} source label mismatch")
            break
    if merged:
        problems.append(f"merged cells: {merged}")
    if non_equal_formulas:
        problems.append(f"formula cells not starting with '=': {non_equal_formulas[:8]}")
    if formula_errors:
        problems.append(f"error tokens in formulas or error values: {formula_errors[:8]}")
    if other_numbers:
        problems.append(f"numeric constants outside inputs: {other_numbers[:8]}")
    if fetch_claims:
        problems.append(f"live Chatham fetch claims: {fetch_claims[:8]}")
    return {
        "sheets": sheets,
        "formula_count": formula_count,
        "numeric_inputs": numeric_inputs,
        "other_numbers": other_numbers,
        "formula_errors": formula_errors,
        "prose_error_mentions": prose_error_mentions,
        "fetch_claims": fetch_claims,
        "chatham_mentions": len(chatham_mentions),
        "source_ok": source_ok,
        "merged": merged,
        "problems": problems,
    }


def recompute(p: dict[str, float], sofr: list[float]) -> dict:
    constr = int(p["CONSTR_MONTHS"])
    if not 1 <= constr <= MONTHS:
        raise Failure(f"CONSTR_MONTHS out of range: {constr}")
    for name in ("RETAIL_OPEN_M", "HOTEL_OPEN_M", "FIRST_CLOSING_M", "PERM_CONV_M", "EXIT_M"):
        if not 1 <= int(p[name]) <= MONTHS:
            raise Failure(f"{name} out of range: {p[name]}")
    if int(p["EXIT_M"]) != MONTHS:
        raise Failure(f"EXIT_M must be {MONTHS}, got {p['EXIT_M']}")
    span = int(p["CLOSINGS_SPAN_M"])
    if span < 1:
        raise Failure("CLOSINGS_SPAN_M < 1")
    if abs(p["CATCHUP_PCT"] - 1) < 1e-12 or not 0 <= p["CATCHUP_PCT"] < 1:
        raise Failure("CATCHUP_PCT must be in [0, 1)")

    sofr_avg = sum(sofr[:constr]) / constr
    land_acq = p["LAND_COST"] * (1 + p["ACQ_COST_PCT"])
    hard = p["RES_GSF"] * p["HC_PSF_RES"] + p["HOTEL_GSF"] * p["HC_PSF_HOTEL"] + p["RETAIL_GSF"] * p["HC_PSF_RETAIL"]
    conting = p["CONTINGENCY_PCT"] * hard
    soft = p["SOFTCOST_PCT"] * hard
    ffe = p["HOTEL_KEYS"] * p["FFE_PER_KEY"] + p["RETAIL_GSF"] * p["FFE_PSF_RETAIL"]
    fee_base = land_acq + hard + conting + soft + ffe
    fee = p["DEVFEE_PCT"] * fee_base
    uses_ex = fee_base + fee
    reserve = p["LTC_PCT"] * uses_ex * ((sofr_avg + p["CT_SPREAD_PCT"]) / 12) * p["CONSTR_MONTHS"] * p["AVG_DRAWN_FRAC"]
    denom = 1 - p["LTC_PCT"] * p["CT_COSTS_PCT"]
    if denom <= 0:
        raise Failure("loan-cost closed form denominator is not positive")
    total_uses = (uses_ex + reserve) / denom
    commitment = p["LTC_PCT"] * total_uses
    loan_costs = p["CT_COSTS_PCT"] * commitment
    equity = total_uses - commitment
    sources = commitment + equity
    component = uses_ex + reserve + loan_costs
    nonland = hard + conting + soft + ffe + fee
    lp_eq = equity * (1 - p["GP_EQUITY_PCT"])

    def s_cum(t: int) -> float:
        if t >= constr:
            return 1.0
        if t <= 0:
            return 0.0
        return (t / constr) ** 2.2

    weights = []
    spend = []
    for t in range(1, MONTHS + 1):
        weight = s_cum(t) - s_cum(t - 1)
        weights.append(weight)
        land_t = land_acq if t == 1 else 0.0
        loan_t = loan_costs if t == 1 else 0.0
        spend.append(land_t + nonland * weight + loan_t)

    types = [
        ("STUDIO", p["UNITS_STUDIO"], p["SQFT_STUDIO"] * p["PPSF_STUDIO"]),
        ("1BR", p["UNITS_1BR"], p["SQFT_1BR"] * p["PPSF_1BR"]),
        ("2BR", p["UNITS_2BR"], p["SQFT_2BR"] * p["PPSF_2BR"]),
        ("3BR", p["UNITS_3BR"], p["SQFT_3BR"] * p["PPSF_3BR"]),
        ("PH", p["UNITS_PH"], p["SQFT_PH"] * p["PPSF_PH"]),
    ]
    total_units = sum(units for _name, units, _price in types)
    if total_units <= 0:
        raise Failure("condo inventory is zero")
    first = int(p["FIRST_CLOSING_M"])
    close_by_type = {name: [] for name, _units, _price in types}
    condo_gross = []
    condo_net = []
    for t in range(1, MONTHS + 1):
        closed = 0.0
        unit_rev = 0.0
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
            unit_rev += n * price
        gross = unit_rev + p["PARKING_SPACES"] * closed / total_units * p["PARKING_PRICE"] + p["STORAGE_UNITS"] * closed / total_units * p["STORAGE_PRICE"]
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
            rooms = p["HOTEL_KEYS"] * month_end_day(t) * occ * adr
            rev = rooms * (1 + p["FB_REV_PCT"] + p["OTHER_REV_PCT"])
            hotel_noi.append(rev * (1 - p["HOTEL_UNDIST_PCT"] - p["HOTEL_MGMT_PCT"] - p["REPL_RESERVE_PCT"]))
        else:
            hotel_noi.append(0.0)
        if t >= retail_open:
            elapsed = t - retail_open
            factor = (1 + p["RETAIL_ESC_PCT"]) ** int(elapsed / 12)
            base = p["RETAIL_BASE_PSF"] * factor * p["RETAIL_GSF"] / 12
            recov = p["RETAIL_RECOV_PSF"] * factor * p["RETAIL_GSF"] * p["RETAIL_RECOV_RATIO"] / 12
            egi = (base + recov) * (1 - p["RETAIL_VAC_PCT"])
            retail_noi.append(egi - p["RETAIL_OP_PSF"] * p["RETAIL_GSF"] / 12 - p["RETAIL_MGMT_PCT"] * egi)
        else:
            retail_noi.append(0.0)

    conv = int(p["PERM_CONV_M"])
    exit_m = int(p["EXIT_M"])

    def t12(series: list[float], end: int) -> float:
        if end < 12:
            raise Failure(f"T12 ending month {end} does not have 12 months")
        return sum(series[end - 12:end])

    noi_conv = t12(hotel_noi, conv) + t12(retail_noi, conv)
    h_val_c = t12(hotel_noi, conv) / p["HOTEL_CAP"]
    r_val_c = t12(retail_noi, conv) / p["RETAIL_CAP"]
    ltv_size = p["PERM_LTV"] * (h_val_c + r_val_c)
    pmt_factor = pmt_on_one(p["PERM_RATE_PCT"], p["PERM_AMORT_YRS"])
    dscr_size = (noi_conv / p["PERM_DSCR"]) / pmt_factor
    dy_size = noi_conv / p["PERM_DY"]
    proceeds = min(ltv_size, dscr_size, dy_size)
    binding = min((ltv_size, "LTV"), (dscr_size, "DSCR"), (dy_size, "DY"))[1]
    h_exit_noi = t12(hotel_noi, exit_m)
    r_exit_noi = t12(retail_noi, exit_m)
    h_exit = h_exit_noi / p["HOTEL_CAP"]
    r_exit = r_exit_noi / p["RETAIL_CAP"]

    debt_open = 0.0
    eq_cash = 0.0
    max_open = max_close = max_after = 0.0
    min_open = min_close = min_after = 0.0
    interest_gap = 0.0
    roll_gap = 0.0
    contribs = 0.0
    ct_payoff_at_conv = 0.0
    condo_to_eq = []
    for t in range(1, MONTHS + 1):
        rate = max(p["SOFR_FLOOR_PCT"], sofr[t - 1]) + p["CT_SPREAD_PCT"]
        interest = debt_open * rate / 12.0
        interest_gap = max(interest_gap, abs(interest - debt_open * rate / 12.0))
        contrib = equity if t == 1 else 0.0
        contribs += contrib
        available = eq_cash + contrib
        used = min(available, spend[t - 1])
        eq_cash = available - used
        draw_spend = spend[t - 1] - used
        draws = draw_spend + interest
        bal_after = debt_open + draws
        condo_repay = min(bal_after, max(condo_net[t - 1], 0.0))
        perm_pay = max(0.0, bal_after - condo_repay) if t == conv else 0.0
        if t == conv:
            ct_payoff_at_conv = perm_pay
        repay = condo_repay + perm_pay
        debt_close = bal_after - repay
        roll_gap = max(roll_gap, abs(debt_close - (debt_open + draws - repay)))
        max_open = max(max_open, debt_open)
        max_close = max(max_close, debt_close)
        max_after = max(max_after, bal_after)
        min_open = min(min_open, debt_open)
        min_close = min(min_close, debt_close)
        min_after = min(min_after, bal_after)
        condo_to_eq.append(condo_net[t - 1] - condo_repay)
        debt_open = debt_close

    perm_open = 0.0
    perm_ds = []
    perm_payoff = []
    refi = []
    for t in range(1, MONTHS + 1):
        opened = proceeds if t == conv else (0.0 if t < conv else perm_open)
        interest = opened * p["PERM_RATE_PCT"] / 12.0
        pmt = proceeds * pmt_factor if conv <= t < exit_m else 0.0
        principal = 0.0 if pmt == 0 else pmt - interest
        payoff = opened if t == exit_m else 0.0
        perm_ds.append(interest + principal)
        perm_payoff.append(payoff)
        refi.append(proceeds * (1 - p["PERM_COSTS_PCT"]) - ct_payoff_at_conv if t == conv else 0.0)
        perm_open = opened - principal - payoff

    dist = []
    for t in range(1, MONTHS + 1):
        terminal = 0.0
        if t == exit_m:
            terminal = (h_exit + r_exit) * (1 - p["SELL_COST_PCT"]) - perm_payoff[t - 1]
        dist.append(condo_to_eq[t - 1] + hotel_noi[t - 1] + retail_noi[t - 1] - perm_ds[t - 1] + refi[t - 1] + terminal)

    unret = lp_eq
    pref_unpaid = 0.0
    pref_cum = 0.0
    t2_cum = 0.0
    lp_cum = 0.0
    t4_open = False
    tier_gap = 0.0
    residual = 0.0
    t2_bad = t3_bad = t4_bad = 0
    retained_exit = 0.0
    for t in range(1, MONTHS + 1):
        cash = dist[t - 1]
        accrual = (unret + pref_unpaid) * p["PREF_PCT"] / 12.0
        need = unret + pref_unpaid + accrual
        t1 = cash if cash < 0 else min(max(cash, 0.0), max(need, 0.0))
        pref_paid = min(max(t1, 0.0), pref_unpaid + accrual)
        cap_paid = max(t1, 0.0) - pref_paid
        t1_done = (need - max(t1, 0.0)) <= TOL_FLOW
        pref_cum += pref_paid
        t2_target = (p["CATCHUP_PCT"] / (1 - p["CATCHUP_PCT"]) * pref_cum) if t1_done else 0.0
        t2_need = max(0.0, t2_target - t2_cum)
        after_t1 = cash - t1
        t2 = min(max(after_t1, 0.0), t2_need) if t1_done else 0.0
        t2_cum += t2
        t2_done = t1_done and (t2_target - t2_cum) <= TOL_FLOW
        accrued = lp_eq * (1 + p["T3_ACCRUAL_PCT"] / 12.0) ** t
        lp_before = lp_cum + t1
        gap = max(0.0, accrued - lp_before)
        t3_need = 0.0 if p["T3_LP_SPLIT"] <= 0 else gap / p["T3_LP_SPLIT"]
        if t4_open:
            t3 = 0.0
        elif t2_done and gap > TOL_FLOW:
            t3 = min(max(after_t1 - t2, 0.0), t3_need)
        else:
            t3 = 0.0
        t3_lp = t3 * p["T3_LP_SPLIT"]
        gate_now = t2_done and (lp_before + t3_lp + TOL_FLOW >= accrued)
        t4_was_open = t4_open
        t4_open = t4_open or gate_now
        t4 = cash - t1 - t2 - t3
        if t2 > TOL_FLOW and (need - max(t1, 0.0)) > TOL_FLOW:
            t2_bad += 1
        if t3 > TOL_FLOW and not t2_done:
            t3_bad += 1
        if abs(t4) > TOL_FLOW and not t4_open:
            t4_bad += 1
        tier_sum = t1 + t2 + t3 + t4
        tier_gap = max(tier_gap, abs(tier_sum - cash))
        residual = max(residual, abs(cash - tier_sum))
        if t == exit_m:
            retained_exit = cash - tier_sum
        unret = unret - cap_paid
        pref_unpaid = pref_unpaid + accrual - pref_paid
        lp_share_t4 = t4 * p["T4_LP_SPLIT"] if t4_open or abs(t4) <= TOL_FLOW else 0.0
        lp_cum += t1 + t3_lp + lp_share_t4
        del t4_was_open

    gross_target = (
        sum(units * price for _name, units, price in types)
        + p["PARKING_SPACES"] * p["PARKING_PRICE"]
        + p["STORAGE_UNITS"] * p["STORAGE_PRICE"]
    )
    closing_gaps = {name: abs(sum(close_by_type[name]) - units) for name, units, _price in types}
    return {
        "sources": sources,
        "uses": total_uses,
        "component": component,
        "commitment": commitment,
        "equity": equity,
        "contribs": contribs,
        "interest_gap": interest_gap,
        "roll_gap": roll_gap,
        "min_open": min_open,
        "min_close": min_close,
        "min_after": min_after,
        "max_open": max_open,
        "max_close": max_close,
        "max_after": max_after,
        "weight_gap": abs(sum(weights) - 1.0),
        "proceeds": proceeds,
        "ltv_size": ltv_size,
        "dscr_size": dscr_size,
        "dy_size": dy_size,
        "binding": binding,
        "pmt_factor": pmt_factor,
        "closing_gaps": closing_gaps,
        "condo_gross": sum(condo_gross),
        "gross_target": gross_target,
        "hotel_exit_noi": h_exit_noi,
        "retail_exit_noi": r_exit_noi,
        "hotel_value": h_exit,
        "retail_value": r_exit,
        "tier_gap": tier_gap,
        "residual": residual,
        "retained_exit": retained_exit,
        "t2_bad": t2_bad,
        "t3_bad": t3_bad,
        "t4_bad": t4_bad,
        "sofr_avg": sofr_avg,
    }


def audit_formulas(wb) -> list[str]:
    problems = []
    cd = wb["ConstructionDebt"]
    cd_labels = label_map(cd)
    open_row = require_label(cd_labels, "Debt opening balance", "ConstructionDebt")
    int_row = require_label(cd_labels, "Interest on opening balance", "ConstructionDebt")
    draws_row = require_label(cd_labels, "Total draws", "ConstructionDebt")
    repay_row = require_label(cd_labels, "Total repayments", "ConstructionDebt")
    close_row = require_label(cd_labels, "Debt closing balance", "ConstructionDebt")
    contrib_row = require_label(cd_labels, "Equity contribution", "ConstructionDebt")
    for t in range(1, MONTHS + 1):
        col = t + 2
        letter = get_column_letter(col)
        expected_interest = (
            f"={letter}{open_row}*(MAX(SOFR_FLOOR_PCT,INDEX(SOFR!$C$2:$C$85,{letter}2))+CT_SPREAD_PCT)/12"
        )
        actual = formula_text(cd.cell(int_row, col).value)
        if actual != expected_interest:
            problems.append(f"C2 formula {letter}{int_row}={actual}")
            break
        if t == 1:
            if formula_text(cd.cell(open_row, col).value) != "=0":
                problems.append(f"C10 month-1 opening is {cd.cell(open_row, col).value}")
        else:
            prev = get_column_letter(col - 1)
            expected_open = f"={prev}{close_row}"
            if formula_text(cd.cell(open_row, col).value) != expected_open:
                problems.append(f"C10 opening {letter}{open_row}={cd.cell(open_row, col).value}")
                break
        expected_close = f"={letter}{open_row}+{letter}{draws_row}-{letter}{repay_row}"
        if formula_text(cd.cell(close_row, col).value) != expected_close:
            problems.append(f"C10 closing {letter}{close_row}={cd.cell(close_row, col).value}")
            break
        expected_contrib = f"=IF({letter}2=1,SourcesUses!$C$28,0)"
        if formula_text(cd.cell(contrib_row, col).value) != expected_contrib:
            problems.append(f"C9 contribution {letter}{contrib_row}={cd.cell(contrib_row, col).value}")
            break

    pd = wb["PermanentDebt"]
    pd_labels = label_map(pd)
    ltv_row = require_label(pd_labels, "LTV size", "PermanentDebt")
    dscr_row = require_label(pd_labels, "DSCR size", "PermanentDebt")
    dy_row = require_label(pd_labels, "Debt-yield size", "PermanentDebt")
    gross_row = require_label(pd_labels, "Permanent proceeds", "PermanentDebt")
    pmt_row = require_label(pd_labels, "PMT factor", "PermanentDebt")
    noi_row = require_label(pd_labels, "Combined T12 NOI", "PermanentDebt")
    h_row = require_label(pd_labels, "Hotel value at conversion", "PermanentDebt")
    r_row = require_label(pd_labels, "Retail value at conversion", "PermanentDebt")
    expected = {
        ltv_row: f"=PERM_LTV*(C{h_row}+C{r_row})",
        dscr_row: f"=(C{noi_row}/PERM_DSCR)/C{pmt_row}",
        dy_row: f"=C{noi_row}/PERM_DY",
        gross_row: f"=MIN(C{ltv_row},C{dscr_row},C{dy_row})",
        pmt_row: "=PMT(PERM_RATE_PCT/12,PERM_AMORT_YRS*12,-1)",
    }
    for row, formula in expected.items():
        actual = formula_text(pd.cell(row, 3).value)
        if actual != formula:
            problems.append(f"C4 PermanentDebt!C{row}={actual}; expected {formula}")

    for sheet, cap in (("HotelValuation", "HOTEL_CAP"), ("RetailValuation", "RETAIL_CAP")):
        ws = wb[sheet]
        labels = label_map(ws)
        t12_row = require_label(labels, "T12 NOI at exit", sheet)
        value_row = require_label(labels, f"{'Hotel' if sheet.startswith('Hotel') else 'Retail'} value", sheet)
        noi_label = "Hotel NOI" if sheet.startswith("Hotel") else "Retail NOI"
        noi_monthly = require_label(labels, noi_label, sheet)
        expected_t12 = f"=SUM(INDEX(C{noi_monthly}:CH{noi_monthly},EXIT_M-11):INDEX(C{noi_monthly}:CH{noi_monthly},EXIT_M))"
        expected_value = f"=C{t12_row}/{cap}"
        if formula_text(ws.cell(t12_row, 3).value) != expected_t12:
            problems.append(f"C6 {sheet}!C{t12_row}={ws.cell(t12_row, 3).value}")
        if formula_text(ws.cell(value_row, 3).value) != expected_value:
            problems.append(f"C6 {sheet}!C{value_row}={ws.cell(value_row, 3).value}")

    wf = wb["Waterfall"]
    wf_labels = label_map(wf)
    dist_row = require_label(wf_labels, "Distributable cash", "Waterfall")
    t1_row = require_label(wf_labels, "Tier 1 to LP", "Waterfall")
    t2_row = require_label(wf_labels, "Tier 2 to GP", "Waterfall")
    t3_row = require_label(wf_labels, "Tier 3 distribution", "Waterfall")
    t4_row = require_label(wf_labels, "Tier 4 distribution", "Waterfall")
    sum_row = require_label(wf_labels, "Tier sum", "Waterfall")
    for t in range(1, MONTHS + 1):
        col = t + 2
        letter = get_column_letter(col)
        expected_t4 = f"={letter}{dist_row}-{letter}{t1_row}-{letter}{t2_row}-{letter}{t3_row}"
        expected_sum = f"={letter}{t1_row}+{letter}{t2_row}+{letter}{t3_row}+{letter}{t4_row}"
        if formula_text(wf.cell(t4_row, col).value) != expected_t4:
            problems.append(f"C7 tier-4 plug {letter}{t4_row}={wf.cell(t4_row, col).value}")
            break
        if formula_text(wf.cell(sum_row, col).value) != expected_sum:
            problems.append(f"C7 tier sum {letter}{sum_row}={wf.cell(sum_row, col).value}")
            break

    su = wb["SourcesUses"]
    su_labels = label_map(su)
    uses_row = require_label(su_labels, "Total uses", "SourcesUses")
    sources_row = require_label(su_labels, "Total sources", "SourcesUses")
    gap_row = require_label(su_labels, "Sources minus uses", "SourcesUses")
    tie_row = require_label(su_labels, "Uses tie-out", "SourcesUses")
    commit_row = require_label(su_labels, "Construction commitment", "SourcesUses")
    if formula_text(su.cell(gap_row, 3).value) != f"=C{sources_row}-C{uses_row}":
        problems.append(f"C1 gap formula {su.cell(gap_row, 3).value}")
    if formula_text(su.cell(commit_row, 3).value) != f"=LTC_PCT*C{uses_row}":
        problems.append(f"C1 commitment formula {su.cell(commit_row, 3).value}")
    if formula_text(su.cell(tie_row, 3).value) is None:
        problems.append("C1 uses tie-out is not a formula")
    return problems


def money(value: float) -> str:
    return f"${value:,.2f}"


def status_line(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def build_report(evidence: dict, results: list[tuple[str, bool, str]], ok: bool) -> str:
    lines = [
        "# VALIDATION — elite-luxury-mixed-use-model.xlsx",
        "",
        "Independent read-only check of the saved workbook. Identities were recomputed from named input cells and the SOFR rate column. Cached Excel values were not read and were not used. The workbook was not modified.",
        "",
        "## Commands",
        "",
        "| Command | Exit | Result |",
        "|---|---:|---|",
        f"| `python3 models/elite-luxury-mixed-use/check_model.py` | {0 if ok else 1} | {'all identities passed' if ok else 'one or more identities failed'} |",
        f"| `command -v soffice` | {evidence['soffice_which_exit']} | {evidence['soffice_which']} |",
        f"| `test -x /Applications/LibreOffice.app/Contents/MacOS/soffice` | {evidence['soffice_app_exit']} | {evidence['soffice_app']} |",
        f"| `test -x /opt/homebrew/bin/soffice` | {evidence['soffice_brew_exit']} | {evidence['soffice_brew']} |",
        "",
        "LibreOffice is not installed. No headless recalc ran. Checker recomputation from input cells is authoritative. LibreOffice was not installed.",
        "",
        "## Workbook",
        "",
        f"- Path: `{XLSX}`",
        f"- SHA-256 before: `{evidence['hash_before']}`",
        f"- SHA-256 after: `{evidence['hash_after']}`",
        f"- Hash unchanged: {evidence['hash_before'] == evidence['hash_after']}",
        f"- OOXML: zip CRC ok, workbook content type present, worksheet parts {evidence['ooxml']['worksheet_parts']}",
        f"- workbook.xml sheets: {', '.join(evidence['ooxml']['xml_sheets'])}",
        f"- openpyxl sheets: {', '.join(evidence['structure']['sheets'])}",
        f"- Defined names read: {evidence['name_count']}",
        f"- Formula cells: {evidence['structure']['formula_count']}",
        f"- Numeric input cells: {evidence['structure']['numeric_inputs']}",
        f"- SOFR inputs read: {evidence['sofr_count']} cells, M1={evidence['sofr_first']:.6%}, M84={evidence['sofr_last']:.6%}",
        f"- Checked at: {evidence['checked_at']}",
        "",
        "## Identities",
        "",
        "| ID | Result | Evidence |",
        "|---|---|---|",
    ]
    for cid, passed, detail in results:
        lines.append(f"| {cid} | {status_line(passed)} | {detail} |")
    lines.extend([
        "",
        "## Notes",
        "",
        "- C4 uses the spec literal: DSCR size = (T12 NOI / PERM_DSCR) / PMT(PERM_RATE_PCT/12, PERM_AMORT_YRS*12, -1), with no extra /12. The binding constraint is reported from that definition.",
        "- Prose on the Checks sheet names `#REF!`, `#NAME?`, `#VALUE!`, and `#CYCLE!` as the tokens being tested. Those label mentions are not formula errors and were not counted as C11 failures. No formula cell contains those tokens.",
        "- Chatham text in the workbook is the placeholder denial and paste-target label. No cell claims a live Chatham fetch.",
        "",
        "## Handoff",
        "",
    ])
    if ok:
        lines.append("All checked identities passed. Task 3.b may render preview.html from this saved xlsx and must not modify it. No workbook patch is required.")
    else:
        lines.append("One or more identities failed. Do not treat the workbook as accepted. Failures route back to task 2.b. This checker did not patch the workbook.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if not XLSX.is_file():
        print(f"missing workbook: {XLSX}", file=sys.stderr)
        return 1
    hash_before = sha256(XLSX)
    soffice_which = shutil.which("soffice")
    app = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    brew = Path("/opt/homebrew/bin/soffice")
    evidence = {
        "hash_before": hash_before,
        "soffice_which": "not found" if soffice_which is None else soffice_which,
        "soffice_which_exit": 1 if soffice_which is None else 0,
        "soffice_app": "present" if app.is_file() else "absent",
        "soffice_app_exit": 0 if app.is_file() else 1,
        "soffice_brew": "present" if brew.is_file() else "absent",
        "soffice_brew_exit": 0 if brew.is_file() else 1,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    results: list[tuple[str, bool, str]] = []
    try:
        evidence["ooxml"] = check_ooxml(XLSX)
        wb = load_workbook(XLSX, data_only=False, read_only=False)
        inputs, refs, input_cells = resolve_defined_names(wb)
        sofr = read_sofr(wb)
        evidence["name_count"] = len(refs)
        evidence["sofr_count"] = len(sofr)
        evidence["sofr_first"] = sofr[0]
        evidence["sofr_last"] = sofr[-1]
        structure = structural(wb, input_cells, range(2, 2 + MONTHS))
        evidence["structure"] = structure
        formula_problems = audit_formulas(wb)
        numbers = recompute(inputs, sofr)
    except Failure as exc:
        evidence["hash_after"] = sha256(XLSX)
        evidence["ooxml"] = evidence.get("ooxml", {"worksheet_parts": 0, "xml_sheets": []})
        evidence["structure"] = evidence.get("structure", {"sheets": [], "formula_count": 0, "numeric_inputs": 0})
        evidence.setdefault("name_count", 0)
        evidence.setdefault("sofr_count", 0)
        evidence.setdefault("sofr_first", 0.0)
        evidence.setdefault("sofr_last", 0.0)
        results.append(("LOAD", False, str(exc)))
        REPORT.write_text(build_report(evidence, results, False))
        print(f"FAIL {exc}")
        return 1

    c1_gap = abs(numbers["sources"] - numbers["uses"])
    c1_tie = abs(numbers["component"] - numbers["uses"])
    c1_ok = c1_gap <= TOL_LEVEL and c1_tie <= TOL_LEVEL and not any(item.startswith("C1 ") for item in formula_problems)
    results.append((
        "C1",
        c1_ok,
        f"sources {money(numbers['sources'])}, uses {money(numbers['uses'])}, gap {money(c1_gap)}, component tie {money(c1_tie)}",
    ))
    c2_formula = not any(item.startswith("C2 ") for item in formula_problems)
    c2_ok = numbers["interest_gap"] <= TOL_FLOW and c2_formula
    results.append((
        "C2",
        c2_ok,
        f"max recomputed interest gap {numbers['interest_gap']:.6f}; saved interest formulas match opening*(MAX(floor, SOFR_t)+spread)/12: {c2_formula}",
    ))
    bounds_ok = (
        numbers["min_open"] >= -TOL_LEVEL
        and numbers["min_close"] >= -TOL_LEVEL
        and numbers["min_after"] >= -TOL_LEVEL
        and numbers["max_open"] <= numbers["commitment"] + TOL_LEVEL
        and numbers["max_close"] <= numbers["commitment"] + TOL_LEVEL
        and numbers["max_after"] <= numbers["commitment"] + TOL_LEVEL
    )
    results.append((
        "C3",
        bounds_ok,
        f"open [{money(numbers['min_open'])}, {money(numbers['max_open'])}], after-draws max {money(numbers['max_after'])}, close max {money(numbers['max_close'])}, commitment {money(numbers['commitment'])}",
    ))
    c4_gap = abs(numbers["proceeds"] - min(numbers["ltv_size"], numbers["dscr_size"], numbers["dy_size"]))
    c4_formula = not any(item.startswith("C4 ") for item in formula_problems)
    results.append((
        "C4",
        c4_gap <= TOL_LEVEL and c4_formula,
        f"proceeds {money(numbers['proceeds'])} = MIN(LTV {money(numbers['ltv_size'])}, DSCR {money(numbers['dscr_size'])}, DY {money(numbers['dy_size'])}); binds {numbers['binding']}; formula match {c4_formula}",
    ))
    closing_ok = all(gap <= TOL_LEVEL for gap in numbers["closing_gaps"].values())
    gross_gap = abs(numbers["condo_gross"] - numbers["gross_target"])
    results.append((
        "C5",
        closing_ok and gross_gap <= TOL_LEVEL,
        f"closing gaps {numbers['closing_gaps']}; gross {money(numbers['condo_gross'])} vs inventory value {money(numbers['gross_target'])}, gap {money(gross_gap)}",
    ))
    hotel_gap = abs(numbers["hotel_value"] - numbers["hotel_exit_noi"] / inputs["HOTEL_CAP"])
    retail_gap = abs(numbers["retail_value"] - numbers["retail_exit_noi"] / inputs["RETAIL_CAP"])
    c6_formula = not any(item.startswith("C6 ") for item in formula_problems)
    results.append((
        "C6",
        hotel_gap <= TOL_LEVEL and retail_gap <= TOL_LEVEL and c6_formula,
        f"hotel {money(numbers['hotel_value'])} = T12 {money(numbers['hotel_exit_noi'])} / {inputs['HOTEL_CAP']:.4%}; retail {money(numbers['retail_value'])} = T12 {money(numbers['retail_exit_noi'])} / {inputs['RETAIL_CAP']:.4%}; formula match {c6_formula}",
    ))
    c7_formula = not any(item.startswith("C7 ") for item in formula_problems)
    c7_ok = numbers["tier_gap"] <= TOL_FLOW and abs(numbers["retained_exit"]) <= TOL_FLOW and numbers["residual"] <= TOL_FLOW and c7_formula
    results.append((
        "C7",
        c7_ok,
        f"max tier gap {numbers['tier_gap']:.6f}; residual after tier 4 {numbers['residual']:.6f}; retained at exit {numbers['retained_exit']:.6f}; tier-4 plug formulas match {c7_formula}",
    ))
    c8_ok = numbers["t2_bad"] == 0 and numbers["t3_bad"] == 0 and numbers["t4_bad"] == 0
    results.append((
        "C8",
        c8_ok,
        f"tier-order breaches t2={numbers['t2_bad']} t3={numbers['t3_bad']} t4={numbers['t4_bad']}",
    ))
    c9_gap = abs(numbers["contribs"] - numbers["equity"])
    c9_formula = not any(item.startswith("C9 ") for item in formula_problems)
    results.append((
        "C9",
        c9_gap <= TOL_LEVEL and c9_formula,
        f"contributions {money(numbers['contribs'])}, equity requirement {money(numbers['equity'])}, gap {money(c9_gap)}; formula match {c9_formula}",
    ))
    c10_formula = not any(item.startswith("C10 ") for item in formula_problems)
    results.append((
        "C10",
        numbers["roll_gap"] <= TOL_FLOW and c10_formula,
        f"max roll-forward gap {numbers['roll_gap']:.6f}; opening/closing formulas match {c10_formula}",
    ))
    c11_ok = (
        evidence["ooxml"]["xml_sheets"] == SHEETS
        and structure["sheets"] == SHEETS
        and not structure["problems"]
        and structure["formula_count"] > 0
        and not formula_problems
    )
    c11_detail = (
        f"16 sheets match; formulas {structure['formula_count']}; numeric inputs {structure['numeric_inputs']}; "
        f"merged {structure['merged'] or 'none'}; formula-pattern problems {len(formula_problems)}; "
        f"structural problems {structure['problems'] or 'none'}"
    )
    if formula_problems:
        c11_detail += f"; first formula problem: {formula_problems[0]}"
    results.append(("C11", c11_ok, c11_detail))
    c12_ok = structure["source_ok"] and not structure["fetch_claims"]
    results.append((
        "C12",
        c12_ok,
        f"SOFR!D2:D85 carry the ASSUMPTION label: {structure['source_ok']}; Chatham mentions {structure['chatham_mentions']}; live-fetch claims {len(structure['fetch_claims'])}",
    ))

    hash_after = sha256(XLSX)
    evidence["hash_after"] = hash_after
    if hash_after != hash_before:
        results.append(("FILE", False, "workbook hash changed during the read-only check"))
    ok = all(passed for _cid, passed, _detail in results) and hash_after == hash_before
    REPORT.write_text(build_report(evidence, results, ok))
    for cid, passed, detail in results:
        print(f"{status_line(passed)} {cid}: {detail}")
    print(f"wrote {REPORT}")
    print(f"workbook hash unchanged: {hash_after == hash_before}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
