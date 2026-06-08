#!/usr/bin/env python3
"""
scripts/backfill_anchors.py — Anchor Intelligence v2.3 backfill round (B2).

ONE-TIME, ON-DEMAND offline backfill of the RECOMPUTABLE valuation anchors into the
append-only anchor archive (``data/anchor_archive.jsonl``). This gives
``lib.anchor_migration``'s readout real history on day one instead of a 1–2 month
cold start.

This is NOT triggered at app startup and is NEVER on the ranking / refresh path
(those must stay fast and network-free). Run it manually:

    # Default: 6-month window, weekly cadence, end_date = today (UTC).
    python3 -B scripts/backfill_anchors.py MU NVDA AAPL

    # Custom window / cadence / anchor date (deterministic for reproducible runs):
    python3 -B scripts/backfill_anchors.py MU --window-months 6 --cadence-days 7 \
            --end-date 2026-06-08

What is recomputed (HARD INVARIANT — see lib/anchor_backfill.py):
  * RECOMPUTABLE (backfilled): DCF, relative-PE (sector P/E × historical EPS), and
    the cyclical PB/PS historical band — all from historical prices + dated
    annual/quarterly fundamentals, by REUSING the live assembler.
  * NEVER fabricated: the analyst anchor (no historical analyst-target series
    exists anywhere) — every backfilled record sets analyst_pool to the
    ``analyst_history_unavailable`` sentinel.

Idempotent: re-running for an already-covered (ticker, as-of date) adds ZERO
duplicate rows (persistent guard on the archive's backfill vintages). Append-only:
a prior row is never rewritten. The fetch reads historical prices + dated
statements + the static sector label only — never any live analyst endpoint.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from lib import anchor_backfill as ab  # noqa: E402


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc).date()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="One-time offline anchor backfill (recomputable anchors only).")
    ap.add_argument("tickers", nargs="+", help="Ticker symbols (e.g. MU NVDA).")
    ap.add_argument("--window-months", type=int, default=ab.BACKFILL_WINDOW_MONTHS,
                    help=f"Backfill window in months (default {ab.BACKFILL_WINDOW_MONTHS}).")
    ap.add_argument("--cadence-days", type=int, default=ab.BACKFILL_CADENCE_DAYS,
                    help=f"Days between as-of points (default {ab.BACKFILL_CADENCE_DAYS}, weekly).")
    ap.add_argument("--end-date", type=str, default=None,
                    help="Anchor date YYYY-MM-DD (default: today UTC).")
    args = ap.parse_args(argv)

    end_date = _parse_date(args.end_date) if args.end_date else None

    print(f"Anchor backfill — window={args.window_months}mo, "
          f"cadence={args.cadence_days}d, "
          f"end_date={args.end_date or 'today'}")
    grand_written = 0
    for tk in args.tickers:
        summary = ab.backfill_ticker(
            tk, window_months=args.window_months, cadence_days=args.cadence_days,
            end_date=end_date)
        grand_written += summary["written"]
        print(
            f"  {summary['ticker']:>6}: {summary['written']} written "
            f"(of {summary['dates_total']} as-of dates; "
            f"{summary['skipped_already_covered']} already covered, "
            f"{summary['skipped_no_price']} no-price, "
            f"{summary['degraded']} degraded/partial)")
    print(f"Done. {grand_written} archive rows appended.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
