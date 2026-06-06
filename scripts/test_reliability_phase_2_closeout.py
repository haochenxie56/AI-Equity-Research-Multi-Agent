#!/usr/bin/env python3
"""
scripts/test_reliability_phase_2_closeout.py

Phase 2 Closeout smoke/contract test.

Verifies that all Phase 0-2 reliability modules are importable and that key
objects/functions exist. Does NOT call live APIs, external data sources, or
the Streamlit app.

Usage:
    python3 scripts/test_reliability_phase_2_closeout.py
"""

from __future__ import annotations

import os
import sys

# Add repo root to sys.path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

PASS = 0
FAIL = 0
_results: list[tuple[str, bool, str]] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
    _results.append((label, condition, detail))


# ---------------------------------------------------------------------------
# 1. Core schemas (Phase 0)
# ---------------------------------------------------------------------------

from lib.reliability.schemas import (
    AgentConfidence,
    AgentResult,
    Assumption,
    DataSnapshot,
    EvidenceRef,
    Finding,
    Risk,
    ToolResult,
    ValidationIssue,
    ValidationReport,
)

check("schemas: ToolResult", callable(ToolResult))
check("schemas: AgentResult", callable(AgentResult))
check("schemas: EvidenceRef", callable(EvidenceRef))
check("schemas: Finding", callable(Finding))
check("schemas: Assumption", callable(Assumption))
check("schemas: Risk", callable(Risk))
check("schemas: DataSnapshot", callable(DataSnapshot))
check("schemas: ValidationIssue", callable(ValidationIssue))
check("schemas: ValidationReport", callable(ValidationReport))
check("schemas: AgentConfidence", callable(AgentConfidence))

# ---------------------------------------------------------------------------
# 2. Validators (Phase 0)
# ---------------------------------------------------------------------------

from lib.reliability.validators import validate_agent_result

check("validators: validate_agent_result", callable(validate_agent_result))

# ---------------------------------------------------------------------------
# 3. RunContext and EvidenceStore (Phase 0)
# ---------------------------------------------------------------------------

from lib.reliability.run_context import RunContext, create_run_context
from lib.reliability.evidence_store import EvidenceStore

check("run_context: RunContext", callable(RunContext))
check("run_context: create_run_context", callable(create_run_context))
check("evidence_store: EvidenceStore", callable(EvidenceStore))

# ---------------------------------------------------------------------------
# 4. Config (Phase 2A)
# ---------------------------------------------------------------------------

from lib.reliability.config import (
    parse_bool,
    load_reliability_flags_from_mapping,
    load_reliability_flags_from_env,
    reliability_flags_to_env_dict,
    describe_reliability_config,
)

check("config: parse_bool", callable(parse_bool))
check("config: load_reliability_flags_from_mapping", callable(load_reliability_flags_from_mapping))
check("config: load_reliability_flags_from_env", callable(load_reliability_flags_from_env))
check("config: reliability_flags_to_env_dict", callable(reliability_flags_to_env_dict))
check("config: describe_reliability_config", callable(describe_reliability_config))

# Sanity check parse_bool
check("config: parse_bool('true') == True", parse_bool("true") is True)
check("config: parse_bool('0') == False", parse_bool("0") is False)

# ---------------------------------------------------------------------------
# 5. Horizon schema (Phase 2B)
# ---------------------------------------------------------------------------

from lib.reliability.horizon import (
    InvestmentHorizon,
    HorizonDecisionSet,
    HorizonThesis,
    default_horizon_evidence_requirements,
    summarize_horizon_coverage,
    validate_horizon_decision_set,
)

check("horizon: InvestmentHorizon", callable(InvestmentHorizon))
check("horizon: HorizonDecisionSet", callable(HorizonDecisionSet))
check("horizon: default_horizon_evidence_requirements", callable(default_horizon_evidence_requirements))
check("horizon: summarize_horizon_coverage", callable(summarize_horizon_coverage))
check("horizon: validate_horizon_decision_set", callable(validate_horizon_decision_set))

# ---------------------------------------------------------------------------
# 6. Macro schema (Phase 2C)
# ---------------------------------------------------------------------------

from lib.reliability.macro import (
    MacroSnapshot,
    MacroIndicator,
    MacroRegimeAssessment,
    macro_snapshot_from_indicators,
    macro_tool_result_from_snapshot,
    validate_macro_snapshot,
)

