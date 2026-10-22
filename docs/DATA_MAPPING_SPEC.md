# Data Mapping Specification — ledger and sub-ledger to COREP cells

Every reported cell is traced to its source here. The machine-readable versions are the decision
tables in `config/`, so a mapping change is a reviewed data change, not a code change.

## 1. Sources

| Source | Grain | Feeds |
|---|---|---|
| `data/general_ledger.csv` | GL account (42 accounts, balance sheet + P&L) | C 01.00, C 47.00 r0190, reconciliations |
| `data/exposures.csv` | Exposure (3,155 rows) | C 02.00 credit risk rows |
| `data/off_balance.csv` | Commitment (515 rows) | C 02.00 (via CCF), C 47.00 r0150-r0180 |
| `data/capital_instruments.csv` | Instrument (4) | C 01.00 r0551 (AT1), r0771 (T2) |
| `data/derivatives.csv` | Trade (26), CR-002 | C 34.03, C 34.01, C 25.01, C 22.00 (forwards), C 02.00 r0120/r0125, C 47.00 r0061/r0091 |
| `data/total_assets_history.csv` | Month-end (3) | C 34.01 r0040 |
| `config/sa_ccr.yaml` | Supervisory parameters | Alpha, supervisory factors, CVA exemptions, FX de minimis |
| `data/property_valuations_2025Q4.csv` | Valuation (6), from the collateral system (CR-001) | Property value for loan-splitting, if ≤ 3 years old (`sql/05_collateral.sql`) |
| `data/pl_history.csv` | Year × P&L item (2023-2025) | C 02.00 r0590 operational risk |
| `config/srep.yaml` | Supervisory parameters | C 03.00 r0130-r0210, C 47.00 r0410-r0470 |

## 2. Credit risk: sub-ledger → exposure class → C 02.00 row

Decision table `config/dt_exposure_class.csv`; the first matching rule by priority wins (`sql/10_credit_risk.sql`, step 1).

| # | Counterparty type | Product | Default | Property value | → Class | C 02.00 row | CRR |
|---|---|---|---|---|---|---|---|
| 1 | any | any | yes | any | Exposures in default | 0160 | Art 127 |
| 2-3 | central bank / government | any | no | any | Central governments | 0070 | Art 114 |
| 4 | institution | any | no | any | Institutions | 0120 | Art 119-121 |
| 5 | corporate | any | no | any | Corporates - Other | 0125 | Art 122 |
| 6 | **blank (data gap)** | any | no | any | Corporates - Other | 0125 | Art 122 |
| 7 | retail | residential mortgage | no | present | Secured by residential property: 0151 secured part / 0152 remainder | 0150 | Art 124-125 |
| 8 | retail | residential mortgage | no | **missing (data gap)** | Retail | 0140 | Art 123-124 |
| 9 | retail | other | no | any | Retail | 0140 | Art 123 |
| 10 | other | any | no | any | Other items | 0211 | Art 134 |

Risk weights: `config/dt_risk_weight.csv` (rating tables of Art 114, 120, 122), `config/dt_other_items.csv`
(Art 134, Art 48(4)), plus three rules coded in SQL because they depend on more than one field:
Art 114(4) EU sovereign in euro → 0%, Art 125 loan-splitting, Art 127 provision-cover test.

Off-balance: `config/dt_ccf.csv` gives the SA CCF (C 02.00) and the leverage CCF (C 47.00 row).

## 3. Own funds: GL → C 01.00

Mapping table `config/map_own_funds.csv`. **One sign rule:** reported value = −1 × GL balance. Equity is
a credit (negative) in the ledger, so it reports positive; deducted assets are debits (positive), so
they report negative, as COREP's "(-)" rows require.

