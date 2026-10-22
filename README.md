# Basel III COREP Reporting — own funds and leverage ratio

**From a bank's general ledger to a validated EBA regulatory submission:** capital (C 01.00),
risk-weighted assets (C 02.00), capital ratios (C 03.00) and the leverage ratio (C 47.00), built
under the CRR as amended by CRR3, checked against the **EBA's own validation rules**, and written in
the EBA 4.0 **xBRL-CSV** format.

| Demo Bank AG, 31 Dec 2025 | | |
|---|---|---|
| Total assets | €6,293.4m | C 47.00 r0190 |
| CET1 / Tier 1 / Own funds | €577.6m / €652.6m / €850.9m | C 01.00 |
| Total risk exposure amount | €3,630.4m (credit 3,320.7 + operational 309.7) | C 02.00 |
| CET1 / Tier 1 / Total capital ratio | **15.91% / 17.98% / 23.44%** vs OCR 13.50% | C 03.00 |
| Leverage ratio | **10.06%** vs 3% | C 47.00 |

| Control | Result |
|---|---|
| EBA validation rules on these templates (from the official taxonomy) | **216 / 216 applicable rules pass**, 0 fail (290 n/a: no IRB, trading book or derivatives) |
| Planted-error tests | 4 / 4 deliberately broken cells caught by the EBA rule that guards them |
| Reconciliations, books → report | **27 / 27 tie** (sub-ledger ↔ GL by account, balance sheet ↔ leverage, equity ↔ own funds, P&L ↔ business indicator) |
| Data-quality rules | 10 rules; gaps found and handled conservatively (4 exposures without a type, 1 mortgage with a stale valuation) |
| Change control | **CR-001** (buffer rate + collateral feed): 38 cells predicted from the regulation, 38 changed, **0 unexpected** ([change record](docs/changes/CR-001.md)) |
| Tests | 33, run in CI |

> **The bank is synthetic.** Real bank data is confidential, so `scripts/generate_bank.py` creates
> the books of a fictional mid-sized EU bank (fixed seed). **The regulation, templates, datapoints
> and validation rules are real**, taken from the CRR and the EBA's published 4.0 taxonomy.

---

## How it works

```
 general ledger ─┐
 risk sub-ledger ┤─► data-quality ─► decision tables (SQL) ─► own funds, RWEA, ─► EBA validation ─► xBRL-CSV
 off-balance     │    rules DQ-01..10   exposure class,          ratios, leverage    rules (216)       packages
 P&L history    ─┘                      risk weight, CCF          │                                    + readable
                                                                  └─► reconciliations REC-01..08       templates
```

1. **Taxonomy extract** — `scripts/extract_taxonomy.py` reads the EBA 4.0 taxonomy and keeps the
   410 cells (with their xBRL-CSV datapoint ids) and the 506 validation rules for these templates.
2. **Data quality** — blocking rules stop the run; warnings apply a documented, conservative fallback
   ([DATA_GAPS.md](docs/DATA_GAPS.md)).
3. **Mapping as data** — exposure class, risk weight, CCF and own-funds mapping live in `config/`
   decision tables, applied in DuckDB SQL ([DATA_MAPPING_SPEC.md](docs/DATA_MAPPING_SPEC.md)).
4. **Calculations** — standardised-approach credit risk (incl. Art 114(4), Art 125 loan-splitting,
   Art 127), operational risk via the Business Indicator Component, own-funds deductions (Art 36),
   threshold deductions (Art 48), T2 amortisation (Art 64), capital ratios with the full requirement
   stack, and the leverage exposure measure.
5. **EBA validation rules** — evaluated with the interval arithmetic the EBA formula engine uses.
6. **Submission** — xBRL-CSV report packages in the layout of the EBA's own 4.0 samples.

## Run it

```bash
pip install -r requirements.txt
python scripts/generate_bank.py   # (re)create the synthetic books
python -m corep.pipeline          # build, reconcile, validate, write out/
python -m pytest                  # 33 tests
```

## Documents

- **[Regulation notes](docs/REGULATION_NOTES.md)** — the regulation in plain English, with every Demo Bank figure explained
- [Functional specification](docs/FUNCTIONAL_SPEC.md) — scope, requirements FR-01..FR-12, assumptions
- [Data mapping specification](docs/DATA_MAPPING_SPEC.md) — every cell traced to its source
- [Data gaps](docs/DATA_GAPS.md) — data-quality rules and fallbacks
- [UAT test cases](docs/UAT_TEST_CASES.md) — 29 cases traced to requirements and tests
- [CR-001 change record](docs/changes/CR-001.md) — a regulatory change run end to end: request, impact analysis, spec update, regression
- [Taxonomy extract](taxonomy/README.md) — source and validation approach

## Outputs (`out/`)

The two `.zip` files are the submission. `corep_templates.csv` shows every reported cell readably,
`eba_validation_results.csv` shows each rule with the values it used, `reconciliation.csv` and
`data_quality.csv` show the controls, and `credit_risk_by_exposure.csv` gives the RWEA of every exposure.

## Stack

Python · DuckDB (SQL) · pandas · XBRL / xBRL-CSV · pytest · GitHub Actions

EBA taxonomy © European Banking Authority, reproduced in part with acknowledgement.
