"""
scripts/test_reliability_horizon_synthesis.py

Phase 3B: Horizon-aware Synthesis Skeleton — test suite.

39 test cases covering:
  - Schema validation (models accept/reject)
  - Helper function determinism
  - Card/report build behavior
  - Issue conversion correctness
  - run_horizon_aware_synthesis end-to-end
  - ToolResult wrapping
  - Serialization roundtrip
  - No live app/LLM/API imports
  - Regression: orchestration skeleton tests still pass

Run directly:
    python3 scripts/test_reliability_horizon_synthesis.py
"""

import inspect
import subprocess
import sys
import os

# Add repo root to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from types import SimpleNamespace
from typing import Any

import pydantic

# --------------------------------------------------------------------------
# Import module under test
# --------------------------------------------------------------------------
import lib.reliability.horizon_synthesis as hs
from lib.reliability.horizon_synthesis import (
    HorizonSynthesisIssue,
    HorizonEvidenceSummary,
    HorizonSynthesisCard,
    HorizonSynthesisReport,
    HorizonSynthesisInputBundle,
    make_horizon_synthesis_issue_id,
    make_horizon_synthesis_id,
    extract_horizon_evidence_ids,
    summarize_horizon_evidence,
    issue_from_validation_item_for_horizon,
    issue_from_staleness_finding_for_horizon,
    issue_from_critic_issue_for_horizon,
    build_horizon_synthesis_card,
    build_horizon_synthesis_report,
    run_horizon_aware_synthesis,
    horizon_synthesis_tool_result_from_report,
    summarize_horizon_synthesis_report,
)

# Supporting imports for fixtures
from lib.reliability.schemas import (
    AgentResult,
    EvidenceRef,
    Finding,
    Assumption,
    Risk,
    ToolResult,
)
from lib.reliability.validation_aggregator import (
    AggregatedValidationItem,
    ValidationAggregate,
    make_validation_item_id,
    aggregate_validation_items,
)
from lib.reliability.staleness import (
    StalenessFinding,
    StalenessReport,
    make_staleness_finding_id,
    aggregate_staleness_findings,
)
from lib.reliability.critic import (
    CriticIssue,
    CriticResult,
    make_critic_issue_id,
    aggregate_critic_issues,
)

# --------------------------------------------------------------------------
# Counters
# --------------------------------------------------------------------------
_passed = 0
_failed = 0


def _pass(name: str) -> None:
    global _passed
    _passed += 1
    print(f"  [PASS] {name}")


def _fail(name: str, reason: str) -> None:
    global _failed
    _failed += 1
    print(f"  [FAIL] {name}: {reason}")


def _assert(condition: bool, name: str, reason: str = "") -> None:
    if condition:
        _pass(name)
    else:
        _fail(name, reason or "condition is False")


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

def _make_tool_result(tool_name: str = "test_tool", run_id: str = "run_001") -> ToolResult:
    from lib.reliability.adapters import make_evidence_id
    eid = make_evidence_id(run_id, tool_name, "TEST", "test_group", {"k": "v"})
    return ToolResult(
        evidence_id=eid,
        tool_name=tool_name,
        run_id=run_id,
        outputs={"result": "mock"},
    )


def _make_agent_result(run_id: str = "run_001") -> AgentResult:
    tr = _make_tool_result(run_id=run_id)
    return AgentResult(
        agent_name="test_agent",
        run_id=run_id,
        findings=[
            Finding(
                text="[MOCK] Test finding with evidence.",
                evidence=[EvidenceRef(evidence_id=tr.evidence_id)],
                confidence=0.5,
            )
        ],
        assumptions=[Assumption(name="mock_assumption", rationale="testing", source="agent")],
        risks=[Risk(name="mock_risk", description="test risk", severity="low")],
    )


def _make_validation_item(
    item_type: str = "missing_data",
    severity: str = "warning",
    message: str = "Test validation item.",
) -> AggregatedValidationItem:
    iid = make_validation_item_id("agent_result", message)
    return AggregatedValidationItem(
        item_id=iid,
        domain="agent_result",
        severity=severity,
        item_type=item_type,
        message=message,
    )


def _make_validation_aggregate(items=None) -> ValidationAggregate:
    if items is None:
        items = [_make_validation_item()]
    agg_id = "test_agg_001"
    return aggregate_validation_items(agg_id, "2026-05-22", items)


