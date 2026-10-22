"""Own funds, risk exposure amounts, capital ratios and the leverage ratio, as COREP cells.

Each function returns {cell: value} for one template, plus the working behind each figure in
`trace`, so every reported number can be explained line by line (docs/REGULATION_NOTES.md).
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import duckdb

from corep import Cell

trace: dict[str, str] = {}


def pct(x: float) -> float:
    """Ratios are reported as decimals to 4 places (decimalsPercentage = 4), rounded half up: 0.05625 -> 0.0563."""
    return float(Decimal(repr(round(x, 10))).quantize(Decimal("0.0001"), ROUND_HALF_UP))  # drop float noise first


def _cell(template: str, row: str, col: str = "0010") -> Cell:
    return (template, row, col)


def gl_sum(con: duckdb.DuckDBPyConnection, accounts: list[str]) -> float:
    q = "SELECT coalesce(sum(amount), 0) FROM general_ledger WHERE account IN (SELECT unnest(?))"
    return float(con.execute(q, [accounts]).fetchone()[0])


# --------------------------------------------------------------------------- operational risk
def operational_risk(con: duckdb.DuckDBPyConnection) -> dict:
    """Business Indicator Component, CRR Art 312-314 (as amended by Regulation (EU) 2024/1623)."""
    h = con.execute("SELECT year, item, amount FROM pl_history").df().pivot(index="year", columns="item", values="amount")
    ildc = min((h.interest_income - h.interest_expense).abs().mean(), 0.0225 * h.interest_earning_assets.mean()) \
        + h.dividend_income.mean()
    sc = max(h.other_operating_income.mean(), h.other_operating_expense.mean()) \
        + max(h.fee_income.mean(), h.fee_expense.mean())
    fc = h.net_trading_book.abs().mean() + h.net_banking_book.abs().mean()
    bi = ildc + sc + fc
    if bi > 1e9:
        raise ValueError("BI above EUR 1bn needs the marginal coefficients of Art 313(2)")
    bic = 0.12 * bi                       # Art 313(1): 12% for BI up to EUR 1bn; ILM = 1 (Art 312(1))
    return {"ildc": ildc, "sc": sc, "fc": fc, "bi": bi, "own_funds_requirement": bic, "rea": 12.5 * bic}


# --------------------------------------------------------------------------- own funds C 01.00
def tier2_amortised(nominal: float, maturity: str, reporting: date) -> float:
    """Art 64: in the final five years the instrument counts pro rata to its remaining days."""
    m = date.fromisoformat(maturity)
    remaining = (m - reporting).days
    five_years = (date(reporting.year + 5, reporting.month, reporting.day) - reporting).days
    return nominal if remaining >= five_years else nominal * max(remaining, 0) / five_years


def own_funds(con: duckdb.DuckDBPyConnection, p: dict) -> dict[Cell, float]:
    t = "C_01.00"
    reporting = date.fromisoformat(p["reporting_date"])
    v: dict[str, float] = {}
    for m in con.execute("SELECT * FROM map_own_funds").df().itertuples():
        if m.source == "gl":
            v[m.c01_row] = -gl_sum(con, m.reference.split())
            trace[f"{t} r{m.c01_row}"] = f"-1 x GL {m.reference} ({m.crr_article})"
        elif m.source == "param":
            v[m.c01_row] = -float(p[m.reference])
            trace[f"{t} r{m.c01_row}"] = f"-{m.reference} from config/srep.yaml ({m.crr_article})"

    # Prudent valuation, simplified approach: 0.1% of assets measured at fair value (FVOCI bonds, GL 1120).
    fair_valued = gl_sum(con, ["1120"])
    v["0290"] = -p["prudent_valuation_simplified"] * fair_valued
    trace[f"{t} r0290"] = f"-0.1% x fair-valued assets {fair_valued:,.0f} (Art 34, 105)"

    # Instruments.
    inst = con.execute("SELECT * FROM capital_instruments").df()
    v["0551"] = float(inst.loc[inst.tier == "AT1", "nominal"].sum())
    t2 = 0.0
    for r in inst[inst.tier == "T2"].itertuples():
        amount = tier2_amortised(r.nominal, r.maturity_date, reporting)
        trace[f"T2 {r.instrument_id}"] = f"{r.nominal:,.0f} -> {amount:,.0f} (Art 64, maturity {r.maturity_date})"
        t2 += amount
    v["0771"] = t2

    # Aggregates exactly as the EBA validation rules define them (v0172, v0182, v0186 ...).
    v["0030"] = v["0040"] + v["0060"]
    v["0150"] = v["0160"] + v["0170"]
    v["0130"] = v["0140"] + v["0150"]
    v["0250"] = v["0290"]
    v["0300"] = v["0310"]
    v["0340"] = v["0350"] + v["0360"]

    # DTA from temporary differences: deducted only above 10% of CET1 after the other deductions (Art 48(1)(a)).
    cet1_before_threshold = v["0030"] + v["0130"] + v["0180"] + v["0200"] + v["0250"] + v["0300"] + v["0340"] + v["0370"]
    dta_temp = gl_sum(con, ["1820"])
    excess = max(0.0, dta_temp - 0.10 * cet1_before_threshold)
    v["0490"] = -excess
    trace[f"{t} r0490"] = (f"DTA temporary differences {dta_temp:,.0f} vs 10% of CET1 {0.10 * cet1_before_threshold:,.0f}: "
                           f"deduct {excess:,.0f}; the rest is risk-weighted at 250% (Art 48(4))")
    v["0020"] = cet1_before_threshold + v["0490"]
    v["0540"] = v["0551"]
    v["0530"] = v["0540"]
    v["0760"] = v["0771"]
    v["0750"] = v["0760"]
    v["0015"] = v["0020"] + v["0530"]
    v["0010"] = v["0015"] + v["0750"]
    return {_cell(t, r): round(x) for r, x in v.items()}


def deductions_from_tier1(of: dict[Cell, float]) -> float:
    """Asset amounts deducted from Tier 1, needed again by the leverage ratio (C 47.00 r0270)."""
    rows = ["0290", "0310", "0340", "0370", "0490"]
    return sum(of[("C_01.00", r, "0010")] for r in rows)


# --------------------------------------------------------------------------- RWEA C 02.00
SA_ROWS = ["0070", "0080", "0090", "0100", "0110", "0120", "0125", "0131", "0140", "0150", "0160",
           "0171", "0180", "0190", "0200", "0210", "0211"]


def risk_exposure_amounts(con: duckdb.DuckDBPyConnection, opr: dict, columns: dict[str, set[str]]) -> dict[Cell, float]:
    t = "C_02.00.a"
    credit = dict(con.execute("SELECT row, rwea FROM c02_credit").fetchall())
    v = {r: credit.get(r, 0.0) for r in SA_ROWS}
    v["0151"], v["0152"] = credit.get("0151", 0.0), credit.get("0152", 0.0)
    v["0150"] = v["0151"] + v["0152"]
    v["0060"] = sum(v[r] for r in SA_ROWS)
    v["0050"] = v["0060"]                  # no securitisation positions
    v["0040"] = v["0050"]                  # no IRB, no default-fund contributions
    v["0590"] = opr["rea"]
    v["0010"] = v["0040"] + v["0590"]       # no market risk, settlement or CVA (no trading book, no derivatives)
    cells = {}
    for row, x in v.items():
        # Standardised-only bank: the output-floor S-TREA (c0020) equals TREA wherever the template has the cell.
        for col in sorted(columns.get(row, {"0010"})):
            cells[_cell(t, row, col)] = round(x)
    return cells


# --------------------------------------------------------------------------- ratios C 03.00
def capital_ratios(of: dict[Cell, float], rea: dict[Cell, float], p: dict) -> dict[Cell, float]:
    t = "C_03.00"
    trea = rea[("C_02.00.a", "0010", "0010")]
    cet1, t1, tc = (of[("C_01.00", r, "0010")] for r in ("0020", "0015", "0010"))
    pr, p2r, share = p["pillar1"], p["p2r"], p["p2r_share"]
    cbr = sum(p["combined_buffer"].values())
    tscr = pr["total"] + p2r
    tscr_cet1 = pr["cet1"] + share["cet1"] * p2r
    tscr_t1 = pr["tier1"] + share["tier1"] * p2r
    ratios = {
        "0010": cet1 / trea, "0030": t1 / trea, "0050": tc / trea,
        "0070": cet1 / trea, "0080": t1 / trea, "0090": tc / trea,          # unfloored = floored (SA only)
        "0330": cet1 / trea, "0340": t1 / trea, "0350": tc / trea,          # no transitional provisions applied
        "0360": cet1 / trea, "0370": t1 / trea, "0380": tc / trea,
        "0130": tscr, "0140": tscr_cet1, "0150": tscr_t1,
        "0151": tscr, "0152": tscr_cet1, "0153": tscr_t1,                   # no Art 104a(6) cap applies
        "0160": tscr + cbr, "0170": tscr_cet1 + cbr, "0180": tscr_t1 + cbr,
        "0190": tscr + cbr + p["p2g"], "0200": tscr_cet1 + cbr + p["p2g"], "0210": tscr_t1 + cbr + p["p2g"],
    }
    amounts = {
        "0020": cet1 - pr["cet1"] * trea,
        "0040": t1 - pr["tier1"] * trea,
        "0060": tc - pr["total"] * trea,
        # CET1 left after meeting the CET1 part of TSCR, the CET1 needed to cover any AT1/T2 shortfall
        # against TSCR, and the combined buffer requirement (Art 92 CRR, Art 104a and 141 CRD).
        "0220": cet1 - tscr_cet1 * trea
                - max(0.0, (tscr_t1 - tscr_cet1) * trea - (t1 - cet1))
                - max(0.0, (tscr - tscr_t1) * trea - (tc - t1))
                - cbr * trea,
    }
    cells = {_cell(t, r): pct(x) for r, x in ratios.items()}
    cells.update({_cell(t, r): round(x) for r, x in amounts.items()})
    return cells


# --------------------------------------------------------------------------- leverage C 47.00
def leverage_ratio(con: duckdb.DuckDBPyConnection, of: dict[Cell, float], p: dict) -> dict[Cell, float]:
    t = "C_47.00"
    v: dict[str, float] = {}
    # On-balance sheet: every asset at its accounting value (net of specific provisions) - Art 429b(1).
    v["0190"] = gl_sum(con, [r[0] for r in con.execute(
        "SELECT account FROM general_ledger WHERE statement = 'BS' AND class = 'asset'").fetchall()])
    trace[f"{t} r0190"] = "Total assets on the balance sheet (all asset GL accounts, net of allowances)"
    # Off-balance sheet items at their leverage-ratio CCF (Art 429f).
    for row, value in con.execute(
            "SELECT c47_row, sum(nominal_amount * lr_ccf) FROM off_balance_rwa GROUP BY 1").fetchall():
        v[row] = value
    # Assets already deducted from Tier 1 are taken out of the exposure measure (C 47.00 r0270/r0280): same amount, negative.
    v["0270"] = deductions_from_tier1(of)
    v["0280"] = v["0270"]
    exposure_rows = ["0150", "0160", "0165", "0170", "0180", "0190"]
    v["0290"] = sum(v.get(r, 0.0) for r in exposure_rows) + v["0270"]
    v["0300"] = sum(v.get(r, 0.0) for r in exposure_rows) + v["0280"]
    t1 = of[("C_01.00", "0015", "0010")]
    v["0310"] = v["0320"] = t1
    lr = p["leverage"]
    ratios = {
        "0330": t1 / v["0290"], "0340": t1 / v["0300"],
        "0410": lr["pillar1"],
        "0420": lr["pillar1"] + lr["p2r"], "0430": 0.0,
        "0440": lr["pillar1"] + lr["p2r"] + lr["gsii_buffer"],
        "0450": lr["pillar1"] + lr["p2r"] + lr["gsii_buffer"] + lr["p2g"],
        "0460": 0.0, "0470": lr["pillar1"] + lr["p2r"] + lr["gsii_buffer"] + lr["p2g"],
    }
    amounts = {"0350": 0.0, "0360": 0.0, "0370": 0.0, "0380": 0.0, "0390": 0.0, "0400": 0.0}
    cells = {_cell(t, r): round(x) for r, x in v.items()}
    cells.update({_cell(t, r): round(x) for r, x in amounts.items()})
    cells.update({_cell(t, r): pct(x) for r, x in ratios.items()})
    return cells
