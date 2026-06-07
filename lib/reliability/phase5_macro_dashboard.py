"""
lib/reliability/phase5_macro_dashboard.py

Phase 5O: Macro Dashboard v0.1 — macro-regime view-model layer.

Purpose
-------
Elevates **macro** from a subsection inside Sector Research into a first-class
upstream input for the Investment Cockpit. This module defines deterministic,
evidence-first Pydantic view-model contracts for:

  1. A **macro regime snapshot** — rates, inflation, liquidity, credit spreads,
     volatility (VIX), market breadth, the dollar, risk appetite, the earnings
     cycle, the growth / recession regime, and policy risk — each represented
     as a fixture-only factor view (NOT a live calculator, NOT live data).
  2. A **regime status** (risk_on / risk_off / neutral / transition /
     liquidity_expanding / liquidity_tightening / inflation_pressure /
     growth_slowdown / earnings_revision_positive / earnings_revision_negative
     / unknown).
  3. **Horizon-specific bias** — short-term, mid-term, and long-term posture
     leanings derived from the regime.
  4. Review-only **opportunity posture** guidance (favor_momentum_trades /
     favor_pullback_entries / favor_watchlist_only / favor_risk_reduction /
     favor_long_term_accumulation / research_more / unknown). These are NOT
     trade instructions and do NOT produce a final buy/sell decision.
  5. Fixture-only **theme implications** (AI infrastructure, space, biotech,
     embodied AI / robotics, data-center power, memory / HBM, optical
     networking, nuclear / energy, ...). These are NOT live market claims.

Macro is intended to feed the future Theme Intelligence (Phase 5J) and
Opportunity Queue (Phase 5K) logic **as context**. This phase deliberately does
**not** rewire Phase 5J / 5K runtime logic; the relationship is expressed only
through fixture / view-model references.

Design principles
-----------------
- Standalone, deterministic, offline / mock-only.
- No live macro data retrieval; no live LLM calls; no external API; no
  Streamlit; no Anthropic / OpenAI SDK; no database / file persistence / vector
  store.
- No reading of the live workflow state JSON file.
- No import of ``app.py``, ``pages/*``, ``lib/llm_orchestrator.py``, or
  ``lib/workflow_state.py``.
- No broker / order / execution behavior; no executable order fields.
- No ``approved_for_execution`` field on any Phase 5O model. Every model sets
  ``extra="forbid"``, so an ``approved_for_execution`` (or any order-ticket)
  field cannot be smuggled in via construction; the invariant holds by
  construction.

Macro is not a decision
-----------------------
**The macro dashboard does not produce final buy/sell decisions and does not
authorize execution.** It produces review-only posture and bias *context* that
a human (and, later, the Opportunity Queue) can weigh. High-conviction regime
reads are still inputs, not orders.

Fixtures
--------
All ``build_*_macro_dashboard_view`` outputs are **deterministic examples**.
Sample theme names and factor descriptors are illustrative fixture examples
only — they are **not** live market claims, recommendations, or current facts.
No API is called to produce them.

Disclaimer: outputs are for research / educational purposes only and do not
constitute investment advice.

See ``docs/reliability_phase_5o_macro_dashboard_v01.md``.
"""

from __future__ import annotations

import hashlib
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Deterministic fixture timestamp (no wall-clock time -> deterministic output)
# ---------------------------------------------------------------------------

SAMPLE_MACRO_AS_OF: str = "2026-05-20T00:00:00Z"

_SCHEMA_VERSION: str = "phase5_macro_dashboard_v1"


# ---------------------------------------------------------------------------
# Literal aliases
# ---------------------------------------------------------------------------

# Scenario kind for a dashboard fixture.
MacroScenarioKind = Literal[
    "default",
    "risk_on",
    "risk_off",
    "transition",
    "degraded",
]

MACRO_SCENARIO_KINDS: tuple[MacroScenarioKind, ...] = (
    "default",
    "risk_on",
    "risk_off",
    "transition",
    "degraded",
)

# The macro factors represented in a regime snapshot.
MacroFactorKind = Literal[
    "rates",
    "inflation",
    "liquidity",
    "credit_spreads",
    "volatility",
    "market_breadth",
    "dollar",
    "risk_appetite",
    "earnings_cycle",
    "growth_regime",
    "policy_risk",
    "unknown",
]

# The required factors a complete macro snapshot should carry.
REQUIRED_MACRO_FACTORS: tuple[MacroFactorKind, ...] = (
    "rates",
    "inflation",
    "liquidity",
    "credit_spreads",
    "volatility",
    "market_breadth",
    "dollar",
    "risk_appetite",
    "earnings_cycle",
    "growth_regime",
    "policy_risk",
)

# Directional trend of a factor (fixture descriptor, not a computed value).
MacroFactorTrend = Literal[
    "expanding",
    "tightening",
    "rising",
    "falling",
    "stable",
    "improving",
    "deteriorating",
    "widening",
    "narrowing",
    "mixed",
    "unknown",
]

# Whether a factor is supportive / a headwind for risk assets (fixture read).
MacroFactorSignal = Literal[
    "supportive",
    "neutral",
    "headwind",
    "mixed",
    "unknown",
]

# Top-level regime statuses.
MacroRegimeStatusLabel = Literal[
    "risk_on",
    "risk_off",
    "neutral",
    "transition",
    "liquidity_expanding",
    "liquidity_tightening",
    "inflation_pressure",
    "growth_slowdown",
    "earnings_revision_positive",
    "earnings_revision_negative",
    "unknown",
]

MACRO_REGIME_STATUS_LABELS: tuple[MacroRegimeStatusLabel, ...] = (
    "risk_on",
    "risk_off",
    "neutral",
    "transition",
    "liquidity_expanding",
    "liquidity_tightening",
    "inflation_pressure",
    "growth_slowdown",
    "earnings_revision_positive",
    "earnings_revision_negative",
    "unknown",
)

# Confidence in a regime read (qualitative).
MacroConfidence = Literal["low", "moderate", "high", "unknown"]

# Review-only opportunity posture guidance. NOT a trade instruction.
MacroOpportunityPosture = Literal[
    "favor_momentum_trades",
    "favor_pullback_entries",
    "favor_watchlist_only",
    "favor_risk_reduction",
    "favor_long_term_accumulation",
    "research_more",
    "unknown",
]

MACRO_OPPORTUNITY_POSTURES: tuple[MacroOpportunityPosture, ...] = (
    "favor_momentum_trades",
    "favor_pullback_entries",
    "favor_watchlist_only",
    "favor_risk_reduction",
    "favor_long_term_accumulation",
    "research_more",
    "unknown",
)

# Horizon bias reuses the same review-only posture vocabulary.
MacroHorizonBiasLabel = MacroOpportunityPosture

# Risk-appetite state.
MacroRiskState = Literal["risk_on", "risk_off", "neutral", "transition", "unknown"]

# Earnings-revision direction.
MacroEarningsRevisionDirection = Literal[
    "positive",
    "negative",
    "mixed",
    "stable",
    "unknown",
]

# How macro context implies for a theme (NOT a buy/sell call, NOT live).
MacroThemeImplication = Literal[
    "tailwind",
    "headwind",
    "neutral",
    "mixed",
    "unknown",
]

# Warnings.
MacroWarningType = Literal[
    "degraded_data",
    "missing_factor",
    "conflicting_signals",
    "late_cycle",
    "crowding",
    "policy_uncertainty",
    "liquidity_tightening",
    "unknown",
]

MacroWarningSeverity = Literal["info", "low", "medium", "high", "unknown"]


# ---------------------------------------------------------------------------
# Internal helpers (deterministic)
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
    """Lowercase alnum slug; non-alnum runs collapse to single underscores."""
    out: list[str] = []
    prev_us = False
    for ch in str(text).strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_us = False
        else:
            if not prev_us:
                out.append("_")
                prev_us = True
    return "".join(out).strip("_") or "x"


def _short_hash(text: str) -> str:
    """Deterministic 8-char hex digest. No randomness, no time."""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:8]


def make_macro_dashboard_id(label: str) -> str:
    """Deterministic, content-sensitive macro dashboard id (no timestamp)."""
    return f"macrodash_{_slug(label)}_{_short_hash('macrodash::' + str(label))}"


_FIXTURE_EVIDENCE_PREFIX = "macroev"


def _ev(label: str) -> str:
    """Deterministic fixture evidence-id string (opaque; no real store)."""
    return f"{_FIXTURE_EVIDENCE_PREFIX}_{_short_hash(label)}"


# ---------------------------------------------------------------------------
# Factor / section view models
# ---------------------------------------------------------------------------


class MacroRiskWarning(BaseModel):
    """A non-fatal risk / caveat attached to a dashboard or section."""

    model_config = ConfigDict(extra="forbid")

    warning_type: MacroWarningType = "unknown"
    severity: MacroWarningSeverity = "info"
    message: str = ""


class MacroRegimeFactorView(BaseModel):
    """A single macro factor (rates, inflation, liquidity, ...).

    All quantitative content is a fixture *descriptor* (``value_placeholder``),
    never a computed indicator value. ``is_live_data`` is permanently False.
    """

    model_config = ConfigDict(extra="forbid")

    factor: MacroFactorKind = "unknown"
    label: str = ""
    trend: MacroFactorTrend = "unknown"
    signal: MacroFactorSignal = "unknown"
    # Fixture descriptor only — e.g. "policy rate plateauing (placeholder)".
    value_placeholder: Optional[str] = None
    description: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    is_live_data: Literal[False] = False
    is_fixture_example: bool = True


class MacroRatesInflationView(BaseModel):
    """Rates + inflation section."""

    model_config = ConfigDict(extra="forbid")

    rates: MacroRegimeFactorView = Field(default_factory=MacroRegimeFactorView)
    inflation: MacroRegimeFactorView = Field(default_factory=MacroRegimeFactorView)
    overall_signal: MacroFactorSignal = "unknown"
    summary: str = ""


class MacroLiquidityView(BaseModel):
    """Liquidity section (expanding / tightening)."""

    model_config = ConfigDict(extra="forbid")

    liquidity: MacroRegimeFactorView = Field(default_factory=MacroRegimeFactorView)
    liquidity_trend: MacroFactorTrend = "unknown"
    overall_signal: MacroFactorSignal = "unknown"
    summary: str = ""


class MacroCreditVolatilityView(BaseModel):
    """Credit spreads + volatility (VIX) section."""

    model_config = ConfigDict(extra="forbid")

    credit_spreads: MacroRegimeFactorView = Field(
        default_factory=MacroRegimeFactorView
    )
    volatility: MacroRegimeFactorView = Field(default_factory=MacroRegimeFactorView)
    overall_signal: MacroFactorSignal = "unknown"
    summary: str = ""


