"""CR-003: run the EBA's validation rules on REAL banks' figures.

Source: EBA 2025 EU-wide Transparency Exercise (data/real/te2025.csv.gz) - 120 EU banks, four
quarters (Sep 2024 - Jun 2025), taken from their own COREP submissions. Amounts in EUR millions.

Two layers of checks:

1. EBA validation rules, unchanged: each published item is placed in its COREP cell
   (config/te_item_map.csv), and a rule is run for a bank-quarter only when EVERY cell the rule
   uses is published. Rules touching unpublished cells are not run, so nothing fails for lack of data.
2. Transparency-level checks (config/te_checks.csv): the same EBA rules restated over published
   aggregates (e.g. intangibles are published as r0300 + r0340 together), plus cross-template ties.

Numbers are compared as intervals: each published amount stands for +/- EUR 0.5k (COREP decimals -3),
each ratio for +/- 0.00005, exactly as the EBA formula engine does.
"""

from __future__ import annotations

import re

import pandas as pd

from corep import CONFIG, DATA, OUT, TAXONOMY
from corep.eba_rules import CELL, Iv, load_rules, to_python

REAL = DATA / "real"
ITEM = re.compile(r"\{(\d{7})\}")


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    te = pd.read_csv(REAL / "te2025.csv.gz", dtype={"lei": str, "item": str})
    te = te.dropna(subset=["amount"])
    banks = pd.read_csv(REAL / "banks.csv", dtype=str)
    m = pd.read_csv(CONFIG / "te_item_map.csv", dtype=str)
    return te, banks, m


def interval(value: float, ratio: bool) -> Iv:
    if ratio:
        return Iv(value - 0.00005, value + 0.00005)
    eur = value * 1e6
    return Iv(eur - 500, eur + 500)


def bank_quarters(te: pd.DataFrame):
    for (lei, period), g in te.groupby(["lei", "period"]):
        yield lei, int(period), dict(zip(g["item"], g["amount"]))


def run_eba_rules(te: pd.DataFrame, m: pd.DataFrame) -> pd.DataFrame:
    single = m.dropna(subset=["template"])
    cell_of = {r.item: (r.template, r.row, r.col) for r in single.itertuples()}
    item_of = {v: k for k, v in cell_of.items()}
    types = pd.read_csv(TAXONOMY / "datapoints.csv", dtype=str)
    ratio = {(r.template, r.row, r.col) for r in types.itertuples() if r.type == "p"}
    rules = [r for r in load_rules() if "empty(" not in r["expression"]
             and all(c in item_of for c in CELL.findall(r["expression"]))]
    out = []
    for lei, period, values in bank_quarters(te):
        cells = {cell_of[i]: interval(v, cell_of[i] in ratio) for i, v in values.items() if i in cell_of}
        env = {"v": lambda t, r, c: cells[(t, r, c)], "abs": abs,
               "sum": lambda *xs: sum((Iv.of(x) for x in xs), Iv(0.0, 0.0)), "True": True, "False": False}
        for rule in rules:
            refs = CELL.findall(rule["expression"])
            if not all(c in cells for c in refs):
                continue
            ok = bool(eval(to_python(rule["expression"]), {"__builtins__": {}}, env))  # noqa: S307
            out.append({"lei": lei, "period": period, "check_id": rule["rule_id"], "basis": "EBA validation rule",
                        "expression": rule["expression"], "status": "pass" if ok else "BREAK",
                        "difference_eur_m": _difference(rule["expression"], cells, ratio)})
    return pd.DataFrame(out)


def _difference(expr: str, cells: dict, ratio: set) -> float | None:
    """Left minus right for an equality, in EUR m (or ratio points), from the interval midpoints."""
    if " = " not in expr or "if " in expr:
        return None
    left, right = expr.split(" = ", 1)
    mid = lambda e: eval(to_python(e), {"__builtins__": {}},  # noqa: S307
                         {"v": lambda t, r, c: (cells[(t, r, c)].lo + cells[(t, r, c)].hi) / 2, "abs": abs, "sum": lambda *x: sum(x)})
    try:
        d = mid(left) - mid(right)
    except Exception:
        return None
    is_ratio = any(c in ratio for c in CELL.findall(expr))
    return round(d if is_ratio else d / 1e6, 6)


def run_te_checks(te: pd.DataFrame) -> pd.DataFrame:
    checks = pd.read_csv(CONFIG / "te_checks.csv", dtype=str)
    out = []
    for lei, period, values in bank_quarters(te):
        for c in checks.itertuples():
            items = ITEM.findall(c.expression)
            lhs = ITEM.findall(c.expression.split("=")[0].split("<=")[0])
            if not all(i in values for i in lhs) or not any(i in values for i in items if i not in lhs):
                continue                               # the total and at least one part must be published
            expr = ITEM.sub(lambda x: f'v("{x.group(1)}")', c.expression).replace(" = ", " == ")
            env = {"v": lambda i: interval(values.get(i, 0.0), False) if i in values else Iv(0.0, 0.0), "abs": abs}
            ok = bool(eval(expr, {"__builtins__": {}}, env))  # noqa: S307
            diff = None
            if "==" in expr:
                left, right = c.expression.split(" = ", 1)
                val = lambda e: sum(values.get(i, 0.0) for i in ITEM.findall(e))
                diff = round(val(left) - val(right), 6)
            out.append({"lei": lei, "period": period, "check_id": c.check_id, "basis": c.basis,
                        "expression": c.description, "status": "pass" if ok else "BREAK", "difference_eur_m": diff})
    return pd.DataFrame(out)


def run(out=OUT / "real") -> dict:
    out.mkdir(parents=True, exist_ok=True)
    te, banks, m = load()
    res = pd.concat([run_eba_rules(te, m), run_te_checks(te)], ignore_index=True)
    res = res.merge(banks[["lei", "name"]], on="lei", how="left")
    res = res.merge(te[["lei", "country"]].drop_duplicates("lei"), on="lei", how="left")
    res["name"] = res["name"].fillna("Bank with LEI withheld in the EBA data")
    # The same figures as COREP cells: what the bank filed, rebuilt from the published items
    single = m.dropna(subset=["template"])
    corep = te.merge(single[["item", "template", "row", "col", "label"]], on="item")
    corep.merge(banks[["lei", "name"]], on="lei", how="left").sort_values(["lei", "period", "template", "row"]).to_csv(
        out / "te2025_as_corep_cells.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    res.to_csv(out / "te2025_check_results.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    breaks = res[res.status == "BREAK"].copy()
    breaks["abs_diff"] = breaks.difference_eur_m.abs()
    breaks.sort_values(["check_id", "abs_diff"], ascending=[True, False]).drop(columns="abs_diff").to_csv(
        out / "te2025_breaks.csv", index=False, lineterminator="\n")
    by = res.groupby(["check_id", "basis"]).status.value_counts().unstack(fill_value=0).reset_index()
    by.to_csv(out / "te2025_by_check.csv", index=False, lineterminator="\n")
    return {
        "banks": int(te.lei.nunique()), "bank_quarters": int(te.groupby(["lei", "period"]).ngroups),
        "values": int(len(te)), "checks_run": int(len(res)),
        "eba_rules_distinct": int(res[res.basis == "EBA validation rule"].check_id.nunique()),
        "pass": int((res.status == "pass").sum()), "breaks": int((res.status == "BREAK").sum()),
        "banks_with_breaks": int(breaks.lei.nunique()),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=1))
