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
        "cockpit_fragility": {"fragility_level": "normal", "distribution_days_spy": 2,
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


# ===========================================================================
# 14. Polish round 3 (banner zero/null, earnings wiring, volume theme selection)
# ===========================================================================

# --- Item 3: volume monitor watches current+recent leaders (leading ∪ rotating_out) ---
_t_ai = _NS(theme_key="ai_chips", stage="rotating_out", momentum_score=0.9, constituents=[])
_t_new = _NS(theme_key="new", stage="rotating_in", momentum_score=0.95, constituents=[])
_t_hbm = _NS(theme_key="hbm", stage="leading", momentum_score=0.8, constituents=[])
_sel = [th.theme_key for th in mi._select_leading_themes([_t_ai, _t_new, _t_hbm], 3)]
check("14.1 rotating_out (just-distributing ex-leader) is now monitored",
      "ai_chips" in _sel)
check("14.2 leading is monitored, rotating_in (new entrant) is excluded",
      "hbm" in _sel and "new" not in _sel)
check("14.3 leading_theme_count default is 3", mi.INTERNALS_CONFIG["leading_theme_count"] == 3)

# --- Item 2: earnings reactions wired with distinct degrade reasons ---
_eidx = pd.bdate_range(end="2026-06-05", periods=40)
_ec = [100.0] * 39 + [97.0]                 # report on _eidx[-2], next session -3%
_eframe = pd.DataFrame({"Close": _ec, "Volume": [1e6] * 40}, index=_eidx)
_rdate = str(_eidx[-2].date())

def _eloader(tk):
    return _eframe

_reac, _reason = mi.build_earnings_reactions(
    ["AVGO"], _eloader,
    lambda: [{"ticker": "AVGO", "report_date": _rdate, "direction": "beat"}],
    "2026-06-05")
check("14.4 a beat sold next session is built as a reaction (evaluated)",
      len(_reac) == 1 and _reac[0]["next_session_return"] < 0 and _reason == "")
check("14.5 degrade reason: no calendar source", mi.build_earnings_reactions(
      ["AVGO"], _eloader, None, "2026-06-05")[1] == "earnings_source_absent")

def _boom():
    raise RuntimeError("finnhub down")

check("14.6 degrade reason: source failed → finnhub_unavailable",
      mi.build_earnings_reactions(["AVGO"], _eloader, _boom, "2026-06-05")[1]
      == "finnhub_unavailable")
check("14.7 degrade reason: call OK but empty → no_reports_in_window",
      mi.build_earnings_reactions(["AVGO"], _eloader, lambda: [], "2026-06-05")[1]
      == "no_reports_in_window")
# A report OUTSIDE the lookback window is not evaluated.
_old_rdate = str(_eidx[0].date())
check("14.8 report outside the session window is not evaluated",
      mi.build_earnings_reactions(
          ["AVGO"], _eloader,
          lambda: [{"ticker": "AVGO", "report_date": _old_rdate, "direction": "beat"}],
          "2026-06-05")[1] == "no_reports_in_window")
# compute_market_fragility now actually evaluates the report (good_news_sold counted).
_efrag = mi.compute_market_fragility(
    universe=["AVGO"], frame_loader=_eloader,
    earnings_calendar_fn=lambda: [{"ticker": "AVGO", "report_date": _rdate,
                                   "direction": "beat"}],
    today_str="2026-06-05")
check("14.9 orchestrator counts the good-news-sold report (earnings wired)",
      _efrag.components.good_news_sold == 1 and _efrag.components.earnings_evaluated == 1
      and _efrag.earnings_degrade_reason == "")
# When the source is absent the reason is surfaced in degraded + the reading.
_efrag2 = mi.compute_market_fragility(universe=["AVGO"], frame_loader=_eloader,
                                      today_str="2026-06-05")
check("14.10 absent earnings source → reason recorded in reading + degraded",
      _efrag2.earnings_degrade_reason == "earnings_source_absent"
      and "earnings_source_absent" in _efrag2.degraded)
# Snapshot persists the degrade reason.
check("14.11 snapshot carries earnings_degrade_reason",
      mi.fragility_snapshot(_efrag2, "2026-06-05").get("earnings_degrade_reason")
      == "earnings_source_absent")

# --- Item 1: banner three-state (0 renders, None → n/a, never omitted) ---
try:
    import streamlit as _st3  # noqa: E402
    _st3.page_link = lambda *a, **k: None
    from streamlit.testing.v1 import AppTest as _AT3  # noqa: E402

    def _render_frag(frag):
        _seed = {
            "macro_regime_result": {"regime": "transition", "confidence": "low",
                                    "horizon_bias": {}, "key_signals": [],
                                    "opportunity_posture": "", "data_coverage": 1.0,
                                    "signals": []},
            "cockpit_fragility": frag,
        }
        _a = _AT3.from_file(os.path.join(_REPO_ROOT, "pages/7_Investment_Cockpit.py"),
                            default_timeout=60)
        for _k, _v in _seed.items():
            _a.session_state[_k] = _v
        _a.run()
        return " ".join(str(getattr(_m, "value", "")) for _m in _a.markdown)

    _blob0 = _render_frag({"fragility_level": "normal", "distribution_days_spy": 3,
                           "breadth_above_sma20": 0.55, "good_news_sold": 0})
    check("14.12 good_news_sold=0 renders as '0' (not suppressed)",
          "good-news-sold: 0" in _blob0, _blob0[:200])
    _blobN = _render_frag({"fragility_level": "normal", "distribution_days_spy": None,
                           "breadth_above_sma20": None, "good_news_sold": None})
    check("14.13 None components render the n/a marker, never omitted",
          "good-news-sold: n/a" in _blobN and "distribution days n/a" in _blobN,
          _blobN[:200])
except Exception as _e:  # noqa: BLE001
    check("14.12 banner three-state render-smoke ran", False, f"AppTest: {_e}")


# ===========================================================================
# 15. Rolling raw-reading series (Task A — the SIGNAL trail)
# ===========================================================================
_ridx = pd.bdate_range(end="2026-06-05", periods=60)


def _spy_with_distribution():
    _c = [100.0]
    _v = [1e6]
    for _i in range(1, 60):
        _c.append(_c[-1] * 1.001)
        _v.append(1e6)
    for _k in (40, 44, 48, 52, 56, 58):  # 6 distribution days near the end
        _c[_k] = _c[_k - 1] * 0.99
        _v[_k] = _v[_k - 1] * 1.5
    return pd.DataFrame({"Close": _c, "Volume": _v}, index=_ridx)


_spy = _spy_with_distribution()
_uni_frames = {f"U{n}": pd.DataFrame(
    {"Close": [100.0 * (0.999 ** i) for i in range(60)], "Volume": [1e6] * 60},
    index=_ridx) for n in range(8)}


def _bench_ld(tk):
    return _spy


def _frame_ld(tk):
    return _uni_frames.get(tk)


# 15.1 — as-of-day component correctness vs an independent direct computation.
_arrays = {tk: mi._dated_arrays(df) for tk, df in _uni_frames.items()}
_asof = str(_ridx[40].date())
_asof_breadth = mi._breadth_above_sma_asof(_arrays, 20, _asof)
_direct_breadth = mi.breadth_above_sma(
    {tk: df.loc[:_asof] for tk, df in _uni_frames.items()}, 20)
check("15.1 as-of breadth matches a direct truncated computation",
      _asof_breadth == _direct_breadth, f"{_asof_breadth} vs {_direct_breadth}")

_r_roll = mi.compute_market_fragility(
    universe=list(_uni_frames), frame_loader=_frame_ld, benchmark_loader=_bench_ld,
    today_str="2026-06-05")
# 15.2 — breadth slope is no longer null on a fresh run (computed from the series).
check("15.2 breadth_slope is non-null with sufficient cache",
      _r_roll.components.breadth_slope is not None)
# 15.3 — hysteresis consumes the rolling series; held 2 sessions → escalates TODAY.
check("15.3 rolling series populated + source=rolling",
      len(_r_roll.rolling_raw_series) >= 2 and _r_roll.hysteresis_source == "rolling")
check("15.4 condition held → effective escalates immediately (not normal)",
      _r_roll.level in ("elevated", "high"), _r_roll.level)

# 15.5 — a one-day spike in the rolling series still never escalates.
_spike_eff, _ = mi._replay_hysteresis(["normal"] * 6 + ["high"], mi.INTERNALS_CONFIG)
check("15.5 one-day spike in the rolling series never escalates",
      _spike_eff == "normal", _spike_eff)
# ...but two consecutive elevated recomputed sessions do.
_hold_eff, _ = mi._replay_hysteresis(["normal"] * 4 + ["elevated", "elevated"],
                                     mi.INTERNALS_CONFIG)
check("15.6 two held sessions in the rolling series escalate", _hold_eff == "elevated")

# 15.7 — fallback to the snapshot path when frames are UNDATED (no calendar).
_undated = {f"U{n}": _df([100.0] * 60) for n in range(4)}  # RangeIndex (no dates)
_r_fb = mi.compute_market_fragility(
    universe=list(_undated), frame_loader=lambda tk: _undated.get(tk),
    benchmark_loader=lambda tk: _df([100.0] * 60), today_str="2026-06-05")
check("15.7 undated frames → hysteresis_source falls back to snapshot",
      _r_fb.hysteresis_source == "snapshot")

# 15.8 — audit vs signal: the snapshot _meta still records today's reading AND the
# hysteresis_source (audit trail unchanged in meaning; source is additive).
_snap_roll = mi.fragility_snapshot(_r_roll, "2026-06-05")
check("15.8 snapshot records today's raw + the hysteresis_source field",
      _snap_roll["fragility_raw_level"] == _r_roll.raw_level
      and _snap_roll["hysteresis_source"] == "rolling"
      and _snap_roll["rolling_window"] == mi.INTERNALS_CONFIG["rolling_window_sessions"])

# 15.9 — structural: NO new per-ticker fetches on the refresh path. Every ticker
# the loaders are asked for is in (universe ∪ SPY/QQQ ∪ offense/defense ETFs).
_req: set = set()
import lib.rotation as _rot_mod  # noqa: E402
_sector_etfs = {str(_rot_mod.SECTOR_CONFIG[s]["etf"]).upper()
                for s in list(_rot_mod.OFFENSE_SECTORS) + list(_rot_mod.DEFENSE_SECTORS)
                if _rot_mod.SECTOR_CONFIG.get(s, {}).get("etf")}


def _rec_frame(tk):
    _req.add(str(tk).upper())
    return _uni_frames.get(tk)


def _rec_bench(tk):
    _req.add(str(tk).upper())
    return _spy


mi.compute_market_fragility(universe=list(_uni_frames), frame_loader=_rec_frame,
                            benchmark_loader=_rec_bench, today_str="2026-06-05")
_expected = {tk.upper() for tk in _uni_frames} | {"SPY", "QQQ"} | _sector_etfs
check("15.9 no surprise per-ticker fetches (requests ⊆ expected universe)",
      _req <= _expected, f"unexpected={_req - _expected}")


# ===========================================================================
# 16. Rolling internals FIX round (banner field drift + data-vintage split)
# ===========================================================================
_fx_fresh = pd.bdate_range(end="2026-06-05", periods=60)
_fx_stale = pd.bdate_range(end="2026-05-15", periods=60)


def _mkf(idx):
    return pd.DataFrame({"Close": [100.0 + i * 0.1 for i in range(60)],
                         "Volume": [1e6] * 60}, index=idx)


_spy_fresh = _mkf(_fx_fresh)
_uni_stale = {f"U{n}": _mkf(_fx_stale) for n in range(6)}
_uni_fresh = {f"U{n}": _mkf(_fx_fresh) for n in range(6)}

# 16.1 — Item 2: vintage MISMATCH (fresh bench vs stale universe) → degrade + flag.
_r_mm = mi.compute_market_fragility(
    universe=list(_uni_stale), frame_loader=lambda tk: _uni_stale.get(tk),
    benchmark_loader=lambda tk: _spy_fresh, today_str="2026-06-05")
check("16.1 vintage mismatch → flagged + degraded to snapshot",
      _r_mm.vintage_mismatch is True and _r_mm.hysteresis_source == "snapshot")
check("16.2 data_vintage is the COMMON (older) date on mismatch",
      _r_mm.data_vintage == "2026-05-15", _r_mm.data_vintage)
# 16.3 — clock_suspect fires when the common vintage is >7d behind system date.
check("16.3 clock_suspect on the common vintage (>7d behind)",
      mi.detect_clock_drift("2026-06-05", [_r_mm.data_vintage])[0] is True)

# 16.4 — MATCHED vintage uses the rolling series.
_r_ok = mi.compute_market_fragility(
    universe=list(_uni_fresh), frame_loader=lambda tk: _uni_fresh.get(tk),
    benchmark_loader=lambda tk: _spy_fresh, today_str="2026-06-05")
check("16.4 matched vintage → rolling, no mismatch",
      _r_ok.vintage_mismatch is False and _r_ok.hysteresis_source == "rolling")
check("16.5 rolling series carries per-day points (3-tuples)",
      len(_r_ok.rolling_raw_series[-1]) == 3
      and isinstance(_r_ok.rolling_raw_series[-1][2], int))

# 16.6 — Item 1: the canonical session object is the FLAT snapshot — level AND
# components are top-level (to_dict() nests components → the banner-n/a bug).
_high = mi.compute_fragility(distribution_days_spy=8, good_news_sold=3,
                             prior_level="high", recent_raw_levels=["high", "high"])
_flat = mi.fragility_snapshot(_high, "2026-06-05")
_nested = _high.to_dict()
check("16.7 flat snapshot has level + components at the SAME (top) level",
      "fragility_level" in _flat and "distribution_days_spy" in _flat
      and "good_news_sold" in _flat)
check("16.8 to_dict() nests components (the field-drift the banner hit)",
      "distribution_days_spy" not in _nested
      and "distribution_days_spy" in _nested.get("components", {}))

# 16.9 — Item 1 render: a non-normal level shows its triggered components' NUMBERS
# (level + components from one object → cannot disagree).
try:
    import streamlit as _st4  # noqa: E402
    _st4.page_link = lambda *a, **k: None
    from streamlit.testing.v1 import AppTest as _AT4  # noqa: E402
    _a4 = _AT4.from_file(os.path.join(_REPO_ROOT, "pages/7_Investment_Cockpit.py"),
                         default_timeout=60)
    _a4.session_state["macro_regime_result"] = {
        "regime": "transition", "confidence": "low", "horizon_bias": {},
        "key_signals": [], "opportunity_posture": "", "data_coverage": 1.0,
        "signals": []}
    _a4.session_state["cockpit_fragility"] = _flat  # the flat snapshot
    _a4.run()
    _b4 = " ".join(str(getattr(_m, "value", "")) for _m in _a4.markdown)
    check("16.10 non-normal banner shows level AND non-null component numbers",
          "high" in _b4 and "distribution days 8/25" in _b4
          and "good-news-sold: 3" in _b4, _b4[:240])
except Exception as _e:  # noqa: BLE001
    check("16.10 banner one-source render-smoke ran", False, f"AppTest: {_e}")

# 16.11 — Item 4: Macro Dashboard Market-Internals block renders the component table.
try:
    import streamlit as _st5  # noqa: E402
    _st5.page_link = lambda *a, **k: None
    from streamlit.testing.v1 import AppTest as _AT5  # noqa: E402
    _a5 = _AT5.from_file(os.path.join(_REPO_ROOT, "pages/8_Macro_Dashboard.py"),
                         default_timeout=60)
    _a5.session_state["cockpit_fragility"] = _flat
    _a5.session_state["cockpit_fragility_series"] = [
        ("2026-06-03", "elevated", 2), ("2026-06-04", "high", 4),
        ("2026-06-05", "high", 4)]
    _a5.run()
    _b5 = (" ".join(str(getattr(_m, "value", "")) for _m in _a5.markdown)
           + " " + " ".join(str(getattr(_s, "value", "")) for _s in _a5.subheader))
    check("16.11 Macro Dashboard internals block renders (header + level/source)",
          ("Market Internals" in _b5 or "市场内部结构" in _b5)
          and ("rolling" in _b5 or "snapshot" in _b5 or "high" in _b5),
          _b5[-200:])
    check("16.12 Macro Dashboard render raised no exception",
          not _a5.exception, str(list(_a5.exception)))
except Exception as _e:  # noqa: BLE001
    check("16.11 Macro Dashboard render-smoke ran", False, f"AppTest: {_e}")


# ===========================================================================
# 17. Data-vintage round 2 (RS stale guard + earnings universe filter)
# ===========================================================================
import lib.cache_manager as _cm  # noqa: E402

# --- Item 1: RS data vintage stamp + rs_stale guard ---
_v_fresh = pd.bdate_range(end="2026-06-05", periods=300)
_v_stale = pd.bdate_range(end="2026-05-15", periods=300)


def _vframe(idx):
    return pd.DataFrame({"Close": [100.0 + i * 0.05 for i in range(300)],
                         "Volume": [1e6] * 300}, index=idx)


def _bench_2arg(tk, p=None):
    return _vframe(_v_fresh)

# 17.1 — compute_relative_strength stamps data_vintage from the frame's last date.
_bench_map = rsm.benchmark_returns(_bench_2arg)
_rs_one = rsm.compute_relative_strength("FRZ", _vframe(_v_fresh), _bench_map)
check("17.1 RS stamps data_vintage from the frame", _rs_one.data_vintage == "2026-06-05",
      _rs_one.data_vintage)
check("17.2 benchmark_vintage reads the bench frames' last date",
      rsm.benchmark_vintage(rsm.benchmark_frames(_bench_2arg)) == "2026-06-05")

# 17.3 — a STALE cached frame (lags the benchmark vintage) → rs_stale True (silent
# stale becomes visible; distinct from a cache-miss rs_degraded).
_m_stale = rsm.build_rs_map_cache_only(
    ["ZZZ"], ohlcv_fn=_bench_2arg, frame_loader=lambda tk: _vframe(_v_stale))
check("17.3 stale cached frame → rs_stale True (data_source still live)",
      _m_stale["ZZZ"].rs_stale is True and _m_stale["ZZZ"].data_source == "live")
# 17.4 — matched vintage → not stale (happy path: RS inputs' last date == bench).
_m_ok = rsm.build_rs_map_cache_only(
    ["ZZZ"], ohlcv_fn=_bench_2arg, frame_loader=lambda tk: _vframe(_v_fresh))
check("17.4 matched RS vintage → rs_stale False (happy path)",
      _m_ok["ZZZ"].rs_stale is False and _m_ok["ZZZ"].data_vintage == "2026-06-05")

# 17.5 — write-through: persisting fresh frames makes the cache-only loader serve
# the SAME vintage (memory hit), so RS no longer reads a stale on-disk file.
_n_wt = rsm.persist_frames_to_cache(["WTKR7B"], lambda tk, p=None: _vframe(_v_fresh))
check("17.5 write-through persists + cache-only load then serves the fresh frame",
      _n_wt == 1 and _cm.load("WTKR7B", "ohlcv") is not None
      and rsm._frame_last_date(_cm.load("WTKR7B", "ohlcv")) == "2026-06-05")

# 17.6 — 7A network-free contract intact: the RS loader performs ZERO per-ticker
# fetches (cache-only); a recording ohlcv_fn is asked only for the benchmarks.
_fetched: list = []


def _rec_ohlcv(tk, p=None):
    _fetched.append(str(tk).upper())
    return _vframe(_v_fresh)

rsm.build_rs_map_cache_only(["AAA", "BBB"], ohlcv_fn=_rec_ohlcv,
                            frame_loader=lambda tk: _vframe(_v_fresh))
check("17.6 RS loader fetches benchmarks ONLY (no per-ticker fetch)",
      set(_fetched) <= {"SPY", "QQQ"}, f"unexpected fetched={set(_fetched) - {'SPY','QQQ'}}")

# 17.7 — rs_stale surfaces on the opportunity card + snapshot.
_stale_rs = {"STK": rsm.RelativeStrength("STK", rs_composite=0.6, data_source="live",
                                         data_vintage="2026-05-15", rs_stale=True)}
_stk_cards = orr.rank_opportunities(
    [{"ticker": "STK", "short_score": 0.6, "mid_score": 0.5, "long_score": 0.5,
      "signal_strength": "single", "candidate_type": "FUNNEL"}],
    rs_map=_stale_rs, themes=None, top_n=0, today=_date(2026, 6, 5))
check("17.7 rs_stale lands on the card + snapshot record",
      _stk_cards[0].rs_stale is True
      and orr._card_snapshot_record(_stk_cards[0], "2026-06-05", "x")["rs_stale"] is True)

# --- Item 2: earnings universe filter + implausibility guard ---
_bd17 = mi._dated_arrays(_vframe(_v_fresh))[0]
_reports17 = [{"ticker": "U0", "report_date": str(_bd17[-2]), "direction": "beat"},
              {"ticker": "OUTSIDER", "report_date": str(_bd17[-2]), "direction": "beat"}]
_recs_uni = mi._reaction_records(_reports17, lambda tk: _vframe(_v_fresh), _bd17,
                                 "2026-06-05", mi.INTERNALS_CONFIG, universe=["U0"])
check("17.8 _reaction_records filters to the universe (drops OUTSIDER)",
      [r["ticker"] for r in _recs_uni] == ["U0"])

# 17.9 — implausibility guard: more evaluated than the universe size → degrade with
# reason implausible_count (the backstop for the 39/92 market-wide leak).
_frag_imp = mi.compute_market_fragility(
    universe=["A", "B", "C"], frame_loader=lambda tk: _vframe(_v_fresh),
    benchmark_loader=_bench_2arg,
    earnings_reactions=[{"direction": "beat", "next_session_return": -0.02}
                        for _ in range(5)],  # 5 evaluated > universe 3
    today_str="2026-06-05")
check("17.9 evaluated > universe size → implausible_count degrade (not reported)",
      _frag_imp.components.earnings_evaluated == 0
      and _frag_imp.components.good_news_sold is None
      and "implausible_count" in _frag_imp.degraded)
# 17.10 — a plausible count (≤ universe) is reported normally.
_frag_ok = mi.compute_market_fragility(
    universe=["A", "B", "C", "D", "E"], frame_loader=lambda tk: _vframe(_v_fresh),
    benchmark_loader=_bench_2arg,
    earnings_reactions=[{"direction": "beat", "next_session_return": -0.02},
                        {"direction": "beat", "next_session_return": 0.03}],
    today_str="2026-06-05")
check("17.10 plausible count (≤ universe) is reported",
      _frag_ok.components.earnings_evaluated == 2
      and _frag_ok.components.good_news_sold == 1)

# 17.11 — corrected today's earnings count is bounded by the universe (regression
# guard for the 39/92 market-wide leak): reaction records never exceed universe.
check("17.11 universe-filtered reactions are bounded by the universe size",
      len(_recs_uni) <= 1)


# ===========================================================================
# 17b. Bulk earnings-calendar retry-once-with-backoff (rate-limit defense).
# ===========================================================================
import lib.signal_engine as _se_rt  # noqa: E402
_orig_get = _se_rt._finnhub_get
_orig_key = _se_rt.FINNHUB_API_KEY
_orig_backoff = _se_rt._FINNHUB_BULK_RETRY_BACKOFF_S
try:
    _se_rt.FINNHUB_API_KEY = "dummy"          # bypass the no-key guard
    _se_rt._FINNHUB_BULK_RETRY_BACKOFF_S = 0  # no real sleep in tests
    # (a) a transient 429 (None on attempt 1) then a valid payload → succeeds.
    _calls = {"n": 0}

    def _flaky(url, params):
        _calls["n"] += 1
        if _calls["n"] == 1:
            return None  # first attempt rate-limited
        return {"earningsCalendar": [{"symbol": "AVGO", "date": "2026-06-02",
                                      "epsActual": 1.0, "epsEstimate": 1.2}]}

    _se_rt._finnhub_get = _flaky
    _out = _se_rt.fetch_earnings_reactions_calendar("2026-05-20", "2026-06-05")
    check("17b.1 transient rate-limit → retried once → returns the second payload",
          _calls["n"] == 2 and len(_out) == 1 and _out[0]["ticker"] == "AVGO")
    # (b) both attempts fail → still raises (fully degradable → finnhub_unavailable).
    _calls["n"] = 0
    _se_rt._finnhub_get = lambda url, params: (_calls.__setitem__("n", _calls["n"] + 1)
                                               or None)
    _raised = False
    try:
        _se_rt.fetch_earnings_reactions_calendar("2026-05-20", "2026-06-05")
    except RuntimeError:
        _raised = True
    check("17b.2 both attempts fail → raises after exactly one retry (2 calls)",
          _raised and _calls["n"] == 2)
finally:
    _se_rt._finnhub_get = _orig_get
    _se_rt.FINNHUB_API_KEY = _orig_key
    _se_rt._FINNHUB_BULK_RETRY_BACKOFF_S = _orig_backoff


# ===========================================================================
# 17c. Earnings rescope to the SCAN universe with a cache-only loader (round 4).
# ===========================================================================
_idxc = pd.bdate_range(end="2026-06-05", periods=40)
_rdc = str(_idxc[-3].date())  # report 2 sessions before the last bday


def _frame_c(sold=False):
    closes = [100.0] * 40
    if sold:
        closes[-2] = 96.0   # beat sold next session (-4%)
    return pd.DataFrame({"Close": closes, "Volume": [1e6] * 40}, index=_idxc)


def _bench_loader_c(tk):
    return _frame_c(False)          # SPY/QQQ + top-N breadth names


def _earn_loader_c(tk):
    """Cache-ONLY earnings loader: SCANX is cache-resident (and sold), NOFRAME is a
    cache miss (returns None → skipped, never fetched)."""
    tk = str(tk).upper().strip()
    if tk == "SCANX":
        return _frame_c(True)
    if tk in ("SPY", "QQQ"):
        return _frame_c(False)
    return None

# (a) a report-ticker in the SCAN universe but NOT the breadth top-N is evaluated.
_fc = mi.compute_market_fragility(
    universe=["TOPA", "TOPB"], frame_loader=_bench_loader_c,
    benchmark_loader=_bench_loader_c,
    earnings_universe=["TOPA", "TOPB", "SCANX"], earnings_frame_loader=_earn_loader_c,
    earnings_calendar_fn=lambda: [{"ticker": "SCANX", "report_date": _rdc,
                                   "direction": "beat"}],
    today_str="2026-06-05")
check("17c.1 earnings_universe scopes good-news-sold to the scan set (non-top-N evaluated)",
      _fc.components.earnings_evaluated == 1 and _fc.components.good_news_sold == 1
      and _fc.components.earnings_skipped == 0 and _fc.earnings_degrade_reason == "")

# (b) a scan-universe report whose frame is NOT cache-resident → skipped + partial.
_fp = mi.compute_market_fragility(
    universe=["TOPA", "TOPB"], frame_loader=_bench_loader_c,
    benchmark_loader=_bench_loader_c,
    earnings_universe=["TOPA", "TOPB", "NOFRAME"], earnings_frame_loader=_earn_loader_c,
    earnings_calendar_fn=lambda: [{"ticker": "NOFRAME", "report_date": _rdc,
                                   "direction": "beat"}],
    today_str="2026-06-05")
check("17c.2 frameless in-window report → skipped + partial_frame_coverage (distinct)",
      _fp.components.good_news_sold is None and _fp.components.earnings_skipped >= 1
      and _fp.earnings_degrade_reason == "partial_frame_coverage"
      and "partial_frame_coverage" in _fp.degraded)

# (c) no scan-universe reports in window → no_reports_in_window (NOT partial).
_fn = mi.compute_market_fragility(
    universe=["TOPA", "TOPB"], frame_loader=_bench_loader_c,
    benchmark_loader=_bench_loader_c,
    earnings_universe=["TOPA", "TOPB", "SCANX"], earnings_frame_loader=_earn_loader_c,
    earnings_calendar_fn=lambda: [], today_str="2026-06-05")
check("17c.3 empty calendar over scan universe → no_reports_in_window (skipped=0)",
      _fn.components.good_news_sold is None and _fn.components.earnings_skipped == 0
      and _fn.earnings_degrade_reason == "no_reports_in_window")

# (d) the implausibility bound now checks against the SCAN universe size.
_fi = mi.compute_market_fragility(
    universe=["X"], earnings_universe=["A", "B", "C"],
    frame_loader=lambda tk: _frame_c(False), benchmark_loader=_bench_loader_c,
    earnings_reactions=[{"direction": "beat", "next_session_return": -0.02}
                        for _ in range(5)],  # 5 evaluated > scan universe 3
    today_str="2026-06-05")
check("17c.4 implausible_count bounds against the SCAN universe size",
      _fi.components.earnings_evaluated == 0 and _fi.components.good_news_sold is None
      and "implausible_count" in _fi.degraded)

# (e) backward-compat: no earnings_universe → breadth universe + loader, no skips.
_fb4 = mi.compute_market_fragility(
    universe=["SCANX"], frame_loader=_earn_loader_c, benchmark_loader=_bench_loader_c,
    earnings_calendar_fn=lambda: [{"ticker": "SCANX", "report_date": _rdc,
                                   "direction": "beat"}],
    today_str="2026-06-05")
check("17c.5 backward-compat: earnings falls back to the breadth universe + loader",
      _fb4.components.earnings_evaluated == 1 and _fb4.components.good_news_sold == 1
      and _fb4.components.earnings_skipped == 0 and _fb4.earnings_degrade_reason == "")

# (f) the published scan universe is the exact object the generator used.
import lib.candidate_generator as _cg4  # noqa: E402
try:
    import streamlit as _st_cg
    _st_cg.session_state.clear()
    _cg4._publish_scan_universe(["aapl", " MU ", "", "nvda"])
    _pub = _st_cg.session_state.get("cockpit_scan_universe")
    check("17c.6 _publish_scan_universe normalizes + drops blanks",
          _pub == ["AAPL", "MU", "NVDA"], str(_pub))
except Exception as _e:  # noqa: BLE001
    check("17c.6 _publish_scan_universe ran", False, str(_e))


# ===========================================================================
# 18. Banner ↔ _meta PARITY — drive the REAL Cockpit refresh end to end.
# ===========================================================================
# Root cause of the recurring report/UI mismatches: verification reconstructed the
# fragility computation INLINE instead of driving the real refresh path, so
# call-site differences (loader choice, universe arg, field nesting) only surfaced
# on the next live refresh. This test drives the ACTUAL `_run_refresh` (the same
# function the refresh button triggers) under AppTest with the network leaves
# mocked, then asserts the banner the page RENDERS equals the `_meta` that same
# refresh WROTE — one source, end to end. The three historical mismatches (nested
# components, vintage split, dead earnings arg) each render a banner that disagrees
# with `_meta`, so each would fail this parity check.
import contextlib as _ctx  # noqa: E402
from datetime import datetime as _dt2, timedelta as _td2  # noqa: E402
from unittest import mock as _mock  # noqa: E402

# en tokens come from the SAME translation table the page renders with, so the
# expected-banner tokens never drift from production strings.
import ui_utils as _uiu  # noqa: E402
_EN = _uiu.TRANSLATIONS["en"]


# Scan-universe scope (round 4): good-news-sold runs over the SCAN universe the
# candidate generator published this refresh — NOT the ranked top-N. The earnings
# loader is CACHE-ONLY (cache_manager.load); a scan ticker NOT in the top-N but WITH
# a cached frame must be evaluated, and a scan ticker WITHOUT a cached frame must be
# skipped+counted (partial_frame_coverage). This is exactly the call-site class of
# bug the parity test exists to catch, so §18 drives it end to end.
_TOPN = ("TOPA", "TOPB")                 # ranked candidates (breadth universe)
_SCAN = ("TOPA", "TOPB", "SCANX", "NOFRAME")  # full scan universe
_CACHE_RESIDENT = {"TOPA", "TOPB", "SPY", "QQQ", "SCANX"}  # NOFRAME absent on purpose


def _parity_idx():
    return pd.bdate_range(end=_dt2.now(), periods=60)


def _report_date():
    return str(_parity_idx()[-3].date())  # report 2 sessions before the last bday


def _parity_frame(sold=False):
    idx = _parity_idx()
    closes = [100.0 + i * 0.1 for i in range(len(idx))]
    if sold:  # beat printed at idx[-3]; next session (idx[-2]) sells off → sold
        closes[-2] = closes[-3] * 0.96
        closes[-1] = closes[-2] * 1.001
    vols = [1e6 + (i % 5) * 1e5 for i in range(len(idx))]
    return pd.DataFrame({"Close": closes, "Volume": vols}, index=idx)


def _breadth_loader(tk):
    """ui_utils.load_ohlcv stand-in: serves the top-N breadth names + benchmarks."""
    return _parity_frame(sold=False)


def _cache_loader(tk, *a, **k):
    """cache_manager.load stand-in (the cache-ONLY earnings loader): returns a frame
    only for cache-resident tickers (SCANX carries the beat-sold reaction); a miss
    returns None so the report is skipped, never fetched."""
    tk = str(tk).upper().strip()
    if tk not in _CACHE_RESIDENT:
        return None
    return _parity_frame(sold=(tk == "SCANX"))


def _parity_patches(snap_dir, earnings_cal_fn):
    """ExitStack of patches over the refresh's network leaves only — the REAL
    compute_market_fragility / fragility_snapshot / write_daily_snapshot run. The
    mocked generate_candidates PUBLISHES the scan universe via the real
    _publish_scan_universe, so the generator→session_state→call-site wiring is
    exercised, not bypassed."""
    def _boom(*a, **k):
        raise RuntimeError("offline")

    import lib.candidate_generator as _cg
    import lib.theme_baskets as _tbm
    import lib.macro_data as _md
    import lib.relative_strength as _rsmod
    import lib.anchor_cache as _ac
    import lib.opportunity_ranker as _orr
    import lib.signal_engine as _se
    import lib.cache_manager as _cm2

    def _fake_generate(*a, **k):
        _cg._publish_scan_universe(list(_SCAN))   # real publish → cockpit_scan_universe
        return [SimpleNamespace(ticker=tk) for tk in _TOPN]

    stack = _ctx.ExitStack()
    stack.enter_context(_mock.patch.object(_cg, "generate_candidates", _fake_generate))
    stack.enter_context(_mock.patch.object(_tbm, "compute_all_themes",
                                           lambda *a, **k: []))
    stack.enter_context(_mock.patch.object(_md, "fetch_all_macro", _boom))
    stack.enter_context(_mock.patch.object(_md, "fetch_economic_releases", _boom))
    stack.enter_context(_mock.patch.object(_rsmod, "build_rs_map_cache_only",
                                           lambda *a, **k: {}))
    stack.enter_context(_mock.patch.object(_rsmod, "persist_frames_to_cache",
                                           lambda *a, **k: None))
    stack.enter_context(_mock.patch.object(_ac, "load_all", lambda *a, **k: {}))
    # rank → [] keeps card construction out of scope; _meta still carries the
    # fragility header via write_daily_snapshot(fragility=cockpit_fragility).
    stack.enter_context(_mock.patch.object(_orr, "rank_opportunities",
                                           lambda *a, **k: []))
    stack.enter_context(_mock.patch.object(_orr, "SNAPSHOT_DIR", snap_dir))
    stack.enter_context(_mock.patch.object(_uiu, "load_ohlcv",
                                           lambda tk, *a, **k: _breadth_loader(tk)))
    stack.enter_context(_mock.patch.object(_cm2, "load", _cache_loader))
    stack.enter_context(_mock.patch.object(_se, "fetch_earnings_reactions_calendar",
                                           earnings_cal_fn))
    return stack


_NA = _EN["cockpit_frag_na"]
# Earnings degrade reasons (the vocabulary that renders in the Macro degrade column).
_EARN_REASONS = {"no_reports_in_window", "finnhub_unavailable", "partial_frame_coverage",
                 "earnings_source_absent", "implausible_count"}
# Canonical fragility_snapshot key set — derived from the CODE, so a field added to
# the snapshot automatically appears here and MUST be classified below.
_SNAP_KEYS = set(mi.fragility_snapshot(mi.FragilityReading(), "2000-01-01").keys())
# Macro table row → trigger codes (mirrors pages/8 _render_market_internals rows).
_TABLE_TRIGGERS = [
    ("distribution_days_elevated", "distribution_days_high"),    # SPY
    ("distribution_days_elevated", "distribution_days_high"),    # QQQ
    ("breadth_weak",),                                           # >SMA20
    (),                                                          # >SMA50
    ("breadth_narrowing",),                                      # slope
    ("weak_bounce",),                                            # weak_bounce
    ("good_news_sold_elevated", "good_news_sold_high"),          # good-news-sold
    ("leading_theme_volume_shrinking",),                         # vol
    ("offense_defense_defensive", "offense_defense_defensive_strong"),  # offense/defense
]


def _lvl_token(level):
    """The level as it renders INSIDE the badge span (`>normal</span>`), not a bare
    substring. Item 2b added a one-line explainer caption near the banner AND on the
    Macro block that names all three levels ("normal = … elevated = … high = …"), so a
    bare-word level check would match the explainer text and (a) pass vacuously and
    (b) break the diverged-level negative control. Pinning the badge-wrapped form keeps
    the assertion on the actual badge surface — and EN badge text is the raw level word
    (Item 2 is ZH-only), so this is unchanged for the rendered EN production string."""
    return f">{level}</span>"


def _dd_banner(m):
    dd = max([x for x in (m.get("distribution_days_spy"), m.get("distribution_days_qqq"))
              if x is not None], default=None)
    return f"{dd}/25" if dd is not None else _NA


def _breadth_banner(m):
    b, p = m.get("breadth_above_sma20"), m.get("breadth_above_sma20_prev")
    if b is None:
        return _NA
    if p is not None:
        return f"{int(p*100)}%→{int(b*100)}%"
    return f"{int(b*100)}%"


def _gns_banner(m):
    g, r = m.get("good_news_sold"), str(m.get("earnings_degrade_reason") or "")
    lbl = _EN["cockpit_frag_gns"]
    if g is not None:
        return f"{lbl}: {g}" + (f" ({r})" if r else "")
    return f"{lbl}: " + (f"{_NA} ({r})" if r else _NA)


def _macro_cell(v):
    """Mirror pages/8 _row value formatting (0 renders as 0; float → 2dp; None → n/a)."""
    return _NA if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))


