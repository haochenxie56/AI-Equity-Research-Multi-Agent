"""Page 2 — 行业研究（基础版：ETF 走势 + 自定义标的对比）"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ui_utils import apply_theme, render_sidebar, load_ohlcv, load_ohlcv_multi, load_info, apply_layout, fmt_large, page_header, style_df

st.set_page_config(page_title="行业研究", page_icon="🏭", layout="wide")
apply_theme()
render_sidebar()

st.title("🏭 行业研究")
page_header()
st.caption("ETF 价格走势 + 自定义标的横向对比")
st.divider()

# ── Sector ETF selector ───────────────────────────────────────────────────────
SECTOR_ETFS = {
    "Technology (XLK)":            ("XLK",  ["AAPL","MSFT","NVDA","AVGO","CRM","AMD","ORCL","QCOM","ACN","TXN"]),
    "Semiconductors (SOXX)":       ("SOXX", ["NVDA","AVGO","AMD","QCOM","TXN","AMAT","KLAC","LRCX","MU","ADI"]),
    "AI & Robotics (BOTZ)":        ("BOTZ", ["NVDA","ISRG","ABB","FANUC","KEYENCE","HON","ROK","IRBT","ZBRA","BRKS"]),
    "Communication Svcs (XLC)":    ("XLC",  ["META","GOOGL","NFLX","DIS","CMCSA","T","VZ","EA","TTWO","WBD"]),
    "Consumer Discret. (XLY)":     ("XLY",  ["AMZN","TSLA","HD","MCD","NKE","SBUX","LOW","TJX","BKNG","CMG"]),
    "Health Care (XLV)":           ("XLV",  ["LLY","UNH","JNJ","ABBV","MRK","ABT","TMO","DHR","AMGN","GILD"]),
    "Financials (XLF)":            ("XLF",  ["BRK-B","JPM","V","MA","BAC","WFC","GS","MS","BLK","SPGI"]),
    "Energy (XLE)":                ("XLE",  ["XOM","CVX","COP","SLB","EOG","MPC","PSX","VLO","PXD","OXY"]),
    "Industrials (XLI)":           ("XLI",  ["GE","CAT","RTX","HON","UNP","UPS","BA","LMT","DE","FDX"]),
    "Utilities (XLU)":             ("XLU",  ["NEE","DUK","SO","D","AEP","EXC","SRE","ES","XEL","WEC"]),
}

col_sel, col_period = st.columns([3, 1])
with col_sel:
    sector_choice = st.selectbox("选择行业 ETF", list(SECTOR_ETFS.keys()))
with col_period:
    period = st.selectbox("时间周期", ["6mo","1y","2y","5y"], index=1)

etf_ticker, default_peers = SECTOR_ETFS[sector_choice]

st.subheader("自定义对比标的")
peers_input = st.text_area(
    "输入要对比的股票（逗号分隔），默认为该行业代表性标的",
    value=", ".join(default_peers[:8]),
    height=80,
)
peer_tickers = [t.strip().upper() for t in peers_input.split(",") if t.strip()]

st.divider()

# ── Load data ─────────────────────────────────────────────────────────────────
all_tickers = list(dict.fromkeys([etf_ticker] + peer_tickers))  # dedup, ETF first

with st.spinner(f"加载 {len(all_tickers)} 个标的数据..."):
    data = load_ohlcv_multi(tuple(all_tickers), period)

if etf_ticker not in data or data[etf_ticker].empty:
    st.error(f"无法加载 ETF 数据：{etf_ticker}")
    st.stop()

# ── Chart 1: ETF absolute price ───────────────────────────────────────────────
st.subheader(f"📈 {etf_ticker} 价格走势")

etf_df = data[etf_ticker]
fig1 = go.Figure()
fig1.add_trace(go.Scatter(
    x=etf_df.index, y=etf_df["Close"],
    name=etf_ticker, line=dict(color="#4da6ff", width=2),
    fill="tozeroy", fillcolor="rgba(77,166,255,0.08)",
    hovertemplate="%{x|%Y-%m-%d}<br>$%{y:.2f}<extra></extra>",
))

# Volume as secondary y
fig1 = make_subplots(rows=2, cols=1, shared_xaxes=True,
                     row_heights=[0.75, 0.25], vertical_spacing=0.03)
fig1.add_trace(go.Scatter(
    x=etf_df.index, y=etf_df["Close"], name=etf_ticker,
    line=dict(color="#4da6ff", width=2),
), row=1, col=1)
_dark  = st.session_state.get("dark_mode", True)
_up_c  = "#00c853" if _dark else "#2da44e"
_dn_c  = "#ff3d3d" if _dark else "#cf222e"
vol_colors = [_up_c if c >= o else _dn_c for c, o in zip(etf_df["Close"], etf_df["Open"])]
fig1.add_trace(go.Bar(
    x=etf_df.index, y=etf_df["Volume"], name="成交量",
    marker_color=vol_colors, showlegend=False,
), row=2, col=1)

fig1.update_yaxes(title_text="价格 (USD)", row=1, col=1)
fig1.update_yaxes(title_text="成交量", row=2, col=1)
apply_layout(fig1, title=f"{etf_ticker} — {period} 价格与成交量", height=450)
st.plotly_chart(fig1, use_container_width=True)

st.divider()

# ── Chart 2: Normalized return comparison ─────────────────────────────────────
st.subheader("📊 标的对比（归一化收益，基准 = 起始日 100）")

available = {t: d for t, d in data.items() if not d.empty and len(d) > 5}
if len(available) < 2:
    st.warning("有效标的不足，请检查 Ticker 是否正确")
else:
    COLORS = (
        ["#4fc3f7","#ff3d3d","#00c853","#ffb300","#cc5de8",
         "#ff922b","#20c997","#f06595","#74c0fc","#a9e34b"]
        if _dark else
        ["#0969da","#cf222e","#1a7f37","#9a6700","#8250df",
         "#bc4c00","#0a969c","#bf3989","#1158c7","#4d7c0f"]
    )

    fig2 = go.Figure()
    for i, (t, df) in enumerate(available.items()):
        norm = df["Close"] / df["Close"].iloc[0] * 100
        is_etf = (t == etf_ticker)
        fig2.add_trace(go.Scatter(
            x=df.index, y=norm,
            name=t,
            line=dict(
                color=COLORS[i % len(COLORS)],
                width=3 if is_etf else 1.5,
                dash="solid" if is_etf else "dot",
            ),
            hovertemplate=f"{t}: %{{y:.1f}}<extra></extra>",
        ))

    fig2.add_hline(y=100, line_dash="dash", line_color="gray", opacity=0.5)
    apply_layout(fig2, title=f"相对表现对比（{period}，基准=100）", height=420)
    st.plotly_chart(fig2, use_container_width=True)

    # ── Performance summary table ─────────────────────────────────────────────
    st.subheader("表现汇总")
    rows = []
    for t, df in available.items():
        close = df["Close"]
        try:
            info_t = load_info(t)
            mktcap = info_t.get("marketCap", 0)
            pe     = info_t.get("trailingPE")
        except Exception:
            mktcap, pe = 0, None

        ret_total = (close.iloc[-1] / close.iloc[0] - 1) * 100
        ret_1m    = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) >= 21 else None
        ret_3m    = (close.iloc[-1] / close.iloc[-63] - 1) * 100 if len(close) >= 63 else None
        vol_ann   = close.pct_change().std() * (252 ** 0.5) * 100

        rows.append({
            "Ticker":      t,
            "ETF?":        "✅" if t == etf_ticker else "",
            "最新价 ($)":  f"{close.iloc[-1]:.2f}",
            f"总收益({period})": f"{ret_total:+.1f}%",
            "1M 收益":     f"{ret_1m:+.1f}%" if ret_1m is not None else "N/A",
            "3M 收益":     f"{ret_3m:+.1f}%" if ret_3m is not None else "N/A",
            "年化波动率":  f"{vol_ann:.1f}%",
            "市值":        fmt_large(mktcap) if mktcap else "N/A",
            "P/E":         f"{pe:.1f}x" if pe else "N/A",
        })

    perf_df = pd.DataFrame(rows).set_index("Ticker")
    st.dataframe(style_df(perf_df), use_container_width=True)

    # Download
    csv_data = pd.DataFrame(rows).to_csv(index=False)
    st.download_button("⬇ 下载表格 CSV", csv_data, f"sector_comparison_{etf_ticker}.csv", "text/csv")
