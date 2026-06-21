"""lib/signal_engine.py — Phase 6B v2 Dual-Track Stock Selection Signal Layer.

This module replaces the Phase 6B v1 single-pass, momentum-biased per-ticker
scoring with a **dual-track candidate architecture** designed to surface
*early-stage* opportunities (MU-style: low RSI, depressed price, fundamental
inflection) alongside alternative-data-triggered candidates — not just the
strongest momentum names.

Architecture (full pipeline orchestrated in ``lib/candidate_generator.py``):

* **Track A (main funnel, 70% of composite)**
    - Layer 1 — hard filter (code only): exclude only on market-cap floor,
      catastrophic 30-day price break, or completely-missing fundamentals. Low
      RSI / low momentum / far-from-52W-high / low ADX are NEVER disqualifiers —
      they are potential early-opportunity signals.
    - Layer 2 — LLM narrative matching (one call per ticker for the top-N): the
      ONLY LLM use in this module. ``llm_orchestrator`` is imported *inside* the
      calling function so Track B and Layers 1/3 carry no LLM dependency. Fails
      closed to a neutral ``NarrativeResult`` on any error / parse failure / no
      key.
    - Layer 3 — fundamental quantitative validation (code only): EPS-revision
      direction (the ``inflecting_up`` cycle-bottom signal), valuation
      percentile vs a hardcoded sector-median map, gross-margin trend, and a
      universe-normalized quality composite.
* **Track B (alternative data, 30% of composite, runs on the FULL universe**
  **independent of the Track A funnel)**: insider-buying, unusual-news keyword,
  and analyst-revision signals. A Track B composite ``>= 0.7`` lets a ticker
  enter the candidate pool *standalone*, labeled ``ALT_SIGNAL``.

Design rules / guardrails (Phase 6B):

* **Free sources only.** yfinance (no key) + Finnhub free tier (reuses the
  existing ``FINNHUB_API_KEY``). Paid alt-data (Quiver Quantitative, Massive
  Options) are in separate modules: lib/quiver_fetcher.py,
  lib/massive_options_fetcher.py. This module uses free sources only.
* **Fail-closed.** Every network fetch is wrapped in its own ``try/except`` and
  returns a deterministic neutral/fixture fallback on *any* error. Functions
  never raise to the caller.
* **No execution.** Review-only observations. No broker / order / execution
  capability and no ``approved_for_execution`` field anywhere; no buy/sell
  instruction is produced.
* **No page / UI imports at module level.** ``signal_engine.py`` never imports
  from ``pages/`` or ``ui_utils`` at module level (``ui_utils.load_ohlcv`` is
  imported lazily inside the technical-snapshot helper). ``llm_orchestrator`` is
  imported lazily inside the single Layer-2 LLM function only.
* **Cached.** Network fetches are memoized with ``st.cache_data(ttl=1800)``; the
  Layer-2 LLM call uses ``ttl=3600`` keyed on ``(ticker, macro_regime)``.

A small set of Phase 6B **v1 backward-compatibility shims** (``FundamentalSignals``
/ ``NarrativeSignals`` / ``EntryQualityScore`` / ``score_ticker`` / the v1 fetch
helpers) is preserved at the bottom of this module so existing v1 consumers keep
working; new code uses the dual-track contracts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv

# Load .env from the project root (one level up from lib/), matching the
# existing lib/data_fetcher.py and lib/macro_data.py conventions.
from pathlib import Path as _Path

load_dotenv(_Path(__file__).parent.parent / ".env")

import yfinance as yf  # free, no API key; module-level so tests can patch it
import requests  # Finnhub free REST endpoints only

# Streamlit's st.cache_data works outside a running server (it simply executes
# the body), so importing it here keeps the module importable + testable offline.
import streamlit as st

# Cross-GICS theme baskets — used only as a READ-ONLY reference for the
# theme-tag reverse-lookup fallback (when the LLM returns no theme_tags). The
# THEME_BASKETS definitions are owned by lib/theme_baskets.py and never modified
# here. theme_baskets imports only yfinance + streamlit (already imported above),
# so this introduces no new heavy dependency and no import cycle.
from lib.theme_baskets import THEME_BASKETS


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Reuses the project's EXISTING Finnhub key (no new credential introduced).
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

# Only free Finnhub endpoints are referenced.
_FINNHUB_RECOMMENDATION = "https://finnhub.io/api/v1/stock/recommendation"
_FINNHUB_EARNINGS = "https://finnhub.io/api/v1/stock/earnings"
_FINNHUB_COMPANY_NEWS = "https://finnhub.io/api/v1/company-news"
_FINNHUB_INSIDER = "https://finnhub.io/api/v1/stock/insider-transactions"

# Cache TTLs — network fetches 30 min; the Layer-2 LLM call 60 min.
_CACHE_TTL = 1800
_LLM_CACHE_TTL = 3600
_HTTP_TIMEOUT = 10

_LIVE = "live"
_FIXTURE = "fixture"

# ----- Layer 1 hard-filter thresholds (documented) -------------------------
# Liquidity floor: below $2B market cap is too illiquid for this surface.
_MIN_MARKET_CAP = 2_000_000_000.0
# Catastrophic break: a >50% drawdown over the last ~30 days usually signals a
# fundamental break (fraud, dilution, bankruptcy risk), not an opportunity.
_MAX_30D_DECLINE_PCT = -50.0
# Tradeability floor: an average daily DOLLAR volume below $10M is too thin to
# build / exit a research position without material slippage. This is the lever
# that meaningfully trims illiquid theme-basket / manually-added small caps
# BEFORE the (cost-bounded) Layer-2 LLM cut — the S&P 500 top-100 anchor names
# all clear it comfortably, so it only bites once smaller names are added. It is
# applied ONLY when both an average-volume and a price field are available from
# yfinance; missing data never excludes on liquidity (still fail-closed by the
# fundamentals gate). Low RSI / low momentum remain NON-disqualifiers.
_MIN_DOLLAR_ADV = 10_000_000.0

# Hardcoded sector median FORWARD P/E map (manual snapshot 2026-05). Used ONLY
# to place a forward P/E on a 0.0–1.0 relative-to-sector scale.
_SECTOR_MEDIAN_FWD_PE = {
    "Technology": 28.0,
    "Communication Services": 19.0,
    "Consumer Cyclical": 22.0,
    "Consumer Defensive": 20.0,
    "Healthcare": 18.0,
    "Financial Services": 13.0,
    "Industrials": 19.0,
    "Energy": 12.0,
    "Basic Materials": 15.0,
    "Real Estate": 30.0,
    "Utilities": 17.0,
}
_DEFAULT_MEDIAN_FWD_PE = 19.0

# Fixed narrative theme taxonomy (Phase 6B contract — passed to the LLM and used
# by the keyword unusual-news / v1-compat attributors).
THEME_TAXONOMY = (
    "AI",
    "semiconductor",
    "cloud",
    "energy",
    "biotech",
    "defense",
    "consumer",
    "financials",
    "industrials",
    "other",
)

# Keyword rules for keyword-based theme attribution (used by Track B unusual-news
# scanning and the v1-compat attributor; the LLM Layer 2 does its OWN judgment).
_THEME_KEYWORDS = {
    "AI": ("ai", "artificial intelligence", "machine learning", "generative",
           "llm", "chatbot", "copilot", "inference", "neural"),
    "semiconductor": ("chip", "chips", "semiconductor", "semiconductors", "wafer",
                      "foundry", "gpu", "node", "fab", "lithography"),
    "cloud": ("cloud", "saas", "data center", "datacenter", "hyperscaler",
              "kubernetes", "serverless", "software-as-a-service"),
    "energy": ("oil", "gas", "energy", "solar", "nuclear", "renewable", "crude",
               "lng", "drilling", "pipeline", "battery", "grid"),
    "biotech": ("biotech", "pharma", "drug", "fda", "clinical", "therapy",
                "vaccine", "oncology", "trial", "biopharma", "gene"),
    "defense": ("defense", "defence", "military", "missile", "aerospace",
                "pentagon", "weapon", "fighter", "radar"),
    "consumer": ("retail", "consumer", "ecommerce", "e-commerce", "apparel",
                 "restaurant", "shopper", "brand", "store"),
    "financials": ("bank", "banks", "lending", "loan", "fintech", "payments",
                   "insurance", "credit", "deposit", "brokerage"),
    "industrials": ("industrial", "manufacturing", "factory", "machinery",
                    "logistics", "freight", "rail", "aviation", "automation"),
}

# Theme -> macro regime alignment hints (used by the v1-compat narrative path;
# the LLM Layer 2 judges alignment itself).
_REGIME_ALIGNED_THEMES = {
    "risk_on": {"AI", "semiconductor", "cloud", "consumer", "industrials"},
    "risk_off": {"energy", "defense", "biotech", "financials"},
}
_REGIME_MISALIGNED_THEMES = {
    "risk_off": {"AI", "semiconductor", "cloud", "consumer"},
    "risk_on": set(),
}

# ----- Track B unusual-news keyword groups (documented per group) ----------
_UNUSUAL_NEWS_KEYWORDS = {
    # Government / defense contract awards.
    "government_contract": (
        "awarded contract", "government contract", "defense contract",
        "federal contract", "dod", "pentagon",
    ),
    # Regulatory approvals (drug / device).
    "regulatory_approval": (
        "fda approved", "fda approval", "cleared by fda", "ema approved",
        "regulatory approval",
    ),
    # Major partnerships / agreements.
    "major_partnership": (
        "strategic partnership", "multi-year agreement", "exclusive agreement",
        "joint venture announced",
    ),
    # Political / policy signals.
    "political_signal": (
        "executive order", "white house", "congress passed", "signed into law",
        "tariff exemption",
    ),
}

# Track B composite weights + standalone-entry threshold.
_TB_W_INSIDER = 0.40
_TB_W_UNUSUAL = 0.35
_TB_W_ANALYST = 0.25
TRACK_B_TRIGGER = 0.7

# ----- Track A scoring maps + weights (all documented) ---------------------
# EPS-revision sub-score — "inflecting_up" is the highest reward (the MU signal:
# the inflection point, not sustained strength).
_EPS_REV_SCORE = {
    "inflecting_up": 1.0,
    "improving": 0.75,
    "stable": 0.4,
    "deteriorating": 0.1,
    "unknown": 0.3,
}
# Margin-trend sub-score.
_MARGIN_SCORE = {
    "expanding": 1.0,
    "stable": 0.5,
    "contracting": 0.1,
    "unknown": 0.3,
}
# Narrative-stage base score — "early"/"growing" preferred; "mature"/"cooling"
# penalized so crowded leaders score lower.
_STAGE_SCORE = {
    "early": 1.0,
    "growing": 0.75,
    "mature": 0.3,
    "cooling": 0.1,
    "unknown": 0.3,
}
# Entry-quality modifier — applied AFTER the raw Track A score (NOT a filter).
# "good" BOOSTS the score (×1.1): an early-stage / oversold name is rewarded,
# not penalized.
_ENTRY_MODIFIER = {"good": 1.1, "fair": 1.0, "extended": 0.85, "avoid": 0.7}

# Track A weights (sum = 1.0).
_WA_EPS = 0.30
_WA_NARRATIVE = 0.25
_WA_VALUATION = 0.20
_WA_MARGIN = 0.15
_WA_QUALITY = 0.10


# ---------------------------------------------------------------------------
# Dual-track result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class NarrativeResult:
    """Layer 2 narrative match (LLM-judged for top-N tickers; else neutral).

    Phase 6B v3 merges catalyst detection into this single LLM narrative call,
    so the catalyst_* fields below are produced by the SAME ``llm_narrative_match``
    call (no extra LLM request). On any LLM parse failure they default to the
    safe neutral values ("" / [] / "none" / False) via :func:`neutral_narrative`.
    """

    theme_tags: list = field(default_factory=list)  # subset of THEME_TAXONOMY
    # "early" | "growing" | "mature" | "cooling" | "unknown"
    narrative_stage: str = "unknown"
    # "aligned" | "neutral" | "misaligned"
    macro_alignment: str = "neutral"
    # "strong" | "moderate" | "weak" | "none"
    narrative_strength: str = "none"
    reasoning: str = ""
    data_source: str = _FIXTURE  # "live" (LLM) | "fixture" (neutral fallback)
    # --- Phase 6B v3 catalyst detection (merged into this LLM call) ----------
    catalyst_summary: str = ""  # one sentence; "" if no catalyst
    catalyst_horizon: list = field(default_factory=list)  # subset of short/mid/long
    # "recent" (<=7d) | "moderate" (8-30d) | "none"
    catalyst_recency: str = "none"
    # True if the catalyst news is >2 weeks old AND the stock already moved >10%.
    already_priced_in: bool = False


@dataclass
class FundamentalResult:
    """Layer 3 fundamental quantitative validation (deterministic, code only)."""

    # "inflecting_up" | "improving" | "stable" | "deteriorating" | "unknown"
    eps_revision_direction: str = "unknown"
    # 0.0–1.0 — forward P/E vs hardcoded sector median (low = undervalued).
    valuation_percentile: float = 0.5
    # "expanding" | "stable" | "contracting" | "unknown"
    margin_trend: str = "unknown"
    # 0.0–1.0 — universe-normalized composite of ROE / gross margin / rev growth.
    quality_composite: float = 0.0
    # Per-field provenance: {"eps","valuation","margin","quality"} -> live/fixture
    data_source: dict = field(default_factory=dict)
    # Raw components (kept so the universe-normalization pass can recompute
    # quality_composite cross-sectionally; never fabricated when missing).
    roe: Optional[float] = None
    gross_margin: Optional[float] = None
    revenue_growth: Optional[float] = None
    forward_pe: Optional[float] = None
    sector: Optional[str] = None


@dataclass
class EntryQualityResult:
    """Deterministic technical entry-quality score (no LLM, no network)."""

    rsi_position: str = "unknown"  # oversold|healthy|extended|overbought|unknown
    distance_from_52w_high: Optional[float] = None  # pct_from_52w_high (<= 0)
    trend_strength: str = "unknown"  # strong|moderate|weak|unknown
    above_sma200: bool = False
    entry_quality_label: str = "fair"  # good|fair|extended|avoid


@dataclass
class TrackAResult:
    """Track A (main funnel) per-ticker result."""

    layer1_passed: bool = False
    layer2_narrative: NarrativeResult = field(default_factory=NarrativeResult)
    layer3_fundamental: FundamentalResult = field(default_factory=FundamentalResult)
    track_a_score: float = 0.0  # 0.0–1.0
    entry_quality: EntryQualityResult = field(default_factory=EntryQualityResult)


@dataclass
class TrackBResult:
    """Track B (alternative data) per-ticker result — full-universe, funnel-free."""

    insider_buy_signal: float = 0.0  # 0.0–1.0
    unusual_news_signal: float = 0.0  # 0.0–1.0
    analyst_revision_signal: float = 0.0  # 0.0–1.0
    track_b_score: float = 0.0  # 0.0–1.0 weighted mean
    is_standalone_trigger: bool = False  # track_b_score >= TRACK_B_TRIGGER


@dataclass
class TickerSignalResult:
    """The full per-ticker dual-track signal bundle surfaced to the Scanner."""

    ticker: str
    track_a: Optional[TrackAResult] = None
    track_b: Optional[TrackBResult] = None
    composite_score: float = 0.0  # 0.0–1.0
    # {"short","mid","long"} -> "strong_fit"|"possible_fit"|"weak_fit"|"no_fit"
    horizon_fit: dict = field(default_factory=dict)
    signal_summary: list = field(default_factory=list)  # up to 5 human strings
    # "FUNNEL" | "ALT_SIGNAL" | "BOTH"
    candidate_type: str = "FUNNEL"
    # --- Phase 6B v1 backward-compat fields (legacy consumers/tests) --------
    fundamental: Optional["FundamentalSignals"] = None
    narrative: Optional["NarrativeSignals"] = None
    entry_quality: Optional[EntryQualityResult] = None


# ---------------------------------------------------------------------------
# Shared low-level fetch helpers (fail-closed)
# ---------------------------------------------------------------------------


def _yf_info(ticker: str) -> dict:
    """Return the yfinance ``info`` dict for a ticker, or ``{}`` on any error."""
    try:
        info = yf.Ticker(ticker).info
        return info if isinstance(info, dict) else {}
    except Exception:  # noqa: BLE001 — fail-closed
        return {}


def _finnhub_get(url: str, params: dict) -> Optional[object]:
    """Shared Finnhub GET (fail-closed). Returns parsed JSON or ``None``."""
    if not FINNHUB_API_KEY:
        return None
    try:
        resp = requests.get(url, params=params, timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:  # noqa: BLE001 — fail-closed
        return None


_FINNHUB_EARNINGS_CAL = "https://finnhub.io/api/v1/calendar/earnings"
# Backoff before the single retry of the bulk earnings-calendar call (rate-limit
# defense). Module-level so tests can monkeypatch it to 0 (no real sleep).
_FINNHUB_BULK_RETRY_BACKOFF_S = 2.0


def fetch_earnings_reactions_calendar(date_from: str, date_to: str) -> list:
    """ONE bulk Finnhub earnings-calendar call (Phase 7B Item 2 — the single,
    skippable earnings call per refresh).

    Returns ``[{ticker, report_date, direction}]`` where ``direction`` is "beat"
    when epsActual > epsEstimate else "miss". **Raises** ``RuntimeError`` when the
    source is unavailable (no key / HTTP error) so the caller can tell
    "finnhub_unavailable" from a legitimately empty window ("no_reports_in_window").
    Reports missing actual/estimate are skipped (no direction can be derived)."""
    if not FINNHUB_API_KEY:
        raise RuntimeError("finnhub_no_key")
    # Single bulk call. Finnhub's free tier is 60 req/min; a refresh that already
    # fetched the candidate universe (hundreds of per-ticker calls) can trip a 429
    # here, which _finnhub_get swallows to None. Retry ONCE with a short backoff
    # before declaring the source unavailable, so a transient rate-limit degrades
    # to a real reading on the second attempt rather than going dark. Still fully
    # degradable: if both attempts fail it raises and the caller records
    # "finnhub_unavailable" (never blocks the refresh).
    _params = {"from": date_from, "to": date_to, "token": FINNHUB_API_KEY}
    data = _finnhub_get(_FINNHUB_EARNINGS_CAL, _params)
    if data is None:
        import time as _time
        _time.sleep(_FINNHUB_BULK_RETRY_BACKOFF_S)
        data = _finnhub_get(_FINNHUB_EARNINGS_CAL, _params)
    if data is None:
        raise RuntimeError("finnhub_error")
    rows = data.get("earningsCalendar", []) if isinstance(data, dict) else []
    out: list = []
    for r in rows or []:
        sym = r.get("symbol")
        rdate = r.get("date")
        act, est = r.get("epsActual"), r.get("epsEstimate")
        if not sym or not rdate or act is None or est is None:
            continue
        try:
            direction = "beat" if float(act) > float(est) else "miss"
        except (TypeError, ValueError):
            continue
        out.append({"ticker": str(sym).upper().strip(),
                    "report_date": str(rdate), "direction": direction})
    return out


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _technical_snapshot(ticker: str, period: str = "1y") -> dict:
    """Fetch OHLCV + compute the technical snapshot (the run_scan engine).

    Reuses ``ui_utils.load_ohlcv`` (lazy import — keeps signal_engine free of a
    module-level page/ui dependency) and ``lib.technical.snapshot``. Fail-closed:
    returns ``{}`` on any error.
    """
    try:
        from ui_utils import load_ohlcv  # local import; heavy + streamlit-bound
        from lib.technical import snapshot

        df = load_ohlcv(ticker, period)
        if df is None or len(df) < 60:
            return {}
        snap = snapshot(df)
        # Phase 6B v3 — add a trailing ~1-month (≈21 trading-day) return so the
        # short-horizon momentum_continuation sub-score has its input. Fail-soft:
        # left absent if the window is too short.
        try:
            if len(df) >= 22:
                last = float(df["Close"].iloc[-1])
                prior = float(df["Close"].iloc[-22])
                if prior > 0:
                    snap["ret_1m"] = round((last / prior - 1.0) * 100.0, 2)
        except Exception:  # noqa: BLE001 — leave ret_1m absent
            pass
        return snap
    except Exception:  # noqa: BLE001 — fail-closed
        return {}


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _return_30d(ticker: str) -> Optional[float]:
    """Trailing ~30-day (≈21 trading-day) price return in pct, or ``None``.

    Fail-closed: returns ``None`` on any error so the Layer 1 price-break check
    is simply skipped rather than crashing.
    """
    try:
        from ui_utils import load_ohlcv  # local import (no module-level ui dep)

        df = load_ohlcv(ticker, "3mo")
        if df is None or len(df) < 22:
            return None
        last = float(df["Close"].iloc[-1])
        prior = float(df["Close"].iloc[-22])
        if prior <= 0:
            return None
        return round((last / prior - 1.0) * 100.0, 2)
    except Exception:  # noqa: BLE001 — fail-closed
        return None


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def fetch_company_news(ticker: str, days: int = 30) -> list:
    """Finnhub /company-news over the last ``days`` (fail-closed → ``[]``).

    Returns a list of ``{"headline","summary","datetime"}``-shaped dicts.
    """
    try:
        to_dt = datetime.now(timezone.utc).date()
        from_dt = to_dt - timedelta(days=days)
        raw = _finnhub_get(
            _FINNHUB_COMPANY_NEWS,
            {"symbol": ticker, "from": str(from_dt), "to": str(to_dt),
             "token": FINNHUB_API_KEY},
        )
        if not isinstance(raw, list):
            return []
        return [
            {"headline": i.get("headline", ""), "summary": i.get("summary", ""),
             "datetime": i.get("datetime")}
            for i in raw if i.get("headline")
        ]
    except Exception:  # noqa: BLE001 — fail-closed
        return []


# ---------------------------------------------------------------------------
# Layer 1 — hard filter (code only; NEVER penalizes low RSI / momentum)
# ---------------------------------------------------------------------------


def passes_layer1(
    ticker: str,
    info: Optional[dict] = None,
    ret_30d: Optional[float] = None,
) -> tuple:
    """Return ``(passed: bool, reason: str)`` for the Track A Layer 1 hard filter.

    Excludes ONLY on:

    * fundamental data completely unavailable from yfinance, or
    * market cap < ``$2B`` (too small), or
    * average daily DOLLAR volume < ``$10M`` (too illiquid to trade) — applied
      only when both an average-volume and a price field are present, or
    * a 30-day price decline worse than ``-50%`` (likely fundamental break).

    It does **NOT** exclude on low RSI, low momentum, far-from-52W-high, or low
    ADX — those are potential early-opportunity signals, not disqualifiers.

    ``info`` / ``ret_30d`` may be injected (tests / pipeline reuse); otherwise
    they are fetched fail-closed.
    """
    try:
        if info is None:
            info = _yf_info(ticker)
        # Completely-unavailable fundamentals -> exclude (cannot evaluate).
        has_fund = bool(info) and any(
            isinstance(info.get(k), (int, float))
            for k in ("marketCap", "forwardPE", "trailingPE", "grossMargins",
                      "returnOnEquity", "revenueGrowth")
        )
        if not has_fund:
            return (False, "no_fundamentals")
        mc = info.get("marketCap")
        if isinstance(mc, (int, float)) and mc < _MIN_MARKET_CAP:
            return (False, "market_cap")
        # Liquidity: average daily DOLLAR volume below $10M is too thin. Computed
        # from yfinance info only (no extra fetch); skipped when data is absent.
        avg_vol = info.get("averageVolume")
        if not isinstance(avg_vol, (int, float)) or avg_vol <= 0:
            avg_vol = info.get("averageDailyVolume10Day")
        price = (info.get("currentPrice") or info.get("regularMarketPrice")
                 or info.get("previousClose"))
        if (isinstance(avg_vol, (int, float)) and avg_vol > 0
                and isinstance(price, (int, float)) and price > 0):
            if avg_vol * price < _MIN_DOLLAR_ADV:
                return (False, "liquidity")
        if ret_30d is None:
            ret_30d = _return_30d(ticker)
        if isinstance(ret_30d, (int, float)) and ret_30d < _MAX_30D_DECLINE_PCT:
            return (False, "price_break")
        return (True, "ok")
    except Exception:  # noqa: BLE001 — fail-closed (exclude on uncertainty)
        return (False, "error")


# ---------------------------------------------------------------------------
# Layer 3 — fundamental quantitative validation (deterministic, code only)
# ---------------------------------------------------------------------------


def _eps_revision_direction(rows: list) -> str:
    """EPS actual-vs-estimate revision direction over the last (≤4) quarters.

    ``rows`` is Finnhub ``/stock/earnings`` output (most-recent-first). We build
    a beat/miss flag per quarter (``actual > estimate``), newest-first, then:

    * **"inflecting_up"** — the most recent quarter BEAT, immediately after a
      MISS (``beats[0] and not beats[1]``). This is the MU signal: the inflection
      point, not sustained strength.
    * **"improving"** — 2+ consecutive beats (``beats[0] and beats[1]``) — i.e.
      sustained strength, explicitly NOT the inflection case.
    * **"deteriorating"** — 2+ consecutive misses.
    * **"stable"** — any other mixed pattern with >= 2 usable quarters.
    * **"unknown"** — fewer than 2 usable quarters.
    """
    beats: list[bool] = []
    for row in (rows or [])[:4]:
        actual = row.get("actual")
        est = row.get("estimate")
        if isinstance(actual, (int, float)) and isinstance(est, (int, float)):
            beats.append(float(actual) > float(est))
    if len(beats) < 2:
        return "unknown"
    if beats[0] and not beats[1]:
        return "inflecting_up"
    if beats[0] and beats[1]:
        return "improving"
    if not beats[0] and not beats[1]:
        return "deteriorating"
    return "stable"


def _valuation_percentile(info: dict) -> float:
    """Forward-P/E percentile relative to the hardcoded sector median (0.0–1.0).

    ``percentile = clamp(0.5 * forwardPE / sector_median, 0, 1)`` — at the median
    -> 0.5, half the median -> ~0.25 (cheap / undervalued opportunity), twice the
    median -> 1.0 (rich / stretched). Lower = cheaper. Missing forward P/E -> 0.5.
    """
    fpe = info.get("forwardPE")
    if not isinstance(fpe, (int, float)) or fpe <= 0:
        return 0.5
    median = _SECTOR_MEDIAN_FWD_PE.get(info.get("sector"), _DEFAULT_MEDIAN_FWD_PE)
    return round(max(0.0, min(1.0, 0.5 * float(fpe) / median)), 4)


def _quality_anchor(info: dict) -> float:
    """Fixed-anchor 0.0–1.0 quality composite (used when universe-normalization
    is unavailable, e.g. the single-ticker ``score_ticker`` path).

    Equal-weight average of independently min-max-normalized ROE / 0.30, gross
    margin / 0.60, revenue growth / 0.25 (each clamped to [0, 1]). Missing
    components are dropped; none present -> 0.0.
    """
    parts: list[float] = []
    roe = info.get("returnOnEquity")
    if isinstance(roe, (int, float)):
        parts.append(max(0.0, min(1.0, float(roe) / 0.30)))
    gm = info.get("grossMargins")
    if isinstance(gm, (int, float)):
        parts.append(max(0.0, min(1.0, float(gm) / 0.60)))
    rev = info.get("revenueGrowth")
    if isinstance(rev, (int, float)):
        parts.append(max(0.0, min(1.0, float(rev) / 0.25)))
    if not parts:
        return 0.0
    return round(sum(parts) / len(parts), 4)


def _yf_margin_trend(ticker: str) -> str:
    """Gross-margin direction over the last 2 available quarters (yfinance).

    Compares gross margin (gross profit / total revenue) of the two most recent
    quarterly income-statement columns: newer - older > +1pp -> "expanding",
    < -1pp -> "contracting", otherwise "stable". Fail-closed -> "unknown".
    """
    try:
        t = yf.Ticker(ticker)
        qf = getattr(t, "quarterly_income_stmt", None)
        if qf is None or getattr(qf, "empty", True):
            qf = getattr(t, "quarterly_financials", None)
        if qf is None or getattr(qf, "empty", True):
            return "unknown"

        def _row(names):
            for n in names:
                if n in qf.index:
                    return qf.loc[n]
            return None

        gp = _row(["Gross Profit", "GrossProfit"])
        rev = _row(["Total Revenue", "TotalRevenue", "Operating Revenue"])
        if gp is None or rev is None:
            return "unknown"
        cols = list(qf.columns)[:2]
        if len(cols) < 2:
            return "unknown"
        margins: list[float] = []
        for c in cols:
            try:
                r = float(rev[c])
                g = float(gp[c])
                if r:
                    margins.append(g / r)
            except (TypeError, ValueError, KeyError):
                continue
        if len(margins) < 2:
            return "unknown"
        delta = margins[0] - margins[1]  # newest - older
        if delta > 0.01:
            return "expanding"
        if delta < -0.01:
            return "contracting"
        return "stable"
    except Exception:  # noqa: BLE001 — fail-closed
        return "unknown"


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def fetch_fundamental(ticker: str) -> FundamentalResult:
    """Compute the Layer 3 :class:`FundamentalResult` for ``ticker`` (fail-closed).

    ``quality_composite`` is seeded with the fixed-anchor proxy; the candidate
    pipeline's universe-normalization pass recomputes it cross-sectionally from
    the stored raw components.
    """
    try:
        info = _yf_info(ticker)
        fund_src = _LIVE if info else _FIXTURE

        eps_rows = _finnhub_get(
            _FINNHUB_EARNINGS, {"symbol": ticker, "token": FINNHUB_API_KEY}
        )
        if isinstance(eps_rows, list) and eps_rows:
            eps_dir = _eps_revision_direction(eps_rows)
            eps_src = _LIVE
        else:
            eps_dir = "unknown"
            eps_src = _FIXTURE

        val_pct = _valuation_percentile(info)
        margin = _yf_margin_trend(ticker) if info else "unknown"
        quality = _quality_anchor(info)

        return FundamentalResult(
            eps_revision_direction=eps_dir,
            valuation_percentile=val_pct,
            margin_trend=margin,
            quality_composite=quality,
            data_source={
                "eps": eps_src,
                "valuation": fund_src,
                "margin": fund_src if margin != "unknown" else _FIXTURE,
                "quality": fund_src,
            },
            roe=info.get("returnOnEquity") if info else None,
            gross_margin=info.get("grossMargins") if info else None,
            revenue_growth=info.get("revenueGrowth") if info else None,
            forward_pe=info.get("forwardPE") if info else None,
            sector=info.get("sector") if info else None,
        )
    except Exception:  # noqa: BLE001 — fully fail-closed
        return FundamentalResult(
            data_source={"eps": _FIXTURE, "valuation": _FIXTURE,
                         "margin": _FIXTURE, "quality": _FIXTURE}
        )


def quality_pre_score(ticker: str, info: Optional[dict] = None) -> float:
    """Lightweight quality proxy (fixed-anchor) used ONLY to rank Layer 1
    survivors for Layer 2 LLM selection (top-N by this proxy). Cheap: one
    yfinance ``info`` read. Fail-closed -> 0.0.
    """
    try:
        if info is None:
            info = _yf_info(ticker)
        return _quality_anchor(info)
    except Exception:  # noqa: BLE001
        return 0.0


def normalize_quality_composite(fundamentals: dict) -> None:
    """Universe-normalize ``quality_composite`` in-place across ``fundamentals``.

    ``fundamentals`` maps ticker -> :class:`FundamentalResult`. Each of ROE /
    gross margin / revenue growth is min-max normalized across the universe; a
    ticker's ``quality_composite`` becomes the equal-weight mean of its present
    normalized components (this measures business quality, NOT momentum). When a
    component has no spread (or is absent universe-wide) it is dropped; a ticker
    with no usable component keeps its fixed-anchor seed value.
    """
    if not fundamentals:
        return
    results = list(fundamentals.values())

    def _bounds(attr):
        vals = [getattr(r, attr) for r in results
                if isinstance(getattr(r, attr), (int, float))]
        if len(vals) < 2:
            return None
        lo, hi = min(vals), max(vals)
        if hi <= lo:
            return None
        return lo, hi

    bounds = {a: _bounds(a) for a in ("roe", "gross_margin", "revenue_growth")}
    for r in results:
        parts: list[float] = []
        for attr in ("roe", "gross_margin", "revenue_growth"):
            b = bounds[attr]
            v = getattr(r, attr)
            if b is not None and isinstance(v, (int, float)):
                lo, hi = b
                parts.append(max(0.0, min(1.0, (float(v) - lo) / (hi - lo))))
        if parts:
            r.quality_composite = round(sum(parts) / len(parts), 4)


# ---------------------------------------------------------------------------
# Layer 2 — LLM narrative matching (the ONLY LLM use; import is in-function)
# ---------------------------------------------------------------------------

_VALID_STAGES = {"early", "growing", "mature", "cooling"}
_VALID_ALIGN = {"aligned", "neutral", "misaligned"}
_VALID_STRENGTH = {"strong", "moderate", "weak", "none"}
_VALID_CATALYST_HORIZON = {"short", "mid", "long"}
_VALID_CATALYST_RECENCY = {"recent", "moderate", "none"}


def neutral_narrative() -> NarrativeResult:
    """Neutral fallback narrative (no LLM judgment) for non-top-N tickers and for
    any LLM failure / parse error / missing key.

    All Phase 6B v3 catalyst fields default to their SAFE values here
    (empty string / empty list / "none" / False) so a parse failure never
    fabricates a catalyst.
    """
    return NarrativeResult(
        theme_tags=[],
        narrative_stage="unknown",
        macro_alignment="neutral",
        narrative_strength="none",
        reasoning="",
        data_source=_FIXTURE,
        catalyst_summary="",
        catalyst_horizon=[],
        catalyst_recency="none",
        already_priced_in=False,
    )


def _has_llm_api_key() -> bool:
    """True if an LLM API key is configured (env or Streamlit secrets).

    Checked WITHOUT importing any LLM SDK so Layers 1/3 and Track B carry no LLM
    dependency, and so a keyless environment never attempts an LLM call.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    try:
        return bool(st.secrets.get("ANTHROPIC_API_KEY"))
    except Exception:  # noqa: BLE001
        return False