def _make_staleness_finding(
    status: str = "stale",
    severity: str = "warning",
    evidence_id: str = "ev_001",
    field_path: str = "created_at",
) -> StalenessFinding:
    fid = make_staleness_finding_id("tool_result", "generated_at", None, "2026-05-22")
    return StalenessFinding(
        finding_id=fid,
        domain="tool_result",
        status=status,
        severity=severity,
        message=f"Tool result {status} (test fixture).",
        as_of="2026-05-22",
        evidence_id=evidence_id,
        field_path=field_path,
    )


def _make_staleness_report(findings=None) -> StalenessReport:
    if findings is None:
        findings = [_make_staleness_finding()]
    return aggregate_staleness_findings("test_sr_001", "2026-05-22", findings)


def _make_critic_issue(
    issue_type: str = "missing_risk",
    severity: str = "warning",
) -> CriticIssue:
    msg = f"[MOCK] Critic issue: {issue_type}."
    iid = make_critic_issue_id(issue_type, msg)
    return CriticIssue(
        issue_id=iid,
        issue_type=issue_type,
        severity=severity,
        message=msg,
    )


def _make_critic_result(issues=None) -> CriticResult:
    if issues is None:
        issues = [_make_critic_issue()]
    return aggregate_critic_issues("test_critic_001", "2026-05-22", issues)


def _make_evidence_summary(
    horizon: str = "short_term",
    evidence_count: int = 0,
) -> HorizonEvidenceSummary:
    return HorizonEvidenceSummary(
        horizon=horizon,
        evidence_count=evidence_count,
        missing_domains=["technical", "news"] if evidence_count == 0 else [],
    )


# ============================================================
# Test Group 1: Model validation — HorizonSynthesisIssue
# ============================================================

def test_01_issue_accepts_valid():
    try:
        issue = HorizonSynthesisIssue(
            issue_id="issue_001",
            issue_type="missing_evidence",
            horizon="short_term",
            severity="warning",
            message="Test missing evidence.",
        )
        _assert(issue.issue_id == "issue_001", "T01: HorizonSynthesisIssue accepts valid issue")
    except Exception as e:
        _fail("T01: HorizonSynthesisIssue accepts valid issue", str(e))


def test_02_issue_rejects_empty_id():
    try:
        HorizonSynthesisIssue(
            issue_id="",
            issue_type="other",
            message="msg",
        )
        _fail("T02: HorizonSynthesisIssue rejects empty issue_id", "no error raised")
    except (pydantic.ValidationError, ValueError):
        _pass("T02: HorizonSynthesisIssue rejects empty issue_id")


def test_03_issue_rejects_empty_message():
    try:
        HorizonSynthesisIssue(
            issue_id="issue_001",
            issue_type="other",
            message="",
        )
        _fail("T03: HorizonSynthesisIssue rejects empty message", "no error raised")
    except (pydantic.ValidationError, ValueError):
        _pass("T03: HorizonSynthesisIssue rejects empty message")


# ============================================================
# Test Group 2: HorizonEvidenceSummary
# ============================================================

def test_04_evidence_summary_accepts_valid():
    try:
        es = HorizonEvidenceSummary(
            horizon="medium_term",
            evidence_count=3,
            missing_domains=["earnings"],
        )
        _assert(es.horizon == "medium_term", "T04: HorizonEvidenceSummary accepts valid summary")
    except Exception as e:
        _fail("T04: HorizonEvidenceSummary accepts valid summary", str(e))


def test_05_evidence_summary_rejects_negative_counts():
    try:
        HorizonEvidenceSummary(
            horizon="short_term",
            evidence_count=-1,
        )
        _fail("T05: HorizonEvidenceSummary rejects negative counts", "no error raised")
    except (pydantic.ValidationError, ValueError):
        _pass("T05: HorizonEvidenceSummary rejects negative counts")


# ============================================================
# Test Group 3: HorizonSynthesisCard
# ============================================================

def test_06_card_accepts_valid():
    try:
        es = _make_evidence_summary(evidence_count=2)
        card = HorizonSynthesisCard(
            horizon="short_term",
            evidence_summary=es,
            confidence="medium",
        )
        _assert(card.horizon == "short_term", "T06: HorizonSynthesisCard accepts valid card")
    except Exception as e:
        _fail("T06: HorizonSynthesisCard accepts valid card", str(e))


# ============================================================
# Test Group 4: HorizonSynthesisReport
# ============================================================

def test_07_report_accepts_valid():
    try:
        report = HorizonSynthesisReport(
            synthesis_id="syn_001",
            as_of="2026-05-22",
            ticker="TEST",
        )
        _assert(report.synthesis_id == "syn_001", "T07: HorizonSynthesisReport accepts valid report")
    except Exception as e:
        _fail("T07: HorizonSynthesisReport accepts valid report", str(e))


