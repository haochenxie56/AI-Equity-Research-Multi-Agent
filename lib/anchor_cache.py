"""lib/anchor_cache.py — Phase "Valuation stop-the-bleed" local anchor cache.

A tiny, deterministic, network-free JSON cache of computed valuation anchors,
keyed by ticker. It exists so the **Investment Cockpit** long-horizon enrichment
(``lib.opportunity_ranker.rank_opportunities`` Phase-2 top-N) can read a
previously-computed fair-value band **without any network fetch**, and therefore
differentiate the LONG status (``in_zone`` / ``above`` / ``below`` the value
band) instead of collapsing every candidate to *Research Required*.

Write-through happens from the places anchors are actually computed today — the
Equity Research page valuation hand-off
(``lib.equity_valuation.store_equity_research_result``) and any research/scanner
path that produces a :class:`lib.equity_valuation.AppFairValue` or
:class:`lib.valuation_anchor.FairValueAnchor`.

Schema (``data/anchor_cache.json``)::

    {
      "version": 1,
      "anchors": {
        "NVDA": {
          "ticker": "NVDA",
          "anchors": [                       # side-by-side basis list
            {"name": "dcf", "value": 120.5, "basis": "dcf"},
            {"name": "relative", "value": 3.23, "basis": "trailing_fallback"},
            {"name": "analyst", "value": 112.5, "basis": "analyst"}
          ],
          "blend_state": "blended",          # blended | anchors_irreconcilable | no_anchor
          "confidence": "medium",            # high | medium | low
          "relative_basis": "forward",       # forward | trailing_fallback | ""
          "fair_value_low": 95.0,
          "fair_value_mid": 110.0,
          "fair_value_high": 130.0,
          "conservative_anchor": 95.0,       # entry floor (== fair_value_low) or null
          "computed_at": "2026-06-05T13:00:00+00:00"
        },
        ...
      }
    }

Guardrails: local JSON only (no DB / vector store / network); atomic write
(``tmp`` + ``os.replace``, mirroring ``lib.holdings``); fully fail-closed — a
missing / corrupt file degrades to "no cached anchor", never an exception.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_log = logging.getLogger("anchor_cache")

# data/anchor_cache.json lives under the repo-root data/ directory.
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ANCHOR_CACHE_PATH = _DATA_DIR / "anchor_cache.json"

_SCHEMA_VERSION = 1

# Default staleness window: ~5 trading days ≈ 7 calendar days. A cached anchor
# older than this is treated as stale (the Cockpit falls back to its prior
# "Research Required / valuation anchor not established" behavior).
DEFAULT_STALENESS_DAYS = 7


# ---------------------------------------------------------------------------
# Time helpers (fail-closed)
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp to an aware UTC datetime, else ``None``."""
    if not isinstance(s, str) or not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def entry_age_days(entry: dict, now: Optional[datetime] = None) -> Optional[float]:
    """Age of a cache ``entry`` in (fractional) days from ``computed_at``.

    Returns ``None`` when the entry has no parseable ``computed_at``. ``now``
    (aware datetime) is injectable for deterministic tests.
    """
    if not isinstance(entry, dict):
        return None
    ts = _parse_iso(entry.get("computed_at"))
    if ts is None:
        return None
    ref = now or _now()
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return (ref - ts).total_seconds() / 86400.0


def is_fresh(entry: dict, max_age_days: Optional[float] = None,
             now: Optional[datetime] = None) -> bool:
    """``True`` when ``entry`` exists and is within ``max_age_days`` (default
    :data:`DEFAULT_STALENESS_DAYS`). A missing / unparseable timestamp is stale.
    """
    if not isinstance(entry, dict) or not entry:
        return False
    age = entry_age_days(entry, now=now)
    if age is None:
        return False
    limit = DEFAULT_STALENESS_DAYS if max_age_days is None else float(max_age_days)
    return 0.0 <= age <= limit


# ---------------------------------------------------------------------------
# Load / read (fail-closed, read-only — safe on the network-free Cockpit path)
# ---------------------------------------------------------------------------