@st.cache_data(ttl=_LLM_CACHE_TTL, show_spinner=False)
def llm_narrative_match(ticker: str, macro_regime: str) -> NarrativeResult:
    """Layer 2 — one LLM call judging the narrative for ``ticker``.

    Inputs: the last 30 days of Finnhub company-news headlines + summaries, the
    current macro regime, and the fixed theme taxonomy. The LLM is instructed to
    base ``narrative_stage`` on news **recency, volume, and sentiment shift** —
    not mere keyword presence. "early"/"growing" are the preferred (uncrowded)
    stages.

    Implementation note: ``llm_orchestrator`` is imported **inside this function**
    (never at module level) so Track B and Layers 1/3 stay free of any LLM
    dependency. Cached TTL=3600 keyed on ``(ticker, macro_regime)``. Fail-closed:
    on no key / no news / API error / parse failure -> :func:`neutral_narrative`.
    """
    try:
        news = fetch_company_news(ticker, days=30)
        if not news:
            return neutral_narrative()
        if not _has_llm_api_key():
            return neutral_narrative()

        # In-function import — keeps the LLM dependency out of module scope.
        from lib import llm_orchestrator

        headlines = []
        for item in news[:25]:
            head = (item.get("headline") or "").strip()
            summ = (item.get("summary") or "").strip()
            line = head if not summ else f"{head} — {summ[:160]}"
            if line:
                headlines.append(f"- {line}")
        news_block = "\n".join(headlines) if headlines else "(no headlines)"
        taxonomy = ", ".join(THEME_TAXONOMY)

        system = (
            "You are an equity narrative + catalyst analyst. From recent company "
            "news, judge a stock's NARRATIVE STAGE and detect any near-term "
            "CATALYST. Base the narrative judgment on news RECENCY, VOLUME, and "
            "SENTIMENT SHIFT over time — NOT on mere keyword presence. "
            "'early' = a nascent / just-emerging story (few but accelerating, "
            "positive-shifting headlines); 'growing' = building momentum; "
            "'mature' = a well-established, widely-covered (crowded) story; "
            "'cooling' = fading attention / negative sentiment shift. "
            "A CATALYST is a specific, datable event (earnings beat, contract "
            "award, regulatory approval, product launch, guidance raise, etc.). "
            "Set catalyst_recency from the catalyst news date: 'recent' if within "
            "the last 7 days, 'moderate' if 8-30 days, 'none' if there is no clear "
            "catalyst. Set already_priced_in to true ONLY if the catalyst news is "
            "more than two weeks old AND the stock has already moved more than 10% "
            "since that news; otherwise false. If there is no catalyst, set "
            'catalyst_summary to "", catalyst_horizon to [], catalyst_recency to '
            '"none", already_priced_in to false. '
            "For theme_tags you MUST choose ONE OR MORE labels strictly from the "
            "provided fixed taxonomy list — do not invent new labels and do not "
            "leave it empty. Pick the single closest taxonomy label when the fit "
            "is only approximate; only use \"other\" when no listed theme applies "
            "at all. "
            "Output PURE JSON (no markdown) with exactly these fields: "
            '{"theme_tags": [subset of the provided taxonomy], '
            '"narrative_stage": "early"|"growing"|"mature"|"cooling", '
            '"macro_alignment": "aligned"|"neutral"|"misaligned", '
            '"narrative_strength": "strong"|"moderate"|"weak"|"none", '
            '"reasoning": "one sentence", '
            '"catalyst_summary": "one sentence or empty string", '
            '"catalyst_horizon": [subset of "short"|"mid"|"long"], '
            '"catalyst_recency": "recent"|"moderate"|"none", '
            '"already_priced_in": true|false}'
        )
        user = (
            f"Ticker: {ticker}\n"
            f"Current macro regime: {macro_regime}\n"
            f"Theme taxonomy (choose theme_tags only from this list): [{taxonomy}]\n\n"
            f"Last 30 days of company news (most recent first):\n{news_block}\n\n"
            "Return the JSON object only."
        )

        client = llm_orchestrator._get_client()
        parsed = llm_orchestrator._llm_json_call(client, 500, system, user)
        if not isinstance(parsed, dict):
            return neutral_narrative()

        raw_tags = parsed.get("theme_tags")
        tags = [t for t in raw_tags if t in THEME_TAXONOMY] if isinstance(raw_tags, list) else []
        stage = parsed.get("narrative_stage")
        stage = stage if stage in _VALID_STAGES else "unknown"
        align = parsed.get("macro_alignment")
        align = align if align in _VALID_ALIGN else "neutral"
        strength = parsed.get("narrative_strength")
        strength = strength if strength in _VALID_STRENGTH else "none"
        reasoning = parsed.get("reasoning")
        reasoning = str(reasoning)[:300] if isinstance(reasoning, str) else ""

        # --- Phase 6B v3 catalyst fields (safe-defaulted) -------------------
        cat_summary = parsed.get("catalyst_summary")
        cat_summary = str(cat_summary)[:300] if isinstance(cat_summary, str) else ""
        raw_chorizon = parsed.get("catalyst_horizon")
        cat_horizon = (
            [h for h in raw_chorizon if h in _VALID_CATALYST_HORIZON]
            if isinstance(raw_chorizon, list) else []
        )
        cat_recency = parsed.get("catalyst_recency")
        cat_recency = cat_recency if cat_recency in _VALID_CATALYST_RECENCY else "none"
        already_priced = bool(parsed.get("already_priced_in", False))
        # No catalyst summary -> never claim a catalyst horizon/recency.
        if not cat_summary:
            cat_horizon = []
            cat_recency = "none"
            already_priced = False

        return NarrativeResult(
            theme_tags=tags,
            narrative_stage=stage,
            macro_alignment=align,
            narrative_strength=strength,
            reasoning=reasoning,
            data_source=_LIVE,
            catalyst_summary=cat_summary,
            catalyst_horizon=cat_horizon,
            catalyst_recency=cat_recency,
            already_priced_in=already_priced,
        )
    except Exception:  # noqa: BLE001 — fail-closed to a neutral narrative
        return neutral_narrative()