def test_08_report_rejects_empty_synthesis_id():
    try:
        HorizonSynthesisReport(synthesis_id="", as_of="2026-05-22")
        _fail("T08: HorizonSynthesisReport rejects empty synthesis_id", "no error raised")
    except (pydantic.ValidationError, ValueError):
        _pass("T08: HorizonSynthesisReport rejects empty synthesis_id")


def test_09_report_rejects_empty_as_of():
    try:
        HorizonSynthesisReport(synthesis_id="syn_001", as_of="")
        _fail("T09: HorizonSynthesisReport rejects empty as_of", "no error raised")
    except (pydantic.ValidationError, ValueError):
        _pass("T09: HorizonSynthesisReport rejects empty as_of")


# ============================================================
# Test Group 5: HorizonSynthesisInputBundle
# ============================================================

def test_10_bundle_accepts_minimal():
    try:
        bundle = HorizonSynthesisInputBundle(bundle_id="b001", as_of="2026-05-22")
        _assert(bundle.bundle_id == "b001", "T10: HorizonSynthesisInputBundle accepts minimal bundle")
    except Exception as e:
        _fail("T10: HorizonSynthesisInputBundle accepts minimal bundle", str(e))


def test_11_bundle_rejects_empty_bundle_id():
    try:
        HorizonSynthesisInputBundle(bundle_id="", as_of="2026-05-22")
        _fail("T11: HorizonSynthesisInputBundle rejects empty bundle_id", "no error raised")
    except (pydantic.ValidationError, ValueError):
        _pass("T11: HorizonSynthesisInputBundle rejects empty bundle_id")


def test_12_bundle_rejects_empty_as_of():
    try:
        HorizonSynthesisInputBundle(bundle_id="b001", as_of="")
        _fail("T12: HorizonSynthesisInputBundle rejects empty as_of", "no error raised")
    except (pydantic.ValidationError, ValueError):
        _pass("T12: HorizonSynthesisInputBundle rejects empty as_of")


# ============================================================
# Test Group 6: make_horizon_synthesis_issue_id
# ============================================================

def test_13_issue_id_deterministic():
    id1 = make_horizon_synthesis_issue_id("missing_evidence", "short_term", "No evidence found.")
    id2 = make_horizon_synthesis_issue_id("missing_evidence", "short_term", "No evidence found.")
    _assert(id1 == id2, "T13: make_horizon_synthesis_issue_id deterministic")


def test_14_issue_id_changes_with_inputs():
    id1 = make_horizon_synthesis_issue_id("missing_evidence", "short_term", "No evidence found.")
    id2 = make_horizon_synthesis_issue_id("missing_evidence", "short_term", "Different message.")
    _assert(id1 != id2, "T14: make_horizon_synthesis_issue_id changes when inputs change")


# ============================================================
# Test Group 7: make_horizon_synthesis_id
# ============================================================

def test_15_synthesis_id_deterministic():
    id1 = make_horizon_synthesis_id("bundle_001", "2026-05-22", "AAPL")
    id2 = make_horizon_synthesis_id("bundle_001", "2026-05-22", "AAPL")
    _assert(id1 == id2, "T15: make_horizon_synthesis_id deterministic")


# ============================================================
# Test Group 8: extract_horizon_evidence_ids
# ============================================================

def test_16_extract_collects_tool_result_ids():
    tr = _make_tool_result("technical_rsi", "run_001")
    ids = extract_horizon_evidence_ids(tool_results=[tr])
    _assert(tr.evidence_id in ids, "T16: extract_horizon_evidence_ids collects ToolResult evidence IDs")


def test_17_extract_collects_agent_result_refs():
    ar = _make_agent_result("run_001")
    # The agent result has findings with evidence refs
    expected_ids = [eref.evidence_id for f in ar.findings for eref in f.evidence]
    ids = extract_horizon_evidence_ids(agent_result=ar)
    if expected_ids:
        _assert(
            all(eid in ids for eid in expected_ids),
            "T17: extract_horizon_evidence_ids collects AgentResult evidence refs",
        )
    else:
        _pass("T17: extract_horizon_evidence_ids collects AgentResult evidence refs (no refs)")


# ============================================================
# Test Group 9: summarize_horizon_evidence
# ============================================================

