"""
lib/reliability/phase5_opportunity_queue.py

Phase 5K: Horizon-aware Opportunity Queue ViewModel.

Purpose
-------
Convert Phase 5J Theme Intelligence / Market Heat records
(``ThemeIntelligenceSnapshot`` / ``ThemeRecord`` / ``ThemeCandidateTicker``)
into deterministic, **horizon-aware** opportunity-queue view models:

  - short-term trade candidates;
  - mid-term position candidates;
  - long-term investment candidates;
  - watch / wait;
  - research more;
  - no trade / avoid.

This is a **view-model contract layer only**. It does **not**:

- decide final trades;
- produce order instructions / order tickets / broker payloads;
- bypass the future research / debate / decision-packet phases;
- fetch any live data or call any LLM / external API;
- introduce any database / vector store / production persistence;
- introduce any broker / order / execution capability.

Product principles preserved
----------------------------
- The Investment Cockpit is **opportunity-first**, not ticker-first.
- The Opportunity Queue is **horizon-aware**, not a single ranked list.
- The **same ticker** can appear in multiple horizons with **different**
  decisions (e.g. short-term ``wait_for_pullback`` while long-term
  ``quality_but_expensive``).
- Original AI Research Workflow momentum candidates may be valid *short-term*
  candidates but still require macro, entry-quality, crowding, and evidence
  validation.
- **Strong theme heat is not enough for buy/trade.** High heat + poor entry
  quality becomes ``wait_for_pullback`` / ``too_extended`` / ``watch_wait`` /
  ``research_more`` / ``no_trade`` — never an automatic ``trade_now``.
- Mid-term and long-term candidates require stronger evidence beyond momentum.
- Final trade / allocation / option planning occurs later, after the Auto
  Research Pack + Agent Debate + Decision Packet phases.

Scoring
-------
Phase 5K defines **deterministic heuristic placeholder** scoring derived only
from Phase 5J fixture fields. The scores are NOT live-trading-valid signals.
``ThemeHeatScore`` (heat) and ``EntryQualityScore`` (entry timing) are kept
**separate**; ``CrowdingRiskBadge`` can downgrade a decision; missing evidence
reduces coverage and pushes decisions toward ``research_more`` /
``insufficient_evidence``.

Safety invariants (by construction)
-----------------------------------
- Every model sets ``extra="forbid"`` — no ``approved_for_execution`` or
  order-ticket field can be smuggled in via construction.
- No model declares a buy/sell decision field or an executable order field.
- ``ThemeHeatBadge.is_buy_signal`` and ``EntryQualityScore.is_heat_score`` are
  hard-coded ``False``.

Disclaimer: outputs are for research / educational purposes only and do not
constitute investment advice.

See ``docs/reliability_phase_5k_horizon_aware_opportunity_queue.md``.
"""

from __future__ import annotations

import hashlib
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from lib.reliability.phase5_theme_intelligence import (
    SAMPLE_THEME_AS_OF,
    ConfirmationDirection,
    CrowdingLevel,
    EvidenceCoverageStatus,
    SignalStrength,
    ThemeCandidateRole,
    ThemeCandidateTicker,
    ThemeHeatScore,
    ThemeIntelligenceSnapshot,
    ThemeLifecycleStage,
    ThemeRecord,
    ThemeRiskSeverity,
    ThemeUniverseSnapshot,
    build_default_theme_intelligence_snapshot,
    build_degraded_theme_fixture,
    build_empty_theme_intelligence_snapshot,
)

_SCHEMA_VERSION: str = "phase5_opportunity_queue_v1"


# ---------------------------------------------------------------------------
# Literal aliases
# ---------------------------------------------------------------------------

# Exactly three supported horizons.
OpportunityHorizon = Literal["short_term", "mid_term", "long_term"]

OPPORTUNITY_HORIZONS: tuple[OpportunityHorizon, ...] = (
    "short_term",
    "mid_term",
    "long_term",
)

# Queue sections (six total: three horizon queues + three cross-cutting).
QueueKind = Literal[
    "short_term_trade",
    "mid_term_position",
    "long_term_investment",
    "watch_wait",
    "research_more",
    "no_trade_avoid",
]

QUEUE_KINDS: tuple[QueueKind, ...] = (
    "short_term_trade",
    "mid_term_position",
    "long_term_investment",
    "watch_wait",
    "research_more",
    "no_trade_avoid",
)

# Horizon-specific decision labels.
ShortTermDecisionLabel = Literal[
    "trade_now",
    "wait_for_pullback",
    "breakout_watch",
    "event_trade_watch",
    "too_extended",
    "no_trade",
]

SHORT_TERM_DECISION_LABELS: tuple[ShortTermDecisionLabel, ...] = (
    "trade_now",
    "wait_for_pullback",
    "breakout_watch",
    "event_trade_watch",
    "too_extended",
    "no_trade",
)

MidTermDecisionLabel = Literal[
    "position_candidate",
    "accumulate_on_pullback",
    "research_more",
    "wait_for_earnings_confirmation",
    "thesis_improving",
    "thesis_unconfirmed",
    "no_trade",
]

MID_TERM_DECISION_LABELS: tuple[MidTermDecisionLabel, ...] = (
    "position_candidate",
    "accumulate_on_pullback",
    "research_more",
    "wait_for_earnings_confirmation",
    "thesis_improving",
    "thesis_unconfirmed",
    "no_trade",
)

LongTermDecisionLabel = Literal[
    "investment_candidate",
    "watch_for_valuation",
    "compounder_watch",
    "quality_but_expensive",
    "thesis_durable",
    "thesis_insufficient",
    "no_trade",
]

LONG_TERM_DECISION_LABELS: tuple[LongTermDecisionLabel, ...] = (
    "investment_candidate",
    "watch_for_valuation",
    "compounder_watch",
    "quality_but_expensive",
    "thesis_durable",
    "thesis_insufficient",
    "no_trade",
)

# Cross-cutting labels usable for any horizon.
CrossCuttingDecisionLabel = Literal[
    "watch_wait",
    "research_more",
    "avoid_too_crowded",
    "insufficient_evidence",
    "no_trade",
]

CROSS_CUTTING_DECISION_LABELS: tuple[CrossCuttingDecisionLabel, ...] = (
    "watch_wait",
    "research_more",
    "avoid_too_crowded",
    "insufficient_evidence",
    "no_trade",
)

# Union of every distinct decision label.
OpportunityDecisionLabel = Literal[
    "trade_now",
    "wait_for_pullback",
    "breakout_watch",
    "event_trade_watch",
    "too_extended",
    "position_candidate",
    "accumulate_on_pullback",
    "wait_for_earnings_confirmation",
    "thesis_improving",
    "thesis_unconfirmed",
    "investment_candidate",
    "watch_for_valuation",
    "compounder_watch",
    "quality_but_expensive",
    "thesis_durable",
    "thesis_insufficient",
    "watch_wait",
    "research_more",
    "avoid_too_crowded",
    "insufficient_evidence",
    "no_trade",
]

# Score band for fit / entry-quality placeholders.
ScoreBand = Literal["poor", "fair", "good", "strong", "unknown"]

# Heat band for the heat badge.
HeatBand = Literal["cool", "warm", "hot", "red_hot", "unknown"]

# Entry quality computation status (separate from heat).
EntryQualityStatus = Literal["computed_placeholder", "partial", "unknown"]

# Status of a thesis at a horizon (qualitative, fixture-derived).
OpportunityThesisStatus = Literal[
    "improving",
    "unconfirmed",
    "durable",
    "insufficient",
    "unknown",
]

