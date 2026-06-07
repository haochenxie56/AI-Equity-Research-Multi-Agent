"""
lib/reliability/event_memory.py

Phase 4M-C: Catalyst / News / Earnings Memory.

Design principles:
  - Standalone, deterministic, offline/mock-only.
  - No live LLM calls, no live data fetching, no app integration.
  - No database writes, no file persistence, no vector store.
  - No broker / order / execution behavior.
  - No pathway that can set approved_for_execution = True.
  - Defines memory records and helper functions only.
  - Records catalyst, news, earnings, guidance, estimate revision, and
    regulatory / product / management / legal / macro events.
  - Consumes typed research artifacts from prior phases via source IDs /
    evidence IDs without duplicating full upstream artifact content.
  - Missing optional prior artifacts produce warnings, not crashes.
  - Does NOT import from app.py, pages/*, lib/llm_orchestrator.py, or any
    live workflow module.
  - Does NOT produce investment advice, buy/sell recommendations, or
    individual security recommendations.
  - approved_for_execution is ALWAYS False. No pathway to set it True exists.
  - No Finnhub / news API / earnings API calls.

Report-level status precedence:
  blocked > thesis_changing > needs_review > reviewed > active > archived > unknown

  - blocked       — human review blocked in input_bundle, OR any record is blocked
  - thesis_changing — any record has thesis_changing=True (absent blocked)
  - needs_review  — any record has status=needs_review, OR any high-impact unreviewed
                    event (absent blocked / thesis_changing)
  - reviewed      — all records are in reviewed status (absent above)
  - active        — clean active records with no review signals
  - archived      — all records are archived
  - unknown       — no records, or only unknown statuses

Single-record status:
  initial_status override > blocked (HRR or review_status) > thesis_changing >
  needs_review (high impact or pending review) > reviewed > active

Relationship to Roadmap v4 Phase 4:
  - Continues the Roadmap Phase 4 Memory + Human Feedback mainline.
  - Phase 4M-A (research_memory.py): Research Run Memory Schema.
  - Phase 4M-B (thesis_memory.py): Thesis Memory by Horizon.
  - Phase 3R-A (event_intelligence.py): Event Intelligence Agents Skeleton.
  - Phase 4A (integration_boundary.py): accepted early infrastructure, not memory mainline.
  - Future subphases: Allocation Decision Memory, Option Trade Plan Memory,
    Human Feedback Layer, Agent Evaluation.

See docs/reliability_phase_4m_event_memory.md for design.

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

EventMemoryStatus = Literal[
    "unknown",
    "active",
    "reviewed",
    "needs_review",
    "thesis_changing",
    "archived",
    "blocked",
]

EventMemoryType = Literal[
    "catalyst",
    "news",
    "earnings",
    "guidance",
    "estimate_revision",
    "regulatory",
    "product",
    "management",
    "legal",
    "macro",
    "other",
    "unknown",
]

EventMemoryImpactDirection = Literal[
    "positive",
    "negative",
    "mixed",
    "neutral",
    "unknown",
]

EventMemoryImpactMagnitude = Literal[
    "low",
    "medium",
    "high",
    "unknown",
]

EventMemoryReviewStatus = Literal[
    "not_required",
    "pending",
    "reviewed",
    "escalated",
    "blocked",
    "unknown",
]

EventMemoryEventType = Literal[
    "event_recorded",
    "review_requested",
    "review_completed",
    "thesis_changed",
    "market_reaction_observed",
    "human_feedback_added",
    "archived",
    "unknown",
]

EventMemoryActorType = Literal[
    "system",
    "user",
    "reviewer",
    "agent",
    "unknown",
]

EventMemorySourceType = Literal[
    "news",
    "earnings_report",
    "sec_filing",
    "analyst_note",
    "event_intelligence",
    "research_memory",
    "thesis_memory",
    "catalyst_snapshot",
    "human_review",
    "tool_result",
    "user_input",
    "unknown",
]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_EVENT_MEMORY_TOOL_NAME: str = "event_memory_report"
_EVENT_MEMORY_METRIC_GROUP: str = "event_memory_report"
_CALCULATION_VERSION: str = "event_memory_v1"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class EventMemorySourceRef(BaseModel):
    """
    A stable pointer to a source of evidence for an EventMemoryRecord.

    Stores a reference to an upstream artifact, news item, filing, or
    analyst note without duplicating full content. All fields except
    source_id are optional.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    source_type: EventMemorySourceType = "unknown"
    artifact_id: Optional[str] = None
    evidence_id: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[str] = None
    field_path: Optional[str] = None
    label: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_source_id(self) -> "EventMemorySourceRef":
        if not self.source_id.strip():
            raise ValueError(
                f"'source_id' must not be whitespace-only; got {self.source_id!r}."
            )
        return self


