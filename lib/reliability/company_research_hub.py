"""
lib/reliability/company_research_hub.py

Phase 5B: Company Research Hub ViewModel Contract.

Purpose
-------
Defines deterministic, cockpit-ready Pydantic view-model contracts that
project the original README app's Equity / Financial / PriceVolume research
outputs into a future Company Research Hub representation, plus deterministic
builder helpers that consume the Phase 5A fixture-backed memory query
contract and/or an ``ExistingWorkflowSnapshot``.

This module is a **view-model contract layer only**. It does not connect to
the live Streamlit app, does not introduce a UI, does not perform any data
fetch, and does not produce trade instructions or investment advice.

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
- ``approved_for_execution`` is not exposed by Phase 5B view models; the
  Phase 5A snapshot already rejects ``approved_for_execution=True`` at its
  model layer, so builders that consume snapshots inherit that invariant.

Relationship to the original README app
---------------------------------------
The README app's Streamlit pages (Equity / Financial / PriceVolume /
Overview) populate the existing five-step workflow's outputs. Phase 5A
provides a read-only adapter that points at those outputs by reference.
Phase 5B re-projects those references into cockpit panels that a future
Phase 5E cockpit UI could render next to the existing pages without
touching them.

Mapping
~~~~~~~
    Equity page         -> EquityResearchPanelView
        business model, moat, management, competitive landscape, peer
        comparison (read by reference; no content fabricated)
    Financial page      -> FinancialValuationPanelView
        financial statements, DCF / relative valuation, profitability /
        cash flow quality, valuation reasonableness (read by reference;
        Phase 4M-D allocation memory provides reasonableness context)
    PriceVolume page    -> PriceVolumeTimingPanelView
        K-line / price-volume context, RSI/MACD/ADX/Bollinger/SMA-style
        indicators as represented in existing fixtures, support /
        resistance / timing interpretation (by reference)
    Overview synthesis  -> SourceWorkflowPanelView (synthesis_summary)

Disclaimer: outputs are for research / educational purposes only and do
not constitute investment advice.

See ``docs/reliability_phase_5b_company_research_hub_view_model.md``.
"""

from __future__ import annotations

from typing import Any, Iterable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.workflow_memory_adapter import (
    ExistingPageOutputRef,
    ExistingWorkflowSnapshot,
    ExistingWorkflowStepSnapshot,
    ExistingWorkflowSynthesisSnapshot,
    WORKFLOW_STEP_ORDER,
    make_workflow_snapshot_id,
)
from lib.reliability.phase5_memory_query import (
    MEMORY_RECORD_TYPES,
    FixtureBackedMemoryStore,
    MemoryQuery,
    MemoryQueryByTicker,
    MemoryQueryResult,
    MemoryStoreProtocol,
)


# ---------------------------------------------------------------------------
# Literal aliases
# ---------------------------------------------------------------------------

MissingDataPanel = Literal[
    "equity",
    "financial",
    "price_volume",
    "synthesis",
    "identity",
    "memory",
]


_CALCULATION_VERSION: str = "company_research_hub_v1"


# Subset of WORKFLOW_STEP_ORDER that maps to research-panel content.
_PANEL_STEP_KEYS: tuple[str, ...] = (
    "sector",
    "scanner",
    "equity",
    "financial",
    "price_volume",
    "synthesis",
)


# ---------------------------------------------------------------------------
# Source-of-data tags
# ---------------------------------------------------------------------------

DataSourceTag = Literal[
    "existing_workflow_snapshot",
    "phase4m_memory_record",
    "memory_query_result",
    "absent",
]


# ---------------------------------------------------------------------------
# Helper functions (private)
# ---------------------------------------------------------------------------


def _step_output_refs(step: ExistingWorkflowStepSnapshot) -> list[ExistingPageOutputRef]:
    """Return page output refs for a step as a new list (defensive copy)."""
    return list(step.page_outputs)


def _step_artifact_refs(step: ExistingWorkflowStepSnapshot) -> list[str]:
    out: list[str] = []
    for ref in step.page_outputs:
        if ref.artifact_id and ref.artifact_id not in out:
            out.append(ref.artifact_id)
    for a in step.artifact_refs:
        if a not in out:
            out.append(a)
    return out


