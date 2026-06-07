"""
lib/reliability/phase5_demo_pack.py

Phase 5G: Fixture Demo Pack Based on Original App Flow.

Purpose
-------
Provides a deterministic, fixture/demo-only Cockpit Demo Pack that simulates
the original README five-step Streamlit workflow end-to-end and feeds the
Phase 5A–5D overlay contracts. Phase 5G is intended to support future
Phase 5H Controlled Streamlit Cockpit UI Integration v0.1, but Phase 5G
itself never builds UI, never wires into the live app, and never enables
execution.

Coverage
--------
The default demo pack includes two scenarios:

  1. Complete scenario (``FIXTKR``)
       - all five workflow steps (sector / scanner / equity / financial /
         price_volume) plus synthesis,
       - one ResearchRunMemoryRecord (Phase 4M-A),
       - three thesis records (Phase 4M-B) — short / medium / long,
       - one event memory record (Phase 4M-C),
       - one allocation decision memory record (Phase 4M-D),
       - one option trade plan memory record (Phase 4M-E) with
         ``approved_for_execution=False``,
       - one human feedback memory record (Phase 4M-F),
       - one agent evaluation memory record (Phase 4M-G).

  2. Degraded scenario (``FIXDEG``)
       - missing the ``financial`` workflow step (safe degraded panel
         in Phase 5B),
       - thesis records for short + medium horizons only (the long
         horizon card surfaces as a safe ``"missing"`` Phase 5C card),
       - one allocation record + one ``no_trade`` option trade plan
         memory record (preserves ``no_trade`` as a first-class option
         overlay state in Phase 5D).

Design principles
-----------------
- Standalone, deterministic, offline / mock-only.
- No live LLM calls, no live data fetching, no Streamlit, no Anthropic
  SDK calls.
- No database writes, no file persistence, no vector store.
- No reading of the live workflow state JSON file.
- No import of ``app.py``, ``pages/*``, ``lib/llm_orchestrator.py``, or
  ``lib/workflow_state.py``.
- No broker / order / execution behavior.
- No order type, time-in-force, broker route, account ID, executable
  quantity, broker payload, order ticket, execution ID, fill price, or
  any other executable order field.
- ``approved_for_execution`` is never positively authorized — every
  underlying record carries ``False`` (or absent) and the demo-only
  safety banner reasserts the invariant explicitly.
- Phase 5G never modifies live runtime files. Phase 4A integration
  boundary remains frozen and is not imported.

Relationship to other phases
----------------------------
- Phase 4M-A through 4M-G memory records are reused (not redefined).
- Phase 5A ``FixtureBackedMemoryStore`` + ``MemoryQueryByTicker`` etc.
  power the demo pack's memory-query layer.
- Phase 5B ``CompanyResearchHubView`` mirrors each scenario's identity
  and panels.
- Phase 5C ``HorizonDecisionCardsView`` + ``ThesisTrackerView`` mirror
  each scenario's per-horizon decision state.
- Phase 5D ``PortfolioCockpitView`` mirrors each scenario's allocation /
  trade plan / option overlay surfaces (with the execution-safety
  banner always present).

See ``docs/reliability_phase_5g_cockpit_demo_pack.md``.

Disclaimer
----------
Outputs are for research / educational purposes only and do not
constitute investment advice.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.research_memory import (
    MemorySourceRef,
    ResearchRunMemoryInputBundle,
    ResearchRunMemoryRecord,
    build_research_run_memory_record,
)
from lib.reliability.thesis_memory import (
    HorizonThesisMemoryRecord,
    ThesisAssumption,
    ThesisInvalidationCondition,
    build_horizon_thesis_memory_record,
)
from lib.reliability.event_memory import (
    EventMemoryRecord,
    EventMemorySourceRef,
    build_event_memory_record,
)
from lib.reliability.allocation_memory import (
    AllocationDecisionMemoryRecord,
    AllocationMemorySourceRef,
    build_allocation_decision_snapshot,
    build_allocation_memory_record,
)
from lib.reliability.option_trade_memory import (
    OptionTradePlanMemoryRecord,
    build_option_trade_memory_record,
    build_option_trade_plan_snapshot,
)
from lib.reliability.human_feedback_memory import (
    HumanFeedbackEntry,
    HumanFeedbackMemoryRecord,
    HumanFeedbackTargetRef,
    build_human_feedback_entry,
    build_human_feedback_memory_record,
    build_human_feedback_target_ref,
)
from lib.reliability.agent_evaluation import (
    AgentEvaluationRecord,
    AgentEvaluationSignal,
    build_agent_evaluation_record,
    build_agent_evaluation_signal,
    build_agent_evaluation_target_ref,
)
from lib.reliability.workflow_memory_adapter import (
    ExistingPageOutputRef,
    ExistingWorkflowSnapshot,
    ExistingWorkflowStepSnapshot,
    ExistingWorkflowSynthesisSnapshot,
    InMemoryWorkflowToMemoryAdapter,
    WORKFLOW_STEP_ORDER,
    WorkflowMemoryBundle,
)
from lib.reliability.phase5_memory_query import (
    FixtureBackedMemoryStore,
    MemoryQueryByTicker,
    MemoryQueryResult,
)
from lib.reliability.company_research_hub import (
    CompanyResearchHubView,
    build_company_research_hub_view,
)
from lib.reliability.phase5_horizon_views import (
    HORIZON_ORDER,
    HorizonDecisionCardsView,
    ThesisTrackerView,
    build_horizon_decision_cards_view,
    build_thesis_tracker_view,
)
from lib.reliability.phase5_portfolio_views import (
    PortfolioCockpitView,
    build_portfolio_cockpit_view,
)


# ---------------------------------------------------------------------------
# Literal aliases / constants
# ---------------------------------------------------------------------------

DemoScenarioKind = Literal["complete", "degraded"]

DEMO_SCENARIO_ORDER: tuple[DemoScenarioKind, ...] = ("complete", "degraded")

_CALCULATION_VERSION: str = "phase5_demo_pack_v1"

# Tickers are clearly fixture-only; not real NYSE/NASDAQ symbols.
SAMPLE_DEMO_COMPLETE_TICKER: str = "FIXTKR"
SAMPLE_DEMO_DEGRADED_TICKER: str = "FIXDEG"

SAMPLE_DEMO_COMPLETE_RUN_ID: str = "FIXTKR_20260524_120000_fix5g_complete"
SAMPLE_DEMO_DEGRADED_RUN_ID: str = "FIXDEG_20260524_120100_fix5g_degraded"
SAMPLE_DEMO_AS_OF: str = "2026-05-24T12:00:00+00:00"

# Demo-only safety banner copy. Mirrors Phase 5D's execution-safety banner
# but adds Phase 5G-specific demo-pack provenance and non-wiring statements.
_DEMO_SAFETY_BANNER_TEXT: str = (
    "Fixture/demo-only Cockpit Demo Pack. This pack does NOT represent a "
    "live workflow run. It does NOT call any external API, LLM, broker, "
    "or order routing system. It does NOT authorize execution. No "
    "executable order fields, time-in-force, broker route, account ID, "
    "or order ticket are exposed. No investment advice. "
    "approved_for_execution is False everywhere. Human review is required "
    "before any real-world action."
)


# ---------------------------------------------------------------------------
# View models
# ---------------------------------------------------------------------------


class DemoSafetyBanner(BaseModel):
    """
    Demo-only safety banner attached to a ``CockpitDemoPack`` and to each
    ``CockpitDemoScenario``.

    Phase 5G's banner is intentionally distinct from Phase 5D's
    ``ExecutionSafetyBannerView``: Phase 5G adds explicit demo-only and
    no-live-wiring statements on top of the non-execution invariant.
    """

    model_config = ConfigDict(extra="forbid")

    is_demo_only: bool = True
    is_non_executable: bool = True
    requires_human_review: bool = True
    no_live_workflow_wiring: bool = True
    no_external_api: bool = True
    no_broker_or_order: bool = True
    no_investment_advice: bool = True
    approved_for_execution: bool = False
    message: str = _DEMO_SAFETY_BANNER_TEXT

    @model_validator(mode="after")
    def _validate(self) -> "DemoSafetyBanner":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 5G "
                "demo packs."
            )
        return self


class DemoDataProvenance(BaseModel):
    """
    Demo-only provenance metadata.

    Captures the deterministic, fixture-only origin of the demo pack:
    Phase 5G generator version, fixture ticker(s), the demo as_of date,
    and an explicit statement that no live data was used.
    """

    model_config = ConfigDict(extra="forbid")

    generator: str = "phase5_demo_pack"
    generator_version: str = _CALCULATION_VERSION
    is_fixture_only: bool = True
    uses_live_data: bool = False
    uses_external_api: bool = False
    uses_live_workflow_state: bool = False
    uses_llm: bool = False
    uses_broker: bool = False
    fixture_tickers: list[str] = Field(default_factory=list)
    as_of: Optional[str] = None
    notes: str = (
        "Phase 5G fixture/demo pack only. No live workflow read, no live "
        "API, no live broker call."
    )


class DemoScenarioMetadata(BaseModel):
    """
    Metadata for one demo scenario inside the demo pack.
    """

    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)
    scenario_kind: DemoScenarioKind = "complete"
    title: str = Field(min_length=1)
    description: str = ""
    ticker: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    as_of: Optional[str] = None
    safety_banner: DemoSafetyBanner = Field(default_factory=DemoSafetyBanner)
    provenance: DemoDataProvenance = Field(default_factory=DemoDataProvenance)

    @model_validator(mode="after")
    def _validate(self) -> "DemoScenarioMetadata":
        for fn in ("scenario_id", "title", "ticker", "run_id"):
            v = getattr(self, fn)
            if not str(v).strip():
                raise ValueError(
                    f"'{fn}' must not be whitespace-only; got {v!r}."
                )
        if self.scenario_kind not in DEMO_SCENARIO_ORDER:
            raise ValueError(
                f"scenario_kind must be one of {DEMO_SCENARIO_ORDER}; "
                f"got {self.scenario_kind!r}."
            )
        return self


class OriginalWorkflowDemoFixture(BaseModel):
    """
    Demo container for one original-app five-step workflow journey.

    Holds the deterministic snapshot, the corresponding Phase 5A
    in-memory adapter, and the resulting ``WorkflowMemoryBundle``. The
    snapshot exposes its present step keys via ``snapshot.step_keys()``;
    callers can verify per-step coverage without inspecting internals.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    ticker: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    snapshot: ExistingWorkflowSnapshot
    adapter: InMemoryWorkflowToMemoryAdapter = Field(exclude=True)
    bundle: WorkflowMemoryBundle
    present_step_keys: list[str] = Field(default_factory=list)
    missing_step_keys: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> "OriginalWorkflowDemoFixture":
        if self.snapshot.approved_for_execution:
            raise ValueError(
                "OriginalWorkflowDemoFixture snapshot must have "
                "approved_for_execution=False."
            )
        if self.bundle.approved_for_execution:
            raise ValueError(
                "OriginalWorkflowDemoFixture bundle must have "
                "approved_for_execution=False."
            )
        return self


