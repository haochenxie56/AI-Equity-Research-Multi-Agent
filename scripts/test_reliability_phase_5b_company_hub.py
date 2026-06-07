#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5b_company_hub.py

Phase 5B: Company Research Hub ViewModel Contract test suite.

Validates:
  - lib/reliability/company_research_hub.py imports without loading any
    forbidden live runtime module (Streamlit, workflow_state,
    llm_orchestrator, data_fetcher, Anthropic SDK, etc.).
  - Source-level forbidden import substrings are absent.
  - build_company_research_hub_view() produces a deterministic
    CompanyResearchHubView from the Phase 5A fixture pack.
  - Equity, Financial, PriceVolume panels populate correctly from the
    fixture workflow snapshot.
  - SourceWorkflowPanelView surfaces synthesis when present.
  - Missing Equity / Financial / PriceVolume step yields safe degraded
    panel views and a MissingDataWarningView entry.
  - Missing ticker / no records yields a safe empty view rather than
    hallucinated content.
  - EvidenceCoveragePanelView reports available / missing source steps
    deterministically.
  - ValidationStatusPanelView never fabricates validation success.
  - No approved_for_execution=True appears anywhere in the view model.
  - Deterministic serialization across rebuilds.
  - Package-level re-exports.

Usage:
    python3 scripts/test_reliability_phase_5b_company_hub.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

# Add repo root to sys.path
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

from lib.reliability import company_research_hub as _hub_mod

check("1.1 company_research_hub importable", _hub_mod is not None)

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
# Section 2 — Source-level forbidden imports check
# ---------------------------------------------------------------------------

