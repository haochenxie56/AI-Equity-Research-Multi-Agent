"""Price & Volume analysis tab renderer.

Extracted from pages/6_PriceVolume.py so that 4_Equity.py can embed it as a tab
without re-running page-level Streamlit setup code.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "lib"))

from datetime import datetime
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ui_utils import (
    load_info, load_ohlcv, load_prepost, load_earnings,
    fmt_val, fmt_pct, apply_layout, download_report_button, t,
)
from technical import add_sma, add_rsi, add_macd, add_bollinger, add_atr, add_adx, add_volume_ratio


def render_pv_tab(ticker: str) -> None:
    """Render the full price & volume analysis content for *ticker* inside a tab."""

    # ── Settings bar ─────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns([2, 2, 1, 1, 1])
    with c1:
        period = st.selectbox(t("p6_period"), ["3mo", "6mo", "1y", "2y", "5y"],
                              index=2, key="pv_period")
    with c2:
        indicator = st.selectbox(t("p6_indicator"),
                                 ["RSI", "MACD", "ADX", t("p6_ind_bb")],
                                 key="pv_ind")
    with c3:
        show_sma20  = st.checkbox("SMA20",  value=True, key="pv_sma20")
    with c4:
        show_sma50  = st.checkbox("SMA50",  value=True, key="pv_sma50")
    with c5:
        show_sma200 = st.checkbox("SMA200", value=True, key="pv_sma200")

    # ── Load data ─────────────────────────────────────────────────────────────
    with st.spinner(f"Loading {ticker}..."):
        info    = load_info(ticker)
        raw_df  = load_ohlcv(ticker, period)
        cal     = load_earnings(ticker)
        prepost = load_prepost(ticker)

    df = raw_df.copy()
    df = add_sma(df, [20, 50, 200])
    df = add_rsi(df)
    df = add_macd(df)
    df = add_bollinger(df)
    df = add_atr(df)
    df = add_adx(df)
    df = add_volume_ratio(df)

    name  = info.get("longName", ticker)
    price = df["Close"].iloc[-1]
    prev  = df["Close"].iloc[-2] if len(df) > 1 else price
    chg   = (price - prev) / prev * 100

    st.markdown(
        f"### {name} &nbsp; `{ticker}` &nbsp; **${price:.2f}**  "
        f"<span style='color:{'green' if chg>=0 else 'red'}'>{'▲' if chg>=0 else '▼'} {chg:+.2f}%</span>",
        unsafe_allow_html=True,
    )

    pp_parts = []
    if prepost.get("pre_market_price"):
        c = prepost["pre_market_change"] or 0
        pp_parts.append(f"{t('p6_pre')} **${prepost['pre_market_price']:.2f}** ({c:+.2f}%)")
    if prepost.get("post_market_price"):
        c = prepost["post_market_change"] or 0
        pp_parts.append(f"{t('p6_post')} **${prepost['post_market_price']:.2f}** ({c:+.2f}%)")
    if pp_parts:
        st.caption(" | ".join(pp_parts))

    if cal.get("next_earnings_date"):
        days = cal.get("days_to_earnings", 0)
        if 0 <= days <= 14:
            _d_str   = cal["next_earnings_date"].strftime("%Y-%m-%d")
            _day_lbl = f"{days}{t('earn_day_out')}"
            st.warning(f"⚠️ {t('earn_window_lbl')}: {_d_str} — {_day_lbl}")

    st.divider()

    # ── Key metric cards ──────────────────────────────────────────────────────
    last      = df.iloc[-1]
    high52    = df["Close"].tail(252).max()
    low52     = df["Close"].tail(252).min()
    pct_from_high = (price / high52 - 1) * 100

    m = st.columns(6)
    m[0].metric("RSI(14)",          f"{last.get('RSI_14', float('nan')):.1f}")
    m[1].metric("ADX",              f"{last.get('ADX', float('nan')):.1f}")
    m[2].metric("ATR(14)",          f"${last.get('ATR_14', float('nan')):.2f}")
    m[3].metric(t("above_sma200"),  "✅" if price > last.get("SMA_200", 0) else "❌",
                delta=f"${price - last.get('SMA_200', price):.2f}")
    m[4].metric(t("from_52w_high"), f"{pct_from_high:.1f}%")
    m[5].metric(t("vol_ratio_lbl"), f"{last.get('Vol_ratio_20d', float('nan')):.2f}x")

    st.divider()

    # ── Main chart ────────────────────────────────────────────────────────────
    _dark  = st.session_state.get("dark_mode", True)
    _up_c  = "#00c853" if _dark else "#2da44e"
    _dn_c  = "#ff3d3d" if _dark else "#cf222e"
    _cbg   = "rgba(0,0,0,0)" if _dark else "#ffffff"
    _ctpl  = "plotly_dark"   if _dark else "plotly_white"
    _ctxt  = "#8b949e"        if _dark else "#1f2328"
    _cgrid = "rgba(128,128,128,0.12)" if _dark else "#d0d7de"
    _legend_main = (
        dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
             bgcolor="rgba(0,0,0,0)", font=dict(color="#8b949e", size=11))
        if _dark else
        dict(x=0.01, y=0.99, xanchor="left", yanchor="top",
             bgcolor="rgba(255,255,255,0.85)",
             bordercolor="#d0d7de", borderwidth=1,
             font=dict(color="#1f2328", size=11))
    )
    _hover_main = (
        dict(bgcolor="#1c2128", font_color="#e6edf3", bordercolor="#30363d")
        if _dark else
        dict(bgcolor="#ffffff", font_color="#1f2328", bordercolor="#d0d7de")
    )

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.58, 0.18, 0.24],
        vertical_spacing=0.02,
        subplot_titles=("", "Volume", indicator),
    )

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name="OHLC",
        increasing_line_color="#00c853", decreasing_line_color="#ff3d3d",
        increasing_fillcolor="#00c853", decreasing_fillcolor="#ff3d3d",
    ), row=1, col=1)

    for col_n, show, color, label in [
        ("SMA_20",  show_sma20,  "#4fc3f7", "SMA20"),
        ("SMA_50",  show_sma50,  "#ffb300", "SMA50"),
        ("SMA_200", show_sma200, "#ff7043", "SMA200"),
    ]:
        if show and col_n in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col_n], name=label,
                line=dict(color=color, width=1.2),
                hovertemplate=f"{label}: $%{{y:.2f}}<extra></extra>",
            ), row=1, col=1)

    if indicator == t("p6_ind_bb") and "BB_upper" in df.columns:
        for band_col, band_name, band_color in [
            ("BB_upper", "BB Upper", "rgba(150,150,255,0.4)"),
            ("BB_mid",   "BB Mid",   "rgba(150,150,255,0.6)"),
            ("BB_lower", "BB Lower", "rgba(150,150,255,0.4)"),
        ]:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[band_col], name=band_name,
                line=dict(color=band_color, width=1, dash="dot"),
            ), row=1, col=1)

    if cal.get("next_earnings_date"):
        try:
            import pytz
            ed_ts = pd.Timestamp(cal["next_earnings_date"])
            if df.index[0].tzinfo is not None:
                ny_tz = pytz.timezone("America/New_York")
                ed_ts = (ed_ts.tz_localize(ny_tz) if ed_ts.tzinfo is None
                         else ed_ts.tz_convert(ny_tz))
            if df.index[0] <= ed_ts <= df.index[-1]:
                fig.add_vline(x=ed_ts, line_dash="dot", line_color="#ffb300",
                              annotation_text="Earnings", row=1, col=1)
        except Exception:
            pass

    vol_colors = [_up_c if c >= o else _dn_c
                  for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(
        x=df.index, y=df["Volume"],
        marker_color=vol_colors, name="Volume", showlegend=False,
    ), row=2, col=1)

    if "Vol_ratio_20d" in df.columns:
        avg_vol = df["Volume"] / df["Vol_ratio_20d"].replace(0, float("nan"))
        fig.add_trace(go.Scatter(
            x=df.index, y=avg_vol, name="20D Avg Vol",
            line=dict(color="rgba(255,179,0,0.65)", width=1, dash="dot"),
        ), row=2, col=1)

    if indicator == "RSI" and "RSI_14" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["RSI_14"], name="RSI(14)",
            line=dict(color="#cc5de8", width=1.5),
        ), row=3, col=1)
        _rsi_lines = (
            [(70, "rgba(239,83,80,0.5)"), (30, "rgba(38,166,154,0.5)"),
             (50, "rgba(150,150,150,0.3)")]
            if _dark else
            [(70, "#cf222e"), (30, "#2da44e"), (50, "#8c959f")]
        )
        for level, color in _rsi_lines:
            fig.add_hline(y=level, line_dash="dash", line_color=color, row=3, col=1)

    elif indicator == "MACD" and "MACD" in df.columns:
        hist_colors = ["#26a69a" if v >= 0 else "#ef5350"
                       for v in df["MACD_hist"].fillna(0)]
        fig.add_trace(go.Bar(
            x=df.index, y=df["MACD_hist"], name="MACD Hist",
            marker_color=hist_colors, showlegend=False,
        ), row=3, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], name="MACD",
                                 line=dict(color="#4da6ff", width=1.3)), row=3, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["MACD_signal"], name="Signal",
                                 line=dict(color="#ffd43b", width=1.3)), row=3, col=1)

    elif indicator == "ADX" and "ADX" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["ADX"], name="ADX",
                                 line=dict(color="#ffd43b", width=1.5)), row=3, col=1)
        if "DI_plus" in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df["DI_plus"], name="+DI",
                                     line=dict(color="#51cf66", width=1)), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df["DI_minus"], name="-DI",
                                     line=dict(color="#ef5350", width=1)), row=3, col=1)
        fig.add_hline(y=25, line_dash="dash",
                      line_color="rgba(150,150,150,0.4)" if _dark else "#8c959f",
                      annotation_text="25", row=3, col=1)

    elif indicator == t("p6_ind_bb") and "ATR_14" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["ATR_14"], name="ATR(14)",
                                 line=dict(color="#ff922b", width=1.5)), row=3, col=1)

    fig.update_layout(
        height=700,
        template=_ctpl,
        paper_bgcolor=_cbg,
        plot_bgcolor=_cbg,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_rangeslider_visible=False,
        legend=_legend_main,
        font=dict(size=11, color=_ctxt),
        hoverlabel=_hover_main,
    )
    for row_i in range(1, 4):
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor=_cgrid,
                         linecolor=_cgrid, tickfont=dict(color=_ctxt), row=row_i, col=1)
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor=_cgrid,
                         linecolor=_cgrid, tickfont=dict(color=_ctxt), row=row_i, col=1)
    fig.update_xaxes(showticklabels=True, row=3, col=1)

    st.plotly_chart(fig, use_container_width=True)
    st.divider()

    # ── Key price levels ──────────────────────────────────────────────────────
    st.subheader(t("p6_key_levels"))
    atr_val  = last.get("ATR_14", 0) or 0
    sma20_v  = last.get("SMA_20", 0) or 0
    sma50_v  = last.get("SMA_50", 0) or 0
    stop_2x  = price - 2 * atr_val
    upside   = high52 - price
    downside = price - stop_2x
    rr_ratio = upside / downside if downside > 0 else 0

    kp1, kp2, kp3, kp4 = st.columns(4)
    kp1.metric(t("p6_sma20_sup"), f"${sma20_v:.2f}")
    kp2.metric(t("p6_sma50_sup"), f"${sma50_v:.2f}")
    kp3.metric(t("p6_stop"),      f"${stop_2x:.2f}", delta=f"-{2*atr_val:.2f}")
    kp4.metric(t("p6_rr"),        f"1 : {rr_ratio:.2f}",
               delta=t("p6_rr_low") if rr_ratio < 1 else t("p6_rr_ok"),
               delta_color="inverse" if rr_ratio < 1 else "normal")

    st.divider()

    # ── Download report ───────────────────────────────────────────────────────
    today    = datetime.now().strftime("%Y-%m-%d")
    date_pfx = datetime.now().strftime("%Y%m%d")
    rsi_v    = last.get("RSI_14", float("nan"))
    adx_v    = last.get("ADX",    float("nan"))
    _vol_r   = last.get("Vol_ratio_20d") or 0

    _lang = st.session_state.get("language", "en")
    _L    = lambda zh, en: en if _lang == "en" else zh

    trend = _L(
        "多头排列" if price > sma20_v > sma50_v else
        "空头排列" if price < sma20_v < sma50_v else "混合/震荡",
        "Bullish alignment" if price > sma20_v > sma50_v else
        "Bearish alignment" if price < sma20_v < sma50_v else "Mixed/Ranging",
    )
    _rsi_sig = _L(
        "超买 ⚠️" if rsi_v > 70 else "超卖 🟢" if rsi_v < 30 else "中性区间 ✓",
        "Overbought ⚠️" if rsi_v > 70 else "Oversold 🟢" if rsi_v < 30 else "Neutral ✓",
    )
    _adx_sig = _L(
        "趋势明确 ✓" if adx_v > 25 else "震荡市",
        "Trending ✓" if adx_v > 25 else "Ranging",
    )
    _vol_sig = _L(
        "放量" if _vol_r > 1.5 else "缩量" if _vol_r < 0.8 else "正常",
        "High volume" if _vol_r > 1.5 else "Low volume" if _vol_r < 0.8 else "Normal",
    )
    _a200_txt = _L(
        "✅ 是" if price > last.get("SMA_200", 0) else "❌ 否",
        "✅ Yes" if price > last.get("SMA_200", 0) else "❌ No",
    )
    pp_line = ""
    if prepost.get("pre_market_price"):
        pp_line = f"**{t('p6_pre')}**: ${prepost['pre_market_price']:.2f} ({prepost.get('pre_market_change', 0):+.2f}%)"
    elif prepost.get("post_market_price"):
        pp_line = f"**{t('p6_post')}**: ${prepost['post_market_price']:.2f} ({prepost.get('post_market_change', 0):+.2f}%)"

    report_md = f"""# {_L('量价分析报告', 'Price & Volume Analysis')}: {ticker} — {name}

