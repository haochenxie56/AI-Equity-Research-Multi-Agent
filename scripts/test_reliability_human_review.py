"""
scripts/test_reliability_human_review.py

Phase 3F: Human Review / Feedback Schema Skeleton — test suite.

Tests cover:
  - All Pydantic model construction, validation, and rejection.
  - Deterministic ID generators.
  - Feedback converters from DecisionPacketIssue, ValidationItem,
    StalenessFinding, CriticIssue.
  - collect_human_feedback, build_revision_requests, build_review_items.
  - determine_human_review_outcome: blocks on critical, revises on warnings,
    approves research-only on clean inputs.
  - build_human_review_report normalization.
  - run_human_review_skeleton: deterministic, no mutation, correct approval logic.
  - human_review_tool_result_from_report: stable tool_name, target, payload,
    deterministic evidence_id.
  - summarize_human_review_report.
  - Serialization roundtrips.
  - Guards: no live app modules imported, no external calls, no LLM calls,
    approved_for_execution always False.
  - Regression: run prior phase test scripts.

Usage:
    python3 scripts/test_reliability_human_review.py
"""

import sys
import os

# Add repo root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import copy
import json
import subprocess
from datetime import datetime, timezone
from typing import Any

import pydantic

from lib.reliability.human_review import (
    HumanFeedbackItem,
    HumanFeedbackSeverity,
    HumanFeedbackType,
    HumanRevisionRequest,
    HumanReviewDecision,
    HumanReviewInputBundle,
    HumanReviewItem,
    HumanReviewOutcome,
    HumanReviewReport,
    HumanReviewRecommendation,
    HumanReviewSourceType,
    HumanReviewStatus,
    HumanReviewerRole,
    HumanReviewRecommendation,
    build_human_review_report,
    build_review_items,
    build_revision_requests,
    collect_human_feedback,
    determine_human_review_outcome,
    feedback_from_critic_issue,
    feedback_from_decision_packet_issue,
    feedback_from_staleness_finding,
    feedback_from_validation_item,
    human_review_tool_result_from_report,
    make_human_feedback_id,
    make_human_review_report_id,
    run_human_review_skeleton,
    summarize_human_review_report,
)
from lib.reliability.critic import CriticIssue, CriticResult, run_mock_critic
from lib.reliability.staleness import (
    StalenessFinding,
    StalenessReport,
    aggregate_staleness_findings,
)
from lib.reliability.validation_aggregator import (
    AggregatedValidationItem,
    ValidationAggregate,
    aggregate_validation_items,
)
from lib.reliability.schemas import ToolResult
from lib.reliability.adapters import stable_hash_payload


_PASS = 0
_FAIL = 0
_TESTS: list[str] = []


def _ok(name: str) -> None:
    global _PASS
    _PASS += 1
    _TESTS.append(f"  PASS  {name}")


def _fail(name: str, reason: str) -> None:
    global _FAIL
    _FAIL += 1
    _TESTS.append(f"  FAIL  {name}: {reason}")