def test_18_summarize_evidence_returns_counts_and_missing():
    tr = _make_tool_result("valuation_dcf", "run_001")
    va = _make_validation_aggregate()
    sr = _make_staleness_report()
    cr = _make_critic_result()

    summary = summarize_horizon_evidence(
        horizon="long_term",
        tool_results=[tr],
        validation_aggregate=va,
        staleness_report=sr,
        critic_result=cr,
    )
    _assert(
        isinstance(summary.evidence_count, int) and summary.evidence_count >= 0,
        "T18a: summarize_horizon_evidence returns non-negative evidence_count",
    )
    _assert(
        isinstance(summary.missing_domains, list),
        "T18b: summarize_horizon_evidence returns missing_domains list",
    )
    # long_term expects: valuation, fundamental, macro
    # We provided valuation_dcf → "valuation" should be covered
    _assert(
        "valuation" not in summary.missing_domains,
        "T18c: summarize_horizon_evidence infers valuation coverage from tool_name",
    )


# ============================================================
# Test Group 10: issue_from_validation_item_for_horizon
# ============================================================

def test_19_validation_item_mapping():
    stale_item = _make_validation_item("stale_data", "warning", "Data is stale.")
    issue = issue_from_validation_item_for_horizon(stale_item, "short_term")
    _assert(issue.issue_type == "stale_evidence", "T19a: stale_data maps to stale_evidence")

    missing_item = _make_validation_item("missing_data", "critical", "Data is missing.")
    issue2 = issue_from_validation_item_for_horizon(missing_item, "medium_term")
    _assert(issue2.issue_type == "missing_evidence", "T19b: missing_data maps to missing_evidence")

    unsupported_item = _make_validation_item("unsupported", "warning", "Unsupported claim.")
    issue3 = issue_from_validation_item_for_horizon(unsupported_item, "long_term")
    _assert(issue3.issue_type == "unsupported_claim", "T19c: unsupported maps to unsupported_claim")


# ============================================================
# Test Group 11: issue_from_staleness_finding_for_horizon
# ============================================================

def test_20_staleness_finding_preserves_fields():
    finding = _make_staleness_finding(
        status="stale",
        evidence_id="ev_stale_001",
        field_path="outputs.as_of",
    )
    issue = issue_from_staleness_finding_for_horizon(finding, "short_term")
    _assert(issue.issue_type == "stale_evidence", "T20a: stale finding maps to stale_evidence")
    _assert(issue.evidence_id == "ev_stale_001", "T20b: staleness finding preserves evidence_id")
    _assert(issue.field_path == "outputs.as_of", "T20c: staleness finding preserves field_path")

    unknown_finding = _make_staleness_finding(status="unknown", severity="warning")
    issue2 = issue_from_staleness_finding_for_horizon(unknown_finding, "medium_term")
    _assert(issue2.issue_type == "missing_evidence", "T20d: unknown finding maps to missing_evidence")


# ============================================================
# Test Group 12: issue_from_critic_issue_for_horizon
# ============================================================

def test_21_critic_issue_maps_missing_risk():
    ci = _make_critic_issue("missing_risk", "warning")
    issue = issue_from_critic_issue_for_horizon(ci, "long_term")
    _assert(issue.issue_type == "missing_risk", "T21a: critic missing_risk maps to missing_risk")
    _assert(issue.related_id == ci.issue_id, "T21b: critic issue related_id preserved")


# ============================================================
# Test Group 13: build_horizon_synthesis_card
# ============================================================

def test_22_card_insufficient_evidence_when_no_evidence():
    es = _make_evidence_summary("short_term", evidence_count=0)
    card = build_horizon_synthesis_card(
        horizon="short_term",
        evidence_summary=es,
    )
    _assert(
        card.confidence == "insufficient_evidence",
        "T22: build_horizon_synthesis_card confidence=insufficient_evidence when no evidence",
    )
    _assert(
        card.signal_direction == "insufficient_evidence",
        "T22b: signal_direction=insufficient_evidence when no evidence",
    )


def test_23_card_includes_all_issue_sources():
    es = _make_evidence_summary("short_term", evidence_count=0)
    va = _make_validation_aggregate()
    sr = _make_staleness_report()
    cr = _make_critic_result()

    card = build_horizon_synthesis_card(
        horizon="short_term",
        evidence_summary=es,
        validation_aggregate=va,
        staleness_report=sr,
        critic_result=cr,
    )
    issue_types = {i.issue_type for i in card.issues}
    _assert(len(card.issues) > 0, "T23a: card has issues from sources")
    # validation item (missing_data → missing_evidence), staleness (stale → stale_evidence),
    # critic (missing_risk → missing_risk), missing domains (missing_evidence)
    has_stale = "stale_evidence" in issue_types
    has_missing = "missing_evidence" in issue_types
    has_critic = "missing_risk" in issue_types
    _assert(
        has_stale and has_missing and has_critic,
        f"T23b: card includes validation/staleness/critic issues (stale={has_stale}, missing={has_missing}, critic={has_critic})",
    )


