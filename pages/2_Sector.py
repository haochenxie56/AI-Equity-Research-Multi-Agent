"""Page 2 — Sector Analysis & Rotation (v4.1)

Sections:
  0  Macro Environment     — VIX / 10Y yield / DXY / SPX cards with interpretation
  1  Rotation Signal       — Risk-On / Neutral / Risk-Off + Top3 + accelerating
                             + Sector Valuation (median Fwd P/E horizontal bar)
  2  Sector Heat Map       — period-aware composite score bar chart (11 GICS)
  3  ETF Trend vs SPY      — normalised return for selected sector
                             + Volume Flow (3M relative vol for all 11 ETFs)
  4  Stock Ranking         — Leader / Challenger / Sleeper tier cards
                             + Send to Scanner button
  5  Sub-sectors           — A: cross-sub-sector comparison heatmap (Layer 2 ETFs vs SPY,
                                period-aware 1M/3M/6M/1Y radio)
                             B: styled stock table within chosen sub-sector
"""

import sys
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from ui_utils import (
    apply_theme, render_sidebar, load_ohlcv,
    apply_layout, apply_legend, fmt_large, page_header, render_table, t,
    render_workflow_bar,
)
from sectors import (
    SECTOR_CONFIG, THEME_ETF_CONFIG, CUSTOM_THEME_CONFIG,
    get_theme_constituents,
)
from rotation import (
    compute_sector_scores, classify_rotation_phase,
    rank_sector_stocks, compute_subsector_scores,
    compute_volume_flow, compute_sector_valuation, get_macro_indicators,
)

st.set_page_config(page_title="Sector Analysis", page_icon="🏭", layout="wide")
apply_theme()
render_sidebar()

_lang = st.session_state.get("language", "en")
_dark = st.session_state.get("dark_mode", True)

# ── AI analysis results from workflow state ───────────────────────────────────
_wf_sector_res = (
    st.session_state.get("research_state", {})
    .get("results", {})
    .get("sector") or {}
)
_sec_llm  = _wf_sector_res.get("llm") or {}
_has_llm  = bool(_sec_llm.get("macro") or _sec_llm.get("rotation"))
_wf_sector_name = st.session_state.get("research_state", {}).get("sector", "")

_ai_bg = "#161b22" if _dark else "#f6f8fa"
_ai_bd = "#30363d" if _dark else "#d0d7de"
_ai_txt = "#e6edf3" if _dark else "#1f2328"


def _ai_block(text: str, title: str) -> None:
    """Render one LLM analysis paragraph with a numbered sub-title."""
    if not text or "unavailable" in text.lower():
        return
    st.markdown(
        f'<div style="background:{_ai_bg};border-left:3px solid #388bfd;'
        f'border-radius:0 6px 6px 0;padding:10px 16px;margin:8px 0 18px">'
        f'<div style="font-size:0.78rem;font-weight:600;color:#58a6ff;'
        f'margin-bottom:6px">{title}</div>'
        f'<p style="font-size:0.92rem;line-height:1.72;color:{_ai_txt};margin:0">'
        f'{text}</p></div>',
        unsafe_allow_html=True,
    )


def _ai_hint() -> None:
    """Compact prompt shown when no workflow LLM results are available."""
    lbl = (
        "尚无 AI 分析 · 请先在 [总览页](/Overview) 运行 AI 研究工作流"
        if _lang == "zh" else
        "No AI analysis yet · Run the AI Research Workflow on the [Overview](/Overview) page first"
    )
    st.markdown(
        f'<div style="background:{_ai_bg};border:1px dashed {_ai_bd};'
        f'border-radius:6px;padding:8px 14px;margin:6px 0 18px;'
        f'font-size:0.82rem;color:#8b949e">'
        f'🤖 {lbl}</div>',
        unsafe_allow_html=True,
    )


st.title(t("p2_title"))
page_header()
render_workflow_bar()
st.caption(t("p2_subtitle"))
st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 0 — Macro Environment Indicators
# ══════════════════════════════════════════════════════════════════════════════
_macro = get_macro_indicators()

def _macro_card(col, key: str, label_key: str, fmt: str, interp_fn) -> None:
    """Render one macro indicator card into a Streamlit column."""
    d = _macro.get(key, {})
    cur  = d.get("current")
    chg  = d.get("change5d")
    pct  = d.get("change5d_pct")
    with col:
        st.markdown(f"**{t(label_key)}**")
        if cur is None:
            st.caption("—")
            return
        val_str = fmt.format(cur)
        st.markdown(f"### {val_str}")
        if chg is not None:
            sign  = "+" if chg >= 0 else ""
            color = "#3fb950" if chg <= 0 else "#f85149"   # green=down for risk measures
            if key in ("SPX",):                             # SPX: green = up
                color = "#3fb950" if chg >= 0 else "#f85149"
            st.markdown(
                f"<span style='color:{color}'>{sign}{chg:.2f} "
                f"({sign}{pct:.1f}%)</span>  ·  {t('p2_macro_5d')}",
                unsafe_allow_html=True,
            )
        st.caption(interp_fn(cur, chg))

