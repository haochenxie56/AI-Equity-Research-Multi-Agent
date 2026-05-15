"""
Dual-layer cache manager for market data.

Layer 1 — In-memory dict  : always available; works on Streamlit Cloud and locally.
Layer 2 — Disk (Parquet)  : used when the filesystem is writable; persists across
                             browser refreshes on local deployments.

Streamlit Cloud provides an *ephemeral* filesystem that is reset on every deploy,
so disk writes silently fail there — the in-memory layer is sufficient for the
duration of a session.  On a local machine both layers are active, giving warm
cache even across Streamlit hot-reloads.
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data" / "us"

# ── In-memory cache ────────────────────────────────────────────────────────────
# { "TICKER::data_type" : {"df": DataFrame, "ts": float (epoch)} }
_MEM: dict = {}

# Default staleness thresholds (seconds)
FRESHNESS = {
    "ohlcv":           4 * 3600,    # 4 hours  — intraday price data
    "financials":      7 * 86400,   # 7 days   — quarterly statements
    "info":           24 * 3600,    # 24 hours — company metadata
    "recommendations":24 * 3600,
}

# Lazy, cached result of the disk write-ability test
_DISK_OK: Optional[bool] = None


# ── Internal helpers ───────────────────────────────────────────────────────────

def _disk_writable() -> bool:
    """Return True if the data directory exists and is writable (tested once)."""
    global _DISK_OK
    if _DISK_OK is None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            probe = DATA_DIR / ".write_probe"
            probe.touch()
            probe.unlink()
            _DISK_OK = True
        except Exception:
            _DISK_OK = False
    return _DISK_OK


def _mem_key(ticker: str, data_type: str) -> str:
    return f"{ticker.upper()}::{data_type}"


def _cache_path(ticker: str, data_type: str) -> Path:
    """Return the most-recent disk cache file path for a ticker/type pair."""
    pattern = f"{ticker.upper()}_{data_type}_*.parquet"
    files = sorted(DATA_DIR.glob(pattern), reverse=True)
    if files:
        return files[0]
    return DATA_DIR / f"{ticker.upper()}_{data_type}_{datetime.now().strftime('%Y%m%d')}.parquet"


# ── Public API ─────────────────────────────────────────────────────────────────

def is_fresh(ticker: str, data_type: str) -> bool:
    """Return True if cached data exists and is within the freshness window."""
    threshold = FRESHNESS.get(data_type, 24 * 3600)
    key = _mem_key(ticker, data_type)

    # 1) Memory hit
    if key in _MEM:
        return (time.time() - _MEM[key]["ts"]) < threshold

    # 2) Disk hit (warm memory from disk while we're here)
    if _disk_writable():
        path = _cache_path(ticker, data_type)
        if path.exists():
            age = time.time() - path.stat().st_mtime
            if age < threshold:
                return True

    return False


def load(ticker: str, data_type: str) -> Optional[pd.DataFrame]:
    """Load cached DataFrame (memory → disk). Returns None on cache miss."""
    key = _mem_key(ticker, data_type)

    # 1) Memory
    if key in _MEM:
        return _MEM[key]["df"]

    # 2) Disk → warm memory
    if _disk_writable():
        path = _cache_path(ticker, data_type)
        if path.exists():
            try:
                df = pd.read_parquet(path)
                _MEM[key] = {"df": df, "ts": path.stat().st_mtime}
                return df
            except Exception:
                pass

    return None


def save(ticker: str, data_type: str, df: pd.DataFrame) -> None:
    """
    Persist DataFrame.
    - Always writes to memory (instant, no I/O).
    - Attempts disk write; silently skips if filesystem is read-only
      (e.g. Streamlit Cloud ephemeral environment).
    """
    key = _mem_key(ticker, data_type)
    _MEM[key] = {"df": df, "ts": time.time()}

    if _disk_writable():
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            path = DATA_DIR / f"{ticker.upper()}_{data_type}_{date_str}.parquet"
            df.to_parquet(path, index=True)
            _cleanup_old(ticker, data_type, keep_path=path)
        except Exception:
            pass  # Cloud / read-only fs — memory layer is sufficient


def _cleanup_old(ticker: str, data_type: str, keep_path: Path) -> None:
    """Remove stale Parquet files for the same ticker/type, keeping only latest."""
    for f in DATA_DIR.glob(f"{ticker.upper()}_{data_type}_*.parquet"):
        if f != keep_path:
            try:
                f.unlink()
            except Exception:
                pass


def get_or_fetch(ticker: str, data_type: str, fetch_fn) -> pd.DataFrame:
    """
    Return cached data if fresh, otherwise call fetch_fn() and cache the result.

    Example::

        df = get_or_fetch(
            "AAPL", "ohlcv",
            lambda: yf.Ticker("AAPL").history(period="1y")
        )
    """
    if is_fresh(ticker, data_type):
        cached = load(ticker, data_type)
        if cached is not None:
            return cached

    df = fetch_fn()
    if df is not None and not df.empty:
        save(ticker, data_type, df)
    return df


def cache_status(ticker: str) -> dict:
    """
    Return freshness status dict for all known data types of a given ticker.
    Used by the sidebar to render the cache indicator dots.
    """
    result = {}
    for dt in FRESHNESS:
        fresh = is_fresh(ticker, dt)
        path_str = None
        if _disk_writable():
            p = _cache_path(ticker, dt)
            path_str = str(p) if p.exists() else None
        result[dt] = {"fresh": fresh, "path": path_str}
    return result
