# EBA taxonomy extract

Source: European Banking Authority, **XBRL taxonomy for reporting framework 4.0** (package
`taxo_package_4.0_errata5.zip`, published March 2025), from
<https://www.eba.europa.eu/risk-and-data-analysis/reporting-frameworks/reporting-framework-40>.
Reproduced in part, with the source acknowledged.

The full taxonomy is 457 MB unzipped. This folder keeps only what the pipeline needs, regenerated with:

```bash
python scripts/extract_taxonomy.py <unzipped EBA_XBRL_4.0_Reporting_Frameworks_4.0.0.0>
```

| File | Rows | Content |
|---|---|---|
| `datapoints.csv` | 1,073 | Every cell of C 00.01, C 01.00, C 02.00.a, C 03.00, C 22.00, C 25.01.a, C 34.01.a, C 34.03 (sheet SA-CCR) and C 47.00: row, column, xBRL-CSV datapoint id, type, row and column labels |
| `validation_rules.csv` | 1,428 | Every EBA validation rule whose cells all sit in those templates, with its expression as the taxonomy states it |

C 34.03 has a sheet (z-axis) per approach. Only sheet s0001 (SA-CCR, `eba_AP:x184`) is reported; its
cells and rules are addressed without the sheet code, and rules on sheet s0002 (simplified SA-CCR) are left out.

## Validation approach

The EBA ships its rules as XBRL formula linkbases. Running them with Arelle needs the Eurofiling
base files that the taxonomy imports from eurofiling.info; that host was unreachable from the build
machine. So `corep/eba_rules.py` evaluates the same rules from their published expressions, using the
interval arithmetic and fallback-to-zero semantics of the formula linkbase. The planted-error tests
(UT-19, UT-20) show that it rejects a broken report.
