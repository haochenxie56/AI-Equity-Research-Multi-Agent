"""
lib/reliability/thesis_memory.py

Phase 4M-B: Thesis Memory by Horizon.

Design principles:
  - Standalone, deterministic, offline/mock-only.
  - No live LLM calls, no live data fetching, no app integration.
  - No database writes, no file persistence, no vector store.
  - No broker / order / execution behavior.
  - No pathway that can set approved_for_execution = True.
  - Defines memory records and helper functions only.
  - Consumes typed research artifacts from prior phases via source IDs / evidence IDs.
  - Produces structured HorizonThesisMemoryRecord and ThesisMemoryReport objects
    for auditable thesis-trail preservation by investment horizon.
  - Missing optional prior artifacts produce warnings, not crashes.
  - Does NOT import from app.py, pages/*, lib/llm_orchestrator.py, or any
    live workflow module.
  - Does NOT produce investment advice, buy/sell recommendations, or
    individual security recommendations.
  - approved_for_execution is ALWAYS False. No pathway to set it True exists.

Status precedence (report level):
  blocked > needs_review > invalidated > active > archived > unknown

  - blocked      — human review blocked in input_bundle, OR any thesis is blocked
  - needs_review — any thesis is needs_review
  - invalidated  — any thesis is invalidated (absent blocked / needs_review)
  - active       — all primary theses are active
  - archived     — all theses are archived
  - unknown      — no theses, or only superseded / unknown statuses

Single-thesis status precedence:
  initial_status override > blocked > needs_review > active

Relationship to Roadmap v4 Phase 4:
  - This module continues the Roadmap Phase 4 Memory + Human Feedback mainline.
  - Phase 4M-A (research_memory.py) is the prior subphase.
  - Phase 4A (integration_boundary.py) remains accepted early infrastructure
    and is NOT this memory mainline.
  - Future subphases: Catalyst Memory, Allocation Decision Memory,
    Option Trade Plan Memory, Human Feedback Layer, Agent Evaluation.

See docs/reliability_phase_4m_thesis_memory.md for design.

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
# Literal type aliases
# ---------------------------------------------------------------------------

ThesisMemoryStatus = Literal[
    "unknown",
    "active",
    "needs_review",
    "invalidated",
    "superseded",
    "archived",
    "blocked",
]

ThesisHorizon = Literal[
    "short",
    "medium",
    "long",
    "multi_horizon",
    "unknown",
]

ThesisDirection = Literal[
    "bullish",
    "bearish",
    "neutral",
    "mixed",
    "unknown",
]

ThesisConfidence = Literal[
    "low",
    "medium",
    "high",
    "unknown",
]

ThesisInvalidationType = Literal[
    "price_level",
    "fundamental",
    "macro",
    "earnings",
    "catalyst",
    "news",
    "estimate_revision",
    "technical",
    "risk_limit",
    "time_based",
    "other",
    "unknown",
]

ThesisMemoryEventType = Literal[
    "thesis_created",
    "thesis_updated",
    "thesis_review_requested",
    "thesis_invalidated",
    "thesis_superseded",
    "thesis_archived",
    "human_feedback_added",
    "outcome_observed",
    "unknown",
]

ThesisAssumptionImportance = Literal[
    "low",
    "medium",
    "high",
    "unknown",
]

ThesisActorType = Literal[
    "system",
    "user",
    "reviewer",
    "agent",
    "unknown",
]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_THESIS_MEMORY_TOOL_NAME: str = "thesis_memory_report"
_THESIS_MEMORY_METRIC_GROUP: str = "thesis_memory_report"
_CALCULATION_VERSION: str = "thesis_memory_v1"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ThesisAssumption(BaseModel):
    """
    A single trackable assumption underpinning a horizon-specific thesis.

    Scoped to a horizon and rated by importance. Missing evidence produces
    warnings but not validation errors. Does not imply execution authorization.
    """

    model_config = ConfigDict(extra="forbid")

    assumption_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    horizon: ThesisHorizon = "unknown"
    importance: ThesisAssumptionImportance = "unknown"
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "ThesisAssumption":
        for fn in ("assumption_id", "description"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class ThesisInvalidationCondition(BaseModel):
    """
    A condition that, if triggered, would invalidate or require review of a thesis.

    trigger_level is non-negative if present (e.g. a price threshold).
    trigger_date is an optional ISO-like date string.
    review_required indicates manual review is warranted if triggered.
    Does not imply execution authorization.
    """

    model_config = ConfigDict(extra="forbid")

    condition_id: str = Field(min_length=1)
    invalidation_type: ThesisInvalidationType = "unknown"
    description: str = Field(min_length=1)
    horizon: ThesisHorizon = "unknown"
    trigger_level: Optional[float] = None
    trigger_date: Optional[str] = None
    review_required: bool = False
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> "ThesisInvalidationCondition":
        for fn in ("condition_id", "description"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        if self.trigger_level is not None and self.trigger_level < 0:
            raise ValueError(
                f"trigger_level must be non-negative if present; got {self.trigger_level!r}."
            )
        return self


class ThesisMemoryEvent(BaseModel):
    """
    A timestamped event in the lifecycle of a thesis memory record.

    Events trace creation, updates, review requests, invalidation, supersession,
    human feedback, and outcome observations. Not an execution instruction or order.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: ThesisMemoryEventType = "unknown"
    created_at: str = Field(min_length=1)
    description: str = Field(min_length=1)
    actor: ThesisActorType = "system"
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "ThesisMemoryEvent":
        for fn in ("event_id", "description", "created_at"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class HorizonThesisMemoryRecord(BaseModel):
    """
    Full thesis memory record for one horizon-specific investment thesis.

    Captures thesis text, assumptions, invalidation conditions, evidence IDs,
    and an event log — without duplicating full upstream artifact content.

    memory_id optionally links this record to a ResearchRunMemoryRecord from
    Phase 4M-A.

    approved_for_execution is ALWAYS False. This record is a research audit
    artifact only and does not constitute investment advice or authorize any
    form of execution.

    No persistence, database write, vector store, or broker integration is
    introduced by this model.
    """

    model_config = ConfigDict(extra="forbid")

    thesis_id: str = Field(min_length=1)
    run_id: Optional[str] = None
    memory_id: Optional[str] = None
    target: str = Field(min_length=1)
    horizon: ThesisHorizon = "unknown"
    direction: ThesisDirection = "unknown"
    status: ThesisMemoryStatus = "unknown"
    confidence: ThesisConfidence = "unknown"
    thesis_text: str = Field(min_length=1)
    assumptions: list[ThesisAssumption] = Field(default_factory=list)
    invalidation_conditions: list[ThesisInvalidationCondition] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    event_log: list[ThesisMemoryEvent] = Field(default_factory=list)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    calculation_version: str = _CALCULATION_VERSION
    warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "HorizonThesisMemoryRecord":
        for fn in ("thesis_id", "target", "thesis_text", "created_at", "updated_at"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "HorizonThesisMemoryRecord":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-B. "
                "This layer does not authorize execution."
            )
        return self


class ThesisMemoryInputBundle(BaseModel):
    """
    Input bundle for building a thesis memory report from accepted artifacts.

    All prior artifact fields are optional (Any) to avoid hard cross-module
    dependencies at import time. Only source_ids, evidence_ids, and status
    attributes are read by helpers.

    Missing optional artifacts produce warnings, not crashes.
    Does not contain or imply any execution authorization.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    target: str = Field(min_length=1)
    run_id: Optional[str] = None
    memory_id: Optional[str] = None
    as_of: Optional[str] = None

    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)

    research_run_memory_record: Optional[Any] = None
    horizon_synthesis: Optional[Any] = None
    debate_report: Optional[Any] = None
    decision_packet: Optional[Any] = None
    event_intelligence_report: Optional[Any] = None
    trade_plan_report: Optional[Any] = None
    allocation_report: Optional[Any] = None
    option_expression_report: Optional[Any] = None
    human_review_report: Optional[Any] = None

    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "ThesisMemoryInputBundle":
        if not self.target.strip():
            raise ValueError("'target' must not be whitespace-only.")
        return self


class ThesisMemorySummary(BaseModel):
    """
    Deterministic summary of a ThesisMemoryReport.

    Aggregates counts and coverage from all thesis records.
    approved_for_execution is always False.
    """

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    status: ThesisMemoryStatus = "unknown"
    thesis_count: int = 0
    active_count: int = 0
    needs_review_count: int = 0
    invalidated_count: int = 0
    superseded_count: int = 0
    archived_count: int = 0
    horizons_covered: list[str] = Field(default_factory=list)
    direction_counts: dict[str, int] = Field(default_factory=dict)
    high_confidence_count: int = 0
    invalidation_condition_count: int = 0
    review_required_count: int = 0
    top_warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "ThesisMemorySummary":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-B. "
                "This layer does not authorize execution."
            )
        return self


class ThesisMemoryReport(BaseModel):
    """
    Full thesis memory report for all horizon-specific thesis records for a target.

    Aggregates thesis memory records, evidence IDs, source IDs, artifact refs,
    and a summary. Does not duplicate full upstream artifact content.

    run_id is optional; derived from input_bundle.run_id when available.

    approved_for_execution is ALWAYS False. This report is a research audit
    artifact only and does not constitute investment advice or authorize any
    form of execution.

    No persistence, database write, vector store, or broker integration is
    introduced by this model.
    """

    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    run_id: Optional[str] = None
    status: ThesisMemoryStatus = "unknown"
    theses: list[HorizonThesisMemoryRecord] = Field(default_factory=list)
    summary: ThesisMemorySummary
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    calculation_version: str = _CALCULATION_VERSION
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "ThesisMemoryReport":
        for fn in ("report_id", "target", "created_at", "updated_at"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "ThesisMemoryReport":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-B. "
                "This layer does not authorize execution."
            )
        return self


# ---------------------------------------------------------------------------
# Helper: deterministic ID generators
# ---------------------------------------------------------------------------

def make_thesis_id(
    target: str,
    horizon: str,
    as_of: str,
    run_id: Optional[str] = None,
) -> str:
    """Return a deterministic stable hash ID for a HorizonThesisMemoryRecord."""
    payload: dict[str, Any] = {"target": target, "horizon": horizon, "as_of": as_of}
    if run_id:
        payload["run_id"] = run_id
    h = stable_hash_payload(payload, length=16)
    return f"thesis_{h}"


def make_thesis_memory_event_id(
    thesis_id: str,
    event_type: str,
    created_at: str,
) -> str:
    """Return a deterministic stable hash ID for a ThesisMemoryEvent."""
    payload = {"thesis_id": thesis_id, "event_type": event_type, "created_at": created_at}
    h = stable_hash_payload(payload, length=12)
    return f"tevt_{h}"


def make_thesis_memory_report_id(
    target: str,
    as_of: str,
    run_id: Optional[str] = None,
) -> str:
    """Return a deterministic stable hash ID for a ThesisMemoryReport."""
    payload: dict[str, Any] = {"target": target, "as_of": as_of}
    if run_id:
        payload["run_id"] = run_id
    h = stable_hash_payload(payload, length=16)
    return f"trep_{h}"


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


def _determine_single_thesis_status(
    input_bundle: Optional[ThesisMemoryInputBundle],
    invalidation_conditions: list[ThesisInvalidationCondition],
    initial_status: Optional[ThesisMemoryStatus] = None,
) -> tuple[ThesisMemoryStatus, list[str]]:
    """
    Determine the status for a single HorizonThesisMemoryRecord.

    Priority:
      initial_status override > blocked (human review blocked) >
      needs_review (review_required conditions or blocked decision_packet) >
      active (clean default)

    Returns (status, warnings).
    initial_status=None means auto-determine; any explicit value overrides.
    """
    warnings: list[str] = []

    if initial_status is not None:
        return initial_status, warnings

    hrr = getattr(input_bundle, "human_review_report", None) if input_bundle else None
    if hrr is not None:
        hr_status = str(getattr(hrr, "status", "unknown"))
        if hr_status == "blocked":
            warnings.append(
                "Human review report is blocked — thesis status set to blocked."
            )
            return "blocked", warnings

    review_required_conditions = [ic for ic in invalidation_conditions if ic.review_required]
    if review_required_conditions:
        warnings.append(
            f"{len(review_required_conditions)} invalidation condition(s) require review "
            "— thesis status set to needs_review."
        )
        return "needs_review", warnings

    dp = getattr(input_bundle, "decision_packet", None) if input_bundle else None
    if dp is not None:
        dp_status = str(getattr(dp, "status", "unknown"))
        if dp_status == "blocked":
            warnings.append(
                "Decision packet is blocked — thesis status set to needs_review."
            )
            return "needs_review", warnings

    return "active", warnings


# ---------------------------------------------------------------------------
# Helper: event builder
# ---------------------------------------------------------------------------

def build_thesis_memory_event(
    event_type: ThesisMemoryEventType,
    description: str,
    thesis_id: str,
    created_at: Optional[str] = None,
    actor: ThesisActorType = "system",
    source_ids: Optional[list[str]] = None,
    evidence_ids: Optional[list[str]] = None,
    metadata: Optional[dict[str, Any]] = None,
    warnings: Optional[list[str]] = None,
) -> ThesisMemoryEvent:
    """Build a single ThesisMemoryEvent with a deterministic event_id."""
    ts = created_at or _DETERMINISTIC_TIMESTAMP_DEFAULT
    event_id = make_thesis_memory_event_id(
        thesis_id=thesis_id,
        event_type=event_type,
        created_at=ts,
    )
    return ThesisMemoryEvent(
        event_id=event_id,
        event_type=event_type,
        created_at=ts,
        description=description,
        actor=actor,
        source_ids=list(source_ids or []),
        evidence_ids=list(evidence_ids or []),
        metadata=dict(metadata or {}),
        warnings=list(warnings or []),
    )


# ---------------------------------------------------------------------------
# Helper: report-level status determination
# ---------------------------------------------------------------------------

def determine_thesis_memory_status(
    theses: list[HorizonThesisMemoryRecord],
    input_bundle: Optional[ThesisMemoryInputBundle] = None,
) -> tuple[ThesisMemoryStatus, list[str]]:
    """
    Determine the overall ThesisMemoryStatus for a ThesisMemoryReport.

    Precedence: blocked > needs_review > invalidated > active > archived > unknown

    - blocked:      human review blocked in input_bundle, OR any thesis is blocked.
    - needs_review: any thesis has status needs_review.
    - invalidated:  any thesis has status invalidated (absent blocked / needs_review).
    - active:       all primary theses are active (some may be archived / superseded).
    - archived:     all theses are archived.
    - unknown:      no theses, or only superseded / unknown statuses.

    Returns (status, warnings). Inputs are never mutated.
    """
    warnings: list[str] = []

    hrr = getattr(input_bundle, "human_review_report", None) if input_bundle else None
    if hrr is not None:
        hr_status = str(getattr(hrr, "status", "unknown"))
        if hr_status == "blocked":
            warnings.append(
                "Human review report is blocked — thesis memory report status set to blocked."
            )
            return "blocked", warnings

    if not theses:
        warnings.append("No theses provided — report status is unknown.")
        return "unknown", warnings

    statuses = [t.status for t in theses]

    if "blocked" in statuses:
        n = statuses.count("blocked")
        warnings.append(f"{n} thesis/theses are blocked.")
        return "blocked", warnings

    if "needs_review" in statuses:
        n = statuses.count("needs_review")
        warnings.append(f"{n} thesis/theses require review.")
        return "needs_review", warnings

    if "invalidated" in statuses:
        n = statuses.count("invalidated")
        warnings.append(f"{n} thesis/theses are invalidated.")
        return "invalidated", warnings

    primary_statuses = [s for s in statuses if s not in ("archived", "unknown", "superseded")]
    if not primary_statuses:
        if all(s == "archived" for s in statuses):
            return "archived", warnings
        return "unknown", warnings

    if all(s == "active" for s in primary_statuses):
        return "active", warnings

    return "unknown", warnings


# ---------------------------------------------------------------------------
# Helper: ID / ref collection
# ---------------------------------------------------------------------------

def collect_thesis_memory_source_ids(
    input_bundle: ThesisMemoryInputBundle,
    theses: Optional[list[HorizonThesisMemoryRecord]] = None,
) -> list[str]:
    """
    Collect and deduplicate source IDs from input_bundle and theses.

    Auto-detects IDs from optional duck-typed upstream artifacts.
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
        "horizon_synthesis",
        "debate_report",
        "decision_packet",
        "event_intelligence_report",
        "trade_plan_report",
        "allocation_report",
        "option_expression_report",
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

    if theses:
        for thesis in theses:
            for sid in thesis.source_ids:
                _add(sid)

    return result


def collect_thesis_memory_evidence_ids(
    input_bundle: ThesisMemoryInputBundle,
    theses: Optional[list[HorizonThesisMemoryRecord]] = None,
) -> list[str]:
    """
    Collect and deduplicate evidence IDs from input_bundle, theses, assumptions,
    and invalidation conditions.

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

    if theses:
        for thesis in theses:
            for eid in thesis.evidence_ids:
                _add(eid)
            for assumption in thesis.assumptions:
                for eid in assumption.evidence_ids:
                    _add(eid)
            for condition in thesis.invalidation_conditions:
                for eid in condition.evidence_ids:
                    _add(eid)

    return result


def collect_thesis_memory_artifact_refs(
    input_bundle: ThesisMemoryInputBundle,
    theses: Optional[list[HorizonThesisMemoryRecord]] = None,
) -> list[str]:
    """
    Collect and deduplicate artifact refs from input_bundle and theses.

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

    if theses:
        for thesis in theses:
            for ref in thesis.artifact_refs:
                _add(ref)

    return result


# ---------------------------------------------------------------------------
# Helper: summary builder
# ---------------------------------------------------------------------------

def summarize_thesis_memory(
    target: str,
    status: ThesisMemoryStatus,
    theses: list[HorizonThesisMemoryRecord],
    warnings: list[str],
) -> ThesisMemorySummary:
    """Build a ThesisMemorySummary from resolved thesis memory components."""
    thesis_count = len(theses)
    active_count = sum(1 for t in theses if t.status == "active")
    needs_review_count = sum(1 for t in theses if t.status == "needs_review")
    invalidated_count = sum(1 for t in theses if t.status == "invalidated")
    superseded_count = sum(1 for t in theses if t.status == "superseded")
    archived_count = sum(1 for t in theses if t.status == "archived")

    horizons_covered = sorted(set(t.horizon for t in theses))

    direction_counts: dict[str, int] = {}
    for t in theses:
        direction_counts[t.direction] = direction_counts.get(t.direction, 0) + 1

    high_confidence_count = sum(1 for t in theses if t.confidence == "high")
    invalidation_condition_count = sum(len(t.invalidation_conditions) for t in theses)
    review_required_count = sum(
        1 for t in theses
        for ic in t.invalidation_conditions
        if ic.review_required
    )

    top_warnings = warnings[:5]

    return ThesisMemorySummary(
        target=target,
        status=status,
        thesis_count=thesis_count,
        active_count=active_count,
        needs_review_count=needs_review_count,
        invalidated_count=invalidated_count,
        superseded_count=superseded_count,
        archived_count=archived_count,
        horizons_covered=horizons_covered,
        direction_counts=direction_counts,
        high_confidence_count=high_confidence_count,
        invalidation_condition_count=invalidation_condition_count,
        review_required_count=review_required_count,
        top_warnings=top_warnings,
        approved_for_execution=False,
    )


# ---------------------------------------------------------------------------
# Main builders
# ---------------------------------------------------------------------------

def build_horizon_thesis_memory_record(
    target: str,
    thesis_text: str,
    horizon: ThesisHorizon = "unknown",
    direction: ThesisDirection = "unknown",
    confidence: ThesisConfidence = "unknown",
    assumptions: Optional[list[ThesisAssumption]] = None,
    invalidation_conditions: Optional[list[ThesisInvalidationCondition]] = None,
    run_id: Optional[str] = None,
    memory_id: Optional[str] = None,
    source_ids: Optional[list[str]] = None,
    evidence_ids: Optional[list[str]] = None,
    artifact_refs: Optional[list[str]] = None,
    created_at: Optional[str] = None,
    updated_at: Optional[str] = None,
    initial_status: Optional[ThesisMemoryStatus] = None,
    input_bundle: Optional[ThesisMemoryInputBundle] = None,
    extra_warnings: Optional[list[str]] = None,
) -> HorizonThesisMemoryRecord:
    """
    Build a HorizonThesisMemoryRecord from thesis parameters and an optional input bundle.

    Timestamp resolution priority (highest wins):
      1. explicit created_at argument;
      2. input_bundle.as_of if present;
      3. _DETERMINISTIC_TIMESTAMP_DEFAULT ("1970-01-01T00:00:00Z").

    If only created_at is resolved, updated_at defaults to created_at.
    Identical inputs without explicit timestamps always produce identical output.
    Inputs are never mutated.
    approved_for_execution is always False.

    initial_status overrides auto-determined status when provided (e.g. to mark
    a thesis as invalidated, superseded, or archived from prior knowledge).

    Missing optional upstream artifacts produce warnings, not crashes.
    """
    ts = (
        created_at
        or (input_bundle.as_of if input_bundle else None)
        or _DETERMINISTIC_TIMESTAMP_DEFAULT
    )
    updated = updated_at or ts

    as_of = (input_bundle.as_of if input_bundle else None) or ts
    effective_run_id = run_id or (input_bundle.run_id if input_bundle else None)
    effective_memory_id = memory_id or (input_bundle.memory_id if input_bundle else None)

    thesis_id = make_thesis_id(
        target=target,
        horizon=horizon,
        as_of=as_of,
        run_id=effective_run_id,
    )

    _assumptions = list(assumptions or [])
    _invalidation_conditions = list(invalidation_conditions or [])
    _source_ids = _dedup_list(list(source_ids or []))
    _evidence_ids = _dedup_list(list(evidence_ids or []))
    _artifact_refs = _dedup_list([r for r in (artifact_refs or []) if r and r.strip()])

    status, status_warnings = _determine_single_thesis_status(
        input_bundle=input_bundle,
        invalidation_conditions=_invalidation_conditions,
        initial_status=initial_status,
    )

    bundle_warnings = list(input_bundle.warnings if input_bundle else [])

    missing_warnings: list[str] = []
    if input_bundle is not None:
        if input_bundle.horizon_synthesis is None:
            missing_warnings.append(
                "Missing optional upstream artifact: horizon_synthesis."
            )
        if input_bundle.debate_report is None:
            missing_warnings.append(
                "Missing optional upstream artifact: debate_report."
            )
        if input_bundle.decision_packet is None:
            missing_warnings.append(
                "Missing optional upstream artifact: decision_packet."
            )

    all_warnings = bundle_warnings + status_warnings + missing_warnings + list(extra_warnings or [])

    creation_event = build_thesis_memory_event(
        event_type="thesis_created",
        description=(
            f"Thesis memory record created for target '{target}' "
            f"(horizon={horizon!r}, direction={direction!r}, status={status!r})."
        ),
        thesis_id=thesis_id,
        created_at=ts,
        actor="system",
        source_ids=_source_ids,
        evidence_ids=_evidence_ids,
        metadata={"target": target, "horizon": horizon},
    )
    event_log = [creation_event]

    if status in ("blocked", "needs_review"):
        review_event = build_thesis_memory_event(
            event_type="thesis_review_requested",
            description=f"Thesis requires review — status is '{status}'.",
            thesis_id=thesis_id,
            created_at=ts,
            actor="system",
        )
        event_log.append(review_event)

    return HorizonThesisMemoryRecord(
        thesis_id=thesis_id,
        run_id=effective_run_id,
        memory_id=effective_memory_id,
        target=target,
        horizon=horizon,
        direction=direction,
        status=status,
        confidence=confidence,
        thesis_text=thesis_text,
        assumptions=_assumptions,
        invalidation_conditions=_invalidation_conditions,
        source_ids=_source_ids,
        evidence_ids=_evidence_ids,
        artifact_refs=_artifact_refs,
        event_log=event_log,
        created_at=ts,
        updated_at=updated,
        calculation_version=_CALCULATION_VERSION,
        warnings=all_warnings,
        approved_for_execution=False,
    )


def build_thesis_memory_report(
    input_bundle: ThesisMemoryInputBundle,
    theses: Optional[list[HorizonThesisMemoryRecord]] = None,
    created_at: Optional[str] = None,
    updated_at: Optional[str] = None,
) -> ThesisMemoryReport:
    """
    Build a ThesisMemoryReport from an input bundle and a list of thesis records.

    Timestamp resolution priority (highest wins):
      1. explicit created_at argument;
      2. input_bundle.as_of if present;
      3. _DETERMINISTIC_TIMESTAMP_DEFAULT ("1970-01-01T00:00:00Z").

    If only created_at is resolved, updated_at defaults to created_at.
    Identical inputs without explicit timestamps always produce identical output.
    Inputs are never mutated.
    approved_for_execution is always False.

    An empty thesis list produces a report with status unknown and a warning.
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

    report_id = make_thesis_memory_report_id(
        target=input_bundle.target,
        as_of=as_of,
        run_id=run_id,
    )

    _theses = list(theses or [])

    status, status_warnings = determine_thesis_memory_status(
        theses=_theses,
        input_bundle=input_bundle,
    )

    missing_warnings: list[str] = []
    if input_bundle.horizon_synthesis is None:
        missing_warnings.append("Missing optional upstream artifact: horizon_synthesis.")
    if input_bundle.debate_report is None:
        missing_warnings.append("Missing optional upstream artifact: debate_report.")
    if input_bundle.decision_packet is None:
        missing_warnings.append("Missing optional upstream artifact: decision_packet.")
    if input_bundle.human_review_report is None:
        missing_warnings.append("Missing optional upstream artifact: human_review_report.")

    all_warnings = list(input_bundle.warnings) + status_warnings + missing_warnings

    source_ids = collect_thesis_memory_source_ids(input_bundle, _theses)
    evidence_ids = collect_thesis_memory_evidence_ids(input_bundle, _theses)
    artifact_refs = collect_thesis_memory_artifact_refs(input_bundle, _theses)

    summary = summarize_thesis_memory(
        target=input_bundle.target,
        status=status,
        theses=_theses,
        warnings=all_warnings,
    )

    return ThesisMemoryReport(
        report_id=report_id,
        target=input_bundle.target,
        run_id=run_id,
        status=status,
        theses=_theses,
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

def thesis_memory_tool_result_from_report(
    report: ThesisMemoryReport,
    run_id: Optional[str] = None,
) -> ToolResult:
    """
    Wrap a ThesisMemoryReport as a ToolResult for evidence-store integration.

    Stable tool name: "thesis_memory_report".
    Deterministic evidence_id derived from report content (including full theses,
    thesis_text, assumptions, and invalidation_conditions).
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
        "thesis_count": report.summary.thesis_count,
        "active_count": report.summary.active_count,
        "needs_review_count": report.summary.needs_review_count,
        "invalidated_count": report.summary.invalidated_count,
        "calculation_version": report.calculation_version,
        "approved_for_execution": False,
    }

    evidence_id = make_evidence_id(
        run_id=_run_id,
        tool_name=_THESIS_MEMORY_TOOL_NAME,
        target=report.target,
        metric_group=_THESIS_MEMORY_METRIC_GROUP,
        payload=outputs,
    )

    return ToolResult(
        tool_name=_THESIS_MEMORY_TOOL_NAME,
        run_id=_run_id,
        ticker=report.target if report.target else None,
        evidence_id=evidence_id,
        inputs={"target": report.target, "report_id": report.report_id},
        outputs=outputs,
        description=(
            f"ThesisMemoryReport for {report.target} "
            f"(report_id={report.report_id!r}, status={report.status!r}, "
            f"theses={report.summary.thesis_count})."
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Literal type aliases
    "ThesisActorType",
    "ThesisAssumptionImportance",
    "ThesisConfidence",
    "ThesisDirection",
    "ThesisHorizon",
    "ThesisInvalidationType",
    "ThesisMemoryEventType",
    "ThesisMemoryStatus",
    # Models
    "ThesisAssumption",
    "ThesisInvalidationCondition",
    "ThesisMemoryEvent",
    "HorizonThesisMemoryRecord",
    "ThesisMemoryInputBundle",
    "ThesisMemorySummary",
    "ThesisMemoryReport",
    # Helpers
    "make_thesis_id",
    "make_thesis_memory_event_id",
    "make_thesis_memory_report_id",
    "build_thesis_memory_event",
    "determine_thesis_memory_status",
    "collect_thesis_memory_source_ids",
    "collect_thesis_memory_evidence_ids",
    "collect_thesis_memory_artifact_refs",
    "summarize_thesis_memory",
    "build_horizon_thesis_memory_record",
    "build_thesis_memory_report",
    "thesis_memory_tool_result_from_report",
]
