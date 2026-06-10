"""Page 8 — Macro Dashboard (Phase 5O fixtures + Phase 6A Live Data Integration).

Phase 6A adds live macro data. When ``MACRO_LIVE_MODE`` is True (the default),
the page renders a "Live Macro Conditions" section that reflects today's market,
fetched through ``lib/macro_data.py`` (free sources only) and classified by
``lib/macro_regime.py``. All live fetching is **fail-closed per metric group**:
any failure falls back to fixture data with a visible FIXTURE badge, and the page
can never crash. When ``MACRO_LIVE_MODE`` is False, every API call is skipped and
the page uses fixture data exactly as before Phase 6A.

This page itself imports no data-vendor SDK directly (all live calls are
encapsulated in ``lib/macro_data.py``), reads no research/.workflow_state.json,
writes nothing to disk, uses no database / vector store / persistence, and
introduces no broker / order / execution capability. approved_for_execution is
False (or absent) everywhere it appears. Not investment advice. The Phase 5O
fixture builder remains fail-closed — no fallback to live macro data, LLM, or
external API.

Phase 5O elevates **macro** from a subsection inside Sector Research into a
first-class upstream input for the Investment Cockpit. The page renders a
deterministic, fixture-only macro-regime view-model with the following tabs:

    Overview / Safety
    Macro Regime
    Liquidity / Rates / Inflation
    Credit / Volatility / Breadth
    Risk Appetite
    Horizon Bias
    Theme Implications
    Opportunity Posture
    Provenance / Diagnostics

Macro regime context is review-only: it influences whether the Cockpit favors
momentum trades, pullback entries, watchlist-only posture, risk reduction, or
long-term accumulation — but it does NOT produce a final buy/sell decision and
does NOT authorize execution.

Data source (deterministic / offline / fixture-only):

* Phase 5O ``lib.reliability.phase5_macro_dashboard`` fixture builders
  (risk_on / risk_off / transition / degraded). The Phase 5O dashboard feeds
  the future Theme Intelligence (Phase 5J) and Opportunity Queue (Phase 5K)
  logic as *context*; this page does not rewire that runtime logic.

Every user-facing chrome string routes through ``ui_utils.t()``. Fixture
content (factor descriptors, theme names, regime labels, JSON dumps, schema
identifiers) is intentionally NOT translated — it is deterministic demo data.

See:
  - docs/reliability_phase_5o_macro_dashboard_v01.md
  - docs/reliability_phase_5n_cockpit_ui_v02_opportunity_first_redesign.md
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st
import plotly.graph_objects as go

# Phase 5O macro dashboard view-model — fixture-only.
from lib.reliability.phase5_macro_dashboard import (
    MacroDashboardView,
    MacroIndicatorPanel,
    MacroIndicatorView,
    MacroRegimeFactorView,
    MacroRegimeSnapshot,
    MACRO_DASHBOARD_SCENARIO_ORDER,
    build_macro_dashboard_view_by_scenario,
)

# Phase 6A — live macro data + deterministic regime classification.
# All live data-vendor access is encapsulated in lib/macro_data.py; this page
# only calls fetch_all_macro() + classify_regime().
from lib.macro_data import fetch_all_macro, MacroDataResult
from lib.macro_regime import classify_regime, MacroRegimeResult
from lib.macro_state import save_regime_to_state  # Phase 6C-B regime boundary

# Shared UI utilities — theme, sidebar (language toggle + global nav), t().
from ui_utils import (apply_theme, render_sidebar, t, apply_layout, apply_legend,
                      frag_reason_gloss, frag_od_value)


# ---------------------------------------------------------------------------
# Phase 6A feature flag — single toggle controlling the entire page.
#
# When True (default), the page fetches live macro data (fail-closed, per metric
# group) and renders the Live Macro Conditions section reflecting today's market.
# When False, all API calls are skipped and the page uses fixture data exactly as
# before Phase 6A. This is a single boolean; nothing else gates the live path.
# ---------------------------------------------------------------------------

MACRO_LIVE_MODE = True


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Macro Dashboard (v0.1 Demo Preview)",
    page_icon="🌐",
    layout="wide",
)

apply_theme()
render_sidebar()


# ---------------------------------------------------------------------------
# Fixture loader (fixture-only; fail closed on builder error).
#
# Uses @st.cache_resource (NOT @st.cache_data): the deterministic Pydantic
# views are kept as live Python objects, never round-tripped through JSON.
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _load_macro_views():
    """Build every Phase 5O macro dashboard fixture once per process.

    Returns ``(views, error)`` where ``views`` maps scenario kind -> view.
    Fail-closed: no fallback to live macro data, LLM, or external API.
    """
    try:
        views = {
            kind: build_macro_dashboard_view_by_scenario(kind)
            for kind in MACRO_DASHBOARD_SCENARIO_ORDER
        }
        return views, None
    except Exception as exc:  # noqa: BLE001 — intentional fail-closed
        return None, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Phase 6A — Live macro data loader (fail-closed; cached 15 min).
#
# The actual data fetching lives entirely in lib/macro_data.py. This page only
# calls fetch_all_macro() + classify_regime(); it never imports a data-vendor SDK
# directly and never reads live workflow state. If the whole live fetch fails,
# the loader returns (None, None, error) and the page degrades to the fixture
# view below — it never crashes.
# ---------------------------------------------------------------------------

@st.cache_data(ttl=900, show_spinner=False)
def _load_live_macro():
    """Fetch live macro data + classify the regime. Returns ``(data, regime, err)``."""
    try:
        data = fetch_all_macro()
        regime = classify_regime(data)
        return data, regime, None
    except Exception as exc:  # noqa: BLE001 — fail-closed; never crash the page
        return None, None, f"{type(exc).__name__}: {exc}"


def _live_badge(source: str) -> str:
    """Return a small colored LIVE / FIXTURE pill for a metric group."""
    if source == "live":
        return _badge_html("● LIVE", _C_GREEN)
    return _badge_html("● FIXTURE", _C_AMBER)


def _lang() -> str:
    return st.session_state.get("language", "en")


def _loc(prefix: str, value) -> str:
    """Localize an enum / value via ``t()``; fall back to the raw value if the
    translation key is absent (so nothing renders as a bare key)."""
    key = f"{prefix}_{value}"
    s = t(key)
    return s if s != key else str(value)


# ---------------------------------------------------------------------------
# Phase 6A visual layer — semantic colors, colored badges, large numbers, the
# hero regime banner, and the collapsible trend table. Uses light inline HTML
# (no external CSS) so values pop and status labels carry color semantics.
# ---------------------------------------------------------------------------

_C_GREEN = "#3fb950"   # supportive / risk-on / favorable / positive
_C_RED = "#f85149"     # stressed / risk-off / unfavorable / negative
_C_AMBER = "#d29922"   # caution / transition / mixed
_C_GRAY = "#8b949e"    # neutral / unknown / muted

# Map regime / horizon-bias / status words to a semantic color.
_SEM_COLOR = {
    # supportive
    "risk_on": _C_GREEN, "favorable": _C_GREEN, "tight": _C_GREEN, "calm": _C_GREEN,
    "broad": _C_GREEN, "easing": _C_GREEN, "contained": _C_GREEN, "greed": _C_GREEN,
    "extreme_greed": _C_GREEN, "weakening": _C_GREEN,  # weaker broad dollar = risk-on lean
    "high": _C_GREEN,  # confidence
    # stressed
    "risk_off": _C_RED, "unfavorable": _C_RED, "wide": _C_RED, "stressed": _C_RED,
    "narrow": _C_RED, "tightening": _C_RED, "fear": _C_RED, "extreme_fear": _C_RED,
    "strengthening": _C_RED,
    # caution
    "transition": _C_AMBER, "cautious": _C_AMBER, "elevated": _C_AMBER, "mixed": _C_AMBER,
    "medium": _C_AMBER,  # confidence
    # neutral / unknown
    "degraded": _C_GRAY, "neutral": _C_GRAY, "normal": _C_GRAY, "moderate": _C_GRAY,
    "stable": _C_GRAY, "low": _C_GRAY, "unknown": _C_GRAY,
}


def _sem_color(word) -> str:
    return _SEM_COLOR.get(str(word), _C_GRAY)


def _num_color(value) -> str:
    """Green for positive, red for negative, neutral (theme default) otherwise."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "inherit"
    if v > 0:
        return _C_GREEN
    if v < 0:
        return _C_RED
    return "inherit"


