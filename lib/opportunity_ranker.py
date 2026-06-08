"""Phase 7A — Opportunity Ranking MVP (orchestration layer ONLY).

Turns the existing signal candidates into a ranked, actionable opportunity list.
This module is a **translation layer** over existing deterministic components
(``lib.order_advisor`` entry-zone engine, ``lib.signal_engine`` /
``lib.candidate_generator`` candidate scores, ``lib.theme_baskets`` momentum,
``lib.macro_regime`` regime, ``lib.macro_data`` releases, ``lib.data_fetcher``
earnings, ``lib.relative_strength`` RS). It implements **no new entry-zone,
stop, or technical-threshold logic** and invents **no numbers**.

See ``docs/reliability_phase_7a_opportunity_ranking.md`` for the status mapping
table, the weight config, and the snapshot schema. Review-only; not investment
advice. ``approved_for_execution`` is never set.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

# Anchor-cache freshness helpers (network-free local JSON). Imported with a
# fail-closed fallback so the ranker never hard-depends on the cache module.
try:  # pragma: no cover - import guard
    from lib.anchor_cache import (
        is_fresh as _anchor_is_fresh,
        entry_age_days as _anchor_age_days,
    )
except Exception:  # noqa: BLE001 — degrade to "no cache enrichment"
    def _anchor_is_fresh(entry, max_age_days=None, now=None):  # type: ignore
        return False

    def _anchor_age_days(entry, now=None):  # type: ignore
        return None


# Canonical key set of the FRESH snapshot anchor block (Anchor Intel v2.3 U2).
# Exported so the §18-style parity test derives the expected fields from the CODE
# (a field added here must be classified by the parity assertion, never silently).
ANCHOR_SNAPSHOT_KEYS = (
    "company_type", "fair_value_mid", "analyst_pool",
    "computed_at", "blend_state", "caveats",
)
# Honest-degrade token (shared with the R3 LONG-path contract): a ranking-path row
# with no fresh cached anchor records this state, never a fabricated value.
ANCHOR_NOT_CACHED = "anchor_not_cached"


def _anchor_snapshot_block(entry: Optional[dict], fresh: bool) -> dict:
    """Build the per-card snapshot anchor block from a cached entry (read-only).

    ``fresh`` is the SAME freshness decision that gated the LONG-status band, so
    the block is single-vintage with the status it accompanies. A non-fresh /
    missing entry yields ``{"state": ANCHOR_NOT_CACHED}`` — the honest-degrade
    contract (no fabricated anchor on the network-free path). Pure; never raises.
    """
    if not fresh or not isinstance(entry, dict):
        return {"state": ANCHOR_NOT_CACHED}
    pool = entry.get("analyst_pool")
    return {
        "company_type": str(entry.get("company_type", "") or ""),
        "fair_value_mid": entry.get("fair_value_mid"),
        "analyst_pool": pool if isinstance(pool, dict) else None,
        "computed_at": str(entry.get("computed_at", "") or ""),
        "blend_state": str(entry.get("blend_state", "") or ""),
        "caveats": list(entry.get("caveats", []) or []),
    }


# ===========================================================================
# Visible config block (calibration baseline — keep all tunables here)
# ===========================================================================

# Three INDEPENDENT horizon weight tables over normalized [0,1] components.
# Each column sums to 1.00. RS carries 0.20 in every horizon (per the outline).
HORIZON_WEIGHTS: dict[str, dict[str, float]] = {
    "short": {"signal": 0.30, "rs": 0.20, "catalyst": 0.20,
              "theme": 0.15, "entry": 0.10, "valuation": 0.05},
    "mid":   {"signal": 0.30, "theme": 0.20, "rs": 0.20,
              "valuation": 0.15, "catalyst": 0.10, "entry": 0.05},
    "long":  {"signal": 0.25, "valuation": 0.25, "rs": 0.20,
              "theme": 0.15, "entry": 0.10, "catalyst": 0.05},
}

# Grade bands (UI shows grades only, never decimals). Lower edge inclusive.
GRADE_BANDS = {"A": 0.66, "B": 0.40}  # >=0.66 A, >=0.40 B, else C

# Rule-based score penalties (network-free, TICKER-SPECIFIC signals only;
# subtracted from score). macro_regime_mismatch is intentionally NOT here: it is
# a market-wide condition shown once as a panel banner (it is uniform across all
# candidates at a horizon, so it never changes the ranking).
BLOCKER_PENALTIES = {
    "valuation_high": 0.10,
    "theme_lagging": 0.05,
}

# Calendar windows + ranking knobs (Task 3 thresholds live here).
CALENDAR_CONFIG = {
    "earnings_window_days": 7,   # earnings within N days gates short-horizon (per-card)
    "fomc_window_days": 3,       # FOMC within N days -> market banner (short)
    "cpi_window_days": 3,        # CPI within N days -> market banner (short)
    "top_n_enrich": 20,          # full status/entry-zone enrichment for top N
}

# Setup-classifier taxonomy thresholds (Task 6 — the setup taxonomy is the
# ranker's own domain; these are NOT entry/stop/zone numbers, which stay in
# lib/order_advisor.py). Kept here, next to the weights, for calibration.
SETUP_THRESHOLDS = {
    "rs_strong": 0.60,          # rs_composite >= -> "strong" relative strength
    "rs_moderate": 0.50,        # rs_composite >= -> positive relative strength
    "momentum_vol_ratio": 1.20,  # RS volume surge cutoff for Momentum Breakout
    "post_earnings_window_days": 21,  # bounded calendar days SINCE the last report
    "pullback_rs_min": 0.60,    # min rs_composite for the Pullback-to-Support flag
    "theme_strong": 0.50,       # theme momentum >= -> theme is supportive
}

# Phase 7B Task 1 — which RS window the why_now outperformance line reports per
# selected horizon (SHORT=5D, MID=1M, LONG=6M), and its bilingual label.
RS_LINE_WINDOW = {"short": "5d", "mid": "1m", "long": "6m"}
RS_LINE_LABEL = {"5d": ("5D", "5日"), "1m": ("1M", "近1月"), "6m": ("6M", "近6月")}

# Reason-code display hygiene (Task 2). A code firing for more than this share of
# today's ranked candidates differentiates no one and is demoted from display,
# unless dropping it would leave fewer than MIN_DISTINCTIVE_CODES.
REASON_COMMONALITY_SHARE = 0.50
MIN_DISTINCTIVE_CODES = 2

# Entry-quality label -> [0,1] component score.
_ENTRY_QUALITY_SCORE = {"good": 1.0, "fair": 0.6, "extended": 0.3, "avoid": 0.0}

# Valuation percentile above which a candidate is flagged "stretched".
_VALUATION_HIGH_PCT = 0.70
# Theme momentum below which a theme is "lagging" (stock can't lean on it).
_THEME_LAGGING_MOMENTUM = 0.33
# RS composite used when a ticker's price history is not cached (degraded).
_RS_NEUTRAL = 0.5
# Codes that are market-wide (shown once as a banner, never as per-card chips).
MARKET_WIDE_BLOCKER_CODES = {"macro_regime_mismatch", "fomc_within_window",
                             "cpi_within_window"}

# Five canonical opportunity states (unified vocabulary).
STATUS_ACTIONABLE = "Actionable Now"
STATUS_PULLBACK = "Wait for Pullback"
STATUS_BREAKOUT = "Wait for Breakout"
STATUS_RESEARCH = "Research Required"
STATUS_AVOID = "Avoid Chasing"

# Map a five-state status to the legacy badge palette used by the pages.
STATUS_COLOR = {
    STATUS_ACTIONABLE: "#3fb950",
    STATUS_PULLBACK: "#d29922",
    STATUS_BREAKOUT: "#388bfd",
    STATUS_RESEARCH: "#8b949e",
    STATUS_AVOID: "#f85149",
}

# 2025–2026 scheduled FOMC meeting end-dates (FRED does not provide these).
# Used only for days_to_fomc; review-only and easy to extend.
FOMC_DATES = [
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30",
    "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29",
    "2026-09-16", "2026-11-04", "2026-12-16",
]

SNAPSHOT_DIR = Path("data/snapshots")


# ===========================================================================
# Data classes
# ===========================================================================

@dataclass
class Blocker:
    """A structured, machine-readable reason a candidate is not Actionable Now."""

    code: str
    severity: str  # "critical" | "caution"
    text_en: str = ""
    text_zh: str = ""
    horizons: list = field(default_factory=list)  # [] = applies to all horizons

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReasonCode:
    """A raw why-now / why-it-matters code with bilingual display text."""

    code: str
    text_en: str = ""
    text_zh: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OpportunityCard:
    """One ranked opportunity (review-only)."""

    ticker: str
    theme: Optional[str] = None
    theme_label_en: str = ""
    theme_label_zh: str = ""
    theme_momentum: float = 0.0
    # Phase 7B Task 2 — the theme's divergence stage (rotating_in / leading /
    # rotating_out / out_of_favor) and whether breadth confirmed it. Carried to
    # the card, the Cockpit Section B summary, Send-to-Scanner, and the snapshot.
    theme_stage: str = ""
    theme_stage_confirmed: bool = False
    short_score: float = 0.0
    mid_score: float = 0.0
    long_score: float = 0.0
    short_grade: str = "C"
    mid_grade: str = "C"
    long_grade: str = "C"
    rs: dict = field(default_factory=dict)
    rs_degraded: bool = False  # True when price history was not cached (RS neutral)
    rs_stale: bool = False  # True when the cached RS frame lagged the benchmark vintage
    setup: str = "Speculative Watch"
    pullback_to_support: bool = False
    # Per-horizon five-state status (Fix round 2) — computed for short/mid/long so
    # the Cockpit horizon selector shows the correct status per view. Values are
    # None outside the top N (engine not run).
    status_by_horizon: dict = field(default_factory=dict)
    next_trigger_by_horizon: dict = field(default_factory=dict)
    status_reason_by_horizon: dict = field(default_factory=dict)  # horizon -> reason code dict
    # Convenience = the DOMINANT horizon's values (Trading Desk single-value handoff).
    status: Optional[str] = None
    next_trigger: str = ""
    blockers: list = field(default_factory=list)  # list[Blocker] (raw, all horizons)
    why_now: list = field(default_factory=list)  # list[ReasonCode] (raw)
    why_it_matters: list = field(default_factory=list)  # list[ReasonCode] (raw)
    why_now_display: list = field(default_factory=list)  # commonality-filtered
    why_matters_display: list = field(default_factory=list)  # commonality-filtered
    # Per-horizon why_now (7B Task 1) — the RS line follows the selected horizon
    # (SHORT=5D / MID=1M / LONG=6M). Populated for enriched (top-N) cards; the
    # Cockpit horizon selector renders the matching list. horizon -> list[ReasonCode].
    why_now_by_horizon: dict = field(default_factory=dict)
    days_to_earnings: Optional[int] = None
    days_since_earnings: Optional[int] = None
    days_to_fomc: Optional[int] = None
    days_to_cpi: Optional[int] = None
    # concentration_ref is computed at DISPLAY time (view-local), not stored here.
    concentration_ref: Optional[str] = None
    signal_strength: str = "none"
    candidate_type: str = "FUNNEL"
    enriched: bool = False
    # entry-zone numbers (top-N only; copied verbatim from PriceLevelResult)
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    risk_reward_ratio: float = 0.0
    position_size_pct: float = 0.0
    # Age (days) of the cached valuation anchor used to derive the LONG status,
    # or None when LONG was derived WITHOUT a fresh cached anchor (stale/missing →
    # the prior "Research Required / valuation anchor not established" behavior).
    # Lets future review assess the staleness impact of cache-driven LONG status.
    anchor_age_days: Optional[float] = None
    # Structured anchor block (Anchor Intel v2.3 U2) for the daily snapshot. Sourced
    # read-only from the SAME anchor_cache lookup that drove the LONG status (single
    # vintage; no live compute on this network-free path). A fresh cached entry →
    # {company_type, fair_value_mid, analyst_pool{…}, computed_at, blend_state,
    # caveats}; no fresh entry → {"state": "anchor_not_cached"} (the R3 honest-
    # degrade token, never a fabricated value).
    anchor_snapshot: Optional[dict] = None
    # optional LLM polish (language only; never alters judgments/numbers)
    why_now_polished_en: str = ""
    why_now_polished_zh: str = ""
    approved_for_execution: bool = False  # invariant: always False

    def to_dict(self) -> dict:
        return asdict(self)


# ===========================================================================
# Field access (candidate may be a CandidateSignal object or a plain dict)
# ===========================================================================

def _g(candidate, name, default=None):
    if isinstance(candidate, dict):
        v = candidate.get(name, default)
    else:
        v = getattr(candidate, name, default)
    return default if v is None else v


def _f(x, default: float = 0.0) -> float:
    try:
        if isinstance(x, bool) or x is None:
            return default
        v = float(x)
        return v if v == v else default
    except (TypeError, ValueError):
        return default


# ===========================================================================
# Component scoring + grades
# ===========================================================================

def _catalyst_component(candidate) -> float:
    """Catalyst freshness -> [0,1]: recent & not-priced-in scores highest."""
    recency = str(_g(candidate, "catalyst_recency", "none") or "none").lower()
    base = {"recent": 0.9, "moderate": 0.55, "none": 0.2}.get(recency, 0.2)
    if bool(_g(candidate, "already_priced_in", False)):
        base *= 0.5
    return round(max(0.0, min(1.0, base)), 4)


def _valuation_component(candidate) -> float:
    """Cheaper valuation -> higher. ``1 - valuation_percentile``."""
    pct = _f(_g(candidate, "valuation_percentile", 0.5), 0.5)
    pct = max(0.0, min(1.0, pct))
    return round(1.0 - pct, 4)


def _entry_component(candidate) -> float:
    label = str(_g(candidate, "entry_quality_label", "fair") or "fair").lower()
    return _ENTRY_QUALITY_SCORE.get(label, 0.6)


def _components(candidate, horizon: str, theme_momentum: float,
                rs_composite: float) -> dict:
    """The normalized [0,1] component scores for one horizon."""
    signal = {
        "short": _f(_g(candidate, "short_score", 0.0)),
        "mid": _f(_g(candidate, "mid_score", 0.0)),
        "long": _f(_g(candidate, "long_score", 0.0)),
    }[horizon]
    return {
        "signal": max(0.0, min(1.0, signal)),
        "rs": max(0.0, min(1.0, _f(rs_composite, 0.5))),
        "catalyst": _catalyst_component(candidate),
        "theme": max(0.0, min(1.0, _f(theme_momentum, 0.0))),
        "entry": _entry_component(candidate),
        "valuation": _valuation_component(candidate),
    }


def _horizon_rs_comp(rs, horizon: str, fallback: float) -> float:
    """The RS composite for one horizon (Phase 7B — each weight table consumes
    its own horizon's windows: SHORT=5D/10D, MID=1M/3M, LONG=6M/12M).

    Reads ``rs_short`` / ``rs_mid`` / ``rs_long`` from a RelativeStrength (or its
    ``.to_dict()``); falls back to the legacy overall composite when the
    per-horizon value is absent — so pre-7B RS objects score unchanged."""
    if rs is None:
        return fallback
    key = {"short": "rs_short", "mid": "rs_mid", "long": "rs_long"}[horizon]
    val = rs.get(key) if isinstance(rs, dict) else getattr(rs, key, None)
    return fallback if val is None else _f(val, fallback)


def _grade(score: float) -> str:
    if score >= GRADE_BANDS["A"]:
        return "A"
    if score >= GRADE_BANDS["B"]:
        return "B"
    return "C"


def score_horizon(candidate, horizon: str, theme_momentum: float,
                  rs_composite: float, penalties: float = 0.0) -> float:
    """Weighted-sum score for one horizon, minus blocker penalties, in [0,1]."""
    comps = _components(candidate, horizon, theme_momentum, rs_composite)
    weights = HORIZON_WEIGHTS[horizon]
    raw = sum(weights[k] * comps[k] for k in weights)
    return round(max(0.0, min(1.0, raw - penalties)), 4)


# ===========================================================================
# Setup classification
# ===========================================================================

def classify_setup(candidate, rs, theme_momentum: float = 0.0,
                   days_since_earnings: Optional[int] = None) -> tuple:
    """Rule-based setup type + Pullback-to-Support variant flag.

    Returns ``(setup_type, pullback_to_support)``. Every threshold comes from the
    ``SETUP_THRESHOLDS`` config block (Task 6 — the setup taxonomy is the ranker's
    own domain; it produces no entry/stop/zone numbers). ``days_since_earnings``
    (calendar days since the last reported quarter, from actual earnings dates) is
    only available during top-N enrichment; ``Post-earnings Reprice`` is gated on
    it within a bounded window — it is NEVER inferred from the LLM catalyst-recency
    field or from price gaps. ``rs`` is a
    :class:`~lib.relative_strength.RelativeStrength` or its ``.to_dict()``.
    """
    T = SETUP_THRESHOLDS

    def rsg(name, default=None):
        if isinstance(rs, dict):
            return rs.get(name, default)
        return getattr(rs, name, default)

    short = _f(_g(candidate, "short_score", 0.0))
    mid = _f(_g(candidate, "mid_score", 0.0))
    long = _f(_g(candidate, "long_score", 0.0))
    dominant = max((("short", short), ("mid", mid), ("long", long)),
                   key=lambda kv: kv[1])[0]
    eps = str(_g(candidate, "eps_revision_direction", "unknown") or "unknown").lower()
    ctype = str(_g(candidate, "candidate_type", "FUNNEL") or "FUNNEL").upper()
    entry_label = str(_g(candidate, "entry_quality_label", "fair") or "fair").lower()
    rs_comp = _f(rsg("rs_composite", _RS_NEUTRAL), _RS_NEUTRAL)
    theme_mom = _f(theme_momentum, 0.0)

    beats_spy_1m = (rsg("ret_1m_vs_spy") or 0) > 0
    beats_qqq_1m = (rsg("ret_1m_vs_qqq") or 0) > 0
    above20 = rsg("above_sma20") is True
    above50 = rsg("above_sma50") is True
    vol_ratio = rsg("vol_ratio") or 0
    has_signal = (short > 0 or mid > 0 or long > 0)

    # Pullback-to-Support variant: strong RS + a fired signal + price retraced
    # near support and not overextended (entry quality not "extended"/"avoid").
    pullback = bool(
        rs_comp >= T["pullback_rs_min"] and has_signal
        and entry_label in ("good", "fair")
        and above50  # still in the larger uptrend
        and (rsg("ret_5d") is not None and rsg("ret_5d") <= 0.0)  # short-term dip
    )

    # Priority-ordered classification.
    post_earnings = (days_since_earnings is not None
                     and days_since_earnings <= T["post_earnings_window_days"]
                     and eps in ("improving", "inflecting_up"))
    if post_earnings:
        setup = "Post-earnings Reprice"
    elif (dominant == "short" and beats_spy_1m and beats_qqq_1m
            and above20 and above50 and vol_ratio > T["momentum_vol_ratio"]):
        setup = "Momentum Breakout"
    elif entry_label == "good" and (rsg("ret_1m") is not None and rsg("ret_1m") < 0):
        setup = "Oversold Rebound"
    elif dominant == "mid" and theme_mom >= T["theme_strong"] and rs_comp >= T["rs_moderate"]:
        setup = "Mid-term Rotation"
    elif dominant == "long" and _valuation_component(candidate) >= 0.5 and above50:
        setup = "Long-term Accumulation"
    elif ctype == "ALT_SIGNAL" or not has_signal:
        setup = "Speculative Watch"
    else:
        # Reasonable default keyed on the dominant horizon.
        setup = {"short": "Momentum Breakout", "mid": "Mid-term Rotation",
                 "long": "Long-term Accumulation"}[dominant]
    return setup, pullback


# ===========================================================================
# Reason codes (raw, bilingual)
# ===========================================================================

def build_reason_codes(candidate, rs, theme_momentum: float,
                       levels=None, pullback: bool = False,
                       days_since_earnings: Optional[int] = None,
                       horizon: str = "mid") -> tuple:
    """Build (why_now, why_it_matters) raw reason-code lists.

    Task 2 — display text states ONLY what the rule verified (no priced-in
    judgment the system does not make) and embeds the already-computed RS / theme
    / valuation magnitudes so cards differentiate. Numbers are read from existing
    fields; nothing is recomputed.

    Phase 7B Task 1: the RS outperformance line follows the SELECTED ``horizon`` —
    SHORT shows the 5D excess, MID the 1M, LONG the 6M — so a short-horizon grade
    is backed by short-horizon evidence. The window's excess is read from the
    RelativeStrength flat fields (``ret_<win>_vs_qqq`` / ``_vs_spy``).
    """
    def rsg(name, default=None):
        if isinstance(rs, dict):
            return rs.get(name, default)
        return getattr(rs, name, default)

    why_now: list = []
    why_matters: list = []

    # ---- why now (timing) ----
    if levels is not None and getattr(levels, "entry_status", "") == "in_zone":
        why_now.append(ReasonCode(
            "in_entry_zone", "Price is inside the entry zone",
            "价格处于入场区间内"))
    if pullback:
        why_now.append(ReasonCode(
            "near_support_not_overextended",
            "Pulled back near support, not overextended",
            "回踩支撑附近，未过度延伸"))
    win = RS_LINE_WINDOW.get(horizon, "1m")
    en_lab, zh_lab = RS_LINE_LABEL.get(win, ("1M", "近1月"))
    r_qqq = rsg(f"ret_{win}_vs_qqq")
    if r_qqq is not None and r_qqq > 0:
        why_now.append(ReasonCode(
            "outperforming_qqq", f"{en_lab} vs QQQ {r_qqq*100:+.1f}%",
            f"{zh_lab}相对QQQ {r_qqq*100:+.1f}%"))
    r_spy = rsg(f"ret_{win}_vs_spy")
    if r_spy is not None and r_spy > 0:
        why_now.append(ReasonCode(
            "outperforming_spy", f"{en_lab} vs SPY {r_spy*100:+.1f}%",
            f"{zh_lab}相对SPY {r_spy*100:+.1f}%"))
    # Catalyst code names ONLY what the rule checks: a recent catalyst within the
    # window. It does NOT claim a "priced-in" judgment (the system makes none).
    recency = str(_g(candidate, "catalyst_recency", "none") or "none").lower()
    if recency == "recent":
        why_now.append(ReasonCode(
            "recent_catalyst", "Recent catalyst flagged",
            "存在近期催化剂"))
    if days_since_earnings is not None and days_since_earnings <= SETUP_THRESHOLDS["post_earnings_window_days"]:
        why_now.append(ReasonCode(
            "recent_earnings", f"Reported {days_since_earnings}d ago",
            f"{days_since_earnings}天前发布财报"))

    # ---- why it matters (thesis) ----
    tm = _f(theme_momentum, 0.0)
    if tm >= 0.66:
        why_matters.append(ReasonCode(
            "theme_momentum_strong",
            f"Theme in the top momentum tier ({tm*100:.0f}th pct)",
            f"主题动能居前（{tm*100:.0f}百分位）"))
    eps = str(_g(candidate, "eps_revision_direction", "unknown") or "unknown").lower()
    if eps in ("improving", "inflecting_up"):
        why_matters.append(ReasonCode(
            "eps_revisions_improving", "EPS estimates revised up",
            "EPS预期上修"))
    vpct = _f(_g(candidate, "valuation_percentile", 0.5), 0.5)
    if _valuation_component(candidate) >= 0.6:
        why_matters.append(ReasonCode(
            "valuation_reasonable",
            f"Valuation in the lower {vpct*100:.0f}th pct vs sector",
            f"估值处于行业较低区间（{vpct*100:.0f}百分位）"))
    if str(_g(candidate, "signal_strength", "none")) == "triple":
        why_matters.append(ReasonCode(
            "triple_horizon_signal", "Signal fires across all three horizons",
            "三个时间维度均触发信号"))
    return why_now, why_matters


def filter_common_reasons(cards: list, attr: str) -> None:
    """Demote over-common reason codes from the per-card DISPLAY list (Task 2).

    A code firing for more than ``REASON_COMMONALITY_SHARE`` of the ranked cards
    differentiates no one, so it is dropped from ``{attr}_display`` — unless doing
    so would leave a card with fewer than ``MIN_DISTINCTIVE_CODES`` (then the raw
    list is kept). Raw codes on ``card.{attr}`` are never mutated (stored raw).
    """
    cards = [c for c in cards if c is not None]
    n = len(cards)
    display_attr = {"why_now": "why_now_display",
                    "why_it_matters": "why_matters_display"}[attr]
    if n == 0:
        return
    counts: dict = {}
    for c in cards:
        for r in getattr(c, attr, []) or []:
            counts[r.code] = counts.get(r.code, 0) + 1
    common = {code for code, k in counts.items() if k > REASON_COMMONALITY_SHARE * n}
    for c in cards:
        raw = list(getattr(c, attr, []) or [])
        distinctive = [r for r in raw if r.code not in common]
        setattr(c, display_attr,
                distinctive if len(distinctive) >= MIN_DISTINCTIVE_CODES else raw)


# ===========================================================================
# Blockers (rule-based; calendar blockers added during top-N enrichment)
# ===========================================================================

def build_rule_blockers(candidate, theme_momentum: float, *,
                        has_theme: bool = False) -> list:
    """Network-free, TICKER-SPECIFIC blockers known for ALL candidates (score
    penalties apply). Market-wide conditions (macro regime, FOMC/CPI) are NOT
    here — they go to the panel banner via :func:`market_banner_blockers`."""
    blockers: list = []
    pct = _f(_g(candidate, "valuation_percentile", 0.5), 0.5)
    if pct >= _VALUATION_HIGH_PCT:
        blockers.append(Blocker(
            "valuation_high", "critical",
            f"Valuation stretched ({pct*100:.0f}th pct)",
            f"估值偏高（{pct*100:.0f}百分位）"))
    # Theme strong elsewhere but stock lagging it: the theme is weak so the
    # stock cannot lean on it.
    if _f(theme_momentum, 0.0) < _THEME_LAGGING_MOMENTUM and has_theme:
        blockers.append(Blocker(
            "theme_lagging", "caution",
            "Theme momentum is weak", "主题动能偏弱"))
    return blockers


def market_banner_blockers(macro_regime: str, horizon_bias: Optional[dict],
                           days_to_fomc: Optional[int], days_to_cpi: Optional[int],
                           horizon: str = "mid") -> list:
    """Market-wide conditions for the displayed horizon — shown ONCE as a
    panel-level banner above the cards, never as per-card chips (Task 3)."""
    out: list = []
    bias = (horizon_bias or {}).get(horizon, "")
    if str(bias).lower() in ("cautious", "unfavorable"):
        out.append(Blocker(
            "macro_regime_mismatch", "caution",
            f"Macro regime {macro_regime} is {bias} for the {horizon} horizon",
            f"宏观环境（{macro_regime}）对{horizon}周期{bias}",
            horizons=[horizon]))
    if horizon == "short":
        if days_to_fomc is not None and days_to_fomc <= CALENDAR_CONFIG["fomc_window_days"]:
            out.append(Blocker(
                "fomc_within_window", "caution",
                f"FOMC in {days_to_fomc}d", f"{days_to_fomc}天后FOMC",
                horizons=["short"]))
        if days_to_cpi is not None and days_to_cpi <= CALENDAR_CONFIG["cpi_window_days"]:
            out.append(Blocker(
                "cpi_within_window", "caution",
                f"CPI in {days_to_cpi}d", f"{days_to_cpi}天后CPI",
                horizons=["short"]))
    return out


def _penalty_total(blockers: list) -> float:
    return round(sum(BLOCKER_PENALTIES.get(b.code, 0.0) for b in blockers), 4)


# ===========================================================================
# Calendar blockers (Task 3)
# ===========================================================================

def days_to_event(event_date_str: Optional[str], today: Optional[date] = None) -> Optional[int]:
    """Days from ``today`` to ``event_date_str`` (YYYY-MM-DD). None if past/invalid."""
    if not event_date_str:
        return None
    today = today or date.today()
    try:
        ev = datetime.strptime(str(event_date_str)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    delta = (ev - today).days
    return delta if delta >= 0 else None


def days_to_next_fomc(today: Optional[date] = None,
                      fomc_dates: Optional[list] = None) -> Optional[int]:
    today = today or date.today()
    cands = []
    for d in (fomc_dates or FOMC_DATES):
        n = days_to_event(d, today)
        if n is not None:
            cands.append(n)
    return min(cands) if cands else None


def days_to_next_cpi(cpi_date_str: Optional[str], today: Optional[date] = None) -> Optional[int]:
    """Next CPI release. CPI is monthly; project the last release forward by
    whole months until the date is today-or-later."""
    if not cpi_date_str:
        return None
    today = today or date.today()
    try:
        last = datetime.strptime(str(cpi_date_str)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    nxt = last
    guard = 0
    while nxt < today and guard < 24:
        # advance ~1 month preserving day-of-month where possible
        month = nxt.month + 1
        year = nxt.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        day = min(nxt.day, 28)
        nxt = date(year, month, day)
        guard += 1
    delta = (nxt - today).days
    return delta if delta >= 0 else None


def default_earnings_timing(ticker: str) -> dict:
    """Per-ticker earnings timing from ACTUAL dates (top-N only; free source).

    Returns ``{"days_to_earnings": int|None, "days_since_earnings": int|None}``.
    ``days_to_earnings`` comes from the existing ``get_earnings_calendar``;
    ``days_since_earnings`` is the calendar gap to the most recent PAST reported
    date (yfinance ``get_earnings_dates``). Fully fail-closed."""
    out = {"days_to_earnings": None, "days_since_earnings": None}
    try:
        from lib.data_fetcher import get_earnings_calendar

        out["days_to_earnings"] = (get_earnings_calendar(ticker) or {}).get("days_to_earnings")
    except Exception:  # noqa: BLE001
        pass
    try:
        import yfinance as yf

        df = yf.Ticker(ticker).get_earnings_dates(limit=8)
        if df is not None and len(df):
            today = datetime.now().date()
            past = [d.date() for d in df.index.to_pydatetime() if d.date() <= today]
            if past:
                out["days_since_earnings"] = (today - max(past)).days
    except Exception:  # noqa: BLE001
        pass
    return out


def build_calendar_blockers(days_to_earnings: Optional[int]) -> list:
    """TICKER-SPECIFIC calendar blocker: earnings proximity gates the SHORT
    horizon (per-card). FOMC/CPI are market-wide and handled by the banner."""
    blockers: list = []
    if (days_to_earnings is not None
            and days_to_earnings <= CALENDAR_CONFIG["earnings_window_days"]):
        blockers.append(Blocker(
            "earnings_within_window", "caution",
            f"Earnings in {days_to_earnings}d", f"{days_to_earnings}天后财报",
            horizons=["short"]))
    return blockers


# ===========================================================================
# Five-state status mapping (single source: order_advisor PriceLevelResult)
# ===========================================================================

# Genuine overextension / risk-failure blocker codes -> "Avoid Chasing".
# NOTE: a not-yet-confirmed entry TRIGGER (EMA trend, volume) is NOT here.
_CRITICAL_GATE_CODES = {"valuation_high", "overextended", "risk_overlay_failed"}

# Fix 3 — classify the entry engine's own ``missing_conditions`` into FUNDAMENTAL
# (valuation / EPS / quality) vs TRIGGER-PENDING (trend / volume / price). A
# fundamental engine block routes to the Avoid Chasing path even when the
# candidate carries NO ranker blockers (legacy hand-off); a trigger block routes
# to Wait for Breakout.
#
# PRIMARY: the entry engine's structured registry (lib.order_advisor
# MISSING_CONDITION_TEXT_TO_CATEGORY) — the authoritative category for every
# string the engine actually emits, so an engine wording change can never
# silently misroute. FALLBACK: case-insensitive substring markers, used ONLY for
# legacy / unregistered conditions (e.g. old pending signals in session_state).
# Fundamental wins on collision.
ENGINE_FUNDAMENTAL_MARKERS = (
    "eps", "valuation", "estimate", "quality", "fundamental",  # English
    "估值", "下修", "基本面", "质量",                              # Chinese
)
ENGINE_TRIGGER_MARKERS = (
    "ema", "sma", "rsi", "volume", "candlestick", "price", "trend", "breakout",
    "支撑", "突破", "均线", "量能", "价格", "看跌",
)

_ENGINE_CATEGORY_MAP: Optional[dict] = None


def _engine_category(text: str) -> Optional[str]:
    """Registry category for an emitted condition string, or None if unregistered.
    The registry is imported lazily and cached on first success (fail-soft)."""
    global _ENGINE_CATEGORY_MAP
    if _ENGINE_CATEGORY_MAP is None:
        try:
            from lib.order_advisor import MISSING_CONDITION_TEXT_TO_CATEGORY as _m

            _ENGINE_CATEGORY_MAP = dict(_m)
        except Exception:  # noqa: BLE001 — registry unavailable -> pure fallback
            return None
    return _ENGINE_CATEGORY_MAP.get(str(text))


def engine_block_is_fundamental(missing_conditions) -> bool:
    """True if any engine missing_condition names a fundamental block (Fix 3).

    Registry category first; substring fallback only for unregistered strings.
    Fundamental wins on collision."""
    for cond in (missing_conditions or []):
        category = _engine_category(cond)
        if category == "fundamental":
            return True
        if category == "trigger":
            continue  # registered as a trigger; not fundamental
        # unregistered (legacy / old session_state) -> substring fallback
        if any(m in str(cond).lower() for m in ENGINE_FUNDAMENTAL_MARKERS):
            return True
    return False


def _bget(blocker, field_name, default=None):
    """Read a field from a Blocker dataclass OR a plain dict (UI hand-off)."""
    if isinstance(blocker, dict):
        v = blocker.get(field_name, default)
    else:
        v = getattr(blocker, field_name, default)
    return default if v is None else v


def derive_status(levels, candidate, blockers: list, horizon: str = "mid",
                  fragility_gate_horizons: tuple = ()) -> str:
    # ``fragility_gate_horizons`` (Phase 7B Task 3, tighten-only): horizons the
    # market-internals fragility level GATES. When ``horizon`` is gated, an in-zone
    # "Actionable Now" degrades to a wait (Research Required) — mirroring the
    # calendar gate. It NEVER relaxes a status and NEVER touches the regime.
    """Map entry-engine outputs + candidate + blockers to a five-state status.

    Revised semantics (fix round, Task 1):
      * **Avoid Chasing is RESERVED** for genuine overextension and risk-overlay
        failures — never assigned merely because an entry trigger/trend gate is
        not yet confirmed.
      * A not-yet-confirmed gate (trend/volume/breakout trigger pending) →
        **Wait for Breakout** (the card also surfaces the engine's next_trigger).
      * ``below_zone`` is **horizon-aware**: SHORT/MID below a support/SMA zone is
        breakdown territory and LONG below a valuation band is "cheaper than the
        value zone" — both → **Research Required** (never a bullish breakout,
        never Avoid Chasing merely for being cheap). ``wait`` aligns with this.

    ``levels`` is a ``PriceLevelResult`` (or a duck-typed stand-in in tests).
    """
    es = str(getattr(levels, "entry_status", "wait") or "wait")
    risk_ok = bool(getattr(levels, "risk_overlay_passed", True))
    val_conf = str(getattr(levels, "valuation_confidence", "low") or "low").lower()
    ctype = str(_g(candidate, "candidate_type", "FUNNEL") or "FUNNEL").upper()
    eps = str(_g(candidate, "eps_revision_direction", "unknown") or "unknown").lower()

    has_critical = any(_bget(b, "severity", "") == "critical" for b in blockers)
    has_hard_gate = any(_bget(b, "code", "") in _CRITICAL_GATE_CODES for b in blockers)
    # A genuine fundamental "do not buy" gate: deteriorating EPS, a critical
    # ranker valuation/overextension blocker, OR the ENGINE's own missing_condition
    # naming a fundamental block (Fix 3 — works even with no ranker blockers).
    # NOT a trend/volume trigger.
    engine_fundamental = engine_block_is_fundamental(
        getattr(levels, "missing_conditions", []) or [])
    fundamental_gate = ((eps == "deteriorating") or has_critical or has_hard_gate
                        or engine_fundamental)
    cal_blocks_horizon = any(
        _bget(b, "code", "") == "earnings_within_window"
        and (not _bget(b, "horizons", []) or horizon in _bget(b, "horizons", []))
        for b in blockers
    )

    # 1 — genuine risk-overlay failure → Avoid Chasing (reserved)
    if not risk_ok:
        return STATUS_AVOID

    # 2 — extended above the zone: Avoid only when a critical blocker confirms
    #     overextension; otherwise it is a quality name to wait on.
    #     INTENDED PRECEDENCE: a price-based overextension verdict (Avoid /
    #     Pullback) is evaluated BEFORE provenance-based Research-Required
    #     (ALT_SIGNAL) below — the more protective price warning wins. So
    #     ALT_SIGNAL + above_zone + critical -> Avoid Chasing (pinned by a test).
    if es == "above_zone":
        return STATUS_AVOID if (has_critical or has_hard_gate) else STATUS_PULLBACK

    # 3 — unconfirmed signal / low confidence → Research Required
    if ctype == "ALT_SIGNAL":
        return STATUS_RESEARCH
    if horizon == "long" and val_conf == "low":
        return STATUS_RESEARCH

    # 4 — below the zone is horizon-aware; never a bullish breakout, never
    #     Avoid-for-cheap. ``wait`` shares the stabilization semantics.
    if es in ("below_zone", "wait"):
        return STATUS_RESEARCH

    # 5 — blocked: a genuine fundamental gate is Avoid; a pending entry trigger
    #     (trend/volume not yet confirmed) is Wait for Breakout.
    if es == "blocked":
        return STATUS_AVOID if fundamental_gate else STATUS_BREAKOUT

    # 6 / 7 — in zone
    if es == "in_zone":
        if fundamental_gate:
            return STATUS_AVOID
        if cal_blocks_horizon:
            return STATUS_RESEARCH
        # Tighten-only: deteriorating market internals gate the SHORT in-zone
        # actionable into a wait (never relaxes anything else).
        if horizon in (fragility_gate_horizons or ()):
            return STATUS_RESEARCH
        return STATUS_ACTIONABLE

    return STATUS_RESEARCH


def status_next_trigger(levels, horizon: str, status: str) -> tuple:
    """Surface (next_trigger_text, status_reason_code) for a card.

    Reuses the engine's own ``next_trigger`` wording for Wait-for-Breakout, and
    the engine's wait-for-stabilization semantics for below-zone Research states
    (horizon-aware: a LONG name below its valuation band is "below the value
    zone", not a breakdown).
    """
    es = str(getattr(levels, "entry_status", "") or "")
    nt = str(getattr(levels, "next_trigger", "") or "")
    if status == STATUS_BREAKOUT:
        text = nt or "Entry trigger not yet confirmed"
        return text, ReasonCode("trigger_pending", text, "入场触发条件尚未确认")
    if status == STATUS_RESEARCH and es in ("below_zone", "wait"):
        if horizon == "long":
            rc = ReasonCode("below_value_zone",
                            "Below the value zone — verify why before buying",
                            "低于估值区间，买入前需核实原因")
        else:
            rc = ReasonCode("stabilization_needed",
                            "Price below the entry zone — needs to stabilize",
                            "价格跌破入场区间，需先企稳")
        return (nt or rc.text_en), rc
    return nt, None


# ===========================================================================
# Theme membership
# ===========================================================================

def _theme_index(themes) -> tuple:
    """Build (ticker->theme_key, theme_key->ThemeMomentumResult-ish) from
    compute_all_themes() output. Fail-closed -> ({}, {})."""
    by_key: dict = {}
    ticker_theme: dict = {}
    if not themes:
        # Fall back to the static THEME_BASKETS membership (no momentum).
        try:
            from lib.theme_baskets import THEME_BASKETS

            for key, cfg in THEME_BASKETS.items():
                for tk in cfg.get("constituents", []):
                    ticker_theme.setdefault(str(tk).upper(), key)
        except Exception:  # noqa: BLE001
            pass
        return ticker_theme, by_key
    for th in themes:
        key = getattr(th, "theme_key", None) or (th.get("theme_key") if isinstance(th, dict) else None)
        if not key:
            continue
        by_key[key] = th
        consts = (getattr(th, "constituents", None)
                  or (th.get("constituents") if isinstance(th, dict) else None) or [])
        for tk in consts:
            ticker_theme.setdefault(str(tk).upper(), key)
    return ticker_theme, by_key


def _theme_for(ticker: str, candidate, ticker_theme: dict, by_key: dict) -> tuple:
    """Resolve (theme_key, momentum, label_en, label_zh) for a ticker."""
    tk = str(ticker).upper()
    key = ticker_theme.get(tk)
    if not key:
        # Fall back to the candidate's own narrative theme tag if it matches.
        tags = _g(candidate, "narrative_theme_tags", []) or []
        for tag in tags:
            if tag in by_key:
                key = tag
                break
    if not key:
        return None, 0.0, "", ""
    th = by_key.get(key)
    mom = _f(getattr(th, "momentum_score", 0.0) if th is not None else 0.0)
    label_en = (getattr(th, "label_en", "") if th is not None else "") or key
    label_zh = (getattr(th, "label_zh", "") if th is not None else "") or key
    return key, mom, label_en, label_zh


# ===========================================================================
# Main ranking entry point
# ===========================================================================

def rank_opportunities(candidates, *, macro_regime: str = "unknown",
                       horizon_bias: Optional[dict] = None,
                       themes=None, rs_map: Optional[dict] = None,
                       earnings_map: Optional[dict] = None,
                       earnings_since_map: Optional[dict] = None,
                       cpi_date: Optional[str] = None,
                       top_n: Optional[int] = None,
                       sort_horizon: str = "best",
                       price_levels_fn: Optional[Callable] = None,
                       earnings_fn: Optional[Callable] = None,
                       anchor_cache: Optional[dict] = None,
                       anchor_staleness_days: Optional[int] = None,
                       fragility_level: str = "normal",
                       today: Optional[date] = None) -> list:
    """Rank candidates into :class:`OpportunityCard` objects (no LLM, no numbers).

    Phase 1 (all candidates): three horizon scores + grades + setup + RS +
    ticker-specific rule blockers + reason codes — **no entry-engine call and no
    per-ticker network fetch** (RS is read from ``rs_map``; a ticker missing from
    it degrades to a neutral RS component and ``rs_degraded=True``). Phase 2 (top
    N, default ``CALENDAR_CONFIG['top_n_enrich']``): one ``price_levels_fn`` call
    + earnings lookup per ticker → status, next_trigger, entry zone, earnings
    blocker, and setup refinement from actual earnings dates.

    Deterministic ordering: cards are sorted by score descending, then ticker
    ascending, so identical inputs always produce identical output (Codex #3).

    Injectables (offline tests / determinism): ``rs_map`` (ticker->RS), ``themes``
    (compute_all_themes output), ``earnings_map`` (ticker->days_to_earnings),
    ``earnings_since_map`` (ticker->days_since_last_earnings), ``cpi_date``,
    ``price_levels_fn`` (default ``order_advisor.compute_price_levels``),
    ``earnings_fn`` (default ``data_fetcher.get_earnings_calendar``), ``today``.

    ``anchor_cache`` (Phase "Valuation stop-the-bleed"): a ``{ticker: entry}`` map
    of cached valuation anchors (see ``lib.anchor_cache``). During top-N
    enrichment a FRESH entry (within ``anchor_staleness_days``, default
    ``lib.anchor_cache.DEFAULT_STALENESS_DAYS``) is handed to ``price_levels_fn``
    so the LONG status can differentiate (in/above/below the value band) instead
    of collapsing to Research Required. Read-only — no network, no disk write
    here. ``None`` (the default) disables cache enrichment (prior behavior).
    """
    candidates = list(candidates or [])
    top_n = CALENDAR_CONFIG["top_n_enrich"] if top_n is None else int(top_n)
    today = today or date.today()
    # Reference "now" for cache staleness (deterministic when ``today`` is given).
    _anchor_now = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    _anchor_cache = anchor_cache if isinstance(anchor_cache, dict) else {}
    ticker_theme, by_key = _theme_index(themes)
    # Phase 7B Task 3 — tighten-only: which horizons the fragility level gates.
    try:
        from lib import market_internals as _mi
        _gate_horizons = _mi.gated_horizons(fragility_level)
        _internals_reason = _mi.internals_reason()
    except Exception:  # noqa: BLE001 — fail-closed; no gating
        _gate_horizons = ()
        _internals_reason = {"code": "internals_deteriorating", "en": "", "zh": ""}
    days_fomc = days_to_next_fomc(today)
    days_cpi = days_to_next_cpi(cpi_date, today) if cpi_date else None

    # ---- Phase 1: score every candidate (NETWORK-FREE — no per-ticker fetch) ----
    cards: list = []
    for c in candidates:
        ticker = str(_g(c, "ticker", "") or "").upper().strip()
        if not ticker:
            continue
        theme_key, theme_mom, label_en, label_zh = _theme_for(ticker, c, ticker_theme, by_key)
        _th_obj = by_key.get(theme_key) if theme_key else None
        theme_stage = str(getattr(_th_obj, "stage", "") or "")
        theme_stage_confirmed = bool(getattr(_th_obj, "stage_confirmed", False))
        rs = (rs_map or {}).get(ticker)
        # Degraded when there is no cached price history (RS missing) OR the RS
        # was built from a fixture/empty frame (cache-only miss).
        rs_source = (rs.get("data_source") if isinstance(rs, dict)
                     else getattr(rs, "data_source", None)) if rs is not None else None
        rs_degraded = rs is None or rs_source == "fixture"
        # rs_stale (data-vintage round 2): a SILENT stale cache-hit — the RS frame's
        # last date lagged the benchmark vintage (distinct from rs_degraded's miss).
        rs_stale = bool((rs.get("rs_stale") if isinstance(rs, dict)
                         else getattr(rs, "rs_stale", False)) if rs is not None else False)
        rs_comp = _RS_NEUTRAL
        if rs is not None and not rs_degraded:
            rs_comp = (rs.get("rs_composite", _RS_NEUTRAL) if isinstance(rs, dict)
                       else getattr(rs, "rs_composite", _RS_NEUTRAL))
        rule_blockers = build_rule_blockers(c, theme_mom, has_theme=bool(theme_key))
        penalty = _penalty_total(rule_blockers)
        # Each horizon consumes its OWN-window RS composite (7B Task 1); a missing
        # per-horizon value falls back to ``rs_comp`` (legacy/degraded behavior).
        rs_for_h = None if rs_degraded else rs
        s_short = score_horizon(c, "short", theme_mom,
                                _horizon_rs_comp(rs_for_h, "short", rs_comp), penalty)
        s_mid = score_horizon(c, "mid", theme_mom,
                              _horizon_rs_comp(rs_for_h, "mid", rs_comp), penalty)
        s_long = score_horizon(c, "long", theme_mom,
                               _horizon_rs_comp(rs_for_h, "long", rs_comp), penalty)
        setup, pullback = classify_setup(c, rs if rs is not None else {}, theme_mom)
        why_now, why_matters = build_reason_codes(
            c, rs if rs is not None else {}, theme_mom, pullback=pullback)
        card = OpportunityCard(
            ticker=ticker,
            theme=theme_key,
            theme_label_en=label_en,
            theme_label_zh=label_zh,
            theme_momentum=round(theme_mom, 4),
            theme_stage=theme_stage,
            theme_stage_confirmed=theme_stage_confirmed,
            short_score=s_short, mid_score=s_mid, long_score=s_long,
            short_grade=_grade(s_short), mid_grade=_grade(s_mid), long_grade=_grade(s_long),
            rs=(rs.to_dict() if hasattr(rs, "to_dict") else (rs or {})),
            rs_degraded=rs_degraded,
            rs_stale=rs_stale,
            setup=setup, pullback_to_support=pullback,
            blockers=list(rule_blockers),
            why_now=why_now, why_it_matters=why_matters,
            days_to_fomc=days_fomc, days_to_cpi=days_cpi,
            signal_strength=str(_g(c, "signal_strength", "none")),
            candidate_type=str(_g(c, "candidate_type", "FUNNEL")),
        )
        card._candidate = c  # transient handle for Phase-2 enrichment
        cards.append(card)

    # ---- deterministic rank: score desc, then ticker asc (stable tie-break) ----
    def _rank_score(card: OpportunityCard) -> float:
        if sort_horizon in ("short", "mid", "long"):
            return getattr(card, f"{sort_horizon}_score")
        return max(card.short_score, card.mid_score, card.long_score)

    cards.sort(key=lambda card: (-_rank_score(card), card.ticker))

    # ---- Phase 2: enrich the top N only ----
    plf = price_levels_fn
    if plf is None:
        try:
            from lib.order_advisor import compute_price_levels as plf  # type: ignore
        except Exception:  # noqa: BLE001
            plf = None
    efn = earnings_fn
    if efn is None and earnings_map is None and earnings_since_map is None:
        efn = default_earnings_timing

    for card in cards[:top_n]:
        c = getattr(card, "_candidate", None)
        dominant = max((("short", card.short_score), ("mid", card.mid_score),
                        ("long", card.long_score)), key=lambda kv: kv[1])[0]
        # earnings timing (per-ticker; top-N only) — actual dates, not inference
        d2e = (earnings_map or {}).get(card.ticker) if earnings_map is not None else None
        d_since = (earnings_since_map or {}).get(card.ticker) if earnings_since_map is not None else None
        if d2e is None and d_since is None and efn is not None:
            try:
                cal = efn(card.ticker) or {}
                d2e = cal.get("days_to_earnings")
                d_since = cal.get("days_since_earnings")
            except Exception:  # noqa: BLE001
                d2e, d_since = None, None
        card.days_to_earnings = d2e
        card.days_since_earnings = d_since
        card.blockers = list(card.blockers) + build_calendar_blockers(d2e)
        # refine the setup with the ACTUAL earnings recency (bounded window)
        if d_since is not None:
            card.setup, card.pullback_to_support = classify_setup(
                c, card.rs, card.theme_momentum, days_since_earnings=d_since)
        # PER-HORIZON status (Fix round 2): derive the entry-engine levels and
        # status for EACH horizon so the Cockpit selector shows the correct status
        # in every view. Deterministic local math over cached OHLCV (≤ 3× per
        # top-N ticker; still zero per-ticker network fetch). The earnings/FOMC
        # gate is horizon-parameterized in derive_status, so the displayed-horizon
        # behavior is automatic, not special-cased.
        eps_dir = str(_g(c, "eps_revision_direction", "unknown") or "unknown")
        val_pct = _f(_g(c, "valuation_percentile", 0.5), 0.5)
        eps_deteriorating = (eps_dir.lower() == "deteriorating")
        # Resolve a FRESH cached valuation anchor (read-only, network-free) so the
        # LONG status can differentiate instead of collapsing to Research Required.
        # Stale / missing → no band passed → prior behavior. The age is recorded
        # on the card (and snapshot) for staleness-impact review.
        _anchor_entry = _anchor_cache.get(card.ticker) if _anchor_cache else None
        _anchor_band = None
        if _anchor_entry is not None and _anchor_is_fresh(
                _anchor_entry, anchor_staleness_days, now=_anchor_now):
            _anchor_band = _anchor_entry
            _age = _anchor_age_days(_anchor_entry, now=_anchor_now)
            card.anchor_age_days = (round(_age, 2) if _age is not None else None)
        for hz in ("short", "mid", "long"):
            lv = None
            if plf is not None:
                try:
                    lv = plf(card.ticker, None, thesis_status="intact", horizon=hz,
                             eps_revision_direction=eps_dir, valuation_percentile=val_pct,
                             app_fair_value=_anchor_band)
                except TypeError:
                    # An injected price_levels_fn without the app_fair_value kwarg
                    # (older signature) — retry without it (no cache enrichment).
                    try:
                        lv = plf(card.ticker, None, thesis_status="intact", horizon=hz,
                                 eps_revision_direction=eps_dir, valuation_percentile=val_pct)
                    except Exception:  # noqa: BLE001 — fail-closed; this horizon null
                        lv = None
                except Exception:  # noqa: BLE001 — fail-closed; this horizon stays null
                    lv = None
            # Per-horizon why_now: the RS line follows THIS horizon's window
            # (SHORT=5D / MID=1M / LONG=6M). Built for EVERY horizon — even when the
            # entry engine produced no levels for it (``lv`` None) — so the selected
            # view never falls back to another horizon's RS line (7B Task 1 fix). The
            # ``levels`` arg only adds the in-zone line; the window is horizon-driven.
            card.why_now_by_horizon[hz] = build_reason_codes(
                c, card.rs, card.theme_momentum, lv,
                pullback=card.pullback_to_support, days_since_earnings=d_since,
                horizon=hz)[0]
            if lv is None:
                continue
            st_hz = derive_status(lv, c, card.blockers, hz,
                                  fragility_gate_horizons=_gate_horizons)
            card.status_by_horizon[hz] = st_hz
            nt_hz, reason_hz = status_next_trigger(lv, hz, st_hz)
            card.next_trigger_by_horizon[hz] = nt_hz
            if reason_hz is not None:
                card.status_reason_by_horizon[hz] = reason_hz.to_dict()
            # If the fragility gate (and only it) caused this horizon to tighten,
            # surface the internals_deteriorating reason (overrides the generic one).
            if hz in _gate_horizons and derive_status(lv, c, card.blockers, hz) != st_hz:
                card.status_reason_by_horizon[hz] = dict(_internals_reason)
            if hz == dominant:
                # convenience single-value fields + entry-zone numbers from the
                # dominant horizon (Trading Desk single-value handoff).
                card.entry_zone_low = getattr(lv, "entry_zone_low", None)
                card.entry_zone_high = getattr(lv, "entry_zone_high", None)
                card.stop_loss = getattr(lv, "stop_loss", None)
                card.target_price = getattr(lv, "target_price", None)
                card.risk_reward_ratio = _f(getattr(lv, "risk_reward_ratio", 0.0))
                card.position_size_pct = _f(getattr(lv, "position_size_pct", 0.0))
                card.status = st_hz
                card.next_trigger = nt_hz
                # Invariant: a genuine Avoid-Chasing name is not a high-quality
                # pullback — drop the pullback flag so the two never co-occur.
                if st_hz == STATUS_AVOID:
                    card.pullback_to_support = False
                # refresh why_now with entry geometry. The status reason
                # (trigger_pending / stabilization_needed / below_value_zone) is
                # NOT injected here (Fix 4) — it duplicates the next_trigger line;
                # it lives in status_reason_by_horizon instead.
                wn, _wm = build_reason_codes(
                    c, card.rs, card.theme_momentum, lv,
                    pullback=card.pullback_to_support, days_since_earnings=d_since,
                    horizon=dominant)
                card.why_now = wn
        card.enriched = True

    # ---- anchor snapshot block (Anchor Intel v2.3 U2): stamp EVERY card from the
    # SAME read-only anchor_cache (network-free dict lookups) using the IDENTICAL
    # freshness decision the top-N LONG status used, so the snapshot's anchor block
    # is single-vintage with the status it accompanies. No fresh entry → an honest
    # ``anchor_not_cached`` state, never a fabricated value.
    for card in cards:
        _e = _anchor_cache.get(card.ticker) if _anchor_cache else None
        _fresh = bool(_e is not None and _anchor_is_fresh(
            _e, anchor_staleness_days, now=_anchor_now))
        card.anchor_snapshot = _anchor_snapshot_block(_e, _fresh)

    # ---- reason-code display hygiene: demote over-common codes (Task 2) ----
    filter_common_reasons(cards, "why_now")
    filter_common_reasons(cards, "why_it_matters")

    # NOTE: the concentration marker is computed at DISPLAY time (view-local),
    # over the per-horizon-sorted list shown to the user — see
    # ``concentration_refs()`` and the Cockpit panel. It is NOT stored here.

    for card in cards:
        if hasattr(card, "_candidate"):
            delattr(card, "_candidate")
    return cards


def concentration_refs(cards: list) -> dict:
    """Display-time concentration map over an ALREADY-SORTED list (Task 4).

    Returns ``{ticker: "#K"}`` where #K is the 1-based position of the FIRST card
    in that theme within the given (displayed) order — so "#K" always points to a
    card visible above. The first card of each theme is omitted (no marker).
    """
    first_pos: dict = {}
    refs: dict = {}
    for pos, card in enumerate(cards, start=1):
        theme = card.get("theme") if isinstance(card, dict) else getattr(card, "theme", None)
        ticker = card.get("ticker") if isinstance(card, dict) else getattr(card, "ticker", "")
        if not theme:
            continue
        if theme in first_pos:
            refs[ticker] = f"#{first_pos[theme]}"
        else:
            first_pos[theme] = pos
    return refs


# ===========================================================================
# Optional LLM polish (language only; separate from the ranking path)
# ===========================================================================

def polish_opportunity_cards(cards: list, lang: str = "en", limit: int = 5) -> list:
    """OPTIONAL: convert the raw reason codes of the top ``limit`` cards to natural
    bilingual sentences via a single LLM call. Never alters judgments or numbers;
    degrades silently to raw-code display on any failure / missing key.

    This is **not** called by :func:`rank_opportunities` — the ranking path makes
    no LLM call. The UI may call this on the cards it is about to display.
    """
    if not cards:
        return cards
    try:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return cards
        from lib.llm_orchestrator import polish_reason_codes  # optional helper
    except Exception:  # noqa: BLE001 — no orchestrator hook -> raw codes
        return cards
    try:
        payload = []
        for card in cards[:limit]:
            payload.append({
                "ticker": card.ticker,
                "why_now": [r.code for r in card.why_now],
                "why_it_matters": [r.code for r in card.why_it_matters],
            })
        polished = polish_reason_codes(payload, lang=lang) or {}
        for card in cards[:limit]:
            p = polished.get(card.ticker) or {}
            card.why_now_polished_en = p.get("why_now_en", "") or card.why_now_polished_en
            card.why_now_polished_zh = p.get("why_now_zh", "") or card.why_now_polished_zh
    except Exception:  # noqa: BLE001 — silent degrade
        return cards
    return cards


# ===========================================================================
# Daily snapshot persistence (Task 4)
# ===========================================================================

def _snapshot_path(date_str: str, base_dir: Optional[Path] = None) -> Path:
    base = Path(base_dir) if base_dir else SNAPSHOT_DIR
    return base / f"opportunities_{date_str.replace('-', '')}.jsonl"


def _card_snapshot_record(card: OpportunityCard, date_str: str,
                          macro_regime: str) -> dict:
    # Reason codes are stored RAW (Task 2); display filtering is view-only. The
    # concentration marker is intentionally NOT stored — it is view-local; the
    # ``theme`` field carries the grouping info needed to rebuild it.
    return {
        "date": date_str,
        "ticker": card.ticker,
        "theme": card.theme,
        "theme_momentum": card.theme_momentum,
        "theme_stage": card.theme_stage,
        "theme_stage_confirmed": card.theme_stage_confirmed,
        "short_score": card.short_score,
        "mid_score": card.mid_score,
        "long_score": card.long_score,
        "short_grade": card.short_grade,
        "mid_grade": card.mid_grade,
        "long_grade": card.long_grade,
        "rs": card.rs,
        "rs_degraded": card.rs_degraded,
        "rs_stale": card.rs_stale,
        "setup": card.setup,
        "pullback_to_support": card.pullback_to_support,
        # Per-horizon status map (Fix round 2) replaces the single status field;
        # values are null outside the top N. ``status`` (dominant) retained for
        # convenience / backward-compatible readers.
        "status_by_horizon": dict(card.status_by_horizon),
        "next_trigger_by_horizon": dict(card.next_trigger_by_horizon),
        "status": card.status,
        # Cache-anchor staleness (stop-bleed): age in days of the cached anchor
        # that drove the LONG status, or null when none was used.
        "anchor_age_days": card.anchor_age_days,
        # Structured anchor block (Anchor Intel v2.3 U2): single-vintage with the
        # LONG status above; {company_type, fair_value_mid, analyst_pool, …} for a
        # fresh cached anchor, else {"state": "anchor_not_cached"}.
        "anchor": card.anchor_snapshot or {"state": ANCHOR_NOT_CACHED},
        "blockers": [b.to_dict() if hasattr(b, "to_dict") else b for b in card.blockers],
        "why_now": [r.code if hasattr(r, "code") else r for r in card.why_now],
        "why_it_matters": [r.code if hasattr(r, "code") else r for r in card.why_it_matters],
        "days_to_earnings": card.days_to_earnings,
        "days_since_earnings": card.days_since_earnings,
        "days_to_fomc": card.days_to_fomc,
        "days_to_cpi": card.days_to_cpi,
        "signal_strength": card.signal_strength,
        "macro_regime": macro_regime,
    }


def write_daily_snapshot(cards: list, *, themes=None, macro_regime: str = "unknown",
                         horizon_bias: Optional[dict] = None,
                         fragility: Optional[dict] = None,
                         clock_suspect: bool = False,
                         clock_suspect_reason: str = "",
                         date_str: Optional[str] = None,
                         refreshed_at: Optional[str] = None,
                         base_dir: Optional[Path] = None) -> str:
    """Persist ALL ranked cards for the day (Task 4). Same-day refreshes
    **overwrite** the day's file, so only the latest snapshot is kept.

    Line 1 is a ``{"_meta": true, ...}`` header (date, refreshed_at, regime,
    horizon_bias, per-theme momentum map); each subsequent line is one ticker
    record. Returns the file path written. Fail-closed -> "".
    """
    try:
        date_str = date_str or date.today().strftime("%Y-%m-%d")
        refreshed_at = refreshed_at or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        _ti, by_key = _theme_index(themes)
        theme_mom_map = {
            k: round(_f(getattr(v, "momentum_score", 0.0)), 4) for k, v in by_key.items()
        }
        path = _snapshot_path(date_str, base_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "_meta": True,
            "date": date_str,
            "refreshed_at": refreshed_at,
            "macro_regime": macro_regime,
            "horizon_bias": horizon_bias or {},
            "theme_momentum": theme_mom_map,
            "n_candidates": len(cards or []),
            # WSL clock-drift defense (polish round): the refresh still writes, but
            # a suspect system clock is flagged so mis-dated snapshots are visible.
            "clock_suspect": bool(clock_suspect),
            "clock_suspect_reason": clock_suspect_reason or "",
        }
        # Phase 7B Task 3 — fragility level + every component value live in the
        # _meta header (the snapshot is the memory; hysteresis reads it back).
        if fragility:
            meta.update(fragility)
        lines = [json.dumps(meta, ensure_ascii=False)]
        for card in (cards or []):
            lines.append(json.dumps(
                _card_snapshot_record(card, date_str, macro_regime),
                ensure_ascii=False))
        # Atomic write: temp file in the same dir + os.replace (Codex #6). A
        # partial/failed write never corrupts or truncates the prior day's file.
        tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, path)
        return str(path)
    except Exception:  # noqa: BLE001 — snapshot is best-effort, never fatal
        try:
            _t = locals().get("tmp")
            if _t is not None and _t.exists():
                _t.unlink()
        except Exception:  # noqa: BLE001
            pass
        return ""


def load_ticker_series(ticker: str, base_dir: Optional[Path] = None) -> list:
    """Reconstruct a per-ticker time series across all daily snapshot files.

    Returns the ticker's record for each day it appears, sorted by date.
    """
    base = Path(base_dir) if base_dir else SNAPSHOT_DIR
    tk = str(ticker).upper().strip()
    out: list = []
    if not base.exists():
        return out
    for fp in sorted(base.glob("opportunities_*.jsonl")):
        try:
            for line in fp.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("_meta"):
                    continue
                if str(rec.get("ticker", "")).upper() == tk:
                    out.append(rec)
        except Exception:  # noqa: BLE001 — skip an unreadable day
            continue
    out.sort(key=lambda r: r.get("date", ""))
    return out