def _od_cell(m):
    return (f"{m.get('offense_defense_direction', '') or '—'} "
            f"{m.get('offense_defense_magnitude', '') or ''}").strip()


# field -> fn(meta) -> [(mode, token)] the UI MUST surface. mode ∈
# {"banner" (substring of cockpit blob), "macro" (substring of macro blob),
#  "cell" (EXACT cell of the macro internals table)}. fragility_triggered is
# checked separately (✅-marker count parity). Every key here is a _meta field with
# a rendered surface; the structural check asserts FIELD_RENDER ∪ EXCLUSIONS == all
# snapshot fields, so a new snapshot field with no surface decision fails loudly.
FIELD_RENDER = {
    "fragility_level": lambda m: [("banner", _lvl_token(str(m["fragility_level"]))),
                                  ("macro", _lvl_token(str(m["fragility_level"])))],
    "distribution_days_spy": lambda m: [("banner", _dd_banner(m)),
                                        ("cell", _macro_cell(m.get("distribution_days_spy")))],
    "distribution_days_qqq": lambda m: [("cell", _macro_cell(m.get("distribution_days_qqq")))],
    "breadth_above_sma20": lambda m: [("banner", _breadth_banner(m)),
                                      ("cell", _macro_cell(m.get("breadth_above_sma20")))],
    "breadth_above_sma20_prev": lambda m: [("banner", _breadth_banner(m))],
    "breadth_above_sma50": lambda m: [("cell", _macro_cell(m.get("breadth_above_sma50")))],
    "breadth_slope": lambda m: [("cell", _macro_cell(m.get("breadth_slope")))],
    "weak_bounce": lambda m: [("cell", _macro_cell(m.get("weak_bounce")))],
    "good_news_sold": lambda m: [("banner", _gns_banner(m)),
                                 ("cell", _macro_cell(m.get("good_news_sold")))],
    "earnings_degrade_reason": lambda m: (
        [("banner", _gns_banner(m))]
        + ([("macro", str(m["earnings_degrade_reason"]))] if m.get("earnings_degrade_reason") else [])),
    "earnings_skipped": lambda m: (
        [("macro", f"skipped={m['earnings_skipped']}")]
        if (m.get("earnings_skipped") and m.get("earnings_degrade_reason")) else []),
    "leading_theme_volume_shrinking": lambda m: [
        ("cell", _macro_cell(m.get("leading_theme_volume_shrinking")))],
    "offense_defense_direction": lambda m: [("cell", _od_cell(m))],
    "offense_defense_magnitude": lambda m: [("cell", _od_cell(m))],
    "hysteresis_source": lambda m: [("macro", str(m.get("hysteresis_source") or "—"))],
    "data_vintage": lambda m: [("macro", str(m.get("data_vintage") or "—"))],
    "vintage_mismatch": lambda m: (
        [("macro", _EN["mi_vintage_mismatch"])] if m.get("vintage_mismatch") else []),
    # The degraded LIST surfaces its earnings reasons in the Macro degrade column
    # (component degrades surface as n/a values, asserted via their own fields).
    "fragility_degraded": lambda m: [("macro", r) for r in (m.get("fragility_degraded") or [])
                                     if r in _EARN_REASONS],
    # ✅ markers in the Macro table — checked via _triggered_parity, not a token.
    "fragility_triggered": lambda m: [],
}