# ---------------------------------------------------------------------------
# Entry quality (deterministic code only — no LLM, no network)
# ---------------------------------------------------------------------------


def _rsi_position(rsi: Optional[float]) -> str:
    """RSI bucket: <40 oversold, 40–65 healthy, 65–75 extended, >75 overbought."""
    if rsi is None:
        return "unknown"
    if rsi < 40:
        return "oversold"
    if rsi <= 65:
        return "healthy"
    if rsi <= 75:
        return "extended"
    return "overbought"


def _trend_strength(adx: Optional[float]) -> str:
    """Trend strength from ADX: >25 strong, 15–25 moderate, <15 weak."""
    if adx is None:
        return "unknown"
    if adx > 25:
        return "strong"
    if adx >= 15:
        return "moderate"
    return "weak"


def compute_entry_quality(ticker: str, technical_snapshot: dict) -> EntryQualityResult:
    """Deterministic technical entry-quality score from a technical snapshot.

    ``technical_snapshot`` is the dict returned by ``lib.technical.snapshot()``.
    No LLM, no network.

    ``entry_quality_label`` rules (evaluated top-down; first match wins):

    1. **avoid**    — overbought RSI (>75): stretched, poor entry.
    2. **good**     — oversold RSI (<40) AND far below the 52-week high
                      (distance <= -20%): the cycle-bottom / early-opportunity
                      case (e.g. MU at a cycle low). This is an entry-quality
                      BOOST, NOT a penalty — even when below SMA200.
    3. **avoid**    — below the 200-day SMA AND a weak trend (no support, no
                      momentum, and not the oversold-opportunity case above).
    4. **extended** — extended RSI band (65–75) while above SMA200: stretched to
                      the upside.
    5. **good**     — above SMA200 AND healthy RSI (40–65) AND >= moderate trend
                      AND within 25% of the 52-week high: the classic
                      constructive trending entry.
    6. **fair**     — everything else (neutral default).

    Low RSI / low momentum / far-from-52W-high are NEVER penalized here; they can
    qualify a name as "good" (rule 2) so early-stage tickers are rewarded.
    """
    snap = technical_snapshot or {}
    rsi = snap.get("RSI_14")
    adx = snap.get("ADX")
    pct_from_high = snap.get("pct_from_52w_high")
    above_sma200 = bool(snap.get("above_SMA200", False))

    rsi_pos = _rsi_position(rsi)
    trend = _trend_strength(adx)
    far_from_high = isinstance(pct_from_high, (int, float)) and pct_from_high <= -20.0

    if rsi_pos == "overbought":
        label = "avoid"
    elif rsi_pos == "oversold" and far_from_high:
        label = "good"  # cycle-bottom opportunity (the MU signal) — a BOOST
    elif not above_sma200 and trend == "weak":
        label = "avoid"
    elif rsi_pos == "extended" and above_sma200:
        label = "extended"
    elif (
        above_sma200
        and rsi_pos == "healthy"
        and trend in ("strong", "moderate")
        and (pct_from_high is None or pct_from_high >= -25.0)
    ):
        label = "good"
    else:
        label = "fair"

    return EntryQualityResult(
        rsi_position=rsi_pos,
        distance_from_52w_high=pct_from_high,
        trend_strength=trend,
        above_sma200=above_sma200,
        entry_quality_label=label,
    )


