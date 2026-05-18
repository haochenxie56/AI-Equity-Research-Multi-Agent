"""Page 3 — Stock Scanner (custom pool)"""

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
    apply_layout, apply_legend, fmt_large, download_report_button, page_header, render_table, t,
    render_workflow_bar,
)

st.set_page_config(page_title="Stock Scanner", page_icon="🔍", layout="wide")
apply_theme()
render_sidebar()

_lang = st.session_state.get("language", "en")
_dark = st.session_state.get("dark_mode", True)

st.title(t("p3_title"))
page_header()
render_workflow_bar()
st.caption(t("p3_subtitle"))
st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# AI WORKFLOW RESULTS — read from research_state
# ══════════════════════════════════════════════════════════════════════════════
_wf_scan_res = (
    st.session_state.get("research_state", {})
    .get("results", {})
    .get("scan") or {}
)
_scan_llm    = _wf_scan_res.get("llm") or {}
_selected    = _scan_llm.get("selected") or []
_top_pick    = (_scan_llm.get("decision") or "").upper().strip()
_runner_up   = (_scan_llm.get("runner_up") or "").upper().strip()
_scan_reason = _scan_llm.get("reasoning", "")

# Resolve top pick: prefer decision field, fall back to first valid selected entry
if not _top_pick or _top_pick == "N/A":
    for _s in _selected:
        _tk = (_s.get("ticker") or "").upper().strip()
        if _tk and _tk != "N/A":
            _top_pick = _tk
            break

_has_scan_llm = bool(_top_pick and _top_pick not in ("N/A", ""))

_ai_bg  = "#161b22" if _dark else "#f6f8fa"
_ai_bd  = "#30363d" if _dark else "#d0d7de"
_ai_txt = "#e6edf3" if _dark else "#1f2328"

_CONF_COLOR = {
    "High": "#3fb950", "高": "#3fb950",
    "Medium": "#d29922", "中": "#d29922",
    "Low": "#f85149", "低": "#f85149",
}
_STRAT_COLOR = {
    "Momentum": "#388bfd",       "质量成长": "#388bfd",
    "Quality Growth": "#3fb950", "动量": "#3fb950",
    "Value": "#d29922",          "价值": "#d29922",
    "Oversold Bounce": "#a371f7","超卖反弹": "#a371f7",
}

_ai_title = "🤖 AI 工作流选股结果" if _lang == "zh" else "🤖 AI Workflow Scan Results"
st.subheader(_ai_title)

if not _has_scan_llm:
    # ── No workflow results: show hint ────────────────────────────────────────
    _hint = (
        "尚无 AI 选股结果。请先在 **[总览页](/Overview)** 运行 AI 研究工作流，"
        "完成后此处将自动显示跨策略选股分析。"
        if _lang == "zh" else
        "No AI scan results yet. Run the **[AI Research Workflow](/Overview)** on the "
        "Overview page first — cross-strategy stock selections will appear here automatically."
    )
    st.markdown(
        f'<div style="background:{_ai_bg};border:1px dashed {_ai_bd};'
        f'border-radius:6px;padding:10px 16px;font-size:0.85rem;color:#8b949e">'
        f'🤖 {_hint}</div>',
        unsafe_allow_html=True,
    )
