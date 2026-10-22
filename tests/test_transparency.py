"""CR-003: EBA rules on real banks' figures (UAT UT-40..UT-45)."""

import pandas as pd
import pytest

from corep import transparency as tr
from corep.eba_rules import CELL, load_rules
from corep.xbrl_csv import datapoint_index


@pytest.fixture(scope="module")
def data():
    te, banks, m = tr.load()
    return te, banks, m


@pytest.fixture(scope="module")
def results(data):
    te, _, m = data
    return pd.concat([tr.run_eba_rules(te, m), tr.run_te_checks(te)], ignore_index=True)


def breaks(res, check, lei=None):
    b = res[(res.check_id == check) & (res.status == "BREAK")]
    return b if lei is None else b[b.lei == lei]


def test_real_data_scope(data):
    # UT-40: 120 banks, 4 quarters (Sep 2024 - Jun 2025)
    te, _, _ = data
    assert te.lei.nunique() == 120 and sorted(te.period.unique()) == [202409, 202412, 202503, 202506]


def test_every_mapped_item_is_a_real_corep_cell(data):
    # UT-41: the item -> cell map only uses cells that exist in the EBA 4.0 taxonomy
    _, _, m = data
    index = datapoint_index()
    cells = {(r.template, r.row, r.col) for r in m.dropna(subset=["template"]).itertuples()}
    assert cells and cells <= set(index)


def test_eba_rules_only_run_when_all_their_cells_are_published(data, results):
    # UT-42: no rule is judged on missing data
    te, _, m = data
    published = {(r.lei, r.period, r.item) for r in te.itertuples()}
    item_of = {(r.template, r.row, r.col): r.item for r in m.dropna(subset=["template"]).itertuples()}
    expr = {r["rule_id"]: r["expression"] for r in load_rules()}
    sample = results[results.basis == "EBA validation rule"].sample(300, random_state=1)
    for r in sample.itertuples():
        assert all((r.lei, r.period, item_of[c]) in published for c in CELL.findall(expr[r.check_id]))


def test_known_findings(results):
    # UT-43: the findings documented in docs/REAL_DATA.md
    assert len(breaks(results, "v4886_m_20", "529900HEKOENJHPNN480")) == 2          # MuniFin CET1 ratio > 100%
    lf = breaks(results, "TE-06", "549300C6TUMDXNOVXS82")                             # Lansforsakringar
    assert list(lf.period) == [202503] and lf.difference_eur_m.iloc[0] == pytest.approx(296.84, abs=0.01)
    assert set(results[results.status == "BREAK"].lei) == {
        "529900HEKOENJHPNN480", "EV2XZWMLLXF2QRX0CD47", "549300C6TUMDXNOVXS82", "3M5E1GQGKL17HI6CPN30",
        "XXXXXXXXXXXXXXXXXXXX"}


def test_ratio_rules_pass_for_every_bank_quarter(results):
    # UT-44: CET1 / T1 / total capital = TREA x ratio (v0218, v0220, v0222) holds for all 469 bank-quarters
    for rule in ["v0218_m_0", "v0220_m_0", "v0222_m_0"]:
        r = results[results.check_id == rule]
        assert len(r) == 469 and (r.status == "pass").all()


def test_planted_error_in_real_data_is_caught(data):
    # UT-45: add EUR 10m to one bank's CET1 -> both the EBA ratio rule and the component check break
    te, _, m = data
    lei = "549300C6TUMDXNOVXS82"
    broken = te.copy()
    hit = (broken.lei == lei) & (broken.period == 202506) & (broken["item"] == "2520102")
    broken.loc[hit, "amount"] += 10
    one = broken[(broken.lei == lei) & (broken.period == 202506)]
    res = pd.concat([tr.run_eba_rules(one, m), tr.run_te_checks(one)])
    failed = set(res[res.status == "BREAK"].check_id)
    assert {"v0218_m_0", "TE-01"} <= failed
