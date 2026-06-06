#!/usr/bin/env python3
"""
scripts/test_reliability_phase_7b_rotation_internals.py

Phase 7B — Multi-window Relative Strength, Two-Ring Rotation Engine, and Market
Internals Fragility Layer. Mock-only / offline: every external dependency is a
fixture; no network, no LLM on the computation paths.

Coverage:
  1. Multi-window RS: full window set + excess vs SPY/QQQ; per-horizon composite
     consumption (SHORT=5D/10D, MID=1M/3M, LONG=6M/12M); 12M→6M window degrade.
  2. Divergence matrix quadrants incl. boundary thresholds.
  3. Theme stage labels + breadth confirmation + the unconfirmed (single-stock)
     guard.
  4. Offense/defense reading (direction, magnitude, confirming windows).
  5. Distribution-day counting on fixture OHLCV.
  6. Earnings-reaction (good-news-sold) counting.
  7. Hysteresis: a 1-day spike never escalates; an N-day hold does; de-escalation.
  8. Tighten-only invariants: the regime object is byte-identical with fragility
     forced high; no gate is relaxed; only SHORT is gated at high.
  9. Snapshot fields complete.
 10. Structural: no network/LLM imports on the computation paths.
"""

from __future__ import annotations

import os
import sys

os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["FINNHUB_API_KEY"] = ""

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_REPO_ROOT, os.path.join(_REPO_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PASS = 0
FAIL = 0
_failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        d = f"  [{detail}]" if detail else ""
        _failures.append(f"FAIL  {label}{d}")


def _df(closes, volumes=None):
    import pandas as pd
    if volumes is None:
        volumes = [1_000_000] * len(closes)
    return pd.DataFrame({"Close": closes, "Volume": volumes})


# ===========================================================================
# 1. Multi-window Relative Strength
# ===========================================================================
import lib.relative_strength as rsm  # noqa: E402

# A clear leader: 300 sessions compounding up; benchmarks flat.
_lead = [100 * (1.002 ** i) for i in range(300)]
_flat = [100.0] * 300
_bench = rsm.benchmark_returns(lambda t, p=None: _df(_flat))
_rs = rsm.compute_relative_strength("LEAD", _df(_lead), _bench)

check("1.1 all six windows present",
      set(_rs.windows.keys()) == {"5d", "10d", "1m", "3m", "6m", "12m"},
      str(list(_rs.windows.keys())))
check("1.2 flat fields populated for new windows",
      all(getattr(_rs, f"ret_{w}") is not None for w in ("10d", "3m", "6m", "12m")))
check("1.3 leader excess vs SPY positive across windows",
      all((_rs.windows[w]["vs_spy"] or 0) > 0 for w in ("5d", "1m", "6m", "12m")))
check("1.4 per-horizon composites computed", None not in
      (_rs.rs_short, _rs.rs_mid, _rs.rs_long))
check("1.5 leader composites are bullish (>0.6)",
      _rs.rs_short > 0.6 and _rs.rs_mid > 0.6 and _rs.rs_long > 0.6)
check("1.6 12M computable from 300 bars → not window-degraded",
      _rs.rs_window_degraded is False)

# Window degrade: ~150 bars cannot compute 12M → degrade to 6M + flag.
_rs2 = rsm.compute_relative_strength("LD2", _df(_lead[:150]), _bench)
check("1.7 12M None on short history", _rs2.ret_12m is None)
check("1.8 6M still computable on 150 bars", _rs2.ret_6m is not None)
check("1.9 rs_window_degraded flagged", _rs2.rs_window_degraded is True)
check("1.10 long composite still produced (rests on 6M)", _rs2.rs_long is not None)

# Horizon consumption in the ranker: SHORT/MID/LONG draw their OWN composite.
import lib.opportunity_ranker as orr  # noqa: E402

_rs_split = rsm.RelativeStrength("SPLIT", rs_composite=0.5,
                                 rs_short=0.9, rs_mid=0.5, rs_long=0.1,
                                 data_source="live")
check("1.11 _horizon_rs_comp picks short composite",
      orr._horizon_rs_comp(_rs_split, "short", 0.5) == 0.9)
check("1.12 _horizon_rs_comp picks long composite",
      orr._horizon_rs_comp(_rs_split, "long", 0.5) == 0.1)
# Legacy object (no per-horizon composite) falls back to rs_composite (7A compat).
_rs_legacy = rsm.RelativeStrength("LEG", rs_composite=0.7)
check("1.13 legacy RS (no per-horizon comp) falls back to the supplied composite",
      orr._horizon_rs_comp(_rs_legacy, "mid", _rs_legacy.rs_composite) == 0.7)
check("1.14 None RS falls back to provided neutral",
      orr._horizon_rs_comp(None, "short", 0.5) == 0.5)

# why_now RS line follows the selected horizon (SHORT=5D, MID=1M, LONG=6M).
_rs_lines = rsm.RelativeStrength("WL", ret_5d_vs_qqq=0.03, ret_1m_vs_qqq=0.05,
                                 ret_6m_vs_qqq=0.09, rs_composite=0.7)
_wn_short, _ = orr.build_reason_codes({"ticker": "WL"}, _rs_lines, 0.3, horizon="short")
_wn_long, _ = orr.build_reason_codes({"ticker": "WL"}, _rs_lines, 0.3, horizon="long")
check("1.15 short why_now RS line uses 5D label",
      any("5" in r.text_zh and "QQQ" in r.text_en for r in _wn_short),
      str([r.text_en for r in _wn_short]))
check("1.16 long why_now RS line uses 6M label",
      any("6" in r.text_en and "QQQ" in r.text_en for r in _wn_long),
      str([r.text_en for r in _wn_long]))


# ===========================================================================
# 2. Theme divergence matrix (boundary thresholds)
# ===========================================================================
import lib.theme_baskets as tb  # noqa: E402

check("2.1 leading: both strong", tb.classify_divergence(2.0, 3.0) == tb.STAGE_LEADING)
check("2.2 rotating_in: 5D strong, 1M weak",
      tb.classify_divergence(2.0, -1.0) == tb.STAGE_ROTATING_IN)
check("2.3 rotating_out: 5D weak, 1M strong",
      tb.classify_divergence(-1.0, 2.0) == tb.STAGE_ROTATING_OUT)
check("2.4 out_of_favor: both weak",
      tb.classify_divergence(-1.0, -2.0) == tb.STAGE_OUT_OF_FAVOR)
# Boundary: exactly the threshold (0.0) is on the WEAK side (strictly-greater).
check("2.5 boundary 5D==0 is weak (out_of_favor when 1M also 0)",
      tb.classify_divergence(0.0, 0.0) == tb.STAGE_OUT_OF_FAVOR)
check("2.6 boundary 5D==0, 1M strong → rotating_out",
      tb.classify_divergence(0.0, 1.0) == tb.STAGE_ROTATING_OUT)
check("2.7 missing window → empty label", tb.classify_divergence(None, 1.0) == "")


# ===========================================================================
# 3. Theme stage + breadth confirmation + unconfirmed guard
# ===========================================================================
# Constituent closes: 3 strong, 1 flat. Benchmark 1M return = 0%.
_strong = _df([100 * (1.003 ** i) for i in range(60)])["Close"]
_weak = _df([100.0] * 60)["Close"]

beat, above, n = tb.compute_theme_breadth(
    {"A": _strong, "B": _strong, "C": _strong, "D": _weak}, 0.0, "1m")
check("3.1 breadth counts all constituents", n == 4)
check("3.2 breadth beat == 0.75 (3 of 4 beat flat bench)", beat == 0.75, str(beat))
check("3.3 breadth above_sma20 ~0.75", above is not None and above >= 0.5)

# Mock loader so compute_theme_momentum is fully offline + deterministic.
def _mk_loader(strong_set):
    def _loader(tk):
        return _strong if tk in strong_set else _weak
    return _loader

# A rotating_in theme that is breadth-confirmed (most constituents strong).
_cfg_key = next(iter(tb.THEME_BASKETS))
_consts = tb.THEME_BASKETS[_cfg_key]["constituents"]
_bench_map = {"QQQ": tb._window_returns(_weak)}  # flat benchmark
_r_conf = tb.compute_theme_momentum(
    _cfg_key, bench_returns_map=_bench_map,
    close_loader=_mk_loader(set(_consts)), active_window="1m")
check("3.4 confirmed: all-strong leading theme is breadth-confirmed",
      _r_conf.stage in (tb.STAGE_LEADING, tb.STAGE_ROTATING_IN)
      and _r_conf.stage_confirmed is True, f"{_r_conf.stage}/{_r_conf.breadth_beat_pct}")

# Single-stock event: only ONE constituent strong → low breadth → unconfirmed.
_r_unconf = tb.compute_theme_momentum(
    _cfg_key, bench_returns_map=_bench_map,
    close_loader=_mk_loader({_consts[0]}), active_window="1m")
check("3.5 unconfirmed guard: single-stock strength is NOT confirmed",
      _r_unconf.stage_confirmed is False, str(_r_unconf.breadth_beat_pct))
check("3.6 excess fields populated", _r_conf.excess_5d is not None
      and _r_conf.excess_1m is not None)


# ===========================================================================
# 4. Offense / defense reading
# ===========================================================================
import lib.rotation as rot  # noqa: E402

# Offense basket strongly positive excess, defense negative → "offense".
_off_excess = {s: {w: 6.0 for w in rot.OD_WINDOW_DAYS} for s in rot.OFFENSE_SECTORS}
_def_excess = {s: {w: -6.0 for w in rot.OD_WINDOW_DAYS} for s in rot.DEFENSE_SECTORS}
_sector_excess = {**_off_excess, **_def_excess}
_od = rot.offense_defense_reading(_sector_excess)
check("4.1 direction == offense", _od["direction"] == "offense", _od["direction"])
check("4.2 magnitude strong (avg diff 12pp)", _od["magnitude"] == "strong", str(_od["avg_diff"]))
check("4.3 all windows confirm", len(_od["confirming_windows"]) == len(rot.OD_WINDOW_DAYS))
check("4.4 by_window populated", set(_od["by_window"].keys()) == set(rot.OD_WINDOW_DAYS))

# Defensive: flip the sign.
_od_def = rot.offense_defense_reading(
    {**{s: {w: -6.0 for w in rot.OD_WINDOW_DAYS} for s in rot.OFFENSE_SECTORS},
     **{s: {w: 6.0 for w in rot.OD_WINDOW_DAYS} for s in rot.DEFENSE_SECTORS}})
check("4.5 direction == defense when defense leads", _od_def["direction"] == "defense")

# Balanced: tiny differential below the balanced band.
_od_bal = rot.offense_defense_reading(
    {**{s: {w: 0.2 for w in rot.OD_WINDOW_DAYS} for s in rot.OFFENSE_SECTORS},
     **{s: {w: 0.0 for w in rot.OD_WINDOW_DAYS} for s in rot.DEFENSE_SECTORS}})
check("4.6 direction == balanced when differential tiny",
      _od_bal["direction"] == "balanced", str(_od_bal["avg_diff"]))
check("4.7 empty input → balanced, 0 windows",
      rot.offense_defense_reading({})["n_windows"] == 0)


# ===========================================================================
# 5. Distribution-day counting
# ===========================================================================
import lib.market_internals as mi  # noqa: E402

# Build a 30-session series with exactly 3 distribution days (down >=0.2% on
# higher volume than the prior session). Start flat, inject three.
_c = [100.0]
_v = [1_000.0]
for i in range(1, 30):
    _c.append(_c[-1] * 1.001)   # mild up day
    _v.append(1_000.0)
# Inject distribution days at indices 10, 20, 28: down 1% on higher volume.
for idx in (10, 20, 28):
    _c[idx] = _c[idx - 1] * 0.99
    _v[idx] = _v[idx - 1] * 1.5
dd = mi.count_distribution_days(_c, _v)
check("5.1 distribution days counted == 3", dd == 3, str(dd))
check("5.2 too-short series → None", mi.count_distribution_days([100.0], [1.0]) is None)
# A down day on LOWER volume is NOT a distribution day.
_c2 = [100.0, 99.0]
_v2 = [1_000.0, 500.0]
check("5.3 down day on lower volume not counted",
      mi.count_distribution_days(_c2, _v2) == 0)


# ===========================================================================
# 6. Earnings-reaction (good-news-sold) counting
# ===========================================================================
_reactions = [
    {"direction": "beat", "next_session_return": -0.03},  # good news SOLD
    {"direction": "beat", "next_session_return": 0.04},   # rewarded
    {"direction": "beat", "next_session_return": -0.01},  # good news SOLD
    {"direction": "miss", "next_session_return": -0.05},  # not good news
    {"direction": "beat"},                                # missing reaction → skip
]
gns, ev = mi.count_good_news_sold(_reactions)
check("6.1 good-news-sold count == 2", gns == 2, str(gns))
check("6.2 evaluated == 4 (one skipped)", ev == 4, str(ev))
check("6.3 empty → (0,0)", mi.count_good_news_sold([]) == (0, 0))


# ===========================================================================
# 7. Hysteresis
# ===========================================================================
# A single-day spike to high (prior normal, no recent highs) never escalates.
lvl, _ = mi.apply_hysteresis("high", "normal", [])
check("7.1 single-day high spike does NOT escalate", lvl == "normal", lvl)
# Held for 2 consecutive sessions (today + 1 prior high) → escalates (default esc=2).
lvl2, _ = mi.apply_hysteresis("high", "normal", ["high"])
check("7.2 2-session hold escalates to high", lvl2 == "high", lvl2)
# Elevated for 2 sessions escalates from normal.
lvl3, _ = mi.apply_hysteresis("elevated", "normal", ["elevated"])
check("7.3 2-session elevated escalates", lvl3 == "elevated", lvl3)
# A single elevated day after normal does not escalate.
lvl4, _ = mi.apply_hysteresis("elevated", "normal", ["normal"])
check("7.4 single elevated day holds at normal", lvl4 == "normal", lvl4)
# De-escalation is faster (default 1): one calm day drops the level.
lvl5, _ = mi.apply_hysteresis("normal", "high", [])
check("7.5 de-escalation immediate (faster)", lvl5 == "normal", lvl5)
# Same level holds.
lvl6, _ = mi.apply_hysteresis("elevated", "elevated", ["elevated"])
check("7.6 same level holds", lvl6 == "elevated", lvl6)

# End-to-end through compute_fragility (the 1-day-spike never escalates path).
# Inputs that score 4 points → raw "high" (distribution-days-high +2, good-news-sold-high +2).
_spike = mi.compute_fragility(distribution_days_spy=8, good_news_sold=3,
                              prior_level="normal", recent_raw_levels=[])
check("7.7 compute_fragility: raw high but effective normal on spike",
      _spike.raw_level == "high" and _spike.level == "normal",
      f"{_spike.raw_level}/{_spike.level}")
_held = mi.compute_fragility(distribution_days_spy=8, good_news_sold=3,
                             prior_level="normal", recent_raw_levels=["high"])
check("7.8 compute_fragility: 2-session hold escalates", _held.level == "high")

# 7.9–7.12 — date adjacency (Codex fix 1): "consecutive" = trading-day-adjacent
# snapshot records; a calendar gap > bound breaks the chain.
check("7.9 adjacency bound visible in config",
      mi.INTERNALS_CONFIG.get("hysteresis_max_calendar_gap_days") == 4)
# Fri + next Wed (gap 5 calendar days > 4) → NOT consecutive → no escalation.
_gap, _ = mi.apply_hysteresis("high", "normal", ["high"],
                              recent_dates=["2026-06-05"], today_date="2026-06-10")
check("7.10 gapped highs (Fri+Wed) do NOT escalate", _gap == "normal", _gap)
# Fri + Mon (weekend gap 3 days ≤ 4) → consecutive → escalates.
_adj, _ = mi.apply_hysteresis("high", "normal", ["high"],
                              recent_dates=["2026-06-05"], today_date="2026-06-08")
check("7.11 weekend-adjacent highs (Fri+Mon) DO escalate", _adj == "high", _adj)
# Chain-break restart: today + adjacent high, but the 2-days-back high is gapped —
# only counts 2 adjacent → still escalates (esc=2); a single gapped record can't add.
_chain, _ = mi.apply_hysteresis(
    "high", "elevated", ["high", "high"],
    recent_dates=["2026-06-08", "2026-06-01"], today_date="2026-06-09")
check("7.12 chain counts only trading-day-adjacent records", _chain == "high", _chain)
# De-escalation stays immediate regardless of gaps.
_de, _ = mi.apply_hysteresis("normal", "high", ["high"],
                             recent_dates=["2026-06-01"], today_date="2026-06-10")
check("7.13 de-escalation immediate despite gap", _de == "normal", _de)

# 7.14–7.21 — adjacency from the BENCHMARK TRADING CALENDAR (revised fix 1).
# A trading-date index for the week of 2026-06-05 (Fri) onward (no weekend dates).
_cal = ["2026-06-05", "2026-06-08", "2026-06-09", "2026-06-10", "2026-06-11", "2026-06-12"]
check("7.14 is_adjacent: Fri+Mon consecutive (no trading day between)",
      mi.is_adjacent_session("2026-06-05", "2026-06-08", _cal) is True)
check("7.15 is_adjacent: Fri+Wed NOT consecutive (Mon/Tue between)",
      mi.is_adjacent_session("2026-06-05", "2026-06-10", _cal) is False)
check("7.16 is_adjacent: out-of-range dates → None (fallback)",
      mi.is_adjacent_session("2020-01-01", "2020-01-02", _cal) is None)
# Fri+Mon via the trading calendar → escalates.
_cal_mon, _ = mi.apply_hysteresis(
    "high", "normal", ["high"], recent_dates=["2026-06-05"],
    today_date="2026-06-08", benchmark_index=_cal)
check("7.17 calendar Fri+Mon escalates", _cal_mon == "high", _cal_mon)
# Fri+Wed with Mon/Tue trading days between → chain broken, no escalation.
_cal_wed, _ = mi.apply_hysteresis(
    "high", "normal", ["high"], recent_dates=["2026-06-05"],
    today_date="2026-06-10", benchmark_index=_cal)
check("7.18 calendar Fri+Wed (Mon/Tue between) does NOT escalate",
      _cal_wed == "normal", _cal_wed)
# Market-holiday Monday: index MISSING 2026-06-08 → Fri+Tue still consecutive.
_cal_hol = ["2026-06-05", "2026-06-09", "2026-06-10", "2026-06-11"]
check("7.19 holiday Monday: Fri+Tue still consecutive (no trading day between)",
      mi.is_adjacent_session("2026-06-05", "2026-06-09", _cal_hol) is True)
_hol_esc, _ = mi.apply_hysteresis(
    "high", "normal", ["high"], recent_dates=["2026-06-05"],
    today_date="2026-06-09", benchmark_index=_cal_hol)
check("7.20 holiday-gap Fri+Tue escalates via the trading calendar",
      _hol_esc == "high", _hol_esc)
# Fallback path when the index is unavailable → calendar bound + adjacency_degraded.
_flags = {}
_fb, _ = mi.apply_hysteresis(
    "high", "normal", ["high"], recent_dates=["2026-06-05"],
    today_date="2026-06-08", benchmark_index=None, out_flags=_flags)
check("7.21 no index → fallback escalates AND flags adjacency_degraded",
      _fb == "high" and _flags.get("adjacency_degraded") is True, str(_flags))
# compute_fragility surfaces adjacency_degraded into the reading + degraded list.
_adj_reading = mi.compute_fragility(
    distribution_days_spy=8, good_news_sold=3, prior_level="normal",
    recent_raw_levels=["high"], recent_dates=["2026-06-05"],
    today_date="2026-06-08")  # no benchmark_index → degraded
check("7.22 reading.adjacency_degraded set when no trading calendar",
      _adj_reading.adjacency_degraded is True
      and "hysteresis_adjacency" in _adj_reading.degraded)
# With the calendar present, adjacency is NOT degraded.
_ok_reading = mi.compute_fragility(
    distribution_days_spy=8, good_news_sold=3, prior_level="normal",
    recent_raw_levels=["high"], recent_dates=["2026-06-05"],
    today_date="2026-06-08", benchmark_index=_cal)
check("7.23 calendar present → adjacency NOT degraded + escalates",
      _ok_reading.adjacency_degraded is False and _ok_reading.level == "high")
# 7.24 — production path: a pandas DatetimeIndex (Timestamps) works like the list.
import pandas as _pd_cal  # noqa: E402
_didx = _pd_cal.DatetimeIndex([_pd_cal.Timestamp(d) for d in _cal])
check("7.24 pandas DatetimeIndex adjacency (Fri+Mon True, Fri+Wed False)",
      mi.is_adjacent_session("2026-06-05", "2026-06-08", _didx) is True
      and mi.is_adjacent_session("2026-06-05", "2026-06-10", _didx) is False)


# ===========================================================================
# 8. Tighten-only invariants
# ===========================================================================
# 8a — the regime object is byte-identical regardless of fragility.
from types import SimpleNamespace  # noqa: E402
import lib.macro_regime as mr  # noqa: E402

_macro = SimpleNamespace(
    data_coverage=1.0,
    vix=SimpleNamespace(value=15.0, fear_greed=70.0),
    rates=SimpleNamespace(spread_10y_2y=0.8),
    credit=SimpleNamespace(hy_spread=3.0),
    dollar=SimpleNamespace(change_1m=-3.0),
    etf_returns=SimpleNamespace(returns_1m={"SPY": 2.0, "IWM": 1.5}),
)
_regime_before = mr.classify_regime(_macro)
# Compute a HIGH fragility reading alongside; it must not touch the regime object.
_frag_high = mi.compute_fragility(distribution_days_spy=8, good_news_sold=3,
                                  prior_level="high", recent_raw_levels=["high", "high"])
_regime_after = mr.classify_regime(_macro)
check("8.1 regime object byte-identical with fragility high",
      _regime_before == _regime_after)
check("8.2 fragility never emits a regime label",
      not hasattr(_frag_high, "regime"))

# 8b — only SHORT is gated at high; elevated gates nothing.
check("8.3 high gates SHORT only", mi.gated_horizons("high") == ("short",))
check("8.4 elevated gates nothing", mi.gated_horizons("elevated") == ())
check("8.5 normal gates nothing", mi.gated_horizons("normal") == ())

# 8c — derive_status: SHORT in_zone Actionable degrades under the gate; MID/LONG
#      and all non-in_zone statuses are unchanged (no gate relaxed).
_lv_inzone = SimpleNamespace(entry_status="in_zone", risk_overlay_passed=True,
                             valuation_confidence="medium", missing_conditions=[])
_cand = {"ticker": "T", "candidate_type": "FUNNEL", "eps_revision_direction": "improving"}
_short_ungated = orr.derive_status(_lv_inzone, _cand, [], "short")
_short_gated = orr.derive_status(_lv_inzone, _cand, [], "short",
                                 fragility_gate_horizons=("short",))
_mid_gated = orr.derive_status(_lv_inzone, _cand, [], "mid",
                               fragility_gate_horizons=("short",))
check("8.6 short in_zone is Actionable when ungated",
      _short_ungated == orr.STATUS_ACTIONABLE)
check("8.7 short in_zone degrades under gate (tighten)",
      _short_gated != orr.STATUS_ACTIONABLE and _short_gated == orr.STATUS_RESEARCH)
check("8.8 MID not gated even when short is in the gate set",
      _mid_gated == orr.STATUS_ACTIONABLE)
# The gate can only tighten: a non-actionable status is never improved by it.
_lv_avoid = SimpleNamespace(entry_status="above_zone", risk_overlay_passed=False,
                            valuation_confidence="low", missing_conditions=[])
check("8.9 gate never relaxes an Avoid",
      orr.derive_status(_lv_avoid, _cand, [], "short",
                        fragility_gate_horizons=("short",)) == orr.STATUS_AVOID)


# ===========================================================================
# 9. Snapshot fields complete
# ===========================================================================
_reading = mi.compute_fragility(
    distribution_days_spy=5, distribution_days_qqq=4,
    breadth_above_sma20=0.38, breadth_above_sma20_prev=0.55,
    breadth_above_sma50=0.40, good_news_sold=2, earnings_evaluated=6,
    leading_theme_breadth_narrowing=True, leading_theme_volume_shrinking=True,
    weak_bounce=True, offense_defense={"direction": "defense", "magnitude": "moderate"},
    prior_level="high", recent_raw_levels=["high", "high"])
_snap = mi.fragility_snapshot(_reading, "2026-06-05")
_required = {
    "fragility_level", "fragility_raw_level", "fragility_points",
    "fragility_triggered", "fragility_consecutive_raw", "fragility_degraded",
    "distribution_days_spy", "distribution_days_qqq", "breadth_above_sma20",
    "breadth_above_sma50", "breadth_above_sma20_prev", "breadth_slope",
    "leading_theme_breadth_narrowing", "leading_theme_volume_shrinking",
    "good_news_sold", "earnings_evaluated", "weak_bounce",
    "offense_defense_direction", "offense_defense_magnitude",
}
check("9.1 snapshot has every required field",
      _required.issubset(set(_snap.keys())),
      str(_required - set(_snap.keys())))
check("9.2 breadth_slope auto-derived (0.38-0.55)", _snap["breadth_slope"] == -0.17)
check("9.3 triggered list non-empty for a high reading", len(_snap["fragility_triggered"]) > 0)
check("9.4 history_from_snapshots reconstructs prior level + raw list + dates",
      mi.history_from_snapshots(
          [{"date": "2026-06-03", "fragility_level": "elevated", "fragility_raw_level": "elevated"},
           {"date": "2026-06-04", "fragility_level": "high", "fragility_raw_level": "high"}],
          before_date="2026-06-05")
      == ("high", ["high", "elevated"], ["2026-06-04", "2026-06-03"]))

# Card-level: theme_stage + per-horizon why_now land on the snapshot record.
_card = orr.OpportunityCard(ticker="ZZ", theme="ai_chips",
                            theme_stage="rotating_in", theme_stage_confirmed=True)
_rec = orr._card_snapshot_record(_card, "2026-06-05", "risk_on")
check("9.5 card snapshot carries theme_stage",
      _rec.get("theme_stage") == "rotating_in" and _rec.get("theme_stage_confirmed") is True)


# ===========================================================================
# 10. Structural — no network / LLM on computation paths
# ===========================================================================
import inspect  # noqa: E402

for _mod, _name in ((mi, "market_internals"), (rsm, "relative_strength")):
    _src = inspect.getsource(_mod)
    check(f"10.x {_name} has no requests/urllib import",
          "import requests" not in _src and "import urllib" not in _src)
    check(f"10.x {_name} references no LLM client",
          "anthropic" not in _src.lower() and "openai" not in _src.lower())

# market_internals must not IMPORT or CALL the frozen regime classifier (prose
# mentions in the docstring/comments are fine — the contract is no code dependency).
_mi_src = inspect.getsource(mi)
check("10.3 market_internals does not import/call macro_regime",
      "from lib.macro_regime" not in _mi_src
      and "import macro_regime" not in _mi_src
      and "classify_regime(" not in _mi_src)


# ===========================================================================
# 11. RS date-aligned excess returns (Codex fix 2)
# ===========================================================================
import pandas as pd  # noqa: E402

# Business-day index; SPY clean, ticker MISSING three interior sessions (halt).
_dates = pd.bdate_range("2026-01-01", periods=40)
_spy_close = pd.Series([100.0 + 0.10 * i for i in range(40)], index=_dates)
# Ticker rises faster; drop sessions INCLUDING one inside the last-6 window so a
# positional slice misaligns the benchmark base date vs the aligned one.
_drop = {_dates[20], _dates[25], _dates[37]}
_tk_idx = [d for d in _dates if d not in _drop]
_tk_close = pd.Series([100.0 + 0.50 * i for i, d in enumerate(_dates) if d not in _drop],
                      index=_tk_idx)

def _frame(series):
    return pd.DataFrame({"Close": series, "Volume": [1_000_000] * len(series)})

_bench_closes = {"SPY": _spy_close, "QQQ": _spy_close}
_pos_bench = rsm._returns_from_frames(_bench_closes)
_rs_aligned = rsm.compute_relative_strength(
    "HALT", _frame(_tk_close), _pos_bench, bench_closes=_bench_closes)

# Independent hand-computed ALIGNED 5D excess (inner-join on dates, iloc math).
_common = _tk_close.index.intersection(_spy_close.index)
_ta = _tk_close.reindex(_common).sort_index()
_ba = _spy_close.reindex(_common).sort_index()
_exp_aligned = round((_ta.iloc[-1] / _ta.iloc[-6] - 1) - (_ba.iloc[-1] / _ba.iloc[-6] - 1), 4)
# What the OLD positional-slice would have produced (different effective dates).
_tl, _bl = list(_tk_close), list(_spy_close)
_pos_val = round((_tl[-1] / _tl[-6] - 1) - (_bl[-1] / _bl[-6] - 1), 4)

check("11.1 aligned 5D excess equals the hand-computed aligned value",
      _rs_aligned.ret_5d_vs_spy == _exp_aligned,
      f"got {_rs_aligned.ret_5d_vs_spy} exp {_exp_aligned}")
check("11.2 aligned value differs from the positional-slice value (gap matters)",
      _exp_aligned != _pos_val, f"aligned {_exp_aligned} == pos {_pos_val}")
# Sufficiency runs on the ALIGNED length: 37 aligned bars → 12M (252) not computable.
check("11.3 aligned 12M not computable on short series", _rs_aligned.ret_12m is None)
# No bench_closes / no date index → positional path unchanged (7A byte-compat).
_rs_positional = rsm.compute_relative_strength("HALT", _df(_tl), _pos_bench)
check("11.4 no bench_closes → positional path (no alignment)",
      _rs_positional.ret_5d_vs_spy == _pos_val,
      f"got {_rs_positional.ret_5d_vs_spy} exp {_pos_val}")
# QQQ-gapped benchmark likewise aligns independently of SPY.
_qqq_gap = _spy_close.drop(index=[_dates[5], _dates[10]])
_rs_qg = rsm.compute_relative_strength(
    "HALT", _frame(_tk_close), _pos_bench,
    bench_closes={"SPY": _spy_close, "QQQ": _qqq_gap})
_cq = _tk_close.index.intersection(_qqq_gap.index)
_tq = _tk_close.reindex(_cq).sort_index(); _bq = _qqq_gap.reindex(_cq).sort_index()
_exp_qqq = round((_tq.iloc[-1] / _tq.iloc[-6] - 1) - (_bq.iloc[-1] / _bq.iloc[-6] - 1), 4)
check("11.5 QQQ excess aligns on its own common dates",
      _rs_qg.ret_5d_vs_qqq == _exp_qqq, f"got {_rs_qg.ret_5d_vs_qqq} exp {_exp_qqq}")


# ===========================================================================
# 12. Post-7B polish round (items 1, 2, 4)
# ===========================================================================
from types import SimpleNamespace as _NS  # noqa: E402

# --- Item 1: same-date adjacency ---
_cal12 = ["2026-06-05", "2026-06-08", "2026-06-09", "2026-06-10"]
check("12.1 is_adjacent_session(d, d) is False (same-session duplicate)",
      mi.is_adjacent_session("2026-06-08", "2026-06-08", _cal12) is False)
# A duplicate same-date prior record must NOT extend the chain → no escalation.
_dup, _ = mi.apply_hysteresis(
    "high", "normal", ["high"], recent_dates=["2026-06-08"],
    today_date="2026-06-08", benchmark_index=_cal12)
check("12.2 duplicate same-date record does not escalate", _dup == "normal", _dup)


def _vol_frame(close, vol):
    return _df([close] * len(vol), vol)


# --- Item 2: leading-theme volume shrink ---
# 40 sessions: high baseline volume, then a low recent 10d window → ratio ≪ 0.85.
_shrink_vol = [1_000_000.0] * 30 + [100_000.0] * 10
_steady_vol = [1_000_000.0] * 40
_shrink_consts = [f"S{i}" for i in range(6)]
_theme_shrink = _NS(theme_key="ai_chips", constituents=_shrink_consts,
                    stage="leading", momentum_score=0.9)
_flag, _deg, _detail = mi.leading_theme_volume_shrink(
    [_theme_shrink], lambda tk: _vol_frame(100.0, _shrink_vol))
check("12.3 shrink fixture fires the volume flag (not degraded)",
      _flag is True and _deg is False, f"{_flag}/{_deg}/{_detail}")
# Steady volume → ratio ~1.0 → no shrink.
_flag2, _deg2, _ = mi.leading_theme_volume_shrink(
    [_theme_shrink], lambda tk: _vol_frame(100.0, _steady_vol))
check("12.4 steady volume does not fire the flag", _flag2 is False and _deg2 is False)
# Insufficient data (too few constituents with usable history) → stays degraded.
_theme_thin = _NS(theme_key="ai_chips", constituents=["A", "B"],
                  stage="leading", momentum_score=0.9)
_flag3, _deg3, _ = mi.leading_theme_volume_shrink(
    [_theme_thin], lambda tk: _vol_frame(100.0, _shrink_vol))
check("12.5 insufficient-data fixture stays degraded (flag False)",
      _flag3 is False and _deg3 is True)
# Flag contributes points ONLY when not degraded: via the orchestrator a degraded
# volume read leaves the component False (no points) and lists it in degraded.
_orch = mi.compute_market_fragility(
    themes=[_theme_thin], frame_loader=lambda tk: _vol_frame(100.0, _shrink_vol))
check("12.6 orchestrator: degraded volume → component False + listed",
      _orch.components.leading_theme_volume_shrinking is False
      and "leading_theme_volume" in _orch.degraded)
# When the flag IS set, _score_components counts it (+1).
_pts_with = mi.compute_fragility(leading_theme_volume_shrinking=True)
check("12.7 set flag contributes a triggered point",
      "leading_theme_volume_shrinking" in _pts_with.triggered)

# --- Item 4: WSL clock-drift defense ---
_clkcal = ["2026-06-05", "2026-06-08", "2026-06-09", "2026-06-12"]  # latest 06-12
check("12.8 clock normal (within bound) → not suspect",
      mi.detect_clock_drift("2026-06-12", _clkcal)[0] is False)
check("12.9 clock EARLIER than latest trading date → suspect",
      mi.detect_clock_drift("2026-06-01", _clkcal)[0] is True)
check("12.10 clock far AHEAD (> bound) → suspect",
      mi.detect_clock_drift("2026-06-30", _clkcal)[0] is True)
check("12.11 clock slightly ahead (within bound) → not suspect",
      mi.detect_clock_drift("2026-06-15", _clkcal)[0] is False)
check("12.12 clock check with no index → not suspect (never blocks)",
      mi.detect_clock_drift("2026-06-12", [])[0] is False)
# write_daily_snapshot persists clock_suspect into the _meta header.
import json as _json  # noqa: E402
import tempfile as _tf  # noqa: E402
from pathlib import Path as _P  # noqa: E402
_tmp = _P(_tf.mkdtemp())
orr.write_daily_snapshot([], macro_regime="risk_on", clock_suspect=True,
                         clock_suspect_reason="test drift", date_str="2026-06-05",
                         base_dir=_tmp)
_meta_line = _json.loads(open(_tmp / "opportunities_20260605.jsonl",
                              encoding="utf-8").readline())
check("12.13 snapshot _meta carries clock_suspect + reason",
      _meta_line.get("clock_suspect") is True
      and _meta_line.get("clock_suspect_reason") == "test drift")


# ===========================================================================
# 13. Polish round 2 (Cockpit display/integration bugs)
# ===========================================================================
from datetime import date as _date  # noqa: E402

# --- Item 2: why_now RS line strictly follows the SELECTED horizon ---
# Structural invariant: build_reason_codes' window selection derives ONLY from the
# horizon argument — the macro lens / active_window must never feed it.
_brc_src = inspect.getsource(orr.build_reason_codes)
check("13.1 build_reason_codes selects its RS window from the horizon arg only",
      "RS_LINE_WINDOW" in _brc_src and "horizon" in _brc_src
      and "active_window" not in _brc_src and "lens" not in _brc_src.lower())

# Integration: a SHORT-dominant card whose LONG entry levels are None must still
# get a 6M (not 5D) why_now line for the long horizon (the bug was the
# `if lv is None: continue` skipping per-horizon population → fallback to dominant).
def _plf_no_long(ticker, _p=None, *, thesis_status="intact", horizon="mid",
                 eps_revision_direction="unknown", valuation_percentile=0.5,
                 app_fair_value=None):
    if horizon == "long":
        return None  # engine produced no LONG levels (e.g., no valuation anchor)
    return SimpleNamespace(
        entry_status="in_zone", risk_overlay_passed=True,
        valuation_confidence="medium", missing_conditions=[],
        entry_zone_low=90.0, entry_zone_high=100.0, stop_loss=85.0,
        target_price=120.0, risk_reward_ratio=2.0, position_size_pct=0.05)

_lt_cand = {"ticker": "LONGT", "short_score": 0.8, "mid_score": 0.5,
            "long_score": 0.6, "signal_strength": "single",
            "candidate_type": "FUNNEL", "catalyst_recency": "none",
            "eps_revision_direction": "unknown", "valuation_percentile": 0.5,
            "entry_quality_label": "fair"}
_lt_rs = {"LONGT": rsm.RelativeStrength(
    "LONGT", ret_5d_vs_qqq=0.022, ret_1m_vs_qqq=0.03, ret_6m_vs_qqq=0.05,
    rs_composite=0.7, data_source="live")}
_lt_cards = orr.rank_opportunities(
    [_lt_cand], rs_map=_lt_rs, themes=None, price_levels_fn=_plf_no_long,
    earnings_map={}, top_n=5, today=_date(2026, 6, 5))
_lt = _lt_cards[0]
_long_txt = " ".join(r.text_en for r in _lt.why_now_by_horizon.get("long", []))
_short_txt = " ".join(r.text_en for r in _lt.why_now_by_horizon.get("short", []))
check("13.2 LONG view why_now populated even when LONG levels are None",
      "long" in _lt.why_now_by_horizon)
check("13.3 LONG why_now shows 6M (not 5D) RS line",
      "6M" in _long_txt and "5D" not in _long_txt, _long_txt)
check("13.4 SHORT why_now shows 5D RS line", "5D" in _short_txt, _short_txt)

# --- Item 1: fragility internals line renders after refresh (incl. level=normal) ---
try:
    import streamlit as _st2  # noqa: E402
    _st2.page_link = lambda *a, **k: None
    from streamlit.testing.v1 import AppTest as _AT  # noqa: E402
    _seed = {
        "macro_regime_result": {"regime": "transition", "confidence": "low",
                                "horizon_bias": {"short": "cautious"},
                                "key_signals": [], "opportunity_posture": "",
                                "data_coverage": 1.0, "signals": []},
        "cockpit_fragility": {"level": "normal", "distribution_days_spy": 2,
                              "distribution_days_qqq": 1,
                              "breadth_above_sma20": 0.55, "good_news_sold": 0},
    }
    _atc = _AT.from_file(os.path.join(_REPO_ROOT, "pages/7_Investment_Cockpit.py"),
                         default_timeout=60)
    for _k, _v in _seed.items():
        _atc.session_state[_k] = _v
    _atc.run()
    _blob = " ".join(str(getattr(_m, "value", "")) for _m in _atc.markdown)
    check("13.5 internals line renders after refresh at level=normal",
          ("Internals" in _blob and "normal" in _blob), _blob[:160])
    check("13.6 seeded Cockpit render raised no exception",
          not _atc.exception, str(list(_atc.exception)))
except Exception as _e:  # noqa: BLE001 — AppTest unavailable counts as a failure
    check("13.5 internals render-smoke ran", False, f"AppTest unavailable: {_e}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n".join(_failures))
print(f"\nPhase 7B — Rotation & Internals: {PASS}/{PASS + FAIL} passed")
sys.exit(1 if FAIL else 0)
