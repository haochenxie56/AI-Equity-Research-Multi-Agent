"""Page 1 — Workflow Control Center

Three states:
  idle      — sector + ticker inputs + Start button
  running   — real-time step progress (5 st.empty containers)
  completed — summary cards for each step + View Details links
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import streamlit as st
from ui_utils import (
    apply_theme, render_sidebar, load_info, load_ohlcv,
    load_financials, load_cashflow, fmt_large, page_header, t,
)
from workflow_state import (
    init_research_state, get_state, update_state, update_step, reset_state,
)

st.set_page_config(page_title="Workflow", page_icon="🔭", layout="wide")
apply_theme()
render_sidebar()

init_research_state()
state = get_state()

_lang = st.session_state.get("language", "en")
_dark = st.session_state.get("dark_mode", True)

st.title("🔭 " + ("工作流控制中心" if _lang == "zh" else "Workflow Control Center"))
page_header()
st.divider()

# ── Sector options ─────────────────────────────────────────────────────────────
_SECTOR_OPTS = [
    "Technology", "Communication Services", "Healthcare",
    "Financial Services", "Consumer Cyclical", "Consumer Defensive",
    "Industrials", "Energy", "Basic Materials", "Real Estate", "Utilities",
]
_SECTOR_ZH = {
    "Technology": "科技", "Communication Services": "通信服务",
    "Healthcare": "医疗健康", "Financial Services": "金融服务",
    "Consumer Cyclical": "可选消费", "Consumer Defensive": "必选消费",
    "Industrials": "工业", "Energy": "能源",
    "Basic Materials": "基础材料", "Real Estate": "房地产", "Utilities": "公用事业",
}

_STEPS     = ["sector", "scan", "equity", "financial", "pv"]
_STEP_KEYS = ["p1_step1_name", "p1_step2_name", "p1_step3_name", "p1_step4_name", "p1_step5_name"]
_STEP_PAGES = [
    "pages/2_Sector.py", "pages/3_Scanner.py", "pages/4_Equity.py",
    "pages/4_Equity.py", "pages/4_Equity.py",
]
_VIEW_KEYS  = [
    "p1_view_sector", "p1_view_scanner",
    "p1_view_equity", "p1_view_equity", "p1_view_equity",
]

# ── Card styling helpers ───────────────────────────────────────────────────────
_card_bg  = "#161b22" if _dark else "#f6f8fa"
_card_bd  = "#30363d" if _dark else "#d0d7de"
_ok_c     = "#3fb950"
_err_c    = "#f85149"
_pend_c   = "#8b949e"
_run_c    = "#58a6ff"


def _step_card(col, step_key: str, step_name: str, page: str, view_lbl: str) -> None:
    step_info  = state.get("steps", {}).get(step_key, {})
    st_status  = step_info.get("status", "pending")
    st_summary = step_info.get("summary") or ""
    icon  = "✅" if st_status == "done" else ("❌" if st_status == "failed" else "⬜")
    color = _ok_c if st_status == "done" else (_err_c if st_status == "failed" else _pend_c)
    with col:
        st.markdown(
            f'<div style="background:{_card_bg};border:1px solid {_card_bd};border-radius:8px;'
            f'padding:14px 16px;margin-bottom:8px;min-height:80px;">'
            f'<div style="font-size:0.85rem;font-weight:600;color:{color};margin-bottom:6px;">'
            f'{icon} {step_name}</div>'
            f'<div style="font-size:0.75rem;color:#8b949e;word-break:break-word;">'
            f'{st_summary}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button(view_lbl, key=f"wf_view_{step_key}", use_container_width=True):
            st.switch_page(page)


# ══════════════════════════════════════════════════════════════════════════════
# IDLE
# ══════════════════════════════════════════════════════════════════════════════
status = state.get("status", "idle")

if status == "idle":
    st.subheader(t("p1_wf_idle_hint"))
    st.markdown("")

    col_s, col_t = st.columns(2)
    with col_s:
        _sector_display = [
            f"{_SECTOR_ZH.get(s, s)} ({s})" if _lang == "zh" else s
            for s in _SECTOR_OPTS
        ]
        sel_idx = st.selectbox(
            t("p1_wf_sector_lbl"),
            range(len(_SECTOR_OPTS)),
            format_func=lambda i: _sector_display[i],
            key="wf_sector_sel",
        )
        wf_sector = _SECTOR_OPTS[sel_idx]

    with col_t:
        wf_ticker = st.text_input(
            t("p1_wf_ticker_lbl"),
            placeholder="e.g. NVDA",
            key="wf_ticker_input",
        ).upper().strip()

    st.markdown("")
    if st.button(t("p1_wf_start"), type="primary", use_container_width=True):
        if not wf_ticker:
            st.warning(t("p1_no_ticker_wf"))
        else:
            reset_state()
            update_state(status="running", sector=wf_sector, ticker=wf_ticker)
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# RUNNING
# ══════════════════════════════════════════════════════════════════════════════
elif status == "running":
    sector = state.get("sector", "")
    ticker = state.get("ticker", "")

    st.info(f"⚡ {t('p1_wf_running')} — **{sector}** / **{ticker}**")

    containers = {s: st.empty() for s in _STEPS}
    for s, key in zip(_STEPS, _STEP_KEYS):
        containers[s].markdown(f"⬜ **{t(key)}** — {t('p1_step_pending')}")
    progress = st.progress(0)

    # ── Step 1: Sector Analysis ────────────────────────────────────────────────
    containers["sector"].markdown(
        f"🔵 **{t('p1_step1_name')}** — {t('p1_step_running')}"
    )
    try:
        from rotation import compute_sector_scores, classify_rotation_phase
        scores_df  = compute_sector_scores(period_days=63)
        phase_info = classify_rotation_phase(scores_df)
        top_row    = scores_df.iloc[0] if len(scores_df) > 0 else None
        top_sector = top_row["sector"] if top_row is not None else sector
        top_score  = float(top_row["score"]) if top_row is not None else 0.0
        phase      = phase_info.get("phase", "neutral")
        top3       = phase_info.get("top3_sectors", [])
        summary    = f"{top_sector} score={top_score:.1f} | phase={phase} | top3={', '.join(top3)}"
        update_step("sector", "done", summary)
        update_state(results={"sector": {
            "phase": phase, "top_sector": top_sector,
            "score": top_score, "top3": top3,
            "accelerating": phase_info.get("accelerating", []),
        }})
        containers["sector"].markdown(f"✅ **{t('p1_step1_name')}** — {summary}")
    except Exception as e:
        update_step("sector", "failed", str(e))
        containers["sector"].markdown(f"❌ **{t('p1_step1_name')}** — {e}")
    progress.progress(20)

    # ── Step 2: Stock Scanner ──────────────────────────────────────────────────
    containers["scan"].markdown(
        f"🔵 **{t('p1_step2_name')}** — {t('p1_step_running')}"
    )
    try:
        from sectors import get_theme_constituents
        from rotation import rank_sector_stocks
        pool     = get_theme_constituents(sector)
        pool_top = pool[:40]
        ranked   = rank_sector_stocks(tuple(pool_top), top_n=20)
        leaders  = (
            ranked[ranked["tier"] == "Leader"]["ticker"].tolist()
            if "tier" in ranked.columns else []
        )
        pool_str = ", ".join(pool_top[:30])
        summary  = (
            f"{len(pool)} constituents | leaders: {', '.join(leaders[:5])}"
            if leaders else f"{len(pool)} constituents"
        )
        update_step("scan", "done", summary)
        update_state(results={"scan": {
            "pool": pool_str,
            "total": len(pool),
            "leaders": leaders,
        }})
        containers["scan"].markdown(f"✅ **{t('p1_step2_name')}** — {summary}")
    except Exception as e:
        update_step("scan", "failed", str(e))
        containers["scan"].markdown(f"❌ **{t('p1_step2_name')}** — {e}")
    progress.progress(40)

    # ── Step 3: Equity Research ────────────────────────────────────────────────
    containers["equity"].markdown(
        f"🔵 **{t('p1_step3_name')}** — {t('p1_step_running')}"
    )
    try:
        info       = load_info(ticker)
        name       = info.get("shortName", ticker)
        gm_v       = (info.get("grossMargins") or 0) * 100
        om_v       = (info.get("operatingMargins") or 0) * 100
        roe_v      = (info.get("returnOnEquity") or 0) * 100
        total_moat = (
            min(5, max(1, int(gm_v / 12))) +
            min(5, max(1, int(om_v / 8) + 1)) +
            2 +
            min(5, max(1, int(om_v / 10))) +
            min(5, max(1, int(roe_v / 15)))
        )
        moat_lbl   = "Wide" if total_moat >= 18 else ("Narrow" if total_moat >= 12 else "None")
        analyst    = str(info.get("recommendationKey", "N/A")).upper()
        target     = info.get("targetMeanPrice")
        price_curr = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        upside     = (target / price_curr - 1) * 100 if (target and price_curr) else None
        summary    = (
            f"{name} | Moat={moat_lbl}({total_moat}/25) | {analyst}"
            + (f" | Target=${target:.2f}({upside:+.1f}%)" if upside is not None else "")
        )
        update_step("equity", "done", summary)
        update_state(results={"equity": {
            "ticker": ticker, "name": name,
            "moat_label": moat_lbl, "total_moat": total_moat,
            "analyst_rating": analyst, "target_mean": target,
            "price": price_curr, "upside": upside,
        }})
        containers["equity"].markdown(f"✅ **{t('p1_step3_name')}** — {summary}")
    except Exception as e:
        update_step("equity", "failed", str(e))
        containers["equity"].markdown(f"❌ **{t('p1_step3_name')}** — {e}")
    progress.progress(60)

    # ── Step 4: Financial Analysis ─────────────────────────────────────────────
    containers["financial"].markdown(
        f"🔵 **{t('p1_step4_name')}** — {t('p1_step_running')}"
    )
    try:
        fin     = load_financials(ticker)
        cf      = load_cashflow(ticker)
        rev     = fin["Total Revenue"].iloc[0]        if "Total Revenue"        in fin.columns else None
        gp      = fin["Gross Profit"].iloc[0]         if "Gross Profit"         in fin.columns else None
        ni      = fin["Net Income"].iloc[0]           if "Net Income"           in fin.columns else None
        op_cf   = cf["Operating Cash Flow"].iloc[0]   if "Operating Cash Flow"  in cf.columns  else None
        capex   = cf["Capital Expenditure"].iloc[0]   if "Capital Expenditure"  in cf.columns  else None
        fcf     = (op_cf + capex) if (op_cf is not None and capex is not None) else None
        gm_pct  = (gp / rev * 100) if (gp and rev) else None
        summary = (
            f"Rev={fmt_large(rev)} | GM={gm_pct:.1f}% | NI={fmt_large(ni)} | FCF={fmt_large(fcf)}"
            if gm_pct is not None else f"Rev={fmt_large(rev)}"
        )
        update_step("financial", "done", summary)
        update_state(results={"financial": {
            "revenue": rev, "gross_profit": gp,
            "net_income": ni, "fcf": fcf, "gross_margin_pct": gm_pct,
        }})
        containers["financial"].markdown(f"✅ **{t('p1_step4_name')}** — {summary}")
    except Exception as e:
        update_step("financial", "failed", str(e))
        containers["financial"].markdown(f"❌ **{t('p1_step4_name')}** — {e}")
    progress.progress(80)

    # ── Step 5: Price & Volume ─────────────────────────────────────────────────
    containers["pv"].markdown(
        f"🔵 **{t('p1_step5_name')}** — {t('p1_step_running')}"
    )
    try:
        from technical import snapshot
        df_ohlcv = load_ohlcv(ticker, "1y")
        snap     = snapshot(df_ohlcv)
        rsi      = snap.get("RSI_14")
        adx      = snap.get("ADX")
        above200 = bool(snap.get("above_SMA200", False))
        from52w  = snap.get("pct_from_52w_high")
        volr     = snap.get("Vol_ratio_20d")
        trend    = "Bullish" if (above200 and (rsi or 0) > 50) else ("Bearish" if not above200 else "Neutral")
        summary  = (
            f"RSI={rsi:.1f} | ADX={adx:.1f} | SMA200={'✓' if above200 else '✗'}"
            f" | 52W={from52w:.1f}% | VolRatio={volr:.2f}x | {trend}"
        )
        update_step("pv", "done", summary)
        update_state(results={"pv": {
            "rsi": rsi, "adx": adx, "above_sma200": above200,
            "from_52w_high": from52w, "vol_ratio": volr, "trend": trend,
        }})
        containers["pv"].markdown(f"✅ **{t('p1_step5_name')}** — {summary}")
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
    sector  = state.get("sector", "")
    ticker  = state.get("ticker", "")
    results = state.get("results", {})

    st.success(f"{t('p1_wf_done')} — **{sector}** / **{ticker}**")

    col_new, _ = st.columns([1, 5])
    with col_new:
        if st.button(t("p1_wf_new"), use_container_width=True):
            reset_state()
            st.rerun()

    # Equity result summary banner
    eq = results.get("equity") or {}
    fin = results.get("financial") or {}
    pv  = results.get("pv") or {}
    if eq or fin or pv:
        st.divider()
        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        mc1.metric("Moat",        f"{eq.get('moat_label','—')} ({eq.get('total_moat','—')}/25)" if eq else "—")
        mc2.metric("Analyst",     eq.get("analyst_rating", "—") if eq else "—")
        mc3.metric("Revenue",     fmt_large(fin.get("revenue")) if fin else "—")
        mc4.metric("Gross Margin", f"{fin.get('gross_margin_pct', 0):.1f}%" if fin.get("gross_margin_pct") else "—")
        mc5.metric("RSI(14)",     f"{pv.get('rsi', '—'):.1f}" if pv.get("rsi") else "—")

    st.divider()

    # Step cards — row 1 (steps 1-3), row 2 (steps 4-5)
    _step_names = [t(k) for k in _STEP_KEYS]

    r1c1, r1c2, r1c3 = st.columns(3)
    _step_card(r1c1, "sector",    _step_names[0], _STEP_PAGES[0], t("p1_view_sector"))
    _step_card(r1c2, "scan",      _step_names[1], _STEP_PAGES[1], t("p1_view_scanner"))
    _step_card(r1c3, "equity",    _step_names[2], _STEP_PAGES[2], t("p1_view_equity"))

    r2c1, r2c2, _ = st.columns(3)
    _step_card(r2c1, "financial", _step_names[3], _STEP_PAGES[3], t("p1_view_equity"))
    _step_card(r2c2, "pv",        _step_names[4], _STEP_PAGES[4], t("p1_view_equity"))