**{_L('日期', 'Date')}**: {today}  |  **{_L('分析周期', 'Period')}**: {period}  |  **{_L('当前价', 'Price')}**: ${price:.2f} USD
{pp_line}

---

## {_L('执行摘要', 'Executive Summary')}

RSI(14) {rsi_v:.1f} ({_rsi_sig}),
ADX {adx_v:.1f} ({_adx_sig}),
{_L('均线结构', 'MA structure')}: {trend}.
{_L('距52周高点', 'From 52W High')} {pct_from_high:.1f}%,
{_L('止损参考（2xATR）', 'Stop loss (2xATR)')} ${stop_2x:.2f},
{_L('风险回报比', 'Risk/Reward')} 1:{rr_ratio:.2f}.

---

## {_L('技术指标读数', 'Technical Indicator Readings')}

| {_L('指标', 'Indicator')} | {_L('值', 'Value')} | {_L('信号', 'Signal')} |
|---|---|---|
| RSI(14) | {rsi_v:.1f} | {_rsi_sig} |
| ADX | {adx_v:.1f} | {_adx_sig} |
| ATR(14) | ${atr_val:.2f} | {_L('日均波幅', 'Avg daily range')} |
| {_L('量比(20D)', 'Vol Ratio(20D)')} | {_vol_r:.2f}x | {_vol_sig} |
| {_L('SMA200上方', 'Above SMA200')} | {_a200_txt} | |

---

> **{_L('风险提示', 'Disclaimer')}**: {_L('本报告仅供研究参考，不构成任何交易建议。', 'For research purposes only. Does not constitute trading advice.')}
"""
    from pathlib import Path as _Path
    rp = _Path(__file__).parent.parent / "research" / "stock" / f"{date_pfx}_{ticker}_pv.md"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(report_md, encoding="utf-8")
    download_report_button(report_md, rp.name, t("download_report"))
