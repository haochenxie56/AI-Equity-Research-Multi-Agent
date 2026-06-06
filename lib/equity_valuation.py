"""lib/equity_valuation.py — Phase 6C-B app-computed fair value (free sources only).

Standalone fair-value computation module used by the Equity Research page
(``pages/4_Equity.py``) and the Investment Cockpit (``pages/7_Investment_Cockpit.py``).
It blends THREE independent, FREE estimates into a low / mid / high fair-value
range that the Trading Desk (``lib/order_advisor.py``) consumes as its primary
valuation anchor when present:

* **DCF** — a deliberately simplified single-stage Gordon-growth model on a
  per-share trailing-twelve-month free-cash-flow base (documented assumptions:
  ``WACC = 10%``, ``growth_rate = min(earningsGrowth | revenueGrowth | 0.05, 0.15)``).
* **Relative** — ``sector_median_pe × trailing_eps`` (a re-rating to the sector
  median multiple).
* **Analyst** — ``targetMedianPrice`` (preferred) else ``targetMeanPrice``.

Guardrails (Phase 6C-B): yfinance only (no paid API, no key); fail-closed with a
``data_source="fixture"`` fallback that degrades to ``current_price``-anchored
band; no broker / order / execution; no DB / vector store; produces no
``approved_for_execution`` field. The fair value is a deterministic,
code-computed reference — the LLM never produces these numbers (it only debates
them; see :func:`lib.llm_orchestrator.analyze_equity_fair_value_debate`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

_log = logging.getLogger("equity_valuation")

# Documented DCF assumptions (Phase 6C-B). Gordon growth requires growth < WACC;
# the growth cap (15%) is above WACC (10%), so when the resolved growth_rate is
# >= WACC the DCF is treated as not computable (dcf_value = None).
_WACC = 0.10            # fixed discount-rate assumption, documented inline
_GROWTH_CAP = 0.15      # cap the growth_rate at 15%
_GROWTH_DEFAULT = 0.05  # fall back to 5% when no growth field is available
_DCF_YEARS = 5          # single-stage horizon exponent

# Mid-value blend weights for the mature_profitable menu (only present sources
# contribute; weights renormalized over whatever is available). These are the
# canonical source-of-truth weights; they are mirrored into ``_ANCHOR_FACTORS``
# (the routed per-anchor factor table) for the dcf / relative_pe / analyst keys so
# the default path stays byte-identical.
_W_DCF = 0.35
_W_RELATIVE = 0.35
_W_ANALYST = 0.30

# Anchor consistency gate (Phase "Valuation stop-the-bleed", Task 1). When the
# spread across the available raw anchors (DCF / relative / analyst, after unit
# sanity) exceeds this max/min ratio they are deemed IRRECONCILABLE and are NOT
# blended into a precise band (averaging garbage with signal — e.g. a $3.23
# relative vs a $112.50 analyst target → a meaningless $53.66 mid). Configurable.
ANCHOR_DISPERSION_THRESHOLD = 3.0

# Blend-state vocabulary (AppFairValue.blend_state).
_BLEND_OK = "blended"
_BLEND_IRRECONCILABLE = "anchors_irreconcilable"
_BLEND_NONE = "no_anchor"

_LIVE = "live"
_FIXTURE = "fixture"
_CACHE_TTL = 3600  # 1 hour, keyed on (ticker, current_price)

# Hardcoded sector → median trailing P/E map (free, deterministic). yfinance
# ``info["sector"]`` labels are used as keys; an unknown sector falls back to the
# default median. Curated June 2026, broadly consistent with long-run sector
# multiples; intentionally conservative.
SECTOR_MEDIAN_PE: dict[str, float] = {
    "Technology": 28.0,
    "Communication Services": 19.0,
    "Consumer Cyclical": 22.0,
    "Consumer Defensive": 20.0,
    "Healthcare": 18.0,
    "Financial Services": 13.0,
    "Industrials": 19.0,
    "Energy": 12.0,
    "Basic Materials": 15.0,
    "Real Estate": 30.0,
    "Utilities": 17.0,
}
_DEFAULT_MEDIAN_PE = 19.0

# Hardcoded sector → median EV/EBITDA and P/S fallback maps (free, deterministic).
# Used ONLY when growth-matched peer multiples are unavailable on the routed
# EV/EBITDA (project_driven) / EV/S (growth) menus — the honest "sector_fallback"
# basis. Curated June 2026; intentionally conservative.
SECTOR_MEDIAN_EV_EBITDA: dict[str, float] = {
    "Technology": 18.0,
    "Communication Services": 11.0,
    "Consumer Cyclical": 12.0,
    "Consumer Defensive": 13.0,
    "Healthcare": 14.0,
    "Financial Services": 10.0,
    "Industrials": 13.0,
    "Energy": 6.0,
    "Basic Materials": 8.0,
    "Real Estate": 18.0,
    "Utilities": 11.0,
}
_DEFAULT_EV_EBITDA = 12.0

SECTOR_MEDIAN_PS: dict[str, float] = {
    "Technology": 6.0,
    "Communication Services": 3.5,
    "Consumer Cyclical": 1.5,
    "Consumer Defensive": 1.5,
    "Healthcare": 4.0,
    "Financial Services": 3.0,
    "Industrials": 2.0,
    "Energy": 1.2,
    "Basic Materials": 1.5,
    "Real Estate": 6.0,
    "Utilities": 2.5,
}
_DEFAULT_PS = 2.5

# --- Method menus per company type (Valuation Refactor v1, Task 2) -----------
# Each company type routes a different INPUT SET into the blend. ``blend`` lists
# the anchor keys eligible for the blend (only the ones whose value is present
# actually contribute); ``blend_if_present`` (a generic, currently-unused
# mechanism) would add an anchor only when its value exists; ``excluded`` anchors
# are computed-but-not-blended (shown for transparency, flagged with the reason).
# The dispersion gate from stop-the-bleed runs LAST on whatever the menu produced.
# The default (empty / unknown company_type) is mature_profitable, which is
# byte-identical to the prior DCF + relative-PE + analyst behavior.
METHOD_MENUS: dict = {
    "mature_profitable": {
        "blend": ["dcf", "relative_pe", "analyst"],
        "excluded": [],
    },
    "growth_profitable": {
        # forward EV/S vs growth-matched peers (primary) + forward PE (secondary)
        # + analyst; Rule-of-40 modifies the EV/S multiple (see _compute_ev_s).
        "blend": ["ev_s", "relative_pe", "analyst"],
        "excluded": ["dcf"],
    },
    "growth_unprofitable": {
        # forward EV/S vs growth-matched peers + analyst ONLY. PE EXCLUDED (the
        # garbage source) AND DCF EXCLUDED structurally — for loss-making companies
        # DCF output is unreliable even when FCF is momentarily positive, and a
        # user DCF override must not bypass the menu either (review fix D2).
        "blend": ["ev_s", "analyst"],
        "excluded": ["relative_pe", "dcf"],
    },
    "project_driven": {
        # forward EV/EBITDA + analyst; backlog coverage is the right metric but is
        # unavailable on free sources (backlog_note). PE / DCF excluded.
        "blend": ["ev_ebitda", "analyst"],
        "excluded": ["dcf", "relative_pe"],
        "backlog_metric": True,
    },
    "cyclical": {
        # PB/PS band vs the ticker's own ≤4y annual history + analyst; trailing-PE
        # is cycle-distorted (flagged, not blended); DCF excluded.
        "blend": ["pb_ps_band", "analyst"],
        "excluded": ["dcf"],
        "cycle_distorted": ["relative_pe"],
    },
}

# Per-anchor blend factors: (low_factor, mid_weight, high_factor, method_label).
# The mature_profitable trio (dcf / relative_pe / analyst) reproduces the prior
# discount / weight / premium factors EXACTLY so the default path is unchanged.
_ANCHOR_FACTORS: dict = {
    "dcf":         (0.85, _W_DCF, 1.10, "DCF (Gordon growth)"),
    "relative_pe": (0.90, _W_RELATIVE, 1.05, "relative P/E × EPS"),
    "analyst":     (0.80, _W_ANALYST, 1.05, "analyst target"),
    "ev_s":        (0.85, 0.45, 1.10, "forward EV/S (peer P/S proxy, growth-matched)"),
    "ev_ebitda":   (0.85, 0.50, 1.10, "forward EV/EBITDA (peers)"),
    "pb_ps_band":  (0.90, 0.50, 1.10, "PB/PS band (≤4y annual percentile)"),
}

# Display name for each anchor key (kept stable for the cache / UI: the relative
# P/E anchor stays "relative", the price-band anchor "pb_ps").
_ANCHOR_DISPLAY: dict = {
    "dcf": "dcf", "relative_pe": "relative", "analyst": "analyst",
    "ev_s": "ev_s", "ev_ebitda": "ev_ebitda", "pb_ps_band": "pb_ps",
}

# Rule-of-40 (growth_profitable quality modifier): a company whose
# (revenue_growth + fcf_margin) clears 40% gets a premium on its EV/S multiple;
# below 40% a discount. Bounded so it never dominates the anchor.
_RULE_OF_40_TARGET = 0.40
_RULE_OF_40_SENSITIVITY = 0.5   # multiplier swing per 1.0 of (score − 0.40)
_RULE_OF_40_MIN = 0.80
_RULE_OF_40_MAX = 1.25

# --- Cyclical PB/PS history band (review fix D1/I10) -------------------------
# The cyclical menu values the company against its OWN historical multiple range.
# Free yfinance annual fundamentals yield ~4 annual observations, so this is an
# **≤4-year ANNUAL approximation** (NOT a 5-year band) and is labelled as such
# everywhere it surfaces. The percentile levels are a single visible config block:
# the p50 (median) of the historical multiple × the current per-share fundamental
# is the blended anchor; p20 / p80 contextualize the cheap / expensive band.
PB_PS_BAND_PERCENTILES: dict = {"low": 20, "mid": 50, "high": 80}
MIN_CYCLICAL_BAND_OBS = 3   # need >= 3 annual observations to trust the band
CYCLICAL_BAND_MAX_YEARS = 4  # free-tier annual statements yield ~4 observations

# --- Valuation caveat vocabulary (review fix I10) ---------------------------
# Real degradation tokens surfaced in pages/4 and carried on AppFairValue.caveats.
CAVEAT_CYCLICAL_BAND_UNAVAILABLE = "cyclical_band_unavailable"
CAVEAT_SINGLE_ANCHOR_BLEND = "single_anchor_blend"
VALUATION_CAVEATS: tuple = (
    CAVEAT_CYCLICAL_BAND_UNAVAILABLE, CAVEAT_SINGLE_ANCHOR_BLEND,
)


def get_sector_median_pe(sector: Optional[str]) -> float:
    """Return the hardcoded median trailing P/E for ``sector`` (default if unknown)."""
    return SECTOR_MEDIAN_PE.get(sector or "", _DEFAULT_MEDIAN_PE)


def get_sector_median_ev_ebitda(sector: Optional[str]) -> float:
    """Return the hardcoded median EV/EBITDA for ``sector`` (default if unknown)."""
    return SECTOR_MEDIAN_EV_EBITDA.get(sector or "", _DEFAULT_EV_EBITDA)


def get_sector_median_ps(sector: Optional[str]) -> float:
    """Return the hardcoded median P/S for ``sector`` (default if unknown)."""
    return SECTOR_MEDIAN_PS.get(sector or "", _DEFAULT_PS)


@dataclass
class AppFairValue:
    """App-computed fair value for one ticker (deterministic; no LLM).

    All three source estimates (``dcf_value`` / ``relative_value`` /
    ``analyst_target``) are per-share and may be ``None`` when their inputs are
    unavailable. The ``fair_value_low <= fair_value_mid <= fair_value_high``
    invariant always holds. Review-only: no ``approved_for_execution`` field.
    """

    ticker: str = ""
    dcf_value: Optional[float] = None
    relative_value: Optional[float] = None
    analyst_target: Optional[float] = None
    analyst_count: int = 0
    fair_value_low: float = 0.0
    fair_value_mid: float = 0.0
    fair_value_high: float = 0.0
    confidence: str = "low"  # high | medium | low
    upside_pct: float = 0.0
    methodology: str = ""
    computed_at: str = ""
    data_source: str = _FIXTURE  # live | fixture
    dcf_note: str = ""  # DCF source detail, or the reason dcf_value is None
    # --- Anchor consistency gate (Task 1) ---------------------------------
    # "blended" — normal weighted band; "anchors_irreconcilable" — the raw
    # anchors disagreed beyond ANCHOR_DISPERSION_THRESHOLD so NO band was
    # produced (low/mid/high are 0.0, confidence forced low); "no_anchor" — no
    # DCF/relative/analyst input at all (band anchored on current price).
    blend_state: str = _BLEND_OK
    anchor_dispersion: Optional[float] = None  # max/min ratio across raw anchors
    # Side-by-side anchors for honest display when irreconcilable. Each item:
    # {"name": str, "value": float, "basis": str}.
    anchors: list = field(default_factory=list)
    # --- Basis flags (Task 2) ---------------------------------------------
    # relative_basis: "forward" (forwardEps) | "trailing_fallback" (trailingEps).
    # peer_pe_basis: "mixed" when forward EPS is multiplied by a trailing sector
    # median P/E (the hardcoded map is trailing) | "trailing" | "".
    relative_basis: str = ""
    peer_pe_basis: str = ""
    # --- Method router (Valuation Refactor v1) ----------------------------
    # company_type: the detected classification (mature_profitable /
    # growth_profitable / growth_unprofitable / project_driven / cyclical).
    # company_type_confidence: "clear" | "borderline" (borderline routes to the
    # default mature menu). routing_rationale: human-readable why-this-menu.
    # methods_used: the anchor method labels that entered the blend.
    # excluded_anchors: computed-but-not-blended anchors (PE for growth/project,
    # cycle-distorted trailing-PE for cyclical) each with {name, value, basis,
    # flag}. ev_s_value / ev_ebitda_value / pb_ps_value carry the routed extra
    # anchors. peer_basis: "growth_matched" | "sector_fallback" | "".
    # backlog_note: honest note when backlog coverage (the right project_driven
    # metric) is unavailable on free sources.
    company_type: str = ""
    company_type_confidence: str = ""
    routing_rationale: str = ""
    methods_used: list = field(default_factory=list)
    excluded_anchors: list = field(default_factory=list)
    ev_s_value: Optional[float] = None
    ev_ebitda_value: Optional[float] = None
    pb_ps_value: Optional[float] = None
    peer_basis: str = ""
    backlog_note: str = ""
    # caveats: real degradation tokens (see VALUATION_CAVEATS) — e.g.
    # "cyclical_band_unavailable" (history band could not be built) or
    # "single_anchor_blend" (only one anchor entered the blend). Surfaced in pages/4.
    caveats: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------


def _finite_pos(x) -> Optional[float]:
    """Return ``x`` as a positive finite float, else ``None`` (rejects NaN / <= 0)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    xf = float(x)
    if xf != xf or xf <= 0:
        return None
    return xf


