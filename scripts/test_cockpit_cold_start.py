#!/usr/bin/env python3
"""
scripts/test_cockpit_cold_start.py

Cockpit cold-start hydration test suite (offline, Streamlit-free).

Drives ``lib.cockpit_hydration.hydrate_cockpit_from_snapshot`` directly with a
plain ``dict`` standing in for ``st.session_state`` and INJECTED loaders that
return controlled ``MetaRecord`` / ``OpportunityRecord`` fixtures — no real
``data/snapshots/`` read, no ``AppTest``, no network. Each case goes RED when the
specific behaviour it guards regresses.

Coverage:
  §CS-1  No snapshot on disk → session_state unpopulated, no banner, no error.
  §CS-2  Snapshot exists → macro_regime_result carries regime / key_signals /
         opportunity_posture / confidence / fragility_level from MetaRecord.
  §CS-3  cockpit_opportunities reconstructed from OpportunityRecord.raw for the
         LATEST date only (older dates excluded).
  §CS-4  cockpit_hydrated_from_snapshot set to meta.date.
  §CS-5  Runs at most once per session (a second call never overwrites keys).
  §CS-6  load_meta raising → session_state unchanged, no exception propagates.
  §CS-7  Mutation probe: key_signals must be mapped MetaRecord → macro_regime_result.
  Extra  why_now code-strings are normalised out so Section C cannot crash.

Run:
    python3 scripts/test_cockpit_cold_start.py
    # or: pytest scripts/test_cockpit_cold_start.py -v
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_REPO_ROOT, os.path.join(_REPO_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.audit_query import MetaRecord, OpportunityRecord
from lib.cockpit_hydration import hydrate_cockpit_from_snapshot


# ---------------------------------------------------------------------------
# Fixture builders — real MetaRecord / OpportunityRecord, no files
# ---------------------------------------------------------------------------

def _meta(date: str, *, macro_regime: str = "risk_on",
          fragility_level: str = "elevated",
          key_signals=None, opportunity_posture: str = "selective_add",
          confidence: str = "medium", horizon_bias=None,
          with_fragility: bool = True) -> MetaRecord:
    raw = {
        "_meta": True,
        "date": date,
        "macro_regime": macro_regime,
        "horizon_bias": dict(horizon_bias or {"short": "neutral", "mid": "long"}),
        "n_candidates": 3,
        "key_signals": list(key_signals if key_signals is not None
                            else ["vix_falling", "breadth_expanding"]),
        "opportunity_posture": opportunity_posture,
        "confidence": confidence,
    }
    if with_fragility:
        raw.update({
            "fragility_level": fragility_level,
            "fragility_raw_level": fragility_level,
            "fragility_points": 2,
            "fragility_triggered": True,
            "fragility_consecutive_raw": 1,
            "hysteresis_source": "rolling",
            "distribution_days_spy": 3,
            "distribution_days_qqq": 4,
            "breadth_above_sma20": 0.42,
            "breadth_above_sma20_prev": 0.55,
            "good_news_sold": 1,
            "earnings_evaluated": 5,
            "earnings_degrade_reason": "",
        })
    return MetaRecord.from_dict(raw)


def _opp(date: str, ticker: str, *, why_now=None, **extra) -> OpportunityRecord:
    raw = {
        "date": date,
        "ticker": ticker,
        "theme": "ai_compute",
        "short_score": 0.7,
        "mid_score": 0.6,
        "long_score": 0.5,
        "short_grade": "B",
        "mid_grade": "A",
        "long_grade": "C",
        "setup": "Momentum Breakout",
        "status": "Actionable Now",
        "status_by_horizon": {"short": "Actionable Now", "mid": "Wait for Pullback",
                              "long": "Research Required"},
        "next_trigger_by_horizon": {},
        "blockers": [],
        # Persisted as reason-CODE strings (mirrors _card_snapshot_record).
        "why_now": why_now if why_now is not None else ["rs_breakout_5d", "vol_surge"],
        "days_to_earnings": 7,
        "signal_strength": "double",
        "macro_regime": "risk_on",
    }
    raw.update(extra)
    return OpportunityRecord.from_dict(raw)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_cs1_no_snapshot():
    """§CS-1 — empty meta history → no population, no banner (None), no error."""
    ss: dict = {}
    result = hydrate_cockpit_from_snapshot(
        ss, load_meta=lambda: [], load_opportunities=lambda: [])
    assert result is None, "no snapshot must return None (no banner)"
    assert ss == {}, f"session_state must stay empty, got {sorted(ss)}"


def test_cs2_section_a_fields():
    """§CS-2 — macro_regime_result carries the five MetaRecord macro fields."""
    ss: dict = {}
    meta = _meta("2026-06-20", macro_regime="risk_off",
                 key_signals=["yields_spiking"], opportunity_posture="defensive",
                 confidence="high", fragility_level="high")
    result = hydrate_cockpit_from_snapshot(
        ss, load_meta=lambda: [meta], load_opportunities=lambda: [])
    assert result == "2026-06-20"
    mr = ss["macro_regime_result"]
    assert mr["regime"] == "risk_off"
    assert mr["key_signals"] == ["yields_spiking"]
    assert mr["opportunity_posture"] == "defensive"
    assert mr["confidence"] == "high"
    assert mr["fragility_level"] == "high"
    # Fragility snapshot rebuilt from the _meta header for Section A's internals line.
    frag = ss["cockpit_fragility"]
    assert frag["fragility_level"] == "high"
    assert frag["distribution_days_qqq"] == 4
    assert frag["breadth_above_sma20"] == 0.42
    assert frag["good_news_sold"] == 1


def test_cs3_latest_date_opportunities_only():
    """§CS-3 — cards come from OpportunityRecord.raw for the LATEST date only."""
    ss: dict = {}
    metas = [_meta("2026-06-19"), _meta("2026-06-20")]  # ascending (load_all_meta order)
    opps = [
        _opp("2026-06-19", "OLD1"),
        _opp("2026-06-19", "OLD2"),
        _opp("2026-06-20", "NEW1"),
        _opp("2026-06-20", "NEW2"),
    ]
    result = hydrate_cockpit_from_snapshot(
        ss, load_meta=lambda: metas, load_opportunities=lambda: opps)
    assert result == "2026-06-20"
    tickers = {c["ticker"] for c in ss["cockpit_opportunities"]}
    assert tickers == {"NEW1", "NEW2"}, f"latest date only, got {tickers}"
    # The reconstructed card preserves raw snapshot fields Section C reads.
    new1 = next(c for c in ss["cockpit_opportunities"] if c["ticker"] == "NEW1")
    assert new1["mid_grade"] == "A"
    assert new1["status_by_horizon"]["short"] == "Actionable Now"


def test_cs4_flag_is_meta_date():
    """§CS-4 — cockpit_hydrated_from_snapshot == meta.date (string)."""
    ss: dict = {}
    hydrate_cockpit_from_snapshot(
        ss, load_meta=lambda: [_meta("2026-06-20")],
        load_opportunities=lambda: [_opp("2026-06-20", "AAA")])
    assert ss["cockpit_hydrated_from_snapshot"] == "2026-06-20"
    assert ss["cockpit_last_refresh"] == "2026-06-20"


def test_cs5_runs_at_most_once():
    """§CS-5 — a second call is a no-op and never overwrites later edits."""
    ss: dict = {}
    meta_a = _meta("2026-06-20")
    opps_a = [_opp("2026-06-20", "AAA")]
    first = hydrate_cockpit_from_snapshot(
        ss, load_meta=lambda: [meta_a], load_opportunities=lambda: opps_a)
    assert first == "2026-06-20"
    # Simulate the user (or a later refresh) mutating state after hydration.
    ss["cockpit_opportunities"] = "USER_MODIFIED"
    # A second call (e.g. a Streamlit rerun) must NOT re-run hydration.
    newer_meta = _meta("2026-06-21")
    newer_opps = [_opp("2026-06-21", "ZZZ")]
    second = hydrate_cockpit_from_snapshot(
        ss, load_meta=lambda: [newer_meta], load_opportunities=lambda: newer_opps)
    assert second is None, "second call must be a no-op (returns None)"
    assert ss["cockpit_opportunities"] == "USER_MODIFIED", "must not overwrite"
    assert ss["cockpit_hydrated_from_snapshot"] == "2026-06-20"


def test_cs5_no_hydrate_when_macro_present():
    """§CS-5 — a live macro_regime_result (manual refresh) blocks hydration."""
    ss = {"macro_regime_result": {"regime": "live"}}
    result = hydrate_cockpit_from_snapshot(
        ss, load_meta=lambda: [_meta("2026-06-20")],
        load_opportunities=lambda: [_opp("2026-06-20", "AAA")])
    assert result is None
    assert ss["macro_regime_result"] == {"regime": "live"}
    assert "cockpit_hydrated_from_snapshot" not in ss


def test_cs6_loader_raises_fail_closed():
    """§CS-6 — load_meta raising → no mutation, no exception propagates."""
    ss: dict = {}

    def _boom():
        raise RuntimeError("disk on fire")

    result = hydrate_cockpit_from_snapshot(
        ss, load_meta=_boom, load_opportunities=lambda: [])
    assert result is None
    assert ss == {}, "fail-closed: session_state must be untouched"

    # Also: opportunities loader raising mid-way leaves nothing committed.
    ss2: dict = {}
    result2 = hydrate_cockpit_from_snapshot(
        ss2, load_meta=lambda: [_meta("2026-06-20")], load_opportunities=_boom)
    assert result2 is None
    assert ss2 == {}, "atomic commit: partial state must not leak on failure"


def test_cs7_mutation_probe_key_signals():
    """§CS-7 — distinctive key_signals must flow MetaRecord → macro_regime_result.

    This is the mutation probe: if the hydration logic stopped mapping
    ``key_signals`` (or mapped a wrong/empty default), the sentinel below would be
    absent and this assertion — like §CS-2 — would go RED. The sentinel is a value
    no default could produce.
    """
    ss: dict = {}
    sentinel = ["__PROBE_SIGNAL_42__"]
    hydrate_cockpit_from_snapshot(
        ss, load_meta=lambda: [_meta("2026-06-20", key_signals=sentinel)],
        load_opportunities=lambda: [])
    assert ss["macro_regime_result"]["key_signals"] == sentinel


def test_why_now_codes_normalised():
    """Extra — reason-CODE strings in why_now are dropped (Section C iterates
    them as dicts; a leftover string would crash the render). Dict elements
    survive; no placeholder text is injected."""
    ss: dict = {}
    card = _opp("2026-06-20", "AAA",
                why_now=["code_string", {"text_en": "real", "text_zh": "真实"}])
    hydrate_cockpit_from_snapshot(
        ss, load_meta=lambda: [_meta("2026-06-20")],
        load_opportunities=lambda: [card])
    why = ss["cockpit_opportunities"][0]["why_now"]
    assert why == [{"text_en": "real", "text_zh": "真实"}], f"got {why}"
    # Every surviving element must be safe for Section C's r.get(...) calls.
    assert all(isinstance(r, dict) for r in why)


def test_no_fragility_when_absent():
    """Extra — a snapshot predating fragility → cockpit_fragility not set."""
    ss: dict = {}
    hydrate_cockpit_from_snapshot(
        ss, load_meta=lambda: [_meta("2026-06-20", with_fragility=False)],
        load_opportunities=lambda: [])
    assert "cockpit_fragility" not in ss
    # macro_regime_result still populated (fragility_level defaults to "normal").
    assert ss["macro_regime_result"]["regime"] == "risk_on"


# ---------------------------------------------------------------------------
# Standalone runner (no pytest dependency required)
# ---------------------------------------------------------------------------

def _run() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = 0
    failures: list[str] = []
    for fn in tests:
        try:
            fn()
            passed += 1
            print(f"  PASS  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{fn.__name__}: {exc!r}")
            print(f"  FAIL  {fn.__name__}: {exc!r}")
    print(f"\n{passed}/{len(tests)} passed")
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL PASS — cockpit cold-start hydration")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
