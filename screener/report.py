"""Write results into the public results repo: dated CSV, latest.csv, and a README summary."""
import csv
import json
from datetime import date
from pathlib import Path

from .config import SETTINGS, Settings

COLUMNS = ["symbol", "name", "exchange", "price", "avg_volume_20d", "market_cap", "verdict", "reasons",
           "business_screen", "sic", "sic_description", "debt", "debt_ratio", "cash", "cash_ratio",
           "revenue", "interest_income", "income_ratio", "currency", "balance_sheet_date",
           "income_period_end", "nasdaq_financial_status", "cik"]


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6g}" if abs(v) < 1e6 else f"{v:.0f}"
    return v


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: _fmt(r.get(k)) for k in COLUMNS})


def _money(v):
    if not v:
        return "–"
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(v) >= div:
            return f"${v / div:.1f}{unit}"
    return f"${v:.0f}"


def _pct(v):
    return "–" if v is None else f"{v:.0%}"


def summary_markdown(rows: list[dict], run_date: date, s: Settings = SETTINGS) -> str:
    counts = {k: sum(r["verdict"] == k for r in rows) for k in ("PASS", "REVIEW", "FAIL")}
    passed = sorted((r for r in rows if r["verdict"] == "PASS"), key=lambda r: -(r.get("market_cap") or 0))
    lines = [
        "# Halal penny-stock screen",
        "",
        f"**Last run:** {run_date.isoformat()} · US-listed common stocks (Nasdaq, NYSE, NYSE American; no OTC) "
        f"with a last close under **${s.max_price:g}**.",
        "",
        f"| Screened | PASS | REVIEW | FAIL |\n|---|---|---|---|\n| {len(rows)} | {counts['PASS']} | "
        f"{counts['REVIEW']} | {counts['FAIL']} |",
        "",
        "**Phone app:** https://faroukfrk.github.io/halal-screener-results/ (open in Chrome → ⋮ → *Add to Home screen*)",
        "",
        f"Full results: [`results/latest.csv`](results/latest.csv) · history in [`results/`](results/)",
        "",
        "## PASS list (largest market cap first)",
        "",
        "| Symbol | Name | Price | Market cap | Debt/MC | Cash/MC | Interest/Income | 20d avg vol |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in passed:
        lines.append(f"| {r['symbol']} | {r['name'][:45]} | ${r['price']:.2f} | {_money(r.get('market_cap'))} | "
                     f"{_pct(r.get('debt_ratio'))} | {_pct(r.get('cash_ratio'))} | {_pct(r.get('income_ratio'))} | "
                     f"{r.get('avg_volume_20d') or '–'} |")
    if not passed:
        lines.append("| – | none this run | | | | | | |")
    lines += [
        "",
        "## Method",
        "",
        "1. **Business activity:** fail on conventional banking, insurance, alcohol, tobacco, gambling, cannabis "
        "(SEC industry code and company name); mixed industries (REITs, SPACs, hotels, restaurants, media, "
        "weapons, meat packing) go to REVIEW.",
        f"2. **Debt:** interest-bearing debt / market cap < {s.max_debt_ratio:.0%}.",
        f"3. **Cash:** cash + interest-bearing securities / market cap < {s.max_cash_ratio:.0%}.",
        f"4. **Income:** interest income / (revenue + interest income) < {s.max_income_ratio:.0%}.",
        "",
        "Thresholds follow AAOIFI Shariah Standard No. 21. Market cap = last close × latest shares outstanding "
        "from SEC filings. Data: Nasdaq Trader symbol lists, Yahoo Finance prices, SEC EDGAR XBRL filings.",
        "REVIEW means the screen could not decide (missing, stale or non-USD data, no revenue, or a mixed industry).",
        "",
        "Updated automatically every weekday after the US market close by "
        "[a GitHub Action](.github/workflows/daily-screen.yml). Code: [`screener/`](screener/) · "
        "method details: [`docs/shariah-method.md`](docs/shariah-method.md).",
        "",
        "> **Not investment advice and not a fatwa.** Automated data can be wrong or out of date. "
        "Penny stocks are high-risk. Verify each company yourself or with a qualified scholar.",
        "",
    ]
    return "\n".join(lines)


def write_results(rows: list[dict], results_dir: Path, run_date: date | None = None,
                  s: Settings = SETTINGS) -> list[Path]:
    run_date = run_date or date.today()
    results_dir = Path(results_dir)
    dated = results_dir / "results" / f"{run_date.isoformat()}.csv"
    latest = results_dir / "results" / "latest.csv"
    readme = results_dir / "README.md"
    write_csv(rows, dated)
    write_csv(rows, latest)
    readme.write_text(summary_markdown(rows, run_date, s), encoding="utf-8")
    meta = results_dir / "results" / "meta.json"   # read by the web app
    meta.write_text(json.dumps(meta_dict(rows, run_date, s), indent=2) + "\n", encoding="utf-8")
    return [dated, latest, readme, meta]


def meta_dict(rows: list[dict], run_date: date, s: Settings = SETTINGS) -> dict:
    return {
        "run_date": run_date.isoformat(),
        "screened": len(rows),
        "counts": {k: sum(r["verdict"] == k for r in rows) for k in ("PASS", "REVIEW", "FAIL")},
        "max_price": s.max_price,
        "limits": {"debt_ratio": s.max_debt_ratio, "cash_ratio": s.max_cash_ratio, "income_ratio": s.max_income_ratio},
    }
