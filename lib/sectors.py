"""
Three-layer sector architecture for US equity rotation analysis.

Layer 1: GICS Standard Sectors (11 sectors, S&P 500 constituents from Wikipedia)
Layer 2: Thematic ETF Sub-Sectors (top holdings from yfinance funds_data)
Layer 3: Custom Theme Pools (small hardcoded lists, no dedicated ETF)
"""

import pandas as pd
import yfinance as yf
import streamlit as st


# ── Layer 1: GICS Standard Sectors ──────────────────────────────────────────
SECTOR_CONFIG = {
    "Information Technology":  {"etf": "XLK",  "color": "#388bfd", "zh": "信息技术"},
    "Health Care":             {"etf": "XLV",  "color": "#3fb950", "zh": "医疗保健"},
    "Financials":              {"etf": "XLF",  "color": "#d29922", "zh": "金融"},
    "Energy":                  {"etf": "XLE",  "color": "#f85149", "zh": "能源"},
    "Industrials":             {"etf": "XLI",  "color": "#bc8cff", "zh": "工业"},
    "Consumer Discretionary":  {"etf": "XLY",  "color": "#ff7043", "zh": "非必需消费"},
    "Consumer Staples":        {"etf": "XLP",  "color": "#4fc3f7", "zh": "必需消费"},
    "Materials":               {"etf": "XLB",  "color": "#a5d6a7", "zh": "材料"},
    "Real Estate":             {"etf": "XLRE", "color": "#ffcc02", "zh": "房地产"},
    "Utilities":               {"etf": "XLU",  "color": "#80cbc4", "zh": "公用事业"},
    "Communication Services":  {"etf": "XLC",  "color": "#f48fb1", "zh": "通信服务"},
}

# ── Layer 2: Thematic ETF Sub-Sectors ───────────────────────────────────────
THEME_ETF_CONFIG = {
    "Semiconductors":      {"etf": "SOXX", "parent": "Information Technology", "zh": "半导体"},
    "Cloud Computing":     {"etf": "WCLD", "parent": "Information Technology", "zh": "云计算"},
    "Cybersecurity":       {"etf": "HACK", "parent": "Information Technology", "zh": "网络安全"},
    "AI & Robotics":       {"etf": "AIQ",  "parent": "Information Technology", "zh": "人工智能"},
    "Data Centers":        {"etf": "DTCR", "parent": "Information Technology", "zh": "数据中心"},
    "Fintech":             {"etf": "FINX", "parent": "Financials",             "zh": "金融科技"},
    "Nuclear Energy":      {"etf": "NLR",  "parent": "Energy",                "zh": "核能"},
    "Clean Energy":        {"etf": "ICLN", "parent": "Energy",                "zh": "清洁能源"},
    "Solar":               {"etf": "TAN",  "parent": "Energy",                "zh": "太阳能"},
    "Biotech":             {"etf": "XBI",  "parent": "Health Care",           "zh": "生物科技"},
    "Genomics":            {"etf": "ARKG", "parent": "Health Care",           "zh": "基因组学"},
    "Global X Copper":     {"etf": "COPX", "parent": "Materials",             "zh": "铜矿"},
}

# ── Layer 3: Custom Theme Pools (no dedicated ETF) ───────────────────────────
CUSTOM_THEME_CONFIG = {
    "Optical Networking": {
        "tickers": ["CIEN", "LITE", "IIVI", "NPTN", "AAOI", "COHR"],
        "parent": "Information Technology",
        "zh": "光模块/光互联",
    },
    "Nuclear Power Developers": {
        "tickers": ["CCJ", "LEU", "NNE", "SMR", "OKLO", "BWXT"],
        "parent": "Energy",
        "zh": "核电开发商",
    },
    "Data Center REITs": {
        "tickers": ["EQIX", "DLR", "AMT", "CCI", "SBAC"],
        "parent": "Real Estate",
        "zh": "数据中心REITs",
    },
}


# ── Data fetchers ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def get_sp500_table() -> pd.DataFrame:
    """Fetch S&P 500 constituent table from Wikipedia. Cached 24h."""
    try:
        df = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            attrs={"id": "constituents"},
        )[0]
        df["Symbol"] = df["Symbol"].str.replace(".", "-", regex=False)
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=86400, show_spinner=False)
def get_etf_holdings(etf_ticker: str, max_holdings: int = 30) -> list[str]:
    """Fetch ETF top holdings via yfinance funds_data. Cached 24h."""
    try:
        tk = yf.Ticker(etf_ticker)
        h = tk.funds_data.top_holdings
        if h is not None and not h.empty:
            return h.index.tolist()[:max_holdings]
    except Exception:
        pass
    return []


# ── Unified constituent interface ─────────────────────────────────────────────

def get_theme_constituents(theme: str) -> list[str]:
    """
    Unified interface for all three layers.
    Returns list of tickers for the given theme/sector name.
    """
    # Layer 1: GICS sector → Wikipedia S&P 500
    if theme in SECTOR_CONFIG:
        df = get_sp500_table()
        if not df.empty and "GICS Sector" in df.columns:
            return df[df["GICS Sector"] == theme]["Symbol"].tolist()

    # Layer 2: Thematic ETF
    if theme in THEME_ETF_CONFIG:
        etf = THEME_ETF_CONFIG[theme]["etf"]
        tickers = get_etf_holdings(etf)
        if tickers:
            return tickers

    # Layer 3: Custom pool
    if theme in CUSTOM_THEME_CONFIG:
        return CUSTOM_THEME_CONFIG[theme]["tickers"]

    return []


def get_all_themes(lang: str = "en") -> dict:
    """Return all available themes across all three layers for UI selectors."""
    result = {}
    for name, cfg in SECTOR_CONFIG.items():
        label = cfg["zh"] if lang == "zh" else name
        result[name] = {
            "label": label, "layer": 1,
            "etf": cfg["etf"], "color": cfg["color"],
        }
    for name, cfg in THEME_ETF_CONFIG.items():
        label = cfg["zh"] if lang == "zh" else name
        result[name] = {
            "label": label, "layer": 2,
            "etf": cfg["etf"], "color": "#8b949e", "parent": cfg["parent"],
        }
    for name, cfg in CUSTOM_THEME_CONFIG.items():
        label = cfg["zh"] if lang == "zh" else name
        result[name] = {
            "label": label, "layer": 3,
            "etf": None, "color": "#8b949e", "parent": cfg["parent"],
        }
    return result