def _vix_interp(cur, chg):
    if cur is None: return ""
    if cur > 25: return t("p2_macro_vix_fear")
    if cur < 15: return t("p2_macro_vix_calm")
    return t("p2_macro_vix_mid")

def _tnx_interp(cur, chg):
    if chg is None: return t("p2_macro_tnx_flat")
    if chg > 0.05:  return t("p2_macro_tnx_up")
    if chg < -0.05: return t("p2_macro_tnx_down")
    return t("p2_macro_tnx_flat")

def _dxy_interp(cur, chg):
    if chg is None: return t("p2_macro_dxy_flat")
    if chg > 0.3:   return t("p2_macro_dxy_up")
    if chg < -0.3:  return t("p2_macro_dxy_down")
    return t("p2_macro_dxy_flat")

def _spx_interp(cur, chg): return ""

st.subheader(t("p2_macro_title"))
_m1, _m2, _m3, _m4 = st.columns(4)
_macro_card(_m1, "VIX", "p2_macro_vix", "{:.1f}", _vix_interp)
_macro_card(_m2, "TNX", "p2_macro_tnx", "{:.2f}%", _tnx_interp)
_macro_card(_m3, "DXY", "p2_macro_dxy", "{:.1f}", _dxy_interp)
_macro_card(_m4, "SPX", "p2_macro_spx", "{:,.0f}", _spx_interp)

# ── AI: Macro Environment analysis ────────────────────────────────────────────
_macro_lbl = "① 宏观环境" if _lang == "zh" else "① Macro Environment"
if _has_llm:
    _ai_block(_sec_llm.get("macro", ""), _macro_lbl)
else:
    _ai_hint()

st.divider()


# ── Load scores (shared by rotation signal + heatmap) ────────────────────────
_period_map = {"1M": 21, "3M": 63, "6M": 126, "1Y": 252}

with st.spinner(t("p2_loading_scores")):
    # Default to 3M for the rotation signal; heatmap period chosen below
    scores_df = compute_sector_scores(63)

if scores_df.empty:
    st.error(
        "Failed to load sector ETF data. Please check your connection and try again."
    )
    st.stop()

# Build display labels (zh / en)
scores_df["label"] = scores_df.apply(
    lambda r: r["zh"] if _lang == "zh" else r["sector"], axis=1
)