class MemoryDemoFixtureBundle(BaseModel):
    """
    Demo container for Phase 4M memory records and their backing Phase 5A
    fixture store.

    Holds the deterministic memory records (research run / thesis / event /
    allocation / option trade plan / human feedback / agent evaluation) and
    the in-memory ``FixtureBackedMemoryStore`` that view-models query.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    ticker: str = Field(min_length=1)
    research_run_memory: Optional[ResearchRunMemoryRecord] = None
    thesis_records: list[HorizonThesisMemoryRecord] = Field(default_factory=list)
    event_records: list[EventMemoryRecord] = Field(default_factory=list)
    allocation_records: list[AllocationDecisionMemoryRecord] = Field(
        default_factory=list
    )
    option_trade_records: list[OptionTradePlanMemoryRecord] = Field(
        default_factory=list
    )
    human_feedback_records: list[HumanFeedbackMemoryRecord] = Field(
        default_factory=list
    )
    agent_evaluation_records: list[AgentEvaluationRecord] = Field(
        default_factory=list
    )
    memory_store: FixtureBackedMemoryStore = Field(exclude=True)
    memory_query_result: MemoryQueryResult

    @model_validator(mode="after")
    def _validate(self) -> "MemoryDemoFixtureBundle":
        if self.memory_query_result.approved_for_execution:
            raise ValueError(
                "MemoryDemoFixtureBundle memory_query_result must have "
                "approved_for_execution=False."
            )
        return self


class CockpitViewDemoBundle(BaseModel):
    """
    Demo container for the Phase 5B / 5C / 5D view-models derived from one
    scenario's memory bundle.

    Notes
    -----
    ``thesis_tracker_view`` covers only the scenario's primary ticker. The
    cockpit may compose multi-target tracker views from multiple demo
    scenarios externally; Phase 5G does not authorize cross-scenario
    aggregation.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    company_research_hub_view: CompanyResearchHubView
    horizon_decision_cards_view: HorizonDecisionCardsView
    thesis_tracker_view: ThesisTrackerView
    portfolio_cockpit_view: PortfolioCockpitView