class MacroMarketBreadthView(BaseModel):
    """Market breadth / participation section."""

    model_config = ConfigDict(extra="forbid")

    breadth: MacroRegimeFactorView = Field(default_factory=MacroRegimeFactorView)
    overall_signal: MacroFactorSignal = "unknown"
    summary: str = ""


class MacroDollarView(BaseModel):
    """US dollar section."""

    model_config = ConfigDict(extra="forbid")

    dollar: MacroRegimeFactorView = Field(default_factory=MacroRegimeFactorView)
    overall_signal: MacroFactorSignal = "unknown"
    summary: str = ""


class MacroRiskAppetiteView(BaseModel):
    """Risk-appetite section."""

    model_config = ConfigDict(extra="forbid")

    risk_appetite: MacroRegimeFactorView = Field(
        default_factory=MacroRegimeFactorView
    )
    risk_state: MacroRiskState = "unknown"
    overall_signal: MacroFactorSignal = "unknown"
    summary: str = ""


class MacroEarningsCycleView(BaseModel):
    """Earnings cycle / revision section."""

    model_config = ConfigDict(extra="forbid")

    earnings_cycle: MacroRegimeFactorView = Field(
        default_factory=MacroRegimeFactorView
    )
    revision_direction: MacroEarningsRevisionDirection = "unknown"
    overall_signal: MacroFactorSignal = "unknown"
    summary: str = ""


class MacroPolicyRiskView(BaseModel):
    """Policy-risk section (monetary / fiscal / regulatory)."""

    model_config = ConfigDict(extra="forbid")

    policy_risk: MacroRegimeFactorView = Field(
        default_factory=MacroRegimeFactorView
    )
    overall_signal: MacroFactorSignal = "unknown"
    summary: str = ""


# ---------------------------------------------------------------------------
# Concrete macro indicator models (Phase 5O.1 — Macro Indicator Expansion)
#
# These model concrete, user-requested macro instruments and economic-release
# indicators (WTI, gold, CNN Fear & Greed, QQQ, IWM, NFP, CPI, PPI). They are
# fixture-only descriptors: ``is_live_data`` is permanently False and
# ``source_type`` is permanently ``"fixture"``. No live macro / external API is
# ever called to populate them; values are deterministic placeholders.
# ---------------------------------------------------------------------------

# Canonical indicator keys (stable identifiers for validation).
MacroIndicatorKey = Literal[
    "wti",
    "gold",
    "fear_greed",
    "qqq",
    "iwm",
    "nfp",
    "cpi",
    "ppi",
    "unknown",
]

# The concrete indicators a complete Phase 5O.1 panel should carry.
REQUIRED_MACRO_INDICATOR_KEYS: tuple[MacroIndicatorKey, ...] = (
    "wti",
    "gold",
    "fear_greed",
    "qqq",
    "iwm",
    "nfp",
    "cpi",
    "ppi",
)

MacroIndicatorCategory = Literal[
    "commodity",
    "risk_appetite",
    "economic_release",
    "unknown",
]

MACRO_INDICATOR_CATEGORIES: tuple[MacroIndicatorCategory, ...] = (
    "commodity",
    "risk_appetite",
    "economic_release",
)

CommodityType = Literal["wti_crude", "gold", "unknown"]

IndexLeadershipRole = Literal[
    "large_cap_growth",
    "small_cap",
    "breadth_proxy",
    "unknown",
]

FearGreedZone = Literal[
    "extreme_fear",
    "fear",
    "neutral",
    "greed",
    "extreme_greed",
    "unknown",
]

EconomicReleaseSurprise = Literal[
    "above_expectations",
    "in_line",
    "below_expectations",
    "unknown",
]

LaborMarketStrength = Literal["strong", "moderate", "weak", "unknown"]

InflationPipelineStage = Literal["consumer", "producer", "unknown"]


def make_macro_indicator_id(key: str) -> str:
    """Deterministic, content-sensitive macro indicator id (no timestamp)."""
    return f"macroind_{_slug(key)}_{_short_hash('macroind::' + str(key))}"


class MacroIndicatorView(BaseModel):
    """A single concrete, fixture-only macro indicator.

    Base for commodity / instrument / sentiment / economic-release indicators.
    All quantitative content is a fixture descriptor (``latest_value`` /
    ``fixture_value``), never a computed or live value. ``is_live_data`` is
    permanently False and ``source_type`` is permanently ``"fixture"``.
    """

    model_config = ConfigDict(extra="forbid")

    indicator_id: str = Field(min_length=1)
    indicator_key: MacroIndicatorKey = "unknown"
    display_name: str = ""
    category: MacroIndicatorCategory = "unknown"
    # Fixture descriptors only (e.g. "~$78/bbl (placeholder)").
    latest_value: Optional[str] = None
    fixture_value: Optional[str] = None
    trend: MacroFactorTrend = "unknown"
    status: str = ""
    signal: MacroFactorSignal = "unknown"
    interpretation: str = ""
    macro_implication: str = ""
    horizon_implication: str = ""
    source_type: Literal["fixture"] = "fixture"
    is_live_data: Literal[False] = False
    is_fixture_example: bool = True
    evidence_refs: list[str] = Field(default_factory=list)
    warnings: list[MacroRiskWarning] = Field(default_factory=list)


class MacroInstrumentSignalView(MacroIndicatorView):
    """A tradeable-instrument indicator (commodity or equity index).

    ``symbol`` is an illustrative fixture symbol, not a live quote subscription.
    """

    symbol: str = ""


class CommoditySignalView(MacroInstrumentSignalView):
    """A commodity indicator (WTI crude oil, GC / gold)."""

    commodity_type: CommodityType = "unknown"
    inflation_sensitivity: str = ""
    growth_sensitivity: str = ""


class IndexRiskAppetiteSignalView(MacroInstrumentSignalView):
    """An equity-index risk-appetite / leadership indicator (QQQ, IWM)."""

    leadership_role: IndexLeadershipRole = "unknown"
    breadth_implication: str = ""


class RiskSentimentSignalView(MacroIndicatorView):
    """A risk-sentiment indicator (CNN Fear & Greed Index)."""

    sentiment_zone: FearGreedZone = "unknown"
    crowding_implication: str = ""


class MacroEconomicReleaseView(MacroIndicatorView):
    """An economic-release indicator (base for NFP / CPI / PPI)."""

    release_name: str = ""
    release_cadence: str = ""
    surprise_direction: EconomicReleaseSurprise = "unknown"


class LaborMarketSignalView(MacroEconomicReleaseView):
    """A labor-market release indicator (Nonfarm Payrolls / NFP)."""

    fed_reaction_risk: str = ""
    labor_strength: LaborMarketStrength = "unknown"


class InflationReleaseSignalView(MacroEconomicReleaseView):
    """An inflation release indicator (CPI / PPI)."""

    pipeline_stage: InflationPipelineStage = "unknown"
    pass_through_risk: str = ""


class MacroIndicatorPanel(BaseModel):
    """A grouped panel of concrete macro indicators (Phase 5O.1).

    Indicators are grouped into commodities, risk-appetite / leadership (CNN
    Fear & Greed + QQQ + IWM), and economic releases (NFP + CPI + PPI). Use
    ``collect_panel_indicators`` to iterate every indicator regardless of group.
    """

    model_config = ConfigDict(extra="forbid")

    commodities: list[CommoditySignalView] = Field(default_factory=list)
    fear_greed: Optional[RiskSentimentSignalView] = None
    index_leadership: list[IndexRiskAppetiteSignalView] = Field(default_factory=list)
    labor_releases: list[LaborMarketSignalView] = Field(default_factory=list)
    inflation_releases: list[InflationReleaseSignalView] = Field(default_factory=list)
    overall_signal: MacroFactorSignal = "unknown"
    summary: str = ""


def collect_panel_indicators(panel: MacroIndicatorPanel) -> list[MacroIndicatorView]:
    """Return every indicator in ``panel`` as a flat list (concrete instances)."""
    items: list[MacroIndicatorView] = []
    items.extend(panel.commodities)
    if panel.fear_greed is not None:
        items.append(panel.fear_greed)
    items.extend(panel.index_leadership)
    items.extend(panel.labor_releases)
    items.extend(panel.inflation_releases)
    return items


# ---------------------------------------------------------------------------
# Regime / status models
# ---------------------------------------------------------------------------


class MacroRegimeStatus(BaseModel):
    """The primary macro regime status plus supporting statuses.

    There is intentionally no buy/sell field and no executable order field on
    this model: a regime read is context, not a decision.
    """

    model_config = ConfigDict(extra="forbid")

    primary_status: MacroRegimeStatusLabel = "unknown"
    supporting_statuses: list[MacroRegimeStatusLabel] = Field(default_factory=list)
    label: str = ""
    description: str = ""
    confidence: MacroConfidence = "unknown"
    is_decision: Literal[False] = False


class MacroRegimeSnapshot(BaseModel):
    """A point-in-time macro regime snapshot.

    ``factors`` is the flat list of every factor view (the source of truth for
    "required factors present" validation); the section views reference the same
    factors grouped for display.
    """

    model_config = ConfigDict(extra="forbid")

    as_of: Optional[str] = None
    regime_status: MacroRegimeStatus = Field(default_factory=MacroRegimeStatus)
    rates_inflation: MacroRatesInflationView = Field(
        default_factory=MacroRatesInflationView
    )
    liquidity: MacroLiquidityView = Field(default_factory=MacroLiquidityView)
    credit_volatility: MacroCreditVolatilityView = Field(
        default_factory=MacroCreditVolatilityView
    )
    market_breadth: MacroMarketBreadthView = Field(
        default_factory=MacroMarketBreadthView
    )
    dollar: MacroDollarView = Field(default_factory=MacroDollarView)
    risk_appetite: MacroRiskAppetiteView = Field(
        default_factory=MacroRiskAppetiteView
    )
    earnings_cycle: MacroEarningsCycleView = Field(
        default_factory=MacroEarningsCycleView
    )
    policy_risk: MacroPolicyRiskView = Field(default_factory=MacroPolicyRiskView)
    # Growth / recession regime factor (kept on the snapshot directly).
    growth_regime: MacroRegimeFactorView = Field(
        default_factory=MacroRegimeFactorView
    )
    # Flat list of all factor views for iteration / validation.
    factors: list[MacroRegimeFactorView] = Field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# Bias / posture / theme models
# ---------------------------------------------------------------------------


