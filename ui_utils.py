"""
Shared utilities for all Streamlit pages.
Handles: sys.path setup, cached data loaders, sidebar renderer, chart helpers.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "lib"))

import pandas as pd
import streamlit as st

# ── Font system (professional financial typography) ───────────────────────────
# Loaded from Google Fonts and injected as the FIRST <style> block (so the
# @import is valid — it must precede all other rules in its own stylesheet).
#   * Headings / body : Inter (sans)            -> var(--font-sans)
#   * Data / numbers   : JetBrains Mono (mono)  -> var(--font-mono)
# Numeric elements use tabular (monospaced) figures so columns of numbers align.
# Mode-independent; shared by every page through apply_theme().
_FONT_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');
:root {
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
  --font-mono: 'JetBrains Mono', 'IBM Plex Mono', 'SF Mono', 'Fira Code', ui-monospace, 'Courier New', monospace;
}
/* Base UI font -> Inter (headings, body, labels, inputs, sidebar). */
html, body, .stApp,
[data-testid="stAppViewContainer"], section[data-testid="stSidebar"],
[data-testid="stMarkdownContainer"], .stMarkdown,
p, li, label, button, input, textarea, select,
h1, h2, h3, h4, h5, h6, [data-testid="stHeading"] {
  font-family: var(--font-sans) !important;
}
h1, h2, h3, h4, h5, h6 { letter-spacing: -0.01em; }
/* Data / numeric elements -> JetBrains Mono with aligned (tabular) figures. */
[data-testid="stMetricValue"], [data-testid="stMetricValue"] > div,
[data-testid="stMetricDelta"], [data-testid="stMetricDelta"] > div,
.fin-card-value, .fin-logo-title, .fin-num,
code, pre, kbd, samp,
[style*="font-variant-numeric"] {
  font-family: var(--font-mono) !important;
  font-variant-numeric: tabular-nums !important;
  font-feature-settings: 'tnum' 1 !important;
}
/* Tables / dataframes: align numeric columns. */
[data-testid="stTable"] td, [data-testid="stDataFrame"] td {
  font-variant-numeric: tabular-nums;
}
</style>"""

# ── Color token CSS (injected before structural CSS) ──────────────────────────
# Accent / data colors never change with mode — kept hardcoded in _GLOBAL_CSS.
# Only bg / border / text tokens are exposed as CSS variables.

_CSS_TOKENS_DARK = """<style>
:root {
  --bg-0: #0d1117;   --bg-1: #161b22;   --bg-2: #1c2128;
  --bd:   #30363d;
  --t0:   #e6edf3;   --t1:   #8b949e;   --t2:   #484f58;
  --chart-bg: #0d1117; --chart-grid: #21262d; --chart-txt: #8b949e;
  --chart-line: #30363d;
}
</style>"""

_CSS_TOKENS_LIGHT = """<style>
:root {
  --bg-0: #f6f8fa;   --bg-1: #ffffff;   --bg-2: #f6f8fa;
  --bd:   #d0d7de;
  --t0:   #1f2328;   --t1:   #57606a;   --t2:   #8c959f;
  --chart-bg: #ffffff; --chart-grid: #d0d7de; --chart-txt: #57606a;
  --chart-line: #d0d7de;
}
</style>"""

# ── Structural CSS (uses var() for theme-sensitive colors) ────────────────────

_GLOBAL_CSS = """
<style>
/* ── Strip Streamlit chrome ── */
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stHeader"]     { background: var(--bg-0) !important;
                                border-bottom: 1px solid var(--bd) !important; }
#MainMenu, footer            { display: none !important; }

/* ── Page background ── */
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
.main .block-container         { background-color: var(--bg-0) !important; }

/* ── Sidebar ── */
section[data-testid="stSidebar"],
[data-testid="stSidebar"] > div {
    background-color: var(--bg-0) !important;
    border-right: 1px solid var(--bd) !important;
}

/* ── Sidebar logo ── */
.fin-logo {
    padding: 4px 0 14px 0;
    border-bottom: 1px solid var(--bd);
    margin-bottom: 10px;
}
.fin-logo-title {
    font-size: 1.0rem; font-weight: 800; color: #388bfd;
    letter-spacing: 0.05em; line-height: 1.25;
    font-family: var(--font-mono);
}
.fin-logo-sub {
    font-size: 0.60rem; color: var(--t2);
    letter-spacing: 0.13em; text-transform: uppercase; margin-top: 3px;
}

/* ── Sidebar nav links ── */
[data-testid="stSidebarNavLink"] {
    border-radius: 6px !important; margin: 2px 0 !important;
    padding: 7px 14px 7px 13px !important;
    color: var(--t1) !important; font-size: 0.84rem !important;
    border-left: 3px solid transparent !important;
    transition: all 0.15s ease; text-decoration: none !important;
}
[data-testid="stSidebarNavLink"]:not(:last-child) {
    border-bottom: 1px solid var(--bg-2) !important;
}
[data-testid="stSidebarNavLink"]:hover {
    background: rgba(56,139,253,0.07) !important;
    color: var(--t0) !important;
    border-left-color: rgba(56,139,253,0.35) !important;
}
[data-testid="stSidebarNavLink"][aria-current="page"] {
    background: rgba(56,139,253,0.12) !important;
    border-left: 3px solid #388bfd !important;
    color: #388bfd !important; font-weight: 600 !important;
}

/* ── Typography ── */
.stApp, .stMarkdown, p, li, label { color: var(--t0); }
h1, h2, h3, h4 { color: var(--t0) !important; font-weight: 600 !important; }

/* ── Buttons ── */
.stButton > button,
[data-testid="stDownloadButton"] > button,
[data-testid="stBaseButton-secondary"] {
    background: transparent !important; border: 1px solid #388bfd !important;
    color: #388bfd !important; border-radius: 6px !important;
    font-weight: 500; transition: all 0.18s ease;
}
.stButton > button:hover,
[data-testid="stDownloadButton"] > button:hover {
    background: rgba(56,139,253,0.13) !important;
    box-shadow: 0 0 0 3px rgba(56,139,253,0.18) !important;
    color: var(--t0) !important;
}
.stButton > button[kind="primary"],
[data-testid="stBaseButton-primary"] {
    background: #388bfd !important; border-color: #388bfd !important; color: #ffffff !important;
}
.stButton > button[kind="primary"]:hover {
    background: #1f6feb !important; border-color: #1f6feb !important;
    box-shadow: 0 0 0 3px rgba(56,139,253,0.25) !important;
}

/* ── st.metric cards ── */
[data-testid="metric-container"] {
    background: var(--bg-1) !important; border: 1px solid var(--bd) !important;
    border-left: 3px solid #388bfd !important;
    border-radius: 8px !important; padding: 14px 18px !important;
    transition: border-left-color 0.18s ease;
}
[data-testid="metric-container"]:hover {
    border-left-color: #58a6ff !important;
    border-color: rgba(56,139,253,0.2) !important;
}
[data-testid="stMetricLabel"] > div {
    font-size: 0.62rem !important; color: var(--t1) !important;
    text-transform: uppercase; letter-spacing: 0.10em;
    font-weight: 500; margin-bottom: 6px !important;
}
[data-testid="stMetricValue"] > div {
    font-size: 1.1rem !important; font-weight: 700 !important;
    color: var(--t0) !important;
    font-family: var(--font-mono) !important;
    font-variant-numeric: tabular-nums !important;
    letter-spacing: -0.01em;
    white-space: normal !important; word-break: break-word !important;
}
[data-testid="stMetricDelta"] svg { display: none !important; }
[data-testid="stMetricDelta"] > div { font-size: 0.78rem !important; font-weight: 600; margin-top: 4px; }
[data-testid="stMetricDelta"][data-direction="up"]   > div { color: #3fb950 !important; }
[data-testid="stMetricDelta"][data-direction="down"] > div { color: #f85149 !important; }

/* ── Custom HTML metric cards ── */
.fin-metric-card {
    background: var(--bg-1); border: 1px solid var(--bd);
    border-left: 3px solid #388bfd; border-radius: 8px;
    padding: 14px 18px; margin-bottom: 2px;
    transition: border-left-color 0.18s ease, border-color 0.18s ease;
}
.fin-metric-card:hover { border-left-color: #58a6ff; border-color: rgba(56,139,253,0.2); }
.fin-card-label {
    font-size: 0.62rem; color: var(--t1); text-transform: uppercase;
    letter-spacing: 0.10em; font-weight: 500; margin-bottom: 6px;
}
.fin-card-value {
    font-size: 1.4rem; font-weight: 700; color: var(--t0);
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.01em; line-height: 1.1;
}
.fin-card-delta { font-size: 0.78rem; font-weight: 600; margin-top: 5px; }
.fin-delta-pos  { color: #3fb950; }
.fin-delta-neg  { color: #f85149; }
.fin-delta-neu  { color: var(--t1); }

/* ── Plotly containers ── */
[data-testid="stPlotlyChart"] {
    background: var(--bg-1) !important; border-radius: 10px !important;
    border: 1px solid var(--bd) !important; padding: 4px !important; overflow: hidden;
}
.modebar-container { display: none !important; }

/* ── Inputs ── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    background-color: var(--bg-2) !important; border: 1px solid var(--bd) !important;
    color: var(--t0) !important; border-radius: 6px;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: #388bfd !important;
    box-shadow: 0 0 0 3px rgba(56,139,253,0.18) !important; outline: none !important;
}
section[data-testid="stSidebar"] .stTextInput > div > div > input {
    border-color: #388bfd !important; background-color: var(--bg-2) !important;
    font-family: var(--font-mono) !important;
    font-variant-numeric: tabular-nums !important;
    font-weight: 700; font-size: 1.0rem; color: #388bfd !important; letter-spacing: 0.10em;
}

/* ── Selectbox ── */
.stSelectbox > div > div,
[data-baseweb="select"] > div {
    background-color: var(--bg-2) !important;
    border-color: var(--bd) !important; color: var(--t0) !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] { background: transparent; border-bottom: 1px solid var(--bd); gap: 2px; }
.stTabs [data-baseweb="tab"] { color: var(--t1) !important; background: transparent !important; border: none !important; }
.stTabs [aria-selected="true"] {
    color: #388bfd !important; background: rgba(56,139,253,0.08) !important;
    border-bottom: 2px solid #388bfd !important; font-weight: 600;
}

/* ── Expanders ── */
details { border: 1px solid var(--bd) !important; border-radius: 6px !important; background: var(--bg-1) !important; }
summary { color: var(--t0) !important; }

/* ── Dataframes ── */
[data-testid="stDataFrame"], [data-testid="stTable"] {
    border: 1px solid var(--bd); border-radius: 8px; overflow: hidden;
}

/* ── Progress / spinner / dividers / checkboxes ── */
.stProgress > div > div > div > div { background: linear-gradient(90deg, #388bfd, #58a6ff) !important; }
.stSpinner > div { border-top-color: #388bfd !important; }
hr { border-color: var(--bd) !important; opacity: 1; }
.stCheckbox span { color: var(--t0) !important; }

/* ── Page accent line ── */
.fin-header-line {
    height: 2px;
    background: linear-gradient(90deg, #388bfd 0%, #58a6ff 45%, transparent 100%);
    border-radius: 1px; margin-bottom: 0.75rem;
}

/* ── Cache status dots ── */
.cdot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 5px; vertical-align: middle; }
.cdot-ok  { background: #3fb950; animation: dpulse 2.5s ease-in-out infinite; }
.cdot-old { background: var(--t2); }
@keyframes dpulse {
    0%,100% { opacity:1; box-shadow: 0 0 4px #3fb950; }
    50%      { opacity:.6; box-shadow: 0 0 9px #3fb950; }
}

/* ── Module grid cards (home page) ── */
.fin-module-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
    margin: 8px 0 20px 0;
}
.fin-module-card {
    background: var(--bg-1);
    border: 1px solid var(--bd);
    border-radius: 10px;
    padding: 20px 20px 16px 20px;
    text-decoration: none !important;
    display: flex; flex-direction: column; min-height: 96px;
    transition: border-color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
    cursor: pointer;
}
.fin-module-card:hover {
    border-color: #388bfd;
    background: var(--bg-2);
    box-shadow: 0 0 0 1px rgba(56,139,253,0.18);
}
.fin-module-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.fin-module-icon { font-size: 1.05rem; line-height: 1; }
.fin-module-title { font-size: 0.95rem; font-weight: 600; color: var(--t0); }
.fin-module-desc { font-size: 0.76rem; color: var(--t1); line-height: 1.45; flex: 1; }
.fin-module-arrow {
    align-self: flex-end; color: #388bfd; font-size: 1.0rem;
    margin-top: 8px; opacity: 0.6;
    transition: opacity 0.15s ease, transform 0.15s ease;
}
.fin-module-card:hover .fin-module-arrow { opacity: 1; transform: translateX(3px); }
</style>
"""


_LIGHT_EXTRA_CSS = """<style>
/* ── Light mode: markdown-rendered table styling (report_md, etc.) ── */
.stMarkdown table { border-collapse: collapse !important; width: 100%; }
.stMarkdown th {
    background: #f6f8fa !important; color: #1f2328 !important;
    border: 1px solid #d0d7de !important; padding: 8px 12px !important;
    font-weight: 600 !important;
}
.stMarkdown td {
    color: #1f2328 !important; border: 1px solid #d0d7de !important;
    padding: 6px 12px !important; background: #ffffff !important;
}
.stMarkdown tr:nth-child(even) td { background: #f6f8fa !important; }

/* ── Light mode: selectbox / multiselect dropdown portal ── */
/* The popup is rendered at document root, outside the app container */
[data-baseweb="popover"],
[data-baseweb="popover"] > div {
    background-color: #ffffff !important;
}
[data-baseweb="menu"] {
    background-color: #ffffff !important;
    border: 1px solid #d0d7de !important;
    box-shadow: 0 8px 24px rgba(140,149,159,0.2) !important;
}
[data-baseweb="option"],
li[role="option"] {
    background-color: #ffffff !important;
    color: #1f2328 !important;
}
[data-baseweb="option"]:hover,
li[role="option"]:hover {
    background-color: #f6f8fa !important;
    color: #1f2328 !important;
}
[aria-selected="true"][data-baseweb="option"],
[aria-selected="true"][role="option"] {
    background-color: #ddf4ff !important;
    color: #0969da !important;
}

/* ── Light mode: multiselect chips / tags ── */
[data-baseweb="tag"] {
    background-color: #ddf4ff !important;
    border-color: rgba(84,174,255,0.25) !important;
}
[data-baseweb="tag"] span { color: #0969da !important; }
[data-baseweb="tag"] button svg { fill: #0969da !important; }

/* ── Light mode: number input stepper buttons ── */
[data-testid="stNumberInput"] button {
    background-color: #f6f8fa !important;
    border-color: #d0d7de !important;
    color: #1f2328 !important;
}

/* ── Light mode: slider thumb ── */
[data-testid="stSlider"] [role="slider"] {
    background-color: #388bfd !important;
    border-color: #388bfd !important;
}

/* ── Light mode: code / pre blocks ── */
code, pre {
    background-color: #f6f8fa !important;
    color: #1f2328 !important;
}
.stMarkdown code {
    border: 1px solid #d0d7de !important;
}

/* ── Light mode: info / warning / error alert boxes ── */
[data-testid="stAlert"] {
    background-color: #f6f8fa !important;
    border-color: #d0d7de !important;
    color: #1f2328 !important;
}

/* ── Light mode: expander summary row ── */
details summary {
    background-color: #f6f8fa !important;
    color: #1f2328 !important;
}
details[open] > div {
    background-color: #ffffff !important;
}

/* ── Light mode: tab panel background ── */
.stTabs [data-baseweb="tab-panel"] {
    background-color: transparent !important;
}

/* ── Light mode: caption / small text ── */
[data-testid="stCaptionContainer"] p {
    color: #57606a !important;
}
</style>"""


def apply_theme() -> None:
    """Inject CSS tokens + structural CSS. Call at the top of every page."""
    dark = st.session_state.get("dark_mode", True)
    tokens = _CSS_TOKENS_DARK if dark else _CSS_TOKENS_LIGHT
    extra  = "" if dark else _LIGHT_EXTRA_CSS
    # _FONT_CSS first: its @import must lead its own <style> block. Color tokens
    # + structural CSS follow and reference var(--font-mono) / var(--font-sans).
    st.markdown(_FONT_CSS + tokens + _GLOBAL_CSS + extra, unsafe_allow_html=True)


# Keep old name as alias so existing call-sites in render_sidebar() still work
inject_global_css = apply_theme


def get_plotly_theme() -> dict:
    """Return Plotly layout color kwargs matching the current theme."""
    dark = st.session_state.get("dark_mode", True)
    bg   = "#0d1117" if dark else "#ffffff"
    bg1  = "#0d1117" if dark else "#f6f8fa"
    grid = "#21262d" if dark else "#d0d7de"
    txt  = "#8b949e" if dark else "#1f2328"
    return dict(
        paper_bgcolor=bg,
        plot_bgcolor=bg1,
        font=dict(color=txt),
        xaxis=dict(gridcolor=grid, linecolor=grid, zeroline=False,
                   tickfont=dict(color=txt)),
        yaxis=dict(gridcolor=grid, linecolor=grid, zeroline=False,
                   tickfont=dict(color=txt)),
    )


def page_header() -> None:
    """Renders the 2-px gradient accent line that sits under the page title."""
    st.markdown('<div class="fin-header-line"></div>', unsafe_allow_html=True)


# ── Cached data loaders (in-memory + parquet) ─────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _load_ohlcv_impl(ticker: str, period: str = "1y") -> pd.DataFrame:
    from data_fetcher import get_ohlcv
    return get_ohlcv(ticker, period)


def load_ohlcv(ticker: str, period: str = "1y") -> pd.DataFrame:
    try:
        return _load_ohlcv_impl(ticker, period)
    except Exception:
        st.warning("⚠️ Data fetch failed. Please try again or check the ticker symbol.")
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def _load_info_impl(ticker: str) -> dict:
    from data_fetcher import get_info
    return get_info(ticker)


def load_info(ticker: str) -> dict:
    try:
        return _load_info_impl(ticker)
    except Exception:
        st.warning("⚠️ Data fetch failed. Please try again or check the ticker symbol.")
        return {}


@st.cache_data(ttl=7 * 86400, show_spinner=False)
def load_financials(ticker: str) -> pd.DataFrame:
    from data_fetcher import get_financials
    return get_financials(ticker)


@st.cache_data(ttl=7 * 86400, show_spinner=False)
def load_balance_sheet(ticker: str) -> pd.DataFrame:
    from data_fetcher import get_balance_sheet
    return get_balance_sheet(ticker)


@st.cache_data(ttl=7 * 86400, show_spinner=False)
def load_cashflow(ticker: str) -> pd.DataFrame:
    from data_fetcher import get_cashflow
    return get_cashflow(ticker)


@st.cache_data(ttl=3600, show_spinner=False)
def load_earnings(ticker: str) -> dict:
    from data_fetcher import get_earnings_calendar
    return get_earnings_calendar(ticker)


@st.cache_data(ttl=300, show_spinner=False)
def load_prepost(ticker: str) -> dict:
    from data_fetcher import get_prepost_price
    return get_prepost_price(ticker)


@st.cache_data(ttl=1800, show_spinner=False)
def _load_news_impl(ticker: str, days: int = 7) -> list:
    from data_fetcher import get_news
    return get_news(ticker, days=days)


def load_news(ticker: str, days: int = 7) -> list:
    """Cached Finnhub news fetch (30-min TTL). Returns [] on error / missing key."""
    try:
        return _load_news_impl(ticker, days)
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def load_ohlcv_multi(tickers: tuple, period: str = "1y") -> dict[str, pd.DataFrame]:
    """Load OHLCV for multiple tickers. Use tuple (not list) for cache hashing."""
    from data_fetcher import get_ohlcv
    result = {}
    for t in tickers:
        try:
            result[t] = get_ohlcv(t, period)
        except Exception:
            pass
    return result


# ── Bilingual field reader ─────────────────────────────────────────────────────

# Substrings that identify LLM error/fallback messages.
# All text matching any of these is suppressed at the bi() level so callers
# never need to check individually.  Covers both the current fallback format
# ("unavailable") and the legacy format ("could not be parsed").
_BI_ERROR_PHRASES: tuple[str, ...] = ("unavailable", "could not be parsed")


def bi(llm: dict, field: str, lang: str | None = None) -> str:
    """
    Read the language-appropriate version of a bilingual LLM field.

    LLM results store both versions as {field}_en and {field}_zh after
    translator.add_bilingual() is applied at generation time.

    Falls back to the undecorated {field} key for backwards compatibility
    with any result that was generated before the bilingual system was added.

    Returns "" (empty string) for any LLM error/fallback message so callers
    can use the simple ``if text:`` pattern without further inspection.

    Usage:
        from ui_utils import bi
        text = bi(sec_llm, "macro", _lang)   # reads "macro_zh" or "macro_en"
    """
    if lang is None:
        lang = st.session_state.get("language", "en")
    text = llm.get(f"{field}_{lang}") or llm.get(field) or ""
    if text:
        lower = text.lower()
        if any(p in lower for p in _BI_ERROR_PHRASES):
            return ""
    return text


# ── Sidebar ───────────────────────────────────────────────────────────────────

def init_session():
    defaults = {
        "ticker": "", "scan_results": None, "last_report": {},
        "dark_mode": True, "language": "en",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def render_sidebar() -> None:
    inject_global_css()
    init_session()
    with st.sidebar:
        st.markdown(
            '<div class="fin-logo">'
            '<div class="fin-logo-title">◈&nbsp;EQUITY RESEARCH</div>'
            '<div class="fin-logo-sub">NYSE · NASDAQ · US MARKETS</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        st.divider()

        # ── Language toggle ──
        _lang = st.session_state.get("language", "en")
        _ll, _lr = st.columns(2)
        if _ll.button("🇺🇸 EN", type="primary" if _lang == "en" else "secondary",
                      use_container_width=True, key="_lang_en"):
            st.session_state.language = "en"
            st.rerun()
        if _lr.button("🇨🇳 中文", type="primary" if _lang == "zh" else "secondary",
                      use_container_width=True, key="_lang_zh"):
            st.session_state.language = "zh"
            st.rerun()

        # ── Dark / light mode toggle ──
        current = st.session_state.get("dark_mode", True)
        toggled = st.toggle(t("dark_mode"), value=current, key="_dark_mode_widget")
        if toggled != current:
            st.session_state.dark_mode = toggled
            st.rerun()

        st.caption(t("disclaimer"))

        st.divider()

        # ── Page navigation ──
        st.markdown(
            f'<p style="font-size:0.70rem;color:var(--t1);text-transform:uppercase;'
            f'letter-spacing:0.08em;margin-bottom:4px">{t("nav_section")}</p>',
            unsafe_allow_html=True,
        )
        # Phase 6C-B — Investment Cockpit is the primary entry point and data
        # aggregation hub, so it leads the navigation (right after Home). The AI
        # Research Workflow (pages/1_Overview.py) is REMOVED from the sidebar; the
        # page file is retained and remains reachable by URL, and its nav_p1
        # translation key is kept (deprecated) so nothing that references it
        # breaks. Phase 5P source-page cleanup is preserved: Financial Analysis
        # (pages/5_Financial.py) and Price & Volume (pages/6_PriceVolume.py) stay
        # source sub-surfaces under Equity Research and are not listed here; their
        # nav_p5 / nav_p6 keys remain as legacy source-module labels.
        st.page_link("app.py",                        label=t("nav_home"))
        st.page_link("pages/7_Investment_Cockpit.py", label=t("nav_p7"))
        st.page_link("pages/8_Macro_Dashboard.py",    label=t("nav_p8"))
        st.page_link("pages/2_Sector.py",             label=t("nav_p2"))
        st.page_link("pages/3_Scanner.py",            label=t("nav_p3"))
        st.page_link("pages/4_Equity.py",             label=t("nav_p4"))
        st.page_link("pages/9_Trading_Desk.py",       label=t("nav_p9"))


# ── Number formatting ─────────────────────────────────────────────────────────

def fmt_large(v, decimals: int = 2, prefix: str = "$") -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "N/A"
    v = float(v)
    if abs(v) >= 1e12:
        return f"{prefix}{v/1e12:.{decimals}f}T"
    if abs(v) >= 1e9:
        return f"{prefix}{v/1e9:.{decimals}f}B"
    if abs(v) >= 1e6:
        return f"{prefix}{v/1e6:.{decimals}f}M"
    return f"{prefix}{v:,.0f}"


def fmt_pct(v, decimals: int = 1) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "N/A"
    return f"{float(v)*100:.{decimals}f}%"


def fmt_val(v, prefix: str = "", suffix: str = "", decimals: int = 2) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "N/A"
    return f"{prefix}{float(v):.{decimals}f}{suffix}"


# ── Metric key → human-readable label ─────────────────────────────────────────
# Tuples are (en_label, zh_label)
KEY_LABELS: dict[str, tuple[str, str]] = {
    "quantitative_score":    ("Score",          "综合评分"),
    "3m_excess_return":      ("3M Excess",       "3月超额收益"),
    "1m_excess_return":      ("1M Excess",       "1月超额收益"),
    "momentum_acceleration": ("Momentum",        "动量加速"),
    "fwd_pe":                ("Fwd P/E",         "预期市盈率"),
    "mkt_cap_b":             ("Mkt Cap (B)",     "市值（十亿）"),
    "3m_ret":                ("3M Return",       "3月涨幅"),
    "rsi":                   ("RSI",             "RSI"),
    "gross_margin":          ("Gross Margin",    "毛利率"),
    "net_margin":            ("Net Margin",      "净利润率"),
    "fcf_quality":           ("FCF Quality",     "现金流质量"),
    "valuation":             ("Valuation",       "估值对比"),
    "trend":                 ("Trend",           "趋势"),
    "momentum":              ("Momentum",        "动量"),
    "support":               ("Support",         "支撑位"),
    "resistance":            ("Resistance",      "压力位"),
}


def fmt_metric_key(k: str, lang: str = "en") -> str:
    """Map a raw JSON key to a human-readable label. Falls back to title-case."""
    entry = KEY_LABELS.get(k.lower())
    if entry:
        return entry[1] if lang == "zh" else entry[0]
    return k.replace("_", " ").title()


# ── Financial table formatter ─────────────────────────────────────────────────

def format_fin_df(df: pd.DataFrame, unit: str = "B") -> pd.DataFrame:
    """Format a financial DataFrame with $B/$M values for display."""
    out = pd.DataFrame(index=df.index)
    divisor = 1e9 if unit == "B" else 1e6
    label = unit
    for col in df.columns:
        try:
            out[str(col)[:10]] = df[col].apply(
                lambda x: f"${x/divisor:.2f}{label}" if pd.notna(x) and x != 0
                else ("—" if pd.notna(x) else "N/A")
            )
        except Exception:
            out[str(col)[:10]] = df[col].astype(str)
    return out


# ── Plotly theme ──────────────────────────────────────────────────────────────

# Static dark defaults (used as fallback and by PLOTLY_LAYOUT consumers)
PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="#0d1117",
    plot_bgcolor="#0d1117",
    margin=dict(l=8, r=8, t=36, b=8),
    font=dict(size=12, color="#8b949e"),
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02,
        bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8b949e", size=11),
    ),
)

# Data color palette — invariant across modes
CHART_COLORS = dict(
    blue="#58a6ff",
    purple="#bc8cff",
    green="#3fb950",
    red="#f85149",
    amber="#d29922",
    sma20="#388bfd",
    sma50="#d29922",
    sma200="#bc8cff",
    up="#3fb950",
    down="#f85149",
)


def apply_layout(fig, title: str = "", height: int = 400):
    """Apply standard layout. Automatically adapts to dark / light mode."""
    dark = st.session_state.get("dark_mode", True)
    if dark:
        bg   = "#0d1117"
        grid = "#21262d"
        line = "#30363d"
        txt  = "#8b949e"
        t0   = "#e6edf3"
        tpl  = "plotly_dark"
        legend_cfg = dict(
            orientation="h", yanchor="bottom", y=1.02,
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=txt, size=11),
        )
        hover_cfg = dict(bgcolor="#1c2128", font_color="#e6edf3", bordercolor="#30363d")
    else:
        bg   = "#ffffff"
        grid = "#d0d7de"
        line = "#d0d7de"
        txt  = "#1f2328"
        t0   = "#1f2328"
        tpl  = "plotly_white"
        legend_cfg = dict(
            x=0.01, y=0.99, xanchor="left", yanchor="top",
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="#d0d7de", borderwidth=1,
            font=dict(color="#1f2328", size=11),
        )
        hover_cfg = dict(bgcolor="#ffffff", font_color="#1f2328", bordercolor="#d0d7de")

    fig.update_layout(
        title=dict(text=title, font=dict(color=t0, size=13), x=0.01),
        height=height,
        template=tpl,
        paper_bgcolor=bg,
        plot_bgcolor=bg,
        margin=dict(l=8, r=8, t=36, b=8),
        font=dict(size=12, color=txt),
        legend=legend_cfg,
        hoverlabel=hover_cfg,
    )
    axis_style = dict(
        showgrid=True, gridwidth=1, gridcolor=grid,
        linecolor=line, zeroline=False,
        tickfont=dict(color=txt, size=11),
    )
    fig.update_xaxes(**axis_style)
    fig.update_yaxes(**axis_style)
    return fig


def apply_legend(fig):
    """Place legend above the plot area, right-aligned, same level as title."""
    dark = st.session_state.get("dark_mode", True)
    font_color = "#e6edf3" if dark else "#1f2328"
    fig.update_layout(
        legend=dict(
            orientation="h",
            x=1,
            y=1.02,
            xanchor="right",
            yanchor="bottom",
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            font=dict(color=font_color, size=11),
        ),
        margin=dict(t=50),
    )


# ── Report save & download ────────────────────────────────────────────────────

def download_report_button(content: str, filename: str, label: str = "⬇ Download Report"):
    st.download_button(
        label=label,
        data=content.encode("utf-8"),
        file_name=filename,
        mime="text/markdown",
    )


# ── Custom metric card ────────────────────────────────────────────────────────