# ---------------------------------------------------------------------------
# Track B — alternative data signals (full universe, funnel-independent)
# ---------------------------------------------------------------------------


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def fetch_insider_signal(ticker: str) -> float:
    """Insider-buying signal 0.0–1.0 from Finnhub /stock/insider-transactions.

    Flags net insider BUYING over the last 60 days: more buy than sell
    transactions by count AND total buy value > $500K. Score blends the net-buy
    ratio with a value score (saturating at $5M). Fail-closed -> 0.0.
    """
    try:
        to_dt = datetime.now(timezone.utc).date()
        from_dt = to_dt - timedelta(days=60)
        data = _finnhub_get(
            _FINNHUB_INSIDER,
            {"symbol": ticker, "from": str(from_dt), "to": str(to_dt),
             "token": FINNHUB_API_KEY},
        )
        rows = data.get("data") if isinstance(data, dict) else None
        if not rows:
            return 0.0
        buys = sells = 0
        buy_value = 0.0
        for r in rows:
            change = r.get("change", 0) or 0
            price = r.get("transactionPrice", 0) or 0
            try:
                change = float(change)
                price = float(price)
            except (TypeError, ValueError):
                continue
            if change > 0:
                buys += 1
                buy_value += change * price
            elif change < 0:
                sells += 1
        if buys <= sells or buy_value < 500_000:
            return 0.0
        net_ratio = (buys - sells) / float(max(1, buys + sells))
        value_score = min(1.0, buy_value / 5_000_000.0)
        return round(max(0.0, min(1.0, 0.5 * net_ratio + 0.5 * value_score)), 4)
    except Exception:  # noqa: BLE001 — fail-closed
        return 0.0


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def fetch_unusual_news_signal(ticker: str) -> float:
    """Unusual-news keyword signal 0.0–1.0 from Finnhub /company-news (60d).

    Scans headlines + summaries for the documented ``_UNUSUAL_NEWS_KEYWORDS``
    groups (government/defense contracts, regulatory approvals, major
    partnerships, political/policy signals). Score is driven by the most-recent
    match's recency (<=7 days -> 1.0, <=30 days -> 0.6, <=60 days -> 0.3) with a
    small bump for multiple matches. Fail-closed -> 0.0.
    """
    try:
        news = fetch_company_news(ticker, days=60)
        if not news:
            return 0.0
        now_ts = datetime.now(timezone.utc).timestamp()
        best_recency = 0.0
        matches = 0
        for item in news:
            text = f"{item.get('headline', '')} {item.get('summary', '')}".lower()
            hit = any(
                kw in text
                for group in _UNUSUAL_NEWS_KEYWORDS.values()
                for kw in group
            )
            if not hit:
                continue
            matches += 1
            ts = item.get("datetime")
            recency = 0.3
            if isinstance(ts, (int, float)) and ts > 0:
                age_days = (now_ts - float(ts)) / 86400.0
                if age_days <= 7:
                    recency = 1.0
                elif age_days <= 30:
                    recency = 0.6
                else:
                    recency = 0.3
            best_recency = max(best_recency, recency)
        if matches == 0:
            return 0.0
        return round(min(1.0, best_recency + 0.1 * (matches - 1)), 4)
    except Exception:  # noqa: BLE001 — fail-closed
        return 0.0


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def fetch_analyst_revision_signal(ticker: str) -> float:
    """Analyst-revision signal 0.0–1.0 from Finnhub /stock/recommendation.

    Flags a strong-buy count increase of 2+ between the latest and prior monthly
    snapshots. Score scales with the increase (saturating at 1.0). (Price-target
    raises are NOT used here — Finnhub's price-target endpoint is premium; left
    for a later paid phase.) Fail-closed -> 0.0.
    """
    try:
        rows = _finnhub_get(
            _FINNHUB_RECOMMENDATION, {"symbol": ticker, "token": FINNHUB_API_KEY}
        )
        if not isinstance(rows, list) or len(rows) < 2:
            return 0.0
        latest = float(rows[0].get("strongBuy", 0) or 0)
        prev = float(rows[1].get("strongBuy", 0) or 0)
        increase = latest - prev
        if increase >= 2:
            return round(min(1.0, 0.5 + 0.1 * increase), 4)
        return 0.0
    except Exception:  # noqa: BLE001 — fail-closed
        return 0.0