# Fields that intentionally have NO UI surface (each with a one-line justification).
# The structural check forces a future snapshot field to land here or in FIELD_RENDER.
EXCLUSIONS = {
    "date": "snapshot record date (metadata); the trading-date surface is data_vintage",
    "fragility_raw_level": "surfaced only as the Macro trend chart's last marker COLOUR (a plotly figure), no text token",
    "fragility_points": "surfaced only as the Macro trend chart's last point Y (plotly figure), no text token",
    "fragility_consecutive_raw": "internal hysteresis counter; no UI surface by design",
    "fragility_adjacency_degraded": "folded into fragility_degraded as 'hysteresis_adjacency'; no distinct surface",
    "rolling_window": "config echo (window length); the trend renders the series itself, length implicit",
    "leading_theme_breadth_narrowing": "scaffolded component (always False, no history); no table row, folded into degraded",
    "earnings_evaluated": "internal count behind good_news_sold; surfaces render good_news_sold + skipped, not evaluated",
}


def _collect(at):
    """All text-renderable element values on a page (markdown/caption/warning/…) PLUS
    every table/dataframe cell value, joined — the page's full rendered text surface."""
    parts = []
    for attr in ("markdown", "caption", "warning", "info", "error", "success",
                 "header", "subheader", "title", "metric"):
        try:
            for el in getattr(at, attr):
                parts.append(str(getattr(el, "value", "")))
        except Exception:  # noqa: BLE001
            pass
    for attr in ("table", "dataframe"):
        try:
            for el in getattr(at, attr):
                v = getattr(el, "value", None)
                if v is None:
                    continue
                try:
                    parts.append(" ".join(str(c) for c in v.columns))
                    parts.append(" ".join(str(c) for row in v.values.tolist() for c in row))
                except Exception:  # noqa: BLE001
                    parts.append(str(v))
        except Exception:  # noqa: BLE001
            pass
    return " ".join(parts)


