"""Phase 7D Block A — Snapshot Audit Query Interface (pure reader).

This module is a **read-only** query layer over the daily opportunity snapshots
persisted under ``data/snapshots/opportunities_YYYYMMDD.jsonl``. It answers audit
questions ("did an 'Actionable Now' signal follow through?", "how has fragility
evolved?") by re-reading the snapshot audit trail — it NEVER recomputes a live
signal.

ISOLATION / INVARIANT (ROADMAP): the audit track (snapshot reads) and the live
signal track (rolling recomputation) must never be mixed. This module therefore
imports **no live engine** — not ``lib.signal_engine``, not any ranking/scoring
or regime-classification path, not ``market_internals`` compute functions, and
nothing that touches the network. It is allowed to reuse exactly two existing
snapshot **read helpers**:

  * ``lib.opportunity_ranker.load_ticker_series`` — per-ticker cross-day series.
  * ``lib.market_internals.read_recent_meta``     — per-day ``_meta`` headers.

Both are pure file readers (verified: importing them pulls in no signal engine).
Every read in this module is fail-closed: a malformed file is logged and skipped,
never raised.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Read helpers only (no ranking/scoring/regime path is touched). See module
# docstring for why these two imports do not breach the audit/live separation.
from lib.opportunity_ranker import load_ticker_series
from lib.market_internals import read_recent_meta

_LOG = logging.getLogger(__name__)

# A limit large enough to mean "all history" for read_recent_meta, which is
# otherwise capped at its default of 10 most-recent days.
_ALL_HISTORY_LIMIT = 100_000

DEFAULT_SNAPSHOT_DIR = "data/snapshots"


# ===========================================================================
# Schema types — typed wrappers tolerant of additive schema drift across the
# 8-file history (``anchor`` absent in 3 earliest files, ``rs_stale`` /
# ``earnings_skipped`` absent in the earliest). Every field uses ``.get()`` with
# a safe default; the full original dict is always retained as ``raw``.
# ===========================================================================

@dataclass
class OpportunityRecord:
    """Typed wrapper for a per-ticker snapshot record (lines 2+ of a file)."""

    date: str
    ticker: str
    status: str                    # flat status, fallback only / 单一状态（兜底）
    status_by_horizon: dict        # authoritative / 权威：{"short":…,"mid":…,"long":…}
    short_score: float
    mid_score: float
    long_score: float
    short_grade: str
    mid_grade: str
    long_grade: str
    theme: str
    macro_regime: str
    signal_strength: Optional[str]
    rs: Optional[float]
    rs_stale: bool                 # default False if missing / 缺失时默认 False
    anchor: dict                   # default {"state":"anchor_not_cached"} if missing
    blockers: list
    raw: dict                      # always store the full original dict / 始终保留原始记录

    @classmethod
    def from_dict(cls, d: dict) -> "OpportunityRecord":
        return cls(
            date=d["date"],
            ticker=d["ticker"],
            status=d.get("status", ""),
            status_by_horizon=d.get("status_by_horizon", {}),
            short_score=d.get("short_score", 0.0),
            mid_score=d.get("mid_score", 0.0),
            long_score=d.get("long_score", 0.0),
            short_grade=d.get("short_grade", ""),
            mid_grade=d.get("mid_grade", ""),
            long_grade=d.get("long_grade", ""),
            theme=d.get("theme", ""),
            macro_regime=d.get("macro_regime", ""),
            signal_strength=d.get("signal_strength"),
            rs=d.get("rs"),
            rs_stale=d.get("rs_stale", False),
            anchor=d.get("anchor", {"state": "anchor_not_cached"}),
            blockers=d.get("blockers", []),
            raw=d,
        )


@dataclass
class MetaRecord:
    """Typed wrapper for a ``_meta`` snapshot record (line 1 of a file)."""

    date: str
    macro_regime: str
    fragility_level: str           # normal / elevated / high
    fragility_points: int
    fragility_raw_level: str
    fragility_triggered: bool
    fragility_consecutive_raw: int
    hysteresis_source: str
    breadth_above_sma20: Optional[float]
    breadth_above_sma50: Optional[float]
    breadth_slope: Optional[float]
    n_candidates: int
    earnings_skipped: list         # default [] if missing (absent in 20260605)
    raw: dict
    # Macro regime context (deterministic classify_regime outputs). Additive — old
    # snapshots predating these keys parse cleanly via the from_dict defaults below.
    # Declared after ``raw`` so the defaults satisfy dataclass field-ordering without
    # touching any existing (non-default) field.
    key_signals: list = field(default_factory=list)
    opportunity_posture: str = ""
    confidence: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "MetaRecord":
        return cls(
            date=d["date"],
            macro_regime=d.get("macro_regime", ""),
            fragility_level=d.get("fragility_level", "normal"),
            fragility_points=d.get("fragility_points", 0),
            fragility_raw_level=d.get("fragility_raw_level", "normal"),
            fragility_triggered=d.get("fragility_triggered", False),
            fragility_consecutive_raw=d.get("fragility_consecutive_raw", 0),
            hysteresis_source=d.get("hysteresis_source", ""),
            breadth_above_sma20=d.get("breadth_above_sma20"),
            breadth_above_sma50=d.get("breadth_above_sma50"),
            breadth_slope=d.get("breadth_slope"),
            n_candidates=d.get("n_candidates", 0),
            earnings_skipped=d.get("earnings_skipped", []),
            raw=d,
            key_signals=d.get("key_signals", []),
            opportunity_posture=d.get("opportunity_posture", ""),
            confidence=d.get("confidence", ""),
        )


# ===========================================================================
# Loaders
# ===========================================================================

def load_all_meta(snapshot_dir: str = DEFAULT_SNAPSHOT_DIR) -> list[MetaRecord]:
    """Return all ``_meta`` records sorted ascending by date.

    Reuses ``read_recent_meta`` (a pure ``_meta``-header reader) with a large
    limit to pull the entire history rather than the default 10 most-recent days.
    Fail-closed: any record that lacks a ``date`` or fails to wrap is skipped.
    """
    try:
        raw_metas = read_recent_meta(snapshot_dir, before_date=None,
                                     limit=_ALL_HISTORY_LIMIT)
    except Exception as exc:  # noqa: BLE001 — never raise from a snapshot read
        _LOG.warning("load_all_meta: read_recent_meta failed: %s", exc)
        return []
    out: list[MetaRecord] = []
    for d in raw_metas or []:
        if not isinstance(d, dict) or "date" not in d:
            _LOG.warning("load_all_meta: skipping malformed _meta record")
            continue
        try:
            out.append(MetaRecord.from_dict(d))
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("load_all_meta: skipping unwrappable _meta record: %s", exc)
            continue
    out.sort(key=lambda m: m.date)
    return out


def load_all_opportunities(
    snapshot_dir: str = DEFAULT_SNAPSHOT_DIR,
) -> list[OpportunityRecord]:
    """Return ALL per-ticker records across ALL snapshot days, sorted by
    ``(date, ticker)``.

    Globs ``opportunities_*.jsonl``, reads each file line by line, skips the
    ``_meta`` header line, and wraps each ticker line with
    ``OpportunityRecord.from_dict``. NOT built on ``load_ticker_series`` (which is
    per-ticker); this is the cross-ticker scan.

    Fail-closed at two granularities: an unreadable/garbled FILE is logged and
    skipped whole; within a readable file, a single malformed LINE is logged and
    skipped without dropping the rest of the file.
    """
    base = Path(snapshot_dir)
    out: list[OpportunityRecord] = []
    if not base.exists():
        return out
    try:
        files = sorted(base.glob("opportunities_*.jsonl"))
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("load_all_opportunities: glob failed in %s: %s", base, exc)
        return out
    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 — skip an unreadable day, never raise
            _LOG.warning("load_all_opportunities: skipping unreadable file %s: %s",
                         fp, exc)
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception as exc:  # noqa: BLE001 — skip a garbled line
                _LOG.warning("load_all_opportunities: skipping garbled line in %s: %s",
                             fp, exc)
                continue
            if not isinstance(rec, dict):
                continue
            # Skip the line-1 market header; ticker records carry no _meta marker.
            if rec.get("_meta"):
                continue
            if "ticker" not in rec or "date" not in rec:
                continue
            try:
                out.append(OpportunityRecord.from_dict(rec))
            except Exception as exc:  # noqa: BLE001
                _LOG.warning("load_all_opportunities: skipping unwrappable record "
                             "in %s: %s", fp, exc)
                continue
    out.sort(key=lambda r: (r.date, r.ticker))
    return out


# ===========================================================================
# Queries
# ===========================================================================

def query_status_transitions(
    ticker: str,
    snapshot_dir: str = DEFAULT_SNAPSHOT_DIR,
) -> list[dict]:
    """Return the status history for a single ticker across all snapshot days.

    Built on ``load_ticker_series`` (the per-ticker read primitive). The
    ``fragility_level`` for each day is joined in from that day's ``_meta`` record
    (``""`` when no ``_meta`` exists for the date). Sorted ascending by date.
    """
    try:
        series = load_ticker_series(ticker, base_dir=Path(snapshot_dir))
    except Exception as exc:  # noqa: BLE001 — never raise from a snapshot read
        _LOG.warning("query_status_transitions: load_ticker_series failed for %s: %s",
                     ticker, exc)
        series = []

    # date -> fragility_level join table from the _meta headers.
    frag_by_date = {m.date: m.fragility_level for m in load_all_meta(snapshot_dir)}

    out: list[dict] = []
    for rec in series or []:
        if not isinstance(rec, dict):
            continue
        sbh = rec.get("status_by_horizon") or {}
        d = rec.get("date", "")
        out.append({
            "date": d,
            "status": rec.get("status", ""),
            "status_short": sbh.get("short", ""),
            "status_mid": sbh.get("mid", ""),
            "status_long": sbh.get("long", ""),
            "short_score": rec.get("short_score", 0.0),
            "mid_score": rec.get("mid_score", 0.0),
            "long_score": rec.get("long_score", 0.0),
            "macro_regime": rec.get("macro_regime", ""),
            "fragility_level": frag_by_date.get(d, ""),
        })
    out.sort(key=lambda r: r["date"])
    return out


# Per-horizon field name for the score column on a record.
_SCORE_FIELD = {"short": "short_score", "mid": "mid_score", "long": "long_score"}


def compute_actionable_follow_through(
    horizon: str,                    # "short" | "mid" | "long"
    status_from: str = "Actionable Now",
    window_days: int = 5,
    score_improvement_threshold: float = 0.05,
    snapshot_dir: str = DEFAULT_SNAPSHOT_DIR,
) -> dict:
    """Did ``status_from`` signals on ``horizon`` follow through with a score gain?

    For every ``(ticker, date)`` whose ``status_by_horizon[horizon] == status_from``,
    look at the next ``window_days`` SNAPSHOT days (not calendar days) for the same
    ticker and ask whether that horizon's score rose by at least
    ``score_improvement_threshold`` above the signal-day score.

    ``follow_through`` is computed over whatever days actually fall in the window —
    a partial window (fewer than ``window_days`` days remain in history) still
    yields a verdict from the days that exist. ``insufficient_history`` is set True
    when ANY signal sits within ``window_days`` of the last snapshot (its window was
    truncated by end-of-data) — with only 8 days of history this is the common case.

    Never raises; always returns a result dict.
    """
    score_field = _SCORE_FIELD.get(horizon)
    result = {
        "horizon": horizon,
        "status_from": status_from,
        "window_days": window_days,
        "score_threshold": score_improvement_threshold,
        "total_signals": 0,
        "follow_through_count": 0,
        "follow_through_rate": 0.0,
        "insufficient_history": False,
        "cases": [],
    }
    if score_field is None:
        _LOG.warning("compute_actionable_follow_through: invalid horizon %r", horizon)
        return result

    records = load_all_opportunities(snapshot_dir)

    # The global ordered list of distinct snapshot days. The window is index-based
    # over THIS list, so gapped calendar dates never fabricate or skip a window.
    all_dates = sorted({r.date for r in records})
    date_pos = {d: i for i, d in enumerate(all_dates)}
    n_dates = len(all_dates)

    # Group each ticker's records by date for in-window lookups.
    by_ticker: dict[str, dict[str, OpportunityRecord]] = {}
    for r in records:
        by_ticker.setdefault(r.ticker, {})[r.date] = r

    cases: list[dict] = []
    follow_through_count = 0
    insufficient_any = False

    for r in records:
        if (r.status_by_horizon or {}).get(horizon) != status_from:
            continue
        initial_score = float(getattr(r, score_field))
        pos = date_pos.get(r.date)
        if pos is None:
            continue

        # Snapshot days strictly after the signal, capped at window_days of them.
        window_dates = all_dates[pos + 1: pos + 1 + window_days]
        days_after_in_history = n_dates - 1 - pos
        if days_after_in_history < window_days:
            insufficient_any = True

        ticker_days = by_ticker.get(r.ticker, {})
        scores_in_window: list[float] = []
        dates_present: list[str] = []
        for d in window_dates:
            rec = ticker_days.get(d)
            if rec is None:
                continue
            scores_in_window.append(float(getattr(rec, score_field)))
            dates_present.append(d)

        best_score = max(scores_in_window) if scores_in_window else initial_score
        score_delta = best_score - initial_score
        follow_through = bool(scores_in_window) and score_delta >= score_improvement_threshold
        if follow_through:
            follow_through_count += 1

        cases.append({
            "ticker": r.ticker,
            "signal_date": r.date,
            "initial_score": initial_score,
            "best_score_in_window": best_score,
            "score_delta": score_delta,
            "follow_through": follow_through,
            "dates_in_window": dates_present,
        })

    total = len(cases)
    result["total_signals"] = total
    result["follow_through_count"] = follow_through_count
    result["follow_through_rate"] = (follow_through_count / total) if total else 0.0
    result["insufficient_history"] = insufficient_any
    result["cases"] = cases
    return result


def compute_fragility_series(
    snapshot_dir: str = DEFAULT_SNAPSHOT_DIR,
) -> list[dict]:
    """Return the fragility state for each snapshot day, sorted ascending by date."""
    out: list[dict] = []
    for m in load_all_meta(snapshot_dir):
        out.append({
            "date": m.date,
            "fragility_level": m.fragility_level,
            "fragility_points": m.fragility_points,
            "fragility_raw_level": m.fragility_raw_level,
            "fragility_triggered": m.fragility_triggered,
            "fragility_consecutive_raw": m.fragility_consecutive_raw,
            "hysteresis_source": m.hysteresis_source,
            "macro_regime": m.macro_regime,
            "breadth_above_sma20": m.breadth_above_sma20,
            "breadth_slope": m.breadth_slope,
        })
    # load_all_meta already sorts ascending; sort again defensively (cheap).
    out.sort(key=lambda r: r["date"])
    return out
