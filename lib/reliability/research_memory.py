"""
lib/reliability/research_memory.py

Phase 4M-A: Research Run Memory Schema.

Design principles:
  - Standalone, deterministic, offline/mock-only.
  - No live LLM calls, no live data fetching, no app integration.
  - No database writes, no file persistence, no vector store.
  - No broker / order / execution behavior.
  - No pathway that can set approved_for_execution = True.
  - Defines memory records and helper functions only.
  - Consumes typed research artifacts from prior phases via source refs / IDs.
  - Produces structured ResearchRunMemoryRecord objects for auditable
    decision-trail preservation.
  - Missing optional prior artifacts produce warnings, not crashes.
  - Does NOT import from app.py, pages/*, lib/llm_orchestrator.py, or any
    live workflow module.
  - Does NOT produce investment advice, buy/sell recommendations, or
    individual security recommendations.
  - approved_for_execution is ALWAYS False. No pathway to set it True exists.

Status precedence:
  blocked > needs_review > incomplete > recorded > unknown

  - blocked      — human review blocked OR critical block from upstream
  - needs_review — review_required signal, missing decision packet without
                   critical block, explicit needs_review trigger
  - incomplete   — missing important optional artifacts (reliability report,
                   decision packet, etc.) without a review/block signal
  - recorded     — clean run with sufficient source/evidence/artifact refs
  - unknown      — run_id or target missing (validation error) or default

Relationship to Roadmap v4 Phase 4:
  - This module starts the Roadmap Phase 4 Memory + Human Feedback mainline.
  - Phase 4A (integration_boundary.py) remains accepted early infrastructure
    and is NOT this memory mainline.
  - Future subphases: Thesis Memory, Catalyst Memory, Allocation Decision Memory,
    Option Trade Plan Memory, Human Feedback Layer, Agent Evaluation.

See docs/reliability_phase_4m_research_memory.md for design.

Disclaimer: All outputs are for research and educational purposes only.
They do not constitute investment advice. Markets involve risk.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.adapters import make_evidence_id, stable_hash_payload
from lib.reliability.schemas import ToolResult


# Stable fallback used when no timestamp is available from any deterministic source.
# Ensures build_research_run_memory_record() is fully deterministic for identical inputs
# even when the caller omits created_at / updated_at and the input bundle lacks
# as_of / created_at.
_DETERMINISTIC_TIMESTAMP_DEFAULT: str = "1970-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Literal type aliases (enums)
# ---------------------------------------------------------------------------

MemoryRecordStatus = Literal[
    "unknown",
    "active",
    "archived",
    "superseded",
    "invalidated",
    "needs_review",
]

ResearchRunMemoryStatus = Literal[
    "unknown",
    "recorded",
    "incomplete",
    "needs_review",
    "blocked",
]

ResearchRunMemorySourceType = Literal[
    "orchestration",
    "horizon_synthesis",
    "macro",
    "debate",
    "decision_packet",
    "human_review",
    "review_loop",
    "event_intelligence",
    "trade_plan",
    "allocation",
    "option_expression",
    "integration_boundary",
    "validation",
    "staleness",
    "critic",
    "tool_result",
    "user_feedback",
    "unknown",
]

MemoryEventType = Literal[
    "research_run_created",
    "thesis_created",
    "decision_created",
    "review_requested",
    "human_feedback_added",
    "outcome_updated",
    "superseded",
    "invalidated",
    "unknown",
]

MemoryActorType = Literal[
    "system",
    "user",
    "reviewer",
    "agent",
    "unknown",
]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_RESEARCH_MEMORY_TOOL_NAME: str = "research_run_memory_record"
_RESEARCH_MEMORY_METRIC_GROUP: str = "research_run_memory_record"
_CALCULATION_VERSION: str = "research_run_memory_v1"

# Source types considered "core" — absence causes incomplete/needs_review
_CORE_SOURCE_TYPES: frozenset[str] = frozenset({
    "orchestration",
    "decision_packet",
    "review_loop",
})


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class MemorySourceRef(BaseModel):
    """
    A stable pointer to an upstream reliability artifact.

    Used to build the decision trail in a ResearchRunMemoryRecord without
    duplicating full artifact content.  All fields except source_id and
    source_type are optional to accommodate partial artifact availability.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    source_type: ResearchRunMemorySourceType = "unknown"
    artifact_id: Optional[str] = None
    run_id: Optional[str] = None
    target: Optional[str] = None
    field_path: Optional[str] = None
    evidence_id: Optional[str] = None
    label: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "MemorySourceRef":
        v = self.source_id
        if not v.strip():
            raise ValueError(f"'source_id' must not be whitespace-only; got {v!r}.")
        return self


