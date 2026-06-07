#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5d_portfolio_trade_option_views.py

Phase 5D: Portfolio / TradePlan / Option Overlay ViewModel Contract test suite.

Validates:
  - lib/reliability/phase5_portfolio_views.py imports without loading any
    forbidden live runtime module (Streamlit, workflow_state,
    llm_orchestrator, data_fetcher, Anthropic SDK, etc.).
  - Source-level forbidden import / live-state-path substrings are absent.
  - build_portfolio_cockpit_view() builds a populated view from the
    Phase 5A complete fixture pack.
  - AllocationSummaryView, PositionAllocationView, TradePlanView, and
    OptionOverlayView are populated faithfully from Phase 4M-D and
    Phase 4M-E records.
  - RiskBudgetView and CashImpactView populate only when the underlying
    allocation records carry the corresponding fields.
  - ``no_trade`` option state is preserved as first-class and does not
    infer a substitute strategy.
  - Missing allocation records produce safe degraded view + warnings.
  - Missing option records produce safe degraded view + warnings.
  - Missing ticker / no records returns a safe empty view.
  - ExecutionSafetyBannerView is always present.
  - No ``approved_for_execution`` field on any Phase 5D class.
  - No ``approved_for_execution=true`` literal in serialized JSON.
  - No executable order fields are introduced (no order_type,
    time_in_force, broker_route, account_id, quantity_to_execute, etc.).
  - Builder rejects empty / whitespace target.
  - Deterministic serialization across rebuilds.
  - Build with explicit MemoryQueryResult equals store-driven build.
  - Phase 5C regression: HorizonDecisionCardsView still builds.
  - Phase 5B regression: CompanyResearchHubView still builds.
  - Phase 5A regression: MemoryQueryResult contract preserved.
  - Package-level re-exports through lib/reliability/__init__.py.
  - __all__ symmetry between module and re-exports.
  - No filesystem writes during the pipeline.

Usage:
    python3 scripts/test_reliability_phase_5d_portfolio_trade_option_views.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

PASS = 0
FAIL = 0
_failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        d = f"  [{detail}]" if detail else ""
        _failures.append(f"FAIL  {label}{d}")


def expect_error(label: str, fn, exc_type=Exception, keyword: str | None = None) -> None:
    global PASS, FAIL
    try:
        fn()
        FAIL += 1
        _failures.append(
            f"FAIL  {label}: expected {exc_type.__name__} but no error raised"
        )
        return
    except exc_type as e:
        if keyword and keyword.lower() not in str(e).lower():
            FAIL += 1
            _failures.append(
                f"FAIL  {label}: raised {exc_type.__name__} but missing keyword "
                f"{keyword!r}: {e}"
            )
            return
        PASS += 1
    except Exception as e:
        FAIL += 1
        _failures.append(
            f"FAIL  {label}: expected {exc_type.__name__} but got "
            f"{type(e).__name__}: {e}"
        )


# ---------------------------------------------------------------------------
# Section 1 — Module imports must succeed and forbidden imports must not occur
# ---------------------------------------------------------------------------

from lib.reliability import phase5_portfolio_views as _pv_mod

check("1.1 phase5_portfolio_views importable", _pv_mod is not None)

_FORBIDDEN_LIVE_MODULES = (
    "lib.workflow_state",
    "lib.llm_orchestrator",
    "lib.data_fetcher",
    "lib.valuation",
    "lib.technical",
    "lib.rotation",
    "lib.cache_manager",
    "app",
    "streamlit",
    "anthropic",
)

for _m in _FORBIDDEN_LIVE_MODULES:
    loaded = any(name == _m or name.startswith(_m + ".") for name in sys.modules)
    check(f"1.x forbidden module not loaded: {_m}", not loaded)


# ---------------------------------------------------------------------------
# Section 2 — Source-level forbidden imports / live-state path check
# ---------------------------------------------------------------------------

_PHASE5D_SOURCES = [
    pathlib.Path(_REPO_ROOT) / "lib" / "reliability" / "phase5_portfolio_views.py",
]

_FORBIDDEN_SUBSTRINGS = [
    "import lib.workflow_state",
    "from lib.workflow_state",
    "import lib.llm_orchestrator",
    "from lib.llm_orchestrator",
    "import lib.data_fetcher",
    "from lib.data_fetcher",
    "import lib.valuation",
    "from lib.valuation",
    "import lib.technical",
    "from lib.technical",
    "import lib.rotation",
    "from lib.rotation",
    "import lib.cache_manager",
    "from lib.cache_manager",
    "import streamlit",
    "from streamlit",
    "import anthropic",
    "from anthropic",
    "import app",
    "from app",
    "from lib.reliability.integration_boundary",
    "import lib.reliability.integration_boundary",
    "research/.workflow_state.json",
]

