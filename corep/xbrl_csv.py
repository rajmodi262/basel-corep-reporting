"""Write the report as EBA xBRL-CSV report packages (one per module), the format the EBA 4.0 framework requires.

A package is a zip holding META-INF/reportPackage.json and reports/: report.json (which module of the
EBA taxonomy it reports against), parameters.csv, FilingIndicators.csv and one "datapoint,factValue"
CSV per template. The layout follows the EBA's own sample packages for release 4.0.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

from corep import TAXONOMY, Cell

MODULES = {
    "corep_of": {"code": "COREPOF",
                 "templates": ["C_00.01", "C_01.00", "C_02.00.a", "C_03.00", "C_22.00", "C_25.01.a", "C_34.01.a", "C_34.03"],
                 "filing": ["C_00.01", "C_01.00", "C_02.00", "C_03.00", "C_22.00", "C_25.01", "C_34.01", "C_34.03"]},
    "corep_lr": {"code": "COREPLR", "templates": ["C_00.01", "C_47.00"], "filing": ["C_00.01", "C_47.00"]},
}
HEADER = {("C_00.01", "0010", "0010"): "eba_AS:x2",   # Nature of report: IFRS
          ("C_00.01", "0020", "0010"): "eba_SC:x6"}   # Reporting level: Individual


def datapoint_index() -> dict[Cell, dict]:
    with open(TAXONOMY / "datapoints.csv", encoding="utf-8") as f:
        return {(r["template"], r["row"], r["col"]): r for r in csv.DictReader(f)}


def fmt(value, kind: str) -> str:
    if kind == "p":
        return f"{value:.4f}"
    if kind in ("m", "i"):
        return str(int(round(value)))
    return str(value)


def write_packages(cells: dict[Cell, object], p: dict, out: Path) -> list[Path]:
    index = datapoint_index()
    unknown = [c for c in cells if c not in index]
    if unknown:
        raise KeyError(f"cells not in the EBA taxonomy: {unknown[:5]}")
    entity, ref = p["entity"], p["reporting_date"]
    written = []
    for module, spec in MODULES.items():
        name = f"{entity}_FR_COREP040000_{spec['code']}_{ref}_20260101000000000"
        files: dict[str, str] = {
            "META-INF/reportPackage.json": json.dumps({"documentInfo": {"documentType": "https://xbrl.org/report-package/2023"}}, indent=2),
            "reports/report.json": json.dumps({"documentInfo": {
                "documentType": "https://xbrl.org/2021/xbrl-csv",
                "extends": [f"http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/corep/4.0/mod/{module}.json"]}}, indent=4),
            "reports/parameters.csv": "name,value\n" + "\n".join([
                f"entityID,rs:{entity}", f"refPeriod,{ref}", "baseCurrency,iso4217:EUR",
                "decimalsMonetary,-3", "decimalsPercentage,4"]) + "\n",
            "reports/FilingIndicators.csv": "templateID,reported\n" + "".join(f"{t},true\n" for t in spec["filing"]),
        }
        for template in spec["templates"]:
            buf = io.StringIO()
            w = csv.writer(buf, lineterminator="\n")
            w.writerow(["datapoint", "factValue"])
            source = HEADER if template == "C_00.01" else cells
            for cell in sorted(c for c in source if c[0] == template):
                meta = index[cell]
                w.writerow([meta["datapoint"], fmt(source[cell], meta["type"])])
            files[f"reports/{index[next(c for c in index if c[0] == template)]['file']}"] = buf.getvalue()
        path = out / f"{name}.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for rel, text in files.items():
                info = zipfile.ZipInfo(f"{name}/{rel}", date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, text)
        written.append(path)
    return written
