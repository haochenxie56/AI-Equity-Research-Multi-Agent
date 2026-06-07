"""
lib/reliability/phase5_fixtures.py

Phase 5A: Deterministic fixture builders for the existing-workflow memory
adapter and the fixture-backed memory query store.

These fixtures simulate the *outputs* of one complete original-app-style
research run through the README five-step workflow (sector -> scanner ->
equity -> financial -> price_volume -> synthesis). They are entirely
fictional and use sample tickers / labels clearly intended for fixture use.

Design principles
-----------------
- Standalone, deterministic, offline / mock-only.
- No live data, no live LLM, no Streamlit, no external API.
- No file persistence, no DB, no vector store.
- ``approved_for_execution`` is always ``False`` on every record produced.
- No broker / order / execution paths.
- Fixtures do not import ``app.py``, ``pages/*``, ``lib/llm_orchestrator.py``,
  or ``lib/workflow_state.py``.
"""

from __future__ import annotations

from typing import Optional

from lib.reliability.adapters import stable_hash_payload
from lib.reliability.research_memory import (
    MemorySourceRef,
    ResearchRunMemoryInputBundle,
    ResearchRunMemoryRecord,
    build_research_run_memory_record,
)
from lib.reliability.thesis_memory import (
    ThesisAssumption,
    ThesisInvalidationCondition,
    HorizonThesisMemoryRecord,
    build_horizon_thesis_memory_record,
)
from lib.reliability.event_memory import (
    EventMemoryRecord,
    EventMemorySourceRef,
    build_event_memory_record,
)
from lib.reliability.allocation_memory import (
    AllocationDecisionMemoryRecord,
    AllocationDecisionSnapshot,
    AllocationMemorySourceRef,
    build_allocation_decision_snapshot,
    build_allocation_memory_record,
)
from lib.reliability.option_trade_memory import (
    OptionTradePlanMemoryRecord,
    OptionTradePlanSnapshot,
    build_option_trade_plan_snapshot,
    build_option_trade_memory_record,
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
    WorkflowMemoryBundle,
)


# ---------------------------------------------------------------------------
# Deterministic fixture constants — fictional / clearly fixture-only
# ---------------------------------------------------------------------------

# Use a clearly fictional ticker that is not an actual NYSE/NASDAQ symbol.
SAMPLE_FIXTURE_TICKER: str = "FIXTKR"
SAMPLE_FIXTURE_RUN_ID: str = "FIXTKR_20260524_120000_fix5a"
SAMPLE_FIXTURE_AS_OF: str = "2026-05-24T12:00:00+00:00"


