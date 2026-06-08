"""Page 9 — Trading Desk (Phase 6C-A).

The execution layer of the investment workflow. Three sections:

1. **Holdings Monitor** — manual position entry with thesis tracking and a Thesis
   Invalidation Monitor that runs on page load (4-hour TTL). For each active
   holding it shows whether the thesis is intact / watch / weakening / broken and
   why.
2. **Order Recommendations** — code-computed entry/exit levels (ATR, SMA,
   support/resistance, Kelly-lite sizing) with an LLM-synthesized narrative. The
   LLM only narrates; it never computes a level.
3. **Opportunity Watch** — triple-signal candidates handed off from the Scanner,
   turned into actionable "add to holdings" setups.

Guardrails (Phase 6C-A): holdings persist ONLY to ``data/holdings.json`` via
``lib/holdings.py`` (never written directly here); no DB / vector store; no paid
API; all data calls fail-closed with a fixture fallback; NO broker / order /
execution capability, no order ticket, no broker payload; ``approved_for_execution``
is never introduced; nothing on this page places or routes an order. Not
investment advice.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from ui_utils import apply_theme, render_sidebar, t

from lib.holdings import (
    HoldingRecord,
    PortfolioSettings,
    add_holding,
    close_holding,
    get_active_holdings,
    load_cash_position,
    load_portfolio_settings,
    save_cash_position,
    save_portfolio_settings,
    update_holding,
)
from lib.thesis_monitor import run_thesis_monitor
from lib.order_advisor import compute_price_levels, generate_order_narrative
# Phase 7A — unified five-state opportunity status (single naming scheme).
from lib.opportunity_ranker import (
    derive_status, status_next_trigger,
    STATUS_ACTIONABLE, STATUS_PULLBACK, STATUS_BREAKOUT,
    STATUS_RESEARCH, STATUS_AVOID,
    MARKET_WIDE_BLOCKER_CODES,
)


def _opp_ticker_blockers(blockers: list, horizon: str) -> list:
    """Ticker-specific blockers filtered to the displayed horizon (Task 3):
    market-wide conditions never render as per-card chips."""
    out = []
    for b in (blockers or []):
        if b.get("code") in MARKET_WIDE_BLOCKER_CODES:
            continue
        hz = b.get("horizons") or []
        if hz and horizon not in hz:
            continue
        out.append(b)
    return out

# Map the five canonical states to t() keys + badge colors (shared with Cockpit).
_OPP_STATUS_KEY = {
    STATUS_ACTIONABLE: "opp_status_actionable",
    STATUS_PULLBACK: "opp_status_pullback",
    STATUS_BREAKOUT: "opp_status_breakout",
    STATUS_RESEARCH: "opp_status_research",
    STATUS_AVOID: "opp_status_avoid",
}
_OPP_STATUS_COLOR = {
    STATUS_ACTIONABLE: "#3fb950", STATUS_PULLBACK: "#d29922",
    STATUS_BREAKOUT: "#388bfd", STATUS_RESEARCH: "#8b949e",
    STATUS_AVOID: "#f85149",
}
_OPP_GRADE_COLOR = {"A": "#3fb950", "B": "#d29922", "C": "#8b949e"}
_OPP_SETUP_KEY = {
    "Momentum Breakout": "opp_setup_momentum_breakout",
    "Mid-term Rotation": "opp_setup_mid_rotation",
    "Oversold Rebound": "opp_setup_oversold_rebound",
    "Post-earnings Reprice": "opp_setup_post_earnings",
    "Long-term Accumulation": "opp_setup_long_accum",
    "Speculative Watch": "opp_setup_speculative",
}

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Trading Desk", page_icon="📋", layout="wide")
apply_theme()
render_sidebar()

# 4-hour auto-refresh window for the thesis monitor.
_REFRESH_TTL = 14400

_STATUS_COLORS = {
    "intact": "#3fb950",
    "watch": "#d29922",
    "weakening": "#e8590c",
    "broken": "#f85149",
}
_ACTION_COLORS = {
    "add": "#3fb950",
    "hold": "#388bfd",
    "trim": "#d29922",
    "exit": "#f85149",
    "wait": "#8b949e",
}
_HORIZON_KEYS = {"short": "td_horizon_short", "mid": "td_horizon_mid", "long": "td_horizon_long"}

# Entry Strategy v3 — fine-grained computed-action vocabulary. Color coding:
# green = enter_* / add_* / average_down*; yellow = wait_* / hold;
# orange = reduce_* / trim_*; red = cut_loss / exit / avoid.
_FINE_ACTION_KEYS = {
    "wait": "td_act_wait", "hold": "td_act_hold",
    "enter_partial_now": "td_act_enter_partial_now",
    "enter_on_pullback": "td_act_enter_on_pullback",
    "enter_or_add_small": "td_act_enter_or_add_small",
    "add_small": "td_act_add_small", "add_partial": "td_act_add_partial",
    "average_down_small": "td_act_average_down_small",
    "average_down": "td_act_average_down",
    "wait_for_pullback": "td_act_wait_for_pullback",
    "wait_or_cut": "td_act_wait_or_cut", "reduce": "td_act_reduce",
    "reduce_or_exit": "td_act_reduce_or_exit", "cut_loss": "td_act_cut_loss",
    "exit": "td_act_exit", "trim_or_stop_adding": "td_act_trim_or_stop_adding",
    "avoid": "td_act_avoid",
}
_SCENARIO_KEYS = {"initiate": "td_scenario_initiate", "add": "td_scenario_add",
                  "manage": "td_scenario_manage"}


def _fine_action_label(action: str) -> str:
    return t(_FINE_ACTION_KEYS.get(action, "td_act_wait"))


def _fine_action_color(action: str) -> str:
    a = action or "wait"
    if a in ("cut_loss", "exit", "avoid"):
        return "#f85149"  # red
    if a.startswith("reduce") or a.startswith("trim"):
        return "#e8590c"  # orange
    if a.startswith("wait") or a == "hold":
        return "#d29922"  # yellow
    if a.startswith("enter") or a.startswith("add") or a.startswith("average_down"):
        return "#3fb950"  # green
    return "#8b949e"  # gray


def _scenario_label(scenario: str) -> str:
    return t(_SCENARIO_KEYS.get(scenario, "td_scenario_initiate"))


# Horizon badge colors — short = blue, mid = green, long = purple.
_HORIZON_COLORS = {"short": "#388bfd", "mid": "#3fb950", "long": "#8957e5"}


def _horizon_color(h: str) -> str:
    return _HORIZON_COLORS.get((h or "mid").strip().lower(), "#388bfd")


# Valuation-confidence badge — high = green, medium = yellow, low = gray.
_CONF_COLORS = {"high": "#3fb950", "medium": "#d29922", "low": "#8b949e"}


def _confidence_color(c: str) -> str:
    return _CONF_COLORS.get((c or "low").strip().lower(), "#8b949e")


def _confidence_label(c: str) -> str:
    return t({"high": "td_conf_high", "medium": "td_conf_medium",
              "low": "td_conf_low"}.get((c or "low").strip().lower(), "td_conf_low"))


def _bi(narrative, field: str, lang: str) -> str:
    """Read the language-appropriate bilingual narrative field (no LLM re-call).

    Prefers ``{field}_{lang}``, then the undecorated ``{field}`` (backward compat),
    then "".
    """
    return (getattr(narrative, f"{field}_{lang}", "")
            or getattr(narrative, field, "") or "")


def _lang() -> str:
    return st.session_state.get("language", "en")


def _macro_result():
    """The shared macro regime result (dict / obj), or None (fail-closed)."""
    return st.session_state.get("macro_regime_result")


def _macro_regime_str() -> str:
    mr = _macro_result()
    if mr is None:
        return "unknown"
    if isinstance(mr, dict):
        return str(mr.get("regime", "unknown"))
    return str(getattr(mr, "regime", "unknown"))


def _badge(text: str, color: str) -> str:
    return (
        f'<span style="display:inline-block;padding:2px 9px;border-radius:10px;'
        f'background:{color}22;color:{color};border:1px solid {color}55;'
        f'font-size:0.72rem;font-weight:600;">{text}</span>'
    )


def _status_label(status: str) -> str:
    return t({"intact": "td_status_intact", "watch": "td_status_watch",
              "weakening": "td_status_weakening", "broken": "td_status_broken"}.get(status, "td_status_intact"))


def _action_label(action: str) -> str:
    return t({"add": "td_action_add", "hold": "td_action_hold", "trim": "td_action_trim",
              "exit": "td_action_exit", "wait": "td_action_wait"}.get(action, "td_action_hold"))


def _horizon_label(h: str) -> str:
    return t(_HORIZON_KEYS.get(h, "td_horizon_mid"))


def _vol_label(v: str) -> str:
    return t({"increasing": "td_vol_increasing", "decreasing": "td_vol_decreasing",
              "neutral": "td_vol_neutral"}.get(v, "td_vol_neutral"))


def _as_float(x, default: float) -> float:
    """Best-effort float coercion with a fallback (no raise)."""
    try:
        if isinstance(x, bool) or x is None:
            return default
        v = float(x)
        return v if v == v else default  # reject NaN
    except (TypeError, ValueError):
        return default


def _dominant_horizon(signal: dict) -> str:
    """Pick the dominant horizon from a Scanner hand-off signal's three scores."""
    scores = {
        "short": signal.get("short_score", 0.0) or 0.0,
        "mid": signal.get("mid_score", 0.0) or 0.0,
        "long": signal.get("long_score", 0.0) or 0.0,
    }
    return max(scores, key=lambda k: scores[k])


