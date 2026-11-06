"""Command line:  python -m screener run --results-dir ../halal-screener-results"""
import argparse
from dataclasses import replace
from pathlib import Path

from . import pipeline, report
from .config import SETTINGS


def main(argv=None):
    p = argparse.ArgumentParser(prog="screener", description="Halal penny-stock screener")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="screen and write results")
    r.add_argument("--results-dir", type=Path, required=True, help="folder of the results repo")
    r.add_argument("--tickers", help="comma-separated symbols to screen (default: all)")
    r.add_argument("--limit", type=int, help="screen only the first N penny stocks (for testing)")
    r.add_argument("--max-price", type=float, default=SETTINGS.max_price)
    r.add_argument("--min-rows", type=int, default=0,
                   help="refuse to write results if fewer stocks were screened (protects against a bad data day)")
    r.add_argument("--prices-from", help="reuse price/volume columns from an earlier results CSV (skips Yahoo)")
    a = p.parse_args(argv)

    s = replace(SETTINGS, max_price=a.max_price)
    tickers = [t.strip() for t in a.tickers.split(",")] if a.tickers else None
    rows = pipeline.run(tickers=tickers, limit=a.limit, s=s, prices_from=a.prices_from)
    if len(rows) < a.min_rows:
        raise SystemExit(f"Only {len(rows)} stocks screened (minimum {a.min_rows}); not writing results.")
    for path in report.write_results(rows, a.results_dir, s=s):
        print(path)


if __name__ == "__main__":
    main()
