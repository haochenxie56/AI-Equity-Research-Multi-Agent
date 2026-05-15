"""
Technical indicators for US equity price/volume analysis.
Uses pandas-ta as the primary engine (no TA-Lib C dependency required).
Input: OHLCV DataFrame with columns [Open, High, Low, Close, Volume].
"""

import pandas as pd

try:
    import pandas_ta as ta
    _TA_AVAILABLE = True
except ImportError:
    _TA_AVAILABLE = False


# ---------------------------------------------------------------------------
# Moving Averages
# ---------------------------------------------------------------------------

def add_sma(df: pd.DataFrame, periods: list[int] = [20, 50, 200]) -> pd.DataFrame:
    df = df.copy()
    for p in periods:
        df[f"SMA_{p}"] = df["Close"].rolling(p).mean()
    return df


def add_ema(df: pd.DataFrame, periods: list[int] = [10, 20]) -> pd.DataFrame:
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
        df[f"RSI_{period}"] = ta.rsi(df["Close"], length=period)
    else:
        delta = df["Close"].diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, float("nan"))
        df[f"RSI_{period}"] = 100 - (100 / (1 + rs))
    return df


def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    df = df.copy()
    if _TA_AVAILABLE:
        macd = ta.macd(df["Close"], fast=fast, slow=slow, signal=signal)
        df["MACD"] = macd.iloc[:, 0]
        df["MACD_signal"] = macd.iloc[:, 1]
        df["MACD_hist"] = macd.iloc[:, 2]
    else:
        ema_fast = df["Close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["Close"].ewm(span=slow, adjust=False).mean()
        df["MACD"] = ema_fast - ema_slow
        df["MACD_signal"] = df["MACD"].ewm(span=signal, adjust=False).mean()
        df["MACD_hist"] = df["MACD"] - df["MACD_signal"]
    return df


def add_stochastic(df: pd.DataFrame, k: int = 14, d: int = 3) -> pd.DataFrame:
    df = df.copy()
    if _TA_AVAILABLE:
        stoch = ta.stoch(df["High"], df["Low"], df["Close"], k=k, d=d)
        df["Stoch_K"] = stoch.iloc[:, 0]
        df["Stoch_D"] = stoch.iloc[:, 1]
    else:
        low_min = df["Low"].rolling(k).min()
        high_max = df["High"].rolling(k).max()
        df["Stoch_K"] = 100 * (df["Close"] - low_min) / (high_max - low_min)
        df["Stoch_D"] = df["Stoch_K"].rolling(d).mean()
    return df


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------

def add_bollinger(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> pd.DataFrame:
    df = df.copy()
    if _TA_AVAILABLE:
        bb = ta.bbands(df["Close"], length=period, std=std)
        df["BB_upper"] = bb.iloc[:, 0]
        df["BB_mid"] = bb.iloc[:, 1]
        df["BB_lower"] = bb.iloc[:, 2]
    else:
        mid = df["Close"].rolling(period).mean()
        s = df["Close"].rolling(period).std()
        df["BB_upper"] = mid + std * s
        df["BB_mid"] = mid
        df["BB_lower"] = mid - std * s
    return df


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df = df.copy()
    if _TA_AVAILABLE:
        df[f"ATR_{period}"] = ta.atr(df["High"], df["Low"], df["Close"], length=period)
    else:
        hl = df["High"] - df["Low"]
        hc = (df["High"] - df["Close"].shift()).abs()
        lc = (df["Low"] - df["Close"].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        df[f"ATR_{period}"] = tr.rolling(period).mean()
    return df


# ---------------------------------------------------------------------------
# Trend Strength
# ---------------------------------------------------------------------------

def add_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df = df.copy()
    if _TA_AVAILABLE:
        adx = ta.adx(df["High"], df["Low"], df["Close"], length=period)
        df["ADX"] = adx.iloc[:, 0]
        df["DI_plus"] = adx.iloc[:, 1]
        df["DI_minus"] = adx.iloc[:, 2]
    else:
        # Pure-Python ADX fallback (Wilder smoothing)
        high, low, close = df["High"], df["Low"], df["Close"]
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        dm_plus = ((high - high.shift(1)).clip(lower=0)
                   .where((high - high.shift(1)) > (low.shift(1) - low), 0))
        dm_minus = ((low.shift(1) - low).clip(lower=0)
                    .where((low.shift(1) - low) > (high - high.shift(1)), 0))

        atr_s = tr.ewm(alpha=1 / period, adjust=False).mean()
        di_plus = 100 * dm_plus.ewm(alpha=1 / period, adjust=False).mean() / atr_s
        di_minus = 100 * dm_minus.ewm(alpha=1 / period, adjust=False).mean() / atr_s
        dx = (100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, float("nan")))
        df["ADX"] = dx.ewm(alpha=1 / period, adjust=False).mean()
        df["DI_plus"] = di_plus
        df["DI_minus"] = di_minus
    return df


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------

def add_obv(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if _TA_AVAILABLE:
        df["OBV"] = ta.obv(df["Close"], df["Volume"])
    else:
        direction = df["Close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        df["OBV"] = (df["Volume"] * direction).cumsum()
    return df


def add_volume_ratio(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Ratio of current volume to N-day average volume."""
    df = df.copy()
    df[f"Vol_ratio_{period}d"] = df["Volume"] / df["Volume"].rolling(period).mean()
    return df


# ---------------------------------------------------------------------------
# Composite: apply standard indicator suite
# ---------------------------------------------------------------------------

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Apply full standard indicator set to an OHLCV DataFrame."""
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
# Utility: current readings snapshot
# ---------------------------------------------------------------------------

def snapshot(df: pd.DataFrame) -> dict:
    """Return latest indicator values as a dict for report generation."""
    df = add_all_indicators(df)
    last = df.iloc[-1]
    price = last["Close"]
    return {
        "price": round(price, 2),
        "SMA_20": round(last.get("SMA_20", float("nan")), 2),
        "SMA_50": round(last.get("SMA_50", float("nan")), 2),
        "SMA_200": round(last.get("SMA_200", float("nan")), 2),
        "RSI_14": round(last.get("RSI_14", float("nan")), 1),
        "MACD": round(last.get("MACD", float("nan")), 4),
        "MACD_hist": round(last.get("MACD_hist", float("nan")), 4),
        "ADX": round(last.get("ADX", float("nan")), 1),
        "ATR_14": round(last.get("ATR_14", float("nan")), 2),
        "Vol_ratio_20d": round(last.get("Vol_ratio_20d", float("nan")), 2),
        "above_SMA200": bool(price > last.get("SMA_200", 0)),
        "52w_high": round(df["Close"].tail(252).max(), 2),
        "52w_low": round(df["Close"].tail(252).min(), 2),
        "pct_from_52w_high": round((price / df["Close"].tail(252).max() - 1) * 100, 1),
    }
