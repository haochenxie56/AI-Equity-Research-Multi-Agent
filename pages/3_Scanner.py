"""Page 3 — Stock Scanner (custom pool)"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from ui_utils import (
    apply_theme, render_sidebar, load_info, load_ohlcv,
    apply_layout, apply_legend, fmt_large, download_report_button, page_header, render_table, t, bi,
    render_workflow_bar,
)
from lib.macro_data import fetch_all_macro
from lib.macro_regime import MacroRegimeResult, classify_regime
from lib.signal_engine import TickerSignalResult
from lib.candidate_generator import generate_candidates, build_universe, UniverseConfig
from lib.theme_baskets import THEME_BASKETS

# ── Phase 6B — Stock Selection Signal Layer feature flag ──────────────────────
# When True, an AI-generated candidate-signal section (built from real
# alternative-data + fundamental + technical signals) is shown at the top of the
# page. When False, this page behaves EXACTLY as it did before Phase 6B: only the
# manual scanner runs and no signal-generation code is exercised.
SCANNER_SIGNAL_MODE = True

st.set_page_config(page_title="Stock Scanner", page_icon="🔍", layout="wide")
apply_theme()
render_sidebar()

_lang = st.session_state.get("language", "en")
_dark = st.session_state.get("dark_mode", True)

st.title(t("p3_title"))
page_header()
render_workflow_bar()
st.caption(t("p3_subtitle"))
st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 6B — AI SIGNAL CANDIDATES (auto-generated from real signals)
# Surfaces an AI-generated candidate list ranked by alternative data, EPS-revision
# trend, narrative attribution, and entry quality — without a manual ticker pool.
# Review-only context; never an order or execution instruction.
# ══════════════════════════════════════════════════════════════════════════════
if SCANNER_SIGNAL_MODE:
    # Phase 6B (Plan A) — obtain the current macro regime directly. Both
    # fetch_all_macro() and classify_regime() are fail-closed and cached
    # (st.cache_data TTL), so if the macro page was already visited this hits the
    # cache with no extra cost; otherwise it fetches the regime live now. The
    # freshly classified regime is published to st.session_state["macro_regime_result"]
    # for cross-page reuse, then its `regime` field drives the signal scoring.
    _macro_regime = "unknown"
    _macro_conf = None
    _macro_cov = None
    try:
        _macro_res = classify_regime(fetch_all_macro())
        st.session_state["macro_regime_result"] = {
            "regime": _macro_res.regime,
            "confidence": _macro_res.confidence,
            "horizon_bias": dict(_macro_res.horizon_bias or {}),
            "data_coverage": _macro_res.data_coverage,
        }
        _macro_regime = _macro_res.regime
        _macro_conf = _macro_res.confidence
        _macro_cov = _macro_res.data_coverage
    except Exception:
        # Fail-closed: reuse any previously-published regime, else stay "unknown".
        _prev = st.session_state.get("macro_regime_result")
        if isinstance(_prev, dict) and _prev.get("regime"):
            _macro_regime = str(_prev.get("regime"))
            _macro_conf = _prev.get("confidence")
            _macro_cov = _prev.get("data_coverage")

    # ── Universe Configuration ────────────────────────────────────────────────
    # Lets the user shape the candidate universe (S&P 500 anchor + cross-GICS
    # theme baskets + manual tickers) before generating candidates. Review-only:
    # no order, no execution. The live universe size is shown without fetching
    # market data (build_universe is a pure set-union over hardcoded lists +
    # session_state). The resulting UniverseConfig is passed to
    # generate_candidates() below.

    # Theme pre-load banner from the Sector Research "Send to Scanner" hand-off.
    _theme_universe = st.session_state.get("theme_universe") or []
    _theme_label = st.session_state.get("theme_universe_label") or ""
    if _theme_universe:
        _bn_col, _clr_col = st.columns([5, 1])
        with _bn_col:
            st.info(
                t("scn_uni_preloaded").format(
                    label=_theme_label or "—", n=len(_theme_universe)
                )
            )
        with _clr_col:
            if st.button(t("scn_uni_clear_btn"), key="scn_uni_clear",
                         use_container_width=True):
                st.session_state.pop("theme_universe", None)
                st.session_state.pop("theme_universe_label", None)
                st.rerun()

    with st.expander(t("scn_uni_title"), expanded=False):
        _inc_sp500 = st.checkbox(
            t("scn_uni_sp500"), value=True, key="scn_uni_sp500_cb",
        )
        _theme_keys = list(THEME_BASKETS.keys())

        def _theme_label_fn(k: str) -> str:
            _cfg = THEME_BASKETS.get(k, {})
            return _cfg.get("label_zh" if _lang == "zh" else "label_en", k)

        _sel_themes = st.multiselect(
            t("scn_uni_themes"), options=_theme_keys,
            format_func=_theme_label_fn, key="scn_uni_themes_ms",
        )
        _manual_raw = st.text_input(
            t("scn_uni_manual"), value="", key="scn_uni_manual_ti",
        )
        _manual_list = [
            x.strip().upper()
            for x in _manual_raw.replace("\n", ",").split(",")
            if x.strip()
        ]
        _max_size = st.slider(
            t("scn_uni_max"), min_value=50, max_value=300, value=150, step=25,
            key="scn_uni_max_sl",
        )

        _uni_config = UniverseConfig(
            include_sp500_top100=_inc_sp500,
            selected_themes=_sel_themes,
            manual_tickers=_manual_list,
            max_size=_max_size,
        )
        # Live universe size — pure set-union, no market-data fetch.
        try:
            _uni_preview = build_universe(_uni_config)
        except Exception:
            _uni_preview = []
        st.caption(t("scn_uni_current").format(n=len(_uni_preview)))

    st.subheader(t("scn_sig_title"))
    # Directly show the currently-loaded macro regime status (regime + confidence
    # + data coverage when available); reuses the existing macro chrome keys.
    _macro_status = f'{t("scn_sig_macro_label")}: {_macro_regime}'
    if _macro_conf:
        _macro_status += f'  ·  {t("macro_live_confidence_label")}: {_macro_conf}'
    if _macro_cov is not None:
        try:
            _macro_status += f'  ·  {t("macro_live_coverage_label")}: {_macro_cov:.0%}'
        except (TypeError, ValueError):
            pass
    st.caption(f'{t("scn_sig_caption")}  ·  {_macro_status}')

    # LLM narrative depth — how many Layer-1 survivors get a Layer-2 LLM
    # narrative call (default 30, range 10–50). Estimated time ≈ llm_n × 2s.
    _llm_n = st.slider(
        t("scn_sig_llm_depth"), min_value=10, max_value=100, value=50, step=5,
        key="scn_sig_llm_n",
        help=t("scn_sig_llm_help"),
    )
    st.caption(f'{t("scn_sig_llm_est")}: ~{_llm_n * 2}s')

    _gen_col, _send_col = st.columns([1, 1])
    with _gen_col:
        _gen_clicked = st.button(
            t("scn_sig_generate_btn"), type="primary",
            use_container_width=True, key="scn_sig_generate",
        )
    with _send_col:
        _send_clicked = st.button(
            t("scn_sig_send_btn"), use_container_width=True, key="scn_sig_send",
            disabled=not st.session_state.get("signal_candidates"),
        )

    if _gen_clicked:
        with st.spinner(t("scn_sig_generating")):
            try:
                st.session_state["signal_candidates"] = generate_candidates(
                    _macro_regime, top_n=20, llm_n=_llm_n, config=_uni_config,
                    lang=_lang,
                )
            except Exception:
                st.session_state["signal_candidates"] = []

    _candidates = st.session_state.get("signal_candidates") or []

    # "Send to Manual Scanner": pre-fill the manual pool input (consumed below by
    # the existing `_scanner_pool_prefill` mechanism on the same render pass).
    if _send_clicked and _candidates:
        _top_syms = [
            c.ticker for c in _candidates[:20] if getattr(c, "ticker", "")
        ]
        if _top_syms:
            st.session_state["_scanner_pool_prefill"] = ", ".join(_top_syms)
            st.success(t("scn_sig_sent_note"))

    if not _candidates:
        st.info(t("scn_sig_empty_hint"))
    else:
        import html as _html_mod

        def _esc(s) -> str:
            return _html_mod.escape(str(s if s is not None else ""))

        _sig_tx = "#e6edf3" if _dark else "#1f2328"
        _sig_mut = "#8b949e"

        # Candidate-type color coding: FUNNEL=blue, ALT_SIGNAL=orange, BOTH=green.
        def _type_color(kind: str) -> str:
            return {
                "FUNNEL": "#388bfd",
                "ALT_SIGNAL": "#d29922",
                "BOTH": "#3fb950",
            }.get(kind, _sig_mut)

        # signal_strength -> (accent color, emoji prefix). triple = gold + 🔥.
        def _strength_style(s: str):
            return {
                "triple": ("#d4a017", "🔥"),
                "double": ("#3fb950", ""),
                "single": ("#388bfd", ""),
                "none":   (_sig_mut, ""),
            }.get(s, (_sig_mut, ""))

        # Per-horizon hit thresholds (short 0.65 / mid 0.60 / long 0.55).
        _HZ_THRESH = {"short": 0.65, "mid": 0.60, "long": 0.55}

        def _pill_color(h: str, score: float) -> str:
            th = _HZ_THRESH.get(h, 0.6)
            if score >= th:
                return "#3fb950"   # green — horizon hit
            if score >= th - 0.15:
                return "#d29922"   # yellow — near threshold
            return "#f85149"       # red — well below

        # ── Horizon filter checkboxes (default all checked) ───────────────────
        st.caption(t("scn_sig_filter_label"))
        _hz_cols = st.columns([1, 1, 1, 3])
        with _hz_cols[0]:
            _show_short = st.checkbox(t("scn_sig_hz_short"), value=True, key="scn_sig_hz_short_cb")
        with _hz_cols[1]:
            _show_mid = st.checkbox(t("scn_sig_hz_mid"), value=True, key="scn_sig_hz_mid_cb")
        with _hz_cols[2]:
            _show_long = st.checkbox(t("scn_sig_hz_long"), value=True, key="scn_sig_hz_long_cb")

        _checked = set()
        if _show_short:
            _checked.add("short")
        if _show_mid:
            _checked.add("mid")
        if _show_long:
            _checked.add("long")
        _all_checked = _show_short and _show_mid and _show_long

        def _visible(c) -> bool:
            # Show a candidate if any of its hit horizons is checked. A "none"
            # signal (no horizon hit) is opt-in: shown only when all three boxes
            # are checked.
            hh = set(getattr(c, "horizons_hit", []) or [])
            if getattr(c, "signal_strength", "none") == "none":
                return _all_checked
            return bool(hh & _checked)

        _shown = [c for c in _candidates if _visible(c)]

        # ── Signal cards ──────────────────────────────────────────────────────
        for c in _shown:
            _s = getattr(c, "signal_strength", "none") or "none"
            _accent, _emoji = _strength_style(_s)
            _kind = getattr(c, "candidate_type", "FUNNEL") or "FUNNEL"
            _kc = _type_color(_kind)
            _short = float(getattr(c, "short_score", 0.0) or 0.0)
            _mid = float(getattr(c, "mid_score", 0.0) or 0.0)
            _long = float(getattr(c, "long_score", 0.0) or 0.0)
            _hh = set(getattr(c, "horizons_hit", []) or [])
            _is_triple = _s == "triple"

            with st.container(border=True):
                # Row 1 — ticker + signal_strength badge + candidate_type badge.
                _strength_badge = (
                    f'<span style="background:{_accent}22;border:1px solid {_accent};'
                    f'color:{_accent};padding:2px 10px;border-radius:12px;'
                    f'font-size:0.78rem;font-weight:700">{_emoji} '
                    f'{_esc(t("scn_sig_strength_" + _s))}</span>'
                )
                _type_badge = (
                    f'<span style="background:{_kc}22;border:1px solid {_kc};'
                    f'color:{_kc};padding:2px 10px;border-radius:12px;'
                    f'font-size:0.72rem;font-weight:700">{_esc(t("scn_sig_col_type"))}: {_esc(_kind)}</span>'
                )
                _triple_hdr = (
                    f'<span style="background:#d4a01733;border:1px solid #d4a017;'
                    f'color:#d4a017;padding:2px 10px;border-radius:12px;'
                    f'font-size:0.78rem;font-weight:700">{_esc(t("scn_sig_triple_header"))}</span>'
                    if _is_triple else ""
                )
                # Triple hits get a gold/amber border accent; others a subtle one.
                _card_border = "2px solid #d4a017" if _is_triple else f"1px solid {_accent}"
                _card_bg = "#d4a01710" if _is_triple else "transparent"

                # Row 2 — three horizon score pills with ✓ (hit) / ○ (below).
                def _pill(h: str, label: str, score: float) -> str:
                    col = _pill_color(h, score)
                    mark = "✓" if h in _hh else "○"
                    return (
                        f'<span style="display:inline-block;margin-right:10px;'
                        f'background:{col}22;border:1px solid {col};color:{col};'
                        f'padding:2px 10px;border-radius:10px;font-weight:700;'
                        f'font-size:0.82rem">{_esc(label)} {score:.2f} {mark}</span>'
                    )
                _pills = (
                    _pill("short", t("scn_sig_hz_short"), _short)
                    + _pill("mid", t("scn_sig_hz_mid"), _mid)
                    + _pill("long", t("scn_sig_hz_long"), _long)
                )

                # Row 3 — catalyst summary (⚡) + horizon tags + recency + warning.
                _cat_summary = getattr(c, "catalyst_summary", "") or ""
                _cat_html = ""
                if _cat_summary:
                    _ch_tags = ", ".join(getattr(c, "catalyst_horizon", []) or []) or "—"
                    _rec = getattr(c, "catalyst_recency", "none") or "none"
                    _priced = bool(getattr(c, "already_priced_in", False))
                    _warn = (
                        f' <span style="color:#f85149;font-weight:700">'
                        f'⚠ {_esc(t("scn_sig_priced_in"))}</span>'
                        if _priced else ""
                    )
                    _cat_html = (
                        f'<div style="margin-top:6px;font-size:0.85rem;color:{_sig_tx}">'
                        f'⚡ {_esc(_cat_summary)} '
                        f'<span style="color:{_sig_mut};font-size:0.78rem">'
                        f'[{_esc(_ch_tags)} · {_esc(_rec)}]</span>{_warn}</div>'
                    )

                # Row 4 — first 3 key signals as a bullet list.
                _ks = getattr(c, "key_signals", []) or []
                _ks_html = "".join(
                    f'<li style="margin:1px 0">{_esc(k)}</li>' for k in _ks[:3]
                )
                _ks_block = (
                    f'<ul style="margin:6px 0 0 0;padding-left:18px;font-size:0.84rem;'
                    f'color:{_sig_tx}">{_ks_html}</ul>' if _ks_html else ""
                )

                st.markdown(
                    f'<div style="border-left:{_card_border};background:{_card_bg};'
                    f'border-radius:0 6px 6px 0;padding:8px 12px">'
                    f'<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">'
                    f'<span style="font-size:1.35rem;font-weight:800;color:{_sig_tx}">{_esc(c.ticker)}</span>'
                    f'{_strength_badge}{_type_badge}{_triple_hdr}</div>'
                    f'<div style="margin-top:8px">{_pills}</div>'
                    f'{_cat_html}{_ks_block}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # Row 5 — collapsed details.
                with st.expander(t("scn_sig_details")):
                    _full_ks = "".join(f"- {k}\n" for k in _ks) or "—\n"
                    st.markdown(_full_ks)
                    _eps = getattr(c, "eps_revision_direction", "unknown")
                    _val = getattr(c, "valuation_percentile", 0.5)
                    _eq = getattr(c, "entry_quality_label", "—")
                    _ns = getattr(c, "narrative_stage", "unknown")
                    _tags = ", ".join(getattr(c, "narrative_theme_tags", []) or []) or "—"
                    try:
                        _val_txt = f"{float(_val):.2f}"
                    except (TypeError, ValueError):
                        _val_txt = "—"
                    st.caption(
                        f'{t("scn_sig_eps")}: {_eps}  ·  '
                        f'{t("scn_sig_val")}: {_val_txt}  ·  '
                        f'{t("scn_sig_col_entry")}: {_eq}'
                    )
                    st.caption(f'{t("scn_sig_narr_stage")}: {_ns}  ·  {t("scn_sig_theme_tags")}: {_tags}')

                    # Track A / Track B sub-scores (shown for ALT_SIGNAL especially).
                    _ta = getattr(c, "track_a", None)
                    _tb = getattr(c, "track_b", None)
                    if _kind == "ALT_SIGNAL" or _tb is not None:
                        _ta_s = f'{_ta.track_a_score:.2f}' if _ta is not None else "—"
                        _tb_s = f'{_tb.track_b_score:.2f}' if _tb is not None else "—"
                        _ins = f'{_tb.insider_buy_signal:.2f}' if _tb is not None else "—"
                        _unu = f'{_tb.unusual_news_signal:.2f}' if _tb is not None else "—"
                        _ana = f'{_tb.analyst_revision_signal:.2f}' if _tb is not None else "—"
                        st.caption(
                            f'{t("scn_sig_col_track_a")}: {_ta_s}  ·  '
                            f'{t("scn_sig_col_track_b")}: {_tb_s}  ·  '
                            f'{t("scn_sig_col_insider")}: {_ins}  ·  '
                            f'{t("scn_sig_col_unusual")}: {_unu}  ·  '
                            f'{t("scn_sig_col_analyst")}: {_ana}'
                        )

        # ── Summary line ──────────────────────────────────────────────────────
        _n_triple = sum(1 for c in _candidates if getattr(c, "signal_strength", "") == "triple")
        _n_double = sum(1 for c in _candidates if getattr(c, "signal_strength", "") == "double")
        _n_single = sum(1 for c in _candidates if getattr(c, "signal_strength", "") == "single")
        st.caption(
            t("scn_sig_summary").format(
                n=len(_candidates), triple=_n_triple, double=_n_double, single=_n_single
            )
        )

    st.caption(t("scn_sig_disclaimer"))
    st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# AI WORKFLOW RESULTS — read from research_state
# ══════════════════════════════════════════════════════════════════════════════
_wf_scan_res = (
    st.session_state.get("research_state", {})
    .get("results", {})
    .get("scan") or {}
)
_scan_llm    = _wf_scan_res.get("llm") or {}
_selected    = _scan_llm.get("selected") or []
_top_pick    = (_scan_llm.get("decision") or "").upper().strip()
_runner_up   = (_scan_llm.get("runner_up") or "").upper().strip()
_scan_reason = bi(_scan_llm, "reasoning", _lang)

# Resolve top pick: prefer decision field, fall back to first valid selected entry
if not _top_pick or _top_pick == "N/A":
    for _s in _selected:
        _tk = (_s.get("ticker") or "").upper().strip()
        if _tk and _tk != "N/A":
            _top_pick = _tk
            break

_has_scan_llm = bool(_top_pick and _top_pick not in ("N/A", ""))

_ai_bg  = "#161b22" if _dark else "#f6f8fa"
_ai_bd  = "#30363d" if _dark else "#d0d7de"
_ai_txt = "#e6edf3" if _dark else "#1f2328"

_CONF_COLOR = {
    "High": "#3fb950", "高": "#3fb950",
    "Medium": "#d29922", "中": "#d29922",
    "Low": "#f85149", "低": "#f85149",
}
_STRAT_COLOR = {
    "Momentum": "#388bfd",       "质量成长": "#388bfd",
    "Quality Growth": "#3fb950", "动量": "#3fb950",
    "Value": "#d29922",          "价值": "#d29922",
    "Oversold Bounce": "#a371f7","超卖反弹": "#a371f7",
}

_ai_title = "🤖 AI 工作流选股结果" if _lang == "zh" else "🤖 AI Workflow Scan Results"
st.subheader(_ai_title)

if not _has_scan_llm:
    # ── No workflow results: show hint ────────────────────────────────────────
    _hint = (
        "尚无 AI 选股结果。请先在 **[总览页](/Overview)** 运行 AI 研究工作流，"
        "完成后此处将自动显示跨策略选股分析。"
        if _lang == "zh" else
        "No AI scan results yet. Run the **[AI Research Workflow](/Overview)** on the "
        "Overview page first — cross-strategy stock selections will appear here automatically."
    )
    st.markdown(
        f'<div style="background:{_ai_bg};border:1px dashed {_ai_bd};'
        f'border-radius:6px;padding:10px 16px;font-size:0.85rem;color:#8b949e">'
        f'🤖 {_hint}</div>',
        unsafe_allow_html=True,
    )
else:
    # ── Top-pick highlight card ───────────────────────────────────────────────
    _top_entry  = next((s for s in _selected if s.get("ticker") == _top_pick), {})
    _top_conf   = _top_entry.get("confidence", "")
    _top_strat  = _top_entry.get("strategy", "")
    _top_reason = bi(_top_entry, "reasoning", _lang)
    _conf_c  = _CONF_COLOR.get(_top_conf, "#58a6ff")
    _strat_c = _STRAT_COLOR.get(_top_strat, "#58a6ff")
    _lbl_top = "最强推荐" if _lang == "zh" else "Top Pick"
    _lbl_str = "策略" if _lang == "zh" else "Strategy"
    _lbl_con = "置信度" if _lang == "zh" else "Confidence"

    st.markdown(
        f'<div style="background:{_ai_bg};border:2px solid {_conf_c};'
        f'border-radius:10px;padding:16px 22px;margin-bottom:14px">'
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">'
        f'<span style="font-size:1.5rem;font-weight:700;color:{_conf_c}">{_top_pick}</span>'
        f'<span style="background:{_ai_bd};padding:2px 10px;border-radius:12px;'
        f'font-size:0.75rem;color:#8b949e">{_lbl_top}</span>'
        + (f'<span style="background:{_strat_c}22;border:1px solid {_strat_c};'
           f'padding:2px 10px;border-radius:12px;font-size:0.75rem;color:{_strat_c}">'
           f'{_lbl_str}: {_top_strat}</span>' if _top_strat else "")
        + (f'<span style="background:{_conf_c}22;border:1px solid {_conf_c};'
           f'padding:2px 10px;border-radius:12px;font-size:0.75rem;color:{_conf_c}">'
           f'{_lbl_con}: {_top_conf}</span>' if _top_conf else "")
        + f'</div>'
        + (f'<p style="font-size:0.88rem;line-height:1.65;color:{_ai_txt};margin:0">'
           f'{_top_reason}</p>' if _top_reason else "")
        + f'</div>',
        unsafe_allow_html=True,
    )

    # ── Other selected stocks ─────────────────────────────────────────────────
    others = [s for s in _selected if s.get("ticker") != _top_pick]
    if others or _runner_up:
        _lbl_others = "其他入选标的" if _lang == "zh" else "Other Selected Stocks"
        st.markdown(f"**{_lbl_others}**")

        # Runner-up not already in selected list
        if _runner_up and not any(s.get("ticker") == _runner_up for s in _selected):
            others = [{"ticker": _runner_up, "strategy": "", "confidence": "", "reasoning": ""}] + others

        for s in others[:4]:
            tk    = s.get("ticker", "")
            strat = s.get("strategy", "")
            conf  = s.get("confidence", "")
            rsn   = bi(s, "reasoning", _lang)
            sc    = _STRAT_COLOR.get(strat, "#58a6ff")
            cc    = _CONF_COLOR.get(conf, "#8b949e")
            st.markdown(
                f'<div style="background:{_ai_bg};border-left:3px solid {sc};'
                f'border-radius:0 6px 6px 0;padding:8px 14px;margin:5px 0">'
                f'<span style="font-weight:700;color:{sc};font-size:0.95rem">{tk}</span>'
                + (f'&nbsp;<span style="background:{sc}22;border:1px solid {sc};'
                   f'padding:1px 8px;border-radius:10px;font-size:0.72rem;color:{sc};'
                   f'margin-left:6px">{strat}</span>' if strat else "")
                + (f'&nbsp;<span style="color:{cc};font-size:0.72rem;margin-left:6px">'
                   f'{conf}</span>' if conf else "")
                + (f'<p style="font-size:0.84rem;color:{_ai_txt};margin:4px 0 0;'
                   f'line-height:1.55">{rsn}</p>' if rsn else "")
                + f'</div>',
                unsafe_allow_html=True,
            )

    # ── Overall reasoning ─────────────────────────────────────────────────────
    if _scan_reason and "unavailable" not in _scan_reason.lower():
        _lbl_rsn = "综合选股逻辑" if _lang == "zh" else "Overall Rationale"
        st.markdown(
            f'<div style="background:{_ai_bg};border:1px solid {_ai_bd};'
            f'border-radius:6px;padding:10px 16px;margin-top:8px">'
            f'<div style="font-size:0.75rem;color:#8b949e;margin-bottom:4px">'
            f'{_lbl_rsn}</div>'
            f'<p style="font-size:0.88rem;line-height:1.65;color:{_ai_txt};margin:0">'
            f'{_scan_reason}</p></div>',
            unsafe_allow_html=True,
        )

    # ── Strategy hit counts ───────────────────────────────────────────────────
    _sr = _wf_scan_res.get("strategy_results") or {}
    if _sr:
        _lbl_hits = "各策略命中" if _lang == "zh" else "Strategy Hit Counts"
        st.caption(
            f"{_lbl_hits}: " + "  ·  ".join(
                f"**{s}** {len(v)}" for s, v in _sr.items()
            )
        )

st.divider()

# ── Default tech pool (S&P 500 top 20 tech) ───────────────────────────────────
DEFAULT_POOL = (
    "AAPL, MSFT, NVDA, AVGO, META, ORCL, CRM, AMD, QCOM, TXN, "
    "AMAT, KLAC, LRCX, MU, ADI, NOW, PANW, SNPS, CDNS, INTC"
)

# Canonical English strategy codes (used internally for filtering / caching)
_STRAT_CODES   = ["Momentum", "Value", "Quality Growth", "Oversold Bounce"]
# Displayed labels (language-aware)
_STRAT_DISPLAY = [
    t("p3_strat_momentum"),
    t("p3_strat_value"),
    t("p3_strat_quality"),
    t("p3_strat_oversold"),
]

# ── Scanner linkage from Sector page ──────────────────────────────────────────
if st.session_state.get("scanner_trigger"):
    _injected_pool = st.session_state.get("scanner_pool", "")
    st.session_state["scanner_trigger"] = False
    if _injected_pool:
        st.session_state["_scanner_pool_prefill"] = _injected_pool
        st.info(f"📥 Pool pre-filled from Sector page ({len([t for t in _injected_pool.split(',') if t.strip()])} tickers)")

# ── Workflow state linkage ─────────────────────────────────────────────────────
if "_scanner_pool_prefill" not in st.session_state:
    _wf_pool = (
        st.session_state.get("research_state", {})
        .get("results", {})
        .get("scan", {}) or {}
    ).get("pool")
    if _wf_pool:
        st.session_state["_scanner_pool_prefill"] = _wf_pool

_default_pool = st.session_state.pop("_scanner_pool_prefill", DEFAULT_POOL)

# ── Settings ──────────────────────────────────────────────────────────────────
col_pool, col_params = st.columns([3, 2])

with col_pool:
    st.subheader(t("p3_pool"))
    pool_input = st.text_area(
        t("p3_pool_input"),
        value=_default_pool,
        height=120,
        help=t("p3_pool_help"),
    )
    pool_tickers = [tk.strip().upper() for tk in pool_input.replace("\n", ",").split(",") if tk.strip()]
    st.caption(f"{len(pool_tickers)} tickers: {', '.join(pool_tickers)}")

with col_params:
    st.subheader(t("p3_strategy"))
    _strat_display_choice = st.selectbox(t("p3_strat_lbl"), _STRAT_DISPLAY)
    # Convert displayed label back to canonical code
    strategy = _STRAT_CODES[_STRAT_DISPLAY.index(_strat_display_choice)]

    period = st.selectbox(t("p3_period"), ["6mo","1y","2y"], index=1)
    top_n  = st.slider(t("p3_top_n"), min_value=5, max_value=len(pool_tickers), value=min(15, len(pool_tickers)))

run_btn = st.button(t("p3_run"), type="primary", use_container_width=True)
st.divider()

# ── Scanner logic ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def run_scan(tickers: tuple, strategy: str, period: str) -> list[dict]:
    """Run the scan for the given tickers, strategy code, and period.
    Column names are always English (language-independent) for caching consistency."""
    sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
    from technical import snapshot

    results = []
    prog = st.progress(0, text="Scanning...")
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        prog.progress((i + 1) / total, text=f"Scanning {ticker} ({i+1}/{total})...")
        try:
            df = load_ohlcv(ticker, period)
            if df is None or len(df) < 60:
                continue
            snap = snapshot(df)
            price = snap["price"]

            # Common metrics
            ret_1m  = (df["Close"].iloc[-1] / df["Close"].iloc[-21]  - 1) * 100 if len(df) >= 21  else None
            ret_3m  = (df["Close"].iloc[-1] / df["Close"].iloc[-63]  - 1) * 100 if len(df) >= 63  else None
            ret_6m  = (df["Close"].iloc[-1] / df["Close"].iloc[-126] - 1) * 100 if len(df) >= 126 else None
            vol_ann = df["Close"].pct_change().std() * (252 ** 0.5) * 100

            # Strategy filters (canonical English codes)
            passes = False
            if strategy == "Momentum":
                passes = (
                    snap["above_SMA200"] and
                    50 <= snap.get("RSI_14", 0) <= 72 and
                    snap.get("Vol_ratio_20d", 0) >= 1.1 and
                    (ret_3m or 0) > 0
                )
            elif strategy == "Value":
                try:
                    info_v = load_info(ticker)
                    pe = info_v.get("trailingPE")
                    passes = pe is not None and pe < 20 and snap.get("RSI_14", 50) < 55
                except Exception:
                    passes = snap.get("RSI_14", 50) < 45
            elif strategy == "Quality Growth":
                passes = (
                    snap["above_SMA200"] and
                    snap.get("ADX", 0) > 20 and
                    (ret_3m or 0) > 5
                )
            elif strategy == "Oversold Bounce":
                passes = (
                    snap.get("RSI_14", 50) < 38 and
                    snap["above_SMA200"]
                )

            if passes:
                try:
                    info_r = load_info(ticker)
                    name   = info_r.get("shortName", ticker)
                    mktcap = info_r.get("marketCap", 0)
                    sector = info_r.get("sector", "N/A")
                    pe     = info_r.get("trailingPE")
                    fwd_pe = info_r.get("forwardPE")
                except Exception:
                    name, mktcap, sector, pe, fwd_pe = ticker, 0, "N/A", None, None

                # Always store with English column names for caching consistency
                results.append({
                    "Ticker":          ticker,
                    "Company":         name,
                    "Sector":          sector,
                    "Price($)":        round(price, 2),
                    "RSI(14)":         snap.get("RSI_14"),
                    "ADX":             snap.get("ADX"),
                    "1M Ret%":         round(ret_1m, 1) if ret_1m else None,
                    "3M Ret%":         round(ret_3m, 1) if ret_3m else None,
                    "6M Ret%":         round(ret_6m, 1) if ret_6m else None,
                    "52W High%":       snap.get("pct_from_52w_high"),
                    "Vol Ratio(20D)":  snap.get("Vol_ratio_20d"),
                    "Ann. Vol%":       round(vol_ann, 1),
                    "Mkt Cap(B)":      round(mktcap / 1e9, 1) if mktcap else None,
                    "P/E":             round(pe, 1) if pe else None,
                    "Fwd P/E":         round(fwd_pe, 1) if fwd_pe else None,
                })
        except Exception:
            continue

    prog.empty()

    # Sort by strategy (English codes)
    sort_key = "3M Ret%" if strategy == "Momentum" else "RSI(14)"
    results.sort(key=lambda x: (x.get(sort_key) or -9999), reverse=(strategy in ("Momentum", "Quality Growth")))
    return results


# ── Run or show cached ────────────────────────────────────────────────────────
cache_key = f"scan_{strategy}_{period}_{','.join(sorted(pool_tickers))}"

if run_btn:
    st.session_state["scan_results"] = None  # force re-run
    st.session_state["scan_cache_key"] = ""

if st.session_state.get("scan_cache_key") == cache_key and st.session_state.get("scan_results"):
    results = st.session_state["scan_results"]
    st.success(f"✅ {len(results)} hits cached — change params and click Scan to re-run")
elif run_btn:
    with st.spinner("Scanning..."):
        results = run_scan(tuple(pool_tickers), strategy, period)
    st.session_state["scan_results"] = results
    st.session_state["scan_cache_key"] = cache_key
    st.success(f"✅ {len(pool_tickers)} scanned → {len(results)} hits")
else:
    st.info(t("p3_start_hint"))
    st.stop()

if not results:
    st.warning(t("p3_no_result"))
    st.stop()

# ── Results ───────────────────────────────────────────────────────────────────
top_results = results[:top_n]
df_results  = pd.DataFrame(top_results)

# Summary bar — always reference English column names internally
c1, c2, c3 = st.columns(3)
c1.metric(t("p3_hits"),    len(results))
c2.metric(t("p3_avg3m"),   f"{pd.Series([r.get('3M Ret%') for r in results if r.get('3M Ret%')]).mean():.1f}%")
c3.metric(t("p3_avg_rsi"), f"{pd.Series([r.get('RSI(14)') for r in results if r.get('RSI(14)')]).mean():.1f}")
st.divider()

# Language-aware column rename map for display
_COL_ZH = {
    "Company":        t("p3_col_company"),
    "Sector":         t("p3_col_sector"),
    "Price($)":       t("p3_col_price"),
    "1M Ret%":        t("p3_col_ret1m"),
    "3M Ret%":        t("p3_col_ret3m"),
    "6M Ret%":        t("p3_col_ret6m"),
    "Vol Ratio(20D)": t("p3_col_volratio"),
    "Ann. Vol%":      t("p3_col_annvol"),
    "Mkt Cap(B)":     t("p3_col_mktcap"),
}
display_df = df_results.rename(columns=_COL_ZH)

# Results table
st.subheader(f"Top {top_n}")
render_table(
    display_df.set_index("Ticker"),
    height=min(400, 50 + len(top_results) * 38),
)
st.divider()

# ── Bubble chart ──────────────────────────────────────────────────────────────
_col_ret3m = _COL_ZH["3M Ret%"]
_col_rsi   = "RSI(14)"
_col_mkt   = _COL_ZH["Mkt Cap(B)"]
_col_sec   = _COL_ZH["Sector"]
_col_co    = _COL_ZH["Company"]
_col_px    = _COL_ZH["Price($)"]

st.subheader(f"{_col_ret3m} vs {_col_rsi} (bubble = {_col_mkt})")
plot_df = display_df.dropna(subset=[_col_ret3m, _col_rsi])

if not plot_df.empty:
    fig = px.scatter(
        plot_df,
        x=_col_ret3m,
        y=_col_rsi,
        size=[max(v, 1) for v in plot_df[_col_mkt].fillna(1)],
        color=_col_sec,
        text="Ticker",
        hover_data={_col_co: True, _col_px: True, "P/E": True,
                    _col_ret3m: True, _col_rsi: True, _col_mkt: True},
        size_max=60,
    )
    fig.add_hline(y=70, line_dash="dash", line_color="red",   opacity=0.5, annotation_text="Overbought(70)")
    fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5, annotation_text="Oversold(30)")
    fig.add_vline(x=0,  line_dash="dash", line_color="gray",  opacity=0.4)
    fig.update_traces(textposition="top center", textfont_size=11)
    apply_layout(fig, title=f"{_col_ret3m} vs {_col_rsi}", height=480)
    apply_legend(fig)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Download ──────────────────────────────────────────────────────────────────
col_dl1, col_dl2 = st.columns(2)
with col_dl1:
    csv_data = display_df.to_csv(index=False)
    st.download_button(t("p3_dl_csv"), csv_data,
                       f"{datetime.now().strftime('%Y%m%d')}_scan_{strategy[:10].replace(' ','_')}.csv", "text/csv")
with col_dl2:
    today = datetime.now().strftime("%Y-%m-%d")
    md_lines = [
        f"# {'Stock Scan' if _lang == 'en' else '选股扫描'}: {_strat_display_choice}",
        f"",
        f"**{'Date' if _lang=='en' else '日期'}**: {today}  |  "
        f"**{'Pool' if _lang=='en' else '股票池'}**: {len(pool_tickers)}  |  "
        f"**{'Hits' if _lang=='en' else '命中'}**: {len(results)}",
        f"",
        f"| Ticker | Price | RSI | ADX | 3M Ret | Mkt Cap |",
        f"|--------|-------|-----|-----|--------|---------|",
    ]
    for r in top_results:
        md_lines.append(
            f"| {r['Ticker']} | ${r['Price($)']} | {r['RSI(14)']} | {r['ADX']} "
            f"| {r.get('3M Ret%','N/A')}% | {r.get('Mkt Cap(B)','N/A')}B |"
        )
    _disclaimer = ("> **Disclaimer**: For research purposes only. Not investment advice."
                   if _lang == "en" else
                   "> **风险提示**：本报告仅供研究参考，不构成投资建议。")
    md_lines += ["", _disclaimer]
    report_md = "\n".join(md_lines)

    # Save to research/scans/
    scan_path = (Path(__file__).parent.parent / "research" / "scans" /
                 f"{datetime.now().strftime('%Y%m%d')}_scan_{strategy[:12].replace(' ','_')}.md")
    scan_path.parent.mkdir(parents=True, exist_ok=True)
    scan_path.write_text(report_md, encoding="utf-8")

    download_report_button(report_md, scan_path.name, t("p3_dl_md"))