# ---------------------------------------------------------------------------
# Thesis monitor + order recommendation refresh (fail-closed; 4h gated)
# ---------------------------------------------------------------------------


def _refresh(active_holdings, force: bool = False) -> None:
    """Run the thesis monitor + order levels for all active holdings.

    Gated by ``trading_desk_last_refresh`` + the 4-hour TTL unless ``force``.
    Stores results in ``st.session_state`` so reruns are cheap. Fail-closed.
    """
    last = st.session_state.get("trading_desk_last_refresh")
    now = time.time()
    if not force and last is not None and (now - last) < _REFRESH_TTL:
        return
    macro = _macro_result()
    regime = _macro_regime_str()
    lang = _lang()
    with st.spinner(t("td_monitor_running")):
        try:
            checks = run_thesis_monitor(active_holdings, macro)
        except Exception:  # noqa: BLE001 — fail-closed
            checks = []
        results_by_id = {c.holding_id: c for c in checks}
        st.session_state["thesis_check_results"] = results_by_id

        # Order recommendations for non-broken holdings (levels are pure code).
        # The entry zone is build-vs-add agnostic: it threads the thesis status,
        # horizon and EPS-revision direction in but NEVER uses the cost basis.
        order_recs: dict = {}
        for h in active_holdings:
            chk = results_by_id.get(h.id)
            try:
                levels = compute_price_levels(
                    h.ticker, h,
                    thesis_status=getattr(chk, "thesis_status", "intact") if chk else "intact",
                    horizon=h.horizon,
                    eps_revision_direction=(
                        getattr(chk, "eps_revision_direction", "unknown") if chk else "unknown"
                    ),
                    allow_fetch=True,  # X1: Trading Desk is a page path (network allowed)
                )
                narrative = generate_order_narrative(h, levels, chk, regime, lang)
                order_recs[h.id] = {"levels": levels, "narrative": narrative}
            except Exception:  # noqa: BLE001 — fail-closed; skip this holding's rec
                continue
        st.session_state["order_recommendations"] = order_recs

        # Opportunity Watch entry zones for triple-signal candidates NOT already
        # held. Pre-computed here (before Section 2 renders) so the Actionable
        # Signals subsection and the Section 3 cards stay in sync. New candidates
        # are assumed thesis-intact; the entry zone never uses any cost basis.
        # Phase 6C-B fix #4 — Opportunity Watch candidates now come from BOTH the
        # Cockpit "Add to Trading Desk" hand-off (td_pending_signals, any signal
        # strength) and the legacy triple-signal hand-off (cockpit_triple_signals,
        # retained as a fallback). Deduped by ticker; pending takes precedence.
        triples = st.session_state.get("cockpit_triple_signals", []) or []
        pending = st.session_state.get("td_pending_signals", []) or []
        _seen_opp: set = set()
        candidates: list = []
        for s in (list(pending) + list(triples)):
            _ctk = str(s.get("ticker", "")).upper().strip()
            if not _ctk or _ctk in _seen_opp:
                continue
            _seen_opp.add(_ctk)
            candidates.append(s)
        held = {h.ticker.upper() for h in active_holdings}
        opp_levels: dict = {}
        actionable: list = []
        for s in candidates:
            tk = str(s.get("ticker", "")).upper().strip()
            if not tk or tk in held:
                continue
            try:
                lv = compute_price_levels(
                    tk, None,
                    thesis_status="intact",
                    horizon=_dominant_horizon(s),
                    eps_revision_direction=str(s.get("eps_revision_direction", "unknown") or "unknown"),
                    valuation_percentile=_as_float(s.get("valuation_percentile"), 0.5),
                    allow_fetch=True,  # X1: Trading Desk is a page path (network allowed)
                )
            except Exception:  # noqa: BLE001 — fail-closed; skip this candidate
                continue
            opp_levels[tk] = lv
            if lv.entry_status == "in_zone":
                actionable.append({
                    "ticker": tk,
                    "entry_zone_low": lv.entry_zone_low,
                    "entry_zone_high": lv.entry_zone_high,
                    "stop_loss": lv.stop_loss,
                    "target_price": lv.target_price,
                    "risk_reward_ratio": lv.risk_reward_ratio,
                    "position_size_pct": lv.position_size_pct,
                })
        st.session_state["opportunity_levels"] = opp_levels
        st.session_state["td_actionable_signals"] = actionable
    st.session_state["trading_desk_last_refresh"] = now


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title(t("td_page_title"))
st.caption(t("td_page_subtitle"))
st.warning(t("td_safety_banner"))

