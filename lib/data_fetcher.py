"""
Unified data fetcher for US equities.
Primary source : yfinance  (with retry + timeout)
Fallback       : polygon.io REST API (requires POLYGON_API_KEY)

All heavy results are cached via cache_manager to avoid redundant requests.
Rate-limit / network errors are retried up to 3 times with exponential
back-off (2 s → 4 s → 8 s) before the exception is re-raised.
"""

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

from cache_manager import get_or_fetch

# Load .env from project root (two levels up from lib/)
load_dotenv(Path(__file__).parent.parent / ".env")

POLYGON_API_KEY  = os.getenv("POLYGON_API_KEY",  "")
FINNHUB_API_KEY  = os.getenv("FINNHUB_API_KEY",  "")

# Safely import yfinance's rate-limit exception (added in ~0.2.38)
try:
    from yfinance.exceptions import YFRateLimitError
except ImportError:
    YFRateLimitError = Exception  # older yfinance — treat all errors as retryable


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

_RETRY_DELAYS = (2, 4, 8)  # seconds; exponential back-off


def _with_retry(fn, retries: int = 3):
    """
    Call fn(), retrying on any exception up to `retries` times.

    Back-off schedule: 2 s → 4 s → 8 s.
    Re-raises the last exception if all attempts fail.
    """
    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as exc:            # noqa: BLE001
            last_exc = exc
            if attempt < retries:
                time.sleep(_RETRY_DELAYS[attempt - 1])
    raise last_exc


# ---------------------------------------------------------------------------
# Price / OHLCV
# ---------------------------------------------------------------------------

