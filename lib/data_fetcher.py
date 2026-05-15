"""
Unified data fetcher for US equities.
Primary source: yfinance. Fallback: polygon.io REST API.
All results are cached via cache_manager.

Polygon.io free tier: https://polygon.io/dashboard  (register → copy key → set POLYGON_API_KEY in .env)
Free tier limits: 5 calls/min, delayed 15min for real-time; unlimited for historical EOD data.
"""

import os
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import yfinance as yf

from cache_manager import get_or_fetch

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")


# ---------------------------------------------------------------------------
# Price / OHLCV
# ---------------------------------------------------------------------------

def get_ohlcv(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Fetch OHLCV data. Period examples: 1y, 6mo, 3mo, 5d."""
    cache_key = f"ohlcv_{period}_{interval}"

    def fetch():
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval, auto_adjust=True)
        return df

    return get_or_fetch(ticker, cache_key, fetch)


# ---------------------------------------------------------------------------
# Company Info & Metadata
# ---------------------------------------------------------------------------

def get_info(ticker: str) -> dict:
    """Return yfinance info dict (market cap, sector, employees, etc.)."""
    t = yf.Ticker(ticker)
    return t.info


def get_fast_info(ticker: str) -> dict:
    """Return lightweight fast_info (price, market cap) — lower latency."""
    t = yf.Ticker(ticker)
    return dict(t.fast_info)


# ---------------------------------------------------------------------------
# Financials
# ---------------------------------------------------------------------------

def get_financials(ticker: str) -> pd.DataFrame:
    """Annual income statement (last 4 fiscal years)."""
    def fetch():
        return yf.Ticker(ticker).financials.T

    return get_or_fetch(ticker, "financials", fetch)


def get_balance_sheet(ticker: str) -> pd.DataFrame:
    """Annual balance sheet (last 4 fiscal years)."""
    def fetch():
        return yf.Ticker(ticker).balance_sheet.T

    return get_or_fetch(ticker, "balance_sheet", fetch)


def get_cashflow(ticker: str) -> pd.DataFrame:
    """Annual cash flow statement (last 4 fiscal years)."""
    def fetch():
        return yf.Ticker(ticker).cashflow.T

    return get_or_fetch(ticker, "cashflow", fetch)


def get_quarterly_financials(ticker: str) -> pd.DataFrame:
    """Quarterly income statement (last 8 quarters)."""
    def fetch():
        return yf.Ticker(ticker).quarterly_financials.T

    return get_or_fetch(ticker, "quarterly_financials", fetch)


# ---------------------------------------------------------------------------
# Estimates & Recommendations
# ---------------------------------------------------------------------------

def get_recommendations(ticker: str) -> pd.DataFrame:
    """Analyst buy/sell recommendations history."""
    def fetch():
        df = yf.Ticker(ticker).recommendations
        return df if df is not None else pd.DataFrame()

    return get_or_fetch(ticker, "recommendations", fetch)


def get_earnings_estimates(ticker: str) -> dict:
    """Forward EPS and revenue estimates."""
    t = yf.Ticker(ticker)
    return {
        "eps_trend": t.eps_trend,
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
    t = yf.Ticker(ticker)
    result: dict = {
        "next_earnings_date": None,
        "days_to_earnings": None,
        "eps_estimate": None,
        "revenue_estimate": None,
        "eps_actual_last": None,
        "surprise_pct_last": None,
    }

    # Next earnings date from calendar (yfinance returns a dict in v0.2+)
    try:
        cal = t.calendar
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date", [])
            if dates:
                ed = dates[0] if isinstance(dates, list) else dates
                result["next_earnings_date"] = pd.Timestamp(ed).to_pydatetime()
                result["days_to_earnings"] = (result["next_earnings_date"].date() - datetime.now(timezone.utc).date()).days
            result["eps_estimate"] = cal.get("Earnings Average")
            result["revenue_estimate"] = cal.get("Revenue Average")
        elif cal is not None and not (hasattr(cal, "empty") and cal.empty):
            # Legacy DataFrame format
            if "Earnings Date" in cal.index:
                ed = cal.loc["Earnings Date"].iloc[0]
                if pd.notna(ed):
                    result["next_earnings_date"] = pd.Timestamp(ed).to_pydatetime()
                    result["days_to_earnings"] = (result["next_earnings_date"].date() - datetime.now(timezone.utc).date()).days
            if "EPS Estimate" in cal.index:
                result["eps_estimate"] = cal.loc["EPS Estimate"].iloc[0]
    except Exception:
        pass

    # Last actual EPS + surprise from earnings_history
    try:
        hist = t.earnings_history
        if hist is not None and not hist.empty:
            last = hist.sort_index().iloc[-1]
            result["eps_actual_last"] = last.get("epsActual")
            eps_est = last.get("epsEstimate")
            eps_act = last.get("epsActual")
            if eps_est and eps_act and eps_est != 0:
                result["surprise_pct_last"] = round((eps_act - eps_est) / abs(eps_est) * 100, 1)
    except Exception:
        pass

    return result


def format_earnings_summary(ticker: str) -> str:
    """Return a one-line human-readable earnings summary for reports."""
    c = get_earnings_calendar(ticker)
    parts = []
    if c["next_earnings_date"]:
        d = c["next_earnings_date"].strftime("%Y-%m-%d")
        days = c["days_to_earnings"]
        label = f"今日" if days == 0 else (f"{days}天后" if days > 0 else f"{abs(days)}天前")
        parts.append(f"下次财报：{d}（{label}）")
        if c["eps_estimate"] is not None:
            parts.append(f"EPS 预期：${c['eps_estimate']:.2f}")
    if c["surprise_pct_last"] is not None:
        sign = "+" if c["surprise_pct_last"] >= 0 else ""
        parts.append(f"上次惊喜：{sign}{c['surprise_pct_last']}%")
    return " | ".join(parts) if parts else "财报日期暂无数据"


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
    t = yf.Ticker(ticker)
    info = t.fast_info
    result = {
        "regular_close": None,
        "pre_market_price": None,
        "pre_market_change": None,
        "post_market_price": None,
        "post_market_change": None,
    }
    try:
        result["regular_close"] = getattr(info, "previous_close", None) or getattr(info, "regularMarketPreviousClose", None)
        pre = getattr(info, "pre_market_price", None)
        post = getattr(info, "post_market_price", None)
        prev = result["regular_close"]
        if pre and prev:
            result["pre_market_price"] = pre
            result["pre_market_change"] = round((pre / prev - 1) * 100, 2)
        if post and prev:
            result["post_market_price"] = post
            result["post_market_change"] = round((post / prev - 1) * 100, 2)
    except Exception:
        pass
    return result


def get_ohlcv_with_prepost(ticker: str, period: str = "5d", interval: str = "1m") -> pd.DataFrame:
    """
    Intraday OHLCV including pre-market and after-hours sessions.
    Use interval='1m' or '5m'. Max period for 1m data is 7 days.
    """
    t = yf.Ticker(ticker)
    return t.history(period=period, interval=interval, prepost=True, auto_adjust=True)


def format_prepost_summary(ticker: str) -> str:
    """Return a one-line pre/post market summary for reports."""
    d = get_prepost_price(ticker)
    parts = []
    if d["pre_market_price"]:
        sign = "+" if (d["pre_market_change"] or 0) >= 0 else ""
        parts.append(f"盘前 ${d['pre_market_price']:.2f}（{sign}{d['pre_market_change']}%）")
    if d["post_market_price"]:
        sign = "+" if (d["post_market_change"] or 0) >= 0 else ""
        parts.append(f"盘后 ${d['post_market_price']:.2f}（{sign}{d['post_market_change']}%）")
    if not parts:
        return "盘前/盘后数据暂不可用（非交易时段或数据源限制）"
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------

def get_news(ticker: str, count: int = 10) -> list[dict]:
    """Recent news headlines for a ticker."""
    t = yf.Ticker(ticker)
    return t.news[:count]


# ---------------------------------------------------------------------------
# Polygon.io fallback
# ---------------------------------------------------------------------------

def _polygon_ohlcv(ticker: str, from_date: str, to_date: str) -> Optional[pd.DataFrame]:
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
        df = df.rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})
        df = df.set_index("date")[["Open", "High", "Low", "Close", "Volume"]]
        return df
    except Exception:
        return None
