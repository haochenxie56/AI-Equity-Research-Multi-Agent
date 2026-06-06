"""
lib/reliability/option_trade_memory.py

Phase 4M-E: Option Trade Plan Memory.

Design principles:
  - Standalone, deterministic, offline/mock-only.
  - No live LLM calls, no live data fetching, no app integration.
  - No database writes, no file persistence, no vector store.
  - No broker / order / execution behavior.
  - No pathway that can set approved_for_execution = True.
  - No live option-chain API calls, no brokerage imports.
  - Defines memory records and helper functions only.
  - Records option expression decisions with strategy, entry IV, expiration,
    max loss, exit rule, actual exit, PnL placeholders, and lessons learned.
  - Consumes typed research artifacts from prior phases via source IDs /
    evidence IDs without duplicating full upstream artifact content.
  - Missing optional prior artifacts produce warnings, not crashes.
  - Does NOT import from app.py, pages/*, lib/llm_orchestrator.py, or any
    live workflow module.
  - Does NOT produce investment advice, buy/sell recommendations, or
    individual security recommendations.
  - approved_for_execution is ALWAYS False. No pathway to set it True exists.
  - no_trade is a first-class, safe decision outcome.
  - PnL fields (pnl_amount, pnl_pct) may be signed (negative for losses).

Report-level status precedence:
  blocked > needs_review > closed > reviewed > active > planned > archived > unknown

  - blocked       — human review blocked in input_bundle, OR any record is blocked
  - needs_review  — any record is needs_review, OR any high-risk unreviewed record
  - closed        — all non-archived/non-invalidated records are closed
  - reviewed      — all non-archived/non-invalidated records are reviewed (or closed+reviewed)
  - active        — any record is active and no higher-priority signals
  - planned       — any record is planned and no higher-priority signals
  - archived      — all records are archived
  - unknown       — no records, or only invalidated/unknown statuses, or fallback

Single-record status:
  initial_status override > blocked (HRR blocked or review_status=blocked) >
  needs_review (high-risk unreviewed, or pending/escalated review) >
  closed (terminal outcome) > reviewed (review_status=reviewed) > active

Relationship to Roadmap v4 Phase 4:
  - Continues the Roadmap Phase 4 Memory + Human Feedback mainline.
  - Phase 4M-A (research_memory.py): Research Run Memory Schema.
  - Phase 4M-B (thesis_memory.py): Thesis Memory by Horizon.
  - Phase 4M-C (event_memory.py): Catalyst / News / Earnings Memory.
  - Phase 4M-D (allocation_memory.py): Allocation Decision Memory.
  - Phase 3R-D (option_expression.py): Option Expression Agent v0.1 Non-live.
  - Phase 4A (integration_boundary.py): accepted early infrastructure, not memory mainline.
  - Future subphases: Human Feedback Layer, Agent Evaluation.

See docs/reliability_phase_4m_option_trade_memory.md for design.

Disclaimer: All outputs are for research and educational purposes only.
They do not constitute investment advice. Markets involve risk.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.adapters import make_evidence_id, stable_hash_payload
from lib.reliability.schemas import ToolResult


# ---------------------------------------------------------------------------
# Stable fallback timestamp
# ---------------------------------------------------------------------------

_DETERMINISTIC_TIMESTAMP_DEFAULT: str = "1970-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_OPTION_TRADE_MEMORY_TOOL_NAME: str = "option_trade_memory_report"
_OPTION_TRADE_MEMORY_METRIC_GROUP: str = "option_trade_memory_report"
_CALCULATION_VERSION: str = "option_trade_memory_v1"

# Outcome values that indicate a trade has concluded (position closed / no-trade confirmed).
_TERMINAL_OUTCOMES: frozenset[str] = frozenset({
    "profit",
    "loss",
    "breakeven",
    "expired_worthless",
    "assigned",
    "exercised",
    "no_trade",
    "invalidated",
})


# ---------------------------------------------------------------------------
# Literal type aliases
# ---------------------------------------------------------------------------

OptionTradeMemoryStatus = Literal[
    "unknown",
    "planned",
    "active",
    "reviewed",
    "needs_review",
    "closed",
    "invalidated",
    "archived",
    "blocked",
]

OptionTradeStrategyType = Literal[
    "long_call",
    "long_put",
    "call_debit_spread",
    "put_debit_spread",
    "cash_secured_put",
    "covered_call",
    "stock",
    "no_trade",
    "unknown",
]

OptionTradeDecision = Literal[
    "option",
    "stock",
    "no_trade",
    "wait",
    "unknown",
]

OptionTradeReviewStatus = Literal[
    "not_required",
    "pending",
    "reviewed",
    "escalated",
    "blocked",
    "unknown",
]

OptionTradeOutcome = Literal[
    "unknown",
    "pending",
    "profit",
    "loss",
    "breakeven",
    "expired_worthless",
    "assigned",
    "exercised",
    "invalidated",
    "no_trade",
]

OptionTradeMemoryEventType = Literal[
    "option_plan_recorded",
    "review_requested",
    "review_completed",
    "exit_rule_updated",
    "outcome_observed",
    "pnl_updated",
    "lesson_added",
    "human_feedback_added",
    "archived",
    "unknown",
]

OptionTradeRiskLevel = Literal[
    "low",
    "medium",
    "high",
    "undefined",
    "unknown",
]

OptionTradeMemoryActorType = Literal[
    "system",
    "user",
    "reviewer",
    "agent",
    "unknown",
]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class OptionTradeMemorySourceRef(BaseModel):
    """
    A stable pointer to a source of evidence for an OptionTradePlanMemoryRecord.

    Stores a reference to an upstream artifact, option expression report, trade
    plan, decision packet, or human review without duplicating full content. All
    fields except source_id are optional.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    source_type: str = "unknown"
    artifact_id: Optional[str] = None
    evidence_id: Optional[str] = None
    field_path: Optional[str] = None
    label: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_source_id(self) -> "OptionTradeMemorySourceRef":
        if not self.source_id.strip():
            raise ValueError(
                f"'source_id' must not be whitespace-only; got {self.source_id!r}."
            )
        return self


