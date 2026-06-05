"""Phase 7A — Simplified Relative Strength (Task 2).

A small, deterministic helper that compares a ticker's recent price action to
SPY and QQQ and to its own moving averages. It is a **new module** (rather than
an edit to the frozen ``lib/technical.py``) and reads OHLCV through the existing
cached loader (``ui_utils.load_ohlcv``), so per-ticker history fetched by the
signal pipeline is reused as a cache hit.

Fields exposed (consumed by ``lib.opportunity_ranker``; RS carries 0.20 weight in
every horizon table, so 7A is incomplete without it):

* 5-day and 1-month return vs SPY and vs QQQ — the **benchmark series is fetched
  once per refresh**, never per ticker.
* above / below SMA20 and SMA50.
* volume ratio (recent vs trailing average).
* ``rs_composite`` — a single [0,1] roll-up of the above for the score tables.

Leader/Improving/Neutral/Laggard labelling and group confirmation are explicitly
**out of scope** (Phase 7B). Review-only; not investment advice. Fully
fail-closed: any missing data degrades to ``None`` / a neutral composite rather
than raising.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Callable, Optional

# ── Multi-window config (Phase 7B Task 1) ─────────────────────────────────────
# All windows in trading days. These are the raw material for both the
# per-horizon RS composites and (future) RS-slope signals. Visible config so the
# windows can be recalibrated without touching the math below.
RS_WINDOWS: dict[str, int] = {
    "5d": 5,
    "10d": 10,
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "12m": 252,
}

# Which windows each investment horizon consumes (primary, secondary). SHORT
# grades must be backed by SHORT-horizon evidence (5D/10D), not a 1M figure;
# MID uses 1M/3M; LONG uses 6M/12M. LONG RS is **trend confirmation**, not
# chase-the-winner — the overextension blocker already guards the chase side.
HORIZON_RS_WINDOWS: dict[str, tuple[str, str]] = {
    "short": ("5d", "10d"),
    "mid": ("1m", "3m"),
    "long": ("6m", "12m"),
}

# Legacy trading-day lookbacks (kept for the unchanged compute_rs_composite path).
_LB_5D = RS_WINDOWS["5d"]
_LB_1M = RS_WINDOWS["1m"]

BENCHMARKS = ("SPY", "QQQ")

# Benchmarks are the single per-refresh fetch, so always pull enough history for
# the 12M (252-session) window regardless of the per-ticker ``period`` hint.
_BENCH_PERIOD = "2y"


@dataclass
class RelativeStrength:
    """Deterministic relative-strength readout for one ticker."""

    ticker: str
    # Legacy flat fields (5D + 1M) — kept byte-compatible for existing consumers.
    ret_5d: Optional[float] = None
    ret_1m: Optional[float] = None
    ret_5d_vs_spy: Optional[float] = None
    ret_1m_vs_spy: Optional[float] = None
    ret_5d_vs_qqq: Optional[float] = None
    ret_1m_vs_qqq: Optional[float] = None
    # Phase 7B — the remaining windows (10D / 3M / 6M / 12M), same naming scheme.
    ret_10d: Optional[float] = None
    ret_3m: Optional[float] = None
    ret_6m: Optional[float] = None
    ret_12m: Optional[float] = None
    ret_10d_vs_spy: Optional[float] = None
    ret_3m_vs_spy: Optional[float] = None
    ret_6m_vs_spy: Optional[float] = None
    ret_12m_vs_spy: Optional[float] = None
    ret_10d_vs_qqq: Optional[float] = None
    ret_3m_vs_qqq: Optional[float] = None
    ret_6m_vs_qqq: Optional[float] = None
    ret_12m_vs_qqq: Optional[float] = None
    above_sma20: Optional[bool] = None
    above_sma50: Optional[bool] = None
    vol_ratio: Optional[float] = None
    # Full per-window snapshot (raw material for future RS-slope signals):
    #   {"5d": {"ret":.., "vs_spy":.., "vs_qqq":..}, "10d": {...}, ...}
    windows: dict = field(default_factory=dict)
    rs_composite: float = 0.5  # neutral when no data (legacy 5D+1M roll-up)
    # Per-horizon composites: each horizon's own windows (None until computed, so
    # legacy consumers that pre-date 7B fall back to rs_composite unchanged).
    rs_short: Optional[float] = None
    rs_mid: Optional[float] = None
    rs_long: Optional[float] = None
    # True when 12M could not be computed (≤1y cached history) and LONG degraded
    # to the 6M window.
    rs_window_degraded: bool = False
    data_source: str = "fixture"  # "live" | "fixture"

    def to_dict(self) -> dict:
        return asdict(self)

    def composite_for(self, horizon: str) -> float:
        """The RS composite the given horizon's weight table should consume.

        Returns the horizon-specific composite when 7B has computed it, otherwise
        falls back to the legacy ``rs_composite`` (so pre-7B RS objects and tests
        score byte-identically)."""
        val = {"short": self.rs_short, "mid": self.rs_mid,
               "long": self.rs_long}.get(horizon)
        return self.rs_composite if val is None else val


# ---------------------------------------------------------------------------
# Pure numeric helpers (no I/O)
# ---------------------------------------------------------------------------

def _finite(x) -> Optional[float]:
    try:
        v = float(x)
        return v if v == v and v not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None


def _pct_return(closes, lookback: int) -> Optional[float]:
    """Trailing pct return over ``lookback`` bars, as a fraction (e.g. 0.05).

    ``closes`` is any sequence-like of prices (pandas Series or list). Returns
    ``None`` when there is not enough history or the base price is non-positive.
    """
    try:
        seq = list(closes)
    except TypeError:
        return None
    if len(seq) < lookback + 1:
        return None
    last = _finite(seq[-1])
    base = _finite(seq[-1 - lookback])
    if last is None or base is None or base <= 0:
        return None
    return last / base - 1.0


def _sma(closes, period: int) -> Optional[float]:
    try:
        seq = [c for c in (_finite(x) for x in list(closes)[-period:]) if c is not None]
    except TypeError:
        return None
    if len(seq) < period:
        return None
    return sum(seq) / len(seq)


def _volume_ratio(volumes, period: int = 20) -> Optional[float]:
    """Most-recent volume vs the trailing ``period``-bar average."""
    try:
        seq = [v for v in (_finite(x) for x in list(volumes)) if v is not None]
    except TypeError:
        return None
    if len(seq) < period + 1:
        return None
    recent = seq[-1]
    avg = sum(seq[-period - 1:-1]) / period
    if avg <= 0:
        return None
    return recent / avg


def _closes_volumes(df):
    """Extract (closes, volumes) lists from an OHLCV DataFrame-like object.

    Accepts a pandas DataFrame with ``Close`` / ``Volume`` columns or a plain
    dict of sequences. Fail-closed -> ([], []).
    """
    try:
        closes = list(df["Close"])
    except Exception:  # noqa: BLE001
        closes = []
    try:
        volumes = list(df["Volume"])
    except Exception:  # noqa: BLE001
        volumes = []
    return closes, volumes


def _close_series(df):
    """The Close column as a pandas Series WITH its (date) index, or None.

    Unlike :func:`_closes_volumes` (which discards the index), this preserves the
    DatetimeIndex needed for date-aligned excess returns. Fail-closed → None."""
    try:
        s = df["Close"]
        return s if hasattr(s, "index") and hasattr(s, "dropna") else None
    except Exception:  # noqa: BLE001
        return None


def _is_dated(series) -> bool:
    """True when ``series`` carries a real DatetimeIndex (so alignment is meaningful)."""
    try:
        import pandas as pd  # lazy: frames are already pandas where this matters
        return isinstance(series.index, pd.DatetimeIndex)
    except Exception:  # noqa: BLE001
        return False


def _aligned_window_returns(ticker_series, bench_series, lookback: int):
    """(ticker_ret, bench_ret) over ``lookback`` bars on the COMMON date index.

    Inner-joins the two series on their dates, sorts, drops NaNs, then computes
    both returns over the same aligned span — so a halted/missing ticker session
    never compares mismatched effective dates. Returns ``(None, None)`` when either
    series lacks a DatetimeIndex or the aligned span is too short (the caller then
    degrades honestly: 12M→6M flag / rs_window_degraded)."""
    if not (_is_dated(ticker_series) and _is_dated(bench_series)):
        return None, None
    try:
        common = ticker_series.index.intersection(bench_series.index)
        if len(common) < lookback + 1:
            return None, None
        t = ticker_series.reindex(common).dropna().sort_index()
        b = bench_series.reindex(common).dropna().sort_index()
        common2 = t.index.intersection(b.index)
        if len(common2) < lookback + 1:
            return None, None
        t = t.reindex(common2).sort_index()
        b = b.reindex(common2).sort_index()
        return _pct_return(list(t), lookback), _pct_return(list(b), lookback)
    except Exception:  # noqa: BLE001
        return None, None


def compute_rs_composite(rs: RelativeStrength) -> float:
    """Roll the RS fields up into a single [0,1] score (deterministic).

    Starts neutral (0.5) and nudges up/down on each available signal. Missing
    inputs simply do not move the score. Designed so a clear leader lands near
    0.8–1.0 and a clear laggard near 0.0–0.2.
    """
    score = 0.5
    # 1-month excess returns carry the most weight (trend), 5-day less (noise).
    for excess, up, dn in (
        (rs.ret_1m_vs_spy, 0.12, 0.12),
        (rs.ret_1m_vs_qqq, 0.12, 0.12),
        (rs.ret_5d_vs_spy, 0.05, 0.05),
        (rs.ret_5d_vs_qqq, 0.05, 0.05),
    ):
        if excess is None:
            continue
        score += up if excess > 0 else -dn
    if rs.above_sma20 is True:
        score += 0.05
    elif rs.above_sma20 is False:
        score -= 0.05
    if rs.above_sma50 is True:
        score += 0.05
    elif rs.above_sma50 is False:
        score -= 0.05
    if rs.vol_ratio is not None and rs.vol_ratio > 1.2:
        score += 0.04
    return max(0.0, min(1.0, round(score, 4)))


def _window_excess(rs: "RelativeStrength", window: str, bench: str):
    """Read one window's excess vs a benchmark from the windows snapshot."""
    rec = (rs.windows or {}).get(window) or {}
    return rec.get(f"vs_{bench}")