def _internals_table(at):
    """The Macro internals component table (the st.table with the mi_triggered col)."""
    try:
        for el in getattr(at, "table", []):
            v = getattr(el, "value", None)
            try:
                cols = list(v.columns)
            except Exception:  # noqa: BLE001
                continue
            if _EN["mi_triggered"] in cols and _EN["mi_component"] in cols:
                return v
    except Exception:  # noqa: BLE001
        pass
    return None


def _internals_cells(df):
    cells = set()
    if df is None:
        return cells
    try:
        cells.update(str(c) for c in df.columns)
        for row in df.values.tolist():
            cells.update(str(c) for c in row)
    except Exception:  # noqa: BLE001
        pass
    return cells


def _expected_tokens(meta):
    """Banner-derived tokens (retained for the banner-only checks 18.4/18.6/18.10)."""
    return [("level", _lvl_token(str(meta.get("fragility_level", "normal")))),
            ("dist", _dd_banner(meta)), ("breadth", _breadth_banner(meta)),
            ("gns", _gns_banner(meta))]


def _parity_holds(blob, meta):
    """True iff EVERY banner token _meta implies is present in the rendered banner."""
    return all(tok in blob for _name, tok in _expected_tokens(meta))


def _missing(meta, R):
    """[(field, mode, token)] for every FIELD_RENDER surface NOT found in R's blobs —
    empty list ⇔ full banner+macro parity against this `meta`."""
    out = []
    for field, fn in FIELD_RENDER.items():
        for mode, token in fn(meta):
            blob = {"banner": R.banner, "macro": R.macro}.get(mode)
            ok = (token in R.cells) if mode == "cell" else (token in blob)
            if not ok:
                out.append((field, mode, token))
    return out


