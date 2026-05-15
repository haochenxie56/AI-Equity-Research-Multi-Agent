"""
Local cache manager for market data. Avoids redundant API calls by storing
data as Parquet files under data/us/ and checking freshness before fetching.
"""

import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data" / "us"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Default staleness thresholds (seconds)
FRESHNESS = {
    "ohlcv": 4 * 3600,        # 4 hours (intraday refresh)
    "financials": 7 * 86400,  # 7 days (quarterly data)
    "info": 24 * 3600,        # 24 hours (company metadata)
    "recommendations": 24 * 3600,
}


def _cache_path(ticker: str, data_type: str) -> Path:
    """Return the latest cache file path for a given ticker and data type."""
    pattern = f"{ticker.upper()}_{data_type}_*.parquet"
    files = sorted(DATA_DIR.glob(pattern), reverse=True)
    if files:
        return files[0]
    return DATA_DIR / f"{ticker.upper()}_{data_type}_{datetime.now().strftime('%Y%m%d')}.parquet"


def is_fresh(ticker: str, data_type: str) -> bool:
    """Return True if cached data exists and is within the freshness window."""
    path = _cache_path(ticker, data_type)
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    threshold = FRESHNESS.get(data_type, 24 * 3600)
    return age < threshold


def load(ticker: str, data_type: str) -> Optional[pd.DataFrame]:
    """Load cached DataFrame. Returns None if no valid cache."""
    path = _cache_path(ticker, data_type)
    if path.exists():
        return pd.read_parquet(path)
    return None


def save(ticker: str, data_type: str, df: pd.DataFrame) -> Path:
    """Save DataFrame to cache with today's date stamp."""
    date_str = datetime.now().strftime("%Y%m%d")
    path = DATA_DIR / f"{ticker.upper()}_{data_type}_{date_str}.parquet"
    df.to_parquet(path, index=True)
    _cleanup_old(ticker, data_type, keep_path=path)
    return path


def _cleanup_old(ticker: str, data_type: str, keep_path: Path) -> None:
    """Remove older cache files for the same ticker/type, keeping only the latest."""
    pattern = f"{ticker.upper()}_{data_type}_*.parquet"
    for f in DATA_DIR.glob(pattern):
        if f != keep_path:
            f.unlink()


def get_or_fetch(ticker: str, data_type: str, fetch_fn) -> pd.DataFrame:
    """
    Return cached data if fresh, otherwise call fetch_fn() and cache the result.

    Usage:
        df = get_or_fetch("AAPL", "ohlcv", lambda: yf.Ticker("AAPL").history(period="1y"))
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
    """Return freshness status for all data types of a given ticker."""
    return {
        dt: {
            "fresh": is_fresh(ticker, dt),
            "path": str(_cache_path(ticker, dt)) if _cache_path(ticker, dt).exists() else None,
        }
        for dt in FRESHNESS
    }
