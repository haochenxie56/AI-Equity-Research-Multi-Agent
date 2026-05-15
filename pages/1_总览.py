"""Page 1 — 总览（Orchestrator）"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from ui_utils import (
    apply_theme, render_sidebar, load_info, load_ohlcv, load_ohlcv_multi,
    load_financials, load_cashflow, load_earnings,
    fmt_large, fmt_pct, fmt_val, download_report_button, page_header, style_df,
)

st.set_page_config(page_title="总览", page_icon="🔭", layout="wide")
apply_theme()
ticker = render_sidebar()

st.title("🔭 总览 — 完整研究流程")
page_header()

if not ticker:
    st.info("请在左侧输入股票代码（如 NVDA、AAPL、MSFT）开始分析")
    st.stop()

# ── Company header ────────────────────────────────────────────────────────────
with st.spinner(f"Loading {ticker}..."):
    info = load_info(ticker)

name   = info.get("longName", ticker)
price  = info.get("currentPrice") or info.get("regularMarketPrice", 0)
prev   = info.get("regularMarketPreviousClose", price)
chg    = (price - prev) / prev * 100 if prev else 0
arrow  = "▲" if chg >= 0 else "▼"
color  = "green" if chg >= 0 else "red"

st.markdown(
    f"### {name} &nbsp; <code>{ticker}</code> &nbsp; "
    f"<b>${price:.2f}</b> &nbsp; <span style='color:{color}'>{arrow} {chg:+.2f}%</span>",
    unsafe_allow_html=True,
)
st.caption(
    f"{info.get('sector','N/A')} / {info.get('industry','N/A')} | "
    f"{info.get('exchange','N/A')} | 员工: {info.get('fullTimeEmployees', 'N/A'):,}"
    if isinstance(info.get('fullTimeEmployees'), int) else
    f"{info.get('sector','N/A')} / {info.get('industry','N/A')} | {info.get('exchange','N/A')}"
)
st.divider()

# ── Module selector + Run button ──────────────────────────────────────────────
st.subheader("选择要运行的分析模块")
col1, col2, col3, col4 = st.columns(4)
run_financial = col1.checkbox("📊 财务分析", value=True)
run_technical = col2.checkbox("📉 量价分析", value=True)
run_equity    = col3.checkbox("🏢 个股研究", value=True)
run_earnings  = col4.checkbox("📅 财报日历", value=True)

run_all = st.button("▶ 一键运行完整研究", type="primary", use_container_width=True)

st.divider()

# ── Run pipeline ──────────────────────────────────────────────────────────────
if run_all or any(k in st.session_state for k in [f"overview_done_{ticker}"]):

    progress = st.progress(0, text="准备中...")
    status_box = st.empty()
    results: dict = {}

    # Step 1: Basic info (already loaded)
    progress.progress(15, text="✓ 公司信息")

    # Step 2: Financial
    if run_financial:
        status_box.info("⚙️ 运行财务分析...")
        try:
            fin = load_financials(ticker)
            cf  = load_cashflow(ticker)
            rev_ttm  = fin["Total Revenue"].iloc[0] if "Total Revenue" in fin.columns else None
            gp_ttm   = fin["Gross Profit"].iloc[0]  if "Gross Profit"  in fin.columns else None
            ni_ttm   = fin["Net Income"].iloc[0]    if "Net Income"    in fin.columns else None
            ebitda   = fin["EBITDA"].iloc[0]        if "EBITDA"        in fin.columns else None
            op_cf    = cf["Operating Cash Flow"].iloc[0] if "Operating Cash Flow" in cf.columns else None
            capex    = cf["Capital Expenditure"].iloc[0] if "Capital Expenditure" in cf.columns else None
            fcf_ttm  = (op_cf + capex) if (op_cf and capex) else None
            results["financial"] = dict(
                rev=rev_ttm, gp=gp_ttm, ni=ni_ttm, ebitda=ebitda,
                fcf=fcf_ttm, gm=gp_ttm/rev_ttm if (gp_ttm and rev_ttm) else None,
            )
        except Exception as e:
            results["financial_error"] = str(e)
        progress.progress(40, text="✓ 财务分析完成")

    # Step 3: Technical
    if run_technical:
        status_box.info("⚙️ 运行量价分析...")
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
            from technical import snapshot
            df = load_ohlcv(ticker, "1y")
            snap = snapshot(df)
            results["technical"] = snap
        except Exception as e:
            results["technical_error"] = str(e)
        progress.progress(60, text="✓ 量价分析完成")

    # Step 4: Earnings
    if run_earnings:
        status_box.info("⚙️ 获取财报日历...")
        try:
            cal = load_earnings(ticker)
            results["earnings"] = cal
        except Exception as e:
            results["earnings_error"] = str(e)
        progress.progress(74, text="✓ 财报日历完成")

    # Step 4b: Equity Research Summary
    if run_equity:
        status_box.info("⚙️ 生成个股研究摘要...")
        try:
            gm_v  = (info.get("grossMargins") or 0) * 100
            om_v  = (info.get("operatingMargins") or 0) * 100
            roe_v = (info.get("returnOnEquity") or 0) * 100
            moat_scores = {
                "无形资产": min(5, max(1, int(gm_v / 12))),
                "转换成本": min(5, max(1, int(om_v / 8) + 1)),
                "网络效应": min(5, max(1, 2)),
                "成本优势": min(5, max(1, int(om_v / 10))),
                "高效规模": min(5, max(1, int(roe_v / 15))),
            }
            total_moat = sum(moat_scores.values())
            moat_label = "宽" if total_moat >= 18 else ("窄" if total_moat >= 12 else "无/极窄")
            results["equity"] = {
                "moat_scores": moat_scores,
                "total_moat": total_moat,
                "moat_label": moat_label,
                "analyst_rating": str(info.get("recommendationKey", "N/A")).upper(),
                "target_mean": info.get("targetMeanPrice"),
                "num_analysts": info.get("numberOfAnalystOpinions", 0),
            }
        except Exception as e:
            results["equity_error"] = str(e)
        progress.progress(87, text="✓ 个股研究完成")

    # Step 5: Write summary report
    status_box.info("⚙️ 生成综合报告...")
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        date_pfx = datetime.now().strftime("%Y%m%d")
        fin_r = results.get("financial", {})
        tech_r = results.get("technical", {})
        earn_r = results.get("earnings", {})

        report_lines = [
            f"# Research Overview: {ticker} — {name}",
            f"",
            f"**日期**：{today}  |  **价格**：${price:.2f}  |  **涨跌**：{chg:+.2f}%",
            f"",
            f"---",
            f"",
            f"## 执行摘要",
            f"",
        ]

        if fin_r:
            gm = f"{fin_r.get('gm',0)*100:.1f}%" if fin_r.get('gm') else 'N/A'
            report_lines += [
                f"- 营收（TTM）：{fmt_large(fin_r.get('rev'))}",
                f"- 毛利率：{gm}",
                f"- 净利润（TTM）：{fmt_large(fin_r.get('ni'))}",
                f"- 自由现金流（TTM）：{fmt_large(fin_r.get('fcf'))}",
                f"",
            ]

        if tech_r:
            trend = "多头排列（价格 > SMA20 > SMA50 > SMA200）" if (
                tech_r.get("price",0) > tech_r.get("SMA_20",0) > tech_r.get("SMA_50",0)
            ) else "均线结构需关注"
            report_lines += [
                f"- 当前价：${tech_r.get('price')} | RSI(14)：{tech_r.get('RSI_14')} | ADX：{tech_r.get('ADX')}",
                f"- 趋势结构：{trend}",
                f"- 距52周高点：{tech_r.get('pct_from_52w_high')}%",
                f"",
            ]

        if earn_r and earn_r.get("next_earnings_date"):
            d = earn_r["next_earnings_date"].strftime("%Y-%m-%d")
            days = earn_r.get("days_to_earnings", 0)
            report_lines.append(
                f"- 下次财报：{d}（{'⚠️ ' if abs(days) <= 14 else ''}{days}天{'后' if days >= 0 else '前'}）"
            )
            if earn_r.get("eps_estimate"):
                report_lines.append(f"  - EPS 预期：${earn_r['eps_estimate']:.2f}")
            if earn_r.get("surprise_pct_last") is not None:
                s = earn_r['surprise_pct_last']
                report_lines.append(f"  - 上次EPS惊喜：{'+' if s >= 0 else ''}{s}%")
            report_lines.append("")

        eq_r = results.get("equity", {})
        if eq_r:
            report_lines += [
                f"- 护城河评级：{eq_r.get('moat_label')}（{eq_r.get('total_moat')}/25）",
                f"- 分析师评级：{eq_r.get('analyst_rating', 'N/A')}",
            ]
            if eq_r.get("target_mean"):
                upside_r = (eq_r["target_mean"] / price - 1) * 100 if price else 0
                report_lines.append(f"- 目标价均值：${eq_r['target_mean']:.2f}（{upside_r:+.1f}%，{eq_r.get('num_analysts', 0)}位分析师）")
            report_lines.append("")

        report_lines += [
            f"## 估值快照",
            f"",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| Trailing P/E | {fmt_val(info.get('trailingPE'), decimals=1, suffix='x')} |",
            f"| Forward P/E  | {fmt_val(info.get('forwardPE'),  decimals=1, suffix='x')} |",
            f"| P/S (TTM)    | {fmt_val(info.get('priceToSalesTrailing12Months'), decimals=1, suffix='x')} |",
            f"| EV/EBITDA    | {fmt_val(info.get('enterpriseToEbitda'), decimals=1, suffix='x')} |",
            f"| 市值         | {fmt_large(info.get('marketCap'))} |",
            f"",
            f"---",
            f"",
            f"> **风险提示**：本报告仅供研究参考，不构成投资建议。",
        ]
        report_content = "\n".join(report_lines)

        report_path = Path(__file__).parent.parent / "research" / "stock" / f"{date_pfx}_{ticker}_summary.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_content, encoding="utf-8")
        results["report"] = report_content
        st.session_state[f"overview_done_{ticker}"] = results
    except Exception as e:
        st.warning(f"报告生成遇到问题：{e}")

    progress.progress(100, text="✅ 所有模块运行完成")
    status_box.empty()

# ── Display results ───────────────────────────────────────────────────────────
stored = st.session_state.get(f"overview_done_{ticker}", {})
if not stored:
    st.info("点击「▶ 一键运行完整研究」开始分析")
    st.stop()

# Key metrics cards
st.subheader("关键指标一览")
m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("市值",        fmt_large(info.get("marketCap")))
m2.metric("Trailing P/E", fmt_val(info.get("trailingPE"), decimals=1, suffix="x"))
m3.metric("Forward P/E",  fmt_val(info.get("forwardPE"),  decimals=1, suffix="x"))
m4.metric("毛利率",       fmt_pct(info.get("grossMargins")))
m5.metric("ROE",          fmt_pct(info.get("returnOnEquity")))
m6.metric("Beta",         fmt_val(info.get("beta"), decimals=2))

st.divider()

# Financial metrics
fin_r = stored.get("financial", {})
if fin_r:
    st.subheader("财务快照（TTM）")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("营收",     fmt_large(fin_r.get("rev")))
    f2.metric("毛利率",   f"{fin_r.get('gm',0)*100:.1f}%" if fin_r.get("gm") else "N/A")
    f3.metric("净利润",   fmt_large(fin_r.get("ni")))
    f4.metric("自由现金流", fmt_large(fin_r.get("fcf")))
    st.divider()

# Technical metrics
tech_r = stored.get("technical", {})
if tech_r:
    st.subheader("技术面快照")
    t1, t2, t3, t4, t5 = st.columns(5)
    t1.metric("RSI(14)",  tech_r.get("RSI_14"))
    t2.metric("ADX",      tech_r.get("ADX"))
    t3.metric("SMA200上方", "✅" if tech_r.get("above_SMA200") else "❌")
    t4.metric("距52W高",  f"{tech_r.get('pct_from_52w_high')}%")
    t5.metric("量比(20D)", f"{tech_r.get('Vol_ratio_20d')}x")
    st.divider()

# Earnings
earn_r = stored.get("earnings", {})
if earn_r and earn_r.get("next_earnings_date"):
    days = earn_r.get("days_to_earnings", 0)
    d_str = earn_r["next_earnings_date"].strftime("%Y-%m-%d")
    if abs(days) <= 14:
        st.warning(f"⚠️ 财报窗口期：{d_str}（{days}天{'后' if days >= 0 else '前'}）｜EPS预期：${earn_r.get('eps_estimate', 'N/A'):.2f}" if earn_r.get('eps_estimate') else f"⚠️ 财报日：{d_str}（{days}天{'后' if days >= 0 else '前'}）")
    else:
        st.info(f"📅 下次财报：{d_str}（{days}天{'后' if days >= 0 else '前'}）｜上次EPS惊喜：{earn_r.get('surprise_pct_last', 'N/A')}%")
    st.divider()

# Equity summary
equity_r = stored.get("equity", {})
if equity_r:
    st.subheader("个股研究摘要")
    eq1, eq2, eq3 = st.columns(3)
    eq1.metric("护城河评级", f"{equity_r.get('moat_label')}（{equity_r.get('total_moat')}/25）")
    eq2.metric("分析师评级", equity_r.get("analyst_rating", "N/A"))
    if equity_r.get("target_mean"):
        target_p = equity_r["target_mean"]
        upside_p = (target_p / price - 1) * 100 if price else 0
        eq3.metric("目标价均值", f"${target_p:.2f}", delta=f"{upside_p:+.1f}%")
    st.divider()

# Comprehensive radar chart
st.subheader("📡 综合雷达图")

_SECTOR_ETF = {
    "Technology": "XLK", "Communication Services": "XLC",
    "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP",
    "Energy": "XLE", "Financial Services": "XLF",
    "Healthcare": "XLV", "Industrials": "XLI",
    "Basic Materials": "XLB", "Real Estate": "XLRE", "Utilities": "XLU",
}
_sector  = info.get("sector", "")
_etf_sym = _SECTOR_ETF.get(_sector, "SPY")
tech_r   = stored.get("technical", {})
fin_r    = stored.get("financial", {})

# 1. 行业景气：sector ETF 3M return vs SPY
_s_score, _s_tip = 3, f"行业 ETF: {_etf_sym}"
try:
    _etf_dfs = load_ohlcv_multi((_etf_sym, "SPY"), "6mo")
    if _etf_sym in _etf_dfs and "SPY" in _etf_dfs and len(_etf_dfs[_etf_sym]) >= 63:
        _er = (_etf_dfs[_etf_sym]["Close"].iloc[-1] / _etf_dfs[_etf_sym]["Close"].iloc[-63] - 1) * 100
        _sr = (_etf_dfs["SPY"]["Close"].iloc[-1]    / _etf_dfs["SPY"]["Close"].iloc[-63]    - 1) * 100
        _ex = _er - _sr
        _s_score = 5 if _ex > 10 else 4 if _ex > 5 else 3 if _ex > 0 else 2 if _ex > -5 else 1
        _s_tip = f"{_etf_sym} 3M超额收益 vs SPY: {_ex:+.1f}%（{_er:.1f}% vs {_sr:.1f}%）"
except Exception:
    pass

# 2. 财务健康：ROE + 毛利率 + FCF质量
_gm_v  = (info.get("grossMargins") or 0) * 100
_roe_v = (info.get("returnOnEquity") or 0) * 100
_roe_s = 5 if _roe_v > 30 else 4 if _roe_v > 20 else 3 if _roe_v > 15 else 2 if _roe_v > 10 else 1
_gm_s  = 5 if _gm_v > 60 else 4 if _gm_v > 40 else 3 if _gm_v > 25 else 2 if _gm_v > 10 else 1
_fcf_s = 3
if fin_r.get("fcf") and fin_r.get("ni") and fin_r["ni"] and fin_r["ni"] != 0:
    _fcf_ni = fin_r["fcf"] / fin_r["ni"]
    _fcf_s  = 5 if _fcf_ni > 1.2 else 4 if _fcf_ni > 1.0 else 3 if _fcf_ni > 0.7 else 2 if _fcf_ni > 0 else 1
_h_score = round((_roe_s + _gm_s + _fcf_s) / 3, 1)
_h_tip   = f"ROE {_roe_v:.1f}% (→{_roe_s}/5), 毛利率 {_gm_v:.1f}% (→{_gm_s}/5), FCF质量 (→{_fcf_s}/5)"

# 3. 估值吸引力：Fwd P/E 绝对水平
_fwd_pe = info.get("forwardPE")
if _fwd_pe and _fwd_pe > 0:
    _v_score = 5 if _fwd_pe < 15 else 4 if _fwd_pe < 20 else 3 if _fwd_pe < 25 else 2 if _fwd_pe < 35 else 1
    _v_tip   = f"Fwd P/E {_fwd_pe:.1f}x（<15→5分, <20→4分, <25→3分, <35→2分）"
else:
    _v_score, _v_tip = 3, "Fwd P/E 不可用，默认中性"

# 4. 技术面：RSI + ADX + SMA200
if tech_r:
    _rsi = tech_r.get("RSI_14", 50)
    _adx = tech_r.get("ADX", 20)
    _a200 = bool(tech_r.get("above_SMA200", False))
    _rsi_s = 5 if 50 <= _rsi <= 65 else 4 if 40 <= _rsi <= 70 else 3 if 35 <= _rsi <= 75 else 2 if 30 <= _rsi <= 80 else 1
    _adx_s = 5 if _adx > 30 else 4 if _adx > 25 else 3 if _adx > 20 else 2 if _adx > 15 else 1
    _t_score = round(min(5, (_rsi_s + _adx_s) / 2 + (0.5 if _a200 else 0)), 1)
    _t_tip   = f"RSI {_rsi:.1f} (→{_rsi_s}/5), ADX {_adx:.1f} (→{_adx_s}/5), SMA200 {'上方✓' if _a200 else '下方✗'}"
else:
    _t_score, _t_tip = 3, "技术模块未运行，默认中性"

# 5. 商业模式：毛利率绝对值
_b_score = 5 if _gm_v > 70 else 4 if _gm_v > 55 else 3 if _gm_v > 40 else 2 if _gm_v > 25 else 1
_b_tip   = f"毛利率 {_gm_v:.1f}%（>70%→5分, >55%→4分, >40%→3分, >25%→2分）"

_dims = ["行业景气", "财务健康", "估值吸引力", "技术面", "商业模式"]
_vals = [_s_score, _h_score, _v_score, _t_score, _b_score]
_tips = [_s_tip,   _h_tip,   _v_tip,   _t_tip,   _b_tip  ]

_radar_col, _score_col = st.columns([3, 2])
with _radar_col:
    _fig_r = go.Figure(go.Scatterpolar(
        r=_vals + [_vals[0]],
        theta=_dims + [_dims[0]],
        customdata=_tips + [_tips[0]],
        fill="toself",
        fillcolor="rgba(77,166,255,0.18)",
        line=dict(color="#4da6ff", width=2),
        hovertemplate="<b>%{theta}</b>: %{r:.1f}/5<br><i>%{customdata}</i><extra></extra>",
        mode="lines+markers",
        marker=dict(size=8, color="#4da6ff"),
    ))
    _r_dark = st.session_state.get("dark_mode", True)
    _r_tpl  = "plotly_dark" if _r_dark else "plotly_white"
    _r_txt  = "#8b949e"     if _r_dark else "#1f2328"
    _r_pbg  = "rgba(0,0,0,0)" if _r_dark else "#ffffff"
    _fig_r.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 5], tickvals=[1, 2, 3, 4, 5],
                            tickfont=dict(size=9, color=_r_txt)),
            angularaxis=dict(tickfont=dict(size=12, color=_r_txt)),
            bgcolor="rgba(0,0,0,0)",
        ),
        showlegend=False,
        height=360,
        margin=dict(l=60, r=60, t=20, b=20),
        paper_bgcolor=_r_pbg,
        template=_r_tpl,
        font=dict(color=_r_txt),
    )
    st.plotly_chart(_fig_r, use_container_width=True)

with _score_col:
    st.caption("鼠标悬停图表各顶点查看评分依据")
    _score_df = pd.DataFrame(
        [{"维度": d, "分值": f"{v:.1f}/5", "说明": t} for d, v, t in zip(_dims, _vals, _tips)]
    ).set_index("维度")
    st.dataframe(style_df(_score_df), use_container_width=True, height=230)
    _overall = round(sum(_vals) / len(_vals), 1)
    st.metric("综合评分", f"{_overall:.1f} / 5.0",
              delta="优质" if _overall >= 3.5 else ("中性" if _overall >= 2.5 else "注意风险"),
              delta_color="normal" if _overall >= 3.5 else ("off" if _overall >= 2.5 else "inverse"))
st.divider()

# Report
if stored.get("report"):
    st.subheader("综合报告")
    st.markdown(stored["report"])
    st.divider()
    date_pfx = datetime.now().strftime("%Y%m%d")
    download_report_button(stored["report"], f"{date_pfx}_{ticker}_summary.md")
