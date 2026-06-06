"""
Technical indicators for US equity price/volume analysis.

Primary engine : `ta` >= 0.11.0  (pure Python, no numba, Python 3.14 compatible)
                 https://github.com/bukosabino/ta
Fallback       : hand-rolled pandas implementations for every indicator,
                 so the app degrades gracefully if ta is not installed.

Input: OHLCV DataFrame with columns [Open, High, Low, Close, Volume].
"""

import pandas as pd

try:
    from ta.momentum   import RSIIndicator, StochasticOscillator
    from ta.trend      import MACD, ADXIndicator, SMAIndicator
    from ta.volatility import BollingerBands, AverageTrueRange
    from ta.volume     import OnBalanceVolumeIndicator
    _TA_AVAILABLE = True
except ImportError:
    _TA_AVAILABLE = False


# ---------------------------------------------------------------------------
# Moving Averages
# ---------------------------------------------------------------------------

def add_sma(df: pd.DataFrame, periods: list[int] = [20, 50, 200]) -> pd.DataFrame:
    """Simple Moving Averages — pure pandas, no ta dependency."""
    df = df.copy()
    for p in periods:
        df[f"SMA_{p}"] = df["Close"].rolling(p).mean()
    return df


def add_ema(df: pd.DataFrame, periods: list[int] = [10, 20]) -> pd.DataFrame:
    """Exponential Moving Averages — pure pandas."""
    df = df.copy()
    for p in periods:
        df[f"EMA_{p}"] = df["Close"].ewm(span=p, adjust=False).mean()
    return df


# ---------------------------------------------------------------------------
# Momentum
# ---------------------------------------------------------------------------

def add_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df = df.copy()
    if _TA_AVAILABLE:
        df[f"RSI_{period}"] = RSIIndicator(
            close=df["Close"], window=period
        ).rsi()
    else:
        # Wilder smoothing fallback
        delta = df["Close"].diff()
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / loss.replace(0, float("nan"))
        df[f"RSI_{period}"] = 100 - (100 / (1 + rs))
    return df


def add_macd(
    df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    df = df.copy()
    if _TA_AVAILABLE:
        ind = MACD(
            close=df["Close"],
            window_fast=fast, window_slow=slow, window_sign=signal,
        )
        df["MACD"]        = ind.macd()
        df["MACD_signal"] = ind.macd_signal()
        df["MACD_hist"]   = ind.macd_diff()
    else:
        ema_fast          = df["Close"].ewm(span=fast,   adjust=False).mean()
        ema_slow          = df["Close"].ewm(span=slow,   adjust=False).mean()
        df["MACD"]        = ema_fast - ema_slow
        df["MACD_signal"] = df["MACD"].ewm(span=signal, adjust=False).mean()
        df["MACD_hist"]   = df["MACD"] - df["MACD_signal"]
    return df


def add_stochastic(df: pd.DataFrame, k: int = 14, d: int = 3) -> pd.DataFrame:
    df = df.copy()
    if _TA_AVAILABLE:
        ind = StochasticOscillator(
            high=df["High"], low=df["Low"], close=df["Close"],
            window=k, smooth_window=d,
        )
        df["Stoch_K"] = ind.stoch()
        df["Stoch_D"] = ind.stoch_signal()
    else:
        low_min   = df["Low"].rolling(k).min()
        high_max  = df["High"].rolling(k).max()
        df["Stoch_K"] = 100 * (df["Close"] - low_min) / (high_max - low_min)
        df["Stoch_D"] = df["Stoch_K"].rolling(d).mean()
    return df


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------

def add_bollinger(
    df: pd.DataFrame, period: int = 20, std: float = 2.0
) -> pd.DataFrame:
    df = df.copy()
    if _TA_AVAILABLE:
        bb = BollingerBands(
            close=df["Close"], window=period, window_dev=std
        )
        df["BB_upper"] = bb.bollinger_hband()
        df["BB_mid"]   = bb.bollinger_mavg()
        df["BB_lower"] = bb.bollinger_lband()
    else:
        mid            = df["Close"].rolling(period).mean()
        s              = df["Close"].rolling(period).std()
        df["BB_upper"] = mid + std * s
        df["BB_mid"]   = mid
        df["BB_lower"] = mid - std * s
    return df


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df = df.copy()
    if _TA_AVAILABLE:
        df[f"ATR_{period}"] = AverageTrueRange(
            high=df["High"], low=df["Low"], close=df["Close"], window=period
        ).average_true_range()
    else:
        hl = df["High"] - df["Low"]
        hc = (df["High"] - df["Close"].shift()).abs()
        lc = (df["Low"]  - df["Close"].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        df[f"ATR_{period}"] = tr.rolling(period).mean()
    return df


# ---------------------------------------------------------------------------
# Trend Strength
# ---------------------------------------------------------------------------

def add_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df = df.copy()
    if _TA_AVAILABLE:
        ind = ADXIndicator(
            high=df["High"], low=df["Low"], close=df["Close"], window=period
        )
        df["ADX"]      = ind.adx()
        df["DI_plus"]  = ind.adx_pos()
        df["DI_minus"] = ind.adx_neg()
    else:
        # Pure-Python ADX fallback (Wilder smoothing)
        high, low, close = df["High"], df["Low"], df["Close"]
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low  - prev_close).abs(),
        ], axis=1).max(axis=1)
        dm_plus  = ((high - high.shift(1)).clip(lower=0)
                    .where((high - high.shift(1)) > (low.shift(1) - low), 0))
        dm_minus = ((low.shift(1) - low).clip(lower=0)
                    .where((low.shift(1) - low) > (high - high.shift(1)), 0))

        atr_s    = tr.ewm(alpha=1 / period, adjust=False).mean()
        di_plus  = 100 * dm_plus.ewm( alpha=1 / period, adjust=False).mean() / atr_s
        di_minus = 100 * dm_minus.ewm(alpha=1 / period, adjust=False).mean() / atr_s
        dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, float("nan"))
        df["ADX"]      = dx.ewm(alpha=1 / period, adjust=False).mean()
        df["DI_plus"]  = di_plus
        df["DI_minus"] = di_minus
    return df


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------