# Helper: English sector key → current-language display label
def _sector_label(sec: str) -> str:
    row = scores_df[scores_df["sector"] == sec]
    return row["label"].iloc[0] if not row.empty else sec


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Rotation Signal  (top of page, before heatmap)
# ══════════════════════════════════════════════════════════════════════════════
with st.expander(t("p2_rotation_signal"), expanded=True):
    phase_info = classify_rotation_phase(scores_df)
    phase      = phase_info["phase"]

    _phase_color = {
        "risk_on":  "#3fb950",
        "neutral":  "#d29922",
        "risk_off": "#f85149",
    }[phase]
    _phase_label = {
        "risk_on":  t("p2_phase_risk_on"),
        "neutral":  t("p2_phase_neutral"),
        "risk_off": t("p2_phase_risk_off"),
    }[phase]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"**{t('p2_market_style')}**")
        st.markdown(
            f"<span style='color:{_phase_color}; font-size:1.5em; font-weight:bold'>"
            f"{_phase_label}</span>",
            unsafe_allow_html=True,
        )
        off = phase_info["offensive_score"]
        dfs = phase_info["defensive_score"]
        if not (pd.isna(off) or pd.isna(dfs)):
            st.caption(f"Offensive avg: {off:.1f}  |  Defensive avg: {dfs:.1f}")

    with c2:
        st.markdown(f"**{t('p2_top3')}**")
        for sec in phase_info["top3_sectors"]:
            row = scores_df[scores_df["sector"] == sec]
            if not row.empty:
                r = row.iloc[0]
                st.markdown(
                    f"- **{_sector_label(sec)}** &nbsp; "
                    f"`{r['score']:.0f}pts` &nbsp; `{r['primary_excess']:+.1f}%`"
                )

    with c3:
        st.markdown(f"**{t('p2_accelerating')}**")
        accel_list = phase_info["accelerating"]
        if accel_list:
            for sec in accel_list:
                row = scores_df[scores_df["sector"] == sec]
                if not row.empty:
                    r = row.iloc[0]
                    st.markdown(
                        f"- **{_sector_label(sec)}** &nbsp; `+{r['momentum_accel']:.2f}`"
                    )
        else:
            st.caption("—")

    # ── AI: Rotation Signal analysis ─────────────────────────────────────────
    _rot_lbl = "② 轮动信号" if _lang == "zh" else "② Rotation Signal"
    if _has_llm:
        _ai_block(_sec_llm.get("rotation", ""), _rot_lbl)
    else:
        _ai_hint()

    # ── Sector valuation (Fwd P/E median) ────────────────────────────────────
    st.markdown("---")
    st.markdown(f"**{t('p2_valuation')}**")
    with st.spinner(t("p2_val_loading")):
        val_df = compute_sector_valuation()

    if val_df.empty:
        st.caption(t("p2_val_unavail"))
    else:
        val_df["label"] = val_df.apply(
            lambda r: r["zh"] if _lang == "zh" else r["sector"], axis=1
        )
        # Colorscale: low P/E → green, high P/E → red
        pe_min, pe_max = val_df["median_fwd_pe"].min(), val_df["median_fwd_pe"].max()
        pe_range = max(pe_max - pe_min, 1.0)

        def _pe_color(pe: float) -> str:
            norm = (pe - pe_min) / pe_range          # 0=cheap → 1=expensive
            r = int(min(255, norm * 2 * 255))
            g = int(min(255, (1 - norm) * 2 * 255))
            return f"rgb({r},{g},60)"

        fig_val = go.Figure(go.Bar(
            x=val_df["median_fwd_pe"],
            y=val_df["label"],
            orientation="h",
            marker_color=[_pe_color(p) for p in val_df["median_fwd_pe"]],
            text=[
                f"{r['median_fwd_pe']:.1f}x"
                + (f"  (n={r['n_stocks']})" if r["pe_source"] == "fwd"
                   else "  (ETF trailing)")
                for _, r in val_df.iterrows()
            ],
            textposition="outside",
            hovertemplate=(
                "<b>%{y}</b><br>"
                "P/E: %{x:.1f}x<br>"
                "Source: %{customdata[0]}<br>"
                "Stocks sampled: %{customdata[1]}<extra></extra>"
            ),
            customdata=val_df[["pe_source", "n_stocks"]].values,
        ))
        _val_h = max(220, len(val_df) * 32 + 60)
        apply_layout(fig_val, title="", height=_val_h)
        apply_legend(fig_val)
        fig_val.update_layout(
            xaxis=dict(title="Fwd P/E", rangemode="tozero"),
            yaxis=dict(autorange="reversed"),
            margin=dict(l=180, r=20, t=30, b=20),
        )
        st.plotly_chart(fig_val, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Sector Heat Map
# ══════════════════════════════════════════════════════════════════════════════
with st.expander(t("p2_heatmap"), expanded=True):
    st.caption(t("p2_heatmap_subtitle"))

    # ── Period selector: recompute scores with selected window ────────────────
    heat_period = st.radio(
        "", list(_period_map.keys()), index=1,
        horizontal=True, key="p2_heat_period",
        label_visibility="collapsed",
    )
    heat_days = _period_map[heat_period]

    if heat_days != 63:
        with st.spinner(t("p2_loading_scores")):
            scores_df = compute_sector_scores(heat_days)
        scores_df["label"] = scores_df.apply(
            lambda r: r["zh"] if _lang == "zh" else r["sector"], axis=1
        )

    # ── Bar text: selected period excess + RSI + score ────────────────────────
    def _bar_text(r: pd.Series) -> str:
        exc = r.get("primary_excess")
        rsi = r.get("rsi")
        sc  = r.get("score")
        if pd.isna(sc) if sc is not None else True:
            return "—"
        if exc is not None and not pd.isna(exc) and rsi is not None and not pd.isna(rsi):
            return f"{heat_period}: {exc:+.1f}%  RSI: {rsi:.0f}  ▶ {sc:.0f}"
        return f"▶ {sc:.0f}"

    # ── Horizontal bar chart ──────────────────────────────────────────────────
    fig_heat = go.Figure(go.Bar(
        x=scores_df["score"],
        y=scores_df["label"],
        orientation="h",
        marker_color=scores_df["color"].tolist(),
        text=[_bar_text(r) for _, r in scores_df.iterrows()],
        textposition="outside",
        hovertemplate=(
            "<b>%{y}</b><br>"
            f"Score ({heat_period}): %{{x:.1f}}<br>"
            "Primary Excess: %{customdata[0]:+.1f}%<br>"
            "1M Excess: %{customdata[1]:+.1f}%<br>"
            "3M Excess: %{customdata[2]:+.1f}%<br>"
            "RSI(14): %{customdata[3]}<br>"
            "From 52W High: %{customdata[4]:.1f}%<extra></extra>"
        ),
        customdata=scores_df[[
            "primary_excess", "1m_excess", "3m_excess", "rsi", "from_52w_high"
        ]].values,
    ))
    apply_layout(fig_heat, title="", height=440)
    apply_legend(fig_heat)
    fig_heat.update_layout(
        xaxis=dict(range=[0, 115]),
        yaxis=dict(autorange="reversed"),
        margin=dict(l=180, r=20, t=50, b=20),
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    # ── AI: Sector Momentum analysis ─────────────────────────────────────────
    _mom_lbl = "③ 板块动量对比" if _lang == "zh" else "③ Sector Momentum"
    if _has_llm:
        _ai_block(_sec_llm.get("momentum", ""), _mom_lbl)
    else:
        _ai_hint()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — ETF Trend vs SPY
# ══════════════════════════════════════════════════════════════════════════════

# Sector + period selectors live outside the expander so their values are
# always resolved (Streamlit still executes expander contents when collapsed,
# but keeping them outside avoids any edge-case ordering surprises).
sector_names = scores_df["sector"].tolist()
_is_zh = (_lang == "zh")

# Pre-fill from workflow state on first visit (only if user hasn't already selected)
_wf_sector = st.session_state.get("research_state", {}).get("sector")
if _wf_sector and _wf_sector in sector_names and "p2_sector_key" not in st.session_state:
    st.session_state["p2_sector_key"] = _wf_sector
    st.session_state["p2_sector_sel"] = SECTOR_CONFIG[_wf_sector]["zh"] if _is_zh else _wf_sector
    st.session_state["_p2_sector_lang"] = _lang

# On language switch: rewrite the stored display string to the new language
# equivalent BEFORE the selectbox renders.
if st.session_state.get("_p2_sector_lang") != _lang:
    _eng = st.session_state.get("p2_sector_key", sector_names[0])
    if _eng not in sector_names:
        _eng = sector_names[0]
    st.session_state["p2_sector_sel"] = SECTOR_CONFIG[_eng]["zh"] if _is_zh else _eng
    st.session_state["_p2_sector_lang"] = _lang

sector_display = [SECTOR_CONFIG[s]["zh"] if _is_zh else s for s in sector_names]

with st.expander(t("p2_etf_trend"), expanded=True):
    col_sel, col_period = st.columns([3, 1])
    with col_sel:
        _sel_display = st.selectbox(
            t("p2_select_sector"),
            options=sector_display,
            key="p2_sector_sel",
            accept_new_options=False,
        )
    with col_period:
        period = st.selectbox(
            t("p2_period"),
            ["1mo", "3mo", "6mo", "1y"],
            index=3,
            format_func=lambda x: {"1mo": "1M", "3mo": "3M", "6mo": "6M", "1y": "1Y"}[x],
            key="p2_period_sel",
            accept_new_options=False,
        )

    sel_sector = sector_names[sector_display.index(_sel_display)]
    st.session_state["p2_sector_key"] = sel_sector          # persist English key
    sel_label  = SECTOR_CONFIG[sel_sector]["zh"] if _is_zh else sel_sector
    etf_ticker = SECTOR_CONFIG[sel_sector]["etf"]
    etf_color  = SECTOR_CONFIG[sel_sector]["color"]

    st.subheader(f"**{etf_ticker}** vs SPY")

    with st.spinner(f"Loading {etf_ticker} & SPY..."):
        etf_df = load_ohlcv(etf_ticker, period)
        spy_df = load_ohlcv("SPY", period)

    if not etf_df.empty and not spy_df.empty:
        fig_trend = go.Figure()
        for tk, df, color, width in [
            (etf_ticker, etf_df, etf_color, 2.5),
            ("SPY",      spy_df, "#8b949e", 1.5),
        ]:
            norm = df["Close"] / df["Close"].iloc[0] * 100
            fig_trend.add_trace(go.Scatter(
                x=df.index, y=norm, name=tk,
                line=dict(color=color, width=width),
                hovertemplate=f"{tk}: %{{y:.1f}}<extra></extra>",
            ))
        fig_trend.add_hline(y=100, line_dash="dash", line_color="gray", opacity=0.4)
        apply_layout(fig_trend, title=f"{t('p2_norm_return')} (Base = 100)", height=380)
        apply_legend(fig_trend)
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.warning(t("p2_insufficient"))

    # ── AI: ETF Trend analysis ────────────────────────────────────────────────
    _etf_lbl = "④ ETF 走势对比" if _lang == "zh" else "④ ETF Trend vs SPY"
    if _has_llm:
        _ai_block(_sec_llm.get("etf_trend", ""), _etf_lbl)
    else:
        _ai_hint()

    # ── Volume Flow: 3-month relative volume for all 11 sector ETFs ──────────
    st.markdown("---")
    st.markdown(f"**{t('p2_vol_flow')}**")
    with st.spinner(t("p2_vol_flow")):
        vol_df = compute_volume_flow()

    if vol_df.empty:
        st.caption(t("p2_vol_unavail"))
    else:
        # Latest vol ratio per sector (for ranking annotation)
        latest_vr = (
            vol_df.sort_values("date")
            .groupby("sector")
            .last()
            .reset_index()[["sector", "etf", "color", "zh", "vol_ratio"]]
            .sort_values("vol_ratio", ascending=False)
        )

        # Highlight set: vol_ratio >= 1.5 OR top-3 by latest ratio
        # (top-3 ensures at least some highlighted traces even in quiet markets)
        _top3_sectors = set(latest_vr.head(3)["sector"].tolist())

        fig_vol = go.Figure()
        # Render active (highlighted) traces first so they sit on top visually;
        # inactive traces are hidden by default (visible="legendonly") but keep
        # their original sector colour — clicking the legend entry reveals them.
        for group_pass in ("active", "others"):
            for _, sec_row in latest_vr.iterrows():
                sec          = sec_row["sector"]
                latest_ratio = sec_row["vol_ratio"]
                is_active    = latest_ratio >= 1.5 or sec in _top3_sectors
                if (group_pass == "active") != is_active:
                    continue

                sec_data = vol_df[vol_df["sector"] == sec].sort_values("date")
                if sec_data.empty:
                    continue
                label = sec_row["zh"] if _lang == "zh" else sec

                fig_vol.add_trace(go.Scatter(
                    x=sec_data["date"],
                    y=sec_data["vol_ratio"],
                    name=label,
                    mode="lines",
                    opacity=1.0,
                    line=dict(color=sec_row["color"], width=2.5),
                    showlegend=True,
                    visible=True if is_active else "legendonly",
                    hovertemplate=f"{label}: %{{y:.2f}}x<extra></extra>",
                ))

        fig_vol.add_hline(y=1.0, line_dash="dot",  line_color="gray",   opacity=0.5)
        fig_vol.add_hline(y=1.5, line_dash="dash", line_color="#f85149", opacity=0.6,
                          annotation_text="1.5x", annotation_position="left")
        apply_layout(fig_vol, title="", height=400)
        apply_legend(fig_vol)
        fig_vol.update_layout(
            yaxis=dict(title=t("p2_vol_ratio"), rangemode="tozero"),
            margin=dict(l=20, r=160, t=30, b=20),   # extra right margin for legend
        )
        st.plotly_chart(fig_vol, use_container_width=True)
        st.caption(t("p2_vol_click_hint"))

        # Active sectors annotation
        breakouts = latest_vr[
            (latest_vr["vol_ratio"] >= 1.5) |
            (latest_vr["sector"].isin(_top3_sectors))
        ]
        if not breakouts.empty:
            _blabels = [
                f"**{r['zh'] if _lang == 'zh' else r['sector']}** `{r['vol_ratio']:.2f}x`"
                for _, r in breakouts.iterrows()
            ]
            st.caption(f"{t('p2_vol_breakout')}: " + "  ·  ".join(_blabels))

    # ── AI: Volume Flow analysis ──────────────────────────────────────────────
    _vf_lbl = "⑤ 资金流入信号" if _lang == "zh" else "⑤ Volume Flow"
    if _has_llm:
        _ai_block(_sec_llm.get("volume_flow", ""), _vf_lbl)
    else:
        _ai_hint()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Intra-Sector Stock Ranking  (+ Section 5: Send to Scanner)
# ══════════════════════════════════════════════════════════════════════════════
with st.expander(f"{t('p2_stock_ranking')}: {sel_label}", expanded=True):
    with st.spinner(t("p2_loading_stocks")):
        constituents = get_theme_constituents(sel_sector)

    if not constituents:
        st.warning(t("p2_no_constituents"))
    else:
        st.caption(
            f"{len(constituents)} {t('p2_constituents_found')} — {t('p2_ranking_top30')}"
        )

        with st.spinner(t("p2_ranking_stocks")):
            ranked_df = rank_sector_stocks(tuple(constituents[:50]))

        if ranked_df.empty:
            st.warning(t("p2_rank_failed"))
        else:
            leaders     = ranked_df[ranked_df["tier"] == "Leader"]
            challengers = ranked_df[ranked_df["tier"] == "Challenger"]
            sleepers    = ranked_df[ranked_df["tier"] == "Sleeper"]

            def _stars(rsi: float) -> str:
                if rsi >= 65:   return "★★★★★"
                elif rsi >= 55: return "★★★★"
                elif rsi >= 45: return "★★★"
                else:           return "★★"

            def _tier_card(df_tier: pd.DataFrame, title: str, border_color: str) -> None:
                st.markdown(
                    f"<div style='border-left:3px solid {border_color};"
                    f" padding:4px 0 4px 10px; margin-bottom:6px;'>"
                    f"<b>{title}</b> &nbsp;<span style='color:{border_color}'>"
                    f"({len(df_tier)})</span></div>",
                    unsafe_allow_html=True,
                )
                for _, row in df_tier.head(8).iterrows():
                    ret3_str = f"{row['3m_ret']:+.1f}%" if row["3m_ret"] is not None else "N/A"
                    pe_str   = f" · PE {row['fwd_pe']:.0f}x" if row["fwd_pe"] else ""
                    st.markdown(
                        f"**{row['ticker']}** {_stars(row['rsi'])}  "
                        f"`{row['name'][:22]}`  \n"
                        f"1M {row['1m_ret']:+.1f}% · 3M {ret3_str} · "
                        f"RSI {row['rsi']} · {fmt_large(row['mkt_cap'])}{pe_str}"
                    )

            col_lead, col_chal, col_sleep = st.columns(3)
            with col_lead:
                _tier_card(leaders,     t("p2_leader"),     "#3fb950")
            with col_chal:
                _tier_card(challengers, t("p2_challenger"), "#d29922")
            with col_sleep:
                _tier_card(sleepers,    t("p2_sleeper"),    "#8b949e")

            st.divider()

            if st.button(
                f"▶ {t('p2_send_scanner')} ({len(ranked_df)} tickers)",
                type="primary", key="p2_send_main",
            ):
                st.session_state["scanner_pool"]    = ", ".join(ranked_df["ticker"].tolist())
                st.session_state["scanner_trigger"] = True
                st.switch_page("pages/3_Scanner.py")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — Sub-sectors (Layer 2 & 3)
# ══════════════════════════════════════════════════════════════════════════════

# ── Styled stock table helper ─────────────────────────────────────────────────
def _render_styled_stocks(df_disp: pd.DataFrame) -> None:
    """
    Render a stock table with:
    - Ticker: monospace + themed blue
    - 1M/3M Ret%: green (≥0) / red (<0)
    """
    tk_c  = "#388bfd" if _dark else "#0969da"
    pos_c = "#3fb950"
    neg_c = "#f85149"
    bd    = "rgba(255,255,255,0.06)" if _dark else "rgba(0,0,0,0.06)"
    txt_c = "#e6edf3" if _dark else "#1f2328"
    hdr_c = "#8b949e"

    def _ret_td(v) -> str:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "<td style='text-align:right'>N/A</td>"
        c = pos_c if float(v) >= 0 else neg_c
        return f"<td style='text-align:right;color:{c}'>{float(v):+.1f}%</td>"

    cols = list(df_disp.columns)
    hdr  = "".join(
        f"<th style='padding:5px 10px;text-align:{'right' if c in ('1M Ret%','3M Ret%','RSI') else 'left'}"
        f";color:{hdr_c};font-weight:normal;border-bottom:1px solid {bd}'>{c}</th>"
        for c in cols
    )

    rows_html = []
    for idx, row in df_disp.iterrows():
        cells = []
        for col in cols:
            v = row[col]
            if col == "1M Ret%" or col == "3M Ret%":
                cells.append(_ret_td(None if pd.isna(v) else v))
            elif col == "RSI":
                cells.append(f"<td style='text-align:right;color:{txt_c}'>{v}</td>")
            else:
                cells.append(
                    f"<td style='padding:5px 10px;color:{txt_c}'>{v}</td>"
                )
        # Ticker cell (first, from index)
        ticker_cell = (
            f"<td style='padding:5px 10px;font-family:monospace;"
            f"font-weight:bold;color:{tk_c}'>{idx}</td>"
        )
        rows_html.append(
            f"<tr style='border-bottom:1px solid {bd}'>"
            f"{ticker_cell}{''.join(cells)}</tr>"
        )

    html = f"""<div style='overflow-x:auto'>
<table style='width:100%;border-collapse:collapse;font-size:13px'>
<thead><tr><th style='padding:5px 10px;text-align:left;color:{hdr_c};
font-weight:normal;border-bottom:1px solid {bd}'>Ticker</th>{hdr}</tr></thead>
<tbody>{''.join(rows_html)}</tbody>
</table></div>"""
    st.markdown(html, unsafe_allow_html=True)


with st.expander(t("p2_subsector_drill"), expanded=True):

    # ── Collect sub-sectors for the selected GICS sector ─────────────────────
    sub_options: dict[str, dict] = {}
    for name, cfg in THEME_ETF_CONFIG.items():
        if cfg["parent"] == sel_sector:
            label = cfg["zh"] if _lang == "zh" else name
            sub_options[name] = {"label": label, "layer": 2, "etf": cfg["etf"]}
    for name, cfg in CUSTOM_THEME_CONFIG.items():
        if cfg["parent"] == sel_sector:
            label = cfg["zh"] if _lang == "zh" else name
            sub_options[name] = {"label": label, "layer": 3, "etf": None}

    if not sub_options:
        st.caption(t("p2_no_subsectors"))
    else:
        # ══════════════════════════════════════════════════════════════════════
        # Part A — Cross-sub-sector comparison heatmap (Layer 2 ETFs only)
        # ══════════════════════════════════════════════════════════════════════
        st.subheader(t("p2_subsector_comparison"))

        # Period selector — same style as main heatmap radio
        _sub_period_map = {"1M": 21, "3M": 63, "6M": 126, "1Y": 252}
        sub_heat_period = st.radio(
            "", list(_sub_period_map.keys()), index=1,
            horizontal=True, key="p2_sub_heat_period",
            label_visibility="collapsed",
        )
        sub_heat_days = _sub_period_map[sub_heat_period]

        with st.spinner(t("p2_loading_scores")):
            subsec_df = compute_subsector_scores(sel_sector, sub_heat_days)

        if subsec_df.empty:
            st.caption("No Layer 2 thematic ETF data available for this sector.")
        else:
            # Display label: zh name or English name
            subsec_df["label"] = subsec_df.apply(
                lambda r: r["zh"] if _lang == "zh" else r["name"], axis=1
            )

            fig_comp = go.Figure(go.Bar(
                x=subsec_df["score"],
                y=subsec_df["label"],
                orientation="h",
                marker=dict(
                    color=subsec_df["score"].tolist(),
                    colorscale="RdYlGn",
                    cmin=0, cmax=100,
                    showscale=False,
                ),
                text=[
                    f"{sub_heat_period}: {r['primary_excess']:+.1f}%  "
                    f"RSI: {r['rsi']:.0f}  ▶ {r['score']:.0f}"
                    for _, r in subsec_df.iterrows()
                ],
                textposition="outside",
                hovertemplate=(
                    "<b>%{y}</b>  (%{customdata[0]})<br>"
                    "Score: %{x:.1f}<br>"
                    f"{sub_heat_period} vs SPY: %{{customdata[1]:+.1f}}%<br>"
                    "1M vs SPY: %{customdata[2]:+.1f}%<br>"
                    "3M vs SPY: %{customdata[3]:+.1f}%<br>"
                    "RSI(14): %{customdata[4]}<br>"
                    "From 52W High: %{customdata[5]:.1f}%<extra></extra>"
                ),
                customdata=subsec_df[[
                    "etf", "primary_excess", "1m_excess", "3m_excess",
                    "rsi", "from_52w_high"
                ]].values,
            ))
            _comp_h   = max(200, len(subsec_df) * 36 + 60)
            _comp_lbl = max(120, max((len(lbl) for lbl in subsec_df["label"]), default=8) * 8)
            apply_layout(fig_comp, title="", height=_comp_h)
            apply_legend(fig_comp)
            fig_comp.update_layout(
                xaxis=dict(range=[0, 120]),
                yaxis=dict(autorange="reversed"),
                margin=dict(l=_comp_lbl, r=20, t=40, b=20),
            )
            st.plotly_chart(fig_comp, use_container_width=True)

        st.divider()

        # ══════════════════════════════════════════════════════════════════════
        # Part B — Per-stock ranking within a chosen sub-sector
        # ══════════════════════════════════════════════════════════════════════
        sub_names   = list(sub_options.keys())
        # sub_options labels are already built in current language
        sub_display = [sub_options[k]["label"] for k in sub_names]

        # On language switch OR parent sector change: rewrite stored display
        # string to the new-language equivalent before rendering.
        _sub_cache_sig = f"{_lang}__{sel_sector}"
        if st.session_state.get("_p2_sub_cache") != _sub_cache_sig:
            _sub_eng = st.session_state.get("p2_sub_key", sub_names[0])
            if _sub_eng not in sub_names:
                _sub_eng = sub_names[0]
            st.session_state["p2_sub_sel"] = sub_options[_sub_eng]["label"]
            st.session_state["_p2_sub_cache"] = _sub_cache_sig

        _sel_sub_display = st.selectbox(
            t("p2_select_subsector"),
            options=sub_display,
            key="p2_sub_sel",
            accept_new_options=False,
        )
        sel_sub = sub_names[sub_display.index(_sel_sub_display)]
        st.session_state["p2_sub_key"] = sel_sub             # persist English key
        layer   = sub_options[sel_sub]["layer"]
        etf_sub = sub_options[sel_sub]["etf"]

        if layer == 2:
            st.caption(f"Layer 2 — ETF: **{etf_sub}**")
        else:
            st.caption(f"Layer 3 — {t('p2_custom_pool')}")

        # ── Stock ranking within selected sub-sector ──────────────────────────
        with st.spinner(t("p2_loading_stocks")):
            sub_tickers = get_theme_constituents(sel_sub)

        if not sub_tickers:
            st.info(t("p2_no_constituents"))
        else:
            preview = ", ".join(sub_tickers[:15])
            st.caption(
                f"{len(sub_tickers)} tickers: {preview}"
                + ("..." if len(sub_tickers) > 15 else "")
            )

            with st.spinner(t("p2_ranking_stocks")):
                sub_ranked = rank_sector_stocks(tuple(sub_tickers[:30]))

            if not sub_ranked.empty:

                # ── Styled stock table ────────────────────────────────────────
                _tier_map = {
                    "Leader":     t("p2_leader"),
                    "Challenger": t("p2_challenger"),
                    "Sleeper":    t("p2_sleeper"),
                }
                disp = sub_ranked[[
                    "ticker", "name", "1m_ret", "3m_ret", "rsi", "tier"
                ]].copy()
                disp["tier"] = disp["tier"].map(_tier_map).fillna(disp["tier"])
                disp.columns = ["Ticker", "Company", "1M Ret%", "3M Ret%", "RSI", "Tier"]
                _render_styled_stocks(disp.set_index("Ticker"))

                st.markdown("")  # spacing

                if st.button(
                    f"▶ {t('p2_send_scanner')} ({len(sub_ranked)} tickers)",
                    key="p2_send_sub",
                ):
                    st.session_state["scanner_pool"]    = ", ".join(sub_ranked["ticker"].tolist())
                    st.session_state["scanner_trigger"] = True
                    st.switch_page("pages/3_Scanner.py")

    # ── AI: Subsector analysis ────────────────────────────────────────────────
    _sub_lbl = "⑥ 子板块分析" if _lang == "zh" else "⑥ Subsector Analysis"
    if _has_llm:
        _ai_block(_sec_llm.get("subsector", ""), _sub_lbl)
    else:
        _ai_hint()


# ══════════════════════════════════════════════════════════════════════════════
# AI 综合研究结论
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
_conc_title = "🔍 AI 综合研究结论" if _lang == "zh" else "🔍 AI Comprehensive Sector Analysis"
st.subheader(_conc_title)

if not _has_llm:
    _ai_hint()
else:
    # Lazy synthesis: generated once per workflow run, cached in session_state
    _syn_key = f"sector_synthesis_{_wf_sector_name}_{_lang}"
    if st.session_state.get("_sector_syn_key") != _syn_key:
        st.session_state["_sector_synthesis"] = None
        st.session_state["_sector_syn_key"] = _syn_key

    if st.session_state.get("_sector_synthesis") is None:
        _spin_txt = "生成综合结论..." if _lang == "zh" else "Generating comprehensive analysis..."
        with st.spinner(_spin_txt):
            sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
            from llm_orchestrator import synthesize_sector_analysis
            st.session_state["_sector_synthesis"] = synthesize_sector_analysis(_sec_llm, _lang)

    _syn_data   = st.session_state["_sector_synthesis"] or {}
    _syn_conc   = _syn_data.get("conclusion", "") or _syn_data.get("reasoning", "")

    if _syn_conc and "unavailable" not in _syn_conc.lower():
        st.markdown(
            f'<div style="background:{_ai_bg};border:1px solid {_ai_bd};'
            f'border-radius:8px;padding:18px 22px;margin-top:4px">'
            f'<p style="font-size:0.95rem;line-height:1.82;color:{_ai_txt};margin:0">'
            f'{_syn_conc}</p></div>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("⚠️ " + (_syn_conc or ("综合结论生成失败" if _lang == "zh" else "Synthesis failed")))
