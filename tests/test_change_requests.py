"""CR-001 regression and acceptance tests (UT-25..UT-29).

The baseline report (tests/baseline/corep_templates_v1.csv) is the submission before CR-001. The
impact list (docs/changes/CR-001_expected_cells.csv) was written from the regulation before the
change was built. A change is accepted only if exactly those cells move.
"""

import importlib.util
from pathlib import Path

import pytest

from corep import ROOT
from corep.books import connect, run_sql
from corep.pipeline import main

spec = importlib.util.spec_from_file_location("impact", ROOT / "scripts" / "impact_analysis.py")
impact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(impact)


@pytest.fixture(scope="module")
def changed(tmp_path_factory):
    out = tmp_path_factory.mktemp("cr001")
    summary = main(out)
    diff = impact.diff(impact.load(ROOT / "tests/baseline/corep_templates_v1.csv"), impact.load(out / "corep_templates.csv"))
    return summary, diff


@pytest.fixture(scope="module")
def con():
    c = connect()
    run_sql(c, "05_collateral.sql")
    run_sql(c, "10_credit_risk.sql")
    return c


def test_only_the_agreed_cells_change(changed):
    # UT-25 regression: no cell outside the impact list moves, and every listed cell does
    _, diff = changed
    unexpected, missed = impact.check(diff, str(ROOT / "docs/changes/CR-001_expected_cells.csv"))
    assert not unexpected, unexpected
    assert not missed, missed


def test_own_funds_and_leverage_untouched(changed):
    # UT-26: neither a buffer rate nor a collateral value changes capital or the leverage measure
    _, diff = changed
    assert not diff[diff.template.isin(["C_01.00", "C_47.00"])].shape[0]


def test_ccyb_raises_ocr_by_25bp(changed):
    # UT-27 CRD Art 128, 130: OCR = TSCR + combined buffer; CCyB 0.75% -> 1.00%
    _, diff = changed
    ocr = diff[(diff.template == "C_03.00") & (diff.row == "0160")].iloc[0]
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
