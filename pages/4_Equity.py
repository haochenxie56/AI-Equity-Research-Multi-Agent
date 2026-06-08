"""Page 4 — 个股研究（Equity Research）

Four-tab layout:
  Overview       — Moat radar, peer comparison, business description, report
  Financials     — 3-statement model, DCF, relative valuation, quality check
  Price & Volume — Candlestick chart, technical indicators, key levels
  News & Sentiment — News feed with sentiment scoring
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from datetime import datetime
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from ui_utils import (
    apply_theme, render_sidebar, load_info, load_ohlcv, load_earnings,
    fmt_large, fmt_pct, fmt_val, apply_layout, apply_legend,
    download_report_button, page_header, translate_to_chinese, render_table,
    load_news, t, render_workflow_bar,
)
from financial_tab import render_financial_tab
from pv_tab import render_pv_tab


def _get_default_peers(ticker: str, info: dict) -> str:
    industry = info.get("industry", "")
    peer_map = {
        "Semiconductors":  "NVDA, AMD, INTC, AVGO, QCOM, TXN",
        "Software":        "MSFT, CRM, ORCL, NOW, ADBE, SAP",
        "Internet":        "META, GOOGL, AMZN, SNAP, PINS",
        "Biotechnology":   "AMGN, GILD, BIIB, REGN, VRTX",
        "Banks":           "JPM, BAC, WFC, C, USB",
        "Communication":   "META, GOOGL, NFLX, DIS, CMCSA",
    }
    for key, peers in peer_map.items():
        if key.lower() in industry.lower():
            return ", ".join([p for p in peers.split(", ") if p != ticker])
    return "AAPL, MSFT, GOOGL, AMZN, META"


st.set_page_config(page_title="Equity Research", page_icon="🏢", layout="wide")
apply_theme()
render_sidebar()

st.title(t("p4_title"))
page_header()
render_workflow_bar()

# In-page ticker input. Priority for the prefilled value:
#   1. Investment Cockpit "View Full Research" hand-off (equity_prefill_ticker),
#   2. the workflow-state ticker (existing behavior).
# We seed the widget's session_state key BEFORE the widget is created so the
# prefill takes effect even if the page was visited earlier this session. The
# hand-off key is popped (one-shot) so it does not stick across manual edits.
_prefill_ticker = (st.session_state.pop("equity_prefill_ticker", "") or "").upper().strip()
if _prefill_ticker:
    st.session_state["p4_ticker_input"] = _prefill_ticker
elif "p4_ticker_input" not in st.session_state:
    _wf_ticker = st.session_state.get("research_state", {}).get("ticker", "")
    if _wf_ticker:
        st.session_state["p4_ticker_input"] = _wf_ticker
ticker = st.text_input(
    t("p1_wf_ticker_lbl"),
    placeholder="e.g. NVDA",
    key="p4_ticker_input",
).upper().strip()

if not ticker:
    st.info(t("no_ticker"))
    # Keep the key section frames visible (with a placeholder) even before a
    # ticker is entered, so navigating here never shows a blank page.
    for _ph_key in ("p4_biz", "p4_report", "cockpit_fv_header"):
        with st.expander(t(_ph_key), expanded=False):
            st.caption(t("cockpit_fv_enter_ticker"))
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT-FIRST PASS — create EVERY section frame BEFORE any blocking call
# ══════════════════════════════════════════════════════════════════════════════
# Streamlit streams element deltas in script-execution order: a section appears
# in the browser only once the line that CREATES it runs. So every top-level
# section frame — company header, earnings banner, key-metrics row, the four
# analysis tabs, the Overview tab's sub-sections (moat+peers area, Company
# Business Description, Research Report) and the AI Valuation Summary — is created
# HERE as an empty slot (or tab/container frame), BEFORE load_info / load_earnings
# / any yfinance / Finnhub / translation / LLM call runs. Each slot is filled in
# the FILL PASS below, once the data arrives.
#
# The ONLY things allowed above this block are imports, session_state reads
# (incl. the equity_prefill_ticker hand-off) and the ticker-input widget — no
# blocking call precedes it. On a cold cache (first page entry — the exact
# acceptance scenario) every frame, including the AI Valuation Summary, is on
# screen immediately rather than after the data fetches complete.
header_slot = st.empty()
with header_slot.container():
    # Lightweight placeholder: the ticker is known without any fetch.
    st.markdown(f"### `{ticker}` …")
st.divider()
earnings_slot = st.empty()
metrics_slot  = st.empty()
st.divider()

tab_overview, tab_financial, tab_pv, tab_news = st.tabs([
    t("p4_tab_overview"),
    t("p4_tab_financial"),
    t("p4_tab_pv"),
    t("p4_tab_news"),
])

# Reserve the Overview tab's sub-section frames, in their on-page vertical order,
# so each appears immediately and is filled in the FILL PASS below:
#   ov_top_slot  — moat radar + peer comparison (container; filled in place)
#   biz_slot     — Company Business Description (st.empty; placeholder → content)
#   report_slot  — Research Report (st.empty; placeholder → auto-generated report)
with tab_overview:
    ov_top_slot = st.container()
    st.divider()
    biz_slot = st.empty()
    with biz_slot.container():
        with st.expander(t("p4_biz"), expanded=False):
            st.caption(f"⏳ {t('p4_loading')}")
    st.divider()
    report_slot = st.empty()
    with report_slot.container():
        st.subheader(t("p4_report"))
        st.caption(f"⏳ {t('p4_loading')}")

st.divider()
_fv_key = f"app_fair_value_{ticker}"
fv_slot = st.empty()
if _fv_key not in st.session_state:
    with fv_slot.container():
        with st.expander(t("cockpit_fv_header"), expanded=True):
            st.info("📊 AI Valuation summarizing...")
# ── End layout block — every section frame now exists on screen ───────────────

# ══════════════════════════════════════════════════════════════════════════════
# FILL PASS — blocking data fetches, then fill the pre-created slots
# ══════════════════════════════════════════════════════════════════════════════
# ── Load shared data ──────────────────────────────────────────────────────────
with st.spinner(f"Loading {ticker}..."):
    info  = load_info(ticker)
    cal   = load_earnings(ticker)

name  = info.get("longName", ticker)
price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
prev  = info.get("regularMarketPreviousClose", price)
chg   = (price - prev) / prev * 100 if prev else 0
arrow = "▲" if chg >= 0 else "▼"
color = "green" if chg >= 0 else "red"

with header_slot.container():
    st.markdown(
        f"### {name} &nbsp; `{ticker}` &nbsp; **${price:.2f}** "
        f"<span style='color:{color}'>{arrow} {chg:+.2f}%</span>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"**{info.get('sector','N/A')}** / {info.get('industry','N/A')} | "
        f"{info.get('exchange','N/A')} | {t('employees')}: {info.get('fullTimeEmployees', 'N/A')}"
    )

# ── Earnings banner ───────────────────────────────────────────────────────────
if cal.get("next_earnings_date"):
    d_str      = cal["next_earnings_date"].strftime("%Y-%m-%d")
    days       = cal.get("days_to_earnings", 0)
    _day_lbl   = f"{days}{t('earn_day_out') if days >= 0 else t('earn_day_ago')}"
    _eps_part  = f" | {t('earn_eps_est')}: ${cal['eps_estimate']:.2f}" if cal.get("eps_estimate") else ""
    _sign      = "+" if (cal.get("surprise_pct_last") or 0) >= 0 else ""
    _surp_part = (f" | {t('earn_last_surp')}: {_sign}{cal.get('surprise_pct_last','N/A')}%"
                  if cal.get("surprise_pct_last") is not None else "")
    banner     = f"📅 {t('earn_next_lbl')}: **{d_str}** — {_day_lbl}{_eps_part}{_surp_part}"
    with earnings_slot.container():
        if 0 <= days <= 14:
            st.warning(f"⚠️ {t('earn_window_lbl')} — {banner}")
        elif days < 0 and abs(days) <= 7:
            st.info(f"🗓️ {t('earn_just_rel')} — {banner}")
        else:
            st.info(banner)

# ── Key metrics ───────────────────────────────────────────────────────────────
with metrics_slot.container():
    m = st.columns(6)
    m[0].metric(t("mkt_cap"),      fmt_large(info.get("marketCap")))
    m[1].metric("Trailing P/E",    fmt_val(info.get("trailingPE"), decimals=1, suffix="x"))
    m[2].metric("Forward P/E",     fmt_val(info.get("forwardPE"),  decimals=1, suffix="x"))
    m[3].metric(t("gross_margin"), fmt_pct(info.get("grossMargins")))
    m[4].metric("ROE",             fmt_pct(info.get("returnOnEquity")))
    m[5].metric(t("analyst_rtg"),  str(info.get("recommendationKey", "N/A")).upper())

# ════════════════════════════════════════════════════════════════════════════════
# TAB 1: OVERVIEW — fill the slots reserved in the layout block above
# ════════════════════════════════════════════════════════════════════════════════
with ov_top_slot:
    left_col, right_col = st.columns([1, 2])

    with left_col:
        st.subheader(t("p4_moat"))
        st.caption(t("p4_moat_hint"))

        gm    = (info.get("grossMargins") or 0) * 100
        om    = (info.get("operatingMargins") or 0) * 100
        roe   = (info.get("returnOnEquity") or 0) * 100

        _moat_dims = [
            ("moat_intangibles", min(5, max(1, int(gm / 12)))),
            ("moat_switching",   min(5, max(1, int(om / 8) + 1))),
            ("moat_network",     min(5, max(1, 2))),
            ("moat_cost_adv",    min(5, max(1, int(om / 10)))),
            ("moat_eff_scale",   min(5, max(1, int(roe / 15)))),
        ]

        scores = {}
        for _mkey, _mdefault in _moat_dims:
            _mlabel = t(_mkey)
            scores[_mlabel] = st.slider(_mlabel, 1, 5, _mdefault, key=f"moat_{_mkey}")

        dims  = list(scores.keys())
        vals  = list(scores.values())
        _dark = st.session_state.get("dark_mode", True)
        _rbg  = "rgba(0,0,0,0)" if _dark else "#ffffff"
        _rtpl = "plotly_dark"   if _dark else "plotly_white"
        _rtxt = "#8b949e"        if _dark else "#1f2328"
        _rgrid = "#21262d"       if _dark else "#d0d7de"

        fig_r = go.Figure(go.Scatterpolar(
            r=vals + [vals[0]],
            theta=dims + [dims[0]],
            fill="toself",
            fillcolor="rgba(77,166,255,0.25)",
            line=dict(color="#4da6ff", width=2),
            name=ticker,
        ))
        fig_r.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True, range=[0, 5], tickvals=[1, 2, 3, 4, 5],
                    gridcolor=_rgrid, tickfont=dict(color=_rtxt),
                ),
                angularaxis=dict(tickfont=dict(size=11, color=_rtxt), gridcolor=_rgrid),
            ),
            showlegend=False, height=320,
            margin=dict(l=40, r=40, t=30, b=30),
            paper_bgcolor=_rbg, plot_bgcolor=_rbg, template=_rtpl,
            font=dict(color=_rtxt),
            hoverlabel=dict(
                bgcolor="#ffffff" if not _dark else "#1c2128",
                font_color="#1f2328" if not _dark else "#e6edf3",
            ),
        )
        st.plotly_chart(fig_r, use_container_width=True)

        total_moat = sum(vals)
        moat_label = (t("moat_wide") if total_moat >= 18 else
                      (t("moat_narrow") if total_moat >= 12 else t("moat_none")))
        st.metric(t("p4_moat_rating"), f"{moat_label} ({total_moat}/25)")

    with right_col:
        st.subheader(t("p4_peers"))

        peer_str  = st.text_input(
            t("p4_peer_input"),
            value=_get_default_peers(ticker, info),
            key="peer_input",
        )
        peer_list = [tk.strip().upper() for tk in peer_str.split(",") if tk.strip()]
        all_comp  = [ticker] + peer_list

        with st.spinner(t("p4_loading_peers")):
            peer_data = []
            # Raw peer info dicts (already fetched here) — reused by the routed
            # valuation for growth-profile peer matching (no new per-ticker
            # network). Each carries sector / revenueGrowth / marketCap /
            # priceToSalesTrailing12Months / enterpriseToEbitda for the matcher.
            peer_infos = []
            for tk in all_comp[:8]:
                try:
                    i = load_info(tk)
                    if tk != ticker:
                        peer_infos.append({"ticker": tk, **i})
                    peer_data.append({
                        "Ticker":        tk,
                        "P/S":           i.get("priceToSalesTrailing12Months") or 0,
                        "Fwd P/E":       i.get("forwardPE") or 0,
                        t("p4_peer_gm"): (i.get("grossMargins") or 0) * 100,
                        t("p4_peer_op"): (i.get("operatingMargins") or 0) * 100,
                        "ROE%":          (i.get("returnOnEquity") or 0) * 100,
                    })
                except Exception:
                    pass

        if peer_data:
            peer_df       = pd.DataFrame(peer_data).set_index("Ticker")
            metric_choice = st.selectbox(
                t("p4_peer_metric"),
                [t("p4_peer_gm"), t("p4_peer_op"), "ROE%", "P/S", "Fwd P/E"],
            )
            colors = ["#4da6ff" if tk == ticker else "#6c757d" for tk in peer_df.index]

            fig_p = go.Figure(go.Bar(
                x=peer_df.index,
                y=peer_df[metric_choice],
                marker_color=colors,
                text=[f"{v:.1f}" for v in peer_df[metric_choice]],
                textposition="outside",
            ))
            apply_layout(fig_p, title=f"{t('p4_peers')} — {metric_choice}", height=300)
            apply_legend(fig_p)
            fig_p.update_yaxes(title_text=metric_choice)
            st.plotly_chart(fig_p, use_container_width=True)

            _pct_cols   = [c for c in peer_df.columns if "%" in c]
            _ratio_cols = [c for c in peer_df.columns if "%" not in c]
            peer_display = peer_df.copy().astype(object)
            for c in _pct_cols:
                peer_display[c] = peer_df[c].apply(
                    lambda v: f"{v:+.1f}%" if pd.notna(v) else "N/A"
                )
            for c in _ratio_cols:
                peer_display[c] = peer_df[c].apply(
                    lambda v: f"{v:.1f}x" if pd.notna(v) and v != 0 else "N/A"
                )
            render_table(peer_display)

# ── Business description (fills the biz_slot reserved in the layout block) ─────
# Replaces the placeholder in place; always renders a final state (text / "N/A" /
# source-text fallback) so the slot is never left on the placeholder.
with biz_slot.container():
    with st.expander(t("p4_biz"), expanded=False):
        raw = info.get("longBusinessSummary", "")
        if raw:
            _lang = st.session_state.get("language", "en")
            try:
                st.markdown(raw if _lang == "en" else translate_to_chinese(raw))
            except Exception:
                # Translation failed (e.g. network) — fall back to the source text
                # rather than leaving the section hanging on the placeholder.
                st.markdown(raw)
        else:
            st.markdown("N/A")

# ── Research Report (fills the report_slot reserved in the layout block) ──────
# Deterministically assembled from already-fetched data on page load — no LLM
# call — so the auto-run behavior is unchanged; this only fills the pre-created
# frame. The render below is pure string formatting (cannot hang on the
# placeholder); the only I/O — writing the .md to disk — is guarded so a
# read-only / failed write still leaves a fully-rendered report on screen.
with report_slot.container():
    st.subheader(t("p4_report"))
    today    = datetime.now().strftime("%Y-%m-%d")
    date_pfx = datetime.now().strftime("%Y%m%d")
    moat_str = "\n".join([f"| {k} | {'★'*v}{'☆'*(5-v)} ({v}/5) |" for k, v in scores.items()])

    _lang = st.session_state.get("language", "en")
    _L    = lambda en, zh: en if _lang == "en" else zh

    _gm_key = t("p4_peer_gm")
    _op_key = t("p4_peer_op")
    _no_peer = _L("No peer data available", "暂无同业数据")
    peer_md_rows = "\n".join([
        f"| {r['Ticker']} | {r[_gm_key]:.1f}% | {r[_op_key]:.1f}% | {r['ROE%']:.1f}% | {r['P/S']:.1f}x | {r['Fwd P/E']:.1f}x |"
        for r in peer_data
    ]) if peer_data else _no_peer

    _analysts_txt = (
        (_L("Analyst consensus: ", "分析师一致评级：") +
         f"**{str(info.get('recommendationKey','N/A')).upper()}**, ")
        if info.get("recommendationKey") else ""
    )
    _target_n   = info.get("numberOfAnalystOpinions", 0)
    _target_txt = _L(f"{_target_n} analysts", f"{_target_n} 位分析师")

    report_md = f"""# {_L('Equity Research', '个股研究报告')}: {ticker} — {name}