def _finite(x) -> Optional[float]:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    xf = float(x)
    return None if xf != xf else xf


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Pure assembler (no I/O) — used directly by tests
# ---------------------------------------------------------------------------


def build_app_fair_value(
    ticker: str,
    current_price: float,
    dcf_value: Optional[float],
    relative_value: Optional[float],
    analyst_target: Optional[float],
    analyst_count: int = 0,
    data_source: str = _FIXTURE,
    dcf_source: str = "",
    dcf_note: str = "",
    relative_basis: str = "",
    peer_pe_basis: str = "",
    *,
    company_type: str = "",
    company_type_confidence: str = "",
    routing_rationale: str = "",
    ev_s_value: Optional[float] = None,
    ev_s_basis: str = "",
    ev_ebitda_value: Optional[float] = None,
    ev_ebitda_basis: str = "",
    pb_ps_value: Optional[float] = None,
    pb_ps_basis: str = "",
    peer_basis: str = "",
    backlog_note: str = "",
    caveats: Optional[list] = None,
) -> AppFairValue:
    """Assemble an :class:`AppFairValue` from the routed anchor set (pure).

    **Method router (Valuation Refactor v1, Task 2):** ``company_type`` selects a
    :data:`METHOD_MENUS` entry that decides which anchors enter the blend. The
    default (``""`` / unknown) is ``mature_profitable`` — DCF + relative-PE +
    analyst with the EXACT prior discount / weight / premium factors, so the
    legacy path is byte-identical. Other types route in EV/S, EV/EBITDA, or a
    PB/PS band and EXCLUDE the inappropriate anchors (e.g. trailing-PE garbage for
    a project-driven company), recording the excluded ones in ``excluded_anchors``
    with the reason (``excluded`` / ``cycle_distorted``) for transparency.

    Always returns a well-formed result with
    ``fair_value_low <= fair_value_mid <= fair_value_high``. When the menu
    produced no usable anchor the band is anchored on ``current_price``
    (0.85 / 1.00 / 1.15), confidence ``low``, ``blend_state="no_anchor"``.

    **Anchor consistency gate (stop-the-bleed, Task 1) runs LAST** on whatever
    the menu produced: the spread across the blended anchors is measured
    (``anchor_dispersion`` = max/min); when they disagree by more than
    :data:`ANCHOR_DISPERSION_THRESHOLD` they are NOT blended — the band collapses
    to ``0.0``, ``confidence`` is forced ``low``, ``blend_state`` is
    ``anchors_irreconcilable``. Routing reduces irreconcilables; the gate still
    catches the rest.
    """
    cp = _finite_pos(current_price) or 0.0
    dcf = _finite_pos(dcf_value)
    rel = _finite_pos(relative_value)
    ana = _finite_pos(analyst_target)
    ev_s = _finite_pos(ev_s_value)
    ev_ebitda = _finite_pos(ev_ebitda_value)
    pb_ps = _finite_pos(pb_ps_value)
    try:
        a_count = int(analyst_count or 0)
    except (TypeError, ValueError):
        a_count = 0

    # Candidate anchors keyed by menu key: (value, display_basis).
    candidates = {
        "dcf": (dcf, (dcf_source or "dcf")),
        "relative_pe": (rel, (relative_basis or "relative")),
        "analyst": (ana, f"analyst (n={a_count})"),
        "ev_s": (ev_s, (ev_s_basis or "EV/S")),
        "ev_ebitda": (ev_ebitda, (ev_ebitda_basis or "EV/EBITDA")),
        "pb_ps_band": (pb_ps, (pb_ps_basis or "PB/PS band")),
    }

    menu_key = company_type if company_type in METHOD_MENUS else "mature_profitable"
    menu = METHOD_MENUS[menu_key]

    # Effective blend keys = menu.blend (+ blend_if_present whose value exists).
    blend_keys = list(menu.get("blend", []))
    for k in menu.get("blend_if_present", []):
        if candidates.get(k, (None, ""))[0] is not None and k not in blend_keys:
            blend_keys.append(k)

    # --- Blended anchor list (present only), in menu order ------------------
    anchors: list = []
    for k in blend_keys:
        v, basis = candidates.get(k, (None, ""))
        if v is None:
            continue
        anchors.append({
            "name": _ANCHOR_DISPLAY.get(k, k),
            "value": round(v, 2),
            "basis": basis,
            "method": _ANCHOR_FACTORS[k][3],
        })
    methods_used = [a["method"] for a in anchors]
    _blend_names = {a["name"] for a in anchors}

    # --- Excluded / flagged anchors (computed but NOT blended) --------------
    excluded_anchors: list = []
    _flagged = [(k, "excluded") for k in menu.get("excluded", [])]
    _flagged += [(k, "cycle_distorted") for k in menu.get("cycle_distorted", [])]
    for k, flag in _flagged:
        v, basis = candidates.get(k, (None, ""))
        if v is None:
            continue
        name = _ANCHOR_DISPLAY.get(k, k)
        if name in _blend_names:
            continue
        excluded_anchors.append({"name": name, "value": round(v, 2),
                                 "basis": basis, "flag": flag})

    # A routing tag is shown only for a non-default routed type (the default
    # mature path keeps the legacy methodology wording byte-for-byte).
    _route_tag = f"[{company_type}] " if company_type else ""

    # --- Anchor consistency gate over the BLENDED set ----------------------
    anchor_values = [a["value"] for a in anchors]
    anchor_dispersion: Optional[float] = None
    if len(anchor_values) >= 2:
        lo_a, hi_a = min(anchor_values), max(anchor_values)
        if lo_a > 0:
            anchor_dispersion = round(hi_a / lo_a, 4)
    irreconcilable = (anchor_dispersion is not None
                      and anchor_dispersion > ANCHOR_DISPERSION_THRESHOLD)

    # Caveats: caller-supplied tokens (e.g. cyclical_band_unavailable) plus a
    # generic single_anchor_blend when exactly one anchor entered the blend.
    _caveats = list(caveats or [])
    if len(anchors) == 1 and CAVEAT_SINGLE_ANCHOR_BLEND not in _caveats:
        _caveats.append(CAVEAT_SINGLE_ANCHOR_BLEND)

    _common = dict(
        company_type=company_type,
        company_type_confidence=company_type_confidence,
        routing_rationale=routing_rationale,
        methods_used=methods_used,
        excluded_anchors=excluded_anchors,
        ev_s_value=(round(ev_s, 2) if ev_s is not None else None),
        ev_ebitda_value=(round(ev_ebitda, 2) if ev_ebitda is not None else None),
        pb_ps_value=(round(pb_ps, 2) if pb_ps is not None else None),
        peer_basis=peer_basis,
        backlog_note=backlog_note,
        caveats=_caveats,
    )

    if irreconcilable:
        # Do NOT blend irreconcilable anchors into a fake band. Present each
        # anchor separately (anchors list), force low confidence, suppress the
        # range. Downstream LONG entry logic degrades to "technical only".
        parts = ", ".join(f"{a['name']} ${a['value']:.2f}" for a in anchors)
        methodology = (
            _route_tag + "Anchors irreconcilable (dispersion "
            f"{anchor_dispersion:.1f}× > {ANCHOR_DISPERSION_THRESHOLD:.0f}×): "
            f"{parts}. Not blended — each shown separately. / "
            f"估值锚不一致（离散度 {anchor_dispersion:.1f}× > "
            f"{ANCHOR_DISPERSION_THRESHOLD:.0f}×）：{parts}。不做融合，分别列示。"
        )
        return AppFairValue(
            ticker=(ticker or "").upper().strip(),
            dcf_value=(round(dcf, 2) if dcf is not None else None),
            relative_value=(round(rel, 2) if rel is not None else None),
            analyst_target=(round(ana, 2) if ana is not None else None),
            analyst_count=a_count,
            fair_value_low=0.0,
            fair_value_mid=0.0,
            fair_value_high=0.0,
            confidence="low",
            upside_pct=0.0,
            methodology=methodology,
            computed_at=_now_iso(),
            data_source=data_source,
            dcf_note=dcf_note,
            blend_state=_BLEND_IRRECONCILABLE,
            anchor_dispersion=anchor_dispersion,
            anchors=anchors,
            relative_basis=relative_basis,
            peer_pe_basis=peer_pe_basis,
            **_common,
        )

    # --- low / mid / high via per-anchor factors over the blended set ------
    low_candidates, high_candidates = [], []
    mid_num = mid_den = 0.0
    for k in blend_keys:
        v, _ = candidates.get(k, (None, ""))
        if v is None:
            continue
        lf, mw, hf, _lbl = _ANCHOR_FACTORS[k]
        low_candidates.append(v * lf)
        high_candidates.append(v * hf)
        mid_num += v * mw
        mid_den += mw
    fair_value_low = min(low_candidates) if low_candidates else (cp * 0.85 if cp else 0.0)
    fair_value_mid = (mid_num / mid_den) if mid_den > 0 else (cp if cp else 0.0)
    fair_value_high = max(high_candidates) if high_candidates else (cp * 1.15 if cp else 0.0)

    # Defensive ordering guarantee (the math above already preserves it, but
    # round-off / degenerate inputs are clamped here so the invariant is hard).
    fair_value_low = round(fair_value_low, 2)
    fair_value_mid = round(max(fair_value_mid, fair_value_low), 2)
    fair_value_high = round(max(fair_value_high, fair_value_mid), 2)

    # --- confidence --------------------------------------------------------
    source_count = len(anchors)
    spread = ((fair_value_high - fair_value_low) / fair_value_mid) if fair_value_mid > 0 else 1.0
    if source_count == 3 and spread < 0.40:
        confidence = "high"
    elif source_count >= 2 or (source_count >= 1 and spread < 0.60):
        confidence = "medium"
    else:
        confidence = "low"

    upside_pct = ((fair_value_mid - cp) / cp) if cp > 0 else 0.0

    if methods_used:
        methodology = _route_tag + "Fair value blends " + ", ".join(methods_used) + "."
    else:
        methodology = (
            _route_tag + "No usable valuation anchors for this company type — band "
            "anchored on current price (low confidence)."
        )
    if dcf is None and dcf_note:
        methodology = methodology + " " + dcf_note
    if backlog_note:
        methodology = methodology + " " + backlog_note

    blend_state = _BLEND_OK if anchors else _BLEND_NONE

    return AppFairValue(
        ticker=(ticker or "").upper().strip(),
        dcf_value=(round(dcf, 2) if dcf is not None else None),
        relative_value=(round(rel, 2) if rel is not None else None),
        analyst_target=(round(ana, 2) if ana is not None else None),
        analyst_count=a_count,
        fair_value_low=fair_value_low,
        fair_value_mid=fair_value_mid,
        fair_value_high=fair_value_high,
        confidence=confidence,
        upside_pct=round(upside_pct, 4),
        methodology=methodology,
        computed_at=_now_iso(),
        data_source=data_source,
        dcf_note=dcf_note,
        blend_state=blend_state,
        anchor_dispersion=anchor_dispersion,
        anchors=anchors,
        relative_basis=relative_basis,
        peer_pe_basis=peer_pe_basis,
        **_common,
    )