else:
    # ── Top-pick highlight card ───────────────────────────────────────────────
    _top_conf   = next((s.get("confidence","") for s in _selected if s.get("ticker")==_top_pick), "")
    _top_strat  = next((s.get("strategy","")   for s in _selected if s.get("ticker")==_top_pick), "")
    _top_reason = next((s.get("reasoning","")  for s in _selected if s.get("ticker")==_top_pick), "")
    _conf_c  = _CONF_COLOR.get(_top_conf, "#58a6ff")
    _strat_c = _STRAT_COLOR.get(_top_strat, "#58a6ff")
    _lbl_top = "最强推荐" if _lang == "zh" else "Top Pick"
    _lbl_str = "策略" if _lang == "zh" else "Strategy"
    _lbl_con = "置信度" if _lang == "zh" else "Confidence"

    st.markdown(
        f'<div style="background:{_ai_bg};border:2px solid {_conf_c};'
        f'border-radius:10px;padding:16px 22px;margin-bottom:14px">'
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">'
        f'<span style="font-size:1.5rem;font-weight:700;color:{_conf_c}">{_top_pick}</span>'
        f'<span style="background:{_ai_bd};padding:2px 10px;border-radius:12px;'
        f'font-size:0.75rem;color:#8b949e">{_lbl_top}</span>'
        + (f'<span style="background:{_strat_c}22;border:1px solid {_strat_c};'
           f'padding:2px 10px;border-radius:12px;font-size:0.75rem;color:{_strat_c}">'
           f'{_lbl_str}: {_top_strat}</span>' if _top_strat else "")
        + (f'<span style="background:{_conf_c}22;border:1px solid {_conf_c};'
           f'padding:2px 10px;border-radius:12px;font-size:0.75rem;color:{_conf_c}">'
           f'{_lbl_con}: {_top_conf}</span>' if _top_conf else "")
        + f'</div>'
        + (f'<p style="font-size:0.88rem;line-height:1.65;color:{_ai_txt};margin:0">'
           f'{_top_reason}</p>' if _top_reason else "")
        + f'</div>',
        unsafe_allow_html=True,
    )

    # ── Other selected stocks ─────────────────────────────────────────────────
    others = [s for s in _selected if s.get("ticker") != _top_pick]
    if others or _runner_up:
        _lbl_others = "其他入选标的" if _lang == "zh" else "Other Selected Stocks"
        st.markdown(f"**{_lbl_others}**")

        # Runner-up not already in selected list
        if _runner_up and not any(s.get("ticker") == _runner_up for s in _selected):
            others = [{"ticker": _runner_up, "strategy": "", "confidence": "", "reasoning": ""}] + others

        for s in others[:4]:
            tk    = s.get("ticker", "")
            strat = s.get("strategy", "")
            conf  = s.get("confidence", "")
            rsn   = s.get("reasoning", "")
            sc    = _STRAT_COLOR.get(strat, "#58a6ff")
            cc    = _CONF_COLOR.get(conf, "#8b949e")
            st.markdown(
                f'<div style="background:{_ai_bg};border-left:3px solid {sc};'
                f'border-radius:0 6px 6px 0;padding:8px 14px;margin:5px 0">'
                f'<span style="font-weight:700;color:{sc};font-size:0.95rem">{tk}</span>'
                + (f'&nbsp;<span style="background:{sc}22;border:1px solid {sc};'
                   f'padding:1px 8px;border-radius:10px;font-size:0.72rem;color:{sc};'
                   f'margin-left:6px">{strat}</span>' if strat else "")
                + (f'&nbsp;<span style="color:{cc};font-size:0.72rem;margin-left:6px">'
                   f'{conf}</span>' if conf else "")
                + (f'<p style="font-size:0.84rem;color:{_ai_txt};margin:4px 0 0;'
                   f'line-height:1.55">{rsn}</p>' if rsn else "")
                + f'</div>',
                unsafe_allow_html=True,
            )

    # ── Overall reasoning ─────────────────────────────────────────────────────
    if _scan_reason and "unavailable" not in _scan_reason.lower():
        _lbl_rsn = "综合选股逻辑" if _lang == "zh" else "Overall Rationale"
        st.markdown(
            f'<div style="background:{_ai_bg};border:1px solid {_ai_bd};'
            f'border-radius:6px;padding:10px 16px;margin-top:8px">'
            f'<div style="font-size:0.75rem;color:#8b949e;margin-bottom:4px">'
            f'{_lbl_rsn}</div>'
            f'<p style="font-size:0.88rem;line-height:1.65;color:{_ai_txt};margin:0">'
            f'{_scan_reason}</p></div>',
            unsafe_allow_html=True,
        )

    # ── Strategy hit counts ───────────────────────────────────────────────────
    _sr = _wf_scan_res.get("strategy_results") or {}
    if _sr:
        _lbl_hits = "各策略命中" if _lang == "zh" else "Strategy Hit Counts"
        st.caption(
            f"{_lbl_hits}: " + "  ·  ".join(
                f"**{s}** {len(v)}" for s, v in _sr.items()
            )
        )

st.divider()

# ── Default tech pool (S&P 500 top 20 tech) ───────────────────────────────────
DEFAULT_POOL = (
    "AAPL, MSFT, NVDA, AVGO, META, ORCL, CRM, AMD, QCOM, TXN, "
    "AMAT, KLAC, LRCX, MU, ADI, NOW, PANW, SNPS, CDNS, INTC"
)

# Canonical English strategy codes (used internally for filtering / caching)
_STRAT_CODES   = ["Momentum", "Value", "Quality Growth", "Oversold Bounce"]
# Displayed labels (language-aware)
_STRAT_DISPLAY = [
    t("p3_strat_momentum"),
    t("p3_strat_value"),
    t("p3_strat_quality"),
    t("p3_strat_oversold"),
]

