#!/usr/bin/env python3
"""
Trigger a complete research pipeline for a single US equity ticker.
Runs: fetch data → technical snapshot → financial summary → write stub reports.
Full deep analysis is handled by Claude agents via orchestrator.

Usage: python scripts/run_research.py NVDA [--type full|financial|technical]
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from data_fetcher import get_ohlcv, get_financials, get_balance_sheet, get_cashflow, get_info
from technical import snapshot
from cache_manager import cache_status
from report_writer import equity_report_path, write_report, make_risk_footer


def print_cache_status(ticker: str):
    status = cache_status(ticker)
    print(f"\nCache status for {ticker}:")
    for dtype, info in status.items():
        marker = "✓" if info["fresh"] else "✗"
        print(f"  {marker} {dtype}: {info['path'] or 'not cached'}")


def run_technical(ticker: str) -> str:
    df = get_ohlcv(ticker, period="1y")
    snap = snapshot(df)
    lines = [
        f"# Technical Snapshot: {ticker}\n",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d')}",
        f"**Price**: ${snap['price']} USD",
        "",
        "| Indicator | Value |",
        "|-----------|-------|",
    ]
    for k, v in snap.items():
        lines.append(f"| {k} | {v} |")
    lines.append(make_risk_footer())
    return "\n".join(lines)


def run_financial_summary(ticker: str) -> str:
    info = get_info(ticker)
    name = info.get("longName", ticker)
    sector = info.get("sector", "N/A")
    market_cap = info.get("marketCap", 0)
    pe = info.get("trailingPE", "N/A")
    fwd_pe = info.get("forwardPE", "N/A")
    ps = info.get("priceToSalesTrailing12Months", "N/A")
    roe = info.get("returnOnEquity", "N/A")

    lines = [
        f"# Financial Summary: {ticker} — {name}\n",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d')}",
        f"**Sector**: {sector}",
        f"**Market Cap**: ${market_cap/1e9:.1f}B USD" if market_cap else "**Market Cap**: N/A",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Trailing P/E | {pe} |",
        f"| Forward P/E | {fwd_pe} |",
        f"| P/S (TTM) | {ps} |",
        f"| ROE | {f'{roe*100:.1f}%' if isinstance(roe, float) else 'N/A'} |",
        "",
        "*Full financial model requires financial-analyst agent.*",
        make_risk_footer(),
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--type", default="full", choices=["full", "financial", "technical"])
    parser.add_argument("--no-cache-check", action="store_true")
    args = parser.parse_args()

    ticker = args.ticker.upper()

    if not args.no_cache_check:
        print_cache_status(ticker)

    if args.type in ("technical", "full"):
        print(f"\nRunning technical snapshot for {ticker}...")
        content = run_technical(ticker)
        path = equity_report_path(ticker, "pv")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"  Written: {path}")

    if args.type in ("financial", "full"):
        print(f"Running financial summary for {ticker}...")
        content = run_financial_summary(ticker)
        path = equity_report_path(ticker, "financial")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"  Written: {path}")

    print(f"\nData pipeline complete for {ticker}.")
    print("To run deep analysis, use the orchestrator agent in Claude Code.")


if __name__ == "__main__":
    main()
