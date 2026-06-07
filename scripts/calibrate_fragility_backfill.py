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
    """The SCAN universe — consistent with cf94f89 and the live compute path.

    ``candidate_generator.get_universe()`` (= SP500_TOP_100 + any session-selected
    constituents) is the exact set the live Cockpit refresh scans, so good-news-sold
    AND breadth here reproduce the numbers the live system computed on those days.
    Falls back to theme-basket constituents only if the scan universe is unavailable."""
    try:
        from lib.candidate_generator import get_universe
        uni = [str(t).upper().strip() for t in (get_universe() or []) if str(t).strip()]
        if uni:
            return uni
    except Exception:  # noqa: BLE001
        pass
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


# ── vol_shrink calibration: new buyer-withdrawal metric vs the OLD dollar ratio ──
# The OLD metric (total-dollar-volume recent/baseline ratio) was REMOVED from the
# library this round; it is reimplemented HERE, local to the calibration tool, purely
# so the backfill can report the old reading alongside the new one as evidence.
VOL_COMPARE_THEMES = ("hbm_memory", "ai_chips")


def _theme_obj(theme_key: str):
    """A minimal ThemeMomentum-like object (constituents only) for a fixed theme."""
    from types import SimpleNamespace
    try:
        from lib.theme_baskets import THEME_BASKETS
        cfg_t = THEME_BASKETS.get(theme_key) or {}
    except Exception:  # noqa: BLE001
        cfg_t = {}
    return SimpleNamespace(theme_key=theme_key,
                           constituents=list(cfg_t.get("constituents", [])),
                           stage="leading", momentum_score=1.0)


def _old_dollar_ratio(frames, recent_days, baseline_days, min_const):
    """The OLD metric: Σ(recent mean dollar-vol)/Σ(baseline mean dollar-vol), or None.

    Reimplemented verbatim from the removed ``mi._theme_dollar_volume_ratio`` so the
    backfill can show what the old metric WOULD have read on each day."""
    need = recent_days + baseline_days
    tr = tb = 0.0
    used = 0
    for df in (frames or {}).values():
        c, v = mi._close_volume_lists(df)
        n = min(len(c), len(v))
        if n < need:
            continue
        dollar = [c[i] * v[i] for i in range(n)]
        recent = dollar[-recent_days:]
        baseline = dollar[-need:-recent_days]
        if not recent or not baseline:
            continue
        used += 1
        tr += sum(recent) / len(recent)
        tb += sum(baseline) / len(baseline)
    if used < min_const or tb <= 0:
        return None, used
    return tr / tb, used


def _vol_metrics_asof(theme_key, frame_loader, as_of, cfg):
    """(new_sig|None, old_ratio|None, n_used) for a fixed theme AS OF ``as_of``.

    Both metrics read the SAME constituent frames truncated to bars <= as_of (the
    library's own as-of loader), so the new/old comparison is on identical data."""
    rec = int(cfg["leading_theme_vol_recent_days"])
    base = int(cfg["leading_theme_vol_baseline_days"])
    minc = int(cfg["leading_theme_min_constituents"])
    th = _theme_obj(theme_key)
    loader = mi._trunc_loader(frame_loader, as_of)
    frames = {}
    for tk in th.constituents:
        try:
            frames[tk] = loader(tk)
        except Exception:  # noqa: BLE001
            frames[tk] = None
    new_sig, _ = mi._theme_buyer_withdrawal(frames, rec, base, minc, cfg)
    old_ratio, _ = _old_dollar_ratio(frames, rec, base, minc)
    return new_sig, old_ratio


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
        # Scope earnings to the SCAN universe (cf94f89): without universe= the bulk
        # calendar's whole-market reports would be counted (the 39/92 leak).
        reaction_records = mi._reaction_records(
            reports, frame_loader, bench_dates, today, cfg, universe=universe)
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

    # ── vol_shrink metric comparison (B3): new buyer-withdrawal vs old ratio ────
    # Day-by-day, for hbm_memory and ai_chips, report the NEW metric (up/down ratios
    # + fired) alongside what the OLD dollar-volume ratio WOULD have read.
    vol_cols = ["date"]
    for _tk in VOL_COMPARE_THEMES:
        vol_cols += [f"{_tk}_old_ratio", f"{_tk}_up_ratio",
                     f"{_tk}_down_ratio", f"{_tk}_fired"]
    vol_rows = []
    for d in window_dates:
        vr = {"date": str(d)}
        for _tk in VOL_COMPARE_THEMES:
            new_sig, old_ratio = _vol_metrics_asof(_tk, frame_loader, d, cfg)
            vr[f"{_tk}_old_ratio"] = ("" if old_ratio is None else round(old_ratio, 4))
            vr[f"{_tk}_up_ratio"] = ("" if not new_sig else new_sig["up_ratio"])
            vr[f"{_tk}_down_ratio"] = ("" if not new_sig else new_sig["down_ratio"])
            vr[f"{_tk}_fired"] = ("" if not new_sig else new_sig["fired"])
        vol_rows.append(vr)

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

    vol_csv_path = os.path.join(
        out_dir, f"fragility_volshrink_{today.replace('-', '')}.csv")
    with open(vol_csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=vol_cols)
        w.writeheader()
        w.writerows(vol_rows)

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

    # ── vol_shrink comparison table (B3) ─────────────────────────────────────
    lines += [
        "## vol_shrink metric comparison — new buyer-withdrawal vs old dollar ratio",
        "",
        "New metric fires when up-day volume CONTRACTS "
        f"(up_ratio < {cfg['leading_theme_up_vol_contract_ratio']}) AND down-day "
        f"volume EXPANDS (down_ratio > {cfg['leading_theme_down_vol_expand_ratio']}). "
        "`*_old_ratio` is the REMOVED total-dollar-volume recent/baseline ratio "
        f"(old flag fired when < {0.85}), shown for comparison only. Empty cells = "
        "fewer than the minimum usable constituents that day (degraded).",
        "",
        "| " + " | ".join(vol_cols) + " |",
        "| " + " | ".join("---" for _ in vol_cols) + " |",
    ]
    for r in vol_rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in vol_cols) + " |")
    _fired_days = {tk: [r["date"] for r in vol_rows if r.get(f"{tk}_fired") is True]
                   for tk in VOL_COMPARE_THEMES}
    lines += [""]
    for tk in VOL_COMPARE_THEMES:
        lines.append(f"**{tk} new-metric fired on:** "
                     f"{', '.join(_fired_days[tk]) or 'none in window'}")
    lines += [""]
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
    for tk in VOL_COMPARE_THEMES:
        print(f"vol_shrink[{tk}] new-metric fired on: "
              f"{', '.join(_fired_days[tk]) or 'none in window'}")
    print(f"Wrote: {os.path.relpath(md_path, _REPO_ROOT)} + "
          f"{os.path.relpath(csv_path, _REPO_ROOT)} + "
          f"{os.path.relpath(vol_csv_path, _REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
