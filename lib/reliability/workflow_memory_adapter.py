"""
lib/reliability/workflow_memory_adapter.py

Phase 5A: Existing Workflow Memory Adapter (overlay contract, fixture-only).

Purpose
-------
Defines a read-only, deterministic adapter contract that maps the *outputs*
of the original README Streamlit five-step research workflow onto Phase 4M
memory record types, without ever touching the live workflow.

The five workflow steps captured here are:

    sector -> scanner -> equity -> financial -> price_volume -> synthesis

This module provides:

  - Pydantic schemas for an *ExistingWorkflowSnapshot* and the per-step
    sub-snapshots that describe what the original Streamlit pages already
    produce, by reference (no full report content duplicated here).
  - A *WorkflowToMemoryAdapter* Protocol describing the conversion contract
    from a snapshot to Phase 4M-compatible memory record references.
  - An *InMemoryWorkflowToMemoryAdapter* implementation that converts a
    fixture-provided snapshot into a deterministic ``WorkflowMemoryBundle``
    of references the fixture-backed memory store can index.

Design principles
-----------------
- Standalone, deterministic, offline / mock-only.
- No live LLM calls.
- No live data fetching, no Streamlit, no Anthropic SDK calls.
- No database writes, no file persistence, no vector store.
- No reading of ``research/.workflow_state.json``.
- No import of ``app.py``, ``pages/*``, ``lib/llm_orchestrator.py``, or
  ``lib/workflow_state.py``.
- No broker / order / execution behavior.
- ``approved_for_execution`` is always ``False`` everywhere it appears.
- Phase 4A (``integration_boundary.py``) is intentionally NOT imported.

Relationship to Phase 4M
------------------------
Phase 5A reuses the accepted Phase 4M memory schemas
(``ResearchRunMemoryRecord``, ``HorizonThesisMemoryRecord``,
``EventMemoryRecord``, ``AllocationDecisionMemoryRecord``,
``OptionTradePlanMemoryRecord``, ``HumanFeedbackMemoryRecord``,
``AgentEvaluationRecord``). Phase 5A does not redefine these record types,
it only defines pointers and adapter glue that the fixture-backed store can
expose to future cockpit view-models (Phase 5B/5C/5D).

See ``docs/reliability_phase_5a_memory_query_contract.md``.

Disclaimer: outputs are for research / educational purposes only and do not
constitute investment advice.
"""

from __future__ import annotations

from typing import Any, Literal, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.adapters import stable_hash_payload
from lib.reliability.research_memory import ResearchRunMemoryRecord
from lib.reliability.thesis_memory import HorizonThesisMemoryRecord
from lib.reliability.event_memory import EventMemoryRecord
from lib.reliability.allocation_memory import AllocationDecisionMemoryRecord
from lib.reliability.option_trade_memory import OptionTradePlanMemoryRecord
from lib.reliability.human_feedback_memory import HumanFeedbackMemoryRecord
from lib.reliability.agent_evaluation import AgentEvaluationRecord


# ---------------------------------------------------------------------------
# Literal type aliases
# ---------------------------------------------------------------------------

ExistingWorkflowStep = Literal[
    "sector",
    "scanner",
    "equity",
    "financial",
    "price_volume",
    "synthesis",
]

ExistingWorkflowStepStatus = Literal[
    "not_run",
    "in_progress",
    "complete",
    "failed",
    "unknown",
]


# Canonical step ordering for deterministic iteration / sorting.
WORKFLOW_STEP_ORDER: tuple[ExistingWorkflowStep, ...] = (
    "sector",
    "scanner",
    "equity",
    "financial",
    "price_volume",
    "synthesis",
)


_CALCULATION_VERSION: str = "workflow_memory_adapter_v1"


# ---------------------------------------------------------------------------
# Snapshot models
# ---------------------------------------------------------------------------


