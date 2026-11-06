"""Shariah screen: business-activity filter + AAOIFI-style financial ratios.

Verdicts:
  PASS   - permissible business and all three ratios under the limits, with fresh data
  FAIL   - prohibited core business, or a ratio over its limit
  REVIEW - can't decide automatically (mixed industry, missing/stale/foreign-currency data, no revenue)

This is a mechanical screen, not a fatwa. Always check the company yourself or with a scholar.
"""
import re
from datetime import date

from .config import SETTINGS, Settings

# SIC codes (https://www.sec.gov/search-filings/standard-industrial-classification-sic-code-list)
FAIL_SIC = {
    **{str(c): "conventional banking/credit" for c in range(6000, 6199)},
    "6211": "conventional brokerage/dealing", "6311": "conventional insurance", "6321": "conventional insurance",
    "6324": "conventional insurance", "6331": "conventional insurance", "6351": "conventional insurance",
    "6361": "conventional insurance", "6399": "conventional insurance", "6411": "insurance brokerage",
    "2082": "alcohol (brewing)", "2084": "alcohol (wine)", "2085": "alcohol (distilling)",
    "5180": "alcohol wholesale", "5182": "alcohol wholesale", "5921": "liquor stores",
    "2100": "tobacco", "2110": "tobacco", "2111": "tobacco", "2120": "tobacco", "2130": "tobacco",
    "6189": "asset-backed securities",
}
REVIEW_SIC = {
    "2080": "beverages (may include alcohol)", "2011": "meat packing (check pork)", "2013": "meat products (check pork)",
    "6770": "blank check / SPAC (trust earns interest)", "6798": "REIT (check tenants and debt)",
    "6199": "finance services, NEC (often crypto miners/lenders: check)", "6221": "commodity trading", "6282": "investment advice", "6200": "securities/commodities", "6792": "oil royalty traders",
    "6794": "patent owners & lessors", "6795": "mineral royalty traders", "6799": "investors, NEC",
    "7990": "amusement & recreation (may include gambling)", "7993": "coin-operated amusement / gaming",
    "7011": "hotels & motels (may serve alcohol/gaming)", "7812": "film & video production (check content)",
    "7822": "film distribution (check content)", "4841": "cable TV (check content)",
    "3480": "ordnance & accessories", "3482": "small arms ammunition", "3483": "ammunition", "3484": "small arms",
    "3489": "ordnance", "5810": "restaurants (may serve alcohol/pork)", "5812": "restaurants (may serve alcohol/pork)",
    "5813": "drinking places (alcohol)",
}
_FAIL_NAME = re.compile(r"\b(bank|bancorp|bancshares|bankshares|banc|insurance|assurance|casino|brewing|brewery|"
                        r"distiller(y|ies)|winery|wines?|spirits|tobacco|cannabis|marijuana|lottery|betting|"
                        r"mortgage|savings|thrift|reinsurance)\b", re.I)
_REVIEW_NAME = re.compile(r"\b(gaming|entertainment|hemp|cbd|vapor|vape|leisure|resorts?|hotels?|capital|"
                          r"financial|finance|lending|credit|acquisition corp|holdings? acquisition|bdc)\b", re.I)


def business_screen(sic: str, name: str) -> tuple[str, str]:
    if sic in FAIL_SIC:
        return "FAIL", f"SIC {sic}: {FAIL_SIC[sic]}"
    m = _FAIL_NAME.search(name or "")
    if m:
        return "FAIL", f"name suggests prohibited business ('{m.group(0)}')"
    if sic in REVIEW_SIC:
        return "REVIEW", f"SIC {sic}: {REVIEW_SIC[sic]}"
    m = _REVIEW_NAME.search(name or "")
    if m:
        return "REVIEW", f"name needs a business check ('{m.group(0)}')"
    if not sic:
        return "REVIEW", "no SEC industry code"
    return "PASS", ""


def _age_days(iso: str, today: date) -> int | None:
    try:
        return (today - date.fromisoformat(iso)).days
    except (TypeError, ValueError):
        return None


def ratio_screen(fin, price: float | None, today: date | None = None, s: Settings = SETTINGS,
                 adr: bool = False) -> dict:
    """Returns market cap, the three ratios, and (status, reasons)."""
    today = today or date.today()
    out = {"market_cap": None, "debt_ratio": None, "cash_ratio": None, "income_ratio": None}
    fails, reviews = [], []

    if fin is None or not fin.taxonomy:
        return {**out, "status": "REVIEW", "reasons": ["no XBRL financial data at SEC"]}
    if adr:
        reviews.append("depositary shares (ADR/ADS): SEC share count is not per ADS, market cap unreliable")
    if fin.shares_outstanding and price:
        out["market_cap"] = fin.shares_outstanding * price
    else:
        reviews.append("no shares-outstanding data (can't compute market cap)")

    usd = fin.currency == "USD"
    if not usd:
        reviews.append(f"financials in {fin.currency}: debt/cash ratios not computed")
    mc = out["market_cap"]

    if mc and usd:
        if fin.debt is None:
            reviews.append(f"debt reported ({fin.debt_unmapped or 'unknown tag'}) but not mapped: check balance sheet")
        else:
            out["debt_ratio"] = fin.debt / mc
            if out["debt_ratio"] >= s.max_debt_ratio:
                fails.append(f"debt {out['debt_ratio']:.0%} of market cap (limit {s.max_debt_ratio:.0%})")
        if fin.cash is None:
            reviews.append("no cash data")
        else:
            out["cash_ratio"] = fin.cash / mc
            if out["cash_ratio"] >= s.max_cash_ratio:
                fails.append(f"cash+securities {out['cash_ratio']:.0%} of market cap (limit {s.max_cash_ratio:.0%})")

    interest = fin.interest_income or 0.0
    revenue = fin.revenue or 0.0
    total_income = revenue + max(interest, 0.0)
    if not fin.income_period_end:
        reviews.append("no annual income statement")
    elif total_income <= 0:
        reviews.append("no revenue or interest income reported")
    else:
        out["income_ratio"] = max(interest, 0.0) / total_income
        if revenue <= 0:
            reviews.append("pre-revenue: income is interest only")
        elif out["income_ratio"] >= s.max_income_ratio:
            fails.append(f"interest income {out['income_ratio']:.1%} of income (limit {s.max_income_ratio:.0%})")

    for label, d in (("balance sheet", fin.balance_sheet_date), ("shares count", fin.shares_date)):
        age = _age_days(d, today)
        if age is not None and age > s.max_filing_age_days:
            reviews.append(f"{label} is stale ({d})")

    status = "FAIL" if fails else ("REVIEW" if reviews else "PASS")
    return {**out, "status": status, "reasons": fails + reviews}


def combine(business: tuple[str, str], ratios: dict) -> tuple[str, str]:
    b_status, b_reason = business
    statuses = [b_status, ratios["status"]]
    reasons = ([b_reason] if b_reason else []) + ratios["reasons"]
    verdict = "FAIL" if "FAIL" in statuses else ("REVIEW" if "REVIEW" in statuses else "PASS")
    return verdict, "; ".join(reasons)


_ADR = re.compile(r"depositary|depository|\bADS\b|\bADR\b", re.I)


def is_adr(name: str) -> bool:
    return bool(_ADR.search(name or ""))
