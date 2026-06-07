"""
lib/reliability/phase5_agent_debate.py

Phase 5M: Agent Debate / Decision Workspace Contract.

Purpose
-------
Define the **deterministic contracts** for how a future Investment Cockpit will
structure agent debate and decision-workspace review **after** a Phase 5L
Research Pack has been assembled:

    Phase 5K Opportunity Candidate
      -> Phase 5L Research Pack (ResearchPackBundle / boundary)
      -> Phase 5M Agent Debate / Decision Workspace   (this module)
      -> (future) Phase 5N Cockpit UI v0.2

This module defines the **contract only**. It does **not**:

- run any real agent (bull / bear / risk / critic / allocation / option /
  synthesis are deterministic *role records*, never live model calls);
- call any LLM or external API;
- fetch any live data;
- read the live workflow state JSON;
- introduce any database / vector store / production persistence;
- introduce any broker / order / execution capability;
- produce a final buy/sell recommendation or an executable trading instruction.

Core principles
---------------
- The Research Pack is **input, not final decision**.
- Debate is **evidence-first** and **horizon-aware**.
- Bull / Bear / Risk / Critic perspectives are **separated**.
- Allocation and Option perspectives are **review-only planning** perspectives;
  they never create an executable allocation or an executable option order.
- The Decision Workspace **summarizes debate state**; it is not an executable
  order system.
- Missing evidence produces ``research_more`` / ``no_decision`` /
  ``insufficient_evidence`` states — never a fabricated decision.
- Conflicting agent stances are **explicit** (``DebateConflictRecord``), never
  hidden — in particular the Critic does not hide an unresolved conflict.
- The final trade / allocation / option plan remains **non-executable** and
  requires later human review.

Safety invariants (by construction)
-----------------------------------
- Every model sets ``extra="forbid"`` — no ``approved_for_execution`` or
  order-ticket field can be smuggled in via construction.
- No model declares ``approved_for_execution`` (it is absent, not False-only),
  no buy/sell field, and no executable order field.
- Agent stance records carry ``is_live_agent_output=False``; participants carry
  ``is_live_agent=False``.
- ``AllocationPerspectiveView.is_executable_allocation`` and
  ``OptionPerspectiveView.is_executable_order`` are hard-coded ``False``;
  ``DecisionWorkspaceView.is_executable_decision`` is hard-coded ``False``.

Disclaimer: outputs are for research / educational purposes only and do not
constitute investment advice.

See ``docs/reliability_phase_5m_agent_debate_decision_workspace.md``.
"""

from __future__ import annotations

import hashlib
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from lib.reliability.phase5_theme_intelligence import ThemeRiskSeverity
from lib.reliability.phase5_opportunity_queue import OpportunityHorizon
from lib.reliability.phase5_research_pack import (
    AutoResearchPackOrchestrationBoundary,
    ResearchPackBundle,
    ResearchPackEvidenceGap,
    ResearchPackRequest,
    build_default_research_pack_bundle,
    build_degraded_research_pack_bundle,
    build_empty_research_pack_bundle,
    build_research_module_requests,
    build_research_pack_bundle_from_fixture,
    make_research_pack_request_id,
)

_SCHEMA_VERSION: str = "phase5_agent_debate_v1"


# ---------------------------------------------------------------------------
# Literal aliases — roles
# ---------------------------------------------------------------------------

# Deterministic participant roles. These are role *records* only — no live
# agent is ever invoked in Phase 5M.
AgentRole = Literal[
    "bull",
    "bear",
    "risk",
    "critic",
    "allocation",
    "option",
    "synthesis",
]

AGENT_ROLES: tuple[AgentRole, ...] = (
    "bull",
    "bear",
    "risk",
    "critic",
    "allocation",
    "option",
    "synthesis",
)

# The six roles that produce an explicit stance record (synthesis is expressed
# through the consensus summary, not a stance).
DEBATE_STANCE_ROLES: tuple[AgentRole, ...] = (
    "bull",
    "bear",
    "risk",
    "critic",
    "allocation",
    "option",
)

DebateConfidence = Literal["high", "medium", "low", "unknown"]


# ---------------------------------------------------------------------------
# Literal aliases — per-role stance labels
# ---------------------------------------------------------------------------

BullStanceLabel = Literal[
    "constructive",
    "bullish_with_conditions",
    "wait_for_better_entry",
    "insufficient_evidence",
]

BearStanceLabel = Literal[
    "overextended",
    "valuation_risk",
    "thesis_weak",
    "crowded_trade",
    "insufficient_evidence",
]

RiskStanceLabel = Literal[
    "acceptable",
    "elevated",
    "high",
    "unacceptable",
    "unknown",
]

CriticStanceLabel = Literal[
    "pass_with_warnings",
    "needs_more_evidence",
    "conflict_unresolved",
    "reject_for_now",
    "no_decision",
]

AllocationStanceLabel = Literal[
    "no_allocation",
    "watchlist_only",
    "small_starter",
    "position_candidate",
    "avoid",
]

OptionStanceLabel = Literal[
    "no_trade",
    "stock_preferred",
    "option_candidate",
    "insufficient_liquidity",
    "event_risk_too_high",
]

# Union of every distinct stance label (used on the generic AgentStanceRecord).
AgentStanceLabel = Literal[
    # bull
    "constructive",
    "bullish_with_conditions",
    "wait_for_better_entry",
    # bear
    "overextended",
    "valuation_risk",
    "thesis_weak",
    "crowded_trade",
    # risk
    "acceptable",
    "elevated",
    "high",
    "unacceptable",
    # critic
    "pass_with_warnings",
    "needs_more_evidence",
    "conflict_unresolved",
    "reject_for_now",
    "no_decision",
    # allocation
    "no_allocation",
    "watchlist_only",
    "small_starter",
    "position_candidate",
    "avoid",
    # option
    "no_trade",
    "stock_preferred",
    "option_candidate",
    "insufficient_liquidity",
    "event_risk_too_high",
    # shared
    "insufficient_evidence",
    "unknown",
]


# ---------------------------------------------------------------------------
# Literal aliases — conflict / consensus / workspace state
# ---------------------------------------------------------------------------

DebateConflictType = Literal[
    "bull_bear_disagreement",
    "risk_override",
    "evidence_dispute",
    "valuation_dispute",
    "crowding_dispute",
    "horizon_disagreement",
    "option_disagreement",
    "unknown",
]

DebateConsensusLevel = Literal[
    "strong_consensus",
    "moderate_consensus",
    "mixed",
    "conflict_unresolved",
    "insufficient_evidence",
]

# Review states only — NOT execution commands.
DecisionWorkspaceStatus = Literal[
    "ready_for_review",
    "research_more",
    "wait_for_pullback",
    "watchlist",
    "no_decision",
    "no_trade",
    "blocked",
    "invalidated",
    "unknown",
]

DECISION_WORKSPACE_STATUSES: tuple[DecisionWorkspaceStatus, ...] = (
    "ready_for_review",
    "research_more",
    "wait_for_pullback",
    "watchlist",
    "no_decision",
    "no_trade",
    "blocked",
    "invalidated",
    "unknown",
)

# Review-only next actions — NONE of these are order instructions.
DecisionWorkspaceNextActionType = Literal[
    "review",
    "research_more",
    "wait_for_pullback",
    "watch",
    "skip",
    "no_trade",
    "escalate_to_human",
]

DEBATE_CONSENSUS_LEVELS: tuple[DebateConsensusLevel, ...] = (
    "strong_consensus",
    "moderate_consensus",
    "mixed",
    "conflict_unresolved",
    "insufficient_evidence",
)

DebateWarningType = Literal[
    "missing_evidence",
    "degraded_upstream",
    "conflict_unresolved",
    "no_trade_review_only",
    "empty_pack",
    "review_required",
    "unknown",
]


# ---------------------------------------------------------------------------
# Decision label groupings (deterministic, fixture/helper only)
# ---------------------------------------------------------------------------

# Strongly constructive Phase 5K decisions a Bull reads as a positive case.
_READY_DECISIONS: tuple[str, ...] = (
    "trade_now",
    "position_candidate",
    "investment_candidate",
    "thesis_durable",
)

# Conditional-constructive decisions (positive but with caveats).
_CONDITIONAL_DECISIONS: tuple[str, ...] = (
    "breakout_watch",
    "event_trade_watch",
    "compounder_watch",
    "thesis_improving",
    "accumulate_on_pullback",
    "wait_for_earnings_confirmation",
)

# Wait / better-entry decisions.
_WAIT_DECISIONS: tuple[str, ...] = (
    "wait_for_pullback",
    "too_extended",
    "accumulate_on_pullback",
)

# Watch / monitor decisions (no action yet, but not a no-trade).
_WATCHLIST_DECISIONS: tuple[str, ...] = (
    "breakout_watch",
    "event_trade_watch",
    "compounder_watch",
    "watch_for_valuation",
    "quality_but_expensive",
    "thesis_improving",
    "wait_for_earnings_confirmation",
    "watch_wait",
)

# Research / insufficient-evidence decisions.
_RESEARCH_DECISIONS: tuple[str, ...] = (
    "research_more",
    "insufficient_evidence",
    "thesis_unconfirmed",
    "thesis_insufficient",
)

# No-trade / avoid decisions (review-only).
_NO_TRADE_DECISIONS: tuple[str, ...] = ("no_trade", "avoid_too_crowded")

