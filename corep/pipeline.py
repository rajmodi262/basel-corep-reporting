"""End-to-end run: books -> data quality -> credit risk SQL -> own funds, RWEA, ratios, leverage
-> reconciliations -> EBA validation rules -> xBRL-CSV packages and readable templates.

    python -m corep.pipeline
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

from corep import OUT, Cell, capital, derivatives, eba_rules, quality, reconcile
from corep.books import connect, params, run_sql
from corep.xbrl_csv import HEADER, datapoint_index, write_packages


def build(data_dir=None):
    con = connect(data_dir) if data_dir else connect()
    p = params()
    run_sql(con, "05_collateral.sql")
    dq = quality.run(con)
    blocking = dq[(dq.severity == "BLOCK") & (dq.hits > 0)]
    if not blocking.empty:
        raise SystemExit("Blocking data-quality failures:\n" + blocking.to_string())
    run_sql(con, "10_credit_risk.sql")

    index = datapoint_index()
    columns: dict[str, set[str]] = defaultdict(set)
    for t, r, c in index:
        if t == "C_02.00.a":
            columns[r].add(c)

    capital.trace.clear()
    opr = capital.operational_risk(con)
    cells: dict[Cell, float] = {}
    of = capital.own_funds(con, p)
    trades = derivatives.trade_level(con, p["reporting_date"])
    ns = derivatives.netting_sets(trades, derivatives.risk_weight_lookup(con))
    con.register("netting_sets_df", ns)
    con.execute("CREATE OR REPLACE TABLE netting_sets AS SELECT * FROM netting_sets_df")
    ccr_rows = {"0120" if ct == "institution" else "0125": g.rwea.sum() for ct, g in ns.groupby("counterparty_type")}
    cva_cells, cva_rea = derivatives.cva(ns, trades)
    fx_cells, fx_rea = derivatives.fx_risk(con, trades, of[("C_01.00", "0010", "0010")])
    rea = capital.risk_exposure_amounts(con, opr, columns, ccr_rows, fx_rea, cva_rea)
    cells.update(of)
    cells.update(rea)
    cells.update(capital.capital_ratios(of, rea, p))
    cells.update(capital.leverage_ratio(con, of, p, ns))
    cells.update(derivatives.c34_01(con))
    cells.update(derivatives.c34_03(trades, ns))
    cells.update(cva_cells)
    cells.update(fx_cells)
    cells.update(HEADER)
    dropped = [c for c in cells if c not in index]
    if dropped:
        raise KeyError(f"calculated cells that the EBA taxonomy does not define: {dropped}")
    return con, p, dq, opr, cells, index


def readable(cells: dict[Cell, float], index: dict) -> pd.DataFrame:
    rows = [{"template": t, "row": r, "col": c, "label": index[(t, r, c)]["row_label"],
             "value": v, "datapoint": index[(t, r, c)]["datapoint"]} for (t, r, c), v in sorted(cells.items())]
    return pd.DataFrame(rows)


def main(out: Path = OUT) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    con, p, dq, opr, cells, index = build()
    rec = reconcile.run(con, cells, opr)
    types = {c: m["type"] for c, m in index.items()}
    rules = pd.DataFrame(eba_rules.evaluate(cells, types))
    packages = write_packages(cells, p, out)

    dq.to_csv(out / "data_quality.csv", index=False, lineterminator="\n")
    rec.to_csv(out / "reconciliation.csv", index=False, lineterminator="\n")
    rules[["rule_id", "templates", "status", "expression", "detail"]].to_csv(
        out / "eba_validation_results.csv", index=False, lineterminator="\n")
    readable(cells, index).to_csv(out / "corep_templates.csv", index=False, lineterminator="\n")
    con.execute("SELECT * FROM credit_rwa ORDER BY exposure_id, part_row").df().to_csv(
        out / "credit_risk_by_exposure.csv", index=False, lineterminator="\n")
    con.execute("SELECT * FROM netting_sets ORDER BY netting_set").df().round(2).to_csv(
        out / "sa_ccr_by_netting_set.csv", index=False, lineterminator="\n")
    (out / "calculation_trace.json").write_text(json.dumps(capital.trace, indent=1), encoding="utf-8")

    c = lambda t, r: cells[(t, r, "0010")]
    summary = {
        "reporting_date": p["reporting_date"],
        "total_assets": round(capital.gl_sum(con, [r[0] for r in con.execute(
            "SELECT account FROM general_ledger WHERE statement='BS' AND class='asset'").fetchall()])),
        "cet1": c("C_01.00", "0020"), "tier1": c("C_01.00", "0015"), "own_funds": c("C_01.00", "0010"),
        "trea": c("C_02.00.a", "0010"), "credit_rwea": c("C_02.00.a", "0040"), "op_risk_rea": c("C_02.00.a", "0590"),
        "cet1_ratio": c("C_03.00", "0010"), "tier1_ratio": c("C_03.00", "0030"), "total_capital_ratio": c("C_03.00", "0050"),
        "ocr": c("C_03.00", "0160"), "cet1_surplus_over_requirements": c("C_03.00", "0220"),
        "leverage_exposure": c("C_47.00", "0290"), "leverage_ratio": c("C_47.00", "0330"),
        "ccr_exposure_value": round(float(con.execute("SELECT sum(exposure_value) FROM netting_sets").fetchone()[0])),
        "ccr_rwea": round(float(con.execute("SELECT sum(rwea) FROM netting_sets").fetchone()[0])),
        "market_risk_rea": c("C_02.00.a", "0520"), "cva_rea": c("C_02.00.a", "0640"),
        "business_indicator": round(opr["bi"]),
        "cells_reported": len(cells),
        "data_quality": {r.rule_id: int(r.hits) for r in dq.itertuples()},
        "reconciliations": f"{(rec.status == 'RECONCILED').sum()}/{len(rec)} reconciled",
        "eba_rules": rules.status.value_counts().to_dict(),
        "packages": [x.name for x in packages],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=float), encoding="utf-8")
    return summary


if __name__ == "__main__":
    s = main()
    print(json.dumps(s, indent=1, default=float))
    sys.exit(0 if s["eba_rules"].get("FAIL", 0) == 0 else 1)
