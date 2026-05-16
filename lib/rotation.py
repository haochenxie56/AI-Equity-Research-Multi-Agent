"""
Sector rotation analysis: momentum scoring, rotation phase detection,
and intra-sector stock ranking.

Imports data_fetcher directly (no ui_utils dependency).
"""

import numpy as np
import pandas as pd
import streamlit as st

from sectors import SECTOR_CONFIG


# ── Internal data helpers ─────────────────────────────────────────────────────

def _get_ohlcv(ticker: str, period: str = "1y") -> pd.DataFrame:
    from data_fetcher import get_ohlcv
    return get_ohlcv(ticker, period=period)


def _get_info(ticker: str) -> dict:
    from data_fetcher import get_info
    try:
        return get_info(ticker)
    except Exception:
        return {}


def _safe(v: float, default: float = 0.0) -> float:
    """Return default if v is NaN or Inf."""
    if v is None:
        return default
    try:
        return default if (np.isnan(v) or np.isinf(v)) else float(v)
    except Exception:
        return default


def _pct_ret(close: pd.Series, n: int) -> float:
    """Return n-period percentage return, or 0.0 if not enough data."""
    if len(close) < n + 1:
        return 0.0
    v = float(close.pct_change(n).iloc[-1])
    return _safe(v, 0.0)


def _rsi14(close: pd.Series) -> float:
    """RSI(14). Returns 50.0 if calculation is not possible."""
    if len(close) < 15:
        return 50.0
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs         = gain / loss.where(loss > 0)          # NaN where loss=0
    rsi_series = (100 - 100 / (1 + rs)).fillna(100)  # all-gains → RSI=100
    return _safe(float(rsi_series.iloc[-1]), 50.0)


def _from_52w_high(close: pd.Series) -> float:
    """Percent distance from 52-week high. min_periods=1 prevents NaN."""
    high = float(close.rolling(252, min_periods=1).max().iloc[-1])
    if high == 0 or np.isnan(high):
        return 0.0
    return _safe((float(close.iloc[-1]) / high - 1) * 100, 0.0)


def _vol_ratio(volume: pd.Series) -> float:
    """5-day vs 20-day average volume ratio. Returns 1.0 on error."""
    vol = volume.fillna(0)
    v20 = float(vol.iloc[-20:].mean())
    v5  = float(vol.iloc[-5:].mean())
    if v20 == 0:
        return 1.0
    return _safe(v5 / v20, 1.0)


# ── Sector scoring ────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def compute_sector_scores(period_days: int = 63) -> pd.DataFrame:
    """
    Compute composite momentum scores for all 11 GICS sectors.

    period_days: primary scoring window in trading days.
      21 = 1M, 63 = 3M (default), 126 = 6M, 252 = 1Y.
      The selected period's excess return weight is raised to 2.0;
      other weights remain at their base values.

    Score formula (raw → normalised to 0-100):
      primary excess × 2.0  (selected period, clipped ±20pp)
      1M excess      × 1.5  (if period ≠ 1M, else merged into primary)
      3M excess      × 1.0  (if period ≠ 3M, else merged into primary)
      RSI deviation  × 0.5  (RSI − 50, clipped ±30)
      52W high dist  × 0.3  (inverted, clipped −30 to 0)
      Volume ratio   × 0.3  (vol_ratio−1 × 100, clipped ±10)
    """
    # ── Weight matrix ─────────────────────────────────────────────────────────
    if period_days == 21:       # 1M is primary
        w1m, w3m, w_extra = 2.0, 1.0, 0.0
    elif period_days == 63:     # 3M is primary
        w1m, w3m, w_extra = 1.5, 2.0, 0.0
    else:                       # 6M or 1Y — add as extra component at 2.0
        w1m, w3m, w_extra = 1.5, 1.0, 2.0

    # ── Benchmark (SPY) ───────────────────────────────────────────────────────
    spy_ret = {"1m": 0.0, "3m": 0.0, "primary": 0.0}
    try:
        spy_close = _get_ohlcv("SPY", "1y")["Close"].dropna()
        spy_ret = {
            "1m":      _pct_ret(spy_close, 21),
            "3m":      _pct_ret(spy_close, 63),
            "primary": _pct_ret(spy_close, period_days),
        }
    except Exception:
        pass

    # ── Per-sector metrics ────────────────────────────────────────────────────
    rows = []
    for sector, cfg in SECTOR_CONFIG.items():
        try:
            df = _get_ohlcv(cfg["etf"], "1y")
            if df is None or df.empty:
                continue
            close = df["Close"].dropna()
            if len(close) < 22:
                continue

            ret_1m      = _pct_ret(close, 21)
            ret_3m      = _pct_ret(close, 63)
            ret_6m      = _pct_ret(close, 126)
            ret_primary = _pct_ret(close, period_days)

            excess_1m      = ret_1m      - spy_ret["1m"]
            excess_3m      = ret_3m      - spy_ret["3m"]
            excess_primary = ret_primary - spy_ret["primary"]

            rsi       = _rsi14(close)
            from_high = _from_52w_high(close)
            vol_r     = _vol_ratio(df["Volume"])
            accel     = excess_1m - (excess_3m / 3)

            raw = (
                np.clip(excess_1m      * 100, -20, 20) * w1m    +
                np.clip(excess_3m      * 100, -20, 20) * w3m    +
                np.clip(excess_primary * 100, -20, 20) * w_extra +
                np.clip(rsi - 50,             -30, 30) * 0.5    +
                np.clip(from_high,            -30,  0) * (-0.3) +
                np.clip((vol_r - 1) * 100,    -10, 10) * 0.3
            )
            score = _safe(float(np.clip(raw + 50, 0, 100)), 50.0)

            rows.append({
                "sector":          sector,
                "etf":             cfg["etf"],
                "color":           cfg["color"],
                "zh":              cfg["zh"],
                "1m_ret":          round(ret_1m * 100, 1),
                "3m_ret":          round(ret_3m * 100, 1),
                "6m_ret":          round(ret_6m * 100, 1),
                "1m_excess":       round(excess_1m * 100, 2),
                "3m_excess":       round(excess_3m * 100, 2),
                "primary_excess":  round(excess_primary * 100, 2),
                "rsi":             round(rsi, 1),
                "from_52w_high":   round(from_high, 1),
                "vol_ratio":       round(vol_r, 2),
                "momentum_accel":  round(accel * 100, 2),
                "score":           round(score, 1),
            })
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    return (
        pd.DataFrame(rows)
        .sort_values("score", ascending=False)
        .reset_index(drop=True)
    )


