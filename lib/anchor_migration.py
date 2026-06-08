"""lib/anchor_migration.py — Anchor Intelligence v2.3 U3 migration readout.

A fully deterministic (no LLM) readout over the append-only anchor archive
(:mod:`lib.anchor_archive`). For a configurable window it answers, per anchor
series, three questions:

* **direction** — is the anchor rising / falling / flat over the window?
* **speed** — Δ per session (one archived page-path valuation = one session).
* **consistency** — do the median / mean / fair-value-mid anchors move TOGETHER
  (multi-anchor co-movement = *conviction*), or does one drift alone
  (lone-anchor drift = *low_consistency*, i.e. noise)?

Consistency is the data source for ``lib.thesis_monitor``'s "logic break vs price
noise" distinction: a systematic, conviction-grade analyst-pool downshift is hard
evidence of thesis deterioration, whereas a single anchor wandering while the
others hold is noise. ``thesis_monitor`` consumes this readout READ-ONLY of the
archive — it never triggers a compute or fetch, and a deteriorating migration may
only ELEVATE a watch annotation, never auto-generate a sell/exit.

Guardrails: pure deterministic computation (``compute_migration`` does no I/O — it
takes records in); ``read_migration`` reads the archive read-only; never raises.
"""

from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# Visible config block (keep all tunables here)
# ---------------------------------------------------------------------------

# Window length: the most-recent N archived valuations ("sessions") considered.
MIGRATION_WINDOW_SESSIONS = 30
# A net relative move (|last − first| / |first|) at or below this is "flat" — the
# anchor did not meaningfully migrate over the window.
FLAT_REL_THRESHOLD = 0.02  # 2%
# Minimum records required to read any direction at all.
MIN_RECORDS_FOR_DIRECTION = 2

# Direction / consistency / overall vocabulary (stable tokens; no LLM text).
DIR_RISING = "rising"
DIR_FALLING = "falling"
DIR_FLAT = "flat"
DIR_UNKNOWN = "unknown"

CONS_CONVICTION = "conviction"        # >= 2 anchors share one non-flat direction
CONS_LOW = "low_consistency"          # lone-anchor drift or disagreement (noise)
CONS_STABLE = "stable"                # all available anchors flat
CONS_INSUFFICIENT = "insufficient"    # not enough history to read migration

# Mixed-origin caveat (Anchor Intel v2.3 backfill round, B3): the analyst series is
# computed ONLY over the live-accumulated span — backfilled records carry no analyst
# pool (the never-fabricate sentinel). When backfill records shorten the analyst
# span below a readable direction, this is flagged so the readout never pretends the
# analyst series reaches as far back as the price series.
CAVEAT_ANALYST_HISTORY_INSUFFICIENT = "analyst_history_insufficient"
ANALYST_HISTORY_INSUFFICIENT_NOTE = (
    "分析师历史不足（回填区间无分析师序列） | analyst history insufficient "
    "(backfilled span carries no analyst series)")

# Record-origin tokens (mirror lib.anchor_archive; inlined to keep compute_migration
# free of any I/O-module import). A record with no origin key reads as "live".
_ORIGIN_LIVE = "live"
_ORIGIN_BACKFILL = "backfill"
_ANALYST_SENTINEL = "analyst_history_unavailable"

# The anchor series read from each archive record.
_SERIES_KEYS = ("fair_value_mid", "analyst_median", "analyst_mean")


def _origin_of(record: dict) -> str:
    """Origin of a record (``"live"`` / ``"backfill"``); absent ⇒ ``"live"``."""
    if not isinstance(record, dict):
        return _ORIGIN_LIVE
    return str(record.get("record_origin") or _ORIGIN_LIVE)


def _is_backfill(record: dict) -> bool:
    """A record is backfilled if tagged so OR its analyst_pool is the sentinel."""
    if not isinstance(record, dict):
        return False
    return (_origin_of(record) == _ORIGIN_BACKFILL
            or record.get("analyst_pool") == _ANALYST_SENTINEL)


# ---------------------------------------------------------------------------
# Numeric helpers (fail-closed)
# ---------------------------------------------------------------------------


def _finite_pos(x) -> Optional[float]:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    xf = float(x)
    if xf != xf or xf <= 0:  # NaN or non-positive
        return None
    return xf


def _value_for(record: dict, key: str) -> Optional[float]:
    """Pull one series value from a record (fair_value_mid or an analyst-pool stat)."""
    if not isinstance(record, dict):
        return None
    if key == "fair_value_mid":
        return _finite_pos(record.get("fair_value_mid"))
    pool = record.get("analyst_pool")
    if not isinstance(pool, dict):
        return None
    stat = "median" if key == "analyst_median" else "mean"
    return _finite_pos(pool.get(stat))


def _direction(first: float, last: float) -> str:
    """Rising / falling / flat from the net relative move (flat band = threshold)."""
    if first <= 0:
        return DIR_UNKNOWN
    rel = (last - first) / first
    if rel > FLAT_REL_THRESHOLD:
        return DIR_RISING
    if rel < -FLAT_REL_THRESHOLD:
        return DIR_FALLING
    return DIR_FLAT