# Next-action verbs (NONE of these are order instructions).
OpportunityActionType = Literal[
    "research_more",
    "validate_macro_and_entry",
    "wait_for_pullback",
    "monitor_breakout",
    "monitor_event",
    "monitor_valuation",
    "add_to_watchlist",
    "reduce_or_avoid",
    "none",
]

# Warning types attached to opportunity candidates.
OpportunityWarningType = Literal[
    "heat_not_buy_signal",
    "crowding",
    "valuation_stretch",
    "missing_evidence",
    "narrative_only",
    "late_cycle",
    "unconfirmed_fundamentals",
    "needs_macro_validation",
    "needs_entry_validation",
    "unknown",
]


# ---------------------------------------------------------------------------
# Internal id helpers (deterministic)
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
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
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:8]


def make_opportunity_queue_id(label: str) -> str:
    """Deterministic, content-sensitive opportunity-queue id (no timestamp)."""
    return f"oppq_{_slug(label)}_{_short_hash('oppq::' + str(label))}"


# ---------------------------------------------------------------------------
# Badge / score models
# ---------------------------------------------------------------------------


class ThemeHeatBadge(BaseModel):
    """Compact view of a theme's heat for an opportunity candidate.

    Heat is a reason to *research*, never a buy signal — ``is_buy_signal`` is
    hard-coded ``False``.
    """

    model_config = ConfigDict(extra="forbid")

    band: HeatBand = "unknown"
    value: Optional[float] = None
    status: Literal["complete", "partial", "unknown"] = "unknown"
    is_buy_signal: Literal[False] = False
    note: str = ""


class EntryQualityScore(BaseModel):
    """Deterministic placeholder entry-quality score — SEPARATE from heat.

    Entry quality measures *timing / structure* (crowding, extension), not how
    hot a theme is. ``is_heat_score`` is hard-coded ``False`` to make the
    separation assertable. The value is a heuristic placeholder, not a
    live-trading signal.
    """

    model_config = ConfigDict(extra="forbid")

    value: Optional[float] = None
    band: ScoreBand = "unknown"
    status: EntryQualityStatus = "unknown"
    is_heat_score: Literal[False] = False
    rationale: str = ""


class HorizonFitScore(BaseModel):
    """Deterministic placeholder score for how well a candidate fits a horizon."""

    model_config = ConfigDict(extra="forbid")

    horizon: OpportunityHorizon
    value: Optional[float] = None
    band: ScoreBand = "unknown"
    rationale: str = ""


class CrowdingRiskBadge(BaseModel):
    """Crowding / positioning risk badge (can downgrade a decision)."""

    model_config = ConfigDict(extra="forbid")

    level: CrowdingLevel = "unknown"
    is_elevated: bool = False
    severity: ThemeRiskSeverity = "info"
    note: str = ""


class EvidenceCoverageBadge(BaseModel):
    """Evidence coverage badge (drives research_more / insufficient_evidence)."""

    model_config = ConfigDict(extra="forbid")

    coverage: EvidenceCoverageStatus = "unknown"
    evidence_ref_count: int = 0
    has_fundamental_confirmation: bool = False
    note: str = ""


class OpportunityNextAction(BaseModel):
    """A descriptive next action. NOT an order instruction."""

    model_config = ConfigDict(extra="forbid")

    action: OpportunityActionType = "none"
    description: str = ""


class OpportunityQueueWarning(BaseModel):
    """A non-fatal warning attached to a candidate or the queue."""

    model_config = ConfigDict(extra="forbid")

    warning_type: OpportunityWarningType = "unknown"
    severity: ThemeRiskSeverity = "info"
    message: str = ""


class OpportunitySourceSummary(BaseModel):
    """Provenance / source-signal summary for a candidate.

    Captures the original AI Research Workflow / theme-intelligence signal
    context that surfaced this candidate (momentum, narrative, fundamentals,
    lifecycle, heat band). It is descriptive provenance, not a decision.
    """

    model_config = ConfigDict(extra="forbid")

    momentum_strength: SignalStrength = "unknown"
    narrative_strength: SignalStrength = "unknown"
    fundamental_confirmation: ConfirmationDirection = "unknown"
    theme_lifecycle: ThemeLifecycleStage = "unknown"
    heat_band: HeatBand = "unknown"
    discovery_source_types: list[str] = Field(default_factory=list)
    from_ai_research_workflow: bool = False
    note: str = ""


# ---------------------------------------------------------------------------
# Candidate view models
# ---------------------------------------------------------------------------


class OpportunityCandidateView(BaseModel):
    """Horizon-agnostic normalized view of a theme candidate ticker.

    Carries the shared identity / badge / provenance context that is the same
    across horizons. Per-horizon decisions live on ``HorizonCandidateView``.
    No buy/sell field; no executable order field.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    company_name: Optional[str] = None
    theme_id: str = Field(min_length=1)
    theme_name: str = ""
    subtheme_ids: list[str] = Field(default_factory=list)
    chain_node_ids: list[str] = Field(default_factory=list)
    candidate_role: ThemeCandidateRole = "unknown"
    theme_heat: ThemeHeatBadge = Field(default_factory=ThemeHeatBadge)
    crowding_risk: CrowdingRiskBadge = Field(default_factory=CrowdingRiskBadge)
    evidence_coverage: EvidenceCoverageBadge = Field(
        default_factory=EvidenceCoverageBadge
    )
    source_signal_summary: OpportunitySourceSummary = Field(
        default_factory=OpportunitySourceSummary
    )
    evidence_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    warnings: list[OpportunityQueueWarning] = Field(default_factory=list)
    is_fixture_example: bool = True
    notes: str = ""


class HorizonCandidateView(BaseModel):
    """A candidate evaluated for ONE horizon, with a horizon-specific decision.

    The same ticker yields up to three of these (one per horizon), each with a
    potentially different ``decision_label``. No buy/sell field; no executable
    order field; no ``approved_for_execution``.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    company_name: Optional[str] = None
    theme_id: str = Field(min_length=1)
    theme_name: str = ""
    subtheme_ids: list[str] = Field(default_factory=list)
    chain_node_ids: list[str] = Field(default_factory=list)
    candidate_role: ThemeCandidateRole = "unknown"
    horizon: OpportunityHorizon
    opportunity_score: Optional[float] = None
    horizon_fit_score: HorizonFitScore
    entry_quality_score: EntryQualityScore = Field(default_factory=EntryQualityScore)
    theme_heat: ThemeHeatBadge = Field(default_factory=ThemeHeatBadge)
    crowding_risk: CrowdingRiskBadge = Field(default_factory=CrowdingRiskBadge)
    evidence_coverage: EvidenceCoverageBadge = Field(
        default_factory=EvidenceCoverageBadge
    )
    thesis_status: OpportunityThesisStatus = "unknown"
    review_trigger: Optional[str] = None
    next_action: OpportunityNextAction = Field(default_factory=OpportunityNextAction)
    decision_label: OpportunityDecisionLabel = "research_more"
    warnings: list[OpportunityQueueWarning] = Field(default_factory=list)
    source_signal_summary: OpportunitySourceSummary = Field(
        default_factory=OpportunitySourceSummary
    )
    evidence_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    is_fixture_example: bool = True
    notes: str = ""


# ---------------------------------------------------------------------------
# Queue section models
# ---------------------------------------------------------------------------


class OpportunityQueueView(BaseModel):
    """Generic queue section: a kind, an optional horizon, and candidates."""

    model_config = ConfigDict(extra="forbid")

    queue_kind: QueueKind
    horizon: Optional[OpportunityHorizon] = None
    title: str = ""
    candidates: list[HorizonCandidateView] = Field(default_factory=list)
    count: int = 0


