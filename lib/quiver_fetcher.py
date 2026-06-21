"""lib/quiver_fetcher.py — Phase 8B-0 Quiver Quantitative ingestion layer.

Fetches paid alternative-data signals from Quiver Quantitative (dark pool,
congressional trades, insider trades, institutional/hedge-fund positions).

Design (matches existing project conventions — see lib/data_fetcher.py and
lib/signal_engine.py):

* **Key loaded module-level** via ``os.getenv("QUIVER_API_KEY", "")``.
* **Fail-closed.** If the key is missing or any network/parse error occurs,
  every fetcher returns its neutral empty value (``[]``). Fetchers never raise
  to the caller.
* **Cached** with ``@st.cache_data`` (works headless — the body simply executes
  when no Streamlit server is running).
* **Fetch vs compute are STRICTLY SEPARATE.** ``fetch_*`` functions do network
  I/O only; ``compute_dark_pool_signal`` is a pure aggregator that performs no
  network access of its own beyond delegating to a cached fetcher.

Note on field names: Quiver returns title-cased JSON keys (``Date``,
``Ticker``, ``Price`` …). The parsers below read those keys with lowercase
fallbacks and emit the project's lowercase record schema. Exact Quiver field
names beyond the dark-pool endpoint should be confirmed against the live API;
the parsers use defensive ``.get`` lookups so an unexpected key simply yields a
neutral value rather than raising.
"""

from __future__ import annotations

import os
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

# Load .env from the project root (one level up from lib/), matching
# lib/data_fetcher.py and lib/signal_engine.py.
load_dotenv(Path(__file__).parent.parent / ".env")

QUIVER_API_KEY = os.getenv("QUIVER_API_KEY", "")
QUIVER_BASE_URL = "https://api.quiverquant.com/beta"

_TIMEOUT = 10  # seconds


# ---------------------------------------------------------------------------
# Internal HTTP helper
# ---------------------------------------------------------------------------