class CockpitDemoScenario(BaseModel):
    """
    One complete demo scenario: metadata + original workflow fixture +
    Phase 4M memory bundle + Phase 5B/5C/5D view-models.

    The scenario is the unit of demo coverage. Each scenario remains
    self-contained and deterministic; cross-scenario interaction is not
    supported by Phase 5G.
    """

    model_config = ConfigDict(extra="forbid")

    metadata: DemoScenarioMetadata
    workflow_fixture: OriginalWorkflowDemoFixture
    memory_fixture: MemoryDemoFixtureBundle
    view_bundle: CockpitViewDemoBundle
    warnings: list[str] = Field(default_factory=list)


class DemoPackValidationSummary(BaseModel):
    """
    Aggregate validation summary for a built demo pack.

    Asserts the structural invariants Phase 5G guarantees: scenario count,
    scenario kinds present, presence of the required Phase 4M record types
    per scenario, presence of the original five-step workflow plus
    synthesis (with a tracked missing step for the degraded scenario), and
    the global ``approved_for_execution=False`` invariant.
    """

    model_config = ConfigDict(extra="forbid")

    scenario_count: int = 0
    scenario_kinds: list[DemoScenarioKind] = Field(default_factory=list)
    has_complete_scenario: bool = False
    has_degraded_scenario: bool = False
    all_approved_for_execution_false: bool = True
    no_executable_order_fields: bool = True
    safety_banner_present: bool = False
    provenance_present: bool = False
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class CockpitDemoPack(BaseModel):
    """
    Top-level Phase 5G Cockpit Demo Pack.

    Aggregates one or more ``CockpitDemoScenario`` values, plus pack-level
    provenance and safety banner. Validation surface is exposed through
    ``validation_summary``; callers can inspect any scenario individually.
    """

    model_config = ConfigDict(extra="forbid")

    pack_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    scenarios: list[CockpitDemoScenario] = Field(default_factory=list)
    safety_banner: DemoSafetyBanner = Field(default_factory=DemoSafetyBanner)
    provenance: DemoDataProvenance = Field(default_factory=DemoDataProvenance)
    validation_summary: DemoPackValidationSummary = Field(
        default_factory=DemoPackValidationSummary
    )
    warnings: list[str] = Field(default_factory=list)
    calculation_version: str = _CALCULATION_VERSION

    @model_validator(mode="after")
    def _validate(self) -> "CockpitDemoPack":
        if not self.scenarios:
            raise ValueError(
                "CockpitDemoPack must contain at least one scenario."
            )
        return self


# ---------------------------------------------------------------------------
# Builders — safety / provenance / metadata
# ---------------------------------------------------------------------------


def build_demo_safety_banner() -> DemoSafetyBanner:
    """Build the deterministic Phase 5G demo-only safety banner."""
    return DemoSafetyBanner()


def build_demo_data_provenance(
    fixture_tickers: list[str],
    as_of: Optional[str] = SAMPLE_DEMO_AS_OF,
) -> DemoDataProvenance:
    """Build the deterministic Phase 5G demo provenance record."""
    return DemoDataProvenance(
        fixture_tickers=list(fixture_tickers),
        as_of=as_of,
    )


def build_demo_scenario_metadata(
    scenario_kind: DemoScenarioKind,
    ticker: str,
    run_id: str,
    title: str,
    description: str = "",
    as_of: Optional[str] = SAMPLE_DEMO_AS_OF,
) -> DemoScenarioMetadata:
    """Build a deterministic ``DemoScenarioMetadata`` value."""
    scenario_id = f"phase5g_scenario_{scenario_kind}_{ticker}"
    return DemoScenarioMetadata(
        scenario_id=scenario_id,
        scenario_kind=scenario_kind,
        title=title,
        description=description,
        ticker=ticker,
        run_id=run_id,
        as_of=as_of,
        safety_banner=build_demo_safety_banner(),
        provenance=build_demo_data_provenance(
            fixture_tickers=[ticker], as_of=as_of
        ),
    )


# ---------------------------------------------------------------------------
# Builders — workflow snapshot fixtures
# ---------------------------------------------------------------------------


def _step(
    name: str,
    page: str,
    summary: str,
    artifact_id: str,
    report_path: str,
    evidence_id: str,
) -> ExistingWorkflowStepSnapshot:
    return ExistingWorkflowStepSnapshot(
        step=name,  # type: ignore[arg-type]
        status="complete",
        summary=summary,
        page_outputs=[
            ExistingPageOutputRef(
                page=page,
                step=name,  # type: ignore[arg-type]
                artifact_id=artifact_id,
                report_path=report_path,
                description=f"Phase 5G fixture {name} page output.",
            )
        ],
        evidence_ids=[evidence_id],
        artifact_refs=[artifact_id],
    )


