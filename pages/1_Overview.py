"""Page 1 — AI Workflow Control Center

Three states:
  idle      — single "Start AI Research Workflow" button
  running   — 5 sequential steps, each with code layer + LLM layer
  completed — summary cards with LLM decisions, reasoning, key_metrics
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import streamlit as st
from ui_utils import (
    apply_theme, render_sidebar, load_info, load_ohlcv,
    load_financials, load_cashflow, load_earnings,
    fmt_large, page_header, t,
)
from workflow_state import (
    init_research_state, get_state, update_state, update_step, reset_state,
)

st.set_page_config(page_title="AI Workflow", page_icon="🤖", layout="wide")
apply_theme()
render_sidebar()

init_research_state()
state = get_state()

_lang = st.session_state.get("language", "en")
_dark = st.session_state.get("dark_mode", True)

st.title("🤖 " + ("AI 研究工作流" if _lang == "zh" else "AI Research Workflow"))
page_header()
st.divider()

# ── Styling helpers ────────────────────────────────────────────────────────────
_card_bg  = "#161b22" if _dark else "#f6f8fa"
_card_bd  = "#30363d" if _dark else "#d0d7de"
_ok_c     = "#3fb950"
_err_c    = "#f85149"
_pend_c   = "#8b949e"
_run_c    = "#58a6ff"

_STEPS      = ["sector", "scan", "equity", "financial", "pv"]
_STEP_KEYS  = ["p1_step1_name", "p1_step2_name", "p1_step3_name", "p1_step4_name", "p1_step5_name"]
_STEP_PAGES = [
    "pages/2_Sector.py", "pages/3_Scanner.py", "pages/4_Equity.py",
    "pages/4_Equity.py", "pages/4_Equity.py",
]
_VIEW_KEYS = [
    "p1_view_sector", "p1_view_scanner",
    "p1_view_equity", "p1_view_equity", "p1_view_equity",
]


def _step_card(col, step_key: str, step_name: str, page: str, view_lbl: str) -> None:
    step_info  = state.get("steps", {}).get(step_key, {})
    st_status  = step_info.get("status", "pending")
    st_summary = step_info.get("summary") or ""

    # LLM decision badge
    llm = (state.get("results", {}).get(step_key) or {}).get("llm", {})
    decision   = llm.get("decision", "")
    reasoning  = llm.get("reasoning", "")
    key_metrics = llm.get("key_metrics") or {}

    icon  = "✅" if st_status == "done" else ("❌" if st_status == "failed" else "⬜")
    color = _ok_c if st_status == "done" else (_err_c if st_status == "failed" else _pend_c)

    # Build metrics HTML
    metrics_html = ""
    if key_metrics:
        items = "".join(
            f'<span style="display:inline-block;margin:2px 4px 2px 0;padding:1px 7px;'
            f'background:{_card_bd};border-radius:10px;font-size:0.70rem;color:#8b949e;">'
            f'{k}: {v}</span>'
            for k, v in list(key_metrics.items())[:4]
        )
        metrics_html = f'<div style="margin-top:6px">{items}</div>'

    with col:
        st.markdown(
            f'<div style="background:{_card_bg};border:1px solid {_card_bd};'
            f'border-radius:8px;padding:14px 16px;margin-bottom:8px;min-height:100px;">'
            f'<div style="font-size:0.85rem;font-weight:600;color:{color};margin-bottom:4px;">'
            f'{icon} {step_name}'
            + (f' &nbsp;<span style="font-size:0.78rem;color:#58a6ff">[{decision}]</span>'
               if decision and decision != "N/A" else "")
            + f'</div>'
            f'<div style="font-size:0.75rem;color:#8b949e;margin-bottom:2px">{st_summary}</div>'
            + (f'<div style="font-size:0.73rem;color:#6e7681;font-style:italic;margin-bottom:2px">'
               f'{reasoning}</div>' if reasoning else "")
            + metrics_html
            + f'</div>',
            unsafe_allow_html=True,
        )
        if st_status == "done" and st.button(view_lbl, key=f"wf_view_{step_key}",
                                             use_container_width=True):
            st.switch_page(page)


# ══════════════════════════════════════════════════════════════════════════════
# IDLE
# ══════════════════════════════════════════════════════════════════════════════
status = state.get("status", "idle")

if status == "idle":
    _hint = ("点击下方按钮，AI 将自动分析市场环境，选定板块、筛选个股并完成深度研究。"
             if _lang == "zh" else
             "Click below to launch the AI-driven pipeline. Claude will automatically "
             "select the best sector, screen for top candidates, and complete a full "
             "5-step deep-dive research workflow.")
    st.info(_hint)
    st.markdown("")

    if st.button(
        "🤖 " + ("启动 AI 研究工作流" if _lang == "zh" else "Start AI Research Workflow"),
        type="primary",
        use_container_width=True,
    ):
        reset_state()
        update_state(status="running")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# RUNNING
# ══════════════════════════════════════════════════════════════════════════════
elif status == "running":
    running_lbl = "⚡ AI 研究工作流运行中..." if _lang == "zh" else "⚡ AI Research Workflow Running..."
    st.info(running_lbl)

    containers = {s: st.empty() for s in _STEPS}
    for s, key in zip(_STEPS, _STEP_KEYS):
        containers[s].markdown(f"⬜ **{t(key)}** — {t('p1_step_pending')}")
    progress = st.progress(0)

    # ── Step 1: Sector Analysis ────────────────────────────────────────────────
    containers["sector"].markdown(f"🔵 **{t('p1_step1_name')}** — {t('p1_step_running')}")
    try:
        from rotation import compute_sector_scores, classify_rotation_phase, get_macro_indicators
        from llm_orchestrator import analyze_sector

        scores_df  = compute_sector_scores(period_days=63)
        phase_info = classify_rotation_phase(scores_df)
        macro_data = get_macro_indicators()

        llm_result = analyze_sector(scores_df, macro_data, _lang)

        # LLM picks sector; fallback to top-scoring sector
        sector = llm_result.get("decision", "")
        if not scores_df.empty:
            valid_sectors = scores_df["sector"].tolist()
            if sector not in valid_sectors:
                sector = valid_sectors[0]   # fallback to top-scoring
        subsector = llm_result.get("subsector") or None

        phase    = phase_info.get("phase", "neutral")
        top3     = phase_info.get("top3_sectors", [])
        top_row  = scores_df.iloc[0] if not scores_df.empty else {}
        top_score = float(top_row.get("score", 0)) if hasattr(top_row, "get") else 0.0

        code_summary = (
            f"phase={phase} | top3={', '.join(top3)} | "
            f"selected={sector} score={top_score:.1f}"
        )
        llm_summary = llm_result.get("summary", code_summary)

        update_step("sector", "done", llm_summary)
        update_state(
            sector=sector,
            results={"sector": {
                "phase": phase, "top_sector": sector, "score": top_score,
                "top3": top3, "subsector": subsector,
                "accelerating": phase_info.get("accelerating", []),
                "llm": llm_result,
            }},
        )
        containers["sector"].markdown(
            f"✅ **{t('p1_step1_name')}** — {llm_summary}"
            + (f"\n\n> {llm_result.get('reasoning', '')}" if llm_result.get("reasoning") else "")
        )
    except Exception as e:
        sector = "Information Technology"   # safe default
        subsector = None
        update_step("sector", "failed", str(e))
        update_state(sector=sector)
        containers["sector"].markdown(f"❌ **{t('p1_step1_name')}** — {e}")
    progress.progress(20)

    # ── Step 2: Stock Scanner ──────────────────────────────────────────────────
    containers["scan"].markdown(f"🔵 **{t('p1_step2_name')}** — {t('p1_step_running')}")
    try:
        from sectors import get_theme_constituents
        from rotation import rank_sector_stocks
        from llm_orchestrator import analyze_scanner

        # Try subsector first; fall back to parent sector
        pool = []
        if subsector:
            pool = get_theme_constituents(subsector)
        if len(pool) < 5:
            pool = get_theme_constituents(sector)
        if not pool:
            pool = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]

        pool_top = pool[:40]
        ranked   = rank_sector_stocks(tuple(pool_top), top_n=30)

        sector_ctx = state.get("results", {}).get("sector", {})
        llm_result = analyze_scanner(ranked, sector_ctx, _lang)

        # LLM picks ticker; fallback to top-ranked Leader or first stock
        ticker = llm_result.get("decision", "").upper().strip()
        if not ticker or ticker == "N/A":
            if not ranked.empty:
                leaders = ranked[ranked["tier"] == "Leader"]["ticker"].tolist()
                ticker = leaders[0] if leaders else ranked.iloc[0]["ticker"]
            else:
                ticker = pool_top[0] if pool_top else "AAPL"

        runner_up = llm_result.get("runner_up", "")
        leaders   = ranked[ranked["tier"] == "Leader"]["ticker"].tolist() if not ranked.empty and "tier" in ranked.columns else []
        pool_str  = ", ".join(pool_top[:30])
        llm_summary = llm_result.get("summary", f"{len(pool)} constituents → {ticker}")

        update_step("scan", "done", llm_summary)
        update_state(
            ticker=ticker,
            results={"scan": {
                "pool": pool_str, "total": len(pool),
                "leaders": leaders, "ticker": ticker, "runner_up": runner_up,
                "llm": llm_result,
            }},
        )
        containers["scan"].markdown(
            f"✅ **{t('p1_step2_name')}** — {llm_summary}"
            + (f"\n\n> {llm_result.get('reasoning', '')}" if llm_result.get("reasoning") else "")
        )
    except Exception as e:
        ticker = "AAPL"   # safe default
        update_step("scan", "failed", str(e))
        update_state(ticker=ticker)
        containers["scan"].markdown(f"❌ **{t('p1_step2_name')}** — {e}")
    progress.progress(40)

    # ── Step 3: Equity Research ────────────────────────────────────────────────
    containers["equity"].markdown(f"🔵 **{t('p1_step3_name')}** — {t('p1_step_running')}")
    try:
        from technical import snapshot
        from llm_orchestrator import analyze_equity

        info     = load_info(ticker)
        df_ohlcv = load_ohlcv(ticker, "1y")
        snap     = snapshot(df_ohlcv)
        earnings = load_earnings(ticker)

        sector_ctx = state.get("results", {}).get("sector", {})
        scan_ctx   = state.get("results", {}).get("scan", {})
        llm_result = analyze_equity(info, snap, earnings, sector_ctx, scan_ctx, _lang)

        name = info.get("longName", info.get("shortName", ticker))
        price_curr = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        llm_summary = llm_result.get("summary", f"{name} — {llm_result.get('decision', '')}")

        update_step("equity", "done", llm_summary)
        update_state(results={"equity": {
            "ticker": ticker, "name": name, "price": price_curr,
            "snap": {k: snap.get(k) for k in ("RSI_14", "ADX", "above_SMA200",
                                               "pct_from_52w_high", "Vol_ratio_20d")},
            "llm": llm_result,
        }})
        containers["equity"].markdown(
            f"✅ **{t('p1_step3_name')}** — {llm_summary}"
            + (f"\n\n> {llm_result.get('reasoning', '')}" if llm_result.get("reasoning") else "")
        )
    except Exception as e:
        update_step("equity", "failed", str(e))
        containers["equity"].markdown(f"❌ **{t('p1_step3_name')}** — {e}")
        info = {}
    progress.progress(60)

    # ── Step 4: Financial Analysis ─────────────────────────────────────────────
    containers["financial"].markdown(f"🔵 **{t('p1_step4_name')}** — {t('p1_step_running')}")
    try:
        from llm_orchestrator import analyze_financials

        fin    = load_financials(ticker)
        cf     = load_cashflow(ticker)
        rev    = fin["Total Revenue"].iloc[0]      if "Total Revenue"       in fin.columns else None
        gp     = fin["Gross Profit"].iloc[0]       if "Gross Profit"        in fin.columns else None
        ni     = fin["Net Income"].iloc[0]         if "Net Income"          in fin.columns else None
        op_cf  = cf["Operating Cash Flow"].iloc[0] if "Operating Cash Flow" in cf.columns else None
        capex  = cf["Capital Expenditure"].iloc[0] if "Capital Expenditure" in cf.columns else None
        fcf    = (op_cf + capex) if (op_cf is not None and capex is not None) else None
        gm_pct = (gp / rev * 100) if (gp and rev) else None

        fin_data = {
            "revenue_TTM":     fmt_large(rev),
            "gross_profit_TTM":fmt_large(gp),
            "net_income_TTM":  fmt_large(ni),
            "operating_cf_TTM":fmt_large(op_cf),
            "fcf_TTM":         fmt_large(fcf),
            "gross_margin":    f"{gm_pct:.1f}%" if gm_pct is not None else None,
            "trailing_pe":     info.get("trailingPE") if info else None,
            "forward_pe":      info.get("forwardPE")  if info else None,
            "ev_ebitda":       info.get("enterpriseToEbitda") if info else None,
        }
        fin_data = {k: v for k, v in fin_data.items() if v is not None}

        equity_ctx = state.get("results", {}).get("equity", {})
        llm_result = analyze_financials(fin_data, equity_ctx, _lang)
        llm_summary = llm_result.get("summary", f"Rev={fmt_large(rev)} | GM={gm_pct:.1f}%" if gm_pct else fmt_large(rev))

        update_step("financial", "done", llm_summary)
        update_state(results={"financial": {
            "revenue": rev, "gross_profit": gp, "net_income": ni,
            "fcf": fcf, "gross_margin_pct": gm_pct,
            "llm": llm_result,
        }})
        containers["financial"].markdown(
            f"✅ **{t('p1_step4_name')}** — {llm_summary}"
            + (f"\n\n> {llm_result.get('reasoning', '')}" if llm_result.get("reasoning") else "")
        )
    except Exception as e:
        update_step("financial", "failed", str(e))
        containers["financial"].markdown(f"❌ **{t('p1_step4_name')}** — {e}")
    progress.progress(80)

    # ── Step 5: Price & Volume ─────────────────────────────────────────────────
    containers["pv"].markdown(f"🔵 **{t('p1_step5_name')}** — {t('p1_step_running')}")
    try:
        from technical import snapshot as snapshot_fn
        from llm_orchestrator import analyze_pv

        df_pv = load_ohlcv(ticker, "1y")
        snap  = snapshot_fn(df_pv)

        equity_ctx = state.get("results", {}).get("equity", {})
        llm_result = analyze_pv(snap, equity_ctx, _lang)

        rsi     = snap.get("RSI_14")
        adx     = snap.get("ADX")
        above200 = bool(snap.get("above_SMA200", False))
        from52w  = snap.get("pct_from_52w_high")
        volr     = snap.get("Vol_ratio_20d")
        code_summary = (
            f"RSI={rsi:.1f} ADX={adx:.1f} SMA200={'✓' if above200 else '✗'} "
            f"52W={from52w:.1f}% VolRatio={volr:.2f}x"
        )
        llm_summary = llm_result.get("summary", code_summary)

        update_step("pv", "done", llm_summary)
        update_state(results={"pv": {
            "rsi": rsi, "adx": adx, "above_sma200": above200,
            "from_52w_high": from52w, "vol_ratio": volr,
            "llm": llm_result,
        }})
        containers["pv"].markdown(
            f"✅ **{t('p1_step5_name')}** — {llm_summary}"
            + (f"\n\n> {llm_result.get('reasoning', '')}" if llm_result.get("reasoning") else "")
        )
    except Exception as e:
        update_step("pv", "failed", str(e))
        containers["pv"].markdown(f"❌ **{t('p1_step5_name')}** — {e}")
    progress.progress(100)

    update_state(status="completed", current_step=None)
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# COMPLETED
# ══════════════════════════════════════════════════════════════════════════════
elif status == "completed":
    sector   = state.get("sector", "")
    ticker   = state.get("ticker", "")
    results  = state.get("results", {})
    steps    = state.get("steps", {})

    # ── Header ────────────────────────────────────────────────────────────────
    sec_res  = results.get("sector") or {}
    scan_res = results.get("scan")   or {}
    eq_res   = results.get("equity") or {}
    fin_res  = results.get("financial") or {}
    pv_res   = results.get("pv")     or {}

    subsector  = sec_res.get("subsector") or ""
    runner_up  = scan_res.get("runner_up") or ""
    eq_llm     = eq_res.get("llm") or {}
    fin_llm    = fin_res.get("llm") or {}
    pv_llm     = pv_res.get("llm") or {}

    done_lbl = "✅ AI 研究完成" if _lang == "zh" else "✅ AI Research Complete"
    header_parts = [f"**{sector}**"]
    if subsector:
        header_parts.append(f"**{subsector}**")
    header_parts.append(f"**{ticker}**")
    if runner_up:
        runner_lbl = "次选" if _lang == "zh" else "Runner-up"
        header_parts.append(f"{runner_lbl}: {runner_up}")
    st.success(f"{done_lbl} — " + " / ".join(header_parts))

    col_new, _ = st.columns([1, 5])
    with col_new:
        new_lbl = t("p1_wf_new")
        if st.button(new_lbl, use_container_width=True):
            reset_state()
            st.rerun()

    # ── Key metrics banner ────────────────────────────────────────────────────
    fin_gm   = fin_res.get("gross_margin_pct")
    pv_snap  = eq_res.get("snap") or {}
    st.divider()
    mc1, mc2, mc3, mc4, mc5 = st.columns(5)
    mc1.metric("Sector", sector)
    mc2.metric("Ticker", ticker)
    mc3.metric("Equity",    eq_llm.get("decision", "—"))
    mc4.metric("Financials",fin_llm.get("decision", "—"))
    mc5.metric("Technical", pv_llm.get("decision", "—"))

    st.divider()

    # ── Step cards ────────────────────────────────────────────────────────────
    _step_names = [t(k) for k in _STEP_KEYS]

    r1c1, r1c2, r1c3 = st.columns(3)
    _step_card(r1c1, "sector",    _step_names[0], _STEP_PAGES[0], t("p1_view_sector"))
    _step_card(r1c2, "scan",      _step_names[1], _STEP_PAGES[1], t("p1_view_scanner"))
    _step_card(r1c3, "equity",    _step_names[2], _STEP_PAGES[2], t("p1_view_equity"))

    r2c1, r2c2, _ = st.columns(3)
    _step_card(r2c1, "financial", _step_names[3], _STEP_PAGES[3], t("p1_view_equity"))
    _step_card(r2c2, "pv",        _step_names[4], _STEP_PAGES[4], t("p1_view_equity"))
