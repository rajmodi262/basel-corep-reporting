# Data gaps and data-quality rules

A regulatory report is only as good as the attributes behind it. Before any calculation,
`corep/quality.py` checks the sub-ledger for the fields each regulatory rule needs.

| Rule | Severity | Check | Regulatory field it protects | Hits | Treatment |
|---|---|---|---|---|---|
| DQ-01 | BLOCK | Exposure id unique | Every figure counted once | 0 | — |
| DQ-02 | WARN | Counterparty type present | Exposure class (Art 112) | **4** | Corporate class, the obligor's rating still applies (decision rule 6) |
| DQ-03 | WARN | Property value present for mortgages (after the collateral feed) | Loan-splitting (Art 124-125) | **1** (was 6 before CR-001) | Not evidenced as secured → retail 75% (decision rule 8) |
| DQ-04 | BLOCK | Provision between 0 and gross amount | Exposure value (Art 111(1)) | 0 | — |
| DQ-05 | BLOCK | Credit quality step is 1-6 or blank | Rating tables (Art 136) | 0 | — |
| DQ-06 | BLOCK | Exposure books to a GL account | Reconciliation REC-01 | 0 | — |
| DQ-07 | BLOCK | Off-balance product has a CCF | Annex I | 0 | — |
| DQ-08 | WARN | Defaulted exposures carry a provision | Art 127 cover test | 0 | — |
| DQ-09 | WARN | Valuation no older than 3 years at the reference date | Art 208(3) | **1** | Valuation not used; mortgage stays retail 75% |
| DQ-10 | BLOCK | Every valuation in the collateral feed belongs to a known mortgage | Feed integrity | 0 | — |

**BLOCK** stops the run (`corep/pipeline.py`); a report must not be produced from broken data.
**WARN** produces a report with a documented, never favourable fallback, and lists the exposures in
`out/data_quality.csv` so the data owner can fix them at source.

## Why the fallbacks are conservative

- **DQ-02:** the corporate class is the default class for a legal entity. A lower-weighted class
  (institution, sovereign, mortgage) needs evidence, so with no type there is none.
- **DQ-03:** a mortgage gets the 20% weight only on the part covered by 55% of a property value
  that has been valued (Art 124(3), 125). With no valuation, no part is evidenced as secured, so the
  whole exposure is treated as an unsecured retail exposure at 75%.

**Impact of the gaps:** a mortgage without a usable valuation carries 75% on its full amount. Fixing
the data moves part of it to 20%, so the gaps make the reported ratios slightly *lower* (safer),
never higher. CR-001 proved it: valuing 5 of the 6 mortgages lowered TREA by €4.3m.

## Gaps in scope (what this bank does not have)

There is no trading book (so no market risk), no derivatives or securities financing (so no
counterparty credit risk, CVA, or leverage rows for SFTs and derivatives), no securitisations, and
no IRB models. Their template rows are left empty, and the EBA rules on those rows are reported as
"not applicable" in `out/eba_validation_results.csv`.