# ============================================================
# Test Group 14: build_horizon_synthesis_report
# ============================================================

def test_24_report_orders_cards():
    # Provide cards in wrong order
    c_long = HorizonSynthesisCard(horizon="long_term")
    c_short = HorizonSynthesisCard(horizon="short_term")
    c_med = HorizonSynthesisCard(horizon="medium_term")

    report = build_horizon_synthesis_report(
        synthesis_id="syn_001",
        as_of="2026-05-22",
        cards=[c_long, c_med, c_short],
    )
    horizons = [c.horizon for c in report.cards]
    _assert(
        horizons == ["short_term", "medium_term", "long_term"],
        f"T24: build_horizon_synthesis_report orders cards short/medium/long (got {horizons})",
    )


# ============================================================
# Test Group 15: run_horizon_aware_synthesis
# ============================================================

def test_25_run_returns_three_cards():
    bundle = HorizonSynthesisInputBundle(bundle_id="b001", as_of="2026-05-22")
    report = run_horizon_aware_synthesis(bundle)
    _assert(len(report.cards) == 3, f"T25: run_horizon_aware_synthesis returns 3 cards (got {len(report.cards)})")
    horizons = [c.horizon for c in report.cards]
    _assert(
        horizons == ["short_term", "medium_term", "long_term"],
        f"T25b: cards are in canonical order (got {horizons})",
    )


def test_26_run_uses_orchestration_report_fallback():
    va = _make_validation_aggregate([
        _make_validation_item("stale_data", "warning", "Staleness from orchestration.")
    ])
    mock_orch = SimpleNamespace(
        orchestration_id="orch_fallback_001",
        validation_aggregate=va,
        staleness_report=None,
        critic_result=None,
    )
    bundle = HorizonSynthesisInputBundle(
        bundle_id="b_fallback",
        as_of="2026-05-22",
        orchestration_report=mock_orch,
        # No validation_aggregate in bundle directly
    )
    report = run_horizon_aware_synthesis(bundle)
    _assert(
        report.orchestration_report_id == "orch_fallback_001",
        "T26a: orchestration_report_id propagated from fallback",
    )
    # All cards should have the validation issues converted
    all_card_issues = [i for card in report.cards for i in card.issues]
    stale_issues = [i for i in all_card_issues if i.issue_type == "stale_evidence"]
    _assert(
        len(stale_issues) > 0,
        f"T26b: cards include staleness issues from orchestration_report fallback ({len(stale_issues)} stale issues)",
    )


def test_27_run_does_not_mutate_bundle():
    tr = _make_tool_result("news_snapshot", "run_001")
    bundle = HorizonSynthesisInputBundle(
        bundle_id="b_immut",
        as_of="2026-05-22",
        tool_results=[tr],
        metadata={"key": "original"},
    )
    original_tool_results = list(bundle.tool_results)
    original_metadata = dict(bundle.metadata)

    run_horizon_aware_synthesis(bundle)

    _assert(
        list(bundle.tool_results) == original_tool_results,
        "T27a: run_horizon_aware_synthesis does not mutate bundle.tool_results",
    )
    _assert(
        dict(bundle.metadata) == original_metadata,
        "T27b: run_horizon_aware_synthesis does not mutate bundle.metadata",
    )


# ============================================================
# Test Group 16: horizon_synthesis_tool_result_from_report
# ============================================================

def test_28_tool_result_is_valid():
    bundle = HorizonSynthesisInputBundle(bundle_id="b001", as_of="2026-05-22", ticker="AAPL")
    report = run_horizon_aware_synthesis(bundle)
    tr = horizon_synthesis_tool_result_from_report(run_id="run_001", report=report)
    _assert(isinstance(tr, ToolResult), "T28: horizon_synthesis_tool_result_from_report returns ToolResult")


