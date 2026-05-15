"""
Investment Research App -- entry point.
Run: streamlit run app.py
"""

import os
import streamlit as st

# Must run before any other st call so session state is set before CSS injection
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True
if "language" not in st.session_state:
    st.session_state.language = "zh"

st.set_page_config(
    page_title="Investment Research",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from ui_utils import (
    apply_theme, render_sidebar, load_info,
    fmt_large, fmt_pct, fmt_val, page_header, t,
)

apply_theme()

if os.environ.get("STREAMLIT_SHARING_MODE"):
    st.info("☁️ 云端版本 — 数据获取可能较慢，如遇超时请稍等片刻后刷新")

ticker = render_sidebar()

# ── Landing page ──────────────────────────────────────────────────────────────
st.title(f"📈 {t('app_title')}")
page_header()
st.caption(t("app_subtitle"))
st.divider()

# Quick ticker preview
if ticker:
    with st.spinner(f"Loading {ticker}..."):
        try:
            info     = load_info(ticker)
            name     = info.get("longName", ticker)
            price    = info.get("currentPrice") or info.get("regularMarketPrice", 0)
            prev     = info.get("regularMarketPreviousClose", price)
            chg      = (price - prev) / prev * 100 if prev else 0
            mktcap   = info.get("marketCap", 0)
            sector   = info.get("sector", "N/A")
            industry = info.get("industry", "N/A")

            col1, col2 = st.columns([2, 1])
            with col1:
                arrow = "▲" if chg >= 0 else "▼"
                color = "green" if chg >= 0 else "red"
                st.markdown(f"### {name} &nbsp; `{ticker}`")
                st.markdown(
                    f"<b>&#36;{price:.2f}</b> &nbsp; "
                    f"<span style='color:{color}'>{arrow} {chg:+.2f}%</span> &nbsp;|&nbsp; "
                    f"{t('mktcap')} <b>{fmt_large(mktcap).replace('$', '&#36;')}</b>"
                    f" &nbsp;|&nbsp; {sector} / {industry}",
                    unsafe_allow_html=True,
                )
            with col2:
                st.markdown(f"#### {t('quick_nav')}")
                st.page_link("pages/1_总览.py",    label=t("nav_overview"),    icon="1️⃣")
                st.page_link("pages/5_财务分析.py", label=t("nav_financial"),   icon="5️⃣")
                st.page_link("pages/6_量价分析.py", label=t("nav_pricevolume"), icon="6️⃣")

        except Exception:
            st.warning(t("loading_failed"))
else:
    st.info(t("input_prompt"))

st.divider()

# ── Module cards grid ─────────────────────────────────────────────────────────
st.subheader(t("modules_title"))
st.markdown(f"""
<div class="fin-module-grid">
  <a class="fin-module-card" href="/总览">
    <div class="fin-module-header">
      <span class="fin-module-icon">1️⃣</span>
      <span class="fin-module-title">{t("mod_overview_title")}</span>
    </div>
    <div class="fin-module-desc">{t("mod_overview_desc")}</div>
    <div class="fin-module-arrow">→</div>
  </a>
  <a class="fin-module-card" href="/行业研究">
    <div class="fin-module-header">
      <span class="fin-module-icon">2️⃣</span>
      <span class="fin-module-title">{t("mod_sector_title")}</span>
    </div>
    <div class="fin-module-desc">{t("mod_sector_desc")}</div>
    <div class="fin-module-arrow">→</div>
  </a>
  <a class="fin-module-card" href="/选股扫描">
    <div class="fin-module-header">
      <span class="fin-module-icon">3️⃣</span>
      <span class="fin-module-title">{t("mod_scanner_title")}</span>
    </div>
    <div class="fin-module-desc">{t("mod_scanner_desc")}</div>
    <div class="fin-module-arrow">→</div>
  </a>
  <a class="fin-module-card" href="/个股研究">
    <div class="fin-module-header">
      <span class="fin-module-icon">4️⃣</span>
      <span class="fin-module-title">{t("mod_equity_title")}</span>
    </div>
    <div class="fin-module-desc">{t("mod_equity_desc")}</div>
    <div class="fin-module-arrow">→</div>
  </a>
  <a class="fin-module-card" href="/财务分析">
    <div class="fin-module-header">
      <span class="fin-module-icon">5️⃣</span>
      <span class="fin-module-title">{t("mod_fin_title")}</span>
    </div>
    <div class="fin-module-desc">{t("mod_fin_desc")}</div>
    <div class="fin-module-arrow">→</div>
  </a>
  <a class="fin-module-card" href="/量价分析">
    <div class="fin-module-header">
      <span class="fin-module-icon">6️⃣</span>
      <span class="fin-module-title">{t("mod_pv_title")}</span>
    </div>
    <div class="fin-module-desc">{t("mod_pv_desc")}</div>
    <div class="fin-module-arrow">→</div>
  </a>
</div>
""", unsafe_allow_html=True)

st.divider()
st.caption(t("data_source"))
