"""
lib/reliability/allocation_memory.py

Phase 4M-D: Allocation Decision Memory.

Design principles:
  - Standalone, deterministic, offline/mock-only.
  - No live LLM calls, no live data fetching, no app integration.
  - No database writes, no file persistence, no vector store.
  - No broker / order / execution behavior.
  - No pathway that can set approved_for_execution = True.
  - Defines memory records and helper functions only.
  - Records allocation decisions with target/actual allocation, risk budget,
    cash impact, forward return, drawdown, and lessons learned.
  - Consumes typed research artifacts from prior phases via source IDs /
    evidence IDs without duplicating full upstream artifact content.
  - Missing optional prior artifacts produce warnings, not crashes.
  - Does NOT import from app.py, pages/*, lib/llm_orchestrator.py, or any
    live workflow module.
  - Does NOT produce investment advice, buy/sell recommendations, or
    individual security recommendations.
  - approved_for_execution is ALWAYS False. No pathway to set it True exists.
  - No brokerage / live portfolio / external API calls.
  - No broker / order / account / execution identifiers.

Report-level status precedence:
  blocked > needs_review > reviewed > active > archived > unknown

  - blocked       — human review blocked in input_bundle, OR any record is blocked
  - needs_review  — any record has status=needs_review, OR any high-risk unreviewed record
  - reviewed      — all non-archived/non-invalidated records are reviewed
  - active        — clean active records with no review signals
  - archived      — all records are archived
  - unknown       — no records, only invalidated/unknown statuses, or fallback

Single-record status:
  initial_status override > blocked (HRR or review_status=blocked) >
  needs_review (high-risk unreviewed, or pending/escalated review) > reviewed > active

Relationship to Roadmap v4 Phase 4:
  - Continues the Roadmap Phase 4 Memory + Human Feedback mainline.
  - Phase 4M-A (research_memory.py): Research Run Memory Schema.
  - Phase 4M-B (thesis_memory.py): Thesis Memory by Horizon.
  - Phase 4M-C (event_memory.py): Catalyst / News / Earnings Memory.
  - Phase 3R-C (allocation_report.py): Allocation Agent v0.1 Non-live.
  - Phase 4A (integration_boundary.py): accepted early infrastructure, not memory mainline.
  - Future subphases: Option Trade Plan Memory, Human Feedback Layer, Agent Evaluation.

See docs/reliability_phase_4m_allocation_memory.md for design.

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

_ALLOCATION_MEMORY_TOOL_NAME: str = "allocation_memory_report"
_ALLOCATION_MEMORY_METRIC_GROUP: str = "allocation_memory_report"
_CALCULATION_VERSION: str = "allocation_memory_v1"


# ---------------------------------------------------------------------------
# Literal type aliases
# ---------------------------------------------------------------------------

AllocationMemoryStatus = Literal[
    "unknown",
    "active",
    "reviewed",
    "needs_review",
    "invalidated",
    "archived",
    "blocked",
]

AllocationDecisionAction = Literal[
    "hold",
    "add",
    "trim",
    "exit",
    "no_action",
    "unknown",
]

AllocationDecisionReviewStatus = Literal[
    "not_required",
    "pending",
    "reviewed",
    "escalated",
    "blocked",
    "unknown",
]

AllocationDecisionOutcome = Literal[
    "unknown",
    "pending",
    "positive",
    "negative",
    "neutral",
    "mixed",
    "invalidated",
]

AllocationMemoryEventType = Literal[
    "allocation_recorded",
    "allocation_review_requested",
    "allocation_review_completed",
    "target_updated",
    "risk_budget_updated",
    "outcome_observed",
    "lesson_added",
    "human_feedback_added",
    "archived",
    "unknown",
]

AllocationMemoryRiskLevel = Literal[
    "low",
    "medium",
    "high",
    "unknown",
]

AllocationMemoryActorType = Literal[
    "system",
    "user",
    "reviewer",
    "agent",
    "unknown",
]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class AllocationMemorySourceRef(BaseModel):
    """
    A stable pointer to a source of evidence for an AllocationDecisionMemoryRecord.

    Stores a reference to an upstream artifact, allocation report, trade plan,
    decision packet, or human review without duplicating full content. All fields
    except source_id are optional.
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
    def _check_source_id(self) -> "AllocationMemorySourceRef":
        if not self.source_id.strip():
            raise ValueError(
                f"'source_id' must not be whitespace-only; got {self.source_id!r}."
            )
        return self