def compute_horizon_composite(rs: "RelativeStrength", horizon: str) -> Optional[float]:
    """A [0,1] RS composite from ``horizon``'s own windows (primary + secondary).

    Mirrors :func:`compute_rs_composite`'s nudging structure but draws on the
    horizon's window pair (e.g. SHORT = 5D primary + 10D secondary). The primary
    window carries 0.12 per benchmark, the secondary 0.06; SMA / volume nudges are
    shared. Returns ``None`` when neither window produced any excess reading (so
    the caller leaves the field unset and falls back to ``rs_composite``)."""
    primary, secondary = HORIZON_RS_WINDOWS[horizon]
    score = 0.5
    seen = False
    for window, up, dn in ((primary, 0.12, 0.12), (secondary, 0.06, 0.06)):
        for bench in ("spy", "qqq"):
            excess = _window_excess(rs, window, bench)
            if excess is None:
                continue
            seen = True
            score += up if excess > 0 else -dn
    if rs.above_sma20 is True:
        score += 0.05
    elif rs.above_sma20 is False:
        score -= 0.05
    if rs.above_sma50 is True:
        score += 0.05
    elif rs.above_sma50 is False:
        score -= 0.05
    if rs.vol_ratio is not None and rs.vol_ratio > 1.2:
        score += 0.04
    if not seen:
        return None
    return max(0.0, min(1.0, round(score, 4)))


