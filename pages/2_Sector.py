"""Page 2 — Sector Research & Rotation (v4)

Architecture:
  Section 1  Sector Heat Map          — 11 GICS sectors, composite score bar chart
  Section 2  Rotation Signal          — Risk-On / Neutral / Risk-Off + top3 + accelerating
  Section 3  ETF Trend vs SPY         — normalised return chart for selected sector
  Section 4  Stock Ranking            — Leader / Challenger / Sleeper tier cards
  Section 5  Send to Scanner          — push ranked tickers to page 3
  Section 6  Sub-Sector Drill-Down    — Layer 2 thematic ETFs + Layer 3 custom pools
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from ui_utils import (
    apply_theme, render_sidebar, load_ohlcv,
    apply_layout, apply_legend, fmt_large, page_header, render_table, t,
)
from sectors import (
    SECTOR_CONFIG, THEME_ETF_CONFIG, CUSTOM_THEME_CONFIG,
    get_theme_constituents,
)
from rotation import compute_sector_scores, classify_rotation_phase, rank_sector_stocks

st.set_page_config(page_title="Sector Research", page_icon="🏭", layout="wide")
apply_theme()
render_sidebar()

_lang = st.session_state.get("language", "en")
_dark = st.session_state.get("dark_mode", True)

st.title(t("p2_title"))
page_header()
st.caption(t("p2_subtitle"))
st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Sector Heat Map
# ══════════════════════════════════════════════════════════════════════════════
st.subheader(t("p2_heatmap"))
st.caption(t("p2_heatmap_subtitle"))

with st.spinner(t("p2_loading_scores")):
    scores_df = compute_sector_scores()

if scores_df.empty:
    st.error("Failed to load sector ETF data. Please check your connection and try again.")
    st.stop()

# Build display labels
scores_df["label"] = scores_df.apply(
    lambda r: r["zh"] if _lang == "zh" else r["sector"], axis=1
)

# ── Horizontal bar chart ──────────────────────────────────────────────────────
fig_heat = go.Figure(go.Bar(
    x=scores_df["score"],
    y=scores_df["label"],
    orientation="h",
    marker_color=scores_df["color"].tolist(),
    text=[
        f"1M: {r['1m_excess']:+.1f}%  3M: {r['3m_excess']:+.1f}%  RSI: {r['rsi']}  ▶ {r['score']:.0f}"
        for _, r in scores_df.iterrows()
    ],
    textposition="outside",
    hovertemplate=(
        "<b>%{y}</b><br>"
        "Score: %{x:.1f}<br>"
        "1M Excess: %{customdata[0]:+.1f}%<br>"
        "3M Excess: %{customdata[1]:+.1f}%<br>"
        "RSI(14): %{customdata[2]}<br>"
        "From 52W High: %{customdata[3]:.1f}%<extra></extra>"
    ),
    customdata=scores_df[["1m_excess", "3m_excess", "rsi", "from_52w_high"]].values,
))
apply_layout(fig_heat, title="", height=440)
apply_legend(fig_heat)
fig_heat.update_layout(
    xaxis=dict(range=[0, 115]),
    yaxis=dict(autorange="reversed"),
    margin=dict(l=180, r=20, t=50, b=20),
)
st.plotly_chart(fig_heat, use_container_width=True)

# ── Sector selector + period (drives all sections below) ─────────────────────
sector_labels = scores_df["label"].tolist()
sector_names  = scores_df["sector"].tolist()

col_sel, col_period = st.columns([3, 1])
with col_sel:
    sel_label  = st.selectbox(t("p2_select_sector"), sector_labels,
                              key="p2_sector_sel")
    sel_sector = sector_names[sector_labels.index(sel_label)]
with col_period:
    period = st.selectbox(
        t("p2_period"),
        ["1mo", "3mo", "6mo", "1y"],
        index=3,
        format_func=lambda x: {"1mo": "1M", "3mo": "3M", "6mo": "6M", "1y": "1Y"}[x],
        key="p2_period_sel",
    )

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Rotation Signal
# ══════════════════════════════════════════════════════════════════════════════
st.subheader(t("p2_rotation_signal"))

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


def _sector_label(sec: str) -> str:
    """Return display label for a sector name."""
    row = scores_df[scores_df["sector"] == sec]
    return row["label"].iloc[0] if not row.empty else sec


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
    st.caption(f"Offensive avg: {off}  |  Defensive avg: {dfs}")

with c2:
    st.markdown(f"**{t('p2_top3')}**")
    for sec in phase_info["top3_sectors"]:
        row = scores_df[scores_df["sector"] == sec]
        if not row.empty:
            r = row.iloc[0]
            st.markdown(
                f"- **{_sector_label(sec)}** &nbsp; "
                f"`{r['score']:.0f}pts` &nbsp; `{r['1m_excess']:+.1f}%`"
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

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — ETF Trend vs SPY
# ══════════════════════════════════════════════════════════════════════════════
etf_ticker = SECTOR_CONFIG[sel_sector]["etf"]
etf_color  = SECTOR_CONFIG[sel_sector]["color"]

st.subheader(f"{t('p2_etf_trend')}: **{etf_ticker}** vs SPY")

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

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Intra-Sector Stock Ranking
# ══════════════════════════════════════════════════════════════════════════════
st.subheader(f"{t('p2_stock_ranking')}: {sel_label}")

with st.spinner(t("p2_loading_stocks")):
    constituents = get_theme_constituents(sel_sector)

if not constituents:
    st.info(t("p2_no_constituents"))
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

        # ── Section 5: Send to Scanner ────────────────────────────────────────
        all_tickers = ranked_df["ticker"].tolist()
        if st.button(f"▶ {t('p2_send_scanner')} ({len(all_tickers)} tickers)",
                     type="primary", key="p2_send_main"):
            st.session_state["scanner_pool"]    = ", ".join(all_tickers)
            st.session_state["scanner_trigger"] = True
            st.switch_page("pages/3_Scanner.py")

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — Sub-Sector Drill-Down (Layer 2 & 3)
# ══════════════════════════════════════════════════════════════════════════════
with st.expander(f"🔍 {t('p2_subsector_drill')}"):

    # Collect sub-sectors parented to the selected GICS sector
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
        sub_labels = [v["label"] for v in sub_options.values()]
        sub_names  = list(sub_options.keys())

        sel_sub_label = st.selectbox(
            t("p2_select_subsector"), sub_labels, key="p2_sub_sel"
        )
        sel_sub = sub_names[sub_labels.index(sel_sub_label)]
        layer   = sub_options[sel_sub]["layer"]
        etf_sub = sub_options[sel_sub]["etf"]

        if layer == 2:
            st.caption(f"Layer 2 — ETF: **{etf_sub}**")
        else:
            st.caption(f"Layer 3 — {t('p2_custom_pool')}")

        with st.spinner(t("p2_loading_stocks")):
            sub_tickers = get_theme_constituents(sel_sub)

        if not sub_tickers:
            st.info(t("p2_no_constituents"))
        else:
            preview = ", ".join(sub_tickers[:15])
            dots    = "..." if len(sub_tickers) > 15 else ""
            st.caption(f"{len(sub_tickers)} tickers: {preview}{dots}")

            with st.spinner(t("p2_ranking_stocks")):
                sub_ranked = rank_sector_stocks(tuple(sub_tickers[:30]))

            if not sub_ranked.empty:
                disp = sub_ranked[["ticker", "name", "1m_ret", "3m_ret", "rsi", "tier"]].copy()
                disp.columns = ["Ticker", "Company", "1M Ret%", "3M Ret%", "RSI", "Tier"]
                render_table(disp.set_index("Ticker"))

                if st.button(
                    f"▶ {t('p2_send_scanner')} ({len(sub_ranked)} tickers)",
                    key="p2_send_sub",
                ):
                    st.session_state["scanner_pool"]    = ", ".join(sub_ranked["ticker"].tolist())
                    st.session_state["scanner_trigger"] = True
                    st.switch_page("pages/3_Scanner.py")
