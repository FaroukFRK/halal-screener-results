"""Run the full screen: universe -> prices -> SEC data -> verdicts."""
import csv
import sys
from datetime import date

from . import prices, sec, shariah, universe
from .config import GENERIC_USER_AGENT, SETTINGS, Settings, sec_user_agent
from .http import Client


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def run(tickers: list[str] | None = None, limit: int | None = None, s: Settings = SETTINGS,
        today: date | None = None, prices_from: str | None = None) -> list[dict]:
    today = today or date.today()
    sec_ua = sec_user_agent()          # fail fast before spending time on prices
    web = Client(GENERIC_USER_AGENT, min_interval=s.yahoo_min_interval)
    sec_api = sec.SecClient(Client(sec_ua, min_interval=s.sec_min_interval))

    log("1/4 Loading US listed symbols (Nasdaq Trader)...")
    secs = universe.load_universe(web)
    if tickers:
        wanted = {t.upper() for t in tickers}
        secs = [x for x in secs if x.symbol.upper() in wanted]
    log(f"    {len(secs)} common stocks")

    detail = {}
    if prices_from:
        log(f"2/4 Reusing prices from {prices_from} (no Yahoo calls)")
        with open(prices_from, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r.get("price"):
                    sym = r["symbol"].replace(".", "-")
                    detail[sym] = {"price": float(r["price"]),
                                   "avg_volume_20d": int(float(r["avg_volume_20d"])) if r.get("avg_volume_20d") else None}
        closes = {k: v["price"] for k, v in detail.items()}
    else:
        log("2/4 Last closes (Yahoo)...")
        closes = prices.last_closes(web, [x.yahoo_symbol for x in secs], log)
    if not tickers and not prices_from and len(closes) < 0.8 * len(secs):
        raise RuntimeError(f"Prices found for only {len(closes)} of {len(secs)} stocks: price source likely blocked.")
    penny = [x for x in secs if s.min_price <= closes.get(x.yahoo_symbol, 1e9) < s.max_price]
    penny.sort(key=lambda x: x.symbol)
    if limit:
        penny = penny[:limit]
    log(f"    {len(penny)} under ${s.max_price:g} (no price for {len(secs) - len(closes)})")

    log("3/4 SEC ticker map...")
    cik_map = sec_api.ticker_map()

    log("4/4 Screening each stock (SEC filings + 20-day volume)...")
    rows = []
    for i, x in enumerate(penny, 1):
        row = {"symbol": x.symbol, "name": x.name, "exchange": x.exchange,
               "nasdaq_financial_status": x.financial_status, "price": closes.get(x.yahoo_symbol)}
        if prices_from:
            row.update({k: v for k, v in detail.get(x.yahoo_symbol, {}).items() if v is not None})
        else:
            try:
                row.update({k: v for k, v in prices.chart_detail(web, x.yahoo_symbol).items() if v is not None})
            except Exception as e:
                log(f"    {x.symbol}: chart failed ({e})")
        cik = cik_map.get(x.sec_ticker)
        fin, info = None, {"sic": "", "sic_description": "", "sec_name": ""}
        if cik:
            try:
                info = sec_api.submissions(cik)
                fin = sec_api.financials(cik)
            except Exception as e:
                log(f"    {x.symbol}: SEC failed ({e})")
        row.update({"cik": cik or "", "sic": info["sic"], "sic_description": info["sic_description"]})
        business = shariah.business_screen(info["sic"], x.name)
        if not cik:
            ratios = {"market_cap": None, "debt_ratio": None, "cash_ratio": None, "income_ratio": None,
                      "status": "REVIEW", "reasons": ["ticker not found at SEC"]}
        else:
            ratios = shariah.ratio_screen(fin, row.get("price"), today, s, adr=shariah.is_adr(x.name))
        verdict, reasons = shariah.combine(business, ratios)
        row.update({
            "business_screen": business[0],
            "market_cap": ratios["market_cap"],
            "debt": fin.debt if fin else None, "debt_ratio": ratios["debt_ratio"],
            "cash": fin.cash if fin else None, "cash_ratio": ratios["cash_ratio"],
            "revenue": fin.revenue if fin else None, "interest_income": fin.interest_income if fin else None,
            "income_ratio": ratios["income_ratio"],
            "currency": fin.currency if fin else "", "balance_sheet_date": fin.balance_sheet_date if fin else "",
            "income_period_end": fin.income_period_end if fin else "",
            "verdict": verdict, "reasons": reasons,
        })
        rows.append(row)
        if i % 100 == 0 or i == len(penny):
            log(f"    {i}/{len(penny)}")
    return rows