def get_ohlcv(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Fetch OHLCV data with retry. Period examples: 1y, 6mo, 3mo, 5d."""
    cache_key = f"ohlcv_{period}_{interval}"

    def fetch():
        return _with_retry(lambda: (
            yf.Ticker(ticker).history(
                period=period, interval=interval,
                auto_adjust=True, timeout=30,
            )
        ))

    return get_or_fetch(ticker, cache_key, fetch)


# ---------------------------------------------------------------------------
# Company Info & Metadata
# ---------------------------------------------------------------------------

def get_info(ticker: str) -> dict:
    """Return yfinance info dict (market cap, sector, employees, etc.)."""
    return _with_retry(lambda: yf.Ticker(ticker).info)


def get_fast_info(ticker: str) -> dict:
    """Return lightweight fast_info (price, market cap) — lower latency."""
    return _with_retry(lambda: dict(yf.Ticker(ticker).fast_info))


# ---------------------------------------------------------------------------
# Financials
# ---------------------------------------------------------------------------

def get_financials(ticker: str) -> pd.DataFrame:
    """Annual income statement (last 4 fiscal years)."""
    return get_or_fetch(
        ticker, "financials",
        lambda: _with_retry(lambda: yf.Ticker(ticker).financials.T),
    )


def get_balance_sheet(ticker: str) -> pd.DataFrame:
    """Annual balance sheet (last 4 fiscal years)."""
    return get_or_fetch(
        ticker, "balance_sheet",
        lambda: _with_retry(lambda: yf.Ticker(ticker).balance_sheet.T),
    )


def get_cashflow(ticker: str) -> pd.DataFrame:
    """Annual cash flow statement (last 4 fiscal years)."""
    return get_or_fetch(
        ticker, "cashflow",
        lambda: _with_retry(lambda: yf.Ticker(ticker).cashflow.T),
    )


def get_quarterly_financials(ticker: str) -> pd.DataFrame:
    """Quarterly income statement (last 8 quarters)."""
    return get_or_fetch(
        ticker, "quarterly_financials",
        lambda: _with_retry(lambda: yf.Ticker(ticker).quarterly_financials.T),
    )


# ---------------------------------------------------------------------------
# Estimates & Recommendations
# ---------------------------------------------------------------------------

def get_recommendations(ticker: str) -> pd.DataFrame:
    """Analyst buy/sell recommendations history."""
    def fetch():
        df = _with_retry(lambda: yf.Ticker(ticker).recommendations)
        return df if df is not None else pd.DataFrame()

    return get_or_fetch(ticker, "recommendations", fetch)


def get_earnings_estimates(ticker: str) -> dict:
    """Forward EPS and revenue estimates."""
    t = yf.Ticker(ticker)
    return {
        "eps_trend":        t.eps_trend,
        "revenue_estimate": t.revenue_estimate,
        "earnings_history": t.earnings_history,
    }


# ---------------------------------------------------------------------------
# Earnings Calendar
# ---------------------------------------------------------------------------

def get_earnings_calendar(ticker: str) -> dict:
    """
    Return upcoming earnings date and consensus estimates.

    Result keys:
      next_earnings_date   : datetime | None
      days_to_earnings     : int | None
      eps_estimate         : float | None  (consensus EPS for next quarter)
      revenue_estimate     : float | None  (consensus revenue for next quarter)
      eps_actual_last      : float | None  (most recent reported EPS)
      surprise_pct_last    : float | None  (last earnings surprise %)
    """
    result: dict = {
        "next_earnings_date":  None,
        "days_to_earnings":    None,
        "eps_estimate":        None,
        "revenue_estimate":    None,
        "eps_actual_last":     None,
        "surprise_pct_last":   None,
    }

    try:
        t = _with_retry(lambda: yf.Ticker(ticker))  # lightweight — no network yet
    except Exception:
        return result

    # Next earnings date from calendar (yfinance returns a dict in v0.2+)
    try:
        cal = _with_retry(lambda: t.calendar)
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date", [])
            if dates:
                ed = dates[0] if isinstance(dates, list) else dates
                result["next_earnings_date"] = pd.Timestamp(ed).to_pydatetime()
                result["days_to_earnings"] = (
                    result["next_earnings_date"].date()
                    - datetime.now(timezone.utc).date()
                ).days
            result["eps_estimate"]     = cal.get("Earnings Average")
            result["revenue_estimate"] = cal.get("Revenue Average")
        elif cal is not None and not (hasattr(cal, "empty") and cal.empty):
            # Legacy DataFrame format
            if "Earnings Date" in cal.index:
                ed = cal.loc["Earnings Date"].iloc[0]
                if pd.notna(ed):
                    result["next_earnings_date"] = pd.Timestamp(ed).to_pydatetime()
                    result["days_to_earnings"] = (
                        result["next_earnings_date"].date()
                        - datetime.now(timezone.utc).date()
                    ).days
            if "EPS Estimate" in cal.index:
                result["eps_estimate"] = cal.loc["EPS Estimate"].iloc[0]
    except Exception:
        pass

    # Last actual EPS + surprise from earnings_history
    try:
        hist = _with_retry(lambda: t.earnings_history)
        if hist is not None and not hist.empty:
            last = hist.sort_index().iloc[-1]
            result["eps_actual_last"] = last.get("epsActual")
            eps_est = last.get("epsEstimate")
            eps_act = last.get("epsActual")
            if eps_est and eps_act and eps_est != 0:
                result["surprise_pct_last"] = round(
                    (eps_act - eps_est) / abs(eps_est) * 100, 1
                )
    except Exception:
        pass

    return result


def format_earnings_summary(ticker: str) -> str:
    """Return a one-line human-readable earnings summary for reports."""
    c = get_earnings_calendar(ticker)
    parts = []
    if c["next_earnings_date"]:
        d     = c["next_earnings_date"].strftime("%Y-%m-%d")
        days  = c["days_to_earnings"]
        label = "Today" if days == 0 else (f"in {days}d" if days > 0 else f"{abs(days)}d ago")
        parts.append(f"Next Earnings: {d} ({label})")
        if c["eps_estimate"] is not None:
            parts.append(f"EPS Est: ${c['eps_estimate']:.2f}")
    if c["surprise_pct_last"] is not None:
        sign = "+" if c["surprise_pct_last"] >= 0 else ""
        parts.append(f"Last Surprise: {sign}{c['surprise_pct_last']}%")
    return " | ".join(parts) if parts else "Earnings date unavailable"


# ---------------------------------------------------------------------------
# Pre/Post Market Data
# ---------------------------------------------------------------------------

def get_prepost_price(ticker: str) -> dict:
    """
    Return latest pre-market and after-hours price alongside regular close.

    Result keys:
      regular_close      : float | None
      pre_market_price   : float | None
      pre_market_change  : float | None  (% vs prev close)
      post_market_price  : float | None
      post_market_change : float | None  (% vs regular close)
    """
    result = {
        "regular_close":     None,
        "pre_market_price":  None,
        "pre_market_change": None,
        "post_market_price": None,
        "post_market_change":None,
    }
    try:
        info = _with_retry(lambda: yf.Ticker(ticker).fast_info)
        result["regular_close"] = (
            getattr(info, "previous_close", None)
            or getattr(info, "regularMarketPreviousClose", None)
        )
        pre  = getattr(info, "pre_market_price",  None)
        post = getattr(info, "post_market_price", None)
        prev = result["regular_close"]
        if pre and prev:
            result["pre_market_price"]  = pre
            result["pre_market_change"] = round((pre / prev - 1) * 100, 2)
        if post and prev:
            result["post_market_price"]  = post
            result["post_market_change"] = round((post / prev - 1) * 100, 2)
    except Exception:
        pass
    return result


def get_ohlcv_with_prepost(
    ticker: str, period: str = "5d", interval: str = "1m"
) -> pd.DataFrame:
    """
    Intraday OHLCV including pre-market and after-hours sessions.
    Use interval='1m' or '5m'. Max period for 1m data is 7 days.
    """
    return _with_retry(lambda: yf.Ticker(ticker).history(
        period=period, interval=interval, prepost=True,
        auto_adjust=True, timeout=30,
    ))


def format_prepost_summary(ticker: str) -> str:
    """Return a one-line pre/post market summary for reports."""
    d = get_prepost_price(ticker)
    parts = []
    if d["pre_market_price"]:
        sign = "+" if (d["pre_market_change"] or 0) >= 0 else ""
        parts.append(f"Pre-mkt ${d['pre_market_price']:.2f} ({sign}{d['pre_market_change']}%)")
    if d["post_market_price"]:
        sign = "+" if (d["post_market_change"] or 0) >= 0 else ""
        parts.append(f"After-hrs ${d['post_market_price']:.2f} ({sign}{d['post_market_change']}%)")
    return " | ".join(parts) if parts else "Pre/post-market data unavailable (non-trading hours or data source limit)"


# ---------------------------------------------------------------------------
# News & Sentiment  (Finnhub primary, silent fallback when key is absent)
# ---------------------------------------------------------------------------

# Keyword sets for per-article headline sentiment scoring.
# Finnhub's free /company-news endpoint has no per-article score,
# so we derive one from headline keywords (range: -1 → +1).
_SENT_POS = frozenset({
    "beat", "beats", "record", "growth", "surges", "surge", "rally",
    "profit", "gains", "gain", "rises", "rise", "soars", "soar",
    "jumps", "jump", "upgrade", "upgraded", "outperform", "strong",
    "bullish", "expansion", "breakthrough", "buy", "positive", "boost",
    "raises", "raise", "exceeds", "exceed",
})
_SENT_NEG = frozenset({
    "miss", "misses", "missed", "loss", "losses", "decline", "declines",
    "drops", "drop", "falls", "fall", "slump", "slumps", "warning",
    "downgrade", "downgraded", "sell", "underperform", "weak", "bearish",
    "lawsuit", "investigation", "recall", "cuts", "cut", "layoffs",
    "layoff", "negative", "concern", "worries", "disappoints", "disappointing",
})


def _headline_sentiment(headline: str) -> float:
    """Keyword-based sentiment score: returns -1.0 … +1.0 (0.0 = neutral)."""
    words = set(headline.lower().split())
    pos = len(words & _SENT_POS)
    neg = len(words & _SENT_NEG)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 2)


def get_news(ticker: str, days: int = 7) -> list[dict]:
    """
    Fetch recent company news from Finnhub for the past `days` days.

    Returns a list of dicts:
        datetime  : "YYYY-MM-DD HH:MM" (UTC)
        headline  : str
        source    : str
        url       : str
        sentiment : float  -1…+1  (keyword-derived, 0 = neutral)
        summary   : str

    Requires FINNHUB_API_KEY env var. Returns [] silently if absent or on
    any network / parse error.
    """
    if not FINNHUB_API_KEY:
        return []

    try:
        import requests
        from datetime import timedelta

        to_dt   = datetime.now(timezone.utc).date()
        from_dt = to_dt - timedelta(days=days)

        resp = requests.get(
            "https://finnhub.io/api/v1/company-news",
            params={
                "symbol": ticker,
                "from":   str(from_dt),
                "to":     str(to_dt),
                "token":  FINNHUB_API_KEY,
            },
            timeout=10,
        )
        resp.raise_for_status()
        raw = resp.json()

        if not isinstance(raw, list):
            return []

        results: list[dict] = []
        for item in raw:
            try:
                headline = item.get("headline", "")
                results.append({
                    "datetime":  datetime.fromtimestamp(
                        item.get("datetime", 0), tz=timezone.utc
                    ).strftime("%Y-%m-%d %H:%M"),
                    "headline":  headline,
                    "source":    item.get("source", ""),
                    "url":       item.get("url", ""),
                    "sentiment": _headline_sentiment(headline),
                    "summary":   item.get("summary", ""),
                })
            except Exception:
                continue

        results.sort(key=lambda x: x["datetime"], reverse=True)
        print(f"[news] source: finnhub, count: {len(results)}", flush=True)
        return results

    except Exception:
        return []


def get_news_sentiment_summary(ticker: str, days: int = 7) -> dict:
    """
    Structured sentiment summary — designed as input for Claude agent calls.

    Keys:
        total            : int   — total article count
        positive         : int   — articles with sentiment > 0.2
        neutral          : int   — articles with -0.2 ≤ sentiment ≤ 0.2
        negative         : int   — articles with sentiment < -0.2
        avg_sentiment    : float — mean score across all articles (-1…+1)
        top_headlines    : list[str] — 3 most recent headlines
        sentiment_trend  : "improving" | "stable" | "deteriorating"
    """
    articles = get_news(ticker, days=days)

    result: dict = {
        "total":           0,
        "positive":        0,
        "neutral":         0,
        "negative":        0,
        "avg_sentiment":   0.0,
        "top_headlines":   [],
        "sentiment_trend": "stable",
    }

    if not articles:
        return result

    scores = [a["sentiment"] for a in articles]
    n = len(scores)

    result["total"]          = n
    result["positive"]       = sum(1 for s in scores if s >  0.2)
    result["neutral"]        = sum(1 for s in scores if -0.2 <= s <= 0.2)
    result["negative"]       = sum(1 for s in scores if s < -0.2)
    result["avg_sentiment"]  = round(sum(scores) / n, 3)
    result["top_headlines"]  = [a["headline"] for a in articles[:3]]

    # Trend: compare the first (most-recent) half vs second (older) half
    mid = n // 2
    if mid > 0:
        recent_avg = sum(scores[:mid]) / mid
        older_avg  = sum(scores[mid:]) / (n - mid)
        diff = recent_avg - older_avg
        if diff > 0.1:
            result["sentiment_trend"] = "improving"
        elif diff < -0.1:
            result["sentiment_trend"] = "deteriorating"

    return result


# ---------------------------------------------------------------------------
# Polygon.io fallback
# ---------------------------------------------------------------------------

def _polygon_ohlcv(
    ticker: str, from_date: str, to_date: str
) -> Optional[pd.DataFrame]:
    """Fetch OHLCV from polygon.io. Requires POLYGON_API_KEY env var."""
    if not POLYGON_API_KEY:
        return None
    try:
        import requests
        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day"
            f"/{from_date}/{to_date}?adjusted=true&sort=asc&limit=5000"
            f"&apiKey={POLYGON_API_KEY}"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None
        df = pd.DataFrame(results)
        df["date"] = pd.to_datetime(df["t"], unit="ms")
        df = df.rename(columns={
            "o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume",
        })
        return df.set_index("date")[["Open", "High", "Low", "Close", "Volume"]]
    except Exception:
        return None