class ShortTermTradeQueue(OpportunityQueueView):
    queue_kind: QueueKind = "short_term_trade"
    horizon: Optional[OpportunityHorizon] = "short_term"
    title: str = "Short-term trade candidates"


class MidTermPositionQueue(OpportunityQueueView):
    queue_kind: QueueKind = "mid_term_position"
    horizon: Optional[OpportunityHorizon] = "mid_term"
    title: str = "Mid-term position candidates"


class LongTermInvestmentQueue(OpportunityQueueView):
    queue_kind: QueueKind = "long_term_investment"
    horizon: Optional[OpportunityHorizon] = "long_term"
    title: str = "Long-term investment candidates"


class WatchWaitQueue(OpportunityQueueView):
    queue_kind: QueueKind = "watch_wait"
    horizon: Optional[OpportunityHorizon] = None
    title: str = "Watch / wait"


class ResearchMoreQueue(OpportunityQueueView):
    queue_kind: QueueKind = "research_more"
    horizon: Optional[OpportunityHorizon] = None
    title: str = "Research more"


class NoTradeAvoidQueue(OpportunityQueueView):
    queue_kind: QueueKind = "no_trade_avoid"
    horizon: Optional[OpportunityHorizon] = None
    title: str = "No trade / avoid"


# ---------------------------------------------------------------------------
# Cross-horizon comparison + validation summary
# ---------------------------------------------------------------------------


class CrossHorizonEntry(BaseModel):
    """One horizon's decision for a ticker in a cross-horizon comparison."""

    model_config = ConfigDict(extra="forbid")

    horizon: OpportunityHorizon
    decision_label: OpportunityDecisionLabel
    queue_kind: QueueKind
    opportunity_score: Optional[float] = None