def _triggered_parity(meta, R):
    """(expected_fires, actual_✅) — the Macro table ✅ count vs _meta.fragility_triggered."""
    trig = set(meta.get("fragility_triggered") or [])
    expected = sum(1 for keys in _TABLE_TRIGGERS if set(keys) & trig)
    actual = None
    if R.table is not None and _EN["mi_triggered"] in list(R.table.columns):
        actual = sum(1 for v in R.table[_EN["mi_triggered"]].tolist() if str(v) == "✅")
    return expected, actual


def _run_parity(earnings_cal_fn):
    """Drive the REAL refresh once, then render BOTH pages from that refresh's
    session reading. Returns a namespace with the cockpit banner blob, the Macro
    blob + internals table/cells, the _meta the refresh wrote, and the clock-warning
    flag — all from ONE refresh, so every surface is asserted against ONE _meta."""
    import streamlit as _stp
    _stp.page_link = lambda *a, **k: None
    from streamlit.testing.v1 import AppTest as _ATp
    R = SimpleNamespace(banner="", macro="", cells=set(), table=None, meta={},
                        clock_warn=False, exc="")
    _tmp = _P(_tf.mkdtemp())
    with _parity_patches(_tmp, earnings_cal_fn):
        _a = _ATp.from_file(os.path.join(_REPO_ROOT, "pages/7_Investment_Cockpit.py"),
                            default_timeout=120)
        _a.session_state["language"] = "en"
        # Seed a valid regime so Section A (which hosts the internals banner) renders;
        # the offline macro step fails-closed and PRESERVES this seed (never clears).
        _a.session_state["macro_regime_result"] = {
            "regime": "transition", "confidence": "low",
            "horizon_bias": {"short": "cautious"}, "key_signals": [],
            "opportunity_posture": "", "data_coverage": 1.0, "signals": []}
        _a.run()
        _btn = None
        for _b in _a.button:
            if getattr(_b, "key", "") == "cockpit_refresh_all":
                _btn = _b
                break
        if _btn is None:
            R.exc = "refresh button not found"
            return R
        _btn.click().run()
        R.banner = _collect(_a)
        R.exc = str(list(_a.exception)) if _a.exception else ""
        R.clock_warn = _EN["cockpit_hub_clock_suspect"] in R.banner
        _files = sorted(_tmp.glob("opportunities_*.jsonl"))
        if _files:
            R.meta = _json.loads(_files[-1].read_text(encoding="utf-8").splitlines()[0])
        # Render the Macro Dashboard from the SAME refresh's session reading.
        _cf = dict(_a.session_state["cockpit_fragility"]) \
            if "cockpit_fragility" in _a.session_state else {}
        _cfs = list(_a.session_state["cockpit_fragility_series"]) \
            if "cockpit_fragility_series" in _a.session_state else []
        _m = _ATp.from_file(os.path.join(_REPO_ROOT, "pages/8_Macro_Dashboard.py"),
                            default_timeout=120)
        _m.session_state["language"] = "en"
        _m.session_state["cockpit_fragility"] = _cf
        _m.session_state["cockpit_fragility_series"] = _cfs
        _m.run()
        R.macro = _collect(_m)
        R.table = _internals_table(_m)
        R.cells = _internals_cells(R.table)
    return R


