#!/usr/bin/env python3
"""
Batch-fetch and cache financial data for a list of tickers.
Usage: python scripts/fetch_financials.py AAPL MSFT NVDA
       python scripts/fetch_financials.py --file tickers.txt
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from data_fetcher import get_financials, get_balance_sheet, get_cashflow, get_ohlcv, get_info
from cache_manager import cache_status


def fetch_all(ticker: str) -> dict[str, bool]:
    """Fetch all data types for a ticker. Returns {data_type: success}."""
    status = {}
    for name, fn in [
        ("ohlcv", lambda: get_ohlcv(ticker, period="2y")),
        ("financials", lambda: get_financials(ticker)),
        ("balance_sheet", lambda: get_balance_sheet(ticker)),
        ("cashflow", lambda: get_cashflow(ticker)),
    ]:
        try:
            df = fn()
            status[name] = df is not None and not df.empty
        except Exception as e:
            print(f"  [{ticker}] {name} failed: {e}")
            status[name] = False
    return status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="*")
    parser.add_argument("--file", help="Text file with one ticker per line")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between requests")
    args = parser.parse_args()

    tickers = list(args.tickers)
    if args.file:
        tickers += Path(args.file).read_text().splitlines()
    tickers = [t.strip().upper() for t in tickers if t.strip()]

    if not tickers:
        print("No tickers provided. Usage: python fetch_financials.py AAPL MSFT")
        sys.exit(1)

    print(f"Fetching data for {len(tickers)} tickers...\n")
    for ticker in tickers:
        print(f"→ {ticker}", end=" ", flush=True)
        result = fetch_all(ticker)
        ok = sum(v for v in result.values())
        print(f"({ok}/{len(result)} OK)")
        if args.delay:
            time.sleep(args.delay)

    print("\nDone.")


if __name__ == "__main__":
    main()