def load_all(path: Optional[Path] = None) -> dict:
    """Return the full ``{ticker: entry}`` map (fail-closed → ``{}``).

    The envelope ``version`` is **respected**: a versioned envelope whose
    ``version`` does not equal :data:`_SCHEMA_VERSION` is treated as an empty
    cache (logged, never raised) so future schema migrations are safe. A bare,
    un-versioned ``{ticker: entry}`` object is still tolerated (legacy).
    """
    p = Path(path) if path else ANCHOR_CACHE_PATH
    try:
        if not p.is_file():
            return {}
        with open(p, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception:  # noqa: BLE001 — fail-closed (missing / corrupt)
        return {}
    if isinstance(raw, dict):
        if "version" in raw:
            ver = raw.get("version")
            if ver != _SCHEMA_VERSION:
                _log.warning(
                    "anchor_cache version mismatch (%r != %r); treating as empty",
                    ver, _SCHEMA_VERSION,
                )
                return {}
            anchors = raw.get("anchors")
            return anchors if isinstance(anchors, dict) else {}
        # Tolerate a bare ticker->entry object (no version envelope; legacy).
        return {k: v for k, v in raw.items() if isinstance(v, dict)}
    return {}


def read_anchor(ticker: str, path: Optional[Path] = None) -> Optional[dict]:
    """Return the cache entry for ``ticker`` (read-only), or ``None``."""
    tk = (ticker or "").upper().strip()
    if not tk:
        return None
    rec = load_all(path).get(tk)
    return rec if isinstance(rec, dict) else None


# ---------------------------------------------------------------------------
# Write-through (atomic, fail-closed)
# ---------------------------------------------------------------------------


def _coerce_entry(ticker: str, entry: dict) -> dict:
    """Normalize an entry dict, stamping ``ticker`` and ``computed_at`` if absent."""
    out = dict(entry or {})
    out["ticker"] = (ticker or out.get("ticker", "")).upper().strip()
    if not out.get("computed_at"):
        out["computed_at"] = _now().isoformat()
    return out


def write_anchor(ticker: str, entry: dict, path: Optional[Path] = None) -> bool:
    """Atomically upsert one ticker's anchor ``entry`` into the cache (fail-closed).

    Merges into the existing on-disk map (other tickers preserved) and writes via
    a ``tmp`` + ``os.replace`` swap, mirroring ``lib.holdings``. Returns ``True``
    on success, ``False`` on any failure (never raises).
    """
    tk = (ticker or "").upper().strip()
    if not tk:
        return False
    p = Path(path) if path else ANCHOR_CACHE_PATH
    try:
        current = load_all(p)
        current[tk] = _coerce_entry(tk, entry)
        payload = {"version": _SCHEMA_VERSION, "anchors": current}
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
        return True
    except Exception:  # noqa: BLE001 — fail-closed write
        return False


def entry_from_app_fair_value(fv) -> dict:
    """Build a cache entry dict from an :class:`lib.equity_valuation.AppFairValue`.

    Pure (no I/O). Tolerant of duck-typed stand-ins in tests via ``getattr``.
    """
    g = lambda n, d=None: getattr(fv, n, d)  # noqa: E731
    low = float(g("fair_value_low", 0.0) or 0.0)
    return {
        "ticker": str(g("ticker", "") or "").upper().strip(),
        "anchors": list(g("anchors", []) or []),
        "blend_state": str(g("blend_state", "blended") or "blended"),
        "confidence": str(g("confidence", "low") or "low"),
        "relative_basis": str(g("relative_basis", "") or ""),
        "peer_pe_basis": str(g("peer_pe_basis", "") or ""),
        "fair_value_low": low,
        "fair_value_mid": float(g("fair_value_mid", 0.0) or 0.0),
        "fair_value_high": float(g("fair_value_high", 0.0) or 0.0),
        # The conservative entry floor consumed by the LONG path is fair_value_low
        # when a real band exists; None when the band was suppressed (irreconcilable).
        "conservative_anchor": (low if low > 0 else None),
        "computed_at": str(g("computed_at", "") or "") or _now().isoformat(),
    }


def write_app_fair_value(fv, path: Optional[Path] = None) -> bool:
    """Write-through helper for an :class:`AppFairValue` (fail-closed)."""
    try:
        entry = entry_from_app_fair_value(fv)
    except Exception:  # noqa: BLE001 — fail-closed
        return False
    return write_anchor(entry.get("ticker", ""), entry, path=path)