def metric_card(
    label: str,
    value: str,
    delta: str | None = None,
    positive: bool | None = None,
    accent: str = "#388bfd",
) -> None:
    """Render a styled HTML metric card with optional delta indicator."""
    if delta is None:
        delta_html = ""
    elif positive is True:
        delta_html = f'<div class="fin-card-delta fin-delta-pos">▲ {delta}</div>'
    elif positive is False:
        delta_html = f'<div class="fin-card-delta fin-delta-neg">▼ {delta}</div>'
    else:
        delta_html = f'<div class="fin-card-delta fin-delta-neu">{delta}</div>'

    st.markdown(
        f'<div class="fin-metric-card" style="border-left-color:{accent}">'
        f'<div class="fin-card-label">{label}</div>'
        f'<div class="fin-card-value">{value}</div>'
        f'{delta_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── Plotly chart with config ──────────────────────────────────────────────────

def render_chart(fig, height: int = 400, key: str | None = None) -> None:
    """Render a Plotly figure with modebar hidden."""
    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"displayModeBar": False, "scrollZoom": False},
        key=key,
    )


# ── Light-mode-aware dataframe styling ───────────────────────────────────────

def style_df(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    """Return a pandas Styler with alternating rows for the current theme.
    Pass the result to st.dataframe() to get theme-consistent table colors."""
    dark = st.session_state.get("dark_mode", True)
    if dark:
        return df.style

    def _alt_rows(data):
        styles = pd.DataFrame("", index=data.index, columns=data.columns)
        for i in range(len(data)):
            bg = "#f6f8fa" if i % 2 else "#ffffff"
            styles.iloc[i] = f"background-color: {bg}; color: #1f2328"
        return styles

    return (df.style
            .apply(_alt_rows, axis=None)
            .set_table_styles([
                {"selector": "th", "props": [
                    ("background-color", "#f6f8fa"), ("color", "#1f2328"),
                    ("border", "1px solid #d0d7de"), ("font-weight", "600"),
                ]},
                {"selector": "td", "props": [("border", "1px solid #d0d7de")]},
            ]))


# ── HTML table renderer (replaces st.dataframe for full theme control) ────────

def render_table(df: pd.DataFrame, height: int = None) -> None:
    """
    Render a DataFrame as a fully-themed HTML <table> via st.markdown.

    Replaces st.dataframe() / style_df() so that both dark and light mode
    are 100% controlled by our CSS — no canvas renderer interference.

    Features:
      • Timestamp columns auto-formatted as "FY2024"
      • Values with "%" → green (≥0) / red (<0)
      • Values starting with "+" → green
      • Numeric-looking columns → right-aligned; text → left-aligned
      • Full row/column names, no truncation
      • Optional scrollable container via height parameter
    """
    dark    = st.session_state.get("dark_mode", True)
    bg      = "#161b22" if dark else "#ffffff"
    hdr_bg  = "#1c2128" if dark else "#f6f8fa"
    alt_bg  = "#1c2128" if dark else "#f6f8fa"
    txt     = "#e6edf3" if dark else "#1f2328"
    hdr_txt = "#8b949e" if dark else "#57606a"
    bd      = "#30363d" if dark else "#d0d7de"
    pos_c   = "#3fb950"
    neg_c   = "#f85149"

    def _fmt_col(c) -> str:
        """Format column header: Timestamp-like strings → FY20xx."""
        s = str(c)
        try:
            ts = pd.Timestamp(s)
            if ts.year > 2000:
                return f"FY{ts.year}"
        except Exception:
            pass
        return s

    def _value_color(val) -> str:
        """Return CSS color for a cell value based on sign/% content."""
        s = str(val).strip()
        if s in ("N/A", "—", "", "-", "nan"):
            return txt
        if "%" in s:
            try:
                num = float(
                    s.replace("%", "").replace("+", "").replace(",", "").strip()
                )
                return pos_c if num >= 0 else neg_c
            except ValueError:
                pass
        if s.startswith("+"):
            return pos_c
        if len(s) > 1 and s[0] == "-" and (s[1].isdigit() or s[1] == "$"):
            return neg_c
        return txt

    def _is_right_align(col_vals) -> bool:
        """True if the majority of sample values look numeric."""
        hits = 0
        for v in col_vals[:8]:
            cleaned = (
                str(v)
                .replace("$", "").replace("B", "").replace("M", "").replace("K", "")
                .replace("%", "").replace("+", "").replace("-", "").replace(",", "")
                .replace("x", "").replace(".", "").strip()
            )
            if cleaned.isdigit() and cleaned:
                hits += 1
        return hits >= 2

    col_align = {
        col: ("right" if _is_right_align(df[col].tolist()) else "left")
        for col in df.columns
    }
    # Apply language-aware column name translation
    _lang_tbl = st.session_state.get("language", "en")
    _col_map  = TRANSLATIONS.get(_lang_tbl, TRANSLATIONS["en"]).get("column_names", {})
    col_headers = [_col_map.get(_fmt_col(c), _fmt_col(c)) for c in df.columns]
    idx_name    = str(df.index.name) if df.index.name else ""

    # Wrapper div: optional vertical scroll
    overflow_y = f"max-height:{height}px;overflow-y:auto;" if height else ""
    wrap_s = (
        f'style="width:100%;overflow-x:auto;{overflow_y}'
        f'border-radius:8px;border:1px solid {bd};margin-bottom:8px;"'
    )
    tbl_s = 'style="width:100%;border-collapse:collapse;font-size:0.82rem;"'

    parts = [f'<div {wrap_s}><table {tbl_s}>']

    # ── Header ──
    th_base = (
        f"background:{hdr_bg};color:{hdr_txt};padding:8px 12px;"
        f"border-bottom:2px solid {bd};border-right:1px solid {bd};"
        f"font-weight:600;white-space:nowrap;"
    )
    parts.append("<thead><tr>")
    parts.append(f'<th style="{th_base}text-align:left;">{idx_name}</th>')
    for i, ch in enumerate(col_headers):
        col   = df.columns[i]
        align = col_align[col]
        parts.append(f'<th style="{th_base}text-align:{align};">{ch}</th>')
    parts.append("</tr></thead><tbody>")

    # ── Body ──
    td_base = (
        f"padding:7px 12px;border-bottom:1px solid {bd};"
        f"border-right:1px solid {bd};white-space:nowrap;"
    )
    for i, (idx_val, row) in enumerate(df.iterrows()):
        row_bg = alt_bg if i % 2 else bg
        parts.append(f'<tr style="background:{row_bg};">')
        # Index cell (always left-aligned, subdued color)
        parts.append(
            f'<td style="{td_base}background:{row_bg};color:{hdr_txt};'
            f'font-weight:500;text-align:left;">{str(idx_val)}</td>'
        )
        # Data cells
        for col in df.columns:
            val   = row[col]
            color = _value_color(val)
            align = col_align[col]
            parts.append(
                f'<td style="{td_base}background:{row_bg};color:{color};'
                f'text-align:{align};">{val}</td>'
            )
        parts.append("</tr>")

    parts.append("</tbody></table></div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


# ── Translation ───────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def translate_to_chinese(text: str) -> str:
    """Translate English text to Simplified Chinese. Falls back to original on any error."""
    if not text or not text.strip():
        return text
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source="en", target="zh-CN").translate(text)
    except Exception:
        return text


# ── i18n: TRANSLATIONS + t() ─────────────────────────────────────────────────

TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh": {
        # ── Sidebar ──────────────────────────────────────────────────────────────
        "sidebar_ticker":     "股票代码",
        "sidebar_ticker_ph":  "如：NVDA",
        "sidebar_cache":      "数据缓存",
        "cache_ohlcv":        "行情",
        "cache_financials":   "财务",
        "cache_balance":      "资产负债",
        "cache_cashflow":     "现金流",
        "dark_mode":          "🌙 深色模式",
        "disclaimer":         "⚠️ 仅供研究参考，不构成投资建议",
        # Nav links
        "nav_home":           "🏠 主页",
        # Phase 6C-B: nav_p1 (AI Research Workflow / Overview) is DEPRECATED in the
        # sidebar — the page file is retained and reachable by URL, but it is no
        # longer registered as a nav entry. Key kept for backward compatibility.
        "nav_p1":             "🔭 总览",
        "nav_p2":             "🏭 行业研究",
        "nav_p3":             "🔍 选股扫描",
        "nav_p4":             "🏢 个股研究",
        # Phase 5P: nav_p5 / nav_p6 are legacy source-module labels — Financial
        # Analysis and Price & Volume are now sub-surfaces under Equity Research
        # and are no longer shown as top-level sidebar nav entries. Keys retained
        # for backward compatibility.
        "nav_p5":             "📊 财务分析",
        "nav_p6":             "📉 量价分析",
        "nav_p8":             "🌐 宏观仪表盘",
        "nav_p9":             "📋 交易台",
        "nav_section":        "导航",
        # ── Phase 6C-B: Investment Cockpit rebuild (data aggregation hub) ────────
        "cockpit_hub_title":            "🧭 投研中枢 / Investment Cockpit",
        "cockpit_hub_subtitle":         "实时数据聚合中枢 — 宏观、主题、信号、个股估值一站汇总（仅供研究，不构成投资建议）",
        "cockpit_hub_refresh_btn":      "🔄 一键刷新",
        "cockpit_hub_last_refresh":     "上次刷新",
        "cockpit_hub_never":            "尚未刷新",
        "cockpit_hub_status_header":    "模块数据状态",
        "cockpit_hub_status_fresh":     "本次会话已刷新",
        "cockpit_hub_status_stale":     "未加载 / 过期",
        "cockpit_hub_status_macro":     "宏观",
        "cockpit_hub_status_themes":    "主题",
        "cockpit_hub_status_signals":   "信号",
        "cockpit_hub_status_equity":    "个股估值",
        "cockpit_hub_sec_macro":        "A · 宏观环境",
        "cockpit_hub_macro_not_loaded": "宏观数据未加载",
        "cockpit_hub_macro_regime":     "市场状态",
        "cockpit_hub_macro_bias":       "周期偏好",
        "cockpit_hub_macro_signals":    "关键信号",
        "cockpit_hub_macro_posture":    "机会取向",
        "cockpit_hub_link_macro":       "前往宏观仪表盘 →",
        "cockpit_hub_sec_themes":       "B · 市场主题",
        "cockpit_hub_themes_not_loaded":"主题数据未加载",
        "cockpit_hub_link_sector":      "前往行业研究 →",
        "cockpit_hub_theme_3m":         "3月收益",
        "cockpit_hub_theme_momentum":   "动量评分",
        # Phase 7B — fragility banner + theme stage / breadth (Cockpit)
        "cockpit_hub_internals":        "市场内部结构",
        "cockpit_hub_internals_note":   "内部结构只是“收紧型”预警，不会改变上方的市场状态判定。",
        "cockpit_hub_internals_unavail":"暂不可用",
        "cockpit_frag_dist":            "派发日",
        # B1: 完整句式，避免「5/25」被误读为日期。
        "cockpit_frag_dist_banner":     "25日内派发 {n} 次",
        "cockpit_frag_breadth":         "广度",
        "cockpit_frag_gns":             "利好遭抛",
        "cockpit_frag_gns_unit":        " 例",
        # B2: 已评估样本分母的标签（「1/12 评估」）。
        "cockpit_frag_gns_eval":        "评估",
        # 横幅空间紧凑，用精简的「分子/分母 次」；工作台表内用完整句式。
        "cockpit_frag_gns_banner":      "{num}/{den} 次",
        "cockpit_frag_gns_full":        "{den} 次财报中 {num} 次遭抛售",
        "cockpit_frag_gns_concept":     "利好遭抛 = 利好出尽式抛售 (sell-the-news)：财报利好后次日放量下跌的名单占比。",
        "cockpit_frag_na":              "无数据",
        # Fragility level badge names + one-line tighten-only explainer.
        "cockpit_frag_lvl_normal":      "正常",
        "cockpit_frag_lvl_elevated":    "警戒",
        "cockpit_frag_lvl_high":        "警报",
        "cockpit_frag_lvl_explain":     "正常 = 没有系统性转差信号；警戒 = 同时出现多个转差信号，但只是提醒，不收紧门槛；警报 = 转差信号被广泛确认，仅收紧短线入场门槛（中长线不受影响）。",
        # Phase 7B — Macro Dashboard "Market Internals" workbench block
        "mi_header":                    "市场内部结构（工作台）",
        "mi_not_loaded":                "请先在投资驾驶舱刷新以生成内部结构读数",
        "mi_go_cockpit":                "前往投资驾驶舱 →",
        "mi_level":                     "脆弱度等级",
        # 标签可加简短读注；数值保持原始 token（rolling / snapshot / 日期），不翻译。
        "mi_source":                    "读数来源（rolling 滚动重算 / snapshot 快照）",
        "mi_vintage":                   "数据时点",
        "mi_vintage_mismatch":          "数据时点不一致（已降级为快照）",
        "mi_points":                    "得分",
        "mi_component":                 "信号项",
        "mi_value":                     "读数",
        "mi_triggered":                 "是否触发",
        "mi_degrade":                   "数据说明",
        "mi_c_breadth20":               "20日均线以上占比",
        "mi_c_breadth50":               "50日均线以上占比",
        "mi_c_slope":                   "广度趋势（斜率）",
        "mi_c_weak_bounce":             "弱反弹",
        "mi_c_vol":                     "龙头量能萎缩",
        "mi_c_od":                      "进攻/防御",
        # 是/否 — 把布尔读数渲染为人类可读（弱反弹等行）。
        "mi_yes":                       "是",
        "mi_no":                        "否",
        # 进攻/防御枚举的中文显示（仅显示层翻译，rotation.py 的 token 不变）。
        "mi_od_dir_offense":            "进攻",
        "mi_od_dir_defense":            "防御",
        "mi_od_dir_balanced":           "均衡",
        "mi_od_mag_strong":             "强",
        "mi_od_mag_moderate":           "中等",
        "mi_od_mag_mild":               "轻微",
        # 降级原因的中文读注：原始 token 文本保持不变，仅在括号内补充释义（审计锚点）。
        "mi_dgloss_finnhub_unavailable":    "Finnhub 数据源不可用",
        "mi_dgloss_earnings_source_absent": "无财报数据源",
        "mi_dgloss_no_reports_in_window":   "窗口内无财报",
        "mi_dgloss_partial_frame_coverage": "部分行情未缓存",
        "mi_dgloss_implausible_count":      "计数异常已剔除",
        "mi_note":                      "内部结构只是“收紧型”预警：信号转差时只收紧门槛，绝不放松；仅供研究参考，不构成投资建议。",
        "cockpit_hub_clock_suspect":    "系统时钟疑似异常（快照仍已写入）",
        "cockpit_hub_theme_3m_excess":  "3月超额 (vs QQQ)",
        "cockpit_hub_stage":            "轮动阶段",
        "cockpit_hub_stage_confirmed":  "广度确认",
        "cockpit_hub_stage_unconfirmed":"广度未确认",
        "cockpit_hub_breadth":          "广度",
        "stage_leading":                "领涨",
        "stage_rotating_in":            "资金流入",
        "stage_rotating_out":           "资金流出",
        "stage_out_of_favor":           "失宠",
        "cockpit_hub_sec_signals":      "C · 信号候选",
        "cockpit_hub_signals_total":    "候选总数",
        "cockpit_hub_signals_triple":   "三重",
        "cockpit_hub_signals_double":   "双重",
        "cockpit_hub_signals_single":   "单一",
        "cockpit_hub_signals_none":     "暂无信号候选",
        "cockpit_hub_top_candidates":   "Top 5 候选",
        "cockpit_hub_select_header":    "选择标的进行深度研究",
        "cockpit_hub_select_all":       "全选",
        "cockpit_hub_no_tickers":       "暂无可选标的",
        "cockpit_hub_run_equity":       "🔬 一键运行个股研究",
        "cockpit_hub_equity_running":   "正在运行个股研究…",
        "cockpit_hub_equity_done":      "个股研究完成",
        "cockpit_hub_no_selection":     "请先勾选至少一个标的",
        "cockpit_hub_sec_equity":       "D · 个股研究结果",
        "cockpit_hub_equity_none":      "尚未选择标的或暂无研究结果",
        "cockpit_hub_not_researched":   "未研究",
        "cockpit_hub_view_research":    "查看完整研究",
        "cockpit_hub_go_equity":        "前往个股研究",
        "cockpit_hub_sec_triple":       "E · 三重信号关注",
        "cockpit_hub_triple_none":      "暂无未持仓的三重信号候选",
        "cockpit_hub_add_holdings":     "加入交易台",
        "cockpit_hub_add_td":           "➕ 加入交易台",
        "cockpit_hub_added_td":         "已加入交易台机会看板",
        "cockpit_hub_refresh_running":  "正在刷新…",
        "cockpit_hub_stage_macro":      "① 宏观与状态分类",
        "cockpit_hub_stage_themes":     "② 主题动量",
        "cockpit_hub_stage_signals":    "③ 信号候选生成",
        "cockpit_hub_stage_equity":     "④ 个股估值",
        "cockpit_hub_refresh_complete": "刷新完成",
        "cockpit_hub_safety":           "⚠️ 本页仅供研究 / 审阅，不下达任何订单、不接入券商、不构成投资建议。",
        "cockpit_hub_upside":           "上行空间",
        "cockpit_hub_confidence":       "置信度",
        "cockpit_hub_fair_value":       "合理估值（中值）",
        "cockpit_hub_action":           "建议动作",
        "cockpit_hub_catalyst":         "催化剂",
        # ── Phase 6C-B: Equity page AI Valuation Summary section ────────────────
        "cockpit_fv_header":            "📊 AI估值综合 / AI Valuation Summary",
        "cockpit_fv_range":             "合理估值区间",
        "cockpit_fv_low":               "低",
        "cockpit_fv_mid":               "中值",
        "cockpit_fv_high":              "高",
        "cockpit_fv_upside":            "上行空间（中值 vs 现价）",
        "cockpit_fv_confidence":        "置信度",
        "cockpit_fv_methodology":       "方法说明",
        "cockpit_fv_dcf":               "DCF 估值",
        "cockpit_fv_relative":          "相对估值（行业P/E）",
        "cockpit_fv_analyst":           "分析师目标价",
        "cockpit_fv_run_debate":        "🤖 运行 AI 多空辩论",
        "cockpit_fv_send_desk":         "📤 发送至交易台",
        "cockpit_fv_sent":              "已发送至交易台 — 订单建议将优先使用应用计算的合理估值。",
        "cockpit_fv_debate_running":    "正在运行 AI 多空辩论…",
        "cockpit_fv_bull":              "多方观点",
        "cockpit_fv_bear":              "空方观点",
        "cockpit_fv_risk":              "风险因素",
        "cockpit_fv_synthesis":         "综合结论",
        "cockpit_fv_endorsed":          "辩论认可区间",
        "cockpit_fv_action":            "建议动作",
        "cockpit_fv_na":                "估值数据不足。",
        # ── Anchor consistency gate (Valuation stop-the-bleed) ──────────────────
        "cockpit_fv_irreconcilable":    "⚠️ 估值锚不一致",
        "cockpit_fv_irreconcilable_note": "各估值方法分歧过大，已停止融合区间——分别列示，请人工判断。",
        "cockpit_fv_basis":             "基准",
        "cockpit_fv_basis_forward":     "前瞻 EPS",
        "cockpit_fv_basis_trailing":    "滚动 EPS（回退）",
        "cockpit_fv_basis_mixed":       "⚠️ 混合基准：前瞻EPS × 滚动同业P/E",
        # --- Method router (Valuation Refactor v1) ---
        "cockpit_fv_company_type":      "公司类型",
        "cockpit_fv_methods_used":      "采用方法",
        "cockpit_fv_excluded":          "已排除锚（不参与融合）",
        "cockpit_fv_peer_basis":        "同业基准",
        "cockpit_fv_routing":           "路由依据",
        "cockpit_fv_borderline":        "边界情形——采用默认方法",
        "cockpit_fv_flag_excluded":     "已排除",
        "cockpit_fv_flag_cycle_distorted": "周期扭曲",
        "cockpit_fv_type_mature_profitable":   "成熟盈利",
        "cockpit_fv_type_growth_profitable":   "高增长盈利",
        "cockpit_fv_type_growth_unprofitable": "高增长未盈利",
        "cockpit_fv_type_project_driven":      "项目驱动",
        "cockpit_fv_type_cyclical":            "周期型",
        "cockpit_fv_peer_growth_matched":      "成长匹配同业",
        "cockpit_fv_peer_sector_fallback":     "行业回退",
        "cockpit_fv_caveats":           "注意事项",
        "cockpit_fv_caveat_cyclical_band_unavailable": "周期历史区间不可用——退化为仅分析师锚（≤4年年度数据不足）",
        "cockpit_fv_caveat_single_anchor_blend":       "仅单一锚参与融合",
        "cockpit_fv_caveat_implausible_forward_eps":   "前瞻EPS异常（远高于滚动EPS）——已剔除相对估值锚",
        "cockpit_fv_caveat_anchor_implausible_vs_price": "某估值锚相对现价明显失真——已剔除该锚",
        "cockpit_fv_caveat_implausible_growth_input":  "营收增速数据异常——分类与同业匹配按缺失处理",
        "cockpit_fv_caveat_analyst_pool_dispersed":    "分析师目标区间过于离散——置信度已下调至「低」（中位数仍纳入融合）",
        "cockpit_fv_analyst_pool":     "分析师目标区间",
        "cockpit_fv_computed_at":      "估值计算时间",
        "cockpit_fv_running":           "正在计算估值…",
        "cockpit_fv_update":            "🔄 更新估值",
        "cockpit_fv_update_hint":       "请先在财务分析页面运行 DCF",
        "cockpit_fv_updated":           "估值已更新（使用财务分析页的 DCF 参数）",
        "cockpit_fv_enter_ticker":      "请输入 ticker 以加载",
        "p4_loading":                   "加载中...",
        "cockpit_fv_fcf_unavailable":   "现金流数据不可用",
        "p6_data_unavailable":          "数据不可用",
        "cockpit_fv_debate_failed":     "AI 辩论未运行",
        # ── Anchor Intel v2.4: valuation diagnosis card ─────────────────────────
        "valdiag_header":               "🔬 估值诊断",
        "valdiag_role":                 "估值定位",
        "valdiag_role_informational":   "仅供参考",
        "valdiag_role_mid_term_supportive": "支持中线",
        "valdiag_role_long_term_eligible":  "可作长线依据",
        "valdiag_consistency":          "锚一致性",
        "valdiag_consistency_consistent":     "多锚一致",
        "valdiag_consistency_single_anchor":  "仅单一锚",
        "valdiag_consistency_irreconcilable": "锚不可调和",
        "valdiag_consistency_no_anchor":      "无有效锚",
        "valdiag_outlier":              "离群锚",
        "valdiag_no_clear_outlier":     "无明确离群锚",
        "valdiag_clustered":            "聚合锚",
        "valdiag_peer_match":           "对标质量",
        "valdiag_peer_match_high":      "可比对标充分",
        "valdiag_peer_match_low":       "可比对标不足 — 已排除对标倍数锚",
        "valdiag_reason_insufficient_comparable_peers": "可比对标不足",
        "valdiag_endorsed_range":       "认可区间",
        "valdiag_range_irreconcilable": "区间暂不给出（各锚分歧过大，分别列示）",
        "valdiag_range_unavailable":    "区间不可用",
        "valdiag_applicable_methods":   "适用方法",
        "valdiag_rejected_methods":     "已排除方法",
        "valdiag_reason_dcf_unavailable": "DCF 不可用",
        "valdiag_reason_excluded_anchor": "已排除",
        "valdiag_what_would_change":    "什么会改变这一结论",
        "valdiag_cond_price_above_endorsed_range": "价格升破认可区间上沿",
        "valdiag_cond_price_below_endorsed_range": "价格跌破认可区间下沿",
        "valdiag_cond_analyst_pool_migration_deteriorating": "分析师锚池系统性下移",
        "valdiag_cond_met":             "已触发",
        "valdiag_cond_armed":           "未触发",
        "valdiag_narrative_pending":    "叙事型催化（利润率指引等）将于 Phase 8 接入",
        "valdiag_reverse_dcf_pending":  "反向 DCF：Phase 8 待接入",
        # ── Phase 6C-B: Trading Desk fair-value source badge ────────────────────
        "td_fair_value_source":         "估值来源",
        "td_fv_src_app":                "应用计算",
        "td_fv_src_app_fair_value":     "应用估值",
        "td_fv_src_fixture":            "占位数据",
        # ── Phase 6C-A: Trading Desk ─────────────────────────────────────────────
        "td_page_title":      "交易台",
        "td_page_subtitle":   "投资工作流的执行层：持仓监控、订单建议、机会看板。仅供研究参考，不构成投资建议，不下单、不接入券商。",
        "td_safety_banner":   "仅供参考，不构成投资建议。所有订单需手动在券商执行；本页面不下单、不接入券商。",
        # Section 1 — Holdings Monitor
        "td_sec1_header":     "持仓监控",
        "td_add_position":    "添加持仓",
        "td_no_holdings":     "暂无活跃持仓。点击“添加持仓”开始追踪你的投资论点。",
        "td_refresh":         "刷新论点监控",
        "td_monitor_running": "正在运行论点监控…",
        "td_last_refresh":    "上次刷新",
        "td_horizon":         "周期",
        "td_horizon_short":   "短线",
        "td_horizon_mid":     "中线",
        "td_horizon_long":    "长线",
        "td_status_intact":   "论点完好",
        "td_status_watch":    "需观察",
        "td_status_weakening":"论点走弱",
        "td_status_broken":   "论点破坏",
        "td_pnl":             "盈亏",
        "td_normal_pullback": "📉 正常回调，非thesis破坏",
        "td_edit":            "编辑",
        "td_save":            "保存",
        "td_close_position":  "平仓",
        "td_closed_price":    "平仓价",
        "td_shares":          "股数",
        "td_cost_basis":      "成本价（每股）",
        "td_entry_date":      "买入日期",
        "td_thesis_text":     "投资论点",
        "td_notes":           "备注",
        "td_thesis_source":   "论点来源",
        "td_thesis_signals":  "关联信号",
        "td_import_thesis":   "从信号导入论点",
        "td_import_none":     "不导入（手动输入）",
        "td_ticker":          "代码",
        "td_add_btn":         "添加",
        "td_position_closed": "已平仓",
        "td_key_development":  "关键进展",
        "td_tech_warning":     "技术破坏信号",
        "td_macro_note":       "宏观信号",
        "td_cancel":           "取消",
        "td_filter_all":       "全部",
        "td_filter_status":    "Thesis状态",
        "td_filter_horizon":   "周期",
        "td_col_price":        "现价",
        "td_col_status":       "状态",
        "td_col_alert":        "预警",
        "td_col_action":       "操作",
        "td_no_match":         "没有符合筛选条件的持仓。",
        "td_cash_position_label": "现金仓位",
        "td_total_assets":     "总资产",
        "td_holdings_value":   "持仓市值",
        "td_cash_ratio":       "现金占比",
        "td_avg_cost":         "均价",
        "td_market_value":     "总市值",
        "td_position_pct":     "仓位占比",
        "td_close_confirm_title": "确认平仓",
        "td_close_shares":     "平仓股数",
        "td_close_proceeds":   "预计成交金额",
        "td_close_add_cash_q": "是否将 {amt} 加入现金仓位？",
        "td_close_add_cash":   "加入现金仓位",
        "td_yes":              "是",
        "td_no":               "否",
        "td_confirm":          "确认",
        # Section 2 — Order Recommendations
        "td_sec2_header":     "订单建议",
        "td_sec2_subheader":  "仅供参考，不构成投资建议。所有订单需手动在券商执行。",
        "td_entry_zone":      "入场区间",
        "td_stop_loss":       "止损",
        "td_target":          "目标价",
        "td_rr_ratio":        "风险回报比",
        "td_position_size":   "建议仓位",
        "td_action_add":      "加仓",
        "td_action_hold":     "持有",
        "td_action_trim":     "减仓",
        "td_action_exit":     "退出",
        "td_action_wait":     "等待",
        "td_details":         "详情",
        "td_support":         "支撑位",
        "td_resistance":      "压力位",
        "td_volume_trend":    "成交量趋势",
        "td_atr":             "ATR(14)",
        "td_candlestick":     "K线形态",
        "td_kelly_note":      "Kelly-lite 仓位假设：胜率 0.55、半 Kelly、限制 2%–10%。",
        "td_broken_section":  "论点破坏的持仓（仅建议退出）",
        "td_risk_warning":    "风险提示",
        "td_vol_increasing":  "放量",
        "td_vol_decreasing":  "缩量",
        "td_vol_neutral":     "中性",
        "td_data_live":       "实时",
        "td_data_fixture":    "示例",
        # Section 3 — Opportunity Watch
        "td_sec3_header":     "机会看板",
        "td_sec3_empty":      "暂无三重信号机会。请前往“选股扫描”页运行扫描以填充此处。",
        "td_add_to_holdings": "加入持仓",
        "td_catalyst":        "催化剂",
        "td_opp_in_zone":     "✅ 当前处于入场区间",
        "td_opp_above_zone":  "⏳ 等待回调",
        "td_opp_blocked":     "⛔ 条件未满足",
        "td_opp_below_zone":  "⚠️ 价格偏低，等待企稳",
        # Phase 7A — unified five-state opportunity status (Cockpit + Trading Desk)
        "opp_status_actionable": "✅ 可立即操作",
        "opp_status_pullback":   "⏳ 等待回调",
        "opp_status_breakout":   "🚀 等待突破",
        "opp_status_research":   "🔍 需进一步研究",
        "opp_status_avoid":      "⛔ 避免追高",
        "opp_status_pending":    "（刷新后评估）",
        # Phase 7A — Opportunity Card panel
        "opp_panel_header":   "C · 机会清单",
        "opp_panel_caption":  "按时间维度排序的研究队列（“值得花 10 分钟关注”），仅供研究，非买入清单。",
        "opp_horizon_label":  "时间维度",
        "opp_horizon_short":  "短线",
        "opp_horizon_mid":    "中线",
        "opp_horizon_long":   "长线",
        "opp_grade":          "评级",
        "opp_setup":          "形态",
        "opp_why_now":        "为何现在",
        "opp_why_matters":    "为何重要",
        "opp_blockers":       "阻碍因素",
        "opp_days_to_earnings": "距财报",
        "opp_days":           "天",
        "opp_concentration_prefix": "同主题押注，参见 ",
        "opp_pullback_support": "回踩支撑（高质量）",
        "opp_none":           "暂无机会候选 — 请先点击“刷新全部”。",
        "opp_banner_header":  "市场环境（适用于全部候选）",
        "opp_next_trigger":   "等待",
        "opp_rs_degraded":    "相对强度数据暂缺（按中性计）",
        "opp_rs_stale":       "相对强度数据时点滞后（疑似陈旧缓存）",
        # Phase 7A — setup type labels
        "opp_setup_momentum_breakout": "动能突破",
        "opp_setup_mid_rotation":      "中线轮动",
        "opp_setup_oversold_rebound":  "超卖反弹",
        "opp_setup_post_earnings":     "财报后重估",
        "opp_setup_long_accum":        "长线积累",
        "opp_setup_speculative":       "投机观察",
        "td_actionable_header": "可执行信号",
        "td_signal_from_scanner": "此信号来自选股扫描",
        # Entry Strategy v3 — scenario / action / fields
        "td_scenario_initiate": "建仓",
        "td_scenario_add":      "加仓",
        "td_scenario_manage":   "管理",
        "td_missing_conditions": "待满足条件",
        "td_next_trigger":      "下一触发条件",
        "td_risk_note":         "风险说明",
        "td_fair_value_anchor": "合理价值锚",
        "td_act_wait":              "等待",
        "td_act_hold":              "持有",
        "td_act_enter_partial_now": "立即建立部分仓位",
        "td_act_enter_on_pullback": "回调建仓",
        "td_act_enter_or_add_small": "小仓建仓/加仓",
        "td_act_add_small":         "小幅加仓",
        "td_act_add_partial":       "部分加仓",
        "td_act_add_tiny":          "极小幅加仓",
        "td_act_average_down_small": "小幅向下加仓",
        "td_act_average_down":      "向下加仓",
        "td_act_wait_for_pullback": "等待回调",
        "td_act_wait_or_cut":       "等待或止损",
        "td_act_reduce":            "减仓",
        "td_act_reduce_or_exit":    "减仓或退出",
        "td_act_cut_loss":          "止损",
        "td_act_exit":              "退出",
        "td_act_trim_or_stop_adding": "减仓/停止加仓",
        "td_act_avoid":             "回避",
        # Entry Strategy v4 — portfolio settings + valuation confidence + risk overlay
        "td_portfolio_settings": "组合设置",
        "td_max_position_pct":   "单一持仓上限",
        "td_short_max_loss":     "短线单笔最大亏损",
        "td_mid_max_loss":       "中线单笔最大亏损",
        "td_long_stop_label":    "长线止损",
        "td_long_stop_value":    "仅逻辑破坏",
        "td_save_settings":      "保存设置",
        "td_settings_saved":     "设置已保存",
        "td_valuation_confidence": "估值置信度",
        "td_conf_high":          "高置信度",
        "td_conf_medium":        "中置信度",
        "td_conf_low":           "低置信度",
        "td_risk_overlay_note":  "风险叠加提示",
        "td_weight_after_add":   "加仓后仓位",
        "td_blended_cost":       "加仓后均价",
        # ── App home ─────────────────────────────────────────────────────────────
        "app_title":          "美股投资研究系统",
        "app_subtitle":       "NYSE & NASDAQ | Powered by yfinance + polygon.io",
        "mktcap":             "市值",
        "quick_nav":          "快速导航",
        "nav_overview":       "🔭 总览分析",
        "nav_financial":      "📊 财务分析",
        "nav_pricevolume":    "📉 量价分析",
        "modules_title":      "分析模块",
        "mod_overview_title": "总览",
        "mod_overview_desc":  "一键运行完整研究流程，汇总各模块结论",
        "mod_sector_title":   "行业研究",
        "mod_sector_desc":    "ETF走势 + 自定义标的横向对比",
        "mod_scanner_title":  "选股扫描",
        "mod_scanner_desc":   "自定义股票池动量 / 价值筛选",
        "mod_equity_title":   "个股研究",
        "mod_equity_desc":    "商业模式、护城河、竞争格局深度分析",
        "mod_fin_title":      "财务分析",
        "mod_fin_desc":       "三张表、DCF估值、同业对比",
        "mod_pv_title":       "量价分析",
        "mod_pv_desc":        "K线图、技术指标、盘前盘后行情",
        "input_prompt":       "👈 请在左侧输入股票代码（如 NVDA、AAPL、MSFT）开始分析",
        "data_source":        "数据来源：yfinance（主）/ polygon.io（备） | 所有内容仅供研究参考，不构成投资建议",
        "loading_failed":     "数据加载失败，请检查股票代码是否正确。",
        # ── Common ───────────────────────────────────────────────────────────────
        "no_ticker":          "请在左侧输入股票代码（如 NVDA、AAPL、MSFT）开始分析",
        "employees":          "员工",
        "download_report":    "⬇ 下载报告",
        "mkt_cap":            "市值",
        "gross_margin":       "毛利率",
        "revenue":            "营收",
        "net_income":         "净利润",
        "free_cash_flow":     "自由现金流",
        "above_sma200":       "SMA200上方",
        "from_52w_high":      "距52W高",
        "vol_ratio_lbl":      "量比(20D)",
        "analyst_rtg":        "分析师评级",
        "moat_rating":        "护城河评级",
        "target_price":       "目标价均值",
        # ── News ─────────────────────────────────────────────────────────────────
        "news_summary":       "摘要",
        # ── Page 1 ───────────────────────────────────────────────────────────────
        "p1_title":           "🔭 总览 — 完整研究流程",
        "p1_select_mods":     "选择要运行的分析模块",
        "p1_mod_financial":   "📊 财务分析",
        "p1_mod_technical":   "📉 量价分析",
        "p1_mod_equity":      "🏢 个股研究",
        "p1_mod_earnings":    "📅 财报日历",
        "p1_run_all":         "▶ 一键运行完整研究",
        "p1_click_run":       "点击「▶ 一键运行完整研究」开始分析",
        "p1_metrics":         "关键指标一览",
        "p1_fin_snap":        "财务快照（TTM）",
        "p1_tech_snap":       "技术面快照",
        "p1_equity_sum":      "个股研究摘要",
        "p1_radar":           "📡 综合雷达图",
        "p1_report":          "综合报告",
        "p1_overall":         "综合评分",
        "p1_hover_hint":      "鼠标悬停图表各顶点查看评分依据",
        "p1_d_sector":        "行业景气",
        "p1_d_health":        "财务健康",
        "p1_d_valuation":     "估值吸引力",
        "p1_d_technical":     "技术面",
        "p1_d_business":      "商业模式",
        "p1_score_dim":       "维度",
        "p1_score_val":       "分值",
        "p1_score_note":      "说明",
        # ── Page 2 ───────────────────────────────────────────────────────────────
        "p2_title":           "🏭 板块研究",
        "p2_subtitle":        "GICS 板块轮动分析 · 主题 ETF 子板块 · 板块内选股",
        "p2_etf":             "选择行业 ETF",
        "p2_period":          "时间周期",
        "p2_peers":           "自定义对比标的",
        "p2_peers_input":     "输入要对比的股票（逗号分隔），默认为该行业代表性标的",
        "p2_perf":            "表现汇总",
        "p2_dl_csv":          "⬇ 下载表格 CSV",
        "p2_price_usd":       "价格 (USD)",
        "p2_volume":          "成交量",
        "p2_norm_return":          "📊 归一化收益率（基准 = 100）",
        "p2_insufficient":         "有效标的不足，请检查 Ticker 是否正确",
        # ── Page 2 v4: rotation ───────────────────────────────────────────────────
        "p2_heatmap":              "📊 板块热力图",
        "p2_heatmap_subtitle":     "综合评分基于超额收益、RSI、距52周高点、成交量；分值越高动量越强",
        "p2_loading_scores":       "计算板块评分中...",
        "p2_select_sector":        "选择板块",
        "p2_rotation_signal":      "🔄 轮动信号",
        "p2_od_panel":             "⚔️ 进攻/防御读数（多窗口）",
        "p2_od_reading":           "读数",
        "p2_od_offense":           "进攻",
        "p2_od_defense":           "防御",
        "p2_od_balanced":          "均衡",
        "p2_od_diff":              "差值",
        "p2_od_window":            "窗口",
        "p2_od_windows_confirm":   "窗口确认",
        "p2_od_unavailable":       "进攻/防御数据暂不可用",
        "p2_od_note":              "进攻篮子相对防御篮子（对SPY超额，单位pp）；仅供研究参考。",
        "p2_market_style":         "市场风格",
        "p2_phase_risk_on":        "进攻 Risk-On",
        "p2_phase_risk_off":       "防御 Risk-Off",
        "p2_phase_neutral":        "中性 Neutral",
        "p2_top3":                 "最强板块 Top 3",
        "p2_accelerating":         "动量加速板块",
        "p2_etf_trend":            "ETF 走势对比",
        "p2_stock_ranking":        "板块内股票分层",
        "p2_loading_stocks":       "加载成分股...",
        "p2_ranking_stocks":       "计算股票排名...",
        "p2_no_constituents":      "S&P 500 成分股数据暂时无法获取。可尝试在下方选择子板块，或检查网络连接。",
        "p2_constituents_found":   "只成分股",
        "p2_ranking_top30":        "展示市值前30名评级",
        "p2_rank_failed":          "排名计算失败，请重试",
        "p2_leader":               "龙头",
        "p2_challenger":           "次龙头",
        "p2_sleeper":              "潜力股",
        "p2_send_scanner":         "发送至选股扫描",
        "p2_subsector_drill":       "📑 子板块",
        "p2_no_subsectors":         "当前板块暂无主题子板块",
        "p2_select_subsector":      "选择子板块",
        "p2_custom_pool":           "自定义股票池",
        "p2_subsector_comparison":  "子板块对比",
        # ── Page 2 — Macro / Volume / Valuation ──────────────────────────────────
        "p2_macro_title":     "宏观环境",
        "p2_macro_vix":       "恐慌指数 VIX",
        "p2_macro_tnx":       "10Y 美债收益率",
        "p2_macro_dxy":       "美元指数 DXY",
        "p2_macro_spx":       "标普500",
        "p2_macro_5d":        "5日变化",
        "p2_macro_vix_fear":  "⚠️ 市场恐慌，偏防御",
        "p2_macro_vix_calm":  "✅ 市场平稳，可进攻",
        "p2_macro_vix_mid":   "市场情绪中性",
        "p2_macro_tnx_up":    "📈 利率上行，不利成长股",
        "p2_macro_tnx_down":  "📉 利率下行，有利成长股",
        "p2_macro_tnx_flat":  "利率稳定",
        "p2_macro_dxy_up":    "💵 美元走强，不利大宗商品",
        "p2_macro_dxy_down":  "💵 美元走弱，有利能源原材料",
        "p2_macro_dxy_flat":  "美元稳定",
        "p2_vol_flow":          "资金流入信号",
        "p2_vol_ratio":         "量比",
        "p2_vol_breakout":      "近期量比突破 1.5x",
        "p2_vol_unavail":       "成交量数据暂不可用",
        "p2_vol_legend_active": "活跃板块",
        "p2_vol_legend_others": "其他（点击显示）",
        "p2_vol_click_hint":    "量比最高的前3个板块已高亮，点击图例可显示/隐藏其他板块。",
        "p2_valuation":       "板块估值对比（Fwd P/E 中位数）",
        "p2_val_loading":     "计算板块估值中...",
        "p2_val_unavail":     "估值数据暂不可用",
        # ── Page 3 ───────────────────────────────────────────────────────────────
        "p3_title":           "🔍 选股扫描",
        "p3_subtitle":        "在自定义股票池中按策略筛选候选标的",
        "p3_pool":            "自定义股票池",
        "p3_pool_input":      "输入 Ticker（逗号或换行分隔）",
        "p3_pool_help":       "默认为标普500科技股前20。可替换为任意美股 ticker。",
        "p3_strategy":        "筛选策略",
        "p3_strat_lbl":       "策略",
        "p3_period":          "数据周期",
        "p3_top_n":           "最多展示 Top N",
        "p3_run":             "▶ 运行扫描",
        "p3_hits":            "命中标的数",
        "p3_avg3m":           "平均3M收益",
        "p3_avg_rsi":         "平均RSI",
        "p3_dl_csv":          "⬇ 下载结果 CSV",
        "p3_dl_md":           "⬇ 下载报告 MD",
        "p3_no_result":       "未找到符合条件的标的，尝试调整策略或股票池",
        "p3_start_hint":      "配置好参数后点击「▶ 运行扫描」开始",
        # ── Page 4 ───────────────────────────────────────────────────────────────
        "p4_title":           "🏢 个股研究",
        "p4_moat":            "🏰 护城河评估",
        "p4_moat_hint":       "根据财务指标自动估算，可手动调整",
        "p4_moat_rating":     "护城河综合评级",
        "p4_peers":           "📊 同业对比",
        "p4_peer_input":      "同业标的（逗号分隔）",
        "p4_peer_metric":     "对比指标",
        "p4_loading_peers":   "加载同业数据...",
        "p4_biz":             "📖 公司业务描述",
        "p4_news":            "📰 近期新闻与市场情绪",
        "p4_loading_news":    "加载新闻数据...",
        "p4_news_count":      "新闻数量",
        "p4_news_avg":        "情绪均值",
        "p4_news_dist":       "情绪分布",
        "p4_filter":          "筛选新闻",
        "p4_all":             "全部",
        "p4_pos":             "正面",
        "p4_neu":             "中性",
        "p4_neg":             "负面",
        "p4_sent_pos":        "正面 🟢",
        "p4_sent_neg":        "负面 🔴",
        "p4_sent_neu":        "中性 ⚪",
        "p4_no_news_cat":     "该情绪分类下暂无新闻",
        "p4_last7d":          "过去 7 天",
        "p4_report":          "📄 研究报告",
        "p4_view_md":         "查看完整报告 Markdown",
        # ── Page 5 ───────────────────────────────────────────────────────────────
        "p5_title":           "📊 财务分析",
        "p5_tab1":            "📋 三张表",
        "p5_tab2":            "📐 估值分析",
        "p5_tab3":            "🔍 财务质量",
        "p5_is":              "损益表",
        "p5_bs":              "资产负债表",
        "p5_cf":              "现金流量表",
        "p5_is_full":         "损益表 (Income Statement)",
        "p5_bs_full":         "资产负债表 (Balance Sheet)",
        "p5_cf_full":         "现金流量表 (Cash Flow Statement)",
        "p5_trend_metric":    "趋势图指标",
        "p5_margin_trend":    "利润率趋势",
        "p5_liq_ratio":       "流动性比率",
        "p5_cap_struct":      "资本结构（十亿美元）",
        "p5_dcf":             "DCF 情景分析",
        "p5_dcf_adj":         "调整 DCF 参数",
        "p5_fcf_b":           "基准 FCF (B USD)",
        "p5_calc_dcf":        "计算 DCF",
        "p5_rel_val":         "相对估值对比",
        "p5_peer_val":        "同业 Ticker（逗号分隔）",
        "p5_mult":            "估值倍数",
        "p5_quality":         "FCF vs 净利润（盈利质量检验）",
        "p5_checklist":       "财务质量检查清单",
        "p5_qual_title":      "净利润 vs 经营现金流 vs 自由现金流（十亿美元）",
        "p5_qual_ni":         "净利润",
        "p5_qual_ocf":        "经营现金流",
        "p5_qual_fcf":        "自由现金流",
        "p5_qual_caption":    "若经营现金流持续低于净利润，盈利质量可能存疑。",
        "p5_chk_rev":         "营收增长",
        "p5_chk_rev_note":    "% 同比",
        "p5_chk_gm":          "毛利率",
        "p5_chk_ocf":         "经营现金流 > 净利润",
        "p5_chk_ocf_note":    "经营CF {ocf}B vs 净利润 {ni}B",
        "p5_chk_gw":          "商誉/总资产",
        "p5_chk_gw_risk":     "（商誉减值风险）",
        "p5_no_data":         "数据不足，无法生成质量检查清单",
        "p5_loading":         "加载同业估值...",
        # ── Page 6 ───────────────────────────────────────────────────────────────
        "p6_title":           "📉 量价分析",
        "p6_period":          "时间周期",
        "p6_indicator":       "副图指标",
        "p6_pre":             "盘前",
        "p6_post":            "盘后",
        "p6_key_levels":      "关键价格水平",
        "p6_sma20_sup":       "SMA20 支撑",
        "p6_sma50_sup":       "SMA50 支撑",
        "p6_stop":            "止损参考(2xATR)",
        "p6_rr":              "风险回报比",
        "p6_rr_low":          "偏低",
        "p6_rr_ok":           "合理",
        # ── Page 6 indicator options ──────────────────────────────────────────────
        "p6_ind_bb":          "布林带",
        # ── Scanner strategies ────────────────────────────────────────────────────
        "p3_strat_momentum":  "动量",
        "p3_strat_value":     "价值",
        "p3_strat_quality":   "高质量成长",
        "p3_strat_oversold":  "超卖反弹",
        # ── Scanner column headers ────────────────────────────────────────────────
        "p3_col_company":     "公司",
        "p3_col_sector":      "行业",
        "p3_col_price":       "价格($)",
        "p3_col_ret1m":       "1M收益%",
        "p3_col_ret3m":       "3M收益%",
        "p3_col_ret6m":       "6M收益%",
        "p3_col_volratio":    "量比(20D)",
        "p3_col_annvol":      "年化波动%",
        "p3_col_mktcap":      "市值(B)",
        # ── Moat slider labels ────────────────────────────────────────────────────
        "moat_intangibles":   "无形资产(品牌/专利)",
        "moat_switching":     "转换成本",
        "moat_network":       "网络效应",
        "moat_cost_adv":      "成本优势",
        "moat_eff_scale":     "高效规模",
        "moat_wide":          "宽",
        "moat_narrow":        "窄",
        "moat_none":          "无/极窄",
        # ── Peer comparison metrics ───────────────────────────────────────────────
        "p4_peer_gm":         "毛利率%",
        "p4_peer_op":         "营业利润率%",
        # ── News sentiment chart titles ───────────────────────────────────────────
        "p4_chart_hourly":    "近期情绪趋势（按小时）",
        "p4_chart_daily":     "近7天日均情绪趋势",
        "p4_no_finnhub":      "💡 配置 `FINNHUB_API_KEY` 环境变量后可显示新闻情绪分析。\n\n免费注册：https://finnhub.io/register",
        "p4_no_news":         "过去7天暂无新闻数据",
        # ── Overview quality labels ───────────────────────────────────────────────
        "p1_qual_excel":      "优质",
        "p1_qual_neutral":    "中性",
        "p1_qual_caution":    "注意风险",
        # ── Earnings banner labels ────────────────────────────────────────────────
        "earn_window_lbl":    "财报窗口期",
        "earn_next_lbl":      "下次财报",
        "earn_day_out":       "天后",
        "earn_day_ago":       "天前",
        "earn_eps_est":       "EPS预期",
        "earn_last_surp":     "上次EPS惊喜",
        "earn_just_rel":      "🗓️ 财报刚发布",
        "p1_rpt_gen_err":     "报告生成遇到问题",
        # ── Financial metric names (for dropdowns & column headers) ───────────────
        "fin_total_revenue":  "营业收入",
        "fin_gross_profit":   "毛利润",
        "fin_op_income":      "营业利润",
        "fin_net_income":     "净利润",
        "fin_basic_eps":      "基本EPS",
        "fin_diluted_eps":    "摊薄EPS",
        # ── Workflow status bar ───────────────────────────────────────────────────
        "wf_status_running":    "工作流进行中",
        "wf_status_done":       "工作流已完成",
        "wf_sector_lbl":        "板块",
        "wf_ticker_lbl":        "标的",
        "wf_fork_btn":          "从这里 Fork",
        "wf_back_btn":          "↩ 返回总览",
        "wf_forked":            "已 Fork",
        # ── Overview workflow control center ──────────────────────────────────────
        "p1_wf_sector_lbl":  "目标板块",
        "p1_wf_ticker_lbl":  "目标标的",
        "p1_wf_start":       "▶ 启动完整工作流",
        "p1_wf_new":         "🔄 重新开始",
        "p1_wf_done":        "✅ 工作流已完成",
        "p1_wf_running":     "工作流进行中",
        "p1_wf_idle_hint":   "选择板块与标的，启动完整研究工作流",
        "p1_step1_name":     "① 板块研究",
        "p1_step2_name":     "② 选股扫描",
        "p1_step3_name":     "③ 个股研究",
        "p1_step4_name":     "④ 财务分析",
        "p1_step5_name":     "⑤ 量价分析",
        "p1_view_sector":    "查看板块详情 →",
        "p1_view_scanner":   "查看扫描结果 →",
        "p1_view_equity":    "查看个股研究 →",
        "p1_step_pending":   "待执行",
        "p1_step_running":   "执行中...",
        "p1_step_done":      "完成",
        "p1_step_failed":    "失败",
        "p1_no_ticker_wf":   "请输入目标标的代码",
        # ── Equity page tabs ──────────────────────────────────────────────────────
        "p4_tab_overview":      "个股概览",
        "p4_tab_financial":     "财务分析",
        "p4_tab_pv":            "量价分析",
        "p4_tab_news":          "新闻情绪",
        # ── Redirect pages ────────────────────────────────────────────────────────
        "redirect_financial":   "财务分析已合并至 **个股研究** 页面。",
        "redirect_pv":          "量价分析已合并至 **个股研究** 页面。",
        "redirect_goto":        "前往个股研究 →",
        # ── Column name translation map (EN→ZH, applied by render_table) ─────────
        "column_names": {
            # General
            "Company": "公司", "Sector": "行业", "Price($)": "价格($)",
            "Mkt Cap": "市值", "Metric": "指标", "Value": "数值",
            "Dimension": "维度", "Score": "评分", "Notes": "说明",
            # Financial statements
            "Total Revenue": "营业收入", "Gross Profit": "毛利润",
            "Operating Income": "营业利润", "Net Income": "净利润",
            "Basic EPS": "基本EPS", "Diluted EPS": "摊薄EPS",
            "Total Assets": "总资产", "Stockholders Equity": "股东权益",
            "Total Liabilities Net Minority Interest": "总负债",
            "Total Debt": "总债务", "Cash And Cash Equivalents": "现金及等价物",
            "Goodwill": "商誉", "Total Current Assets": "流动资产",
            "Total Current Liabilities": "流动负债",
            "Operating Cash Flow": "经营现金流", "Capital Expenditure": "资本支出",
            "Free Cash Flow": "自由现金流",
            "Repurchase Of Capital Stock": "股票回购", "Cash Dividends Paid": "股息支付",
            # Quality check
            "Revenue Growth": "营收增长", "Gross Margin": "毛利率",
            "Operating CF > Net Income": "经营现金流>净利润",
            "Goodwill/Total Assets": "商誉/总资产",
            # Peer / scanner
            "1M Ret%": "1M回报%", "3M Ret%": "3M回报%", "6M Ret%": "6M回报%",
            "Vol Ratio(20D)": "量比(20D)", "Ann. Vol%": "年化波动%",
            "Fwd P/E": "远期P/E", "Mkt Cap(B)": "市值(B)",
            "52W High%": "距52周高%",
        },
        # ── Phase 5H.1: Investment Cockpit ───────────────────────────────────────
        "nav_p7":                          "🧭 投研中枢",
        "cockpit_page_title":              "投研中枢 — v0.2 演示预览（机会优先）",
        "cockpit_page_subtitle":           "投研中枢叠加层的机会优先 v0.2 演示/示例预览。仅供查看；无实时接入、无外部 API、无下单。",
        "cockpit_scenario_select_label":   "场景（演示/示例）",
        "cockpit_scenario_select_help":    "选择要预览的 Phase 5G 示例场景。'complete' = FIXTKR（数据齐全）；'degraded' = FIXDEG（缺失财务步骤 + 缺失长期论点 + no_trade 期权叠加）。",
        "cockpit_sidebar_pack_id":         "Pack ID：",
        "cockpit_sidebar_scenario_id":     "Scenario ID：",
        "cockpit_sidebar_data_source":     "数据来源：仅 Phase 5G 演示/示例数据包，无任何实时接入。",
        # Safety banner
        "cockpit_safety_headline":         "投研中枢预览 — 仅为演示/示例数据，不构成投资建议。",
        "cockpit_safety_b1":               "Fixture/demo only — 演示/示例数据，无实时工作流接入。",
        "cockpit_safety_b2":               "未调用任何外部 API、LLM、券商或下单路由（No external API）。",
        "cockpit_safety_b3":               "不读取 research/.workflow_state.json。",
        "cockpit_safety_b4":               "无任何订单、订单凭证、券商载荷或可执行指令（No orders）。",
        "cockpit_safety_b5":               "approved_for_execution 在所有出现处均为 False（或不存在）。",
        "cockpit_safety_b6":               "Not investment advice — 不构成投资建议；任何实际操作前须经人工复核。",
        "cockpit_safety_pack_caption":     "数据包级安全标识（Phase 5G）",
        "cockpit_safety_scenario_caption": "场景级安全标识（Phase 5G）",
        # Tabs
        "cockpit_tab_overview":            "总览 / 安全",
        "cockpit_tab_company":             "公司研究中心",
        "cockpit_tab_horizon":             "周期决策卡片",
        "cockpit_tab_thesis":              "ThesisTracker 追踪",
        "cockpit_tab_portfolio":           "组合 / 交易方案",
        "cockpit_tab_option":              "期权叠加",
        "cockpit_tab_feedback":            "反馈 / Agent 评估",
        "cockpit_tab_provenance":          "数据来源 / 诊断",
        # Overview
        "cockpit_overview_scenario_kind":  "场景类型",
        "cockpit_overview_ticker":         "标的（示例）",
        "cockpit_overview_runid":          "Run ID",
        "cockpit_overview_no_desc":        "（无场景描述）",
        "cockpit_overview_warnings":       "场景提示（仅示例）：",
        # Company Research Hub
        "cockpit_company_target":          "标的",
        "cockpit_company_run_id":          "Run ID",
        "cockpit_company_as_of":           "截至",
        "cockpit_company_workflow":        "工作流",
        "cockpit_company_missing_data":    "缺失数据提示（降级场景面板）：",
        "cockpit_company_panel_equity":    "个股研究面板",
        "cockpit_company_panel_financial": "财务 / 估值面板",
        "cockpit_company_panel_pv":        "量价时机面板",
        "cockpit_company_financial_missing": "财务面板缺失 — 演示/示例降级场景，未重新生成任何分析。",
        "cockpit_company_expander_source": "源工作流面板（示例引用）",
        "cockpit_company_expander_evidence": "证据覆盖面板",
        "cockpit_company_expander_validation": "校验状态面板",
        "cockpit_company_synthesis_present":  "综合结论存在",
        "cockpit_company_synthesis_status":   "综合结论状态",
        "cockpit_company_present_steps":      "已完成步骤",
        "cockpit_company_missing_steps":      "缺失步骤",
        "cockpit_company_synthesis_no_summary": "（无综合摘要）",
        "cockpit_company_total_evidence":     "证据 ID 总数",
        "cockpit_company_total_records":      "记忆记录总数",
        "cockpit_company_complete_coverage":  "完整步骤覆盖",
        "cockpit_company_inspected":          "已检查记录",
        "cockpit_company_blocked":            "已阻断",
        "cockpit_company_needs_review":       "待复核",
        "cockpit_company_validation_signal":  "存在任何校验信号",
        "cockpit_company_is_clean":           "无异常",
        # Common
        "cockpit_common_populated":        "已填充",
        "cockpit_common_status":           "状态",
        "cockpit_common_no_summary":       "（无摘要）",
        "cockpit_common_direction":        "方向",
        "cockpit_common_confidence":       "信心",
        # Horizon cards
        "cockpit_horizon_caption":         "卡片按统一顺序短期→中期→长期排列。缺失的卡片以安全降级形式保留可见。",
        "cockpit_horizon_horizon":         "周期",
        "cockpit_horizon_no_thesis":       "该周期暂无论点 — 安全降级卡片（演示/示例）。",
        "cockpit_horizon_review_needed":   "需复核标记 — 原因：",
        "cockpit_horizon_missing_evidence": "证据缺失标记 — 缺失类型：",
        "cockpit_horizon_no_thesis_record": "（示例中无论点记录）",
        "cockpit_horizon_no_text":         "（无论点正文）",
        "cockpit_horizon_assumptions":     "前提假设",
        "cockpit_horizon_invalidation":    "证伪触发条件",
        "cockpit_horizon_next_action":     "下一步动作标签（描述性，非执行）：",
        "cockpit_horizon_view_warnings":   "视图级提示：",
        # ThesisTracker
        "cockpit_thesis_caption":          "ThesisTracker 行按 (标的, 周期) 列出。行内容确定，不会被编造。",
        "cockpit_thesis_no_rows":          "本示例场景无 tracker 行。",
        "cockpit_thesis_warnings":         "Tracker 级提示：",
        # Portfolio
        "cockpit_portfolio_alloc_summary": "组合配置摘要 —",
        "cockpit_portfolio_records":       "记录数",
        "cockpit_portfolio_blocked":       "已阻断",
        "cockpit_portfolio_needs_review":  "待复核",
        "cockpit_portfolio_reviewed":      "已复核",
        "cockpit_portfolio_risk_budget":   "风险预算",
        "cockpit_portfolio_cash_impact":   "现金影响",
        "cockpit_portfolio_no_risk_budget": "示例中无风险预算数据。",
        "cockpit_portfolio_no_cash_impact": "示例中无现金影响数据。",
        "cockpit_portfolio_positions":     "持仓（示例）",
        "cockpit_portfolio_trade_plans":   "交易方案（示例，非可执行）",
        "cockpit_portfolio_no_trade_plans": "本示例场景无交易方案。",
        "cockpit_portfolio_trade_plan_for": "交易方案 —",
        "cockpit_portfolio_action":        "动作",
        "cockpit_portfolio_status":        "状态",
        "cockpit_portfolio_review_trigger": "复核触发 — 原因：",
        "cockpit_portfolio_no_rationale":  "（无理由）",
        "cockpit_portfolio_no_levels":     "示例记录中无交易方案位级数据。",
        "cockpit_portfolio_missing_data":  "缺失数据提示：",
        # Option overlay
        "cockpit_option_no_record":        "本示例场景无期权叠加记录。",
        "cockpit_option_overlay_for":      "期权叠加 —",
        "cockpit_option_state":            "状态",
        "cockpit_option_status":           "状态",
        "cockpit_option_no_trade_msg":     "期权叠加结果为 `no_trade`（一级状态）。Phase 5H 不会推断替代策略。",
        "cockpit_option_no_trade_reason": "no_trade 原因：",
        "cockpit_option_review_trigger":   "复核触发：",
        "cockpit_option_strategy_summary": "策略摘要",
        "cockpit_option_decision":         "决策",
        "cockpit_option_strategy_type":    "策略类型",
        "cockpit_option_expiration":       "到期日",
        "cockpit_option_contracts":        "合约数（示例）",
        "cockpit_option_exit_rule":        "计划出场规则",
        "cockpit_option_risk_level":       "风险级别",
        "cockpit_option_rr":               "风险 / 收益（示例）",
        "cockpit_option_max_loss":         "最大亏损",
        "cockpit_option_max_gain":         "最大收益",
        "cockpit_option_breakeven":        "盈亏平衡",
        "cockpit_option_entry_iv":         "建仓时隐波",
        "cockpit_option_entry_underlying": "建仓时标的价",
        "cockpit_option_cash_required":    "所需现金",
        "cockpit_option_rr_ratio":         "风险收益比",
        "cockpit_option_liquidity":        "流动性提示（来自示例）：",
        "cockpit_option_event_risk":       "事件风险提示（来自示例）：",
        # Feedback / Agent evaluation
        "cockpit_feedback_caption":        "示例支撑下的人工反馈与 Agent 评估记录的只读摘要。",
        "cockpit_feedback_human":          "人工反馈（示例）",
        "cockpit_feedback_agent":          "Agent 评估（示例）",
        "cockpit_feedback_no_human":       "本场景无人工反馈记录。",
        "cockpit_feedback_no_agent":       "本场景无 Agent 评估记录。",
        "cockpit_feedback_memory_id":      "Memory ID：",
        "cockpit_feedback_target":         "标的：",
        "cockpit_feedback_outcome":        "结果：",
        "cockpit_feedback_record_id":      "记录 ID：",
        "cockpit_feedback_agent_type":     "Agent 类型：",
        "cockpit_feedback_lesson":         "经验：",
        "cockpit_feedback_entries_suffix": "条反馈条目",
        "cockpit_feedback_signals_suffix": "条信号",
        # Provenance / Diagnostics
        "cockpit_provenance_caption":      "仅演示用途的来源信息。这并非实时工作流输出。示例数据包是本预览页面唯一的数据来源。",
        "cockpit_provenance_pack_level":   "数据包级来源",
        "cockpit_provenance_scenario_level": "场景级来源",
        "cockpit_provenance_validation":   "校验 / 示例摘要",
        "cockpit_provenance_source":       "源示例：`lib/reliability/phase5_demo_pack.py`（Phase 5G 默认演示数据包）。",
        "cockpit_provenance_not_live":     "本页面不读取实时工作流输出，不调用任何实时 API。",
        # Fail-closed
        "cockpit_failclosed_headline":     "构建 Phase 5G 演示/示例数据包失败。无法显示投研中枢预览。",
        "cockpit_failclosed_no_detail":    "（无错误详情）",
        "cockpit_failclosed_note":         "Fail-closed：不向实时工作流、LLM 或外部 API 回退。修复演示数据包构建器后重试。",
        "cockpit_no_scenarios":            "Phase 5G 数据包内未提供任何场景。",
        # --- Phase 5N v0.2（机会优先重构）---
        # 新标签页
        "cockpit_tab_themes":              "市场主题",
        "cockpit_tab_opportunity":         "机会队列",
        "cockpit_tab_decision":            "决策工作区",
        "cockpit_tab_research":            "研究快照",
        "cockpit_tab_debate":              "Agent 辩论",
        "cockpit_tab_trade":               "交易 / 配置方案",
        "cockpit_tab_review":              "反馈 / 复核",
        # 总览 v0.2
        "cockpit_overview_v02_preview":    "机会优先 v0.2 预览 — 仅演示/示例数据，无实时工作流接入、无外部 API、无券商/下单/执行、不构成投资建议。approved_for_execution 在所有出现处均为 False（或不存在）。",
        "cockpit_overview_flow_header":    "中枢流程",
        "cockpit_overview_flow":           "市场主题 → 机会队列 → 研究包 → Agent 辩论 → 决策工作区 → 复核。",
        # Phase 5R — 演示导览 / 如何阅读本页
        "cockpit_walkthrough_header":      "如何阅读本页（演示导览）",
        "cockpit_walkthrough_intro":       "本页是机会优先、跨期限的投研中枢演示。全部为确定性示例数据；按以下顺序阅读各标签页：",
        "cockpit_walkthrough_step1":       "市场主题 — 市场层面的热度与生命周期背景（热度 ≠ 买入信号）。",
        "cockpit_walkthrough_step2":       "机会队列 — 按期限组织、依机会契合度排序的候选标的。",
        "cockpit_walkthrough_step3":       "研究包 / 研究快照 — 某候选标的会调用的来源研究模块（仅描述）。",
        "cockpit_walkthrough_step4":       "Agent 辩论 — 多头 / 空头 / 风险 / 评审视角；分歧始终可见，不被掩盖。",
        "cockpit_walkthrough_step5":       "决策工作区 — 仅供复核的状态；需人工复核，从不执行。",
        "cockpit_walkthrough_step6":       "反馈 / 复核 — 记录仅限本次会话的复核备注；不做任何持久化。",
        "cockpit_walkthrough_safety":      "仅演示/示例数据 · 仅供复核 · 不可执行 · 无实时工作流、LLM、外部 API、券商或下单。不构成投资建议。",
        # 市场主题（Phase 5J）
        "cockpit_themes_caption":          "示例支撑的主题情报 / 市场热度（Phase 5J）。主题是市场层面的背景，而非个股。",
        "cockpit_themes_heat_not_buy":     "主题热度分数并非买入信号，也不等同于入场质量。",
        "cockpit_themes_lifecycle":        "生命周期阶段",
        "cockpit_themes_heat_status":      "热度状态",
        "cockpit_themes_heat_score":       "热度分数",
        "cockpit_themes_candidates":       "候选标的数",
        "cockpit_themes_subthemes":        "子主题数",
        "cockpit_themes_chain_nodes":      "产业链节点数",
        "cockpit_themes_warnings":         "主题风险 / 拥挤度提示（示例）：",
        "cockpit_themes_chain_decomposition": "产业链分解",
        "cockpit_themes_candidate_tickers": "候选标的（示例）",
        "cockpit_themes_theme_count":      "主题",
        "cockpit_themes_subtheme_count":   "子主题",
        "cockpit_themes_chain_node_count": "产业链节点",
        "cockpit_themes_candidate_count":  "候选标的",
        "cockpit_themes_no_themes":        "本示例快照中无主题（安全空集）。",
        # 机会队列（Phase 5K）
        "cockpit_opportunity_caption":     "周期感知的机会队列（Phase 5K）。同一标的可在不同周期出现并对应不同的决策标签。",
        "cockpit_opportunity_heat_not_trade": "高主题热度并不自动等于 trade_now。拥挤度可将机会降级为观望 / 回避。",
        "cockpit_opportunity_horizon_queues": "周期队列",
        "cockpit_opportunity_cross_cutting": "横向队列",
        "cockpit_opportunity_short_term":  "短期交易",
        "cockpit_opportunity_mid_term":    "中期持仓",
        "cockpit_opportunity_long_term":   "长期投资",
        "cockpit_opportunity_watch_wait":  "观察 / 等待",
        "cockpit_opportunity_research_more": "进一步研究",
        "cockpit_opportunity_no_trade":    "不交易 / 回避",
        "cockpit_opportunity_no_candidates": "此队列暂无候选。",
        "cockpit_opportunity_decision":    "决策",
        "cockpit_opportunity_horizon":     "周期",
        "cockpit_opportunity_score":       "机会评分",
        "cockpit_opportunity_horizon_fit": "周期匹配度",
        "cockpit_opportunity_entry_quality": "入场质量",
        "cockpit_opportunity_crowding":    "拥挤风险",
        "cockpit_opportunity_next_action": "下一步动作：",
        "cockpit_opportunity_theme":       "主题",
        "cockpit_opportunity_cross_horizon": "跨周期对比",
        "cockpit_opportunity_cross_horizon_caption": "同一标的在不同周期下的不同决策（示例）。",
        "cockpit_opportunity_warnings":    "队列级提示：",
        # 决策工作区（Phase 5M）
        "cockpit_decision_caption":        "仅供查看的决策工作区（Phase 5M）。连接研究包与经人工复核的决策状态的桥梁。",
        "cockpit_decision_for":            "决策工作区 —",
        "cockpit_decision_status":         "状态",
        "cockpit_decision_decision_label": "决策标签",
        "cockpit_decision_next_action":    "仅供查看的下一步动作",
        "cockpit_decision_review_only":    "仅供查看：本工作区并非可执行决策，须经人工复核。",
        "cockpit_decision_recommendation_state": "建议 / 复核状态",
        "cockpit_decision_consensus":      "共识",
        "cockpit_decision_supporting_roles": "支持角色",
        "cockpit_decision_dissenting_roles": "异议角色",
        "cockpit_decision_evidence_coverage": "证据覆盖",
        "cockpit_decision_conflicts":      "未解决冲突",
        "cockpit_decision_no_conflicts":   "未记录冲突。",
        "cockpit_decision_no_views":       "本示例中无决策工作区视图。",
        "cockpit_decision_warnings":       "工作区提示：",
        # 研究快照（Phase 5B / 5C / 5L）
        "cockpit_research_caption":        "公司研究快照 — 汇总来源研究模块的产出；不替代、不重新生成原始的个股研究。",
        "cockpit_research_thesis_header":  "周期论点快照（来源产出）",
        "cockpit_research_pack_header":    "研究包模块覆盖（Phase 5L，描述性）",
        "cockpit_research_pack_status":    "研究包状态",
        "cockpit_research_pack_required_modules": "必需模块",
        # Agent 辩论（Phase 5M）
        "cockpit_debate_caption":          "示例支撑的 Agent 辩论（Phase 5M）。仅为角色记录 — 不运行任何实时 Agent。",
        "cockpit_debate_session_for":      "辩论会话 —",
        "cockpit_debate_participants":     "参与者",
        "cockpit_debate_stances":          "立场",
        "cockpit_debate_stance":           "立场",
        "cockpit_debate_confidence":       "信心",
        "cockpit_debate_key_claims":       "核心论点：",
        "cockpit_debate_risks":            "风险：",
        "cockpit_debate_missing_evidence": "缺失证据：",
        "cockpit_debate_invalidation":     "证伪条件：",
        "cockpit_debate_review_triggers":  "复核触发：",
        "cockpit_debate_critic":           "Critic 复核",
        "cockpit_debate_critic_ack":       "已确认冲突：",
        "cockpit_debate_allocation":       "配置视角",
        "cockpit_debate_option":           "期权视角",
        "cockpit_debate_alloc_non_exec":   "配置视角仅供查看，不可执行。",
        "cockpit_debate_option_non_exec":  "期权视角仅供查看，不可执行。",
        "cockpit_debate_conflicts":        "冲突",
        "cockpit_debate_no_conflicts":     "未记录冲突。",
        "cockpit_debate_no_sessions":      "本示例中无辩论会话。",
        # 交易 / 配置方案（Phase 5D）
        "cockpit_trade_caption":           "仅供查看的组合 / 交易方案（Phase 5D），置于决策工作区与辩论之后。",
        "cockpit_trade_boundary":          "仅供查看的规划视图 — 并非下单凭证（not an order ticket）。",
        "cockpit_trade_non_executable":    "不可执行",
        "cockpit_trade_requires_review":   "需人工复核",
        "cockpit_trade_max_risk_budget":   "最大风险预算 %",
        "cockpit_trade_max_portfolio_loss": "最大组合亏损 %",
        "cockpit_trade_risk_counts":       "高 / 中 / 低 / 未知 风险计数",
        "cockpit_trade_total_cash_impact": "现金影响合计",
        "cockpit_trade_min_cash":          "最低预计现金 %",
        "cockpit_trade_max_cash":          "最高预计现金 %",
        "cockpit_trade_col_target":        "标的",
        "cockpit_trade_col_horizon":       "周期",
        "cockpit_trade_col_action":        "动作",
        "cockpit_trade_col_status":        "状态",
        "cockpit_trade_col_target_alloc":  "目标配置 %",
        "cockpit_trade_col_actual_alloc":  "实际配置 %",
        "cockpit_trade_col_review_needed": "需复核",
        "cockpit_trade_col_kind":          "类型",
        "cockpit_trade_col_label":         "标签",
        "cockpit_trade_col_pct":           "百分比",
        "cockpit_trade_col_value":         "数值",
        "cockpit_trade_col_note":          "备注",
        # 期权叠加 v0.2
        "cockpit_option_caption_v02":      "仅供查看的期权叠加（Phase 5D）。no_trade 为一级状态；不推断替代策略；不执行。",
        # 反馈 / 复核 v0.2
        "cockpit_review_caption":          "示例支撑的人工反馈与 Agent 评估记录的只读摘要。暂未实现真实反馈持久化。",
        "cockpit_review_actions":          "仅供查看的动作标签来自示例/视图模型；不会提交或持久化任何内容。",
        # ── Phase 5Q: Human Feedback UI v0.1（仅会话 / 不持久化 / 不可执行）──────────
        "cockpit_review_hf_safety_headline": "人工反馈 — 仅限本次会话，不持久化；无券商/下单/执行；不构成投资建议。",
        "cockpit_review_hf_safety_b1":     "仅会话（Session-only）— 反馈仅存于本次浏览器会话，刷新或关闭后即丢失。",
        "cockpit_review_hf_safety_b2":     "不持久化（Not persisted）— 不写入磁盘、数据库、向量库或工作流状态。",
        "cockpit_review_hf_safety_b3":     "无券商/下单/执行（No broker/order/execution）。",
        "cockpit_review_hf_safety_b4":     "不调用任何 LLM 或外部 API（No LLM / external API）。",
        "cockpit_review_hf_safety_b5":     "approved_for_execution 始终为 False（或不存在）；不构成投资建议。",
        "cockpit_review_hf_form_header":   "记录复核反馈（仅会话）",
        "cockpit_review_hf_no_targets":    "当前示例无可复核的目标。",
        "cockpit_review_hf_kind_label":    "目标类型",
        "cockpit_review_hf_target_label":  "复核目标",
        "cockpit_review_hf_target_help":   "选择要附加复核反馈的示例目标：机会候选 / 投资期限 / 决策工作台 / 期权叠加。",
        "cockpit_review_hf_action_label":  "复核动作（仅供查看，不执行）",
        "cockpit_review_hf_note_label":    "备注（可选）",
        "cockpit_review_hf_note_ph":       "可填写复核理由或思路调整说明……",
        "cockpit_review_hf_non_exec_note": "所有动作均为仅供查看的复核意图；不会触发下单或执行，不会被持久化。",
        "cockpit_review_hf_add_button":    "加入本次会话预览",
        "cockpit_review_hf_clear_button":  "清空本次会话反馈",
        "cockpit_review_hf_preview_header": "本次会话反馈预览（仅会话）",
        "cockpit_review_hf_preview_note":  "以下条目仅存于本次会话，不持久化、不可执行。",
        "cockpit_review_hf_preview_empty": "本次会话尚未记录任何反馈。",
        "cockpit_review_hf_preview_count": "本次会话已记录 {n} 条仅会话反馈（不持久化）。",
        "cockpit_review_hf_col_kind":      "目标类型",
        "cockpit_review_hf_col_target":    "目标",
        "cockpit_review_hf_col_action":    "动作",
        "cockpit_review_hf_col_note":      "备注",
        "cockpit_review_hf_bind_kind":     "目标类型",
        "cockpit_review_hf_bind_ticker":   "标的",
        "cockpit_review_hf_bind_horizon":  "期限",
        "cockpit_review_hf_fixture_header": "示例支撑的人工反馈 / Agent 评估记录（只读）",
        # 复核动作标签
        "cockpit_review_action_accept_for_watchlist":             "加入观察清单",
        "cockpit_review_action_reject":                           "否决",
        "cockpit_review_action_modify_thesis":                    "修改论点",
        "cockpit_review_action_request_more_research":            "请求补充研究",
        "cockpit_review_action_wait_for_pullback":                "等待回调",
        "cockpit_review_action_manually_executed_outside_system": "已在系统外手动执行（仅标注）",
        "cockpit_review_action_skip":                             "跳过",
        "cockpit_review_action_review_later":                     "稍后复核",
        "cockpit_review_action_no_trade_confirmed":               "确认不交易（no_trade）",
        # 数据来源 / 诊断 v0.2
        "cockpit_provenance_no_api":       "无外部 API，无 LLM。这并非实时工作流输出。",
        "cockpit_provenance_intel_validation": "Phase 5J / 5K / 5L / 5M 校验摘要",
        # ── Phase 5O: Macro Dashboard v0.1 ───────────────────────────────────────
        "macro_page_title":                "宏观仪表盘",
        "macro_page_subtitle":             "实时宏观环境与市场状态总览。",
        # Phase 6A — Overview intro page (user-facing)
        "macro_banner_live":               "实时数据模式：以下为反映当前市况的实时数据。",
        "macro_banner_degraded":           "部分数据暂不可用，已回退到演示数据。",
        "macro_ov_state":                  "当前市场状态",
        "macro_ov_dimensions":             "本页分析维度",
        "macro_ov_dim_rates":              "利率 — 判断货币环境与久期压力。",
        "macro_ov_dim_credit":             "信用 — 衡量信用风险与市场承压程度。",
        "macro_ov_dim_vol":                "波动率 — 反映市场情绪与避险程度。",
        "macro_ov_dim_etf":                "ETF 收益 — 跨资产与板块的相对表现。",
        "macro_ov_dim_econ":               "经济数据 — 就业与通胀的最新趋势。",
        "macro_ov_dim_sentiment":          "市场情绪 — 综合的恐惧 / 贪婪与新闻情绪。",
        "macro_ov_sources":                "数据来源与更新频率",
        "macro_ov_sources_desc":           "数据来自公开市场行情与官方宏观统计，约每 15 分钟更新一次。",
        # Phase 5R — 演示导览 / 如何阅读本页
        "macro_walkthrough_header":        "如何阅读本页（演示导览）",
        "macro_walkthrough_intro":         "本页提供宏观优先的上游背景，供投研中枢参考。全部为确定性示例数据；按以下顺序阅读各标签页：",
        "macro_walkthrough_step1":         "宏观环境 — 确定性的风险偏好/规避/过渡背景及其驱动因子。",
        "macro_walkthrough_step2":         "宏观指标 — 示例的大宗商品、风险偏好/领涨结构、以及经济数据发布。",
        "macro_walkthrough_step3":         "期限倾向 — 当前环境如何影响短 / 中 / 长期姿态。",
        "macro_walkthrough_step4":         "主题影响 — 当前环境利好或承压的主题（背景判断，并非实时市场结论）。",
        "macro_walkthrough_step5":         "机会姿态 — 由此得出的仅供复核的姿态；绝不产生最终买卖决策。",
        "macro_walkthrough_safety":        "仅演示/示例数据 · 宏观优先背景 · 仅供复核 · 无实时宏观/外部 API、LLM、券商或下单。不构成投资建议。",
        "macro_scenario_select_label":     "宏观情景（演示/示例）",
        "macro_scenario_select_help":      "选择要预览的确定性宏观示例情景：risk_on（风险偏好）/ risk_off（风险规避）/ transition（过渡）/ degraded（数据降级/未知）。全部为离线示例数据。",
        "macro_sidebar_dashboard_id":      "Dashboard ID：",
        "macro_sidebar_data_source":       "数据来源：仅 Phase 5O 确定性示例数据，无任何实时宏观/外部接入。",
        # Safety banner
        "macro_safety_headline":           "仅供研究参考，不构成投资建议。",
        "macro_safety_b1":                 "Fixture/demo only — 演示/示例数据，无实时宏观数据接入。",
        "macro_safety_b2":                 "未调用任何实时宏观 API（No live macro API）。",
        "macro_safety_b3":                 "未调用任何外部 API（No external API）。",
        "macro_safety_b4":                 "未调用任何 LLM（No LLM）。",
        "macro_safety_b5":                 "无任何券商/订单/执行能力（No broker/order/execution）。",
        "macro_safety_b6":                 "approved_for_execution 在所有出现处均为 False（或不存在）；不构成投资建议。",
        # Tabs
        "macro_tab_overview":              "宏观综合",
        "macro_tab_regime":                "宏观区间",
        "macro_tab_liquidity":             "利率环境",
        "macro_tab_credit":                "信用与波动",
        "macro_tab_risk":                  "市场情绪",
        "macro_tab_horizon":               "周期倾向",
        "macro_tab_themes":                "主题影响",
        "macro_tab_posture":               "机会姿态",
        "macro_tab_provenance":            "数据来源",
        # Overview
        "macro_overview_caption":          "宏观区间是机会选择的一级上游输入：它影响投研中枢偏向动量交易、回调入场、仅观察、降风险还是长期建仓。",
        "macro_overview_first_class":      "为什么宏观是一级输入：先判断宏观区间，再筛选机会。宏观为背景信息，不产生最终买卖决策。",
        "macro_overview_regime_status":    "宏观区间状态",
        "macro_overview_confidence":       "信心",
        "macro_overview_as_of":            "截至",
        "macro_overview_scenario_kind":    "情景类型",
        "macro_overview_warnings":         "宏观提示（仅示例）：",
        # Regime
        "macro_regime_caption":            "确定性宏观区间快照（示例）。所有数值均为占位描述，并非实时计算或实时数据。",
        "macro_regime_primary":            "主区间状态",
        "macro_regime_supporting":         "辅助状态",
        "macro_regime_no_factors":         "本示例快照中无宏观因子（安全空集 / 降级）。",
        "macro_regime_growth":             "增长 / 衰退区间",
        # Common factor display
        "macro_factor_trend":              "趋势",
        "macro_factor_signal":             "信号",
        "macro_factor_value":              "数值（占位）",
        "macro_section_summary":           "小结",
        "macro_section_overall_signal":    "整体信号",
        # Liquidity / Rates / Inflation
        "macro_liquidity_caption":         "流动性、利率与通胀 — 风险资产的主导宏观驱动（示例）。",
        "macro_liquidity_header":          "流动性",
        "macro_rates_header":              "利率",
        "macro_inflation_header":          "通胀",
        "macro_liquidity_trend":           "流动性趋势",
        # Credit / Volatility / Breadth
        "macro_credit_caption":            "信用利差、波动率（VIX）与市场广度 — 风险情绪的确认/背离信号（示例）。",
        "macro_credit_header":             "信用利差",
        "macro_volatility_header":         "波动率",
        "macro_breadth_header":            "市场广度",
        "macro_dollar_header":             "美元",
        "macro_earnings_header":           "盈利周期",
        "macro_policy_header":             "政策风险",
        # Phase 5O.1: Macro Indicators tab
        "macro_tab_indicators":            "宏观指标",
        "macro_indicators_caption":        "用户关注的具体宏观工具与经济数据指标（示例）。分为大宗商品、风险偏好/领涨与经济数据三组。",
        "macro_indicators_not_live":       "本页指标为示例 / 演示数据。",
        "macro_indicators_commodities_header": "大宗商品",
        "macro_indicators_risk_header":    "风险偏好 / 领涨",
        "macro_indicators_releases_header": "经济数据",
        "macro_indicators_no_data":        "本示例中该组无指标。",
        "macro_ind_value":                 "数值（占位）",
        "macro_ind_trend":                 "趋势",
        "macro_ind_signal":                "信号",
        "macro_ind_status":                "状态",
        "macro_ind_category":              "类别",
        "macro_ind_interpretation":        "解读",
        "macro_ind_macro_implication":     "宏观含义",
        "macro_ind_horizon_implication":   "周期含义",
        # Risk appetite
        "macro_risk_caption":              "风险偏好状态（示例）。",
        "macro_risk_state":                "风险状态",
        # Horizon bias
        "macro_horizon_caption":           "宏观对不同周期的倾向（仅供查看；并非交易指令）。同一区间可短期偏动量、长期偏建仓。",
        "macro_horizon_short":             "短期倾向",
        "macro_horizon_mid":               "中期倾向",
        "macro_horizon_long":              "长期倾向",
        "macro_horizon_rationale":         "依据",
        "macro_horizon_not_decision":      "周期倾向为仅供查看的背景信息，并非买卖决策或交易指令。",
        # Theme implications
        "macro_themes_caption":            "宏观对主题的影响（仅示例）。这些是示例关系，并非实时市场事实或买卖建议。",
        "macro_themes_implication":        "影响",
        "macro_themes_rationale":          "依据",
        "macro_themes_not_live":           "主题影响为示例性背景关系，并非实时市场结论。",
        "macro_themes_no_implications":    "本示例中无主题影响。",
        # Opportunity posture
        "macro_posture_caption":           "仅供查看的机会姿态指引（示例）。这些不是交易指令，也不产生最终买卖决策。",
        "macro_posture_primary":           "主姿态",
        "macro_posture_secondary":         "辅助姿态",
        "macro_posture_rationale":         "依据",
        "macro_posture_not_decision":      "机会姿态仅为背景参考，并非买卖决策或交易指令。",
        # Provenance / Diagnostics
        "macro_provenance_caption":        "仅演示用途的来源信息。这并非实时工作流输出，未调用任何实时宏观/外部 API。",
        "macro_provenance_no_api":         "无实时宏观 API，无外部 API，无 LLM。",
        "macro_provenance_validation":     "校验 / 示例摘要（Phase 5O）",
        "macro_provenance_source":         "源示例：`lib/reliability/phase5_macro_dashboard.py`（Phase 5O 确定性宏观示例）。",
        "macro_provenance_not_live":       "本页面不读取实时工作流状态，不调用任何实时宏观/外部 API。",
        "macro_provenance_missing_factors": "缺失因子（降级示例）：",
        # Fail-closed
        "macro_failclosed_headline":       "构建 Phase 5O 宏观示例数据失败。无法显示宏观仪表盘预览。",
        "macro_failclosed_no_detail":      "（无错误详情）",
        "macro_failclosed_note":           "Fail-closed：不向实时宏观数据、LLM 或外部 API 回退。修复示例构建器后重试。",
        "macro_no_scenarios":              "未提供任何宏观示例情景。",
        # ── Phase 6A: Live Macro Conditions ──────────────────────────────────────
        "macro_live_header":               "实时宏观环境",
        "macro_live_caption":              "下方为反映当前市况的实时宏观数据；每个指标标注其数据状态。",
        "macro_live_mode_caption":         "实时数据反映当前市况。仅供查看，不构成投资建议，且不授权任何交易。",
        "macro_live_disabled_note":        "实时模式已关闭：使用备用示例数据。",
        "macro_live_failclosed_note":      "实时宏观数据获取整体失败，已回退到示例数据。页面继续以仅供查看的方式展示，不会崩溃。",
        "macro_live_coverage_label":       "数据覆盖率",
        "macro_live_freshness_label":      "数据时效",
        "macro_live_updated_label":        "快照时间（UTC）",
        "macro_live_regime_label":         "实时宏观区间",
        "macro_live_confidence_label":     "信心",
        "macro_live_posture_label":        "机会姿态（仅供查看）",
        "macro_live_signals_label":        "关键信号",
        "macro_live_horizon_label":        "周期倾向",
        "macro_live_badge_live_help":      "LIVE = 本指标组已成功获取实时数据。",
        "macro_live_badge_fixture_help":   "FIXTURE = 本指标组获取失败，已回退到示例数据。",
        "macro_live_fallback_note":        "本指标暂无实时数据，已使用备用数据显示。",
        "macro_live_grp_vix":              "市场波动率",
        "macro_live_grp_rates":            "利率与通胀",
        "macro_live_grp_credit":           "信用利差",
        "macro_live_grp_dollar":           "美元",
        "macro_live_grp_etf":              "ETF 收益",
        "macro_live_grp_releases":         "经济数据",
        "macro_live_grp_sentiment":        "市场情绪",
        "macro_live_vix":                  "VIX",
        "macro_live_vix_chg":              "VIX 1M 变化",
        "macro_live_feargreed":            "恐惧贪婪代理（0–100）",
        "macro_live_y10":                  "10Y 收益率 %",
        "macro_live_y2":                   "2Y 收益率 %",
        "macro_live_spread":               "10Y-2Y 利差 %",
        "macro_live_breakeven":            "10Y 盈亏平衡通胀 %",
        "macro_live_hy":                   "高收益债利差 %",
        "macro_live_dxy":                  "广义美元指数",
        "macro_live_dxy_chg":              "美元 1M 变化 %",
        "macro_live_nfp":                  "NFP 非农就业（千人）",
        "macro_live_cpi":                  "CPI 指数",
        "macro_live_ppi":                  "PPI 指数",
        "macro_live_nfp_chg":              "NFP 月度变化（千人）",
        "macro_live_cpi_mom":              "CPI 环比 %",
        "macro_live_ppi_mom":              "PPI 环比 %",
        "macro_live_sentiment_score":      "情绪分（0–100）",
        "macro_live_etf_1m":               "1M 收益 %",
        "macro_live_etf_3m":               "3M 收益 %",
        "macro_live_fear_greed_proxy_note": "恐惧贪婪指数由市场波动率推算：波动越平静，数值越高（越偏贪婪）；波动越剧烈，数值越低（越偏恐惧）。",
        "macro_live_safety":               "实时宏观为仅供查看的背景信息，不产生最终买卖决策，也不授权任何交易。",
        # Phase 6A — regime / confidence / horizon-bias localized value maps
        "macro_regimeval_risk_on":         "偏多（risk-on）",
        "macro_regimeval_risk_off":        "偏空（risk-off）",
        "macro_regimeval_transition":      "过渡（transition）",
        "macro_regimeval_degraded":        "降级 / 未知（degraded）",
        "macro_confval_high":              "高",
        "macro_confval_medium":            "中",
        "macro_confval_low":               "低",
        "macro_biasval_favorable":         "有利",
        "macro_biasval_neutral":           "中性",
        "macro_biasval_cautious":          "谨慎",
        "macro_biasval_unfavorable":       "不利",
        # Phase 6A — localized opportunity posture by regime
        "macro_posture_text_risk_on":      "偏多环境：短 / 中期利于动量与延续型机会；长期入场仍需保持估值纪律。仅供查看的背景判断，并非买卖决策。",
        "macro_posture_text_risk_off":     "偏空环境：不利于新建短 / 中期风险敞口；优先保全资本，等待后续可能出现的建仓窗口。仅供查看，并非买卖决策。",
        "macro_posture_text_transition":   "过渡环境：信号混合 / 待确认；各周期保持谨慎，等待确认后再行动。仅供查看，并非买卖决策。",
        "macro_posture_text_degraded":     "数据覆盖不足，无法判定区间。将宏观视为未知，仅依赖自下而上的复核。仅供查看，并非买卖决策。",
        # Phase 6A — localized signal templates (parameterized via {placeholders})
        "macro_sig_vix_low":               "VIX {vix} 偏低（<18）：波动平静，偏 risk-on。",
        "macro_sig_vix_high":              "VIX {vix} 偏高（>27）：市场承压，偏 risk-off。",
        "macro_sig_vix_mid":               "VIX {vix} 处于中间区间（18–27）：波动率中性。",
        "macro_sig_fg_greed":              "恐惧贪婪代理 {fg} 处于贪婪（>60）：偏 risk-on（留意拥挤）。",
        "macro_sig_fg_fear":               "恐惧贪婪代理 {fg} 处于恐惧（<40）：偏 risk-off。",
        "macro_sig_credit_tight":          "高收益债利差 {hy}pp 偏窄（<3.5）：信用健康，偏 risk-on。",
        "macro_sig_credit_wide":           "高收益债利差 {hy}pp 偏宽（>5.0）：信用承压，偏 risk-off。",
        "macro_sig_curve_inverted":        "10Y-2Y 利差 {spread}pp 倒挂（<0）：衰退风险，需谨慎。",
        "macro_sig_curve_steep":           "10Y-2Y 利差 {spread}pp 正向走陡（>0.5）：利于扩张。",
        "macro_sig_breadth_broad":         "SPY {spy}% 与 IWM {iwm}% 近 1 月均为正：参与度广泛，偏 risk-on。",
        "macro_sig_breadth_weak":          "SPY {spy}% 与 IWM {iwm}% 近 1 月均为负：普遍走弱，偏 risk-off。",
        "macro_sig_breadth_mixed":         "SPY {spy}% 与 IWM {iwm}% 近 1 月分化：广度信号混合。",
        "macro_sig_dollar_strong":         "广义美元近 1 月 +{chg}%：流动性收紧，偏 risk-off。",
        "macro_sig_dollar_weak":           "广义美元近 1 月 {chg}%：流动性宽松，偏 risk-on。",
        "macro_sig_degraded":              "实时数据覆盖率 {coverage_pct} 低于 50% 阈值：区间研判降级 / 未知。",
        "macro_sig_default":               "无明确宏观信号，按默认净值判定。",
        # Phase 6A — localized status words (for live sub-regime readouts)
        "macro_status_elevated":           "偏高",
        "macro_status_moderate":           "中等",
        "macro_status_low":                "偏低",
        "macro_status_contained":          "受控",
        "macro_status_tightening":         "收紧",
        "macro_status_easing":             "宽松",
        "macro_status_neutral":            "中性",
        "macro_status_tight":              "偏窄 / 健康",
        "macro_status_normal":             "正常",
        "macro_status_wide":               "偏宽 / 承压",
        "macro_status_calm":               "平静",
        "macro_status_stressed":           "承压",
        "macro_status_broad":              "广泛",
        "macro_status_narrow":             "狭窄",
        "macro_status_mixed":              "混合",
        "macro_status_strengthening":      "走强",
        "macro_status_weakening":          "走弱",
        "macro_status_stable":             "平稳",
        "macro_status_greed":              "贪婪",
        "macro_status_extreme_greed":      "极度贪婪",
        "macro_status_fear":               "恐惧",
        "macro_status_extreme_fear":       "极度恐惧",
        "macro_status_unknown":            "未知",
        # Phase 6A — live sub-regime domain labels + section headers
        "macro_live_domain_rates":         "利率",
        "macro_live_domain_inflation":     "通胀预期",
        "macro_live_domain_liquidity":     "流动性",
        "macro_live_domain_credit":        "信用利差",
        "macro_live_domain_volatility":    "波动率",
        "macro_live_domain_breadth":       "市场广度",
        "macro_live_domain_dollar":        "美元",
        "macro_live_domain_risk":          "风险偏好",
        "macro_live_regime_readout":       "区间研判（基于实时数据）",
        "macro_live_overview_regime":      "当前宏观区间",
        "macro_live_section_signals":      "关键信号（基于实时数据）",
        "macro_live_details":              "详情",
        "macro_live_no_group_data":        "该指标组暂无实时数据，已回退至示例值。",
        "macro_live_status_label":         "状态",
        "macro_live_theme_caption":        "以下主题影响由当前宏观区间推导，仅为背景判断，并非实时市场结论或买卖建议。",
        "macro_theme_impl_risk_on":        "偏多环境通常利好成长 / AI / 半导体等高 beta 主题，相对利空防御板块；留意拥挤与估值。",
        "macro_theme_impl_risk_off":       "偏空环境通常利好防御 / 必需消费 / 现金类，相对利空高 beta 成长主题。",
        "macro_theme_impl_transition":     "过渡环境下主题轮动不清晰，建议等待确认后再行动。",
        "macro_theme_impl_degraded":       "数据不足，暂不推导主题影响。",
        # Phase 6A — visual upgrade chrome (hero banner + trend tables + sections)
        "macro_hero_label":                "当前市场状态",
        "macro_hero_caption":              "由实时宏观数据确定性研判（仅供查看，并非买卖决策）。",
        "macro_trend_header":              "历史趋势（近 6 期）",
        "macro_trend_no_data":             "暂无历史数据。",
        "macro_trend_date":                "日期",
        "macro_trend_value":               "数值",
        "macro_sec_headline":              "区间总览",
        "macro_sec_indicators":            "核心指标",
        "macro_sec_signals":               "信号与研判",
        # Phase 6B — AI Signal Candidates (Scanner signal layer)
        "scn_sig_title":                   "AI候选信号",
        "scn_sig_caption":                 "基于真实信号自动生成的候选标的（仅供研究查看，并非买卖建议）。",
        "scn_sig_macro_label":             "宏观区间",
        "scn_sig_generate_btn":            "生成候选",
        "scn_sig_send_btn":                "发送到手动扫描",
        "scn_sig_generating":              "正在为候选标的评分……",
        "scn_sig_sent_note":               "已将候选标的填入下方手动股票池。",
        "scn_sig_empty_hint":              "点击「生成候选」，由系统综合另类数据、EPS 修正趋势、叙事归因与入场质量自动产出候选标的。",
        "scn_sig_col_ticker":              "代码",
        "scn_sig_col_score":               "综合评分",
        "scn_sig_col_entry":               "入场质量",
        "scn_sig_col_horizon":             "周期契合（短/中/长）",
        "scn_sig_col_signals":             "关键信号",
        "scn_sig_count":                   "候选数量",
        "scn_sig_disclaimer":              "仅供研究查看，不构成投资建议；不产生任何买卖或下单指令。",
        # Phase 6B v2 — Dual-Track signal layer (additive)
        "scn_sig_llm_depth":               "LLM叙事分析数量",
        "scn_sig_llm_help":                "对通过第一层筛选的标的，按质量预评分取前 N 名进行 LLM 叙事阶段判断（10–100，默认 50）。",
        "scn_sig_llm_est":                 "预计耗时",
        "scn_sig_col_type":                "类型",
        "scn_sig_subscores":               "Track A / Track B 子评分",
        "scn_sig_col_track_a":             "Track A 评分",
        "scn_sig_col_track_b":             "Track B 评分",
        "scn_sig_col_insider":             "内部增持",
        "scn_sig_col_unusual":             "异常新闻",
        "scn_sig_col_analyst":             "分析师上调",
        # Phase 6B v3 — Horizon-native signal cards (additive)
        "scn_sig_filter_label":            "按周期筛选（默认全选）",
        "scn_sig_hz_short":                "短线 Short",
        "scn_sig_hz_mid":                  "中线 Mid",
        "scn_sig_hz_long":                 "长线 Long",
        "scn_sig_strength_triple":         "三线共振",
        "scn_sig_strength_double":         "双线",
        "scn_sig_strength_single":         "单线",
        "scn_sig_strength_none":           "弱信号",
        "scn_sig_triple_header":           "⭐ 三线共振 Triple Signal",
        "scn_sig_priced_in":               "可能已被price in",
        "scn_sig_details":                 "详情 / Details",
        "scn_sig_summary":                 "共 {n} 个候选 · 三线共振 {triple} · 双线 {double} · 单线 {single}",
        "scn_sig_eps":                     "EPS 修正",
        "scn_sig_val":                     "估值分位",
        "scn_sig_narr_stage":              "叙事阶段",
        "scn_sig_theme_tags":              "主题标签",
        # Phase 6B v2 — Scanner universe configuration (additive)
        "scn_uni_title":                   "股票池构成配置",
        "scn_uni_sp500":                   "包含标普500前100成分股",
        "scn_uni_themes":                  "加入主题篮子",
        "scn_uni_manual":                  "手动添加标的（逗号分隔）",
        "scn_uni_max":                     "股票池规模上限",
        "scn_uni_current":                 "当前股票池：{n} 个标的",
        "scn_uni_preloaded":               "已从行业研究预载主题：{label}（{n} 个标的）",
        "scn_uni_clear_btn":               "清除",
        # Phase 6B — Cross-GICS Market Themes (additive)
        "p2_tab_sector":                   "行业分析",
        "theme_tab":                       "市场主题",
        "theme_subtitle":                  "面向当前 AI 驱动周期的跨 GICS 投资主题。主题动量将作为扫描器股票池来源。",
        "theme_caption":                   "每个主题或追踪一只代表性 ETF，或以精选成分股的等权篮子计算（人工整理，2026年6月）。仅供研究参考，不构成投资建议。",
        "theme_loading":                   "正在加载主题动量...",
        "theme_no_data":                   "暂时无法获取主题动量数据，请稍后重试。",
        "theme_col_theme":                 "主题",
        "theme_col_1m":                    "1月收益%",
        "theme_col_3m":                    "3月收益%",
        "theme_col_6m":                    "6月收益%",
        "theme_col_score":                 "动量评分",
        "theme_col_3m_excess":             "3月超额%(vs QQQ)",
        "theme_col_stage":                 "轮动阶段",
        "theme_col_breadth":               "广度",
        "theme_stage_unconfirmed":         "未确认",
        "theme_col_source":                "数据来源",
        "theme_src_etf":                   "ETF",
        "theme_src_equal_weight":          "等权",
        "theme_src_fixture":               "示例",
        "theme_constituents":              "成分股",
        "theme_constituent_returns":       "成分股收益（1月 / 3月）",
        "theme_bar_title":                 "成分股3月收益（%）",
        "theme_constituent_na":            "暂无成分股收益数据。",
        "theme_send_top_btn":              "将最强主题发送至扫描器",
        "theme_send_all_btn":              "将全部主题成分股发送至扫描器",
        "theme_sent_top":                  "已将最强主题发送至扫描器",
        "theme_sent_all":                  "已将全部主题成分股发送至扫描器",
        "theme_tickers":                   "支",
        "theme_analyze_btn":               "AI 研判",
        "theme_analyzing":                 "正在研判主题...",
        "theme_ai_macro_alignment":        "宏观契合度",
        "theme_ai_narrative_stage":        "叙事阶段",
        "theme_ai_catalysts":              "核心催化剂",
        "theme_ai_risks":                  "风险因素",
        "theme_ai_horizon":                "持有周期",
        "theme_ai_summary":                "摘要",
        "theme_ai_unavailable":            "AI 分析暂不可用。",
    },
    "en": {
        # ── Sidebar ──────────────────────────────────────────────────────────────
        "sidebar_ticker":     "Ticker Symbol",
        "sidebar_ticker_ph":  "e.g. NVDA",
        "sidebar_cache":      "Data Cache",
        "cache_ohlcv":        "OHLCV",
        "cache_financials":   "Financials",
        "cache_balance":      "Balance Sheet",
        "cache_cashflow":     "Cash Flow",
        "dark_mode":          "🌙 Dark Mode",
        "disclaimer":         "⚠️ For research only, not investment advice",
        # Nav links
        "nav_home":           "🏠 Home",
        # Phase 6C-B: nav_p1 (AI Research Workflow / Overview) is DEPRECATED in the
        # sidebar — the page file is retained and reachable by URL, but it is no
        # longer registered as a nav entry. Key kept for backward compatibility.
        "nav_p1":             "🔭 Overview",
        "nav_p2":             "🏭 Sector Research",
        "nav_p3":             "🔍 Stock Scanner",
        "nav_p4":             "🏢 Equity Research",
        # Phase 5P: nav_p5 / nav_p6 are legacy source-module labels — Financial
        # Analysis and Price & Volume are now sub-surfaces under Equity Research
        # and are no longer shown as top-level sidebar nav entries. Keys retained
        # for backward compatibility.
        "nav_p5":             "📊 Financials",
        "nav_p6":             "📉 Price & Volume",
        "nav_p8":             "🌐 Macro Dashboard",
        "nav_p9":             "📋 Trading Desk",
        "nav_section":        "Navigation",
        # ── Phase 6C-B: Investment Cockpit rebuild (data aggregation hub) ────────
        "cockpit_hub_title":            "🧭 Investment Cockpit / 投研中枢",
        "cockpit_hub_subtitle":         "Live data aggregation hub — macro, themes, signals and equity valuation in one place (research only; not investment advice)",
        "cockpit_hub_refresh_btn":      "🔄 Refresh All",
        "cockpit_hub_last_refresh":     "Last refresh",
        "cockpit_hub_never":            "Never refreshed",
        "cockpit_hub_status_header":    "Module data status",
        "cockpit_hub_status_fresh":     "Refreshed this session",
        "cockpit_hub_status_stale":     "Stale / never",
        "cockpit_hub_status_macro":     "Macro",
        "cockpit_hub_status_themes":    "Themes",
        "cockpit_hub_status_signals":   "Signals",
        "cockpit_hub_status_equity":    "Equity",
        "cockpit_hub_sec_macro":        "A · Macro Regime",
        "cockpit_hub_macro_not_loaded": "Macro data not loaded",
        "cockpit_hub_macro_regime":     "Regime",
        "cockpit_hub_macro_bias":       "Horizon bias",
        "cockpit_hub_macro_signals":    "Key signals",
        "cockpit_hub_macro_posture":    "Opportunity posture",
        "cockpit_hub_link_macro":       "Go to Macro Dashboard →",
        "cockpit_hub_sec_themes":       "B · Market Themes",
        "cockpit_hub_themes_not_loaded":"Theme data not loaded",
        "cockpit_hub_link_sector":      "Go to Sector Research →",
        "cockpit_hub_theme_3m":         "3M return",
        "cockpit_hub_theme_momentum":   "Momentum score",
        # Phase 7B — fragility banner + theme stage / breadth (Cockpit)
        "cockpit_hub_internals":        "Internals",
        "cockpit_hub_internals_note":   "Internals are a tighten-only early warning; they do not change the regime label above.",
        "cockpit_hub_internals_unavail":"unavailable",
        "cockpit_frag_dist":            "distribution days",
        # B1: full sentence for the banner so "5/25" is never misread as a date.
        "cockpit_frag_dist_banner":     "{n} distribution days in 25 sessions",
        "cockpit_frag_breadth":         "breadth",
        "cockpit_frag_gns":             "good-news-sold",
        "cockpit_frag_gns_unit":        "",
        # B2: label for the evaluated-sample denominator ("1/12 evaluated").
        "cockpit_frag_gns_eval":        "evaluated",
        # Banner space is tight → compact "num/den"; the workbench table uses the full phrase.
        "cockpit_frag_gns_banner":      "{num}/{den}",
        "cockpit_frag_gns_full":        "{num} of {den} post-beat names sold off",
        "cockpit_frag_gns_concept":     "good-news-sold = sell-the-news: share of post-beat names that sold off on the next session.",
        "cockpit_frag_na":              "n/a",
        # Fragility level badge names + one-line tighten-only explainer.
        "cockpit_frag_lvl_normal":      "normal",
        "cockpit_frag_lvl_elevated":    "elevated",
        "cockpit_frag_lvl_high":        "high",
        "cockpit_frag_lvl_explain":     "normal = no signs of systemic deterioration; elevated = several deterioration signals at once, but this is an alert only — thresholds are not tightened; high = deterioration broadly confirmed — only short-horizon entry thresholds tighten (mid/long horizons unaffected).",
        # Phase 7B — Macro Dashboard "Market Internals" workbench block
        "mi_header":                    "Market Internals (workbench)",
        "mi_not_loaded":                "Refresh the Cockpit first to generate an internals reading",
        "mi_go_cockpit":                "Go to Investment Cockpit →",
        "mi_level":                     "Fragility level",
        # Label may carry a short reading-note; the VALUE stays the raw token
        # (rolling / snapshot / the date), never translated.
        "mi_source":                    "Hysteresis source",
        "mi_vintage":                   "Data vintage",
        "mi_vintage_mismatch":          "vintage mismatch (degraded to snapshot)",
        "mi_points":                    "Points",
        "mi_component":                 "Signal",
        "mi_value":                     "Reading",
        "mi_triggered":                 "Triggered?",
        "mi_degrade":                   "Data note",
        "mi_c_breadth20":               ">20-day MA %",
        "mi_c_breadth50":               ">50-day MA %",
        "mi_c_slope":                   "Breadth trend (slope)",
        "mi_c_weak_bounce":             "Weak bounce",
        "mi_c_vol":                     "Leading-theme volume shrink",
        "mi_c_od":                      "Offense/defense",
        # Yes/No — render bool readings human-readable (weak-bounce etc.).
        "mi_yes":                       "Yes",
        "mi_no":                        "No",
        # Offense/defense enum display. EN values EQUAL the raw rotation.py tokens
        # (so the EN surface is unchanged); only ZH gets localized words.
        "mi_od_dir_offense":            "offense",
        "mi_od_dir_defense":            "defense",
        "mi_od_dir_balanced":           "balanced",
        "mi_od_mag_strong":             "strong",
        "mi_od_mag_moderate":           "moderate",
        "mi_od_mag_mild":               "mild",
        # Degrade-reason glosses are EMPTY in EN → the bare audit token renders.
        "mi_dgloss_finnhub_unavailable":    "",
        "mi_dgloss_earnings_source_absent": "",
        "mi_dgloss_no_reports_in_window":   "",
        "mi_dgloss_partial_frame_coverage": "",
        "mi_dgloss_implausible_count":      "",
        "mi_note":                      "Internals are a tighten-only early warning — a worse signal only tightens thresholds, never loosens them; research-only, not investment advice.",
        "cockpit_hub_clock_suspect":    "System clock looks off (snapshot still written)",
        "cockpit_hub_theme_3m_excess":  "3M excess (vs QQQ)",
        "cockpit_hub_stage":            "Rotation stage",
        "cockpit_hub_stage_confirmed":  "breadth-confirmed",
        "cockpit_hub_stage_unconfirmed":"unconfirmed",
        "cockpit_hub_breadth":          "Breadth",
        "stage_leading":                "leading",
        "stage_rotating_in":            "rotating in",
        "stage_rotating_out":           "rotating out",
        "stage_out_of_favor":           "out of favor",
        "cockpit_hub_sec_signals":      "C · Signal Candidates",
        "cockpit_hub_signals_total":    "Total candidates",
        "cockpit_hub_signals_triple":   "Triple",
        "cockpit_hub_signals_double":   "Double",
        "cockpit_hub_signals_single":   "Single",
        "cockpit_hub_signals_none":     "No signal candidates yet",
        "cockpit_hub_top_candidates":   "Top 5 candidates",
        "cockpit_hub_select_header":    "Select tickers for deep research",
        "cockpit_hub_select_all":       "Select All",
        "cockpit_hub_no_tickers":       "No tickers available",
        "cockpit_hub_run_equity":       "🔬 Run Equity Research",
        "cockpit_hub_equity_running":   "Running equity research…",
        "cockpit_hub_equity_done":      "Equity research complete",
        "cockpit_hub_no_selection":     "Select at least one ticker first",
        "cockpit_hub_sec_equity":       "D · Equity Research Results",
        "cockpit_hub_equity_none":      "No tickers selected or no results yet",
        "cockpit_hub_not_researched":   "Not yet researched",
        "cockpit_hub_view_research":    "View Full Research",
        "cockpit_hub_go_equity":        "Go to Equity Research",
        "cockpit_hub_sec_triple":       "E · Triple Signal Watch",
        "cockpit_hub_triple_none":      "No triple-signal candidates outside active holdings",
        "cockpit_hub_add_holdings":     "Add to Holdings",
        "cockpit_hub_add_td":           "➕ Add to Trading Desk",
        "cockpit_hub_added_td":         "added to Trading Desk watch",
        "cockpit_hub_refresh_running":  "Refreshing…",
        "cockpit_hub_stage_macro":      "① Macro + regime classification",
        "cockpit_hub_stage_themes":     "② Theme momentum",
        "cockpit_hub_stage_signals":    "③ Signal candidate generation",
        "cockpit_hub_stage_equity":     "④ Equity valuation",
        "cockpit_hub_refresh_complete": "Refresh complete",
        "cockpit_hub_safety":           "⚠️ This page is research / review only — it places no orders, connects to no broker, and is not investment advice.",
        "cockpit_hub_upside":           "Upside",
        "cockpit_hub_confidence":       "Confidence",
        "cockpit_hub_fair_value":       "Fair value (mid)",
        "cockpit_hub_action":           "Action",
        "cockpit_hub_catalyst":         "Catalyst",
        # ── Phase 6C-B: Equity page AI Valuation Summary section ────────────────
        "cockpit_fv_header":            "📊 AI Valuation Summary / AI估值综合",
        "cockpit_fv_range":             "Fair value range",
        "cockpit_fv_low":               "Low",
        "cockpit_fv_mid":               "Mid",
        "cockpit_fv_high":              "High",
        "cockpit_fv_upside":            "Upside (mid vs current)",
        "cockpit_fv_confidence":        "Confidence",
        "cockpit_fv_methodology":       "Methodology",
        "cockpit_fv_dcf":               "DCF value",
        "cockpit_fv_relative":          "Relative value (sector P/E)",
        "cockpit_fv_analyst":           "Analyst target",
        "cockpit_fv_run_debate":        "🤖 Run AI Debate",
        "cockpit_fv_send_desk":         "📤 Send to Trading Desk",
        "cockpit_fv_sent":              "Sent to Trading Desk — order recommendations will use the app-computed fair value.",
        "cockpit_fv_debate_running":    "Running AI bull/bear debate…",
        "cockpit_fv_bull":              "Bull case",
        "cockpit_fv_bear":              "Bear case",
        "cockpit_fv_risk":              "Risk factors",
        "cockpit_fv_synthesis":         "Synthesis",
        "cockpit_fv_endorsed":          "Endorsed fair value range",
        "cockpit_fv_action":            "Recommended action",
        "cockpit_fv_na":                "Insufficient valuation data.",
        # ── Anchor consistency gate (Valuation stop-the-bleed) ──────────────────
        "cockpit_fv_irreconcilable":    "⚠️ Anchors Irreconcilable",
        "cockpit_fv_irreconcilable_note": "The valuation methods disagree too much to blend into a single range — each is shown separately for human judgment.",
        "cockpit_fv_basis":             "Basis",
        "cockpit_fv_basis_forward":     "forward EPS",
        "cockpit_fv_basis_trailing":    "trailing EPS (fallback)",
        "cockpit_fv_basis_mixed":       "⚠️ Mixed basis: forward EPS × trailing peer P/E",
        # --- Method router (Valuation Refactor v1) ---
        "cockpit_fv_company_type":      "Company type",
        "cockpit_fv_methods_used":      "Methods used",
        "cockpit_fv_excluded":          "Excluded anchors (not blended)",
        "cockpit_fv_peer_basis":        "Peer basis",
        "cockpit_fv_routing":           "Routing",
        "cockpit_fv_borderline":        "borderline — default methods used",
        "cockpit_fv_flag_excluded":     "excluded",
        "cockpit_fv_flag_cycle_distorted": "cycle-distorted",
        "cockpit_fv_type_mature_profitable":   "Mature / profitable",
        "cockpit_fv_type_growth_profitable":   "Growth / profitable",
        "cockpit_fv_type_growth_unprofitable": "Growth / unprofitable",
        "cockpit_fv_type_project_driven":      "Project-driven",
        "cockpit_fv_type_cyclical":            "Cyclical",
        "cockpit_fv_peer_growth_matched":      "growth-matched peers",
        "cockpit_fv_peer_sector_fallback":     "sector fallback",
        "cockpit_fv_caveats":           "Caveats",
        "cockpit_fv_caveat_cyclical_band_unavailable": "Cyclical history band unavailable — degraded to analyst-only (< required ≤4y annual observations)",
        "cockpit_fv_caveat_single_anchor_blend":       "Only a single anchor entered the blend",
        "cockpit_fv_caveat_implausible_forward_eps":   "Forward EPS implausible (far above trailing EPS) — relative anchor excluded",
        "cockpit_fv_caveat_anchor_implausible_vs_price": "An anchor was implausible vs the current price — that anchor was excluded",
        "cockpit_fv_caveat_implausible_growth_input":  "Revenue-growth input implausible — treated as missing for classification & peer matching",
        "cockpit_fv_caveat_analyst_pool_dispersed":    "Analyst target pool too dispersed — confidence capped at low (median still blended)",
        "cockpit_fv_analyst_pool":     "Analyst pool",
        "cockpit_fv_computed_at":      "Computed",
        "cockpit_fv_running":           "Computing valuation…",
        "cockpit_fv_update":            "🔄 Update Valuation",
        "cockpit_fv_update_hint":       "Run DCF on the Financials tab first",
        "cockpit_fv_updated":           "Valuation updated (using the Financials tab DCF)",
        "cockpit_fv_enter_ticker":      "Enter a ticker to load",
        "p4_loading":                   "Loading...",
        "cockpit_fv_fcf_unavailable":   "FCF data unavailable",
        "p6_data_unavailable":          "Data unavailable",
        "cockpit_fv_debate_failed":     "AI debate did not run",
        # ── Anchor Intel v2.4: valuation diagnosis card ─────────────────────────
        "valdiag_header":               "🔬 Valuation Diagnosis",
        "valdiag_role":                 "Valuation role",
        "valdiag_role_informational":   "Informational",
        "valdiag_role_mid_term_supportive": "Mid-term supportive",
        "valdiag_role_long_term_eligible":  "Long-term eligible",
        "valdiag_consistency":          "Anchor consistency",
        "valdiag_consistency_consistent":     "Anchors agree",
        "valdiag_consistency_single_anchor":  "Single anchor only",
        "valdiag_consistency_irreconcilable": "Anchors irreconcilable",
        "valdiag_consistency_no_anchor":      "No valid anchor",
        "valdiag_outlier":              "Outlier",
        "valdiag_no_clear_outlier":     "no clear outlier",
        "valdiag_clustered":            "Clustered",
        "valdiag_peer_match":           "Peer match",
        "valdiag_peer_match_high":      "comparable peers sufficient",
        "valdiag_peer_match_low":       "insufficient comparable peers — peer multiple excluded",
        "valdiag_reason_insufficient_comparable_peers": "insufficient comparable peers",
        "valdiag_endorsed_range":       "Endorsed range",
        "valdiag_range_irreconcilable": "Range withheld (anchors disagree — shown separately)",
        "valdiag_range_unavailable":    "Range unavailable",
        "valdiag_applicable_methods":   "Applicable methods",
        "valdiag_rejected_methods":     "Rejected methods",
        "valdiag_reason_dcf_unavailable": "DCF unavailable",
        "valdiag_reason_excluded_anchor": "excluded",
        "valdiag_what_would_change":    "What would change this",
        "valdiag_cond_price_above_endorsed_range": "Price breaks above the endorsed range",
        "valdiag_cond_price_below_endorsed_range": "Price breaks below the endorsed range",
        "valdiag_cond_analyst_pool_migration_deteriorating": "Analyst pool migrating systematically lower",
        "valdiag_cond_met":             "triggered",
        "valdiag_cond_armed":           "not yet",
        "valdiag_narrative_pending":    "Narrative catalysts (margin guidance, etc.) — arriving in Phase 8",
        "valdiag_reverse_dcf_pending":  "Reverse DCF: Phase 8 pending",
        # ── Phase 6C-B: Trading Desk fair-value source badge ────────────────────
        "td_fair_value_source":         "Fair value source",
        "td_fv_src_app":                "app-computed",
        "td_fv_src_app_fair_value":     "app fair value",
        "td_fv_src_fixture":            "fixture",
        # ── Phase 6C-A: Trading Desk ─────────────────────────────────────────────
        "td_page_title":      "Trading Desk",
        "td_page_subtitle":   "The execution layer of the workflow: holdings monitor, order recommendations, opportunity watch. Research-only; not investment advice; no orders are placed and no broker is connected.",
        "td_safety_banner":   "For reference only — not investment advice. All orders must be placed manually with your broker; this page places no orders and connects to no broker.",
        # Section 1 — Holdings Monitor
        "td_sec1_header":     "Holdings Monitor",
        "td_add_position":    "Add Position",
        "td_no_holdings":     "No active holdings yet. Click “Add Position” to start tracking a thesis.",
        "td_refresh":         "Refresh Thesis Monitor",
        "td_monitor_running": "Running Thesis Monitor…",
        "td_last_refresh":    "Last refresh",
        "td_horizon":         "Horizon",
        "td_horizon_short":   "Short",
        "td_horizon_mid":     "Mid",
        "td_horizon_long":    "Long",
        "td_status_intact":   "Intact",
        "td_status_watch":    "Watch",
        "td_status_weakening":"Weakening",
        "td_status_broken":   "Broken",
        "td_pnl":             "P&L",
        "td_normal_pullback": "📉 Normal pullback, thesis intact",
        "td_edit":            "Edit",
        "td_save":            "Save",
        "td_close_position":  "Close Position",
        "td_closed_price":    "Closed price",
        "td_shares":          "Shares",
        "td_cost_basis":      "Cost basis (per share)",
        "td_entry_date":      "Entry date",
        "td_thesis_text":     "Thesis",
        "td_notes":           "Notes",
        "td_thesis_source":   "Thesis source",
        "td_thesis_signals":  "Thesis signals",
        "td_import_thesis":   "Import thesis from signal",
        "td_import_none":     "None (manual entry)",
        "td_ticker":          "Ticker",
        "td_add_btn":         "Add",
        "td_position_closed": "Closed",
        "td_key_development":  "Key development",
        "td_tech_warning":     "Technical breakdown",
        "td_macro_note":       "Macro signal",
        "td_cancel":           "Cancel",
        "td_filter_all":       "All",
        "td_filter_status":    "Thesis Status",
        "td_filter_horizon":   "Horizon",
        "td_col_price":        "Current Price",
        "td_col_status":       "Status",
        "td_col_alert":        "Alert",
        "td_col_action":       "Action",
        "td_no_match":         "No holdings match the current filters.",
        "td_cash_position_label": "Cash Position",
        "td_total_assets":     "Total Assets",
        "td_holdings_value":   "Holdings Value",
        "td_cash_ratio":       "Cash Ratio",
        "td_avg_cost":         "Avg Cost",
        "td_market_value":     "Market Value",
        "td_position_pct":     "Position %",
        "td_close_confirm_title": "Confirm Close",
        "td_close_shares":     "Shares to close",
        "td_close_proceeds":   "Estimated proceeds",
        "td_close_add_cash_q": "Add {amt} to your cash position?",
        "td_close_add_cash":   "Add to cash position",
        "td_yes":              "Yes",
        "td_no":               "No",
        "td_confirm":          "Confirm",
        # Section 2 — Order Recommendations
        "td_sec2_header":     "Order Recommendations",
        "td_sec2_subheader":  "For reference only. All orders must be placed manually.",
        "td_entry_zone":      "Entry zone",
        "td_stop_loss":       "Stop loss",
        "td_target":          "Target",
        "td_rr_ratio":        "R:R ratio",
        "td_position_size":   "Position size",
        "td_action_add":      "Add",
        "td_action_hold":     "Hold",
        "td_action_trim":     "Trim",
        "td_action_exit":     "Exit",
        "td_action_wait":     "Wait",
        "td_details":         "Details",
        "td_support":         "Support levels",
        "td_resistance":      "Resistance levels",
        "td_volume_trend":    "Volume trend",
        "td_atr":             "ATR(14)",
        "td_candlestick":     "Candlestick",
        "td_kelly_note":      "Kelly-lite sizing: win_rate 0.55, half-Kelly, clamped 2%–10%.",
        "td_broken_section":  "Holdings with broken thesis (exit recommendation only)",
        "td_risk_warning":    "Risk warning",
        "td_vol_increasing":  "Increasing",
        "td_vol_decreasing":  "Decreasing",
        "td_vol_neutral":     "Neutral",
        "td_data_live":       "LIVE",
        "td_data_fixture":    "FIXTURE",
        # Section 3 — Opportunity Watch
        "td_sec3_header":     "Opportunity Watch",
        "td_sec3_empty":      "No triple-signal opportunities yet. Run the Scanner to populate this.",
        "td_add_to_holdings": "Add to Holdings",
        "td_catalyst":        "Catalyst",
        "td_opp_in_zone":     "✅ Currently in entry zone",
        "td_opp_above_zone":  "⏳ Waiting for pullback",
        "td_opp_blocked":     "⛔ Entry conditions not met",
        "td_opp_below_zone":  "⚠️ Price below zone, wait for stabilization",
        # Phase 7A — unified five-state opportunity status (Cockpit + Trading Desk)
        "opp_status_actionable": "✅ Actionable Now",
        "opp_status_pullback":   "⏳ Wait for Pullback",
        "opp_status_breakout":   "🚀 Wait for Breakout",
        "opp_status_research":   "🔍 Research Required",
        "opp_status_avoid":      "⛔ Avoid Chasing",
        "opp_status_pending":    "(refresh to evaluate)",
        # Phase 7A — Opportunity Card panel
        "opp_panel_header":   "C · Opportunity Queue",
        "opp_panel_caption":  "A research queue sorted by horizon (\"worth 10 minutes of attention\") — review-only, not a buy list.",
        "opp_horizon_label":  "Horizon",
        "opp_horizon_short":  "Short",
        "opp_horizon_mid":    "Mid",
        "opp_horizon_long":   "Long",
        "opp_grade":          "Grade",
        "opp_setup":          "Setup",
        "opp_why_now":        "Why now",
        "opp_why_matters":    "Why it matters",
        "opp_blockers":       "Blockers",
        "opp_days_to_earnings": "To earnings",
        "opp_days":           "d",
        "opp_concentration_prefix": "Same underlying bet as ",
        "opp_pullback_support": "Pullback-to-Support (high quality)",
        "opp_none":           "No opportunities yet — click Refresh All first.",
        "opp_banner_header":  "Market context (applies to all candidates)",
        "opp_next_trigger":   "Waiting for",
        "opp_rs_degraded":    "Relative-strength data unavailable (treated as neutral)",
        "opp_rs_stale":       "Relative-strength data vintage lags (stale cache suspected)",
        # Phase 7A — setup type labels
        "opp_setup_momentum_breakout": "Momentum Breakout",
        "opp_setup_mid_rotation":      "Mid-term Rotation",
        "opp_setup_oversold_rebound":  "Oversold Rebound",
        "opp_setup_post_earnings":     "Post-earnings Reprice",
        "opp_setup_long_accum":        "Long-term Accumulation",
        "opp_setup_speculative":       "Speculative Watch",
        "td_actionable_header": "Actionable Signals",
        "td_signal_from_scanner": "Signal from Scanner",
        # Entry Strategy v3 — scenario / action / fields
        "td_scenario_initiate": "Initiate",
        "td_scenario_add":      "Add",
        "td_scenario_manage":   "Manage",
        "td_missing_conditions": "Conditions to meet",
        "td_next_trigger":      "Next trigger",
        "td_risk_note":         "Risk note",
        "td_fair_value_anchor": "Fair-value anchor",
        "td_act_wait":              "Wait",
        "td_act_hold":              "Hold",
        "td_act_enter_partial_now": "Enter partial now",
        "td_act_enter_on_pullback": "Enter on pullback",
        "td_act_enter_or_add_small": "Enter/add small",
        "td_act_add_small":         "Add small",
        "td_act_add_partial":       "Add partial",
        "td_act_add_tiny":          "Add tiny",
        "td_act_average_down_small": "Average down (small)",
        "td_act_average_down":      "Average down",
        "td_act_wait_for_pullback": "Wait for pullback",
        "td_act_wait_or_cut":       "Wait or cut",
        "td_act_reduce":            "Reduce",
        "td_act_reduce_or_exit":    "Reduce or exit",
        "td_act_cut_loss":          "Cut loss",
        "td_act_exit":              "Exit",
        "td_act_trim_or_stop_adding": "Trim / stop adding",
        "td_act_avoid":             "Avoid",
        # Entry Strategy v4 — portfolio settings + valuation confidence + risk overlay
        "td_portfolio_settings": "Portfolio Settings",
        "td_max_position_pct":   "Max position size",
        "td_short_max_loss":     "Short-term max loss",
        "td_mid_max_loss":       "Mid-term max loss",
        "td_long_stop_label":    "Long-horizon stop",
        "td_long_stop_value":    "Thesis break only",
        "td_save_settings":      "Save settings",
        "td_settings_saved":     "Settings saved",
        "td_valuation_confidence": "Valuation confidence",
        "td_conf_high":          "High confidence",
        "td_conf_medium":        "Medium confidence",
        "td_conf_low":           "Low confidence",
        "td_risk_overlay_note":  "Risk overlay",
        "td_weight_after_add":   "Weight after add",
        "td_blended_cost":       "Blended cost after add",
        # ── App home ─────────────────────────────────────────────────────────────
        "app_title":          "US Equity Research System",
        "app_subtitle":       "NYSE & NASDAQ | Powered by yfinance + polygon.io",
        "mktcap":             "Mkt Cap",
        "quick_nav":          "Quick Navigation",
        "nav_overview":       "🔭 Overview",
        "nav_financial":      "📊 Financials",
        "nav_pricevolume":    "📉 Price & Volume",
        "modules_title":      "Analysis Modules",
        "mod_overview_title": "Overview",
        "mod_overview_desc":  "Run full research pipeline, summarize all module conclusions",
        "mod_sector_title":   "Sector Research",
        "mod_sector_desc":    "ETF trends + custom peer comparison",
        "mod_scanner_title":  "Stock Scanner",
        "mod_scanner_desc":   "Custom watchlist momentum / value screening",
        "mod_equity_title":   "Equity Research",
        "mod_equity_desc":    "Business model, moat, competitive landscape deep-dive",
        "mod_fin_title":      "Financial Analysis",
        "mod_fin_desc":       "3-statement model, DCF valuation, peer comparison",
        "mod_pv_title":       "Price & Volume",
        "mod_pv_desc":        "Candlestick charts, technical indicators, pre/post market",
        "input_prompt":       "👈 Enter a ticker on the left (e.g. NVDA, AAPL, MSFT) to start",
        "data_source":        "Data: yfinance (primary) / polygon.io (fallback) | For research only, not investment advice",
        "loading_failed":     "Failed to load data. Please verify the ticker symbol.",
        # ── Common ───────────────────────────────────────────────────────────────
        "no_ticker":          "Enter a ticker on the left (e.g. NVDA, AAPL, MSFT) to begin",
        "employees":          "Employees",
        "download_report":    "⬇ Download Report",
        "mkt_cap":            "Mkt Cap",
        "gross_margin":       "Gross Margin",
        "revenue":            "Revenue",
        "net_income":         "Net Income",
        "free_cash_flow":     "Free Cash Flow",
        "above_sma200":       "Above SMA200",
        "from_52w_high":      "From 52W High",
        "vol_ratio_lbl":      "Vol Ratio (20D)",
        "analyst_rtg":        "Analyst Rating",
        "moat_rating":        "Moat Rating",
        "target_price":       "Price Target",
        # ── News ─────────────────────────────────────────────────────────────────
        "news_summary":       "Summary",
        # ── Page 1 ───────────────────────────────────────────────────────────────
        "p1_title":           "🔭 Overview — Full Research Pipeline",
        "p1_select_mods":     "Select Analysis Modules",
        "p1_mod_financial":   "📊 Financials",
        "p1_mod_technical":   "📉 Price & Volume",
        "p1_mod_equity":      "🏢 Equity Research",
        "p1_mod_earnings":    "📅 Earnings Calendar",
        "p1_run_all":         "▶ Run Full Research",
        "p1_click_run":       "Click「▶ Run Full Research」to start",
        "p1_metrics":         "Key Metrics",
        "p1_fin_snap":        "Financial Snapshot (TTM)",
        "p1_tech_snap":       "Technical Snapshot",
        "p1_equity_sum":      "Equity Research Summary",
        "p1_radar":           "📡 Comprehensive Radar",
        "p1_report":          "Comprehensive Report",
        "p1_overall":         "Overall Score",
        "p1_hover_hint":      "Hover over radar vertices to see scoring rationale",
        "p1_d_sector":        "Sector Momentum",
        "p1_d_health":        "Financial Health",
        "p1_d_valuation":     "Valuation Appeal",
        "p1_d_technical":     "Technical",
        "p1_d_business":      "Business Model",
        "p1_score_dim":       "Dimension",
        "p1_score_val":       "Score",
        "p1_score_note":      "Notes",
        # ── Page 2 ───────────────────────────────────────────────────────────────
        "p2_title":           "🏭 Sector Analysis",
        "p2_subtitle":        "GICS Sector Rotation · Thematic ETF Sub-Sectors · Intra-Sector Stock Ranking",
        "p2_etf":             "Select Sector ETF",
        "p2_period":          "Time Period",
        "p2_peers":           "Custom Comparison Tickers",
        "p2_peers_input":     "Enter tickers to compare (comma-separated); defaults to sector leaders",
        "p2_perf":            "Performance Summary",
        "p2_dl_csv":          "⬇ Download CSV",
        "p2_price_usd":       "Price (USD)",
        "p2_volume":          "Volume",
        "p2_norm_return":          "📊 Normalized Return (Base = 100)",
        "p2_insufficient":         "Not enough valid tickers. Please check the symbols.",
        # ── Page 2 v4: rotation ───────────────────────────────────────────────────
        "p2_heatmap":              "📊 Sector Heat Map",
        "p2_heatmap_subtitle":     "Composite score based on excess return, RSI, distance from 52W high, and volume. Higher = stronger momentum.",
        "p2_loading_scores":       "Computing sector scores...",
        "p2_select_sector":        "Select Sector",
        "p2_rotation_signal":      "🔄 Rotation Signal",
        "p2_od_panel":             "⚔️ Offense / Defense reading (multi-window)",
        "p2_od_reading":           "Reading",
        "p2_od_offense":           "offense",
        "p2_od_defense":           "defense",
        "p2_od_balanced":          "balanced",
        "p2_od_diff":              "Diff",
        "p2_od_window":            "Window",
        "p2_od_windows_confirm":   "windows confirm",
        "p2_od_unavailable":       "Offense/defense data unavailable",
        "p2_od_note":              "Offense basket vs defense basket (excess vs SPY, pp). Review-only.",
        "p2_market_style":         "Market Style",
        "p2_phase_risk_on":        "Risk-On",
        "p2_phase_risk_off":       "Risk-Off",
        "p2_phase_neutral":        "Neutral",
        "p2_top3":                 "Top 3 Sectors",
        "p2_accelerating":         "Accelerating Momentum",
        "p2_etf_trend":            "ETF Trend vs SPY",
        "p2_stock_ranking":        "Stock Ranking within Sector",
        "p2_loading_stocks":       "Loading constituents...",
        "p2_ranking_stocks":       "Ranking stocks...",
        "p2_no_constituents":      "Wikipedia data unavailable. Try selecting a sub-sector below, or check your internet connection.",
        "p2_constituents_found":   "constituents",
        "p2_ranking_top30":        "Showing top 30 by market cap",
        "p2_rank_failed":          "Ranking failed. Please try again.",
        "p2_leader":               "Leaders",
        "p2_challenger":           "Challengers",
        "p2_sleeper":              "Sleepers",
        "p2_send_scanner":         "Send to Scanner",
        "p2_subsector_drill":       "📑 Sub-sectors",
        "p2_no_subsectors":         "No thematic sub-sectors available for this sector.",
        "p2_select_subsector":      "Select Sub-Sector",
        "p2_custom_pool":           "Custom Pool",
        "p2_subsector_comparison":  "Sub-sector Comparison",
        # ── Page 2 — Macro / Volume / Valuation ──────────────────────────────────
        "p2_macro_title":     "Macro Environment",
        "p2_macro_vix":       "Fear Index VIX",
        "p2_macro_tnx":       "10Y Treasury Yield",
        "p2_macro_dxy":       "Dollar Index DXY",
        "p2_macro_spx":       "S&P 500",
        "p2_macro_5d":        "5D Change",
        "p2_macro_vix_fear":  "⚠️ Market fear, favor defensives",
        "p2_macro_vix_calm":  "✅ Low fear, favor growth",
        "p2_macro_vix_mid":   "Neutral sentiment",
        "p2_macro_tnx_up":    "📈 Rising rates, headwind for growth",
        "p2_macro_tnx_down":  "📉 Falling rates, tailwind for growth",
        "p2_macro_tnx_flat":  "Rates stable",
        "p2_macro_dxy_up":    "💵 Strong USD, headwind for commodities",
        "p2_macro_dxy_down":  "💵 Weak USD, tailwind for materials",
        "p2_macro_dxy_flat":  "Dollar stable",
        "p2_vol_flow":          "Volume Flow",
        "p2_vol_ratio":         "Vol Ratio",
        "p2_vol_breakout":      "Recent vol ratio > 1.5x breakout",
        "p2_vol_unavail":       "Volume data unavailable",
        "p2_vol_legend_active": "Active",
        "p2_vol_legend_others": "Others (click to show)",
        "p2_vol_click_hint":    "Top 3 sectors by volume ratio highlighted. Click legend to show/hide other sectors.",
        "p2_valuation":       "Sector Valuation (Median Fwd P/E)",
        "p2_val_loading":     "Computing sector valuations...",
        "p2_val_unavail":     "Valuation data unavailable",
        # ── Page 3 ───────────────────────────────────────────────────────────────
        "p3_title":           "🔍 Stock Scanner",
        "p3_subtitle":        "Screen a custom stock pool by strategy",
        "p3_pool":            "Custom Stock Pool",
        "p3_pool_input":      "Enter tickers (comma or newline separated)",
        "p3_pool_help":       "Defaults to top-20 S&P 500 tech stocks. Replace with any US tickers.",
        "p3_strategy":        "Screening Strategy",
        "p3_strat_lbl":       "Strategy",
        "p3_period":          "Data Period",
        "p3_top_n":           "Show Top N",
        "p3_run":             "▶ Run Scan",
        "p3_hits":            "Hits",
        "p3_avg3m":           "Avg 3M Return",
        "p3_avg_rsi":         "Avg RSI",
        "p3_dl_csv":          "⬇ Download CSV",
        "p3_dl_md":           "⬇ Download Report MD",
        "p3_no_result":       "No matches found. Try adjusting the strategy or stock pool.",
        "p3_start_hint":      "Configure settings then click「▶ Run Scan」",
        # ── Page 4 ───────────────────────────────────────────────────────────────
        "p4_title":           "🏢 Equity Research",
        "p4_moat":            "🏰 Moat Assessment",
        "p4_moat_hint":       "Auto-estimated from financials; adjust sliders manually",
        "p4_moat_rating":     "Overall Moat Rating",
        "p4_peers":           "📊 Peer Comparison",
        "p4_peer_input":      "Peer tickers (comma-separated)",
        "p4_peer_metric":     "Comparison Metric",
        "p4_loading_peers":   "Loading peer data...",
        "p4_biz":             "📖 Business Description",
        "p4_news":            "📰 Recent News & Sentiment",
        "p4_loading_news":    "Loading news...",
        "p4_news_count":      "News Count",
        "p4_news_avg":        "Avg Sentiment",
        "p4_news_dist":       "Sentiment Mix",
        "p4_filter":          "Filter News",
        "p4_all":             "All",
        "p4_pos":             "Positive",
        "p4_neu":             "Neutral",
        "p4_neg":             "Negative",
        "p4_sent_pos":        "Positive 🟢",
        "p4_sent_neg":        "Negative 🔴",
        "p4_sent_neu":        "Neutral ⚪",
        "p4_no_news_cat":     "No news in this sentiment category",
        "p4_last7d":          "Last 7 Days",
        "p4_report":          "📄 Research Report",
        "p4_view_md":         "View Full Report Markdown",
        # ── Page 5 ───────────────────────────────────────────────────────────────
        "p5_title":           "📊 Financial Analysis",
        "p5_tab1":            "📋 3-Statement",
        "p5_tab2":            "📐 Valuation",
        "p5_tab3":            "🔍 Quality Check",
        "p5_is":              "Income Stmt",
        "p5_bs":              "Balance Sheet",
        "p5_cf":              "Cash Flow",
        "p5_is_full":         "Income Statement",
        "p5_bs_full":         "Balance Sheet",
        "p5_cf_full":         "Cash Flow Statement",
        "p5_trend_metric":    "Chart Metric",
        "p5_margin_trend":    "Margin Trend",
        "p5_liq_ratio":       "Liquidity Ratios",
        "p5_cap_struct":      "Capital Structure ($B)",
        "p5_dcf":             "DCF Scenario Analysis",
        "p5_dcf_adj":         "Adjust DCF Parameters",
        "p5_fcf_b":           "Base FCF (B USD)",
        "p5_calc_dcf":        "Calculate DCF",
        "p5_rel_val":         "Relative Valuation",
        "p5_peer_val":        "Peer Tickers (comma-separated)",
        "p5_mult":            "Valuation Multiple",
        "p5_quality":         "FCF vs Net Income (Earnings Quality)",
        "p5_checklist":       "Financial Quality Checklist",
        "p5_qual_title":      "Net Income vs Operating CF vs FCF (B USD)",
        "p5_qual_ni":         "Net Income",
        "p5_qual_ocf":        "Operating CF",
        "p5_qual_fcf":        "FCF",
        "p5_qual_caption":    "If operating cash flow consistently lags net income, earnings quality may be in question.",
        "p5_chk_rev":         "Revenue Growth",
        "p5_chk_rev_note":    "% YoY",
        "p5_chk_gm":          "Gross Margin",
        "p5_chk_ocf":         "Operating CF > Net Income",
        "p5_chk_ocf_note":    "CF ${ocf}B vs NI ${ni}B",
        "p5_chk_gw":          "Goodwill/Total Assets",
        "p5_chk_gw_risk":     "(impairment risk)",
        "p5_no_data":         "Insufficient data to generate quality checklist",
        "p5_loading":         "Loading peer valuations...",
        # ── Page 6 ───────────────────────────────────────────────────────────────
        "p6_title":           "📉 Price & Volume",
        "p6_period":          "Time Period",
        "p6_indicator":       "Sub-Chart Indicator",
        "p6_pre":             "Pre-market",
        "p6_post":            "After-hours",
        "p6_key_levels":      "Key Price Levels",
        "p6_sma20_sup":       "SMA20 Support",
        "p6_sma50_sup":       "SMA50 Support",
        "p6_stop":            "Stop Loss (2xATR)",
        "p6_rr":              "Risk/Reward Ratio",
        "p6_rr_low":          "Unfavorable",
        "p6_rr_ok":           "Reasonable",
        # ── Page 6 indicator options ──────────────────────────────────────────────
        "p6_ind_bb":          "Bollinger Bands",
        # ── Scanner strategies ────────────────────────────────────────────────────
        "p3_strat_momentum":  "Momentum",
        "p3_strat_value":     "Value",
        "p3_strat_quality":   "Quality Growth",
        "p3_strat_oversold":  "Oversold Bounce",
        # ── Scanner column headers ────────────────────────────────────────────────
        "p3_col_company":     "Company",
        "p3_col_sector":      "Sector",
        "p3_col_price":       "Price($)",
        "p3_col_ret1m":       "1M Ret%",
        "p3_col_ret3m":       "3M Ret%",
        "p3_col_ret6m":       "6M Ret%",
        "p3_col_volratio":    "Vol Ratio(20D)",
        "p3_col_annvol":      "Ann. Vol%",
        "p3_col_mktcap":      "Mkt Cap(B)",
        # ── Moat slider labels ────────────────────────────────────────────────────
        "moat_intangibles":   "Intangibles (Brand/Patents)",
        "moat_switching":     "Switching Costs",
        "moat_network":       "Network Effects",
        "moat_cost_adv":      "Cost Advantage",
        "moat_eff_scale":     "Efficient Scale",
        "moat_wide":          "Wide",
        "moat_narrow":        "Narrow",
        "moat_none":          "None/Very Narrow",
        # ── Peer comparison metrics ───────────────────────────────────────────────
        "p4_peer_gm":         "GM%",
        "p4_peer_op":         "Op. Margin%",
        # ── News sentiment chart titles ───────────────────────────────────────────
        "p4_chart_hourly":    "Recent Sentiment (Hourly)",
        "p4_chart_daily":     "7-Day Avg Sentiment",
        "p4_no_finnhub":      "💡 Set the `FINNHUB_API_KEY` environment variable to enable news sentiment.\n\nSign up free: https://finnhub.io/register",
        "p4_no_news":         "No news data for the past 7 days",
        # ── Overview quality labels ───────────────────────────────────────────────
        "p1_qual_excel":      "Excellent",
        "p1_qual_neutral":    "Neutral",
        "p1_qual_caution":    "Caution",
        # ── Earnings banner labels ────────────────────────────────────────────────
        "earn_window_lbl":    "Earnings window",
        "earn_next_lbl":      "Next earnings",
        "earn_day_out":       "d out",
        "earn_day_ago":       "d ago",
        "earn_eps_est":       "EPS est.",
        "earn_last_surp":     "Last EPS surprise",
        "earn_just_rel":      "🗓️ Earnings just released",
        "p1_rpt_gen_err":     "Report generation error",
        # ── Financial metric names ────────────────────────────────────────────────
        "fin_total_revenue":  "Total Revenue",
        "fin_gross_profit":   "Gross Profit",
        "fin_op_income":      "Operating Income",
        "fin_net_income":     "Net Income",
        "fin_basic_eps":      "Basic EPS",
        "fin_diluted_eps":    "Diluted EPS",
        # ── Workflow status bar ───────────────────────────────────────────────────
        "wf_status_running":    "Workflow running",
        "wf_status_done":       "Workflow completed",
        "wf_sector_lbl":        "Sector",
        "wf_ticker_lbl":        "Ticker",
        "wf_fork_btn":          "Fork from here",
        "wf_back_btn":          "↩ Overview",
        "wf_forked":            "Forked",
        # ── Overview workflow control center ──────────────────────────────────────
        "p1_wf_sector_lbl":  "Target Sector",
        "p1_wf_ticker_lbl":  "Target Ticker",
        "p1_wf_start":       "▶ Start Full Workflow",
        "p1_wf_new":         "🔄 New Workflow",
        "p1_wf_done":        "✅ Workflow Complete",
        "p1_wf_running":     "Workflow in Progress",
        "p1_wf_idle_hint":   "Select a sector and ticker, then launch the full research pipeline",
        "p1_step1_name":     "① Sector Analysis",
        "p1_step2_name":     "② Stock Scanner",
        "p1_step3_name":     "③ Equity Research",
        "p1_step4_name":     "④ Financial Analysis",
        "p1_step5_name":     "⑤ Price & Volume",
        "p1_view_sector":    "View Sector →",
        "p1_view_scanner":   "View Scanner →",
        "p1_view_equity":    "View Equity →",
        "p1_step_pending":   "Pending",
        "p1_step_running":   "Running...",
        "p1_step_done":      "Done",
        "p1_step_failed":    "Failed",
        "p1_no_ticker_wf":   "Please enter a target ticker symbol",
        # ── Equity page tabs ──────────────────────────────────────────────────────
        "p4_tab_overview":      "Overview",
        "p4_tab_financial":     "Financials",
        "p4_tab_pv":            "Price & Volume",
        "p4_tab_news":          "News & Sentiment",
        # ── Redirect pages ────────────────────────────────────────────────────────
        "redirect_financial":   "Financial Analysis has been merged into **Equity Research**.",
        "redirect_pv":          "Price & Volume has been merged into **Equity Research**.",
        "redirect_goto":        "Go to Equity Research →",
        # ── Column name translation map (ZH→EN, applied by render_table) ─────────
        "column_names": {
            # General
            "公司": "Company", "行业": "Sector", "价格($)": "Price($)",
            "市值": "Mkt Cap", "指标": "Metric", "数值": "Value",
            "维度": "Dimension", "评分": "Score", "说明": "Notes",
            # Financial statements
            "营业收入": "Total Revenue", "毛利润": "Gross Profit",
            "营业利润": "Operating Income", "净利润": "Net Income",
            "基本EPS": "Basic EPS", "摊薄EPS": "Diluted EPS",
            "总资产": "Total Assets", "股东权益": "Stockholders Equity",
            "总负债": "Total Liabilities", "总债务": "Total Debt",
            "现金及等价物": "Cash & Equivalents", "商誉": "Goodwill",
            "流动资产": "Current Assets", "流动负债": "Current Liabilities",
            "经营现金流": "Operating CF", "资本支出": "CapEx",
            "自由现金流": "Free Cash Flow",
            "股票回购": "Share Buybacks", "股息支付": "Dividends Paid",
            # Quality check
            "营收增长": "Revenue Growth", "毛利率": "Gross Margin",
            "经营现金流>净利润": "Op. CF > Net Income",
            "商誉/总资产": "Goodwill/Assets",
            # Peer / scanner
            "1M回报%": "1M Ret%", "3M回报%": "3M Ret%", "6M回报%": "6M Ret%",
            "量比(20D)": "Vol Ratio(20D)", "年化波动%": "Ann. Vol%",
            "远期P/E": "Fwd P/E", "市值(B)": "Mkt Cap(B)",
            "距52周高%": "52W High%",
        },
        # ── Phase 5H.1: Investment Cockpit ───────────────────────────────────────
        "nav_p7":                          "🧭 Investment Cockpit",
        "cockpit_page_title":              "Investment Cockpit — v0.2 Demo Preview (Opportunity-first)",
        "cockpit_page_subtitle":           "Fixture/demo-only, opportunity-first v0.2 preview of the Investment Cockpit overlay. Review-only; no live wiring, no external API, no orders.",
        "cockpit_scenario_select_label":   "Scenario (fixture/demo only)",
        "cockpit_scenario_select_help":    "Choose which Phase 5G fixture scenario to preview. 'complete' = FIXTKR (all data present). 'degraded' = FIXDEG (missing financial step + missing long-horizon thesis + no_trade option overlay).",
        "cockpit_sidebar_pack_id":         "Pack ID:",
        "cockpit_sidebar_scenario_id":     "Scenario ID:",
        "cockpit_sidebar_data_source":     "Data source: Phase 5G fixture demo pack only. No live wiring.",
        # Safety banner
        "cockpit_safety_headline":         "Investment Cockpit Preview — fixture/demo only, not investment advice.",
        "cockpit_safety_b1":               "Fixture/demo only — no live workflow wiring.",
        "cockpit_safety_b2":               "No external API, LLM, broker, or order routing is called.",
        "cockpit_safety_b3":               "No reads of research/.workflow_state.json.",
        "cockpit_safety_b4":               "No orders, order tickets, broker payloads, or executable instructions.",
        "cockpit_safety_b5":               "approved_for_execution is False (or absent) everywhere it appears.",
        "cockpit_safety_b6":               "Not investment advice. Human review required before any real-world action.",
        "cockpit_safety_pack_caption":     "Pack-level safety banner (Phase 5G)",
        "cockpit_safety_scenario_caption": "Scenario-level safety banner (Phase 5G)",
        # Tabs
        "cockpit_tab_overview":            "Overview / Safety",
        "cockpit_tab_company":             "Company Research Hub",
        "cockpit_tab_horizon":             "Horizon Cards",
        "cockpit_tab_thesis":              "ThesisTracker",
        "cockpit_tab_portfolio":           "Portfolio / TradePlan",
        "cockpit_tab_option":              "Option Overlay",
        "cockpit_tab_feedback":            "Feedback / Agent Evaluation",
        "cockpit_tab_provenance":          "Provenance / Diagnostics",
        # Overview
        "cockpit_overview_scenario_kind":  "Scenario kind",
        "cockpit_overview_ticker":         "Ticker (fixture)",
        "cockpit_overview_runid":          "Run ID",
        "cockpit_overview_no_desc":        "(no scenario description)",
        "cockpit_overview_warnings":       "Scenario warnings (fixture-only):",
        # Company Research Hub
        "cockpit_company_target":          "Target",
        "cockpit_company_run_id":          "Run ID",
        "cockpit_company_as_of":           "As of",
        "cockpit_company_workflow":        "Workflow",
        "cockpit_company_missing_data":    "Missing-data warnings (degraded scenario panels):",
        "cockpit_company_panel_equity":    "Equity research panel",
        "cockpit_company_panel_financial": "Financial / valuation panel",
        "cockpit_company_panel_pv":        "Price / volume timing panel",
        "cockpit_company_financial_missing": "Financial panel is missing — fixture/demo degraded scenario. No analysis is regenerated.",
        "cockpit_company_expander_source": "Source workflow panel (fixture references)",
        "cockpit_company_expander_evidence": "Evidence coverage panel",
        "cockpit_company_expander_validation": "Validation status panel",
        "cockpit_company_synthesis_present":  "Synthesis present",
        "cockpit_company_synthesis_status":   "Synthesis status",
        "cockpit_company_present_steps":      "Present steps",
        "cockpit_company_missing_steps":      "Missing steps",
        "cockpit_company_synthesis_no_summary": "(no synthesis summary)",
        "cockpit_company_total_evidence":     "Total evidence IDs",
        "cockpit_company_total_records":      "Total memory records",
        "cockpit_company_complete_coverage":  "Complete step coverage",
        "cockpit_company_inspected":          "Inspected records",
        "cockpit_company_blocked":            "Blocked",
        "cockpit_company_needs_review":       "Needs review",
        "cockpit_company_validation_signal":  "Has any validation signal",
        "cockpit_company_is_clean":           "Is clean",
        # Common
        "cockpit_common_populated":        "Populated",
        "cockpit_common_status":           "Status",
        "cockpit_common_no_summary":       "(no summary)",
        "cockpit_common_direction":        "Direction",
        "cockpit_common_confidence":       "Confidence",
        # Horizon cards
        "cockpit_horizon_caption":         "Cards are emitted in canonical short → medium → long order. Missing cards remain visible as safe degraded slots.",
        "cockpit_horizon_horizon":         "Horizon",
        "cockpit_horizon_no_thesis":       "No thesis available for this horizon — safe degraded card (fixture/demo).",
        "cockpit_horizon_review_needed":   "Review-needed badge — reasons:",
        "cockpit_horizon_missing_evidence": "Missing-evidence badge — missing kinds:",
        "cockpit_horizon_no_thesis_record": "(no thesis record present in the fixture)",
        "cockpit_horizon_no_text":         "(no thesis text)",
        "cockpit_horizon_assumptions":     "Assumptions",
        "cockpit_horizon_invalidation":    "Invalidation triggers",
        "cockpit_horizon_next_action":     "Next action label (descriptive, non-executive):",
        "cockpit_horizon_view_warnings":   "View-level warnings:",
        # ThesisTracker
        "cockpit_thesis_caption":          "ThesisTracker rows by (ticker, horizon). Rows are deterministic and never fabricated.",
        "cockpit_thesis_no_rows":          "No tracker rows in this fixture scenario.",
        "cockpit_thesis_warnings":         "Tracker-level warnings:",
        # Portfolio
        "cockpit_portfolio_alloc_summary": "Allocation summary for",
        "cockpit_portfolio_records":       "Records",
        "cockpit_portfolio_blocked":       "Blocked",
        "cockpit_portfolio_needs_review":  "Needs review",
        "cockpit_portfolio_reviewed":      "Reviewed",
        "cockpit_portfolio_risk_budget":   "Risk budget",
        "cockpit_portfolio_cash_impact":   "Cash impact",
        "cockpit_portfolio_no_risk_budget": "No risk budget data in fixture.",
        "cockpit_portfolio_no_cash_impact": "No cash impact data in fixture.",
        "cockpit_portfolio_positions":     "Positions (fixture)",
        "cockpit_portfolio_trade_plans":   "Trade plans (fixture, non-executable)",
        "cockpit_portfolio_no_trade_plans": "No trade plans in fixture scenario.",
        "cockpit_portfolio_trade_plan_for": "Trade plan for",
        "cockpit_portfolio_action":        "action",
        "cockpit_portfolio_status":        "status",
        "cockpit_portfolio_review_trigger": "Review trigger — reasons:",
        "cockpit_portfolio_no_rationale":  "(no rationale)",
        "cockpit_portfolio_no_levels":     "No trade-plan levels populated in the fixture record.",
        "cockpit_portfolio_missing_data":  "Missing-data warnings:",
        # Option overlay
        "cockpit_option_no_record":        "No option overlay record in this fixture scenario.",
        "cockpit_option_overlay_for":      "Option overlay for",
        "cockpit_option_state":            "state",
        "cockpit_option_status":           "status",
        "cockpit_option_no_trade_msg":     "Option overlay reports `no_trade` (first-class state). Phase 5H never infers a substitute strategy.",
        "cockpit_option_no_trade_reason": "No-trade reason:",
        "cockpit_option_review_trigger":   "Review trigger:",
        "cockpit_option_strategy_summary": "Strategy summary",
        "cockpit_option_decision":         "Decision",
        "cockpit_option_strategy_type":    "Strategy type",
        "cockpit_option_expiration":       "Expiration",
        "cockpit_option_contracts":        "Contracts (fixture)",
        "cockpit_option_exit_rule":        "Planned exit rule",
        "cockpit_option_risk_level":       "Risk level",
        "cockpit_option_rr":               "Risk / reward (fixture)",
        "cockpit_option_max_loss":         "Max loss",
        "cockpit_option_max_gain":         "Max gain",
        "cockpit_option_breakeven":        "Breakeven",
        "cockpit_option_entry_iv":         "Entry IV",
        "cockpit_option_entry_underlying": "Entry underlying price",
        "cockpit_option_cash_required":    "Cash required",
        "cockpit_option_rr_ratio":         "Risk/reward ratio",
        "cockpit_option_liquidity":        "Liquidity warnings (from fixture):",
        "cockpit_option_event_risk":       "Event-risk warnings (from fixture):",
        # Feedback / Agent evaluation
        "cockpit_feedback_caption":        "Review-only summary of fixture-backed human feedback and agent evaluation records.",
        "cockpit_feedback_human":          "Human feedback (fixture)",
        "cockpit_feedback_agent":          "Agent evaluation (fixture)",
        "cockpit_feedback_no_human":       "No human feedback records in this scenario.",
        "cockpit_feedback_no_agent":       "No agent evaluation records in this scenario.",
        "cockpit_feedback_memory_id":      "Memory ID:",
        "cockpit_feedback_target":         "Target:",
        "cockpit_feedback_outcome":        "Outcome:",
        "cockpit_feedback_record_id":      "Record ID:",
        "cockpit_feedback_agent_type":     "Agent type:",
        "cockpit_feedback_lesson":         "Lesson:",
        "cockpit_feedback_entries_suffix": "feedback entry(ies)",
        "cockpit_feedback_signals_suffix": "signal(s)",
        # Provenance / Diagnostics
        "cockpit_provenance_caption":      "Demo-only provenance. This is NOT live workflow output. The fixture demo pack is the only data source for this preview page.",
        "cockpit_provenance_pack_level":   "Pack-level provenance",
        "cockpit_provenance_scenario_level": "Scenario-level provenance",
        "cockpit_provenance_validation":   "Validation / demo summary",
        "cockpit_provenance_source":       "Source fixture: `lib/reliability/phase5_demo_pack.py` (Phase 5G default demo pack).",
        "cockpit_provenance_not_live":     "This page does not read live workflow output and does not call any live API.",
        # Fail-closed
        "cockpit_failclosed_headline":     "Failed to build the Phase 5G fixture demo pack. The cockpit preview cannot be displayed.",
        "cockpit_failclosed_no_detail":    "(no error detail)",
        "cockpit_failclosed_note":         "Fail-closed: no fallback to live workflow, LLM, or external API. Fix the demo pack builder and retry.",
        "cockpit_no_scenarios":            "No scenarios available in the Phase 5G demo pack.",
        # --- Phase 5N v0.2 (opportunity-first redesign) ---
        # New tabs
        "cockpit_tab_themes":              "Market Themes",
        "cockpit_tab_opportunity":         "Opportunity Queue",
        "cockpit_tab_decision":            "Decision Workspace",
        "cockpit_tab_research":            "Research Snapshot",
        "cockpit_tab_debate":              "Agent Debate",
        "cockpit_tab_trade":               "Trade / Allocation Plan",
        "cockpit_tab_review":              "Feedback / Review",
        # Overview v0.2
        "cockpit_overview_v02_preview":    "Opportunity-first v0.2 preview — fixture/demo only, no live workflow wiring, no external API, no broker/order/execution, not investment advice. approved_for_execution is False (or absent) everywhere.",
        "cockpit_overview_flow_header":    "Cockpit flow",
        "cockpit_overview_flow":           "Market Themes → Opportunity Queue → Research Pack → Agent Debate → Decision Workspace → Review.",
        # Phase 5R — demo walkthrough / how to read this page
        "cockpit_walkthrough_header":      "How to read this page (demo walkthrough)",
        "cockpit_walkthrough_intro":       "This is an opportunity-first, horizon-aware research cockpit demo. All data is deterministic fixtures; read the tabs in this order:",
        "cockpit_walkthrough_step1":       "Market Themes — market-level heat & lifecycle context (heat is NOT a buy signal).",
        "cockpit_walkthrough_step2":       "Opportunity Queue — horizon-aware candidates ranked by opportunity fit.",
        "cockpit_walkthrough_step3":       "Research Pack / Snapshot — the source research modules a candidate would draw on (descriptive only).",
        "cockpit_walkthrough_step4":       "Agent Debate — bull / bear / risk / critic perspectives; conflicts stay visible and are never hidden.",
        "cockpit_walkthrough_step5":       "Decision Workspace — review-only status; requires human review and never executes.",
        "cockpit_walkthrough_step6":       "Feedback / Review — record session-only review notes; nothing is persisted.",
        "cockpit_walkthrough_safety":      "Fixture/demo only · review-only · non-executable · no live workflow, LLM, external API, broker, or order. Not investment advice.",
        # Market Themes (Phase 5J)
        "cockpit_themes_caption":          "Fixture-backed theme intelligence / market heat (Phase 5J). Themes are market-level context, not tickers.",
        "cockpit_themes_heat_not_buy":     "Theme heat score is NOT a buy signal and is not entry quality.",
        "cockpit_themes_lifecycle":        "Lifecycle stage",
        "cockpit_themes_heat_status":      "Heat status",
        "cockpit_themes_heat_score":       "Heat score",
        "cockpit_themes_candidates":       "Candidate tickers",
        "cockpit_themes_subthemes":        "Subthemes",
        "cockpit_themes_chain_nodes":      "Industry-chain nodes",
        "cockpit_themes_warnings":         "Theme risk / crowding warnings (fixture):",
        "cockpit_themes_chain_decomposition": "Industry-chain decomposition",
        "cockpit_themes_candidate_tickers": "Candidate tickers (fixture)",
        "cockpit_themes_theme_count":      "Themes",
        "cockpit_themes_subtheme_count":   "Subthemes",
        "cockpit_themes_chain_node_count": "Chain nodes",
        "cockpit_themes_candidate_count":  "Candidates",
        "cockpit_themes_no_themes":        "No themes in this fixture snapshot (safe empty universe).",
        # Opportunity Queue (Phase 5K)
        "cockpit_opportunity_caption":     "Horizon-aware opportunity queue (Phase 5K). The same ticker can appear across horizons with different decision labels.",
        "cockpit_opportunity_heat_not_trade": "High theme heat does NOT automatically imply trade_now. Crowding can downgrade an idea to wait / avoid.",
        "cockpit_opportunity_horizon_queues": "Horizon queues",
        "cockpit_opportunity_cross_cutting": "Cross-cutting queues",
        "cockpit_opportunity_short_term":  "Short-term trade",
        "cockpit_opportunity_mid_term":    "Mid-term position",
        "cockpit_opportunity_long_term":   "Long-term investment",
        "cockpit_opportunity_watch_wait":  "Watch / wait",
        "cockpit_opportunity_research_more": "Research more",
        "cockpit_opportunity_no_trade":    "No trade / avoid",
        "cockpit_opportunity_no_candidates": "No candidates in this queue.",
        "cockpit_opportunity_decision":    "Decision",
        "cockpit_opportunity_horizon":     "Horizon",
        "cockpit_opportunity_score":       "Opportunity score",
        "cockpit_opportunity_horizon_fit": "Horizon fit",
        "cockpit_opportunity_entry_quality": "Entry quality",
        "cockpit_opportunity_crowding":    "Crowding risk",
        "cockpit_opportunity_next_action": "Next action:",
        "cockpit_opportunity_theme":       "Theme",
        "cockpit_opportunity_cross_horizon": "Cross-horizon comparison",
        "cockpit_opportunity_cross_horizon_caption": "Same ticker, different decision by horizon (fixture).",
        "cockpit_opportunity_warnings":    "Queue-level warnings:",
        # Decision Workspace (Phase 5M)
        "cockpit_decision_caption":        "Review-only decision workspace (Phase 5M). The bridge between research pack and a human-reviewed decision state.",
        "cockpit_decision_for":            "Decision workspace for",
        "cockpit_decision_status":         "Status",
        "cockpit_decision_decision_label": "Decision label",
        "cockpit_decision_next_action":    "Review-only next action",
        "cockpit_decision_review_only":    "Review-only: this workspace is not an executable decision and requires human review.",
        "cockpit_decision_recommendation_state": "Recommendation / review state",
        "cockpit_decision_consensus":      "Consensus",
        "cockpit_decision_supporting_roles": "Supporting roles",
        "cockpit_decision_dissenting_roles": "Dissenting roles",
        "cockpit_decision_evidence_coverage": "Evidence coverage",
        "cockpit_decision_conflicts":      "Unresolved conflicts",
        "cockpit_decision_no_conflicts":   "No conflicts recorded.",
        "cockpit_decision_no_views":       "No decision workspace views in this fixture.",
        "cockpit_decision_warnings":       "Workspace warnings:",
        # Research Snapshot (Phase 5B / 5C / 5L)
        "cockpit_research_caption":        "Company Research Snapshot — summarizes source research-module outputs; it does not replace or regenerate the original Equity Research.",
        "cockpit_research_thesis_header":  "Horizon thesis snapshot (source output)",
        "cockpit_research_pack_header":    "Research pack module coverage (Phase 5L, descriptive)",
        "cockpit_research_pack_status":    "Research pack status",
        "cockpit_research_pack_required_modules": "required modules",
        # Agent Debate (Phase 5M)
        "cockpit_debate_caption":          "Fixture-backed agent debate (Phase 5M). Role records only — no live agent is run.",
        "cockpit_debate_session_for":      "Debate session for",
        "cockpit_debate_participants":     "Participants",
        "cockpit_debate_stances":          "Stances",
        "cockpit_debate_stance":           "stance",
        "cockpit_debate_confidence":       "confidence",
        "cockpit_debate_key_claims":       "Key claims:",
        "cockpit_debate_risks":            "Risks:",
        "cockpit_debate_missing_evidence": "Missing evidence:",
        "cockpit_debate_invalidation":     "Invalidation conditions:",
        "cockpit_debate_review_triggers":  "Review triggers:",
        "cockpit_debate_critic":           "Critic review",
        "cockpit_debate_critic_ack":       "Acknowledged conflicts:",
        "cockpit_debate_allocation":       "Allocation perspective",
        "cockpit_debate_option":           "Option perspective",
        "cockpit_debate_alloc_non_exec":   "Allocation perspective is review-only and non-executable.",
        "cockpit_debate_option_non_exec":  "Option perspective is review-only and non-executable.",
        "cockpit_debate_conflicts":        "Conflicts",
        "cockpit_debate_no_conflicts":     "No conflicts recorded.",
        "cockpit_debate_no_sessions":      "No debate sessions in this fixture.",
        # Trade / Allocation Plan (Phase 5D)
        "cockpit_trade_caption":           "Review-only portfolio / trade plan (Phase 5D), placed after the decision workspace and debate.",
        "cockpit_trade_boundary":          "Review-only planning view — not an order ticket.",
        "cockpit_trade_non_executable":    "Non-executable",
        "cockpit_trade_requires_review":   "Requires human review",
        "cockpit_trade_max_risk_budget":   "Max risk budget %",
        "cockpit_trade_max_portfolio_loss": "Max portfolio loss %",
        "cockpit_trade_risk_counts":       "High / medium / low / unknown risk counts",
        "cockpit_trade_total_cash_impact": "Total cash impact",
        "cockpit_trade_min_cash":          "Min projected cash %",
        "cockpit_trade_max_cash":          "Max projected cash %",
        "cockpit_trade_col_target":        "Target",
        "cockpit_trade_col_horizon":       "Horizon",
        "cockpit_trade_col_action":        "Action",
        "cockpit_trade_col_status":        "Status",
        "cockpit_trade_col_target_alloc":  "Target alloc %",
        "cockpit_trade_col_actual_alloc":  "Actual alloc %",
        "cockpit_trade_col_review_needed": "Review needed",
        "cockpit_trade_col_kind":          "Kind",
        "cockpit_trade_col_label":         "Label",
        "cockpit_trade_col_pct":           "Pct",
        "cockpit_trade_col_value":         "Value",
        "cockpit_trade_col_note":          "Note",
        # Option Overlay v0.2
        "cockpit_option_caption_v02":      "Review-only option overlay (Phase 5D). no_trade is first-class; no substitute strategy is inferred; no execution.",
        # Feedback / Review v0.2
        "cockpit_review_caption":          "Review-only summary of fixture-backed human feedback and agent evaluation records. No real feedback persistence yet.",
        "cockpit_review_actions":          "Review-only action labels are surfaced from fixtures; nothing is submitted or persisted.",
        # ── Phase 5Q: Human Feedback UI v0.1 (session-only / non-persistent / non-executable) ──
        "cockpit_review_hf_safety_headline": "Human feedback — session-only, not persisted. No broker/order/execution; not investment advice.",
        "cockpit_review_hf_safety_b1":     "Session-only — feedback lives only in this browser session and is lost on refresh/close.",
        "cockpit_review_hf_safety_b2":     "Not persisted — nothing is written to disk, database, vector store, or workflow state.",
        "cockpit_review_hf_safety_b3":     "No broker / order / execution.",
        "cockpit_review_hf_safety_b4":     "No LLM and no external API call.",
        "cockpit_review_hf_safety_b5":     "approved_for_execution is always False (or absent); not investment advice.",
        "cockpit_review_hf_form_header":   "Record review feedback (session-only)",
        "cockpit_review_hf_no_targets":    "No reviewable targets in this fixture.",
        "cockpit_review_hf_kind_label":    "Target kind",
        "cockpit_review_hf_target_label":  "Review target",
        "cockpit_review_hf_target_help":   "Choose the fixture target to attach review feedback to: opportunity candidate / horizon / decision workspace / option overlay.",
        "cockpit_review_hf_action_label":  "Review action (review-only, non-executable)",
        "cockpit_review_hf_note_label":    "Note (optional)",
        "cockpit_review_hf_note_ph":       "Optional review rationale or thesis-modification note…",
        "cockpit_review_hf_non_exec_note": "All actions are review-only review intents; nothing triggers an order or execution, and nothing is persisted.",
        "cockpit_review_hf_add_button":    "Add to session preview",
        "cockpit_review_hf_clear_button":  "Clear session feedback",
        "cockpit_review_hf_preview_header": "Session feedback preview (session-only)",
        "cockpit_review_hf_preview_note":  "The items below live only in this session — not persisted, not executable.",
        "cockpit_review_hf_preview_empty": "No feedback recorded in this session yet.",
        "cockpit_review_hf_preview_count": "{n} session-only feedback item(s) recorded this session (not persisted).",
        "cockpit_review_hf_col_kind":      "Target kind",
        "cockpit_review_hf_col_target":    "Target",
        "cockpit_review_hf_col_action":    "Action",
        "cockpit_review_hf_col_note":      "Note",
        "cockpit_review_hf_bind_kind":     "Target kind",
        "cockpit_review_hf_bind_ticker":   "Ticker",
        "cockpit_review_hf_bind_horizon":  "Horizon",
        "cockpit_review_hf_fixture_header": "Fixture-backed human feedback / agent evaluation records (read-only)",
        # Review action labels
        "cockpit_review_action_accept_for_watchlist":             "Accept for watchlist",
        "cockpit_review_action_reject":                           "Reject",
        "cockpit_review_action_modify_thesis":                    "Modify thesis",
        "cockpit_review_action_request_more_research":            "Request more research",
        "cockpit_review_action_wait_for_pullback":                "Wait for pullback",
        "cockpit_review_action_manually_executed_outside_system": "Manually executed outside system (label only)",
        "cockpit_review_action_skip":                             "Skip",
        "cockpit_review_action_review_later":                     "Review later",
        "cockpit_review_action_no_trade_confirmed":               "No-trade confirmed",
        # Provenance / Diagnostics v0.2
        "cockpit_provenance_no_api":       "No external API, no LLM. This is not live workflow output.",
        "cockpit_provenance_intel_validation": "Phase 5J / 5K / 5L / 5M validation summaries",
        # ── Phase 5O: Macro Dashboard v0.1 ───────────────────────────────────────
        "macro_page_title":                "Macro Dashboard",
        "macro_page_subtitle":             "A live overview of macro conditions and the market regime.",
        # Phase 6A — Overview intro page (user-facing)
        "macro_banner_live":               "Live data mode — showing data that reflects today's market.",
        "macro_banner_degraded":           "Some data is unavailable; showing demo data as a fallback.",
        "macro_ov_state":                  "Current market state",
        "macro_ov_dimensions":             "What this page covers",
        "macro_ov_dim_rates":              "Rates — read the monetary backdrop and duration pressure.",
        "macro_ov_dim_credit":             "Credit — gauge credit risk and market stress.",
        "macro_ov_dim_vol":                "Volatility — market sentiment and risk aversion.",
        "macro_ov_dim_etf":                "ETF returns — cross-asset and sector relative performance.",
        "macro_ov_dim_econ":               "Economic releases — latest jobs and inflation trends.",
        "macro_ov_dim_sentiment":          "Market sentiment — aggregate fear/greed and news tone.",
        "macro_ov_sources":                "Data sources & update frequency",
        "macro_ov_sources_desc":           "Data comes from public market quotes and official macro statistics, refreshed about every 15 minutes.",
        # Phase 5R — demo walkthrough / how to read this page
        "macro_walkthrough_header":        "How to read this page (demo walkthrough)",
        "macro_walkthrough_intro":         "This page provides macro-first upstream context for the Investment Cockpit. All data is deterministic fixtures; read the tabs in this order:",
        "macro_walkthrough_step1":         "Macro Regime — the deterministic risk-on / risk-off / transition backdrop and its factors.",
        "macro_walkthrough_step2":         "Macro Indicators — fixture commodities, risk-appetite / leadership, and economic releases.",
        "macro_walkthrough_step3":         "Horizon Bias — how the regime tilts short / mid / long-term posture.",
        "macro_walkthrough_step4":         "Theme Implications — which themes the regime favors or pressures (context, not a live market claim).",
        "macro_walkthrough_step5":         "Opportunity Posture — the resulting review-only posture; never a final buy/sell decision.",
        "macro_walkthrough_safety":        "Fixture/demo only · macro-first context · review-only · no live macro/external API, LLM, broker, or order. Not investment advice.",
        "macro_scenario_select_label":     "Macro scenario (demo/fixture)",
        "macro_scenario_select_help":      "Choose a deterministic macro fixture scenario to preview: risk_on / risk_off / transition / degraded (unknown). All are offline fixture data.",
        "macro_sidebar_dashboard_id":      "Dashboard ID:",
        "macro_sidebar_data_source":       "Data source: Phase 5O deterministic fixtures only — no live macro / external wiring.",
        # Safety banner
        "macro_safety_headline":           "For research and educational purposes only — not investment advice.",
        "macro_safety_b1":                 "Fixture/demo only — no live macro data wiring.",
        "macro_safety_b2":                 "No live macro API is called.",
        "macro_safety_b3":                 "No external API is called.",
        "macro_safety_b4":                 "No LLM is called.",
        "macro_safety_b5":                 "No broker / order / execution capability.",
        "macro_safety_b6":                 "approved_for_execution is False (or absent) everywhere; not investment advice.",
        # Tabs
        "macro_tab_overview":              "Overview",
        "macro_tab_regime":                "Macro Regime",
        "macro_tab_liquidity":             "Rates & Liquidity",
        "macro_tab_credit":                "Credit & Volatility",
        "macro_tab_risk":                  "Market Sentiment",
        "macro_tab_horizon":               "Horizon Bias",
        "macro_tab_themes":                "Theme Implications",
        "macro_tab_posture":               "Opportunity Posture",
        "macro_tab_provenance":            "Data Sources",
        # Overview
        "macro_overview_caption":          "Macro regime is a first-class upstream input to opportunity selection: it influences whether the Cockpit favors momentum trades, pullback entries, watchlist-only, risk reduction, or long-term accumulation.",
        "macro_overview_first_class":      "Why macro is first-class: read the regime before screening opportunities. Macro is context — it does not produce a final buy/sell decision.",
        "macro_overview_regime_status":    "Macro regime status",
        "macro_overview_confidence":       "Confidence",
        "macro_overview_as_of":            "As of",
        "macro_overview_scenario_kind":    "Scenario kind",
        "macro_overview_warnings":         "Macro warnings (fixture only):",
        # Regime
        "macro_regime_caption":            "Deterministic macro regime snapshot (fixture). All values are placeholder descriptors — not live computation and not live data.",
        "macro_regime_primary":            "Primary regime status",
        "macro_regime_supporting":         "Supporting statuses",
        "macro_regime_no_factors":         "No macro factors in this fixture snapshot (safe empty / degraded).",
        "macro_regime_growth":             "Growth / recession regime",
        # Common factor display
        "macro_factor_trend":              "Trend",
        "macro_factor_signal":             "Signal",
        "macro_factor_value":              "Value (placeholder)",
        "macro_section_summary":           "Summary",
        "macro_section_overall_signal":    "Overall signal",
        # Liquidity / Rates / Inflation
        "macro_liquidity_caption":         "Liquidity, rates and inflation — the dominant macro drivers for risk assets (fixture).",
        "macro_liquidity_header":          "Liquidity",
        "macro_rates_header":              "Rates",
        "macro_inflation_header":          "Inflation",
        "macro_liquidity_trend":           "Liquidity trend",
        # Credit / Volatility / Breadth
        "macro_credit_caption":            "Credit spreads, volatility (VIX) and market breadth — confirm/diverge signals for risk sentiment (fixture).",
        "macro_credit_header":             "Credit spreads",
        "macro_volatility_header":         "Volatility",
        "macro_breadth_header":            "Market breadth",
        "macro_dollar_header":             "US dollar",
        "macro_earnings_header":           "Earnings cycle",
        "macro_policy_header":             "Policy risk",
        # Phase 5O.1: Macro Indicators tab
        "macro_tab_indicators":            "Macro Indicators",
        "macro_indicators_caption":        "Concrete user-requested macro instruments and economic-release indicators (fixture). Grouped into commodities, risk appetite / leadership, and economic releases.",
        "macro_indicators_not_live":       "Indicators on this page are sample / demo data.",
        "macro_indicators_commodities_header": "Commodities",
        "macro_indicators_risk_header":    "Risk appetite / leadership",
        "macro_indicators_releases_header": "Economic releases",
        "macro_indicators_no_data":        "No indicators in this group for this fixture.",
        "macro_ind_value":                 "Value (placeholder)",
        "macro_ind_trend":                 "Trend",
        "macro_ind_signal":                "Signal",
        "macro_ind_status":                "Status",
        "macro_ind_category":              "Category",
        "macro_ind_interpretation":        "Interpretation",
        "macro_ind_macro_implication":     "Macro implication",
        "macro_ind_horizon_implication":   "Horizon implication",
        # Risk appetite
        "macro_risk_caption":              "Risk-appetite state (fixture).",
        "macro_risk_state":                "Risk state",
        # Horizon bias
        "macro_horizon_caption":           "Macro bias by horizon (review-only; not a trade instruction). The same regime can favor momentum short-term and accumulation long-term.",
        "macro_horizon_short":             "Short-term bias",
        "macro_horizon_mid":               "Mid-term bias",
        "macro_horizon_long":              "Long-term bias",
        "macro_horizon_rationale":         "Rationale",
        "macro_horizon_not_decision":      "Horizon bias is review-only context — not a buy/sell decision or trade instruction.",
        # Theme implications
        "macro_themes_caption":            "Macro implications for themes (fixture only). These are example relationships — not live market facts or buy/sell calls.",
        "macro_themes_implication":        "Implication",
        "macro_themes_rationale":          "Rationale",
        "macro_themes_not_live":           "Theme implications are illustrative context, not live market claims.",
        "macro_themes_no_implications":    "No theme implications in this fixture.",
        # Opportunity posture
        "macro_posture_caption":           "Review-only opportunity posture guidance (fixture). These are not trade instructions and do not produce a final buy/sell decision.",
        "macro_posture_primary":           "Primary posture",
        "macro_posture_secondary":         "Secondary postures",
        "macro_posture_rationale":         "Rationale",
        "macro_posture_not_decision":      "Opportunity posture is review-only context — not a buy/sell decision or trade instruction.",
        # Provenance / Diagnostics
        "macro_provenance_caption":        "Demo-only provenance. This is not live workflow output; no live macro / external API was called.",
        "macro_provenance_no_api":         "No live macro API, no external API, no LLM.",
        "macro_provenance_validation":     "Validation / fixture summary (Phase 5O)",
        "macro_provenance_source":         "Source fixture: `lib/reliability/phase5_macro_dashboard.py` (Phase 5O deterministic macro fixtures).",
        "macro_provenance_not_live":       "This page does not read live workflow state and does not call any live macro / external API.",
        "macro_provenance_missing_factors": "Missing factors (degraded fixture):",
        # Fail-closed
        "macro_failclosed_headline":       "Failed to build the Phase 5O macro fixture. Cannot display the Macro Dashboard preview.",
        "macro_failclosed_no_detail":      "(no error detail)",
        "macro_failclosed_note":           "Fail-closed: no fallback to live macro data, LLM, or external API. Fix the fixture builder and retry.",
        "macro_no_scenarios":              "No macro fixture scenarios available.",
        # ── Phase 6A: Live Macro Conditions ──────────────────────────────────────
        "macro_live_header":               "Live Macro Conditions",
        "macro_live_caption":              "Below is live macro data reflecting today's market conditions; each metric shows its data status.",
        "macro_live_mode_caption":         "Live data reflecting today's market. Review-only — not investment advice, and authorizes no trading.",
        "macro_live_disabled_note":        "Live mode is off: showing backup sample data.",
        "macro_live_failclosed_note":      "Live macro fetch failed overall; fell back to fixture data. The page continues to render review-only and does not crash.",
        "macro_live_coverage_label":       "Data coverage",
        "macro_live_freshness_label":      "Data freshness",
        "macro_live_updated_label":        "Snapshot time (UTC)",
        "macro_live_regime_label":         "Live macro regime",
        "macro_live_confidence_label":     "Confidence",
        "macro_live_posture_label":        "Opportunity posture (review-only)",
        "macro_live_signals_label":        "Key signals",
        "macro_live_horizon_label":        "Horizon bias",
        "macro_live_badge_live_help":      "LIVE = this metric group was fetched successfully from a live source.",
        "macro_live_badge_fixture_help":   "FIXTURE = this metric group fell back to fixture data because the fetch failed.",
        "macro_live_fallback_note":        "No live data for this metric; showing backup data.",
        "macro_live_grp_vix":              "Market volatility",
        "macro_live_grp_rates":            "Rates & inflation",
        "macro_live_grp_credit":           "Credit spreads",
        "macro_live_grp_dollar":           "US dollar",
        "macro_live_grp_etf":              "ETF returns",
        "macro_live_grp_releases":         "Economic releases",
        "macro_live_grp_sentiment":        "Market sentiment",
        "macro_live_vix":                  "VIX",
        "macro_live_vix_chg":              "VIX 1M change",
        "macro_live_feargreed":            "Fear/greed proxy (0–100)",
        "macro_live_y10":                  "10Y yield %",
        "macro_live_y2":                   "2Y yield %",
        "macro_live_spread":               "10Y-2Y spread %",
        "macro_live_breakeven":            "10Y breakeven inflation %",
        "macro_live_hy":                   "HY credit spread %",
        "macro_live_dxy":                  "Broad dollar index",
        "macro_live_dxy_chg":              "Dollar 1M change %",
        "macro_live_nfp":                  "NFP nonfarm payrolls (thousands)",
        "macro_live_cpi":                  "CPI index",
        "macro_live_ppi":                  "PPI index",
        "macro_live_nfp_chg":              "NFP monthly change (thousands)",
        "macro_live_cpi_mom":              "CPI MoM %",
        "macro_live_ppi_mom":              "PPI MoM %",
        "macro_live_sentiment_score":      "Sentiment score (0–100)",
        "macro_live_etf_1m":               "1M return %",
        "macro_live_etf_3m":               "3M return %",
        "macro_live_fear_greed_proxy_note": "The fear/greed score is derived from market volatility: calmer volatility means a higher (greedier) reading, while sharper volatility means a lower (fearful) reading.",
        "macro_live_safety":               "Live macro is review-only context; it produces no buy/sell decision and authorizes no trading.",
        # Phase 6A — regime / confidence / horizon-bias localized value maps
        "macro_regimeval_risk_on":         "Risk-on",
        "macro_regimeval_risk_off":        "Risk-off",
        "macro_regimeval_transition":      "Transition",
        "macro_regimeval_degraded":        "Degraded / unknown",
        "macro_confval_high":              "High",
        "macro_confval_medium":            "Medium",
        "macro_confval_low":               "Low",
        "macro_biasval_favorable":         "Favorable",
        "macro_biasval_neutral":           "Neutral",
        "macro_biasval_cautious":          "Cautious",
        "macro_biasval_unfavorable":       "Unfavorable",
        # Phase 6A — localized opportunity posture by regime
        "macro_posture_text_risk_on":      "Risk-on backdrop favors momentum and continuation setups short- and mid-term; keep long-term entries valuation-disciplined. Review-only context, not a buy/sell decision.",
        "macro_posture_text_risk_off":     "Risk-off backdrop is unfavorable for fresh short- and mid-term risk; favor capital preservation and watch for a later accumulation window. Review-only context, not a buy/sell decision.",
        "macro_posture_text_transition":   "Transitional backdrop with mixed/unconfirmed signals; stay cautious across horizons and wait for confirmation. Review-only context, not a buy/sell decision.",
        "macro_posture_text_degraded":     "Macro data coverage is insufficient to classify a regime. Treat macro context as unknown and rely on bottom-up review only. Review-only context, not a buy/sell decision.",
        # Phase 6A — localized signal templates (parameterized via {placeholders})
        "macro_sig_vix_low":               "VIX {vix} is low (<18): calm volatility, risk-on.",
        "macro_sig_vix_high":              "VIX {vix} is elevated (>27): stress, risk-off.",
        "macro_sig_vix_mid":               "VIX {vix} is mid-range (18–27): neutral volatility.",
        "macro_sig_fg_greed":              "Fear/greed proxy {fg} signals greed (>60): risk-on (watch for crowding).",
        "macro_sig_fg_fear":               "Fear/greed proxy {fg} signals fear (<40): risk-off.",
        "macro_sig_credit_tight":          "HY credit spread {hy}pp is tight (<3.5): risk-on.",
        "macro_sig_credit_wide":           "HY credit spread {hy}pp is wide (>5.0): credit stress, risk-off.",
        "macro_sig_curve_inverted":        "10Y-2Y spread {spread}pp is inverted (<0): recession-risk caution.",
        "macro_sig_curve_steep":           "10Y-2Y spread {spread}pp is positively sloped (>0.5): expansion-friendly.",
        "macro_sig_breadth_broad":         "SPY {spy}% and IWM {iwm}% 1M returns are both positive: broad participation, risk-on.",
        "macro_sig_breadth_weak":          "SPY {spy}% and IWM {iwm}% 1M returns are both negative: broad weakness, risk-off.",
        "macro_sig_breadth_mixed":         "SPY {spy}% vs IWM {iwm}% 1M returns diverge: mixed breadth.",
        "macro_sig_dollar_strong":         "Broad dollar +{chg}% 1M: tightening liquidity, risk-off lean.",
        "macro_sig_dollar_weak":           "Broad dollar {chg}% 1M: easing liquidity, risk-on lean.",
        "macro_sig_degraded":              "Live data coverage {coverage_pct} is below the 50% threshold: regime is degraded / unknown.",
        "macro_sig_default":               "No decisive macro signals available; classified by default margin.",
        # Phase 6A — localized status words (for live sub-regime readouts)
        "macro_status_elevated":           "Elevated",
        "macro_status_moderate":           "Moderate",
        "macro_status_low":                "Low",
        "macro_status_contained":          "Contained",
        "macro_status_tightening":         "Tightening",
        "macro_status_easing":             "Easing",
        "macro_status_neutral":            "Neutral",
        "macro_status_tight":              "Tight / healthy",
        "macro_status_normal":             "Normal",
        "macro_status_wide":               "Wide / stressed",
        "macro_status_calm":               "Calm",
        "macro_status_stressed":           "Stressed",
        "macro_status_broad":              "Broad",
        "macro_status_narrow":             "Narrow",
        "macro_status_mixed":              "Mixed",
        "macro_status_strengthening":      "Strengthening",
        "macro_status_weakening":          "Weakening",
        "macro_status_stable":             "Stable",
        "macro_status_greed":              "Greed",
        "macro_status_extreme_greed":      "Extreme greed",
        "macro_status_fear":               "Fear",
        "macro_status_extreme_fear":       "Extreme fear",
        "macro_status_unknown":            "Unknown",
        # Phase 6A — live sub-regime domain labels + section headers
        "macro_live_domain_rates":         "Rates",
        "macro_live_domain_inflation":     "Inflation expectations",
        "macro_live_domain_liquidity":     "Liquidity",
        "macro_live_domain_credit":        "Credit spreads",
        "macro_live_domain_volatility":    "Volatility",
        "macro_live_domain_breadth":       "Market breadth",
        "macro_live_domain_dollar":        "US dollar",
        "macro_live_domain_risk":          "Risk appetite",
        "macro_live_regime_readout":       "Regime readout (from live data)",
        "macro_live_overview_regime":      "Current macro regime",
        "macro_live_section_signals":      "Key signals (from live data)",
        "macro_live_details":              "Details",
        "macro_live_no_group_data":        "No live data for this group; fell back to fixture values.",
        "macro_live_status_label":         "Status",
        "macro_live_theme_caption":        "The theme implications below are derived from the current macro regime — context only, not a live market claim or a buy/sell call.",
        "macro_theme_impl_risk_on":        "A risk-on backdrop typically favors high-beta themes (growth / AI / semis) and pressures defensives; watch crowding and valuation.",
        "macro_theme_impl_risk_off":       "A risk-off backdrop typically favors defensives / staples / cash and pressures high-beta growth themes.",
        "macro_theme_impl_transition":     "In a transitional backdrop theme rotation is unclear; wait for confirmation before adding exposure.",
        "macro_theme_impl_degraded":       "Insufficient data to derive theme implications.",
        # Phase 6A — visual upgrade chrome (hero banner + trend tables + sections)
        "macro_hero_label":                "Current market regime",
        "macro_hero_caption":              "Deterministically classified from live macro data (review-only, not a buy/sell decision).",
        "macro_trend_header":              "History trend (last 6)",
        "macro_trend_no_data":             "No history data.",
        "macro_trend_date":                "Date",
        "macro_trend_value":               "Value",
        "macro_sec_headline":              "Regime overview",
        "macro_sec_indicators":            "Core indicators",
        "macro_sec_signals":               "Signals & readout",
        # Phase 6B — AI Signal Candidates (Scanner signal layer)
        "scn_sig_title":                   "AI Signal Candidates",
        "scn_sig_caption":                 "Auto-generated candidates from real signals (research review-only, not buy/sell advice).",
        "scn_sig_macro_label":             "Macro regime",
        "scn_sig_generate_btn":            "Generate Candidates",
        "scn_sig_send_btn":                "Send to Manual Scanner",
        "scn_sig_generating":              "Scoring candidates...",
        "scn_sig_sent_note":               "Top candidates pre-filled into the manual pool below.",
        "scn_sig_empty_hint":              "Click \"Generate Candidates\" to surface tickers ranked by alternative data, EPS-revision trend, narrative attribution, and entry quality.",
        "scn_sig_col_ticker":              "Ticker",
        "scn_sig_col_score":               "Composite Score",
        "scn_sig_col_entry":               "Entry Quality",
        "scn_sig_col_horizon":             "Horizon Fit (S/M/L)",
        "scn_sig_col_signals":             "Key Signals",
        "scn_sig_count":                   "Candidates",
        "scn_sig_disclaimer":              "Research review-only; not investment advice. Produces no buy/sell or order instruction.",
        # Phase 6B v2 — Dual-Track signal layer (additive)
        "scn_sig_llm_depth":               "LLM narrative depth",
        "scn_sig_llm_help":                "Number of Layer-1 survivors (ranked by quality pre-score) that receive an LLM narrative-stage judgment (10–100, default 50).",
        "scn_sig_llm_est":                 "Estimated time",
        "scn_sig_col_type":                "Type",
        "scn_sig_subscores":               "Track A / Track B sub-scores",
        "scn_sig_col_track_a":             "Track A",
        "scn_sig_col_track_b":             "Track B",
        "scn_sig_col_insider":             "Insider",
        "scn_sig_col_unusual":             "Unusual News",
        "scn_sig_col_analyst":             "Analyst Rev.",
        # Phase 6B v3 — Horizon-native signal cards (additive)
        "scn_sig_filter_label":            "Filter by horizon (all checked by default)",
        "scn_sig_hz_short":                "Short",
        "scn_sig_hz_mid":                  "Mid",
        "scn_sig_hz_long":                 "Long",
        "scn_sig_strength_triple":         "Triple Signal",
        "scn_sig_strength_double":         "Double",
        "scn_sig_strength_single":         "Single",
        "scn_sig_strength_none":           "Weak",
        "scn_sig_triple_header":           "⭐ Triple Signal",
        "scn_sig_priced_in":               "May be priced in",
        "scn_sig_details":                 "Details",
        "scn_sig_summary":                 "{n} candidates · Triple {triple} · Double {double} · Single {single}",
        "scn_sig_eps":                     "EPS revision",
        "scn_sig_val":                     "Valuation pct",
        "scn_sig_narr_stage":              "Narrative stage",
        "scn_sig_theme_tags":              "Theme tags",
        # Phase 6B v2 — Scanner universe configuration (additive)
        "scn_uni_title":                   "Universe Configuration",
        "scn_uni_sp500":                   "Include S&P 500 top 100",
        "scn_uni_themes":                  "Add theme baskets",
        "scn_uni_manual":                  "Add tickers manually (comma-separated)",
        "scn_uni_max":                     "Max universe size",
        "scn_uni_current":                 "Current universe: {n} tickers",
        "scn_uni_preloaded":               "Theme pre-loaded from Sector Research: {label} ({n} tickers)",
        "scn_uni_clear_btn":               "Clear",
        # Phase 6B — Cross-GICS Market Themes (additive)
        "p2_tab_sector":                   "Sector Analysis",
        "theme_tab":                       "Market Themes",
        "theme_subtitle":                  "Cross-GICS investment themes for the current AI-driven cycle. Theme momentum feeds the Scanner universe.",
        "theme_caption":                   "Each theme either tracks a representative ETF or is scored as an equal-weight basket of curated constituents (manually curated, June 2026). Research review-only — not investment advice.",
        "theme_loading":                   "Loading theme momentum...",
        "theme_no_data":                   "Theme momentum data is unavailable right now. Please try again later.",
        "theme_col_theme":                 "Theme",
        "theme_col_1m":                    "1M Return %",
        "theme_col_3m":                    "3M Return %",
        "theme_col_6m":                    "6M Return %",
        "theme_col_score":                 "Momentum Score",
        "theme_col_3m_excess":             "3M excess% (vs QQQ)",
        "theme_col_stage":                 "Stage",
        "theme_col_breadth":               "Breadth",
        "theme_stage_unconfirmed":         "unconfirmed",
        "theme_col_source":                "Data Source",
        "theme_src_etf":                   "ETF",
        "theme_src_equal_weight":          "Equal-weight",
        "theme_src_fixture":               "Fixture",
        "theme_constituents":              "Constituents",
        "theme_constituent_returns":       "Constituent returns (1M / 3M)",
        "theme_bar_title":                 "Constituent 3M Returns (%)",
        "theme_constituent_na":            "Constituent return data unavailable.",
        "theme_send_top_btn":              "Send top theme to Scanner",
        "theme_send_all_btn":              "Send all theme constituents to Scanner",
        "theme_sent_top":                  "Sent top theme to Scanner",
        "theme_sent_all":                  "Sent all theme constituents to Scanner",
        "theme_tickers":                   "tickers",
        "theme_analyze_btn":               "Analyze",
        "theme_analyzing":                 "Analyzing theme...",
        "theme_ai_macro_alignment":        "Macro alignment",
        "theme_ai_narrative_stage":        "Narrative stage",
        "theme_ai_catalysts":              "Key catalysts",
        "theme_ai_risks":                  "Risk factors",
        "theme_ai_horizon":                "Horizon bias",
        "theme_ai_summary":                "Summary",
        "theme_ai_unavailable":            "AI analysis unavailable.",
    },
}


