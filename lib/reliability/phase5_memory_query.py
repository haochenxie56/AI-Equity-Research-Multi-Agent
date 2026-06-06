"""
lib/reliability/phase5_memory_query.py

Phase 5A: Fixture-backed Memory Query Contract.

Purpose
-------
Defines a read-only ``MemoryStoreProtocol`` and an in-memory
``FixtureBackedMemoryStore`` implementation that future Phase 5
cockpit / view-model layers can query for Phase 4M memory records.

Supported query inputs:

  - MemoryQueryByTicker          — query by target (ticker)
  - MemoryQueryByRunId           — query by run_id
  - MemoryQueryByHorizon         — query thesis records by horizon
  - MemoryQueryByType            — query by memory type
  - MemoryQueryByReviewStatus    — query by review/needs-review state

Supported memory record types (mirroring Phase 4M):

  - research_run    -> ResearchRunMemoryRecord
  - thesis          -> HorizonThesisMemoryRecord
  - event           -> EventMemoryRecord
  - allocation      -> AllocationDecisionMemoryRecord
  - option_trade    -> OptionTradePlanMemoryRecord
  - human_feedback  -> HumanFeedbackMemoryRecord
  - agent_evaluation-> AgentEvaluationRecord

Design principles
-----------------
- Standalone, deterministic, offline / mock-only.
- No live LLM calls.
- No live data fetching.
- No database writes, no file persistence, no vector store.
- No reading of ``research/.workflow_state.json``.
- No import of ``app.py``, ``pages/*``, ``lib/llm_orchestrator.py``, or
  ``lib/workflow_state.py``.
- No broker / order / execution behavior.
- ``approved_for_execution`` is always ``False`` everywhere it appears.

Empty-state behavior
--------------------
- Missing ticker -> empty ``MemoryQueryResult`` (no hallucination).
- Missing run_id -> empty result.
- Missing horizon -> empty result.
- Unknown memory type -> validation error at query construction time.

See ``docs/reliability_phase_5a_memory_query_contract.md``.
"""

from __future__ import annotations

from typing import Any, Literal, Optional, Protocol, Union, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.research_memory import ResearchRunMemoryRecord
from lib.reliability.thesis_memory import HorizonThesisMemoryRecord
from lib.reliability.event_memory import EventMemoryRecord
from lib.reliability.allocation_memory import AllocationDecisionMemoryRecord
from lib.reliability.option_trade_memory import OptionTradePlanMemoryRecord
from lib.reliability.human_feedback_memory import HumanFeedbackMemoryRecord
from lib.reliability.agent_evaluation import AgentEvaluationRecord
from lib.reliability.workflow_memory_adapter import (
    ExistingWorkflowSnapshot,
    InMemoryWorkflowToMemoryAdapter,
    WorkflowMemoryBundle,
)


# ---------------------------------------------------------------------------
# Literal type aliases
# ---------------------------------------------------------------------------

MemoryRecordType = Literal[
    "research_run",
    "thesis",
    "event",
    "allocation",
    "option_trade",
    "human_feedback",
    "agent_evaluation",
]

MEMORY_RECORD_TYPES: tuple[MemoryRecordType, ...] = (
    "research_run",
    "thesis",
    "event",
    "allocation",
    "option_trade",
    "human_feedback",
    "agent_evaluation",
)

MemoryHorizon = Literal[
    "short",
    "medium",
    "long",
    "multi_horizon",
    "unknown",
]

MemoryReviewStatus = Literal[
    "any",
    "needs_review",
    "blocked",
    "review_required",
    "clean",
]


# Union type of all Phase 4M record classes that this store exposes.
MemoryRecord = Union[
    ResearchRunMemoryRecord,
    HorizonThesisMemoryRecord,
    EventMemoryRecord,
    AllocationDecisionMemoryRecord,
    OptionTradePlanMemoryRecord,
    HumanFeedbackMemoryRecord,
    AgentEvaluationRecord,
]


# ---------------------------------------------------------------------------
# Query models
# ---------------------------------------------------------------------------


