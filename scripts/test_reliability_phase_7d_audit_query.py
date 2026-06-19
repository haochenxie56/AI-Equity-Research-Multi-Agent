#!/usr/bin/env python3
"""
scripts/test_reliability_phase_7d_audit_query.py

Phase 7D Block A — Snapshot Audit Query Interface test suite (pytest, offline).

Every test constructs its snapshot fixtures in a ``tmp_path`` directory; NOTHING
reads the real ``data/snapshots/``. The suite is discriminating: each case goes
RED when the specific bug it guards is present (missing-field defaults, _meta
leakage into the ticker scan, wrong sort, wrong follow-through delta, missing
fragility join, or an audit/live-engine import breach).

Run:
    pytest scripts/test_reliability_phase_7d_audit_query.py -v
"""

from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

# Make the repo root importable (so ``import lib.audit_query`` works under pytest).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
if os.path.join(_REPO_ROOT, "lib") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "lib"))

from lib import audit_query
from lib.audit_query import (
    MetaRecord,
    OpportunityRecord,
    compute_actionable_follow_through,
    compute_fragility_series,
    load_all_opportunities,
    query_status_transitions,
)


# ---------------------------------------------------------------------------
# Fixture builders (in-memory snapshot files)
# ---------------------------------------------------------------------------

def _meta_line(date: str, *, fragility_level: str = "normal",
               fragility_points: int = 0, macro_regime: str = "neutral",
               **extra) -> dict:
    d = {
        "_meta": True,
        "date": date,
        "macro_regime": macro_regime,
        "fragility_level": fragility_level,
        "fragility_points": fragility_points,
        "fragility_raw_level": fragility_level,
        "fragility_triggered": False,
        "fragility_consecutive_raw": 0,
        "hysteresis_source": "rolling",
        "breadth_above_sma20": 0.5,
        "breadth_above_sma50": 0.5,
        "breadth_slope": 0.0,
        "n_candidates": 0,
        "earnings_skipped": [],
    }
    d.update(extra)
    return d


def _ticker_line(date: str, ticker: str, *, status: str = "Watch",
                 status_by_horizon: dict | None = None,
                 short_score: float = 0.0, mid_score: float = 0.0,
                 long_score: float = 0.0, macro_regime: str = "neutral",
                 **extra) -> dict:
    d = {
        "date": date,
        "ticker": ticker,
        "status": status,
        "status_by_horizon": status_by_horizon or {
            "short": status, "mid": status, "long": status},
        "short_score": short_score,
        "mid_score": mid_score,
        "long_score": long_score,
        "short_grade": "B",
        "mid_grade": "B",
        "long_grade": "B",
        "theme": "test_theme",
        "macro_regime": macro_regime,
    }
    d.update(extra)
    return d


def _write_snapshot(base: Path, date: str, meta: dict, records: list[dict]) -> Path:
    """Write one ``opportunities_<YYYYMMDD>.jsonl`` file (line1 _meta + records)."""
    base.mkdir(parents=True, exist_ok=True)
    fname = f"opportunities_{date.replace('-', '')}.jsonl"
    fp = base / fname
    lines = [json.dumps(meta, ensure_ascii=False)]
    lines += [json.dumps(r, ensure_ascii=False) for r in records]
    fp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return fp


# ---------------------------------------------------------------------------
# §7D.1 — OpportunityRecord.from_dict handles missing anchor field
# ---------------------------------------------------------------------------

def test_7d_1_opportunity_record_missing_anchor():
    d = _ticker_line("2026-06-05", "AAAA")
    d.pop("anchor", None)                       # ensure absent
    rec = OpportunityRecord.from_dict(d)
    assert rec.anchor == {"state": "anchor_not_cached"}


# ---------------------------------------------------------------------------
# §7D.2 — OpportunityRecord.from_dict handles missing rs_stale
# ---------------------------------------------------------------------------

def test_7d_2_opportunity_record_missing_rs_stale():
    d = _ticker_line("2026-06-05", "AAAA")
    d.pop("rs_stale", None)
    rec = OpportunityRecord.from_dict(d)
    assert rec.rs_stale is False


# ---------------------------------------------------------------------------
# §7D.3 — MetaRecord.from_dict handles missing earnings_skipped
# ---------------------------------------------------------------------------

def test_7d_3_meta_record_missing_earnings_skipped():
    d = _meta_line("2026-06-05")
    d.pop("earnings_skipped", None)
    rec = MetaRecord.from_dict(d)
    assert rec.earnings_skipped == []


# ---------------------------------------------------------------------------
# §7D.4 — load_all_opportunities skips _meta lines
# ---------------------------------------------------------------------------