def _track_b_composite(insider: float, unusual: float, analyst: float) -> float:
    """Track B weighted-mean composite (insider 40% / unusual-news 35% /
    analyst-revision 25%), clamped to [0, 1]."""
    score = _TB_W_INSIDER * insider + _TB_W_UNUSUAL * unusual + _TB_W_ANALYST * analyst
    return round(max(0.0, min(1.0, score)), 4)


def compute_track_b(
    ticker: str,
    insider: Optional[float] = None,
    unusual: Optional[float] = None,
    analyst: Optional[float] = None,
) -> TrackBResult:
    """Assemble the :class:`TrackBResult` for ``ticker`` (fail-closed).

    Sub-signals may be injected (tests); otherwise each is fetched. The standalone
    trigger fires when the composite ``>= TRACK_B_TRIGGER`` (0.7).
    """
    insider = fetch_insider_signal(ticker) if insider is None else insider
    unusual = fetch_unusual_news_signal(ticker) if unusual is None else unusual
    analyst = fetch_analyst_revision_signal(ticker) if analyst is None else analyst
    score = _track_b_composite(insider, unusual, analyst)
    return TrackBResult(
        insider_buy_signal=round(float(insider), 4),
        unusual_news_signal=round(float(unusual), 4),
        analyst_revision_signal=round(float(analyst), 4),
        track_b_score=score,
        is_standalone_trigger=score >= TRACK_B_TRIGGER,
    )


# ---------------------------------------------------------------------------
# Composite scoring + horizon fit + signal summary
# ---------------------------------------------------------------------------


def _bias_for_regime(macro_regime: str) -> dict:
    """Deterministic horizon-bias for a regime string (mirrors the mapping in
    ``lib/macro_regime.py``; kept local to avoid a hard import dependency)."""
    r = (macro_regime or "unknown").strip().lower()
    if r == "risk_on":
        return {"short": "favorable", "mid": "favorable", "long": "neutral"}
    if r == "risk_off":
        return {"short": "unfavorable", "mid": "unfavorable", "long": "neutral"}
    if r == "transition":
        return {"short": "cautious", "mid": "cautious", "long": "cautious"}
    return {"short": "neutral", "mid": "neutral", "long": "neutral"}


def _narrative_score(narrative: NarrativeResult) -> float:
    """Narrative sub-score 0.0–1.0.

    stage: early 1.0 / growing 0.75 / mature 0.3 / cooling 0.1 (unknown 0.3);
    alignment: aligned +0.15 / misaligned -0.15;
    strength: strong +0.1 / none -0.1. Final clamped to [0, 1].
    """
    base = _STAGE_SCORE.get(narrative.narrative_stage, 0.3)
    if narrative.macro_alignment == "aligned":
        base += 0.15
    elif narrative.macro_alignment == "misaligned":
        base -= 0.15
    if narrative.narrative_strength == "strong":
        base += 0.1
    elif narrative.narrative_strength == "none":
        base -= 0.1
    return round(max(0.0, min(1.0, base)), 4)


def compute_track_a_score(
    fundamental: FundamentalResult,
    narrative: NarrativeResult,
    entry: EntryQualityResult,
) -> float:
    """Track A score 0.0–1.0 (documented weights), then the entry-quality modifier.

    Sub-scores: eps_revision_score, narrative_score, valuation_score
    (= 1 - valuation_percentile), margin_score, quality_score (= quality_composite).
    Weights: eps 0.30 / narrative 0.25 / valuation 0.20 / margin 0.15 / quality
    0.10. The entry-quality modifier (good ×1.1 / fair ×1.0 / extended ×0.85 /
    avoid ×0.7) is applied AFTER (a BOOST for "good", not a filter). Clamp [0, 1].
    """
    eps = _EPS_REV_SCORE.get(fundamental.eps_revision_direction, 0.3)
    valuation = max(0.0, min(1.0, 1.0 - float(fundamental.valuation_percentile)))
    margin = _MARGIN_SCORE.get(fundamental.margin_trend, 0.3)
    quality = max(0.0, min(1.0, float(fundamental.quality_composite)))
    narr = _narrative_score(narrative)
    raw = (
        _WA_EPS * eps
        + _WA_NARRATIVE * narr
        + _WA_VALUATION * valuation
        + _WA_MARGIN * margin
        + _WA_QUALITY * quality
    )
    modifier = _ENTRY_MODIFIER.get(entry.entry_quality_label, 1.0)
    return round(max(0.0, min(1.0, raw * modifier)), 4)


def compute_composite(track_a_score: float, track_b_score: float, candidate_type: str) -> float:
    """Composite 0.0–1.0. FUNNEL/BOTH: 0.7×Track A + 0.3×Track B. ALT_SIGNAL
    (standalone Track B entry only): the Track B score itself."""
    if candidate_type == "ALT_SIGNAL":
        return round(max(0.0, min(1.0, float(track_b_score))), 4)
    return round(max(0.0, min(1.0, 0.7 * float(track_a_score) + 0.3 * float(track_b_score))), 4)


def compute_horizon_fit(
    fundamental: FundamentalResult,
    narrative: NarrativeResult,
    entry: EntryQualityResult,
    horizon_bias: dict,
) -> dict:
    """Deterministic per-horizon fit (review-only). Values: strong_fit /
    possible_fit / weak_fit / no_fit. Rules documented inline (Phase 6B v2)."""
    bias = horizon_bias or {}
    stage = narrative.narrative_stage
    eps = fundamental.eps_revision_direction
    label = entry.entry_quality_label
    val = float(fundamental.valuation_percentile)
    qual = float(fundamental.quality_composite)
    margin = fundamental.margin_trend

    # SHORT — timing-led (entry quality + narrative + macro short bias).
    if label == "good" and stage in ("early", "growing") and bias.get("short") in ("favorable", "neutral"):
        short = "strong_fit"
    elif label in ("good", "fair") and bias.get("short") != "unfavorable":
        short = "possible_fit"
    elif label == "extended":
        short = "weak_fit"
    else:
        short = "no_fit"

    # MID — trend-led (EPS revision + narrative stage + macro mid bias).
    if eps in ("inflecting_up", "improving") and stage in ("early", "growing", "mature") and bias.get("mid") in ("favorable", "neutral"):
        mid = "strong_fit"
    elif eps != "deteriorating" and bias.get("mid") != "unfavorable":
        mid = "possible_fit"
    elif stage == "cooling":
        mid = "weak_fit"
    else:
        mid = "no_fit"

    # LONG — fundamentals-led (valuation + quality + margin).
    if val < 0.3 and qual > 0.6 and margin in ("expanding", "stable"):
        long = "strong_fit"
    elif val < 0.5 and qual > 0.4:
        long = "possible_fit"
    elif val > 0.7 and qual < 0.3:
        long = "no_fit"
    elif val >= 0.5:
        long = "weak_fit"
    else:
        long = "weak_fit"

    return {"short": short, "mid": mid, "long": long}


def _dominant_track_b_signal(track_b: Optional[TrackBResult]) -> str:
    """Name the Track B sub-signal that contributed most (for ALT_SIGNAL labels)."""
    if track_b is None:
        return "alt_signal"
    pairs = [
        ("insider", track_b.insider_buy_signal),
        ("unusual_news", track_b.unusual_news_signal),
        ("analyst_revision", track_b.analyst_revision_signal),
    ]
    pairs.sort(key=lambda p: p[1], reverse=True)
    return pairs[0][0] if pairs[0][1] > 0 else "alt_signal"