class OptionTradePlanSnapshot(BaseModel):
    """
    A non-live snapshot of the option expression / option plan at decision time.

    Captures strategy, entry IV, expiration, max loss, exit rule, and related
    metrics that informed the decision. No broker / order / account / execution
    fields. All pct-like IV fields are non-negative floats (e.g. 0.35 = 35% IV).
    Price / loss / gain / cash / ratio fields are non-negative where applicable.
    contracts is a non-negative integer when present.

    no_trade strategy does not require option metrics — all option-specific
    fields are optional.

    This snapshot is a research audit artifact only. No live option-chain API
    calls, no brokerage calls, no execution authorization.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    decision: OptionTradeDecision = "unknown"
    strategy_type: OptionTradeStrategyType = "unknown"
    expiration: Optional[str] = None
    entry_iv: Optional[float] = None
    exit_iv: Optional[float] = None
    entry_underlying_price: Optional[float] = None
    exit_underlying_price: Optional[float] = None
    max_loss: Optional[float] = None
    max_gain: Optional[float] = None
    breakeven: Optional[float] = None
    cash_required: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    contracts: Optional[int] = None
    planned_exit_rule: Optional[str] = None
    actual_exit_reason: Optional[str] = None
    risk_level: OptionTradeRiskLevel = "unknown"
    source_refs: list[OptionTradeMemorySourceRef] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_fields(self) -> "OptionTradePlanSnapshot":
        non_negative_float_fields = [
            "entry_iv",
            "exit_iv",
            "entry_underlying_price",
            "exit_underlying_price",
            "max_loss",
            "max_gain",
            "breakeven",
            "cash_required",
            "risk_reward_ratio",
        ]
        for fn in non_negative_float_fields:
            v = getattr(self, fn)
            if v is not None and v < 0.0:
                raise ValueError(
                    f"'{fn}' must be non-negative when present; got {v!r}."
                )
        if self.contracts is not None and self.contracts < 0:
            raise ValueError(
                f"'contracts' must be non-negative when present; got {self.contracts!r}."
            )
        return self


class OptionTradeMemoryLogEntry(BaseModel):
    """
    A timestamped lifecycle entry in the event log of an OptionTradePlanMemoryRecord.

    Traces option plan recording, review requests, exit rule updates, outcome
    observations, PnL updates, lesson additions, and human feedback. Not an
    execution instruction or order.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: OptionTradeMemoryEventType = "unknown"
    created_at: str = Field(min_length=1)
    actor: OptionTradeMemoryActorType = "system"
    description: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "OptionTradeMemoryLogEntry":
        for fn in ("event_id", "created_at", "description"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class OptionTradePlanMemoryRecord(BaseModel):
    """
    A single option trade plan memory record.

    Captures the decision (option/stock/no_trade/wait), the plan snapshot,
    rationale, review status, outcome, PnL placeholders, and lesson.

    memory_id optionally links to a ResearchRunMemoryRecord (Phase 4M-A).
    thesis_id optionally links to a HorizonThesisMemoryRecord (Phase 4M-B).
    allocation_memory_id optionally links to an AllocationDecisionMemoryRecord (Phase 4M-D).
    option_expression_report_id optionally links to an OptionExpressionReport (Phase 3R-D).
    trade_plan_report_id optionally links to a TradePlanReport (Phase 3R-B).
    decision_packet_id optionally links to a DecisionPacket (Phase 3E).

    pnl_amount and pnl_pct may be signed (negative for losses).

    approved_for_execution is ALWAYS False. This record is a research audit
    artifact only and does not constitute investment advice or authorize any
    form of execution.

    No broker / order / account / execution fields. No live portfolio data.
    No brokerage calls. No file persistence. No option-chain API calls.
    no_trade is a first-class, safe decision — not an error path.
    """

    model_config = ConfigDict(extra="forbid")

    option_trade_memory_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    run_id: Optional[str] = None
    memory_id: Optional[str] = None
    thesis_id: Optional[str] = None
    allocation_memory_id: Optional[str] = None
    option_expression_report_id: Optional[str] = None
    trade_plan_report_id: Optional[str] = None
    decision_packet_id: Optional[str] = None
    status: OptionTradeMemoryStatus = "unknown"
    decision: OptionTradeDecision = "unknown"
    review_status: OptionTradeReviewStatus = "unknown"
    outcome: OptionTradeOutcome = "unknown"
    plan_snapshot: OptionTradePlanSnapshot
    rationale: str = Field(min_length=1)
    review_trigger: Optional[str] = None
    actual_exit_date: Optional[str] = None
    pnl_amount: Optional[float] = None
    pnl_pct: Optional[float] = None
    lesson: Optional[str] = None
    recorded_at: str = Field(min_length=1)
    reviewed_at: Optional[str] = None
    source_refs: list[OptionTradeMemorySourceRef] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    event_log: list[OptionTradeMemoryLogEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "OptionTradePlanMemoryRecord":
        for fn in ("option_trade_memory_id", "target", "rationale", "recorded_at"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "OptionTradePlanMemoryRecord":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-E. "
                "This layer does not authorize execution."
            )
        return self


class OptionTradeMemoryInputBundle(BaseModel):
    """
    Input bundle for building an option trade memory report from accepted artifacts.

    All prior artifact fields are optional (Any) to avoid hard cross-module
    dependencies at import time. Only source_ids, evidence_ids, status
    attributes, and the human_review_report are read by helpers.

    Missing optional artifacts produce warnings, not crashes.
    Does not contain or imply any execution authorization.
    No brokerage / live portfolio / external API / live option-chain data.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    target: str = Field(min_length=1)
    run_id: Optional[str] = None
    memory_id: Optional[str] = None
    thesis_id: Optional[str] = None
    allocation_memory_id: Optional[str] = None
    as_of: Optional[str] = None

    research_run_memory_record: Optional[Any] = None
    thesis_memory_report: Optional[Any] = None
    allocation_memory_report: Optional[Any] = None
    option_expression_report: Optional[Any] = None
    trade_plan_report: Optional[Any] = None
    decision_packet: Optional[Any] = None
    human_review_report: Optional[Any] = None

    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "OptionTradeMemoryInputBundle":
        if not self.target.strip():
            raise ValueError("'target' must not be whitespace-only.")
        return self


class OptionTradeMemorySummary(BaseModel):
    """
    Deterministic summary of an OptionTradeMemoryReport.

    Aggregates counts, decision distribution, strategy distribution, outcome
    statistics, and numeric aggregates across all OptionTradePlanMemoryRecord
    objects. approved_for_execution is always False.
    """

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    status: OptionTradeMemoryStatus = "unknown"
    record_count: int = 0
    decision_counts: dict[str, int] = Field(default_factory=dict)
    strategy_counts: dict[str, int] = Field(default_factory=dict)
    reviewed_count: int = 0
    needs_review_count: int = 0
    blocked_count: int = 0
    closed_count: int = 0
    no_trade_count: int = 0
    high_risk_count: int = 0
    pending_outcome_count: int = 0
    profit_count: int = 0
    loss_count: int = 0
    total_pnl_amount: Optional[float] = None
    avg_pnl_pct: Optional[float] = None
    max_loss_planned: Optional[float] = None
    top_warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "OptionTradeMemorySummary":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-E. "
                "This layer does not authorize execution."
            )
        return self


class OptionTradeMemoryReport(BaseModel):
    """
    Full option trade memory report aggregating all plan memory records for a target.

    Captures option trade decisions with their evidence, source refs, artifact refs,
    and a summary. Does not duplicate full upstream artifact content.

    run_id is optional; derived from input_bundle.run_id when available.

    approved_for_execution is ALWAYS False. This report is a research audit
    artifact only and does not constitute investment advice or authorize any
    form of execution.

    No persistence, database write, vector store, or broker integration is
    introduced by this model. No brokerage / live portfolio data. No live
    option-chain API calls.
    """

    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    run_id: Optional[str] = None
    status: OptionTradeMemoryStatus = "unknown"
    records: list[OptionTradePlanMemoryRecord] = Field(default_factory=list)
    summary: OptionTradeMemorySummary
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    calculation_version: str = _CALCULATION_VERSION
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "OptionTradeMemoryReport":
        for fn in ("report_id", "target", "created_at", "updated_at"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "OptionTradeMemoryReport":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-E. "
                "This layer does not authorize execution."
            )
        return self


# ---------------------------------------------------------------------------
# Helper: deterministic ID generators
# ---------------------------------------------------------------------------

def make_option_trade_memory_record_id(
    target: str,
    decision: str,
    strategy_type: str,
    snapshot_id: str,
    rationale: str,
    review_status: str,
    outcome: str,
    run_id: Optional[str] = None,
    as_of: Optional[str] = None,
) -> str:
    """Return a deterministic stable hash ID for an OptionTradePlanMemoryRecord.

    All key fields that materially distinguish different option trade decisions
    are included: decision, strategy_type, snapshot_id, rationale, review_status,
    and outcome. This ensures two records that share the same target but differ
    in any of these fields receive distinct IDs.
    """
    payload: dict[str, Any] = {
        "target": target,
        "decision": decision,
        "strategy_type": strategy_type,
        "snapshot_id": snapshot_id,
        "rationale": rationale,
        "review_status": review_status,
        "outcome": outcome,
    }
    if run_id:
        payload["run_id"] = run_id
    if as_of:
        payload["as_of"] = as_of
    h = stable_hash_payload(payload, length=16)
    return f"otmem_{h}"


def make_option_trade_memory_log_entry_id(
    option_trade_memory_id: str,
    event_type: str,
    created_at: str,
) -> str:
    """Return a deterministic stable hash ID for an OptionTradeMemoryLogEntry."""
    payload = {
        "option_trade_memory_id": option_trade_memory_id,
        "event_type": event_type,
        "created_at": created_at,
    }
    h = stable_hash_payload(payload, length=12)
    return f"otlog_{h}"


def make_option_trade_memory_report_id(
    target: str,
    as_of: str,
    run_id: Optional[str] = None,
) -> str:
    """Return a deterministic stable hash ID for an OptionTradeMemoryReport."""
    payload: dict[str, Any] = {"target": target, "as_of": as_of}
    if run_id:
        payload["run_id"] = run_id
    h = stable_hash_payload(payload, length=16)
    return f"otmrep_{h}"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _dedup_list(items: list[str]) -> list[str]:
    """Deduplicate a list of strings preserving first-occurrence order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _dedup_source_refs(
    source_refs: list[OptionTradeMemorySourceRef],
) -> list[OptionTradeMemorySourceRef]:
    """Deduplicate OptionTradeMemorySourceRef list by source_id (first wins)."""
    seen: set[str] = set()
    result: list[OptionTradeMemorySourceRef] = []
    for ref in source_refs:
        if ref.source_id not in seen:
            seen.add(ref.source_id)
            result.append(ref)
    return result


def _determine_single_option_trade_record_status(
    risk_level: str,
    review_status: str,
    outcome: str,
    input_bundle: Optional[OptionTradeMemoryInputBundle] = None,
    initial_status: Optional[OptionTradeMemoryStatus] = None,
) -> tuple[OptionTradeMemoryStatus, list[str]]:
    """
    Determine the status for a single OptionTradePlanMemoryRecord.

    Priority:
      initial_status override > blocked (HRR blocked or review_status=blocked) >
      needs_review (high-risk unreviewed, or pending/escalated review) >
      closed (terminal outcome) > reviewed (review_status=reviewed) > active

    Returns (status, warnings).
    initial_status=None means auto-determine.
    """
    warnings: list[str] = []

    if initial_status is not None:
        return initial_status, warnings

    hrr = getattr(input_bundle, "human_review_report", None) if input_bundle else None
    if hrr is not None:
        hr_status = str(getattr(hrr, "status", "unknown"))
        if hr_status == "blocked":
            warnings.append(
                "Human review report is blocked "
                "— option trade memory record status set to blocked."
            )
            return "blocked", warnings

    if review_status == "blocked":
        warnings.append(
            "Review status is blocked "
            "— option trade memory record status set to blocked."
        )
        return "blocked", warnings

    if risk_level == "high" and review_status != "reviewed":
        warnings.append(
            f"High-risk option trade without confirmed review (review_status={review_status!r}) "
            "— record status set to needs_review."
        )
        return "needs_review", warnings

    if review_status in ("pending", "escalated"):
        warnings.append(
            f"Review status is '{review_status}' "
            "— record status set to needs_review."
        )
        return "needs_review", warnings

    if outcome in _TERMINAL_OUTCOMES:
        if review_status == "reviewed":
            return "reviewed", warnings
        return "closed", warnings

    if review_status == "reviewed":
        return "reviewed", warnings

    return "active", warnings


# ---------------------------------------------------------------------------
# Helper: snapshot builder
# ---------------------------------------------------------------------------

def build_option_trade_plan_snapshot(
    target: str,
    decision: OptionTradeDecision = "unknown",
    strategy_type: OptionTradeStrategyType = "unknown",
    expiration: Optional[str] = None,
    entry_iv: Optional[float] = None,
    exit_iv: Optional[float] = None,
    entry_underlying_price: Optional[float] = None,
    exit_underlying_price: Optional[float] = None,
    max_loss: Optional[float] = None,
    max_gain: Optional[float] = None,
    breakeven: Optional[float] = None,
    cash_required: Optional[float] = None,
    risk_reward_ratio: Optional[float] = None,
    contracts: Optional[int] = None,
    planned_exit_rule: Optional[str] = None,
    actual_exit_reason: Optional[str] = None,
    risk_level: OptionTradeRiskLevel = "unknown",
    source_refs: Optional[list[OptionTradeMemorySourceRef]] = None,
    evidence_ids: Optional[list[str]] = None,
    artifact_refs: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
    as_of: Optional[str] = None,
) -> OptionTradePlanSnapshot:
    """
    Build an OptionTradePlanSnapshot from option plan data at decision time.

    Deterministic: same inputs → same snapshot_id.
    Deduplicates source_refs by source_id (first occurrence wins).
    No live data, no brokerage calls, no option-chain API, no execution implication.
    Inputs are never mutated.
    no_trade strategy does not require option metrics.
    """
    _source_refs = _dedup_source_refs(list(source_refs or []))
    _evidence_ids = _dedup_list(list(evidence_ids or []))
    _artifact_refs = _dedup_list([r for r in (artifact_refs or []) if r and r.strip()])

    snapshot_payload: dict[str, Any] = {
        "target": target,
        "decision": decision,
        "strategy_type": strategy_type,
        "expiration": expiration,
        "entry_iv": entry_iv,
        "exit_iv": exit_iv,
        "entry_underlying_price": entry_underlying_price,
        "exit_underlying_price": exit_underlying_price,
        "max_loss": max_loss,
        "max_gain": max_gain,
        "breakeven": breakeven,
        "cash_required": cash_required,
        "risk_reward_ratio": risk_reward_ratio,
        "contracts": contracts,
        "planned_exit_rule": planned_exit_rule,
        "actual_exit_reason": actual_exit_reason,
        "risk_level": risk_level,
        "as_of": as_of or _DETERMINISTIC_TIMESTAMP_DEFAULT,
    }
    h = stable_hash_payload(snapshot_payload, length=12)
    snapshot_id = f"otsnap_{h}"

    return OptionTradePlanSnapshot(
        snapshot_id=snapshot_id,
        target=target,
        decision=decision,
        strategy_type=strategy_type,
        expiration=expiration,
        entry_iv=entry_iv,
        exit_iv=exit_iv,
        entry_underlying_price=entry_underlying_price,
        exit_underlying_price=exit_underlying_price,
        max_loss=max_loss,
        max_gain=max_gain,
        breakeven=breakeven,
        cash_required=cash_required,
        risk_reward_ratio=risk_reward_ratio,
        contracts=contracts,
        planned_exit_rule=planned_exit_rule,
        actual_exit_reason=actual_exit_reason,
        risk_level=risk_level,
        source_refs=_source_refs,
        evidence_ids=_evidence_ids,
        artifact_refs=_artifact_refs,
        warnings=list(warnings or []),
    )


# ---------------------------------------------------------------------------
# Helper: log entry builder
# ---------------------------------------------------------------------------

def build_option_trade_memory_log_entry(
    event_type: OptionTradeMemoryEventType,
    description: str,
    option_trade_memory_id: str,
    created_at: Optional[str] = None,
    actor: OptionTradeMemoryActorType = "system",
    source_ids: Optional[list[str]] = None,
    evidence_ids: Optional[list[str]] = None,
    metadata: Optional[dict[str, Any]] = None,
    warnings: Optional[list[str]] = None,
) -> OptionTradeMemoryLogEntry:
    """Build a single OptionTradeMemoryLogEntry with a deterministic event_id."""
    ts = created_at or _DETERMINISTIC_TIMESTAMP_DEFAULT
    entry_id = make_option_trade_memory_log_entry_id(
        option_trade_memory_id=option_trade_memory_id,
        event_type=event_type,
        created_at=ts,
    )
    return OptionTradeMemoryLogEntry(
        event_id=entry_id,
        event_type=event_type,
        created_at=ts,
        actor=actor,
        description=description,
        source_ids=list(source_ids or []),
        evidence_ids=list(evidence_ids or []),
        metadata=dict(metadata or {}),
        warnings=list(warnings or []),
    )


# ---------------------------------------------------------------------------
# Helper: report-level status determination
# ---------------------------------------------------------------------------

def determine_option_trade_memory_status(
    records: list[OptionTradePlanMemoryRecord],
    input_bundle: Optional[OptionTradeMemoryInputBundle] = None,
) -> tuple[OptionTradeMemoryStatus, list[str]]:
    """
    Determine the overall OptionTradeMemoryStatus for an OptionTradeMemoryReport.

    Precedence: blocked > needs_review > closed > reviewed > active > planned > archived > unknown

    - blocked:      HRR blocked in input_bundle, OR any record has status=blocked.
    - needs_review: any record is needs_review, OR any high-risk unreviewed record.
    - closed:       all non-archived/non-invalidated records are closed.
    - reviewed:     all non-archived/non-invalidated records are reviewed (or closed+reviewed).
    - active:       any record is active and no higher-priority signals.
    - planned:      any record is planned and no higher-priority signals.
    - archived:     all records are archived.
    - unknown:      no records, or all invalidated/unknown statuses, or fallback.

    Returns (status, warnings). Inputs are never mutated.
    """
    warnings: list[str] = []

    hrr = getattr(input_bundle, "human_review_report", None) if input_bundle else None
    if hrr is not None:
        hr_status = str(getattr(hrr, "status", "unknown"))
        if hr_status == "blocked":
            warnings.append(
                "Human review report is blocked "
                "— option trade memory report status set to blocked."
            )
            return "blocked", warnings

    if not records:
        warnings.append("No option trade memory records provided — report status is unknown.")
        return "unknown", warnings

    statuses = [r.status for r in records]

    if "blocked" in statuses:
        n = statuses.count("blocked")
        warnings.append(f"{n} option trade memory record(s) are blocked.")
        return "blocked", warnings

    if "needs_review" in statuses:
        n = statuses.count("needs_review")
        warnings.append(f"{n} option trade memory record(s) require review.")
        return "needs_review", warnings

    # High-risk unreviewed records escalate to needs_review
    high_risk_unreviewed = [
        r for r in records
        if r.plan_snapshot.risk_level == "high"
        and r.status not in ("reviewed", "archived", "invalidated", "closed")
    ]
    if high_risk_unreviewed:
        warnings.append(
            f"{len(high_risk_unreviewed)} high-risk option trade(s) are not yet reviewed."
        )
        return "needs_review", warnings

    non_terminal = [
        s for s in statuses if s not in ("archived", "invalidated", "unknown")
    ]

    if not non_terminal:
        if all(s == "archived" for s in statuses):
            return "archived", warnings
        return "unknown", warnings

    if all(s == "closed" for s in non_terminal):
        return "closed", warnings

    if all(s in ("reviewed", "closed") for s in non_terminal):
        return "reviewed", warnings

    if any(s == "active" for s in non_terminal):
        return "active", warnings

    if any(s == "planned" for s in non_terminal):
        return "planned", warnings

    return "unknown", warnings


# ---------------------------------------------------------------------------
# Helper: ID / ref collection
# ---------------------------------------------------------------------------

def collect_option_trade_memory_source_ids(
    input_bundle: OptionTradeMemoryInputBundle,
    records: Optional[list[OptionTradePlanMemoryRecord]] = None,
) -> list[str]:
    """
    Collect and deduplicate source IDs from input_bundle, records, and upstream artifacts.

    Deduplication preserves first-occurrence order.
    """
    seen: set[str] = set()
    result: list[str] = []

    def _add(sid: str) -> None:
        if sid and sid not in seen:
            seen.add(sid)
            result.append(sid)

    for sid in input_bundle.source_ids:
        _add(sid)

    _artifact_attrs = [
        "research_run_memory_record",
        "thesis_memory_report",
        "allocation_memory_report",
        "option_expression_report",
        "trade_plan_report",
        "decision_packet",
        "human_review_report",
    ]
    for attr_name in _artifact_attrs:
        artifact = getattr(input_bundle, attr_name, None)
        if artifact is None:
            continue
        artifact_source_ids = getattr(artifact, "source_ids", []) or []
        for sid in artifact_source_ids:
            _add(str(sid))
        artifact_id = (
            getattr(artifact, "report_id", None)
            or getattr(artifact, "result_id", None)
            or getattr(artifact, "packet_id", None)
            or getattr(artifact, "memory_id", None)
        )
        if artifact_id:
            _add(str(artifact_id))

    if records:
        for record in records:
            for ref in record.source_refs:
                _add(ref.source_id)
            for ref in record.plan_snapshot.source_refs:
                _add(ref.source_id)

    return result


def collect_option_trade_memory_evidence_ids(
    input_bundle: OptionTradeMemoryInputBundle,
    records: Optional[list[OptionTradePlanMemoryRecord]] = None,
) -> list[str]:
    """
    Collect and deduplicate evidence IDs from input_bundle, records, and source refs.

    Deduplication preserves first-occurrence order.
    """
    seen: set[str] = set()
    result: list[str] = []

    def _add(eid: str) -> None:
        if eid and eid not in seen:
            seen.add(eid)
            result.append(eid)

    for eid in input_bundle.evidence_ids:
        _add(eid)

    # Collect evidence_id / evidence_ids from upstream duck-typed artifacts.
    # Defensive: missing attributes produce no crash; unknown shapes are skipped.
    _artifact_attrs = [
        "research_run_memory_record",
        "thesis_memory_report",
        "allocation_memory_report",
        "option_expression_report",
        "trade_plan_report",
        "decision_packet",
        "human_review_report",
    ]
    for attr_name in _artifact_attrs:
        artifact = getattr(input_bundle, attr_name, None)
        if artifact is None:
            continue
        artifact_evidence_ids = getattr(artifact, "evidence_ids", None) or []
        for eid in artifact_evidence_ids:
            if eid:
                _add(str(eid))
        artifact_evidence_id = getattr(artifact, "evidence_id", None)
        if artifact_evidence_id:
            _add(str(artifact_evidence_id))

    if records:
        for record in records:
            for eid in record.evidence_ids:
                _add(eid)
            for ref in record.source_refs:
                if ref.evidence_id:
                    _add(ref.evidence_id)
            for eid in record.plan_snapshot.evidence_ids:
                _add(eid)
            for ref in record.plan_snapshot.source_refs:
                if ref.evidence_id:
                    _add(ref.evidence_id)

    return result


def collect_option_trade_memory_artifact_refs(
    input_bundle: OptionTradeMemoryInputBundle,
    records: Optional[list[OptionTradePlanMemoryRecord]] = None,
) -> list[str]:
    """
    Collect and deduplicate artifact refs from input_bundle and records.

    Empty / whitespace-only refs are filtered. Deduplication preserves
    first-occurrence order.
    """
    seen: set[str] = set()
    result: list[str] = []

    def _add(ref: str) -> None:
        if ref and ref.strip() and ref not in seen:
            seen.add(ref)
            result.append(ref)

    for ref in input_bundle.artifact_refs:
        _add(ref)

    if records:
        for record in records:
            for ref in record.artifact_refs:
                _add(ref)
            for ref in record.plan_snapshot.artifact_refs:
                _add(ref)

    return result


# ---------------------------------------------------------------------------
# Helper: summary builder
# ---------------------------------------------------------------------------

def summarize_option_trade_memory(
    target: str,
    status: OptionTradeMemoryStatus,
    records: list[OptionTradePlanMemoryRecord],
    warnings: list[str],
) -> OptionTradeMemorySummary:
    """Build an OptionTradeMemorySummary from resolved option trade memory components."""
    record_count = len(records)

    decision_counts: dict[str, int] = {}
    strategy_counts: dict[str, int] = {}
    for r in records:
        decision_counts[r.decision] = decision_counts.get(r.decision, 0) + 1
        strategy_counts[r.plan_snapshot.strategy_type] = (
            strategy_counts.get(r.plan_snapshot.strategy_type, 0) + 1
        )

    reviewed_count = sum(1 for r in records if r.status == "reviewed")
    needs_review_count = sum(1 for r in records if r.status == "needs_review")
    blocked_count = sum(1 for r in records if r.status == "blocked")
    closed_count = sum(1 for r in records if r.status == "closed")
    no_trade_count = sum(
        1 for r in records if r.decision == "no_trade" or r.outcome == "no_trade"
    )
    high_risk_count = sum(
        1 for r in records if r.plan_snapshot.risk_level == "high"
    )
    pending_outcome_count = sum(1 for r in records if r.outcome == "pending")
    profit_count = sum(1 for r in records if r.outcome == "profit")
    loss_count = sum(1 for r in records if r.outcome == "loss")

    pnl_amounts = [r.pnl_amount for r in records if r.pnl_amount is not None]
    total_pnl_amount: Optional[float] = (
        round(sum(pnl_amounts), 10) if pnl_amounts else None
    )

    pnl_pcts = [r.pnl_pct for r in records if r.pnl_pct is not None]
    avg_pnl_pct: Optional[float] = (
        round(sum(pnl_pcts) / len(pnl_pcts), 10) if pnl_pcts else None
    )

    max_losses = [
        r.plan_snapshot.max_loss
        for r in records
        if r.plan_snapshot.max_loss is not None
    ]
    max_loss_planned: Optional[float] = max(max_losses) if max_losses else None

    top_warnings = warnings[:5]

    return OptionTradeMemorySummary(
        target=target,
        status=status,
        record_count=record_count,
        decision_counts=decision_counts,
        strategy_counts=strategy_counts,
        reviewed_count=reviewed_count,
        needs_review_count=needs_review_count,
        blocked_count=blocked_count,
        closed_count=closed_count,
        no_trade_count=no_trade_count,
        high_risk_count=high_risk_count,
        pending_outcome_count=pending_outcome_count,
        profit_count=profit_count,
        loss_count=loss_count,
        total_pnl_amount=total_pnl_amount,
        avg_pnl_pct=avg_pnl_pct,
        max_loss_planned=max_loss_planned,
        top_warnings=top_warnings,
        approved_for_execution=False,
    )


# ---------------------------------------------------------------------------
# Main builders
# ---------------------------------------------------------------------------

def build_option_trade_memory_record(
    target: str,
    decision: OptionTradeDecision,
    rationale: str,
    plan_snapshot: Optional[OptionTradePlanSnapshot] = None,
    review_status: OptionTradeReviewStatus = "unknown",
    outcome: OptionTradeOutcome = "unknown",
    pnl_amount: Optional[float] = None,
    pnl_pct: Optional[float] = None,
    lesson: Optional[str] = None,
    review_trigger: Optional[str] = None,
    actual_exit_date: Optional[str] = None,
    run_id: Optional[str] = None,
    memory_id: Optional[str] = None,
    thesis_id: Optional[str] = None,
    allocation_memory_id: Optional[str] = None,
    option_expression_report_id: Optional[str] = None,
    trade_plan_report_id: Optional[str] = None,
    decision_packet_id: Optional[str] = None,
    source_refs: Optional[list[OptionTradeMemorySourceRef]] = None,
    evidence_ids: Optional[list[str]] = None,
    artifact_refs: Optional[list[str]] = None,
    recorded_at: Optional[str] = None,
    initial_status: Optional[OptionTradeMemoryStatus] = None,
    input_bundle: Optional[OptionTradeMemoryInputBundle] = None,
    extra_warnings: Optional[list[str]] = None,
) -> OptionTradePlanMemoryRecord:
    """
    Build an OptionTradePlanMemoryRecord for a single option trade decision.

    Timestamp resolution priority (highest wins):
      1. explicit recorded_at argument;
      2. input_bundle.as_of if present;
      3. _DETERMINISTIC_TIMESTAMP_DEFAULT ("1970-01-01T00:00:00Z").

    Identical inputs without explicit timestamps always produce identical output.
    Inputs are never mutated.
    approved_for_execution is always False.
    Missing optional upstream artifacts produce warnings, not crashes.
    initial_status overrides auto-determined status when provided.

    If plan_snapshot is not provided, an empty snapshot is generated
    with a warning.
    no_trade is a first-class decision — not an error path.
    pnl_amount and pnl_pct may be signed (negative for losses).
    """
    ts = (
        recorded_at
        or (input_bundle.as_of if input_bundle else None)
        or _DETERMINISTIC_TIMESTAMP_DEFAULT
    )

    as_of = (input_bundle.as_of if input_bundle else None) or ts
    effective_run_id = run_id or (input_bundle.run_id if input_bundle else None)
    effective_memory_id = memory_id or (input_bundle.memory_id if input_bundle else None)
    effective_thesis_id = thesis_id or (input_bundle.thesis_id if input_bundle else None)
    effective_alloc_mid = allocation_memory_id or (
        input_bundle.allocation_memory_id if input_bundle else None
    )

    # Build or use plan_snapshot FIRST — snapshot_id is needed for the
    # content-sensitive record ID.
    extra_snap_warnings: list[str] = []
    if plan_snapshot is None:
        extra_snap_warnings.append(
            "No plan_snapshot provided — using empty snapshot with no option plan data."
        )
        plan_snapshot = build_option_trade_plan_snapshot(
            target=target,
            decision=decision,
            as_of=as_of,
        )

    strategy_type = plan_snapshot.strategy_type

    option_trade_memory_id = make_option_trade_memory_record_id(
        target=target,
        decision=decision,
        strategy_type=strategy_type,
        snapshot_id=plan_snapshot.snapshot_id,
        rationale=rationale,
        review_status=review_status,
        outcome=outcome,
        run_id=effective_run_id,
        as_of=as_of,
    )

    # Deduplicate source_refs by source_id (first occurrence wins)
    _seen_sids: set[str] = set()
    _source_refs: list[OptionTradeMemorySourceRef] = []
    for _sr in (source_refs or []):
        if _sr.source_id not in _seen_sids:
            _seen_sids.add(_sr.source_id)
            _source_refs.append(_sr)

    _evidence_ids = _dedup_list(list(evidence_ids or []))
    _artifact_refs = _dedup_list([r for r in (artifact_refs or []) if r and r.strip()])

    risk_level = plan_snapshot.risk_level
    status, status_warnings = _determine_single_option_trade_record_status(
        risk_level=risk_level,
        review_status=review_status,
        outcome=outcome,
        input_bundle=input_bundle,
        initial_status=initial_status,
    )

    bundle_warnings = list(input_bundle.warnings if input_bundle else [])

    missing_warnings: list[str] = []
    if input_bundle is not None:
        if input_bundle.option_expression_report is None:
            missing_warnings.append(
                "Missing optional upstream artifact: option_expression_report."
            )
        if input_bundle.trade_plan_report is None:
            missing_warnings.append(
                "Missing optional upstream artifact: trade_plan_report."
            )
        if input_bundle.decision_packet is None:
            missing_warnings.append(
                "Missing optional upstream artifact: decision_packet."
            )

    all_warnings = (
        bundle_warnings
        + status_warnings
        + extra_snap_warnings
        + missing_warnings
        + list(extra_warnings or [])
    )

    # Build event log
    creation_entry = build_option_trade_memory_log_entry(
        event_type="option_plan_recorded",
        description=(
            f"Option trade memory record created for target '{target}' "
            f"(decision={decision!r}, strategy_type={strategy_type!r}, "
            f"risk_level={risk_level!r}, status={status!r}, outcome={outcome!r})."
        ),
        option_trade_memory_id=option_trade_memory_id,
        created_at=ts,
        actor="system",
        source_ids=[ref.source_id for ref in _source_refs],
        evidence_ids=_evidence_ids,
        metadata={"target": target, "decision": decision, "strategy_type": strategy_type},
    )
    event_log = [creation_entry]

    if status in ("blocked", "needs_review"):
        review_entry = build_option_trade_memory_log_entry(
            event_type="review_requested",
            description=(
                f"Option trade plan record requires review — status is '{status}'."
            ),
            option_trade_memory_id=option_trade_memory_id,
            created_at=ts,
            actor="system",
        )
        event_log.append(review_entry)

    if lesson:
        lesson_entry = build_option_trade_memory_log_entry(
            event_type="lesson_added",
            description=f"Lesson recorded: {lesson}",
            option_trade_memory_id=option_trade_memory_id,
            created_at=ts,
            actor="system",
            metadata={"lesson": lesson},
        )
        event_log.append(lesson_entry)

    if outcome in _TERMINAL_OUTCOMES and outcome not in ("unknown", "pending"):
        outcome_entry = build_option_trade_memory_log_entry(
            event_type="outcome_observed",
            description=(
                f"Option trade outcome observed: {outcome!r}. "
                f"pnl_amount={pnl_amount!r}, pnl_pct={pnl_pct!r}."
            ),
            option_trade_memory_id=option_trade_memory_id,
            created_at=ts,
            actor="system",
            metadata={"outcome": outcome},
        )
        event_log.append(outcome_entry)

    if pnl_amount is not None or pnl_pct is not None:
        pnl_entry = build_option_trade_memory_log_entry(
            event_type="pnl_updated",
            description=(
                f"PnL recorded: pnl_amount={pnl_amount!r}, pnl_pct={pnl_pct!r}."
            ),
            option_trade_memory_id=option_trade_memory_id,
            created_at=ts,
            actor="system",
            metadata={"pnl_amount": pnl_amount, "pnl_pct": pnl_pct},
        )
        event_log.append(pnl_entry)

    return OptionTradePlanMemoryRecord(
        option_trade_memory_id=option_trade_memory_id,
        target=target,
        run_id=effective_run_id,
        memory_id=effective_memory_id,
        thesis_id=effective_thesis_id,
        allocation_memory_id=effective_alloc_mid,
        option_expression_report_id=option_expression_report_id,
        trade_plan_report_id=trade_plan_report_id,
        decision_packet_id=decision_packet_id,
        status=status,
        decision=decision,
        review_status=review_status,
        outcome=outcome,
        plan_snapshot=plan_snapshot,
        rationale=rationale,
        review_trigger=review_trigger,
        actual_exit_date=actual_exit_date,
        pnl_amount=pnl_amount,
        pnl_pct=pnl_pct,
        lesson=lesson,
        recorded_at=ts,
        source_refs=_source_refs,
        evidence_ids=_evidence_ids,
        artifact_refs=_artifact_refs,
        event_log=event_log,
        warnings=all_warnings,
        approved_for_execution=False,
    )


def build_option_trade_memory_report(
    input_bundle: OptionTradeMemoryInputBundle,
    records: Optional[list[OptionTradePlanMemoryRecord]] = None,
    created_at: Optional[str] = None,
    updated_at: Optional[str] = None,
) -> OptionTradeMemoryReport:
    """
    Build an OptionTradeMemoryReport from an input bundle and a list of records.

    Timestamp resolution priority (highest wins):
      1. explicit created_at argument;
      2. input_bundle.as_of if present;
      3. _DETERMINISTIC_TIMESTAMP_DEFAULT ("1970-01-01T00:00:00Z").

    If only created_at is resolved, updated_at defaults to created_at.
    Identical inputs without explicit timestamps always produce identical output.
    Inputs are never mutated.
    approved_for_execution is always False.

    An empty record list produces a report with status unknown and a warning.
    Missing optional artifacts produce warnings, not crashes.
    """
    ts = (
        created_at
        or input_bundle.as_of
        or _DETERMINISTIC_TIMESTAMP_DEFAULT
    )
    updated = updated_at or ts

    as_of = input_bundle.as_of or ts
    run_id = input_bundle.run_id

    report_id = make_option_trade_memory_report_id(
        target=input_bundle.target,
        as_of=as_of,
        run_id=run_id,
    )

    _records = list(records or [])

    status, status_warnings = determine_option_trade_memory_status(
        records=_records,
        input_bundle=input_bundle,
    )

    missing_warnings: list[str] = []
    if input_bundle.option_expression_report is None:
        missing_warnings.append(
            "Missing optional upstream artifact: option_expression_report."
        )
    if input_bundle.trade_plan_report is None:
        missing_warnings.append(
            "Missing optional upstream artifact: trade_plan_report."
        )
    if input_bundle.decision_packet is None:
        missing_warnings.append(
            "Missing optional upstream artifact: decision_packet."
        )
    if input_bundle.human_review_report is None:
        missing_warnings.append(
            "Missing optional upstream artifact: human_review_report."
        )

    all_warnings = list(input_bundle.warnings) + status_warnings + missing_warnings

    source_ids = collect_option_trade_memory_source_ids(input_bundle, _records)
    evidence_ids = collect_option_trade_memory_evidence_ids(input_bundle, _records)
    artifact_refs = collect_option_trade_memory_artifact_refs(input_bundle, _records)

    summary = summarize_option_trade_memory(
        target=input_bundle.target,
        status=status,
        records=_records,
        warnings=all_warnings,
    )

    return OptionTradeMemoryReport(
        report_id=report_id,
        target=input_bundle.target,
        run_id=run_id,
        status=status,
        records=_records,
        summary=summary,
        source_ids=source_ids,
        evidence_ids=evidence_ids,
        artifact_refs=artifact_refs,
        warnings=all_warnings,
        created_at=ts,
        updated_at=updated,
        calculation_version=_CALCULATION_VERSION,
        approved_for_execution=False,
    )


# ---------------------------------------------------------------------------
# ToolResult adapter
# ---------------------------------------------------------------------------

def option_trade_memory_tool_result_from_report(
    report: OptionTradeMemoryReport,
    run_id: Optional[str] = None,
) -> ToolResult:
    """
    Wrap an OptionTradeMemoryReport as a ToolResult for evidence-store integration.

    Stable tool name: "option_trade_memory_report".
    Deterministic evidence_id derived from report content (including full records,
    event logs, source_refs, evidence_ids, and warnings).
    No fake evidence; no execution implication; no persistence side effect.
    This adapter does NOT look like an order ticket or persistence receipt.
    """
    _run_id = run_id or report.run_id or report.target

    outputs = {
        "report_id": report.report_id,
        "target": report.target,
        "status": report.status,
        "report": report.model_dump(),
        "summary": report.summary.model_dump(),
        "record_count": report.summary.record_count,
        "reviewed_count": report.summary.reviewed_count,
        "needs_review_count": report.summary.needs_review_count,
        "blocked_count": report.summary.blocked_count,
        "closed_count": report.summary.closed_count,
        "no_trade_count": report.summary.no_trade_count,
        "calculation_version": report.calculation_version,
        "approved_for_execution": False,
    }

    evidence_id = make_evidence_id(
        run_id=_run_id,
        tool_name=_OPTION_TRADE_MEMORY_TOOL_NAME,
        target=report.target,
        metric_group=_OPTION_TRADE_MEMORY_METRIC_GROUP,
        payload=outputs,
    )

    return ToolResult(
        tool_name=_OPTION_TRADE_MEMORY_TOOL_NAME,
        run_id=_run_id,
        ticker=report.target if report.target else None,
        evidence_id=evidence_id,
        inputs={"target": report.target, "report_id": report.report_id},
        outputs=outputs,
        description=(
            f"OptionTradeMemoryReport for {report.target} "
            f"(report_id={report.report_id!r}, status={report.status!r}, "
            f"records={report.summary.record_count}, "
            f"reviewed={report.summary.reviewed_count}, "
            f"needs_review={report.summary.needs_review_count}, "
            f"closed={report.summary.closed_count})."
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Literal type aliases
    "OptionTradeDecision",
    "OptionTradeMemoryActorType",
    "OptionTradeMemoryEventType",
    "OptionTradeMemoryStatus",
    "OptionTradeOutcome",
    "OptionTradeReviewStatus",
    "OptionTradeRiskLevel",
    "OptionTradeStrategyType",
    # Models
    "OptionTradeMemoryInputBundle",
    "OptionTradeMemoryLogEntry",
    "OptionTradeMemoryReport",
    "OptionTradeMemorySourceRef",
    "OptionTradeMemorySummary",
    "OptionTradePlanMemoryRecord",
    "OptionTradePlanSnapshot",
    # Helpers
    "build_option_trade_memory_log_entry",
    "build_option_trade_memory_record",
    "build_option_trade_memory_report",
    "build_option_trade_plan_snapshot",
    "collect_option_trade_memory_artifact_refs",
    "collect_option_trade_memory_evidence_ids",
    "collect_option_trade_memory_source_ids",
    "determine_option_trade_memory_status",
    "make_option_trade_memory_log_entry_id",
    "make_option_trade_memory_record_id",
    "make_option_trade_memory_report_id",
    "option_trade_memory_tool_result_from_report",
    "summarize_option_trade_memory",
]