# ---------------------------------------------------------------------------
# Raw input fetch (yfinance only; fail-closed) — patched by tests
# ---------------------------------------------------------------------------


def _fetch_raw(ticker: str) -> dict:
    """Fetch the raw fair-value inputs for ``ticker`` from yfinance (fail-closed).

    Returns a dict with ``fcf_ttm`` / ``shares`` / ``growth_rate`` /
    ``trailing_eps`` / ``sector`` / ``analyst_median`` / ``analyst_mean`` /
    ``analyst_count`` / ``live``. Any missing piece is ``None`` (or ``0`` for the
    count). Never raises.
    """
    out = {
        "fcf_ttm": None,
        "fcf_source": "",
        "ebitda": None,
        "shares": None,
        "growth_rate": None,
        "trailing_eps": None,
        "forward_eps": None,
        "sector": None,
        "analyst_median": None,
        "analyst_mean": None,
        "analyst_count": 0,
        "live": False,
        # --- Method-router classifier / extra-anchor inputs (Valuation Refactor
        # v1). All read from the SAME tk.info dict already fetched above — no new
        # per-ticker network. Any missing piece stays None.
        "industry": None,
        "revenue_growth": None,
        "earnings_growth": None,
        "profit_margin": None,
        "operating_margin": None,
        "market_cap": None,
        "enterprise_value": None,
        "total_revenue": None,
        "total_debt": None,
        "total_cash": None,
        "book_value": None,
        "price_to_book": None,
        "price_to_sales": None,
    }
    try:
        import yfinance as yf

        tk = yf.Ticker(ticker)
        info = tk.info if isinstance(getattr(tk, "info", None), dict) else {}
        if info:
            out["live"] = True

        out["sector"] = info.get("sector")
        # Classifier / extra-anchor inputs (same info dict; no extra fetch).
        out["industry"] = info.get("industry")
        out["revenue_growth"] = _finite(info.get("revenueGrowth"))
        out["earnings_growth"] = _finite(info.get("earningsGrowth"))
        out["profit_margin"] = _finite(info.get("profitMargins"))
        out["operating_margin"] = _finite(info.get("operatingMargins"))
        out["market_cap"] = _finite_pos(info.get("marketCap"))
        out["enterprise_value"] = _finite(info.get("enterpriseValue"))
        out["total_revenue"] = _finite_pos(info.get("totalRevenue"))
        out["total_debt"] = _finite(info.get("totalDebt"))
        out["total_cash"] = _finite(info.get("totalCash"))
        out["book_value"] = _finite(info.get("bookValue"))  # per-share
        out["price_to_book"] = _finite_pos(info.get("priceToBook"))
        out["price_to_sales"] = _finite_pos(
            info.get("priceToSalesTrailing12Months"))
        out["trailing_eps"] = _finite(info.get("trailingEps"))
        # Forward consensus EPS (preferred basis for the relative anchor, Task 2).
        out["forward_eps"] = _finite(info.get("forwardEps"))
        out["shares"] = _finite_pos(info.get("sharesOutstanding"))
        out["analyst_median"] = _finite_pos(info.get("targetMedianPrice"))
        out["analyst_mean"] = _finite_pos(info.get("targetMeanPrice"))
        try:
            out["analyst_count"] = int(info.get("numberOfAnalystOpinions") or 0)
        except (TypeError, ValueError):
            out["analyst_count"] = 0

        # growth_rate = min(earningsGrowth | revenueGrowth | 0.05, 0.15)
        g = _finite(info.get("earningsGrowth"))
        if g is None:
            g = _finite(info.get("revenueGrowth"))
        if g is None:
            g = _GROWTH_DEFAULT
        out["growth_rate"] = min(g, _GROWTH_CAP)

        out["ebitda"] = _finite(info.get("ebitda"))
        # TTM free cash flow via a documented fallback chain (see
        # :func:`_fcf_with_source`); the chosen source is recorded for the
        # methodology string.
        out["fcf_ttm"], out["fcf_source"] = _fcf_with_source(tk, info)
    except Exception:  # noqa: BLE001 — fail-closed (no live info)
        return out
    return out