def _make_complete_workflow_snapshot(
    ticker: str = SAMPLE_DEMO_COMPLETE_TICKER,
    run_id: str = SAMPLE_DEMO_COMPLETE_RUN_ID,
    as_of: str = SAMPLE_DEMO_AS_OF,
) -> ExistingWorkflowSnapshot:
    return ExistingWorkflowSnapshot(
        run_id=run_id,
        target=ticker,
        as_of=as_of,
        workflow_name="five_step_research_workflow",
        steps={
            "sector": _step(
                "sector",
                "Sector",
                "Demo sector analysis output (Phase 5G complete scenario).",
                "fix5g_complete_sector_artifact",
                "research/sector/fix5g_complete_sector.md",
                "fix5g_complete_evid_sector",
            ),
            "scanner": _step(
                "scanner",
                "Scanner",
                "Demo scanner output (Phase 5G complete scenario).",
                "fix5g_complete_scanner_artifact",
                "research/scans/fix5g_complete_scan.md",
                "fix5g_complete_evid_scanner",
            ),
            "equity": _step(
                "equity",
                "Equity",
                "Demo equity research output (Phase 5G complete scenario).",
                "fix5g_complete_equity_artifact",
                "research/stock/fix5g_complete_equity.md",
                "fix5g_complete_evid_equity",
            ),
            "financial": _step(
                "financial",
                "Financial",
                "Demo financial analysis output (Phase 5G complete scenario).",
                "fix5g_complete_financial_artifact",
                "research/stock/fix5g_complete_financial.md",
                "fix5g_complete_evid_financial",
            ),
            "price_volume": _step(
                "price_volume",
                "PriceVolume",
                "Demo price/volume output (Phase 5G complete scenario).",
                "fix5g_complete_pv_artifact",
                "research/stock/fix5g_complete_pv.md",
                "fix5g_complete_evid_pv",
            ),
            "synthesis": _step(
                "synthesis",
                "Overview",
                "Demo synthesis output (Phase 5G complete scenario).",
                "fix5g_complete_synthesis_artifact",
                "research/stock/fix5g_complete_synthesis.md",
                "fix5g_complete_evid_synthesis",
            ),
        },
        synthesis=ExistingWorkflowSynthesisSnapshot(
            status="complete",
            summary=(
                "Demo five-step synthesis (Phase 5G complete scenario, "
                "fixture only)."
            ),
            consolidated_report_ref=ExistingPageOutputRef(
                page="Overview",
                step="synthesis",
                artifact_id="fix5g_complete_synthesis_artifact",
                report_path="research/stock/fix5g_complete_synthesis.md",
                description="Demo consolidated synthesis output.",
            ),
            artifact_refs=["fix5g_complete_synthesis_artifact"],
        ),
        notes=(
            "Phase 5G complete-scenario fixture only — does not represent a "
            "live research run."
        ),
    )


def _make_degraded_workflow_snapshot(
    ticker: str = SAMPLE_DEMO_DEGRADED_TICKER,
    run_id: str = SAMPLE_DEMO_DEGRADED_RUN_ID,
    as_of: str = SAMPLE_DEMO_AS_OF,
) -> ExistingWorkflowSnapshot:
    """Degraded scenario snapshot — intentionally missing the ``financial``
    step to demonstrate the Phase 5B safe degraded panel behavior.
    """
    return ExistingWorkflowSnapshot(
        run_id=run_id,
        target=ticker,
        as_of=as_of,
        workflow_name="five_step_research_workflow",
        steps={
            "sector": _step(
                "sector",
                "Sector",
                "Demo sector analysis output (Phase 5G degraded scenario).",
                "fix5g_degraded_sector_artifact",
                "research/sector/fix5g_degraded_sector.md",
                "fix5g_degraded_evid_sector",
            ),
            "scanner": _step(
                "scanner",
                "Scanner",
                "Demo scanner output (Phase 5G degraded scenario).",
                "fix5g_degraded_scanner_artifact",
                "research/scans/fix5g_degraded_scan.md",
                "fix5g_degraded_evid_scanner",
            ),
            "equity": _step(
                "equity",
                "Equity",
                "Demo equity research output (Phase 5G degraded scenario).",
                "fix5g_degraded_equity_artifact",
                "research/stock/fix5g_degraded_equity.md",
                "fix5g_degraded_evid_equity",
            ),
            # financial step intentionally omitted
            "price_volume": _step(
                "price_volume",
                "PriceVolume",
                "Demo price/volume output (Phase 5G degraded scenario).",
                "fix5g_degraded_pv_artifact",
                "research/stock/fix5g_degraded_pv.md",
                "fix5g_degraded_evid_pv",
            ),
            "synthesis": _step(
                "synthesis",
                "Overview",
                "Demo synthesis output (Phase 5G degraded scenario).",
                "fix5g_degraded_synthesis_artifact",
                "research/stock/fix5g_degraded_synthesis.md",
                "fix5g_degraded_evid_synthesis",
            ),
        },
        synthesis=ExistingWorkflowSynthesisSnapshot(
            status="complete",
            summary=(
                "Demo five-step synthesis (Phase 5G degraded scenario, "
                "fixture only). Note: financial step omitted to demonstrate "
                "safe degraded behavior."
            ),
            consolidated_report_ref=ExistingPageOutputRef(
                page="Overview",
                step="synthesis",
                artifact_id="fix5g_degraded_synthesis_artifact",
                report_path="research/stock/fix5g_degraded_synthesis.md",
                description="Demo consolidated synthesis output (degraded).",
            ),
            artifact_refs=["fix5g_degraded_synthesis_artifact"],
        ),
        notes=(
            "Phase 5G degraded-scenario fixture only — missing financial "
            "step and missing long-horizon thesis."
        ),
    )


# ---------------------------------------------------------------------------
# Builders — Phase 4M memory records
# ---------------------------------------------------------------------------


def _make_research_run_memory(
    snapshot: ExistingWorkflowSnapshot,
    id_prefix: str,
) -> ResearchRunMemoryRecord:
    bundle = ResearchRunMemoryInputBundle(
        run_id=snapshot.run_id,
        target=snapshot.target,
        as_of=snapshot.as_of,
        workflow_name="five_step_research_workflow",
        source_refs=[
            MemorySourceRef(
                source_id=f"{id_prefix}_step_{step}",
                source_type="orchestration",
                run_id=snapshot.run_id,
                target=snapshot.target,
                label=f"Phase 5G fixture {step} source ref",
            )
            for step in snapshot.step_keys()
        ],
        evidence_ids=[f"{id_prefix}_evid_{step}" for step in snapshot.step_keys()],
        artifact_refs=[
            f"{id_prefix}_artifact_{step}" for step in snapshot.step_keys()
        ],
    )
    return build_research_run_memory_record(
        bundle,
        created_at=snapshot.as_of,
        updated_at=snapshot.as_of,
    )


def _make_thesis_record(
    snapshot: ExistingWorkflowSnapshot,
    horizon: str,
    direction: str,
    confidence: str,
    text: str,
    id_prefix: str,
) -> HorizonThesisMemoryRecord:
    return build_horizon_thesis_memory_record(
        target=snapshot.target,
        thesis_text=text,
        horizon=horizon,  # type: ignore[arg-type]
        direction=direction,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        assumptions=[
            ThesisAssumption(
                assumption_id=f"{id_prefix}_assump_{horizon}_1",
                description=(
                    f"Phase 5G {horizon} assumption (fixture only)."
                ),
                horizon=horizon,  # type: ignore[arg-type]
                importance="medium",
            )
        ],
        invalidation_conditions=[
            ThesisInvalidationCondition(
                condition_id=f"{id_prefix}_invalid_{horizon}_1",
                invalidation_type=(
                    "technical"
                    if horizon == "short"
                    else "fundamental"
                    if horizon == "long"
                    else "earnings"
                ),
                description=(
                    f"Phase 5G {horizon} invalidation condition (fixture only)."
                ),
                horizon=horizon,  # type: ignore[arg-type]
            )
        ],
        run_id=snapshot.run_id,
        source_ids=[f"{id_prefix}_step_synthesis"],
        evidence_ids=[f"{id_prefix}_evid_{horizon}"],
        created_at=snapshot.as_of,
        updated_at=snapshot.as_of,
    )


