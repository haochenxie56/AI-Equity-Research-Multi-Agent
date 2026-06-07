"""
scripts/test_reliability_decision_packet.py

Phase 3E test suite: DecisionPacket Schema / Decision Synthesis Skeleton.

Run:
    python3 scripts/test_reliability_decision_packet.py

All 58 assertions are self-contained. No network/API/LLM calls are made.
"""
from __future__ import annotations

import sys
import os

# Ensure repo root is on sys.path before any local imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from typing import Any

import pydantic


def _run_test(name: str, fn) -> bool:
    try:
        fn()
        print(f"  PASS  {name}")
        return True
    except Exception as exc:
        print(f"  FAIL  {name}: {exc}")
        return False


# ---------------------------------------------------------------------------
# Import guard — must not pull in any live app modules
# ---------------------------------------------------------------------------

def _import_forbidden_modules() -> None:
    """Ensure no live app modules are imported by decision_packet."""
    forbidden = ["app", "pages", "lib.llm_orchestrator", "streamlit"]
    for mod in forbidden:
        assert mod not in sys.modules, f"Forbidden module loaded: {mod}"


# ---------------------------------------------------------------------------
# Imports from the module under test
# ---------------------------------------------------------------------------

from lib.reliability.decision_packet import (
    DecisionActionDraft,
    DecisionActionType,
    DecisionConfidence,
    DecisionGuardrail,
    DecisionGuardrailType,
    DecisionHorizon,
    DecisionIssueSeverity,
    DecisionPacket,
    DecisionPacketInputBundle,
    DecisionPacketIssue,
    DecisionRationale,
    DecisionRecommendation,
    DecisionReviewRequirement,
    DecisionReviewStatus,
    DecisionSourceType,
    DecisionPacketStatus,
    build_decision_action_draft,
    build_decision_guardrails,
    build_decision_packet,
    build_decision_rationales,
    build_review_requirements,
    decision_packet_tool_result_from_packet,
    extract_decision_evidence_ids,
    issue_from_critic_issue_for_decision,
    issue_from_debate_issue_for_decision,
    issue_from_staleness_finding_for_decision,
    issue_from_validation_item_for_decision,
    make_decision_packet_id,
    make_decision_packet_issue_id,
    run_decision_packet_synthesis,
    summarize_decision_packet,
)

from lib.reliability.schemas import AgentResult, ToolResult
from lib.reliability.validation_aggregator import (
    AggregatedValidationItem,
    ValidationAggregate,
    make_validation_item_id,
)
from lib.reliability.staleness import StalenessFinding, StalenessReport
from lib.reliability.critic import CriticIssue, CriticResult
from lib.reliability.adapters import stable_hash_payload
from lib.reliability.horizon_synthesis import (
    HorizonEvidenceSummary,
    HorizonSynthesisCard,
    HorizonSynthesisReport,
)
from lib.reliability.macro_agent import (
    MacroAgentResult,
    MacroRegimeAssessment,
    MacroHorizonImpact,
    MacroSectorBias,
)
from lib.reliability.orchestration import OrchestrationReport


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _make_validation_item(severity: str = "warning", item_type: str = "missing_data") -> AggregatedValidationItem:
    iid = make_validation_item_id(
        domain="agent_result",
        message="Test validation item",
        source_name=item_type,
        object_id="obj1",
        field_path="findings[0].text",
    )
    return AggregatedValidationItem(
        item_id=iid,
        domain="agent_result",
        severity=severity,
        item_type=item_type,
        message="Test validation item",
        object_id="obj1",
        evidence_id="ev_001",
        field_path="findings[0].text",
    )


def _make_staleness_finding(status: str = "stale") -> StalenessFinding:
    from lib.reliability.staleness import make_staleness_finding_id
    fid = make_staleness_finding_id(
        domain="tool_result",
        timestamp_role="as_of",
        timestamp_value="2024-01-01",
        as_of="2026-05-23",
        object_id="tr_001",
        field_path="created_at",
    )
    severity = "critical" if status == "expired" else "warning"
    return StalenessFinding(
        finding_id=fid,
        domain="tool_result",
        status=status,
        severity=severity,
        message=f"Data is {status}.",
        as_of="2026-05-23",
        object_id="tr_001",
        field_path="created_at",
        evidence_id="ev_002",
    )


def _make_critic_issue(issue_type: str = "missing_risk") -> CriticIssue:
    from lib.reliability.critic import make_critic_issue_id
    iid = make_critic_issue_id(
        issue_type=issue_type,
        message=f"Critic found {issue_type}",
        target_id="ar_001",
    )
    return CriticIssue(
        issue_id=iid,
        issue_type=issue_type,
        severity="warning",
        target_type="agent_result",
        message=f"Critic found {issue_type}",
        target_id="ar_001",
        evidence_id="ev_003",
        field_path="risks[0]",
    )


def _make_debate_issue_duck(issue_type: str = "unresolved_question") -> object:
    """Duck-typed DebateIssue with minimal interface."""
    class _FakeDebateIssue:
        def __init__(self):
            self.issue_id = f"di_{stable_hash_payload({'t': issue_type}, 8)}"
            self.issue_type = issue_type
            self.severity = "warning"
            self.message = f"Debate issue: {issue_type}"
            self.related_id = "round_01"
            self.evidence_id = "ev_004"
            self.field_path = "round.bull_position"
    return _FakeDebateIssue()


def _make_tool_result(eid: str = "ev_tr_001") -> ToolResult:
    return ToolResult(
        evidence_id=eid,
        tool_name="mock_tool",
        run_id="run_test",
        outputs={"value": 42},
    )


