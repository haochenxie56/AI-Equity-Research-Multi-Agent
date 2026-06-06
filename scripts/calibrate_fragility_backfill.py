#!/usr/bin/env python3
"""
scripts/calibrate_fragility_backfill.py — Phase 7B Task B (calibration TOOL).

Recompute the market-internals fragility reading "as of" each of the past ~N
trading days from cached (or fetched) OHLCV, applying hysteresis over the
recomputed series, and write a per-day table (markdown + CSV) for threshold
calibration. This is a TOOL, not app code: it MAY fetch (``--fetch``); it is NOT
subject to the network-free ranking contract. It prefers the cache.

    python3 scripts/calibrate_fragility_backfill.py [--days 30] [--fetch]

⚠️  HINDSIGHT CAVEAT: the backfill uses TODAY'S code and TODAY'S universe applied
to past days — it is hindsight-tinted and is for THRESHOLD CALIBRATION ONLY, never
for performance claims. Annotate days against remembered market feel, then adjust
``lib.market_internals.INTERNALS_CONFIG``.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_REPO_ROOT, os.path.join(_REPO_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib.market_internals as mi  # noqa: E402

CAVEAT = ("Backfill uses TODAY'S code and TODAY'S universe applied to past days — "
          "hindsight-tinted, for THRESHOLD CALIBRATION ONLY, never performance claims.")


def _universe() -> list:
    """Deduped theme-basket constituents = the breadth/internals universe."""
    out: list = []
    try:
        from lib.theme_baskets import THEME_BASKETS
        for cfg in THEME_BASKETS.values():
            for tk in cfg.get("constituents", []):
                if tk not in out:
                    out.append(tk)
    except Exception:  # noqa: BLE001
        pass
    return out


def _loaders(fetch: bool):
    """(frame_loader, label). Default: cache-only. ``--fetch``: ui_utils.load_ohlcv."""
    if fetch:
        from ui_utils import load_ohlcv
        return (lambda tk: load_ohlcv(tk, "1y")), "fetch"
    from lib.relative_strength import _default_frame_loader
    return _default_frame_loader, "cache-only"


def _today_str() -> str:
    # The system date (UTC) — a tool, so a real clock read is acceptable here.
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fragility backfill calibration tool")
    ap.add_argument("--days", type=int, default=30, help="trading days to backfill")
    ap.add_argument("--fetch", action="store_true",
                    help="fetch via yfinance instead of cache-only")
    args = ap.parse_args()
    cfg = mi.INTERNALS_CONFIG
    today = _today_str()

    frame_loader, src_label = _loaders(args.fetch)
    universe = _universe()

    spy = frame_loader("SPY")
    qqq = frame_loader("QQQ")
    bench_arr = mi._dated_arrays(spy) if spy is not None else None
    qqq_arr = mi._dated_arrays(qqq) if qqq is not None else None
    bench_dates = (bench_arr[0] if bench_arr else (qqq_arr[0] if qqq_arr else []))
    if not bench_dates:
        print("ERROR: no benchmark calendar (SPY/QQQ) available "
              + ("(try --fetch)" if not args.fetch else "(fetch failed)"))
        return 1

    universe_arrays = {}
    for tk in universe:
        try:
            df = frame_loader(tk)
        except Exception:  # noqa: BLE001
            df = None
        universe_arrays[tk] = mi._dated_arrays(df) if df is not None else None
    sector_arrays = mi._preload_sector_arrays(frame_loader)

    # Themes (for the leading-theme volume component) — best-effort.
    themes = None
    try:
        from lib.theme_baskets import compute_all_themes
        themes = compute_all_themes()
    except Exception:  # noqa: BLE001
        themes = None

    # Earnings: ONE bulk historical-calendar call over the window (minimal calls).
    reaction_records = []
    earnings_note = "ok"
    try:
        import datetime as _dt
        lo = (_dt.date.fromisoformat(str(bench_dates[-1]))
              - _dt.timedelta(days=int(args.days) * 2 + 10)).isoformat()
        from lib.signal_engine import fetch_earnings_reactions_calendar
        reports = fetch_earnings_reactions_calendar(lo, today)
        reaction_records = mi._reaction_records(reports, frame_loader, bench_dates, today, cfg)
    except Exception as exc:  # noqa: BLE001
        earnings_note = f"unavailable ({exc})"

    # The window: the last `days` trading dates on/before today.
    pos_today = mi._pos_le(bench_dates, today)
    if pos_today is None:
        pos_today = len(bench_dates) - 1
    start = max(0, pos_today - int(args.days) + 1)
    window_dates = bench_dates[start:pos_today + 1]

    rows = []
    raw_chrono = []
    for d in window_dates:
        comp = mi._components_asof(
            d, bench_arr=bench_arr, qqq_arr=qqq_arr, universe_arrays=universe_arrays,
            sector_arrays=sector_arrays, frame_loader=frame_loader, themes=themes,
            reaction_records=reaction_records, bench_dates=bench_dates, cfg=cfg)
        points, triggered = mi._score_components(comp, cfg)
        raw = mi._raw_level_from_points(points, cfg)
        raw_chrono.append(raw)
        effective, _ = mi._replay_hysteresis(raw_chrono, cfg)
        rows.append({
            "date": str(d),
            "dist_spy": comp.distribution_days_spy,
            "dist_qqq": comp.distribution_days_qqq,
            "breadth20": comp.breadth_above_sma20,
            "breadth50": comp.breadth_above_sma50,
            "breadth_slope": comp.breadth_slope,
            "weak_bounce": comp.weak_bounce,
            "good_news_sold": comp.good_news_sold,
            "earnings_eval": comp.earnings_evaluated,
            "vol_shrink": comp.leading_theme_volume_shrinking,
            "od_dir": comp.offense_defense_direction,
            "od_mag": comp.offense_defense_magnitude,
            "points": points,
            "raw": raw,
            "effective": effective,
        })

    # Mark level-transition days (effective changed vs the prior day).
    prev_eff = None
    for r in rows:
        r["transition"] = "*" if (prev_eff is not None and r["effective"] != prev_eff) else ""
        prev_eff = r["effective"]

    # ── Write markdown + CSV to docs/calibration/ ────────────────────────────
    out_dir = os.path.join(_REPO_ROOT, "docs", "calibration")
    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, f"fragility_backfill_{today.replace('-', '')}.md")
    csv_path = os.path.join(out_dir, f"fragility_backfill_{today.replace('-', '')}.csv")

    cols = ["date", "dist_spy", "dist_qqq", "breadth20", "breadth50", "breadth_slope",
            "weak_bounce", "good_news_sold", "earnings_eval", "vol_shrink",
            "od_dir", "od_mag", "points", "raw", "effective", "transition"]
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    lines = [
        f"# Fragility backfill — {today}",
        "",
        f"> ⚠️ {CAVEAT}",
        "",
        f"- Source: **{src_label}** · universe: **{len(universe)}** tickers · "
        f"window: **{len(window_dates)}** trading days · earnings: **{earnings_note}**",
        f"- Config snapshot: rolling_window={cfg['rolling_window_sessions']}, "
        f"elevated_points={cfg['elevated_points']}, high_points={cfg['high_points']}, "
        f"escalate={cfg['hysteresis_escalate_sessions']}, "
        f"dist(elevated/high)={cfg['distribution_days_elevated']}/{cfg['distribution_days_high']}, "
        f"breadth_weak={cfg['breadth_weak_pct']}, slope_drop={cfg['breadth_slope_drop']}",
        "",
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
    ]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    transitions = [r["date"] for r in rows if r["transition"]]
    lines += ["", f"**Level transitions:** {', '.join(transitions) or 'none'}", ""]
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"⚠️  {CAVEAT}")
    print(f"Backfill: {len(window_dates)} days · source={src_label} · "
          f"universe={len(universe)} · earnings={earnings_note}")
    from collections import Counter
    eff_dist = Counter(r["effective"] for r in rows)
    print(f"Effective-level distribution: {dict(eff_dist)}")
    print(f"Level transitions: {', '.join(transitions) or 'none'}")
    if rows:
        last = rows[-1]
        print(f"Today ({last['date']}): raw={last['raw']} points={last['points']} "
              f"effective={last['effective']}")
    print(f"Wrote: {os.path.relpath(md_path, _REPO_ROOT)} + "
          f"{os.path.relpath(csv_path, _REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