def _make_event_record(
    snapshot: ExistingWorkflowSnapshot,
    thesis_id: Optional[str],
    id_prefix: str,
) -> EventMemoryRecord:
    return build_event_memory_record(
        target=snapshot.target,
        event_name=f"Phase 5G {id_prefix} mock earnings event (fixture only)",
        summary="Phase 5G fixture earnings event for the demo scenario.",
        event_type="earnings",
        impact_direction="neutral",
        impact_magnitude="medium",
        review_status="reviewed",
        thesis_changing=False,
        affected_horizons=["short", "medium"],
        market_reaction="Stable price action (fixture only).",
        guidance_update="Maintained prior guidance (fixture only).",
        event_date="2026-04-30",
        run_id=snapshot.run_id,
        thesis_id=thesis_id,
        source_refs=[
            EventMemorySourceRef(
                source_id=f"{id_prefix}_event_src_1",
                source_type="event_intelligence",
                label="Phase 5G event intelligence source ref",
            )
        ],
        evidence_ids=[f"{id_prefix}_evid_event"],
        recorded_at=snapshot.as_of,
    )


def _make_allocation_record(
    snapshot: ExistingWorkflowSnapshot,
    thesis_id: Optional[str],
    id_prefix: str,
) -> AllocationDecisionMemoryRecord:
    decision_snapshot = build_allocation_decision_snapshot(
        target=snapshot.target,
        target_allocation_pct=0.05,
        actual_allocation_pct=0.04,
        min_allocation_pct=0.02,
        max_allocation_pct=0.07,
        cash_pct=0.20,
        risk_level="medium",
        as_of=snapshot.as_of,
    )
    return build_allocation_memory_record(
        target=snapshot.target,
        action="add",
        rationale=(
            f"Phase 5G {id_prefix} allocation rationale (fixture only)."
        ),
        decision_snapshot=decision_snapshot,
        review_status="reviewed",
        outcome="pending",
        run_id=snapshot.run_id,
        thesis_id=thesis_id,
        source_refs=[
            AllocationMemorySourceRef(
                source_id=f"{id_prefix}_alloc_src_1",
                source_type="allocation_report",
                label="Phase 5G allocation source ref",
            )
        ],
        evidence_ids=[f"{id_prefix}_evid_alloc"],
        recorded_at=snapshot.as_of,
    )


def _make_option_trade_record(
    snapshot: ExistingWorkflowSnapshot,
    thesis_id: Optional[str],
    allocation_memory_id: Optional[str],
    id_prefix: str,
    *,
    no_trade: bool = False,
) -> OptionTradePlanMemoryRecord:
    if no_trade:
        plan_snapshot = build_option_trade_plan_snapshot(
            target=snapshot.target,
            decision="no_trade",
            strategy_type="no_trade",
            risk_level="low",
            as_of=snapshot.as_of,
        )
        return build_option_trade_memory_record(
            target=snapshot.target,
            decision="no_trade",
            rationale=(
                f"Phase 5G {id_prefix} option no_trade rationale: liquidity "
                "and event risk filters block expression (fixture only)."
            ),
            plan_snapshot=plan_snapshot,
            review_status="reviewed",
            outcome="no_trade",
            run_id=snapshot.run_id,
            thesis_id=thesis_id,
            allocation_memory_id=allocation_memory_id,
            evidence_ids=[f"{id_prefix}_evid_option_no_trade"],
            recorded_at=snapshot.as_of,
        )

    plan_snapshot = build_option_trade_plan_snapshot(
        target=snapshot.target,
        decision="option",
        strategy_type="long_call",
        expiration="2026-09-18",
        entry_iv=0.32,
        entry_underlying_price=100.0,
        max_loss=300.0,
        max_gain=700.0,
        breakeven=103.0,
        cash_required=300.0,
        risk_reward_ratio=2.33,
        contracts=1,
        planned_exit_rule=(
            "Exit at 50% max profit OR if underlying breaks below "
            "short-horizon support."
        ),
        risk_level="medium",
        as_of=snapshot.as_of,
    )
    return build_option_trade_memory_record(
        target=snapshot.target,
        decision="option",
        rationale=(
            f"Phase 5G {id_prefix} option rationale: long call expresses "
            "bullish short-horizon thesis with bounded max loss (fixture only)."
        ),
        plan_snapshot=plan_snapshot,
        review_status="reviewed",
        outcome="pending",
        run_id=snapshot.run_id,
        thesis_id=thesis_id,
        allocation_memory_id=allocation_memory_id,
        evidence_ids=[f"{id_prefix}_evid_option"],
        recorded_at=snapshot.as_of,
    )


def _make_human_feedback_record(
    snapshot: ExistingWorkflowSnapshot,
    target_artifact_id: str,
    id_prefix: str,
) -> HumanFeedbackMemoryRecord:
    target_ref: HumanFeedbackTargetRef = build_human_feedback_target_ref(
        target_id=target_artifact_id,
        target_type="research_run_memory",
        run_id=snapshot.run_id,
        label="Phase 5G target ref (research run memory)",
        as_of=snapshot.as_of,
    )
    entry: HumanFeedbackEntry = build_human_feedback_entry(
        feedback_id=f"{id_prefix}_feedback_1",
        feedback_text=(
            f"Phase 5G {id_prefix} reviewer accepts the fixture thesis but "
            "flags watching next earnings cycle (fixture only)."
        ),
        decision="accepted",
        reason_type="preference",
        actor="reviewer",
        created_at=snapshot.as_of,
    )
    return build_human_feedback_memory_record(
        target=snapshot.target,
        target_ref=target_ref,
        feedback_entries=[entry],
        outcome="positive",
        run_id=snapshot.run_id,
        recorded_at=snapshot.as_of,
    )