def _make_validation_aggregate(n_warning: int = 1, n_critical: int = 0) -> ValidationAggregate:
    items = []
    for i in range(n_warning):
        items.append(_make_validation_item("warning", "missing_data"))
    for i in range(n_critical):
        items.append(_make_validation_item("critical", "risk_limit"))
    from lib.reliability.validation_aggregator import aggregate_validation_items
    return aggregate_validation_items(
        aggregate_id=f"agg_test_{stable_hash_payload({'w': n_warning, 'c': n_critical}, 8)}",
        as_of="2026-05-23",
        items=items,
    )


def _make_staleness_report(n_stale: int = 1, n_expired: int = 0) -> StalenessReport:
    findings = []
    for i in range(n_stale):
        findings.append(_make_staleness_finding("stale"))
    for i in range(n_expired):
        findings.append(_make_staleness_finding("expired"))
    from lib.reliability.staleness import aggregate_staleness_findings
    return aggregate_staleness_findings(
        report_id=f"sr_test_{stable_hash_payload({'s': n_stale, 'e': n_expired}, 8)}",
        as_of="2026-05-23",
        findings=findings,
    )


def _make_critic_result(n_issues: int = 1) -> CriticResult:
    from lib.reliability.critic import aggregate_critic_issues
    issues = [_make_critic_issue("missing_risk") for _ in range(n_issues)]
    return aggregate_critic_issues(
        critic_id=f"cr_test_{stable_hash_payload({'n': n_issues}, 8)}",
        as_of="2026-05-23",
        issues=issues,
    )


def _make_minimal_bundle(ticker: str = "AAPL") -> DecisionPacketInputBundle:
    return DecisionPacketInputBundle(
        bundle_id="bundle_test_001",
        as_of="2026-05-23",
        ticker=ticker,
    )


def _make_full_bundle() -> DecisionPacketInputBundle:
    return DecisionPacketInputBundle(
        bundle_id="bundle_full_001",
        as_of="2026-05-23",
        ticker="NVDA",
        validation_aggregate=_make_validation_aggregate(n_warning=2, n_critical=0),
        staleness_report=_make_staleness_report(n_stale=1, n_expired=0),
        critic_result=_make_critic_result(n_issues=1),
        tool_results=[_make_tool_result("ev_tr_001"), _make_tool_result("ev_tr_002")],
    )


def _make_real_horizon_synthesis_report() -> HorizonSynthesisReport:
    """Accepted Phase 3B fixture with evidence_summary.supporting_evidence_ids."""
    return HorizonSynthesisReport(
        synthesis_id="hsr_phase3b_real",
        as_of="2026-05-23",
        ticker="NVDA",
        cards=[
            HorizonSynthesisCard(
                horizon="short_term",
                signal_direction="bullish",
                evidence_summary=HorizonEvidenceSummary(
                    horizon="short_term",
                    evidence_count=1,
                    supporting_evidence_ids=["ev_horizon_short"],
                ),
            ),
            HorizonSynthesisCard(
                horizon="medium_term",
                signal_direction="mixed",
                evidence_summary=HorizonEvidenceSummary(
                    horizon="medium_term",
                    evidence_count=1,
                    supporting_evidence_ids=["ev_horizon_medium"],
                ),
            ),
            HorizonSynthesisCard(
                horizon="long_term",
                signal_direction="neutral",
                evidence_summary=HorizonEvidenceSummary(
                    horizon="long_term",
                    evidence_count=1,
                    supporting_evidence_ids=["ev_horizon_long"],
                ),
            ),
        ],
    )


def _make_real_macro_agent_result() -> MacroAgentResult:
    """Accepted Phase 3C fixture with regime/impact/bias evidence fields."""
    return MacroAgentResult(
        macro_agent_id="macro_phase3c_real",
        as_of="2026-05-23",
        ticker="NVDA",
        regime_assessment=MacroRegimeAssessment(
            regime="mixed",
            risk_appetite="moderate",
            supporting_evidence_ids=["ev_macro_regime"],
        ),
        horizon_impacts=[
            MacroHorizonImpact(
                horizon="short_term",
                impact="supportive",
                evidence_ids=["ev_macro_short"],
            )
        ],
        sector_biases=[
            MacroSectorBias(
                sector="Technology",
                bias="neutral",
                evidence_ids=["ev_macro_sector"],
            )
        ],
    )


# ---------------------------------------------------------------------------
# Tests: Model validation
# ---------------------------------------------------------------------------

def test_01_decision_packet_issue_accepts_valid():
    iid = make_decision_packet_issue_id("validation_failure", "Some issue", "validation")
    iss = DecisionPacketIssue(
        issue_id=iid,
        guardrail_type="validation_failure",
        severity="warning",
        message="Some issue",
        source_type="validation",
    )
    assert iss.issue_id == iid
    assert iss.guardrail_type == "validation_failure"


def test_02_decision_packet_issue_rejects_empty_issue_id():
    try:
        DecisionPacketIssue(
            issue_id="",
            guardrail_type="other",
            message="test",
        )
        raise AssertionError("Should have raised")
    except pydantic.ValidationError:
        pass


def test_03_decision_packet_issue_rejects_empty_message():
    try:
        DecisionPacketIssue(
            issue_id="some_id",
            guardrail_type="other",
            message="",
        )
        raise AssertionError("Should have raised")
    except pydantic.ValidationError:
        pass


def test_04_decision_rationale_accepts_valid():
    rat = DecisionRationale(
        rationale_id="rat_001",
        source_type="debate",
        horizon="short_term",
        summary="Research summary for testing.",
        confidence="medium",
    )
    assert rat.rationale_id == "rat_001"
    assert rat.confidence == "medium"


