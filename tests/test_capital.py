"""Own funds, operational risk and leverage calculations checked by hand (UAT UT-10..UT-15)."""

from datetime import date

import pytest

from corep.capital import operational_risk, pct, tier2_amortised
from corep.pipeline import build


@pytest.fixture(scope="module")
def run():
    con, p, dq, opr, cells, index = build()
    return con, p, opr, cells


def c(cells, t, r, col="0010"):
    return cells[(t, r, col)]


def test_tier2_amortisation_in_final_five_years():
    # UT-10 Art 64: 100m maturing 2028-05-30 counts 881/1826 at 2025-12-31; one maturing in 2033 counts in full
    assert tier2_amortised(100e6, "2028-05-30", date(2025, 12, 31)) == pytest.approx(100e6 * 881 / 1826)
    assert tier2_amortised(150e6, "2033-09-20", date(2025, 12, 31)) == 150e6


def test_business_indicator_by_hand(run):
    # UT-11 Art 314, inputs in EUR m (2023, 2024, 2025)
    con, *_ = run
    ildc = min((127 + 139 + 148) / 3, 0.0225 * (5480 + 5690 + 5870) / 3) + 2
    sc = max((5 + 7 + 6) / 3, (6 + 4 + 5) / 3) + max((64 + 68 + 71) / 3, (12 + 13 + 14) / 3)
    fc = 0 + (4 + 2 + 3) / 3
    opr = operational_risk(con)
    assert opr["bi"] == pytest.approx((ildc + sc + fc) * 1e6)
    assert opr["rea"] == pytest.approx(12.5 * 0.12 * opr["bi"])


def test_cet1_built_from_ledger(run):
    # UT-12: 200 + 150 + 281 + (48 - 20) - 15 + 25 - 0.39 - 40 - (45 - 6) - 12 = 577.61m
    _, _, _, cells = run
    assert c(cells, "C_01.00", "0020") == 577_610_000


def test_foreseeable_dividend_reduces_eligible_profit(run):
    # UT-13 Art 26(2)
    _, _, _, cells = run
    assert c(cells, "C_01.00", "0160") == 48_000_000
    assert c(cells, "C_01.00", "0170") == -20_000_000
    assert c(cells, "C_01.00", "0150") == 28_000_000


def test_ratios_are_own_funds_over_trea(run):
    # UT-14 Art 92(2)
    _, _, _, cells = run
    trea = c(cells, "C_02.00.a", "0010")
    assert c(cells, "C_03.00", "0010") == pct(c(cells, "C_01.00", "0020") / trea)
    assert c(cells, "C_03.00", "0050") == pct(c(cells, "C_01.00", "0010") / trea)
    assert c(cells, "C_03.00", "0140") == 0.0563  # 4.5% + 56.25% x 2% P2R


def test_leverage_ratio_by_hand(run):
    # UT-15 Art 429: Tier 1 / (assets + off-balance at LR CCF - assets deducted from Tier 1)
    con, _, _, cells = run
    assets = c(cells, "C_47.00", "0190")
    obs = con.execute("SELECT sum(nominal_amount * lr_ccf) FROM off_balance_rwa").fetchone()[0]
    deducted = 40e6 + 39e6 + 12e6 + 390_000
    exposure = assets + obs - deducted
    assert c(cells, "C_47.00", "0290") == pytest.approx(exposure, abs=1)
    assert c(cells, "C_47.00", "0330") == pct(c(cells, "C_01.00", "0015") / exposure)