def t(key: str) -> str:
    """Return the translated UI string for the current language (defaults to en)."""
    lang = st.session_state.get("language", "en")
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)


# --- Market-internals display helpers (plain-language layer; no computation) -------
# These translate already-computed tokens at the RENDER layer only. EN keys equal the
# raw tokens, so the EN surface is byte-for-byte unchanged; only ZH gains readability.

_FRAG_REASON_GLOSS_KEY = {
    "finnhub_unavailable":    "mi_dgloss_finnhub_unavailable",
    "earnings_source_absent": "mi_dgloss_earnings_source_absent",
    "no_reports_in_window":   "mi_dgloss_no_reports_in_window",
    "partial_frame_coverage": "mi_dgloss_partial_frame_coverage",
    "implausible_count":      "mi_dgloss_implausible_count",
}


def frag_reason_gloss(reason: str) -> str:
    """Append a ZH gloss to a raw earnings degrade-reason token WITHOUT altering the
    token text — the token stays a stable audit anchor (降级词汇表). EN renders the bare
    token (empty gloss); unknown tokens pass through unchanged."""
    if not reason:
        return reason
    key = _FRAG_REASON_GLOSS_KEY.get(reason)
    gloss = t(key) if key else ""
    return f"{reason}（{gloss}）" if gloss else reason


