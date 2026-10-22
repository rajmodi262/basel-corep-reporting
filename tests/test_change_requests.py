"""Change-request regression and acceptance tests (CR-001: UT-25..UT-29, CR-002: UT-38..UT-39).

Each change has a frozen "before" report (tests/baseline/) and an impact list written from the
regulation before the change was built (docs/changes/CR-00x_expected_cells.csv). A change is
accepted only if exactly those cells move.

- CR-001 is history: v1 -> v2 are both frozen, so its evidence stays checkable after later changes.
- CR-002 is the current change: v2 -> the report the pipeline produces now.
"""

import importlib.util

import pytest

from corep import ROOT
from corep.books import connect, run_sql
from corep.pipeline import main

spec = importlib.util.spec_from_file_location("impact", ROOT / "scripts" / "impact_analysis.py")
impact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(impact)

BASE = ROOT / "tests" / "baseline"
CHANGES = ROOT / "docs" / "changes"


@pytest.fixture(scope="module")
def cr001():
    return impact.diff(impact.load(BASE / "corep_templates_v1.csv"), impact.load(BASE / "corep_templates_v2.csv"))


@pytest.fixture(scope="module")
def cr002(tmp_path_factory):
    out = tmp_path_factory.mktemp("cr002")
    main(out)
    return impact.diff(impact.load(BASE / "corep_templates_v2.csv"), impact.load(out / "corep_templates.csv"))


@pytest.fixture(scope="module")
def con():
    c = connect()
    run_sql(c, "05_collateral.sql")
    run_sql(c, "10_credit_risk.sql")
    return c


# ---------------------------------------------------------------- CR-001
def test_cr001_only_the_agreed_cells_change(cr001):
    # UT-25 regression: no cell outside the impact list moved, and every listed cell did
    unexpected, missed = impact.check(cr001, str(CHANGES / "CR-001_expected_cells.csv"))
    assert not unexpected and not missed, (unexpected, missed)


def test_cr001_own_funds_and_leverage_untouched(cr001):
    # UT-26: neither a buffer rate nor a collateral value changes capital or the leverage measure
    assert not cr001[cr001.template.isin(["C_01.00", "C_47.00"])].shape[0]


def test_cr001_ccyb_raises_ocr_by_25bp(cr001):
    # UT-27 CRD Art 128, 130: OCR = TSCR + combined buffer; CCyB 0.75% -> 1.00%
    ocr = cr001[(cr001.template == "C_03.00") & (cr001.row == "0160")].iloc[0]
    assert float(ocr.value_old) == 0.1325 and float(ocr.value_new) == 0.135


def test_fresh_valuation_moves_mortgage_to_secured_class(con):
    # UT-28 Art 125: valued in Nov 2025 -> loan-splitting applies
    rows = dict(con.execute("SELECT part_row, risk_weight FROM credit_rwa WHERE exposure_id = 'EXP-MTG-00014'").fetchall())
    assert rows == {"0151": 0.20, "0152": 0.75}
    src = con.execute("SELECT valuation_source FROM exposures_enriched WHERE exposure_id = 'EXP-MTG-00014'").fetchone()[0]
    assert src == "collateral feed 2025-11-14"


def test_stale_valuation_is_rejected_not_used(con):
    # UT-29 Art 208(3): a June 2021 valuation is older than 3 years -> reported by DQ-09, mortgage stays retail
    assert [r[0] for r in con.execute("SELECT exposure_id FROM stale_valuations").fetchall()] == ["EXP-MTG-00960"]
    assert con.execute("SELECT exposure_class FROM credit_rwa WHERE exposure_id='EXP-MTG-00960'").fetchone()[0] == "retail"


# ---------------------------------------------------------------- CR-002
def test_cr002_only_the_agreed_cells_change(cr002):
    # UT-38 regression: 4 new templates plus the predicted C 02.00 / C 03.00 / C 47.00 cells; nothing else
    unexpected, missed = impact.check(cr002, str(CHANGES / "CR-002_expected_cells.csv"))
    assert not unexpected and not missed, (unexpected, missed)


def test_cr002_capital_and_on_balance_leverage_untouched(cr002):
    # UT-39: derivatives change risk, not capital; derivative assets leave C 47.00 r0190 for r0061/r0091
    assert not cr002[cr002.template == "C_01.00"].shape[0]
    assert not cr002[(cr002.template == "C_47.00") & (cr002.row == "0190")].shape[0]