def test_7d_4_load_all_opportunities_skips_meta(tmp_path):
    _write_snapshot(tmp_path, "2026-06-05",
                    _meta_line("2026-06-05"),
                    [_ticker_line("2026-06-05", "AAAA"),
                     _ticker_line("2026-06-05", "BBBB")])
    _write_snapshot(tmp_path, "2026-06-06",
                    _meta_line("2026-06-06"),
                    [_ticker_line("2026-06-06", "CCCC"),
                     _ticker_line("2026-06-06", "DDDD")])
    recs = load_all_opportunities(str(tmp_path))
    assert len(recs) == 4
    # No _meta header ever leaks into the ticker scan.
    assert all(r.raw.get("_meta") is not True for r in recs)
    assert {r.ticker for r in recs} == {"AAAA", "BBBB", "CCCC", "DDDD"}


# ---------------------------------------------------------------------------
# §7D.5 — load_all_opportunities sorts by (date, ticker)
# ---------------------------------------------------------------------------

def test_7d_5_load_all_opportunities_sorted(tmp_path):
    # Deliberately out-of-order tickers within each day, days written newest-first.
    _write_snapshot(tmp_path, "2026-06-06",
                    _meta_line("2026-06-06"),
                    [_ticker_line("2026-06-06", "ZZZZ"),
                     _ticker_line("2026-06-06", "MMMM")])
    _write_snapshot(tmp_path, "2026-06-05",
                    _meta_line("2026-06-05"),
                    [_ticker_line("2026-06-05", "YYYY"),
                     _ticker_line("2026-06-05", "AAAA")])
    recs = load_all_opportunities(str(tmp_path))
    keys = [(r.date, r.ticker) for r in recs]
    assert keys == sorted(keys)
    assert keys == [
        ("2026-06-05", "AAAA"), ("2026-06-05", "YYYY"),
        ("2026-06-06", "MMMM"), ("2026-06-06", "ZZZZ"),
    ]


# ---------------------------------------------------------------------------
# §7D.6 — follow_through=True when score improves (and delta is correct)
# ---------------------------------------------------------------------------

def test_7d_6_follow_through_true_on_improvement(tmp_path):
    actionable = {"short": "Actionable Now", "mid": "Watch", "long": "Watch"}
    watch = {"short": "Watch", "mid": "Watch", "long": "Watch"}
    _write_snapshot(tmp_path, "2026-06-05", _meta_line("2026-06-05"),
                    [_ticker_line("2026-06-05", "AAAA",
                                  status_by_horizon=actionable, short_score=0.50)])
    _write_snapshot(tmp_path, "2026-06-06", _meta_line("2026-06-06"),
                    [_ticker_line("2026-06-06", "AAAA",
                                  status_by_horizon=watch, short_score=0.60)])
    _write_snapshot(tmp_path, "2026-06-07", _meta_line("2026-06-07"),
                    [_ticker_line("2026-06-07", "AAAA",
                                  status_by_horizon=watch, short_score=0.65)])
    res = compute_actionable_follow_through(
        horizon="short", window_days=5, score_improvement_threshold=0.05,
        snapshot_dir=str(tmp_path))
    aaaa = [c for c in res["cases"] if c["ticker"] == "AAAA"]
    assert len(aaaa) == 1
    case = aaaa[0]
    assert case["follow_through"] is True
    # Delta is best-in-window (0.65) minus initial (0.50) = 0.15 >= 0.10.
    assert case["initial_score"] == 0.50
    assert case["best_score_in_window"] == 0.65
    assert case["score_delta"] >= 0.10

    # DISCRIMINATING CHECK: if the post-signal scores only nudge to 0.51, the
    # delta (0.01) is below the 0.05 threshold and follow_through MUST be False.
    # This catches an absolute-threshold bug (e.g. comparing best >= threshold
    # instead of best - initial >= threshold).
    _write_snapshot(tmp_path, "2026-06-06", _meta_line("2026-06-06"),
                    [_ticker_line("2026-06-06", "AAAA",
                                  status_by_horizon=watch, short_score=0.51)])
    _write_snapshot(tmp_path, "2026-06-07", _meta_line("2026-06-07"),
                    [_ticker_line("2026-06-07", "AAAA",
                                  status_by_horizon=watch, short_score=0.51)])
    res2 = compute_actionable_follow_through(
        horizon="short", window_days=5, score_improvement_threshold=0.05,
        snapshot_dir=str(tmp_path))
    case2 = [c for c in res2["cases"] if c["ticker"] == "AAAA"][0]
    assert abs(case2["score_delta"] - 0.01) < 1e-9
    assert case2["follow_through"] is False


# ---------------------------------------------------------------------------
# §7D.7 — insufficient_history when signal is at the edge of available data
# ---------------------------------------------------------------------------