class MemoryQuery(BaseModel):
    """
    Base query model. Concrete query types are specialised subclasses.

    A bare ``MemoryQuery()`` represents "return everything"; the store
    treats it as an unbounded scan in deterministic order.
    """

    model_config = ConfigDict(extra="forbid")

    limit: Optional[int] = None

    @model_validator(mode="after")
    def _validate_limit(self) -> "MemoryQuery":
        if self.limit is not None and self.limit < 0:
            raise ValueError(f"'limit' must be non-negative when present; got {self.limit!r}.")
        return self


class MemoryQueryByTicker(MemoryQuery):
    """Query memory records by the ``target`` field (typically a ticker)."""

    target: str = Field(min_length=1)
    record_types: Optional[list[MemoryRecordType]] = None

    @model_validator(mode="after")
    def _validate(self) -> "MemoryQueryByTicker":
        if not self.target.strip():
            raise ValueError("'target' must not be whitespace-only.")
        if self.record_types is not None:
            for rt in self.record_types:
                if rt not in MEMORY_RECORD_TYPES:
                    raise ValueError(
                        f"Unknown memory record type {rt!r}; "
                        f"expected one of {MEMORY_RECORD_TYPES}."
                    )
        return self


class MemoryQueryByRunId(MemoryQuery):
    """Query memory records by ``run_id``."""

    run_id: str = Field(min_length=1)
    record_types: Optional[list[MemoryRecordType]] = None

    @model_validator(mode="after")
    def _validate(self) -> "MemoryQueryByRunId":
        if not self.run_id.strip():
            raise ValueError("'run_id' must not be whitespace-only.")
        if self.record_types is not None:
            for rt in self.record_types:
                if rt not in MEMORY_RECORD_TYPES:
                    raise ValueError(
                        f"Unknown memory record type {rt!r}; "
                        f"expected one of {MEMORY_RECORD_TYPES}."
                    )
        return self


class MemoryQueryByHorizon(MemoryQuery):
    """Query thesis memory records by horizon (and optional target)."""

    horizon: MemoryHorizon = "unknown"
    target: Optional[str] = None

    @model_validator(mode="after")
    def _validate(self) -> "MemoryQueryByHorizon":
        if self.target is not None and not self.target.strip():
            raise ValueError("'target' must not be whitespace-only when provided.")
        return self


class MemoryQueryByType(MemoryQuery):
    """Query memory records by ``record_type``."""

    record_type: MemoryRecordType = "research_run"
    target: Optional[str] = None
    run_id: Optional[str] = None

    @model_validator(mode="after")
    def _validate(self) -> "MemoryQueryByType":
        if self.record_type not in MEMORY_RECORD_TYPES:
            raise ValueError(
                f"Unknown memory record type {self.record_type!r}; "
                f"expected one of {MEMORY_RECORD_TYPES}."
            )
        if self.target is not None and not self.target.strip():
            raise ValueError("'target' must not be whitespace-only when provided.")
        if self.run_id is not None and not self.run_id.strip():
            raise ValueError("'run_id' must not be whitespace-only when provided.")
        return self


class MemoryQueryByReviewStatus(MemoryQuery):
    """
    Query memory records by review status.

    ``review_status='needs_review'`` returns records whose ``status`` is
    ``needs_review`` *or* whose ``review_required``/``review_status`` flags
    indicate review.

    ``review_status='blocked'`` returns records whose ``status`` is
    ``blocked``.

    ``review_status='review_required'`` returns records with a truthy
    ``review_required`` attribute.

    ``review_status='clean'`` returns records whose ``status`` is neither
    blocked nor needs_review and whose ``review_required`` flag (if any)
    is False.

    ``review_status='any'`` returns all records (no review filter).
    """

    review_status: MemoryReviewStatus = "any"
    target: Optional[str] = None
    record_types: Optional[list[MemoryRecordType]] = None

    @model_validator(mode="after")
    def _validate(self) -> "MemoryQueryByReviewStatus":
        if self.target is not None and not self.target.strip():
            raise ValueError("'target' must not be whitespace-only when provided.")
        if self.record_types is not None:
            for rt in self.record_types:
                if rt not in MEMORY_RECORD_TYPES:
                    raise ValueError(
                        f"Unknown memory record type {rt!r}; "
                        f"expected one of {MEMORY_RECORD_TYPES}."
                    )
        return self


# ---------------------------------------------------------------------------
# Query result
# ---------------------------------------------------------------------------