# Modules each role conceptually leans on (for evidence references). Phase 5M
# never executes them; these are planned-module references only.
_ROLE_MODULES: dict[AgentRole, tuple[str, ...]] = {
    "bull": ("company_research", "financial_analysis", "theme_context", "catalyst_earnings"),
    "bear": ("risk_review", "price_volume_analysis", "financial_analysis"),
    "risk": ("risk_review", "price_volume_analysis", "macro_context"),
    "critic": ("evidence_validation", "risk_review"),
    "allocation": ("financial_analysis", "risk_review"),
    "option": ("price_volume_analysis", "catalyst_earnings", "risk_review"),
    "synthesis": ("evidence_validation",),
}

_SEVERITY_RANK: dict[str, int] = {"info": 0, "low": 1, "medium": 2, "high": 3}


# ---------------------------------------------------------------------------
# Deterministic id helpers (no timestamp, no randomness)
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


def _dedup(seq) -> list:
    """Order-preserving de-duplication."""
    seen: set = set()
    out: list = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def make_debate_session_id(
    ticker: str, theme_id: str, horizon: str, decision: str
) -> str:
    """Deterministic, content-sensitive debate-session id."""
    payload = f"dbsess::{ticker}::{theme_id}::{horizon}::{decision}"
    return f"dbsess_{_slug(ticker)}_{_slug(horizon)}_{_short_hash(payload)}"


def make_agent_stance_id(session_id: str, role: str) -> str:
    """Deterministic stance id keyed by session + role."""
    return f"stance_{_slug(role)}_{_short_hash('stance::' + str(session_id) + '::' + str(role))}"


def make_decision_workspace_view_id(session_id: str) -> str:
    """Deterministic decision-workspace-view id derived from a session id."""
    return f"dwview_{_short_hash('dwview::' + str(session_id))}"


def make_agent_debate_workspace_id(label: str) -> str:
    """Deterministic agent-debate-workspace id from a stable label."""
    return f"adw_{_slug(label)}_{_short_hash('adw::' + str(label))}"


# ---------------------------------------------------------------------------
# Safety banner
# ---------------------------------------------------------------------------


class DecisionWorkspaceSafetyBanner(BaseModel):
    """Always-on safety banner. Deliberately omits ``approved_for_execution``.

    The non-authorization of execution is expressed by ``no_execution_authorized``
    (a positive ``True`` flag) and by the *absence* of any
    ``approved_for_execution`` field — execution is never positively authorized.
    """

    model_config = ConfigDict(extra="forbid")

    is_fixture: Literal[True] = True
    no_live_agents: Literal[True] = True
    no_external_api: Literal[True] = True
    no_orders: Literal[True] = True
    no_final_recommendation: Literal[True] = True
    no_execution_authorized: Literal[True] = True
    requires_human_review: Literal[True] = True
    not_investment_advice: Literal[True] = True
    message: str = (
        "Phase 5M agent debate / decision workspace contract only. Agent roles "
        "are deterministic records, not live model calls. No live data, no LLM, "
        "no external API, no orders, no final recommendation. The decision "
        "workspace is review-only and requires later human review. Not "
        "investment advice."
    )


def build_decision_workspace_safety_banner() -> DecisionWorkspaceSafetyBanner:
    """Return the deterministic Phase 5M safety banner."""
    return DecisionWorkspaceSafetyBanner()


# ---------------------------------------------------------------------------
# Warning model
# ---------------------------------------------------------------------------


class DebateWarning(BaseModel):
    """A non-fatal warning attached to a stance / session / workspace."""

    model_config = ConfigDict(extra="forbid")

    warning_type: DebateWarningType = "unknown"
    severity: ThemeRiskSeverity = "info"
    message: str = ""


# ---------------------------------------------------------------------------
# Participant + stance records
# ---------------------------------------------------------------------------


class AgentDebateParticipant(BaseModel):
    """A deterministic debate participant *role record*.

    This is NOT a live agent. ``is_live_agent`` is hard-coded ``False``.
    """

    model_config = ConfigDict(extra="forbid")

    agent_role: AgentRole
    participant_id: str = Field(min_length=1)
    display_name: str = ""
    description: str = ""
    is_live_agent: Literal[False] = False
    note: str = ""


class AgentStanceRecord(BaseModel):
    """One agent role's deterministic stance on one (ticker, horizon) pack.

    Carries no buy/sell field, no executable order field, and no
    ``approved_for_execution`` field. ``is_live_agent_output`` is hard-coded
    ``False`` — this is a deterministic fixture/contract record, never live
    model output.
    """

    model_config = ConfigDict(extra="forbid")

    stance_id: str = Field(min_length=1)
    agent_role: AgentRole
    ticker: str = Field(min_length=1)
    theme_id: str = ""
    theme_name: str = ""
    horizon: OpportunityHorizon
    stance_label: AgentStanceLabel
    confidence: DebateConfidence = "unknown"
    key_claims: list[str] = Field(default_factory=list)
    supporting_evidence_refs: list[str] = Field(default_factory=list)
    missing_evidence_refs: list[str] = Field(default_factory=list)
    missing_evidence_reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    review_triggers: list[str] = Field(default_factory=list)
    source_research_pack_ids: list[str] = Field(default_factory=list)
    warnings: list[DebateWarning] = Field(default_factory=list)
    created_from_fixture: bool = True
    is_live_agent_output: Literal[False] = False
    rationale: str = ""
    notes: str = ""


# ---------------------------------------------------------------------------
# Per-perspective views
# ---------------------------------------------------------------------------


class _BasePerspectiveView(BaseModel):
    """Shared fields for the bull / bear / risk perspective views."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    theme_id: str = ""
    horizon: OpportunityHorizon
    confidence: DebateConfidence = "unknown"
    key_claims: list[str] = Field(default_factory=list)
    supporting_evidence_refs: list[str] = Field(default_factory=list)
    missing_evidence_refs: list[str] = Field(default_factory=list)
    missing_evidence_reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    warnings: list[DebateWarning] = Field(default_factory=list)
    is_populated: bool = True
    note: str = ""


class BullCaseView(_BasePerspectiveView):
    """The bull perspective (constructive case)."""

    stance_label: BullStanceLabel = "insufficient_evidence"


class BearCaseView(_BasePerspectiveView):
    """The bear perspective (skeptical case)."""

    stance_label: BearStanceLabel = "insufficient_evidence"


class RiskCaseView(_BasePerspectiveView):
    """The risk perspective.

    ``can_downgrade_decision`` flags that the risk read is high enough to
    downgrade an otherwise-constructive workspace state (e.g. to
    ``wait_for_pullback`` / ``research_more``). It never authorizes execution.
    """

    stance_label: RiskStanceLabel = "unknown"
    can_downgrade_decision: bool = False


class CriticReviewView(BaseModel):
    """The critic perspective.

    The critic adjudicates evidence and **must not hide unresolved conflicts**:
    ``hides_unresolved_conflict`` is hard-coded ``False`` and
    ``acknowledged_conflict_ids`` / ``unresolved_conflict_count`` mirror the
    session's conflict records.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    theme_id: str = ""
    horizon: OpportunityHorizon
    stance_label: CriticStanceLabel = "no_decision"
    confidence: DebateConfidence = "unknown"
    key_claims: list[str] = Field(default_factory=list)
    supporting_evidence_refs: list[str] = Field(default_factory=list)
    missing_evidence_reasons: list[str] = Field(default_factory=list)
    acknowledged_conflict_ids: list[str] = Field(default_factory=list)
    unresolved_conflict_count: int = 0
    hides_unresolved_conflict: Literal[False] = False
    warnings: list[DebateWarning] = Field(default_factory=list)
    is_populated: bool = True
    note: str = ""


class AllocationPerspectiveView(BaseModel):
    """The allocation perspective — review-only planning, never executable.

    ``is_executable_allocation`` is hard-coded ``False`` and no order /
    position-size-to-execute field is declared.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    theme_id: str = ""
    horizon: OpportunityHorizon
    stance_label: AllocationStanceLabel = "no_allocation"
    confidence: DebateConfidence = "unknown"
    key_claims: list[str] = Field(default_factory=list)
    supporting_evidence_refs: list[str] = Field(default_factory=list)
    missing_evidence_reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    is_executable_allocation: Literal[False] = False
    warnings: list[DebateWarning] = Field(default_factory=list)
    is_populated: bool = True
    note: str = ""


class OptionPerspectiveView(BaseModel):
    """The option perspective — review-only planning, never executable.

    ``no_trade`` is a first-class state. ``is_executable_order`` is hard-coded
    ``False`` and no option order / leg-to-execute field is declared.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    theme_id: str = ""
    horizon: OpportunityHorizon
    stance_label: OptionStanceLabel = "no_trade"
    confidence: DebateConfidence = "unknown"
    key_claims: list[str] = Field(default_factory=list)
    supporting_evidence_refs: list[str] = Field(default_factory=list)
    missing_evidence_reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    is_no_trade: bool = True
    is_executable_order: Literal[False] = False
    warnings: list[DebateWarning] = Field(default_factory=list)
    is_populated: bool = True
    note: str = ""


# ---------------------------------------------------------------------------
# Conflict / consensus / evidence-coverage models
# ---------------------------------------------------------------------------