for src in _PHASE5D_SOURCES:
    text = src.read_text(encoding="utf-8")
    for sub in _FORBIDDEN_SUBSTRINGS:
        check(
            f"2.{src.name}::{sub!r}",
            sub not in text,
            f"forbidden substring {sub!r} found in {src.name}",
        )


# Also ensure no obvious executable-order field name leaks into the module.
_FORBIDDEN_ORDER_FIELDS = (
    "order_type",
    "time_in_force",
    "broker_route",
    "account_id",
    "quantity_to_execute",
    "broker_payload",
    "order_ticket",
    "submit_order",
    "place_order",
    "execute_trade",
)
for src in _PHASE5D_SOURCES:
    text_lower = src.read_text(encoding="utf-8").lower()
    for forbidden in _FORBIDDEN_ORDER_FIELDS:
        check(
            f"2.order::{src.name}::{forbidden!r}",
            forbidden not in text_lower,
            f"forbidden executable-order substring {forbidden!r} found",
        )


# ---------------------------------------------------------------------------
# Section 3 — Public symbol imports
# ---------------------------------------------------------------------------

from lib.reliability.phase5_portfolio_views import (
    AllocationSummaryView,
    CashImpactView,
    ExecutionSafetyBannerView,
    MissingPortfolioDataWarningView,
    MissingPortfolioPanel,
    NoTradeReasonView,
    OptionEventRiskWarningView,
    OptionLiquidityWarningView,
    OptionOverlayState,
    OptionOverlayView,
    OptionRiskRewardView,
    OptionStrategySummaryView,
    PortfolioCockpitView,
    PortfolioDataSource,
    PositionAllocationView,
    RiskBudgetView,
    TRADE_PLAN_LEVEL_KINDS,
    TradePlanLevelKind,
    TradePlanLevelView,
    TradePlanReviewTriggerView,
    TradePlanView,
    build_allocation_summary_view,
    build_execution_safety_banner,
    build_no_trade_reason_view,
    build_option_overlay_view,
    build_portfolio_cockpit_view,
    build_position_allocation_view,
    build_trade_plan_view,
)
from lib.reliability.phase5_fixtures import (
    SAMPLE_FIXTURE_AS_OF,
    SAMPLE_FIXTURE_RUN_ID,
    SAMPLE_FIXTURE_TICKER,
    build_sample_fixture_pack,
    make_sample_allocation_record,
    make_sample_option_trade_record,
    make_sample_workflow_snapshot,
)
from lib.reliability.phase5_memory_query import (
    FixtureBackedMemoryStore,
    MemoryQueryByTicker,
    MemoryQueryResult,
)
from lib.reliability.allocation_memory import (
    AllocationDecisionMemoryRecord,
    build_allocation_decision_snapshot,
    build_allocation_memory_record,
)
from lib.reliability.option_trade_memory import (
    OptionTradePlanMemoryRecord,
    build_option_trade_memory_record,
    build_option_trade_plan_snapshot,
)
from lib.reliability.human_feedback_memory import (
    build_human_feedback_entry,
    build_human_feedback_memory_record,
    build_human_feedback_target_ref,
)

check("3.1 PortfolioCockpitView importable", PortfolioCockpitView is not None)
check("3.2 OptionOverlayView importable", OptionOverlayView is not None)
check("3.3 TradePlanView importable", TradePlanView is not None)
check(
    "3.4 TRADE_PLAN_LEVEL_KINDS includes entry/add/trim/stop/target/review",
    set(TRADE_PLAN_LEVEL_KINDS) == {"entry", "add", "trim", "stop", "target", "review"},
)


# ---------------------------------------------------------------------------
# Section 4 — Full PortfolioCockpitView build from Phase 5A complete fixture
# ---------------------------------------------------------------------------

snap, adapter, bundle = build_sample_fixture_pack()
store = FixtureBackedMemoryStore()
store.register_bundle(bundle)

cockpit = build_portfolio_cockpit_view(
    target=SAMPLE_FIXTURE_TICKER, memory_store=store
)

check(
    "4.1 cockpit is PortfolioCockpitView",
    isinstance(cockpit, PortfolioCockpitView),
)
check("4.2 cockpit.target matches fixture", cockpit.target == SAMPLE_FIXTURE_TICKER)
check(
    "4.3 cockpit.calculation_version stable",
    cockpit.calculation_version == "phase5_portfolio_views_v1",
)
check(
    "4.4 cockpit.execution_safety_banner is non-executable",
    cockpit.execution_safety_banner.is_non_executable is True,
)
check(
    "4.5 cockpit.execution_safety_banner requires human review",
    cockpit.execution_safety_banner.requires_human_review is True,
)


# ---------------------------------------------------------------------------
# Section 5 — Allocation summary populated from allocation memory
# ---------------------------------------------------------------------------

