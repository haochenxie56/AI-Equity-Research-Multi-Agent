#!/usr/bin/env python3
"""
scripts/test_reliability_anchor_archive.py

Anchor Intelligence v2.3 — anchor historization test suite (mock-only / offline).

Covers the three round deliverables and their access-path invariants:

  * U1 — append-only anchor archive (``lib/anchor_archive.py``): record mapping,
    data_vintage default + override, APPEND-ONLY (a second valuation appends a row
    and never mutates the prior one), schema-version read guard, fail-closed I/O,
    and the page-path write-through via ``store_equity_research_result``.
  * U2 — snapshot anchor block (``lib/opportunity_ranker.py``): the ranking path
    stamps every card's ``anchor`` block from the SAME read-only anchor_cache that
    drove LONG status (single vintage), with an honest ``anchor_not_cached`` state
    when no fresh entry exists; PARITY of the serialized block vs its cache source.
  * U3 — deterministic migration readout (``lib/anchor_migration.py``) and its
    READ-ONLY ``lib/thesis_monitor.py`` surface: fixed fixtures → fixed
    direction/speed/consistency; the thesis annotation is watch-level only (never
    changes thesis_status, never computes/fetches).

Usage:
    python3 -B scripts/test_reliability_anchor_archive.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["FINNHUB_API_KEY"] = ""

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from datetime import date as _date  # noqa: E402

import pandas as pd  # noqa: E402

import lib.anchor_archive as aa  # noqa: E402
import lib.anchor_cache as ac  # noqa: E402
import lib.anchor_migration as am  # noqa: E402
import lib.equity_valuation as eqv  # noqa: E402
import lib.holdings as holds  # noqa: E402
import lib.order_advisor as oa  # noqa: E402
import lib.opportunity_ranker as orr  # noqa: E402
import lib.thesis_monitor as tm  # noqa: E402


# Live yfinance-style raw (raw["live"]=True → AppFairValue.data_source=="live"),
# reused to drive a real page-path live computation through the producer.
_LIVE_RAW = {
    "fcf_ttm": 2.0e9, "fcf_source": "", "ebitda": 8.0e9, "shares": 1.1e9,
    "growth_rate": 0.15, "trailing_eps": 5.0, "forward_eps": None,
    "sector": "Technology", "industry": "Semiconductors",
    "analyst_median": 110.0, "analyst_mean": 108.0, "analyst_high": 130.0,
    "analyst_low": 95.0, "analyst_count": 20, "revenue_growth": 0.20,
    "earnings_growth": 0.10, "profit_margin": 0.10, "operating_margin": 0.12,
    "market_cap": 1.1e11, "enterprise_value": 1.2e11, "total_revenue": 2.5e10,
    "total_debt": 1.0e10, "total_cash": 0.9e10, "book_value": 30.0,
    "price_to_book": 3.0, "price_to_sales": 4.0, "live": True,
}


def _df40():
    rows = [[99.0, 102.0, 97.0, 100.0, 1_000_000.0] for _ in range(40)]
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])


def _snap100():
    return {"price": 100.0, "EMA_10": None, "EMA_20": None, "SMA_50": None,
            "SMA_200": 80.0, "RSI_14": 50.0, "ADX": None, "ATR_14": 3.0,
            "Vol_ratio_20d": 1.0, "above_SMA200": True, "pct_from_52w_high": -5.0,
            "nearest_support": None, "nearest_resistance": None,
            "candlestick_pattern": "none"}

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


def _fv(ticker="MU", computed_at="2026-06-08T13:00:00+00:00", mid=110.0,
        pool=None, **kw):
    """A duck-typed AppFairValue stand-in (real dataclass kwargs)."""
    base = dict(
        ticker=ticker, computed_at=computed_at, company_type="cyclical",
        fair_value_low=mid * 0.86, fair_value_mid=mid, fair_value_high=mid * 1.18,
        blend_state="blended",
        analyst_pool=(pool if pool is not None else
                      {"median": 112.5, "mean": 110.0, "high": 130.0,
                       "low": 95.0, "n": 20, "as_of": "2026-06-08"}),
        methods_used=["dcf", "relative", "analyst"], excluded_anchors=[],
        caveats=["single_anchor_blend"],
    )
    base.update(kw)
    return eqv.AppFairValue(**base)


# ===========================================================================
# 1. U1 — record mapping + data_vintage
# ===========================================================================
_rec = aa.record_from_app_fair_value(_fv())
check("1.1 record schema_version is the current constant",
      _rec["schema_version"] == aa.ANCHOR_ARCHIVE_SCHEMA_VERSION)
check("1.2 record carries the full v2.3 schema key set",
      set(_rec.keys()) == {
          "schema_version", "ticker", "computed_at", "data_vintage",
          "company_type", "fair_value_low", "fair_value_mid", "fair_value_high",
          "blend_state", "analyst_pool", "methods_used", "excluded_anchors",
          "caveats"},
      detail=str(sorted(_rec.keys())))
check("1.3 analyst_pool projected to {median,mean,high,low,n} (as_of dropped)",
      set(_rec["analyst_pool"].keys()) == {"median", "mean", "high", "low", "n"},
      detail=str(_rec["analyst_pool"]))
check("1.4 data_vintage defaults to the computed_at DATE",
      _rec["data_vintage"] == "2026-06-08", detail=_rec["data_vintage"])
_rec_ov = aa.record_from_app_fair_value(_fv(), data_vintage="2026-05-30")
check("1.5 data_vintage explicit override honored",
      _rec_ov["data_vintage"] == "2026-05-30", detail=_rec_ov["data_vintage"])
_rec_np = aa.record_from_app_fair_value(
    eqv.AppFairValue(ticker="MU", computed_at="2026-06-08T13:00:00+00:00",
                     fair_value_mid=110.0, analyst_pool=None))
check("1.6 no analyst coverage -> analyst_pool None (not fabricated)",
      _rec_np["analyst_pool"] is None)


# ===========================================================================
# 2. U1 — APPEND-ONLY + schema guard + fail-closed
# ===========================================================================
_d = tempfile.mkdtemp()
_p = Path(_d) / "anchor_archive.jsonl"

check("2.1 append #1 succeeds", aa.append_anchor_record(_fv(mid=110.0), path=_p))
_line1_after_first = _p.read_text(encoding="utf-8").splitlines()[0]
check("2.2 append #2 (same ticker) succeeds",
      aa.append_anchor_record(
          _fv(mid=105.0, computed_at="2026-06-09T13:00:00+00:00"), path=_p))
_lines = _p.read_text(encoding="utf-8").splitlines()
check("2.3 second valuation APPENDS a row (2 lines total)", len(_lines) == 2,
      detail=str(len(_lines)))
check("2.4 APPEND-ONLY: the prior row is byte-for-byte unchanged",
      _lines[0] == _line1_after_first)
check("2.5 the two rows carry the two distinct mids (no in-place edit)",
      json.loads(_lines[0])["fair_value_mid"] == 110.0
      and json.loads(_lines[1])["fair_value_mid"] == 105.0)
_read = aa.read_archive("MU", path=_p)
check("2.6 read_archive returns both rows oldest->newest",
      [r["fair_value_mid"] for r in _read] == [110.0, 105.0],
      detail=str([r["fair_value_mid"] for r in _read]))

# Schema-version guard: a hand-written wrong-version row is SKIPPED on read but the
# valid rows survive (append-only file with mixed versions stays readable).
with open(_p, "a", encoding="utf-8") as _fh:
    _fh.write(json.dumps({"schema_version": 999, "ticker": "MU",
                          "computed_at": "2026-06-10T00:00:00+00:00",
                          "fair_value_mid": 1.0}) + "\n")
_read2 = aa.read_archive("MU", path=_p)
check("2.7 schema-version guard skips the wrong-version row on read",
      [r["fair_value_mid"] for r in _read2] == [110.0, 105.0],
      detail=str([r["fair_value_mid"] for r in _read2]))
check("2.8 fail-closed: append with no ticker returns False, writes nothing",
      aa.append_record({"fair_value_mid": 5.0}) is False)
check("2.9 fail-closed: read of a missing archive -> []",
      aa.read_archive("MU", path=Path(_d) / "nope.jsonl") == [])
# window truncation
for i in range(5):
    aa.append_anchor_record(
        _fv(ticker="WNDW", mid=100.0 + i,
            computed_at=f"2026-06-0{i+1}T00:00:00+00:00"), path=_p)
check("2.10 read_archive window keeps only the most recent N",
      [r["fair_value_mid"] for r in aa.read_archive("WNDW", window=2, path=_p)]
      == [103.0, 104.0])


# ===========================================================================
# 3. U1/F1 — archive at the PRODUCER chokepoint (covers pages/4, pages/7, pages/9)
# ===========================================================================
# F1: the append lives at compute_app_fair_value (its live return), NOT at
# store_equity_research_result — so EVERY page-path live compute is historized,
# including the Trading Desk (pages/9), which never calls the hand-off.
_d2 = tempfile.mkdtemp()
_p2 = Path(_d2) / "anchor_archive.jsonl"
aa.reset_dedup_cache()
getattr(eqv._compute_cached, "clear", lambda: None)()
with mock.patch.object(aa, "ANCHOR_ARCHIVE_PATH", _p2), \
        mock.patch.object(eqv, "_fetch_raw", return_value=dict(_LIVE_RAW)):
    _fv_live1 = eqv.compute_app_fair_value("MU", 100.0)
    _fv_live2 = eqv.compute_app_fair_value("MU", 100.0)  # cache hit -> same vintage
_lines2 = _p2.read_text(encoding="utf-8").splitlines() if _p2.exists() else []
check("3.1 producer chokepoint: a live compute appends exactly one archive row",
      len(_lines2) == 1 and _fv_live1.data_source == "live",
      detail=f"{len(_lines2)}/{_fv_live1.data_source}")
check("3.2 dedup: same-vintage recompute (cache hit, identical computed_at) appends nothing",
      len(_lines2) == 1 and _fv_live1.computed_at == _fv_live2.computed_at,
      detail=f"{len(_lines2)}/{_fv_live1.computed_at}=={_fv_live2.computed_at}")
check("3.3 archived row is the live MU vintage",
      _lines2 and json.loads(_lines2[0])["ticker"] == "MU"
      and json.loads(_lines2[0])["computed_at"] == _fv_live1.computed_at)

# 3.4 F1 CORE: the Trading Desk (pages/9) live compute — driven through the REAL
# order_advisor.compute_price_levels(allow_fetch=True) -> _gather_technicals ->
# compute_app_fair_value path, which never calls store_equity_research_result —
# DOES enter the archive. This is the exact gap F1 closes; it would FAIL before the
# producer-chokepoint move.
_d3 = tempfile.mkdtemp()
_p3 = Path(_d3) / "anchor_archive.jsonl"
aa.reset_dedup_cache()
getattr(eqv._compute_cached, "clear", lambda: None)()
with mock.patch.object(aa, "ANCHOR_ARCHIVE_PATH", _p3), \
        mock.patch.object(eqv, "_fetch_raw", return_value=dict(_LIVE_RAW)), \
        mock.patch("ui_utils.load_ohlcv", return_value=_df40()), \
        mock.patch("lib.technical.snapshot", return_value=_snap100()), \
        mock.patch("lib.holdings.load_holdings", return_value=[]), \
        mock.patch("lib.holdings.load_cash_position", return_value=0.0), \
        mock.patch("lib.holdings.load_portfolio_settings",
                   return_value=holds.PortfolioSettings()):
    _pl = oa.compute_price_levels("TDX", None, horizon="long",
                                  valuation_percentile=0.3, allow_fetch=True)
_lines3 = _p3.read_text(encoding="utf-8").splitlines() if _p3.exists() else []
check("3.4 F1: Trading Desk (pages/9, allow_fetch=True) live anchor enters the archive",
      len(_lines3) == 1 and json.loads(_lines3[0])["ticker"] == "TDX",
      detail=f"{len(_lines3)}/{[json.loads(x)['ticker'] for x in _lines3]}")

# 3.5 a fixture fallback (data_source != live) is NEVER historized — no fabricated
# anchor in the migration series.
_d4 = tempfile.mkdtemp()
_p4 = Path(_d4) / "anchor_archive.jsonl"
aa.reset_dedup_cache()
getattr(eqv._compute_cached, "clear", lambda: None)()
with mock.patch.object(aa, "ANCHOR_ARCHIVE_PATH", _p4), \
        mock.patch.object(eqv, "_fetch_raw", return_value={}):
    _fv_fix = eqv.compute_app_fair_value("FIXY", 100.0)
check("3.5 fixture fallback is NOT archived (data_source != live)",
      _fv_fix.data_source != "live" and not _p4.exists(),
      detail=f"{_fv_fix.data_source}/exists={_p4.exists()}")

# 3.6 store_equity_research_result no longer appends on its own (chokepoint moved).
_d5 = tempfile.mkdtemp()
_p5 = Path(_d5) / "anchor_archive.jsonl"
aa.reset_dedup_cache()
with mock.patch.object(aa, "ANCHOR_ARCHIVE_PATH", _p5):
    eqv.store_equity_research_result("MU", _fv(mid=110.0))
check("3.6 store_equity_research_result is no longer an archive site (no double-write)",
      not _p5.exists(), detail=f"exists={_p5.exists()}")


# ===========================================================================
# 4. U3 — migration readout determinism (pure compute over fixed fixtures)
# ===========================================================================
def _mrec(mid, med, mean, ca):
    return {"schema_version": aa.ANCHOR_ARCHIVE_SCHEMA_VERSION, "ticker": "MU",
            "computed_at": ca, "fair_value_mid": mid,
            "analyst_pool": {"median": med, "mean": mean,
                             "high": med * 1.2, "low": med * 0.8, "n": 20}}


_conv_fall = [_mrec(110, 112, 111, "d1"), _mrec(108, 110, 109, "d2"),
              _mrec(105, 108, 107, "d3")]
_m = am.compute_migration(_conv_fall)
check("4.1 conviction falling: all three series 'falling'",
      {_m["series"][k]["direction"] for k in _m["series"]} == {"falling"})
check("4.2 conviction falling: consistency=conviction, direction=falling",
      _m["consistency"] == "conviction" and _m["direction"] == "falling")
check("4.3 conviction falling: deteriorating True (hard thesis-erosion signal)",
      _m["deteriorating"] is True)
check("4.4 speed is Δ/session deterministic ((105-110)/2)=-2.5",
      _m["series"]["fair_value_mid"]["speed"] == -2.5,
      detail=str(_m["series"]["fair_value_mid"]["speed"]))

_conv_rise = [_mrec(105, 108, 107, "d1"), _mrec(108, 110, 109, "d2"),
              _mrec(110, 112, 111, "d3")]
_mr = am.compute_migration(_conv_rise)
check("4.5 conviction rising: consistency=conviction, NOT deteriorating",
      _mr["consistency"] == "conviction" and _mr["direction"] == "rising"
      and _mr["deteriorating"] is False)

# lone-anchor drift: fair_value_mid plunges, analyst pool holds flat -> noise.
_lone = [_mrec(110, 112, 111, "d1"), _mrec(100, 111, 110, "d2")]
_ml = am.compute_migration(_lone)
check("4.6 lone-anchor drift: consistency=low_consistency, NOT deteriorating",
      _ml["consistency"] == "low_consistency" and _ml["deteriorating"] is False,
      detail=f"{_ml['consistency']}/{_ml['deteriorating']}")
check("4.7 lone-anchor drift flags lone_anchor_drift caveat",
      "lone_anchor_drift" in _ml["caveats"])

_flat = [_mrec(110, 112, 111, "d1"), _mrec(111, 113, 112, "d2")]
check("4.8 all-flat series -> consistency=stable, direction=flat",
      am.compute_migration(_flat)["consistency"] == "stable")
check("4.9 single record -> insufficient (no direction read)",
      am.compute_migration([_mrec(110, 112, 111, "d1")])["consistency"]
      == "insufficient")
check("4.10 empty -> insufficient", am.compute_migration([])["consistency"]
      == "insufficient")
# window truncation inside compute_migration
_many = [_mrec(100 + i, 100 + i, 100 + i, f"d{i:03d}") for i in range(40)]
check("4.11 compute_migration honors window (40 recs, window 30 -> n=30)",
      am.compute_migration(_many, window=30)["n_records"] == 30)
# determinism: identical input -> identical output
check("4.12 deterministic: identical input -> identical output",
      am.compute_migration(_conv_fall) == am.compute_migration(_conv_fall))


# ===========================================================================
# 5. U3 — read_migration is READ-ONLY (no compute, no fetch)
# ===========================================================================
_net = {"n": 0}


def _boom(*_a, **_k):
    _net["n"] += 1
    raise AssertionError("producer/fetch reached on the migration READ path")


with mock.patch.object(aa, "read_archive", return_value=_conv_fall), \
        mock.patch.object(eqv, "compute_app_fair_value", side_effect=_boom), \
        mock.patch.object(eqv, "fetch_cyclical_band_history", side_effect=_boom), \
        mock.patch.object(eqv, "_fetch_raw", side_effect=_boom):
    _rm = am.read_migration("MU")
check("5.1 read_migration consumes the archive READ-ONLY (no producer/fetch)",
      _net["n"] == 0 and _rm["deteriorating"] is True,
      detail=f"net={_net['n']}/det={_rm['deteriorating']}")


# ===========================================================================
# 6. U3 — thesis_monitor annotation (watch-level only; never changes status)
# ===========================================================================
check("6.1 annotation fires watch on a deteriorating (conviction-falling) readout",
      tm._anchor_migration_annotation(_m) == (True, tm._anchor_migration_annotation(_m)[1])
      and tm._anchor_migration_annotation(_m)[0] is True
      and bool(tm._anchor_migration_annotation(_m)[1]))
check("6.2 annotation does NOT fire on a rising readout",
      tm._anchor_migration_annotation(_mr)[0] is False)
check("6.3 annotation does NOT fire on lone-anchor drift (noise, not signal)",
      tm._anchor_migration_annotation(_ml)[0] is False)
check("6.4 annotation fail-closed on a non-readout",
      tm._anchor_migration_annotation(None) == (False, ""))

# check_holding wires it READ-ONLY: mock the four signal leaves to neutral and the
# archive to a deteriorating fixture; the producer/fetch must NEVER be touched, the
# watch must fire, and thesis_status must stay 'intact' (migration ELEVATES a note,
# it does NOT escalate the status — mirrors the D2 fragility invariant).
_net["n"] = 0
_holding = NS(id="h1", ticker="MU", cost_basis=100.0, horizon="long",
              thesis_text="cyclical recovery", status="active")
with mock.patch.object(tm, "news_signal",
                       return_value={"news_sentiment": "neutral",
                                     "thesis_relevant": False, "key_development": ""}), \
        mock.patch.object(tm, "eps_signal", return_value="unknown"), \
        mock.patch("lib.signal_engine._technical_snapshot", return_value={}), \
        mock.patch.object(aa, "read_archive", return_value=_conv_fall), \
        mock.patch.object(eqv, "compute_app_fair_value", side_effect=_boom), \
        mock.patch.object(eqv, "fetch_cyclical_band_history", side_effect=_boom), \
        mock.patch.object(eqv, "_fetch_raw", side_effect=_boom):
    _res = tm.check_holding(_holding, regime="neutral")
check("6.5 check_holding fires the anchor-migration watch (deteriorating)",
      _res.anchor_migration_watch is True and bool(_res.anchor_migration_note),
      detail=str(_res.anchor_migration_watch))
check("6.6 check_holding migration is READ-ONLY (no producer/fetch reached)",
      _net["n"] == 0, detail=str(_net["n"]))
check("6.7 migration NEVER changes thesis_status (intact stays intact)",
      _res.thesis_status == "intact", detail=_res.thesis_status)
check("6.8 check_holding carries the full deterministic readout",
      isinstance(_res.anchor_migration, dict)
      and _res.anchor_migration.get("consistency") == "conviction")

# control: a non-deteriorating archive -> no watch, status still intact
_net["n"] = 0
with mock.patch.object(tm, "news_signal",
                       return_value={"news_sentiment": "neutral",
                                     "thesis_relevant": False, "key_development": ""}), \
        mock.patch.object(tm, "eps_signal", return_value="unknown"), \
        mock.patch("lib.signal_engine._technical_snapshot", return_value={}), \
        mock.patch.object(aa, "read_archive", return_value=_conv_rise), \
        mock.patch.object(eqv, "compute_app_fair_value", side_effect=_boom), \
        mock.patch.object(eqv, "fetch_cyclical_band_history", side_effect=_boom):
    _res2 = tm.check_holding(_holding, regime="neutral")
check("6.9 control: rising migration -> no watch, status intact",
      _res2.anchor_migration_watch is False and _res2.thesis_status == "intact")


# ===========================================================================
# 7. U2 — snapshot anchor block PARITY (single-vintage, read-only of anchor_cache)
# ===========================================================================
# Warm cache for FRESHX (fresh, within staleness), none for COLDX. Drive the REAL
# rank_opportunities network-free, write the daily snapshot, read it back, and assert
# the serialized anchor block equals its anchor_cache SOURCE (parity must FAIL if the
# block ever drifts from the cache read that drove LONG status).
import lib.relative_strength as rsm  # noqa: E402

_today = _date(2026, 6, 5)
_pool = {"median": 112.5, "mean": 110.0, "high": 130.0, "low": 95.0, "n": 20}
_cache_entry = ac.entry_from_app_fair_value(
    _fv(ticker="FRESHX", mid=110.0, computed_at="2026-06-04T10:00:00+00:00",
        pool=_pool))
_anchor_cache = {"FRESHX": _cache_entry}
_cands = [dict(ticker="FRESHX", short_score=0.2, mid_score=0.3, long_score=0.9,
               candidate_type="FUNNEL", eps_revision_direction="improving",
               valuation_percentile=0.3),
          dict(ticker="COLDX", short_score=0.2, mid_score=0.3, long_score=0.8,
               candidate_type="FUNNEL", eps_revision_direction="improving",
               valuation_percentile=0.3)]
_rs = {"FRESHX": rsm.RelativeStrength("FRESHX", rs_composite=0.6, data_source="live"),
       "COLDX": rsm.RelativeStrength("COLDX", rs_composite=0.6, data_source="live")}

_snap_dir = Path(tempfile.mkdtemp())
with mock.patch("ui_utils.load_ohlcv", return_value=None), \
        mock.patch.object(eqv, "compute_app_fair_value", side_effect=_boom), \
        mock.patch.object(eqv, "fetch_cyclical_band_history", side_effect=_boom), \
        mock.patch.object(eqv, "_fetch_raw", side_effect=_boom):
    _cards = orr.rank_opportunities(
        _cands, rs_map=_rs, earnings_map={}, top_n=2,
        anchor_cache=_anchor_cache, today=_today)
    _path = orr.write_daily_snapshot(_cards, macro_regime="neutral",
                                     date_str="2026-06-05", base_dir=_snap_dir)

_recs = [json.loads(ln) for ln in Path(_path).read_text(encoding="utf-8").splitlines()]
_by_tk = {r["ticker"]: r for r in _recs if not r.get("_meta")}
_fresh_anchor = _by_tk["FRESHX"]["anchor"]
_cold_anchor = _by_tk["COLDX"]["anchor"]

check("7.1 snapshot records carry an 'anchor' block per card",
      "anchor" in _by_tk["FRESHX"] and "anchor" in _by_tk["COLDX"])
check("7.2 fresh anchor block has the canonical key set (no silent extra field)",
      set(_fresh_anchor.keys()) == set(orr.ANCHOR_SNAPSHOT_KEYS),
      detail=str(sorted(_fresh_anchor.keys())))
check("7.3 PARITY: block.fair_value_mid == the anchor_cache source that drove it",
      _fresh_anchor["fair_value_mid"] == _cache_entry["fair_value_mid"],
      detail=f"{_fresh_anchor['fair_value_mid']} vs {_cache_entry['fair_value_mid']}")
check("7.4 PARITY: block.computed_at == cache computed_at (single vintage)",
      _fresh_anchor["computed_at"] == _cache_entry["computed_at"],
      detail=f"{_fresh_anchor['computed_at']} vs {_cache_entry['computed_at']}")
check("7.5 PARITY: block.analyst_pool == cache analyst_pool (persisted for ranking)",
      _fresh_anchor["analyst_pool"] == _cache_entry["analyst_pool"],
      detail=str(_fresh_anchor["analyst_pool"]))
check("7.6 no cached anchor -> honest anchor_not_cached state (no fabricated value)",
      _cold_anchor == {"state": orr.ANCHOR_NOT_CACHED}, detail=str(_cold_anchor))
check("7.7 anchor_cache entry now persists analyst_pool (U2 dependency)",
      _cache_entry.get("analyst_pool") == _pool, detail=str(_cache_entry.get("analyst_pool")))
# F3 — full source-equality for the REMAINING block fields.
check("7.8 PARITY: block.company_type == anchor_cache source",
      _fresh_anchor["company_type"] == _cache_entry["company_type"],
      detail=f"{_fresh_anchor['company_type']} vs {_cache_entry['company_type']}")
check("7.9 PARITY: block.blend_state == anchor_cache source",
      _fresh_anchor["blend_state"] == _cache_entry["blend_state"],
      detail=f"{_fresh_anchor['blend_state']} vs {_cache_entry['blend_state']}")
check("7.10 PARITY: block.caveats == anchor_cache source",
      _fresh_anchor["caveats"] == list(_cache_entry.get("caveats", []) or []),
      detail=f"{_fresh_anchor['caveats']} vs {_cache_entry.get('caveats')}")

# F3 — binding/exclusion completeness (mirrors the §18 canonical-key-set pattern):
# EVERY field in the snapshot anchor block is EITHER bound to a UI surface OR listed
# in the explicit-exclusion set with a documented reason, so a future field added to
# ANCHOR_SNAPSHOT_KEYS forces a surface decision (fails loudly otherwise).
_ANCHOR_BOUND = {
    "fair_value_mid": "drives the LONG-status value band the Cockpit card renders",
}
_ANCHOR_EXCLUDED = {
    "computed_at": "vintage stamp; the card staleness surface is anchor_age_days",
    "company_type": "archive/migration audit field; no per-card Cockpit surface this round",
    "analyst_pool": "migration-source (consumed from the ARCHIVE, not the snapshot block); no per-card surface",
    "blend_state": "archive/migration audit field; degrade display is driven by status, not this block",
    "caveats": "archive/migration audit field; no per-card surface this round",
}
check("7.11 every snapshot anchor-block field is bound OR explicitly excluded",
      set(_ANCHOR_BOUND) | set(_ANCHOR_EXCLUDED) == set(orr.ANCHOR_SNAPSHOT_KEYS)
      and not (set(_ANCHOR_BOUND) & set(_ANCHOR_EXCLUDED)),
      detail=str(set(orr.ANCHOR_SNAPSHOT_KEYS)
                 ^ (set(_ANCHOR_BOUND) | set(_ANCHOR_EXCLUDED))))


# ===========================================================================
# 8. F2 — migration note surfaced in _summary() + bound on the Trading Desk card
# ===========================================================================
# _res / _res2 come from §6 (deteriorating vs rising check_holding runs).
check("8.1 _summary() includes the bilingual migration note when deteriorating",
      _res.anchor_migration_note in _res.summary and bool(_res.anchor_migration_note),
      detail=_res.summary)
check("8.2 _summary() does NOT show the downshift note when not deteriorating",
      "downshifting" not in _res2.summary.lower()
      and not _res2.anchor_migration_watch)
check("8.3 surfacing is watch-level only — thesis_status unchanged (intact)",
      _res.thesis_status == "intact" and _res2.thesis_status == "intact")
# Render-surface binding (source inspection — mirrors the cockpit_rebuild §273
# pattern; full AppTest of pages/9 is out of scope and the 5x AppTest harness is
# pre-existing-red): the Trading Desk order card reads the watch and renders the note.
_src9 = open(os.path.join(_REPO_ROOT, "pages", "9_Trading_Desk.py"),
             encoding="utf-8").read()
check("8.4 Trading Desk order card binds anchor_migration_watch + _note",
      "anchor_migration_watch" in _src9 and "anchor_migration_note" in _src9)


# ===========================================================================
print("\n".join(_failures))
total = PASS + FAIL
print(f"\nAnchor Intelligence v2.3 — anchor historization — {PASS}/{total} checks passed.")
if FAIL:
    sys.exit(1)
print("ALL PASSED.")
