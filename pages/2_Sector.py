"""Page 2 — 行业研究（基础版：ETF 走势 + 自定义标的对比）"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ui_utils import (
    apply_theme, render_sidebar, load_ohlcv, load_ohlcv_multi, load_info,
    apply_layout, apply_legend, fmt_large, page_header, render_table, t,
)

st.set_page_config(page_title="Sector Research", page_icon="🏭", layout="wide")
apply_theme()
render_sidebar()

st.title(t("p2_title"))
page_header()
st.caption(t("p2_subtitle"))
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
    sector_choice = st.selectbox(t("p2_etf"), list(SECTOR_ETFS.keys()))
with col_period:
    period = st.selectbox(t("p2_period"), ["6mo","1y","2y","5y"], index=1)

etf_ticker, default_peers = SECTOR_ETFS[sector_choice]

st.subheader(t("p2_peers"))
peers_input = st.text_area(
    t("p2_peers_input"),
    value=", ".join(default_peers[:8]),
    height=80,
)
peer_tickers = [tk.strip().upper() for tk in peers_input.split(",") if tk.strip()]

st.divider()

# ── Load data ─────────────────────────────────────────────────────────────────
all_tickers = list(dict.fromkeys([etf_ticker] + peer_tickers))  # dedup, ETF first

with st.spinner(f"{t('p2_peers')} {len(all_tickers)}..."):
    data = load_ohlcv_multi(tuple(all_tickers), period)

if etf_ticker not in data or data[etf_ticker].empty:
    st.error(f"无法加载 ETF 数据：{etf_ticker}")
    st.stop()

# ── Chart 1: ETF absolute price ───────────────────────────────────────────────
st.subheader(f"📈 {etf_ticker} {t('p2_subtitle').split('+')[0].strip()}")

etf_df = data[etf_ticker]

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
    x=etf_df.index, y=etf_df["Volume"], name=t("p2_volume"),
    marker_color=vol_colors, showlegend=False,
), row=2, col=1)

fig1.update_yaxes(title_text=t("p2_price_usd"), row=1, col=1)
fig1.update_yaxes(title_text=t("p2_volume"),    row=2, col=1)
apply_layout(fig1, title=f"{etf_ticker} — {period}", height=450)
apply_legend(fig1)
st.plotly_chart(fig1, use_container_width=True)

st.divider()

# ── Chart 2: Normalized return comparison ─────────────────────────────────────
st.subheader(t("p2_norm_return"))

available = {tk: d for tk, d in data.items() if not d.empty and len(d) > 5}
if len(available) < 2:
    st.warning(t("p2_insufficient"))
else:
    COLORS = (
        ["#4fc3f7","#ff3d3d","#00c853","#ffb300","#cc5de8",
         "#ff922b","#20c997","#f06595","#74c0fc","#a9e34b"]
        if _dark else
        ["#0969da","#cf222e","#1a7f37","#9a6700","#8250df",
         "#bc4c00","#0a969c","#bf3989","#1158c7","#4d7c0f"]
    )

    fig2 = go.Figure()
    for i, (tk, df) in enumerate(available.items()):
        norm = df["Close"] / df["Close"].iloc[0] * 100
        is_etf = (tk == etf_ticker)
        fig2.add_trace(go.Scatter(
            x=df.index, y=norm,
            name=tk,
            line=dict(
                color=COLORS[i % len(COLORS)],
                width=3 if is_etf else 1.5,
                dash="solid" if is_etf else "dot",
            ),
            hovertemplate=f"{tk}: %{{y:.1f}}<extra></extra>",
        ))

    fig2.add_hline(y=100, line_dash="dash", line_color="gray", opacity=0.5)
    apply_layout(fig2, title=f"Relative Performance ({period}, Base=100)", height=420)
    apply_legend(fig2)
    st.plotly_chart(fig2, use_container_width=True)

    # ── Performance summary table ─────────────────────────────────────────────
    st.subheader(t("p2_perf"))
    rows = []
    for tk, df in available.items():
        close = df["Close"]
        try:
            info_t = load_info(tk)
            mktcap = info_t.get("marketCap", 0)
            pe     = info_t.get("trailingPE")
        except Exception:
            mktcap, pe = 0, None

        ret_total = (close.iloc[-1] / close.iloc[0] - 1) * 100
        ret_1m    = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) >= 21 else None
        ret_3m    = (close.iloc[-1] / close.iloc[-63] - 1) * 100 if len(close) >= 63 else None
        vol_ann   = close.pct_change().std() * (252 ** 0.5) * 100

        rows.append({
            "Ticker":               tk,
            "ETF?":                 "✅" if tk == etf_ticker else "",
            "Latest ($)":           f"{close.iloc[-1]:.2f}",
            f"Total({period})":     f"{ret_total:+.1f}%",
            "1M Ret":               f"{ret_1m:+.1f}%" if ret_1m is not None else "N/A",
            "3M Ret":               f"{ret_3m:+.1f}%" if ret_3m is not None else "N/A",
            "Ann. Vol":             f"{vol_ann:.1f}%",
            "Mkt Cap":              fmt_large(mktcap) if mktcap else "N/A",
            "P/E":                  f"{pe:.1f}x" if pe else "N/A",
        })

    perf_df = pd.DataFrame(rows).set_index("Ticker")
    render_table(perf_df)

    # Download
    csv_data = pd.DataFrame(rows).to_csv(index=False)
    st.download_button(t("p2_dl_csv"), csv_data, f"sector_comparison_{etf_ticker}.csv", "text/csv")