check("5.1 allocation_summary populated", cockpit.allocation_summary.record_count == 1)
check(
    "5.2 allocation_summary.has_any_records True",
    cockpit.allocation_summary.has_any_records is True,
)
check(
    "5.3 allocation_summary.action_counts mentions add",
    cockpit.allocation_summary.action_counts.get("add", 0) == 1,
)
check(
    "5.4 allocation_summary.data_source phase4m_allocation_memory",
    cockpit.allocation_summary.data_source == "phase4m_allocation_memory",
)
check(
    "5.5 positions list populated",
    len(cockpit.positions) == 1
    and isinstance(cockpit.positions[0], PositionAllocationView),
)
check(
    "5.6 position[0].allocation_memory_id non-empty",
    bool(cockpit.positions[0].allocation_memory_id),
)
check(
    "5.7 position[0].target matches fixture",
    cockpit.positions[0].target == SAMPLE_FIXTURE_TICKER,
)
check(
    "5.8 position[0].target_allocation_pct == 0.05",
    cockpit.positions[0].target_allocation_pct == 0.05,
)
check(
    "5.9 position[0].risk_level medium",
    cockpit.positions[0].risk_level == "medium",
)
check(
    "5.10 position[0].action add",
    cockpit.positions[0].action == "add",
)


# ---------------------------------------------------------------------------
# Section 6 — Risk budget / cash impact populated only when supported
# ---------------------------------------------------------------------------

# The Phase 5A fixture allocation record does NOT supply risk_budget_pct or
# portfolio_loss_pct, and does NOT supply cash_impact or projected_cash_pct,
# so both views should report has_*=False.
check(
    "6.1 risk_budget.record_count reflects allocation count",
    cockpit.risk_budget.record_count == 1,
)
check(
    "6.2 risk_budget.medium_risk_count == 1 (fixture risk_level=medium)",
    cockpit.risk_budget.medium_risk_count == 1,
)
check(
    "6.3 risk_budget.has_risk_budget False (fixture has no risk_budget_pct)",
    cockpit.risk_budget.has_risk_budget is False,
)
check(
    "6.4 cash_impact.has_cash_impact False (fixture has no cash_impact)",
    cockpit.cash_impact.has_cash_impact is False,
)

# Build a record with risk_budget_pct and cash_impact and verify both views
# populate.
rb_snap = build_allocation_decision_snapshot(
    target=SAMPLE_FIXTURE_TICKER,
    target_allocation_pct=0.06,
    actual_allocation_pct=0.04,
    cash_pct=0.18,
    cash_impact=-1500.0,
    projected_cash_pct=0.16,
    portfolio_loss_pct=0.02,
    risk_budget_pct=0.04,
    risk_level="high",
    as_of=SAMPLE_FIXTURE_AS_OF,
)
rb_record = build_allocation_memory_record(
    target=SAMPLE_FIXTURE_TICKER,
    action="add",
    rationale="Fixture allocation with full risk/cash fields.",
    decision_snapshot=rb_snap,
    review_status="reviewed",
    outcome="pending",
    run_id=SAMPLE_FIXTURE_RUN_ID,
    recorded_at=SAMPLE_FIXTURE_AS_OF,
)
rb_store = FixtureBackedMemoryStore()
rb_store.add_allocation_record(rb_record)
rb_cockpit = build_portfolio_cockpit_view(
    target=SAMPLE_FIXTURE_TICKER, memory_store=rb_store
)
check(
    "6.5 risk_budget.has_risk_budget True when fields supplied",
    rb_cockpit.risk_budget.has_risk_budget is True,
)
check(
    "6.6 risk_budget.max_risk_budget_pct == 0.04",
    rb_cockpit.risk_budget.max_risk_budget_pct == 0.04,
)
check(
    "6.7 risk_budget.high_risk_count == 1",
    rb_cockpit.risk_budget.high_risk_count == 1,
)
check(
    "6.8 cash_impact.has_cash_impact True when fields supplied",
    rb_cockpit.cash_impact.has_cash_impact is True,
)
check(
    "6.9 cash_impact.total_cash_impact == -1500.0",
    rb_cockpit.cash_impact.total_cash_impact == -1500.0,
)
check(
    "6.10 cash_impact.max_projected_cash_pct == 0.16",
    rb_cockpit.cash_impact.max_projected_cash_pct == 0.16,
)


# ---------------------------------------------------------------------------
# Section 7 — TradePlan view populated from allocation memory
# ---------------------------------------------------------------------------

check("7.1 cockpit.trade_plans populated", len(cockpit.trade_plans) == 1)
tp = cockpit.trade_plans[0]
check("7.2 trade plan target matches fixture", tp.target == SAMPLE_FIXTURE_TICKER)
check("7.3 trade plan action add", tp.action == "add")
check(
    "7.4 trade plan levels enumerate all 6 kinds",
    [lvl.kind for lvl in tp.levels]
    == ["entry", "add", "trim", "stop", "target", "review"],
)
check(
    "7.5 trade plan entry level matches target_allocation_pct",
    tp.levels[0].pct == 0.05,
)
check(
    "7.6 trade plan trim level matches min_allocation_pct",
    tp.levels[2].pct == 0.02,
)
check(
    "7.7 trade plan target level matches target_allocation_pct",
    tp.levels[4].pct == 0.05,
)
check(
    "7.8 trade plan data_source phase4m_allocation_memory",
    tp.data_source == "phase4m_allocation_memory",
)
check(
    "7.9 trade plan no approved_for_execution field declared",
    "approved_for_execution" not in TradePlanView.model_fields,
)
check(
    "7.10 trade plan review_trigger view is TradePlanReviewTriggerView",
    isinstance(tp.review_trigger, TradePlanReviewTriggerView),
)