class DebateConflictRecord(BaseModel):
    """An explicit conflict between two or more agent stances.

    Conflicts are never hidden. ``is_resolved`` defaults to ``False`` — Phase 5M
    does not silently resolve disagreement; an unresolved conflict drives the
    workspace toward ``research_more`` / ``escalate_to_human``.
    """

    model_config = ConfigDict(extra="forbid")

    conflict_id: str = Field(min_length=1)
    conflict_type: DebateConflictType = "unknown"
    severity: ThemeRiskSeverity = "info"
    roles_in_conflict: list[AgentRole] = Field(default_factory=list)
    stance_labels: list[str] = Field(default_factory=list)
    description: str = ""
    is_resolved: bool = False
    resolution_note: str = ""


class DebateConsensusSummary(BaseModel):
    """Summarizes how aligned the agent stances are.

    Never produces a buy/sell decision; describes consensus *level* only.
    """

    model_config = ConfigDict(extra="forbid")

    consensus_level: DebateConsensusLevel = "insufficient_evidence"
    agreeing_roles: list[AgentRole] = Field(default_factory=list)
    dissenting_roles: list[AgentRole] = Field(default_factory=list)
    neutral_roles: list[AgentRole] = Field(default_factory=list)
    total_conflicts: int = 0
    unresolved_conflict_count: int = 0
    note: str = ""


class DebateEvidenceCoverage(BaseModel):
    """Evidence coverage across the debate (evidence-first accounting)."""

    model_config = ConfigDict(extra="forbid")

    coverage: Literal["complete", "partial", "none", "unknown"] = "unknown"
    total_supporting_evidence_refs: int = 0
    total_missing_evidence_reasons: int = 0
    evidence_gap_count: int = 0
    has_unresolved_evidence_gap: bool = False
    note: str = ""


# ---------------------------------------------------------------------------
# Debate round + session
# ---------------------------------------------------------------------------


class AgentDebateRound(BaseModel):
    """One deterministic debate round holding the per-role stance records."""

    model_config = ConfigDict(extra="forbid")

    round_index: int = 1
    round_label: str = "initial_debate"
    stances: list[AgentStanceRecord] = Field(default_factory=list)
    note: str = ""