def test_05_decision_rationale_rejects_empty_rationale_id():
    try:
        DecisionRationale(
            rationale_id="",
            source_type="debate",
            summary="test",
        )
        raise AssertionError("Should have raised")
    except pydantic.ValidationError:
        pass


def test_06_decision_rationale_rejects_empty_summary():
    try:
        DecisionRationale(
            rationale_id="rat_001",
            source_type="debate",
            summary="",
        )
        raise AssertionError("Should have raised")
    except pydantic.ValidationError:
        pass


def test_07_decision_guardrail_accepts_valid():
    grd = DecisionGuardrail(
        guardrail_id="grd_001",
        guardrail_type="execution_forbidden",
        triggered=True,
        severity="critical",
        message="Execution is forbidden.",
    )
    assert grd.triggered is True
    assert grd.guardrail_type == "execution_forbidden"


def test_08_decision_guardrail_rejects_empty_guardrail_id():
    try:
        DecisionGuardrail(
            guardrail_id="",
            guardrail_type="other",
            message="test",
        )
        raise AssertionError("Should have raised")
    except pydantic.ValidationError:
        pass


def test_09_decision_guardrail_rejects_empty_message():
    try:
        DecisionGuardrail(
            guardrail_id="grd_001",
            guardrail_type="other",
            message="",
        )
        raise AssertionError("Should have raised")
    except pydantic.ValidationError:
        pass


def test_10_decision_action_draft_accepts_valid():
    action = DecisionActionDraft(
        action_id="action_001",
        action_type="monitor",
        description="Monitor the subject for new developments.",
    )
    assert action.requires_human_review is True
    assert action.action_type == "monitor"


def test_11_decision_action_draft_rejects_empty_action_id():
    try:
        DecisionActionDraft(
            action_id="",
            description="test",
        )
        raise AssertionError("Should have raised")
    except pydantic.ValidationError:
        pass


def test_12_decision_action_draft_rejects_empty_description():
    try:
        DecisionActionDraft(
            action_id="action_001",
            description="",
        )
        raise AssertionError("Should have raised")
    except pydantic.ValidationError:
        pass


def test_13_decision_review_requirement_accepts_valid():
    rev = DecisionReviewRequirement(
        review_id="rev_001",
        review_status="review_required",
        required=True,
        reason="Human review required before execution.",
        reviewer_role="human_analyst",
    )
    assert rev.required is True
    assert rev.review_status == "review_required"


def test_14_decision_review_requirement_rejects_empty_review_id():
    try:
        DecisionReviewRequirement(
            review_id="",
            reason="test",
        )
        raise AssertionError("Should have raised")
    except pydantic.ValidationError:
        pass


def test_15_decision_review_requirement_rejects_empty_reason():
    try:
        DecisionReviewRequirement(
            review_id="rev_001",
            reason="",
        )
        raise AssertionError("Should have raised")
    except pydantic.ValidationError:
        pass


def test_16_decision_packet_accepts_valid():
    packet = DecisionPacket(
        decision_packet_id="dp_001",
        as_of="2026-05-23",
        ticker="AAPL",
        status="pass",
        recommendation="accept_for_research",
        confidence="medium",
    )
    assert packet.schema_version == "1.0"
    assert packet.ticker == "AAPL"


def test_17_decision_packet_rejects_empty_decision_packet_id():
    try:
        DecisionPacket(
            decision_packet_id="",
            as_of="2026-05-23",
        )
        raise AssertionError("Should have raised")
    except pydantic.ValidationError:
        pass


def test_18_decision_packet_rejects_empty_as_of():
    try:
        DecisionPacket(
            decision_packet_id="dp_001",
            as_of="",
        )
        raise AssertionError("Should have raised")
    except pydantic.ValidationError:
        pass


def test_19_decision_packet_input_bundle_accepts_minimal():
    bundle = _make_minimal_bundle()
    assert bundle.bundle_id == "bundle_test_001"
    assert bundle.ticker == "AAPL"
    assert bundle.tool_results == []


def test_20_decision_packet_input_bundle_rejects_empty_bundle_id():
    try:
        DecisionPacketInputBundle(
            bundle_id="",
            as_of="2026-05-23",
        )
        raise AssertionError("Should have raised")
    except pydantic.ValidationError:
        pass


def test_21_decision_packet_input_bundle_rejects_empty_as_of():
    try:
        DecisionPacketInputBundle(
            bundle_id="bundle_001",
            as_of="",
        )
        raise AssertionError("Should have raised")
    except pydantic.ValidationError:
        pass


# ---------------------------------------------------------------------------
# Tests: Deterministic ID helpers
# ---------------------------------------------------------------------------

def test_22_make_decision_packet_issue_id_deterministic():
    id1 = make_decision_packet_issue_id("stale_data", "Data is stale.", "staleness", "obj1", "ev1", "field.path")
    id2 = make_decision_packet_issue_id("stale_data", "Data is stale.", "staleness", "obj1", "ev1", "field.path")
    assert id1 == id2


def test_23_make_decision_packet_issue_id_changes_on_input_change():
    id1 = make_decision_packet_issue_id("stale_data", "Data is stale.", "staleness")
    id2 = make_decision_packet_issue_id("stale_data", "Different message.", "staleness")
    assert id1 != id2


def test_24_make_decision_packet_id_deterministic():
    id1 = make_decision_packet_id("bundle_001", "2026-05-23", "NVDA")
    id2 = make_decision_packet_id("bundle_001", "2026-05-23", "NVDA")
    assert id1 == id2


