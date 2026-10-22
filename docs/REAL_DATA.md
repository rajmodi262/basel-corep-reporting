# CR-003 — EBA validation rules on real banks' published figures

The rest of this project uses a synthetic bank, because bank books are confidential. This part uses
**real data**: the EBA's **2025 EU-wide Transparency Exercise**, which publishes figures taken from
banks' own COREP submissions.

| | |
|---|---|
| Source | EBA, 2025 EU-wide Transparency Exercise, full database (`tr_oth.csv`, `TR_Metadata.xlsx`) |
| Coverage | **120 EU banks**, 4 quarters (Sep 2024, Dec 2024, Mar 2025, Jun 2025), **469 bank-quarters**, 34,489 published values |
| Templates | Capital (C 01.00, C 03.00), RWA overview (C 02.00), Leverage (C 47.00) |
| Extract | `scripts/extract_transparency.py` → `data/real/te2025.csv.gz` (EUR millions) |

## Method

1. **Item → COREP cell.** `config/te_item_map.csv` places each published item in the cell the
   EBA's own mapping workbook names. Examples: retained earnings → C 01.00 r0130; Tier 1 → r0015;
   leverage exposure → C 47.00 r0290. All 41 single-cell mappings exist in the EBA 4.0 taxonomy (UT-41).
2. **EBA validation rules, unchanged**, run on each bank-quarter **only when every cell the rule
   uses is published** (UT-42). This applies to 44 distinct EBA rules.
3. **Transparency-level checks** (`config/te_checks.csv`) restate EBA rules where the EBA publishes
   only an aggregate (intangibles = r0300 + r0340), and add cross-template ties: leverage Tier 1 vs
   own-funds Tier 1, RWA overview total vs TREA, and the CRR3 output floor (TREA = pre-floor + floor
   adjustment).
4. **Tolerance:** published amounts are compared as intervals of ±€500 (COREP accuracy, decimals −3)
   and ratios as ±0.00005, the same interval arithmetic the EBA formula engine uses.

## Result

| | |
|---|---|
| Checks run | **23,919** |
| Pass | **23,893** |
| Breaks | **26**, in **5 banks** |
| EBA ratio rules v0218 / v0220 / v0222 (capital = TREA × ratio) | pass for all 469 bank-quarters |
| CET1, AT1, Tier 2 component checks (v0172, v0182, v0186) | pass for all 469 bank-quarters |
| Output-floor structure (TREA = pre-floor + floor adjustment, 2025 quarters) | pass for all 232 bank-quarters |

## Findings — every break explained

| # | Bank | Check | Quarter(s) | Difference | Reading |
|---|---|---|---|---|---|
| 1 | **Kuntarahoitus Oyj (MuniFin)**, FI | EBA v4886 (capital ratios < 100%) | Sep, Dec 2024 | CET1 ratio 104.3%, 107.7% | **Genuine data, rule correctly flags it.** A public-sector lender whose loans to Finnish municipalities carry 0% risk weight, so TREA is smaller than capital. Below 100% again from Mar 2025. |
| 2 | **Kommuninvest**, SE | EBA v4886 | all 4 | CET1 ratio 180%–353% | Same business model (Swedish local governments). A plausibility rule, not an error: the filer explains, the supervisor accepts. |
| 3 | **Länsförsäkringar Bank**, SE | Leverage Tier 1 (C 47.00 r0320) = own-funds Tier 1 (C 01.00 r0015) | Mar 2025 only | Leverage Tier 1 **+€296.8m** | Equal in the other three quarters. A one-quarter inconsistency between two templates of the same filing: **query the bank** (e.g. interim profit included in one template only). |
| 4 | **Jyske Bank**, DK | Same | Mar 2025 only | +€0.9m | Small, but outside rounding tolerance. Same query. |
| 5 | **Bank with LEI withheld in the EBA data** | Same | all 4 | Leverage Tier 1 **€302m–€408m lower** | Persistent, so not a one-off error. Likely a structural difference in what each template includes; needs the bank's explanation. |
| 6 | Same bank | RWA overview total = C 02.00 TREA | Mar 2025; Jun 2025 | OV1 **€463.7m lower**; then €0.7m | The RWA overview omits €463.7m of TREA in one quarter. Corrected by Jun 2025. |

**What a reviewer does with this:** findings 1–2 are explained by the business model and closed.
Findings 3–6 go back to the bank as data queries. Choosing which is which is the job a regulatory
reporting BA does every quarter.

## Outputs (`out/real/`)

| File | Content |
|---|---|
| `te2025_by_check.csv` | Pass / break counts per rule or check |
| `te2025_breaks.csv` | Every break with bank, quarter and difference |
| `te2025_check_results.csv.gz` | All 23,919 results |
| `te2025_as_corep_cells.csv.gz` | The published figures as COREP cells (bank, quarter, template, row, column) |

Run: `python -m corep.transparency`. EBA data © European Banking Authority, reproduced in part with
acknowledgement.