def test_29_tool_result_stable_tool_name_and_target():
    bundle = HorizonSynthesisInputBundle(bundle_id="b001", as_of="2026-05-22", ticker="NVDA")
    report = run_horizon_aware_synthesis(bundle)
    tr = horizon_synthesis_tool_result_from_report(run_id="run_001", report=report)
    _assert(
        tr.tool_name == "horizon_synthesis_report",
        f"T29a: stable tool_name (got {tr.tool_name!r})",
    )
    _assert(
        "NVDA" in tr.inputs.get("target", "") or tr.inputs.get("target") == "NVDA",
        f"T29b: target is ticker (got {tr.inputs.get('target')!r})",
    )


def test_30_tool_result_payload_keys():
    bundle = HorizonSynthesisInputBundle(bundle_id="b001", as_of="2026-05-22")
    report = run_horizon_aware_synthesis(bundle)
    tr = horizon_synthesis_tool_result_from_report(run_id="run_001", report=report)
    _assert("report" in tr.outputs, "T30a: payload includes 'report'")
    _assert("summary" in tr.outputs, "T30b: payload includes 'summary'")
    _assert("calculation_version" in tr.outputs, "T30c: payload includes 'calculation_version'")


def test_31_tool_result_evidence_id_deterministic():
    bundle = HorizonSynthesisInputBundle(bundle_id="b001", as_of="2026-05-22")
    report = run_horizon_aware_synthesis(bundle)
    tr1 = horizon_synthesis_tool_result_from_report(run_id="run_001", report=report)
    tr2 = horizon_synthesis_tool_result_from_report(run_id="run_001", report=report)
    _assert(
        tr1.evidence_id == tr2.evidence_id,
        f"T31: evidence_id is deterministic (got {tr1.evidence_id!r})",
    )


def test_39_tool_result_evidence_id_changes_with_report_content():
    """evidence_id must change when serialized report content changes."""
    # Two reports with the same synthesis_id / as_of / ticker / target,
    # but different card content — evidence_id must differ.
    common_synthesis_id = "syn_content_test"
    common_as_of = "2026-05-22"
    common_ticker = "TEST"

    issue_a = HorizonSynthesisIssue(
        issue_id="issue_alpha_001",
        issue_type="other",
        severity="info",
        message="Alpha card info issue — report A.",
    )
    issue_b = HorizonSynthesisIssue(
        issue_id="issue_beta_001",
        issue_type="other",
        severity="info",
        message="Beta card info issue — report B, different content.",
    )

    card_a = HorizonSynthesisCard(
        horizon="short_term",
        thesis_summary="Report A preliminary thesis.",
        issues=[issue_a],
    )
    card_b = HorizonSynthesisCard(
        horizon="short_term",
        thesis_summary="Report B different thesis content.",
        issues=[issue_b],
    )

    report_a = HorizonSynthesisReport(
        synthesis_id=common_synthesis_id,
        as_of=common_as_of,
        ticker=common_ticker,
        cards=[card_a],
    )
    report_b = HorizonSynthesisReport(
        synthesis_id=common_synthesis_id,
        as_of=common_as_of,
        ticker=common_ticker,
        cards=[card_b],
    )

    tr_a = horizon_synthesis_tool_result_from_report(
        run_id="same_run",
        report=report_a,
        target="same_target",
        calculation_version="horizon_synthesis_skeleton_v1",
    )
    tr_b = horizon_synthesis_tool_result_from_report(
        run_id="same_run",
        report=report_b,
        target="same_target",
        calculation_version="horizon_synthesis_skeleton_v1",
    )

    _assert(
        tr_a.evidence_id != tr_b.evidence_id,
        f"T39a: evidence_id changes when report content changes "
        f"(a={tr_a.evidence_id!r}, b={tr_b.evidence_id!r})",
    )
    _assert(
        isinstance(tr_a, ToolResult) and isinstance(tr_b, ToolResult),
        "T39b: both ToolResults remain valid",
    )
    _assert(
        all(k in tr_a.outputs for k in ("report", "summary", "calculation_version")),
        "T39c: report_a ToolResult payload includes report, summary, calculation_version",
    )
    _assert(
        all(k in tr_b.outputs for k in ("report", "summary", "calculation_version")),
        "T39d: report_b ToolResult payload includes report, summary, calculation_version",
    )
    _assert(
        tr_a.evidence_id == horizon_synthesis_tool_result_from_report(
            run_id="same_run",
            report=report_a,
            target="same_target",
            calculation_version="horizon_synthesis_skeleton_v1",
        ).evidence_id,
        "T39e: evidence_id remains deterministic for identical report_a payload",
    )


# ============================================================
# Test Group 17: summarize_horizon_synthesis_report
# ============================================================

