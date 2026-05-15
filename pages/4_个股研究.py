"""Page 4 — 个股研究（Equity Research）"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from ui_utils import (
    apply_theme, render_sidebar, load_info, load_ohlcv, load_ohlcv_multi, load_earnings,
    fmt_large, fmt_pct, fmt_val, apply_layout, download_report_button, page_header,
    translate_to_chinese, render_table, load_news,
)


def _get_default_peers(ticker: str, info: dict) -> str:
    """Guess default peers based on sector/industry."""
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

st.set_page_config(page_title="个股研究", page_icon="🏢", layout="wide")
apply_theme()
ticker = render_sidebar()

st.title("🏢 个股研究")
page_header()
if not ticker:
    st.info("请在左侧输入股票代码（如 NVDA、AAPL、MSFT）开始分析")
    st.stop()

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner(f"Loading {ticker}..."):
    info    = load_info(ticker)
    cal     = load_earnings(ticker)
    ohlcv   = load_ohlcv(ticker, "1y")

name     = info.get("longName", ticker)
price    = info.get("currentPrice") or info.get("regularMarketPrice", 0)
prev     = info.get("regularMarketPreviousClose", price)
chg      = (price - prev) / prev * 100 if prev else 0
arrow    = "▲" if chg >= 0 else "▼"
color    = "green" if chg >= 0 else "red"

st.markdown(
    f"### {name} &nbsp; `{ticker}` &nbsp; **${price:.2f}** "
    f"<span style='color:{color}'>{arrow} {chg:+.2f}%</span>",
    unsafe_allow_html=True,
)
st.caption(
    f"**{info.get('sector','N/A')}** / {info.get('industry','N/A')} | "
    f"{info.get('exchange','N/A')} | 员工: {info.get('fullTimeEmployees', 'N/A')}"
)
st.divider()

# ── Earnings banner ───────────────────────────────────────────────────────────
if cal.get("next_earnings_date"):
    d_str = cal["next_earnings_date"].strftime("%Y-%m-%d")
    days  = cal.get("days_to_earnings", 0)
    eps_e = f" | EPS预期 ${cal['eps_estimate']:.2f}" if cal.get("eps_estimate") else ""
    surp  = f" | 上次惊喜 {'+' if (cal.get('surprise_pct_last') or 0) >= 0 else ''}{cal.get('surprise_pct_last','N/A')}%" if cal.get("surprise_pct_last") is not None else ""
    banner = f"📅 下次财报：**{d_str}**（{days}天{'后' if days >= 0 else '前'}）{eps_e}{surp}"
    if 0 <= days <= 14:
        st.warning(f"⚠️ 财报窗口期 — {banner}")
    elif days < 0 and abs(days) <= 7:
        st.info(f"🗓️ 财报刚公布 — {banner}")
    else:
        st.info(banner)

# ── Key metrics ───────────────────────────────────────────────────────────────
m = st.columns(6)
m[0].metric("市值",       fmt_large(info.get("marketCap")))
m[1].metric("Trailing P/E", fmt_val(info.get("trailingPE"), decimals=1, suffix="x"))
m[2].metric("Forward P/E",  fmt_val(info.get("forwardPE"),  decimals=1, suffix="x"))
m[3].metric("毛利率",       fmt_pct(info.get("grossMargins")))
m[4].metric("ROE",          fmt_pct(info.get("returnOnEquity")))
m[5].metric("分析师评级",   str(info.get("recommendationKey", "N/A")).upper())
st.divider()

# ── Main layout: left = moat radar, right = peer comparison ───────────────────
left_col, right_col = st.columns([1, 2])

with left_col:
    st.subheader("🏰 护城河评估")
    st.caption("根据财务指标自动估算，可手动调整")

    # Auto-estimate moat scores from financials
    gm    = (info.get("grossMargins") or 0) * 100
    om    = (info.get("operatingMargins") or 0) * 100
    roe   = (info.get("returnOnEquity") or 0) * 100
    rnd_r = (info.get("researchDevelopmentToRevenue") or 0) * 100

    default_scores = {
        "无形资产\n(品牌/专利)": min(5, max(1, int(gm / 12))),
        "转换成本":              min(5, max(1, int(om / 8) + 1)),
        "网络效应":              min(5, max(1, 2)),
        "成本优势":              min(5, max(1, int(om / 10))),
        "高效规模":              min(5, max(1, int(roe / 15))),
    }

    scores = {}
    for dim, default_val in default_scores.items():
        scores[dim] = st.slider(dim, 1, 5, default_val, key=f"moat_{dim}")

    # Radar chart
    dims   = list(scores.keys())
    vals   = list(scores.values())
    _dark  = st.session_state.get("dark_mode", True)
    _rbg   = "rgba(0,0,0,0)" if _dark else "#ffffff"
    _rtpl  = "plotly_dark"   if _dark else "plotly_white"
    _rtxt  = "#8b949e"        if _dark else "#1f2328"
    _rgrid = "#21262d"        if _dark else "#d0d7de"
    fig_r  = go.Figure(go.Scatterpolar(
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
                visible=True, range=[0, 5], tickvals=[1,2,3,4,5],
                gridcolor=_rgrid, tickfont=dict(color=_rtxt),
            ),
            angularaxis=dict(
                tickfont=dict(size=11, color=_rtxt),
                gridcolor=_rgrid,
            ),
        ),
        showlegend=False,
        height=320,
        margin=dict(l=40, r=40, t=30, b=30),
        paper_bgcolor=_rbg,
        plot_bgcolor=_rbg,
        template=_rtpl,
        font=dict(color=_rtxt),
        hoverlabel=dict(
            bgcolor="#ffffff" if not _dark else "#1c2128",
            font_color="#1f2328" if not _dark else "#e6edf3",
        ),
    )
    st.plotly_chart(fig_r, use_container_width=True)

    total_moat = sum(vals)
    moat_label = "宽" if total_moat >= 18 else ("窄" if total_moat >= 12 else "无/极窄")
    st.metric("护城河综合评级", f"{moat_label}（{total_moat}/25）")

with right_col:
    st.subheader("📊 同业对比")

    # Peer tickers
    peer_str = st.text_input(
        "同业标的（逗号分隔）",
        value=", ".join((info.get("companyOfficers") or [])[0:0]) or _get_default_peers(ticker, info),
        key="peer_input",
    )
    peer_list = [t.strip().upper() for t in peer_str.split(",") if t.strip()]
    all_comp  = [ticker] + peer_list

    with st.spinner("加载同业数据..."):
        peer_data = []
        for t in all_comp[:8]:
            try:
                i = load_info(t)
                peer_data.append({
                    "Ticker":   t,
                    "P/S":      i.get("priceToSalesTrailing12Months") or 0,
                    "Fwd P/E":  i.get("forwardPE") or 0,
                    "毛利率%":  (i.get("grossMargins") or 0) * 100,
                    "营业利润率%": (i.get("operatingMargins") or 0) * 100,
                    "ROE%":     (i.get("returnOnEquity") or 0) * 100,
                })
            except Exception:
                pass

    if peer_data:
        peer_df = pd.DataFrame(peer_data).set_index("Ticker")

        metric_choice = st.selectbox("对比指标", ["毛利率%","营业利润率%","ROE%","P/S","Fwd P/E"])
        colors = ["#4da6ff" if t == ticker else "#6c757d" for t in peer_df.index]

        fig_p = go.Figure(go.Bar(
            x=peer_df.index,
            y=peer_df[metric_choice],
            marker_color=colors,
            text=[f"{v:.1f}" for v in peer_df[metric_choice]],
            textposition="outside",
        ))
        suffix = "%" if "%" in metric_choice else "x"
        apply_layout(fig_p, title=f"同业对比 — {metric_choice}", height=300)
        fig_p.update_yaxes(title_text=metric_choice)
        st.plotly_chart(fig_p, use_container_width=True)

        # Pre-format peer_df values for render_table:
        # % columns get +/- sign for color coding; ratio columns get "x" suffix
        _pct_cols  = [c for c in peer_df.columns if "%" in c]
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

st.divider()

# ── Business description ──────────────────────────────────────────────────────
with st.expander("📖 公司业务描述", expanded=False):
    raw = info.get("longBusinessSummary", "")
    st.markdown(translate_to_chinese(raw) if raw else "暂无描述")

st.divider()

# ── News & Sentiment ──────────────────────────────────────────────────────────
st.subheader("📰 近期新闻与市场情绪")

_dark     = st.session_state.get("dark_mode", True)
_pos_col  = "#3fb950"
_neg_col  = "#f85149"
_neu_col  = "#8b949e"
_bd_col   = "#30363d" if _dark else "#d0d7de"
_t0_col   = "#e6edf3" if _dark else "#1f2328"
_t1_col   = "#8b949e" if _dark else "#57606a"

with st.spinner("加载新闻数据..."):
    _news = load_news(ticker, days=7)

_has_finnhub = bool(__import__("os").getenv("FINNHUB_API_KEY", ""))

if not _news:
    if not _has_finnhub:
        st.info(
            "💡 配置 `FINNHUB_API_KEY` 环境变量后可显示新闻情绪分析。\n\n"
            "免费注册：https://finnhub.io/register"
        )
    else:
        st.info("过去7天暂无新闻数据")
else:
    # ── Sentiment metrics ─────────────────────────────────────────────────────
    _scores   = [a["sentiment"] for a in _news]
    _total    = len(_scores)
    _pos_n    = sum(1 for s in _scores if s >  0.2)
    _neu_n    = sum(1 for s in _scores if -0.2 <= s <= 0.2)
    _neg_n    = sum(1 for s in _scores if s < -0.2)
    _avg_s    = sum(_scores) / _total
    _avg_lbl  = "正面 🟢" if _avg_s > 0.2 else ("负面 🔴" if _avg_s < -0.2 else "中性 ⚪")

    _mc1, _mc2, _mc3 = st.columns(3)
    _mc1.metric("新闻数量", f"{_total} 条", "过去 7 天")
    _mc2.metric("情绪均值", f"{_avg_s:+.2f}", _avg_lbl)
    _mc3.metric(
        "情绪分布",
        f"正 {_pos_n} / 中 {_neu_n} / 负 {_neg_n}",
        f"{_pos_n/_total*100:.0f}% 正面" if _total else "",
    )

    # ── Sentiment trend chart ─────────────────────────────────────────────────
    from collections import defaultdict
    _daily: dict = defaultdict(list)
    for _a in _news:
        _daily[_a["datetime"][:10]].append(_a["sentiment"])

    _dates    = sorted(_daily.keys())
    _daily_avg = [sum(_daily[d]) / len(_daily[d]) for d in _dates]

    if len(_dates) >= 2:
        _fig_s = go.Figure()
        # Positive fill
        _fig_s.add_trace(go.Scatter(
            x=_dates, y=[max(0.0, v) for v in _daily_avg],
            fill="tozeroy",
            fillcolor="rgba(63,185,80,0.15)",
            line=dict(color="rgba(0,0,0,0)"),
            showlegend=False, hoverinfo="skip",
        ))
        # Negative fill
        _fig_s.add_trace(go.Scatter(
            x=_dates, y=[min(0.0, v) for v in _daily_avg],
            fill="tozeroy",
            fillcolor="rgba(248,81,73,0.15)",
            line=dict(color="rgba(0,0,0,0)"),
            showlegend=False, hoverinfo="skip",
        ))
        # Main sentiment line
        _fig_s.add_trace(go.Scatter(
            x=_dates, y=_daily_avg,
            mode="lines+markers",
            line=dict(color="#4da6ff", width=2),
            marker=dict(size=6),
            name="日均情绪",
            hovertemplate="%{x}<br>情绪均值：%{y:.2f}<extra></extra>",
        ))
        _hline_c = "#484f58" if _dark else "#8c959f"
        _fig_s.add_hline(
            y=0, line_dash="dash", line_color=_hline_c, line_width=1,
            annotation_text="中性基准", annotation_position="right",
            annotation_font_color=_hline_c,
        )
        apply_layout(_fig_s, title="近7天日均情绪趋势", height=240)
        _fig_s.update_yaxes(range=[-1.1, 1.1], title_text="情绪分数")
        st.plotly_chart(_fig_s, use_container_width=True)

    # ── News list ─────────────────────────────────────────────────────────────
    _filter = st.radio(
        "筛选新闻",
        ["全部", "正面", "中性", "负面"],
        horizontal=True,
        key="news_sentiment_filter",
    )

    def _sent_label(s: float) -> str:
        if s >  0.2: return "正面"
        if s < -0.2: return "负面"
        return "中性"

    _filtered = (
        _news if _filter == "全部"
        else [a for a in _news if _sent_label(a["sentiment"]) == _filter]
    )

    if not _filtered:
        st.caption("该情绪分类下暂无新闻")
    else:
        for _a in _filtered[:20]:
            _s = _a["sentiment"]
            _dot = _pos_col if _s > 0.2 else (_neg_col if _s < -0.2 else _neu_col)
            _score_txt = f"{_s:+.2f}"
            _link = (
                f'<a href="{_a["url"]}" target="_blank" '
                f'style="color:{_t0_col};text-decoration:none;font-weight:500;">'
                f'{_a["headline"]}</a>'
                if _a.get("url") else
                f'<span style="color:{_t0_col};font-weight:500;">{_a["headline"]}</span>'
            )
            st.markdown(
                f'<div style="display:flex;align-items:flex-start;'
                f'padding:10px 0;border-bottom:1px solid {_bd_col};">'
                # Dot + score
                f'<div style="flex-shrink:0;width:48px;text-align:center;padding-top:2px;">'
                f'<span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
                f'background:{_dot};margin-bottom:3px;"></span>'
                f'<div style="font-size:0.68rem;color:{_dot};font-weight:600;'
                f'font-family:monospace;">{_score_txt}</div>'
                f'</div>'
                # Headline + meta
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
                with st.expander("摘要", expanded=False):
                    st.caption(_a["summary"])

st.divider()

# ── Generate & download report ────────────────────────────────────────────────
st.subheader("📄 研究报告")
today    = datetime.now().strftime("%Y-%m-%d")
date_pfx = datetime.now().strftime("%Y%m%d")
moat_str = "\n".join([f"| {k.replace(chr(10),' ')} | {'★'*v}{'☆'*(5-v)} ({v}/5) |" for k, v in scores.items()])

# Peer table md
peer_md_rows = "\n".join([
    f"| {r['Ticker']} | {r['毛利率%']:.1f}% | {r['营业利润率%']:.1f}% | {r['ROE%']:.1f}% | {r['P/S']:.1f}x | {r['Fwd P/E']:.1f}x |"
    for r in peer_data
]) if peer_data else "暂无同业数据"

report_md = f"""# Equity Research: {ticker} — {name}

