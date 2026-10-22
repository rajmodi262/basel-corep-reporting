"""CR-002: derivatives. Counterparty credit risk under SA-CCR, CVA risk, FX market risk, and the
size-of-derivative-business test, with the COREP cells each one feeds.

SA-CCR (CRR Part Three, Title II, Chapter 6, Section 3), per netting set:

    exposure value = alpha x (RC + PFE)                                  Art 274(2)
    RC             = max(V - C, 0)          unmargined, no collateral    Art 275(1)
    PFE            = multiplier x AddOn                                  Art 278
    multiplier     = min(1, 0.05 + 0.95 x exp(V / (2 x 0.95 x AddOn)))   Art 278(3)
    AddOn          = sum over risk categories                            Art 278(1)
      interest rate: 0.5% x effective notional over three maturity buckets  Art 280a
      FX:            4% x |effective notional| per currency pair          Art 280c
    effective notional of a trade = delta x adjusted notional x maturity factor
      adjusted notional (IR) = notional x supervisory duration           Art 279b(1)(a)
      maturity factor (unmargined) = sqrt(min(max(M, 10 days), 1 year))  Art 279c(1)(a)
"""

from __future__ import annotations

import math
from datetime import date

import duckdb
import pandas as pd
import yaml

from corep import CONFIG, Cell

PARAMS = yaml.safe_load((CONFIG / "sa_ccr.yaml").read_text(encoding="utf-8"))


def years_between(start: str, end: str) -> float:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days / 365.0


def trade_level(con: duckdb.DuckDBPyConnection, reporting_date: str) -> pd.DataFrame:
    p = PARAMS["sa_ccr"]
    t = con.execute("SELECT * FROM derivatives ORDER BY trade_id").df()
    t["M"] = [max(years_between(reporting_date, m), 0.0) for m in t.maturity_date]
    t["S"] = [max(years_between(reporting_date, s), 0.0) for s in t.start_date]
    r = p["interest_rate"]["supervisory_duration_rate"]
    t["supervisory_duration"] = [
        (math.exp(-r * s) - math.exp(-r * e)) / r if ac == "interest_rate" else 1.0
        for ac, s, e in zip(t.asset_class, t.S, t.M)
    ]
    t["adjusted_notional"] = t.notional * t.supervisory_duration
    t["maturity_factor"] = [math.sqrt(min(max(m, p["min_maturity_years"]), 1.0)) for m in t.M]
    # delta +1 for a long position in the primary risk driver: paying fixed is long rates (Art 279a(1))
    t["delta"] = t.direction.map({"pay_fixed": 1, "receive_fixed": -1, "buy_currency_2": 1, "sell_currency_2": -1})
    t["effective_notional"] = t.delta * t.adjusted_notional * t.maturity_factor
    edges = p["interest_rate"]["bucket_edges_years"]
    t["ir_bucket"] = [("1" if m < edges[0] else "2" if m <= edges[1] else "3") if ac == "interest_rate" else ""
                      for ac, m in zip(t.asset_class, t.M)]
    t["mtm"] = t.mtm_2025_12_31
    return t


def ir_addon(trades: pd.DataFrame) -> float:
    ir = PARAMS["sa_ccr"]["interest_rate"]
    d = {k: trades.loc[trades.ir_bucket == k, "effective_notional"].sum() for k in "123"}
    en = math.sqrt(d["1"] ** 2 + d["2"] ** 2 + d["3"] ** 2 + ir["correlation_adjacent"] * (d["1"] * d["2"] + d["2"] * d["3"])
                   + ir["correlation_outer"] * d["1"] * d["3"])
    return ir["supervisory_factor"] * en


def fx_addon(trades: pd.DataFrame) -> float:
    sf = PARAMS["sa_ccr"]["foreign_exchange"]["supervisory_factor"]
    return sum(sf * abs(g.effective_notional.sum()) for _, g in trades.groupby(["currency", "currency_2"]))


