"""lib/anchor_archive.py — Anchor Intelligence v2.3 append-only anchor archive.

The hot ``lib.anchor_cache`` keeps only the *latest* computed valuation anchor per
ticker (overwrite-only), so historical anchors are LOST on every refresh — the
documented gap behind the MU anchor-swing diagnosis (snapshots carried no anchor,
so there was no way to tell a thesis-breaking analyst-pool downshift from price
noise). This module adds the missing **append-only history**: each PAGE-PATH
valuation appends one immutable record to the archive, building a per-ticker
time series that :mod:`lib.anchor_migration` reads to compute a deterministic
migration readout.

**Layout (v2.4 — F4 repayment):** the archive is SHARDED per ticker — the canonical
store is the directory :data:`ANCHOR_ARCHIVE_DIR` with one shard ``<TICKER>.jsonl``
per ticker, so a read for ticker T touches only T's bytes (O(T's records), not
O(total)). See the sharding note at :data:`ANCHOR_ARCHIVE_DIR`.

Access-path contract (Anchor Intel v2.3 STEP 0 matrix — see
``docs/reliability_anchor_intel_v2.md``):

* **Write only on page paths.** The single archive-append chokepoint is the producer
  ``lib.equity_valuation.compute_app_fair_value`` (appended on its live return; F1
  moved it here from ``store_equity_research_result`` so pages/9 / the Trading Desk,
  which never calls the hand-off, is historized too). It is invoked ONLY on
  ``allow_fetch=True`` page paths (pages/4, the Cockpit on-demand
  ``_run_equity_research``, and pages/9 via ``order_advisor._gather_technicals``).
  The ranking / Cockpit-refresh path (``rank_opportunities`` / ``_run_refresh``)
  appends NOTHING and makes no network call.
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

# The archive lives under the repo-root data/ directory, alongside
# anchor_cache.json (the hot "latest" cache, unchanged).
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# --- Per-ticker sharding (Anchor Intel v2.4, F4 repayment) -------------------
# v2.3 stored the whole history in ONE file ``data/anchor_archive.jsonl`` and every
# read scanned the entire file (O(total bytes)) before filtering by ticker — the
# documented F4 cost. v2.4 SHARDS the archive per ticker: the canonical store is the
# directory ``ANCHOR_ARCHIVE_DIR`` with one shard ``<TICKER>.jsonl`` per ticker, so a
# read for ticker T touches ONLY T's bytes (O(T's records)). Every production read is
# already keyed by a single ticker (``read_archive`` / ``covered_vintages`` /
# ``backfilled_vintages``; ``load_all_records`` has no production caller), so sharding
# bounds every hot-path read. Per-ticker sharding was chosen over a tail-bounded read
# because the single file interleaved all tickers — a tail read cannot bound a
# *per-ticker* read (T's most-recent records may sit arbitrarily far back behind other
# tickers' appends).
#
# The injectable ``path`` / ``archive_path`` parameter is the shard ROOT DIRECTORY
# (default ``ANCHOR_ARCHIVE_DIR``); the shard for ticker T is ``<root>/<T>.jsonl``.
# The legacy single-file path below is RETAINED only as the source the one-time
# offline migration (``scripts/migrate_anchor_archive_to_shards.py``) reads — reads
# never auto-migrate (that would reintroduce the O(total) scan). ``data/`` is
# git-ignored, so the layout change touches no tracked file.
ANCHOR_ARCHIVE_DIR = _DATA_DIR / "anchor_archive"

# Legacy single-file archive (pre-v2.4). NOT written or read on any hot path; the
# migration script reads it once to split it into per-ticker shards.
ANCHOR_ARCHIVE_PATH = _DATA_DIR / "anchor_archive.jsonl"

# One visible schema-version constant. Bump on any record-shape change; the
# read-time version guard (``_iter_file``) skips records of any other version so
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
# Shard-path resolution (per-ticker sharding, v2.4)
# ---------------------------------------------------------------------------


def _resolve_root(path: Optional[Path] = None) -> Path:
    """The shard ROOT directory (``path`` when given, else :data:`ANCHOR_ARCHIVE_DIR`).

    Resolves :data:`ANCHOR_ARCHIVE_DIR` at call time (not signature-default) so a test
    monkeypatching the module constant redirects production reads/writes.
    """
    return Path(path) if path else ANCHOR_ARCHIVE_DIR


def _shard_name(ticker: str) -> str:
    """Filesystem-safe shard filename for ``ticker`` (``<TICKER>.jsonl``).

    Uppercases + strips, then keeps ``[A-Z0-9._-]`` (US tickers may carry ``.`` /
    ``-`` / ``^``) and maps any other character to ``_`` so an exotic symbol can
    never escape the shard directory. Returns ``""`` for an empty ticker (callers
    guard on a falsy ticker before writing).
    """
    tk = (ticker or "").upper().strip()
    if not tk:
        return ""
    safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in tk)
    return f"{safe}.jsonl"


def shard_path(ticker: str, root: Optional[Path] = None) -> Path:
    """Absolute path of one ticker's shard under ``root`` (default the canonical dir).

    The public layout helper — the migration script and the test suites resolve a
    ticker's shard through this so the on-disk convention lives in exactly one place.
    """
    return _resolve_root(root) / _shard_name(ticker)


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


def _canonical_shard_str(p: Path) -> str:
    """Canonical absolute string for a shard path (dedup-key stable; F-B2).

    Uses ``Path.resolve()`` so equivalent aliases of the same shard — relative vs.
    absolute, a ``./`` prefix, or a symlinked root — collapse to ONE key and cannot
    bypass the append dedup (which would let the same vintage be appended twice and
    corrupt the append-only series / migration speed). ``resolve(strict=False)`` does
    not require the file to exist (a first append targets a not-yet-created shard).
    Fail-closed: an unresolvable path falls back to its absolute form, then its raw
    string, so the dedup key is always well-defined.
    """
    try:
        return str(p.resolve())
    except Exception:  # noqa: BLE001 — fail-closed; still canonicalize what we can
        try:
            return str(p.absolute())
        except Exception:  # noqa: BLE001
            return str(p)


def append_record(record: dict, path: Optional[Path] = None) -> bool:
    """Append one well-formed ``record`` to the archive (atomic, fail-closed).

    HARD INVARIANT: append-only. This opens the ticker's shard in append mode and
    writes a single JSON line; it never reads, rewrites, or mutates any prior record.
    The append routes to ``<root>/<TICKER>.jsonl`` (``path`` is the shard ROOT
    directory; default :data:`ANCHOR_ARCHIVE_DIR`). Identical (shard, ticker,
    computed_at) re-appends within the process are deduped (a cache re-read of one
    vintage, not a new valuation) and reported as success without writing a second
    row. Returns ``True`` on success / dedup, ``False`` on any failure (never raises).
    """
    tk = str((record or {}).get("ticker", "") or "").upper().strip()
    if not tk:
        return False
    p = shard_path(tk, path)
    key = (_canonical_shard_str(p), tk, str((record or {}).get("computed_at", "") or ""))
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

    Called ONLY from the producer chokepoint ``compute_app_fair_value`` (page
    paths) — never from the ranking / refresh path (see the access-path matrix).
    Routes to the ticker's shard (``path`` is the shard ROOT directory).
    """
    try:
        record = record_from_app_fair_value(fv, data_vintage=data_vintage)
    except Exception:  # noqa: BLE001 — fail-closed
        return False
    return append_record(record, path=path)