def _make_agent_evaluation_record(
    snapshot: ExistingWorkflowSnapshot,
    human_feedback_memory_id: Optional[str],
    id_prefix: str,
) -> AgentEvaluationRecord:
    target_ref = build_agent_evaluation_target_ref(
        artifact_id=f"{id_prefix}_synth_artifact_{snapshot.target}",
        agent_type="horizon_synthesis",
        run_id=snapshot.run_id,
        horizon="medium",
        signal_type="thesis_direction",
        as_of=snapshot.as_of,
    )
    signal: AgentEvaluationSignal = build_agent_evaluation_signal(
        signal_id=f"{id_prefix}_signal_1",
        rationale=(
            f"Phase 5G {id_prefix} evaluation signal (fixture only): "
            "medium-horizon thesis direction partially correct."
        ),
        signal_type="thesis_direction",
        agent_type="horizon_synthesis",
        horizon="medium",
        original_claim="medium-horizon thesis bullish/neutral",
        original_direction="neutral",
        original_confidence=0.5,
        evaluated_outcome="partially_correct",
        evaluation_grade="mixed",
    )
    return build_agent_evaluation_record(
        target=snapshot.target,
        target_ref=target_ref,
        signals=[signal],
        agent_type="horizon_synthesis",
        run_id=snapshot.run_id,
        human_feedback_memory_id=human_feedback_memory_id,
        lesson=(
            f"Phase 5G {id_prefix} lesson: medium-horizon calls benefit "
            "from macro confluence."
        ),
        recorded_at=snapshot.as_of,
        as_of=snapshot.as_of,
    )


# ---------------------------------------------------------------------------
# Builders — fixtures + view bundles
# ---------------------------------------------------------------------------


def build_original_workflow_demo_fixture(
    snapshot: ExistingWorkflowSnapshot,
    memory_bundle: WorkflowMemoryBundle,
    adapter: InMemoryWorkflowToMemoryAdapter,
) -> OriginalWorkflowDemoFixture:
    """Wrap a snapshot + adapter + bundle into an ``OriginalWorkflowDemoFixture``.

    Computes present / missing step keys deterministically from the
    snapshot. Does not mutate any input.
    """
    present = snapshot.step_keys()
    missing = [s for s in WORKFLOW_STEP_ORDER if s not in snapshot.steps]
    return OriginalWorkflowDemoFixture(
        ticker=snapshot.target,
        run_id=snapshot.run_id,
        snapshot=snapshot,
        adapter=adapter,
        bundle=memory_bundle,
        present_step_keys=present,
        missing_step_keys=missing,
    )


def build_memory_demo_fixture_bundle(
    ticker: str,
    bundle: WorkflowMemoryBundle,
) -> MemoryDemoFixtureBundle:
    """
    Register a workflow memory bundle into a fresh ``FixtureBackedMemoryStore``
    and run a target-scoped query. Returns the full memory demo bundle.

    The fixture store is created fresh; Phase 5G never reuses a shared
    store across scenarios.
    """
    store = FixtureBackedMemoryStore()
    store.register_bundle(bundle)
    result = store.query(MemoryQueryByTicker(target=ticker))
    return MemoryDemoFixtureBundle(
        ticker=ticker,
        research_run_memory=bundle.research_run_memory,
        thesis_records=list(bundle.thesis_records),
        event_records=list(bundle.event_records),
        allocation_records=list(bundle.allocation_records),
        option_trade_records=list(bundle.option_trade_records),
        human_feedback_records=list(bundle.human_feedback_records),
        agent_evaluation_records=list(bundle.agent_evaluation_records),
        memory_store=store,
        memory_query_result=result,
    )


def build_cockpit_view_demo_bundle(
    ticker: str,
    snapshot: ExistingWorkflowSnapshot,
    memory_fixture: MemoryDemoFixtureBundle,
) -> CockpitViewDemoBundle:
    """Build the Phase 5B/5C/5D view bundle for one scenario."""
    company_view = build_company_research_hub_view(
        target=ticker,
        snapshot=snapshot,
        memory_store=memory_fixture.memory_store,
        memory_query_result=memory_fixture.memory_query_result,
    )
    horizon_cards = build_horizon_decision_cards_view(
        target=ticker,
        memory_store=memory_fixture.memory_store,
        memory_query_result=memory_fixture.memory_query_result,
    )
    tracker = build_thesis_tracker_view(
        targets=[ticker],
        memory_store=memory_fixture.memory_store,
        memory_query_result=memory_fixture.memory_query_result,
    )
    portfolio_view = build_portfolio_cockpit_view(
        target=ticker,
        memory_store=memory_fixture.memory_store,
        memory_query_result=memory_fixture.memory_query_result,
    )
    return CockpitViewDemoBundle(
        ticker=ticker,
        company_research_hub_view=company_view,
        horizon_decision_cards_view=horizon_cards,
        thesis_tracker_view=tracker,
        portfolio_cockpit_view=portfolio_view,
    )


# ---------------------------------------------------------------------------
# Scenario builders
# ---------------------------------------------------------------------------


