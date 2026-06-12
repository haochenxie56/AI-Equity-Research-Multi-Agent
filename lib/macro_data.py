"""lib/macro_data.py — Phase 6A Live Macro Data Integration.

This module is responsible for **all** live macro data fetching for the Macro
Dashboard (``pages/8_Macro_Dashboard.py``). It is the single place where the
project reaches out to free data sources for current macro conditions:

* yfinance      — price/return data for ETF proxies and ``^VIX`` (no API key).
* FRED          — rates, inflation, credit, dollar, and economic releases
                  (free; requires ``FRED_API_KEY`` from fred.stlouisfed.org).
* Finnhub       — supplementary market news + social sentiment (free tier;
                  reuses the project's existing ``FINNHUB_API_KEY`` and request
                  pattern; only the two allowed endpoints are used).

Design rules (Phase 6A guardrails):

* **Free sources only.** No paid API is called.
* **Fail-closed per metric group.** Every public ``fetch_*`` function is wrapped
  in its own ``try/except``. On *any* failure (missing key, network error, parse
  error, empty data) it returns a deterministic **fixture** fallback whose
  ``data_source`` field is ``"fixture"`` instead of ``"live"``. Functions never
  raise to the caller, so the dashboard can never crash on a data error.
* **Cached.** Public fetch functions are memoized with ``st.cache_data`` and a
  TTL of 900 s (15 minutes) so the page does not hammer the upstream APIs.
* **No execution.** This module produces market *observations* only. It contains
  no broker / order / execution capability and no ``approved_for_execution``
  field anywhere.

CNN Fear & Greed substitution: there is no reliable free CNN Fear & Greed API,
so a **VIX-derived fear/greed proxy** is computed instead (see ``fetch_vix``):
the proxy is the inverse of the trailing-252-day percentile rank of the latest
VIX close, scaled to 0–100. A calm VIX (low percentile) maps to a high
("greed") score; an elevated VIX (high percentile) maps to a low ("fear")
score. This substitution is documented in
``docs/reliability_phase_6a_live_data_integration.md``.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv

# Load .env from the project root (one level up from lib/), matching the
# existing lib/data_fetcher.py convention.
from pathlib import Path as _Path

load_dotenv(_Path(__file__).parent.parent / ".env")

import yfinance as yf  # primary, free, no API key required
import requests  # FRED + Finnhub REST calls (free endpoints only)

# Streamlit is an app dependency; importing it here is safe in both the app and
# in plain scripts. ``st.cache_data`` works outside a running server (it simply
# executes the body), so the module remains importable and testable offline.
import streamlit as st


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

# Free public endpoints (no paid tier used).
_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
_FINNHUB_NEWS = "https://finnhub.io/api/v1/news"
_FINNHUB_SOCIAL = "https://finnhub.io/api/v1/stock/social-sentiment"

# ETF proxies fetched from yfinance for cross-asset return context.
ETF_PROXIES = ("QQQ", "IWM", "SPY", "GLD", "USO", "TLT", "HYG")

# Cache TTL — 15 minutes, as required by Phase 6A.
_CACHE_TTL = 900

# Network timeouts kept tight so a degraded network fails fast and falls back to
# fixture rather than hanging a page render.
_HTTP_TIMEOUT = 10
_YF_TIMEOUT = 12

_LIVE = "live"
_FIXTURE = "fixture"


def _now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string (no microseconds)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _history_from_desc(pairs, n: int = 6, stride: int = 21, ndigits: int = 2) -> list:
    """Sample a small trend series from a most-recent-first ``(date, value)`` list.

    Picks every ``stride``-th point (e.g. ~21 trading days ≈ monthly for daily
    data) up to ``n`` points, then reverses to oldest->newest. Used purely to
    slice ALREADY-FETCHED data into a tiny trend table — no new API calls.
    """
    out: list = []
    i = 0
    while len(out) < n and i < len(pairs):
        date, value = pairs[i]
        try:
            out.append({"date": str(date), "value": round(float(value), ndigits)})
        except (TypeError, ValueError):
            pass
        i += stride
    out.reverse()
    return out


# ---------------------------------------------------------------------------
# Result dataclasses — one per metric group + the unified MacroDataResult.
# Every group carries a ``data_source`` field ("live" | "fixture") and an
# ``as_of`` freshness marker.
# ---------------------------------------------------------------------------


@dataclass
class VixResult:
    """VIX level + 1M change + VIX-derived fear/greed proxy (0–100)."""

    value: Optional[float]
    change_1m: Optional[float]
    fear_greed: Optional[float]
    data_source: str
    as_of: Optional[str] = None
    # Small recent history (oldest->newest) for the trend table: [{"date","value"}].
    history: list = field(default_factory=list)


@dataclass
class RatesResult:
    """Treasury yields and breakeven inflation from FRED."""

    yield_10y: Optional[float]
    yield_2y: Optional[float]
    spread_10y_2y: Optional[float]
    breakeven_10y: Optional[float]
    data_source: str
    as_of: Optional[str] = None
    # Recent 10Y-yield history (oldest->newest): [{"date","value"}].
    history: list = field(default_factory=list)


@dataclass
class CreditResult:
    """High-yield credit spread (FRED BAMLH0A0HYM2, in percentage points)."""

    hy_spread: Optional[float]
    data_source: str
    as_of: Optional[str] = None
    # Recent HY-spread history (oldest->newest): [{"date","value"}].
    history: list = field(default_factory=list)


@dataclass
class DollarResult:
    """Broad US dollar index proxy (FRED DTWEXBGS) + 1M change."""

    value: Optional[float]
    change_1m: Optional[float]
    data_source: str
    as_of: Optional[str] = None
    # Recent broad-dollar history (oldest->newest): [{"date","value"}].
    history: list = field(default_factory=list)


@dataclass
class EtfReturnsResult:
    """Trailing 1M and 3M price returns (pct) for the ETF proxy set."""

    returns_1m: dict = field(default_factory=dict)
    returns_3m: dict = field(default_factory=dict)
    data_source: str = _FIXTURE
    as_of: Optional[str] = None
    # Per-ticker cumulative-return history (oldest->newest), for the trend chart:
    #   {"QQQ": [{"date","value"}], ...}  value = cumulative % return over window.
    history: dict = field(default_factory=dict)


@dataclass
class EconomicReleasesResult:
    """Latest NFP / CPI / PPI values and most-recent release dates from FRED."""

    nfp: Optional[float]
    nfp_date: Optional[str]
    cpi: Optional[float]
    cpi_date: Optional[str]
    ppi: Optional[float]
    ppi_date: Optional[str]
    data_source: str
    as_of: Optional[str] = None
    # Month-aligned recent history (oldest->newest): [{"date","NFP","CPI","PPI"}].
    history: list = field(default_factory=list)


@dataclass
class SentimentResult:
    """Supplementary market sentiment from Finnhub (social + general news).

    Falls back to the VIX-derived fear/greed proxy when Finnhub is unavailable.
    """

    score: Optional[float]  # 0–100 scale, normalized to the fear/greed convention
    label: Optional[str]  # human-readable bucket (e.g. "greed" / "fear" / "neutral")
    symbols: list = field(default_factory=list)
    news_headlines: list = field(default_factory=list)
    data_source: str = _FIXTURE
    as_of: Optional[str] = None


@dataclass
class MacroDataResult:
    """Unified macro data snapshot returned by :func:`fetch_all_macro`.

    ``data_coverage`` is the fraction (0.0–1.0) of the seven metric groups that
    were successfully fetched **live** (``data_source == "live"``).
    """

    vix: VixResult
    rates: RatesResult
    credit: CreditResult
    dollar: DollarResult
    etf_returns: EtfReturnsResult
    economic_releases: EconomicReleasesResult
    sentiment: SentimentResult
    timestamp: str
    data_coverage: float


# ---------------------------------------------------------------------------
# Deterministic fixture fallbacks — used whenever a live fetch fails. These keep
# the dashboard populated (never empty / broken) and are plausible, neutral
# placeholder values. They are clearly marked ``data_source="fixture"``.
# ---------------------------------------------------------------------------


def _fx_hist(values, ndigits: int = 2) -> list:
    """Build a small fixture history (oldest->newest) with placeholder dates."""
    dates = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-05"]
    out = []
    for i, v in enumerate(values):
        out.append({"date": dates[i] if i < len(dates) else f"t-{len(values) - i}",
                    "value": round(float(v), ndigits)})
    return out


def _vix_fixture() -> VixResult:
    return VixResult(
        value=16.5, change_1m=-0.8, fear_greed=58.0, data_source=_FIXTURE, as_of=None,
        history=_fx_hist([18.2, 17.5, 19.1, 16.9, 17.2, 16.5]),
    )


def _rates_fixture() -> RatesResult:
    return RatesResult(
        yield_10y=4.30,
        yield_2y=4.05,
        spread_10y_2y=0.25,
        breakeven_10y=2.30,
        data_source=_FIXTURE,
        as_of=None,
        # Month-aligned 10Y / 2Y / spread trend rows (oldest->newest).
        history=[
            {"date": "2026-01", "10Y": 4.05, "2Y": 4.30, "spread": -0.25},
            {"date": "2026-02", "10Y": 4.15, "2Y": 4.25, "spread": -0.10},
            {"date": "2026-03", "10Y": 4.40, "2Y": 4.20, "spread": 0.20},
            {"date": "2026-04", "10Y": 4.35, "2Y": 4.10, "spread": 0.25},
            {"date": "2026-05", "10Y": 4.25, "2Y": 4.05, "spread": 0.20},
            {"date": "2026-05", "10Y": 4.30, "2Y": 4.05, "spread": 0.25},
        ],
    )


def _credit_fixture() -> CreditResult:
    return CreditResult(
        hy_spread=3.20, data_source=_FIXTURE, as_of=None,
        history=_fx_hist([3.60, 3.45, 3.30, 3.25, 3.15, 3.20]),
    )


def _dollar_fixture() -> DollarResult:
    return DollarResult(
        value=121.0, change_1m=0.4, data_source=_FIXTURE, as_of=None,
        history=_fx_hist([119.5, 120.2, 120.8, 121.4, 120.6, 121.0]),
    )


def _etf_returns_fixture() -> EtfReturnsResult:
    one_m = {"QQQ": 2.1, "IWM": 1.2, "SPY": 1.8, "GLD": 0.9, "USO": -1.5, "TLT": -0.6, "HYG": 0.4}
    three_m = {"QQQ": 6.0, "IWM": 3.0, "SPY": 5.2, "GLD": 4.0, "USO": -3.0, "TLT": -1.5, "HYG": 1.1}
    _dts = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-05"]
    _cum = {
        "QQQ": [0.0, 1.2, 3.1, 4.0, 5.2, 6.0], "IWM": [0.0, 0.8, 1.5, 2.1, 2.6, 3.0],
        "SPY": [0.0, 1.0, 2.6, 3.4, 4.5, 5.2], "GLD": [0.0, 0.9, 1.8, 2.7, 3.4, 4.0],
        "USO": [0.0, -0.6, -1.2, -2.0, -2.6, -3.0], "TLT": [0.0, -0.3, -0.7, -1.0, -1.3, -1.5],
        "HYG": [0.0, 0.2, 0.5, 0.7, 0.9, 1.1],
    }
    history = {
        tkr: [{"date": _dts[i], "value": vals[i]} for i in range(len(vals))]
        for tkr, vals in _cum.items()
    }
    return EtfReturnsResult(
        returns_1m=one_m, returns_3m=three_m, data_source=_FIXTURE, as_of=None,
        history=history,
    )


def _economic_releases_fixture() -> EconomicReleasesResult:
    return EconomicReleasesResult(
        nfp=None,
        nfp_date=None,
        cpi=None,
        cpi_date=None,
        ppi=None,
        ppi_date=None,
        data_source=_FIXTURE,
        as_of=None,
        history=[],
    )


def _sentiment_fixture() -> SentimentResult:
    return SentimentResult(
        score=58.0,
        label="neutral",
        symbols=[],
        news_headlines=[],
        data_source=_FIXTURE,
        as_of=None,
    )


def _fear_greed_label(score: Optional[float]) -> str:
    """Map a 0–100 fear/greed score to a human-readable bucket."""
    if score is None:
        return "unknown"
    if score >= 75:
        return "extreme_greed"
    if score >= 55:
        return "greed"
    if score > 45:
        return "neutral"
    if score > 25:
        return "fear"
    return "extreme_fear"


# Lightweight keyword sentiment for general-market headlines. This mirrors the
# spirit of lib/data_fetcher._headline_sentiment but is kept local so this module
# carries no import dependency on data_fetcher (which uses a bare
# ``from cache_manager import ...`` that only resolves with lib/ on sys.path).
_POS_WORDS = (
    "beat", "beats", "surge", "rally", "gain", "gains", "record", "growth",
    "strong", "upgrade", "jump", "soar", "rise", "rises", "boost", "optimism",
    "bullish", "outperform", "tops", "rebound", "recovery", "ease", "eases",
)
_NEG_WORDS = (
    "miss", "misses", "plunge", "slump", "fall", "falls", "drop", "loss",
    "weak", "downgrade", "crash", "fear", "recession", "selloff", "sell-off",
    "tumble", "warn", "warns", "cut", "cuts", "bearish", "slowdown", "default",
    "crisis", "layoff", "layoffs", "sink", "slide",
)


def _headlines_sentiment_score(headlines: list) -> Optional[float]:
    """Map a list of headlines to a 0–100 fear/greed-style score (50 = neutral).

    Returns ``None`` when there are no headlines. With headlines but no matched
    keywords, returns a neutral 50.0 (we still have live news, just neutral tone).
    """
    if not headlines:
        return None
    pos = 0
    neg = 0
    for h in headlines:
        low = str(h).lower()
        pos += sum(1 for w in _POS_WORDS if w in low)
        neg += sum(1 for w in _NEG_WORDS if w in low)
    total = pos + neg
    if total == 0:
        return 50.0
    ratio = (pos - neg) / total  # -1..1
    return round((ratio + 1.0) / 2.0 * 100.0, 1)


# ---------------------------------------------------------------------------
# Low-level FRED helper (free endpoint).
# ---------------------------------------------------------------------------


def _fred_observations(series_id: str, limit: int = 30, retries: int = 3) -> list:
    """Return most-recent-first ``(date, float_value)`` pairs for a FRED series.

    Returns an empty list if ``FRED_API_KEY`` is absent. Skips observations whose
    value is "." (FRED's missing marker).

    FRED throttles rapid bursts with **HTTP 429** ("Too Many Requests") even well
    under its documented 120 req/min budget. Because the dashboard fires several
    FRED series on first load, this helper retries on 429 (and other transient
    errors) with a short exponential back-off. If every attempt fails it re-raises
    the last exception so the calling ``fetch_*`` function can fail closed to its
    fixture fallback. When no key is set it returns ``[]`` immediately (no
    network, no sleeps — keeps offline tests fast).
    """
    if not FRED_API_KEY:
        return []
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            resp = requests.get(
                _FRED_BASE,
                params={
                    "series_id": series_id,
                    "api_key": FRED_API_KEY,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": limit,
                },
                timeout=_HTTP_TIMEOUT,
            )
            # Back off and retry on rate-limit responses.
            if resp.status_code == 429:
                last_exc = requests.HTTPError(f"429 Too Many Requests ({series_id})")
                time.sleep(0.6 * (attempt + 1))
                continue
            resp.raise_for_status()
            obs = resp.json().get("observations", [])
            out: list = []
            for row in obs:
                raw = row.get("value", ".")
                if raw in (".", "", None):
                    continue
                try:
                    out.append((row.get("date"), float(raw)))
                except (TypeError, ValueError):
                    continue
            return out
        except Exception as exc:  # noqa: BLE001 — retry transient errors
            last_exc = exc
            time.sleep(0.4 * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    return []


# ---------------------------------------------------------------------------
# Public fetch functions — each individually wrapped in try/except and cached.
# ---------------------------------------------------------------------------


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def fetch_vix() -> VixResult:
    """Fetch the latest VIX value, its 1M change, and a VIX-derived fear/greed
    proxy (0–100, the inverse of the trailing-252-day VIX percentile).

    Fail-closed: returns a fixture VixResult on any error.
    """
    try:
        hist = yf.Ticker("^VIX").history(period="1y", timeout=_YF_TIMEOUT)
        closes = hist["Close"].dropna()
        if closes.empty:
            return _vix_fixture()
        latest = float(closes.iloc[-1])
        # 1-month change ~ 21 trading days.
        change_1m = None
        if len(closes) > 21:
            prior = float(closes.iloc[-22])
            change_1m = round(latest - prior, 2)
        # VIX-derived fear/greed proxy: inverse percentile rank over trailing
        # 252 trading days, scaled to 0–100. Calm VIX -> high (greed) score.
        window = closes.tail(252)
        pct_rank = float((window <= latest).sum()) / float(len(window))
        fear_greed = round((1.0 - pct_rank) * 100.0, 1)
        as_of = str(closes.index[-1].date()) if hasattr(closes.index[-1], "date") else None
        # Trend history (~monthly) sliced from the already-fetched 1y series.
        vix_pairs = [
            (str(idx.date()) if hasattr(idx, "date") else str(idx), float(val))
            for idx, val in zip(reversed(list(closes.index)), reversed(list(closes.values)))
        ]
        history = _history_from_desc(vix_pairs, n=6, stride=21, ndigits=2)
        return VixResult(
            value=round(latest, 2),
            change_1m=change_1m,
            fear_greed=fear_greed,
            data_source=_LIVE,
            as_of=as_of,
            history=history,
        )
    except Exception:  # noqa: BLE001 — fail-closed to fixture
        return _vix_fixture()


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def fetch_rates() -> RatesResult:
    """Fetch 10Y / 2Y Treasury yields, the 10Y-2Y spread, and the 10Y breakeven
    inflation rate from FRED (DGS10, DGS2, T10YIE).

    Fail-closed: returns a fixture RatesResult if FRED is unavailable.
    """
    try:
        # DGS10 / DGS2 fetched with a wider window so we can slice a trend and
        # build a date-aligned 2Y + spread history (one request per series).
        ten = _fred_observations("DGS10", limit=140)
        two = _fred_observations("DGS2", limit=140)
        if not ten or not two:
            return _rates_fixture()
        y10_date, y10 = ten[0]
        _, y2 = two[0]
        # Breakeven is an optional sub-field — its failure (e.g. a 429) must not
        # discard the successful 10Y / 2Y readings.
        try:
            be = _fred_observations("T10YIE", limit=10)
        except Exception:  # noqa: BLE001
            be = []
        breakeven = be[0][1] if be else None
        # Month-aligned 10Y / 2Y / spread trend rows from the same observations.
        _two_map = {d: v for d, v in two}
        history = []
        for _row in _history_from_desc(ten, n=6, stride=21, ndigits=2):
            _d = _row["date"]
            _r = {"date": _d, "10Y": _row["value"]}
            _v2 = _two_map.get(_d)
            if _v2 is not None:
                _r["2Y"] = round(_v2, 2)
                _r["spread"] = round(_row["value"] - _v2, 2)
            history.append(_r)
        return RatesResult(
            yield_10y=round(y10, 2),
            yield_2y=round(y2, 2),
            spread_10y_2y=round(y10 - y2, 2),
            breakeven_10y=round(breakeven, 2) if breakeven is not None else None,
            data_source=_LIVE,
            as_of=y10_date,
            history=history,
        )
    except Exception:  # noqa: BLE001 — fail-closed to fixture
        return _rates_fixture()


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def fetch_credit() -> CreditResult:
    """Fetch the ICE BofA US High Yield OAS credit spread from FRED
    (BAMLH0A0HYM2, in percentage points).

    Fail-closed: returns a fixture CreditResult if FRED is unavailable.
    """
    try:
        hy = _fred_observations("BAMLH0A0HYM2", limit=140)
        if not hy:
            return _credit_fixture()
        hy_date, hy_val = hy[0]
        history = _history_from_desc(hy, n=6, stride=21, ndigits=2)
        return CreditResult(
            hy_spread=round(hy_val, 2), data_source=_LIVE, as_of=hy_date, history=history
        )
    except Exception:  # noqa: BLE001 — fail-closed to fixture
        return _credit_fixture()


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def fetch_dollar() -> DollarResult:
    """Fetch the broad US dollar index proxy and its 1M change from FRED
    (DTWEXBGS).

    Fail-closed: returns a fixture DollarResult if FRED is unavailable.
    """
    try:
        obs = _fred_observations("DTWEXBGS", limit=140)
        if not obs:
            return _dollar_fixture()
        latest_date, latest = obs[0]
        change_1m = None
        # ~22 business days back for a ~1-month change.
        if len(obs) > 22:
            prior = obs[22][1]
            if prior:
                change_1m = round((latest - prior) / prior * 100.0, 2)
        history = _history_from_desc(obs, n=6, stride=21, ndigits=2)
        return DollarResult(
            value=round(latest, 2),
            change_1m=change_1m,
            data_source=_LIVE,
            as_of=latest_date,
            history=history,
        )
    except Exception:  # noqa: BLE001 — fail-closed to fixture
        return _dollar_fixture()


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def fetch_etf_returns() -> EtfReturnsResult:
    """Fetch trailing 1M and 3M price returns (pct) for the ETF proxy set via
    yfinance (QQQ, IWM, SPY, GLD, USO, TLT, HYG).

    Fail-closed: returns a fixture EtfReturnsResult on any error.
    """
    try:
        data = yf.download(
            list(ETF_PROXIES),
            period="6mo",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False,
            timeout=_YF_TIMEOUT,
        )
        # yf.download returns a column-multiindex when multiple tickers.
        close = data["Close"] if "Close" in data else data
        one_m: dict = {}
        three_m: dict = {}
        history: dict = {}
        as_of = None
        for tkr in ETF_PROXIES:
            try:
                series = close[tkr].dropna() if tkr in close else None
            except Exception:  # noqa: BLE001
                series = None
            if series is None or series.empty:
                continue
            last = float(series.iloc[-1])
            if as_of is None and hasattr(series.index[-1], "date"):
                as_of = str(series.index[-1].date())
            if len(series) > 21:
                base = float(series.iloc[-22])
                if base:
                    one_m[tkr] = round((last - base) / base * 100.0, 2)
            if len(series) > 63:
                base3 = float(series.iloc[-64])
                if base3:
                    three_m[tkr] = round((last - base3) / base3 * 100.0, 2)
            # Cumulative-return trend (~monthly) sliced from the same price series.
            _pairs = [
                (str(idx.date()) if hasattr(idx, "date") else str(idx), float(val))
                for idx, val in zip(reversed(list(series.index)), reversed(list(series.values)))
            ]
            _sampled = _history_from_desc(_pairs, n=6, stride=21, ndigits=4)
            if len(_sampled) >= 2 and _sampled[0]["value"]:
                _b = _sampled[0]["value"]
                history[tkr] = [
                    {"date": s["date"], "value": round((s["value"] / _b - 1.0) * 100.0, 2)}
                    for s in _sampled
                ]
        if not one_m and not three_m:
            return _etf_returns_fixture()
        return EtfReturnsResult(
            returns_1m=one_m, returns_3m=three_m, data_source=_LIVE, as_of=as_of,
            history=history,
        )
    except Exception:  # noqa: BLE001 — fail-closed to fixture
        return _etf_returns_fixture()


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def fetch_economic_releases() -> EconomicReleasesResult:
    """Fetch latest NFP (PAYEMS), CPI (CPIAUCSL), and PPI (PPIACO) values and
    their most-recent release (observation) dates from FRED.

    Fail-closed: returns a fixture EconomicReleasesResult if FRED is unavailable.
    """
    def _safe_obs(series_id: str) -> list:
        # Each release is independent: a per-series failure (e.g. a 429) must not
        # void the others, so a partial live set is still reported live. A 6-month
        # window is fetched (one request each) so the trend table can be sliced.
        try:
            return _fred_observations(series_id, limit=6)
        except Exception:  # noqa: BLE001
            return []

    try:
        nfp = _safe_obs("PAYEMS")
        cpi = _safe_obs("CPIAUCSL")
        ppi = _safe_obs("PPIACO")
        if not nfp and not cpi and not ppi:
            return _economic_releases_fixture()
        # Month-aligned trend history from the already-fetched observations.
        dmap: dict = {}
        for label, lst, nd in (("NFP", nfp, 1), ("CPI", cpi, 2), ("PPI", ppi, 2)):
            for d, v in lst[:6]:
                try:
                    dmap.setdefault(d, {"date": d})[label] = round(float(v), nd)
                except (TypeError, ValueError):
                    continue
        history = [dmap[k] for k in sorted(dmap.keys())][-6:]
        return EconomicReleasesResult(
            nfp=round(nfp[0][1], 1) if nfp else None,
            nfp_date=nfp[0][0] if nfp else None,
            cpi=round(cpi[0][1], 2) if cpi else None,
            cpi_date=cpi[0][0] if cpi else None,
            ppi=round(ppi[0][1], 2) if ppi else None,
            ppi_date=ppi[0][0] if ppi else None,
            data_source=_LIVE,
            as_of=_now_iso(),
            history=history,
        )
    except Exception:  # noqa: BLE001 — fail-closed to fixture
        return _economic_releases_fixture()


def _vix_proxy_sentiment() -> SentimentResult:
    """Fixture sentiment derived from the VIX fear/greed proxy (fail-closed)."""
    try:
        score = fetch_vix().fear_greed
    except Exception:  # noqa: BLE001
        score = _sentiment_fixture().score
    return SentimentResult(
        score=score,
        label=_fear_greed_label(score),
        symbols=[],
        news_headlines=[],
        data_source=_FIXTURE,
        as_of=None,
    )


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def fetch_market_sentiment() -> SentimentResult:
    """Fetch supplementary market sentiment from Finnhub.

    Uses only the two allowed Finnhub endpoints and the project's existing
    request pattern (``requests.get`` + ``token`` query param + short timeout +
    ``raise_for_status`` + try/except), matching ``lib/data_fetcher.py``:

    * ``/stock/social-sentiment`` (SPY, QQQ) — NOTE: this is a **premium** Finnhub
      endpoint. Free-tier keys receive HTTP 403 ("You don't have access to this
      resource"). It is therefore treated as **best-effort**: a per-symbol
      failure is swallowed and does not abort the function.
    * ``/news?category=general`` — the **free** market-news feed. This is the
      **primary live sentiment signal**: when it returns headlines, the result is
      ``data_source="live"`` and the score is derived from headline tone (or from
      premium social mentions when those are available).

    Fail-closed: if neither Finnhub source returns data (no key, network error,
    or both endpoints fail), falls back to the VIX-derived fear/greed proxy with
    ``data_source="fixture"`` — the function never raises.
    """
    if not FINNHUB_API_KEY:
        # No key — fall back to the VIX-derived fear/greed proxy.
        return _vix_proxy_sentiment()

    try:
        symbols = ["SPY", "QQQ"]
        got_live = False

        # 1) Social sentiment — PREMIUM endpoint (free keys get HTTP 403), so it
        #    is best-effort only. Any per-symbol failure is swallowed; we never
        #    let it abort the free news path below.
        mention_score = 0.0
        mention_total = 0.0
        social_symbols: list = []
        for sym in symbols:
            try:
                resp = requests.get(
                    _FINNHUB_SOCIAL,
                    params={"symbol": sym, "token": FINNHUB_API_KEY},
                    timeout=_HTTP_TIMEOUT,
                )
                resp.raise_for_status()
                payload = resp.json()
                if not isinstance(payload, dict):
                    continue
                sym_has = False
                for channel in ("reddit", "twitter"):
                    for row in payload.get(channel, []) or []:
                        pos = float(row.get("positiveMention", 0) or 0)
                        neg = float(row.get("negativeMention", 0) or 0)
                        mention_score += pos - neg
                        mention_total += pos + neg
                        sym_has = True
                if sym_has:
                    social_symbols.append(sym)
                    got_live = True
            except Exception:  # noqa: BLE001 — premium endpoint; best-effort only
                continue

        # 2) General market news — FREE endpoint and the primary live signal.
        headlines: list = []
        try:
            news_resp = requests.get(
                _FINNHUB_NEWS,
                params={"category": "general", "token": FINNHUB_API_KEY},
                timeout=_HTTP_TIMEOUT,
            )
            news_resp.raise_for_status()
            raw_news = news_resp.json()
            if isinstance(raw_news, list):
                headlines = [
                    n.get("headline", "") for n in raw_news[:20] if n.get("headline")
                ]
                if headlines:
                    got_live = True
        except Exception:  # noqa: BLE001 — news is best-effort too
            headlines = []

        if not got_live:
            # Neither Finnhub source returned live data — fall back to VIX proxy.
            return _vix_proxy_sentiment()

        # Prefer premium social mentions when present; otherwise derive the score
        # from the free news headlines' tone.
        if mention_total > 0:
            ratio = mention_score / mention_total  # -1..1
            score = round((ratio + 1.0) / 2.0 * 100.0, 1)
            used_symbols = social_symbols or symbols
        else:
            score = _headlines_sentiment_score(headlines)
            used_symbols = []  # market-wide news, not symbol-specific
            if score is None:
                score = fetch_vix().fear_greed

        return SentimentResult(
            score=score,
            label=_fear_greed_label(score),
            symbols=used_symbols,
            news_headlines=headlines[:5],
            data_source=_LIVE,
            as_of=_now_iso(),
        )
    except Exception:  # noqa: BLE001 — fail-closed to VIX-derived proxy
        return _vix_proxy_sentiment()


# Seven metric groups contribute to data_coverage.
_COVERAGE_GROUPS = (
    "vix",
    "rates",
    "credit",
    "dollar",
    "etf_returns",
    "economic_releases",
    "sentiment",
)


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def fetch_all_macro() -> MacroDataResult:
    """Call every ``fetch_*`` function in sequence and assemble a unified
    :class:`MacroDataResult`.

    Each underlying fetch is already individually fail-closed, so this function
    cannot crash on a single source failure. ``data_coverage`` is the fraction of
    the seven metric groups that were fetched live.
    """
    try:
        vix = fetch_vix()
        rates = fetch_rates()
        credit = fetch_credit()
        dollar = fetch_dollar()
        etf = fetch_etf_returns()
        releases = fetch_economic_releases()
        sentiment = fetch_market_sentiment()
    except Exception:  # noqa: BLE001 — fully fail-closed (every group -> fixture)
        vix = _vix_fixture()
        rates = _rates_fixture()
        credit = _credit_fixture()
        dollar = _dollar_fixture()
        etf = _etf_returns_fixture()
        releases = _economic_releases_fixture()
        sentiment = _sentiment_fixture()

    groups = {
        "vix": vix,
        "rates": rates,
        "credit": credit,
        "dollar": dollar,
        "etf_returns": etf,
        "economic_releases": releases,
        "sentiment": sentiment,
    }
    live_count = sum(
        1 for name in _COVERAGE_GROUPS if getattr(groups[name], "data_source", _FIXTURE) == _LIVE
    )
    coverage = round(live_count / float(len(_COVERAGE_GROUPS)), 4)

    return MacroDataResult(
        vix=vix,
        rates=rates,
        credit=credit,
        dollar=dollar,
        etf_returns=etf,
        economic_releases=releases,
        sentiment=sentiment,
        timestamp=_now_iso(),
        data_coverage=coverage,
    )


# ---------------------------------------------------------------------------
# Money-market liquidity (FRED) — DISPLAY-ONLY, fetched ON DEMAND.
#
# Deliberately SEPARATE from MacroDataResult / fetch_all_macro: this group is
# rendered only on the Macro Dashboard Liquidity tab and is NEVER written to the
# daily snapshot _meta by design. classify_regime + write_daily_snapshot consume
# MacroDataResult, which does NOT include this group; the daily snapshot persists
# only the regime string + the fragility fields. Mirrors the existing fetch_<group>
# pattern: a data_source-tagged dataclass, @st.cache_data, fail-closed to a fixture,
# reusing _fred_observations' own retry/backoff (no new throttling, no new key).
# ---------------------------------------------------------------------------


@dataclass
class LiquidityResult:
    """Money-market plumbing levels from FRED (display-only):

    * ``sofr``     — SOFR secured overnight financing rate (%).
    * ``on_rrp``   — overnight reverse-repo volume, RRPONTSYD ($B).
    * ``tga``      — Treasury General Account balance, WTREGEN ($B).
    * ``reserves`` — aggregate bank reserves, WRESBAL ($B).

    Carries ``data_source`` ("live"/"fixture") + ``as_of`` like every other macro
    group. NOT part of :class:`MacroDataResult` — it is fetched on demand from the
    Macro Dashboard and never persisted to the snapshot _meta.
    """

    sofr: Optional[float]
    on_rrp: Optional[float]
    tga: Optional[float]
    reserves: Optional[float]
    data_source: str
    as_of: Optional[str] = None
    # Per-series recent history (oldest->newest): {"sofr": [{"date","value"}], ...}.
    history: dict = field(default_factory=dict)


def _liquidity_fixture() -> LiquidityResult:
    return LiquidityResult(
        sofr=5.31, on_rrp=420.0, tga=750.0, reserves=3250.0,
        data_source=_FIXTURE, as_of=None,
        history={
            "sofr": _fx_hist([5.33, 5.32, 5.31, 5.31, 5.30, 5.31]),
            "on_rrp": _fx_hist([520.0, 500.0, 470.0, 450.0, 430.0, 420.0]),
            "tga": _fx_hist([700.0, 720.0, 740.0, 760.0, 745.0, 750.0]),
            "reserves": _fx_hist([3400.0, 3350.0, 3300.0, 3280.0, 3260.0, 3250.0]),
        },
    )


_LIQUIDITY_SERIES = (("sofr", "SOFR"), ("on_rrp", "RRPONTSYD"),
                     ("tga", "WTREGEN"), ("reserves", "WRESBAL"))


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def fetch_liquidity() -> LiquidityResult:
    """Fetch money-market liquidity levels from FRED: SOFR (overnight financing
    rate), ON RRP volume (RRPONTSYD), the Treasury General Account (WTREGEN), and
    aggregate bank reserves (WRESBAL).

    DISPLAY-ONLY; fetched on demand from the Macro Dashboard Liquidity tab; never
    written to the snapshot _meta by design (deliberately NOT part of
    fetch_all_macro() / MacroDataResult, so classify_regime and write_daily_snapshot
    never consume it). Fail-closed: returns a fixture LiquidityResult if FRED is
    unavailable. Reuses _fred_observations' own retry/backoff — no new throttling.
    """
    try:
        latest: dict = {}
        history: dict = {}
        as_of = None
        any_live = False
        for _key, _sid in _LIQUIDITY_SERIES:
            try:
                obs = _fred_observations(_sid, limit=140)
            except Exception:  # noqa: BLE001 — isolate one series' failure
                obs = []
            if obs:
                any_live = True
                _d, _v = obs[0]
                latest[_key] = round(_v, 2)
                if as_of is None or str(_d) > str(as_of):
                    as_of = _d
                history[_key] = _history_from_desc(obs, n=6, stride=21, ndigits=2)
            else:
                latest[_key] = None
                history[_key] = []
        if not any_live:
            return _liquidity_fixture()
        return LiquidityResult(
            sofr=latest["sofr"], on_rrp=latest["on_rrp"],
            tga=latest["tga"], reserves=latest["reserves"],
            data_source=_LIVE, as_of=as_of, history=history,
        )
    except Exception:  # noqa: BLE001 — fail-closed to fixture
        return _liquidity_fixture()