def _badge_html(text: str, color: str) -> str:
    """A small colored pill badge."""
    return (
        f"<span style='background:{color}22;color:{color};padding:2px 10px;"
        f"border-radius:10px;font-size:0.82rem;font-weight:600;"
        f"border:1px solid {color}55;white-space:nowrap'>{text}</span>"
    )


def _sem_badge(prefix: str, value) -> str:
    """Localized, semantically-colored badge for a regime / bias / status value."""
    return _badge_html(_loc(prefix, value), _sem_color(value))


def _bignum(col, label: str, value, *, signed: bool = False) -> None:
    """Render a large (~1.5x) metric value: green/red when ``signed`` and the
    value is positive/negative, otherwise the theme's default text color."""
    color = _num_color(value) if signed else "inherit"
    # 1.6rem, monospace with tabular figures so numbers align and stay in scale
    # with the page's type hierarchy (see ui_utils --font-mono).
    col.markdown(
        f"<div style='line-height:1.1;margin:2px 0 6px 0'>"
        f"<div style='font-size:1.6rem;font-weight:700;color:{color};"
        f"font-family:var(--font-mono);font-variant-numeric:tabular-nums'>{_fmt(value)}</div>"
        f"<div style='font-size:0.8rem;color:{_C_GRAY}'>{label}</div></div>",
        unsafe_allow_html=True,
    )


def _spacer(px: int = 10) -> None:
    st.markdown(f"<div style='height:{px}px'></div>", unsafe_allow_html=True)


