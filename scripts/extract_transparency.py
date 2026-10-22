"""Extract the real-bank data used by CR-003 from the EBA 2025 EU-wide Transparency Exercise.

    python scripts/extract_transparency.py <folder with tr_oth.csv and TR_Metadata.xlsx>

Source: European Banking Authority, 2025 EU-wide Transparency Exercise, full database
(https://www.eba.europa.eu/risk-and-data-analysis/risk-analysis/eu-wide-transparency-exercise).
Figures come from the banks' own COREP/FINREP submissions; amounts are in EUR millions.
Reproduced in part, with the source acknowledged.

Keeps the Capital, Leverage and RWA OV1 templates (C 01.00, C 02.00, C 03.00, C 47.00 items) and
the bank names, and writes data/real/te2025.csv.gz and data/real/banks.csv.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "real"


def main(src: str) -> None:
    src = Path(src)
    OUT.mkdir(parents=True, exist_ok=True)
    d = pd.read_csv(src / "tr_oth.csv", low_memory=False, dtype={"LEI_Code": str, "Item": str})
    d = d[d.Sheet.isin(["Capital", "Leverage", "RWA OV1"])]
    d = d[["LEI_Code", "NSA", "Period", "Item", "Amount"]].rename(columns={"LEI_Code": "lei", "NSA": "country",
                                                                           "Period": "period", "Item": "item",
                                                                           "Amount": "amount"})
    d.sort_values(["lei", "period", "item"]).to_csv(OUT / "te2025.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    meta = pd.read_excel(src / "TR_Metadata.xlsx", "List of Institutions", header=1)
    meta = meta[["LEI_Code", "Name", "Country"]].dropna(subset=["LEI_Code"])
    meta.columns = ["lei", "name", "country"]
    meta.to_csv(OUT / "banks.csv", index=False, lineterminator="\n")
    print(f"{len(d)} values, {d.lei.nunique()} banks, periods {sorted(d.period.unique())}")


if __name__ == "__main__":
    main(sys.argv[1])