**日期**：{today}
**Ticker**：{ticker} | {info.get('exchange','N/A')}
**行业**：{info.get('sector','N/A')} / {info.get('industry','N/A')}
**分析师 Agent**：equity-research

---

## 执行摘要

{name} 当前股价 ${price:.2f}，市值 {fmt_large(info.get('marketCap'))}。
{'分析师一致评级 **' + str(info.get('recommendationKey','N/A')).upper() + '**，' if info.get('recommendationKey') else ''}
目标价均值 ${info.get('targetMeanPrice', 'N/A')}（{info.get('numberOfAnalystOpinions', 0)} 位分析师）。

---

## 关键财务指标

| 指标 | 数值 |
|------|------|
| 市值 | {fmt_large(info.get('marketCap'))} |
| Trailing P/E | {fmt_val(info.get('trailingPE'), decimals=1, suffix='x')} |
| Forward P/E | {fmt_val(info.get('forwardPE'), decimals=1, suffix='x')} |
| P/S (TTM) | {fmt_val(info.get('priceToSalesTrailing12Months'), decimals=1, suffix='x')} |
| 毛利率 | {fmt_pct(info.get('grossMargins'))} |
| ROE | {fmt_pct(info.get('returnOnEquity'))} |
| Beta | {fmt_val(info.get('beta'), decimals=2)} |

---

## 护城河评估

| 维度 | 评分 |
|------|------|
{moat_str}

**综合评级**：{moat_label}（{total_moat}/25）

---

## 同业对比

| Ticker | 毛利率 | 营业利润率 | ROE | P/S | Fwd P/E |
|--------|--------|-----------|-----|-----|---------|
{peer_md_rows}

---

## 主要风险

1. 估值水平需结合未来增长预期评估
2. 行业竞争格局变化
3. 宏观经济与利率环境

---

> **风险提示**：本报告仅供研究参考，不构成投资建议。
"""

with st.expander("查看完整报告 Markdown", expanded=False):
    st.markdown(report_md)

report_path = Path(__file__).parent.parent / "research" / "stock" / f"{date_pfx}_{ticker}_equity.md"
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(report_md, encoding="utf-8")
download_report_button(report_md, report_path.name)