class ExistingPageOutputRef(BaseModel):
    """
    A read-only pointer to an output already produced by one of the original
    Streamlit pages (Overview / Sector / Scanner / Equity / Financial /
    PriceVolume) for one of the five workflow steps.

    Phase 5A never loads the underlying live workflow output. It only holds
    a stable reference so future cockpit view-models can fetch the right
    fixture-backed memory records by run_id / target.

    No execution authorization is implied.
    """

    model_config = ConfigDict(extra="forbid")

    page: str = Field(min_length=1)
    step: ExistingWorkflowStep = "sector"
    artifact_id: Optional[str] = None
    report_path: Optional[str] = None
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "ExistingPageOutputRef":
        if not self.page.strip():
            raise ValueError(f"'page' must not be whitespace-only; got {self.page!r}.")
        return self


class ExistingWorkflowStepSnapshot(BaseModel):
    """
    Per-step snapshot of one of the five existing workflow steps.

    Captures status, optional human-readable summary, and pointers to the
    page outputs the live app already produced (by reference). Does not
    contain or imply any execution authorization.
    """

    model_config = ConfigDict(extra="forbid")

    step: ExistingWorkflowStep = "sector"
    status: ExistingWorkflowStepStatus = "unknown"
    summary: str = ""
    page_outputs: list[ExistingPageOutputRef] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExistingWorkflowSynthesisSnapshot(BaseModel):
    """
    Snapshot of the synthesis step that aggregates the prior four steps
    in the original five-step workflow.

    Captures the synthesis status and optional summary, plus pointers to any
    consolidated report artifact the live app produced. This is the existing
    'Synthesis' step's mirror; it is NOT a new decision packet.
    """

    model_config = ConfigDict(extra="forbid")

    status: ExistingWorkflowStepStatus = "unknown"
    summary: str = ""
    consolidated_report_ref: Optional[ExistingPageOutputRef] = None
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExistingWorkflowSnapshot(BaseModel):
    """
    Read-only snapshot of one complete run of the original five-step
    Streamlit workflow plus its synthesis step.

    Fixture-only. Phase 5A never builds these from a live ``workflow_state``
    read. ``approved_for_execution`` is always ``False``.

    Field semantics:

    - ``run_id``: caller-provided ID for the fixture run. Must not be empty.
    - ``target``: ticker or other research target. Must not be empty.
    - ``as_of``: optional ISO-like date string of the snapshot.
    - ``steps``: dict keyed by step name (sector/scanner/equity/financial/
      price_volume) with per-step sub-snapshots.
    - ``synthesis``: optional synthesis sub-snapshot.

    Whitespace validation enforces non-empty IDs. Unknown extra fields
    are rejected.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    as_of: Optional[str] = None
    workflow_name: Optional[str] = None
    steps: dict[str, ExistingWorkflowStepSnapshot] = Field(default_factory=dict)
    synthesis: Optional[ExistingWorkflowSynthesisSnapshot] = None
    notes: str = ""
    warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _validate(self) -> "ExistingWorkflowSnapshot":
        for fn in ("run_id", "target"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 5A. "
                "This overlay does not authorize execution."
            )
        for key, step in self.steps.items():
            if key not in WORKFLOW_STEP_ORDER:
                raise ValueError(
                    f"Unknown workflow step key {key!r}; "
                    f"expected one of {WORKFLOW_STEP_ORDER}."
                )
            if step.step != key:
                raise ValueError(
                    f"Workflow step key {key!r} does not match step.step "
                    f"{step.step!r}; keys must match step names."
                )
        return self

    def step_keys(self) -> list[str]:
        """Return deterministic-ordered list of present step keys."""
        return [s for s in WORKFLOW_STEP_ORDER if s in self.steps]


# ---------------------------------------------------------------------------
# Adapter output bundle
# ---------------------------------------------------------------------------


class WorkflowMemoryBundle(BaseModel):
    """
    Output of a ``WorkflowToMemoryAdapter`` conversion.

    Holds Phase 4M memory records associated with a single snapshot. All
    fields are optional or list-typed so partial coverage is allowed.
    ``approved_for_execution`` is always ``False``.

    The bundle is deterministic for identical input snapshots and identical
    memory record lists.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    research_run_memory: Optional[ResearchRunMemoryRecord] = None
    thesis_records: list[HorizonThesisMemoryRecord] = Field(default_factory=list)
    event_records: list[EventMemoryRecord] = Field(default_factory=list)
    allocation_records: list[AllocationDecisionMemoryRecord] = Field(default_factory=list)
    option_trade_records: list[OptionTradePlanMemoryRecord] = Field(default_factory=list)
    human_feedback_records: list[HumanFeedbackMemoryRecord] = Field(default_factory=list)
    agent_evaluation_records: list[AgentEvaluationRecord] = Field(default_factory=list)
    workflow_step_keys: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    calculation_version: str = _CALCULATION_VERSION
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _validate(self) -> "WorkflowMemoryBundle":
        for fn in ("run_id", "target", "snapshot_id"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 5A."
            )
        return self