class MacroHorizonBiasView(BaseModel):
    """Horizon-specific posture leanings derived from the regime.

    These are review-only *biases*, not trade instructions. The same regime can
    favor momentum short-term while preferring accumulation long-term.
    """

    model_config = ConfigDict(extra="forbid")

    short_term_bias: MacroHorizonBiasLabel = "unknown"
    mid_term_bias: MacroHorizonBiasLabel = "unknown"
    long_term_bias: MacroHorizonBiasLabel = "unknown"
    short_term_rationale: str = ""
    mid_term_rationale: str = ""
    long_term_rationale: str = ""
    is_decision: Literal[False] = False
    notes: str = ""


class MacroOpportunityPostureView(BaseModel):
    """Review-only opportunity posture guidance.

    Explicit, assertable markers state this is neither a buy signal nor an
    executable decision. The macro dashboard never produces a final buy/sell.
    """

    model_config = ConfigDict(extra="forbid")

    primary_posture: MacroOpportunityPosture = "unknown"
    secondary_postures: list[MacroOpportunityPosture] = Field(default_factory=list)
    rationale: str = ""
    # Assertable invariants.
    is_buy_signal: Literal[False] = False
    is_executable: Literal[False] = False
    produces_final_decision: Literal[False] = False
    requires_human_review: Literal[True] = True
    notes: str = ""


class MacroThemeImplicationView(BaseModel):
    """A fixture-only macro implication for a theme.

    ``is_live_market_claim`` is permanently False — these are example
    relationships, not current market facts.
    """

    model_config = ConfigDict(extra="forbid")

    theme_name: str = Field(min_length=1)
    implication: MacroThemeImplication = "unknown"
    rationale: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    is_live_market_claim: Literal[False] = False
    is_fixture_example: bool = True


# ---------------------------------------------------------------------------
# Safety + validation + top-level view
# ---------------------------------------------------------------------------


class MacroDashboardSafetyBanner(BaseModel):
    """Safety banner surfaced on the macro dashboard.

    ``approved_for_execution`` is intentionally absent (every model
    ``extra="forbid"``); the invariant ``approved_for_execution`` is False/absent
    holds by construction and is surfaced as banner copy on the page.
    """

    model_config = ConfigDict(extra="forbid")

    is_fixture_only: Literal[True] = True
    is_demo_only: Literal[True] = True
    no_live_macro_api: Literal[True] = True
    no_external_api: Literal[True] = True
    no_llm: Literal[True] = True
    no_broker_or_order: Literal[True] = True
    no_investment_advice: Literal[True] = True
    produces_final_decision: Literal[False] = False
    requires_human_review: Literal[True] = True
    message: str = (
        "Fixture/demo only — no live macro API, no external API, no LLM, no "
        "broker/order/execution, not investment advice. Macro is review-only "
        "context, not a buy/sell decision."
    )


class MacroDashboardValidationSummary(BaseModel):
    """Deterministic, safe summary of a macro dashboard view.

    Reports factor counts and invariant flags. ``is_safe_empty`` is True for an
    empty dashboard (a valid, safe state). ``issues`` carries non-fatal
    observations; it never makes the dashboard a decision and never fabricates
    completion for missing factors.
    """

    model_config = ConfigDict(extra="forbid")

    factor_count: int = 0
    primary_regime_status: MacroRegimeStatusLabel = "unknown"
    has_all_required_factors: bool = False
    missing_factors: list[str] = Field(default_factory=list)
    theme_implication_count: int = 0
    # Phase 5O.1 — concrete indicator metrics.
    indicator_count: int = 0
    has_all_required_indicators: bool = False
    missing_indicators: list[str] = Field(default_factory=list)
    commodity_count: int = 0
    risk_appetite_indicator_count: int = 0
    economic_release_count: int = 0
    is_degraded: bool = False
    is_safe_empty: bool = True
    # Safety invariants (always True for a well-formed Phase 5O dashboard).
    no_final_decision: bool = True
    no_buy_signal_fields: bool = True
    no_executable_order_fields: bool = True
    approved_for_execution_absent: bool = True
    no_live_macro_api: bool = True
    # Phase 5O.1 — every concrete indicator is fixture-only (never live data).
    all_indicators_fixture_only: bool = True
    issues: list[str] = Field(default_factory=list)


class MacroDashboardView(BaseModel):
    """Top-level Phase 5O contract: a macro regime view + bias + posture.

    Fixture / mock-only. Carries no buy/sell decision, no executable order
    field, and no live macro data. Feeds future Theme Intelligence / Opportunity
    Queue logic as context only.
    """

    model_config = ConfigDict(extra="forbid")

    dashboard_id: str = Field(min_length=1)
    as_of: Optional[str] = None
    schema_version: str = _SCHEMA_VERSION
    scenario_kind: MacroScenarioKind = "default"
    title: str = ""
    description: str = ""
    regime_snapshot: MacroRegimeSnapshot = Field(default_factory=MacroRegimeSnapshot)
    horizon_bias: MacroHorizonBiasView = Field(default_factory=MacroHorizonBiasView)
    opportunity_posture: MacroOpportunityPostureView = Field(
        default_factory=MacroOpportunityPostureView
    )
    theme_implications: list[MacroThemeImplicationView] = Field(default_factory=list)
    # Phase 5O.1 — concrete macro indicator panel (WTI / gold / Fear & Greed /
    # QQQ / IWM / NFP / CPI / PPI). Fixture-only.
    indicator_panel: MacroIndicatorPanel = Field(default_factory=MacroIndicatorPanel)
    safety_banner: MacroDashboardSafetyBanner = Field(
        default_factory=MacroDashboardSafetyBanner
    )
    validation_summary: Optional[MacroDashboardValidationSummary] = None
    warnings: list[MacroRiskWarning] = Field(default_factory=list)
    is_fixture: bool = True
    notes: str = ""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_macro_dashboard_view(
    view: MacroDashboardView,
) -> MacroDashboardValidationSummary:
    """Produce a deterministic, safe validation summary for a dashboard view.

    Counts factors, flags missing required factors, marks an empty dashboard as
    a *safe empty* state, and records non-fatal observations in ``issues``.
    Missing factors are reflected as ``missing_factors`` — never fabricated.
    """
    factors = list(view.regime_snapshot.factors)
    present_kinds = {f.factor for f in factors}
    missing = [k for k in REQUIRED_MACRO_FACTORS if k not in present_kinds]

    # Phase 5O.1 — concrete indicator panel coverage.
    panel = view.indicator_panel
    indicators = collect_panel_indicators(panel)
    present_indicator_keys = {i.indicator_key for i in indicators}
    missing_indicators = [
        k for k in REQUIRED_MACRO_INDICATOR_KEYS if k not in present_indicator_keys
    ]
    all_indicators_fixture_only = all(
        (i.is_live_data is False and i.source_type == "fixture") for i in indicators
    )

    primary = view.regime_snapshot.regime_status.primary_status
    is_degraded = (
        view.scenario_kind == "degraded"
        or primary == "unknown"
        or bool(missing)
        or bool(missing_indicators)
    )
    is_safe_empty = (
        (len(factors) == 0)
        and (len(view.theme_implications) == 0)
        and (len(indicators) == 0)
    )

    issues: list[str] = []
    for k in missing:
        issues.append(f"missing required macro factor: {k!r}")
    for k in missing_indicators:
        issues.append(f"missing required macro indicator: {k!r}")

    return MacroDashboardValidationSummary(
        factor_count=len(factors),
        primary_regime_status=primary,
        has_all_required_factors=(not missing),
        missing_factors=[str(k) for k in missing],
        theme_implication_count=len(view.theme_implications),
        indicator_count=len(indicators),
        has_all_required_indicators=(not missing_indicators),
        missing_indicators=[str(k) for k in missing_indicators],
        commodity_count=len(panel.commodities),
        risk_appetite_indicator_count=(
            len(panel.index_leadership) + (1 if panel.fear_greed is not None else 0)
        ),
        economic_release_count=(
            len(panel.labor_releases) + len(panel.inflation_releases)
        ),
        all_indicators_fixture_only=all_indicators_fixture_only,
        is_degraded=is_degraded,
        is_safe_empty=is_safe_empty,
        issues=issues,
    )


def attach_macro_dashboard_validation_summary(
    view: MacroDashboardView,
) -> MacroDashboardView:
    """Return ``view`` with its ``validation_summary`` populated."""
    view.validation_summary = validate_macro_dashboard_view(view)
    return view


# ---------------------------------------------------------------------------
# Factor / snapshot builder helpers (deterministic)
# ---------------------------------------------------------------------------


def build_macro_factor_view(
    *,
    factor: MacroFactorKind,
    label: str,
    trend: MacroFactorTrend = "unknown",
    signal: MacroFactorSignal = "unknown",
    value_placeholder: Optional[str] = None,
    description: str = "",
    evidence_label: Optional[str] = None,
) -> MacroRegimeFactorView:
    """Build a deterministic factor view. ``evidence_label`` -> fixture id."""
    refs = [_ev(evidence_label)] if evidence_label else []
    return MacroRegimeFactorView(
        factor=factor,
        label=label,
        trend=trend,
        signal=signal,
        value_placeholder=value_placeholder,
        description=description,
        evidence_refs=refs,
    )