def _quiver_get(path: str) -> object:
    """GET ``{QUIVER_BASE_URL}{path}`` and return parsed JSON.

    Raises on any HTTP / transport error; callers wrap this in try/except to
    stay fail-closed. The bearer token is sent in the Authorization header.
    """
    headers = {
        "Authorization": f"Bearer {QUIVER_API_KEY}",
        "Accept": "application/json",
    }
    resp = requests.get(
        f"{QUIVER_BASE_URL}{path}", headers=headers, timeout=_TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()


def _first(rec: dict, *keys, default=None):
    """Return the first present, non-None value among *keys* in *rec*."""
    for k in keys:
        if k in rec and rec[k] is not None:
            return rec[k]
    return default


def _to_float(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _to_int(x, default: int = 0) -> int:
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Fetchers (network only; fail-closed; cached)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_dark_pool(ticker: str, lookback_days: int = 10) -> list[dict]:
    """Dark pool transaction records for *ticker* (Quiver /live/darkpool).

    TTL 1h (dark pool prints are end-of-day). Fail-closed -> ``[]``.

    Each record: ``{date, ticker, price, size, amount, source}`` and, when the
    raw API provides a prior close, an extra ``prev_close`` key used by
    ``compute_dark_pool_signal`` as the buy/sell proxy pivot.
    """
    if not QUIVER_API_KEY:
        return []
    try:
        raw = _quiver_get(f"/live/darkpool/{ticker}")
        if not isinstance(raw, list):
            return []
        out: list[dict] = []
        for r in raw:
            if not isinstance(r, dict):
                continue
            try:
                rec = {
                    "date": str(_first(r, "Date", "date", default="")),
                    "ticker": str(_first(r, "Ticker", "ticker", default=ticker)),
                    "price": _to_float(_first(r, "Price", "price")),
                    "size": _to_int(_first(r, "Size", "size")),
                    "amount": _to_float(_first(r, "Amount", "amount", "DollarVolume")),
                    "source": "quiver_dark_pool",
                }
                pc = _first(r, "PrevClose", "prev_close", "PreviousClose")
                if pc is not None:
                    rec["prev_close"] = _to_float(pc)
                out.append(rec)
            except Exception:  # noqa: BLE001 — skip a single malformed record
                continue
        return out[:lookback_days] if lookback_days and lookback_days > 0 else out
    except Exception:  # noqa: BLE001 — fail-closed
        return []


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_congress_trades(lookback_days: int = 30) -> list[dict]:
    """Congressional trade records (Quiver /live/congresstrading).

    TTL 24h (congressional disclosures are infrequent). Fail-closed -> ``[]``.

    Each record: ``{date, ticker, representative, transaction, amount, source}``.
    """
    if not QUIVER_API_KEY:
        return []
    try:
        raw = _quiver_get("/live/congresstrading")
        if not isinstance(raw, list):
            return []
        out: list[dict] = []
        for r in raw:
            if not isinstance(r, dict):
                continue
            try:
                out.append({
                    "date": str(_first(r, "Date", "date", "TransactionDate", default="")),
                    "ticker": str(_first(r, "Ticker", "ticker", default="")),
                    "representative": str(
                        _first(r, "Representative", "representative", "Name", default="")
                    ),
                    "transaction": str(
                        _first(r, "Transaction", "transaction", default="")
                    ),
                    "amount": str(_first(r, "Amount", "amount", "Range", default="")),
                    "source": "quiver_congress",
                })
            except Exception:  # noqa: BLE001
                continue
        return out
    except Exception:  # noqa: BLE001 — fail-closed
        return []


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_insider_trades(ticker: str, lookback_days: int = 30) -> list[dict]:
    """Insider (SEC Form 4) trade records (Quiver /live/insiders).

    TTL 24h. Fail-closed -> ``[]``.

    Each record: ``{date, ticker, name, relationship, transaction, shares,
    value, source}``.
    """
    if not QUIVER_API_KEY:
        return []
    try:
        raw = _quiver_get(f"/live/insiders/{ticker}")
        if not isinstance(raw, list):
            return []
        out: list[dict] = []
        for r in raw:
            if not isinstance(r, dict):
                continue
            try:
                out.append({
                    "date": str(_first(r, "Date", "date", "FilingDate", default="")),
                    "ticker": str(_first(r, "Ticker", "ticker", default=ticker)),
                    "name": str(_first(r, "Name", "name", default="")),
                    "relationship": str(
                        _first(r, "Relationship", "relationship", "Title", default="")
                    ),
                    "transaction": str(
                        _first(r, "Transaction", "transaction", "AcquiredDisposed",
                               default="")
                    ),
                    "shares": _to_int(_first(r, "Shares", "shares")),
                    "value": _to_float(_first(r, "Value", "value")),
                    "source": "quiver_insider",
                })
            except Exception:  # noqa: BLE001
                continue
        return out
    except Exception:  # noqa: BLE001 — fail-closed
        return []


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_hedge_fund_positions(ticker: str) -> list[dict]:
    """Institutional / hedge-fund holding records
    (Quiver /live/institutionalownership). TTL 24h. Fail-closed -> ``[]``.

    Each record: ``{date, ticker, institution, shares, value, source}``.
    """
    if not QUIVER_API_KEY:
        return []
    try:
        raw = _quiver_get(f"/live/institutionalownership/{ticker}")
        if not isinstance(raw, list):
            return []
        out: list[dict] = []
        for r in raw:
            if not isinstance(r, dict):
                continue
            try:
                out.append({
                    "date": str(_first(r, "Date", "date", "ReportDate", default="")),
                    "ticker": str(_first(r, "Ticker", "ticker", default=ticker)),
                    "institution": str(
                        _first(r, "Institution", "institution", "Filer", default="")
                    ),
                    "shares": _to_int(_first(r, "Shares", "shares")),
                    "value": _to_float(_first(r, "Value", "value")),
                    "source": "quiver_institutional",
                })
            except Exception:  # noqa: BLE001
                continue
        return out
    except Exception:  # noqa: BLE001 — fail-closed
        return []


# ---------------------------------------------------------------------------
# Processed signal (pure aggregator; no cache decorator)
# ---------------------------------------------------------------------------

# Net-direction thresholds (documented, deterministic):
#   buy_ratio >= 0.65 -> bullish; <= 0.35 -> bearish; else neutral.
_BULL_RATIO = 0.65
_BEAR_RATIO = 0.35
# Minimum records needed to classify at all.
_MIN_RECORDS = 3


def _strength(buy_ratio: float, direction: str) -> str:
    """Signal strength by magnitude of the buy_ratio beyond its threshold."""
    if direction == "bullish":
        if buy_ratio >= 0.80:
            return "strong"
        if buy_ratio >= 0.70:
            return "moderate"
        return "weak"  # 0.65 .. 0.70
    if direction == "bearish":
        if buy_ratio <= 0.20:
            return "strong"
        if buy_ratio <= 0.30:
            return "moderate"
        return "weak"  # 0.30 .. 0.35
    return "none"


def compute_dark_pool_signal(ticker: str, n_days: int = 5) -> dict:
    """Aggregate the last *n_days* of dark pool records for *ticker*.

    Pure aggregator: delegates the single network read to ``fetch_dark_pool``
    and performs only deterministic arithmetic afterwards.

    Buy/sell proxy: dark pool prints rarely carry an explicit side, so each
    record is classified by price vs its prior close — ``price > prev_close``
    is treated as buy-side, ``price < prev_close`` as sell-side. When a
    record lacks ``prev_close`` the proxy is unavailable for that print, so its
    dollar amount is split 50/50 and the result is marked ``degraded`` (per
    spec). With ``< 3`` records the window is too thin to classify.
    """
    records = fetch_dark_pool(ticker, lookback_days=n_days)
    record_count = len(records)

    base = {
        "ticker": ticker,
        "n_days": n_days,
        "net_direction": "neutral",
        "total_amount": 0.0,
        "buy_amount": 0.0,
        "sell_amount": 0.0,
        "signal_strength": "none",
        "record_count": record_count,
        "degraded": False,
        "source": "quiver_dark_pool",
    }

    # Insufficient data guard.
    if record_count < _MIN_RECORDS:
        base["net_direction"] = "insufficient_data"
        base["degraded"] = True
        return base

    buy_amount = 0.0
    sell_amount = 0.0
    total_amount = 0.0
    degraded = False

    for r in records:
        amount = _to_float(r.get("amount"))
        total_amount += amount
        price = r.get("price")
        pc = r.get("prev_close")
        if pc is not None and price is not None and amount != 0.0:
            if price > pc:
                buy_amount += amount
            elif price < pc:
                sell_amount += amount
            else:  # exactly at prior close — indeterminate
                buy_amount += amount / 2.0
                sell_amount += amount / 2.0
        else:
            # prev_close proxy unavailable for this print -> split 50/50.
            buy_amount += amount / 2.0
            sell_amount += amount / 2.0
            degraded = True

    base["total_amount"] = round(total_amount, 2)
    base["buy_amount"] = round(buy_amount, 2)
    base["sell_amount"] = round(sell_amount, 2)
    base["degraded"] = degraded

    if total_amount <= 0.0:
        # No usable dollar volume -> cannot infer direction.
        base["net_direction"] = "neutral"
        base["degraded"] = True
        return base

    buy_ratio = buy_amount / total_amount
    if buy_ratio >= _BULL_RATIO:
        direction = "bullish"
    elif buy_ratio <= _BEAR_RATIO:
        direction = "bearish"
    else:
        direction = "neutral"

    base["net_direction"] = direction
    base["signal_strength"] = _strength(buy_ratio, direction)
    return base