class EventMemoryLogEntry(BaseModel):
    """
    A timestamped lifecycle entry in the event log of an EventMemoryRecord.

    Traces creation, review requests, review completions, thesis-changing
    signals, market reaction observations, and human feedback. Not an
    execution instruction or order.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: EventMemoryEventType = "unknown"
    created_at: str = Field(min_length=1)
    actor: EventMemoryActorType = "system"
    description: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "EventMemoryLogEntry":
        for fn in ("event_id", "created_at", "description"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class EventMemoryRecord(BaseModel):
    """
    A single event memory record capturing one catalyst, news item, earnings
    event, guidance update, estimate revision, or related market event.

    memory_id optionally links to a ResearchRunMemoryRecord (Phase 4M-A).
    thesis_id optionally links to a HorizonThesisMemoryRecord (Phase 4M-B).

    approved_for_execution is ALWAYS False. This record is a research audit
    artifact only and does not constitute investment advice or authorize any
    form of execution.

    No persistence, database write, vector store, or broker integration is
    introduced by this model.
    """

    model_config = ConfigDict(extra="forbid")

    event_memory_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    run_id: Optional[str] = None
    memory_id: Optional[str] = None
    thesis_id: Optional[str] = None
    event_type: EventMemoryType = "unknown"
    status: EventMemoryStatus = "unknown"
    review_status: EventMemoryReviewStatus = "unknown"
    event_name: str = Field(min_length=1)
    event_date: Optional[str] = None
    recorded_at: str = Field(min_length=1)
    reviewed_at: Optional[str] = None
    impact_direction: EventMemoryImpactDirection = "unknown"
    impact_magnitude: EventMemoryImpactMagnitude = "unknown"
    thesis_changing: bool = False
    affected_horizons: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)
    market_reaction: Optional[str] = None
    guidance_update: Optional[str] = None
    estimate_revision_summary: Optional[str] = None
    source_refs: list[EventMemorySourceRef] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    event_log: list[EventMemoryLogEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "EventMemoryRecord":
        for fn in ("event_memory_id", "target", "event_name", "recorded_at", "summary"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "EventMemoryRecord":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-C. "
                "This layer does not authorize execution."
            )
        return self


class EventMemoryInputBundle(BaseModel):
    """
    Input bundle for building an event memory report from accepted artifacts.

    All prior artifact fields are optional (Any) to avoid hard cross-module
    dependencies at import time. Only source_ids, evidence_ids, status
    attributes, and the human_review_report are read by helpers.

    Missing optional artifacts produce warnings, not crashes.
    Does not contain or imply any execution authorization.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    target: str = Field(min_length=1)
    run_id: Optional[str] = None
    memory_id: Optional[str] = None
    thesis_id: Optional[str] = None
    as_of: Optional[str] = None

    research_run_memory_record: Optional[Any] = None
    thesis_memory_report: Optional[Any] = None
    event_intelligence_report: Optional[Any] = None
    decision_packet: Optional[Any] = None
    human_review_report: Optional[Any] = None

    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "EventMemoryInputBundle":
        if not self.target.strip():
            raise ValueError("'target' must not be whitespace-only.")
        return self