def add_obv(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if _TA_AVAILABLE:
        df["OBV"] = OnBalanceVolumeIndicator(
            close=df["Close"], volume=df["Volume"]
        ).on_balance_volume()
    else:
        direction = df["Close"].diff().apply(
            lambda x: 1 if x > 0 else (-1 if x < 0 else 0)
        )
        df["OBV"] = (df["Volume"] * direction).cumsum()
    return df


def add_volume_ratio(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Ratio of current volume to N-day average volume (pure pandas)."""
    df = df.copy()
    df[f"Vol_ratio_{period}d"] = df["Volume"] / df["Volume"].rolling(period).mean()
    return df


# ---------------------------------------------------------------------------
# Composite: apply standard indicator suite
# ---------------------------------------------------------------------------

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the full standard indicator set to an OHLCV DataFrame."""
    df = add_sma(df, [20, 50, 200])
    df = add_ema(df, [10, 20])
    df = add_rsi(df)
    df = add_macd(df)
    df = add_bollinger(df)
    df = add_atr(df)
    df = add_adx(df)
    df = add_obv(df)
    df = add_volume_ratio(df)
    return df


# ---------------------------------------------------------------------------
# Swing support / resistance + candlestick (pure pandas/code; no LLM)
# ---------------------------------------------------------------------------

def _nearest_swing_levels(df: pd.DataFrame, price: float, window: int = 20) -> tuple:
    """Return ``(nearest_support, nearest_resistance)`` over the last ``window`` bars.

    * ``nearest_support`` — the LARGEST swing low strictly *below* ``price`` (a bar
      whose Low is the minimum of its ±2-bar neighborhood), or ``None`` if none.
    * ``nearest_resistance`` — the SMALLEST swing high strictly *above* ``price``,
      or ``None`` if none.

    Fail-closed -> ``(None, None)``.
    """
    try:
        recent = df.tail(max(window, 5))
        lows = [float(x) for x in recent["Low"].values]
        highs = [float(x) for x in recent["High"].values]
        n = len(lows)
        swing_lows: list = []
        swing_highs: list = []
        for i in range(2, n - 2):
            if lows[i] == min(lows[i - 2 : i + 3]):
                swing_lows.append(lows[i])
            if highs[i] == max(highs[i - 2 : i + 3]):
                swing_highs.append(highs[i])
        below = [s for s in swing_lows if s < price]
        above = [r for r in swing_highs if r > price]
        nearest_support = round(max(below), 2) if below else None
        nearest_resistance = round(min(above), 2) if above else None
        return nearest_support, nearest_resistance
    except Exception:  # noqa: BLE001 — fail-closed
        return None, None


def candlestick_pattern(df: pd.DataFrame) -> str:
    """Detect a single candlestick pattern from the most-recent (up to 2) candles.

    Precedence: doji -> engulfing -> hammer/shooting_star -> "none". Mirrors the
    detector documented in ``lib/order_advisor._candlestick_pattern``; kept here so
    ``snapshot()`` can expose a ``candlestick_pattern`` field. Fail-closed -> "none".
    """
    try:
        if len(df) < 2:
            return "none"
        o = float(df["Open"].iloc[-1])
        h = float(df["High"].iloc[-1])
        l = float(df["Low"].iloc[-1])
        c = float(df["Close"].iloc[-1])
        po = float(df["Open"].iloc[-2])
        pc = float(df["Close"].iloc[-2])
        rng = h - l
        if rng <= 0:
            return "none"
        body = abs(c - o)
        if body <= 0.1 * rng:
            return "doji"
        prev_red, prev_green = pc < po, pc > po
        cur_green, cur_red = c > o, c < o
        if prev_red and cur_green and o <= pc and c >= po:
            return "bullish_engulfing"
        if prev_green and cur_red and o >= pc and c <= po:
            return "bearish_engulfing"
        upper_shadow = h - max(o, c)
        lower_shadow = min(o, c) - l
        if lower_shadow >= 2 * body and upper_shadow <= body and min(o, c) >= l + 0.5 * rng:
            return "hammer"
        if upper_shadow >= 2 * body and lower_shadow <= body and max(o, c) <= h - 0.5 * rng:
            return "shooting_star"
        return "none"
    except Exception:  # noqa: BLE001 — fail-closed
        return "none"


# ---------------------------------------------------------------------------
# Utility: latest readings snapshot (for report generation)
# ---------------------------------------------------------------------------

def snapshot(df: pd.DataFrame) -> dict:
    """Return the most-recent indicator values as a plain dict.

    Includes the moving-average set (EMA_10 / EMA_20 / SMA_20 / SMA_50 / SMA_200),
    momentum / volatility / volume readings, the nearest swing support/resistance
    over the last 20 bars, and the most-recent candlestick pattern — all computed
    deterministically here (no LLM). ``nearest_support`` / ``nearest_resistance``
    are ``None`` when no qualifying swing level exists.
    """
    df    = add_all_indicators(df)
    last  = df.iloc[-1]
    price = last["Close"]
    nearest_support, nearest_resistance = _nearest_swing_levels(df, float(price), 20)
    return {
        "price":            round(price, 2),
        "EMA_10":           round(last.get("EMA_10",        float("nan")), 2),
        "EMA_20":           round(last.get("EMA_20",        float("nan")), 2),
        "SMA_20":           round(last.get("SMA_20",        float("nan")), 2),
        "SMA_50":           round(last.get("SMA_50",        float("nan")), 2),
        "SMA_200":          round(last.get("SMA_200",       float("nan")), 2),
        "RSI_14":           round(last.get("RSI_14",        float("nan")), 1),
        "MACD":             round(last.get("MACD",          float("nan")), 4),
        "MACD_hist":        round(last.get("MACD_hist",     float("nan")), 4),
        "ADX":              round(last.get("ADX",           float("nan")), 1),
        "ATR_14":           round(last.get("ATR_14",        float("nan")), 2),
        "Vol_ratio_20d":    round(last.get("Vol_ratio_20d", float("nan")), 2),
        "above_SMA200":     bool(price > last.get("SMA_200", 0)),
        "52w_high":         round(df["Close"].tail(252).max(), 2),
        "52w_low":          round(df["Close"].tail(252).min(), 2),
        "pct_from_52w_high":round((price / df["Close"].tail(252).max() - 1) * 100, 1),
        # --- Entry Strategy v3 additions (swing levels + candlestick) ---------
        "nearest_support":    nearest_support,
        "nearest_resistance": nearest_resistance,
        "candlestick_pattern": candlestick_pattern(df),
    }