# ---------------------------------------------------------------------------
# Read (read-only, fail-closed, version-guarded)
# ---------------------------------------------------------------------------


def _iter_file(p: Path):
    """Yield each valid current-schema record from ONE shard file (read-only).

    Skips blank lines, unparseable lines, and records whose ``schema_version``
    differs from :data:`ANCHOR_ARCHIVE_SCHEMA_VERSION` (forward-migration safe —
    an append-only file with mixed versions stays readable). Never raises.
    """
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


def _iter_ticker(ticker: str, root: Optional[Path] = None):
    """Yield ``ticker``'s valid records by reading ONLY its shard (O(shard bytes)).

    This is the bounded per-ticker read that repays F4: it opens
    ``<root>/<TICKER>.jsonl`` and nothing else, so cost is O(the ticker's records)
    rather than O(total archive bytes). Records inside a shard are already only that
    ticker's, but the ``ticker`` guard is kept defensively. Never raises.
    """
    tk = (ticker or "").upper().strip()
    if not tk:
        return
    for rec in _iter_file(shard_path(tk, root)):
        if str(rec.get("ticker", "")).upper().strip() == tk:
            yield rec


def load_all_records(path: Optional[Path] = None) -> list:
    """Return every valid record across ALL shards (read-only; fail-closed → []).

    Globs ``<root>/*.jsonl`` and reads each shard. O(total) by construction — it has
    NO production caller (diagnostics / tests only); every hot-path read is the
    bounded per-ticker :func:`read_archive`.
    """
    root = _resolve_root(path)
    if not root.is_dir():
        return []
    out: list = []
    try:
        shards = sorted(root.glob("*.jsonl"))
    except Exception:  # noqa: BLE001 — fail-closed
        return []
    for shard in shards:
        out.extend(_iter_file(shard))
    return out