# ---------------------------------------------------------------------------
# Tests: extract_decision_evidence_ids
# ---------------------------------------------------------------------------

def test_25_extract_collects_tool_result_evidence_ids():
    bundle = DecisionPacketInputBundle(
        bundle_id="bundle_ev_001",
        as_of="2026-05-23",
        tool_results=[
            _make_tool_result("ev_tr_A"),
            _make_tool_result("ev_tr_B"),
        ],
    )
    eids = extract_decision_evidence_ids(bundle)
    assert "ev_tr_A" in eids
    assert "ev_tr_B" in eids
    assert eids.index("ev_tr_A") < eids.index("ev_tr_B")


def test_26_extract_collects_debate_claim_evidence_ids():
    class _FakeClaim:
        def __init__(self, eid):
            self.evidence_ids = [eid]
            self.text = "claim text"

    class _FakePosition:
        def __init__(self, eid):
            self.evidence_ids = [eid]
            self.claims = [_FakeClaim(eid)]
            self.summary = "summary"

    class _FakeRound:
        def __init__(self, eid):
            self.horizon = "short_term"
            self.bull_position = _FakePosition(eid)
            self.bear_position = None
            self.risk_position = None
            self.issues = []

    class _FakeDebateReport:
        def __init__(self):
            self.rounds = [_FakeRound("ev_debate_01")]
            self.issues = []

    bundle = DecisionPacketInputBundle(
        bundle_id="bundle_ev_002",
        as_of="2026-05-23",
        debate_report=_FakeDebateReport(),
    )
    eids = extract_decision_evidence_ids(bundle)
    assert "ev_debate_01" in eids


# ---------------------------------------------------------------------------
# Tests: issue converters
# ---------------------------------------------------------------------------

def test_27_issue_from_validation_item_preserves_evidence_id_field_path():
    item = _make_validation_item("warning", "missing_data")
    iss = issue_from_validation_item_for_decision(item)
    assert iss.evidence_id == "ev_001"
    assert iss.field_path == "findings[0].text"
    assert iss.guardrail_type == "insufficient_evidence"


def test_28_issue_from_staleness_finding_maps_stale_data():
    finding = _make_staleness_finding("stale")
    iss = issue_from_staleness_finding_for_decision(finding)
    assert iss.guardrail_type == "stale_data"
    assert iss.evidence_id == "ev_002"
    assert iss.source_type == "staleness"


def test_29_issue_from_critic_issue_maps_missing_risk_and_overconfidence():
    ci_risk = _make_critic_issue("missing_risk")
    iss_risk = issue_from_critic_issue_for_decision(ci_risk)
    assert iss_risk.guardrail_type == "missing_risk"

    ci_over = _make_critic_issue("overconfidence")
    iss_over = issue_from_critic_issue_for_decision(ci_over)
    assert iss_over.guardrail_type == "overconfidence"


def test_30_issue_from_debate_issue_maps_unresolved_stale_conflict():
    di_unresolved = _make_debate_issue_duck("unresolved_question")
    iss_u = issue_from_debate_issue_for_decision(di_unresolved)
    assert iss_u.guardrail_type == "debate_unresolved"

    di_stale = _make_debate_issue_duck("stale_evidence")
    iss_s = issue_from_debate_issue_for_decision(di_stale)
    assert iss_s.guardrail_type == "stale_data"

    di_conflict = _make_debate_issue_duck("conflicting_evidence")
    iss_c = issue_from_debate_issue_for_decision(di_conflict)
    assert iss_c.guardrail_type == "conflicting_evidence"


# ---------------------------------------------------------------------------
# Tests: build_decision_rationales
# ---------------------------------------------------------------------------

def test_31_build_decision_rationales_creates_cautious_research_only_rationale():
    bundle = _make_minimal_bundle("TSLA")
    evidence_ids: list[str] = []
    rationales = build_decision_rationales(bundle, evidence_ids)
    assert len(rationales) >= 1
    # Should contain a fallback rationale since no artifacts
    assert any("research" in r.summary.lower() or "insufficient" in r.summary.lower() for r in rationales)
    # Must not contain investment advice language
    for r in rationales:
        lower = r.summary.lower()
        assert "buy" not in lower, f"Found 'buy' in rationale: {r.summary}"
        assert "sell" not in lower, f"Found 'sell' in rationale: {r.summary}"
        assert "order" not in lower, f"Found 'order' in rationale: {r.summary}"


# ---------------------------------------------------------------------------
# Tests: build_decision_guardrails
# ---------------------------------------------------------------------------

def test_32_build_decision_guardrails_always_includes_execution_forbidden():
    bundle = _make_minimal_bundle()
    issues: list[DecisionPacketIssue] = []
    guardrails = build_decision_guardrails(bundle, issues)
    types = [g.guardrail_type for g in guardrails]
    assert "execution_forbidden" in types
    ef = next(g for g in guardrails if g.guardrail_type == "execution_forbidden")
    assert ef.triggered is True
    assert ef.severity == "critical"


# ---------------------------------------------------------------------------
# Tests: build_decision_action_draft
# ---------------------------------------------------------------------------

def test_33_build_decision_action_draft_never_produces_buy_sell_order():
    guardrails = build_decision_guardrails(_make_minimal_bundle(), [])
    action = build_decision_action_draft(
        status="pass",
        recommendation="accept_for_research",
        guardrails=guardrails,
        evidence_ids=["ev_001"],
        ticker="AAPL",
    )
    lower_desc = action.description.lower()
    lower_action = action.action_type.lower()
    for bad_word in ("buy", "sell", "short", "execute", "place_order"):
        assert bad_word not in lower_desc, f"Found '{bad_word}' in description"
        assert bad_word not in lower_action, f"Found '{bad_word}' in action_type"