def _fcf_with_source(tk, info: dict) -> tuple:
    """Return ``(fcf_ttm, source_label)`` via a documented fallback chain (fail-closed):

    1. cashflow statement — the ``Free Cash Flow`` row (TTM) if present, else
       ``Σ_last4q(operating CF) − |Σ_last4q(CapEx)|``,
    2. yfinance ``freeCashflow`` (used directly if non-None and non-zero),
    3. yfinance ``operatingCashflow`` alone (proxy; no CapEx),
    4. ``ebitda × 0.6`` (rough proxy),
    5. otherwise ``(None, "")``.

    Each level logs success (``logging.info``) or failure (``logging.warning``) so
    it is clear which source actually supplied the FCF.
    """
    # 1. Quarterly cashflow statement (4 quarters → TTM).
    try:
        qcf = getattr(tk, "quarterly_cashflow", None)
        if qcf is not None and not getattr(qcf, "empty", True):
            def _row_sum(names, n=4):
                for nm in names:
                    if nm in qcf.index:
                        vals = []
                        for c in list(qcf.columns)[:n]:
                            v = _finite(qcf.loc[nm, c])
                            if v is not None:
                                vals.append(v)
                        if vals:
                            return sum(vals)
                return None

            # yfinance's cashflow statement usually carries a literal
            # "Free Cash Flow" row — read it directly first.
            fcf_row = _row_sum(["Free Cash Flow", "FreeCashFlow"])
            if fcf_row is not None:
                src = "cashflow statement (Free Cash Flow, TTM)"
                _log.info("FCF source: %s, value: %s", src, fcf_row)
                return fcf_row, src
            ocf = _row_sum(["Operating Cash Flow", "Total Cash From Operating Activities"])
            capex = _row_sum(["Capital Expenditure", "Capital Expenditures"])
            if ocf is not None and capex is not None:
                src = "cashflow statement (OCF − CapEx, TTM)"
                val = ocf - abs(capex)
                _log.info("FCF source: %s, value: %s", src, val)
                return val, src
            _log.warning("FCF level 1 failed: no Free Cash Flow / OCF+CapEx rows in "
                         "quarterly cashflow")
        else:
            _log.warning("FCF level 1 failed: quarterly_cashflow empty/unavailable")
    except Exception as exc:  # noqa: BLE001 — fall through
        _log.warning("FCF level 1 failed: %s", exc)
    # 2. info-level freeCashflow — use directly if non-None and non-zero.
    try:
        fcf = _finite(info.get("freeCashflow"))
        if fcf is not None and fcf != 0:
            src = "yfinance freeCashflow"
            _log.info("FCF source: %s, value: %s", src, fcf)
            return fcf, src
        _log.warning("FCF level 2 failed: freeCashflow None/0")
    except Exception as exc:  # noqa: BLE001
        _log.warning("FCF level 2 failed: %s", exc)
    # 3. operatingCashflow alone (proxy; CapEx unavailable at info level).
    try:
        ocf = _finite(info.get("operatingCashflow"))
        if ocf is not None and ocf != 0:
            src = "operatingCashflow proxy (no CapEx)"
            _log.info("FCF source: %s, value: %s", src, ocf)
            return ocf, src
        _log.warning("FCF level 3 failed: operatingCashflow None/0")
    except Exception as exc:  # noqa: BLE001
        _log.warning("FCF level 3 failed: %s", exc)
    # 4. EBITDA × 0.6 rough proxy.
    try:
        ebitda = _finite(info.get("ebitda"))
        if ebitda is not None and ebitda != 0:
            val = ebitda * 0.6
            src = "EBITDA × 0.6 proxy"
            _log.info("FCF source: %s, value: %s", src, val)
            return val, src
        _log.warning("FCF level 4 failed: ebitda None/0")
    except Exception as exc:  # noqa: BLE001
        _log.warning("FCF level 4 failed: %s", exc)
    # 5. nothing usable.
    _log.warning("FCF level 5: no usable FCF/EBITDA source")
    return None, ""


