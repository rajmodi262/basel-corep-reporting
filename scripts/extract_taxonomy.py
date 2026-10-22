"""Extract the parts of the EBA 4.0 reporting taxonomy this project reports against.

    python scripts/extract_taxonomy.py <path to unzipped EBA_XBRL_4.0_Reporting_Frameworks_4.0.0.0>

Writes two small files that are committed, so the pipeline and CI never need the 457 MB taxonomy:

- taxonomy/datapoints.csv: every cell of the reported templates with its xBRL-CSV datapoint id
  (e.g. C_47.00 r0290 c0010 -> dp...), value type and row label;
- taxonomy/validation_rules.csv: every EBA validation rule whose cells all sit in those templates,
  with the rule expression exactly as the taxonomy states it (verbose label).

Source: European Banking Authority, XBRL taxonomy for reporting framework 4.0 (errata 5).
"""

from __future__ import annotations

import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XL = "{http://www.w3.org/1999/xlink}"

# template id -> (folder relative to fws/corep, table json name)
TEMPLATES = {
    "C_00.01": ("3.4/tab/c_00.01", "c_00.01"),
    "C_01.00": ("4.0/tab/c_01.00", "c_01.00"),
    "C_02.00.a": ("4.0/tab/c_02.00.a", "c_02.00.a"),
    "C_03.00": ("4.0/tab/c_03.00", "c_03.00"),
    "C_47.00": ("4.0/tab/c_47.00", "c_47.00"),
    "C_22.00": ("4.0/tab/c_22.00", "c_22.00"),          # market risk: foreign exchange (CR-002)
    "C_25.01.a": ("4.0/tab/c_25.01.a", "c_25.01.a"),    # CVA risk (CR-002)
    "C_34.01.a": ("4.0/tab/c_34.01.a", "c_34.01.a"),    # size of derivative business (CR-002)
    "C_34.03": ("4.0/tab/c_34.03", "c_34.03"),          # SA-CCR by risk category (CR-002), sheet s0001 only
}
# Templates with a sheet (z-axis): only the listed sheet is reported, and its cells are addressed
# without the sheet code. C 34.03 s0001 = SA-CCR (eba_AP:x184); s0002 = simplified SA-CCR, not used.
SHEETS = {"C_34.03": "s0001"}
MODULES = {"C_00.01": "both", "C_01.00": "corep_of", "C_02.00.a": "corep_of", "C_03.00": "corep_of", "C_47.00": "corep_lr",
           "C_22.00": "corep_of", "C_25.01.a": "corep_of", "C_34.01.a": "corep_of", "C_34.03": "corep_of"}


def row_labels(folder: Path, name: str, axis: str = "y") -> dict[str, str]:
    """Row code -> English label, joining the code and English label linkbases on the element id."""
    def by_element(path: Path) -> dict[str, str]:
        root = ET.parse(path).getroot()
        locs = {l.get(XL + "label"): l.get(XL + "href").split("#")[1] for l in root.iter() if l.tag.endswith("}loc")}
        res = {l.get(XL + "label"): (l.text or "").strip() for l in root.iter() if l.tag.endswith("}label")}
        out = {}
        for arc in root.iter():
            if arc.tag.endswith("}arc"):
                el, text = locs.get(arc.get(XL + "from")), res.get(arc.get(XL + "to"))
                if el and text:
                    out.setdefault(el, text)
        return out

    codes, english = by_element(folder / f"{name}-lab-codes.xml"), by_element(folder / f"{name}-lab-en.xml")
    rows = y_axis_nodes(folder / f"{name}-rend.xml", axis)
    return {code: english[el] for el, code in codes.items()
            if el in rows and el in english and re.fullmatch(r"\d{4}", code)}


def y_axis_nodes(rend: Path, axis: str = "y") -> set[str]:
    """Ids of the rule nodes on the table's y axis (rows), walking breakdown -> tree -> subtree arcs."""
    root = ET.parse(rend).getroot()
    locs = {l.get(XL + "label"): l.get(XL + "href").split("#")[1] for l in root.iter() if l.tag.endswith("}loc")}
    ids = {r.get(XL + "label"): r.get("id") for r in root.iter() if r.get("id")}
    resolve = lambda label: locs.get(label) or ids.get(label)
    children: dict[str, list[str]] = {}
    starts = []
    for arc in root.iter():
        role = arc.get(XL + "arcrole") or ""
        if not role:
            continue
        f, t = resolve(arc.get(XL + "from")), resolve(arc.get(XL + "to"))
        if role.endswith("table-breakdown") and arc.get("axis") == axis:
            starts.append(t)
        elif role.endswith("breakdown-tree") or role.endswith("definition-node-subtree"):
            children.setdefault(f, []).append(t)
    seen, stack = set(), list(starts)
    while stack:
        node = stack.pop()
        if node not in seen:
            seen.add(node)
            stack.extend(children.get(node, []))
    return seen


def datapoints(corep: Path) -> list[dict]:
    rows = []
    for template, (rel, name) in TEMPLATES.items():
        folder = corep / rel
        table = json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))
        tt = next(iter(table["tableTemplates"].values()))
        labels = row_labels(folder, name)
        col_labels = row_labels(folder, name, "x")
        for dp, group in tt["columns"]["datapoint"]["propertyGroups"].items():
            doc = group["eba:documentation"]
            sheet = re.search(r"s(\d{4})", doc["cellcode"])
            if sheet and f"s{sheet.group(1)}" != SHEETS.get(template):
                continue
            m = re.search(r"r(\d{4})", doc["cellcode"]) or None
            c = re.search(r"c(\d{4})", doc["cellcode"])
            row = m.group(1) if m else ""
            rows.append({
                "template": template, "module": MODULES[template], "file": f"{name}.csv",
                "row": row, "col": c.group(1) if c else "", "datapoint": dp, "type": doc["type"],
                "cellcode": doc["cellcode"], "row_label": labels.get(row, ""),
                "col_label": col_labels.get(c.group(1) if c else "", ""),
            })
    return rows


CELL = re.compile(r"\{(C_[0-9.]+[a-z]?(?:\.[a-z])?),([^,}]*),([^,}]*),([^}]*)\}")


def rules(corep: Path) -> list[dict]:
    reported = set(TEMPLATES)
    out = []
    for path in sorted((corep / "4.0" / "val").glob("vr-*.xml")):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r'xlink:role="http://www.xbrl.org/2008/role/verboseLabel"[^>]*>([^<]+)<', text):
            label = m.group(1).strip()
            rid, _, expr = label.partition(": ")
            cells = CELL.findall(expr)
            if any(s and "s" + s.lstrip("s") != SHEETS.get(tb) for tb, _, _, s in cells):  # rules write the sheet as 0001
                continue  # rule on a sheet we do not report
            expr = CELL.sub(lambda c: "{%s,%s,%s,}" % c.group(1, 2, 3), expr)
            tables = {c[0] for c in cells}
            if tables and tables <= reported:
                out.append({"rule_id": rid, "file": path.name, "templates": " ".join(sorted(tables)), "expression": expr})
    return out


def main(framework_root: str) -> None:
    corep = Path(framework_root) / "www.eba.europa.eu/eu/fr/xbrl/crr/fws/corep"
    out = ROOT / "taxonomy"
    out.mkdir(exist_ok=True)
    for name, rows in [("datapoints.csv", datapoints(corep)), ("validation_rules.csv", rules(corep))]:
        with open(out / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        print(f"{name}: {len(rows)} rows")


if __name__ == "__main__":
    main(sys.argv[1])