def _assemble_snapshot(
    *,
    as_of: str,
    regime_status: MacroRegimeStatus,
    rates: MacroRegimeFactorView,
    inflation: MacroRegimeFactorView,
    liquidity: MacroRegimeFactorView,
    credit: MacroRegimeFactorView,
    volatility: MacroRegimeFactorView,
    breadth: MacroRegimeFactorView,
    dollar: MacroRegimeFactorView,
    risk_appetite: MacroRegimeFactorView,
    earnings: MacroRegimeFactorView,
    growth: MacroRegimeFactorView,
    policy: MacroRegimeFactorView,
    rates_inflation_signal: MacroFactorSignal,
    rates_inflation_summary: str,
    liquidity_signal: MacroFactorSignal,
    liquidity_summary: str,
    credit_vol_signal: MacroFactorSignal,
    credit_vol_summary: str,
    breadth_signal: MacroFactorSignal,
    breadth_summary: str,
    dollar_signal: MacroFactorSignal,
    dollar_summary: str,
    risk_state: MacroRiskState,
    risk_signal: MacroFactorSignal,
    risk_summary: str,
    revision_direction: MacroEarningsRevisionDirection,
    earnings_signal: MacroFactorSignal,
    earnings_summary: str,
    policy_signal: MacroFactorSignal,
    policy_summary: str,
    notes: str = "",
) -> MacroRegimeSnapshot:
    """Assemble a deterministic regime snapshot from individual factor views."""
    return MacroRegimeSnapshot(
        as_of=as_of,
        regime_status=regime_status,
        rates_inflation=MacroRatesInflationView(
            rates=rates,
            inflation=inflation,
            overall_signal=rates_inflation_signal,
            summary=rates_inflation_summary,
        ),
        liquidity=MacroLiquidityView(
            liquidity=liquidity,
            liquidity_trend=liquidity.trend,
            overall_signal=liquidity_signal,
            summary=liquidity_summary,
        ),
        credit_volatility=MacroCreditVolatilityView(
            credit_spreads=credit,
            volatility=volatility,
            overall_signal=credit_vol_signal,
            summary=credit_vol_summary,
        ),
        market_breadth=MacroMarketBreadthView(
            breadth=breadth,
            overall_signal=breadth_signal,
            summary=breadth_summary,
        ),
        dollar=MacroDollarView(
            dollar=dollar,
            overall_signal=dollar_signal,
            summary=dollar_summary,
        ),
        risk_appetite=MacroRiskAppetiteView(
            risk_appetite=risk_appetite,
            risk_state=risk_state,
            overall_signal=risk_signal,
            summary=risk_summary,
        ),
        earnings_cycle=MacroEarningsCycleView(
            earnings_cycle=earnings,
            revision_direction=revision_direction,
            overall_signal=earnings_signal,
            summary=earnings_summary,
        ),
        policy_risk=MacroPolicyRiskView(
            policy_risk=policy,
            overall_signal=policy_signal,
            summary=policy_summary,
        ),
        growth_regime=growth,
        factors=[
            rates,
            inflation,
            liquidity,
            credit,
            volatility,
            breadth,
            dollar,
            risk_appetite,
            earnings,
            growth,
            policy,
        ],
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Phase 5O.1 indicator factories + per-scenario panel builders (deterministic)
# ---------------------------------------------------------------------------


def _commodity_signal(
    *, key, symbol, display_name, commodity_type, trend, signal, value, status,
    interpretation, macro_implication, horizon_implication,
    inflation_sensitivity, growth_sensitivity, ev, warnings=None,
) -> CommoditySignalView:
    return CommoditySignalView(
        indicator_id=make_macro_indicator_id(key),
        indicator_key=key,
        display_name=display_name,
        category="commodity",
        symbol=symbol,
        commodity_type=commodity_type,
        trend=trend,
        signal=signal,
        latest_value=value,
        fixture_value=value,
        status=status,
        interpretation=interpretation,
        macro_implication=macro_implication,
        horizon_implication=horizon_implication,
        inflation_sensitivity=inflation_sensitivity,
        growth_sensitivity=growth_sensitivity,
        evidence_refs=[_ev(ev)],
        warnings=list(warnings or []),
    )


def _index_signal(
    *, key, symbol, display_name, leadership_role, trend, signal, value, status,
    interpretation, macro_implication, horizon_implication, breadth_implication,
    ev, warnings=None,
) -> IndexRiskAppetiteSignalView:
    return IndexRiskAppetiteSignalView(
        indicator_id=make_macro_indicator_id(key),
        indicator_key=key,
        display_name=display_name,
        category="risk_appetite",
        symbol=symbol,
        leadership_role=leadership_role,
        trend=trend,
        signal=signal,
        latest_value=value,
        fixture_value=value,
        status=status,
        interpretation=interpretation,
        macro_implication=macro_implication,
        horizon_implication=horizon_implication,
        breadth_implication=breadth_implication,
        evidence_refs=[_ev(ev)],
        warnings=list(warnings or []),
    )


def _fear_greed_signal(
    *, trend, signal, value, status, sentiment_zone, interpretation,
    macro_implication, horizon_implication, crowding_implication, ev, warnings=None,
) -> RiskSentimentSignalView:
    return RiskSentimentSignalView(
        indicator_id=make_macro_indicator_id("fear_greed"),
        indicator_key="fear_greed",
        display_name="CNN Fear & Greed Index",
        category="risk_appetite",
        trend=trend,
        signal=signal,
        latest_value=value,
        fixture_value=value,
        status=status,
        sentiment_zone=sentiment_zone,
        interpretation=interpretation,
        macro_implication=macro_implication,
        horizon_implication=horizon_implication,
        crowding_implication=crowding_implication,
        evidence_refs=[_ev(ev)],
        warnings=list(warnings or []),
    )


def _labor_signal(
    *, trend, signal, value, status, surprise_direction, labor_strength,
    interpretation, macro_implication, horizon_implication, fed_reaction_risk,
    ev, warnings=None,
) -> LaborMarketSignalView:
    return LaborMarketSignalView(
        indicator_id=make_macro_indicator_id("nfp"),
        indicator_key="nfp",
        display_name="Nonfarm Payrolls (NFP)",
        category="economic_release",
        release_name="Nonfarm Payrolls",
        release_cadence="monthly",
        trend=trend,
        signal=signal,
        latest_value=value,
        fixture_value=value,
        status=status,
        surprise_direction=surprise_direction,
        labor_strength=labor_strength,
        interpretation=interpretation,
        macro_implication=macro_implication,
        horizon_implication=horizon_implication,
        fed_reaction_risk=fed_reaction_risk,
        evidence_refs=[_ev(ev)],
        warnings=list(warnings or []),
    )


def _inflation_signal(
    *, key, display_name, release_name, pipeline_stage, trend, signal, value, status,
    surprise_direction, interpretation, macro_implication, horizon_implication,
    pass_through_risk, ev, warnings=None,
) -> InflationReleaseSignalView:
    return InflationReleaseSignalView(
        indicator_id=make_macro_indicator_id(key),
        indicator_key=key,
        display_name=display_name,
        category="economic_release",
        release_name=release_name,
        release_cadence="monthly",
        pipeline_stage=pipeline_stage,
        trend=trend,
        signal=signal,
        latest_value=value,
        fixture_value=value,
        status=status,
        surprise_direction=surprise_direction,
        interpretation=interpretation,
        macro_implication=macro_implication,
        horizon_implication=horizon_implication,
        pass_through_risk=pass_through_risk,
        evidence_refs=[_ev(ev)],
        warnings=list(warnings or []),
    )


def _build_indicator_panel_risk_on() -> MacroIndicatorPanel:
    """Risk-on indicator panel: strong leadership + broadening, greed crowding."""
    return MacroIndicatorPanel(
        commodities=[
            _commodity_signal(
                key="wti", symbol="WTI", display_name="WTI Crude Oil",
                commodity_type="wti_crude", trend="rising", signal="mixed",
                value="~$82/bbl (placeholder)", status="firm",
                interpretation="Crude firm on resilient demand (fixture).",
                macro_implication="Mild inflation pressure / input-cost risk; also a growth-demand signal.",
                horizon_implication="Watch energy input costs for transports / margins.",
                inflation_sensitivity="Rising oil adds to headline inflation (placeholder).",
                growth_sensitivity="Demand-driven strength is pro-cyclical (placeholder).",
                ev="ron_wti",
            ),
            _commodity_signal(
                key="gold", symbol="GC", display_name="Gold (GC)",
                commodity_type="gold", trend="rising", signal="supportive",
                value="~$2,350/oz (placeholder)", status="firm",
                interpretation="Gold firm on softer real rates / weaker dollar (fixture).",
                macro_implication="Real-rate sensitivity; weaker dollar is supportive — not a risk-off signal here.",
                horizon_implication="Diversifier; corroborates softer real rates.",
                inflation_sensitivity="Hedge against inflation / debasement (placeholder).",
                growth_sensitivity="Low direct growth sensitivity (placeholder).",
                ev="ron_gold",
            ),
        ],
        fear_greed=_fear_greed_signal(
            trend="rising", signal="mixed", value="72 / Greed (placeholder)",
            status="greed", sentiment_zone="greed",
            interpretation="Sentiment in greed (fixture).",
            macro_implication="Risk appetite strong, but greed implies crowding.",
            horizon_implication="Crowding caution — prefer pullback entries for new risk.",
            crowding_implication="Greed → elevated crowding risk; not a buy signal.",
            ev="ron_fg",
        ),
        index_leadership=[
            _index_signal(
                key="qqq", symbol="QQQ", display_name="QQQ (Nasdaq-100)",
                leadership_role="large_cap_growth", trend="rising", signal="supportive",
                value="uptrend above rising 50DMA (placeholder)", status="leading",
                interpretation="Large-cap tech / AI leadership strong (fixture).",
                macro_implication="Growth / AI risk appetite healthy.",
                horizon_implication="Supports short-term momentum in the AI complex.",
                breadth_implication="Leadership concentrated in mega-cap (narrow proxy).",
                ev="ron_qqq",
            ),
            _index_signal(
                key="iwm", symbol="IWM", display_name="IWM (Russell 2000)",
                leadership_role="small_cap", trend="improving", signal="supportive",
                value="breaking higher; breadth improving (placeholder)", status="participating",
                interpretation="Small-caps participating (fixture).",
                macro_implication="Broadening risk appetite.",
                horizon_implication="Improving breadth supports broader momentum.",
                breadth_implication="Broadening participation is a healthy confirm.",
                ev="ron_iwm",
            ),
        ],
        labor_releases=[
            _labor_signal(
                trend="rising", signal="mixed", value="+220k (placeholder)",
                status="resilient", surprise_direction="above_expectations",
                labor_strength="strong",
                interpretation="Labor market resilient (fixture).",
                macro_implication="Growth resilient; some Fed-reaction / overheating risk.",
                horizon_implication="Watch for hawkish repricing on hot prints.",
                fed_reaction_risk="Strong prints can delay cuts (placeholder).",
                ev="ron_nfp",
            ),
        ],
        inflation_releases=[
            _inflation_signal(
                key="cpi", display_name="CPI", release_name="Consumer Price Index",
                pipeline_stage="consumer", trend="falling", signal="supportive",
                value="cooling toward target (placeholder)", status="disinflating",
                surprise_direction="in_line",
                interpretation="Disinflation continuing (fixture).",
                macro_implication="Eases rates pressure; supports long-duration growth valuations.",
                horizon_implication="Supportive for growth multiples.",
                pass_through_risk="n/a — consumer-stage release.",
                ev="ron_cpi",
            ),
            _inflation_signal(
                key="ppi", display_name="PPI", release_name="Producer Price Index",
                pipeline_stage="producer", trend="falling", signal="supportive",
                value="soft; limited pipeline pressure (placeholder)", status="muted",
                surprise_direction="in_line",
                interpretation="Pipeline inflation muted (fixture).",
                macro_implication="Limited future CPI pass-through; margin pressure easing.",
                horizon_implication="Supportive for margins.",
                pass_through_risk="Low pass-through to CPI (placeholder).",
                ev="ron_ppi",
            ),
        ],
        overall_signal="supportive",
        summary=(
            "Risk-on indicators: strong QQQ leadership + broadening IWM, greed "
            "(crowding caution), disinflation (CPI/PPI), resilient labor with "
            "mild Fed-reaction risk; oil/gold firm."
        ),
    )


def _build_indicator_panel_risk_off() -> MacroIndicatorPanel:
    """Risk-off indicator panel: weak leadership, fear, defensive macro."""
    return MacroIndicatorPanel(
        commodities=[
            _commodity_signal(
                key="wti", symbol="WTI", display_name="WTI Crude Oil",
                commodity_type="wti_crude", trend="falling", signal="headwind",
                value="~$68/bbl; demand fears (placeholder)", status="weak",
                interpretation="Crude weak on demand fears (fixture).",
                macro_implication="Signals growth slowdown; disinflationary but demand-negative.",
                horizon_implication="Cyclical weakness; defensive tilt.",
                inflation_sensitivity="Falling oil eases headline inflation (placeholder).",
                growth_sensitivity="Demand-driven weakness is a growth warning (placeholder).",
                ev="roff_wti",
            ),
            _commodity_signal(
                key="gold", symbol="GC", display_name="Gold (GC)",
                commodity_type="gold", trend="rising", signal="supportive",
                value="bid as safe haven (placeholder)", status="haven_bid",
                interpretation="Gold bid on risk-off / safe-haven demand (fixture).",
                macro_implication="Safe-haven demand; risk-off proxy.",
                horizon_implication="Defensive diversifier in risk-off.",
                inflation_sensitivity="Hedge demand (placeholder).",
                growth_sensitivity="Counter-cyclical haven (placeholder).",
                ev="roff_gold",
            ),
        ],
        fear_greed=_fear_greed_signal(
            trend="falling", signal="headwind", value="22 / Fear (placeholder)",
            status="fear", sentiment_zone="fear",
            interpretation="Sentiment in fear (fixture).",
            macro_implication="Risk-off; possible contrarian watchlist context.",
            horizon_implication="Watchlist / research_more; contrarian only with confirmation.",
            crowding_implication="Fear → de-risking; contrarian watch, not a buy.",
            ev="roff_fg",
        ),
        index_leadership=[
            _index_signal(
                key="qqq", symbol="QQQ", display_name="QQQ (Nasdaq-100)",
                leadership_role="large_cap_growth", trend="deteriorating", signal="headwind",
                value="below 50DMA; leadership breaking (placeholder)", status="weakening",
                interpretation="Large-cap tech / AI leadership breaking down (fixture).",
                macro_implication="Growth / AI risk appetite deteriorating.",
                horizon_implication="Avoid chasing; watchlist only.",
                breadth_implication="Leadership breaking down.",
                ev="roff_qqq",
            ),
            _index_signal(
                key="iwm", symbol="IWM", display_name="IWM (Russell 2000)",
                leadership_role="small_cap", trend="deteriorating", signal="headwind",
                value="lagging; breadth poor (placeholder)", status="lagging",
                interpretation="Small-caps underperforming (fixture).",
                macro_implication="Weak breadth confirms risk-off.",
                horizon_implication="Risk reduction.",
                breadth_implication="Narrow / poor breadth.",
                ev="roff_iwm",
            ),
        ],
        labor_releases=[
            _labor_signal(
                trend="falling", signal="headwind", value="+80k; slowing (placeholder)",
                status="cooling", surprise_direction="below_expectations",
                labor_strength="weak",
                interpretation="Labor cooling (fixture).",
                macro_implication="Growth slowdown / recession risk rising.",
                horizon_implication="Defensive posture.",
                fed_reaction_risk="Weak prints raise hard-landing risk (placeholder).",
                ev="roff_nfp",
            ),
        ],
        inflation_releases=[
            _inflation_signal(
                key="cpi", display_name="CPI", release_name="Consumer Price Index",
                pipeline_stage="consumer", trend="rising", signal="headwind",
                value="sticky / above expectations (placeholder)", status="sticky",
                surprise_direction="above_expectations",
                interpretation="Inflation sticky (fixture).",
                macro_implication="Keeps policy tight; pressures long-duration valuations.",
                horizon_implication="Headwind for growth multiples.",
                pass_through_risk="n/a — consumer-stage release.",
                ev="roff_cpi",
            ),
            _inflation_signal(
                key="ppi", display_name="PPI", release_name="Producer Price Index",
                pipeline_stage="producer", trend="rising", signal="headwind",
                value="firming pipeline (placeholder)", status="firming",
                surprise_direction="above_expectations",
                interpretation="Pipeline inflation firming (fixture).",
                macro_implication="Future CPI pass-through risk; margin pressure.",
                horizon_implication="Margin headwind.",
                pass_through_risk="Elevated pass-through to CPI (placeholder).",
                ev="roff_ppi",
            ),
        ],
        overall_signal="headwind",
        summary=(
            "Risk-off indicators: QQQ/IWM weakening (poor breadth), fear, gold "
            "haven bid + weak oil (demand fears), cooling labor, sticky/firming "
            "CPI/PPI (tight policy)."
        ),
    )


def _build_indicator_panel_transition() -> MacroIndicatorPanel:
    """Transition indicator panel: mixed / unconfirmed signals."""
    return MacroIndicatorPanel(
        commodities=[
            _commodity_signal(
                key="wti", symbol="WTI", display_name="WTI Crude Oil",
                commodity_type="wti_crude", trend="mixed", signal="mixed",
                value="range-bound (placeholder)", status="range_bound",
                interpretation="Crude range-bound (fixture).",
                macro_implication="Neither clear inflation nor demand signal.",
                horizon_implication="Not the swing factor right now.",
                inflation_sensitivity="Neutral on inflation (placeholder).",
                growth_sensitivity="Neutral on growth (placeholder).",
                ev="trn_wti",
            ),
            _commodity_signal(
                key="gold", symbol="GC", display_name="Gold (GC)",
                commodity_type="gold", trend="rising", signal="mixed",
                value="firm; hedge demand (placeholder)", status="firm",
                interpretation="Gold firm on hedge demand (fixture).",
                macro_implication="Some hedging into uncertainty.",
                horizon_implication="Diversifier while signals resolve.",
                inflation_sensitivity="Hedge demand (placeholder).",
                growth_sensitivity="Low (placeholder).",
                ev="trn_gold",
            ),
        ],
        fear_greed=_fear_greed_signal(
            trend="mixed", signal="neutral", value="50 / Neutral (placeholder)",
            status="neutral", sentiment_zone="neutral",
            interpretation="Sentiment neutral (fixture).",
            macro_implication="No sentiment extreme to lean on.",
            horizon_implication="Prefer pullback entries; wait for confirmation.",
            crowding_implication="Neutral — neither crowded nor capitulated.",
            ev="trn_fg",
        ),
        index_leadership=[
            _index_signal(
                key="qqq", symbol="QQQ", display_name="QQQ (Nasdaq-100)",
                leadership_role="large_cap_growth", trend="mixed", signal="mixed",
                value="overextended; choppy (placeholder)", status="choppy",
                interpretation="Large-cap leadership overextended / choppy (fixture).",
                macro_implication="Risk appetite present but fragile.",
                horizon_implication="Buy pullbacks rather than chase.",
                breadth_implication="Narrow leadership.",
                ev="trn_qqq",
            ),
            _index_signal(
                key="iwm", symbol="IWM", display_name="IWM (Russell 2000)",
                leadership_role="small_cap", trend="mixed", signal="mixed",
                value="lagging QQQ; breadth unconfirmed (placeholder)", status="unconfirmed",
                interpretation="Small-caps not yet confirming (fixture).",
                macro_implication="Breadth not broadening yet.",
                horizon_implication="Wait for broadening or pullbacks.",
                breadth_implication="Breadth unconfirmed.",
                ev="trn_iwm",
            ),
        ],
        labor_releases=[
            _labor_signal(
                trend="stable", signal="mixed", value="+150k (placeholder)",
                status="moderate", surprise_direction="in_line",
                labor_strength="moderate",
                interpretation="Labor moderate (fixture).",
                macro_implication="Cooling but not breaking; late-cycle.",
                horizon_implication="Direction unsettled.",
                fed_reaction_risk="Two-sided Fed reaction risk (placeholder).",
                ev="trn_nfp",
            ),
        ],
        inflation_releases=[
            _inflation_signal(
                key="cpi", display_name="CPI", release_name="Consumer Price Index",
                pipeline_stage="consumer", trend="mixed", signal="mixed",
                value="disinflation stalling (placeholder)", status="stalling",
                surprise_direction="in_line",
                interpretation="Disinflation stalling (fixture).",
                macro_implication="Inflation path uncertain.",
                horizon_implication="Rates path two-sided.",
                pass_through_risk="n/a — consumer-stage release.",
                ev="trn_cpi",
            ),
            _inflation_signal(
                key="ppi", display_name="PPI", release_name="Producer Price Index",
                pipeline_stage="producer", trend="mixed", signal="mixed",
                value="mixed (placeholder)", status="mixed",
                surprise_direction="in_line",
                interpretation="Pipeline inflation mixed (fixture).",
                macro_implication="No clear pass-through signal.",
                horizon_implication="Margin path unsettled.",
                pass_through_risk="Uncertain pass-through (placeholder).",
                ev="trn_ppi",
            ),
        ],
        overall_signal="mixed",
        summary=(
            "Transition indicators: overextended QQQ with unconfirmed IWM "
            "breadth, neutral sentiment, stalling disinflation, moderate labor "
            "— mixed signals favor pullback entries."
        ),
    )


def _build_indicator_panel_degraded() -> MacroIndicatorPanel:
    """Degraded indicator panel: a few unknown indicators + missing rest.

    Demonstrates fail-soft behavior — present indicators are ``unknown`` with
    warnings; several required indicators are deliberately absent so the
    validator reports them as ``missing_indicators`` (nothing fabricated).
    """
    _w = [
        MacroRiskWarning(
            warning_type="degraded_data",
            severity="high",
            message="Indicator data unavailable in this degraded fixture.",
        )
    ]
    return MacroIndicatorPanel(
        commodities=[
            _commodity_signal(
                key="wti", symbol="WTI", display_name="WTI Crude Oil",
                commodity_type="unknown", trend="unknown", signal="unknown",
                value=None, status="unknown",
                interpretation="WTI data unavailable (degraded fixture).",
                macro_implication="Unknown — do not infer.",
                horizon_implication="Unknown.",
                inflation_sensitivity="Unknown (placeholder).",
                growth_sensitivity="Unknown (placeholder).",
                ev="deg_wti", warnings=_w,
            ),
        ],
        fear_greed=_fear_greed_signal(
            trend="unknown", signal="unknown", value=None, status="unknown",
            sentiment_zone="unknown",
            interpretation="Fear & Greed data unavailable (degraded fixture).",
            macro_implication="Unknown — do not infer sentiment.",
            horizon_implication="Unknown.",
            crowding_implication="Unknown.",
            ev="deg_fg", warnings=_w,
        ),
        index_leadership=[],
        labor_releases=[
            _labor_signal(
                trend="unknown", signal="unknown", value=None, status="unknown",
                surprise_direction="unknown", labor_strength="unknown",
                interpretation="NFP data unavailable (degraded fixture).",
                macro_implication="Unknown — do not infer labor strength.",
                horizon_implication="Unknown.",
                fed_reaction_risk="Unknown (placeholder).",
                ev="deg_nfp", warnings=_w,
            ),
        ],
        inflation_releases=[],
        overall_signal="unknown",
        summary=(
            "Degraded indicators: WTI / Fear & Greed / NFP present but unknown; "
            "gold, QQQ, IWM, CPI, PPI missing. Nothing fabricated."
        ),
    )


# ---------------------------------------------------------------------------
# Fixtures — deterministic examples only (NOT live market claims)
# ---------------------------------------------------------------------------


def _default_theme_implications() -> list[MacroThemeImplicationView]:
    """Deterministic risk-on theme implications (fixture examples only)."""
    return [
        MacroThemeImplicationView(
            theme_name="AI infrastructure",
            implication="tailwind",
            rationale=(
                "Expanding liquidity + positive earnings revisions support "
                "long-duration AI capex (fixture example, not a live claim)."
            ),
            evidence_refs=[_ev("ai_infra_tailwind")],
        ),
        MacroThemeImplicationView(
            theme_name="Data-center power",
            implication="tailwind",
            rationale="Capex cycle backdrop supports power/cooling (fixture).",
            evidence_refs=[_ev("dc_power_tailwind")],
        ),
        MacroThemeImplicationView(
            theme_name="Memory / HBM",
            implication="tailwind",
            rationale="Cyclical upswing + AI demand (fixture example).",
        ),
        MacroThemeImplicationView(
            theme_name="Optical networking",
            implication="tailwind",
            rationale="Second-derivative AI build-out beneficiary (fixture).",
        ),
        MacroThemeImplicationView(
            theme_name="Space",
            implication="neutral",
            rationale="Narrative-driven; less macro-sensitive (fixture).",
        ),
        MacroThemeImplicationView(
            theme_name="Embodied AI / robotics",
            implication="neutral",
            rationale="Early-stage; macro is not the swing factor yet (fixture).",
        ),
        MacroThemeImplicationView(
            theme_name="Biotech",
            implication="mixed",
            rationale=(
                "Rate-sensitive long-duration cash flows; improving liquidity "
                "helps but policy risk is a swing factor (fixture)."
            ),
        ),
        MacroThemeImplicationView(
            theme_name="Nuclear / energy",
            implication="tailwind",
            rationale="Power-demand + policy support backdrop (fixture).",
        ),
    ]


def build_risk_on_macro_dashboard_view() -> MacroDashboardView:
    """Risk-on regime: momentum allowed but crowding caution.

    Improving breadth and expanding liquidity support short-term momentum;
    elevated valuations and rising volatility argue for crowding caution.
    """
    regime_status = MacroRegimeStatus(
        primary_status="risk_on",
        supporting_statuses=["liquidity_expanding", "earnings_revision_positive"],
        label="Risk-on / liquidity expanding",
        description=(
            "Risk-on regime with expanding liquidity and positive earnings "
            "revisions; breadth improving but leadership extended (fixture)."
        ),
        confidence="moderate",
    )
    rates = build_macro_factor_view(
        factor="rates",
        label="Policy & long-end rates",
        trend="stable",
        signal="supportive",
        value_placeholder="policy rate plateauing; long end stable (placeholder)",
        description="Rates no longer a headwind for duration (fixture).",
        evidence_label="ron_rates",
    )
    inflation = build_macro_factor_view(
        factor="inflation",
        label="Inflation",
        trend="falling",
        signal="supportive",
        value_placeholder="disinflation continuing (placeholder)",
        description="Cooling inflation supports multiples (fixture).",
        evidence_label="ron_infl",
    )
    liquidity = build_macro_factor_view(
        factor="liquidity",
        label="Liquidity",
        trend="expanding",
        signal="supportive",
        value_placeholder="net liquidity rising (placeholder)",
        description="Expanding liquidity supports risk assets (fixture).",
        evidence_label="ron_liq",
    )
    credit = build_macro_factor_view(
        factor="credit_spreads",
        label="Credit spreads",
        trend="narrowing",
        signal="supportive",
        value_placeholder="IG/HY spreads tight (placeholder)",
        description="Tight credit signals risk appetite (fixture).",
        evidence_label="ron_credit",
    )
    volatility = build_macro_factor_view(
        factor="volatility",
        label="Volatility (VIX)",
        trend="rising",
        signal="headwind",
        value_placeholder="VIX low but ticking up (placeholder)",
        description="Low but rising vol — crowding caution (fixture).",
        evidence_label="ron_vix",
    )
    breadth = build_macro_factor_view(
        factor="market_breadth",
        label="Market breadth",
        trend="improving",
        signal="supportive",
        value_placeholder="participation broadening (placeholder)",
        description="Improving breadth supports momentum (fixture).",
        evidence_label="ron_breadth",
    )
    dollar = build_macro_factor_view(
        factor="dollar",
        label="US dollar",
        trend="falling",
        signal="supportive",
        value_placeholder="DXY softening (placeholder)",
        description="Softer dollar is risk-supportive (fixture).",
        evidence_label="ron_dxy",
    )
    risk_appetite = build_macro_factor_view(
        factor="risk_appetite",
        label="Risk appetite",
        trend="improving",
        signal="supportive",
        value_placeholder="risk-on positioning (placeholder)",
        description="Broad risk appetite but increasingly crowded (fixture).",
        evidence_label="ron_risk",
    )
    earnings = build_macro_factor_view(
        factor="earnings_cycle",
        label="Earnings cycle",
        trend="improving",
        signal="supportive",
        value_placeholder="revisions positive (placeholder)",
        description="Positive earnings revisions (fixture).",
        evidence_label="ron_earn",
    )
    growth = build_macro_factor_view(
        factor="growth_regime",
        label="Growth / recession regime",
        trend="improving",
        signal="supportive",
        value_placeholder="soft-landing / re-acceleration (placeholder)",
        description="Growth holding up; recession risk low (fixture).",
        evidence_label="ron_growth",
    )
    policy = build_macro_factor_view(
        factor="policy_risk",
        label="Policy risk",
        trend="stable",
        signal="neutral",
        value_placeholder="policy mix neutral (placeholder)",
        description="No imminent policy shock priced (fixture).",
        evidence_label="ron_policy",
    )

    snapshot = _assemble_snapshot(
        as_of=SAMPLE_MACRO_AS_OF,
        regime_status=regime_status,
        rates=rates,
        inflation=inflation,
        liquidity=liquidity,
        credit=credit,
        volatility=volatility,
        breadth=breadth,
        dollar=dollar,
        risk_appetite=risk_appetite,
        earnings=earnings,
        growth=growth,
        policy=policy,
        rates_inflation_signal="supportive",
        rates_inflation_summary="Disinflation + stable rates support multiples.",
        liquidity_signal="supportive",
        liquidity_summary="Expanding liquidity is the dominant tailwind.",
        credit_vol_signal="mixed",
        credit_vol_summary="Tight credit, but low-and-rising vol warns on crowding.",
        breadth_signal="supportive",
        breadth_summary="Breadth broadening supports momentum entries.",
        dollar_signal="supportive",
        dollar_summary="Softer dollar is risk-supportive.",
        risk_state="risk_on",
        risk_signal="supportive",
        risk_summary="Risk-on, but leadership extended — watch crowding.",
        revision_direction="positive",
        earnings_signal="supportive",
        earnings_summary="Positive earnings revisions confirm the regime.",
        policy_signal="neutral",
        policy_summary="Policy backdrop neutral; no imminent shock priced.",
        notes="Risk-on fixture: momentum allowed with crowding caution.",
    )

    horizon_bias = MacroHorizonBiasView(
        short_term_bias="favor_momentum_trades",
        mid_term_bias="favor_pullback_entries",
        long_term_bias="favor_long_term_accumulation",
        short_term_rationale=(
            "Risk-on + improving breadth supports short-term momentum."
        ),
        mid_term_rationale=(
            "Leadership extended / volatility rising — prefer pullback entries "
            "for new mid-term positions."
        ),
        long_term_rationale=(
            "Expanding liquidity supports long-term accumulation candidates."
        ),
        notes="Same regime can favor momentum short-term and accumulation long-term.",
    )
    posture = MacroOpportunityPostureView(
        primary_posture="favor_momentum_trades",
        secondary_postures=["favor_pullback_entries", "favor_long_term_accumulation"],
        rationale=(
            "Risk-on regime favors momentum, but crowding caution argues for "
            "pullback entries on extended leaders. Review-only context — not a "
            "buy signal and not a trade instruction."
        ),
    )

    view = MacroDashboardView(
        dashboard_id=make_macro_dashboard_id("risk_on"),
        as_of=SAMPLE_MACRO_AS_OF,
        scenario_kind="risk_on",
        title="Macro Dashboard — Risk-on (fixture)",
        indicator_panel=_build_indicator_panel_risk_on(),
        description=(
            "Deterministic risk-on macro fixture: expanding liquidity, positive "
            "earnings revisions, improving breadth, with crowding caution."
        ),
        regime_snapshot=snapshot,
        horizon_bias=horizon_bias,
        opportunity_posture=posture,
        theme_implications=_default_theme_implications(),
        warnings=[
            MacroRiskWarning(
                warning_type="crowding",
                severity="medium",
                message=(
                    "Risk-on but leadership extended; high regime conviction is "
                    "context, not a buy signal."
                ),
            ),
        ],
    )
    return attach_macro_dashboard_validation_summary(view)


def build_risk_off_macro_dashboard_view() -> MacroDashboardView:
    """Risk-off regime: watchlist / research_more posture."""
    regime_status = MacroRegimeStatus(
        primary_status="risk_off",
        supporting_statuses=["liquidity_tightening", "growth_slowdown"],
        label="Risk-off / liquidity tightening",
        description=(
            "Risk-off regime with tightening liquidity, widening credit, rising "
            "volatility, and deteriorating breadth (fixture)."
        ),
        confidence="moderate",
    )
    rates = build_macro_factor_view(
        factor="rates",
        label="Policy & long-end rates",
        trend="rising",
        signal="headwind",
        value_placeholder="rates rising / restrictive (placeholder)",
        description="Restrictive rates pressure long-duration (fixture).",
        evidence_label="roff_rates",
    )
    inflation = build_macro_factor_view(
        factor="inflation",
        label="Inflation",
        trend="rising",
        signal="headwind",
        value_placeholder="sticky inflation (placeholder)",
        description="Sticky inflation keeps policy tight (fixture).",
        evidence_label="roff_infl",
    )
    liquidity = build_macro_factor_view(
        factor="liquidity",
        label="Liquidity",
        trend="tightening",
        signal="headwind",
        value_placeholder="net liquidity falling (placeholder)",
        description="Tightening liquidity penalizes risk (fixture).",
        evidence_label="roff_liq",
    )
    credit = build_macro_factor_view(
        factor="credit_spreads",
        label="Credit spreads",
        trend="widening",
        signal="headwind",
        value_placeholder="HY spreads widening (placeholder)",
        description="Widening credit signals stress (fixture).",
        evidence_label="roff_credit",
    )
    volatility = build_macro_factor_view(
        factor="volatility",
        label="Volatility (VIX)",
        trend="rising",
        signal="headwind",
        value_placeholder="VIX elevated (placeholder)",
        description="Elevated volatility argues for risk reduction (fixture).",
        evidence_label="roff_vix",
    )
    breadth = build_macro_factor_view(
        factor="market_breadth",
        label="Market breadth",
        trend="deteriorating",
        signal="headwind",
        value_placeholder="narrowing participation (placeholder)",
        description="Deteriorating breadth (fixture).",
        evidence_label="roff_breadth",
    )
    dollar = build_macro_factor_view(
        factor="dollar",
        label="US dollar",
        trend="rising",
        signal="headwind",
        value_placeholder="DXY rising (placeholder)",
        description="Strong dollar tightens financial conditions (fixture).",
        evidence_label="roff_dxy",
    )
    risk_appetite = build_macro_factor_view(
        factor="risk_appetite",
        label="Risk appetite",
        trend="deteriorating",
        signal="headwind",
        value_placeholder="risk-off positioning (placeholder)",
        description="Defensive positioning (fixture).",
        evidence_label="roff_risk",
    )
    earnings = build_macro_factor_view(
        factor="earnings_cycle",
        label="Earnings cycle",
        trend="deteriorating",
        signal="headwind",
        value_placeholder="revisions negative (placeholder)",
        description="Negative earnings revisions (fixture).",
        evidence_label="roff_earn",
    )
    growth = build_macro_factor_view(
        factor="growth_regime",
        label="Growth / recession regime",
        trend="deteriorating",
        signal="headwind",
        value_placeholder="growth slowdown / recession risk rising (placeholder)",
        description="Rising recession risk (fixture).",
        evidence_label="roff_growth",
    )
    policy = build_macro_factor_view(
        factor="policy_risk",
        label="Policy risk",
        trend="rising",
        signal="headwind",
        value_placeholder="policy uncertainty elevated (placeholder)",
        description="Elevated policy uncertainty (fixture).",
        evidence_label="roff_policy",
    )

    snapshot = _assemble_snapshot(
        as_of=SAMPLE_MACRO_AS_OF,
        regime_status=regime_status,
        rates=rates,
        inflation=inflation,
        liquidity=liquidity,
        credit=credit,
        volatility=volatility,
        breadth=breadth,
        dollar=dollar,
        risk_appetite=risk_appetite,
        earnings=earnings,
        growth=growth,
        policy=policy,
        rates_inflation_signal="headwind",
        rates_inflation_summary="Sticky inflation + restrictive rates are headwinds.",
        liquidity_signal="headwind",
        liquidity_summary="Tightening liquidity penalizes long-duration growth.",
        credit_vol_signal="headwind",
        credit_vol_summary="Widening credit and elevated vol argue for caution.",
        breadth_signal="headwind",
        breadth_summary="Breadth deteriorating — momentum entries discouraged.",
        dollar_signal="headwind",
        dollar_summary="Strong dollar tightens conditions.",
        risk_state="risk_off",
        risk_signal="headwind",
        risk_summary="Risk-off — favor watchlist / research_more posture.",
        revision_direction="negative",
        earnings_signal="headwind",
        earnings_summary="Negative earnings revisions confirm the slowdown.",
        policy_signal="headwind",
        policy_summary="Elevated policy uncertainty.",
        notes="Risk-off fixture: watchlist / research_more posture.",
    )

    horizon_bias = MacroHorizonBiasView(
        short_term_bias="favor_watchlist_only",
        mid_term_bias="favor_risk_reduction",
        long_term_bias="research_more",
        short_term_rationale=(
            "Risk-off pushes short-term candidates to watchlist only."
        ),
        mid_term_rationale=(
            "Deteriorating regime argues for risk reduction over new entries."
        ),
        long_term_rationale=(
            "Tightening liquidity / rising rates penalize long-duration entry "
            "quality — research more before accumulating."
        ),
        notes="Risk-off: capital preservation precedes opportunity-seeking.",
    )
    posture = MacroOpportunityPostureView(
        primary_posture="favor_watchlist_only",
        secondary_postures=["favor_risk_reduction", "research_more"],
        rationale=(
            "Risk-off regime favors watchlist-only / risk reduction. Review-only "
            "context — not a sell signal and not a trade instruction."
        ),
    )

    view = MacroDashboardView(
        dashboard_id=make_macro_dashboard_id("risk_off"),
        as_of=SAMPLE_MACRO_AS_OF,
        scenario_kind="risk_off",
        title="Macro Dashboard — Risk-off (fixture)",
        indicator_panel=_build_indicator_panel_risk_off(),
        description=(
            "Deterministic risk-off macro fixture: tightening liquidity, widening "
            "credit, rising volatility, deteriorating breadth."
        ),
        regime_snapshot=snapshot,
        horizon_bias=horizon_bias,
        opportunity_posture=posture,
        theme_implications=[
            MacroThemeImplicationView(
                theme_name="AI infrastructure",
                implication="headwind",
                rationale=(
                    "Tightening liquidity / rising rates penalize long-duration "
                    "growth entry quality (fixture)."
                ),
            ),
            MacroThemeImplicationView(
                theme_name="Biotech",
                implication="headwind",
                rationale="Rate-sensitive long-duration cash flows (fixture).",
            ),
            MacroThemeImplicationView(
                theme_name="Nuclear / energy",
                implication="neutral",
                rationale="Defensive-ish cash flows; less risk-on dependent (fixture).",
            ),
            MacroThemeImplicationView(
                theme_name="Memory / HBM",
                implication="headwind",
                rationale="Cyclical; vulnerable in a slowdown (fixture).",
            ),
            MacroThemeImplicationView(
                theme_name="Space",
                implication="headwind",
                rationale="Speculative names hit hardest in risk-off (fixture).",
            ),
        ],
        warnings=[
            MacroRiskWarning(
                warning_type="liquidity_tightening",
                severity="high",
                message=(
                    "Tightening liquidity / rising rates penalize long-duration "
                    "growth entry quality."
                ),
            ),
        ],
    )
    return attach_macro_dashboard_validation_summary(view)


def build_transition_macro_dashboard_view() -> MacroDashboardView:
    """Transition regime: pullback-entry preference."""
    regime_status = MacroRegimeStatus(
        primary_status="transition",
        supporting_statuses=["earnings_revision_positive"],
        label="Transition / mixed signals",
        description=(
            "Transition regime: improving earnings but stretched leadership and "
            "rising volatility — mixed signals favor pullback entries (fixture)."
        ),
        confidence="low",
    )
    rates = build_macro_factor_view(
        factor="rates",
        label="Policy & long-end rates",
        trend="stable",
        signal="neutral",
        value_placeholder="rates range-bound (placeholder)",
        description="Rates neither tailwind nor headwind (fixture).",
        evidence_label="trn_rates",
    )
    inflation = build_macro_factor_view(
        factor="inflation",
        label="Inflation",
        trend="mixed",
        signal="mixed",
        value_placeholder="disinflation stalling (placeholder)",
        description="Inflation path uncertain (fixture).",
        evidence_label="trn_infl",
    )
    liquidity = build_macro_factor_view(
        factor="liquidity",
        label="Liquidity",
        trend="stable",
        signal="neutral",
        value_placeholder="liquidity flat (placeholder)",
        description="Liquidity neither expanding nor tightening (fixture).",
        evidence_label="trn_liq",
    )
    credit = build_macro_factor_view(
        factor="credit_spreads",
        label="Credit spreads",
        trend="stable",
        signal="neutral",
        value_placeholder="spreads range-bound (placeholder)",
        description="Credit calm but not improving (fixture).",
        evidence_label="trn_credit",
    )
    volatility = build_macro_factor_view(
        factor="volatility",
        label="Volatility (VIX)",
        trend="rising",
        signal="headwind",
        value_placeholder="vol creeping up (placeholder)",
        description="Rising vol argues for pullback entries (fixture).",
        evidence_label="trn_vix",
    )
    breadth = build_macro_factor_view(
        factor="market_breadth",
        label="Market breadth",
        trend="mixed",
        signal="mixed",
        value_placeholder="narrow leadership (placeholder)",
        description="Leadership narrow / overextended (fixture).",
        evidence_label="trn_breadth",
    )
    dollar = build_macro_factor_view(
        factor="dollar",
        label="US dollar",
        trend="stable",
        signal="neutral",
        value_placeholder="DXY range-bound (placeholder)",
        description="Dollar neutral (fixture).",
        evidence_label="trn_dxy",
    )
    risk_appetite = build_macro_factor_view(
        factor="risk_appetite",
        label="Risk appetite",
        trend="mixed",
        signal="mixed",
        value_placeholder="cautious risk-on (placeholder)",
        description="Risk appetite present but fragile (fixture).",
        evidence_label="trn_risk",
    )
    earnings = build_macro_factor_view(
        factor="earnings_cycle",
        label="Earnings cycle",
        trend="improving",
        signal="supportive",
        value_placeholder="revisions turning positive (placeholder)",
        description="Earnings improving — a supportive crosscurrent (fixture).",
        evidence_label="trn_earn",
    )
    growth = build_macro_factor_view(
        factor="growth_regime",
        label="Growth / recession regime",
        trend="mixed",
        signal="mixed",
        value_placeholder="late-cycle expansion (placeholder)",
        description="Late-cycle; direction unsettled (fixture).",
        evidence_label="trn_growth",
    )
    policy = build_macro_factor_view(
        factor="policy_risk",
        label="Policy risk",
        trend="stable",
        signal="neutral",
        value_placeholder="policy pivot watched (placeholder)",
        description="Markets await policy direction (fixture).",
        evidence_label="trn_policy",
    )

    snapshot = _assemble_snapshot(
        as_of=SAMPLE_MACRO_AS_OF,
        regime_status=regime_status,
        rates=rates,
        inflation=inflation,
        liquidity=liquidity,
        credit=credit,
        volatility=volatility,
        breadth=breadth,
        dollar=dollar,
        risk_appetite=risk_appetite,
        earnings=earnings,
        growth=growth,
        policy=policy,
        rates_inflation_signal="mixed",
        rates_inflation_summary="Rates range-bound; inflation path uncertain.",
        liquidity_signal="neutral",
        liquidity_summary="Liquidity flat — not the swing factor right now.",
        credit_vol_signal="mixed",
        credit_vol_summary="Credit calm but rising vol favors pullback entries.",
        breadth_signal="mixed",
        breadth_summary="Narrow leadership — wait for broadening or pullbacks.",
        dollar_signal="neutral",
        dollar_summary="Dollar neutral.",
        risk_state="transition",
        risk_signal="mixed",
        risk_summary="Cautious risk-on; prefer pullback entries.",
        revision_direction="positive",
        earnings_signal="supportive",
        earnings_summary="Improving earnings is the supportive crosscurrent.",
        policy_signal="neutral",
        policy_summary="Policy direction awaited.",
        notes="Transition fixture: pullback-entry preference.",
    )

    horizon_bias = MacroHorizonBiasView(
        short_term_bias="favor_pullback_entries",
        mid_term_bias="favor_pullback_entries",
        long_term_bias="favor_long_term_accumulation",
        short_term_rationale=(
            "Risk-on but overextended / volatility rising — prefer pullback "
            "entries over chasing momentum."
        ),
        mid_term_rationale="Wait for breadth to broaden or for pullbacks.",
        long_term_rationale=(
            "Improving earnings supports gradual long-term accumulation."
        ),
        notes="Transition: pullback entries preferred while signals resolve.",
    )
    posture = MacroOpportunityPostureView(
        primary_posture="favor_pullback_entries",
        secondary_postures=["research_more", "favor_long_term_accumulation"],
        rationale=(
            "Mixed/transition regime favors pullback entries and more research "
            "before adding risk. Review-only context — not a trade instruction."
        ),
    )

    view = MacroDashboardView(
        dashboard_id=make_macro_dashboard_id("transition"),
        as_of=SAMPLE_MACRO_AS_OF,
        scenario_kind="transition",
        title="Macro Dashboard — Transition (fixture)",
        indicator_panel=_build_indicator_panel_transition(),
        description=(
            "Deterministic transition macro fixture: improving earnings but "
            "overextended leadership and rising volatility favor pullback entries."
        ),
        regime_snapshot=snapshot,
        horizon_bias=horizon_bias,
        opportunity_posture=posture,
        theme_implications=[
            MacroThemeImplicationView(
                theme_name="AI infrastructure",
                implication="mixed",
                rationale="Supportive earnings but overextended — buy pullbacks (fixture).",
            ),
            MacroThemeImplicationView(
                theme_name="Data-center power",
                implication="tailwind",
                rationale="Structural capex less sensitive to the transition (fixture).",
            ),
            MacroThemeImplicationView(
                theme_name="Memory / HBM",
                implication="mixed",
                rationale="Cyclical; wait for confirmation (fixture).",
            ),
            MacroThemeImplicationView(
                theme_name="Biotech",
                implication="neutral",
                rationale="Idiosyncratic drivers dominate in transition (fixture).",
            ),
            MacroThemeImplicationView(
                theme_name="Space",
                implication="neutral",
                rationale="Narrative-driven; macro-neutral here (fixture).",
            ),
        ],
        warnings=[
            MacroRiskWarning(
                warning_type="conflicting_signals",
                severity="medium",
                message=(
                    "Transition regime: conflicting signals — prefer pullback "
                    "entries over momentum chasing."
                ),
            ),
            MacroRiskWarning(
                warning_type="late_cycle",
                severity="low",
                message="Late-cycle dynamics; growth direction unsettled.",
            ),
        ],
    )
    return attach_macro_dashboard_validation_summary(view)


def build_degraded_macro_dashboard_view() -> MacroDashboardView:
    """Degraded / unknown macro state.

    Demonstrates fail-soft behavior: most factors are ``unknown``, several
    required factors are missing, the regime status is ``unknown``, and the
    posture is ``research_more``. Nothing is fabricated.
    """
    regime_status = MacroRegimeStatus(
        primary_status="unknown",
        supporting_statuses=[],
        label="Unknown / degraded",
        description=(
            "Degraded macro state: insufficient/missing factor data; regime "
            "status is unknown, not neutral (fixture)."
        ),
        confidence="unknown",
    )
    # Only a few factors present; several required factors deliberately missing.
    rates = build_macro_factor_view(
        factor="rates",
        label="Policy & long-end rates",
        trend="unknown",
        signal="unknown",
        description="Rates data unavailable in this degraded fixture.",
    )
    liquidity = build_macro_factor_view(
        factor="liquidity",
        label="Liquidity",
        trend="unknown",
        signal="unknown",
        description="Liquidity data unavailable in this degraded fixture.",
    )
    risk_appetite = build_macro_factor_view(
        factor="risk_appetite",
        label="Risk appetite",
        trend="unknown",
        signal="unknown",
        description="Risk appetite unknown in this degraded fixture.",
    )

    snapshot = MacroRegimeSnapshot(
        as_of=SAMPLE_MACRO_AS_OF,
        regime_status=regime_status,
        rates_inflation=MacroRatesInflationView(
            rates=rates,
            overall_signal="unknown",
            summary="Rates known; inflation missing (degraded).",
        ),
        liquidity=MacroLiquidityView(
            liquidity=liquidity,
            liquidity_trend="unknown",
            overall_signal="unknown",
            summary="Liquidity unknown (degraded).",
        ),
        risk_appetite=MacroRiskAppetiteView(
            risk_appetite=risk_appetite,
            risk_state="unknown",
            overall_signal="unknown",
            summary="Risk appetite unknown (degraded).",
        ),
        # Credit/vol, breadth, dollar, earnings, growth, policy sections left as
        # safe empty defaults; their factors are intentionally absent from the
        # flat ``factors`` list to demonstrate missing-factor handling.
        factors=[rates, liquidity, risk_appetite],
        notes="Degraded fixture: most factors unknown / missing.",
    )

    horizon_bias = MacroHorizonBiasView(
        short_term_bias="research_more",
        mid_term_bias="research_more",
        long_term_bias="research_more",
        short_term_rationale="Insufficient macro data to bias short-term posture.",
        mid_term_rationale="Insufficient macro data to bias mid-term posture.",
        long_term_rationale="Insufficient macro data to bias long-term posture.",
        notes="Degraded: do not infer a regime from missing data.",
    )
    posture = MacroOpportunityPostureView(
        primary_posture="research_more",
        secondary_postures=["unknown"],
        rationale=(
            "Macro state is degraded/unknown — research more before forming a "
            "posture. Review-only context; nothing is inferred from missing data."
        ),
    )

    view = MacroDashboardView(
        dashboard_id=make_macro_dashboard_id("degraded"),
        as_of=SAMPLE_MACRO_AS_OF,
        scenario_kind="degraded",
        title="Macro Dashboard — Degraded / Unknown (fixture)",
        indicator_panel=_build_indicator_panel_degraded(),
        description=(
            "Deterministic degraded macro fixture: missing factors, unknown "
            "regime status, research_more posture. Fail-soft, nothing fabricated."
        ),
        regime_snapshot=snapshot,
        horizon_bias=horizon_bias,
        opportunity_posture=posture,
        theme_implications=[
            MacroThemeImplicationView(
                theme_name="AI infrastructure",
                implication="unknown",
                rationale="Macro implication unknown in a degraded state (fixture).",
            ),
        ],
        warnings=[
            MacroRiskWarning(
                warning_type="degraded_data",
                severity="high",
                message=(
                    "Degraded macro state: several required factors missing; "
                    "regime status is unknown, not neutral. Do not infer."
                ),
            ),
            MacroRiskWarning(
                warning_type="missing_factor",
                severity="medium",
                message="Inflation, credit, volatility, breadth and others missing.",
            ),
        ],
    )
    return attach_macro_dashboard_validation_summary(view)


def build_default_macro_dashboard_view() -> MacroDashboardView:
    """Deterministic default macro dashboard (risk-on baseline).

    The default elevates a complete risk-on regime read with all required
    factors present. All content is a deterministic fixture example — not a live
    market claim and not investment advice.
    """
    view = build_risk_on_macro_dashboard_view()
    # Re-key the default so its id is distinct from the explicit risk-on fixture.
    view.dashboard_id = make_macro_dashboard_id("default")
    view.scenario_kind = "default"
    view.title = "Macro Dashboard — Default (risk-on baseline, fixture)"
    view.description = (
        "Default Phase 5O macro dashboard fixture (risk-on baseline). Macro is a "
        "first-class upstream input for the Investment Cockpit; review-only "
        "context, not a buy/sell decision."
    )
    return attach_macro_dashboard_validation_summary(view)


def build_empty_macro_dashboard_view() -> MacroDashboardView:
    """Deterministic, safe EMPTY dashboard (no factors, no implications)."""
    view = MacroDashboardView(
        dashboard_id=make_macro_dashboard_id("empty"),
        as_of=SAMPLE_MACRO_AS_OF,
        scenario_kind="degraded",
        title="Macro Dashboard — Empty (fixture)",
        description="Safe empty Phase 5O macro dashboard.",
        regime_snapshot=MacroRegimeSnapshot(as_of=SAMPLE_MACRO_AS_OF),
    )
    return attach_macro_dashboard_validation_summary(view)


# ---------------------------------------------------------------------------
# Scenario registry (for the additive Streamlit page selector)
# ---------------------------------------------------------------------------

# Ordered scenario kinds exposed by the page selector (default first).
MACRO_DASHBOARD_SCENARIO_ORDER: tuple[MacroScenarioKind, ...] = (
    "risk_on",
    "risk_off",
    "transition",
    "degraded",
)

_SCENARIO_BUILDERS = {
    "default": build_default_macro_dashboard_view,
    "risk_on": build_risk_on_macro_dashboard_view,
    "risk_off": build_risk_off_macro_dashboard_view,
    "transition": build_transition_macro_dashboard_view,
    "degraded": build_degraded_macro_dashboard_view,
}


def build_macro_dashboard_view_by_scenario(
    scenario_kind: MacroScenarioKind,
) -> MacroDashboardView:
    """Return the deterministic macro dashboard fixture for ``scenario_kind``.

    Falls back to the default (risk-on baseline) for an unknown kind.
    """
    builder = _SCENARIO_BUILDERS.get(scenario_kind, build_default_macro_dashboard_view)
    return builder()


def build_all_macro_dashboard_views() -> dict[str, MacroDashboardView]:
    """Build every selectable scenario view (deterministic)."""
    return {
        kind: build_macro_dashboard_view_by_scenario(kind)
        for kind in MACRO_DASHBOARD_SCENARIO_ORDER
    }
