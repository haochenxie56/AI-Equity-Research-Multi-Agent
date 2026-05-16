"""
Sector rotation analysis: momentum scoring, rotation phase detection,
and intra-sector stock ranking.

Imports data_fetcher directly (no ui_utils dependency) so this module
can be used from lib/ context as well as from Streamlit pages.
"""

import numpy as np
import pandas as pd
import streamlit as st

from sectors import SECTOR_CONFIG


# ── Internal data helpers (lazy import to avoid circular issues) ──────────────

def _get_ohlcv(ticker: str, period: str = "1y") -> pd.DataFrame:
    from data_fetcher import get_ohlcv
    return get_ohlcv(ticker, period=period)


def _get_info(ticker: str) -> dict:
    from data_fetcher import get_info
    try:
        return get_info(ticker)
    except Exception:
        return {}


# ── Sector scoring ────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def compute_sector_scores() -> pd.DataFrame:
    """
    Compute composite momentum scores for all 11 GICS sectors.

    Returns a DataFrame sorted by score (descending) with columns:
    sector, etf, color, zh, 1m_ret, 3m_ret, 6m_ret,
    1m_excess, 3m_excess, rsi, from_52w_high, vol_ratio,
    momentum_accel, score
    """
    # Benchmark returns
    try:
        spy_close = _get_ohlcv("SPY", "1y")["Close"]
        spy_ret = {
            "1m": float(spy_close.pct_change(21).iloc[-1]),
            "3m": float(spy_close.pct_change(63).iloc[-1]),
            "6m": float(spy_close.pct_change(126).iloc[-1]),
        }
    except Exception:
        spy_ret = {"1m": 0.0, "3m": 0.0, "6m": 0.0}

    rows = []
    for sector, cfg in SECTOR_CONFIG.items():
        try:
            df    = _get_ohlcv(cfg["etf"], "1y")
            close = df["Close"]

            ret_1m = float(close.pct_change(21).iloc[-1])
            ret_3m = float(close.pct_change(63).iloc[-1])
            ret_6m = float(close.pct_change(126).iloc[-1])
            excess_1m = ret_1m - spy_ret["1m"]
            excess_3m = ret_3m - spy_ret["3m"]

            # RSI(14)
            delta = close.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rsi   = float((100 - 100 / (1 + gain / loss.replace(0, np.nan))).iloc[-1])

            # Distance from 52-week high
            high_52w  = float(close.rolling(252).max().iloc[-1])
            from_high = (float(close.iloc[-1]) / high_52w - 1) * 100

            # Volume ratio: 5-day vs 20-day average
            vol_ratio = float(
                df["Volume"].iloc[-5:].mean() / df["Volume"].iloc[-20:].mean()
            )

            # Momentum acceleration: is short-term excess gaining vs medium-term?
            accel = excess_1m - (excess_3m / 3)

            # Composite score (raw → normalised to 0-100)
            raw = (
                np.clip(excess_1m * 100, -20, 20) * 1.5 +
                np.clip(excess_3m * 100, -20, 20) * 1.0 +
                np.clip(rsi - 50,        -30, 30) * 0.5 +
                np.clip(from_high,       -30,  0) * (-0.3) +
                np.clip((vol_ratio - 1) * 100, -10, 10) * 0.3
            )
            score = float(np.clip(raw + 50, 0, 100))

            rows.append({
                "sector":         sector,
                "etf":            cfg["etf"],
                "color":          cfg["color"],
                "zh":             cfg["zh"],
                "1m_ret":         round(ret_1m * 100, 1),
                "3m_ret":         round(ret_3m * 100, 1),
                "6m_ret":         round(ret_6m * 100, 1),
                "1m_excess":      round(excess_1m * 100, 2),
                "3m_excess":      round(excess_3m * 100, 2),
                "rsi":            round(rsi, 1),
                "from_52w_high":  round(from_high, 1),
                "vol_ratio":      round(vol_ratio, 2),
                "momentum_accel": round(accel * 100, 2),
                "score":          round(score, 1),
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
    """
    Detect market rotation phase from sector relative strength.
    Returns a dict with: phase, offensive_score, defensive_score,
    top3_sectors, accelerating.
    """
    defensive = ["Utilities", "Consumer Staples", "Health Care"]
    offensive = ["Information Technology", "Consumer Discretionary", "Financials"]

    def_score = float(
        scores_df[scores_df["sector"].isin(defensive)]["score"].mean()
    )
    off_score = float(
        scores_df[scores_df["sector"].isin(offensive)]["score"].mean()
    )

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
    Rank a tuple of tickers by market cap and classify into tiers.

    Tiers:
      Leader     — top-3 by mkt cap, RSI > 45, above SMA200
      Challenger — top-10 by mkt cap OR above-average 3M return
      Sleeper    — below-average 3M return, RSI < 60 (mean-reversion candidates)

    `tickers` must be a tuple (hashable for st.cache_data).
    """
    rows = []
    for ticker in tickers[:top_n]:
        try:
            info  = _get_info(ticker)
            df    = _get_ohlcv(ticker, "6mo")
            close = df["Close"]
            if len(close) < 21:
                continue

            mkt_cap = info.get("marketCap", 0) or 0
            ret_1m  = float(close.pct_change(21).iloc[-1] * 100)
            ret_3m  = (
                float(close.pct_change(63).iloc[-1] * 100)
                if len(close) >= 63 else None
            )

            # RSI(14)
            delta = close.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rsi   = float(
                (100 - 100 / (1 + gain / loss.replace(0, np.nan))).iloc[-1]
            )

            sma200       = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else float(close.mean())
            above_sma200 = bool(close.iloc[-1] > sma200)
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

    df_out  = (
        pd.DataFrame(rows)
        .sort_values("mkt_cap", ascending=False)
        .reset_index(drop=True)
    )
    avg_3m  = df_out["3m_ret"].dropna().mean()

    tiers = []
    for i, row in df_out.iterrows():
        r3 = row["3m_ret"] if row["3m_ret"] is not None else -999.0
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
