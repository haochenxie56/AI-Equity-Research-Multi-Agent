"""
lib/theme_baskets.py — Cross-GICS investment theme baskets.

This module extends the existing GICS-sector / subsector coverage with a small
set of **cross-GICS investment themes** relevant to the current AI-driven market
cycle (model training, HBM/memory, optical interconnect, data-center infra, AI
power, cloud data platforms, AI software, semi equipment, AI/robotics, biotech
AI, defense/space). A theme either maps to a representative ETF (e.g. SOXX,
BOTZ, XBI, ITA) or, when no clean ETF exists, is scored as an **equal-weight
average** across its hardcoded constituents.

Theme basket definitions: **manually curated, June 2026.** The constituent lists
are a static, human-curated snapshot and are intentionally hardcoded here so the
downstream Scanner universe is reproducible. They are not exhaustive and are not
investment advice.

Data sourcing:
  * ETF themes      -> ETF price returns (yfinance, free, no API key).
  * ETF-less themes -> equal-weight average return across constituents (yfinance).
  * Any fetch failure fails **closed** to a deterministic fixture fallback so the
    UI never crashes and never blocks on the network.

No paid APIs. No broker / order / execution. No DB / vector store / persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Load .env from the project root (one level up from lib/), matching the
# existing lib/signal_engine.py / lib/data_fetcher.py / lib/macro_data.py
# conventions. Harmless if python-dotenv or the file is absent.
try:  # pragma: no cover - environment bootstrap
    from pathlib import Path as _Path

    from dotenv import load_dotenv

    load_dotenv(_Path(__file__).parent.parent / ".env")
except Exception:  # noqa: BLE001 - fail-closed; .env is optional
    pass

import yfinance as yf  # free, no API key; module-level so tests can patch it

# Streamlit's st.cache_data executes the wrapped body even outside a running
# server, so importing it here keeps the module importable + testable offline.
import streamlit as st


# ── Theme basket definitions (manually curated, June 2026) ────────────────────

THEME_BASKETS = {
    "ai_chips": {
        "label_en": "AI Chips/GPU/ASIC/Accelerators",
        "label_zh": "AI算力芯片/GPU/ASIC",
        "etf": None,
        "constituents": ["NVDA", "AVGO", "AMD", "MRVL", "ARM",
                         "INTC", "QCOM", "ALAB", "MCHP", "NXPI"],
        "description_en": "Hardware powering AI model training and inference",
        "description_zh": "驱动AI模型训练与推理的核心算力硬件"
    },
    "semiconductor_mfg": {
        "label_en": "Semiconductor Manufacturing/Equipment/EDA",
        "label_zh": "半导体制造/设备/EDA",
        "etf": "SOXX",
        "constituents": ["TSM", "ASML", "AMAT", "LRCX", "KLAC",
                         "SNPS", "CDNS", "TER", "ONTO", "ASX"],
        "description_en": "Chipmaking equipment, advanced process nodes, and EDA tools",
        "description_zh": "芯片制造设备、先进制程及EDA工具"
    },
    "hbm_memory": {
        "label_en": "HBM / DRAM / NAND / Memory Systems",
        "label_zh": "HBM/DRAM/NAND/存储系统",
        "etf": None,
        "constituents": ["MU", "WDC", "STX", "PSTG", "NTAP", "SNDK",
                         "SIMO", "MRVL", "DELL"],
        "description_en": "High-bandwidth memory, NAND, and enterprise storage for AI workloads",
        "description_zh": "AI工作负载所需的高带宽存储、NAND及企业级存储系统"
    },
    "networking_optical": {
        "label_en": "Networking/Optical Interconnect/Ethernet",
        "label_zh": "网络互连 / 光模块 / 以太网",
        "etf": None,
        "constituents": ["ANET", "AVGO", "MRVL", "CSCO", "COHR", "GLW",
                         "LITE", "CIEN", "FN", "NOK", "ERIC"],
        "description_en": "AI data center networking, optical modules, and switching",
        "description_zh": "AI数据中心网络交换、光模块及互联基础设施"
    },
    "ai_servers_infra": {
        "label_en": "AI Servers/ODM/Enterprise Infrastructure",
        "label_zh": "AI服务器/整机/企业基础设施",
        "etf": None,
        "constituents": ["SMCI", "DELL", "HPE", "NTAP", "PSTG",
                         "CLS", "SANM", "JBL", "WDC", "STX"],
        "description_en": "AI server systems, ODM supply chain, and enterprise infrastructure",
        "description_zh": "AI服务器系统、ODM供应链及企业基础设施"
    },
    "datacenter_power": {
        "label_en": "Data Center Power/Grid/Cooling",
        "label_zh": "数据中心电力/电网/冷却",
        "etf": None,
        "constituents": ["ETN", "VRT", "PWR", "EME", "TT", "GEV",
                         "CARR", "JCI", "CEG", "VST", "OKLO"],
        "description_en": "Power delivery, grid infrastructure, and cooling for AI data centers",
        "description_zh": "为AI数据中心提供配电、电网建设及冷却系统"
    },
    "cloud_hyperscaler": {
        "label_en": "Cloud/Hyperscaler/Model Platforms",
        "label_zh": "云计算/Hyperscaler/模型平台",
        "etf": None,
        "constituents": ["MSFT", "GOOGL", "AMZN", "META", "ORCL",
                         "IBM", "BABA", "SAP", "CRM"],
        "description_en": "Cloud platforms, AI model infrastructure, and hyperscaler capex",
        "description_zh": "云计算平台、AI模型基础设施及Hyperscaler资本支出"
    },
    "data_infrastructure": {
        "label_en": "Data Infrastructure/Database",
        "label_zh": "数据基础设施/数据库",
        "etf": None,
        "constituents": ["SNOW", "MDB", "DDOG", "ESTC", "CFLT",
                         "PLTR", "GTLB", "S", "NET", "ORCL"],
        "description_en": "Data platforms, real-time pipelines, and AI-ready data infrastructure",
        "description_zh": "数据平台、实时数据管道及AI就绪数据基础设施"
    },
    "ai_software": {
        "label_en": "AI Application Layer/Enterprise SaaS/Agentic Workflow",
        "label_zh": "AI应用层/企业SaaS/Agentic工作流",
        "etf": None,
        "constituents": ["MSFT", "CRM", "NOW", "ADBE", "INTU",
                         "WDAY", "HUBS", "SHOP", "APPF", "DUOL"],
        "description_en": "Enterprise SaaS platforms integrating AI into business workflows",
        "description_zh": "将AI集成进企业工作流的SaaS平台及Agentic应用"
    },
    "cybersecurity": {
        "label_en": "AI Security/Cybersecurity",
        "label_zh": "AI安全/网络安全",
        "etf": None,
        "constituents": ["PANW", "CRWD", "ZS", "NET", "S",
                         "OKTA", "CYBR", "FTNT", "TENB", "VRNS"],
        "description_en": "AI-driven cybersecurity platforms and data governance",
        "description_zh": "AI驱动的网络安全平台及数据治理"
    },
    "edge_ai_devices": {
        "label_en": "AI PC/Mobile/Edge AI/Endpoint Devices",
        "label_zh": "AI PC/手机/边缘AI/终端设备",
        "etf": None,
        "constituents": ["AAPL", "QCOM", "MSFT", "AMD", "INTC", "NVDA",
                         "DELL", "HPQ", "LOGI", "STM", "NXPI"],
        "description_en": "On-device AI, AI PCs, smartphones, and edge inference chips",
        "description_zh": "端侧AI、AI PC、智能手机及边缘推理芯片"
    },
    "robotics_autonomous": {
        "label_en": "Robotics/Autonomous Driving/Physical AI",
        "label_zh": "机器人/自动驾驶/物理AI",
        "etf": "BOTZ",
        "constituents": ["TSLA", "ISRG", "SYM", "TER", "ROK",
                         "HON", "ABBNY", "FANUY", "MBLY", "OUST", "RR"],
        "description_en": "Industrial robotics, autonomous vehicles, and physical AI systems",
        "description_zh": "工业机器人、自动驾驶及物理AI系统"
    }
}


# ── Phase 7B Task 2 config (inner ring — AI theme chain relay) ────────────────
# Default benchmark for theme EXCESS returns (per-theme overridable via a
# "benchmark" key in THEME_BASKETS; defaults to QQQ).
THEME_BENCHMARK_DEFAULT = "QQQ"

# Same multi-window set as lib/relative_strength (mirrored locally).
THEME_WINDOW_DAYS = {"5d": 5, "10d": 10, "1m": 21, "3m": 63, "6m": 126, "12m": 252}

# Divergence matrix (Task 2): 5D vs 1M EXCESS-return quadrants → stage label.
# "strong" means excess strictly greater than the threshold; the boundary value
# itself falls on the weak side (<=). Thresholds in percentage points.
DIVERGENCE_THRESHOLDS = {"excess_5d_pp": 0.0, "excess_1m_pp": 0.0}

# Group-confirmation breadth: a stage is "confirmed" only when at least this
# fraction of constituents beat the benchmark over the active window (single-
# stock event guard). Reported alongside the % above SMA20.
BREADTH_CONFIRM_FRACTION = 0.50

# Macro lens (regime modulates the LENS, never the ranking): which window the
# theme view emphasizes for breadth / divergence read by default. Display/default
# only — theme scores are NOT re-ranked by regime.
MACRO_LENS_WINDOW = {
    "risk_on": "1m",       # trend emphasis
    "risk_off": "5d",      # short-window + downside-resilience emphasis
    "transition": "5d",
    "degraded": "1m",
    "unknown": "1m",
}

# Stage labels (deterministic).
STAGE_ROTATING_IN = "rotating_in"
STAGE_LEADING = "leading"
STAGE_ROTATING_OUT = "rotating_out"
STAGE_OUT_OF_FAVOR = "out_of_favor"


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class ThemeMomentumResult:
    """Deterministic momentum readout for one cross-GICS theme basket."""

    theme_key: str
    label_en: str
    label_zh: str
    constituents: list[str]
    etf: Optional[str]
    return_1m: Optional[float] = None
    return_3m: Optional[float] = None
    return_6m: Optional[float] = None
    # Percentile rank (0.0-1.0) of this theme's EXCESS-3M return (vs benchmark)
    # across all themes in the same compute_all_themes() call. Standalone calls
    # leave it at 0.0. (Phase 7B: basis switched from absolute 3M to excess 3M.)
    momentum_score: float = 0.0
    # "etf" | "equal_weight" | "fixture"
    data_source: str = "fixture"
    # Constituents whose price history was successfully read (equal-weight info).
    n_constituents_used: int = 0
    # ── Phase 7B Task 2 — multi-window EXCESS vs benchmark + stage + breadth ──
    benchmark: str = THEME_BENCHMARK_DEFAULT
    # Per-window theme excess vs benchmark (pp): {"5d":.., "10d":.., ...}.
    excess: dict = field(default_factory=dict)
    excess_5d: Optional[float] = None
    excess_1m: Optional[float] = None
    excess_3m: Optional[float] = None
    # Divergence-matrix stage label + whether breadth confirms it.
    stage: str = ""
    stage_confirmed: bool = False
    # Group confirmation breadth over the active window.
    active_window: str = "1m"
    breadth_beat_pct: Optional[float] = None       # % constituents beating bench
    breadth_above_sma20_pct: Optional[float] = None  # % constituents above SMA20
    n_constituents_breadth: int = 0
    # Per-constituent EXCESS vs benchmark (pp/frac, rounded 4dp) by window:
    #   {ticker: {"1m": .., "3m": .., "active": ..}}. Only present windows with a
    #   computable value are stored (None filtered). Populated by
    #   _enrich_excess_stage_breadth (no new fetch — reuses constituent_closes);
    #   fixture-fallback themes never reach enrichment so this stays {}.
    constituent_rs: dict = field(default_factory=dict)


# ── Deterministic fixture fallback (offline / fail-closed) ────────────────────
# Used only when a live yfinance fetch fails. Plausible static placeholders so
# the page renders something coherent; clearly labeled data_source="fixture".
_FIXTURE_RETURNS: dict[str, tuple[float, float, float]] = {
    "ai_chips":               (5.0, 14.0, 30.0),
    "semiconductor_mfg":      (3.5, 9.0, 18.0),
    "hbm_memory":             (6.2, 15.5, 22.0),
    "networking_optical":     (5.1, 14.0, 28.0),
    "ai_servers_infra":       (4.0, 11.0, 20.0),
    "datacenter_power":       (3.0, 8.5, 17.0),
    "cloud_hyperscaler":      (2.5, 7.0, 15.0),
    "data_infrastructure":    (2.0, 6.0, 12.0),
    "ai_software":            (1.0, 3.5, 8.0),
    "cybersecurity":          (2.2, 6.5, 13.0),
    "edge_ai_devices":        (1.5, 4.5, 9.5),
    "robotics_autonomous":    (1.1, 4.0, 9.0),
}

# Trading-day windows (~21/63/126 sessions ≈ 1M/3M/6M).
_WIN_1M = 21
_WIN_3M = 63
_WIN_6M = 126


# ── Internal price helpers (yfinance, fail-closed) ────────────────────────────

def _history_close(ticker: str):
    """Return a 1y Close price Series for `ticker`, or None on any failure.

    Always fetches ~1y so 1M / 3M / 6M windows are all computable regardless of
    the caller's `period` hint. Fail-closed: any exception -> None.
    """
    try:
        hist = yf.Ticker(ticker).history(period="1y")
        if hist is None or getattr(hist, "empty", True):
            return None
        if "Close" not in hist.columns:
            return None
        close = hist["Close"].dropna()
        if len(close) < 2:
            return None
        return close
    except Exception:  # noqa: BLE001 - fail-closed
        return None


def _pct_return(close, n: int) -> Optional[float]:
    """N-trading-day percentage return (rounded to 2dp), or None if too short."""
    try:
        if close is None or len(close) < n + 1:
            return None
        prev = float(close.iloc[-n - 1])
        last = float(close.iloc[-1])
        if prev == 0:
            return None
        return round((last / prev - 1.0) * 100.0, 2)
    except Exception:  # noqa: BLE001 - fail-closed
        return None


def _ticker_returns(ticker: str) -> Optional[tuple[Optional[float], Optional[float], Optional[float]]]:
    """(1M, 3M, 6M) returns for one ticker, or None if its history is unusable."""
    close = _history_close(ticker)
    if close is None:
        return None
    return (
        _pct_return(close, _WIN_1M),
        _pct_return(close, _WIN_3M),
        _pct_return(close, _WIN_6M),
    )


def _avg(values: list[Optional[float]]) -> Optional[float]:
    """Mean of the non-None values (rounded 2dp), or None if all are None."""
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


# ── Phase 7B Task 2 — pure divergence / breadth / excess helpers ──────────────

def classify_divergence(excess_5d: Optional[float],
                        excess_1m: Optional[float]) -> str:
    """5D-vs-1M EXCESS-return quadrant → deterministic stage label.

    rotating_in : 5D strong / 1M flat-or-weak (early relay-in).
    leading     : both strong.
    rotating_out: 5D weak / 1M strong (momentum fading).
    out_of_favor: both weak.
    Returns "" when either window is missing. "strong" = excess strictly above
    the configured threshold; the boundary value itself is weak (<=)."""
    if excess_5d is None or excess_1m is None:
        return ""
    s5 = excess_5d > DIVERGENCE_THRESHOLDS["excess_5d_pp"]
    s1 = excess_1m > DIVERGENCE_THRESHOLDS["excess_1m_pp"]
    if s5 and s1:
        return STAGE_LEADING
    if s5 and not s1:
        return STAGE_ROTATING_IN
    if (not s5) and s1:
        return STAGE_ROTATING_OUT
    return STAGE_OUT_OF_FAVOR


def _sma_last(close, period: int) -> Optional[float]:
    """Last simple moving average of a Close Series, or None."""
    try:
        if close is None or len(close) < period:
            return None
        return float(close.iloc[-period:].mean())
    except Exception:  # noqa: BLE001
        return None


def compute_theme_breadth(constituent_closes: dict, bench_window_ret: Optional[float],
                          active_window: str):
    """(% beating benchmark, % above SMA20, n_used) over the active window.

    ``constituent_closes`` is ``{ticker: Close Series|None}``; ``bench_window_ret``
    is the benchmark's return over ``active_window`` (percent). Deterministic, no
    I/O. Returns ``(None, None, 0)`` when no constituent has usable history."""
    n_days = THEME_WINDOW_DAYS.get(active_window, 21)
    beat = above = used = 0
    for close in constituent_closes.values():
        r = _pct_return(close, n_days)
        if r is None:
            continue
        used += 1
        if bench_window_ret is not None and (r - bench_window_ret) > 0:
            beat += 1
        s20 = _sma_last(close, 20)
        try:
            if s20 is not None and float(close.iloc[-1]) >= s20:
                above += 1
        except Exception:  # noqa: BLE001
            pass
    if used == 0:
        return None, None, 0
    return round(beat / used, 4), round(above / used, 4), used


def _window_returns(close) -> dict:
    """{window: percent return} for a Close Series over the full window set."""
    return {w: _pct_return(close, n) for w, n in THEME_WINDOW_DAYS.items()}


def _theme_benchmark(cfg: dict) -> str:
    return str(cfg.get("benchmark") or THEME_BENCHMARK_DEFAULT).upper()


def _fixture_result(theme_key: str, cfg: dict) -> ThemeMomentumResult:
    """Build a fail-closed fixture result for one theme."""
    r1, r3, r6 = _FIXTURE_RETURNS.get(theme_key, (None, None, None))
    return ThemeMomentumResult(
        theme_key=theme_key,
        label_en=cfg["label_en"],
        label_zh=cfg["label_zh"],
        constituents=list(cfg["constituents"]),
        etf=cfg["etf"],
        return_1m=r1,
        return_3m=r3,
        return_6m=r6,
        momentum_score=0.0,
        data_source="fixture",
        n_constituents_used=0,
    )


# ── Public: per-theme momentum ────────────────────────────────────────────────

def _enrich_excess_stage_breadth(result: ThemeMomentumResult, cfg: dict,
                                 theme_win: dict, bench_win: dict,
                                 loader, active_window: str) -> None:
    """Fill the Phase 7B excess / stage / breadth fields on ``result`` in place.

    ``theme_win`` / ``bench_win`` are ``{window: percent return}``. Excess is the
    theme's window return minus the benchmark's (pp). The divergence stage comes
    from 5D vs 1M excess; breadth is computed over the constituents for the active
    window. Confirmation is direction-aware (a bullish stage needs broad
    participation; a bearish stage needs broad weakness) — the single-stock guard."""
    excess = {}
    for w in THEME_WINDOW_DAYS:
        tv, bv = theme_win.get(w), bench_win.get(w)
        excess[w] = (round(tv - bv, 2)
                     if isinstance(tv, (int, float)) and isinstance(bv, (int, float))
                     else None)
    result.excess = excess
    result.excess_5d = excess.get("5d")
    result.excess_1m = excess.get("1m")
    result.excess_3m = excess.get("3m")
    result.stage = classify_divergence(excess.get("5d"), excess.get("1m"))
    result.active_window = active_window

    constituent_closes = {}
    for tk in cfg["constituents"]:
        try:
            constituent_closes[tk] = loader(tk)
        except Exception:  # noqa: BLE001 - fail-closed per ticker
            constituent_closes[tk] = None

    # Per-constituent EXCESS vs benchmark for "1m", "3m", and the active window.
    # Reuses the constituent_closes already loaded above — NO new fetch. None
    # values are filtered out, so only present windows carry a float.
    _const_rs: dict = {}
    for _tk, _close in constituent_closes.items():
        if _close is None:
            continue
        _ticker_excess: dict = {}
        for _w in ("1m", "3m"):
            _days = THEME_WINDOW_DAYS.get(_w)
            _bench = bench_win.get(_w)
            if _days is not None and _bench is not None:
                _raw = _pct_return(_close, _days)
                if _raw is not None:
                    _ticker_excess[_w] = round(_raw - _bench, 4)
        # Active window stored under its own "active" key (may duplicate the
        # value of "1m"/"3m" when active_window matches — kept separate by design).
        _a_days = THEME_WINDOW_DAYS.get(active_window)
        _a_bench = bench_win.get(active_window)
        if _a_days is not None and _a_bench is not None:
            _a_raw = _pct_return(_close, _a_days)
            if _a_raw is not None:
                _ticker_excess["active"] = round(_a_raw - _a_bench, 4)
        if _ticker_excess:
            _const_rs[_tk] = _ticker_excess
    result.constituent_rs = _const_rs

    beat, above, n = compute_theme_breadth(
        constituent_closes, bench_win.get(active_window), active_window)
    result.breadth_beat_pct = beat
    result.breadth_above_sma20_pct = above
    result.n_constituents_breadth = n

    if beat is None or not result.stage:
        result.stage_confirmed = False
    elif result.stage in (STAGE_ROTATING_IN, STAGE_LEADING):
        result.stage_confirmed = beat >= BREADTH_CONFIRM_FRACTION
    else:  # rotating_out / out_of_favor — confirmed weakness is broad weakness
        result.stage_confirmed = beat <= (1.0 - BREADTH_CONFIRM_FRACTION)


def compute_theme_momentum(theme_key: str, period: str = "3mo", *,
                           bench_returns_map: Optional[dict] = None,
                           close_loader=None,
                           active_window: str = "1m") -> ThemeMomentumResult:
    """Compute multi-window momentum + EXCESS vs benchmark for a single theme.

    * ETF themes      -> returns derived from the ETF price series (data_source="etf").
    * ETF-less themes -> equal-weight average of constituent returns
                         (data_source="equal_weight").
    * Any failure     -> deterministic fixture fallback (data_source="fixture").

    Phase 7B Task 2: when ``bench_returns_map`` (``{benchmark: {window: pct}}``) is
    supplied — by :func:`compute_all_themes`, which fetches each benchmark once —
    the EXCESS-vs-benchmark window set, the divergence stage label, and the
    group-confirmation breadth are filled in. ``close_loader(ticker)->Close
    Series`` is injectable (mock tests + the network-free path); it defaults to the
    yfinance reader. ``momentum_score`` is left at 0.0 here; compute_all_themes()
    fills it with the cross-theme EXCESS-3M percentile rank. Always fail-closed.
    """
    cfg = THEME_BASKETS.get(theme_key)
    if cfg is None:
        # Unknown key -> safe empty result rather than raising.
        return ThemeMomentumResult(
            theme_key=theme_key,
            label_en=theme_key,
            label_zh=theme_key,
            constituents=[],
            etf=None,
            data_source="fixture",
        )

    loader = close_loader or _history_close
    bench_sym = _theme_benchmark(cfg)
    try:
        etf = cfg.get("etf")
        if etf:
            # ── ETF-backed theme ─────────────────────────────────────────────
            close = loader(etf)
            if close is None:
                return _fixture_result(theme_key, cfg)
            theme_win = _window_returns(close)
            result = ThemeMomentumResult(
                theme_key=theme_key,
                label_en=cfg["label_en"],
                label_zh=cfg["label_zh"],
                constituents=list(cfg["constituents"]),
                etf=etf,
                return_1m=theme_win.get("1m"),
                return_3m=theme_win.get("3m"),
                return_6m=theme_win.get("6m"),
                momentum_score=0.0,
                data_source="etf",
                n_constituents_used=0,
                benchmark=bench_sym,
            )
        else:
            # ── ETF-less theme: equal-weight average across constituents ─────
            per_window: dict = {w: [] for w in THEME_WINDOW_DAYS}
            used = 0
            for tk in cfg["constituents"]:
                c = loader(tk)
                if c is None:
                    continue
                used += 1
                wr = _window_returns(c)
                for w in THEME_WINDOW_DAYS:
                    if wr.get(w) is not None:
                        per_window[w].append(wr[w])
            if used == 0:
                return _fixture_result(theme_key, cfg)
            theme_win = {w: (round(sum(v) / len(v), 2) if v else None)
                         for w, v in per_window.items()}
            result = ThemeMomentumResult(
                theme_key=theme_key,
                label_en=cfg["label_en"],
                label_zh=cfg["label_zh"],
                constituents=list(cfg["constituents"]),
                etf=None,
                return_1m=theme_win.get("1m"),
                return_3m=theme_win.get("3m"),
                return_6m=theme_win.get("6m"),
                momentum_score=0.0,
                data_source="equal_weight",
                n_constituents_used=used,
                benchmark=bench_sym,
            )

        if bench_returns_map is not None:
            _enrich_excess_stage_breadth(
                result, cfg, theme_win,
                bench_returns_map.get(bench_sym, {}) or {},
                loader, active_window)
        return result

    except Exception:  # noqa: BLE001 - fail-closed
        return _fixture_result(theme_key, cfg)


# ── Percentile rank helper ────────────────────────────────────────────────────

def _percentile_rank(value: Optional[float], all_values: list[Optional[float]]) -> float:
    """Rank-based percentile of `value` within `all_values`, scaled 0.0-1.0.

    The lowest valid 3M return maps to 0.0, the highest to 1.0. None values (and
    a value of None) map to 0.0. Ties share the lower rank. Always in [0, 1].
    """
    vals = sorted(v for v in all_values if isinstance(v, (int, float)))
    if value is None or not vals:
        return 0.0
    if len(vals) == 1:
        return 1.0
    # Number of values strictly less than `value`.
    rank = sum(1 for v in vals if v < value)
    return round(rank / (len(vals) - 1), 4)


# ── Public: all themes (cached) ───────────────────────────────────────────────

def _benchmark_returns_map(close_loader) -> dict:
    """Fetch each distinct theme benchmark ONCE → ``{sym: {window: pct}}``."""
    syms = {_theme_benchmark(cfg) for cfg in THEME_BASKETS.values()}
    out: dict = {}
    for sym in syms:
        try:
            close = close_loader(sym)
        except Exception:  # noqa: BLE001
            close = None
        out[sym] = _window_returns(close) if close is not None else {}
    return out


@st.cache_data(ttl=1800, show_spinner=False)
def compute_all_themes(period: str = "3mo",
                       regime: str = "unknown") -> list[ThemeMomentumResult]:
    """Compute multi-window EXCESS momentum for every theme, assign the EXCESS-3M
    percentile momentum score + divergence stage + breadth, and return the list
    sorted by momentum_score descending.

    ``regime`` selects the macro LENS (default active window): risk_off/transition
    emphasize the 5D window, risk_on the 1M — a pure display/default choice that
    never re-ranks the themes. Cached for 30 minutes. Always fail-closed: a
    per-theme failure degrades to that theme's fixture result.
    """
    active_window = MACRO_LENS_WINDOW.get(str(regime or "unknown"), "1m")
    bench_map = _benchmark_returns_map(_history_close)

    results: list[ThemeMomentumResult] = []
    for key in THEME_BASKETS:
        try:
            results.append(compute_theme_momentum(
                key, period, bench_returns_map=bench_map,
                active_window=active_window))
        except Exception:  # noqa: BLE001 - fail-closed per theme
            results.append(_fixture_result(key, THEME_BASKETS[key]))

    # Momentum score = cross-theme percentile of EXCESS-3M return (Phase 7B).
    excess_3m = [r.excess_3m for r in results]
    for r in results:
        r.momentum_score = _percentile_rank(r.excess_3m, excess_3m)

    results.sort(key=lambda r: r.momentum_score, reverse=True)
    return results


# ── Scanner hand-off helpers (review-only; no execution) ──────────────────────
# These write the theme universe into Streamlit session_state for a *future*
# Scanner universe integration. They never place orders and never set any
# execution flag — they only stage tickers for research screening.

def send_top_theme_to_scanner(results: list[ThemeMomentumResult],
                              session_state, lang: str = "en") -> Optional[ThemeMomentumResult]:
    """Write the top-momentum theme's constituents to the Scanner hand-off keys.

    Sets session_state["theme_universe"] (deduped constituent list) and
    session_state["theme_universe_label"]. Returns the chosen theme, or None if
    there are no results. `session_state` may be any mapping (real
    st.session_state or a plain dict in tests).
    """
    if not results:
        return None
    top = results[0]
    seen: list[str] = []
    for tk in top.constituents:
        if tk not in seen:
            seen.append(tk)
    session_state["theme_universe"] = seen
    session_state["theme_universe_label"] = top.label_zh if lang == "zh" else top.label_en
    return top


def send_all_themes_to_scanner(results: list[ThemeMomentumResult],
                               session_state, lang: str = "en") -> list[str]:
    """Write the deduplicated union of all theme constituents to the Scanner
    hand-off keys. Returns the unique ticker list.
    """
    seen: list[str] = []
    for r in results:
        for tk in r.constituents:
            if tk not in seen:
                seen.append(tk)
    session_state["theme_universe"] = seen
    session_state["theme_universe_label"] = (
        "全部主题成分股" if lang == "zh" else "All theme constituents"
    )
    return seen