class CrossHorizonCandidateComparison(BaseModel):
    """How a single ticker is treated across all three horizons.

    Demonstrates the core principle that the same ticker may appear in multiple
    horizons with different decisions.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    company_name: Optional[str] = None
    theme_id: str = Field(min_length=1)
    theme_name: str = ""
    entries: list[CrossHorizonEntry] = Field(default_factory=list)
    decisions_by_horizon: dict[str, str] = Field(default_factory=dict)
    has_divergent_decisions: bool = False
    note: str = ""


class OpportunityQueueValidationSummary(BaseModel):
    """Deterministic, safe summary of a horizon-aware opportunity queue.

    Reports counts and safety invariant flags. ``is_safe_empty`` is True for an
    empty theme universe (a valid, safe state). ``issues`` carries non-fatal
    observations. It never produces a buy/sell decision and never fabricates
    completion for missing evidence.
    """

    model_config = ConfigDict(extra="forbid")

    total_horizon_candidates: int = 0
    short_term_count: int = 0
    mid_term_count: int = 0
    long_term_count: int = 0
    watch_wait_count: int = 0
    research_more_count: int = 0
    no_trade_avoid_count: int = 0
    trade_now_count: int = 0
    # NOTE: ``distinct_tickers`` counts distinct ``(theme_id, ticker)`` pairs,
    # not bare ticker symbols. The same symbol mapped to two different themes
    # counts twice; the same symbol evaluated across multiple horizons within
    # one theme counts once. It is therefore more precisely a count of distinct
    # *theme-candidate opportunities*. ``distinct_theme_candidate_opportunities``
    # below carries the same value under the clearer name; ``distinct_tickers``
    # is preserved for backward compatibility with existing Phase 5K consumers.
    distinct_tickers: int = 0
    distinct_theme_candidate_opportunities: int = 0
    multi_horizon_ticker_count: int = 0
    candidates_with_warnings: int = 0
    missing_evidence_count: int = 0
    crowded_downgrade_count: int = 0
    is_safe_empty: bool = True
    # Safety invariants (always True for a well-formed Phase 5K queue).
    no_buy_signal_fields: bool = True
    no_executable_order_fields: bool = True
    approved_for_execution_absent: bool = True
    no_unsafe_trade_now: bool = True
    issues: list[str] = Field(default_factory=list)


class HorizonAwareOpportunityQueueView(BaseModel):
    """Top-level Phase 5K contract: six queues + cross-horizon comparisons.

    Built deterministically from a Phase 5J ``ThemeIntelligenceSnapshot``.
    Carries no buy/sell decision, no order instruction, and no executable
    order field. Final trade / allocation / option planning happens later.
    """

    model_config = ConfigDict(extra="forbid")

    queue_id: str = Field(min_length=1)
    as_of: Optional[str] = None
    schema_version: str = _SCHEMA_VERSION
    source_theme_snapshot_id: Optional[str] = None
    description: str = ""
    short_term: ShortTermTradeQueue = Field(default_factory=ShortTermTradeQueue)
    mid_term: MidTermPositionQueue = Field(default_factory=MidTermPositionQueue)
    long_term: LongTermInvestmentQueue = Field(default_factory=LongTermInvestmentQueue)
    watch_wait: WatchWaitQueue = Field(default_factory=WatchWaitQueue)
    research_more: ResearchMoreQueue = Field(default_factory=ResearchMoreQueue)
    no_trade_avoid: NoTradeAvoidQueue = Field(default_factory=NoTradeAvoidQueue)
    candidates: list[OpportunityCandidateView] = Field(default_factory=list)
    cross_horizon_comparisons: list[CrossHorizonCandidateComparison] = Field(
        default_factory=list
    )
    validation_summary: Optional[OpportunityQueueValidationSummary] = None
    warnings: list[OpportunityQueueWarning] = Field(default_factory=list)
    is_fixture: bool = True
    notes: str = ""


# ---------------------------------------------------------------------------
# Deterministic scoring helpers (heuristic placeholders; not live signals)
# ---------------------------------------------------------------------------

_HEAT_COMPONENT_FIELDS: tuple[str, ...] = (
    "price_momentum_component",
    "volume_component",
    "breadth_component",
    "narrative_component",
    "fundamental_confirmation_component",
    "freshness_component",
)

_CROWDED_LEVELS = ("elevated", "high", "extreme")


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _score_band(value: Optional[float]) -> ScoreBand:
    if value is None:
        return "unknown"
    if value >= 0.7:
        return "strong"
    if value >= 0.55:
        return "good"
    if value >= 0.35:
        return "fair"
    return "poor"


def _heat_band(value: Optional[float]) -> HeatBand:
    if value is None:
        return "unknown"
    if value >= 0.75:
        return "red_hot"
    if value >= 0.55:
        return "hot"
    if value >= 0.35:
        return "warm"
    return "cool"


def _heat_value(score: ThemeHeatScore) -> Optional[float]:
    """Mean of present heat components (0..1). None if no components present."""
    present = [
        float(getattr(score, f))
        for f in _HEAT_COMPONENT_FIELDS
        if getattr(score, f) is not None
    ]
    if not present:
        return None
    return round(sum(present) / len(present), 4)


def build_theme_heat_badge(score: ThemeHeatScore) -> ThemeHeatBadge:
    """Deterministic heat badge from a Phase 5J ``ThemeHeatScore``."""
    value = _heat_value(score)
    band = _heat_band(value)
    return ThemeHeatBadge(
        band=band,
        value=value,
        status=score.score_status,
        note="Heat is a reason to research, not a buy signal.",
    )


def _resolve_crowding_level(candidate: ThemeCandidateTicker) -> CrowdingLevel:
    if candidate.crowding_level != "unknown":
        return candidate.crowding_level
    if candidate.crowding_signal is not None:
        return candidate.crowding_signal.crowding_level
    return "unknown"


def build_crowding_risk_badge(candidate: ThemeCandidateTicker) -> CrowdingRiskBadge:
    level = _resolve_crowding_level(candidate)
    severity_map: dict[CrowdingLevel, ThemeRiskSeverity] = {
        "low": "info",
        "moderate": "info",
        "elevated": "low",
        "high": "medium",
        "extreme": "high",
        "unknown": "info",
    }
    return CrowdingRiskBadge(
        level=level,
        is_elevated=level in _CROWDED_LEVELS,
        severity=severity_map.get(level, "info"),
        note="Crowding is an argument against chasing; kept separate from heat.",
    )


def _theme_confirmation(theme: ThemeRecord) -> tuple[bool, bool, bool]:
    """Return (confirming, confirming_strong, mixed) from theme signals."""
    confirming = False
    strong = False
    mixed = False
    for sig in theme.fundamental_confirmation_signals:
        if sig.confirmation_direction == "confirming":
            confirming = True
            if sig.strength == "strong":
                strong = True
        elif sig.confirmation_direction == "mixed":
            mixed = True
    return confirming, strong, mixed


def build_evidence_coverage_badge(
    candidate: ThemeCandidateTicker, theme: ThemeRecord
) -> EvidenceCoverageBadge:
    confirming, _strong, _mixed = _theme_confirmation(theme)
    cov = candidate.evidence.coverage_status
    has_fund = confirming and cov == "complete"
    note = ""
    if cov in ("none", "unknown"):
        note = "Insufficient evidence; do not treat as actionable."
    elif cov == "partial":
        note = "Partial evidence; further confirmation required."
    return EvidenceCoverageBadge(
        coverage=cov,
        evidence_ref_count=len(candidate.evidence.evidence_refs),
        has_fundamental_confirmation=has_fund,
        note=note,
    )


def _momentum(theme: ThemeRecord, candidate: ThemeCandidateTicker, heat_band: HeatBand):
    """Return (momentum_strong, momentum_moderate, strength)."""
    price_strong = any(
        s.signal_type == "price_momentum" and s.strength == "strong"
        for s in theme.source_signals
    )
    price_moderate = any(
        s.signal_type == "price_momentum" and s.strength in ("strong", "moderate")
        for s in theme.source_signals
    )
    hc = candidate.heat_contribution or 0.0
    momentum_strong = (heat_band in ("hot", "red_hot") and hc >= 0.6) or (
        price_strong and hc >= 0.5
    )
    momentum_moderate = (
        momentum_strong
        or hc >= 0.4
        or price_moderate
        or heat_band in ("warm", "hot", "red_hot")
    )
    if momentum_strong:
        strength: SignalStrength = "strong"
    elif momentum_moderate:
        strength = "moderate"
    elif hc > 0.0 or price_moderate:
        strength = "weak"
    else:
        strength = "unknown"
    return momentum_strong, momentum_moderate, strength


def _entry_quality(
    crowding_level: CrowdingLevel,
    heat_band: HeatBand,
    evidence_status: EvidenceCoverageStatus,
) -> EntryQualityScore:
    """Deterministic placeholder entry quality, SEPARATE from heat.

    Crowding dominates (chasing risk); a hotter band slightly worsens entry
    (more extended); thin evidence slightly worsens entry.
    """
    if crowding_level == "unknown" and heat_band == "unknown":
        return EntryQualityScore(
            value=None,
            band="unknown",
            status="unknown",
            rationale="Crowding and heat both unknown; entry quality not assessable.",
        )

    crowd_adj = {
        "low": 0.30,
        "moderate": 0.05,
        "elevated": -0.15,
        "high": -0.30,
        "extreme": -0.45,
        "unknown": 0.0,
    }[crowding_level]
    heat_adj = {
        "red_hot": -0.10,
        "hot": -0.05,
        "warm": 0.0,
        "cool": 0.10,
        "unknown": 0.0,
    }[heat_band]
    ev_adj = {
        "complete": 0.10,
        "partial": 0.0,
        "none": -0.10,
        "unknown": 0.0,
    }[evidence_status]

    value = round(_clamp(0.5 + crowd_adj + heat_adj + ev_adj), 4)
    band = _score_band(value)
    status: EntryQualityStatus = (
        "partial"
        if crowding_level == "unknown" or evidence_status == "unknown"
        else "computed_placeholder"
    )
    return EntryQualityScore(
        value=value,
        band=band,
        status=status,
        rationale=(
            "Heuristic placeholder: crowding-dominant, heat-extension-aware. "
            "Separate from theme heat; not a live-trading signal."
        ),
    )


def _horizon_fit(
    horizon: OpportunityHorizon,
    *,
    heat_value: Optional[float],
    heat_contribution: float,
    role: ThemeCandidateRole,
    evidence_status: EvidenceCoverageStatus,
    confirming: bool,
    strong: bool,
    mixed: bool,
    lifecycle: ThemeLifecycleStage,
    crowding_level: CrowdingLevel,
) -> HorizonFitScore:
    if horizon == "short_term":
        role_bonus = {
            "leader": 0.15,
            "second_derivative_beneficiary": 0.10,
            "supplier": 0.05,
            "platform": 0.05,
            "laggard": -0.10,
            "speculative": -0.10,
            "unknown": 0.0,
        }[role]
        hv = heat_value if heat_value is not None else 0.3
        value = round(_clamp(0.5 * hv + 0.3 * heat_contribution + role_bonus), 4)
        rationale = "Short-term fit favors momentum / heat + leadership role."
    elif horizon == "mid_term":
        ev_score = {"complete": 0.4, "partial": 0.2, "none": 0.0, "unknown": 0.0}[
            evidence_status
        ]
        conf_score = 0.3 if confirming else (0.15 if mixed else 0.0)
        life_score = {
            "accelerating": 0.2,
            "consensus": 0.2,
            "emerging": 0.1,
            "crowded": 0.05,
            "fading": 0.0,
            "unknown": 0.0,
        }[lifecycle]
        value = round(_clamp(ev_score + conf_score + life_score), 4)
        rationale = (
            "Mid-term fit requires fundamental confirmation + evidence + "
            "constructive lifecycle, beyond momentum."
        )
    else:  # long_term
        ev_score = {"complete": 0.4, "partial": 0.15, "none": 0.0, "unknown": 0.0}[
            evidence_status
        ]
        conf_score = 0.3 if strong else (0.2 if confirming else (0.05 if mixed else 0.0))
        crowd_pen = {
            "low": 0.0,
            "moderate": 0.0,
            "elevated": -0.10,
            "high": -0.20,
            "extreme": -0.30,
            "unknown": 0.0,
        }[crowding_level]
        late_pen = {"fading": -0.2, "crowded": -0.1}.get(lifecycle, 0.0)
        value = round(_clamp(0.2 + ev_score + conf_score + crowd_pen + late_pen), 4)
        rationale = (
            "Long-term fit requires complete evidence + durable confirmation; "
            "penalized by crowding / late-cycle."
        )
    return HorizonFitScore(
        horizon=horizon, value=value, band=_score_band(value), rationale=rationale
    )


def _thesis_status(
    evidence_status: EvidenceCoverageStatus,
    confirming: bool,
    strong: bool,
    mixed: bool,
) -> OpportunityThesisStatus:
    if evidence_status in ("none", "unknown"):
        return "insufficient"
    if confirming and strong and evidence_status == "complete":
        return "durable"
    if confirming:
        return "improving"
    if mixed:
        return "unconfirmed"
    return "unconfirmed"


def _review_trigger(
    evidence_status: EvidenceCoverageStatus,
    crowding_elevated: bool,
    heat_band: HeatBand,
) -> Optional[str]:
    triggers: list[str] = []
    if evidence_status in ("partial", "none", "unknown"):
        triggers.append("Awaiting fundamental / earnings confirmation")
    if crowding_elevated:
        triggers.append("Re-evaluate on pullback / crowding reset")
    if heat_band == "red_hot":
        triggers.append("Monitor for valuation / heat normalization")
    return "; ".join(triggers) if triggers else None


# ---------------------------------------------------------------------------
# Decision logic (deterministic, per horizon)
# ---------------------------------------------------------------------------


def _short_term_decision(
    *,
    role: ThemeCandidateRole,
    evidence_status: EvidenceCoverageStatus,
    crowding_level: CrowdingLevel,
    heat_band: HeatBand,
    heat_status: str,
    entry_band: ScoreBand,
    momentum_strong: bool,
    momentum_moderate: bool,
    disconfirming: bool,
) -> OpportunityDecisionLabel:
    crowding_elevated = crowding_level in _CROWDED_LEVELS
    if disconfirming:
        return "no_trade"
    if evidence_status == "none" and role == "speculative":
        return "research_more"
    if crowding_level == "extreme":
        return "avoid_too_crowded"
    if heat_status == "unknown" and not momentum_moderate:
        if evidence_status in ("none", "unknown"):
            return "insufficient_evidence"
        return "watch_wait"
    if crowding_level in ("high", "extreme") and heat_band == "red_hot":
        return "too_extended"
    if crowding_elevated and entry_band in ("poor", "fair"):
        return "wait_for_pullback"
    if momentum_strong and entry_band in ("good", "strong") and not crowding_elevated:
        return "trade_now"
    if momentum_strong:
        return "wait_for_pullback"
    if momentum_moderate:
        return "breakout_watch"
    if evidence_status in ("none", "unknown"):
        return "research_more"
    return "watch_wait"


def _mid_term_decision(
    *,
    role: ThemeCandidateRole,
    evidence_status: EvidenceCoverageStatus,
    crowding_level: CrowdingLevel,
    confirming: bool,
    mixed: bool,
    lifecycle: ThemeLifecycleStage,
    disconfirming: bool,
) -> OpportunityDecisionLabel:
    crowding_elevated = crowding_level in _CROWDED_LEVELS
    if disconfirming:
        return "no_trade"
    if crowding_level == "extreme":
        return "avoid_too_crowded"
    if evidence_status in ("none", "unknown"):
        return "insufficient_evidence" if role == "speculative" else "research_more"
    if confirming and evidence_status == "complete":
        if lifecycle in ("accelerating", "consensus"):
            return "accumulate_on_pullback" if crowding_elevated else "position_candidate"
        if lifecycle == "emerging":
            return "thesis_improving"
        return "research_more"
    if mixed:
        return "wait_for_earnings_confirmation"
    if evidence_status == "complete" and not confirming:
        return "thesis_unconfirmed"
    # partial evidence without complete confirmation -> needs more research.
    return "research_more"


def _long_term_decision(
    *,
    role: ThemeCandidateRole,
    evidence_status: EvidenceCoverageStatus,
    crowding_level: CrowdingLevel,
    heat_band: HeatBand,
    confirming: bool,
    strong: bool,
    mixed: bool,
    lifecycle: ThemeLifecycleStage,
    valuation_stretch: bool,
    disconfirming: bool,
) -> OpportunityDecisionLabel:
    crowding_elevated = crowding_level in _CROWDED_LEVELS
    if disconfirming:
        return "no_trade"
    if crowding_level == "extreme":
        return "avoid_too_crowded"
    if evidence_status in ("none", "unknown"):
        return "insufficient_evidence" if role == "speculative" else "research_more"
    if evidence_status == "partial":
        # Long-term needs complete evidence; momentum alone is insufficient.
        return "research_more"
    if evidence_status == "complete" and confirming:
        if valuation_stretch or crowding_level in ("high", "extreme"):
            return "quality_but_expensive"
        if heat_band == "red_hot" or crowding_elevated:
            return "watch_for_valuation"
        if role in ("leader", "platform") and lifecycle in (
            "accelerating",
            "consensus",
        ):
            return "compounder_watch"
        if strong and lifecycle == "consensus":
            return "thesis_durable"
        return "investment_candidate"
    if mixed:
        return "thesis_insufficient"
    if evidence_status == "complete" and not confirming:
        return "thesis_insufficient"
    return "research_more"


# Decision label -> next action mapping.
_ACTION_MAP: dict[str, tuple[OpportunityActionType, str]] = {
    "trade_now": (
        "validate_macro_and_entry",
        "Validate macro + entry quality before any action; not an order.",
    ),
    "wait_for_pullback": (
        "wait_for_pullback",
        "Wait for a pullback / better entry; do not chase.",
    ),
    "breakout_watch": (
        "monitor_breakout",
        "Monitor for a confirmed breakout with volume.",
    ),
    "event_trade_watch": (
        "monitor_event",
        "Monitor the upcoming catalyst / event before acting.",
    ),
    "too_extended": (
        "wait_for_pullback",
        "Too extended; wait for mean reversion / pullback.",
    ),
    "position_candidate": (
        "validate_macro_and_entry",
        "Mid-term position candidate pending macro + entry validation.",
    ),
    "accumulate_on_pullback": (
        "wait_for_pullback",
        "Accumulate on pullbacks; scale in, do not chase.",
    ),
    "wait_for_earnings_confirmation": (
        "monitor_event",
        "Wait for earnings / fundamental confirmation.",
    ),
    "thesis_improving": (
        "research_more",
        "Thesis improving; continue research to confirm.",
    ),
    "thesis_unconfirmed": (
        "research_more",
        "Thesis unconfirmed; needs more evidence.",
    ),
    "investment_candidate": (
        "validate_macro_and_entry",
        "Long-term investment candidate pending full research / decision.",
    ),
    "watch_for_valuation": (
        "monitor_valuation",
        "Quality name; wait for a better valuation.",
    ),
    "compounder_watch": (
        "add_to_watchlist",
        "Potential compounder; add to the long-term watchlist.",
    ),
    "quality_but_expensive": (
        "monitor_valuation",
        "Quality but expensive; monitor valuation / crowding.",
    ),
    "thesis_durable": (
        "add_to_watchlist",
        "Durable thesis; track for better entry windows.",
    ),
    "thesis_insufficient": (
        "research_more",
        "Insufficient long-term evidence; research more.",
    ),
    "watch_wait": (
        "add_to_watchlist",
        "Watch and wait; insufficient trigger to act.",
    ),
    "research_more": (
        "research_more",
        "Needs more research / evidence before any decision.",
    ),
    "avoid_too_crowded": (
        "reduce_or_avoid",
        "Too crowded; avoid chasing here.",
    ),
    "insufficient_evidence": (
        "research_more",
        "Insufficient evidence; do not treat as actionable.",
    ),
    "no_trade": (
        "reduce_or_avoid",
        "No trade; avoid.",
    ),
}


def _next_action(decision: OpportunityDecisionLabel) -> OpportunityNextAction:
    action, desc = _ACTION_MAP.get(decision, ("none", ""))
    return OpportunityNextAction(action=action, description=desc)


_WARN_TYPE_MAP: dict[str, OpportunityWarningType] = {
    "crowding": "crowding",
    "valuation_stretch": "valuation_stretch",
    "narrative_only": "narrative_only",
    "missing_evidence": "missing_evidence",
    "late_cycle": "late_cycle",
    "unconfirmed_fundamentals": "unconfirmed_fundamentals",
    "low_breadth": "unknown",
    "unknown": "unknown",
}


def _build_candidate_warnings(
    candidate: ThemeCandidateTicker,
    *,
    heat_band: HeatBand,
    crowding_level: CrowdingLevel,
    evidence_status: EvidenceCoverageStatus,
) -> list[OpportunityQueueWarning]:
    warnings: list[OpportunityQueueWarning] = []
    for w in candidate.warnings:
        warnings.append(
            OpportunityQueueWarning(
                warning_type=_WARN_TYPE_MAP.get(w.warning_type, "unknown"),
                severity=w.severity,
                message=w.message,
            )
        )
    if heat_band in ("hot", "red_hot"):
        warnings.append(
            OpportunityQueueWarning(
                warning_type="heat_not_buy_signal",
                severity="info",
                message="High theme heat is not a buy signal; validate entry quality.",
            )
        )
    if crowding_level in _CROWDED_LEVELS:
        warnings.append(
            OpportunityQueueWarning(
                warning_type="crowding",
                severity="medium" if crowding_level in ("high", "extreme") else "low",
                message=f"Crowding is {crowding_level}; avoid chasing into the crowd.",
            )
        )
    if evidence_status in ("none", "unknown"):
        warnings.append(
            OpportunityQueueWarning(
                warning_type="missing_evidence",
                severity="high",
                message="Insufficient evidence; research before any decision.",
            )
        )
    elif evidence_status == "partial":
        warnings.append(
            OpportunityQueueWarning(
                warning_type="missing_evidence",
                severity="low",
                message="Partial evidence; further confirmation required.",
            )
        )
    return warnings


def _opportunity_score(
    fit: HorizonFitScore, entry: EntryQualityScore
) -> Optional[float]:
    parts: list[float] = []
    if fit.value is not None:
        parts.append(fit.value)
    if entry.value is not None:
        parts.append(entry.value)
    if not parts:
        return None
    return round(sum(parts) / len(parts), 4)


def _source_summary(
    theme: ThemeRecord,
    candidate: ThemeCandidateTicker,
    *,
    heat_band: HeatBand,
    momentum_strength: SignalStrength,
    confirming: bool,
    strong: bool,
    mixed: bool,
) -> OpportunitySourceSummary:
    narrative_strength: SignalStrength = "unknown"
    if theme.narrative_signals:
        narrative_strength = theme.narrative_signals[0].mention_intensity
    if strong:
        fundamental: ConfirmationDirection = "confirming"
    elif confirming:
        fundamental = "confirming"
    elif mixed:
        fundamental = "mixed"
    else:
        fundamental = "unconfirmed"
    src_types = sorted({s.source_type for s in theme.discovery_sources})
    from_workflow = any(
        s.source_type in ("scanner", "sector_rotation") for s in theme.source_signals
    )
    return OpportunitySourceSummary(
        momentum_strength=momentum_strength,
        narrative_strength=narrative_strength,
        fundamental_confirmation=fundamental,
        theme_lifecycle=theme.lifecycle_stage,
        heat_band=heat_band,
        discovery_source_types=src_types,
        from_ai_research_workflow=from_workflow,
        note="Descriptive provenance only; not a decision.",
    )


# ---------------------------------------------------------------------------
# Candidate builders
# ---------------------------------------------------------------------------


def _candidate_context(candidate: ThemeCandidateTicker, theme: ThemeRecord) -> dict:
    """Compute the shared deterministic context for one candidate/theme."""
    heat_badge = build_theme_heat_badge(theme.heat_score)
    crowding_badge = build_crowding_risk_badge(candidate)
    evidence_badge = build_evidence_coverage_badge(candidate, theme)
    confirming, strong, mixed = _theme_confirmation(theme)
    disconfirming = any(
        s.confirmation_direction == "disconfirming"
        for s in theme.fundamental_confirmation_signals
    )
    momentum_strong, momentum_moderate, momentum_strength = _momentum(
        theme, candidate, heat_badge.band
    )
    crowding_level = crowding_badge.level
    evidence_status = candidate.evidence.coverage_status
    entry = _entry_quality(crowding_level, heat_badge.band, evidence_status)
    valuation_stretch = (
        candidate.crowding_signal is not None
        and candidate.crowding_signal.valuation_stretch is not None
    )
    return {
        "heat_badge": heat_badge,
        "crowding_badge": crowding_badge,
        "evidence_badge": evidence_badge,
        "confirming": confirming,
        "strong": strong,
        "mixed": mixed,
        "disconfirming": disconfirming,
        "momentum_strong": momentum_strong,
        "momentum_moderate": momentum_moderate,
        "momentum_strength": momentum_strength,
        "crowding_level": crowding_level,
        "evidence_status": evidence_status,
        "entry": entry,
        "valuation_stretch": valuation_stretch,
        "lifecycle": theme.lifecycle_stage,
        "role": candidate.role,
        "heat_contribution": candidate.heat_contribution or 0.0,
    }


def build_opportunity_candidate_from_theme_candidate(
    candidate: ThemeCandidateTicker, theme: ThemeRecord
) -> OpportunityCandidateView:
    """Build the horizon-agnostic normalized candidate view."""
    ctx = _candidate_context(candidate, theme)
    summary = _source_summary(
        theme,
        candidate,
        heat_band=ctx["heat_badge"].band,
        momentum_strength=ctx["momentum_strength"],
        confirming=ctx["confirming"],
        strong=ctx["strong"],
        mixed=ctx["mixed"],
    )
    warnings = _build_candidate_warnings(
        candidate,
        heat_band=ctx["heat_badge"].band,
        crowding_level=ctx["crowding_level"],
        evidence_status=ctx["evidence_status"],
    )
    return OpportunityCandidateView(
        ticker=candidate.ticker,
        company_name=candidate.company_name,
        theme_id=candidate.theme_id,
        theme_name=theme.name,
        subtheme_ids=list(candidate.subtheme_ids),
        chain_node_ids=list(candidate.chain_node_ids),
        candidate_role=candidate.role,
        theme_heat=ctx["heat_badge"],
        crowding_risk=ctx["crowding_badge"],
        evidence_coverage=ctx["evidence_badge"],
        source_signal_summary=summary,
        evidence_refs=list(candidate.evidence.evidence_refs),
        source_refs=list(candidate.evidence.source_refs),
        warnings=warnings,
        is_fixture_example=candidate.is_fixture_example,
        notes=candidate.notes,
    )


def _build_horizon_candidate_view(
    candidate: ThemeCandidateTicker,
    theme: ThemeRecord,
    horizon: OpportunityHorizon,
    ctx: dict,
) -> HorizonCandidateView:
    heat_badge: ThemeHeatBadge = ctx["heat_badge"]
    entry: EntryQualityScore = ctx["entry"]
    crowding_level: CrowdingLevel = ctx["crowding_level"]
    evidence_status: EvidenceCoverageStatus = ctx["evidence_status"]

    fit = _horizon_fit(
        horizon,
        heat_value=heat_badge.value,
        heat_contribution=ctx["heat_contribution"],
        role=ctx["role"],
        evidence_status=evidence_status,
        confirming=ctx["confirming"],
        strong=ctx["strong"],
        mixed=ctx["mixed"],
        lifecycle=ctx["lifecycle"],
        crowding_level=crowding_level,
    )

    if horizon == "short_term":
        decision = _short_term_decision(
            role=ctx["role"],
            evidence_status=evidence_status,
            crowding_level=crowding_level,
            heat_band=heat_badge.band,
            heat_status=heat_badge.status,
            entry_band=entry.band,
            momentum_strong=ctx["momentum_strong"],
            momentum_moderate=ctx["momentum_moderate"],
            disconfirming=ctx["disconfirming"],
        )
    elif horizon == "mid_term":
        decision = _mid_term_decision(
            role=ctx["role"],
            evidence_status=evidence_status,
            crowding_level=crowding_level,
            confirming=ctx["confirming"],
            mixed=ctx["mixed"],
            lifecycle=ctx["lifecycle"],
            disconfirming=ctx["disconfirming"],
        )
    else:
        decision = _long_term_decision(
            role=ctx["role"],
            evidence_status=evidence_status,
            crowding_level=crowding_level,
            heat_band=heat_badge.band,
            confirming=ctx["confirming"],
            strong=ctx["strong"],
            mixed=ctx["mixed"],
            lifecycle=ctx["lifecycle"],
            valuation_stretch=ctx["valuation_stretch"],
            disconfirming=ctx["disconfirming"],
        )

    warnings = _build_candidate_warnings(
        candidate,
        heat_band=heat_badge.band,
        crowding_level=crowding_level,
        evidence_status=evidence_status,
    )
    summary = _source_summary(
        theme,
        candidate,
        heat_band=heat_badge.band,
        momentum_strength=ctx["momentum_strength"],
        confirming=ctx["confirming"],
        strong=ctx["strong"],
        mixed=ctx["mixed"],
    )
    return HorizonCandidateView(
        ticker=candidate.ticker,
        company_name=candidate.company_name,
        theme_id=candidate.theme_id,
        theme_name=theme.name,
        subtheme_ids=list(candidate.subtheme_ids),
        chain_node_ids=list(candidate.chain_node_ids),
        candidate_role=candidate.role,
        horizon=horizon,
        opportunity_score=_opportunity_score(fit, entry),
        horizon_fit_score=fit,
        entry_quality_score=entry,
        theme_heat=heat_badge,
        crowding_risk=ctx["crowding_badge"],
        evidence_coverage=ctx["evidence_badge"],
        thesis_status=_thesis_status(
            evidence_status, ctx["confirming"], ctx["strong"], ctx["mixed"]
        ),
        review_trigger=_review_trigger(
            evidence_status,
            crowding_level in _CROWDED_LEVELS,
            heat_badge.band,
        ),
        next_action=_next_action(decision),
        decision_label=decision,
        warnings=warnings,
        source_signal_summary=summary,
        evidence_refs=list(candidate.evidence.evidence_refs),
        source_refs=list(candidate.evidence.source_refs),
        is_fixture_example=candidate.is_fixture_example,
        notes=candidate.notes,
    )


def build_short_term_candidate_view(
    candidate: ThemeCandidateTicker, theme: ThemeRecord
) -> HorizonCandidateView:
    return _build_horizon_candidate_view(
        candidate, theme, "short_term", _candidate_context(candidate, theme)
    )


def build_mid_term_candidate_view(
    candidate: ThemeCandidateTicker, theme: ThemeRecord
) -> HorizonCandidateView:
    return _build_horizon_candidate_view(
        candidate, theme, "mid_term", _candidate_context(candidate, theme)
    )


def build_long_term_candidate_view(
    candidate: ThemeCandidateTicker, theme: ThemeRecord
) -> HorizonCandidateView:
    return _build_horizon_candidate_view(
        candidate, theme, "long_term", _candidate_context(candidate, theme)
    )


def build_horizon_candidate_views(
    candidate: ThemeCandidateTicker, theme: ThemeRecord
) -> list[HorizonCandidateView]:
    """Build the three horizon views (short, mid, long) for one candidate."""
    ctx = _candidate_context(candidate, theme)
    return [
        _build_horizon_candidate_view(candidate, theme, h, ctx)
        for h in OPPORTUNITY_HORIZONS
    ]


# ---------------------------------------------------------------------------
# Routing + queue assembly
# ---------------------------------------------------------------------------

# Cross-cutting decision labels route to a cross-cutting queue regardless of
# the horizon they were evaluated for.
_CROSS_ROUTE: dict[str, QueueKind] = {
    "watch_wait": "watch_wait",
    "research_more": "research_more",
    "insufficient_evidence": "research_more",
    "thesis_unconfirmed": "research_more",
    "thesis_insufficient": "research_more",
    "avoid_too_crowded": "no_trade_avoid",
    "no_trade": "no_trade_avoid",
}

_HORIZON_TO_QUEUE: dict[OpportunityHorizon, QueueKind] = {
    "short_term": "short_term_trade",
    "mid_term": "mid_term_position",
    "long_term": "long_term_investment",
}


def _route_queue_kind(
    decision: OpportunityDecisionLabel, horizon: OpportunityHorizon
) -> QueueKind:
    """Horizon-native labels route to the horizon queue; cross-cutting labels
    route to the matching cross-cutting queue."""
    if decision in _CROSS_ROUTE:
        return _CROSS_ROUTE[decision]
    return _HORIZON_TO_QUEUE[horizon]


def _collect_theme_candidates(theme: ThemeRecord) -> list[ThemeCandidateTicker]:
    """Theme-level candidates if present; else dedup subtheme candidates."""
    if theme.candidate_tickers:
        return list(theme.candidate_tickers)
    seen: set[str] = set()
    collected: list[ThemeCandidateTicker] = []
    for sub in theme.subthemes:
        for cand in sub.candidate_tickers:
            if cand.ticker not in seen:
                seen.add(cand.ticker)
                collected.append(cand)
    return collected


def build_cross_horizon_candidate_comparison(
    horizon_views: list[HorizonCandidateView],
) -> list[CrossHorizonCandidateComparison]:
    """Group horizon views by (theme_id, ticker) into cross-horizon rows.

    Deterministic: entries are ordered by ``OPPORTUNITY_HORIZONS``; groups are
    emitted in first-seen order.
    """
    order: list[tuple[str, str]] = []
    groups: dict[tuple[str, str], list[HorizonCandidateView]] = {}
    for view in horizon_views:
        key = (view.theme_id, view.ticker)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(view)

    comparisons: list[CrossHorizonCandidateComparison] = []
    for key in order:
        views = groups[key]
        by_horizon = {v.horizon: v for v in views}
        entries: list[CrossHorizonEntry] = []
        decisions: dict[str, str] = {}
        for h in OPPORTUNITY_HORIZONS:
            v = by_horizon.get(h)
            if v is None:
                continue
            entries.append(
                CrossHorizonEntry(
                    horizon=h,
                    decision_label=v.decision_label,
                    queue_kind=_route_queue_kind(v.decision_label, h),
                    opportunity_score=v.opportunity_score,
                )
            )
            decisions[h] = v.decision_label
        first = views[0]
        comparisons.append(
            CrossHorizonCandidateComparison(
                ticker=first.ticker,
                company_name=first.company_name,
                theme_id=first.theme_id,
                theme_name=first.theme_name,
                entries=entries,
                decisions_by_horizon=decisions,
                has_divergent_decisions=len(set(decisions.values())) > 1,
                note=(
                    "Same ticker can carry different decisions per horizon; "
                    "this is expected and intentional."
                ),
            )
        )
    return comparisons


def build_opportunity_queue_validation_summary(
    *,
    horizon_views: list[HorizonCandidateView],
    routed: dict[QueueKind, list[HorizonCandidateView]],
    comparisons: list[CrossHorizonCandidateComparison],
    theme_count: int,
) -> OpportunityQueueValidationSummary:
    """Deterministic, safe validation summary of the queue."""
    issues: list[str] = []

    def _count(kind: QueueKind) -> int:
        return len(routed.get(kind, []))

    distinct = {(v.theme_id, v.ticker) for v in horizon_views}
    multi = sum(1 for c in comparisons if c.has_divergent_decisions)
    with_warnings = sum(1 for v in horizon_views if v.warnings)
    missing_ev = sum(
        1
        for v in horizon_views
        if v.evidence_coverage.coverage in ("none", "unknown")
    )
    crowded_downgrade = sum(
        1
        for v in horizon_views
        if v.decision_label
        in ("wait_for_pullback", "too_extended", "avoid_too_crowded")
        and v.crowding_risk.is_elevated
    )
    trade_now = sum(1 for v in horizon_views if v.decision_label == "trade_now")

    # Safety invariant: no trade_now should survive with poor entry quality or
    # elevated crowding. (Decision logic enforces this; this re-checks it.)
    unsafe = [
        v
        for v in horizon_views
        if v.decision_label == "trade_now"
        and (v.entry_quality_score.band in ("poor", "fair") or v.crowding_risk.is_elevated)
    ]
    if unsafe:
        issues.append(
            f"{len(unsafe)} trade_now candidate(s) with poor entry / crowding "
            "(invariant violation)"
        )

    return OpportunityQueueValidationSummary(
        total_horizon_candidates=len(horizon_views),
        short_term_count=_count("short_term_trade"),
        mid_term_count=_count("mid_term_position"),
        long_term_count=_count("long_term_investment"),
        watch_wait_count=_count("watch_wait"),
        research_more_count=_count("research_more"),
        no_trade_avoid_count=_count("no_trade_avoid"),
        trade_now_count=trade_now,
        distinct_tickers=len(distinct),
        distinct_theme_candidate_opportunities=len(distinct),
        multi_horizon_ticker_count=multi,
        candidates_with_warnings=with_warnings,
        missing_evidence_count=missing_ev,
        crowded_downgrade_count=crowded_downgrade,
        is_safe_empty=(theme_count == 0),
        no_unsafe_trade_now=(len(unsafe) == 0),
        issues=issues,
    )


def build_horizon_aware_opportunity_queue(
    snapshot: ThemeIntelligenceSnapshot,
    *,
    label: str = "default",
) -> HorizonAwareOpportunityQueueView:
    """Build the full horizon-aware opportunity queue from a theme snapshot.

    Deterministic and offline. An empty theme universe yields safe empty
    queues. Missing candidate data yields warnings, not fabricated candidates.
    """
    themes = list(snapshot.universe.themes)

    normalized: list[OpportunityCandidateView] = []
    horizon_views: list[HorizonCandidateView] = []
    routed: dict[QueueKind, list[HorizonCandidateView]] = {k: [] for k in QUEUE_KINDS}

    for theme in themes:
        candidates = _collect_theme_candidates(theme)
        for candidate in candidates:
            ctx = _candidate_context(candidate, theme)
            normalized.append(
                build_opportunity_candidate_from_theme_candidate(candidate, theme)
            )
            for h in OPPORTUNITY_HORIZONS:
                view = _build_horizon_candidate_view(candidate, theme, h, ctx)
                horizon_views.append(view)
                routed[_route_queue_kind(view.decision_label, h)].append(view)

    comparisons = build_cross_horizon_candidate_comparison(horizon_views)

    short_q = ShortTermTradeQueue(
        candidates=routed["short_term_trade"],
        count=len(routed["short_term_trade"]),
    )
    mid_q = MidTermPositionQueue(
        candidates=routed["mid_term_position"],
        count=len(routed["mid_term_position"]),
    )
    long_q = LongTermInvestmentQueue(
        candidates=routed["long_term_investment"],
        count=len(routed["long_term_investment"]),
    )
    watch_q = WatchWaitQueue(
        candidates=routed["watch_wait"], count=len(routed["watch_wait"])
    )
    research_q = ResearchMoreQueue(
        candidates=routed["research_more"], count=len(routed["research_more"])
    )
    no_trade_q = NoTradeAvoidQueue(
        candidates=routed["no_trade_avoid"], count=len(routed["no_trade_avoid"])
    )

    validation = build_opportunity_queue_validation_summary(
        horizon_views=horizon_views,
        routed=routed,
        comparisons=comparisons,
        theme_count=len(themes),
    )

    warnings: list[OpportunityQueueWarning] = [
        OpportunityQueueWarning(
            warning_type="heat_not_buy_signal",
            severity="info",
            message=(
                "Theme heat is not a buy signal. This queue is a view-model "
                "contract only; final trade / allocation / option decisions "
                "occur later after Auto Research Pack + Agent Debate + Decision "
                "Packet. Not investment advice."
            ),
        )
    ]
    if not themes:
        warnings.append(
            OpportunityQueueWarning(
                warning_type="missing_evidence",
                severity="info",
                message="Empty theme universe; safe empty opportunity queues.",
            )
        )

    return HorizonAwareOpportunityQueueView(
        queue_id=make_opportunity_queue_id(label),
        as_of=snapshot.as_of,
        source_theme_snapshot_id=snapshot.snapshot_id,
        description=(
            "Horizon-aware opportunity queue derived from a Phase 5J Theme "
            "Intelligence snapshot. Opportunity-first, horizon-aware, "
            "evidence-gated. Heat is not a buy signal; this is not a final "
            "trade recommendation."
        ),
        short_term=short_q,
        mid_term=mid_q,
        long_term=long_q,
        watch_wait=watch_q,
        research_more=research_q,
        no_trade_avoid=no_trade_q,
        candidates=normalized,
        cross_horizon_comparisons=comparisons,
        validation_summary=validation,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Fixtures — deterministic examples only (NOT live market claims)
# ---------------------------------------------------------------------------


def build_opportunity_queue_from_default_theme_snapshot() -> (
    HorizonAwareOpportunityQueueView
):
    """Build the opportunity queue from the Phase 5J default theme snapshot
    (AI + Space + degraded embodied-AI)."""
    return build_horizon_aware_opportunity_queue(
        build_default_theme_intelligence_snapshot(), label="default"
    )


def build_default_opportunity_queue_view() -> HorizonAwareOpportunityQueueView:
    """Deterministic default opportunity queue view (alias of the default
    theme-snapshot build)."""
    return build_opportunity_queue_from_default_theme_snapshot()


def build_degraded_opportunity_queue_view() -> HorizonAwareOpportunityQueueView:
    """Opportunity queue built from ONLY the degraded / emerging theme fixture.

    Demonstrates safe degraded behavior: partial / no evidence pushes
    candidates into research_more / insufficient_evidence with warnings, and no
    fabricated actionable candidates.
    """
    snapshot = ThemeIntelligenceSnapshot(
        snapshot_id="themeintel_degraded_only",
        as_of=SAMPLE_THEME_AS_OF,
        description="Degraded-only Phase 5J theme snapshot for Phase 5K.",
        universe=ThemeUniverseSnapshot(
            as_of=SAMPLE_THEME_AS_OF,
            description="Single emerging embodied-AI theme (degraded).",
            themes=[build_degraded_theme_fixture()],
        ),
    )
    return build_horizon_aware_opportunity_queue(snapshot, label="degraded")


def build_empty_opportunity_queue_view() -> HorizonAwareOpportunityQueueView:
    """Safe empty opportunity queue (empty theme universe)."""
    return build_horizon_aware_opportunity_queue(
        build_empty_theme_intelligence_snapshot(), label="empty"
    )