# ---------------------------------------------------------------------------
# Adapter protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class WorkflowToMemoryAdapter(Protocol):
    """
    Protocol for adapters that convert an ``ExistingWorkflowSnapshot`` into a
    ``WorkflowMemoryBundle`` of Phase 4M-compatible memory records.

    Implementations MUST be deterministic for identical inputs and MUST NOT
    read from ``lib/workflow_state.py`` or any live runtime path. They MUST
    NOT call external APIs or live LLMs.
    """

    def adapt(self, snapshot: ExistingWorkflowSnapshot) -> WorkflowMemoryBundle:
        """Convert a workflow snapshot into a Phase 4M memory bundle."""
        ...


# ---------------------------------------------------------------------------
# Deterministic ID helpers
# ---------------------------------------------------------------------------


def make_workflow_snapshot_id(
    run_id: str,
    target: str,
    as_of: Optional[str] = None,
) -> str:
    """Return a deterministic stable ID for a workflow snapshot."""
    payload: dict[str, Any] = {"run_id": run_id, "target": target, "as_of": as_of or ""}
    h = stable_hash_payload(payload, length=16)
    return f"wfsnap_{h}"


# ---------------------------------------------------------------------------
# Default in-memory adapter
# ---------------------------------------------------------------------------


class InMemoryWorkflowToMemoryAdapter:
    """
    Default fixture/mock-only ``WorkflowToMemoryAdapter``.

    Holds an optional pre-built ``WorkflowMemoryBundle`` *associated* with a
    fixture snapshot. The adapter does not synthesize memory records from
    the snapshot — Phase 5A is a contract/interface layer, not a generator.
    Fixtures provide the memory records explicitly via
    ``register_records()``.

    The adapter validates that:
      - bundle.run_id matches snapshot.run_id
      - bundle.target matches snapshot.target
      - every memory record that carries a ``run_id`` attribute matches
        snapshot.run_id (when not None)

    No persistence, no DB, no vector store, no external IO. No live
    ``workflow_state`` read. ``approved_for_execution`` remains ``False``.
    """

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], WorkflowMemoryBundle] = {}

    def register_records(
        self,
        snapshot: ExistingWorkflowSnapshot,
        research_run_memory: Optional[ResearchRunMemoryRecord] = None,
        thesis_records: Optional[list[HorizonThesisMemoryRecord]] = None,
        event_records: Optional[list[EventMemoryRecord]] = None,
        allocation_records: Optional[list[AllocationDecisionMemoryRecord]] = None,
        option_trade_records: Optional[list[OptionTradePlanMemoryRecord]] = None,
        human_feedback_records: Optional[list[HumanFeedbackMemoryRecord]] = None,
        agent_evaluation_records: Optional[list[AgentEvaluationRecord]] = None,
        warnings: Optional[list[str]] = None,
    ) -> WorkflowMemoryBundle:
        """
        Register a pre-built set of Phase 4M memory records against the
        snapshot. Returns the resulting ``WorkflowMemoryBundle``.

        Phase 5A does not synthesize memory content from the snapshot's text.
        Fixtures supply the records explicitly so that the boundary contract
        is the only thing under test.
        """
        thesis_records = list(thesis_records or [])
        event_records = list(event_records or [])
        allocation_records = list(allocation_records or [])
        option_trade_records = list(option_trade_records or [])
        human_feedback_records = list(human_feedback_records or [])
        agent_evaluation_records = list(agent_evaluation_records or [])

        snapshot_id = make_workflow_snapshot_id(
            run_id=snapshot.run_id,
            target=snapshot.target,
            as_of=snapshot.as_of,
        )

        adapter_warnings: list[str] = list(warnings or [])

        # Cross-validate run_id consistency on every memory record that has a
        # run_id attribute. Mismatched records produce warnings rather than
        # raising — that way fixtures can include cross-run agent evaluation
        # records if needed, while the boundary remains explicit.
        for label, records in (
            ("thesis", thesis_records),
            ("event", event_records),
            ("allocation", allocation_records),
            ("option_trade", option_trade_records),
            ("human_feedback", human_feedback_records),
            ("agent_evaluation", agent_evaluation_records),
        ):
            for r in records:
                rid = getattr(r, "run_id", None)
                if rid is not None and rid != snapshot.run_id:
                    adapter_warnings.append(
                        f"{label} record run_id={rid!r} does not match "
                        f"snapshot.run_id={snapshot.run_id!r}; included anyway."
                    )
                tgt = getattr(r, "target", None)
                if tgt is not None and tgt != snapshot.target:
                    adapter_warnings.append(
                        f"{label} record target={tgt!r} does not match "
                        f"snapshot.target={snapshot.target!r}; included anyway."
                    )

        bundle = WorkflowMemoryBundle(
            run_id=snapshot.run_id,
            target=snapshot.target,
            snapshot_id=snapshot_id,
            research_run_memory=research_run_memory,
            thesis_records=thesis_records,
            event_records=event_records,
            allocation_records=allocation_records,
            option_trade_records=option_trade_records,
            human_feedback_records=human_feedback_records,
            agent_evaluation_records=agent_evaluation_records,
            workflow_step_keys=snapshot.step_keys(),
            warnings=adapter_warnings,
            approved_for_execution=False,
        )

        self._records[(snapshot.run_id, snapshot.target)] = bundle
        return bundle

    def adapt(self, snapshot: ExistingWorkflowSnapshot) -> WorkflowMemoryBundle:
        """
        Return the pre-registered ``WorkflowMemoryBundle`` for this snapshot.

        If no records were registered, returns an empty bundle (no
        hallucination — Phase 5A never fabricates memory content).
        """
        key = (snapshot.run_id, snapshot.target)
        existing = self._records.get(key)
        if existing is not None:
            return existing
        snapshot_id = make_workflow_snapshot_id(
            run_id=snapshot.run_id,
            target=snapshot.target,
            as_of=snapshot.as_of,
        )
        return WorkflowMemoryBundle(
            run_id=snapshot.run_id,
            target=snapshot.target,
            snapshot_id=snapshot_id,
            workflow_step_keys=snapshot.step_keys(),
            warnings=[
                "No Phase 4M memory records were registered for this snapshot; "
                "returning an empty bundle."
            ],
            approved_for_execution=False,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Literal aliases
    "ExistingWorkflowStep",
    "ExistingWorkflowStepStatus",
    "WORKFLOW_STEP_ORDER",
    # Models
    "ExistingPageOutputRef",
    "ExistingWorkflowStepSnapshot",
    "ExistingWorkflowSynthesisSnapshot",
    "ExistingWorkflowSnapshot",
    "WorkflowMemoryBundle",
    # Protocol + adapter
    "WorkflowToMemoryAdapter",
    "InMemoryWorkflowToMemoryAdapter",
    # Helpers
    "make_workflow_snapshot_id",
]