class EventMemorySummary(BaseModel):
    """
    Deterministic summary of an EventMemoryReport.

    Aggregates counts and coverage across all EventMemoryRecord objects.
    approved_for_execution is always False.
    """

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    status: EventMemoryStatus = "unknown"
    record_count: int = 0
    catalyst_count: int = 0
    news_count: int = 0
    earnings_count: int = 0
    guidance_count: int = 0
    estimate_revision_count: int = 0
    thesis_changing_count: int = 0
    needs_review_count: int = 0
    reviewed_count: int = 0
    high_impact_count: int = 0
    affected_horizons: list[str] = Field(default_factory=list)
    top_warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "EventMemorySummary":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-C. "
                "This layer does not authorize execution."
            )
        return self


class EventMemoryReport(BaseModel):
    """
    Full event memory report aggregating all event memory records for a target.

    Captures catalyst, news, earnings, guidance, estimate revision, and other
    market event records with their evidence, source refs, artifact refs, and
    a summary. Does not duplicate full upstream artifact content.

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
    status: EventMemoryStatus = "unknown"
    records: list[EventMemoryRecord] = Field(default_factory=list)
    summary: EventMemorySummary
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    calculation_version: str = _CALCULATION_VERSION
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "EventMemoryReport":
        for fn in ("report_id", "target", "created_at", "updated_at"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "EventMemoryReport":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-C. "
                "This layer does not authorize execution."
            )
        return self


# ---------------------------------------------------------------------------
# Helper: deterministic ID generators
# ---------------------------------------------------------------------------

def make_event_memory_record_id(
    target: str,
    event_name: str,
    event_type: str,
    as_of: str,
    run_id: Optional[str] = None,
) -> str:
    """Return a deterministic stable hash ID for an EventMemoryRecord."""
    payload: dict[str, Any] = {
        "target": target,
        "event_name": event_name,
        "event_type": event_type,
        "as_of": as_of,
    }
    if run_id:
        payload["run_id"] = run_id
    h = stable_hash_payload(payload, length=16)
    return f"emem_{h}"


def make_event_memory_log_entry_id(
    event_memory_id: str,
    event_type: str,
    created_at: str,
) -> str:
    """Return a deterministic stable hash ID for an EventMemoryLogEntry."""
    payload = {
        "event_memory_id": event_memory_id,
        "event_type": event_type,
        "created_at": created_at,
    }
    h = stable_hash_payload(payload, length=12)
    return f"emevt_{h}"


def make_event_memory_report_id(
    target: str,
    as_of: str,
    run_id: Optional[str] = None,
) -> str:
    """Return a deterministic stable hash ID for an EventMemoryReport."""
    payload: dict[str, Any] = {"target": target, "as_of": as_of}
    if run_id:
        payload["run_id"] = run_id
    h = stable_hash_payload(payload, length=16)
    return f"emrep_{h}"


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


def _determine_single_record_status(
    thesis_changing: bool,
    impact_magnitude: str,
    review_status: str,
    input_bundle: Optional[EventMemoryInputBundle] = None,
    initial_status: Optional[EventMemoryStatus] = None,
) -> tuple[EventMemoryStatus, list[str]]:
    """
    Determine the status for a single EventMemoryRecord.

    Priority:
      initial_status override > blocked (HRR blocked or review_status blocked) >
      thesis_changing > needs_review (high impact or pending/escalated review) >
      reviewed > active

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
                "Human review report is blocked — event memory record status set to blocked."
            )
            return "blocked", warnings

    if review_status == "blocked":
        warnings.append(
            "Review status is blocked — event memory record status set to blocked."
        )
        return "blocked", warnings

    if thesis_changing:
        if review_status in ("pending", "escalated"):
            warnings.append(
                "Thesis-changing event with pending/escalated review "
                "— record status set to needs_review."
            )
            return "needs_review", warnings
        warnings.append(
            "Thesis-changing event — record status set to thesis_changing."
        )
        return "thesis_changing", warnings

    if impact_magnitude == "high" and review_status not in ("reviewed", "not_required"):
        warnings.append(
            "High-impact event with unreviewed status — record status set to needs_review."
        )
        return "needs_review", warnings

    if review_status in ("pending", "escalated"):
        warnings.append(
            f"Review status is '{review_status}' — record status set to needs_review."
        )
        return "needs_review", warnings

    if review_status == "reviewed":
        return "reviewed", warnings

    return "active", warnings


