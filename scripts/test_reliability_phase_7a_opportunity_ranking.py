#!/usr/bin/env python3
"""
scripts/test_reliability_phase_7a_opportunity_ranking.py

Phase 7A — Opportunity Ranking MVP test suite (mock-only / offline).

Runs entirely without real API calls or network. Every external dependency is
injected as a fixture (rs_map, themes, earnings_map, price_levels_fn). Covers the
original MVP plus the fix-round revisions:

  1. Revised five-state mapping incl. horizon-aware below_zone + the two
     invariants (pullback never co-occurs with Avoid Chasing; below_zone never
     yields Wait for Breakout).
  2. Blocker assembly: ticker-specific per-card vs market-wide banner; earnings
     calendar blocker.
  3. Setup classification incl. the bounded post-earnings window (actual dates).
  4. Three weight tables -> different orderings + deterministic tie-break.
  5. Grade bucketing boundaries.
  6. Snapshot write + same-day dedup + reconstruction + atomic-write failure.
  7. RS from fixture price data + cache-only (network-free) mode.
  8. Reason-code informativeness: commonality filter, numeric embedding, no
     overclaiming; display-time concentration refs; no-LLM ranking path.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["FINNHUB_API_KEY"] = ""

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
if os.path.join(_REPO_ROOT, "lib") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "lib"))

from lib import opportunity_ranker as orr
from lib import relative_strength as rsm

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def levels(**kw):
    """Duck-typed PriceLevelResult stand-in."""
    base = dict(
        entry_status="in_zone", risk_overlay_passed=True,
        valuation_confidence="medium", missing_conditions=[], horizon="mid",
        next_trigger="", entry_zone_low=90.0, entry_zone_high=100.0, stop_loss=85.0,
        target_price=120.0, risk_reward_ratio=2.0, position_size_pct=0.05,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def candidate(ticker, **kw):
    base = dict(
        ticker=ticker, short_score=0.5, mid_score=0.5, long_score=0.5,
        signal_strength="single", catalyst_recency="none",
        already_priced_in=False, eps_revision_direction="unknown",
        valuation_percentile=0.5, entry_quality_label="fair",
        candidate_type="FUNNEL", narrative_theme_tags=[],
    )
    base.update(kw)
    return base


def theme_obj(theme_key, momentum, constituents):
    return SimpleNamespace(
        theme_key=theme_key, momentum_score=momentum, constituents=constituents,
        label_en=theme_key.upper(), label_zh=theme_key)


c_funnel = candidate("AAA", candidate_type="FUNNEL")

# ---------------------------------------------------------------------------
# 1. Revised five-state status mapping
# ---------------------------------------------------------------------------

check("1.1 in_zone, gates pass -> Actionable Now",
      orr.derive_status(levels(entry_status="in_zone"), c_funnel, [], "mid")
      == orr.STATUS_ACTIONABLE)

check("1.2 above_zone (no critical) -> Wait for Pullback",
      orr.derive_status(levels(entry_status="above_zone"), c_funnel, [], "mid")
      == orr.STATUS_PULLBACK)

check("1.3 above_zone + critical blocker -> Avoid Chasing",
      orr.derive_status(levels(entry_status="above_zone"), c_funnel,
                        [orr.Blocker("valuation_high", "critical")], "mid")
      == orr.STATUS_AVOID)

# Task 1(a): blocked-with-missing (trend/trigger gate, NOT overextension) must
# NOT be Avoid Chasing — it is a pending trigger.
check("1.4 blocked + trend-gate missing (eps ok) -> Wait for Breakout",
      orr.derive_status(levels(entry_status="blocked",
                               missing_conditions=["price not above EMA20"],
                               next_trigger="Wait for EMA trend + volume"),
                        c_funnel, [], "short")
      == orr.STATUS_BREAKOUT)

check("1.5 blocked + EPS deteriorating -> Avoid Chasing",
      orr.derive_status(levels(entry_status="blocked", missing_conditions=[]),
                        candidate("D", eps_revision_direction="deteriorating"),
                        [], "mid")
      == orr.STATUS_AVOID)

check("1.6 risk overlay failed -> Avoid Chasing",
      orr.derive_status(levels(entry_status="in_zone", risk_overlay_passed=False),
                        c_funnel, [], "mid")
      == orr.STATUS_AVOID)

check("1.7 ALT_SIGNAL only -> Research Required",
      orr.derive_status(levels(entry_status="in_zone"),
                        candidate("B", candidate_type="ALT_SIGNAL"), [], "mid")
      == orr.STATUS_RESEARCH)

check("1.8 long + low valuation confidence -> Research Required",
      orr.derive_status(levels(entry_status="in_zone", valuation_confidence="low"),
                        c_funnel, [], "long")
      == orr.STATUS_RESEARCH)

# Task 1(b): below_zone is horizon-aware Research, never Wait for Breakout.
check("1.9 below_zone SHORT -> Research Required (stabilization)",
      orr.derive_status(levels(entry_status="below_zone"), c_funnel, [], "short")
      == orr.STATUS_RESEARCH)
check("1.10 below_zone MID -> Research Required",
      orr.derive_status(levels(entry_status="below_zone"), c_funnel, [], "mid")
      == orr.STATUS_RESEARCH)
check("1.11 below_zone LONG -> Research Required (below value zone)",
      orr.derive_status(levels(entry_status="below_zone"), c_funnel, [], "long")
      == orr.STATUS_RESEARCH)

check("1.12 in_zone + earnings calendar blocker (short) -> Research Required",
      orr.derive_status(levels(entry_status="in_zone"), c_funnel,
                        [orr.Blocker("earnings_within_window", "caution",
                                     horizons=["short"])], "short")
      == orr.STATUS_RESEARCH)
check("1.13 in_zone + short-only earnings blocker does NOT gate mid horizon",
      orr.derive_status(levels(entry_status="in_zone"), c_funnel,
                        [orr.Blocker("earnings_within_window", "caution",
                                     horizons=["short"])], "mid")
      == orr.STATUS_ACTIONABLE)

# INVARIANT: below_zone never yields Wait for Breakout (any horizon, any candidate)
_below_breakout = False
for _hz in ("short", "mid", "long"):
    for _vc in ("low", "medium", "high"):
        if orr.derive_status(levels(entry_status="below_zone", valuation_confidence=_vc),
                             c_funnel, [], _hz) == orr.STATUS_BREAKOUT:
            _below_breakout = True
check("1.14 INVARIANT below_zone never -> Wait for Breakout", not _below_breakout)

# all five states reachable
_reached = {
    orr.derive_status(levels(entry_status="in_zone"), c_funnel, [], "mid"),          # Actionable
    orr.derive_status(levels(entry_status="above_zone"), c_funnel, [], "mid"),       # Pullback
    orr.derive_status(levels(entry_status="blocked",
                             missing_conditions=["x"]), c_funnel, [], "short"),      # Breakout
    orr.derive_status(levels(entry_status="below_zone"), c_funnel, [], "mid"),       # Research
    orr.derive_status(levels(entry_status="in_zone", risk_overlay_passed=False),
                      c_funnel, [], "mid"),                                          # Avoid
}
check("1.15 all five states reachable", len(_reached) == 5, f"reached={_reached}")

# status_next_trigger surfaces engine text + a horizon-aware reason code
_nt, _rc = orr.status_next_trigger(
    levels(entry_status="blocked", next_trigger="Wait for EMA trend"),
    "short", orr.STATUS_BREAKOUT)
check("1.16 next_trigger surfaced for Wait for Breakout",
      _nt == "Wait for EMA trend" and _rc is not None and _rc.code == "trigger_pending")
_nt2, _rc2 = orr.status_next_trigger(
    levels(entry_status="below_zone"), "long", orr.STATUS_RESEARCH)
check("1.17 LONG below-zone reason is below_value_zone",
      _rc2 is not None and _rc2.code == "below_value_zone")
_nt3, _rc3 = orr.status_next_trigger(
    levels(entry_status="below_zone"), "short", orr.STATUS_RESEARCH)
check("1.18 SHORT below-zone reason is stabilization_needed",
      _rc3 is not None and _rc3.code == "stabilization_needed")

# Fix 3 — engine missing_conditions drive the fundamental gate via the engine's
# OWN registry (no hand-written approximations). Import the registry and pin
# EVERY entry through the full derive_status path.
import ast as _ast
from lib.order_advisor import MISSING_CONDITION_REGISTRY as _REG

_pin_fail = []
for _mc in _REG.values():
    _st = orr.derive_status(
        levels(entry_status="blocked", missing_conditions=[_mc.text]),
        c_funnel, [], "mid")
    _exp = orr.STATUS_AVOID if _mc.category == "fundamental" else orr.STATUS_BREAKOUT
    if _st != _exp:
        _pin_fail.append(f"{_mc.code}:{_mc.category}->{_st}")
check("1.19 every registry condition classifies to its category via derive_status",
      not _pin_fail, str(_pin_fail))
check("1.19b registry has both categories represented",
      {mc.category for mc in _REG.values()} == {"fundamental", "trigger"})

# Completeness guard: NO inline missing-condition string literal may be appended
# to a *missing* list in order_advisor — every condition must come from the
# registry, so a future inline addition fails this suite.
_oa_src = open(os.path.join(_REPO_ROOT, "lib/order_advisor.py"), encoding="utf-8").read()
_inline_appends = []
for _node in _ast.walk(_ast.parse(_oa_src)):
    if (isinstance(_node, _ast.Call) and isinstance(_node.func, _ast.Attribute)
            and _node.func.attr == "append"
            and "missing" in getattr(_node.func.value, "id", "").lower()):
        for _arg in _node.args:
            if isinstance(_arg, _ast.Constant) and isinstance(_arg.value, str):
                _inline_appends.append(_arg.value)
check("1.20 no inline missing-condition literals in order_advisor (registry-only)",
      not _inline_appends, str(_inline_appends))

# Legacy fallback: an UNREGISTERED text-only condition still classifies via
# substrings; fundamental wins on collision.
check("1.21 legacy unregistered fundamental text -> fundamental (substring fallback)",
      orr.engine_block_is_fundamental(["unusual EPS estimate warning (legacy)"]) is True)
check("1.22 legacy unregistered trigger-ish text -> not fundamental",
      orr.engine_block_is_fundamental(["momentum stalling (legacy)"]) is False)
check("1.22b collision: a registered trigger + a registered fundamental -> fundamental wins",
      orr.engine_block_is_fundamental(
          [_REG["price_below_ema20"].text, _REG["eps_deteriorating"].text]) is True)
check("1.22c registered trigger alone -> not fundamental (no false substring hit)",
      orr.engine_block_is_fundamental([_REG["rsi_out_of_band"].text]) is False)

# Row-4 precedence (pinned, intended): price overextension beats provenance.
check("1.23 ALT_SIGNAL + above_zone + critical -> Avoid Chasing (price beats provenance)",
      orr.derive_status(levels(entry_status="above_zone"),
                        candidate("ALT", candidate_type="ALT_SIGNAL"),
                        [orr.Blocker("valuation_high", "critical")], "mid")
      == orr.STATUS_AVOID)
check("1.24 ALT_SIGNAL + above_zone (no critical) -> Wait for Pullback (price beats provenance)",
      orr.derive_status(levels(entry_status="above_zone"),
                        candidate("ALT", candidate_type="ALT_SIGNAL"), [], "mid")
      == orr.STATUS_PULLBACK)

# Per-horizon status (the MU mid-view anomaly): the engine returns a different
# entry_status per horizon, so the card's status_by_horizon must differ.
def _per_horizon_levels(ticker, holding=None, horizon="mid", **kw):
    es = {"short": "blocked", "mid": "in_zone", "long": "below_zone"}[horizon]
    nt = {"short": "Wait for EMA trend + volume", "mid": "",
          "long": "Wait for valuation anchor"}[horizon]
    return levels(entry_status=es, next_trigger=nt, horizon=horizon)

_ph_cand = candidate("MU", short_score=0.4, mid_score=0.8, long_score=0.5)
_ph = orr.rank_opportunities(
    [dict(_ph_cand)], rs_map={"MU": rsm.RelativeStrength("MU", rs_composite=0.5,
     data_source="live")}, earnings_map={}, top_n=1, price_levels_fn=_per_horizon_levels)[0]
check("1.25 per-horizon status map populated for all three horizons",
      set(_ph.status_by_horizon) == {"short", "mid", "long"})
check("1.26 MID view is Actionable while SHORT is Wait for Breakout",
      _ph.status_by_horizon["mid"] == orr.STATUS_ACTIONABLE
      and _ph.status_by_horizon["short"] == orr.STATUS_BREAKOUT)
check("1.27 LONG below-zone view is Research Required (not breakout)",
      _ph.status_by_horizon["long"] == orr.STATUS_RESEARCH)
check("1.28 dominant convenience status == MID (dominant horizon)",
      _ph.status == _ph.status_by_horizon["mid"])
check("1.29 MID next_trigger is NOT the SHORT EMA phrasing",
      "EMA" not in (_ph.next_trigger_by_horizon.get("mid") or ""))


# ---------------------------------------------------------------------------
# 2. Blocker assembly: ticker-specific vs market-wide
# ---------------------------------------------------------------------------

_today = date(2026, 6, 5)

_rb = orr.build_rule_blockers(candidate("Z", valuation_percentile=0.85),
                              theme_momentum=0.2, has_theme=True)
_codes = {b.code for b in _rb}
check("2.1 valuation_high blocker assembled (ticker-specific)", "valuation_high" in _codes)
check("2.2 theme_lagging blocker assembled (ticker-specific)", "theme_lagging" in _codes)
check("2.3 macro_regime_mismatch NOT a per-card blocker", "macro_regime_mismatch" not in _codes)
check("2.4 valuation_high is critical severity",
      any(b.code == "valuation_high" and b.severity == "critical" for b in _rb))
check("2.5 blockers carry bilingual text", all(b.text_en and b.text_zh for b in _rb))

# market-wide banner (Task 3)
_banner = orr.market_banner_blockers("transition", {"short": "cautious"},
                                     days_to_fomc=2, days_to_cpi=10, horizon="short")
_bcodes = {b.code for b in _banner}
check("2.6 banner carries macro_regime_mismatch", "macro_regime_mismatch" in _bcodes)
check("2.7 banner carries fomc within window (2<=3)", "fomc_within_window" in _bcodes)
check("2.8 banner omits cpi outside window (10>3)", "cpi_within_window" not in _bcodes)
check("2.9 banner codes are all market-wide",
      _bcodes.issubset(orr.MARKET_WIDE_BLOCKER_CODES))
_banner_mid = orr.market_banner_blockers("transition", {"mid": "favorable"},
                                         days_to_fomc=2, days_to_cpi=2, horizon="mid")
check("2.10 mid horizon (favorable) -> no macro mismatch, no fomc/cpi",
      _banner_mid == [])

# earnings calendar blocker (per-card, ticker-specific)
_cb = orr.build_calendar_blockers(days_to_earnings=3)
check("2.11 earnings within window injected (3<=7)",
      any(b.code == "earnings_within_window" for b in _cb))
check("2.12 earnings blocker gates short horizon only",
      all(b.horizons == ["short"] for b in _cb))
check("2.13 no earnings blocker outside window",
      orr.build_calendar_blockers(days_to_earnings=30) == [])

# days-to-event math
check("2.14 days_to_event future", orr.days_to_event("2026-06-12", _today) == 7)
check("2.15 days_to_event past -> None", orr.days_to_event("2026-06-01", _today) is None)
check("2.16 days_to_next_fomc nearest upcoming",
      orr.days_to_next_fomc(_today, ["2026-05-01", "2026-06-17"]) == 12)
check("2.17 days_to_next_cpi projects forward",
      orr.days_to_next_cpi("2026-05-13", _today) is not None)


# ---------------------------------------------------------------------------
# 3. Setup classification (config-driven; bounded post-earnings window)
# ---------------------------------------------------------------------------

rs_strong = rsm.RelativeStrength(
    "M", ret_5d=0.02, ret_1m=0.10, ret_1m_vs_spy=0.05, ret_1m_vs_qqq=0.04,
    ret_5d_vs_spy=0.01, above_sma20=True, above_sma50=True, vol_ratio=1.5,
    rs_composite=0.85)

s, _ = orr.classify_setup(
    candidate("M", short_score=0.8, mid_score=0.3, long_score=0.2), rs_strong, 0.4)
check("3.1 Momentum Breakout", s == "Momentum Breakout", s)

# Post-earnings requires an ACTUAL recent report within the bounded window.
s, _ = orr.classify_setup(
    candidate("E", eps_revision_direction="improving", short_score=0.6,
              mid_score=0.5, long_score=0.4),
    rsm.RelativeStrength("E", rs_composite=0.5), 0.3, days_since_earnings=4)
check("3.2 Post-earnings Reprice (reported 4d ago, eps improving)",
      s == "Post-earnings Reprice", s)

# Stale report (35d) must NOT be labelled Post-earnings (the AAPL screenshot bug).
s, _ = orr.classify_setup(
    candidate("AAPL", eps_revision_direction="improving", mid_score=0.7,
              short_score=0.3, long_score=0.3),
    rsm.RelativeStrength("AAPL", above_sma50=True, rs_composite=0.6), 0.6,
    days_since_earnings=35)
check("3.3 stale report (35d) is NOT Post-earnings Reprice", s != "Post-earnings Reprice", s)

# Without earnings timing (Phase 1) Post-earnings is never assigned.
s, _ = orr.classify_setup(
    candidate("X", eps_revision_direction="improving", mid_score=0.7),
    rsm.RelativeStrength("X", above_sma50=True, rs_composite=0.6), 0.6)
check("3.4 no earnings date -> not Post-earnings (no inference)", s != "Post-earnings Reprice", s)

s, _ = orr.classify_setup(
    candidate("R", mid_score=0.7, short_score=0.3, long_score=0.3), rs_strong, 0.7)
check("3.5 Mid-term Rotation", s == "Mid-term Rotation", s)

s, _ = orr.classify_setup(
    candidate("L", long_score=0.7, short_score=0.2, mid_score=0.3, valuation_percentile=0.2),
    rsm.RelativeStrength("L", above_sma50=True, rs_composite=0.55), 0.4)
check("3.6 Long-term Accumulation", s == "Long-term Accumulation", s)

s, _ = orr.classify_setup(
    candidate("SP", candidate_type="ALT_SIGNAL", short_score=0.0, mid_score=0.0, long_score=0.0),
    rsm.RelativeStrength("SP", rs_composite=0.5), 0.0)
check("3.7 Speculative Watch", s == "Speculative Watch", s)

_, pb = orr.classify_setup(
    candidate("PB", mid_score=0.6, entry_quality_label="good"),
    rsm.RelativeStrength("PB", ret_5d=-0.02, ret_1m=0.08, above_sma50=True, rs_composite=0.7), 0.5)
check("3.8 Pullback-to-Support variant flagged", pb is True)

check("3.9 setup thresholds live in the config block",
      "momentum_vol_ratio" in orr.SETUP_THRESHOLDS
      and "post_earnings_window_days" in orr.SETUP_THRESHOLDS)


# ---------------------------------------------------------------------------
# 4. Weight tables -> different orderings + deterministic tie-break
# ---------------------------------------------------------------------------

cands = [
    candidate("A", short_score=0.9, mid_score=0.5, long_score=0.2,
              valuation_percentile=0.9, catalyst_recency="recent"),
    candidate("B", short_score=0.2, mid_score=0.5, long_score=0.9, valuation_percentile=0.1),
    candidate("C", short_score=0.5, mid_score=0.55, long_score=0.5, valuation_percentile=0.5),
]
rs_map = {c["ticker"]: rsm.RelativeStrength(c["ticker"], rs_composite=0.5,
          data_source="live") for c in cands}

order_short = [c.ticker for c in orr.rank_opportunities(
    [dict(c) for c in cands], rs_map=rs_map, top_n=0, sort_horizon="short")]
order_long = [c.ticker for c in orr.rank_opportunities(
    [dict(c) for c in cands], rs_map=rs_map, top_n=0, sort_horizon="long")]
check("4.1 short table orders A first", order_short[0] == "A", str(order_short))
check("4.2 long table orders B first", order_long[0] == "B", str(order_long))
check("4.3 short vs long orderings differ", order_short != order_long)

# tie-break determinism: equal scores -> ticker asc, stable across runs
tied = [candidate(t, short_score=0.5, mid_score=0.5, long_score=0.5) for t in ["ZZZ", "AAA", "MMM"]]
tied_rs = {c["ticker"]: rsm.RelativeStrength(c["ticker"], rs_composite=0.5, data_source="live") for c in tied}
o1 = [c.ticker for c in orr.rank_opportunities([dict(c) for c in tied], rs_map=tied_rs, top_n=0)]
o2 = [c.ticker for c in orr.rank_opportunities([dict(c) for c in reversed(tied)], rs_map=tied_rs, top_n=0)]
check("4.4 tie-break is deterministic (ticker asc) regardless of input order",
      o1 == o2 == ["AAA", "MMM", "ZZZ"], f"{o1} vs {o2}")


# ---------------------------------------------------------------------------
# 5. Grade bucketing boundaries
# ---------------------------------------------------------------------------

check("5.1 0.66 -> A", orr._grade(0.66) == "A")
check("5.2 0.659 -> B", orr._grade(0.659) == "B")
check("5.3 0.40 -> B", orr._grade(0.40) == "B")
check("5.4 0.399 -> C", orr._grade(0.399) == "C")
check("5.5 0.0 -> C", orr._grade(0.0) == "C")
check("5.6 1.0 -> A", orr._grade(1.0) == "A")


# ---------------------------------------------------------------------------
# 6. Snapshot write + same-day dedup + reconstruction + atomic-write failure
# ---------------------------------------------------------------------------

try:
    import pandas as pd
    _HAS_PD = True
except Exception:  # noqa: BLE001
    _HAS_PD = False


def _series_df(closes, volumes=None):
    n = len(closes)
    vols = volumes if volumes is not None else [1_000_000] * n
    if _HAS_PD:
        return pd.DataFrame({"Close": closes, "Volume": vols})
    return {"Close": closes, "Volume": vols}


import json as _json

with tempfile.TemporaryDirectory() as _tmp:
    base = Path(_tmp)
    themes = [theme_obj("ai_chips", 0.82, ["A", "C"]), theme_obj("cloud", 0.2, ["B"])]
    day_cards = orr.rank_opportunities([dict(c) for c in cands], rs_map=rs_map,
                                       themes=themes, top_n=0)

    p1 = orr.write_daily_snapshot(day_cards, themes=themes, macro_regime="risk_on",
                                  horizon_bias={"mid": "favorable"},
                                  date_str="2026-06-05", base_dir=base)
    check("6.1 snapshot file written", bool(p1) and Path(p1).exists())
    _lines = Path(p1).read_text(encoding="utf-8").strip().splitlines()
    _meta = _json.loads(_lines[0])
    _recs = [_json.loads(x) for x in _lines[1:]]
    check("6.2 meta header present", _meta.get("_meta") is True)
    check("6.3 meta per-theme momentum map", _meta.get("theme_momentum", {}).get("ai_chips") == 0.82)
    check("6.4 one record per candidate", len(_recs) == len(cands))
    check("6.5 records carry rs_degraded + raw reason codes + per-horizon status map",
          all("rs_degraded" in r and "why_now" in r and "status_by_horizon" in r
              and "next_trigger_by_horizon" in r for r in _recs))
    check("6.6 concentration_ref NOT stored (view-local)",
          all("concentration_ref" not in r for r in _recs))

    # same-day re-write overwrites (dedup)
    orr.write_daily_snapshot(day_cards, themes=themes, date_str="2026-06-05", base_dir=base)
    _recs2 = [_json.loads(x) for x in
              Path(p1).read_text(encoding="utf-8").strip().splitlines()[1:]]
    check("6.7 same-day re-write dedups", len(_recs2) == len(cands))

    # second day -> per-ticker series reconstruction
    orr.write_daily_snapshot(day_cards, themes=themes, date_str="2026-06-06", base_dir=base)
    series_a = orr.load_ticker_series("A", base_dir=base)
    check("6.8 per-ticker series spans two days", len(series_a) == 2)
    check("6.9 series sorted by date",
          [r["date"] for r in series_a] == ["2026-06-05", "2026-06-06"])

    # atomic-write failure degrades silently and does not corrupt the prior file
    _orig_replace = orr.os.replace
    _before = Path(p1).read_text(encoding="utf-8")
    try:
        orr.os.replace = lambda a, b: (_ for _ in ()).throw(OSError("boom"))
        _res = orr.write_daily_snapshot(day_cards, themes=themes,
                                        date_str="2026-06-05", base_dir=base)
    finally:
        orr.os.replace = _orig_replace
    check("6.10 atomic-write failure returns '' (silent degrade)", _res == "")
    check("6.11 prior snapshot intact after failed write",
          Path(p1).read_text(encoding="utf-8") == _before)
    check("6.12 no .tmp leftover after failed write",
          not list(base.glob("*.tmp*")))


# ---------------------------------------------------------------------------
# 7. RS from fixture price data + cache-only (network-free) mode
# ---------------------------------------------------------------------------

_leader_closes = [100.0 + i * 0.8 for i in range(60)]
_laggard_closes = [100.0 - i * 0.5 for i in range(60)]
_bench_closes = [100.0 + i * 0.2 for i in range(60)]
_bench_fn = lambda tk, period="6mo": _series_df(_bench_closes)
_bench = rsm.benchmark_returns(_bench_fn)

rs_leader = rsm.compute_relative_strength("LEAD", _series_df(_leader_closes), _bench)
rs_laggard = rsm.compute_relative_strength("LAG", _series_df(_laggard_closes), _bench)
check("7.1 leader RS composite > laggard", rs_leader.rs_composite > rs_laggard.rs_composite)
check("7.2 leader beats benchmark 1m", rs_leader.ret_1m_vs_spy and rs_leader.ret_1m_vs_spy > 0)
check("7.3 leader above SMA20+SMA50", rs_leader.above_sma20 and rs_leader.above_sma50)
check("7.4 leader data_source live", rs_leader.data_source == "live")
check("7.5 empty series -> fixture/degraded",
      rsm.compute_relative_strength("E", _series_df([]), _bench).data_source == "fixture")

# cache-only mode: per-ticker reads ONLY from frames; zero per-ticker fetches.
_fetch = {"n": 0}
def _counting_loader(tk, period="6mo"):
    _fetch["n"] += 1
    return _series_df(_bench_closes)
res_co = rsm.compute_rs_for_tickers(
    ["AAA", "BBB"], ohlcv_fn=_counting_loader, cache_only=True, frames={})
check("7.6 cache-only: only benchmark fetches (2), zero per-ticker", _fetch["n"] == 2, str(_fetch["n"]))
check("7.7 cache-only miss -> degraded RS (fixture source)",
      all(r.data_source == "fixture" for r in res_co.values()))
# cache-only with frames provided + benchmarks supplied -> ZERO loader calls
_fetch2 = {"n": 0}
def _counting_loader2(tk, period="6mo"):
    _fetch2["n"] += 1
    return None
res_co2 = rsm.compute_rs_for_tickers(
    ["LEAD"], ohlcv_fn=_counting_loader2, bench_returns=_bench, cache_only=True,
    frames={"LEAD": _series_df(_leader_closes)})
check("7.8 cache-only with frames + bench -> zero loader calls", _fetch2["n"] == 0)
check("7.9 cache-only frame hit -> live RS", res_co2["LEAD"].data_source == "live")

# 7b — INTEGRATION (Fix 2): the Cockpit RS path (build_rs_map_cache_only) must
# perform ZERO per-ticker fetches; misses degrade. Counting bench loader +
# cache-only frame_loader stub with deliberate misses.
_bench_calls = {"tickers": []}
def _bench_loader(tk, period="1y"):
    _bench_calls["tickers"].append(tk)
    return _series_df(_bench_closes)
# only LEAD is "cached"; LAG and GONE are deliberate cache misses
_frame_cache = {"LEAD": _series_df(_leader_closes)}
def _frame_loader(tk):
    return _frame_cache.get(tk)  # cache-only: None on miss, NEVER fetches

_rs_int = rsm.build_rs_map_cache_only(
    ["LEAD", "LAG", "GONE"], ohlcv_fn=_bench_loader, frame_loader=_frame_loader)
check("7b.1 Cockpit RS path fetches ONLY benchmarks (no candidate fetch)",
      set(_bench_calls["tickers"]) == {"SPY", "QQQ"}, str(_bench_calls["tickers"]))
check("7b.2 cached ticker -> live RS", _rs_int["LEAD"].data_source == "live")
check("7b.3 missed tickers degrade (fixture source / neutral)",
      _rs_int["LAG"].data_source == "fixture" and _rs_int["GONE"].data_source == "fixture")
# and rank_opportunities turns a degraded RS into rs_degraded + neutral
_int_rank = orr.rank_opportunities(
    [candidate("LAG", short_score=0.5, mid_score=0.5, long_score=0.5)],
    rs_map=_rs_int, top_n=0)
check("7b.4 degraded RS -> card.rs_degraded + neutral RS contribution",
      _int_rank[0].rs_degraded is True)


# ---------------------------------------------------------------------------
# 8. Reason-code hygiene, structural no-LLM/no-fetch, concentration, invariants
# ---------------------------------------------------------------------------

# 8a — no overclaiming: catalyst code names only what it checks (no "priced in").
_wn, _wm = orr.build_reason_codes(
    candidate("CAT", catalyst_recency="recent"),
    rsm.RelativeStrength("CAT", ret_1m_vs_qqq=0.034, rs_composite=0.7), 0.7)
_all_text = " ".join(r.text_en + r.text_zh for r in _wn + _wm)
check("8.1 no 'priced in' overclaim in reason text",
      "priced in" not in _all_text.lower() and "尚未完全反映" not in _all_text)
check("8.2 catalyst code renamed to recent_catalyst",
      any(r.code == "recent_catalyst" for r in _wn))
check("8.3 RS reason embeds the computed magnitude",
      any("QQQ" in r.text_en and "%" in r.text_en for r in _wn))

# 8b — commonality filter: a code shared by everyone is demoted from display.
common_cands = [candidate(f"T{i}", short_score=0.6, mid_score=0.6, long_score=0.6,
                          signal_strength="triple") for i in range(6)]
# All six share triple_horizon_signal (>50% -> common). Give two of them TWO
# distinctive codes (eps improving + reasonable valuation) so the common code is
# actually dropped from their display (>=2 distinctive remain).
for i in (0, 1):
    common_cands[i]["eps_revision_direction"] = "improving"
    common_cands[i]["valuation_percentile"] = 0.2
common_rs = {c["ticker"]: rsm.RelativeStrength(c["ticker"], rs_composite=0.5,
             data_source="live") for c in common_cands}
ranked_c = orr.rank_opportunities([dict(c) for c in common_cands], rs_map=common_rs, top_n=0)
_t0 = next(c for c in ranked_c if c.ticker == "T0")
_disp_codes_t0 = {r.code for r in _t0.why_matters_display}
check("8.4 over-common code demoted from display when >=2 distinctive remain",
      "triple_horizon_signal" not in _disp_codes_t0 and len(_t0.why_matters_display) >= 2,
      str(_disp_codes_t0))
check("8.5 raw reason codes preserved on the card",
      any(r.code == "triple_horizon_signal" for r in _t0.why_it_matters))

# Fix 4 — trigger_pending is a status reason only; never in the why_now vocab.
def _breakout_levels(ticker, holding=None, horizon="mid", **kw):
    return levels(entry_status="blocked", missing_conditions=["price not above EMA20"],
                  next_trigger="Wait for EMA trend + volume")
_bk_card = orr.rank_opportunities(
    [candidate("BRK", short_score=0.8, mid_score=0.3, long_score=0.2)],
    rs_map={"BRK": rsm.RelativeStrength("BRK", rs_composite=0.5, data_source="live")},
    earnings_map={}, top_n=1, price_levels_fn=_breakout_levels)[0]
check("8.5b Wait-for-Breakout card: dominant status is Breakout",
      _bk_card.status == orr.STATUS_BREAKOUT)
check("8.5c trigger_pending NOT in why_now (Fix 4 — it duplicates the trigger line)",
      all(r.code != "trigger_pending" for r in _bk_card.why_now))
check("8.5d trigger_pending IS the status reason for the dominant horizon",
      (_bk_card.status_reason_by_horizon.get("short") or {}).get("code") == "trigger_pending")

# 8c — structural: entry engine called 3x per top_n (per-horizon); none on scoring.
_engine = {"n": 0, "horizons": set()}
def _counting_levels(ticker, holding=None, horizon="mid", **kw):
    _engine["n"] += 1
    _engine["horizons"].add(horizon)
    return levels(entry_status="in_zone")
big = [candidate(f"B{i}", short_score=0.9 - i * 0.01, mid_score=0.5, long_score=0.4) for i in range(40)]
# rs_map deliberately MISSING half the tickers -> they must degrade, not fetch.
big_rs = {c["ticker"]: rsm.RelativeStrength(c["ticker"], rs_composite=0.5, data_source="live")
          for c in big[:20]}
ranked = orr.rank_opportunities([dict(c) for c in big], rs_map=big_rs, earnings_map={},
                                top_n=20, price_levels_fn=_counting_levels)
check("8.6 entry engine called 3x per top_n (per-horizon)", _engine["n"] == 60, str(_engine["n"]))
check("8.6b entry engine called for all three horizons",
      _engine["horizons"] == {"short", "mid", "long"})
check("8.7 unenriched cards beyond top N have null status",
      ranked[25].status is None and ranked[25].status_by_horizon == {}
      and ranked[25].enriched is False)
check("8.8 all 40 candidates scored", len(ranked) == 40)
_missing = next(c for c in ranked if c.ticker not in big_rs)
check("8.9 missing-RS card flagged rs_degraded", _missing.rs_degraded is True)

# 8d — no LLM on the ranking path (poison the orchestrator).
import types as _types
_poison = _types.ModuleType("lib.llm_orchestrator")
def _boom(*a, **k):
    raise AssertionError("LLM called on the ranking path")
_poison.polish_reason_codes = _boom
sys.modules["lib.llm_orchestrator"] = _poison
try:
    orr.rank_opportunities([dict(c) for c in big], rs_map=big_rs, earnings_map={},
                           top_n=20, price_levels_fn=_counting_levels)
    check("8.10 ranking path makes no LLM call", True)
except AssertionError as e:
    check("8.10 ranking path makes no LLM call", False, str(e))
finally:
    sys.modules.pop("lib.llm_orchestrator", None)

# 8e — INVARIANT: pullback_to_support never co-occurs with Avoid Chasing.
def _avoid_levels(ticker, holding=None, **kw):
    return levels(entry_status="in_zone", risk_overlay_passed=False)  # forces Avoid
pull_cands = [candidate("PUL", mid_score=0.7, entry_quality_label="good",
                        eps_revision_direction="deteriorating")]
pull_rs = {"PUL": rsm.RelativeStrength("PUL", ret_5d=-0.02, ret_1m=0.08,
           above_sma50=True, rs_composite=0.75, data_source="live")}
pr = orr.rank_opportunities([dict(c) for c in pull_cands], rs_map=pull_rs,
                            earnings_map={}, top_n=1, price_levels_fn=_avoid_levels)
check("8.11 INVARIANT pullback flag dropped when status is Avoid Chasing",
      not (pr[0].status == orr.STATUS_AVOID and pr[0].pullback_to_support))

# 8f — display-time concentration: "#K" points to a card visible above.
conc_cards = [{"ticker": "T0", "theme": "ai_chips"},
              {"ticker": "T1", "theme": "cloud"},
              {"ticker": "T2", "theme": "ai_chips"}]
refs = orr.concentration_refs(conc_cards)
check("8.12 first card of a theme has no ref", "T0" not in refs)
check("8.13 later same-theme card refs the first by display position", refs.get("T2") == "#1")
check("8.14 different-theme card has no ref", "T1" not in refs)

# 8g — approved_for_execution invariant
check("8.15 approved_for_execution always False",
      all(c.approved_for_execution is False for c in ranked))


# ---------------------------------------------------------------------------
# 9. Page import + render smoke (permanent guard against import drift)
#
# Imports BOTH Streamlit pages fresh and renders them via AppTest, with NO mocks
# on lib.opportunity_ranker — so the pages' top-level
# ``from lib.opportunity_ranker import ...`` lines execute against the real,
# current module. A missing/renamed export (the line-96 ImportError this hotfix
# addresses) surfaces as at.exception and FAILS the suite. The only harness
# workaround is patching st.page_link, which raises a KeyError under AppTest's
# single-file multipage harness (unrelated to our code).
# ---------------------------------------------------------------------------

# Fix 5 — parse the names each page imports from lib.opportunity_ranker straight
# from the page source (AST), so a renamed export or a NEW page import is caught
# without maintaining a hand-written list.
import ast as _ast


def _ranker_imports(page_rel: str) -> set:
    src = open(os.path.join(_REPO_ROOT, page_rel), encoding="utf-8").read()
    names: set = set()
    for node in _ast.walk(_ast.parse(src)):
        if isinstance(node, _ast.ImportFrom) and node.module == "lib.opportunity_ranker":
            for alias in node.names:
                names.add(alias.name)
    return names


_imported = (_ranker_imports("pages/7_Investment_Cockpit.py")
             | _ranker_imports("pages/9_Trading_Desk.py"))
_missing_exports = sorted(n for n in _imported if not hasattr(orr, n))
check("9.0 every name the two pages import from lib.opportunity_ranker exists",
      not _missing_exports, f"missing={_missing_exports}; parsed={sorted(_imported)}")

try:
    import time as _time
    import streamlit as _st
    _st.page_link = lambda *a, **k: None  # AppTest cannot resolve multipage links
    from streamlit.testing.v1 import AppTest

    def _smoke(rel_path: str, presession: dict):
        path = os.path.join(_REPO_ROOT, rel_path)
        try:
            at = AppTest.from_file(path, default_timeout=60)
            for k, v in (presession or {}).items():
                at.session_state[k] = v
            at.run()
            return at.exception
        except Exception as e:  # noqa: BLE001 — harness error counts as a failure
            return e

    _exc7 = _smoke("pages/7_Investment_Cockpit.py", {})
    check("9.1 pages/7_Investment_Cockpit.py imports + renders (no exception)",
          not _exc7, str(_exc7))

    # Skip the Trading Desk's 4h thesis-monitor refresh (would attempt network);
    # the import that triggered the bug runs at module top regardless.
    _exc9 = _smoke("pages/9_Trading_Desk.py",
                   {"trading_desk_last_refresh": _time.time()})
    check("9.2 pages/9_Trading_Desk.py imports + renders (no exception)",
          not _exc9, str(_exc9))
except Exception as _e:  # noqa: BLE001 — streamlit/AppTest unavailable
    check("9.x page render smoke ran", False, f"AppTest unavailable: {_e}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n".join(_failures))
print(f"\n{PASS}/{PASS + FAIL} passed")
sys.exit(1 if FAIL else 0)