# --- Structural completeness: every snapshot field is classified (loud on a new one).
_unclassified = _SNAP_KEYS - set(FIELD_RENDER) - set(EXCLUSIONS)
_overlap = set(FIELD_RENDER) & set(EXCLUSIONS)
_phantom = (set(FIELD_RENDER) | set(EXCLUSIONS)) - _SNAP_KEYS
check("18.0 every fragility_snapshot field is classified (surface or justified exclusion)",
      not _unclassified and not _overlap and not _phantom,
      f"unclassified={_unclassified} overlap={_overlap} phantom={_phantom}")

try:
    # --- Scenario A: a SCAN-universe ticker NOT in the top-N reports + has a cached
    # frame → it is EVALUATED (the round-4 rescope: market signal over the scan set).
    _lit_cal = lambda *a, **k: [{"ticker": "SCANX",
                                 "report_date": _report_date(),
                                 "direction": "beat"}]  # noqa: E731
    _RA = _run_parity(_lit_cal)
    check("18.1 real refresh wrote a fragility _meta header (lit path)",
          bool(_RA.meta) and "fragility_level" in _RA.meta, _RA.exc[:160])
    check("18.2 refresh raised no exception (lit path)", _RA.exc == "", _RA.exc[:200])
    check("18.3 LIVE: a non-top-N SCAN ticker (SCANX) is evaluated → number in _meta",
          _RA.meta.get("good_news_sold") is not None
          and _RA.meta.get("earnings_evaluated", 0) >= 1
          and "SCANX" not in _TOPN  # proves it came from the scan scope, not top-N
          and _RA.meta.get("earnings_degrade_reason", "") == "",
          f"gns={_RA.meta.get('good_news_sold')} ev={_RA.meta.get('earnings_evaluated')} "
          f"reason={_RA.meta.get('earnings_degrade_reason')}")
    check("18.4 PARITY (lit): every _meta token is rendered on the banner",
          _parity_holds(_RA.banner, _RA.meta),
          str(_expected_tokens(_RA.meta)) + " || " + _RA.banner[:240])
    # FULL cross-page parity: every surfaced _meta field appears on its surface.
    _missA = _missing(_RA.meta, _RA)
    check("18.11 FULL PARITY (lit): every surfaced _meta field renders (banner+macro)",
          _missA == [], f"missing={_missA[:8]}")
    _expF, _actF = _triggered_parity(_RA.meta, _RA)
    check("18.12 triggered ✅-marker parity (Macro table == _meta.fragility_triggered)",
          _actF is not None and _expF == _actF,
          f"expected_fires={_expF} actual_✅={_actF} trig={_RA.meta.get('fragility_triggered')}")
    check("18.13 clock-warning parity (banner ⟺ _meta.clock_suspect)",
          _RA.clock_warn == bool(_RA.meta.get("clock_suspect")),
          f"banner_warn={_RA.clock_warn} meta={_RA.meta.get('clock_suspect')}")
    check("18.14 vintage-mismatch parity (Macro warning ⟺ _meta.vintage_mismatch)",
          (_EN["mi_vintage_mismatch"] in _RA.macro) == bool(_RA.meta.get("vintage_mismatch")),
          f"meta={_RA.meta.get('vintage_mismatch')}")
    # Spot-confirm the new fields actually rendered (not vacuously absent).
    check("18.15 Macro surfaces hysteresis_source + data_vintage from _meta",
          str(_RA.meta.get("hysteresis_source")) in _RA.macro
          and str(_RA.meta.get("data_vintage")) in _RA.macro,
          f"src={_RA.meta.get('hysteresis_source')} vintage={_RA.meta.get('data_vintage')} "
          + _RA.macro[:160])

    # --- Scenario B: earnings DARK (empty calendar) → no_reports_in_window ---
    _dark_cal = lambda *a, **k: []  # call OK, nothing in window → no_reports_in_window
    _RB = _run_parity(_dark_cal)
    check("18.5 LIVE: empty calendar degrades to no_reports_in_window in _meta",
          _RB.meta.get("good_news_sold") is None
          and _RB.meta.get("earnings_degrade_reason") == "no_reports_in_window",
          f"gns={_RB.meta.get('good_news_sold')} reason={_RB.meta.get('earnings_degrade_reason')}")
    check("18.6 PARITY (dark): banner shows 'n/a (no_reports_in_window)' = _meta",
          _parity_holds(_RB.banner, _RB.meta)
          and "good-news-sold: n/a (no_reports_in_window)" in _RB.banner,
          _RB.banner[:240])
    _missB = _missing(_RB.meta, _RB)
    check("18.16 FULL PARITY (dark): degrade reason renders on BOTH banner + Macro table",
          _missB == []
          and "no_reports_in_window" in _RB.macro,  # the Macro degrade column
          f"missing={_missB[:8]}")

    # --- Scenario C: scan ticker reports, frame NOT cache-resident → partial_frame_coverage ---
    _partial_cal = lambda *a, **k: [{"ticker": "NOFRAME",
                                     "report_date": _report_date(),
                                     "direction": "beat"}]  # noqa: E731
    _RC = _run_parity(_partial_cal)
    check("18.9 LIVE: in-window report without a cached frame → partial_frame_coverage",
          _RC.meta.get("good_news_sold") is None
          and _RC.meta.get("earnings_skipped", 0) >= 1
          and _RC.meta.get("earnings_degrade_reason") == "partial_frame_coverage",
          f"gns={_RC.meta.get('good_news_sold')} skipped={_RC.meta.get('earnings_skipped')} "
          f"reason={_RC.meta.get('earnings_degrade_reason')}")
    check("18.10 PARITY (partial): banner shows 'n/a (partial_frame_coverage)' = _meta",
          _parity_holds(_RC.banner, _RC.meta)
          and "good-news-sold: n/a (partial_frame_coverage)" in _RC.banner,
          _RC.banner[:240])
    _missC = _missing(_RC.meta, _RC)
    check("18.17 FULL PARITY (partial): Macro surfaces reason + 'skipped=N' note",
          _missC == [] and "skipped=" in _RC.macro,
          f"missing={_missC[:8]} skipped={_RC.meta.get('earnings_skipped')}")

    # --- Negative divergence controls for the newly covered classes (#3): mutate a
    # _meta field POST-refresh (blobs unchanged) → the full parity MUST now fail. ---
    _badV = {**_RA.meta, "data_vintage": "1999-12-31"}
    check("18.18 parity FAILS on diverged data_vintage",
          any(f == "data_vintage" for f, _mo, _tk in _missing(_badV, _RA)))
    _badH = {**_RA.meta, "hysteresis_source":
             ("snapshot" if _RA.meta.get("hysteresis_source") != "snapshot" else "rolling")}
    check("18.19 parity FAILS on diverged hysteresis_source",
          any(f == "hysteresis_source" for f, _mo, _tk in _missing(_badH, _RA)))
    # Mutate one degraded-list entry (the earnings reason) to a different known reason
    # the Macro surface does NOT show → fragility_degraded parity must fail.
    _deg = list(_RB.meta.get("fragility_degraded") or [])
    _deg = ["finnhub_unavailable" if d == "no_reports_in_window" else d for d in _deg]
    _badD = {**_RB.meta, "fragility_degraded": _deg}
    check("18.20 parity FAILS on a diverged fragility_degraded entry",
          any(f == "fragility_degraded" for f, _mo, _tk in _missing(_badD, _RB)),
          f"degraded={_deg}")

    # --- Existing banner-only divergence controls (retained). ---
    _diverged_level = {**_RB.meta, "fragility_level":
                       ("high" if _RB.meta.get("fragility_level") != "high" else "normal")}
    check("18.7 parity FAILS on a diverged level (level mismatch caught)",
          not _parity_holds(_RB.banner, _diverged_level))
    _diverged_gns = {**_RA.meta, "good_news_sold": (_RA.meta.get("good_news_sold") or 0) + 7}
    check("18.8 parity FAILS on a diverged component value (number mismatch caught)",
          not _parity_holds(_RA.banner, _diverged_gns))
except Exception as _e:  # noqa: BLE001 — AppTest unavailable counts as a failure
    import traceback as _tb_p
    check("18.1 banner↔_meta parity harness ran", False,
          f"{_e} :: {_tb_p.format_exc()[-400:]}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n".join(_failures))
print(f"\nPhase 7B — Rotation & Internals: {PASS}/{PASS + FAIL} passed")
sys.exit(1 if FAIL else 0)
