#!/usr/bin/env python3
"""
scripts/test_reliability_valuation_stopbleed.py

Phase "Valuation stop-the-bleed" test suite (mock-only / offline).

Runs entirely WITHOUT real API calls. Verifies the three tasks:

  Task 1 — Anchor consistency gate:
    * lib/equity_valuation.build_app_fair_value dispersion gate (max/min ratio):
      reconcilable anchors blend; irreconcilable (> threshold) collapse the band
      (mid = 0), force low confidence, blend_state = "anchors_irreconcilable",
      and list each anchor with its basis.
    * lib/valuation_anchor anchor_state gate (analyst vs relative).
    * lib/order_advisor LONG path degrades EXPLICITLY to a technical-only
      reference when the anchor state is irreconcilable (never a blended mid),
      and only on the LONG horizon.

  Task 2 — Forward-estimates basis:
    * Relative anchor prefers forward consensus EPS; falls back to trailing with
      relative_basis = "trailing_fallback"; peer P/E basis flagged "mixed".

  Task 3 — Anchor cache + Cockpit LONG enrichment:
    * lib/anchor_cache atomic write / read / staleness boundaries.
    * rank_opportunities top-N enrichment differentiates LONG status with a FRESH
      cached anchor and falls back to Research Required when stale / missing;
      anchor_age_days is recorded for review.

Usage:
    python3 -B scripts/test_reliability_valuation_stopbleed.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["FINNHUB_API_KEY"] = ""

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pandas as pd  # noqa: E402

import lib.anchor_cache as ac  # noqa: E402
import lib.equity_valuation as eqv  # noqa: E402
import lib.valuation_anchor as va  # noqa: E402
import lib.order_advisor as oa  # noqa: E402
import lib.opportunity_ranker as orr  # noqa: E402
import lib.relative_strength as rsm  # noqa: E402


PASS = 0
FAIL = 0
_failures: list = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        d = f"  [{detail}]" if detail else ""
        _failures.append(f"FAIL  {label}{d}")


# ===========================================================================
# Section 1 — equity_valuation dispersion gate boundaries (pure assembler)
# ===========================================================================

# Reconcilable: three anchors within range → blended band, real mid.
_ok = eqv.build_app_fair_value("AAA", 100.0, dcf_value=95.0, relative_value=98.0,
                               analyst_target=110.0, analyst_count=10)
check("1.1 reconcilable anchors -> blend_state 'blended'",
      _ok.blend_state == "blended", detail=_ok.blend_state)
check("1.2 reconcilable anchors -> positive mid", _ok.fair_value_mid > 0)
check("1.3 anchor_dispersion computed (max/min)",
      _ok.anchor_dispersion is not None and _ok.anchor_dispersion < 3.0,
      detail=str(_ok.anchor_dispersion))

# Boundary: ratio EXACTLY 3.0 is NOT irreconcilable (gate uses '>').
_edge = eqv.build_app_fair_value("AAB", 100.0, dcf_value=None, relative_value=30.0,
                                 analyst_target=90.0, analyst_count=5)
check("1.4 dispersion == 3.0 (boundary) stays blended",
      _edge.blend_state == "blended" and abs(_edge.anchor_dispersion - 3.0) < 1e-9,
      detail=f"{_edge.blend_state} disp={_edge.anchor_dispersion}")

# Just over the boundary → irreconcilable.
_over = eqv.build_app_fair_value("AAC", 100.0, dcf_value=None, relative_value=29.9,
                                 analyst_target=90.0, analyst_count=5)
check("1.5 dispersion > 3.0 -> anchors_irreconcilable",
      _over.blend_state == "anchors_irreconcilable", detail=_over.blend_state)
check("1.6 irreconcilable -> mid collapsed to 0 (no fake band)",
      _over.fair_value_mid == 0.0 and _over.fair_value_low == 0.0
      and _over.fair_value_high == 0.0)
check("1.7 irreconcilable -> confidence forced low", _over.confidence == "low")
check("1.8 irreconcilable -> anchors listed side by side with basis",
      len(_over.anchors) >= 2 and all("basis" in a and "value" in a for a in _over.anchors),
      detail=str(_over.anchors))

# The audit case: relative $3.23 vs analyst $112.50 → must NOT blend to a mid.
_audit = eqv.build_app_fair_value("NVDA", 100.0, dcf_value=None, relative_value=3.23,
                                  analyst_target=112.50, analyst_count=10)
check("1.9 audit case ($3.23 vs $112.50) -> irreconcilable, no $53 mid",
      _audit.blend_state == "anchors_irreconcilable" and _audit.fair_value_mid == 0.0,
      detail=str(_audit.fair_value_mid))

# Single anchor → cannot be irreconcilable (no dispersion).
_one = eqv.build_app_fair_value("AAD", 100.0, dcf_value=None, relative_value=None,
                                analyst_target=110.0, analyst_count=8)
check("1.10 single anchor -> blended (no dispersion gate)",
      _one.blend_state == "blended" and _one.anchor_dispersion is None)

# No anchors → no_anchor (current-price band).
_none = eqv.build_app_fair_value("AAE", 100.0, None, None, None)
check("1.11 no anchors -> blend_state 'no_anchor'", _none.blend_state == "no_anchor")


# ===========================================================================
# Section 2 — forward/trailing relative-anchor basis selection (Task 2)
# ===========================================================================

def _raw(**over) -> dict:
    base = {
        "fcf_ttm": None, "fcf_source": "", "ebitda": None, "shares": None,
        "growth_rate": 0.05, "trailing_eps": None, "forward_eps": None,
        "sector": "Technology", "analyst_median": None, "analyst_mean": None,
        "analyst_count": 0, "live": True,
    }
    base.update(over)
    return base


def _fv_from_raw(ticker: str, raw: dict):
    with mock.patch.object(eqv, "_fetch_raw", return_value=raw):
        return eqv.compute_app_fair_value(ticker, 100.0)


# Forward EPS present → relative uses forward basis, peer P/E flagged mixed.
_fwd = _fv_from_raw("FWD1", _raw(forward_eps=6.0, trailing_eps=5.0))
check("2.1 forward EPS present -> relative_basis 'forward'",
      _fwd.relative_basis == "forward", detail=_fwd.relative_basis)
check("2.2 forward EPS -> relative_value = sector_pe(28) * fwd_eps(6) = 168",
      _fwd.relative_value == 168.0, detail=str(_fwd.relative_value))
check("2.3 forward EPS x trailing sector median -> peer_pe_basis 'mixed'",
      _fwd.peer_pe_basis == "mixed", detail=_fwd.peer_pe_basis)

# Forward EPS absent → trailing fallback with the basis flag.
_trl = _fv_from_raw("TRL1", _raw(forward_eps=None, trailing_eps=5.0))
check("2.4 forward missing -> relative_basis 'trailing_fallback'",
      _trl.relative_basis == "trailing_fallback", detail=_trl.relative_basis)
check("2.5 trailing fallback -> relative_value = 28 * 5 = 140",
      _trl.relative_value == 140.0, detail=str(_trl.relative_value))
check("2.6 trailing fallback -> peer_pe_basis 'trailing'",
      _trl.peer_pe_basis == "trailing", detail=_trl.peer_pe_basis)

# Non-positive forward EPS is rejected -> trailing fallback.
_negfwd = _fv_from_raw("NEG1", _raw(forward_eps=-2.0, trailing_eps=5.0))
check("2.7 non-positive forward EPS -> trailing_fallback",
      _negfwd.relative_basis == "trailing_fallback", detail=_negfwd.relative_basis)

# No EPS at all -> no relative anchor, empty basis.
_noeps = _fv_from_raw("NOE1", _raw(forward_eps=None, trailing_eps=None))
check("2.8 no EPS -> relative_value None, basis empty",
      _noeps.relative_value is None and _noeps.relative_basis == "")


# ===========================================================================
# Section 3 — valuation_anchor anchor_state gate
# ===========================================================================

def _fva_with(info: dict, pe_median, ticker: str, cp: float = 200.0, vp: float = 0.3):
    mock_ticker = mock.MagicMock()
    mock_ticker.info = info
    with mock.patch("yfinance.Ticker", return_value=mock_ticker), \
            mock.patch.object(va, "_median_trailing_pe", return_value=pe_median):
        return va.compute_fair_value_anchor(ticker, cp, vp)


# analyst 120 vs relative (pe 2 * eps 5 = 10) -> ratio 12 -> irreconcilable.
_irr = _fva_with(
    {"targetMeanPrice": 120.0, "targetMedianPrice": 120.0, "targetHighPrice": 130.0,
     "targetLowPrice": 110.0, "numberOfAnalystOpinions": 10, "trailingEps": 5.0},
    pe_median=2.0, ticker="VAIRR")
check("3.1 valuation_anchor irreconcilable -> anchor_state set",
      _irr.anchor_state == "anchors_irreconcilable", detail=_irr.anchor_state)
check("3.2 irreconcilable -> confidence forced low", _irr.confidence == "low")
check("3.3 irreconcilable -> conservative_anchor None", _irr.conservative_anchor is None)

# analyst 120 vs relative 100 (pe 20 * eps 5) -> ratio 1.2 -> blended.
_blend = _fva_with(
    {"targetMeanPrice": 120.0, "targetMedianPrice": 120.0, "targetHighPrice": 126.0,
     "targetLowPrice": 114.0, "numberOfAnalystOpinions": 10, "trailingEps": 5.0},
    pe_median=20.0, ticker="VAOK")
check("3.4 consistent anchors -> anchor_state 'blended'",
      _blend.anchor_state == "blended", detail=_blend.anchor_state)

# Boundary: ratio exactly 3.0 (analyst 120 vs relative 40) -> blended.
_edge_va = _fva_with(
    {"targetMeanPrice": 120.0, "targetMedianPrice": 120.0, "targetHighPrice": 126.0,
     "targetLowPrice": 114.0, "numberOfAnalystOpinions": 10, "trailingEps": 5.0},
    pe_median=8.0, ticker="VAEDGE")
check("3.5 ratio == 3.0 boundary -> blended (not irreconcilable)",
      _edge_va.anchor_state == "blended", detail=_edge_va.anchor_state)


# ===========================================================================
# Section 4 — order_advisor LONG degrade + differentiation
# ===========================================================================

_IRREC_BAND = {"blend_state": "anchors_irreconcilable", "confidence": "low"}
_GOOD_BAND = {"blend_state": "blended", "confidence": "high",
              "fair_value_low": 100.0, "fair_value_mid": 110.0, "fair_value_high": 130.0}

# LONG + irreconcilable band -> explicit technical-only degrade (no zone).
_long_irr = oa.compute_price_levels("ZZZ", horizon="long", app_fair_value=_IRREC_BAND)
check("4.1 LONG irreconcilable -> action wait (no entry)",
      _long_irr.action == "wait" and _long_irr.entry_zone_low is None)
check("4.2 LONG irreconcilable -> 'valuation unreliable' reason",
      "valuation unreliable" in _long_irr.reason.lower(), detail=_long_irr.reason)

# SHORT is unaffected by an irreconcilable valuation anchor.
_short_irr = oa.compute_price_levels("ZZZ", horizon="short", app_fair_value=_IRREC_BAND)
check("4.3 SHORT not degraded by irreconcilable valuation",
      "valuation unreliable" not in _short_irr.reason.lower())

# LONG + good high-confidence band where price sits in the band -> in_zone, and
# valuation_confidence reflects the app band (high), NOT the fixture proxy (low).
_long_ok = oa.compute_price_levels("ZZZ", horizon="long", app_fair_value=_GOOD_BAND)
check("4.4 LONG good band -> entry_status in_zone",
      _long_ok.entry_status == "in_zone", detail=_long_ok.entry_status)
check("4.5 LONG good band -> valuation_confidence == high (band, not proxy)",
      _long_ok.valuation_confidence == "high", detail=_long_ok.valuation_confidence)

# fva_obj-side irreconcilable (analyst-proxy path, no app band) also degrades LONG.
_fva_irr = va.FairValueAnchor(ticker="ZZZ", confidence="low",
                              anchor_state="anchors_irreconcilable",
                              fair_value_anchor=85.0)
_snap = {"price": 100.0, "ATR_14": 3.0, "SMA_200": 80.0, "Vol_ratio_20d": 1.0,
         "nearest_support": None, "nearest_resistance": None, "candlestick_pattern": "none"}
_df = pd.DataFrame([[99, 102, 97, 100, 1_000_000]] * 40,
                   columns=["Open", "High", "Low", "Close", "Volume"])
with mock.patch("ui_utils.load_ohlcv", return_value=_df), \
        mock.patch("lib.technical.snapshot", return_value=_snap), \
        mock.patch("lib.valuation_anchor.compute_fair_value_anchor", return_value=_fva_irr):
    _long_fva = oa.compute_price_levels("ZZZ", horizon="long")
check("4.6 fva_obj irreconcilable -> LONG degraded to technical-only",
      _long_fva.action == "wait" and "valuation unreliable" in _long_fva.reason.lower(),
      detail=_long_fva.reason)

# approved_for_execution invariant holds on the degraded path.
check("4.7 degraded LONG keeps approved_for_execution False",
      _long_irr.approved_for_execution is False)

# Missing / low-confidence LONG anchor (fixture: no app band, fva_obj None) emits
# the SAME unified degrade reason + next_trigger as the irreconcilable path.
_long_missing = oa.compute_price_levels("ZZQ", horizon="long")
check("4.8 missing-anchor LONG -> same unified degrade reason as irreconcilable",
      _long_missing.reason == _long_irr.reason and _long_missing.entry_zone_low is None,
      detail=_long_missing.reason)
check("4.9 missing-anchor LONG -> same unified next_trigger",
      _long_missing.next_trigger == _long_irr.next_trigger)
check("4.10 unified degrade reason carries 'valuation unreliable'",
      "valuation unreliable" in _long_missing.reason.lower())
check("4.11 unified degrade code constant exposed",
      oa._LONG_DEGRADE_CODE == "valuation_unreliable_technical_only",
      detail=oa._LONG_DEGRADE_CODE)


# ===========================================================================
# Section 5 — anchor_cache write / read / staleness (temp file)
# ===========================================================================

with tempfile.TemporaryDirectory() as _td:
    _p = Path(_td) / "anchor_cache.json"
    _e1 = {"confidence": "high", "blend_state": "blended", "fair_value_low": 90.0,
           "fair_value_mid": 100.0, "fair_value_high": 120.0,
           "computed_at": datetime(2026, 6, 3, tzinfo=timezone.utc).isoformat()}
    ok1 = ac.write_anchor("NVDA", _e1, path=_p)
    check("5.1 write_anchor returns True", ok1 is True)
    check("5.2 cache file written atomically (no .tmp left)",
          _p.is_file() and not _p.with_suffix(".json.tmp").exists())
    got = ac.read_anchor("NVDA", path=_p)
    check("5.3 read_anchor round-trips the entry",
          got is not None and got["fair_value_mid"] == 100.0)
    check("5.4 read_anchor stamps ticker", got.get("ticker") == "NVDA")

    # second write merges (other tickers preserved).
    ac.write_anchor("AMD", {"confidence": "medium", "fair_value_mid": 50.0,
                            "computed_at": datetime(2026, 6, 4, tzinfo=timezone.utc).isoformat()},
                    path=_p)
    allmap = ac.load_all(_p)
    check("5.5 second write preserves the first ticker",
          set(allmap.keys()) == {"NVDA", "AMD"}, detail=str(set(allmap.keys())))

    # staleness boundaries against a fixed 'now'.
    _now = datetime(2026, 6, 8, tzinfo=timezone.utc)  # 5 days after NVDA computed_at
    check("5.6 entry_age_days computed (5.0 days)",
          abs(ac.entry_age_days(_e1, now=_now) - 5.0) < 1e-6,
          detail=str(ac.entry_age_days(_e1, now=_now)))
    check("5.7 fresh within default window (7d)", ac.is_fresh(_e1, now=_now) is True)
    _now_stale = datetime(2026, 6, 12, tzinfo=timezone.utc)  # 9 days
    check("5.8 stale beyond default window", ac.is_fresh(_e1, now=_now_stale) is False)
    # exact boundary: age == max_age_days is still fresh (<=).
    check("5.9 boundary age == max_age_days is fresh",
          ac.is_fresh(_e1, max_age_days=5, now=_now) is True)
    check("5.10 age just over max_age_days is stale",
          ac.is_fresh(_e1, max_age_days=5,
                      now=datetime(2026, 6, 8, 1, tzinfo=timezone.utc)) is False)
    # missing timestamp -> stale.
    check("5.11 missing computed_at -> not fresh",
          ac.is_fresh({"confidence": "high"}, now=_now) is False)
    # missing file -> empty map, no raise.
    check("5.12 absent cache file -> {} (fail-closed)",
          ac.load_all(Path(_td) / "nope.json") == {})

    # write-through from an AppFairValue (entry_from_app_fair_value normalization).
    _appfv = eqv.build_app_fair_value("ORCL", 100.0, dcf_value=95.0,
                                      relative_value=98.0, analyst_target=110.0,
                                      analyst_count=10, relative_basis="forward")
    ac.write_app_fair_value(_appfv, path=_p)
    orcl = ac.read_anchor("ORCL", path=_p)
    check("5.13 write_app_fair_value persists band + state",
          orcl is not None and orcl["blend_state"] == "blended"
          and orcl["conservative_anchor"] == orcl["fair_value_low"],
          detail=str(orcl))

    # irreconcilable AppFairValue -> conservative_anchor None in the cache.
    _appirr = eqv.build_app_fair_value("BADX", 100.0, dcf_value=None,
                                       relative_value=3.0, analyst_target=120.0,
                                       analyst_count=10)
    ac.write_app_fair_value(_appirr, path=_p)
    badx = ac.read_anchor("BADX", path=_p)
    check("5.14 irreconcilable cached -> conservative_anchor None",
          badx["blend_state"] == "anchors_irreconcilable"
          and badx["conservative_anchor"] is None, detail=str(badx))

    # Version is respected on read: mismatched envelopes load as empty (safe for
    # future schema migrations); the supported version + bare legacy load normally.
    import json as _json
    _vp = Path(_td) / "ver.json"
    _cur_ver = ac._SCHEMA_VERSION
    for _bad in (0, _cur_ver - 1, _cur_ver + 1):
        with open(_vp, "w", encoding="utf-8") as fh:
            _json.dump({"version": _bad, "anchors": {"X": {"fair_value_mid": 1.0}}}, fh)
        check(f"5.15 version={_bad} envelope loads as empty",
              ac.load_all(_vp) == {}, detail=str(ac.load_all(_vp)))
    with open(_vp, "w", encoding="utf-8") as fh:
        _json.dump({"version": _cur_ver, "anchors": {"X": {"fair_value_mid": 1.0}}}, fh)
    check(f"5.16 supported version (=={_cur_ver}) loads", set(ac.load_all(_vp)) == {"X"})
    # DELIBERATE ASSERTION CHANGE (review fix F3/I4): bare un-versioned legacy
    # objects are now REJECTED (invalidated → recomputed), not tolerated, so stale
    # entries lacking company_type cannot surface. Old files degrade gracefully.
    with open(_vp, "w", encoding="utf-8") as fh:
        _json.dump({"X": {"fair_value_mid": 1.0}}, fh)
    check("5.17 bare un-versioned legacy object is now REJECTED (loads as empty)",
          ac.load_all(_vp) == {}, detail=str(ac.load_all(_vp)))


# ===========================================================================
# Section 6 — Cockpit rank_opportunities LONG enrichment (fresh vs stale)
# ===========================================================================

class _DuckLevels:
    def __init__(self, **k):
        self.entry_status = k.get("entry_status", "wait")
        self.valuation_confidence = k.get("valuation_confidence", "low")
        self.risk_overlay_passed = True
        self.missing_conditions = []
        self.next_trigger = ""
        self.horizon = k.get("horizon", "mid")
        self.entry_zone_low = None
        self.entry_zone_high = None
        self.stop_loss = None
        self.target_price = None
        self.risk_reward_ratio = 0.0
        self.position_size_pct = 0.0


def _mock_plf(tk, holding=None, horizon="mid", app_fair_value=None, **kw):
    # A fresh high-confidence band makes LONG in-zone (Actionable); otherwise the
    # LONG view is "below the value zone" -> Research Required.
    if horizon == "long" and app_fair_value and str(app_fair_value.get("confidence")) == "high":
        return _DuckLevels(entry_status="in_zone", valuation_confidence="high", horizon="long")
    es = "below_zone" if horizon == "long" else "in_zone"
    return _DuckLevels(entry_status=es, valuation_confidence="low", horizon=horizon)


_cand = dict(ticker="NVDA", short_score=0.3, mid_score=0.4, long_score=0.9,
             candidate_type="FUNNEL", eps_revision_direction="improving",
             valuation_percentile=0.4)
_today = date(2026, 6, 5)
_rs = {"NVDA": rsm.RelativeStrength("NVDA", rs_composite=0.5, data_source="live")}
_fresh_entry = {"fair_value_low": 80.0, "fair_value_mid": 100.0, "fair_value_high": 130.0,
                "confidence": "high", "blend_state": "blended",
                "computed_at": datetime(2026, 6, 3, tzinfo=timezone.utc).isoformat()}
_stale_entry = {**_fresh_entry,
                "computed_at": datetime(2026, 5, 1, tzinfo=timezone.utc).isoformat()}


def _rank_long_status(cache):
    card = orr.rank_opportunities(
        [dict(_cand)], rs_map=_rs, earnings_map={}, top_n=1,
        price_levels_fn=_mock_plf, anchor_cache=cache, today=_today)[0]
    return card


_fresh_card = _rank_long_status({"NVDA": _fresh_entry})
check("6.1 fresh cached anchor -> LONG differentiates (Actionable Now)",
      _fresh_card.status_by_horizon.get("long") == orr.STATUS_ACTIONABLE,
      detail=str(_fresh_card.status_by_horizon.get("long")))
check("6.2 fresh anchor -> anchor_age_days recorded",
      _fresh_card.anchor_age_days == 2.0, detail=str(_fresh_card.anchor_age_days))

_stale_card = _rank_long_status({"NVDA": _stale_entry})
check("6.3 stale anchor -> LONG falls back to Research Required",
      _stale_card.status_by_horizon.get("long") == orr.STATUS_RESEARCH,
      detail=str(_stale_card.status_by_horizon.get("long")))
check("6.4 stale anchor -> anchor_age_days None (not used)",
      _stale_card.anchor_age_days is None)

_missing_card = _rank_long_status(None)
check("6.5 no cache -> LONG Research Required (prior behavior)",
      _missing_card.status_by_horizon.get("long") == orr.STATUS_RESEARCH
      and _missing_card.anchor_age_days is None)

# snapshot record carries anchor_age_days.
_rec = orr._card_snapshot_record(_fresh_card, "2026-06-05", "neutral")
check("6.6 snapshot record exposes anchor_age_days",
      _rec.get("anchor_age_days") == 2.0, detail=str(_rec.get("anchor_age_days")))

# A FRESH but UNUSABLE (irreconcilable) anchor still records anchor_age_days —
# usability is carried by blend_state / the LONG degrade, NOT the age field.
_irr_entry = {"fair_value_low": 0.0, "fair_value_mid": 0.0, "fair_value_high": 0.0,
              "confidence": "low", "blend_state": "anchors_irreconcilable",
              "computed_at": datetime(2026, 6, 3, tzinfo=timezone.utc).isoformat()}
_irr_card = _rank_long_status({"NVDA": _irr_entry})
check("6.7 fresh irreconcilable -> LONG still Research Required",
      _irr_card.status_by_horizon.get("long") == orr.STATUS_RESEARCH,
      detail=str(_irr_card.status_by_horizon.get("long")))
check("6.8 fresh irreconcilable -> anchor_age_days recorded (usability-independent)",
      _irr_card.anchor_age_days == 2.0, detail=str(_irr_card.anchor_age_days))

# An injected legacy plf WITHOUT the app_fair_value kwarg still works (retry path).
def _legacy_plf(tk, holding=None, horizon="mid", **kw):
    return _DuckLevels(entry_status="in_zone" if horizon != "long" else "below_zone",
                       horizon=horizon)


_legacy_card = orr.rank_opportunities(
    [dict(_cand)], rs_map=_rs, earnings_map={}, top_n=1,
    price_levels_fn=_legacy_plf, anchor_cache={"NVDA": _fresh_entry}, today=_today)[0]
check("6.9 legacy plf signature (no app_fair_value kwarg) does not crash",
      _legacy_card.enriched is True)


# ===========================================================================
# Section 7 — guardrails (no execution / DB tokens in the new module)
# ===========================================================================

_ac_src = ""
_ac_path = os.path.join(_REPO_ROOT, "lib", "anchor_cache.py")
if os.path.isfile(_ac_path):
    with open(_ac_path, "r", encoding="utf-8") as fh:
        _ac_src = fh.read().lower()
check("7.1 anchor_cache has no DB / vector store",
      not any(tok in _ac_src for tok in ("sqlite", "psycopg", "chromadb", "pinecone",
                                         "faiss", "sqlalchemy")))
check("7.2 anchor_cache has no order / execution capability",
      not any(tok in _ac_src for tok in ("approved_for_execution", "place_order",
                                         "submit_order", "broker")))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n".join(_failures))
total = PASS + FAIL
print(f"\nValuation stop-the-bleed — {PASS}/{total} checks passed.")
if FAIL:
    print(f"{FAIL} FAILED.")
    sys.exit(1)
print("ALL PASSED.")