_FRAG_OD_DIR_TOK = ("offense", "defense", "balanced")
_FRAG_OD_MAG_TOK = ("strong", "moderate", "mild")


def frag_od_value(direction: str, magnitude: str) -> str:
    """Localize the offense/defense enum at the display layer (rotation.py tokens are
    untouched). EN values equal the raw tokens, so EN render is unchanged; ZH renders
    进攻/防御/均衡 + 强/中等/轻微. Mirrors the prior fallback: empty direction → '—',
    empty magnitude → '' (so a blank reading still renders a '—' cell)."""
    d = direction or ""
    m = magnitude or ""
    d_txt = (t(f"mi_od_dir_{d}") if d in _FRAG_OD_DIR_TOK else d) if d else "—"
    m_txt = (t(f"mi_od_mag_{m}") if m in _FRAG_OD_MAG_TOK else m) if m else ""
    return f"{d_txt} {m_txt}".strip()


def render_valuation_diagnosis_card(diag) -> None:
    """Render the Anchor Intel v2.4 valuation diagnosis card (bilingual, fail-soft).

    ``diag`` is a :class:`lib.valuation_diagnosis.ValuationDiagnosis` (duck-typed).
    UI-copy discipline: the decision-relevant tokens (valuation role, endorsed range,
    anchor consistency, what-would-change) render in the main view; method/token-level
    detail is folded into muted captions + ``help=`` tooltips (NOT a nested expander —
    this card renders inside an already-open expander on pages/4). Never raises.
    """
    if diag is None:
        return
    try:
        _role = str(getattr(diag, "valuation_role", "") or "informational")
        _role_color = {"informational": "#8b949e", "mid_term_supportive": "#d29922",
                       "long_term_eligible": "#3fb950"}.get(_role, "#8b949e")
        st.markdown(f"**{t('valdiag_header')}**")
        # ── Valuation role badge (the headline decision token) ──────────────────
        st.markdown(
            f"{t('valdiag_role')}: "
            f"<span style='background:{_role_color}22;color:{_role_color};"
            f"border:1px solid {_role_color}55;padding:2px 9px;border-radius:10px;"
            f"font-weight:600'>{t(f'valdiag_role_{_role}')}</span>",
            unsafe_allow_html=True,
        )
        # ── Endorsed range (or the honest irreconcilable / unavailable state) ───
        _er = getattr(diag, "endorsed_range", None)
        _er_state = getattr(_er, "state", "unavailable")
        if _er_state == "endorsed" and getattr(_er, "mid", None) is not None:
            st.caption(
                f"{t('valdiag_endorsed_range')}: "
                f"${_er.low:.2f} – ${_er.high:.2f}  (mid ${_er.mid:.2f})")
        elif _er_state == "irreconcilable":
            st.caption(f"⚠️ {t('valdiag_range_irreconcilable')}")
        else:
            st.caption(t("valdiag_range_unavailable"))
        # ── Anchor consistency (+ outlier when irreconcilable) ──────────────────
        _ac = getattr(diag, "anchor_consistency", None)
        _ac_state = getattr(_ac, "state", "no_anchor")
        _ac_line = f"{t('valdiag_consistency')}: {t(f'valdiag_consistency_{_ac_state}')}"
        _outlier = getattr(_ac, "outlier", "") or ""
        if _outlier == "no_clear_outlier":
            _ac_line += f"  ·  {t('valdiag_outlier')}: {t('valdiag_no_clear_outlier')}"
        elif _outlier:
            _ac_line += f"  ·  {t('valdiag_outlier')}: {_outlier.upper()}"
        st.caption(_ac_line)
        # ── Peer match quality (v2.5) — only when assessed (peers supplied) ──────
        _pmq = str(getattr(diag, "peer_match_quality", "") or "")
        if _pmq == "low":
            st.caption(f"⚠️ {t('valdiag_peer_match')}: {t('valdiag_peer_match_low')}")
        elif _pmq == "high":
            st.caption(f"{t('valdiag_peer_match')}: {t('valdiag_peer_match_high')}")
        # ── What would change this (mechanical, falsifiable) ────────────────────
        _mech = list(getattr(getattr(diag, "what_would_change", None), "mechanical", []) or [])
        if _mech:
            _parts = []
            for _c in _mech:
                _mark = "🔴" if getattr(_c, "met", False) else "⚪"
                _state = t("valdiag_cond_met") if getattr(_c, "met", False) else t("valdiag_cond_armed")
                _parts.append(f"{_mark} {t(f'valdiag_cond_{_c.id}')} ({_state})")
            st.caption(f"{t('valdiag_what_would_change')}: " + "  ·  ".join(_parts))
        # ── Method detail — folded (muted captions + tooltips) ──────────────────
        _applic = list(getattr(diag, "applicable_methods", []) or [])
        if _applic:
            st.caption(f"{t('valdiag_applicable_methods')}: "
                       + " · ".join(str(m).upper() for m in _applic))
        _rej = list(getattr(diag, "rejected_methods", []) or [])
        if _rej:
            _rparts = []
            for _r in _rej:
                _reason = getattr(_r, "reason", "") or ""
                # Map reason tokens to bilingual labels (reuse existing flag keys).
                _rlabel = {
                    "cycle_distorted": t("cockpit_fv_flag_cycle_distorted"),
                    "dcf_unavailable": t("valdiag_reason_dcf_unavailable"),
                    "excluded_anchor": t("valdiag_reason_excluded_anchor"),
                    "insufficient_comparable_peers":
                        t("valdiag_reason_insufficient_comparable_peers"),
                }.get(_reason, _reason or t("valdiag_reason_excluded_anchor"))
                _detail = getattr(_r, "detail", "") or ""
                _val = getattr(_r, "value", None)
                _vtxt = f" ${_val:.2f}" if isinstance(_val, (int, float)) else ""
                _rparts.append((f"{str(getattr(_r, 'name', '')).upper()}{_vtxt} "
                                f"({_rlabel})", _detail))
            # Render with per-item tooltips carrying the human basis.
            st.caption(f"{t('valdiag_rejected_methods')}: "
                       + " · ".join(p[0] for p in _rparts))
        # ── Phase-8 placeholders (named, muted) ─────────────────────────────────
        st.caption(f"_{t('valdiag_reverse_dcf_pending')}_  ·  _{t('valdiag_narrative_pending')}_")
    except Exception:  # noqa: BLE001 — render is best-effort; never break the page
        return