_active = get_active_holdings()
# Auto-run the monitor on page load when stale / first visit.
_refresh(_active)
_checks = st.session_state.get("thesis_check_results", {})
_order_recs = st.session_state.get("order_recommendations", {})

# A manual refresh button (top-right).
_hc1, _hc2 = st.columns([4, 1])
with _hc2:
    if st.button("🔄 " + t("td_refresh"), use_container_width=True, key="td_refresh_btn"):
        _refresh(_active, force=True)
        st.rerun()
_last = st.session_state.get("trading_desk_last_refresh")
if _last:
    with _hc1:
        st.caption(
            f"{t('td_last_refresh')}: "
            f"{datetime.fromtimestamp(_last, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )


# ---------------------------------------------------------------------------
# Add Position form (shared by Section 1 + Section 3 hand-off)
# ---------------------------------------------------------------------------

st.session_state.setdefault("td_prefill", {})
st.session_state.setdefault("td_editing_id", None)
st.session_state.setdefault("td_adding", False)


def _current_price(h, chk) -> float:
    """Best-effort current price: order-level price, else cost × (1 + P&L%)."""
    rec = _order_recs.get(h.id)
    if rec is not None:
        cp = getattr(rec["levels"], "current_price", 0.0) or 0.0
        if cp:
            return float(cp)
    if chk is not None and h.cost_basis:
        return round(float(h.cost_basis) * (1.0 + getattr(chk, "price_vs_entry", 0.0) / 100.0), 2)
    return 0.0


def _key_alert(chk) -> str:
    """First key_development / technical reason, truncated to 30 chars (else —)."""
    if chk is None:
        return "—"
    txt = ""
    if getattr(chk, "key_development", ""):
        txt = chk.key_development
    elif getattr(chk, "technical_breakdown_reasons", []):
        txt = chk.technical_breakdown_reasons[0]
    if not txt:
        if getattr(chk, "is_normal_pullback", False):
            return t("td_normal_pullback")
        return "—"
    return (txt[:30] + "…") if len(txt) > 30 else txt


# Thesis-status severity ordering — the parent (merged) ticker row shows the
# WORST status across its per-horizon holdings.
_STATUS_RANK = {"intact": 0, "watch": 1, "weakening": 2, "broken": 3}


def _worst_status(holdings_list) -> str:
    """The most-severe thesis status across a ticker's holdings (broken wins)."""
    worst = "intact"
    for h in holdings_list:
        c = _checks.get(h.id)
        s = getattr(c, "thesis_status", "intact") if c else "intact"
        if _STATUS_RANK.get(s, 0) > _STATUS_RANK.get(worst, 0):
            worst = s
    return worst


def _ticker_price(holdings_list) -> float:
    """The current market price for a ticker (same across its holdings)."""
    for h in holdings_list:
        cp = _current_price(h, _checks.get(h.id))
        if cp:
            return float(cp)
    return 0.0


def _render_add_form() -> None:
    """Inline Add Position form (mutually exclusive with the edit form)."""
    prefill = dict(st.session_state.get("td_prefill", {}) or {})
    with st.container(border=True):
        st.markdown(f"**➕ {t('td_add_position')}**")
        # Import-from-signal selector (OUTSIDE the form so selecting it reruns
        # and fills the form defaults). Driven by the Scanner hand-off.
        all_signals = st.session_state.get("cockpit_all_signals", []) or []
        if all_signals and not prefill:
            opts = [t("td_import_none")] + [
                f"{s.get('ticker', '?')} ({s.get('signal_strength', 'none')})"
                for s in all_signals
            ]
            sel = st.selectbox(t("td_import_thesis"), opts, key="td_import_select")
            idx = opts.index(sel) - 1 if sel in opts else -1
            if 0 <= idx < len(all_signals):
                sig = all_signals[idx]
                ks = sig.get("key_signals", []) or []
                prefill = {
                    "ticker": sig.get("ticker", ""),
                    "horizon": _dominant_horizon(sig),
                    "thesis_text": "\n".join(f"- {x}" for x in ks),
                    "thesis_source": "cockpit",
                    "thesis_signals": ks,
                }

        with st.form("td_add_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            ticker = c1.text_input(t("td_ticker"), value=prefill.get("ticker", "")).upper().strip()
            shares = c2.number_input(t("td_shares"), min_value=0.0, value=0.0, step=1.0)
            cost_basis = c3.number_input(t("td_cost_basis"), min_value=0.0, value=0.0, step=0.01)
            c4, c5 = st.columns(2)
            entry_date = c4.text_input(
                t("td_entry_date"),
                value=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            )
            _hz_opts = ["short", "mid", "long"]
            _hz_default = prefill.get("horizon", "mid")
            horizon = c5.selectbox(
                t("td_horizon"), _hz_opts,
                index=_hz_opts.index(_hz_default) if _hz_default in _hz_opts else 1,
                format_func=_horizon_label,
            )
            thesis_text = st.text_area(t("td_thesis_text"), value=prefill.get("thesis_text", ""))
            notes = st.text_area(t("td_notes"), value="")
            if prefill.get("thesis_source", "manual") != "manual":
                st.caption(
                    f"{t('td_thesis_source')}: {prefill.get('thesis_source')} · "
                    f"{t('td_thesis_signals')}: {', '.join(prefill.get('thesis_signals', []))}"
                )
            bc = st.columns(2)
            submitted = bc[0].form_submit_button("✅ " + t("td_add_btn"))
            cancelled = bc[1].form_submit_button("✖ " + t("td_cancel"))
            if submitted and ticker:
                rec = HoldingRecord(
                    ticker=ticker,
                    shares=float(shares),
                    cost_basis=float(cost_basis),
                    entry_date=entry_date,
                    horizon=horizon,
                    thesis_text=thesis_text,
                    thesis_source=prefill.get("thesis_source", "manual"),
                    thesis_signals=prefill.get("thesis_signals", []),
                )
                add_holding(rec)
                st.session_state["td_prefill"] = {}
                st.session_state["td_adding"] = False
                _refresh(get_active_holdings(), force=True)
                st.rerun()
            if cancelled:
                st.session_state["td_prefill"] = {}
                st.session_state["td_adding"] = False
                st.rerun()


def _render_edit_form(h) -> None:
    """Inline edit/close form for ONE holding (mutually exclusive with add)."""
    with st.container(border=True):
        st.markdown(f"**✏️ {t('td_edit')} — {h.ticker}**")
        with st.form(f"td_edit_{h.id}"):
            ec = st.columns(3)
            e_shares = ec[0].number_input(t("td_shares"), min_value=0.0,
                                          value=float(h.shares), step=1.0,
                                          key=f"e_sh_{h.id}")
            e_cost = ec[1].number_input(t("td_cost_basis"), min_value=0.0,
                                        value=float(h.cost_basis), step=0.01,
                                        key=f"e_cb_{h.id}")
            _hz_opts = ["short", "mid", "long"]
            e_horizon = ec[2].selectbox(
                t("td_horizon"), _hz_opts,
                index=_hz_opts.index(h.horizon) if h.horizon in _hz_opts else 1,
                format_func=_horizon_label, key=f"e_hz_{h.id}",
            )
            e_thesis = st.text_area(t("td_thesis_text"), value=h.thesis_text,
                                    key=f"e_th_{h.id}")
            e_notes = st.text_area(t("td_notes"), value=h.notes, key=f"e_no_{h.id}")
            # Read-only provenance.
            st.caption(
                f"{t('td_thesis_source')}: {h.thesis_source} · "
                f"{t('td_thesis_signals')}: {', '.join(h.thesis_signals) or '—'}"
            )
            bc = st.columns(3)
            save = bc[0].form_submit_button("💾 " + t("td_save"))
            do_close = bc[1].form_submit_button("🔒 " + t("td_close_position"))
            cancel = bc[2].form_submit_button("✖ " + t("td_cancel"))
            if save:
                update_holding(h.id, {
                    "shares": float(e_shares), "cost_basis": float(e_cost),
                    "horizon": e_horizon, "thesis_text": e_thesis, "notes": e_notes,
                })
                st.session_state["td_editing_id"] = None
                _refresh(get_active_holdings(), force=True)
                st.rerun()
            if do_close:
                # Open a confirmation dialog rather than closing immediately. The
                # actual close + cash handling happens in the confirmation flow,
                # using the current price for the estimated proceeds.
                _cp_close = _current_price(h, _checks.get(h.id)) or float(h.cost_basis)
                st.session_state["td_close_confirm"] = {
                    "id": h.id, "ticker": h.ticker,
                    "shares": float(h.shares), "price": float(_cp_close),
                }
                st.rerun()
            if cancel:
                st.session_state["td_editing_id"] = None
                st.rerun()


# ---------------------------------------------------------------------------
# SECTION 1 — Holdings Monitor
# ---------------------------------------------------------------------------

st.divider()
st.subheader("📊 " + t("td_sec1_header"))

# --- Portfolio settings (persisted) — collapsed expander at the top ---------
# Loaded once into session_state; saved through lib.holdings (never written here).
if "td_portfolio_settings" not in st.session_state:
    st.session_state["td_portfolio_settings"] = load_portfolio_settings()
_ps = st.session_state["td_portfolio_settings"]
with st.expander("⚙️ " + t("td_portfolio_settings"), expanded=False):
    _psc = st.columns(3)
    _max_pos = _psc[0].slider(
        t("td_max_position_pct"), min_value=5, max_value=30,
        value=int(round(float(_ps.max_position_pct) * 100)), step=1, format="%d%%",
        key="td_set_max_pos",
    )
    _short_loss = _psc[1].slider(
        t("td_short_max_loss"), min_value=0.5, max_value=5.0,
        value=float(_ps.short_max_loss_pct) * 100, step=0.5, format="%.1f%%",
        key="td_set_short_loss",
    )
    _mid_loss = _psc[2].slider(
        t("td_mid_max_loss"), min_value=1, max_value=10,
        value=int(round(float(_ps.mid_max_loss_pct) * 100)), step=1, format="%d%%",
        key="td_set_mid_loss",
    )
    st.caption(f"{t('td_long_stop_label')}: **{t('td_long_stop_value')}**")
    if st.button("💾 " + t("td_save_settings"), key="td_save_settings_btn"):
        _new_settings = PortfolioSettings(
            max_position_pct=_max_pos / 100.0,
            short_max_loss_pct=_short_loss / 100.0,
            mid_max_loss_pct=_mid_loss / 100.0,
            long_stop="thesis_break",
        )
        save_portfolio_settings(_new_settings)
        st.session_state["td_portfolio_settings"] = _new_settings
        st.success(t("td_settings_saved"))
        st.rerun()

# Add Position toggle (mutually exclusive with row editing).
if st.button("➕ " + t("td_add_position"), key="td_add_btn_top"):
    st.session_state["td_adding"] = not st.session_state.get("td_adding", False)
    if st.session_state["td_adding"]:
        st.session_state["td_editing_id"] = None
    else:
        st.session_state["td_prefill"] = {}
    st.rerun()

# --- Cash position + portfolio summary --------------------------------------
# The cash position is PERSISTED to data/holdings.json (top-level field) via
# lib.holdings; it is loaded once into session_state and saved on every change.
# A pending cash add (from a confirmed close) is applied HERE, before the cash
# number_input widget is instantiated, so it never mutates a live widget key.
if "td_cash_position" not in st.session_state:
    st.session_state["td_cash_position"] = load_cash_position()
st.session_state.setdefault("td_expanded_tickers", set())
_pending_cash = st.session_state.pop("td_pending_cash_add", 0.0) or 0.0
if _pending_cash:
    st.session_state["td_cash_position"] = (
        float(st.session_state.get("td_cash_position", 0.0) or 0.0) + float(_pending_cash)
    )
    save_cash_position(st.session_state["td_cash_position"])


def _persist_cash() -> None:
    """Persist the cash position whenever the user edits the input."""
    save_cash_position(float(st.session_state.get("td_cash_position", 0.0) or 0.0))


_cc = st.columns([1.5, 1, 1, 1])
_cc[0].number_input(
    "💵 " + t("td_cash_position_label"), min_value=0.0, step=100.0,
    key="td_cash_position", on_change=_persist_cash,
)
_cash = float(st.session_state.get("td_cash_position", 0.0) or 0.0)

# Total assets = sum(current_price × shares) over all active holdings + cash.
_holdings_mv = sum(
    _current_price(h, _checks.get(h.id)) * float(h.shares or 0.0) for h in _active
)
_total_assets = _holdings_mv + _cash
_cash_ratio = (_cash / _total_assets * 100.0) if _total_assets > 0 else 0.0
_cc[1].metric(t("td_total_assets"), f"${_total_assets:,.0f}")
_cc[2].metric(t("td_holdings_value"), f"${_holdings_mv:,.0f}")
_cc[3].metric(t("td_cash_ratio"), f"{_cash_ratio:.1f}%")


# --- Close-confirmation flow (st.dialog when available, else inline) ---------
def _close_confirm_body() -> None:
    info = st.session_state.get("td_close_confirm") or {}
    if not info:
        return
    proceeds = float(info.get("shares", 0.0)) * float(info.get("price", 0.0))
    st.write(f"**{info.get('ticker', '?')}** · "
             f"{t('td_close_shares')}: {info.get('shares', 0):g}")
    st.write(f"{t('td_close_proceeds')}: **${proceeds:,.2f}**")
    st.write(t("td_close_add_cash_q").format(amt=f"${proceeds:,.2f}"))
    choice = st.radio(
        t("td_close_add_cash"), [t("td_yes"), t("td_no")],
        horizontal=True, key="td_close_radio",
    )
    bcols = st.columns(2)
    if bcols[0].button("✅ " + t("td_confirm"), key="td_close_confirm_yes",
                       use_container_width=True):
        close_holding(info["id"], float(info["price"]),
                      datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        if choice == t("td_yes"):
            # Deferred to the next run (the cash widget is already live here).
            st.session_state["td_pending_cash_add"] = proceeds
        st.session_state["td_close_confirm"] = None
        st.session_state["td_editing_id"] = None
        _refresh(get_active_holdings(), force=True)
        st.rerun()
    if bcols[1].button("✖ " + t("td_cancel"), key="td_close_confirm_no",
                       use_container_width=True):
        st.session_state["td_close_confirm"] = None
        st.rerun()


if st.session_state.get("td_close_confirm"):
    if hasattr(st, "dialog"):
        @st.dialog(t("td_close_confirm_title"))
        def _close_dialog() -> None:
            _close_confirm_body()

        _close_dialog()
    else:
        with st.container(border=True):
            st.markdown(f"**🔒 {t('td_close_confirm_title')}**")
            _close_confirm_body()


# Brokerage-style collapsible holdings table — scoped CSS via st-key-* classes
# (hover highlight, group dividers, child-row hierarchy accent). Compact rows.
st.markdown(
    """
    <style>
    /* Ticker group — a clear divider between every ticker block. */
    div[class*="st-key-tdgrp-"] {
        border-bottom: 2px solid var(--bd);
        margin-bottom: 4px;
        padding-bottom: 2px;
    }
    /* Parent (merged ticker) row — hover highlight, rounded, compact. */
    div[class*="st-key-tdrow-"] {
        border-radius: 6px;
        padding: 2px 6px;
        transition: background 0.12s ease;
    }
    div[class*="st-key-tdrow-"]:hover { background: rgba(56,139,253,0.10); }
    /* Child (per-horizon) row — indented accent + its own hover; columns still
       use the SAME widths as the header for strict alignment. */
    div[class*="st-key-tdchild-"] {
        border-left: 2px solid #388bfd66;
        border-top: 1px solid var(--bd);
        padding: 2px 6px;
        background: rgba(56,139,253,0.035);
        transition: background 0.12s ease;
    }
    div[class*="st-key-tdchild-"]:hover { background: rgba(56,139,253,0.09); }
    /* Tighten paragraph spacing inside the table for a dense, pro look. */
    div[class*="st-key-tdrow-"] p, div[class*="st-key-tdchild-"] p {
        margin-bottom: 0 !important;
        font-size: 0.86rem;
    }
    /* Parent collapse control — render the arrow+ticker button as plain inline
       text (no box border / background / shadow), left-aligned. */
    div[class*="st-key-td_expand_"] button {
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
        padding: 0 !important;
        text-align: left !important;
        justify-content: flex-start !important;
        min-height: 0 !important;
    }
    div[class*="st-key-td_expand_"] button:hover { background: transparent !important; }
    div[class*="st-key-td_expand_"] button p { font-size: 0.92rem !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

if not _active:
    st.info(t("td_no_holdings"))
else:
    # Group active holdings by ticker; each ticker is one merged parent row.
    _groups: dict = {}
    for h in _active:
        _groups.setdefault(h.ticker.upper(), []).append(h)

    # Header row — child rows reuse these SAME widths for strict alignment.
    _W = [1.3, 0.9, 1.0, 1.0, 0.9, 1.1, 1.0, 1.1, 0.7]
    _headers = [t("td_ticker"), t("td_shares"), t("td_avg_cost"), t("td_col_price"),
                t("td_pnl"), t("td_market_value"), t("td_position_pct"),
                t("td_col_status"), ""]
    _hcols = st.columns(_W, vertical_alignment="center")
    for _col, _label in zip(_hcols, _headers):
        _col.markdown(
            f"<span style='font-size:0.66rem;color:var(--t1);text-transform:uppercase;"
            f"letter-spacing:0.05em;'>{_label}</span>",
            unsafe_allow_html=True,
        )
    st.markdown("<hr style='margin:3px 0;border-color:var(--bd);'>", unsafe_allow_html=True)

    for _tk, _hs in sorted(_groups.items()):
        _total_shares = sum(float(h.shares or 0.0) for h in _hs)
        _cost_sum = sum(float(h.shares or 0.0) * float(h.cost_basis or 0.0) for h in _hs)
        _avg_cost = (_cost_sum / _total_shares) if _total_shares > 0 else 0.0
        _cp = _ticker_price(_hs)
        _mv = _cp * _total_shares
        _pnl = ((_cp / _avg_cost - 1.0) * 100.0) if _avg_cost > 0 and _cp > 0 else 0.0
        _pos_pct = (_mv / _total_assets * 100.0) if _total_assets > 0 else 0.0
        # Parent badge = WORST status across this ticker's per-horizon holdings,
        # looked up from thesis_check_results by holding_id (broken > weakening
        # > watch > intact).
        _worst = _worst_status(_hs)
        _expanded = _tk in st.session_state["td_expanded_tickers"]
        _pnl_color = "#3fb950" if _pnl >= 0 else "#f85149"

        with st.container(key=f"tdgrp-{_tk}"):
            # --- Parent (merged ticker) row ---
            with st.container(key=f"tdrow-{_tk}"):
                rc = st.columns(_W, vertical_alignment="center")
                _arrow = "▼" if _expanded else "▶"
                # Left-side collapse arrow (clickable) + ticker.
                if rc[0].button(f"{_arrow} **{_tk}**", key=f"td_expand_{_tk}",
                                use_container_width=True):
                    if _expanded:
                        st.session_state["td_expanded_tickers"].discard(_tk)
                    else:
                        st.session_state["td_expanded_tickers"].add(_tk)
                    st.rerun()
                rc[1].markdown(f"{_total_shares:g}")
                rc[2].markdown(f"${_avg_cost:,.2f}")
                rc[3].markdown(f"${_cp:g}" if _cp else "—")
                rc[4].markdown(
                    f"<span style='color:{_pnl_color};font-weight:600;'>{_pnl:+.1f}%</span>",
                    unsafe_allow_html=True,
                )
                rc[5].markdown(f"${_mv:,.0f}")
                rc[6].markdown(f"{_pos_pct:.1f}%")
                rc[7].markdown(
                    _badge(_status_label(_worst), _STATUS_COLORS.get(_worst, "#8b949e")),
                    unsafe_allow_html=True,
                )
                # rc[8] (action col) stays empty on the parent row.

            # --- Child (per-horizon) rows, only shares > 0, when expanded ---
            if _expanded:
                for h in _hs:
                    if float(h.shares or 0.0) <= 0:
                        continue
                    _chk = _checks.get(h.id)
                    _hstatus = getattr(_chk, "thesis_status", "intact") if _chk else "intact"
                    _h_shares = float(h.shares or 0.0)
                    _h_cost = float(h.cost_basis or 0.0)
                    _h_pnl = ((_cp / _h_cost - 1.0) * 100.0) if _h_cost > 0 and _cp > 0 else 0.0
                    _h_mv = _cp * _h_shares
                    _h_pos = (_h_mv / _total_assets * 100.0) if _total_assets > 0 else 0.0
                    _h_pnl_color = "#3fb950" if _h_pnl >= 0 else "#f85149"
                    _editing_this = st.session_state.get("td_editing_id") == h.id
                    with st.container(key=f"tdchild-{h.id}"):
                        cc = st.columns(_W, vertical_alignment="center")
                        # Horizon label — plain centered text (same font as the
                        # ticker; no badge, no color), grid stays aligned.
                        cc[0].markdown(
                            f"<div style='text-align:center;'>{_horizon_label(h.horizon)}</div>",
                            unsafe_allow_html=True,
                        )
                        cc[1].markdown(f"{_h_shares:g}")
                        cc[2].markdown(f"${_h_cost:g}")
                        cc[3].markdown("")  # current price NOT repeated (parent has it)
                        cc[4].markdown(
                            f"<span style='color:{_h_pnl_color};font-weight:600;'>"
                            f"{_h_pnl:+.1f}%</span>",
                            unsafe_allow_html=True,
                        )
                        cc[5].markdown(f"${_h_mv:,.0f}")
                        cc[6].markdown(f"{_h_pos:.1f}%")
                        cc[7].markdown(
                            _badge(_status_label(_hstatus),
                                   _STATUS_COLORS.get(_hstatus, "#8b949e")),
                            unsafe_allow_html=True,
                        )
                        if cc[8].button(("✖" if _editing_this else "✏️"),
                                        key=f"td_edit_btn_{h.id}",
                                        use_container_width=True):
                            st.session_state["td_editing_id"] = (
                                None if _editing_this else h.id
                            )
                            st.session_state["td_adding"] = False
                            st.rerun()
                    # Optional key-development alert below the child row.
                    _alert = _key_alert(_chk)
                    if _alert and _alert != "—":
                        st.markdown(
                            f"<div style='padding-left:26px;font-size:0.78rem;"
                            f"color:var(--t1);'>⚠️ {_alert}</div>",
                            unsafe_allow_html=True,
                        )
                    if _editing_this:
                        _render_edit_form(h)

# Add Position form (the edit form is rendered inline under its child row).
if st.session_state.get("td_adding"):
    _render_add_form()


# ---------------------------------------------------------------------------
# SECTION 2 — Order Recommendations
# ---------------------------------------------------------------------------

st.divider()
st.subheader("🎯 " + t("td_sec2_header"))
st.caption(t("td_sec2_subheader"))


def _render_order_card(h, rec) -> None:
    levels = rec["levels"]
    narrative = rec["narrative"]
    # The computed (fine-grained) action drives the colored action badge; the
    # LLM narrative.action_suggestion is the high-level synthesis label.
    fine_action = getattr(levels, "action", "wait")
    scenario = getattr(levels, "scenario", "initiate")
    _hz = getattr(levels, "horizon", h.horizon)
    blocked = getattr(levels, "entry_blocked", False)
    lang = _lang()
    with st.container(border=True):
        r1 = st.columns([1.8, 1.1, 1.2, 1.3])
        r1[0].markdown(f"**{h.ticker}**")
        # Horizon badge (short = blue, mid = green, long = purple).
        r1[1].markdown(_badge(_horizon_label(_hz), _horizon_color(_hz)),
                       unsafe_allow_html=True)
        # Scenario badge (建仓 / 加仓 / 管理).
        r1[2].markdown(_badge(_scenario_label(scenario), "#388bfd"), unsafe_allow_html=True)
        # Action badge, color-coded per action type.
        r1[3].markdown(
            _badge(_fine_action_label(fine_action), _fine_action_color(fine_action)),
            unsafe_allow_html=True,
        )
        # LONG valuation-confidence badge (high=green, medium=yellow, low=gray).
        if (_hz or "").strip().lower() == "long":
            _conf = getattr(levels, "valuation_confidence", "low")
            st.markdown(
                f"{t('td_valuation_confidence')}: "
                + _badge(_confidence_label(_conf), _confidence_color(_conf)),
                unsafe_allow_html=True,
            )
        # Row 2 — entry / stop / target. The entry zone may be None (blocked).
        r2 = st.columns(3)
        if blocked:
            r2[0].metric(t("td_entry_zone"), "—")
        else:
            r2[0].metric(
                t("td_entry_zone"),
                f"{levels.entry_zone_low}–{levels.entry_zone_high}",
            )
        r2[1].metric(t("td_stop_loss"), f"{levels.stop_loss_level}")
        r2[2].metric(t("td_target"), f"{levels.target_price}")
        # Entry-status banner (blocked / waiting for pullback / below zone).
        _es = getattr(levels, "entry_status", "in_zone")
        if blocked:
            _reason = getattr(levels, "reason", "") or getattr(levels, "entry_blocked_reason", "")
            st.markdown(
                _badge(f"{t('td_opp_blocked')} · {_reason}", "#8b949e"),
                unsafe_allow_html=True,
            )
        elif _es == "above_zone":
            st.markdown(_badge(t("td_opp_above_zone"), "#d29922"), unsafe_allow_html=True)
            if getattr(levels, "wait_target", ""):
                st.caption(levels.wait_target)
        elif _es == "below_zone":
            st.markdown(_badge(t("td_opp_below_zone"), "#e8590c"), unsafe_allow_html=True)
            if getattr(levels, "wait_target", ""):
                st.caption(levels.wait_target)
        # Missing conditions — shown as a bullet list whenever entry is blocked.
        _missing = getattr(levels, "missing_conditions", []) or []
        if _missing:
            st.markdown(f"**{t('td_missing_conditions')}:**")
            for _m in _missing:
                st.markdown(f"- {_m}")
        # Next trigger — prominently displayed when there is no entry zone.
        if blocked and getattr(levels, "next_trigger", ""):
            st.markdown(
                f'<div style="border-left:3px solid #d29922;padding:2px 10px;'
                f'margin:4px 0;color:var(--t0);">🎯 {t("td_next_trigger")}: '
                f"{levels.next_trigger}</div>",
                unsafe_allow_html=True,
            )
        # Row 3 — R:R (red if < 1.5) + position sizing band.
        rr = levels.risk_reward_ratio
        rr_color = "#f85149" if rr < 1.5 else "#3fb950"
        r3 = st.columns(2)
        r3[0].markdown(
            f"{t('td_rr_ratio')}: "
            f'<span style="color:{rr_color};font-weight:600;">{rr:.2f}</span>',
            unsafe_allow_html=True,
        )
        if getattr(levels, "position_sizing", ""):
            r3[1].markdown(f"{t('td_position_size')}: **{levels.position_sizing}**")
        # Risk overlay (add scenario): blocking note + projected weight / blended cost.
        if scenario == "add":
            if not getattr(levels, "risk_overlay_passed", True) and getattr(levels, "risk_overlay_note", ""):
                st.markdown(
                    _badge(f"{t('td_risk_overlay_note')} · {levels.risk_overlay_note}", "#e8590c"),
                    unsafe_allow_html=True,
                )
            _waa = getattr(levels, "portfolio_weight_after_add", 0.0) or 0.0
            _bca = getattr(levels, "blended_cost_after_add", None)
            if _waa or _bca is not None:
                _ra = st.columns(2)
                if _waa:
                    _ra[0].markdown(f"{t('td_weight_after_add')}: **{_waa*100:.1f}%**")
                if _bca is not None:
                    _ra[1].markdown(f"{t('td_blended_cost')}: **${_bca}**")
        # Row 4 — LLM action reasoning (bilingual; reads the current language).
        _reasoning = _bi(narrative, "action_reasoning", lang)
        if _reasoning:
            st.write(_reasoning)
        # Row 5 — next-trigger note from the LLM narrative (bilingual).
        _ntn = _bi(narrative, "next_trigger_note", lang)
        if _ntn:
            st.caption(f"🎯 {_ntn}")
        # Row 6 — candlestick.
        if levels.candlestick_pattern and levels.candlestick_pattern != "none":
            st.caption(f"{t('td_candlestick')}: {levels.candlestick_pattern}")
        # Row 7 — risk warning + risk note (bilingual).
        _rw = _bi(narrative, "risk_warning", lang)
        if _rw:
            st.markdown(
                f'<span style="color:#f85149;">⚠️ {_rw}</span>',
                unsafe_allow_html=True,
            )
        with st.expander("🔎 " + t("td_details")):
            if getattr(levels, "risk_note", ""):
                st.caption(f"{t('td_risk_note')}: {levels.risk_note}")
            _en = _bi(narrative, "entry_note", lang)
            if _en:
                st.write(_en)
            _sn = _bi(narrative, "stop_note", lang)
            if _sn:
                st.write(_sn)
            _tn = _bi(narrative, "target_note", lang)
            if _tn:
                st.write(_tn)
            st.caption(f"{t('td_support')}: " + ", ".join(str(x) for x in levels.support_levels) or "—")
            st.caption(f"{t('td_resistance')}: " + ", ".join(str(x) for x in levels.resistance_levels) or "—")
            st.caption(f"{t('td_volume_trend')}: {_vol_label(levels.volume_trend)}")
            st.caption(f"{t('td_atr')}: {levels.atr_14}")
            _fva = getattr(levels, "fair_value_anchor", None)
            if _fva is not None:
                # Phase 6C-B — surface the provenance of the fair-value anchor.
                _fvs = getattr(levels, "fair_value_source", "app_fair_value")
                _fvs_lbl = {
                    "app_computed": t("td_fv_src_app"),
                    "app_fair_value": t("td_fv_src_app_fair_value"),
                    "fixture": t("td_fv_src_fixture"),
                }.get(_fvs, _fvs)
                _fvs_color = "#3fb950" if _fvs == "app_computed" else (
                    "#8b949e" if _fvs == "fixture" else "#388bfd")
                st.markdown(
                    f"{t('td_fair_value_anchor')}: **{_fva}** &nbsp; "
                    + _badge(f"{t('td_fair_value_source')}: {_fvs_lbl}", _fvs_color),
                    unsafe_allow_html=True,
                )
                # Epoch stamp (Anchor Intel v2, U3) — the AppFairValue compute time
                # behind this anchor, surfaced unobtrusively (caption only). All
                # anchor-derived numbers on this card come from that one instance.
                _fvc = getattr(levels, "fair_value_computed_at", "") or ""
                if _fvc:
                    st.caption(
                        f"{t('cockpit_fv_computed_at')}: {_fvc[:16].replace('T', ' ')} UTC")
            st.caption(t("td_kelly_note"))
            _src = t("td_data_live") if levels.data_source == "live" else t("td_data_fixture")
            st.caption(f"· {_src}")


def _prefill_from_ticker(tk: str) -> None:
    """Stage an Add-Position prefill for a Scanner candidate by ticker."""
    sig = next(
        (s for s in (st.session_state.get("cockpit_triple_signals", []) or [])
         if str(s.get("ticker", "")).upper().strip() == tk.upper()),
        {},
    )
    ks = sig.get("key_signals", []) or []
    st.session_state["td_prefill"] = {
        "ticker": tk,
        "horizon": _dominant_horizon(sig) if sig else "mid",
        "thesis_text": "\n".join(f"- {x}" for x in ks),
        "thesis_source": "scanner",
        "thesis_signals": ks,
    }
    st.session_state["td_adding"] = True
    st.session_state["td_editing_id"] = None


# Actionable Signals — in-zone Scanner candidates surfaced ABOVE holdings orders.
_actionable = st.session_state.get("td_actionable_signals", []) or []
if _actionable:
    st.markdown(f"**⚡ {t('td_actionable_header')}**")
    for _sig in _actionable:
        _tk = _sig.get("ticker", "?")
        with st.container(border=True):
            ac = st.columns([1.2, 2.2, 1.1, 1.1, 0.9, 1.0, 1.2])
            ac[0].markdown(f"**{_tk}**")
            ac[1].markdown(
                f"{t('td_entry_zone')}: "
                f"{_sig.get('entry_zone_low')}–{_sig.get('entry_zone_high')}"
            )
            ac[2].markdown(f"{t('td_stop_loss')}: {_sig.get('stop_loss')}")
            ac[3].markdown(f"{t('td_target')}: {_sig.get('target_price')}")
            _arr = _sig.get("risk_reward_ratio", 0.0) or 0.0
            _arr_color = "#f85149" if _arr < 1.5 else "#3fb950"
            ac[4].markdown(
                f"{t('td_rr_ratio')}: "
                f'<span style="color:{_arr_color};font-weight:600;">{_arr:.2f}</span>',
                unsafe_allow_html=True,
            )
            ac[5].markdown(
                f"{t('td_position_size')}: {(_sig.get('position_size_pct', 0.0) or 0.0)*100:.1f}%"
            )
            if ac[6].button("➕ " + t("td_add_to_holdings"), key=f"td_actionable_{_tk}",
                            use_container_width=True):
                _prefill_from_ticker(_tk)
                st.rerun()
            st.caption(t("td_signal_from_scanner"))


if not _active:
    st.info(t("td_no_holdings"))
else:
    _broken = []
    for h in _active:
        chk = _checks.get(h.id)
        status = getattr(chk, "thesis_status", "intact") if chk else "intact"
        rec = _order_recs.get(h.id)
        if rec is None:
            continue
        if status == "broken":
            _broken.append((h, rec))
            continue
        _render_order_card(h, rec)

    # Broken-thesis holdings shown separately with exit-only framing.
    if _broken:
        st.markdown(
            f'<div style="border:1px solid #f85149;border-radius:8px;padding:6px 12px;'
            f'margin-top:8px;color:#f85149;font-weight:600;">⛔ {t("td_broken_section")}</div>',
            unsafe_allow_html=True,
        )
        for h, rec in _broken:
            _render_order_card(h, rec)


# ---------------------------------------------------------------------------
# SECTION 3 — Opportunity Watch
# ---------------------------------------------------------------------------

st.divider()
st.subheader("🔭 " + t("td_sec3_header"))

# Opportunity Watch candidates: Cockpit hand-off (td_pending_signals, any signal
# strength) merged with the legacy triple-signal hand-off (cockpit_triple_signals,
# retained as a fallback). Deduped by ticker; pending takes precedence.
_triples = st.session_state.get("cockpit_triple_signals", []) or []
_pending = st.session_state.get("td_pending_signals", []) or []
_seen_sec3: set = set()
_opp_candidates: list = []
for _s in (list(_pending) + list(_triples)):
    _stk = str(_s.get("ticker", "")).upper().strip()
    if not _stk or _stk in _seen_sec3:
        continue
    _seen_sec3.add(_stk)
    _opp_candidates.append(_s)
_held_tickers = {h.ticker.upper() for h in _active}
_opp_levels = st.session_state.get("opportunity_levels", {}) or {}


def _opp_status_badge(status) -> str:
    """Unified five-state status badge (Phase 7A naming, shared with Cockpit)."""
    if not status:
        return _badge(t("opp_status_pending"), "#8b949e")
    return _badge(t(_OPP_STATUS_KEY.get(status, "opp_status_research")),
                  _OPP_STATUS_COLOR.get(status, "#8b949e"))


def _render_opp_entry_zone(levels, signal: dict | None = None) -> None:
    """Render the per-candidate five-state status banner + entry numbers.

    The legacy in_zone/above_zone/below_zone/blocked vocabulary is unified into
    the Phase 7A five-state system via ``opportunity_ranker.derive_status``. The
    deterministic entry numbers (zone/stop/target/R:R/size) are shown only when
    the state is Actionable Now. ``signal`` carries the Cockpit hand-off fields
    (blockers/candidate_type) so the mapping matches the Cockpit's."""
    if levels is None:
        st.markdown(_opp_status_badge(None), unsafe_allow_html=True)
        return
    signal = signal or {}
    horizon = _dominant_horizon(signal) if signal else getattr(levels, "horizon", "mid")
    status = derive_status(levels, signal, signal.get("blockers", []) or [], horizon)
    st.markdown(_opp_status_badge(status), unsafe_allow_html=True)
    if status == STATUS_ACTIONABLE:
        z1 = st.columns(3)
        z1[0].metric(t("td_entry_zone"), f"{levels.entry_zone_low}–{levels.entry_zone_high}")
        z1[1].metric(t("td_stop_loss"), f"{levels.stop_loss}")
        z1[2].metric(t("td_target"), f"{levels.target_price}")
        _rr = getattr(levels, "risk_reward_ratio", 0.0) or 0.0
        _rr_color = "#f85149" if _rr < 1.5 else "#3fb950"
        z2 = st.columns(2)
        z2[0].markdown(
            f"{t('td_rr_ratio')}: "
            f'<span style="color:{_rr_color};font-weight:600;">{_rr:.2f}</span>',
            unsafe_allow_html=True,
        )
        z2[1].markdown(
            f"{t('td_position_size')}: **{(getattr(levels, 'position_size_pct', 0.0) or 0.0)*100:.1f}%**"
        )
    else:
        # Surface the engine's next_trigger / stabilization text (unified wording).
        _nt, _ = status_next_trigger(levels, horizon, status)
        _wt = _nt or getattr(levels, "wait_target", "") or getattr(levels, "entry_blocked_reason", "")
        if _wt:
            st.caption(f"⏭️ {t('opp_next_trigger')}: {_wt}")


if not _opp_candidates:
    st.info(t("td_sec3_empty"))
else:
    _shown = [s for s in _opp_candidates if str(s.get("ticker", "")).upper() not in _held_tickers]
    if not _shown:
        st.info(t("td_sec3_empty"))
    for s in _shown:
        with st.container(border=True):
            c = st.columns([1.6, 2.6, 1.2])
            c[0].markdown(f"**{s.get('ticker', '?')}**")
            # Phase 7A — grade-only display (never decimals) + setup label.
            _dom = _dominant_horizon(s)
            _grade = s.get(f"{_dom}_grade")
            _setup = s.get("setup", "")
            if _grade:
                _glabel = (f"{t('opp_grade')} "
                           + _badge(_grade, _OPP_GRADE_COLOR.get(_grade, "#8b949e")))
                if _setup:
                    _glabel += f" · 🎯 {t(_OPP_SETUP_KEY.get(_setup, 'opp_setup_speculative'))}"
                c[1].markdown(_glabel, unsafe_allow_html=True)
            else:
                # Legacy hand-off without ranker fields — fall back to raw scores.
                c[1].caption(
                    f"{_horizon_label('short')} {s.get('short_score', 0):.2f} · "
                    f"{_horizon_label('mid')} {s.get('mid_score', 0):.2f} · "
                    f"{_horizon_label('long')} {s.get('long_score', 0):.2f}"
                )
            if c[2].button("➕ " + t("td_add_to_holdings"), key=f"td_opp_{s.get('ticker')}"):
                ks = s.get("key_signals", []) or []
                st.session_state["td_prefill"] = {
                    "ticker": s.get("ticker", ""),
                    "horizon": _dom,
                    "thesis_text": "\n".join(f"- {x}" for x in ks),
                    "thesis_source": "scanner",
                    "thesis_signals": ks,
                }
                st.session_state["td_adding"] = True
                st.session_state["td_editing_id"] = None
                st.rerun()
            if s.get("catalyst_summary"):
                st.caption(f"⚡ {t('td_catalyst')}: {s.get('catalyst_summary')}")
            # Unified five-state status banner for this candidate (entry zone
            # pre-computed in _refresh; thesis assumed intact for a new candidate).
            _render_opp_entry_zone(
                _opp_levels.get(str(s.get("ticker", "")).upper().strip()), s)
            # Per-card blockers: ticker-specific, filtered to the displayed
            # horizon (market-wide conditions are not repeated per card — Task 3).
            _bk = _opp_ticker_blockers(s.get("blockers", []) or [], _dom)
            if _bk:
                _lang_td = st.session_state.get("language", "en")
                _chips = " ".join(
                    _badge(b.get(f"text_{_lang_td}") or b.get("text_en", b.get("code", "")),
                           "#f85149" if b.get("severity") == "critical" else "#d29922")
                    for b in _bk[:4])
                st.markdown(f"{t('opp_blockers')}: {_chips}", unsafe_allow_html=True)