def make_sample_workflow_snapshot(
    ticker: str = SAMPLE_FIXTURE_TICKER,
    run_id: str = SAMPLE_FIXTURE_RUN_ID,
    as_of: str = SAMPLE_FIXTURE_AS_OF,
) -> ExistingWorkflowSnapshot:
    """
    Build a fixture ``ExistingWorkflowSnapshot`` representing one complete
    original-app-style workflow journey.

    Includes sector / scanner / equity / financial / price_volume / synthesis
    sub-snapshots, each carrying a deterministic ``ExistingPageOutputRef``.
    """
    return ExistingWorkflowSnapshot(
        run_id=run_id,
        target=ticker,
        as_of=as_of,
        workflow_name="five_step_research_workflow",
        steps={
            "sector": ExistingWorkflowStepSnapshot(
                step="sector",
                status="complete",
                summary="Sector analysis output ref (fixture only).",
                page_outputs=[
                    ExistingPageOutputRef(
                        page="Sector",
                        step="sector",
                        artifact_id="fix5a_sector_artifact",
                        report_path="research/sector/fix5a_sector.md",
                        description="Mock sector analysis page output.",
                    )
                ],
            ),
            "scanner": ExistingWorkflowStepSnapshot(
                step="scanner",
                status="complete",
                summary="Scanner analysis output ref (fixture only).",
                page_outputs=[
                    ExistingPageOutputRef(
                        page="Scanner",
                        step="scanner",
                        artifact_id="fix5a_scanner_artifact",
                        report_path="research/scans/fix5a_scan.md",
                        description="Mock scanner page output.",
                    )
                ],
            ),
            "equity": ExistingWorkflowStepSnapshot(
                step="equity",
                status="complete",
                summary="Equity research output ref (fixture only).",
                page_outputs=[
                    ExistingPageOutputRef(
                        page="Equity",
                        step="equity",
                        artifact_id="fix5a_equity_artifact",
                        report_path="research/stock/fix5a_equity.md",
                        description="Mock equity page output.",
                    )
                ],
            ),
            "financial": ExistingWorkflowStepSnapshot(
                step="financial",
                status="complete",
                summary="Financial analysis output ref (fixture only).",
                page_outputs=[
                    ExistingPageOutputRef(
                        page="Financial",
                        step="financial",
                        artifact_id="fix5a_financial_artifact",
                        report_path="research/stock/fix5a_financial.md",
                        description="Mock financial page output.",
                    )
                ],
            ),
            "price_volume": ExistingWorkflowStepSnapshot(
                step="price_volume",
                status="complete",
                summary="Price/Volume analysis output ref (fixture only).",
                page_outputs=[
                    ExistingPageOutputRef(
                        page="PriceVolume",
                        step="price_volume",
                        artifact_id="fix5a_pricevolume_artifact",
                        report_path="research/stock/fix5a_pricevolume.md",
                        description="Mock price/volume page output.",
                    )
                ],
            ),
            "synthesis": ExistingWorkflowStepSnapshot(
                step="synthesis",
                status="complete",
                summary="Synthesis output ref (fixture only).",
                page_outputs=[
                    ExistingPageOutputRef(
                        page="Overview",
                        step="synthesis",
                        artifact_id="fix5a_synthesis_artifact",
                        report_path="research/stock/fix5a_synthesis.md",
                        description="Mock synthesis page output.",
                    )
                ],
            ),
        },
        synthesis=ExistingWorkflowSynthesisSnapshot(
            status="complete",
            summary="Mock five-step synthesis (fixture only).",
            consolidated_report_ref=ExistingPageOutputRef(
                page="Overview",
                step="synthesis",
                artifact_id="fix5a_synthesis_artifact",
                report_path="research/stock/fix5a_synthesis.md",
                description="Mock consolidated synthesis output.",
            ),
            artifact_refs=["fix5a_synthesis_artifact"],
        ),
        notes="Phase 5A fixture only — does not represent any real research run.",
    )


# ---------------------------------------------------------------------------
# Memory record builders for the fixture journey
# ---------------------------------------------------------------------------


def make_sample_research_run_memory(
    snapshot: ExistingWorkflowSnapshot,
) -> ResearchRunMemoryRecord:
    """Build a deterministic ResearchRunMemoryRecord for the fixture snapshot."""
    bundle = ResearchRunMemoryInputBundle(
        run_id=snapshot.run_id,
        target=snapshot.target,
        as_of=snapshot.as_of,
        workflow_name="five_step_research_workflow",
        source_refs=[
            MemorySourceRef(
                source_id=f"fix5a_step_{step}",
                source_type="orchestration",
                run_id=snapshot.run_id,
                target=snapshot.target,
                label=f"Fixture {step} step source ref",
            )
            for step in snapshot.step_keys()
        ],
        evidence_ids=[f"fix5a_evid_{step}" for step in snapshot.step_keys()],
        artifact_refs=[
            f"fix5a_artifact_{step}" for step in snapshot.step_keys()
        ],
    )
    return build_research_run_memory_record(
        bundle,
        created_at=snapshot.as_of,
        updated_at=snapshot.as_of,
    )