def _series_readout(values: list) -> dict:
    """Direction / speed / endpoints for one ordered (oldest→newest) value list."""
    vals = [v for v in values if v is not None]
    n = len(vals)
    if n < MIN_RECORDS_FOR_DIRECTION:
        return {"direction": DIR_UNKNOWN, "speed": None,
                "first": (vals[0] if vals else None),
                "last": (vals[-1] if vals else None), "n": n}
    first, last = vals[0], vals[-1]
    # Δ per session: one step = one archived valuation between the endpoints.
    speed = round((last - first) / (n - 1), 6)
    return {"direction": _direction(first, last), "speed": speed,
            "first": round(first, 6), "last": round(last, 6), "n": n}


# ---------------------------------------------------------------------------
# Migration readout (pure — no I/O)
# ---------------------------------------------------------------------------


def compute_migration(records: list,
                      *, window: int = MIGRATION_WINDOW_SESSIONS) -> dict:
    """Deterministic migration readout over ``records`` (oldest→newest).

    Pure: takes records in, does NO I/O. ``records`` should already be filtered to
    one ticker (see :func:`read_migration`); the most-recent ``window`` are used.
    Returns a fully deterministic dict — identical input always yields identical
    output. Never raises.
    """
    recs = list(records or [])
    if window is not None and window > 0:
        recs = recs[-int(window):]
    n_records = len(recs)

    series: dict = {}
    for key in _SERIES_KEYS:
        series[key] = _series_readout([_value_for(r, key) for r in recs])

    # Consistency: classify cross-anchor co-movement over the NON-flat directions.
    non_flat = [s["direction"] for s in series.values()
                if s["direction"] in (DIR_RISING, DIR_FALLING)]
    have_any = any(s["n"] >= MIN_RECORDS_FOR_DIRECTION for s in series.values())
    if n_records < MIN_RECORDS_FOR_DIRECTION or not have_any:
        consistency = CONS_INSUFFICIENT
        direction = DIR_UNKNOWN
    elif not non_flat:
        consistency = CONS_STABLE
        direction = DIR_FLAT
    elif len(set(non_flat)) == 1 and len(non_flat) >= 2:
        # >= 2 anchors share ONE direction → conviction (genuine migration).
        consistency = CONS_CONVICTION
        direction = non_flat[0]
    else:
        # A lone anchor moved while others held, or anchors disagreed → noise.
        consistency = CONS_LOW
        direction = DIR_UNKNOWN

    # Deterministic "hard evidence of deterioration": a conviction-grade DOWNSHIFT
    # (the systematic analyst-pool downshift the thesis monitor elevates on).
    deteriorating = (consistency == CONS_CONVICTION and direction == DIR_FALLING)

    caveats: list = []
    if consistency == CONS_INSUFFICIENT:
        caveats.append("insufficient_history")
    elif consistency == CONS_LOW:
        caveats.append("lone_anchor_drift")

    # --- Mixed-origin honesty (B3): price anchors span the full backfilled+live
    # window; the analyst anchor spans ONLY the live-accumulated records (backfill
    # carries no analyst series). Surface each span honestly and flag when backfill
    # has shortened the analyst span below a readable direction. ---
    n_backfill = sum(1 for r in recs if _is_backfill(r))
    n_live = n_records - n_backfill
    price_span_n = series["fair_value_mid"]["n"]
    analyst_span_n = max(series["analyst_median"]["n"], series["analyst_mean"]["n"])
    analyst_history_available = analyst_span_n >= MIN_RECORDS_FOR_DIRECTION
    analyst_history_note = ""
    if n_backfill > 0 and not analyst_history_available and price_span_n >= 1:
        # Backfill present but the live analyst span is too short to read a
        # direction — say so rather than imply the analyst series goes back further.
        if CAVEAT_ANALYST_HISTORY_INSUFFICIENT not in caveats:
            caveats.append(CAVEAT_ANALYST_HISTORY_INSUFFICIENT)
        analyst_history_note = ANALYST_HISTORY_INSUFFICIENT_NOTE

    return {
        "n_records": n_records,
        "window": int(window) if window else None,
        "series": series,
        "consistency": consistency,
        "direction": direction,
        "deteriorating": deteriorating,
        "caveats": caveats,
        # Additive mixed-origin fields (backfill round):
        "origins": {"live": n_live, "backfill": n_backfill},
        "price_span_n": price_span_n,
        "analyst_span_n": analyst_span_n,
        "analyst_history_available": analyst_history_available,
        "analyst_history_note": analyst_history_note,
    }


# ---------------------------------------------------------------------------
# Archive read (read-only — no compute, no network)
# ---------------------------------------------------------------------------


def read_migration(ticker: str, *, window: int = MIGRATION_WINDOW_SESSIONS,
                   archive_path=None) -> dict:
    """Read one ticker's archive history (READ-ONLY) and compute its migration.

    Reads only — never computes a fair value, never fetches. Fail-closed: a missing
    archive / read error degrades to the ``insufficient`` readout. ``archive_path``
    is injectable for deterministic tests.
    """
    try:
        from lib.anchor_archive import read_archive

        records = read_archive(ticker, window=window, path=archive_path)
    except Exception:  # noqa: BLE001 — fail-closed; no history
        records = []
    return compute_migration(records, window=window)