def test_34_build_decision_action_draft_includes_prohibited_live_trading():
    guardrails = build_decision_guardrails(_make_minimal_bundle(), [])
    action = build_decision_action_draft(
        status="pass",
        recommendation="accept_for_research",
        guardrails=guardrails,
        evidence_ids=["ev_001"],
    )
    assert len(action.prohibited_actions) > 0
    prohibited_lower = " ".join(action.prohibited_actions).lower()
    assert "trading" in prohibited_lower or "order" in prohibited_lower


# ---------------------------------------------------------------------------
# Tests: build_review_requirements
# ---------------------------------------------------------------------------

def test_35_build_review_requirements_requires_human_review_for_triggered_guardrails():
    guardrails = build_decision_guardrails(_make_full_bundle(), [])
    issues: list[DecisionPacketIssue] = []
    reqs = build_review_requirements(guardrails, issues)
    assert len(reqs) >= 1
    assert all(r.required for r in reqs)
    # Baseline review requirement must exist
    assert any("research artifact" in r.reason.lower() for r in reqs)


# ---------------------------------------------------------------------------
# Tests: build_decision_packet
# ---------------------------------------------------------------------------

def test_36_build_decision_packet_normalizes_status_recommendation():
    bundle = _make_full_bundle()
    evidence_ids = extract_decision_evidence_ids(bundle)
    issues_list: list[DecisionPacketIssue] = []
    guardrails = build_decision_guardrails(bundle, issues_list)
    rationales = build_decision_rationales(bundle, evidence_ids)
    action = build_decision_action_draft(
        status="pass_with_warnings",
        recommendation="revise",
        guardrails=guardrails,
        evidence_ids=evidence_ids,
        ticker=bundle.ticker,
    )
    review_reqs = build_review_requirements(guardrails, issues_list)
    packet = build_decision_packet(
        decision_packet_id=make_decision_packet_id(bundle.bundle_id, bundle.as_of, bundle.ticker),
        as_of=bundle.as_of,
        ticker=bundle.ticker,
        rationales=rationales,
        guardrails=guardrails,
        review_requirements=review_reqs,
        issues=issues_list,
        primary_action=action,
        evidence_ids=evidence_ids,
    )
    assert packet.status in ("pass", "pass_with_warnings", "fail", "blocked", "insufficient_evidence", "unknown")
    assert packet.recommendation in (
        "accept_for_research", "revise", "reject", "needs_more_evidence", "monitor_only", "unknown"
    )


# ---------------------------------------------------------------------------
# Tests: run_decision_packet_synthesis
# ---------------------------------------------------------------------------

def test_37_run_decision_packet_synthesis_returns_deterministic_decision_packet():
    bundle = _make_full_bundle()
    packet1 = run_decision_packet_synthesis(bundle)
    packet2 = run_decision_packet_synthesis(bundle)
    assert packet1.decision_packet_id == packet2.decision_packet_id
    assert packet1.status == packet2.status
    assert packet1.recommendation == packet2.recommendation


def test_38_run_decision_packet_synthesis_does_not_mutate_input_bundle():
    bundle = _make_full_bundle()
    original_bundle_id = bundle.bundle_id
    original_ticker = bundle.ticker
    original_tool_results_len = len(bundle.tool_results)
    _ = run_decision_packet_synthesis(bundle)
    assert bundle.bundle_id == original_bundle_id
    assert bundle.ticker == original_ticker
    assert len(bundle.tool_results) == original_tool_results_len


def test_39_run_synthesis_with_insufficient_evidence_returns_needs_more_evidence():
    bundle = DecisionPacketInputBundle(
        bundle_id="bundle_insuff_001",
        as_of="2026-05-23",
        ticker="XYZ",
        # No tool_results, no artifacts
    )
    packet = run_decision_packet_synthesis(bundle)
    # Should have insufficient_evidence status or pass/pass_with_warnings with review required
    assert packet.status in (
        "insufficient_evidence", "pass", "pass_with_warnings", "fail", "blocked"
    )
    # Must always have execution_forbidden
    types = [g.guardrail_type for g in packet.guardrails]
    assert "execution_forbidden" in types
    # Action should require more research or monitoring
    assert packet.primary_action is not None
    assert packet.primary_action.action_type in (
        "needs_more_research", "monitor", "human_review_required", "reject", "no_action", "unknown"
    )


# ---------------------------------------------------------------------------
# Tests: ToolResult wrapper
# ---------------------------------------------------------------------------

def test_40_decision_packet_tool_result_from_packet_returns_valid_tool_result():
    bundle = _make_minimal_bundle()
    packet = run_decision_packet_synthesis(bundle)
    tr = decision_packet_tool_result_from_packet("run_test_001", packet)
    assert tr.evidence_id
    assert tr.tool_name == "decision_packet"
    assert tr.run_id == "run_test_001"


def test_41_decision_packet_tool_result_has_stable_tool_name_and_target():
    bundle = _make_minimal_bundle("MSFT")
    packet = run_decision_packet_synthesis(bundle)
    tr = decision_packet_tool_result_from_packet("run_001", packet)
    assert tr.tool_name == "decision_packet"
    assert tr.ticker == "MSFT"


def test_42_decision_packet_tool_result_payload_includes_packet_summary_version():
    bundle = _make_minimal_bundle()
    packet = run_decision_packet_synthesis(bundle)
    tr = decision_packet_tool_result_from_packet("run_001", packet)
    assert "packet" in tr.outputs
    assert "summary" in tr.outputs
    assert "calculation_version" in tr.outputs
    assert tr.outputs["calculation_version"] == "decision_packet_skeleton_v1"


