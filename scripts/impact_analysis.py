"""Cell-level impact analysis between two runs of the report.

    python scripts/impact_analysis.py <baseline corep_templates.csv> <new corep_templates.csv> \
        [--expected docs/changes/CR-001_expected_cells.csv] [--out docs/changes/CR-001_impact.md]

Lists every COREP cell whose value changed, with old value, new value and difference, and checks
the result against the impact list agreed before the change was built:

- a cell that changed but was not on the list is an UNEXPECTED change (regression);
- a cell on the list that did not change is a MISSED change (the change did not take effect).

Both must be zero for the change to be accepted.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

KEY = ["template", "row", "col"]


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"row": str, "col": str, "value": str})
    return df[KEY + ["label", "value"]]


def as_number(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def diff(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    m = old.merge(new, on=KEY, how="outer", suffixes=("_old", "_new"), indicator=True)
    m["label"] = m["label_new"].fillna(m["label_old"])
    changed = m[(m["_merge"] != "both") | (m["value_old"] != m["value_new"])].copy()
    changed["change"] = [
        (as_number(n) - as_number(o)) if as_number(n) is not None and as_number(o) is not None else None
        for o, n in zip(changed["value_old"], changed["value_new"])
    ]
    changed["status"] = changed["_merge"].map({"both": "changed", "left_only": "removed", "right_only": "added"})
    return changed[KEY + ["label", "value_old", "value_new", "change", "status"]].sort_values(KEY)


def check(changed: pd.DataFrame, expected_path: str | None) -> tuple[set, set]:
    if not expected_path:
        return set(), set()
    exp = pd.read_csv(expected_path, dtype=str)
    actual = set(map(tuple, changed[KEY].to_numpy()))
    # "*" in row or col expects every cell it covers to change (used for whole new templates)
    patterns = [tuple(r) for r in exp[KEY].to_numpy()]
    match = lambda cell, pat: all(p in ("*", c) for c, p in zip(cell, pat))
    unexpected = {c for c in actual if not any(match(c, p) for p in patterns)}
    missed = {p for p in patterns if not any(match(c, p) for c in actual)}
    return unexpected, missed


def fmt(x) -> str:
    v = as_number(x)
    if v is None:
        return "" if pd.isna(x) else str(x)
    return f"{v:.2%}" if abs(v) < 1 and v != 0 else f"{v:,.0f}"


def markdown(changed: pd.DataFrame, unexpected: set, missed: set) -> str:
    lines = ["| Template | Row | Col | Item | Before | After | Change |", "|---|---|---|---|---|---|---|"]
    for r in changed.itertuples():
        label = (r.label or "")[:70]
        lines.append(f"| {r.template} | {r.row} | {r.col} | {label} | {fmt(r.value_old)} | {fmt(r.value_new)} | {fmt(r.change)} |")
    lines += ["", f"**Cells changed:** {len(changed)}  ",
              f"**Unexpected changes (regressions):** {len(unexpected)}  ",
              f"**Expected changes that did not happen:** {len(missed)}"]
    for title, cells in [("Unexpected", unexpected), ("Missed", missed)]:
        for c in sorted(cells):
            lines.append(f"- {title}: {' '.join(c)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline")
    ap.add_argument("new")
    ap.add_argument("--expected")
    ap.add_argument("--out")
    a = ap.parse_args()
    changed = diff(load(a.baseline), load(a.new))
    unexpected, missed = check(changed, a.expected)
    text = markdown(changed, unexpected, missed)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    return 1 if unexpected or missed else 0


if __name__ == "__main__":
    sys.exit(main())