check("macro: MacroSnapshot", callable(MacroSnapshot))
check("macro: MacroIndicator", callable(MacroIndicator))
check("macro: MacroRegimeAssessment", callable(MacroRegimeAssessment))
check("macro: macro_snapshot_from_indicators", callable(macro_snapshot_from_indicators))
check("macro: macro_tool_result_from_snapshot", callable(macro_tool_result_from_snapshot))
check("macro: validate_macro_snapshot", callable(validate_macro_snapshot))

# ---------------------------------------------------------------------------
# 7. Allocation schema (Phase 2D)
# ---------------------------------------------------------------------------

from lib.reliability.allocation import (
    AllocationDecisionSet,
    PositionSizingResult,
    PortfolioSnapshot,
    calculate_position_sizing,
    allocation_tool_result_from_decision_set,
    validate_allocation_decision_set,
)

check("allocation: AllocationDecisionSet", callable(AllocationDecisionSet))
check("allocation: PositionSizingResult", callable(PositionSizingResult))
check("allocation: PortfolioSnapshot", callable(PortfolioSnapshot))
check("allocation: calculate_position_sizing", callable(calculate_position_sizing))
check("allocation: allocation_tool_result_from_decision_set", callable(allocation_tool_result_from_decision_set))
check("allocation: validate_allocation_decision_set", callable(validate_allocation_decision_set))

# ---------------------------------------------------------------------------
# 8. Options schema (Phase 2E)
# ---------------------------------------------------------------------------

from lib.reliability.options import (
    OptionStrategyDecisionSet,
    OptionPayoffResult,
    OptionContractSnapshot,
    calculate_long_call_payoff,
    option_strategy_tool_result_from_decision_set,
    validate_option_strategy_decision_set,
)

check("options: OptionStrategyDecisionSet", callable(OptionStrategyDecisionSet))
check("options: OptionPayoffResult", callable(OptionPayoffResult))
check("options: OptionContractSnapshot", callable(OptionContractSnapshot))
check("options: calculate_long_call_payoff", callable(calculate_long_call_payoff))
check("options: option_strategy_tool_result_from_decision_set", callable(option_strategy_tool_result_from_decision_set))
check("options: validate_option_strategy_decision_set", callable(validate_option_strategy_decision_set))

# ---------------------------------------------------------------------------
# 9. News schema (Phase 2F)
# ---------------------------------------------------------------------------

from lib.reliability.news import (
    NewsSnapshot,
    NewsEvent,
    NewsCoverageSummary,
    news_snapshot_from_events,
    news_tool_result_from_snapshot,
    validate_news_snapshot,
)

check("news: NewsSnapshot", callable(NewsSnapshot))
check("news: NewsEvent", callable(NewsEvent))
check("news: NewsCoverageSummary", callable(NewsCoverageSummary))
check("news: news_snapshot_from_events", callable(news_snapshot_from_events))
check("news: news_tool_result_from_snapshot", callable(news_tool_result_from_snapshot))
check("news: validate_news_snapshot", callable(validate_news_snapshot))

# ---------------------------------------------------------------------------
# 10. Catalyst / Earnings / Estimate Revision schema (Phase 2G)
# ---------------------------------------------------------------------------

from lib.reliability.catalysts import (
    CatalystSnapshot,
    CatalystEvent,
    EarningsEvent,
    EstimateRevision,
    CatalystCoverageSummary,
    catalyst_snapshot_from_components,
    catalyst_tool_result_from_snapshot,
    validate_catalyst_snapshot,
)

check("catalysts: CatalystSnapshot", callable(CatalystSnapshot))
check("catalysts: CatalystEvent", callable(CatalystEvent))
check("catalysts: EarningsEvent", callable(EarningsEvent))
check("catalysts: EstimateRevision", callable(EstimateRevision))
check("catalysts: CatalystCoverageSummary", callable(CatalystCoverageSummary))
check("catalysts: catalyst_snapshot_from_components", callable(catalyst_snapshot_from_components))
check("catalysts: catalyst_tool_result_from_snapshot", callable(catalyst_tool_result_from_snapshot))
check("catalysts: validate_catalyst_snapshot", callable(validate_catalyst_snapshot))

# ---------------------------------------------------------------------------
# 11. Validation Aggregator (Phase 2H)
# ---------------------------------------------------------------------------