class MemoryQueryResult(BaseModel):
    """
    Result of a memory query against a fixture-backed memory store.

    All record-list fields are deterministic-ordered (insertion order from
    the store, filtered by query, never randomized). ``approved_for_execution``
    is always ``False``.

    ``total_count`` is the count of records before any ``limit`` clamp was
    applied; consumers can use it to detect truncation.
    """

    model_config = ConfigDict(extra="forbid")

    research_run_records: list[ResearchRunMemoryRecord] = Field(default_factory=list)
    thesis_records: list[HorizonThesisMemoryRecord] = Field(default_factory=list)
    event_records: list[EventMemoryRecord] = Field(default_factory=list)
    allocation_records: list[AllocationDecisionMemoryRecord] = Field(default_factory=list)
    option_trade_records: list[OptionTradePlanMemoryRecord] = Field(default_factory=list)
    human_feedback_records: list[HumanFeedbackMemoryRecord] = Field(default_factory=list)
    agent_evaluation_records: list[AgentEvaluationRecord] = Field(default_factory=list)
    total_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _validate(self) -> "MemoryQueryResult":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 5A."
            )
        if self.total_count < 0:
            raise ValueError(f"'total_count' must be non-negative; got {self.total_count!r}.")
        return self

    def is_empty(self) -> bool:
        return (
            not self.research_run_records
            and not self.thesis_records
            and not self.event_records
            and not self.allocation_records
            and not self.option_trade_records
            and not self.human_feedback_records
            and not self.agent_evaluation_records
        )

    def count_by_type(self) -> dict[str, int]:
        return {
            "research_run": len(self.research_run_records),
            "thesis": len(self.thesis_records),
            "event": len(self.event_records),
            "allocation": len(self.allocation_records),
            "option_trade": len(self.option_trade_records),
            "human_feedback": len(self.human_feedback_records),
            "agent_evaluation": len(self.agent_evaluation_records),
        }


# ---------------------------------------------------------------------------
# Store protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class MemoryStoreProtocol(Protocol):
    """
    Protocol for read-only memory stores used by Phase 5 view-model layers.

    Implementations MUST be deterministic. They MUST NOT persist memory
    records to disk, a database, or a vector store. They MUST NOT call
    external APIs.

    Phase 5A's reference implementation is ``FixtureBackedMemoryStore``.
    """

    def query(
        self,
        query: Union[
            MemoryQuery,
            MemoryQueryByTicker,
            MemoryQueryByRunId,
            MemoryQueryByHorizon,
            MemoryQueryByType,
            MemoryQueryByReviewStatus,
        ],
    ) -> MemoryQueryResult:
        """Return a deterministic ``MemoryQueryResult`` for the given query."""
        ...


MemoryQueryProtocol = MemoryStoreProtocol  # alias for callers that prefer the name


# ---------------------------------------------------------------------------
# Helpers — review-status interpretation
# ---------------------------------------------------------------------------


def _record_status_str(record: MemoryRecord) -> str:
    return str(getattr(record, "status", "") or "")


def _record_review_required(record: MemoryRecord) -> bool:
    rr = getattr(record, "review_required", None)
    if rr is not None:
        return bool(rr)
    summary = getattr(record, "summary", None)
    if summary is not None:
        srr = getattr(summary, "review_required", None)
        if srr is not None:
            return bool(srr)
    return False


def _record_matches_review_status(
    record: MemoryRecord, review_status: MemoryReviewStatus
) -> bool:
    if review_status == "any":
        return True
    status = _record_status_str(record)
    if review_status == "blocked":
        return status == "blocked"
    if review_status == "needs_review":
        if status in ("needs_review", "blocked"):
            return True
        return _record_review_required(record)
    if review_status == "review_required":
        return _record_review_required(record)
    if review_status == "clean":
        if status in ("needs_review", "blocked"):
            return False
        return not _record_review_required(record)
    return True


# ---------------------------------------------------------------------------
# Fixture-backed memory store
# ---------------------------------------------------------------------------


