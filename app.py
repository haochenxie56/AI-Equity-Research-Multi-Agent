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
    st.session_state.language = "en"

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
    st.info("☁️ Cloud deployment — data fetching may be slow. If you hit a timeout, wait a moment and refresh.")

render_sidebar()

# ── Landing page ──────────────────────────────────────────────────────────────
st.title(f"📈 {t('app_title')}")
page_header()
st.caption(t("app_subtitle"))
st.divider()

st.info(t("input_prompt"))

st.divider()

# ── Module cards grid ─────────────────────────────────────────────────────────
st.subheader(t("modules_title"))
st.markdown(f"""
<div class="fin-module-grid">
  <a class="fin-module-card" href="/Overview">
    <div class="fin-module-header">
      <span class="fin-module-icon">1️⃣</span>
      <span class="fin-module-title">{t("mod_overview_title")}</span>
    </div>
    <div class="fin-module-desc">{t("mod_overview_desc")}</div>
    <div class="fin-module-arrow">→</div>
  </a>
  <a class="fin-module-card" href="/Sector">
    <div class="fin-module-header">
      <span class="fin-module-icon">2️⃣</span>
      <span class="fin-module-title">{t("mod_sector_title")}</span>
    </div>
    <div class="fin-module-desc">{t("mod_sector_desc")}</div>
    <div class="fin-module-arrow">→</div>
  </a>
  <a class="fin-module-card" href="/Scanner">
    <div class="fin-module-header">
      <span class="fin-module-icon">3️⃣</span>
      <span class="fin-module-title">{t("mod_scanner_title")}</span>
    </div>
    <div class="fin-module-desc">{t("mod_scanner_desc")}</div>
    <div class="fin-module-arrow">→</div>
  </a>
  <a class="fin-module-card" href="/Equity">
    <div class="fin-module-header">
      <span class="fin-module-icon">4️⃣</span>
      <span class="fin-module-title">{t("mod_equity_title")}</span>
    </div>
    <div class="fin-module-desc">{t("mod_equity_desc")}</div>
    <div class="fin-module-arrow">→</div>
  </a>
  <a class="fin-module-card" href="/Financial">
    <div class="fin-module-header">
      <span class="fin-module-icon">5️⃣</span>
      <span class="fin-module-title">{t("mod_fin_title")}</span>
    </div>
    <div class="fin-module-desc">{t("mod_fin_desc")}</div>
    <div class="fin-module-arrow">→</div>
  </a>
  <a class="fin-module-card" href="/PriceVolume">
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