class AllocationDecisionSnapshot(BaseModel):
    """
    A non-live snapshot of target/actual allocation at decision time.

    Captures the allocation numbers and risk budget that informed the decision.
    No broker / order / account / execution fields. All pct fields are bounded
    [0, 1] except loss/risk fields which are non-negative. Trade value and
    shares fields may be signed (positive = add, negative = trim).

    This snapshot is a research audit artifact only. No live portfolio data,
    brokerage calls, or execution authorization.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    target_allocation_pct: Optional[float] = None
    actual_allocation_pct: Optional[float] = None
    min_allocation_pct: Optional[float] = None
    max_allocation_pct: Optional[float] = None
    cash_pct: Optional[float] = None
    required_trade_value: Optional[float] = None
    required_shares: Optional[float] = None
    cash_impact: Optional[float] = None
    projected_cash_pct: Optional[float] = None
    portfolio_loss_pct: Optional[float] = None
    risk_budget_pct: Optional[float] = None
    risk_level: AllocationMemoryRiskLevel = "unknown"
    source_refs: list[AllocationMemorySourceRef] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_fields(self) -> "AllocationDecisionSnapshot":
        bounded_pct_fields = [
            "target_allocation_pct",
            "actual_allocation_pct",
            "min_allocation_pct",
            "max_allocation_pct",
            "cash_pct",
            "projected_cash_pct",
        ]
        non_negative_pct_fields = [
            "portfolio_loss_pct",
            "risk_budget_pct",
        ]
        for fn in bounded_pct_fields:
            v = getattr(self, fn)
            if v is not None and not (0.0 <= v <= 1.0):
                raise ValueError(
                    f"'{fn}' must be between 0 and 1 when present; got {v!r}."
                )
        for fn in non_negative_pct_fields:
            v = getattr(self, fn)
            if v is not None and v < 0.0:
                raise ValueError(
                    f"'{fn}' must be non-negative when present; got {v!r}."
                )
        return self


class AllocationMemoryLogEntry(BaseModel):
    """
    A timestamped lifecycle entry in the event log of an AllocationDecisionMemoryRecord.

    Traces allocation recording, review requests, review completions, target
    updates, risk budget updates, outcome observations, lesson additions, and
    human feedback. Not an execution instruction or order.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: AllocationMemoryEventType = "unknown"
    created_at: str = Field(min_length=1)
    actor: AllocationMemoryActorType = "system"
    description: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "AllocationMemoryLogEntry":
        for fn in ("event_id", "created_at", "description"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class AllocationDecisionMemoryRecord(BaseModel):
    """
    A single allocation decision memory record.

    Captures the action taken (hold/add/trim/exit), the decision snapshot,
    rationale, review status, outcome, forward return, drawdown, and lesson.

    memory_id optionally links to a ResearchRunMemoryRecord (Phase 4M-A).
    thesis_id optionally links to a HorizonThesisMemoryRecord (Phase 4M-B).
    allocation_report_id optionally links to an AllocationReport (Phase 3R-C).
    trade_plan_report_id optionally links to a TradePlanReport (Phase 3R-B).
    decision_packet_id optionally links to a DecisionPacket (Phase 3E).

    approved_for_execution is ALWAYS False. This record is a research audit
    artifact only and does not constitute investment advice or authorize any
    form of execution.

    No broker / order / account / execution fields. No live portfolio data.
    No brokerage calls. No file persistence.
    """

    model_config = ConfigDict(extra="forbid")

    allocation_memory_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    run_id: Optional[str] = None
    memory_id: Optional[str] = None
    thesis_id: Optional[str] = None
    allocation_report_id: Optional[str] = None
    trade_plan_report_id: Optional[str] = None
    decision_packet_id: Optional[str] = None
    action: AllocationDecisionAction = "unknown"
    status: AllocationMemoryStatus = "unknown"
    review_status: AllocationDecisionReviewStatus = "unknown"
    outcome: AllocationDecisionOutcome = "unknown"
    decision_snapshot: AllocationDecisionSnapshot
    rationale: str = Field(min_length=1)
    review_trigger: Optional[str] = None
    forward_return_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    lesson: Optional[str] = None
    recorded_at: str = Field(min_length=1)
    reviewed_at: Optional[str] = None
    source_refs: list[AllocationMemorySourceRef] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    event_log: list[AllocationMemoryLogEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "AllocationDecisionMemoryRecord":
        for fn in ("allocation_memory_id", "target", "rationale", "recorded_at"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _validate_numeric_fields(self) -> "AllocationDecisionMemoryRecord":
        if self.max_drawdown_pct is not None and self.max_drawdown_pct < 0.0:
            raise ValueError(
                f"'max_drawdown_pct' must be non-negative when present; got {self.max_drawdown_pct!r}."
            )
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "AllocationDecisionMemoryRecord":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-D. "
                "This layer does not authorize execution."
            )
        return self


class AllocationMemoryInputBundle(BaseModel):
    """
    Input bundle for building an allocation memory report from accepted artifacts.

    All prior artifact fields are optional (Any) to avoid hard cross-module
    dependencies at import time. Only source_ids, evidence_ids, status
    attributes, and the human_review_report are read by helpers.

    Missing optional artifacts produce warnings, not crashes.
    Does not contain or imply any execution authorization.
    No brokerage / live portfolio / external API data.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    target: str = Field(min_length=1)
    run_id: Optional[str] = None
    memory_id: Optional[str] = None
    thesis_id: Optional[str] = None
    as_of: Optional[str] = None

    research_run_memory_record: Optional[Any] = None
    thesis_memory_report: Optional[Any] = None
    allocation_report: Optional[Any] = None
    trade_plan_report: Optional[Any] = None
    decision_packet: Optional[Any] = None
    human_review_report: Optional[Any] = None

    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "AllocationMemoryInputBundle":
        if not self.target.strip():
            raise ValueError("'target' must not be whitespace-only.")
        return self


class AllocationMemorySummary(BaseModel):
    """
    Deterministic summary of an AllocationMemoryReport.

    Aggregates counts, action distribution, outcome statistics, and
    numeric aggregates across all AllocationDecisionMemoryRecord objects.
    approved_for_execution is always False.
    """

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    status: AllocationMemoryStatus = "unknown"
    record_count: int = 0
    action_counts: dict[str, int] = Field(default_factory=dict)
    reviewed_count: int = 0
    needs_review_count: int = 0
    blocked_count: int = 0
    high_risk_count: int = 0
    pending_outcome_count: int = 0
    positive_outcome_count: int = 0
    negative_outcome_count: int = 0
    avg_forward_return_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    top_warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "AllocationMemorySummary":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-D. "
                "This layer does not authorize execution."
            )
        return self


class AllocationMemoryReport(BaseModel):
    """
    Full allocation memory report aggregating all decision memory records for a target.

    Captures allocation decisions with their evidence, source refs, artifact refs,
    and a summary. Does not duplicate full upstream artifact content.

    run_id is optional; derived from input_bundle.run_id when available.

    approved_for_execution is ALWAYS False. This report is a research audit
    artifact only and does not constitute investment advice or authorize any
    form of execution.

    No persistence, database write, vector store, or broker integration is
    introduced by this model. No brokerage / live portfolio data.
    """

    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    run_id: Optional[str] = None
    status: AllocationMemoryStatus = "unknown"
    records: list[AllocationDecisionMemoryRecord] = Field(default_factory=list)
    summary: AllocationMemorySummary
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    calculation_version: str = _CALCULATION_VERSION
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "AllocationMemoryReport":
        for fn in ("report_id", "target", "created_at", "updated_at"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "AllocationMemoryReport":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-D. "
                "This layer does not authorize execution."
            )
        return self


# ---------------------------------------------------------------------------
# Helper: deterministic ID generators
# ---------------------------------------------------------------------------

def make_allocation_memory_record_id(
    target: str,
    action: str,
    as_of: str,
    run_id: Optional[str] = None,
    snapshot_id: Optional[str] = None,
    rationale: Optional[str] = None,
    review_status: Optional[str] = None,
    outcome: Optional[str] = None,
) -> str:
    """Return a deterministic stable hash ID for an AllocationDecisionMemoryRecord.

    Including snapshot_id ensures two records that share the same
    target/action/as_of/run_id but differ in decision content (e.g. different
    target allocation, risk level, or rationale) receive distinct IDs.
    All optional parameters are included in the payload only when not None,
    preserving backwards-compatible behaviour for callers that omit them.
    """
    payload: dict[str, Any] = {
        "target": target,
        "action": action,
        "as_of": as_of,
    }
    if run_id:
        payload["run_id"] = run_id
    if snapshot_id is not None:
        payload["snapshot_id"] = snapshot_id
    if rationale is not None:
        payload["rationale"] = rationale
    if review_status is not None:
        payload["review_status"] = review_status
    if outcome is not None:
        payload["outcome"] = outcome
    h = stable_hash_payload(payload, length=16)
    return f"amem_{h}"


def make_allocation_memory_log_entry_id(
    allocation_memory_id: str,
    event_type: str,
    created_at: str,
) -> str:
    """Return a deterministic stable hash ID for an AllocationMemoryLogEntry."""
    payload = {
        "allocation_memory_id": allocation_memory_id,
        "event_type": event_type,
        "created_at": created_at,
    }
    h = stable_hash_payload(payload, length=12)
    return f"amlog_{h}"


def make_allocation_memory_report_id(
    target: str,
    as_of: str,
    run_id: Optional[str] = None,
) -> str:
    """Return a deterministic stable hash ID for an AllocationMemoryReport."""
    payload: dict[str, Any] = {"target": target, "as_of": as_of}
    if run_id:
        payload["run_id"] = run_id
    h = stable_hash_payload(payload, length=16)
    return f"amrep_{h}"


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
    source_refs: list[AllocationMemorySourceRef],
) -> list[AllocationMemorySourceRef]:
    """Deduplicate AllocationMemorySourceRef list by source_id (first occurrence wins)."""
    seen: set[str] = set()
    result: list[AllocationMemorySourceRef] = []
    for ref in source_refs:
        if ref.source_id not in seen:
            seen.add(ref.source_id)
            result.append(ref)
    return result


def _determine_single_record_status(
    risk_level: str,
    review_status: str,
    input_bundle: Optional[AllocationMemoryInputBundle] = None,
    initial_status: Optional[AllocationMemoryStatus] = None,
) -> tuple[AllocationMemoryStatus, list[str]]:
    """
    Determine the status for a single AllocationDecisionMemoryRecord.

    Priority:
      initial_status override > blocked (HRR blocked or review_status=blocked) >
      needs_review (high-risk unreviewed, or pending/escalated review) > reviewed > active

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
                "— allocation memory record status set to blocked."
            )
            return "blocked", warnings

    if review_status == "blocked":
        warnings.append(
            "Review status is blocked "
            "— allocation memory record status set to blocked."
        )
        return "blocked", warnings

    if risk_level == "high" and review_status != "reviewed":
        warnings.append(
            f"High-risk allocation without confirmed review (review_status={review_status!r}) "
            "— record status set to needs_review."
        )
        return "needs_review", warnings

    if review_status in ("pending", "escalated"):
        warnings.append(
            f"Review status is '{review_status}' "
            "— record status set to needs_review."
        )
        return "needs_review", warnings

    if review_status == "reviewed":
        return "reviewed", warnings

    return "active", warnings


# ---------------------------------------------------------------------------
# Helper: snapshot builder
# ---------------------------------------------------------------------------

def build_allocation_decision_snapshot(
    target: str,
    target_allocation_pct: Optional[float] = None,
    actual_allocation_pct: Optional[float] = None,
    min_allocation_pct: Optional[float] = None,
    max_allocation_pct: Optional[float] = None,
    cash_pct: Optional[float] = None,
    required_trade_value: Optional[float] = None,
    required_shares: Optional[float] = None,
    cash_impact: Optional[float] = None,
    projected_cash_pct: Optional[float] = None,
    portfolio_loss_pct: Optional[float] = None,
    risk_budget_pct: Optional[float] = None,
    risk_level: AllocationMemoryRiskLevel = "unknown",
    source_refs: Optional[list[AllocationMemorySourceRef]] = None,
    evidence_ids: Optional[list[str]] = None,
    artifact_refs: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
    as_of: Optional[str] = None,
) -> AllocationDecisionSnapshot:
    """
    Build an AllocationDecisionSnapshot from allocation data at decision time.

    Deterministic: same inputs → same snapshot_id.
    Deduplicates source_refs by source_id (first occurrence wins).
    No live data, no brokerage calls, no execution implication.
    Inputs are never mutated.
    """
    _source_refs = _dedup_source_refs(list(source_refs or []))
    _evidence_ids = _dedup_list(list(evidence_ids or []))
    _artifact_refs = _dedup_list([r for r in (artifact_refs or []) if r and r.strip()])

    snapshot_payload: dict[str, Any] = {
        "target": target,
        "target_allocation_pct": target_allocation_pct,
        "actual_allocation_pct": actual_allocation_pct,
        "risk_level": risk_level,
        "as_of": as_of or _DETERMINISTIC_TIMESTAMP_DEFAULT,
    }
    h = stable_hash_payload(snapshot_payload, length=12)
    snapshot_id = f"asnap_{h}"

    return AllocationDecisionSnapshot(
        snapshot_id=snapshot_id,
        target=target,
        target_allocation_pct=target_allocation_pct,
        actual_allocation_pct=actual_allocation_pct,
        min_allocation_pct=min_allocation_pct,
        max_allocation_pct=max_allocation_pct,
        cash_pct=cash_pct,
        required_trade_value=required_trade_value,
        required_shares=required_shares,
        cash_impact=cash_impact,
        projected_cash_pct=projected_cash_pct,
        portfolio_loss_pct=portfolio_loss_pct,
        risk_budget_pct=risk_budget_pct,
        risk_level=risk_level,
        source_refs=_source_refs,
        evidence_ids=_evidence_ids,
        artifact_refs=_artifact_refs,
        warnings=list(warnings or []),
    )


# ---------------------------------------------------------------------------
# Helper: log entry builder
# ---------------------------------------------------------------------------

def build_allocation_memory_log_entry(
    event_type: AllocationMemoryEventType,
    description: str,
    allocation_memory_id: str,
    created_at: Optional[str] = None,
    actor: AllocationMemoryActorType = "system",
    source_ids: Optional[list[str]] = None,
    evidence_ids: Optional[list[str]] = None,
    metadata: Optional[dict[str, Any]] = None,
    warnings: Optional[list[str]] = None,
) -> AllocationMemoryLogEntry:
    """Build a single AllocationMemoryLogEntry with a deterministic event_id."""
    ts = created_at or _DETERMINISTIC_TIMESTAMP_DEFAULT
    entry_id = make_allocation_memory_log_entry_id(
        allocation_memory_id=allocation_memory_id,
        event_type=event_type,
        created_at=ts,
    )
    return AllocationMemoryLogEntry(
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

def determine_allocation_memory_status(
    records: list[AllocationDecisionMemoryRecord],
    input_bundle: Optional[AllocationMemoryInputBundle] = None,
) -> tuple[AllocationMemoryStatus, list[str]]:
    """
    Determine the overall AllocationMemoryStatus for an AllocationMemoryReport.

    Precedence: blocked > needs_review > reviewed > active > archived > unknown

    - blocked:      HRR blocked in input_bundle, OR any record has status=blocked.
    - needs_review: any record has status=needs_review, OR any high-risk unreviewed record.
    - reviewed:     all non-archived/non-invalidated records are reviewed.
    - active:       records exist with active status and no review signals.
    - archived:     all records are archived.
    - unknown:      no records, or all invalidated/unknown statuses.

    Returns (status, warnings). Inputs are never mutated.
    """
    warnings: list[str] = []

    hrr = getattr(input_bundle, "human_review_report", None) if input_bundle else None
    if hrr is not None:
        hr_status = str(getattr(hrr, "status", "unknown"))
        if hr_status == "blocked":
            warnings.append(
                "Human review report is blocked "
                "— allocation memory report status set to blocked."
            )
            return "blocked", warnings

    if not records:
        warnings.append("No allocation memory records provided — report status is unknown.")
        return "unknown", warnings

    statuses = [r.status for r in records]

    if "blocked" in statuses:
        n = statuses.count("blocked")
        warnings.append(f"{n} allocation memory record(s) are blocked.")
        return "blocked", warnings

    if "needs_review" in statuses:
        n = statuses.count("needs_review")
        warnings.append(f"{n} allocation memory record(s) require review.")
        return "needs_review", warnings

    # High-risk unreviewed records escalate to needs_review
    high_risk_unreviewed = [
        r for r in records
        if r.decision_snapshot.risk_level == "high"
        and r.status not in ("reviewed", "archived", "invalidated")
    ]
    if high_risk_unreviewed:
        warnings.append(
            f"{len(high_risk_unreviewed)} high-risk allocation(s) are not yet reviewed."
        )
        return "needs_review", warnings

    non_terminal = [
        s for s in statuses if s not in ("archived", "invalidated", "unknown")
    ]

    if not non_terminal:
        if all(s == "archived" for s in statuses):
            return "archived", warnings
        return "unknown", warnings

    if all(s == "reviewed" for s in non_terminal):
        return "reviewed", warnings

    if any(s == "active" for s in non_terminal):
        return "active", warnings

    return "unknown", warnings


# ---------------------------------------------------------------------------
# Helper: ID / ref collection
# ---------------------------------------------------------------------------

def collect_allocation_memory_source_ids(
    input_bundle: AllocationMemoryInputBundle,
    records: Optional[list[AllocationDecisionMemoryRecord]] = None,
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
        "allocation_report",
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
            for ref in record.decision_snapshot.source_refs:
                _add(ref.source_id)

    return result


def collect_allocation_memory_evidence_ids(
    input_bundle: AllocationMemoryInputBundle,
    records: Optional[list[AllocationDecisionMemoryRecord]] = None,
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

    if records:
        for record in records:
            for eid in record.evidence_ids:
                _add(eid)
            for ref in record.source_refs:
                if ref.evidence_id:
                    _add(ref.evidence_id)
            for eid in record.decision_snapshot.evidence_ids:
                _add(eid)
            for ref in record.decision_snapshot.source_refs:
                if ref.evidence_id:
                    _add(ref.evidence_id)

    return result


def collect_allocation_memory_artifact_refs(
    input_bundle: AllocationMemoryInputBundle,
    records: Optional[list[AllocationDecisionMemoryRecord]] = None,
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
            for ref in record.decision_snapshot.artifact_refs:
                _add(ref)

    return result


# ---------------------------------------------------------------------------
# Helper: summary builder
# ---------------------------------------------------------------------------

def summarize_allocation_memory(
    target: str,
    status: AllocationMemoryStatus,
    records: list[AllocationDecisionMemoryRecord],
    warnings: list[str],
) -> AllocationMemorySummary:
    """Build an AllocationMemorySummary from resolved allocation memory components."""
    record_count = len(records)

    action_counts: dict[str, int] = {}
    for r in records:
        action_counts[r.action] = action_counts.get(r.action, 0) + 1

    reviewed_count = sum(1 for r in records if r.status == "reviewed")
    needs_review_count = sum(1 for r in records if r.status == "needs_review")
    blocked_count = sum(1 for r in records if r.status == "blocked")
    high_risk_count = sum(
        1 for r in records if r.decision_snapshot.risk_level == "high"
    )
    pending_outcome_count = sum(1 for r in records if r.outcome == "pending")
    positive_outcome_count = sum(1 for r in records if r.outcome == "positive")
    negative_outcome_count = sum(1 for r in records if r.outcome == "negative")

    fwd_returns = [
        r.forward_return_pct for r in records if r.forward_return_pct is not None
    ]
    avg_forward_return_pct: Optional[float] = (
        round(sum(fwd_returns) / len(fwd_returns), 10)
        if fwd_returns
        else None
    )

    drawdowns = [
        r.max_drawdown_pct for r in records if r.max_drawdown_pct is not None
    ]
    max_drawdown_pct: Optional[float] = max(drawdowns) if drawdowns else None

    top_warnings = warnings[:5]

    return AllocationMemorySummary(
        target=target,
        status=status,
        record_count=record_count,
        action_counts=action_counts,
        reviewed_count=reviewed_count,
        needs_review_count=needs_review_count,
        blocked_count=blocked_count,
        high_risk_count=high_risk_count,
        pending_outcome_count=pending_outcome_count,
        positive_outcome_count=positive_outcome_count,
        negative_outcome_count=negative_outcome_count,
        avg_forward_return_pct=avg_forward_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        top_warnings=top_warnings,
        approved_for_execution=False,
    )


# ---------------------------------------------------------------------------
# Main builders
# ---------------------------------------------------------------------------

def build_allocation_memory_record(
    target: str,
    action: AllocationDecisionAction,
    rationale: str,
    decision_snapshot: Optional[AllocationDecisionSnapshot] = None,
    review_status: AllocationDecisionReviewStatus = "unknown",
    outcome: AllocationDecisionOutcome = "unknown",
    forward_return_pct: Optional[float] = None,
    max_drawdown_pct: Optional[float] = None,
    lesson: Optional[str] = None,
    review_trigger: Optional[str] = None,
    run_id: Optional[str] = None,
    memory_id: Optional[str] = None,
    thesis_id: Optional[str] = None,
    allocation_report_id: Optional[str] = None,
    trade_plan_report_id: Optional[str] = None,
    decision_packet_id: Optional[str] = None,
    source_refs: Optional[list[AllocationMemorySourceRef]] = None,
    evidence_ids: Optional[list[str]] = None,
    artifact_refs: Optional[list[str]] = None,
    recorded_at: Optional[str] = None,
    initial_status: Optional[AllocationMemoryStatus] = None,
    input_bundle: Optional[AllocationMemoryInputBundle] = None,
    extra_warnings: Optional[list[str]] = None,
) -> AllocationDecisionMemoryRecord:
    """
    Build an AllocationDecisionMemoryRecord for a single allocation decision.

    Timestamp resolution priority (highest wins):
      1. explicit recorded_at argument;
      2. input_bundle.as_of if present;
      3. _DETERMINISTIC_TIMESTAMP_DEFAULT ("1970-01-01T00:00:00Z").

    Identical inputs without explicit timestamps always produce identical output.
    Inputs are never mutated.
    approved_for_execution is always False.
    Missing optional upstream artifacts produce warnings, not crashes.
    initial_status overrides auto-determined status when provided.

    If decision_snapshot is not provided, an empty snapshot is generated
    with a warning.
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

    # Build or use decision_snapshot FIRST — snapshot_id is needed for the
    # content-sensitive record ID so that two records sharing the same
    # target/action/as_of/run_id but carrying different allocation numbers
    # do not collide.
    extra_snap_warnings: list[str] = []
    if decision_snapshot is None:
        extra_snap_warnings.append(
            "No decision_snapshot provided — using empty snapshot with no allocation data."
        )
        decision_snapshot = build_allocation_decision_snapshot(
            target=target,
            as_of=as_of,
        )

    allocation_memory_id = make_allocation_memory_record_id(
        target=target,
        action=action,
        as_of=as_of,
        run_id=effective_run_id,
        snapshot_id=decision_snapshot.snapshot_id,
        rationale=rationale,
        review_status=review_status,
        outcome=outcome,
    )

    # Deduplicate source_refs by source_id (first occurrence wins)
    _seen_sids: set[str] = set()
    _source_refs: list[AllocationMemorySourceRef] = []
    for _sr in (source_refs or []):
        if _sr.source_id not in _seen_sids:
            _seen_sids.add(_sr.source_id)
            _source_refs.append(_sr)

    _evidence_ids = _dedup_list(list(evidence_ids or []))
    _artifact_refs = _dedup_list([r for r in (artifact_refs or []) if r and r.strip()])

    risk_level = decision_snapshot.risk_level
    status, status_warnings = _determine_single_record_status(
        risk_level=risk_level,
        review_status=review_status,
        input_bundle=input_bundle,
        initial_status=initial_status,
    )

    bundle_warnings = list(input_bundle.warnings if input_bundle else [])

    missing_warnings: list[str] = []
    if input_bundle is not None:
        if input_bundle.allocation_report is None:
            missing_warnings.append(
                "Missing optional upstream artifact: allocation_report."
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
    creation_entry = build_allocation_memory_log_entry(
        event_type="allocation_recorded",
        description=(
            f"Allocation decision memory record created for target '{target}' "
            f"(action={action!r}, risk_level={risk_level!r}, status={status!r}, "
            f"outcome={outcome!r})."
        ),
        allocation_memory_id=allocation_memory_id,
        created_at=ts,
        actor="system",
        source_ids=[ref.source_id for ref in _source_refs],
        evidence_ids=_evidence_ids,
        metadata={"target": target, "action": action},
    )
    event_log = [creation_entry]

    if status in ("blocked", "needs_review"):
        review_entry = build_allocation_memory_log_entry(
            event_type="allocation_review_requested",
            description=(
                f"Allocation decision record requires review — status is '{status}'."
            ),
            allocation_memory_id=allocation_memory_id,
            created_at=ts,
            actor="system",
        )
        event_log.append(review_entry)

    if lesson:
        lesson_entry = build_allocation_memory_log_entry(
            event_type="lesson_added",
            description=f"Lesson recorded: {lesson}",
            allocation_memory_id=allocation_memory_id,
            created_at=ts,
            actor="system",
            metadata={"lesson": lesson},
        )
        event_log.append(lesson_entry)

    if outcome not in ("unknown", "pending"):
        outcome_entry = build_allocation_memory_log_entry(
            event_type="outcome_observed",
            description=(
                f"Allocation outcome observed: {outcome!r}. "
                f"forward_return_pct={forward_return_pct!r}, "
                f"max_drawdown_pct={max_drawdown_pct!r}."
            ),
            allocation_memory_id=allocation_memory_id,
            created_at=ts,
            actor="system",
            metadata={"outcome": outcome},
        )
        event_log.append(outcome_entry)

    return AllocationDecisionMemoryRecord(
        allocation_memory_id=allocation_memory_id,
        target=target,
        run_id=effective_run_id,
        memory_id=effective_memory_id,
        thesis_id=effective_thesis_id,
        allocation_report_id=allocation_report_id,
        trade_plan_report_id=trade_plan_report_id,
        decision_packet_id=decision_packet_id,
        action=action,
        status=status,
        review_status=review_status,
        outcome=outcome,
        decision_snapshot=decision_snapshot,
        rationale=rationale,
        review_trigger=review_trigger,
        forward_return_pct=forward_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        lesson=lesson,
        recorded_at=ts,
        source_refs=_source_refs,
        evidence_ids=_evidence_ids,
        artifact_refs=_artifact_refs,
        event_log=event_log,
        warnings=all_warnings,
        approved_for_execution=False,
    )


def build_allocation_memory_report(
    input_bundle: AllocationMemoryInputBundle,
    records: Optional[list[AllocationDecisionMemoryRecord]] = None,
    created_at: Optional[str] = None,
    updated_at: Optional[str] = None,
) -> AllocationMemoryReport:
    """
    Build an AllocationMemoryReport from an input bundle and a list of records.

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

    report_id = make_allocation_memory_report_id(
        target=input_bundle.target,
        as_of=as_of,
        run_id=run_id,
    )

    _records = list(records or [])

    status, status_warnings = determine_allocation_memory_status(
        records=_records,
        input_bundle=input_bundle,
    )

    missing_warnings: list[str] = []
    if input_bundle.allocation_report is None:
        missing_warnings.append("Missing optional upstream artifact: allocation_report.")
    if input_bundle.trade_plan_report is None:
        missing_warnings.append("Missing optional upstream artifact: trade_plan_report.")
    if input_bundle.decision_packet is None:
        missing_warnings.append("Missing optional upstream artifact: decision_packet.")
    if input_bundle.human_review_report is None:
        missing_warnings.append("Missing optional upstream artifact: human_review_report.")

    all_warnings = list(input_bundle.warnings) + status_warnings + missing_warnings

    source_ids = collect_allocation_memory_source_ids(input_bundle, _records)
    evidence_ids = collect_allocation_memory_evidence_ids(input_bundle, _records)
    artifact_refs = collect_allocation_memory_artifact_refs(input_bundle, _records)

    summary = summarize_allocation_memory(
        target=input_bundle.target,
        status=status,
        records=_records,
        warnings=all_warnings,
    )

    return AllocationMemoryReport(
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

def allocation_memory_tool_result_from_report(
    report: AllocationMemoryReport,
    run_id: Optional[str] = None,
) -> ToolResult:
    """
    Wrap an AllocationMemoryReport as a ToolResult for evidence-store integration.

    Stable tool name: "allocation_memory_report".
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
        "high_risk_count": report.summary.high_risk_count,
        "pending_outcome_count": report.summary.pending_outcome_count,
        "calculation_version": report.calculation_version,
        "approved_for_execution": False,
    }

    evidence_id = make_evidence_id(
        run_id=_run_id,
        tool_name=_ALLOCATION_MEMORY_TOOL_NAME,
        target=report.target,
        metric_group=_ALLOCATION_MEMORY_METRIC_GROUP,
        payload=outputs,
    )

    return ToolResult(
        tool_name=_ALLOCATION_MEMORY_TOOL_NAME,
        run_id=_run_id,
        ticker=report.target if report.target else None,
        evidence_id=evidence_id,
        inputs={"target": report.target, "report_id": report.report_id},
        outputs=outputs,
        description=(
            f"AllocationMemoryReport for {report.target} "
            f"(report_id={report.report_id!r}, status={report.status!r}, "
            f"records={report.summary.record_count}, "
            f"reviewed={report.summary.reviewed_count}, "
            f"needs_review={report.summary.needs_review_count})."
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Literal type aliases
    "AllocationDecisionAction",
    "AllocationDecisionOutcome",
    "AllocationDecisionReviewStatus",
    "AllocationMemoryActorType",
    "AllocationMemoryEventType",
    "AllocationMemoryRiskLevel",
    "AllocationMemoryStatus",
    # Models
    "AllocationDecisionMemoryRecord",
    "AllocationDecisionSnapshot",
    "AllocationMemoryInputBundle",
    "AllocationMemoryLogEntry",
    "AllocationMemoryReport",
    "AllocationMemorySourceRef",
    "AllocationMemorySummary",
    # Helpers
    "allocation_memory_tool_result_from_report",
    "build_allocation_decision_snapshot",
    "build_allocation_memory_log_entry",
    "build_allocation_memory_record",
    "build_allocation_memory_report",
    "collect_allocation_memory_artifact_refs",
    "collect_allocation_memory_evidence_ids",
    "collect_allocation_memory_source_ids",
    "determine_allocation_memory_status",
    "make_allocation_memory_log_entry_id",
    "make_allocation_memory_record_id",
    "make_allocation_memory_report_id",
    "summarize_allocation_memory",
]