# ---------------------------------------------------------------------------
# Section 8 — Option overlay populated from option trade memory
# ---------------------------------------------------------------------------

check("8.1 cockpit.option_overlays populated", len(cockpit.option_overlays) == 1)
ov = cockpit.option_overlays[0]
check("8.2 overlay target matches fixture", ov.target == SAMPLE_FIXTURE_TICKER)
check("8.3 overlay state 'option'", ov.state == "option")
check("8.4 overlay is_no_trade False", ov.is_no_trade is False)
check(
    "8.5 overlay strategy_summary.strategy_type long_call",
    ov.strategy_summary.strategy_type == "long_call",
)
check(
    "8.6 overlay strategy_summary.expiration matches fixture",
    ov.strategy_summary.expiration == "2026-09-18",
)
check(
    "8.7 overlay risk_reward.max_loss matches fixture",
    ov.risk_reward.max_loss == 300.0,
)
check(
    "8.8 overlay risk_reward.breakeven matches fixture",
    ov.risk_reward.breakeven == 103.0,
)
check(
    "8.9 overlay risk_reward.risk_reward_ratio matches fixture",
    ov.risk_reward.risk_reward_ratio == 2.33,
)
check(
    "8.10 overlay no_trade_reason is None for non-no_trade",
    ov.no_trade_reason is None,
)
check(
    "8.11 overlay data_source phase4m_option_trade_memory",
    ov.data_source == "phase4m_option_trade_memory",
)
check(
    "8.12 overlay no approved_for_execution field declared",
    "approved_for_execution" not in OptionOverlayView.model_fields,
)


# ---------------------------------------------------------------------------
# Section 9 — no_trade option state preserved (no inferred substitute)
# ---------------------------------------------------------------------------

nt_snap = build_option_trade_plan_snapshot(
    target=SAMPLE_FIXTURE_TICKER,
    decision="no_trade",
    strategy_type="no_trade",
    risk_level="undefined",
    as_of=SAMPLE_FIXTURE_AS_OF,
)
nt_record = build_option_trade_memory_record(
    target=SAMPLE_FIXTURE_TICKER,
    decision="no_trade",
    rationale=(
        "Fixture no_trade rationale: insufficient edge or unfavorable IV "
        "regime; Phase 5D must not infer a substitute strategy."
    ),
    plan_snapshot=nt_snap,
    review_status="reviewed",
    outcome="no_trade",
    run_id=SAMPLE_FIXTURE_RUN_ID,
    recorded_at=SAMPLE_FIXTURE_AS_OF,
)
nt_store = FixtureBackedMemoryStore()
nt_store.add_option_trade_record(nt_record)
nt_cockpit = build_portfolio_cockpit_view(
    target=SAMPLE_FIXTURE_TICKER, memory_store=nt_store
)
check("9.1 no_trade cockpit has 1 overlay", len(nt_cockpit.option_overlays) == 1)
nt_ov = nt_cockpit.option_overlays[0]
check("9.2 no_trade overlay state preserved", nt_ov.state == "no_trade")
check("9.3 no_trade overlay is_no_trade True", nt_ov.is_no_trade is True)
check(
    "9.4 no_trade overlay strategy_summary strategy_type preserved",
    nt_ov.strategy_summary.strategy_type == "no_trade",
)
check(
    "9.5 no_trade overlay risk_reward empty (no fabricated metrics)",
    nt_ov.risk_reward.max_loss is None
    and nt_ov.risk_reward.max_gain is None
    and nt_ov.risk_reward.breakeven is None,
)
check(
    "9.6 no_trade overlay no_trade_reason present",
    nt_ov.no_trade_reason is not None
    and nt_ov.no_trade_reason.is_no_trade is True,
)
check(
    "9.7 no_trade overlay no_trade_reason references source record",
    nt_ov.no_trade_reason is not None
    and nt_ov.no_trade_reason.source_record_id
    == nt_record.option_trade_memory_id,
)


# Direct builder check.
nt_reason = build_no_trade_reason_view(nt_record)
check("9.8 build_no_trade_reason_view.is_no_trade True", nt_reason.is_no_trade is True)
check(
    "9.9 build_no_trade_reason_view rationale carried",
    "no_trade" in nt_reason.rationale.lower()
    or "no_trade rationale" in nt_reason.rationale.lower(),
)