def make_sample_thesis_records(
    snapshot: ExistingWorkflowSnapshot,
) -> list[HorizonThesisMemoryRecord]:
    """
    Build short / medium / long horizon thesis records for the fixture.

    Each thesis references one fixture assumption and one fixture invalidation
    condition.
    """
    short = build_horizon_thesis_memory_record(
        target=snapshot.target,
        thesis_text="Short-horizon thesis (fixture only): expect modest upside on momentum.",
        horizon="short",
        direction="bullish",
        confidence="medium",
        assumptions=[
            ThesisAssumption(
                assumption_id="fix5a_assump_short_1",
                description="Short-term momentum continues over next 4 weeks.",
                horizon="short",
                importance="medium",
            )
        ],
        invalidation_conditions=[
            ThesisInvalidationCondition(
                condition_id="fix5a_invalid_short_1",
                invalidation_type="technical",
                description="Close below short-horizon support invalidates thesis.",
                horizon="short",
            )
        ],
        run_id=snapshot.run_id,
        source_ids=["fix5a_step_horizon_synth"],
        evidence_ids=["fix5a_evid_short"],
        created_at=snapshot.as_of,
        updated_at=snapshot.as_of,
    )
    medium = build_horizon_thesis_memory_record(
        target=snapshot.target,
        thesis_text="Medium-horizon thesis (fixture only): mean reversion plausible 1-2Q.",
        horizon="medium",
        direction="neutral",
        confidence="medium",
        assumptions=[
            ThesisAssumption(
                assumption_id="fix5a_assump_med_1",
                description="No major earnings surprise expected.",
                horizon="medium",
                importance="high",
            )
        ],
        invalidation_conditions=[
            ThesisInvalidationCondition(
                condition_id="fix5a_invalid_med_1",
                invalidation_type="earnings",
                description="Negative earnings surprise > 10% invalidates thesis.",
                horizon="medium",
            )
        ],
        run_id=snapshot.run_id,
        source_ids=["fix5a_step_horizon_synth"],
        evidence_ids=["fix5a_evid_medium"],
        created_at=snapshot.as_of,
        updated_at=snapshot.as_of,
    )
    long_ = build_horizon_thesis_memory_record(
        target=snapshot.target,
        thesis_text="Long-horizon thesis (fixture only): structural growth maintained.",
        horizon="long",
        direction="bullish",
        confidence="high",
        assumptions=[
            ThesisAssumption(
                assumption_id="fix5a_assump_long_1",
                description="Secular growth in target's end markets continues.",
                horizon="long",
                importance="high",
            )
        ],
        invalidation_conditions=[
            ThesisInvalidationCondition(
                condition_id="fix5a_invalid_long_1",
                invalidation_type="fundamental",
                description="Sustained margin compression for two consecutive years.",
                horizon="long",
            )
        ],
        run_id=snapshot.run_id,
        source_ids=["fix5a_step_horizon_synth"],
        evidence_ids=["fix5a_evid_long"],
        created_at=snapshot.as_of,
        updated_at=snapshot.as_of,
    )
    return [short, medium, long_]


def make_sample_event_record(
    snapshot: ExistingWorkflowSnapshot,
    thesis_id: Optional[str] = None,
) -> EventMemoryRecord:
    """Build a fixture catalyst/news/earnings memory record."""
    return build_event_memory_record(
        target=snapshot.target,
        event_name="Mock Q1 2026 earnings (fixture only)",
        summary="Fixture earnings event for Phase 5A snapshot.",
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
                source_id="fix5a_event_src_1",
                source_type="event_intelligence",
                label="Fixture event intelligence source ref",
            )
        ],
        evidence_ids=["fix5a_evid_event"],
        recorded_at=snapshot.as_of,
    )


