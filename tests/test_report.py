"""The report as a whole: EBA rules, planted errors, reconciliations and the xBRL-CSV package (UT-16..UT-24)."""

import csv
import io
import json
import zipfile

import pytest

from corep import eba_rules
from corep.eba_rules import Iv, to_python
from corep.pipeline import build, main


@pytest.fixture(scope="module")
def built():
    con, p, dq, opr, cells, index = build()
    types = {c: m["type"] for c, m in index.items()}
    return cells, types, index


@pytest.fixture(scope="module")
def summary(tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    return main(out), out


def failures(cells, types):
    return [r for r in eba_rules.evaluate(cells, types) if r["status"] == "FAIL"]


def test_interval_equality_uses_declared_accuracy():
    # UT-16: 1,000,000 reported to the thousand equals 1,000,400 but not 1,001,200
    a = Iv(999_500, 1_000_500)
    assert a == Iv(1_000_400 - 500, 1_000_400 + 500)
    assert not (a == Iv(1_001_200 - 500, 1_001_200 + 500))


def test_rule_translation():
    # UT-17
    e = to_python("if ({C_03.00,0020,0010,} < 0) then ({C_03.00,0010,0010,} < 0.045) else True")
    assert e == '(((v("C_03.00","0010","0010") < 0.045)) if ((v("C_03.00","0020","0010") < 0)) else (True))'
    assert "==" in to_python("{C_01.00,0015,0010,} = {C_01.00,0020,0010,} + {C_01.00,0530,0010,}")


def test_report_passes_every_applicable_eba_rule(built):
    # UT-18
    cells, types, _ = built
    results = eba_rules.evaluate(cells, types)
    assert not [r for r in results if r["status"] in ("FAIL", "not evaluated")]
    assert sum(r["status"] == "pass" for r in results) > 200


@pytest.mark.parametrize("cell, delta, rule", [
    (("C_01.00", "0020", "0010"), 1_000_000, "v0172_m_0"),   # CET1 no longer equals its components
    (("C_02.00.a", "0590", "0010"), 5_000_000, "v0204_m_0"),  # op risk changed without the TREA total
    (("C_47.00", "0190", "0010"), 2_000_000, "v4457_m_0"),   # leverage exposure no longer adds up
    (("C_03.00", "0010", "0010"), 0.01, "v0218_m_0"),        # CET1 ratio inconsistent with CET1 / TREA
])
def test_planted_errors_are_caught(built, cell, delta, rule):
    # UT-19: change one reported cell and the EBA rule that guards it must fail
    cells, types, _ = built
    broken = dict(cells)
    broken[cell] = cells[cell] + delta
    failed = {r["rule_id"] for r in failures(broken, types)}
    assert rule in failed


def test_removing_a_mandatory_cell_is_caught(built):
    # UT-20: existence rules
    cells, types, _ = built
    broken = {k: v for k, v in cells.items() if k != ("C_03.00", "0130", "0010")}
    assert failures(broken, types)


def test_all_reconciliations_tie(summary):
    # UT-21
    s, out = summary
    rec = list(csv.DictReader(open(out / "reconciliation.csv", encoding="utf-8")))
    assert all(r["status"] == "RECONCILED" for r in rec), [r for r in rec if r["status"] != "RECONCILED"]


def test_capital_well_above_requirements(summary):
    # UT-22: sanity of the outcome, not a rule: CET1 ratio above OCR, leverage above 3%
    s, _ = summary
    assert s["total_capital_ratio"] > s["ocr"]
    assert s["leverage_ratio"] > 0.03


def test_xbrl_csv_packages_match_eba_layout(summary, built):
    # UT-23: same structure as the EBA 4.0 sample packages; every datapoint id exists in the taxonomy
    s, out = summary
    _, _, index = built
    known = {m["datapoint"] for m in index.values()}
    for name in s["packages"]:
        with zipfile.ZipFile(out / name) as z:
            files = {n.split("/", 1)[1]: z.read(n).decode() for n in z.namelist()}
        assert json.loads(files["META-INF/reportPackage.json"])["documentInfo"]["documentType"].endswith("report-package/2023")
        extends = json.loads(files["reports/report.json"])["documentInfo"]["extends"][0]
        assert extends.startswith("http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/corep/4.0/mod/")
        params = dict(csv.reader(io.StringIO(files["reports/parameters.csv"])))
        assert params["entityID"].startswith("rs:") and params["baseCurrency"] == "iso4217:EUR"
        for rel, text in files.items():
            if rel.startswith("reports/c_"):
                rows = list(csv.DictReader(io.StringIO(text)))
                assert rows and all(r["datapoint"] in known for r in rows)


def test_packages_are_reproducible(tmp_path, summary):
    # UT-24: same inputs -> byte-identical packages
    s, out = summary
    again = main(tmp_path)
    for name in s["packages"]:
        assert (out / name).read_bytes() == (tmp_path / name).read_bytes()