_PHASE5B_SOURCES = [
    pathlib.Path(_REPO_ROOT) / "lib" / "reliability" / "company_research_hub.py",
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

for src in _PHASE5B_SOURCES:
    text = src.read_text(encoding="utf-8")
    for sub in _FORBIDDEN_SUBSTRINGS:
        check(
            f"2.{src.name}::{sub!r}",
            sub not in text,
            f"forbidden substring {sub!r} found in {src.name}",
        )


# ---------------------------------------------------------------------------
# Section 3 — Imports from the module
# ---------------------------------------------------------------------------

from lib.reliability.company_research_hub import (
    CompanyIdentityView,
    CompanyResearchHubView,
    DataSourceTag,
    EquityResearchPanelView,
    EvidenceCoveragePanelView,
    FinancialValuationPanelView,
    MissingDataPanel,
    MissingDataWarningView,
    PriceVolumeTimingPanelView,
    SourceWorkflowPanelView,
    ValidationStatusPanelView,
    build_company_identity_view,
    build_company_research_hub_view,
    build_equity_research_panel,
    build_evidence_coverage_panel,
    build_financial_valuation_panel,
    build_price_volume_timing_panel,
    build_source_workflow_panel,
    build_validation_status_panel,
)
from lib.reliability.phase5_fixtures import (
    SAMPLE_FIXTURE_AS_OF,
    SAMPLE_FIXTURE_RUN_ID,
    SAMPLE_FIXTURE_TICKER,
    build_sample_fixture_pack,
    make_sample_workflow_snapshot,
)
from lib.reliability.phase5_memory_query import (
    FixtureBackedMemoryStore,
    MemoryQuery,
    MemoryQueryByTicker,
    MemoryQueryResult,
)
from lib.reliability.workflow_memory_adapter import (
    ExistingPageOutputRef,
    ExistingWorkflowSnapshot,
    ExistingWorkflowStepSnapshot,
    ExistingWorkflowSynthesisSnapshot,
    InMemoryWorkflowToMemoryAdapter,
    make_workflow_snapshot_id,
)

check("3.1 CompanyResearchHubView class importable", CompanyResearchHubView is not None)
check("3.2 builder importable", build_company_research_hub_view is not None)


# ---------------------------------------------------------------------------
# Section 4 — Build full CompanyResearchHubView from Phase 5A fixture pack
# ---------------------------------------------------------------------------

snap, adapter, bundle = build_sample_fixture_pack()
store = FixtureBackedMemoryStore()
store.register_bundle(bundle)

view = build_company_research_hub_view(
    target=SAMPLE_FIXTURE_TICKER,
    snapshot=snap,
    memory_store=store,
)

check("4.1 view is CompanyResearchHubView", isinstance(view, CompanyResearchHubView))
check("4.2 identity target matches fixture", view.identity.target == SAMPLE_FIXTURE_TICKER)
check("4.3 identity run_id matches fixture", view.identity.run_id == SAMPLE_FIXTURE_RUN_ID)
check("4.4 identity as_of matches fixture", view.identity.as_of == SAMPLE_FIXTURE_AS_OF)
check(
    "4.5 identity snapshot_id deterministic",
    view.identity.snapshot_id
    == make_workflow_snapshot_id(
        run_id=SAMPLE_FIXTURE_RUN_ID,
        target=SAMPLE_FIXTURE_TICKER,
        as_of=SAMPLE_FIXTURE_AS_OF,
    ),
)
check("4.6 identity data_source labels snapshot", view.identity.data_source == "existing_workflow_snapshot")
check("4.7 view.calculation_version stable", view.calculation_version == "company_research_hub_v1")
check("4.8 no top-level warnings (full fixture)", view.warnings == [])


# ---------------------------------------------------------------------------
# Section 5 — Equity panel populated from fixture workflow data
# ---------------------------------------------------------------------------

ep = view.equity_panel
check("5.1 equity panel populated", ep.is_populated is True)
check("5.2 equity target matches", ep.target == SAMPLE_FIXTURE_TICKER)
check("5.3 equity step_status complete", ep.step_status == "complete")
check("5.4 equity has page_outputs", len(ep.page_outputs) == 1)
check(
    "5.5 equity page_output matches fixture",
    ep.page_outputs[0].page == "Equity"
    and ep.page_outputs[0].step == "equity"
    and ep.page_outputs[0].artifact_id == "fix5a_equity_artifact",
)
check(
    "5.6 equity research_run_memory_ids non-empty",
    len(ep.research_run_memory_ids) == 1 and ep.research_run_memory_ids[0].startswith("rmem_"),
)
check("5.7 equity data_source labels snapshot", ep.data_source == "existing_workflow_snapshot")
check("5.8 equity no warnings (populated case)", ep.warnings == [])


# ---------------------------------------------------------------------------
# Section 6 — Financial panel populated from fixture workflow data
# ---------------------------------------------------------------------------

fp = view.financial_panel
check("6.1 financial panel populated", fp.is_populated is True)
check("6.2 financial target matches", fp.target == SAMPLE_FIXTURE_TICKER)
check("6.3 financial step_status complete", fp.step_status == "complete")
check(
    "6.4 financial page_output matches fixture",
    len(fp.page_outputs) == 1
    and fp.page_outputs[0].page == "Financial"
    and fp.page_outputs[0].step == "financial",
)
check(
    "6.5 financial allocation_memory_ids include fixture allocation",
    len(fp.allocation_memory_ids) == 1
    and fp.allocation_memory_ids[0].startswith("amem_"),
)
check(
    "6.6 financial valuation_context_notes contains allocation rationale",
    len(fp.valuation_context_notes) >= 1,
)
check("6.7 financial data_source labels snapshot", fp.data_source == "existing_workflow_snapshot")


# ---------------------------------------------------------------------------
# Section 7 — PriceVolume panel populated from fixture workflow data
# ---------------------------------------------------------------------------

pp = view.price_volume_panel
check("7.1 price/volume panel populated", pp.is_populated is True)
check("7.2 price/volume target matches", pp.target == SAMPLE_FIXTURE_TICKER)
check(
    "7.3 price/volume page_output matches fixture",
    len(pp.page_outputs) == 1
    and pp.page_outputs[0].page == "PriceVolume"
    and pp.page_outputs[0].step == "price_volume",
)
check("7.4 price/volume data_source labels snapshot", pp.data_source == "existing_workflow_snapshot")


# ---------------------------------------------------------------------------
# Section 8 — Source workflow panel synthesis present
# ---------------------------------------------------------------------------

sp = view.source_workflow_panel
check("8.1 synthesis present", sp.synthesis_present is True)
check(
    "8.2 synthesis_summary surfaced from fixture",
    sp.synthesis_summary == "Mock five-step synthesis (fixture only).",
)
check("8.3 synthesis_status complete", sp.synthesis_status == "complete")
check(
    "8.4 present_step_keys contains all six fixture steps",
    sp.present_step_keys == ["sector", "scanner", "equity", "financial", "price_volume", "synthesis"],
)
check("8.5 missing_step_keys empty when all steps present", sp.missing_step_keys == [])
check(
    "8.6 step_statuses sized to present steps",
    set(sp.step_statuses.keys()) == set(sp.present_step_keys),
)


# ---------------------------------------------------------------------------
# Section 9 — Missing Equity panel returns safe degraded view + warning
# ---------------------------------------------------------------------------

snap_no_equity = ExistingWorkflowSnapshot(
    run_id=SAMPLE_FIXTURE_RUN_ID,
    target=SAMPLE_FIXTURE_TICKER,
    as_of=SAMPLE_FIXTURE_AS_OF,
    workflow_name="five_step_research_workflow",
    steps={
        "sector": ExistingWorkflowStepSnapshot(step="sector", status="complete"),
        "scanner": ExistingWorkflowStepSnapshot(step="scanner", status="complete"),
        "financial": ExistingWorkflowStepSnapshot(step="financial", status="complete"),
        "price_volume": ExistingWorkflowStepSnapshot(step="price_volume", status="complete"),
        "synthesis": ExistingWorkflowStepSnapshot(step="synthesis", status="complete"),
    },
    synthesis=ExistingWorkflowSynthesisSnapshot(status="complete", summary="syn"),
)
view_no_equity = build_company_research_hub_view(
    target=SAMPLE_FIXTURE_TICKER,
    snapshot=snap_no_equity,
    memory_store=None,
)
check(
    "9.1 missing equity -> equity panel not populated",
    view_no_equity.equity_panel.is_populated is False,
)
check("9.2 missing equity -> equity step_status unknown", view_no_equity.equity_panel.step_status == "unknown")
check(
    "9.3 missing equity -> equity warnings non-empty",
    len(view_no_equity.equity_panel.warnings) >= 1
    and "equity" in view_no_equity.equity_panel.warnings[0].lower(),
)
check("9.4 missing equity -> equity data_source absent", view_no_equity.equity_panel.data_source == "absent")
check(
    "9.5 missing equity -> missing_data lists equity",
    "equity" in view_no_equity.missing_data.missing_panels,
)
check(
    "9.6 missing equity -> missing_data warnings non-empty",
    any("equity" in w.lower() for w in view_no_equity.missing_data.warnings),
)


# ---------------------------------------------------------------------------
# Section 10 — Missing Financial panel returns safe degraded view + warning
# ---------------------------------------------------------------------------

snap_no_financial = ExistingWorkflowSnapshot(
    run_id=SAMPLE_FIXTURE_RUN_ID,
    target=SAMPLE_FIXTURE_TICKER,
    as_of=SAMPLE_FIXTURE_AS_OF,
    steps={
        "equity": ExistingWorkflowStepSnapshot(step="equity", status="complete"),
        "price_volume": ExistingWorkflowStepSnapshot(step="price_volume", status="complete"),
    },
)
view_no_fin = build_company_research_hub_view(
    target=SAMPLE_FIXTURE_TICKER, snapshot=snap_no_financial, memory_store=None
)
check(
    "10.1 missing financial -> financial panel not populated",
    view_no_fin.financial_panel.is_populated is False,
)
check(
    "10.2 missing financial -> financial warnings non-empty",
    len(view_no_fin.financial_panel.warnings) >= 1,
)
check(
    "10.3 missing financial -> missing_data lists financial",
    "financial" in view_no_fin.missing_data.missing_panels,
)
check(
    "10.4 missing financial -> financial data_source absent",
    view_no_fin.financial_panel.data_source == "absent",
)


# ---------------------------------------------------------------------------
# Section 11 — Missing PriceVolume panel returns safe degraded view + warning
# ---------------------------------------------------------------------------

snap_no_pv = ExistingWorkflowSnapshot(
    run_id=SAMPLE_FIXTURE_RUN_ID,
    target=SAMPLE_FIXTURE_TICKER,
    as_of=SAMPLE_FIXTURE_AS_OF,
    steps={
        "equity": ExistingWorkflowStepSnapshot(step="equity", status="complete"),
        "financial": ExistingWorkflowStepSnapshot(step="financial", status="complete"),
    },
)
view_no_pv = build_company_research_hub_view(
    target=SAMPLE_FIXTURE_TICKER, snapshot=snap_no_pv, memory_store=None
)
check(
    "11.1 missing price_volume -> price_volume panel not populated",
    view_no_pv.price_volume_panel.is_populated is False,
)
check(
    "11.2 missing price_volume -> price_volume warnings non-empty",
    len(view_no_pv.price_volume_panel.warnings) >= 1,
)
check(
    "11.3 missing price_volume -> missing_data lists price_volume",
    "price_volume" in view_no_pv.missing_data.missing_panels,
)


# ---------------------------------------------------------------------------
# Section 12 — Missing synthesis surfaces warning
# ---------------------------------------------------------------------------

snap_no_syn = ExistingWorkflowSnapshot(
    run_id=SAMPLE_FIXTURE_RUN_ID,
    target=SAMPLE_FIXTURE_TICKER,
    as_of=SAMPLE_FIXTURE_AS_OF,
    steps={
        "equity": ExistingWorkflowStepSnapshot(step="equity", status="complete"),
        "financial": ExistingWorkflowStepSnapshot(step="financial", status="complete"),
        "price_volume": ExistingWorkflowStepSnapshot(step="price_volume", status="complete"),
    },
)
view_no_syn = build_company_research_hub_view(
    target=SAMPLE_FIXTURE_TICKER, snapshot=snap_no_syn, memory_store=None
)
check(
    "12.1 missing synthesis -> synthesis_present False",
    view_no_syn.source_workflow_panel.synthesis_present is False,
)
check(
    "12.2 missing synthesis -> source_workflow_panel warnings non-empty",
    len(view_no_syn.source_workflow_panel.warnings) >= 1,
)
check(
    "12.3 missing synthesis -> missing_data lists synthesis",
    "synthesis" in view_no_syn.missing_data.missing_panels,
)


# ---------------------------------------------------------------------------
# Section 13 — Missing ticker / no query results returns empty safe view
# ---------------------------------------------------------------------------

empty_store = FixtureBackedMemoryStore()
view_empty = build_company_research_hub_view(
    target="NONEXISTENT", snapshot=None, memory_store=empty_store
)
check("13.1 empty view: identity target preserved", view_empty.identity.target == "NONEXISTENT")
check("13.2 empty view: identity data_source absent", view_empty.identity.data_source == "absent")
check("13.3 empty view: equity not populated", view_empty.equity_panel.is_populated is False)
check("13.4 empty view: financial not populated", view_empty.financial_panel.is_populated is False)
check("13.5 empty view: price_volume not populated", view_empty.price_volume_panel.is_populated is False)
check(
    "13.6 empty view: synthesis_present False",
    view_empty.source_workflow_panel.synthesis_present is False,
)
check(
    "13.7 empty view: missing_data lists identity",
    "identity" in view_empty.missing_data.missing_panels,
)
check(
    "13.8 empty view: evidence_coverage available source steps empty",
    view_empty.evidence_coverage_panel.available_source_steps == [],
)
check(
    "13.9 empty view: evidence_coverage missing all source steps",
    set(view_empty.evidence_coverage_panel.missing_source_steps)
    == {"sector", "scanner", "equity", "financial", "price_volume", "synthesis"},
)
check(
    "13.10 empty view: evidence_coverage total memory record count zero",
    view_empty.evidence_coverage_panel.total_memory_record_count == 0,
)
check(
    "13.11 empty view: validation panel has no signal",
    view_empty.validation_status_panel.has_any_validation_signal is False,
)
check(
    "13.12 empty view: validation panel not clean (no fabrication)",
    view_empty.validation_status_panel.is_clean is False,
)


# ---------------------------------------------------------------------------
# Section 14 — Evidence coverage deterministic and accurate
# ---------------------------------------------------------------------------

ev = view.evidence_coverage_panel
check(
    "14.1 evidence_coverage available_source_steps deterministic order",
    ev.available_source_steps
    == ["sector", "scanner", "equity", "financial", "price_volume", "synthesis"],
)
check("14.2 evidence_coverage missing_source_steps empty for full fixture", ev.missing_source_steps == [])
check(
    "14.3 evidence_coverage has_complete_step_coverage True for full fixture",
    ev.has_complete_step_coverage is True,
)
check(
    "14.4 evidence_coverage available_memory_record_types includes thesis/research_run/event/allocation/option_trade/human_feedback/agent_evaluation",
    set(ev.available_memory_record_types)
    == {
        "research_run",
        "thesis",
        "event",
        "allocation",
        "option_trade",
        "human_feedback",
        "agent_evaluation",
    },
)
check(
    "14.5 evidence_coverage record counts deterministic",
    ev.memory_record_counts_by_type
    == {
        "research_run": 1,
        "thesis": 3,
        "event": 1,
        "allocation": 1,
        "option_trade": 1,
        "human_feedback": 1,
        "agent_evaluation": 1,
    },
)
check(
    "14.6 evidence_coverage total_memory_record_count sums correctly",
    ev.total_memory_record_count == 9,
)
check(
    "14.7 evidence_coverage has_any_memory_records True",
    ev.has_any_memory_records is True,
)


# ---------------------------------------------------------------------------
# Section 15 — Validation status panel does not fabricate validation success
# ---------------------------------------------------------------------------

vs = view.validation_status_panel
check("15.1 validation inspected_record_count == 9", vs.inspected_record_count == 9)
check("15.2 validation has_any_validation_signal True", vs.has_any_validation_signal is True)
# At least one fixture record carries summary.review_required=True (research run
# memory's summary). is_clean must NOT be True in that case.
check(
    "15.3 validation is_clean reflects record state, no fabrication",
    vs.is_clean is False,
)
check("15.4 validation blocked_count is 0", vs.blocked_count == 0)
check("15.5 validation needs_review_count is 0", vs.needs_review_count == 0)
check("15.6 validation review_required_count >= 1", vs.review_required_count >= 1)

# No-records case must not claim clean validation
vs_empty = build_validation_status_panel(memory_query_result=None)
check(
    "15.7 validation empty: has_any_validation_signal False",
    vs_empty.has_any_validation_signal is False,
)
check("15.8 validation empty: is_clean False (no fabrication)", vs_empty.is_clean is False)
check("15.9 validation empty: warnings non-empty", len(vs_empty.warnings) >= 1)


# ---------------------------------------------------------------------------
# Section 16 — No approved_for_execution=True appears anywhere in the view
# ---------------------------------------------------------------------------

view_json = view.model_dump_json()
check(
    "16.1 view JSON does not contain approved_for_execution=true literal",
    '"approved_for_execution": true' not in view_json.lower().replace(" ", "")
    and '"approved_for_execution":true' not in view_json.lower(),
)
# Also any nested record dumps from page_outputs etc. should not contain True
check(
    "16.2 view JSON does not contain approved_for_execution=True at all",
    "approved_for_execution" not in view.model_dump_json()
    or "approved_for_execution\": false" in view.model_dump_json().lower()
    or "approved_for_execution\":false" in view.model_dump_json().lower(),
)
# The view's own Pydantic models simply do not declare approved_for_execution.
for cls in (
    CompanyResearchHubView,
    CompanyIdentityView,
    EquityResearchPanelView,
    FinancialValuationPanelView,
    PriceVolumeTimingPanelView,
    SourceWorkflowPanelView,
    EvidenceCoveragePanelView,
    ValidationStatusPanelView,
    MissingDataWarningView,
):
    field_names = set(cls.model_fields.keys())
    check(
        f"16.3 {cls.__name__}: approved_for_execution not a field",
        "approved_for_execution" not in field_names,
    )


# ---------------------------------------------------------------------------
# Section 17 — Deterministic serialization across rebuilds
# ---------------------------------------------------------------------------

snap2, adapter2, bundle2 = build_sample_fixture_pack()
store2 = FixtureBackedMemoryStore()
store2.register_bundle(bundle2)
view2 = build_company_research_hub_view(
    target=SAMPLE_FIXTURE_TICKER, snapshot=snap2, memory_store=store2
)
check(
    "17.1 deterministic JSON across rebuilds",
    json.dumps(view.model_dump(mode="json"), sort_keys=True)
    == json.dumps(view2.model_dump(mode="json"), sort_keys=True),
)


# ---------------------------------------------------------------------------
# Section 18 — Build with MemoryQueryResult parameter directly
# ---------------------------------------------------------------------------

qres = store.query(MemoryQueryByTicker(target=SAMPLE_FIXTURE_TICKER))
view_with_qr = build_company_research_hub_view(
    target=SAMPLE_FIXTURE_TICKER,
    snapshot=snap,
    memory_query_result=qres,
)
check(
    "18.1 view with explicit MemoryQueryResult builds equally",
    view_with_qr.evidence_coverage_panel.total_memory_record_count == 9,
)
check(
    "18.2 view with explicit MemoryQueryResult validation panel has signal",
    view_with_qr.validation_status_panel.has_any_validation_signal is True,
)


# ---------------------------------------------------------------------------
# Section 19 — Builder rejects empty / whitespace target
# ---------------------------------------------------------------------------

expect_error(
    "19.1 build_company_research_hub_view empty target raises",
    lambda: build_company_research_hub_view(target=""),
    exc_type=ValueError,
)
expect_error(
    "19.2 build_company_research_hub_view whitespace target raises",
    lambda: build_company_research_hub_view(target="   "),
    exc_type=ValueError,
)
expect_error(
    "19.3 build_company_identity_view empty target raises",
    lambda: build_company_identity_view(target=""),
    exc_type=ValueError,
)


# ---------------------------------------------------------------------------
# Section 20 — Snapshot with approved_for_execution=True must be rejected at
#              Phase 5A model layer (defense in depth; builder inherits this)
# ---------------------------------------------------------------------------

# This test ensures Phase 5B never silently constructs an unsafe view.
def _make_approved_snapshot():
    ExistingWorkflowSnapshot(
        run_id=SAMPLE_FIXTURE_RUN_ID,
        target=SAMPLE_FIXTURE_TICKER,
        as_of=SAMPLE_FIXTURE_AS_OF,
        approved_for_execution=True,
    )


expect_error(
    "20.1 ExistingWorkflowSnapshot rejects approved_for_execution=True",
    _make_approved_snapshot,
    exc_type=Exception,  # Pydantic ValidationError or ValueError
    keyword="approved_for_execution",
)


# ---------------------------------------------------------------------------
# Section 21 — Per-builder direct calls match aggregator output
# ---------------------------------------------------------------------------

eq_direct = build_equity_research_panel(
    target=SAMPLE_FIXTURE_TICKER, snapshot=snap, memory_store=store
)
fin_direct = build_financial_valuation_panel(
    target=SAMPLE_FIXTURE_TICKER, snapshot=snap, memory_store=store
)
pv_direct = build_price_volume_timing_panel(target=SAMPLE_FIXTURE_TICKER, snapshot=snap)
sw_direct = build_source_workflow_panel(snapshot=snap)
ev_direct = build_evidence_coverage_panel(snapshot=snap, memory_query_result=qres)
vs_direct = build_validation_status_panel(memory_query_result=qres)
check("21.1 direct equity panel deterministic", eq_direct.model_dump() == view.equity_panel.model_dump())
check("21.2 direct financial panel deterministic", fin_direct.model_dump() == view.financial_panel.model_dump())
check("21.3 direct price/volume panel deterministic", pv_direct.model_dump() == view.price_volume_panel.model_dump())
check("21.4 direct source workflow panel deterministic", sw_direct.model_dump() == view.source_workflow_panel.model_dump())
check(
    "21.5 direct evidence coverage panel matches aggregator",
    ev_direct.model_dump() == view.evidence_coverage_panel.model_dump(),
)
check(
    "21.6 direct validation status panel matches aggregator",
    vs_direct.model_dump() == view.validation_status_panel.model_dump(),
)


# ---------------------------------------------------------------------------
# Section 22 — Package-level re-exports through lib/reliability/__init__.py
# ---------------------------------------------------------------------------

import lib.reliability as _r

_PHASE5B_EXPECTED_EXPORTS = (
    "CompanyIdentityView",
    "CompanyResearchHubView",
    "DataSourceTag",
    "EquityResearchPanelView",
    "EvidenceCoveragePanelView",
    "FinancialValuationPanelView",
    "MissingDataPanel",
    "MissingDataWarningView",
    "PriceVolumeTimingPanelView",
    "SourceWorkflowPanelView",
    "ValidationStatusPanelView",
    "build_company_identity_view",
    "build_company_research_hub_view",
    "build_equity_research_panel",
    "build_evidence_coverage_panel",
    "build_financial_valuation_panel",
    "build_price_volume_timing_panel",
    "build_source_workflow_panel",
    "build_validation_status_panel",
)

for name in _PHASE5B_EXPECTED_EXPORTS:
    check(f"22.x lib.reliability re-exports {name}", hasattr(_r, name) and name in _r.__all__)


# ---------------------------------------------------------------------------
# Section 23 — __all__ symmetry between module and re-exports
# ---------------------------------------------------------------------------

check(
    "23.1 module __all__ contains all Phase 5B view symbols",
    set(_PHASE5B_EXPECTED_EXPORTS).issubset(set(_hub_mod.__all__)),
)


# ---------------------------------------------------------------------------
# Section 24 — No filesystem writes anywhere in Phase 5B pipeline
# ---------------------------------------------------------------------------

_before = set(pathlib.Path(_REPO_ROOT, "research").rglob("*")) if (
    pathlib.Path(_REPO_ROOT, "research").exists()
) else set()

# Re-run the full pipeline to confirm no writes
_ = build_company_research_hub_view(
    target=SAMPLE_FIXTURE_TICKER, snapshot=snap, memory_store=store
)
_ = build_company_research_hub_view(target="NOPE", snapshot=None, memory_store=None)

_after = set(pathlib.Path(_REPO_ROOT, "research").rglob("*")) if (
    pathlib.Path(_REPO_ROOT, "research").exists()
) else set()

check("24.1 no new files written under research/", _before == _after)


# ---------------------------------------------------------------------------
# Section 25 — Build with snapshot but no memory_store
# ---------------------------------------------------------------------------

view_no_store = build_company_research_hub_view(
    target=SAMPLE_FIXTURE_TICKER, snapshot=snap, memory_store=None
)
check(
    "25.1 view without store: equity populated (from snapshot)",
    view_no_store.equity_panel.is_populated is True,
)
check(
    "25.2 view without store: research_run_memory_ids empty",
    view_no_store.equity_panel.research_run_memory_ids == [],
)
check(
    "25.3 view without store: evidence_coverage total_memory_record_count == 0",
    view_no_store.evidence_coverage_panel.total_memory_record_count == 0,
)
check(
    "25.4 view without store: validation panel has_any_validation_signal False",
    view_no_store.validation_status_panel.has_any_validation_signal is False,
)
check(
    "25.5 view without store: top-level warnings include 'no memory store or query result'",
    any("memory store" in w.lower() for w in view_no_store.warnings),
)


# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------

print("=" * 70)
print("Phase 5B — Company Research Hub ViewModel Contract — test results")
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
    print("RESULT: FAIL — Phase 5B contract NOT verified.")
    sys.exit(1)
else:
    print("RESULT: PASS — Phase 5B contract verified.")
    sys.exit(0)