def render_workflow_bar() -> None:
    """Show a workflow status banner on sector / scan / equity pages.

    Hidden when research_state.status is 'idle'.
    Displays current sector/ticker, fork badge, Fork and Overview buttons.
    """
    state = st.session_state.get("research_state", {})
    if state.get("status", "idle") == "idle":
        return

    _dark  = st.session_state.get("dark_mode", True)
    bar_bg = "#161b22" if _dark else "#f0f3f6"
    bar_bd = "#30363d" if _dark else "#d0d7de"
    t0_c   = "#e6edf3" if _dark else "#1f2328"
    t1_c   = "#8b949e" if _dark else "#57606a"

    is_running = state.get("status") == "running"
    dot_color  = "#ffd43b" if is_running else "#3fb950"
    status_lbl = t("wf_status_running") if is_running else t("wf_status_done")

    parts: list[str] = []
    if state.get("sector"):
        parts.append(f"{t('wf_sector_lbl')}: <b>{state['sector']}</b>")
    if state.get("ticker"):
        parts.append(f"{t('wf_ticker_lbl')}: <b>{state['ticker']}</b>")
    if state.get("fork"):
        parts.append(f"✂️ {t('wf_forked')}")
    info_html = " &nbsp;·&nbsp; ".join(parts)

    st.markdown(
        f'<div style="background:{bar_bg};border:1px solid {bar_bd};border-radius:8px;'
        f'padding:8px 16px;margin-bottom:8px;display:flex;align-items:center;gap:10px;">'
        f'<span style="width:8px;height:8px;border-radius:50%;background:{dot_color};'
        f'display:inline-block;flex-shrink:0;"></span>'
        f'<span style="font-size:0.80rem;color:{t1_c};white-space:nowrap;">{status_lbl}</span>'
        f'<span style="font-size:0.83rem;color:{t0_c};flex:1;">{info_html}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    _bc = st.columns([1, 1, 5])
    with _bc[0]:
        if not state.get("fork"):
            if st.button(t("wf_fork_btn"), key="_wf_fork", use_container_width=True):
                st.session_state["research_state"]["fork"] = True
                st.rerun()
        else:
            st.caption(f"✂️ {t('wf_forked')}")
    with _bc[1]:
        if st.button(t("wf_back_btn"), key="_wf_back", use_container_width=True):
            st.switch_page("pages/1_Overview.py")


# ── Financial statement row-name translation ──────────────────────────────────

ROW_NAME_MAP: dict[str, str] = {
    # ── Income Statement ──────────────────────────────────────────────────────
    "Total Revenue":                       "营业收入",
    "Cost Of Revenue":                     "营业成本",
    "Gross Profit":                        "毛利润",
    "Operating Expense":                   "营业费用",
    "Research And Development":            "研发费用",
    "Selling General Administrative":      "销售及管理费用",
    "Operating Income":                    "营业利润",
    "EBITDA":                              "EBITDA",
    "Net Income":                          "净利润",
    "Basic EPS":                           "基本每股收益",
    "Diluted EPS":                         "稀释每股收益",
    "Interest Expense":                    "利息费用",
    "Tax Provision":                       "所得税",
    "Pretax Income":                       "税前利润",
    # ── Balance Sheet ─────────────────────────────────────────────────────────
    "Total Assets":                        "总资产",
    "Total Liabilities Net Minority Interest": "总负债",
    "Total Equity Gross Minority Interest":"总权益",
    "Stockholders Equity":                 "股东权益",
    "Total Current Assets":                "流动资产",
    "Total Current Liabilities":           "流动负债",
    "Cash And Cash Equivalents":           "现金及等价物",
    "Total Debt":                          "总债务",
    "Net Debt":                            "净债务",
    "Inventory":                           "存货",
    "Accounts Receivable":                 "应收账款",
    "Retained Earnings":                   "留存收益",
    "Goodwill":                            "商誉",
    "Goodwill And Other Intangible Assets":"商誉及无形资产",
    "Long Term Debt":                      "长期债务",
    # ── Cash Flow Statement ───────────────────────────────────────────────────
    "Operating Cash Flow":                 "经营活动现金流",
    "Free Cash Flow":                      "自由现金流",
    "Capital Expenditure":                 "资本支出",
    "Investing Cash Flow":                 "投资活动现金流",
    "Financing Cash Flow":                 "融资活动现金流",
    "Net Income From Continuing Operations":"持续经营净利润",
    "Depreciation And Amortization":       "折旧与摊销",
    "Change In Working Capital":           "营运资本变动",
    "Repurchase Of Capital Stock":         "股票回购",
    "Cash Dividends Paid":                 "股息支付",
    "Issuance Of Debt":                    "债务发行",
    "Repayment Of Debt":                   "债务偿还",
    "Net Common Stock Issuance":           "股本变动（净）",
}


def translate_index(df, lang: str) -> pd.DataFrame:
    """
    Translate the row index of a financial-statement DataFrame into Chinese.
    Rows not found in ROW_NAME_MAP are left unchanged (e.g. already-translated
    or vendor-specific names).  Only applied when lang == "zh".
    """
    if lang != "zh":
        return df
    df = df.copy()
    df.index = [ROW_NAME_MAP.get(str(idx), str(idx)) for idx in df.index]
    return df
