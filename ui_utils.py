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
    font-family: 'SF Mono', 'Fira Code', 'Courier New', monospace;
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
    font-size: 1.4rem !important; font-weight: 700 !important;
    color: var(--t0) !important;
    font-family: 'SF Mono', 'Fira Code', 'Courier New', monospace !important;
    letter-spacing: -0.01em;
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
    font-family: 'SF Mono', 'Fira Code', 'Courier New', monospace;
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
    font-family: 'SF Mono', 'Fira Code', 'Courier New', monospace;
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
    st.markdown(tokens + _GLOBAL_CSS + extra, unsafe_allow_html=True)


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


# ── Sidebar ───────────────────────────────────────────────────────────────────

def init_session():
    defaults = {
        "ticker": "", "scan_results": None, "last_report": {},
        "dark_mode": True, "language": "en",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def render_sidebar() -> str:
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

        ticker = st.text_input(
            t("sidebar_ticker"),
            value=st.session_state.ticker,
            placeholder=t("sidebar_ticker_ph"),
            key="sidebar_ticker",
        ).upper().strip()

        if ticker and ticker != st.session_state.ticker:
            st.session_state.ticker = ticker
            st.cache_data.clear()
            st.rerun()

        if ticker:
            st.divider()
            st.markdown(
                f'<p style="font-size:0.70rem;color:var(--t1);text-transform:uppercase;'
                f'letter-spacing:0.08em;margin-bottom:6px">{t("sidebar_cache")} · {ticker}</p>',
                unsafe_allow_html=True,
            )
            try:
                from cache_manager import cache_status
                status = cache_status(ticker)
                labels = {
                    "ohlcv_1y_1d":   t("cache_ohlcv"),
                    "financials":    t("cache_financials"),
                    "balance_sheet": t("cache_balance"),
                    "cashflow":      t("cache_cashflow"),
                }
                cols = st.columns(2)
                for i, (key, label) in enumerate(labels.items()):
                    fresh = status.get(key, {}).get("fresh", False)
                    dot   = '<span class="cdot cdot-ok"></span>' if fresh else '<span class="cdot cdot-old"></span>'
                    cols[i % 2].markdown(
                        f'<span style="font-size:0.73rem">{dot}{label}</span>',
                        unsafe_allow_html=True,
                    )
            except Exception:
                pass

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
        st.page_link("app.py",                      label=t("nav_home"))
        st.page_link("pages/1_Overview.py",         label=t("nav_p1"))
        st.page_link("pages/2_Sector.py",           label=t("nav_p2"))
        st.page_link("pages/3_Scanner.py",          label=t("nav_p3"))
        st.page_link("pages/4_Equity.py",           label=t("nav_p4"))
        st.page_link("pages/5_Financial.py",        label=t("nav_p5"))
        st.page_link("pages/6_PriceVolume.py",      label=t("nav_p6"))

    return st.session_state.ticker


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
        "nav_p1":             "🔭 总览",
        "nav_p2":             "🏭 行业研究",
        "nav_p3":             "🔍 选股扫描",
        "nav_p4":             "🏢 个股研究",
        "nav_p5":             "📊 财务分析",
        "nav_p6":             "📉 量价分析",
        "nav_section":        "导航",
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
        "p2_title":           "🏭 行业研究",
        "p2_subtitle":        "ETF 价格走势 + 自定义标的横向对比",
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
        "p2_subtitle":             "GICS 板块轮动分析 · 主题 ETF 子板块 · 板块内选股",
        "p2_heatmap":              "📊 板块热力图",
        "p2_heatmap_subtitle":     "综合评分基于超额收益、RSI、距52周高点、成交量；分值越高动量越强",
        "p2_loading_scores":       "计算板块评分中...",
        "p2_select_sector":        "选择板块",
        "p2_rotation_signal":      "🔄 轮动信号",
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
        "p2_no_constituents":      "暂无成分股数据，请稍后重试",
        "p2_constituents_found":   "只只成分股",
        "p2_ranking_top30":        "展示市值前30名评级",
        "p2_rank_failed":          "排名计算失败，请重试",
        "p2_leader":               "龙头 Leaders",
        "p2_challenger":           "次龙头 Challengers",
        "p2_sleeper":              "潜力股 Sleepers",
        "p2_send_scanner":         "发送至选股扫描",
        "p2_subsector_drill":      "子板块下钻（Layer 2 / 3）",
        "p2_no_subsectors":        "当前板块暂无主题子板块",
        "p2_select_subsector":     "选择子板块",
        "p2_custom_pool":          "自定义股票池",
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
        "nav_p1":             "🔭 Overview",
        "nav_p2":             "🏭 Sector Research",
        "nav_p3":             "🔍 Stock Scanner",
        "nav_p4":             "🏢 Equity Research",
        "nav_p5":             "📊 Financials",
        "nav_p6":             "📉 Price & Volume",
        "nav_section":        "Navigation",
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
        "p2_title":           "🏭 Sector Research",
        "p2_subtitle":        "ETF Price Trends + Custom Peer Comparison",
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
        "p2_subtitle":             "GICS Sector Rotation · Thematic ETF Sub-Sectors · Intra-Sector Stock Ranking",
        "p2_heatmap":              "📊 Sector Heat Map",
        "p2_heatmap_subtitle":     "Composite score based on excess return, RSI, distance from 52W high, and volume. Higher = stronger momentum.",
        "p2_loading_scores":       "Computing sector scores...",
        "p2_select_sector":        "Select Sector",
        "p2_rotation_signal":      "🔄 Rotation Signal",
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
        "p2_no_constituents":      "No constituent data available. Please try again later.",
        "p2_constituents_found":   "constituents",
        "p2_ranking_top30":        "Showing top 30 by market cap",
        "p2_rank_failed":          "Ranking failed. Please try again.",
        "p2_leader":               "Leaders",
        "p2_challenger":           "Challengers",
        "p2_sleeper":              "Sleepers",
        "p2_send_scanner":         "Send to Scanner",
        "p2_subsector_drill":      "Sub-Sector Drill-Down (Layer 2 / 3)",
        "p2_no_subsectors":        "No thematic sub-sectors available for this sector.",
        "p2_select_subsector":     "Select Sub-Sector",
        "p2_custom_pool":          "Custom Pool",
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
    },
}


def t(key: str) -> str:
    """Return the translated UI string for the current language (defaults to en)."""
    lang = st.session_state.get("language", "en")
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)


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