def build_signal_summary(
    fundamental: FundamentalResult,
    narrative: NarrativeResult,
    entry: EntryQualityResult,
    track_b: Optional[TrackBResult],
    candidate_type: str,
) -> list:
    """Build up to 5 human-readable key-signal strings (code, NOT LLM).

    Priority order: (1) EPS inflection if inflecting_up, (2) narrative stage +
    theme_tags, (3) entry quality with RSI + distance from 52W high, (4)
    valuation percentile if < 0.3 (undervalued), (5) Track B trigger if ALT_SIGNAL.
    """
    out: list[str] = []
    if fundamental.eps_revision_direction == "inflecting_up":
        out.append("EPS inflection: beat after prior miss (cycle-bottom signal)")
    if narrative.narrative_stage and narrative.narrative_stage != "unknown":
        themes = ", ".join(narrative.theme_tags[:3]) if narrative.theme_tags else "—"
        out.append(f"Narrative: {narrative.narrative_stage} ({themes})")
    dist = entry.distance_from_52w_high
    dist_txt = f"{dist:.0f}% from 52W high" if isinstance(dist, (int, float)) else "52W high n/a"
    out.append(f"Entry: {entry.entry_quality_label} (RSI {entry.rsi_position}, {dist_txt})")
    if isinstance(fundamental.valuation_percentile, (int, float)) and fundamental.valuation_percentile < 0.3:
        out.append(f"Undervalued vs sector (val pct {fundamental.valuation_percentile:.2f})")
    if candidate_type in ("ALT_SIGNAL", "BOTH") and track_b is not None and track_b.is_standalone_trigger:
        out.append(f"ALT_SIGNAL trigger: {_dominant_track_b_signal(track_b)} (Track B {track_b.track_b_score:.2f})")
    return out[:5]


def build_ticker_result(
    ticker: str,
    fundamental: FundamentalResult,
    narrative: NarrativeResult,
    entry: EntryQualityResult,
    track_b: TrackBResult,
    macro_regime: str,
    layer1_passed: bool = True,
) -> TickerSignalResult:
    """Assemble a full dual-track :class:`TickerSignalResult` (deterministic).

    ``candidate_type``:
    * **FUNNEL** — passed the Track A funnel; Track B did not standalone-trigger.
    * **BOTH**   — passed the funnel AND Track B standalone-triggered.
    * **ALT_SIGNAL** — entered via the Track B standalone trigger only (did NOT
      pass the funnel); composite is the Track B score, displayed separately.
    """
    track_a_score = compute_track_a_score(fundamental, narrative, entry)
    if not layer1_passed:
        candidate_type = "ALT_SIGNAL"
    elif track_b.is_standalone_trigger:
        candidate_type = "BOTH"
    else:
        candidate_type = "FUNNEL"

    composite = compute_composite(track_a_score, track_b.track_b_score, candidate_type)
    horizon = compute_horizon_fit(fundamental, narrative, entry, _bias_for_regime(macro_regime))
    summary = build_signal_summary(fundamental, narrative, entry, track_b, candidate_type)

    track_a = TrackAResult(
        layer1_passed=layer1_passed,
        layer2_narrative=narrative,
        layer3_fundamental=fundamental,
        track_a_score=track_a_score,
        entry_quality=entry,
    )
    return TickerSignalResult(
        ticker=ticker,
        track_a=track_a,
        track_b=track_b,
        composite_score=composite,
        horizon_fit=horizon,
        signal_summary=summary,
        candidate_type=candidate_type,
        entry_quality=entry,
    )


# ===========================================================================
# Phase 6B v3 — HORIZON-NATIVE THREE-TRACK SCORING
# ---------------------------------------------------------------------------
# Replaces the single composite score with three INDEPENDENT horizon scores
# (short / mid / long), each with its own deterministic weighting logic, plus a
# signal_strength ("triple"/"double"/"single"/"none") derived from how many
# horizons clear their threshold. Catalyst inputs come from the single merged
# LLM narrative call (NarrativeResult.catalyst_*). All scoring is deterministic.
# ===========================================================================

# ----- Short horizon (timing) weights + threshold (sum = 1.0) --------------
_SHORT_W_TECH = 0.40        # technical_momentum
_SHORT_W_CATALYST = 0.35    # catalyst_score
_SHORT_W_MOMENTUM = 0.25    # momentum_continuation
_SHORT_THRESHOLD = 0.65

# ----- Mid horizon (trend) weights + threshold (sum = 1.0) -----------------
_MID_W_EPS = 0.35           # eps_revision
_MID_W_NARRATIVE = 0.30     # narrative_stage
_MID_W_VALUATION = 0.20     # valuation
_MID_W_QUALITY = 0.15       # quality_composite
_MID_THRESHOLD = 0.60

# ----- Long horizon (fundamentals) weights + threshold (sum = 1.0) ---------
_LONG_W_VALUATION = 0.35    # valuation
_LONG_W_QUALITY = 0.35      # quality_composite
_LONG_W_NARRATIVE = 0.20    # narrative_stage
_LONG_W_MACRO = 0.10        # macro_alignment
_LONG_THRESHOLD = 0.55

# Mid-horizon narrative-stage map (early/growing favored).
_MID_STAGE_SCORE = {"early": 1.0, "growing": 0.75, "mature": 0.30, "cooling": 0.10,
                    "unknown": 0.30}
# Long-horizon narrative-stage map (steeper decay than mid).
_LONG_STAGE_SCORE = {"early": 1.0, "growing": 0.60, "mature": 0.25, "cooling": 0.05,
                     "unknown": 0.25}
# Long-horizon macro-alignment map.
_LONG_MACRO_SCORE = {"aligned": 1.0, "neutral": 0.5, "misaligned": 0.1}

