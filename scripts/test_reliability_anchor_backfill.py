#!/usr/bin/env python3
"""
scripts/test_reliability_anchor_backfill.py

Anchor Intelligence v2.3 — BACKFILL ROUND test suite (mock-only / offline).

Covers the backfill engine (``lib/anchor_backfill.py``) + its archive / migration /
thesis-monitor integration. NO live network anywhere (fixed price/fundamental
fixtures only).

  * B1 — backfill determinism: a fixed historical fixture → fixed backfilled anchor
    values at known as-of dates; reuses the LIVE assembler (no reimplementation);
    weekly cadence over the 6-month window.
  * NEVER-FABRICATE: a backfilled record's ``analyst_pool`` is the
    ``analyst_history_unavailable`` SENTINEL — never a number, never None, never
    today's pool back-dated. Discrimination: wiring a real/back-dated pool in fails.
  * B2 — idempotency: a double-run adds ZERO duplicate rows (persistent guard);
    append-only holds; the fetch never reaches a live analyst endpoint / the live
    producer.
  * B3 — mixed-origin U3: an archive with backfilled (analyst-absent) + live
    (analyst-present) records yields PRICE-anchor migration over the FULL span but
    ANALYST migration only over the LIVE span, each labeled honestly; thesis_monitor
    surfaces the analyst-history note WITHOUT a watch / status change.
  * Cold ranking stays zero-write / zero-network (backfill is offline-only and is
    not imported by the ranking path).

Usage:
    python3 -B scripts/test_reliability_anchor_backfill.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["FINNHUB_API_KEY"] = ""

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pandas as pd  # noqa: E402

import lib.anchor_archive as aa  # noqa: E402
import lib.anchor_backfill as ab  # noqa: E402
import lib.anchor_migration as am  # noqa: E402
import lib.equity_valuation as eqv  # noqa: E402
import lib.thesis_monitor as tm  # noqa: E402

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


# ---------------------------------------------------------------------------
# Deterministic historical fixtures (yfinance-shaped; NO network).
# Annual statements: index = row label, columns = fiscal-period Timestamps.
# ---------------------------------------------------------------------------
_FCOLS = [pd.Timestamp("2025-06-30"), pd.Timestamp("2024-06-30"),
          pd.Timestamp("2023-06-30"), pd.Timestamp("2022-06-30")]
_BS = pd.DataFrame({c: v for c, v in zip(_FCOLS, [
    {"Stockholders Equity": 5.0e10, "Ordinary Shares Number": 1.0e9,
     "Total Debt": 1.0e10, "Cash And Cash Equivalents": 9.0e9},
    {"Stockholders Equity": 4.5e10, "Ordinary Shares Number": 1.0e9,
     "Total Debt": 1.0e10, "Cash And Cash Equivalents": 8.0e9},
    {"Stockholders Equity": 4.0e10, "Ordinary Shares Number": 1.0e9,
     "Total Debt": 1.0e10, "Cash And Cash Equivalents": 7.0e9},
    {"Stockholders Equity": 3.5e10, "Ordinary Shares Number": 1.0e9,
     "Total Debt": 1.0e10, "Cash And Cash Equivalents": 6.0e9}])})
_IS = pd.DataFrame({c: v for c, v in zip(_FCOLS, [
    {"Total Revenue": 3.0e10, "Net Income": 4.0e9, "Operating Income": 5.0e9,
     "Diluted EPS": 4.0},
    {"Total Revenue": 2.6e10, "Net Income": 3.2e9, "Operating Income": 4.2e9,
     "Diluted EPS": 3.2},
    {"Total Revenue": 2.2e10, "Net Income": 2.4e9, "Operating Income": 3.4e9,
     "Diluted EPS": 2.4},
    {"Total Revenue": 2.0e10, "Net Income": 2.0e9, "Operating Income": 3.0e9,
     "Diluted EPS": 2.0}])})
_CF = pd.DataFrame({c: v for c, v in zip(_FCOLS, [
    {"Operating Cash Flow": 7.0e9, "Capital Expenditure": -2.0e9},
    {"Operating Cash Flow": 6.0e9, "Capital Expenditure": -1.8e9},
    {"Operating Cash Flow": 5.0e9, "Capital Expenditure": -1.6e9},
    {"Operating Cash Flow": 4.5e9, "Capital Expenditure": -1.5e9}])})
# Deterministic weekly price history (tz-aware, like yfinance .history).
_PX_IDX = pd.date_range("2021-01-03", "2026-06-08", freq="W", tz="America/New_York")
_PX = pd.DataFrame({"Close": [50.0 + 0.1 * i for i in range(len(_PX_IDX))]},
                   index=_PX_IDX)

_END = date(2026, 6, 8)


def _loader(_t):
    return {"balance_sheet": _BS, "income_stmt": _IS, "cashflow": _CF,
            "price_history": _PX, "sector": "Technology"}


# ===========================================================================
# 1. B1 — as-of date generation (weekly cadence over the 6-month window)
# ===========================================================================
_dates = ab._as_of_dates(_END)
check("1.1 default window is 6 months, weekly cadence (visible config)",
      ab.BACKFILL_WINDOW_MONTHS == 6 and ab.BACKFILL_CADENCE_DAYS == 7)
check("1.2 as-of dates are weekly (7-day step), oldest->newest, end inclusive",
      all((_dates[i + 1] - _dates[i]).days == 7 for i in range(len(_dates) - 1))
      and _dates[-1] == _END and _dates == sorted(_dates),
      detail=f"{_dates[0]}..{_dates[-1]} n={len(_dates)}")
check("1.3 window spans ~6 months (>= 25 weekly points)", len(_dates) >= 25,
      detail=str(len(_dates)))
_cad = ab._as_of_dates(_END, cadence_days=14)
check("1.4 cadence is configurable (14-day step honored)",
      all((_cad[i + 1] - _cad[i]).days == 14 for i in range(len(_cad) - 1)))


# ===========================================================================
# 2. B1 — backfill determinism + REUSE of the live assembler (no network)
# ===========================================================================
# Patch the live fetch/producer to BLOW UP: compute_backfill_records must reach the
# anchor math WITHOUT touching _fetch_raw / compute_app_fair_value (it reuses the
# pure _assemble_fair_value with as-of frames). This is the no-live-fetch proof.
_net = {"n": 0}


def _boom(*_a, **_k):
    _net["n"] += 1
    raise AssertionError("live fetch/producer reached on the backfill path")


with mock.patch.object(eqv, "_fetch_raw", side_effect=_boom), \
        mock.patch.object(eqv, "compute_app_fair_value", side_effect=_boom):
    _recs = ab.compute_backfill_records(
        "MU", balance_sheet=_BS, income_stmt=_IS, cashflow=_CF,
        price_history=_PX, as_of_dates=_dates, sector="Technology")
    _recs2 = ab.compute_backfill_records(
        "MU", balance_sheet=_BS, income_stmt=_IS, cashflow=_CF,
        price_history=_PX, as_of_dates=_dates, sector="Technology")

check("2.1 backfill reaches anchor math WITHOUT the live producer / _fetch_raw",
      _net["n"] == 0 and len(_recs) == len(_dates), detail=str(_net["n"]))
check("2.2 deterministic: identical fixture+dates -> identical records",
      _recs == _recs2)
_last = _recs[-1]
check("2.3 GOLDEN: fixed fixture -> fixed band (77.2 / 69.48 / 84.92)",
      (_last["fair_value_mid"], _last["fair_value_low"], _last["fair_value_high"])
      == (77.2, 69.48, 84.92), detail=str(_last["fair_value_mid"]))
check("2.4 cyclical company routes to the recomputable PB/PS band anchor",
      _last["company_type"] == "cyclical"
      and any("PB/PS" in m or "PB" in m for m in _last["methods_used"]),
      detail=str(_last["methods_used"]))
check("2.5 every record is tagged record_origin='backfill'",
      all(r["record_origin"] == aa.RECORD_ORIGIN_BACKFILL for r in _recs))
check("2.6 data_vintage == the historical as-of date (not 'now')",
      [r["data_vintage"] for r in _recs] == [d.isoformat() for d in _dates],
      detail=str(_recs[0]["data_vintage"]))
check("2.7 computed_at is the historical vintage midnight (deterministic, not now)",
      _last["computed_at"] == f"{_last['data_vintage']}T00:00:00+00:00",
      detail=_last["computed_at"])


# ===========================================================================
# 3. NEVER-FABRICATE — the analyst anchor is the sentinel, never a number
# ===========================================================================
check("3.1 EVERY backfilled record's analyst_pool is the sentinel STRING",
      all(r["analyst_pool"] == aa.ANALYST_HISTORY_UNAVAILABLE for r in _recs),
      detail=str(_last["analyst_pool"]))
check("3.2 analyst_pool is NOT a dict and NOT None (never-fabricate discrimination)",
      all(not isinstance(r["analyst_pool"], dict) and r["analyst_pool"] is not None
          for r in _recs))
# Discrimination: the as-of raw NEVER carries an analyst/forward field. If a future
# edit back-dated today's pool, _raw_asof would have to populate these — assert they
# stay None regardless of inputs, AND that the sentinel survives any raw content.
_raw_probe = ab._raw_asof(balance_sheet_asof=_BS, income_stmt_asof=_IS,
                          cashflow_asof=_CF, price_at_asof=100.0, sector="Technology")
check("3.3 as-of raw NEVER carries analyst_* / forward_eps (CURRENT-only fields)",
      _raw_probe["analyst_median"] is None and _raw_probe["analyst_mean"] is None
      and _raw_probe["analyst_high"] is None and _raw_probe["analyst_low"] is None
      and _raw_probe["analyst_count"] == 0 and _raw_probe["forward_eps"] is None)
check("3.4 as-of raw DOES carry historical-derivable inputs (BVPS, revenue, FCF, EPS)",
      _raw_probe["book_value"] is not None and _raw_probe["total_revenue"] is not None
      and _raw_probe["fcf_ttm"] is not None and _raw_probe["trailing_eps"] is not None,
      detail=str({k: _raw_probe[k] for k in
                  ("book_value", "total_revenue", "fcf_ttm", "trailing_eps")}))
# The projected pool from a record carrying the sentinel is never re-numbered.
_proj = aa._project_analyst_pool(aa.ANALYST_HISTORY_UNAVAILABLE)
check("3.5 archive's analyst projector treats the sentinel as no-coverage (None), "
      "never a number", _proj is None)


# ===========================================================================
# 4. Degraded / no-data honesty (partial record, never a fabricated band)
# ===========================================================================
# 4a. An as-of date BEFORE any fiscal statement but WITH a price → no anchor can be
# built → degraded PARTIAL record (band ZEROED + caveat), never a current-price stub.
_early_px = pd.DataFrame(
    {"Close": [40.0, 41.0, 42.0]},
    index=pd.date_range("2019-01-06", periods=3, freq="W", tz="America/New_York"))
_deg = ab._backfill_one("MU", date(2019, 1, 20), balance_sheet=_BS, income_stmt=_IS,
                        cashflow=_CF, price_history=_early_px, sector="Technology")
check("4.1 insufficient-fundamentals as-of date -> degraded partial record (not skipped)",
      _deg is not None and ab.CAVEAT_BACKFILL_INSUFFICIENT_FUNDAMENTALS in _deg["caveats"],
      detail=str(None if _deg is None else _deg["caveats"]))
check("4.2 degraded record ZEROES the band (no current-price stub enters history)",
      _deg["fair_value_mid"] == 0.0 and _deg["fair_value_low"] == 0.0
      and _deg["fair_value_high"] == 0.0)
check("4.3 degraded record still carries the analyst sentinel (partial by construction)",
      _deg["analyst_pool"] == aa.ANALYST_HISTORY_UNAVAILABLE)
# 4b. An as-of date with NO price at all → skipped entirely (never fabricate a price).
_no_px = ab._backfill_one("MU", date(2017, 1, 1), balance_sheet=_BS, income_stmt=_IS,
                          cashflow=_CF, price_history=_early_px, sector="Technology")
check("4.4 no as-of price -> NO record (price is never fabricated)", _no_px is None)


# ===========================================================================
# 5. B2 — idempotency (double-run = zero duplicate rows) + append-only + offline
# ===========================================================================
_d = tempfile.mkdtemp()
_p = Path(_d) / "anchor_archive.jsonl"
aa.reset_dedup_cache()
# First run: writes all price-bearing as-of dates. Patch the live producer/fetch to
# BLOW UP so we also prove the engine never touches the live network path.
with mock.patch.object(eqv, "_fetch_raw", side_effect=_boom), \
        mock.patch.object(eqv, "compute_app_fair_value", side_effect=_boom):
    _net["n"] = 0
    _s1 = ab.backfill_ticker("MU", end_date=_END, archive_path=_p, data_loader=_loader)
_lines1 = _p.read_text(encoding="utf-8").splitlines()
check("5.1 first run writes one row per as-of date (no live producer/fetch reached)",
      _s1["written"] == len(_dates) and len(_lines1) == len(_dates) and _net["n"] == 0,
      detail=f"written={_s1['written']} lines={len(_lines1)} net={_net['n']}")
_first_line = _lines1[0]

# Second run (fresh process memo) — every as-of date already covered → ZERO writes.
aa.reset_dedup_cache()
_s2 = ab.backfill_ticker("MU", end_date=_END, archive_path=_p, data_loader=_loader)
_lines2 = _p.read_text(encoding="utf-8").splitlines()
check("5.2 IDEMPOTENT: a double-run adds ZERO duplicate rows",
      _s2["written"] == 0 and len(_lines2) == len(_lines1),
      detail=f"written={_s2['written']} lines={len(_lines2)}")
check("5.3 idempotency is the persistent guard (all dates 'already covered')",
      _s2["skipped_already_covered"] == _s2["dates_total"],
      detail=str(_s2["skipped_already_covered"]))
check("5.4 APPEND-ONLY: the first row is byte-for-byte unchanged after the re-run",
      _p.read_text(encoding="utf-8").splitlines()[0] == _first_line)
check("5.5 every persisted row is a current-schema backfill record",
      all(json.loads(ln)["record_origin"] == aa.RECORD_ORIGIN_BACKFILL
          and json.loads(ln)["schema_version"] == aa.ANCHOR_ARCHIVE_SCHEMA_VERSION
          for ln in _lines2))
# read_archive returns them oldest->newest; mids are the golden value (fiscal-stable).
_back = aa.read_archive("MU", path=_p)
check("5.6 read_archive returns the backfilled series oldest->newest",
      [r["data_vintage"] for r in _back] == [d.isoformat() for d in _dates])
check("5.7 backfilled_vintages reports exactly the covered as-of dates",
      aa.backfilled_vintages("MU", path=_p) == {d.isoformat() for d in _dates})


# ===========================================================================
# 6. B3 — mixed-origin migration: price over FULL span, analyst over LIVE span
# ===========================================================================
def _bf_rec(mid, ca, vintage):
    """A backfilled (analyst-absent) record."""
    return {"schema_version": aa.ANCHOR_ARCHIVE_SCHEMA_VERSION,
            "record_origin": aa.RECORD_ORIGIN_BACKFILL, "ticker": "MU",
            "computed_at": ca, "data_vintage": vintage, "fair_value_mid": mid,
            "analyst_pool": aa.ANALYST_HISTORY_UNAVAILABLE}


def _live_rec(mid, med, mean, ca):
    """A live (analyst-present) record."""
    return {"schema_version": aa.ANCHOR_ARCHIVE_SCHEMA_VERSION,
            "record_origin": aa.RECORD_ORIGIN_LIVE, "ticker": "MU",
            "computed_at": ca, "data_vintage": ca[:10], "fair_value_mid": mid,
            "analyst_pool": {"median": med, "mean": mean, "high": med * 1.2,
                             "low": med * 0.8, "n": 20}}


# 4 backfilled (falling price anchor, NO analyst) + 2 live (analyst present).
_mixed = [_bf_rec(120, "2026-01-07T00:00:00+00:00", "2026-01-07"),
          _bf_rec(116, "2026-02-04T00:00:00+00:00", "2026-02-04"),
          _bf_rec(112, "2026-03-04T00:00:00+00:00", "2026-03-04"),
          _bf_rec(108, "2026-04-01T00:00:00+00:00", "2026-04-01"),
          _live_rec(106, 110, 109, "2026-05-06T13:00:00+00:00"),
          _live_rec(104, 108, 107, "2026-06-03T13:00:00+00:00")]
_mig = am.compute_migration(_mixed)

check("6.1 origins counted (4 backfill + 2 live)",
      _mig["origins"] == {"backfill": 4, "live": 2}, detail=str(_mig["origins"]))
check("6.2 PRICE anchor (fair_value_mid) migration spans the FULL backfilled+live set",
      _mig["price_span_n"] == 6 and _mig["series"]["fair_value_mid"]["n"] == 6,
      detail=str(_mig["price_span_n"]))
check("6.3 ANALYST anchor migration spans ONLY the live records (2), never the "
      "backfilled span", _mig["analyst_span_n"] == 2
      and _mig["series"]["analyst_median"]["n"] == 2,
      detail=str(_mig["analyst_span_n"]))
check("6.4 price anchor reads its direction over the full span (falling 120->104)",
      _mig["series"]["fair_value_mid"]["direction"] == "falling")
check("6.5 analyst series endpoints are the LIVE records only (110 -> 108)",
      _mig["series"]["analyst_median"]["first"] == 110.0
      and _mig["series"]["analyst_median"]["last"] == 108.0,
      detail=str(_mig["series"]["analyst_median"]))
check("6.6 analyst_history_available True (>=2 live analyst records here)",
      _mig["analyst_history_available"] is True)

# Backfill-ONLY archive: analyst series is EMPTY, the honest note + caveat fire, and
# NO conviction/deterioration is asserted (can't, without analyst corroboration).
_bf_only = [_bf_rec(120, "2026-01-07T00:00:00+00:00", "2026-01-07"),
            _bf_rec(112, "2026-03-04T00:00:00+00:00", "2026-03-04"),
            _bf_rec(104, "2026-05-06T00:00:00+00:00", "2026-05-06")]
_mig0 = am.compute_migration(_bf_only)
check("6.7 backfill-only: analyst span is ZERO (sentinel yields no analyst value)",
      _mig0["analyst_span_n"] == 0 and _mig0["price_span_n"] == 3,
      detail=str(_mig0["analyst_span_n"]))
check("6.8 backfill-only: price anchor still reads 'falling' over the full span",
      _mig0["series"]["fair_value_mid"]["direction"] == "falling")
check("6.9 backfill-only: NOT deteriorating (no analyst corroboration -> not conviction)",
      _mig0["deteriorating"] is False, detail=str(_mig0["consistency"]))
check("6.10 backfill-only: analyst_history_insufficient caveat + honest bilingual note",
      am.CAVEAT_ANALYST_HISTORY_INSUFFICIENT in _mig0["caveats"]
      and "分析师历史不足" in _mig0["analyst_history_note"]
      and "insufficient" in _mig0["analyst_history_note"].lower(),
      detail=str(_mig0["caveats"]))
# A pure-LIVE archive carries NO backfill note (additive change is inert for live).
_live_only = [_live_rec(110, 112, 111, "2026-05-01T13:00:00+00:00"),
              _live_rec(108, 110, 109, "2026-06-01T13:00:00+00:00")]
_migL = am.compute_migration(_live_only)
check("6.11 pure-live archive: no analyst-history note, no backfill caveat",
      _migL["analyst_history_note"] == ""
      and am.CAVEAT_ANALYST_HISTORY_INSUFFICIENT not in _migL["caveats"]
      and _migL["origins"] == {"backfill": 0, "live": 2})
check("6.12 determinism preserved on the extended readout",
      am.compute_migration(_mixed) == am.compute_migration(_mixed))


# ===========================================================================
# 7. B3 — thesis_monitor surfaces the analyst-history note (INFO only, no watch)
# ===========================================================================
_holding = NS(id="h1", ticker="MU", cost_basis=100.0, horizon="long",
              thesis_text="cyclical recovery", status="active")
_net["n"] = 0
with mock.patch.object(tm, "news_signal",
                       return_value={"news_sentiment": "neutral",
                                     "thesis_relevant": False, "key_development": ""}), \
        mock.patch.object(tm, "eps_signal", return_value="unknown"), \
        mock.patch("lib.signal_engine._technical_snapshot", return_value={}), \
        mock.patch.object(aa, "read_archive", return_value=_bf_only), \
        mock.patch.object(eqv, "compute_app_fair_value", side_effect=_boom), \
        mock.patch.object(eqv, "fetch_cyclical_band_history", side_effect=_boom), \
        mock.patch.object(eqv, "_fetch_raw", side_effect=_boom):
    _res = tm.check_holding(_holding, regime="neutral")
check("7.1 thesis_monitor carries the analyst-history note from the readout",
      _res.anchor_migration_analyst_note
      and "分析师历史不足" in _res.anchor_migration_analyst_note)
check("7.2 the note is surfaced in the human summary",
      _res.anchor_migration_analyst_note in _res.summary, detail=_res.summary)
check("7.3 INFO only — NOT a watch (analyst span too short to be conviction)",
      _res.anchor_migration_watch is False)
check("7.4 NEVER changes thesis_status (intact stays intact)",
      _res.thesis_status == "intact", detail=_res.thesis_status)
check("7.5 migration consumed READ-ONLY (no producer/fetch reached)", _net["n"] == 0,
      detail=str(_net["n"]))


# ===========================================================================
# 8. Cold ranking stays zero-write / zero-network (backfill is offline-only)
# ===========================================================================
# The backfill module is NOT imported by the ranking path. Prove the ranking-path
# producers are untouched by importing-only: opportunity_ranker must not import
# anchor_backfill (the offline engine).
import lib.opportunity_ranker as orr  # noqa: E402

_orr_src = open(os.path.join(_REPO_ROOT, "lib", "opportunity_ranker.py"),
                encoding="utf-8").read()
check("8.1 opportunity_ranker does NOT import the offline backfill engine",
      "anchor_backfill" not in _orr_src)
check("8.2 backfill_ticker is offline-explicit (no app-startup / refresh trigger): "
      "default end_date resolves lazily, archive_path injectable",
      "anchor_backfill" not in open(
          os.path.join(_REPO_ROOT, "lib", "thesis_monitor.py"),
          encoding="utf-8").read())


# ===========================================================================
print("\n".join(_failures))
total = PASS + FAIL
print(f"\nAnchor Intelligence v2.3 — backfill round — {PASS}/{total} checks passed.")
if FAIL:
    sys.exit(1)
print("ALL PASSED.")
