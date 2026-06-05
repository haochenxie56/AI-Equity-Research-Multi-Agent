"""Page 7 — Investment Cockpit (Phase 6C-B — live data aggregation hub).

The Investment Cockpit is the PRIMARY entry point of the app and a live data
aggregation hub. A single "Refresh All" button pulls macro regime, market-theme
momentum, and signal candidates, then values any selected tickers — surfacing
everything in one place so the user can decide what to research and trade.

Sections:
    A — Macro Regime Summary    (st.session_state["macro_regime_result"])
    B — Market Themes Summary   (st.session_state["theme_momentum_results"])
    C — Signal Candidates       (st.session_state["cockpit_all_signals"]) + selection
    D — Equity Research Results (st.session_state["equity_research_results"])
    E — Triple Signal Watch     (st.session_state["cockpit_triple_signals"])

Guardrails (Phase 6C-B): free sources only (yfinance / FRED / Finnhub free tier
via the existing fetchers); no paid API; no broker / order / execution; no order
ticket / broker payload; ``approved_for_execution`` is never set True; no DB /
vector store / persistence beyond ``st.session_state``. The one-click refresh is
fully fail-closed: a failure in any one step never aborts the others. The
Trading Desk thesis monitor is NOT run here — it runs on the Trading Desk page
as before. Review-only; not investment advice.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "lib"))

import streamlit as st

from ui_utils import apply_theme, render_sidebar, load_info, t
# Phase 6C-B — single macro-regime session-state boundary (stores a plain dict;
# reads via dict .get()). lib/macro_regime.py stays frozen.
from lib.macro_state import (
    save_regime_to_state, get_regime_field, get_regime_str, get_regime_dict,
)

st.set_page_config(page_title="Investment Cockpit", page_icon="🧭", layout="wide")
apply_theme()
render_sidebar()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _regime_str() -> str:
    """The current macro regime as a string (fail-closed -> 'unknown')."""
    return get_regime_str("unknown")


def _badge(text: str, color: str) -> str:
    return (
        f'<span style="display:inline-block;padding:2px 9px;border-radius:10px;'
        f'background:{color}22;color:{color};border:1px solid {color}55;'
        f'font-size:0.72rem;font-weight:600;">{text}</span>'
    )


_STRENGTH_COLOR = {"triple": "#d4a017", "double": "#3fb950",
                   "single": "#388bfd", "none": "#8b949e"}
_REGIME_COLOR = {"risk_on": "#3fb950", "risk_off": "#f85149",
                 "transition": "#d29922", "degraded": "#8b949e", "unknown": "#8b949e"}

# Phase 7A — Opportunity Card display maps (status/setup/grade -> labels/colors).
_GRADE_COLOR = {"A": "#3fb950", "B": "#d29922", "C": "#8b949e"}
_SETUP_KEY = {
    "Momentum Breakout": "opp_setup_momentum_breakout",
    "Mid-term Rotation": "opp_setup_mid_rotation",
    "Oversold Rebound": "opp_setup_oversold_rebound",
    "Post-earnings Reprice": "opp_setup_post_earnings",
    "Long-term Accumulation": "opp_setup_long_accum",
    "Speculative Watch": "opp_setup_speculative",
}
_STATUS_KEY = {
    "Actionable Now": "opp_status_actionable",
    "Wait for Pullback": "opp_status_pullback",
    "Wait for Breakout": "opp_status_breakout",
    "Research Required": "opp_status_research",
    "Avoid Chasing": "opp_status_avoid",
}
_STATUS_COLOR = {
    "Actionable Now": "#3fb950", "Wait for Pullback": "#d29922",
    "Wait for Breakout": "#388bfd", "Research Required": "#8b949e",
    "Avoid Chasing": "#f85149",
}
# Phase 7A fix round — display-time helpers from the ranker (banner, concentration).
from lib.opportunity_ranker import (
    market_banner_blockers as _market_banner_blockers,
    concentration_refs as _concentration_refs,
    MARKET_WIDE_BLOCKER_CODES as _MARKET_WIDE_CODES,
)


def _current_price(ticker: str) -> float:
    """Best-effort current price via the cached info loader (fail-closed -> 0.0)."""
    try:
        info = load_info(ticker) or {}
        cp = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        return float(cp) if cp else 0.0
    except Exception:  # noqa: BLE001 — fail-closed
        return 0.0


def _macro_zh(signals: list, posture: str) -> tuple:
    """Translate macro key_signals + opportunity_posture to Chinese (cached).

    classify_regime emits English-only key_signals / opportunity_posture; this
    translates them via deep-translator for the ZH surface (fail-closed -> the
    English originals). Result is cached in session_state keyed on the English
    text so we do not re-translate on every rerun.
    """
    try:
        from lib.translator import translate_str_list

        key = ("|".join(signals or []), posture or "")
        cache = st.session_state.get("_macro_zh_cache", {})
        if cache.get("key") == key:
            return cache["signals"], cache["posture"]
        sig_zh = translate_str_list(list(signals), "en")["zh"] if signals else signals
        pos_zh = translate_str_list([posture], "en")["zh"][0] if posture else posture
        st.session_state["_macro_zh_cache"] = {
            "key": key, "signals": sig_zh, "posture": pos_zh}
        return sig_zh, pos_zh
    except Exception:  # noqa: BLE001 — fail-closed to English
        return signals, posture


def _add_to_trading_desk(card: dict, base: dict | None = None) -> bool:
    """Stage an opportunity card (any strength) for the Trading Desk Opportunity
    Watch via ``st.session_state["td_pending_signals"]`` (deduped by ticker).

    Phase 7A carries the new ranker fields (setup / status / blockers / grades /
    days_to_earnings) alongside the legacy fields so Section 3 can display them.
    ``base`` is the matching ``cockpit_all_signals`` hand-off dict (source of
    catalyst_summary / key_signals, which the card does not carry)."""
    tk = str(card.get("ticker", "")).upper().strip()
    if not tk:
        return False
    base = base or {}
    rec = {
        "ticker": tk,
        "signal_strength": card.get("signal_strength", base.get("signal_strength", "none")),
        "short_score": card.get("short_score", base.get("short_score", 0.0)),
        "mid_score": card.get("mid_score", base.get("mid_score", 0.0)),
        "long_score": card.get("long_score", base.get("long_score", 0.0)),
        "catalyst_summary": base.get("catalyst_summary", ""),
        "key_signals": base.get("key_signals", []) or [],
        # Phase 7A — unified opportunity fields carried to Opportunity Watch.
        # Carry the per-horizon status map (Fix round 2) so Opportunity Watch can
        # also respect horizon; ``status`` (dominant) kept for convenience.
        "setup": card.get("setup", ""),
        "status": card.get("status"),
        "status_by_horizon": card.get("status_by_horizon", {}) or {},
        "next_trigger_by_horizon": card.get("next_trigger_by_horizon", {}) or {},
        "blockers": card.get("blockers", []) or [],
        "short_grade": card.get("short_grade", "C"),
        "mid_grade": card.get("mid_grade", "C"),
        "long_grade": card.get("long_grade", "C"),
        "days_to_earnings": card.get("days_to_earnings"),
        "pullback_to_support": bool(card.get("pullback_to_support", False)),
    }
    pending = [p for p in (st.session_state.get("td_pending_signals", []) or [])
               if str(p.get("ticker", "")).upper() != tk]
    pending.append(rec)
    st.session_state["td_pending_signals"] = pending
    return True


def _go_equity(ticker: str) -> None:
    """Stage the Equity Research page prefill ticker, then navigate there.

    The Equity page reads ``equity_prefill_ticker`` on load, fills the ticker
    input, and clears the key (one-shot hand-off)."""
    st.session_state["equity_prefill_ticker"] = str(ticker or "").upper().strip()
    st.switch_page("pages/4_Equity.py")


# ---------------------------------------------------------------------------
# One-click refresh (fail-closed; each step independent)
# ---------------------------------------------------------------------------

def _run_refresh() -> None:
    status = {"macro": False, "themes": False, "signals": False, "equity": False}
    _macro_obj = None  # local handle for the post-refresh integrity check
    prog = st.progress(0, text=t("cockpit_hub_stage_macro"))

    # Step 1 — macro + regime classification
    try:
        from lib.macro_data import fetch_all_macro
        from lib.macro_regime import classify_regime

        regime = classify_regime(fetch_all_macro())
        # Store as a plain dict (not the dataclass) via the macro_state boundary so
        # it survives cross-page session_state reuse consistently with pages 3 / 8.
        save_regime_to_state(regime)
        _macro_obj = get_regime_dict()
        status["macro"] = True
    except Exception:  # noqa: BLE001 — fail-closed; do not abort other steps
        pass
    prog.progress(25, text=t("cockpit_hub_stage_themes"))

    # Step 2 — market-theme momentum
    try:
        from lib.theme_baskets import compute_all_themes

        st.session_state["theme_momentum_results"] = compute_all_themes()
        status["themes"] = True
    except Exception:  # noqa: BLE001 — fail-closed
        pass
    prog.progress(50, text=t("cockpit_hub_stage_signals"))

    # Step 3 — signal candidates (writes cockpit_all_signals + cockpit_triple_signals)
    _candidates = []
    try:
        from lib.candidate_generator import generate_candidates

        _candidates = generate_candidates(
            _regime_str(), top_n=20, llm_n=50,
            lang=st.session_state.get("language", "en")) or []
        status["signals"] = True
    except Exception:  # noqa: BLE001 — fail-closed
        pass
    prog.progress(75, text=t("cockpit_hub_stage_signals"))

    # Step 4 — Phase 7A: rank candidates into opportunity cards + persist the
    # daily snapshot. Orchestration only (no new numbers); fully fail-closed.
    try:
        from lib.opportunity_ranker import rank_opportunities, write_daily_snapshot
        from lib.relative_strength import build_rs_map_cache_only

        _themes_list = st.session_state.get("theme_momentum_results") or []
        _bias = get_regime_field("horizon_bias", {}) or {}
        _cpi_date = None
        try:
            from lib.macro_data import fetch_economic_releases

            _cpi_date = fetch_economic_releases().cpi_date
        except Exception:  # noqa: BLE001 — fail-closed; CPI blocker simply absent
            _cpi_date = None
        # RS (Fix 2 — network-free): SPY/QQQ benchmarks are the single per-refresh
        # fetch; per-ticker history is read CACHE-ONLY from the signal pipeline's
        # already-fetched OHLCV cache (lib.cache_manager). A cache miss degrades to
        # a neutral RS + rs_degraded — it never triggers a per-ticker fetch.
        _tickers = [getattr(c, "ticker", "") for c in _candidates]
        _rs_map = build_rs_map_cache_only(_tickers, period="1y")
        # Cached valuation anchors (read-only, network-free) so LONG-horizon
        # enrichment can differentiate in/above/below the value band instead of
        # collapsing to Research Required. Fail-closed → empty map.
        try:
            from lib.anchor_cache import load_all as _load_anchor_cache

            _anchor_cache = _load_anchor_cache()
        except Exception:  # noqa: BLE001 — fail-closed; no cache enrichment
            _anchor_cache = {}
        # Phase 7B Task 3 — market-internals fragility (network-free; cache-only
        # frames + the single SPY/QQQ fetch). Tighten-only: it can only gate the
        # SHORT horizon, never relax a gate, never touch the frozen regime.
        _fragility = None
        _frag_level = "normal"
        try:
            from lib import market_internals as _mi
            from lib.relative_strength import _default_frame_loader as _cache_frames
            from lib.opportunity_ranker import SNAPSHOT_DIR as _snap_dir
            from ui_utils import load_ohlcv as _bench_frames

            _fragility = _mi.compute_market_fragility(
                universe=_tickers, frame_loader=_cache_frames,
                benchmark_loader=lambda tk: _bench_frames(tk, "1y"),
                themes=_themes_list, snapshot_dir=_snap_dir,
                today_str=datetime.now().strftime("%Y-%m-%d"))
            _frag_level = _fragility.level
            st.session_state["cockpit_fragility"] = _fragility.to_dict()
        except Exception:  # noqa: BLE001 — fail-closed; fragility simply absent
            st.session_state.pop("cockpit_fragility", None)
        _cards = rank_opportunities(
            _candidates, macro_regime=_regime_str(), horizon_bias=_bias,
            themes=_themes_list, rs_map=_rs_map, cpi_date=_cpi_date,
            anchor_cache=_anchor_cache, fragility_level=_frag_level)
        st.session_state["cockpit_opportunities"] = [c.to_dict() for c in _cards]
        _frag_meta = None
        if _fragility is not None:
            try:
                _frag_meta = _mi.fragility_snapshot(
                    _fragility, datetime.now().strftime("%Y-%m-%d"))
            except Exception:  # noqa: BLE001
                _frag_meta = None
        write_daily_snapshot(_cards, themes=_themes_list, macro_regime=_regime_str(),
                             horizon_bias=_bias, fragility=_frag_meta)
        status["opportunities"] = True
    except Exception:  # noqa: BLE001 — fail-closed; Section C falls back gracefully
        pass
    prog.progress(100, text=t("cockpit_hub_refresh_complete"))

    # Integrity check — ensure the macro regime written in Step 1 survived the
    # later steps (no step should overwrite or clear it). Restore if lost.
    if not get_regime_dict() and _macro_obj:
        save_regime_to_state(_macro_obj)

    # Equity valuation is NO LONGER part of the one-click refresh — it runs on
    # demand via the Section C "Run Equity Research" button. Preserve any prior
    # equity freshness flag rather than resetting it.
    _prev_status = st.session_state.get("cockpit_status", {}) or {}
    status["equity"] = bool(_prev_status.get("equity", False))
    st.session_state["cockpit_status"] = status
    st.session_state["cockpit_last_refresh"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _run_equity_research(tickers: list) -> dict:
    """On-demand equity valuation + AI debate for the selected tickers.

    For each ticker: ``compute_app_fair_value`` -> ``analyze_equity_fair_value_debate``
    -> ``store_equity_research_result``, with a progress bar. Returns a summary
    ``{valued, fallbacks, error}``. Fully fail-closed (a failure on one ticker
    never aborts the rest).
    """
    tickers = [str(tk).upper().strip() for tk in (tickers or []) if str(tk).strip()]
    summary = {"valued": 0, "fallbacks": 0, "error": ""}
    if not tickers:
        return summary
    try:
        from lib.equity_valuation import (
            compute_app_fair_value, store_equity_research_result,
        )
        from lib.llm_orchestrator import analyze_equity_fair_value_debate
    except Exception:  # noqa: BLE001 — fail-closed
        return summary
    regime = _regime_str()
    lang = st.session_state.get("language", "en")
    n = len(tickers)
    prog = st.progress(0, text=t("cockpit_hub_equity_running"))
    for i, tk in enumerate(tickers):
        try:
            fv = compute_app_fair_value(tk, _current_price(tk))
            debate = analyze_equity_fair_value_debate(
                tk, fv, macro_regime=regime, lang=lang)
            if (debate.get("debate_status") == "fallback"
                    or not debate.get("bull_case_en")):
                summary["fallbacks"] += 1
                summary["error"] = summary["error"] or debate.get("debate_error", "")
            synth = (debate.get(f"synthesis_{lang}") or debate.get("synthesis_en", ""))
            store_equity_research_result(
                tk, fv, debate_summary=synth,
                analyst_action=debate.get("analyst_action", ""))
            summary["valued"] += 1
        except Exception:  # noqa: BLE001 — skip one ticker, keep going
            pass
        prog.progress(int((i + 1) / n * 100), text=f"{tk} ({i + 1}/{n})")
    _status = dict(st.session_state.get("cockpit_status", {}) or {})
    _status["equity"] = True
    st.session_state["cockpit_status"] = _status
    st.session_state["cockpit_equity_valued_count"] = summary["valued"]
    st.session_state["cockpit_debate_fallbacks"] = summary["fallbacks"]
    st.session_state["cockpit_debate_error"] = summary["error"]
    return summary


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title(t("cockpit_hub_title"))
st.caption(t("cockpit_hub_subtitle"))
st.warning(t("cockpit_hub_safety"))

_hl, _hr = st.columns([3, 1])
with _hl:
    _last = st.session_state.get("cockpit_last_refresh")
    st.caption(f"{t('cockpit_hub_last_refresh')}: {_last or t('cockpit_hub_never')}")
with _hr:
    _do_refresh = st.button(t("cockpit_hub_refresh_btn"), type="primary",
                            use_container_width=True, key="cockpit_refresh_all")

if _do_refresh:
    _run_refresh()
    _status = st.session_state.get("cockpit_status", {})
    _n_sig = len(st.session_state.get("cockpit_all_signals", []) or [])
    # One-click refresh now runs ONLY macro + themes + signals. Equity valuation
    # is on-demand (Section C "Run Equity Research" button).
    st.success(
        f"{t('cockpit_hub_refresh_complete')} — "
        f"{t('cockpit_hub_status_macro')}: {'✅' if _status.get('macro') else '—'} "
        f"{t('cockpit_hub_status_themes')}: {'✅' if _status.get('themes') else '—'} "
        f"{t('cockpit_hub_status_signals')}: {_n_sig}"
    )

# Status indicators — green = refreshed this session, gray = stale / never.
_status = st.session_state.get("cockpit_status", {})
st.markdown(f"**{t('cockpit_hub_status_header')}**")
_sc = st.columns(4)
for _i, (_key, _lbl) in enumerate([
    ("macro", t("cockpit_hub_status_macro")),
    ("themes", t("cockpit_hub_status_themes")),
    ("signals", t("cockpit_hub_status_signals")),
    ("equity", t("cockpit_hub_status_equity")),
]):
    _fresh = bool(_status.get(_key))
    _color = "#3fb950" if _fresh else "#8b949e"
    _txt = t("cockpit_hub_status_fresh") if _fresh else t("cockpit_hub_status_stale")
    _sc[_i].markdown(_badge(f"{_lbl}: {_txt}", _color), unsafe_allow_html=True)

st.divider()


# ---------------------------------------------------------------------------
# Section A — Macro Regime Summary
# ---------------------------------------------------------------------------

st.subheader(t("cockpit_hub_sec_macro"))
# Dev-mode only: surface the actual stored type to confirm the dict invariant.
if os.environ.get("COCKPIT_DEBUG"):
    st.caption(
        "debug: macro_regime_result type = "
        f"{type(st.session_state.get('macro_regime_result')).__name__}"
    )
# Read the regime as a plain dict via the macro_state boundary (dict .get()).
_macro = get_regime_dict()
if not _macro:
    st.info(t("cockpit_hub_macro_not_loaded"))
    st.page_link("pages/8_Macro_Dashboard.py", label=t("cockpit_hub_link_macro"))
else:
    _regime = get_regime_str("unknown")
    _rcolor = _REGIME_COLOR.get(_regime, "#8b949e")
    _bias = get_regime_field("horizon_bias", {}) or {}
    _signals = get_regime_field("key_signals", []) or []
    _posture = get_regime_field("opportunity_posture", "") or ""
    _conf = get_regime_field("confidence", "") or ""
    # classify_regime emits English-only signals/posture — translate for ZH.
    if st.session_state.get("language", "en") == "zh" and (_signals or _posture):
        _signals, _posture = _macro_zh(_signals, _posture)
    st.markdown(
        f"{t('cockpit_hub_macro_regime')}: "
        + _badge(f"{_regime} ({_conf})", _rcolor),
        unsafe_allow_html=True,
    )
    # Phase 7B Task 3 — market-internals fragility line (tighten-only context;
    # the regime label above is NEVER changed by fragility). Shows the level plus
    # the top triggered components with their numbers.
    _frag = st.session_state.get("cockpit_fragility") or {}
    _flevel = str(_frag.get("level", "normal"))
    if _frag and _flevel != "normal":
        _fcolor = {"elevated": "#d29922", "high": "#f85149"}.get(_flevel, "#8b949e")
        _bits = []
        _dd = max([x for x in (_frag.get("distribution_days_spy"),
                               _frag.get("distribution_days_qqq")) if x is not None],
                  default=None)
        if _dd is not None:
            _bits.append(f"distribution days {_dd}/25")
        _b20 = _frag.get("breadth_above_sma20")
        _b20p = _frag.get("breadth_above_sma20_prev")
        if _b20 is not None:
            _bits.append(f"breadth {int((_b20p or _b20)*100)}%→{int(_b20*100)}%"
                         if _b20p is not None else f"breadth {int(_b20*100)}%")
        _gns = _frag.get("good_news_sold")
        if _gns:
            _bits.append(f"{_gns} good-news-sold")
        st.markdown(
            f"{t('cockpit_hub_internals')}: "
            + _badge(_flevel, _fcolor)
            + (f" — {', '.join(_bits)}" if _bits else ""),
            unsafe_allow_html=True,
        )
        st.caption(t("cockpit_hub_internals_note"))
    if _bias:
        st.caption(
            f"{t('cockpit_hub_macro_bias')}: "
            + " · ".join(f"{k}={v}" for k, v in _bias.items())
        )
    if _posture:
        st.caption(f"{t('cockpit_hub_macro_posture')}: {_posture}")
    if _signals:
        st.markdown(f"**{t('cockpit_hub_macro_signals')}**")
        for _s in _signals[:6]:
            st.markdown(f"- {_s}")

st.divider()


# ---------------------------------------------------------------------------
# Section B — Market Themes Summary (top 3 by momentum)
# ---------------------------------------------------------------------------

st.subheader(t("cockpit_hub_sec_themes"))
_themes = st.session_state.get("theme_momentum_results")
if not _themes:
    st.info(t("cockpit_hub_themes_not_loaded"))
    st.page_link("pages/2_Sector.py", label=t("cockpit_hub_link_sector"))
else:
    _lang = st.session_state.get("language", "en")
    _top3 = sorted(_themes, key=lambda r: getattr(r, "momentum_score", 0.0),
                   reverse=True)[:3]
    _tcols = st.columns(len(_top3) or 1)
    for _i, _th in enumerate(_top3):
        with _tcols[_i]:
            with st.container(border=True):
                _name = getattr(_th, "label_zh" if _lang == "zh" else "label_en",
                                getattr(_th, "theme_key", "?"))
                _r3 = getattr(_th, "return_3m", None)
                _ms = getattr(_th, "momentum_score", 0.0) or 0.0
                st.markdown(f"**{_name}**")
                st.metric(t("cockpit_hub_theme_3m"),
                          f"{_r3:+.1f}%" if _r3 is not None else "—")
                _mcolor = "#3fb950" if _ms >= 0.66 else ("#d29922" if _ms >= 0.33 else "#8b949e")
                st.markdown(
                    f"{t('cockpit_hub_theme_momentum')}: "
                    + _badge(f"{_ms:.2f}", _mcolor),
                    unsafe_allow_html=True,
                )
                # Phase 7B Task 2 — stage label + one-line breadth summary only
                # (the deep two-ring view lives on the Sector page; no chart here).
                _stage = getattr(_th, "stage", "") or ""
                if _stage:
                    _scol = {"leading": "#3fb950", "rotating_in": "#388bfd",
                             "rotating_out": "#d29922",
                             "out_of_favor": "#8b949e"}.get(_stage, "#8b949e")
                    _conf_txt = (t("cockpit_hub_stage_confirmed")
                                 if getattr(_th, "stage_confirmed", False)
                                 else t("cockpit_hub_stage_unconfirmed"))
                    st.markdown(
                        f"{t('cockpit_hub_stage')}: "
                        + _badge(f"{t('stage_' + _stage)} · {_conf_txt}", _scol),
                        unsafe_allow_html=True,
                    )
                    _bb = getattr(_th, "breadth_beat_pct", None)
                    _ba = getattr(_th, "breadth_above_sma20_pct", None)
                    if _bb is not None:
                        st.caption(
                            f"{t('cockpit_hub_breadth')}: "
                            f"{int(_bb*100)}% > {getattr(_th, 'benchmark', 'QQQ')}"
                            + (f" · {int(_ba*100)}% > SMA20" if _ba is not None else ""))

st.divider()


# ---------------------------------------------------------------------------
# Section C — Opportunity Card panel (Phase 7A) + ticker selection
# ---------------------------------------------------------------------------

st.subheader(t("opp_panel_header"))
st.caption(t("opp_panel_caption"))
_all_signals = st.session_state.get("cockpit_all_signals", []) or []
_opportunities = st.session_state.get("cockpit_opportunities", []) or []
_lang_c = st.session_state.get("language", "en")
_sig_by_tk = {str(s.get("ticker", "")).upper(): s for s in _all_signals}


def _opp_grade_badge(grade: str) -> str:
    return _badge(grade, _GRADE_COLOR.get(grade, "#8b949e"))


def _opp_status_badge(status) -> str:
    if not status:
        return _badge(t("opp_status_pending"), "#8b949e")
    return _badge(t(_STATUS_KEY.get(status, "opp_status_research")),
                  _STATUS_COLOR.get(status, "#8b949e"))


def _opp_card_blockers(card: dict, horizon: str) -> list:
    """Per-card blockers: ticker-specific only, filtered to the displayed horizon
    (market-wide conditions are shown once in the banner, Task 3)."""
    out = []
    for b in (card.get("blockers", []) or []):
        if b.get("code") in _MARKET_WIDE_CODES:
            continue  # shown in the panel banner, not per card
        hz = b.get("horizons") or []
        if hz and horizon not in hz:
            continue  # not relevant to the currently displayed horizon
        out.append(b)
    return out


def _render_opportunity_card(card: dict, rank: int, horizon: str,
                             concentration_ref: str | None = None) -> None:
    """Render one Phase 7A opportunity card (review-only research queue item)."""
    tk = str(card.get("ticker", "?")).upper()
    grade = card.get(f"{horizon}_grade", "C")
    setup_lbl = t(_SETUP_KEY.get(card.get("setup", ""), "opp_setup_speculative"))
    # Per-horizon status/trigger for the SELECTED horizon (Fix round 2).
    _status = (card.get("status_by_horizon") or {}).get(horizon)
    _nt = (card.get("next_trigger_by_horizon") or {}).get(horizon, "")
    with st.container(border=True):
        _r = st.columns([1.4, 1.0, 1.0, 2.2, 1.4])
        _r[0].markdown(f"**{tk}**")
        _r[1].markdown(f"{t('opp_grade')} " + _opp_grade_badge(grade),
                       unsafe_allow_html=True)
        _r[2].markdown(_opp_status_badge(_status), unsafe_allow_html=True)
        _r[3].caption(f"🎯 {setup_lbl}")
        # Any candidate can be staged for the Trading Desk Opportunity Watch.
        if _r[4].button(t("cockpit_hub_add_td"), key=f"cockpit_addtd_{tk}",
                        use_container_width=True):
            if _add_to_trading_desk(card, _sig_by_tk.get(tk)):
                st.toast(f"{tk} → {t('cockpit_hub_added_td')}")
        # three independent grades (S/M/L) — never decimals
        st.caption(
            f"{t('opp_horizon_short')} {card.get('short_grade', 'C')} · "
            f"{t('opp_horizon_mid')} {card.get('mid_grade', 'C')} · "
            f"{t('opp_horizon_long')} {card.get('long_grade', 'C')}"
            + (f" · 🟢 {t('opp_pullback_support')}"
               if card.get("pullback_to_support") else "")
        )
        # what the card is waiting for — from the SELECTED horizon's engine output
        if _nt and _status not in ("Actionable Now", None):
            st.caption(f"⏭️ {t('opp_next_trigger')}: {_nt}")
        # why-now lines (polished sentence if available, else commonality-filtered
        # bilingual codes — see why_now_display)
        _polished = card.get(f"why_now_polished_{_lang_c}", "")
        # Phase 7B Task 1 — the why_now RS line follows the SELECTED horizon
        # (SHORT=5D / MID=1M / LONG=6M); fall back to the dominant-horizon list.
        _why = ((card.get("why_now_by_horizon") or {}).get(horizon)
                or card.get("why_now_display") or card.get("why_now", []) or [])
        if _polished:
            st.markdown(f"**{t('opp_why_now')}**: {_polished}")
        elif _why:
            _txt = " · ".join(
                (r.get(f"text_{_lang_c}") or r.get("text_en", "")) for r in _why[:3])
            st.markdown(f"**{t('opp_why_now')}**: {_txt}")
        # per-card blockers: ticker-specific, filtered to the displayed horizon
        _blk = _opp_card_blockers(card, horizon)
        if _blk:
            _chips = " ".join(
                _badge(b.get(f"text_{_lang_c}") or b.get("text_en", b.get("code", "")),
                       "#f85149" if b.get("severity") == "critical" else "#d29922")
                for b in _blk[:4])
            st.markdown(f"{t('opp_blockers')}: {_chips}", unsafe_allow_html=True)
        # calendar + concentration hints (concentration is computed at display time)
        _hints = []
        _d2e = card.get("days_to_earnings")
        if _d2e is not None:
            _hints.append(f"📅 {t('opp_days_to_earnings')}: {_d2e}{t('opp_days')}")
        if concentration_ref:
            _hints.append(f"🔗 {t('opp_concentration_prefix')}{concentration_ref}")
        if card.get("rs_degraded"):
            _hints.append(f"⚠️ {t('opp_rs_degraded')}")
        if _hints:
            st.caption(" · ".join(_hints))


if not _opportunities:
    if _all_signals:
        # Signals exist but were not ranked (e.g. ranking step failed) — degrade.
        st.info(t("cockpit_hub_signals_none"))
    else:
        st.info(t("opp_none"))
else:
    _n_triple = sum(1 for s in _all_signals if s.get("signal_strength") == "triple")
    _n_double = sum(1 for s in _all_signals if s.get("signal_strength") == "double")
    _n_single = sum(1 for s in _all_signals if s.get("signal_strength") == "single")
    _scols = st.columns(4)
    _scols[0].metric(t("cockpit_hub_signals_total"), len(_opportunities))
    _scols[1].metric(t("cockpit_hub_signals_triple"), _n_triple)
    _scols[2].metric(t("cockpit_hub_signals_double"), _n_double)
    _scols[3].metric(t("cockpit_hub_signals_single"), _n_single)

    # Horizon selector — re-sorts the queue by the corresponding horizon score.
    _h_opts = {"short": t("opp_horizon_short"), "mid": t("opp_horizon_mid"),
               "long": t("opp_horizon_long")}
    _h_sel = st.radio(
        t("opp_horizon_label"), options=list(_h_opts.keys()),
        format_func=lambda k: _h_opts[k], index=1, horizontal=True,
        key="cockpit_opp_horizon")
    # Deterministic display order: score desc, then ticker asc.
    _ranked = sorted(
        _opportunities,
        key=lambda c: (-(c.get(f"{_h_sel}_score", 0.0) or 0.0), c.get("ticker", "")))
    _shown = _ranked[:10]

    # Market-wide conditions shown ONCE as a banner above the cards (Task 3).
    _bias = get_regime_field("horizon_bias", {}) or {}
    _d2f = _shown[0].get("days_to_fomc") if _shown else None
    _d2c = _shown[0].get("days_to_cpi") if _shown else None
    _banner = _market_banner_blockers(_regime_str(), _bias, _d2f, _d2c, _h_sel)
    if _banner:
        _lang_c2 = st.session_state.get("language", "en")
        _bchips = " ".join(
            _badge(b.text_zh if _lang_c2 == "zh" else b.text_en, "#d29922")
            for b in _banner)
        st.markdown(f"**{t('opp_banner_header')}**: {_bchips}", unsafe_allow_html=True)

    # Concentration markers computed at DISPLAY time over the shown order, so
    # "#K" always points to a card visible above (Task 4).
    _conc = _concentration_refs(_shown)
    for _rank, _card in enumerate(_shown, start=1):
        _render_opportunity_card(_card, _rank, _h_sel,
                                 _conc.get(_card.get("ticker", "")))

# ── Ticker selection for deep research (signals + active holdings) ──────────
st.markdown(f"#### {t('cockpit_hub_select_header')}")
_holding_tickers = []
try:
    from lib.holdings import get_active_holdings

    _holding_tickers = [h.ticker.upper() for h in (get_active_holdings() or [])
                        if getattr(h, "ticker", "")]
except Exception:  # noqa: BLE001 — fail-closed
    _holding_tickers = []

_signal_tickers = [str(s.get("ticker", "")).upper() for s in _all_signals
                   if s.get("ticker")]
_all_tickers = sorted(set(_signal_tickers) | set(_holding_tickers))

if not _all_tickers:
    st.caption(t("cockpit_hub_no_tickers"))
    st.session_state["cockpit_selected_tickers"] = []
else:
    _select_all = st.checkbox(t("cockpit_hub_select_all"), key="cockpit_select_all")
    _selected: list[str] = []
    _cols = st.columns(4)
    for _i, _tk in enumerate(_all_tickers):
        # Include the select-all state in the key so flipping it re-creates the
        # individual checkboxes with the new default (works around Streamlit's
        # widget-state stickiness).
        _checked = _cols[_i % 4].checkbox(
            _tk, value=_select_all, key=f"cockpit_sel_{_tk}_{_select_all}")
        if _checked:
            _selected.append(_tk)
    st.session_state["cockpit_selected_tickers"] = _selected

# On-demand equity research — valuation + AI debate for the selected tickers.
# (No longer part of the one-click refresh.)
if st.button(t("cockpit_hub_run_equity"), type="primary",
             key="cockpit_run_equity"):
    _sel_now = st.session_state.get("cockpit_selected_tickers", []) or []
    if not _sel_now:
        st.warning(t("cockpit_hub_no_selection"))
    else:
        _eq_summary = _run_equity_research(_sel_now)
        st.success(
            f"{t('cockpit_hub_equity_done')} — "
            f"{t('cockpit_hub_status_equity')}: {_eq_summary['valued']}"
        )
        if _eq_summary.get("fallbacks"):
            st.warning(
                f"{t('cockpit_fv_debate_failed')} ({_eq_summary['fallbacks']}) — "
                f"{_eq_summary.get('error') or t('cockpit_fv_na')}"
            )

st.divider()


# ---------------------------------------------------------------------------
# Section D — Equity Research Results
# ---------------------------------------------------------------------------

st.subheader(t("cockpit_hub_sec_equity"))
_equity_results = st.session_state.get("equity_research_results", {}) or {}
_selected = st.session_state.get("cockpit_selected_tickers", []) or []

if not _selected:
    st.info(t("cockpit_hub_equity_none"))
else:
    for _tk in _selected:
        _res = _equity_results.get(_tk)
        with st.container(border=True):
            if not _res:
                _cc = st.columns([1, 3])
                _cc[0].markdown(f"**{_tk}**")
                _cc[1].caption(t("cockpit_hub_not_researched"))
                if st.button(t("cockpit_hub_go_equity"), key=f"cockpit_goeq_nr_{_tk}"):
                    _go_equity(_tk)
                continue
            _up = _res.get("upside_pct", 0.0) or 0.0
            _up_color = "#3fb950" if _up > 0.10 else ("#f85149" if _up < -0.10 else "#8b949e")
            _conf = _res.get("confidence", "low")
            _cf_color = {"high": "#3fb950", "medium": "#d29922", "low": "#8b949e"}.get(
                _conf, "#8b949e")
            _act = _res.get("analyst_action", "") or "—"
            _row = st.columns([1.0, 1.4, 1.2, 1.2, 1.2])
            _row[0].markdown(f"**{_tk}**")
            _row[1].markdown(
                f"{t('cockpit_hub_fair_value')}: **${_res.get('fair_value_mid', 0):.2f}**")
            _row[2].markdown(
                f"{t('cockpit_hub_upside')}: "
                f"<span style='color:{_up_color};font-weight:700'>{_up*100:+.1f}%</span>",
                unsafe_allow_html=True)
            _row[3].markdown(
                f"{t('cockpit_hub_confidence')}: " + _badge(_conf, _cf_color),
                unsafe_allow_html=True)
            _row[4].markdown(f"{t('cockpit_hub_action')}: **{_act}**")
            _summary = (_res.get("debate_summary", "") or "")[:100]
            if _summary:
                st.caption(_summary)
            if st.button(t("cockpit_hub_view_research"), key=f"cockpit_goeq_{_tk}"):
                _go_equity(_tk)

st.divider()


# ---------------------------------------------------------------------------
# Section E — Triple Signal Watch (triple hits not in active holdings)
# ---------------------------------------------------------------------------

st.subheader(t("cockpit_hub_sec_triple"))
_triples = st.session_state.get("cockpit_triple_signals", []) or []
_held = set(_holding_tickers)
_watch = [s for s in _triples if str(s.get("ticker", "")).upper() not in _held]

if not _watch:
    st.info(t("cockpit_hub_triple_none"))
else:
    for _sig in _watch:
        _tk = str(_sig.get("ticker", "?")).upper()
        with st.container(border=True):
            _r = st.columns([1.0, 3.0, 1.4])
            _r[0].markdown(f"**{_tk}** " + _badge("triple", _STRENGTH_COLOR["triple"]),
                           unsafe_allow_html=True)
            _r[1].caption(
                f"S {_sig.get('short_score', 0):.2f} · "
                f"M {_sig.get('mid_score', 0):.2f} · "
                f"L {_sig.get('long_score', 0):.2f}"
            )
            if _r[2].button(t("cockpit_hub_add_holdings"),
                            key=f"cockpit_addhold_{_tk}", use_container_width=True):
                _ks = _sig.get("key_signals", []) or []
                _scores = {
                    "short": _sig.get("short_score", 0.0) or 0.0,
                    "mid": _sig.get("mid_score", 0.0) or 0.0,
                    "long": _sig.get("long_score", 0.0) or 0.0,
                }
                st.session_state["td_prefill"] = {
                    "ticker": _tk,
                    "horizon": max(_scores, key=lambda k: _scores[k]),
                    "thesis_text": "\n".join(f"- {x}" for x in _ks),
                    "thesis_source": "scanner",
                    "thesis_signals": _ks,
                }
                st.session_state["td_adding"] = True
                st.session_state["td_editing_id"] = None
                st.switch_page("pages/9_Trading_Desk.py")
            _cat = _sig.get("catalyst_summary", "") or ""
            if _cat:
                st.caption(f"⚡ {t('cockpit_hub_catalyst')}: {_cat}")