class FixtureBackedMemoryStore:
    """
    In-memory, fixture-backed implementation of ``MemoryStoreProtocol``.

    Holds Phase 4M memory records added via ``register_bundle()`` or the
    direct ``add_*`` methods. Query semantics are deterministic: records
    are returned in insertion order, filtered by the query.

    The store does **not** persist to disk, a database, or a vector store.
    It does **not** import live workflow modules, does **not** read
    ``research/.workflow_state.json``, and does **not** call external APIs.

    ``approved_for_execution`` remains ``False`` on every query result.
    """

    def __init__(self) -> None:
        self._research_run_records: list[ResearchRunMemoryRecord] = []
        self._thesis_records: list[HorizonThesisMemoryRecord] = []
        self._event_records: list[EventMemoryRecord] = []
        self._allocation_records: list[AllocationDecisionMemoryRecord] = []
        self._option_trade_records: list[OptionTradePlanMemoryRecord] = []
        self._human_feedback_records: list[HumanFeedbackMemoryRecord] = []
        self._agent_evaluation_records: list[AgentEvaluationRecord] = []

    # --- registration ------------------------------------------------------

    def register_bundle(self, bundle: WorkflowMemoryBundle) -> None:
        """Register all records from a ``WorkflowMemoryBundle``."""
        if bundle.approved_for_execution:
            raise ValueError(
                "Cannot register bundle with approved_for_execution=True."
            )
        if bundle.research_run_memory is not None:
            self.add_research_run_record(bundle.research_run_memory)
        for r in bundle.thesis_records:
            self.add_thesis_record(r)
        for r in bundle.event_records:
            self.add_event_record(r)
        for r in bundle.allocation_records:
            self.add_allocation_record(r)
        for r in bundle.option_trade_records:
            self.add_option_trade_record(r)
        for r in bundle.human_feedback_records:
            self.add_human_feedback_record(r)
        for r in bundle.agent_evaluation_records:
            self.add_agent_evaluation_record(r)

    def add_research_run_record(self, record: ResearchRunMemoryRecord) -> None:
        if record.approved_for_execution:
            raise ValueError("Cannot register record with approved_for_execution=True.")
        self._research_run_records.append(record)

    def add_thesis_record(self, record: HorizonThesisMemoryRecord) -> None:
        if record.approved_for_execution:
            raise ValueError("Cannot register record with approved_for_execution=True.")
        self._thesis_records.append(record)

    def add_event_record(self, record: EventMemoryRecord) -> None:
        if record.approved_for_execution:
            raise ValueError("Cannot register record with approved_for_execution=True.")
        self._event_records.append(record)

    def add_allocation_record(self, record: AllocationDecisionMemoryRecord) -> None:
        if record.approved_for_execution:
            raise ValueError("Cannot register record with approved_for_execution=True.")
        self._allocation_records.append(record)

    def add_option_trade_record(self, record: OptionTradePlanMemoryRecord) -> None:
        if record.approved_for_execution:
            raise ValueError("Cannot register record with approved_for_execution=True.")
        self._option_trade_records.append(record)

    def add_human_feedback_record(self, record: HumanFeedbackMemoryRecord) -> None:
        if record.approved_for_execution:
            raise ValueError("Cannot register record with approved_for_execution=True.")
        self._human_feedback_records.append(record)

    def add_agent_evaluation_record(self, record: AgentEvaluationRecord) -> None:
        if record.approved_for_execution:
            raise ValueError("Cannot register record with approved_for_execution=True.")
        self._agent_evaluation_records.append(record)

    # --- query -------------------------------------------------------------

    def query(
        self,
        query: Union[
            MemoryQuery,
            MemoryQueryByTicker,
            MemoryQueryByRunId,
            MemoryQueryByHorizon,
            MemoryQueryByType,
            MemoryQueryByReviewStatus,
        ],
    ) -> MemoryQueryResult:
        """Run a query against the store and return a deterministic result."""
        if isinstance(query, MemoryQueryByTicker):
            return self._query_by_ticker(query)
        if isinstance(query, MemoryQueryByRunId):
            return self._query_by_run_id(query)
        if isinstance(query, MemoryQueryByHorizon):
            return self._query_by_horizon(query)
        if isinstance(query, MemoryQueryByType):
            return self._query_by_type(query)
        if isinstance(query, MemoryQueryByReviewStatus):
            return self._query_by_review_status(query)
        if isinstance(query, MemoryQuery):
            return self._query_all(query)
        raise TypeError(
            f"Unsupported query type: {type(query).__name__}. "
            "Expected one of MemoryQuery, MemoryQueryByTicker, "
            "MemoryQueryByRunId, MemoryQueryByHorizon, MemoryQueryByType, "
            "MemoryQueryByReviewStatus."
        )

    # --- internal query implementations -----------------------------------

    def _filter_by_record_types(
        self, record_types: Optional[list[MemoryRecordType]]
    ) -> set[MemoryRecordType]:
        if record_types is None:
            return set(MEMORY_RECORD_TYPES)
        return set(record_types)

    def _result_from_lists(
        self,
        *,
        research_run: list[ResearchRunMemoryRecord],
        thesis: list[HorizonThesisMemoryRecord],
        event: list[EventMemoryRecord],
        allocation: list[AllocationDecisionMemoryRecord],
        option_trade: list[OptionTradePlanMemoryRecord],
        human_feedback: list[HumanFeedbackMemoryRecord],
        agent_evaluation: list[AgentEvaluationRecord],
        limit: Optional[int],
        warnings: Optional[list[str]] = None,
    ) -> MemoryQueryResult:
        total = (
            len(research_run)
            + len(thesis)
            + len(event)
            + len(allocation)
            + len(option_trade)
            + len(human_feedback)
            + len(agent_evaluation)
        )
        if limit is not None:
            research_run = research_run[:limit]
            thesis = thesis[:limit]
            event = event[:limit]
            allocation = allocation[:limit]
            option_trade = option_trade[:limit]
            human_feedback = human_feedback[:limit]
            agent_evaluation = agent_evaluation[:limit]
        return MemoryQueryResult(
            research_run_records=research_run,
            thesis_records=thesis,
            event_records=event,
            allocation_records=allocation,
            option_trade_records=option_trade,
            human_feedback_records=human_feedback,
            agent_evaluation_records=agent_evaluation,
            total_count=total,
            warnings=list(warnings or []),
            approved_for_execution=False,
        )

    def _query_all(self, query: MemoryQuery) -> MemoryQueryResult:
        return self._result_from_lists(
            research_run=list(self._research_run_records),
            thesis=list(self._thesis_records),
            event=list(self._event_records),
            allocation=list(self._allocation_records),
            option_trade=list(self._option_trade_records),
            human_feedback=list(self._human_feedback_records),
            agent_evaluation=list(self._agent_evaluation_records),
            limit=query.limit,
        )

    def _query_by_ticker(self, query: MemoryQueryByTicker) -> MemoryQueryResult:
        types = self._filter_by_record_types(query.record_types)
        t = query.target

        def keep(records, type_key):
            if type_key not in types:
                return []
            return [r for r in records if getattr(r, "target", None) == t]

        return self._result_from_lists(
            research_run=keep(self._research_run_records, "research_run"),
            thesis=keep(self._thesis_records, "thesis"),
            event=keep(self._event_records, "event"),
            allocation=keep(self._allocation_records, "allocation"),
            option_trade=keep(self._option_trade_records, "option_trade"),
            human_feedback=keep(self._human_feedback_records, "human_feedback"),
            agent_evaluation=keep(self._agent_evaluation_records, "agent_evaluation"),
            limit=query.limit,
        )

    def _query_by_run_id(self, query: MemoryQueryByRunId) -> MemoryQueryResult:
        types = self._filter_by_record_types(query.record_types)
        rid = query.run_id

        def keep(records, type_key):
            if type_key not in types:
                return []
            return [r for r in records if getattr(r, "run_id", None) == rid]

        return self._result_from_lists(
            research_run=keep(self._research_run_records, "research_run"),
            thesis=keep(self._thesis_records, "thesis"),
            event=keep(self._event_records, "event"),
            allocation=keep(self._allocation_records, "allocation"),
            option_trade=keep(self._option_trade_records, "option_trade"),
            human_feedback=keep(self._human_feedback_records, "human_feedback"),
            agent_evaluation=keep(self._agent_evaluation_records, "agent_evaluation"),
            limit=query.limit,
        )

    def _query_by_horizon(self, query: MemoryQueryByHorizon) -> MemoryQueryResult:
        horizon = query.horizon
        target = query.target

        def horizon_match(record: HorizonThesisMemoryRecord) -> bool:
            if getattr(record, "horizon", None) != horizon:
                return False
            if target is not None and getattr(record, "target", None) != target:
                return False
            return True

        matched = [r for r in self._thesis_records if horizon_match(r)]
        return self._result_from_lists(
            research_run=[],
            thesis=matched,
            event=[],
            allocation=[],
            option_trade=[],
            human_feedback=[],
            agent_evaluation=[],
            limit=query.limit,
        )

    def _query_by_type(self, query: MemoryQueryByType) -> MemoryQueryResult:
        rt = query.record_type
        target = query.target
        run_id = query.run_id

        def keep(records):
            out = list(records)
            if target is not None:
                out = [r for r in out if getattr(r, "target", None) == target]
            if run_id is not None:
                out = [r for r in out if getattr(r, "run_id", None) == run_id]
            return out

        research_run: list[ResearchRunMemoryRecord] = []
        thesis: list[HorizonThesisMemoryRecord] = []
        event: list[EventMemoryRecord] = []
        allocation: list[AllocationDecisionMemoryRecord] = []
        option_trade: list[OptionTradePlanMemoryRecord] = []
        human_feedback: list[HumanFeedbackMemoryRecord] = []
        agent_evaluation: list[AgentEvaluationRecord] = []

        if rt == "research_run":
            research_run = keep(self._research_run_records)
        elif rt == "thesis":
            thesis = keep(self._thesis_records)
        elif rt == "event":
            event = keep(self._event_records)
        elif rt == "allocation":
            allocation = keep(self._allocation_records)
        elif rt == "option_trade":
            option_trade = keep(self._option_trade_records)
        elif rt == "human_feedback":
            human_feedback = keep(self._human_feedback_records)
        elif rt == "agent_evaluation":
            agent_evaluation = keep(self._agent_evaluation_records)

        return self._result_from_lists(
            research_run=research_run,
            thesis=thesis,
            event=event,
            allocation=allocation,
            option_trade=option_trade,
            human_feedback=human_feedback,
            agent_evaluation=agent_evaluation,
            limit=query.limit,
        )

    def _query_by_review_status(
        self, query: MemoryQueryByReviewStatus
    ) -> MemoryQueryResult:
        types = self._filter_by_record_types(query.record_types)
        target = query.target
        rs = query.review_status

        def keep(records, type_key):
            if type_key not in types:
                return []
            out = list(records)
            if target is not None:
                out = [r for r in out if getattr(r, "target", None) == target]
            return [r for r in out if _record_matches_review_status(r, rs)]

        return self._result_from_lists(
            research_run=keep(self._research_run_records, "research_run"),
            thesis=keep(self._thesis_records, "thesis"),
            event=keep(self._event_records, "event"),
            allocation=keep(self._allocation_records, "allocation"),
            option_trade=keep(self._option_trade_records, "option_trade"),
            human_feedback=keep(self._human_feedback_records, "human_feedback"),
            agent_evaluation=keep(self._agent_evaluation_records, "agent_evaluation"),
            limit=query.limit,
        )


