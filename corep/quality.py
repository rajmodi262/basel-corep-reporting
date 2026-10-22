"""Data-quality rules on the risk sub-ledger, run before any calculation.

Each rule names the regulatory field it protects. Nothing is dropped silently: an exposure that
breaks a rule is either reported with a documented conservative fallback (WARN) or stops the run
(BLOCK). See docs/DATA_GAPS.md.
"""

from __future__ import annotations

import duckdb
import pandas as pd

RULES = [
    ("DQ-01", "BLOCK", "Exposure id unique",
     "SELECT exposure_id FROM exposures GROUP BY 1 HAVING count(*) > 1"),
    ("DQ-02", "WARN", "Counterparty type present (drives the exposure class, Art 112)",
     "SELECT exposure_id FROM exposures WHERE coalesce(counterparty_type, '') = ''"),
    ("DQ-03", "WARN", "Property value present for mortgages (needed for loan-splitting, Art 124-125)",
     "SELECT exposure_id FROM exposures WHERE product = 'residential_mortgage' AND property_value IS NULL"),
    ("DQ-04", "BLOCK", "Specific provision between 0 and the gross amount (Art 111(1))",
     "SELECT exposure_id FROM exposures WHERE specific_provision < 0 OR specific_provision > gross_amount"),
    ("DQ-05", "BLOCK", "Credit quality step is 1-6 or blank (Art 136 mapping)",
     "SELECT exposure_id FROM exposures WHERE coalesce(cqs, '') NOT IN ('', '1', '2', '3', '4', '5', '6')"),
    ("DQ-06", "BLOCK", "Every exposure books to a GL account in the trial balance",
     "SELECT exposure_id FROM exposures WHERE gl_account NOT IN (SELECT account FROM general_ledger)"),
    ("DQ-07", "BLOCK", "Every off-balance product has a CCF in the decision table (Annex I)",
     "SELECT commitment_id FROM off_balance WHERE product NOT IN (SELECT product FROM dt_ccf)"),
    ("DQ-08", "WARN", "Defaulted exposures carry a specific provision (IFRS 9 stage 3)",
     "SELECT exposure_id FROM exposures WHERE default_flag = 1 AND specific_provision = 0"),
]


def run(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    rows = []
    for rule_id, severity, name, sql in RULES:
        ids = [r[0] for r in con.execute(sql).fetchall()]
        rows.append({"rule_id": rule_id, "severity": severity, "rule": name, "hits": len(ids),
                     "examples": " ".join(ids[:6])})
    return pd.DataFrame(rows)
