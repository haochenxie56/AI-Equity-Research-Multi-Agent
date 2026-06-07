"""
lib/reliability/horizon.py

Standalone schema models and helper functions for horizon-aware investment
reasoning.

Design principles:
  - Pure Pydantic v2 models; no Streamlit, no LLM calls, no file I/O.
  - Reuses EvidenceRef and AgentConfidence from lib.reliability.schemas.
  - Three explicit investment horizons: short_term, medium_term, long_term.
  - Schemas define the data contract only — they do not compute facts,
    manage positions, or call the Claude API.
  - Position sizing belongs to a future Allocation phase.
  - Option payoff belongs to a future Option Tool phase.
  - UI cards belong to a future Cockpit phase.

See docs/reliability_phase_2b_investment_horizon_schema.md for full design
rationale and rollout context.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.schemas import AgentConfidence, EvidenceRef


# ---------------------------------------------------------------------------
# Horizon type alias
# ---------------------------------------------------------------------------

InvestmentHorizon = Literal["short_term", "medium_term", "long_term"]

_ALL_HORIZONS: tuple[InvestmentHorizon, ...] = (
    "short_term",
    "medium_term",
    "long_term",
)


# ---------------------------------------------------------------------------
# Default evidence category definitions
# ---------------------------------------------------------------------------

# Evidence categories expected by each horizon.  These are advisory defaults;
# later phases may specialise or override them per research context.

_DEFAULT_SHORT_TERM_REQUIRED: list[str] = ["technical", "price_volume", "event"]
_DEFAULT_SHORT_TERM_PREFERRED: list[str] = ["options_flow", "news_sentiment"]

_DEFAULT_MEDIUM_TERM_REQUIRED: list[str] = [
    "catalyst",
    "earnings",
    "estimate_revision",
    "valuation",
    "sector_rotation",
]
_DEFAULT_MEDIUM_TERM_PREFERRED: list[str] = ["macro", "relative_strength"]

_DEFAULT_LONG_TERM_REQUIRED: list[str] = [
    "business_quality",
    "financials",
    "valuation",
    "moat",
    "management",
    "capital_allocation",
]
_DEFAULT_LONG_TERM_PREFERRED: list[str] = ["esg", "regulatory", "macro"]


# ---------------------------------------------------------------------------
# 1. HorizonEvidenceRequirement
# ---------------------------------------------------------------------------

class HorizonEvidenceRequirement(BaseModel):
    """
    Specifies which evidence categories are required or preferred for a
    given investment horizon.

    This is a planning contract only.  It does not validate live evidence
    against tool results — that belongs to the ValidationReport layer.

    Fields:
        horizon: One of ``"short_term"``, ``"medium_term"``, ``"long_term"``.
        required_evidence_categories: Categories that MUST be present for a
            well-formed decision at this horizon.
        preferred_evidence_categories: Categories that are useful but not
            strictly required.
        description: Optional free-form annotation.
    """

    model_config = ConfigDict(extra="forbid")

    horizon: InvestmentHorizon
    required_evidence_categories: list[str] = Field(default_factory=list)
    preferred_evidence_categories: list[str] = Field(default_factory=list)
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# 2. HorizonRisk
# ---------------------------------------------------------------------------

class HorizonRisk(BaseModel):
    """
    A horizon-specific risk with optional evidence references.

    Fields:
        horizon: Investment horizon this risk applies to.
        risk_type: Short label (e.g. ``"earnings_miss"``, ``"macro_shock"``).
        description: Human-readable description of the risk.
        severity: Impact level — ``"low"``, ``"medium"``, ``"high"``,
            or ``"critical"``.
        evidence_refs: Supporting ToolResult evidence for this risk.
        invalidation_trigger: Condition that would eliminate or negate this
            risk (optional).
    """

    model_config = ConfigDict(extra="forbid")

    horizon: InvestmentHorizon
    risk_type: str = Field(min_length=1)
    description: str = Field(min_length=1)
    severity: Literal["low", "medium", "high", "critical"]
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    invalidation_trigger: Optional[str] = None


# ---------------------------------------------------------------------------
# 3. HorizonThesis
# ---------------------------------------------------------------------------

class HorizonThesis(BaseModel):
    """
    The investment thesis for a specific horizon.

    Fields:
        horizon: Investment horizon this thesis covers.
        thesis: Core thesis statement (non-empty).
        supporting_points: Bullet-point elaborations (each non-empty).
        evidence_refs: ToolResult evidence supporting this thesis.
        confidence: Agent confidence assessment (optional).
        invalidation_conditions: Conditions that would invalidate the thesis.
    """

    model_config = ConfigDict(extra="forbid")

    horizon: InvestmentHorizon
    thesis: str = Field(min_length=1)
    supporting_points: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    confidence: Optional[AgentConfidence] = None
    invalidation_conditions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_supporting_points_non_empty(self) -> "HorizonThesis":
        for i, pt in enumerate(self.supporting_points):
            if not pt or not pt.strip():
                raise ValueError(
                    f"supporting_points[{i}] must be a non-empty string."
                )
        return self


# ---------------------------------------------------------------------------
# 4. HorizonRecommendation
# ---------------------------------------------------------------------------

HorizonAction = Literal[
    "buy",
    "hold",
    "trim",
    "exit",
    "avoid",
    "wait",
    "add_on_pullback",
    "add_on_breakout",
    "no_action",
]


class HorizonRecommendation(BaseModel):
    """
    A horizon-specific action recommendation with supporting evidence.

    Fields:
        horizon: Investment horizon this recommendation applies to.
        action: One of the allowed action literals.
        rationale: Human-readable rationale (non-empty).
        confidence: Agent confidence assessment (optional).
        evidence_refs: ToolResult evidence supporting this recommendation.
        entry_condition: Suggested entry trigger (optional).
        exit_condition: Suggested exit trigger (optional).
        review_trigger: Condition that should prompt a review (optional).
        invalidation_trigger: Condition that would invalidate this
            recommendation (optional).
    """

    model_config = ConfigDict(extra="forbid")

    horizon: InvestmentHorizon
    action: HorizonAction
    rationale: str = Field(min_length=1)
    confidence: Optional[AgentConfidence] = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    entry_condition: Optional[str] = None
    exit_condition: Optional[str] = None
    review_trigger: Optional[str] = None
    invalidation_trigger: Optional[str] = None


# ---------------------------------------------------------------------------
# 5. HorizonTradePlan
# ---------------------------------------------------------------------------

HorizonInstrument = Literal[
    "stock",
    "option",
    "cash",
    "watchlist",
    "no_trade",
    "undetermined",
]


class HorizonTradePlan(BaseModel):
    """
    Descriptive trade plan for a given horizon.

    This model captures WHAT to do and WHEN — not HOW MUCH.
    Position sizing belongs to the future Allocation phase.
    Option payoff/chain analysis belongs to the future Option Tool phase.

    Fields:
        horizon: Investment horizon this plan covers.
        preferred_instrument: The instrument type most appropriate for this
            horizon and action.
        entry_zone: Descriptive price or condition range for entry.
        add_zone: Descriptive price or condition range to add.
        trim_zone: Descriptive price or condition range to reduce.
        stop_loss: Stop-loss description (not a hard numeric calc here).
        target_zone: Target price or condition range.
        max_risk_note: Brief qualitative note on maximum risk tolerance.
        time_stop: Condition or date after which the thesis is re-evaluated.
        review_trigger: Event or level that triggers a plan review.
        evidence_refs: ToolResult evidence supporting this plan.
    """

    model_config = ConfigDict(extra="forbid")

    horizon: InvestmentHorizon
    preferred_instrument: HorizonInstrument = "undetermined"
    entry_zone: Optional[str] = None
    add_zone: Optional[str] = None
    trim_zone: Optional[str] = None
    stop_loss: Optional[str] = None
    target_zone: Optional[str] = None
    max_risk_note: Optional[str] = None
    time_stop: Optional[str] = None
    review_trigger: Optional[str] = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 6. HorizonDecisionSet
# ---------------------------------------------------------------------------

class HorizonDecisionSet(BaseModel):
    """
    Container for all horizon outputs for one research target.

    Partial data is explicitly allowed — a decision set may cover only one
    or two horizons at first.  All list fields default to empty.

    Fields:
        target: Ticker symbol or research target name (non-empty).
        schema_version: Version of this schema contract.
        theses: Horizon theses by any subset of horizons.
        risks: Horizon risks by any subset of horizons.
        recommendations: Horizon recommendations by any subset of horizons.
        trade_plans: Horizon trade plans by any subset of horizons.
        evidence_requirements: Horizon evidence requirements (may be default
            or customised for this target).
    """

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    schema_version: str = "1.0"
    theses: list[HorizonThesis] = Field(default_factory=list)
    risks: list[HorizonRisk] = Field(default_factory=list)
    recommendations: list[HorizonRecommendation] = Field(default_factory=list)
    trade_plans: list[HorizonTradePlan] = Field(default_factory=list)
    evidence_requirements: list[HorizonEvidenceRequirement] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper 1: default_horizon_evidence_requirements
# ---------------------------------------------------------------------------

def default_horizon_evidence_requirements() -> list[HorizonEvidenceRequirement]:
    """
    Return default evidence requirements for all three investment horizons.

    Returns:
        A list of three ``HorizonEvidenceRequirement`` instances — one each
        for ``"short_term"``, ``"medium_term"``, and ``"long_term"``.

    Examples::

        reqs = default_horizon_evidence_requirements()
        assert len(reqs) == 3
        horizons = {r.horizon for r in reqs}
        assert "short_term" in horizons
    """
    return [
        HorizonEvidenceRequirement(
            horizon="short_term",
            required_evidence_categories=list(_DEFAULT_SHORT_TERM_REQUIRED),
            preferred_evidence_categories=list(_DEFAULT_SHORT_TERM_PREFERRED),
            description=(
                "Short-term evidence focuses on price action, volume patterns, "
                "and near-term catalysts or event risk."
            ),
        ),
        HorizonEvidenceRequirement(
            horizon="medium_term",
            required_evidence_categories=list(_DEFAULT_MEDIUM_TERM_REQUIRED),
            preferred_evidence_categories=list(_DEFAULT_MEDIUM_TERM_PREFERRED),
            description=(
                "Medium-term evidence includes earnings outlook, estimate "
                "revisions, sector rotation dynamics, and relative valuation."
            ),
        ),
        HorizonEvidenceRequirement(
            horizon="long_term",
            required_evidence_categories=list(_DEFAULT_LONG_TERM_REQUIRED),
            preferred_evidence_categories=list(_DEFAULT_LONG_TERM_PREFERRED),
            description=(
                "Long-term evidence assesses business quality, financial "
                "durability, competitive moat, management quality, and "
                "capital allocation history."
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# Helper 2: group_horizon_decisions_by_horizon
# ---------------------------------------------------------------------------

def group_horizon_decisions_by_horizon(
    decision_set: HorizonDecisionSet,
) -> dict[str, dict[str, list]]:
    """
    Group all entries in *decision_set* by investment horizon.

    Returns:
        A ``dict`` keyed by ``"short_term"``, ``"medium_term"``, and
        ``"long_term"``.  Each value is a dict with keys:

        - ``"theses"``
        - ``"risks"``
        - ``"recommendations"``
        - ``"trade_plans"``
        - ``"evidence_requirements"``

        Horizons that have no entries will have empty lists for all keys.

    Examples::

        ds = HorizonDecisionSet(target="AAPL", theses=[...])
        grouped = group_horizon_decisions_by_horizon(ds)
        grouped["short_term"]["theses"]  # → list of short-term theses
    """
    result: dict[str, dict[str, list]] = {
        h: {
            "theses": [],
            "risks": [],
            "recommendations": [],
            "trade_plans": [],
            "evidence_requirements": [],
        }
        for h in _ALL_HORIZONS
    }

    for obj in decision_set.theses:
        result[obj.horizon]["theses"].append(obj)
    for obj in decision_set.risks:
        result[obj.horizon]["risks"].append(obj)
    for obj in decision_set.recommendations:
        result[obj.horizon]["recommendations"].append(obj)
    for obj in decision_set.trade_plans:
        result[obj.horizon]["trade_plans"].append(obj)
    for obj in decision_set.evidence_requirements:
        result[obj.horizon]["evidence_requirements"].append(obj)

    return result


# ---------------------------------------------------------------------------
# Helper 3: summarize_horizon_coverage
# ---------------------------------------------------------------------------

def summarize_horizon_coverage(
    decision_set: HorizonDecisionSet,
) -> dict[str, object]:
    """
    Return a concise coverage summary for *decision_set*.

    Returns:
        A ``dict`` with:

        - ``"target"`` (str): The research target.
        - ``"present_horizons"`` (list[str]): Horizons that have at least one
          thesis, risk, recommendation, or trade plan.
        - ``"missing_horizons"`` (list[str]): Horizons that have no entries.
        - ``"counts"`` (dict): Per-horizon counts for theses, risks,
          recommendations, and trade_plans.
        - ``"total_theses"`` (int): Total theses across all horizons.
        - ``"total_risks"`` (int): Total risks across all horizons.
        - ``"total_recommendations"`` (int): Total recommendations across
          all horizons.
        - ``"total_trade_plans"`` (int): Total trade plans across all horizons.

    Examples::

        summary = summarize_horizon_coverage(ds)
        summary["present_horizons"]  # → ["short_term"]
        summary["missing_horizons"]  # → ["medium_term", "long_term"]
    """
    grouped = group_horizon_decisions_by_horizon(decision_set)

    counts: dict[str, dict[str, int]] = {}
    present: list[str] = []
    missing: list[str] = []

    for h in _ALL_HORIZONS:
        g = grouped[h]
        n_theses = len(g["theses"])
        n_risks = len(g["risks"])
        n_recs = len(g["recommendations"])
        n_plans = len(g["trade_plans"])
        counts[h] = {
            "theses": n_theses,
            "risks": n_risks,
            "recommendations": n_recs,
            "trade_plans": n_plans,
        }
        if n_theses + n_risks + n_recs + n_plans > 0:
            present.append(h)
        else:
            missing.append(h)

    return {
        "target": decision_set.target,
        "present_horizons": present,
        "missing_horizons": missing,
        "counts": counts,
        "total_theses": len(decision_set.theses),
        "total_risks": len(decision_set.risks),
        "total_recommendations": len(decision_set.recommendations),
        "total_trade_plans": len(decision_set.trade_plans),
    }


# ---------------------------------------------------------------------------
# Helper 4: validate_horizon_decision_set
# ---------------------------------------------------------------------------

_ACTIVE_ACTIONS: frozenset[str] = frozenset(
    {"buy", "add_on_pullback", "add_on_breakout"}
)


def validate_horizon_decision_set(
    decision_set: HorizonDecisionSet,
) -> list[str]:
    """
    Perform lightweight advisory validation on *decision_set*.

    Returns warning strings for soft issues.  Does not raise exceptions.
    Does not integrate with ``ValidationReport`` in this phase.

    Checked conditions:

    +------------------------------------------------------------------+
    | Condition                                                        |
    +==================================================================+
    | No recommendations at all                                       |
    +------------------------------------------------------------------+
    | No theses at all                                                 |
    +------------------------------------------------------------------+
    | Recommendation with no evidence_refs                             |
    +------------------------------------------------------------------+
    | Thesis with no evidence_refs                                     |
    +------------------------------------------------------------------+
    | Trade plan with preferred_instrument="option" and no evidence    |
    +------------------------------------------------------------------+
    | Active action (buy/add) with no invalidation_trigger or          |
    | review_trigger                                                   |
    +------------------------------------------------------------------+
    | Duplicate recommendations for the same horizon                   |
    +------------------------------------------------------------------+

    Args:
        decision_set: ``HorizonDecisionSet`` to validate.

    Returns:
        List of warning strings (may be empty for a clean set).

    Examples::

        warnings = validate_horizon_decision_set(ds)
        assert all(isinstance(w, str) for w in warnings)
    """
    warnings: list[str] = []

    if not decision_set.recommendations:
        warnings.append(
            "HorizonDecisionSet has no recommendations. "
            "At least one horizon recommendation is expected."
        )

    if not decision_set.theses:
        warnings.append(
            "HorizonDecisionSet has no theses. "
            "At least one horizon thesis is expected."
        )

    for rec in decision_set.recommendations:
        if not rec.evidence_refs:
            warnings.append(
                f"HorizonRecommendation for horizon='{rec.horizon}' "
                f"action='{rec.action}' has no evidence_refs. "
                "Recommendations should be evidence-linked."
            )
        if rec.action in _ACTIVE_ACTIONS:
            if not rec.invalidation_trigger and not rec.review_trigger:
                warnings.append(
                    f"HorizonRecommendation for horizon='{rec.horizon}' "
                    f"action='{rec.action}' has neither invalidation_trigger "
                    "nor review_trigger. Active buy/add actions should define "
                    "at least one exit or review condition."
                )

    for thesis in decision_set.theses:
        if not thesis.evidence_refs:
            warnings.append(
                f"HorizonThesis for horizon='{thesis.horizon}' has no evidence_refs. "
                "Theses should cite supporting evidence."
            )

    for plan in decision_set.trade_plans:
        if plan.preferred_instrument == "option" and not plan.evidence_refs:
            warnings.append(
                f"HorizonTradePlan for horizon='{plan.horizon}' uses "
                "preferred_instrument='option' but has no evidence_refs. "
                "Option trade plans should cite supporting evidence."
            )

    # Detect duplicate recommendations for the same horizon
    seen_horizons: set[str] = set()
    for rec in decision_set.recommendations:
        if rec.horizon in seen_horizons:
            warnings.append(
                f"Duplicate HorizonRecommendation for horizon='{rec.horizon}'. "
                "Each horizon should have at most one recommendation."
            )
        seen_horizons.add(rec.horizon)

    return warnings