# ---------------------------------------------------------------------------
# Convenience constructor — fixture pack from snapshot + adapter
# ---------------------------------------------------------------------------


def build_fixture_memory_store_from_snapshot(
    snapshot: ExistingWorkflowSnapshot,
    adapter: InMemoryWorkflowToMemoryAdapter,
) -> "FixtureBackedMemoryStore":
    """
    Convenience helper: convert a workflow snapshot through the provided
    fixture adapter and register the resulting bundle into a new
    ``FixtureBackedMemoryStore``.

    The adapter must already have memory records registered for the
    snapshot via ``adapter.register_records()``. Otherwise the resulting
    store will be empty.
    """
    bundle = adapter.adapt(snapshot)
    store = FixtureBackedMemoryStore()
    store.register_bundle(bundle)
    return store


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Literal aliases
    "MemoryRecordType",
    "MEMORY_RECORD_TYPES",
    "MemoryHorizon",
    "MemoryReviewStatus",
    # Union alias
    "MemoryRecord",
    # Query models
    "MemoryQuery",
    "MemoryQueryByTicker",
    "MemoryQueryByRunId",
    "MemoryQueryByHorizon",
    "MemoryQueryByType",
    "MemoryQueryByReviewStatus",
    "MemoryQueryResult",
    # Protocols + store
    "MemoryStoreProtocol",
    "MemoryQueryProtocol",
    "FixtureBackedMemoryStore",
    # Convenience helper
    "build_fixture_memory_store_from_snapshot",
]
