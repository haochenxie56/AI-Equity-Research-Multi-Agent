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
import pandas as pd
from ui_utils import (
    apply_theme, render_sidebar, load_info, load_ohlcv,
    load_financials, load_cashflow, load_earnings,
    fmt_large, page_header, t, fmt_metric_key,
)
from workflow_state import (
    init_research_state, get_state, update_state, update_step, reset_state,
)

st.set_page_config(page_title="AI Workflow", page_icon="🤖", layout="wide")
apply_theme()
render_sidebar()

init_research_state()

# On every new Streamlit session (cold start / browser refresh), reset workflow
# to idle so the page always opens in "waiting to start" state.
# The flag _wf_session_init is session-scoped: absent on first run, present
# on subsequent reruns within the same session (e.g. intra-page navigation).
if "_wf_session_init" not in st.session_state:
    st.session_state["_wf_session_init"] = True
    if get_state().get("status") != "idle":
        st.session_state.pop("_wf_conclusion", None)
        st.session_state.pop("_wf_conclusion_key", None)
        reset_state()

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
        from rotation import (compute_sector_scores, classify_rotation_phase,
                              get_macro_indicators, compute_volume_flow,
                              compute_subsector_scores)
        from sectors import SECTOR_CONFIG
        from llm_orchestrator import analyze_sector_full

        # ── Code layer: gather all 6 dimensions ───────────────────────────────
        scores_3m  = compute_sector_scores(period_days=63)
        phase_info = classify_rotation_phase(scores_3m)
        macro_data = get_macro_indicators()

        try:
            scores_1m = compute_sector_scores(period_days=21)
        except Exception:
            scores_1m = pd.DataFrame()
        try:
            scores_6m = compute_sector_scores(period_days=126)
        except Exception:
            scores_6m = pd.DataFrame()

        # Volume flow: last 5 trading-day average vol_ratio per sector
        volume_recent = {}
        try:
            vol_df = compute_volume_flow()
            if not vol_df.empty:
                recent_dates = sorted(vol_df["date"].unique())[-5:]
                vol_5d = vol_df[vol_df["date"].isin(recent_dates)]
                for sec, grp in vol_5d.groupby("sector"):
                    volume_recent[str(sec)] = round(float(grp["vol_ratio"].mean()), 2)
        except Exception:
            pass

        # Tentative sector = top-scoring by 3M
        tentative_sector = (scores_3m.iloc[0]["sector"]
                            if not scores_3m.empty else "Information Technology")
        sector_etf = SECTOR_CONFIG.get(tentative_sector, {}).get("etf", "XLK")

        # ETF returns vs SPY for tentative sector
        etf_returns = {}
        try:
            etf_df = load_ohlcv(sector_etf, "1y")
            spy_df = load_ohlcv("SPY", "1y")
            if etf_df is not None and spy_df is not None:
                for lbl, days in [("1M", 21), ("3M", 63), ("6M", 126)]:
                    if len(etf_df) >= days and len(spy_df) >= days:
                        er = (etf_df["Close"].iloc[-1] / etf_df["Close"].iloc[-days] - 1) * 100
                        sr = (spy_df["Close"].iloc[-1] / spy_df["Close"].iloc[-days] - 1) * 100
                        etf_returns[lbl] = {
                            "etf": round(float(er), 1),
                            "spy": round(float(sr), 1),
                            "excess": round(float(er - sr), 1),
                        }
        except Exception:
            pass

        # Subsector scores for tentative sector
        subsector_df = pd.DataFrame()
        try:
            subsector_df = compute_subsector_scores(tentative_sector)
        except Exception:
            pass

        # ── LLM layer: one comprehensive call for all 6 dimensions ────────────
        llm_result = analyze_sector_full({
            "macro":            macro_data,
            "phase":            phase_info,
            "scores_3m":        scores_3m,
            "scores_1m":        scores_1m,
            "scores_6m":        scores_6m,
            "volume_recent":    volume_recent,
            "etf_returns":      etf_returns,
            "subsector_scores": subsector_df,
            "sector_etf":       sector_etf,
            "tentative_sector": tentative_sector,
        }, _lang)

        # Sector decision with fallback to top-scoring
        sector = llm_result.get("decision", "")
        valid_sectors = scores_3m["sector"].tolist() if not scores_3m.empty else []
        if sector not in valid_sectors:
            sector = tentative_sector
        subsector = llm_result.get("subsector_decision") or None

        phase     = phase_info.get("phase", "neutral")
        top3      = phase_info.get("top3_sectors", [])
        top_row   = scores_3m.iloc[0] if not scores_3m.empty else {}
        top_score = float(top_row.get("score", 0)) if hasattr(top_row, "get") else 0.0

        llm_summary = llm_result.get("summary", f"selected={sector} score={top_score:.1f}")

        update_step("sector", "done", llm_summary)
        update_state(
            sector=sector,
            results={"sector": {
                "phase": phase, "top_sector": sector, "score": top_score,
                "top3": top3, "subsector": subsector,
                "accelerating": phase_info.get("accelerating", []),
                "etf_returns":  etf_returns,
                "sector_etf":   sector_etf,
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

    # ── Step 2: Stock Scanner (4-strategy multi-scan) ─────────────────────────
    containers["scan"].markdown(f"🔵 **{t('p1_step2_name')}** — {t('p1_step_running')}")
    try:
        from sectors import get_theme_constituents
        from technical import snapshot as _snap_fn
        from llm_orchestrator import analyze_scanner_multi

        # ── Build ticker pool from subsector → sector → fallback ──────────────
        pool: list[str] = []
        if subsector:
            pool = get_theme_constituents(subsector)
        if len(pool) < 5:
            pool = get_theme_constituents(sector)
        if not pool:
            pool = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]
        pool_top = pool[:40]

        # ── Code layer: run all 4 strategies in one pass over the pool ────────
        _strats     = ["Momentum", "Value", "Quality Growth", "Oversold Bounce"]
        _period     = "1y"
        _info_cache: dict = {}

        def _cached_info(tk: str) -> dict:
            if tk not in _info_cache:
                try:
                    _info_cache[tk] = load_info(tk)
                except Exception:
                    _info_cache[tk] = {}
            return _info_cache[tk]

        strategy_results: dict[str, list] = {s: [] for s in _strats}

        for tk in pool_top:
            try:
                df = load_ohlcv(tk, _period)
                if df is None or len(df) < 60:
                    continue
                snap    = _snap_fn(df)
                ret_1m  = (df["Close"].iloc[-1]/df["Close"].iloc[-21]-1)*100 if len(df)>=21 else None
                ret_3m  = (df["Close"].iloc[-1]/df["Close"].iloc[-63]-1)*100 if len(df)>=63 else None

                strat_flags: dict[str, bool] = {}
                # Value: needs info for PE filter
                try:
                    _pe = _cached_info(tk).get("trailingPE")
                    strat_flags["Value"] = _pe is not None and _pe < 20 and snap.get("RSI_14", 50) < 55
                except Exception:
                    strat_flags["Value"] = snap.get("RSI_14", 50) < 45

                strat_flags["Momentum"] = (
                    bool(snap.get("above_SMA200")) and
                    50 <= (snap.get("RSI_14") or 0) <= 72 and
                    (snap.get("Vol_ratio_20d") or 0) >= 1.1 and
                    (ret_3m or 0) > 0
                )
                strat_flags["Quality Growth"] = (
                    bool(snap.get("above_SMA200")) and
                    (snap.get("ADX") or 0) > 20 and
                    (ret_3m or 0) > 5
                )
                strat_flags["Oversold Bounce"] = (
                    (snap.get("RSI_14") or 50) < 38 and
                    bool(snap.get("above_SMA200"))
                )

                if any(strat_flags.values()):
                    info_r   = _cached_info(tk)
                    name     = info_r.get("shortName", tk)
                    mktcap   = info_r.get("marketCap") or 0
                    fwd_pe   = info_r.get("forwardPE")
                    hit_data = {
                        "ticker":      tk,
                        "name":        name,
                        "rsi":         snap.get("RSI_14"),
                        "adx":         snap.get("ADX"),
                        "3m_ret":      round(ret_3m, 1) if ret_3m is not None else None,
                        "1m_ret":      round(ret_1m, 1) if ret_1m is not None else None,
                        "vol_ratio":   snap.get("Vol_ratio_20d"),
                        "above_sma200":snap.get("above_SMA200"),
                        "mkt_cap_b":   round(mktcap/1e9, 1) if mktcap else None,
                        "fwd_pe":      round(fwd_pe, 1) if fwd_pe else None,
                    }
                    for strat, passed in strat_flags.items():
                        if passed:
                            strategy_results[strat].append(hit_data)
            except Exception:
                continue

        # Sort each strategy's hits (Momentum/QG by 3M ret desc; others by RSI asc)
        for strat in _strats:
            reverse = strat in ("Momentum", "Quality Growth")
            key_col = "3m_ret" if strat in ("Momentum", "Quality Growth") else "rsi"
            strategy_results[strat].sort(
                key=lambda x, k=key_col: (x.get(k) or -9999), reverse=reverse
            )

        # ── LLM layer: cross-strategy evaluation ──────────────────────────────
        sector_ctx = state.get("results", {}).get("sector", {})
        llm_result = analyze_scanner_multi(strategy_results, sector_ctx, _lang)

        # Extract top pick with fallback
        ticker = (llm_result.get("decision") or "").upper().strip()
        if not ticker or ticker == "N/A":
            for strat in _strats:
                if strategy_results[strat]:
                    ticker = strategy_results[strat][0]["ticker"]
                    break
            if not ticker:
                ticker = pool_top[0] if pool_top else "AAPL"

        runner_up  = llm_result.get("runner_up", "")
        selected   = llm_result.get("selected") or []
        total_hits = sum(len(v) for v in strategy_results.values())
        pool_str   = ", ".join(pool_top[:30])
        llm_summary = llm_result.get("summary", f"{total_hits} hits → {ticker}")

        update_step("scan", "done", llm_summary)
        update_state(
            ticker=ticker,
            results={"scan": {
                "pool":             pool_str,
                "total":            len(pool),
                "strategy_results": strategy_results,
                "selected":         selected,
                "ticker":           ticker,
                "runner_up":        runner_up,
                "total_hits":       total_hits,
                "llm":              llm_result,
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
# COMPLETED — report-style layout
# ══════════════════════════════════════════════════════════════════════════════
elif status == "completed":
    from datetime import datetime
    sector   = state.get("sector", "")
    ticker   = state.get("ticker", "")
    results  = state.get("results", {})
    steps    = state.get("steps", {})

    sec_res  = results.get("sector")    or {}
    scan_res = results.get("scan")      or {}
    eq_res   = results.get("equity")    or {}
    fin_res  = results.get("financial") or {}
    pv_res   = results.get("pv")        or {}

    subsector = sec_res.get("subsector") or ""
    runner_up = scan_res.get("runner_up") or ""
    sec_llm  = sec_res.get("llm")  or {}
    scan_llm = scan_res.get("llm") or {}
    eq_llm   = eq_res.get("llm")   or {}
    fin_llm  = fin_res.get("llm")  or {}
    pv_llm   = pv_res.get("llm")   or {}

    # ── Lazy-generate comprehensive conclusion (cached in session) ─────────────
    _cache_key = f"wf_conclusion_{ticker}_{sector}"
    if st.session_state.get("_wf_conclusion_key") != _cache_key:
        st.session_state["_wf_conclusion"] = None
        st.session_state["_wf_conclusion_key"] = _cache_key
    if st.session_state.get("_wf_conclusion") is None:
        with st.spinner("✍️ " + ("生成综合结论..." if _lang == "zh" else "Generating conclusion...")):
            from llm_orchestrator import synthesize_report
            st.session_state["_wf_conclusion"] = synthesize_report(state, _lang)
    conclusion_data = st.session_state["_wf_conclusion"] or {}

    rec       = conclusion_data.get("recommendation", "")
    conc_text = conclusion_data.get("conclusion", "")
    risks     = conclusion_data.get("risks") or []

    # ── Recommendation color ───────────────────────────────────────────────────
    _REC_COLORS = {
        "Buy": "#3fb950", "积极配置": "#3fb950",
        "Hold": "#d29922", "Watch": "#d29922", "观察等待": "#d29922",
        "Avoid": "#f85149", "谨慎回避": "#f85149",
    }
    rec_color = _REC_COLORS.get(rec, "#58a6ff")

    # ── Top bar: title + New Workflow button (right-aligned) ────────────────────
    title_col, btn_col = st.columns([6, 1])
    with title_col:
        report_title = ("📋 AI 研究报告" if _lang == "zh" else "📋 AI Research Report")
        st.markdown(f"## {report_title}")
    with btn_col:
        st.markdown("<div style='padding-top:10px'>", unsafe_allow_html=True)
        if st.button(t("p1_wf_new"), use_container_width=True, key="rpt_new"):
            st.session_state.pop("_wf_conclusion", None)
            st.session_state.pop("_wf_conclusion_key", None)
            reset_state()
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Report header block ─────────────────────────────────────────────────────
    now_str   = datetime.now().strftime("%Y-%m-%d %H:%M")
    path_str  = sector + (" › " + subsector if subsector else "") + " › **" + ticker + "**"
    runner_str = (f"  &nbsp;|&nbsp;  {'次选' if _lang == 'zh' else 'Runner-up'}: {runner_up}"
                  if runner_up else "")
    rec_badge = (
        f'<span style="background:{rec_color};color:#fff;padding:2px 10px;'
        f'border-radius:12px;font-size:0.82rem;font-weight:600">{rec}</span>'
        if rec else ""
    )
    gen_lbl = "生成时间" if _lang == "zh" else "Generated"
    path_lbl = "研究路径" if _lang == "zh" else "Research Path"
    rec_lbl  = "整体建议" if _lang == "zh" else "Recommendation"

    st.markdown(
        f'<div style="background:{_card_bg};border:1px solid {_card_bd};'
        f'border-radius:10px;padding:18px 24px;margin-bottom:4px;">'
        f'<div style="font-size:0.75rem;color:#8b949e;margin-bottom:8px">'
        f'{gen_lbl}: {now_str}</div>'
        f'<div style="margin-bottom:6px"><span style="font-size:0.75rem;color:#8b949e">'
        f'{path_lbl}:&nbsp;</span>{path_str}{runner_str}</div>'
        f'<div><span style="font-size:0.75rem;color:#8b949e">{rec_lbl}:&nbsp;</span>'
        f'{rec_badge}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    _sep = "：" if _lang == "zh" else ": "

    # ── Shared color maps (reused by _scan_section and _section) ───────────────
    _CONF_COLOR = {
        "High": "#3fb950", "高": "#3fb950",
        "Medium": "#d29922", "中": "#d29922",
        "Low": "#f85149", "低": "#f85149",
    }
    _STRAT_COLOR = {
        "Momentum":       "#388bfd",
        "Quality Growth": "#3fb950",
        "Value":          "#d29922",
        "Oversold Bounce":"#a371f7",
    }

    # ── Helper: render scan section with top-pick card + selected list ──────────
    def _scan_section(title: str, page: str, view_lbl: str) -> None:
        st_status = (steps.get("scan") or {}).get("status", "pending")
        icon = "✅" if st_status == "done" else ("❌" if st_status == "failed" else "⬜")
        st.markdown(f"#### {icon}&nbsp; {title}")

        if st_status == "failed":
            st.caption("⚠️ " + (steps.get("scan") or {}).get("summary", "Step failed"))

        _selected  = scan_llm.get("selected") or []
        _top_pick  = (scan_llm.get("decision") or "").upper().strip()
        _runner_up = (scan_llm.get("runner_up") or "").upper().strip()
        _s_reason  = scan_llm.get("reasoning", "")

        if not _top_pick or _top_pick == "N/A":
            # Fallback: show legacy key-value data
            legacy = {
                ("已选标的" if _lang == "zh" else "Selected"): ticker,
                ("次选" if _lang == "zh" else "Runner-up"):    runner_up or "—",
                ("股票池" if _lang == "zh" else "Pool"):       str(scan_res.get("total", "—")),
            }
            items = [(k, str(v)) for k, v in legacy.items() if v]
            if items:
                st.markdown("\n\n".join(f"**{k}**{_sep}{v}" for k, v in items))
        else:
            # ── Top-pick highlight card ──────────────────────────────────────
            _top_data   = next((s for s in _selected if s.get("ticker") == _top_pick), {})
            _top_conf   = _top_data.get("confidence", "")
            _top_strat  = _top_data.get("strategy", "")
            _top_reason = _top_data.get("reasoning", "")
            _conf_c  = _CONF_COLOR.get(_top_conf, "#58a6ff")
            _strat_c = _STRAT_COLOR.get(_top_strat, "#58a6ff")
            _lbl_top = "最强推荐" if _lang == "zh" else "Top Pick"
            _lbl_str = "策略" if _lang == "zh" else "Strategy"
            _lbl_con = "置信度" if _lang == "zh" else "Confidence"
            st.markdown(
                f'<div style="background:{_card_bg};border:2px solid {_conf_c};'
                f'border-radius:10px;padding:14px 18px;margin:8px 0 12px">'
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
                f'<span style="font-size:1.3rem;font-weight:700;color:{_conf_c}">{_top_pick}</span>'
                f'<span style="background:{_card_bd};padding:1px 8px;border-radius:10px;'
                f'font-size:0.72rem;color:#8b949e">{_lbl_top}</span>'
                + (f'<span style="background:{_strat_c}22;border:1px solid {_strat_c};'
                   f'padding:1px 8px;border-radius:10px;font-size:0.72rem;color:{_strat_c}">'
                   f'{_lbl_str}: {_top_strat}</span>' if _top_strat else "")
                + (f'<span style="background:{_conf_c}22;border:1px solid {_conf_c};'
                   f'padding:1px 8px;border-radius:10px;font-size:0.72rem;color:{_conf_c}">'
                   f'{_lbl_con}: {_top_conf}</span>' if _top_conf else "")
                + f'</div>'
                + (f'<p style="font-size:0.87rem;line-height:1.6;color:{"#e6edf3" if _dark else "#1f2328"};'
                   f'margin:0">{_top_reason}</p>' if _top_reason else "")
                + f'</div>',
                unsafe_allow_html=True,
            )

            # ── Other selected stocks ────────────────────────────────────────
            others = [s for s in _selected if s.get("ticker") != _top_pick]
            if _runner_up and not any(s.get("ticker") == _runner_up for s in _selected):
                others = [{"ticker": _runner_up, "strategy": "", "confidence": "", "reasoning": ""}] + others
            for s in others[:4]:
                tk_o   = s.get("ticker", "")
                strat  = s.get("strategy", "")
                conf   = s.get("confidence", "")
                rsn    = s.get("reasoning", "")
                sc     = _STRAT_COLOR.get(strat, "#58a6ff")
                cc     = _CONF_COLOR.get(conf, "#8b949e")
                st.markdown(
                    f'<div style="background:{_card_bg};border-left:3px solid {sc};'
                    f'border-radius:0 6px 6px 0;padding:7px 12px;margin:4px 0">'
                    f'<span style="font-weight:700;color:{sc};font-size:0.92rem">{tk_o}</span>'
                    + (f'&nbsp;<span style="background:{sc}22;border:1px solid {sc};'
                       f'padding:1px 7px;border-radius:10px;font-size:0.70rem;color:{sc};'
                       f'margin-left:5px">{strat}</span>' if strat else "")
                    + (f'&nbsp;<span style="color:{cc};font-size:0.70rem;margin-left:5px">'
                       f'{conf}</span>' if conf else "")
                    + (f'<p style="font-size:0.82rem;color:{"#e6edf3" if _dark else "#1f2328"};'
                       f'margin:3px 0 0;line-height:1.5">{rsn}</p>' if rsn else "")
                    + f'</div>',
                    unsafe_allow_html=True,
                )

            # ── Overall reasoning ────────────────────────────────────────────
            if _s_reason and "unavailable" not in _s_reason.lower():
                _lbl_rsn = "综合选股逻辑" if _lang == "zh" else "Overall Rationale"
                st.markdown(
                    f'<div style="background:{_card_bg};border:1px solid {_card_bd};'
                    f'border-radius:6px;padding:9px 14px;margin-top:8px">'
                    f'<div style="font-size:0.72rem;color:#8b949e;margin-bottom:3px">'
                    f'{_lbl_rsn}</div>'
                    f'<p style="font-size:0.86rem;line-height:1.6;color:{"#e6edf3" if _dark else "#1f2328"};'
                    f'margin:0">{_s_reason}</p></div>',
                    unsafe_allow_html=True,
                )

            # ── Strategy hit counts ──────────────────────────────────────────
            _sr = scan_res.get("strategy_results") or {}
            if _sr:
                _lbl_hits = "各策略命中" if _lang == "zh" else "Strategy Hits"
                st.caption(
                    f"{_lbl_hits}: " + "  ·  ".join(
                        f"**{s}** {len(v)}" for s, v in _sr.items()
                    )
                )

        _, _btn = st.columns([5, 1])
        with _btn:
            if st.button(view_lbl, key="rpt_scan", use_container_width=True):
                st.switch_page(page)
        st.divider()

    # ── Helper: render one report section (non-sector steps) ───────────────────
    def _section(title: str, step_key: str,
                 llm_data: dict, metrics_fallback: dict,
                 page: str, view_lbl: str) -> None:
        st_status = (steps.get(step_key) or {}).get("status", "pending")
        icon = "✅" if st_status == "done" else ("❌" if st_status == "failed" else "⬜")

        st.markdown(f"#### {icon}&nbsp; {title}")

        # Reasoning as body paragraph
        reasoning = llm_data.get("reasoning", "")
        if reasoning and "unavailable" not in reasoning.lower():
            st.markdown(
                f'<p style="font-size:0.95rem;line-height:1.75;color:var(--t0,'
                f'{"#e6edf3" if _dark else "#1f2328"});margin:8px 0 12px">'
                f'{reasoning}</p>',
                unsafe_allow_html=True,
            )
        elif st_status == "failed":
            st.caption("⚠️ " + (steps.get(step_key) or {}).get("summary", "Step failed"))

        # Key metrics as key-value text (LLM key_metrics preferred, else fallback)
        km = llm_data.get("key_metrics") or {}
        display = km if km else metrics_fallback
        if display:
            items = [(fmt_metric_key(k, _lang), str(v))
                     for k, v in list(display.items())[:6] if v]
            if items:
                st.markdown(
                    "\n\n".join(f"**{k}**{_sep}{v}" for k, v in items)
                )

        # View Details button — right-aligned
        _, _btn = st.columns([5, 1])
        with _btn:
            if st.button(view_lbl, key=f"rpt_{step_key}", use_container_width=True):
                st.switch_page(page)

        st.divider()

    # ── Helper: render sector section with 6 sub-sections ──────────────────────
    def _sector_section(title: str, llm_data: dict, code_data: dict,
                        page: str, view_lbl: str) -> None:
        st_status = (steps.get("sector") or {}).get("status", "pending")
        icon = "✅" if st_status == "done" else ("❌" if st_status == "failed" else "⬜")

        st.markdown(f"#### {icon}&nbsp; {title}")

        if st_status == "failed":
            st.caption("⚠️ " + (steps.get("sector") or {}).get("summary", "Step failed"))

        _sub_titles = {
            "macro":       ("① 宏观环境"     if _lang == "zh" else "① Macro Environment"),
            "rotation":    ("② 轮动信号"     if _lang == "zh" else "② Rotation Signal"),
            "momentum":    ("③ 板块动量对比" if _lang == "zh" else "③ Sector Momentum"),
            "etf_trend":   ("④ ETF 走势对比" if _lang == "zh" else "④ ETF Trend vs SPY"),
            "volume_flow": ("⑤ 资金流入信号" if _lang == "zh" else "⑤ Volume Flow"),
            "subsector":   ("⑥ 子板块分析"  if _lang == "zh" else "⑥ Subsector Analysis"),
        }

        has_any = any(llm_data.get(k) for k in _sub_titles)
        if has_any:
            for key, sub_title in _sub_titles.items():
                text = llm_data.get(key, "")
                if text and "unavailable" not in text.lower():
                    st.markdown(f"**{sub_title}**")
                    st.markdown(
                        f'<p style="font-size:0.92rem;line-height:1.72;'
                        f'color:var(--t0,{"#e6edf3" if _dark else "#1f2328"});'
                        f'margin:4px 0 14px;padding-left:4px">'
                        f'{text}</p>',
                        unsafe_allow_html=True,
                    )
        else:
            # Fallback: reasoning paragraph + code-layer key-value data
            reasoning = llm_data.get("reasoning", "")
            if reasoning and "unavailable" not in reasoning.lower():
                st.markdown(
                    f'<p style="font-size:0.95rem;line-height:1.75;'
                    f'color:var(--t0,{"#e6edf3" if _dark else "#1f2328"});'
                    f'margin:8px 0 12px">{reasoning}</p>',
                    unsafe_allow_html=True,
                )
            if code_data:
                items = [(fmt_metric_key(k, _lang), str(v))
                         for k, v in list(code_data.items())[:6] if v]
                if items:
                    st.markdown("\n\n".join(f"**{k}**{_sep}{v}" for k, v in items))

        _, _btn = st.columns([5, 1])
        with _btn:
            if st.button(view_lbl, key="rpt_sector", use_container_width=True):
                st.switch_page(page)

        st.divider()

    _sec_titles = [t(k) for k in _STEP_KEYS]

    # ── Section 1: Sector Analysis ─────────────────────────────────────────────
    sec_fallback = {
        "Score":    f"{sec_res.get('score', '—')}",
        "Phase":    sec_res.get("phase", "—"),
        "Top3":     ", ".join((sec_res.get("top3") or [])[:2]),
        "Subsector":subsector or "—",
    }
    _sector_section(_sec_titles[0], sec_llm, sec_fallback,
                    _STEP_PAGES[0], t("p1_view_sector"))

    # ── Section 2: Stock Scanner ───────────────────────────────────────────────
    _scan_section(_sec_titles[1], _STEP_PAGES[1], t("p1_view_scanner"))

    # ── Section 3: Equity Research ─────────────────────────────────────────────
    eq_snap = eq_res.get("snap") or {}
    eq_fallback = {
        "Decision":  eq_llm.get("decision", "—"),
        "RSI(14)":   f"{eq_snap.get('RSI_14', '—')}",
        "ADX":       f"{eq_snap.get('ADX', '—')}",
        "SMA200":    "Above ✓" if eq_snap.get("above_SMA200") else "Below ✗",
    }
    _section(_sec_titles[2], "equity",
             eq_llm, eq_fallback,
             _STEP_PAGES[2], t("p1_view_equity"))

    # ── Section 4: Financial Analysis ──────────────────────────────────────────
    fin_fallback = {
        "Revenue":     fmt_large(fin_res.get("revenue")),
        "Gross Margin":f"{fin_res.get('gross_margin_pct', 0):.1f}%" if fin_res.get("gross_margin_pct") else "—",
        "Net Income":  fmt_large(fin_res.get("net_income")),
        "FCF":         fmt_large(fin_res.get("fcf")),
    }
    _section(_sec_titles[3], "financial",
             fin_llm, fin_fallback,
             _STEP_PAGES[3], t("p1_view_equity"))

    # ── Section 5: Price & Volume ──────────────────────────────────────────────
    pv_fallback = {
        "RSI(14)":      f"{pv_res.get('rsi', '—')}",
        "ADX":          f"{pv_res.get('adx', '—')}",
        "SMA200":       "Above ✓" if pv_res.get("above_sma200") else "Below ✗",
        "Vol Ratio":    f"{pv_res.get('vol_ratio', '—')}x",
    }
    _section(_sec_titles[4], "pv",
             pv_llm, pv_fallback,
             _STEP_PAGES[4], t("p1_view_equity"))

    # ── Comprehensive Conclusion ────────────────────────────────────────────────
    conc_title = "综合结论" if _lang == "zh" else "Comprehensive Conclusion"
    st.markdown(f"#### 🔍&nbsp; {conc_title}")

    if conc_text and "unavailable" not in conc_text.lower():
        if rec:
            st.markdown(
                f'<span style="background:{rec_color};color:#fff;padding:3px 12px;'
                f'border-radius:14px;font-size:0.85rem;font-weight:600;'
                f'margin-bottom:12px;display:inline-block">{rec}</span>',
                unsafe_allow_html=True,
            )
        st.markdown(
            f'<p style="font-size:0.95rem;line-height:1.85;color:var(--t0,'
            f'{"#e6edf3" if _dark else "#1f2328"});margin:10px 0 16px">'
            f'{conc_text}</p>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("⚠️ " + (conc_text or "Conclusion generation failed"))

    if risks:
        risk_title = "主要风险" if _lang == "zh" else "Key Risks"
        st.markdown(f"**{risk_title}:**")
        for r in risks:
            st.markdown(f"- {r}")

    st.divider()

    # ── Download report as Markdown ─────────────────────────────────────────────
    today = datetime.now().strftime("%Y-%m-%d")
    date_pfx = datetime.now().strftime("%Y%m%d")

    if _lang == "zh":
        md_parts = [
            f"# AI 研究报告：{sector} / {ticker}",
            f"",
            f"**生成时间**：{today}  |  **整体建议**：{rec or 'N/A'}",
            f"**研究路径**：{sector}" + (f" › {subsector}" if subsector else "") + f" › {ticker}",
            f"",
            f"---",
        ]
    else:
        md_parts = [
            f"# AI Research Report: {sector} / {ticker}",
            f"",
            f"**Generated**: {today}  |  **Recommendation**: {rec or 'N/A'}",
            f"**Research Path**: {sector}" + (f" › {subsector}" if subsector else "") + f" › {ticker}",
            f"",
            f"---",
        ]

    _sec_md_titles = [
        ("一、板块分析" if _lang == "zh" else "I. Sector Analysis"),
        ("二、选股扫描" if _lang == "zh" else "II. Stock Scanner"),
        ("三、个股研究" if _lang == "zh" else "III. Equity Research"),
        ("四、财务分析" if _lang == "zh" else "IV. Financial Analysis"),
        ("五、量价分析" if _lang == "zh" else "V. Price & Volume"),
    ]
    # Build fallbacks for non-scan sections (scan gets special markdown below)
    _sec_others = [
        (sec_llm,  sec_fallback,  _sec_md_titles[0]),
        (eq_llm,   eq_fallback,   _sec_md_titles[2]),
        (fin_llm,  fin_fallback,  _sec_md_titles[3]),
        (pv_llm,   pv_fallback,   _sec_md_titles[4]),
    ]

    # ── Sector section markdown ────────────────────────────────────────────────
    _sector_sub_keys = ["macro","rotation","momentum","etf_trend","volume_flow","subsector"]
    _sector_sub_lbl_zh = ["宏观环境","轮动信号","板块动量","ETF走势","资金流入","子板块"]
    _sector_sub_lbl_en = ["Macro","Rotation","Momentum","ETF Trend","Volume Flow","Subsector"]
    md_parts += [f"## {_sec_md_titles[0]}", ""]
    for fk, lzh, len_ in zip(_sector_sub_keys, _sector_sub_lbl_zh, _sector_sub_lbl_en):
        txt = sec_llm.get(fk, "")
        if txt:
            lbl = lzh if _lang == "zh" else len_
            md_parts += [f"**{lbl}**", txt, ""]
    md_parts.append("---")

    # ── Scan section markdown ──────────────────────────────────────────────────
    md_parts += [f"## {_sec_md_titles[1]}", ""]
    _md_selected  = scan_llm.get("selected") or []
    _md_top_pick  = scan_llm.get("decision", "")
    _md_reasoning = scan_llm.get("reasoning", "")
    if _md_top_pick:
        md_parts.append(f"**{'最强推荐' if _lang == 'zh' else 'Top Pick'}**: {_md_top_pick}")
        md_parts.append("")
    if _md_selected:
        md_parts.append(f"| Ticker | {'策略' if _lang == 'zh' else 'Strategy'} | {'置信度' if _lang == 'zh' else 'Confidence'} | {'理由' if _lang == 'zh' else 'Reasoning'} |")
        md_parts.append("|---|---|---|---|")
        for s in _md_selected[:5]:
            md_parts.append(
                f"| {s.get('ticker','')} | {s.get('strategy','')} "
                f"| {s.get('confidence','')} | {s.get('reasoning','')[:80]} |"
            )
        md_parts.append("")
    if _md_reasoning:
        md_parts += [_md_reasoning, ""]
    md_parts.append("---")

    # ── Remaining sections (equity, financial, pv) ───────────────────────────
    for llm_d, fb_d, sec_t in _sec_others[1:]:   # skip index 0 (sector done above)
        rea = llm_d.get("reasoning", "")
        km  = llm_d.get("key_metrics") or fb_d
        md_parts += [f"## {sec_t}", ""]
        if rea:
            md_parts += [rea, ""]
        if km:
            md_parts.append("| " + (" | ".join("Metric Value".split())) + " |")
            md_parts.append("|---|---|")
            for k, v in list(km.items())[:6]:
                md_parts.append(f"| {k} | {v} |")
            md_parts.append("")
        md_parts.append("---")

    conc_h = "## 综合结论" if _lang == "zh" else "## Comprehensive Conclusion"
    md_parts += ["", conc_h, ""]
    if conc_text:
        md_parts.append(conc_text)
    if risks:
        risk_h = "### 主要风险" if _lang == "zh" else "### Key Risks"
        md_parts += ["", risk_h]
        for r in risks:
            md_parts.append(f"- {r}")
    disclaimer = (
        "\n\n---\n> **风险提示**：本报告由 AI 自动生成，仅供研究参考，不构成投资建议。"
        if _lang == "zh" else
        "\n\n---\n> **Disclaimer**: This report is AI-generated for research purposes only. Not investment advice."
    )
    md_parts.append(disclaimer)
    report_md = "\n".join(md_parts)

    # Save to research/stock/
    try:
        from pathlib import Path as _Path
        rpt_dir = _Path(__file__).parent.parent / "research" / "stock"
        rpt_dir.mkdir(parents=True, exist_ok=True)
        rpt_file = rpt_dir / f"{date_pfx}_{ticker}_ai_report.md"
        rpt_file.write_text(report_md, encoding="utf-8")
    except Exception:
        pass

    dl_lbl = "⬇ 下载研究报告 (.md)" if _lang == "zh" else "⬇ Download Report (.md)"
    st.download_button(
        dl_lbl,
        report_md,
        file_name=f"{date_pfx}_{ticker}_ai_report.md",
        mime="text/markdown",
        use_container_width=False,
    )
