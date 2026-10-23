# Basel III COREP Reporting — capital, credit, counterparty, market and CVA risk, leverage

**From a bank's general ledger and trading records to a validated EBA regulatory submission.**
Built under the CRR as amended by CRR3, checked against the **EBA's own validation rules**, and
written in the EBA 4.0 **xBRL-CSV** format. It covers 9 COREP templates:

| Template | What it reports | Risk |
|---|---|---|
| C 01.00 | Own funds: CET1, AT1, Tier 2 and every deduction | Capital |
| C 02.00 | Risk exposure amounts by risk type and exposure class | All |
| C 03.00 | Capital ratios and the requirement stack (Pillar 1, P2R, buffers, P2G) | Capital |
| C 22.00 | Foreign-exchange position and own funds requirement | **Market risk** |
| C 25.01 | CVA risk, simplified approach, with exempted transactions | **CVA risk** |
| C 34.01 | Size of the derivative business, month by month | **Counterparty credit risk** |
| C 34.03 | SA-CCR: notionals, market values and add-ons by risk category | **Counterparty credit risk** |
| C 47.00 | Leverage ratio exposure measure, including derivatives | Leverage |
| C 00.01 | Report header | — |

| Demo Bank AG, 31 Dec 2025 | | |
|---|---|---|
| Total assets | €6,303.2m | GL |
| CET1 / Tier 1 / Own funds | €577.6m / €652.6m / €850.9m | C 01.00 |
| Total risk exposure amount | €3,693.6m = credit 3,320.7 + **counterparty 27.9** + **market 30.0** + operational 309.7 + **CVA 5.3** | C 02.00 |
| CET1 / Tier 1 / Total capital ratio | **15.64% / 17.67% / 23.04%** vs OCR 13.50% | C 03.00 |
| Derivatives book | 26 trades, €1.96bn notional, 6 netting sets → SA-CCR exposure €47.1m | C 34.03 |
| Leverage ratio | **9.97%** vs 3% | C 47.00 |

| Control | Result |
|---|---|
| EBA validation rules on these templates (from the official taxonomy) | **453 / 453 applicable rules pass**, 0 fail (975 n/a: no IRB, IMM, securitisation or trading book) |
| Planted-error tests | 7 / 7 deliberately broken cells caught by the EBA rule that guards them |
| Reconciliations, books → report | **32 / 32 tie** (sub-ledger ↔ GL by account, derivative fair values ↔ GL, balance sheet ↔ leverage, equity ↔ own funds, P&L ↔ business indicator, FX position ↔ sub-ledger) |
| Data-quality rules | 13 rules; gaps found and handled conservatively (4 exposures without a type, 1 mortgage with a stale valuation) |
| Change control | **CR-001** (buffer rate + collateral feed): 38 cells predicted, 38 changed, 0 unexpected. **CR-002** (derivatives, CCR, market risk, CVA): 153 cells predicted, 153 changed, 0 unexpected ([change records](docs/changes/)) |
| Tests | 51, run in CI |

> **The bank is synthetic.** Real bank data is confidential, so `scripts/generate_bank.py` creates
> the books of a fictional mid-sized EU bank (fixed seed). **The regulation, templates, datapoints
> and validation rules are real**, taken from the CRR and the EBA's published 4.0 taxonomy.

## Real banks: EBA rules on 120 banks' published COREP figures

The same EBA rules also run on **real data**: the EBA's 2025 Transparency Exercise, with figures from
the COREP submissions of **120 EU banks over 4 quarters** (469 bank-quarters). Each published item is
placed in its COREP cell, and a rule runs only when every cell it uses is published.

| | |
|---|---|
| Checks run (44 EBA rules + 9 cross-template checks) | **23,919** |
| Pass / break | **23,893 / 26**, in 5 banks |
| Findings | 2 public-sector lenders with capital ratios above 100% (genuine, flagged by EBA rule v4886); Tier 1 in the leverage template ≠ Tier 1 in own funds at 3 banks (up to €408m); one bank's RWA overview €464m below its TREA |

Every break is explained in **[REAL_DATA.md](docs/REAL_DATA.md)**. Run: `python -m corep.transparency`.

---

## See it

