"""Run the EBA's own validation rules against the report.

The rules come from the EBA 4.0 taxonomy (taxonomy/validation_rules.csv), written in the EBA's cell
notation, e.g. "{C_01.00,0015,0010,} = {C_01.00,0020,0010,} + {C_01.00,0530,0010,}". They are
evaluated the way the EBA formula linkbase does it:

- interval arithmetic: each reported number stands for an interval set by its declared accuracy
  (monetary decimals -3 -> +/- 500; percentages decimals 4 -> +/- 0.00005), so "=" means the
  intervals overlap;
- a missing cell counts as 0 (fallbackValue="0"), and a rule with none of its cells reported does
  not apply;
- empty(...) tests whether a cell was reported at all.
"""

from __future__ import annotations

import csv
import html
import re
from dataclasses import dataclass

from corep import TAXONOMY, Cell

CELL = re.compile(r"\{(C_[0-9.]+(?:\.[a-z])?),(\d{4}),(\d{4}),\}")


@dataclass(frozen=True)
class Iv:
    lo: float
    hi: float

    @staticmethod
    def of(x) -> "Iv":
        return x if isinstance(x, Iv) else Iv(float(x), float(x))

    def __add__(self, o): o = Iv.of(o); return Iv(self.lo + o.lo, self.hi + o.hi)
    __radd__ = __add__
    def __sub__(self, o): o = Iv.of(o); return Iv(self.lo - o.hi, self.hi - o.lo)
    def __rsub__(self, o): return Iv.of(o) - self
    def __neg__(self): return Iv(-self.hi, -self.lo)

    def __mul__(self, o):
        o = Iv.of(o)
        p = [self.lo * o.lo, self.lo * o.hi, self.hi * o.lo, self.hi * o.hi]
        return Iv(min(p), max(p))
    __rmul__ = __mul__

    def __truediv__(self, o):
        o = Iv.of(o)
        if o.lo <= 0 <= o.hi:
            raise ZeroDivisionError
        return self * Iv(1 / o.hi, 1 / o.lo)

    # comparisons: true if some value in each interval satisfies the relation
    def __eq__(self, o): o = Iv.of(o); return self.lo <= o.hi and o.lo <= self.hi
    def __ne__(self, o): o = Iv.of(o); return not (self.lo == self.hi == o.lo == o.hi)
    def __ge__(self, o): return self.hi >= Iv.of(o).lo
    def __le__(self, o): return self.lo <= Iv.of(o).hi
    def __gt__(self, o): return self.hi > Iv.of(o).lo
    def __lt__(self, o): return self.lo < Iv.of(o).hi
    def __abs__(self):
        if self.lo >= 0:
            return self
        if self.hi <= 0:
            return -self
        return Iv(0.0, max(-self.lo, self.hi))


def load_rules() -> list[dict]:
    with open(TAXONOMY / "validation_rules.csv", encoding="utf-8") as f:
        return [{**r, "expression": html.unescape(r["expression"])} for r in csv.DictReader(f)]


def to_python(expr: str) -> str:
    """Translate the EBA notation into a Python expression over v(...) and empty(...)."""
    e = re.sub(r"empty\(" + CELL.pattern + r"\)", r'empty("\1","\2","\3")', expr)
    e = CELL.sub(r'v("\1","\2","\3")', e)
    m = re.fullmatch(r"\s*if\s*(.+?)\s+then\s+(.+?)\s+else\s+(.+)", e)
    if m:
        e = f"(({m.group(2)}) if ({m.group(1)}) else ({m.group(3)}))"
    e = re.sub(r"(?<![<>!=])=(?!=)", "==", e)
    e = e.replace("true()", "True").replace("false()", "False")
    return e


def evaluate(cells: dict[Cell, float], types: dict[Cell, str]) -> list[dict]:
    def interval(cell: Cell) -> Iv:
        x = cells[cell]
        kind = types.get(cell)
        half = 0.00005 if kind == "p" else 0.0 if kind == "i" else 500.0
        return Iv(x - half, x + half)

    results = []
    for rule in load_rules():
        refs = [(t, r, c) for t, r, c in CELL.findall(rule["expression"])]
        bare = CELL.findall(re.sub(r"empty\(" + CELL.pattern + r"\)", "", rule["expression"]))
        existence = "empty(" in rule["expression"]
        if not existence and not any(tuple(c) in cells for c in bare):
            results.append({**rule, "status": "not applicable", "detail": "none of its cells is reported"})
            continue
        env = {
            "v": lambda t, r, c: interval((t, r, c)) if (t, r, c) in cells else Iv(0.0, 0.0),
            "empty": lambda t, r, c: (t, r, c) not in cells,
            "abs": abs,
            "sum": lambda *xs: sum((Iv.of(x) for x in xs), Iv(0.0, 0.0)),
            "True": True, "False": False,
        }
        try:
            ok = bool(eval(to_python(rule["expression"]), {"__builtins__": {}}, env))  # noqa: S307 - taxonomy text, no builtins
            values = ", ".join(f"{t} r{r} c{c} = {cells.get((t, r, c), 'empty')}" for t, r, c in refs[:6])
            results.append({**rule, "status": "pass" if ok else "FAIL", "detail": values})
        except ZeroDivisionError:
            results.append({**rule, "status": "not applicable", "detail": "division by zero"})
        except Exception as exc:  # unsupported syntax is reported, never silently passed
            results.append({**rule, "status": "not evaluated", "detail": f"{type(exc).__name__}: {exc}"})
    return results