class MemoryEvent(BaseModel):
    """
    A timestamped event recorded in the memory record's event log.

    Events trace the lifecycle of a research run memory record — from
    creation through human review, feedback, supersession, and invalidation.
    Not an execution instruction or order.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: MemoryEventType = "unknown"
    created_at: str = Field(min_length=1)
    actor: MemoryActorType = "system"
    description: str = ""
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "MemoryEvent":
        for fn in ("event_id", "created_at"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class ResearchRunMemoryInputBundle(BaseModel):
    """
    Input bundle for building a research run memory record from accepted artifacts.

    Holds optional prior-phase research artifacts for evidence tracing.
    All prior artifact fields beyond run_id and target are optional (Any) to
    avoid hard cross-module dependencies at import time.  Only source_refs,
    evidence_ids, tool_result_ids, and status attributes are read by helpers.

    Missing optional artifacts produce warnings, not crashes.
    This bundle does not contain or imply any execution authorization.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    run_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    as_of: Optional[str] = None
    created_at: Optional[str] = None
    workflow_name: Optional[str] = None

    # Caller-supplied source refs and IDs (explicit tracing)
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    tool_result_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)

    # Duck-typed optional upstream research artifacts
    validation_summary: Optional[Any] = None
    reliability_report: Optional[Any] = None
    decision_packet: Optional[Any] = None
    human_review_report: Optional[Any] = None
    event_intelligence_report: Optional[Any] = None
    trade_plan_report: Optional[Any] = None
    allocation_report: Optional[Any] = None
    option_expression_report: Optional[Any] = None
    integration_boundary_report: Optional[Any] = None

    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "ResearchRunMemoryInputBundle":
        for fn in ("run_id", "target"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class ResearchRunMemorySummary(BaseModel):
    """
    Deterministic summary of one research run memory record.

    Computed from input bundle and resolved status.
    approved_for_execution is always False.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    status: ResearchRunMemoryStatus = "unknown"
    source_count: int = 0
    evidence_count: int = 0
    tool_result_count: int = 0
    artifact_count: int = 0
    has_decision_packet: bool = False
    has_human_review: bool = False
    has_event_intelligence: bool = False
    has_trade_plan: bool = False
    has_allocation: bool = False
    has_option_expression: bool = False
    has_integration_boundary: bool = False
    review_required: bool = False
    blocked: bool = False
    top_warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "ResearchRunMemorySummary":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-A. "
                "This layer does not authorize execution."
            )
        return self


class ResearchRunMemoryRecord(BaseModel):
    """
    Full research run memory record for one research run.

    Captures the decision trail by reference — source refs, evidence IDs,
    tool result IDs, and artifact refs — without duplicating full artifact
    content.

    approved_for_execution is ALWAYS False.  This record is a research
    audit artifact only and does not constitute investment advice or
    authorize any form of execution.

    No persistence, database write, vector store, or broker integration
    is introduced by this model.
    """

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    status: ResearchRunMemoryStatus = "unknown"
    summary: ResearchRunMemorySummary
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    tool_result_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    event_log: list[MemoryEvent] = Field(default_factory=list)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    calculation_version: str = _CALCULATION_VERSION
    warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "ResearchRunMemoryRecord":
        for fn in ("memory_id", "run_id", "target", "created_at", "updated_at"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "ResearchRunMemoryRecord":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-A. "
                "This layer does not authorize execution."
            )
        return self


class ResearchRunMemoryIndexEntry(BaseModel):
    """
    Lightweight index entry for a ResearchRunMemoryRecord.

    Used to maintain a fast-access index across multiple memory records
    without loading full record content.  No persistence is implied.
    """

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    status: ResearchRunMemoryStatus = "unknown"
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    source_count: int = 0
    evidence_count: int = 0
    review_required: bool = False
    blocked: bool = False
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "ResearchRunMemoryIndexEntry":
        for fn in ("memory_id", "run_id", "target", "created_at", "updated_at"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


# ---------------------------------------------------------------------------
# Helper: deterministic ID generators
# ---------------------------------------------------------------------------

def make_research_run_memory_id(
    run_id: str,
    target: str,
    as_of: str,
) -> str:
    """Return a deterministic stable hash ID for a ResearchRunMemoryRecord."""
    payload = {"run_id": run_id, "target": target, "as_of": as_of}
    h = stable_hash_payload(payload, length=16)
    return f"rmem_{h}"


def make_memory_event_id(
    memory_id: str,
    event_type: str,
    created_at: str,
) -> str:
    """Return a deterministic stable hash ID for a MemoryEvent."""
    payload = {"memory_id": memory_id, "event_type": event_type, "created_at": created_at}
    h = stable_hash_payload(payload, length=12)
    return f"mevt_{h}"


# ---------------------------------------------------------------------------
# Helper: source ref collection
# ---------------------------------------------------------------------------

def collect_memory_source_refs(
    input_bundle: ResearchRunMemoryInputBundle,
) -> list[MemorySourceRef]:
    """
    Collect and deduplicate MemorySourceRef objects from the input bundle.

    Deduplication is by source_id (first occurrence wins, preserving order).
    Caller-supplied source_refs take precedence over auto-detected artifact refs.
    """
    seen: set[str] = set()
    result: list[MemorySourceRef] = []

    def _add(ref: MemorySourceRef) -> None:
        if ref.source_id not in seen:
            seen.add(ref.source_id)
            result.append(ref)

    # Caller-supplied source refs first
    for ref in input_bundle.source_refs:
        _add(ref)

    # Auto-detect from optional duck-typed artifacts
    _artifact_map = [
        ("reliability_report",         "review_loop"),
        ("decision_packet",             "decision_packet"),
        ("human_review_report",         "human_review"),
        ("event_intelligence_report",   "event_intelligence"),
        ("trade_plan_report",           "trade_plan"),
        ("allocation_report",           "allocation"),
        ("option_expression_report",    "option_expression"),
        ("integration_boundary_report", "integration_boundary"),
        ("validation_summary",          "validation"),
    ]
    for attr_name, source_type in _artifact_map:
        artifact = getattr(input_bundle, attr_name, None)
        if artifact is None:
            continue
        # Extract artifact_id from common report-id attributes
        artifact_id: Optional[str] = (
            getattr(artifact, "report_id", None)
            or getattr(artifact, "result_id", None)
            or getattr(artifact, "packet_id", None)
            or getattr(artifact, "bundle_id", None)
        )
        source_id = artifact_id or f"{source_type}:{input_bundle.run_id}"
        ref = MemorySourceRef(
            source_id=source_id,
            source_type=source_type,  # type: ignore[arg-type]
            artifact_id=artifact_id,
            run_id=input_bundle.run_id,
            target=input_bundle.target,
            label=source_type.replace("_", " ").title(),
        )
        _add(ref)

    return result


def collect_memory_evidence_ids(
    input_bundle: ResearchRunMemoryInputBundle,
    source_refs: list[MemorySourceRef],
) -> list[str]:
    """
    Collect and deduplicate evidence IDs from the input bundle and source refs.

    Deduplication preserves first-occurrence order.
    """
    seen: set[str] = set()
    result: list[str] = []

    def _add_id(eid: str) -> None:
        if eid and eid not in seen:
            seen.add(eid)
            result.append(eid)

    # Caller-supplied evidence IDs
    for eid in input_bundle.evidence_ids:
        _add_id(eid)

    # Evidence IDs embedded in source refs
    for ref in source_refs:
        if ref.evidence_id:
            _add_id(ref.evidence_id)

    return result


def collect_memory_tool_result_ids(
    input_bundle: ResearchRunMemoryInputBundle,
    source_refs: list[MemorySourceRef],
) -> list[str]:
    """
    Collect and deduplicate tool result IDs from the input bundle.

    Deduplication preserves first-occurrence order.
    """
    seen: set[str] = set()
    result: list[str] = []

    for tid in input_bundle.tool_result_ids:
        if tid and tid not in seen:
            seen.add(tid)
            result.append(tid)

    return result


# ---------------------------------------------------------------------------
# Helper: status determination
# ---------------------------------------------------------------------------

def determine_research_run_memory_status(
    input_bundle: ResearchRunMemoryInputBundle,
    source_refs: list[MemorySourceRef],
) -> tuple[ResearchRunMemoryStatus, bool, bool, list[str]]:
    """
    Derive the ResearchRunMemoryStatus from the input bundle.

    Returns (status, review_required, blocked, warnings).

    Priority (highest wins):
      blocked      — human review blocked (critical feedback) OR critical block signal
      needs_review — explicit review_required signal; missing decision packet/
                     reliability report without critical block
      incomplete   — missing important optional artifacts (decision packet or
                     reliability report) without a review/block signal
      recorded     — clean run with sufficient source/evidence/artifact refs
      unknown      — unexpected state or no artifacts

    approved_for_execution is never implied by any status value.
    """
    warnings: list[str] = []
    review_required: bool = False
    blocked: bool = False

    hrr = input_bundle.human_review_report
    dp = input_bundle.decision_packet
    rr = input_bundle.reliability_report

    # --- Check for human review block ---
    hr_blocked: bool = False
    if hrr is not None:
        hr_status = str(getattr(hrr, "status", "unknown"))
        if hr_status == "blocked":
            hr_blocked = True
            blocked = True
            warnings.append(
                "Human review report is blocked — critical feedback detected."
            )

    # --- Check for decision packet signals ---
    dp_present: bool = dp is not None
    dp_blocked: bool = False
    if dp_present:
        dp_status = str(getattr(dp, "status", "unknown"))
        if dp_status in ("blocked",):
            dp_blocked = True
            blocked = True
            warnings.append(
                f"Decision packet status is '{dp_status}' — blocked at decision layer."
            )
        elif dp_status in ("fail",):
            review_required = True
            warnings.append(
                f"Decision packet status is '{dp_status}' — requires review."
            )

    # --- Check for reliability report ---
    rr_present: bool = rr is not None
    if rr_present:
        rr_status = str(getattr(rr, "status", "unknown"))
        if rr_status in ("blocked",):
            blocked = True
            warnings.append(
                "Reliability run report status is 'blocked'."
            )
        elif rr_status in ("needs_revision", "failed"):
            review_required = True
            warnings.append(
                f"Reliability run report status is '{rr_status}' — review required."
            )

    # --- Check for missing important artifacts ---
    missing_important: list[str] = []
    if not dp_present:
        missing_important.append("decision_packet")
    if not rr_present:
        missing_important.append("reliability_report")
    if missing_important:
        review_required = True
        warnings.append(
            "Missing important artifact refs: "
            + ", ".join(missing_important)
            + ". Status: incomplete or needs_review."
        )

    # --- Count available refs to decide recorded vs incomplete ---
    has_refs = (
        len(source_refs) > 0
        or len(input_bundle.evidence_ids) > 0
        or len(input_bundle.tool_result_ids) > 0
        or len(input_bundle.artifact_refs) > 0
    )

    # --- Resolve final status — precedence: blocked > needs_review > incomplete > recorded > unknown ---
    status: ResearchRunMemoryStatus
    if blocked:
        status = "blocked"
    elif review_required:
        if missing_important and not dp_present and not rr_present:
            status = "incomplete"
        else:
            status = "needs_review"
    elif has_refs:
        status = "recorded"
    else:
        status = "unknown"

    return status, review_required, blocked, warnings


# ---------------------------------------------------------------------------
# Helper: event log construction
# ---------------------------------------------------------------------------

def build_memory_event(
    event_type: MemoryEventType,
    description: str,
    memory_id: str,
    created_at: Optional[str] = None,
    actor: MemoryActorType = "system",
    source_refs: Optional[list[MemorySourceRef]] = None,
    metadata: Optional[dict[str, Any]] = None,
    warnings: Optional[list[str]] = None,
) -> MemoryEvent:
    """Build a single MemoryEvent with a deterministic event_id."""
    ts = created_at or _DETERMINISTIC_TIMESTAMP_DEFAULT
    event_id = make_memory_event_id(
        memory_id=memory_id,
        event_type=event_type,
        created_at=ts,
    )
    return MemoryEvent(
        event_id=event_id,
        event_type=event_type,
        created_at=ts,
        actor=actor,
        description=description,
        source_refs=source_refs or [],
        metadata=metadata or {},
        warnings=warnings or [],
    )


def _build_initial_event_log(
    input_bundle: ResearchRunMemoryInputBundle,
    memory_id: str,
    status: ResearchRunMemoryStatus,
    review_required: bool,
    blocked: bool,
    created_at: str,
) -> list[MemoryEvent]:
    """Build the initial event log for a new ResearchRunMemoryRecord."""
    events: list[MemoryEvent] = []

    # Creation event
    create_event = build_memory_event(
        event_type="research_run_created",
        description=(
            f"Research run memory record created for target '{input_bundle.target}' "
            f"(run_id={input_bundle.run_id!r}, status={status!r})."
        ),
        memory_id=memory_id,
        created_at=created_at,
        actor="system",
        source_refs=list(input_bundle.source_refs),
        metadata={"run_id": input_bundle.run_id, "target": input_bundle.target},
    )
    events.append(create_event)

    # Review requested event if applicable
    if review_required or blocked:
        review_event = build_memory_event(
            event_type="review_requested",
            description=(
                "Research run memory requires review — "
                + ("blocked by human review or decision packet. " if blocked else "")
                + ("review_required signal detected." if review_required and not blocked else "")
            ).strip(),
            memory_id=memory_id,
            created_at=created_at,
            actor="system",
        )
        events.append(review_event)

    return events


# ---------------------------------------------------------------------------
# Helper: summary builder
# ---------------------------------------------------------------------------

def summarize_research_run_memory(
    input_bundle: ResearchRunMemoryInputBundle,
    status: ResearchRunMemoryStatus,
    source_refs: list[MemorySourceRef],
    evidence_ids: list[str],
    tool_result_ids: list[str],
    review_required: bool,
    blocked: bool,
    warnings: list[str],
) -> ResearchRunMemorySummary:
    """Build a ResearchRunMemorySummary from resolved run components."""
    artifact_refs = [r for r in input_bundle.artifact_refs if r and r.strip()]

    # Derive artifact presence from input bundle
    has_dp = input_bundle.decision_packet is not None
    has_hr = input_bundle.human_review_report is not None
    has_ei = input_bundle.event_intelligence_report is not None
    has_tp = input_bundle.trade_plan_report is not None
    has_alloc = input_bundle.allocation_report is not None
    has_opt = input_bundle.option_expression_report is not None
    has_ib = input_bundle.integration_boundary_report is not None

    top_warnings = warnings[:5]

    return ResearchRunMemorySummary(
        run_id=input_bundle.run_id,
        target=input_bundle.target,
        status=status,
        source_count=len(source_refs),
        evidence_count=len(evidence_ids),
        tool_result_count=len(tool_result_ids),
        artifact_count=len(artifact_refs),
        has_decision_packet=has_dp,
        has_human_review=has_hr,
        has_event_intelligence=has_ei,
        has_trade_plan=has_tp,
        has_allocation=has_alloc,
        has_option_expression=has_opt,
        has_integration_boundary=has_ib,
        review_required=review_required,
        blocked=blocked,
        top_warnings=top_warnings,
        approved_for_execution=False,
    )


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_research_run_memory_record(
    input_bundle: ResearchRunMemoryInputBundle,
    created_at: Optional[str] = None,
    updated_at: Optional[str] = None,
) -> ResearchRunMemoryRecord:
    """
    Build a ResearchRunMemoryRecord from an input bundle.

    Timestamp resolution priority (highest wins):
      1. explicit created_at / updated_at arguments;
      2. input_bundle.created_at if present;
      3. input_bundle.as_of if present;
      4. _DETERMINISTIC_TIMESTAMP_DEFAULT ("1970-01-01T00:00:00Z").

    Identical inputs without explicit timestamps always produce identical output.
    If only created_at is resolved, updated_at defaults to created_at.
    Inputs are never mutated.
    approved_for_execution is always False.
    Missing optional artifacts produce warnings, not crashes.
    """
    ts = (
        created_at
        or input_bundle.created_at
        or input_bundle.as_of
        or _DETERMINISTIC_TIMESTAMP_DEFAULT
    )
    updated = updated_at or ts

    as_of = input_bundle.as_of or ts

    memory_id = make_research_run_memory_id(
        run_id=input_bundle.run_id,
        target=input_bundle.target,
        as_of=as_of,
    )

    source_refs = collect_memory_source_refs(input_bundle)
    evidence_ids = collect_memory_evidence_ids(input_bundle, source_refs)
    tool_result_ids = collect_memory_tool_result_ids(input_bundle, source_refs)

    status, review_required, blocked, det_warnings = determine_research_run_memory_status(
        input_bundle=input_bundle,
        source_refs=source_refs,
    )

    all_warnings = list(input_bundle.warnings) + det_warnings

    summary = summarize_research_run_memory(
        input_bundle=input_bundle,
        status=status,
        source_refs=source_refs,
        evidence_ids=evidence_ids,
        tool_result_ids=tool_result_ids,
        review_required=review_required,
        blocked=blocked,
        warnings=all_warnings,
    )

    event_log = _build_initial_event_log(
        input_bundle=input_bundle,
        memory_id=memory_id,
        status=status,
        review_required=review_required,
        blocked=blocked,
        created_at=ts,
    )

    return ResearchRunMemoryRecord(
        memory_id=memory_id,
        run_id=input_bundle.run_id,
        target=input_bundle.target,
        status=status,
        summary=summary,
        source_refs=source_refs,
        evidence_ids=evidence_ids,
        tool_result_ids=tool_result_ids,
        artifact_refs=[r for r in input_bundle.artifact_refs if r and r.strip()],
        event_log=event_log,
        created_at=ts,
        updated_at=updated,
        calculation_version=_CALCULATION_VERSION,
        warnings=all_warnings,
        approved_for_execution=False,
    )


# ---------------------------------------------------------------------------
# Helper: index entry builder
# ---------------------------------------------------------------------------

def build_memory_index_entry(
    record: ResearchRunMemoryRecord,
    tags: Optional[list[str]] = None,
) -> ResearchRunMemoryIndexEntry:
    """Build a ResearchRunMemoryIndexEntry from a ResearchRunMemoryRecord."""
    return ResearchRunMemoryIndexEntry(
        memory_id=record.memory_id,
        run_id=record.run_id,
        target=record.target,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        source_count=record.summary.source_count,
        evidence_count=record.summary.evidence_count,
        review_required=record.summary.review_required,
        blocked=record.summary.blocked,
        tags=list(tags or []),
    )


# ---------------------------------------------------------------------------
# ToolResult adapter
# ---------------------------------------------------------------------------

def research_run_memory_tool_result_from_record(
    record: ResearchRunMemoryRecord,
) -> ToolResult:
    """
    Wrap a ResearchRunMemoryRecord as a ToolResult for evidence-store integration.

    Stable tool name: "research_run_memory_record".
    Deterministic evidence_id derived from record content.
    No fake evidence; no execution implication; no persistence side effect.
    This adapter does NOT look like an order ticket or persistence receipt.
    """
    outputs = {
        "memory_id": record.memory_id,
        "run_id": record.run_id,
        "target": record.target,
        "status": record.status,
        # Full record included so evidence_id is sensitive to source_refs,
        # event_log, warnings, and artifact_refs — not just summary counts.
        "record": record.model_dump(),
        "summary": record.summary.model_dump(),
        "source_count": record.summary.source_count,
        "evidence_count": record.summary.evidence_count,
        "tool_result_count": record.summary.tool_result_count,
        "artifact_count": record.summary.artifact_count,
        "review_required": record.summary.review_required,
        "blocked": record.summary.blocked,
        "calculation_version": record.calculation_version,
        "approved_for_execution": False,
    }

    evidence_id = make_evidence_id(
        run_id=record.run_id,
        tool_name=_RESEARCH_MEMORY_TOOL_NAME,
        target=record.target,
        metric_group=_RESEARCH_MEMORY_METRIC_GROUP,
        payload=outputs,
    )

    return ToolResult(
        tool_name=_RESEARCH_MEMORY_TOOL_NAME,
        run_id=record.run_id,
        ticker=record.target if record.target else None,
        evidence_id=evidence_id,
        inputs={"run_id": record.run_id, "target": record.target},
        outputs=outputs,
        description=(
            f"ResearchRunMemoryRecord for {record.target} "
            f"(run_id={record.run_id!r}, status={record.status!r})."
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Literal type aliases
    "MemoryActorType",
    "MemoryEventType",
    "MemoryRecordStatus",
    "ResearchRunMemorySourceType",
    "ResearchRunMemoryStatus",
    # Models
    "MemoryEvent",
    "MemorySourceRef",
    "ResearchRunMemoryIndexEntry",
    "ResearchRunMemoryInputBundle",
    "ResearchRunMemoryRecord",
    "ResearchRunMemorySummary",
    # Helpers
    "build_memory_event",
    "build_memory_index_entry",
    "build_research_run_memory_record",
    "collect_memory_evidence_ids",
    "collect_memory_source_refs",
    "collect_memory_tool_result_ids",
    "determine_research_run_memory_status",
    "make_memory_event_id",
    "make_research_run_memory_id",
    "research_run_memory_tool_result_from_record",
    "summarize_research_run_memory",
]
