"""Reconciliations between the accounting books and the regulatory report.

A COREP report is only trusted if it ties back to the general ledger. Each check states what is
compared, both amounts, and the difference.
"""

from __future__ import annotations

import duckdb
import pandas as pd

from corep import Cell
from corep.capital import gl_sum


def run(con: duckdb.DuckDBPyConnection, cells: dict[Cell, float], opr: dict) -> pd.DataFrame:
    checks = []

    def add(check_id: str, what: str, left: float, right: float, tolerance: float = 0.5) -> None:
        checks.append({"check_id": check_id, "check": what, "left": round(left, 2), "right": round(right, 2),
                       "difference": round(left - right, 2),
                       "status": "RECONCILED" if abs(left - right) <= tolerance else "BREAK"})

    # REC-01: sub-ledger to GL, account by account (gross amounts and the allowance).
    sub = con.execute("SELECT gl_account, sum(gross_amount) FROM exposures GROUP BY 1 ORDER BY 1").fetchall()
    for account, amount in sub:
        add(f"REC-01/{account}", f"Risk sub-ledger vs GL account {account}", float(amount), gl_sum(con, [account]))
    prov = float(con.execute("SELECT sum(specific_provision) FROM exposures").fetchone()[0])
    add("REC-01/1590", "Specific provisions in sub-ledger vs GL loan-loss allowance", -prov, gl_sum(con, ["1590"]))

    # REC-02: trial balance is balanced.
    add("REC-02", "Trial balance: debits = credits", gl_sum(con, [r[0] for r in con.execute(
        "SELECT account FROM general_ledger").fetchall()]), 0.0)

    # REC-03: every exposure went through classification exactly once and kept its full value.
    n_in = con.execute("SELECT count(*) FROM exposures").fetchone()[0]
    n_out = con.execute("SELECT count(DISTINCT exposure_id) FROM credit_rwa").fetchone()[0]
    add("REC-03a", "Exposures in = exposures risk-weighted", n_in, n_out, 0)
    ev_in = con.execute("SELECT sum(gross_amount - specific_provision) FROM exposures").fetchone()[0]
    ev_out = con.execute("SELECT sum(exposure_value) FROM credit_rwa").fetchone()[0]
    add("REC-03b", "Net exposure value in = sum of risk-weighted parts (incl. mortgage split)", ev_in, ev_out)

    # REC-04: balance sheet total assets, less derivatives (measured by SA-CCR), = C 47.00 r0190.
    assets = gl_sum(con, [r[0] for r in con.execute(
        "SELECT account FROM general_ledger WHERE statement='BS' AND class='asset'").fetchall()])
    derivative_assets = gl_sum(con, ["1150"])
    add("REC-04", "Total assets (GL) less derivative assets vs C 47.00 r0190 on-balance exposures",
        assets - derivative_assets, cells[("C_47.00", "0190", "0010")])

    # REC-05: every asset is either risk-weighted as credit risk, deducted from CET1, or a derivative
    #   (counterparty credit risk). Nothing is missed and nothing is counted twice.
    deducted_assets = gl_sum(con, ["1600", "1610", "1620", "1810"])
    add("REC-05", "Total assets = credit exposure value + assets deducted from CET1 + derivative assets",
        assets, float(ev_out) + deducted_assets + derivative_assets)

    # REC-09: derivative fair values in the GL = trade-level market values (CR-002).
    mtm = con.execute("SELECT sum(CASE WHEN mtm_2025_12_31 > 0 THEN mtm_2025_12_31 END), "
                      "sum(CASE WHEN mtm_2025_12_31 < 0 THEN mtm_2025_12_31 END) FROM derivatives").fetchone()
    add("REC-09a", "Positive trade market values vs GL 1150 derivative assets", float(mtm[0]), derivative_assets)
    add("REC-09b", "Negative trade market values vs GL 2150 derivative liabilities", float(mtm[1]), gl_sum(con, ["2150"]))

    # REC-10: C 34.03 notional and trade count = the derivatives book.
    n, notional = con.execute("SELECT count(*), sum(notional) FROM derivatives").fetchone()
    add("REC-10a", "Trades in the book vs C 34.03 r0010 number of transactions", n, cells[("C_34.03", "0010", "0030")], 0)
    add("REC-10b", "Notional in the book vs C 34.03 r0010 notional", float(notional), cells[("C_34.03", "0010", "0040")])

    # REC-11: C 22.00 USD long position = USD exposures in the credit sub-ledger.
    usd = con.execute("SELECT sum(gross_amount - specific_provision) FROM exposures WHERE currency = 'USD'").fetchone()[0]
    add("REC-11", "USD exposures in the sub-ledger vs C 22.00 USD long position (on-balance part)",
        float(usd), cells[("C_22.00", "0100", "0020")])

    # REC-06: equity in the GL bridges to CET1 + AT1 before regulatory adjustments.
    equity = -gl_sum(con, [r[0] for r in con.execute(
        "SELECT account FROM general_ledger WHERE statement='BS' AND class='equity'").fetchall()])
    profit = -gl_sum(con, [r[0] for r in con.execute("SELECT account FROM general_ledger WHERE statement='PL'").fetchall()])
    of = lambda r: cells[("C_01.00", r, "0010")]
    regulatory = of("0030") + of("0140") + of("0160") + of("0180") + of("0200") + of("0551")
    add("REC-06", "Balance-sheet equity incl. profit vs own-funds items before filters and deductions",
        equity + profit, regulatory)

    # REC-07: 2025 business-indicator inputs equal the 2025 P&L in the GL.
    h = con.execute("SELECT item, amount FROM pl_history WHERE year = 2025").df().set_index("item").amount
    pairs = [("interest_income", "4000", -1), ("interest_expense", "4100", 1), ("dividend_income", "4200", -1),
             ("fee_income", "4300", -1), ("fee_expense", "4400", 1), ("other_operating_income", "4600", -1),
             ("other_operating_expense", "5300", 1), ("net_banking_book", "4500", -1)]
    for item, account, sign in pairs:
        add(f"REC-07/{item}", f"Business indicator 2025 {item} vs GL {account}", float(h[item]), sign * gl_sum(con, [account]))

    # REC-08: C 02.00 credit RWEA = sum of loan-level RWEA.
    loan_level = con.execute("SELECT sum(exposure_value * risk_weight) FROM credit_rwa").fetchone()[0] \
        + con.execute("SELECT sum(exposure_value * risk_weight) FROM off_balance_rwa").fetchone()[0] \
        + con.execute("SELECT sum(rwea) FROM netting_sets").fetchone()[0]
    add("REC-08", "C 02.00 r0060 vs loan-level RWEA + netting-set CCR RWEA", cells[("C_02.00.a", "0060", "0010")],
        loan_level, 1.0)
    return pd.DataFrame(checks)
