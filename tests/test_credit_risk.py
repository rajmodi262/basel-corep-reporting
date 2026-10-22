"""Decision-table and risk-weight cases (UAT UT-01..UT-09), each tied to a CRR article."""

import pandas as pd
import pytest

from corep.books import connect, run_sql


@pytest.fixture(scope="module")
def con():
    c = connect()
    run_sql(c, "10_credit_risk.sql")
    return c


def rw(con, exposure_id, part=None):
    q = "SELECT risk_weight FROM credit_rwa WHERE exposure_id = ?" + (" AND part_row = ?" if part else "")
    return con.execute(q, [exposure_id] + ([part] if part else [])).fetchone()[0]


def test_eu_sovereign_in_euro_is_zero_even_below_cqs1(con):
    # UT-01 Art 114(4): Italy, CQS 3, EUR -> 0% (Table 1 alone would give 50%)
    row = con.execute("SELECT risk_weight, rw_basis FROM credit_rwa WHERE exposure_id = 'EXP-SOV-0005'").fetchone()
    assert row == (0.0, "Art 114(4)")


def test_non_eu_sovereign_uses_rating_table(con):
    # UT-02 Art 114(2): Turkey in USD, CQS 5 -> 100%
    assert rw(con, "EXP-SOV-0007") == 1.0


def test_institution_short_term_table(con):
    # UT-03 Art 120(2): short-term claims on CQS 1-3 institutions -> 20%
    df = con.execute("SELECT cqs, short_term, risk_weight FROM credit_rwa WHERE exposure_class='institution'").df()
    assert (df[df.short_term == "1"].risk_weight == 0.20).all()
    assert set(df[(df.short_term == "0") & (df.cqs == "2")].risk_weight) == {0.30}


def test_mortgage_loan_splitting(con):
    # UT-04 Art 125(1): up to 55% of property value at 20%, remainder at 75%
    e = con.execute("SELECT gross_amount - specific_provision, property_value FROM exposures "
                    "WHERE exposure_id = 'EXP-MTG-00001'").fetchone()
    parts = dict(con.execute("SELECT part_row, exposure_value FROM credit_rwa WHERE exposure_id='EXP-MTG-00001'").fetchall())
    assert parts["0151"] == pytest.approx(min(e[0], 0.55 * e[1]))
    assert parts["0151"] + parts["0152"] == pytest.approx(e[0])
    assert rw(con, "EXP-MTG-00001", "0151") == 0.20 and rw(con, "EXP-MTG-00001", "0152") == 0.75


def test_mortgage_without_valuation_falls_back_to_retail(con):
    # UT-05 data gap DQ-03: no property value -> not "secured by mortgage" -> retail 75%
    row = con.execute("SELECT exposure_class, risk_weight FROM credit_rwa WHERE exposure_id='EXP-MTG-00014'").fetchone()
    assert row == ("retail", 0.75)


def test_missing_counterparty_type_falls_back_to_corporate(con):
    # UT-06 data gap DQ-02: corporate class (never a lower-weighted class); the obligor's rating still applies
    df = con.execute("SELECT e.exposure_id, e.cqs, r.exposure_class, r.risk_weight FROM exposures e "
                     "JOIN credit_rwa r USING (exposure_id) WHERE coalesce(e.counterparty_type, '') = ''").df()
    assert len(df) == 4 and (df.exposure_class == "corporate").all()
    table6 = {"": 1.0, "1": 0.2, "2": 0.5, "3": 0.75, "4": 1.0, "5": 1.5, "6": 1.5}
    assert (df.risk_weight == df.cqs.fillna("").map(table6)).all()


def test_defaulted_risk_weight_depends_on_provision_cover(con):
    # UT-07 Art 127(1): 150% if specific provisions < 20% of the exposure, else 100%
    df = con.execute("SELECT gross_amount, specific_provision, product, risk_weight FROM credit_rwa "
                     "WHERE exposure_class = 'default'").df()
    non_mortgage = df[df["product"] != "residential_mortgage"]
    expected = (non_mortgage.specific_provision >= 0.2 * non_mortgage.gross_amount).map({True: 1.0, False: 1.5})
    assert (non_mortgage.risk_weight == expected).all()
    assert set(non_mortgage.risk_weight) == {1.0, 1.5}


def test_deferred_tax_asset_below_threshold_weighted_250(con):
    # UT-08 Art 48(4)
    assert rw(con, "EXP-OTH-0004") == 2.5


def test_off_balance_ccfs(con):
    # UT-09 Annex I: 10% / 20% / 40% / 100%
    df = con.execute("SELECT product, sa_ccf FROM off_balance_rwa GROUP BY ALL").df().set_index("product").sa_ccf
    assert df.to_dict() == {"unconditionally_cancellable_line": 0.10, "documentary_credit": 0.20,
                            "undrawn_committed_facility": 0.40, "financial_guarantee": 1.00}


def test_every_exposure_gets_exactly_one_class_and_a_weight(con):
    df = con.execute("SELECT exposure_id, risk_weight FROM credit_rwa").df()
    assert df.risk_weight.notna().all()
    n = con.execute("SELECT count(*) FROM exposures").fetchone()[0]
    assert df.exposure_id.nunique() == n