from lib.reliability.validation_aggregator import (
    ValidationAggregate,
    AggregatedValidationItem,
    aggregate_validation_items,
    merge_validation_aggregates,
    collect_phase2_validation_warnings,
    validation_aggregate_tool_result_from_aggregate,
)

check("validation_aggregator: ValidationAggregate", callable(ValidationAggregate))
check("validation_aggregator: AggregatedValidationItem", callable(AggregatedValidationItem))
check("validation_aggregator: aggregate_validation_items", callable(aggregate_validation_items))
check("validation_aggregator: merge_validation_aggregates", callable(merge_validation_aggregates))
check("validation_aggregator: collect_phase2_validation_warnings", callable(collect_phase2_validation_warnings))
check("validation_aggregator: validation_aggregate_tool_result_from_aggregate", callable(validation_aggregate_tool_result_from_aggregate))

# ---------------------------------------------------------------------------
# 12. Staleness Checker (Phase 2I)
# ---------------------------------------------------------------------------

from lib.reliability.staleness import (
    StalenessReport,
    StalenessFinding,
    StalenessPolicy,
    aggregate_staleness_findings,
    check_tool_result_staleness,
    check_news_snapshot_staleness,
    staleness_report_tool_result_from_report,
    summarize_staleness_report,
)

check("staleness: StalenessReport", callable(StalenessReport))
check("staleness: StalenessFinding", callable(StalenessFinding))
check("staleness: StalenessPolicy", callable(StalenessPolicy))
check("staleness: aggregate_staleness_findings", callable(aggregate_staleness_findings))
check("staleness: check_tool_result_staleness", callable(check_tool_result_staleness))
check("staleness: check_news_snapshot_staleness", callable(check_news_snapshot_staleness))
check("staleness: staleness_report_tool_result_from_report", callable(staleness_report_tool_result_from_report))
check("staleness: summarize_staleness_report", callable(summarize_staleness_report))

# ---------------------------------------------------------------------------
# 13. Critic Agent v0.1 (Phase 2J)
# ---------------------------------------------------------------------------

from lib.reliability.critic import (
    CriticResult,
    CriticIssue,
    run_mock_critic,
    critic_result_tool_result_from_result,
    summarize_critic_result,
)

check("critic: CriticResult", callable(CriticResult))
check("critic: CriticIssue", callable(CriticIssue))
check("critic: run_mock_critic", callable(run_mock_critic))
check("critic: critic_result_tool_result_from_result", callable(critic_result_tool_result_from_result))
check("critic: summarize_critic_result", callable(summarize_critic_result))

# ---------------------------------------------------------------------------
# 14. Evaluation Harness (Phase 2K)
# ---------------------------------------------------------------------------

from lib.reliability.evaluation import (
    ReliabilityScoreSummary,
    ReliabilityEvalCase,
    ReliabilityExpectedOutput,
    ReliabilityEvalCaseResult,
    ReliabilityFailureMode,
    REQUIRED_FAILURE_MODES,
    load_eval_cases,
    load_expected_outputs,
    run_single_eval_case,
    run_reliability_evals,
    summarize_reliability_score,
    save_reliability_score_summary,
)

check("evaluation: ReliabilityScoreSummary", callable(ReliabilityScoreSummary))
check("evaluation: ReliabilityEvalCase", callable(ReliabilityEvalCase))
check("evaluation: ReliabilityExpectedOutput", callable(ReliabilityExpectedOutput))
check("evaluation: ReliabilityEvalCaseResult", callable(ReliabilityEvalCaseResult))
check("evaluation: REQUIRED_FAILURE_MODES is a set/frozenset/list", isinstance(REQUIRED_FAILURE_MODES, (set, frozenset, list, tuple)))
check("evaluation: load_eval_cases", callable(load_eval_cases))
check("evaluation: load_expected_outputs", callable(load_expected_outputs))
check("evaluation: run_single_eval_case", callable(run_single_eval_case))
check("evaluation: run_reliability_evals", callable(run_reliability_evals))
check("evaluation: summarize_reliability_score", callable(summarize_reliability_score))
check("evaluation: save_reliability_score_summary", callable(save_reliability_score_summary))

# ---------------------------------------------------------------------------
# 15. Eval fixture files exist and are paired (Phase 2K)
# ---------------------------------------------------------------------------