def _expect_error(name: str, fn, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
        _fail(name, "Expected ValidationError but none was raised")
    except pydantic.ValidationError:
        _ok(name)
    except Exception as e:
        _fail(name, f"Unexpected exception type {type(e).__name__}: {e}")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _make_feedback_item(
    feedback_id: str = "hf_test001",
    feedback_type: str = "evidence_gap",
    severity: str = "warning",
    message: str = "Test feedback message",
    source_type: str = "validation",
) -> HumanFeedbackItem:
    return HumanFeedbackItem(
        feedback_id=feedback_id,
        feedback_type=feedback_type,
        severity=severity,
        message=message,
        source_type=source_type,
    )


def _make_revision_request(
    revision_request_id: str = "rr_test001",
    reason: str = "Evidence gap detected.",
    blocked: bool = False,
) -> HumanRevisionRequest:
    return HumanRevisionRequest(
        revision_request_id=revision_request_id,
        reason=reason,
        blocked_until_resolved=blocked,
    )


def _make_review_item(
    review_item_id: str = "ri_test001",
    source_type: str = "decision_packet",
    summary: str = "Review item summary.",
) -> HumanReviewItem:
    return HumanReviewItem(
        review_item_id=review_item_id,
        source_type=source_type,
        summary=summary,
    )


def _make_outcome(
    outcome_id: str = "hro_test001",
    decision: str = "approve_for_research",
    status: str = "approved_for_research_only",
    recommendation: str = "accept_for_research",
    rationale: str = "Test rationale.",
    approved_for_research_only: bool = True,
    approved_for_execution: bool = False,
) -> HumanReviewOutcome:
    return HumanReviewOutcome(
        outcome_id=outcome_id,
        decision=decision,
        status=status,
        recommendation=recommendation,
        rationale=rationale,
        approved_for_research_only=approved_for_research_only,
        approved_for_execution=approved_for_execution,
    )


def _make_report(
    review_report_id: str = "hrr_test001",
    as_of: str = "2026-05-23",
) -> HumanReviewReport:
    return HumanReviewReport(
        review_report_id=review_report_id,
        as_of=as_of,
    )


def _make_bundle(
    bundle_id: str = "bundle_test001",
    as_of: str = "2026-05-23",
    ticker: str = "NVDA",
) -> HumanReviewInputBundle:
    return HumanReviewInputBundle(
        bundle_id=bundle_id,
        as_of=as_of,
        ticker=ticker,
    )


def _make_validation_item(
    item_id: str = "vi_test001",
    item_type: str = "evidence_binding",
    severity: str = "warning",
    message: str = "Validation issue.",
    evidence_id: str = "ev_abc",
    field_path: str = "findings[0].text",
    object_id: str = "obj_001",
) -> AggregatedValidationItem:
    return AggregatedValidationItem(
        item_id=item_id,
        domain="evidence",
        severity=severity,
        item_type=item_type,
        message=message,
        evidence_id=evidence_id,
        field_path=field_path,
        object_id=object_id,
    )


def _make_staleness_finding(
    finding_id: str = "sf_test001",
    status: str = "stale",
    severity: str = "warning",
    message: str = "Data is stale.",
    evidence_id: str = "ev_stale",
    field_path: str = "as_of",
    object_id: str = "obj_staleness",
) -> StalenessFinding:
    return StalenessFinding(
        finding_id=finding_id,
        domain="tool_result",
        status=status,
        severity=severity,
        message=message,
        as_of="2026-05-23",
        evidence_id=evidence_id,
        field_path=field_path,
        object_id=object_id,
    )


def _make_critic_issue(
    issue_id: str = "ci_test001",
    issue_type: str = "missing_risk",
    severity: str = "warning",
    message: str = "Missing risk identified.",
    evidence_id: str = "ev_critic",
    field_path: str = "risks",
) -> CriticIssue:
    return CriticIssue(
        issue_id=issue_id,
        issue_type=issue_type,
        severity=severity,
        message=message,
        evidence_id=evidence_id,
        field_path=field_path,
    )


def _make_dp_issue(
    issue_id: str = "dpi_test001",
    guardrail_type: str = "insufficient_evidence",
    severity: str = "warning",
    message: str = "Decision packet issue.",
    evidence_id: str = "ev_dp",
    field_path: str = "rationales[0]",
    related_id: str = "rat_001",
) -> Any:
    """Return a duck-typed DecisionPacketIssue-like object."""
    class _FakeIssue:
        pass
    obj = _FakeIssue()
    obj.issue_id = issue_id
    obj.guardrail_type = guardrail_type
    obj.severity = severity
    obj.message = message
    obj.evidence_id = evidence_id
    obj.field_path = field_path
    obj.related_id = related_id
    return obj


def _make_fake_dp(
    decision_packet_id: str = "dp_test001",
    issues: list = None,
    guardrails: list = None,
) -> Any:
    class _FakeDP:
        pass
    dp = _FakeDP()
    dp.decision_packet_id = decision_packet_id
    dp.issues = issues or []
    dp.guardrails = guardrails or []
    return dp


# ---------------------------------------------------------------------------
# Tests: HumanFeedbackItem
# ---------------------------------------------------------------------------

def test_human_feedback_item_valid():
    try:
        item = _make_feedback_item()
        assert item.feedback_id == "hf_test001"
        assert item.feedback_type == "evidence_gap"
        assert item.severity == "warning"
        _ok("01_HumanFeedbackItem accepts valid feedback")
    except Exception as e:
        _fail("01_HumanFeedbackItem accepts valid feedback", str(e))


def test_human_feedback_item_rejects_empty_id():
    _expect_error(
        "02_HumanFeedbackItem rejects empty feedback_id",
        HumanFeedbackItem,
        feedback_id="",
        feedback_type="evidence_gap",
        message="Some message",
        source_type="validation",
    )


def test_human_feedback_item_rejects_empty_message():
    _expect_error(
        "03_HumanFeedbackItem rejects empty message",
        HumanFeedbackItem,
        feedback_id="hf_001",
        feedback_type="evidence_gap",
        message="",
        source_type="validation",
    )


# ---------------------------------------------------------------------------
# Tests: HumanRevisionRequest
# ---------------------------------------------------------------------------

def test_revision_request_valid():
    try:
        rr = _make_revision_request()
        assert rr.revision_request_id == "rr_test001"
        assert rr.required is True
        _ok("04_HumanRevisionRequest accepts valid request")
    except Exception as e:
        _fail("04_HumanRevisionRequest accepts valid request", str(e))


def test_revision_request_rejects_empty_id():
    _expect_error(
        "05_HumanRevisionRequest rejects empty revision_request_id",
        HumanRevisionRequest,
        revision_request_id="",
        reason="Some reason",
    )


def test_revision_request_rejects_empty_reason():
    _expect_error(
        "06_HumanRevisionRequest rejects empty reason",
        HumanRevisionRequest,
        revision_request_id="rr_001",
        reason="",
    )


# ---------------------------------------------------------------------------
# Tests: HumanReviewItem
# ---------------------------------------------------------------------------

def test_review_item_valid():
    try:
        item = _make_review_item()
        assert item.review_item_id == "ri_test001"
        assert item.status == "pending"
        _ok("07_HumanReviewItem accepts valid item")
    except Exception as e:
        _fail("07_HumanReviewItem accepts valid item", str(e))


def test_review_item_rejects_empty_id():
    _expect_error(
        "08_HumanReviewItem rejects empty review_item_id",
        HumanReviewItem,
        review_item_id="",
        source_type="decision_packet",
        summary="Some summary",
    )


def test_review_item_rejects_empty_summary():
    _expect_error(
        "09_HumanReviewItem rejects empty summary",
        HumanReviewItem,
        review_item_id="ri_001",
        source_type="decision_packet",
        summary="",
    )


# ---------------------------------------------------------------------------
# Tests: HumanReviewOutcome
# ---------------------------------------------------------------------------

def test_review_outcome_valid():
    try:
        outcome = _make_outcome()
        assert outcome.outcome_id == "hro_test001"
        assert outcome.approved_for_execution is False
        assert outcome.approved_for_research_only is True
        _ok("10_HumanReviewOutcome accepts valid outcome")
    except Exception as e:
        _fail("10_HumanReviewOutcome accepts valid outcome", str(e))


def test_review_outcome_rejects_empty_id():
    _expect_error(
        "11_HumanReviewOutcome rejects empty outcome_id",
        HumanReviewOutcome,
        outcome_id="",
        rationale="Some rationale",
    )


def test_review_outcome_rejects_empty_rationale():
    _expect_error(
        "12_HumanReviewOutcome rejects empty rationale",
        HumanReviewOutcome,
        outcome_id="hro_001",
        rationale="",
    )


def test_review_outcome_cannot_approve_execution():
    _expect_error(
        "13_HumanReviewOutcome cannot approve execution",
        HumanReviewOutcome,
        outcome_id="hro_001",
        rationale="Some rationale",
        approved_for_execution=True,
    )


# ---------------------------------------------------------------------------
# Tests: HumanReviewReport
# ---------------------------------------------------------------------------

def test_review_report_valid():
    try:
        report = _make_report()
        assert report.review_report_id == "hrr_test001"
        assert report.as_of == "2026-05-23"
        _ok("14_HumanReviewReport accepts valid report")
    except Exception as e:
        _fail("14_HumanReviewReport accepts valid report", str(e))


def test_review_report_rejects_empty_id():
    _expect_error(
        "15_HumanReviewReport rejects empty review_report_id",
        HumanReviewReport,
        review_report_id="",
        as_of="2026-05-23",
    )


def test_review_report_rejects_empty_as_of():
    _expect_error(
        "16_HumanReviewReport rejects empty as_of",
        HumanReviewReport,
        review_report_id="hrr_001",
        as_of="",
    )


# ---------------------------------------------------------------------------
# Tests: HumanReviewInputBundle
# ---------------------------------------------------------------------------

def test_input_bundle_minimal():
    try:
        bundle = _make_bundle()
        assert bundle.bundle_id == "bundle_test001"
        assert bundle.ticker == "NVDA"
        assert bundle.manual_feedback == []
        _ok("17_HumanReviewInputBundle accepts minimal bundle")
    except Exception as e:
        _fail("17_HumanReviewInputBundle accepts minimal bundle", str(e))


def test_input_bundle_rejects_empty_bundle_id():
    _expect_error(
        "18_HumanReviewInputBundle rejects empty bundle_id",
        HumanReviewInputBundle,
        bundle_id="",
        as_of="2026-05-23",
    )


def test_input_bundle_rejects_empty_as_of():
    _expect_error(
        "19_HumanReviewInputBundle rejects empty as_of",
        HumanReviewInputBundle,
        bundle_id="bundle_001",
        as_of="",
    )


# ---------------------------------------------------------------------------
# Tests: make_human_feedback_id
# ---------------------------------------------------------------------------

def test_feedback_id_deterministic():
    try:
        id1 = make_human_feedback_id("evidence_gap", "Test message", "validation")
        id2 = make_human_feedback_id("evidence_gap", "Test message", "validation")
        assert id1 == id2, f"Expected same ID, got {id1!r} vs {id2!r}"
        assert id1.startswith("hf_")
        _ok("20_make_human_feedback_id deterministic")
    except Exception as e:
        _fail("20_make_human_feedback_id deterministic", str(e))


def test_feedback_id_changes_on_input_change():
    try:
        id1 = make_human_feedback_id("evidence_gap", "Message A", "validation")
        id2 = make_human_feedback_id("evidence_gap", "Message B", "validation")
        id3 = make_human_feedback_id("stale_data", "Message A", "validation")
        id4 = make_human_feedback_id("evidence_gap", "Message A", "staleness")
        assert id1 != id2, "IDs should differ when message changes"
        assert id1 != id3, "IDs should differ when type changes"
        assert id1 != id4, "IDs should differ when source_type changes"
        _ok("21_make_human_feedback_id changes when inputs change")
    except Exception as e:
        _fail("21_make_human_feedback_id changes when inputs change", str(e))


# ---------------------------------------------------------------------------
# Tests: make_human_review_report_id
# ---------------------------------------------------------------------------

def test_review_report_id_deterministic():
    try:
        id1 = make_human_review_report_id("bundle_001", "2026-05-23", "NVDA")
        id2 = make_human_review_report_id("bundle_001", "2026-05-23", "NVDA")
        assert id1 == id2
        assert id1.startswith("hrr_")
        _ok("22_make_human_review_report_id deterministic")
    except Exception as e:
        _fail("22_make_human_review_report_id deterministic", str(e))


# ---------------------------------------------------------------------------
# Tests: feedback_from_decision_packet_issue
# ---------------------------------------------------------------------------

def test_feedback_from_dp_issue_preserves_fields():
    try:
        issue = _make_dp_issue(
            guardrail_type="insufficient_evidence",
            severity="critical",
            message="Evidence missing for claim X.",
            evidence_id="ev_001",
            field_path="findings[0].text",
            related_id="rat_abc",
        )
        item = feedback_from_decision_packet_issue(issue)
        assert item.feedback_type == "evidence_gap"
        assert item.severity == "critical"
        assert item.evidence_id == "ev_001"
        assert item.field_path == "findings[0].text"
        assert item.related_id == "rat_abc"
        assert item.source_type == "decision_packet"
        _ok("23_feedback_from_decision_packet_issue preserves evidence_id/field_path")
    except Exception as e:
        _fail("23_feedback_from_decision_packet_issue preserves evidence_id/field_path", str(e))


# ---------------------------------------------------------------------------
# Tests: feedback_from_validation_item
# ---------------------------------------------------------------------------

def test_feedback_from_validation_item_maps_types():
    try:
        vi_binding = _make_validation_item(item_type="evidence_binding", severity="warning")
        vi_stale = _make_validation_item(item_id="vi_002", item_type="stale_data", severity="critical", message="Stale data found.")
        vi_missing = _make_validation_item(item_id="vi_003", item_type="missing_data", severity="warning", message="Missing data.")
        vi_safety = _make_validation_item(item_id="vi_004", item_type="safety", severity="critical", message="Safety issue.")

        fb_binding = feedback_from_validation_item(vi_binding)
        fb_stale = feedback_from_validation_item(vi_stale)
        fb_missing = feedback_from_validation_item(vi_missing)
        fb_safety = feedback_from_validation_item(vi_safety)

        assert fb_binding.feedback_type == "evidence_gap"
        assert fb_stale.feedback_type == "stale_data"
        assert fb_missing.feedback_type == "evidence_gap"
        assert fb_safety.feedback_type == "safety_concern"
        assert fb_stale.severity == "critical"
        assert fb_binding.evidence_id == "ev_abc"
        assert fb_binding.related_id == "obj_001"
        _ok("24_feedback_from_validation_item maps missing/stale/evidence issues")
    except Exception as e:
        _fail("24_feedback_from_validation_item maps missing/stale/evidence issues", str(e))


# ---------------------------------------------------------------------------
# Tests: feedback_from_staleness_finding
# ---------------------------------------------------------------------------

def test_feedback_from_staleness_finding_maps_stale():
    try:
        stale = _make_staleness_finding(status="stale", severity="warning", message="Data is stale.")
        expired = _make_staleness_finding(finding_id="sf_002", status="expired", severity="critical", message="Data expired.")
        unknown = _make_staleness_finding(finding_id="sf_003", status="unknown", severity="warning", message="Timestamp unknown.")

        fb_stale = feedback_from_staleness_finding(stale)
        fb_expired = feedback_from_staleness_finding(expired)
        fb_unknown = feedback_from_staleness_finding(unknown)

        assert fb_stale.feedback_type == "stale_data"
        assert fb_expired.feedback_type == "stale_data"
        assert fb_expired.severity == "critical"
        assert fb_unknown.feedback_type == "evidence_gap"
        assert fb_stale.evidence_id == "ev_stale"
        assert fb_stale.related_id == "obj_staleness"
        _ok("25_feedback_from_staleness_finding maps stale data")
    except Exception as e:
        _fail("25_feedback_from_staleness_finding maps stale data", str(e))


# ---------------------------------------------------------------------------
# Tests: feedback_from_critic_issue
# ---------------------------------------------------------------------------

def test_feedback_from_critic_issue_maps_types():
    try:
        ci_risk = _make_critic_issue(issue_type="missing_risk", severity="warning")
        ci_conf = _make_critic_issue(issue_id="ci_002", issue_type="overconfidence", severity="critical", message="Overconfident claim.")
        ci_claim = _make_critic_issue(issue_id="ci_003", issue_type="unsupported_claim", severity="warning", message="Unsupported claim.")

        fb_risk = feedback_from_critic_issue(ci_risk)
        fb_conf = feedback_from_critic_issue(ci_conf)
        fb_claim = feedback_from_critic_issue(ci_claim)

        assert fb_risk.feedback_type == "missing_risk"
        assert fb_conf.feedback_type == "excessive_confidence"
        assert fb_conf.severity == "critical"
        assert fb_claim.feedback_type == "unsupported_claim"
        assert fb_risk.evidence_id == "ev_critic"
        _ok("26_feedback_from_critic_issue maps overconfidence/missing risk")
    except Exception as e:
        _fail("26_feedback_from_critic_issue maps overconfidence/missing risk", str(e))


# ---------------------------------------------------------------------------
# Tests: collect_human_feedback
# ---------------------------------------------------------------------------

def test_collect_feedback_from_decision_packet():
    try:
        dp_issue = _make_dp_issue(
            guardrail_type="insufficient_evidence",
            message="Missing evidence for claim.",
        )
        dp = _make_fake_dp(issues=[dp_issue], guardrails=[])
        bundle = HumanReviewInputBundle(
            bundle_id="b001",
            as_of="2026-05-23",
            decision_packet=dp,
        )
        items = collect_human_feedback(bundle)
        assert len(items) >= 1
        assert any(f.source_type == "decision_packet" for f in items)
        _ok("27_collect_human_feedback collects from decision packet")
    except Exception as e:
        _fail("27_collect_human_feedback collects from decision packet", str(e))


def test_collect_feedback_from_validation_staleness_critic():
    try:
        vi = _make_validation_item()
        va = aggregate_validation_items("agg_001", "2026-05-23", [vi])

        sf = _make_staleness_finding(status="stale")
        sr = aggregate_staleness_findings("sr_001", "2026-05-23", [sf])

        ci = _make_critic_issue()
        # Build a minimal CriticResult manually
        cr = CriticResult(
            critic_id="cr_001",
            as_of="2026-05-23",
            issues=[ci],
        )

        bundle = HumanReviewInputBundle(
            bundle_id="b002",
            as_of="2026-05-23",
            validation_aggregate=va,
            staleness_report=sr,
            critic_result=cr,
        )
        items = collect_human_feedback(bundle)
        source_types = {f.source_type for f in items}
        assert "validation" in source_types
        assert "staleness" in source_types
        assert "critic" in source_types
        _ok("28_collect_human_feedback collects from validation/staleness/critic")
    except Exception as e:
        _fail("28_collect_human_feedback collects from validation/staleness/critic", str(e))


def test_collect_feedback_includes_manual():
    try:
        manual_fb = _make_feedback_item(
            feedback_id="hf_manual001",
            source_type="manual",
            message="Manual reviewer note.",
        )
        bundle = HumanReviewInputBundle(
            bundle_id="b003",
            as_of="2026-05-23",
            manual_feedback=[manual_fb],
        )
        items = collect_human_feedback(bundle)
        assert any(f.source_type == "manual" for f in items)
        _ok("29_collect_human_feedback includes manual feedback")
    except Exception as e:
        _fail("29_collect_human_feedback includes manual feedback", str(e))


def test_collect_feedback_deduplicates():
    try:
        # Two items with identical inputs → same feedback_id → deduplicated
        vi1 = _make_validation_item(item_id="vi_dup1", message="Duplicate message.")
        vi2 = _make_validation_item(item_id="vi_dup2", message="Duplicate message.")
        va = aggregate_validation_items("agg_dup", "2026-05-23", [vi1, vi2])
        bundle = HumanReviewInputBundle(
            bundle_id="b004",
            as_of="2026-05-23",
            validation_aggregate=va,
        )
        items = collect_human_feedback(bundle)
        ids = [f.feedback_id for f in items]
        assert len(ids) == len(set(ids)), "Duplicate feedback_ids found"
        _ok("30_collect_human_feedback deduplicates")
    except Exception as e:
        _fail("30_collect_human_feedback deduplicates", str(e))


# ---------------------------------------------------------------------------
# Tests: build_revision_requests
# ---------------------------------------------------------------------------

def test_build_revision_requests_critical_blocked():
    try:
        critical_fb = _make_feedback_item(severity="critical", feedback_type="safety_concern")
        rrs = build_revision_requests([critical_fb])
        assert len(rrs) >= 1
        assert any(r.blocked_until_resolved for r in rrs)
        _ok("31_build_revision_requests creates blocked request for critical feedback")
    except Exception as e:
        _fail("31_build_revision_requests creates blocked request for critical feedback", str(e))


def test_build_revision_requests_evidence_gap():
    try:
        fb = _make_feedback_item(feedback_type="evidence_gap", severity="warning")
        rrs = build_revision_requests([fb])
        assert len(rrs) >= 1
        assert any("evidence" in c.lower() for r in rrs for c in r.requested_changes)
        _ok("32_build_revision_requests creates evidence request for evidence gap")
    except Exception as e:
        _fail("32_build_revision_requests creates evidence request for evidence gap", str(e))


# ---------------------------------------------------------------------------
# Tests: build_review_items
# ---------------------------------------------------------------------------

def test_build_review_items_includes_source_ids():
    try:
        dp = _make_fake_dp(decision_packet_id="dp_abc123")
        bundle = HumanReviewInputBundle(
            bundle_id="b005",
            as_of="2026-05-23",
            ticker="AAPL",
            decision_packet=dp,
        )
        items = build_review_items(bundle, [], [])
        dp_items = [i for i in items if i.source_type == "decision_packet"]
        assert len(dp_items) >= 1
        assert dp_items[0].source_id == "dp_abc123"
        _ok("33_build_review_items includes source IDs")
    except Exception as e:
        _fail("33_build_review_items includes source IDs", str(e))


# ---------------------------------------------------------------------------
# Tests: determine_human_review_outcome
# ---------------------------------------------------------------------------

def test_outcome_blocks_on_critical_feedback():
    try:
        critical_fb = _make_feedback_item(severity="critical", feedback_type="safety_concern")
        blocked_rr = _make_revision_request(blocked=True)
        outcome = determine_human_review_outcome([critical_fb], [blocked_rr])
        assert outcome.blocked is True
        assert outcome.approved_for_execution is False
        assert outcome.status in ("blocked", "changes_requested")
        _ok("34_determine_human_review_outcome blocks on critical feedback")
    except Exception as e:
        _fail("34_determine_human_review_outcome blocks on critical feedback", str(e))


def test_outcome_requests_revision_on_warnings():
    try:
        warning_fb = _make_feedback_item(severity="warning", feedback_type="missing_risk")
        rr = _make_revision_request(blocked=False)
        outcome = determine_human_review_outcome([warning_fb], [rr])
        assert outcome.status == "changes_requested"
        assert outcome.decision == "request_revision"
        assert outcome.approved_for_execution is False
        _ok("35_determine_human_review_outcome requests revision on warnings")
    except Exception as e:
        _fail("35_determine_human_review_outcome requests revision on warnings", str(e))


def test_outcome_approves_research_only_on_clean_inputs():
    try:
        outcome = determine_human_review_outcome([], [])
        assert outcome.decision == "approve_for_research"
        assert outcome.status == "approved_for_research_only"
        assert outcome.approved_for_research_only is True
        assert outcome.approved_for_execution is False
        _ok("36_determine_human_review_outcome approves research-only on clean inputs")
    except Exception as e:
        _fail("36_determine_human_review_outcome approves research-only on clean inputs", str(e))


def test_outcome_never_approves_execution():
    try:
        outcome1 = determine_human_review_outcome([], [])
        outcome2 = determine_human_review_outcome(
            [_make_feedback_item(severity="critical")], []
        )
        outcome3 = determine_human_review_outcome(
            [_make_feedback_item(severity="warning")], []
        )
        assert outcome1.approved_for_execution is False
        assert outcome2.approved_for_execution is False
        assert outcome3.approved_for_execution is False
        _ok("37_determine_human_review_outcome never approves execution")
    except Exception as e:
        _fail("37_determine_human_review_outcome never approves execution", str(e))


def test_outcome_blocks_on_critical_without_blocked_revision():
    """
    Regression: critical feedback must produce a blocking outcome even when
    revision_requests is empty (no pre-built blocked revision was supplied).
    Contract: decision=="block", status=="blocked", recommendation=="block",
    approved_for_execution is False.
    """
    try:
        critical_fb = _make_feedback_item(severity="critical", feedback_type="safety_concern")
        outcome = determine_human_review_outcome([critical_fb], [])
        assert outcome.decision == "block", (
            f"Expected decision='block', got {outcome.decision!r}"
        )
        assert outcome.status == "blocked", (
            f"Expected status='blocked', got {outcome.status!r}"
        )
        assert outcome.recommendation == "block", (
            f"Expected recommendation='block', got {outcome.recommendation!r}"
        )
        assert outcome.approved_for_execution is False
        _ok("37b_determine_human_review_outcome blocks on critical feedback without pre-built blocked revision")
    except Exception as e:
        _fail("37b_determine_human_review_outcome blocks on critical feedback without pre-built blocked revision", str(e))


# ---------------------------------------------------------------------------
# Tests: build_human_review_report
# ---------------------------------------------------------------------------

def test_build_report_normalizes_status():
    try:
        critical_fb = _make_feedback_item(severity="critical")
        report = build_human_review_report(
            review_report_id="hrr_norm_001",
            as_of="2026-05-23",
            feedback_items=[critical_fb],
        )
        assert report.status == "blocked"
        assert report.recommendation == "block"

        warn_fb = _make_feedback_item(
            feedback_id="hf_warn",
            severity="warning",
            feedback_type="missing_risk",
        )
        report2 = build_human_review_report(
            review_report_id="hrr_norm_002",
            as_of="2026-05-23",
            feedback_items=[warn_fb],
        )
        assert report2.status == "changes_requested"
        assert report2.recommendation == "revise"

        report3 = build_human_review_report(
            review_report_id="hrr_norm_003",
            as_of="2026-05-23",
            feedback_items=[],
        )
        assert report3.status == "pending"
        _ok("38_build_human_review_report normalizes status/recommendation")
    except Exception as e:
        _fail("38_build_human_review_report normalizes status/recommendation", str(e))


# ---------------------------------------------------------------------------
# Tests: run_human_review_skeleton
# ---------------------------------------------------------------------------

def test_skeleton_returns_deterministic_report():
    try:
        bundle = _make_bundle()
        r1 = run_human_review_skeleton(bundle)
        r2 = run_human_review_skeleton(bundle)
        assert r1.review_report_id == r2.review_report_id
        assert r1.status == r2.status
        _ok("39_run_human_review_skeleton returns deterministic report")
    except Exception as e:
        _fail("39_run_human_review_skeleton returns deterministic report", str(e))


def test_skeleton_does_not_mutate_bundle():
    try:
        bundle = _make_bundle()
        original_id = bundle.bundle_id
        original_as_of = bundle.as_of
        _ = run_human_review_skeleton(bundle)
        assert bundle.bundle_id == original_id
        assert bundle.as_of == original_as_of
        _ok("40_run_human_review_skeleton does not mutate input bundle")
    except Exception as e:
        _fail("40_run_human_review_skeleton does not mutate input bundle", str(e))


def test_skeleton_clean_packet_approves_research_only():
    try:
        clean_dp = _make_fake_dp(issues=[], guardrails=[])
        bundle = HumanReviewInputBundle(
            bundle_id="b_clean",
            as_of="2026-05-23",
            ticker="MSFT",
            decision_packet=clean_dp,
        )
        report = run_human_review_skeleton(bundle)
        assert report.status == "approved_for_research_only"
        if report.outcome is not None:
            assert report.outcome.approved_for_execution is False
            assert report.outcome.approved_for_research_only is True
        _ok("41_run_human_review_skeleton with clean packet approves research-only, not execution")
    except Exception as e:
        _fail("41_run_human_review_skeleton with clean packet approves research-only, not execution", str(e))


def test_skeleton_critical_guardrail_blocks():
    try:
        # Use a validation item with critical severity to simulate a blocker
        vi_critical = _make_validation_item(severity="critical", message="Critical validation failure.")
        va = aggregate_validation_items("agg_crit", "2026-05-23", [vi_critical])
        bundle = HumanReviewInputBundle(
            bundle_id="b_crit",
            as_of="2026-05-23",
            ticker="TSLA",
            validation_aggregate=va,
        )
        report = run_human_review_skeleton(bundle)
        assert report.status in ("blocked", "changes_requested")
        if report.outcome is not None:
            assert report.outcome.approved_for_execution is False
        _ok("42_run_human_review_skeleton with critical guardrail blocks or requests revision")
    except Exception as e:
        _fail("42_run_human_review_skeleton with critical guardrail blocks or requests revision", str(e))


# ---------------------------------------------------------------------------
# Tests: human_review_tool_result_from_report
# ---------------------------------------------------------------------------

def test_tool_result_valid():
    try:
        report = _make_report()
        tr = human_review_tool_result_from_report("run_001", report)
        assert isinstance(tr, ToolResult)
        assert tr.tool_name == "human_review_report"
        _ok("43_human_review_tool_result_from_report returns valid ToolResult")
    except Exception as e:
        _fail("43_human_review_tool_result_from_report returns valid ToolResult", str(e))


def test_tool_result_stable_tool_name_target():
    try:
        report = HumanReviewReport(
            review_report_id="hrr_tr001",
            as_of="2026-05-23",
            ticker="AAPL",
        )
        tr1 = human_review_tool_result_from_report("run_001", report)
        tr2 = human_review_tool_result_from_report("run_001", report)
        assert tr1.tool_name == "human_review_report"
        assert tr2.tool_name == "human_review_report"
        assert tr1.ticker == "AAPL"
        assert tr2.ticker == "AAPL"
        # evidence_id encodes target; check it contains "AAPL"
        assert "AAPL" in tr1.evidence_id
        _ok("44_Human Review ToolResult has stable tool_name and target")
    except Exception as e:
        _fail("44_Human Review ToolResult has stable tool_name and target", str(e))


def test_tool_result_payload_includes_report_summary_version():
    try:
        report = _make_report()
        tr = human_review_tool_result_from_report("run_001", report)
        assert "report" in tr.outputs
        assert "summary" in tr.outputs
        assert "calculation_version" in tr.outputs
        assert tr.outputs["calculation_version"] == "human_review_skeleton_v1"
        _ok("45_Human Review ToolResult payload includes report, summary, calculation_version")
    except Exception as e:
        _fail("45_Human Review ToolResult payload includes report, summary, calculation_version", str(e))


def test_tool_result_evidence_id_deterministic():
    try:
        report = _make_report()
        tr1 = human_review_tool_result_from_report("run_001", report)
        tr2 = human_review_tool_result_from_report("run_001", report)
        assert tr1.evidence_id == tr2.evidence_id
        _ok("46_Human Review ToolResult evidence_id deterministic for identical report payload")
    except Exception as e:
        _fail("46_Human Review ToolResult evidence_id deterministic for identical report payload", str(e))


def test_tool_result_evidence_id_changes_on_report_change():
    try:
        r1 = HumanReviewReport(review_report_id="hrr_a", as_of="2026-05-23")
        r2 = HumanReviewReport(review_report_id="hrr_b", as_of="2026-05-23")
        tr1 = human_review_tool_result_from_report("run_001", r1)
        tr2 = human_review_tool_result_from_report("run_001", r2)
        assert tr1.evidence_id != tr2.evidence_id
        _ok("47_Human Review ToolResult evidence_id changes when report payload changes")
    except Exception as e:
        _fail("47_Human Review ToolResult evidence_id changes when report payload changes", str(e))


# ---------------------------------------------------------------------------
# Tests: summarize_human_review_report
# ---------------------------------------------------------------------------

def test_summarize_returns_expected_fields():
    try:
        fb_crit = _make_feedback_item(severity="critical")
        fb_warn = _make_feedback_item(
            feedback_id="hf_w001",
            severity="warning",
            feedback_type="missing_risk",
            message="Missing risk.",
        )
        fb_info = _make_feedback_item(
            feedback_id="hf_i001",
            severity="info",
            feedback_type="wording_change",
            message="Minor wording.",
        )
        report = HumanReviewReport(
            review_report_id="hrr_summ",
            as_of="2026-05-23",
            ticker="NVDA",
            feedback_items=[fb_crit, fb_warn, fb_info],
        )
        summary = summarize_human_review_report(report)
        assert summary["review_report_id"] == "hrr_summ"
        assert summary["ticker"] == "NVDA"
        assert summary["feedback_count"] == 3
        assert summary["critical_count"] == 1
        assert summary["warning_count"] == 1
        assert summary["info_count"] == 1
        assert summary["approved_for_execution"] is False
        assert isinstance(summary["top_messages"], list)
        assert len(summary["top_messages"]) <= 10
        _ok("48_summarize_human_review_report returns expected summary")
    except Exception as e:
        _fail("48_summarize_human_review_report returns expected summary", str(e))


# ---------------------------------------------------------------------------
# Tests: __all__ smoke test (Phase 3F symbols in lib.reliability.__all__)
# ---------------------------------------------------------------------------

def test_phase3f_all_exports_present():
    try:
        import lib.reliability as rel
        expected_symbols = [
            "HumanReviewStatus", "HumanReviewDecision", "HumanFeedbackType",
            "HumanFeedbackSeverity", "HumanReviewerRole", "HumanReviewSourceType",
            "HumanReviewRecommendation", "HumanFeedbackItem", "HumanRevisionRequest",
            "HumanReviewItem", "HumanReviewOutcome", "HumanReviewReport",
            "HumanReviewInputBundle", "make_human_feedback_id", "make_human_review_report_id",
            "feedback_from_decision_packet_issue", "feedback_from_validation_item",
            "feedback_from_staleness_finding", "feedback_from_critic_issue",
            "collect_human_feedback", "build_revision_requests", "build_review_items",
            "determine_human_review_outcome", "build_human_review_report",
            "run_human_review_skeleton", "human_review_tool_result_from_report",
            "summarize_human_review_report",
        ]
        missing = [s for s in expected_symbols if s not in rel.__all__]
        assert not missing, f"Phase 3F symbols missing from __all__: {missing}"
        _ok("48b_Phase 3F symbols present in lib.reliability.__all__")
    except Exception as e:
        _fail("48b_Phase 3F symbols present in lib.reliability.__all__", str(e))


# ---------------------------------------------------------------------------
# Tests: source_id aggregation across all artifact types
# ---------------------------------------------------------------------------

def test_source_id_aggregation_across_artifacts():
    try:
        class _FakeDebate:
            debate_id = "deb_src001"

        class _FakeHSR:
            synthesis_id = "hsr_src001"

        class _FakeMacro:
            macro_agent_id = "mac_src001"

        vi = _make_validation_item()
        va = aggregate_validation_items("agg_src001", "2026-05-23", [vi])
        sf = _make_staleness_finding()
        sr = aggregate_staleness_findings("sr_src001", "2026-05-23", [sf])
        ci = _make_critic_issue()
        cr = CriticResult(critic_id="cr_src001", as_of="2026-05-23", issues=[ci])
        dp = _make_fake_dp(decision_packet_id="dp_src001")

        bundle = HumanReviewInputBundle(
            bundle_id="b_srcagg",
            as_of="2026-05-23",
            ticker="GOOG",
            decision_packet=dp,
            debate_report=_FakeDebate(),
            horizon_synthesis_report=_FakeHSR(),
            macro_agent_result=_FakeMacro(),
            validation_aggregate=va,
            staleness_report=sr,
            critic_result=cr,
        )
        report = run_human_review_skeleton(bundle)
        assert "decision_packet_id" in report.source_ids, "decision_packet_id missing from source_ids"
        assert report.source_ids["decision_packet_id"] == "dp_src001"
        assert "debate_id" in report.source_ids, "debate_id missing from source_ids"
        assert report.source_ids["debate_id"] == "deb_src001"
        assert "synthesis_id" in report.source_ids, "synthesis_id missing from source_ids"
        assert report.source_ids["synthesis_id"] == "hsr_src001"
        assert "macro_agent_id" in report.source_ids, "macro_agent_id missing from source_ids"
        assert report.source_ids["macro_agent_id"] == "mac_src001"
        _ok("48c_run_human_review_skeleton aggregates source IDs across all artifact types")
    except Exception as e:
        _fail("48c_run_human_review_skeleton aggregates source IDs across all artifact types", str(e))


# ---------------------------------------------------------------------------
# Tests: serialization roundtrips
# ---------------------------------------------------------------------------

def test_review_report_roundtrip():
    try:
        report = run_human_review_skeleton(_make_bundle())
        d = report.model_dump()
        report2 = HumanReviewReport.model_validate(d)
        assert report2.review_report_id == report.review_report_id
        assert report2.status == report.status
        _ok("49_HumanReviewReport serialization roundtrip")
    except Exception as e:
        _fail("49_HumanReviewReport serialization roundtrip", str(e))


def test_feedback_item_roundtrip():
    try:
        item = _make_feedback_item()
        d = item.model_dump()
        item2 = HumanFeedbackItem.model_validate(d)
        assert item2.feedback_id == item.feedback_id
        assert item2.feedback_type == item.feedback_type
        _ok("50_HumanFeedbackItem serialization roundtrip")
    except Exception as e:
        _fail("50_HumanFeedbackItem serialization roundtrip", str(e))


# ---------------------------------------------------------------------------
# Guards: no live app modules, no external calls, no LLM, no execution
# ---------------------------------------------------------------------------

def test_no_live_app_imports():
    try:
        import lib.reliability.human_review as hr_module
        source = open(hr_module.__file__).read()
        # Check for actual import statements referencing forbidden modules
        forbidden_imports = [
            "import app",
            "from app ",
            "from pages",
            "import llm_orchestrator",
            "from lib.llm_orchestrator",
        ]
        for f in forbidden_imports:
            assert f not in source, f"Found forbidden import statement: {f!r}"
        _ok("51_No live app modules are imported")
    except Exception as e:
        _fail("51_No live app modules are imported", str(e))


def test_no_external_api_calls():
    try:
        import lib.reliability.human_review as hr_module
        source = open(hr_module.__file__).read()
        forbidden = ["requests.get", "urllib.request", "httpx.get", "boto3", "aiohttp"]
        for f in forbidden:
            assert f not in source, f"Found external API call: {f!r}"
        _ok("52_No external API/network calls are made")
    except Exception as e:
        _fail("52_No external API/network calls are made", str(e))


def test_no_llm_api_calls():
    try:
        import lib.reliability.human_review as hr_module
        source = open(hr_module.__file__).read()
        forbidden = ["anthropic", "openai", "claude", "ChatCompletion"]
        for f in forbidden:
            assert f not in source, f"Found LLM API reference: {f!r}"
        _ok("53_No Claude/LLM API is called")
    except Exception as e:
        _fail("53_No Claude/LLM API is called", str(e))


def test_no_approved_for_execution():
    try:
        # Exhaustive check: run skeleton with all inputs and verify
        bundle = _make_bundle()
        report = run_human_review_skeleton(bundle)
        if report.outcome:
            assert report.outcome.approved_for_execution is False

        # Attempt to create outcome with approved_for_execution=True should fail
        raised = False
        try:
            HumanReviewOutcome(
                outcome_id="bad_001",
                rationale="Should fail",
                approved_for_execution=True,
            )
        except pydantic.ValidationError:
            raised = True
        assert raised, "Should have raised ValidationError"
        _ok("54_No approved_for_execution=True possible in Phase 3F")
    except Exception as e:
        _fail("54_No approved_for_execution=True possible in Phase 3F", str(e))


# ---------------------------------------------------------------------------
# Regression: run prior phase scripts
# ---------------------------------------------------------------------------

_PRIOR_SCRIPTS = [
    "scripts/test_reliability_foundation.py",
    "scripts/test_reliability_negative_cases.py",
    "scripts/test_reliability_adapters.py",
    "scripts/test_reliability_valuation_adapter.py",
    "scripts/test_reliability_technical_adapter.py",
    "scripts/test_reliability_scanner_rotation_adapter.py",
    "scripts/test_reliability_agent_output.py",
    "scripts/test_reliability_prompt_contracts.py",
    "scripts/test_reliability_mock_agent_roundtrip.py",
    "scripts/test_reliability_orchestration_plan.py",
    "scripts/test_reliability_config.py",
    "scripts/test_reliability_horizon.py",
    "scripts/test_reliability_macro.py",
    "scripts/test_reliability_allocation.py",
    "scripts/test_reliability_options.py",
    "scripts/test_reliability_news.py",
    "scripts/test_reliability_catalysts.py",
    "scripts/test_reliability_validation_aggregator.py",
    "scripts/test_reliability_staleness.py",
    "scripts/test_reliability_critic.py",
    "scripts/test_reliability_evaluation_harness.py",
    "evals/run_evals.py",
    "scripts/test_reliability_phase_2_closeout.py",
    "scripts/test_reliability_orchestration_skeleton.py",
    "scripts/test_reliability_horizon_synthesis.py",
    "scripts/test_reliability_macro_agent.py",
    "scripts/test_reliability_debate.py",
    "scripts/test_reliability_decision_packet.py",
]


def test_regression_prior_phases():
    """Run all prior phase test scripts and verify they pass."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    all_passed = True
    for script in _PRIOR_SCRIPTS:
        script_path = os.path.join(repo_root, script)
        if not os.path.exists(script_path):
            _fail(f"55_Regression/{script}", f"Script not found: {script_path}")
            all_passed = False
            continue
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        if result.returncode != 0:
            _fail(
                f"55_Regression/{script}",
                f"Exit code {result.returncode}\n{result.stderr[-500:]}",
            )
            all_passed = False
        else:
            _ok(f"55_Regression/{script}")
    return all_passed


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("Phase 3F: Human Review / Feedback Schema Skeleton — Test Suite")
    print("=" * 70)
    print()

    # Schema tests
    test_human_feedback_item_valid()
    test_human_feedback_item_rejects_empty_id()
    test_human_feedback_item_rejects_empty_message()
    test_revision_request_valid()
    test_revision_request_rejects_empty_id()
    test_revision_request_rejects_empty_reason()
    test_review_item_valid()
    test_review_item_rejects_empty_id()
    test_review_item_rejects_empty_summary()
    test_review_outcome_valid()
    test_review_outcome_rejects_empty_id()
    test_review_outcome_rejects_empty_rationale()
    test_review_outcome_cannot_approve_execution()
    test_review_report_valid()
    test_review_report_rejects_empty_id()
    test_review_report_rejects_empty_as_of()
    test_input_bundle_minimal()
    test_input_bundle_rejects_empty_bundle_id()
    test_input_bundle_rejects_empty_as_of()

    # ID generator tests
    test_feedback_id_deterministic()
    test_feedback_id_changes_on_input_change()
    test_review_report_id_deterministic()

    # Converter tests
    test_feedback_from_dp_issue_preserves_fields()
    test_feedback_from_validation_item_maps_types()
    test_feedback_from_staleness_finding_maps_stale()
    test_feedback_from_critic_issue_maps_types()

    # Collector tests
    test_collect_feedback_from_decision_packet()
    test_collect_feedback_from_validation_staleness_critic()
    test_collect_feedback_includes_manual()
    test_collect_feedback_deduplicates()

    # Revision request tests
    test_build_revision_requests_critical_blocked()
    test_build_revision_requests_evidence_gap()

    # Review item tests
    test_build_review_items_includes_source_ids()

    # Outcome tests
    test_outcome_blocks_on_critical_feedback()
    test_outcome_requests_revision_on_warnings()
    test_outcome_approves_research_only_on_clean_inputs()
    test_outcome_never_approves_execution()
    test_outcome_blocks_on_critical_without_blocked_revision()

    # Report tests
    test_build_report_normalizes_status()

    # Skeleton tests
    test_skeleton_returns_deterministic_report()
    test_skeleton_does_not_mutate_bundle()
    test_skeleton_clean_packet_approves_research_only()
    test_skeleton_critical_guardrail_blocks()

    # ToolResult tests
    test_tool_result_valid()
    test_tool_result_stable_tool_name_target()
    test_tool_result_payload_includes_report_summary_version()
    test_tool_result_evidence_id_deterministic()
    test_tool_result_evidence_id_changes_on_report_change()

    # Summary tests
    test_summarize_returns_expected_fields()

    # __all__ smoke test and source_id aggregation
    test_phase3f_all_exports_present()
    test_source_id_aggregation_across_artifacts()

    # Serialization tests
    test_review_report_roundtrip()
    test_feedback_item_roundtrip()

    # Guard tests
    test_no_live_app_imports()
    test_no_external_api_calls()
    test_no_llm_api_calls()
    test_no_approved_for_execution()

    # Print Phase 3F results
    print()
    for t in _TESTS:
        print(t)
    print()
    print(f"Phase 3F tests: {_PASS} passed, {_FAIL} failed out of {_PASS + _FAIL} total")

    if _FAIL > 0:
        print()
        print("PHASE 3F TESTS FAILED")
        sys.exit(1)

    # Regression
    print()
    print("=" * 70)
    print("Running regression (prior phase scripts)...")
    print("=" * 70)
    test_regression_prior_phases()

    # Print regression results
    regression_tests = [t for t in _TESTS if "Regression" in t]
    regression_pass = sum(1 for t in regression_tests if "PASS" in t)
    regression_fail = sum(1 for t in regression_tests if "FAIL" in t)
    print()
    for t in regression_tests:
        print(t)
    print()
    print(f"Regression: {regression_pass} passed, {regression_fail} failed")

    total_fail = _FAIL + regression_fail
    if total_fail > 0:
        print("SOME TESTS FAILED")
        sys.exit(1)
    else:
        total_pass = _PASS + regression_pass
        print()
        print(f"All {total_pass} tests passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
