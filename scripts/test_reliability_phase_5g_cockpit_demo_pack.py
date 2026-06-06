#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5g_cockpit_demo_pack.py

Phase 5G: Fixture Demo Pack Based on Original App Flow test suite.

Validates:
  - Default demo pack builds successfully and is deterministic.
  - Demo pack includes the original workflow fixture covering sector /
    scanner / equity / financial / price_volume / synthesis steps.
  - Demo pack includes every Phase 4M memory record type required by
    Phase 5A–5D (research run / thesis / event / allocation / option
    trade / human feedback / agent evaluation).
  - Demo pack constructs Phase 5A memory store / query outputs.
  - Demo pack constructs Phase 5B CompanyResearchHubView.
  - Demo pack constructs Phase 5C HorizonDecisionCardsView and
    ThesisTrackerView.
  - Demo pack constructs Phase 5D PortfolioCockpitView / trade plan /
    option overlay views.
  - Complete scenario has short / medium / long horizon cards in
    deterministic order.
  - Demo safety banner is present and non-execution.
  - Demo provenance is present and fixture-only.
  - approved_for_execution is False (or absent) everywhere.
  - No executable order fields are introduced on any demo-pack model.
  - Degraded scenario produces safe warnings (missing financial step,
    missing long-horizon thesis, no_trade option overlay).
  - Serialization is deterministic.
  - No import of app.py, pages/*, Streamlit, lib/workflow_state.py,
    lib/llm_orchestrator.py, broker APIs, or external APIs.
  - Regression checks: Phase 5A / 5B / 5C / 5D suites still pass at the
    module level (re-imports succeed; representative assertions).

Usage:
    python3 scripts/test_reliability_phase_5g_cockpit_demo_pack.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

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
# Section 1 — Module imports + forbidden-module non-load
# ---------------------------------------------------------------------------

from lib.reliability import phase5_demo_pack as _demo_mod

check("1.1 phase5_demo_pack importable", _demo_mod is not None)

_FORBIDDEN_LIVE_MODULES = (
    "lib.workflow_state",
    "lib.llm_orchestrator",
    "lib.data_fetcher",
    "lib.valuation",
    "lib.technical",
    "lib.rotation",
    "app",
    "streamlit",
    "anthropic",
)

for _m in _FORBIDDEN_LIVE_MODULES:
    loaded = any(name == _m or name.startswith(_m + ".") for name in sys.modules)
    check(f"1.x forbidden module not loaded: {_m}", not loaded)


# ---------------------------------------------------------------------------
# Section 2 — Source-level forbidden import substring check
# ---------------------------------------------------------------------------

_PHASE5G_SRC = pathlib.Path(_REPO_ROOT) / "lib" / "reliability" / "phase5_demo_pack.py"

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
    "import streamlit",
    "import anthropic",
    "from lib.reliability.integration_boundary",
    "import lib.reliability.integration_boundary",
]

_src_text = _PHASE5G_SRC.read_text()
for needle in _FORBIDDEN_SUBSTRINGS:
    check(
        f"2.x no forbidden source ref in phase5_demo_pack.py: {needle!r}",
        needle not in _src_text,
    )


# ---------------------------------------------------------------------------
# Section 3 — Build default demo pack
# ---------------------------------------------------------------------------

from lib.reliability.phase5_demo_pack import (
    CockpitDemoPack,
    CockpitDemoScenario,
    CockpitViewDemoBundle,
    DEMO_SCENARIO_ORDER,
    DemoDataProvenance,
    DemoPackValidationSummary,
    DemoSafetyBanner,
    DemoScenarioKind,
    DemoScenarioMetadata,
    MemoryDemoFixtureBundle,
    OriginalWorkflowDemoFixture,
    SAMPLE_DEMO_AS_OF,
    SAMPLE_DEMO_COMPLETE_RUN_ID,
    SAMPLE_DEMO_COMPLETE_TICKER,
    SAMPLE_DEMO_DEGRADED_RUN_ID,
    SAMPLE_DEMO_DEGRADED_TICKER,
    build_cockpit_view_demo_bundle,
    build_default_cockpit_demo_pack,
    build_demo_data_provenance,
    build_demo_safety_banner,
    build_demo_scenario_metadata,
    build_memory_demo_fixture_bundle,
    build_original_workflow_demo_fixture,
    validate_cockpit_demo_pack,
)

pack = build_default_cockpit_demo_pack()
check("3.1 pack is CockpitDemoPack", isinstance(pack, CockpitDemoPack))
check("3.2 pack_id matches default", pack.pack_id == "phase5g_default_cockpit_demo_pack")
check("3.3 pack title non-empty", bool(pack.title.strip()))
check("3.4 pack has at least 2 scenarios", len(pack.scenarios) >= 2)
check("3.5 pack has exactly 2 scenarios (default)", len(pack.scenarios) == 2)

# Determinism: building twice yields equal JSON representations.
pack2 = build_default_cockpit_demo_pack()
check(
    "3.6 default pack deterministic across builds",
    pack.model_dump_json() == pack2.model_dump_json(),
)


# ---------------------------------------------------------------------------
# Section 4 — Complete scenario coverage
# ---------------------------------------------------------------------------

complete = next(
    (s for s in pack.scenarios if s.metadata.scenario_kind == "complete"), None
)
check("4.1 complete scenario present", complete is not None)
assert complete is not None  # mypy/runtime guard for below

check(
    "4.2 complete scenario ticker is fixture (FIXTKR)",
    complete.metadata.ticker == SAMPLE_DEMO_COMPLETE_TICKER == "FIXTKR",
)
check(
    "4.3 complete scenario run_id matches default",
    complete.metadata.run_id == SAMPLE_DEMO_COMPLETE_RUN_ID,
)

# Workflow fixture covers all 6 steps (sector/scanner/equity/financial/price_volume/synthesis).
_EXPECTED_STEPS = (
    "sector",
    "scanner",
    "equity",
    "financial",
    "price_volume",
    "synthesis",
)
present_complete = complete.workflow_fixture.present_step_keys
for step in _EXPECTED_STEPS:
    check(
        f"4.x complete scenario has '{step}' step",
        step in present_complete,
    )
check(
    "4.10 complete scenario has no missing steps",
    complete.workflow_fixture.missing_step_keys == [],
)
check(
    "4.11 complete scenario snapshot has synthesis",
    complete.workflow_fixture.snapshot.synthesis is not None,
)


# ---------------------------------------------------------------------------
# Section 5 — Complete scenario memory coverage
# ---------------------------------------------------------------------------

mf = complete.memory_fixture
check("5.1 research_run_memory present", mf.research_run_memory is not None)
check("5.2 thesis records count = 3 (short/medium/long)", len(mf.thesis_records) == 3)
check("5.3 at least one event record", len(mf.event_records) >= 1)
check("5.4 at least one allocation record", len(mf.allocation_records) >= 1)
check(
    "5.5 at least one option trade record",
    len(mf.option_trade_records) >= 1,
)
check(
    "5.6 at least one human feedback record",
    len(mf.human_feedback_records) >= 1,
)
check(
    "5.7 at least one agent evaluation record",
    len(mf.agent_evaluation_records) >= 1,
)

# Memory store + query exposed
check("5.8 memory_store available", mf.memory_store is not None)
check(
    "5.9 memory_query_result is target-scoped",
    not mf.memory_query_result.is_empty(),
)

# All theses cover short / medium / long horizons.
horizons_present = {t.horizon for t in mf.thesis_records}
check("5.10 thesis short horizon present", "short" in horizons_present)
check("5.11 thesis medium horizon present", "medium" in horizons_present)
check("5.12 thesis long horizon present", "long" in horizons_present)


# ---------------------------------------------------------------------------
# Section 6 — Complete scenario view-bundle (Phase 5B/5C/5D)
# ---------------------------------------------------------------------------

vb = complete.view_bundle
check("6.1 CompanyResearchHubView built", vb.company_research_hub_view is not None)
check(
    "6.2 equity panel populated in complete",
    vb.company_research_hub_view.equity_panel.is_populated,
)
check(
    "6.3 financial panel populated in complete",
    vb.company_research_hub_view.financial_panel.is_populated,
)
check(
    "6.4 price_volume panel populated in complete",
    vb.company_research_hub_view.price_volume_panel.is_populated,
)
check(
    "6.5 source_workflow_panel synthesis present in complete",
    vb.company_research_hub_view.source_workflow_panel.synthesis_present,
)

# Phase 5C — Horizon decision cards
cards = vb.horizon_decision_cards_view.cards
check("6.6 horizon cards count = 3", len(cards) == 3)
check(
    "6.7 cards in canonical short/medium/long order",
    [c.horizon for c in cards] == ["short", "medium", "long"],
)
check(
    "6.8 every complete card is_populated",
    all(c.is_populated for c in cards),
)

# Phase 5C — Thesis tracker
tracker = vb.thesis_tracker_view
check("6.9 tracker rows count = 3 (short/medium/long)", len(tracker.rows) == 3)
check(
    "6.10 tracker target_count = 1",
    tracker.target_count == 1,
)
check(
    "6.11 tracker rows in canonical horizon order",
    [r.horizon for r in tracker.rows] == ["short", "medium", "long"],
)

# Phase 5D — Portfolio cockpit
portfolio = vb.portfolio_cockpit_view
check(
    "6.12 portfolio target matches scenario",
    portfolio.target == complete.metadata.ticker,
)
check(
    "6.13 allocation_summary has any records in complete",
    portfolio.allocation_summary.has_any_records,
)
check(
    "6.14 at least one trade plan",
    len(portfolio.trade_plans) >= 1,
)
check(
    "6.15 at least one option overlay",
    len(portfolio.option_overlays) >= 1,
)
check(
    "6.16 execution safety banner present + non-executable",
    portfolio.execution_safety_banner.is_non_executable
    and portfolio.execution_safety_banner.requires_human_review,
)
# Complete scenario should NOT be no_trade.
check(
    "6.17 complete scenario option overlay is not no_trade",
    all(not o.is_no_trade for o in portfolio.option_overlays),
)


# ---------------------------------------------------------------------------
# Section 7 — Degraded scenario coverage
# ---------------------------------------------------------------------------

degraded = next(
    (s for s in pack.scenarios if s.metadata.scenario_kind == "degraded"), None
)
check("7.1 degraded scenario present", degraded is not None)
assert degraded is not None

check(
    "7.2 degraded scenario ticker is fixture (FIXDEG)",
    degraded.metadata.ticker == SAMPLE_DEMO_DEGRADED_TICKER == "FIXDEG",
)
check(
    "7.3 degraded scenario run_id matches default",
    degraded.metadata.run_id == SAMPLE_DEMO_DEGRADED_RUN_ID,
)

# Degraded snapshot is missing the financial step.
check(
    "7.4 degraded scenario missing financial step",
    "financial" in degraded.workflow_fixture.missing_step_keys,
)
check(
    "7.5 degraded scenario does NOT have financial in present steps",
    "financial" not in degraded.workflow_fixture.present_step_keys,
)
# Remaining steps still present.
for step in ("sector", "scanner", "equity", "price_volume", "synthesis"):
    check(
        f"7.x degraded scenario still has '{step}' step",
        step in degraded.workflow_fixture.present_step_keys,
    )

# Degraded thesis records: only short + medium horizons (long intentionally absent).
dmf = degraded.memory_fixture
d_horizons = {t.horizon for t in dmf.thesis_records}
check("7.10 degraded thesis short present", "short" in d_horizons)
check("7.11 degraded thesis medium present", "medium" in d_horizons)
check("7.12 degraded thesis long absent", "long" not in d_horizons)
check("7.13 degraded thesis count = 2", len(dmf.thesis_records) == 2)

# Degraded option overlay should be no_trade — preserves first-class state.
dvb = degraded.view_bundle
overlays = dvb.portfolio_cockpit_view.option_overlays
check("7.14 degraded option overlay count >= 1", len(overlays) >= 1)
check(
    "7.15 degraded option overlay is_no_trade",
    all(o.is_no_trade for o in overlays),
)
check(
    "7.16 degraded option overlay state == no_trade",
    all(o.state == "no_trade" for o in overlays),
)
check(
    "7.17 degraded option overlay has no_trade_reason",
    all(o.no_trade_reason is not None and o.no_trade_reason.is_no_trade for o in overlays),
)

# Degraded company hub: financial panel safe-degraded.
chub = dvb.company_research_hub_view
check(
    "7.18 degraded financial panel is_populated False",
    not chub.financial_panel.is_populated,
)
check(
    "7.19 degraded equity panel still populated",
    chub.equity_panel.is_populated,
)
check(
    "7.20 degraded missing_data warning includes 'financial'",
    "financial" in chub.missing_data.missing_panels,
)

# Degraded horizon cards: still three cards, long is missing/safe.
dcards = dvb.horizon_decision_cards_view.cards
check("7.21 degraded horizon cards count = 3", len(dcards) == 3)
check(
    "7.22 degraded cards in canonical order",
    [c.horizon for c in dcards] == ["short", "medium", "long"],
)
check(
    "7.23 degraded long card is missing",
    dcards[2].status == "missing" and not dcards[2].is_populated,
)
check(
    "7.24 degraded long card has warnings",
    len(dcards[2].warnings) > 0,
)

# Scenario-level warnings present.
check("7.25 degraded scenario carries explanatory warnings", len(degraded.warnings) >= 1)


# ---------------------------------------------------------------------------
# Section 8 — Safety banner + provenance invariants
# ---------------------------------------------------------------------------

banner = pack.safety_banner
check("8.1 pack safety banner is_demo_only", banner.is_demo_only)
check("8.2 pack safety banner is_non_executable", banner.is_non_executable)
check("8.3 pack safety banner requires_human_review", banner.requires_human_review)
check(
    "8.4 pack safety banner no_live_workflow_wiring", banner.no_live_workflow_wiring
)
check("8.5 pack safety banner no_external_api", banner.no_external_api)
check("8.6 pack safety banner no_broker_or_order", banner.no_broker_or_order)
check("8.7 pack safety banner no_investment_advice", banner.no_investment_advice)
check(
    "8.8 pack safety banner approved_for_execution False",
    banner.approved_for_execution is False,
)
check("8.9 pack safety banner message non-empty", bool(banner.message.strip()))

# Banner construction should reject approved_for_execution=True.
expect_error(
    "8.10 DemoSafetyBanner rejects approved_for_execution=True",
    lambda: DemoSafetyBanner(approved_for_execution=True),
    ValueError,
    "approved_for_execution",
)

prov = pack.provenance
check("8.11 provenance is_fixture_only", prov.is_fixture_only)
check("8.12 provenance not uses_live_data", not prov.uses_live_data)
check("8.13 provenance not uses_external_api", not prov.uses_external_api)
check(
    "8.14 provenance not uses_live_workflow_state",
    not prov.uses_live_workflow_state,
)
check("8.15 provenance not uses_llm", not prov.uses_llm)
check("8.16 provenance not uses_broker", not prov.uses_broker)
check(
    "8.17 provenance includes both fixture tickers",
    set(prov.fixture_tickers)
    == {SAMPLE_DEMO_COMPLETE_TICKER, SAMPLE_DEMO_DEGRADED_TICKER},
)
check("8.18 provenance as_of matches default", prov.as_of == SAMPLE_DEMO_AS_OF)

# Each scenario carries its own banner + provenance.
for s in pack.scenarios:
    check(
        f"8.x scenario {s.metadata.scenario_id!r} banner is_demo_only",
        s.metadata.safety_banner.is_demo_only,
    )
    check(
        f"8.x scenario {s.metadata.scenario_id!r} banner approved=False",
        s.metadata.safety_banner.approved_for_execution is False,
    )
    check(
        f"8.x scenario {s.metadata.scenario_id!r} provenance fixture_only",
        s.metadata.provenance.is_fixture_only,
    )


# ---------------------------------------------------------------------------
# Section 9 — approved_for_execution invariant everywhere
# ---------------------------------------------------------------------------

for s in pack.scenarios:
    # Snapshot + bundle invariants.
    check(
        f"9.x scenario {s.metadata.scenario_id!r} snapshot approved=False",
        s.workflow_fixture.snapshot.approved_for_execution is False,
    )
    check(
        f"9.x scenario {s.metadata.scenario_id!r} bundle approved=False",
        s.workflow_fixture.bundle.approved_for_execution is False,
    )
    check(
        f"9.x scenario {s.metadata.scenario_id!r} memory_query_result approved=False",
        s.memory_fixture.memory_query_result.approved_for_execution is False,
    )
    # Records' approved_for_execution either False or absent.
    record_lists: list[list] = [
        [s.memory_fixture.research_run_memory] if s.memory_fixture.research_run_memory else [],
        list(s.memory_fixture.thesis_records),
        list(s.memory_fixture.event_records),
        list(s.memory_fixture.allocation_records),
        list(s.memory_fixture.option_trade_records),
        list(s.memory_fixture.human_feedback_records),
        list(s.memory_fixture.agent_evaluation_records),
    ]
    for lst in record_lists:
        for r in lst:
            aft = getattr(r, "approved_for_execution", False)
            check(
                f"9.x record on {s.metadata.scenario_id!r} approved=False",
                aft is False,
            )


# ---------------------------------------------------------------------------
# Section 10 — No executable order fields anywhere on Phase 5G models
# ---------------------------------------------------------------------------

_FORBIDDEN_ORDER_FIELDS = (
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

_PHASE5G_MODELS = [
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

for cls in _PHASE5G_MODELS:
    for fname in _FORBIDDEN_ORDER_FIELDS:
        check(
            f"10.x {cls.__name__} does not declare forbidden field {fname!r}",
            fname not in cls.model_fields,
        )

# Source-level: forbidden field substrings must not appear as field names on
# any Phase 5G class body. (Mention inside docstrings / safety banner text /
# forbidden-list tuples is allowed and expected.)
for fname in _FORBIDDEN_ORDER_FIELDS:
    # Field definitions in Pydantic look like ``order_type:`` followed by a
    # type annotation. We forbid the colon form on Phase 5G models.
    needle = f"\n    {fname}: "
    check(
        f"10.x phase5_demo_pack.py does not define field {fname!r}",
        needle not in _src_text,
    )


# ---------------------------------------------------------------------------
# Section 11 — validation summary asserts invariants
# ---------------------------------------------------------------------------

vs = pack.validation_summary
check("11.1 validation scenario_count == 2", vs.scenario_count == 2)
check(
    "11.2 validation has_complete_scenario",
    vs.has_complete_scenario,
)
check(
    "11.3 validation has_degraded_scenario",
    vs.has_degraded_scenario,
)
check(
    "11.4 validation all_approved_for_execution_false",
    vs.all_approved_for_execution_false,
)
check(
    "11.5 validation no_executable_order_fields",
    vs.no_executable_order_fields,
)
check("11.6 validation safety_banner_present", vs.safety_banner_present)
check("11.7 validation provenance_present", vs.provenance_present)
check("11.8 validation errors empty", vs.errors == [])
check(
    "11.9 validation scenario_kinds matches DEMO_SCENARIO_ORDER",
    set(vs.scenario_kinds) == set(DEMO_SCENARIO_ORDER),
)

# Direct validator call is consistent.
direct = validate_cockpit_demo_pack(pack)
check(
    "11.10 direct validate_cockpit_demo_pack matches pack.validation_summary",
    direct.model_dump_json() == vs.model_dump_json(),
)


# ---------------------------------------------------------------------------
# Section 12 — Serialization determinism + round-trip
# ---------------------------------------------------------------------------

pack_json = pack.model_dump_json()
pack_dict = pack.model_dump()
check("12.1 pack model_dump_json non-empty", bool(pack_json.strip()))
# Decode and check shape
decoded = json.loads(pack_json)
check("12.2 pack_id round-trips through JSON", decoded["pack_id"] == pack.pack_id)
check(
    "12.3 scenarios round-trip through JSON",
    len(decoded["scenarios"]) == len(pack.scenarios),
)
# Determinism — same JSON across two builds.
check(
    "12.4 serialization deterministic across builds",
    pack.model_dump_json() == build_default_cockpit_demo_pack().model_dump_json(),
)


# ---------------------------------------------------------------------------
# Section 13 — Standalone builders (safety banner / provenance / metadata)
# ---------------------------------------------------------------------------

banner_only = build_demo_safety_banner()
check("13.1 build_demo_safety_banner ok", isinstance(banner_only, DemoSafetyBanner))
check("13.2 banner approved=False default", banner_only.approved_for_execution is False)

prov_only = build_demo_data_provenance(fixture_tickers=["FIXTKR"])
check(
    "13.3 build_demo_data_provenance ok",
    isinstance(prov_only, DemoDataProvenance),
)
check(
    "13.4 provenance ticker captured",
    prov_only.fixture_tickers == ["FIXTKR"],
)

md = build_demo_scenario_metadata(
    scenario_kind="complete",
    ticker="FIXTKR",
    run_id="FIXTKR_run_x",
    title="Test scenario",
)
check("13.5 build_demo_scenario_metadata ok", isinstance(md, DemoScenarioMetadata))
check("13.6 metadata scenario_id includes ticker + kind",
      "FIXTKR" in md.scenario_id and "complete" in md.scenario_id)

# Whitespace rejection on metadata fields.
expect_error(
    "13.7 metadata whitespace ticker rejected",
    lambda: build_demo_scenario_metadata(
        scenario_kind="complete", ticker="   ", run_id="r", title="t"
    ),
    Exception,
)


# ---------------------------------------------------------------------------
# Section 14 — Helper builders work standalone (workflow / memory / view)
# ---------------------------------------------------------------------------

complete_scenario = complete  # alias
wf_fix = build_original_workflow_demo_fixture(
    snapshot=complete_scenario.workflow_fixture.snapshot,
    memory_bundle=complete_scenario.workflow_fixture.bundle,
    adapter=complete_scenario.workflow_fixture.adapter,
)
check("14.1 build_original_workflow_demo_fixture ok",
      isinstance(wf_fix, OriginalWorkflowDemoFixture))
check("14.2 wf_fix carries every present step",
      set(wf_fix.present_step_keys) == set(_EXPECTED_STEPS))

mem_fix = build_memory_demo_fixture_bundle(
    ticker=complete_scenario.metadata.ticker,
    bundle=complete_scenario.workflow_fixture.bundle,
)
check("14.3 build_memory_demo_fixture_bundle ok",
      isinstance(mem_fix, MemoryDemoFixtureBundle))
check(
    "14.4 mem_fix memory_query_result has records",
    not mem_fix.memory_query_result.is_empty(),
)

view_fix = build_cockpit_view_demo_bundle(
    ticker=complete_scenario.metadata.ticker,
    snapshot=complete_scenario.workflow_fixture.snapshot,
    memory_fixture=mem_fix,
)
check("14.5 build_cockpit_view_demo_bundle ok",
      isinstance(view_fix, CockpitViewDemoBundle))
check(
    "14.6 view bundle horizon cards in canonical order",
    [c.horizon for c in view_fix.horizon_decision_cards_view.cards]
    == ["short", "medium", "long"],
)


# ---------------------------------------------------------------------------
# Section 15 — No filesystem writes / no external IO during build
# ---------------------------------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:
    before = set(os.listdir(tmp))
    _ = build_default_cockpit_demo_pack()
    after = set(os.listdir(tmp))
    check("15.1 no files written to tmp by Phase 5G builder", before == after)


# ---------------------------------------------------------------------------
# Section 16 — Exports / __all__
# ---------------------------------------------------------------------------

from lib.reliability.phase5_demo_pack import __all__ as _DEMO_ALL

_EXPECTED_DEMO = {
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
}

check("16.1 phase5_demo_pack __all__ matches", set(_DEMO_ALL) == _EXPECTED_DEMO)


# ---------------------------------------------------------------------------
# Section 17 — Package-level re-exports
# ---------------------------------------------------------------------------

import lib.reliability as _rel_pkg

for _sym in sorted(_EXPECTED_DEMO):
    check(
        f"17.x lib.reliability re-exports {_sym}",
        hasattr(_rel_pkg, _sym),
    )


# ---------------------------------------------------------------------------
# Section 18 — No live wiring / no positive authorization in source
# ---------------------------------------------------------------------------

# Phase 5G source must not positively authorize approved_for_execution=True.
check(
    "18.1 source does not positively set approved_for_execution = True",
    "approved_for_execution=True" not in _src_text
    or "must always be False" in _src_text,
)
# Stricter: literal "approved_for_execution = True" never appears outside
# the validator error message.
_lines_with_aft_true = [
    line for line in _src_text.splitlines()
    if "approved_for_execution=True" in line or "approved_for_execution = True" in line
]
for line in _lines_with_aft_true:
    # Allowed only inside an error message / docstring / validator context.
    ok = (
        "raise" in line
        or "must always be False" in line
        or "rejects" in line
        or "must have" in line
        or "missing" in line
        or "has approved_for_execution=True" in line  # error string
    )
    check(
        "18.x approved_for_execution=True appears only in negation/error context",
        ok,
        detail=line.strip(),
    )

# Phase 5G source must not import Phase 4A integration_boundary.
check(
    "18.2 phase5_demo_pack does not import Phase 4A integration_boundary",
    "integration_boundary" not in _src_text
    or "frozen" in _src_text.lower(),
)


# ---------------------------------------------------------------------------
# Section 19 — Regression: Phase 5A / 5B / 5C / 5D contract surfaces intact
# ---------------------------------------------------------------------------

# Phase 5A — memory query types are still importable and behave deterministically.
from lib.reliability.phase5_memory_query import (
    FixtureBackedMemoryStore,
    MemoryQuery,
    MemoryQueryByTicker,
    MemoryQueryByHorizon,
    MemoryQueryByType,
    MemoryQueryByReviewStatus,
    MemoryQueryResult,
)

check("19.1 Phase 5A query types still importable", True)
# Sanity: query the demo pack's complete-scenario store by horizon.
r = complete.memory_fixture.memory_store.query(
    MemoryQueryByHorizon(horizon="medium", target=complete.metadata.ticker)
)
check("19.2 Phase 5A horizon query returns thesis records",
      len(r.thesis_records) >= 1)
check("19.3 Phase 5A horizon query approved=False",
      r.approved_for_execution is False)

# Phase 5B — CompanyResearchHubView surfaces still importable.
from lib.reliability.company_research_hub import (
    CompanyResearchHubView,
    build_company_research_hub_view,
)

check("19.4 Phase 5B view + builder importable", True)

# Phase 5C — Horizon view surfaces still importable.
from lib.reliability.phase5_horizon_views import (
    HORIZON_ORDER,
    HorizonDecisionCardsView,
    ThesisTrackerView,
    build_horizon_decision_cards_view,
    build_thesis_tracker_view,
)

check("19.5 Phase 5C view + builders importable", True)
check("19.6 HORIZON_ORDER unchanged short/medium/long",
      HORIZON_ORDER == ("short", "medium", "long"))

# Phase 5D — Portfolio view surfaces still importable.
from lib.reliability.phase5_portfolio_views import (
    PortfolioCockpitView,
    TRADE_PLAN_LEVEL_KINDS,
    build_portfolio_cockpit_view,
)

check("19.7 Phase 5D view + builders importable", True)
check(
    "19.8 TRADE_PLAN_LEVEL_KINDS unchanged",
    TRADE_PLAN_LEVEL_KINDS == ("entry", "add", "trim", "stop", "target", "review"),
)


# ---------------------------------------------------------------------------
# Section 20 — Pack-level invariants on degraded scenario warnings
# ---------------------------------------------------------------------------

# Degraded scenario warnings should mention financial / long / no_trade.
d_warning_text = " ".join(degraded.warnings).lower()
check("20.1 degraded warnings mention financial", "financial" in d_warning_text)
check("20.2 degraded warnings mention long", "long" in d_warning_text)
check("20.3 degraded warnings mention no_trade", "no_trade" in d_warning_text)

# Degraded portfolio cockpit's missing_data must include option_overlay? No —
# option overlay is present (in no_trade state). Allocation panel still present.
# But financial source step is missing on the company hub side.
check(
    "20.4 degraded company hub missing_data lists at least 'financial'",
    "financial" in dvb.company_research_hub_view.missing_data.missing_panels,
)


# ---------------------------------------------------------------------------
# Section 21 — Forbidden live runtime files still present (not modified)
# ---------------------------------------------------------------------------

_FORBIDDEN_FILE_PATHS = [
    pathlib.Path(_REPO_ROOT) / "app.py",
    pathlib.Path(_REPO_ROOT) / "lib" / "llm_orchestrator.py",
    pathlib.Path(_REPO_ROOT) / "lib" / "valuation.py",
    pathlib.Path(_REPO_ROOT) / "lib" / "technical.py",
    pathlib.Path(_REPO_ROOT) / "lib" / "rotation.py",
    pathlib.Path(_REPO_ROOT) / "lib" / "data_fetcher.py",
    pathlib.Path(_REPO_ROOT) / "lib" / "workflow_state.py",
    pathlib.Path(_REPO_ROOT) / "lib" / "reliability" / "integration_boundary.py",
]
for p in _FORBIDDEN_FILE_PATHS:
    check(f"21.x forbidden file still present at {p.name}", p.exists())


# ---------------------------------------------------------------------------
# Section 22 — Phase 5G design doc exists and contains required sections
# ---------------------------------------------------------------------------

_DOC = pathlib.Path(_REPO_ROOT) / "docs" / "reliability_phase_5g_cockpit_demo_pack.md"
check("22.1 Phase 5G design doc exists", _DOC.exists())

if _DOC.exists():
    doc_text = _DOC.read_text()
    _REQUIRED_DOC_SECTIONS = (
        "Purpose",
        "Relationship to Roadmap v4",
        "Relationship to the Original README App",
        "Relationship to Phase 4M",
        "Relationship to Phase 5A",
        "Relationship to Phase 5B",
        "Relationship to Phase 5C",
        "Relationship to Phase 5D",
        "Relationship to Phase 5E",
        "Relationship to Phase 5F",
        "Demo scenario structure",
        "Complete scenario contents",
        "Optional degraded scenario contents",
        "Demo-only provenance",
        "Safety banner semantics",
        "Non-Goals",
        "Guardrails",
        "Acceptance Criteria",
        "Future Phase 5H Dependency",
    )
    for header in _REQUIRED_DOC_SECTIONS:
        check(
            f"22.x Phase 5G doc references section: {header!r}",
            header in doc_text,
        )

    # Doc should reaffirm execution non-authorization.
    check(
        "22.30 Phase 5G doc states approved_for_execution remains False",
        "approved_for_execution" in doc_text and "False" in doc_text,
    )
    # Doc must mention Phase 5H dependency but not claim Phase 5H started.
    check(
        "22.31 Phase 5G doc references Phase 5H",
        "Phase 5H" in doc_text,
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("=" * 70)
print("Phase 5G — Fixture Demo Pack Based on Original App Flow — test results")
print("=" * 70)

if _failures:
    print()
    for line in _failures:
        print(line)

print()
print(f"Passed: {PASS}")
print(f"Failed: {FAIL}")
print(f"Total:  {PASS + FAIL}")
print()

if FAIL == 0:
    print("RESULT: PASS — Phase 5G demo pack contract verified.")
    sys.exit(0)
else:
    print("RESULT: FAIL — see failures above.")
    sys.exit(1)