_EVALS_DIR = os.path.join(_REPO_ROOT, "evals")
_CASES_DIR = os.path.join(_EVALS_DIR, "cases")
_EXPECTED_DIR = os.path.join(_EVALS_DIR, "expected")
_RUNNER_FILE = os.path.join(_EVALS_DIR, "run_evals.py")

check("evals/run_evals.py exists", os.path.isfile(_RUNNER_FILE))
check("evals/cases/ exists", os.path.isdir(_CASES_DIR))
check("evals/expected/ exists", os.path.isdir(_EXPECTED_DIR))

_case_files = sorted(f for f in os.listdir(_CASES_DIR) if f.endswith(".json")) if os.path.isdir(_CASES_DIR) else []
_expected_files = sorted(f for f in os.listdir(_EXPECTED_DIR) if f.endswith(".json")) if os.path.isdir(_EXPECTED_DIR) else []

check("evals/cases/ has at least 12 fixtures", len(_case_files) >= 12)
check("evals/expected/ has at least 12 fixtures", len(_expected_files) >= 12)
check("evals: cases and expected counts match", len(_case_files) == len(_expected_files),
      f"cases={len(_case_files)} expected={len(_expected_files)}")

# Verify each case has a matching expected file
_missing_expected = [f for f in _case_files if f not in _expected_files]
_orphan_expected = [f for f in _expected_files if f not in _case_files]
check("evals: no case is missing an expected file", len(_missing_expected) == 0,
      f"missing: {_missing_expected}")
check("evals: no orphan expected files", len(_orphan_expected) == 0,
      f"orphans: {_orphan_expected}")

# ---------------------------------------------------------------------------
# 16. Smoke: construct minimal objects
# ---------------------------------------------------------------------------

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

_run_id = f"TEST_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

_tr = ToolResult(
    evidence_id="ev_smoke_01",
    tool_name="smoke_tool",
    run_id=_run_id,
    ticker="AAPL",
    outputs={"price": 150.0},
)
check("smoke: ToolResult constructable", _tr.evidence_id == "ev_smoke_01")

_ar = AgentResult(
    run_id=_run_id,
    agent_name="smoke_agent",
    ticker="AAPL",
    findings=[
        Finding(
            text="Price is $150.",
            evidence=[EvidenceRef(evidence_id="ev_smoke_01", metric="price")],
            confidence=0.9,
        )
    ],
    assumptions=[Assumption(name="stable_market", rationale="VIX below 20")],
    risks=[Risk(name="macro_risk", description="Macro slowdown", evidence=[])],
    confidence=AgentConfidence(level="high", rationale="clean data"),
)
check("smoke: AgentResult constructable", _ar.agent_name == "smoke_agent")

# validate_agent_result requires an EvidenceStore; create a temp-dir-backed one
_tmpdir = tempfile.mkdtemp(prefix="phase2_closeout_smoke_")
_store = EvidenceStore(run_dir=Path(_tmpdir))
_store.add_tool_result(_tr)
_vr = validate_agent_result(_ar, _store)
check("smoke: validate_agent_result returns ValidationReport", hasattr(_vr, "issues") and hasattr(_vr, "passed"))

# ---------------------------------------------------------------------------
# 17. Forbidden module check
# ---------------------------------------------------------------------------

_FORBIDDEN = [
    "app",
    "streamlit",
    "lib.llm_orchestrator",
    "lib.data_fetcher",
    "lib.valuation",
    "lib.technical",
    "lib.rotation",
    "lib.workflow_state",
]

for _mod in _FORBIDDEN:
    _loaded = any(
        m == _mod or m.startswith(_mod + ".")
        for m in sys.modules
    )
    check(f"forbidden module not loaded: {_mod}", not _loaded)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print("Phase 2 Closeout Smoke Test")
print("=" * 60)

if FAIL > 0:
    print()
    print("FAILURES:")
    for label, ok, detail in _results:
        if not ok:
            d = f"  [{detail}]" if detail else ""
            print(f"  FAIL  {label}{d}")

print()
print(f"Passed: {PASS}")
print(f"Failed: {FAIL}")
print(f"Total:  {PASS + FAIL}")
print()

if FAIL == 0:
    print("RESULT: PASS — all Phase 0-2 reliability contracts verified.")
    sys.exit(0)
else:
    print("RESULT: FAIL — see failures above.")
    sys.exit(1)