def netting_sets(t: pd.DataFrame, risk_weight) -> pd.DataFrame:
    p = PARAMS["sa_ccr"]
    rows = []
    for ns, g in t.groupby("netting_set"):
        addons = {"interest_rate": ir_addon(g[g.asset_class == "interest_rate"]),
                  "foreign_exchange": fx_addon(g[g.asset_class == "foreign_exchange"])}
        addon = sum(addons.values())
        v = g.mtm.sum()
        rc = max(v, 0.0)
        mult = 1.0 if v >= 0 else min(1.0, p["multiplier_floor"] + (1 - p["multiplier_floor"]) * math.exp(v / (2 * (1 - p["multiplier_floor"]) * addon)))
        pfe = mult * addon
        ead = p["alpha"] * (rc + pfe)
        ctype, cqs = g.counterparty_type.iloc[0], g.cqs.iloc[0]
        rw = risk_weight(ctype, cqs)
        rows.append({"netting_set": ns, "counterparty_id": g.counterparty_id.iloc[0], "counterparty_type": ctype,
                     "cqs": cqs, "trades": len(g), "notional": g.notional.sum(), "V": v, "RC": rc,
                     "addon_ir": addons["interest_rate"], "addon_fx": addons["foreign_exchange"], "addon": addon,
                     "multiplier": mult, "PFE": pfe, "exposure_value": ead, "risk_weight": rw, "rwea": ead * rw,
                     # leverage ratio: same RC and add-on, multiplier set to 1 (Art 429c(5)), alpha applies
                     "lr_rc": p["alpha"] * rc, "lr_pfe": p["alpha"] * addon})
    return pd.DataFrame(rows)


def risk_weight_lookup(con: duckdb.DuckDBPyConnection):
    table = con.execute("SELECT exposure_class, cqs, short_term, risk_weight FROM dt_risk_weight").df()

    def rw(ctype: str, cqs: str) -> float:
        cls = "institution" if ctype == "institution" else "corporate"
        hit = table[(table.exposure_class == cls) & (table.cqs == (cqs or "")) & table.short_term.isin(["*", "0"])]
        return float(hit.risk_weight.iloc[0])
    return rw


# --------------------------------------------------------------------------- COREP cells
def _c(t, r, col) -> Cell:
    return (t, r, col)


def c34_03(t: pd.DataFrame, ns: pd.DataFrame) -> dict[Cell, object]:
    """C 34.03, sheet SA-CCR: transactions, notionals, market values and add-ons by risk category."""
    T = "C_34.03"
    cells: dict[Cell, object] = {}

    no_addon = {"0060", "0130"}  # "of which: mapped exclusively to ..." rows carry no add-on column

    def block(rows: list[str], g: pd.DataFrame, addon: float):
        for r in rows:
            cells[_c(T, r, "0030")] = len(g)
            cells[_c(T, r, "0040")] = round(g.notional.sum())
            cells[_c(T, r, "0050")] = round(g.mtm[g.mtm > 0].sum())
            cells[_c(T, r, "0060")] = round(g.mtm[g.mtm < 0].sum())
            if r not in no_addon:
                cells[_c(T, r, "0070")] = round(addon)

    ir, fx = t[t.asset_class == "interest_rate"], t[t.asset_class == "foreign_exchange"]
    block(["0050", "0060", "0070"], ir, ns.addon_ir.sum())        # all IR trades are EUR, mapped only to IR
    cells[_c(T, "0070", "0010")] = "eba_CU:EUR"
    block(["0120", "0130", "0140"], fx, ns.addon_fx.sum())        # one currency pair, EUR/USD
    cells[_c(T, "0140", "0010")] = "eba_CU:EUR"
    cells[_c(T, "0140", "0020")] = "eba_CU:USD"
    block(["0010"], t, ns.addon.sum())
    return cells


def c34_01(con: duckdb.DuckDBPyConnection) -> dict[Cell, object]:
    """C 34.01: size of the derivative business per month (Art 273a(3)): long = positive market values,
    short = absolute negative market values, as a share of total assets."""
    T = "C_34.01.a"
    d = con.execute("SELECT * FROM derivatives").df()
    assets = con.execute("SELECT total_assets FROM total_assets_history ORDER BY month_end").df().total_assets.tolist()
    cells: dict[Cell, object] = {}
    for (long_c, short_c, tot_c), col, a in zip([("0010", "0020", "0030"), ("0040", "0050", "0060"), ("0070", "0080", "0090")],
                                                ["mtm_2025_10_31", "mtm_2025_11_30", "mtm_2025_12_31"], assets):
        long_, short = round(d[col][d[col] > 0].sum()), round(-d[col][d[col] < 0].sum())
        for r in ("0010", "0020"):
            cells[_c(T, r, long_c)], cells[_c(T, r, short_c)], cells[_c(T, r, tot_c)] = long_, short, long_ + short
        cells[_c(T, "0040", tot_c)] = round(a)
        cells[_c(T, "0050", tot_c)] = round((long_ + short) / a, 4)
    return cells