**{_L('Date', '日期')}**: {today}
**Ticker**: {ticker} | {info.get('exchange','N/A')}
**{_L('Sector', '行业')}**: {info.get('sector','N/A')} / {info.get('industry','N/A')}
**{_L('Analyst Agent', '分析师 Agent')}**: equity-research

---

## {_L('Executive Summary', '执行摘要')}

{name} — {_L('current price', '当前股价')} ${price:.2f}, {_L('market cap', '市值')} {fmt_large(info.get('marketCap'))}.
{_analysts_txt}{_L('price target', '目标价均值')} ${info.get('targetMeanPrice', 'N/A')} ({_target_txt}).

---

## {_L('Key Financial Metrics', '关键财务指标')}

| {_L('Metric', '指标')} | {_L('Value', '数值')} |
|---|---|
| {_L('Market Cap', '市值')} | {fmt_large(info.get('marketCap'))} |
| Trailing P/E | {fmt_val(info.get('trailingPE'), decimals=1, suffix='x')} |
| Forward P/E | {fmt_val(info.get('forwardPE'), decimals=1, suffix='x')} |
| P/S (TTM) | {fmt_val(info.get('priceToSalesTrailing12Months'), decimals=1, suffix='x')} |
| {_L('Gross Margin', '毛利率')} | {fmt_pct(info.get('grossMargins'))} |
| ROE | {fmt_pct(info.get('returnOnEquity'))} |
| Beta | {fmt_val(info.get('beta'), decimals=2)} |