| C 01.00 row | Item | Source | Value (EUR) |
|---|---|---|---|
| 0040 | Paid-up capital | GL 3000 | 200,000,000 |
| 0060 | Share premium | GL 3100 | 150,000,000 |
| 0140 | Previous years retained earnings | GL 3200 | 281,000,000 |
| 0160 | Profit of the year | all P&L accounts 4000-5900 | 48,000,000 |
| 0170 | (-) Foreseeable dividend | `srep.yaml` | −20,000,000 |
| 0180 | Accumulated OCI | GL 3300 | −15,000,000 |
| 0200 | Other reserves | GL 3400 | 25,000,000 |
| 0290 | (-) Prudent valuation | 0.1% × GL 1120 | −390,000 |
| 0310 | (-) Goodwill | GL 1600 | −40,000,000 |
| 0350 / 0352 | (-) Intangibles / of which software | GL 1610+1620 / 1610 | −45,000,000 / −35,000,000 |
| 0360 | DTL on intangibles | GL 2810 | 6,000,000 |
| 0370 | (-) DTA on tax losses | GL 1810 | −12,000,000 |
| 0490 | (-) DTA temporary differences above 10% threshold | GL 1820 vs 10% CET1 | 0 |
| 0551 | AT1 instrument | instruments, tier AT1 | 75,000,000 |
| 0771 | T2 instruments after Art 64 amortisation | instruments, tier T2 | 198,247,536 |

Totals (r0010, 0015, 0020, 0030, 0130, 0150, 0250, 0300, 0340, 0530, 0540, 0750, 0760) are built
exactly as the EBA validation rules define them (v0172, v0182, v0186, v1771, v23596 …), so the
template is internally consistent by construction, and the rules check it again independently.

## 4. Leverage ratio: → C 47.00

| Row | Item | Source |
|---|---|---|
| 0150 / 0160 / 0165 / 0180 | Off-balance at 10% / 20% / 40% / 100% CCF | `off_balance` × `dt_ccf.lr_ccf` |
| 0061 / 0091 | Derivatives: replacement cost / PFE (multiplier 1), × 1.4 | `corep/derivatives.py` per netting set |
| 0190 | Other assets (on-balance, not derivatives or SFTs) | sum of asset GL accounts except 1150 (derivative assets) |
| 0270 / 0280 | (-) Assets deducted from Tier 1 | C 01.00 r0290 + 0310 + 0340 + 0370 + 0490 |
| 0290 / 0300 | Total exposure measure | EBA rule v4457 / v4458 |
| 0310 / 0320 | Tier 1 | C 01.00 r0015 |
| 0330 / 0340 | Leverage ratio | r0310 / r0290 |
| 0410-0470 | Requirements | `srep.yaml` leverage block |

## 5. Derivatives (CR-002)

| Cell | Item | Source / rule |
|---|---|---|
| C 34.03 r0010-r0140 | Trades, notional, positive/negative market value, add-on by risk category; largest currency EUR, pair EUR/USD | Trade level; add-ons per netting set (Art 280a, 280c), summed |
| C 34.01 r0010-r0050 | Long / short market values, total assets, % — per month | `mtm_2025_10_31/11_30/12_31`, `total_assets_history` |
| C 25.01 r0010-r0020 | CVA in scope: CCR exposure, CCR own funds, simplified-approach own funds, REA | Bank netting sets; own funds = RWEA / 12.5 (Art 385) |
| C 25.01 r0040-r0070 | Exempt: EU non-financial counterparties, marginal impact | Corporate netting sets (Art 382(4)(a)) |
| C 22.00 r0010/r0030/r0380 | USD long 110m (bonds), short 80m (forwards), net 30m, 8% own funds | Sub-ledger exposures in USD + forward notionals (Art 352) |
| C 02.00 r0120 / r0125 | + CCR RWEA of bank / corporate netting sets | SA-CCR exposure × Art 120 / 122 risk weight |

## 6. Output: cell → xBRL-CSV datapoint

`taxonomy/datapoints.csv` (extracted from the EBA 4.0 taxonomy by `scripts/extract_taxonomy.py`)
maps every cell to its datapoint id and type (m = monetary, p = percentage, e = enumeration).
`corep/xbrl_csv.py` writes one `datapoint,factValue` file per template, and the run stops if a
calculated cell has no datapoint in the taxonomy.
