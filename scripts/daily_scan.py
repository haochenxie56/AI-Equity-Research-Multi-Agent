#!/usr/bin/env python3
"""
Daily US equity scan. Runs the configured strategies and writes results to research/scans/.
Usage: python scripts/daily_scan.py [--strategy momentum] [--universe sp500] [--top 20]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import pandas as pd
import yfinance as yf

from cache_manager import get_or_fetch
from technical import snapshot
from report_writer import scan_report_path, write_report, make_risk_footer, _today


SP500_CSV_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"

# Fallback list covering all 11 GICS sectors (~80 large-caps)
_FALLBACK_TICKERS = [
    # Technology
    "AAPL","MSFT","NVDA","AVGO","ORCL","CRM","AMD","QCOM","TXN","AMAT","KLAC","LRCX","MU","INTC","ADI",
    # Communication Services
    "META","GOOGL","GOOG","NFLX","DIS","CMCSA","T","VZ",
    # Consumer Discretionary
    "AMZN","TSLA","HD","MCD","NKE","SBUX","LOW","TJX","BKNG",
    # Consumer Staples
    "WMT","PG","KO","PEP","COST","PM","MO","CL",
    # Health Care
    "LLY","UNH","JNJ","ABBV","MRK","ABT","TMO","DHR","AMGN","GILD","ISRG",
    # Financials
    "BRK-B","JPM","V","MA","BAC","WFC","GS","MS","BLK","SPGI","CB",
    # Industrials
    "GE","CAT","RTX","HON","UNP","UPS","BA","LMT","DE",
    # Energy
    "XOM","CVX","COP","SLB","EOG","MPC","PSX",
    # Materials
    "LIN","APD","SHW","ECL","NEM","FCX",
    # Real Estate
    "PLD","AMT","EQIX","SPG","O",
    # Utilities
    "NEE","DUK","SO","D","AEP",
]


def load_sp500_tickers() -> list[str]:
    # Try GitHub-hosted CSV first
    try:
        df = pd.read_csv(SP500_CSV_URL)
        col = next((c for c in df.columns if c.lower() in ("symbol", "ticker")), None)
        if col:
            tickers = df[col].tolist()
            print(f"  Loaded {len(tickers)} tickers from GitHub CSV.")
            return tickers
    except Exception as e:
        print(f"  GitHub CSV failed: {e}")

    # Fall back to built-in list
    print(f"  Using built-in fallback list ({len(_FALLBACK_TICKERS)} tickers).")
    return _FALLBACK_TICKERS


def screen_momentum(tickers: list[str], top_n: int = 20) -> list[dict]:
    """
    Momentum screen: Price > SMA200, RSI between 50-70, volume ratio > 1.2,
    sorted by 3-month return descending.
    """
    results = []
    for ticker in tickers:
        try:
            df = get_or_fetch(ticker, "ohlcv_1y_1d", lambda t=ticker: yf.Ticker(t).history(period="1y"))
            if df is None or len(df) < 200:
                continue
            snap = snapshot(df)
            ret_3m = (df["Close"].iloc[-1] / df["Close"].iloc[-63] - 1) if len(df) >= 63 else None
            if not snap["above_SMA200"]:
                continue
            rsi = snap.get("RSI_14", 0)
            if not (50 <= rsi <= 72):
                continue
            if snap.get("Vol_ratio_20d", 0) < 1.1:
                continue
            results.append({
                "ticker": ticker,
                "price": snap["price"],
                "RSI": snap["RSI_14"],
                "vol_ratio": snap["Vol_ratio_20d"],
                "ret_3m": round(ret_3m * 100, 1) if ret_3m else None,
                "pct_from_52w_high": snap["pct_from_52w_high"],
            })
        except Exception:
            continue

    results.sort(key=lambda x: x.get("ret_3m") or -999, reverse=True)
    return results[:top_n]


def build_report(strategy: str, results: list[dict]) -> str:
    header = f"""# Stock Scan: {strategy.title()}

**Date**: {_today()}
**Universe**: S&P 500 (NYSE + NASDAQ)
**Strategy**: {strategy}
**Hits**: {len(results)}

---

## Candidate List

| Rank | Ticker | Price (USD) | RSI(14) | Vol Ratio | 3M Return | % from 52W High |
|------|--------|-------------|---------|-----------|-----------|-----------------|
"""
    rows = []
    for i, r in enumerate(results, 1):
        rows.append(
            f"| {i} | {r['ticker']} | ${r['price']} | {r.get('RSI', '-')} "
            f"| {r.get('vol_ratio', '-')}x | {r.get('ret_3m', '-')}% | {r.get('pct_from_52w_high', '-')}% |"
        )
    return header + "\n".join(rows) + make_risk_footer()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default="momentum", choices=["momentum"])
    parser.add_argument("--universe", default="sp500", choices=["sp500"])
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()

    print(f"Loading {args.universe} tickers...")
    tickers = load_sp500_tickers()
    if not tickers:
        print("No tickers loaded. Exiting.")
        sys.exit(1)
    print(f"Loaded {len(tickers)} tickers. Running {args.strategy} screen...")

    if args.strategy == "momentum":
        results = screen_momentum(tickers, top_n=args.top)

    report = build_report(args.strategy, results)
    path = scan_report_path(args.strategy)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    print(f"Report written: {path}")


if __name__ == "__main__":
    main()