def test_32_summarize_returns_expected_keys():
    bundle = HorizonSynthesisInputBundle(bundle_id="b001", as_of="2026-05-22", ticker="MSFT")
    report = run_horizon_aware_synthesis(bundle)
    summary = summarize_horizon_synthesis_report(report)

    required_keys = [
        "synthesis_id", "ticker", "status", "recommendation",
        "card_count", "issue_count", "critical_count", "warning_count", "info_count",
        "horizon_statuses", "horizon_recommendations", "top_messages",
    ]
    missing = [k for k in required_keys if k not in summary]
    _assert(not missing, f"T32a: summarize returns all required keys (missing: {missing})")
    _assert(summary["card_count"] == 3, f"T32b: card_count == 3 (got {summary['card_count']})")
    _assert(summary["ticker"] == "MSFT", f"T32c: ticker preserved (got {summary['ticker']!r})")
    _assert(isinstance(summary["top_messages"], list), "T32d: top_messages is a list")
    # Cap at 10
    _assert(len(summary["top_messages"]) <= 10, f"T32e: top_messages capped at 10 (got {len(summary['top_messages'])})")


# ============================================================
# Test Group 18: Serialization roundtrip
# ============================================================

def test_33_report_serialization_roundtrip():
    bundle = HorizonSynthesisInputBundle(
        bundle_id="b_rt",
        as_of="2026-05-22",
        ticker="GOOG",
        validation_aggregate=_make_validation_aggregate(),
    )
    report = run_horizon_aware_synthesis(bundle)
    data = report.model_dump(mode="json")
    report2 = HorizonSynthesisReport.model_validate(data)
    _assert(
        report.synthesis_id == report2.synthesis_id,
        "T33a: HorizonSynthesisReport roundtrip preserves synthesis_id",
    )
    _assert(
        report.status == report2.status,
        f"T33b: HorizonSynthesisReport roundtrip preserves status (got {report2.status!r})",
    )
    _assert(
        len(report.cards) == len(report2.cards),
        f"T33c: HorizonSynthesisReport roundtrip preserves card count",
    )


def test_34_issue_serialization_roundtrip():
    issue = HorizonSynthesisIssue(
        issue_id="issue_rt_001",
        issue_type="stale_evidence",
        horizon="long_term",
        severity="critical",
        message="Stale evidence roundtrip test.",
        evidence_id="ev_001",
        field_path="created_at",
    )
    data = issue.model_dump(mode="json")
    issue2 = HorizonSynthesisIssue.model_validate(data)
    _assert(issue.issue_id == issue2.issue_id, "T34a: HorizonSynthesisIssue roundtrip preserves issue_id")
    _assert(issue.issue_type == issue2.issue_type, "T34b: HorizonSynthesisIssue roundtrip preserves issue_type")
    _assert(issue.evidence_id == issue2.evidence_id, "T34c: HorizonSynthesisIssue roundtrip preserves evidence_id")


# ============================================================
# Test Group 19: No live app/LLM/API imports
# ============================================================

def test_35_no_live_app_modules_imported():
    src = inspect.getsource(hs)
    # Check only actual import lines (not comments or docstrings)
    import_lines = [
        line.strip() for line in src.split("\n")
        if line.strip().startswith(("import ", "from "))
    ]
    forbidden_checks = [
        lambda l: l.startswith("import app") or (l.startswith("from app") and "from app" in l),
        lambda l: l.startswith("from pages") or l.startswith("import pages"),
        lambda l: "llm_orchestrator" in l and ("import" in l or "from" in l),
    ]
    violations = [
        line for line in import_lines
        if any(check(line) for check in forbidden_checks)
    ]
    _assert(
        not violations,
        f"T35: No live app modules in import statements (violations: {violations})",
    )


def test_36_no_external_api_calls():
    src = inspect.getsource(hs)
    # Check only actual import lines for network/external library patterns
    import_lines = [
        line.strip() for line in src.split("\n")
        if line.strip().startswith(("import ", "from "))
    ]
    network_patterns = ["requests", "urllib.request", "http.client", "socket", "aiohttp"]
    violations = [
        line for line in import_lines
        if any(pat in line for pat in network_patterns)
    ]
    _assert(
        not violations,
        f"T36: No external network imports in horizon_synthesis.py (violations: {violations})",
    )