def compute_horizon_composites(rs: "RelativeStrength") -> None:
    """Fill ``rs_short`` / ``rs_mid`` / ``rs_long`` in place from the windows.

    Also sets ``rs_window_degraded`` when 12M is unavailable (≤1y cached history)
    but 6M is — LONG then rests on the 6M window alone."""
    rs.rs_short = compute_horizon_composite(rs, "short")
    rs.rs_mid = compute_horizon_composite(rs, "mid")
    rs.rs_long = compute_horizon_composite(rs, "long")
    twelve = (rs.windows or {}).get("12m") or {}
    six = (rs.windows or {}).get("6m") or {}
    if twelve.get("ret") is None and six.get("ret") is not None:
        rs.rs_window_degraded = True


def compute_relative_strength(ticker: str, df, bench_returns: dict,
                              bench_closes: Optional[dict] = None) -> RelativeStrength:
    """Build a :class:`RelativeStrength` from one ticker's OHLCV + benchmark map.

    ``bench_returns`` is the once-per-refresh benchmark map produced by
    :func:`benchmark_returns`, e.g. ``{"SPY": {"5d": 0.01, "1m": 0.03}, ...}`` —
    the **positional** fallback used when date alignment is not available.

    ``bench_closes`` (Phase 7B fix) is the benchmark **Close Series** map
    (``{"SPY": Series, "QQQ": Series}`` with DatetimeIndex) produced by
    :func:`benchmark_frames`. When supplied AND the ticker frame carries a
    DatetimeIndex, each window's excess is computed on the COMMON date index
    (inner join) so a halted/missing ticker session never compares mismatched
    effective dates; the sufficiency check then runs on the ALIGNED length. When
    alignment is unavailable (no dates / fixture frames), the positional
    ``bench_returns`` path is used — preserving 7A byte-compat.

    Pure (no I/O): ``df`` is the already-fetched ticker history. Fail-closed.
    """
    closes, volumes = _closes_volumes(df)
    rs = RelativeStrength(ticker=str(ticker).upper())
    if not closes:
        rs.rs_composite = compute_rs_composite(rs)
        return rs

    spy = bench_returns.get("SPY", {}) if bench_returns else {}
    qqq = bench_returns.get("QQQ", {}) if bench_returns else {}
    ts = _close_series(df)
    spy_series = (bench_closes or {}).get("SPY")
    qqq_series = (bench_closes or {}).get("QQQ")
    # Date alignment is active only when the ticker AND at least one benchmark are
    # dated. Fixture/no-date frames fall through to the positional path unchanged.
    aligned_mode = ts is not None and _is_dated(ts) and (
        _is_dated(spy_series) or _is_dated(qqq_series))

    # ── Every window: own return + excess vs SPY/QQQ → flat fields + snapshot ──
    for window, lookback in RS_WINDOWS.items():
        if aligned_mode:
            t_spy, b_spy = _aligned_window_returns(ts, spy_series, lookback)
            t_qqq, b_qqq = _aligned_window_returns(ts, qqq_series, lookback)
            # Canonical own-return reflects the aligned span (so sufficiency /
            # the 12M→6M degrade are honest about missing sessions).
            ret = t_spy if t_spy is not None else t_qqq
            vs_spy = (round(t_spy - b_spy, 4)
                      if t_spy is not None and b_spy is not None else None)
            vs_qqq = (round(t_qqq - b_qqq, 4)
                      if t_qqq is not None and b_qqq is not None else None)
        else:
            ret = _pct_return(closes, lookback)
            vs_spy = (round(ret - spy[window], 4)
                      if ret is not None and spy.get(window) is not None else None)
            vs_qqq = (round(ret - qqq[window], 4)
                      if ret is not None and qqq.get(window) is not None else None)
        rs.windows[window] = {"ret": ret, "vs_spy": vs_spy, "vs_qqq": vs_qqq}
        setattr(rs, f"ret_{window}", ret)
        setattr(rs, f"ret_{window}_vs_spy", vs_spy)
        setattr(rs, f"ret_{window}_vs_qqq", vs_qqq)

    last = _finite(closes[-1])
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    if last is not None and sma20 is not None:
        rs.above_sma20 = last >= sma20
    if last is not None and sma50 is not None:
        rs.above_sma50 = last >= sma50
    rs.vol_ratio = _volume_ratio(volumes, 20)
    if rs.vol_ratio is not None:
        rs.vol_ratio = round(rs.vol_ratio, 2)

    rs.data_source = "live"
    rs.rs_composite = compute_rs_composite(rs)
    compute_horizon_composites(rs)
    return rs


