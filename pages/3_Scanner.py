"""Page 3 — 选股扫描（自定义股票池）"""

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
    apply_layout, fmt_large, download_report_button, page_header, render_table, t,
)

st.set_page_config(page_title="选股扫描", page_icon="🔍", layout="wide")
apply_theme()
render_sidebar()

st.title(t("p3_title"))
page_header()
st.caption(t("p3_subtitle"))
st.divider()

# ── Default tech pool (S&P 500 top 20 tech) ───────────────────────────────────
DEFAULT_POOL = (
    "AAPL, MSFT, NVDA, AVGO, META, ORCL, CRM, AMD, QCOM, TXN, "
    "AMAT, KLAC, LRCX, MU, ADI, NOW, PANW, SNPS, CDNS, INTC"
)

# ── Settings ──────────────────────────────────────────────────────────────────
col_pool, col_params = st.columns([3, 2])

with col_pool:
    st.subheader(t("p3_pool"))
    pool_input = st.text_area(
        t("p3_pool_input"),
        value=DEFAULT_POOL,
        height=120,
        help=t("p3_pool_help"),
    )
    pool_tickers = [tk.strip().upper() for tk in pool_input.replace("\n", ",").split(",") if tk.strip()]
    st.caption(f"{len(pool_tickers)} tickers: {', '.join(pool_tickers)}")

with col_params:
    st.subheader(t("p3_strategy"))
    strategy = st.selectbox(t("p3_strat_lbl"), [
        "动量 Momentum",
        "价值 Value",
        "高质量成长 Quality Growth",
        "超卖反弹 Oversold Bounce",
    ])
    period = st.selectbox(t("p3_period"), ["6mo","1y","2y"], index=1)
    top_n  = st.slider(t("p3_top_n"), min_value=5, max_value=len(pool_tickers), value=min(15, len(pool_tickers)))

run_btn = st.button(t("p3_run"), type="primary", use_container_width=True)
st.divider()

# ── Scanner logic ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def run_scan(tickers: tuple, strategy: str, period: str) -> list[dict]:
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

            # Strategy filters
            passes = False
            if "动量" in strategy:
                passes = (
                    snap["above_SMA200"] and
                    50 <= snap.get("RSI_14", 0) <= 72 and
                    snap.get("Vol_ratio_20d", 0) >= 1.1 and
                    (ret_3m or 0) > 0
                )
            elif "价值" in strategy:
                try:
                    info_v = load_info(ticker)
                    pe = info_v.get("trailingPE")
                    passes = pe is not None and pe < 20 and snap.get("RSI_14", 50) < 55
                except Exception:
                    passes = snap.get("RSI_14", 50) < 45
            elif "Quality" in strategy or "质量" in strategy:
                passes = (
                    snap["above_SMA200"] and
                    snap.get("ADX", 0) > 20 and
                    (ret_3m or 0) > 5
                )
            elif "超卖" in strategy:
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

                results.append({
                    "Ticker":    ticker,
                    "公司":      name,
                    "行业":      sector,
                    "价格($)":   round(price, 2),
                    "RSI(14)":   snap.get("RSI_14"),
                    "ADX":       snap.get("ADX"),
                    "1M收益%":   round(ret_1m, 1) if ret_1m else None,
                    "3M收益%":   round(ret_3m, 1) if ret_3m else None,
                    "6M收益%":   round(ret_6m, 1) if ret_6m else None,
                    "52W高%":    snap.get("pct_from_52w_high"),
                    "量比(20D)": snap.get("Vol_ratio_20d"),
                    "年化波动%": round(vol_ann, 1),
                    "市值(B)":   round(mktcap / 1e9, 1) if mktcap else None,
                    "P/E":       round(pe, 1) if pe else None,
                    "Fwd P/E":   round(fwd_pe, 1) if fwd_pe else None,
                })
        except Exception:
            continue

    prog.empty()

    # Sort by strategy
    sort_key = "3M收益%" if "动量" in strategy else "RSI(14)"
    results.sort(key=lambda x: (x.get(sort_key) or -9999), reverse=("动量" in strategy or "质量" in strategy))
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

# Summary bar
c1, c2, c3 = st.columns(3)
c1.metric(t("p3_hits"),    len(results))
c2.metric(t("p3_avg3m"),   f"{pd.Series([r.get('3M收益%') for r in results if r.get('3M收益%')]).mean():.1f}%")
c3.metric(t("p3_avg_rsi"), f"{pd.Series([r.get('RSI(14)') for r in results if r.get('RSI(14)')]).mean():.1f}")
st.divider()

# Results table
st.subheader(f"Top {top_n}")
render_table(
    df_results.set_index("Ticker"),
    height=min(400, 50 + len(top_results) * 38),
)
st.divider()

# ── Bubble chart ──────────────────────────────────────────────────────────────
st.subheader("3M Return vs RSI (bubble size = Mkt Cap)")
plot_df = df_results.dropna(subset=["3M收益%", "RSI(14)"])

if not plot_df.empty:
    fig = px.scatter(
        plot_df,
        x="3M收益%",
        y="RSI(14)",
        size=[max(v, 1) for v in plot_df["市值(B)"].fillna(1)],
        color="行业",
        text="Ticker",
        hover_data={"公司": True, "价格($)": True, "P/E": True,
                    "3M收益%": True, "RSI(14)": True, "市值(B)": True},
        size_max=60,
    )
    fig.add_hline(y=70, line_dash="dash", line_color="red",   opacity=0.5, annotation_text="Overbought(70)")
    fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5, annotation_text="Oversold(30)")
    fig.add_vline(x=0,  line_dash="dash", line_color="gray",  opacity=0.4)
    fig.update_traces(textposition="top center", textfont_size=11)
    apply_layout(fig, title="3M Return (%) vs RSI(14)", height=480)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Download ──────────────────────────────────────────────────────────────────
col_dl1, col_dl2 = st.columns(2)
with col_dl1:
    csv_data = df_results.to_csv(index=False)
    st.download_button(t("p3_dl_csv"), csv_data,
                       f"{datetime.now().strftime('%Y%m%d')}_scan_{strategy[:5]}.csv", "text/csv")
with col_dl2:
    today = datetime.now().strftime("%Y-%m-%d")
    md_lines = [
        f"# Stock Scan: {strategy}",
        f"",
        f"**日期**：{today}  |  **股票池**：{len(pool_tickers)} 只  |  **命中**：{len(results)} 只",
        f"",
        f"| Ticker | 价格 | RSI | ADX | 3M收益 | 市值 |",
        f"|--------|------|-----|-----|--------|------|",
    ]
    for r in top_results:
        md_lines.append(
            f"| {r['Ticker']} | ${r['价格($)']} | {r['RSI(14)']} | {r['ADX']} "
            f"| {r.get('3M收益%','N/A')}% | {r.get('市值(B)','N/A')}B |"
        )
    md_lines += ["", "> **风险提示**：本报告仅供研究参考，不构成投资建议。"]
    report_md = "\n".join(md_lines)

    # Save to research/scans/
    scan_path = (Path(__file__).parent.parent / "research" / "scans" /
                 f"{datetime.now().strftime('%Y%m%d')}_scan_{strategy[:8].replace(' ','_')}.md")
    scan_path.parent.mkdir(parents=True, exist_ok=True)
    scan_path.write_text(report_md, encoding="utf-8")

    download_report_button(report_md, scan_path.name, t("p3_dl_md"))
