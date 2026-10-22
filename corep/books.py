"""Load the bank's books and the configuration into DuckDB."""

from __future__ import annotations

import duckdb
import pandas as pd
import yaml

from corep import CONFIG, DATA, SQL

EU_MEMBER_STATES = ["AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR", "HR", "HU", "IE", "IT",
                    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"]


def params() -> dict:
    return yaml.safe_load((CONFIG / "srep.yaml").read_text(encoding="utf-8"))


def read_csv(path, **kw) -> pd.DataFrame:
    return pd.read_csv(path, keep_default_na=False, na_values={"property_value": [""], "original_maturity_days": [""]}, **kw)


def connect(data_dir=DATA) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    text_cols = {"gl_account": str, "account": str, "cqs": str, "counterparty_type": str, "c02_row": str,
                 "c47_row": str, "c01_row": str, "default_flag": str, "has_property_value": str, "short_term": str,
                 "reference": str, "currency_2": str}
    tables = {
        "exposures": data_dir / "exposures.csv",
        "off_balance": data_dir / "off_balance.csv",
        "general_ledger": data_dir / "general_ledger.csv",
        "pl_history": data_dir / "pl_history.csv",
        "capital_instruments": data_dir / "capital_instruments.csv",
        "property_valuations": data_dir / "property_valuations_2025Q4.csv",
        "derivatives": data_dir / "derivatives.csv",
        "total_assets_history": data_dir / "total_assets_history.csv",
        "dt_exposure_class": CONFIG / "dt_exposure_class.csv",
        "dt_risk_weight": CONFIG / "dt_risk_weight.csv",
        "dt_other_items": CONFIG / "dt_other_items.csv",
        "dt_ccf": CONFIG / "dt_ccf.csv",
        "map_own_funds": CONFIG / "map_own_funds.csv",
    }
    for name, path in tables.items():
        df = read_csv(path, dtype={k: v for k, v in text_cols.items()})
        if name == "exposures":
            df["default_flag"] = df["default_flag"].astype(int)
        con.register(f"{name}_df", df)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM {name}_df")
    p = params()
    con.execute("CREATE TABLE params AS SELECT ? AS eu_sovereign_domestic_zero, ? AS reporting_date",
                [p["eu_sovereign_domestic_zero"], p["reporting_date"]])
    con.register("eu_df", pd.DataFrame({"country": EU_MEMBER_STATES}))
    con.execute("CREATE TABLE eu_member_states AS SELECT * FROM eu_df")
    return con


def run_sql(con: duckdb.DuckDBPyConnection, name: str) -> None:
    con.execute((SQL / name).read_text(encoding="utf-8"))