def _line_color(value) -> str:
    """Line color by the indicator's positive/negative semantic:
    green when the latest value is positive, red when negative, gray at zero."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _C_GRAY
    if v > 0:
        return _C_GREEN
    if v < 0:
        return _C_RED
    return _C_GRAY


# 10Y / 2Y / spread share one trend table; each gets its own colored line chart.
_RATES_CHARTS = ("10Y", "2Y", "spread")


def _trend_chart(history: list, value_key: str, color: str):
    """Build a simple 200px line chart (X=date, Y=value_key) from history rows.

    Style: no legend, no gridlines, line color = the indicator's pos/neg
    semantic. Reuses the global apply_layout()/apply_legend() for theme
    consistency, then strips chrome for a clean sparkline-style trend.
    Returns ``None`` if there are fewer than 2 points to plot.
    """
    xs = [h.get("date") for h in history if h.get(value_key) is not None]
    ys = [h.get(value_key) for h in history if h.get(value_key) is not None]
    if len(ys) < 2:
        return None
    fig = go.Figure(
        go.Scatter(
            x=xs, y=ys, mode="lines+markers",
            line=dict(color=color, width=2),
            marker=dict(size=4, color=color),
            hovertemplate="%{x} · %{y}<extra></extra>",
        )
    )
    apply_layout(fig, height=200)
    apply_legend(fig)
    # Simple style: no legend, no gridlines, tight margins.
    fig.update_layout(showlegend=False, title=None, margin=dict(l=6, r=6, t=6, b=6))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False)
    return fig


def _plot_trend(history: list, value_key: str, label: str = "", key: str = "") -> None:
    vals = [h[value_key] for h in history if h.get(value_key) is not None]
    if len(vals) < 2:
        return
    fig = _trend_chart(history, value_key, _line_color(vals[-1]))
    if fig is None:
        return
    if label:
        st.caption(label)
    # A unique key avoids StreamlitDuplicateElementId when two charts share data.
    st.plotly_chart(
        fig, use_container_width=True, config={"displayModeBar": False},
        key=f"macro_trend_{key or value_key}",
    )


def _render_trend(history: list, charts=None, key_prefix: str = "trend") -> None:
    """Collapsible recent-history trend block (default collapsed): one or more
    line charts above the data table. Data comes from the already-fetched series
    in lib/macro_data — no new API calls.

    ``charts``: keys to plot above the table. Defaults to the single "value"
    series; pass e.g. ``("10Y", "2Y", "spread")`` for the multi-column rates rows.
    """
    with st.expander(t("macro_trend_header"), expanded=False):
        if not history:
            st.caption(t("macro_trend_no_data"))
            return
        specs = charts if charts is not None else ("value",)
        for key in specs:
            if any(key in h for h in history):
                _plot_trend(
                    history, key,
                    label="" if key == "value" else key,
                    key=f"{key_prefix}_{key}",
                )
        # Data table (generalized: {date,value} or multi-column rows).
        rows = []
        for h in history:
            if "value" in h:
                rows.append(
                    {t("macro_trend_date"): h.get("date", "—"),
                     t("macro_trend_value"): h.get("value", "—")}
                )
            else:
                row = {t("macro_trend_date"): h.get("date", "—")}
                for k, v in h.items():
                    if k != "date":
                        row[k] = v
                rows.append(row)
        st.table(rows)


def _render_etf_trend(etf, key_prefix: str = "etf") -> None:
    """Collapsible per-ETF cumulative-return trend charts (default collapsed).

    One small line chart per proxy (QQQ/IWM/SPY/GLD/USO/TLT/HYG), laid out two
    per row; line color follows the latest cumulative return's sign.
    """
    with st.expander(t("macro_trend_header"), expanded=False):
        hist = etf.history or {}
        tickers = [tkr for tkr in ("QQQ", "IWM", "SPY", "GLD", "USO", "TLT", "HYG") if hist.get(tkr)]
        if not tickers:
            st.caption(t("macro_trend_no_data"))
            return
        for i in range(0, len(tickers), 2):
            cols = st.columns(2)
            for j, tkr in enumerate(tickers[i:i + 2]):
                with cols[j]:
                    _plot_trend(hist[tkr], "value", label=tkr, key=f"{key_prefix}_{tkr}")


def _releases_change_series(history: list, key: str, mode: str) -> list:
    """Derive a month-over-month series from the level history rows.

    ``mode="diff"`` → level change (NFP payroll adds); ``mode="pct"`` → MoM %
    (CPI / PPI). Oldest->newest; first month dropped (no prior month)."""
    out = []
    prev = None
    for row in history:
        v = row.get(key)
        if v is None:
            prev = None
            continue
        if prev is not None:
            if mode == "diff":
                out.append({"date": row.get("date", "—"), "value": round(v - prev, 1)})
            elif prev:
                out.append({"date": row.get("date", "—"), "value": round((v / prev - 1.0) * 100.0, 2)})
        prev = v
    return out


def _render_releases_trend(rel, key_prefix: str = "ind_rel") -> None:
    """Collapsible economic-release trend charts (default collapsed): NFP monthly
    change, CPI MoM %, PPI MoM % — derived from the already-fetched FRED levels
    (no new API calls) — above the levels table."""
    with st.expander(t("macro_trend_header"), expanded=False):
        hist = rel.history or []
        if not hist:
            st.caption(t("macro_trend_no_data"))
            return
        for label_key, key, mode, ckey in (
            ("macro_live_nfp_chg", "NFP", "diff", "nfp"),
            ("macro_live_cpi_mom", "CPI", "pct", "cpi"),
            ("macro_live_ppi_mom", "PPI", "pct", "ppi"),
        ):
            _plot_trend(
                _releases_change_series(hist, key, mode), "value",
                label=t(label_key), key=f"{key_prefix}_{ckey}",
            )
        # Levels table (date + NFP / CPI / PPI).
        rows = [
            {
                t("macro_trend_date"): h.get("date", "—"),
                "NFP": h.get("NFP", "—"), "CPI": h.get("CPI", "—"), "PPI": h.get("PPI", "—"),
            }
            for h in hist
        ]
        st.table(rows)


def _render_hero(data, regime) -> None:
    """Prominent top-of-page regime banner: large regime label on a colored
    background, with confidence, coverage and snapshot time."""
    color = _sem_color(regime.regime)
    regime_label = _loc("macro_regimeval", regime.regime)
    conf = _loc("macro_confval", regime.confidence)
    cov = f"{data.data_coverage * 100:.0f}%"
    st.markdown(
        f"<div style='background:{color}1f;border:1px solid {color}55;"
        f"border-left:6px solid {color};border-radius:12px;padding:14px 20px;"
        f"margin:4px 0 10px 0'>"
        f"<div style='font-size:0.8rem;color:{_C_GRAY};letter-spacing:0.06em;"
        f"text-transform:uppercase'>{t('macro_hero_label')}</div>"
        f"<div style='font-size:1.9rem;font-weight:800;color:{color};"
        f"line-height:1.15'>{regime_label}</div>"
        f"<div style='font-size:0.95rem;color:{_C_GRAY};margin-top:4px'>"
        f"{t('macro_live_confidence_label')}: <b>{conf}</b> &nbsp;·&nbsp; "
        f"{t('macro_live_coverage_label')}: <b>{cov}</b> &nbsp;·&nbsp; "
        f"{t('macro_live_updated_label')}: {data.timestamp}</div>"
        f"<div style='font-size:0.8rem;color:{_C_GRAY};margin-top:6px'>"
        f"{t('macro_hero_caption')}</div></div>",
        unsafe_allow_html=True,
    )


def _fmt(value, suffix: str = "") -> str:
    if value is None:
        return "—"
    return f"{value}{suffix}"


def _render_live_group_header(title: str, source: str) -> None:
    """Terminal-style card header: title on the left, a small colored LIVE /
    FIXTURE tag top-right. A fixture fallback shows a single muted inline note."""
    cols = st.columns([5, 1])
    cols[0].markdown(f"**{title}**")
    cols[1].markdown(_live_badge(source), unsafe_allow_html=True)
    if source != "live":
        st.caption(f"⚠️ {t('macro_live_fallback_note')}")


# ---------------------------------------------------------------------------
# Signal localization (parallel structured signals + English canonical text)
# ---------------------------------------------------------------------------

def _signal_line(sig: dict, en_text: str) -> str:
    """Render one regime signal localized for the current language."""
    code = sig.get("code", "")
    if _lang() == "zh":
        key = f"macro_sig_{code}"
        tmpl = t(key)
        if tmpl != key:
            try:
                return tmpl.format(**(sig.get("values") or {}))
            except Exception:  # noqa: BLE001 — fall back to canonical English
                return en_text
    return en_text


def _render_filtered_signals(regime, codes) -> None:
    """Render the localized signal lines whose code is in ``codes``."""
    sigs = regime.signals or []
    ens = regime.key_signals or []
    lines = [
        _signal_line(sig, ens[i] if i < len(ens) else "")
        for i, sig in enumerate(sigs)
        if sig.get("code") in codes
    ]
    if lines:
        st.markdown(f"**{t('macro_live_section_signals')}**")
        for ln in lines:
            st.markdown(f"- {ln}")


def _render_live_signals(regime) -> None:
    """Render every localized regime signal line."""
    sigs = regime.signals or []
    ens = regime.key_signals or []
    if not sigs:
        return
    st.markdown(f"**{t('macro_live_section_signals')}**")
    for i, sig in enumerate(sigs):
        st.markdown(f"- {_signal_line(sig, ens[i] if i < len(ens) else '')}")


def _posture_text(regime) -> str:
    """Localized opportunity posture (falls back to canonical English)."""
    if _lang() == "zh":
        key = f"macro_posture_text_{regime.regime}"
        s = t(key)
        if s != key:
            return s
    return regime.opportunity_posture or ""


# ---------------------------------------------------------------------------
# Deterministic status words derived from the live data (localized via t()).
# These power the sub-regime readouts so the bottom blocks reflect real data
# instead of placeholder descriptors. Thresholds mirror lib/macro_regime.py.
# ---------------------------------------------------------------------------

def _status_rates(rates) -> str:
    y = rates.yield_10y
    if y is None:
        return "unknown"
    if y >= 4.5:
        return "elevated"
    if y >= 3.0:
        return "moderate"
    return "low"


def _status_inflation(rates) -> str:
    be = rates.breakeven_10y
    if be is None:
        return "unknown"
    if be >= 2.5:
        return "elevated"
    if be >= 2.0:
        return "moderate"
    return "contained"


def _status_liquidity(dollar, credit) -> str:
    chg = dollar.change_1m
    hy = credit.hy_spread
    if (chg is not None and chg > 1.0) or (hy is not None and hy > 5.0):
        return "tightening"
    if (chg is not None and chg < -1.0) and (hy is not None and hy < 3.5):
        return "easing"
    return "neutral"


def _status_credit(credit) -> str:
    hy = credit.hy_spread
    if hy is None:
        return "unknown"
    if hy < 3.5:
        return "tight"
    if hy > 5.0:
        return "wide"
    return "normal"


def _status_vol(vix) -> str:
    v = vix.value
    if v is None:
        return "unknown"
    if v < 18:
        return "calm"
    if v > 27:
        return "stressed"
    return "moderate"


def _status_breadth(etf) -> str:
    spy = (etf.returns_1m or {}).get("SPY")
    iwm = (etf.returns_1m or {}).get("IWM")
    if spy is None or iwm is None:
        return "unknown"
    if spy > 0 and iwm > 0:
        return "broad"
    if spy < 0 and iwm < 0:
        return "narrow"
    return "mixed"


def _status_dollar(dollar) -> str:
    chg = dollar.change_1m
    if chg is None:
        return "unknown"
    if chg > 1.0:
        return "strengthening"
    if chg < -1.0:
        return "weakening"
    return "stable"


def _status_risk(vix) -> str:
    fg = vix.fear_greed
    if fg is None:
        return "unknown"
    if fg > 60:
        return "greed"
    if fg < 40:
        return "fear"
    return "neutral"


def _domain_status_line(domain_key: str, status_word: str) -> None:
    st.markdown(
        f"**{t(domain_key)}** &nbsp; {_sem_badge('macro_status', status_word)}",
        unsafe_allow_html=True,
    )


def _labeled_badge(col, label: str, prefix: str, value) -> None:
    """Small caption label + a semantically-colored value badge in a column."""
    col.markdown(
        f"<div style='font-size:0.8rem;color:{_C_GRAY};margin-bottom:2px'>{label}</div>"
        f"{_sem_badge(prefix, value)}",
        unsafe_allow_html=True,
    )


def _render_live_horizon_metrics(regime) -> None:
    hb = regime.horizon_bias or {}
    st.markdown(f"**{t('macro_live_horizon_label')}**")
    cols = st.columns(3)
    _labeled_badge(cols[0], t("macro_horizon_short"), "macro_biasval", hb.get("short", "—"))
    _labeled_badge(cols[1], t("macro_horizon_mid"), "macro_biasval", hb.get("mid", "—"))
    _labeled_badge(cols[2], t("macro_horizon_long"), "macro_biasval", hb.get("long", "—"))


def _regime_headline(data, regime) -> None:
    cols = st.columns([2, 2, 1])
    _labeled_badge(cols[0], t("macro_live_overview_regime"), "macro_regimeval", regime.regime)
    _labeled_badge(cols[1], t("macro_live_confidence_label"), "macro_confval", regime.confidence)
    _bignum(cols[2], t("macro_live_coverage_label"), f"{data.data_coverage * 100:.0f}%")


# ---------------------------------------------------------------------------
# Phase 6A — live tab renderers (terminal-style, fully localized, real data).
# ---------------------------------------------------------------------------

def _render_live_overview(data, regime) -> None:
    """User-facing intro page: a single dynamic data-mode banner, then three
    concise blocks (current market state, what this page covers, data sources),
    and one short disclaimer. No developer guardrail bullets, no duplicate regime
    block (the regime is shown once here in block 1)."""
    st.subheader(t("macro_tab_overview"))

    # One merged data-mode banner, driven by live mode + actual coverage.
    if MACRO_LIVE_MODE and data.data_coverage >= 0.5:
        st.success(t("macro_banner_live"))
    else:
        st.warning(t("macro_banner_degraded"))

    # Block 1 — current market state: regime + confidence + horizon bias.
    st.markdown(f"#### {t('macro_ov_state')}")
    _regime_headline(data, regime)
    _render_live_horizon_metrics(regime)

    # Block 2 — the analysis dimensions this page covers (one line each).
    st.markdown(f"#### {t('macro_ov_dimensions')}")
    for _k in (
        "macro_ov_dim_rates", "macro_ov_dim_credit", "macro_ov_dim_vol",
        "macro_ov_dim_etf", "macro_ov_dim_econ", "macro_ov_dim_sentiment",
    ):
        st.markdown(f"- {t(_k)}")

    # Block 3 — data sources & update frequency (one line, no endpoints).
    st.markdown(f"#### {t('macro_ov_sources')}")
    st.caption(t("macro_ov_sources_desc"))

    # Single short disclaimer (the only safety line on this intro page).
    st.caption(t("macro_safety_headline"))


def _render_live_regime(data, regime) -> None:
    st.subheader(t("macro_tab_regime"))
    st.caption(t("macro_live_regime_readout"))
    _regime_headline(data, regime)
    st.markdown(f"**{t('macro_live_posture_label')}**")
    st.caption(_posture_text(regime))
    _render_live_horizon_metrics(regime)
    _render_live_signals(regime)
    st.markdown(f"**{t('macro_live_regime_readout')}**")
    _domain_status_line("macro_live_domain_rates", _status_rates(data.rates))
    _domain_status_line("macro_live_domain_inflation", _status_inflation(data.rates))
    _domain_status_line("macro_live_domain_liquidity", _status_liquidity(data.dollar, data.credit))
    _domain_status_line("macro_live_domain_credit", _status_credit(data.credit))
    _domain_status_line("macro_live_domain_volatility", _status_vol(data.vix))
    _domain_status_line("macro_live_domain_breadth", _status_breadth(data.etf_returns))
    _domain_status_line("macro_live_domain_dollar", _status_dollar(data.dollar))
    _domain_status_line("macro_live_domain_risk", _status_risk(data.vix))


def _render_live_indicators(data, regime) -> None:
    st.subheader(t("macro_tab_indicators"))
    st.caption(t("macro_live_caption"))
    cov = st.columns([1, 3])
    _bignum(cov[0], t("macro_live_coverage_label"), f"{data.data_coverage * 100:.0f}%")
    cov[1].caption(f"{t('macro_live_updated_label')}: `{data.timestamp}`")
    _spacer(6)

    # VIX — big level + signed 1M change + fear/greed; trend + source collapsed.
    vix = data.vix
    with st.container(border=True):
        _render_live_group_header(t("macro_live_grp_vix"), vix.data_source)
        cc = st.columns(3)
        _bignum(cc[0], t("macro_live_vix"), vix.value)
        _bignum(cc[1], t("macro_live_vix_chg"), vix.change_1m, signed=True)
        _bignum(cc[2], t("macro_live_feargreed"), vix.fear_greed)
        _render_trend(vix.history, key_prefix="ind_vix")
        with st.expander(t("macro_live_details")):
            st.caption(f"{t('macro_live_freshness_label')}: `{vix.as_of or '—'}`")
            st.caption(t("macro_live_fear_greed_proxy_note"))
    _spacer()

    # Rates — 10Y headline + 2Y + signed curve spread; breakeven muted; trend.
    rates = data.rates
    with st.container(border=True):
        _render_live_group_header(t("macro_live_grp_rates"), rates.data_source)
        rc = st.columns(3)
        _bignum(rc[0], t("macro_live_y10"), rates.yield_10y)
        _bignum(rc[1], t("macro_live_y2"), rates.yield_2y)
        _bignum(rc[2], t("macro_live_spread"), rates.spread_10y_2y, signed=True)
        st.caption(f"{t('macro_live_breakeven')}: {_fmt(rates.breakeven_10y)}")
        _render_trend(rates.history, charts=_RATES_CHARTS, key_prefix="ind_rates")
        with st.expander(t("macro_live_details")):
            st.caption(f"{t('macro_live_freshness_label')}: `{rates.as_of or '—'}`")
    _spacer()

    # Credit — single headline number + trend.
    credit = data.credit
    with st.container(border=True):
        _render_live_group_header(t("macro_live_grp_credit"), credit.data_source)
        cc = st.columns(3)
        _bignum(cc[0], t("macro_live_hy"), credit.hy_spread)
        _render_trend(credit.history, key_prefix="ind_credit")
        with st.expander(t("macro_live_details")):
            st.caption(f"{t('macro_live_freshness_label')}: `{credit.as_of or '—'}`")
    _spacer()

    # Dollar — index headline + signed 1M change + trend.
    dollar = data.dollar
    with st.container(border=True):
        _render_live_group_header(t("macro_live_grp_dollar"), dollar.data_source)
        dc = st.columns(3)
        _bignum(dc[0], t("macro_live_dxy"), dollar.value)
        _bignum(dc[1], t("macro_live_dxy_chg"), dollar.change_1m, signed=True)
        _render_trend(dollar.history, key_prefix="ind_dollar")
        with st.expander(t("macro_live_details")):
            st.caption(f"{t('macro_live_freshness_label')}: `{dollar.as_of or '—'}`")
    _spacer()

    # ETF returns — compact table (terminal style, low noise).
    etf = data.etf_returns
    with st.container(border=True):
        _render_live_group_header(t("macro_live_grp_etf"), etf.data_source)
        rows = [
            {
                "ticker": tkr,
                t("macro_live_etf_1m"): (etf.returns_1m or {}).get(tkr, "—"),
                t("macro_live_etf_3m"): (etf.returns_3m or {}).get(tkr, "—"),
            }
            for tkr in ("QQQ", "IWM", "SPY", "GLD", "USO", "TLT", "HYG")
        ]
        st.table(rows)
        _render_etf_trend(etf, key_prefix="ind_etf")
        with st.expander(t("macro_live_details")):
            st.caption(f"{t('macro_live_freshness_label')}: `{etf.as_of or '—'}`")
    _spacer()

    # Economic releases — three big headline numbers + month-aligned trend.
    rel = data.economic_releases
    with st.container(border=True):
        _render_live_group_header(t("macro_live_grp_releases"), rel.data_source)
        rc = st.columns(3)
        _bignum(rc[0], t("macro_live_nfp"), rel.nfp)
        _bignum(rc[1], t("macro_live_cpi"), rel.cpi)
        _bignum(rc[2], t("macro_live_ppi"), rel.ppi)
        _render_releases_trend(rel, key_prefix="ind_rel")
        with st.expander(t("macro_live_details")):
            st.caption(
                f"NFP `{rel.nfp_date or '—'}` · CPI `{rel.cpi_date or '—'}` · "
                f"PPI `{rel.ppi_date or '—'}`"
            )
    _spacer()

    # Market sentiment — score headline + colored localized bucket; headlines collapsed.
    sent = data.sentiment
    with st.container(border=True):
        _render_live_group_header(t("macro_live_grp_sentiment"), sent.data_source)
        sc = st.columns(2)
        _bignum(sc[0], t("macro_live_sentiment_score"), sent.score)
        if sent.label:
            _labeled_badge(sc[1], t("macro_live_status_label"), "macro_status", sent.label)
        else:
            sc[1].caption("—")
        if sent.news_headlines:
            with st.expander(t("macro_live_details")):
                for hl in sent.news_headlines[:5]:
                    st.caption(f"📰 {hl}")


def _render_live_liquidity(data, regime) -> None:
    st.subheader(t("macro_tab_liquidity"))
    rates = data.rates
    _render_live_group_header(t("macro_live_grp_rates"), rates.data_source)
    rc = st.columns(4)
    _bignum(rc[0], t("macro_live_y10"), rates.yield_10y)
    _bignum(rc[1], t("macro_live_y2"), rates.yield_2y)
    _bignum(rc[2], t("macro_live_spread"), rates.spread_10y_2y, signed=True)
    _bignum(rc[3], t("macro_live_breakeven"), rates.breakeven_10y)
    _render_trend(rates.history, charts=_RATES_CHARTS, key_prefix="liq_rates")
    _domain_status_line("macro_live_domain_rates", _status_rates(rates))
    _domain_status_line("macro_live_domain_inflation", _status_inflation(rates))
    _domain_status_line("macro_live_domain_liquidity", _status_liquidity(data.dollar, data.credit))
    _render_filtered_signals(
        regime, {"curve_inverted", "curve_steep", "dollar_strong", "dollar_weak"}
    )


def _render_live_credit(data, regime) -> None:
    st.subheader(t("macro_tab_credit"))
    credit = data.credit
    vix = data.vix
    dollar = data.dollar
    cols = st.columns(3)
    _bignum(cols[0], t("macro_live_hy"), credit.hy_spread)
    _bignum(cols[1], t("macro_live_vix"), vix.value)
    _bignum(cols[2], t("macro_live_dxy"), dollar.value)
    _domain_status_line("macro_live_domain_credit", _status_credit(credit))
    _domain_status_line("macro_live_domain_volatility", _status_vol(vix))
    _domain_status_line("macro_live_domain_breadth", _status_breadth(data.etf_returns))
    _domain_status_line("macro_live_domain_dollar", _status_dollar(dollar))
    _render_filtered_signals(
        regime,
        {
            "credit_tight", "credit_wide", "vix_low", "vix_high", "vix_mid",
            "breadth_broad", "breadth_weak", "breadth_mixed",
        },
    )


def _render_live_risk(data, regime) -> None:
    st.subheader(t("macro_tab_risk"))
    vix = data.vix
    sent = data.sentiment
    cols = st.columns(2)
    _bignum(cols[0], t("macro_live_feargreed"), vix.fear_greed)
    _bignum(cols[1], t("macro_live_sentiment_score"), sent.score)
    _domain_status_line("macro_live_domain_risk", _status_risk(vix))
    _render_filtered_signals(regime, {"fg_greed", "fg_fear"})
    st.caption(t("macro_live_fear_greed_proxy_note"))


def _render_live_horizon(data, regime) -> None:
    st.subheader(t("macro_tab_horizon"))
    st.info(t("macro_horizon_not_decision"))
    _render_live_horizon_metrics(regime)
    st.markdown(f"**{t('macro_horizon_rationale')}**")
    st.caption(_posture_text(regime))


def _render_live_themes(data, regime) -> None:
    st.subheader(t("macro_tab_themes"))
    st.caption(t("macro_live_theme_caption"))
    st.markdown(f"- {t(f'macro_theme_impl_{regime.regime}')}")


def _render_live_posture(data, regime) -> None:
    st.subheader(t("macro_tab_posture"))
    _regime_headline(data, regime)
    st.markdown(f"**{t('macro_posture_primary')}**")
    st.caption(_posture_text(regime))
    _render_live_horizon_metrics(regime)
    # Review-only boundary (kept verbatim; never authorizes execution).
    st.info(t("macro_posture_not_decision"))


def _render_live_provenance(data, regime) -> None:
    st.subheader(t("macro_tab_provenance"))
    st.caption(t("macro_live_mode_caption"))
    cov = st.columns(2)
    cov[0].metric(t("macro_live_coverage_label"), f"{data.data_coverage * 100:.0f}%")
    cov[1].metric(t("macro_live_updated_label"), data.timestamp)
    rows = []
    for label_key, grp in (
        ("macro_live_grp_vix", data.vix),
        ("macro_live_grp_rates", data.rates),
        ("macro_live_grp_credit", data.credit),
        ("macro_live_grp_dollar", data.dollar),
        ("macro_live_grp_etf", data.etf_returns),
        ("macro_live_grp_releases", data.economic_releases),
        ("macro_live_grp_sentiment", data.sentiment),
    ):
        rows.append(
            {
                "group": t(label_key),
                "data_source": grp.data_source,
                t("macro_live_freshness_label"): getattr(grp, "as_of", None) or "—",
            }
        )
    st.table(rows)
    st.info(t("macro_live_safety"))


def _render_live_tabs(data, regime) -> None:
    """Render the full live, real-data macro dashboard across the ten tabs."""
    # Hero regime banner — top of page, most prominent (large + colored).
    _render_hero(data, regime)
    tab_labels = [
        t("macro_tab_overview"),
        t("macro_tab_regime"),
        t("macro_tab_indicators"),
        t("macro_tab_liquidity"),
        t("macro_tab_credit"),
        t("macro_tab_risk"),
        t("macro_tab_horizon"),
        t("macro_tab_themes"),
        t("macro_tab_posture"),
        t("macro_tab_provenance"),
    ]
    tabs = st.tabs(tab_labels)
    with tabs[0]:
        _render_live_overview(data, regime)
    with tabs[1]:
        _render_live_regime(data, regime)
    with tabs[2]:
        _render_live_indicators(data, regime)
    with tabs[3]:
        _render_live_liquidity(data, regime)
    with tabs[4]:
        _render_live_credit(data, regime)
    with tabs[5]:
        _render_live_risk(data, regime)
    with tabs[6]:
        _render_live_horizon(data, regime)
    with tabs[7]:
        _render_live_themes(data, regime)
    with tabs[8]:
        _render_live_posture(data, regime)
    with tabs[9]:
        _render_live_provenance(data, regime)


# ---------------------------------------------------------------------------
# Safety banner (shared with Overview tab)
# ---------------------------------------------------------------------------

_SAFETY_BULLET_KEYS = (
    "macro_safety_b1",
    "macro_safety_b2",
    "macro_safety_b3",
    "macro_safety_b4",
    "macro_safety_b5",
    "macro_safety_b6",
)


def _render_demo_walkthrough() -> None:
    """Phase 5R — concise "How to read this page" / demo walkthrough.

    Demo-readiness only. Explains the fixture-only, macro-first context,
    review-only nature of the dashboard and the order in which the tabs are
    meant to be read. No onboarding/persistence system is introduced; nothing
    here is stored and the copy is static (routed through ``t()``).
    """
    with st.expander(t("macro_walkthrough_header")):
        st.caption(t("macro_walkthrough_intro"))
        for key in (
            "macro_walkthrough_step1",
            "macro_walkthrough_step2",
            "macro_walkthrough_step3",
            "macro_walkthrough_step4",
            "macro_walkthrough_step5",
        ):
            st.markdown(f"- {t(key)}")
        st.info(t("macro_walkthrough_safety"))


def _render_safety_banner() -> None:
    st.warning(t("macro_safety_headline"))
    for key in _SAFETY_BULLET_KEYS:
        st.markdown(f"- {t(key)}")


def _render_factor(factor: MacroRegimeFactorView) -> None:
    st.markdown(f"**`{factor.factor}`** — {factor.label}")
    cols = st.columns(3)
    cols[0].metric(t("macro_factor_trend"), factor.trend)
    cols[1].metric(t("macro_factor_signal"), factor.signal)
    cols[2].metric(
        t("macro_factor_value"),
        factor.value_placeholder if factor.value_placeholder else "—",
    )
    st.caption(factor.description or "")


# ---------------------------------------------------------------------------
# 1. Overview / Safety
# ---------------------------------------------------------------------------

def _render_overview_section(view: MacroDashboardView) -> None:
    st.subheader(t("macro_tab_overview"))
    st.info(t("macro_overview_caption"))
    st.caption(t("macro_overview_first_class"))
    _render_safety_banner()

    st.markdown("---")
    rs = view.regime_snapshot.regime_status
    cols = st.columns(3)
    cols[0].metric(t("macro_overview_regime_status"), rs.primary_status)
    cols[1].metric(t("macro_overview_confidence"), rs.confidence)
    cols[2].metric(t("macro_overview_scenario_kind"), view.scenario_kind)
    st.caption(f"{t('macro_overview_as_of')}: `{view.as_of or '—'}`")
    st.caption(rs.description or "")

    if view.warnings:
        st.info(t("macro_overview_warnings"))
        for w in view.warnings:
            st.markdown(f"- `{w.warning_type}` ({w.severity}): {w.message}")


# ---------------------------------------------------------------------------
# 2. Macro Regime
# ---------------------------------------------------------------------------

def _render_regime_section(snapshot: MacroRegimeSnapshot) -> None:
    st.subheader(t("macro_tab_regime"))
    st.caption(t("macro_regime_caption"))

    rs = snapshot.regime_status
    cols = st.columns(2)
    cols[0].markdown(f"**{t('macro_regime_primary')}**: `{rs.primary_status}`")
    cols[1].markdown(
        f"**{t('macro_regime_supporting')}**: "
        f"`{', '.join(rs.supporting_statuses) if rs.supporting_statuses else '—'}`"
    )
    st.caption(rs.label or "")

    if not snapshot.factors:
        st.info(t("macro_regime_no_factors"))
        return

    for factor in snapshot.factors:
        with st.container(border=True):
            _render_factor(factor)


# ---------------------------------------------------------------------------
# 3. Liquidity / Rates / Inflation
# ---------------------------------------------------------------------------

def _render_liquidity_section(snapshot: MacroRegimeSnapshot) -> None:
    st.subheader(t("macro_tab_liquidity"))
    st.caption(t("macro_liquidity_caption"))

    liq = snapshot.liquidity
    st.markdown(f"#### {t('macro_liquidity_header')}")
    st.caption(
        f"{t('macro_liquidity_trend')}: `{liq.liquidity_trend}` · "
        f"{t('macro_section_overall_signal')}: `{liq.overall_signal}`"
    )
    with st.container(border=True):
        _render_factor(liq.liquidity)
    st.caption(liq.summary or "")

    ri = snapshot.rates_inflation
    st.markdown(f"#### {t('macro_rates_header')} / {t('macro_inflation_header')}")
    st.caption(f"{t('macro_section_overall_signal')}: `{ri.overall_signal}`")
    cols = st.columns(2)
    with cols[0]:
        with st.container(border=True):
            _render_factor(ri.rates)
    with cols[1]:
        with st.container(border=True):
            _render_factor(ri.inflation)
    st.caption(ri.summary or "")


# ---------------------------------------------------------------------------
# 4. Credit / Volatility / Breadth
# ---------------------------------------------------------------------------

def _render_credit_section(snapshot: MacroRegimeSnapshot) -> None:
    st.subheader(t("macro_tab_credit"))
    st.caption(t("macro_credit_caption"))

    cv = snapshot.credit_volatility
    st.caption(f"{t('macro_section_overall_signal')}: `{cv.overall_signal}`")
    cols = st.columns(2)
    with cols[0]:
        st.markdown(f"**{t('macro_credit_header')}**")
        with st.container(border=True):
            _render_factor(cv.credit_spreads)
    with cols[1]:
        st.markdown(f"**{t('macro_volatility_header')}**")
        with st.container(border=True):
            _render_factor(cv.volatility)
    st.caption(cv.summary or "")

    br = snapshot.market_breadth
    st.markdown(f"#### {t('macro_breadth_header')}")
    st.caption(f"{t('macro_section_overall_signal')}: `{br.overall_signal}`")
    with st.container(border=True):
        _render_factor(br.breadth)
    st.caption(br.summary or "")

    # Dollar is a closely related cross-asset confirm signal.
    dl = snapshot.dollar
    st.markdown(f"#### {t('macro_dollar_header')}")
    st.caption(f"{t('macro_section_overall_signal')}: `{dl.overall_signal}`")
    with st.container(border=True):
        _render_factor(dl.dollar)
    st.caption(dl.summary or "")


# ---------------------------------------------------------------------------
# 5. Risk Appetite
# ---------------------------------------------------------------------------

def _render_risk_section(snapshot: MacroRegimeSnapshot) -> None:
    st.subheader(t("macro_tab_risk"))
    st.caption(t("macro_risk_caption"))

    ra = snapshot.risk_appetite
    cols = st.columns(2)
    cols[0].metric(t("macro_risk_state"), ra.risk_state)
    cols[1].metric(t("macro_section_overall_signal"), ra.overall_signal)
    with st.container(border=True):
        _render_factor(ra.risk_appetite)
    st.caption(ra.summary or "")

    # Earnings cycle + growth regime round out the risk-appetite picture.
    ec = snapshot.earnings_cycle
    st.markdown(f"#### {t('macro_earnings_header')}")
    st.caption(
        f"revision_direction: `{ec.revision_direction}` · "
        f"{t('macro_section_overall_signal')}: `{ec.overall_signal}`"
    )
    with st.container(border=True):
        _render_factor(ec.earnings_cycle)
    st.caption(ec.summary or "")

    st.markdown(f"#### {t('macro_regime_growth')}")
    with st.container(border=True):
        _render_factor(snapshot.growth_regime)

    pr = snapshot.policy_risk
    st.markdown(f"#### {t('macro_policy_header')}")
    st.caption(f"{t('macro_section_overall_signal')}: `{pr.overall_signal}`")
    with st.container(border=True):
        _render_factor(pr.policy_risk)
    st.caption(pr.summary or "")


# ---------------------------------------------------------------------------
# 6. Horizon Bias
# ---------------------------------------------------------------------------

def _render_indicator(ind: MacroIndicatorView) -> None:
    st.markdown(f"**{ind.display_name}** — `{ind.indicator_key}`")
    cols = st.columns(4)
    cols[0].metric(t("macro_ind_value"), ind.latest_value or ind.fixture_value or "—")
    cols[1].metric(t("macro_ind_trend"), ind.trend)
    cols[2].metric(t("macro_ind_signal"), ind.signal)
    cols[3].metric(t("macro_ind_status"), ind.status or "—")
    st.caption(f"{t('macro_ind_interpretation')}: {ind.interpretation or '—'}")
    st.caption(f"{t('macro_ind_macro_implication')}: {ind.macro_implication or '—'}")
    st.caption(f"{t('macro_ind_horizon_implication')}: {ind.horizon_implication or '—'}")
    # Fixture-only marker — never live data.
    st.caption(
        f"{t('macro_ind_category')}: `{ind.category}` · "
        f"source_type=`{ind.source_type}` · is_live_data=`{ind.is_live_data}`"
    )
    for w in ind.warnings:
        st.markdown(f"- ⚠️ `{w.warning_type}` ({w.severity}): {w.message}")


def _render_indicators_section(panel: MacroIndicatorPanel) -> None:
    st.subheader(t("macro_tab_indicators"))
    st.caption(t("macro_indicators_caption"))
    st.info(t("macro_indicators_not_live"))

    if panel.summary:
        st.caption(f"{t('macro_section_summary')}: {panel.summary}")
    st.caption(f"{t('macro_section_overall_signal')}: `{panel.overall_signal}`")

    # Commodities — WTI, Gold.
    st.markdown(f"#### {t('macro_indicators_commodities_header')}")
    if panel.commodities:
        for ind in panel.commodities:
            with st.container(border=True):
                _render_indicator(ind)
    else:
        st.info(t("macro_indicators_no_data"))

    # Risk appetite / leadership — CNN Fear & Greed, QQQ, IWM.
    st.markdown(f"#### {t('macro_indicators_risk_header')}")
    _risk_inds: list[MacroIndicatorView] = []
    if panel.fear_greed is not None:
        _risk_inds.append(panel.fear_greed)
    _risk_inds.extend(panel.index_leadership)
    if _risk_inds:
        for ind in _risk_inds:
            with st.container(border=True):
                _render_indicator(ind)
    else:
        st.info(t("macro_indicators_no_data"))

    # Economic releases — NFP, CPI, PPI.
    st.markdown(f"#### {t('macro_indicators_releases_header')}")
    _release_inds: list[MacroIndicatorView] = list(panel.labor_releases) + list(
        panel.inflation_releases
    )
    if _release_inds:
        for ind in _release_inds:
            with st.container(border=True):
                _render_indicator(ind)
    else:
        st.info(t("macro_indicators_no_data"))


def _render_horizon_section(view: MacroDashboardView) -> None:
    st.subheader(t("macro_tab_horizon"))
    st.caption(t("macro_horizon_caption"))
    st.info(t("macro_horizon_not_decision"))

    hb = view.horizon_bias
    cols = st.columns(3)
    cols[0].metric(t("macro_horizon_short"), hb.short_term_bias)
    cols[1].metric(t("macro_horizon_mid"), hb.mid_term_bias)
    cols[2].metric(t("macro_horizon_long"), hb.long_term_bias)

    st.markdown(f"**{t('macro_horizon_rationale')}**")
    st.markdown(f"- `{t('macro_horizon_short')}`: {hb.short_term_rationale or '—'}")
    st.markdown(f"- `{t('macro_horizon_mid')}`: {hb.mid_term_rationale or '—'}")
    st.markdown(f"- `{t('macro_horizon_long')}`: {hb.long_term_rationale or '—'}")


# ---------------------------------------------------------------------------
# 7. Theme Implications
# ---------------------------------------------------------------------------

def _render_themes_section(view: MacroDashboardView) -> None:
    st.subheader(t("macro_tab_themes"))
    st.caption(t("macro_themes_caption"))
    st.info(t("macro_themes_not_live"))

    if not view.theme_implications:
        st.info(t("macro_themes_no_implications"))
        return

    rows = []
    for ti in view.theme_implications:
        rows.append(
            {
                "theme_name": ti.theme_name,
                t("macro_themes_implication"): ti.implication,
                "is_live_market_claim": ti.is_live_market_claim,
                t("macro_themes_rationale"): ti.rationale,
            }
        )
    st.table(rows)


# ---------------------------------------------------------------------------
# 8. Opportunity Posture
# ---------------------------------------------------------------------------

def _render_posture_section(view: MacroDashboardView) -> None:
    st.subheader(t("macro_tab_posture"))
    st.caption(t("macro_posture_caption"))

    op = view.opportunity_posture
    cols = st.columns(2)
    cols[0].metric(t("macro_posture_primary"), op.primary_posture)
    cols[1].markdown(
        f"**{t('macro_posture_secondary')}**: "
        f"`{', '.join(op.secondary_postures) if op.secondary_postures else '—'}`"
    )
    st.markdown(f"**{t('macro_posture_rationale')}**")
    st.caption(op.rationale or "")

    # Review-only invariants — always surfaced (non-executability evidence).
    st.info(
        t("macro_posture_not_decision")
        + f" (is_buy_signal=`{op.is_buy_signal}`, "
        + f"is_executable=`{op.is_executable}`, "
        + f"produces_final_decision=`{op.produces_final_decision}`)"
    )


# ---------------------------------------------------------------------------
# 9. Provenance / Diagnostics
# ---------------------------------------------------------------------------

def _validation_dict(view: MacroDashboardView) -> dict:
    vs = view.validation_summary
    if vs is None:
        return {"validation_summary": None}
    return {
        "factor_count": vs.factor_count,
        "primary_regime_status": vs.primary_regime_status,
        "has_all_required_factors": vs.has_all_required_factors,
        "missing_factors": list(vs.missing_factors),
        "theme_implication_count": vs.theme_implication_count,
        "is_degraded": vs.is_degraded,
        "is_safe_empty": vs.is_safe_empty,
        "no_final_decision": vs.no_final_decision,
        "no_buy_signal_fields": vs.no_buy_signal_fields,
        "no_executable_order_fields": vs.no_executable_order_fields,
        "approved_for_execution_absent": vs.approved_for_execution_absent,
        "no_live_macro_api": vs.no_live_macro_api,
        "issues": list(vs.issues),
    }


def _banner_dict(view: MacroDashboardView) -> dict:
    b = view.safety_banner
    return {
        "is_fixture_only": b.is_fixture_only,
        "is_demo_only": b.is_demo_only,
        "no_live_macro_api": b.no_live_macro_api,
        "no_external_api": b.no_external_api,
        "no_llm": b.no_llm,
        "no_broker_or_order": b.no_broker_or_order,
        "no_investment_advice": b.no_investment_advice,
        "produces_final_decision": b.produces_final_decision,
        "requires_human_review": b.requires_human_review,
    }


def _render_provenance_section(view: MacroDashboardView) -> None:
    st.subheader(t("macro_tab_provenance"))
    st.caption(t("macro_provenance_caption"))
    st.info(t("macro_provenance_no_api"))

    cols = st.columns(2)
    with cols[0]:
        st.markdown(f"**{t('macro_provenance_validation')}**")
        st.json(_validation_dict(view))
    with cols[1]:
        st.markdown("**Safety banner**")
        st.json(_banner_dict(view))

    vs = view.validation_summary
    if vs is not None and vs.missing_factors:
        st.warning(
            t("macro_provenance_missing_factors") + " "
            + ", ".join(vs.missing_factors)
        )

    st.caption(f"dashboard_id: `{view.dashboard_id}` · schema: `{view.schema_version}`")
    st.caption(t("macro_provenance_source"))
    st.caption(t("macro_provenance_not_live"))


# ---------------------------------------------------------------------------
# Page entry
# ---------------------------------------------------------------------------

def _render_fixture_tabs() -> None:
    """Phase 5O fixture view — used only in fixture mode (MACRO_LIVE_MODE=False)
    or when the live fetch fully fails. Preserves the original demo scenarios so
    the page never renders empty or broken under any condition."""
    views, err = _load_macro_views()
    if views is None or not views:
        # Fail-closed: no fallback to live macro data, LLM, or external API.
        st.error(t("macro_failclosed_headline"))
        st.code(err or t("macro_failclosed_no_detail"))
        st.warning(t("macro_failclosed_note"))
        return

    available_kinds = [k for k in MACRO_DASHBOARD_SCENARIO_ORDER if k in views]
    if not available_kinds:
        st.error(t("macro_no_scenarios"))
        return

    # Default to the risk-on scenario (first in the order).
    default_kind = "risk_on" if "risk_on" in available_kinds else available_kinds[0]
    default_index = available_kinds.index(default_kind)

    selected_kind = st.sidebar.selectbox(
        t("macro_scenario_select_label"),
        options=available_kinds,
        index=default_index,
        help=t("macro_scenario_select_help"),
    )
    view = views[selected_kind]

    st.sidebar.caption(f"{t('macro_sidebar_dashboard_id')} `{view.dashboard_id}`")
    st.sidebar.caption(t("macro_sidebar_data_source"))

    tab_labels = [
        t("macro_tab_overview"),
        t("macro_tab_regime"),
        t("macro_tab_indicators"),
        t("macro_tab_liquidity"),
        t("macro_tab_credit"),
        t("macro_tab_risk"),
        t("macro_tab_horizon"),
        t("macro_tab_themes"),
        t("macro_tab_posture"),
        t("macro_tab_provenance"),
    ]
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        _render_overview_section(view)
    with tabs[1]:
        _render_regime_section(view.regime_snapshot)
    with tabs[2]:
        _render_indicators_section(view.indicator_panel)
    with tabs[3]:
        _render_liquidity_section(view.regime_snapshot)
    with tabs[4]:
        _render_credit_section(view.regime_snapshot)
    with tabs[5]:
        _render_risk_section(view.regime_snapshot)
    with tabs[6]:
        _render_horizon_section(view)
    with tabs[7]:
        _render_themes_section(view)
    with tabs[8]:
        _render_posture_section(view)
    with tabs[9]:
        _render_provenance_section(view)


def main() -> None:
    st.title(t("macro_page_title"))
    st.caption(t("macro_page_subtitle"))
    _render_demo_walkthrough()

    # Phase 6A — a single feature flag controls the entire page.
    if MACRO_LIVE_MODE:
        data, regime, err = _load_live_macro()
        if data is not None and regime is not None:
            # Phase 6B/6C-B — publish the freshly-classified macro regime for
            # cross-page consumers (Scanner, Cockpit, Trading Desk). Routed through
            # the single macro_state boundary so it is stored as a plain dict
            # (the full canonical field set), consistent with the Cockpit. Done at
            # the (non-cached) call site, never mutating live behavior.
            save_regime_to_state(regime)
            # Live, real-data dashboard (reflects today's conditions).
            _render_live_tabs(data, regime)
            return
        # Live fetch fully failed → degrade to the fixture view below (never crash).
        st.warning(t("macro_live_failclosed_note"))
        if err:
            st.caption(f"`{err}`")
    else:
        st.caption(t("macro_live_disabled_note"))

    # Fixture view (live mode off, or live fetch fully failed).
    _render_fixture_tabs()


def _render_market_internals() -> None:
    """Phase 7B — Market-Internals workbench (verification surface).

    Reuses the Cockpit's session reading + rolling series (zero new computation):
    a 10-day raw-reading trend (points line + level colour markers, hysteresis
    source + data vintage) and a per-component detail table (value incl 0, triggered
    flag, degrade reason). The Cockpit keeps the one-line conclusion; this is the
    macro workbench (same division as Sector page vs Cockpit)."""
    st.divider()
    st.subheader(t("mi_header"))
    frag = st.session_state.get("cockpit_fragility") or {}
    series = st.session_state.get("cockpit_fragility_series") or []
    if not frag:
        st.info(t("mi_not_loaded"))
        st.page_link("pages/7_Investment_Cockpit.py", label=t("mi_go_cockpit"))
        return

    _lvl_color = {"normal": "#3fb950", "elevated": "#d29922", "high": "#f85149"}
    level = str(frag.get("fragility_level", "normal"))
    # Localized badge text (EN keeps the raw level word; ZH renders 正常/警戒/警报).
    _lvl_label = {"normal": t("cockpit_frag_lvl_normal"),
                  "elevated": t("cockpit_frag_lvl_elevated"),
                  "high": t("cockpit_frag_lvl_high")}.get(level, level)
    st.markdown(
        f"{t('mi_level')}: " + _badge_html(_lvl_label, _lvl_color.get(level, "#8b949e"))
        + f" &nbsp; {t('mi_source')}: <b>{frag.get('hysteresis_source', '—')}</b>"
        + f" &nbsp; {t('mi_vintage')}: <b>{frag.get('data_vintage') or '—'}</b>"
        + (f" &nbsp; ⚠️ {t('mi_vintage_mismatch')}" if frag.get("vintage_mismatch") else ""),
        unsafe_allow_html=True,
    )
    st.caption(t("cockpit_frag_lvl_explain"))

    # 10-day raw-reading trend: points line + per-day level-coloured markers.
    if series:
        xs = [row[0] for row in series]
        ys = [row[2] if len(row) > 2 else 0 for row in series]
        marker_colors = [_lvl_color.get(row[1], "#8b949e") for row in series]
        fig = go.Figure(go.Scatter(
            x=xs, y=ys, mode="lines+markers",
            line=dict(color="#8b949e", width=2),
            marker=dict(size=9, color=marker_colors),
            name=t("mi_points")))
        try:
            import lib.market_internals as _miC
            fig.add_hline(y=_miC.INTERNALS_CONFIG["elevated_points"],
                          line=dict(color="#d29922", dash="dot"))
            fig.add_hline(y=_miC.INTERNALS_CONFIG["high_points"],
                          line=dict(color="#f85149", dash="dot"))
        except Exception:  # noqa: BLE001
            pass
        apply_layout(fig, height=240)
        apply_legend(fig)
        st.plotly_chart(fig, use_container_width=True)

    # Component detail table — value (0 renders as 0), triggered flag, degrade reason.
    triggered = set(frag.get("fragility_triggered", []) or [])
    earn_reason = frag.get("earnings_degrade_reason", "") or ""

    def _row(label, value, trig_keys, reason=""):
        fired = any(k in triggered for k in trig_keys)
        val = t("cockpit_frag_na") if value is None else (
            f"{value:.2f}" if isinstance(value, float) else str(value))
        return {t("mi_component"): label, t("mi_value"): val,
                t("mi_triggered"): "✅" if fired else "—",
                t("mi_degrade"): reason}

    def _pct(v):
        # Breadth reads as a fraction; render it as a percentage ("50%"). None → n/a.
        return None if v is None else f"{int(v * 100)}%"

    def _yesno(v):
        # Bool reading → human-readable 是/否 (Yes/No). None → n/a (keep named-absence).
        return None if v is None else (t("mi_yes") if v else t("mi_no"))

    # B2: good-news-sold renders as a full phrase ("1 of 12 post-beat names sold off")
    # from the SAME refresh's evaluated denominator (single vintage). None → n/a row.
    _gns_v = frag.get("good_news_sold")
    _gns_cell = (t("cockpit_frag_gns_full").format(
        num=_gns_v, den=frag.get("earnings_evaluated"))
        if _gns_v is not None else None)
    rows = [
        _row(t("cockpit_frag_dist") + " SPY", frag.get("distribution_days_spy"),
             ("distribution_days_elevated", "distribution_days_high")),
        _row(t("cockpit_frag_dist") + " QQQ", frag.get("distribution_days_qqq"),
             ("distribution_days_elevated", "distribution_days_high")),
        _row(t("mi_c_breadth20"), _pct(frag.get("breadth_above_sma20")),
             ("breadth_weak",)),
        _row(t("mi_c_breadth50"), _pct(frag.get("breadth_above_sma50")), ()),
        _row(t("mi_c_slope"), frag.get("breadth_slope"), ("breadth_narrowing",)),
        _row(t("mi_c_weak_bounce"), _yesno(frag.get("weak_bounce")), ("weak_bounce",)),
        _row(t("cockpit_frag_gns"), _gns_cell,
             ("good_news_sold_elevated", "good_news_sold_high"),
             # Show the reason whenever present — including partial_frame_coverage
             # on a reported number (skipped > evaluated under the scan scope). The raw
             # token text is preserved; ZH gets a gloss appended (EN = bare token).
             (frag_reason_gloss(earn_reason)
              + (f" (skipped={frag.get('earnings_skipped')})"
                 if frag.get("earnings_skipped") else "")
              ) if earn_reason else ""),
        _row(t("mi_c_vol"), frag.get("leading_theme_volume_shrinking"),
             ("leading_theme_volume_shrinking",)),
        _row(t("mi_c_od"),
             frag_od_value(frag.get("offense_defense_direction", ""),
                           frag.get("offense_defense_magnitude", "")),
             ("offense_defense_defensive", "offense_defense_defensive_strong")),
    ]
    st.table(rows)
    st.caption(t("cockpit_frag_gns_concept"))
    st.caption(t("mi_note"))


main()
_render_market_internals()