def _build_complete_scenario() -> CockpitDemoScenario:
    snapshot = _make_complete_workflow_snapshot()
    id_prefix = "fix5g_complete"

    research_run = _make_research_run_memory(snapshot, id_prefix)

    short_thesis = _make_thesis_record(
        snapshot,
        horizon="short",
        direction="bullish",
        confidence="medium",
        text=(
            "Phase 5G short-horizon thesis (fixture only): expect modest "
            "upside on momentum."
        ),
        id_prefix=id_prefix,
    )
    medium_thesis = _make_thesis_record(
        snapshot,
        horizon="medium",
        direction="neutral",
        confidence="medium",
        text=(
            "Phase 5G medium-horizon thesis (fixture only): mean reversion "
            "plausible 1-2Q."
        ),
        id_prefix=id_prefix,
    )
    long_thesis = _make_thesis_record(
        snapshot,
        horizon="long",
        direction="bullish",
        confidence="high",
        text=(
            "Phase 5G long-horizon thesis (fixture only): structural growth "
            "maintained."
        ),
        id_prefix=id_prefix,
    )
    theses = [short_thesis, medium_thesis, long_thesis]

    event = _make_event_record(
        snapshot, thesis_id=medium_thesis.thesis_id, id_prefix=id_prefix
    )
    allocation = _make_allocation_record(
        snapshot, thesis_id=medium_thesis.thesis_id, id_prefix=id_prefix
    )
    option_trade = _make_option_trade_record(
        snapshot,
        thesis_id=short_thesis.thesis_id,
        allocation_memory_id=allocation.allocation_memory_id,
        id_prefix=id_prefix,
        no_trade=False,
    )
    human_feedback = _make_human_feedback_record(
        snapshot,
        target_artifact_id=research_run.memory_id,
        id_prefix=id_prefix,
    )
    agent_evaluation = _make_agent_evaluation_record(
        snapshot,
        human_feedback_memory_id=human_feedback.feedback_memory_id,
        id_prefix=id_prefix,
    )

    adapter = InMemoryWorkflowToMemoryAdapter()
    bundle = adapter.register_records(
        snapshot=snapshot,
        research_run_memory=research_run,
        thesis_records=theses,
        event_records=[event],
        allocation_records=[allocation],
        option_trade_records=[option_trade],
        human_feedback_records=[human_feedback],
        agent_evaluation_records=[agent_evaluation],
    )

    workflow_fixture = build_original_workflow_demo_fixture(
        snapshot=snapshot, memory_bundle=bundle, adapter=adapter
    )
    memory_fixture = build_memory_demo_fixture_bundle(
        ticker=snapshot.target, bundle=bundle
    )
    view_bundle = build_cockpit_view_demo_bundle(
        ticker=snapshot.target,
        snapshot=snapshot,
        memory_fixture=memory_fixture,
    )

    metadata = build_demo_scenario_metadata(
        scenario_kind="complete",
        ticker=snapshot.target,
        run_id=snapshot.run_id,
        title="Phase 5G Complete Scenario — FIXTKR",
        description=(
            "Complete original-workflow demo scenario covering all five "
            "research steps + synthesis + every Phase 4M memory record "
            "type. Demonstrates Phase 5B/5C/5D view-model population."
        ),
        as_of=snapshot.as_of,
    )

    return CockpitDemoScenario(
        metadata=metadata,
        workflow_fixture=workflow_fixture,
        memory_fixture=memory_fixture,
        view_bundle=view_bundle,
        warnings=[],
    )