def make_sample_allocation_record(
    snapshot: ExistingWorkflowSnapshot,
    thesis_id: Optional[str] = None,
) -> AllocationDecisionMemoryRecord:
    """Build a fixture allocation decision memory record."""
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
            "Fixture allocation rationale: add to target allocation following "
            "constructive thesis confluence (fixture only)."
        ),
        decision_snapshot=decision_snapshot,
        review_status="reviewed",
        outcome="pending",
        run_id=snapshot.run_id,
        thesis_id=thesis_id,
        source_refs=[
            AllocationMemorySourceRef(
                source_id="fix5a_alloc_src_1",
                source_type="allocation_report",
                label="Fixture allocation source ref",
            )
        ],
        evidence_ids=["fix5a_evid_alloc"],
        recorded_at=snapshot.as_of,
    )


def make_sample_option_trade_record(
    snapshot: ExistingWorkflowSnapshot,
    thesis_id: Optional[str] = None,
    allocation_memory_id: Optional[str] = None,
) -> OptionTradePlanMemoryRecord:
    """
    Build a fixture option trade plan memory record with
    ``approved_for_execution=False`` (Phase 5A guarantees this everywhere).

    The trade plan is structured as a long call option expression with a
    bounded max-loss snapshot to demonstrate the boundary contract; it is
    research-only and not executable.
    """
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
        planned_exit_rule="Exit at 50% max profit OR if underlying breaks below short-horizon support.",
        risk_level="medium",
        as_of=snapshot.as_of,
    )
    return build_option_trade_memory_record(
        target=snapshot.target,
        decision="option",
        rationale=(
            "Fixture option expression rationale: long call expresses "
            "bullish short-horizon thesis with bounded max loss (fixture only)."
        ),
        plan_snapshot=plan_snapshot,
        review_status="reviewed",
        outcome="pending",
        run_id=snapshot.run_id,
        thesis_id=thesis_id,
        allocation_memory_id=allocation_memory_id,
        evidence_ids=["fix5a_evid_option"],
        recorded_at=snapshot.as_of,
    )