def cva(ns: pd.DataFrame, t: pd.DataFrame) -> tuple[dict[Cell, object], float]:
    """C 25.01: simplified approach (Art 385). Non-financial counterparties are exempt (Art 382(4)(a));
    their marginal impact is shown in the exemption rows, as the template asks."""
    T = "C_25.01.a"
    exempt = ns.counterparty_type.isin(PARAMS["cva"]["exempt_counterparty_types"])
    cells: dict[Cell, object] = {}

    def fill(rows, part):
        ofr_ccr = part.rwea.sum() * 0.08
        for r in rows:
            cells[_c(T, r, "0010")] = round(part.exposure_value.sum())
            cells[_c(T, r, "0020")] = round(ofr_ccr)
            cells[_c(T, r, "0060")] = round(part.rwea.sum() / 12.5)
            cells[_c(T, r, "0280")] = round(part.rwea.sum() / 12.5)
            cells[_c(T, r, "0290")] = round(part.rwea.sum())
        return part.rwea.sum()

    rea = fill(["0010", "0020"], ns[~exempt])              # in scope: all transactions are derivatives
    fill(["0040", "0060", "0070"], ns[exempt])               # exempted: EU non-financial counterparties
    cells[_c(T, "0010", "0130")] = int((~exempt).sum())      # number of counterparties in scope
    return cells, rea


def fx_risk(con: duckdb.DuckDBPyConnection, t: pd.DataFrame, own_funds: float) -> tuple[dict[Cell, object], float]:
    """C 22.00: FX risk on the whole balance sheet (Art 351-354). Net position per currency; the overall
    net position is charged at 8% if it exceeds 2% of own funds (de minimis, Art 351)."""
    T = "C_22.00"
    p = PARAMS["fx_risk"]
    assets = con.execute("SELECT currency, sum(gross_amount - specific_provision) FROM exposures "
                         "WHERE currency <> 'EUR' GROUP BY 1").fetchall()
    cells: dict[Cell, object] = {}
    total_rea = 0.0
    currency_rows = {"USD": "0380"}
    long_all = short_all = net_long = net_short = 0.0
    for cur, on_balance in assets:
        fwd_short = t[(t["product"] == "fx_forward") & (t.currency_2 == cur) & (t.direction == "sell_currency_2")].notional.sum()
        fwd_long = t[(t["product"] == "fx_forward") & (t.currency_2 == cur) & (t.direction == "buy_currency_2")].notional.sum()
        long_, short = on_balance + fwd_long, fwd_short
        net = long_ - short
        r = currency_rows[cur]
        cells[_c(T, r, "0020")], cells[_c(T, r, "0030")] = round(long_), round(short)
        cells[_c(T, r, "0040")], cells[_c(T, r, "0050")] = round(max(net, 0)), round(max(-net, 0))
        long_all, short_all = long_all + long_, short_all + short
        net_long, net_short = net_long + max(net, 0), net_short + max(-net, 0)
        on_bal_long, deriv_short, deriv_long = on_balance, fwd_short, fwd_long
    overall = max(net_long, net_short)                        # Art 352(2)
    charged = overall if overall > p["de_minimis_share_of_own_funds"] * own_funds else 0.0
    ofr = p["own_funds_rate"] * charged
    for r in ("0010", "0030"):                                # all positions are "other currencies"
        cells[_c(T, r, "0020")], cells[_c(T, r, "0030")] = round(long_all), round(short_all)
        cells[_c(T, r, "0040")], cells[_c(T, r, "0050")] = round(net_long), round(net_short)
        cells[_c(T, r, "0060")] = round(net_long if charged else 0)
        cells[_c(T, r, "0070")] = round(net_short if charged else 0)
        cells[_c(T, r, "0090")] = round(ofr)
    cells[_c(T, "0010", "0100")] = round(12.5 * ofr)
    # breakdown of total positions by exposure type
    cells[_c(T, "0100", "0020")], cells[_c(T, "0100", "0030")] = round(on_bal_long), 0
    cells[_c(T, "0120", "0020")], cells[_c(T, "0120", "0030")] = round(deriv_long), round(deriv_short)
    return cells, 12.5 * ofr
