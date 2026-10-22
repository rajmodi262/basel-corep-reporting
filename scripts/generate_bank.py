"""Generate the books of "Demo Bank AG", a synthetic, mid-sized EU retail and commercial bank.

    python scripts/generate_bank.py

Real bank data is confidential, so the inputs are synthetic; everything downstream (the CRR rules,
the EBA templates, datapoints and validation rules) is real. The generator is deterministic
(fixed seed), so every figure in the README reproduces exactly.

It writes, as of the reporting date 2025-12-31:

- data/exposures.csv        loan-level credit exposures (the risk sub-ledger)
- data/off_balance.csv      undrawn commitments and guarantees
- data/general_ledger.csv   trial balance: every balance-sheet and P&L account
- data/pl_history.csv       three years of P&L items for the operational-risk business indicator
- data/capital_instruments.csv   shares, AT1 and Tier 2 bonds with their terms

Data-quality gaps are planted on purpose, as a real sub-ledger has them (see docs/DATA_GAPS.md):
a few exposures have no counterparty type, and a few mortgages have no property valuation.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RNG = np.random.default_rng(20251231)
M = 1_000_000


def write(name: str, rows: list[dict]) -> None:
    with open(DATA / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def amounts(n: int, total: float, sigma: float = 0.9) -> np.ndarray:
    """n lognormal amounts rounded to whole euros, scaled to add up to total exactly."""
    raw = RNG.lognormal(0, sigma, n)
    out = np.floor(raw / raw.sum() * total)
    out[0] += total - out.sum()
    return out


def exposures() -> list[dict]:
    rows: list[dict] = []

    def add(**kw):
        kw.setdefault("cqs", "")
        kw.setdefault("property_value", "")
        kw.setdefault("specific_provision", 0)
        kw.setdefault("default_flag", 0)
        kw.setdefault("original_maturity_days", "")
        kw.setdefault("accounting_portfolio", "AC")
        rows.append(kw)

    # sovereign and central bank
    add(exposure_id="EXP-SOV-0001", counterparty_id="CB-DE", counterparty_type="central_bank", country="DE",
        currency="EUR", product="central_bank_reserve", gl_account="1010", gross_amount=410 * M, cqs="1")
    for i, (cty, cur, cqs, amt, port) in enumerate([
        ("DE", "EUR", "1", 380 * M, "AC"), ("DE", "EUR", "1", 160 * M, "FVOCI"), ("FR", "EUR", "2", 140 * M, "FVOCI"),
        ("IT", "EUR", "3", 120 * M, "AC"), ("US", "USD", "1", 90 * M, "FVOCI"), ("TR", "USD", "5", 20 * M, "AC"),
    ], start=1):
        gl = "1110" if port == "AC" else "1120"
        add(exposure_id=f"EXP-SOV-{i + 1:04d}", counterparty_id=f"GOV-{cty}", counterparty_type="central_government",
            country=cty, currency=cur, product="government_bond", gl_account=gl, gross_amount=amt, cqs=cqs,
            accounting_portfolio=port)

    # institutions
    inst = amounts(24, 310 * M, 0.6)
    for i, a in enumerate(inst, start=1):
        short = i % 3 == 0
        add(exposure_id=f"EXP-INS-{i:04d}", counterparty_id=f"BNK-{i:03d}", counterparty_type="institution",
            country=RNG.choice(["DE", "FR", "NL", "AT", "GB"]), currency="EUR",
            product="interbank_placement" if short else "interbank_loan", gl_account="1210", gross_amount=a,
            cqs=str(RNG.choice([1, 2, 2, 3])), original_maturity_days=60 if short else 720)

    # corporates
    corp = amounts(420, 1_820 * M, 1.1)
    for i, a in enumerate(corp, start=1):
        rated = RNG.random() < 0.3
        default = RNG.random() < 0.025
        prov = round(a * RNG.uniform(0.1, 0.45)) if default else 0
        ctype = "" if i in (37, 112, 268, 391) else "corporate"  # planted gap: no counterparty type
        add(exposure_id=f"EXP-COR-{i:04d}", counterparty_id=f"CORP-{i:04d}", counterparty_type=ctype,
            country=RNG.choice(["DE", "DE", "DE", "AT", "NL", "FR"]), currency="EUR", product="term_loan",
            gl_account="1310", gross_amount=a, cqs=str(RNG.choice([2, 3, 3, 4, 5])) if rated else "",
            default_flag=int(default), specific_provision=prov)

    # retail
    retail = amounts(1_500, 520 * M, 0.7)
    for i, a in enumerate(retail, start=1):
        default = RNG.random() < 0.03
        prov = round(a * RNG.uniform(0.15, 0.6)) if default else 0
        add(exposure_id=f"EXP-RET-{i:05d}", counterparty_id=f"CUST-{i:05d}", counterparty_type="retail",
            country="DE", currency="EUR", product="consumer_loan", gl_account="1410", gross_amount=a,
            default_flag=int(default), specific_provision=prov)

    # residential mortgages
    mort = amounts(1_200, 2_050 * M, 0.5)
    for i, a in enumerate(mort, start=1):
        ltv = RNG.uniform(0.35, 0.95)
        default = RNG.random() < 0.012
        prov = round(a * RNG.uniform(0.05, 0.25)) if default else 0
        value = "" if i in (14, 233, 501, 742, 960, 1111) else round(a / ltv)  # planted gap: no valuation
        add(exposure_id=f"EXP-MTG-{i:05d}", counterparty_id=f"CUST-M{i:05d}", counterparty_type="retail",
            country="DE", currency="EUR", product="residential_mortgage", gl_account="1510", gross_amount=a,
            property_value=value, default_flag=int(default), specific_provision=prov)

    # other items held on the balance sheet that carry credit risk weights
    add(exposure_id="EXP-OTH-0001", counterparty_id="OWN", counterparty_type="other", country="DE", currency="EUR",
        product="cash", gl_account="1000", gross_amount=25 * M)
    add(exposure_id="EXP-OTH-0002", counterparty_id="OWN", counterparty_type="other", country="DE", currency="EUR",
        product="tangible_asset", gl_account="1700", gross_amount=92 * M)
    add(exposure_id="EXP-OTH-0003", counterparty_id="OWN", counterparty_type="other", country="DE", currency="EUR",
        product="other_asset", gl_account="1900", gross_amount=58 * M)
    add(exposure_id="EXP-OTH-0004", counterparty_id="TAX", counterparty_type="other", country="DE", currency="EUR",
        product="dta_temporary_differences", gl_account="1820", gross_amount=26 * M)
    for r in rows:
        r["gross_amount"] = int(r["gross_amount"])
        r["specific_provision"] = int(r["specific_provision"])
    return rows


def off_balance() -> list[dict]:
    rows = []
    specs = [
        ("undrawn_committed_facility", "corporate", 60, 412 * M),
        ("unconditionally_cancellable_line", "retail", 400, 305 * M),
        ("documentary_credit", "corporate", 25, 48 * M),
        ("financial_guarantee", "corporate", 30, 82 * M),
    ]
    n = 0
    for product, ctype, count, total in specs:
        for a in amounts(count, total, 0.8):
            n += 1
            rows.append({
                "commitment_id": f"OBS-{n:04d}", "counterparty_type": ctype, "product": product,
                "nominal_amount": int(a), "cqs": str(RNG.choice([3, 4])) if ctype == "corporate" and RNG.random() < 0.3 else "",
            })
    return rows


def capital_instruments() -> list[dict]:
    return [
        {"instrument_id": "SHR-ORD", "type": "ordinary_shares", "tier": "CET1", "gl_account": "3000",
         "nominal": 200 * M, "issue_date": "2004-06-01", "maturity_date": "", "call_date": ""},
        {"instrument_id": "AT1-2030C", "type": "perpetual_contingent_convertible", "tier": "AT1", "gl_account": "3500",
         "nominal": 75 * M, "issue_date": "2023-03-15", "maturity_date": "", "call_date": "2030-03-15"},
        {"instrument_id": "T2-2033", "type": "subordinated_bond", "tier": "T2", "gl_account": "2600",
         "nominal": 150 * M, "issue_date": "2023-09-20", "maturity_date": "2033-09-20", "call_date": "2028-09-20"},
        {"instrument_id": "T2-2028", "type": "subordinated_bond", "tier": "T2", "gl_account": "2610",
         "nominal": 100 * M, "issue_date": "2018-05-30", "maturity_date": "2028-05-30", "call_date": ""},
    ]


def general_ledger(exp: list[dict]) -> list[dict]:
    gl: dict[str, int] = {}
    for e in exp:
        gl[e["gl_account"]] = gl.get(e["gl_account"], 0) + e["gross_amount"]
    provisions = sum(e["specific_provision"] for e in exp)
    accounts = [
        # account, description, statement, class, amount (assets/expenses positive; liabilities/equity/income negative)
        ("1000", "Cash in hand", "BS", "asset", gl["1000"]),
        ("1010", "Balances with central banks", "BS", "asset", gl["1010"]),
        ("1110", "Government bonds - amortised cost", "BS", "asset", gl["1110"]),
        ("1120", "Government bonds - FVOCI", "BS", "asset", gl["1120"]),
        ("1210", "Loans and advances to banks", "BS", "asset", gl["1210"]),
        ("1310", "Loans to corporates - gross", "BS", "asset", gl["1310"]),
        ("1410", "Consumer loans - gross", "BS", "asset", gl["1410"]),
        ("1510", "Residential mortgages - gross", "BS", "asset", gl["1510"]),
        ("1590", "Loan loss allowance (specific)", "BS", "asset", -provisions),
        ("1600", "Goodwill", "BS", "asset", 40 * M),
        ("1610", "Software", "BS", "asset", 35 * M),
        ("1620", "Other intangible assets", "BS", "asset", 10 * M),
        ("1700", "Property and equipment", "BS", "asset", gl["1700"]),
        ("1810", "Deferred tax asset - tax loss carry-forward", "BS", "asset", 12 * M),
        ("1820", "Deferred tax asset - temporary differences", "BS", "asset", gl["1820"]),
        ("1900", "Other assets", "BS", "asset", gl["1900"]),
        ("2100", "Debt securities issued", "BS", "liability", -600 * M),
        ("2600", "Subordinated bond T2-2033", "BS", "liability", -150 * M),
        ("2610", "Subordinated bond T2-2028", "BS", "liability", -100 * M),
        ("2700", "Provisions", "BS", "liability", -31 * M),
        ("2810", "Deferred tax liability on intangible assets", "BS", "liability", -6 * M),
        ("2900", "Other liabilities", "BS", "liability", -64 * M),
        ("3000", "Share capital", "BS", "equity", -200 * M),
        ("3100", "Share premium", "BS", "equity", -150 * M),
        ("3200", "Retained earnings - prior years", "BS", "equity", -281 * M),
        ("3300", "Accumulated other comprehensive income", "BS", "equity", 15 * M),
        ("3400", "Other reserves", "BS", "equity", -25 * M),
        ("3500", "AT1 instrument (equity-classified)", "BS", "equity", -75 * M),
    ]
    pl = [
        ("4000", "Interest income", "PL", "income", -246 * M),
        ("4100", "Interest expense", "PL", "expense", 98 * M),
        ("4200", "Dividend income", "PL", "income", -2 * M),
        ("4300", "Fee and commission income", "PL", "income", -71 * M),
        ("4400", "Fee and commission expense", "PL", "expense", 14 * M),
        ("4500", "Net gains on financial assets (banking book)", "PL", "income", -3 * M),
        ("4600", "Other operating income", "PL", "income", -6 * M),
        ("5000", "Staff expenses", "PL", "expense", 78 * M),
        ("5100", "Other administrative expenses", "PL", "expense", 44 * M),
        ("5200", "Depreciation and amortisation", "PL", "expense", 15 * M),
        ("5300", "Other operating expenses", "PL", "expense", 5 * M),
        ("5400", "Impairment losses on loans", "PL", "expense", 0),  # set below
        ("5900", "Income tax expense", "PL", "expense", 0),          # set below
    ]
    # Target profit after tax of 48m: impairment and tax close the P&L.
    pre_imp = -sum(a for *_, a in pl)
    tax = 21 * M
    impairment = pre_imp - tax - 48 * M
    pl = [(a, d, s, c, impairment if a == "5400" else tax if a == "5900" else v) for a, d, s, c, v in pl]
    rows = accounts + pl
    profit = -sum(v for a, d, s, c, v in pl)
    # Customer deposits close the balance sheet: assets + liabilities + equity - profit = 0.
    balance = sum(v for *_, v in accounts) - profit
    rows.insert(16, ("2000", "Customer deposits", "BS", "liability", -balance))
    return [{"account": a, "description": d, "statement": s, "class": c, "amount": int(v)} for a, d, s, c, v in rows]


def pl_history() -> list[dict]:
    """Business-indicator inputs for 2023-2025 (CRR Article 314)."""
    years = {
        2023: dict(interest_income=198, interest_expense=71, interest_earning_assets=5_480, dividend_income=2,
                   fee_income=64, fee_expense=12, other_operating_income=5, other_operating_expense=6,
                   net_trading_book=0, net_banking_book=-4),
        2024: dict(interest_income=231, interest_expense=92, interest_earning_assets=5_690, dividend_income=2,
                   fee_income=68, fee_expense=13, other_operating_income=7, other_operating_expense=4,
                   net_trading_book=0, net_banking_book=2),
        2025: dict(interest_income=246, interest_expense=98, interest_earning_assets=5_870, dividend_income=2,
                   fee_income=71, fee_expense=14, other_operating_income=6, other_operating_expense=5,
                   net_trading_book=0, net_banking_book=3),
    }
    return [{"year": y, "item": k, "amount": v * M} for y, items in years.items() for k, v in items.items()]


def main() -> None:
    DATA.mkdir(exist_ok=True)
    exp = exposures()
    write("exposures.csv", exp)
    write("off_balance.csv", off_balance())
    write("capital_instruments.csv", capital_instruments())
    write("general_ledger.csv", general_ledger(exp))
    write("pl_history.csv", pl_history())
    print(f"{len(exp)} exposures written")


if __name__ == "__main__":
    main()