# ── Rotation phase detection ──────────────────────────────────────────────────

def classify_rotation_phase(scores_df: pd.DataFrame) -> dict:
    """Detect market rotation phase from sector relative strength."""
    defensive = ["Utilities", "Consumer Staples", "Health Care"]
    offensive = ["Information Technology", "Consumer Discretionary", "Financials"]

    def_scores = scores_df[scores_df["sector"].isin(defensive)]["score"].dropna()
    off_scores = scores_df[scores_df["sector"].isin(offensive)]["score"].dropna()

    def_score = _safe(float(def_scores.mean()), 50.0) if not def_scores.empty else 50.0
    off_score = _safe(float(off_scores.mean()), 50.0) if not off_scores.empty else 50.0

    top3       = scores_df.head(3)["sector"].tolist()
    accel_secs = scores_df[scores_df["momentum_accel"] > 1]["sector"].tolist()

    if off_score > def_score + 10:
        phase = "risk_on"
    elif def_score > off_score + 10:
        phase = "risk_off"
    else:
        phase = "neutral"

    return {
        "phase":           phase,
        "offensive_score": round(off_score, 1),
        "defensive_score": round(def_score, 1),
        "top3_sectors":    top3,
        "accelerating":    accel_secs,
    }


# ── Intra-sector stock ranking ────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def rank_sector_stocks(tickers: tuple, top_n: int = 30) -> pd.DataFrame:
    """
    Rank a tuple of tickers by market cap and classify into tiers:
      Leader     — top-3 by mkt cap, RSI > 45, above SMA200
      Challenger — top-10 by mkt cap OR above-average 3M return
      Sleeper    — below-average 3M return + RSI < 60
    """
    rows = []
    for ticker in tickers[:top_n]:
        try:
            info  = _get_info(ticker)
            df    = _get_ohlcv(ticker, "6mo")
            if df is None or df.empty:
                continue
            close = df["Close"].dropna()
            if len(close) < 21:
                continue

            mkt_cap = info.get("marketCap", 0) or 0
            ret_1m  = _pct_ret(close, 21) * 100
            ret_3m  = (_pct_ret(close, 63) * 100) if len(close) >= 64 else None

            rsi = _rsi14(close)

            sma_n        = min(200, len(close))
            above_sma200 = bool(float(close.iloc[-1]) > float(close.rolling(sma_n).mean().iloc[-1]))
            fwd_pe       = info.get("forwardPE")

            rows.append({
                "ticker":       ticker,
                "name":         info.get("shortName", ticker),
                "mkt_cap":      mkt_cap,
                "1m_ret":       round(ret_1m, 1),
                "3m_ret":       round(ret_3m, 1) if ret_3m is not None else None,
                "rsi":          round(rsi, 1),
                "above_sma200": above_sma200,
                "fwd_pe":       round(fwd_pe, 1) if fwd_pe else None,
            })
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    df_out = (
        pd.DataFrame(rows)
        .sort_values("mkt_cap", ascending=False)
        .reset_index(drop=True)
    )
    avg_3m = _safe(df_out["3m_ret"].dropna().mean(), 0.0)

    tiers = []
    for i, row in df_out.iterrows():
        r3 = _safe(row["3m_ret"] if row["3m_ret"] is not None else -999.0, -999.0)
        if i < 3 and row["rsi"] > 45 and row["above_sma200"]:
            tiers.append("Leader")
        elif i < 10 and r3 >= avg_3m:
            tiers.append("Challenger")
        elif r3 < avg_3m - 10 and row["rsi"] < 60:
            tiers.append("Sleeper")
        else:
            tiers.append("Challenger")

    df_out["tier"] = tiers
    return df_out