class AgentDebateSession(BaseModel):
    """A full deterministic debate session for ONE (ticker, horizon) pack.

    Built from a Phase 5L ``ResearchPackBundle``. Carries no buy/sell field, no
    executable order field, and no ``approved_for_execution`` field.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    schema_version: str = _SCHEMA_VERSION
    ticker: str = Field(min_length=1)
    company_name: Optional[str] = None
    theme_id: str = ""
    theme_name: str = ""
    horizon: OpportunityHorizon
    decision_label: str = ""
    source_pack_request_id: Optional[str] = None
    source_bundle_id: Optional[str] = None
    source_research_pack_ids: list[str] = Field(default_factory=list)
    participants: list[AgentDebateParticipant] = Field(default_factory=list)
    rounds: list[AgentDebateRound] = Field(default_factory=list)
    stances: list[AgentStanceRecord] = Field(default_factory=list)
    bull_case: Optional[BullCaseView] = None
    bear_case: Optional[BearCaseView] = None
    risk_case: Optional[RiskCaseView] = None
    critic_review: Optional[CriticReviewView] = None
    allocation_perspective: Optional[AllocationPerspectiveView] = None
    option_perspective: Optional[OptionPerspectiveView] = None
    conflicts: list[DebateConflictRecord] = Field(default_factory=list)
    consensus_summary: Optional[DebateConsensusSummary] = None
    evidence_coverage: Optional[DebateEvidenceCoverage] = None
    is_review_only: bool = False
    is_degraded: bool = False
    safety_banner: DecisionWorkspaceSafetyBanner = Field(
        default_factory=DecisionWorkspaceSafetyBanner
    )
    warnings: list[DebateWarning] = Field(default_factory=list)
    created_from_fixture: bool = True
    notes: str = ""


# ---------------------------------------------------------------------------
# Decision workspace view models
# ---------------------------------------------------------------------------


class DecisionWorkspaceNextAction(BaseModel):
    """A review-only next action. NOT an order instruction."""

    model_config = ConfigDict(extra="forbid")

    action: DecisionWorkspaceNextActionType = "review"
    description: str = ""


class DecisionWorkspaceRecommendationState(BaseModel):
    """A review-only recommendation *state* (not an executable decision).

    ``is_executable`` is hard-coded ``False`` and ``requires_human_review`` is
    hard-coded ``True``. No ``approved_for_execution`` field is declared.
    """

    model_config = ConfigDict(extra="forbid")

    status: DecisionWorkspaceStatus = "unknown"
    consensus_level: DebateConsensusLevel = "insufficient_evidence"
    supporting_roles: list[AgentRole] = Field(default_factory=list)
    dissenting_roles: list[AgentRole] = Field(default_factory=list)
    rationale: str = ""
    is_executable: Literal[False] = False
    requires_human_review: Literal[True] = True
    note: str = ""


class DecisionWorkspaceView(BaseModel):
    """The decision workspace summary for ONE debate session.

    Summarizes debate state for review. It is **not** an executable order
    system: ``is_executable_decision`` is hard-coded ``False`` and no order /
    broker / execution field is declared.
    """

    model_config = ConfigDict(extra="forbid")

    workspace_view_id: str = Field(min_length=1)
    schema_version: str = _SCHEMA_VERSION
    ticker: str = Field(min_length=1)
    theme_id: str = ""
    theme_name: str = ""
    horizon: OpportunityHorizon
    decision_label: str = ""
    status: DecisionWorkspaceStatus = "unknown"
    recommendation_state: DecisionWorkspaceRecommendationState = Field(
        default_factory=DecisionWorkspaceRecommendationState
    )
    next_action: DecisionWorkspaceNextAction = Field(
        default_factory=DecisionWorkspaceNextAction
    )
    consensus_summary: Optional[DebateConsensusSummary] = None
    conflicts: list[DebateConflictRecord] = Field(default_factory=list)
    evidence_coverage: Optional[DebateEvidenceCoverage] = None
    bull_case: Optional[BullCaseView] = None
    bear_case: Optional[BearCaseView] = None
    risk_case: Optional[RiskCaseView] = None
    critic_review: Optional[CriticReviewView] = None
    allocation_perspective: Optional[AllocationPerspectiveView] = None
    option_perspective: Optional[OptionPerspectiveView] = None
    source_session_id: Optional[str] = None
    source_research_pack_ids: list[str] = Field(default_factory=list)
    requires_human_review: Literal[True] = True
    is_executable_decision: Literal[False] = False
    safety_banner: DecisionWorkspaceSafetyBanner = Field(
        default_factory=DecisionWorkspaceSafetyBanner
    )
    warnings: list[DebateWarning] = Field(default_factory=list)
    notes: str = ""


class DecisionWorkspaceValidationSummary(BaseModel):
    """Deterministic, safe summary of an agent-debate workspace.

    ``is_safe_empty`` is True when there are no sessions (a valid, safe state).
    Safety invariant flags are always True for a well-formed Phase 5M output.
    """

    model_config = ConfigDict(extra="forbid")

    total_sessions: int = 0
    total_workspace_views: int = 0
    total_stances: int = 0
    total_participants: int = 0
    bull_stance_count: int = 0
    bear_stance_count: int = 0
    risk_stance_count: int = 0
    critic_stance_count: int = 0
    allocation_stance_count: int = 0
    option_stance_count: int = 0
    total_conflicts: int = 0
    unresolved_conflict_count: int = 0
    ready_for_review_count: int = 0
    research_more_count: int = 0
    wait_for_pullback_count: int = 0
    watchlist_count: int = 0
    no_trade_count: int = 0
    no_decision_count: int = 0
    blocked_count: int = 0
    strong_consensus_count: int = 0
    conflict_unresolved_count: int = 0
    distinct_tickers: int = 0
    distinct_theme_candidate_workspaces: int = 0
    is_safe_empty: bool = True
    # Safety invariants (always True for a well-formed Phase 5M output).
    no_executable_order_fields: bool = True
    approved_for_execution_absent: bool = True
    no_live_agent_calls: bool = True
    no_final_recommendation: bool = True
    all_stances_fixture: bool = True
    critic_hides_no_conflict: bool = True
    issues: list[str] = Field(default_factory=list)


class AgentDebateWorkspace(BaseModel):
    """Top-level Phase 5M contract: debate sessions + decision-workspace views.

    Built deterministically from a Phase 5L
    ``AutoResearchPackOrchestrationBoundary``. Carries no buy/sell decision, no
    order instruction, no executable order field, and no
    ``approved_for_execution`` field.
    """

    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(min_length=1)
    schema_version: str = _SCHEMA_VERSION
    as_of: Optional[str] = None
    source_boundary_id: Optional[str] = None
    source_queue_id: Optional[str] = None
    source_theme_snapshot_id: Optional[str] = None
    description: str = ""
    sessions: list[AgentDebateSession] = Field(default_factory=list)
    workspace_views: list[DecisionWorkspaceView] = Field(default_factory=list)
    validation_summary: Optional[DecisionWorkspaceValidationSummary] = None
    safety_banner: DecisionWorkspaceSafetyBanner = Field(
        default_factory=DecisionWorkspaceSafetyBanner
    )
    warnings: list[DebateWarning] = Field(default_factory=list)
    is_fixture: bool = True
    notes: str = ""


# ---------------------------------------------------------------------------
# Participants
# ---------------------------------------------------------------------------

_PARTICIPANT_META: dict[AgentRole, tuple[str, str]] = {
    "bull": ("Bull", "Constructive case; argues the opportunity is attractive."),
    "bear": ("Bear", "Skeptical case; argues against the opportunity."),
    "risk": ("Risk", "Risk / crowding / drawdown assessment; can downgrade state."),
    "critic": ("Critic", "Evidence referee; surfaces unresolved conflicts."),
    "allocation": (
        "Allocation",
        "Review-only sizing perspective; never an executable allocation.",
    ),
    "option": (
        "Option",
        "Review-only option-expression perspective; no_trade is first-class.",
    ),
    "synthesis": ("Synthesis", "Consensus synthesizer; expressed via consensus summary."),
}


def build_default_participants() -> list[AgentDebateParticipant]:
    """Return the deterministic set of seven debate participant role records."""
    out: list[AgentDebateParticipant] = []
    for role in AGENT_ROLES:
        name, desc = _PARTICIPANT_META[role]
        out.append(
            AgentDebateParticipant(
                agent_role=role,
                participant_id=f"participant_{role}",
                display_name=name,
                description=desc,
                note="Deterministic role record; not a live agent.",
            )
        )
    return out


def build_agent_debate_participant(role: AgentRole) -> AgentDebateParticipant:
    """Build a single deterministic participant role record."""
    name, desc = _PARTICIPANT_META[role]
    return AgentDebateParticipant(
        agent_role=role,
        participant_id=f"participant_{role}",
        display_name=name,
        description=desc,
        note="Deterministic role record; not a live agent.",
    )


# ---------------------------------------------------------------------------
# Evidence helpers (from a research-pack request)
# ---------------------------------------------------------------------------


def _gap_types(request: ResearchPackRequest) -> set[str]:
    return {str(g.gap_type) for g in request.evidence_gaps}


def _max_gap_severity(request: ResearchPackRequest) -> int:
    return max(
        (_SEVERITY_RANK.get(str(g.severity), 0) for g in request.evidence_gaps),
        default=0,
    )


def _request_modules(request: ResearchPackRequest) -> set[str]:
    mods: set[str] = set()
    for m in list(request.required_modules) + list(request.optional_modules):
        mods.add(str(m.module))
    return mods


def _role_evidence_refs(request: ResearchPackRequest, role: AgentRole) -> list[str]:
    """Planned-module references the role leans on (no live evidence exists yet)."""
    present = _request_modules(request)
    refs = [
        f"planned_module::{m}" for m in _ROLE_MODULES.get(role, ()) if m in present
    ]
    return refs


def _missing_reasons(request: ResearchPackRequest, *, is_degraded: bool) -> list[str]:
    reasons = [g.description or f"{g.gap_type} gap" for g in request.evidence_gaps]
    if is_degraded:
        reasons.append(
            "Upstream research modules are blocked placeholders; no analysis "
            "available yet."
        )
    return reasons


# ---------------------------------------------------------------------------
# Per-role stance-label derivation (deterministic)
# ---------------------------------------------------------------------------


def _evidence_insufficient(
    decision: str, gap_types: set[str], max_sev: int, *, is_degraded: bool
) -> bool:
    if is_degraded:
        return True
    if decision in _RESEARCH_DECISIONS:
        return True
    if "incomplete_evidence" in gap_types and max_sev >= _SEVERITY_RANK["high"]:
        return True
    return False


def _bull_label(
    decision: str, gap_types: set[str], *, evidence_insufficient: bool, is_review_only: bool
) -> BullStanceLabel:
    if is_review_only or decision in _NO_TRADE_DECISIONS:
        return "insufficient_evidence"
    if evidence_insufficient:
        return "insufficient_evidence"
    if decision in _READY_DECISIONS:
        if "incomplete_evidence" in gap_types or "missing_fundamental_confirmation" in gap_types:
            return "bullish_with_conditions"
        return "constructive"
    if decision in _WAIT_DECISIONS:
        return "wait_for_better_entry"
    if decision in _CONDITIONAL_DECISIONS:
        return "bullish_with_conditions"
    return "insufficient_evidence"


def _bear_label(
    decision: str, gap_types: set[str], max_sev: int, *, evidence_insufficient: bool
) -> BearStanceLabel:
    if evidence_insufficient:
        return "insufficient_evidence"
    if decision == "too_extended":
        return "overextended"
    if "crowding_risk" in gap_types or decision == "avoid_too_crowded":
        return "crowded_trade"
    if "valuation_stretch" in gap_types or decision in (
        "quality_but_expensive",
        "watch_for_valuation",
    ):
        return "valuation_risk"
    if decision in ("no_trade", "thesis_unconfirmed", "thesis_insufficient"):
        return "thesis_weak"
    # Clean constructive / conditional with no flagged gaps: no bear case.
    return "insufficient_evidence"


def _risk_label(
    decision: str, gap_types: set[str], max_sev: int, *, is_degraded: bool
) -> RiskStanceLabel:
    if is_degraded:
        return "unknown"
    if decision == "avoid_too_crowded":
        return "unacceptable"
    if decision == "no_trade":
        return "high"
    if "crowding_risk" in gap_types and max_sev >= _SEVERITY_RANK["high"]:
        return "high"
    if decision == "too_extended" or "crowding_risk" in gap_types:
        return "elevated"
    if "valuation_stretch" in gap_types:
        return "elevated"
    if decision in _RESEARCH_DECISIONS:
        return "unknown"
    if decision in _READY_DECISIONS and not gap_types:
        return "acceptable"
    return "elevated"


def _bull_is_positive(label: str) -> bool:
    return label in ("constructive", "bullish_with_conditions")


def _bear_is_opposing(label: str) -> bool:
    return label in ("overextended", "valuation_risk", "thesis_weak", "crowded_trade")


def _critic_label(
    decision: str,
    *,
    evidence_insufficient: bool,
    is_review_only: bool,
    has_unresolved_conflict: bool,
) -> CriticStanceLabel:
    if evidence_insufficient:
        return "needs_more_evidence"
    if is_review_only or decision in _NO_TRADE_DECISIONS:
        return "reject_for_now"
    if has_unresolved_conflict:
        return "conflict_unresolved"
    return "pass_with_warnings"


def _allocation_label(
    decision: str,
    bull_label: str,
    risk_label: str,
    *,
    evidence_insufficient: bool,
    is_review_only: bool,
) -> AllocationStanceLabel:
    if is_review_only or decision in _NO_TRADE_DECISIONS:
        return "avoid"
    if evidence_insufficient:
        return "no_allocation"
    if risk_label in ("high", "unacceptable"):
        return "watchlist_only"
    if decision in _READY_DECISIONS and bull_label == "constructive" and risk_label == "acceptable":
        return "position_candidate"
    if decision in _READY_DECISIONS or bull_label in ("constructive", "bullish_with_conditions"):
        return "small_starter"
    if decision in _WAIT_DECISIONS or decision in _WATCHLIST_DECISIONS:
        return "watchlist_only"
    return "no_allocation"


def _option_label(
    decision: str,
    horizon: OpportunityHorizon,
    risk_label: str,
    *,
    evidence_insufficient: bool,
    is_review_only: bool,
    is_degraded: bool,
) -> OptionStanceLabel:
    if is_review_only or decision in _NO_TRADE_DECISIONS:
        return "no_trade"
    if is_degraded:
        return "no_trade"
    if decision == "event_trade_watch":
        return "event_risk_too_high"
    if evidence_insufficient or decision in _RESEARCH_DECISIONS:
        return "no_trade"
    if (
        horizon == "short_term"
        and decision in _READY_DECISIONS
        and risk_label == "acceptable"
    ):
        return "option_candidate"
    if decision in _WAIT_DECISIONS:
        return "no_trade"
    return "stock_preferred"


# Role alignment for consensus accounting.
def _role_alignment(role: AgentRole, label: str) -> str:
    if role == "bull":
        return "support" if _bull_is_positive(label) else "neutral"
    if role == "bear":
        return "oppose" if _bear_is_opposing(label) else "neutral"
    if role == "risk":
        if label == "acceptable":
            return "support"
        if label in ("high", "unacceptable"):
            return "oppose"
        return "neutral"
    if role == "critic":
        if label == "pass_with_warnings":
            return "support"
        if label == "reject_for_now":
            return "oppose"
        return "neutral"
    if role == "allocation":
        if label in ("position_candidate", "small_starter"):
            return "support"
        if label == "avoid":
            return "oppose"
        return "neutral"
    if role == "option":
        if label in ("option_candidate", "stock_preferred"):
            return "support"
        if label == "no_trade":
            return "oppose"
        return "neutral"
    return "neutral"


# ---------------------------------------------------------------------------
# Stance record building
# ---------------------------------------------------------------------------

_STANCE_CLAIMS: dict[AgentRole, dict[str, str]] = {
    "bull": {
        "constructive": "Constructive case: the opportunity is attractive on the available signals.",
        "bullish_with_conditions": "Bullish but conditional on closing the open evidence gaps.",
        "wait_for_better_entry": "Thesis may hold, but wait for a better entry.",
        "insufficient_evidence": "Not enough evidence to mount a constructive case yet.",
    },
    "bear": {
        "overextended": "The move looks overextended; risk of mean reversion.",
        "valuation_risk": "Valuation is stretched; downside if multiples compress.",
        "thesis_weak": "The thesis is weak / unconfirmed by fundamentals.",
        "crowded_trade": "The trade is crowded; chasing into the crowd is risky.",
        "insufficient_evidence": "No strong bear case on the available evidence.",
    },
    "risk": {
        "acceptable": "Risk appears acceptable for review under position sizing.",
        "elevated": "Risk is elevated; size down and confirm entry.",
        "high": "Risk is high; a constructive read should be downgraded.",
        "unacceptable": "Risk is unacceptable here; avoid chasing.",
        "unknown": "Risk cannot be assessed without more evidence.",
    },
    "critic": {
        "pass_with_warnings": "Evidence is adequate to proceed to human review, with warnings.",
        "needs_more_evidence": "Evidence is insufficient; more research is required.",
        "conflict_unresolved": "Bull / bear / risk conflict is unresolved; do not force a decision.",
        "reject_for_now": "Reject for now; this is a review-only no-trade case.",
        "no_decision": "No decision can be made on the current state.",
    },
    "allocation": {
        "no_allocation": "No allocation; insufficient basis to size a position.",
        "watchlist_only": "Watchlist only; no sizing until risk / entry improves.",
        "small_starter": "A small starter could be considered after human review.",
        "position_candidate": "Position candidate for review (non-executable).",
        "avoid": "Avoid; no allocation for a no-trade / avoid case.",
    },
    "option": {
        "no_trade": "No option trade; preserved as a first-class state.",
        "stock_preferred": "Prefer the underlying over an option expression.",
        "option_candidate": "Option expression candidate for review (non-executable).",
        "insufficient_liquidity": "Insufficient option liquidity to consider an expression.",
        "event_risk_too_high": "Event risk is too high for an option expression now.",
    },
}


def _stance_warnings(
    role: AgentRole, label: str, *, is_degraded: bool, gap_types: set[str]
) -> list[DebateWarning]:
    warnings: list[DebateWarning] = []
    if is_degraded:
        warnings.append(
            DebateWarning(
                warning_type="degraded_upstream",
                severity="medium",
                message="Upstream research modules are blocked; stance is provisional.",
            )
        )
    if label == "insufficient_evidence" or (
        role == "critic" and label == "needs_more_evidence"
    ):
        warnings.append(
            DebateWarning(
                warning_type="missing_evidence",
                severity="low" if not is_degraded else "medium",
                message="Evidence is incomplete; do not treat this stance as actionable.",
            )
        )
    if role == "option" and label == "no_trade":
        warnings.append(
            DebateWarning(
                warning_type="no_trade_review_only",
                severity="info",
                message="Option no_trade is a valid review-only state, not a recommendation.",
            )
        )
    return warnings


def _build_stance_record(
    *,
    session_id: str,
    role: AgentRole,
    request: ResearchPackRequest,
    label: str,
    confidence: DebateConfidence,
    is_degraded: bool,
    gap_types: set[str],
) -> AgentStanceRecord:
    claim = _STANCE_CLAIMS.get(role, {}).get(label, f"{role} stance: {label}.")
    invalidation = [
        f"Stance '{label}' invalidated if upstream evidence contradicts the {role} case."
    ]
    review_triggers = [
        "Re-run debate after the planned research modules complete.",
    ]
    risks = [g.description or f"{g.gap_type} risk" for g in request.evidence_gaps]
    return AgentStanceRecord(
        stance_id=make_agent_stance_id(session_id, role),
        agent_role=role,
        ticker=request.ticker,
        theme_id=request.theme_id,
        theme_name=request.theme_name,
        horizon=request.horizon,
        stance_label=label,  # validated against AgentStanceLabel union
        confidence=confidence,
        key_claims=[claim],
        supporting_evidence_refs=_role_evidence_refs(request, role),
        missing_evidence_refs=[],
        missing_evidence_reasons=_missing_reasons(request, is_degraded=is_degraded),
        risks=risks,
        invalidation_conditions=invalidation,
        review_triggers=review_triggers,
        source_research_pack_ids=[request.pack_request_id],
        warnings=_stance_warnings(
            role, label, is_degraded=is_degraded, gap_types=gap_types
        ),
        rationale=(
            f"Deterministic {role} stance derived from the Phase 5L research pack "
            f"(decision={request.decision_label}, horizon={request.horizon}). "
            "Not a live agent call; not a final decision."
        ),
    )


# ---------------------------------------------------------------------------
# Perspective view builders
# ---------------------------------------------------------------------------


def _confidence_for(label: str, *, is_degraded: bool) -> DebateConfidence:
    if is_degraded:
        return "low"
    if label in ("constructive", "overextended", "crowded_trade", "high", "unacceptable",
                 "position_candidate", "reject_for_now", "thesis_weak"):
        return "high"
    if label in ("insufficient_evidence", "unknown", "needs_more_evidence", "no_decision"):
        return "low"
    return "medium"


def build_bull_case_view(stance: AgentStanceRecord) -> BullCaseView:
    """Build the bull perspective view from the bull stance record."""
    return BullCaseView(
        ticker=stance.ticker,
        theme_id=stance.theme_id,
        horizon=stance.horizon,
        stance_label=stance.stance_label,  # BullStanceLabel subset
        confidence=stance.confidence,
        key_claims=list(stance.key_claims),
        supporting_evidence_refs=list(stance.supporting_evidence_refs),
        missing_evidence_refs=list(stance.missing_evidence_refs),
        missing_evidence_reasons=list(stance.missing_evidence_reasons),
        risks=list(stance.risks),
        invalidation_conditions=list(stance.invalidation_conditions),
        warnings=list(stance.warnings),
        is_populated=stance.stance_label != "insufficient_evidence",
        note="Bull perspective; not a buy recommendation.",
    )


def build_bear_case_view(stance: AgentStanceRecord) -> BearCaseView:
    """Build the bear perspective view from the bear stance record."""
    return BearCaseView(
        ticker=stance.ticker,
        theme_id=stance.theme_id,
        horizon=stance.horizon,
        stance_label=stance.stance_label,
        confidence=stance.confidence,
        key_claims=list(stance.key_claims),
        supporting_evidence_refs=list(stance.supporting_evidence_refs),
        missing_evidence_refs=list(stance.missing_evidence_refs),
        missing_evidence_reasons=list(stance.missing_evidence_reasons),
        risks=list(stance.risks),
        invalidation_conditions=list(stance.invalidation_conditions),
        warnings=list(stance.warnings),
        is_populated=stance.stance_label != "insufficient_evidence",
        note="Bear perspective; not a sell recommendation.",
    )


def build_risk_case_view(stance: AgentStanceRecord) -> RiskCaseView:
    """Build the risk perspective view from the risk stance record."""
    return RiskCaseView(
        ticker=stance.ticker,
        theme_id=stance.theme_id,
        horizon=stance.horizon,
        stance_label=stance.stance_label,
        confidence=stance.confidence,
        key_claims=list(stance.key_claims),
        supporting_evidence_refs=list(stance.supporting_evidence_refs),
        missing_evidence_refs=list(stance.missing_evidence_refs),
        missing_evidence_reasons=list(stance.missing_evidence_reasons),
        risks=list(stance.risks),
        invalidation_conditions=list(stance.invalidation_conditions),
        warnings=list(stance.warnings),
        can_downgrade_decision=stance.stance_label in ("high", "unacceptable"),
        is_populated=stance.stance_label != "unknown",
        note="Risk perspective; can downgrade workspace state but never authorizes execution.",
    )


def build_critic_review_view(
    stance: AgentStanceRecord,
    conflicts: list[DebateConflictRecord],
) -> CriticReviewView:
    """Build the critic perspective view.

    The critic acknowledges every unresolved conflict — it does not hide them.
    """
    unresolved = [c for c in conflicts if not c.is_resolved]
    warnings = list(stance.warnings)
    for c in unresolved:
        warnings.append(
            DebateWarning(
                warning_type="conflict_unresolved",
                severity=c.severity,
                message=f"Unresolved conflict acknowledged: {c.description}",
            )
        )
    return CriticReviewView(
        ticker=stance.ticker,
        theme_id=stance.theme_id,
        horizon=stance.horizon,
        stance_label=stance.stance_label,
        confidence=stance.confidence,
        key_claims=list(stance.key_claims),
        supporting_evidence_refs=list(stance.supporting_evidence_refs),
        missing_evidence_reasons=list(stance.missing_evidence_reasons),
        acknowledged_conflict_ids=[c.conflict_id for c in unresolved],
        unresolved_conflict_count=len(unresolved),
        warnings=warnings,
        is_populated=True,
        note="Critic perspective; unresolved conflicts are surfaced, never hidden.",
    )


def build_allocation_perspective_view(
    stance: AgentStanceRecord,
) -> AllocationPerspectiveView:
    """Build the review-only allocation perspective (never executable)."""
    return AllocationPerspectiveView(
        ticker=stance.ticker,
        theme_id=stance.theme_id,
        horizon=stance.horizon,
        stance_label=stance.stance_label,
        confidence=stance.confidence,
        key_claims=list(stance.key_claims),
        supporting_evidence_refs=list(stance.supporting_evidence_refs),
        missing_evidence_reasons=list(stance.missing_evidence_reasons),
        risks=list(stance.risks),
        warnings=list(stance.warnings),
        is_populated=stance.stance_label not in ("no_allocation", "avoid"),
        note="Allocation perspective is review-only; no executable allocation is created.",
    )


def build_option_perspective_view(stance: AgentStanceRecord) -> OptionPerspectiveView:
    """Build the review-only option perspective (no_trade first-class)."""
    return OptionPerspectiveView(
        ticker=stance.ticker,
        theme_id=stance.theme_id,
        horizon=stance.horizon,
        stance_label=stance.stance_label,
        confidence=stance.confidence,
        key_claims=list(stance.key_claims),
        supporting_evidence_refs=list(stance.supporting_evidence_refs),
        missing_evidence_reasons=list(stance.missing_evidence_reasons),
        risks=list(stance.risks),
        is_no_trade=stance.stance_label == "no_trade",
        warnings=list(stance.warnings),
        is_populated=stance.stance_label != "no_trade",
        note="Option perspective is review-only; no_trade is a valid first-class state.",
    )


# ---------------------------------------------------------------------------
# Conflict / consensus / evidence builders
# ---------------------------------------------------------------------------


def build_debate_conflicts(
    *,
    session_id: str,
    bull_label: str,
    bear_label: str,
    risk_label: str,
    allocation_label: str,
    option_label: str,
) -> list[DebateConflictRecord]:
    """Derive explicit conflict records from the per-role stance labels.

    Conflicts are never hidden. A bull/bear disagreement and a risk override are
    surfaced as unresolved conflicts when present.
    """
    conflicts: list[DebateConflictRecord] = []

    if _bull_is_positive(bull_label) and _bear_is_opposing(bear_label):
        if bear_label in ("crowded_trade", "overextended"):
            ctype: DebateConflictType = "crowding_dispute"
        elif bear_label == "valuation_risk":
            ctype = "valuation_dispute"
        else:
            ctype = "evidence_dispute"
        conflicts.append(
            DebateConflictRecord(
                conflict_id=f"conflict_{_short_hash(session_id + '::bull_bear')}",
                conflict_type="bull_bear_disagreement",
                severity="medium",
                roles_in_conflict=["bull", "bear"],
                stance_labels=[bull_label, bear_label],
                description=(
                    f"Bull is {bull_label} while Bear is {bear_label} "
                    f"({ctype}); disagreement is explicit and unresolved."
                ),
                is_resolved=False,
                resolution_note=(
                    "Unresolved: requires completed research / human review."
                ),
            )
        )

    if _bull_is_positive(bull_label) and risk_label in ("high", "unacceptable"):
        conflicts.append(
            DebateConflictRecord(
                conflict_id=f"conflict_{_short_hash(session_id + '::risk_override')}",
                conflict_type="risk_override",
                severity="high",
                roles_in_conflict=["risk", "bull"],
                stance_labels=[risk_label, bull_label],
                description=(
                    f"Risk is {risk_label} while Bull is {bull_label}; "
                    "risk overrides the constructive case."
                ),
                is_resolved=False,
                resolution_note="Unresolved: risk must be resolved before any review-ready state.",
            )
        )

    if allocation_label in ("position_candidate", "small_starter") and option_label == "no_trade":
        conflicts.append(
            DebateConflictRecord(
                conflict_id=f"conflict_{_short_hash(session_id + '::option')}",
                conflict_type="option_disagreement",
                severity="low",
                roles_in_conflict=["allocation", "option"],
                stance_labels=[allocation_label, option_label],
                description=(
                    f"Allocation suggests {allocation_label} while Option is no_trade; "
                    "expression-vehicle disagreement (review-only)."
                ),
                is_resolved=False,
                resolution_note="Minor: stock vs option expression to be decided by human review.",
            )
        )

    return conflicts


def build_debate_consensus_summary(
    *,
    stance_labels: dict[AgentRole, str],
    conflicts: list[DebateConflictRecord],
    critic_label: str,
    evidence_insufficient: bool,
    is_empty: bool = False,
) -> DebateConsensusSummary:
    """Derive the consensus level deterministically from stance labels."""
    agreeing: list[AgentRole] = []
    dissenting: list[AgentRole] = []
    neutral: list[AgentRole] = []
    for role in DEBATE_STANCE_ROLES:
        label = stance_labels.get(role, "unknown")
        align = _role_alignment(role, label)
        if align == "support":
            agreeing.append(role)
        elif align == "oppose":
            dissenting.append(role)
        else:
            neutral.append(role)

    unresolved = [c for c in conflicts if not c.is_resolved]

    if is_empty:
        level: DebateConsensusLevel = "insufficient_evidence"
    elif evidence_insufficient or critic_label in ("needs_more_evidence", "no_decision"):
        level = "insufficient_evidence"
    elif critic_label == "conflict_unresolved" or (
        unresolved
        and any(c.conflict_type in ("risk_override", "bull_bear_disagreement") for c in unresolved)
        and any(c.severity in ("medium", "high") for c in unresolved)
    ):
        level = "conflict_unresolved"
    elif conflicts:
        level = "mixed"
    elif (
        stance_labels.get("bull") == "constructive"
        and stance_labels.get("bear") == "insufficient_evidence"
        and stance_labels.get("risk") == "acceptable"
        and critic_label == "pass_with_warnings"
    ):
        level = "strong_consensus"
    else:
        level = "moderate_consensus"

    note = {
        "strong_consensus": "Roles broadly align; ready for human review.",
        "moderate_consensus": "Roles mostly align with some caveats.",
        "mixed": "Roles disagree; conflicts are explicit.",
        "conflict_unresolved": "An unresolved conflict blocks a review-ready state.",
        "insufficient_evidence": "Insufficient evidence for consensus.",
    }[level]

    return DebateConsensusSummary(
        consensus_level=level,
        agreeing_roles=agreeing,
        dissenting_roles=dissenting,
        neutral_roles=neutral,
        total_conflicts=len(conflicts),
        unresolved_conflict_count=len(unresolved),
        note=note,
    )


def build_debate_evidence_coverage(
    request: ResearchPackRequest,
    stances: list[AgentStanceRecord],
    *,
    is_degraded: bool,
) -> DebateEvidenceCoverage:
    """Build evidence-coverage accounting for the debate."""
    supporting = sum(len(s.supporting_evidence_refs) for s in stances)
    missing = sum(len(s.missing_evidence_reasons) for s in stances)
    gap_count = len(request.evidence_gaps)
    if is_degraded:
        coverage: Literal["complete", "partial", "none", "unknown"] = "none"
    elif gap_count == 0 and supporting > 0:
        coverage = "complete"
    elif supporting > 0:
        coverage = "partial"
    else:
        coverage = "unknown"
    return DebateEvidenceCoverage(
        coverage=coverage,
        total_supporting_evidence_refs=supporting,
        total_missing_evidence_reasons=missing,
        evidence_gap_count=gap_count,
        has_unresolved_evidence_gap=gap_count > 0 or is_degraded,
        note=(
            "Evidence is planned (research pack not executed); coverage is "
            "provisional and evidence-first."
        ),
    )


# ---------------------------------------------------------------------------
# Workspace status / next action / recommendation
# ---------------------------------------------------------------------------


def _derive_workspace_status(
    *,
    decision: str,
    risk_label: str,
    critic_label: str,
    evidence_insufficient: bool,
    is_review_only: bool,
    is_degraded: bool,
    is_failed: bool,
    is_empty: bool,
) -> DecisionWorkspaceStatus:
    if is_empty:
        return "no_decision"
    if is_failed:
        return "invalidated"
    if is_degraded:
        return "blocked"
    if is_review_only or decision in _NO_TRADE_DECISIONS:
        return "no_trade"
    if (
        critic_label in ("needs_more_evidence", "conflict_unresolved")
        or evidence_insufficient
        or decision in _RESEARCH_DECISIONS
    ):
        return "research_more"
    if risk_label in ("high", "unacceptable"):
        if decision in _READY_DECISIONS or decision in _WAIT_DECISIONS or decision in _WATCHLIST_DECISIONS:
            return "wait_for_pullback"
        return "research_more"
    if decision in _WAIT_DECISIONS:
        return "wait_for_pullback"
    if decision in _WATCHLIST_DECISIONS:
        return "watchlist"
    if decision in _READY_DECISIONS:
        return "ready_for_review"
    return "unknown"


_NEXT_ACTION_MAP: dict[DecisionWorkspaceStatus, tuple[DecisionWorkspaceNextActionType, str]] = {
    "ready_for_review": ("review", "Ready for human review; not an executable order."),
    "research_more": ("research_more", "Close evidence gaps before any decision."),
    "wait_for_pullback": ("wait_for_pullback", "Wait for a better entry; do not chase."),
    "watchlist": ("watch", "Add to watchlist; monitor for a trigger."),
    "no_trade": ("no_trade", "No trade; review-only no-trade state."),
    "blocked": ("research_more", "Upstream blocked; re-run research before review."),
    "invalidated": ("skip", "Thesis invalidated; skip for now."),
    "no_decision": ("skip", "No decision possible; skip / revisit later."),
    "unknown": ("review", "State unknown; route to human review."),
}


def _build_next_action(
    status: DecisionWorkspaceStatus, *, has_unresolved_conflict: bool
) -> DecisionWorkspaceNextAction:
    if status == "research_more" and has_unresolved_conflict:
        return DecisionWorkspaceNextAction(
            action="escalate_to_human",
            description=(
                "Unresolved agent conflict; escalate to human review rather than "
                "forcing a decision."
            ),
        )
    action, desc = _NEXT_ACTION_MAP.get(status, ("review", "Route to human review."))
    return DecisionWorkspaceNextAction(action=action, description=desc)


# ---------------------------------------------------------------------------
# Session builder
# ---------------------------------------------------------------------------


def build_debate_session_from_research_pack(
    bundle: ResearchPackBundle,
) -> AgentDebateSession:
    """Build a deterministic debate session from a Phase 5L research-pack bundle.

    Generates fixture stances for bull / bear / risk / critic / allocation /
    option, surfaces explicit conflicts, and summarizes consensus. Runs no live
    agent and produces no executable decision.
    """
    request = bundle.request
    decision = str(request.decision_label)
    horizon = request.horizon
    gap_types = _gap_types(request)
    max_sev = _max_gap_severity(request)
    is_review_only = bool(request.is_review_only)
    is_degraded = bundle.status == "blocked"
    is_failed = bundle.status == "failed"
    evidence_insufficient = _evidence_insufficient(
        decision, gap_types, max_sev, is_degraded=is_degraded
    )

    session_id = make_debate_session_id(
        request.ticker, request.theme_id, horizon, decision
    )

    # Derive per-role stance labels.
    bull_label = _bull_label(
        decision, gap_types, evidence_insufficient=evidence_insufficient,
        is_review_only=is_review_only,
    )
    bear_label = _bear_label(
        decision, gap_types, max_sev, evidence_insufficient=evidence_insufficient
    )
    risk_label = _risk_label(decision, gap_types, max_sev, is_degraded=is_degraded)
    allocation_label = _allocation_label(
        decision, bull_label, risk_label,
        evidence_insufficient=evidence_insufficient, is_review_only=is_review_only,
    )
    option_label = _option_label(
        decision, horizon, risk_label,
        evidence_insufficient=evidence_insufficient, is_review_only=is_review_only,
        is_degraded=is_degraded,
    )

    # Conflicts depend on bull/bear/risk; critic must acknowledge them.
    conflicts = build_debate_conflicts(
        session_id=session_id,
        bull_label=bull_label,
        bear_label=bear_label,
        risk_label=risk_label,
        allocation_label=allocation_label,
        option_label=option_label,
    )
    has_unresolved_conflict = any(not c.is_resolved for c in conflicts)
    critic_label = _critic_label(
        decision,
        evidence_insufficient=evidence_insufficient,
        is_review_only=is_review_only,
        has_unresolved_conflict=has_unresolved_conflict,
    )

    labels: dict[AgentRole, str] = {
        "bull": bull_label,
        "bear": bear_label,
        "risk": risk_label,
        "critic": critic_label,
        "allocation": allocation_label,
        "option": option_label,
    }

    stances: list[AgentStanceRecord] = []
    for role in DEBATE_STANCE_ROLES:
        label = labels[role]
        conf = _confidence_for(label, is_degraded=is_degraded)
        stances.append(
            _build_stance_record(
                session_id=session_id,
                role=role,
                request=request,
                label=label,
                confidence=conf,
                is_degraded=is_degraded,
                gap_types=gap_types,
            )
        )

    stance_by_role = {s.agent_role: s for s in stances}
    bull_case = build_bull_case_view(stance_by_role["bull"])
    bear_case = build_bear_case_view(stance_by_role["bear"])
    risk_case = build_risk_case_view(stance_by_role["risk"])
    critic_review = build_critic_review_view(stance_by_role["critic"], conflicts)
    allocation_view = build_allocation_perspective_view(stance_by_role["allocation"])
    option_view = build_option_perspective_view(stance_by_role["option"])

    consensus = build_debate_consensus_summary(
        stance_labels=labels,
        conflicts=conflicts,
        critic_label=critic_label,
        evidence_insufficient=evidence_insufficient,
    )
    coverage = build_debate_evidence_coverage(request, stances, is_degraded=is_degraded)

    warnings: list[DebateWarning] = []
    if is_degraded:
        warnings.append(
            DebateWarning(
                warning_type="degraded_upstream",
                severity="medium",
                message="Degraded research pack; debate stances are provisional.",
            )
        )
    if evidence_insufficient:
        warnings.append(
            DebateWarning(
                warning_type="missing_evidence",
                severity="medium",
                message="Insufficient evidence; debate cannot reach a review-ready state.",
            )
        )
    if has_unresolved_conflict:
        warnings.append(
            DebateWarning(
                warning_type="conflict_unresolved",
                severity="high",
                message="Unresolved agent conflict; no executable recommendation is produced.",
            )
        )
    if is_review_only or decision in _NO_TRADE_DECISIONS:
        warnings.append(
            DebateWarning(
                warning_type="no_trade_review_only",
                severity="info",
                message="Review-only no-trade case; no trade path is generated.",
            )
        )
    warnings.append(
        DebateWarning(
            warning_type="review_required",
            severity="info",
            message="Decision workspace is review-only and requires human review.",
        )
    )

    round_one = AgentDebateRound(
        round_index=1,
        round_label="initial_debate",
        stances=stances,
        note="Single deterministic debate round (contract fixture).",
    )

    return AgentDebateSession(
        session_id=session_id,
        ticker=request.ticker,
        company_name=request.company_name,
        theme_id=request.theme_id,
        theme_name=request.theme_name,
        horizon=horizon,
        decision_label=decision,
        source_pack_request_id=request.pack_request_id,
        source_bundle_id=bundle.bundle_id,
        source_research_pack_ids=[request.pack_request_id],
        participants=build_default_participants(),
        rounds=[round_one],
        stances=stances,
        bull_case=bull_case,
        bear_case=bear_case,
        risk_case=risk_case,
        critic_review=critic_review,
        allocation_perspective=allocation_view,
        option_perspective=option_view,
        conflicts=conflicts,
        consensus_summary=consensus,
        evidence_coverage=coverage,
        is_review_only=is_review_only,
        is_degraded=is_degraded,
        warnings=warnings,
        notes=(
            "Deterministic agent debate session (Phase 5M contract). Roles are "
            "records, not live agents; output is review-only and not a final "
            "decision."
        ),
    )


# ---------------------------------------------------------------------------
# Decision workspace builders
# ---------------------------------------------------------------------------


def build_decision_workspace_recommendation_state(
    session: AgentDebateSession,
    status: DecisionWorkspaceStatus,
) -> DecisionWorkspaceRecommendationState:
    """Build the review-only recommendation state (never executable)."""
    consensus = session.consensus_summary
    level = consensus.consensus_level if consensus else "insufficient_evidence"
    supporting = list(consensus.agreeing_roles) if consensus else []
    dissenting = list(consensus.dissenting_roles) if consensus else []
    rationale = (
        f"Status '{status}' derived from debate consensus '{level}', "
        f"critic '{session.critic_review.stance_label if session.critic_review else 'unknown'}', "
        f"and risk '{session.risk_case.stance_label if session.risk_case else 'unknown'}'. "
        "Review-only; requires human review; not executable."
    )
    return DecisionWorkspaceRecommendationState(
        status=status,
        consensus_level=level,
        supporting_roles=supporting,
        dissenting_roles=dissenting,
        rationale=rationale,
        note="Recommendation state is review-only and non-executable.",
    )


def build_decision_workspace_view(session: AgentDebateSession) -> DecisionWorkspaceView:
    """Build the decision-workspace view summarizing one debate session."""
    is_empty = not session.stances
    risk_label = session.risk_case.stance_label if session.risk_case else "unknown"
    critic_label = (
        session.critic_review.stance_label if session.critic_review else "no_decision"
    )
    evidence_insufficient = critic_label in ("needs_more_evidence", "no_decision")
    has_unresolved_conflict = any(not c.is_resolved for c in session.conflicts)

    status = _derive_workspace_status(
        decision=session.decision_label,
        risk_label=risk_label,
        critic_label=critic_label,
        evidence_insufficient=evidence_insufficient,
        is_review_only=session.is_review_only,
        is_degraded=session.is_degraded,
        is_failed=False,
        is_empty=is_empty,
    )

    next_action = _build_next_action(
        status, has_unresolved_conflict=has_unresolved_conflict
    )
    recommendation = build_decision_workspace_recommendation_state(session, status)

    warnings: list[DebateWarning] = [
        DebateWarning(
            warning_type="review_required",
            severity="info",
            message=(
                "Decision workspace summarizes debate state only; it is "
                "review-only and requires human review. Not investment advice."
            ),
        )
    ]
    if has_unresolved_conflict:
        warnings.append(
            DebateWarning(
                warning_type="conflict_unresolved",
                severity="high",
                message="Unresolved conflict present; no executable recommendation.",
            )
        )

    return DecisionWorkspaceView(
        workspace_view_id=make_decision_workspace_view_id(session.session_id),
        ticker=session.ticker,
        theme_id=session.theme_id,
        theme_name=session.theme_name,
        horizon=session.horizon,
        decision_label=session.decision_label,
        status=status,
        recommendation_state=recommendation,
        next_action=next_action,
        consensus_summary=session.consensus_summary,
        conflicts=list(session.conflicts),
        evidence_coverage=session.evidence_coverage,
        bull_case=session.bull_case,
        bear_case=session.bear_case,
        risk_case=session.risk_case,
        critic_review=session.critic_review,
        allocation_perspective=session.allocation_perspective,
        option_perspective=session.option_perspective,
        source_session_id=session.session_id,
        source_research_pack_ids=list(session.source_research_pack_ids),
        warnings=warnings,
        notes="Decision workspace view (Phase 5M). Review-only; non-executable.",
    )


# ---------------------------------------------------------------------------
# Validation summary
# ---------------------------------------------------------------------------


def build_decision_workspace_validation_summary(
    *,
    sessions: list[AgentDebateSession],
    views: list[DecisionWorkspaceView],
    is_empty: bool = False,
) -> DecisionWorkspaceValidationSummary:
    """Build the aggregate validation summary across sessions + views."""
    all_stances = [s for sess in sessions for s in sess.stances]
    role_counts = {role: 0 for role in DEBATE_STANCE_ROLES}
    for st in all_stances:
        if st.agent_role in role_counts:
            role_counts[st.agent_role] += 1

    all_conflicts = [c for sess in sessions for c in sess.conflicts]
    unresolved = sum(1 for c in all_conflicts if not c.is_resolved)

    def _status_count(status: str) -> int:
        return sum(1 for v in views if v.status == status)

    strong_consensus = sum(
        1
        for sess in sessions
        if sess.consensus_summary is not None
        and sess.consensus_summary.consensus_level == "strong_consensus"
    )
    conflict_unresolved = sum(
        1
        for sess in sessions
        if sess.consensus_summary is not None
        and sess.consensus_summary.consensus_level == "conflict_unresolved"
    )

    distinct_tickers = len({s.ticker for s in sessions})
    distinct_workspaces = len({(s.theme_id, s.ticker, s.horizon) for s in sessions})

    issues: list[str] = []
    # Safety: a critic that hides a conflict would be a defect.
    for sess in sessions:
        cr = sess.critic_review
        unresolved_in_sess = sum(1 for c in sess.conflicts if not c.is_resolved)
        if cr is not None and cr.unresolved_conflict_count != unresolved_in_sess:
            issues.append(
                f"session {sess.session_id!r} critic under-reports unresolved conflicts"
            )

    return DecisionWorkspaceValidationSummary(
        total_sessions=len(sessions),
        total_workspace_views=len(views),
        total_stances=len(all_stances),
        total_participants=sum(len(s.participants) for s in sessions),
        bull_stance_count=role_counts["bull"],
        bear_stance_count=role_counts["bear"],
        risk_stance_count=role_counts["risk"],
        critic_stance_count=role_counts["critic"],
        allocation_stance_count=role_counts["allocation"],
        option_stance_count=role_counts["option"],
        total_conflicts=len(all_conflicts),
        unresolved_conflict_count=unresolved,
        ready_for_review_count=_status_count("ready_for_review"),
        research_more_count=_status_count("research_more"),
        wait_for_pullback_count=_status_count("wait_for_pullback"),
        watchlist_count=_status_count("watchlist"),
        no_trade_count=_status_count("no_trade"),
        no_decision_count=_status_count("no_decision"),
        blocked_count=_status_count("blocked"),
        strong_consensus_count=strong_consensus,
        conflict_unresolved_count=conflict_unresolved,
        distinct_tickers=distinct_tickers,
        distinct_theme_candidate_workspaces=distinct_workspaces,
        is_safe_empty=is_empty or not sessions,
        critic_hides_no_conflict=not issues,
        issues=issues,
    )


# ---------------------------------------------------------------------------
# Top-level workspace builder
# ---------------------------------------------------------------------------


def build_agent_debate_workspace(
    boundary: AutoResearchPackOrchestrationBoundary,
    *,
    label: str = "default",
) -> AgentDebateWorkspace:
    """Build the full Phase 5M agent-debate workspace from a Phase 5L boundary.

    Deterministic and offline. An empty boundary yields a safe empty workspace.
    Each research-pack bundle yields one debate session + one decision-workspace
    view.
    """
    sessions: list[AgentDebateSession] = []
    views: list[DecisionWorkspaceView] = []
    for bundle in boundary.pack_bundles:
        session = build_debate_session_from_research_pack(bundle)
        sessions.append(session)
        views.append(build_decision_workspace_view(session))

    validation = build_decision_workspace_validation_summary(
        sessions=sessions, views=views, is_empty=not sessions
    )

    warnings: list[DebateWarning] = [
        DebateWarning(
            warning_type="review_required",
            severity="info",
            message=(
                "This is an agent-debate / decision-workspace contract only. "
                "Agent roles are deterministic records; no live agent is run. "
                "The workspace is review-only and requires human review. No final "
                "buy/sell decision, no order instruction, no execution. Phase 5N "
                "Cockpit UI comes later. Not investment advice."
            ),
        )
    ]
    if not sessions:
        warnings.append(
            DebateWarning(
                warning_type="empty_pack",
                severity="info",
                message="Empty research-pack boundary; safe empty debate workspace.",
            )
        )

    return AgentDebateWorkspace(
        workspace_id=make_agent_debate_workspace_id(label),
        as_of=boundary.as_of,
        source_boundary_id=boundary.boundary_id,
        source_queue_id=boundary.source_queue_id,
        source_theme_snapshot_id=boundary.source_theme_snapshot_id,
        description=(
            "Agent debate / decision workspace derived from a Phase 5L auto "
            "research pack orchestration boundary. Evidence-first, horizon-aware, "
            "bull/bear/risk/critic-separated, allocation/option review-only. This "
            "is not a final trade recommendation."
        ),
        sessions=sessions,
        workspace_views=views,
        validation_summary=validation,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Fixtures — deterministic examples only (NOT live claims)
# ---------------------------------------------------------------------------


def build_default_agent_debate_workspace() -> AgentDebateWorkspace:
    """Default Phase 5M workspace from the Phase 5L default research pack bundle."""
    return build_agent_debate_workspace(
        build_default_research_pack_bundle(), label="default"
    )


def build_degraded_agent_debate_workspace() -> AgentDebateWorkspace:
    """Degraded Phase 5M workspace from the degraded research pack bundle.

    Produces research_more / blocked states and insufficient-evidence stances;
    no analysis is fabricated.
    """
    return build_agent_debate_workspace(
        build_degraded_research_pack_bundle(), label="degraded"
    )


def build_empty_agent_debate_workspace() -> AgentDebateWorkspace:
    """Safe empty Phase 5M workspace from the empty research pack bundle."""
    return build_agent_debate_workspace(
        build_empty_research_pack_bundle(), label="empty"
    )


def _fixture_gap(
    gap_type: str, severity: ThemeRiskSeverity, description: str, modules: tuple[str, ...]
) -> ResearchPackEvidenceGap:
    return ResearchPackEvidenceGap(
        gap_type=gap_type,
        severity=severity,
        description=description,
        addressed_by_modules=list(modules),
    )


def _fixture_bundle(
    *,
    ticker: str,
    theme_id: str,
    theme_name: str,
    horizon: OpportunityHorizon,
    decision: str,
    gaps: list[ResearchPackEvidenceGap],
    is_review_only: bool,
) -> ResearchPackBundle:
    req_objs, opt_objs = build_research_module_requests(
        horizon=horizon,
        decision_label=decision,
        evidence_gaps=gaps,
        is_review_only=is_review_only,
    )
    request = ResearchPackRequest(
        pack_request_id=make_research_pack_request_id(
            ticker, theme_id, horizon, decision
        ),
        ticker=ticker,
        theme_id=theme_id,
        theme_name=theme_name,
        horizon=horizon,
        decision_label=decision,
        evidence_gaps=gaps,
        required_modules=req_objs,
        optional_modules=opt_objs,
        is_review_only=is_review_only,
        notes="Synthetic Phase 5M fixture research-pack request (not live).",
    )
    return build_research_pack_bundle_from_fixture(request)


def build_conflict_agent_debate_session() -> AgentDebateSession:
    """Conflict fixture: bull constructive while bear/risk flag overextension.

    A strongly-constructive short-term decision (``trade_now``) carries crowding
    and valuation gaps. The Bull stays constructive; the Bear flags a crowded /
    overextended trade; Risk is high; the Critic surfaces the unresolved
    conflict. No executable recommendation is produced.
    """
    gaps = [
        _fixture_gap(
            "crowding_risk",
            "high",
            "Positioning is crowded; chasing risk is elevated.",
            ("price_volume_analysis", "risk_review"),
        ),
        _fixture_gap(
            "valuation_stretch",
            "medium",
            "Valuation looks stretched versus history.",
            ("financial_analysis", "risk_review"),
        ),
    ]
    bundle = _fixture_bundle(
        ticker="CONFLX",
        theme_id="theme_conflict",
        theme_name="Conflict Example Theme",
        horizon="short_term",
        decision="trade_now",
        gaps=gaps,
        is_review_only=False,
    )
    return build_debate_session_from_research_pack(bundle)


def build_no_trade_option_agent_debate_session() -> AgentDebateSession:
    """No-trade fixture: option perspective preserves ``no_trade`` first-class."""
    bundle = _fixture_bundle(
        ticker="NOTRDX",
        theme_id="theme_no_trade",
        theme_name="No-Trade Example Theme",
        horizon="short_term",
        decision="no_trade",
        gaps=[],
        is_review_only=True,
    )
    return build_debate_session_from_research_pack(bundle)


def build_research_more_agent_debate_session() -> AgentDebateSession:
    """Research-more fixture: missing evidence drives a research_more state."""
    gaps = [
        _fixture_gap(
            "incomplete_evidence",
            "high",
            "Evidence coverage is none; close before any decision.",
            ("evidence_validation", "company_research"),
        ),
        _fixture_gap(
            "missing_fundamental_confirmation",
            "medium",
            "No fundamental confirmation; confirm the thesis.",
            ("financial_analysis", "catalyst_earnings"),
        ),
    ]
    bundle = _fixture_bundle(
        ticker="RSCHX",
        theme_id="theme_research_more",
        theme_name="Research-More Example Theme",
        horizon="mid_term",
        decision="research_more",
        gaps=gaps,
        is_review_only=False,
    )
    return build_debate_session_from_research_pack(bundle)
