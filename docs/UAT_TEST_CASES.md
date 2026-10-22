# UAT Test Cases

All cases are automated (`python -m pytest`, 33 tests) and run in CI on every change.

| ID | Requirement | Given / When / Then | Test |
|---|---|---|---|
| UT-01 | FR-04 | Italian government bond, CQS 3, in EUR → 0% under Art 114(4), not 50% | `test_eu_sovereign_in_euro_is_zero_even_below_cqs1` |
| UT-02 | FR-04 | Turkish government bond in USD, CQS 5 → 100% | `test_non_eu_sovereign_uses_rating_table` |
| UT-03 | FR-04 | Short-term interbank placements at CQS 1-3 → 20%; long-term CQS 2 → 30% | `test_institution_short_term_table` |
| UT-04 | FR-04 | Mortgage: secured part = min(exposure, 55% × property) at 20%, remainder at 75%, parts add up to the exposure | `test_mortgage_loan_splitting` |
| UT-05 | FR-02/03 | Mortgage without a property value → retail 75% | `test_mortgage_without_valuation_falls_back_to_retail` |
| UT-06 | FR-02/03 | Exposure without a counterparty type → corporate class, rating table applies | `test_missing_counterparty_type_falls_back_to_corporate` |
| UT-07 | FR-04 | Defaulted: 150% if provision < 20%, else 100% | `test_defaulted_risk_weight_depends_on_provision_cover` |
| UT-08 | FR-04 | DTA from temporary differences below threshold → 250% | `test_deferred_tax_asset_below_threshold_weighted_250` |
| UT-09 | FR-04 | Off-balance CCFs 10 / 20 / 40 / 100% | `test_off_balance_ccfs` |
| — | FR-03 | Every exposure classified exactly once with a weight | `test_every_exposure_gets_exactly_one_class_and_a_weight` |
| UT-10 | FR-06 | T2 maturing 30 May 2028 counts 881/1,826 at 31 Dec 2025 | `test_tier2_amortisation_in_final_five_years` |
| UT-11 | FR-05 | Business indicator recomputed by hand from the 3-year inputs | `test_business_indicator_by_hand` |
| UT-12 | FR-06 | CET1 = 577,610,000, rebuilt by hand from the ledger | `test_cet1_built_from_ledger` |
| UT-13 | FR-06 | Profit 48m less foreseeable dividend 20m → 28m eligible | `test_foreseeable_dividend_reduces_eligible_profit` |
| UT-14 | FR-07 | Ratios = capital / TREA; CET1 part of TSCR = 5.63% | `test_ratios_are_own_funds_over_trea` |
| UT-15 | FR-08 | Leverage exposure and ratio rebuilt by hand | `test_leverage_ratio_by_hand` |
| UT-16 | FR-10 | Interval arithmetic: values reported to the thousand compare with ±500 | `test_interval_equality_uses_declared_accuracy` |
| UT-17 | FR-10 | EBA rule syntax (if/then/else, =) translates correctly | `test_rule_translation` |
| UT-18 | FR-10 | The report passes every applicable EBA rule; none left unevaluated | `test_report_passes_every_applicable_eba_rule` |
| UT-19 | FR-10 | **Planted errors:** CET1 +1m, op-risk +5m, total assets +2m, CET1 ratio +1pp → the guarding EBA rule fails (v0172, v0204, v4457, v0218) | `test_planted_errors_are_caught` (4 cases) |
| UT-20 | FR-10 | A mandatory cell removed → existence rule fails | `test_removing_a_mandatory_cell_is_caught` |
| UT-21 | FR-09 | All 27 reconciliations tie | `test_all_reconciliations_tie` |
| UT-22 | — | Total capital ratio above OCR, leverage above 3% | `test_capital_well_above_requirements` |
| UT-23 | FR-11 | Packages follow the EBA sample layout; every datapoint id exists in the taxonomy | `test_xbrl_csv_packages_match_eba_layout` |
| UT-24 | FR-11 | Same inputs → byte-identical packages | `test_packages_are_reproducible` |
| UT-25 | FR-13 | **CR-001 regression:** exactly the 38 cells on the agreed impact list change, no other cell | `test_only_the_agreed_cells_change` |
| UT-26 | FR-13 | C 01.00 and C 47.00 unchanged by a buffer rate or a collateral value | `test_own_funds_and_leverage_untouched` |
| UT-27 | FR-07 | CCyB 0.75% → 1.00% raises OCR from 13.25% to 13.50% | `test_ccyb_raises_ocr_by_25bp` |
| UT-28 | FR-04 | A fresh valuation moves a mortgage into loan-splitting (20% / 75%) | `test_fresh_valuation_moves_mortgage_to_secured_class` |
| UT-29 | FR-14 | A 2021 valuation is rejected (DQ-09) and the mortgage stays retail | `test_stale_valuation_is_rejected_not_used` |
