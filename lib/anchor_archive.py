"""lib/anchor_archive.py — Anchor Intelligence v2.3 append-only anchor archive.

The hot ``lib.anchor_cache`` keeps only the *latest* computed valuation anchor per
ticker (overwrite-only), so historical anchors are LOST on every refresh — the
documented gap behind the MU anchor-swing diagnosis (snapshots carried no anchor,
so there was no way to tell a thesis-breaking analyst-pool downshift from price
noise). This module adds the missing **append-only history**: each PAGE-PATH
valuation appends one immutable record to a JSONL archive, building a per-ticker
time series that :mod:`lib.anchor_migration` reads to compute a deterministic
migration readout.

Access-path contract (Anchor Intel v2.3 STEP 0 matrix — see
``docs/reliability_anchor_intel_v2.md``):

* **Write only on page paths.** The single archive-append chokepoint is
  ``lib.equity_valuation.store_equity_research_result`` (called only from
  ``pages/4`` and the Cockpit on-demand ``_run_equity_research`` — both
  ``allow_fetch=True`` page paths). The ranking / Cockpit-refresh path
  (``rank_opportunities`` / ``_run_refresh``) appends NOTHING and makes no network
  call.
* **Append-only — HARD INVARIANT.** Records are NEVER rewritten or mutated in
  place (mirrors git's no-rewrite-published-history rule). A second valuation of
  the same ticker adds a row; it never edits the prior row.
* **Read-only consumers.** ``lib.anchor_migration`` and ``lib.thesis_monitor`` read
  the archive read-only; they never trigger a compute or fetch.

Schema (one record per JSONL line)::

    {
      "schema_version": 1,
      "record_origin": "live",          # "live" | "backfill" (absent ⇒ "live")
      "ticker": "MU",
      "computed_at": "2026-06-08T13:00:00+00:00",
      "data_vintage": "2026-06-08",
      "company_type": "cyclical",
      "fair_value_low": 95.0,
      "fair_value_mid": 110.0,
      "fair_value_high": 130.0,
      "blend_state": "blended",
      "analyst_pool": {"median": 112.5, "mean": 110.0,
                       "high": 130.0, "low": 95.0, "n": 20},
      "methods_used": ["dcf", "relative", "analyst"],
      "excluded_anchors": [{"name": "pe", "value": 8.1, "basis": "...", "flag": "..."}],
      "caveats": ["single_anchor_blend"]
    }

Guardrails: local JSON only (no DB / vector store / network); atomic append
(``open("a")`` + ``flush`` + ``fsync`` of one line — mirrors
``lib.reliability.evidence_store``); fully fail-closed — a missing / corrupt file
degrades to "no history", never an exception; a record whose ``schema_version``
differs from the current constant is skipped on read (forward-migration safe).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_log = logging.getLogger("anchor_archive")

# data/anchor_archive.jsonl lives under the repo-root data/ directory, alongside
# anchor_cache.json (the hot "latest" cache, unchanged).
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ANCHOR_ARCHIVE_PATH = _DATA_DIR / "anchor_archive.jsonl"

# One visible schema-version constant. Bump on any record-shape change; the
# read-time version guard (``_iter_records``) skips records of any other version so
# an append-only file with mixed versions stays readable (older rows are ignored,
# not migrated in place — append-only is preserved).
ANCHOR_ARCHIVE_SCHEMA_VERSION = 1

# --- Record origin + analyst sentinel (Anchor Intel v2.3 backfill round) -----
# ``record_origin`` distinguishes a live-complete record (the producer chokepoint,
# all anchors including the live analyst pool) from a backfilled-PARTIAL record
# (recomputed price/financial anchors only; the analyst anchor is ABSENT by
# construction — see ``ANALYST_HISTORY_UNAVAILABLE``). The field is purely
# ADDITIVE and ``schema_version`` is NOT bumped: a record written before this round
# simply lacks ``record_origin`` and reads as ``"live"`` (the default), exactly the
# U2 ``anchor_cache.analyst_pool`` additive-no-bump precedent. Bumping the version
# would orphan those older live rows behind the read-time version guard.
RECORD_ORIGIN_LIVE = "live"
RECORD_ORIGIN_BACKFILL = "backfill"

# Sentinel for ``analyst_pool`` on a BACKFILLED record. yfinance and all free
# sources expose ONLY the CURRENT analyst pool — there is no historical
# analyst-target series anywhere retrievable, so a backfilled record MUST NOT
# carry a number for it. This sentinel STRING (never ``None``-that-reads-as-zero,
# never today's pool back-dated, never any invented value) is the never-fabricate
# marker. Migration consumers treat a non-dict ``analyst_pool`` as "no analyst
# value" (see ``lib.anchor_migration._value_for``), so the analyst series is
# computed ONLY over the live-accumulated span.
ANALYST_HISTORY_UNAVAILABLE = "analyst_history_unavailable"

# Sentinel object for "argument not supplied" so an explicit ``None`` / sentinel
# string override is distinguishable from "use the projected pool".
_UNSET = object()


def record_origin_of(record: dict) -> str:
    """Origin of a record (``"live"`` / ``"backfill"``); absent ⇒ ``"live"``.

    Backward-compatible read default: a pre-backfill-round record has no
    ``record_origin`` key and is a live-complete record.
    """
    if not isinstance(record, dict):
        return RECORD_ORIGIN_LIVE
    return str(record.get("record_origin") or RECORD_ORIGIN_LIVE)


# ---------------------------------------------------------------------------
# Time helpers (fail-closed)
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _vintage_from_computed_at(computed_at: str) -> str:
    """Date portion (``YYYY-MM-DD``) of an ISO ``computed_at``, else today's date.

    The page-path valuation runs on free same-day yfinance data, so the compute
    date is an honest stand-in for the underlying data vintage when an explicit
    market-data date is not supplied. This is a real timestamp, never a fabricated
    bar-date.
    """
    if isinstance(computed_at, str) and len(computed_at) >= 10:
        head = computed_at[:10]
        if head[4] == "-" and head[7] == "-":
            return head
    return _now().date().isoformat()


# ---------------------------------------------------------------------------
# Record construction (pure — no I/O)
# ---------------------------------------------------------------------------


def _project_analyst_pool(pool) -> Optional[dict]:
    """Project an analyst pool to the archived ``{median,mean,high,low,n}`` subset.

    Returns ``None`` when the pool is missing / not a dict (a ticker without
    analyst coverage). Pure; never raises.
    """
    if not isinstance(pool, dict):
        return None
    out = {}
    for k in ("median", "mean", "high", "low"):
        v = pool.get(k)
        out[k] = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    try:
        out["n"] = int(pool.get("n") or 0)
    except (TypeError, ValueError):
        out["n"] = 0
    return out


def record_from_app_fair_value(fv, *, data_vintage: str = "",
                               record_origin: str = RECORD_ORIGIN_LIVE,
                               analyst_pool_override=_UNSET) -> dict:
    """Build an archive record from an :class:`lib.equity_valuation.AppFairValue`.

    Pure (no I/O). Tolerant of duck-typed stand-ins in tests via ``getattr``.
    ``data_vintage`` defaults to the date of ``fv.computed_at`` when not supplied.

    ``record_origin`` tags the record ``"live"`` (the producer chokepoint default)
    or ``"backfill"`` (the offline recompute engine). ``analyst_pool_override``,
    when supplied, REPLACES the projected analyst pool — the backfill engine passes
    :data:`ANALYST_HISTORY_UNAVAILABLE` because no historical analyst series exists
    (the never-fabricate invariant); a live record leaves it ``_UNSET`` so the real
    pool is projected from ``fv``.
    """
    g = lambda n, d=None: getattr(fv, n, d)  # noqa: E731
    computed_at = str(g("computed_at", "") or "") or _now().isoformat()
    vintage = str(data_vintage or "").strip() or _vintage_from_computed_at(computed_at)
    if analyst_pool_override is _UNSET:
        analyst_pool = _project_analyst_pool(g("analyst_pool", None))
    else:
        analyst_pool = analyst_pool_override
    return {
        "schema_version": ANCHOR_ARCHIVE_SCHEMA_VERSION,
        "record_origin": str(record_origin or RECORD_ORIGIN_LIVE),
        "ticker": str(g("ticker", "") or "").upper().strip(),
        "computed_at": computed_at,
        "data_vintage": vintage,
        "company_type": str(g("company_type", "") or ""),
        "fair_value_low": float(g("fair_value_low", 0.0) or 0.0),
        "fair_value_mid": float(g("fair_value_mid", 0.0) or 0.0),
        "fair_value_high": float(g("fair_value_high", 0.0) or 0.0),
        "blend_state": str(g("blend_state", "blended") or "blended"),
        "analyst_pool": analyst_pool,
        "methods_used": list(g("methods_used", []) or []),
        "excluded_anchors": list(g("excluded_anchors", []) or []),
        "caveats": list(g("caveats", []) or []),
    }


# ---------------------------------------------------------------------------
# Append (atomic, append-only, fail-closed)
# ---------------------------------------------------------------------------

# In-process dedup memo (Anchor Intel v2.3 F1). The producer chokepoint
# (``equity_valuation.compute_app_fair_value``) appends on EVERY page-path call,
# but ``compute_app_fair_value``'s cached worker re-surfaces the SAME computed
# vintage when the same ticker is valued twice in one session (e.g. pages/4 then
# pages/9): an identical ``computed_at`` is a cache RE-READ of one vintage, not a
# new valuation, so it is deduped. A genuinely new computation carries a fresh
# ``computed_at`` (a distinct key) and is appended (append-only keeps real
# vintages). Keyed by (resolved path, ticker, computed_at) so distinct archive
# files — e.g. per-test temp files — never collide. O(1); avoids reading the
# archive on the page path (see the F4 storage-growth note in the phase doc).
_APPENDED_KEYS: set = set()


def reset_dedup_cache() -> None:
    """Clear the in-process append dedup memo (test hook)."""
    _APPENDED_KEYS.clear()


def append_record(record: dict, path: Optional[Path] = None) -> bool:
    """Append one well-formed ``record`` to the archive (atomic, fail-closed).

    HARD INVARIANT: append-only. This opens the file in append mode and writes a
    single JSON line; it never reads, rewrites, or mutates any prior record.
    Identical (path, ticker, computed_at) re-appends within the process are deduped
    (a cache re-read of one vintage, not a new valuation) and reported as success
    without writing a second row. Returns ``True`` on success / dedup, ``False`` on
    any failure (never raises).
    """
    tk = str((record or {}).get("ticker", "") or "").upper().strip()
    if not tk:
        return False
    p = Path(path) if path else ANCHOR_ARCHIVE_PATH
    key = (str(p), tk, str((record or {}).get("computed_at", "") or ""))
    if key in _APPENDED_KEYS:
        return True  # same vintage re-surfaced this session — append-only no-op
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        _APPENDED_KEYS.add(key)
        return True
    except Exception:  # noqa: BLE001 — fail-closed append
        return False


def append_anchor_record(fv, *, data_vintage: str = "",
                         path: Optional[Path] = None) -> bool:
    """Append-only archive write-through for an :class:`AppFairValue` (fail-closed).

    Called ONLY from the page-path ``store_equity_research_result`` chokepoint —
    never from the ranking / refresh path (see the v2.3 access-path matrix).
    """
    try:
        record = record_from_app_fair_value(fv, data_vintage=data_vintage)
    except Exception:  # noqa: BLE001 — fail-closed
        return False
    return append_record(record, path=path)


# ---------------------------------------------------------------------------
# Read (read-only, fail-closed, version-guarded)
# ---------------------------------------------------------------------------


def _iter_records(path: Optional[Path] = None):
    """Yield each valid current-schema record from the archive (read-only).

    Skips blank lines, unparseable lines, and records whose ``schema_version``
    differs from :data:`ANCHOR_ARCHIVE_SCHEMA_VERSION` (forward-migration safe —
    an append-only file with mixed versions stays readable). Never raises.
    """
    p = Path(path) if path else ANCHOR_ARCHIVE_PATH
    if not p.is_file():
        return
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 — fail-closed (missing / corrupt)
        return
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:  # noqa: BLE001 — skip an unparseable line
            continue
        if not isinstance(rec, dict):
            continue
        if rec.get("schema_version") != ANCHOR_ARCHIVE_SCHEMA_VERSION:
            continue
        yield rec


def load_all_records(path: Optional[Path] = None) -> list:
    """Return every valid record in the archive (read-only; fail-closed → [])."""
    return list(_iter_records(path))


def read_archive(ticker: str, *, window: Optional[int] = None,
                 path: Optional[Path] = None) -> list:
    """Return one ticker's records, oldest→newest by ``computed_at`` (read-only).

    ``window`` (when given) keeps only the most recent ``window`` records. Purely
    read-only — no compute, no network, no write. Fail-closed → ``[]``.
    """
    tk = (ticker or "").upper().strip()
    if not tk:
        return []
    out = [r for r in _iter_records(path)
           if str(r.get("ticker", "")).upper().strip() == tk]
    out.sort(key=lambda r: str(r.get("computed_at", "")))
    if window is not None and window > 0:
        out = out[-int(window):]
    return out


def backfilled_vintages(ticker: str, *, path: Optional[Path] = None) -> set:
    """Return the set of ``data_vintage`` dates already covered by BACKFILL records.

    Reports only ``record_origin == "backfill"`` rows. Read-only; fail-closed →
    ``set()``. (The backfill engine's skip-guard uses :func:`covered_vintages`,
    which spans BOTH origins; this narrower view remains for diagnostics / tests.)
    """
    tk = (ticker or "").upper().strip()
    if not tk:
        return set()
    return {str(r.get("data_vintage", "")) for r in _iter_records(path)
            if str(r.get("ticker", "")).upper().strip() == tk
            and record_origin_of(r) == RECORD_ORIGIN_BACKFILL
            and r.get("data_vintage")}


def covered_vintages(ticker: str, *, path: Optional[Path] = None) -> set:
    """Return ``data_vintage`` dates already covered by ANY-origin records (G2 fix).

    The persistent idempotency guard for the offline backfill engine: re-running
    backfill skips any as-of date that already has a record of EITHER origin —
    ``live`` OR ``backfill`` — for the ticker. A real contemporaneous (live) compute
    for a date must NOT be double-counted by a historical backfill approximation of
    the SAME date (the end_date seam, where the weekly grid includes today and a
    live row may already exist): live wins. Robust across process restarts (the
    in-process append memo is not). Read-only; fail-closed → ``set()``.
    """
    tk = (ticker or "").upper().strip()
    if not tk:
        return set()
    return {str(r.get("data_vintage", "")) for r in _iter_records(path)
            if str(r.get("ticker", "")).upper().strip() == tk
            and r.get("data_vintage")}
