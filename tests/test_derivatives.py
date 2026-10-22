"""CR-002: SA-CCR, CVA, FX risk and the derivative-size test, checked independently (UT-30..UT-37)."""

import math

import pytest

from corep import derivatives
from corep.books import connect
from corep.eba_rules import evaluate
from corep.pipeline import build


@pytest.fixture(scope="module")
def run():
    con, p, dq, opr, cells, index = build()
    trades = derivatives.trade_level(con, p["reporting_date"])
    ns = derivatives.netting_sets(trades, derivatives.risk_weight_lookup(con)).set_index("netting_set")
    types = {c: m["type"] for c, m in index.items()}
    return con, cells, trades, ns, types


def test_sa_ccr_by_hand_for_one_netting_set(run):
    # UT-30 Art 274-280a, recomputed from the trades without the module's helpers (NS-01: 4 EUR swaps + 2 FX forwards)
    _, _, trades, ns, _ = run
    g = trades[trades.netting_set == "NS-01"]
    d = {"1": 0.0, "2": 0.0, "3": 0.0}
    fx = 0.0
    for t in g.itertuples():
        mf = math.sqrt(min(max(t.M, 10 / 250), 1.0))
        if t.asset_class == "interest_rate":
            sd = (1 - math.exp(-0.05 * t.M)) / 0.05
            delta = 1 if t.direction == "pay_fixed" else -1
            d["1" if t.M < 1 else "2" if t.M <= 5 else "3"] += delta * t.notional * sd * mf
        else:
            fx += (-1 if t.direction == "sell_currency_2" else 1) * t.notional * mf
    addon = 0.005 * math.sqrt(d["1"] ** 2 + d["2"] ** 2 + d["3"] ** 2 + 1.4 * d["1"] * d["2"] + 1.4 * d["2"] * d["3"]
                              + 0.6 * d["1"] * d["3"]) + 0.04 * abs(fx)
    v = g.mtm.sum()
    assert v > 0                                       # so RC = V and the multiplier is 1
    assert ns.loc["NS-01", "exposure_value"] == pytest.approx(1.4 * (v + addon))
    assert ns.loc["NS-01", "rwea"] == pytest.approx(1.4 * (v + addon) * 0.20)     # bank, CQS 1


def test_out_of_the_money_netting_set_gets_rc_zero_and_multiplier_below_one(run):
    # UT-31 Art 275(1), 278(3)
    _, _, _, ns, _ = run
    r = ns.loc["NS-04"]
    assert r.V < 0 and r.RC == 0
    assert r.multiplier == pytest.approx(0.05 + 0.95 * math.exp(r.V / (2 * 0.95 * r.addon)))
    assert 0.05 <= r.multiplier < 1


def test_leverage_uses_multiplier_one(run):
    # UT-32 Art 429c(5): PFE in the leverage measure ignores the multiplier
    _, cells, _, ns, _ = run
    assert cells[("C_47.00", "0091", "0010")] == pytest.approx(1.4 * ns.addon.sum(), abs=1)
    assert cells[("C_47.00", "0061", "0010")] == pytest.approx(1.4 * ns.RC.sum(), abs=1)


def test_cva_excludes_non_financial_counterparties(run):
    # UT-33 Art 382(4)(a) exemption, Art 385 simplified approach: CVA REA = CCR RWEA of in-scope netting sets
    _, cells, _, ns, _ = run
    in_scope = ns[ns.counterparty_type == "institution"].rwea.sum()
    assert cells[("C_02.00.a", "0675", "0010")] == round(in_scope)
    assert cells[("C_25.01.a", "0060", "0290")] == round(ns[ns.counterparty_type == "corporate"].rwea.sum())


def test_fx_risk_charged_above_de_minimis(run):
    # UT-34 Art 351-352: net USD = 110m bonds - 80m sold forward = 30m > 2% of own funds -> 8% charge
    _, cells, _, _, _ = run
    assert cells[("C_22.00", "0010", "0040")] == 30_000_000
    assert cells[("C_22.00", "0010", "0090")] == 2_400_000
    assert cells[("C_02.00.a", "0560", "0010")] == 30_000_000


def test_fx_risk_waived_below_de_minimis(run):
    # UT-35 Art 351: with own funds of EUR 2bn the 30m position is under 2% (40m) -> no charge
    con, _, trades, _, _ = run
    _, rea = derivatives.fx_risk(con, trades, 2_000_000_000)
    assert rea == 0


def test_derivative_business_is_small(run):
    # UT-36 Art 273a(2): below 5% of total assets and EUR 100m in each month -> simplified CVA approach allowed
    _, cells, _, _, _ = run
    for total, pct in [("0030", "0050"), ("0060", "0050"), ("0090", "0050")]:
        assert cells[("C_34.01.a", "0010", total)] < 100_000_000
        assert cells[("C_34.01.a", "0050", total)] < 0.05


@pytest.mark.parametrize("cell, delta, rule", [
    (("C_22.00", "0010", "0100"), 1_000_000, "v0629_m_0"),     # FX REA no longer equals C 02.00 r0560
    (("C_25.01.a", "0010", "0060"), 100_000, "v22976_m_0"),    # CVA own funds x 12.5 no longer equals C 02.00 r0675
    (("C_34.03", "0050", "0040"), 10_000_000, "v10288_h_2"),   # IR notional no longer adds up to the total
])
def test_planted_errors_in_new_templates_are_caught(run, cell, delta, rule):
    # UT-37
    _, cells, _, _, types = run
    broken = dict(cells)
    broken[cell] = cells[cell] + delta
    assert rule in {r["rule_id"] for r in evaluate(broken, types) if r["status"] == "FAIL"}