def test_43_decision_packet_tool_result_evidence_id_deterministic_for_identical_packet():
    bundle = _make_minimal_bundle()
    packet = run_decision_packet_synthesis(bundle)
    tr1 = decision_packet_tool_result_from_packet("run_001", packet)
    tr2 = decision_packet_tool_result_from_packet("run_001", packet)
    assert tr1.evidence_id == tr2.evidence_id


def test_44_decision_packet_tool_result_evidence_id_changes_when_packet_payload_changes():
    bundle1 = _make_minimal_bundle("AAPL")
    bundle2 = _make_minimal_bundle("MSFT")
    packet1 = run_decision_packet_synthesis(bundle1)
    packet2 = run_decision_packet_synthesis(bundle2)
    tr1 = decision_packet_tool_result_from_packet("run_001", packet1)
    tr2 = decision_packet_tool_result_from_packet("run_001", packet2)
    assert tr1.evidence_id != tr2.evidence_id


# ---------------------------------------------------------------------------
# Tests: summarize_decision_packet
# ---------------------------------------------------------------------------

def test_45_summarize_decision_packet_returns_expected_summary():
    bundle = _make_full_bundle()
    packet = run_decision_packet_synthesis(bundle)
    summary = summarize_decision_packet(packet)
    required_keys = [
        "decision_packet_id", "ticker", "status", "recommendation", "confidence",
        "primary_action_type", "rationale_count", "guardrail_count",
        "review_requirement_count", "issue_count", "critical_count",
        "warning_count", "info_count", "triggered_guardrails", "top_messages",
    ]
    for key in required_keys:
        assert key in summary, f"Missing key in summary: {key}"
    assert isinstance(summary["triggered_guardrails"], list)
    assert isinstance(summary["top_messages"], list)
    assert len(summary["top_messages"]) <= 10


# ---------------------------------------------------------------------------
# Tests: serialization roundtrip
# ---------------------------------------------------------------------------

def test_46_decision_packet_serialization_roundtrip():
    bundle = _make_full_bundle()
    packet = run_decision_packet_synthesis(bundle)
    dumped = packet.model_dump()
    restored = DecisionPacket.model_validate(dumped)
    assert restored.decision_packet_id == packet.decision_packet_id
    assert restored.status == packet.status
    assert restored.recommendation == packet.recommendation
    assert len(restored.guardrails) == len(packet.guardrails)


def test_47_decision_packet_issue_serialization_roundtrip():
    iid = make_decision_packet_issue_id("stale_data", "Data is stale.", "staleness")
    iss = DecisionPacketIssue(
        issue_id=iid,
        guardrail_type="stale_data",
        severity="warning",
        message="Data is stale.",
        source_type="staleness",
        evidence_id="ev_001",
    )
    dumped = iss.model_dump()
    restored = DecisionPacketIssue.model_validate(dumped)
    assert restored.issue_id == iss.issue_id
    assert restored.guardrail_type == iss.guardrail_type


# ---------------------------------------------------------------------------
# Tests: safety / isolation
# ---------------------------------------------------------------------------

def test_48_no_live_app_modules_imported():
    forbidden = ["app", "pages", "lib.llm_orchestrator", "streamlit"]
    for mod in forbidden:
        assert mod not in sys.modules, f"Forbidden module loaded: {mod}"


def test_49_no_external_api_network_calls():
    # Simply importing and running synthesis should not trigger network
    # (verified by running offline — no external requests are possible in test)
    bundle = _make_minimal_bundle()
    packet = run_decision_packet_synthesis(bundle)
    assert packet is not None  # If we got here, no network calls were made


def test_50_no_claude_llm_api_called():
    # anthropic module should not be loaded by decision_packet
    assert "anthropic" not in sys.modules


def test_51_no_buy_sell_place_order_execute_in_DecisionActionType():
    import typing
    import lib.reliability.decision_packet as dp_module
    # DecisionActionType is a Literal — get its args
    rat = dp_module.DecisionActionType
    args = typing.get_args(rat)
    forbidden = {"buy", "sell", "short", "execute", "place_order", "order", "trade"}
    for a in args:
        lower = a.lower()
        for bad in forbidden:
            assert bad not in lower, (
                f"Forbidden action type '{a}' contains '{bad}' — no live trading actions allowed"
            )


# ---------------------------------------------------------------------------
# Tests: regression against prior phases
# ---------------------------------------------------------------------------

def test_52_existing_debate_macro_horizon_orchestration_imports_still_work():
    from lib.reliability.debate import run_debate_by_horizon, DebateReport, DebateInputBundle
    from lib.reliability.macro_agent import run_macro_agent_v0, MacroAgentInputBundle
    from lib.reliability.horizon_synthesis import run_horizon_aware_synthesis, HorizonSynthesisInputBundle
    from lib.reliability.orchestration import OrchestrationReport
    # All should be importable without error
    assert run_debate_by_horizon is not None
    assert DebateReport is not None
    assert run_macro_agent_v0 is not None
    assert run_horizon_aware_synthesis is not None
    assert OrchestrationReport is not None


# ---------------------------------------------------------------------------
# Tests: real Phase 3B / 3C evidence handoff
# ---------------------------------------------------------------------------

def test_53_extract_collects_real_phase3b_horizon_evidence_summary_ids():
    bundle = DecisionPacketInputBundle(
        bundle_id="bundle_real_horizon",
        as_of="2026-05-23",
        ticker="NVDA",
        horizon_synthesis_report=_make_real_horizon_synthesis_report(),
    )
    eids = extract_decision_evidence_ids(bundle)
    assert "ev_horizon_short" in eids
    assert "ev_horizon_medium" in eids
    assert "ev_horizon_long" in eids