def test_37_no_llm_api_called():
    src = inspect.getsource(hs)
    # Check only actual import lines for LLM/API patterns
    import_lines = [
        line.strip() for line in src.split("\n")
        if line.strip().startswith(("import ", "from "))
    ]
    llm_patterns = ["anthropic", "openai", "claude_client"]
    violations = [
        line for line in import_lines
        if any(pat in line for pat in llm_patterns)
    ]
    _assert(
        not violations,
        f"T37: No LLM/Claude API imports in horizon_synthesis.py (violations: {violations})",
    )


# ============================================================
# Test Group 20: Regression — orchestration skeleton
# ============================================================

def test_38_orchestration_skeleton_regression():
    result = subprocess.run(
        [sys.executable, "scripts/test_reliability_orchestration_skeleton.py"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    _assert(
        result.returncode == 0,
        f"T38: test_reliability_orchestration_skeleton.py passes (returncode={result.returncode})\n"
        f"stdout: {result.stdout[-500:] if result.stdout else ''}\n"
        f"stderr: {result.stderr[-200:] if result.stderr else ''}",
    )


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("\n=== Phase 3B: Horizon-aware Synthesis Skeleton — Test Suite ===\n")

    print("Group 1: HorizonSynthesisIssue validation")
    test_01_issue_accepts_valid()
    test_02_issue_rejects_empty_id()
    test_03_issue_rejects_empty_message()

    print("\nGroup 2: HorizonEvidenceSummary validation")
    test_04_evidence_summary_accepts_valid()
    test_05_evidence_summary_rejects_negative_counts()

    print("\nGroup 3: HorizonSynthesisCard validation")
    test_06_card_accepts_valid()

    print("\nGroup 4: HorizonSynthesisReport validation")
    test_07_report_accepts_valid()
    test_08_report_rejects_empty_synthesis_id()
    test_09_report_rejects_empty_as_of()

    print("\nGroup 5: HorizonSynthesisInputBundle validation")
    test_10_bundle_accepts_minimal()
    test_11_bundle_rejects_empty_bundle_id()
    test_12_bundle_rejects_empty_as_of()

    print("\nGroup 6: make_horizon_synthesis_issue_id")
    test_13_issue_id_deterministic()
    test_14_issue_id_changes_with_inputs()

    print("\nGroup 7: make_horizon_synthesis_id")
    test_15_synthesis_id_deterministic()

    print("\nGroup 8: extract_horizon_evidence_ids")
    test_16_extract_collects_tool_result_ids()
    test_17_extract_collects_agent_result_refs()

    print("\nGroup 9: summarize_horizon_evidence")
    test_18_summarize_evidence_returns_counts_and_missing()

    print("\nGroup 10: issue_from_validation_item_for_horizon")
    test_19_validation_item_mapping()

    print("\nGroup 11: issue_from_staleness_finding_for_horizon")
    test_20_staleness_finding_preserves_fields()

    print("\nGroup 12: issue_from_critic_issue_for_horizon")
    test_21_critic_issue_maps_missing_risk()

    print("\nGroup 13: build_horizon_synthesis_card")
    test_22_card_insufficient_evidence_when_no_evidence()
    test_23_card_includes_all_issue_sources()

    print("\nGroup 14: build_horizon_synthesis_report")
    test_24_report_orders_cards()

    print("\nGroup 15: run_horizon_aware_synthesis")
    test_25_run_returns_three_cards()
    test_26_run_uses_orchestration_report_fallback()
    test_27_run_does_not_mutate_bundle()

    print("\nGroup 16: horizon_synthesis_tool_result_from_report")
    test_28_tool_result_is_valid()
    test_29_tool_result_stable_tool_name_and_target()
    test_30_tool_result_payload_keys()
    test_31_tool_result_evidence_id_deterministic()
    test_39_tool_result_evidence_id_changes_with_report_content()

    print("\nGroup 17: summarize_horizon_synthesis_report")
    test_32_summarize_returns_expected_keys()

    print("\nGroup 18: Serialization roundtrips")
    test_33_report_serialization_roundtrip()
    test_34_issue_serialization_roundtrip()

    print("\nGroup 19: No live app/LLM/API imports")
    test_35_no_live_app_modules_imported()
    test_36_no_external_api_calls()
    test_37_no_llm_api_called()

    print("\nGroup 20: Regression — orchestration skeleton")
    test_38_orchestration_skeleton_regression()

    print(f"\n{'='*60}")
    total = _passed + _failed
    print(f"Results: {_passed}/{total} passed, {_failed} failed")
    if _failed == 0:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)
    # Expected: 67/67 (62 original + 5 from T39)

    sys.exit(0 if _failed == 0 else 1)


if __name__ == "__main__":
    main()
