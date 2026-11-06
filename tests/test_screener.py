"""Offline tests with small hand-made fixtures (no network)."""
from datetime import date

from screener import prices, report, sec, shariah, universe

NASDAQ_TXT = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAAA|Alpha Corp - Common Stock|S|N|D|100|N|N
AAAW|Alpha Corp - Warrants|S|N|N|100|N|N
ETFX|Some ETF|G|N|N|100|Y|N
ZTST|Test Issue Inc|S|Y|N|100|N|N
UNIT|United Widgets Inc - Common Stock|S|N|N|100|N|N
File Creation Time: 1105202608:31|||||||
"""
OTHER_TXT = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
BF.B|Brown Class B Common Stock|N|BF.B|N|100|N|BF=B
ABR$D|Arbor 6.375% Preferred Series D|N|ABRpD|N|100|N|ABR-D
CCC|Gamma Inc Common Stock|A|CCC|N|100|N|CCC
"""


def test_universe_filters_non_common_stock():
    n = universe.parse_nasdaq(NASDAQ_TXT)
    assert [s.symbol for s in n] == ["AAAA", "UNIT"]          # "United" must not match "units"
    assert n[0].financial_status == "D"
    o = universe.parse_other(OTHER_TXT)
    assert [s.symbol for s in o] == ["BF.B", "CCC"]
    assert o[0].yahoo_symbol == "BF-B" and o[0].sec_ticker == "BF-B"
    assert o[1].exchange == "NYSE American"


def test_parse_spark_and_chart():
    spark = {"AAA": {"close": [1.0, None, 1.5, None]}, "BBB": {"close": []}}
    assert prices.parse_spark(spark) == {"AAA": 1.5}
    chart = {"chart": {"result": [{"meta": {"regularMarketPrice": 2.0},
                                   "indicators": {"quote": [{"close": [1.9, 2.1], "volume": [100, None, 300]}]}}]}}
    assert prices.parse_chart(chart) == {"price": 2.1, "avg_volume_20d": 200}


def _fact(val, end, start=None, filed="2026-03-01", accn="A1", fy=2025, fp="FY", form="10-K"):
    e = {"val": val, "end": end, "filed": filed, "accn": accn, "fy": fy, "fp": fp, "form": form}
    if start:
        e["start"] = start
    return e


def _companyfacts():
    usd = lambda *es: {"units": {"USD": list(es)}}  # noqa: E731
    return {"facts": {
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            _fact(10_000_000, "2026-02-15", accn="A1"), _fact(2_000_000, "2026-02-15", accn="A1"),  # two classes
            _fact(9_000_000, "2025-02-15", accn="A0", filed="2025-03-01")]}}},
        "us-gaap": {
            "Assets": usd(_fact(50e6, "2025-12-31"), _fact(40e6, "2024-12-31")),
            "LongTermDebtNoncurrent": usd(_fact(3e6, "2025-12-31")),
            "LongTermDebtCurrent": usd(_fact(1e6, "2025-12-31")),
            "ShortTermBorrowings": usd(_fact(0.5e6, "2025-12-31"), _fact(9e6, "2024-12-31")),
            "CashAndCashEquivalentsAtCarryingValue": usd(_fact(2e6, "2025-12-31")),
            "ShortTermInvestments": usd(_fact(1e6, "2025-12-31")),
            "Revenues": usd(_fact(20e6, "2025-12-31", "2025-01-01"), _fact(5e6, "2025-12-31", "2025-10-01"),
                            _fact(18e6, "2024-12-31", "2024-01-01")),
            "InvestmentIncomeInterest": usd(_fact(0.4e6, "2025-12-31", "2025-01-01")),
        }}}


def test_extract_financials():
    f = sec.extract_financials(_companyfacts())
    assert f.taxonomy == "us-gaap" and f.currency == "USD"
    assert f.shares_outstanding == 12_000_000 and f.shares_date == "2026-02-15"
    assert f.balance_sheet_date == "2025-12-31"
    assert f.debt == 4.5e6                 # 3 + 1 + 0.5 (old 2024 borrowings ignored)
    assert f.cash == 3e6
    assert f.income_period_end == "2025-12-31"
    assert f.revenue == 20e6               # annual, not the quarter
    assert f.interest_income == 0.4e6


def test_ratio_screen_pass_and_fail():
    f = sec.extract_financials(_companyfacts())
    today = date(2026, 6, 1)
    ok = shariah.ratio_screen(f, price=2.0, today=today)      # market cap 24M
    assert ok["status"] == "PASS", ok["reasons"]
    assert round(ok["debt_ratio"], 4) == round(4.5 / 24, 4)
    bad = shariah.ratio_screen(f, price=0.5, today=today)     # market cap 6M -> debt 75%, cash 50%
    assert bad["status"] == "FAIL"
    assert any("debt" in r for r in bad["reasons"]) and any("cash" in r for r in bad["reasons"])


def test_ratio_screen_review_cases():
    today = date(2026, 6, 1)
    assert shariah.ratio_screen(sec.Financials(), 1.0, today)["status"] == "REVIEW"
    f = sec.extract_financials(_companyfacts())
    f.revenue = 0.0
    r = shariah.ratio_screen(f, 2.0, today)
    assert r["status"] == "REVIEW" and any("pre-revenue" in x for x in r["reasons"])
    stale = shariah.ratio_screen(sec.extract_financials(_companyfacts()), 2.0, date(2028, 1, 1))
    assert stale["status"] == "REVIEW"


