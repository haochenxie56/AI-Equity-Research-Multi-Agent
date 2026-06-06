"""lib/candidate_generator.py — Phase 6B v2 Dual-Track candidate generation.

This module builds the ticker **universe** and runs the Phase 6B v2 **dual-track**
signal pipeline (``lib.signal_engine``) over it to surface review-only candidate
opportunities for the Scanner — automatically, without a manually-entered pool.

Pipeline (orchestrated by :func:`generate_candidates`):

1. **Layer 1 — hard filter** (:func:`run_layer1_filter`): keep only tickers that
   clear the market-cap floor / catastrophic-price-break / data-availability
   gate. Low RSI / low momentum / far-from-52W-high are NOT filtered.
2. **Layer 2 — LLM narrative matching** (:func:`run_layer2_narrative`): the top
   ``llm_n`` Layer 1 survivors (ranked by a lightweight quality pre-score) get one
   LLM narrative call each; the rest get a neutral narrative.
3. **Layer 3 — fundamental validation** (:func:`run_layer3_fundamental`): EPS
   revision / valuation / margin trend / universe-normalized quality.
4. **Track B — alternative signals** (:func:`run_track_b`): insider / unusual
   news / analyst revision, run on the FULL universe independent of the funnel.
5. **Combine + rank**: FUNNEL/BOTH candidates first (by composite desc), then
   ALT_SIGNAL-only candidates (Track B standalone triggers) appended after.

Design rules (Phase 6B guardrails):

* **Free sources only.** Scoring uses only the free signal engine. No paid API,
  no DB, no vector store.
* **Fail-closed.** Universe construction and every stage degrade gracefully (a
  failed ticker is dropped; an unavailable ``research_state`` is ignored). Nothing
  raises to the page.
* **Review-only.** Output is a ranked list of :class:`TickerSignalResult`. No
  broker / order / execution capability, no ``approved_for_execution`` field, no
  buy/sell instruction.
* **Cached.** :func:`generate_candidates` is memoized with ``st.cache_data``
  (TTL=1800 s) keyed on ``(macro_regime, top_n, llm_n)``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import streamlit as st

from lib.theme_baskets import THEME_BASKETS
from lib.signal_engine import (
    CandidateSignal,
    TickerSignalResult,
    build_candidate_signal,
    build_ticker_result,  # noqa: F401 — re-exported for v2-compat consumers/tests
    compute_composite,
    compute_entry_quality,
    compute_track_b,
    fetch_fundamental,
    llm_narrative_match,
    neutral_narrative,
    normalize_quality_composite,
    passes_layer1,
    quality_pre_score,
    score_ticker,  # noqa: F401 — re-exported for v1-compat consumers/tests
    _technical_snapshot,
)

# Bounded parallelism for per-ticker fetches within a stage (Finnhub free tier
# 60 RPM is respected via the signal engine's TTL=1800 caching).
_MAX_WORKERS = 8  # ThreadPoolExecutor(max_workers=8)

# ---------------------------------------------------------------------------
# Static universe
# ---------------------------------------------------------------------------

# S&P 500 — top ~100 constituents by market capitalization.
#
# Source: author's manual snapshot of the largest S&P 500 members by market cap
# (per slickcharts.com / S&P 500 weightings), captured 2026-05. Hardcoded,
# manually-maintained reference list — NOT a live index feed. It anchors the
# candidate universe so the Scanner can generate candidates without a manual
# pool. (Note: MU is intentionally included so a cycle-bottom semiconductor name
# can be surfaced by the dual-track pipeline.)
SP500_TOP_100 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "BRK-B", "AVGO",
    "TSLA", "LLY", "JPM", "V", "XOM", "UNH", "MA", "COST", "HD", "PG", "JNJ",
    "WMT", "NFLX", "ABBV", "ORCL", "BAC", "CRM", "CVX", "KO", "AMD", "PEP",
    "TMO", "LIN", "ADBE", "MRK", "WFC", "CSCO", "ACN", "MCD", "ABT", "GE",
    "DHR", "IBM", "AXP", "QCOM", "NOW", "TXN", "PM", "CAT", "ISRG", "VZ",
    "INTU", "DIS", "RTX", "AMGN", "SPGI", "PFE", "GS", "CMCSA", "UNP", "T",
    "LOW", "AMAT", "NEE", "HON", "BKNG", "PGR", "ELV", "BLK", "SYK", "COP",
    "VRTX", "TJX", "C", "BSX", "ADP", "MS", "MDT", "GILD", "SCHW", "LMT",
    "DE", "BMY", "ADI", "MMC", "CB", "PLD", "SBUX", "AMT", "MO", "FISV",
    "REGN", "PANW", "ETN", "KLAC", "LRCX", "MU", "SO", "DUK", "INTC", "ICE",
]
# Note: Fiserv is listed as ``FISV`` (not its current NYSE ticker ``FI``) because
# the yfinance/Yahoo data backend only resolves Fiserv under the legacy ``FISV``
# symbol; ``FI`` returns a 404 and is dropped at Layer 1 as missing-fundamentals.

# Hard cap on the combined universe size (Phase 6B contract).
_UNIVERSE_CAP = 150


def get_universe() -> list:
    """Return the combined, deduplicated, capped (<=150) ticker universe.

    Combines the hardcoded :data:`SP500_TOP_100` with the currently-selected
    subsector constituents from ``st.session_state.research_state`` when available
    (read defensively, ignored if absent). Deduplicates (S&P names first) and caps
    at 150. Always returns a ``list[str]``.
    """
    universe: list[str] = []
    seen: set[str] = set()

    def _add(sym) -> None:
        if not isinstance(sym, str):
            return
        s = sym.upper().strip()
        if s and s not in seen:
            seen.add(s)
            universe.append(s)

    for sym in SP500_TOP_100:
        _add(sym)

    try:
        research_state = st.session_state.get("research_state", {}) or {}
        results = research_state.get("results", {}) or {}
        sector_res = results.get("sector", {}) or {}
        for key in ("constituents", "subsector_constituents", "tickers"):
            vals = sector_res.get(key)
            if isinstance(vals, (list, tuple)):
                for v in vals:
                    if isinstance(v, str):
                        _add(v)
                    elif isinstance(v, dict) and v.get("ticker"):
                        _add(v.get("ticker"))
        scan_res = results.get("scan", {}) or {}
        pool = scan_res.get("pool")
        if isinstance(pool, str):
            for v in pool.replace("\n", ",").split(","):
                _add(v)
        elif isinstance(pool, (list, tuple)):
            for v in pool:
                _add(v)
    except Exception:  # noqa: BLE001 — research_state absent / unexpected shape
        pass

    return universe[:_UNIVERSE_CAP]


# ---------------------------------------------------------------------------
# Configurable universe construction (Phase 6B v2 — theme-aware)
# ---------------------------------------------------------------------------


@dataclass
class UniverseConfig:
    """Declarative description of how to assemble the candidate universe.

    Combines the hardcoded S&P 500 top-100 anchor, any selected cross-GICS theme
    baskets (keys from :data:`lib.theme_baskets.THEME_BASKETS`), manually-entered
    tickers, the Sector Research "Send to Scanner" hand-off
    (``st.session_state["theme_universe"]``), and any ``research_state`` subsector
    constituents — deduplicated and capped at :attr:`max_size`. Review-only: this
    config never carries an execution flag and never places an order.
    """

    include_sp500_top100: bool = True
    selected_themes: list = field(default_factory=list)
    manual_tickers: list = field(default_factory=list)
    max_size: int = 150


def build_universe(config: "UniverseConfig") -> list:
    """Assemble the deduplicated, capped ticker universe described by ``config``.

    Source order (all fail-closed; deduplicated, first occurrence wins):

    1. :data:`SP500_TOP_100` (when ``config.include_sp500_top100``).
    2. Constituents of each selected theme in ``config.selected_themes``.
    3. ``st.session_state["theme_universe"]`` if set by the Sector Research
       "Send to Scanner" hand-off.
    4. ``config.manual_tickers``.
    5. ``research_state`` subsector constituents when available.

    The result is capped at ``config.max_size`` (falls back to the hard
    :data:`_UNIVERSE_CAP` if ``max_size`` is not a positive int). Always returns
    a ``list[str]``; never raises.
    """
    universe: list = []
    seen: set = set()

    def _add(sym) -> None:
        if not isinstance(sym, str):
            return
        s = sym.upper().strip()
        if s and s not in seen:
            seen.add(s)
            universe.append(s)

    # 1. S&P 500 top-100 anchor.
    if getattr(config, "include_sp500_top100", True):
        for sym in SP500_TOP_100:
            _add(sym)

    # 2. Selected theme-basket constituents.
    for theme_key in (getattr(config, "selected_themes", None) or []):
        cfg = THEME_BASKETS.get(theme_key)
        if not cfg:
            continue
        for sym in (cfg.get("constituents") or []):
            _add(sym)

    # 3. Sector Research "Send to Scanner" hand-off (session_state).
    try:
        theme_universe = st.session_state.get("theme_universe", []) or []
        if isinstance(theme_universe, (list, tuple)):
            for sym in theme_universe:
                _add(sym)
    except Exception:  # noqa: BLE001 — no Streamlit runtime / unexpected shape
        pass

    # 4. Manually-entered tickers.
    for sym in (getattr(config, "manual_tickers", None) or []):
        _add(sym)

    # 5. research_state subsector constituents (read defensively).
    try:
        research_state = st.session_state.get("research_state", {}) or {}
        results = research_state.get("results", {}) or {}
        sector_res = results.get("sector", {}) or {}
        for key in ("constituents", "subsector_constituents", "tickers"):
            vals = sector_res.get(key)
            if isinstance(vals, (list, tuple)):
                for v in vals:
                    if isinstance(v, str):
                        _add(v)
                    elif isinstance(v, dict) and v.get("ticker"):
                        _add(v.get("ticker"))
    except Exception:  # noqa: BLE001 — research_state absent / unexpected shape
        pass

    cap = config.max_size if isinstance(config.max_size, int) and config.max_size > 0 else _UNIVERSE_CAP
    return universe[:cap]


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------


def _map_parallel(fn, items: list) -> dict:
    """Run ``fn(item) -> value`` over ``items`` with a bounded thread pool.

    Returns ``{item: value}``; a per-item failure maps to ``None`` (caller filters).
    """
    out: dict = {}
    if not items:
        return out
    try:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {pool.submit(fn, it): it for it in items}
            for fut, it in futures.items():
                try:
                    out[it] = fut.result()
                except Exception:  # noqa: BLE001 — drop the failed item
                    out[it] = None
    except Exception:  # noqa: BLE001 — pool failure -> sequential fallback
        for it in items:
            try:
                out[it] = fn(it)
            except Exception:  # noqa: BLE001
                out[it] = None
    return out


def run_layer1_filter(universe: list) -> list:
    """Track A Layer 1 — return the subset of ``universe`` passing the hard filter.

    Excludes only on market cap / catastrophic price break / missing
    fundamentals. NEVER excludes on low RSI / momentum / 52W distance / ADX.
    """
    verdicts = _map_parallel(lambda t: passes_layer1(t), list(universe or []))
    passed = []
    for t in universe or []:
        v = verdicts.get(t)
        if isinstance(v, tuple) and v and v[0]:
            passed.append(t)
    return passed


def run_layer2_narrative(filtered: list, macro_regime: str, llm_n: int) -> dict:
    """Track A Layer 2 — narrative match for the top ``llm_n`` survivors.

    Survivors are ranked by a lightweight quality pre-score (descending); the top
    ``llm_n`` get one LLM narrative call each, the rest get a neutral narrative.
    Returns ``{ticker: NarrativeResult}``. Fail-closed throughout.
    """
    filtered = list(filtered or [])
    if not filtered:
        return {}
    try:
        llm_n = max(0, int(llm_n))
    except (TypeError, ValueError):
        llm_n = 50

    pre = _map_parallel(quality_pre_score, filtered)
    ranked = sorted(filtered, key=lambda t: (pre.get(t) or 0.0), reverse=True)
    top = ranked[:llm_n]
    rest = ranked[llm_n:]

    narratives: dict = {}
    llm_results = _map_parallel(lambda t: llm_narrative_match(t, macro_regime), top)
    for t in top:
        res = llm_results.get(t)
        narratives[t] = res if res is not None else neutral_narrative()
    for t in rest:
        narratives[t] = neutral_narrative()
    return narratives


def run_layer3_fundamental(filtered: list) -> dict:
    """Track A Layer 3 — fundamental validation with universe-normalized quality.

    Returns ``{ticker: FundamentalResult}``. ``quality_composite`` is normalized
    cross-sectionally across the filtered set. Fail-closed throughout.
    """
    filtered = list(filtered or [])
    raw = _map_parallel(fetch_fundamental, filtered)
    fundamentals = {t: r for t, r in raw.items() if r is not None}
    normalize_quality_composite(fundamentals)
    return fundamentals


def run_track_b(universe: list, macro_regime: str) -> dict:
    """Track B — alternative-data signals over the FULL universe (no Layer 1).

    Returns ``{ticker: TrackBResult}``. Fail-closed throughout.
    """
    raw = _map_parallel(lambda t: compute_track_b(t), list(universe or []))
    return {t: r for t, r in raw.items() if r is not None}


# ---------------------------------------------------------------------------
# Full dual-track pipeline
# ---------------------------------------------------------------------------


def _progress(bar, frac: float, text: str) -> None:
    if bar is None:
        return
    try:
        bar.progress(frac, text=text)
    except Exception:  # noqa: BLE001
        pass


# Signal-strength ordering: triple first, then double, single, none.
_STRENGTH_RANK = {"triple": 3, "double": 2, "single": 1, "none": 0}


def _strength_rank(signal_strength: str) -> int:
    """Sort rank for a signal_strength label (higher = stronger)."""
    return _STRENGTH_RANK.get(signal_strength, 0)


def _horizon_avg(c: "CandidateSignal") -> float:
    """Average of (short + mid + long) / 3 for a CandidateSignal (sort key)."""
    try:
        return (float(c.short_score) + float(c.mid_score) + float(c.long_score)) / 3.0
    except Exception:  # noqa: BLE001
        return 0.0


@st.cache_data(ttl=1800, show_spinner=False)
def _generate_candidates_cached(macro_regime: str, top_n: int, llm_n: int,
                                universe: tuple = (), lang: str = "en") -> list:
    """Cached dual-track candidate generation, keyed on
    ``(macro_regime, top_n, llm_n, universe, lang)`` — so each regime / depth /
    universe / language configuration caches separately. ``universe`` is a
    hashable tuple of tickers (built by :func:`build_universe` /
    :func:`get_universe`). ``lang`` localizes the display fields (zh) of each
    :class:`CandidateSignal`.
    """
    universe = list(universe or [])
    if not universe:
        return []

    try:
        bar = st.progress(0.0, text="Starting...")
    except Exception:  # noqa: BLE001 — no Streamlit runtime (offline test)
        bar = None

    try:
        _progress(bar, 0.05, "Layer 1: filtering universe...")
        filtered = run_layer1_filter(universe)
        filtered_set = set(filtered)

        try:
            _llm_count = min(len(filtered), int(llm_n))
        except (TypeError, ValueError):
            _llm_count = len(filtered)
        _progress(bar, 0.25, f"Layer 2: LLM narrative matching ({_llm_count} tickers)...")
        narratives = run_layer2_narrative(filtered, macro_regime, llm_n)

        _progress(bar, 0.55, "Layer 3: fundamental validation...")
        fundamentals = run_layer3_fundamental(filtered)

        _progress(bar, 0.75, "Track B: alternative signals...")
        track_b_all = run_track_b(universe, macro_regime)

        _progress(bar, 0.9, "Combining and ranking...")
        # Per-ticker technical snapshots (entry quality) for Layer 1 survivors.
        snaps = _map_parallel(_technical_snapshot, filtered)

        funnel: list[CandidateSignal] = []
        for t in filtered:
            try:
                fundamental = fundamentals.get(t)
                if fundamental is None:
                    continue
                narrative = narratives.get(t) or neutral_narrative()
                snap = snaps.get(t) or {}
                entry = compute_entry_quality(t, snap)
                track_b = track_b_all.get(t) or compute_track_b(t, 0.0, 0.0, 0.0)
                funnel.append(
                    build_candidate_signal(
                        t, fundamental, narrative, entry, track_b, snap,
                        macro_regime, layer1_passed=True, lang=lang,
                    )
                )
            except Exception:  # noqa: BLE001 — drop the failed ticker
                continue

        # ALT_SIGNAL-only: tickers that did NOT pass the funnel but whose Track B
        # composite standalone-triggered (>= 0.7). These still get short/mid/long
        # horizon scores computed normally (from neutral fundamentals/narrative).
        alt: list[CandidateSignal] = []
        for t in universe:
            if t in filtered_set:
                continue
            tb = track_b_all.get(t)
            if tb is None or not tb.is_standalone_trigger:
                continue
            try:
                from lib.signal_engine import FundamentalResult, EntryQualityResult
                alt.append(
                    build_candidate_signal(
                        t, FundamentalResult(), neutral_narrative(),
                        EntryQualityResult(), tb, {}, macro_regime,
                        layer1_passed=False, lang=lang,
                    )
                )
            except Exception:  # noqa: BLE001 — drop the failed ticker
                continue

        # Cap the funnel at top_n by horizon-average, then append all ALT_SIGNAL.
        funnel.sort(key=_horizon_avg, reverse=True)
        funnel = funnel[: max(0, int(top_n))]
        combined = funnel + alt
        # Final ordering: triple first, then double, single, none; within each
        # signal_strength group by the average of (short+mid+long)/3 descending.
        combined.sort(key=lambda c: (_strength_rank(c.signal_strength), _horizon_avg(c)),
                      reverse=True)
        return combined
    finally:
        if bar is not None:
            try:
                bar.empty()
            except Exception:  # noqa: BLE001
                pass


def generate_candidates(macro_regime: str, top_n: int = 20, llm_n: int = 50,
                        config: "Optional[UniverseConfig]" = None,
                        lang: str = "en") -> list:
    """Run the full dual-track pipeline and return ranked candidates.

    ``macro_regime`` is normalized (stripped + lowercased; empty -> "unknown") so
    the cache key is well-defined; ``llm_n`` (default 50, clamped to 10–100) sets
    how many Layer 1 survivors get an LLM narrative call. ``config`` selects the
    universe: when provided, the universe is assembled by :func:`build_universe`
    (S&P 500 anchor + selected themes + ``theme_universe`` hand-off + manual
    tickers + ``research_state``); when ``None``, the legacy :func:`get_universe`
    is used. The assembled universe (a hashable tuple) is part of the cache key,
    so each universe configuration caches separately. Returns a combined list
    sorted by ``composite_score`` descending, with ALT_SIGNAL-only candidates
    appended after the FUNNEL/BOTH candidates. Cached TTL=1800 keyed on
    ``(macro_regime, top_n, llm_n, universe, lang)``. ``lang`` (``"en"`` |
    ``"zh"``) localizes the DISPLAY fields (catalyst summary, theme-tag labels,
    key signals) of each :class:`CandidateSignal` (the English LLM prompt/response
    are unchanged). Fail-closed: never raises to the page; output is review-only
    (no execution, no order side effects).
    """
    regime_key = (macro_regime or "unknown").strip().lower() or "unknown"
    try:
        llm_n = int(llm_n)
    except (TypeError, ValueError):
        llm_n = 50
    llm_n = max(10, min(100, llm_n))
    lang = lang if lang in ("en", "zh") else "en"
    try:
        universe = build_universe(config) if config is not None else get_universe()
    except Exception:  # noqa: BLE001 — fail-closed universe construction
        universe = get_universe()
    results = _generate_candidates_cached(regime_key, top_n, llm_n,
                                          tuple(universe), lang)
    _publish_cockpit_signals(results)
    _publish_scan_universe(universe)
    return results


def _publish_scan_universe(universe: list) -> None:
    """Stage the EXACT scan universe used THIS refresh so the Cockpit's market-
    internals earnings scope (good-news-sold) runs over the scanned set (~100-150
    names), not the ranked top-N. Publishing the object the generator actually used
    avoids a re-derived list that could drift from this refresh. Fail-closed."""
    try:
        st.session_state["cockpit_scan_universe"] = [
            str(t).upper().strip() for t in (universe or []) if str(t).strip()
        ]
    except Exception:  # noqa: BLE001 — no Streamlit runtime / unexpected shape
        pass


def _candidate_handoff_dict(c: "CandidateSignal", signal_strength: str) -> dict:
    """Shape one CandidateSignal as the review-only Cockpit hand-off record."""
    return {
        "ticker": c.ticker,
        "short_score": c.short_score,
        "mid_score": c.mid_score,
        "long_score": c.long_score,
        "catalyst_summary": c.catalyst_summary,
        "key_signals": c.key_signals,
        "signal_strength": signal_strength,
        "timestamp": datetime.utcnow().isoformat(),
    }


def _publish_cockpit_signals(results: list) -> None:
    """Stage the triple-hit and all-candidate hand-off lists for a FUTURE Cockpit
    integration (review-only; no execution, no persistence).

    Writes ``st.session_state["cockpit_triple_signals"]`` (triple hits only) and
    ``st.session_state["cockpit_all_signals"]`` (every candidate). Fail-closed:
    a missing/unavailable Streamlit session never raises to the page.
    """
    try:
        results = results or []
        st.session_state["cockpit_triple_signals"] = [
            _candidate_handoff_dict(c, "triple")
            for c in results if getattr(c, "signal_strength", "none") == "triple"
        ]
        st.session_state["cockpit_all_signals"] = [
            _candidate_handoff_dict(c, getattr(c, "signal_strength", "none"))
            for c in results
        ]
    except Exception:  # noqa: BLE001 — no Streamlit runtime / unexpected shape
        pass