def make_sample_human_feedback_record(
    snapshot: ExistingWorkflowSnapshot,
    target_artifact_id: str,
) -> HumanFeedbackMemoryRecord:
    """Build a fixture human feedback memory record."""
    target_ref: HumanFeedbackTargetRef = build_human_feedback_target_ref(
        target_id=target_artifact_id,
        target_type="research_run_memory",
        run_id=snapshot.run_id,
        label="Fixture target ref (research run memory)",
        as_of=snapshot.as_of,
    )
    entry: HumanFeedbackEntry = build_human_feedback_entry(
        feedback_id="fix5a_feedback_1",
        feedback_text=(
            "Reviewer accepts the fixture thesis but flags watching the "
            "next earnings cycle for margin direction (fixture only)."
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


def make_sample_agent_evaluation_record(
    snapshot: ExistingWorkflowSnapshot,
    human_feedback_memory_id: Optional[str] = None,
) -> AgentEvaluationRecord:
    """Build a fixture agent evaluation memory record."""
    target_ref = build_agent_evaluation_target_ref(
        artifact_id=f"fix5a_synth_artifact_{snapshot.target}",
        agent_type="horizon_synthesis",
        run_id=snapshot.run_id,
        horizon="medium",
        signal_type="thesis_direction",
        as_of=snapshot.as_of,
    )
    signal: AgentEvaluationSignal = build_agent_evaluation_signal(
        signal_id="fix5a_signal_1",
        rationale="Fixture evaluation signal: medium-horizon thesis direction correct.",
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
        lesson="Fixture lesson: medium-horizon calls benefit from confluence with macro signal.",
        recorded_at=snapshot.as_of,
        as_of=snapshot.as_of,
    )


# ---------------------------------------------------------------------------
# Whole-journey fixture pack
# ---------------------------------------------------------------------------


def build_sample_workflow_memory_bundle(
    snapshot: Optional[ExistingWorkflowSnapshot] = None,
) -> WorkflowMemoryBundle:
    """
    Build a complete fixture ``WorkflowMemoryBundle`` containing one record of
    each Phase 4M memory type, all keyed to a single deterministic snapshot.

    Returns
    -------
    WorkflowMemoryBundle
        A bundle with research-run memory, three thesis records (short /
        medium / long), one event memory record, one allocation decision
        memory record, one option trade plan memory record (with
        ``approved_for_execution=False``), one human feedback record, and
        one agent evaluation record.

    The bundle is produced through the ``InMemoryWorkflowToMemoryAdapter`` so
    that callers exercise the adapter contract.
    """
    snap = snapshot or make_sample_workflow_snapshot()
    research_run = make_sample_research_run_memory(snap)
    theses = make_sample_thesis_records(snap)
    short_id = theses[0].thesis_id
    medium_id = theses[1].thesis_id
    event = make_sample_event_record(snap, thesis_id=medium_id)
    allocation = make_sample_allocation_record(snap, thesis_id=medium_id)
    option_trade = make_sample_option_trade_record(
        snap,
        thesis_id=short_id,
        allocation_memory_id=allocation.allocation_memory_id,
    )
    human_feedback = make_sample_human_feedback_record(
        snap,
        target_artifact_id=research_run.memory_id,
    )
    agent_evaluation = make_sample_agent_evaluation_record(
        snap,
        human_feedback_memory_id=human_feedback.feedback_memory_id,
    )

    adapter = InMemoryWorkflowToMemoryAdapter()
    bundle = adapter.register_records(
        snapshot=snap,
        research_run_memory=research_run,
        thesis_records=theses,
        event_records=[event],
        allocation_records=[allocation],
        option_trade_records=[option_trade],
        human_feedback_records=[human_feedback],
        agent_evaluation_records=[agent_evaluation],
    )
    return bundle


def build_sample_fixture_pack() -> tuple[
    ExistingWorkflowSnapshot,
    InMemoryWorkflowToMemoryAdapter,
    WorkflowMemoryBundle,
]:
    """
    Build a deterministic 3-tuple ``(snapshot, adapter, bundle)`` representing
    one complete original-app-style fixture journey.

    The caller can register the bundle into a ``FixtureBackedMemoryStore``.
    """
    snap = make_sample_workflow_snapshot()
    research_run = make_sample_research_run_memory(snap)
    theses = make_sample_thesis_records(snap)
    short_id = theses[0].thesis_id
    medium_id = theses[1].thesis_id
    event = make_sample_event_record(snap, thesis_id=medium_id)
    allocation = make_sample_allocation_record(snap, thesis_id=medium_id)
    option_trade = make_sample_option_trade_record(
        snap,
        thesis_id=short_id,
        allocation_memory_id=allocation.allocation_memory_id,
    )
    human_feedback = make_sample_human_feedback_record(
        snap,
        target_artifact_id=research_run.memory_id,
    )
    agent_evaluation = make_sample_agent_evaluation_record(
        snap,
        human_feedback_memory_id=human_feedback.feedback_memory_id,
    )

    adapter = InMemoryWorkflowToMemoryAdapter()
    bundle = adapter.register_records(
        snapshot=snap,
        research_run_memory=research_run,
        thesis_records=theses,
        event_records=[event],
        allocation_records=[allocation],
        option_trade_records=[option_trade],
        human_feedback_records=[human_feedback],
        agent_evaluation_records=[agent_evaluation],
    )
    return snap, adapter, bundle


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "SAMPLE_FIXTURE_TICKER",
    "SAMPLE_FIXTURE_RUN_ID",
    "SAMPLE_FIXTURE_AS_OF",
    "make_sample_workflow_snapshot",
    "make_sample_research_run_memory",
    "make_sample_thesis_records",
    "make_sample_event_record",
    "make_sample_allocation_record",
    "make_sample_option_trade_record",
    "make_sample_human_feedback_record",
    "make_sample_agent_evaluation_record",
    "build_sample_workflow_memory_bundle",
    "build_sample_fixture_pack",
]
