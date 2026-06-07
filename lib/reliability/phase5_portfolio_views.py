"""
lib/reliability/phase5_portfolio_views.py

Phase 5D: Portfolio / TradePlan / Option Overlay ViewModel Contract.

Purpose
-------
Defines deterministic, cockpit-ready Pydantic view-model contracts that
project Phase 4M allocation decision memory (Phase 4M-D) and Phase 4M
option trade plan memory (Phase 4M-E) into:

  1. Portfolio / Allocation Cockpit
       - aggregate AllocationSummaryView
       - per-record PositionAllocationView
       - RiskBudgetView / CashImpactView aggregates (only when supported
         by underlying memory records)
  2. TradePlan card representation
       - TradePlanView (one per allocation memory record)
       - TradePlanLevelView (entry / add / trim / stop / target zones
         sourced from the allocation snapshot — never fabricated)
       - TradePlanReviewTriggerView (review triggers + status)
  3. Option Overlay representation
       - OptionOverlayView (one per option trade plan memory record)
       - OptionStrategySummaryView / OptionRiskRewardView projections
       - OptionLiquidityWarningView / OptionEventRiskWarningView (only
         when the underlying record carries such signals)
       - NoTradeReasonView when the option decision is ``no_trade``

This module is a **view-model contract layer only**. It does not connect
to the live Streamlit app, does not introduce a UI, does not perform any
data fetch, does not invoke any LLM, and does not produce trade
instructions, executable orders, broker payloads, or investment advice.
It surfaces only what existing Phase 4M memory records carry, by
reference.

Design principles
-----------------
- Standalone, deterministic, offline / mock-only.
- No live LLM calls.
- No live data fetching, no Streamlit, no Anthropic SDK calls.
- No database writes, no file persistence, no vector store.
- No reading of the live workflow state JSON file.
- No import of ``app.py``, ``pages/*``, ``lib/llm_orchestrator.py``, or
  ``lib/workflow_state.py``.
- No broker / order / execution behavior.
- No order type, time-in-force, broker route, account ID, executable
  quantity, or live instruction is exposed by any view.
- No ``approved_for_execution`` field on any Phase 5D view; the upstream
  Phase 4M records already reject truthy ``approved_for_execution`` at
  their model layers, so this view layer inherits the invariant by
  construction.
- ``no_trade`` is a first-class, valid option state. Phase 5D never
  infers a substitute strategy when the underlying record reports
  ``no_trade``.

Relationship to Phase 4M / Phase 5A / Phase 5C
----------------------------------------------
- Phase 4M-D (``AllocationDecisionMemoryRecord``) drives the portfolio
  and trade-plan projections.
- Phase 4M-E (``OptionTradePlanMemoryRecord``) drives the option
  overlay projection (including the ``no_trade`` state).
- Phase 4M-F (``HumanFeedbackMemoryRecord``) is surfaced for review
  signals when target-matched records exist.
- Phase 5A's ``MemoryStoreProtocol`` / ``MemoryQueryResult`` provide
  the query boundary.
- Phase 5C ``HorizonDecisionCardsView`` / ``ThesisTrackerView`` are
  *optional* context the cockpit can compose alongside Phase 5D views;
  Phase 5D does not import the Phase 5C module to keep coupling
  minimal.

Execution safety boundary
-------------------------
Every Phase 5D view treats portfolio and trade-plan content as
research-only. ``ExecutionSafetyBannerView`` is attached to every
``PortfolioCockpitView`` and explicitly states the view is
non-executable / review-only. The cockpit can render the banner; it is
not a substitute for human review.

Disclaimer: outputs are for research / educational purposes only and do
not constitute investment advice.

See ``docs/reliability_phase_5d_portfolio_trade_option_view_model.md``.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from lib.reliability.allocation_memory import (
    AllocationDecisionMemoryRecord,
)
from lib.reliability.option_trade_memory import (
    OptionTradePlanMemoryRecord,
)
from lib.reliability.human_feedback_memory import HumanFeedbackMemoryRecord
from lib.reliability.phase5_memory_query import (
    MemoryQueryByTicker,
    MemoryQueryResult,
    MemoryStoreProtocol,
)


# ---------------------------------------------------------------------------
# Literal aliases
# ---------------------------------------------------------------------------

PortfolioDataSource = Literal[
    "phase4m_allocation_memory",
    "phase4m_option_trade_memory",
    "phase4m_human_feedback_memory",
    "memory_query_result",
    "absent",
]


# Slots in the trade plan derived from the underlying allocation snapshot.
# These labels are descriptive only — they are not order types.
TradePlanLevelKind = Literal[
    "entry",
    "add",
    "trim",
    "stop",
    "target",
    "review",
]


TRADE_PLAN_LEVEL_KINDS: tuple[TradePlanLevelKind, ...] = (
    "entry",
    "add",
    "trim",
    "stop",
    "target",
    "review",
)


MissingPortfolioPanel = Literal[
    "allocation",
    "trade_plan",
    "option_overlay",
    "risk_budget",
    "cash_impact",
    "human_feedback",
    "memory",
]


OptionOverlayState = Literal[
    "option",
    "stock",
    "no_trade",
    "wait",
    "unknown",
    "missing",
]


_CALCULATION_VERSION: str = "phase5_portfolio_views_v1"

_EXECUTION_SAFETY_BANNER_TEXT: str = (
    "Research-only view. This cockpit projection does NOT authorize any "
    "trade execution, broker routing, or order placement. No "
    "executable orders, time-in-force fields, account IDs, or broker "
    "routes are exposed. Human review is required before any action."
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _query_result_for_target(
    memory_store: Optional[MemoryStoreProtocol],
    target: Optional[str],
) -> MemoryQueryResult:
    """Run a target-scoped memory query. Empty result if no store / target."""
    if memory_store is None or target is None or not str(target).strip():
        return MemoryQueryResult()
    return memory_store.query(MemoryQueryByTicker(target=target))


def _is_truthy_review_required(record: Any) -> bool:
    rr = getattr(record, "review_required", None)
    if rr is not None:
        return bool(rr)
    summary = getattr(record, "summary", None)
    if summary is not None and not isinstance(summary, str):
        srr = getattr(summary, "review_required", None)
        if srr is not None:
            return bool(srr)
    return False


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in items:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# View models — safety / missing
# ---------------------------------------------------------------------------


class ExecutionSafetyBannerView(BaseModel):
    """
    Cockpit-side safety banner. Always present on a ``PortfolioCockpitView``.

    The banner states explicitly that the view is research-only and
    non-executable. Phase 5D does not generate orders, order tickets,
    broker payloads, or execution authorization. ``approved_for_execution``
    is *not* declared anywhere in Phase 5D.
    """

    model_config = ConfigDict(extra="forbid")

    is_non_executable: bool = True
    message: str = _EXECUTION_SAFETY_BANNER_TEXT
    requires_human_review: bool = True


class MissingPortfolioDataWarningView(BaseModel):
    """
    Surfaces missing-panel warnings deterministically.

    Each warning names which portfolio sub-view is missing and a short
    description. The cockpit degrades safely when allocation / option /
    human feedback records are absent: the corresponding sub-view returns
    a safe empty value and one warning is appended here.
    """

    model_config = ConfigDict(extra="forbid")

    missing_panels: list[MissingPortfolioPanel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class NoTradeReasonView(BaseModel):
    """
    Surfaces a ``no_trade`` decision from Phase 4M-E option trade plan
    memory.

    Phase 5D never infers a substitute strategy. When the underlying
    record reports ``decision="no_trade"`` (or ``strategy_type="no_trade"``
    or ``outcome="no_trade"``), the corresponding ``OptionOverlayView``
    carries this ``no_trade_reason`` view. The cockpit can render the
    reason; it is descriptive only.
    """

    model_config = ConfigDict(extra="forbid")

    is_no_trade: bool = True
    reason_text: str = ""
    review_trigger: Optional[str] = None
    rationale: str = ""
    source_record_id: Optional[str] = None


# ---------------------------------------------------------------------------
# View models — portfolio / allocation
# ---------------------------------------------------------------------------


class TradePlanLevelView(BaseModel):
    """
    One trade-plan level projection (entry / add / trim / stop / target /
    review).

    Levels are sourced *only* from the underlying allocation snapshot's
    bounded percentage fields and from the option trade memory's bounded
    risk fields. Phase 5D does not compute share counts, broker-routed
    quantities, or executable order parameters.

    All numeric fields are bounded as in their upstream model layers; this
    view does not enforce additional ranges.
    """

    model_config = ConfigDict(extra="forbid")

    kind: TradePlanLevelKind
    label: str = ""
    pct: Optional[float] = None
    value: Optional[float] = None
    note: str = ""
    source_field: Optional[str] = None


class TradePlanReviewTriggerView(BaseModel):
    """
    Surfaces the review-trigger surface for a trade plan derived from the
    Phase 4M-D allocation memory record.

    ``review_needed`` is True when the underlying allocation record has
    status ``blocked`` / ``needs_review``, review_status is ``pending`` /
    ``escalated`` / ``blocked``, or a target-scoped human feedback record
    flags review.
    """

    model_config = ConfigDict(extra="forbid")

    review_needed: bool = False
    review_trigger: Optional[str] = None
    status: str = "unknown"
    review_status: str = "unknown"
    reasons: list[str] = Field(default_factory=list)


class PositionAllocationView(BaseModel):
    """
    One allocation decision memory record projection.

    Preserves the underlying allocation_memory_id, action, status, and
    bounded snapshot fields. Surfaces evidence refs and source IDs. Never
    fabricates allocation numbers, brokerage values, or executable
    quantities.
    """

    model_config = ConfigDict(extra="forbid")

    allocation_memory_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    horizon: Optional[str] = None
    action: str = "unknown"
    status: str = "unknown"
    review_status: str = "unknown"
    outcome: str = "unknown"
    target_allocation_pct: Optional[float] = None
    actual_allocation_pct: Optional[float] = None
    min_allocation_pct: Optional[float] = None
    max_allocation_pct: Optional[float] = None
    cash_pct: Optional[float] = None
    cash_impact: Optional[float] = None
    projected_cash_pct: Optional[float] = None
    portfolio_loss_pct: Optional[float] = None
    risk_budget_pct: Optional[float] = None
    risk_level: str = "unknown"
    rationale: str = ""
    review_trigger: Optional[str] = None
    snapshot_id: Optional[str] = None
    recorded_at: Optional[str] = None
    run_id: Optional[str] = None
    thesis_id: Optional[str] = None
    decision_packet_id: Optional[str] = None
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    review_needed: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    data_source: PortfolioDataSource = "absent"


class RiskBudgetView(BaseModel):
    """
    Aggregate risk-budget projection.

    Counts and surfaces only the deterministic ``risk_budget_pct`` /
    ``portfolio_loss_pct`` / ``risk_level`` fields the underlying
    allocation records carry. ``has_risk_budget`` is True only when at
    least one record contributed a non-None value.
    """

    model_config = ConfigDict(extra="forbid")

    record_count: int = 0
    high_risk_count: int = 0
    medium_risk_count: int = 0
    low_risk_count: int = 0
    unknown_risk_count: int = 0
    max_risk_budget_pct: Optional[float] = None
    max_portfolio_loss_pct: Optional[float] = None
    has_risk_budget: bool = False
    warnings: list[str] = Field(default_factory=list)


class CashImpactView(BaseModel):
    """
    Aggregate cash-impact projection.

    Sums ``cash_impact`` values across the underlying allocation records
    when present; never invents cash flows. ``has_cash_impact`` is True
    only when at least one record contributed a non-None value.
    """

    model_config = ConfigDict(extra="forbid")

    record_count: int = 0
    total_cash_impact: Optional[float] = None
    min_projected_cash_pct: Optional[float] = None
    max_projected_cash_pct: Optional[float] = None
    has_cash_impact: bool = False
    warnings: list[str] = Field(default_factory=list)


class AllocationSummaryView(BaseModel):
    """
    Aggregate allocation-summary projection.

    Counts allocation records by action / status / review status without
    fabricating clean state. ``has_any_records`` is True only when at
    least one allocation memory record contributed.
    """

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    record_count: int = 0
    action_counts: dict[str, int] = Field(default_factory=dict)
    status_counts: dict[str, int] = Field(default_factory=dict)
    review_status_counts: dict[str, int] = Field(default_factory=dict)
    has_any_records: bool = False
    blocked_count: int = 0
    needs_review_count: int = 0
    reviewed_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    data_source: PortfolioDataSource = "absent"


# ---------------------------------------------------------------------------
# View models — trade plan
# ---------------------------------------------------------------------------


class TradePlanView(BaseModel):
    """
    One TradePlan card projection.

    Derived from one Phase 4M-D allocation decision memory record. Levels
    enumerate entry / add / trim / stop / target / review slots based on
    the underlying snapshot — values are only filled when the upstream
    record carries them. Phase 5D never converts a TradePlan into an
    executable order: no order type, no time-in-force, no broker route,
    no account ID, no live instruction.
    """

    model_config = ConfigDict(extra="forbid")

    allocation_memory_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    action: str = "unknown"
    status: str = "unknown"
    review_status: str = "unknown"
    rationale: str = ""
    levels: list[TradePlanLevelView] = Field(default_factory=list)
    review_trigger: TradePlanReviewTriggerView = Field(
        default_factory=TradePlanReviewTriggerView
    )
    related_decision_packet_id: Optional[str] = None
    related_thesis_id: Optional[str] = None
    related_run_id: Optional[str] = None
    related_evidence_ids: list[str] = Field(default_factory=list)
    related_artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    data_source: PortfolioDataSource = "absent"
    # No 'approved_for_execution' field — explicit invariant.


# ---------------------------------------------------------------------------
# View models — option overlay
# ---------------------------------------------------------------------------


class OptionStrategySummaryView(BaseModel):
    """
    Read-only projection of the option strategy header.

    All fields are surfaced exactly as they appear on the underlying
    Phase 4M-E ``OptionTradePlanSnapshot``. ``no_trade`` strategies still
    receive a strategy summary (with empty option metrics) so the cockpit
    can render the slot uniformly.
    """

    model_config = ConfigDict(extra="forbid")

    decision: str = "unknown"
    strategy_type: str = "unknown"
    expiration: Optional[str] = None
    contracts: Optional[int] = None
    planned_exit_rule: Optional[str] = None
    actual_exit_reason: Optional[str] = None
    risk_level: str = "unknown"


class OptionRiskRewardView(BaseModel):
    """
    Read-only projection of the option risk / reward surface.

    Surfaces only the bounded numeric fields the underlying snapshot
    carries: max_loss, max_gain, breakeven, entry_iv, exit_iv,
    entry_underlying_price, cash_required, risk_reward_ratio. Phase 5D
    does not compute live Greeks, IV rank, margin, assignment risk,
    probability of profit, or any live market quantity.
    """

    model_config = ConfigDict(extra="forbid")

    max_loss: Optional[float] = None
    max_gain: Optional[float] = None
    breakeven: Optional[float] = None
    entry_iv: Optional[float] = None
    exit_iv: Optional[float] = None
    entry_underlying_price: Optional[float] = None
    exit_underlying_price: Optional[float] = None
    cash_required: Optional[float] = None
    risk_reward_ratio: Optional[float] = None


class OptionLiquidityWarningView(BaseModel):
    """
    Surfaces option liquidity warnings as carried by the underlying
    snapshot / record warnings list. Phase 5D does not compute live
    liquidity scores.
    """

    model_config = ConfigDict(extra="forbid")

    has_liquidity_warning: bool = False
    warnings: list[str] = Field(default_factory=list)


class OptionEventRiskWarningView(BaseModel):
    """
    Surfaces option event-risk warnings as carried by the underlying
    snapshot / record warnings list (e.g. earnings inside expiration).
    Phase 5D does not compute live event risk.
    """

    model_config = ConfigDict(extra="forbid")

    has_event_risk_warning: bool = False
    warnings: list[str] = Field(default_factory=list)


class OptionOverlayView(BaseModel):
    """
    One option-overlay projection derived from a Phase 4M-E option trade
    plan memory record.

    ``no_trade`` is a first-class valid state. When the underlying record
    reports ``decision="no_trade"`` (or ``strategy_type="no_trade"`` /
    ``outcome="no_trade"``), Phase 5D does NOT infer a substitute
    strategy: the overlay view exposes a ``no_trade_reason`` view and
    leaves the risk/reward view empty. The cockpit can render the
    no-trade state; Phase 5D never authorizes alternative trades.

    No ``approved_for_execution`` field. No executable order field. No
    broker route. No account ID.
    """

    model_config = ConfigDict(extra="forbid")

    option_trade_memory_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    state: OptionOverlayState = "unknown"
    is_no_trade: bool = False
    status: str = "unknown"
    review_status: str = "unknown"
    outcome: str = "unknown"
    rationale: str = ""
    strategy_summary: OptionStrategySummaryView = Field(
        default_factory=OptionStrategySummaryView
    )
    risk_reward: OptionRiskRewardView = Field(default_factory=OptionRiskRewardView)
    liquidity_warning: OptionLiquidityWarningView = Field(
        default_factory=OptionLiquidityWarningView
    )
    event_risk_warning: OptionEventRiskWarningView = Field(
        default_factory=OptionEventRiskWarningView
    )
    no_trade_reason: Optional[NoTradeReasonView] = None
    related_thesis_id: Optional[str] = None
    related_allocation_memory_id: Optional[str] = None
    related_decision_packet_id: Optional[str] = None
    related_run_id: Optional[str] = None
    related_evidence_ids: list[str] = Field(default_factory=list)
    related_artifact_refs: list[str] = Field(default_factory=list)
    review_needed: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    data_source: PortfolioDataSource = "absent"
    # No 'approved_for_execution' field — explicit invariant.


# ---------------------------------------------------------------------------
# View models — portfolio cockpit (aggregate)
# ---------------------------------------------------------------------------


class PortfolioCockpitView(BaseModel):
    """
    Aggregate Portfolio / Allocation Cockpit projection.

    Combines per-target allocation positions, the aggregate allocation
    summary, the deterministic risk-budget and cash-impact aggregates,
    one or more trade plans, one or more option overlays, the
    execution-safety banner, and missing-data warnings.

    Never exposes ``approved_for_execution``. No Phase 5D class declares
    that field. The underlying Phase 4M records already reject truthy
    values at their model layers.
    """

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    allocation_summary: AllocationSummaryView
    positions: list[PositionAllocationView] = Field(default_factory=list)
    risk_budget: RiskBudgetView = Field(default_factory=RiskBudgetView)
    cash_impact: CashImpactView = Field(default_factory=CashImpactView)
    trade_plans: list[TradePlanView] = Field(default_factory=list)
    option_overlays: list[OptionOverlayView] = Field(default_factory=list)
    execution_safety_banner: ExecutionSafetyBannerView = Field(
        default_factory=ExecutionSafetyBannerView
    )
    missing_data: MissingPortfolioDataWarningView = Field(
        default_factory=MissingPortfolioDataWarningView
    )
    warnings: list[str] = Field(default_factory=list)
    calculation_version: str = _CALCULATION_VERSION
    # No 'approved_for_execution' field — explicit invariant.


# ---------------------------------------------------------------------------
# Builder helpers — safety / missing
# ---------------------------------------------------------------------------


def build_execution_safety_banner() -> ExecutionSafetyBannerView:
    """Build a deterministic execution-safety banner.

    Always returns the same content for the same Phase 5D version. The
    banner exists so the cockpit always carries an explicit non-executable
    statement.
    """
    return ExecutionSafetyBannerView(
        is_non_executable=True,
        message=_EXECUTION_SAFETY_BANNER_TEXT,
        requires_human_review=True,
    )


def build_no_trade_reason_view(
    option_record: OptionTradePlanMemoryRecord,
) -> NoTradeReasonView:
    """Build a ``NoTradeReasonView`` from a Phase 4M-E option trade record.

    The view never infers a substitute strategy. If the supplied record
    is not in a no-trade state (decision / strategy_type / outcome), the
    builder still returns a ``NoTradeReasonView`` with ``is_no_trade``
    reflecting the underlying record's no-trade signal.
    """
    is_no_trade = (
        str(option_record.decision) == "no_trade"
        or str(option_record.plan_snapshot.strategy_type) == "no_trade"
        or str(option_record.outcome) == "no_trade"
    )
    reason_text = (
        "Underlying option trade plan memory record reports no_trade. "
        "Phase 5D does not infer a substitute strategy."
        if is_no_trade
        else "Underlying option trade plan memory record is not in a no_trade state."
    )
    return NoTradeReasonView(
        is_no_trade=is_no_trade,
        reason_text=reason_text,
        review_trigger=option_record.review_trigger,
        rationale=option_record.rationale,
        source_record_id=option_record.option_trade_memory_id,
    )


# ---------------------------------------------------------------------------
# Builder helpers — allocation
# ---------------------------------------------------------------------------


def _human_feedback_review_signals_for_target(
    target: str,
    human_feedback_records: list[HumanFeedbackMemoryRecord],
) -> list[str]:
    """Collect review reasons from target-scoped human feedback records."""
    reasons: list[str] = []
    for f in human_feedback_records:
        if getattr(f, "target", None) != target:
            continue
        if _is_truthy_review_required(f):
            fid = getattr(f, "feedback_memory_id", "")
            reasons.append(
                f"Human feedback record requires review "
                f"(feedback_memory_id={fid!r})."
            )
            continue
        fs = str(getattr(f, "status", "") or "")
        if fs in ("blocked", "needs_review"):
            reasons.append(f"Human feedback record status is {fs!r}.")
    return reasons


def _allocation_review_reasons(
    record: AllocationDecisionMemoryRecord,
    feedback_reasons: list[str],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    status = str(record.status)
    review_status = str(record.review_status)
    if status == "blocked":
        reasons.append(f"Allocation record status is {status!r}.")
    elif status == "needs_review":
        reasons.append(f"Allocation record status is {status!r}.")
    if review_status in ("pending", "escalated", "blocked"):
        reasons.append(f"Allocation review_status is {review_status!r}.")
    if record.review_trigger:
        reasons.append(
            f"Allocation review_trigger: {record.review_trigger!r}."
        )
    reasons.extend(feedback_reasons)
    review_needed = bool(reasons) or status in ("blocked", "needs_review") or (
        review_status in ("pending", "escalated", "blocked")
    )
    return review_needed, reasons


def build_position_allocation_view(
    record: AllocationDecisionMemoryRecord,
    human_feedback_records: Optional[list[HumanFeedbackMemoryRecord]] = None,
) -> PositionAllocationView:
    """Build a ``PositionAllocationView`` from a Phase 4M-D record.

    Never fabricates allocation numbers; surfaces only what the record
    carries. Human feedback reasons surface as ``review_reasons`` when
    the supplied feedback list contains target-scoped records.
    """
    feedback_reasons = _human_feedback_review_signals_for_target(
        target=record.target,
        human_feedback_records=list(human_feedback_records or []),
    )
    review_needed, reasons = _allocation_review_reasons(record, feedback_reasons)
    return PositionAllocationView(
        allocation_memory_id=record.allocation_memory_id,
        target=record.target,
        action=str(record.action),
        status=str(record.status),
        review_status=str(record.review_status),
        outcome=str(record.outcome),
        target_allocation_pct=record.decision_snapshot.target_allocation_pct,
        actual_allocation_pct=record.decision_snapshot.actual_allocation_pct,
        min_allocation_pct=record.decision_snapshot.min_allocation_pct,
        max_allocation_pct=record.decision_snapshot.max_allocation_pct,
        cash_pct=record.decision_snapshot.cash_pct,
        cash_impact=record.decision_snapshot.cash_impact,
        projected_cash_pct=record.decision_snapshot.projected_cash_pct,
        portfolio_loss_pct=record.decision_snapshot.portfolio_loss_pct,
        risk_budget_pct=record.decision_snapshot.risk_budget_pct,
        risk_level=str(record.decision_snapshot.risk_level),
        rationale=record.rationale,
        review_trigger=record.review_trigger,
        snapshot_id=record.decision_snapshot.snapshot_id,
        recorded_at=record.recorded_at,
        run_id=record.run_id,
        thesis_id=record.thesis_id,
        decision_packet_id=record.decision_packet_id,
        evidence_ids=list(record.evidence_ids),
        artifact_refs=list(record.artifact_refs),
        source_ids=[ref.source_id for ref in record.source_refs],
        review_needed=review_needed,
        review_reasons=reasons,
        warnings=list(record.warnings),
        data_source="phase4m_allocation_memory",
    )


def build_allocation_summary_view(
    target: str,
    allocation_records: list[AllocationDecisionMemoryRecord],
) -> AllocationSummaryView:
    """Build an aggregate ``AllocationSummaryView``.

    Counts records by action / status / review_status. Never fabricates
    a clean state when no records exist — ``has_any_records`` reflects
    whether any allocation record was inspected.
    """
    if not target or not str(target).strip():
        raise ValueError("'target' must not be empty or whitespace-only.")
    action_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    review_status_counts: dict[str, int] = {}
    blocked = 0
    needs_review = 0
    reviewed = 0
    for r in allocation_records:
        action_counts[r.action] = action_counts.get(r.action, 0) + 1
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
        review_status_counts[r.review_status] = (
            review_status_counts.get(r.review_status, 0) + 1
        )
        if r.status == "blocked":
            blocked += 1
        elif r.status == "needs_review":
            needs_review += 1
        elif r.status == "reviewed":
            reviewed += 1

    warnings: list[str] = []
    if not allocation_records:
        warnings.append(
            "No Phase 4M-D allocation decision memory records supplied; "
            "allocation summary is empty."
        )

    return AllocationSummaryView(
        target=target,
        record_count=len(allocation_records),
        action_counts=action_counts,
        status_counts=status_counts,
        review_status_counts=review_status_counts,
        has_any_records=bool(allocation_records),
        blocked_count=blocked,
        needs_review_count=needs_review,
        reviewed_count=reviewed,
        warnings=warnings,
        data_source=(
            "phase4m_allocation_memory"
            if allocation_records
            else "absent"
        ),
    )


def _build_risk_budget_view(
    allocation_records: list[AllocationDecisionMemoryRecord],
) -> RiskBudgetView:
    high = sum(
        1 for r in allocation_records if r.decision_snapshot.risk_level == "high"
    )
    medium = sum(
        1 for r in allocation_records if r.decision_snapshot.risk_level == "medium"
    )
    low = sum(
        1 for r in allocation_records if r.decision_snapshot.risk_level == "low"
    )
    unknown = sum(
        1
        for r in allocation_records
        if r.decision_snapshot.risk_level not in ("high", "medium", "low")
    )
    risk_budget_pcts = [
        r.decision_snapshot.risk_budget_pct
        for r in allocation_records
        if r.decision_snapshot.risk_budget_pct is not None
    ]
    portfolio_loss_pcts = [
        r.decision_snapshot.portfolio_loss_pct
        for r in allocation_records
        if r.decision_snapshot.portfolio_loss_pct is not None
    ]
    has_risk = bool(risk_budget_pcts) or bool(portfolio_loss_pcts)
    warnings: list[str] = []
    if not allocation_records:
        warnings.append(
            "No allocation memory records supplied; risk budget view empty."
        )
    elif not has_risk:
        warnings.append(
            "Allocation records did not carry risk_budget_pct or "
            "portfolio_loss_pct; risk budget view empty."
        )
    return RiskBudgetView(
        record_count=len(allocation_records),
        high_risk_count=high,
        medium_risk_count=medium,
        low_risk_count=low,
        unknown_risk_count=unknown,
        max_risk_budget_pct=max(risk_budget_pcts) if risk_budget_pcts else None,
        max_portfolio_loss_pct=(
            max(portfolio_loss_pcts) if portfolio_loss_pcts else None
        ),
        has_risk_budget=has_risk,
        warnings=warnings,
    )


def _build_cash_impact_view(
    allocation_records: list[AllocationDecisionMemoryRecord],
) -> CashImpactView:
    cash_impacts = [
        r.decision_snapshot.cash_impact
        for r in allocation_records
        if r.decision_snapshot.cash_impact is not None
    ]
    projected = [
        r.decision_snapshot.projected_cash_pct
        for r in allocation_records
        if r.decision_snapshot.projected_cash_pct is not None
    ]
    has_cash = bool(cash_impacts) or bool(projected)
    warnings: list[str] = []
    if not allocation_records:
        warnings.append(
            "No allocation memory records supplied; cash impact view empty."
        )
    elif not has_cash:
        warnings.append(
            "Allocation records did not carry cash_impact or "
            "projected_cash_pct; cash impact view empty."
        )
    return CashImpactView(
        record_count=len(allocation_records),
        total_cash_impact=(
            round(sum(cash_impacts), 10) if cash_impacts else None
        ),
        min_projected_cash_pct=min(projected) if projected else None,
        max_projected_cash_pct=max(projected) if projected else None,
        has_cash_impact=has_cash,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Builder helpers — trade plan
# ---------------------------------------------------------------------------


def _trade_plan_levels_from_allocation(
    record: AllocationDecisionMemoryRecord,
) -> list[TradePlanLevelView]:
    """Project an allocation snapshot into descriptive trade-plan levels.

    Levels are descriptive cockpit slots. No executable order parameters
    are introduced; values reflect only the underlying snapshot fields.
    """
    snap = record.decision_snapshot
    levels: list[TradePlanLevelView] = []
    levels.append(
        TradePlanLevelView(
            kind="entry",
            label="Target allocation",
            pct=snap.target_allocation_pct,
            source_field="decision_snapshot.target_allocation_pct",
            note=(
                "Snapshot target allocation percentage; descriptive only, "
                "not an executable order."
            ),
        )
    )
    if str(record.action) == "add":
        add_label = "Add toward target"
    elif str(record.action) == "trim":
        add_label = "Trim toward target"
    else:
        add_label = f"Action: {record.action}"
    levels.append(
        TradePlanLevelView(
            kind="add",
            label=add_label,
            pct=snap.max_allocation_pct,
            source_field="decision_snapshot.max_allocation_pct",
            note=(
                "Snapshot maximum allowed allocation percentage; "
                "descriptive only."
            ),
        )
    )
    levels.append(
        TradePlanLevelView(
            kind="trim",
            label="Trim threshold",
            pct=snap.min_allocation_pct,
            source_field="decision_snapshot.min_allocation_pct",
            note=(
                "Snapshot minimum allocation percentage; descriptive only."
            ),
        )
    )
    levels.append(
        TradePlanLevelView(
            kind="stop",
            label="Portfolio loss budget",
            pct=snap.portfolio_loss_pct,
            source_field="decision_snapshot.portfolio_loss_pct",
            note=(
                "Snapshot portfolio loss budget; descriptive only, not a "
                "broker-routed stop order."
            ),
        )
    )
    levels.append(
        TradePlanLevelView(
            kind="target",
            label="Target allocation (target zone)",
            pct=snap.target_allocation_pct,
            source_field="decision_snapshot.target_allocation_pct",
            note=(
                "Snapshot target allocation; descriptive only, not a "
                "limit/profit-target order."
            ),
        )
    )
    levels.append(
        TradePlanLevelView(
            kind="review",
            label="Review trigger",
            pct=None,
            source_field=(
                "review_trigger" if record.review_trigger else None
            ),
            note=record.review_trigger or "No review trigger recorded.",
        )
    )
    return levels


def build_trade_plan_view(
    record: AllocationDecisionMemoryRecord,
    human_feedback_records: Optional[list[HumanFeedbackMemoryRecord]] = None,
) -> TradePlanView:
    """Build a ``TradePlanView`` from one Phase 4M-D allocation record.

    Levels enumerate entry / add / trim / stop / target / review slots
    based only on the underlying snapshot. ``review_trigger`` aggregates
    the record's status / review_status / review_trigger / human-feedback
    signals.
    """
    feedback_reasons = _human_feedback_review_signals_for_target(
        target=record.target,
        human_feedback_records=list(human_feedback_records or []),
    )
    review_needed, reasons = _allocation_review_reasons(record, feedback_reasons)
    levels = _trade_plan_levels_from_allocation(record)
    return TradePlanView(
        allocation_memory_id=record.allocation_memory_id,
        target=record.target,
        action=str(record.action),
        status=str(record.status),
        review_status=str(record.review_status),
        rationale=record.rationale,
        levels=levels,
        review_trigger=TradePlanReviewTriggerView(
            review_needed=review_needed,
            review_trigger=record.review_trigger,
            status=str(record.status),
            review_status=str(record.review_status),
            reasons=reasons,
        ),
        related_decision_packet_id=record.decision_packet_id,
        related_thesis_id=record.thesis_id,
        related_run_id=record.run_id,
        related_evidence_ids=list(record.evidence_ids),
        related_artifact_refs=list(record.artifact_refs),
        warnings=list(record.warnings),
        data_source="phase4m_allocation_memory",
    )


# ---------------------------------------------------------------------------
# Builder helpers — option overlay
# ---------------------------------------------------------------------------


def _filter_warnings(warnings: list[str], keywords: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for w in warnings:
        wl = w.lower()
        if any(k in wl for k in keywords):
            out.append(w)
    return out


def _option_review_reasons(
    record: OptionTradePlanMemoryRecord,
    feedback_reasons: list[str],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    status = str(record.status)
    review_status = str(record.review_status)
    if status in ("blocked", "needs_review"):
        reasons.append(f"Option trade record status is {status!r}.")
    if review_status in ("pending", "escalated", "blocked"):
        reasons.append(
            f"Option trade review_status is {review_status!r}."
        )
    if record.review_trigger:
        reasons.append(
            f"Option trade review_trigger: {record.review_trigger!r}."
        )
    reasons.extend(feedback_reasons)
    review_needed = bool(reasons) or status in ("blocked", "needs_review") or (
        review_status in ("pending", "escalated", "blocked")
    )
    return review_needed, reasons


def build_option_overlay_view(
    record: OptionTradePlanMemoryRecord,
    human_feedback_records: Optional[list[HumanFeedbackMemoryRecord]] = None,
) -> OptionOverlayView:
    """Build an ``OptionOverlayView`` from a Phase 4M-E record.

    ``no_trade`` is preserved as a first-class state. When the underlying
    record reports a no-trade state, Phase 5D never infers a substitute
    strategy; the overlay carries an explicit ``NoTradeReasonView`` and
    its risk/reward view is left empty.
    """
    snap = record.plan_snapshot
    is_no_trade = (
        str(record.decision) == "no_trade"
        or str(snap.strategy_type) == "no_trade"
        or str(record.outcome) == "no_trade"
    )
    if is_no_trade:
        state: OptionOverlayState = "no_trade"
    else:
        d = str(record.decision)
        if d in ("option", "stock", "wait"):
            state = d  # type: ignore[assignment]
        else:
            state = "unknown"

    strategy_summary = OptionStrategySummaryView(
        decision=str(record.decision),
        strategy_type=str(snap.strategy_type),
        expiration=snap.expiration,
        contracts=snap.contracts,
        planned_exit_rule=snap.planned_exit_rule,
        actual_exit_reason=snap.actual_exit_reason,
        risk_level=str(snap.risk_level),
    )

    if is_no_trade:
        risk_reward = OptionRiskRewardView()  # empty — no fabrication
    else:
        risk_reward = OptionRiskRewardView(
            max_loss=snap.max_loss,
            max_gain=snap.max_gain,
            breakeven=snap.breakeven,
            entry_iv=snap.entry_iv,
            exit_iv=snap.exit_iv,
            entry_underlying_price=snap.entry_underlying_price,
            exit_underlying_price=snap.exit_underlying_price,
            cash_required=snap.cash_required,
            risk_reward_ratio=snap.risk_reward_ratio,
        )

    # Surface upstream warnings that mention liquidity or event risk.
    all_warnings = list(record.warnings) + list(snap.warnings)
    liquidity_warnings = _filter_warnings(
        all_warnings, ("liquidity", "bid-ask", "spread", "open interest")
    )
    event_warnings = _filter_warnings(
        all_warnings, ("event risk", "earnings", "ex-dividend", "expiration", "expiry")
    )

    liquidity_view = OptionLiquidityWarningView(
        has_liquidity_warning=bool(liquidity_warnings),
        warnings=liquidity_warnings,
    )
    event_view = OptionEventRiskWarningView(
        has_event_risk_warning=bool(event_warnings),
        warnings=event_warnings,
    )

    no_trade_reason: Optional[NoTradeReasonView] = (
        build_no_trade_reason_view(record) if is_no_trade else None
    )

    feedback_reasons = _human_feedback_review_signals_for_target(
        target=record.target,
        human_feedback_records=list(human_feedback_records or []),
    )
    review_needed, reasons = _option_review_reasons(record, feedback_reasons)

    return OptionOverlayView(
        option_trade_memory_id=record.option_trade_memory_id,
        target=record.target,
        state=state,
        is_no_trade=is_no_trade,
        status=str(record.status),
        review_status=str(record.review_status),
        outcome=str(record.outcome),
        rationale=record.rationale,
        strategy_summary=strategy_summary,
        risk_reward=risk_reward,
        liquidity_warning=liquidity_view,
        event_risk_warning=event_view,
        no_trade_reason=no_trade_reason,
        related_thesis_id=record.thesis_id,
        related_allocation_memory_id=record.allocation_memory_id,
        related_decision_packet_id=record.decision_packet_id,
        related_run_id=record.run_id,
        related_evidence_ids=list(record.evidence_ids),
        related_artifact_refs=list(record.artifact_refs),
        review_needed=review_needed,
        review_reasons=reasons,
        warnings=list(record.warnings),
        data_source="phase4m_option_trade_memory",
    )


# ---------------------------------------------------------------------------
# Builder — top-level portfolio cockpit
# ---------------------------------------------------------------------------


def _collect_missing_data_warnings(
    *,
    allocation_records: list[AllocationDecisionMemoryRecord],
    option_records: list[OptionTradePlanMemoryRecord],
    human_feedback_records: list[HumanFeedbackMemoryRecord],
    risk_budget: RiskBudgetView,
    cash_impact: CashImpactView,
    memory_supplied: bool,
) -> MissingPortfolioDataWarningView:
    missing: list[MissingPortfolioPanel] = []
    warnings: list[str] = []
    if not memory_supplied:
        missing.append("memory")
        warnings.append(
            "No memory store or query result supplied; portfolio cockpit "
            "view returned safe degraded state."
        )
    if not allocation_records:
        missing.append("allocation")
        warnings.append(
            "No Phase 4M-D allocation decision memory records found; "
            "allocation summary and positions returned empty."
        )
        missing.append("trade_plan")
        warnings.append(
            "No allocation memory records found; trade plan list returned "
            "empty (Phase 5D never fabricates a trade plan)."
        )
    if not option_records:
        missing.append("option_overlay")
        warnings.append(
            "No Phase 4M-E option trade plan memory records found; "
            "option overlay list returned empty (Phase 5D never infers a "
            "strategy)."
        )
    if not risk_budget.has_risk_budget:
        missing.append("risk_budget")
        warnings.append(
            "Risk budget view empty (no risk_budget_pct or "
            "portfolio_loss_pct supplied by allocation records)."
        )
    if not cash_impact.has_cash_impact:
        missing.append("cash_impact")
        warnings.append(
            "Cash impact view empty (no cash_impact or projected_cash_pct "
            "supplied by allocation records)."
        )
    if not human_feedback_records:
        missing.append("human_feedback")
        warnings.append(
            "No Phase 4M-F human feedback records found for target; "
            "review reasons from human feedback are unavailable."
        )
    return MissingPortfolioDataWarningView(
        missing_panels=missing,
        warnings=warnings,
    )


def build_portfolio_cockpit_view(
    target: str,
    memory_store: Optional[MemoryStoreProtocol] = None,
    memory_query_result: Optional[MemoryQueryResult] = None,
) -> PortfolioCockpitView:
    """
    Build a deterministic ``PortfolioCockpitView`` for one target.

    Parameters
    ----------
    target : str
        Ticker / research target identifier. Required.
    memory_store : MemoryStoreProtocol, optional
        Phase 5A memory store. When supplied and ``memory_query_result``
        is not, a target-scoped query is run internally.
    memory_query_result : MemoryQueryResult, optional
        Pre-computed memory query result; takes precedence over
        ``memory_store`` for the records this view consumes.

    Returns
    -------
    PortfolioCockpitView
        Aggregate portfolio + trade-plan + option-overlay projection
        with an attached execution-safety banner and deterministic
        missing-data warnings. Never carries an ``approved_for_execution``
        flag.
    """
    if not target or not str(target).strip():
        raise ValueError("'target' must not be empty or whitespace-only.")

    memory_supplied = (memory_store is not None) or (
        memory_query_result is not None
    )

    result = memory_query_result
    if result is None:
        result = _query_result_for_target(memory_store, target)

    allocation_records = [
        r for r in result.allocation_records
        if getattr(r, "target", None) == target
    ]
    option_records = [
        r for r in result.option_trade_records
        if getattr(r, "target", None) == target
    ]
    human_feedback_records = [
        r for r in result.human_feedback_records
        if getattr(r, "target", None) == target
    ]

    allocation_summary = build_allocation_summary_view(
        target=target, allocation_records=allocation_records
    )
    positions = [
        build_position_allocation_view(
            record=r, human_feedback_records=human_feedback_records
        )
        for r in allocation_records
    ]
    risk_budget = _build_risk_budget_view(allocation_records)
    cash_impact = _build_cash_impact_view(allocation_records)
    trade_plans = [
        build_trade_plan_view(
            record=r, human_feedback_records=human_feedback_records
        )
        for r in allocation_records
    ]
    option_overlays = [
        build_option_overlay_view(
            record=r, human_feedback_records=human_feedback_records
        )
        for r in option_records
    ]

    missing_data = _collect_missing_data_warnings(
        allocation_records=allocation_records,
        option_records=option_records,
        human_feedback_records=human_feedback_records,
        risk_budget=risk_budget,
        cash_impact=cash_impact,
        memory_supplied=memory_supplied,
    )

    warnings: list[str] = []
    if not memory_supplied:
        warnings.append(
            "No memory store or query result supplied; portfolio cockpit "
            "view built without memory-backed evidence."
        )

    return PortfolioCockpitView(
        target=target,
        allocation_summary=allocation_summary,
        positions=positions,
        risk_budget=risk_budget,
        cash_impact=cash_impact,
        trade_plans=trade_plans,
        option_overlays=option_overlays,
        execution_safety_banner=build_execution_safety_banner(),
        missing_data=missing_data,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Literal aliases / constants
    "PortfolioDataSource",
    "TradePlanLevelKind",
    "TRADE_PLAN_LEVEL_KINDS",
    "MissingPortfolioPanel",
    "OptionOverlayState",
    # Safety / missing views
    "ExecutionSafetyBannerView",
    "MissingPortfolioDataWarningView",
    "NoTradeReasonView",
    # Portfolio / allocation views
    "TradePlanLevelView",
    "TradePlanReviewTriggerView",
    "PositionAllocationView",
    "RiskBudgetView",
    "CashImpactView",
    "AllocationSummaryView",
    # Trade plan view
    "TradePlanView",
    # Option overlay views
    "OptionStrategySummaryView",
    "OptionRiskRewardView",
    "OptionLiquidityWarningView",
    "OptionEventRiskWarningView",
    "OptionOverlayView",
    # Aggregate view
    "PortfolioCockpitView",
    # Builders
    "build_execution_safety_banner",
    "build_no_trade_reason_view",
    "build_position_allocation_view",
    "build_allocation_summary_view",
    "build_trade_plan_view",
    "build_option_overlay_view",
    "build_portfolio_cockpit_view",
]
