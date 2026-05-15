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
        st.warning("⚠️ 数据获取受限，请稍后重试或更换股票代码")
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def _load_info_impl(ticker: str) -> dict:
    from data_fetcher import get_info
    return get_info(ticker)


def load_info(ticker: str) -> dict:
    try:
        return _load_info_impl(ticker)
    except Exception:
        st.warning("⚠️ 数据获取受限，请稍后重试或更换股票代码")
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
    defaults = {"ticker": "", "scan_results": None, "last_report": {}, "dark_mode": True}
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
            "股票代码",
            value=st.session_state.ticker,
            placeholder="如：NVDA",
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
                f'letter-spacing:0.08em;margin-bottom:6px">数据缓存 · {ticker}</p>',
                unsafe_allow_html=True,
            )
            try:
                from cache_manager import cache_status
                status = cache_status(ticker)
                labels = {
                    "ohlcv_1y_1d":   "行情",
                    "financials":    "财务",
                    "balance_sheet": "资产负债",
                    "cashflow":      "现金流",
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

        # ── Dark / light mode toggle ──
        # Use a separate widget key so st.toggle doesn't own session_state.dark_mode
        current = st.session_state.get("dark_mode", True)
        toggled = st.toggle("🌙 深色模式", value=current, key="_dark_mode_widget")
        if toggled != current:
            st.session_state.dark_mode = toggled
            st.rerun()

        st.caption("⚠️ 仅供研究参考，不构成投资建议")

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


# ── Report save & download ────────────────────────────────────────────────────

def download_report_button(content: str, filename: str, label: str = "⬇ 下载报告"):
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
    col_headers = [_fmt_col(c) for c in df.columns]
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