def _step_evidence_ids(step: ExistingWorkflowStepSnapshot) -> list[str]:
    return list(step.evidence_ids)


def _is_review_required(record: Any) -> bool:
    rr = getattr(record, "review_required", None)
    if rr is not None:
        return bool(rr)
    summary = getattr(record, "summary", None)
    if summary is not None and not isinstance(summary, str):
        srr = getattr(summary, "review_required", None)
        if srr is not None:
            return bool(srr)
    return False


def _record_status_str(record: Any) -> str:
    return str(getattr(record, "status", "") or "")


def _query_result_for_target(
    memory_store: Optional[MemoryStoreProtocol],
    target: Optional[str],
) -> MemoryQueryResult:
    """Run a target-scoped memory query. Empty result if no store / no target."""
    if memory_store is None or target is None or not str(target).strip():
        return MemoryQueryResult()
    return memory_store.query(MemoryQueryByTicker(target=target))


def _query_result_all(
    memory_store: Optional[MemoryStoreProtocol],
) -> MemoryQueryResult:
    if memory_store is None:
        return MemoryQueryResult()
    return memory_store.query(MemoryQuery())


def _result_iter_records(result: MemoryQueryResult) -> Iterable[Any]:
    yield from result.research_run_records
    yield from result.thesis_records
    yield from result.event_records
    yield from result.allocation_records
    yield from result.option_trade_records
    yield from result.human_feedback_records
    yield from result.agent_evaluation_records


# ---------------------------------------------------------------------------
# View models
# ---------------------------------------------------------------------------


class CompanyIdentityView(BaseModel):
    """
    Identity-level projection for the Company Research Hub view.

    Captures the deterministic identity coordinates of one research run
    (target / run_id / as_of / workflow_name / snapshot_id) plus an
    optional notes field. Carries no recommendation and no execution
    authorization.
    """

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    run_id: Optional[str] = None
    as_of: Optional[str] = None
    workflow_name: Optional[str] = None
    snapshot_id: Optional[str] = None
    notes: str = ""
    data_source: DataSourceTag = "absent"

    @model_validator(mode="after")
    def _validate(self) -> "CompanyIdentityView":
        if not self.target.strip():
            raise ValueError("'target' must not be whitespace-only.")
        return self