---

## {_L('Moat Assessment', '护城河评估')}

| {_L('Dimension', '维度')} | {_L('Score', '评分')} |
|---|---|
{moat_str}

**{_L('Overall Rating', '综合评级')}**: {moat_label} ({total_moat}/25)

---

## {_L('Peer Comparison', '同业对比')}

| Ticker | {_L('Gross Margin', '毛利率')} | {_L('Op. Margin', '营业利润率')} | ROE | P/S | Fwd P/E |
|---|---|---|---|---|---|
{peer_md_rows}

---

## {_L('Key Risks', '主要风险')}

1. {_L('Valuation must be assessed against future growth expectations', '估值水平需结合未来增长预期评估')}
2. {_L('Changes in competitive landscape', '行业竞争格局变化')}
3. {_L('Macro environment and interest rate risk', '宏观经济与利率环境')}

---

> **{_L('Disclaimer', '风险提示')}**: {_L('For research purposes only. Not investment advice.', '本报告仅供研究参考，不构成投资建议。')}
"""

    with st.expander(t("p4_view_md"), expanded=False):
        with st.spinner(t("p4_loading")):
            st.markdown(report_md)

    report_path = (Path(__file__).parent.parent / "research" / "stock"
                   / f"{date_pfx}_{ticker}_equity.md")
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_md, encoding="utf-8")
    except Exception:
        pass  # read-only / failed write — the rendered report above still stands
    download_report_button(report_md, report_path.name, t("download_report"))

# ════════════════════════════════════════════════════════════════════════════════
# TAB 2: FINANCIALS
# ════════════════════════════════════════════════════════════════════════════════
with tab_financial:
    render_financial_tab(ticker)

# ════════════════════════════════════════════════════════════════════════════════
# TAB 3: PRICE & VOLUME
# ════════════════════════════════════════════════════════════════════════════════
with tab_pv:
    render_pv_tab(ticker)

# ════════════════════════════════════════════════════════════════════════════════
# TAB 4: NEWS & SENTIMENT
# ════════════════════════════════════════════════════════════════════════════════
with tab_news:
    st.subheader(t("p4_news"))

    _dark    = st.session_state.get("dark_mode", True)
    _pos_col = "#3fb950"
    _neg_col = "#f85149"
    _neu_col = "#8b949e"
    _bd_col  = "#30363d" if _dark else "#d0d7de"
    _t0_col  = "#e6edf3" if _dark else "#1f2328"
    _t1_col  = "#8b949e" if _dark else "#57606a"

    with st.spinner(t("p4_loading_news")):
        _news = load_news(ticker, days=7)

    _has_finnhub = bool(__import__("os").getenv("FINNHUB_API_KEY", ""))

    if not _news:
        if not _has_finnhub:
            st.info(t("p4_no_finnhub"))
        else:
            st.info(t("p4_no_news"))
    else:
        _scores  = [a["sentiment"] for a in _news]
        _total   = len(_scores)
        _pos_n   = sum(1 for s in _scores if s >  0.2)
        _neu_n   = sum(1 for s in _scores if -0.2 <= s <= 0.2)
        _neg_n   = sum(1 for s in _scores if s < -0.2)
        _avg_s   = sum(_scores) / _total
        _avg_lbl = (t("p4_sent_pos") if _avg_s > 0.2 else
                    (t("p4_sent_neg") if _avg_s < -0.2 else t("p4_sent_neu")))

        _mc1, _mc2, _mc3 = st.columns(3)
        _mc1.metric(t("p4_news_count"), f"{_total}", t("p4_last7d"))
        _mc2.metric(t("p4_news_avg"),   f"{_avg_s:+.2f}", _avg_lbl)
        _mc3.metric(
            t("p4_news_dist"),
            f"{t('p4_pos')} {_pos_n} / {t('p4_neu')} {_neu_n} / {t('p4_neg')} {_neg_n}",
            f"{_pos_n/_total*100:.0f}% {t('p4_pos')}" if _total else "",
        )

        from collections import defaultdict
        from datetime import datetime as _dt_cls

        _raw_times    = [a["datetime"] for a in _news]
        _span_min     = _dt_cls.strptime(min(_raw_times), "%Y-%m-%d %H:%M")
        _span_max     = _dt_cls.strptime(max(_raw_times), "%Y-%m-%d %H:%M")
        _date_range_d = (_span_max - _span_min).total_seconds() / 86400

        if _date_range_d < 2:
            _daily: dict = defaultdict(list)
            for _a in _news:
                _daily[_a["datetime"][:13] + ":00"].append(_a["sentiment"])
            _tick_fmt    = "%m-%d %H:%M"
            _chart_title = t("p4_chart_hourly")
        else:
            _daily = defaultdict(list)
            for _a in _news:
                _daily[_a["datetime"][:10]].append(_a["sentiment"])
            _tick_fmt    = "%m-%d"
            _chart_title = t("p4_chart_daily")

        _dates     = sorted(_daily.keys())
        _daily_avg = [sum(_daily[d]) / len(_daily[d]) for d in _dates]

        if len(_dates) >= 2:
            _fig_s = go.Figure()
            _fig_s.add_trace(go.Scatter(
                x=_dates, y=[max(0.0, v) for v in _daily_avg],
                fill="tozeroy", fillcolor="rgba(63,185,80,0.15)",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False, hoverinfo="skip",
            ))
            _fig_s.add_trace(go.Scatter(
                x=_dates, y=[min(0.0, v) for v in _daily_avg],
                fill="tozeroy", fillcolor="rgba(248,81,73,0.15)",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False, hoverinfo="skip",
            ))
            _fig_s.add_trace(go.Scatter(
                x=_dates, y=_daily_avg,
                mode="lines+markers",
                line=dict(color="#4da6ff", width=2),
                marker=dict(size=6),
                name="Avg Sentiment",
                hovertemplate="%{x}<br>Sentiment: %{y:.2f}<extra></extra>",
            ))
            _hline_c = "#484f58" if _dark else "#8c959f"
            _fig_s.add_hline(
                y=0, line_dash="dash", line_color=_hline_c, line_width=1,
                annotation_text="Neutral", annotation_position="right",
                annotation_font_color=_hline_c,
            )
            apply_layout(_fig_s, title=_chart_title, height=240)
            apply_legend(_fig_s)
            _fig_s.update_yaxes(range=[-1.1, 1.1], title_text="Sentiment")
            _fig_s.update_xaxes(tickformat=_tick_fmt)
            st.plotly_chart(_fig_s, use_container_width=True)

        _filter = st.radio(
            t("p4_filter"),
            [t("p4_all"), t("p4_pos"), t("p4_neu"), t("p4_neg")],
            horizontal=True,
            key="news_sentiment_filter",
        )

        def _sent_label(s: float) -> str:
            if s >  0.2: return t("p4_pos")
            if s < -0.2: return t("p4_neg")
            return t("p4_neu")

        _filtered = (
            _news if _filter == t("p4_all")
            else [a for a in _news if _sent_label(a["sentiment"]) == _filter]
        )

        if not _filtered:
            st.caption(t("p4_no_news_cat"))
        else:
            _lang = st.session_state.get("language", "zh")
            for _a in _filtered[:20]:
                _s       = _a["sentiment"]
                _dot     = _pos_col if _s > 0.2 else (_neg_col if _s < -0.2 else _neu_col)
                _score_txt = f"{_s:+.2f}"
                _headline_display = (
                    _a["headline"] if _lang == "en"
                    else (translate_to_chinese(_a["headline"]) if _a.get("headline") else "")
                )
                _link = (
                    f'<a href="{_a["url"]}" target="_blank" '
                    f'style="color:{_t0_col};text-decoration:none;font-weight:500;">'
                    f'{_headline_display}</a>'
                    if _a.get("url") else
                    f'<span style="color:{_t0_col};font-weight:500;">{_headline_display}</span>'
                )
                st.markdown(
                    f'<div style="display:flex;align-items:flex-start;'
                    f'padding:10px 0;border-bottom:1px solid {_bd_col};">'
                    f'<div style="flex-shrink:0;width:48px;text-align:center;padding-top:2px;">'
                    f'<span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
                    f'background:{_dot};margin-bottom:3px;"></span>'
                    f'<div style="font-size:0.68rem;color:{_dot};font-weight:600;'
                    f'font-family:monospace;">{_score_txt}</div>'
                    f'</div>'
                    f'<div style="flex:1;min-width:0;">'
                    f'<div style="line-height:1.4;">{_link}</div>'
                    f'<div style="font-size:0.73rem;color:{_t1_col};margin-top:4px;">'
                    f'{_a["source"]} &nbsp;·&nbsp; {_a["datetime"]}'
                    f'</div>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if _a.get("summary"):
                    _summary_label = t("news_summary")
                    with st.expander(_summary_label, expanded=False):
                        _summary_txt = (
                            _a["summary"] if _lang == "en"
                            else translate_to_chinese(_a["summary"])
                        )
                        st.caption(_summary_txt)


# ════════════════════════════════════════════════════════════════════════════════
# Phase 6C-B — AI Valuation Summary (app-computed fair value + optional AI debate)
# ════════════════════════════════════════════════════════════════════════════════
# Computes a deterministic, code-only fair value (DCF + relative + analyst) on
# page load, surfaces a low/mid/high range, and can store the result for the
# Trading Desk to consume as its primary valuation anchor. Review-only; not
# investment advice; no order is placed.
#
# ── AI Valuation Summary content (fills the slot reserved in the layout block) ─
# The expander FRAME + placeholder were already painted into ``fv_slot`` up in the
# LAYOUT-FIRST PASS (before any blocking fetch). Here we run the (synchronous)
# fair-value compute and write the result into that SAME slot, replacing the
# placeholder in place — no st.rerun(), no layout shift, no second frame.
# ``fv_slot.container()`` re-targets the st.empty() slot, so the result renders at
# its original below-the-tabs position.
from lib.equity_valuation import (
    compute_app_fair_value, store_equity_research_result, fetch_cyclical_band_history,
)
from lib.llm_orchestrator import analyze_equity_fair_value_debate

_fv_lang = st.session_state.get("language", "en")
_debate_key = f"equity_debate_{ticker}"


def _macro_regime_str_p4() -> str:
    _ro = st.session_state.get("macro_regime_result")
    if isinstance(_ro, dict):
        return str(_ro.get("regime", "unknown"))
    if _ro is not None:
        return str(getattr(_ro, "regime", "unknown"))
    return "unknown"


if _fv_key not in st.session_state:
    # Pass the already-fetched peer info dicts so the routed valuation can use
    # growth-matched peer multiples for the EV anchors (Task 3). Falls back to
    # sector-median multiples when peers are unavailable. The cyclical history
    # fetcher (page path only) builds the ≤4y annual PB/PS band for cyclical names;
    # the result is written through to the anchor cache so the network-free
    # ranking / Cockpit paths read the baked band.
    _peers_for_val = globals().get("peer_infos") or None
    st.session_state[_fv_key] = compute_app_fair_value(
        ticker, price, peers=_peers_for_val,
        cyclical_history_fetcher=fetch_cyclical_band_history)
_fv = st.session_state[_fv_key]

_fv_irreconcilable = getattr(_fv, "blend_state", "blended") == "anchors_irreconcilable"


def _render_company_type_badge(_fv) -> None:
    """Render the method-router badge: company type + methods used + excluded
    anchors (Valuation Refactor v1, Task 4). Bilingual; fail-soft."""
    _ctype = getattr(_fv, "company_type", "") or ""
    if not _ctype:
        return
    _type_label = t(f"cockpit_fv_type_{_ctype}")
    _conf = getattr(_fv, "company_type_confidence", "") or ""
    _badge = f"🏷️ {t('cockpit_fv_company_type')}: **{_type_label}**"
    if _conf == "borderline":
        _badge += f"  · _{t('cockpit_fv_borderline')}_"
    _peer_basis = getattr(_fv, "peer_basis", "") or ""
    if _peer_basis:
        _pb_label = (t("cockpit_fv_peer_growth_matched")
                     if _peer_basis == "growth_matched"
                     else t("cockpit_fv_peer_sector_fallback"))
        _badge += f"  · {t('cockpit_fv_peer_basis')}: {_pb_label}"
    st.markdown(_badge)
    _blended = getattr(_fv, "anchors", []) or []
    if _blended:
        _mparts = [f"{str(a.get('name', '')).upper()} ${float(a.get('value', 0.0)):.2f} "
                   f"({a.get('method', a.get('basis', ''))})" for a in _blended]
        st.caption(f"{t('cockpit_fv_methods_used')}: " + " · ".join(_mparts))
    _routing = getattr(_fv, "routing_rationale", "") or ""
    if _routing:
        st.caption(f"{t('cockpit_fv_routing')}: {_routing}")
    _excluded = getattr(_fv, "excluded_anchors", []) or []
    if _excluded:
        _parts = []
        for _a in _excluded:
            _flag = _a.get("flag", "")
            _flbl = (t("cockpit_fv_flag_cycle_distorted")
                     if _flag == "cycle_distorted" else t("cockpit_fv_flag_excluded"))
            _parts.append(f"{str(_a.get('name', '')).upper()} "
                          f"${float(_a.get('value', 0.0)):.2f} ({_flbl})")
        st.caption(f"{t('cockpit_fv_excluded')}: " + " · ".join(_parts))
    # Degradation caveats (e.g. cyclical_band_unavailable / single_anchor_blend).
    _caveats = getattr(_fv, "caveats", []) or []
    if _caveats:
        _clabels = [t(f"cockpit_fv_caveat_{c}") for c in _caveats]
        st.caption(f"⚠️ {t('cockpit_fv_caveats')}: " + " · ".join(_clabels))


with fv_slot.container().expander(t("cockpit_fv_header"), expanded=True):
    _render_company_type_badge(_fv)
    if _fv.fair_value_mid <= 0 and not _fv_irreconcilable:
        st.info(t("cockpit_fv_na"))
    elif _fv_irreconcilable:
        # ── Anchor consistency gate (Task 1): render the irreconcilable state
        # honestly — each anchor side by side with its basis, an explanation
        # line, and NO range bar pretending precision. Bilingual via t().
        st.warning(t("cockpit_fv_irreconcilable"))
        st.caption(t("cockpit_fv_irreconcilable_note"))
        _anchors = list(getattr(_fv, "anchors", []) or [])
        if _anchors:
            _acols = st.columns(len(_anchors))
            for _i, _a in enumerate(_anchors):
                _acols[_i].metric(
                    str(_a.get("name", "")).upper(),
                    f"${float(_a.get('value', 0.0)):.2f}",
                    help=str(_a.get("basis", "")),
                )
                # Mixed-basis warning next to the relative anchor.
                if (str(_a.get("name", "")) == "relative"
                        and getattr(_fv, "peer_pe_basis", "") == "mixed"):
                    _acols[_i].caption(t("cockpit_fv_basis_mixed"))
        st.caption(f"📍 ${price:.2f}  ·  {_fv.methodology}")
        # Still allow hand-off to the Trading Desk: store_equity_research_result
        # propagates the irreconcilable state so the LONG path degrades to a
        # technical-only reference (never a blended mid).
        if st.button(t("cockpit_fv_send_desk"), key=f"fv_send_irr_{ticker}",
                     use_container_width=True):
            store_equity_research_result(ticker, _fv)
            st.success(t("cockpit_fv_sent"))
    else:
        # ── Range bar (plotly) low → mid → high + current price marker ──────────
        _flo, _fmid, _fhi = _fv.fair_value_low, _fv.fair_value_mid, _fv.fair_value_high
        fig_fv = go.Figure()
        fig_fv.add_trace(go.Scatter(
            x=[_flo, _fhi], y=[0, 0], mode="lines",
            line=dict(color="#388bfd", width=10), hoverinfo="skip", showlegend=False,
        ))
        fig_fv.add_trace(go.Scatter(
            x=[_fmid], y=[0], mode="markers+text",
            marker=dict(size=16, color="#3fb950"),
            text=[f"{t('cockpit_fv_mid')} ${_fmid:.2f}"], textposition="top center",
            hoverinfo="skip", showlegend=False,
        ))
        fig_fv.add_trace(go.Scatter(
            x=[price], y=[0], mode="markers+text",
            marker=dict(size=13, color="#f85149", symbol="diamond"),
            text=[f"${price:.2f}"], textposition="bottom center",
            hoverinfo="skip", showlegend=False,
        ))
        apply_layout(fig_fv, title=t("cockpit_fv_range"), height=170)
        fig_fv.update_yaxes(visible=False, showgrid=False, range=[-1, 1])
        fig_fv.update_xaxes(title_text="")
        st.plotly_chart(fig_fv, use_container_width=True)

        # ── Upside (colored) + confidence badge ─────────────────────────────────
        _up = _fv.upside_pct
        _up_color = "#3fb950" if _up > 0.10 else ("#f85149" if _up < -0.10 else "#8b949e")
        _conf_color = {"high": "#3fb950", "medium": "#d29922", "low": "#8b949e"}.get(
            _fv.confidence, "#8b949e")
        _bcols = st.columns(3)
        _bcols[0].markdown(
            f"{t('cockpit_fv_upside')}: "
            f"<span style='color:{_up_color};font-weight:700'>{_up*100:+.1f}%</span>",
            unsafe_allow_html=True,
        )
        _bcols[1].markdown(
            f"{t('cockpit_fv_confidence')}: "
            f"<span style='background:{_conf_color}22;color:{_conf_color};"
            f"border:1px solid {_conf_color}55;padding:2px 9px;border-radius:10px;"
            f"font-weight:600'>{_fv.confidence}</span>",
            unsafe_allow_html=True,
        )
        _bcols[2].caption(
            t("td_data_live") if _fv.data_source == "live" else t("td_data_fixture")
        )
        st.caption(f"{t('cockpit_fv_methodology')}: {_fv.methodology}")

        # ── Individual source contributions ─────────────────────────────────────
        _scols = st.columns(3)
        if _fv.dcf_value is not None:
            _scols[0].metric(t("cockpit_fv_dcf"), f"${_fv.dcf_value:.2f}")
        else:
            # Show the concrete reason DCF is unavailable rather than a bare N/A.
            _scols[0].metric(t("cockpit_fv_dcf"), "N/A")
            _scols[0].caption(_fv.dcf_note or t("cockpit_fv_fcf_unavailable"))
        _scols[1].metric(
            t("cockpit_fv_relative"),
            f"${_fv.relative_value:.2f}" if _fv.relative_value is not None else "N/A")
        # Relative-anchor EPS basis badge (Task 2): forward consensus vs trailing.
        _rbasis = getattr(_fv, "relative_basis", "")
        if _fv.relative_value is not None and _rbasis:
            _basis_label = (t("cockpit_fv_basis_forward") if _rbasis == "forward"
                            else t("cockpit_fv_basis_trailing"))
            _scols[1].caption(f"{t('cockpit_fv_basis')}: {_basis_label}")
        # Visible mixed-basis warning (forward EPS × trailing peer P/E).
        if _fv.relative_value is not None and getattr(_fv, "peer_pe_basis", "") == "mixed":
            _scols[1].caption(t("cockpit_fv_basis_mixed"))
        _scols[2].metric(
            t("cockpit_fv_analyst"),
            (f"${_fv.analyst_target:.2f} (n={_fv.analyst_count})"
             if _fv.analyst_target is not None else "N/A"))
        # Structured analyst pool (Anchor Intel v2, U2): the sell-side target
        # distribution behind the consensus. Surfaced under the analyst metric so a
        # wide pool (which caps confidence — see the analyst_pool_dispersed caveat) is
        # visible. Median is the central estimate that entered the blend.
        _pool = getattr(_fv, "analyst_pool", None)
        if isinstance(_pool, dict):
            _pmd, _phi, _plo = _pool.get("median"), _pool.get("high"), _pool.get("low")
            if _pmd is not None and _phi is not None and _plo is not None:
                _scols[2].caption(
                    f"{t('cockpit_fv_analyst_pool')}: ${_plo:.0f}–${_phi:.0f} "
                    f"(med ${_pmd:.0f}, n={_pool.get('n', 0)})")

        # Epoch stamp (U3) — unobtrusive caption so the anchor's freshness is visible
        # without cluttering the primary cells.
        _capr = getattr(_fv, "computed_at", "") or ""
        if _capr:
            st.caption(f"{t('cockpit_fv_computed_at')}: {_capr[:16].replace('T', ' ')} UTC")

        st.divider()

        # ── Action buttons: Run AI Debate / Update Valuation / Send to Desk ──────
        _bcol1, _bcol2, _bcol3 = st.columns(3)
        if _bcol1.button(t("cockpit_fv_run_debate"), key=f"fv_debate_{ticker}",
                         use_container_width=True):
            with st.spinner(t("cockpit_fv_debate_running")):
                _debate = analyze_equity_fair_value_debate(
                    ticker, _fv,
                    thesis_text=info.get("longBusinessSummary", "")[:600],
                    macro_regime=_macro_regime_str_p4(), lang=_fv_lang,
                )
            st.session_state[_debate_key] = _debate
            # Persist the fair value + debate summary for the Trading Desk.
            _synth = _debate.get(f"synthesis_{_fv_lang}") or _debate.get("synthesis_en", "")
            store_equity_research_result(
                ticker, _fv, debate_summary=_synth,
                analyst_action=_debate.get("analyst_action", ""),
            )

        # Update Valuation — recompute using the user-adjusted DCF intrinsic value
        # from the Financials tab (published to st.session_state["dcf_params"]),
        # then re-run the debate. Disabled when no matching DCF params exist.
        _dcf_params = st.session_state.get("dcf_params")
        _dcf_ready = (
            isinstance(_dcf_params, dict)
            and str(_dcf_params.get("ticker", "")).upper().strip() == ticker
            and float(_dcf_params.get("intrinsic_value") or 0) > 0
        )
        if _bcol2.button(t("cockpit_fv_update"), key=f"fv_update_{ticker}",
                         use_container_width=True, disabled=not _dcf_ready):
            with st.spinner(t("cockpit_fv_running")):
                # X3 (fix round 2): a recompute MUST pass the same routed inputs as
                # the initial render (line ~668) — the cyclical band fetcher AND the
                # peer list — otherwise it silently strips the cyclical PB/PS band
                # (degrading to analyst-only) and the growth-matched peer basis.
                _peers_upd = globals().get("peer_infos") or None
                _fv2 = compute_app_fair_value(
                    ticker, price,
                    dcf_override=float(_dcf_params["intrinsic_value"]),
                    peers=_peers_upd,
                    cyclical_history_fetcher=fetch_cyclical_band_history,
                )
                st.session_state[_fv_key] = _fv2
                _dbt = analyze_equity_fair_value_debate(
                    ticker, _fv2,
                    thesis_text=info.get("longBusinessSummary", "")[:600],
                    macro_regime=_macro_regime_str_p4(), lang=_fv_lang,
                )
                st.session_state[_debate_key] = _dbt
                _synth = _dbt.get(f"synthesis_{_fv_lang}") or _dbt.get("synthesis_en", "")
                store_equity_research_result(
                    ticker, _fv2, debate_summary=_synth,
                    analyst_action=_dbt.get("analyst_action", ""),
                )
            st.toast(t("cockpit_fv_updated"))
            st.rerun()

        if _bcol3.button(t("cockpit_fv_send_desk"), key=f"fv_send_{ticker}",
                         use_container_width=True):
            store_equity_research_result(ticker, _fv)
            st.success(t("cockpit_fv_sent"))

        if not _dcf_ready:
            st.caption(t("cockpit_fv_update_hint"))

        # ── Render a previously-run debate (persists across reruns) ─────────────
        _debate = st.session_state.get(_debate_key)
        if _debate:
            # If the debate fell back (no API key / bad JSON / API error), show the
            # concrete reason instead of silently rendering the fallback prose.
            if _debate.get("debate_status") == "fallback":
                st.warning(
                    f"{t('cockpit_fv_debate_failed')}: "
                    f"{_debate.get('debate_error') or t('cockpit_fv_na')}"
                )

            def _dbi(field: str) -> str:
                return (_debate.get(f"{field}_{_fv_lang}")
                        or _debate.get(f"{field}_en", "") or "")
            st.markdown(f"**🟢 {t('cockpit_fv_bull')}**")
            st.write(_dbi("bull_case"))
            st.markdown(f"**🔴 {t('cockpit_fv_bear')}**")
            st.write(_dbi("bear_case"))
            st.markdown(f"**⚠️ {t('cockpit_fv_risk')}**")
            st.write(_dbi("risk_factors"))
            st.markdown(f"**🔍 {t('cockpit_fv_synthesis')}**")
            st.write(_dbi("synthesis"))
            _el = _debate.get("endorsed_fair_value_low")
            _eh = _debate.get("endorsed_fair_value_high")
            _act = _debate.get("analyst_action", "")
            st.caption(
                f"{t('cockpit_fv_endorsed')}: ${_el} – ${_eh}  ·  "
                f"{t('cockpit_fv_action')}: **{_act}**"
            )