def test_interest_income_fail():
    f = sec.extract_financials(_companyfacts())
    f.interest_income = 2e6                                   # 2 / 22 = 9%
    r = shariah.ratio_screen(f, 2.0, date(2026, 6, 1))
    assert r["status"] == "FAIL" and any("interest income" in x for x in r["reasons"])


def test_business_screen():
    assert shariah.business_screen("6022", "First Something")[0] == "FAIL"
    assert shariah.business_screen("2834", "Acme Bancorp")[0] == "FAIL"
    assert shariah.business_screen("2833", "Green Cannabis Co")[0] == "FAIL"
    assert shariah.business_screen("6770", "XYZ Acquisition Corp")[0] == "REVIEW"
    assert shariah.business_screen("3674", "Chipmaker Inc") == ("PASS", "")
    assert shariah.business_screen("", "Chipmaker Inc")[0] == "REVIEW"
    assert shariah.combine(("PASS", ""), {"status": "FAIL", "reasons": ["x"]}) == ("FAIL", "x")


def test_ticker_map():
    data = {"fields": ["cik", "name", "ticker", "exchange"], "data": [[1, "A", "aaa", "Nasdaq"], [2, "B", "BF-B", "NYSE"]]}
    assert sec.parse_ticker_map(data) == {"AAA": 1, "BF-B": 2}


def test_write_results(tmp_path):
    rows = [{"symbol": "AAAA", "name": "Alpha", "exchange": "NASDAQ", "price": 1.23, "market_cap": 5e7,
             "debt_ratio": 0.1, "cash_ratio": 0.05, "income_ratio": 0.01, "avg_volume_20d": 1000,
             "verdict": "PASS", "reasons": ""},
            {"symbol": "BBBB", "name": "Beta", "price": 0.5, "verdict": "FAIL", "reasons": "debt"}]
    paths = report.write_results(rows, tmp_path, date(2026, 11, 5))
    assert (tmp_path / "results" / "2026-11-05.csv").exists()
    md = (tmp_path / "README.md").read_text()
    assert "| 2 | 1 | 0 | 1 |" in md and "AAAA" in md and "BBBB" not in md.split("## PASS")[1].split("## Method")[0]
    assert len(paths) == 4
    import json
    meta = json.loads((tmp_path / "results" / "meta.json").read_text())
    assert meta["counts"] == {"PASS": 1, "REVIEW": 0, "FAIL": 1} and meta["limits"]["debt_ratio"] == 0.30


def test_taxonomy_switch_uses_newest():
    usd = lambda v, end: {"units": {"USD": [_fact(v, end)]}}  # noqa: E731
    cf = {"facts": {"us-gaap": {"Assets": usd(1e6, "2010-12-31")},
                    "ifrs-full": {"Assets": usd(2e6, "2025-12-31"), "Borrowings": usd(5e5, "2025-12-31")}}}
    f = sec.extract_financials(cf)
    assert f.taxonomy == "ifrs-full" and f.balance_sheet_date == "2025-12-31" and f.debt == 5e5


def test_sic_6199_is_review():
    assert shariah.business_screen("6199", "Bitcoin Miner Inc")[0] == "REVIEW"


def test_lease_inclusive_debt_tag_is_counted():
    usd = lambda v, end: {"units": {"USD": [_fact(v, end)]}}  # noqa: E731
    cf = {"facts": {"us-gaap": {"Assets": usd(5e9, "2026-09-30"),
                                "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities": usd(13e9, "2026-09-30")}}}
    assert sec.extract_financials(cf).debt == 13e9


def test_unmapped_debt_gives_review_not_pass():
    usd = lambda v, end: {"units": {"USD": [_fact(v, end)]}}  # noqa: E731
    cf = _companyfacts()
    g = cf["facts"]["us-gaap"]
    for k in ("LongTermDebtNoncurrent", "LongTermDebtCurrent", "ShortTermBorrowings"):
        del g[k]
    g["SomeExoticBorrowingsTotal"] = usd(9e6, "2025-12-31")
    g["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo"] = usd(1e6, "2025-12-31")  # not a balance
    f = sec.extract_financials(cf)
    assert f.debt is None and f.debt_unmapped == "SomeExoticBorrowingsTotal"
    r = shariah.ratio_screen(f, 2.0, date(2026, 6, 1))
    assert r["status"] == "REVIEW"
    del g["SomeExoticBorrowingsTotal"]
    assert sec.extract_financials(cf).debt == 0.0


def test_adr_goes_to_review():
    assert shariah.is_adr("Foo Ltd - American Depositary Shares") and not shariah.is_adr("Adsero Corp")
    assert shariah.is_adr("NOVONIX Limited - American Depository Shares")
    f = sec.extract_financials(_companyfacts())
    assert shariah.ratio_screen(f, 2.0, date(2026, 6, 1), adr=True)["status"] == "REVIEW"


def test_clean_user_agent():
    from screener.config import clean_user_agent
    assert clean_user_agent('  "Name\u00a0me@x.com"\r\n') == "Name me@x.com"
    assert clean_user_agent("Name\nme@x.com") == "Name me@x.com"