class MissingDataWarningView(BaseModel):
    """
    Surfaces missing-panel warnings deterministically.

    Each warning names which panel is missing and a short description.
    The Company Research Hub view degrades safely when a panel is absent:
    the corresponding panel view returns ``is_populated=False`` and one
    warning is appended here.
    """

    model_config = ConfigDict(extra="forbid")

    missing_panels: list[MissingDataPanel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EquityResearchPanelView(BaseModel):
    """
    Equity research panel projection.

    Mirrors the original README Equity page concerns (business model,
    moat, management, competitive landscape, peer comparison) by
    reference. Content lives in fixture-backed page outputs and Phase 4M
    research-run memory records. This view fabricates no narrative.
    """

    model_config = ConfigDict(extra="forbid")

    is_populated: bool = False
    target: str = Field(min_length=1)
    step_status: str = "unknown"
    summary: str = ""
    page_outputs: list[ExistingPageOutputRef] = Field(default_factory=list)
    research_run_memory_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    data_source: DataSourceTag = "absent"


class FinancialValuationPanelView(BaseModel):
    """
    Financial / valuation panel projection.

    Mirrors the original README Financial page concerns (financial
    statements, DCF / relative valuation, profitability / cash-flow
    quality, valuation reasonableness) by reference. Phase 4M-D
    allocation memory records are surfaced as valuation-reasonableness
    context only; this view does not recompute valuation numbers.
    """

    model_config = ConfigDict(extra="forbid")

    is_populated: bool = False
    target: str = Field(min_length=1)
    step_status: str = "unknown"
    summary: str = ""
    page_outputs: list[ExistingPageOutputRef] = Field(default_factory=list)
    allocation_memory_ids: list[str] = Field(default_factory=list)
    valuation_context_notes: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    data_source: DataSourceTag = "absent"


class PriceVolumeTimingPanelView(BaseModel):
    """
    Price/Volume timing panel projection.

    Mirrors the original README PriceVolume page concerns (K-line /
    price-volume context, RSI / MACD / ADX / Bollinger / SMA-style
    indicators where represented in existing fixtures, support /
    resistance / timing interpretation) by reference. The panel does not
    recompute indicators.
    """

    model_config = ConfigDict(extra="forbid")

    is_populated: bool = False
    target: str = Field(min_length=1)
    step_status: str = "unknown"
    summary: str = ""
    page_outputs: list[ExistingPageOutputRef] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    data_source: DataSourceTag = "absent"


class SourceWorkflowPanelView(BaseModel):
    """
    Source workflow panel projection.

    Surfaces which of the original five workflow steps are present, which
    are missing, and the synthesis summary when present. This panel is
    the cockpit-side mirror of the original Overview / Synthesis step.
    """

    model_config = ConfigDict(extra="forbid")

    workflow_name: Optional[str] = None
    present_step_keys: list[str] = Field(default_factory=list)
    missing_step_keys: list[str] = Field(default_factory=list)
    step_statuses: dict[str, str] = Field(default_factory=dict)
    synthesis_status: str = "unknown"
    synthesis_summary: str = ""
    synthesis_present: bool = False
    consolidated_report_ref: Optional[ExistingPageOutputRef] = None
    warnings: list[str] = Field(default_factory=list)
    data_source: DataSourceTag = "absent"


class EvidenceCoveragePanelView(BaseModel):
    """
    Evidence coverage panel projection.

    Aggregates deterministic counts of available source steps, missing
    source steps, evidence IDs by step, and memory record counts by type.
    Never claims complete evidence coverage unless the data supports it.
    """

    model_config = ConfigDict(extra="forbid")

    available_source_steps: list[str] = Field(default_factory=list)
    missing_source_steps: list[str] = Field(default_factory=list)
    available_memory_record_types: list[str] = Field(default_factory=list)
    memory_record_counts_by_type: dict[str, int] = Field(default_factory=dict)
    evidence_id_count_by_step: dict[str, int] = Field(default_factory=dict)
    total_evidence_id_count: int = 0
    total_memory_record_count: int = 0
    has_complete_step_coverage: bool = False
    has_any_memory_records: bool = False
    warnings: list[str] = Field(default_factory=list)


class ValidationStatusPanelView(BaseModel):
    """
    Validation status panel projection.

    Summarizes blocked / needs_review / review_required counts derived
    from Phase 4M memory records. This view never fabricates validation
    success: ``has_any_validation_signal`` is True only when at least one
    underlying memory record carries an explicit status, and
    ``is_clean`` is True only when no record is blocked / needs_review /
    review_required.
    """

    model_config = ConfigDict(extra="forbid")

    blocked_count: int = 0
    needs_review_count: int = 0
    review_required_count: int = 0
    inspected_record_count: int = 0
    record_status_counts: dict[str, int] = Field(default_factory=dict)
    has_any_validation_signal: bool = False
    is_clean: bool = False
    warnings: list[str] = Field(default_factory=list)


class CompanyResearchHubView(BaseModel):
    """
    Top-level Company Research Hub view-model.

    Aggregates the deterministic panels into a single Pydantic value.
    Safe degraded behavior: each panel reports ``is_populated`` (or
    ``synthesis_present`` for the source-workflow panel); missing
    panels are appended to the ``missing_data`` warning view rather
    than fabricated.

    No ``approved_for_execution`` flag — Phase 5B does not authorize
    execution. The underlying snapshot enforces ``False`` at its model
    layer; this view does not surface that field.
    """

    model_config = ConfigDict(extra="forbid")

    identity: CompanyIdentityView
    equity_panel: EquityResearchPanelView
    financial_panel: FinancialValuationPanelView
    price_volume_panel: PriceVolumeTimingPanelView
    source_workflow_panel: SourceWorkflowPanelView
    evidence_coverage_panel: EvidenceCoveragePanelView
    validation_status_panel: ValidationStatusPanelView
    missing_data: MissingDataWarningView = Field(default_factory=MissingDataWarningView)
    warnings: list[str] = Field(default_factory=list)
    calculation_version: str = _CALCULATION_VERSION


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------


def build_company_identity_view(
    target: str,
    snapshot: Optional[ExistingWorkflowSnapshot] = None,
    run_id: Optional[str] = None,
    as_of: Optional[str] = None,
) -> CompanyIdentityView:
    """Build a deterministic ``CompanyIdentityView``.

    When a snapshot is provided, its ``run_id`` / ``as_of`` /
    ``workflow_name`` / ``notes`` populate the view and ``data_source``
    becomes ``"existing_workflow_snapshot"``. Otherwise the view
    captures only the caller-provided identity coordinates.
    """
    if not target or not str(target).strip():
        raise ValueError("'target' must not be empty or whitespace-only.")

    if snapshot is not None:
        return CompanyIdentityView(
            target=snapshot.target if snapshot.target else target,
            run_id=run_id if run_id is not None else snapshot.run_id,
            as_of=as_of if as_of is not None else snapshot.as_of,
            workflow_name=snapshot.workflow_name,
            snapshot_id=make_workflow_snapshot_id(
                run_id=snapshot.run_id,
                target=snapshot.target,
                as_of=snapshot.as_of,
            ),
            notes=snapshot.notes,
            data_source="existing_workflow_snapshot",
        )

    return CompanyIdentityView(
        target=target,
        run_id=run_id,
        as_of=as_of,
        data_source="absent",
    )


def _build_panel_from_step(
    target: str,
    snapshot: Optional[ExistingWorkflowSnapshot],
    step_key: str,
) -> tuple[bool, str, str, list[ExistingPageOutputRef], list[str], list[str], list[str], DataSourceTag]:
    """Return common per-step fields used by Equity / Financial / PriceVolume panels."""
    if snapshot is None or step_key not in snapshot.steps:
        warnings = [
            f"No '{step_key}' step present in workflow snapshot; "
            "returning safe degraded panel."
        ]
        return (False, "unknown", "", [], [], [], warnings, "absent")
    step = snapshot.steps[step_key]
    return (
        True,
        str(step.status),
        step.summary,
        _step_output_refs(step),
        _step_evidence_ids(step),
        _step_artifact_refs(step),
        list(step.warnings),
        "existing_workflow_snapshot",
    )


def build_equity_research_panel(
    target: str,
    snapshot: Optional[ExistingWorkflowSnapshot] = None,
    memory_store: Optional[MemoryStoreProtocol] = None,
) -> EquityResearchPanelView:
    """Build the equity research panel projection."""
    (
        is_populated,
        step_status,
        summary,
        page_outputs,
        evidence_ids,
        artifact_refs,
        warnings,
        data_source,
    ) = _build_panel_from_step(target, snapshot, "equity")

    research_run_ids: list[str] = []
    if memory_store is not None and snapshot is not None:
        q = memory_store.query(MemoryQueryByTicker(target=snapshot.target))
        for r in q.research_run_records:
            mid = getattr(r, "memory_id", None)
            if mid and mid not in research_run_ids:
                research_run_ids.append(mid)

    return EquityResearchPanelView(
        is_populated=is_populated,
        target=target,
        step_status=step_status,
        summary=summary,
        page_outputs=page_outputs,
        research_run_memory_ids=research_run_ids,
        evidence_ids=evidence_ids,
        artifact_refs=artifact_refs,
        warnings=warnings,
        data_source=data_source,
    )


def build_financial_valuation_panel(
    target: str,
    snapshot: Optional[ExistingWorkflowSnapshot] = None,
    memory_store: Optional[MemoryStoreProtocol] = None,
) -> FinancialValuationPanelView:
    """Build the financial / valuation panel projection."""
    (
        is_populated,
        step_status,
        summary,
        page_outputs,
        evidence_ids,
        artifact_refs,
        warnings,
        data_source,
    ) = _build_panel_from_step(target, snapshot, "financial")

    allocation_ids: list[str] = []
    valuation_notes: list[str] = []
    if memory_store is not None and snapshot is not None:
        q = memory_store.query(MemoryQueryByTicker(target=snapshot.target))
        for r in q.allocation_records:
            aid = getattr(r, "allocation_memory_id", None)
            if aid and aid not in allocation_ids:
                allocation_ids.append(aid)
            rationale = getattr(r, "rationale", "")
            if rationale and rationale not in valuation_notes:
                valuation_notes.append(rationale)

    return FinancialValuationPanelView(
        is_populated=is_populated,
        target=target,
        step_status=step_status,
        summary=summary,
        page_outputs=page_outputs,
        allocation_memory_ids=allocation_ids,
        valuation_context_notes=valuation_notes,
        evidence_ids=evidence_ids,
        artifact_refs=artifact_refs,
        warnings=warnings,
        data_source=data_source,
    )


def build_price_volume_timing_panel(
    target: str,
    snapshot: Optional[ExistingWorkflowSnapshot] = None,
) -> PriceVolumeTimingPanelView:
    """Build the price/volume timing panel projection."""
    (
        is_populated,
        step_status,
        summary,
        page_outputs,
        evidence_ids,
        artifact_refs,
        warnings,
        data_source,
    ) = _build_panel_from_step(target, snapshot, "price_volume")

    return PriceVolumeTimingPanelView(
        is_populated=is_populated,
        target=target,
        step_status=step_status,
        summary=summary,
        page_outputs=page_outputs,
        evidence_ids=evidence_ids,
        artifact_refs=artifact_refs,
        warnings=warnings,
        data_source=data_source,
    )


def build_source_workflow_panel(
    snapshot: Optional[ExistingWorkflowSnapshot] = None,
) -> SourceWorkflowPanelView:
    """Build the source workflow / synthesis projection."""
    if snapshot is None:
        return SourceWorkflowPanelView(
            workflow_name=None,
            present_step_keys=[],
            missing_step_keys=list(WORKFLOW_STEP_ORDER),
            step_statuses={},
            synthesis_status="unknown",
            synthesis_summary="",
            synthesis_present=False,
            consolidated_report_ref=None,
            warnings=[
                "No workflow snapshot supplied; source workflow panel "
                "returned safe degraded view."
            ],
            data_source="absent",
        )

    present_keys = [s for s in WORKFLOW_STEP_ORDER if s in snapshot.steps]
    missing_keys = [s for s in WORKFLOW_STEP_ORDER if s not in snapshot.steps]

    step_statuses: dict[str, str] = {}
    for k in present_keys:
        step_statuses[k] = str(snapshot.steps[k].status)

    synthesis: Optional[ExistingWorkflowSynthesisSnapshot] = snapshot.synthesis
    synthesis_present = synthesis is not None
    synthesis_status = "unknown"
    synthesis_summary = ""
    consolidated_report_ref: Optional[ExistingPageOutputRef] = None
    panel_warnings: list[str] = []
    if synthesis is not None:
        synthesis_status = str(synthesis.status)
        synthesis_summary = synthesis.summary
        consolidated_report_ref = synthesis.consolidated_report_ref
        panel_warnings = list(synthesis.warnings)
    else:
        panel_warnings.append(
            "Synthesis step absent from workflow snapshot; "
            "source workflow panel returned safe degraded view."
        )

    return SourceWorkflowPanelView(
        workflow_name=snapshot.workflow_name,
        present_step_keys=present_keys,
        missing_step_keys=missing_keys,
        step_statuses=step_statuses,
        synthesis_status=synthesis_status,
        synthesis_summary=synthesis_summary,
        synthesis_present=synthesis_present,
        consolidated_report_ref=consolidated_report_ref,
        warnings=panel_warnings,
        data_source="existing_workflow_snapshot",
    )


def build_evidence_coverage_panel(
    snapshot: Optional[ExistingWorkflowSnapshot] = None,
    memory_query_result: Optional[MemoryQueryResult] = None,
) -> EvidenceCoveragePanelView:
    """Build the evidence coverage projection.

    The panel records:
      - which workflow steps are present (available source steps);
      - which are missing;
      - which Phase 4M memory record types are populated and their counts;
      - deterministic per-step evidence-ID counts.
    """
    if snapshot is None:
        available_steps: list[str] = []
        missing_steps: list[str] = list(WORKFLOW_STEP_ORDER)
        evidence_id_count_by_step: dict[str, int] = {}
        total_evidence_ids = 0
    else:
        available_steps = [s for s in WORKFLOW_STEP_ORDER if s in snapshot.steps]
        missing_steps = [s for s in WORKFLOW_STEP_ORDER if s not in snapshot.steps]
        evidence_id_count_by_step = {
            s: len(snapshot.steps[s].evidence_ids) for s in available_steps
        }
        total_evidence_ids = sum(evidence_id_count_by_step.values())

    available_record_types: list[str] = []
    record_counts_by_type: dict[str, int] = {rt: 0 for rt in MEMORY_RECORD_TYPES}
    total_memory_records = 0
    if memory_query_result is not None:
        counts = memory_query_result.count_by_type()
        for rt in MEMORY_RECORD_TYPES:
            c = int(counts.get(rt, 0))
            record_counts_by_type[rt] = c
            if c > 0 and rt not in available_record_types:
                available_record_types.append(rt)
            total_memory_records += c

    has_complete_step_coverage = (
        snapshot is not None and not missing_steps and len(available_steps) == len(WORKFLOW_STEP_ORDER)
    )

    warnings: list[str] = []
    if snapshot is None:
        warnings.append(
            "No workflow snapshot supplied; evidence coverage based on memory "
            "store records only."
        )
    if missing_steps:
        warnings.append(
            "Evidence coverage incomplete: missing workflow step(s) "
            f"{missing_steps}."
        )
    if memory_query_result is None:
        warnings.append(
            "No memory query result supplied; memory record counts default "
            "to zero."
        )

    return EvidenceCoveragePanelView(
        available_source_steps=available_steps,
        missing_source_steps=missing_steps,
        available_memory_record_types=available_record_types,
        memory_record_counts_by_type=record_counts_by_type,
        evidence_id_count_by_step=evidence_id_count_by_step,
        total_evidence_id_count=total_evidence_ids,
        total_memory_record_count=total_memory_records,
        has_complete_step_coverage=has_complete_step_coverage,
        has_any_memory_records=total_memory_records > 0,
        warnings=warnings,
    )


def build_validation_status_panel(
    memory_query_result: Optional[MemoryQueryResult] = None,
) -> ValidationStatusPanelView:
    """Build the validation status panel projection.

    Never fabricates validation success. ``is_clean`` is True only when
    we actually inspected at least one record and none flagged blocked /
    needs_review / review_required.
    """
    blocked = 0
    needs_review = 0
    review_required = 0
    record_status_counts: dict[str, int] = {}
    inspected = 0

    if memory_query_result is not None:
        for r in _result_iter_records(memory_query_result):
            inspected += 1
            status = _record_status_str(r)
            if status:
                record_status_counts[status] = record_status_counts.get(status, 0) + 1
            if status == "blocked":
                blocked += 1
            elif status == "needs_review":
                needs_review += 1
            if _is_review_required(r):
                review_required += 1

    has_any = inspected > 0
    warnings: list[str] = []
    if not has_any:
        warnings.append(
            "No memory records inspected; validation status panel cannot "
            "claim validation success."
        )

    is_clean = (
        has_any and blocked == 0 and needs_review == 0 and review_required == 0
    )

    return ValidationStatusPanelView(
        blocked_count=blocked,
        needs_review_count=needs_review,
        review_required_count=review_required,
        inspected_record_count=inspected,
        record_status_counts=record_status_counts,
        has_any_validation_signal=has_any,
        is_clean=is_clean,
        warnings=warnings,
    )


def _collect_missing_data_warnings(
    *,
    snapshot: Optional[ExistingWorkflowSnapshot],
    equity_panel: EquityResearchPanelView,
    financial_panel: FinancialValuationPanelView,
    price_volume_panel: PriceVolumeTimingPanelView,
    source_workflow_panel: SourceWorkflowPanelView,
) -> MissingDataWarningView:
    """Aggregate missing-panel warnings deterministically."""
    missing: list[MissingDataPanel] = []
    warnings: list[str] = []
    if snapshot is None:
        missing.append("identity")
        warnings.append(
            "No workflow snapshot supplied; Company Research Hub view returned "
            "safe empty/degraded state."
        )
    if not equity_panel.is_populated:
        missing.append("equity")
        warnings.append(
            "Equity research panel missing; returned safe degraded panel."
        )
    if not financial_panel.is_populated:
        missing.append("financial")
        warnings.append(
            "Financial valuation panel missing; returned safe degraded panel."
        )
    if not price_volume_panel.is_populated:
        missing.append("price_volume")
        warnings.append(
            "Price/Volume timing panel missing; returned safe degraded panel."
        )
    if not source_workflow_panel.synthesis_present:
        missing.append("synthesis")
        warnings.append(
            "Synthesis step missing; source workflow panel returned safe "
            "degraded view."
        )
    return MissingDataWarningView(
        missing_panels=missing,
        warnings=warnings,
    )


def build_company_research_hub_view(
    target: str,
    snapshot: Optional[ExistingWorkflowSnapshot] = None,
    memory_store: Optional[MemoryStoreProtocol] = None,
    memory_query_result: Optional[MemoryQueryResult] = None,
    run_id: Optional[str] = None,
    as_of: Optional[str] = None,
) -> CompanyResearchHubView:
    """Build a deterministic ``CompanyResearchHubView``.

    Inputs
    ------
    target : str
        Ticker / research target identifier. Required.
    snapshot : ExistingWorkflowSnapshot, optional
        Phase 5A snapshot describing one original five-step workflow run.
        When absent, panels degrade to safe empty/unpopulated state.
    memory_store : MemoryStoreProtocol, optional
        Phase 5A memory store (e.g. ``FixtureBackedMemoryStore``) used to
        scope memory records to the target. When absent, no memory
        records are surfaced.
    memory_query_result : MemoryQueryResult, optional
        Optional pre-computed query result to use for evidence /
        validation aggregation. When omitted and ``memory_store`` is
        provided, a target-scoped query is run internally.
    run_id, as_of : str, optional
        Identity overrides; ``snapshot`` values take precedence when
        absent.

    Returns
    -------
    CompanyResearchHubView
        Top-level cockpit-ready view aggregating identity + equity +
        financial + price/volume + source workflow + evidence coverage
        + validation status + missing-data warnings.

    The function fabricates no narrative, no recommendation, no trade
    instruction, and exposes no ``approved_for_execution`` flag.
    """
    if not target or not str(target).strip():
        raise ValueError("'target' must not be empty or whitespace-only.")

    if memory_query_result is None and memory_store is not None:
        memory_query_result = _query_result_for_target(memory_store, target)

    identity = build_company_identity_view(
        target=target,
        snapshot=snapshot,
        run_id=run_id,
        as_of=as_of,
    )

    equity_panel = build_equity_research_panel(
        target=target, snapshot=snapshot, memory_store=memory_store
    )
    financial_panel = build_financial_valuation_panel(
        target=target, snapshot=snapshot, memory_store=memory_store
    )
    price_volume_panel = build_price_volume_timing_panel(
        target=target, snapshot=snapshot
    )
    source_workflow_panel = build_source_workflow_panel(snapshot=snapshot)
    evidence_coverage_panel = build_evidence_coverage_panel(
        snapshot=snapshot, memory_query_result=memory_query_result
    )
    validation_status_panel = build_validation_status_panel(
        memory_query_result=memory_query_result
    )

    missing_data = _collect_missing_data_warnings(
        snapshot=snapshot,
        equity_panel=equity_panel,
        financial_panel=financial_panel,
        price_volume_panel=price_volume_panel,
        source_workflow_panel=source_workflow_panel,
    )

    view_warnings: list[str] = []
    if memory_store is None and memory_query_result is None:
        view_warnings.append(
            "No memory store or query result supplied; Company Research "
            "Hub view returned without memory-backed evidence."
        )

    return CompanyResearchHubView(
        identity=identity,
        equity_panel=equity_panel,
        financial_panel=financial_panel,
        price_volume_panel=price_volume_panel,
        source_workflow_panel=source_workflow_panel,
        evidence_coverage_panel=evidence_coverage_panel,
        validation_status_panel=validation_status_panel,
        missing_data=missing_data,
        warnings=view_warnings,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Literal aliases
    "MissingDataPanel",
    "DataSourceTag",
    # View models
    "CompanyIdentityView",
    "EquityResearchPanelView",
    "FinancialValuationPanelView",
    "PriceVolumeTimingPanelView",
    "SourceWorkflowPanelView",
    "EvidenceCoveragePanelView",
    "ValidationStatusPanelView",
    "MissingDataWarningView",
    "CompanyResearchHubView",
    # Builders
    "build_company_identity_view",
    "build_equity_research_panel",
    "build_financial_valuation_panel",
    "build_price_volume_timing_panel",
    "build_source_workflow_panel",
    "build_evidence_coverage_panel",
    "build_validation_status_panel",
    "build_company_research_hub_view",
]