def _build_degraded_scenario() -> CockpitDemoScenario:
    snapshot = _make_degraded_workflow_snapshot()
    id_prefix = "fix5g_degraded"

    research_run = _make_research_run_memory(snapshot, id_prefix)

    # Only short + medium thesis — long thesis intentionally omitted.
    short_thesis = _make_thesis_record(
        snapshot,
        horizon="short",
        direction="neutral",
        confidence="low",
        text=(
            "Phase 5G degraded short-horizon thesis (fixture only): "
            "limited conviction pending financial review."
        ),
        id_prefix=id_prefix,
    )
    medium_thesis = _make_thesis_record(
        snapshot,
        horizon="medium",
        direction="neutral",
        confidence="low",
        text=(
            "Phase 5G degraded medium-horizon thesis (fixture only): "
            "thesis depends on missing financial step."
        ),
        id_prefix=id_prefix,
    )
    theses = [short_thesis, medium_thesis]

    allocation = _make_allocation_record(
        snapshot, thesis_id=medium_thesis.thesis_id, id_prefix=id_prefix
    )
    # No-trade option overlay — preserves no_trade as first-class state.
    option_trade = _make_option_trade_record(
        snapshot,
        thesis_id=short_thesis.thesis_id,
        allocation_memory_id=allocation.allocation_memory_id,
        id_prefix=id_prefix,
        no_trade=True,
    )
    human_feedback = _make_human_feedback_record(
        snapshot,
        target_artifact_id=research_run.memory_id,
        id_prefix=id_prefix,
    )

    adapter = InMemoryWorkflowToMemoryAdapter()
    bundle = adapter.register_records(
        snapshot=snapshot,
        research_run_memory=research_run,
        thesis_records=theses,
        event_records=[],
        allocation_records=[allocation],
        option_trade_records=[option_trade],
        human_feedback_records=[human_feedback],
        agent_evaluation_records=[],
    )

    workflow_fixture = build_original_workflow_demo_fixture(
        snapshot=snapshot, memory_bundle=bundle, adapter=adapter
    )
    memory_fixture = build_memory_demo_fixture_bundle(
        ticker=snapshot.target, bundle=bundle
    )
    view_bundle = build_cockpit_view_demo_bundle(
        ticker=snapshot.target,
        snapshot=snapshot,
        memory_fixture=memory_fixture,
    )

    metadata = build_demo_scenario_metadata(
        scenario_kind="degraded",
        ticker=snapshot.target,
        run_id=snapshot.run_id,
        title="Phase 5G Degraded Scenario — FIXDEG",
        description=(
            "Degraded scenario: missing financial workflow step, missing "
            "long-horizon thesis, and no_trade option overlay. "
            "Demonstrates Phase 5B safe degraded panel, Phase 5C safe "
            "missing-card behavior, and Phase 5D first-class no_trade "
            "state."
        ),
        as_of=snapshot.as_of,
    )

    warnings = [
        "Degraded scenario: financial step is intentionally missing.",
        "Degraded scenario: long-horizon thesis is intentionally absent.",
        "Degraded scenario: option overlay reports no_trade.",
    ]

    return CockpitDemoScenario(
        metadata=metadata,
        workflow_fixture=workflow_fixture,
        memory_fixture=memory_fixture,
        view_bundle=view_bundle,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


# Names that must not appear as field names on any Phase 5G demo-pack model.
_FORBIDDEN_EXECUTABLE_ORDER_FIELDS: tuple[str, ...] = (
    "order_type",
    "time_in_force",
    "broker_route",
    "broker_id",
    "account_id",
    "quantity_to_execute",
    "broker_payload",
    "order_ticket",
    "execution_id",
    "fill_price",
)


def _scenario_record_lists(scenario: CockpitDemoScenario) -> list[object]:
    out: list[object] = []
    if scenario.memory_fixture.research_run_memory is not None:
        out.append(scenario.memory_fixture.research_run_memory)
    out.extend(scenario.memory_fixture.thesis_records)
    out.extend(scenario.memory_fixture.event_records)
    out.extend(scenario.memory_fixture.allocation_records)
    out.extend(scenario.memory_fixture.option_trade_records)
    out.extend(scenario.memory_fixture.human_feedback_records)
    out.extend(scenario.memory_fixture.agent_evaluation_records)
    return out


def validate_cockpit_demo_pack(pack: CockpitDemoPack) -> DemoPackValidationSummary:
    """
    Validate a built ``CockpitDemoPack`` and return a deterministic summary.

    Checks:
      - At least one scenario is present.
      - ``approved_for_execution`` is ``False`` everywhere it appears on
        an underlying record or view-model.
      - No executable order field names appear on any demo-pack model.
      - Safety banner + provenance are populated.
      - Reports which scenario kinds are present (complete / degraded).
    """
    errors: list[str] = []
    warnings: list[str] = []
    kinds: list[DemoScenarioKind] = []
    has_complete = False
    has_degraded = False

    all_aft_false = True
    no_order_fields = True

    if not pack.scenarios:
        errors.append("Pack has no scenarios.")

    for scenario in pack.scenarios:
        kinds.append(scenario.metadata.scenario_kind)
        if scenario.metadata.scenario_kind == "complete":
            has_complete = True
        elif scenario.metadata.scenario_kind == "degraded":
            has_degraded = True

        # approved_for_execution invariants on underlying records.
        for record in _scenario_record_lists(scenario):
            aft = getattr(record, "approved_for_execution", False)
            if aft:
                all_aft_false = False
                errors.append(
                    f"Record on scenario {scenario.metadata.scenario_id!r} "
                    "has approved_for_execution=True."
                )

        # Snapshot + bundle invariants.
        if scenario.workflow_fixture.snapshot.approved_for_execution:
            all_aft_false = False
            errors.append(
                f"Snapshot on scenario {scenario.metadata.scenario_id!r} "
                "has approved_for_execution=True."
            )
        if scenario.workflow_fixture.bundle.approved_for_execution:
            all_aft_false = False
            errors.append(
                f"Bundle on scenario {scenario.metadata.scenario_id!r} "
                "has approved_for_execution=True."
            )
        if scenario.memory_fixture.memory_query_result.approved_for_execution:
            all_aft_false = False
            errors.append(
                f"Memory query result on scenario "
                f"{scenario.metadata.scenario_id!r} has approved_for_execution=True."
            )

        # Safety banner / provenance presence on the scenario.
        if not scenario.metadata.safety_banner.is_demo_only:
            errors.append(
                f"Scenario {scenario.metadata.scenario_id!r} safety banner "
                "missing is_demo_only=True."
            )
        if not scenario.metadata.provenance.is_fixture_only:
            errors.append(
                f"Scenario {scenario.metadata.scenario_id!r} provenance "
                "missing is_fixture_only=True."
            )

    # No executable order field names on any Phase 5G model.
    phase5g_models: list[type[BaseModel]] = [
        DemoSafetyBanner,
        DemoDataProvenance,
        DemoScenarioMetadata,
        OriginalWorkflowDemoFixture,
        MemoryDemoFixtureBundle,
        CockpitViewDemoBundle,
        CockpitDemoScenario,
        DemoPackValidationSummary,
        CockpitDemoPack,
    ]
    for cls in phase5g_models:
        for fname in cls.model_fields:
            if fname in _FORBIDDEN_EXECUTABLE_ORDER_FIELDS:
                no_order_fields = False
                errors.append(
                    f"Phase 5G model {cls.__name__} declares forbidden "
                    f"executable order field {fname!r}."
                )

    # Pack-level safety banner / provenance.
    banner_ok = pack.safety_banner.is_demo_only and not pack.safety_banner.approved_for_execution
    provenance_ok = pack.provenance.is_fixture_only and not pack.provenance.uses_live_data

    if not banner_ok:
        errors.append("Pack-level safety banner is missing demo-only invariants.")
    if not provenance_ok:
        errors.append("Pack-level provenance is missing fixture-only invariants.")

    return DemoPackValidationSummary(
        scenario_count=len(pack.scenarios),
        scenario_kinds=kinds,
        has_complete_scenario=has_complete,
        has_degraded_scenario=has_degraded,
        all_approved_for_execution_false=all_aft_false,
        no_executable_order_fields=no_order_fields,
        safety_banner_present=banner_ok,
        provenance_present=provenance_ok,
        warnings=warnings,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------


def build_default_cockpit_demo_pack() -> CockpitDemoPack:
    """
    Build the default Phase 5G ``CockpitDemoPack``.

    Includes both the complete scenario (``FIXTKR``) and the degraded
    scenario (``FIXDEG``). Returns a fully-validated ``CockpitDemoPack``
    with ``validation_summary`` populated.

    The pack is deterministic: identical inputs always produce identical
    IDs and identical serialized contents.
    """
    scenarios = [_build_complete_scenario(), _build_degraded_scenario()]
    fixture_tickers = [s.metadata.ticker for s in scenarios]
    pack = CockpitDemoPack(
        pack_id="phase5g_default_cockpit_demo_pack",
        title="Phase 5G — Default Cockpit Demo Pack",
        description=(
            "Deterministic fixture/demo pack representing the original "
            "five-step README app flow end-to-end and feeding Phase 5A–5D "
            "contracts. Includes one complete scenario and one degraded "
            "scenario. Phase 5G is fixture-only and does not create UI."
        ),
        scenarios=scenarios,
        safety_banner=build_demo_safety_banner(),
        provenance=build_demo_data_provenance(
            fixture_tickers=fixture_tickers, as_of=SAMPLE_DEMO_AS_OF
        ),
        warnings=[],
    )
    pack = pack.model_copy(
        update={"validation_summary": validate_cockpit_demo_pack(pack)}
    )
    return pack


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Literal aliases / constants
    "DemoScenarioKind",
    "DEMO_SCENARIO_ORDER",
    "SAMPLE_DEMO_COMPLETE_TICKER",
    "SAMPLE_DEMO_DEGRADED_TICKER",
    "SAMPLE_DEMO_COMPLETE_RUN_ID",
    "SAMPLE_DEMO_DEGRADED_RUN_ID",
    "SAMPLE_DEMO_AS_OF",
    # Models
    "DemoSafetyBanner",
    "DemoDataProvenance",
    "DemoScenarioMetadata",
    "OriginalWorkflowDemoFixture",
    "MemoryDemoFixtureBundle",
    "CockpitViewDemoBundle",
    "CockpitDemoScenario",
    "DemoPackValidationSummary",
    "CockpitDemoPack",
    # Builders
    "build_demo_safety_banner",
    "build_demo_data_provenance",
    "build_demo_scenario_metadata",
    "build_original_workflow_demo_fixture",
    "build_memory_demo_fixture_bundle",
    "build_cockpit_view_demo_bundle",
    "validate_cockpit_demo_pack",
    "build_default_cockpit_demo_pack",
]