def test_7d_7_insufficient_history_at_edge(tmp_path):
    watch = {"short": "Watch", "mid": "Watch", "long": "Watch"}
    actionable = {"short": "Actionable Now", "mid": "Watch", "long": "Watch"}
    _write_snapshot(tmp_path, "2026-06-05", _meta_line("2026-06-05"),
                    [_ticker_line("2026-06-05", "AAAA",
                                  status_by_horizon=watch, short_score=0.40)])
    _write_snapshot(tmp_path, "2026-06-06", _meta_line("2026-06-06"),
                    [_ticker_line("2026-06-06", "AAAA",
                                  status_by_horizon=watch, short_score=0.40)])
    # Signal on the LAST day → no snapshot days exist after it.
    _write_snapshot(tmp_path, "2026-06-07", _meta_line("2026-06-07"),
                    [_ticker_line("2026-06-07", "AAAA",
                                  status_by_horizon=actionable, short_score=0.40)])
    res = compute_actionable_follow_through(
        horizon="short", window_days=5, score_improvement_threshold=0.05,
        snapshot_dir=str(tmp_path))
    assert res["insufficient_history"] is True
    case = [c for c in res["cases"] if c["signal_date"] == "2026-06-07"][0]
    assert case["dates_in_window"] == []
    assert case["follow_through"] is False


# ---------------------------------------------------------------------------
# §7D.8 — compute_fragility_series returns sorted ascending
# ---------------------------------------------------------------------------

def test_7d_8_fragility_series_sorted(tmp_path):
    # Write three days out of chronological order.
    _write_snapshot(tmp_path, "2026-06-07",
                    _meta_line("2026-06-07", fragility_level="high",
                               fragility_points=7), [])
    _write_snapshot(tmp_path, "2026-06-05",
                    _meta_line("2026-06-05", fragility_level="normal",
                               fragility_points=1), [])
    _write_snapshot(tmp_path, "2026-06-06",
                    _meta_line("2026-06-06", fragility_level="elevated",
                               fragility_points=4), [])
    series = compute_fragility_series(str(tmp_path))
    dates = [e["date"] for e in series]
    assert dates == ["2026-06-05", "2026-06-06", "2026-06-07"]
    assert dates == sorted(dates)
    # Values travel with their date (not just the order).
    by_date = {e["date"]: e for e in series}
    assert by_date["2026-06-07"]["fragility_level"] == "high"
    assert by_date["2026-06-05"]["fragility_points"] == 1


# ---------------------------------------------------------------------------
# §7D.9 — query_status_transitions joins fragility_level from _meta
# ---------------------------------------------------------------------------

def test_7d_9_status_transitions_joins_fragility(tmp_path):
    _write_snapshot(tmp_path, "2026-06-05",
                    _meta_line("2026-06-05", fragility_level="elevated"),
                    [_ticker_line("2026-06-05", "AAAA",
                                  status_by_horizon={"short": "Actionable Now",
                                                     "mid": "Watch", "long": "Watch"},
                                  short_score=0.5)])
    _write_snapshot(tmp_path, "2026-06-06",
                    _meta_line("2026-06-06", fragility_level="high"),
                    [_ticker_line("2026-06-06", "AAAA",
                                  status_by_horizon={"short": "Watch", "mid": "Watch",
                                                     "long": "Watch"},
                                  short_score=0.6)])
    rows = query_status_transitions("AAAA", snapshot_dir=str(tmp_path))
    assert len(rows) == 2
    by_date = {r["date"]: r for r in rows}
    assert by_date["2026-06-05"]["fragility_level"] == "elevated"
    assert by_date["2026-06-06"]["fragility_level"] == "high"
    assert by_date["2026-06-05"]["status_short"] == "Actionable Now"


# ---------------------------------------------------------------------------
# §7D.10 — audit_query has no live-engine import (audit/live separation)
# ---------------------------------------------------------------------------

def test_7d_10_no_live_engine_imports():
    # (a) Static check: parse the module source; no import statement may reference
    # signal_engine, and opportunity_ranker may be imported ONLY for the allowed
    # read helper load_ticker_series (never a ranking/scoring function).
    src_path = Path(audit_query.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    allowed_from_ranker = {"load_ticker_series"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "signal_engine" not in alias.name, \
                    f"forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "signal_engine" not in mod, f"forbidden import-from: {mod}"
            if mod.endswith("opportunity_ranker"):
                names = {a.name for a in node.names}
                assert names <= allowed_from_ranker, \
                    f"opportunity_ranker import beyond read helpers: {names}"

    # (b) Runtime check (spec's simple approach): importing audit_query must not
    # have pulled the live signal engine into the process.
    assert not any("signal_engine" in m for m in sys.modules), \
        "signal_engine present in sys.modules after importing audit_query"


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-v"]))