# ── Scanner linkage from Sector page ──────────────────────────────────────────
if st.session_state.get("scanner_trigger"):
    _injected_pool = st.session_state.get("scanner_pool", "")
    st.session_state["scanner_trigger"] = False
    if _injected_pool:
        st.session_state["_scanner_pool_prefill"] = _injected_pool
        st.info(f"📥 Pool pre-filled from Sector page ({len([t for t in _injected_pool.split(',') if t.strip()])} tickers)")

# ── Workflow state linkage ─────────────────────────────────────────────────────
if "_scanner_pool_prefill" not in st.session_state:
    _wf_pool = (
        st.session_state.get("research_state", {})
        .get("results", {})
        .get("scan", {}) or {}
    ).get("pool")
    if _wf_pool:
        st.session_state["_scanner_pool_prefill"] = _wf_pool

_default_pool = st.session_state.pop("_scanner_pool_prefill", DEFAULT_POOL)

# ── Settings ──────────────────────────────────────────────────────────────────
col_pool, col_params = st.columns([3, 2])

with col_pool:
    st.subheader(t("p3_pool"))
    pool_input = st.text_area(
        t("p3_pool_input"),
        value=_default_pool,
        height=120,
        help=t("p3_pool_help"),
    )
    pool_tickers = [tk.strip().upper() for tk in pool_input.replace("\n", ",").split(",") if tk.strip()]
    st.caption(f"{len(pool_tickers)} tickers: {', '.join(pool_tickers)}")

with col_params:
    st.subheader(t("p3_strategy"))
    _strat_display_choice = st.selectbox(t("p3_strat_lbl"), _STRAT_DISPLAY)
    # Convert displayed label back to canonical code
    strategy = _STRAT_CODES[_STRAT_DISPLAY.index(_strat_display_choice)]

    period = st.selectbox(t("p3_period"), ["6mo","1y","2y"], index=1)
    top_n  = st.slider(t("p3_top_n"), min_value=5, max_value=len(pool_tickers), value=min(15, len(pool_tickers)))

run_btn = st.button(t("p3_run"), type="primary", use_container_width=True)
st.divider()

# ── Scanner logic ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def run_scan(tickers: tuple, strategy: str, period: str) -> list[dict]:
    """Run the scan for the given tickers, strategy code, and period.
    Column names are always English (language-independent) for caching consistency."""
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

            # Strategy filters (canonical English codes)
            passes = False
            if strategy == "Momentum":
                passes = (
                    snap["above_SMA200"] and
                    50 <= snap.get("RSI_14", 0) <= 72 and
                    snap.get("Vol_ratio_20d", 0) >= 1.1 and
                    (ret_3m or 0) > 0
                )
            elif strategy == "Value":
                try:
                    info_v = load_info(ticker)
                    pe = info_v.get("trailingPE")
                    passes = pe is not None and pe < 20 and snap.get("RSI_14", 50) < 55
                except Exception:
                    passes = snap.get("RSI_14", 50) < 45
            elif strategy == "Quality Growth":
                passes = (
                    snap["above_SMA200"] and
                    snap.get("ADX", 0) > 20 and
                    (ret_3m or 0) > 5
                )
            elif strategy == "Oversold Bounce":
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

                # Always store with English column names for caching consistency
                results.append({
                    "Ticker":          ticker,
                    "Company":         name,
                    "Sector":          sector,
                    "Price($)":        round(price, 2),
                    "RSI(14)":         snap.get("RSI_14"),
                    "ADX":             snap.get("ADX"),
                    "1M Ret%":         round(ret_1m, 1) if ret_1m else None,
                    "3M Ret%":         round(ret_3m, 1) if ret_3m else None,
                    "6M Ret%":         round(ret_6m, 1) if ret_6m else None,
                    "52W High%":       snap.get("pct_from_52w_high"),
                    "Vol Ratio(20D)":  snap.get("Vol_ratio_20d"),
                    "Ann. Vol%":       round(vol_ann, 1),
                    "Mkt Cap(B)":      round(mktcap / 1e9, 1) if mktcap else None,
                    "P/E":             round(pe, 1) if pe else None,
                    "Fwd P/E":         round(fwd_pe, 1) if fwd_pe else None,
                })
        except Exception:
            continue

    prog.empty()

    # Sort by strategy (English codes)
    sort_key = "3M Ret%" if strategy == "Momentum" else "RSI(14)"
    results.sort(key=lambda x: (x.get(sort_key) or -9999), reverse=(strategy in ("Momentum", "Quality Growth")))
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

# Summary bar — always reference English column names internally
c1, c2, c3 = st.columns(3)
c1.metric(t("p3_hits"),    len(results))
c2.metric(t("p3_avg3m"),   f"{pd.Series([r.get('3M Ret%') for r in results if r.get('3M Ret%')]).mean():.1f}%")
c3.metric(t("p3_avg_rsi"), f"{pd.Series([r.get('RSI(14)') for r in results if r.get('RSI(14)')]).mean():.1f}")
st.divider()