HORIZONS = ("short", "mid", "long")
_HORIZON_THRESHOLDS = {"short": _SHORT_THRESHOLD, "mid": _MID_THRESHOLD,
                       "long": _LONG_THRESHOLD}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _finite(x) -> Optional[float]:
    """Return ``x`` as a float, or ``None`` if it is missing / NaN / non-numeric."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    xf = float(x)
    return None if xf != xf else xf  # NaN != NaN


def _valuation_horizon_score(valuation_percentile: float) -> float:
    """Shared mid/long valuation sub-score from the sector valuation percentile.

    percentile < 0.3 -> 1.0; 0.3–0.5 -> 0.65; 0.5–0.7 -> 0.35; > 0.7 -> 0.10.
    """
    pct = _finite(valuation_percentile)
    if pct is None:
        pct = 0.5
    if pct < 0.3:
        return 1.0
    if pct < 0.5:
        return 0.65
    if pct < 0.7:
        return 0.35
    return 0.10


def technical_momentum_score(snap: dict) -> float:
    """SHORT sub-score 0.0–1.0 from the technical snapshot (deterministic).

    RSI base: 45–65 -> 1.0; 65–72 -> 0.7; < 45 -> 0.5; > 72 -> 0.2 (missing 0.5).
    Bonuses/penalties: ADX > 25 +0.15, ADX < 15 -0.1; Vol_ratio_20d > 1.3 +0.1;
    above_SMA200 +0.05. Clamped to [0, 1].
    """
    snap = snap or {}
    rsi = _finite(snap.get("RSI_14"))
    if rsi is None:
        base = 0.5
    elif 45.0 <= rsi <= 65.0:
        base = 1.0
    elif 65.0 < rsi <= 72.0:
        base = 0.7
    elif rsi < 45.0:
        base = 0.5
    else:  # rsi > 72
        base = 0.2
    adx = _finite(snap.get("ADX"))
    if adx is not None:
        if adx > 25.0:
            base += 0.15
        elif adx < 15.0:
            base -= 0.1
    vr = _finite(snap.get("Vol_ratio_20d"))
    if vr is not None and vr > 1.3:
        base += 0.1
    if bool(snap.get("above_SMA200", False)):
        base += 0.05
    return round(_clamp01(base), 4)


def catalyst_score(narrative: NarrativeResult) -> float:
    """SHORT sub-score 0.0–1.0 from the merged-LLM catalyst fields (deterministic).

    catalyst_horizon contains "short" -> base 0.8; catalyst_recency "recent"
    (<=7d) -> +0.2 bonus; catalyst_recency "moderate" (8–30d) -> base 0.5; no
    catalyst -> 0.2; already_priced_in -> ×0.5 multiplier. Clamped to [0, 1].
    """
    horizon = narrative.catalyst_horizon or []
    recency = narrative.catalyst_recency or "none"
    if "short" in horizon:
        base = 0.8
    elif recency == "moderate":
        base = 0.5
    else:
        base = 0.2  # no (short) catalyst
    if recency == "recent":
        base += 0.2
    if narrative.already_priced_in:
        base *= 0.5
    return round(_clamp01(base), 4)


def momentum_continuation_score(snap: dict) -> float:
    """SHORT sub-score 0.0–1.0 from the trailing 1-month return (deterministic).

    1M return > +10% -> 0.9; 5–10% -> 0.7; 0–5% -> 0.5; negative -> 0.2
    (missing -> 0.5, neutral).
    """
    ret_1m = _finite((snap or {}).get("ret_1m"))
    if ret_1m is None:
        return 0.5
    if ret_1m > 10.0:
        return 0.9
    if ret_1m >= 5.0:
        return 0.7
    if ret_1m >= 0.0:
        return 0.5
    return 0.2


def compute_short_score(snap: dict, narrative: NarrativeResult) -> float:
    """Independent SHORT-horizon score 0.0–1.0 (technical_momentum 0.40 /
    catalyst 0.35 / momentum_continuation 0.25)."""
    tech = technical_momentum_score(snap)
    cat = catalyst_score(narrative)
    mom = momentum_continuation_score(snap)
    score = _SHORT_W_TECH * tech + _SHORT_W_CATALYST * cat + _SHORT_W_MOMENTUM * mom
    return round(_clamp01(score), 4)


def compute_mid_score(fundamental: FundamentalResult, narrative: NarrativeResult) -> float:
    """Independent MID-horizon score 0.0–1.0 (eps_revision 0.35 / narrative_stage
    0.30 / valuation 0.20 / quality_composite 0.15)."""
    eps = _EPS_REV_SCORE.get(fundamental.eps_revision_direction, 0.30)
    stage = _MID_STAGE_SCORE.get(narrative.narrative_stage, 0.30)
    if narrative.macro_alignment == "aligned":
        stage += 0.10
    stage = _clamp01(stage)
    valuation = _valuation_horizon_score(fundamental.valuation_percentile)
    quality = _clamp01(fundamental.quality_composite)
    score = (
        _MID_W_EPS * eps
        + _MID_W_NARRATIVE * stage
        + _MID_W_VALUATION * valuation
        + _MID_W_QUALITY * quality
    )
    return round(_clamp01(score), 4)


def compute_long_score(fundamental: FundamentalResult, narrative: NarrativeResult) -> float:
    """Independent LONG-horizon score 0.0–1.0 (valuation 0.35 / quality_composite
    0.35 / narrative_stage 0.20 / macro_alignment 0.10)."""
    valuation = _valuation_horizon_score(fundamental.valuation_percentile)
    quality = _clamp01(fundamental.quality_composite)
    stage = _LONG_STAGE_SCORE.get(narrative.narrative_stage, 0.25)
    macro = _LONG_MACRO_SCORE.get(narrative.macro_alignment, 0.5)
    score = (
        _LONG_W_VALUATION * valuation
        + _LONG_W_QUALITY * quality
        + _LONG_W_NARRATIVE * stage
        + _LONG_W_MACRO * macro
    )
    return round(_clamp01(score), 4)


def derive_horizons_hit(short_score: float, mid_score: float, long_score: float) -> list:
    """Return the horizons whose score clears its threshold (0.65 / 0.60 / 0.55)."""
    scores = {"short": short_score, "mid": mid_score, "long": long_score}
    return [h for h in HORIZONS if scores[h] >= _HORIZON_THRESHOLDS[h]]


def derive_signal_strength(horizons_hit: list) -> str:
    """Map the number of horizons hit -> triple / double / single / none."""
    n = len(horizons_hit or [])
    if n == 3:
        return "triple"
    if n == 2:
        return "double"
    if n == 1:
        return "single"
    return "none"


def _data_coverage(
    fundamental: FundamentalResult,
    narrative: NarrativeResult,
    snap: dict,
) -> float:
    """Deterministic 0.0–1.0 data-coverage estimate across the input layers.

    Equal-weight fraction of: (1) any live fundamental source, (2) a live
    (LLM) narrative, (3) a usable technical snapshot.
    """
    parts = []
    srcs = list((fundamental.data_source or {}).values())
    parts.append(1.0 if any(s == _LIVE for s in srcs) else 0.0)
    parts.append(1.0 if narrative.data_source == _LIVE else 0.0)
    parts.append(1.0 if (snap or {}).get("RSI_14") is not None else 0.0)
    return round(sum(parts) / len(parts), 2) if parts else 0.0


def _theme_tags_for_ticker(ticker: str, lang: str = "en") -> list:
    """Reverse-lookup fallback theme tags for ``ticker`` from THEME_BASKETS.

    When the LLM returns no ``theme_tags``, a ticker that appears in one or more
    ``THEME_BASKETS`` constituent lists is tagged with the matching theme's
    ``label_zh`` (zh) / ``label_en`` (en). Deterministic, no network. Returns up
    to 3 labels; ``[]`` if the ticker is in no basket.
    """
    sym = (ticker or "").upper().strip()
    if not sym:
        return []
    label_key = "label_zh" if lang == "zh" else "label_en"
    out: list[str] = []
    try:
        for cfg in THEME_BASKETS.values():
            consts = [str(c).upper() for c in (cfg.get("constituents") or [])]
            if sym in consts:
                label = cfg.get(label_key) or cfg.get("label_en") or ""
                if label and label not in out:
                    out.append(label)
    except Exception:  # noqa: BLE001 — fail-closed (THEME_BASKETS unexpected shape)
        return []
    return out[:3]


@st.cache_data(ttl=_LLM_CACHE_TTL, show_spinner=False)
def _localize_texts(texts: tuple, lang: str) -> tuple:
    """Batch-translate display strings to ``lang`` (cached; key includes lang).

    Only translates when ``lang == "zh"``; English passes through untouched (no
    network). Uses ``lib.translator._translate_batch`` (deep-translator), which
    is itself fail-closed — returns the originals on any error. Cached TTL=3600
    keyed on ``(texts, lang)`` so each language caches separately and repeated
    identical strings are not re-translated.

    Fail-closed guarantees:
    - Any exception from ``_translate_batch`` returns the originals.
    - A partial result (fewer items than requested, e.g. some translations were
      empty or the batch was truncated) is detected and the originals are used
      for positions that are blank or missing, ensuring the caller always gets
      a tuple of the SAME LENGTH as ``texts``.
    """
    items = [str(t) for t in (texts or ())]
    if lang != "zh" or not items:
        return tuple(items)
    try:
        from lib.translator import _translate_batch
        translated = list(_translate_batch(items, "zh"))
        # Guarantee: result must have exactly len(items) entries.
        if len(translated) != len(items):
            return tuple(items)
        # Per-item guard: blank translation -> fall back to the original.
        result = []
        for orig, trans in zip(items, translated):
            result.append(trans if (trans and trans.strip()) else orig)
        return tuple(result)
    except Exception:  # noqa: BLE001 — fail-closed to the originals
        return tuple(items)


def build_key_signals(
    signal_strength: str,
    fundamental: FundamentalResult,
    narrative: NarrativeResult,
    entry: EntryQualityResult,
    track_b: Optional[TrackBResult],
    candidate_type: str,
    theme_tags: Optional[list] = None,
) -> list:
    """Build up to 5 human-readable key-signal strings (code-generated, NOT LLM).

    Priority order:
      1. "Triple signal: short + mid + long" if signal_strength == "triple"
      2. EPS inflection if eps_revision_direction == "inflecting_up"
      3. Catalyst summary if catalyst_summary non-empty
      4. Narrative stage + theme tags
      5. Entry quality with RSI and distance from 52W high
      6. Valuation undervalued flag if valuation_percentile < 0.3
      7. Track B trigger if candidate_type == "ALT_SIGNAL"

    ``theme_tags`` overrides ``narrative.theme_tags`` for the narrative line (used
    to surface the THEME_BASKETS reverse-lookup fallback). All strings are built
    in ENGLISH here; localization (zh) is applied later in build_candidate_signal.
    """
    out: list[str] = []
    tags_src = theme_tags if theme_tags is not None else narrative.theme_tags
    if signal_strength == "triple":
        out.append("Triple signal: short + mid + long")
    if fundamental.eps_revision_direction == "inflecting_up":
        out.append("EPS inflection: beat after prior miss (cycle-bottom signal)")
    if narrative.catalyst_summary:
        out.append(f"Catalyst: {narrative.catalyst_summary}")
    if narrative.narrative_stage and narrative.narrative_stage != "unknown":
        themes = ", ".join(tags_src[:3]) if tags_src else "—"
        out.append(f"Narrative: {narrative.narrative_stage} ({themes})")
    dist = entry.distance_from_52w_high
    dist_txt = f"{dist:.0f}% from 52W high" if isinstance(dist, (int, float)) else "52W high n/a"
    out.append(f"Entry: {entry.entry_quality_label} (RSI {entry.rsi_position}, {dist_txt})")
    if isinstance(fundamental.valuation_percentile, (int, float)) and fundamental.valuation_percentile < 0.3:
        out.append(f"Undervalued vs sector (val pct {fundamental.valuation_percentile:.2f})")
    if candidate_type == "ALT_SIGNAL" and track_b is not None and track_b.is_standalone_trigger:
        out.append(f"ALT_SIGNAL trigger: {_dominant_track_b_signal(track_b)} (Track B {track_b.track_b_score:.2f})")
    return out[:5]


@dataclass
class CandidateSignal(TickerSignalResult):
    """Phase 6B v3 horizon-native candidate signal.

    Subclasses the v2 :class:`TickerSignalResult` (so existing dual-track
    consumers that rely on ``composite_score`` / ``horizon_fit`` / ``track_a`` /
    ``track_b`` / ``candidate_type`` / ``isinstance(..., TickerSignalResult)``
    keep working) while adding the three INDEPENDENT horizon scores, the derived
    ``signal_strength`` / ``horizons_hit``, the merged-LLM catalyst fields, and a
    code-generated ``key_signals`` list. Review-only: no execution field, no
    ``approved_for_execution``, no order side effects.
    """

    short_score: float = 0.0
    mid_score: float = 0.0
    long_score: float = 0.0
    horizons_hit: list = field(default_factory=list)
    signal_strength: str = "none"  # "triple" | "double" | "single" | "none"
    catalyst_summary: str = ""
    catalyst_horizon: list = field(default_factory=list)
    catalyst_recency: str = "none"  # "recent" | "moderate" | "none"
    already_priced_in: bool = False
    narrative_stage: str = "unknown"
    narrative_theme_tags: list = field(default_factory=list)
    eps_revision_direction: str = "unknown"
    valuation_percentile: float = 0.5
    entry_quality_label: str = "fair"
    track_b_score: float = 0.0
    key_signals: list = field(default_factory=list)  # up to 5, code-generated
    data_coverage: float = 0.0


def build_candidate_signal(
    ticker: str,
    fundamental: FundamentalResult,
    narrative: NarrativeResult,
    entry: EntryQualityResult,
    track_b: TrackBResult,
    snap: dict,
    macro_regime: str,
    layer1_passed: bool = True,
    lang: str = "en",
) -> CandidateSignal:
    """Assemble a horizon-native :class:`CandidateSignal` (deterministic).

    Computes the three independent horizon scores, derives ``horizons_hit`` /
    ``signal_strength``, builds the code-generated ``key_signals``, and preserves
    the v2 dual-track fields (``track_a`` / ``track_b`` / ``composite_score`` /
    ``horizon_fit`` / ``candidate_type``). ``candidate_type``:

    * **FUNNEL** — passed the Track A funnel; Track B did not standalone-trigger.
    * **BOTH**   — passed the funnel AND Track B standalone-triggered.
    * **ALT_SIGNAL** — entered via the Track B standalone trigger only (did NOT
      pass the funnel). Horizon scores are still computed normally.

    ``lang``: when ``"zh"`` the human-readable DISPLAY fields (catalyst_summary,
    narrative theme tags, key_signals) are translated to Chinese via
    ``lib.translator`` before being stored on the returned :class:`CandidateSignal`
    (the English LLM prompt/response are unchanged — only the final display text
    is localized; cached per-language). ``theme_tags`` empty -> THEME_BASKETS
    reverse-lookup fallback.
    """
    short = compute_short_score(snap, narrative)
    mid = compute_mid_score(fundamental, narrative)
    long = compute_long_score(fundamental, narrative)
    horizons_hit = derive_horizons_hit(short, mid, long)
    signal_strength = derive_signal_strength(horizons_hit)

    if not layer1_passed:
        candidate_type = "ALT_SIGNAL"
    elif track_b is not None and track_b.is_standalone_trigger:
        candidate_type = "BOTH"
    else:
        candidate_type = "FUNNEL"

    # Theme tags: prefer the LLM taxonomy tags; if empty, fall back to the
    # THEME_BASKETS constituent reverse-lookup (label_zh / label_en by lang).
    theme_tags = list(narrative.theme_tags or [])
    if not theme_tags:
        theme_tags = _theme_tags_for_ticker(ticker, lang)

    key_signals = build_key_signals(
        signal_strength, fundamental, narrative, entry, track_b, candidate_type,
        theme_tags=theme_tags,
    )
    # v2 dual-track fields preserved for backward compatibility.
    track_a_score = compute_track_a_score(fundamental, narrative, entry)
    composite = round((short + mid + long) / 3.0, 4)
    horizon_fit = compute_horizon_fit(
        fundamental, narrative, entry, _bias_for_regime(macro_regime)
    )
    track_a = TrackAResult(
        layer1_passed=layer1_passed,
        layer2_narrative=narrative,
        layer3_fundamental=fundamental,
        track_a_score=track_a_score,
        entry_quality=entry,
    ) if layer1_passed else None

    catalyst_summary = narrative.catalyst_summary

    # --- Chinese localization of display fields (zh only; fail-closed) -------
    # The English LLM response is untouched; only the final display strings
    # (catalyst summary, theme-tag labels, key signals) are translated, batched
    # into a single cached translate call so repeated strings reuse the cache.
    if lang == "zh":
        _orig_catalyst = catalyst_summary
        _orig_tags = list(theme_tags)
        _orig_signals = list(key_signals)
        _n_tags = len(theme_tags)
        _n_sigs = len(key_signals)
        _expected = 1 + _n_tags + _n_sigs
        try:
            _to_loc = [catalyst_summary] + list(theme_tags) + list(key_signals)
            _loc = list(_localize_texts(tuple(_to_loc), "zh"))
            # Length guard: if the result is shorter than expected, skip the
            # localization entirely and keep the original English values.
            if len(_loc) >= _expected:
                _cat_zh = _loc[0]
                # Blank-translation guard for catalyst_summary.
                catalyst_summary = (_cat_zh if (_cat_zh and _cat_zh.strip())
                                    else _orig_catalyst)
                theme_tags = _loc[1:1 + _n_tags]
                key_signals = _loc[1 + _n_tags:1 + _n_tags + _n_sigs]
                # Any blank translated tag/signal falls back to the English original.
                theme_tags = [
                    (zh_t if (zh_t and zh_t.strip()) else en_t)
                    for zh_t, en_t in zip(theme_tags, _orig_tags)
                ]
                key_signals = [
                    (zh_s if (zh_s and zh_s.strip()) else en_s)
                    for zh_s, en_s in zip(key_signals, _orig_signals)
                ]
            # else: keep _orig_* values (length mismatch — translation skipped)
        except Exception:  # noqa: BLE001 — fail-closed to the originals
            catalyst_summary = _orig_catalyst
            theme_tags = _orig_tags
            key_signals = _orig_signals

    return CandidateSignal(
        ticker=ticker,
        track_a=track_a,
        track_b=track_b,
        composite_score=composite,
        horizon_fit=horizon_fit,
        signal_summary=key_signals,
        candidate_type=candidate_type,
        entry_quality=entry,
        fundamental=None,
        narrative=None,
        short_score=short,
        mid_score=mid,
        long_score=long,
        horizons_hit=horizons_hit,
        signal_strength=signal_strength,
        catalyst_summary=catalyst_summary,
        catalyst_horizon=list(narrative.catalyst_horizon or []),
        catalyst_recency=narrative.catalyst_recency,
        already_priced_in=narrative.already_priced_in,
        narrative_stage=narrative.narrative_stage,
        narrative_theme_tags=list(theme_tags or []),
        eps_revision_direction=fundamental.eps_revision_direction,
        valuation_percentile=float(fundamental.valuation_percentile),
        entry_quality_label=entry.entry_quality_label,
        track_b_score=track_b.track_b_score if track_b is not None else 0.0,
        key_signals=key_signals,
        data_coverage=_data_coverage(fundamental, narrative, snap),
    )


# ===========================================================================
# Phase 6B v1 BACKWARD-COMPATIBILITY SHIMS
# ---------------------------------------------------------------------------
# The legacy v1 dataclasses + helpers below are preserved so existing v1
# consumers (and the v1 test) keep importing/working. New code should use the
# dual-track contracts above. None of these shims call the LLM.
# ===========================================================================


@dataclass
class FundamentalSignals:
    """(v1 compat) Fundamental + analyst signals for one ticker."""

    eps_surprise_trend: str = "unknown"
    recommendation_momentum: str = "unknown"
    valuation_percentile: float = 0.5
    quality_score: float = 0.0
    data_source: dict = field(default_factory=dict)
    sector: Optional[str] = None
    forward_pe: Optional[float] = None
    trailing_pe: Optional[float] = None
    market_cap: Optional[float] = None


@dataclass
class NarrativeSignals:
    """(v1 compat) Keyword-derived narrative signals for one ticker."""

    theme_tags: list = field(default_factory=list)
    narrative_strength: str = "unknown"
    macro_alignment: str = "neutral"
    news_count: int = 0
    data_source: str = _FIXTURE


# EntryQualityScore is structurally identical to the v2 EntryQualityResult, so it
# is kept as an alias (one class, both names).
EntryQualityScore = EntryQualityResult


def _attribute_themes(headlines: list) -> list:
    """(v1 compat) Keyword-rule theme attribution over headlines (NON-LLM)."""
    if not headlines:
        return []
    counts: dict[str, int] = {}
    for h in headlines:
        low = str(h).lower()
        for theme, kws in _THEME_KEYWORDS.items():
            if any(kw in low for kw in kws):
                counts[theme] = counts.get(theme, 0) + 1
    if not counts:
        return ["other"]
    return sorted(counts.keys(), key=lambda th: (-counts[th], THEME_TAXONOMY.index(th)))


def _quality_score(info: dict) -> float:
    """(v1 compat) Alias of the fixed-anchor quality composite."""
    return _quality_anchor(info)


def _recommendation_momentum(rows: list) -> str:
    """(v1 compat) Direction of the analyst buy/sell ratio change."""
    def _ratio(row: dict) -> Optional[float]:
        try:
            sb = float(row.get("strongBuy", 0) or 0)
            b = float(row.get("buy", 0) or 0)
            h = float(row.get("hold", 0) or 0)
            s = float(row.get("sell", 0) or 0)
            ss = float(row.get("strongSell", 0) or 0)
            total = sb + b + h + s + ss
            if total <= 0:
                return None
            return (sb + b) / total
        except Exception:  # noqa: BLE001
            return None

    if not rows or len(rows) < 2:
        return "unknown"
    latest = _ratio(rows[0])
    older_idx = 3 if len(rows) > 3 else len(rows) - 1
    older = _ratio(rows[older_idx])
    if latest is None or older is None:
        return "unknown"
    delta = latest - older
    if delta > 0.05:
        return "upgrading"
    if delta < -0.05:
        return "downgrading"
    return "stable"


def _eps_surprise_trend(rows: list) -> str:
    """(v1 compat) EPS surprise trend over the last (≤4) quarters."""
    series: list[float] = []
    for row in (rows or [])[:4]:
        sp = row.get("surprisePercent")
        if isinstance(sp, (int, float)):
            series.append(float(sp))
            continue
        actual = row.get("actual")
        est = row.get("estimate")
        if isinstance(actual, (int, float)) and isinstance(est, (int, float)) and est not in (0, None):
            series.append((float(actual) - float(est)) / abs(float(est)) * 100.0)
    if len(series) < 2:
        return "unknown"
    series.reverse()
    half = len(series) // 2
    older = series[:half] or series[:1]
    recent = series[half:] or series[-1:]
    older_avg = sum(older) / len(older)
    recent_avg = sum(recent) / len(recent)
    delta = recent_avg - older_avg
    if delta > 1.0:
        return "improving"
    if delta < -1.0:
        return "deteriorating"
    return "mixed"


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def fetch_fundamental_signals(ticker: str) -> FundamentalSignals:
    """(v1 compat) Compute fundamental + analyst signals (fail-closed)."""
    try:
        info = _yf_info(ticker)
        fundamentals_src = _LIVE if info else _FIXTURE
        quality = _quality_anchor(info)
        val_pct = _valuation_percentile(info)

        rec_rows = _finnhub_get(
            _FINNHUB_RECOMMENDATION, {"symbol": ticker, "token": FINNHUB_API_KEY}
        )
        if isinstance(rec_rows, list) and rec_rows:
            rec_momentum = _recommendation_momentum(rec_rows)
            rec_src = _LIVE
        else:
            rec_momentum = "unknown"
            rec_src = _FIXTURE

        eps_rows = _finnhub_get(
            _FINNHUB_EARNINGS, {"symbol": ticker, "token": FINNHUB_API_KEY}
        )
        if isinstance(eps_rows, list) and eps_rows:
            eps_trend = _eps_surprise_trend(eps_rows)
            eps_src = _LIVE
        else:
            eps_trend = "unknown"
            eps_src = _FIXTURE

        return FundamentalSignals(
            eps_surprise_trend=eps_trend,
            recommendation_momentum=rec_momentum,
            valuation_percentile=val_pct,
            quality_score=quality,
            data_source={
                "fundamentals": fundamentals_src,
                "recommendation": rec_src,
                "earnings": eps_src,
            },
            sector=info.get("sector") if info else None,
            forward_pe=info.get("forwardPE") if info else None,
            trailing_pe=info.get("trailingPE") if info else None,
            market_cap=info.get("marketCap") if info else None,
        )
    except Exception:  # noqa: BLE001 — fully fail-closed
        return FundamentalSignals(
            data_source={"fundamentals": _FIXTURE, "recommendation": _FIXTURE,
                         "earnings": _FIXTURE}
        )


def _narrative_strength(news_count: int) -> str:
    """(v1 compat) Map 30-day news volume to a narrative-strength bucket."""
    if news_count >= 12:
        return "strong"
    if news_count >= 5:
        return "moderate"
    if news_count >= 1:
        return "weak"
    return "unknown"


def _macro_alignment(theme_tags: list, macro_regime: str) -> str:
    """(v1 compat) Deterministic theme<->regime alignment (NON-LLM)."""
    regime = (macro_regime or "unknown").lower()
    favored = _REGIME_ALIGNED_THEMES.get(regime, set())
    disfavored = _REGIME_MISALIGNED_THEMES.get(regime, set())
    tags = set(theme_tags or [])
    if tags & favored:
        return "aligned"
    if tags & disfavored:
        return "misaligned"
    return "neutral"


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def fetch_narrative_signals(ticker: str, macro_regime: str) -> NarrativeSignals:
    """(v1 compat) Keyword-based narrative signals from company-news (NON-LLM)."""
    try:
        news = fetch_company_news(ticker, days=30)
        if not news:
            return NarrativeSignals(
                theme_tags=[], narrative_strength="unknown",
                macro_alignment="neutral", news_count=0, data_source=_FIXTURE,
            )
        headlines = [item.get("headline", "") for item in news if item.get("headline")]
        news_count = len(headlines)
        theme_tags = _attribute_themes(headlines)
        strength = _narrative_strength(news_count)
        alignment = _macro_alignment(theme_tags, macro_regime)
        return NarrativeSignals(
            theme_tags=theme_tags, narrative_strength=strength,
            macro_alignment=alignment, news_count=news_count, data_source=_LIVE,
        )
    except Exception:  # noqa: BLE001 — fail-closed
        return NarrativeSignals(
            theme_tags=[], narrative_strength="unknown",
            macro_alignment="neutral", news_count=0, data_source=_FIXTURE,
        )


def score_ticker(ticker: str, macro_regime: str, lang: str = "en") -> CandidateSignal:
    """Single-ticker horizon-native scorer (v3 entry point).

    This is the lightweight, **LLM-free** per-ticker path: Layer 2 uses a neutral
    narrative (the full merged-LLM Layer 2 + catalyst call runs only inside the
    candidate-generation pipeline for the top-N tickers). It computes Layer 3
    fundamentals (fixed-anchor quality), entry quality, and Track B, then assembles
    a horizon-native :class:`CandidateSignal` with three independent horizon scores
    and a derived ``signal_strength``.

    ``lang`` (``"en"`` | ``"zh"``) localizes the DISPLAY fields (catalyst summary,
    theme-tag labels, key signals) before they are stored on the returned
    :class:`CandidateSignal` — see :func:`build_candidate_signal`. The translation
    runs before this call returns and is cached per-language.

    Fail-closed: any sub-step degrades to a neutral default; always returns a
    well-formed :class:`CandidateSignal` (each horizon score in [0, 1]). No LLM,
    no execution, no order side effects.
    """
    ticker = (ticker or "").upper().strip()
    try:
        fundamental = fetch_fundamental(ticker)
    except Exception:  # noqa: BLE001
        fundamental = FundamentalResult()
    try:
        snap = _technical_snapshot(ticker)
    except Exception:  # noqa: BLE001
        snap = {}
    entry = compute_entry_quality(ticker, snap)
    narrative = neutral_narrative()
    try:
        track_b = compute_track_b(ticker)
    except Exception:  # noqa: BLE001
        track_b = TrackBResult()
    return build_candidate_signal(
        ticker, fundamental, narrative, entry, track_b, snap, macro_regime,
        layer1_passed=True, lang=lang,
    )