# ---------------------------------------------------------------------------
# Helper: log entry builder
# ---------------------------------------------------------------------------

def build_event_memory_log_entry(
    event_type: EventMemoryEventType,
    description: str,
    event_memory_id: str,
    created_at: Optional[str] = None,
    actor: EventMemoryActorType = "system",
    source_ids: Optional[list[str]] = None,
    evidence_ids: Optional[list[str]] = None,
    metadata: Optional[dict[str, Any]] = None,
    warnings: Optional[list[str]] = None,
) -> EventMemoryLogEntry:
    """Build a single EventMemoryLogEntry with a deterministic event_id."""
    ts = created_at or _DETERMINISTIC_TIMESTAMP_DEFAULT
    entry_id = make_event_memory_log_entry_id(
        event_memory_id=event_memory_id,
        event_type=event_type,
        created_at=ts,
    )
    return EventMemoryLogEntry(
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

def determine_event_memory_status(
    records: list[EventMemoryRecord],
    input_bundle: Optional[EventMemoryInputBundle] = None,
) -> tuple[EventMemoryStatus, list[str]]:
    """
    Determine the overall EventMemoryStatus for an EventMemoryReport.

    Precedence: blocked > thesis_changing > needs_review > reviewed > active > archived > unknown

    - blocked:        HRR blocked in input_bundle, OR any record has status=blocked.
    - thesis_changing: any record has status=thesis_changing or thesis_changing=True.
    - needs_review:   any record has status=needs_review, OR any high-impact unreviewed record.
    - reviewed:       all records are in reviewed status (none need_review or blocked).
    - active:         records exist with no review signals or thesis_changing flags.
    - archived:       all records are archived.
    - unknown:        no records, or only unknown statuses.

    Returns (status, warnings). Inputs are never mutated.
    """
    warnings: list[str] = []

    hrr = getattr(input_bundle, "human_review_report", None) if input_bundle else None
    if hrr is not None:
        hr_status = str(getattr(hrr, "status", "unknown"))
        if hr_status == "blocked":
            warnings.append(
                "Human review report is blocked — event memory report status set to blocked."
            )
            return "blocked", warnings

    if not records:
        warnings.append("No event memory records provided — report status is unknown.")
        return "unknown", warnings

    statuses = [r.status for r in records]

    if "blocked" in statuses:
        n = statuses.count("blocked")
        warnings.append(f"{n} event memory record(s) are blocked.")
        return "blocked", warnings

    if "thesis_changing" in statuses or any(r.thesis_changing for r in records):
        n_tc = statuses.count("thesis_changing") + sum(
            1 for r in records if r.thesis_changing and r.status != "thesis_changing"
        )
        warnings.append(f"{n_tc} thesis-changing event(s) detected.")
        return "thesis_changing", warnings

    if "needs_review" in statuses:
        n = statuses.count("needs_review")
        warnings.append(f"{n} event memory record(s) require review.")
        return "needs_review", warnings

    # High-impact unreviewed records escalate to needs_review
    high_impact_unreviewed = [
        r for r in records
        if r.impact_magnitude == "high" and r.status not in ("reviewed", "archived")
    ]
    if high_impact_unreviewed:
        warnings.append(
            f"{len(high_impact_unreviewed)} high-impact event(s) are not yet reviewed."
        )
        return "needs_review", warnings

    non_archived = [s for s in statuses if s not in ("archived", "unknown")]

    if not non_archived:
        if all(s == "archived" for s in statuses):
            return "archived", warnings
        return "unknown", warnings

    if all(s == "reviewed" for s in non_archived):
        return "reviewed", warnings

    if any(s == "active" for s in non_archived):
        return "active", warnings

    return "unknown", warnings


# ---------------------------------------------------------------------------
# Helper: ID / ref collection
# ---------------------------------------------------------------------------

def collect_event_memory_source_ids(
    input_bundle: EventMemoryInputBundle,
    records: Optional[list[EventMemoryRecord]] = None,
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
        "event_intelligence_report",
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

    return result


def collect_event_memory_evidence_ids(
    input_bundle: EventMemoryInputBundle,
    records: Optional[list[EventMemoryRecord]] = None,
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

    return result


def collect_event_memory_artifact_refs(
    input_bundle: EventMemoryInputBundle,
    records: Optional[list[EventMemoryRecord]] = None,
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

    return result


# ---------------------------------------------------------------------------
# Helper: summary builder
# ---------------------------------------------------------------------------

def summarize_event_memory(
    target: str,
    status: EventMemoryStatus,
    records: list[EventMemoryRecord],
    warnings: list[str],
) -> EventMemorySummary:
    """Build an EventMemorySummary from resolved event memory components."""
    record_count = len(records)
    catalyst_count = sum(1 for r in records if r.event_type == "catalyst")
    news_count = sum(1 for r in records if r.event_type == "news")
    earnings_count = sum(1 for r in records if r.event_type == "earnings")
    guidance_count = sum(1 for r in records if r.event_type == "guidance")
    estimate_revision_count = sum(1 for r in records if r.event_type == "estimate_revision")
    thesis_changing_count = sum(1 for r in records if r.thesis_changing)
    needs_review_count = sum(1 for r in records if r.status == "needs_review")
    reviewed_count = sum(1 for r in records if r.status == "reviewed")
    high_impact_count = sum(1 for r in records if r.impact_magnitude == "high")

    all_horizons: set[str] = set()
    for r in records:
        for h in r.affected_horizons:
            if h:
                all_horizons.add(h)
    affected_horizons = sorted(all_horizons)

    top_warnings = warnings[:5]

    return EventMemorySummary(
        target=target,
        status=status,
        record_count=record_count,
        catalyst_count=catalyst_count,
        news_count=news_count,
        earnings_count=earnings_count,
        guidance_count=guidance_count,
        estimate_revision_count=estimate_revision_count,
        thesis_changing_count=thesis_changing_count,
        needs_review_count=needs_review_count,
        reviewed_count=reviewed_count,
        high_impact_count=high_impact_count,
        affected_horizons=affected_horizons,
        top_warnings=top_warnings,
        approved_for_execution=False,
    )


# ---------------------------------------------------------------------------
# Main builders
# ---------------------------------------------------------------------------

def build_event_memory_record(
    target: str,
    event_name: str,
    summary: str,
    event_type: EventMemoryType = "unknown",
    impact_direction: EventMemoryImpactDirection = "unknown",
    impact_magnitude: EventMemoryImpactMagnitude = "unknown",
    review_status: EventMemoryReviewStatus = "unknown",
    thesis_changing: bool = False,
    affected_horizons: Optional[list[str]] = None,
    market_reaction: Optional[str] = None,
    guidance_update: Optional[str] = None,
    estimate_revision_summary: Optional[str] = None,
    event_date: Optional[str] = None,
    run_id: Optional[str] = None,
    memory_id: Optional[str] = None,
    thesis_id: Optional[str] = None,
    source_refs: Optional[list[EventMemorySourceRef]] = None,
    evidence_ids: Optional[list[str]] = None,
    artifact_refs: Optional[list[str]] = None,
    recorded_at: Optional[str] = None,
    initial_status: Optional[EventMemoryStatus] = None,
    input_bundle: Optional[EventMemoryInputBundle] = None,
    extra_warnings: Optional[list[str]] = None,
) -> EventMemoryRecord:
    """
    Build an EventMemoryRecord for a single catalyst, news, earnings, or other event.

    Timestamp resolution priority (highest wins):
      1. explicit recorded_at argument;
      2. input_bundle.as_of if present;
      3. _DETERMINISTIC_TIMESTAMP_DEFAULT ("1970-01-01T00:00:00Z").

    Identical inputs without explicit timestamps always produce identical output.
    Inputs are never mutated.
    approved_for_execution is always False.
    Missing optional upstream artifacts produce warnings, not crashes.
    initial_status overrides auto-determined status when provided.
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

    event_memory_id = make_event_memory_record_id(
        target=target,
        event_name=event_name,
        event_type=event_type,
        as_of=as_of,
        run_id=effective_run_id,
    )

    # Deduplicate source_refs by source_id (first occurrence wins)
    _seen_sids: set[str] = set()
    _source_refs: list[EventMemorySourceRef] = []
    for _sr in (source_refs or []):
        if _sr.source_id not in _seen_sids:
            _seen_sids.add(_sr.source_id)
            _source_refs.append(_sr)
    _evidence_ids = _dedup_list(list(evidence_ids or []))
    _artifact_refs = _dedup_list([r for r in (artifact_refs or []) if r and r.strip()])
    _affected_horizons = list(affected_horizons or [])

    status, status_warnings = _determine_single_record_status(
        thesis_changing=thesis_changing,
        impact_magnitude=impact_magnitude,
        review_status=review_status,
        input_bundle=input_bundle,
        initial_status=initial_status,
    )

    bundle_warnings = list(input_bundle.warnings if input_bundle else [])

    missing_warnings: list[str] = []
    if input_bundle is not None:
        if input_bundle.event_intelligence_report is None:
            missing_warnings.append(
                "Missing optional upstream artifact: event_intelligence_report."
            )
        if input_bundle.decision_packet is None:
            missing_warnings.append(
                "Missing optional upstream artifact: decision_packet."
            )

    all_warnings = bundle_warnings + status_warnings + missing_warnings + list(extra_warnings or [])

    # Build initial event log entry
    creation_entry = build_event_memory_log_entry(
        event_type="event_recorded",
        description=(
            f"Event memory record created for target '{target}' "
            f"(event_type={event_type!r}, impact={impact_magnitude!r}, "
            f"thesis_changing={thesis_changing!r}, status={status!r})."
        ),
        event_memory_id=event_memory_id,
        created_at=ts,
        actor="system",
        source_ids=[ref.source_id for ref in _source_refs],
        evidence_ids=_evidence_ids,
        metadata={"target": target, "event_type": event_type},
    )
    event_log = [creation_entry]

    if status in ("blocked", "needs_review", "thesis_changing"):
        review_entry = build_event_memory_log_entry(
            event_type="review_requested",
            description=f"Event memory record requires review — status is '{status}'.",
            event_memory_id=event_memory_id,
            created_at=ts,
            actor="system",
        )
        event_log.append(review_entry)

    if thesis_changing and status == "thesis_changing":
        thesis_entry = build_event_memory_log_entry(
            event_type="thesis_changed",
            description=(
                f"Thesis-changing event recorded: {event_name!r}. "
                f"Impact direction: {impact_direction!r}, magnitude: {impact_magnitude!r}."
            ),
            event_memory_id=event_memory_id,
            created_at=ts,
            actor="system",
        )
        event_log.append(thesis_entry)

    return EventMemoryRecord(
        event_memory_id=event_memory_id,
        target=target,
        run_id=effective_run_id,
        memory_id=effective_memory_id,
        thesis_id=effective_thesis_id,
        event_type=event_type,
        status=status,
        review_status=review_status,
        event_name=event_name,
        event_date=event_date,
        recorded_at=ts,
        impact_direction=impact_direction,
        impact_magnitude=impact_magnitude,
        thesis_changing=thesis_changing,
        affected_horizons=_affected_horizons,
        summary=summary,
        market_reaction=market_reaction,
        guidance_update=guidance_update,
        estimate_revision_summary=estimate_revision_summary,
        source_refs=_source_refs,
        evidence_ids=_evidence_ids,
        artifact_refs=_artifact_refs,
        event_log=event_log,
        warnings=all_warnings,
        approved_for_execution=False,
    )


def build_event_memory_report(
    input_bundle: EventMemoryInputBundle,
    records: Optional[list[EventMemoryRecord]] = None,
    created_at: Optional[str] = None,
    updated_at: Optional[str] = None,
) -> EventMemoryReport:
    """
    Build an EventMemoryReport from an input bundle and a list of event memory records.

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

    report_id = make_event_memory_report_id(
        target=input_bundle.target,
        as_of=as_of,
        run_id=run_id,
    )

    _records = list(records or [])

    status, status_warnings = determine_event_memory_status(
        records=_records,
        input_bundle=input_bundle,
    )

    missing_warnings: list[str] = []
    if input_bundle.event_intelligence_report is None:
        missing_warnings.append("Missing optional upstream artifact: event_intelligence_report.")
    if input_bundle.decision_packet is None:
        missing_warnings.append("Missing optional upstream artifact: decision_packet.")
    if input_bundle.human_review_report is None:
        missing_warnings.append("Missing optional upstream artifact: human_review_report.")

    all_warnings = list(input_bundle.warnings) + status_warnings + missing_warnings

    source_ids = collect_event_memory_source_ids(input_bundle, _records)
    evidence_ids = collect_event_memory_evidence_ids(input_bundle, _records)
    artifact_refs = collect_event_memory_artifact_refs(input_bundle, _records)

    summary = summarize_event_memory(
        target=input_bundle.target,
        status=status,
        records=_records,
        warnings=all_warnings,
    )

    return EventMemoryReport(
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

def event_memory_tool_result_from_report(
    report: EventMemoryReport,
    run_id: Optional[str] = None,
) -> ToolResult:
    """
    Wrap an EventMemoryReport as a ToolResult for evidence-store integration.

    Stable tool name: "event_memory_report".
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
        "thesis_changing_count": report.summary.thesis_changing_count,
        "needs_review_count": report.summary.needs_review_count,
        "high_impact_count": report.summary.high_impact_count,
        "calculation_version": report.calculation_version,
        "approved_for_execution": False,
    }

    evidence_id = make_evidence_id(
        run_id=_run_id,
        tool_name=_EVENT_MEMORY_TOOL_NAME,
        target=report.target,
        metric_group=_EVENT_MEMORY_METRIC_GROUP,
        payload=outputs,
    )

    return ToolResult(
        tool_name=_EVENT_MEMORY_TOOL_NAME,
        run_id=_run_id,
        ticker=report.target if report.target else None,
        evidence_id=evidence_id,
        inputs={"target": report.target, "report_id": report.report_id},
        outputs=outputs,
        description=(
            f"EventMemoryReport for {report.target} "
            f"(report_id={report.report_id!r}, status={report.status!r}, "
            f"records={report.summary.record_count}, "
            f"thesis_changing={report.summary.thesis_changing_count})."
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Literal type aliases
    "EventMemoryActorType",
    "EventMemoryEventType",
    "EventMemoryImpactDirection",
    "EventMemoryImpactMagnitude",
    "EventMemoryReviewStatus",
    "EventMemorySourceType",
    "EventMemoryStatus",
    "EventMemoryType",
    # Models
    "EventMemoryInputBundle",
    "EventMemoryLogEntry",
    "EventMemoryRecord",
    "EventMemoryReport",
    "EventMemorySourceRef",
    "EventMemorySummary",
    # Helpers
    "build_event_memory_log_entry",
    "build_event_memory_record",
    "build_event_memory_report",
    "collect_event_memory_artifact_refs",
    "collect_event_memory_evidence_ids",
    "collect_event_memory_source_ids",
    "determine_event_memory_status",
    "event_memory_tool_result_from_report",
    "make_event_memory_log_entry_id",
    "make_event_memory_record_id",
    "make_event_memory_report_id",
    "summarize_event_memory",
]