# Language-aware column rename map for display
_COL_ZH = {
    "Company":        t("p3_col_company"),
    "Sector":         t("p3_col_sector"),
    "Price($)":       t("p3_col_price"),
    "1M Ret%":        t("p3_col_ret1m"),
    "3M Ret%":        t("p3_col_ret3m"),
    "6M Ret%":        t("p3_col_ret6m"),
    "Vol Ratio(20D)": t("p3_col_volratio"),
    "Ann. Vol%":      t("p3_col_annvol"),
    "Mkt Cap(B)":     t("p3_col_mktcap"),
}
display_df = df_results.rename(columns=_COL_ZH)

# Results table
st.subheader(f"Top {top_n}")
render_table(
    display_df.set_index("Ticker"),
    height=min(400, 50 + len(top_results) * 38),
)
st.divider()

# ── Bubble chart ──────────────────────────────────────────────────────────────
_col_ret3m = _COL_ZH["3M Ret%"]
_col_rsi   = "RSI(14)"
_col_mkt   = _COL_ZH["Mkt Cap(B)"]
_col_sec   = _COL_ZH["Sector"]
_col_co    = _COL_ZH["Company"]
_col_px    = _COL_ZH["Price($)"]

st.subheader(f"{_col_ret3m} vs {_col_rsi} (bubble = {_col_mkt})")
plot_df = display_df.dropna(subset=[_col_ret3m, _col_rsi])

if not plot_df.empty:
    fig = px.scatter(
        plot_df,
        x=_col_ret3m,
        y=_col_rsi,
        size=[max(v, 1) for v in plot_df[_col_mkt].fillna(1)],
        color=_col_sec,
        text="Ticker",
        hover_data={_col_co: True, _col_px: True, "P/E": True,
                    _col_ret3m: True, _col_rsi: True, _col_mkt: True},
        size_max=60,
    )
    fig.add_hline(y=70, line_dash="dash", line_color="red",   opacity=0.5, annotation_text="Overbought(70)")
    fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5, annotation_text="Oversold(30)")
    fig.add_vline(x=0,  line_dash="dash", line_color="gray",  opacity=0.4)
    fig.update_traces(textposition="top center", textfont_size=11)
    apply_layout(fig, title=f"{_col_ret3m} vs {_col_rsi}", height=480)
    apply_legend(fig)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Download ──────────────────────────────────────────────────────────────────
col_dl1, col_dl2 = st.columns(2)
with col_dl1:
    csv_data = display_df.to_csv(index=False)
    st.download_button(t("p3_dl_csv"), csv_data,
                       f"{datetime.now().strftime('%Y%m%d')}_scan_{strategy[:10].replace(' ','_')}.csv", "text/csv")
with col_dl2:
    today = datetime.now().strftime("%Y-%m-%d")
    md_lines = [
        f"# {'Stock Scan' if _lang == 'en' else '选股扫描'}: {_strat_display_choice}",
        f"",
        f"**{'Date' if _lang=='en' else '日期'}**: {today}  |  "
        f"**{'Pool' if _lang=='en' else '股票池'}**: {len(pool_tickers)}  |  "
        f"**{'Hits' if _lang=='en' else '命中'}**: {len(results)}",
        f"",
        f"| Ticker | Price | RSI | ADX | 3M Ret | Mkt Cap |",
        f"|--------|-------|-----|-----|--------|---------|",
    ]
    for r in top_results:
        md_lines.append(
            f"| {r['Ticker']} | ${r['Price($)']} | {r['RSI(14)']} | {r['ADX']} "
            f"| {r.get('3M Ret%','N/A')}% | {r.get('Mkt Cap(B)','N/A')}B |"
        )
    _disclaimer = ("> **Disclaimer**: For research purposes only. Not investment advice."
                   if _lang == "en" else
                   "> **风险提示**：本报告仅供研究参考，不构成投资建议。")
    md_lines += ["", _disclaimer]
    report_md = "\n".join(md_lines)

    # Save to research/scans/
    scan_path = (Path(__file__).parent.parent / "research" / "scans" /
                 f"{datetime.now().strftime('%Y%m%d')}_scan_{strategy[:12].replace(' ','_')}.md")
    scan_path.parent.mkdir(parents=True, exist_ok=True)
    scan_path.write_text(report_md, encoding="utf-8")

    download_report_button(report_md, scan_path.name, t("p3_dl_md"))