# ---------------------------------------------------------------------------
# Section 10 — Missing allocation records produce safe degraded view + warning
# ---------------------------------------------------------------------------

# Use a store with only the option trade record (no allocation).
opt_only_store = FixtureBackedMemoryStore()
opt_only_store.add_option_trade_record(
    make_sample_option_trade_record(snap)
)
opt_only_cockpit = build_portfolio_cockpit_view(
    target=SAMPLE_FIXTURE_TICKER, memory_store=opt_only_store
)
check(
    "10.1 missing allocation -> allocation_summary.record_count == 0",
    opt_only_cockpit.allocation_summary.record_count == 0,
)
check(
    "10.2 missing allocation -> has_any_records False",
    opt_only_cockpit.allocation_summary.has_any_records is False,
)
check(
    "10.3 missing allocation -> positions empty",
    opt_only_cockpit.positions == [],
)
check(
    "10.4 missing allocation -> trade_plans empty",
    opt_only_cockpit.trade_plans == [],
)
check(
    "10.5 missing allocation -> missing_panels includes 'allocation'",
    "allocation" in opt_only_cockpit.missing_data.missing_panels,
)
check(
    "10.6 missing allocation -> missing_panels includes 'trade_plan'",
    "trade_plan" in opt_only_cockpit.missing_data.missing_panels,
)
check(
    "10.7 missing allocation -> option overlay still populated",
    len(opt_only_cockpit.option_overlays) == 1,
)


# ---------------------------------------------------------------------------
# Section 11 — Missing option records produce safe degraded view + warning
# ---------------------------------------------------------------------------

alloc_only_store = FixtureBackedMemoryStore()
alloc_only_store.add_allocation_record(make_sample_allocation_record(snap))
alloc_only_cockpit = build_portfolio_cockpit_view(
    target=SAMPLE_FIXTURE_TICKER, memory_store=alloc_only_store
)
check(
    "11.1 missing option -> option_overlays empty",
    alloc_only_cockpit.option_overlays == [],
)
check(
    "11.2 missing option -> missing_panels includes 'option_overlay'",
    "option_overlay" in alloc_only_cockpit.missing_data.missing_panels,
)
check(
    "11.3 missing option -> allocation summary still populated",
    alloc_only_cockpit.allocation_summary.record_count == 1,
)


# ---------------------------------------------------------------------------
# Section 12 — Missing ticker / no records returns safe empty view
# ---------------------------------------------------------------------------

empty_store = FixtureBackedMemoryStore()
empty_cockpit = build_portfolio_cockpit_view(
    target="NONEXISTENT", memory_store=empty_store
)
check(
    "12.1 empty view target preserved",
    empty_cockpit.target == "NONEXISTENT",
)
check(
    "12.2 empty view positions == []",
    empty_cockpit.positions == [],
)
check(
    "12.3 empty view trade_plans == []",
    empty_cockpit.trade_plans == [],
)
check(
    "12.4 empty view option_overlays == []",
    empty_cockpit.option_overlays == [],
)
check(
    "12.5 empty view missing_panels includes 'allocation','option_overlay','trade_plan'",
    all(
        p in empty_cockpit.missing_data.missing_panels
        for p in ("allocation", "trade_plan", "option_overlay")
    ),
)
check(
    "12.6 empty view allocation_summary.has_any_records False",
    empty_cockpit.allocation_summary.has_any_records is False,
)
check(
    "12.7 empty view risk_budget.has_risk_budget False",
    empty_cockpit.risk_budget.has_risk_budget is False,
)
check(
    "12.8 empty view cash_impact.has_cash_impact False",
    empty_cockpit.cash_impact.has_cash_impact is False,
)
check(
    "12.9 empty view execution_safety_banner still present",
    empty_cockpit.execution_safety_banner.is_non_executable is True,
)


# Bare build with no memory store or query result at all.
bare_cockpit = build_portfolio_cockpit_view(target="BARE")
check(
    "12.10 bare view: warnings mention missing memory",
    any("memory" in w.lower() for w in bare_cockpit.warnings),
)
check(
    "12.11 bare view: missing_panels includes 'memory'",
    "memory" in bare_cockpit.missing_data.missing_panels,
)


# ---------------------------------------------------------------------------
# Section 13 — ExecutionSafetyBannerView present and explicit
# ---------------------------------------------------------------------------

banner = build_execution_safety_banner()
check(
    "13.1 execution_safety_banner.is_non_executable True",
    banner.is_non_executable is True,
)
check(
    "13.2 execution_safety_banner.requires_human_review True",
    banner.requires_human_review is True,
)
check(
    "13.3 execution_safety_banner.message mentions non-executable",
    "execut" in banner.message.lower() and "research-only" in banner.message.lower(),
)


# ---------------------------------------------------------------------------
# Section 14 — No approved_for_execution=True anywhere
# ---------------------------------------------------------------------------