# ---------------------------------------------------------------------------
# compute_app_fair_value — cached, fail-closed
# ---------------------------------------------------------------------------


def _compute_dcf_per_share(raw: dict) -> Optional[float]:
    """Simplified single-stage Gordon-growth DCF, per share (fail-closed -> None).

    ``dcf = (fcf_per_share × (1 + g)^5) / (WACC − g)``; returns ``None`` when the
    FCF base, shares, or ``WACC − g`` denominator is unavailable / non-positive.
    """
    fcf = _finite(raw.get("fcf_ttm"))
    shares = _finite_pos(raw.get("shares"))
    g = _finite(raw.get("growth_rate"))
    if fcf is None or fcf <= 0 or shares is None or g is None:
        return None
    denom = _WACC - g
    if denom <= 0:  # growth >= WACC -> Gordon growth undefined; not computable
        return None
    fcf_ps = fcf / shares
    if fcf_ps <= 0:
        return None
    value = fcf_ps * ((1.0 + g) ** _DCF_YEARS) / denom
    if value != value or value <= 0:  # NaN / non-positive
        return None
    return round(value, 2)


# ---------------------------------------------------------------------------
# Routed extra-anchor helpers (Valuation Refactor v1, Task 2)
# ---------------------------------------------------------------------------


def _median(vals: list) -> Optional[float]:
    nums = sorted(float(v) for v in vals if _finite(v) is not None)
    if not nums:
        return None
    n = len(nums)
    mid = n // 2
    return nums[mid] if n % 2 == 1 else (nums[mid - 1] + nums[mid]) / 2.0


def _percentile(vals: list, p: float) -> Optional[float]:
    """Linear-interpolation percentile (``p`` in 0–100) over ``vals`` (numpy-free,
    deterministic). Returns ``None`` for an empty / all-invalid list."""
    nums = sorted(float(v) for v in vals if _finite(v) is not None)
    if not nums:
        return None
    if len(nums) == 1:
        return nums[0]
    rank = (p / 100.0) * (len(nums) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(nums) - 1)
    frac = rank - lo
    return nums[lo] + (nums[hi] - nums[lo]) * frac


def _rule_of_40_multiplier(score: Optional[float]) -> float:
    """Rule-of-40 quality modifier on a growth multiple (bounded).

    ``score`` = revenue_growth + fcf_margin (fractions). A score above the 40%
    target earns a premium on the multiple; below it, a discount. Bounded to
    [``_RULE_OF_40_MIN``, ``_RULE_OF_40_MAX``] so it never dominates the anchor.
    """
    s = _finite(score)
    if s is None:
        return 1.0
    mult = 1.0 + (s - _RULE_OF_40_TARGET) * _RULE_OF_40_SENSITIVITY
    return round(max(_RULE_OF_40_MIN, min(_RULE_OF_40_MAX, mult)), 4)


def _compute_ev_s(raw: dict, *, peer_ps: Optional[float] = None,
                  rule_of_40_score: Optional[float] = None) -> tuple:
    """Forward EV/S anchor, per share (equity-level P/S proxy; fail-closed).

    ``fair_price = target_ps × (revenue / shares)`` where ``target_ps`` is the
    growth-matched peer median P/S when provided, else the sector-median P/S
    fallback. A Rule-of-40 multiplier (growth_profitable) adjusts the multiple.
    Uses an equity-level P/S (not a true EV/S) because the peer table supplies
    P/S and this needs no net-debt bridge — documented honestly in the basis.
    Returns ``(value, basis)`` or ``(None, "")``.
    """
    revenue = _finite_pos(raw.get("total_revenue"))
    shares = _finite_pos(raw.get("shares"))
    if revenue is None or shares is None:
        return None, ""
    if peer_ps is not None and peer_ps > 0:
        target_ps = float(peer_ps)
        basis = "peer P/S (growth-matched)"
    else:
        target_ps = get_sector_median_ps(raw.get("sector"))
        basis = "sector P/S (fallback)"
    if rule_of_40_score is not None:
        mult = _rule_of_40_multiplier(rule_of_40_score)
        target_ps = target_ps * mult
        basis = f"{basis} ×R40 {mult:.2f}"
    value = target_ps * (revenue / shares)
    if value != value or value <= 0:
        return None, ""
    return round(value, 2), basis