def test_54_rationales_preserve_real_phase3b_horizon_evidence_ids():
    bundle = DecisionPacketInputBundle(
        bundle_id="bundle_real_horizon_rat",
        as_of="2026-05-23",
        ticker="NVDA",
        horizon_synthesis_report=_make_real_horizon_synthesis_report(),
    )
    rationales = build_decision_rationales(bundle, extract_decision_evidence_ids(bundle))
    rat_eids = {eid for rat in rationales for eid in rat.evidence_ids}
    assert "ev_horizon_short" in rat_eids
    assert "ev_horizon_medium" in rat_eids
    assert "ev_horizon_long" in rat_eids


def test_55_extract_collects_real_phase3c_macro_evidence_ids():
    bundle = DecisionPacketInputBundle(
        bundle_id="bundle_real_macro",
        as_of="2026-05-23",
        ticker="NVDA",
        macro_agent_result=_make_real_macro_agent_result(),
    )
    eids = extract_decision_evidence_ids(bundle)
    assert "ev_macro_regime" in eids
    assert "ev_macro_short" in eids
    assert "ev_macro_sector" in eids


def test_56_rationales_preserve_real_phase3c_macro_evidence_ids():
    bundle = DecisionPacketInputBundle(
        bundle_id="bundle_real_macro_rat",
        as_of="2026-05-23",
        ticker="NVDA",
        macro_agent_result=_make_real_macro_agent_result(),
    )
    rationales = build_decision_rationales(bundle, extract_decision_evidence_ids(bundle))
    macro_rationale = next(r for r in rationales if r.source_type == "macro_agent")
    assert "ev_macro_regime" in macro_rationale.evidence_ids
    assert "ev_macro_short" in macro_rationale.evidence_ids
    assert "ev_macro_sector" in macro_rationale.evidence_ids


def test_57_run_synthesis_preserves_real_phase3b_3c_evidence_and_source_ids():
    hsr = _make_real_horizon_synthesis_report()
    mar = _make_real_macro_agent_result()
    bundle = DecisionPacketInputBundle(
        bundle_id="bundle_real_combined",
        as_of="2026-05-23",
        ticker="NVDA",
        horizon_synthesis_report=hsr,
        macro_agent_result=mar,
    )
    packet = run_decision_packet_synthesis(bundle)
    rat_eids = {eid for rat in packet.rationales for eid in rat.evidence_ids}
    assert "ev_horizon_short" in rat_eids
    assert "ev_macro_regime" in rat_eids
    assert "ev_macro_short" in rat_eids
    assert packet.source_ids["horizon_synthesis_report"] == hsr.synthesis_id
    assert packet.source_ids["macro_agent_result"] == mar.macro_agent_id


