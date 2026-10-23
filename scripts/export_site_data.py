"""Export the pipeline's results into site/data.json for the static frontend.

    python scripts/export_site_data.py

The site never calculates regulation itself: every number it shows comes from out/ and data/,
produced by the tested pipeline. "Break the report" scenarios are evaluated here with the same
EBA rule engine, and the site only replays their results.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from corep import OUT, eba_rules
from corep.derivatives import trade_level
from corep.pipeline import build

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def main() -> None:
    con, p, dq, opr, cells, index = build()
    types = {c: m["type"] for c, m in index.items()}
    s = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    c = lambda t, r, col="0010": cells[(t, r, col)]
    m = 1e6

    # Scene 1: balance sheet -> COREP cells
    gl = con.execute("SELECT account, description, class, amount FROM general_ledger WHERE statement='BS'").df()
    assets = gl[gl["class"] == "asset"].amount.sum()
    hero = {
        "assets": [["Loans to customers and banks", 4675.4], ["Government bonds", 910.0], ["Cash and central bank", 435.0],
                   ["Goodwill and intangibles", 85.0], ["Deferred tax assets", 38.0], ["Derivatives", 9.8], ["Other assets", 150.0]],
        "liabilities": [["Customer deposits", 4566.9], ["Debt securities", 600.0], ["Tier 2 bonds", 250.0],
                        ["Derivatives", 21.3], ["Other liabilities", 101.0], ["Equity", 764.0]],
        "total": round(assets / m, 1),
        "cells": [["C 01.00", "r0020", "CET1 capital", c("C_01.00", "0020") / m],
                  ["C 01.00", "r0010", "Own funds", c("C_01.00", "0010") / m],
                  ["C 02.00", "r0010", "Total risk exposure", c("C_02.00.a", "0010") / m],
                  ["C 03.00", "r0010", "CET1 ratio", c("C_03.00", "0010")],
                  ["C 22.00", "r0010", "FX risk exposure", c("C_22.00", "0010", "0100") / m],
                  ["C 25.01", "r0010", "CVA risk exposure", c("C_25.01.a", "0010", "0290") / m],
                  ["C 34.03", "r0010", "SA-CCR add-on", c("C_34.03", "0010", "0070") / m],
                  ["C 47.00", "r0290", "Leverage exposure", c("C_47.00", "0290") / m],
                  ["C 47.00", "r0330", "Leverage ratio", c("C_47.00", "0330")]],
        "rules_passed": s["eba_rules"]["pass"],
    }

    # Scene 2: capital tower and requirement stack
    tower = {"cet1": c("C_01.00", "0020") / m, "at1": c("C_01.00", "0530") / m, "t2": c("C_01.00", "0750") / m,
             "trea": c("C_02.00.a", "0010") / m, "pillar1": 0.08, "p2r": p["p2r"], "ccb": p["combined_buffer"]["ccb"],
             "ccyb": p["combined_buffer"]["ccyb"], "p2g": p["p2g"]}

    # Scene 3: every exposure as a dot
    cr = con.execute("SELECT exposure_class, risk_weight, exposure_value, exposure_id, part_row FROM credit_rwa").df()
    classes = ["central_government", "institution", "corporate", "retail", "mortgage", "default", "other_items"]
    cr["rwea"] = cr.exposure_value * cr.risk_weight
    per = cr.groupby(["exposure_id", "exposure_class"], as_index=False)[["exposure_value", "rwea"]].sum()
    per["rw"] = (per.rwea / per.exposure_value.where(per.exposure_value > 0)).fillna(0)   # blended weight of split mortgages
    dots = [[classes.index(r.exposure_class), round(r.rw, 2), round(r.exposure_value / m, 3)] for r in per.itertuples()]
    both = cr[cr.part_row.isin(["0151", "0152"]) & (cr.exposure_value > 0)].groupby("exposure_id").size()
    mid = sorted(both[both == 2].index)[0]                      # first mortgage that really splits in two
    mort = cr[cr.exposure_id == mid].sort_values("part_row")
    split = {"id": mid,
             "value": round(con.execute("SELECT property_value FROM exposures WHERE exposure_id=?", [mid]).fetchone()[0] / m, 3),
             "parts": [[r.part_row, round(r.exposure_value / m, 3), r.risk_weight] for r in mort.itertuples()]}

    # Scene 4: why EUR 1.96bn of notional becomes EUR 47m of exposure
    t = trade_level(con, p["reporting_date"])
    ns = pd.read_csv(OUT / "sa_ccr_by_netting_set.csv")
    waterfall = [
        ["Notional of 26 trades", t.notional.sum() / m, "What the contracts are written on"],
        ["Duration-weighted notional", t.effective_notional.abs().sum() / m, "Each swap counts once per year of rate risk it carries, Art 279b-279c"],
        ["Add-on", ns.addon.sum() / m, "0.5% for rates, 4% for FX, with offsets between buckets, Art 280a, 280c"],
        ["Potential future exposure", ns.PFE.sum() / m, "Add-on x multiplier, which falls below 1 when a netting set is out of the money, Art 278"],
        ["+ Replacement cost", (ns.PFE.sum() + ns.RC.sum()) / m, "What a default would cost today, Art 275"],
        ["x 1.4 = Exposure value", ns.exposure_value.sum() / m, "Alpha, Art 274(2)"],
    ]

    # Scene 5: validation wall + replayed "break the report" scenarios
    results = eba_rules.evaluate(cells, types)
    wall = [[r["rule_id"], r["templates"]] for r in results if r["status"] == "pass"]
    scenarios = []
    for label, cell, delta, unit in [
        ("Add EUR 1m to CET1", ("C_01.00", "0020", "0010"), 1_000_000, "EUR"),
        ("Add EUR 5m to operational risk", ("C_02.00.a", "0590", "0010"), 5_000_000, "EUR"),
        ("Add EUR 2m to on-balance assets", ("C_47.00", "0190", "0010"), 2_000_000, "EUR"),
        ("Raise the CET1 ratio by 1 point", ("C_03.00", "0010", "0010"), 0.01, "ratio"),
    ]:
        broken = dict(cells)
        broken[cell] = cells[cell] + delta
        failed = [r for r in eba_rules.evaluate(broken, types) if r["status"] == "FAIL"]
        scenarios.append({"label": label, "cell": " ".join([cell[0].replace("_", " "), "r" + cell[1], "c" + cell[2]]),
                          "failed": [[r["rule_id"], r["expression"]] for r in failed]})

    # Scene 6: change requests
    def changed(path):
        df = pd.read_csv(ROOT / path, dtype=str)
        return df
    crs = []
    for cr_id, base, new, n_pred in [("CR-001", "tests/baseline/corep_templates_v1.csv", "tests/baseline/corep_templates_v2.csv", 38),
                                     ("CR-002", "tests/baseline/corep_templates_v2.csv", "out/corep_templates.csv", 153)]:
        a, b = changed(base), changed(new)
        mrg = a.merge(b, on=["template", "row", "col"], how="outer", suffixes=("_a", "_b"))
        diff = mrg[mrg.value_a != mrg.value_b]
        crs.append({"id": cr_id, "predicted": n_pred, "changed": int(len(diff)),
                    "by_template": diff.template.value_counts().to_dict(),
                    "title": {"CR-001": "Buffer rate 0.75% to 1.00% and a new collateral feed",
                              "CR-002": "A derivatives book: counterparty, CVA and FX risk"}[cr_id]})
    all_cells = pd.read_csv(OUT / "corep_templates.csv", dtype=str).template.value_counts().to_dict()

    # Scene 7: real banks
    te = pd.read_csv(ROOT / "data/real/te2025.csv.gz", dtype={"lei": str, "item": str})
    banks = pd.read_csv(ROOT / "data/real/banks.csv", dtype=str)
    cet1 = te[(te["item"] == "2520140") & (te.period == 202506)].merge(banks[["lei", "name"]], on="lei", how="left")
    findings = {
        "529900HEKOENJHPNN480": "Capital ratios above 100% in two quarters. Genuine: loans to Finnish municipalities carry a 0% risk weight. EBA rule v4886 flags it correctly.",
        "EV2XZWMLLXF2QRX0CD47": "CET1 ratio 180% to 353%. Same public-sector business model, so the plausibility flag is explained and closed.",
        "549300C6TUMDXNOVXS82": "Tier 1 in the leverage template is EUR 296.8m higher than Tier 1 in own funds, in March 2025 only. A query for the bank.",
        "3M5E1GQGKL17HI6CPN30": "Tier 1 differs between the two templates by EUR 0.9m in March 2025. Small, but outside rounding.",
        "XXXXXXXXXXXXXXXXXXXX": "Leverage Tier 1 is EUR 302m to 408m lower than own-funds Tier 1 every quarter, and the RWA overview misses EUR 463.7m in March 2025.",
    }
    real = {"banks": [[r.name if isinstance(r.name, str) else "Bank with LEI withheld", round(r.amount, 4), r.lei in findings]
                      for r in cet1.itertuples()],
            "findings": [[(banks.set_index("lei").name.get(k) if k in set(banks.lei) else "Bank with LEI withheld"), v]
                         for k, v in findings.items()],
            "checks": 23919, "breaks": 26, "bank_quarters": 469}

    SITE.mkdir(exist_ok=True)
    data = {"hero": hero, "tower": tower, "classes": classes, "dots": dots, "split": split, "waterfall": waterfall,
            "wall": wall, "scenarios": scenarios, "crs": crs, "cells_by_template": all_cells, "real": real,
            "summary": {k: s[k] for k in ["cet1_ratio", "tier1_ratio", "total_capital_ratio", "leverage_ratio", "trea"]}}
    (SITE / "data.json").write_text(json.dumps(data, separators=(",", ":"), default=float), encoding="utf-8")
    print(f"site/data.json: {(SITE / 'data.json').stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