`site/` is a one-page visual story of the project: the balance sheet turning into the filing, the capital stack with a live buffer slider, 3,155 loans by risk weight, the SA-CCR waterfall, a "break the report" wall of the 453 EBA rules, both change requests, and the 120 real banks. Every number comes from `site/data.json`, exported from the pipeline by `scripts/export_site_data.py`. Open it locally with `python -m http.server --directory site`. Add `?film` to the URL for a self-playing version used to record the walkthrough.

## How it works

```
 general ledger ─┐
 risk sub-ledger ┤                    decision tables (SQL)      own funds, RWEA,
 off-balance     ├─► data-quality ─►  exposure class, risk  ─►  SA-CCR, CVA, FX risk, ─► EBA validation ─► xBRL-CSV
 derivatives     │    DQ-01..13       weight, CCF, SA-CCR        ratios, leverage          rules (453)       packages
 collateral feed │                    supervisory factors        │                                           + readable
 P&L history    ─┘                                               └─► reconciliations REC-01..11              templates
```

1. **Taxonomy extract** — `scripts/extract_taxonomy.py` reads the EBA 4.0 taxonomy and keeps the
   1,073 cells (with their xBRL-CSV datapoint ids) and the 1,428 validation rules for these templates.
2. **Data quality** — blocking rules stop the run; warnings apply a documented, conservative fallback
   ([DATA_GAPS.md](docs/DATA_GAPS.md)).
3. **Mapping as data** — exposure class, risk weight, CCF, own-funds mapping and SA-CCR supervisory
   parameters live in `config/`, applied in DuckDB SQL and Python ([DATA_MAPPING_SPEC.md](docs/DATA_MAPPING_SPEC.md)).
4. **Calculations**
   - **Credit risk:** standardised approach (incl. Art 114(4), Art 125 loan-splitting, Art 127).
   - **Counterparty credit risk:** SA-CCR (Art 274-280a), with replacement cost, PFE and the multiplier per netting set.
   - **CVA risk:** simplified approach (Art 385), with the non-financial counterparty exemption (Art 382(4)).
   - **Market risk:** FX on the whole balance sheet (Art 351-354).
   - **Operational risk:** via the Business Indicator Component.
   - **Own funds:** deductions (Art 36, 48), Tier 2 amortisation (Art 64), capital ratios with the requirement stack.
   - **Leverage:** exposure measure including derivatives at SA-CCR with multiplier 1 (Art 429c).
5. **EBA validation rules** — evaluated with the interval arithmetic the EBA formula engine uses.
6. **Submission** — xBRL-CSV report packages in the layout of the EBA's own 4.0 samples.

## Run it

```bash
pip install -r requirements.txt
python scripts/generate_bank.py   # (re)create the synthetic books
python -m corep.pipeline          # build, reconcile, validate, write out/
python -m corep.transparency      # EBA rules on 120 real banks (CR-003)
python -m pytest                  # 51 tests
```

## Documents

- **[Regulation notes](docs/REGULATION_NOTES.md)** — the regulation in plain English, with every Demo Bank figure explained
- [Functional specification](docs/FUNCTIONAL_SPEC.md) — scope, requirements FR-01..FR-18, assumptions
- [Data mapping specification](docs/DATA_MAPPING_SPEC.md) — every cell traced to its source
- [Data gaps](docs/DATA_GAPS.md) — data-quality rules and fallbacks
- **[Real-bank checks](docs/REAL_DATA.md)** — EBA rules on 120 banks' published figures, every break explained
- [UAT test cases](docs/UAT_TEST_CASES.md) — 45 cases traced to requirements and tests
- Change records: [CR-001](docs/changes/CR-001.md) (buffer rate + collateral feed), [CR-002](docs/changes/CR-002.md) (derivatives, CCR, market risk, CVA)
- [Taxonomy extract](taxonomy/README.md) — source and validation approach

## Outputs (`out/`)

The two `.zip` files are the submission. Supporting outputs:
- `corep_templates.csv` shows every reported cell readably.
- `eba_validation_results.csv` shows each rule with the values it used.
- `reconciliation.csv` and `data_quality.csv` show the controls.
- `credit_risk_by_exposure.csv` and `sa_ccr_by_netting_set.csv` give the RWEA of every exposure and netting set.

## Stack

Python · DuckDB (SQL) · pandas · XBRL / xBRL-CSV · pytest · GitHub Actions

EBA taxonomy © European Banking Authority, reproduced in part with acknowledgement.
