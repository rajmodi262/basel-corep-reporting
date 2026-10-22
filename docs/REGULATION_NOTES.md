# Regulation notes — what this project reports, in plain English

These notes cover everything you need to explain the project: the regulation, the reports and the
numbers. Each section links the idea to the CRR article and to the exact COREP cell where it ends up.
Figures are Demo Bank AG's at 31 December 2025.

**CRR** = Capital Requirements Regulation, (EU) No 575/2013, as amended by Regulation (EU) 2024/1623 ("CRR3", Basel III final reforms).
**CRD** = Capital Requirements Directive, 2013/36/EU.

---

## 1. Why banks report capital at all

A bank lends out money that mostly belongs to depositors. If loans go bad, someone absorbs the loss.
**Capital** (the owners' money plus some loss-absorbing debt) is that buffer. Basel III, written by the
Basel Committee and turned into EU law by the CRR, says how much capital a bank must hold **relative to
the riskiness of what it owns**. Supervisors check this every quarter through standard reports:

| Report | Means | What it shows | Here |
|---|---|---|---|
| **COREP** | Common Reporting | Capital, risk, leverage, liquidity, large exposures | C 01.00, C 02.00, C 03.00, C 47.00 |
| **FINREP** | Financial Reporting | Balance sheet and P&L in a standard layout | (not in the EBA 4.0 release; the bank's ledger is the source here) |

The **EBA** (European Banking Authority) defines the templates, each cell's meaning, and the
validation rules, and publishes them as a machine-readable **XBRL taxonomy**. Banks submit files in
**xBRL-CSV** format; from release 4.0 that is the EBA's required format.

## 2. The balance sheet and P&L — the starting point

Every number in COREP starts from the accounts (`data/general_ledger.csv`):

| Balance sheet (EUR m) | | | |
|---|---|---|---|
| Loans to customers and banks | 4,675 | Customer deposits | 4,578 |
| Government bonds | 910 | Debt securities issued | 600 |
| Cash and central bank | 435 | Subordinated (Tier 2) bonds | 250 |
| Goodwill, software, intangibles | 85 | Other liabilities | 101 |
| Deferred tax assets | 38 | **Equity** (shares, reserves, AT1, profit) | **764** |
| Other assets | 150 | | |
| **Total assets** | **6,293** | **Total liabilities + equity** | **6,293** |

The **P&L** for 2025: net interest income 148, net fees 57, other income 11, costs −142,
impairments −5, tax −21 → **profit 48**. The board proposes a **20 dividend**.

## 3. Own funds — what counts as capital (C 01.00)

Capital comes in three tiers, from most to least loss-absorbing:

| Tier | What it is | Demo Bank | CRR |
|---|---|---|---|
| **CET1** — Common Equity Tier 1 | Shares, share premium, retained earnings, reserves **minus deductions** | 577.6 | Art 26-50 |
| **AT1** — Additional Tier 1 | Perpetual bonds that convert or write down if CET1 falls | 75.0 | Art 51-61 |
| **T2** — Tier 2 | Subordinated bonds with 5+ years to run | 198.2 | Art 62-71 |
| **Own funds** | CET1 + AT1 + T2 | **850.9** | Art 72 |

**Why equity of 764 becomes CET1 of 577.6** (the walkthrough has every line):

- **Profit:** only profit **after foreseeable dividends** counts. 48 − 20 = 28 (Art 26(2)) → r0150/r0170.
- **AT1** is accounting equity but is its own tier → moved out of CET1 (75).
- **Deductions** (Art 36): things that are worth nothing in a crisis.
  - Goodwill −40 (r0310).
  - Software and intangibles −45, less the deferred tax liability tied to them +6 → −39 (r0340).
  - Deferred tax assets from tax losses −12 (r0370), because they only have value if the bank makes profits again.
- **Prudential filter:** prudent valuation of fair-valued bonds, simplified approach 0.1% × 390 → −0.39 (r0290).
- **Threshold test** (Art 48): deferred tax assets from *temporary* differences (26) are deducted only above 10% of CET1 (57.8). They're below it, so instead they get a **250% risk weight**.
- **Tier 2 amortisation** (Art 64): a T2 bond counts in full until its last 5 years, then straight-line down. The 100m bond maturing May 2028 has 881 of 1,826 days left, so it counts 48.2.

## 4. Risk exposure amounts — the denominator (C 02.00)

Capital is compared with **risk-weighted assets (RWA)**, called **TREA** (total risk exposure amount)
in COREP. Each asset's value is multiplied by a **risk weight** that reflects how likely it is to lose
money.

### 4a. Credit risk — Standardised Approach (Art 111-134)

`exposure value × risk weight = RWEA`. Exposure value is the accounting value net of specific provisions (Art 111(1)).

| Exposure class | Rule | Demo Bank risk weight | RWEA (m) |
|---|---|---|---|
| Central governments (Art 114) | By rating (credit quality step 1-6). **EU governments in their own currency: 0%** (Art 114(4)) | Bund, OAT, BTP: 0%; US Treasury CQS1: 0%; Turkey CQS5: 100% | 20.0 |
| Institutions (Art 120) | By rating; short-term (≤ 3 months) gets better weights | 20-50% | 81.5 |
| Corporates (Art 122) | By rating; **unrated = 100%** | 50-150%, mostly 100% | 1,943.2 |
| Retail (Art 123) | Flat 75% | 75% | 399.1 |
| Residential mortgages (Art 125) | **Loan-splitting**: the part up to 55% of the property value at 20%, the rest at 75% | 20% / 75% | 587.4 |
| In default (Art 127) | 150% if provisions < 20%, else 100% | 100-150% | 74.5 |
| Other items (Art 134) | Cash 0%, fixed assets 100%, DTA 250% | | 215.0 |

**Off-balance-sheet items** (undrawn credit lines, guarantees) are converted first with a **credit
conversion factor (CCF)**, the share expected to be drawn (Art 111, Annex I): unconditionally
cancellable lines 10%, trade finance 20%, other commitments 40%, guarantees 100%.

### 4b. Operational risk — Business Indicator Component (Art 312-316)

Losses from failed processes, people, systems or external events. CRR3 sizes it from the P&L only:

- **Business Indicator (BI)** = interest component + services component + financial component, each a 3-year average (Art 314).
  - Interest: min(|interest income − expense|, 2.25% × interest-earning assets) + dividends.
  - Services: max(other operating income, expense) + max(fee income, fee expense).
  - Financial: |trading book P&L| + |banking book P&L|.
- **BIC** = 12% × BI for BI up to €1bn (Art 313). Demo Bank: BI 206.5 → BIC 24.8 → **REA = 12.5 × 24.8 = 309.7**.

Why 12.5? Because 1 / 8% = 12.5. Multiplying a capital *requirement* by 12.5 turns it into an RWA-equivalent amount.

**TREA = 3,320.7 credit + 309.7 operational = 3,630.4.** (No trading book, so no market risk; no derivatives, so no CVA.)

## 5. Capital ratios and the requirement stack (C 03.00)

| Ratio (Art 92) | Formula | Demo Bank | Pillar 1 minimum |
|---|---|---|---|
| CET1 ratio | CET1 / TREA | **15.91%** | 4.5% |
| Tier 1 ratio | T1 / TREA | **17.98%** | 6% |
| Total capital ratio | Own funds / TREA | **23.44%** | 8% |

On top of Pillar 1 the supervisor adds layers (set in `config/srep.yaml`):

```
 Pillar 1            8.00%   everyone (Art 92 CRR)
+ P2R                2.00%   bank-specific, from the supervisor's SREP (Art 104 CRD)
= TSCR              10.00%   total SREP capital requirement            -> C 03.00 r0130
+ Combined buffer    3.50%   conservation 2.5% + countercyclical 1.00% (Art 128-140 CRD)
= OCR               13.50%   overall capital requirement               -> r0160
+ P2G                1.00%   guidance, not binding                     -> r0190 = 14.50%
```

P2R must be met at least 56.25% with CET1 and 75% with Tier 1 (Art 104a CRD). That's why the CET1
part of TSCR is 4.5% + 56.25% × 2% = **5.625%** (r0140). After meeting everything, Demo Bank has
**€246m of CET1 to spare** (r0220).

## 6. Leverage ratio (C 47.00)

Risk weights can be wrong, so Basel III adds a **non-risk-based backstop**:
**Tier 1 / total exposure ≥ 3%** (Art 92(1)(d), Art 429).

- Exposure = all balance-sheet assets (6,293.4, r0190)
- \+ off-balance items at their leverage CCFs (Art 429f): 30.5 + 9.6 + 164.8 + 82.0
- − assets already deducted from Tier 1 (−91.4, r0270)
- = **6,488.9** (r0290).

**Leverage ratio = 652.6 / 6,488.9 = 10.06%** (r0330).

Difference from the capital ratio: a government bond at 0% risk weight adds nothing to TREA, but it
counts in full in the leverage exposure.

## 7. How the report is built and checked

- **DPM** (Data Point Model): every cell is a *data point* with a fixed meaning. `{C_47.00, r0290, c0010}` is the data point `dp134660` in the taxonomy.
- **XBRL taxonomy**: the EBA's machine-readable definition of all data points and rules.
- **xBRL-CSV**: the submission format. One CSV per template with `datapoint,factValue` rows, plus `parameters.csv` (entity, date, currency, precision) and `FilingIndicators.csv` (which templates are filed).
- **Validation rules**: the EBA's checks, e.g. `v0218_m_0: {C_01.00,0020} = {C_02.00.a,0010} × {C_03.00,0010}` (CET1 = TREA × CET1 ratio). A blocking failure means the supervisor rejects the file.

## 8. Questions you should be able to answer

1. Why is a German government bond 0% but a Turkish one 100%? (Art 114(4) vs the rating table.)
2. Why is goodwill deducted from capital and not risk-weighted? (No value in liquidation; Art 36(1)(b).)
3. What is loan-splitting and why does it need the property value? (Art 125; that's why DQ-03 matters.)
4. Why does a T2 bond count less as it approaches maturity? (Art 64: it will not be there to absorb losses.)
5. How can CET1 ratio be 15.9% while the leverage ratio is 10.1%? (Different denominators; see section 6.)
6. What happens if the CET1 ratio falls below OCR? (Restrictions on dividends and AT1 coupons, the MDA, Art 141 CRD.)
7. What does the 12.5 in "12.5 × BIC" mean? (1 / 8%.)
8. What is the difference between COREP and FINREP?
9. What is the difference between P2R and P2G?
10. The countercyclical buffer went from 0.75% to 1% (CR-001). Which cells move, and why do own funds and the leverage ratio not? (docs/changes/CR-001.md)
11. Why does the report carry `decimalsMonetary = -3`, and how does that affect validation? (Values are accurate to the thousand, so each rule allows ±500 per cell under interval arithmetic.)