cockpit_json = cockpit.model_dump_json()
check(
    "14.1 cockpit JSON does not contain approved_for_execution=true",
    '"approved_for_execution": true' not in cockpit_json.lower()
    and '"approved_for_execution":true' not in cockpit_json.lower(),
)

# Phase 5D view models themselves must not declare approved_for_execution.
for cls in (
    PortfolioCockpitView,
    AllocationSummaryView,
    PositionAllocationView,
    RiskBudgetView,
    CashImpactView,
    TradePlanView,
    TradePlanLevelView,
    TradePlanReviewTriggerView,
    OptionOverlayView,
    OptionStrategySummaryView,
    OptionRiskRewardView,
    OptionLiquidityWarningView,
    OptionEventRiskWarningView,
    NoTradeReasonView,
    ExecutionSafetyBannerView,
    MissingPortfolioDataWarningView,
):
    field_names = set(cls.model_fields.keys())
    check(
        f"14.2 {cls.__name__}: approved_for_execution not a field",
        "approved_for_execution" not in field_names,
    )


# ---------------------------------------------------------------------------
# Section 15 — No executable order fields are declared on any view
# ---------------------------------------------------------------------------

_FORBIDDEN_EXECUTABLE_FIELDS = {
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
}
for cls in (
    PortfolioCockpitView,
    AllocationSummaryView,
    PositionAllocationView,
    RiskBudgetView,
    CashImpactView,
    TradePlanView,
    TradePlanLevelView,
    TradePlanReviewTriggerView,
    OptionOverlayView,
    OptionStrategySummaryView,
    OptionRiskRewardView,
    OptionLiquidityWarningView,
    OptionEventRiskWarningView,
    NoTradeReasonView,
    ExecutionSafetyBannerView,
    MissingPortfolioDataWarningView,
):
    fields = set(cls.model_fields.keys())
    leaks = fields & _FORBIDDEN_EXECUTABLE_FIELDS
    check(
        f"15.x {cls.__name__}: no executable-order fields declared",
        not leaks,
        f"leaked executable-order fields: {sorted(leaks)}",
    )


# ---------------------------------------------------------------------------
# Section 16 — Builder rejects empty / whitespace target
# ---------------------------------------------------------------------------

expect_error(
    "16.1 build_portfolio_cockpit_view empty target raises",
    lambda: build_portfolio_cockpit_view(target=""),
    exc_type=ValueError,
)
expect_error(
    "16.2 build_portfolio_cockpit_view whitespace target raises",
    lambda: build_portfolio_cockpit_view(target="   "),
    exc_type=ValueError,
)
expect_error(
    "16.3 build_allocation_summary_view empty target raises",
    lambda: build_allocation_summary_view(target="", allocation_records=[]),
    exc_type=ValueError,
)


# ---------------------------------------------------------------------------
# Section 17 — Deterministic serialization across rebuilds
# ---------------------------------------------------------------------------

snap_r, adapter_r, bundle_r = build_sample_fixture_pack()
store_r = FixtureBackedMemoryStore()
store_r.register_bundle(bundle_r)
cockpit_r = build_portfolio_cockpit_view(
    target=SAMPLE_FIXTURE_TICKER, memory_store=store_r
)
check(
    "17.1 cockpit deterministic JSON across rebuilds",
    json.dumps(cockpit.model_dump(mode="json"), sort_keys=True)
    == json.dumps(cockpit_r.model_dump(mode="json"), sort_keys=True),
)


# ---------------------------------------------------------------------------
# Section 18 — Build with explicit MemoryQueryResult
# ---------------------------------------------------------------------------

qres = store.query(MemoryQueryByTicker(target=SAMPLE_FIXTURE_TICKER))
cockpit_q = build_portfolio_cockpit_view(
    target=SAMPLE_FIXTURE_TICKER, memory_query_result=qres
)
check(
    "18.1 build with explicit MemoryQueryResult: cockpit equals store version",
    json.dumps(cockpit_q.model_dump(mode="json"), sort_keys=True)
    == json.dumps(cockpit.model_dump(mode="json"), sort_keys=True),
)


# ---------------------------------------------------------------------------
# Section 19 — Human-feedback review surfacing
# ---------------------------------------------------------------------------

# Build a human feedback record with review_required=True scoped to target,
# and confirm that both the trade plan view and option overlay view pick up
# the review reason.
hf_target_ref = build_human_feedback_target_ref(
    target_id="fix5d_target_artifact_1",
    target_type="research_run_memory",
    run_id=SAMPLE_FIXTURE_RUN_ID,
    label="Fixture HF target ref",
    as_of=SAMPLE_FIXTURE_AS_OF,
)
hf_entry = build_human_feedback_entry(
    feedback_id="fix5d_feedback_1",
    feedback_text="Reviewer requests follow-up before relying on this allocation.",
    decision="deferred",
    reason_type="risk_too_high",
    actor="reviewer",
    created_at=SAMPLE_FIXTURE_AS_OF,
)
hf_record = build_human_feedback_memory_record(
    target=SAMPLE_FIXTURE_TICKER,
    target_ref=hf_target_ref,
    feedback_entries=[hf_entry],
    outcome="pending",
    run_id=SAMPLE_FIXTURE_RUN_ID,
    review_required=True,
    recorded_at=SAMPLE_FIXTURE_AS_OF,
)