def _compute_ev_ebitda(raw: dict, *, peer_ev_ebitda: Optional[float] = None) -> tuple:
    """Forward EV/EBITDA anchor, per share (fail-closed).

    ``fair_ev = target × EBITDA``; ``fair_equity = fair_ev − net_debt``;
    ``per_share = fair_equity / shares``. ``net_debt`` prefers
    ``total_debt − total_cash``, else ``enterprise_value − market_cap`` (the EV
    bridge), else ``0``. ``target`` is the growth-matched peer median EV/EBITDA
    when provided, else the sector-median fallback. Returns ``(value, basis)`` or
    ``(None, "")``.
    """
    ebitda = _finite_pos(raw.get("ebitda"))
    shares = _finite_pos(raw.get("shares"))
    if ebitda is None or shares is None:
        return None, ""
    if peer_ev_ebitda is not None and peer_ev_ebitda > 0:
        target = float(peer_ev_ebitda)
        basis = "peer EV/EBITDA (growth-matched)"
    else:
        target = get_sector_median_ev_ebitda(raw.get("sector"))
        basis = "sector EV/EBITDA (fallback)"
    fair_ev = target * ebitda
    net_debt: Optional[float] = None
    td = _finite(raw.get("total_debt"))
    tc = _finite(raw.get("total_cash"))
    if td is not None and tc is not None:
        net_debt = td - tc
    else:
        ev = _finite(raw.get("enterprise_value"))
        mc = _finite_pos(raw.get("market_cap"))
        if ev is not None and mc is not None:
            net_debt = ev - mc
    if net_debt is None:
        net_debt = 0.0
    value = (fair_ev - net_debt) / shares
    if value != value or value <= 0:
        return None, ""
    return round(value, 2), basis


def _compute_pb_ps_band(raw: dict, *, pb_history: Optional[list] = None,
                        ps_history: Optional[list] = None,
                        years: Optional[int] = None) -> tuple:
    """PB/PS band anchor vs the ticker's OWN ≤4-year ANNUAL history (fail-closed).

    Given a historical annual multiple series (``pb_history`` of price/book or
    ``ps_history`` of price/sales — built by :func:`build_pb_ps_history` on the
    page path), the blended anchor is the **p50 (median)** of the multiple ×
    the current per-share fundamental (mid-cycle re-rating). The p20 / p80
    percentiles (``PB_PS_BAND_PERCENTILES``) contextualize the cheap / expensive
    band in the basis label. PB is preferred (stabler for cyclicals); PS is the
    fallback. The label says it is an **≤Ny annual approximation** — never a "5y
    band". Returns ``(value, basis)`` or ``(None, "")`` (callers degrade with the
    ``cyclical_band_unavailable`` caveat).
    """
    lo_p = PB_PS_BAND_PERCENTILES["low"]
    mid_p = PB_PS_BAND_PERCENTILES["mid"]
    hi_p = PB_PS_BAND_PERCENTILES["high"]

    bvps = _finite_pos(raw.get("book_value"))
    if pb_history and bvps is not None:
        vals = [v for v in pb_history if _finite_pos(v) is not None]
        p50 = _percentile(vals, mid_p)
        if p50 is not None and p50 > 0:
            value = p50 * bvps
            if value == value and value > 0:
                p20 = _percentile(vals, lo_p) or p50
                p80 = _percentile(vals, hi_p) or p50
                yr = years if years else len(vals)
                return round(value, 2), (
                    f"PB band (≤{yr}y annual: p20/p50/p80 = "
                    f"{p20:.1f}/{p50:.1f}/{p80:.1f}× × BVPS ${bvps:.2f})")
    if ps_history:
        revenue = _finite_pos(raw.get("total_revenue"))
        shares = _finite_pos(raw.get("shares"))
        if revenue is not None and shares is not None:
            vals = [v for v in ps_history if _finite_pos(v) is not None]
            p50 = _percentile(vals, mid_p)
            if p50 is not None and p50 > 0:
                value = p50 * (revenue / shares)
                if value == value and value > 0:
                    p20 = _percentile(vals, lo_p) or p50
                    p80 = _percentile(vals, hi_p) or p50
                    yr = years if years else len(vals)
                    return round(value, 2), (
                        f"PS band (≤{yr}y annual: p20/p50/p80 = "
                        f"{p20:.1f}/{p50:.1f}/{p80:.1f}× × sales/share)")
    return None, ""


def build_pb_ps_history(balance_sheet, income_stmt, price_history, *,
                        ticker: str = "",
                        max_years: int = CYCLICAL_BAND_MAX_YEARS) -> dict:
    """Build annual PB & PS multiple series from annual statements + dated prices.

    PURE (no network): given yfinance-shaped annual ``balance_sheet`` /
    ``income_stmt`` DataFrames (index = row label, columns = fiscal-period
    Timestamps) and a ``price_history`` (a DataFrame/Series with a DatetimeIndex
    and a Close), compute, for each of the most recent ``max_years`` fiscal
    periods, ``PB = price_asof / (equity / shares)`` and
    ``PS = price_asof / (revenue / shares)``. Returns
    ``{"pb_history", "ps_history", "years", "source"}`` (``years`` = count of
    usable annual observations). Fail-closed → ``{}`` on any error.
    """
    try:
        import pandas as pd  # local import; pandas already a project dep

        def _row(df, names):
            if df is None or getattr(df, "empty", True):
                return None
            for nm in names:
                if nm in df.index:
                    return df.loc[nm]
            return None

        equity_row = _row(balance_sheet, [
            "Stockholders Equity", "Common Stock Equity",
            "Total Stockholder Equity", "StockholdersEquity"])
        shares_row = _row(balance_sheet, [
            "Ordinary Shares Number", "Share Issued", "Common Stock Shares Outstanding"])
        revenue_row = _row(income_stmt, ["Total Revenue", "TotalRevenue", "Revenue"])
        if equity_row is None or shares_row is None:
            return {}

        # Dated Close series for as-of lookup.
        close = None
        if price_history is not None:
            try:
                if hasattr(price_history, "columns"):
                    close = (price_history["Close"] if "Close" in price_history.columns
                             else price_history.iloc[:, 0])
                else:
                    close = price_history  # already a Series
                close = close.dropna()
                close = close.sort_index()
            except Exception:  # noqa: BLE001
                close = None

        def _price_asof(date):
            if close is None or len(close) == 0:
                return None
            try:
                ts = pd.Timestamp(date)
                sub = close[close.index <= ts]
                if len(sub) == 0:
                    return None
                return float(sub.iloc[-1])
            except Exception:  # noqa: BLE001
                return None

        cols = list(equity_row.index)[:max_years]
        pb_history, ps_history = [], []
        for c in cols:
            try:
                equity = _finite_pos(equity_row.get(c))
                shares = _finite_pos(shares_row.get(c))
            except Exception:  # noqa: BLE001
                equity = shares = None
            if equity is None or shares is None:
                continue
            price = _price_asof(c)
            if price is None or price <= 0:
                continue
            bvps = equity / shares
            if bvps and bvps > 0:
                pb = price / bvps
                if pb == pb and pb > 0:
                    pb_history.append(round(pb, 4))
            if revenue_row is not None:
                try:
                    rev = _finite_pos(revenue_row.get(c))
                except Exception:  # noqa: BLE001
                    rev = None
                if rev is not None:
                    sps = rev / shares
                    if sps and sps > 0:
                        ps = price / sps
                        if ps == ps and ps > 0:
                            ps_history.append(round(ps, 4))
        years = max(len(pb_history), len(ps_history))
        if years == 0:
            return {}
        return {"pb_history": pb_history, "ps_history": ps_history,
                "years": years, "source": "yfinance annual (≤4y)"}
    except Exception:  # noqa: BLE001 — fully fail-closed
        return {}