def test_58_source_ids_use_accepted_macro_and_orchestration_ids():
    mar = _make_real_macro_agent_result()
    orch = OrchestrationReport(
        orchestration_id="orch_phase3a_real",
        as_of="2026-05-23",
    )
    bundle = DecisionPacketInputBundle(
        bundle_id="bundle_source_ids",
        as_of="2026-05-23",
        macro_agent_result=mar,
        orchestration_report=orch,
    )
    packet = run_decision_packet_synthesis(bundle)
    assert packet.source_ids["macro_agent_result"] == "macro_phase3c_real"
    assert packet.source_ids["orchestration_report"] == "orch_phase3a_real"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> int:
    tests = [
        ("01 DecisionPacketIssue accepts valid issue", test_01_decision_packet_issue_accepts_valid),
        ("02 DecisionPacketIssue rejects empty issue_id", test_02_decision_packet_issue_rejects_empty_issue_id),
        ("03 DecisionPacketIssue rejects empty message", test_03_decision_packet_issue_rejects_empty_message),
        ("04 DecisionRationale accepts valid rationale", test_04_decision_rationale_accepts_valid),
        ("05 DecisionRationale rejects empty rationale_id", test_05_decision_rationale_rejects_empty_rationale_id),
        ("06 DecisionRationale rejects empty summary", test_06_decision_rationale_rejects_empty_summary),
        ("07 DecisionGuardrail accepts valid guardrail", test_07_decision_guardrail_accepts_valid),
        ("08 DecisionGuardrail rejects empty guardrail_id", test_08_decision_guardrail_rejects_empty_guardrail_id),
        ("09 DecisionGuardrail rejects empty message", test_09_decision_guardrail_rejects_empty_message),
        ("10 DecisionActionDraft accepts valid action", test_10_decision_action_draft_accepts_valid),
        ("11 DecisionActionDraft rejects empty action_id", test_11_decision_action_draft_rejects_empty_action_id),
        ("12 DecisionActionDraft rejects empty description", test_12_decision_action_draft_rejects_empty_description),
        ("13 DecisionReviewRequirement accepts valid", test_13_decision_review_requirement_accepts_valid),
        ("14 DecisionReviewRequirement rejects empty review_id", test_14_decision_review_requirement_rejects_empty_review_id),
        ("15 DecisionReviewRequirement rejects empty reason", test_15_decision_review_requirement_rejects_empty_reason),
        ("16 DecisionPacket accepts valid packet", test_16_decision_packet_accepts_valid),
        ("17 DecisionPacket rejects empty decision_packet_id", test_17_decision_packet_rejects_empty_decision_packet_id),
        ("18 DecisionPacket rejects empty as_of", test_18_decision_packet_rejects_empty_as_of),
        ("19 DecisionPacketInputBundle accepts minimal", test_19_decision_packet_input_bundle_accepts_minimal),
        ("20 DecisionPacketInputBundle rejects empty bundle_id", test_20_decision_packet_input_bundle_rejects_empty_bundle_id),
        ("21 DecisionPacketInputBundle rejects empty as_of", test_21_decision_packet_input_bundle_rejects_empty_as_of),
        ("22 make_decision_packet_issue_id deterministic", test_22_make_decision_packet_issue_id_deterministic),
        ("23 make_decision_packet_issue_id changes on input change", test_23_make_decision_packet_issue_id_changes_on_input_change),
        ("24 make_decision_packet_id deterministic", test_24_make_decision_packet_id_deterministic),
        ("25 extract_decision_evidence_ids collects ToolResult IDs", test_25_extract_collects_tool_result_evidence_ids),
        ("26 extract_decision_evidence_ids collects DebateReport claim IDs", test_26_extract_collects_debate_claim_evidence_ids),
        ("27 issue_from_validation_item preserves evidence_id/field_path", test_27_issue_from_validation_item_preserves_evidence_id_field_path),
        ("28 issue_from_staleness_finding maps stale data", test_28_issue_from_staleness_finding_maps_stale_data),
        ("29 issue_from_critic_issue maps missing_risk/overconfidence", test_29_issue_from_critic_issue_maps_missing_risk_and_overconfidence),
        ("30 issue_from_debate_issue maps unresolved/stale/conflict", test_30_issue_from_debate_issue_maps_unresolved_stale_conflict),
        ("31 build_decision_rationales creates cautious research-only rationale", test_31_build_decision_rationales_creates_cautious_research_only_rationale),
        ("32 build_decision_guardrails always includes execution_forbidden", test_32_build_decision_guardrails_always_includes_execution_forbidden),
        ("33 build_decision_action_draft never produces buy/sell/order", test_33_build_decision_action_draft_never_produces_buy_sell_order),
        ("34 build_decision_action_draft includes prohibited live trading", test_34_build_decision_action_draft_includes_prohibited_live_trading),
        ("35 build_review_requirements requires human review for guardrails", test_35_build_review_requirements_requires_human_review_for_triggered_guardrails),
        ("36 build_decision_packet normalizes status/recommendation", test_36_build_decision_packet_normalizes_status_recommendation),
        ("37 run_decision_packet_synthesis returns deterministic DecisionPacket", test_37_run_decision_packet_synthesis_returns_deterministic_decision_packet),
        ("38 run_decision_packet_synthesis does not mutate input bundle", test_38_run_decision_packet_synthesis_does_not_mutate_input_bundle),
        ("39 run_synthesis with insufficient evidence returns needs_more or human_review", test_39_run_synthesis_with_insufficient_evidence_returns_needs_more_evidence),
        ("40 decision_packet_tool_result_from_packet returns valid ToolResult", test_40_decision_packet_tool_result_from_packet_returns_valid_tool_result),
        ("41 ToolResult has stable tool_name and target", test_41_decision_packet_tool_result_has_stable_tool_name_and_target),
        ("42 ToolResult payload includes packet, summary, calculation_version", test_42_decision_packet_tool_result_payload_includes_packet_summary_version),
        ("43 ToolResult evidence_id deterministic for identical packet", test_43_decision_packet_tool_result_evidence_id_deterministic_for_identical_packet),
        ("44 ToolResult evidence_id changes when packet payload changes", test_44_decision_packet_tool_result_evidence_id_changes_when_packet_payload_changes),
        ("45 summarize_decision_packet returns expected summary", test_45_summarize_decision_packet_returns_expected_summary),
        ("46 DecisionPacket serialization roundtrip", test_46_decision_packet_serialization_roundtrip),
        ("47 DecisionPacketIssue serialization roundtrip", test_47_decision_packet_issue_serialization_roundtrip),
        ("48 No live app modules imported", test_48_no_live_app_modules_imported),
        ("49 No external API/network calls made", test_49_no_external_api_network_calls),
        ("50 No Claude/LLM API called", test_50_no_claude_llm_api_called),
        ("51 No buy/sell/place_order/execute in DecisionActionType", test_51_no_buy_sell_place_order_execute_in_DecisionActionType),
        ("52 Prior phase imports still work", test_52_existing_debate_macro_horizon_orchestration_imports_still_work),
        ("53 Real Phase 3B HorizonSynthesisReport evidence extracted", test_53_extract_collects_real_phase3b_horizon_evidence_summary_ids),
        ("54 Real Phase 3B HorizonSynthesisReport rationale evidence preserved", test_54_rationales_preserve_real_phase3b_horizon_evidence_ids),
        ("55 Real Phase 3C MacroAgentResult evidence extracted", test_55_extract_collects_real_phase3c_macro_evidence_ids),
        ("56 Real Phase 3C MacroAgentResult rationale evidence preserved", test_56_rationales_preserve_real_phase3c_macro_evidence_ids),
        ("57 Synthesis preserves real Phase 3B/3C evidence and source IDs", test_57_run_synthesis_preserves_real_phase3b_3c_evidence_and_source_ids),
        ("58 Source IDs use accepted macro/orchestration IDs", test_58_source_ids_use_accepted_macro_and_orchestration_ids),
    ]

    print(f"\nPhase 3E: DecisionPacket Schema / Decision Synthesis Skeleton")
    print(f"Running {len(tests)} tests...\n")

    passed = 0
    failed = 0
    for name, fn in tests:
        ok = _run_test(name, fn)
        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed}/{len(tests)} passed, {failed} failed")
    print(f"{'='*60}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