def read_archive(ticker: str, *, window: Optional[int] = None,
                 path: Optional[Path] = None) -> list:
    """Return one ticker's records, oldest→newest by ``computed_at`` (read-only).

    Reads ONLY the ticker's shard (``<root>/<TICKER>.jsonl``) — O(the ticker's
    records), not O(total archive). ``window`` (when given) keeps only the most
    recent ``window`` records. Purely read-only — no compute, no network, no write.
    Fail-closed → ``[]``.
    """
    tk = (ticker or "").upper().strip()
    if not tk:
        return []
    out = list(_iter_ticker(tk, path))
    out.sort(key=lambda r: str(r.get("computed_at", "")))
    if window is not None and window > 0:
        out = out[-int(window):]
    return out


def backfilled_vintages(ticker: str, *, path: Optional[Path] = None) -> set:
    """Return the set of ``data_vintage`` dates already covered by BACKFILL records.

    Reads ONLY the ticker's shard. Reports only ``record_origin == "backfill"`` rows.
    Read-only; fail-closed → ``set()``. (The backfill engine's skip-guard uses
    :func:`covered_vintages`, which spans BOTH origins; this narrower view remains
    for diagnostics / tests.)
    """
    tk = (ticker or "").upper().strip()
    if not tk:
        return set()
    return {str(r.get("data_vintage", "")) for r in _iter_ticker(tk, path)
            if record_origin_of(r) == RECORD_ORIGIN_BACKFILL
            and r.get("data_vintage")}


def covered_vintages(ticker: str, *, path: Optional[Path] = None) -> set:
    """Return ``data_vintage`` dates already covered by ANY-origin records (G2 fix).

    Reads ONLY the ticker's shard. The persistent idempotency guard for the offline
    backfill engine: re-running backfill skips any as-of date that already has a
    record of EITHER origin — ``live`` OR ``backfill`` — for the ticker. A real
    contemporaneous (live) compute for a date must NOT be double-counted by a
    historical backfill approximation of the SAME date (the end_date seam, where the
    weekly grid includes today and a live row may already exist): live wins. Robust
    across process restarts (the in-process append memo is not). Read-only;
    fail-closed → ``set()``.
    """
    tk = (ticker or "").upper().strip()
    if not tk:
        return set()
    return {str(r.get("data_vintage", "")) for r in _iter_ticker(tk, path)
            if r.get("data_vintage")}