# ---------------------------------------------------------------------------
# I/O orchestration (benchmarks fetched once; per-ticker history is a cache hit)
# ---------------------------------------------------------------------------

def _default_ohlcv_fn(ticker: str, period: str = "1y"):
    """Lazy adapter onto the cached Streamlit loader; fail-closed -> None."""
    try:
        from ui_utils import load_ohlcv

        return load_ohlcv(ticker, period)
    except Exception:  # noqa: BLE001
        return None


def benchmark_returns(ohlcv_fn: Optional[Callable] = None,
                      period: str = "6mo") -> dict:
    """Fetch SPY and QQQ **once** and return their returns over every RS window.

    ``{"SPY": {"5d": <frac|None>, "10d": ..., "1m": ..., "3m": ..., "6m": ...,
    "12m": ...}, "QQQ": {...}}``. Benchmarks pull ~2y so the 12M window is
    computable; the ``period`` hint is honored only as a lower bound."""
    fn = ohlcv_fn or _default_ohlcv_fn
    fetch_period = _BENCH_PERIOD if period in (None, "6mo", "1y") else period
    out: dict = {}
    for bench in BENCHMARKS:
        closes = []
        try:
            df = fn(bench, fetch_period)
            if df is not None:
                closes, _ = _closes_volumes(df)
        except Exception:  # noqa: BLE001
            closes = []
        out[bench] = {w: _pct_return(closes, lb) for w, lb in RS_WINDOWS.items()}
    return out


def benchmark_frames(ohlcv_fn: Optional[Callable] = None,
                     period: str = "6mo") -> dict:
    """Fetch SPY and QQQ **once** and return their dated Close Series.

    ``{"SPY": <Close Series|None>, "QQQ": <Close Series|None>}`` — the raw material
    for date-aligned excess returns (Phase 7B fix). Same single-fetch discipline
    and ~2y depth as :func:`benchmark_returns`."""
    fn = ohlcv_fn or _default_ohlcv_fn
    fetch_period = _BENCH_PERIOD if period in (None, "6mo", "1y") else period
    out: dict = {}
    for bench in BENCHMARKS:
        try:
            out[bench] = _close_series(fn(bench, fetch_period))
        except Exception:  # noqa: BLE001
            out[bench] = None
    return out