hf_store = FixtureBackedMemoryStore()
hf_store.add_allocation_record(make_sample_allocation_record(snap))
hf_store.add_option_trade_record(make_sample_option_trade_record(snap))
hf_store.add_human_feedback_record(hf_record)

hf_cockpit = build_portfolio_cockpit_view(
    target=SAMPLE_FIXTURE_TICKER, memory_store=hf_store
)
check(
    "19.1 human feedback review_required surfaces on trade plan",
    hf_cockpit.trade_plans[0].review_trigger.review_needed is True
    and any(
        "human feedback" in r.lower()
        for r in hf_cockpit.trade_plans[0].review_trigger.reasons
    ),
)
check(
    "19.2 human feedback review_required surfaces on option overlay",
    hf_cockpit.option_overlays[0].review_needed is True
    and any(
        "human feedback" in r.lower()
        for r in hf_cockpit.option_overlays[0].review_reasons
    ),
)
check(
    "19.3 human feedback review_required surfaces on position view",
    hf_cockpit.positions[0].review_needed is True,
)
check(
    "19.4 human feedback recorded -> missing_panels does NOT include 'human_feedback'",
    "human_feedback" not in hf_cockpit.missing_data.missing_panels,
)


# ---------------------------------------------------------------------------
# Section 20 — Direct builder calls match aggregator output
# ---------------------------------------------------------------------------

# Build the allocation record directly via the fixture and confirm the
# position / trade plan views are equivalent.
alloc_rec = make_sample_allocation_record(snap)
direct_pos = build_position_allocation_view(record=alloc_rec)
check(
    "20.1 direct PositionAllocationView allocation_memory_id matches",
    direct_pos.allocation_memory_id == cockpit.positions[0].allocation_memory_id,
)
direct_tp = build_trade_plan_view(record=alloc_rec)
check(
    "20.2 direct TradePlanView levels match aggregator",
    [lvl.kind for lvl in direct_tp.levels]
    == [lvl.kind for lvl in cockpit.trade_plans[0].levels],
)
direct_ov = build_option_overlay_view(record=make_sample_option_trade_record(snap))
check(
    "20.3 direct OptionOverlayView option_trade_memory_id matches aggregator",
    direct_ov.option_trade_memory_id
    == cockpit.option_overlays[0].option_trade_memory_id,
)


# ---------------------------------------------------------------------------
# Section 21 — Package-level re-exports through lib/reliability/__init__.py
# ---------------------------------------------------------------------------

import lib.reliability as _r

_PHASE5D_EXPECTED_EXPORTS = (
    "AllocationSummaryView",
    "CashImpactView",
    "ExecutionSafetyBannerView",
    "MissingPortfolioDataWarningView",
    "MissingPortfolioPanel",
    "NoTradeReasonView",
    "OptionEventRiskWarningView",
    "OptionLiquidityWarningView",
    "OptionOverlayState",
    "OptionOverlayView",
    "OptionRiskRewardView",
    "OptionStrategySummaryView",
    "PortfolioCockpitView",
    "PortfolioDataSource",
    "PositionAllocationView",
    "RiskBudgetView",
    "TRADE_PLAN_LEVEL_KINDS",
    "TradePlanLevelKind",
    "TradePlanLevelView",
    "TradePlanReviewTriggerView",
    "TradePlanView",
    "build_allocation_summary_view",
    "build_execution_safety_banner",
    "build_no_trade_reason_view",
    "build_option_overlay_view",
    "build_portfolio_cockpit_view",
    "build_position_allocation_view",
    "build_trade_plan_view",
)

for name in _PHASE5D_EXPECTED_EXPORTS:
    check(
        f"21.x lib.reliability re-exports {name}",
        hasattr(_r, name) and name in _r.__all__,
    )


# ---------------------------------------------------------------------------
# Section 22 — __all__ symmetry between module and re-exports
# ---------------------------------------------------------------------------

check(
    "22.1 module __all__ contains all Phase 5D view symbols",
    set(_PHASE5D_EXPECTED_EXPORTS).issubset(set(_pv_mod.__all__)),
)


# ---------------------------------------------------------------------------
# Section 23 — No filesystem writes during the Phase 5D pipeline
# ---------------------------------------------------------------------------

_before = (
    set(pathlib.Path(_REPO_ROOT, "research").rglob("*"))
    if pathlib.Path(_REPO_ROOT, "research").exists()
    else set()
)
_ = build_portfolio_cockpit_view(target=SAMPLE_FIXTURE_TICKER, memory_store=store)
_ = build_portfolio_cockpit_view(target="UNK")
_after = (
    set(pathlib.Path(_REPO_ROOT, "research").rglob("*"))
    if pathlib.Path(_REPO_ROOT, "research").exists()
    else set()
)
check("23.1 no new files written under research/", _before == _after)


