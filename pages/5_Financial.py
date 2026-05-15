"""Page 5 — 财务分析（三张表 + DCF + 估值对比）"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from ui_utils import (
    apply_theme, render_sidebar, load_info, load_financials, load_balance_sheet,
    load_cashflow, load_earnings, fmt_large, fmt_pct, fmt_val,
    apply_layout, download_report_button, page_header, render_table, t,
)

st.set_page_config(page_title="Financials", page_icon="📊", layout="wide")
apply_theme()
ticker = render_sidebar()

st.title(t("p5_title"))
page_header()
if not ticker:
    st.info(t("no_ticker"))
    st.stop()

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner(f"Loading {ticker} financials..."):
    info = load_info(ticker)
    cal  = load_earnings(ticker)
    try:
        fin = load_financials(ticker)
        bs  = load_balance_sheet(ticker)
        cf  = load_cashflow(ticker)
        has_data = True
    except Exception as e:
        st.error(f"{t('loading_failed')}: {e}")
        has_data = False

name  = info.get("longName", ticker)
price = info.get("currentPrice") or info.get("regularMarketPrice", 0)

st.markdown(f"### {name} &nbsp; `{ticker}` &nbsp; **${price:.2f}**")

# Earnings warning
if cal.get("next_earnings_date"):
    days = cal.get("days_to_earnings", 0)
    if 0 <= days <= 14:
        st.warning(f"⚠️ Earnings window: {cal['next_earnings_date'].strftime('%Y-%m-%d')} — {days}d out")

st.divider()

if not has_data:
    st.stop()

# ── Helper: format df for display ─────────────────────────────────────────────
def fmt_df_billions(df: pd.DataFrame, key_rows: list) -> pd.DataFrame:
    available = [r for r in key_rows if r in df.columns]
    sub = df[available].copy()
    display = sub.T.copy()
    for col in display.columns:
        display[col] = display[col].apply(
            lambda x: f"${x/1e9:.2f}B"  if pd.notna(x) and abs(x) >= 1e9
            else     (f"${x/1e6:.1f}M"  if pd.notna(x) and abs(x) >= 1e6
            else     (f"{x:.2f}"         if pd.notna(x) else "N/A"))
        )
    return display


def bar_trend(df: pd.DataFrame, col: str, title: str, color: str = "#4da6ff", pct: bool = False):
    if col not in df.columns:
        return None
    s = df[col].dropna()
    if s.empty:
        return None
    years = [str(d)[:7] for d in s.index]
    vals  = [v / 1e9 if not pct else v * 100 for v in s.values]
    fig = go.Figure(go.Bar(x=years, y=vals, marker_color=color,
                           text=[f"{v:.1f}" for v in vals], textposition="outside"))
    ylabel = "%" if pct else "B USD"
    apply_layout(fig, title=title, height=280)
    fig.update_yaxes(title_text=ylabel)
    return fig


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([t("p5_tab1"), t("p5_tab2"), t("p5_tab3")])

# ════════════════════════════════════════════════════════════════════════════════
# TAB 1: 三张表
# ════════════════════════════════════════════════════════════════════════════════
with tab1:
    stmt_tab1, stmt_tab2, stmt_tab3 = st.tabs([t("p5_is"), t("p5_bs"), t("p5_cf")])

    # ── Income Statement ──────────────────────────────────────────────────────
    with stmt_tab1:
        IS_KEYS = ["Total Revenue", "Gross Profit", "Operating Income",
                   "Net Income", "EBITDA", "Basic EPS", "Diluted EPS"]
        st.subheader(t("p5_is_full"))
        col_tbl, col_chart = st.columns([1, 1])

        with col_tbl:
            disp = fmt_df_billions(fin, IS_KEYS)
            render_table(disp)

        with col_chart:
            metric = st.selectbox(t("p5_trend_metric"), [k for k in IS_KEYS if k in fin.columns], key="is_metric")
            is_pct = metric in ("Basic EPS", "Diluted EPS")
            divisor = 1 if is_pct else 1e9
            if metric in fin.columns:
                s = fin[metric].dropna()
                fig = go.Figure(go.Bar(
                    x=[str(d)[:7] for d in s.index],
                    y=[v / divisor for v in s.values],
                    marker_color=["#26a69a" if v >= 0 else "#ef5350" for v in s.values],
                    text=[f"{v/divisor:.2f}" for v in s.values],
                    textposition="outside",
                ))
                apply_layout(fig, title=metric, height=280)
                fig.update_yaxes(title_text="USD" if not is_pct else "EPS")
                st.plotly_chart(fig, use_container_width=True)

        # Margin trend
        if all(k in fin.columns for k in ["Total Revenue","Gross Profit"]):
            st.subheader(t("p5_margin_trend"))
            margin_fig = go.Figure()
            rev = fin["Total Revenue"]
            for col_n, color, label in [
                ("Gross Profit",     "#4da6ff", "Gross Margin"),
                ("Operating Income", "#51cf66", "Op. Margin"),
                ("Net Income",       "#ffd43b", "Net Margin"),
            ]:
                if col_n in fin.columns:
                    margin = fin[col_n] / rev * 100
                    margin_fig.add_trace(go.Scatter(
                        x=[str(d)[:7] for d in margin.index],
                        y=margin.values,
                        name=label, line=dict(color=color, width=2),
                        mode="lines+markers",
                        hovertemplate=f"{label}: %{{y:.1f}}%<extra></extra>",
                    ))
            apply_layout(margin_fig, title=t("p5_margin_trend"), height=280)
            margin_fig.update_yaxes(title_text="%")
            st.plotly_chart(margin_fig, use_container_width=True)

    # ── Balance Sheet ─────────────────────────────────────────────────────────
    with stmt_tab2:
        BS_KEYS = ["Total Assets","Total Liabilities Net Minority Interest","Stockholders Equity",
                   "Total Debt","Cash And Cash Equivalents","Goodwill","Total Current Assets",
                   "Total Current Liabilities"]
        st.subheader(t("p5_bs_full"))
        col_tbl, col_chart = st.columns([1, 1])

        with col_tbl:
            disp = fmt_df_billions(bs, BS_KEYS)
            render_table(disp)

        with col_chart:
            if "Total Assets" in bs.columns and "Stockholders Equity" in bs.columns:
                years  = [str(d)[:7] for d in bs.index]
                assets = bs.get("Total Assets", pd.Series()).fillna(0) / 1e9
                equity = bs.get("Stockholders Equity", pd.Series()).fillna(0) / 1e9
                debt   = bs.get("Total Debt", pd.Series()).fillna(0) / 1e9
                fig_bs = go.Figure()
                fig_bs.add_trace(go.Bar(x=years, y=equity.values, name="Stockholders Equity", marker_color="#51cf66"))
                fig_bs.add_trace(go.Bar(x=years, y=debt.values,   name="Total Debt",          marker_color="#ef5350"))
                fig_bs.update_layout(barmode="stack")
                apply_layout(fig_bs, title=t("p5_cap_struct"), height=280)
                st.plotly_chart(fig_bs, use_container_width=True)

        if "Total Current Assets" in bs.columns and "Total Current Liabilities" in bs.columns:
            st.subheader(t("p5_liq_ratio"))
            cr = bs["Total Current Assets"] / bs["Total Current Liabilities"]
            fig_cr = go.Figure(go.Scatter(
                x=[str(d)[:7] for d in cr.index], y=cr.values,
                mode="lines+markers", line=dict(color="#cc5de8", width=2),
            ))
            fig_cr.add_hline(y=1, line_dash="dash", line_color="orange", annotation_text="1.0x")
            apply_layout(fig_cr, title="Current Ratio", height=240)
            st.plotly_chart(fig_cr, use_container_width=True)

    # ── Cash Flow ─────────────────────────────────────────────────────────────
    with stmt_tab3:
        CF_KEYS = ["Operating Cash Flow","Capital Expenditure","Free Cash Flow",
                   "Repurchase Of Capital Stock","Cash Dividends Paid"]
        st.subheader(t("p5_cf_full"))
        col_tbl, col_chart = st.columns([1, 1])

        with col_tbl:
            disp = fmt_df_billions(cf, CF_KEYS)
            render_table(disp)

        with col_chart:
            if "Operating Cash Flow" in cf.columns:
                years = [str(d)[:7] for d in cf.index]
                op_cf = cf.get("Operating Cash Flow", pd.Series()).fillna(0) / 1e9
                capex = cf.get("Capital Expenditure", pd.Series()).fillna(0).abs() / 1e9
                fcf_  = op_cf - capex

                fig_cf = go.Figure()
                fig_cf.add_trace(go.Bar(x=years, y=op_cf.values,
                                        name="Operating CF", marker_color="#51cf66", opacity=0.8))
                fig_cf.add_trace(go.Bar(x=years, y=(-capex).values,
                                        name="CapEx", marker_color="#ef5350", opacity=0.8))
                fig_cf.add_trace(go.Scatter(x=years, y=fcf_.values,
                                            name="FCF", mode="lines+markers",
                                            line=dict(color="#ffd43b", width=2.5)))
                fig_cf.update_layout(barmode="relative")
                apply_layout(fig_cf, title="Cash Flow Trend (B USD)", height=300)
                st.plotly_chart(fig_cf, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════════
# TAB 2: 估值分析
# ════════════════════════════════════════════════════════════════════════════════
with tab2:
    col_dcf, col_comps = st.columns([1, 1])

    with col_dcf:
        st.subheader(t("p5_dcf"))

        sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
        from valuation import calc_wacc, dcf_scenarios

        beta   = info.get("beta", 1.0) or 1.0
        shares = info.get("sharesOutstanding", 1e9) or 1e9
        debt   = info.get("totalDebt", 0) or 0
        cash   = info.get("totalCash", 0) or 0
        net_d  = debt - cash

        wacc = calc_wacc(beta=beta)

        base_fcf_auto = 0
        try:
            op_cf_v = cf.get("Operating Cash Flow", pd.Series()).iloc[0] if "Operating Cash Flow" in cf.columns else 0
            capex_v = cf.get("Capital Expenditure", pd.Series()).iloc[0] if "Capital Expenditure" in cf.columns else 0
            base_fcf_auto = max(op_cf_v + capex_v, 0)
        except Exception:
            pass

        with st.form("dcf_form"):
            st.caption(t("p5_dcf_adj"))
            base_fcf_b = st.number_input(t("p5_fcf_b"),
                                          value=round(base_fcf_auto / 1e9, 1), step=0.5,
                                          help="TTM Free Cash Flow, or projected FCF")
            wacc_pct = st.slider("WACC (%)", 6.0, 20.0, round(wacc * 100, 1), 0.5)
            run_dcf  = st.form_submit_button(t("p5_calc_dcf"))

        if run_dcf:
            base_fcf_input = base_fcf_b * 1e9
            if base_fcf_input <= 0:
                st.warning("Base FCF ≤ 0, DCF result is indicative only (using EBITDA proxy)")
                try:
                    ebitda_v = fin.get("EBITDA", pd.Series()).iloc[0] if "EBITDA" in fin.columns else 0
                    base_fcf_input = max(ebitda_v * 0.5, 1e8)
                except Exception:
                    base_fcf_input = 1e8

            scenarios_r = dcf_scenarios(
                base_fcf=base_fcf_input,
                wacc=wacc_pct / 100,
                shares_outstanding=shares,
                net_debt=net_d,
                current_price=price,
            )

            scen_names = ["bear", "base", "bull"]
            iv_vals    = [scenarios_r[s].intrinsic_value for s in scen_names]
            premiums   = [scenarios_r[s].implied_premium * 100 for s in scen_names]
            colors_dcf = ["#ef5350", "#ffd43b", "#51cf66"]

            fig_dcf = go.Figure()
            fig_dcf.add_trace(go.Bar(
                x=["Bear","Base","Bull"],
                y=iv_vals,
                marker_color=colors_dcf,
                text=[f"${v:.0f}" for v in iv_vals],
                textposition="outside",
                name="Intrinsic Value",
            ))
            _hline_col = "white" if st.session_state.get("dark_mode", True) else "#1f2328"
            fig_dcf.add_hline(y=price, line_dash="dash", line_color=_hline_col,
                              annotation_text=f"Current ${price:.0f}", annotation_position="right")
            apply_layout(fig_dcf, title=f"DCF Intrinsic Value vs Current (WACC={wacc_pct}%)", height=320)
            fig_dcf.update_yaxes(title_text="USD/share")
            st.plotly_chart(fig_dcf, use_container_width=True)

            for name_s, r in scenarios_r.items():
                label_map = {"bear":"Bear","base":"Base","bull":"Bull"}
                prem = r.implied_premium * 100
                sign_color = "🟢" if prem > 0 else "🔴"
                st.caption(f"{sign_color} {label_map[name_s]}: **${r.intrinsic_value:.2f}** ({prem:+.0f}%)")

    with col_comps:
        st.subheader(t("p5_rel_val"))
        peer_str_v = st.text_input(t("p5_peer_val"), value="NVDA, AMD, INTC, AVGO, QCOM", key="peer_val")
        comp_tickers = list(dict.fromkeys([ticker] + [tk.strip().upper() for tk in peer_str_v.split(",") if tk.strip()]))

        mult_choice = st.selectbox(t("p5_mult"), ["P/S","forwardPE","trailingPE","enterpriseToEbitda"], key="mult_sel")
        mult_labels = {"P/S":"P/S","forwardPE":"Forward P/E","trailingPE":"Trailing P/E","enterpriseToEbitda":"EV/EBITDA"}
        mult_key = {"P/S":"priceToSalesTrailing12Months","forwardPE":"forwardPE",
                    "trailingPE":"trailingPE","enterpriseToEbitda":"enterpriseToEbitda"}[mult_choice]

        with st.spinner(t("p5_loading")):
            comp_rows = []
            for tk in comp_tickers[:8]:
                try:
                    i = load_info(tk)
                    comp_rows.append({"Ticker": tk, "val": i.get(mult_key)})
                except Exception:
                    pass

        comp_rows = [r for r in comp_rows if r["val"]]
        if comp_rows:
            comp_df = pd.DataFrame(comp_rows)
            bar_colors = ["#4da6ff" if tk == ticker else "#6c757d" for tk in comp_df["Ticker"]]
            fig_comp = go.Figure(go.Bar(
                x=comp_df["Ticker"], y=comp_df["val"],
                marker_color=bar_colors,
                text=[f"{v:.1f}x" for v in comp_df["val"]],
                textposition="outside",
            ))
            apply_layout(fig_comp, title=f"{mult_labels[mult_choice]} Peer Comparison", height=320)
            st.plotly_chart(fig_comp, use_container_width=True)

            comp_full = []
            for tk in comp_tickers[:8]:
                try:
                    i = load_info(tk)
                    comp_full.append({
                        "Ticker":    tk,
                        "P/S":       f"{i.get('priceToSalesTrailing12Months', 0):.1f}x",
                        "Fwd P/E":   f"{i.get('forwardPE', 0):.1f}x"           if i.get('forwardPE') else "N/A",
                        "EV/EBITDA": f"{i.get('enterpriseToEbitda', 0):.1f}x"  if i.get('enterpriseToEbitda') else "N/A",
                        t("gross_margin"): f"{(i.get('grossMargins',0) or 0)*100:.1f}%",
                        t("mkt_cap"):      fmt_large(i.get("marketCap", 0)),
                    })
                except Exception:
                    pass
            if comp_full:
                _cdf = pd.DataFrame(comp_full).set_index("Ticker")
                render_table(_cdf)


# ════════════════════════════════════════════════════════════════════════════════
# TAB 3: 财务质量
# ════════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader(t("p5_quality"))
    if "Net Income" in fin.columns and "Operating Cash Flow" in cf.columns:
        years  = [str(d)[:7] for d in fin.index]
        ni     = fin.get("Net Income", pd.Series()).fillna(0) / 1e9
        op_cf_ = cf.get("Operating Cash Flow", pd.Series()).reindex(fin.index).fillna(0) / 1e9
        capex_ = cf.get("Capital Expenditure", pd.Series()).reindex(fin.index).fillna(0).abs() / 1e9
        fcf_q  = op_cf_ - capex_

        fig_q = go.Figure()
        fig_q.add_trace(go.Bar(x=years, y=ni.values,     name="Net Income",    marker_color="#4da6ff", opacity=0.7))
        fig_q.add_trace(go.Scatter(x=years, y=op_cf_.values, name="Operating CF",
                                   mode="lines+markers", line=dict(color="#51cf66", width=2)))
        fig_q.add_trace(go.Scatter(x=years, y=fcf_q.values, name="FCF",
                                   mode="lines+markers", line=dict(color="#ffd43b", width=2, dash="dot")))
        apply_layout(fig_q, title="Net Income vs Operating CF vs FCF (B USD)", height=320)
        st.plotly_chart(fig_q, use_container_width=True)
        st.caption("If operating cash flow consistently lags net income, earnings quality may be in question.")

    st.divider()
    st.subheader(t("p5_checklist"))
    checks = []
    try:
        rev_s  = fin.get("Total Revenue", pd.Series())
        ni_s   = fin.get("Net Income", pd.Series())
        gp_s   = fin.get("Gross Profit", pd.Series())
        ocf_s  = cf.get("Operating Cash Flow", pd.Series())
        gw_s   = bs.get("Goodwill", pd.Series())
        ta_s   = bs.get("Total Assets", pd.Series())

        if len(rev_s) >= 2:
            rev_g = (rev_s.iloc[0] / rev_s.iloc[1] - 1) if rev_s.iloc[1] != 0 else None
            checks.append(("Revenue Growth", "✅" if (rev_g or 0) > 0 else "⚠️",
                           f"{(rev_g or 0)*100:.1f}% YoY"))
        if len(gp_s) >= 1 and len(rev_s) >= 1 and rev_s.iloc[0]:
            gm_v = gp_s.iloc[0] / rev_s.iloc[0] * 100
            checks.append(("Gross Margin", "✅" if gm_v > 30 else "⚠️", f"{gm_v:.1f}%"))
        if len(ocf_s) >= 1 and len(ni_s) >= 1:
            ni_v  = ni_s.iloc[0]
            ocf_v = ocf_s.iloc[0]
            checks.append(("Operating CF > Net Income", "✅" if ocf_v >= ni_v else "⚠️",
                           f"CF ${ocf_v/1e9:.1f}B vs NI ${ni_v/1e9:.1f}B"))
        if len(gw_s) >= 1 and len(ta_s) >= 1 and ta_s.iloc[0]:
            gw_ratio = gw_s.iloc[0] / ta_s.iloc[0] * 100
            checks.append(("Goodwill/Total Assets", "✅" if gw_ratio < 30 else "⚠️",
                           f"{gw_ratio:.1f}% {'(impairment risk)' if gw_ratio > 30 else ''}"))
    except Exception:
        pass

    if checks:
        for item, status, note in checks:
            st.markdown(f"- {status} **{item}**: {note}")
    else:
        st.caption("Insufficient data to generate quality checklist")

# ── Download ──────────────────────────────────────────────────────────────────
st.divider()
today    = datetime.now().strftime("%Y-%m-%d")
date_pfx = datetime.now().strftime("%Y%m%d")

report_md = f"""# Financial Analysis: {ticker} — {name}

**日期**：{today}  |  **数据来源**：yfinance  |  **货币**：USD

## 估值快照

| 指标 | 数值 |
|------|------|
| 市值 | {fmt_large(info.get('marketCap'))} |
| Trailing P/E | {fmt_val(info.get('trailingPE'), decimals=1, suffix='x')} |
| Forward P/E | {fmt_val(info.get('forwardPE'), decimals=1, suffix='x')} |
| P/S (TTM) | {fmt_val(info.get('priceToSalesTrailing12Months'), decimals=1, suffix='x')} |
| EV/EBITDA | {fmt_val(info.get('enterpriseToEbitda'), decimals=1, suffix='x')} |
| 毛利率 | {fmt_pct(info.get('grossMargins'))} |
| ROE | {fmt_pct(info.get('returnOnEquity'))} |

> **风险提示**：本报告仅供研究参考，不构成投资建议。
"""

rp = Path(__file__).parent.parent / "research" / "stock" / f"{date_pfx}_{ticker}_financial.md"
rp.parent.mkdir(parents=True, exist_ok=True)
rp.write_text(report_md, encoding="utf-8")
download_report_button(report_md, rp.name, t("download_report"))
