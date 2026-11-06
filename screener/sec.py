"""SEC EDGAR: ticker->CIK map, industry code (SIC), and XBRL financial facts.

Free and keyless, but SEC requires a User-Agent with your name + email (see config.sec_user_agent).
"""
from dataclasses import dataclass, field
from datetime import date

TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"


def parse_ticker_map(data: dict) -> dict[str, int]:
    fields = data["fields"]
    i_cik, i_tic = fields.index("cik"), fields.index("ticker")
    out = {}
    for row in data["data"]:
        tic = (row[i_tic] or "").upper()
        if tic and tic not in out:
            out[tic] = int(row[i_cik])
    return out


# --- XBRL tag sets ---------------------------------------------------------------
# Each "alternative" is a list of tags that do NOT overlap with each other, so they can be summed.
# We take the LARGEST alternative total: the most complete picture the filing gives us.
DEBT_ALTS = {
    "us-gaap": [
        ["LongTermDebt", "ShortTermBorrowings"],
        ["LongTermDebtNoncurrent", "DebtCurrent"],
        ["LongTermDebtNoncurrent", "LongTermDebtCurrent", "ShortTermBorrowings"],
        ["DebtInstrumentCarryingAmount"],
        ["LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities", "ShortTermBorrowings"],
        ["LongTermDebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligationsCurrent", "ShortTermBorrowings"],
        ["DebtAndCapitalLeaseObligations"],
        ["DebtLongtermAndShorttermCombinedAmount"],
        ["LongTermLoansPayable", "LoansPayableCurrent", "ShortTermBorrowings"],
        ["LoansPayable"],
        ["SeniorNotes", "ConvertibleNotesPayable", "ShortTermBorrowings"],
        ["SecuredDebt", "UnsecuredDebt"],
        ["ConvertibleNotesPayable", "NotesPayable", "LinesOfCreditCurrent"],
        ["ConvertibleNotesPayableCurrent", "ConvertibleLongTermNotesPayable", "NotesPayableCurrent",
         "LongTermNotesPayable", "NotesPayableRelatedPartiesClassifiedCurrent", "LinesOfCreditCurrent",
         "LongTermLineOfCredit", "ShortTermBorrowings"],
    ],
    "ifrs-full": [
        ["Borrowings"],
        ["CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings", "NoncurrentPortionOfNoncurrentBorrowings"],
        ["ShorttermBorrowings", "CurrentPortionOfLongtermBorrowings", "LongtermBorrowings"],
    ],
}
CASH_ALTS = {
    "us-gaap": [
        ["CashAndCashEquivalentsAtCarryingValue", "ShortTermInvestments"],
        ["CashAndCashEquivalentsAtCarryingValue", "MarketableSecuritiesCurrent"],
        ["CashAndCashEquivalentsAtCarryingValue", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
        ["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "ShortTermInvestments"],
        ["Cash", "ShortTermInvestments"],
    ],
    "ifrs-full": [
        ["CashAndCashEquivalents", "ShorttermInvestments"],
        ["CashAndCashEquivalents", "CurrentInvestments"],
        ["Cash", "ShorttermDepositsNotClassifiedAsCashEquivalents"],
    ],
}
REVENUE_ALTS = {
    "us-gaap": [["Revenues"], ["RevenueFromContractWithCustomerExcludingAssessedTax"],
                ["RevenueFromContractWithCustomerIncludingAssessedTax"], ["SalesRevenueNet"],
                ["SalesRevenueGoodsNet"], ["RevenuesNetOfInterestExpense"]],
    "ifrs-full": [["Revenue"], ["RevenueFromContractsWithCustomers"]],
}
INTEREST_ALTS = {
    "us-gaap": [["InvestmentIncomeInterest"], ["InvestmentIncomeInterestAndDividend"],
                ["InterestIncomeOther"], ["InterestAndOtherIncome"], ["InterestIncomeOperating"],
                ["InterestAndDividendIncomeOperating"]],
    "ifrs-full": [["InterestIncomeOnFinancialAssetsAtAmortisedCost"], ["InterestRevenueCalculatedUsingEffectiveInterestMethod"],
                  ["FinanceIncome"], ["InterestIncome"]],
}
ANCHOR_INSTANT = {"us-gaap": ["Assets", "Liabilities", "StockholdersEquity"], "ifrs-full": ["Assets", "Equity"]}


# Safety net: a tag whose name looks like borrowings (not leases, maturities schedules, securities held, etc.).
_DEBT_WORDS = ("Debt", "Borrowing", "NotesPayable", "LoansPayable", "SeniorNotes", "LineOfCredit", "LinesOfCredit")
_NOT_DEBT_WORDS = ("Maturit", "Discount", "Premium", "IssuanceCost", "Securities", "RightOfUse", "FairValue",
                   "Repayment", "Proceeds", "Repurchased", "Forgiveness", "Extinguishment", "Conversion",
                   "Converted", "InterestRate", "Receivable", "Allowance", "Amortization", "Increase", "Decrease",
                   "Payments", "Covenant", "Term", "FaceAmount", "Expense", "Restructur", "Guarantee", "Investment")


def _debt_hint(facts, taxonomy, unit, bs_end) -> str:
    """Name of a debt-like instant tag with a positive value within ~13 months before the balance sheet."""
    if not bs_end:
        return ""
    floor = date.fromisoformat(bs_end).toordinal() - 400
    for tag, body in facts.get(taxonomy, {}).items():
        if not any(w in tag for w in _DEBT_WORDS) or any(w in tag for w in _NOT_DEBT_WORDS):
            continue
        for e in (body.get("units") or {}).get(unit) or []:
            if "start" not in e and float(e["val"]) > 0 and date.fromisoformat(e["end"]).toordinal() >= floor:
                return tag
    return ""


@dataclass
class Financials:
    taxonomy: str = ""
    currency: str = ""
    balance_sheet_date: str = ""
    income_period_end: str = ""
    shares_outstanding: float | None = None
    shares_date: str = ""
    debt: float | None = None
    debt_tags: list = field(default_factory=list)
    debt_unmapped: str = ""      # debt-like tag seen in filings although no mapped debt tag was found
    cash: float | None = None
    cash_tags: list = field(default_factory=list)
    revenue: float | None = None
    interest_income: float | None = None
    interest_tags: list = field(default_factory=list)


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _pick_unit(facts: dict, taxonomy: str) -> str:
    """Reporting currency: USD if the filer uses it, else the most common monetary unit."""
    counts = {}
    for tag in ANCHOR_INSTANT.get(taxonomy, []):
        for unit, entries in (facts.get(taxonomy, {}).get(tag, {}).get("units") or {}).items():
            counts[unit] = counts.get(unit, 0) + len(entries)
    if not counts:
        return "USD"
    return "USD" if "USD" in counts else max(counts, key=counts.get)


def _entries(facts, taxonomy, tag, unit):
    return (facts.get(taxonomy, {}).get(tag, {}).get("units") or {}).get(unit) or []


def _instant_at(facts, taxonomy, tag, unit, end):
    """Value of an instant fact on a date (latest filing wins)."""
    best = None
    for e in _entries(facts, taxonomy, tag, unit):
        if e.get("end") == end and "start" not in e:
            if best is None or e.get("filed", "") > best.get("filed", ""):
                best = e
    return None if best is None else float(best["val"])


def _annual_at(facts, taxonomy, tag, unit, end):
    best = None
    for e in _entries(facts, taxonomy, tag, unit):
        if e.get("end") == end and e.get("start") and 350 <= _days(e["start"], e["end"]) <= 380:
            if best is None or e.get("filed", "") > best.get("filed", ""):
                best = e
    return None if best is None else float(best["val"])


def _latest_instant_date(facts, taxonomy, tags, unit):
    ends = [e["end"] for t in tags for e in _entries(facts, taxonomy, t, unit) if "start" not in e]
    return max(ends) if ends else ""


def _latest_annual_end(facts, taxonomy, alts, unit):
    ends = [e["end"] for alt in alts for t in alt for e in _entries(facts, taxonomy, t, unit)
            if e.get("start") and 350 <= _days(e["start"], e["end"]) <= 380]
    return max(ends) if ends else ""


def _best_alt(value_at, alts):
    """Sum each alternative; return (largest total, tags used). (None, []) if nothing reported."""
    best_total, best_tags = None, []
    for alt in alts:
        vals = {t: value_at(t) for t in alt}
        found = {t: v for t, v in vals.items() if v is not None}
        if not found:
            continue
        total = sum(found.values())
        if best_total is None or total > best_total:
            best_total, best_tags = total, sorted(found)
    return best_total, best_tags


def _shares(facts: dict):
    """Latest shares outstanding (sums share classes reported on the same date and filing)."""
    for taxonomy, tag in (("dei", "EntityCommonStockSharesOutstanding"),
                          ("us-gaap", "CommonStockSharesOutstanding"),
                          ("ifrs-full", "NumberOfSharesOutstanding")):
        entries = _entries(facts, taxonomy, tag, "shares")
        if not entries:
            continue
        latest_end = max(e["end"] for e in entries)
        same = [e for e in entries if e["end"] == latest_end]
        latest_accn = max(same, key=lambda e: e.get("filed", ""))["accn"]
        total = sum(float(e["val"]) for e in same if e["accn"] == latest_accn)
        if total > 0:
            return total, latest_end
    return None, ""


def _pick_taxonomy(facts: dict) -> str:
    """us-gaap or ifrs-full, whichever has the most recent balance sheet (filers can switch over time)."""
    best, best_end = "", ""
    for taxonomy in ("us-gaap", "ifrs-full"):
        if taxonomy not in facts:
            continue
        ends = [e["end"] for tag in ANCHOR_INSTANT[taxonomy]
                for entries in (facts[taxonomy].get(tag, {}).get("units") or {}).values() for e in entries]
        end = max(ends) if ends else "0000"
        if end > best_end:
            best, best_end = taxonomy, end
    return best


def extract_financials(companyfacts: dict) -> Financials:
    facts = companyfacts.get("facts") or {}
    taxonomy = _pick_taxonomy(facts)
    f = Financials(taxonomy=taxonomy)
    f.shares_outstanding, f.shares_date = _shares(facts)
    if not taxonomy:
        return f
    unit = f.currency = _pick_unit(facts, taxonomy)

    all_bs_tags = ANCHOR_INSTANT[taxonomy] + [t for a in DEBT_ALTS[taxonomy] + CASH_ALTS[taxonomy] for t in a]
    bs = f.balance_sheet_date = _latest_instant_date(facts, taxonomy, all_bs_tags, unit)
    if bs:
        at = lambda t: _instant_at(facts, taxonomy, t, unit, bs)  # noqa: E731
        debt, f.debt_tags = _best_alt(at, DEBT_ALTS[taxonomy])
        if debt is None:
            # No mapped debt tag. Only treat as debt-free if the filings show no debt-like tag at all.
            f.debt_unmapped = _debt_hint(facts, taxonomy, unit, bs)
            debt = None if f.debt_unmapped else 0.0
        f.debt = debt
        cash, f.cash_tags = _best_alt(at, CASH_ALTS[taxonomy])
        f.cash = cash

    end = f.income_period_end = _latest_annual_end(facts, taxonomy, REVENUE_ALTS[taxonomy] + INTEREST_ALTS[taxonomy], unit)
    if end:
        ann = lambda t: _annual_at(facts, taxonomy, t, unit, end)  # noqa: E731
        f.revenue, _ = _best_alt(ann, REVENUE_ALTS[taxonomy])
        # Interest: take the FIRST alternative found (they overlap; broader tags come later).
        for alt in INTEREST_ALTS[taxonomy]:
            v = ann(alt[0])
            if v is not None:
                f.interest_income, f.interest_tags = v, alt
                break
    return f


def parse_submissions(data: dict) -> dict:
    return {
        "sic": str(data.get("sic") or ""),
        "sic_description": data.get("sicDescription") or "",
        "sec_name": data.get("name") or "",
        "entity_type": data.get("entityType") or "",
    }


class SecClient:
    def __init__(self, client):
        self.client = client

    def ticker_map(self) -> dict[str, int]:
        return parse_ticker_map(self.client.get_json(TICKERS_URL))

    def submissions(self, cik: int) -> dict:
        return parse_submissions(self.client.get_json(SUBMISSIONS_URL.format(cik=cik)))

    def financials(self, cik: int) -> Financials:
        try:
            data = self.client.get_json(FACTS_URL.format(cik=cik))
        except Exception as e:
            if getattr(getattr(e, "response", None), "status_code", None) == 404:
                return Financials()   # company files no XBRL
            raise
        return extract_financials(data)