# ---------------------------------------------------------------------------
# Section 24 — Phase 5C regression: HorizonDecisionCardsView still builds
# ---------------------------------------------------------------------------

from lib.reliability.phase5_horizon_views import (
    HorizonDecisionCardsView,
    build_horizon_decision_cards_view,
)

phase5c_view = build_horizon_decision_cards_view(
    target=SAMPLE_FIXTURE_TICKER, memory_store=store
)
check(
    "24.1 Phase 5C HorizonDecisionCardsView still builds",
    isinstance(phase5c_view, HorizonDecisionCardsView),
)
check(
    "24.2 Phase 5C three cards short/medium/long",
    [c.horizon for c in phase5c_view.cards] == ["short", "medium", "long"],
)


# ---------------------------------------------------------------------------
# Section 25 — Phase 5B regression: CompanyResearchHubView still builds
# ---------------------------------------------------------------------------

from lib.reliability.company_research_hub import (
    CompanyResearchHubView,
    build_company_research_hub_view,
)

phase5b_view = build_company_research_hub_view(
    target=SAMPLE_FIXTURE_TICKER, snapshot=snap, memory_store=store
)
check(
    "25.1 Phase 5B CompanyResearchHubView still builds from fixture",
    isinstance(phase5b_view, CompanyResearchHubView),
)
check(
    "25.2 Phase 5B equity panel still populated",
    phase5b_view.equity_panel.is_populated is True,
)


# ---------------------------------------------------------------------------
# Section 26 — Phase 5A regression: MemoryQueryResult contract preserved
# ---------------------------------------------------------------------------

q5a = store.query(MemoryQueryByTicker(target=SAMPLE_FIXTURE_TICKER))
check(
    "26.1 Phase 5A MemoryQueryResult.approved_for_execution=False",
    q5a.approved_for_execution is False,
)
check(
    "26.2 Phase 5A allocation_records carry target",
    all(r.target == SAMPLE_FIXTURE_TICKER for r in q5a.allocation_records),
)
check(
    "26.3 Phase 5A option_trade_records carry target",
    all(r.target == SAMPLE_FIXTURE_TICKER for r in q5a.option_trade_records),
)


# ---------------------------------------------------------------------------
# Section 27 — Option warning surfacing from upstream warnings
# ---------------------------------------------------------------------------

# Build an option record carrying a liquidity warning and an event-risk
# warning via the upstream record's warnings list (passed through
# extra_warnings) and confirm both surface deterministically.
warn_snap = build_option_trade_plan_snapshot(
    target=SAMPLE_FIXTURE_TICKER,
    decision="option",
    strategy_type="long_call",
    expiration="2026-09-18",
    entry_iv=0.45,
    entry_underlying_price=110.0,
    max_loss=400.0,
    max_gain=600.0,
    breakeven=114.0,
    cash_required=400.0,
    risk_reward_ratio=1.5,
    contracts=1,
    risk_level="high",
    as_of=SAMPLE_FIXTURE_AS_OF,
)
warn_record = build_option_trade_memory_record(
    target=SAMPLE_FIXTURE_TICKER,
    decision="option",
    rationale=(
        "Fixture option record with liquidity and event-risk warnings "
        "passed through extra_warnings."
    ),
    plan_snapshot=warn_snap,
    review_status="reviewed",
    outcome="pending",
    run_id=SAMPLE_FIXTURE_RUN_ID,
    recorded_at=SAMPLE_FIXTURE_AS_OF,
    extra_warnings=[
        "Liquidity warning: wide bid-ask spread observed.",
        "Event risk warning: earnings inside expiration window.",
    ],
)
warn_view = build_option_overlay_view(record=warn_record)
check(
    "27.1 option overlay liquidity warning surfaces",
    warn_view.liquidity_warning.has_liquidity_warning is True
    and any("bid-ask" in w.lower() for w in warn_view.liquidity_warning.warnings),
)
check(
    "27.2 option overlay event risk warning surfaces",
    warn_view.event_risk_warning.has_event_risk_warning is True
    and any(
        "earnings" in w.lower() or "expiration" in w.lower()
        for w in warn_view.event_risk_warning.warnings
    ),
)


# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------

print("=" * 70)
print("Phase 5D — Portfolio / TradePlan / Option Overlay — test results")
print("=" * 70)
print()
print(f"Passed: {PASS}")
print(f"Failed: {FAIL}")
print(f"Total:  {PASS + FAIL}")
print()
if FAIL:
    print("Failures:")
    for f in _failures:
        print("  " + f)
    print()
    print("RESULT: FAIL — Phase 5D contract NOT verified.")
    sys.exit(1)
else:
    print("RESULT: PASS — Phase 5D contract verified.")
    sys.exit(0)
