"""Page 6 — 量价分析（重定向至个股研究）

Price & Volume analysis has been merged into Page 4 (Equity Research) as a tab.
This file is kept to preserve sidebar navigation structure.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from ui_utils import apply_theme, render_sidebar, page_header, t

st.set_page_config(page_title="Price & Volume → Equity", page_icon="📉", layout="wide")
apply_theme()
render_sidebar()
page_header()

_dark = st.session_state.get("dark_mode", True)
_bg   = "#161b22" if _dark else "#f0f3f6"
_bd   = "#30363d" if _dark else "#d0d7de"
_t0   = "#e6edf3" if _dark else "#1f2328"
_t1   = "#8b949e" if _dark else "#57606a"

st.markdown(
    f'<div style="background:{_bg};border:1px solid {_bd};border-radius:10px;'
    f'padding:32px 40px;max-width:540px;margin:60px auto 0;">'
    f'<div style="font-size:2rem;margin-bottom:16px;">📉 → 🏢</div>'
    f'<div style="font-size:1.05rem;color:{_t0};margin-bottom:8px;">{t("redirect_pv")}</div>'
    f'<div style="font-size:0.85rem;color:{_t1};">'
    f'{"请切换至「个股研究」页面的「量价分析」标签页。" if st.session_state.get("language","en")=="zh" else "Please switch to the Price & Volume tab inside Equity Research."}'
    f'</div>'
    f'</div>',
    unsafe_allow_html=True,
)

st.markdown("<br>", unsafe_allow_html=True)
col_btn, _ = st.columns([1, 3])
with col_btn:
    if st.button(t("redirect_goto"), use_container_width=True):
        st.switch_page("pages/4_Equity.py")