def fetch_cyclical_band_history(ticker: str, *, price_loader=None) -> dict:
    """Fetch annual fundamentals (yfinance) + cached prices → PB/PS history.

    **PAGE PATH ONLY** — the per-ticker fundamentals fetch is allowed only where
    existing per-ticker fetches happen (pages/4 context). The price history comes
    from the local OHLCV cache (no fetch). Results are written through to the
    anchor cache by the page hand-off, so subsequent loads and ALL ranking /
    Cockpit refresh paths read the baked band and stay network-free. Fail-closed
    → ``{}`` (caller degrades with the ``cyclical_band_unavailable`` caveat).
    """
    try:
        import yfinance as yf

        tk = yf.Ticker(ticker)
        bs = getattr(tk, "balance_sheet", None)
        istmt = getattr(tk, "income_stmt", None)
        if istmt is None or getattr(istmt, "empty", True):
            istmt = getattr(tk, "financials", None)

        if price_loader is None:
            def price_loader(t):  # default: local OHLCV cache (no fetch)
                try:
                    from lib import cache_manager
                    for dt in ("ohlcv_1y_1d", "ohlcv", "ohlcv_2y_1d", "ohlcv_5y_1wk"):
                        df = cache_manager.load(t, dt)
                        if df is not None and not getattr(df, "empty", True):
                            return df
                except Exception:  # noqa: BLE001
                    return None
                return None

        px = price_loader(ticker)
        return build_pb_ps_history(bs, istmt, px, ticker=ticker)
    except Exception:  # noqa: BLE001 — fail-closed (page path)
        return {}


# ---------------------------------------------------------------------------
# compute_app_fair_value — cached, fail-closed, routed
# ---------------------------------------------------------------------------


def _assemble_fair_value(ticker: str, current_price: float,
                         dcf_override: Optional[float], raw: dict,
                         peers: Optional[list] = None,
                         cyclical_history_fetcher=None) -> AppFairValue:
    """Classify the company, route the anchor menu, and assemble the band (pure).

    Computes the DCF / relative-PE / analyst anchors (unchanged), classifies the
    company via :mod:`lib.valuation_router`, selects the method menu, and computes
    the routed extra anchors (EV/S, EV/EBITDA, PB/PS band) the menu needs. When
    ``peers`` (already-fetched peer ``info`` dicts) is supplied, growth-matched
    peer multiples drive the EV anchors; otherwise the sector-median fallback is
    used and ``peer_basis="sector_fallback"``.

    ``cyclical_history_fetcher`` (page path only) is a ``ticker -> {pb_history,
    ps_history, years}`` callable used ONLY for the cyclical menu to build the
    ≤4y annual PB/PS band. It is ``None`` on the cached / ranking path, so those
    paths stay network-free and degrade with the ``cyclical_band_unavailable``
    caveat. The dispersion gate still runs LAST inside :func:`build_app_fair_value`.
    """
    from lib.valuation_router import (
        classify_company, select_method_menu, match_growth_profile_peers,
    )

    # --- DCF (unchanged) ---------------------------------------------------
    if dcf_override is not None and dcf_override > 0:
        dcf_value = round(float(dcf_override), 2)
        dcf_source = "user DCF (Financials tab)"
        dcf_note = dcf_source
    else:
        dcf_value = _compute_dcf_per_share(raw)
        _fcf_src = raw.get("fcf_source") or ""
        if dcf_value is not None:
            dcf_source = _fcf_src
            dcf_note = f"DCF FCF source: {_fcf_src}" if _fcf_src else ""
        else:
            dcf_source = ""
            if raw.get("fcf_ttm") is None:
                dcf_note = "FCF data unavailable / 现金流数据不可用"
            else:
                dcf_note = (
                    "DCF not computable (shares missing or growth ≥ WACC) / "
                    "DCF 无法计算"
                )

    # --- relative-PE anchor (Task 2 forward basis; unchanged) --------------
    relative_value: Optional[float] = None
    relative_basis = ""
    peer_pe_basis = ""
    fwd_eps = _finite_pos(raw.get("forward_eps"))
    eps = _finite_pos(raw.get("trailing_eps"))
    chosen_eps = fwd_eps if fwd_eps is not None else eps
    if chosen_eps is not None:
        relative_value = round(get_sector_median_pe(raw.get("sector")) * chosen_eps, 2)
        relative_basis = "forward" if fwd_eps is not None else "trailing_fallback"
        peer_pe_basis = "mixed" if fwd_eps is not None else "trailing"

    # analyst_target = targetMedianPrice if available else targetMeanPrice
    analyst_target = raw.get("analyst_median") or raw.get("analyst_mean")

    # --- Classify + route (Task 1 / Task 2) --------------------------------
    classification = classify_company(
        ticker=ticker,
        sector=raw.get("sector"),
        industry=raw.get("industry"),
        revenue_growth=raw.get("revenue_growth"),
        profit_margin=raw.get("profit_margin"),
        operating_margin=raw.get("operating_margin"),
        fcf=raw.get("fcf_ttm"),
        market_cap=raw.get("market_cap"),
    )
    menu_key = select_method_menu(classification)
    menu = METHOD_MENUS.get(menu_key, METHOD_MENUS["mature_profitable"])

    # --- Routed extra anchors ---------------------------------------------
    ev_s_value = ev_ebitda_value = pb_ps_value = None
    ev_s_basis = ev_ebitda_basis = pb_ps_basis = ""
    peer_basis = ""
    backlog_note = ""
    caveats: list = []

    needs_ev_s = "ev_s" in menu.get("blend", [])
    needs_ev_ebitda = "ev_ebitda" in menu.get("blend", [])
    needs_pb_ps = "pb_ps_band" in menu.get("blend", [])

    # Growth-matched peer multiples (Task 3) come from already-fetched peer info
    # dicts. No new per-ticker network — peers is None on the cached path.
    peer_ps = None
    peer_ev_ebitda = None
    if peers and (needs_ev_s or needs_ev_ebitda):
        target_profile = {
            "ticker": ticker, "sector": raw.get("sector"),
            "revenue_growth": raw.get("revenue_growth"),
            "market_cap": raw.get("market_cap"),
        }
        if needs_ev_s:
            pm = match_growth_profile_peers(
                target_profile, peers,
                multiple_field="priceToSalesTrailing12Months")
            peer_ps = pm.median_multiple
            peer_basis = pm.peer_basis
        if needs_ev_ebitda:
            pm = match_growth_profile_peers(
                target_profile, peers, multiple_field="enterpriseToEbitda")
            peer_ev_ebitda = pm.median_multiple
            peer_basis = pm.peer_basis

    if needs_ev_s:
        r40 = None
        if menu_key == "growth_profitable":
            rg = _finite(raw.get("revenue_growth"))
            fcf = _finite(raw.get("fcf_ttm"))
            rev = _finite_pos(raw.get("total_revenue"))
            if rg is not None and fcf is not None and rev:
                r40 = rg + (fcf / rev)
        ev_s_value, ev_s_basis = _compute_ev_s(
            raw, peer_ps=peer_ps, rule_of_40_score=r40)
        if not peer_basis:
            peer_basis = "growth_matched" if peer_ps is not None else "sector_fallback"

    if needs_ev_ebitda:
        ev_ebitda_value, ev_ebitda_basis = _compute_ev_ebitda(
            raw, peer_ev_ebitda=peer_ev_ebitda)
        if not peer_basis:
            peer_basis = "growth_matched" if peer_ev_ebitda is not None else "sector_fallback"

    if needs_pb_ps:
        # Build the ≤4y annual PB/PS band ONLY on the page path (fetcher
        # supplied). Need >= MIN_CYCLICAL_BAND_OBS annual observations; else
        # degrade to analyst-only with a real caveat token (network-free ranking /
        # Cockpit paths always take this degrade since they pass no fetcher).
        _hist = None
        if cyclical_history_fetcher is not None:
            try:
                _hist = cyclical_history_fetcher(ticker)
            except Exception:  # noqa: BLE001 — fail-closed
                _hist = None
        _yrs = int((_hist or {}).get("years", 0) or 0)
        if _hist and _yrs >= MIN_CYCLICAL_BAND_OBS:
            pb_ps_value, pb_ps_basis = _compute_pb_ps_band(
                raw, pb_history=_hist.get("pb_history"),
                ps_history=_hist.get("ps_history"), years=_yrs)
        if pb_ps_value is None:
            caveats.append(CAVEAT_CYCLICAL_BAND_UNAVAILABLE)

    if menu.get("backlog_metric") and not pb_ps_value:
        backlog_note = (
            "Backlog coverage is the right metric for project-driven names but "
            "is unavailable on free sources / 在建订单覆盖率是项目型公司的合适指标，"
            "但免费数据源不可得"
        )

    # Honest DCF reason when the menu EXCLUDES DCF for this company type.
    if "dcf" in menu.get("excluded", []):
        dcf_note = (
            f"DCF excluded for {menu_key} companies (method not appropriate) / "
            f"{menu_key} 类公司不适用 DCF"
        )

    data_source = _LIVE if raw.get("live") else _FIXTURE
    return build_app_fair_value(
        ticker=ticker,
        current_price=current_price,
        dcf_value=dcf_value,
        relative_value=relative_value,
        analyst_target=analyst_target,
        analyst_count=raw.get("analyst_count", 0),
        data_source=data_source,
        dcf_source=dcf_source,
        dcf_note=dcf_note,
        relative_basis=relative_basis,
        peer_pe_basis=peer_pe_basis,
        company_type=classification.company_type,
        company_type_confidence=classification.confidence,
        routing_rationale=classification.rationale,
        ev_s_value=ev_s_value,
        ev_s_basis=ev_s_basis,
        ev_ebitda_value=ev_ebitda_value,
        ev_ebitda_basis=ev_ebitda_basis,
        pb_ps_value=pb_ps_value,
        pb_ps_basis=pb_ps_basis,
        peer_basis=peer_basis,
        backlog_note=backlog_note,
        caveats=caveats,
    )