def _returns_from_frames(frames: dict) -> dict:
    """Positional benchmark returns from a ``{sym: Close Series}`` map (fallback)."""
    out: dict = {}
    for bench in BENCHMARKS:
        s = (frames or {}).get(bench)
        closes = list(s) if s is not None else []
        out[bench] = {w: _pct_return(closes, lb) for w, lb in RS_WINDOWS.items()}
    return out


def _default_frame_loader(ticker: str):
    """Cache-only OHLCV read (memory → disk, NO network fetch on miss).

    Reads the already-fetched frame the signal pipeline persisted via
    ``lib.cache_manager`` (data_type ``"ohlcv"``). Returns ``None`` on a cache
    miss — it never triggers a fetch. Fail-closed."""
    try:
        from lib.cache_manager import load as _cache_load

        return _cache_load(str(ticker).upper().strip(), "ohlcv")
    except Exception:  # noqa: BLE001
        return None


def load_cached_frames(tickers, frame_loader: Optional[Callable] = None) -> dict:
    """Build ``{ticker: frame|None}`` from the cache ONLY (no per-ticker fetch)."""
    fl = frame_loader or _default_frame_loader
    out: dict = {}
    for tk in tickers or []:
        sym = str(tk).upper().strip()
        if not sym or sym in out:
            continue
        try:
            out[sym] = fl(sym)
        except Exception:  # noqa: BLE001
            out[sym] = None
    return out


def build_rs_map_cache_only(tickers, *, ohlcv_fn: Optional[Callable] = None,
                            frame_loader: Optional[Callable] = None,
                            bench_returns: Optional[dict] = None,
                            period: str = "1y") -> dict:
    """Production RS entry point for the Cockpit refresh (Fix 2 — network-free).

    The SPY/QQQ benchmark series is the **single** per-refresh fetch (via
    ``ohlcv_fn``). Per-ticker price is read **cache-only** (``frame_loader`` →
    ``lib.cache_manager.load``); a cache miss degrades to a neutral RS
    (``data_source='fixture'``) and never triggers a per-ticker fetch. The
    benchmark Close Series are kept (``benchmark_frames``) so excess returns are
    **date-aligned** against each ticker's own (cached) dates. Returns
    ``{ticker: RelativeStrength}``."""
    bench_frames = benchmark_frames(ohlcv_fn or _default_ohlcv_fn, period)
    bench = bench_returns if bench_returns is not None else _returns_from_frames(bench_frames)
    frames = load_cached_frames(tickers, frame_loader)
    return compute_rs_for_tickers(tickers, bench_returns=bench, cache_only=True,
                                  frames=frames, period=period,
                                  bench_closes=bench_frames)


def compute_rs_for_tickers(tickers, ohlcv_fn: Optional[Callable] = None,
                           bench_returns: Optional[dict] = None,
                           period: str = "6mo", *, cache_only: bool = False,
                           frames: Optional[dict] = None,
                           bench_closes: Optional[dict] = None) -> dict:
    """Compute RS for many tickers, fetching the benchmark series only once.

    The **benchmark** series (SPY/QQQ) is the single per-refresh fetch. Per-ticker
    OHLCV is read via ``ohlcv_fn`` (default: the cached ``ui_utils.load_ohlcv``),
    so history already fetched by the signal pipeline is reused as a cache hit.

    ``cache_only=True`` (Codex #5 — network-free ranking) reads per-ticker price
    ONLY from the supplied ``frames`` dict and NEVER calls the loader for a
    per-ticker fetch: a missing frame degrades to a neutral RS
    (``data_source='fixture'``) rather than triggering network I/O. Returns
    ``{ticker: RelativeStrength}``. Fail-closed per ticker.
    """
    fn = ohlcv_fn or _default_ohlcv_fn
    bench = bench_returns if bench_returns is not None else benchmark_returns(fn, period)
    frames = frames or {}
    out: dict = {}
    for tk in tickers or []:
        sym = str(tk).upper().strip()
        if not sym or sym in out:
            continue
        if cache_only:
            df = frames.get(sym)  # no per-ticker fetch on miss -> degrades
        else:
            try:
                df = fn(sym, period)
            except Exception:  # noqa: BLE001
                df = None
        out[sym] = compute_relative_strength(sym, df, bench, bench_closes=bench_closes)
    return out