def _compute_cached(ticker: str, current_price: float,
                    dcf_override: Optional[float] = None) -> AppFairValue:
    """Cached worker (fail-closed). Separated so ``st.cache_data`` can wrap it.

    ``dcf_override`` (per-share, > 0) replaces the internal Gordon-growth DCF —
    used by the Equity page "Update Valuation" action to feed a user-adjusted DCF
    intrinsic value from the Financials tab. Uses the sector-median fallback for
    routed peer multiples (``peers=None``) so the cache key stays hashable.
    """
    raw = _fetch_raw(ticker)
    return _assemble_fair_value(ticker, current_price, dcf_override, raw, peers=None)


def compute_app_fair_value(ticker: str, current_price: float, *,
                           dcf_override: Optional[float] = None,
                           peers: Optional[list] = None,
                           cyclical_history_fetcher=None) -> AppFairValue:
    """Compute the :class:`AppFairValue` for ``ticker`` (yfinance only; fail-closed).

    Cached TTL=3600 keyed on ``(ticker, current_price, dcf_override)``. When
    ``dcf_override`` (a per-share intrinsic value, > 0) is supplied it replaces the
    internal DCF (e.g. a user-adjusted DCF from the Financials tab).

    When ``peers`` (already-fetched peer ``info`` dicts from the Equity page peer
    table) OR ``cyclical_history_fetcher`` (the page-path PB/PS-band fetcher) is
    supplied, the routed path runs UNCACHED (the inputs are unhashable) and re-uses
    page-side data — no new per-ticker network beyond the page's existing fetches.
    The cached path (neither supplied) is taken by the ranking / Cockpit refresh,
    which therefore stays network-free. On ANY failure a well-formed
    ``data_source="fixture"`` result anchored on ``current_price`` is returned —
    this function never raises.
    """
    t = (ticker or "").upper().strip()
    cp = _finite_pos(current_price) or 0.0
    ov: Optional[float] = None
    if dcf_override is not None:
        try:
            ov = float(dcf_override)
            ov = ov if ov > 0 else None
        except (TypeError, ValueError):
            ov = None
    try:
        if peers or cyclical_history_fetcher is not None:
            return _assemble_fair_value(
                t, round(cp, 4), ov, _fetch_raw(t), peers=peers,
                cyclical_history_fetcher=cyclical_history_fetcher)
        return _compute_cached(t, round(cp, 4), ov)
    except Exception:  # noqa: BLE001 — fully fail-closed
        return build_app_fair_value(
            ticker=t,
            current_price=cp if cp > 0 else 100.0,
            dcf_value=None,
            relative_value=None,
            analyst_target=None,
            analyst_count=0,
            data_source=_FIXTURE,
        )


def store_equity_research_result(
    ticker: str,
    fair_value: AppFairValue,
    debate_summary: str = "",
    analyst_action: str = "",
) -> None:
    """Write the fair-value summary into ``st.session_state["equity_research_results"]``.

    Review-only hand-off consumed by ``lib/order_advisor.py`` (the Trading Desk
    primary valuation anchor). Fail-closed: a missing Streamlit runtime never
    raises to the caller. The session dict lives only in the browser session;
    additionally the anchor is **written through** to the local
    ``data/anchor_cache.json`` (network-free) so the Investment Cockpit
    long-horizon enrichment can read it later without any fetch.
    """
    t = (ticker or "").upper().strip()
    if not t or fair_value is None:
        return

    # Write-through to the local anchor cache (independent of Streamlit; the
    # Cockpit reads this on its network-free enrichment path). Fail-closed.
    try:
        from lib.anchor_cache import write_app_fair_value

        write_app_fair_value(fair_value)
    except Exception:  # noqa: BLE001 — cache write is best-effort
        pass

    try:
        import streamlit as st

        results = dict(st.session_state.get("equity_research_results", {}) or {})
        results[t] = {
            "fair_value_low": fair_value.fair_value_low,
            "fair_value_mid": fair_value.fair_value_mid,
            "fair_value_high": fair_value.fair_value_high,
            "confidence": fair_value.confidence,
            "methodology": fair_value.methodology,
            "upside_pct": fair_value.upside_pct,
            # Anchor consistency state (Task 1) so the Trading Desk LONG path can
            # degrade explicitly instead of silently using a blended mid.
            "blend_state": getattr(fair_value, "blend_state", "blended"),
            "debate_summary": debate_summary or "",
            "analyst_action": analyst_action or "",
            "computed_at": fair_value.computed_at,
        }
        st.session_state["equity_research_results"] = results
    except Exception:  # noqa: BLE001 — fail-closed (no Streamlit runtime)
        return


# Decorate the cached worker with st.cache_data when Streamlit is importable
# (the body is fail-closed, so offline tests simply execute it once per call).
try:  # pragma: no cover - cache decoration is environment dependent
    import streamlit as _st

    _compute_cached = _st.cache_data(ttl=_CACHE_TTL, show_spinner=False)(_compute_cached)
except Exception:  # noqa: BLE001
    pass
